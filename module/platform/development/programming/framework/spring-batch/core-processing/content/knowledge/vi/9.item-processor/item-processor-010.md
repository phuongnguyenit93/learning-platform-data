# Processor dùng service ngoài

Trong Spring Batch, `ItemProcessor` nhận một item từ `ItemReader`, thực hiện kiểm tra hoặc chuyển đổi dữ liệu rồi trả về item mới cho `ItemWriter`. Processor có thể gọi một service khác để lấy thêm thông tin hoặc áp dụng quy tắc nghiệp vụ, chẳng hạn tra cứu hồ sơ khách hàng, kiểm tra trạng thái tài khoản, tính thuế hoặc gọi API của hệ thống đối tác.

Việc gọi service từ processor giúp tách logic xử lý item khỏi cách truy cập dữ liệu hoặc giao tiếp với hệ thống bên ngoài. Tuy nhiên, mỗi lời gọi có thể làm tăng thời gian xử lý, phát sinh lỗi mạng và tạo tác dụng phụ nằm ngoài transaction của chunk. Vì vậy, cần thiết kế rõ ranh giới trách nhiệm, timeout, retry, idempotency và giới hạn tải trước khi đưa Job vào production.

## 1. Vai trò của ItemProcessor

Interface `ItemProcessor<I, O>` nhận một item kiểu `I` và trả về một item kiểu `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Processor có thể:

- Kiểm tra dữ liệu đầu vào và ném exception nếu dữ liệu không hợp lệ.
- Chuẩn hóa hoặc chuyển đổi item sang kiểu dữ liệu phù hợp với writer.
- Bổ sung thông tin từ service, repository hoặc API khác.
- Áp dụng quy tắc nghiệp vụ để tính giá trị đầu ra.
- Trả về `null` để lọc bỏ item khỏi luồng ghi.

Ví dụ, reader đọc một `OrderInput` chỉ có mã đơn hàng và mã khách hàng. Processor gọi `CustomerProfileService` để lấy hạng thành viên, sau đó tạo `EnrichedOrder` chứa dữ liệu đã bổ sung cho writer.

```text
ItemReader<OrderInput>
        |
        v
ItemProcessor<OrderInput, EnrichedOrder>
        |
        +----> CustomerProfileService
        |             |
        |             v
        |       Customer profile
        |
        v
ItemWriter<EnrichedOrder>
```

Processor không cần biết profile được lấy từ database, cache hay HTTP API. Nó chỉ phụ thuộc vào hợp đồng service. Cách tách này giúp thay đổi cách truy cập hệ thống mà không phải viết lại logic chuyển đổi item.

## 2. Inject service vào processor bằng dependency injection

Trong Spring, processor thường được khai báo thành bean và nhận service qua constructor injection. Đây là cách rõ ràng để thể hiện phụ thuộc và thuận tiện khi thay thế service trong kiểm thử.

```java
public interface CustomerProfileService {
    CustomerProfile findByCustomerId(String customerId);
}
```

Processor sử dụng interface này:

```java
@Component
public class EnrichOrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService customerProfileService;

    public EnrichOrderProcessor(
            CustomerProfileService customerProfileService) {
        this.customerProfileService = customerProfileService;
    }

    @Override
    public EnrichedOrder process(OrderInput input) {
        CustomerProfile profile = customerProfileService
                .findByCustomerId(input.customerId());

        return new EnrichedOrder(
                input.orderId(),
                input.customerId(),
                input.amount(),
                profile.membershipLevel());
    }
}
```

Service có thể được triển khai bằng một repository trong cùng ứng dụng hoặc bằng HTTP client gọi sang ứng dụng khác. Processor không cần tạo service mới bằng `new`, cũng không nên tự quản lý kết nối HTTP hay database nếu những trách nhiệm đó đã thuộc service.

### Service gọi REST API

Nếu service cần gọi một hệ thống khác, có thể dùng `RestClient` (Spring Framework 6.1 trở lên) hoặc HTTP client phù hợp với phiên bản ứng dụng:

```java
@Service
public class RemoteCustomerProfileService
        implements CustomerProfileService {

    private final RestClient restClient;

    public RemoteCustomerProfileService(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public CustomerProfile findByCustomerId(String customerId) {
        return restClient.get()
                .uri("/customers/{customerId}", customerId)
                .retrieve()
                .body(CustomerProfile.class);
    }
}
```

`RestClient` nên được cấu hình tập trung với base URL, authentication, connection timeout và response timeout phù hợp. Không nên tạo một HTTP client mới cho từng item vì sẽ gây thêm chi phí tạo kết nối và khó kiểm soát tài nguyên.

## 3. Đặt service call ở đâu trong pipeline?

Vị trí gọi service phụ thuộc vào mục đích của lời gọi.

**Trong processor:** phù hợp khi service cung cấp dữ liệu hoặc kết quả cần thiết để biến đổi item. Ví dụ tra cứu thông tin khách hàng để tạo bản ghi đầu ra, tính phí dựa trên dữ liệu tham chiếu hoặc kiểm tra điều kiện nghiệp vụ.

**Trong reader:** có thể phù hợp nếu service chính là nguồn cung cấp item. Ví dụ reader đọc từng bản ghi từ API phân trang. Reader chịu trách nhiệm lấy input và báo hết dữ liệu; processor vẫn nên tập trung vào chuyển đổi hoặc áp dụng quy tắc.

**Trong writer:** phù hợp khi nhiệm vụ chính là gửi kết quả đã xử lý sang hệ thống đích. Ví dụ ghi bản ghi đã chuẩn hóa vào một API đối tác. Writer nhận cả danh sách item của chunk, vì vậy có thể tận dụng endpoint hỗ trợ gửi theo lô.

Không nên đặt mọi lời gọi bên ngoài vào processor chỉ vì đây là nơi dễ viết code. Hãy xác định service đang cung cấp dữ liệu đầu vào, hỗ trợ xử lý từng item hay tiếp nhận kết quả đầu ra để chọn đúng thành phần.

## 4. Xử lý lỗi khi service ngoài không phản hồi

Service ngoài có thể gặp các lỗi như:

- Timeout hoặc mất kết nối mạng.
- HTTP `429 Too Many Requests` do vượt giới hạn request.
- HTTP `5xx` khi service đích gặp sự cố tạm thời.
- HTTP `4xx` do tham số sai, quyền truy cập không hợp lệ hoặc tài nguyên không tồn tại.
- Response không đúng định dạng hoặc thiếu dữ liệu bắt buộc.
- Service trả kết quả nghiệp vụ từ chối yêu cầu.

Không nên xử lý tất cả lỗi theo cùng một cách. Lỗi mạng tạm thời có thể retry; lỗi dữ liệu hoặc xác thực thường cần sửa đầu vào hay cấu hình trước khi chạy lại. Nếu service trả về “không tìm thấy khách hàng”, nghiệp vụ có thể coi đó là dữ liệu không hợp lệ, cần skip có kiểm soát hoặc làm Job thất bại.

Nên ánh xạ lỗi ở lớp service thành các exception có ý nghĩa để processor hoặc cấu hình Step phân loại được:

```java
public class RemoteServiceException extends RuntimeException {
    public RemoteServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class CustomerDataException extends RuntimeException {
    public CustomerDataException(String message) {
        super(message);
    }
}
```

Service có thể chuyển timeout hoặc lỗi server thành `RemoteServiceException`, còn dữ liệu khách hàng không tồn tại thành `CustomerDataException`. Cần giữ nguyên nguyên nhân gốc để log và điều tra.

## 5. Retry và skip khi processor gọi service

Spring Batch hỗ trợ cấu hình retry và skip cho fault-tolerant Step. Với service ngoài, chỉ nên retry lỗi có khả năng tự hết, chẳng hạn timeout ngắn hạn, HTTP 429 theo chính sách `Retry-After`, hoặc lỗi 5xx tạm thời. Không nên retry vô hạn hoặc retry lỗi dữ liệu không thể tự khắc phục.

Ví dụ cấu hình retry giới hạn trong Spring Batch 5:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        EnrichOrderProcessor processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
            .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(RemoteServiceException.class)
            .retryLimit(3)
            .build();
}
```

Ví dụ này cho phép retry exception `RemoteServiceException` tối đa theo giới hạn đã cấu hình. Cần xác nhận chính xác ý nghĩa retry limit và cách đếm retry theo phiên bản Spring Batch đang dùng; nên kết hợp backoff để tránh gửi lại liên tục trong lúc hệ thống đích đang quá tải.

Nếu dữ liệu đầu vào không hợp lệ và nghiệp vụ cho phép bỏ qua, có thể cấu hình skip riêng:

```java
.faultTolerant()
.retry(RemoteServiceException.class)
.retryLimit(3)
.skip(CustomerDataException.class)
.skipLimit(100)
```

Không nên skip lỗi kết nối hoặc lỗi service hàng loạt một cách tùy tiện. Nếu hệ thống phụ thuộc đang ngừng hoạt động, bỏ qua hàng nghìn item có thể khiến Job `COMPLETED` nhưng kết quả thiếu dữ liệu. Nên đặt skip limit hợp lý, lưu danh sách item lỗi và có quy trình xử lý bù.

## 6. Timeout, backoff và circuit breaker

Retry không thay thế timeout. Nếu HTTP request không có timeout, một lần gọi có thể treo lâu và giữ chunk transaction mở trong thời gian dài. Cần đặt:

- **Connection timeout:** giới hạn thời gian thiết lập kết nối.
- **Response/read timeout:** giới hạn thời gian chờ dữ liệu phản hồi.
- **Overall deadline:** giới hạn tổng thời gian cho một lần xử lý hoặc một Job nếu nghiệp vụ yêu cầu.

Backoff làm giãn thời gian giữa các lần retry. Ví dụ, thay vì gửi lại ngay lập tức ba lần, có thể chờ tăng dần 200 ms, 500 ms rồi 1 giây, kèm jitter để nhiều worker không đồng loạt gọi lại cùng lúc. Với HTTP 429, nên tôn trọng giới hạn hoặc `Retry-After` mà service đích cung cấp.

Circuit breaker là cơ chế tạm ngừng gọi một service đang lỗi liên tục. Khi circuit mở, các lời gọi tiếp theo bị từ chối nhanh trong một khoảng thời gian, giúp tránh làm quá tải hệ thống phụ thuộc và giảm số thread bị giữ chờ. Khi hết thời gian, cơ chế cho phép một số request thử lại để xác định service đã phục hồi hay chưa.

Các cơ chế này có thể được triển khai bằng HTTP client, Resilience4j hoặc thư viện phù hợp. Cần tránh xếp chồng nhiều tầng retry mà không tính tổng số lần gọi. Ví dụ, nếu HTTP client tự retry 3 lần và Spring Batch cũng retry 3 lần, một item có thể tạo ra nhiều request hơn dự kiến.

## 7. Transaction của chunk không bao trùm service ngoài

Đây là rủi ro quan trọng khi gọi hệ thống từ processor. Spring Batch thường thực hiện reader, processor và writer trong phạm vi xử lý chunk, với transaction được commit sau khi writer hoàn tất. Transaction manager có thể rollback các thay đổi trên resource tham gia transaction, chẳng hạn database connection được quản lý.

Một HTTP service độc lập không tự động tham gia transaction database của chunk. Nếu processor gọi API và service đích đã thực hiện hành động, nhưng writer sau đó lỗi và transaction database rollback, hành động ở service ngoài vẫn có thể đã xảy ra.

Ví dụ:

```text
Chunk bắt đầu
    |
    v
Processor gọi API đối tác
    |
    v
Đối tác xác nhận cập nhật thành công
    |
    v
Writer ghi database bị lỗi
    |
    v
Database transaction rollback

Kết quả: cập nhật ở đối tác vẫn tồn tại
```

Khi retry chunk hoặc restart Job, processor có thể gọi API lần nữa. Vì vậy, cần xác định service call chỉ đọc dữ liệu hay tạo tác dụng phụ.

- Với lời gọi chỉ đọc (GET/enrichment), retry thường an toàn hơn, nhưng response có thể thay đổi theo thời gian. Nếu cần tính nhất quán, nên dùng snapshot hoặc version dữ liệu.
- Với lời gọi ghi hoặc tạo hành động (POST thanh toán, gửi thông báo, tạo lệnh), cần idempotency key hoặc cơ chế chống trùng ở hệ thống đích.
- Nếu phải đồng bộ thay đổi database và message/API, cân nhắc transactional outbox hoặc một quy trình saga/đối soát phù hợp thay vì giả định hai hệ thống có chung transaction.

## 8. Thiết kế idempotency cho service call

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng định danh mà không tạo thêm tác dụng phụ ngoài ý muốn. Đây là yêu cầu quan trọng vì Spring Batch có thể retry item hoặc xử lý lại chunk sau rollback/restart.

Ví dụ, khi gửi yêu cầu tạo giao dịch đối tác, có thể tạo khóa duy nhất từ mã giao dịch nguồn:

```java
public PartnerResult createPartnerTransaction(
        SourceTransaction transaction) {

    String idempotencyKey = "settlement:" + transaction.id();

    return restClient.post()
            .uri("/transactions")
            .header("Idempotency-Key", idempotencyKey)
            .body(new PartnerRequest(
                    transaction.id(), transaction.amount()))
            .retrieve()
            .body(PartnerResult.class);
}
```

Đây là ví dụ minh họa; hệ thống đối tác phải hỗ trợ và thực thi đúng hợp đồng idempotency key thì cơ chế mới có tác dụng. Khóa cần ổn định giữa các lần retry, restart và các execution của cùng một nghiệp vụ. Không tạo UUID mới mỗi lần gọi nếu mục tiêu là nhận diện cùng một hành động.

Nếu service đích không hỗ trợ idempotency, có thể cần lưu trạng thái xử lý ở hệ thống của mình, dùng unique constraint hoặc xây dựng bước đối soát để phát hiện và xử lý giao dịch không rõ kết quả.

## 9. Hiệu năng khi gọi service cho từng item

Nếu Job xử lý 500.000 item và mỗi item gọi một API, Job có thể tạo 500.000 request. Ngay cả khi mỗi request mất 100 ms, thời gian tổng có thể rất lớn nếu thực hiện tuần tự. Khi lập kế hoạch, cần ước lượng số lời gọi, latency, throughput giới hạn của service đích và khả năng chịu tải của mạng.

Một số cách cải thiện:

### Cache dữ liệu tham chiếu

Nếu nhiều item tra cứu cùng một mã khách hàng hoặc danh mục ít thay đổi, cache có thể giảm số request. Cần chọn TTL, giới hạn dung lượng và chính sách invalidation phù hợp. Không cache dữ liệu nhạy cảm hoặc dữ liệu có yêu cầu nhất quán nghiêm ngặt mà chưa đánh giá rủi ro stale data.

### Batch API

Nếu service đích hỗ trợ tra cứu nhiều ID trong một request, có thể gom các khóa để gọi API theo lô. Vì `ItemProcessor` nhận từng item, việc gom request có thể cần một lớp cache/buffer có kiểm soát hoặc chuyển logic lấy dữ liệu sang reader/writer phù hợp. Không nên tự tạo buffer làm thay đổi thứ tự hoặc gây mất dữ liệu khi restart.

### Giới hạn mức song song

Tăng thread có thể tăng throughput, nhưng cũng tăng số request đồng thời. Cần giới hạn worker, connection pool, concurrency và rate theo quota của service đích. Nếu hệ thống đối tác chỉ cho phép 50 request/giây, cấu hình batch không nên vượt giới hạn đó.

### Tối ưu dữ liệu gửi đi

Chỉ gửi các trường cần thiết, tái sử dụng HTTP client và tránh tải lại dữ liệu có thể lấy từ nguồn ban đầu. Nếu dữ liệu tham chiếu đã có sẵn trong database hoặc snapshot, đọc theo lô có thể hiệu quả hơn gọi API cho từng item.

## 10. Thread safety khi Step chạy song song

Nếu Step dùng multi-threading hoặc partitioning, nhiều lần gọi `process()` có thể diễn ra đồng thời. Processor và service được inject thường là singleton bean, vì vậy không nên lưu trạng thái riêng của item trong mutable field dùng chung.

Ví dụ không an toàn:

```java
@Component
public class UnsafeProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private OrderInput currentItem; // Trạng thái dùng chung giữa các thread

    @Override
    public EnrichedOrder process(OrderInput item) {
        currentItem = item;
        // Một thread khác có thể ghi đè currentItem tại đây.
        return convert(currentItem);
    }
}
```

Nên giữ dữ liệu xử lý trong biến cục bộ của phương thức:

```java
@Component
public class SafeProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService profileService;

    public SafeProcessor(CustomerProfileService profileService) {
        this.profileService = profileService;
    }

    @Override
    public EnrichedOrder process(OrderInput item) {
        CustomerProfile profile = profileService
                .findByCustomerId(item.customerId());

        return convert(item, profile);
    }
}
```

Service và HTTP client cũng cần an toàn khi được gọi đồng thời. Kiểm tra tài liệu của client, cache và thư viện dùng chung; bảo đảm connection pool và giới hạn concurrency được cấu hình phù hợp. Nếu processor không thread-safe, không nên bật multi-threaded Step chỉ để tăng tốc.

## 11. Logging và theo dõi service call

Khi processor gọi service ngoài, log cần giúp xác định item nào gặp lỗi và service nào đang chậm. Nên ghi:

- JobExecution ID và StepExecution ID.
- Mã item hoặc business key, tránh log toàn bộ dữ liệu nhạy cảm.
- Tên service/endpoint ở mức phù hợp.
- Thời gian gọi, trạng thái kết quả và số lần retry.
- Mã lỗi hoặc correlation ID từ hệ thống đích.

Không nên log access token, password, dữ liệu cá nhân hoặc toàn bộ payload nếu không có nhu cầu và kiểm soát truy cập phù hợp. Metrics nên theo dõi latency p50/p95/p99, tỷ lệ lỗi, số lần retry, số request/giây và số circuit breaker mở. Các chỉ số này giúp phân biệt Job chậm do processor hay do service phụ thuộc.

## 12. Kiểm thử processor có service phụ thuộc

Vì processor phụ thuộc vào interface service, có thể kiểm thử logic mà không cần gọi hệ thống thật bằng mock hoặc fake service.

Ví dụ với Mockito:

```java
@ExtendWith(MockitoExtension.class)
class EnrichOrderProcessorTest {

    @Mock
    CustomerProfileService profileService;

    @InjectMocks
    EnrichOrderProcessor processor;

    @Test
    void enrichesOrderUsingCustomerProfile() {
        OrderInput input = new OrderInput("O-100", "C-10", new BigDecimal("50.00"));
        CustomerProfile profile = new CustomerProfile("C-10", "GOLD");

        when(profileService.findByCustomerId("C-10"))
                .thenReturn(profile);

        EnrichedOrder result = processor.process(input);

        assertEquals("O-100", result.orderId());
        assertEquals("GOLD", result.membershipLevel());
    }
}
```

Ngoài trường hợp thành công, nên kiểm thử service trả về không tìm thấy dữ liệu, ném lỗi tạm thời, ném lỗi nghiệp vụ và processor lọc item nếu có. Kiểm thử tích hợp riêng có thể xác nhận HTTP timeout, mapping status code, authentication và serialization. Không nên để unit test phụ thuộc mạng hoặc endpoint production.

## 13. Khi nào không nên gọi service trực tiếp từ processor?

Không nên gọi service trực tiếp trong processor nếu:

- Mỗi item yêu cầu một request nhưng API chỉ hỗ trợ batch và khối lượng dữ liệu rất lớn.
- Service có latency cao hoặc giới hạn request thấp khiến Job không thể hoàn tất trong batch window.
- Lời gọi tạo tác dụng phụ không có idempotency, trong khi chunk có thể retry hoặc restart.
- Dữ liệu cần tra cứu đã có thể được join hoặc lấy theo batch hiệu quả hơn từ database.
- Nghiệp vụ cần một snapshot nhất quán nhưng service trả dữ liệu thay đổi theo thời gian.
- Processor cần trạng thái mutable dùng chung hoặc phụ thuộc vào thứ tự thực thi song song.

Trong các trường hợp này, cân nhắc tải dữ liệu tham chiếu trước thành snapshot, dùng reader đọc từ nguồn đã chuẩn bị, gọi API theo lô hoặc chuyển thao tác ghi sang writer với cơ chế idempotent. Mục tiêu là đặt trách nhiệm ở thành phần phù hợp và giữ khả năng restart đáng tin cậy.

## Kết luận

`ItemProcessor` có thể sử dụng service được inject để bổ sung dữ liệu hoặc áp dụng quy tắc nghiệp vụ cho từng item. Nên phụ thuộc vào interface, quản lý HTTP client tập trung và phân loại rõ lỗi tạm thời với lỗi dữ liệu. Khi gọi service ngoài, cần đặt timeout, retry có giới hạn và backoff; hiểu rằng transaction của chunk không rollback được tác dụng phụ ở hệ thống độc lập; đồng thời dùng idempotency để bảo vệ khi retry hoặc restart. Với Job lớn, hãy đo latency, cache hoặc gọi theo lô khi phù hợp, giới hạn mức song song và bảo đảm processor cùng service an toàn khi nhiều thread thực thi.
