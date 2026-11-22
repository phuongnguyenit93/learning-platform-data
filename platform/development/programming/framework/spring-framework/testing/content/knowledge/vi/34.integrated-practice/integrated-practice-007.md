# Bổ sung một tình huống bất đồng bộ và một lỗi hạ tầng

Một bộ kiểm thử Spring thường đã có trường hợp thành công và các lỗi đầu vào cơ bản. Để kiểm tra luồng thực tế tốt hơn, hãy bổ sung ít nhất một tình huống trong đó công việc hoàn tất ở thread nền và một tình huống trong đó dependency hạ tầng không sẵn sàng. Hai tình huống này kiểm tra hai rủi ro khác nhau: ứng dụng có xử lý đúng thời điểm hoàn tất bất đồng bộ hay không, và ứng dụng có phản ứng đúng khi dịch vụ phụ thuộc gặp sự cố hay không.

Bài thực hành này dùng một luồng tạo báo cáo. Client gửi request tạo báo cáo; API lưu job ở trạng thái PENDING và trả HTTP 202 Accepted. Worker chạy nền gọi dịch vụ tạo báo cáo. Nếu thành công, job chuyển sang COMPLETED. Nếu dịch vụ báo cáo không truy cập được hoặc trả HTTP 5xx, job chuyển sang FAILED với mã lỗi ổn định.

Điểm cần giữ rõ trong test: response 202 xác nhận hệ thống đã nhận job. Kết quả cuối cùng chỉ có sau khi worker hoàn tất. Nếu dịch vụ ngoài gặp sự cố sau khi job đã được nhận, response 202 ban đầu vẫn là response đúng; client kiểm tra trạng thái job để biết quá trình nền thất bại.

## 1. Xác định hai tình huống cần bổ sung

Luồng mẫu:

~~~text
POST /api/report-jobs
        |
        v
ReportJobController
        |
        v
ReportJobService
        |
        +--> lưu job: PENDING
        |
        +--> gửi ReportWorker vào executor
                    |
                    v
             ReportProviderClient
                    |
             +------+------+
             |             |
          Thành công     Hạ tầng lỗi
             |             |
             v             v
        COMPLETED        FAILED
~~~

Hai test nên bảo vệ hai nhánh:

| Tình huống | Điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Tác vụ bất đồng bộ thành công | Provider trả tài liệu hợp lệ | Request nhận 202; job cuối cùng là COMPLETED; tài liệu được lưu |
| Lỗi hạ tầng | Provider timeout, không kết nối được hoặc trả 5xx | Request đã nhận vẫn là 202; job cuối cùng là FAILED với mã lỗi hạ tầng; không lưu kết quả thành công |

Không nên chỉ kiểm tra rằng phương thức worker đã được gọi. Test cần chờ đến trạng thái cuối và xác nhận dữ liệu được lưu hoặc lỗi được ghi nhận.

## 2. Phân biệt lỗi nghiệp vụ và lỗi hạ tầng

Không phải mọi exception từ dependency đều có cùng ý nghĩa:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Lỗi đầu vào | Ngày kết thúc trước ngày bắt đầu | Từ chối request, thường là 400 |
| Lỗi nghiệp vụ | Báo cáo không tồn tại hoặc người dùng không có quyền | Trả lỗi domain theo hợp đồng |
| Lỗi hạ tầng tạm thời | Connection refused, timeout, HTTP 503 | Có thể retry có giới hạn; ghi trạng thái thất bại hoặc chờ thử lại |
| Lỗi hạ tầng lâu dài/cấu hình | Sai host, chứng chỉ không hợp lệ, thiếu credential | Ghi nhận lỗi và cảnh báo; không retry vô hạn |
| Lỗi lập trình | NullPointerException hoặc invariant bị phá vỡ | Ghi log đầy đủ, đánh dấu lỗi xử lý và điều tra code |

Trong ví dụ, provider client chuẩn hóa lỗi kết nối và HTTP 5xx thành ReportProviderUnavailableException. Worker nhận diện đúng nhóm lỗi hạ tầng này và cập nhật trạng thái job. Lỗi 4xx do request không hợp lệ không nên tự động bị phân loại thành outage; cần ánh xạ theo hợp đồng của provider.

Không bắt mọi RuntimeException rồi coi là lỗi hạ tầng. Cách đó có thể che lỗi lập trình và làm metric outage sai lệch.

## 3. Thiết kế các thành phần cho luồng mẫu

### 3.1. Trạng thái và dữ liệu job

Ví dụ mô hình trạng thái:

~~~java
public enum ReportJobStatus {
    PENDING,
    COMPLETED,
    FAILED
}
~~~

Một job có thể lưu các trường:

~~~java
public class ReportJob {

    private UUID id;
    private ReportJobStatus status;
    private byte[] document;
    private String errorCode;

    // Constructor, factory và getter/setter tùy cách triển khai.
}
~~~

Repository hoặc store cần các thao tác tương đương:

~~~java
public interface ReportJobRepository {

    ReportJob save(ReportJob job);

    Optional<ReportJob> findById(UUID id);

    void markCompleted(UUID id, byte[] document);

    void markFailed(UUID id, String errorCode);
}
~~~

Trong ứng dụng thực tế, đây có thể là Spring Data repository cùng các phương thức cập nhật trạng thái trong service có transaction. Bài thực hành tập trung vào hợp đồng trạng thái, không yêu cầu một kiểu persistence cụ thể.

### 3.2. Client gọi dịch vụ báo cáo

Định nghĩa một abstraction cho dependency ngoài:

~~~java
public interface ReportProviderClient {

    byte[] generate(CreateReportRequest request);
}
~~~

Exception đại diện cho provider không sẵn sàng:

~~~java
public class ReportProviderUnavailableException
        extends RuntimeException {

    public ReportProviderUnavailableException(Throwable cause) {
        super("Report provider is unavailable", cause);
    }
}
~~~

Adapter dùng RestClient có thể chuẩn hóa lỗi I/O và HTTP 5xx:

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

ResourceAccessException thường đại diện lỗi truy cập như connection hoặc timeout. HttpServerErrorException đại diện response HTTP 5xx do provider trả về. Hai nhóm này có thể được chuẩn hóa thành một lỗi hạ tầng để worker xử lý thống nhất.

Không bắt HttpClientErrorException một cách máy móc. HTTP 400 hoặc 404 từ provider có thể biểu thị request không hợp lệ hoặc tài nguyên không tồn tại, cần quy tắc domain riêng.

### 3.3. Worker chạy nền

Bật async execution và cấu hình executor có giới hạn:

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

Worker là bean riêng để lời gọi @Async đi qua Spring proxy:

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

Ví dụ bắt lỗi hạ tầng đã biết và ghi trạng thái FAILED. Ứng dụng thực tế nên bổ sung log có correlation/job ID và xử lý các exception không dự kiến. Nếu cần retry, hãy quy định số lần thử, backoff, deadline và trạng thái trung gian như RETRYING; không retry vô hạn trong worker.

Không gọi phương thức @Async từ một phương thức khác trong cùng object nếu đang dùng proxy mặc định. Lời gọi nội bộ không đi qua proxy và có thể chạy đồng bộ. Tách worker thành bean riêng như ví dụ giúp ranh giới async rõ ràng.

### 3.4. Service tiếp nhận request

Service lưu job trước, sau đó gửi worker:

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

Controller trả 202 Accepted cùng mã job:

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

Client có thể truy vấn GET /api/report-jobs/{id} để lấy trạng thái cuối. Request tạo job không đợi provider hoàn tất.

Nếu executor từ chối tác vụ ngay lúc submit do pool và queue đầy, TaskRejectedException có thể xảy ra trước khi controller trả 202. Đây là lỗi ở bước nhận công việc, khác với provider outage xảy ra sau khi job đã được chấp nhận. Hãy định nghĩa riêng cách xử lý và test cho trường hợp queue bị từ chối nếu hệ thống cần bảo vệ hành vi đó.

## 4. Chuẩn bị test integration cho hai tình huống

Một integration test có thể dùng:

- Spring application context thật để kiểm tra @Async proxy và executor bean.
- MockMvc để gửi request vào controller.
- Repository test thật hoặc store thread-safe để quan sát trạng thái job.
- Provider client được thay bằng mock để tạo kết quả thành công hoặc lỗi hạ tầng có thể lặp lại.
- Awaitility để chờ trạng thái cuối với timeout hữu hạn.

Ví dụ cấu trúc:

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

    // Các test ở những phần tiếp theo.
}
~~~

@MockitoBean thuộc Spring Framework 6.2 trở lên. Với dự án Spring Boot cũ hơn, dùng annotation mock bean tương ứng mà phiên bản Spring Boot cung cấp, chẳng hạn @MockBean. Test context phải nạp @EnableAsync và bean reportExecutor thật; nếu mock hoặc thay worker bằng implementation đồng bộ thì test không còn xác nhận async dispatch.

Nếu repository dùng database, cấu hình database test tách biệt. Có thể dùng H2 cho test không phụ thuộc dialect hoặc Testcontainers với cùng loại database production khi cần xác nhận SQL, locking và transaction behavior. Không để integration test vô tình kết nối database developer hoặc production.

## 5. Tình huống 1: request được nhận và job hoàn tất bất đồng bộ

Test gửi request tạo báo cáo, xác nhận HTTP 202, lấy job ID rồi chờ trạng thái COMPLETED:

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

Test không giả định worker hoàn tất ngay sau perform(...). Nó xác nhận request được chấp nhận trước, sau đó chờ điều kiện cuối. await().atMost(...) có timeout hữu hạn nên test thất bại rõ ràng nếu worker không chạy hoặc không cập nhật trạng thái.

Trong dự án dùng JUnit/Mockito phiên bản khác, có thể dùng verify(providerClient, timeout(...)) để chờ lời gọi mock. Tuy nhiên, xác nhận trạng thái cuối trong repository có giá trị hơn nếu mục tiêu là bảo vệ toàn bộ tác vụ, vì lời gọi provider chưa chứng minh bước lưu kết quả đã hoàn tất.

Không dùng Thread.sleep(...) giữa request và assertion. Sleep chỉ đoán thời gian xử lý và có thể tạo test chập chờn khi CI tải cao.

## 6. Tình huống 2: provider gặp lỗi hạ tầng sau khi job được nhận

Mô phỏng provider không truy cập được:

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

Test này mô phỏng lỗi kết nối ở ranh giới provider client. API đã trả 202 vì job được lưu và chấp nhận; lỗi xảy ra trong worker sau đó nên trạng thái job chuyển sang FAILED. Không mong đợi request POST ban đầu đổi thành 503 sau khi đã trả response.

Nếu sản phẩm muốn client nhận được kết quả lỗi qua một request đồng bộ, đó là hợp đồng khác: endpoint phải đợi provider và ánh xạ exception thành HTTP response trước khi hoàn tất request. Không trộn hai mô hình đồng bộ và job nền trong cùng assertion.

## 7. Kiểm tra HTTP 503 thật ở adapter của provider

Mock provider client trong integration test giúp tạo lỗi nền ổn định, nhưng nó không kiểm tra adapter có chuyển HTTP 503 thành ReportProviderUnavailableException hay không. Bổ sung một test nhỏ cho HTTP client adapter bằng MockRestServiceServer:

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

Test này xác nhận adapter gửi đúng endpoint và chuyển response 503 thành exception hạ tầng mà worker hiểu. MockRestServiceServer không mở socket; nếu cần kiểm tra timeout qua HTTP connector thật, có thể dùng WireMock hoặc MockWebServer và cấu hình timeout client thực tế.

Hai lớp test có mục tiêu khác nhau:

- Integration test của job kiểm tra worker phản ứng đúng khi provider abstraction báo unavailable.
- Adapter test kiểm tra HTTP 503 được chuyển thành lỗi unavailable.

Không cần lặp toàn bộ workflow trong test adapter.

## 8. Nếu muốn kiểm tra lỗi network timeout thay vì HTTP 503

HTTP 503 là response hợp lệ từ server. Connection timeout hoặc connection refused là lỗi ở tầng truyền tải và thường được biểu diễn bằng ResourceAccessException khi dùng RestClient.

Có thể kiểm tra adapter chuẩn hóa lỗi đó:

~~~java
assertThatThrownBy(() -> provider.generate(validRequest()))
        .isInstanceOf(ReportProviderUnavailableException.class)
        .hasCauseInstanceOf(ResourceAccessException.class);
~~~

Để tạo lỗi network thực tế, dùng một mock server có thể dừng hoặc cấu hình response delay dài hơn timeout client. Không dựa vào một host public ngẫu nhiên hoặc mạng internet của CI; test như vậy không ổn định và có thể tạo tải không mong muốn.

Khi dùng mock server thật qua socket, đặt timeout hữu hạn ở HTTP client và đảm bảo server được đóng trong lifecycle của test. Kiểm tra exception cụ thể của phiên bản HTTP connector đang dùng, vì loại exception có thể được bọc theo nhiều tầng.

## 9. Quan sát kết quả job qua API

Ngoài repository assertion, có thể kiểm tra endpoint trạng thái mà client thực sự sử dụng:

~~~java
@GetMapping("/{id}")
ReportJobResponse getStatus(@PathVariable UUID id) {
    ReportJob job = reportJobService.findById(id);
    return ReportJobResponse.from(job);
}
~~~

Sau khi chờ repository chuyển trạng thái, test có thể gọi GET:

~~~java
mockMvc.perform(get("/api/report-jobs/{id}", jobId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("FAILED"))
        .andExpect(jsonPath("$.errorCode")
                .value("REPORT_PROVIDER_UNAVAILABLE"));
~~~

Repository assertion giúp xác định trạng thái được ghi đúng. HTTP assertion giúp xác nhận client có thể đọc trạng thái đó qua API. Với test workflow quan trọng, hai mức này bổ sung bằng chứng cho nhau.

Không trả exception message hoặc stack trace của provider cho client. Dùng error code ổn định; chi tiết kỹ thuật nên được ghi log nội bộ cùng job ID/correlation ID.

## 10. Kiểm soát thời gian chờ và tránh test chập chờn

Tác vụ bất đồng bộ không có thời gian hoàn tất cố định. Test nên chờ một điều kiện có ý nghĩa:

| Cách chờ | Khi phù hợp |
|---|---|
| CompletableFuture.get(timeout, unit) | Test trực tiếp nhận được future từ worker |
| CountDownLatch.await(timeout, unit) | Tác vụ void hoặc cần báo hiệu một mốc hoàn tất |
| Awaitility untilAsserted(...) | Trạng thái được cập nhật qua repository hoặc nhiều thành phần |
| StepVerifier | Tác vụ trả Mono/Flux và cần kiểm tra tín hiệu reactive |

Đặt timeout đủ rộng cho môi trường CI nhưng vẫn hữu hạn để phát hiện deadlock hoặc worker không được schedule. Không đặt timeout vài phút chỉ để che một task bị treo.

Nếu cần test nhiều worker chạy đồng thời, dùng latch/barrier để giữ các task ở cùng một điểm rồi xác nhận số task đã bắt đầu. Không kiểm tra concurrency bằng cách đoán thứ tự log hoặc dùng sleep.

## 11. Dọn dữ liệu và cô lập test

Test async có thể tiếp tục chạy sau khi method test kết thúc nếu test không chờ worker. Điều này làm task của test trước cập nhật dữ liệu khi test sau đã bắt đầu.

Để tránh:

- Chờ trạng thái cuối hoặc completion signal trước khi kết thúc test.
- Dùng job ID mới cho mỗi test.
- Dọn dữ liệu test sau khi worker hoàn tất.
- Không shutdown executor singleton do Spring context quản lý trong từng test method.
- Không chia sẻ mutable mock state giữa các test chạy song song.
- Nếu test dùng database thật, tạo dữ liệu theo ID riêng và rollback/cleanup có chủ đích.

Transaction test không tự động bao phủ thread nền. Một transaction mở trên test thread thường không truyền sang worker thread. Vì vậy, dữ liệu được tạo trong transaction test có thể chưa commit và worker không nhìn thấy. Với test async, hãy lưu/commit dữ liệu cần thiết trước khi gửi task hoặc dùng transaction boundary rõ ràng ở worker.

Đừng dựa vào rollback của test method để dọn dữ liệu do thread khác ghi. Worker có thể commit độc lập và dữ liệu vẫn tồn tại sau khi transaction của test thread rollback.

## 12. Phân biệt provider outage với executor rejection

Hai lỗi có thời điểm khác nhau:

| Tình huống | Thời điểm | Hành vi thường thấy |
|---|---|---|
| Provider timeout/503 | Sau khi executor đã chạy worker | Job đã PENDING; worker ghi FAILED hoặc RETRYING |
| Executor từ chối task | Khi ứng dụng gửi task vào executor | Job có thể đã được lưu nhưng task chưa được nhận; service cần xử lý rollback/trạng thái phù hợp |

Nếu executor dùng queue hữu hạn và bị đầy, TaskRejectedException có thể xảy ra ngay khi gọi phương thức async qua proxy. Hãy quyết định job đã lưu trước đó cần chuyển sang trạng thái nào hoặc transaction phải rollback ra sao. Test riêng trường hợp queue/rejection nếu tải công việc là rủi ro quan trọng.

Không dùng lỗi provider để đại diện cho executor rejection. Một lỗi xảy ra trong worker; lỗi kia xảy ra trước khi worker được nhận để chạy.

## 13. Retry có kiểm soát cho lỗi hạ tầng

Một số lỗi hạ tầng có thể tạm thời và được retry, nhưng retry cần chính sách rõ:

- Chỉ retry nhóm lỗi được xác định là tạm thời, chẳng hạn timeout hoặc một số HTTP 5xx.
- Đặt số lần thử tối đa.
- Dùng backoff và jitter để tránh nhiều worker cùng gọi lại đồng thời.
- Đặt deadline tổng thể cho job.
- Bảo đảm thao tác idempotent hoặc có idempotency key.
- Ghi nhận số lần thử và nguyên nhân cuối cùng.
- Không retry lỗi đầu vào hoặc lỗi domain không thể tự khắc phục.

Nếu dùng Spring Retry hoặc cơ chế retry riêng, test cần xác nhận số lần gọi đúng, thời gian/backoff theo cấu hình và trạng thái cuối sau khi hết lượt. Với test đơn vị, có thể dùng sleeper/clock giả hoặc policy cấu hình thời gian ngắn để tránh đợi thật. Với test tích hợp, không nên dựa vào thời gian retry dài của production.

Trong ví dụ cơ bản, worker đánh dấu FAILED ngay khi nhận provider unavailable để tập trung vào một lỗi hạ tầng. Có thể mở rộng trạng thái thành RETRYING và thêm test retry khi sản phẩm yêu cầu.

## 14. Các lỗi thường gặp khi bổ sung hai tình huống

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test kiểm tra COMPLETED ngay sau POST và thất bại ngẫu nhiên | Worker chưa hoàn tất | Chờ trạng thái cuối bằng Awaitility hoặc future |
| Test pass khi chạy riêng nhưng fail trong suite | Worker cũ còn chạy hoặc dữ liệu dùng chung | Chờ completion, dùng job ID riêng và cleanup |
| @Async chạy đồng bộ trong test | Gọi self-invocation hoặc worker được tạo bằng new | Gọi qua Spring proxy và dùng bean worker riêng |
| Test chỉ xác nhận provider được gọi | Chưa chứng minh kết quả được lưu | Assert trạng thái và dữ liệu cuối |
| Provider 503 bị coi là lỗi đầu vào | Phân loại exception quá rộng hoặc sai | Tách HTTP 4xx, HTTP 5xx và lỗi I/O |
| Request POST bị kỳ vọng 503 dù job đã nhận | Nhầm lỗi xảy ra sau khi trả 202 với lỗi đồng bộ | Kiểm tra trạng thái job sau đó |
| Task không được nhận nhưng job vẫn PENDING | Executor rejection không được xử lý | Định nghĩa chính sách khi submit bị từ chối |
| Test transaction không thấy dữ liệu trong worker | Transaction không truyền sang thread nền | Commit dữ liệu cần thiết hoặc tạo transaction ở worker |
| Test treo khi provider lỗi | Không có timeout hoặc latch không được giải phóng | Dùng timeout hữu hạn và cleanup trong finally |
| Lỗi hạ tầng làm lộ stack trace ra API | Dùng exception message trực tiếp trong response | Trả error code ổn định, log chi tiết nội bộ |

## 15. Checklist cho bài thực hành

Trước khi coi hai tình huống đã được bổ sung, xác nhận:

1. Test async gọi worker qua Spring bean/proxy.
2. Executor test có số thread và queue được cấu hình rõ.
3. Request tạo job trả 202 và một job ID có thể truy vấn.
4. Test thành công chờ đến COMPLETED và kiểm tra kết quả đã lưu.
5. Test hạ tầng mô phỏng lỗi provider có thể lặp lại, không phụ thuộc mạng công cộng.
6. Test lỗi chờ đến FAILED và kiểm tra error code ổn định.
7. Không dùng Thread.sleep để đoán thời điểm hoàn tất.
8. Mọi thao tác chờ đều có timeout hữu hạn.
9. Worker không phân loại mọi exception thành lỗi hạ tầng.
10. Dữ liệu test và executor được cô lập; worker không còn chạy sau khi test kết thúc.
11. Nếu kiểm tra HTTP 503, có test riêng xác nhận adapter chuyển 5xx thành lỗi provider unavailable.
12. Nếu có retry, số lần thử, backoff, deadline và idempotency được kiểm tra theo chính sách.

## 16. Kết quả mong đợi

Sau khi bổ sung hai tình huống, bộ test có thể chứng minh:

- Ứng dụng nhận request và trả 202 khi job được chấp nhận.
- Công việc nền thực sự chạy qua executor và cuối cùng lưu trạng thái COMPLETED.
- Khi provider không sẵn sàng, worker ghi nhận trạng thái FAILED với mã lỗi phù hợp.
- Lỗi xảy ra sau khi job được chấp nhận được quan sát qua trạng thái job, không bị nhầm với lỗi đồng bộ của request ban đầu.
- HTTP 503 hoặc lỗi kết nối được adapter chuẩn hóa thành loại lỗi hạ tầng mà worker xử lý.

Một test bất đồng bộ tốt phải chờ kết quả có ý nghĩa thay vì đoán thời gian. Một test lỗi hạ tầng tốt phải mô phỏng đúng ranh giới dependency và xác nhận trạng thái mà hệ thống công bố. Kết hợp hai tình huống này giúp kiểm thử được cả đường chạy nền bình thường lẫn khả năng ứng dụng ghi nhận sự cố của hệ thống phụ thuộc.
