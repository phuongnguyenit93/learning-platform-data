# 8.7 Correlating native thread IDs with OS CPU metrics

A Java service has high CPU, yet its thread dump shows hundreds of `RUNNABLE`, `WAITING`, and `TIMED_WAITING` threads. Which thread is actually consuming CPU? Looking only at `Thread.State` cannot answer that: a thread with Java state `RUNNABLE` may be in a native I/O wait, while the thread consuming CPU could be application code, GC, the JIT compiler, or JNI.

A useful investigation workflow on **HotSpot/OpenJDK 17 running on Linux** is **collect per-OS-thread CPU → locate the corresponding native thread ID (`nid`) in the thread dump → read that exact thread's stack frames → verify using CPU samples and closely timed dumps**. This lesson explains that exact mapping and its limitations when using `top -H`, `ps -L`, `pidstat -t`, `/proc/<pid>/task/<tid>`, `ThreadMXBean`, JFR, and container metrics.

**Learning outcomes:** after this lesson, you can convert hex `nid` to decimal Linux TID; distinguish Java ID, HotSpot `tid`, and native `nid`; choose between instantaneous and cumulative CPU measurements; compute %CPU from two samples with consistent units; correlate multiple snapshots with accurate PID/JVM identity; and avoid confusing high CPU with `RUNNABLE` threads, load average, or CPU throttling.

## 1. Investigation model: two perspectives, one thread

A Java thread is mapped by HotSpot to an OS thread on standard JDK 17. Thread dumps tell the story via **call stacks inside the JVM**; Linux tools tell the story via **CPU time/OS scheduling**. Both sides need a common join key, usually the **native thread ID**, along with the exact process and timestamp.

```text
           Linux / OS                            JVM HotSpot
┌────────────────────────────┐        ┌───────────────────────────────┐
│ Java process PID           │        │ JVM PID/start/container       │
│ Decimal LWP/TID: 10815     │        │ thread header: nid=0x2a3f     │
│ %CPU over observation win. │        │ name="payment-worker-7"       │
│ TIME / utime+stime ticks   │        │ #42, tid=0x..., Java state    │
│ OS scheduling state        │        │ Java stack frames + locks     │
└──────────────┬─────────────┘        └───────────────┬───────────────┘
               └───── 10815 == 0x2a3f ───────────────┘
                              │
                              ▼
                   Add UTC timestamp,
             PID namespace, and JVM generation
                              │
                              ▼
       Evidence-backed hypothesis: Java/GC/JIT/native,
                 CPU-bound or blocked/I/O
```

**A successful mapping is not yet the root-cause conclusion:** `nid` takes you to a thread entry, yet the stack at one exact instant may differ from the code that consumed CPU during the preceding interval. To distinguish a “repeated hotspot” from “happened to be in method X once”, use multiple dumps, CPU counters, and an appropriate JFR/profiler.

### 1.1. Six prerequisites before joining

1. **Same JVM process:** never join `top` output from PID A with a dump from PID B.
2. **Same JVM generation:** PIDs can be reused by the OS after restarts; also record JVM start/uptime and container identity.
3. **Same PID namespace:** Linux host PID/TID numbers can differ from numbers seen inside a container.
4. **Close enough in time:** `top` measures an interval; a dump is a point-in-time snapshot.
5. **Consistent %CPU definition:** one logical core or total across N cores? Average since process start or recent interval?
6. **Right identifier:** native TID `nid`; **never** substitute Java ID, `tid` pointer, or object monitor ID.

## 2. Three easily confused identifiers in thread dumps

A **HotSpot-modeled** header:

```text
"payment-worker-7" #42 daemon prio=5 os_prio=0 cpu=512.40ms elapsed=30.02s
   tid=0x00007f1a84032000 nid=0x2a3f runnable
   [0x00007f1a001bd000]
   java.lang.Thread.State: RUNNABLE
        at com.example.pricing.PriceEngine.calculate(PriceEngine.java:118)
        at com.example.checkout.CheckoutService.total(CheckoutService.java:75)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

Line breaks and values here are formatted for readability; real HotSpot may print the header on one line, change ordering, or omit some fields depending on build/JDK/options.

| Field | Example | Meaning | How to use |
| --- | --- | --- | --- |
| Thread name | `"payment-worker-7"` | Label set by app/framework/JVM; not unique | Identify function, read stack |
| `#42` | Java thread number in illustrative HotSpot format | Related to Java thread identity, not OS TID | Compare with Java management when format matches |
| `tid=0x00007f...` | Address of internal HotSpot `JavaThread` structure | **Not** the Linux TID | Format-specific VM diagnostics, never use in `top -H` |
| `nid=0x2a3f` | Hexadecimal native OS thread ID | **Join key to decimal Linux LWP/TID** | Convert to `10815` |
| `cpu=512.40ms` | Cumulative CPU time printed by runtime if present | **Not** %CPU over the past second | Compare increase between two samples of the same thread when metric fits |
| `elapsed=30.02s` | Thread lifetime per runtime | Not request duration | Hints at thread lifecycle, does not measure CPU usage |
| `java.lang.Thread.State: RUNNABLE` | Java thread state | Not necessarily executing on CPU | Read alongside frames and OS counters |

There is no Java SE contract requiring every vendor to use this exact header text or field names. The `nid` join applies to **HotSpot dumps with native IDs**, not as a portable parser across all JVMs.

### 2.1. Java thread ID is not Linux thread ID

Java 17:

```java
long javaId = Thread.currentThread().getId();
```

This is a **snippet inside a method**, returning a `long` Java ID. `ThreadMXBean.getThreadCpuTime(long id)` and `ThreadInfo.getThreadId()` use the **Java thread ID**. The Java SE 17 interface **does not provide a standard `getNativeThreadId()`**. If `ThreadMXBean` reports Java ID `42`, do not go looking for Linux LWP 42.

Likewise, never convert HotSpot `tid=0x00007f...` to decimal and pass it to `top -H`: that field is an **internal native JVM pointer**, typically very large and distinct from `nid`.

### 2.2. What is the native ID in Linux?

A Linux process can contain multiple tasks/threads. On Linux, each thread has a kernel-assigned **thread ID (TID)**; tools like `ps -L` commonly label that column `LWP` or `SPID`. Within a process's thread group, the thread-group ID (TGID) is what users ordinarily call the **process PID**.

On HotSpot/Linux, `nid` in dumps usually prints the native TID **in hexadecimal**, whereas `top -H` and `ps -L` display **decimal**.

Example:

```text
nid = 0x2a3f (hex)
    = 2*4096 + 10*256 + 3*16 + 15
    = 10815 (decimal)
```

Linux `bash` shell:

```bash
printf '%d\n' 0x2a3f
```

Exact output:

```text
10815
```

If you need the reverse conversion to search from Linux into a dump:

```bash
printf '0x%x\n' 10815
```

Exact output:

```text
0x2a3f
```

In Bash, `printf` accepts `0x...` numbers. On other shells or tools, hex parsing syntax can differ; do not assume Windows `cmd.exe` understands the same syntax. For larger TIDs, do not truncate leading digits or cast to types that can overflow.

### 2.3. PID namespaces change the numbers

Inside a container, the JVM might see PID `1`, while the host sees that same JVM as PID `18432`. Thread TIDs can also differ across namespaces. Thus:

```text
container namespace: TGID=1,    TID=88
host namespace:      TGID=18432, TID=18510
```

This is a **hypothetical mapping example**, not metrics from a real system. If the dump was captured **inside a container**, read OS thread metrics **from that same PID namespace** or establish the mapping reliably. Use `/proc/<pid>/status` with `NSpid`/`NStgid` fields when supported and authorized to inspect, or use approved container runtime tools. Never mix numbers from host and container just because they share the same service name.

## 3. Getting per-thread OS CPU on Linux

### 3.1. Start with the exact PID

Before running measurement commands:

- Identify the real Java process, host/container ID, JVM start time, and build revision.
- Confirm the PID is inside the running terminal's namespace.
- Check OS permissions for reading process/thread information.
- If using `jcmd`, the JDK tool may require the same effective user/group as the JVM and may not see JVMs in other containers.
- Record UTC timestamps for each capture, since OS %CPU and dumps are rarely captured at the exact same instant.

Examples below assume JVM PID `12345` in the same Linux PID namespace. **Replace with a verified PID**; never target another process's PID.

### 3.2. `top -H -p PID`: observing CPU by update interval

```bash
top -H -p 12345
```

With GNU/procps `top`, `-H` enables **threads** mode instead of aggregating all threads of a process, and `-p` filters by PID. In interactive mode, you can sort by `%CPU` and inspect the thread row's PID/TID column.

To capture in batch mode when supported by the tool:

```bash
top -b -H -p 12345 -d 1 -n 3
```

`-b` is batch mode, `-d 1` sets a 1-second sampling interval, `-n 3` sets 3 update iterations. **The first iteration** may be calculated over a different window or may not represent the most recent interval; when analyzing spikes, use subsequent iterations with timestamps if available. These commands do not save files automatically; if saving, choose a restricted-access path.

In `top`, **Irix mode** and **Solaris mode** affect how `%CPU` is normalized on multi-CPU machines:

- Irix mode on: `100%` corresponds to roughly **one logical CPU core** fully busy over the interval. A **multi-threaded process** can exceed 100%.
- Solaris mode: `%CPU` is divided by the CPU count per the tool's definition, making numbers look smaller.

Record the `top` mode (key `I` toggles it in procps), tool version, and CPU denominator. For **one ordinary OS thread**, maximum consumption equivalent to **one core** is roughly 100% in Irix mode (excluding sampling noise/delay). Never compare a Solaris-mode `top` row directly with a dashboard defining 100% = one core.

### 3.3. `ps -L`: viewing LWP and lifetime CPU

```bash
ps -L -p 12345 -o pid,lwp,stat,pcpu,time,comm
```

Common columns:

| Column | Meaning | Pitfall |
| --- | --- | --- |
| `PID` | Thread-group/process ID | Not the individual row's LWP |
| `LWP` | Decimal OS thread ID | Joins to HotSpot `nid` after hex conversion |
| `STAT` | OS scheduler state | Differs from `java.lang.Thread.State` |
| `%CPU` / `PCPU` | In procps `ps`, ratio of CPU time / task lifetime (lifetime average) | **Not** %CPU over the last 1 second |
| `TIME` | Cumulative CPU time | Not wall time or UTC timestamp |
| `COMMAND` / `COMM` | Native task name, may be truncated | Not always identical to Java thread name |

Because `ps %CPU` can be a **lifetime average since the thread started**, a thread that was busy for 10 minutes and then idle for 20 minutes can show a very different %CPU than recent `top`. Use `ps -L` to verify identity and lifetime data; use delta samples or `top`/`pidstat` when recent rates are needed.

A **fictional** sample line:

```text
PID     LWP   STAT  %CPU     TIME COMMAND
12345  10815  R     79.5 00:02:03 java
```

From `STAT=R` and `%CPU=79.5` alone you cannot conclude which Java frame caused the load: look up `nid=0x2a3f` in a dump near the measurement time.

### 3.4. `pidstat -t -p PID`: thread CPU across multiple intervals

If Linux has **sysstat** (`pidstat` is not part of the JDK):

```bash
pidstat -t -u -p 12345 1 5
```

This command can report each TID, `%usr`, `%system`, and `%CPU` over 1-second intervals (count 5). Exact labels/columns and normalization depend on `pidstat` version; read the local man page before comparing with `top`. Prefer tools already installed rather than installing software into production just for prettier CPU tables.

### 3.5. Tool selection table

| Need to know | Starting source | Reason |
| --- | --- | --- |
| Which TID recently used the most CPU? | `top -H -p PID` or `pidstat -t` | Reflects recent measurement intervals |
| Does a TID exist in the process? | `ps -L` or `/proc/PID/task/TID` | Confirms mapping and namespace |
| Cumulative CPU time of a TID? | `ps TIME` or `/proc/PID/task/TID/stat` | Provides counter for taking deltas |
| Java stack of that TID? | `jcmd PID Thread.print -l` and `nid` | Maps native ID → Java frames |
| Native/GC/JIT thread without Java frames? | HotSpot internal threads, JFR/native profiler | Java stack may not exist |
| Total process CPU and quota? | Process/cgroup OS metrics | One thread does not represent the entire JVM |
| Are errors caused by CPU throttling? | `cpu.stat` and quota of the exact cgroup | Per-thread %CPU cannot prove throttling |

## 4. Capturing thread dumps to join with OS metrics

### 4.1. `jcmd Thread.print` on the right JVM

```bash
jcmd -l

# Check the actual JVM version, not just java from shell PATH.
jcmd 12345 VM.version

# Inspect supported commands and options.
jcmd 12345 help Thread.print

# Capture Java thread stacks and lock details (when authorized).
jcmd 12345 Thread.print -l
```

According to Oracle JDK 17 documentation, `Thread.print` has **Medium** impact (depending on thread count); it is not a zero-cost metric read. For JVMs with thousands of threads or experiencing severe latency, limit capture count and avoid dumping across the entire cluster. `jcmd` requires matching permissions and may not list/attach across container boundaries.

When conserving impact, do not capture hundreds of dumps to “scan” CPU. One to a few snapshots near the spike, paired with OS CPU samples/JFR, is usually far more informative.

### 4.2. Example joining a `top` line to a dump

Suppose `top -H` prints:

```text
PID      %CPU    TIME+      COMMAND
10815    97.3    2:06.43    java
```

In **the same JVM**, an illustrative dump entry:

```text
"pricing-hot-loop" #42 daemon prio=5 os_prio=0 cpu=126000.00ms elapsed=184.00s
   tid=0x00007f1a84032000 nid=0x2a3f runnable
   java.lang.Thread.State: RUNNABLE
        at com.example.pricing.PriceEngine.calculate(PriceEngine.java:118)
        at com.example.pricing.PriceEngine.score(PriceEngine.java:92)
        at com.example.web.CheckoutController.handle(CheckoutController.java:47)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

**What is observed:** the OS reports native TID `10815` consumed roughly 97.3% of one core over the selected `top` window; `10815 = 0x2a3f`; the dump associates `nid=0x2a3f` with a Java thread named `pricing-hot-loop`, state RUNNABLE, and stack at `PriceEngine.calculate`.

**What is not yet concluded:** that `PriceEngine.calculate` specifically consumed all 97.3% CPU over **the entire interval**; the thread could move across multiple methods between captures. Repeat samples/profiler/tracing, or at least check CPU time deltas and stack stability across closely spaced captures.

### 4.3. Name, `#n`, `tid`, and `nid` are distinct

- Name `pricing-hot-loop`: for functional grouping; may duplicate.
- `#42`: Java thread ID/number printed in HotSpot style, **different from OS TID**.
- `tid=0x00007f...`: HotSpot native structure pointer, **never match with LWP**.
- `nid=0x2a3f`: **native TID**, convert to decimal when comparing with Linux tools.
- Line `java.lang.Thread.State: RUNNABLE`: Java VM state, **not a %CPU figure**.
- `cpu=...ms`: thread CPU time printed by the VM, **not a percentage at t0**.

Many JVM internal threads (GC workers, JIT compilers, VM Thread) may appear in a separate section or only carry native info, lacking a Java `Thread` object/Java stack to match easily. Never attribute a native GC thread to application code simply because it does not match typical Java names.

## 5. Understanding `%CPU`, CPU time, and CPU cores properly

### 5.1. CPU time and wall time

**CPU time** is the amount of time a thread actually executes on CPU (user mode plus kernel mode per counter definition). **Wall time** is elapsed real-world time.

A thread running continuously on one logical core for 5 wall seconds can accumulate roughly **5 CPU-seconds**. If it blocks waiting on network for 4.5 seconds and uses 0.5 seconds of CPU, over that same 5-second wall window the thread's CPU usage is roughly 10% of **one core-equivalent**.

A **multi-threaded process** can consume 20 total CPU-seconds in 5 wall seconds = **4 core-equivalents**, or roughly 400% on a 100%-equals-one-core scale. This is completely possible on a host/namespace with at least four effective cores. A **single OS thread** does not run concurrently across multiple CPU cores, so averaging near 100% of one core is the usual upper bound (aside from sampling noise/counter quirks).

### 5.2. Interval normalization formulas

Let:

- `cpuTime0Ns`, `cpuTime1Ns`: cumulative CPU time of **the same thread**, in nanoseconds;
- `wall0Ns`, `wall1Ns`: two monotonic elapsed timestamps from the machine/tool, in nanoseconds.

```text
deltaCpuNs  = cpuTime1Ns - cpuTime0Ns
deltaWallNs = wall1Ns    - wall0Ns

coreEquivalents = deltaCpuNs / deltaWallNs
percentOneCore  = 100 * coreEquivalents

percentOfNProcessors = percentOneCore / N
```

If `deltaCpuNs=450,000,000` and `deltaWallNs=1,500,000,000`:

```text
coreEquivalents    = 0.30
percentOneCore     = 30%
percentOf4Cpus     = 7.5%
```

**N must be explicitly defined:** host logical CPUs, process cpuset CPUs, processor count visible to the JVM, or container quota cores? Different denominators answer **different questions**. Never blindly divide every OS metric by `Runtime.availableProcessors()` as a single universal standard, especially with fractional container CPU quotas or JDK updates changing container awareness.

### 5.3. Non-simultaneous sampling times

With `top`, %CPU reflects **an update interval**; with thread dumps, call stacks reflect **the moment the JVM took the snapshot**. A thread could burn heavy CPU for 2 seconds and then block on I/O right before the dump is taken. You will see a `RUNNABLE`/native read or `WAITING` despite the high CPU sample just prior.

A good sequence:

```text
t0: OS CPU counters + UTC / monotonic timestamp
t1: thread dump near the same window
t2: OS CPU counters + UTC / monotonic timestamp
t3: follow-up thread dump if symptom persists and permitted
```

Do not call two tools “simultaneous” if you have not saved actual timestamps. If a CPU burst lasts only 100 ms, an ad-hoc dump will easily miss it; **JFR/profile sampling** is far better for short attribution.

### 5.4. `ps` lifetime average vs `top` interval rate

| Situation | `ps -L %CPU` | `top -H %CPU` | Interpretation |
| --- | --- | --- | --- |
| Thread was hot 10 min, now idle | May remain high because it averages since start | May be near 0% in recent interval | Not a contradiction |
| Thread just started a hotspot | Lifetime avg reflects short total lifetime | May be near 100% of one core | Needs further observation |
| Process with 4 threads at full CPU | Individual `ps -L` rows vary | Each TID near 100% in Irix mode, aggregate process ~400% | There is no “one thread at 400%” |
| 32-CPU host, 1-CPU pod quota | % may display per tool's definition | One thread saturating core may show ~100% | Pod can still be throttled even if host is lightly loaded |

Do not sum %CPU numbers across different tools/periods to derive an exact ratio. Summing **CPU-time deltas** over the same period for present threads is more consistent, while still accounting for thread lifecycles and missing samples.

## 6. Measuring thread CPU directly from `/proc` on Linux

### 6.1. `/proc/PID/task/TID`

Linux procfs exposes:

```text
/proc/<process-tgid>/task/<native-tid>/
    stat
    status
    schedstat
    ...
```

Where:

- `PID` is the JVM's process/thread-group ID **in the namespace visible to procfs**.
- `TID` is the ID of an OS thread in that group.
- `/proc/PID/task/TID/stat` holds CPU time fields.
- `/proc/PID/task/TID/status` holds thread name, state, and metadata; `NSpid` can assist with PID namespace correlation.
- `schedstat` provides extra scheduler data on supporting kernels/configurations; presence and completeness are not guaranteed everywhere.

Example reading one known thread, **only with verified PID/TID and permissions**:

```bash
cat /proc/12345/task/10815/status
cat /proc/12345/task/10815/stat
getconf CLK_TCK
```

`getconf CLK_TCK` gives clock ticks per second used by `/proc` fields (typically 100 on Linux, yet **must be queried**, not hardcoded). Paths can disappear between reads when a thread exits. Inside a container with a different procfs mount, paths/TIDs may not correspond to the host.

### 6.2. `stat` fields 14/15 are user/system CPU ticks

Per Linux `proc_pid_stat(5)`:

- **Field 14 `utime`**: CPU time in user mode, measured in **clock ticks**.
- **Field 15 `stime`**: CPU time in kernel mode, measured in **clock ticks**.
- **Field 22 `starttime`**: time the task started after system boot, in clock ticks (useful for detecting TID reuse).

In **per-task** `/proc/PID/task/TID/stat`, counters reflect that specific task/thread. Summing `utime+stime` yields cumulative thread CPU time per procfs rules. To convert to seconds:

```text
cpuSeconds = (utimeTicks + stimeTicks) / CLK_TCK
```

To compute **single-core** %CPU from two samples:

```text
percentOneCore =
    100 * ((utime1 + stime1) - (utime0 + stime0))
        / (CLK_TCK * elapsedWallSeconds)
```

Do not use process-wide `/proc/PID/stat` in place of `/proc/PID/task/TID/stat` when targeting an **individual thread**.

### 6.3. Warning on parsing `stat`

`/proc/PID/task/TID/stat` **is not a line you can always split naively on whitespace**: field 2 `comm` is enclosed in parentheses `(...)` and may contain spaces or parentheses. Running `awk '{print $14,$15}'` unconditionally on a thread name containing spaces shifts field indices and yields wrong CPU times.

Structured parsing steps:

1. Find the **last** closing `)` of the `comm` field.
2. The remainder starts at **field 3 `state`**.
3. When splitting that remainder, `utime` (field 14) is **index 11**, `stime` (field 15) is **index 12**, and `starttime` (field 22) is **index 19** using 0-based indexing.
4. Validate field count, valid numeric parsing, and unchanged thread identity.

A production parser should be tested against thread names with spaces, `)` characters, threads exiting mid-sample, and different namespaces; never trust a simple regex built from one clean output.

### 6.4. `schedstat` can help distinguish running vs scheduler wait

When supported by the kernel, `/proc/PID/task/TID/schedstat` provides counters for time spent running on CPU, time spent waiting to be scheduled, and run count (kernel-dependent definitions). These help ask “did the thread want to run but wait for CPU?” better than reading Java state alone.

Do not treat `schedstat` as a single universal source across all Linux distros; availability, permissions, and kernel configs vary. If unavailable, record unavailable and use `top`/`pidstat`/cgroup CPU metrics/JFR accordingly.

## 7. Runnable Java 17+: verifying mapping and exact %CPU from fixed numbers

To verify hex conversion and formulas independent of the host machine, use a program with fixed values. Save file **`NativeThreadCpuMath.java`**:

```java
import java.util.Locale;

public class NativeThreadCpuMath {
    public static void main(String[] args) {
        String nidHex = "0x2a3f";
        long nativeTid = Long.parseLong(
                nidHex.substring(2), 16);

        long userTicks0 = 1_000L;
        long systemTicks0 = 400L;
        long userTicks1 = 1_030L;
        long systemTicks1 = 415L;

        long ticksPerSecond = 100L;
        double elapsedSeconds = 1.5;
        int logicalCpus = 4;

        long deltaTicks = (userTicks1 + systemTicks1)
                        - (userTicks0 + systemTicks0);
        double cpuSeconds = (double) deltaTicks / ticksPerSecond;
        double percentOneCore = 100.0 * cpuSeconds / elapsedSeconds;
        double percentOfFour = percentOneCore / logicalCpus;

        System.out.println("nid.hex=" + nidHex);
        System.out.println("nid.decimal=" + nativeTid);
        System.out.println("delta.ticks=" + deltaTicks);
        System.out.printf(Locale.ROOT, "cpu.seconds=%.2f%n",
                cpuSeconds);
        System.out.printf(Locale.ROOT, "one.core.percent=%.2f%%%n",
                percentOneCore);
        System.out.printf(Locale.ROOT, "four.cpus.percent=%.2f%%%n",
                percentOfFour);
    }
}
```

Compile/run with JDK 17+:

```bash
javac NativeThreadCpuMath.java
java NativeThreadCpuMath
```

**Exact stdout:**

```text
nid.hex=0x2a3f
nid.decimal=10815
delta.ticks=45
cpu.seconds=0.45
one.core.percent=30.00%
four.cpus.percent=7.50%
```

Explanation: 30 user ticks + 15 system ticks = 45 ticks; at 100 ticks/second that is 0.45 CPU seconds in 1.5 wall seconds. This is **30% of one core**, not “30% of the entire host CPU”. With four logical CPUs as the denominator, 30/4 = **7.5% of total four cores**. These numbers are fixed for the math exercise and do not represent real system load.

## 8. Runnable Java 17+ on Linux: measuring `/proc` for the exact TID

The following example is a **read-only** tool running on Linux when `/proc` read permissions are available. It reads CPU ticks of one native TID inside a JVM process at two points, checks `starttime` to guard against TID reuse, and prints %CPU on **one logical core**. The program **does not attach, send signals, or modify the JVM**, though it must still respect access permissions and sampling budgets.

Save file **`LinuxNativeTidCpu.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class LinuxNativeTidCpu {
    record Sample(long userTicks, long systemTicks, long startTicks) {
        long totalTicks() {
            return userTicks + systemTicks;
        }
    }

    private static Sample sample(String processPid, String nativeTid)
            throws IOException {
        Path file = Path.of("/proc", processPid,
                "task", nativeTid, "stat");
        String stat = Files.readString(file);

        // comm is field 2 enclosed in (...), which may contain spaces.
        int endComm = stat.lastIndexOf(')');
        if (endComm < 0 || endComm + 1 >= stat.length()) {
            throw new IOException("Malformed /proc task stat");
        }

        // Everything after ')' begins at field 3: state.
        String[] fields = stat.substring(endComm + 1)
                .trim().split("\\s+");
        if (fields.length <= 19) {
            throw new IOException("Missing /proc task fields");
        }

        long utime = Long.parseLong(fields[11]);    // field 14
        long stime = Long.parseLong(fields[12]);    // field 15
        long start = Long.parseLong(fields[19]);    // field 22
        return new Sample(utime, stime, start);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                "Usage: java LinuxNativeTidCpu PID NID_HEX CLK_TCK INTERVAL_MS");
            return;
        }

        String processPid = args[0];
        String nidHex = args[1];
        if (!processPid.matches("[0-9]+")
                || !nidHex.matches("0[xX][0-9a-fA-F]+")) {
            throw new IllegalArgumentException("Bad PID or NID_HEX");
        }

        String nativeTid = Long.toUnsignedString(
                Long.parseUnsignedLong(nidHex.substring(2), 16));

        long ticksPerSecond = Long.parseLong(args[2]);
        long intervalMs = Long.parseLong(args[3]);
        if (ticksPerSecond <= 0 || intervalMs < 200) {
            throw new IllegalArgumentException(
                    "CLK_TCK must be positive; interval >= 200 ms");
        }

        long wallStart = System.nanoTime();
        Sample first = sample(processPid, nativeTid);
        Thread.sleep(intervalMs);
        Sample second = sample(processPid, nativeTid);
        long elapsedNs = System.nanoTime() - wallStart;

        if (first.startTicks != second.startTicks) {
            throw new IllegalStateException("TID was reused");
        }

        long cpuTicks = second.totalTicks() - first.totalTicks();
        if (cpuTicks < 0 || elapsedNs <= 0) {
            throw new IllegalStateException("Invalid CPU/wall delta");
        }

        double cpuSeconds = (double) cpuTicks / ticksPerSecond;
        double wallSeconds = elapsedNs / 1_000_000_000.0;
        double percentOneCore = 100.0 * cpuSeconds / wallSeconds;

        System.out.println("linux.tid=" + nativeTid);
        System.out.println("cpu.delta.ticks=" + cpuTicks);
        System.out.printf(Locale.ROOT, "one.core.percent=%.2f%%%n",
                percentOneCore);
    }
}
```

On Linux with JDK 17 and example JVM PID `12345`, `nid=0x2a3f`:

```bash
javac LinuxNativeTidCpu.java

# Query actual ticks/second from the real environment.
getconf CLK_TCK

# Replace PID/nid with a verified pair; measure over roughly 1000 ms.
java LinuxNativeTidCpu 12345 0x2a3f "$(getconf CLK_TCK)" 1000
```

**Non-deterministic output**: the thread may exit, counters and %CPU vary with load, or `/proc` permissions may be restricted. A hypothetical output:

```text
linux.tid=10815
cpu.delta.ticks=73
one.core.percent=72.91%
```

`72.91%` is only an example: actual elapsed time can be slightly over or under 1 second, so you cannot compute it precisely from `delta.ticks=73` alone without that run's `elapsedNs`.

Important notes:

- `Sample` is a **Java 17 record**, compilable in a single source file.
- The parser uses `lastIndexOf(')')` so it does not mis-split a `comm` field containing spaces. Indices `11/12/19` are right solely because the substring after the parenthesis starts at field 3.
- The program reads the thread **in the current procfs namespace**; if PID/nid come from another namespace, the path will not exist or could point to the wrong task.
- `starttime` reduces TID-reuse risk, though in real incidents you must still check JVM PID/start time, container identity, and clock source.
- CPU ticks have coarse granularity, and `/proc` reads are not strictly simultaneous with `System.nanoTime()`; overly short sampling intervals increase error.
- If the process/thread exits between samples, `Files.readString` may throw `IOException`: report “thread disappeared” instead of forcing CPU to 0.
- The parser is a learning example; a production collector must handle kernel formats, cgroup versions, permissions, and operational logging/safety standards.
- A native HotSpot GC/JIT thread can still appear in procfs and consume CPU even without a corresponding Java `ThreadInfo`.

## 9. Comparing Linux thread CPU with Java `ThreadMXBean`

### 9.1. ThreadMXBean uses Java thread IDs

In a Java 17 JVM, `java.lang.management.ThreadMXBean` provides:

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory.getThreadMXBean();

boolean supported = mx.isThreadCpuTimeSupported();
boolean enabled = mx.isThreadCpuTimeEnabled();
long javaThreadId = Thread.currentThread().getId();

if (supported && enabled) {
    long cpuNs = mx.getThreadCpuTime(javaThreadId);
    // cpuNs >= 0: cumulative CPU time, in nanoseconds.
}
```

This is a snippet inside a method, not a standalone program. `getThreadCpuTime(id)` accepts a **Java thread ID**, **not** a Linux LWP/native ID. It can return `-1` when unavailable, the thread is dead, or CPU time measurement is disabled. On unsupported JVMs, the method may throw `UnsupportedOperationException`; check capability first. Never enable CPU time monitoring in production by default without measuring overhead and having permission to change runtime state.

### 9.2. Java CPU nanoseconds vs Linux CPU ticks

Two sources can tell the same story in different units:

| Source | Input ID | Unit | Characteristics |
| --- | --- | --- | --- |
| `ThreadMXBean.getThreadCpuTime(javaId)` | Java thread ID | Nanoseconds | JVM management view; only Java threads managed by the API |
| `/proc/PID/task/TID/stat` | Native TID | Clock ticks | Kernel view; includes JVM native/internal threads |
| `ps -L TIME` | Linux LWP | Formatted CPU duration | Lifetime accumulated; good for quick overview |
| `top -H %CPU` | Linux TID in tool namespace | %CPU over update window | Must know Irix/Solaris mode and interval |
| `pidstat -t %CPU` | Linux TID | Interval %CPU | Depends on tool configuration/version |
| HotSpot `Thread.print cpu=...` | Thread header | Usually milliseconds | JVM-specific; not guaranteed on every format |

Do not expect the two counters to match to the nanosecond: how the JVM and kernel sample timestamps/CPU scheduling, sampling time, counter granularity, and native runtime accounting can differ. Compare CPU **deltas** over roughly matching intervals within the same thread lifetime; if ID mapping is missing, never substitute Java ID for Linux TID.

### 9.3. Java 17+ program example for Java ID and CPU time availability

Save **`JavaThreadCpuProbe.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class JavaThreadCpuProbe {
    public static void main(String[] args) {
        Thread self = Thread.currentThread();
        self.setName("cpu-probe-main");

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();

        System.out.println("threadName=" + self.getName());
        System.out.println("javaIdPositive=" + (self.getId() > 0));
        System.out.println("mxThreadIdMatches="
                + (mx.getThreadInfo(self.getId()).getThreadId()
                    == self.getId()));

        boolean supported = mx.isThreadCpuTimeSupported();
        System.out.println("cpuTimeSupported=" + supported);
        if (supported && mx.isThreadCpuTimeEnabled()) {
            long cpuNs = mx.getThreadCpuTime(self.getId());
            System.out.println("cpuTimeNonNegative=" + (cpuNs >= 0));
        } else {
            System.out.println("cpuTime=unavailable");
        }
    }
}
```

Compile/run:

```bash
javac JavaThreadCpuProbe.java
java JavaThreadCpuProbe
```

The first three stdout lines have **deterministic content**:

```text
threadName=cpu-probe-main
javaIdPositive=true
mxThreadIdMatches=true
```

The final lines **depend on CPU time support** and JVM configuration, for example:

```text
cpuTimeSupported=true
cpuTimeNonNegative=true
```

If unsupported or disabled, output may be `cpuTimeSupported=false` and `cpuTime=unavailable` or `cpuTimeSupported=true` and `cpuTime=unavailable`. The program does not print a native TID because Java SE 17 `ThreadMXBean` has no portable API to fetch `nid`. To correlate with OS threads, inspect HotSpot dumps/JFR/appropriate native tools.

## 10. Many native JVM threads also consume CPU

A JVM does not contain only application threads. Components that can consume CPU include:

- GC workers and concurrent GC threads;
- JIT compiler threads (C1/C2) and VM service threads;
- signal dispatchers, native agents, JVMTI/profiler threads;
- JNI/native libraries spawning their own pthreads;
- Java ForkJoinPool, executor, or HTTP worker threads.

A native thread reported hot by `top -H` may have **no matching Java stack** in the dump. This does not prove the OS tool is wrong: it may be a **non-Java thread** belonging to the JVM runtime or JNI. Some HotSpot dumps have a dedicated section for internal threads; formatting varies across builds.

When `nid` maps to a GC worker:

1. Check process CPU and total GC/JIT activity in the same window.
2. Inspect GC logs/JFR events (GC pauses, concurrent phases) and heap/allocation rates.
3. Do not blindly blame high CPU on “Java method X” when the hot thread is a JVM worker.
4. If native profiling is used, verify architecture, symbols, and access permissions; Java dumps do not contain full C/C++ stacks.

### 10.1. “Cannot find nid” can have multiple causes

- The native thread exited before the dump was captured.
- The JVM restarted and the OS TID was reused.
- The dump excludes non-Java threads or the JDK format prints only a subset.
- PID/TID came from a different namespace.
- The OS tool displayed **thread-group ID** instead of LWP because threads mode was not enabled.
- Hex conversion mistake or truncated output lines.
- `jcmd` attached to a different JVM.

Do not pick a numerically close `nid`, or force-match a Java thread with a “similar name” when IDs do not match. Mark it “unmapped” and collect other evidence.

## 11. High CPU yet dump shows WAITING or RUNNABLE in native poll

### 11.1. RUNNABLE does not always burn CPU

`Thread.State.RUNNABLE` in Java is a VM state that can include waiting for OS I/O inside a native method. Composite example:

```text
"selector-0" #70 ... nid=0x2a3f runnable
   java.lang.Thread.State: RUNNABLE
        at java.base/sun.nio.ch.EPoll.wait(Native Method)
        at java.base/sun.nio.ch.EPollSelectorImpl.doSelect(...)
        at java.base/java.nio.channels.Selector.select(...)
```

This is an illustrative sample; exact stacks differ across JDK releases. If `top -H` reports this TID near 0% CPU, there is no contradiction: Java RUNNABLE does not mean the thread is saturating a core.

### 11.2. WAITING does not mean an error

A thread in:

```text
java.lang.Thread.State: WAITING (parking)
    at java.base/jdk.internal.misc.Unsafe.park(Native Method)
    at java.base/java.util.concurrent.locks.LockSupport.park(...)
    at java.base/java.util.concurrent.LinkedBlockingQueue.take(...)
    at java.base/java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

may be a **normally idle** worker. If an OS CPU sample was just high, yet the dump immediately afterward shows WAITING, the thread may have finished its CPU-bound task. To confirm a hotspot, inspect CPU time deltas and multi-sample stacks/JFR rather than guessing “the state is wrong”.

### 11.3. Repeated RUNNABLE in business code

For example, a thread is repeatedly captured at:

```text
java.lang.Thread.State: RUNNABLE
    at com.example.pricing.RuleEvaluator.apply(RuleEvaluator.java:214)
    at com.example.pricing.PriceService.score(PriceService.java:86)
```

If at the same time CPU time of that exact `nid` increases steadily, this is **stronger** evidence of CPU-bound work. Even so, three snapshots in the same method can still result from a fast loop repeatedly passing through it; knowing which function consumes the most CPU requires a sampling profiler/JFR, not just one frame.

### 11.4. Low CPU, high latency

A thread may be:

- blocked on a Java monitor (`BLOCKED`) or AQS lock (`WAITING/parking`);
- waiting on database/network I/O;
- waiting on queues, futures, or downstream limits;
- experiencing CPU throttling/cgroup pressure;
- paused by stop-the-world GC/safepoints;
- blocked in native calls/OS scheduler waits.

Thread dumps and `top -H` provide an initial distinction, yet low CPU does not prove “the application is healthy”. Choose thread dumps, GC/JFR logs, tracing, and cgroup counters based on symptoms.

## 12. Cgroups, Kubernetes, and %CPU normalization

### 12.1. Host CPU differs from container CPU quota

Suppose a host has 32 logical CPUs, a pod has a CPU limit of 1 core, and the JVM uses nearly 100% of one core during an interval:

- Host-wide %CPU ≈ `100/32 = 3.125%` of total capacity;
- pod CPU usage relative to its 1-core limit ≈ `100%`;
- `top -H` Irix mode for one hot thread ≈ `100%` of one core;
- JVM `getAvailableProcessors()` may equal 1 via container awareness or differ if flags/vendors vary.

All four figures can be **simultaneously true**. Therefore every dashboard must state its denominator clearly, not just label it “CPU%”. If a pod has a 500m limit (half a CPU), seeing one thread report 50% of one core cannot be read as “using 50% of quota”: it may be nearly exhausting the 500m quota.

### 12.2. CPU throttling is not in Java thread states

If a cgroup quota is exhausted during a scheduler period, runnable threads can be delayed. `top -H` may display lower usage than expected even as requests slow down. To prove throttling, inspect the exact cgroup:

- cgroup v2: `cpu.max` (quota/period), `cpu.stat` (`nr_throttled`, `throttled_usec` where present);
- cgroup v1: `cpu.cfs_quota_us`, `cpu.cfs_period_us`, and `cpu.stat` in the matching controller;
- orchestrator metrics: CPU throttled periods/time, requests/limits, node contention.

**You cannot assert throttling from `nid` or Thread.State.RUNNABLE alone**. CPU limits, kernel scheduler behavior, CPU affinity/cpuset, and JVM active processor count can all influence results differently.

### 12.3. Rules when capturing from host vs container

1. Pick one perspective as the **primary identity source**: host PID namespace or container PID namespace.
2. Within that perspective, collect matching `ps/top`, `/proc`, and `nid`.
3. If crossing namespaces, record the PID/TID mapping using authoritative container tools/metadata; never guess PIDs by eye.
4. Record container ID, JVM start time, image digest, and host/node identity because PIDs get reused.
5. Keep UTC timestamps, intervals, units, and scope together in a single record.

## 13. End-to-end practical workflow for CPU hotspots

### Step 1 — Verify the exact Java process

Use process/service/container metadata to confirm PID and JVM start time. `jcmd -l` can help, though it does not list every JVM across separate containers. Avoid picking a Java PID merely by a similar name.

### Step 2 — Choose CPU measurement intervals

For example, run `top -H` over 2–3 intervals or `pidstat -t`. Record timestamps, tool/version, Irix/Solaris mode, CPU denominator, and top TIDs. Do not rely on `ps %CPU` lifetime averages if an incident lasted only seconds.

### Step 3 — Convert decimal TID to hex `nid`

```bash
# TID reported by OS tool: 10815.
printf '0x%x\n' 10815
```

Output:

```text
0x2a3f
```

Search for the exact string `nid=0x2a3f` in a thread dump from **the same namespace/JVM**.

### Step 4 — Capture a controlled thread dump

```bash
jcmd 12345 Thread.print -l
```

For JVMs with very many threads, weigh overhead and security. If saving to disk, enforce private permissions and retention. Use `Thread.print -e` if supported by the JVM and extended metadata is needed; check `jcmd PID help Thread.print` rather than guessing options by version.

### Step 5 — Read the exact thread entry

Record name, Java ID if present, `tid` pointer, `nid` native ID, Java state, frames, and locks:

- `RUNNABLE` + business computation frame → **hypothesis** of CPU hotspot;
- `RUNNABLE` + native socket/epoll → may be waiting on I/O;
- `BLOCKED` + `waiting to lock` → lock contention;
- `WAITING` in `ThreadPoolExecutor.getTask` → likely idle;
- JVM GC/JIT native thread → inspect GC/JIT metrics and event logs.

### Step 6 — Capture a CPU delta or second sample

If the symptom persists, collect another CPU interval and nearby dump, comparing **the same TID and JVM generation**. A thread showing the same frame with barely increasing `CPU time` may be waiting; same frame with rapidly rising `CPU time` gives stronger support for a hotspot.

### Step 7 — Gather root-cause evidence

- CPU-bound Java code → JFR Method Profiling, async-profiler, or approved tools; inspect input sizes, algorithms, hot loops.
- GC/JIT → GC logs, JFR GC/Compilation events, heap/allocation metrics.
- JNI/native → native profiling, OS scheduling, libraries/ABI.
- Lock contention → lock owners, `ThreadMXBean`/multi-timestamp thread dumps.
- CPU throttling → cgroup `cpu.stat` and quota.

### Step 8 — Write a verifiable conclusion

A strong conclusion looks like:

> In pod checkout-3, JVM started near 08:12Z; from 08:15:04–08:15:07Z Linux TID 10815 consumed 0.92–0.98 core-equivalents. A dump from the same JVM shows `nid=0x2a3f`, named `pricing-hot-loop`, across multiple snapshots in `PriceEngine.calculate`. JFR samples confirm CPU concentrated in that method. Optimize the pricing path and verify after deployment.

This is a **hypothetical conclusion template**, not a real event. With only a single dump and a single OS interval, say “suggests” rather than “proves”.

## 14. Four illustrative investigation scenarios

### Scenario A — 100% CPU on one JVM worker

`top -H` reports TID 10815 near 100% in Irix mode; the dump has `nid=0x2a3f` with `java.lang.Thread.State.RUNNABLE` and `RuleEvaluator.evaluate` on top. Collecting a few more samples shows rising CPU time and similar stacks. **Strong hypothesis** is CPU-bound Java business code; use JFR/profiler to pinpoint the method actually consuming time before changing algorithms.

**Avoid:** seeing RUNNABLE and immediately declaring it the root cause, or tuning worker thread counts without measuring contention/throughput.

### Scenario B — High process CPU with no matching Java thread

The OS reports a hot TID, yet no matching `nid` appears in Java thread entries. Check JVM internal/GC/JIT threads, native library/JNI threads, snapshot timing, namespaces, and target PID. GC workers can burn high CPU while Java application threads sit WAITING. **Never force-assign a TID to a similarly named Java thread**.

### Scenario C — Brief CPU spike followed by WAITING in dump

In the interval before the dump, OS TID 10815 used 80% CPU. One second later, the thread finished computing and entered `LinkedBlockingQueue.take`. The dump shows WAITING. The two sources do not contradict each other because **their sampling windows differ**. To catch brief bursts, prefer JFR/profiler sampling or application event tracing rather than cranking up dump frequency blindly.

### Scenario D — Pod slows down due to CPU quota

The host has 64 CPUs, and the app has a container CPU limit of 0.5 core. `top -H` on one worker averages near 50% of one core, while latency rises and cgroup `nr_throttled` climbs steadily. This is a strong quota-bottleneck hypothesis, though you must still check traffic/GC/queues and distinguish `CPU requests` from `CPU limits`. Do not read 50% of one core as “the pod still has 50% unused CPU”.

## 15. Common mistakes when correlating native TIDs and CPU

1. **Searching for `tid` instead of `nid`.** HotSpot `tid` is a VM pointer, not the Linux LWP.
2. **Using `Thread.getId()` to look up `top -H`.** Java IDs differ from native TIDs.
3. **Forgetting hex ↔ decimal conversion.** `nid=0x2a3f` matches OS TID `10815`, not 0x2a3f read as decimal.
4. **Joining OS output and a dump from a different PID.** Matching process names alone is insufficient.
5. **Ignoring container PID namespaces.** Host and container can observe different TID numbers.
6. **Joining two JVM generations after a restart.** PIDs/Java IDs/TIDs can be reused.
7. **Treating `ps -L %CPU` as CPU over the last second.** `ps` is typically a lifetime average.
8. **Forgetting `top`'s Irix/Solaris normalization.** One %CPU number can use a different denominator.
9. **Calling `CPU% > 100` a bug on multi-threaded processes.** A process using multiple cores can exceed 100% on a one-core scale.
10. **Adding `user ticks` and `system ticks` while forgetting to divide by `CLK_TCK`.** Ticks are not automatically nanoseconds.
11. **Hardcoding `CLK_TCK=100` for all Linux systems.** Query `getconf CLK_TCK`.
12. **Parsing `/proc/.../stat` by splitting whitespace from the start.** The `comm` field can shift indices.
13. **Ignoring `starttime` when a TID vanishes/reappears.** You may connect two distinct thread lifetimes.
14. **Concluding `RUNNABLE` equals 100% CPU.** Native I/O waits can still report RUNNABLE.
15. **Treating `WAITING` after a CPU spike as proof the OS tool is wrong.** CPU intervals and dumps cover different times/windows.
16. **Picking one top frame and changing code immediately.** One snapshot does not measure CPU share.
17. **Confusing `java.lang.Thread.State` with Linux `STAT=R/S/D`.** The two state systems have different semantics.
18. **Equating process CPU time with a single thread's CPU time.** Totals can include GC/JIT/native threads.
19. **Ignoring JVM internal threads.** GC and JIT can be the CPU source.
20. **Skipping CPU throttling checks just because process %CPU looks modest.** Check cgroup quotas/counters.
21. **Dividing OS %CPU by JVM processor count without verifying scope.** Fractional quotas and affinity distort this.
22. **Believing one `top -H` and one dump can catch a 50 ms burst.** Use appropriate JFR/profiler sampling.
23. **Taking dumps too frequently on an overloaded process.** `Thread.print` incurs thread-count-dependent overhead.
24. **Treating an unmapped TID as a Java bug.** It may be GC/JIT/native or a thread that already exited.
25. **Posting full dumps, process args, or sensitive `/proc` metadata on public issues.** Enforce access/retention policies.
26. **Using interactive `top` in production and accidentally triggering `kill/renice`.** Stay strictly read-only when diagnosing.
27. **Merging samples from different intervals without timestamps.** Causal conclusions easily go wrong.

## 16. Collection and analysis checklist

- [ ] Right service, JVM PID/start, container ID, and PID namespace?
- [ ] Is `top -H` or `pidstat -t` actually showing **threads**, not only processes?
- [ ] Recorded CPU tool version, Irix/Solaris mode, sampling interval, and UTC timestamps?
- [ ] Decimal TID accurately converted to hex `nid=0x...`?
- [ ] Confirmed JVM pointer `tid` is **not** used as Linux LWP?
- [ ] Java ID/`ThreadMXBean` and native ID kept clearly separate?
- [ ] Did the thread in the dump still exist during the OS sample? Checked for TID reuse?
- [ ] Is `%CPU` an interval rate or a lifetime average?
- [ ] Does CPU-time data use the right ticks/ns and actual `CLK_TCK`?
- [ ] If using `/proc`, properly parsed `comm` and verified fields 14/15/22?
- [ ] Understood that one OS thread uses at most roughly one core at a time, while multi-threaded processes can exceed 100%?
- [ ] Understood %CPU normalization by core, host, or container quota?
- [ ] Do thread states and Java frames align with CPU evidence across multiple samples?
- [ ] Checked JVM GC/JIT/native threads if no Java entry matches?
- [ ] Checked cgroup CPU throttling/affinity when latency rises despite low CPU load?
- [ ] Are JFR/native profiler/GC logs needed to confirm a hotspot beyond thread dumps?
- [ ] Collection performed with proper authorization and reasonable frequency without leaking sensitive data?
- [ ] Does the report distinguish observations, hypotheses, and verified conclusions?

## 17. Applied exercises

**Exercise 1 — ID conversion.** `top -H` shows thread LWP 10815 using 87% CPU. The HotSpot dump has fields `#42`, `tid=0x00007f0120001000`, `nid=0x2a3f`. Which field matches Linux LWP? **`nid=0x2a3f`**, because `0x2a3f=10815`; `#42` is the Java number and `tid` is the JVM pointer.

**Exercise 2 — %CPU from ticks.** CPU ticks rise from 1000 to 1075; `CLK_TCK=100`; two reads are 2.5 wall seconds apart. CPU time increased by 0.75 seconds; `percentOneCore=0.75/2.5*100=30%`. On a 4-core host, the share across all four cores is 7.5%. Any label “CPU%” must state its denominator.

**Exercise 3 — Two tools disagree.** `ps -L` reports 65%, `top -H` reports 5% for the same TID. Is one of them definitely wrong? **No**. `ps` shows a lifetime average while `top` shows a recent interval; the thread may have shifted from CPU work to idle. Check mode, interval, and CPU-time deltas.

**Exercise 4 — RUNNABLE yet low CPU.** Dump shows `EPoll.wait(Native Method)` in state RUNNABLE, while `top -H` is near 0%. Is this a bug? **Not by default**. It may be waiting on native I/O; inspect latency/tracing/OS state.

**Exercise 5 — 100% quota yet 3% host.** A host has 32 cores, a pod has a 1-core CPU limit, and the JVM uses roughly one core. Simultaneously, the pod can be near 100% of quota and the host near 3.125% of capacity. Always state source and normalization.

**Exercise 6 — Matching TID after JVM restart.** At 08:00 `nid=0x2a3f` is seen; at 08:10 `nid=0x2a3f` is still present, but JVM start time changed. Is it guaranteed to be the same Java thread? **No**: PIDs/TIDs can be reused; never join two CPU-time/dump series across restarts into one.

## References

- Oracle Java SE 17, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): examples and usage of HotSpot thread dumps, `jcmd Thread.print`, `nid`, JVM troubleshooting.
- Oracle Java SE 17, [`jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, permissions, and impact.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): Java thread IDs and CPU time in nanoseconds, capability flags.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): Java ID, name, state, stack frames, locks.
- Linux man-pages project, [`ps(1)`](https://man7.org/linux/man-pages/man1/ps.1.html): `-L`, `LWP`, `%CPU`, and lifetime CPU utilization.
- Linux man-pages project, [`top(1)`](https://man7.org/linux/man-pages/man1/top.1.html): threads mode `H`, Irix/Solaris normalization `I`, and %CPU per update window.
- Linux man-pages project, [`proc(5)`](https://man7.org/linux/man-pages/man5/proc.5.html): `/proc/PID/task/TID` for individual OS threads.
- Linux man-pages project, [`proc_pid_stat(5)`](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html): fields `utime` (14), `stime` (15), `starttime` (22).
- Linux kernel documentation, [Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, throttling, and container limits.

**Conclusion:** the key step when locating CPU-consuming threads is **converting Linux native TIDs to `nid` in a HotSpot thread dump of the exact JVM**, never confusing them with Java IDs or VM pointers. Afterward, correlate **CPU-time deltas and stack snapshots over matching intervals**, with clear awareness of %CPU normalization, container quotas, JVM internal threads, and collection overhead. A proper mapping points to where to investigate; repeated evidence and profiling establish the cause.