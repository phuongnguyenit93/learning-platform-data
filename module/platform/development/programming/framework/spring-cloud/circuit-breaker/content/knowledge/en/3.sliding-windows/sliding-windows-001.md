# Count-Based and Time-Based Sliding Windows

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, Spring Cloud Circuit Breaker combined with Resilience4j helps limit the impact when a dependent service is slow or unavailable. To decide when to open the circuit, the Circuit Breaker must observe the outcomes of recent calls. Resilience4j provides two ways of observing them: a count-based sliding window (**COUNT_BASED**) and a time-based sliding window (**TIME_BASED**).

Both window types serve the same goal: calculating the failure rate and slow call rate from recent data. The difference lies in how the data scope is defined. COUNT_BASED keeps a fixed number of the most recent calls; TIME_BASED keeps results from the most recent time interval. Choosing the right window type helps the Circuit Breaker react appropriately to the actual traffic of the service.

## 1. What is a sliding window used for?

Suppose the Order service calls the Inventory service to check stock. If it only looks at a single call, a single error might cause the system to react too early. Conversely, if it calculates the failure rate since application startup, old errors may continue to influence decisions even after the Inventory service has recovered.

A sliding window limits the data used to evaluate recent health. Whenever a call completes, its outcome is recorded. As the window slides, data outside the scope is no longer included in the calculation.

A Circuit Breaker typically tracks at least two rates:

- **Failure rate:** the percentage of calls recorded as failed.
- **Slow call rate:** the percentage of calls whose execution duration exceeds **slowCallDurationThreshold**.

These rates are compared against **failureRateThreshold** and **slowCallRateThreshold**. If either rate reaches or exceeds its threshold after the minimum number of samples has been collected, the Circuit Breaker can transition from CLOSED to OPEN.

Conceptually, the two calculations take the form:

$$
\text{Failure rate} =
\frac{\text{number of failed calls}}{\text{total recorded calls in the window}}
\times 100\%
$$

$$
\text{Slow call rate} =
\frac{\text{number of slow calls}}{\text{total recorded calls in the window}}
\times 100\%
$$

A slow call can still succeed. For example, the Inventory service returns HTTP 200 after 4 seconds; if the slow call threshold is 2 seconds, that call is considered slow even though it did not fail. Tracking both rates separately helps detect both failure conditions and latency degradation.

## 2. Count-Based Sliding Window — COUNT_BASED

With **COUNT_BASED**, **slidingWindowSize** is the number of most recent calls retained in the window. For example, a size of 10 means the Circuit Breaker evaluates up to the 10 most recently completed call results.

When a new result arrives:

1. The new result is added to the window.
2. If the window is already full, the oldest result leaves the window.
3. The Circuit Breaker updates the counts of successful, failed, and slow calls in the window.
4. Once the minimum number of samples is reached, the rates are compared against the configured thresholds.

A window of size 5 can be visualized as follows:

~~~text
Time A: [Success, Success, Failure, Success, Success]
Add a Failure call:
Time B: [Success, Failure, Success, Success, Failure]
         ^ oldest result has left the window
~~~

For example, a window has 10 calls and records 3 failed calls. The failure rate is 30%. If the failure threshold is 50%, the circuit does not open yet because the rate has not reached the threshold. As new calls complete and replace older results, the rate may increase or decrease. If the window now has 5 failed calls out of 10 calls, the failure rate reaches 50% and meets the threshold.

### Characteristics of COUNT_BASED

- The number of samples in the window remains relatively stable once the window is full.
- The time span covered by the window varies with traffic. At 100 calls per second, a 100-call window reflects roughly one second; at one call per minute, it may reflect nearly 100 minutes.
- Every call carries equal weight in the rate calculation, whether the calls are milliseconds or minutes apart.
- This window is suitable when you want to evaluate a fixed number of recent transactions and traffic does not fluctuate too abruptly, or when sample count matters more than time span length.

COUNT_BASED does not mean the Circuit Breaker only operates after reaching the full **slidingWindowSize**. When rate calculation starts is controlled by **minimumNumberOfCalls**. For example, if the window size is 20 but the minimum number of calls is 10, the Circuit Breaker can evaluate once 10 calls have been recorded; the window continues to update as more results arrive.

## 3. Time-Based Sliding Window — TIME_BASED

With **TIME_BASED**, **slidingWindowSize** is the window length in seconds. For example, a size of 10 means the Circuit Breaker observes call results from the last 10 seconds.

Resilience4j divides the time window into buckets (statistical slots), with each bucket corresponding to one second. Each bucket stores partial statistics for the calls recorded during that second. When the window slides to a new second, the oldest bucket leaves the scope and a new bucket is used to collect subsequent results. The metrics in the buckets remaining in the window are aggregated to produce the overall statistics.

For example, with a 5-second window, at 12:00:05 the observation scope is approximately the buckets from 12:00:01 to 12:00:05. When moving to 12:00:06, the 12:00:01 bucket leaves the window and the 12:00:06 bucket is added.

~~~text
Time 12:00:05
[12:00:01] [12:00:02] [12:00:03] [12:00:04] [12:00:05]
      <---------- 5-second window ---------->

Time 12:00:06
             [12:00:02] [12:00:03] [12:00:04] [12:00:05] [12:00:06]
                   <---------- 5-second window ---------->
~~~

Suppose there are 40 calls in the last 10 seconds, of which 8 fail. The failure rate is 20%. If 10 more calls arrive in the next second and the oldest bucket leaves the window, the new rate is calculated over the total results remaining in the new 10-second scope. The number of calls in the window can rise or fall with traffic; it is not fixed like in COUNT_BASED.

### Characteristics of TIME_BASED

- The observation scope always targets a fixed time interval, such as the last 10 seconds.
- The number of samples varies with traffic. During peak hours there may be hundreds of calls; during low load there may only be a few.
- Old results automatically leave the window as the corresponding time interval elapses, so the rate reflects the situation over time.
- This window type is useful when traffic varies significantly and you want to know the service health over a recent short time period.

TIME_BASED does not automatically make a decision just because one bucket has a high failure rate. The Circuit Breaker still needs to reach **minimumNumberOfCalls** within the window before calculating rates. For example, a 10-second window with 4 calls, 2 of which fail, yields an observed rate of 50%; however, if **minimumNumberOfCalls** is 10, there are not yet enough samples to use that rate to decide to open the circuit.

## 4. Role of minimumNumberOfCalls

**minimumNumberOfCalls** is the minimum number of calls that must be recorded in the window before the Circuit Breaker calculates the failure rate and slow call rate to decide state transitions.

This parameter prevents drawing conclusions from too small a sample. If there are only 2 calls and both fail, the failure rate is 100%, yet that is not necessarily a reliable signal to cut off all subsequent calls. When the minimum requirement is 10, the Circuit Breaker waits until 10 results are recorded before evaluating the rates.

Example with **minimumNumberOfCalls: 10**:

| Recorded calls | Failed calls | Observed failure rate | Enough samples to evaluate? |
| ---: | ---: | ---: | --- |
| 2 | 2 | 100% | No |
| 8 | 4 | 50% | No |
| 10 | 4 | 40% | Yes |
| 10 | 6 | 60% | Yes |

Suppose **failureRateThreshold** is 50%. When there are 10 results and 4 failures, the 40% rate has not reached the threshold. When there are 10 results and 6 failures, the 60% rate exceeds the threshold so the Circuit Breaker can open the circuit.

For TIME_BASED, if traffic is too low and the window never accumulates the minimum number of calls, the Circuit Breaker will not calculate rates to open the circuit based on those samples. For COUNT_BASED, the time needed to accumulate enough samples can lengthen during low traffic. Therefore, you need to consider window size, actual traffic, and minimum sample count together.

## 5. Comparing the Two Window Types

| Criterion | COUNT_BASED | TIME_BASED |
| --- | --- | --- |
| **slidingWindowSize** represents | Number of most recent calls | Number of most recent seconds |
| Observation scope | Varies with call rate | Fixed by time |
| Number of samples in the window | Stable once the window is full | Varies with traffic |
| When traffic increases | The window covers a shorter time span | More samples fall within the same time span |
| When traffic decreases | The window covers a longer time span | May not reach minimum samples |
| Suitable when | Evaluating the latest N calls | Evaluating health over the last T seconds |

For example, the Inventory service receives traffic of 5 calls per second. A COUNT_BASED window of size 50 will cover about 10 seconds under steady traffic. If traffic increases to 50 calls per second, the same window covers only about one second. A 10-second TIME_BASED window still covers 10 seconds in both cases, though the sample count differs.

Neither type is universally better. COUNT_BASED answers the question “Are the last N calls having issues?”, while TIME_BASED answers “Has the service been having issues over the last T seconds?”. The operational question you need to answer should drive the choice.

## 6. Configuration in Spring Cloud CircuitBreaker with Resilience4j

Spring Cloud CircuitBreaker allows using Resilience4j as the implementation. Instances are configured by name in **application.yml**. The instance name must match the name used when creating the Circuit Breaker in the application, such as **inventory**.

### COUNT_BASED Example

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
~~~

In this configuration:

- The window retains up to the 20 most recent calls.
- At least 10 results are required before calculating rates.
- If the failure rate reaches 50% or the slow call rate reaches 60%, the Circuit Breaker can transition to OPEN.
- Calls lasting longer than 2 seconds are classified as slow calls.
- Once OPEN, the circuit remains in that state for 10 seconds according to **waitDurationInOpenState** before allowing the HALF_OPEN trial phase.

### TIME_BASED Example

To switch to a time-based window, change the window type and size:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
~~~

In this configuration, **slidingWindowSize: 10** means the last 10 seconds, not 10 calls. If fewer than 10 results occur within that interval, the Circuit Breaker does not yet have enough samples to evaluate the rates. The parameters for failure threshold, slow calls, and OPEN duration have the same meaning as in the COUNT_BASED example.

The two YAML snippets above are two configuration options for the same **inventory** instance; when deploying, choose one window type that matches your operational goal. You should not create two configurations with the same instance name expecting them to operate simultaneously.

### Calling the Circuit Breaker by Instance Name

With the Spring Cloud CircuitBreaker abstraction, the application can create a Circuit Breaker by its configured name:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> callInventoryService(sku),
                error -> Inventory.unavailable(sku)
        );
    }

    private Inventory callInventoryService(String sku) {
        // Perform an HTTP call to the Inventory service.
        return fetchInventory(sku);
    }

    private Inventory fetchInventory(String sku) {
        // HTTP call details are simplified to focus on the Circuit Breaker.
        return new Inventory(sku);
    }
}
~~~

The name **inventory** links the call in source code to the instance configured in YAML. In a real application, the HTTP call needs to be implemented with an appropriate client, and the fallback must accurately represent the data state. The example above only illustrates how to select an instance; it does not replace configuring timeouts on the HTTP client.

## 7. How to Choose Window Size and Thresholds

Window size and minimum sample count directly affect failure detection speed and decision stability.

**A window that is too small** can react quickly, but rates fluctuate sharply when just a few calls change outcomes. A brief burst of errors can open the circuit even if the service recovers shortly afterward.

**A window that is too large** smooths out random fluctuations, but a new incident can be diluted by many older successful results. The Circuit Breaker may take longer to detect degradation.

**A minimumNumberOfCalls that is too low** makes decisions overly sensitive to a small sample. **A minimumNumberOfCalls that is too high** can delay decisions, especially for low-traffic services or short TIME_BASED windows.

A practical configuration selection process:

1. Measure traffic over time, including peak hours and low-request periods.
2. Define the incident detection target, such as reacting within the last 10 seconds or after the last 50 transactions.
3. Choose COUNT_BASED or TIME_BASED based on that target.
4. Choose **minimumNumberOfCalls** so rates are not computed from too small a sample, while still being achievable under normal traffic.
5. Set **failureRateThreshold** and **slowCallRateThreshold** based on acceptable degradation levels.
6. Observe circuit states and adjust based on real operational data.

For a service whose traffic fluctuates by the hour, TIME_BASED often makes the question “health over the last 10 seconds” more consistent. However, you must verify whether low traffic meets **minimumNumberOfCalls**. For a background task with a steady but modest call count, COUNT_BASED can evaluate a recent batch of transactions more clearly.

## 8. Points to Note When Reading Results

**Only calls with completed outcomes contribute to statistics.** A pending call cannot be classified as successful, failed, or slow until it completes or times out. If a dependent service can hang for a long time, configure timeouts on the HTTP client or use an appropriate TimeLimiter. A Circuit Breaker does not replace a timeout by itself.

**Not every exception should be counted as a dependency failure.** A business error such as a nonexistent SKU may be a valid response from the Inventory service. If configured to record it as an infrastructure failure, the failure rate will be skewed upward. Classify recorded exceptions and ignored exceptions according to application semantics.

**Calls rejected while the circuit is OPEN differ from failed calls.** A rejected call does not reach the Inventory service, so it is not a new outcome of the dependent operation to be entered into the sliding window. Track rejected calls separately to know how many requests the Circuit Breaker is blocking.

**Failure rate and slow call rate should be read together.** A service may return successful results that are too slow to meet requirements. If you only monitor the failure rate, this condition may not be detected in time.

**Each instance has its own window and statistics.** Place a Circuit Breaker per dependent service or per group of operations with similar characteristics. If multiple unrelated dependencies share one instance, errors in one dependency can affect decisions for the others.

## 9. Monitoring and Verifying the Window Choice

During testing, observe the metrics per instance:

- Circuit Breaker state: CLOSED, OPEN, or HALF_OPEN.
- Total recorded calls, successful calls, and failed calls.
- Failure rate and slow call rate.
- Number of calls rejected while the circuit is OPEN.
- Number of fallback executions and final response latency.

Resilience4j can expose metrics via Micrometer when the application enables the appropriate integration configuration. Spring Boot Actuator and systems like Prometheus can collect metrics for display on dashboards. When evaluating a window, correlate rates with the actual sample count and time span; a 100% rate from two calls means something very different from 100% from two hundred calls.

A simple test for the Inventory service:

1. Send steady traffic with mostly successful calls and observe the window.
2. Inject a controlled burst of errors so the failure rate gradually increases.
3. Observe when the Circuit Breaker reaches **minimumNumberOfCalls** and transitions to OPEN.
4. Stop injecting errors, allowing new good results to enter the window or waiting for old error buckets to expire.
5. Observe the HALF_OPEN phase and the circuit returning to CLOSED when trial calls meet the criteria.

With COUNT_BASED, observe new calls replacing old results. With TIME_BASED, observe old buckets expiring over time. These two mechanisms explain why the failure rate can drop after the service recovers, without any manual history reset.

## 10. Selection Scenario

An e-commerce platform has two types of dependencies:

- The Inventory service receives high traffic that fluctuates sharply with promotional campaigns. The operations team wants to know the failure rate over the last 10 seconds to protect order requests. TIME_BASED with a 10-second window is a suitable choice to try, paired with **minimumNumberOfCalls** chosen based on the lowest expected traffic.
- A periodic sync job sends a batch of transactions with a relatively fixed count. The development team wants to evaluate the last 30 calls regardless of how long the batch takes to complete. COUNT_BASED with a 30-call window better fits this goal.

In both cases, the development team must still measure latency, classify exceptions, and set timeouts. After deployment, compare the number of circuit openings, rejected calls, fallback rate, and recovery time to tune the configuration.

## 11. Self-Check

1. With **COUNT_BASED** and **slidingWindowSize: 50**, what is the Circuit Breaker observing?
2. With **TIME_BASED** and **slidingWindowSize: 10**, does the number 10 represent the number of calls or the number of seconds?
3. Why is **minimumNumberOfCalls** important when a TIME_BASED window has low traffic?
4. If traffic increases tenfold, how does the time span covered by a COUNT_BASED window change?
5. A call that returns a successful result after 5 seconds can affect which rate?
6. Why should calls rejected in the OPEN state be tracked separately from failed calls?

Once you can answer these questions, you can read sliding window configurations, explain the difference between COUNT_BASED and TIME_BASED, and choose a statistical scope that fits each service's traffic in Spring Cloud CircuitBreaker.
