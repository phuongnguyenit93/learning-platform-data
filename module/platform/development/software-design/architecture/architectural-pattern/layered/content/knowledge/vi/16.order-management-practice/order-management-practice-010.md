# Kiểm thử luồng tích hợp, hợp đồng và tự động phát hiện phụ thuộc sai

Một ứng dụng phân tầng có thể vượt qua unit test nhưng vẫn lỗi khi các tầng được nối với nhau: controller ánh xạ sai request, Spring inject nhầm adapter, repository truy vấn sai, transaction không bao trọn các cập nhật hoặc response không còn tương thích với client. Vì vậy, cần kiểm thử ở nhiều ranh giới bổ sung cho nhau: **kiểm thử luồng tích hợp** xác minh các thành phần phối hợp khi chạy; **kiểm thử hợp đồng** xác minh các bên giao tiếp hiểu cùng một định dạng và ngữ nghĩa; **kiểm thử kiến trúc** tự động phát hiện những phụ thuộc mã nguồn đi ngược quy tắc thiết kế.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này dùng một hệ thống quản lý đơn hàng làm ví dụ. Mục tiêu là kiểm tra được luồng từ adapter đầu vào qua ca sử dụng, domain và adapter lưu trữ; bảo vệ hợp đồng HTTP/message; đồng thời đưa quy tắc phụ thuộc giữa presentation, application, domain và infrastructure vào CI để vi phạm được phát hiện ngay khi có thay đổi.

## 1. Ba loại kiểm thử trả lời ba câu hỏi khác nhau

Các loại kiểm thử này có thể cùng dùng một test framework, nhưng chúng xác minh những thuộc tính khác nhau:

| Loại kiểm thử | Câu hỏi chính | Phạm vi thường gặp | Lỗi có thể phát hiện |
|---|---|---|---|
| Luồng tích hợp (integration flow) | Các thành phần thật có phối hợp đúng trong một ca sử dụng không? | Spring context, controller hoặc message adapter, application service, domain, repository và storage. | Wiring sai, mapping sai, transaction không đúng, truy vấn hoặc cập nhật dữ liệu sai. |
| Hợp đồng (contract) | Hai bên giao tiếp có thống nhất schema, mã lỗi và ý nghĩa dữ liệu không? | REST API, message event, HTTP client hoặc tích hợp giữa service. | Đổi field không tương thích, sai kiểu, thiếu header, sai status hoặc thay đổi ngữ nghĩa event. |
| Kiến trúc (architecture/dependency) | Mã nguồn có tuân thủ hướng phụ thuộc đã chọn không? | Package, class, module và quy tắc build. | Domain import Spring/JPA, application phụ thuộc adapter cụ thể, chu trình package/module. |

Một unit test cho Order có thể chứng minh đơn không được xác nhận khi không có dòng hàng. Nó không chứng minh request HTTP được chuyển đúng thành command hoặc JPA adapter lưu đúng trạng thái. Một integration test có thể chứng minh luồng chạy, nhưng không tự động phát hiện mọi thay đổi phá vỡ client bên ngoài. Một contract test có thể bảo vệ API, nhưng không chứng minh domain không phụ thuộc vào infrastructure. Vì vậy, hãy chọn test theo rủi ro cần kiểm soát.

Có thể hình dung các lớp bảo vệ như sau:

~~~mermaid
flowchart TB
    Client["Client / hệ thống tích hợp"]
    Contract["Contract tests<br/>HTTP, event schema"]
    Flow["Integration flow tests<br/>Spring + database"]
    Architecture["Architecture tests<br/>package/module dependencies"]
    Code["Presentation → Application → Domain → Infrastructure"]
    Storage[("Database / message broker")]

    Client --> Contract
    Contract --> Code
    Flow --> Code
    Code --> Storage
    Architecture -.kiểm tra cấu trúc.-> Code
~~~

Sơ đồ thể hiện các test quan sát những khía cạnh khác nhau của cùng hệ thống. Không nhất thiết mọi test đều phải khởi động toàn bộ ứng dụng hoặc chạy qua mạng thật.

## 2. Xác định luồng tích hợp cần bảo vệ

Với ca sử dụng tạo đơn hàng, một luồng điển hình là:

1. REST controller nhận request và kiểm tra cấu trúc.
2. Controller chuyển request thành command và gọi PlaceOrderUseCase.
3. Dịch vụ ứng dụng tải sản phẩm, phối hợp domain tạo đơn và yêu cầu lưu dữ liệu.
4. Domain bảo vệ bất biến như số lượng dương và đơn phải có ít nhất một dòng hàng.
5. Repository adapter ánh xạ mô hình nghiệp vụ sang JPA entity và lưu vào database.
6. Ứng dụng trả kết quả; controller chuyển kết quả thành HTTP response.

Khi kiểm thử luồng này, hãy xác định ranh giới thật và ranh giới giả lập. Một integration test có thể dùng Spring context, controller, service, domain, repository và PostgreSQL thật, trong khi thay cổng thanh toán hoặc dịch vụ email bằng test double. Cách này tập trung vào luồng đơn hàng và tránh phụ thuộc vào dịch vụ ngoài không liên quan đến mục tiêu test.

Đừng gọi một test dùng controller giả, repository mock và database không được truy cập là integration test của toàn luồng. Nó có thể là unit test hoặc slice test hữu ích, nhưng phạm vi cần được ghi đúng để người đọc hiểu điều gì đã được xác minh.

## 3. Kiểm thử luồng Spring qua HTTP và database thật

Với ứng dụng Spring Boot, có thể dùng @SpringBootTest cùng @AutoConfigureMockMvc để khởi động application context và gửi request qua Spring MVC. Testcontainers cung cấp database engine gần production để kiểm tra repository và transaction.

Ví dụ dưới đây giả định Spring Boot 3.1 trở lên, PostgreSQL là storage của ứng dụng và dự án đã khai báo dependency Spring Boot Test, Spring Boot Testcontainers, Testcontainers JUnit/PostgreSQL:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class PlaceOrderFlowIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    MockMvc mockMvc;

    @Autowired
    InventoryJpaRepository inventory;

    @Autowired
    OrderJpaRepository orders;

    @Test
    void createsOrderAndReservesInventory() throws Exception {
        UUID customerId = UUID.randomUUID();
        UUID productId = UUID.randomUUID();

        inventory.saveAndFlush(
            InventoryJpaEntity.available(productId, 8));

        String request = """
            {
              "customerId": "%s",
              "items": [
                {
                  "productId": "%s",
                  "quantity": 3
                }
              ]
            }
            """.formatted(customerId, productId);

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(request))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("CONFIRMED"));

        OrderJpaEntity saved = orders
            .findFirstByCustomerId(customerId)
            .orElseThrow();

        assertEquals(OrderStatus.CONFIRMED, saved.getStatus());
        assertEquals(
            5,
            inventory.findById(productId)
                .orElseThrow()
                .getAvailableQuantity()
        );
    }
}
~~~

Ví dụ minh họa đường đi từ HTTP adapter đến database. Các lớp entity, repository, endpoint và trạng thái là thành phần của ứng dụng mẫu; tên phương thức cần điều chỉnh theo dự án thực tế. Test không gắn @Transactional ở cấp phương thức để request được xử lý và commit qua transaction của ca sử dụng. Sau khi MockMvc nhận response, truy vấn repository đọc lại trạng thái đã lưu trong một persistence context mới của thao tác repository.

Các điểm cần kiểm tra:

- Dữ liệu ban đầu được ghi và commit trước khi gọi endpoint.
- Request thực sự đi qua Spring MVC binding và validation.
- Bean của use case và repository được Spring wiring như cấu hình chạy thật.
- Database test là engine cần hỗ trợ, không tự động bị thay bằng H2.
- Test đọc lại dữ liệu đã lưu, không chỉ kiểm tra response.
- Dữ liệu test có ID riêng để không phụ thuộc thứ tự chạy.

Nếu chỉ muốn kiểm tra controller mapping mà không cần database, dùng @WebMvcTest và mock use case. Nếu muốn kiểm tra repository, mapping và SQL, dùng @DataJpaTest. Dùng full application context khi mục tiêu là kiểm tra các tầng phối hợp qua cấu hình Spring.

## 4. Kiểm tra tính nguyên tử và nhất quán của ca sử dụng

Một integration flow test nên kiểm tra không chỉ kết quả thành công mà cả trường hợp thất bại giữa chừng. Giả sử đặt hàng gồm hai thay đổi trong cùng PostgreSQL database: giữ tồn kho và lưu đơn. Nếu lưu đơn thất bại sau khi tồn kho đã được giữ, hai thay đổi phải rollback cùng nhau khi nghiệp vụ yêu cầu chúng là một đơn vị nguyên tử.

Tầng ứng dụng thường đặt ranh giới transaction trên phương thức ca sử dụng:

~~~java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    PlaceOrderService(
            InventoryRepository inventory,
            OrderRepository orders) {
        this.inventory = inventory;
        this.orders = orders;
    }

    @Override
    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        Order order = Order.place(command.customerId(), command.items());
        inventory.reserve(command.items());
        orders.save(order);
        return order.id();
    }
}
~~~

Transaction cục bộ có thể bảo đảm tính nguyên tử khi các repository tham gia cùng transaction manager và cùng resource manager phù hợp, ví dụ cùng một PostgreSQL datasource. Nếu một thao tác ghi ném RuntimeException làm transaction rollback theo chính sách mặc định của Spring, các thay đổi đã thực hiện trong transaction đó sẽ rollback cùng nhau. Checked exception không tự động kích hoạt rollback theo mặc định; nếu ca sử dụng cần rollback với loại checked exception cụ thể, phải cấu hình rollbackFor phù hợp. Nếu ứng dụng bắt lỗi rồi trả kết quả bình thường, transaction có thể commit trừ khi được đánh dấu rollback-only.

Có thể kiểm tra rollback bằng một test tích hợp có chủ đích làm bước ghi đơn thất bại sau khi đã giữ tồn kho. Ví dụ, test dùng một adapter kiểm thử được cấu hình để ném lỗi ở bước lưu đơn, trong khi thao tác giữ tồn kho vẫn chạy trên database thật. Sau khi lời gọi ca sử dụng kết thúc bằng lỗi, test đọc lại bằng transaction mới và xác minh tồn kho trở về giá trị ban đầu, đồng thời không có đơn được lưu. Điều quan trọng là lời gọi phải đi qua Spring transaction proxy và test không bọc toàn bộ kịch bản trong transaction ngoài làm che khuất thời điểm commit/rollback.

Nếu đơn hàng và tồn kho nằm ở hai database/service khác nhau, một transaction Spring cục bộ không thể tự rollback cả hai hệ thống. Khi đó cần workflow nhiều bước như saga, trạng thái chờ, retry và hành động bù phù hợp. Nếu cần phát sự kiện sau khi lưu đơn, transactional outbox ghi trạng thái đơn và bản ghi outbox trong cùng database transaction; worker phát message sau commit. Consumer cần idempotency vì việc gửi message có thể lặp. Test phải xác minh từng transaction cục bộ và khả năng phục hồi, không giả định có một transaction ACID xuyên suốt mạng.

### Ma trận kịch bản luồng tích hợp

| Kịch bản | Trạng thái mong đợi | Điều cần xác minh |
|---|---|---|
| Đặt hàng thành công | Đơn được lưu, tồn kho được giữ/trừ đúng | HTTP response, domain state và dữ liệu DB nhất quán. |
| Số lượng không hợp lệ | Request bị từ chối trước khi tạo đơn | Lỗi validation đúng; không có ghi dữ liệu. |
| Sản phẩm không tồn tại | Ca sử dụng không tạo đơn | Mã lỗi nghiệp vụ/tài nguyên phù hợp; không thay đổi tồn kho. |
| Không đủ tồn kho | Không xác nhận đơn | Kiểm tra tồn kho có tính nguyên tử hoặc khóa phù hợp. |
| Lưu đơn thất bại sau khi giữ hàng | Không có cập nhật một phần | Transaction rollback cả thao tác giữ hàng và lưu đơn nếu cùng resource manager. |
| Database không khả dụng | Ca sử dụng không báo thành công giả | Lỗi hạ tầng được chuyển đúng; không để trạng thái thành công không có dữ liệu. |
| Message phát sau commit bị lỗi | Đơn và ý định phát sự kiện vẫn được lưu | Outbox còn pending và worker có thể gửi lại an toàn. |

## 5. Kiểm thử hợp đồng REST API

Hợp đồng API xác định những gì client có thể gửi và những gì server cam kết trả về. Hợp đồng nên mô tả ít nhất:

- HTTP method, path và query/path parameter.
- Header cần thiết như Content-Type, Authorization, If-Match hoặc idempotency key nếu có.
- Schema request và response, trường bắt buộc, kiểu, giới hạn và enum.
- HTTP status cho thành công, validation, conflict, business rejection và lỗi server.
- Ngữ nghĩa của field, đơn vị tiền tệ, timezone, phân trang và quy tắc tương thích phiên bản.

Ví dụ, API tạo đơn có thể công bố:

| Trường hợp | Request/điều kiện | Kết quả hợp đồng |
|---|---|---|
| Thành công | Request hợp lệ, đủ điều kiện đặt hàng | 201 Created; response có orderId và status. |
| Sai cú pháp/validation | JSON hỏng, thiếu items hoặc quantity không hợp lệ | 400 Bad Request; mã lỗi và fieldErrors ổn định. |
| Không có quyền | Người gọi không được phép tạo đơn cho khách hàng đó | 403 Forbidden theo chính sách bảo mật. |
| Xung đột trạng thái | Idempotency/version hoặc trạng thái hiện tại xung đột | 409 Conflict nếu phù hợp với ngữ nghĩa API. |
| Từ chối nghiệp vụ | Không đáp ứng chính sách đặt hàng | Mã status đã được API tài liệu hóa, ví dụ 422 Unprocessable Content. |
| Lỗi phụ thuộc | Database hoặc upstream không sẵn sàng | 5xx phù hợp; không lộ stack trace hoặc chi tiết nội bộ. |

Một test controller có thể xác minh response theo hợp đồng:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerContractTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    PlaceOrderUseCase placeOrder;

    @Test
    void returnsDocumentedCreateOrderResponse() throws Exception {
        given(placeOrder.handle(any()))
            .willReturn(new PlaceOrderResult(
                UUID.fromString("4b6c2c60-0d91-4e0b-9e14-71b9e2c1d210"),
                OrderStatus.CONFIRMED
            ));

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "f8e7d3b0-3f9b-4a25-a7e7-2f2c5e9d8c10",
                      "items": [
                        {
                          "productId": "1b2e8f4d-7a3c-4b5d-9e6f-0a1b2c3d4e5f",
                          "quantity": 2
                        }
                      ]
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderId").exists())
            .andExpect(jsonPath("$.status").value("CONFIRMED"));
    }
}
~~~

Ví dụ dùng @MockitoBean trong các phiên bản Spring Framework mới; với phiên bản cũ hơn, dự án có thể đang dùng @MockBean. Test này kiểm tra controller và hợp đồng response, không kiểm tra database hoặc logic đặt hàng thật vì use case đã được thay bằng mock. Đó là chủ ý: contract test của adapter nên nhanh và chỉ xác minh chuyển đổi HTTP. Luồng end-to-end hơn được kiểm tra riêng bằng integration flow test.

Với API được nhiều client sử dụng, nên quản lý hợp đồng bằng OpenAPI và kiểm tra response/request thực tế so với schema. Khi một service cung cấp API cho service khác, consumer-driven contract testing bằng Pact hoặc Spring Cloud Contract có thể xác minh provider vẫn đáp ứng những tương tác mà consumer đang sử dụng. Test provider cần chạy với implementation thật của endpoint; test consumer ghi nhận yêu cầu mà client thực sự gửi. Hợp đồng được kiểm tra trong CI trước khi phát hành để phát hiện thay đổi không tương thích.

## 6. Kiểm thử hợp đồng message và sự kiện

Trong hệ thống đơn hàng, một sự kiện OrderPlaced có thể được gửi tới dịch vụ giao hàng, phân tích hoặc thông báo. Schema sự kiện là hợp đồng giữa producer và consumer. Cần kiểm tra:

- Tên event và version/schema được công bố.
- Field bắt buộc, kiểu dữ liệu, định dạng ID và thời gian.
- Ngữ nghĩa field: amount là tổng trước hay sau thuế, currency dùng mã nào, occurredAt là thời điểm UTC hay offset.
- Quy tắc thêm field tùy chọn và loại bỏ field cũ.
- Consumer xử lý event lặp hoặc đến sai thứ tự như thế nào.
- Consumer xử lý event phiên bản cũ trong giai đoạn triển khai cuốn chiếu ra sao.

Ví dụ payload:

~~~json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "eventId": "e52d54c0-3b7e-4c56-8a9b-12b4d2d3f456",
  "orderId": "4b6c2c60-0d91-4e0b-9e14-71b9e2c1d210",
  "occurredAt": "2026-11-25T09:30:00Z"
}
~~~

Producer test nên xác minh event được tạo với schema và ý nghĩa đúng. Consumer contract test nên cung cấp payload mẫu theo version được hỗ trợ và xác minh consumer đọc được, thực hiện đúng hành vi. Nếu schema dùng Avro, Protobuf hoặc JSON Schema, có thể dùng registry/tooling tương ứng để kiểm tra compatibility theo chính sách của tổ chức.

Không nên thay đổi tên hoặc ý nghĩa field hiện có mà không có kế hoạch versioning. Thêm một field bắt buộc có thể làm consumer cũ lỗi; đổi đơn vị tiền hoặc timezone có thể phá hợp đồng dù schema vẫn hợp lệ. Với message broker, delivery thường có thể là at-least-once; consumer nên idempotent dựa trên eventId hoặc business key phù hợp. Việc broker xác nhận message không chứng minh side effect của consumer đã commit nếu consumer xử lý database và offset ở các resource manager khác nhau.

## 7. Tự động phát hiện phụ thuộc sai bằng ArchUnit

Sơ đồ kiến trúc chỉ có giá trị nếu mã nguồn tuân thủ. ArchUnit cho phép viết test kiểm tra phụ thuộc package và lớp Java. Ví dụ, domain không được phụ thuộc presentation hoặc infrastructure; application không được import adapter hạ tầng cụ thể:

~~~java
@AnalyzeClasses(packages = "com.example.orders")
class LayerArchitectureTest {

    @ArchTest
    static final ArchRule domainDoesNotDependOnOuterLayers =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..presentation..",
                "..infrastructure.."
            );

    @ArchTest
    static final ArchRule applicationDoesNotDependOnInfrastructure =
        noClasses()
            .that().resideInAPackage("..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule packagesAreFreeOfCycles =
        slices()
            .matching("com.example.orders.(*)..")
            .should().beFreeOfCycles();
}
~~~

Đoạn mã giả định các package thực tế tuân theo cấu trúc đã nêu và test source có dependency ArchUnit JUnit 5. Các static import thường dùng gồm ArchRuleDefinition.noClasses, ArchRuleDefinition.slices, ArchUnit runner annotations AnalyzeClasses và ArchTest. Điều chỉnh package pattern theo cấu trúc dự án; nếu pattern quá rộng hoặc không khớp, rule có thể bỏ sót lớp hoặc kiểm tra nhầm package.

Có thể thêm rule về tầng trình bày chỉ phụ thuộc application, hoặc application/domain không import các kiểu Spring Web, Spring Data và Hibernate. Tuy nhiên, hãy chọn quy tắc theo kiến trúc mà nhóm thực sự cam kết. Một ứng dụng CRUD nhỏ có thể cho phép một đường truy vấn đơn giản đi thẳng tới read repository; nếu đó là ngoại lệ có chủ đích, hãy giới hạn và ghi rõ thay vì tạo một rule quá rộng khiến nhóm phải vô hiệu hóa cả bộ kiểm thử.

ArchUnit kiểm tra tham chiếu tĩnh trong bytecode ở phạm vi nó hỗ trợ. Nó không tự phát hiện đầy đủ dependency qua reflection, bean được chọn theo profile, SQL động, cấu hình mạng hoặc lời gọi HTTP runtime. Cần bổ sung test cấu hình, integration test, contract test và quan sát runtime cho các loại phụ thuộc đó.

## 8. Kiểm tra ranh giới module trong build

Khi ứng dụng dùng nhiều Gradle/Maven module, hãy bảo vệ dependency graph ở cấp build. Ví dụ một cấu trúc có thể là:

~~~text
orders
├── orders-domain
├── orders-application
├── orders-infrastructure
└── orders-bootstrap
~~~

Một quy ước có thể là:

- orders-domain không phụ thuộc Spring Boot, JPA hoặc module infrastructure.
- orders-application phụ thuộc orders-domain và định nghĩa use case/port.
- orders-infrastructure phụ thuộc application/domain để triển khai port.
- orders-bootstrap kết nối các module và cung cấp cấu hình khởi động.
- Adapter presentation có thể nằm trong bootstrap hoặc một module riêng, tùy cách đóng gói.

Build script cần khai báo dependency theo hướng đó. Nếu application khai báo implementation project(":orders-infrastructure"), build graph đã cho thấy một phụ thuộc ngược cần xem xét. Có thể kiểm tra dependency tree trong review và dùng convention plugin hoặc rule build để giới hạn dependency được phép. Việc tách Gradle module không đồng nghĩa phải deploy từng module thành service riêng; nhiều module vẫn có thể đóng gói trong một ứng dụng.

## 9. Đưa các kiểm thử vào pipeline CI

Một pipeline hợp lý thường chạy test nhanh trước, rồi tới test cần môi trường tích hợp:

~~~mermaid
flowchart TD
    Commit["Commit / Pull request"] --> Compile["Compile và static checks"]
    Compile --> Unit["Unit tests"]
    Unit --> Arch["Architecture dependency tests"]
    Arch --> Contract["API / message contract tests"]
    Contract --> Integration["Integration flow tests + real storage"]
    Integration --> Report["Test report và coverage"]
    Report --> Ready["Đủ điều kiện review/release"]
~~~

Thứ tự có thể thay đổi tùy thời gian chạy và cách quản lý môi trường. Architecture test thường nhanh nên có thể chạy cùng unit test. Contract test có thể chạy với provider/consumer riêng. Integration test dùng Testcontainers cần runner hỗ trợ Docker hoặc một database test được quản lý.

Không nên chỉ dựa vào tổng tỷ lệ coverage. Một test có thể chạy qua nhiều dòng code nhưng không kiểm tra đúng hợp đồng hoặc không xác minh trạng thái database sau commit. Hãy theo dõi test nào bảo vệ từng ranh giới và kịch bản lỗi quan trọng.

### Ma trận kiểm thử cho hệ thống quản lý đơn hàng

| Rủi ro | Kiểm thử phù hợp | Bằng chứng cần có |
|---|---|---|
| Controller chuyển request sai | MVC/contract test | Command được tạo đúng; response đúng schema/status. |
| Ca sử dụng không phối hợp đúng | Application unit test và integration flow | Các bước nghiệp vụ và repository được gọi đúng; trạng thái cuối đúng. |
| ORM mapping hoặc query sai | Repository integration test | Dữ liệu được flush, clear và đọc lại từ database thật. |
| Transaction tạo cập nhật một phần | Integration test có fault injection | Tất cả thay đổi trong cùng transaction rollback cùng nhau. |
| Client bị phá bởi API change | OpenAPI/Pact/Spring Cloud Contract | Provider đáp ứng hợp đồng consumer đang sử dụng. |
| Consumer không đọc được event mới | Message schema/consumer contract test | Payload phiên bản được hỗ trợ được parse và xử lý đúng. |
| Domain import framework hoặc adapter | ArchUnit test | Rule phụ thuộc pass trong CI. |
| Gradle module phụ thuộc sai chiều | Build dependency rule/review | Module graph tuân thủ hướng đã thống nhất. |
| Gọi dịch vụ ngoài timeout hoặc retry sai | Adapter integration/contract test | Timeout, retry, idempotency và lỗi được xử lý đúng. |

## 10. Những lỗi thường gặp khi thiết kế bộ kiểm thử

- **Dùng mock cho mọi thứ:** test chạy nhanh nhưng không xác minh wiring, database, transaction hoặc schema thật.
- **Gọi test controller là end-to-end:** nếu use case và repository đều mock, test chỉ xác minh adapter HTTP.
- **Chỉ kiểm tra HTTP status:** response có thể trả 201 nhưng database chưa có đơn hoặc tồn kho bị cập nhật sai.
- **Bọc test trong transaction ngoài mà không để ý:** có thể che khuất hành vi commit của transaction ca sử dụng.
- **Giả định mọi ngoại lệ đều rollback:** Spring mặc định rollback với RuntimeException và Error; checked exception cần cấu hình nếu phải rollback.
- **Giả định một transaction bao trùm broker hoặc service ngoài:** transaction cục bộ không tạo atomicity xuyên nhiều resource manager độc lập.
- **Không version hóa contract:** thay field hoặc ngữ nghĩa event có thể phá consumer đang triển khai.
- **Rule kiến trúc quá nghiêm hoặc không chính xác:** nhóm dễ bỏ qua hoặc vô hiệu hóa rule nếu nó không phản ánh kiến trúc thực tế.
- **Chỉ kiểm tra dependency tĩnh:** runtime wiring và network dependency vẫn có thể sai dù ArchUnit pass.
- **Không cô lập dữ liệu test:** test phụ thuộc thứ tự hoặc làm hỏng dữ liệu của nhau.

## 11. Quy trình áp dụng cho một thay đổi trong hệ thống đơn hàng

Khi thêm hoặc sửa một ca sử dụng, hãy thực hiện:

1. Xác định luồng từ adapter đầu vào đến database hoặc message adapter; đánh dấu thành phần thật và thành phần giả lập trong từng test.
2. Xác định bất biến và các thay đổi phải cùng commit. Nếu nằm trong cùng database, kiểm tra transaction boundary và rollback; nếu qua nhiều service, thiết kế workflow và phục hồi.
3. Viết integration flow test cho đường thành công và ít nhất một trường hợp thất bại có thể gây cập nhật một phần.
4. Cập nhật contract test khi request, response, status, header hoặc event schema thay đổi.
5. Chạy ArchUnit và kiểm tra module dependency để bảo đảm code mới không tạo phụ thuộc sai chiều hoặc chu trình.
6. Chạy test trong CI với database engine/schema phù hợp và lưu lại báo cáo.
7. Nếu cần ngoại lệ kiến trúc, ghi rõ lý do, phạm vi, rủi ro và điều kiện xem xét lại.

Một chiến lược kiểm thử tốt không dựa vào một loại test duy nhất. Integration flow chứng minh các tầng phối hợp đúng với cấu hình và storage thực; contract test bảo vệ thỏa thuận giữa hệ thống với client hoặc consumer; architecture test giữ cho đồ thị phụ thuộc phù hợp với ranh giới đã chọn. Khi ba loại kiểm thử này được đặt vào pipeline và gắn với các kịch bản nghiệp vụ cụ thể, nhóm có thể phát hiện lỗi tích hợp, thay đổi phá vỡ hợp đồng và phụ thuộc sai trước khi chúng trở thành sự cố khi triển khai.

