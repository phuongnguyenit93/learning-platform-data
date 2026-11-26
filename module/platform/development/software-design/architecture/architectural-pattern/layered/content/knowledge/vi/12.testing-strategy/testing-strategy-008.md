# Chiến lược kiểm thử

## Kiểm thử tích hợp xuyên tầng cho các ca sử dụng quan trọng

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — một ca sử dụng quan trọng thường đi qua nhiều ranh giới: HTTP controller tiếp nhận yêu cầu, application service điều phối, domain model áp dụng quy tắc, repository lưu dữ liệu và adapter giao tiếp với hệ thống bên ngoài. Kiểm thử từng class riêng lẻ không chứng minh được toàn bộ các phần này phối hợp đúng khi được lắp ghép.

**Kiểm thử tích hợp xuyên tầng** xác minh một luồng nghiệp vụ thực tế đi qua những thành phần và ranh giới quan trọng của ứng dụng. Mục tiêu là phát hiện lỗi ở wiring, mapping, transaction, truy vấn, bảo mật và hợp đồng giữa các tầng — những lỗi có thể không xuất hiện khi từng thành phần được kiểm thử độc lập.

Bài học dùng ví dụ đặt hàng trong Java/Spring. Chiến lược phù hợp không phải là khởi động mọi hệ thống phụ thuộc trong mọi test; cần chọn phạm vi tích hợp đủ rộng để kiểm chứng rủi ro của ca sử dụng, đồng thời giữ dữ liệu và các dịch vụ ngoài trong trạng thái có thể kiểm soát.

## 1. Vì sao cần kiểm thử xuyên tầng?

Một bộ unit test có thể xác nhận `Order` tính tổng tiền đúng, `PlaceOrderService` gọi repository và controller ánh xạ response. Nhưng các test đó có thể vẫn xanh nếu:

- Spring không tạo được bean hoặc inject nhầm implementation.
- Controller ánh xạ sai trường JSON sang command.
- Repository query sai tên cột, sai quan hệ hoặc không tương thích dialect của database.
- JPA mapping làm mất giá trị khi lưu rồi đọc lại.
- Transaction không bao trùm các thao tác cần commit/rollback cùng nhau.
- Exception bị chuyển thành HTTP status hoặc response body không đúng hợp đồng.
- Adapter ngoài gửi sai payload, timeout hoặc lỗi được xử lý sai.
- Security filter, method security hoặc cấu hình serialization làm thay đổi kết quả thực tế.

Kiểm thử tích hợp tạo bằng chứng rằng những thành phần liên quan hoạt động cùng nhau qua một luồng cụ thể. Nó bổ sung cho unit test và kiểm thử adapter riêng, không thay thế chúng.

### Phân biệt các phạm vi kiểm thử

| Loại kiểm thử | Phạm vi thường gặp | Câu hỏi chính |
| --- | --- | --- |
| Unit test | Một class hoặc mô hình nhỏ, phụ thuộc được thay bằng fake/mock | Quy tắc hoặc thuật toán có đúng không? |
| Integration test của adapter | Repository với database, HTTP client với stub server, serializer với schema | Hai thành phần kỹ thuật có giao tiếp đúng không? |
| Kiểm thử tích hợp xuyên tầng | Nhiều tầng của một ca sử dụng, thường qua controller tới database | Các tầng có phối hợp đúng và giữ đúng hợp đồng không? |
| End-to-end test | Ứng dụng được chạy gần môi trường triển khai, có thể gồm nhiều tiến trình/dịch vụ | Hệ thống hoàn chỉnh có đáp ứng hành trình người dùng không? |

Ranh giới giữa các loại có thể thay đổi theo tổ chức. Một test `@SpringBootTest` với MockMvc và database thật thường được gọi là integration test; nó chưa nhất thiết là end-to-end nếu chưa chạy qua mạng, gateway hoặc các dịch vụ production-like.

## 2. Chọn ca sử dụng cần kiểm thử

Không phải mọi phương thức đều cần một bài kiểm thử xuyên tầng. Hãy ưu tiên ca sử dụng có tác động lớn nếu sai, nhiều ranh giới hoặc rủi ro tích hợp cao:

- Tạo đơn, thanh toán, hoàn tiền, hủy đơn hoặc xác nhận đặt chỗ.
- Cập nhật dữ liệu có nhiều bước cần cùng commit hoặc rollback.
- Luồng phụ thuộc vào quyền truy cập, trạng thái và dữ liệu của người dùng.
- Luồng đọc/ghi có truy vấn phức tạp, phân trang, khóa hoặc cạnh tranh đồng thời.
- Luồng gọi hệ thống ngoài, phát sự kiện hoặc cập nhật outbox.
- Luồng có hợp đồng API hoặc thông điệp được nhiều bên sử dụng.

Với mỗi ca sử dụng, mô tả rõ:

1. Đầu vào và điểm vào của luồng, chẳng hạn `POST /orders`.
2. Kết quả thành công mà người gọi quan sát được.
3. Bất biến nghiệp vụ cần giữ sau khi thực thi.
4. Những dữ liệu phải được ghi hoặc không được ghi khi thất bại.
5. Các adapter và dịch vụ ngoài tham gia.
6. Các lỗi quan trọng cần được chuyển thành kết quả có thể dự đoán.

Mô tả này trở thành cơ sở để thiết kế fixture, assertion và phạm vi tích hợp.

## 3. Chọn phạm vi tích hợp phù hợp

Một test xuyên tầng thường nên dùng các thành phần thật của ứng dụng ở những ranh giới mà nó muốn kiểm tra. Với luồng tạo đơn, phạm vi có thể gồm:

```text
HTTP request
    |
    v
OrderController
    |
    v
PlaceOrderService
    |
    +----> Order (domain rules)
    |
    +----> OrderRepository port
                 |
                 v
           JpaOrderRepository
                 |
                 v
             Database

PlaceOrderService ----> Payment adapter ----> Stub payment server
                    \
                     +--> Outbox repository --> Database
```

Đối với test tập trung vào mapping và transaction, có thể dùng:

- Spring application context thật để kiểm tra cấu hình bean và proxy.
- Controller thật thông qua MockMvc hoặc HTTP thật.
- Application service, domain model và repository thật.
- Cơ sở dữ liệu cùng loại hoặc tương thích chặt với môi trường chạy.
- Stub server cho hệ thống ngoài để kiểm soát response, timeout và lỗi.

Không nên mock `PlaceOrderService` hoặc `OrderRepository` trong một test được thiết kế để kiểm tra chính luồng controller → application → database. Mock ở những ranh giới bên ngoài hệ thống đang kiểm tra, chẳng hạn cổng thanh toán, hãng vận chuyển hoặc dịch vụ định danh từ xa. Nếu mục tiêu của test là kiểm tra một adapter riêng, phạm vi có thể hẹp hơn.

## 4. Dùng Spring Boot Test và database thật

`@SpringBootTest` khởi tạo application context theo cấu hình Spring Boot. `@AutoConfigureMockMvc` cung cấp MockMvc để gửi request qua Spring MVC mà không cần mở cổng HTTP. Với database, Testcontainers có thể khởi chạy một instance tạm thời của cùng hệ quản trị mà ứng dụng sử dụng.

Ví dụ cấu hình test với PostgreSQL:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class PlaceOrderIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
}
```

Đây là khung minh họa; cần thêm dependency test phù hợp với phiên bản Spring Boot, JUnit, Testcontainers và driver PostgreSQL của dự án. Nếu dùng Spring Boot phiên bản hỗ trợ `@ServiceConnection`, có thể cấu hình kết nối container theo cách đó thay cho `@DynamicPropertySource`.

Database thật giúp kiểm tra dialect, constraint, kiểu dữ liệu, locking, transaction và hành vi query gần production hơn. H2 có thể hữu ích cho một số test nhanh, nhưng không nên giả định H2 tương đương PostgreSQL hoặc MySQL về SQL, isolation, sequence, index, constraint và locking.

### Chuẩn bị schema và dữ liệu nền

Kiểm thử tích hợp nên dùng schema được tạo bằng cùng cơ chế migration mà ứng dụng triển khai, ví dụ Flyway hoặc Liquibase. Điều này phát hiện lỗi migration, sai tên cột và khác biệt giữa schema test với schema production.

Fixture nên nhỏ, tường minh và độc lập giữa các test. Có thể tạo sản phẩm, khách hàng và tồn kho bằng builder hoặc helper có tên rõ ràng; không nên phụ thuộc vào dữ liệu còn sót lại từ một test khác. Dùng ID xác định hoặc lưu ID trả về từ bước chuẩn bị để assertion không dựa trên thứ tự bản ghi.

## 5. Kiểm thử luồng thành công từ HTTP tới database

Một test đặt hàng thành công cần xác minh cả phản hồi bên ngoài lẫn trạng thái bền vững:

```java
@Test
void createsOrderAndPersistsItsItems() throws Exception {
    UUID productId = insertProduct("Keyboard", new BigDecimal("80.00"));
    UUID customerId = insertCustomer("buyer-" + UUID.randomUUID() + "@example.test");
    insertInventory(productId, 5);

    MvcResult result = mvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": "%s",
                  "items": [{"productId": "%s", "quantity": 2}]
                }
                """.formatted(customerId, productId)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.status").value("PLACED"))
        .andReturn();

    String orderIdValue = JsonPath.read(
        result.getResponse().getContentAsString(), "$.id");
    UUID orderId = UUID.fromString(orderIdValue);

    assertThat(jdbc.queryForObject(
        "select count(*) from orders where customer_id = ?",
        Integer.class, customerId)).isEqualTo(1);

    assertThat(jdbc.queryForObject(
        "select available from inventory where product_id = ?",
        Integer.class, productId)).isEqualTo(3);

    assertThat(jdbc.queryForObject(
        "select count(*) from order_items where order_id = ?",
        Integer.class, orderId)).isEqualTo(1);
}
```

Các helper `insertProduct`, `insertCustomer` và `insertInventory` đại diện cho bước chuẩn bị fixture; trong dự án thật có thể dùng repository test helper hoặc SQL script. Cấu trúc JSON, tên bảng và response là ví dụ, cần khớp với API thực tế.

Test này đi qua controller, application service, domain và persistence adapter. Assertion trên database chứng minh dữ liệu được ghi thực sự, thay vì chỉ kiểm tra một mock repository đã nhận lời gọi. Nếu use case còn tạo outbox record hoặc gọi adapter thanh toán, hãy xác minh các tác động đó ở đúng ranh giới.

### Assertion nên kiểm tra điều gì?

- HTTP status, content type và các trường response công khai.
- Định danh hoặc correlation cần thiết để truy vấn kết quả.
- Dữ liệu aggregate và các hàng liên quan được lưu đúng.
- Giá trị tiền, số lượng, trạng thái và timestamp giữ đúng ý nghĩa.
- Tồn kho hoặc số dư thay đổi theo bất biến.
- Event/outbox record được tạo đúng nếu ca sử dụng yêu cầu.
- Không có hàng hoặc tác dụng phụ thừa.

Đừng chỉ kiểm tra HTTP 201. Một response thành công nhưng thiếu order item hoặc không cập nhật tồn kho vẫn là lỗi tích hợp.

## 6. Kiểm thử lỗi và rollback xuyên tầng

Một ca sử dụng quan trọng cần xác nhận dữ liệu không ở trạng thái nửa chừng khi một bước thất bại. Ví dụ, nếu tạo đơn cần ghi order, order items và reservation trong cùng database transaction, lỗi khi ghi item phải rollback các thay đổi thuộc transaction đó.

Các trường hợp nên có:

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Request sai định dạng | HTTP 400; không tạo order hoặc thay đổi tồn kho |
| Sản phẩm không tồn tại | Lỗi nghiệp vụ được ánh xạ đúng; không có order dở dang |
| Số lượng không hợp lệ hoặc không đủ hàng | Không ghi đơn thành công; tồn kho không âm |
| Repository gặp lỗi constraint | Transaction rollback theo chính sách; response không báo thành công |
| Adapter ngoài từ chối thanh toán | Trạng thái order và reservation tuân theo quy trình đã thiết kế |
| Người gọi không đủ quyền | HTTP 401/403 phù hợp; không có thay đổi dữ liệu |

Ví dụ kiểm tra request không đủ hàng:

```java
@Test
void rejectsOrderWhenInventoryIsInsufficient() throws Exception {
    UUID productId = insertProduct("Keyboard", new BigDecimal("80.00"));
    UUID customerId = insertCustomer("buyer-" + UUID.randomUUID() + "@example.test");
    insertInventory(productId, 1);

    mvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content(orderRequest(customerId, productId, 2)))
        .andExpect(status().isConflict());

    assertThat(countOrdersFor(customerId)).isZero();
    assertThat(availableFor(productId)).isEqualTo(1);
}
```

HTTP 409 chỉ là lựa chọn minh họa; hợp đồng API có thể dùng status khác. Điều quan trọng là assertion phù hợp với chính sách đã định và dữ liệu không bị ghi sai.

### Lưu ý về transaction của test

Spring Test có thể mở transaction cho test và rollback sau khi test kết thúc. Điều này thuận tiện khi request được thực hiện đồng bộ trong cùng thread, ví dụ MockMvc thông thường, và các service tham gia transaction hiện tại. Nhưng không được mặc định mọi test HTTP đều nằm trong transaction test:

- Khi chạy server thật với `RANDOM_PORT`, request được xử lý ở thread khác và transaction của test không bao quanh transaction phía server.
- `REQUIRES_NEW`, tác vụ bất đồng bộ, message listener hoặc transaction độc lập có thể commit ngoài transaction của test.
- Các thao tác bulk SQL hoặc dữ liệu được ghi bởi tiến trình khác cũng không nhất thiết được rollback cùng test transaction.

Vì vậy, test dùng server thật hoặc async nên có chiến lược dọn dữ liệu rõ ràng: tạo schema/database riêng theo test suite, truncate bảng theo thứ tự phụ thuộc, dùng transaction cleanup phù hợp hoặc xóa fixture theo ID. Không để test xanh chỉ vì rollback một transaction khác với transaction thật của request.

## 7. Kiểm thử adapter bên ngoài mà vẫn giữ luồng xuyên tầng

Một ca sử dụng có thể gọi payment gateway, shipping provider hoặc identity service. Để test lặp lại được, thay endpoint bên ngoài bằng stub server có thể điều khiển. Ví dụ, WireMock có thể trả về kết quả thanh toán thành công, bị từ chối, timeout hoặc payload sai.

```java
stubFor(post(urlEqualTo("/payments/authorizations"))
    .willReturn(aResponse()
        .withStatus(201)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"authorizationId":"auth-test-123","status":"APPROVED"}
            """)));
```

Sau khi gửi request qua controller, kiểm tra stub đã nhận đúng payload và hệ thống đã lưu trạng thái phù hợp. Với lỗi timeout hoặc 5xx, xác minh retry có giới hạn, idempotency và trạng thái cuối cùng. Stub kiểm soát hợp đồng HTTP nhưng không chứng minh dịch vụ ngoài thật hoạt động; contract test hoặc kiểm thử trên sandbox của nhà cung cấp có thể bổ sung bằng chứng ở giai đoạn phù hợp.

Nếu use case dùng transactional outbox, test nên xác minh bản ghi outbox được ghi cùng transaction với order. Việc worker gửi message thành công là một luồng khác, có thể kiểm thử riêng bằng integration test của publisher/consumer. Không cần buộc test đặt hàng phải chờ email thật được gửi.

## 8. Kiểm thử bảo mật và hợp đồng giữa các tầng

Kiểm thử xuyên tầng cũng nên xác minh những ranh giới không chỉ liên quan database:

- Request DTO được validate trước khi application service chạy.
- Người chưa xác thực bị từ chối; người đã xác thực nhưng thiếu quyền bị từ chối theo chính sách.
- Người dùng không thể truy cập dữ liệu của người khác chỉ bằng cách thay ID trong URL.
- Domain exception được chuyển thành HTTP response nhất quán, không lộ stack trace hoặc chi tiết SQL.
- Response DTO không làm lộ persistence entity, trường nội bộ hoặc dữ liệu nhạy cảm.
- Mapping command/result và persistence giữ đúng đơn vị tiền, định danh, trạng thái và timezone.

Đối với test bảo mật, dùng cấu hình Spring Security thực tế của ứng dụng và thiết lập principal/authority qua test support phù hợp. Nếu tắt filter hoặc mock toàn bộ security chain trong test, test đó không thể chứng minh cấu hình bảo mật đang chạy thật hoạt động đúng.

## 9. Kiểm thử cạnh tranh và nhất quán dữ liệu

Nếu use case đọc, kiểm tra rồi cập nhật dữ liệu có thể bị gọi đồng thời, cần ít nhất một test với nhiều transaction/connection độc lập. Ví dụ, chỉ còn 3 đơn vị hàng nhưng nhiều request cùng đặt số lượng 1; tổng số request thành công không được vượt quá 3 và tồn kho cuối cùng không được âm.

Test cần điều khiển thời điểm để tái tạo cạnh tranh bằng barrier/latch hoặc gửi nhiều request đồng thời. Xác nhận cả dữ liệu cuối cùng và cách ứng dụng xử lý conflict: cập nhật có điều kiện, optimistic locking, pessimistic locking hoặc serialization failure. Không dựa vào một test tuần tự để kết luận luồng đồng thời an toàn.

Các test này nên chạy trên cùng loại database với production vì semantics của MVCC, lock, isolation và constraint có thể khác giữa các engine. Nếu test concurrency chậm hoặc dễ dao động, hãy giữ số lượng test nhỏ, đồng bộ bằng cơ chế rõ ràng và không dùng `Thread.sleep` như cách duy nhất để tạo thứ tự.

## 10. Giữ test nhanh, ổn định và dễ chẩn đoán

Kiểm thử tích hợp tốn tài nguyên hơn unit test. Một số nguyên tắc giúp kiểm soát chi phí:

- Chỉ khởi tạo các bean và dịch vụ ngoài cần cho ca sử dụng; không kéo cả hệ thống vào một test nếu không cần.
- Dùng một container database dùng chung cho test suite khi an toàn, nhưng cô lập dữ liệu giữa các test.
- Dùng fixture builder có tên nghiệp vụ, tránh SQL chuẩn bị dữ liệu lặp lại khó hiểu.
- Không phụ thuộc thứ tự chạy test, dữ liệu dùng chung hoặc thời gian thực.
- Dùng clock cố định, stub server và ID xác định khi cần kết quả lặp lại.
- Assertion lỗi nên chỉ ra tầng hoặc hợp đồng bị vi phạm, thay vì chỉ kiểm tra một thông báo tổng quát.
- Chạy các test quan trọng trong CI cùng migration và cấu hình tương thích với môi trường triển khai.

Khi test thất bại, ghi lại request, response, ID fixture và trạng thái database liên quan để có thể tái hiện. Tránh log token, thông tin cá nhân hoặc dữ liệu nhạy cảm trong output của test.

## 11. Checklist thiết kế một test xuyên tầng

Trước khi viết test cho một use case, hãy xác nhận:

1. Mục tiêu nghiệp vụ và bất biến cần giữ đã được mô tả rõ chưa?
2. Test bắt đầu ở ranh giới phù hợp — controller, message handler hay application service — chưa?
3. Những tầng và adapter nào cần dùng implementation thật để kiểm chứng?
4. Database có cùng engine/dialect và chạy migration như môi trường mục tiêu không?
5. Dữ liệu fixture có độc lập và được dọn đúng cách không?
6. Test có kiểm tra cả response lẫn trạng thái bền vững và tác dụng phụ quan trọng không?
7. Các đường lỗi có xác nhận rollback hoặc trạng thái bù trừ đúng không?
8. Dịch vụ ngoài có được stub ở ranh giới có kiểm soát không?
9. Test có thực sự đi qua security, transaction và proxy mà ứng dụng sử dụng không?
10. Với luồng đồng thời, test có dùng transaction/connection độc lập và xác nhận bất biến cuối cùng không?

Một bộ test xuyên tầng tốt không cần mô phỏng mọi tổ hợp có thể xảy ra. Nó cần bao phủ những đường đi quan trọng nhất, kiểm chứng các hợp đồng giữa tầng và bảo vệ những bất biến mà người dùng hoặc hệ thống phụ thuộc vào.

## Tự kiểm tra

1. Vì sao test đặt hàng xuyên tầng nên dùng repository và database thật thay vì mock `OrderRepository`?
2. Khi nào MockMvc đủ để kiểm tra luồng controller và khi nào cần chạy server thật?
3. Vì sao `@Transactional` trên test không đảm bảo rollback dữ liệu của request chạy trên server thread khác?
4. Nên stub payment gateway ở đâu và cần kiểm tra những gì sau request?
5. Làm thế nào để xác minh một lỗi ở bước cuối không để lại order hoặc reservation dở dang?
6. Vì sao test concurrency cần database engine gần production và nhiều transaction độc lập?

