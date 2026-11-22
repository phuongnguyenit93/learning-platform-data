# Chiến lược kiểm thử theo trách nhiệm của từng thành phần

Một ứng dụng MVC có thể có nhiều loại kiểm thử: kiểm thử đơn vị cho quy tắc nghiệp vụ, kiểm thử repository với cơ sở dữ liệu, kiểm thử Controller qua HTTP giả lập, kiểm thử tích hợp toàn luồng và kiểm thử giao diện trên trình duyệt. Nếu chọn sai phạm vi, test có thể chậm, khó bảo trì hoặc không phát hiện đúng loại lỗi mà nhóm quan tâm.

**Chiến lược kiểm thử theo trách nhiệm của từng thành phần** xác định mỗi phần của ứng dụng cần được kiểm tra ở ranh giới nào, bằng loại test nào và với mức phụ thuộc ra sao. Trong mô hình **Model–View–Controller (MVC)**, Model chịu trách nhiệm trạng thái và quy tắc nghiệp vụ; View trình bày dữ liệu; Controller tiếp nhận tương tác và điều phối. Ứng dụng web thực tế thường có thêm application service, repository, security filter và adapter hạ tầng. Chiến lược test cần bao phủ các thành phần này mà không biến mọi kiểm thử thành một bài test end-to-end lớn.

Mục tiêu không phải đạt một tỷ lệ test cố định bằng mọi giá. Mục tiêu là đặt kiểm thử gần nơi hành vi được quyết định nhất, đồng thời có đủ kiểm thử tích hợp để xác nhận các thành phần phối hợp đúng khi chạy cùng nhau.

## 1. Bắt đầu từ trách nhiệm, không bắt đầu từ tên lớp

MVC phân chia trách nhiệm trong ứng dụng:

- **Model/Domain:** bảo vệ trạng thái, bất biến và quy tắc nghiệp vụ.
- **Application service:** điều phối use case, transaction và các cộng tác viên.
- **Repository:** lưu trữ và truy vấn dữ liệu.
- **Controller:** tiếp nhận request, binding, validation đầu vào, gọi use case và chọn phản hồi.
- **View:** trình bày dữ liệu đã được chuẩn bị.
- **Security/filter/interceptor:** áp dụng chính sách truy cập và xử lý chung của tầng web.

Một test tốt xác minh hành vi thuộc trách nhiệm của thành phần. Ví dụ, quy tắc “đơn đã giao không thể hủy” thuộc Model hoặc dịch vụ nghiệp vụ; test quy tắc đó không cần khởi động Servlet container. Ngược lại, quy tắc “POST không có CSRF token bị từ chối” phụ thuộc chuỗi bảo mật web và cần test ở ranh giới HTTP/security.

| Thành phần | Hành vi cần kiểm tra | Loại test thường phù hợp |
|---|---|---|
| Domain Model | Bất biến, chuyển trạng thái, phép tính, quy tắc | Unit test |
| Application service | Điều phối use case, transaction boundary, gọi port | Unit test và integration test |
| Repository/ORM | Mapping, query, constraint, phân trang | Persistence slice hoặc integration test |
| Controller | Route, method, binding, validation, status, redirect | MVC slice test |
| View/template | Hiển thị dữ liệu, lỗi, escape, không truy cập persistence | Template/render test và browser test có chọn lọc |
| Security | Xác thực, role, quyền đối tượng, CSRF | Security slice/integration test |
| Adapter bên ngoài | Mapping request/response, timeout, lỗi giao tiếp | Adapter test, contract test |
| Toàn ứng dụng | Luồng người dùng qua nhiều tầng | End-to-end test có chọn lọc |

Ranh giới này không cứng nhắc. Một thành phần có thể cần nhiều loại test, nhưng mỗi test nên có một mục đích rõ ràng.

## 2. Dùng kim tự tháp kiểm thử làm định hướng

Kim tự tháp kiểm thử (test pyramid) là mô hình phân bổ tương đối: nhiều unit test nhanh ở đáy, số lượng vừa phải integration/slice test ở giữa và ít end-to-end test ở đỉnh.

~~~mermaid
flowchart TD
    E[End-to-end tests<br/>Ít, kiểm tra luồng quan trọng]
    I[Integration và slice tests<br/>Kiểm tra ranh giới giữa các thành phần]
    U[Unit tests<br/>Nhiều, nhanh, tập trung vào hành vi]
    E --> I
    I --> U
~~~

Mô hình này giúp cân bằng tốc độ và độ tin cậy:

- Unit test chạy nhanh, xác định lỗi ở phạm vi nhỏ.
- Slice test chỉ khởi động một phần framework cần thiết, ví dụ MVC hoặc JPA.
- Integration test xác nhận các thành phần thật phối hợp đúng.
- End-to-end test kiểm tra một số hành trình người dùng từ giao diện đến hệ thống.

Đây là định hướng chứ không phải luật về số lượng. Ứng dụng có nhiều logic phân tán, tích hợp bên ngoài hoặc giao diện phức tạp có thể cần tỷ lệ khác. Điều quan trọng là không dùng hàng trăm browser test để kiểm tra những quy tắc có thể được xác minh bằng unit test.

## 3. Chọn test theo rủi ro và chi phí thay đổi

Không phải mọi dòng code đều cần cùng mức kiểm thử. Nên ưu tiên hành vi có hậu quả lớn khi sai:

- Tính tiền, thuế, chiết khấu và hoàn tiền.
- Chuyển trạng thái đơn hàng hoặc tài khoản.
- Xác thực, phân quyền và cách ly tenant.
- Binding dữ liệu đầu vào và xử lý lỗi.
- Truy vấn có phân trang, lọc hoặc tổng hợp.
- Tích hợp thanh toán, email, kho vận hoặc hệ thống bên ngoài.
- Các luồng có nhiều bước hoặc tác dụng phụ.

Với mỗi rủi ro, hãy hỏi:

1. Quy tắc được quyết định ở đâu?
2. Có thể kiểm tra ở phạm vi nhỏ nhất nào?
3. Cần test tích hợp nào để xác minh cấu hình hoặc công nghệ thực tế?
4. Có hành trình người dùng nào cần được xác nhận từ đầu đến cuối?

Ví dụ, phép tính tổng tiền nên có unit test cho nhiều trường hợp biên. Một integration test xác nhận dữ liệu đơn hàng được lưu đúng. Một E2E test có thể xác minh người dùng tạo đơn thành công. Không cần lặp lại toàn bộ tổ hợp phép tính trong E2E.

## 4. Unit test cho Domain Model

Domain Model là nơi phù hợp để kiểm tra các quy tắc nghiệp vụ thuần túy. Unit test nên tạo đối tượng, gọi hành vi và xác minh trạng thái hoặc kết quả.

Ví dụ, đơn hàng chỉ được hủy khi chưa giao:

~~~java
class OrderTest {

    @Test
    void confirmedOrderCanBeCancelled() {
        Order order = Order.confirmed();

        order.cancel();

        assertThat(order.getStatus()).isEqualTo(OrderStatus.CANCELLED);
    }

    @Test
    void shippedOrderCannotBeCancelled() {
        Order order = Order.shipped();

        assertThatThrownBy(order::cancel)
                .isInstanceOf(OrderCannotBeCancelled.class);

        assertThat(order.getStatus()).isEqualTo(OrderStatus.SHIPPED);
    }
}
~~~

Test xác minh cả kết quả thành công lẫn trường hợp bị từ chối. Với hành vi thất bại, cần kiểm tra trạng thái không bị thay đổi ngoài ý muốn.

### 4.1. Những gì nên kiểm tra trong Domain

- Trạng thái ban đầu và chuyển trạng thái hợp lệ.
- Chuyển trạng thái không hợp lệ.
- Bất biến như số lượng phải dương hoặc tổng tiền không âm.
- Phép tính với giá trị biên, số thập phân và làm tròn.
- Quy tắc thời gian, hạn sử dụng và múi giờ.
- Quy tắc kết hợp nhiều điều kiện.
- Giá trị object và equality nếu là một phần hợp đồng.

### 4.2. Giữ unit test độc lập với framework

Nếu domain không cần Spring, JPA hoặc Servlet, đừng khởi động các framework đó chỉ để kiểm tra quy tắc. Test độc lập thường nhanh, dễ đọc và chỉ ra lỗi chính xác hơn.

Nếu một domain object cần thời gian hiện tại, hãy truyền Clock hoặc một abstraction thời gian vào để test không phụ thuộc đồng hồ thật:

~~~java
class SubscriptionTest {
    @Test
    void expiresAtTheConfiguredInstant() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-10T00:00:00Z"),
                ZoneOffset.UTC
        );
        Subscription subscription = new Subscription(
                Instant.parse("2026-01-09T00:00:00Z")
        );

        assertThat(subscription.isExpired(clock)).isTrue();
    }
}
~~~

## 5. Unit test cho Application Service

Application service điều phối một use case. Nó thường lấy dữ liệu qua repository port, gọi domain behavior và yêu cầu lưu kết quả hoặc phát sự kiện.

Test service có thể dùng mock hoặc fake cho các dependency bên ngoài để kiểm tra:

- Đúng repository hoặc gateway được gọi.
- Đúng dữ liệu được truyền vào.
- Use case không lưu khi validation nghiệp vụ thất bại.
- Kết quả được chuyển đổi đúng.
- Các lỗi từ dependency được ánh xạ hoặc truyền lên theo hợp đồng.

Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class CancelOrderServiceTest {

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    CancelOrderService service;

    @Test
    void savesOrderAfterSuccessfulCancellation() {
        Order order = Order.confirmed();
        given(orderRepository.findById(42L)).willReturn(Optional.of(order));

        service.cancel(42L);

        assertThat(order.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        then(orderRepository).should().save(order);
    }

    @Test
    void doesNotSaveWhenOrderCannotBeCancelled() {
        Order order = Order.shipped();
        given(orderRepository.findById(42L)).willReturn(Optional.of(order));

        assertThatThrownBy(() -> service.cancel(42L))
                .isInstanceOf(OrderCannotBeCancelled.class);

        then(orderRepository).should(never()).save(any());
    }
}
~~~

Ví dụ giả định service gọi `save` sau khi thay đổi trạng thái. Nếu repository sử dụng dirty checking và không cần gọi save tường minh, test nên xác minh hợp đồng thực tế của use case thay vì bắt chước chi tiết implementation.

### 5.1. Không mock mọi thứ

Mock hữu ích khi kiểm tra tương tác với cổng bên ngoài. Nhưng nếu mọi đối tượng đều là mock, test có thể chỉ xác minh rằng các mock được gọi theo kịch bản đã viết, trong khi logic thật vẫn sai.

Hãy giữ domain object thật khi kiểm tra quy tắc domain. Dùng fake repository đơn giản khi cần dữ liệu trong bộ nhớ. Chỉ mock dependency khi hành vi của dependency không phải mục tiêu của test.

### 5.2. Transaction cần integration test

Unit test có thể xác minh service gọi repository, nhưng không chứng minh transaction rollback, isolation hoặc constraint của database hoạt động đúng. Những hành vi này cần test với transaction manager và cơ sở dữ liệu phù hợp.

## 6. Persistence test cho Repository và ORM

Repository có trách nhiệm chuyển hợp đồng truy vấn thành thao tác lưu trữ. Test cần kiểm tra hành vi với database thật hoặc database test tương thích, thay vì mock repository rồi kết luận query đúng.

Với Spring Boot, `@DataJpaTest` thường được dùng để tạo một persistence test slice:

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void findsOrdersOnlyForTheRequestedOwner() {
        Order orderA = persistOrderFor(10L);
        persistOrderFor(20L);
        entityManager.flush();
        entityManager.clear();

        List<Order> result = orderRepository.findByOwnerId(10L);

        assertThat(result)
                .extracting(Order::getId)
                .containsExactly(orderA.getId());
    }
}
~~~

Test này xác minh điều kiện lọc ở database, thay vì chỉ kiểm tra một list giả lập.

### 6.1. Các trường hợp nên kiểm tra

- Truy vấn lọc đúng owner, tenant và trạng thái.
- Sắp xếp ổn định khi có nhiều bản ghi cùng giá trị sort.
- Phân trang và tổng số bản ghi.
- Projection/DTO query trả đúng trường.
- Mapping quan hệ và cascade.
- Unique constraint, foreign key và nullability.
- Transaction rollback khi có lỗi.
- Optimistic locking hoặc xử lý cập nhật đồng thời nếu có.
- Fetch plan không tạo N+1 ngoài dự kiến.

### 6.2. Vì sao cần flush và clear?

Persistence context có thể giữ entity trong bộ nhớ. Nếu test chỉ đọc lại entity đã được quản lý, nó có thể không thực sự xác minh dữ liệu đã ghi và đọc từ database.

- `flush()` đẩy thay đổi đang chờ xuống database.
- `clear()` loại entity khỏi persistence context hiện tại.
- Truy vấn sau đó buộc ORM lấy dữ liệu qua persistence layer.

Không phải test nào cũng cần hai thao tác này, nhưng chúng hữu ích khi xác minh mapping, query và constraint thực tế.

### 6.3. Chọn database test phù hợp

Database in-memory có thể chạy nhanh nhưng khác với database production về SQL dialect, collation, kiểu dữ liệu, constraint hoặc locking. Với các query và hành vi phụ thuộc database cụ thể, dùng Testcontainers hoặc môi trường database tương thích giúp kết quả đáng tin hơn.

## 7. MVC slice test cho Controller

Controller chịu trách nhiệm chuyển HTTP request thành lời gọi use case và chọn phản hồi. Controller test nên kiểm tra:

- URL và HTTP method được ánh xạ đúng.
- Path variable, query parameter và form/body được binding đúng.
- Validation error được trả về đúng View hoặc response.
- Status code, redirect location và model attribute đúng.
- Controller gọi use case với dữ liệu phù hợp.
- Lỗi nghiệp vụ được chuyển thành phản hồi theo hợp đồng.

Với Spring MVC, `@WebMvcTest` chỉ nạp phần web cần thiết và thường kết hợp với MockMvc:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderQueryService orderQueryService;

    @MockBean
    OrderCommandService orderCommandService;

    @Test
    void detailReturnsViewWithTheRequestedOrder() throws Exception {
        given(orderQueryService.getDetail(42L))
                .willReturn(new OrderDetailView("ORD-42", "An", List.of()));

        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(view().name("orders/detail"))
                .andExpect(model().attributeExists("order"));

        then(orderQueryService).should().getDetail(42L);
    }
}
~~~

Test tập trung vào hợp đồng HTTP của Controller. Nó không cần khởi động database nếu service được thay bằng mock và database không phải mục tiêu của test.

### 7.1. Kiểm tra validation và binding

Một biểu mẫu sai cần trả lại View cùng lỗi:

~~~java
@Test
void invalidFormReturnsTheFormView() throws Exception {
    mockMvc.perform(post("/orders")
                    .param("quantity", "-2")
                    .param("productId", "P-10"))
            .andExpect(status().isOk())
            .andExpect(view().name("orders/new"))
            .andExpect(model().attributeHasFieldErrors(
                    "form",
                    "quantity"
            ));

    then(orderCommandService).shouldHaveNoInteractions();
}
~~~

Test này xác minh Controller không gọi use case khi form chưa hợp lệ. Tên model attribute và status cần khớp cách ứng dụng render form.

### 7.2. Kiểm tra redirect sau POST

Với thao tác thành công, test có thể xác minh PRG:

~~~java
mockMvc.perform(post("/orders")
                .param("productId", "P-10")
                .param("quantity", "2"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/created"));
~~~

Nếu ứng dụng dùng API JSON thay vì HTML redirect, hãy kiểm tra status và response body theo hợp đồng API tương ứng.

## 8. Test View và template

View có trách nhiệm trình bày dữ liệu đã được Controller chuẩn bị. Test View nên tập trung vào:

- Các trường quan trọng được hiển thị.
- Trạng thái rỗng, trạng thái lỗi và trạng thái thành công.
- Dữ liệu đã nhập được giữ lại đúng trường.
- Nội dung động được escape.
- Không render trường bí mật hoặc trường nội bộ.
- Không gọi repository hoặc service trong quá trình render.

Có thể kiểm tra template bằng cơ chế render của framework hoặc test tích hợp web. Một cách đơn giản là truyền DTO thuần vào View và render sau khi transaction đã kết thúc. Nếu View cần entity proxy hoặc persistence context đang mở để hoạt động, đó là dấu hiệu ranh giới trình bày và lưu trữ đang bị trộn.

Không nên viết nhiều test chỉ xác minh HTML có một class CSS cụ thể nếu class đó không thuộc hợp đồng người dùng. Dành browser test cho hành vi tương tác thực sự như gửi form, hiển thị lỗi, điều hướng và accessibility.

## 9. Test Security ở đúng ranh giới

Security có nhiều lớp: xác thực, URL authorization, method authorization, quyền trên đối tượng và CSRF. Mỗi loại cần test phù hợp.

| Chính sách | Phạm vi test phù hợp |
|---|---|
| Chưa đăng nhập không vào endpoint riêng tư | Security/MVC test |
| Chỉ ADMIN vào route quản trị | Security/MVC test |
| Customer chỉ xem đơn của mình | Service/repository test và MVC integration test |
| Tenant A không đọc dữ liệu tenant B | Repository/service integration test |
| POST thiếu CSRF token bị chặn | Security filter test |
| Response không chứa password hash | Controller/serialization test |

Test security cần có cả trường hợp được phép và bị từ chối. Nếu chỉ viết test âm, cấu hình deny-all cũng có thể làm test xanh dù ứng dụng không còn dùng được.

Đặc biệt, test quyền trên đối tượng nên chuẩn bị hai actor và hai tài nguyên. Chỉ test role CUSTOMER không phát hiện lỗi Customer A đọc dữ liệu Customer B.

## 10. Test tích hợp cho luồng giữa các tầng

Unit test từng lớp không bảo đảm các lớp phối hợp đúng khi chạy cùng nhau. Integration test xác minh một nhóm thành phần thật:

- Controller + application service + repository + database.
- Security filter + Controller + service.
- Service + transaction manager + database.
- Adapter HTTP + stub server của dịch vụ ngoài.

Ví dụ luồng tạo đơn:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as OrderController
    participant A as OrderApplicationService
    participant D as Domain Model
    participant R as OrderRepository
    participant DB as Database

    User->>C: POST /orders
    C->>C: Bind và validate form
    C->>A: createOrder(command)
    A->>D: Tạo và kiểm tra đơn
    A->>R: save(order)
    R->>DB: INSERT
    DB-->>R: Kết quả lưu
    R-->>A: Order
    A-->>C: Order ID
    C-->>User: Redirect /orders/{id}
~~~

Integration test nên xác minh một số thuộc tính xuyên suốt:

- Request hợp lệ tạo dữ liệu đúng trong database.
- Request không hợp lệ không tạo bản ghi.
- Quyền truy cập được áp dụng trước khi dữ liệu nhạy cảm được trả.
- Lỗi persistence được ánh xạ thành phản hồi an toàn.
- Transaction rollback khi một bước quan trọng thất bại.

Không cần lặp lại mọi tổ hợp đầu vào đã được unit test bao phủ. Integration test tập trung vào cấu hình và tương tác thật giữa các tầng.

## 11. Contract test cho tích hợp bên ngoài

Nếu application service gọi payment gateway, email provider hoặc API vận chuyển, test không nên phụ thuộc vào dịch vụ thật trong mọi lần chạy.

Có thể dùng:

- Stub server để trả response thành công, lỗi, timeout hoặc dữ liệu sai định dạng.
- Contract test để xác minh request/response tuân theo hợp đồng đã thống nhất.
- Test adapter để xác minh mapping từ kiểu nội bộ sang giao thức bên ngoài.

Ví dụ các trường hợp cần kiểm tra với payment adapter:

| Tình huống | Hành vi cần xác minh |
|---|---|
| Gateway chấp nhận thanh toán | Mapping mã giao dịch và trạng thái đúng |
| Gateway từ chối | Ánh xạ thành lỗi nghiệp vụ phù hợp |
| Gateway timeout | Không giả định giao dịch thất bại; hỗ trợ kiểm tra trạng thái |
| Response thiếu trường bắt buộc | Adapter từ chối dữ liệu không hợp lệ |
| Gateway trả 5xx | Retry theo chính sách, không tạo giao dịch trùng |

Không nên để unit test gọi mạng thật. Những test phụ thuộc dịch vụ bên ngoài thường chậm, dễ chập chờn và khó tái hiện khi hệ thống kia thay đổi.

## 12. End-to-end test cho hành trình người dùng

End-to-end test (E2E) chạy ứng dụng gần với cách người dùng sử dụng: mở trình duyệt, đi qua trang, nhập dữ liệu và kiểm tra kết quả. Nó giúp xác minh những thứ test ở tầng thấp không thể bao phủ hoàn toàn:

- Route, template và static resource được nối đúng.
- Form hoạt động trong trình duyệt.
- Cookie, session và redirect tương tác đúng.
- JavaScript và HTML phối hợp đúng.
- Luồng người dùng quan trọng hoàn tất từ đầu đến cuối.

Nên chọn một số hành trình có giá trị cao, ví dụ:

1. Đăng nhập và xem hồ sơ của mình.
2. Tạo đơn hàng hợp lệ.
3. Nhập form sai và sửa lỗi.
4. Người dùng không có quyền bị từ chối khi mở tài nguyên của người khác.
5. Đăng xuất làm session không còn truy cập được.

E2E test thường tốn thời gian và dễ bị ảnh hưởng bởi dữ liệu, timing hoặc môi trường. Không nên dùng nó để kiểm tra hàng trăm biến thể của một phép tính thuần túy.

## 13. Test double: Dummy, Stub, Fake, Mock và Spy

Test double là đối tượng thay thế một dependency trong test. Chọn loại phù hợp giúp test rõ mục tiêu.

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Dummy | Được truyền vào nhưng không dùng | Một đối tượng cần để thỏa constructor |
| Stub | Trả kết quả cố định | Repository trả về một Order mẫu |
| Fake | Có implementation đơn giản nhưng hoạt động | In-memory repository |
| Mock | Xác minh tương tác được mong đợi | Xác minh gateway được gọi một lần |
| Spy | Bao quanh đối tượng thật và ghi nhận tương tác | Theo dõi lời gọi một phương thức |

Không nên xác minh quá nhiều chi tiết nội bộ bằng mock. Nếu refactor cách triển khai nhưng hành vi bên ngoài không đổi, test chỉ nên tiếp tục xanh. Ưu tiên kiểm tra kết quả và tác dụng phụ có ý nghĩa; xác minh tương tác khi nó là một phần hợp đồng, chẳng hạn không gửi thanh toán lần thứ hai.

## 14. Dữ liệu test và tính độc lập giữa các test

Test đáng tin cần chạy độc lập, có thể lặp lại và không phụ thuộc thứ tự.

Một số nguyên tắc:

- Mỗi test tạo dữ liệu cần thiết cho chính nó.
- Dùng ID hoặc dữ liệu riêng, tránh phụ thuộc bản ghi tồn tại sẵn.
- Dọn dữ liệu hoặc rollback transaction theo cơ chế phù hợp.
- Không dùng chung mutable static state giữa các test.
- Dùng clock cố định cho quy tắc thời gian.
- Không phụ thuộc mạng công cộng hoặc dịch vụ bên ngoài không ổn định.
- Tránh dùng sleep để chờ; ưu tiên đồng bộ hóa hoặc chờ có điều kiện với timeout rõ.

Fixture nên thể hiện ý nghĩa nghiệp vụ. Ví dụ `confirmedOrder()` dễ hiểu hơn một constructor có mười tham số không giải thích. Tuy nhiên, builder test cũng cần giữ dữ liệu hợp lệ; không nên tạo một object không thể tồn tại trong hệ thống chỉ để test chạy.

## 15. Kiểm thử bất đồng bộ và sự kiện

Một số use case MVC phát sự kiện sau khi lưu dữ liệu, gửi email hoặc xử lý công việc nền. Cần xác định test đang kiểm tra điều gì:

- Service có phát đúng sự kiện sau khi use case thành công không?
- Sự kiện có được phát khi transaction commit không?
- Consumer xử lý sự kiện đúng và có tính idempotent không?
- Lỗi tạm thời có retry hoặc đưa vào dead-letter queue theo chính sách không?

Unit test có thể xác minh event được tạo. Integration test cần kiểm tra transaction/event listener hoặc message broker thực tế. Không nên dùng một test service đồng bộ để kết luận luồng message bất đồng bộ hoạt động đúng.

Với tác vụ nền, hãy có correlation ID hoặc business ID để liên kết log và test. Test cần chờ điều kiện hoàn tất thay vì sleep một khoảng cố định rồi giả định công việc đã chạy.

## 16. Phân biệt test hành vi với test implementation

Test hành vi xác minh điều người dùng hoặc thành phần khác có thể quan sát. Test implementation phụ thuộc vào chi tiết nội bộ như tên phương thức riêng, số lần gọi helper hoặc cấu trúc biến tạm.

Ví dụ:

- Tốt: “Khi đơn đã giao, yêu cầu hủy bị từ chối và trạng thái vẫn là SHIPPED.”
- Mong manh: “Phương thức private validateStatus được gọi đúng một lần.”
- Tốt: “POST hợp lệ redirect đến trang xác nhận.”
- Mong manh: “Controller gọi helper buildRedirectUrl.”

Test cần bảo vệ hợp đồng và hành vi quan trọng. Khi test phụ thuộc implementation quá sâu, một refactor an toàn có thể làm hỏng test dù sản phẩm vẫn đúng.

## 17. Coverage không đồng nghĩa với chất lượng

Code coverage cho biết phần mã được thực thi khi test chạy, nhưng không chứng minh assertion có ý nghĩa. Một test có thể đi qua 100% dòng code mà không kiểm tra kết quả quan trọng.

Nên xem coverage cùng với:

- Những nhánh nghiệp vụ đã được kiểm tra.
- Trường hợp biên và dữ liệu không hợp lệ.
- Test âm cho quyền truy cập.
- Assertion về trạng thái sau thao tác thất bại.
- Mutation testing nếu dự án cần đánh giá khả năng phát hiện lỗi của test.
- Tính dễ đọc và khả năng tái hiện khi test thất bại.

Đừng viết test chỉ để tăng phần trăm coverage. Hãy dùng coverage để tìm vùng mã chưa có kiểm tra, sau đó xác định rủi ro và hành vi cần bảo vệ.

## 18. Tổ chức test trong dự án Spring MVC

Một cấu trúc đơn giản có thể là:

~~~text
src/
├── main/
│   ├── java/com/example/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   └── web/
│   └── resources/templates/
└── test/
    ├── java/com/example/
    │   ├── domain/
    │   ├── application/
    │   ├── infrastructure/
    │   └── web/
    └── resources/
~~~

Tên thư mục test có thể phản chiếu package production để dễ tìm, nhưng không bắt buộc phải giống hệt. Có thể phân biệt thêm:

- `*Test`: unit test nhanh.
- `*RepositoryTest`: persistence test.
- `*ControllerTest`: MVC slice test.
- `*IntegrationTest`: tích hợp nhiều tầng.
- `*E2ETest`: hành trình trình duyệt.

Tên test nên nói rõ hành vi, ví dụ `shippedOrderCannotBeCancelled`, thay vì tên chung như `testCancel`.

## 19. Chạy test theo tầng trong CI

Pipeline có thể chạy nhóm test theo tốc độ và chi phí:

~~~mermaid
flowchart TD
    C[Commit / Pull Request] --> U[Unit tests]
    U -->|Pass| S[Slice tests]
    S -->|Pass| I[Integration tests]
    I -->|Pass| E[Selected E2E / contract tests]
    E -->|Pass| R[Review result]
    U -->|Fail| F[Feedback]
    S -->|Fail| F
    I -->|Fail| F
    E -->|Fail| F
~~~

Một chiến lược thường dùng:

1. Chạy unit test nhanh trên mỗi thay đổi.
2. Chạy MVC, JPA và security slice test trong pull request.
3. Chạy integration test với database hoặc container phù hợp.
4. Chạy contract test khi thay đổi adapter hoặc API tích hợp.
5. Chạy một tập E2E quan trọng trên môi trường tích hợp hoặc trước release.

Không nên để test E2E chập chờn chặn mọi thay đổi mà không có cơ chế chẩn đoán. Khi test thất bại, báo cáo cần chỉ rõ loại test, dữ liệu và log liên quan.

## 20. Những lỗi thường gặp khi xây dựng chiến lược test

### Chỉ kiểm thử Controller

Mock service trả dữ liệu cố định có thể làm Controller test xanh trong khi domain rule hoặc query thực tế sai. Cần test riêng Model, service và repository.

### Dùng E2E cho mọi quy tắc

E2E chậm và khó xác định nguyên nhân. Quy tắc tính toán hoặc chuyển trạng thái nên được kiểm tra ở unit test; E2E xác minh một số hành trình đại diện.

### Mock repository trong mọi test

Mock không kiểm tra query, mapping, constraint hoặc transaction. Cần persistence test với database.

### Test chỉ xác minh status code

HTTP 200 không chứng minh response đúng dữ liệu; 403 không chứng minh dữ liệu không thay đổi. Kiểm tra body, View, header và trạng thái sau thao tác khi phù hợp.

### Chỉ có test âm

Test từ chối truy cập là cần thiết, nhưng cũng cần test actor hợp lệ để chứng minh chức năng vẫn hoạt động.

### Dữ liệu test phụ thuộc thứ tự

Test chạy riêng thì xanh nhưng chạy cả suite lại lỗi thường do shared state, dữ liệu tồn dư hoặc test phụ thuộc nhau. Mỗi test cần tự chuẩn bị dữ liệu và dọn dẹp rõ.

### Assertion quá chặt vào chi tiết không ổn định

Không nên so sánh toàn bộ HTML hoặc JSON nếu thứ tự trường, khoảng trắng hay metadata không thuộc hợp đồng. Chọn assertion cho các trường và hành vi có ý nghĩa.

### Không test cấu hình bảo mật thật

Nếu test tắt security filter hoặc mock toàn bộ principal, nó không chứng minh cấu hình authorization hoạt động. Cần có security integration test với filter chain thật.

## 21. Ví dụ ma trận test cho một use case MVC

Giả sử chức năng xem và hủy đơn hàng. Có thể phân bổ test như sau:

| Hành vi | Nơi quyết định | Test chính | Assertion trọng tâm |
|---|---|---|---|
| Đơn CONFIRMED chuyển sang CANCELLED | Domain | Unit | Trạng thái mới là CANCELLED |
| Đơn SHIPPED không thể hủy | Domain | Unit | Exception và trạng thái không đổi |
| Service tải đơn và lưu sau khi hủy | Application | Unit | Repository được gọi đúng theo hợp đồng |
| Chỉ owner hoặc actor được ủy quyền xem đơn | Application/query | Service + repository integration | Người khác không tải được dữ liệu |
| GET /orders/{id} trả đúng View | Controller | MVC slice | Status, View name và model |
| ID không hợp lệ hoặc không tồn tại | Controller/service | MVC slice | 404 hoặc lỗi theo hợp đồng |
| Customer A không xem đơn B | Security + application | MVC integration | Bị từ chối, không rò dữ liệu |
| Template hiển thị tên và dòng hàng | View | Render test | Trường cần có được hiển thị |
| Người dùng tạo và hủy đơn qua giao diện | Toàn luồng | E2E | Hành trình hoàn tất đúng |

Ma trận này tránh việc mọi test dồn vào Controller. Mỗi trách nhiệm được kiểm tra ở phạm vi phù hợp, trong khi integration test xác nhận các ranh giới quan trọng nối với nhau.

## 22. Checklist xây dựng chiến lược kiểm thử MVC

- [ ] Đã liệt kê trách nhiệm của Domain, Application, Repository, Controller, View và Security.
- [ ] Mỗi quy tắc nghiệp vụ quan trọng có unit test.
- [ ] Application service có test cho luồng thành công, thất bại và tác dụng phụ.
- [ ] Repository có test với database cho query, mapping và constraint quan trọng.
- [ ] Controller có MVC slice test cho route, binding, validation, status và redirect.
- [ ] View được kiểm tra việc hiển thị, escape và không phụ thuộc persistence.
- [ ] Security có test xác thực, role, quyền đối tượng và CSRF theo chính sách.
- [ ] Có integration test cho các ranh giới quan trọng giữa các tầng.
- [ ] Adapter bên ngoài có stub/contract test cho thành công, lỗi và timeout.
- [ ] E2E chỉ bao phủ các hành trình người dùng có giá trị cao.
- [ ] Test có dữ liệu riêng, độc lập và có thể chạy lặp lại.
- [ ] Có kiểm tra request thất bại không tạo tác dụng phụ.
- [ ] Assertion tập trung vào hành vi và hợp đồng ổn định.
- [ ] Coverage được dùng để tìm khoảng trống, không phải mục tiêu duy nhất.
- [ ] CI chạy các nhóm test theo tốc độ và mức độ quan trọng phù hợp.

## Kết luận

Chiến lược kiểm thử MVC hiệu quả bắt đầu từ trách nhiệm của từng thành phần. Domain được kiểm tra bằng unit test cho quy tắc và trạng thái; application service được kiểm tra về điều phối; repository cần persistence test với database; Controller cần MVC slice test cho HTTP, binding và phản hồi; View cần được kiểm tra như lớp trình bày; security cần test ở cả endpoint lẫn quyền trên đối tượng. Integration, contract và E2E test xác nhận các ranh giới quan trọng phối hợp đúng. Khi mỗi loại test có mục đích rõ, nhóm có phản hồi nhanh ở thay đổi nhỏ và đủ bằng chứng cho các luồng quan trọng của ứng dụng web.
