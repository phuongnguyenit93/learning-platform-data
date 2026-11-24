# 3.8 Distinguishing Available Information from Sensitive Information That Must Be Removed Before Sharing

When investigating a Java incident, operators often collect PIDs, launch commands, JVM versions, system properties, environment variables, thread dumps, GC logs, JFRs, or heap dumps. Part of this information is readily available in the process, operating system, or observability platform; however, **being accessible does not mean it is safe or permitted to share verbatim**.

For example, `jcmd PID VM.command_line` helps cross-check JVM flags, yet startup arguments can contain passwords or API keys if the application received secrets via `-D...`. `ProcessHandle.Info.commandLine()` may return the command line subject to OS permissions; it is not an automatic privacy filter. A heap dump can contain objects, tokens, and personal data residing in memory. Posting raw output onto a public issue can turn a diagnostic effort into a data breach.

This lesson focuses on the boundary between **information available for observation** and **safe, necessary information to share** within the *process and environment* context of Java. The goal is to collect the right evidence, classify risks, remove or transform sensitive information verifiably, and share within the right recipient scope while preserving investigative value.

## 1. Two Independent Questions: “Can We Read It?” and “Who Should Receive It?”

### 1.1 “Available” Only Speaks to Observability

A data field can come from many sources:

- JVM/Java APIs: `System.getProperty`, `ManagementFactory`, `ProcessHandle`, or MBeans.
- JDK tools: `jps`, `jcmd`, JFR, GC logs, and diagnostic commands supported by the target JVM.
- Operating system: process lists, command lines, environments, file descriptors, users, memory mappings, file paths, or crash artifacts.
- Deployment platform: container/pod metadata, runtime parameters, service labels, image names, logs, and metrics.
- Application: request/trace IDs, exception stack traces, URLs, HTTP headers, SQL/DB connection details, payloads, and user session info.

Observability is always bounded by **permissions**, timing, namespaces, tool versions, and runtime configuration. For instance, Java `ProcessHandle.Info.arguments()` returns `Optional` and may provide no value; `jcmd` may fail to attach to the target JVM. **Unable to read** does not mean the data does not exist; **able to read** also does not mean the data is sanitized.

### 1.2 “Shareable” Depends on Context and Recipients

The same piece of data may be appropriate in an internal incident room yet inappropriate in a public forum, vendor support ticket, or social media screenshot. You must know:

1. **Purpose**: does the recipient need to verify Java version, heap size, stack trace, or an exact endpoint?
2. **Audience**: authorized ops team, partner support, public community, or a third-party ticketing/AI system?
3. **Sensitivity level**: secrets, personal data, customer identifiers, internal infrastructure, security/defense config details, or business data?
4. **Applicable rules**: organizational policy, permitted data disclosure scope, retention periods, and access controls.
5. **Diagnostic value**: which fields are truly needed to test a hypothesis versus which ones are only “there because the tool printed them”?

A PID or Java version usually carries lower risk than an access token, yet context still matters: exposing versions alongside internal hostnames, IPs, build IDs, private paths, or deployment architecture can create sensitive intelligence when combined.

**Core principle:** select *the minimum information sufficient to explain the phenomenon* and share only with authorized recipients. There is no universal list of fields “publicly safe in every situation”.

## 2. Classify Information by Risk, Not Just by Tool Name

A practical classification for day-to-day work:

| Category | Examples in Java diagnostics | Default handling before broader sharing |
| --- | --- | --- |
| **Low-sensitivity technical data** | Java major version, GC type, max heap, thread count, total CPU time | Check context and audience; aggregated metrics can be shared if needed |
| **Internal/environment data** | Hostname, container ID, namespace, paths, private IPs, image registry, service name, internal package structure | Use aliases or functional descriptions; omit unnecessary identifiers |
| **Account/personal data** | Username, email, customer ID, session ID, request payload, IDs in URLs | Remove, aggregate, or use controlled pseudonyms |
| **Access secrets** | Passwords, bearer tokens, API keys, private keys, session cookies, credential URLs, cloud secrets | Never include in shared artifacts; if already exposed, handle as a credential incident |
| **High-risk raw diagnostics** | Heap dumps, core dumps, request/body logs, `/proc/PID/environ`, full JFR, or `hs_err_pid` | Store in protected channels; share only reviewed excerpts or via approved workflows |

This classification guides decisions, not a promise that every “low-sensitivity” number is automatically public-safe. **Sensitivity can arise from combination**: an API's p95 alone reveals little, but paired with customer IDs, payloads, internal addresses, and exact timestamps it can pinpoint individual transactions.

Also distinguish:

- **Secrets**: anyone holding the value may gain authorization or impersonate access (tokens, keys, passwords). For secrets, masking only the last few characters is usually **not enough**.
- **Personal data**: tied to specific individuals; can appear in thread names, logs, URLs, SQL, stack traces, or heap snapshots.
- **Internal/system-sensitive data**: not necessarily passwords, yet reveals topology, hostnames, private networks, repositories, defense mechanisms, or operational setup.
- **Correlation data**: trace IDs, span IDs, correlation IDs, timestamps; sometimes needed for tracing, yet linkable to other records. Keep only when purpose and audience permit.

## 3. Sources That Look Like Mere “System Info” Yet Can Hold Sensitive Data

### 3.1 Command Lines and JVM Arguments

Common sources:

```bash
jps -v
jcmd 4242 VM.command_line
ps -p 4242 -o pid,args
```

These commands illustrate querying PID `4242` in an appropriate environment; the PID is not real output and `ps` uses Linux/Unix syntax. `jcmd` requires permissions/attach and target JVM support; `jps` sees only JVMs detectable by the tool.

A command line can contain:

- `-Xmx`, `-Xms`, `-XX:+...`: usually helpful for heap/GC investigation, though internal config details still warrant review.
- `-Dservice.env=...` or `-Dconfig.path=...`: exposes environment names and internal paths.
- `-Dapi.token=...`, `--password=...`, or URLs containing `user:password@host`: **secrets that must be removed**, even though passed to the JVM as arguments.
- Main class, JAR paths, account names, installation directories: can reveal system structure or user accounts.

`jps -v` and `jcmd VM.command_line` can differ in information types and completeness; **never treat one output lacking secrets as proof that other sources are clean**.

**Hypothetical data example, containing no real credentials:**

```text
java -Xmx512m -Dservice.env=staging -Dapi.token=DEMO_ONLY_NOT_VALID -jar order-api.jar
```

Before sending to a broader audience, do not post this kind of snippet verbatim when values are real. An illustrative shared version could be:

```text
Java launcher: java -jar <application.jar>
Heap max setting: -Xmx512m
Sensitive JVM properties: [REDACTED]
Runtime profile: staging (keep only if permitted)
```

Keep `-Xmx512m` because it relates to heap investigation; remove **both the value and unnecessary details** of sensitive properties. If service or environment names are also sensitive, use neutral labels or omit those fields.

### 3.2 System Properties Are Not Identical to Environment Variables

`System.getProperties()` and certain VM commands return Java **system properties**. `System.getenv()` returns **environment variables** visible to the process within OS/runtime permissions. These two sources are distinct, and values in one are not guaranteed to appear in the other.

For instance, `user.home`, `user.name`, and `java.class.path` can expose usernames, project paths, package/class names, and deployment directories. Custom application properties can hold secrets if misconfigured. Environment variables are also frequently used to pass config/credentials into containers; they are not safe merely because they “do not appear in args”.

On Linux, with sufficient permissions, `/proc/<PID>/environ` can hold environment data as exposed by the kernel; contents may not reflect later changes depending on execution mechanisms. **Never paste that file verbatim into a ticket.** `docker inspect` output, pod specs, or diagnostic snapshots can also contain env values or secret references; never assume a tool “only reads metadata” and therefore strips sensitive info.

When comparing runtimes, ask for the exact needed field: **which variable name is declared**, whether a value is present, and which config profile/version is active. For credentials, stating “credential configured/present” is usually better than printing the value.

### 3.3 ProcessHandle and Process Listings

Java `ProcessHandle.Info` can provide:

- `command()`: executable path/name (OS and permission dependent).
- `commandLine()` and `arguments()`: best-effort command line/argv, which may be incomplete and may carry secrets.
- `user()`: account running the process, which may be internal/personal info.
- `startInstant()` and `totalCpuDuration()`: start timestamp and cumulative CPU time, if supported.

These methods return `Optional`; never treat an empty string as “safe” or infer from the executable name that arguments contain no secrets. If you only need PID and JVM version, **do not collect `commandLine()` or `user()`**.

`ProcessHandle.allProcesses()` lists many kinds of visible native processes, not just Java. Pasting the whole list into a report can expose software, accounts, background services, and naming conventions on the machine unrelated to the incident.

### 3.4 Thread Dumps, Stack Traces, and Exception Messages

Thread dumps supply stacks, thread names, and states to diagnose blocking/deadlocks or thread pools. Although a stack trace mostly contains class/method names rather than request payloads, sensitive data can still hide in:

- Thread names constructed by the application from user/customer/request IDs.
- Exception messages containing URLs, query parameters, SQL literals, filenames, or input data.
- Lock/monitor info, internal packages, and library names/versions revealing architecture.
- Logs or reports pairing thread dumps with request metadata.

Never assume “a thread dump definitely contains no secrets”; nor should you blindly strip every class name if engineering needs stack frames to locate hanging code. **Keep relevant frames and replace sensitive identifiers with consistent labels** when permitted.

### 3.5 GC Logs, Metrics, and JFR

GC logs typically show timestamps, heap regions, pauses, and flags to distinguish GC pressure. However, paths, JVM arguments, PIDs, hostnames, target filenames, or printed startup lines can expose internal details.

Metrics can carry labels such as `customer_id`, `user_id`, `tenant`, private endpoints, or paths. Some labels have **high cardinality** and simultaneously pose privacy risks. When sharing, keep aggregated values sufficient for comparison and drop unnecessary identifying labels.

A JFR recording can contain stack traces, thread names, exception events, class/method names, allocation events, file/socket context, and other events depending on config/version. It is **not an “anonymized” file by default**; analysis tools can reveal details invisible in a screenshot. Before sending a JFR externally, inspect which events were recorded, which data is sensitive, and whether exporting statistics or a filtered subset suffices instead of the entire recording.

### 3.6 Heap Dumps and Core Dumps: Higher Risk Than Plain Text

A heap dump is a snapshot of object data inside the JVM and can hold `String`s, caches, request/session data, tokens, configurations, business records, and reference graphs. Core dumps/native crash dumps can capture process memory regions, not merely stack traces. `hs_err_pid*.log` files or crash reports can expose parameters, paths, environments, and memory mappings depending on version.

**Never try “find and replace strings” in a text editor on a binary heap dump** and consider it redacted. Dump structures and binary layouts require format-aware tools; overwriting one visible string does not guarantee the data is gone from the dump. When sharing is needed:

1. Keep the raw file in a restricted-access channel protected by policy.
2. Prefer exporting **derived reports**: object histograms, total retained bytes, stacks/frames, or allocation stats sufficient for the question.
3. If sending the raw dump to an authorized party is mandatory, use formal transfer, encryption, retention limits, and data approval workflows; verify recipient scope and revocation capability.
4. Never send heap dumps over chat, public issues, or shared buckets simply because generating the file was easy.

## 4. Decision Matrix: Keep, Replace, Aggregate, or Remove?

When processing a field, choose the action based on both sensitivity and diagnostic value:

| Example field | What investigation does it help? | Handling before sharing outside the owning team |
| --- | --- | --- |
| `java.version` or JVM implementation | Runtime/JIT/GC differences, compatibility | Keep when needed and permitted; sometimes Java major version suffices |
| `-Xmx512m`, GC type, thread count | Heap sizing, GC/threads | Can keep if it does not expose restricted configuration |
| PID and start time | Confirming the exact instance | Keep internal; can replace with `process-A` in public versions |
| Full hostname, private IP, pod UID | Infrastructure correlation | Replace with `host-A`, `container-1`, or aggregate |
| Executable path with username | Identifying runtime binary | Keep executable type; mask identifying directory segments |
| System property `api.key` | Checking whether a credential is configured | Report only “configured” status; remove name/value if unneeded |
| Cookies, Authorization headers, URLs with tokens | Investigating auth/transactions | Omit values; describe header type, presence, or status code |
| Email, user/customer ID | Event correlation | Replace with random ID or managed pseudonym; omit if unneeded |
| Request body / SQL with real values | Reproducing business logic | Use synthetic payloads, parameter placeholders, or data types |
| Stack trace | Diagnosing exceptions, locks, deadlocks | Keep relevant frames; remove sensitive messages/IDs/paths |
| Heap/core dump, full JFR | Investigating memory/native crashes, event details | Share approved derived reports; raw files stay in controlled channels |

**Four main handling modes:**

- **Conditional keep:** low-sensitivity field, genuinely needed, appropriate recipient.
- **Replace (redact/mask):** strip sensitive value, use `[REDACTED]` or aliases preserving technical relationships.
- **Aggregate:** share only counts, rates, percentiles, ranges, error groups, or bucketed results instead of individual users/requests.
- **Remove:** field is irrelevant or too sensitive to share for this purpose.

Sometimes **even revealing “present vs. absent”** leaks restricted facts, such as the existence of an internal system or specific security mechanism. In that case, remove the field name itself from the shared version.

## 5. Evidence Sanitization Workflow Before Sharing

### 5.1 Step 1: Define Purpose and Recipient Scope

Write a narrow question: “Need to verify increased GC pauses when the JVM runs G1 with a 512 MiB heap” or “Need to analyze stacks of BLOCKED threads”. Avoid broad goals like “send all diagnostics so others can look around”.

Label the audience:

- **Within the owning team:** may see more evidence, still subject to least privilege.
- **Other internal teams / vendor support:** only data permitted by contract/process; trim unneeded fields.
- **Public issues, forums, learning materials, external services:** default to synthetic examples or minimal reviewed reports.

An external AI service is also **a recipient over a sharing channel**. Never paste credentials, heap dumps, or raw logs into any tool just to find a quick answer; check data transfer policies and purpose first.

### 5.2 Step 2: Minimize Data Collection at the Source

If you only need Java version and heap limit, collect just those fields; do not dump all system properties or environment variables hoping regex will catch everything. Guidelines:

1. Prefer aggregated metrics, APIs returning specific fields, or targeted read-only commands.
2. Avoid enabling debug logging that records real request bodies/headers unless necessary.
3. Avoid heavy profilers/dumps merely to answer a small question.
4. Do not print raw output onto terminals captured by broadly shared session logs if secrets might appear.
5. If raw evidence must be kept for internal forensics, store it separately with restricted permissions, encryption, and retention rules; the shared artifact is a sanitized copy.

The best approach is **not collecting or emitting sensitive data when the question does not need it**. Post-collection redaction remains an essential defense layer, not a substitute for minimization.

### 5.3 Step 3: Classify Fields and Hidden Data Locations

For every artifact, scan for:

- **Simple key/value pairs:** `password`, `passwd`, `secret`, `token`, `apiKey`, `Authorization`, `Cookie`, `privateKey`, and app-specific variable names.
- **Values embedded in strings:** query parameters, URL userinfo, connection strings, JDBC URLs, header lines, nested JSON, YAML, JVM `-D...`, command-line arguments.
- **Encoded/wrapped data:** URL encoding, Base64, escaped JSON, multiline PEM, or log chunks; absence of the word “password” does not prove cleanliness.
- **Indirect identifiers:** email, phone, usernames in paths, IPs, customer IDs, session IDs, device IDs, trace IDs, tenant/domain names.
- **Artifact metadata:** filenames, titles, folder paths, share links, comments, revision history, attachment descriptions, timestamps, and creator info.

Use automated scanners as **an assistant**, never treating “0 matches” as a safety certificate. Secrets can carry custom names; free text, binary data, or unexpected formats can evade regexes.

### 5.4 Step 4: Sanitize Using Methods Matched to Data Type

**Structured data:** use a field allowlist before exporting. For example, export `java.version`, `heap.max.bytes`, and GC type instead of serializing `System.getProperties()`. For JSON/YAML, parse structurally, filter fields, and re-serialize; avoid ad hoc text replacement that misses nested fields or corrupts output.

**Command lines:** `split(" ")` cannot reliably parse them because quoting/escaping differs across shells and OSes. To share JVM flags, extract needed non-sensitive flags intentionally; never build a “command-line sanitizer” using simple regex replacements and trust it blindly. When a `-D...` holds a secret, describe it as “sensitive property configured” rather than printing name and value.

**URLs/connection strings:** a URL can carry username/password in authority, query, path, or fragment. JDBC connection strings vary widely by driver. Prefer placeholder strings or driver/protocol-aware parsing that retains only scheme, connection type, and diagnostic traits; **never** automatically assume a URI without `@` is safe.

**Text logs/stack traces:** keep needed frames, error codes, and timestamps; trim messages containing customer data; replace usernames/hostnames with consistent aliases if correlation helps. Check before and after the replaced section so copies do not remain in other fields or nested exceptions.

**Dumps/binaries:** never redact by blind byte replacement. Extract reports from analysis tools, then review derived outputs. Keep raw dumps in restricted-access storage.

**Images/screenshots:** crop/mask values in the image, yet also check other browser tabs, tooltips, window titles, URL bars, metadata, and filenames. Whenever possible, render screenshots from sanitized text rather than capturing raw output and drawing a rectangle over secrets.

### 5.5 Step 5: Inspect the Version You Will Share, Not the Original by Mistake

Verify **the final artifact** in the exact format the recipient will open:

1. Read the entire export, including attachments, collapsed sections, metadata, or truncated tail lines.
2. Search for credential patterns, URLs, IPs, emails, usernames, token-like strings, secret-specific key names, and known sensitive values.
3. Verify aliases were applied **consistently** so a process/request remains traceable when needed without carrying real identities.
4. Test whether a recipient could recover data from base64, HTML source, comments/revisions, embedded original files, or links to raw evidence.
5. Confirm recipients, link permissions, expiration, and transfer channel; share only after contents fit the defined scope.

**Visual redaction is not always real redaction.** For example, a spreadsheet cell displaying `[REDACTED]` might still retain notes/comments or revision history; a PDF with a black box over text might still keep the underlying text layer; a compressed log archive might still hold raw secrets. Inspect the underlying data layer and final shared artifact.

### 5.6 Step 6: Keep an Audit Trail and Handle Secret Exposure Incidents

Record in the internal investigation log:

- Data source, timestamp, PID/host/container scope, and command/collector used.
- Categories of fields kept/removed/aggregated, method, and script/policy version.
- Reviewer and intended recipients; hash/checksum of derived artifacts if integrity tracking is needed.
- Protected location of raw evidence and scheduled deletion per policy; avoid writing secrets directly into approval records.

If a real credential has already leaked to an out-of-scope channel, **deleting the message is not necessarily sufficient** due to logs, copies, caches, or history. Follow your organization's incident process: notify owners, revoke/rotate secrets as appropriate, assess exposure scope, and control copies. Never republish the value to “prove it leaked”.

## 6. Before–After Comparison Example: Preserving Diagnostic Value

Suppose a JVM experiences rising heap occupancy in a test environment. The **simulated** record contains the following data (all names, domains, and tokens are unusable illustrative examples):

```text
Captured at: 2026-10-29T08:00:00Z
Process PID: 4242
Java version: 21.0.4
JVM: -Xms256m -Xmx512m -Dapi.token=DEMO_ONLY_INVALID
Run as: demo-user
Home: /home/demo-user/apps/order
DB: jdbc:postgresql://db.internal.invalid:5432/orders?password=DEMO_ONLY_INVALID
Authorization: Bearer DEMO_ONLY_INVALID
Heap used: 420 MiB
Heap max: 512 MiB
```

If sharing internally with colleagues who only need to analyze the heap, an appropriate version **after checking recipient permissions** could be:

```text
Capture time (UTC): 2026-10-29T08:00:00Z
Process: instance-A
Runtime: Java 21
Heap flags: -Xms256m -Xmx512m
Heap used: 420 MiB
Heap max: 512 MiB
Startup properties outside approved fields: omitted
Account, paths, DB endpoint, credentials, authorization header: omitted
```

The second version still supports evaluating heap occupancy and sizing. It **no longer** holds enough data to connect to the database, forge sessions, discover account names, or infer real filesystem paths. When comparing two captures from the same instance, keep the alias `instance-A` in an internal record with a protected mapping; do not publish the mapping externally.

If the goal were investigating DB latency itself, you could keep “database dependency = PostgreSQL” or query p95 stats after stripping hosts/accounts/credentials. Do not destroy all technical evidence when a safer aggregated summary works.

## 7. Java 17+ Practice: Allowlist Reporting Instead of Printing Raw Data

The example below builds **hypothetical in-memory data** and emits only allowed fields. It does not access other processes, read real environment variables, or create valid secrets. Thus stdout can be verified deterministically on Java 17+.

Save the file `DiagnosticDisclosureDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DiagnosticDisclosureDemo {
    public static void main(String[] args) {
        // All values are simulated data, not real secrets.
        Map<String, String> observed = new LinkedHashMap<>();
        observed.put("timestamp.utc", "2026-10-29T08:00:00Z");
        observed.put("jvm.version", "21.0.4");
        observed.put("pid", "4242");
        observed.put("heap.max.bytes", "536870912");
        observed.put("os.user", "demo-user");
        observed.put("db.url", "jdbc:postgresql://db.internal.invalid/orders");
        observed.put("api.token", "DEMO_ONLY_INVALID");
        observed.put("process.commandLine", "java -Dapi.token=DEMO_ONLY_INVALID");

        List<String> allowedFields = List.of(
                "timestamp.utc",
                "jvm.version",
                "pid",
                "heap.max.bytes"
        );

        int omitted = observed.size();
        for (String key : allowedFields) {
            String value = observed.get(key);
            if (value != null) {
                System.out.println(key + "=" + value);
                omitted--;
            }
        }
        System.out.println("omitted_fields=" + omitted);
    }
}
```

Compile and run:

```bash
javac DiagnosticDisclosureDemo.java
java DiagnosticDisclosureDemo
```

**Exact** stdout:

```text
timestamp.utc=2026-10-29T08:00:00Z
jvm.version=21.0.4
pid=4242
heap.max.bytes=536870912
omitted_fields=4
```

**Key points from the example:**

- The program uses `LinkedHashMap` and an ordered `List`, keeping output order deterministic. Eight fields exist in input, yet only four allowlisted fields are printed; the four omitted fields **print neither name nor value**.
- If `session.cookie` or `cloud.secret` shows up in the source tomorrow, new fields are still excluded by default; you do not need to anticipate every secret naming convention.
- A field **allowed by name** can still hold sensitive values due to mapping/source bugs. In production, validate data types, origins, and contents of each allowlisted field rather than trusting keys alone.
- PID and JVM version in the example are assumed suitable for a **hypothetical internal technical report**, which **does not** mean they are always safe to publish publicly. For other audiences, use a stricter allowlist and consider aliasing the PID.
- This is an **illustration of the minimization principle**, not a general-purpose redaction library. It does not parse command lines, nested JSON, URLs, logs, or heap dumps. Do not even load those values into `observed` in production code if they are not needed.

### 7.1 Why Is an Allowlist Usually Safer Than Regex Keyword Masking Alone?

Suppose a program prints an entire map and masks strings containing `password`. It can miss `Authorization`, `apiKey`, `sessionId`, custom credential names, tokens in URLs, or escaped values. With multi-layer serialization, secrets can also surface in secondary fields or exception messages.

An allowlist outputs only fields serving the goal, **dropping unknown fields by default**. Even after allowlisting, review values, inspect the final artifact, and verify recipient permissions. Combining both layers is far more realistic than expecting one regex to catch every secret in every format.

### 7.2 When You Need to Correlate the Same User/Host Across Logs

You can use aliases like `user-A`, `host-B`, `session-C` that stay **consistent within an incident** to preserve relationships. The mapping from alias to real value stays in a restricted-access internal store; never attach the mapping to shared outputs. Do not hash emails, phone numbers, or low-entropy customer IDs with a plain hash and call it “anonymous”: dictionary attacks can reverse them. When tokenization/pseudonymization is needed, use an approved mechanism, manage keys separately, and define correlation retention limits.

**Pseudonymization is not absolute anonymization** when timestamps, locations, behaviors, or metadata can still re-identify records.

## 8. Preserving Technical Utility After Sanitization

Over-aggressive redaction can make it impossible for others to distinguish two JVMs or runtime causes. Balance investigative utility with a structured approach:

1. **Keep units and measurement windows:** “heap used 420 MiB at 08:00 UTC, max 512 MiB” is far more useful than “memory high”.
2. **Keep technical mechanisms:** GC type, non-sensitive flags, appropriate Java version, stack states, exception types, HTTP statuses; you do not necessarily need usernames/hostnames.
3. **Keep minimal correlation:** aliases `instance-A` and `instance-B`, rounded UTC timestamps if appropriate, consistent trace IDs across measurements.
4. **Label redactions clearly:** `[REDACTED: credential]`, `[REDACTED: hostname]`, or “field omitted by allowlist”. Never replace real values with strings that look like real measurements.
5. **Do not distort facts with arbitrary edits:** if hiding part of a stack trace might drop a key frame, note clearly that frames were hidden; never reorder events or delete failures just to make metrics look “clean”.

For example, in deadlock investigations, keep thread states, lock ownership relationships, and stack frames after removing request/customer names if present. In OOM investigations, retained-size histograms or allocation trends usually suffice for initial steps; raw heap dumps are used only once necessity and protected channels are confirmed.

### 8.1 Store Raw Evidence and Shared Versions Separately

A sound storage model:

```text
Runtime/process source with real data
             |
       minimal collection
             |
         raw evidence
 (restricted store + retention)
             |
   classification and reporting
             |
       redaction + QA
             |
     sanitized artifact
             |
    authorized recipients
```

Keeping raw evidence is not always necessary or permitted. If unnecessary for the investigation, do not create extra copies. When incident policy requires keeping raw evidence, never let the raw file accidentally ride along with the sanitized version inside the same ZIP, chat attachment, or shared folder.

## 9. Practical Diagnostic Scenarios

### Scenario A — Asking About Startup Failure After Changing JVMs

Share with the engineering team: Java major/vendor, GC type, exception class, relevant stack frames, and non-sensitive heap config. Omit: full `java.class.path` if it contains internal paths, `System.getProperties()`, environment variables, tokens, or full shell history.

**Shared artifact:** Java version and JVM name (when permitted), filtered JVM flags, error type, and stack snippet after reviewing messages. If the stack contains home/user paths, apply intentional path aliases.

### Scenario B — Cannot Attach to JVM with jcmd

Helpful info: JDK tool version, runtime/vendor, PID namespace, effective user/group mismatch, attach support status, error message shape, and commands attempted. No need to paste `env` or full command lines with credentials. To prove permission issues, stating “tool ran under account A; process under account B” with aliases suffices.

**Note:** an attach failure can stem from permissions or namespaces rather than secrets; minimal sharing still supports diagnosis.

### Scenario C — Production Heap Growing Continuously

Helpful info: heap occupancy over time, GC pauses, allocation trends, top object types, and retained bytes. Raw heap dumps risk containing tokens/requests/customer data. Export only a top-class histogram or aggregated charts for initial discussions; if internal class/package names are sensitive, substitute appropriate group labels.

**Do not assume** a heap dump is safe merely because the file is compressed or because an analyzer UI only shows a few objects on screen.

### Scenario D — Slow API and Logs Contain Authorization Headers

Latency histograms, status codes, request durations, dependency durations, and trace hierarchies are useful investigative data. `Authorization` headers, cookies, request bodies, or query tokens are unnecessary for proving CPU/GC pressure. Prevent excess log capture at the source, fix logging configuration if appropriate, and review log excerpts before sending.

**If real secrets leaked**, execute incident response/rotation per policy; stop copying the exposed value into reports.

### Scenario E — Posting to the Community or a Third Party

A reproducible question can provide stripped-down source code, a sanitized stack trace, JDK version, and resource limits in aggregate numbers. Never include hostnames, cloud account IDs, private image registries, emails, or raw binary dumps just for “completeness”. Try building a **minimal reproducible example** with synthetic data before sharing real environment details.

## 10. Mistakes to Avoid

| Mistake | Consequence | Correct handling |
| --- | --- | --- |
| “The command is read-only, so its output is safe.” | Output can still hold credentials, account names, paths, business data | Classify **output contents**, not read-only nature |
| “Just mask `password`.” | Misses tokens, API keys, URLs, session cookies, personal data | Allowlist + multi-category sensitivity review |
| “Showing `***` is enough.” | Raw values remain in metadata, revisions, other logs, or embedded files | Inspect the actual artifact, permissions, and data sources after transformation |
| “Hashing emails anonymizes them.” | Values are easily reversed or linked | Remove data or use controlled pseudonymization |
| “Heap dumps are just for debugging, no user data.” | Heap objects can hold sessions, tokens, and payloads | Protect as sensitive data; prefer derived reports |
| “PIDs/hostnames are always harmless.” | Reveals topology or enables identity correlation | Decide by audience and purpose; use aliases |
| “Regex had no matches, so it's safe.” | Misses encodings, nested fields, custom names, binaries | Check structure/format, manual review, and testing |
| “Post the full stack/log now and edit later.” | Copies, notifications, caches, and history may persist | Sanitize before sharing; handle leaks via incident workflow |
| “Once secrets are gone, numbers don't matter.” | Losing units, ordering, or lock/GC relationships breaks diagnosis | Preserve technical facts and clearly mark omissions |
| “Hiding data on screen hides it from the file.” | Text layers, notes, revisions, or metadata still hold values | Re-export with actual data stripped and verify |

## 11. Checklist Before Sending a Diagnostic Artifact

- [ ] Clearly know **the recipients**, sharing channel, and technical purpose.
- [ ] Collected only data needed to test the hypothesis; avoided dumping full environments/system properties needlessly.
- [ ] Checked command lines, JVM `-D...`, args, env, URLs, headers, logs, and nested fields.
- [ ] Evaluated emails, customer/session/request IDs, account names, private IPs, hostnames, and internal identifiers.
- [ ] For JFR, heap dumps, core dumps, crash reports, or other binaries, assessed data hidden outside visible lines.
- [ ] Chose **keep / replace / aggregate / remove** per field group based on purpose.
- [ ] Preserved units, timestamps/scope, Java/JVM context, and technical events needed for analysis.
- [ ] Used consistent aliases when correlation is required; kept real mappings out of shared artifacts.
- [ ] Reviewed final output, attachments, ZIPs, metadata, links, and permissions.
- [ ] Kept a record of redactions and internal sources if re-verification is needed.
- [ ] If an exposed secret is discovered, switched to the appropriate incident response workflow.

## 12. Self-Assessment Exercises

**Exercise 1 — Choosing fields to keep.** You need to verify why two JVMs running the same code have different GC pauses. Available fields: Java vendor/version, `-Xmx`, GC type, GC event timestamps, full command line, DB password, user email, container CPU quota. Select fields serving JVM comparison (version, heap/GC, timestamps, quota) and explain why secrets and emails can be dropped; other command-line arguments must be reviewed individually.

**Exercise 2 — Choosing the sharing format.** A vendor only needs a retained-size histogram to advise on an OOM. You have a heap dump, class histogram, raw request payloads, and a heap summary report. Prefer the reviewed histogram/summary; raw dumps can contain sensitive data and should only be transferred when strictly necessary over authorized channels.

**Exercise 3 — Spotting sanitizer limits.** A program masks only `password=`. List at least four fields that can slip through: `Authorization: Bearer ...`, `apiKey`, tokens in URL queries, cookies, URL-encoded/Base64 credentials, or nested JSON fields. Then design an allowlist export suited to the requirement instead of endlessly expanding regexes.

**Exercise 4 — Re-checking the shared copy.** An HTML report displays `[REDACTED]` while the source still holds real values in `data-*` attributes; a screenshot shows the hostname in a browser tab; an attached ZIP includes the raw heap dump. Conclusion: redaction **failed** because recipients can still access sensitive data through the final artifacts.

## References

- [Java SE 21 — ProcessHandle.Info](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): `Optional` fields of process info, subject to permissions and OS.
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic commands and permission/support limits, including commands that can reveal system properties/command lines.
- [JDK 21 — jps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html): listing JVMs and options that show JVM arguments.
- [JDK 21 — JFR Runtime Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): reference for JFR event recording; event types and data must be evaluated against the actual recording.

**Key takeaway:** “Available information” answers *what tools can read within permitted scope*. “Shareable information” answers *who needs which data, at what level of detail*. In Java runtime diagnostics, **minimize collection at the source, classify by audience, export allowlists, inspect sanitized artifacts**, and keep sensitive data inside protected channels. A useful diagnostic report must supply sufficient technical evidence without carrying unnecessary credentials, personal data, or internal environment details.