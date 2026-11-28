# Mô phỏng API nhà cung cấp, lỗi mạng và thời gian chờ

## Mục tiêu và bối cảnh

Spring Cloud Service Broker thường gọi API của nhà cung cấp để tạo database, cấp user, cấu hình queue, tạo bucket hoặc thu hồi quyền truy cập. Những API này nằm ngoài tiến trình broker và có thể chậm, mất kết nối, trả lỗi tạm thời hoặc hoàn tất side effect nhưng response không tới được broker.

Nếu chỉ kiểm thử với mock method trả về thành công, ta chưa biết broker có xử lý đúng khi provider trả 429/503, đóng socket giữa chừng, trả JSON sai định dạng hoặc timeout sau khi đã tạo tài nguyên hay không. Một broker cần kiểm thử cả phản hồi bình thường lẫn các lỗi xảy ra trên đường truyền và tại backend.

Bài học này hướng dẫn mô phỏng API provider, lỗi mạng và thời gian chờ để kiểm tra service broker một cách có kiểm soát. Nội dung bao gồm provider stub, contract test, WireMock/MockWebServer, fault injection, timeout ở nhiều tầng, retry an toàn, idempotency và trạng thái operation của Open Service Broker API (OSB API).

Sau bài học, bạn có thể:

- Tách provider adapter khỏi logic nghiệp vụ để dễ thay thế backend trong test.
- Dựng HTTP stub có thể trả response thành công, lỗi hoặc chậm.
- Mô phỏng connect timeout, read timeout, reset connection, HTTP 429/5xx và payload lỗi.
- Kiểm tra timeout, retry, backoff, circuit breaker và bulkhead.
- Phân biệt request thất bại với kết quả backend chưa xác định.
- Xác minh operation bất đồng bộ và endpoint last_operation.
- Kiểm thử rằng retry không tạo tài nguyên trùng hoặc làm lộ credentials.
- Thiết kế test ổn định, có thể chạy lặp lại trong CI.

## 1. Vì sao phải mô phỏng provider API?

Một service broker có hai ranh giới chính:

- Ranh giới OSB API giữa Cloud Foundry/Kubernetes hoặc platform khác với broker.
- Ranh giới provider API giữa broker và hệ thống thực sự cấp phát tài nguyên.

Một test chỉ mock CloudProviderClient.createDatabase() thường bỏ qua các lỗi HTTP client, serialization, TLS, connection pool, timeout và response parsing. Ngược lại, test chỉ gọi provider stub mà không đi qua application service sẽ không chứng minh broker cập nhật operation hoặc trả response OSB đúng.

Cần kết hợp nhiều lớp kiểm thử:

~~~mermaid
flowchart TD
    A[OSB API request] --> B[Application Service]
    B --> C[Provider Adapter]
    C --> D[HTTP Client]
    D --> E[Provider Stub / Fault Proxy]
    E --> F[Mock Backend State]
    B --> G[(Broker Database)]
    G --> H[Operation / last_operation]
    E -->|Faults| X[Timeout / 429 / 503 / Disconnect]
~~~

Provider stub mô phỏng hợp đồng HTTP mà broker sử dụng. Fault proxy mô phỏng vấn đề đường truyền. Broker database và operation endpoint cho biết ứng dụng đã xử lý kết quả lỗi như thế nào.

### 1.1. Những tình huống cần kiểm thử

| Tình huống | Điều cần xác minh |
|---|---|
| Provider trả 200/201 | Broker parse response và lưu external resource ID |
| Provider trả 400 | Broker phân loại lỗi cấu hình/request, không retry vô hạn |
| Provider trả 401/403 | Broker phát hiện credentials/quyền của chính broker có vấn đề |
| Provider trả 404 | Broker xử lý resource không tồn tại theo ngữ cảnh |
| Provider trả 409 | Broker xử lý xung đột hoặc resource đã tồn tại |
| Provider trả 429 | Broker tôn trọng rate limit và Retry-After |
| Provider trả 500/502/503/504 | Broker retry có giới hạn nếu thao tác an toàn |
| DNS/connect failure | Broker không treo request vô hạn |
| Response chậm | Timeout được áp dụng ở đúng tầng |
| Connection bị reset | Broker phân loại lỗi và phục hồi an toàn |
| Response JSON sai | Broker không đánh dấu operation thành công |
| Backend hoàn tất nhưng response mất | Broker tra cứu kết quả trước khi tạo lại tài nguyên |

## 2. Tách provider adapter để có thể thay thế backend trong test

Application service không nên phụ thuộc trực tiếp vào HTTP client hoặc SDK cụ thể. Hãy định nghĩa một interface thể hiện nghiệp vụ broker cần:

~~~java
public interface ProviderDatabaseGateway {

    Mono<ProviderDatabase> create(
            CreateDatabaseCommand command
    );

    Mono<ProviderDatabase> findByExternalId(
            String externalId
    );

    Mono<ProviderDatabase> findByRequestKey(
            String requestKey
    );

    Mono<Void> delete(String externalId);
}
~~~

Implementation production dùng WebClient hoặc SDK provider. Trong test, có thể thay bằng HTTP stub hoặc fake implementation giữ trạng thái backend trong bộ nhớ.

Application service tiếp tục điều phối operation:

~~~java
public Mono<ProvisionResult> provision(
        ProvisionCommand command) {

    String requestKey = command.stableRequestKey();

    return providerGateway.create(
                    command.toProviderCommand(requestKey)
            )
            .map(providerDatabase ->
                    new ProvisionResult(
                            providerDatabase.id(),
                            providerDatabase.endpoint()
                    )
            );
}
~~~

Đây là ví dụ rút gọn. Trong broker thực tế, request key phải ổn định qua retry, operation và resource identity phải được lưu bền vững, và kết quả backend cần được commit trước khi operation được đánh dấu hoàn tất.

Tách adapter giúp test application service mà không cần biết provider dùng HTTP, SDK hay một giao thức khác. Đồng thời, HTTP integration test có thể kiểm tra riêng adapter với một server giả.

## 3. Dùng WireMock để mô phỏng API provider

WireMock dựng một HTTP server trong test và cho phép khai báo response theo method, path, header hoặc request body. Test có thể điều khiển status code, response body, header và độ trễ.

Một stub trả database đã tạo:

~~~java
stubFor(post(urlEqualTo("/v1/databases"))
        .willReturn(aResponse()
                .withStatus(201)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "id": "db-test-100",
                      "host": "db.test.internal",
                      "port": 5432
                    }
                    """)));
~~~

Một stub trả lỗi tạm thời:

~~~java
stubFor(post(urlEqualTo("/v1/databases"))
        .willReturn(aResponse()
                .withStatus(503)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {
                      "code": "PROVIDER_UNAVAILABLE",
                      "message": "Temporary maintenance"
                    }
                    """)));
~~~

Một stub trả rate limit:

~~~java
stubFor(post(urlEqualTo("/v1/databases"))
        .willReturn(aResponse()
                .withStatus(429)
                .withHeader("Retry-After", "2")
                .withBody("""
                    {
                      "code": "RATE_LIMITED"
                    }
                    """)));
~~~

Các ví dụ dùng API Java của WireMock. Dependency, package và cách khởi động server phụ thuộc phiên bản WireMock mà project chọn. Có thể dùng WireMock extension của JUnit hoặc khởi động server theo port động trong test.

### 3.1. Kiểm tra request broker gửi tới provider

Stub không chỉ trả response; nó còn có thể xác minh broker gửi đúng dữ liệu:

~~~java
verify(postRequestedFor(urlEqualTo("/v1/databases"))
        .withHeader("Content-Type", containing("application/json"))
        .withRequestBody(matchingJsonPath("$.name", equalTo("orders-db")))
        .withRequestBody(matchingJsonPath("$.storageGb", equalTo("100"))));
~~~

Kiểm tra thêm:

- Authorization header đúng với cơ chế provider yêu cầu.
- Idempotency key ổn định giữa các lần retry.
- Resource name hoặc tenant tag được gửi đúng.
- Broker không gửi parameters không được phép.
- Không có secret trong URL hoặc query string nếu provider không yêu cầu.

Không ghi toàn bộ request header/body ra log test nếu fixture chứa credentials. Dùng placeholder và dữ liệu giả.

### 3.2. MockWebServer là lựa chọn khác

OkHttp MockWebServer cũng cung cấp HTTP server giả, hàng đợi response và khả năng kiểm tra request đã nhận. Nó phù hợp khi muốn kiểm soát request/response theo thứ tự mà không cần khai báo nhiều mapping.

Ví dụ ý tưởng:

~~~java
mockWebServer.enqueue(
        new MockResponse()
                .setResponseCode(201)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                    {"id":"db-test-100","host":"db.test.internal"}
                    """)
);

URI providerUri = mockWebServer.url("/").uri();
~~~

Adapter nhận base URL của server test thay vì endpoint provider thật. Sau khi gọi adapter, test có thể lấy recorded request để xác minh method, path, header và body.

Chọn WireMock hoặc MockWebServer theo nhu cầu của nhóm. Không cần dùng cả hai nếu chúng cung cấp cùng một khả năng cho cùng loại test.

## 4. Mô phỏng response lỗi và payload bất thường

Provider có thể trả response không đúng kỳ vọng. Test cần kiểm tra adapter xử lý cả HTTP status lẫn nội dung body.

| Fault fixture | Ví dụ | Kỳ vọng |
|---|---|---|
| Body JSON thiếu field | Không có external ID | Không đánh dấu provision thành công |
| Content-Type sai | Trả text/plain thay vì JSON | Lỗi protocol/decoding được phân loại |
| JSON sai cú pháp | Body bị cắt hoặc malformed | Không lưu resource reference giả |
| Field sai kiểu | port là chuỗi không hợp lệ | Parse/validation failure |
| Body quá lớn | Response vượt giới hạn | Bị giới hạn và xử lý an toàn |
| Header thiếu | Không có request ID hoặc version bắt buộc | Adapter xử lý theo contract |
| Status không dự kiến | 3xx hoặc 418 | Không tự coi là thành công |

Ví dụ test response body lỗi:

~~~java
stubFor(post(urlEqualTo("/v1/databases"))
        .willReturn(aResponse()
                .withStatus(201)
                .withHeader("Content-Type", "application/json")
                .withBody("{ invalid-json ")));
~~~

HTTP status 201 không đủ để kết luận resource đã được broker quản lý thành công. Nếu body không thể parse hoặc thiếu external ID cần thiết, broker phải giữ trạng thái lỗi/không xác định và thực hiện reconciliation khi có thể.

Không để decoder exception bị biến thành null rồi lưu operation SUCCEEDED.

## 5. Phân biệt các loại timeout

Một request tới provider có thể chờ ở nhiều giai đoạn. Đặt một timeout tổng là chưa đủ để hiểu nguyên nhân.

| Timeout | Thời điểm | Ví dụ nguyên nhân |
|---|---|---|
| DNS resolution timeout | Phân giải hostname | DNS chậm hoặc không truy cập được |
| Connection pool acquire timeout | Chờ lấy connection | Pool cạn hoặc request đang chờ quá nhiều |
| Connect timeout | Thiết lập TCP/TLS connection | Provider không phản hồi hoặc network route lỗi |
| TLS handshake timeout | Bắt tay TLS | Certificate hoặc endpoint có vấn đề |
| Response/read timeout | Chờ dữ liệu phản hồi hoặc khoảng thời gian không có dữ liệu | Provider xử lý chậm hoặc socket bị treo |
| Overall request timeout | Tổng thời gian pipeline | Request vượt deadline nghiệp vụ |

Timeout nên phù hợp với operation. Một request đọc metadata có thể cần deadline ngắn; một lệnh tạo resource có thể có thời gian provider dài hơn nhưng nên được điều phối bằng async operation thay vì giữ HTTP request mở lâu.

### 5.1. Cấu hình timeout cho WebClient với Reactor Netty

Ví dụ cấu hình:

~~~java
ConnectionProvider connectionProvider =
        ConnectionProvider.builder("provider-pool")
                .maxConnections(32)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();

HttpClient httpClient =
        HttpClient.create(connectionProvider)
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        2_000
                )
                .responseTimeout(Duration.ofSeconds(4));

WebClient providerWebClient =
        WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient)
                )
                .build();
~~~

Các giá trị chỉ là ví dụ. Hãy chọn connection limit theo quota provider và năng lực broker. Cấu hình timeout của client cần được kiểm tra với phiên bản Reactor Netty đang dùng.

Có thể đặt thêm deadline cho reactive pipeline:

~~~java
return providerWebClient.post()
        .uri("/v1/databases")
        .bodyValue(command)
        .retrieve()
        .bodyToMono(ProviderDatabase.class)
        .timeout(Duration.ofSeconds(6));
~~~

Timeout Reactor giới hạn thời gian subscription chờ kết quả. Nó không bảo đảm server đã dừng xử lý request hoặc side effect backend đã bị hủy. Vì vậy cần cấu hình timeout ở HTTP client và thiết kế idempotency/reconciliation cho thao tác thay đổi tài nguyên.

### 5.2. Đừng dùng một timeout cho mọi provider

Timeout cần tính đến:

- SLA và latency thực tế của provider.
- Số lượng request đồng thời.
- Connection pool và pending acquire.
- Loại thao tác read/create/delete.
- Deadline tổng của request OSB.
- Chính sách retry và backoff.
- Thời gian platform hoặc worker có thể chờ.

Nếu timeout quá ngắn, broker tạo retry không cần thiết. Nếu quá dài, thread/connection và operation bị chiếm dụng, làm tăng queueing và giảm throughput.

## 6. Mô phỏng lỗi mạng bằng fault injection

HTTP stub mô phỏng response có kiểm soát. Fault proxy hoặc network fault injection giúp mô phỏng lỗi ở tầng truyền tải, nơi provider không gửi được một response HTTP hoàn chỉnh.

Các lỗi nên thử:

- Tăng latency giữa broker và provider.
- Ngắt kết nối trước khi request tới provider.
- Reset connection sau khi request đã được gửi.
- Chỉ gửi một phần response rồi đóng socket.
- Làm connection pool bị cạn.
- Chặn route hoặc mô phỏng DNS failure.
- Làm TLS handshake thất bại.
- Tạo packet delay hoặc packet loss trong môi trường staging.

### 6.1. Toxiproxy

Toxiproxy là công cụ tạo proxy có thể thêm toxic để mô phỏng latency, timeout, giới hạn băng thông hoặc gián đoạn kết nối. Trong integration test, broker trỏ tới proxy; proxy chuyển tiếp tới provider stub.

~~~mermaid
flowchart LR
    T[Test / Broker] --> P[Toxiproxy]
    P --> S[Provider Stub]
    P -. latency / timeout / disconnect .-> S
~~~

Ví dụ cấu hình test:

1. Khởi động provider stub.
2. Khởi động Toxiproxy trong Testcontainers hoặc môi trường test.
3. Tạo proxy từ cổng broker test tới provider stub.
4. Cấu hình WebClient dùng địa chỉ proxy.
5. Bật toxic latency hoặc timeout.
6. Gửi request từ service broker.
7. Xác minh timeout, retry, operation state và số side effect.
8. Gỡ toxic sau test để không ảnh hưởng case tiếp theo.

Toxiproxy chỉ nên được dùng trong môi trường kiểm thử được kiểm soát. Không bật fault injection tùy tiện trên provider production.

### 6.2. DNS và TLS fault

DNS failure có thể được mô phỏng bằng hostname không phân giải được hoặc một DNS test environment. TLS failure có thể dùng certificate hết hạn, hostname mismatch hoặc CA không được tin cậy trong test.

Không tắt xác minh certificate trong production chỉ để test chạy qua. Test phải chứng minh broker từ chối certificate không hợp lệ và không gửi credentials tới endpoint không đáng tin cậy.

## 7. Retry phải dựa trên loại lỗi và tính idempotent

Retry có thể cải thiện khả năng phục hồi, nhưng retry sai có thể nhân đôi side effect. Broker cần phân loại lỗi trước khi quyết định.

| Lỗi | Retry tự động |
|---|---|
| DNS/connect failure trước khi gửi request | Có thể retry có giới hạn |
| HTTP 429 | Có, tôn trọng Retry-After và quota |
| HTTP 500/502/503/504 | Có thể retry nếu operation an toàn |
| HTTP 400/401/403 | Không retry mù quáng |
| HTTP 409 | Đọc trạng thái/tra cứu resource trước khi quyết định |
| Invalid JSON/schema | Không retry cùng response; cần xử lý contract |
| Timeout sau khi gửi create | Kết quả chưa xác định; tra cứu trước khi retry |
| Cancellation | Không tự kết luận backend đã rollback |

Ví dụ retry cho một thao tác read-only:

~~~java
return providerGateway.find(resourceId)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2))
                        .jitter(0.5)
                        .filter(this::isTransientFailure)
        );
~~~

Không áp dụng trực tiếp mẫu này cho mọi lệnh create/delete. Với create, chỉ retry khi provider hỗ trợ idempotency key hoặc broker có thể tra cứu resource bằng request key ổn định.

### 7.1. Exponential backoff và Retry-After

Backoff làm khoảng chờ tăng dần sau mỗi lần thử. Jitter thêm độ ngẫu nhiên để nhiều broker instance không retry cùng thời điểm sau một sự cố provider.

Nếu provider trả Retry-After, broker nên tôn trọng giá trị đó trong giới hạn deadline và chính sách vận hành. Không retry dồn dập khi nhận 429 vì điều đó làm provider quá tải hơn.

Cần giới hạn:

- Số lần retry.
- Tổng thời gian retry.
- Số request retry đồng thời.
- Số operation đang chờ.
- Ngân sách retry theo provider hoặc tenant.

### 7.2. Timeout không đồng nghĩa thao tác thất bại

Một tình huống quan trọng:

1. Broker gửi POST create database.
2. Provider tạo database thành công.
3. Response bị mất trên mạng.
4. Broker nhận timeout.
5. Worker retry.

Broker không biết database đã được tạo hay chưa. Đây là trạng thái kết quả chưa xác định (unknown outcome).

Cách xử lý:

- Dùng idempotency key ổn định cho request create nếu provider hỗ trợ.
- Nếu không, dùng resource name hoặc metadata tag ổn định.
- Tra cứu provider theo request key hoặc external reference trước khi gửi create lần nữa.
- Nếu resource tồn tại và owner khớp, lưu external ID và tiếp tục.
- Nếu chưa tồn tại, retry theo policy.
- Nếu không thể xác minh, giữ operation ở trạng thái cần reconciliation.

Không tạo một idempotency key mới cho mỗi lần retry. Điều đó khiến provider hiểu mỗi lần là một yêu cầu mới.

## 8. Kiểm thử operation bất đồng bộ của OSB API

Provision, update và deprovision có thể cần xử lý bất đồng bộ. Nếu platform gửi accepts_incomplete=true và broker không thể hoàn tất trong request, broker có thể lưu operation, trả 202 Accepted cùng operation token rồi tiếp tục xử lý ở worker.

Trong test cần xác minh:

1. Operation và yêu cầu công việc được ghi bền vững trước response 202.
2. Worker gọi provider qua adapter.
3. Provider trả lỗi tạm thời thì operation chuyển RETRY_WAIT hoặc trạng thái nội bộ tương đương.
4. Provider phục hồi thì worker retry với cùng idempotency key.
5. Khi thành công, broker cập nhật instance và operation.
6. last_operation phản ánh in progress, succeeded hoặc failed đúng thời điểm.

Ví dụ test logic với provider stub trả 503 rồi 201:

~~~java
stubFor(post(urlEqualTo("/v1/databases"))
        .inScenario("provider-recovers")
        .whenScenarioStateIs(Scenario.STARTED)
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("available"));

stubFor(post(urlEqualTo("/v1/databases"))
        .inScenario("provider-recovers")
        .whenScenarioStateIs("available")
        .willReturn(aResponse()
                .withStatus(201)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"id":"db-test-100"}
                    """)));
~~~

Test cần dùng clock/retry scheduler phù hợp để không phải chờ thời gian dài. Sau khi worker hoàn tất, gọi last_operation và xác nhận trạng thái succeeded, external resource ID được lưu và số lần tạo backend phù hợp với idempotency policy.

### 8.1. Phân biệt lỗi trước và sau khi trả 202

Nếu lỗi xảy ra trước khi broker chấp nhận operation, broker có thể trả HTTP error tương ứng. Nếu broker đã trả 202, response ban đầu không thể đổi thành 503 sau đó.

Lỗi phát sinh trong worker phải được lưu vào operation và trả qua last_operation. Không tạo một response HTTP mới cho request đã kết thúc.

Bind và unbind trong OSB API chuẩn là thao tác đồng bộ. Không dùng test async provision để suy ra rằng mọi thao tác binding đều có operation token và polling giống nhau.

## 9. Kiểm thử timeout và cancellation

Timeout test cần xác minh cả thời gian phản hồi và side effect backend.

Ví dụ provider stub cố tình trả chậm:

~~~java
stubFor(get(urlEqualTo("/v1/databases/db-test-100"))
        .willReturn(aResponse()
                .withFixedDelay(5_000)
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"id":"db-test-100"}
                    """)));
~~~

Nếu client timeout sau ba giây, test xác nhận:

- Application nhận timeout exception được phân loại.
- Request không treo vô hạn.
- Không đánh dấu operation thành công khi chưa có kết quả.
- Không retry thao tác không an toàn.
- Metrics ghi nhận timeout.
- Connection hoặc task được giải phóng theo khả năng của client.

Với lệnh create, cần test riêng tình huống provider đã tạo resource nhưng response chậm hơn timeout. Có thể dùng stub stateful để ghi nhận side effect rồi trì hoãn response. Sau timeout, broker phải lookup resource trước khi quyết định create lại.

Cancellation ở Reactor chỉ dừng việc chờ subscription theo cơ chế của client. Một số blocking SDK hoặc provider vẫn tiếp tục xử lý. Test phải xác minh broker không coi client disconnect là bằng chứng backend đã rollback.

## 10. Circuit breaker và bulkhead khi provider liên tục lỗi

Nếu provider liên tục timeout hoặc trả 503, broker có thể tạo nhiều request thất bại và làm cạn connection pool. Circuit breaker tạm ngừng gọi provider sau ngưỡng lỗi; bulkhead giới hạn số lời gọi đồng thời.

Các trạng thái circuit breaker thường gồm:

- CLOSED: cho phép request đi qua.
- OPEN: từ chối nhanh trong thời gian chờ.
- HALF_OPEN: cho phép một số probe để xác định provider đã phục hồi chưa.

Trong test:

1. Stub provider trả liên tục 503.
2. Gửi đủ số request để breaker mở.
3. Xác nhận request tiếp theo bị fail fast mà không gọi provider.
4. Cho provider trả 200 sau thời gian open.
5. Xác nhận half-open probe thành công và breaker đóng lại.

Bulkhead test nên xác minh số request đồng thời không vượt giới hạn. Khi quá giới hạn, broker trả hoặc lưu lỗi quá tải theo policy thay vì tạo hàng đợi không kiểm soát.

Không dùng circuit breaker để thay thế retry hoặc operation persistence. Nó là cơ chế bảo vệ dependency, còn operation record vẫn là nguồn sự thật cho tiến độ lifecycle.

## 11. Kiểm thử provider contract và schema

Provider stub phải phản ánh đúng hợp đồng mà adapter mong đợi. Nếu stub chỉ trả những field mà test tự nghĩ ra, test có thể xanh dù provider thật đã thay đổi schema.

Nên lưu các fixture response đại diện:

- Create success.
- Resource lookup success.
- Delete success.
- Not found.
- Rate limited.
- Authentication failure.
- Temporary unavailable.
- Validation error.
- Malformed response.

Nếu provider có OpenAPI specification hoặc contract chính thức, dùng nó để kiểm tra request/response schema. Khi provider thay đổi API version, chạy contract test để phát hiện mismatch trước khi deploy broker.

Không biến fixture thành bản sao cứng của mọi chi tiết provider nếu adapter chỉ cần một phần dữ liệu. Nhưng các field quan trọng như external ID, status, endpoint và credentials reference cần được xác minh.

### 11.1. Contract test khác với unit test

| Loại test | Kiểm tra gì |
|---|---|
| Unit test | Phân loại exception, retry policy, mapping dữ liệu |
| Adapter integration test | HTTP method, URL, headers, serialization, status handling |
| Provider contract test | Request/response khớp contract đã thỏa thuận |
| OSB API test | Endpoint broker trả status/body theo OSB API |
| End-to-end test | Platform flow từ provision tới bind và deprovision |
| Fault injection test | Broker phục hồi khi network/provider lỗi |

Không cần gọi provider production trong CI để chứng minh adapter hoạt động. Dùng stub/contract fixture để test lặp lại được; kiểm thử live provider có thể chạy ở môi trường riêng với tài khoản và resource thử nghiệm.

## 12. Dùng thời gian ảo để kiểm thử retry và backoff

Nếu retry policy dùng Reactor Retry.backoff, test có thể phải chờ thực tế. Reactor Test cung cấp StepVerifier.withVirtualTime để kiểm soát thời gian trong pipeline hỗ trợ scheduler ảo.

Ví dụ ý tưởng:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> attemptCounter.incrementAndGet() < 3
                ? Mono.error(new ProviderUnavailableException())
                : Mono.just("ok"))
            .retryWhen(
                    Retry.backoff(2, Duration.ofSeconds(1))
                            .jitter(0)
            )
)
.thenAwait(Duration.ofSeconds(3))
.expectNext("ok")
.verifyComplete();
~~~

Ví dụ minh họa cần đặt việc tạo publisher bên trong supplier của withVirtualTime để scheduler được thay thế trước khi pipeline được dựng. Với HTTP client hoặc scheduler tự quản lý, virtual time có thể không điều khiển được socket timeout thật; dùng stub delay hoặc fault proxy trong integration test cho trường hợp đó.

Virtual time hữu ích để kiểm tra số lần thử và lịch backoff mà không làm CI phải chờ lâu. Không dùng nó để kết luận TCP, TLS hoặc DNS hoạt động đúng; những điều đó cần test ở tầng mạng.

## 13. Bảo mật trong test provider

Provider request có thể chứa API token, client secret hoặc thông tin tenant. Test cần xác nhận broker không làm lộ dữ liệu khi lỗi xảy ra.

Các kiểm tra:

- Authorization header không xuất hiện trong log.
- Error response gửi platform không chứa provider token.
- Exception message được sanitize trước khi lưu description.
- Fixture chỉ dùng credentials giả.
- Không commit file .env hoặc secret thật.
- TLS certificate verification không bị tắt trong cấu hình production.
- Request body không chứa field ngoài schema.
- Provider stub không mở cổng ra mạng ngoài nếu không cần.

Khi test lỗi 401/403 từ provider, phải phân biệt credentials của broker dùng với provider với credentials của platform dùng với broker. Provider từ chối broker không có nghĩa platform caller chưa được xác thực.

## 14. Ma trận test lỗi provider và mạng

Một ma trận giúp không bỏ sót tình huống:

| Nhóm | Fault | Kỳ vọng ở broker |
|---|---|---|
| HTTP | 400 | Lưu lỗi cuối hoặc trả validation/dependency error phù hợp |
| HTTP | 401/403 | Cảnh báo credentials/quyền provider; không retry mù quáng |
| HTTP | 404 | Phân biệt resource không tồn tại với endpoint sai |
| HTTP | 409 | Lookup trạng thái và xử lý duplicate/conflict |
| HTTP | 429 | Backoff, tôn trọng Retry-After |
| HTTP | 500/502/503/504 | Retry có giới hạn nếu thao tác idempotent |
| Network | DNS failure | Timeout/failure có kiểm soát |
| Network | Connect refused | Không treo request |
| Network | Connection reset | Phân loại kết quả; lookup nếu có side effect |
| Network | Read timeout | Không giả định create đã thất bại |
| Network | TLS validation error | Từ chối kết nối, không gửi secret |
| Payload | Invalid JSON | Không đánh dấu thành công |
| Payload | Missing external ID | Giữ operation ở trạng thái lỗi/unknown |
| Load | Pool exhausted | Bulkhead/backpressure bảo vệ broker |
| Recovery | Provider phục hồi | Retry hoặc reconciliation hoàn tất đúng một resource |

Với mỗi case, kiểm tra cả ba lớp:

1. HTTP response hoặc operation state mà platform nhìn thấy.
2. Bản ghi instance/operation trong broker database.
3. Side effect và resource thực tế trong provider stub.

Chỉ kiểm tra status code là chưa đủ. Một request trả 503 nhưng đã tạo hai database vẫn là test thất bại.

## 15. Tổ chức test trong Spring Boot

Một cấu trúc test có thể gồm:

~~~text
src/test/java/
  .../
    provider/
      ProviderDatabaseGatewayTest.java
      ProviderContractTest.java
      ProviderTimeoutTest.java
    broker/
      ProvisionControllerTest.java
      LastOperationControllerTest.java
      BindingLifecycleTest.java
    resilience/
      RetryPolicyTest.java
      CircuitBreakerTest.java
    support/
      ProviderStubConfiguration.java
      ProviderFixtures.java
~~~

Đây là cấu trúc gợi ý; hãy dùng convention của project hiện tại.

Dùng @SpringBootTest cho integration test cần application context thật. Dùng WebTestClient để gọi endpoint WebFlux và WireMock/MockWebServer cho provider API. Nếu database hoặc queue cần kiểm thử thực, có thể dùng Testcontainers để khởi động dependency cô lập.

Mỗi test nên:

- Dùng port động.
- Dùng resource ID duy nhất.
- Reset stub mapping và request journal giữa các case.
- Dọn container/proxy sau test.
- Không phụ thuộc thứ tự chạy test.
- Không dùng sleep cố định nếu có thể dùng polling assertion hoặc virtual time.
- Giới hạn tổng thời gian để test không treo CI.

### 15.1. Kiểm tra số side effect

Đối với provision, hãy đếm số lần provider nhận lệnh create và số resource thực sự được tạo. Với retry hợp lệ, nhiều HTTP attempt có thể xảy ra nhưng chỉ được tạo một resource logic.

Ví dụ:

~~~java
verify(lessThanOrEqualTo(3),
        postRequestedFor(urlEqualTo("/v1/databases")));

assertThat(providerState.resources())
        .containsOnlyKeys("db-test-100");
~~~

Cú pháp verify cụ thể phụ thuộc WireMock và fake provider state mà test sử dụng. Điều quan trọng là phân biệt số lần HTTP request với số tài nguyên cuối cùng. Idempotency có thể cho phép nhiều lần gửi request nhưng chỉ một side effect.

## 16. Những lỗi kiểm thử thường gặp

- **Chỉ mock method Java:** bỏ qua serialization, HTTP status, header và timeout thật.
- **Dùng provider production trong unit test:** test phụ thuộc mạng, quota và dữ liệu thật.
- **Stub chỉ có response thành công:** không kiểm tra failure mode.
- **Chỉ đặt Reactor timeout:** bỏ qua connect/read timeout và tác vụ backend vẫn tiếp tục.
- **Retry mọi exception:** có thể tạo resource trùng hoặc lặp lỗi permanent.
- **Dùng idempotency key mới mỗi lần retry:** provider không nhận ra cùng operation.
- **Coi timeout là thất bại chắc chắn:** có thể bỏ sót resource đã được tạo.
- **Không kiểm tra last_operation:** operation async có thể bị kẹt dù API ban đầu trả 202.
- **Không kiểm tra side effect:** test status xanh nhưng backend giả đã tạo duplicate.
- **Không reset WireMock/Toxiproxy:** test phụ thuộc thứ tự hoặc gây flaky.
- **Dùng sleep cố định:** test chậm và không ổn định trên CI.
- **Tắt TLS verification để test dễ chạy:** che giấu lỗi bảo mật.
- **Ghi token vào test log:** làm lộ secret dù chỉ ở môi trường CI.

## 17. Quy trình xây dựng bộ test fault-tolerance

Khi tích hợp một provider mới hoặc thay đổi HTTP client, hãy triển khai theo thứ tự:

1. Xác định provider contract và các operation broker sử dụng.
2. Tách provider adapter khỏi application service.
3. Dựng stub cho success, validation error, authentication error và transient failure.
4. Kiểm tra method, URL, header, body và response parsing.
5. Cấu hình connection pool, connect timeout, response timeout và deadline tổng.
6. Thêm test response chậm, connection reset, DNS/TLS failure hoặc fault proxy.
7. Phân loại lỗi retryable và permanent.
8. Dùng idempotency key ổn định cho side effect có thể được retry.
9. Kiểm thử kết quả unknown sau timeout bằng lookup/reconciliation.
10. Kiểm thử circuit breaker, bulkhead và rate limit nếu có.
11. Kiểm thử OSB operation và last_operation cho workflow async.
12. Kiểm tra audit/log không lộ credentials.
13. Chạy integration test lặp lại và xác nhận cleanup test resource.
14. Theo dõi timeout, retry, provider latency và operation age trong môi trường staging.

## Kết luận

Mô phỏng provider API và lỗi mạng giúp kiểm tra hành vi thực tế của service broker khi dependency chậm, mất kết nối hoặc trả kết quả bất thường. WireMock và MockWebServer phù hợp để kiểm tra HTTP contract; Toxiproxy hoặc fault injection phù hợp để mô phỏng lỗi truyền tải; virtual time giúp kiểm tra retry/backoff mà không chờ lâu.

Trong Spring Cloud Service Broker, cần kiểm tra cả response OSB, operation state và side effect ở provider. Timeout không chứng minh thao tác chưa xảy ra; retry chỉ an toàn khi có idempotency key ổn định hoặc cơ chế lookup/reconciliation. Khi kết hợp adapter tách biệt, timeout ở nhiều tầng, retry có giới hạn, fault injection và test phục hồi, broker sẽ giữ được trạng thái nhất quán ngay cả khi provider hoặc mạng gặp sự cố.
