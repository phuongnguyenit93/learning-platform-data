# Bảo vệ hành vi hiện có bằng kiểm thử đặc trưng

Khi cải tiến một ứng dụng MVC đã chạy lâu, nhóm phát triển thường không có tài liệu đầy đủ về mọi hành vi đang tồn tại. Controller có thể trả một status code đặc biệt, form có thể giữ lại một số trường sau validation lỗi, service có thể làm tròn tiền theo quy tắc cũ, hoặc một thao tác có thể phát email và cập nhật nhiều bảng. Những hành vi này đôi khi không được mô tả trong yêu cầu ban đầu nhưng vẫn đang được người dùng hoặc hệ thống khác phụ thuộc.

**Kiểm thử đặc trưng (characterization test)** ghi lại hành vi có thể quan sát được của hệ thống tại một thời điểm. Nhóm dùng các kiểm thử này làm đường cơ sở trước khi refactor, sau đó chạy lại để biết thay đổi cấu trúc có vô tình làm đổi hành vi hay không. Chúng đặc biệt hữu ích với ứng dụng MVC cũ, nơi Controller, Model, View, repository và tích hợp bên ngoài có thể đã đan xen qua nhiều năm.

Kiểm thử đặc trưng mô tả điều hệ thống đang làm; nó chưa tự chứng minh điều đó đúng về mặt nghiệp vụ. Vì vậy, cần kết hợp quan sát, đánh giá và quyết định rõ hành vi nào phải được giữ, hành vi nào là lỗi cần sửa và hành vi nào chưa đủ thông tin để kết luận.

## 1. Kiểm thử đặc trưng giải quyết vấn đề gì?

Một refactor thay đổi cách tổ chức mã nguồn nhưng được kỳ vọng giữ nguyên hành vi. Nếu không có kiểm thử, nhóm khó biết liệu việc tách Controller, chuyển logic vào service, thay ORM hoặc viết lại template có tạo ra khác biệt ngoài ý muốn hay không.

Ví dụ một trang chi tiết đơn hàng đang có các hành vi:

- Người dùng đã đăng nhập và có quyền xem nhận HTML với mã đơn, trạng thái và tổng tiền.
- Người dùng không có quyền nhận 404 để không tiết lộ đơn hàng có tồn tại hay không.
- Request có ID sai định dạng nhận 400.
- Đơn đã hủy vẫn hiển thị trong lịch sử nhưng không có nút hủy lần nữa.
- Tổng tiền được hiển thị theo quy tắc làm tròn hiện tại.

Một bộ characterization test có thể ghi lại các kết quả này trước khi nhóm đổi cấu trúc. Sau refactor, nếu status, dữ liệu hoặc tác dụng phụ thay đổi, test sẽ chỉ ra điểm khác biệt để nhóm xem xét.

| Kiểm thử | Mục tiêu chính |
|---|---|
| Characterization test | Ghi nhận hành vi hiện tại có thể quan sát được |
| Acceptance/contract test | Xác nhận hành vi theo yêu cầu hoặc hợp đồng đã thống nhất |
| Regression test | Ngăn lỗi đã biết tái xuất hiện |
| Unit test | Kiểm tra một đơn vị logic trong phạm vi cô lập |
| Integration test | Kiểm tra sự cộng tác giữa các thành phần thật |
| End-to-end test | Kiểm tra một luồng người dùng xuyên suốt hệ thống |

Một characterization test sau khi được đánh giá có thể trở thành regression test hoặc một phần của contract suite. Tuy nhiên, hai khái niệm không đồng nhất: hành vi được quan sát hôm nay có thể là hành vi sai và cần thay đổi.

## 2. Nguyên tắc: ghi nhận điều quan sát được

Một kiểm thử đặc trưng tốt mô tả đầu vào, điều kiện ban đầu và kết quả bên ngoài mà người dùng hoặc hệ thống khác có thể nhận biết. Nó không nên khóa vào tên phương thức private, thứ tự gọi helper hoặc cấu trúc package hiện tại.

Với một request MVC, những điều có thể quan sát gồm:

- HTTP method, URL, query parameter và header.
- Status code, redirect, response header và body.
- View được chọn và các thuộc tính quan trọng được đưa vào View.
- JSON field, kiểu dữ liệu, mã lỗi và định dạng response.
- Trạng thái dữ liệu sau thao tác.
- Sự kiện, thông báo hoặc tác dụng phụ có ý nghĩa được phát ra.
- Quyền truy cập và hành vi khi đầu vào không hợp lệ.

Không cần ghi lại mọi chi tiết. Hãy tập trung vào hành vi có khả năng được người dùng, client, báo cáo hoặc hệ thống tích hợp phụ thuộc.

Ví dụ, nếu Controller hiện gọi ba helper nội bộ trước khi trả View, thứ tự đó không phải hợp đồng trừ khi nó làm thay đổi kết quả hoặc tác dụng phụ. Ngược lại, việc tạo đơn chỉ gửi một email xác nhận là hành vi có ý nghĩa vì gửi trùng email ảnh hưởng người dùng.

## 3. Quy trình tạo characterization test

Một quy trình có thể áp dụng cho từng use case:

1. Chọn một luồng đang hoạt động và có phạm vi đủ nhỏ.
2. Xác định điểm vào, dữ liệu ban đầu và danh tính người gọi.
3. Chạy hệ thống với các trường hợp đại diện và quan sát response cùng tác dụng phụ.
4. Ghi lại kết quả bằng assertion rõ ràng hoặc snapshot có kiểm soát.
5. Phân loại hành vi: cần giữ, cần sửa, chưa rõ hoặc không ổn định.
6. Chuyển các hành vi cần giữ thành test có tên mô tả yêu cầu.
7. Refactor từng bước nhỏ và chạy lại test sau mỗi thay đổi.
8. Khi hành vi thay đổi có chủ đích, cập nhật test cùng với quyết định và lý do.

~~~mermaid
flowchart TD
    A[Chọn luồng MVC hiện có] --> B[Chuẩn bị dữ liệu và điều kiện]
    B --> C[Chạy request và quan sát]
    C --> D[Ghi status, response, state và side effects]
    D --> E{Đánh giá hành vi}
    E -->|Cần giữ| F[Viết characterization test]
    E -->|Là lỗi cần sửa| G[Ghi nhận defect và test mục tiêu mới]
    E -->|Chưa rõ| H[Xác minh với nghiệp vụ hoặc chủ sở hữu]
    F --> I[Refactor từng bước]
    I --> J[Chạy lại test và review khác biệt]
    G --> I
    H --> I
~~~

### 3.1. Chọn một luồng có giá trị

Không nên bắt đầu bằng việc snapshot toàn bộ ứng dụng. Chọn một use case có người dùng hoặc hệ thống phụ thuộc rõ ràng, ví dụ:

- Đăng nhập và chuyển hướng sau đăng nhập.
- Tạo đơn hàng từ form.
- Xem lịch sử giao dịch.
- Cập nhật hồ sơ.
- Hủy một đơn chưa giao.
- REST endpoint trả chi tiết sản phẩm.

Mỗi luồng có thể được chia thành các trường hợp: thành công, đầu vào sai, không tìm thấy, không đủ quyền, xung đột trạng thái và lỗi tích hợp.

### 3.2. Ghi lại điều kiện ban đầu

Kết quả request phụ thuộc trạng thái trước khi chạy. Hãy ghi rõ:

- User, role, tenant và quyền của người gọi.
- Dữ liệu sản phẩm/đơn hàng/tài khoản liên quan.
- Trạng thái hiện tại của aggregate.
- Thời gian hoặc locale nếu chúng ảnh hưởng response.
- Cấu hình feature flag hoặc chính sách liên quan.
- Các dịch vụ ngoài đang được giả lập hay chạy thật.

Một test chỉ ghi “POST trả 302” mà không nêu dữ liệu và danh tính người gọi thường không đủ để giải thích vì sao hành vi đó đúng.

## 4. Đặt characterization test ở đúng ranh giới MVC

Nên ghi nhận hành vi tại ranh giới có ý nghĩa. Không phải mọi chi tiết đều cần một end-to-end test.

| Ranh giới | Điều nên ghi nhận |
|---|---|
| Controller/HTTP | Status, redirect, header, JSON, View name, validation và authorization |
| Application service/use case | Kết quả nghiệp vụ, trạng thái thay đổi và các port được gọi vì tác dụng phụ |
| Domain model | Bất biến, tính toán, chuyển trạng thái |
| Repository/database | Dữ liệu đọc/ghi, mapping, constraint và transaction |
| View/browser | Nội dung và hành động người dùng nhìn thấy |
| Tích hợp bên ngoài | Request được gửi, thông điệp được phát và cách xử lý lỗi |

Một chiến lược cân bằng thường dùng unit test cho quy tắc domain, MVC slice test cho HTTP mapping, integration test cho database và một số end-to-end test cho hành trình quan trọng. Dùng đúng ranh giới giúp test nhanh, dễ hiểu và ít phụ thuộc vào cấu trúc nội bộ.

### 4.1. Characterization test cho Controller với MockMvc

Giả sử một ứng dụng Spring MVC có endpoint xem đơn hàng. Trước khi refactor, ta muốn ghi lại response HTML cho người có quyền:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderPageCharacterizationTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepositoryTestSupport testOrders;

    @Test
    void customerSeesOrderNumberStatusAndTotal() throws Exception {
        long customerId = 7L;
        long orderId = testOrders.createPlacedOrder(
                customerId,
                "ORD-42",
                new BigDecimal("125000.00"),
                "VND"
        );

        mockMvc.perform(get("/orders/{id}", orderId)
                        .with(authentication(customerAuthentication(customerId))))
                .andExpect(status().isOk())
                .andExpect(view().name("orders/detail"))
                .andExpect(model().attributeExists("order"))
                .andExpect(content().string(
                        containsString("ORD-42")
                ));
    }
}
~~~

Đây là ví dụ khung: OrderRepositoryTestSupport và customerAuthentication là fixture riêng của dự án; cần cấu hình authentication đúng kiểu principal mà ứng dụng sử dụng. Nếu Spring Security bật CSRF, các request ghi dữ liệu cần gửi token CSRF trong test. Test này ghi nhận status, View và một nội dung quan trọng. Nó không kiểm tra tên method service hoặc thứ tự gọi mapper.

Nếu trang có nhiều dữ liệu động, không nên so sánh toàn bộ HTML nguyên văn. Hãy kiểm tra những phần có ý nghĩa như mã đơn, tổng tiền, trạng thái, liên kết và nút thao tác.

### 4.2. Ghi nhận JSON contract

Với REST API, các trường và status có thể là hợp đồng với client:

~~~java
@Test
void apiReturnsTheCurrentOrderRepresentation() throws Exception {
    long orderId = testOrders.createPlacedOrder(
            7L,
            "ORD-42",
            new BigDecimal("125000.00"),
            "VND"
    );

    mockMvc.perform(get("/api/orders/{id}", orderId)
                    .with(authentication(customerAuthentication(7L))))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.orderNumber").value("ORD-42"))
            .andExpect(jsonPath("$.status").value("PLACED"))
            .andExpect(jsonPath("$.total.amount").value(125000.00))
            .andExpect(jsonPath("$.total.currency").value("VND"));
}
~~~

Các field trong ví dụ đại diện cho response hiện tại. Khi ghi nhận hệ thống thật, cần lấy đúng cấu trúc đã quan sát được, không tự giả định response có nested object hoặc mã trạng thái cụ thể. Nếu thứ tự JSON không thuộc hợp đồng, không so sánh chuỗi JSON nguyên văn.

### 4.3. Ghi nhận validation và redirect

Với form HTML, hành vi có thể bao gồm trả lại trang nhập, giữ lại dữ liệu người dùng đã nhập, hiển thị lỗi và không tạo bản ghi:

~~~java
@Test
void invalidQuantityReturnsFormWithErrorsAndDoesNotCreateOrder()
        throws Exception {
    mockMvc.perform(post("/orders")
                    .with(authentication(customerAuthentication(7L)))
                    .with(csrf())
                    .param("productId", "9")
                    .param("quantity", "0"))
            .andExpect(status().isOk())
            .andExpect(view().name("orders/new"))
            .andExpect(model().attributeHasFieldErrors("form", "quantity"));

    assertThat(testOrders.countForCustomer(7L)).isZero();
}
~~~

Nếu ứng dụng hiện tại redirect khi lỗi, dùng status và redirect URL đã quan sát được. Characterization test ghi lại hành vi đang chạy; quyết định thay đổi UX là một thay đổi yêu cầu riêng.

Với thao tác thành công theo Post/Redirect/Get, ghi nhận redirect đích và việc chỉ có một đơn được tạo. Nếu hợp đồng quy định 303, assert chính xác 303; nếu chỉ yêu cầu redirect, có thể kiểm tra nhóm 3xx.

## 5. Ghi nhận quy tắc nghiệp vụ trước khi di chuyển logic

Khi refactor một Controller lớn, logic nghiệp vụ có thể đang nằm trực tiếp trong action method. Trước khi di chuyển nó vào service hoặc domain model, hãy ghi lại các đầu vào và kết quả đại diện.

Ví dụ một phép tính tổng tiền cũ:

~~~java
@Test
void currentOrderCalculationUsesTheObservedRoundingRule() {
    Order order = legacyOrderWithLine(
            3,
            new BigDecimal("10.005"),
            new BigDecimal("2.00")
    );

    BigDecimal total = legacyCalculator.total(order);

    assertThat(total).isEqualByComparingTo("32.02");
}
~~~

Giá trị kỳ vọng trong ví dụ chỉ minh họa một kết quả đã được xác nhận bằng cách chạy implementation cũ. Không lấy số này làm quy tắc phổ quát cho mọi hệ thống tiền tệ. Cần xác định quy tắc làm tròn theo hợp đồng nghiệp vụ, đơn vị tiền, scale và thời điểm làm tròn.

Sau khi có test, nhóm có thể chuyển phép tính vào Order.total() hoặc một policy. Test sẽ cho biết refactor có giữ nguyên kết quả đã ghi nhận hay không.

### 5.1. Dùng bảng trường hợp thay vì chỉ một ví dụ

Một phép tính hoặc chuyển trạng thái thường cần nhiều trường hợp:

| Đầu vào | Hành vi cần quan sát |
|---|---|
| Số lượng 1 | Tổng tiền cơ bản |
| Số lượng lớn hơn 1 | Nhân số lượng và đơn giá |
| Giảm giá hợp lệ | Cách áp dụng và làm tròn |
| Phí vận chuyển bằng 0 | Có cộng phí hay không |
| Tiền tệ khác nhau | Bị từ chối hay được quy đổi |
| Giá trị biên | Cách xử lý số 0, số âm hoặc giới hạn |

Với state machine, ghi nhận cả chuyển trạng thái hợp lệ và bị từ chối. Đừng chỉ kiểm thử happy path nếu người dùng phụ thuộc vào các trạng thái cũ.

## 6. Characterization test và golden master

Golden master (còn gọi là approval test hoặc snapshot test trong một số công cụ) lưu một kết quả tham chiếu rồi so sánh lần chạy sau với kết quả đó. Nó hữu ích khi output phức tạp, khó viết assertion thủ công, ví dụ tài liệu, báo cáo hoặc một vùng HTML lớn.

Luồng làm việc:

1. Chạy implementation hiện tại với fixture ổn định.
2. Lưu output đã được chuẩn hóa thành baseline.
3. Review baseline để hiểu nội dung nào có ý nghĩa.
4. Chạy lại sau refactor và xem diff.
5. Chỉ cập nhật baseline sau khi xác nhận khác biệt là thay đổi được chấp thuận.

~~~mermaid
flowchart LR
    A[Fixture cố định] --> B[Implementation hiện tại]
    B --> C[Output quan sát]
    C --> D[Normalize dữ liệu động]
    D --> E[Golden master]
    F[Implementation sau refactor] --> G[Output mới]
    G --> H[Normalize giống baseline]
    H --> I[So sánh và review diff]
    E --> I
~~~

Không nên tự động chấp nhận mọi snapshot mới chỉ vì test đang đỏ. Nếu snapshot thay đổi, cần xác định:

- Thay đổi có được yêu cầu không?
- Có trường nhạy cảm hoặc dữ liệu cá nhân nào xuất hiện không?
- Thay đổi có đến từ thời gian, random, locale hoặc thứ tự không ổn định không?
- Có khác biệt về status, field hoặc nội dung người dùng thực sự nhìn thấy không?
- Có phải lỗi cũ đang được sửa không?

Golden master là bằng chứng về output tại thời điểm chụp. Nó không phải đặc tả nghiệp vụ hoàn chỉnh.

### 6.1. Chuẩn hóa dữ liệu động trước khi so sánh

Output có thể thay đổi giữa các lần chạy dù hành vi nghiệp vụ không đổi:

- Timestamp lấy từ đồng hồ hệ thống.
- ID tự tăng trong database.
- UUID hoặc token ngẫu nhiên.
- CSRF token và session identifier.
- Thứ tự phần tử không được hợp đồng quy định.
- Nội dung phụ thuộc locale hoặc timezone.
- URL tuyệt đối phụ thuộc host và port test.

Hãy tiêm Clock, generator ID hoặc nguồn random khi cần kiểm soát; dùng fixture cố định; chuẩn hóa đúng trường động trước khi tạo snapshot. Không xóa toàn bộ khác biệt một cách tùy tiện vì có thể che lỗi thực.

### 6.2. Snapshot HTML cần có phạm vi

HTML có thể thay đổi vì whitespace, thuộc tính CSS, thứ tự attribute hoặc markup phục vụ accessibility. Thay vì snapshot toàn bộ trang, có thể:

- Parse HTML và assert các phần tử theo role, label hoặc nội dung.
- Snapshot một component hoặc fragment ổn định.
- Loại bỏ timestamp, nonce và token động bằng bộ normalize rõ ràng.
- Giữ assertion riêng cho form action, link đích và nội dung quan trọng.

Nếu dùng browser test, ưu tiên locator theo accessible role/name thay vì selector CSS phụ thuộc sâu vào cấu trúc DOM.

## 7. Đưa code cũ vào một seam có thể kiểm thử

Legacy code thường khó kiểm thử vì khởi tạo dependency trực tiếp, đọc đồng hồ hệ thống, gọi static API hoặc tạo kết nối trong constructor. Một seam là điểm mà nhóm có thể thay thế hoặc quan sát một dependency mà không phải viết lại toàn bộ module.

Các seam phổ biến:

- Constructor injection cho repository, clock hoặc gateway.
- Interface nhỏ bao quanh API bên ngoài.
- Adapter bọc static call hoặc thư viện cũ.
- Factory cho đối tượng khó khởi tạo.
- HTTP endpoint hoặc application service làm ranh giới tích hợp.

Ví dụ thay vì gọi trực tiếp đồng hồ:

~~~java
public class SubscriptionService {
    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Subscription subscription) {
        return !subscription.expiresAt().isAfter(Instant.now(clock));
    }
}
~~~

Test dùng clock cố định:

~~~java
@Test
void subscriptionExpiresAtTheObservedBoundary() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-19T10:00:00Z"),
            ZoneOffset.UTC
    );
    SubscriptionService service = new SubscriptionService(clock);
    Subscription subscription = subscriptionExpiringAt(
            Instant.parse("2026-11-19T10:00:00Z")
    );

    assertThat(service.isExpired(subscription)).isTrue();
}
~~~

Đưa Clock vào không làm thay đổi quy tắc nghiệp vụ; nó làm thời gian có thể kiểm soát trong test. Với legacy code, hãy tạo seam nhỏ nhất cần thiết để quan sát hành vi, sau đó mới refactor cấu trúc lớn hơn.

## 8. Ghi nhận side effects mà không gọi hệ thống thật

Một request MVC có thể gửi email, phát event, gọi cổng thanh toán, đẩy message hoặc ghi file. Characterization test cần biết tác dụng phụ nào xảy ra, nhưng không nên gửi email thật hoặc tạo giao dịch thật.

Có thể thay dependency bên ngoài bằng fake hoặc test double có khả năng ghi nhận:

~~~java
final class RecordingNotificationGateway implements NotificationGateway {
    private final List<Notification> sent = new ArrayList<>();

    @Override
    public void send(Notification notification) {
        sent.add(notification);
    }

    List<Notification> sentNotifications() {
        return List.copyOf(sent);
    }
}
~~~

Test kiểm tra tác dụng phụ ở mức hợp đồng:

~~~java
@Test
void successfulOrderSendsOneConfirmation() {
    RecordingNotificationGateway notifications =
            new RecordingNotificationGateway();
    PlaceOrderService service = serviceWith(notifications);

    service.execute(validPlaceOrderCommand());

    assertThat(notifications.sentNotifications())
            .hasSize(1)
            .first()
            .extracting(Notification::type)
            .isEqualTo(NotificationType.ORDER_CONFIRMATION);
}
~~~

Test không cần xác nhận một helper private tên buildEmail được gọi. Nó xác nhận người nhận tích hợp nhận một thông báo xác nhận.

Đối với thanh toán, không gọi provider production trong test. Dùng fake gateway hoặc sandbox/test environment được kiểm soát, đồng thời bảo đảm test không thể trỏ nhầm đến tài khoản thật. Với message broker, có thể dùng test container hoặc fake publisher tùy mục tiêu kiểm thử.

### 8.1. Phân biệt side effect trong và ngoài transaction

Nếu ứng dụng gửi email trước khi transaction commit rồi transaction rollback, người dùng có thể nhận thông báo về một đơn không tồn tại. Characterization test có thể phát hiện thứ tự hiện tại, nhưng nhóm cần đánh giá đó có phải hành vi mong muốn không.

Với sự kiện cần phát sau commit, có thể dùng transaction event hoặc outbox. Khi refactor, hãy kiểm tra:

- Sự kiện có được phát khi transaction commit thành công không?
- Có bị phát khi rollback không?
- Retry có thể gửi trùng không?
- Consumer có idempotent không?
- Thông điệp có chứa dữ liệu nhạy cảm không?

## 9. Phân loại hành vi quan sát được

Đây là bước quan trọng để tránh biến mọi hành vi cũ thành hợp đồng không thể thay đổi.

| Nhóm | Cách xử lý |
|---|---|
| Hành vi đúng và đang được sử dụng | Giữ bằng characterization/regression test |
| Hành vi chưa rõ nhưng có người phụ thuộc | Ghi nhận, hỏi chủ sở hữu và giữ tạm trong lúc xác minh |
| Lỗi đã biết | Ghi test mô tả lỗi hoặc tạo test mục tiêu cho cách sửa; không coi lỗi là hợp đồng mong muốn |
| Hành vi không ổn định | Tìm nguồn nondeterminism và kiểm soát trước khi đóng băng |
| Hành vi không còn được sử dụng | Xác minh không có client/luồng nào phụ thuộc rồi cân nhắc loại bỏ |
| Hành vi nguy hiểm về bảo mật | Không bảo tồn chỉ vì nó đang tồn tại; xác định cách sửa và kiểm thử bảo mật |

Ví dụ: nếu endpoint hiện trả thông tin tài khoản của user khác do thiếu authorization, không nên tạo snapshot coi dữ liệu đó là kết quả chuẩn. Hãy ghi nhận lỗ hổng, tạo test thể hiện quyền truy cập mong muốn và sửa theo quyết định bảo mật.

Nếu response hiện có field legacy mà client bên ngoài đang sử dụng, cần xác minh usage trước khi xóa. Một field không được tài liệu hóa vẫn có thể là hợp đồng thực tế.

## 10. Xử lý nondeterminism và flaky behavior

Một test chỉ hữu ích nếu cùng điều kiện có thể tạo kết quả lặp lại. Ứng dụng MVC cũ có thể phụ thuộc:

- Đồng hồ hệ thống hoặc timezone mặc định.
- Locale của máy chạy test.
- Thứ tự record do database trả về khi không có ORDER BY.
- Dữ liệu chia sẻ giữa test.
- Random, UUID hoặc ID tự tăng.
- Cache còn dữ liệu từ lần chạy trước.
- Job nền hoặc message consumer xử lý không đồng bộ.
- Race condition trong cập nhật đồng thời.

Các cách ổn định:

1. Dùng Clock.fixed cho logic phụ thuộc thời gian.
2. Thiết lập locale/timezone trong test nếu thuộc hợp đồng.
3. Sắp xếp kết quả chỉ khi thứ tự là yêu cầu; nếu không, so sánh tập dữ liệu.
4. Tạo dữ liệu riêng cho mỗi test và cleanup rõ ràng.
5. Dùng queue giả hoặc chờ điều kiện có timeout thay cho sleep cố định.
6. Tắt hoặc kiểm soát scheduler trong test slice.
7. Cô lập cache và database giữa test.
8. Với concurrency, dùng barrier/latch để tạo tình huống có thể tái hiện.

Không dùng retry test như cách che một race condition chưa được hiểu. Nếu test chỉ pass khi chạy lại, hãy tìm nguồn không ổn định trước khi coi baseline là đáng tin.

## 11. Characterization test cho dữ liệu và transaction

Khi refactor Model hoặc repository, response HTTP có thể không đổi nhưng dữ liệu được lưu khác đi. Cần ghi nhận các hậu điều kiện quan trọng:

- Bản ghi nào được tạo hoặc cập nhật?
- Trạng thái aggregate sau thao tác là gì?
- Có bản ghi phụ, audit entry hoặc outbox event nào không?
- Khi lỗi xảy ra, thay đổi nào được rollback?
- Ràng buộc unique hoặc quan hệ có tiếp tục được bảo vệ không?

Ví dụ:

~~~java
@SpringBootTest
class OrderPersistenceCharacterizationTest {
    @Autowired
    PlaceOrderUseCase placeOrder;

    @Autowired
    OrderRepository orders;

    @Test
    void successfulPlacementPersistsOnePlacedOrder() {
        PlaceOrderResult result =
                placeOrder.execute(validPlaceOrderCommand());

        Order saved = orders.findById(result.orderId()).orElseThrow();

        assertThat(saved.status()).isEqualTo(OrderStatus.PLACED);
        assertThat(saved.lines()).hasSize(1);
        assertThat(saved.customerId()).isEqualTo(7L);
    }
}
~~~

Test này cần database fixture cô lập và cleanup rõ ràng. Có thể dùng transaction rollback cho một số integration test, nhưng không giả định rollback bao phủ mọi thao tác async, thread khác hoặc hệ thống ngoài. Với test qua HTTP, xác định rõ transaction được mở ở test hay ở request để tránh đọc dữ liệu trước khi commit.

## 12. Tách test đặc trưng khỏi test mục tiêu mới

Khi refactor, có thể phát hiện một hành vi hiện tại không còn phù hợp. Không nên âm thầm sửa expected value trong characterization test rồi mất dấu quyết định.

Một cách làm rõ ràng:

1. Giữ test cũ mô tả hành vi đã quan sát và đánh dấu nó là hành vi cần thay đổi.
2. Viết test mục tiêu mô tả hành vi mới theo yêu cầu.
3. Sửa implementation để test mới pass.
4. Xóa hoặc thay thế characterization test cũ sau khi xác nhận migration hoàn tất.
5. Cập nhật tài liệu hợp đồng hoặc ghi chú thay đổi nếu client bị ảnh hưởng.

Ví dụ endpoint cũ trả 200 với body rỗng khi không tìm thấy tài nguyên, nhưng hợp đồng mới yêu cầu 404. Hãy viết test cho 404 trước khi thay đổi. Sau khi migration hoàn tất, loại bỏ assertion cũ khỏi bộ regression suite; không giữ hai kết quả mâu thuẫn trong cùng một hợp đồng.

## 13. Dùng differential testing khi có hai implementation

Nếu đang thay một service cũ bằng implementation mới, có thể chạy cùng một bộ input qua cả hai và so sánh kết quả. Đây là differential testing.

~~~java
@ParameterizedTest
@MethodSource("orderCases")
void newImplementationMatchesApprovedLegacyBehavior(OrderCase input) {
    OrderResult oldResult = legacyService.execute(input.command());
    OrderResult newResult = refactoredService.execute(input.command());

    assertThat(newResult).usingRecursiveComparison()
            .isEqualTo(oldResult);
}
~~~

Ví dụ giả định hai implementation có thể chạy độc lập và kết quả đã được chuẩn hóa. Không so sánh trực tiếp object chứa timestamp, ID ngẫu nhiên hoặc field kỹ thuật nếu chúng không thuộc hành vi cần giữ. Với side effect, dùng fake gateway riêng cho từng implementation và so sánh loại/số lượng/tác dụng có ý nghĩa.

Differential test rất hữu ích khi thay thuật toán tính toán, query hoặc mapping. Tuy nhiên, implementation cũ không phải oracle tuyệt đối: nếu nó có bug, hai bản cùng trả kết quả sai vẫn làm test pass. Hãy dùng các trường hợp đã được nghiệp vụ xác nhận để bổ sung test độc lập.

## 14. Dùng dữ liệu production một cách an toàn

Dữ liệu thực tế có thể giúp phát hiện các trường hợp biên mà fixture tự tạo bỏ sót. Nhưng không nên sao chép dữ liệu cá nhân hoặc bí mật từ production vào test repository.

Ưu tiên:

- Fixture tổng hợp mô phỏng các trạng thái quan trọng.
- Dữ liệu đã ẩn danh và được phép sử dụng.
- Chỉ giữ trường cần thiết cho hành vi đang kiểm tra.
- Loại bỏ token, mật khẩu, email, số điện thoại và định danh nhạy cảm.
- Không đưa response production nguyên vẹn vào snapshot được commit.
- Không chạy characterization test có side effect ghi dữ liệu lên production.

Nếu cần tái hiện một lỗi production, hãy tạo fixture tối thiểu đã làm sạch, giữ lại cấu trúc và điều kiện gây lỗi nhưng thay dữ liệu nhận dạng.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Snapshot toàn bộ ứng dụng ngay từ đầu | Baseline lớn, khó review và nhiều khác biệt nhiễu | Bắt đầu theo use case và ranh giới |
| Coi mọi hành vi cũ là đúng | Đóng băng bug và lỗ hổng | Phân loại trước khi giữ |
| Assert tên method và thứ tự helper | Test hỏng khi refactor không đổi hành vi | Assert response, state và side effect |
| Chỉ kiểm tra status code | Có thể bỏ sót dữ liệu sai hoặc side effect trùng | Kiểm tra các field và hậu điều kiện quan trọng |
| Dùng snapshot không normalize | Test flaky do timestamp, ID hoặc token | Chuẩn hóa trường động có chủ đích |
| Tự động accept snapshot mới | Che thay đổi ngoài ý muốn | Review diff và lý do |
| Gọi dịch vụ thật trong test | Gửi email/thanh toán hoặc phụ thuộc mạng | Fake, stub hoặc sandbox được kiểm soát |
| Chia sẻ database/cache giữa test | Test phụ thuộc thứ tự chạy | Cô lập fixture và cleanup |
| Dùng production data chưa ẩn danh | Rò rỉ dữ liệu nhạy cảm | Dùng dữ liệu tổng hợp hoặc đã làm sạch |
| Xóa test cũ ngay khi refactor | Mất bằng chứng hành vi trước đó | Giữ test cho đến khi thay đổi được chấp thuận |
| Retry test flaky | Che race hoặc nondeterminism | Tìm và loại bỏ nguồn không ổn định |

## 16. Quy trình áp dụng trong một đợt refactor MVC

Một kế hoạch thực tế cho một use case:

**Trước refactor**

- Ghi nhận route, request, principal và dữ liệu ban đầu.
- Chạy các trường hợp thành công, validation lỗi, không tìm thấy và không đủ quyền.
- Ghi lại response contract và hậu điều kiện database.
- Ghi nhận side effect qua fake hoặc sandbox.
- Phân loại hành vi cần giữ và hành vi cần thay đổi.

**Trong refactor**

- Thay đổi từng ranh giới nhỏ: Controller, application service, domain model, repository hoặc View.
- Chạy characterization suite sau mỗi bước.
- Nếu có diff, xác định nguyên nhân trước khi cập nhật baseline.
- Giữ test ở mức hợp đồng, tránh sửa test chỉ để phù hợp cấu trúc mới.

**Sau refactor**

- Chạy lại toàn bộ test liên quan.
- Bổ sung test cho hành vi mới hoặc lỗi đã được sửa.
- Kiểm tra response và side effect với dữ liệu đại diện.
- Xác nhận các client/tích hợp không bị thay đổi ngoài kế hoạch.
- Xóa baseline cũ chỉ khi hành vi cũ đã được thay thế có chủ đích.

## 17. Checklist review characterization test

Trước khi dùng test làm đường cơ sở cho refactor, hãy xác nhận:

- Test mô tả một hành vi có thể quan sát được không?
- Đã ghi rõ request, user/tenant, trạng thái và fixture ban đầu chưa?
- Assertion có bao phủ status, body/View, state hoặc side effect quan trọng không?
- Test có phụ thuộc private method, tên biến hoặc thứ tự gọi nội bộ không?
- Có dữ liệu động cần kiểm soát hoặc normalize không?
- Có side effect nào đang gọi dịch vụ thật không?
- Test có thể chạy độc lập và lặp lại không?
- Hành vi đã được phân loại là cần giữ, lỗi cần sửa hay chưa rõ chưa?
- Snapshot/golden master có phạm vi nhỏ và diff dễ review không?
- Có test mục tiêu mới cho hành vi cần thay đổi không?
- Dữ liệu fixture có được làm sạch và không chứa bí mật không?

## 18. Kết luận

Kiểm thử đặc trưng tạo một đường cơ sở thực tế cho việc cải tiến ứng dụng MVC. Bằng cách ghi nhận request, response, trạng thái nghiệp vụ, dữ liệu lưu trữ và tác dụng phụ ở những ranh giới có ý nghĩa, nhóm có thể refactor Controller, Model, View hoặc persistence mà vẫn nhận biết được thay đổi ngoài ý muốn.

Giá trị của characterization test nằm ở việc làm rõ điều hệ thống đang làm trước khi quyết định thay đổi. Hãy giữ những hành vi đã được xác nhận là cần thiết, đánh dấu và sửa lỗi đã biết bằng test mục tiêu, kiểm soát dữ liệu động và review mọi thay đổi baseline. Khi đó, kiểm thử trở thành công cụ giúp hiểu hệ thống cũ và cải tiến nó có kiểm soát, thay vì một bản chụp vô điều kiện của mọi lỗi đang tồn tại.
