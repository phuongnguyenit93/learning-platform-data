# Lập chiến lược kiểm thử theo ranh giới và rủi ro của từng tầng

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Chiến lược kiểm thử**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, trong đó presentation tiếp nhận giao tiếp bên ngoài, application điều phối ca sử dụng, business/domain bảo vệ quy tắc và data access/infrastructure làm việc với cơ sở dữ liệu hoặc hệ thống khác. Chiến lược kiểm thử cần phản ánh các ranh giới này: kiểm tra đúng trách nhiệm ở đúng nơi, chọn mức kiểm thử theo rủi ro và giữ được phản hồi đủ nhanh để nhóm phát hiện lỗi thường xuyên.

Không có một tỷ lệ unit test, integration test hay end-to-end test bắt buộc cho mọi dự án. Một hệ thống CRUD nhỏ và một hệ thống tài chính có nhiều quy tắc, tích hợp và giao dịch sẽ có hồ sơ rủi ro khác nhau. Mục tiêu là tạo bằng chứng đáng tin cậy rằng các hành vi quan trọng hoạt động đúng, các hợp đồng giữa tầng không bị phá vỡ và thay đổi ở một tầng không âm thầm làm hỏng tầng khác.

## 1. Bắt đầu từ rủi ro và hành vi cần bảo vệ

Kiểm thử có giá trị khi trả lời một câu hỏi cụ thể: điều gì có thể sai, hậu quả ra sao và kiểm thử nào phát hiện lỗi đó với chi phí hợp lý?

Trong hệ thống đặt hàng, một số rủi ro có thể là:

- API chấp nhận số lượng âm hoặc trả sai mã HTTP.
- Application service lưu đơn hàng nhưng quên giữ chỗ tồn kho.
- Domain cho phép chuyển đơn hàng từ trạng thái đã giao về trạng thái nháp.
- Mapper làm mất tiền tệ hoặc ánh xạ sai mã sản phẩm.
- Repository truy vấn sai dữ liệu hoặc tạo ra N+1 query.
- Hai yêu cầu đồng thời cùng đặt vượt quá số lượng tồn.
- Một thay đổi package làm tầng domain phụ thuộc trực tiếp vào Spring MVC hoặc JPA.
- Hệ thống phát thông báo thành công dù transaction đã rollback.

Mức ưu tiên kiểm thử phụ thuộc vào xác suất xảy ra và tác động của lỗi. Một lỗi hiển thị sai nhãn trên màn hình quản trị có thể có tác động thấp; một lỗi tính sai số tiền, bỏ qua quyền truy cập hoặc ghi nhận thanh toán hai lần có thể có tác động rất cao.

Có thể lập ma trận rủi ro đơn giản:

| Rủi ro | Hậu quả | Bằng chứng cần có |
|---|---|---|
| Quy tắc nghiệp vụ sai | Dữ liệu hoặc quyết định kinh doanh không hợp lệ | Unit test domain với trường hợp đúng, sai và biên |
| Điều phối thiếu bước | Ca sử dụng hoàn thành một phần hoặc gọi sai thứ tự | Unit test application và integration test transaction |
| Hợp đồng HTTP sai | Client không thể dùng API hoặc nhận dữ liệu sai | Web-layer/contract test |
| Ánh xạ dữ liệu sai | Mất trường, đổi nghĩa tiền hoặc trạng thái | Mapper test và persistence integration test |
| Truy vấn sai/chậm | Thiếu dữ liệu, N+1, hiệu năng kém | Repository test với database phù hợp và kiểm tra query |
| Cạnh tranh đồng thời | Mất cập nhật, đặt vượt tồn kho | Concurrency test và kiểm tra locking |
| Phụ thuộc kiến trúc bị đảo | Thay đổi kỹ thuật lan vào nghiệp vụ | Architecture test hoặc dependency rule |
| Tích hợp ngoài lỗi | Giao dịch không đồng bộ, tác động lặp | Contract test, outbox/consumer test và kiểm thử phục hồi |

Ma trận không phải tài liệu phải duy trì nặng nề cho mọi thay đổi. Với một tính năng nhỏ, vài dòng ghi nhận rủi ro trong pull request có thể đủ. Với luồng quan trọng, nên xác định rõ rủi ro, kiểm thử bảo vệ và cách quan sát khi chạy thật.

## 2. Ánh xạ trách nhiệm của tầng với loại kiểm thử

Một chiến lược phân tầng thường kết hợp nhiều loại kiểm thử. Mỗi loại có phạm vi và chi phí khác nhau.

| Phần được kiểm thử | Điều cần xác minh | Loại kiểm thử thường phù hợp |
|---|---|---|
| Presentation | HTTP contract, validation, status code, serialization | Web slice hoặc contract test |
| Application | Điều phối ca sử dụng, thứ tự bước, xử lý lỗi, transaction boundary | Unit test với collaborator giả; integration test cho hành vi hạ tầng |
| Business/domain | Quy tắc, bất biến, chuyển trạng thái và tính toán | Unit test thuần Java |
| Data access | SQL, mapping ORM, transaction, khóa và migration | Repository/persistence integration test |
| Adapter tích hợp | Request/response tới dịch vụ ngoài, message schema, lỗi mạng | Contract test, adapter test với stub hoặc môi trường thử nghiệm |
| Toàn hệ thống | Luồng quan trọng qua nhiều tầng | Một số end-to-end test chọn lọc |
| Cấu trúc kiến trúc | Hướng phụ thuộc và ranh giới package/module | Architecture test hoặc static analysis |

Không cần tạo một loại test riêng cho mỗi class. Hãy kiểm thử hành vi và hợp đồng có ý nghĩa. Ví dụ, một DTO chỉ chứa các trường đơn giản có thể được kiểm tra qua web test; không nhất thiết cần một bộ unit test cho từng getter.

## 3. Unit test cho business/domain

Unit test phù hợp với quy tắc có thể kiểm tra mà không cần Spring, database, filesystem hoặc mạng. Đây thường là mức kiểm thử nhanh và ổn định nhất cho domain model.

Ví dụ, đơn hàng chỉ được xác nhận khi đang ở trạng thái nháp và có ít nhất một dòng hợp lệ:

```java
class OrderTest {
    @Test
    void confirmsDraftOrder() {
        Order order = Order.draft(
                new CustomerId("C-100"),
                List.of(new OrderLine(new ProductId("P-10"), 2)));

        order.confirm();

        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @Test
    void rejectsConfirmationWhenOrderHasNoLines() {
        assertThrows(
                InvalidOrderException.class,
                () -> Order.draft(new CustomerId("C-100"), List.of()));
    }

    @Test
    void cannotConfirmAnAlreadyCancelledOrder() {
        Order order = Order.draft(
                new CustomerId("C-100"),
                List.of(new OrderLine(new ProductId("P-10"), 2)));
        order.cancel();

        assertThrows(InvalidOrderStateException.class, order::confirm);
    }
}
```

Ví dụ giả định domain cung cấp các factory và exception tương ứng. Điều quan trọng là test thể hiện quy tắc qua hành vi công khai của domain, không kiểm tra chi tiết private field hoặc số lần gọi getter.

Nên bao phủ:

- Trường hợp hợp lệ thường gặp.
- Trường hợp vi phạm từng bất biến quan trọng.
- Giá trị biên như số lượng bằng 0, giới hạn tối đa, tổng tiền bằng ngưỡng.
- Chuyển trạng thái hợp lệ và không hợp lệ.
- Quy tắc làm tròn, tiền tệ, ngày giờ và null nếu chúng thuộc nghiệp vụ.

Không cần test mọi tổ hợp đầu vào một cách máy móc. Chọn các trường hợp phân biệt được hành vi và có khả năng phát hiện lỗi. Với thuật toán tính toán nhiều nhánh, property-based test hoặc kiểm thử theo bảng dữ liệu có thể bổ sung giá trị.

## 4. Unit test cho application service

Application service điều phối các bước của ca sử dụng. Test ở mức này có thể dùng mock hoặc fake cho repository, gateway và publisher để tập trung vào luồng điều khiển.

Ví dụ, khi đặt hàng, application service phải tải sản phẩm, kiểm tra tồn kho, tạo đơn và lưu kết quả. Một unit test có thể xác minh khi tồn kho không đủ thì không lưu đơn:

```java
@ExtendWith(MockitoExtension.class)
class PlaceOrderServiceTest {
    @Mock InventoryRepository inventoryRepository;
    @Mock OrderRepository orderRepository;

    @InjectMocks PlaceOrderService service;

    @Test
    void doesNotSaveOrderWhenInventoryIsInsufficient() {
        when(inventoryRepository.findAvailable(
                new ProductId("P-10")))
                .thenReturn(Optional.of(new Inventory(1)));

        var command = new PlaceOrderCommand(
                new CustomerId("C-100"),
                new ProductId("P-10"),
                2);

        assertThrows(
                InsufficientInventoryException.class,
                () -> service.place(command));

        verify(orderRepository, never()).save(any());
    }
}
```

Test này kiểm tra quyết định điều phối ở tình huống tồn kho không đủ. Nó không chứng minh SQL, transaction hay locking hoạt động đúng; các nội dung đó cần integration test với hạ tầng thực.

Khi dùng mock, chỉ kiểm tra những tương tác có ý nghĩa đối với hợp đồng ca sử dụng. Nếu test xác minh từng lời gọi nội bộ, thứ tự getter hoặc mọi chi tiết triển khai, refactor nhỏ có thể làm test hỏng dù hành vi không đổi. Fake repository đơn giản có thể hữu ích khi cần kiểm thử luồng nghiệp vụ nhiều bước mà không muốn tạo quá nhiều cấu hình mock.

Application service thường cũng là nơi đặt transaction boundary. Unit test với mock không thể chứng minh nhiều repository cùng commit hoặc rollback. Cần có test tích hợp cho transaction, propagation và lỗi commit nếu đó là rủi ro quan trọng.

## 5. Web-layer test cho presentation

Presentation chịu trách nhiệm chuyển đổi giao thức HTTP thành lời gọi application và chuyển kết quả thành response. Web-layer test nên xác minh:

- Endpoint đúng method và path.
- Request JSON được deserialize đúng.
- Validation ở biên hoạt động.
- Status code, header và response body đúng hợp đồng.
- Lỗi nghiệp vụ được chuyển thành HTTP response phù hợp.
- Trường nội bộ không bị lộ ra response.

Với Spring Boot, `@WebMvcTest` có thể nạp một lát cắt MVC và mock application service. Ví dụ:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mvc;

    @MockitoBean PlaceOrderUseCase placeOrder;

    @Test
    void createsOrderAndReturnsCreatedResponse() throws Exception {
        when(placeOrder.handle(any()))
                .thenReturn(new PlaceOrderResult(
                        UUID.fromString("11111111-1111-1111-1111-111111111111"),
                        "CREATED"));

        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "C-100",
                      "lines": [{"productCode": "P-10", "quantity": 2}]
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").exists())
            .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
```

Ví dụ dùng `@MockitoBean` ở các phiên bản Spring Framework/Spring Boot hỗ trợ; dự án dùng phiên bản cũ có thể dùng annotation mock bean tương ứng. Test nên tập trung vào hợp đồng HTTP, không cần khởi động toàn bộ hệ thống nếu không có lý do.

Cũng cần kiểm tra request không hợp lệ, chẳng hạn thiếu customer ID hoặc quantity không dương. Validation annotation có thể phát hiện lỗi cấu trúc tại biên; các bất biến nghiệp vụ vẫn cần được bảo vệ trong domain/application vì ca sử dụng có thể được gọi từ nơi khác.

## 6. Integration test cho repository và data access

Repository test xác minh adapter thật sự làm việc với database như dự kiến. Mock Spring Data repository không kiểm tra được SQL, mapping JPA, ràng buộc, transaction hoặc hành vi của database.

Với Spring Data JPA, `@DataJpaTest` thường phù hợp để kiểm tra repository trong lát cắt persistence. Tuy nhiên, cần chọn database phù hợp với rủi ro. Database nhúng như H2 có thể nhanh, nhưng khác PostgreSQL/MySQL/SQL Server về kiểu dữ liệu, cú pháp SQL, locking, collation và transaction behavior. Nếu ứng dụng phụ thuộc vào đặc tính cụ thể của database sản xuất, nên chạy integration test với cùng loại database, thường qua Testcontainers hoặc môi trường CI tương đương.

Ví dụ:

```java
@DataJpaTest
class OrderRepositoryTest {
    @Autowired TestEntityManager entityManager;
    @Autowired SpringDataOrderRepository repository;

    @Test
    void findsOrdersByCustomer() {
        OrderJpaEntity order = OrderJpaEntity.create(
                UUID.randomUUID(), "C-100");
        entityManager.persistAndFlush(order);

        List<OrderJpaEntity> found =
                repository.findByCustomerCode("C-100");

        assertEquals(1, found.size());
        assertEquals("C-100", found.get(0).getCustomerCode());
    }
}
```

Tùy cấu hình dự án, `@DataJpaTest` thường chạy trong transaction test và rollback sau mỗi test. Điều này tiện cho cô lập dữ liệu, nhưng không tự chứng minh hành vi commit/rollback của application service bên ngoài. Với test transaction, cần chủ động kiểm soát transaction của test và đọc lại dữ liệu trong transaction mới khi xác minh trạng thái sau commit.

Nên kiểm tra:

- Điều kiện truy vấn và phân trang.
- Mapping entity, enum, tiền, ngày giờ và quan hệ.
- Unique constraint, foreign key và nullability.
- Lazy/eager loading và nguy cơ N+1.
- Optimistic/pessimistic locking nếu nghiệp vụ cần.
- Migration schema và khả năng đọc dữ liệu cũ.

## 7. Contract test giữa các tầng và hệ thống

Mỗi ranh giới đều có một hợp đồng. Hợp đồng có thể là kiểu Java, method signature, JSON schema, message payload, interface repository hoặc quy tắc lỗi. Test hợp đồng giúp phát hiện khi một phía thay đổi nhưng phía còn lại chưa cập nhật.

Ví dụ:

- Presentation và application thống nhất command/result, validation và ý nghĩa lỗi.
- Application và repository thống nhất cách truy vấn, lưu và xử lý không tìm thấy dữ liệu.
- Producer và consumer thống nhất schema message, version và semantics của event.
- Service gọi và service được gọi thống nhất HTTP status, timeout, authentication và error body.

Với API công khai hoặc tích hợp giữa nhiều nhóm, contract test có thể chạy độc lập với end-to-end test. Consumer-driven contract test là một lựa chọn khi consumer cần mô tả phần hợp đồng mà nó thực sự sử dụng. Tuy nhiên, không phải mọi ứng dụng nội bộ đều cần một framework contract testing riêng; test serialization, schema compatibility hoặc adapter test có thể đủ.

Đặc biệt, test hợp đồng nên bao gồm lỗi và trường hợp biên, không chỉ response thành công. Ví dụ HTTP 404, 409, 429, timeout, message phiên bản cũ và trường tùy chọn bị thiếu có thể ảnh hưởng đáng kể đến cách tầng gọi xử lý.

## 8. End-to-end test: ít nhưng bảo vệ luồng quan trọng

End-to-end (E2E) test chạy qua nhiều tầng với hạ tầng gần thực tế hơn, thường từ HTTP endpoint tới database và đôi khi cả dịch vụ phụ thuộc. Nó có thể phát hiện lỗi tích hợp mà unit hoặc slice test không thấy.

Ví dụ một luồng đặt hàng E2E có thể xác minh:

1. Client gửi request hợp lệ.
2. API trả về mã tạo thành công và mã đơn hàng.
3. Đơn hàng được lưu với các dòng đúng.
4. Tồn kho được cập nhật.
5. Một outbox record được tạo nếu quy trình dùng outbox.
6. Request gửi lại với cùng idempotency key không tạo đơn hàng thứ hai.

E2E test có chi phí cao hơn: khởi động nhiều thành phần, tạo dữ liệu, dọn trạng thái, dễ bị ảnh hưởng bởi môi trường và khó định vị lỗi. Vì vậy, chỉ nên giữ một số lượng chọn lọc cho các hành trình nghiệp vụ quan trọng hoặc rủi ro cao. Không nên dùng E2E để kiểm tra mọi tổ hợp logic có thể được kiểm tra nhanh hơn ở domain hoặc application.

Một E2E test thất bại có thể do API, database, cấu hình, dịch vụ ngoài hoặc dữ liệu test. Test cần log, correlation ID và thông tin chẩn đoán đủ để xác định nguyên nhân.

## 9. Kiểm thử ranh giới kiến trúc

Ngoài hành vi, kiến trúc phân tầng còn có các quy tắc về phụ thuộc. Ví dụ, domain không nên phụ thuộc controller hoặc entity JPA; presentation nên gọi application contract thay vì truy vấn database trực tiếp; adapter persistence triển khai abstraction phù hợp với hướng phụ thuộc đã chọn.

Có thể dùng architecture test hoặc static analysis để kiểm tra các quy tắc này. Một ví dụ với ArchUnit:

```java
@AnalyzeClasses(packages = "com.example.orders")
class LayerDependencyTest {
    @ArchTest
    static final ArchRule domainDoesNotDependOnWeb =
            noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat()
                .resideInAnyPackage("..controller..", "..web..");

    @ArchTest
    static final ArchRule domainDoesNotDependOnPersistence =
            noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat()
                .resideInAnyPackage("..persistence..", "jakarta.persistence..");
}
```

Tên package và cấu trúc ở đây chỉ là ví dụ. Dự án có thể dùng package, module hoặc quy tắc phụ thuộc khác. Không nên áp đặt một sơ đồ tầng cố định nếu kiến trúc thực tế có adapter hoặc module khác. Điều cần kiểm tra là các quy tắc phụ thuộc mà nhóm đã quyết định bảo vệ.

Architecture test có thể phát hiện một import vô tình kéo framework vào domain trước khi thay đổi lan rộng. Nó không chứng minh toàn bộ kiến trúc tốt; chỉ chứng minh các quy tắc đã viết trong test đang được tuân thủ.

## 10. Test pyramid là gợi ý về chi phí, không phải tỷ lệ bắt buộc

Một mô hình thường dùng là test pyramid:

```text
            /\
           /E2E\        Ít, chậm, kiểm tra luồng quan trọng
          /------\
         /Contract\     Một số, xác minh hợp đồng
        /Integration\   Chọn lọc, kiểm tra adapter và hạ tầng
       /--------------\
      /   Unit tests   \ Nhiều, nhanh, kiểm tra quy tắc và logic
     /__________________\
```

Ý nghĩa chính là kiểm tra càng rộng thường càng tốn thời gian và khó chẩn đoán, nên các quy tắc nhỏ nên được kiểm thử ở mức hẹp khi có thể. Tuy nhiên, không cần đạt một tỷ lệ cố định như 70/20/10. Một ứng dụng tích hợp nhiều giao thức hoặc phụ thuộc mạnh vào database có thể cần nhiều integration test hơn một thư viện tính toán thuần Java.

Một số dự án dùng test trophy hoặc mô hình khác để nhấn mạnh integration test. Hãy chọn cấu trúc phản ánh nơi rủi ro thực sự nằm. Điều quan trọng là không bỏ trống ranh giới quan trọng và không tạo nhiều test đắt tiền chỉ để tăng số lượng.

## 11. Dữ liệu kiểm thử và tính ổn định

Một test đáng tin cậy cần dữ liệu đầu vào rõ ràng và kết quả có thể dự đoán. Nên:

- Tạo dữ liệu tối thiểu cho từng kịch bản, tránh phụ thuộc vào thứ tự test.
- Dùng factory hoặc builder để tạo object hợp lệ với tên gọi diễn đạt ý nghĩa.
- Cô lập dữ liệu database theo test hoặc theo suite.
- Dùng clock giả hoặc truyền thời gian vào khi kiểm tra logic phụ thuộc ngày giờ.
- Dùng stub server hoặc fake cho dịch vụ ngoài thay vì gọi dịch vụ thật trong unit test.
- Không phụ thuộc vào dữ liệu ngẫu nhiên khó tái tạo; nếu cần random, cố định seed khi kiểm thử.
- Dọn tài nguyên và trạng thái sau test, đặc biệt với message broker, filesystem và cache.

Tránh dùng một fixture khổng lồ chung cho mọi test. Khi một trường không liên quan thay đổi, nhiều test có thể hỏng dây chuyền. Factory nên cung cấp giá trị mặc định hợp lệ và cho phép test chỉ rõ những trường liên quan tới hành vi đang kiểm tra.

Test không ổn định (flaky test) làm giảm niềm tin vào pipeline. Nguyên nhân thường gặp gồm sleep cố định để chờ bất đồng bộ, phụ thuộc thứ tự chạy, race condition trong test, đồng hồ thật, gọi mạng thật và chia sẻ dữ liệu. Hãy chờ theo điều kiện có timeout, cô lập trạng thái và làm rõ nguyên nhân thay vì retry test thất bại vô hạn.

## 12. Tổ chức kiểm thử trong CI

Một pipeline có thể chia kiểm thử theo thời gian và mục đích:

| Giai đoạn | Kiểm thử thường chạy | Mục tiêu |
|---|---|---|
| Khi phát triển/commit | Compile, unit test, static checks, architecture rules | Phản hồi nhanh |
| Pull request | Unit, web slice, repository integration, contract test quan trọng | Phát hiện lỗi trước khi hợp nhất |
| Build chính hoặc trước phát hành | Integration test rộng, migration, một số E2E | Xác minh tương tác gần thực tế |
| Môi trường staging | Smoke test, luồng nghiệp vụ quan trọng, kiểm tra cấu hình | Xác minh bản triển khai |
| Sau phát hành | Health check, synthetic check và quan sát vận hành | Phát hiện lỗi trong môi trường thật |

Không phải mọi nhóm cần đủ các giai đoạn trên. Có thể chạy tất cả test trên PR nếu thời gian hợp lý, hoặc chia suite khi tích hợp hạ tầng tốn thời gian. Cần có quy tắc rõ về test bắt buộc, test chậm và cách xử lý khi môi trường test gặp sự cố.

Coverage đo phần mã được thực thi trong test, nhưng không đo trực tiếp chất lượng của assertion hay mức độ bảo vệ rủi ro. Một test chạy qua mọi dòng mà không xác minh kết quả có thể tạo coverage cao nhưng giá trị thấp. Dùng coverage để tìm vùng logic chưa được kiểm tra, không biến nó thành mục tiêu duy nhất hoặc lý do để viết test hình thức.

Khi một bug được phát hiện, nên thêm test tái hiện lỗi ở mức phù hợp trước hoặc cùng lúc sửa lỗi. Test hồi quy giúp bảo đảm cùng lỗi không quay lại khi thay đổi tầng liên quan.

## 13. Chọn mức kiểm thử theo tình huống

Một số ví dụ giúp lựa chọn nhanh:

| Thay đổi | Kiểm thử ưu tiên | Bổ sung khi rủi ro cao |
|---|---|---|
| Sửa công thức chiết khấu | Domain unit test với giá trị biên | Property-based test, regression test |
| Thêm field vào REST response | Web-layer/contract test và mapper test nếu có logic | E2E cho luồng client quan trọng |
| Sửa truy vấn repository | Repository integration test | Kiểm tra query count, execution plan ở môi trường phù hợp |
| Thay đổi transaction nhiều repository | Application test và integration test rollback | Concurrency test, failure injection |
| Đổi schema hoặc migration | Migration test và repository integration test | Test nâng cấp từ dữ liệu phiên bản trước |
| Thêm message consumer | Unit test xử lý message và contract test | Integration test broker, redelivery/idempotency |
| Chuyển package hoặc module | Architecture test, compile và test liên quan | Kiểm tra module boundary toàn bộ |
| Thêm retry/timeout | Unit test policy và adapter test | Integration test timeout, idempotency, load behavior |

Chọn test hẹp nhất có thể phát hiện lỗi một cách đáng tin cậy. Nếu rủi ro nằm ở tương tác giữa hai tầng, cần test qua ranh giới đó. Nếu rủi ro nằm trong một quy tắc thuần, không cần khởi động cả ứng dụng để kiểm tra.

## 14. Checklist lập chiến lược kiểm thử

Trước khi hoàn thành một tính năng, hãy tự hỏi:

1. Quy tắc nghiệp vụ nào có hậu quả lớn nếu sai? Đã có unit test cho trường hợp đúng, sai và biên chưa?
2. Application service có nhiều bước hoặc nhiều repository không? Đã kiểm tra điều phối và transaction bằng mức test phù hợp chưa?
3. Hợp đồng HTTP/message có thay đổi không? Đã kiểm tra serialization, validation, status code và lỗi chưa?
4. Mapper có thể làm mất hoặc đổi nghĩa dữ liệu không? Đã kiểm tra null, enum, tiền, thời gian và collection cần thiết chưa?
5. Repository có truy vấn, locking hoặc migration đặc thù không? Đã kiểm tra với database phù hợp chưa?
6. Có ranh giới kiến trúc cần bảo vệ bằng dependency rule không?
7. Luồng đầu cuối nào quan trọng nhất với người dùng hoặc nghiệp vụ? Có E2E test chọn lọc không?
8. Test có độc lập, ổn định, có thể chạy lại và chẩn đoán được khi thất bại không?
9. CI có chạy các test quan trọng đủ sớm để phản hồi trước khi phát hành không?
10. Khi bug được sửa, có test hồi quy để giữ lại hành vi mong muốn không?

## 15. Ghi nhớ

- Lập chiến lược kiểm thử từ rủi ro và hành vi cần bảo vệ, không bắt đầu bằng một tỷ lệ test cố định.
- Domain unit test phù hợp với quy tắc và bất biến; application test kiểm tra điều phối; web test kiểm tra hợp đồng HTTP.
- Repository integration test cần database phù hợp với đặc tính mà ứng dụng phụ thuộc; mock không chứng minh SQL, transaction hay locking đúng.
- Contract test bảo vệ giao tiếp giữa các tầng và dịch vụ; E2E test nên chọn lọc cho hành trình quan trọng.
- Architecture test có thể giữ hướng phụ thuộc và ranh giới module không bị phá vỡ.
- Test pyramid là gợi ý về chi phí và phạm vi, không phải công thức số lượng bắt buộc.
- Dữ liệu test cần độc lập, dễ hiểu và tái tạo; tránh phụ thuộc thứ tự, sleep cố định và dịch vụ mạng thật trong unit test.
- Coverage chỉ là tín hiệu; chất lượng assertion và khả năng phát hiện lỗi mới quyết định giá trị của test.
- Chạy kiểm thử theo nhiều giai đoạn CI và bổ sung regression test khi sửa lỗi.

