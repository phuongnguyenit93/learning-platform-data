# Adding an Asynchronous Scenario and an Infrastructure Failure Scenario

A Spring test suite often already covers the happy path and basic input errors. To test real-world flows better, add at least one scenario where work completes on a background thread and one scenario where an infrastructure dependency is unavailable. These two scenarios test two different risks: whether the application handles asynchronous completion timing properly, and whether the application reacts properly when a dependent service fails.

This practice uses a report generation flow. The client sends a request to create a report; the API saves the job in the PENDING state and returns HTTP 202 Accepted. A background worker calls the report generation service. On success, the job transitions to COMPLETED. If the report service is unreachable or returns HTTP 5xx, the job transitions to FAILED with a stable error code.

An important point to keep clear in tests: the 202 response confirms that the system has accepted the job. The final outcome only arrives after the worker finishes. If the external service fails after the job has already been accepted, the initial 202 response is still the right response; the client polls job status to learn that background processing failed.

## 1. Identifying the Two Scenarios to Add

Sample flow:

~~~text
POST /api/report-jobs
        |
        v
ReportJobController
        |
        v
ReportJobService
        |
        +--> save job: PENDING
        |
        +--> submit ReportWorker to executor
                    |
                    v
             ReportProviderClient
                    |
             +------+------+
             |             |
          Success   Infrastructure error
             |             |
             v             v
        COMPLETED        FAILED
~~~

Two tests should protect both branches:

| Scenario | Condition | What to Verify |
|---|---|---|
| Successful asynchronous task | Provider returns a valid document | Request receives 202; job eventually becomes COMPLETED; document is saved |
| Infrastructure failure | Provider times out, cannot connect, or returns 5xx | Accepted request still returns 202; job eventually becomes FAILED with an infrastructure error code; no success output is saved |

Do not only verify that the worker method was called. Tests must wait for the final state and verify that the output was saved or the failure was recorded.

## 2. Distinguishing Business Errors from Infrastructure Errors

Not every exception from a dependency carries the same meaning:

| Error Type | Example | Typical Appropriate Handling |
|---|---|---|
| Input error | End date before start date | Reject request, typically 400 |
| Business error | Report does not exist or user lacks permission | Return domain error per contract |
| Transient infrastructure error | Connection refused, timeout, HTTP 503 | May retry with limits; record failure status or schedule retry |
| Persistent/configuration infrastructure error | Wrong host, invalid certificate, missing credentials | Record error and alert; do not retry infinitely |
| Programming error | NullPointerException or broken invariant | Log fully, mark processing error, and investigate code |

In the example, the provider client normalizes connection errors and HTTP 5xx responses into ReportProviderUnavailableException. The worker recognizes this infrastructure error category and updates the job status. 4xx errors caused by invalid requests should not automatically be classified as outages; map them according to the provider's contract.

Do not catch every RuntimeException and treat it as an infrastructure error. That can hide programming bugs and distort outage metrics.

## 3. Designing Components for the Sample Flow

### 3.1. Job State and Data

Example state model:

~~~java
public enum ReportJobStatus {
    PENDING,
    COMPLETED,
    FAILED
}
~~~

A job can store these fields:

~~~java
public class ReportJob {

    private UUID id;
    private ReportJobStatus status;
    private byte[] document;
    private String errorCode;

    // Constructor, factory, and getters/setters depending on implementation.
}
~~~

The repository or store needs equivalent operations:

~~~java
public interface ReportJobRepository {

    ReportJob save(ReportJob job);

    Optional<ReportJob> findById(UUID id);

    void markCompleted(UUID id, byte[] document);

    void markFailed(UUID id, String errorCode);
}
~~~

In a real application, this can be a Spring Data repository paired with transactional status update methods in a service. This practice focuses on the state contract and does not mandate a specific persistence style.

### 3.2. Client Calling the Report Service

Define an abstraction for the external dependency:

~~~java
public interface ReportProviderClient {

    byte[] generate(CreateReportRequest request);
}
~~~

Exception representing an unavailable provider:

~~~java
public class ReportProviderUnavailableException
        extends RuntimeException {

    public ReportProviderUnavailableException(Throwable cause) {
        super("Report provider is unavailable", cause);
    }
}
~~~

An adapter using RestClient can normalize I/O and HTTP 5xx errors:

~~~java
public class RestReportProviderClient implements ReportProviderClient {

    private final RestClient restClient;

    public RestReportProviderClient(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public byte[] generate(CreateReportRequest request) {
        try {
            return restClient.post()
                    .uri("/api/reports")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_PDF)
                    .body(request)
                    .retrieve()
                    .body(byte[].class);
        }
        catch (ResourceAccessException |
               HttpServerErrorException exception) {
            throw new ReportProviderUnavailableException(exception);
        }
    }
}
~~~

ResourceAccessException typically represents access errors such as connection failures or timeouts. HttpServerErrorException represents HTTP 5xx responses returned by the provider. These two categories can be normalized into a single infrastructure error so the worker handles them uniformly.

Do not catch HttpClientErrorException mechanically. HTTP 400 or 404 from the provider may indicate an invalid request or non-existent resource, requiring a separate domain rule.

### 3.3. Background Worker

Enable async execution and configure a bounded executor:

~~~java
@Configuration
@EnableAsync
public class ReportAsyncConfiguration {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("report-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

The worker is a separate bean so @Async calls pass through the Spring proxy:

~~~java
@Service
public class ReportWorker {

    private final ReportProviderClient providerClient;
    private final ReportJobRepository jobRepository;

    public ReportWorker(
            ReportProviderClient providerClient,
            ReportJobRepository jobRepository) {
        this.providerClient = providerClient;
        this.jobRepository = jobRepository;
    }

    @Async("reportExecutor")
    public CompletableFuture<Void> generate(
            UUID jobId,
            CreateReportRequest request) {

        try {
            byte[] document = providerClient.generate(request);
            jobRepository.markCompleted(jobId, document);
        }
        catch (ReportProviderUnavailableException exception) {
            jobRepository.markFailed(
                    jobId, "REPORT_PROVIDER_UNAVAILABLE");
        }

        return CompletableFuture.completedFuture(null);
    }
}
~~~

The example catches the known infrastructure error and records the FAILED state. A real application should add logging with correlation/job IDs and handle unexpected exceptions. If retries are needed, define retry count, backoff, deadline, and an intermediate state such as RETRYING; never retry infinitely inside a worker.

Do not call an @Async method from another method on the same object when using default proxies. Self-invocation bypasses the proxy and can run synchronously. Extracting the worker into its own bean, as in this example, keeps the async boundary clear.

### 3.4. Service Accepting the Request

The service saves the job first, then submits it to the worker:

~~~java
@Service
public class ReportJobService {

    private final ReportJobRepository jobRepository;
    private final ReportWorker reportWorker;

    public ReportJobService(
            ReportJobRepository jobRepository,
            ReportWorker reportWorker) {
        this.jobRepository = jobRepository;
        this.reportWorker = reportWorker;
    }

    public ReportJob submit(CreateReportRequest request) {
        ReportJob job = ReportJob.pending(UUID.randomUUID());
        jobRepository.save(job);

        reportWorker.generate(job.getId(), request);
        return job;
    }
}
~~~

The controller returns 202 Accepted along with the job ID:

~~~java
@RestController
@RequestMapping("/api/report-jobs")
public class ReportJobController {

    private final ReportJobService reportJobService;

    public ReportJobController(ReportJobService reportJobService) {
        this.reportJobService = reportJobService;
    }

    @PostMapping
    ResponseEntity<ReportJobResponse> submit(
            @Valid @RequestBody CreateReportRequest request) {

        ReportJob job = reportJobService.submit(request);
        return ResponseEntity.accepted()
                .body(new ReportJobResponse(job.getId(), job.getStatus()));
    }
}
~~~

Clients can query GET /api/report-jobs/{id} to retrieve the final status. The job creation request does not wait for the provider to finish.

If the executor rejects the task immediately on submit because the pool and queue are full, TaskRejectedException can occur before the controller returns 202. That is an error during work acceptance, distinct from a provider outage occurring after the job has been accepted. Define separate handling and tests for queue rejection if the system must protect that behavior.

## 4. Preparing Integration Tests for Both Scenarios

An integration test can use:

- A real Spring application context to verify the @Async proxy and executor bean.
- MockMvc to send requests into the controller.
- A real test repository or thread-safe store to observe job status.
- A mocked provider client to produce repeatable success or infrastructure errors.
- Awaitility to wait for the final state with a finite timeout.

Example structure:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ReportJobIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ReportJobRepository jobRepository;

    @MockitoBean
    ReportProviderClient providerClient;

    // Tests in the following sections.
}
~~~

@MockitoBean belongs to Spring Framework 6.2 and later. For older Spring Boot projects, use the corresponding mock bean annotation provided by your Spring Boot version, such as @MockBean. The test context must load @EnableAsync and the real reportExecutor bean; if you mock or replace the worker with a synchronous implementation, the test no longer verifies async dispatch.

If the repository uses a database, configure an isolated test database. You can use H2 for dialect-independent tests or Testcontainers with the production database type when verifying SQL, locking, and transaction behavior. Never let integration tests accidentally connect to a developer or production database.

## 5. Scenario 1: Request Accepted and Job Completes Asynchronously

The test sends the report creation request, asserts HTTP 202, extracts the job ID, and waits for COMPLETED:

~~~java
@Test
void acceptsJobAndCompletesItInBackground() throws Exception {
    byte[] generatedDocument = "PDF-CONTENT".getBytes(StandardCharsets.UTF_8);
    given(providerClient.generate(any(CreateReportRequest.class)))
            .willReturn(generatedDocument);

    MvcResult result = mockMvc.perform(post("/api/report-jobs")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "accountId": "ACCOUNT-42",
                              "from": "2026-01-01",
                              "to": "2026-01-31"
                            }
                            """))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andReturn();

    UUID jobId = UUID.fromString(
            JsonPath.read(
                    result.getResponse().getContentAsString(),
                    "$.id"));

    await()
            .atMost(Duration.ofSeconds(5))
            .untilAsserted(() -> {
                ReportJob job = jobRepository.findById(jobId)
                        .orElseThrow();

                assertThat(job.getStatus())
                        .isEqualTo(ReportJobStatus.COMPLETED);
                assertThat(job.getDocument())
                        .containsExactly(generatedDocument);
            });

    then(providerClient).should()
            .generate(any(CreateReportRequest.class));
}
~~~

The test does not assume the worker has finished immediately after perform(...). It first verifies that the request was accepted, then waits for the final condition. await().atMost(...) has a finite timeout so the test fails clearly if the worker fails to run or update the state.

In projects using other JUnit/Mockito versions, you might use verify(providerClient, timeout(...)) to wait for the mock invocation. However, asserting the final state in the repository is more valuable when the goal is protecting the full task, because calling the provider alone does not prove the output-saving step completed.

Do not use Thread.sleep(...) between the request and assertions. Sleeping merely guesses processing time and can cause flaky tests under heavy CI load.

## 6. Scenario 2: Provider Encounters an Infrastructure Failure After Job Acceptance

Simulating an unreachable provider:

~~~java
@Test
void marksJobFailedWhenProviderIsUnavailable() throws Exception {
    given(providerClient.generate(any(CreateReportRequest.class)))
            .willThrow(new ReportProviderUnavailableException(
                    new ResourceAccessException("Connection timed out")));

    MvcResult result = mockMvc.perform(post("/api/report-jobs")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "accountId": "ACCOUNT-42",
                              "from": "2026-02-01",
                              "to": "2026-02-28"
                            }
                            """))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andReturn();

    UUID jobId = UUID.fromString(
            JsonPath.read(
                    result.getResponse().getContentAsString(),
                    "$.id"));

    await()
            .atMost(Duration.ofSeconds(5))
            .untilAsserted(() -> {
                ReportJob job = jobRepository.findById(jobId)
                        .orElseThrow();

                assertThat(job.getStatus())
                        .isEqualTo(ReportJobStatus.FAILED);
                assertThat(job.getErrorCode())
                        .isEqualTo("REPORT_PROVIDER_UNAVAILABLE");
                assertThat(job.getDocument()).isNull();
            });

    then(providerClient).should()
            .generate(any(CreateReportRequest.class));
}
~~~

This test simulates a connection error at the provider client boundary. The API already returned 202 because the job was saved and accepted; the failure happened inside the worker afterward, so the job transitions to FAILED. Do not expect the initial POST request to change to 503 after already returning a response.

If the product wants the client to receive the error directly from a synchronous request, that is a different contract: the endpoint must wait for the provider and map the exception to an HTTP response before completing the request. Do not mix synchronous and background-job models in the same assertions.

## 7. Verifying Real HTTP 503 in the Provider Adapter

Mocking the provider client in integration tests creates repeatable background failures, but it does not check whether the adapter translates HTTP 503 into ReportProviderUnavailableException. Add a small test for the HTTP client adapter using MockRestServiceServer:

~~~java
@Test
void mapsProviderHttp503ToUnavailableException() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://reports.example");

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

    ReportProviderClient provider =
            new RestReportProviderClient(builder.build());

    server.expect(requestTo("https://reports.example/api/reports"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

    assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(ReportProviderUnavailableException.class);

    server.verify();
}
~~~

This test verifies that the adapter hits the right endpoint and translates a 503 response into the infrastructure exception understood by the worker. MockRestServiceServer does not open a socket; if you need to test timeouts over a real HTTP connector, use WireMock or MockWebServer and configure realistic client timeouts.

The two test layers have different goals:

- The job integration test verifies that the worker reacts properly when the provider abstraction reports unavailability.
- The adapter test verifies that HTTP 503 is translated into an unavailable error.

There is no need to repeat the entire workflow inside the adapter test.

## 8. When You Want to Test Network Timeouts Instead of HTTP 503

HTTP 503 is a valid response from the server. Connection timeout or connection refused are transport-layer errors and are typically represented by ResourceAccessException when using RestClient.

You can verify that the adapter normalizes that error:

~~~java
assertThatThrownBy(() -> provider.generate(validRequest()))
        .isInstanceOf(ReportProviderUnavailableException.class)
        .hasCauseInstanceOf(ResourceAccessException.class);
~~~

To produce a real network error, use a mock server that can be stopped or configured with a response delay longer than the client timeout. Do not rely on a random public host or CI internet access; such tests are flaky and can generate unwanted traffic.

When using a real mock server over sockets, set a finite timeout on the HTTP client and ensure the server is shut down in the test lifecycle. Check the specific exception of the HTTP connector version in use, as exception types may be wrapped across multiple layers.

## 9. Observing Job Results Through the API

In addition to repository assertions, you can test the status endpoint that clients actually call:

~~~java
@GetMapping("/{id}")
ReportJobResponse getStatus(@PathVariable UUID id) {
    ReportJob job = reportJobService.findById(id);
    return ReportJobResponse.from(job);
}
~~~

After waiting for the repository state transition, the test can call GET:

~~~java
mockMvc.perform(get("/api/report-jobs/{id}", jobId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("FAILED"))
        .andExpect(jsonPath("$.errorCode")
                .value("REPORT_PROVIDER_UNAVAILABLE"));
~~~

Repository assertions establish that the state was persisted accurately. HTTP assertions establish that clients can read that state through the API. For critical workflows, these two levels provide complementary evidence.

Never return provider exception messages or stack traces to clients. Use stable error codes; technical details should be logged internally alongside the job ID/correlation ID.

## 10. Controlling Wait Times and Avoiding Flaky Tests

Asynchronous tasks do not have a fixed completion time. Tests should wait for a meaningful condition:

| Waiting Approach | When Appropriate |
|---|---|
| CompletableFuture.get(timeout, unit) | Test directly receives a future from the worker |
| CountDownLatch.await(timeout, unit) | Void tasks or signaling a completion milestone |
| Awaitility untilAsserted(...) | State is updated via a repository or multiple components |
| StepVerifier | Task returns Mono/Flux and reactive signals need verification |

Set timeouts generous enough for CI environments yet still finite so deadlocks or unscheduled workers are caught. Do not set multi-minute timeouts just to mask a hung task.

When testing multiple concurrent workers, use a latch/barrier to hold tasks at the same point and verify how many tasks started. Never verify concurrency by guessing log order or using sleep.

## 11. Data Cleanup and Test Isolation

Async tests can keep running after the test method finishes if the test does not wait for the worker. This causes a task from an earlier test to mutate data after the next test has started.

To prevent this:

- Wait for the final state or a completion signal before ending the test.
- Use a fresh job ID for every test.
- Clean up test data after the worker finishes.
- Do not shut down a singleton executor managed by the Spring context inside individual test methods.
- Do not share mutable mock state across parallel tests.
- If tests use a real database, create data with unique IDs and roll back/clean up intentionally.

A test transaction does not automatically span background threads. A transaction opened on the test thread normally does not propagate to the worker thread. Consequently, data created inside the test transaction may still be uncommitted and invisible to the worker. For async tests, save/commit the required data before submitting the task or define clear transaction boundaries in the worker.

Do not rely on test-method rollback to clean up data written by another thread. The worker may commit independently, leaving data behind after the test thread's transaction rolls back.

## 12. Distinguishing Provider Outages from Executor Rejections

These two failures occur at different points in time:

| Situation | Timing | Typical Behavior |
|---|---|---|
| Provider timeout/503 | After the executor starts the worker | Job is already PENDING; worker records FAILED or RETRYING |
| Executor rejects task | When the application submits the task to the executor | Job may already have been saved yet task was never accepted; service needs appropriate rollback/status handling |

If the executor uses a bounded queue and fills up, TaskRejectedException can occur immediately when calling the async method through the proxy. Decide which state a previously saved job should transition to or how the transaction should roll back. Write dedicated tests for queue/rejection if workload saturation is a significant risk.

Do not use a provider error to stand in for executor rejection. One occurs inside the worker; the other occurs before the worker is even accepted to run.

## 13. Controlled Retries for Infrastructure Errors

Some infrastructure errors are transient and can be retried, but retries require a clear policy:

- Only retry error categories classified as transient, such as timeouts or certain HTTP 5xx codes.
- Set a maximum number of attempts.
- Use backoff and jitter to avoid multiple workers retrying simultaneously.
- Set an overall deadline for the job.
- Ensure the operation is idempotent or uses an idempotency key.
- Record attempt counts and the final cause.
- Do not retry input errors or non-recoverable domain errors.

If using Spring Retry or a custom retry mechanism, tests should verify the exact invocation count, configured timing/backoff, and final state after exhausting retries. In unit tests, you can use a fake sleeper/clock or short-interval policy configuration to avoid real waiting. In integration tests, avoid relying on long production retry intervals.

In the baseline example, the worker marks FAILED immediately upon receiving provider unavailability to focus on a single infrastructure failure. You can extend the states to include RETRYING and add retry tests when product requirements call for it.

## 14. Common Mistakes When Adding These Two Scenarios

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Test checks COMPLETED immediately after POST and fails intermittently | Worker has not finished yet | Wait for the final state using Awaitility or a future |
| Test passes alone but fails in the suite | Previous worker still running or shared data | Wait for completion, use unique job IDs, and clean up |
| @Async runs synchronously in tests | Self-invocation or worker created with new | Call through a Spring proxy and use a separate worker bean |
| Test only verifies provider was called | Does not prove output was saved | Assert final state and persisted data |
| Provider 503 is treated as an input error | Exception classification too broad or wrong | Separate HTTP 4xx, HTTP 5xx, and I/O errors |
| POST request is expected to return 503 even though job was accepted | Confusing post-202 background failure with synchronous failure | Poll job status afterward |
| Task is rejected yet job stays PENDING | Executor rejection unhandled | Define policy when submission is rejected |
| Transactional test hides data from worker | Transaction does not propagate to background thread | Commit required data or create transactions inside the worker |
| Test hangs when provider fails | Missing timeout or unreleased latch | Use finite timeouts and cleanup in finally |
| Infrastructure failure leaks stack trace in API | Returning exception message directly in response | Return stable error code, log details internally |

## 15. Practice Checklist

Before considering both scenarios added, verify:

1. Async test invokes the worker through a Spring bean/proxy.
2. Test executor has explicitly configured thread counts and queue capacity.
3. Job creation request returns 202 and a queryable job ID.
4. Success test waits for COMPLETED and checks the saved output.
5. Infrastructure test simulates repeatable provider errors without depending on public networks.
6. Failure test waits for FAILED and checks a stable error code.
7. Thread.sleep is never used to guess completion time.
8. Every wait operation has a finite timeout.
9. Worker does not classify every exception as an infrastructure error.
10. Test data and executor are isolated; no worker remains running after the test finishes.
11. If testing HTTP 503, a separate test verifies the adapter translates 5xx into a provider unavailable error.
12. If retries exist, attempt count, backoff, deadline, and idempotency are tested against the policy.

## 16. Expected Outcomes

After adding these two scenarios, the test suite can prove:

- The application accepts requests and returns 202 when a job is accepted.
- Background work actually runs on the executor and eventually persists COMPLETED state.
- When the provider is unavailable, the worker records FAILED state with the right error code.
- Failures occurring after job acceptance are observed through job status rather than confused with synchronous errors on the initial request.
- HTTP 503 or connection failures are normalized by the adapter into the infrastructure error type handled by the worker.

A good async test waits for a meaningful outcome instead of guessing timings. A good infrastructure failure test simulates the dependency boundary accurately and verifies the state published by the system. Combining these two scenarios tests both the normal background execution path and the application's ability to record failures in dependent systems.
