# 4.2 Same-Host Condition, User Permissions, and Attach Capability

> **Java Advance – runtime-diagnostics** · **4. The jcmd Tool**

## 1. Why being able to run jcmd does not guarantee connecting to a JVM

*jcmd* is a diagnostic tool bundled with the JDK that sends **diagnostic commands** to a running Java JVM. Commands can query the VM version, startup configuration, thread dumps, memory info, or control Java Flight Recorder. However, *having jcmd in PATH*, *seeing a PID*, and *attaching successfully* are **three different conditions**.

According to the JDK documentation, jcmd must operate on the **same machine** as the target JVM and, on systems with user/group IDs such as Linux, must have the **matching effective user ID and effective group ID** with which the JVM was started. At the same time, the process must actually exist, be visible in the appropriate namespace, provide a compatible attach mechanism, and be able to respond. Containers, security configurations, JDK version mismatches, process/temporary directory permissions, or a hung JVM can all cause a diagnostic attempt to fail.

This lesson focuses on **execution conditions and how to verify attachability**, without diving deep into analyzing the contents of thread dumps, heap dumps, or JFR.

After this lesson, you will be able to:

1. Explain "same machine" from the perspective of processes, OS permissions, and containers, instead of confusing it with remote HTTP/JMX connections.
2. Identify the right PID and distinguish *jcmd -l* output from attach capability.
3. Compare effective UID/GID between the caller and the target JVM on Linux; recognize permission constraints on Windows.
4. Check JDK tools, JVM attach support, the *DisableAttachMechanism* flag, temp/process namespace setup, and process responsiveness.
5. Diagnose common error messages without opening permissions or making uncontrolled changes to production environments.

## 2. Mental model: four gates to pass through

~~~text
Terminal with jcmd
       |
       v
[1] Right host / PID namespace, found the right process?
       |
       v
[2] User + group + security mechanisms allow access?
       |
       v
[3] Does the JVM support and enable the Attach Mechanism?
       |
       v
[4] Is the JVM responding and can the attach channel exchange data?
       |
       v
jcmd <PID> VM.version succeeds
       |
       v
Only then choose a diagnostic command suited to the goal
~~~

This diagram is a **verification model**, not a step-by-step specification of the attach protocol on every OS. A JVM can pass an earlier gate and fail at a later one: for example, a PID appears in *ps* but the UID does not match; or the user matches but the JVM was started with attach disabled.

| Question | Signals to confirm | If wrong, typically leads to |
| --- | --- | --- |
| Right machine and right process? | Host/container, PID, and command line match the application | PID not found, wrong PID selected, process not found |
| Right identity / authorized? | Effective UID/GID, OS permissions, security policies | Permission denied, Operation not permitted |
| Compatible tool and mechanism available? | JDK tool, actual JVM, compatible version, attach enabled | Command not found, attach unsupported/disabled |
| JVM responsive? | Process is alive and responding; attach communication path is accessible | Timeout, unable to open socket/file, target does not respond |

**Distinction rule:** *process visibility* is not yet *permission*, and *permission* is not yet *attach success*. Do not conclude "the JVM is not running" just because a listing command did not find it.

## 3. What does "same machine" mean?

*jcmd* is primarily a **local diagnostic tool**. When running:

~~~bash
jcmd <PID> VM.version
~~~

the tool locates the target JVM process and uses the local attach channel of the OS/JVM. This is **not** an HTTP/JMX API requiring only a hostname, port, and password. There is no standard syntax like "jcmd server.example.com:1234 VM.version" to attach from a laptop to a JVM on another machine.

If the JVM runs on a remote server, the accurate phrasing is: **log in to an authorized machine (for example via SSH), then run jcmd on that machine**. With containers/Kubernetes, the tool must execute in an environment where PIDs, permissions, and the attach channel are compatible with the target JVM—typically the application container or a properly configured diagnostic environment.

| Case | Satisfies "same machine"? | What else must be checked? |
| --- | --- | --- |
| Java and jcmd run on same host, same user | Usually yes | PID, group, JDK/JVM, attach enabled, JVM responding |
| Laptop runs jcmd while Java is on a remote machine | No | Run the tool from the remote host/appropriate environment |
| SSH to the host running Java and invoke jcmd there | Yes at the host level | User/group, namespace, binary, security |
| Java in Docker, jcmd run on the host | Same physical host but may have **different namespaces/mounts** | PID seen from each side, attach channel, UID/GID, permissions |
| Java in a container, jcmd run **inside that same container** | Usually the simplest path | Whether the container image has JDK/jcmd; whether user matches |
| jcmd in another pod/container | Cannot attach by default | PID namespace, temp/mount namespace, user, permissions; requires proper debug design |

Do not conclude "same Kubernetes node" means jcmd can definitely attach. Pods usually have separate process namespaces, and even containers within the same pod do not by default have full permissions or paths to attach across containers.

## 4. A PID is the identity of **a process in a specific namespace**

### 4.1 Listing JVMs with jcmd

Basic command:

~~~bash
jcmd -l
~~~

In a normal environment, output may look like:

~~~text
12345 com.example.Main
12501 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

The actual PID numbers and names **vary per run**. *jcmd* can appear in its own output because it also runs on a JVM. Cross-check the main class/JAR name, command line, start time, and the service you intend to inspect before picking a PID.

According to official JDK 21 guidance, **jcmd -l does not list JVMs running in separate Docker processes** via normal listing; use tools like *ps* to identify the PID when needed. Therefore:

- Not seeing a JVM in *jcmd -l* **does not prove the JVM is dead**.
- Seeing a PID in *jcmd -l* **does not guarantee** the attach command has permission and will succeed.
- The PID on the host and the PID inside a container **can differ**. For example, the JVM may be PID 1 inside the container while having a different PID when viewed from the host.
- A PID can be reused after a process terminates; do not grab an old PID and run a high-impact command.

### 4.2 Confirming the PID via the OS

On Linux, in an environment where Java is visible:

~~~bash
ps -ef
~~~

If you already have a candidate PID, inspect it specifically:

~~~bash
ps -o pid,ppid,euid,egid,args -p <PID>
~~~

Record PID, PPID, EUID, EGID, and the command string. *args* may contain secrets if the application passes tokens, passwords, or sensitive URLs on the command line; avoid copying it verbatim into uncontrolled locations.

In a container, if the application runs as PID 1, that may be **PID 1 inside the container**, not PID 1 of the host. Run checks and *jcmd* within **the same PID namespace** or clearly understand PID mapping across namespaces.

## 5. User permissions: effective UID/GID, not just display name

In the Linux/Unix model, the shell user is who **actually invokes jcmd**; the JVM user is the identity of the running Java process. The JDK 21 jcmd documentation requires **the same effective user and group identifiers**. This is stricter than assuming "same Linux group is enough" or "sudo/root can always attach".

### Checking the current shell

~~~bash
whoami
id
id -u
id -g
~~~

Hypothetical example:

~~~text
appuser
uid=10001(appuser) gid=10001(appgroup) groups=10001(appgroup)
10001
10001
~~~

The snippet above is **illustrative**, not fixed output on every machine. *id -u* and *id -g* during normal execution describe the corresponding effective identities; in cases where real and effective IDs differ, carefully inspect the process attributes.

### Checking the target JVM

~~~bash
ps -o pid,euid,egid,args -p <PID>
~~~

If the JVM has effective UID=10001, effective GID=10001, while the shell running jcmd has UID=1000, GID=1000, that is a **mismatch to investigate first**. Run the command as the appropriate operational user per authorized procedure, for example on a system that permits switching to *appuser*:

~~~bash
sudo -u appuser -- jcmd <PID> VM.version
~~~

This command is only a conditional example; verify **the effective group as well** after switching users, system policy permissions, and the JDK path. Do not treat *sudo -u* as a guaranteed trick to fix every error or attempt unauthorized privilege escalation in restricted environments.

**Supplementary Linux groups** may grant access to other resources, but they do not replace the effective identity condition described by jcmd. SELinux/AppArmor, seccomp, procfs restrictions, container capabilities, and service policies can restrict the operation even when the user appears identical. Root privileges, if present, also do not automatically resolve PID/mount namespaces, disabled attach, or an unresponsive JVM.

### On Windows

Windows does not use POSIX UID/GID in the same way. Check the account running the Java service, the account invoking jcmd, process access permissions, and privilege/elevation level. Running the terminal under the same account/appropriate security context is usually the first check. Do not extrapolate from Linux rules that matching *whoami* is sufficient across all Windows services/sessions.

### Why does this matter?

Diagnostic commands can expose command-line arguments, configuration details, stacks, memory data, or create dumps containing sensitive data. Attach permission control is part of the security boundary; do not "fix" errors by broadly disabling security policies.

## 6. Is jcmd present in the image: JDK, JRE, and PATH

Running jcmd requires the **jcmd binary** in the tool execution environment, normally part of the JDK. Many minimal, JRE-only, or distroless runtime images **do not include** this tool. A JVM can still run the application normally without *jcmd* in the container.

Check:

~~~bash
java -version
jcmd -h
~~~

In Linux/macOS shells with *command*:

~~~bash
command -v java
command -v jcmd
~~~

If jcmd is not on PATH but a JDK is installed, you can use the full path to *bin/jcmd* of the appropriate JDK. However, do not treat copying a binary from an incompatible JDK into the image as a standard practice.

**Version compatibility:** the *java* command documentation notes that JDK tools (including jcmd, jmap, jstack, jinfo) are **unsupported** when using a tool from one JDK version to diagnose a JVM of another version. Therefore, the safe choice is to use **jcmd from the JDK matching the target JVM**; check *java -version* of both the tool and the running Java process, not just the default Java on PATH.

If the target is a VM or implementation that does not support HotSpot diagnostic commands, a failed attach does not mean the application is broken. Verify the VM name, version, implementation, and vendor documentation.

## 7. Attach Mechanism must be enabled and the JVM must respond

HotSpot has the option:

~~~text
-XX:+DisableAttachMechanism
~~~

When a JVM is started with this flag, the mechanism allowing tools to attach to the JVM is disabled. In that case, running with the right user/host/PID still **will not make jcmd attach succeed**. The flag is set at startup; if operational policy allows changing it, plan a configuration change and a controlled restart. Do not flip flags in production just to grab one snapshot.

Distinguish easily confused concepts:

- **DisableAttachMechanism:** directly restricts the tool attach mechanism.
- **EnableDynamicAgentLoading:** relates to dynamically loading Java/JVMTI agents; does not mean "enabling all jcmd commands".
- **JEP 451 (JDK 21):** warns when dynamically loading an agent; **not** a notice that read commands like *VM.version* are disabled.
- **-Djdk.attach.allowAttachSelf:** configuration related to self-attach in certain API cases; not a general fix for *jcmd* running as an external process.

A JVM with attach enabled that is severely congested, experiencing long pauses, or unable to service requests in time can cause commands to fail with timeouts. A timeout error is **insufficient evidence** to conclude that DisableAttachMechanism is enabled.

The attach mechanism on Linux can involve temporary files/sockets and paths viewed across different namespaces/mounts. If the tool cannot see the communication channel due to container/temp filesystem setup or an environmental issue, connection can fail even though the process exists. Do not arbitrarily delete sockets, clear temp directories, or open permissions on all of */tmp* in production: such actions can affect the JVM and other applications.

## 8. Low-intrusion verification workflow: from PID to VM.version

Follow the sequence strictly to avoid testing high-overhead commands before confirming the target.

### Step 1 – Identify the environment

Record:

- Actual host or node/container/pod running the application.
- OS, JDK/JVM version, and intended *jcmd* path.
- Effective account of the JVM, account of the terminal, and corresponding groups.
- Timestamp and instance/version experiencing symptoms.

### Step 2 – Identify the exact PID

~~~bash
jcmd -l
ps -ef
~~~

In environments lacking *ps* or *jcmd*, use a valid process observation method instead of assuming Java is dead. Match the command line to the target application; if the process recently restarted, get the new PID.

### Step 3 – Verify user/group on Linux

~~~bash
id
ps -o pid,euid,egid,args -p <PID>
~~~

If there is a mismatch, request/apply appropriate operational authorization to run from the same effective identity. Do not escalate privileges against policy.

### Step 4 – Test the simplest attach command

~~~bash
jcmd <PID> VM.version
~~~

*VM.version* is a state-reading check, typically lighter than a thread dump or heap dump. A successful result begins with a header containing the target PID and VM/version info; exact contents vary by JDK and vendor.

Next, list diagnostic commands supported by the **target JVM itself**:

~~~bash
jcmd <PID> help
~~~

You can query the syntax of a specific diagnostic command:

~~~bash
jcmd <PID> help Thread.print
~~~

Once attachability is confirmed and you have a clear diagnostic goal:

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
~~~

*VM.flags* shows actual VM configuration; *VM.command_line* may expose sensitive parameters, so only store/export it within allowed security boundaries. Only then consider *Thread.print*, *JFR.start*, or *GC.heap_dump* depending on the issue and impact level; "attachable" does not mean every command is free or read-only.

### Step 5 – Record results and limitations

A good report should include the timestamp, PID, JVM version, user/group context, container/namespace, diagnostic command, verbatim outcome/error **with sensitive data redacted**, and why attachability was confirmed or not. Do not blame permissions if the actual issue is a paused JVM or incompatible JDK.

## 9. Java 17+ Lab: run a JVM and attach properly on the same host

The lab below creates an application that **stays alive long enough** to test *jcmd*. Run on a development machine you control, with JDK 17+ containing *javac*, *java*, and *jcmd*. No external libraries required.

Create file **JcmdAttachDemo.java**:

~~~java
public final class JcmdAttachDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("Attach demo ready");
        Thread.sleep(90_000L);
    }
}
~~~

Compile:

~~~bash
javac JcmdAttachDemo.java
~~~

In **terminal A**, run:

~~~bash
java JcmdAttachDemo
~~~

Exact stdout of the program right at startup:

~~~text
Attach demo ready
~~~

The JVM continues sleeping for about 90 seconds and then exits normally without printing anything else. If the process is stopped early with Ctrl+C, termination depends on the OS, though the first line remains the application's output.

In **terminal B** (same host, same effective account, and matching JDK) while the JVM is alive:

~~~bash
jcmd -l
~~~

Find the line containing *JcmdAttachDemo* and its PID. Illustrative example where **PID is not fixed**:

~~~text
12345 JcmdAttachDemo
~~~

Next, replace *<PID>* with the exact PID observed:

~~~bash
jcmd <PID> VM.version
jcmd <PID> help
~~~

If the first command succeeds, you have verified you can communicate with an actual running JVM in that context. The content of *VM.version* is not fixed because it depends on JDK/vendor/build; do not expect identical output strings across different machines.

**Experiment distinguishing listing from attaching (lab only):** stop the program, restart with attach disabled:

~~~bash
java -XX:+DisableAttachMechanism JcmdAttachDemo
~~~

Re-run *jcmd -l* and *jcmd <PID> VM.version* while the program is alive. Process listing behavior may vary, but attaching to a JVM with the attach mechanism disabled **must fail**. This demonstrates that "finding the PID" and "attaching successfully" are not equivalent. Do not run attach-disabling experiments on real applications outside authorized scope.

### Why can this code run on Java 17?

This is plain Java using *public static void main*, *System.out.println*, and *Thread.sleep(long)*, with no preview APIs or dependencies. The file name matches the public class name. The code only keeps the JVM alive to test attachability; it **does not implement jcmd itself** or alter process permissions.

## 10. Docker: viewing PIDs and users from the right side

In an image containing JDK tools, for example a container named *my-java-app*, the usual investigation path is executing commands **inside the application container**:

~~~bash
docker exec my-java-app sh -c 'id'
docker exec my-java-app sh -c 'ps -ef'
docker exec my-java-app jcmd -l
~~~

If the image lacks *sh*, *ps*, or *jcmd*, the commands will report missing tools; this does not indicate the JVM is not running. Minimal production images may contain only the runtime and application binaries. In that case, use an ops-approved diagnostic path (a suitable debug image, an environment sharing the required PID/permission/temp setup, or existing telemetry).

Some Java apps run directly as PID **1** in a container, though not always: the entrypoint may include a shell/tini or multiple processes. Confirm with *ps* if available, rather than assuming PID 1.

Once you know the PID inside the container (e.g., PID 1 after verification) and the user matches:

~~~bash
docker exec my-java-app jcmd 1 VM.version
~~~

**Important condition:** the user executing *docker exec* depends on the image/container configuration and might not match the user that actually launched Java; check *id* and process EUID/EGID. Docker provides the *--user* option if you have the required operational permissions, but switching users must match the effective identity and not violate container policies.

**Avoid two false conclusions:**

1. Seeing Java with PID 24189 on the host and PID 1 inside the container does not mean two different JVMs; it can be **the same process numbered differently across PID namespaces**.
2. Being able to run *docker ps* or *docker exec* does not prove the diagnostic tool has the same user, matching JDK, or a working attach channel.

When forced to diagnose from the host or a debug container, you must understand PID mapping, OS permissions, *procfs*, mount namespaces, and where the JVM creates its attach channel. Do not broadly advise mounting */tmp* across containers or opening file/socket permissions; evaluate specifically according to security configurations.

## 11. Kubernetes: checking the right pod, container, and namespace

In Kubernetes, *kubectl* runs on your workstation, while the following command executes the program **inside the selected container**:

~~~bash
kubectl exec -n <namespace> <pod> -c <container> -- jcmd -l
~~~

To request *VM.version* after verifying the PID:

~~~bash
kubectl exec -n <namespace> <pod> -c <container> -- jcmd <PID> VM.version
~~~

The placeholders *<namespace>*, *<pod>*, *<container>*, and *<PID>* must be replaced with real values. Before running, verify the right cluster/context, namespace, pod, and container; a pod may contain multiple containers or have just restarted. A PID from an earlier run may no longer exist.

If *kubectl exec* reports jcmd not found, that is an **image tooling issue**, not proof that the target is hung or attach is broken. If the PID is not visible, check namespace/process visibility; if it fails with permission denied, check effective user and container policies.

**A debug sidecar/ephemeral container is not an automatic guarantee:** a new container may have *jcmd* yet fail to share the PID namespace or temp/mount namespace with Java, or run as a different user. Use a platform-team-managed debug approach with authorized access and the proper context, rather than adding high capabilities or enabling privileged mode in production.

Running *jcmd* inside a container does not require opening a new HTTP endpoint or management port. It is a local operation on the process, though still governed by Kubernetes RBAC, exec permissions, and OS policies.

## 12. Diagnosing common errors by symptoms, not guesswork

Exact messages depend on the JDK, OS, distro, and deployment. The table below provides **triage guidance**, without claiming every error has a single cause.

| Symptom or message | Plausible hypothesis | Next verification check |
| --- | --- | --- |
| *jcmd: command not found* | Missing JDK bin/jcmd or wrong PATH | Check binary, image, JDK version |
| *jcmd -l* does not show Java | Different container/PID namespace; process discovery permissions; JVM excluded from listing mechanism; process exited | *ps* in the right environment, PID/timestamp/container |
| *No such process*, *process not found* | Wrong PID, process restarted/exited, or different namespace | Retrieve new PID, compare command line and timestamp |
| *Permission denied* / *Operation not permitted* | EUID/EGID mismatch or security mechanism blocking operation | *id*, *ps -o euid,egid*, OS/container policy |
| *AttachNotSupportedException* | JVM does not support provider, attach disabled, wrong implementation/version, or incompatible environment | Verify JVM/JDK, startup flags, provider, PID |
| *Unable to open socket file* / *target does not respond* | Attach/temp channel inaccessible, different namespace, target overloaded/unresponsive, or attach restricted | Cross-check process state, mount/temp, timestamps, logs; do not delete sockets arbitrarily |
| *Unknown diagnostic command* | Command does not exist in that JVM/version or wrong name/syntax | *jcmd <PID> help*, *help <command>* |
| Light read commands work, heap dump/JFR fails | File write permissions/path, resource/cost constraints, command-specific config | Read command help, disk capacity, path seen by JVM, permissions |
| Command works on host but not in container | Different binary/user/PID/mount namespace, minimal image | Compare same VM, effective identity, namespace, and tooling |

### Ordered interpretation

**Case A – jcmd -l does not see the target:**

1. Check whether the Java process is alive in the right host/container.
2. Confirm PID namespace and listing scope; with Docker, *jcmd -l* has documented limitations.
3. Check user context and tool version; do not raise privileges just to "see more".
4. Only when you have the right PID and right permissions should you try *jcmd <PID> VM.version*.

**Case B – PID is visible, but attach reports permission denied:**

1. Compare effective UID/GID of the shell and Java.
2. Check OS policy, container security context, process permissions, and temp path if needed.
3. Use the matching authorized identity rather than relaxing system-wide permissions.
4. Repeat a lightweight read command, saving the verbatim error and timestamp if it still fails.

**Case C – UID/GID match, but attach times out:**

1. Verify the right PID/JVM/version.
2. Check whether the JVM has attach enabled from startup/deployment configuration.
3. Inspect process state, CPU/GC/pauses, and signs of unresponsiveness during that window.
4. Check for namespace or temp/mount isolation differences.
5. If the JVM is truly hung, consider gathering info via telemetry, logs, or other OS mechanisms approved by operations. Do not treat every timeout as proof of a JVM deadlock.

## 13. Commands have permission, but their impact levels differ

Once attached successfully, some commands mainly read information while others incur overhead or alter runtime state:

| Group | Examples | Notes |
| --- | --- | --- |
| Verify attach | *VM.version*, *help* | Usually a lightweight, easily observed starting point |
| Configuration info | *VM.flags*, *VM.command_line* | May expose sensitive arguments |
| Thread observation | *Thread.print -l* | Cost scales with thread count; output can be large |
| Time-based observation | *JFR.start*, *JFR.dump*, *JFR.stop* | Manage duration, disk space, output location, overhead |
| Heap/memory dump | *GC.heap_dump* | Can have significant impact, consume disk, and contain sensitive data |
| Configuration or agent changes | *VM.set_flag*, *JVMTI.agent_load*, and other admin commands | Can alter state or open powerful capabilities; require separate review/authorization |

Do not test a heavy command on a production JVM just to check "whether attach works". *VM.version* is a more appropriate confirmation for the goal of this lesson. In particular, file-writing commands can create files at **paths seen by the target JVM**, not necessarily paths of the terminal/debug container invoking the command.

If a command involves sensitive data (heap, args, stacks), restrict viewing permissions, storage location, retention period, and sharing. Do not move real process contents to public places just to get debugging help.

## 14. Separating attach errors from command errors

An investigation must pinpoint the exact layer of failure:

~~~text
jcmd cannot run at all?
  -> check terminal binary/PATH/JDK.

jcmd runs but does not see the JVM in the list?
  -> check PID, container/namespace, process discovery permissions.

jcmd <PID> VM.version fails?
  -> check if PID is alive, EUID/EGID, attach enabled,
     JDK/JVM compatibility, OS policy, attach channel, JVM responsiveness.

VM.version succeeds, but another command fails?
  -> basic attach already works; check command help, syntax,
     command-specific permissions and resources, output path.

Command runs, but data is for the wrong target?
  -> check whether you selected the right process, version, container, timestamp.
~~~

**Important:** If *VM.version* succeeds, you have evidence that diagnostic connectivity to the target process works at that moment; it does not mean every diagnostic command will succeed at all times. If *VM.version* fails, you cannot deduce the exact root cause from a single error alone; you must still rely on the error type and corroborating evidence.

## 15. Three practical scenarios requiring reasoning

### Scenario 1 – Java runs as appuser, terminal logged in as deployer

- JVM effective UID/GID is 10001:10001.
- The terminal invoking *jcmd* has 1000:1000.
- *ps* can see the JVM, but *jcmd <PID> VM.version* reports a permission error.

**Hypothesis:** effective identity mismatch. **Verification:** compare *id*, *ps -o euid,egid*, OS permissions; choose the authorized matching user and re-run the read command. Do not change ownership of the entire app or apply broad chmod.

### Scenario 2 – JVM runs as PID 1 in Docker

- *docker exec* shows Java at PID 1.
- On the host, *ps* shows a different PID; *jcmd -l* on the host does not list Java normally.
- Inside the container there is no jcmd due to a minimal runtime image.

**Hypothesis:** not a missing JVM, but a different PID namespace and missing tooling. **Handling:** confirm the actual PID and choose an authorized debug path with a compatible JDK, matching user/namespace/temp. Do not arbitrarily download/copy incompatible tools into a traffic-serving container.

### Scenario 3 – Right PID, right user, yet only one JVM fails to attach

- Two HotSpot processes run on the same host and user.
- JVM A accepts *VM.version*; JVM B does not even though the PID is alive.
- B's startup configuration includes *-XX:+DisableAttachMechanism*.

**Strongly evidenced hypothesis:** B disabled the attach mechanism at startup. **Action:** document the diagnostic limitation, switch to available telemetry/logs; if attach needs to be enabled, update configuration and roll out through the approval process. Do not expect switching users or raising privileges to override this VM flag.

## 16. Checklist for incident responders

Before using jcmd on a Java runtime:

1. Am I on the right machine or running the command **in the right host/container** hosting the target JVM?
2. Is the PID for the right process, in the same namespace, and still alive? Have I verified command line/instance/version?
3. Does *jcmd -l* have limitations in this container environment? Have I used *ps* or an appropriate process discovery method?
4. Do Java and jcmd belong to the same implementation family and compatible JDK version?
5. Does the caller's effective UID/GID (or Windows security context) satisfy the attach condition?
6. Does the JVM have the Attach Mechanism enabled? Is *-XX:+DisableAttachMechanism* in the startup configuration?
7. Do process, procfs, filesystem/temp, and container security policies allow the attach channel?
8. Is the JVM overloaded, experiencing long pauses, or unresponsive at the time of the operation?
9. Have I tried **jcmd <PID> VM.version** and **help** before high-cost commands?
10. Have I recorded timestamp, PID, command, result/error, version, and remaining uncertainties?

A verification report should use the following short format:

~~~text
Target host/container:
JVM PID (namespace):
JVM Java version / implementation:
jcmd path / version:
Caller effective UID/GID (if Linux):
Target effective UID/GID (if Linux):
Attach enabled / startup flags evidence:
Command: jcmd <PID> VM.version
Timestamp/timezone:
Result: success / exact error
Hypothesis and next safe check:
~~~

Conclusions should stay strictly within the bounds of evidence. "Permission denied due to UID mismatch" requires identity evidence; "Attach disabled" requires JVM configuration evidence; "not seen in jcmd -l" is **not enough** to confirm the JVM has stopped.

## 17. Self-check questions

**1. Why does jcmd -l run successfully yet fail to show Java inside Docker?**  
Because jcmd's listing capability has limitations with JVMs in isolated Docker processes, and namespaces/permissions can alter observation scope. You need to verify the process using OS tools in the right environment; do not equate "not listed" with "does not exist".

**2. Is being on the same host and seeing the PID enough to attach?**  
No. You also need matching effective user/group, JVM attach support and enablement, JDK/JVM compatibility, OS/container policies, an accessible attach channel, and actual responsiveness.

**3. Does *sudo* always solve Permission denied?**  
No. You must ensure the right identity and permissions; namespaces, security policies, or disabled attach can still block it. Only switch users/escalate privileges with operational authorization.

**4. If a JVM has -XX:+DisableAttachMechanism, will running jcmd under the exact UID succeed?**  
No, because the attach mechanism has been disabled. You must adjust startup configuration through the proper process if you want to allow attach, or use other observation channels.

**5. Does JEP 451 make jcmd VM.version unusable on JDK 21?**  
No. JEP 451 addresses dynamic agent loading and warns when an agent is loaded; it does not mean read-only diagnostic commands are disabled.

**6. What does it mean if VM.version succeeds but GC.heap_dump fails to write a file?**  
Basic attach already works. You need to inspect conditions specific to **that command**, such as path/disk capacity/permissions from the JVM's perspective and resource impact, before blaming attach.

**7. Does a command timeout prove a JVM deadlock?**  
No. A timeout can be caused by a long pause, resource pressure, attach/temp/namespace channel issues, blocked mechanisms, or an unresponsive JVM during that window. Additional evidence is required.

## 18. Official documentation for reference

- Oracle JDK 21, **The jcmd Command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21, **Diagnostic Tools**: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21, **The java Command**, section *Advanced Serviceability Options*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- OpenJDK **JEP 451: Prepare to Disallow the Dynamic Loading of Agents**: https://openjdk.org/jeps/451

Consult documentation for the exact JDK version in use, as command lists, flags, and mechanisms can differ across VMs.

## Takeaway

**jcmd is a local diagnostic path from a tool to a specific JVM.** To attach successfully, you need the **right host/namespace and PID**, the **right effective identity/permissions**, a **compatible JDK/JVM**, an **enabled Attach Mechanism**, and a **responsive JVM and communication channel**. *jcmd -l* only assists process discovery; the simplest direct verification check is *jcmd <PID> VM.version*. Always separate **process discovery**, **permissions**, **attach**, and **diagnostic command** failures to avoid fixing the wrong layer or increasing operational risk.