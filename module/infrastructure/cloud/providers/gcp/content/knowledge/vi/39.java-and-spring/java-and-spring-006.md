# Timeouts, retries, pagination và long-running operations

Một ứng dụng Java trên Google Cloud thường gọi nhiều API: đọc cấu hình từ Secret Manager, liệt kê object trong Cloud Storage, truy vấn BigQuery, tạo tài nguyên Compute Engine hoặc triển khai pipeline Dataflow. Những lời gọi này đi qua mạng và phụ thuộc vào dịch vụ ở xa. Chúng có thể chậm, tạm thời không khả dụng, trả về hàng nghìn kết quả hoặc cần nhiều phút để hoàn tất.

Nếu không đặt timeout, một thread có thể bị giữ quá lâu. Nếu retry mọi lỗi, hệ thống có thể tạo thêm tải khi dịch vụ đang quá tải hoặc thực hiện lặp một thao tác ghi. Nếu không xử lý pagination, ứng dụng chỉ đọc trang đầu hoặc tải toàn bộ dữ liệu vào bộ nhớ. Nếu chờ một thao tác dài bằng một HTTP request duy nhất, người dùng và gateway có thể hết thời gian chờ dù tác vụ phía Google Cloud vẫn đang chạy.

Trong Java và Spring, cần phối hợp bốn cơ chế:

- **Timeout và deadline:** giới hạn thời gian chờ cho một lần gọi và cho toàn bộ công việc.
- **Retry:** thử lại lỗi tạm thời theo chính sách có giới hạn, backoff và jitter.
- **Pagination:** đọc tập kết quả lớn theo từng trang, dùng page token để tiếp tục.
- **Long-running operation (LRO):** khởi chạy tác vụ dài, lưu operation name và theo dõi trạng thái bằng polling hoặc callback.

Các Cloud Client Libraries for Java dùng GAX để cung cấp retry, paging và LRO cho nhiều API Google Cloud. Với HTTP API hoặc dịch vụ Spring bên ngoài, ứng dụng có thể dùng RestClient hoặc WebClient và cấu hình chính sách tương ứng. Mục tiêu là giữ cho ứng dụng phản hồi trong giới hạn đã định, không tạo thao tác trùng và có thể tiếp tục công việc sau khi tiến trình bị gián đoạn.

Sau bài học này, bạn có thể:

- Phân biệt connect timeout, per-attempt timeout, total timeout và deadline của request.
- Chọn lỗi nào nên retry và lỗi nào cần trả về ngay.
- Thiết kế exponential backoff, jitter, retry budget và idempotency.
- Dùng RetrySettings của Google API Client Libraries for Java.
- Cấu hình timeout và retry cho Spring WebClient.
- Đọc hết kết quả phân trang bằng PagedResponse hoặc page token.
- Theo dõi, khôi phục và xử lý lỗi của OperationFuture.
- Đo lường timeout, retry, pagination và thời gian hoàn tất LRO trong production.

## 1. Timeout và deadline

### Vì sao phải đặt timeout?

Khi gọi một API từ ứng dụng Java, thời gian chờ có thể bao gồm:

1. Chờ lấy connection từ connection pool.
2. Thiết lập TCP và TLS tới máy chủ.
3. Gửi request và chờ server xử lý.
4. Nhận response headers và body.
5. Giải mã response, retry hoặc polling nếu cần.

Nếu chỉ cấu hình một timeout ở tầng ứng dụng mà không giới hạn các tầng thấp hơn, request vẫn có thể bị giữ ở connection pool hoặc socket lâu hơn dự kiến. Timeout nên được thiết kế từ ngân sách thời gian mà người dùng chấp nhận.

### Các loại timeout

| Loại | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Connection timeout | Thời gian thiết lập kết nối TCP tới server | Tối đa 2 giây để mở kết nối |
| Read/response timeout | Thời gian chờ dữ liệu phản hồi hoặc khoảng chờ giữa dữ liệu | Tối đa 5 giây để nhận response |
| Per-attempt RPC timeout | Thời gian cho một lần gọi API | Mỗi lần gọi tối đa 3 giây |
| Total operation timeout | Tổng thời gian của lần gọi logic, bao gồm delay và retry | Tối đa 10 giây cho cả chuỗi retry |
| Application deadline | Thời gian tối đa của toàn bộ request nghiệp vụ | HTTP request phải hoàn tất trong 8 giây |
| LRO polling timeout | Thời gian client tiếp tục theo dõi tác vụ dài | Theo dõi operation tối đa 2 giờ |

**Timeout** thường giới hạn một bước hoặc một lần chờ. **Deadline** là mốc thời gian cuối cùng mà toàn bộ công việc phải hoàn thành. Khi có nhiều tầng, deadline ở tầng trên phải lớn hơn tổng ngân sách của các thao tác bên dưới, nhưng vẫn nằm trong giới hạn của request gốc.

Ví dụ, API Spring có deadline 8 giây. Nếu nó gọi hai dịch vụ nối tiếp, mỗi dịch vụ không nên có total timeout 8 giây. Có thể phân bổ 3 giây cho dịch vụ thứ nhất, 3 giây cho dịch vụ thứ hai và giữ phần còn lại cho xử lý, serialization và phản hồi. Nếu một thao tác cần thời gian dài hơn nhiều, nên chuyển sang mô hình LRO hoặc xử lý bất đồng bộ.

### Không nhầm timeout với hủy tác vụ

Client hết thời gian chờ không có nghĩa server đã dừng xử lý. Request có thể đã tới server và server có thể đã ghi dữ liệu trước khi response bị mất. Điều này đặc biệt quan trọng với thao tác tạo tài nguyên, thanh toán hoặc gửi lệnh triển khai. Sau timeout, trạng thái thực tế có thể là:

- Request chưa tới server.
- Server đã nhận nhưng chưa thực hiện.
- Server đã thực hiện thành công nhưng response không tới client.
- Server vẫn đang xử lý.

Vì vậy, với thao tác ghi, timeout phải đi cùng thiết kế idempotency và cách tra cứu trạng thái.

## 2. Retry đúng cách

### Lỗi nào có thể retry?

Retry phù hợp với lỗi tạm thời, khi có cơ hội lần gọi tiếp theo thành công. Một số trường hợp thường được xem xét:

| Lỗi | Có nên retry? | Ghi chú |
|---|---|---|
| Mất kết nối, connection reset, timeout mạng | Có điều kiện | Chỉ retry nếu thao tác có thể lặp an toàn hoặc có idempotency key |
| HTTP 429 / RESOURCE_EXHAUSTED | Thường có | Tôn trọng Retry-After hoặc thông tin retry của server |
| HTTP 500, 502, 503, 504 | Thường có | Dùng backoff; không retry vô hạn |
| gRPC UNAVAILABLE | Thường có | Lỗi dịch vụ hoặc kết nối tạm thời |
| gRPC DEADLINE_EXCEEDED | Có điều kiện | Cần xem thao tác đã được server thực hiện hay chưa |
| HTTP 400 / INVALID_ARGUMENT | Không | Sửa dữ liệu hoặc request |
| HTTP 401 / UNAUTHENTICATED | Không lặp vô hạn | Làm mới thông tin xác thực theo cơ chế đúng rồi thử lại có giới hạn |
| HTTP 403 / PERMISSION_DENIED | Không | Sửa IAM hoặc cấu hình quyền |
| HTTP 404 / NOT_FOUND | Thường không | Trừ trường hợp eventual consistency được tài liệu API cho phép |
| HTTP 409 / ABORTED | Phụ thuộc API | Có thể cần đọc lại state, cập nhật version hoặc thực hiện lại transaction |

Đây là hướng dẫn chung. Hãy tuân theo retry policy của từng Google Cloud API vì mã lỗi giống nhau có thể mang ngữ nghĩa khác nhau theo thao tác.

### Exponential backoff

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại:

\[
delay_n = \min(maxDelay,\ initialDelay \times multiplier^{n-1}), \quad n \ge 1
\]

Ví dụ với initial delay 200 ms, multiplier 2 và max delay 2 giây:

| Lần retry | Delay trước retry (chưa tính jitter) |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 trở đi | 2.000 ms |

Backoff giảm áp lực lên dịch vụ đang gặp sự cố. Tuy nhiên, nếu mọi client đều retry đúng cùng một thời điểm, chúng có thể tạo thành đợt tải đồng bộ.

### Jitter

Jitter thêm yếu tố ngẫu nhiên vào thời gian chờ để phân tán retry. Google Cloud Java Client Libraries tự bật jitter cho retry; không cần tự đặt cờ jitter trong cấu hình GAX hiện hành. Với Spring hoặc HTTP client tự triển khai, có thể dùng full jitter:

\[
actualDelay = random(0,\ cappedExponentialDelay)
\]

Jitter giúp giảm hiện tượng nhiều instance cùng retry vào một thời điểm sau một lần mất kết nối hoặc lỗi diện rộng.

### Retry budget và giới hạn

Một retry policy cần ít nhất:

- Số lần thử tối đa hoặc total timeout.
- Initial delay, multiplier và max delay.
- Timeout cho từng attempt.
- Danh sách mã lỗi được retry.
- Ngân sách retry cho toàn hệ thống hoặc từng dependency.

Không retry vô hạn. Retry ở nhiều tầng có thể nhân số lần gọi. Ví dụ, API gateway retry 3 lần, Spring service retry 3 lần và Cloud Client Library retry 3 lần có thể tạo ra tối đa 27 lần gọi tới backend cho một request ban đầu. Hãy xác định tầng nào sở hữu retry và tắt hoặc giới hạn retry trùng lặp ở tầng khác.

Khi dịch vụ trả Retry-After hoặc gRPC RetryInfo, hãy tôn trọng thời gian server yêu cầu trong giới hạn deadline và chính sách của ứng dụng.

## 3. Idempotency trước khi retry thao tác ghi

Một thao tác là **idempotent** nếu thực hiện nhiều lần với cùng đầu vào tạo ra cùng trạng thái cuối cùng như thực hiện một lần. Ví dụ, cập nhật một tài nguyên về một cấu hình xác định thường có thể thiết kế idempotent; tạo một đơn hàng mới thường không tự động idempotent.

### Tình huống nguy hiểm

Ứng dụng gửi yêu cầu tạo tài nguyên. Server tạo thành công nhưng response bị mất do mạng. Client thấy timeout và gửi lại. Nếu API không nhận diện lần gửi lại, có thể tạo hai tài nguyên hoặc hai giao dịch.

Các cách giảm rủi ro:

- Dùng requestId, idempotency key hoặc client token nếu API hỗ trợ.
- Dùng resource ID do client xác định khi API cho phép.
- Dùng điều kiện cập nhật như ETag, generation hoặc If-Match để tránh ghi đè thay đổi mới.
- Sau timeout, truy vấn trạng thái theo resource name hoặc operation name trước khi gửi lại.
- Thiết kế endpoint nghiệp vụ có unique key và lưu kết quả xử lý để trả lại cùng kết quả khi nhận request trùng.

Không tự thêm header Idempotency-Key rồi giả định Google Cloud API sẽ hiểu header đó. Chỉ sử dụng cơ chế được API cụ thể hỗ trợ và kiểm tra thời hạn lưu idempotency key.

### Phân loại thao tác

| Thao tác | Cách retry |
|---|---|
| GET/list/read | Thường retry được với lỗi tạm thời |
| PUT cập nhật về trạng thái xác định | Thường idempotent, nhưng cần xem precondition |
| DELETE tài nguyên | Có thể idempotent về trạng thái cuối; lần sau có thể trả NOT_FOUND |
| POST tạo tài nguyên | Chỉ retry khi API hỗ trợ request ID/idempotency hoặc có thể kiểm tra trạng thái trước |
| Chuyển tiền, tạo đơn, gửi email | Cần idempotency key hoặc cơ chế chống trùng ở tầng nghiệp vụ |

Retry không thay thế transaction, optimistic locking hoặc kiểm tra trạng thái nghiệp vụ.

## 4. Cấu hình retry cho Google Cloud Java Client Libraries

### GAX RetrySettings

Các Cloud Client Libraries for Java sử dụng GAX cho nhiều thao tác RPC. RetrySettings điều khiển thời gian chờ và retry:

| Thuộc tính | Ý nghĩa |
|---|---|
| initialRetryDelayDuration | Thời gian chờ trước lần retry đầu tiên |
| retryDelayMultiplier | Hệ số tăng delay |
| maxRetryDelayDuration | Giới hạn delay |
| initialRpcTimeoutDuration | Timeout cho RPC đầu tiên |
| rpcTimeoutMultiplier | Hệ số thay đổi RPC timeout giữa các lần |
| maxRpcTimeoutDuration | Giới hạn timeout mỗi RPC |
| totalTimeoutDuration | Tổng thời gian tối đa của operation retry |
| maxAttempts | Giới hạn số lần gọi |

Một cấu hình minh họa:

~~~java
import com.google.api.gax.retrying.RetrySettings;
import java.time.Duration;

RetrySettings retrySettings =
    RetrySettings.newBuilder()
        .setInitialRetryDelayDuration(Duration.ofMillis(200))
        .setRetryDelayMultiplier(2.0)
        .setMaxRetryDelayDuration(Duration.ofSeconds(2))
        .setInitialRpcTimeoutDuration(Duration.ofSeconds(2))
        .setRpcTimeoutMultiplier(1.0)
        .setMaxRpcTimeoutDuration(Duration.ofSeconds(2))
        .setTotalTimeoutDuration(Duration.ofSeconds(10))
        .setMaxAttempts(5)
        .build();
~~~

Đây là cấu hình ví dụ, không phải giá trị tối ưu cho mọi API. GAX dùng cả giới hạn số lần thử và total timeout; lần gọi không được vượt quá ngân sách tổng. Jitter được áp dụng tự động.

Trong GAX, RPC timeout bằng Duration.ZERO có thể cho phép một lần RPC chờ vô thời hạn cho tới khi kết nối bị ngắt hoặc connect timeout xảy ra. Không dựa vào giá trị này như một deadline nghiệp vụ; hãy đặt total timeout hoặc max attempts rõ ràng.

### Gắn RetrySettings vào RPC cụ thể

Mỗi Cloud Client Library có lớp Settings riêng. Tên RPC và cách truy cập builder phụ thuộc thư viện. Ví dụ khái quát:

~~~java
// Minh họa: tên settings và RPC builder phụ thuộc API đang sử dụng.
SomeServiceSettings.Builder settingsBuilder =
    SomeServiceSettings.newBuilder();

settingsBuilder.someReadCallSettings()
    .setRetrySettings(retrySettings);

SomeServiceClient client =
    SomeServiceClient.create(settingsBuilder.build());
~~~

Không giả định một RetrySettings áp dụng cho toàn bộ client. Hãy xem StubSettings của đúng thư viện để biết RPC nào có retry, mã lỗi nào được retry và cấu hình nào là retry hay polling. Service team thường đã chọn giá trị mặc định dựa trên hành vi của API; chỉ ghi đè khi có số liệu và lý do rõ ràng.

### Tránh retry hai lần

Cloud Client Libraries có thể tự retry một số RPC theo cấu hình mặc định. Nếu bọc các lời gọi đó bằng Resilience4j hoặc retry của Spring, hãy xác định rõ tầng nào chịu trách nhiệm. Với thao tác đã có GAX retry, thường nên giữ retry trong client library và dùng circuit breaker hoặc bulkhead ở tầng ứng dụng thay vì lặp lại cùng một policy.

## 5. Timeout và retry trong Spring WebClient

Spring WebClient phù hợp với ứng dụng reactive hoặc khi cần xử lý nhiều request đồng thời. Timeout cần cấu hình ở HTTP connector để giới hạn connection và response; Mono.timeout có thể đặt thêm deadline cho luồng reactive.

### Cấu hình connection và response timeout

Ví dụ dùng Reactor Netty:

~~~java
import io.netty.channel.ChannelOption;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        HttpClient httpClient =
            HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(5));

        return WebClient.builder()
            .baseUrl("https://partner.example.com")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Connection timeout giới hạn thời gian kết nối; response timeout giới hạn khoảng chờ phản hồi ở tầng HTTP client. Với luồng truyền dữ liệu dài, cần cân nhắc read/write timeout và idle timeout phù hợp với giao thức.

### Retry có điều kiện

Ví dụ dưới đây chỉ retry lỗi mạng và một số mã trạng thái tạm thời. Lọc lỗi cần được điều chỉnh theo API thực tế:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> loadStatus(String id) {
    return partnerWebClient.get()
        .uri("/jobs/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(error ->
                    error instanceof WebClientRequestException
                    || (error instanceof WebClientResponseException response
                        && (response.getStatusCode().value() == 429
                            || response.getStatusCode().is5xxServerError()))))
        .timeout(Duration.ofSeconds(10));
}
~~~

Đoạn code minh họa retry GET. Với POST hoặc thao tác ghi, chỉ thêm retry sau khi đã có idempotency. Timeout và retry phải nằm trong một deadline tổng; nếu mỗi lần retry lại được cấp timeout mới mà không có giới hạn tổng, request có thể kéo dài ngoài ngân sách của caller.

Ví dụ này minh họa lọc lỗi, chưa đọc header Retry-After. Nếu API đối tác trả Retry-After, hãy bổ sung retry policy có thể đọc response header và lên lịch lần thử tiếp theo theo thời gian server yêu cầu, đồng thời vẫn giữ deadline tổng.

Khi dùng Spring RestClient đồng bộ, cấu hình timeout ở ClientHttpRequestFactory hoặc HTTP client nền. RestClient là lựa chọn đồng bộ hiện đại; WebClient phù hợp cho non-blocking và streaming. Không dựa vào timeout của tầng controller để thay thế timeout ở socket hoặc HTTP connector.

## 6. Pagination: đọc dữ liệu theo từng trang

### Vì sao API phân trang?

API thường giới hạn số bản ghi trong một response để tránh response quá lớn, tốn bộ nhớ hoặc chậm. Một list request có thể trả:

- Danh sách item của trang hiện tại.
- nextPageToken để yêu cầu trang tiếp theo.
- Có thể có tổng số bản ghi, nhưng không phải API nào cũng trả total count.

pageSize là số item tối đa client mong muốn. Server có thể trả ít hơn; không được suy luận rằng trang đã hết chỉ vì số item nhỏ hơn pageSize. Điều kiện kết thúc thường là không còn nextPageToken.

### Dùng PagedResponse của GAX

Nhiều list method trong Cloud Client Libraries for Java trả về PagedResponse. iterateAll() tự động tải trang tiếp theo khi cần:

~~~java
import com.google.cloud.secretmanager.v1.ListSecretsRequest;
import com.google.cloud.secretmanager.v1.ProjectName;
import com.google.cloud.secretmanager.v1.Secret;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

void listAllSecrets(String projectId) throws Exception {
    try (SecretManagerServiceClient client =
             SecretManagerServiceClient.create()) {

        ListSecretsRequest request =
            ListSecretsRequest.newBuilder()
                .setParent(ProjectName.of(projectId).toString())
                .setPageSize(100)
                .build();

        SecretManagerServiceClient.ListSecretsPagedResponse response =
            client.listSecrets(request);

        for (Secret secret : response.iterateAll()) {
            process(secret);
        }
    }
}
~~~

iterateAll() tải lười từng trang khi vòng lặp cần dữ liệu. Điều này tiện cho xử lý toàn bộ kết quả, nhưng không có nghĩa toàn bộ quá trình không tốn thời gian hoặc không phát sinh request mạng. Mỗi trang tiếp theo vẫn có thể gặp timeout, retry hoặc lỗi quyền.

Nếu chỉ cần trang hiện tại, dùng response.getPage().getValues(). Để điều khiển thủ công, lấy getNextPageToken() và truyền lại token vào request tiếp theo.

### Phân trang thủ công

~~~java
String pageToken = "";

do {
    ListSecretsRequest.Builder builder =
        ListSecretsRequest.newBuilder()
            .setParent(ProjectName.of(projectId).toString())
            .setPageSize(100);

    if (!pageToken.isEmpty()) {
        builder.setPageToken(pageToken);
    }

    var page = client.listSecrets(builder.build());

    for (Secret secret : page.getPage().getValues()) {
        process(secret);
    }

    pageToken = page.getNextPageToken();
} while (!pageToken.isEmpty());
~~~

Mỗi lần gọi lấy một trang. Cách này phù hợp khi cần checkpoint tiến độ, trả từng trang cho caller hoặc dừng sau một giới hạn số bản ghi.

### Pagination trong REST API và Spring

Với REST API, request thường có pageSize và pageToken, response có items và nextPageToken:

~~~http
GET /v1/projects/my-project/secrets?pageSize=100&pageToken=eyJvZmZzZXQiOjEwMH0
~~~

Response minh họa:

~~~json
{
  "items": [
    { "name": "projects/my-project/secrets/db-password" }
  ],
  "nextPageToken": "eyJvZmZzZXQiOjIwMH0"
}
~~~

Giữ nguyên token do server trả về; không tự giải mã, tăng offset hoặc sửa token. Giữ nguyên các filter, sort và scope của truy vấn giữa các trang. Nếu API dùng cursor, token thường gắn với chính truy vấn ban đầu.

### Thiết kế pagination cho API Spring của bạn

Một endpoint Spring có thể nhận page size và cursor, rồi trả items cùng nextPageToken:

~~~java
public record PageResponse<T>(
    List<T> items,
    String nextPageToken
) {}
~~~

Các nguyên tắc:

- Đặt giới hạn page size tối đa ở server, ví dụ 100 hoặc 500 theo chi phí truy vấn.
- Dùng thứ tự ổn định và có khóa phân biệt, ví dụ created_at, id.
- Dùng cursor/page token thay cho offset lớn khi dữ liệu tăng nhanh.
- Không đưa thông tin bí mật hoặc quyền truy cập vào token dạng dễ đọc; có thể ký hoặc mã hóa cursor.
- Kiểm tra token thuộc đúng user, tenant, filter và sort nếu token mang ngữ cảnh truy vấn.
- Dùng token rỗng hoặc không có token tiếp theo để báo hết dữ liệu theo contract đã công bố.

### Pagination và dữ liệu thay đổi

Trong khi client đọc trang 1, một bản ghi mới có thể được thêm hoặc bản ghi cũ bị xóa. Nếu API không cung cấp snapshot consistency, các trang có thể có bản ghi lặp hoặc bị bỏ qua. Có thể giảm rủi ro bằng:

- Sort theo trường ổn định, có tie-breaker duy nhất.
- Dùng cursor theo khóa cuối trang thay vì offset.
- Dùng snapshot timestamp hoặc read time nếu API hỗ trợ.
- Deduplicate bằng resource ID khi hợp đồng cho phép.
- Lưu checkpoint sau khi xử lý xong trang để có thể tiếp tục.

Không giả định page token có thể lưu vô thời hạn. Một số API có thể làm token hết hạn hoặc không hợp lệ sau khi trạng thái dữ liệu thay đổi.

## 7. Long-running operations (LRO)

### LRO là gì?

Một số thao tác Google Cloud mất nhiều phút hoặc lâu hơn: tạo GKE cluster, khởi tạo Dataflow job, tạo Dataproc cluster hoặc thay đổi tài nguyên lớn. Thay vì giữ một kết nối HTTP mở trong toàn bộ thời gian, API trả về một operation đại diện cho công việc đang chạy.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant App as Java/Spring application
    participant API as Google Cloud API
    participant Worker as Backend service
    App->>API: Gửi yêu cầu tạo tài nguyên
    API-->>App: Trả operation name
    API->>Worker: Bắt đầu công việc
    loop Poll theo lịch/backoff
        App->>API: Get operation status
        API-->>App: done=false + metadata
    end
    Worker-->>API: Hoàn tất hoặc lỗi
    App->>API: Get operation status
    API-->>App: done=true + response/error
~~~

Operation thường có:

- name: định danh operation do server cấp.
- metadata: tiến độ hoặc thông tin tác vụ, tùy API.
- done: cho biết operation đã kết thúc hay chưa.
- response: kết quả nếu thành công.
- error: mã và thông tin lỗi nếu thất bại.

Operation name cần được giữ lại nếu ứng dụng phải tiếp tục theo dõi sau khi restart.

### Nhận diện LRO trong Java client library

Trong Cloud Client Libraries for Java, LRO thường có method kết thúc bằng Async hoặc có OperationCallable. Kết quả thường là OperationFuture:

~~~java
OperationFuture<ResponseT, MetadataT> future =
    client.someLongRunningMethodAsync(request);
~~~

OperationFuture theo dõi operation bằng các lần polling. Client library thường đã cấu hình polling interval và retry theo mặc định của service team; không cần tự viết vòng lặp polling nếu không có yêu cầu đặc biệt.

### Chờ kết quả với OperationFuture

Ví dụ với Dataproc:

~~~java
import com.google.api.gax.longrunning.OperationFuture;
import com.google.cloud.dataproc.v1.Cluster;
import com.google.cloud.dataproc.v1.ClusterControllerClient;
import com.google.cloud.dataproc.v1.ClusterOperationMetadata;
import com.google.cloud.dataproc.v1.CreateClusterRequest;
import java.util.concurrent.CancellationException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

Cluster createCluster(CreateClusterRequest request) throws Exception {
    try (ClusterControllerClient client =
             ClusterControllerClient.create()) {

        OperationFuture<Cluster, ClusterOperationMetadata> future =
            client.createClusterAsync(request);

        try {
            return future.get(30, TimeUnit.MINUTES);
        } catch (TimeoutException | CancellationException timeout) {
            // Caller hoặc cơ chế polling đã ngừng chờ. Operation phía server có thể vẫn chạy.
            String operationName = future.getName();
            if (operationName != null) {
                saveOperationName(operationName);
            }
            throw timeout;
        }
    }
}
~~~

Future.get(timeout, unit) giới hạn thời gian thread caller chờ kết quả. Timeout của lệnh get không tự chứng minh backend đã hủy tác vụ. Lưu operation name để có thể tiếp tục kiểm tra.

Giới hạn 30 phút của Future.get không tự thay đổi polling timeout do GAX cấu hình cho service. Nếu policy polling mặc định kết thúc sớm hơn, client có thể nhận CancellationException trước khi caller chạm mốc 30 phút. Khi cần theo dõi lâu hơn, hãy cấu hình polling algorithm cho đúng LRO như ví dụ ở phần sau. Nếu timeout xảy ra trước khi initial request trả operation name, getName() có thể chưa có giá trị; khi đó cần dùng request ID hoặc cơ chế tra cứu trạng thái mà API hỗ trợ, không gửi lại thao tác tạo một cách mù quáng.

### Phân biệt timeout chờ và timeout polling

GAX dùng RetrySettings riêng cho LRO polling. Nếu total timeout của polling bị vượt, thư viện có thể ném CancellationException và dừng polling phía client. Điều này **không có nghĩa** tác vụ Google Cloud đã bị hủy. Backend có thể tiếp tục và hoàn tất sau đó.

Vì vậy:

- TimeoutException từ Future.get(timeout, unit) có nghĩa caller đã hết thời gian chờ.
- CancellationException do GAX total timeout có thể có nghĩa client library đã dừng theo dõi operation.
- Operation chỉ thực sự bị hủy khi API hỗ trợ cancel và server xác nhận hoặc báo trạng thái hủy.

Không xóa operation name khi caller hết timeout. Dùng nó để truy vấn trạng thái, khôi phục việc theo dõi hoặc xử lý kết quả muộn.

### Lưu và tiếp tục operation

OperationFuture cung cấp getName() để lấy operation name. Một số OperationCallable còn cung cấp resumeFutureCall(operationName) để tạo future theo dõi operation đã khởi chạy trước đó:

~~~java
String operationName = loadOperationName(jobId);

OperationFuture<Cluster, ClusterOperationMetadata> resumed =
    client.createClusterOperationCallable()
        .resumeFutureCall(operationName);

Cluster result = resumed.get();
~~~

Tên callable và response type tùy API. Chỉ resume operation bằng client của đúng service và operation name tương ứng. Nếu API không hỗ trợ resume qua client library, gọi Operations.GetOperation hoặc endpoint theo dõi được tài liệu dịch vụ cung cấp.

### Cấu hình polling cho một LRO

Nếu operation thường cần nhiều thời gian hơn mặc định, có thể tăng total timeout hoặc điều chỉnh poll interval cho đúng RPC operation:

~~~java
import com.google.api.gax.longrunning.OperationTimedPollAlgorithm;
import com.google.api.gax.retrying.RetrySettings;
import com.google.api.gax.retrying.TimedRetryAlgorithm;
import com.google.cloud.dataproc.v1.ClusterControllerClient;
import com.google.cloud.dataproc.v1.ClusterControllerSettings;
import java.time.Duration;

ClusterControllerSettings.Builder settingsBuilder =
    ClusterControllerSettings.newBuilder();

TimedRetryAlgorithm pollingAlgorithm =
    OperationTimedPollAlgorithm.create(
        RetrySettings.newBuilder()
            .setInitialRetryDelayDuration(Duration.ofSeconds(5))
            .setRetryDelayMultiplier(1.5)
            .setMaxRetryDelayDuration(Duration.ofSeconds(45))
            .setTotalTimeoutDuration(Duration.ofHours(2))
            .build());

settingsBuilder.createClusterOperationSettings()
    .setPollingAlgorithm(pollingAlgorithm);

ClusterControllerClient client =
    ClusterControllerClient.create(settingsBuilder.build());
~~~

Đoạn code chỉ điều chỉnh polling của createClusterOperation; các LRO khác trong cùng client vẫn dùng cấu hình riêng. Không tăng timeout một cách tùy tiện. Hãy xem thời gian hoàn tất thực tế, SLA nghiệp vụ, quota và cách API xử lý operation.

### Hủy operation

Một số API hỗ trợ cancel operation, nhưng hủy thường là best effort. Server có thể không hỗ trợ hoặc tác vụ đã đi tới điểm không thể hủy. Hủy future ở client và gửi lệnh cancel tới server là hai hành động khác nhau. Khi cần hủy, dùng API cancel được dịch vụ hỗ trợ, sau đó tiếp tục kiểm tra operation để biết kết quả cuối cùng.

## 8. Kết hợp pagination, retry và deadline

Một lần iterateAll() có thể tạo nhiều request mạng. Mỗi trang có retry riêng, nhưng toàn bộ tác vụ đọc dữ liệu vẫn cần một giới hạn thời gian và checkpoint.

Ví dụ, một batch job đọc 100.000 secret:

1. Đặt page size phù hợp, ví dụ 100.
2. Dùng iterateAll() nếu có thể xử lý tuần tự và không cần checkpoint chi tiết.
3. Dùng pagination thủ công nếu cần lưu token sau mỗi trang.
4. Retry lỗi tạm thời khi tải trang, không retry lỗi quyền hoặc token sai.
5. Ghi nhận trang đã xử lý bằng resource ID hoặc checkpoint.
6. Khi job bị dừng, tiếp tục từ checkpoint còn hợp lệ; nếu token hết hạn, khởi tạo lại truy vấn theo snapshot hoặc quy tắc deduplication.

Không giữ một transaction database mở trong toàn bộ quá trình pagination. Xử lý từng trang theo transaction ngắn để giảm lock và dễ khôi phục.

## 9. Thiết kế API Spring cho công việc dài

Nếu ứng dụng Spring của bạn cung cấp endpoint để khởi chạy một tác vụ dài, không nên bắt client chờ HTTP response cho tới khi tác vụ hoàn tất. Có thể dùng mô hình bất đồng bộ:

1. Client gọi POST /exports.
2. Spring xác thực request, kiểm tra idempotency key và ghi một job record.
3. Spring gửi công việc tới worker hoặc queue.
4. API trả 202 Accepted cùng jobId và URL trạng thái.
5. Client gọi GET /exports/{jobId} để xem QUEUED, RUNNING, SUCCEEDED hoặc FAILED.
6. Khi job kết thúc, client tải kết quả qua URL hoặc resource được cấp.

Response minh họa:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/exports/job-7f31
Retry-After: 5
Content-Type: application/json

{
  "jobId": "job-7f31",
  "status": "RUNNING",
  "statusUrl": "/v1/exports/job-7f31"
}
~~~

Retry-After gợi ý client khoảng chờ trước khi kiểm tra lại. Endpoint status nên nhẹ, không kích hoạt lại tác vụ. Lưu trạng thái job và operation name bền vững để có thể khôi phục sau khi ứng dụng restart.

### Trạng thái và tính idempotent

Nếu client gửi lại POST /exports vì response đầu tiên bị timeout, idempotency key giúp server nhận biết đó là cùng một yêu cầu. Server nên lưu key, hash payload, job ID và kết quả khởi tạo trong một transaction. Nếu cùng key nhưng payload khác, trả lỗi xung đột theo contract.

Không dùng HTTP request thread để polling Google Cloud LRO trong nhiều giờ. Worker hoặc scheduler có thể theo dõi operation, cập nhật job record và phát sự kiện khi hoàn tất.

## 10. Quan sát và vận hành

Timeout, retry, pagination và LRO cần có telemetry để phân biệt lỗi dịch vụ với lỗi cấu hình hoặc lỗi ứng dụng.

Nên theo dõi:

- Số lần retry trên mỗi RPC và tổng retry theo dependency.
- Tỷ lệ request kết thúc bằng timeout, phân loại connect/read/RPC/total timeout.
- Thời gian thực tế của mỗi attempt và toàn bộ logical operation.
- Số trang được đọc, số item mỗi trang, số trang lỗi và số token hết hạn.
- Số LRO đang chạy, tuổi operation, thời gian hoàn tất p50/p95/p99 và tỷ lệ thất bại.
- Số operation bị client ngừng polling nhưng backend vẫn đang xử lý.
- Tỷ lệ request bị circuit breaker từ chối hoặc bị giới hạn bởi bulkhead.

Log nên chứa correlation ID, resource name, operation name, attempt number và error code. Không ghi access token, secret, nội dung dữ liệu nhạy cảm hoặc toàn bộ page token nếu token có thể tiết lộ ngữ cảnh truy vấn.

### Cảnh báo hữu ích

- Retry rate tăng nhanh hoặc vượt retry budget.
- Tỷ lệ 429/RESOURCE_EXHAUSTED tăng.
- Timeout p95/p99 vượt ngân sách của request.
- Pagination liên tục nhận cùng page token hoặc số trang tăng bất thường.
- LRO chạy lâu hơn ngưỡng dự kiến hoặc không có tiến độ.
- Số operation chưa hoàn tất tăng liên tục.

Circuit breaker có thể ngăn ứng dụng tiếp tục gửi request tới dependency đang lỗi. Bulkhead giới hạn số request đồng thời để một dependency chậm không chiếm hết thread hoặc connection pool.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request bị treo lâu | Thiếu connect/read/total timeout hoặc timeout ở tầng dưới quá lớn | Đặt timeout theo từng lớp và deadline tổng |
| Retry không làm request thành công | Retry cả lỗi cấu hình, dữ liệu hoặc IAM | Lọc mã lỗi transient; trả lỗi permanent ngay |
| Backend nhận nhiều request trùng | Retry thao tác POST không idempotent | Dùng request ID/idempotency key hoặc tra cứu trạng thái trước khi retry |
| 429 xuất hiện nhiều hơn sau khi thêm retry | Retry quá nhanh hoặc nhiều tầng retry chồng nhau | Tăng backoff, thêm jitter, giảm retry và tôn trọng Retry-After |
| Chỉ nhận được trang đầu | Code chỉ đọc values của response đầu tiên | Dùng iterateAll hoặc vòng lặp page token |
| Lặp vô hạn khi phân trang | Token không được cập nhật hoặc API trả token lặp | Kiểm tra điều kiện kết thúc, phát hiện token lặp và ghi log |
| Dữ liệu lặp hoặc thiếu giữa các trang | Dataset thay đổi khi phân trang hoặc sort không ổn định | Dùng cursor/snapshot, sort có tie-breaker và deduplicate |
| LRO báo timeout nhưng tài nguyên vẫn được tạo | Client dừng chờ/polling trong khi backend tiếp tục | Lưu operation name, kiểm tra trạng thái trước khi gửi yêu cầu mới |
| LRO bị hủy ngoài ý muốn | Dùng CancellationException như bằng chứng server đã cancel | Phân biệt client polling timeout với API cancel server-side |
| Spring WebClient timeout không như mong đợi | Chỉ dùng Mono.timeout hoặc chỉ cấu hình socket timeout | Cấu hình connection/response timeout và deadline nghiệp vụ riêng |

## 12. Checklist production

- [ ] Có connect timeout, response/read timeout và total deadline phù hợp.
- [ ] Ngân sách timeout của dependency nằm trong deadline của request gọi nó.
- [ ] Retry chỉ áp dụng cho lỗi tạm thời và có giới hạn số lần hoặc tổng thời gian.
- [ ] Có exponential backoff, jitter và tôn trọng Retry-After/RetryInfo.
- [ ] Không có retry chồng lặp không kiểm soát giữa gateway, Spring và GAX.
- [ ] Thao tác ghi có idempotency key, request ID hoặc cơ chế tra cứu trạng thái.
- [ ] Pagination dùng page token từ server và có điều kiện kết thúc rõ ràng.
- [ ] Có giới hạn page size, sort ổn định và xử lý dữ liệu thay đổi.
- [ ] LRO lưu operation name và có khả năng resume sau restart.
- [ ] Phân biệt timeout của caller, timeout polling và cancel server-side.
- [ ] Có metric retry, timeout, page count, LRO duration và alert.
- [ ] Không log token, secret hoặc dữ liệu nhạy cảm.

## 13. Kết luận

Timeout giới hạn thời gian chờ; retry giúp vượt qua lỗi tạm thời; pagination xử lý tập dữ liệu lớn theo từng phần; LRO cho phép theo dõi công việc dài mà không giữ một request mở liên tục. Bốn cơ chế cần được thiết kế cùng nhau theo deadline của nghiệp vụ và khả năng của API.

Với Google Cloud Java Client Libraries, hãy tận dụng retry, pagination và LRO tích hợp trong GAX trước khi tự viết lại. Với Spring WebClient hoặc REST API riêng, cấu hình timeout ở HTTP client, retry có điều kiện và idempotency cho thao tác ghi. Khi lưu page token, operation name và checkpoint đúng cách, ứng dụng có thể tiếp tục công việc sau timeout hoặc restart mà không tạo thêm tác động ngoài ý muốn.

## Tài liệu tham khảo

- [Configure client-side retries – Java](https://docs.cloud.google.com/java/docs/client-retries)
- [RetrySettings – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.retrying.RetrySettings)
- [Manage pagination – Java](https://docs.cloud.google.com/java/docs/pagination)
- [Page interface – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.paging.Page)
- [Manage long-running operations – Java](https://docs.cloud.google.com/java/docs/long-running-operations)
- [OperationFuture – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.longrunning.OperationFuture)
- [REST Clients – Spring Framework](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [WebClient configuration and timeouts – Spring Framework](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Cloud Client Libraries for Java](https://docs.cloud.google.com/java/docs/reference)
