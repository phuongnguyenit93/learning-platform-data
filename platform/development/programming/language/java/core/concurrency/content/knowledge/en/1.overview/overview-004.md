# Latency, throughput, responsiveness, and utilization in Java concurrency

## Goals and context

When evaluating a Java program running multiple concurrent tasks, “fast” can mean several different things: a single request finishes early, the system processes many requests per second, users perceive the application as responding promptly, or CPUs/threads are used efficiently. Those four perspectives are **latency**, **throughput**, **responsiveness**, and **utilization**. They are related to one another, but they are not interchangeable.

After this lesson, you will be able to:
- Define measurement boundaries and units for each metric, distinguishing queue wait time from execution time.
- Read median, p95, and p99, and recognize why an average cannot describe the worst experience of a subset of users.
- Explain why increasing the thread count can increase throughput for I/O-bound tasks but may not help CPU-bound tasks—and can even worsen latency.
- Relate work in progress, completion rate, and response time using Little’s Law, and recognize when a system is approaching overload.
- Measure these metrics yourself in Java using `System.nanoTime()` and `ExecutorService`, and interpret the numbers within the limits of the experiment.

**Scope:** general Java/JVM concurrency mechanisms, including threads, executors, queues, CPU, and I/O-bound waiting tasks. Spring-specific mechanisms or configurations belong to another chapter.

## 1. A timing model before measuring

Suppose a task is submitted to the system at time `t0`, starts being processed by a worker at `t1`, and completes at `t2`.

~~~text
Task arrives/submitted                  Starts running               Completes
t0                                    t1                           t2
|-------------- queue wait ------------|--------- execution ---------|
|---------------- latency measured at this boundary -----------------|
~~~

If we only consider the path from submission to completion:
- **Queue wait:** `t1 − t0`. The task has been accepted, but no worker is executing it yet.
- **Execution elapsed time:** `t2 − t1`. This can include **actual CPU execution**, lock waiting, I/O waiting, `sleep`, OS scheduler preemption, etc. Therefore, “execution elapsed” does not mean “CPU time”.
- **Task latency:** `t2 − t0 = queue wait + execution elapsed time`.

For example, if a task waits in a queue for 80 ms and then takes 40 ms to complete, the latency measured from submission is **120 ms**, even though the worker’s execution segment is only 40 ms. If measured from the caller’s side over a network, latency can also include data transfer, proxies, serialization, and client-side time. Always state clearly **where measurement starts, where it ends, and what is being measured**.

For multi-stage tasks (enqueue → call another service → wait for a lock → compute → send result), you should measure both end-to-end latency and per-stage duration. Placing a timer only around the processing call after dequeuing the task can hide the real bottleneck.

## 2. Latency: how long does one piece of work take?

**Latency** is the time it takes for a single unit of work to complete, measured across a stated boundary. The unit is typically ms or µs. When saying “100 ms latency”, you need to know which call it is, whether it is client-side or server-side, whether queueing is included, and whether it covers only successes or also errors/timeouts.

Common statistics:

| Metric | Meaning | Things to remember |
| --- | --- | --- |
| Mean (average) | Total time / sample count | Easily pulled up by a few very slow requests |
| Median / p50 | About 50% of samples have latency no greater than this value | Describes the typical experience |
| p95 | About 95% of samples do not exceed this value | Highlights the slow tail more clearly |
| p99 | About 99% of samples do not exceed this value | Important for rare but bad experiences |
| Max | The slowest sample in the measured set | Sensitive to sample size and noise |

For example, suppose there are 100 requests: 95 complete in 20–40 ms and 5 take 800 ms. The average might still look acceptable for some targets, but p99 will be around 800 ms. A UI or a chain of multiple calls is easily affected by these latency spikes.

**Percentiles depend on the sample set and how they are computed.** With small sample sizes, p99 is very unstable; tools using different interpolation or histogram algorithms can produce different numbers. Do not compare two p99 values if the measurement windows, request sets, error handling, or percentile algorithms differ. Percentiles also cannot be added directly: the p95 of step A plus the p95 of step B is not necessarily the p95 of the entire request.

To analyze high latency, separate at least: **time spent in queue**, **lock/synchronization wait time**, **I/O wait time**, and **actual execution time**. Pauses from GC, CPU scheduling, and startup/JIT can also create latency spikes.

## 3. Throughput: how much work gets completed?

**Throughput** is the amount of work completed per unit of time—for example, task/s, request/s, message/s, or MB/s:

~~~text
throughput = completed work items in interval / interval duration (seconds)
~~~

If 600 tasks finish in 10 seconds, the observed throughput is 60 task/s. Be explicit about whether “completed” means all outcomes, only successful outcomes, or actual bytes transferred. Always report **error rate** and **timeout rate** alongside it, because throughput that counts failed requests can give a misleading impression of useful serving capacity.

Distinguish between:
- **Arrival rate / offered load (λ):** number of tasks entering per second.
- **Completion throughput (X):** number of tasks finishing per second.
- **Capacity:** the rate the system can sustain while meeting chosen latency and error-rate targets under a defined workload and configuration.

In steady state—with no dropped tasks and no long-term queue growth—the arrival rate is close to the completion rate. When 120 request/s continuously arrive but only 90 request/s finish, the backlog grows by about **30 requests per second** on average until rejection, timeouts, task drops, or a load change occurs. A short measurement window can show high throughput by draining an existing backlog; it does not prove sustained capacity.

Throughput measurements must state the work size: 10 cache reads are not equivalent to 10 disk queries or 10 heavy encryption operations. Comparing task/s between two systems with different inputs is usually meaningless.

## 4. Responsiveness: how promptly does the system respond?

**Responsiveness** describes how quickly and consistently a system reacts to interactions or new signals. It is related to latency, but also includes **time to first response**, smoothness, and the ability to keep serving while a long-running job is still in progress.

Examples:
- A Java desktop UI receives a command and runs heavy processing on the UI thread: the total job may finish in 2 seconds, but the window freezes for the entire 2 seconds. Moving the work to a worker and posting progress updates makes the UI more responsive, even if total completion latency does not decrease.
- A service handling a long-running job can quickly acknowledge “received” and finish later. **Time to first acknowledgment** is low, while **end-to-end completion latency** remains long. Never relabel acknowledgment time as completion time.
- When cancelling a task or shutting down the system, workers that properly check cancellation/interrupt flags usually improve responsiveness to control operations, even if normal-case throughput stays unchanged.

Responsiveness has no single formula that fits every product. Choose a metric that represents the real promise: **time to first response**, event-handling delay, UI freeze duration, task cancellation delay, or tail latency of interactive requests. Do not use “having many threads” as proof that a system is responsive.

## 5. Utilization: how busy are the resources?

**Utilization (U)** is the fraction of time or capacity of **a specific resource** that is busy during a measurement window:

~~~text
U = resource busy time / resource available time
~~~

For example, a CPU core busy running tasks for 700 ms out of a 1,000 ms interval has a utilization of roughly **70%** over that interval. On a 4-core machine, state the normalization: consuming an average of 3 cores is about 75% of 4-core capacity; some tools display “300% CPU” when treating **100% as one core**. Always check the denominator before comparing numbers.

In Java, you usually need to distinguish the following resources:

| Resource measured | Approximate metric | Do not infer |
| --- | --- | --- |
| Process/system CPU | CPU percentage or CPU time per interval | 80% CPU does not tell you p99 latency |
| Worker thread pool | Active workers running tasks / pool size | A worker blocked on a socket can still count as active while consuming no CPU |
| Connection pool | Borrowed connections / total connections | Busy connections do not imply high CPU |
| Bandwidth/disk | Fraction of capacity used or device busy time | Thread count does not directly reflect I/O load |
| Lock/critical section | Lock hold time and waiter count/wait time | More threads may simply increase contention |

**Thread pool utilization and CPU utilization are different quantities.** For I/O-bound tasks, 100% busy workers do not necessarily mean 100% CPU; conversely, with few “active” workers, a single compute-heavy thread can still saturate an entire core. `ThreadPoolExecutor.getActiveCount()` and `getQueue().size()` only provide approximate snapshots—useful for observing trends, not as strictly linearizable counts.

Very low utilization may indicate spare capacity, low workload, or threads blocked on locks/I/O. High utilization uses resources efficiently, but **does not mean good performance**: near saturation, queues can grow sharply, worsening latency and variance. There is no universal “ideal CPU %” for every system; you must consider bursts, tail latency, priorities, and desired headroom.

## 6. How do the four metrics affect one another?

### 6.1. Queues are the critical link

If the task arrival rate exceeds a resource’s processing rate for long enough, queues grow. Older work occupies slots and newer work waits longer: **latency increases**, **responsiveness drops**, and **throughput may have already hit a ceiling** even while utilization stays high. Adding more work or more threads when the CPU is already saturated usually makes contention, context switching, and memory pressure worse.

~~~text
Arrival rate increases
       |
       v
Worker/resource approaches limit
       |
       +---- sufficient capacity ----> throughput increases, latency can stay stable
       |
       +---- near/over limit --------> queue grows --> p95/p99 latency increases
                                                         |
                                                         v
                                          timeouts, slow responses, more errors
~~~

With a bounded queue and a rejection policy, backlog is capped via **admission control / backpressure**: excess load receives an error or is asked to retry. This can protect latency for accepted tasks, but you must measure the rejection rate separately; do not mistake low throughput caused by rejections for good efficiency.

### 6.2. Little’s Law: work in the system, rate, and time

For a **stable system** with consistent measurement boundaries and the same type of work, Little’s Law states:

~~~text
L = λ × W
~~~

- `L`: average number of work items **in the system** (waiting + running).
- `λ`: steady-state rate of work passing through the system, in items/second.
- `W`: average time spent in the system, in seconds.

For example, suppose a stable system completes **120 request/s**, and each request has an average latency of **0.25 s** from arrival to completion. Then the average number of requests waiting or executing is `L = 120 × 0.25 = 30`.

Using the formula correctly:
1. Convert ms to seconds and keep the same measurement scope; if `W` excludes the queue, `L` must also exclude the queue.
2. Use **averages**, not p95/p99, for `W` in the formula.
3. Check whether the queue grows over time. When a system continuously accumulates backlog, you cannot take a short window and treat it as steady state.
4. If failed requests, retries, or timeouts are included, define consistently when they leave the system.

Little’s Law describes a relationship between quantities; it **does not prove** that increasing concurrency will increase throughput. If the bottleneck is a 4-core CPU, adding hundreds of threads does not create more cores.

### 6.3. Utilization from resource demand

Consider a resource with `m` identical service units, where each work item consumes an average of `D` seconds of **busy time on one resource unit**, at a completion rate of `X` items/second. In steady state with balanced load, average utilization is approximately:

~~~text
U ≈ X × D / m
~~~

For example, suppose a process needs **0.025 CPU-core-seconds/request**; at **120 request/s**, total demand is `120 × 0.025 = 3` continuously busy cores. If 4 cores are available to the process, utilization is roughly `3/4 = 75%`. This calculation is for **CPU time**—you must not plug 250 ms of elapsed time that includes network waiting into `D` to infer CPU utilization.

This approximation assumes an appropriate definition of CPU capacity/affinity/quota and sufficient parallelism. For a thread pool, busy time can include I/O waiting; a separate resource model is needed.

### 6.4. Adding threads: when does it help?

| Workload type | What more workers can provide | Limits or risks |
| --- | --- | --- |
| CPU-bound: encryption, computation | Increases parallelism until useful cores are saturated | Exceeding core count increases context switching, cache contention, and tail latency |
| I/O-bound: file/socket waiting | Lets other work run while one worker waits | Too many threads/tasks can exhaust RAM, connection pools, or downstream services |
| Heavy lock contention | Usually does not solve the bottleneck | More contenders can worsen queueing and latency |
| Mixed workload | Appropriate pools and concurrency limits can balance work | Must measure queue wait, CPU, I/O, and external dependencies separately |

Since Java 21, **virtual threads** make it possible to run many concurrently waiting tasks in a thread-per-task style with lower thread overhead in many situations. They **do not make CPU-bound work run in parallel beyond CPU capacity**, and they do not remove database, socket, lock, or external resource limits. The measurement example below uses **Java 17+** and platform threads so behavior is easy to observe.

## 7. Hands-on: measuring a batch of tasks in Java 17+

This experiment creates **12 tasks**, each calling `Thread.sleep(120)` to simulate *waiting* for about 120 ms. It runs two passes with pools of 2 and 4 workers, recording submission time, execution start, completion time, and total batch duration. Every measurement uses the monotonic clock `System.nanoTime()`, which is suitable for measuring **elapsed intervals** rather than wall-clock timestamps.

Create the file **`ConcurrencyMetricsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ConcurrencyMetricsDemo {
    private record Sample(long queueNs, long runNs, long latencyNs) {}

    private static void experiment(int workers) throws InterruptedException {
        final int taskCount = 12;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        List<Sample> samples = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch completed = new CountDownLatch(taskCount);

        long batchStart = System.nanoTime();
        for (int i = 0; i < taskCount; i++) {
            long submittedAt = System.nanoTime();
            pool.execute(() -> {
                long startedAt = System.nanoTime();
                try {
                    Thread.sleep(120); // Simulate wait time without burning CPU
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    long finishedAt = System.nanoTime();
                    samples.add(new Sample(
                            startedAt - submittedAt,
                            finishedAt - startedAt,
                            finishedAt - submittedAt));
                    completed.countDown();
                }
            });
        }

        completed.await();
        long batchEnd = System.nanoTime();
        pool.shutdown();
        if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
            throw new IllegalStateException("Workers did not terminate");
        }

        List<Long> latencies = samples.stream()
                .map(Sample::latencyNs)
                .sorted()
                .toList();

        int p95Index = (int) Math.ceil(0.95 * latencies.size()) - 1;
        double p95Ms = latencies.get(p95Index) / 1_000_000.0;
        double avgQueueMs = samples.stream()
                .mapToDouble(s -> s.queueNs() / 1_000_000.0)
                .average().orElse(0.0);
        double avgRunMs = samples.stream()
                .mapToDouble(s -> s.runNs() / 1_000_000.0)
                .average().orElse(0.0);
        double throughput = taskCount
                / ((batchEnd - batchStart) / 1_000_000_000.0);

        System.out.printf(Locale.US,
                "workers=%d | throughput=%.1f tasks/s"
                + " | p95=%.1f ms | avgQueue=%.1f ms | avgRun=%.1f ms%n",
                workers, throughput, p95Ms, avgQueueMs, avgRunMs);
    }

    public static void main(String[] args) throws InterruptedException {
        experiment(2);
        experiment(4);
    }
}
~~~

Compile and run:

~~~bash
javac ConcurrencyMetricsDemo.java
java ConcurrencyMetricsDemo
~~~

The program prints **two lines** in the following format:

~~~text
workers=2 | throughput=... tasks/s | p95=... ms | avgQueue=... ms | avgRun=... ms
workers=4 | throughput=... tasks/s | p95=... ms | avgQueue=... ms | avgRun=... ms
~~~

The `...` placeholders **represent measured numbers**, not fixed stdout values. Results are affected by the machine, OS scheduler, JIT, timer precision, and thread startup delay.

**How to interpret:** with only two workers, more tasks must wait for earlier waves, so `avgQueue` and `p95` are usually higher. Four workers can finish the batch sooner, yielding higher batch throughput because the tasks are mostly sleeping/waiting. `avgRun` is usually near 120 ms plus scheduler overhead; that is the task’s elapsed time, **not 120 ms of CPU**.

**Limitations of the experiment:**
- This measures a **12-task burst**, where throughput = 12 / batch completion time; it is **not** the sustained capacity of a continuously running service.
- `Executors.newFixedThreadPool` uses an unbounded queue by default; the example is suitable for learning measurements on a small batch, **not as a default** for arbitrary production load.
- The `p95` of 12 samples is a very noisy educational statistic. Do not use it to claim an SLO or compare real benchmarks.
- `Thread.sleep` simulates a worker not doing computation; to test CPU-bound behavior, you need a sufficiently large compute workload and to measure actual CPU time.
- Only successfully submitted tasks are measured; production systems also need to measure errors, task rejections, timeouts, retries, warm-up, and input distributions.

A useful exercise extension: add a bounded pool using `ThreadPoolExecutor` with `ArrayBlockingQueue` and an explicit `RejectedExecutionHandler`; try increasing the submission rate to observe queue wait, successful throughput, and rejections together. Set safe limits to avoid generating uncontrolled load.

## 8. Collecting reliable metrics on the JVM

### Measure the right things

- Use `System.nanoTime()` for durations: `end - start`. Do not use `System.currentTimeMillis()` for very short benchmarks because the wall clock can be adjusted and has different resolution.
- Record **submit/enqueue → start → finish** timestamps; if there is a network API, also record **client send → first response → complete** so the two sides are not conflated.
- Track latency histograms/distributions rather than only an average; keep the same measurement window, and tag task type, version, load, and error rate.
- For `ThreadPoolExecutor`, observe `getActiveCount()`, `getPoolSize()`, `getQueue().size()`, completed task count, and rejections. The getters return instantaneous/approximate state; periodic sampling is more useful than a single snapshot.
- Monitor CPU/GC/lock contention with appropriate JVM tools such as **Java Flight Recorder (JFR)** and **Java Mission Control (JMC)**; you can use `java.lang.management.ThreadMXBean` to inspect per-thread CPU time **if the JVM supports it and the feature is enabled**. CPU time, wall time, and blocked/waited time answer different questions.
- Plot throughput, latency, CPU, queue depth, and error/timeout rate on **the same timeline** to see causal direction: did CPU spike before p99 rose? Did the queue grow when arrival exceeded completion? Did timeouts rise after the queue grew long?

### Designing a load experiment

1. Define the workload: data sizes, CPU/I/O ratio, task mix, execution paths, JVM settings, and resources (cores, memory, quotas).
2. Warm up sufficiently so initial class loading/JIT costs are not mistaken for steady state; record cold-start performance separately if that is an actual requirement.
3. Step up the offered load across multiple levels and hold each long enough to see whether the system stabilizes or backlog grows. Compare **successful** throughput, p50/p95/p99, CPU, queue depth, and errors at each level.
4. Distinguish **open-loop** load testing (sending at a predetermined rate) from **closed-loop** load testing (waiting for a response before sending the next request). Closed-loop generators naturally slow down when the system slows, making results look artificially good. Avoid **coordinated omission**: the load generator failing to record the intervals when requests should have arrived but were not sent because the system was slow.
5. Fix the environment and run multiple trials; report variance as well. Data from a laptop running many background processes is not enough to establish production capacity.

### A useful test log template

~~~text
Workload: 80% I/O wait, 20% CPU work; 4 CPU cores; fixed JVM/config
Offered load: 100 request/s, measured for 5 minutes after warm-up
Completed success: 98 request/s; errors/timeouts: recorded separately
Latency boundary: client send -> complete
Latency: mean ..., p50 ..., p95 ..., p99 ... (ms)
CPU utilization: ...% / 4 cores; pool active: .../N; queue: ...
Conclusion: evaluate trends across multiple load levels, not from a single sample
~~~

The `...` placeholders are where **actual measured numbers** should be filled in, not guessed figures.

## 9. Analyzing common scenarios

| Simultaneous observations | Hypothesis to test | Investigation / adjustment direction |
| --- | --- | --- |
| Throughput is nearly flat, CPU is near saturation, queue and p99 are rising | CPU is the bottleneck | Profile CPU, reduce CPU per request, shed/limit admitted load, or add CPU resources; avoid blindly adding threads |
| Low CPU, almost all workers active, queue growing | Workers are stuck on I/O or waiting on locks/downstream | Measure blocked/waited time, timeouts, and downstream dependencies; consider appropriate concurrency/pool limits |
| Mean latency is stable, but p99 spikes sharply | Bursty congestion, GC pauses, locks, slow I/O, or work skew | Check histograms, per-stage traces, JFR, and timestamps when queues grew |
| Throughput increases, but timeouts/rejections are high | Incoming load increased or rejection policies kicked in | Report successful throughput and error rate; determine capacity against SLOs |
| Adding workers helps I/O-bound tasks, but slows CPU-bound tasks | Added concurrency exceeded useful resources | Separate workloads, bound pools, measure context switches/CPU/queue |
| “Received” ack is very fast, but actual result arrives very late | Good first response, poor completion latency | Communicate status clearly, measure both milestones, and support cancellation/progress tracking |

Do not jump to conclusions from a single metric. For example, **low CPU + high p99** does not prove the system has plenty of spare capacity: a lock or slow downstream service can be the bottleneck while CPU sits nearly idle.

## 10. Common misconceptions and practical principles

1. **“More threads means faster.”** Only true within specific resource limits and workload types; CPU-bound work, lock contention, and memory pressure can get worse.
2. **“High throughput means low latency.”** A system can complete many request/s while still making each request wait a long time in a queue.
3. **“A low mean means every user is happy.”** You need to check p95/p99, timeouts, and measurement boundaries.
4. **“100% utilization is always good.”** Operating near saturation reduces burst absorption; tail latency can climb rapidly.
5. **“An active thread means a busy CPU.”** A thread may be waiting on I/O, `synchronized`, `Lock`, or a condition.
6. **“Task latency equals processing time after dequeue.”** Queue wait is also part of what the caller waits for if measurement starts at submission.
7. **“One batch benchmark proves sustained capacity.”** Bursts, warm-up, backlog, and load-generation mechanics can skew results.
8. **“Just increase the timeout.”** Longer timeouts can keep more tasks in flight in the system and exhaust resources; you must find the bottleneck and apply load-limiting policies.

When designing concurrent programs in Java, start with **measurable goals**: for example, “p95 completion latency under 200 ms at 150 task/s, errors under 0.1%, on 4 cores with the described workload”. Then observe **latency distribution + successful throughput + responsiveness + utilization/queue/error rate** together. Metrics are only meaningful when they share the same boundary, measurement interval, and workload definition.

## Self-check

1. If a request waits 90 ms in the queue and runs for 30 ms, what is the latency from submission? Why should you not report 30 ms as the total latency?
2. A stable system completes 200 task/s with an average latency of 150 ms. According to Little’s Law, how many tasks are in the system on average? (Answer: `200 × 0.150 = 30`.)
3. A pool has 100% active workers, but process CPU is only 15%. Which wait times would you inspect before increasing the pool size?
4. Why can you not add the p99 of two processing steps to get the exact p99 of the entire flow?
5. For a CPU-bound workload on 4 cores, what should you observe before changing from 4 to 64 workers?

**Key takeaway:** latency measures **time for one piece of work**, throughput measures **work completed over time**, responsiveness measures **timely reaction**, and utilization measures **how busy a specific resource is**. Optimizing concurrency is about managing the relationships among these metrics, bottlenecks, and load—not maximizing a single metric in isolation.