import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    description: z.string(),
    ticker: z.string().optional(),
    sector: z.enum(["semiconductor", "battery", "market"]).optional(),
    tags: z.array(z.string()).default([]),
  }),
});

export const collections = { posts };
