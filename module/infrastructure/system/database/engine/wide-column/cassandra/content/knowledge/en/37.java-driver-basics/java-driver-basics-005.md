# Driver Configuration, Execution Profiles, and Effective Values in the Cassandra Java Driver

> **Chapter:** Java Driver Basics  
> **Scope:** Configuring Apache Cassandra Java Driver 4.x for Java applications via HOCON, `DriverConfigLoader`, default/named execution profiles, and per-statement attributes; how to verify **effective runtime values** when issuing CQL, understand multi-layer precedence, hot reload, statement immutability, and production risks. API examples closely follow Java Driver 4.17; from 4.18, the Java Driver project is maintained by the Apache Software Foundation, so always verify documentation for your actual version and artifact.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain **`DriverConfigLoader`**, `DriverConfig`, `DriverExecutionProfile`, `reference.conf`, `application.conf`, system properties, and programmatic overrides.
2. Read the exact precedence across **configuration sources**, between **default and named profiles**, and between **profiles and explicit statement settings**.
3. Create execution profiles for **point lookups, range/paged reads, and administrative operations** with distinct timeouts, consistency levels, page sizes, and idempotence settings.
4. Distinguish **declared values**, **resolved config values**, and the **final effective value used by a request**, including under hot reload.
5. Query typed getters on `session.getContext().getConfig()`, verify existing profiles, track down JVM overrides, and identify non-reloadable options.
6. Write a Java 17 application using `CqlSession`, `SimpleStatement`/`PreparedStatement`/`BoundStatement`, and named profiles per the 4.x API.
7. Set `local-datacenter`, contact points, CL, request timeout, serial consistency, paging, and idempotence to match replication and business goals.
8. Run CQL + Java tests on a lab cluster, compare default/profile/request overrides, then execute a controlled change and verify rollback.

**Context:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` requires understanding distributed wide-column architecture, partition keys, query-driven table design, read/write consistency, and Java connectivity. Driver configuration is the **client-side request behavior control layer**, not a substitute for partition key design, replica placement, compaction/repair, or actual data in Cassandra.

## 2. Four Layers to Distinguish When Discussing "Effective Values"

A request can be influenced by multiple layers:

~~~text
                      JAVA APPLICATION
                             |
                 CqlSession / DriverContext
                             |
                 DRIVER CONFIG LOADER
         +-------------------+-------------------+
         |                   |                   |
   reference.conf     application.conf      system properties
    defaults             overrides          (+ programmatic)
         +-------------------+-------------------+
                             |
                      DEFAULT PROFILE
                             |
                 NAMED PROFILE (if selected)
                   inherit + override
                             |
                 STATEMENT-LEVEL OPTIONS
                   explicit values
                             |
                     EFFECTIVE REQUEST
              timeout / CL / page / idempotence
                             |
                 COORDINATOR -> REPLICAS
~~~

Ask precisely:

1. **Declared value:** What value appears in a specific file or property?
2. **Resolved config value:** After merging/fallback, what does `DriverExecutionProfile` return?
3. **Selected profile:** Does the request actually use `default` or a named/derived profile?
4. **Explicit statement value:** Does `setTimeout` or `setConsistencyLevel` on the statement override the profile?
5. **Runtime behavior:** Do the selected config and statement actually succeed under the current RF/DC, node health, and workload?

For example: `application.conf` declares `basic.request.timeout = 2 seconds`; named profile `reporting` sets 8 seconds; the statement calls `setTimeout(Duration.ofSeconds(1))`. **This request uses a 1-second timeout**, not 2 or 8. Yet that does not guarantee the query finishes within 1 second or that the server stops work at that exact mark: timeout is a driver-side budget, while cancellation/write outcome must be understood separately.

### 2.1. Effective Values Do Not Guarantee Business Outcomes

| Confirmed Value | What It Proves | What It Does **Not** Prove |
|---|---|---|
| `REQUEST_CONSISTENCY=LOCAL_QUORUM` | The client requests this consistency level when unoverridden | Replicas hold identical data or all DCs are synchronized |
| `REQUEST_TIMEOUT=2s` | Client-side time limit placed on the request | Cassandra rolled back a timed-out write |
| `REQUEST_PAGE_SIZE=100` | Suggested page size per fetch | The query reads only 100 rows total |
| `REQUEST_DEFAULT_IDEMPOTENCE=false` | If undeclared on a statement, the driver treats it as non-idempotent | The mutation is actually non-idempotent at the business level |
| `local-datacenter=dc1` | Driver recognizes local DC for routing/policy | dc1 servers are healthy or already hold the data |

Thus "reading effective config" differs from "measuring p99/errors" and "reconciling data": all three are needed when evaluating production.

## 3. Components in Java Driver 4.x Configuration

### 3.1. Configuration Tree

Java Driver 4.x uses **Typesafe Config / HOCON** with default root `datastax-java-driver`:

~~~hocon
datastax-java-driver {
  basic {
    session-name = "order-api"

    contact-points = [ "127.0.0.1:9042" ]

    load-balancing-policy {
      local-datacenter = "datacenter1"
    }

    request {
      timeout = 2 seconds
      consistency = LOCAL_ONE
      serial-consistency = SERIAL
      page-size = 5000
      default-idempotence = false
    }
  }

  profiles {
    point_read {
      basic.request.timeout = 500 milliseconds
      basic.request.page-size = 50
    }
  }
}
~~~

This is a **sample configuration** illustrating the 4.x API, not a recommendation to use `LOCAL_ONE` and a 500 ms timeout everywhere. Contact points and `local-datacenter` in this snippet only match a lab if the node truly belongs to DC `datacenter1`; replace with real hostnames/IPs/DC in production.

### 3.2. Role of Each Component

| Component | Role | Commonly Mistaken For |
|---|---|---|
| `reference.conf` | Default configuration bundled inside the driver JAR and dependencies | "A file to edit directly" — **do not** |
| `application.conf` | Application-level overrides on the classpath | "Automatically beats all other sources" — **false** |
| JVM system properties | Quick overrides via `-Ddatastax-java-driver...` | "Arbitrary OS env vars auto-map here" — **false** |
| `DriverConfigLoader` | Selects sources, merges, and optionally reloads config | A single immutable profile or config object |
| `DriverConfig` | API for inspecting resolved profiles | Full history of config files |
| Default profile | Fallback for requests without a named profile | A profile you must explicitly name `default` in the file |
| Named profile | Group of overrides for a request category | A separate `CqlSession`/independent connection pool |
| Derived profile | Selective copy of an existing profile | A profile to instantiate fresh on every request |
| Statement attributes | Overrides for a single request | Changing global config for other requests |

**One `CqlSession` is normally reused**, is thread-safe, and manages connection resources. Never create a new session per execution profile or per request.

### 3.3. HOCON: Dot Syntax and Nested Syntax

These two snippets define the exact same key:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds
}
~~~

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
    }
  }
}
~~~

`2 seconds` is a duration, not a unitless string `"2"`; `page-size=100` is an integer; `consistency=LOCAL_QUORUM` is parsed by the driver. HOCON allows `#`/`//` comments and substitutions, so always inspect the **final resolved value** rather than guessing from raw text.

## 4. Precedence Order of Config Sources

With Java Driver 4.17's default loader, sources merge in **highest-to-lowest precedence order**:

| Order | Source | Example |
|---:|---|---|
| 1 | **System properties** | `-Ddatastax-java-driver.basic.request.timeout="4 seconds"` |
| 2 | **Programmatic overrides** when using `programmaticBuilder()` | `withDuration(REQUEST_TIMEOUT, 3s)` |
| 3 | `application.conf` on classpath | `basic.request.timeout = 2 seconds` |
| 4 | `application.json` on classpath | Equivalent option in JSON format |
| 5 | `application.properties` on classpath | Option in properties format |
| 6 | `reference.conf` | Driver defaults |

This order applies to loaders using **programmatic overrides with classpath fallback**. With `DriverConfigLoader.fromFile(file)`, the typical chain is **system properties → specified file → reference.conf**, without automatically merging every other `application.conf` on the classpath. A **custom loader** may merge differently; do not assume this order applies universally to every implementation.

### 4.1. Three-Source Conflict Example

Suppose:

~~~hocon
# application.conf
datastax-java-driver.basic.request.timeout = 2 seconds
~~~

~~~java
// Programmatic config loader
DriverConfigLoader loader = DriverConfigLoader.programmaticBuilder()
    .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                  Duration.ofSeconds(3))
    .build();
~~~

And the JVM runs with:

~~~bash
java -Ddatastax-java-driver.basic.request.timeout="4 seconds" \
     -jar order-service.jar
~~~

**The expected resolved timeout of the default profile is 4 seconds**, because the system property outranks programmatic and file config. Removing the system property leaves 3 seconds; removing the programmatic override leaves 2 seconds. You **cannot know** the effective value just by opening `application.conf`.

### 4.2. Sources That Commonly Mislead Operators

- **Environment variables:** The Java Driver does not by default map variables like `CASSANDRA_TIMEOUT` to `basic.request.timeout`. Frameworks like Spring/Micronaut/Quarkus, startup scripts, or custom loaders may map them; check the integration layer.
- **Multiple `application.conf` files:** Libraries or multiple resources with the same name may participate in merging; check the classpath/packaging if values look unexpected.
- **JVM flags inside containers:** Arguments injected via `JAVA_TOOL_OPTIONS`/startup scripts can set system properties invisible to someone only reading config files.
- **Files in the source tree:** Editing `src/main/resources/application.conf` on a dev laptop does not change a running JAR; deploy the new resource or point a loader to a writable external file.
- **Programmatic builder/session builder:** Choices like `withLocalDatacenter` or `addContactPoint` apply directly during session creation; do not infer from text configs alone what changed.

## 5. Default Profile and Named Execution Profiles

### 5.1. Per-Option Inheritance

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 500
    default-idempotence = false
  }

  profiles {
    point_read {
      basic.request.timeout = 400 milliseconds
      basic.request.page-size = 40
    }

    history_read {
      basic.request.timeout = 6 seconds
      basic.request.page-size = 200
    }
  }
}
~~~

| Option | Default | `point_read` effective | `history_read` effective |
|---|---|---|---|
| Timeout | 2 s | **400 ms** | **6 s** |
| Consistency | LOCAL_QUORUM | LOCAL_QUORUM (*inherited*) | LOCAL_QUORUM (*inherited*) |
| Page size | 500 | **40** | **200** |
| Default idempotence | false | false (*inherited*) | false (*inherited*) |

Each named profile **inherits from default** for any option it does not override. For example, `point_read` omits `consistency`, so its value comes from the **merged** default, not falling back to `LOCAL_ONE` in `reference.conf` when default is `LOCAL_QUORUM`.

### 5.2. Using Profiles to Express Policies per *Query Family*

| Query Family | Suggested Profile | Why? |
|---|---|---|
| `orders.getById` | `point_read` | Small partition lookup, tight latency budget |
| `orders.listRecent` | `history_read` | May page and needs dedicated timeout/page size |
| `orders.placeOrder` | `write_critical` | CL/timeout/idempotency per write contract |
| `schema.migrate` | `ddl` | DDL can be slower than OLTP, different timeout |
| `export.nightly` | `batch_read` | Caps total consumption and peak impact |

Profile names carry no automatic technical semantics: naming one `point_read` does not tell the driver the partition key or optimize an `ALLOW FILTERING` query. It only applies the declared options. Query shape, prepared statements, and token-aware routing must still be designed separately.

### 5.3. Do Not Treat Profiles as Security or Isolation Boundaries

- A named profile **does not create a new keyspace/role/tenant ACL**.
- It does not fully isolate `CqlSession`, disk, coordinators, or replica pools; some policies may share or separate instances depending on configuration.
- A profile with a long timeout cannot "bypass" CQL auth/network permissions.
- A profile with a small page size does not cap **total rows** if code keeps fetching pages.
- Using profiles with differing CLs requires business/data correctness review, not just a performance review.

## 6. Sample `application.conf` for a Java Application Connecting to Cassandra

### 6.1. Complete Lab Configuration

Place `src/main/resources/application.conf` on the Java/Maven/Gradle application's **classpath**:

~~~hocon
datastax-java-driver {
  basic {
    session-name = "cassandra-driver-lab"
    contact-points = [ "127.0.0.1:9042" ]

    load-balancing-policy {
      local-datacenter = "datacenter1"
    }

    config-reload-interval = 5 minutes

    request {
      timeout = 2 seconds
      consistency = LOCAL_ONE
      serial-consistency = SERIAL
      page-size = 500
      default-idempotence = false
    }
  }

  profiles {
    point_read {
      basic.request.timeout = 500 milliseconds
      basic.request.page-size = 25
      basic.request.default-idempotence = true
    }

    history_read {
      basic.request.timeout = 5 seconds
      basic.request.page-size = 100
      basic.request.default-idempotence = true
    }

    ddl {
      basic.request.timeout = 15 seconds
      basic.request.page-size = 500
    }
  }
}
~~~

**Scope of this sample:** a **single-node, RF=1** Cassandra lab, DC named `datacenter1`, read-only queries on `point_read` and `history_read`. For multi-DC production, **do not copy `LOCAL_ONE`**, localhost contact points, or `default-idempotence=true` to all statements without evaluating consistency contracts, mutation idempotence, and RF. Replace with the real DC name from `nodetool status`/topology inventory.

### 6.2. Moving Toward Production

Another template example:

~~~hocon
# Illustrative; hostnames and local DC must match actual topology.
datastax-java-driver {
  basic.contact-points = [
    "cassandra-1.dc1.example.internal:9042",
    "cassandra-2.dc1.example.internal:9042"
  ]

  basic.load-balancing-policy.local-datacenter = "dc1"
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
    page-size = 500
    default-idempotence = false
  }

  profiles {
    fast_read {
      basic.request.timeout = 800 milliseconds
      basic.request.page-size = 50
      basic.request.default-idempotence = true
    }

    report_read {
      basic.request.timeout = 8 seconds
      basic.request.page-size = 200
      basic.request.default-idempotence = true
    }
  }
}
~~~

The `800 ms`/`8 s` values are **illustrative** to distinguish SLOs, not Apache-recommended defaults for every system. If an app needs read-your-writes or specific guarantees, CL/partitioning/RF must be determined by the workload, not merely picking `LOCAL_QUORUM` because it "looks safe".

### 6.3. Local Datacenter Is Not a Per-Query Option

`local-datacenter` guides the driver's load balancing routing policy and must match **the target cluster's DC name**. Names like `dc1` or `datacenter1` are **topology labels**, not arbitrary aliases invented in config. When wrong:

- The session may fail to initialize or find no eligible local nodes.
- Routing may hit unintended coordinators.
- `LOCAL_QUORUM` is evaluated in the **coordinator's actual local DC**, not "cluster-wide".
- Apps deployed in dc2 yet configured with dc1 suffer higher network latency and misleading durability/consistency assumptions.

Inspect **node/DC visibility** and verify real connections. Driver config never alters `NetworkTopologyStrategy` or a keyspace's RF.

## 7. Statement-Level Overrides: Final Priority for a Single Request

Attributes that can be set directly on a statement include:

- `execution profile` (by name or derived profile object).
- `request timeout`.
- `normal consistency level`; serial consistency for LWT.
- `page size` and paging state.
- `idempotent flag`.
- `tracing`, routing information, or query timestamp when needed.

For overridable request settings, the rule is:

~~~text
Explicit statement option  >  selected execution profile option
                                      |
                     if profile does not override:
                                 default profile
                                      |
                         merged config sources
~~~

**Important:** "Statement uses `point_read`" does not mean the statement uses every option in `point_read`: if the developer calls `setTimeout` or `setPageSize` on it, those explicit options override the profile. Options not overridable at the statement level remain governed by config/policy.

### 7.1. Correct Example with SimpleStatement.Builder

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;

SimpleStatement statement = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("point_read")
    .setTimeout(Duration.ofSeconds(1))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setIdempotent(true)
    .build();
~~~

Assuming `point_read` has a 500 ms timeout and default CL `LOCAL_ONE`, this statement:

- Uses profile `point_read` for any unoverridden options.
- **Has an effective timeout of 1 second** because it is set on the statement.
- **Uses consistency `ONE`** because it is set explicitly; querying a system table in a lab is illustrative only and should not be copied as a business CL.
- Explicitly sets idempotence to `true`, ignoring the profile default.

### 7.2. 4.x Statements Are Immutable; Never Ignore the Return Value

**Wrong:**

~~~java
SimpleStatement s = SimpleStatement.newInstance(
    "SELECT release_version FROM system.local");

s.setExecutionProfileName("point_read");
s.setTimeout(Duration.ofSeconds(1));

// s is still the original object, not mutated in place.
// session.execute(s) will use default profile/timeout since s was not reassigned.
~~~

**Right:**

~~~java
SimpleStatement s = SimpleStatement.newInstance(
    "SELECT release_version FROM system.local");

s = s.setExecutionProfileName("point_read")
     .setTimeout(Duration.ofSeconds(1));

// session.execute(s) receives the new object carrying those attributes.
~~~

Built-in statement setters in Java Driver 4.x return **a new instance**. This is one of the most frequent reasons why "I called the setter, yet the driver still uses the old value".

### 7.3. PreparedStatement and BoundStatement Also Require Care

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.time.LocalDate;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, status FROM driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? LIMIT 50");

BoundStatement bound = prepared.bind(
    "tenant-a", LocalDate.parse("2026-11-21"));

bound = bound.setExecutionProfileName("history_read")
             .setPageSize(20);

// effective page-size=20 for this request,
// not history_read's page-size=100.
session.execute(bound);
~~~

`PreparedStatement` provides stable bind types and routing keys without blocking statement-level overrides. **Do not re-prepare the same query on every request or create a new session each time**; preparing on the hot path adds unnecessary overhead.

### 7.4. Combined Precedence Reference Table

Suppose `application.conf` contains:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 2 seconds
  basic.request.page-size = 500
  profiles {
    history_read {
      basic.request.timeout = 5 seconds
      basic.request.page-size = 100
    }
  }
}
~~~

| Java Call | Effective Timeout | Effective Page Size |
|---|---|---|
| `execute(SimpleStatement.newInstance(...))` | 2 s | 500 |
| `setExecutionProfileName("history_read")` | 5 s | 100 |
| `history_read` + `setTimeout(1s)` | **1 s** | 100 |
| `history_read` + `setPageSize(20)` | 5 s | **20** |
| `history_read` + both overrides | **1 s** | **20** |

If the JVM has `-Ddatastax-java-driver.basic.request.timeout="7 seconds"`, it changes the **default resolved timeout to 7 s**, yet `history_read` keeps its own 5 s override (unless a system property **specifically targets that named profile's path**). A statement setting 1 s still resolves to 1 s.

## 8. Reading `DriverConfig` and Effective Profile Values in Java

### 8.1. API for Inspecting Merged Configuration

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import java.time.Duration;

public final class DriverEffectiveConfig {
    private DriverEffectiveConfig() {}

    public static void print(CqlSession session) {
        DriverConfig config = session.getContext().getConfig();

        DriverExecutionProfile defaultProfile =
            config.getDefaultProfile();
        DriverExecutionProfile pointRead =
            config.getProfile("point_read");
        DriverExecutionProfile historyRead =
            config.getProfile("history_read");

        logProfile(defaultProfile);
        logProfile(pointRead);
        logProfile(historyRead);
    }

    private static void logProfile(DriverExecutionProfile profile) {
        Duration timeout = profile.getDuration(
            DefaultDriverOption.REQUEST_TIMEOUT);

        String cl = profile.getString(
            DefaultDriverOption.REQUEST_CONSISTENCY);

        String serialCl = profile.getString(
            DefaultDriverOption.REQUEST_SERIAL_CONSISTENCY);

        int pageSize = profile.getInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE);

        boolean defaultIdempotence = profile.getBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE);

        System.out.printf(
            "profile=%s timeout=%s CL=%s serialCL=%s " +
            "pageSize=%d defaultIdempotence=%s%n",
            profile.getName(),
            timeout, cl, serialCl, pageSize, defaultIdempotence);
    }
}
~~~

This is the **most reliable way to check resolved profile values in the live session**, instead of guessing from a single file. `DriverConfig.getProfile(name)` throws `IllegalArgumentException` if the profile does not exist; verify profile names at startup/in tests rather than waiting for production traffic to uncover a typo.

### 8.2. Reading `DriverExecutionProfile` Does Not Account for Statement Overrides

If `point_read` reports a 500 ms timeout while a statement sets `setTimeout(Duration.ofSeconds(1))`, `logProfile(pointRead)` still prints **500 ms**, because the profile object knows nothing about per-request overrides.

To determine a statement's effective timeout:

1. Identify **which profile** the statement selects (default/named/derived).
2. Read the statement's explicit attribute, e.g., `getTimeout()`; `null` means inherit in the Request API.
3. If no override is present, read `profile.getDuration(REQUEST_TIMEOUT)`.
4. If an override is present, use the **statement value**.

Pseudocode:

~~~text
effective_timeout(request):
    if request.getTimeout() != null:
        return request.getTimeout()
    else:
        return selected_profile.getDuration(REQUEST_TIMEOUT)
~~~

This is a mental model for **request timeout**, not a full replacement for driver internals covering retries, timer ticks, first-page/next-page fetches, custom policies, or connection errors. For CL/page/idempotence, apply the corresponding inheritance rules and option semantics.

### 8.3. Querying Config Beyond Debug Printing

Typed getters can be used to:

- Enforce **SLO policies** at startup: ensure `point_read` does not exceed an approved timeout ceiling.
- Guard against CL accidentally dropping to `ONE` after a deploy.
- Compare config **before and after reload** on a canary.
- Record version/hash of config sources without exposing passwords.
- Expose a self-diagnostic endpoint returning **only allowlisted non-secret settings** to operators.

Never serialize the entire `DriverConfig`, contact points, credentials, or truststore passwords to logs or public debug endpoints. Resolved values can still contain secrets.

## 9. `DriverConfigLoader`: Loading from File, Classpath, or Java

### 9.1. Default: Searching for `application.conf` on the Classpath

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

// When application.conf provides valid contact-points and local-datacenter,
// the default loader reads configuration from the classpath.
try (CqlSession session = CqlSession.builder().build()) {
    DriverEffectiveConfig.print(session);
}
~~~

In Maven projects, place `application.conf` under `src/main/resources/`; after building, verify it is actually present in the runtime classpath/JAR. With Spring Boot or frameworks providing their own Cassandra settings, distinguish `spring.cassandra.*` or framework configs from `datastax-java-driver.*`: do not assume one automatically syncs into the other.

### 9.2. Selecting an External File Outside the Classpath

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.io.File;

File configFile = new File("/etc/order-api/cassandra-driver.conf");

try (CqlSession session = CqlSession.builder()
        .withConfigLoader(DriverConfigLoader.fromFile(configFile))
        .build()) {
    DriverEffectiveConfig.print(session);
}
~~~

With `fromFile`, precedence is **system properties → specified file → reference.conf**. This is useful when config is mounted as an external file; ensure read permissions, atomic file replacement on updates, and version/checksum tracking. Do not expect the loader to also merge `application.conf` inside the JAR once `fromFile` is chosen.

### 9.3. Other Factory Methods

| API | Meaning | Notes |
|---|---|---|
| `DriverConfigLoader.fromClasspath("mydriver")` | Reads `mydriver.conf`/`mydriver.json`/`mydriver.properties` on classpath | Do not confuse resource prefix with root `datastax-java-driver` |
| `DriverConfigLoader.fromFile(file)` | Reads an external file outside classpath | File must exist/be readable on the JVM host |
| `DriverConfigLoader.fromPath(path)` | Same, using `java.nio.file.Path` | Verify reloader behavior for the binary |
| `DriverConfigLoader.fromUrl(url)` | Reads from a URL | Manage trust/network/failure caching separately |
| `DriverConfigLoader.fromString(contents)` | Reads a HOCON string | **Does not support runtime reload** in API 4.17 |
| `DriverConfigLoader.programmaticBuilder()` | Java overrides with config fallback | System properties can still win |
| `DriverConfigLoader.fromMap(options)` | Config from an in-memory options map | Check version/API for reload semantics |

Never pass URLs containing credentials or log full HOCON configs containing secrets. Never edit `reference.conf` inside the driver JAR to change defaults; keep application overrides in a managed source.

### 9.4. Programmatic Config Loader with Named Profiles

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.net.InetSocketAddress;
import java.time.Duration;

DriverConfigLoader loader = DriverConfigLoader.programmaticBuilder()
    .withDuration(
        DefaultDriverOption.REQUEST_TIMEOUT,
        Duration.ofSeconds(2))
    .withString(
        DefaultDriverOption.REQUEST_CONSISTENCY,
        "LOCAL_ONE")
    .withInt(
        DefaultDriverOption.REQUEST_PAGE_SIZE,
        500)
    .startProfile("point_read")
        .withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofMillis(500))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            25)
        .withBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE,
            true)
    .endProfile()
    .startProfile("history_read")
        .withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofSeconds(5))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            100)
        .withBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE,
            true)
    .endProfile()
    .build();

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .withConfigLoader(loader)
        .build()) {
    DriverEffectiveConfig.print(session);
}
~~~

**Explanation:**

- `withDuration`/`withInt`/`withString`/`withBoolean` are **typed options**, avoiding arbitrary string coercion.
- `startProfile` scopes subsequent options to a **named profile**; `endProfile` returns to the default scope.
- `withLocalDatacenter` and `addContactPoint` apply on the session builder, useful when addresses come from service discovery or deployment config.
- This is an **alternative** to HOCON; avoid mixing two divergent declarations without tracking precedence: programmatic overrides sit above `application.conf` but below system properties.
- `LOCAL_ONE`/lab DC and 500 ms values are for learning; production often needs `LOCAL_QUORUM` with matching RF.

### 9.5. Checking Conflicts Between Files and Programmatic Config

If `application.conf` declares `point_read` timeout 800 ms while programmatic config sets `point_read` to 500 ms, the effective profile uses 500 ms, **unless a system property overrides that exact option/path**. Reading only the file and assuming 800 ms means looking at **declared config** rather than runtime resolved config.

## 10. Hot Reload: Editing a File Does Not Mean Every Option Updates Immediately

### 10.1. How Does Reload Work?

Java Driver 4.17's default Typesafe Config loader supports periodic reload:

~~~hocon
datastax-java-driver {
  basic.config-reload-interval = 5 minutes
}
~~~

Setting interval `0` disables periodic reload. When the file changes and the loader reloads successfully, the driver updates **options marked as runtime-modifiable**. Changes such as protocol version, certain policies, or connection pool structure cannot be hot-applied just by editing HOCON; some require building a new session or redeploying.

~~~text
T0: session initializes, config C0
    |
    v
T1: operator changes config file C0 -> C1
    |
    +-- File packaged inside read-only JAR?
    |       -> No real change in runtime resource
    |
    +-- External file and loader supports reload?
            |
            v
       Reload interval / manual reload
            |
     +------+------+
     |             |
   MODIFIABLE   NON-MODIFIABLE
     |             |
 New requests    Usually needs
 use C1          session rebuild/redeploy
~~~

### 10.2. Manual Reload from Java

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.util.concurrent.CompletionStage;

public final class ConfigReloader {
    private ConfigReloader() {}

    public static CompletionStage<Boolean> reload(CqlSession session) {
        DriverConfigLoader loader =
            session.getContext().getConfigLoader();

        if (!loader.supportsReloading()) {
            throw new IllegalStateException(
                "Configured loader does not support manual reload");
        }

        // Boolean = configuration actually changed on reload,
        // not "every configured component has been reinitialized".
        return loader.reload();
    }
}
~~~

Invoking from an operational flow:

~~~java
ConfigReloader.reload(session).whenComplete((changed, error) -> {
    if (error != null) {
        System.err.println("Config reload failed: " + error);
    } else {
        System.out.println("Driver config changed=" + changed);
        DriverEffectiveConfig.print(session);
    }
});
~~~

Check `supportsReloading()` because custom loaders and `fromString` may not support it. `reload()` returns `CompletionStage<Boolean>`; `true` indicates config **changed**, **not** that all resources, connections, and policies were recreated. Confirm an option took effect by **re-reading typed getters + checking option docs + measuring new requests**.

### 10.3. Changing a Reloadable Option

Per reference.conf 4.17:

| Option | Runtime-Modifiable? | Overridable in Profile? | How to Verify |
|---|---|---|---|
| `basic.request.timeout` | Yes, for **new requests** | Yes | `REQUEST_TIMEOUT` |
| `basic.request.consistency` | Yes | Yes | `REQUEST_CONSISTENCY` |
| `basic.request.serial-consistency` | Yes | Yes | `REQUEST_SERIAL_CONSISTENCY` |
| `basic.request.page-size` | Yes | Yes | `REQUEST_PAGE_SIZE` |
| `basic.request.default-idempotence` | Yes | Yes | `REQUEST_DEFAULT_IDEMPOTENCE` |
| `basic.config-reload-interval` | Reload behavior per loader | **No** | Read loader/config option and test reload |
| `basic.load-balancing-policy.class` | **No** default class reload | Configurable per profile, policy-dependent | Usually requires session rebuild |
| `advanced.netty.timer.tick-duration` | **No** | **No** | Fixed at JVM/session init |

Never infer from `advanced.*` that every option is non-reloadable, or from `basic.*` that every option is reloadable. **Reference configuration documents each option explicitly** with both properties: modifiable at runtime and overridable in a profile.

### 10.4. Named Profiles and Reload

If `history_read` has a 5 s timeout and an operator edits an external file to 6 s, **new** requests using that profile observe 6 s **after reload succeeds**, provided no system/statement override exists and the option supports runtime modification.

However:

- Requests **already sent before reload** are not guaranteed to alter deadlines mid-flight.
- Statements calling `setTimeout(1s)` **remain at 1 s**.
- If a system property sets `datastax-java-driver.profiles.history_read.basic.request.timeout` to 4 s, editing the file 5→6 s **remains shadowed by 4 s**.
- Application config inside a read-only JAR **never changes** when you edit source code; deploy the new resource.
- Derived profiles from a base may reflect reloads per reference semantics, but should be cached and tested on your exact version.

### 10.5. Rollback Conditions After Reload

A change record should capture:

~~~text
Change ID: DRIVER-PROFILE-ROLL-001
Scope: order-api / dc1 / 1 canary instance
Profile: history_read
Option: basic.request.timeout
Effective before: 5 seconds
Proposed: 6 seconds
Trigger: timeout rate, p99, pool in-flight, retry amplification
Rollback: restore external config value 5 seconds
Verify: reload success + typed getter + new-request metrics
~~~

If raising the timeout merely lets clients wait longer while the server remains overloaded, do not call that "fixing latency". Rollback decisions must track **user-visible error budgets**, physical attempts, and Cassandra resources—not only confirming the effective value reverted to C0.

## 11. Five Request Options to Understand Before Deploying Profiles to Production

### 11.1. `basic.request.consistency`: A Replica Requirement, Not a Performance Switch

Every CQL read/write has a consistency level (CL), governing coordinator response criteria. Example with `NetworkTopologyStrategy` in `dc1` at RF=3:

| CL | General Response Condition | Trade-Off |
|---|---|---|
| `ONE` | One replica responds | Lower latency/higher availability; weaker consistency |
| `LOCAL_ONE` | One replica in local DC | Avoids forcing remote DC for local requests |
| `LOCAL_QUORUM` | Quorum of full replicas in **local DC** (RF=3 typically needs 2) | Higher latency than ONE, but quorum guarantees |
| `QUORUM` | Quorum across the keyspace's applicable replicas | May span multiple DCs depending on RF/topology |
| `ALL` | Responses from all full replicas per CL semantics | Harder to maintain availability when any replica degrades |

`LOCAL_QUORUM` at RF=3 needs **two** local-DC responses for standard operations. A `fast_read` profile setting `ONE` must never be used solely to shave p99 if the business contract requires `LOCAL_QUORUM`. CL also does not replace repair or replica consistency checks.

Config example:

~~~hocon
datastax-java-driver {
  basic.request.consistency = LOCAL_QUORUM
  profiles {
    payments {
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

**Do not confuse CL with replication factor.** RF is defined on the keyspace; CL is a per-**request** requirement. Editing a Java Driver config file **never** creates extra data replicas; changing RF on existing data requires repair/rebuild/streaming per Cassandra runbooks.

### 11.2. `basic.request.serial-consistency`: For LWT/Paxos

Serial consistency level applies to conditional mutations using `IF ...` (LWT). Values such as `SERIAL` or `LOCAL_SERIAL` govern the Paxos/serial consensus phase; this is **distinct from** the normal CL used for the mutation phase.

~~~sql
-- LAB CQL showing a conditional write.
INSERT INTO driver_lab.orders_by_id (
    tenant_id, order_id, status
) VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW'
) IF NOT EXISTS;
~~~

If the application does not use LWT, changing serial consistency in a profile **will not speed up point SELECTs**. For LWT, configure **both normal CL and serial CL** according to desired DC/consistency scope; do not default to `LOCAL_SERIAL` as a "half-cost shortcut". Watch for cases where drivers/frameworks override these two options per statement.

### 11.3. `basic.request.timeout`: A Client Deadline, Not a Server Rollback

Java Driver 4.x treats `REQUEST_TIMEOUT` as the **budget for a single request**, including retries/speculative attempts within that request. A timed-out `session.execute(stmt)` does not prove Cassandra failed to apply the mutation; replicas may have written it while the ACK never reached the client.

~~~text
Client                    Coordinator / replicas
   |                               |
   |--- CQL mutation -------------->|
   |                               | writes commit log/memtable
   |              (slow/lost ACK)  |
   |-- timeout after 2 seconds ----X
   |
Client cannot know for sure whether the write applied.
Retries must respect idempotency and source of truth.
~~~

Example:

~~~java
SimpleStatement request = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("point_read")
    .setTimeout(Duration.ofMillis(800))
    .build();
~~~

The 800 ms timeout **overrides** the profile's 500 ms. Never set a 20 ms timeout expecting exact millisecond enforcement: the driver relies on timer resolution/ticks and faces network, GC, and queuing jitter; reference config also warns timeouts must align with `advanced.netty.timer.tick-duration`.

**Paging nuance:** When iterating a multi-page `ResultSet`, each subsequent page fetch can be its own request with its own timeout budget. The first request's `REQUEST_TIMEOUT` does not automatically become an absolute deadline for an **entire API workflow** reading 100 pages. APIs also need an **end-to-end deadline**, max rows/pages, and cancellation/backpressure.

### 11.4. `basic.request.page-size`: Page Size, Not LIMIT

~~~java
SimpleStatement pageRequest = SimpleStatement.builder(
        "SELECT event_time, event_id, status " +
        "FROM driver_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND day = ?")
    .addPositionalValues("tenant-a",
                         java.time.LocalDate.parse("2026-11-21"))
    .setExecutionProfileName("history_read")
    .setPageSize(20)
    .build();
~~~

`setPageSize(20)` tells the driver to request **roughly 20 rows per page**, not to cap total results at 20. Iterating `ResultSet` automatically fetches further pages. With the async API, the application manages fetch-next-page; avoid loading entire datasets into client memory. Excessively large page sizes bloat payloads/network/client heap; excessively small ones trigger too many round trips.

Compare:

~~~sql
-- LIMIT caps total query rows under CQL semantics.
SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
LIMIT 50;
~~~

`LIMIT 50` differs from `page-size=20`: a `LIMIT 50` query may still arrive across multiple small pages. Wide partitions or heavy tombstones can still scan many cells to locate 50 live rows. **Never use page size as a substitute for partition key design or API bounds.**

Zero/negative values may be treated by the driver as disabling paging per reference docs for certain options; never rely on that when scanning large tables or you risk memory/response spikes.

### 11.5. `basic.request.default-idempotence`: Prerequisite for Retry/Speculation

A request is idempotent when **repeating the same operation leaves the final state unchanged** under operation and business semantics. The driver needs this signal to decide whether retries or speculative executions are safe in specific failure modes.

| Request | Potentially Idempotent? | What to Verify |
|---|---|---|
| Point SELECT | Usually yes | No external side effects |
| INSERT upsert with same PK and values | Conditionally | Timestamps/TTL/data source and concurrency |
| UPDATE with literal values | Conditionally | Timestamps, write conflicts, TTL |
| Counter UPDATE `counter = counter + 1` | **No** | Repeating increments multiple times |
| Conditional write `IF NOT EXISTS` | Do not assume retries are harmless | `[applied]`, contention, business outcome |
| Writing a fresh UUID on every attempt | **No** | Retries create duplicate rows |
| DELETE single row | Conditionally | Tombstone timestamp, retention, event order |

Reference config 4.17 defaults to `default-idempotence=false`. Setting `true` inside a **SELECT-only profile** can make sense. Never set `basic.request.default-idempotence=true` across a mixed read/write service just to enable more speculative retries.

~~~java
// Explicit statement-level decision after verifying business semantics.
SimpleStatement s = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setIdempotent(true)
    .build();
~~~

**The driver flag does not make a non-idempotent operation idempotent**. If retrying after a timeout generates new client timestamps/UUIDs, correctness must be engineered in the application, not toggled with a boolean config flag.

### 11.6. Request Profiles and Cluster Health

A profile with `LOCAL_QUORUM`, a 3 s timeout, and page-size 100 **does not guarantee** slow queries vanish:

- Nodes suffer disk/GC overload, preventing coordinators from collecting replicas in time.
- Partition keys create hotspots, or range scans hit many SSTables/tombstones.
- Datacenters lack sufficient replication or a replica is `DOWN`.
- Java Driver pools have excessive in-flight requests, or retries amplify load.
- A query fetches many pages, inflating end-to-end API latency.

Combine **config introspection** with JMX `ClientRequest`/`Table`, `nodetool status`/`tpstats`, Java driver metrics, and per-query-family analysis.

## 12. Designing Execution Profiles by SLO and Workload Type

### 12.1. Separating OLTP, History, and DDL

An ordering service commonly has:

~~~text
REST GET /orders/{id}
   -> point_read
   -> partition key lookup
   -> small response, strict p99 SLO

REST GET /orders/history
   -> history_read
   -> multi-row clustering range read with paging
   -> bounded pages/results, longer timeout

Migration / CREATE TABLE
   -> ddl
   -> infrequent, longer timeout for schema agreement
~~~

Why profiles beat scattered `if/else` logic:

- One place clearly declares timeout/CL/page/idempotence per request class.
- Easy to inspect effective options and compare before/after deploys.
- Prevents a method tuning its timeout from accidentally leaking into other query types.
- Supports canarying one profile without altering all queries.
- Unit/integration tests can assert repositories select the right profile name.

### 12.2. Illustrative Policy Matrix

| Profile | Assumed Timeout | Assumed CL | Page Size | Default Idempotence | Policy |
|---|---:|---|---:|---|---|
| `point_read` | 500 ms | LOCAL_QUORUM | 25 | true | Audited point SELECTs only |
| `history_read` | 5 s | LOCAL_QUORUM | 100 | true | Paged partition/range reads |
| `write_critical` | 3 s | LOCAL_QUORUM | 500 | false | Mutations requiring explicit idempotency |
| `ddl` | 15 s | LOCAL_QUORUM | 500 | false | Dedicated schema ops, never mixed with APIs |

These numbers are **not driver defaults** or universal cluster recommendations. With RF3 in one DC, `LOCAL_QUORUM` typically needs 2 replicas. In an RF1 lab, configs can use `LOCAL_ONE`/`ONE` for learning; never change CL between benchmark runs and claim the new profile is "faster".

### 12.3. A Profile Is Not Enough If a Request Fetches Many Pages

Suppose a history endpoint returns 100 rows per page, and a caller requests 10,000 rows:

~~~text
history_read.page-size = 100
Pages to fetch ≈ 100 (ignoring dataset/filter nuances)
Each page incurs its own latency.
Total API time can exceed 5 seconds even when each page is <5 seconds.
~~~

Proper solutions include **cursor/paging APIs**, capping maximum rows/pages, time-bucketed queries, appropriate caching, or data model redesign. **Never** just bump `history_read.timeout` to 60 seconds to hide reading too much data.

### 12.4. Never Share One Profile Across Incompatible Semantics

A single `fast` profile used for SELECT, INSERT, LWT, and bulk export gets pulled in conflicting directions: low timeouts break schema mutations, `idempotence=true` breaks counters, CL mismatches business rules, and huge page sizes hurt exports. Group by **genuinely shared policy**, not merely REST endpoint path or owning team.

## 13. CQL Lab — Creating Workloads to Test Profiles

**Lab goal:** Two query families on a table with a composite partition key, invoked from Java via `point_read` and `history_read`. This lab tests **config selection behavior**, not Cassandra benchmarking or CL performance comparisons.

**Environment:** A running Cassandra 4.1/5.0 node; `cqlsh`, Java 17, compatible Java Driver 4.x, and permissions to create keyspaces/tables. `SimpleStrategy` and RF1 are for lab use only; multi-DC production requires `NetworkTopologyStrategy` and appropriate RF.

### Step 1 — Verify the Real DC Name

~~~bash
# Read-only; does not modify data:
nodetool status
nodetool describecluster
~~~

If `nodetool status` reports DC as `dc1` instead of `datacenter1`, update `application.conf` or `withLocalDatacenter` to match. **Never assume a DC name** and expect the driver to guess correctly.

### Step 2 — Create Keyspace and Tables

~~~sql
CREATE KEYSPACE IF NOT EXISTS driver_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS driver_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS driver_lab.orders_by_id (
    tenant_id text,
    order_id uuid,
    status text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Explanation:

- `events_by_tenant_day` has partition key `(tenant_id, day)` and clustering key `(event_time, event_id)`, suited for daily history queries.
- `orders_by_id` uses key `(tenant_id), order_id`; in production, very large tenants may require revisiting this partition model.
- `status` is a regular column and does not allow efficient cluster-wide filtering.
- Execution profiles **cannot turn a CQL query missing its partition key** into a good query; data modeling remains a separate step.

### Step 3 — Insert Deterministic Sample Data

~~~sql
CONSISTENCY ONE;

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 'created'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222,
  'PAID', 'payment accepted'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333,
  'SHIPPED', 'out for delivery'
);

INSERT INTO driver_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, payload)
VALUES (
  'tenant-b', '2026-11-21', '2026-11-21T09:00:00Z',
  44444444-4444-4444-4444-444444444444,
  'NEW', 'created'
);

INSERT INTO driver_lab.orders_by_id
  (tenant_id, order_id, status)
VALUES (
  'tenant-a', 11111111-1111-1111-1111-111111111111, 'NEW'
);
~~~

The lab uses `CONSISTENCY ONE` to match RF1. For RF3 production, never apply `ONE` just because lab commands run fast.

### Step 4 — Verify Queries by Partition Key

~~~sql
SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status
FROM driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:05:00Z'
  AND event_id = 22222222-2222-2222-2222-222222222222;
~~~

Expect the first query to return three rows (ordered by `event_time DESC`), and the second to return `PAID`. With only a few rows, toggling `page-size=25` vs. `page-size=100` **shows no visible performance difference** because the result set is tiny; the goal is verifying profile selection and effective values.

## 14. Java Lab — Printing Profiles, Executing CQL, and Testing Statement Overrides

### 14.1. Application Structure

~~~text
driver-profile-lab/
  src/main/java/example/DriverProfileLab.java
  src/main/resources/application.conf
  pom.xml or build.gradle (configured per project)
~~~

Dependencies require Java Driver core 4.x compatible with your running Cassandra plus a matching logger binding. This lesson provides **source content only**, without generating project files or running Maven/Gradle. For Java Driver 4.18+ (ASF), Maven coordinates differ from 4.17; check docs for your selected version before building.

Use the **lab `application.conf` from Section 6.1**. If an app framework already configures Cassandra via its own bean/config, use only one verified integration mechanism so you do not spawn two `CqlSession`s targeting different DCs.

### 14.2. Complete Application

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DriverProfileLab {
    private DriverProfileLab() {}

    public static void main(String[] args) {
        // application.conf supplies real contact-points and local-datacenter.
        try (CqlSession session = CqlSession.builder().build()) {
            DriverConfig config = session.getContext().getConfig();
            DriverExecutionProfile defaults =
                config.getDefaultProfile();
            DriverExecutionProfile point =
                config.getProfile("point_read");
            DriverExecutionProfile history =
                config.getProfile("history_read");

            print("default", defaults);
            print("point_read", point);
            print("history_read", history);

            // Point lookup: explicitly select point_read profile.
            PreparedStatement getOne = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM driver_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ? " +
                "AND event_time = ? AND event_id = ?");

            BoundStatement one = getOne.bind(
                "tenant-a",
                LocalDate.parse("2026-11-21"),
                Instant.parse("2026-11-21T08:05:00Z"),
                UUID.fromString(
                    "22222222-2222-2222-2222-222222222222"))
                .setExecutionProfileName("point_read");

            Row row = session.execute(one).one();
            System.out.println("point status=" +
                (row == null ? "(missing)" : row.getString("status")));

            // Partition read with paging: history_read profile.
            PreparedStatement list = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM driver_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ?");

            BoundStatement listStatement = list.bind(
                "tenant-a", LocalDate.parse("2026-11-21"))
                .setExecutionProfileName("history_read");

            ResultSet result = session.execute(listStatement);
            int rows = 0;
            for (Row next : result) {
                rows++;
                System.out.println("history=" +
                    next.getInstant("event_time") + " " +
                    next.getString("status"));
            }
            System.out.println("history rows=" + rows);

            // Request uses history profile, but timeout and page-size
            // are explicitly overridden.
            SimpleStatement overridden = SimpleStatement.builder(
                    "SELECT event_time, status " +
                    "FROM driver_lab.events_by_tenant_day " +
                    "WHERE tenant_id = ? AND day = ?")
                .addPositionalValues(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setExecutionProfileName("history_read")
                .setTimeout(Duration.ofSeconds(1))
                .setPageSize(2)
                .build();

            System.out.println("explicit timeout=" +
                overridden.getTimeout());
            System.out.println("explicit pageSize=" +
                overridden.getPageSize());

            int overriddenRows = 0;
            for (Row next : session.execute(overridden)) {
                overriddenRows++;
            }
            System.out.println("override rows=" + overriddenRows);
        }
    }

    private static void print(
            String label, DriverExecutionProfile profile) {
        System.out.printf(
            "%s: name=%s timeout=%s consistency=%s " +
            "pageSize=%d idempotentDefault=%s%n",
            label,
            profile.getName(),
            profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT),
            profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY),
            profile.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE),
            profile.getBoolean(
                DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE));
    }
}
~~~

**What to observe:**

1. `session.getContext().getConfig()` returns **merged profiles** from HOCON.
2. `getProfile("point_read")` and `getProfile("history_read")` expose typed named profiles.
3. `getOne.bind(...).setExecutionProfileName(...)` selects a named profile without creating a new session.
4. `SimpleStatement.Builder` sets timeout=1s and page-size=2; those explicit values beat `history_read`.
5. `getTimeout()`/`getPageSize()` read **statement attributes**, not "actual elapsed execution time".
6. `for (Row ... : result)` transparently fetches subsequent pages. With 3 rows and page-size 2, all three rows are still read, not stopped at two.

### 14.3. Expected Output (Illustrative, Not Latency Measurement)

~~~text
default: name=default timeout=PT2S consistency=LOCAL_ONE pageSize=500 idempotentDefault=false
point_read: name=point_read timeout=PT0.5S consistency=LOCAL_ONE pageSize=25 idempotentDefault=true
history_read: name=history_read timeout=PT5S consistency=LOCAL_ONE pageSize=100 idempotentDefault=true
point status=PAID
history=2026-11-21T08:10:00Z SHIPPED
history=2026-11-21T08:05:00Z PAID
history=2026-11-21T08:00:00Z NEW
history rows=3
explicit timeout=PT1S
explicit pageSize=2
override rows=3
~~~

**Do not hardcode expected values if the environment passes system properties.** If the command line sets `-Ddatastax-java-driver.profiles.point_read.basic.request.timeout=...`, the output will differ. **Explain discrepancies via precedence** rather than blindly editing HOCON or deleting properties without knowing who manages them.

### 14.4. Record an Observation Table

| Request | Selected Profile | Profile Timeout | Statement Timeout | Expected Effective Timeout |
|---|---|---|---|---|
| `getOne` | point_read | 500 ms | null | 500 ms |
| `listStatement` | history_read | 5 s | null | 5 s |
| `overridden` | history_read | 5 s | 1 s | **1 s** |
| `SimpleStatement` with no profile/timeout | default | 2 s | null | 2 s |

Build the same table for page size and CL. This validates effective-value logic before testing **hot reload**.

## 15. Source Precedence Lab: Verifying a System Property

Goal: test the highest-precedence loader source **without editing YAML or Cassandra config**.

### Step 1 — Record Baseline

Run the lab program with Section 6's `application.conf`, note default/point/history timeouts, and confirm CQL queries succeed.

### Step 2 — Run JVM with Property Override

~~~bash
# Lab JVM example on Unix/Linux shell.
# -D arguments must appear before -jar.
java -Ddatastax-java-driver.basic.request.timeout="4 seconds" \
     -jar driver-profile-lab.jar
~~~

**What must happen** if the property reaches the JVM and no programmatic/custom loader shadows it:

- Default timeout shifts from 2 s → **4 s**.
- `point_read` stays **500 ms** because the profile overrides timeout itself.
- `history_read` stays **5 s** because the profile overrides timeout itself.
- Statement `overridden` stays **1 s**.

Do not treat this as a latency benchmark. It demonstrates **config source precedence and override scope**, not which deadline is better.

### Step 3 — Override a Specific Named Profile

~~~bash
java -Ddatastax-java-driver.profiles.history_read.basic.request.timeout="7 seconds" \
     -jar driver-profile-lab.jar
~~~

Expect `history_read` effective timeout to become **7 seconds**, since the system property targets the exact profile path. If the JVM only overrides `basic.request.timeout` on default, the 5 s override inside `history_read` still beats the inherited default.

### Step 4 — Unexpected Result?

Check sequentially:

1. Does the property have the exact **prefix, casing, and path**?
2. Was `-D` passed to the **exact JVM process**?
3. Does the app use the default loader, `fromFile`, programmatic, or a custom loader?
4. Does profile `history_read` actually exist and get selected by the statement?
5. Does the statement call an explicit `setTimeout`?
6. Is another framework config file merging in?
7. Does the logging endpoint print from the live config object or a stale cached file?

**Cleanup after lab:** Remove `-D` from the command line/entrypoint, restart the JVM with original config, and re-verify effective values. Never leave experimental system properties in production deployments.

## 16. Hot Reload Lab Using an External File Outside the JAR

**Goal:** Prove a runtime-modifiable option updates inside a profile after reload, while a statement with an explicit override keeps its own value. This lab requires a continuously running app or a test harness keeping `CqlSession` open, rather than a `main` that exits immediately.

### 16.1. Prepare a Mutable Config File

~~~text
/etc/driver-lab/driver.conf
  datastax-java-driver {
    basic.contact-points = [ "127.0.0.1:9042" ]
    basic.load-balancing-policy.local-datacenter = "datacenter1"
    basic.config-reload-interval = 0
    basic.request.timeout = 2 seconds
    basic.request.consistency = LOCAL_ONE
    profiles {
      history_read {
        basic.request.timeout = 5 seconds
        basic.request.page-size = 100
      }
    }
  }
~~~

`0` disables **periodic reload** so the test controls **manual reload** deterministically. The HOCON above is the lab file content, not driver output. Replace `datacenter1` with your actual DC; avoid creating/modifying test files in production.

### 16.2. Initialize Session from File

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.io.File;

DriverConfigLoader loader = DriverConfigLoader.fromFile(
    new File("/etc/driver-lab/driver.conf"));

CqlSession session = CqlSession.builder()
    .withConfigLoader(loader)
    .build();

// Keep session open throughout the experiment;
// call session.close() or use try-with-resources at the end.
~~~

### 16.3. Edit the File and Trigger Reload

After creating the session, edit **just one line** on the lab host:

~~~diff
- basic.request.timeout = 5 seconds
+ basic.request.timeout = 6 seconds
~~~

Note this line is **inside `profiles.history_read`**, not default `basic.request.timeout`. Save atomically if automated. Then invoke:

~~~java
DriverConfigLoader activeLoader =
    session.getContext().getConfigLoader();

if (activeLoader.supportsReloading()) {
    boolean changed =
        activeLoader.reload().toCompletableFuture().join();

    System.out.println("reload changed=" + changed);
    System.out.println(
        session.getContext().getConfig()
            .getProfile("history_read")
            .getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
}
~~~

Expected after reload: `history_read` timeout changes from `PT5S` to `PT6S`. If `changed=false`, check file path, permissions, system property precedence, and whether the file actually changed. If reload throws an exception, **keep the previously verified state**, fix the config, and retry cleanly; do not continue rollout.

### 16.4. Statement-Level Override Still Wins

~~~java
SimpleStatement s = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("history_read")
    .setTimeout(Duration.ofSeconds(1))
    .build();

// Profile is 6s after reload, but request s uses 1s
// because s carries an explicit override.
session.execute(s);
~~~

### 16.5. Rollback and Verify

1. Restore `driver.conf` from 6 s back to 5 s.
2. Reload again via `supportsReloading()`/`reload()`.
3. Print `getProfile("history_read").getDuration(REQUEST_TIMEOUT)` and confirm it returns to 5 s.
4. Execute new requests, verify SLO/timeout/rate, and ensure automation will not re-apply 6 s on the next deploy.
5. Close the session on app shutdown without leaking JMX/driver resources.

**Key lesson:** "File edited" differs from "config reloaded" and from "statement override cleared". In production, never raise timeouts to mask disk/GC/replica bottlenecks without measurement.

## 17. Derived Profiles: Changing One Request Without Editing HOCON

### 17.1. Mechanism

Java Driver 4.x allows creating a **derived execution profile** from an existing profile via `withXxx` methods returning a **new object**:

~~~java
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.Duration;

DriverExecutionProfile base =
    session.getContext().getConfig().getProfile("history_read");

DriverExecutionProfile special =
    base.withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofSeconds(3))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE,
            20);

SimpleStatement query = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfile(special)
    .build();

session.execute(query);
~~~

Computed values:

- `special` uses a **3 s** timeout and page-size **20**.
- Remaining options still come from `base` and the default profile via inheritance.
- `session.getContext().getConfig().getProfile("history_read")` is **not mutated directly** when creating `special`.
- The statement takes the **`special` object**, needing no new name in `application.conf`.

### 17.2. When to Use a Derived Profile?

Suitable for **a special one-off use case** or small request group testing a policy in code. However:

- `withXxx` allocates a new object; do not create derived profiles **per request** when a cached instance suffices.
- The driver must maintain linkage when the base profile reloads; creating too many derived profiles adds overhead.
- If the requirement is stable and handles thousands of requests/s, a **pre-declared named profile** is usually simpler and easier to audit.
- A derived profile with a custom CL must still satisfy the business consistency contract—no exceptions just because it was built in Java.

### 17.3. Comparing Named, Derived, and Explicit Statement Settings

| Choice | Best Fit | Auditability/Observability | Example |
|---|---|---|---|
| Named profile | Policy for a stable query family | High, declared in HOCON/typed getters | `history_read` |
| Derived profile | Small code-level variation or experiment | Medium, requires tracing code path | `history_read` with 3s timeout and page 20 |
| Explicit request setting | Exceptional value for **one** request | Must inspect at statement site | `setTimeout(1s)` |
| Default profile | Requests without special needs | High, though easily abused for mixed workloads | CQL health check |

**Avoid "profile explosion":** Never name profiles after every tenant ID, UUID, or query value; profiles express policies for a **finite set of query classes**, not per-record tags.

## 18. Testing Config Without a Live Cassandra Cluster

Teams often want to verify HOCON/precedence in CI before opening connections. You can test the config loader at the **API** level, while testing `CqlSession`, routing, and real timeouts requires integration tests against a lab cluster.

### 18.1. Checking Default and Named Profiles

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import java.time.Duration;

public final class ConfigContractCheck {
    public static void main(String[] args) {
        DriverConfigLoader loader =
            DriverConfigLoader.fromClasspath("application");

        try {
            DriverConfig config = loader.getInitialConfig();
            DriverExecutionProfile point =
                config.getProfile("point_read");
            DriverExecutionProfile history =
                config.getProfile("history_read");

            Duration pointTimeout = point.getDuration(
                DefaultDriverOption.REQUEST_TIMEOUT);
            Duration historyTimeout = history.getDuration(
                DefaultDriverOption.REQUEST_TIMEOUT);

            if (!pointTimeout.equals(Duration.ofMillis(500))) {
                throw new AssertionError(
                    "point_read timeout differs: " + pointTimeout);
            }
            if (!historyTimeout.equals(Duration.ofSeconds(5))) {
                throw new AssertionError(
                    "history_read timeout differs: " + historyTimeout);
            }
            if (point.getInt(
                    DefaultDriverOption.REQUEST_PAGE_SIZE) != 25) {
                throw new AssertionError("point_read page-size changed");
            }
        } finally {
            loader.close();
        }
    }
}
~~~

This checks **initial config only**; it does not prove cluster readiness or what happens on file reload. If CI/JVM sets different system properties, adjust expectations or strip overrides cleanly in the test environment. Never alter production runtime parameters just to make a test pass.

### 18.2. Tests Requiring an Integration Cluster

| Test | Why Config-Only Testing Is Insufficient |
|---|---|
| Connecting to a DC | Requires real local DC and network/contact points |
| `LOCAL_QUORUM` with specific RF | Requires real replica topology and service health |
| Multi-page paging | Requires a result set larger than page size |
| LWT with serial CL | Requires real Paxos/contended mutations |
| Timeout/retry | Requires controlled latency/failure injection |
| Hot reload + post-reload requests | Must keep a live session and observe behavior |
| Token-aware routing | Requires prepared statements and real partition key/ring metadata |

Never run fault injection tests (killing nodes, throttling disks) on production just to verify a profile. Use a lab/staging cluster with representative topology and defined guardrails.

## 19. Diagnosing "I Configured It, Yet the Driver Uses Something Else"

### 19.1. Scenario Table and Root-Cause Verification

| Symptom | Common Cause | Correct Check |
|---|---|---|
| File specifies 1 s timeout, profile prints 2 s | File not on runtime classpath or shadowed by `-D` | Print `DriverConfig`; inspect JAR/classpath/JVM args |
| Profile name not found | Undeclared, typo/casing, loader reading another file | `config.getProfiles()` and `getProfile(name)` |
| Profile prints 500 ms, yet CQL times out at 2 s | Statement did not select profile or has explicit override | Check `setExecutionProfileName`/`getTimeout()` |
| Called `setTimeout()`, nothing changed | 4.x statements are immutable; return value discarded | Reassign or use builder |
| Named profile timeout 5 s, file default timeout 2 s | **Expected** inheritance: named override | Print both default and named values |
| Named profile changed without editing source | JVM system property, another config on classpath, reload | Log effective config source and startup args |
| Edited file after deploy, app unchanged | Resource inside JAR, reload disabled, custom loader | Verify active file, `supportsReloading()`, and restart |
| Reload returns `changed=true`, routing unchanged | Option/policy not runtime-modifiable | Read option reference; rebuild session if required |
| Java service throws `NoNodeAvailable` / init fails | Wrong DC/contact points, TLS/auth, cluster down | Check `local-datacenter`, networking/driver logs |
| `LOCAL_QUORUM` times out with RF3 and 2 replicas DOWN | Insufficient quorum, not a config merge bug | `nodetool status`, per-DC RF, coordinator logs |
| `page-size=20` yet API reads 500 rows | Page size **is not LIMIT** | Count pages/rows and check iterator/fetch loop |
| p99 stays bad despite raising timeout from 2 s to 10 s | Driver just waits longer | Measure queues, disk/GC, replicas, p95/p99, error budget |
| Timeout stays 1 s after profile reloads to 6 s | Statement has explicit 1 s | Check `Request.getTimeout`/`setTimeout` |
| LWT unchanged after editing SELECT profile's serial CL | Serial CL applies only to conditional requests | Check CQL `IF` and the mutation's actual profile |
| No retries despite `default-idempotence=true` | Policy does not retry this error or statement explicitly sets false | Check retry policy, error class, request flag |
| Driver 3.x sample fails to compile on 4.x | API/classes/setter semantics changed | Match docs and dependencies to the **same major** |

### 19.2. Effective Value Investigation Flow

~~~text
You expect request to use X, but it behaves like Y?
                    |
             Is session alive?
             /             \
           NO               YES
           |                 |
      Debug startup       getContext().getConfig()
      DC/auth/port                |
                         List all profiles
                                |
                       Named profile exists?
                         /             \
                        NO             YES
                        |               |
                    Fix name       Print typed values
                                        |
                               Matches expected?
                                /            \
                              NO              YES
                              |                |
                       Check precedence   Check statement:
                       -D / program /     profile name?
                       file / reference   explicit setter?
                                             |
                                           Verify
                                      timeout/CL/page
                                             |
                                      Request metrics
                                             |
                                     Cassandra health
~~~

### 19.3. Reading Error Logs Without Leaking Data

In development environments, enable driver/Typesafe config logging via your logging framework to inspect file loading, profile warnings, and failures. However:

- **Never** log raw CQL bind values or passwords unnecessarily.
- Restrict log access; authentication/truststore/config file paths are also sensitive.
- Emit markers on deploy/reload; avoid mixing logs from old instances and new canary instances.
- If the server warns of "slow queries", check nodes/replicas/compaction/partition keys too; do not blame the config loader prematurely.

### 19.4. Checking One Option Across All Profiles

A small diagnostic instead of printing only default:

~~~java
DriverConfig config = session.getContext().getConfig();
config.getProfiles().forEach((name, profile) -> {
    System.out.printf(
        "profile=%s timeout=%s consistency=%s pageSize=%d%n",
        name,
        profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT),
        profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY),
        profile.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE));
});
~~~

`getProfiles()` returns known profiles including `default`, catching misnamed profiles. Yet it still **does not prove a repository method selected the right profile**; verify via code review, statement instrumentation, or per-query-family integration tests.

## 20. Observability: Effective Config Is One Dimension, Request Outcome Is Another

### 20.1. Selectively Enabling Driver Metrics

In Java Driver 4.17, driver metrics are **disabled by default**; enable the needed metrics and wire up a matching metrics library/reporter:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      pool.open-connections,
      pool.in-flight
    ]
  }
}
~~~

Exported metric names in Prometheus/Dropwizard/Micrometer depend on integration; toggling HOCON options alone **does not build a dashboard** without a registry/exporter. Before basing rollback decisions on metrics, verify metrics are actually scraped.

### 20.2. Distinguishing Driver-Side Metrics

| Metric | Scope | Interpretation |
|---|---|---|
| `cql-requests` | Session | Overall latency and throughput of CQL requests, including retries per driver semantics |
| `cql-client-timeouts` | Session | Requests exceeding the driver deadline |
| `connected-nodes` | Session | Count of nodes with active connections |
| `cql-messages` | Node | Messages/attempts sent to a node; one logical request may emit multiple messages via retries/speculation |
| `pool.open-connections` | Node | Open connections to the node |
| `pool.in-flight` | Node | Messages awaiting responses |

In multi-service Java apps, session metrics usually **do not know CQL template/feature names**. To see how a profile affects specific queries, instrument repositories with bounded **query family**, outcome, local DC, and profile name labels; never use raw SQL, tenant IDs, UUIDs, or emails as metric labels due to high cardinality and privacy risks.

### 20.3. Monitoring the Server in Parallel

~~~bash
nodetool status
nodetool tpstats
nodetool tablestats driver_lab.events_by_tenant_day
nodetool compactionstats
nodetool netstats
~~~

| Driver Observation | Helpful Server Observation | Hypothesis |
|---|---|---|
| `cql-requests` p99 rises | `ClientRequest.Read.Latency` rises | Slow coordinator/replica/storage |
| `pool.in-flight` rises, nodes healthy | App concurrency/throttle and client CPU | Possible client-side queuing |
| `cql-messages`/`cql-requests` ratio grows | Server requests, timeouts increase | Retry/speculation load amplification |
| One named profile times out | High table tombstones/SSTables-per-read | Query shape or partition size |
| Multiple query families slow down | Disk/GC/compaction spike together | Shared bottleneck, not every profile misconfigured |
| `connected-nodes` drops | Node `DOWN`, network/TLS/repair | Availability/topology issue |

**Never subtract two p99s** (driver minus server) to deduce exact network latency: percentiles across mismatched populations are not linearly additive. Use tracing and per-request event timelines when decomposing latency.

### 20.4. Measuring Impact After Changing a Profile

Set up sensible canary/control groups:

~~~text
Canary 5% instances:
  history_read timeout 5s -> 6s

Control 95% instances:
  history_read timeout = 5s

Measure over the same window/workload:
  request count, p95/p99, error/timeout%
  page counts, retries, pool in-flight
  coordinator/replica latency, CPU/disk/GC
  consistency correctness, business outcome
~~~

This is an **experimental pattern**, not a claim that 5% is always safe. Because every instance hits the **same Cassandra cluster**, canary and control **affect each other via shared resources**, so monitor the server too. Longer timeouts can hold more in-flight connections or make error rates look lower while user experience worsens.

### 20.5. Keeping a Config Source of Truth

Each release should record a **non-secret config fingerprint**:

~~~text
service: order-api
driver: 4.17.x
java: 17
cluster / local DC: cassandra-orders / dc1
config source: external /etc/order-api/driver.conf
config commit/version: abc123
default: timeout 3s / CL LOCAL_QUORUM / page 500
point_read: timeout 800ms / page 50
history_read: timeout 8s / page 200
reload enabled: yes/no, interval
~~~

Never record passwords or truststore secrets. If system properties diverge from Git config, record **effective values** and who injected the override; otherwise a rollback may revert the file without changing runtime behavior.

## 21. Production Runbook: Deploy, Reload, Verify, and Rollback

### 21.1. Preflight Before Changing a Profile

A Java request configuration change should specify:

1. **Quantitative goal:** e.g., reduce timeout rate on `orders.listRecent` without pushing p99 or in-flight requests past SLO.
2. **Scope:** service, JVM instances, cluster/DC, profile name, release/config commit.
3. **Effective C0 value:** read from `DriverConfig`, plus any explicit statement attributes.
4. **Proposed C1 value:** with units, consistency contract, and rollback plan.
5. **Override sources:** `-D`, programmatic loader, external file, or packaged resource.
6. **Reload feasibility:** is the option runtime-modifiable; does `supportsReloading` return true?
7. **Metrics:** app p95/p99/errors, driver session/node metrics, Cassandra coordinator/table stats, replica health.
8. **Data preservation:** do not alter CL/idempotence/TTL/timestamp semantics inadvertently.

### 21.2. Phased Execution

~~~text
T0: Capture baseline, config source/version, effective C0
    |
T1: Canary preflight: DC, RF, cluster health, traffic
    |
T2: Apply C1 to 1 canary instance/profile
    |
T3: Reload if option allows; otherwise redeploy session
    |
T4: Print effective C1, verify no unexpected statement overrides
    |
T5: Observe sufficient new requests and server metrics
    |
T6: Decide GO / HOLD / ROLLBACK / ESCALATE
    |
T7: Expand in batches if GO, repeating T4-T6
    |
T8: Finalize config management and service-wide state
~~~

When a change requires session rebuilds, rolling restarts can cause **connection storms/re-preparing** or warmup spikes; never restart all JVMs/replicas simultaneously for a single profile tweak.

### 21.3. Example Guardrails (All Numbers Illustrative)

| Indicator | Baseline | Illustrative Canary Trigger | Action |
|---|---:|---:|---|
| `history_read` p99 | 350 ms | `>600 ms` across 3 sufficient windows | Halt rollout/rollback |
| Timeout rate | 0.1% | `>1%` across two 5-minute windows | Rollback or open incident |
| Driver pool in-flight | 80 | Sustained rise across nodes with flat throughput | HOLD/investigate |
| `cql-messages`/`cql-requests` | ~1 on sample workload | Abnormal spike from retries/speculation | Investigate attempts/idempotence |
| Replica availability | Quorum healthy | Can no longer satisfy required CL | **ESCALATE immediately** |
| Disk await/GC | Stable | Sustained anomaly correlated with canary traffic | Do not proceed |
| Correctness | Audit checks match | Wrong rows or unapproved CL | **STOP**, do not just tweak timeout |

These are **not standard Cassandra thresholds**. Thresholds must match your system's SLOs/resources and sample sizes; for severe data/quorum errors, do not wait three windows.

### 21.4. Config Rollback Differs from Request Rollback

- **Config rollback:** revert file/flag/code to `C0`, reload or redeploy, print effective values.
- **In-flight requests:** requests already dispatched under C1 may still be running; rollback does not "recall" active requests.
- **Write outcomes:** timeouts/retries during C1 testing may have left applied writes; reconcile via idempotency/business events if uncertain.
- **Data/schema:** if the experiment also altered CQL/schema/CL, rolling back driver config alone **does not** undo data or migrations.
- **Source of truth:** clear old `-D`/programmatic overrides or update the authoritative config manager so future restarts do not re-apply C1.

### 21.5. Post-Change Verification Record

~~~text
CHANGE: ORDER-DRIVER-PROFILE-002 (example)
SERVICE / LOCAL DC: order-api / dc1
PROFILE: history_read
OPTION: REQUEST_TIMEOUT
OLD EFFECTIVE C0: 5 s
NEW PROPOSED C1: 6 s
LOADER: fromFile(/etc/order-api/driver.conf)
PER-STATEMENT OVERRIDE: none for listRecent
RELOAD: supported / attempted / changed=true
CANARY: 1 instance, period and request samples recorded
APP: p95/p99, timeout%, user-visible failures
DRIVER: cql-requests, cql-messages, pool.in-flight
SERVER: ClientRequest, Table latency, disk/GC/repair
DECISION: GO / HOLD / ROLLBACK / ESCALATE
POST-ACTION EFFECTIVE VALUE: C1 or C0 (verified)
RESIDUAL RISKS / OWNER: ...
~~~

**Never** mark `ROLLED_BACK` just because the file was edited; confirm C0 via `DriverConfig` and verify request metrics returned to acceptable levels.

## 22. Eight Real-World Scenarios and Decision-Making

### Case A — `application.conf` Says 500 ms, Service Uses 5 s

**Symptom:** Source/HOCON shows `point_read.timeout=500 ms`, yet startup diagnostics print `PT5S`.

**Hypothesis:** Deployment passes `-Ddatastax-java-driver.profiles.point_read.basic.request.timeout="5 seconds"` or a programmatic override exists.

**Resolution:** Print loader source path/version, inspect JVM flags, and check typed getters. If the deployment platform injects the property, update its **true source of truth**; editing `application.conf` alone cannot override `-D`. After rollback, verify a fresh request has no statement-level override.

### Case B — Named Profile Is Right, Yet Repository Times Out at Default

**Symptom:** `getProfile("history_read")` prints 5 s, yet request logs show 2 s timeouts.

**Likely Cause:** The repository forgot `setExecutionProfileName("history_read")` on the statement **actually passed to `session.execute`**, or called the setter and discarded the returned immutable statement.

**Resolution:** Trace the executed statement code path and write an integration test asserting profile selection. Do not raise the global default to 5 s to hide a broken profile selection.

### Case C — Profile Is Correct, Yet Required CL Returns Unavailable

**Symptom:** RF3 in dc1, profile `write_critical` sets `LOCAL_QUORUM`. One node is `DOWN`, another is still recovering; queries return `Unavailable`.

**Explanation:** At RF3, local quorum needs 2 responding full replicas; if only 1 is available, bumping timeout from 2 s → 20 s cannot conjure another replica.

**Decision:** Handle as an availability/topology incident—recover the node or shift traffic per runbook. Never drop CL to `ONE` to "fix" critical data when the business contract forbids it.

### Case D — Raising `history_read.page-size` Cuts Round Trips but Spikes Memory

**Symptom:** Raising page size 100 → 5,000 sped up a few `GET /history` calls in the lab. In production with wide rows/columns, response bytes, client heap, and GC jumped; p99 for unrelated APIs degraded.

**Decision:** Roll back or test an intermediate page size tailored to the workload; measure rows/page, bytes/page, pages/API call, and client memory. Consider cursor APIs/result caps instead of stuffing huge datasets into one page.

### Case E — Enabling `default-idempotence=true` Triggers a Retry Storm

**Symptom:** A developer enabled `basic.request.default-idempotence=true` service-wide alongside speculative execution/reroutes. Client latency briefly improved, while node `cql-messages`, CPU, write conflicts, and other timeouts climbed.

**Risk:** Mixed workloads include counters, LWTs, TTLs, and mutations generating fresh UUIDs. Marking non-idempotent requests as idempotent risks duplicate/corrupt state.

**Decision:** Restore `false` as default per contract, set explicit idempotence only on reviewed query families, and measure retries/attempts and correctness. Never treat the flag as a "free optimization".

### Case F — Profile Hot Reload Succeeds, Yet Old Requests Do Not Change

**Symptom:** `history_read` typed getter changed 5 s → 6 s, yet some active requests still timed out at 5 s.

**Explanation:** Runtime-modifiable settings apply to **new requests**; already in-flight requests do not necessarily reset their deadlines mid-execution. Some statements may also carry explicit `setTimeout(1s)`.

**Decision:** Observe post-reload request distributions alongside in-flight drains; do not restart all services just because legacy in-flight calls finished under the old timer. Plan a separate deployment when non-reloadable resources/policies must change.

### Case G — Creating a Derived Profile per Request

**Symptom:** A 10,000 QPS hot path calls `base.withDuration(...)` using tenant info on every query.

**Risk:** Thousands of profile objects, reload-propagation overhead, and opaque policies. If derived from arbitrary input, timeouts can lose finite bounds.

**Decision:** Use a small set of pre-defined named profiles or cache a few vetted derived profiles. Enforce business-bounded deadlines and caps rather than letting requests pick arbitrary timeouts.

### Case H — Raising Profile Timeout "Improves" Timeout Rate, Yet API Stays Slow

**Symptom:** Timeout increased from 2 s to 10 s; `DriverTimeoutException` rate dropped, yet API p99 climbed and more requests held in-flight pool slots longer.

**Explanation:** The driver simply waited longer without making Cassandra faster. Root causes may be missing partition keys, heavy tombstones, compaction backlogs, or unstable node networking.

**Decision:** Compare against end-to-end SLOs, inspect server/driver metrics, and fix query shape/capacity. Set rollback thresholds before raising timeouts further.

## 23. Adoption Checklist for Java Cassandra Projects

### 23.1. When Writing Initial Configuration

- [ ] Java Driver **major/version** is locked; docs and API match that version.
- [ ] A single `CqlSession` is reused, never created per request.
- [ ] Active config loader (`default`/`fromFile`/programmatic/custom) is known.
- [ ] Source precedence is verified: `-D`, programmatic, app resources, and reference.
- [ ] HOCON root uses exact `datastax-java-driver` prefix.
- [ ] Contact points and `local-datacenter` match real cluster topology.
- [ ] Keyspace RF and normal/serial CL are reviewed.
- [ ] Default request timeout/page/idempotence have explicit values.
- [ ] Named profiles map to stable policy/query families, not per-user/tenant keys.
- [ ] Each named profile overrides only options that differ from default.
- [ ] Overridden profile options are confirmed supported by reference docs.
- [ ] `default-idempotence=true` is not set across unaudited mixed write workloads.
- [ ] Credentials/TLS configs use secret management; full resolved config is never logged.

### 23.2. When Writing Repositories/Services

- [ ] CQL includes partition keys/access patterns suited for wide-column Cassandra.
- [ ] `PreparedStatement` is used for repeated queries with accurate bind types.
- [ ] Code sets `setExecutionProfileName` and keeps the returned immutable instance.
- [ ] `DriverExecutionProfile.withXxx` is not called per request when named/cached profiles work.
- [ ] Explicit `setTimeout`/`setConsistencyLevel`/`setPageSize` overrides are reviewed exceptions.
- [ ] Page size is never treated as `LIMIT` or total row cap.
- [ ] Multi-page queries enforce an end-to-end API deadline.
- [ ] Retries/speculative execution apply only where idempotency is verified.
- [ ] Unknown write outcomes after timeouts are handled rather than assumed safe to retry.
- [ ] Normal CL and LWT serial CL are clearly distinguished.
- [ ] Each query family emits success/failure, p95/p99, and timeout metrics.

### 23.3. When Changing Production Configuration

- [ ] Saved **effective C0** directly from the running JVM, not just from files.
- [ ] Recorded loader version/source/path and startup overrides.
- [ ] Targeted the right option, right profile, and right scope.
- [ ] Confirmed whether runtime-modifiable or requiring session rebuild/redeploy.
- [ ] For hot reload, verified `supportsReloading` and `reload` result.
- [ ] After reload, re-read typed getters and checked explicit statement overrides.
- [ ] Verified sufficient traffic samples, query families, and error budgets.
- [ ] Monitored `cql-requests`/`cql-messages`, in-flight, node timeouts, and server disk/GC.
- [ ] Did not trade away CL/idempotence/retry correctness for performance without review.
- [ ] Prepared canary, rollback triggers, and centralized config source of truth.
- [ ] On rollback, verified both effective C0 **and** SLO/resource recovery.

### 23.4. When Debugging "Wrong Config"

- [ ] Printed `session.getContext().getConfig().getProfiles()`.
- [ ] Printed `REQUEST_TIMEOUT`/`REQUEST_CONSISTENCY`/`REQUEST_PAGE_SIZE` per profile.
- [ ] Verified named profile spelling and casing.
- [ ] Verified the executed statement actually selects that profile.
- [ ] Checked for explicit request-level overrides.
- [ ] Checked `-D` flags on the **exact JVM**, classpath files, and programmatic builder.
- [ ] Checked whether reload actually ran and whether the option is runtime-modifiable.
- [ ] Verified local DC/replica availability before blaming timeouts on config.
- [ ] Checked whether app/framework integrations spawn another unintended session.
- [ ] Kept secrets and raw bind values out of debug output.

## 24. Self-Assessment Questions and Suggested Answers

**Question 1.** How do `reference.conf` and `application.conf` differ?  
**Guidance:** `reference.conf` is bundled in the driver JAR to provide defaults; `application.conf` holds application overrides and typically lives on the runtime classpath.

**Question 2.** When both `application.conf` and `-Ddatastax-java-driver.basic.request.timeout` declare the same option, which wins?  
**Guidance:** The system property has higher precedence in the default loader.

**Question 3.** When `programmaticBuilder` sets 3 s while JVM `-D` sets 4 s for the same option, what is the effective default timeout?  
**Guidance:** 4 s, because system properties outrank programmatic overrides in this loader.

**Question 4.** Given `fromFile("/etc/my-driver.conf")`, does the driver still automatically load every `application.conf` on the classpath?  
**Guidance:** Not by default; `fromFile` uses system properties → specified file → `reference.conf`.

**Question 5.** Default profile timeout is 2 s; named `history_read` timeout is 5 s. When a request uses `history_read` without setting a timeout, what applies?  
**Guidance:** 5 s.

**Question 6.** In Question 5, the statement also calls `setTimeout(Duration.ofSeconds(1))`. What does the request use?  
**Guidance:** 1 s, because an explicit statement timeout beats the profile.

**Question 7.** Named profile `point_read` sets only timeout, omitting CL. Where does its CL come from?  
**Guidance:** Inherited from the **merged** default profile across config sources.

**Question 8.** What is the pitfall in `s.setExecutionProfileName("point_read"); session.execute(s);` in Driver 4.x?  
**Guidance:** Built-in statements are immutable; discarding the returned instance leaves `s` without the new profile.

**Question 9.** What does `config.getProfile("unknown")` do?  
**Guidance:** It can throw `IllegalArgumentException`; validate profiles during startup/tests.

**Question 10.** `getProfile("history_read").getDuration(REQUEST_TIMEOUT)` returns 5 s, while a request sets `setTimeout(1s)`. Does 5 s prove the request uses 5 s?  
**Guidance:** No; the profile's typed getter does not reflect explicit statement overrides.

**Question 11.** Why is `getString(REQUEST_CONSISTENCY)` appropriate rather than `getInt(REQUEST_CONSISTENCY)`?  
**Guidance:** That option has a String value type; typed getters must match the types defined in `DefaultDriverOption`.

**Question 12.** Why is `page-size=25` not `LIMIT 25`?  
**Guidance:** Page size controls how many rows are fetched per page; iteration can fetch across multiple pages.

**Question 13.** A service sets `page-size=5000` and hits out-of-memory errors while iterating large results. Does lowering the timeout fix the root cause?  
**Guidance:** No; bound total results, use paging/cursors, fix data modeling, stream pages, and monitor client heap.

**Question 14.** With RF=3 in a DC and `LOCAL_QUORUM`, how many replicas must normally respond?  
**Guidance:** 2 full replicas in the local DC; if only 1 is healthy, requests can fail with unavailable.

**Question 15.** Why shouldn't you switch payments to `LOCAL_ONE` solely because its p99 is lower than `LOCAL_QUORUM`?  
**Guidance:** CL is a data contract, not just a performance knob; evaluate consistency/durability per business requirements.

**Question 16.** How do `SERIAL`/`LOCAL_SERIAL` differ from normal CL?  
**Guidance:** They apply to conditional mutations/LWT/Paxos; they do not replace normal CL and do not speed up regular point SELECTs.

**Question 17.** Does `default-idempotence=true` make a counter increment idempotent?  
**Guidance:** No. The flag tells the driver whether retries/speculation are allowed; repeating an increment still increments multiple times.

**Question 18.** `session.execute()`'s timeout covers retries; is that an end-to-end deadline for an API reading 100 pages?  
**Guidance:** Not by default; subsequent page fetches are separate requests, so the API needs its own total deadline/cursor/limit.

**Question 19.** Why doesn't editing `src/main/resources/application.conf` on a laptop immediately change a running JAR JVM?  
**Guidance:** Runtime resources are already packaged/loaded from another classpath; deploy the updated file or use an external config with supported reload.

**Question 20.** When `DriverConfigLoader.fromString` is used, can you rely on hot reload like `fromFile`?  
**Guidance:** No; `fromString` in the 4.17 API does not support runtime reload.

**Question 21.** Does `reload()` returning `true` prove protocol version or load balancing policy was reinitialized?  
**Guidance:** No; `true` only means config changed, and some options are not runtime-modifiable.

**Question 22.** A named profile timeout reloaded from 5 s to 6 s, yet requests still use 1 s. Name two common reasons.  
**Guidance:** An explicit `setTimeout(1s)` on the statement or a system property targeting that exact profile overrides it.

**Question 23.** Why is creating a new derived profile per request at 10,000 QPS bad?  
**Guidance:** Object/config allocation and reload-linkage overhead; prefer named profiles or a small cache of derived profiles.

**Question 24.** Does one driver session with multiple execution profiles equal multiple isolated Cassandra clusters?  
**Guidance:** No. Profiles are request policies sharing the same cluster/resources unless specific separate policies are configured.

**Question 25.** How do `cql-requests` and `cql-messages` differ?  
**Guidance:** Session-level CQL requests differ from per-node message attempts; retries/speculation can send multiple messages for one request.

**Question 26.** `history_read` p95 is high even though typed getters confirm the expected timeout. What next?  
**Guidance:** Check query shape/partition keys, retry/page counts, coordinator/replica/table metrics, disk/GC, and data correctness—do not just tweak config.

**Question 27.** Why shouldn't you log the full config object while debugging?  
**Guidance:** It can leak credentials, TLS truststore/key paths, contact points, and sensitive values; log only allowlisted keys.

**Question 28.** Is changing local DC via a profile enough to safely shift a service from dc1 to dc2?  
**Guidance:** No. Local DC belongs to session/load balancing configuration and requires topology/replication/readiness/network/traffic planning, not just a per-query timeout profile.

**Question 29.** To roll back timeout 6 s → 5 s, what proves completion?  
**Guidance:** Config manager reverted to C0, reload/redeploy succeeded, typed getter prints 5 s, statement overrides are checked, and SLO/timeout behavior recovers.

**Question 30.** A query uses a prepared statement with a partition key, yet p99 stays high. Will an execution profile definitely fix it?  
**Guidance:** No; causes can be oversized partitions, tombstones, many SSTables, disk/GC, or node outages. Tuning timeouts/page sizes does not change the data model.

## 25. Summary: Formula for Determining Effective Values

~~~text
                     DRIVER 4.x CONFIG
                            |
               +------------+------------+
               |                         |
        SOURCE PRECEDENCE           RUNTIME LOADER
        system properties           supports reload?
             > programmatic         option modifiable?
             > app.conf
             > app.json
             > app.properties
             > reference.conf
               |                         |
               +------------+------------+
                            |
                     DEFAULT PROFILE
                            |
             +--------------+---------------+
             |                              |
      No profile on request         Named/derived profile
             |                      inherits default
             |                       + overrides
             +--------------+---------------+
                            |
                  EXPLICIT STATEMENT OPTIONS?
                      /              \
                    YES              NO
                    |                 |
                 Override        Profile value
                    \                 /
                     \               /
                       EFFECTIVE REQUEST
                            |
                  CQL Coordinator/Replicas
                            |
              Observe latency/CL/paging/errors
                     and correctness
~~~

A short formula to remember:

\[
\text{EffectiveOption(request)}
=
\begin{cases}
\text{StatementOverride}, & \text{if explicitly set},\\
\text{Named/DerivedProfile}, & \text{if selected and overriding the option},\\
\text{Resolved DefaultProfile}, & \text{otherwise}.
\end{cases}
\]

Note that this is a **model for overridable request options**, not a universal formula for every driver setting (for instance, local DC, Netty timer, or protocol version are not resolved as per-request settings).

**Most important takeaway:** Do not ask "what does `application.conf` say?" and treat that as the final answer. Ask **which loader the session uses, how sources merged, which profile the request selected, and what the statement overrode**. Then verify via `DriverConfig.getProfile()`/typed getters and request metrics. Only by cross-checking all layers can you tune timeouts, consistency, page size, or idempotence without accidentally altering Cassandra's distributed behavior and data correctness.

## References

- [Apache Cassandra Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.0/core/configuration/) — Typesafe Config structure, execution profiles, typed getters, reload, and derived profiles (Apache-maintained from 4.18).
- [DataStax Java Driver 4.17 — Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/) — HOCON/application.conf, profile inheritance, config precedence, programmatic builder, reload.
- [DataStax Java Driver 4.17 — Reference Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — defaults and "modifiable at runtime / overridable in a profile" metadata for each option.
- [DataStax Java Driver 4.17 — DriverConfigLoader API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverConfigLoader.html) — `fromFile`, `fromClasspath`, `programmaticBuilder`, `supportsReloading`/`reload`.
- [DataStax Java Driver 4.17 — DriverConfig API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverConfig.html) — `getDefaultProfile`, `getProfile`, `getProfiles`.
- [DataStax Java Driver 4.17 — DriverExecutionProfile API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DriverExecutionProfile.html) — typed getters/`withXxx`, derived profiles, and immutability.
- [DataStax Java Driver 4.17 — DefaultDriverOption API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DefaultDriverOption.html) — constants `REQUEST_TIMEOUT`, `REQUEST_CONSISTENCY`, `REQUEST_PAGE_SIZE`, `REQUEST_DEFAULT_IDEMPOTENCE`.
- [DataStax Java Driver 4.17 — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) — `SimpleStatement`, `BoundStatement`, immutability, request attributes, and overrides.
- [DataStax Java Driver 4.17 — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/) — page size, auto/async fetching, and memory bounds.
- [DataStax Java Driver 4.17 — Retries](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/) — retry policy and timeout/unknown write outcomes.
- [DataStax Java Driver 4.17 — Query Idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/) — deciding request idempotence for retries/speculative execution.
- [DataStax Java Driver 4.17 — Speculative Execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — tail-latency reduction potential and extra request cost.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — `cql-requests`, `cql-messages`, `pool.in-flight`, registry wiring.
- [Apache Cassandra — Replication and consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — token ring, natural replicas, coordinator, quorum, and consistency.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — partition keys and wide-column query-driven design.
- [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — SELECT, INSERT/IF, paging, timestamps, and query restrictions.
