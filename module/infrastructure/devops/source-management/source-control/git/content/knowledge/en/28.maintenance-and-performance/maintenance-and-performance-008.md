# Diagnosing slow operations using Git tracing mechanisms

When a Git command runs slowly, the impression that "Git is hanging" does not tell you where time is actually being spent. `git status` may spend time scanning the working tree; `git fetch` may be waiting on the network, the server, or packfile processing; `git push` may be waiting on authentication, data transfer, or hooks. Git provides multiple tracing mechanisms to record internal activity and execution timings, helping pinpoint the slow stage before changing configuration or infrastructure.

Commonly used environment variables include `GIT_TRACE`, `GIT_TRACE_SETUP`, `GIT_TRACE_PERFORMANCE`, the Trace2 group (`GIT_TRACE2`, `GIT_TRACE2_PERF`, `GIT_TRACE2_EVENT`), along with specialized traces for packets, HTTP, packfiles, and refs. Start with a general performance trace, then enable specialized traces matching the symptoms. Tracing is an observation tool; by itself it does not optimize the repository or fix bugs.

## 1. What questions can tracing help answer?

A Git operation typically consists of multiple steps. For example, `git fetch` may perform:

1. Read repository and remote configuration.
2. Launch a transport such as SSH or HTTP.
3. Negotiate protocol capabilities and determine which refs need updating.
4. Receive packfile or object data.
5. Verify, unpack, and write objects to the object database.
6. Update refs and related metadata.

If you only measure total runtime, you know how long the command took but not which step was slow. Tracing reveals child processes, protocol activity, internal processing regions, and stage timings.

Questions you can investigate include:

- Which child commands is Git running, and how long does each child take?
- Is time spent in repository initialization, reading the index, or processing objects?
- Is fetch/push waiting on packets from the remote or transferring data over HTTP?
- Is Git accessing packfiles excessively or performing many ref operations?
- Is a command slow because of Git itself or because of SSH, a credential helper, a hook, the network, or the server?

Tracing helps narrow down the cause. To measure CPU, disk I/O, DNS, network latency, or external process behavior at the operating system level, additional profilers and monitoring tools may be needed.

## 2. Starting with GIT_TRACE and GIT_TRACE_PERFORMANCE

### GIT_TRACE: viewing general activity

`GIT_TRACE` enables Git's general trace. It is useful for inspecting alias expansion, invoked child commands, and certain internal execution steps.

On macOS/Linux or Git Bash:

```bash
GIT_TRACE=1 git status
GIT_TRACE=1 git fetch origin
```

A value of `1` (or `true`) typically sends trace output to standard error. You can specify a file path to save the trace:

```bash
GIT_TRACE=/tmp/git-trace.log git fetch origin
```

In PowerShell:

```powershell
$env:GIT_TRACE = "1"
git fetch origin
Remove-Item Env:GIT_TRACE
```

If you want to write to a file:

```powershell
$env:GIT_TRACE = "$env:TEMP\git-trace.log"
git fetch origin
Remove-Item Env:GIT_TRACE
```

General tracing is useful for checking which programs Git invokes—such as `ssh`, `git-remote-https`, a credential helper, or a hook. If a child process appears in the trace and Git waits on it for a long time, investigate that process rather than focusing solely on Git core.

### GIT_TRACE_PERFORMANCE: viewing execution timings

`GIT_TRACE_PERFORMANCE` records timing information for the Git command and certain processing regions. Example:

```bash
GIT_TRACE_PERFORMANCE=1 git status
GIT_TRACE_PERFORMANCE=1 git log --all --oneline -100
```

Output typically includes durations in seconds and descriptions of the measured command or phase. This is a quick way to tell whether time is spent overall or in a specific internal step.

You can write to a file:

```bash
GIT_TRACE_PERFORMANCE=/tmp/git-performance.log git status
```

In PowerShell:

```powershell
$env:GIT_TRACE_PERFORMANCE = "$env:TEMP\git-performance.log"
git status
Remove-Item Env:GIT_TRACE_PERFORMANCE
```

When you only need to answer "how long did this command take and which phase does Git report as expensive?", start with `GIT_TRACE_PERFORMANCE` before enabling more detailed protocol traces.

## 3. Trace2: structured observation of activity

Trace2 is Git's modern tracing system. It adds structured information about processes, threads, events, processing regions, and durations. Trace2 is useful when commands are complex, involve multiple child processes, or require automated log analysis.

Git provides three commonly used Trace2 targets:

| Environment variable | Data format | When to use |
|---|---|---|
| `GIT_TRACE2` | General Trace2 | Inspect execution flow and events in standard Trace2 format |
| `GIT_TRACE2_PERF` | Text-based performance trace | Directly read durations, regions, and process relationships |
| `GIT_TRACE2_EVENT` | JSON events | Parse with scripts, jq, or log systems |

### Trace2 performance

Example in a Unix-like shell:

```bash
GIT_TRACE2_PERF=/tmp/fetch-perf.log git fetch origin
```

In PowerShell:

```powershell
$env:GIT_TRACE2_PERF = "$env:TEMP\fetch-perf.log"
git fetch origin
Remove-Item Env:GIT_TRACE2_PERF
```

Trace2 performance can show process start/end timestamps, durations, opened/closed processing regions, and child process activity. Trace lines carry process and thread identifiers, which helps when multiple Git tasks run nested inside one another.

### Trace2 event JSON

When structured data is needed:

```bash
GIT_TRACE2_EVENT=/tmp/fetch-events.json git fetch origin
```

In PowerShell:

```powershell
$env:GIT_TRACE2_EVENT = "$env:TEMP\fetch-events.json"
git fetch origin
Remove-Item Env:GIT_TRACE2_EVENT
```

The event file contains JSON records, each describing an event. Depending on the operation and Git version, you may see event types such as `start`, `cmd_name`, `child_start`, `child_exit`, `region_enter`, `region_leave`, `data`, and `exit`.

These events help reconstruct the execution timeline. For instance, `child_start`/`child_exit` pairs indicate when a child process was spawned and finished; `region_enter`/`region_leave` mark a processing region; `exit` records the end of the Git process. Not every command emits every event type.

### Choosing Trace2 or traditional traces?

- Use `GIT_TRACE_PERFORMANCE` for quick timing checks.
- Use `GIT_TRACE2_PERF` for deeper visibility into processing regions and child processes.
- Use `GIT_TRACE2_EVENT` when you need JSON parsing or CI telemetry collection.
- Use `GIT_TRACE` to view general command invocations.

There is no need to enable all of them at once from the start. Enabling one group at a time based on the question you need answered keeps logs readable with minimal noise.

## 4. Checking which repository Git detects with GIT_TRACE_SETUP

Sometimes commands are slow or behave unexpectedly because Git discovers a different repository, worktree, or index than anticipated. `GIT_TRACE_SETUP` records Git setup details such as current directory, Git directory, working tree, and prefix.

Example:

```bash
GIT_TRACE_SETUP=1 git status
```

Or write to a file:

```bash
GIT_TRACE_SETUP=/tmp/git-setup.log git status
```

In PowerShell:

```powershell
$env:GIT_TRACE_SETUP = "1"
git status
Remove-Item Env:GIT_TRACE_SETUP
```

This trace is useful when:

- Running commands from a subdirectory causes Git to detect the wrong repository.
- Using linked worktrees and needing to verify the Git directory/common directory.
- A script sets `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE`, shifting command context.
- An IDE or tool invokes Git from an unexpected working directory.

For quick standalone verification, you can combine:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

## 5. Packet tracing when fetch or push is slow

Git uses a packet-line exchange protocol when communicating with remotes. `GIT_TRACE_PACKET` logs packet activity at the protocol level, revealing capability negotiation, ref advertisement, and message exchanges.

Examples:

```bash
GIT_TRACE_PACKET=1 git ls-remote origin
GIT_TRACE_PACKET=1 git fetch origin
```

Output typically distinguishes sent and received data and displays packet-line payloads or corresponding protocol messages. This trace is helpful when:

- Fetch/push spends time in the negotiation phase.
- The server returns unexpected refs or capabilities.
- Protocol compatibility issues arise between client and server.
- You need to identify which step the client is waiting on for a response.

Packet traces are quite detailed and can generate large logs. They may also contain branch names, tags, URLs, or repository metadata. Enable them only during diagnosis and review logs before sharing.

## 6. Tracing HTTP(S) with GIT_TRACE_CURL

When a remote uses HTTP or HTTPS, Git uses a transport layer based on libcurl. `GIT_TRACE_CURL` enables request/response and HTTP connection tracing, helpful when fetch or push is slow.

Example:

```bash
GIT_TRACE_CURL=1 GIT_TRACE_CURL_NO_DATA=1 git fetch origin
```

`GIT_TRACE_CURL_NO_DATA=1` omits payload data from the curl trace so logs focus on connection details and headers. Depending on the version and request type, the trace may still include sensitive metadata.

In PowerShell:

```powershell
$env:GIT_TRACE_CURL = "1"
$env:GIT_TRACE_CURL_NO_DATA = "1"
git fetch origin
Remove-Item Env:GIT_TRACE_CURL
Remove-Item Env:GIT_TRACE_CURL_NO_DATA
```

Curl tracing helps investigate:

- Whether DNS, TCP connection, or TLS handshake is slow.
- Which HTTP status codes the server returns.
- Whether redirects, retries, or repeated authentication occur.
- Response wait times and header exchanges.
- Proxy or HTTP configuration issues.

Never enable curl tracing and post raw logs publicly. Review internal URLs, usernames, headers, cookies, proxy info, and any identifying data before sharing. Although Git redacts some sensitive headers in certain versions, do not rely on that as a guarantee that logs contain no secrets.

## 7. Tracing packfile and ref access

When local operations are slow, the issue may involve the object database, packfiles, or ref storage.

### GIT_TRACE_PACK_ACCESS

`GIT_TRACE_PACK_ACCESS` logs when Git accesses packfiles, typically including the packfile and offset read. Example:

```bash
GIT_TRACE_PACK_ACCESS=1 git log --all --oneline -200
```

This trace is useful when you suspect a history or object read operation is hitting packfiles repeatedly. It provides clues about pack read activity, though it does not identify which blob is largest or prove that the disk itself is slow.

### GIT_TRACE_REFS

`GIT_TRACE_REFS` records activity related to the ref database, useful when branch/tag operations or ref updates seem slow:

```bash
GIT_TRACE_REFS=1 git branch --all --verbose
GIT_TRACE_REFS=1 git show-ref
```

If ref counts are large or the repository uses a specific ref backend, this trace helps identify ref read/write steps. Do not draw conclusions solely from trace line counts; cross-check against execution timings and repository structure.

## 8. Choosing traces by symptom

No single trace variable fits every issue. The table below suggests starting points:

| Symptom | Trace to try first | What to observe |
|---|---|---|
| `git status` or `git log` is slow | `GIT_TRACE_PERFORMANCE`, `GIT_TRACE2_PERF` | Total runtime and internal processing regions |
| Git invokes the wrong program or alias | `GIT_TRACE` | Expanded commands and child processes |
| Git detects the wrong repository/worktree | `GIT_TRACE_SETUP` | Git directory, worktree, prefix, and current context |
| `fetch`/`push` is slow at the protocol level | `GIT_TRACE_PACKET` | Packet exchange and negotiation stages |
| HTTPS remote is slow or returns HTTP errors | `GIT_TRACE_CURL` | Connection, TLS, HTTP status, redirects, and response times |
| Local object/history reads are slow | `GIT_TRACE_PACK_ACCESS` | Packfile accesses and offsets |
| Branch or tag reads/writes are slow | `GIT_TRACE_REFS` | Ref database activity |
| Complex command with many child processes | `GIT_TRACE2_EVENT` | Event sequence and child process durations |

Select traces based on symptoms instead of enabling all of them. If performance traces show Git waiting on a child process, enable appropriate traces for transport or hooks; if time is spent in internal processing regions, switch to pack/ref traces or deeper profilers.

## 9. Workflow for investigating a slow Git command

A consistent workflow prevents changing configuration before knowing the root cause.

### Step 1: Record the command and reproduction conditions

Note down:

- Full command and arguments.
- Relevant repository, branch, and remote.
- Git version via `git --version`.
- Operating system, filesystem type, and network connection if applicable.
- Normal runtime versus runtime during the issue.

Retry the same command under comparable conditions. A first run may reflect a cold cache, whereas subsequent runs are faster because objects or metadata are already in the OS cache.

### Step 2: Measure total time with performance traces

Example:

```bash
GIT_TRACE_PERFORMANCE=1 git status
```

Or use Trace2:

```bash
GIT_TRACE2_PERF=/tmp/git-status.perf git status
```

Identify total duration and any processing regions with notable runtimes.

### Step 3: Check whether Git spawns child processes

```bash
GIT_TRACE=1 GIT_TRACE2_PERF=/tmp/git-command.perf git fetch origin
```

If the trace shows Git invoking SSH, a credential helper, a hook, or another program, inspect that process's duration and configuration.

### Step 4: Enable specialized traces

- If protocol issues are suspected, use `GIT_TRACE_PACKET`.
- If using HTTP(S), use `GIT_TRACE_CURL` and consider `GIT_TRACE_CURL_NO_DATA`.
- If packfile issues are suspected, use `GIT_TRACE_PACK_ACCESS`.
- If ref issues are suspected, use `GIT_TRACE_REFS`.

Enable only necessary traces to keep logs short and readable.

### Step 5: Form a hypothesis and verify

For example, if `fetch` is slow and traces show most time spent waiting on HTTP responses, the hypothesis may point to network, proxy, or server latency. If time is spent processing packs after data arrives, examine pack sizes, CPU, I/O, and the object database. Verify every configuration change by re-running the same command under comparable conditions.

### Step 6: Disable traces and save needed results

Once collection is complete, remove the environment variables set in the current shell. Store needed logs outside the repository and scrub sensitive information before sharing with support teams.

## 10. Practical example: investigating a slow fetch

Suppose `git fetch origin` takes several minutes. Start with performance measurement and Trace2 logging:

```bash
GIT_TRACE2_PERF=/tmp/fetch-perf.log git fetch origin
```

If significant time appears in the transport process, enable packet tracing:

```bash
GIT_TRACE_PACKET=1 GIT_TRACE2_PERF=/tmp/fetch-protocol.perf git fetch origin
```

If the remote uses HTTPS, add curl tracing:

```bash
GIT_TRACE_CURL=1 GIT_TRACE_CURL_NO_DATA=1 \
GIT_TRACE2_PERF=/tmp/fetch-http.perf git fetch origin
```

Read the results in order:

1. Trace2 shows total time and which child processes consume time.
2. Packet trace shows negotiation and exchanges with the remote.
3. Curl trace reveals HTTP connections, TLS, status codes, redirects, or retries.
4. If data arrives quickly yet processing remains slow, move on to inspecting packs/objects, CPU, and I/O.

Do not conclude "Git is slow" simply because total fetch time is long. The cause may lie in DNS, proxy, VPN, hosting server, authentication, data volume, or local disk speed.

## 11. Practical example: investigating slow git status

`git status` must compare the index, HEAD, and the working tree. In repositories with very many files, slow filesystems, or antivirus scanning directories, this operation can take significant time.

Measure first:

```bash
GIT_TRACE_PERFORMANCE=1 git status
```

If deeper analysis is needed:

```bash
GIT_TRACE2_PERF=/tmp/status.perf git status
GIT_TRACE_SETUP=1 git status
```

Setup tracing confirms Git is inspecting the expected working tree. Performance tracing shows whether time is spent reading the index, refreshing stat state, or in other processing regions emitted by your Git version.

If filesystem issues are suspected, continue inspecting file counts, filesystem/network drives, antivirus/indexers, and appropriate monitor settings. Git tracing identifies what Git is waiting on; it does not replace OS-level measurements of file access latency.

## 12. Saving logs and reading Trace2 JSON data

When logs are long, write them to a temporary directory outside the repository so you do not accidentally stage or commit diagnostic logs.

Unix-like shell:

```bash
GIT_TRACE2_EVENT=/tmp/git-trace.json git status
```

PowerShell:

```powershell
$traceFile = Join-Path $env:TEMP "git-trace.json"
$env:GIT_TRACE2_EVENT = $traceFile
git status
Remove-Item Env:GIT_TRACE2_EVENT
Get-Item $traceFile
```

Trace2 events are line-delimited JSON (*JSON Lines*), so they can be filtered with JSON tools. For example, if `jq` is installed, view child process start and exit events:

```bash
jq 'select(.event == "child_start" or .event == "child_exit")' /tmp/git-trace.json
```

Exact field names depend on the event type. Inspect the actual structure before writing rigid parsers. When comparing multiple runs, save separate logs per run along with Git version, command, branch, and test conditions.

## 13. Security and limitations of tracing

Traces can contain information you do not want made public:

- Remote URLs, hostnames, repository paths, and branch names.
- Packet/protocol metadata or ref names.
- HTTP details, headers, cookies, proxies, or authentication details.
- Local paths, usernames, and environment details.
- Process names, command-line arguments, or running hooks.

Some traces can contain very large payloads or sensitive information depending on transport and Git version. Never post raw logs on public issues before reviewing and redacting private details. Never put tokens or passwords on the command line to trace them; use credential helpers and proper authentication mechanisms.

Tracing also introduces logging and processing overhead. Enabling many variables simultaneously can produce huge logs, increase overhead, and skew timings compared to normal runs. Keep traces brief, reproduce under controlled conditions, and disable them immediately after gathering enough data.

Git's internal traces are not a system-wide profiler. If you need CPU hotspots, syscalls, page faults, I/O latency, or detailed DNS timings, combine OS profilers, network tools, and server logs.

## 14. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| `GIT_TRACE=1` reveals the full root cause of every slow command | It provides general tracing; pick performance or specialized traces based on symptoms |
| `GIT_TRACE_PERFORMANCE` optimizes Git automatically | It only records timing metrics and does not improve performance |
| Trace2 event JSON always emits the same event set | Emitted events depend on the command, Git version, and execution paths |
| Packet traces only contain harmless data | They can expose refs, URLs, or protocol metadata; review before sharing |
| Curl trace is used for SSH | `GIT_TRACE_CURL` is for HTTP(S) transport; SSH requires checking the SSH process and appropriate traces |
| Pack access trace identifies the exact largest blob | It logs packfile access activity, not an object size ranking report |
| Every hook appears identically in traces | Hooks appear only when invoked; check hook names, `core.hooksPath`, and child processes |
| A slow trace proves Git core is at fault | Time may be spent in networking, filesystem, credential helpers, hooks, or external programs |

## 15. Key takeaways

Start diagnostics with `GIT_TRACE_PERFORMANCE` or `GIT_TRACE2_PERF` to pinpoint which stage takes time. Use `GIT_TRACE` to inspect child commands, `GIT_TRACE_SETUP` to verify repository context, `GIT_TRACE_PACKET` for protocol exchanges, `GIT_TRACE_CURL` for HTTP(S), `GIT_TRACE_PACK_ACCESS` for packfiles, and `GIT_TRACE_REFS` for the ref database. When automated analysis or multi-process visibility is needed, `GIT_TRACE2_EVENT` provides structured JSON data.

Enable only the traces you need, store logs outside the repository, unset environment variables after measuring, and review for sensitive data before sharing. Use the findings to form a hypothesis and verify it with comparable runs. Tracing shows what Git is doing and where time goes; optimization decisions should rest on confirmed causes.
