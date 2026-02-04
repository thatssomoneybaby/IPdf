COMPOSE := docker compose -f docker/docker-compose.yml

.PHONY: up down logs ps build build-base

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

build-base:
	$(COMPOSE) --profile build build docling-base api
