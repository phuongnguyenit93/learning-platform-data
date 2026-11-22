# Processor gọi remote service

Trong Spring Batch, `ItemProcessor` thường đảm nhiệm việc biến đổi, làm giàu hoặc kiểm tra từng item trước khi item được ghi ra đích. Một trường hợp phổ biến là processor cần gọi một remote service để lấy thêm dữ liệu hoặc xác minh thông tin. Ví dụ, khi xử lý đơn hàng, processor có thể gọi Customer API để lấy phân khúc khách hàng rồi tạo ra bản ghi đã được làm giàu.

Mẫu này hữu ích khi kết quả xử lý một item phụ thuộc vào dữ liệu bên ngoài. Tuy nhiên, mỗi lời gọi mạng đều có độ trễ và có thể thất bại độc lập với transaction của batch job. Vì vậy, cần thiết kế rõ ranh giới trách nhiệm, chính sách lỗi, khả năng gọi lặp lại và giới hạn tải.

## 1. Remote service nằm ở đâu trong luồng xử lý?

Trong một chunk-oriented step, luồng cơ bản là:

```text
ItemReader
    |
    v
 ItemProcessor -----> Remote service
    |                    |
    |<--- dữ liệu -------+
    v
 ItemWriter
    |
    v
 Đích lưu trữ
```

`ItemReader` đọc item đầu vào. `ItemProcessor<I, O>` nhận một item kiểu `I`, thực hiện logic nghiệp vụ và trả về item kiểu `O`. `ItemWriter` ghi các item đầu ra theo chunk.

Processor có thể thực hiện một trong các hành vi sau:

- Chuyển đổi item đầu vào thành một kiểu dữ liệu đầu ra khác.
- Gọi service để bổ sung dữ liệu còn thiếu, sau đó tạo item đã được làm giàu.
- Gọi service để kiểm tra một điều kiện nghiệp vụ trước khi cho item đi tiếp.
- Trả về `null` để lọc bỏ item khỏi luồng ghi.
- Ném exception khi không thể xử lý item theo quy tắc đã định.

Ví dụ, `Order` chỉ có `customerId`, còn Customer API trả về tên và phân khúc khách hàng. Processor kết hợp hai nguồn dữ liệu để tạo `EnrichedOrder`.

Nên đặt lời gọi remote trong processor khi dữ liệu trả về trực tiếp tham gia vào phép biến đổi hoặc quyết định xử lý item. Nếu nhiệm vụ chính là đọc dữ liệu từ một nguồn bên ngoài, hãy cân nhắc một reader phù hợp. Nếu nhiệm vụ là gửi một lệnh hoặc tạo tác động bên ngoài, cần xem xét kỹ tính lặp lại và có thể đặt phần ghi nhận ý định trong writer hoặc outbox.

## 2. Tách logic batch khỏi chi tiết HTTP

Processor nên phụ thuộc vào một interface mô tả nhu cầu nghiệp vụ, chẳng hạn `CustomerProfileClient`. Adapter triển khai interface đó mới chịu trách nhiệm gọi HTTP, ánh xạ response và chuyển lỗi kỹ thuật thành exception có ý nghĩa đối với ứng dụng.

Cách tách này giúp processor dễ kiểm thử, đồng thời cho phép thay đổi thư viện HTTP hoặc endpoint mà không phải sửa logic xử lý batch.

```java
public interface CustomerProfileClient {
    CustomerProfile findById(String customerId);
}
```

Các kiểu dữ liệu minh họa:

```java
public record Order(
        String id,
        String customerId,
        BigDecimal total
) {}

public record CustomerProfile(
        String customerId,
        String segment
) {}

public record EnrichedOrder(
        String orderId,
        String customerId,
        String customerSegment,
        BigDecimal total
) {}
```

Processor chỉ tập trung vào quy tắc biến đổi:

```java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class CustomerEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder> {

    private final CustomerProfileClient customerProfileClient;

    public CustomerEnrichmentProcessor(
            CustomerProfileClient customerProfileClient) {
        this.customerProfileClient = customerProfileClient;
    }

    @Override
    public EnrichedOrder process(Order order) {
        CustomerProfile profile = customerProfileClient
                .findById(order.customerId());

        if (profile == null) {
            throw new CustomerNotFoundException(order.customerId());
        }

        return new EnrichedOrder(
                order.id(),
                order.customerId(),
                profile.segment(),
                order.total()
        );
    }
}
```

`CustomerNotFoundException` ở đây là exception nghiệp vụ do ứng dụng định nghĩa. Ứng dụng cần quyết định trường hợp không tìm thấy khách hàng sẽ làm job thất bại, được skip theo chính sách, hay được xử lý theo một nhánh nghiệp vụ khác. Không nên âm thầm tạo dữ liệu mặc định nếu giá trị đó có thể làm sai kết quả.

## 3. Triển khai client gọi HTTP

Với Spring Framework 6.1 trở lên, có thể dùng `RestClient` cho lời gọi HTTP đồng bộ. Ví dụ adapter dưới đây gọi endpoint tra cứu khách hàng:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class RestCustomerProfileClient implements CustomerProfileClient {

    private final RestClient restClient;

    public RestCustomerProfileClient(RestClient customerRestClient) {
        this.restClient = customerRestClient;
    }

    @Override
    public CustomerProfile findById(String customerId) {
        return restClient.get()
                .uri("/customers/{id}", customerId)
                .retrieve()
                .body(CustomerProfile.class);
    }
}
```

Đăng ký một `RestClient` bean với base URL lấy từ cấu hình môi trường:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@ConfigurationProperties(prefix = "integration.customer")
record CustomerApiProperties(String baseUrl) {}

@Configuration
@EnableConfigurationProperties(CustomerApiProperties.class)
class CustomerApiConfiguration {

    @Bean
    RestClient customerRestClient(
            RestClient.Builder builder,
            CustomerApiProperties properties) {
        return builder
                .baseUrl(properties.baseUrl())
                .build();
    }
}
```

Ví dụ cấu hình:

```yaml
integration:
  customer:
    base-url: https://customer-api.example.internal
```

URL thực tế, thông tin xác thực và cấu hình timeout nên được quản lý theo môi trường triển khai. Không đặt token hoặc mật khẩu trực tiếp trong source code. Cần cấu hình cả thời gian chờ kết nối và thời gian chờ response bằng request factory phù hợp; tên API cấu hình cụ thể phụ thuộc phiên bản Spring và HTTP client đang sử dụng.

`RestClient` phù hợp với Spring Framework 6.1+ (thường có trong Spring Boot 3.2+). Với ứng dụng dùng phiên bản cũ hơn, có thể dùng `RestTemplate` hoặc một client khác đã được dự án chuẩn hóa. Dù dùng thư viện nào, interface nghiệp vụ của client vẫn có thể được giữ nguyên.

## 4. Xử lý lỗi theo bản chất của response

Không phải mọi lỗi remote service đều có cùng cách xử lý. Trước khi cấu hình retry hoặc skip, hãy phân loại lỗi theo khả năng tự hồi phục và ý nghĩa nghiệp vụ.

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Lỗi kết nối, timeout tạm thời | Có thể retry với giới hạn và backoff |
| HTTP 5xx | Thường là lỗi tạm thời; retry có giới hạn nếu thao tác an toàn khi gọi lại |
| HTTP 429 | Tôn trọng `Retry-After` nếu có, giảm tốc độ gọi và backoff |
| HTTP 408 | Có thể retry nếu request có thể thực hiện lại an toàn |
| HTTP 400 hoặc 422 do dữ liệu không hợp lệ | Thường không retry; sửa dữ liệu hoặc xử lý theo chính sách nghiệp vụ |
| HTTP 401 hoặc 403 | Kiểm tra cấu hình xác thực và quyền; retry liên tục thường không giúp ích |
| HTTP 404 | Xác định đây là dữ liệu không tồn tại hợp lệ, trường hợp cần skip hay lỗi phải dừng job |

Các mã HTTP chỉ là gợi ý phân loại. Quyết định cuối cùng phải dựa vào hợp đồng của remote API. Chẳng hạn, một API có thể dùng 404 để biểu thị trạng thái nghiệp vụ bình thường, trong khi API khác coi đó là lỗi dữ liệu nghiêm trọng.

Adapter nên chuyển các lỗi HTTP thành những exception rõ nghĩa như `TemporaryRemoteServiceException`, `RemoteAuthenticationException` hoặc `CustomerNotFoundException`. Nhờ đó, cấu hình fault tolerance của step không phải phụ thuộc vào chi tiết thư viện HTTP.

Tránh retry mọi `Exception`. Retry lỗi dữ liệu, lỗi xác thực hoặc lỗi lập trình chỉ làm job chậm hơn và có thể tạo thêm tải cho service.

## 5. Cấu hình retry và skip trong step

Spring Batch hỗ trợ fault-tolerant step để quy định exception nào được retry và exception nào được skip. Ví dụ sau minh họa cấu hình theo API của Spring Batch 5:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrders", jobRepository)
            .<Order, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TemporaryRemoteServiceException.class)
            .retryLimit(3)
            .skip(CustomerNotFoundException.class)
            .skipLimit(100)
            .build();
}
```

Trong ví dụ này:

- Lỗi remote service tạm thời được retry trong giới hạn đã cấu hình.
- Trường hợp không tìm thấy khách hàng được skip, nhưng số item bị skip vẫn bị giới hạn.
- Nếu vượt giới hạn skip hoặc gặp exception không có chính sách xử lý phù hợp, step có thể thất bại.

Chỉ skip khi bỏ item là một quyết định nghiệp vụ được chấp nhận. Nếu bỏ một đơn hàng có thể gây sai lệch tài chính hoặc mất dữ liệu quan trọng, nên dừng job hoặc đưa item vào quy trình xử lý lỗi riêng.

Retry nên đi kèm backoff, thường là exponential backoff có jitter và giới hạn thời gian tối đa. Với HTTP 429, hãy tôn trọng thời gian chờ mà server yêu cầu khi có thể. Giới hạn số lần retry để một service đang lỗi không khiến batch job gửi request liên tục.

## 6. Transaction, retry và khả năng gọi lặp lại

Đây là điểm cần chú ý nhất khi processor gọi remote service. Transaction của chunk thường quản lý thay đổi trong tài nguyên được transaction manager hỗ trợ, chẳng hạn database đích. Một lời gọi HTTP thông thường không tự động tham gia transaction đó.

Giả sử processor gọi API thành công, sau đó writer ghi database nhưng gặp lỗi. Transaction database có thể rollback, trong khi remote service vẫn giữ kết quả đã thực hiện. Khi chunk được thử lại hoặc job được restart, processor có thể gọi API lần nữa. Vì vậy, không thể mặc định rằng một item chỉ tạo ra đúng một lời gọi remote.

Với lời gọi chỉ đọc như tra cứu hồ sơ khách hàng, gọi lại thường có thể chấp nhận được, dù vẫn tốn thời gian và tải. Với lời gọi tạo đơn, trừ tiền, gửi thông báo hoặc thay đổi trạng thái bên ngoài, gọi lặp lại có thể tạo tác động trùng.

Để xử lý trường hợp đó:

1. Ưu tiên để processor thực hiện tra cứu hoặc phép biến đổi không gây tác động phụ.
2. Nếu phải gửi lệnh, tạo một idempotency key ổn định từ định danh nghiệp vụ của item và gửi key đó trong request.
3. Remote service cần hỗ trợ lưu và nhận diện key đã xử lý để request lặp lại không tạo tác động lần hai.
4. Nếu cần phối hợp việc ghi database với việc phát lệnh ra ngoài, cân nhắc transactional outbox: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction, sau đó một tiến trình riêng gửi thông điệp và retry có kiểm soát.

Không nên coi việc thêm `@Transactional` quanh processor là cách tạo transaction phân tán giữa database và HTTP service. Annotation này không làm cho một REST API thông thường có khả năng rollback cùng database.

Lời gọi mạng cũng kéo dài thời gian xử lý chunk. Khi transaction của chunk còn mở, một remote service phản hồi chậm có thể làm transaction giữ tài nguyên lâu hơn và tăng nguy cơ timeout hoặc tranh chấp khóa. Hãy đặt timeout hữu hạn, theo dõi thời gian xử lý và chọn chunk size dựa trên cả thời gian gọi API lẫn khả năng của database.

## 7. Hiệu năng, giới hạn tải và tính an toàn luồng

Nếu processor gọi API một lần cho mỗi item, số request tăng theo số item. Với một job có hàng trăm nghìn bản ghi, độ trễ nhỏ trên từng request vẫn có thể tạo ra tổng thời gian lớn. Trước khi tăng số thread, hãy xác định remote service có thể chịu được bao nhiêu request đồng thời.

Một số cách cải thiện thường dùng:

- **Bulk API:** Nếu service hỗ trợ tra cứu nhiều ID trong một request, gom ID theo nhóm để giảm số lượt round trip. Khi đó có thể cần bước chuẩn bị dữ liệu hoặc một processor có cơ chế tra cứu theo lô phù hợp.
- **Cache:** Cache kết quả tra cứu có thể giảm request trùng lặp. Chọn cache key, TTL và chính sách làm mới dựa trên độ mới dữ liệu mà nghiệp vụ yêu cầu. Tránh cache dữ liệu nhạy cảm hoặc dữ liệu thay đổi nhanh nếu chưa có chính sách phù hợp.
- **Connection pooling:** Dùng HTTP client có pool kết nối được cấu hình phù hợp để tránh tạo kết nối mới cho từng item.
- **Timeout và giới hạn đồng thời:** Đặt connect/read/response timeout, giới hạn số request đang chạy và cân nhắc rate limiter hoặc circuit breaker.
- **Chunk size:** Chunk lớn giảm số lần commit nhưng có thể kéo dài transaction và tăng lượng công việc phải xử lý lại khi lỗi. Chunk nhỏ giúp giới hạn phạm vi rollback nhưng có thể tăng overhead.
- **Concurrency:** Chỉ tăng số thread sau khi đo tải và xác nhận remote service đáp ứng được. Nếu step xử lý song song, processor và các dependency dùng chung phải an toàn luồng; không lưu trạng thái tạm của từng item trong field mutable của singleton processor.

`ItemProcessor` có chữ ký đồng bộ. Nếu dùng `WebClient` bên trong processor rồi gọi `block()`, lời gọi vẫn chiếm thread cho đến khi có kết quả. Không nên tạo một tác vụ bất đồng bộ không giới hạn cho mỗi item rồi để batch tiếp tục trước khi kết quả hoàn tất; cách đó làm mất sự gắn kết giữa kết quả xử lý, commit chunk và checkpoint. Nếu cần xử lý reactive end-to-end, hãy thiết kế mô hình thực thi phù hợp thay vì chỉ chuyển HTTP client sang reactive.

## 8. Quan sát và vận hành

Khi remote service trở thành một phần của batch pipeline, log trạng thái job là chưa đủ. Nên thu thập các chỉ số giúp phân biệt lỗi batch với lỗi phụ thuộc bên ngoài:

- Số request, số request thành công và số request thất bại theo service hoặc endpoint.
- Thời gian phản hồi, đặc biệt là p95/p99, cùng số timeout.
- Số lần retry, số response 429 và số item bị skip.
- Số lỗi theo nhóm nghiệp vụ và nhóm kỹ thuật.
- Thời gian xử lý mỗi chunk và tổng thời gian của step.

Log nên có job execution ID, step execution ID và business key phù hợp để truy vết một item qua các lần retry. Không ghi access token, secret hoặc toàn bộ dữ liệu cá nhân trong request/response. Khi ghi lỗi, giữ lại thông tin đủ để điều tra nhưng phải tuân theo chính sách bảo vệ dữ liệu của hệ thống.

Nếu dùng circuit breaker, hãy xác định rõ hành vi khi circuit mở: dừng step, retry sau khoảng chờ, hay chuyển item sang luồng xử lý lỗi. Không nên trả về dữ liệu giả chỉ để job tiếp tục chạy, trừ khi nghiệp vụ định nghĩa rõ giá trị thay thế đó.

## 9. Kiểm thử processor và tích hợp remote client

Có thể chia kiểm thử thành các lớp để mỗi lớp tập trung vào một trách nhiệm.

**Unit test cho processor:** mock `CustomerProfileClient`, sau đó kiểm tra:

- Khi client trả về profile hợp lệ, processor tạo đúng `EnrichedOrder`.
- Khi client báo không tìm thấy khách hàng, processor ném đúng exception nghiệp vụ.
- Khi client ném lỗi tạm thời, exception được truyền ra để step áp dụng retry policy.
- Khi logic nghiệp vụ lọc một item, processor trả về `null` và item không được chuyển tới writer.

Ví dụ với JUnit và Mockito:

```java
@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    CustomerProfileClient customerProfileClient;

    @InjectMocks
    CustomerEnrichmentProcessor processor;

    @Test
    void enrichesOrderWithCustomerSegment() {
        Order order = new Order(
                "order-1", "customer-7", new BigDecimal("125.00"));
        CustomerProfile profile = new CustomerProfile(
                "customer-7", "GOLD");

        when(customerProfileClient.findById("customer-7"))
                .thenReturn(profile);

        EnrichedOrder result = processor.process(order);

        assertEquals("order-1", result.orderId());
        assertEquals("GOLD", result.customerSegment());
        verify(customerProfileClient).findById("customer-7");
    }
}
```

**Integration test cho HTTP adapter:** dùng mock HTTP server để xác minh method, path, request header, cách giải mã response và cách ánh xạ status code thành exception. Không cần gọi service thật trong unit test.

**Test cho step:** xác minh retry có giới hạn, skip limit, số item writer nhận được và hành vi khi job restart. Đặc biệt, nếu remote operation có side effect, hãy kiểm tra idempotency key bảo vệ hệ thống khỏi tác động trùng khi request được gửi lại.

## 10. Khi nào nên dùng pattern này?

Processor gọi remote service phù hợp khi mỗi item cần dữ liệu hoặc quyết định từ một hệ thống khác để hoàn tất phép biến đổi. Đây là lựa chọn tự nhiên cho các thao tác tra cứu, enrichment và validation có thời gian phản hồi được kiểm soát.

Trước khi triển khai, hãy trả lời được các câu hỏi sau:

- Remote call là đọc dữ liệu hay tạo tác động bên ngoài?
- Một item có thể được gọi lại khi retry hoặc restart không, và kết quả có an toàn khi gọi lại không?
- Lỗi nào là tạm thời, lỗi nào là vĩnh viễn, và trường hợp nào được phép skip?
- Timeout, backoff, rate limit và giới hạn request đồng thời được cấu hình ở đâu?
- Số request dự kiến có phù hợp với năng lực của remote service không?
- Có thể dùng bulk API hoặc cache để giảm số lần gọi không?
- Metrics và log có đủ để truy tìm item lỗi mà không làm lộ dữ liệu nhạy cảm không?

Khi các điều kiện này được xác định rõ, remote service có thể trở thành một dependency có kiểm soát trong Spring Batch pipeline, thay vì một điểm nghẽn khó dự đoán trong lúc job chạy.
