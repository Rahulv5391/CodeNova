"use server";

import axios, { HttpStatusCode } from "axios";
import { cookies } from "next/headers";
import { Repository } from "@/types/repo";
import { revalidatePath } from "next/cache";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

export async function getServerApi() {
  const cookieStore = await cookies();

  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  console.log(cookieStore.getAll());
  console.log(cookieStore.get("jwt"));

  return axios.create({
    baseURL: backendUrl,
    headers: {
      Cookie: cookieHeader,
    },
  });
}

export async function getRepos() {
  const api = await getServerApi();
  const { data } = await api.get("/repos");
  return data;
}

export async function deleteRepo(repo: Repository) {
  try {
    const api = await getServerApi();
    const response = await api.delete(`/repos/${repo.id}`);

    if (response.status !== HttpStatusCode.Ok) {
      throw new Error("Failed to delete repository");
    }

    revalidatePath("/dashboard");

    return {
      success: true,
    };
  } catch (error) {
    console.error("Delete repo failed:", error);

    throw new Error("Could not delete repository");
  }
}


export async function updateRepo(repo: Repository) {
  const api = await getServerApi();
  const response = await api.post(`/repos/${repo.id}/refresh`)
  if (
    ![
      HttpStatusCode.Ok,
      HttpStatusCode.Created,
      HttpStatusCode.Accepted,
    ].includes(response.status)
  ) {
      throw new Error("Failed to Update repository");
  }
  revalidatePath("/dashboard");
  return response.data;
}
