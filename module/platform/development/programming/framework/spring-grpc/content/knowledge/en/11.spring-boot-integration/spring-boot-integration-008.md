# Properties and YAML for gRPC in Spring Boot

## 1. The Role of Properties in gRPC Integration

A **SPRING_GRPC** application can both expose a gRPC server and call multiple remote gRPC services. Environment-specific settings such as ports, targets, TLS certificates, trust stores, and transport options must be externalized into configuration rather than hardcoded in Java code.

Spring Boot reads configuration from YAML/properties, merges multiple sources, and binds them into configuration objects. The gRPC starter leverages that mechanism to configure servers and clients. Consequently, developers must understand three layers:

1. **YAML syntax:** hierarchical structure, data types, indentation, and placeholders.
2. **Property names:** server/client namespaces and logical client names exposed by the starter.
3. **Binding and value sources:** how Spring turns configuration into runtime values, along with precedence across files, profiles, environment variables, and command-line arguments.

This lesson focuses on **Properties and YAML for gRPC**. Examples use **`net.devh:grpc-server-spring-boot-starter`** and **`net.devh:grpc-client-spring-boot-starter`**, with the `grpc.server.*` and `grpc.client.<name>.*` prefixes. Official Spring gRPC has its own property system and configuration; always consult the reference for your exact starter/version. Never mix property names between the two ecosystems.

## 2. YAML Is a Data Structure

YAML represents objects using indentation. In Spring Boot, hierarchical keys normally map to dot-separated properties.

Example:

```yaml
grpc:
  server:
    port: 9090
  client:
    inventory:
      address: "static://inventory.internal:9090"
      negotiationType: TLS
```

This is equivalent to the properties:

- `grpc.server.port = 9090`
- `grpc.client.inventory.address = static://inventory.internal:9090`
- `grpc.client.inventory.negotiationType = TLS`

Lines at the same indentation level are members of the same object. YAML uses spaces—never tabs—for indentation. Deeper nesting must add a consistent number of spaces; incorrect indentation can cause YAML parse failures or bind structures differently than expected.

### 2.1. Data Types

| YAML Value | Typical Parsed Type | Usage |
| --- | --- | --- |
| `9090` | Integer | Ports, counts |
| `true` / `false` | Boolean | Toggling features |
| `"static://host:9090"` | String | Addresses, URIs, enum-like values |
| `null` or `~` | Null | Avoid using instead of required values |
| `[a, b]` | List | Ordered values if supported by the property |
| Nested block | Map/object | Server and named client groups |

Fields representing URIs, hostnames, enums, or values with special characters should be quoted to make string intent explicit. Do not quote ports when the property expects an integer, unless the starter documentation requires a string.

Example:

```yaml
grpc:
  server:
    port: 9090
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: "TLS"
```

Avoid type-confusion patterns:

- `port: "9090"` when the property expects an integer.
- `enabled: "true"` when the property expects a boolean.
- Leaving `address:` blank when the client requires a target.
- Using tabs for indentation or declaring duplicate keys at the same level.

## 3. Two Main Namespaces: Server and Client

With the `net.devh` starter, server and client configuration are split into two branches:

```text
grpc
├── server
│   ├── port
│   ├── address / security / supported server properties
│   └── ...
└── client
    ├── inventory
    │   ├── address
    │   ├── negotiationType
    │   └── security / supported client properties
    └── payment
        ├── address
        └── ...
```

**`grpc.server.*`** applies to the gRPC server managed by the server starter. **`grpc.client.<name>.*`** applies to a logically named client/channel. They do not replace `server.port` for Spring Web or `management.server.port` for Actuator.

### 3.1. Server Properties

A basic server configuration:

```yaml
grpc:
  server:
    port: 9090
```

You can add TLS for deployment:

```yaml
grpc:
  server:
    port: 9090
    security:
      enabled: true
      certificateChain: "file:/run/secrets/grpc/server.crt"
      privateKey: "file:/run/secrets/grpc/server.key"
```

Property names follow `net.devh`; verify resource formats and security fields in the reference for your exact version. Paths must exist and be readable by the process. Never store real private keys in the repository.

If the application runs both an HTTP server and a gRPC server, declare two separate ports:

```yaml
server:
  port: 8080

grpc:
  server:
    port: 9090
```

Here `server.port` configures the HTTP listener if a web stack is present; `grpc.server.port` configures the starter's gRPC listener. Changing one value does not automatically change the other.

### 3.2. Named Client Properties

Each remote client sits under its own key name:

```yaml
grpc:
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: TLS
    payment:
      address: "dns:///payment.internal:9090"
      negotiationType: TLS
```

The names `inventory` and `payment` are **client names** used to link configuration to the corresponding injection point, e.g., `@GrpcClient("inventory")`. These names do not have to match the Protobuf package, Java class name, or DNS hostname.

If two backends have different targets or security policies, give them separate client names. Do not group them under one shared configuration and share a channel when connection policies differ.

## 4. Address Format and Negotiation Type

### 4.1. Address Is a Logical Target

Common examples:

| Address | Purpose |
| --- | --- |
| `static://localhost:9090` | Fixed endpoint for local use |
| `static://inventory.internal:9090` | Fixed endpoint by hostname |
| `dns:///inventory.internal:9090` | Uses gRPC Java's DNS resolver if supported at runtime |
| `in-process:inventory-test` | In-process transport when supported by starter/version |

Not every scheme is supported by every starter. A scheme requires a matching resolver on the runtime classpath. If the client initializes yet fails to resolve the target, inspect the scheme and name resolver before modifying RPC methods.

Avoid hardcoding ephemeral pod or container IPs. In orchestrated environments, prefer stable DNS/service names or a discovery-integrated resolver.

### 4.2. Negotiation Type

With `net.devh`, common settings are `PLAINTEXT` and `TLS`:

```yaml
grpc:
  client:
    inventory:
      address: "static://localhost:9090"
      negotiationType: PLAINTEXT
```

`PLAINTEXT` is suitable for local loopback or isolated test networks. When calling across untrusted networks, use TLS and configure appropriate trust certificates:

```yaml
grpc:
  client:
    inventory:
      address: "dns:///inventory.internal:9090"
      negotiationType: TLS
      security:
        trustCertCollection: "file:/run/secrets/grpc/inventory-ca.crt"
```

The client must verify the server's certificate chain and hostname/SAN. Never disable verification or use trust-all just to make connections succeed. With mTLS, also configure the client certificate/key and server trust policy per the starter's API.

## 5. Placeholders and Environment Variables

Avoid creating separate YAML variants by hand-editing endpoints before each deploy. Spring Boot supports placeholders to pull values from the `Environment`:

```yaml
grpc:
  server:
    port: ${GRPC_SERVER_PORT:9090}
  client:
    inventory:
      address: "${INVENTORY_GRPC_ADDRESS:static://localhost:9091}"
      negotiationType: ${INVENTORY_GRPC_NEGOTIATION:PLAINTEXT}
```

Syntax:

- `${GRPC_SERVER_PORT:9090}`: uses `GRPC_SERVER_PORT` if set; otherwise falls back to `9090`.
- `${INVENTORY_GRPC_ADDRESS:...}`: reads target from environment, falling back to the local target.
- `${INVENTORY_GRPC_NEGOTIATION:PLAINTEXT}`: reads negotiation mode from environment or uses the default.

Fallbacks should only exist when the default value is genuinely safe. For instance, plaintext or `localhost` fallbacks are handy locally yet dangerous if production forgets to provide the environment variable. For mandatory production values, omit the default so the application fails fast when missing.

### 5.1. Environment Variable Names

Spring Boot supports relaxed binding. A property like:

`grpc.client.inventory.address`

is commonly represented in the environment as:

`GRPC_CLIENT_INVENTORY_ADDRESS`

Similarly:

| Property | Typical Environment Variable |
| --- | --- |
| `grpc.server.port` | `GRPC_SERVER_PORT` |
| `grpc.client.inventory.address` | `GRPC_CLIENT_INVENTORY_ADDRESS` |
| `grpc.client.inventory.negotiationType` | `GRPC_CLIENT_INVENTORY_NEGOTIATIONTYPE` |

Spring Boot's name-conversion rules replace dots with underscores, remove hyphens, and convert to uppercase. For map keys and client names, verify actual binding in your version; keeping client names simple like `inventory` and `payment` avoids unnecessary conversion quirks.

Never pass secrets directly on the command line if process listings or environment logs could expose arguments. Use a secrets manager or secure secret file mounts.

## 6. Configuring Multiple Environments Without Duplicating YAML

Keep stable structure in `application.yml`, then override changing values in profile files.

Shared configuration:

```yaml
spring:
  application:
    name: order-service

grpc:
  server:
    port: ${GRPC_SERVER_PORT:9090}
```

Local configuration:

```yaml
grpc:
  client:
    inventory:
      address: "static://localhost:9091"
      negotiationType: PLAINTEXT
```

Production configuration:

```yaml
grpc:
  client:
    inventory:
      address: ${INVENTORY_GRPC_ADDRESS}
      negotiationType: TLS
      security:
        trustCertCollection: "file:${INVENTORY_GRPC_CA_PATH}"
```

Profiles choose the appropriate value set; environment variables and command-line arguments can still override profile files according to Spring Boot's precedence order. Never assume `application-prod.yml` always beats every other configuration source.

Duplicate only properties that genuinely differ. If the same `grpc.client.inventory.negotiationType` appears in base, local, and prod files, ensure every override is deliberate. Avoid shared defaults that could cause production to connect over plaintext unintentionally.

## 7. Additional Properties: Configure Only When Needed

gRPC starters may offer options for TLS, message size, keepalive, interceptors, executors, or shutdown. Exact names and types vary by version. Before adding a property:

1. Check the exact artifact and version running.
2. Verify the property name in the starter's reference configuration or metadata.
3. Determine the expected type: integer, boolean, enum, duration, or resource path.
4. Check the default value and its impact on server/client behavior.
5. Change one group at a time and measure the effect.

Examples of **data types** in general Spring Boot configuration:

```yaml
app:
  rpc:
    request-timeout: 800ms
    shutdown-grace-period: 20s
    max-payload-size: 4MB
    tracing-enabled: true
```

These are custom application-defined properties illustrating `Duration`, `DataSize`, and boolean; **this does not claim** `net.devh` recognizes `app.rpc.*` keys. When using `@ConfigurationProperties`, declare matching Java types and validation for required values. Never copy these example names under `grpc.*` expecting the starter to understand them.

Keepalive does not replace RPC deadlines; raising message size limits does not replace memory controls; enabling tracing does not automatically propagate trace context without instrumentation/interceptors.

## 8. Verifying Bound Configuration

When YAML is valid yet the server or client misbehaves, inspect the **actual bound values**:

- Active profiles: is the app running with `local`, `test`, or `prod`?
- `grpc.server.port`: which config value did the gRPC listener receive?
- `grpc.client.inventory.address`: what is the final resolved target?
- `grpc.client.inventory.negotiationType`: plaintext or TLS?
- Do certificate/CA paths exist and have read permissions?

You can inspect via `Environment` in tests:

```java
@Autowired
Environment environment;

@Test
void usesTestInventoryTarget() {
    assertEquals(
        "in-process:inventory-test",
        environment.getProperty("grpc.client.inventory.address")
    );
}
```

This assertion example only applies if the test actually declares that target. You can use `@ConfigurationProperties`/`@ConfigurationPropertiesScan` for application-owned settings; for starter properties, inspect starter-provided beans/configurations or read `Environment` rather than instantiating an unbound object manually.

Spring Boot Actuator exposes `env` and `configprops` endpoints if enabled, helping trace property sources and bound values. Because these endpoints can disclose sensitive settings, enable them only in protected administrative environments and never expose secrets.

## 9. Common YAML and Binding Errors

| Symptom | Cause | How to Check |
| --- | --- | --- |
| YAML fails to parse | Wrong indentation, tabs, or unclosed quotes | Check YAML structure and reported line |
| Port does not change | Wrong namespace, inactive profile, or overridden elsewhere | Check effective `grpc.server.port` |
| Client misses target | Wrong client name or wrong nesting under `grpc.client` | Compare `@GrpcClient("name")` with YAML key |
| Address parsed incorrectly | Missing quotes or unresolved placeholder | Check final type and value in `Environment` |
| `UNAVAILABLE` | Wrong target, DNS, port, or transport | Check effective target and network |
| TLS handshake fails | Mismatched CA/SAN/hostname or negotiation mode | Check certificates and trust chain |
| Property has no effect | Starter/version does not support that key | Check version-specific reference configuration |
| Production uses plaintext unexpectedly | Inherited local fallback or overlapping profiles | Remove unsafe fallback and check active profiles |
| Invalid duration value | Property expects integer or duration, wrong format | Match Java type and supported syntax |

YAML syntax errors usually fail immediately when building the `Environment`. Binding errors often surface when the starter creates beans. Wrong targets or TLS mismatches usually surface only when the channel connects or an RPC is invoked. Separating these phases helps focus investigation on the right layer.

## 10. Workflow for Writing and Reviewing gRPC YAML

1. Identify the starter and version, using its exact property namespace.
2. Separate server properties from client properties; give each remote backend its own client name.
3. Choose proper YAML types: numbers for ports, booleans for flags, quoted strings for URIs/enums.
4. Use placeholders for environment-dependent endpoints and secrets.
5. Never leave plaintext or `localhost` as production fallbacks.
6. Select profiles and verify property precedence.
7. Confirm keys are actually bound by the starter; never guess property names from Java field names.
8. Start the server, invoke a real client RPC, and verify TLS and status codes.
9. Check logs/metrics without logging tokens, private keys, or sensitive payloads.

When configured properly, YAML clearly documents **where the server listens, which target each client calls, how transports are secured, and which environment supplies each value**. This lets teams adjust endpoints and connection policies without editing business code while making misconfigurations easy to catch before traffic arrives.
