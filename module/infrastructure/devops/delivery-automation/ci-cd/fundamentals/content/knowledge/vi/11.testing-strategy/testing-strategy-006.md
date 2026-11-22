# Kiểm thử với dịch vụ thật, môi trường cô lập hoặc đối tượng thay thế

Một bài kiểm thử có thể chạy nhanh nhưng chưa chắc phản ánh đúng cách ứng dụng hoạt động khi kết nối database, gọi API hoặc gửi message. Ngược lại, một bài kiểm thử dùng toàn bộ dịch vụ thật có thể chậm, khó thiết lập và dễ thất bại do mạng hoặc dữ liệu dùng chung. Vì vậy, thiết kế chiến lược kiểm thử cần quyết định rõ khi nào nên dùng dịch vụ thật, khi nào nên dựng dịch vụ trong môi trường cô lập và khi nào nên thay dependency bằng test double.

Ba lựa chọn này giải quyết các câu hỏi khác nhau. Dịch vụ thật cho biết ứng dụng có tương tác đúng với triển khai thực tế của dependency hay không. Môi trường cô lập giúp chạy triển khai thật trong một phạm vi riêng, có vòng đời và dữ liệu kiểm soát được. Test double cho phép kiểm tra logic của thành phần đang xét mà không phụ thuộc vào dịch vụ bên ngoài.

Không có một lựa chọn duy nhất phù hợp cho mọi test. Một chiến lược tốt phối hợp chúng theo rủi ro: dùng test double để kiểm tra nhánh logic và tình huống lỗi; dùng dịch vụ thật trong container hoặc sandbox để xác minh tích hợp; dùng môi trường staging hoặc dịch vụ test được quản lý để kiểm tra các hợp đồng và hành vi chỉ có thể quan sát ở hệ thống thật.

## 1. Phân biệt ba cách tiếp cận

### Dịch vụ thật

Dịch vụ thật là triển khai thực tế của dependency mà ứng dụng sẽ sử dụng, chẳng hạn PostgreSQL, Redis, Kafka hoặc API của nhà cung cấp. Dịch vụ có thể chạy trên máy local, trong container, trên máy ảo hoặc trong môi trường test dùng chung.

Khi dùng dịch vụ thật, bài kiểm thử đi qua giao thức, driver, serialization, transaction và hành vi của triển khai đó. Ví dụ, test repository với PostgreSQL thật có thể phát hiện cú pháp SQL không tương thích, khác biệt kiểu dữ liệu, lỗi constraint hoặc hành vi transaction mà một mock repository không thể chứng minh.

Dịch vụ thật không nhất thiết là production service. Một database PostgreSQL khởi chạy riêng cho test vẫn là triển khai database thật, dù nó chạy bằng container và chỉ chứa dữ liệu giả.

### Môi trường cô lập

Môi trường cô lập là một phạm vi thực thi được tạo riêng cho một lần chạy hoặc một nhóm test. Nó có thể chứa dịch vụ thật nhưng có network, dữ liệu, cấu hình và vòng đời riêng.

Ví dụ:

- Khởi chạy PostgreSQL bằng Testcontainers cho một test suite.
- Tạo Docker Compose project riêng cho mỗi CI job.
- Dùng namespace Kubernetes tạm cho integration test.
- Tạo database hoặc schema riêng cho mỗi worker.
- Dùng máy ảo sạch để kiểm tra package cài đặt.

Cô lập là thuộc tính của môi trường và vòng đời tài nguyên. Nó không đồng nghĩa với việc dùng mock. Một PostgreSQL container là dịch vụ thật chạy trong môi trường cô lập.

### Đối tượng thay thế (test double)

Test double là một đối tượng thay cho dependency thật trong test. Nó có thể trả dữ liệu cố định, mô phỏng lỗi hoặc ghi nhận lời gọi để kiểm tra tương tác.

Ví dụ, khi kiểm tra logic tính phí đơn hàng, có thể thay PaymentGateway bằng một stub trả về kết quả thanh toán thành công hoặc thất bại. Test tập trung vào cách OrderService phản ứng mà không gọi mạng hoặc tạo giao dịch thật.

Test double giúp kiểm soát đầu vào và kết quả, nhưng không chứng minh ứng dụng tương thích với giao thức hoặc hành vi của dịch vụ thật. Nếu mock trả về một cấu trúc không giống phản hồi thật, test có thể xanh trong khi ứng dụng vẫn lỗi khi tích hợp.

## 2. So sánh trade-off

| Tiêu chí | Dịch vụ thật | Môi trường cô lập | Test double |
|---|---|---|---|
| Tính chân thực | Cao, phản ánh triển khai dependency | Cao nếu chứa đúng dịch vụ và cấu hình cần kiểm tra | Phụ thuộc mức độ mô phỏng |
| Tốc độ | Có thể chậm do khởi động và I/O | Có chi phí khởi tạo, nhưng vòng đời được kiểm soát | Thường nhanh |
| Độ ổn định | Có thể bị ảnh hưởng bởi mạng, tải và trạng thái dùng chung | Tốt hơn khi tài nguyên riêng và có thể tạo lại | Cao nếu test double đơn giản |
| Khả năng kiểm soát | Hạn chế với hệ thống bên ngoài | Cao hơn nhờ cấu hình và dữ liệu riêng | Rất cao |
| Phát hiện lỗi tích hợp | Tốt | Tốt nếu chạy dịch vụ thật | Hạn chế |
| Mô phỏng lỗi hiếm | Khó nếu phụ thuộc dịch vụ thật | Có thể cấu hình fault hoặc proxy | Dễ tạo timeout, lỗi xác định, phản hồi bất thường |
| Chi phí vận hành | Có thể cao nếu dùng hệ thống dùng chung | Cần quản lý image, tài nguyên và cleanup | Thấp hơn, nhưng cần duy trì test double |
| Phù hợp nhất | Kiểm tra hành vi và tương thích thực tế | Integration test có thể tái tạo | Unit test và kiểm tra logic có nhánh |

Không nên xem dịch vụ thật luôn tốt hơn hoặc test double luôn kém hơn. Dịch vụ thật trả lời câu hỏi về tích hợp; test double trả lời câu hỏi về logic trong điều kiện được kiểm soát. Dùng sai công cụ có thể tạo ra bằng chứng yếu: mock quá sâu làm mất kiểm tra tích hợp, còn dựng toàn bộ hệ thống cho một phép tính đơn giản làm test chậm và khó chẩn đoán.

## 3. Chọn theo câu hỏi mà test cần trả lời

Trước khi chọn công cụ, hãy viết rõ điều muốn chứng minh.

- Nếu câu hỏi là "quy tắc tính phí xử lý đúng khi gateway từ chối thanh toán không?", một stub hoặc fake thường đủ.
- Nếu câu hỏi là "repository có lưu và đọc dữ liệu đúng trên PostgreSQL không?", cần PostgreSQL thật.
- Nếu câu hỏi là "dịch vụ có khởi động từ image đã publish và kết nối đúng với database không?", cần chạy artifact trong môi trường consumer cô lập.
- Nếu câu hỏi là "ứng dụng có gửi đúng request theo hợp đồng của nhà cung cấp không?", có thể dùng contract test hoặc sandbox của nhà cung cấp.
- Nếu câu hỏi là "khi broker tạm mất kết nối, ứng dụng retry và phục hồi thế nào?", cần kết hợp fault injection có kiểm soát với test tích hợp phù hợp.

Một test nên có một mục tiêu chính. Nếu test vừa kiểm tra thuật toán nghiệp vụ, vừa kiểm tra kết nối database, vừa gọi API bên ngoài, khi thất bại sẽ khó biết lỗi thuộc thành phần nào. Tách test theo ranh giới giúp phản hồi nhanh và làm rõ bằng chứng.

## 4. Chọn dịch vụ thật theo rủi ro tích hợp

Nên ưu tiên dịch vụ thật khi dependency có hành vi mà test double khó mô phỏng chính xác hoặc khi rủi ro tương thích cao.

**Database và transaction.** SQL dialect, isolation level, locking, constraint, migration và kiểu dữ liệu phụ thuộc vào hệ quản trị. Test với database cùng loại giúp phát hiện khác biệt thực tế.

**Message broker.** Routing key, partition, consumer group, acknowledgement, redelivery và ordering phụ thuộc vào broker. Một fake queue đơn giản không thể chứng minh những đặc tính này.

**Cache.** TTL, eviction, serialization, atomic operation và distributed lock cần được kiểm tra với loại cache thật nếu chúng ảnh hưởng đến correctness.

**Protocol và serialization.** Khi ứng dụng giao tiếp qua HTTP, gRPC hoặc message format, cần có test xác minh wire format, header, status code và schema.

**Native library hoặc hệ thống phụ thuộc nền tảng.** Một số hành vi chỉ xuất hiện khi chạy với thư viện hoặc runtime thực tế.

Không cần gọi dịch vụ production để có dịch vụ thật. Dùng phiên bản test, container hoặc sandbox thường an toàn và dễ tái tạo hơn.

## 5. Khi nào test double là lựa chọn phù hợp?

Test double đặc biệt hữu ích khi dependency chậm, đắt, khó truy cập hoặc có tác dụng phụ. Nó cũng giúp tạo tình huống khó xảy ra một cách ổn định.

Ví dụ:

- Gateway thanh toán trả về thành công, từ chối hoặc trạng thái đang xử lý.
- API bên ngoài trả timeout, HTTP 429 hoặc HTTP 503.
- Đồng hồ trả về thời điểm cố định để kiểm tra hết hạn.
- Dịch vụ gửi email ghi nhận nội dung thay vì gửi email thật.
- Hệ thống lưu trữ giả lập lỗi disk hoặc quyền truy cập.
- Một dependency trả dữ liệu lớn hoặc dữ liệu biên mà không cần chuẩn bị hệ thống thật.

Test double nên thay đúng ranh giới bên ngoài. Không nên mock mọi lớp nội bộ trong cùng module. Nếu test phải mô tả hàng chục lời gọi nội bộ theo đúng thứ tự, nó có thể đang kiểm tra cấu trúc triển khai thay vì hành vi mà người dùng hoặc thành phần khác quan sát được.

## 6. Các loại test double

Các thuật ngữ thường gặp:

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Dummy | Đối tượng được truyền vào nhưng test không sử dụng | Một context rỗng để thỏa tham số constructor |
| Stub | Trả về dữ liệu đã định trước | Gateway trả về PaymentApproved |
| Fake | Triển khai đơn giản nhưng có hành vi thực thi được | In-memory repository lưu dữ liệu trong map |
| Mock | Cho phép kỳ vọng và xác minh lời gọi | Kiểm tra gateway được gọi đúng một lần với request phù hợp |
| Spy | Bao bọc hoặc ghi nhận lời gọi của đối tượng thực | Ghi nhận số lần gọi phương thức trong khi vẫn thực thi logic |

Một fake có thể hữu ích cho unit test, nhưng không thay thế integration test với database thật. In-memory repository có thể không hỗ trợ transaction, unique constraint, locking hoặc query semantics giống database production.

Stub và mock cũng có mục tiêu khác nhau. Stub cung cấp phản hồi để test quan sát kết quả. Mock thường dùng để xác minh tương tác. Nên ưu tiên kiểm tra kết quả hoặc trạng thái quan sát được; chỉ kiểm tra tương tác khi việc gọi dependency là một phần quan trọng của hợp đồng.

## 7. Ví dụ: kiểm tra logic nghiệp vụ bằng stub

Giả sử OrderService cần gọi PaymentGateway để thanh toán đơn hàng. Logic nghiệp vụ cần quyết định trạng thái đơn khi thanh toán được chấp nhận hoặc từ chối.

Có thể định nghĩa ranh giới dependency:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

public record PaymentRequest(String orderId, long amount) {}

public record PaymentResult(boolean approved, String reference) {}
```

Test có thể dùng stub đơn giản:

```java
final class ApprovedPaymentGateway implements PaymentGateway {
    @Override
    public PaymentResult charge(PaymentRequest request) {
        return new PaymentResult(true, "test-reference");
    }
}
```

Và kiểm tra hành vi của service:

```java
@Test
void confirmsOrderWhenPaymentIsApproved() {
    PaymentGateway gateway = new ApprovedPaymentGateway();
    OrderService service = new OrderService(gateway);

    OrderResult result = service.placeOrder(
        new OrderCommand("order-100", 250_000)
    );

    assertEquals(OrderStatus.CONFIRMED, result.status());
}
```

Đây là ví dụ khái niệm; kiểu dữ liệu và constructor cần khớp với ứng dụng thực tế. Test này tập trung vào quy tắc nghiệp vụ khi gateway chấp nhận thanh toán. Nó không kiểm tra HTTP client, TLS, authentication, request serialization hoặc API của nhà cung cấp.

Có thể tạo thêm stub từ chối thanh toán để kiểm tra trạng thái bị từ chối. Không cần dựng dịch vụ thanh toán thật cho từng nhánh logic như vậy.

## 8. Ví dụ: kiểm tra repository với PostgreSQL thật trong container

Khi cần xác minh repository dùng đúng SQL và migration, nên chạy test với cùng loại database mà ứng dụng hỗ trợ. Testcontainers giúp test Java tạo và quản lý container dịch vụ theo vòng đời test.

Ví dụ dưới đây dùng JUnit 5, Testcontainers và Spring Boot để cung cấp URL database động:

```java
@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void persistsAndReadsOrder() {
        Order saved = repository.save(new Order("order-200", 250_000));

        Order loaded = repository.findById(saved.getId()).orElseThrow();

        assertEquals("order-200", loaded.getExternalId());
    }
}
```

Đây là ví dụ dành cho ứng dụng Spring Boot. Dự án cần dependency Testcontainers JUnit Jupiter và PostgreSQL module, cùng cấu hình Spring phù hợp. Phiên bản image nên được khóa theo chính sách của dự án; trong môi trường yêu cầu chặt, có thể dùng digest. Testcontainers cần một Docker-compatible runtime hoặc môi trường container tương thích trên máy local và CI.

Điểm quan trọng là repository được chạy với PostgreSQL thật, nhưng database được tạo riêng cho test. Khi test kết thúc, container có thể được dừng và xóa. Test này kiểm tra được SQL, schema, driver và hành vi database thực tế hơn một mock repository.

Nếu ứng dụng không dùng Spring, có thể khởi chạy container bằng API Testcontainers trong lifecycle của JUnit, lấy JDBC URL, tạo DataSource và truyền vào repository. Nguyên tắc vẫn là dùng dịch vụ thật với cấu hình được tạo cho test.

## 9. Môi trường cô lập không nhất thiết phải là một container cho mỗi test

Tạo một container cho mỗi phương thức test có thể rất tốn thời gian. Có thể chọn vòng đời theo mức cô lập cần thiết:

- **Theo test method:** mức cô lập cao, phù hợp test cần trạng thái hoàn toàn mới nhưng tốn thời gian khởi động.
- **Theo test class:** cân bằng giữa tốc độ và cô lập; mỗi class có thể dùng database riêng hoặc reset schema.
- **Theo test suite:** nhanh hơn, nhưng test phải quản lý dữ liệu và trạng thái chặt chẽ.
- **Theo CI job:** nhiều test dùng chung stack dịch vụ tạm; cần schema, topic hoặc tenant riêng để tránh va chạm.
- **Dịch vụ test dùng chung:** tiết kiệm tài nguyên nhưng cần cơ chế phân vùng dữ liệu, quyền và cleanup rõ ràng.

Không có vòng đời đúng cho mọi dự án. Chọn mức nhỏ nhất vẫn đáp ứng mục tiêu test và không làm test phụ thuộc vào thứ tự chạy.

Nếu dùng một database cho cả suite, hãy đảm bảo test không đọc dữ liệu do test trước tạo ra. Có thể dùng transaction rollback cho test đồng bộ, nhưng cách này không luôn hiệu quả với thread khác, asynchronous worker, message broker hoặc DDL. Khi cần, tạo schema hoặc database riêng theo test class/worker.

## 10. Dùng sandbox hoặc dịch vụ test của nhà cung cấp

Một số hệ thống bên ngoài có sandbox chính thức, ví dụ payment gateway, identity provider, email service hoặc API đối tác. Sandbox thường triển khai gần với dịch vụ thật nhưng dùng tài khoản, dữ liệu và endpoint test.

Sandbox hữu ích để kiểm tra:

- Authentication và token flow.
- Request/response schema.
- Status code và error code thực tế.
- Webhook hoặc callback.
- Quy trình nghiệp vụ nhiều bước.
- Tương thích với phiên bản API đang sử dụng.

Sandbox vẫn có thể giới hạn tính năng, dữ liệu và độ ổn định. Nó có thể bị rate limit, bảo trì hoặc không mô phỏng đầy đủ production. Vì vậy, test sandbox nên được phân biệt với unit test và integration test chạy local.

Không nên gọi sandbox bên ngoài trong mọi unit test hoặc mọi lần chạy nhanh nếu điều đó làm feedback phụ thuộc mạng. Có thể chạy một nhóm kiểm tra sandbox có kiểm soát trong CI theo lịch, trước release hoặc khi thay đổi adapter/API quan trọng. Cần quản lý credential test riêng và không để chúng xuất hiện trong log.

## 11. Contract test là cầu nối giữa test double và dịch vụ thật

Contract test kiểm tra thỏa thuận giao tiếp giữa consumer và provider. Nó hữu ích khi không thể hoặc không cần khởi động toàn bộ hệ thống trong mỗi lần test.

Consumer contract ghi lại những request mà consumer gửi và phản hồi mà consumer kỳ vọng. Provider verification kiểm tra provider thật có đáp ứng hợp đồng đó không. Cách này giúp phát hiện sự lệch nhau về field, kiểu dữ liệu, status hoặc quy tắc tương thích.

Ví dụ, consumer có thể kỳ vọng API trả về trường status với một trong các giá trị đã quy định. Một stub HTTP có thể giúp kiểm tra consumer xử lý phản hồi đó; provider contract test xác minh dịch vụ thật vẫn trả cấu trúc tương ứng.

Contract test không thay thế mọi integration test. Nó tập trung vào giao diện giữa hai thành phần. Các vấn đề về transaction, network, timeout, authentication hoặc cấu hình triển khai vẫn có thể cần test tích hợp.

## 12. Kiểm tra API bằng server giả lập

Khi kiểm tra HTTP client, có thể dùng mock server cục bộ như WireMock hoặc MockWebServer. Server giả lập nhận request thật từ HTTP client và trả response đã định nghĩa.

Khác với việc mock trực tiếp phương thức của HTTP client, cách này vẫn đi qua serialization, header, URL, timeout và một phần network stack của ứng dụng. Nó có thể phát hiện lỗi như sai path, thiếu header hoặc parse response không đúng.

Một kịch bản có thể gồm:

1. Khởi động mock server trên cổng ngẫu nhiên.
2. Cấu hình HTTP client dùng base URL của server.
3. Khai báo response thành công, lỗi hoặc chậm.
4. Gọi service đang dùng HTTP client.
5. Kiểm tra kết quả nghiệp vụ và request server đã nhận.
6. Dừng server sau test.

Mock server vẫn không chứng minh API nhà cung cấp thực sự có hành vi đó. Khi hợp đồng API thay đổi, fixture có thể lỗi thời. Nên lấy ví dụ response từ schema hoặc contract được quản lý, và có kiểm tra bổ sung với sandbox hoặc provider contract.

## 13. Kiểm tra lỗi và tình huống bất thường

Dịch vụ thật thường khó tạo ra một số tình huống lỗi đúng thời điểm. Test double hoặc fault injection có kiểm soát giúp kiểm tra những trường hợp này.

Các tình huống quan trọng:

- Timeout trước khi nhận phản hồi.
- Kết nối bị đóng giữa chừng.
- HTTP 429 hoặc 503.
- Database từ chối kết nối hoặc deadlock.
- Broker redeliver message.
- Message trùng lặp hoặc đến sai thứ tự.
- Response thiếu field hoặc chứa giá trị không hợp lệ.
- Dịch vụ trả thành công nhưng quá chậm.
- Dịch vụ đã xử lý request nhưng client bị timeout trước khi nhận kết quả.

Không phải lỗi nào cũng có thể retry an toàn. Ví dụ, khi request thanh toán đã được xử lý nhưng phản hồi bị mất, client không thể kết luận giao dịch chưa xảy ra. Test nên xác minh idempotency key, truy vấn trạng thái hoặc cơ chế reconciliation thay vì chỉ kiểm tra số lần retry.

Nên kết hợp:
- Stub để tạo lỗi xác định cho logic retry.
- Mock server hoặc proxy để kiểm tra HTTP client và timeout.
- Dịch vụ thật trong container để kiểm tra lỗi kết nối hoặc hành vi protocol có thể tái hiện.
- Sandbox hoặc staging để kiểm tra quy trình tích hợp cuối với nhà cung cấp.

## 14. Quản lý dữ liệu kiểm thử

Dịch vụ thật làm cho dữ liệu test trở thành một phần quan trọng của tính ổn định. Nếu test phụ thuộc vào bản ghi đã tồn tại từ lần chạy trước, kết quả có thể thay đổi theo thứ tự hoặc môi trường.

Các nguyên tắc:

- Tạo dữ liệu đầu vào rõ ràng trong test setup.
- Dùng định danh duy nhất theo test, class hoặc worker.
- Không dùng dữ liệu khách hàng thật nếu không có cơ chế bảo vệ và phê duyệt phù hợp.
- Xóa hoặc reset dữ liệu sau test theo phạm vi sở hữu.
- Kiểm tra migration từ schema sạch và từ phiên bản được hỗ trợ nâng cấp.
- Không giả định transaction rollback có thể hoàn tác mọi tác dụng phụ bên ngoài database.
- Tránh dùng chung tài khoản, topic hoặc bucket cho nhiều test chạy song song nếu không có phân vùng.

Với database, có thể dùng schema riêng cho mỗi worker, truncate bảng theo thứ tự phù hợp hoặc tạo database mới. Với message broker, có thể dùng topic/queue riêng hoặc consumer group riêng. Với object storage, dùng bucket hoặc prefix riêng có mã run.

Dữ liệu test cần đủ đại diện để kiểm tra constraint và trường hợp biên, nhưng phải có thể tạo lại. Nếu fixture được lưu trong repository, hãy review chúng như mã nguồn và tránh chứa dữ liệu nhạy cảm.

## 15. Cô lập và chạy song song

Chạy test song song giúp giảm thời gian CI nhưng có thể gây race condition nếu nhiều test chia sẻ tài nguyên.

Các nguồn xung đột thường gặp:

- Hai test ghi cùng một bản ghi hoặc cập nhật cùng một trạng thái.
- Hai worker dùng chung schema hoặc sequence.
- Một test xóa dữ liệu mà test khác đang đọc.
- Nhiều test cùng sử dụng cổng cố định.
- Test dùng chung file hoặc thư mục tạm.
- Consumer group hoặc queue nhận message của test khác.
- Rate limit của sandbox bị chia sẻ.

Biện pháp:

- Tạo tài nguyên có tên duy nhất theo test run và worker.
- Dùng cổng ngẫu nhiên hoặc cơ chế cấp cổng động.
- Chia database schema, topic, bucket hoặc tenant.
- Không dựa vào thứ tự test.
- Cleanup bằng lifecycle hook và có cơ chế dọn tài nguyên rò rỉ.
- Giới hạn concurrency khi dịch vụ không đủ tài nguyên.
- Dùng timeout để phát hiện test treo.

Mỗi test nên sở hữu rõ tài nguyên nó tạo ra. Cleanup chỉ xóa tài nguyên thuộc phạm vi test, không xóa database hoặc bucket dùng chung. Với môi trường tạm, có thể gắn nhãn theo run ID và có job dọn tài nguyên quá hạn để xử lý trường hợp runner bị ngắt đột ngột.

## 16. Đảm bảo readiness và quản lý vòng đời dịch vụ

Một container ở trạng thái running chưa chắc database hoặc broker đã sẵn sàng nhận request. Test khởi chạy quá sớm có thể thất bại ngẫu nhiên.

Cần phân biệt:

- Process đã được tạo.
- Cổng đã mở.
- Service đã sẵn sàng nhận request.
- Service đã hoàn tất migration hoặc khởi tạo dữ liệu.
- Ứng dụng phụ thuộc đã kết nối và hoạt động bình thường.

Dùng health check hoặc wait strategy dựa trên điều kiện thật, chẳng hạn truy vấn database thành công, HTTP health endpoint trả trạng thái sẵn sàng hoặc broker có thể tạo và đọc message. Không dùng sleep cố định dài như giải pháp duy nhất; nó vừa chậm vừa không bảo đảm service đã sẵn sàng.

Vòng đời cần có timeout và cleanup. Nếu khởi động thất bại, test phải báo rõ service nào không sẵn sàng. Nếu test thất bại, tài nguyên vẫn cần được dọn trong finally hoặc lifecycle hook. CI cũng nên có bước cleanup cho tài nguyên bên ngoài container khi job bị hủy.

## 17. Xây dựng chiến lược theo lớp kiểm thử

Một chiến lược thực tế thường phối hợp nhiều loại test:

| Lớp | Dependency thường dùng | Mục tiêu | Tần suất |
|---|---|---|---|
| Unit test | Stub, fake, mock có chọn lọc | Kiểm tra logic nhanh và nhiều trường hợp biên | Mọi thay đổi |
| Component test | Một số dịch vụ thật hoặc fake | Kiểm tra một thành phần với ranh giới rõ | Mọi PR hoặc theo module |
| Integration test | Database, broker, mock server hoặc dịch vụ thật trong container | Kiểm tra giao thức, persistence và phối hợp | Mọi PR quan trọng hoặc trước merge |
| Contract test | Contract fixture và provider verification | Phát hiện lệch giao diện consumer/provider | Khi đổi API hoặc theo pipeline |
| End-to-end test | Hệ thống tích hợp trên staging/sandbox | Kiểm tra luồng nghiệp vụ từ đầu đến cuối | Theo lịch hoặc trước release |
| Production verification | Kiểm tra an toàn sau triển khai | Xác nhận dịch vụ thực tế hoạt động | Sau mỗi lần deploy |

Đây không phải quy tắc cứng về số lượng test. Mỗi dự án cần chọn lớp và tần suất theo rủi ro, thời gian phản hồi và khả năng vận hành.

Một test unit không nên cần Docker hoặc network nếu mục tiêu chỉ là tính toán thuần. Một integration test cần PostgreSQL thật thì nên khai báo rõ yêu cầu runtime. Một end-to-end test không nên được dùng để thay thế toàn bộ unit test vì chậm và khó định vị lỗi.

## 18. Tích hợp vào CI/CD

CI cần cung cấp môi trường ổn định, phân biệt test bắt buộc với test mở rộng và thu thập bằng chứng khi thất bại.

Một pipeline có thể tổ chức:

1. Chạy unit test với test doubles trên mọi pull request.
2. Khởi chạy database/broker trong container cho integration test.
3. Chạy contract test cho API nội bộ hoặc dependency quan trọng.
4. Chạy nhóm test sandbox có giới hạn khi thay đổi adapter hoặc trước release.
5. Chạy end-to-end trên staging sau khi artifact được triển khai.
6. Ghi lại phiên bản image, digest dịch vụ, cấu hình test và kết quả.

Các test cần thiết để bảo vệ nhánh phải ổn định và có timeout hợp lý. Nếu dịch vụ phụ trợ không thể khởi động do lỗi runner, cần phân biệt lỗi hạ tầng với lỗi sản phẩm. Không nên retry vô hạn hoặc đánh dấu pass khi test bị bỏ qua.

Không cấp production secret cho job chạy mã pull request chưa tin cậy. Container test và dịch vụ phụ trợ cần dùng dữ liệu giả, credential giới hạn quyền và network chỉ mở tới dependency cần thiết.

Khi CI dùng cache, cache chỉ nên giúp tăng tốc. Test vẫn phải chạy được khi cache trống. Nếu môi trường test dùng image, hãy khóa phiên bản image và ghi lại digest để kết quả có thể truy vết.

## 19. Ví dụ quyết định: OrderService và các dependency

Giả sử một hệ thống đặt hàng có OrderService sử dụng PostgreSQL, Redis, PaymentGateway và message broker.

| Hành vi cần kiểm tra | Lựa chọn | Lý do |
|---|---|---|
| Tính tổng đơn hàng và áp dụng giảm giá | Unit test với dữ liệu trực tiếp | Logic thuần, không cần dịch vụ |
| Xử lý thanh toán bị từ chối | Stub PaymentGateway | Cần kiểm soát kết quả gateway |
| HTTP client gửi đúng header và parse response | Mock HTTP server | Kiểm tra giao thức client mà không gọi mạng ngoài |
| Repository lưu đơn và kiểm tra unique constraint | PostgreSQL trong container | Cần hành vi database thật |
| Cache TTL và serialization | Redis trong container | Cần xác minh semantics của Redis |
| Publish và consume message | Broker trong container | Cần kiểm tra protocol, acknowledgement và redelivery |
| Tích hợp với API thanh toán của nhà cung cấp | Sandbox hoặc contract test | Cần xác minh hợp đồng bên ngoài |
| Toàn bộ luồng đặt hàng từ API đến message và database | Staging hoặc môi trường E2E cô lập | Cần xác minh phối hợp nhiều thành phần |

Một bài test không cần sử dụng tất cả dependency cùng lúc. Chia theo ranh giới giúp xác định nhanh lỗi nằm ở logic đơn hàng, repository, adapter HTTP hay broker.

## 20. Những anti-pattern thường gặp

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| Mock repository trong mọi test | Không phát hiện SQL hoặc migration lỗi | Có integration test với database thật |
| Dùng database in-memory thay cho database production mà không đánh giá khác biệt | Bỏ sót dialect, transaction và constraint | Test với đúng engine hoặc phiên bản tương thích |
| Dùng production service cho test thường xuyên | Có tác dụng phụ, dữ liệu khó dọn và chi phí cao | Dùng container, sandbox hoặc test tenant |
| Mock mọi lớp nội bộ | Test phụ thuộc cấu trúc triển khai và dễ vỡ | Mock ở ranh giới bên ngoài, kiểm tra hành vi quan sát được |
| Fake được xem là tương đương dịch vụ thật | Bỏ sót khác biệt semantics | Duy trì integration/contract test |
| Dùng chung database và dữ liệu cố định | Test phụ thuộc thứ tự và chạy song song bị lỗi | Dùng dữ liệu, schema hoặc database riêng |
| Dùng sleep cố định để chờ service | Test chậm và vẫn có thể flaky | Dùng health check hoặc wait strategy |
| Không cleanup tài nguyên | Tài nguyên rò rỉ và làm test sau bị ảnh hưởng | Quản lý lifecycle và cleanup an toàn |
| Retry mọi test thất bại | Che giấu flaky test hoặc lỗi sản phẩm | Phân loại lỗi và giới hạn retry |
| Chạy test sandbox trong mọi unit test | Feedback chậm và phụ thuộc mạng | Tách thành nhóm kiểm tra riêng |
| Dùng cổng cố định cho nhiều worker | Xung đột khi chạy song song | Cấp cổng động |
| Test double trả cấu trúc không giống API thật | Test xanh nhưng tích hợp lỗi | Dùng schema/contract chung và provider verification |

## 21. Cách đưa chiến lược vào một dự án

Có thể bắt đầu theo từng bước:

1. **Liệt kê dependency bên ngoài:** database, cache, broker, API, file storage, clock và hệ thống có tác dụng phụ.
2. **Xác định rủi ro:** xem dependency nào có semantics quan trọng hoặc từng gây lỗi tích hợp.
3. **Định nghĩa ranh giới:** tách logic nghiệp vụ khỏi adapter, client và hạ tầng để có thể kiểm tra riêng.
4. **Chọn test double cho logic:** tạo stub/fake cho các phản hồi và lỗi cần kiểm soát.
5. **Dựng dịch vụ thật cho integration test:** dùng container hoặc môi trường test tạm với phiên bản được xác định.
6. **Thiết kế dữ liệu và cleanup:** bảo đảm test độc lập, chạy song song an toàn và không dùng dữ liệu production.
7. **Bổ sung contract/sandbox test:** dành cho các API hoặc provider có hợp đồng bên ngoài.
8. **Tích hợp CI:** phân nhóm theo tốc độ và rủi ro, đặt timeout, lưu report và giới hạn quyền.
9. **Theo dõi độ ổn định:** phân loại lỗi sản phẩm, lỗi hạ tầng và flaky test.
10. **Rà soát định kỳ:** bỏ test double không còn phản ánh hợp đồng, cập nhật image và phiên bản dịch vụ test.

Nên bắt đầu từ một dependency có rủi ro cao, chẳng hạn database hoặc payment adapter. Tạo một test với dịch vụ thật và một test với test double để làm rõ mỗi loại chứng minh điều gì. Sau đó mở rộng theo các ranh giới khác.

## 22. Đo chất lượng chiến lược kiểm thử

Không nên đánh giá chiến lược chỉ bằng số lượng test hoặc tỷ lệ coverage. Hãy quan sát liệu test có phát hiện lỗi ở đúng ranh giới và cung cấp phản hồi đủ nhanh hay không.

Một số chỉ số hữu ích:

- Thời gian chạy unit, integration, contract và end-to-end test.
- Tỷ lệ test thất bại do lỗi sản phẩm, hạ tầng hoặc flaky behavior.
- Tỷ lệ lỗi tích hợp chỉ được phát hiện sau merge hoặc sau deploy.
- Thời gian khởi động và cleanup dịch vụ test.
- Số lần test bị ảnh hưởng bởi dữ liệu hoặc tài nguyên dùng chung.
- Tỷ lệ dependency quan trọng có integration hoặc contract test.
- Số lần phải bypass test bắt buộc và lý do.
- Thời gian từ khi phát hiện lỗi đến khi có thể tái hiện cục bộ.

Nếu integration test quá chậm, có thể tối ưu việc tái sử dụng image, khởi tạo schema, chạy song song hoặc chọn phạm vi test. Không nên thay dịch vụ thật bằng mock chỉ để làm pipeline xanh nhanh hơn nếu rủi ro tích hợp vẫn còn.

## 23. Checklist lựa chọn phương pháp

Trước khi quyết định một test dùng dịch vụ thật, môi trường cô lập hay test double, hãy kiểm tra:

- [ ] Câu hỏi mà test cần trả lời đã được mô tả rõ.
- [ ] Dependency có hành vi hoặc semantics nào cần xác minh thực tế?
- [ ] Có thể dùng test double để kiểm tra logic mà không làm mất bằng chứng tích hợp cần thiết?
- [ ] Nếu dùng dịch vụ thật, phiên bản và cấu hình có phù hợp với hệ thống mục tiêu?
- [ ] Môi trường test có thể tạo mới và dọn dẹp an toàn?
- [ ] Dữ liệu test được sở hữu riêng và có thể tạo lại?
- [ ] Test không phụ thuộc thứ tự hoặc trạng thái của test khác?
- [ ] Có readiness check, timeout và xử lý lỗi khởi động?
- [ ] Test có thể chạy song song mà không tranh chấp tài nguyên?
- [ ] Credential và dữ liệu được giới hạn ở mức test?
- [ ] CI phân biệt lỗi sản phẩm với lỗi hạ tầng?
- [ ] Contract hoặc sandbox test được tách khỏi nhóm unit test nhanh?
- [ ] Test double có phản ánh đúng hợp đồng cần kiểm tra?
- [ ] Có ít nhất một lớp kiểm tra với triển khai thật cho dependency có rủi ro cao?

## Kết luận

Dịch vụ thật, môi trường cô lập và test double là những công cụ bổ sung cho nhau. Dịch vụ thật giúp xác minh hành vi tích hợp; môi trường cô lập làm cho dịch vụ và dữ liệu có thể tạo lại, kiểm soát và dọn dẹp; test double giúp kiểm tra logic nhanh và mô phỏng những phản hồi hoặc lỗi khó tạo ra trong hệ thống thật.

Chiến lược CI/CD tốt chọn phương pháp theo câu hỏi và rủi ro của từng test. Dùng test double ở ranh giới phù hợp, kiểm tra dependency quan trọng bằng triển khai thật, cô lập tài nguyên và dữ liệu, rồi tổ chức các lớp test với thời gian phản hồi hợp lý. Nhờ đó, nhóm vừa có phản hồi nhanh khi phát triển vừa có bằng chứng đáng tin cậy rằng các thành phần thực sự phối hợp được với nhau.

