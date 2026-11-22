# Thiết kế mã kiểm thử, dữ liệu và các lớp hỗ trợ có thể duy trì

Mã kiểm thử là một phần của sản phẩm kỹ thuật. Nó cần được đọc, sửa, chạy và mở rộng trong suốt vòng đời hệ thống. Khi kiểm thử có cấu trúc khó hiểu, dữ liệu phụ thuộc lẫn nhau hoặc lớp hỗ trợ che giấu quá nhiều hành vi, mỗi thay đổi nhỏ có thể làm tăng chi phí bảo trì và khiến nhóm mất niềm tin vào kết quả.

Thiết kế có thể duy trì bắt đầu từ ba thành phần liên kết với nhau:

- **Mã kiểm thử:** diễn đạt rõ hành vi cần xác minh, điều kiện đầu vào và kết quả mong đợi.
- **Dữ liệu kiểm thử:** tạo đúng trạng thái cần thiết, có thể tái tạo và không gây phụ thuộc giữa các lần chạy.
- **Các lớp hỗ trợ:** cung cấp cách tạo dữ liệu, thao tác với hệ thống và quan sát kết quả mà không che khuất mục tiêu của kiểm thử.

Một bộ kiểm thử tốt không nhất thiết có nhiều abstraction hoặc framework riêng. Nó cần đủ cấu trúc để tránh lặp lại công việc, nhưng vẫn giữ được mối liên hệ trực tiếp giữa tên kiểm thử, hành vi nghiệp vụ và assertion. Mỗi lớp hỗ trợ cần có mục đích rõ, phạm vi trách nhiệm nhỏ và cách sử dụng nhất quán.

## 1. Nguyên tắc thiết kế mã kiểm thử có thể duy trì

Mã kiểm thử cần giúp người đọc nhanh chóng trả lời ba câu hỏi: điều kiện nào đang được thiết lập, hành động nào được kiểm tra và điều gì chứng minh hành vi đúng.

### Diễn đạt hành vi thay vì chi tiết triển khai

Tên kiểm thử và cấu trúc nội dung nên mô tả hành vi quan sát được. Ví dụ, **rejectsOrderWhenRequestedQuantityExceedsAvailableStock** nói rõ điều kiện và kết quả. Một tên như **testMethod3** hoặc **testSave** không cho biết lý do kiểm thử tồn tại.

Ưu tiên mô tả quy tắc nghiệp vụ thay vì tên phương thức nội bộ. Nếu một kiểm thử chỉ đạt khi gọi đúng một hàm private hoặc phụ thuộc vào thứ tự gọi nội bộ không phải hợp đồng của thành phần, nó có thể trở nên mong manh khi thiết kế được cải tiến.

### Mỗi kiểm thử nên có một mục tiêu chính

Một kiểm thử có thể xác minh nhiều assertion liên quan đến cùng một hành vi. Tuy nhiên, nếu nó đồng thời kiểm tra tạo đơn, thanh toán, gửi email, cập nhật kho và báo cáo, khi thất bại sẽ khó xác định vấn đề nằm ở đâu.

Hãy chia kiểm thử theo hành vi có ý nghĩa. Giữ những assertion cần thiết để xác minh đầy đủ hành vi đó, nhưng tránh gom nhiều quy tắc độc lập vào một kịch bản dài.

### Giữ phần thiết lập dễ hiểu

Thiết lập dữ liệu có thể chiếm nhiều dòng hơn assertion, nhưng người đọc vẫn cần biết vì sao dữ liệu đó quan trọng. Dùng tên biến mô tả vai trò, giá trị và trạng thái. Tránh các biến như a, x1, obj2 trong kịch bản nghiệp vụ.

### Ưu tiên tính xác định và khả năng tái hiện

Cùng một mã kiểm thử, dữ liệu và điều kiện môi trường nên tạo ra cùng một kết quả. Tránh phụ thuộc vào thời gian hiện tại, thứ tự ngẫu nhiên, dữ liệu dùng chung hoặc dịch vụ bên ngoài không kiểm soát được nếu không có lý do rõ ràng.

### Chỉ trừu tượng hóa khi tạo ra lợi ích

Một helper tốt làm giảm lặp lại và làm rõ ý định. Một helper kém khiến người đọc phải mở nhiều lớp mới hiểu kiểm thử đang làm gì. Trước khi tạo lớp hỗ trợ, hãy xác định phần nào thực sự lặp lại hoặc cần che giấu chi tiết kỹ thuật.

## 2. Cấu trúc một kiểm thử rõ ràng

Một cấu trúc phổ biến là Arrange–Act–Assert:

1. **Arrange:** chuẩn bị dữ liệu, trạng thái và phụ thuộc.
2. **Act:** thực hiện hành động cần kiểm tra.
3. **Assert:** xác minh kết quả quan sát được.

Ví dụ với JUnit 5:

~~~java
@Test
void rejectsOrderWhenRequestedQuantityExceedsAvailableStock() {
    Inventory inventory = new Inventory("SKU-42", 2);
    OrderService service = new OrderService(inventory);

    OrderResult result = service.placeOrder("SKU-42", 3);

    assertEquals(OrderStatus.REJECTED, result.status());
    assertEquals(2, inventory.availableQuantity("SKU-42"));
}
~~~

Phần Arrange tạo tồn kho có hai sản phẩm. Phần Act yêu cầu ba sản phẩm. Phần Assert xác minh đơn bị từ chối và tồn kho không bị thay đổi. Người đọc có thể hiểu mục tiêu mà không cần biết chi tiết triển khai của OrderService.

### Đặt tên kiểm thử theo điều kiện và kết quả

Có thể dùng một trong các mẫu:

- doesXWhenY
- returnsXForY
- rejectsXWhenY
- transitionsFromXToYWhenZ
- givenX_whenY_thenZ

Không cần ép mọi nhóm dùng cùng một mẫu tên nếu quy ước hiện tại đã rõ. Điều quan trọng là tên có ý nghĩa, nhất quán và không phụ thuộc vào số thứ tự.

### Tránh kiểm thử phụ thuộc thứ tự

Mỗi kiểm thử nên có thể chạy độc lập. Không nên yêu cầu kiểm thử A chạy trước để tạo dữ liệu cho kiểm thử B. Nếu một bộ kiểm thử chỉ đạt khi chạy theo một thứ tự cụ thể, trạng thái dùng chung hoặc cleanup có thể đang sai.

### Giữ assertion có ý nghĩa

Assertion nên kiểm tra điều kiện cần thiết, không chỉ kiểm tra rằng một đối tượng không null hoặc một danh sách không rỗng khi yêu cầu cần xác minh nội dung cụ thể.

Ví dụ, thay vì chỉ xác minh đơn hàng tồn tại, hãy kiểm tra mã khách hàng, tổng tiền, trạng thái và các thuộc tính liên quan đến quy tắc đang kiểm tra. Tuy nhiên, không cần kiểm tra mọi trường của đối tượng trong mọi test; hãy tập trung vào kết quả của hành vi.

## 3. Chia sẻ thiết lập mà không che khuất ý định

Thiết lập lặp lại là lý do phổ biến để tạo fixture hoặc helper. Việc chia sẻ nên giảm mã lặp nhưng không làm người đọc mất khả năng nhìn thấy dữ liệu quan trọng.

### Fixture là gì?

Fixture là dữ liệu hoặc trạng thái cần thiết để thực hiện kiểm thử. Fixture có thể gồm đối tượng trong bộ nhớ, bản ghi cơ sở dữ liệu, tệp, cấu hình, tài khoản hoặc môi trường dịch vụ.

Một fixture tốt:

- Có tên mô tả vai trò và trạng thái.
- Chỉ chứa dữ liệu cần thiết cho kịch bản.
- Có thể tạo lại với kết quả ổn định.
- Không phụ thuộc vào thứ tự kiểm thử.
- Có cách dọn dẹp hoặc cô lập phù hợp.
- Cho phép thay đổi những thuộc tính quan trọng của kịch bản.

### Dùng factory cho dữ liệu mặc định hợp lệ

Factory tạo đối tượng với giá trị mặc định hợp lý. Người viết test chỉ cần chỉ rõ những thuộc tính liên quan.

~~~java
final class CustomerFactory {
    static Customer aValidCustomer() {
        return new Customer(
            "customer-100",
            "customer@example.test",
            CustomerStatus.ACTIVE
        );
    }
}
~~~

Trong kiểm thử:

~~~java
@Test
void allowsActiveCustomerToPlaceOrder() {
    Customer customer = CustomerFactory.aValidCustomer();

    OrderResult result = orderService.placeOrder(customer, validCart());

    assertEquals(OrderStatus.CREATED, result.status());
}
~~~

Tên aValidCustomer giúp người đọc hiểu dữ liệu cơ sở. Nếu email hoặc trạng thái là điều kiện quan trọng, nên thể hiện trực tiếp trong test hoặc dùng một factory có tham số rõ ràng.

### Dùng Builder khi dữ liệu có nhiều thuộc tính tùy chọn

Builder phù hợp khi đối tượng có nhiều trường và mỗi kiểm thử chỉ cần thay đổi một vài trường. Builder nên có giá trị mặc định hợp lệ và tên phương thức dễ hiểu.

~~~java
Customer customer = CustomerBuilder.aCustomer()
    .withStatus(CustomerStatus.SUSPENDED)
    .withEmail("suspended@example.test")
    .build();
~~~

Tránh tạo builder có hàng chục phương thức không rõ ý nghĩa hoặc mặc định ẩn chứa điều kiện quan trọng. Nếu một test cần dữ liệu bất thường, tên builder và các thuộc tính thay đổi phải làm rõ điều đó.

### Object Mother và giới hạn sử dụng

Object Mother là nơi cung cấp một số đối tượng mẫu có ý nghĩa nghiệp vụ, chẳng hạn anActiveCustomer() hoặc anOverdueInvoice(). Cách này hữu ích khi các mẫu được dùng rộng rãi và có tên ổn định.

Nhược điểm là thư viện mẫu có thể phát triển quá lớn, chứa nhiều trường hợp gần giống nhau hoặc che giấu giá trị cụ thể. Chỉ duy trì các mẫu thực sự phổ biến; với trường hợp riêng, dùng factory hoặc builder để diễn đạt trực tiếp.

## 4. Thiết kế dữ liệu kiểm thử có tính độc lập

Dữ liệu dùng chung là một nguyên nhân lớn gây kiểm thử không ổn định. Một test cập nhật bản ghi có thể làm test khác thất bại; một test xóa tài khoản có thể khiến lần chạy tiếp theo không còn dữ liệu.

### Tạo dữ liệu riêng cho từng kiểm thử

Khi có thể, mỗi test nên tạo dữ liệu riêng với định danh duy nhất. Có thể dùng UUID, tiền tố theo test hoặc cơ chế cấp phát định danh của môi trường.

Không nên dựa vào một tài khoản hoặc bản ghi cố định mà nhiều test cùng sửa đổi. Nếu phải dùng dữ liệu dùng chung vì chi phí tạo cao, cần bảo đảm test chỉ đọc hoặc có cơ chế khóa và khôi phục được kiểm soát.

### Không phụ thuộc vào thứ tự hoặc kết quả lần chạy trước

Trước khi chạy, trạng thái cần được thiết lập rõ ràng. Sau khi chạy, dữ liệu phải được xóa hoặc cách ly để lần chạy sau không bị ảnh hưởng.

Với cơ sở dữ liệu thử nghiệm, có thể dùng transaction rollback, schema riêng, database riêng hoặc tạo/xóa bản ghi theo từng test. Chọn cách phù hợp với kiến trúc và hành vi cần kiểm tra. Transaction rollback không phù hợp nếu hệ thống thực hiện commit qua nhiều kết nối hoặc phát sự kiện ra ngoài transaction.

### Sử dụng dữ liệu tổng hợp và an toàn

Tránh sao chép dữ liệu cá nhân hoặc bí mật từ môi trường thật vào kiểm thử nếu chưa có biện pháp bảo vệ và cơ sở phù hợp. Dữ liệu tổng hợp nên đủ thực tế để kiểm tra định dạng, quan hệ và quy tắc nghiệp vụ nhưng không chứa thông tin có thể nhận diện người thật.

### Dùng thời gian cố định khi kiểm thử quy tắc thời gian

Nếu hành vi phụ thuộc vào ngày hiện tại, hạn dùng hoặc thời điểm hết hạn, hãy tiêm một Clock hoặc nguồn thời gian có thể điều khiển thay vì gọi trực tiếp thời gian hệ thống.

~~~java
class SubscriptionService {
    private final Clock clock;

    SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Subscription subscription) {
        return subscription.expiresAt().isBefore(Instant.now(clock));
    }
}
~~~

Kiểm thử có thể dùng đồng hồ cố định:

~~~java
@Test
void marksSubscriptionExpiredAfterItsExpiryTime() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-05-10T10:00:00Z"),
        ZoneOffset.UTC
    );
    SubscriptionService service = new SubscriptionService(clock);
    Subscription subscription =
        new Subscription(Instant.parse("2026-05-10T09:59:59Z"));

    assertTrue(service.isExpired(subscription));
}
~~~

Cách này tránh phụ thuộc thời điểm chạy và giúp kiểm tra chính xác ranh giới thời gian, múi giờ hoặc ngày nhuận.

## 5. Quản lý vòng đời dữ liệu và cleanup

Dữ liệu kiểm thử cần được tạo, sử dụng và dọn dẹp theo cách có thể dự đoán. Cleanup không nên là một thao tác tùy chọn được thực hiện khi người viết nhớ đến.

### Thiết lập và dọn dẹp ở đúng phạm vi

JUnit 5 cung cấp @BeforeEach và @AfterEach cho công việc cần chạy trước hoặc sau mỗi test. Dùng chúng cho tài nguyên thực sự được chia sẻ trong phạm vi lớp hoặc test.

~~~java
class CustomerRepositoryTest {
    private TestDatabase database;
    private CustomerRepository repository;

    @BeforeEach
    void setUp() {
        database = TestDatabase.start();
        repository = new CustomerRepository(database.dataSource());
    }

    @AfterEach
    void tearDown() {
        database.close();
    }
}
~~~

Nếu tài nguyên cần được dọn ngay cả khi quá trình thiết lập có thể thất bại, hoặc cần quản lý nhiều tài nguyên, hãy cân nhắc try-with-resources hoặc cơ chế lifecycle có bảo đảm.

### Chọn đúng phạm vi chia sẻ

- **Theo test:** phù hợp với dữ liệu có thể thay đổi và cần độc lập cao.
- **Theo lớp:** phù hợp với tài nguyên khởi tạo tốn kém nhưng phải bảo đảm test không làm thay đổi trạng thái dùng chung.
- **Theo bộ kiểm thử:** chỉ dùng khi có lý do rõ và cơ chế khôi phục đáng tin cậy.
- **Theo môi trường:** phù hợp với dịch vụ hoặc cơ sở dữ liệu dùng chung, nhưng cần cách ly dữ liệu và kiểm soát truy cập.

Phạm vi chia sẻ càng rộng thì nguy cơ test ảnh hưởng lẫn nhau càng cao. Tối ưu thời gian khởi tạo không nên làm mất tính xác định.

### Dọn dẹp theo cách an toàn

Cleanup cần xử lý cả trường hợp test thất bại. Với tài nguyên hệ thống như tệp, container, socket hoặc tiến trình, dùng cơ chế đóng tài nguyên rõ ràng. Với dữ liệu cơ sở dữ liệu, chỉ xóa những bản ghi do test tạo ra, tránh thao tác xóa rộng dựa trên điều kiện không đủ chặt.

Không nên để cleanup che giấu lỗi. Nếu test thất bại vì trạng thái không đúng, việc xóa dữ liệu ngay có thể làm mất bằng chứng cần điều tra. Có thể lưu log hoặc snapshot cần thiết trước khi dọn.

## 6. Thiết kế các lớp hỗ trợ theo trách nhiệm

Các lớp hỗ trợ làm cho kiểm thử dễ đọc hơn khi chúng gom một nhóm thao tác kỹ thuật có ý nghĩa. Tuy nhiên, một lớp hỗ trợ không nên trở thành nơi chứa toàn bộ logic kiểm thử.

Có thể phân chia thành các lớp sau:

- **Factory hoặc Builder:** tạo dữ liệu và đối tượng.
- **Fixture hoặc Test Data Manager:** quản lý trạng thái và vòng đời dữ liệu.
- **Client hoặc Gateway kiểm thử:** giao tiếp với API hoặc phụ thuộc.
- **Page Object hoặc Screen Object:** đóng gói thao tác và bộ định vị trên giao diện.
- **Assertion Helper:** diễn đạt các xác minh lặp lại có ý nghĩa nghiệp vụ.
- **Environment/Configuration Helper:** cung cấp cấu hình và tài nguyên kiểm thử.
- **Clock hoặc Random Provider:** kiểm soát thời gian và tính ngẫu nhiên.
- **Stub/Mock/Fake:** thay thế phụ thuộc theo mục tiêu kiểm thử.

Tên lớp nên phản ánh vai trò, chẳng hạn OrderTestData, PaymentApiClient hoặc OrderAssertions. Tránh những tên chung như Utils, CommonHelper hoặc BaseTest chứa nhiều chức năng không liên quan.

### Một lớp nên có một lý do thay đổi chính

Nếu một lớp vừa tạo khách hàng, gọi API, kiểm tra cơ sở dữ liệu, tạo báo cáo và xóa dữ liệu, nó đang gánh quá nhiều trách nhiệm. Khi một quy tắc thay đổi, nhiều test có thể bị ảnh hưởng theo cách khó dự đoán.

Tách lớp theo ranh giới hợp lý giúp thay đổi cục bộ và làm rõ quyền sở hữu. Tuy nhiên, không nên tạo lớp cho từng dòng lệnh đơn giản. Mục tiêu là giảm độ phức tạp tổng thể, không tăng số lượng tệp.

## 7. Tạo lớp hỗ trợ API và kiểm thử tích hợp

Khi kiểm thử API, client hỗ trợ nên đóng gói cách thiết lập request, xác thực và phân tích response. Nhưng assertion về nghiệp vụ nên nằm ở test hoặc helper có tên thể hiện rõ hành vi.

Ví dụ:

~~~java
final class OrdersApiClient {
    private final HttpClient httpClient;
    private final URI baseUri;
    private final String accessToken;

    OrdersApiClient(HttpClient httpClient, URI baseUri, String accessToken) {
        this.httpClient = httpClient;
        this.baseUri = baseUri;
        this.accessToken = accessToken;
    }

    HttpResponse<String> createOrder(String requestBody)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(baseUri.resolve("/orders"))
            .header("Authorization", "Bearer " + accessToken)
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .build();

        return httpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );
    }
}
~~~

Kiểm thử:

~~~java
@Test
void createsOrderForValidRequest() throws Exception {
    String request = """
        {"customerId":"customer-100","sku":"SKU-42","quantity":1}
        """;

    HttpResponse<String> response = ordersApi.createOrder(request);

    assertEquals(201, response.statusCode());
    assertTrue(response.body().contains("\"status\":\"CREATED\""));
}
~~~

Ví dụ tối giản này minh họa ranh giới giữa client và test. Trong hệ thống thực tế, nên dùng JSON parser hoặc DTO để xác minh cấu trúc và giá trị thay vì tìm chuỗi trong response. Client không nên tự động coi mọi phản hồi là thành công hoặc giấu mã trạng thái và nội dung lỗi.

### Không biến client thành lớp nghiệp vụ

Một OrdersApiClient nên gửi request và trả kết quả. Nếu nó tự quyết định đơn hàng nào hợp lệ, tự tạo nhiều đối tượng nghiệp vụ hoặc tự khẳng định test đã đạt, trách nhiệm trở nên khó phân biệt.

Có thể tạo helper cấp cao hơn như OrderWorkflow nếu nhiều test thực sự cần thực hiện cùng một hành trình. Nhưng helper cần cho phép người đọc nhìn thấy các điểm quan trọng và không được che giấu assertion cần thiết.

## 8. Thiết kế Page Object cho kiểm thử giao diện

Page Object đóng gói bộ định vị và thao tác trên một trang hoặc thành phần giao diện. Nó giúp giảm lặp lại khi giao diện thay đổi và giữ test tập trung vào mục tiêu người dùng.

Ví dụ khái niệm:

~~~java
final class LoginPage {
    private final WebDriver driver;

    LoginPage(WebDriver driver) {
        this.driver = driver;
    }

    void enterEmail(String email) {
        driver.findElement(By.id("email")).sendKeys(email);
    }

    void enterPassword(String password) {
        driver.findElement(By.id("password")).sendKeys(password);
    }

    void submit() {
        driver.findElement(By.id("login")).click();
    }

    String errorMessage() {
        return driver.findElement(By.cssSelector("[role='alert']")).getText();
    }
}
~~~

Test có thể diễn đạt hành vi:

~~~java
@Test
void showsErrorForInvalidCredentials() {
    LoginPage loginPage = new LoginPage(driver);

    loginPage.enterEmail("person@example.test");
    loginPage.enterPassword("incorrect-password");
    loginPage.submit();

    assertEquals("Thông tin đăng nhập không hợp lệ",
                 loginPage.errorMessage());
}
~~~

### Giữ Page Object ở đúng ranh giới

Page Object nên cung cấp thao tác và thông tin quan sát của trang. Tránh đặt mọi assertion nghiệp vụ, điều hướng toàn bộ ứng dụng và dữ liệu kiểm thử vào một lớp duy nhất.

Không nên tạo một BasePage khổng lồ chứa các phương thức cho mọi trang. Dùng thành phần dùng chung khi có hành vi thực sự chung và ổn định.

Đối với giao diện động, cần chờ điều kiện cụ thể thay vì dùng sleep cố định. Chờ phần tử hiển thị, trạng thái tải kết thúc hoặc điều kiện nghiệp vụ được phản ánh trên trang sẽ ổn định hơn chờ một số giây tùy ý.

## 9. Dùng Test Double đúng mục đích

Test double là đối tượng thay thế một phụ thuộc thật trong kiểm thử. Các dạng phổ biến gồm:

- **Dummy:** được truyền vào nhưng không tham gia hành vi cần kiểm tra.
- **Stub:** trả về dữ liệu đã định trước.
- **Spy:** ghi nhận cách nó được sử dụng.
- **Mock:** cho phép xác minh tương tác mong đợi.
- **Fake:** triển khai đơn giản nhưng có hành vi thực tế, chẳng hạn repository lưu trong bộ nhớ.

Chọn loại phù hợp với câu hỏi cần kiểm tra. Không nên dùng mock cho mọi phụ thuộc vì test có thể chỉ xác minh cách gọi nội bộ thay vì kết quả nghiệp vụ.

### Khi nào nên dùng mock hoặc stub?

Dùng khi cần cô lập thành phần khỏi dịch vụ ngoài, mô phỏng phản hồi lỗi khó tạo hoặc kiểm tra một tương tác có ý nghĩa trong hợp đồng.

Ví dụ, kiểm tra dịch vụ đơn hàng xử lý khi cổng thanh toán từ chối:

~~~java
@Test
void keepsOrderUnpaidWhenPaymentIsDeclined() {
    PaymentGateway gateway = request ->
        PaymentResult.declined("CARD_DECLINED");
    OrderService service = new OrderService(gateway);

    OrderResult result = service.placeOrder(validOrder());

    assertEquals(OrderStatus.PAYMENT_FAILED, result.status());
}
~~~

Ở đây stub mô phỏng phản hồi từ chối. Assertion tập trung vào kết quả nghiệp vụ của dịch vụ đơn hàng.

### Khi nào nên dùng fake hoặc phụ thuộc thật?

Fake hữu ích khi cần hành vi đủ thực tế nhưng không muốn phụ thuộc hạ tầng nặng. Ví dụ, một repository trong bộ nhớ có thể phù hợp cho kiểm thử logic ứng dụng. Tuy nhiên, fake không chứng minh truy vấn SQL, transaction hoặc hành vi của cơ sở dữ liệu thật.

Với rủi ro nằm ở giao tiếp hoặc cấu hình, cần kiểm thử tích hợp với phụ thuộc thật hoặc môi trường tương đương. Mỗi lần dùng test double, hãy ghi rõ phần nào được thay thế và giới hạn của bằng chứng.

### Tránh kiểm tra quá sâu vào chi tiết nội bộ

Nếu test xác minh chính xác một phương thức private được gọi bao nhiêu lần, nó có thể thất bại khi refactor dù hành vi bên ngoài không đổi. Chỉ xác minh tương tác khi tương tác đó là một phần quan trọng của hợp đồng, chẳng hạn không gửi thanh toán lần thứ hai hoặc phát đúng một sự kiện.

## 10. Xây dựng Assertion Helper có ý nghĩa

Khi nhiều test cần xác minh cùng một tập điều kiện nghiệp vụ, assertion helper có thể giúp giảm lặp và làm rõ mục đích.

Ví dụ:

~~~java
final class OrderAssertions {
    static void isPaidOrder(Order order, Money expectedTotal) {
        assertEquals(OrderStatus.PAID, order.status());
        assertEquals(expectedTotal, order.total());
        assertNotNull(order.paidAt());
        assertNotNull(order.paymentReference());
    }
}
~~~

Cách dùng:

~~~java
@Test
void marksOrderPaidAfterSuccessfulPayment() {
    Order order = orderWorkflow.pay(validOrder());

    OrderAssertions.isPaidOrder(order, Money.of("125.00", "USD"));
}
~~~

Helper này hữu ích nếu khái niệm “đơn đã thanh toán hợp lệ” được dùng lặp lại. Nếu mỗi test chỉ cần một assertion đơn giản, gọi assertion trực tiếp có thể dễ đọc hơn.

### Thông báo lỗi cần giúp điều tra

Một assertion helper nên cung cấp thông tin đủ để biết điều kiện nào thất bại. Tránh helper chỉ trả về false hoặc ném lỗi chung chung như “validation failed”. Có thể dùng thông điệp mô tả, giá trị mong đợi và giá trị thực tế.

Không nên xây dựng một ngôn ngữ assertion riêng quá phức tạp. Hãy tận dụng thư viện kiểm thử hiện có và bổ sung helper cho các khái niệm nghiệp vụ thật sự có ích.

## 11. Tổ chức cấu trúc thư mục và phạm vi dùng chung

Cấu trúc thư mục cần giúp nhóm tìm được test, dữ liệu và lớp hỗ trợ liên quan. Có thể tổ chức theo tính năng hoặc theo loại kiểm thử, tùy quy mô dự án.

Ví dụ:

~~~text
src/test/java/
  orders/
    OrderServiceTest.java
    OrderWorkflowTest.java
    OrderTestData.java
    OrderAssertions.java
  payments/
    PaymentServiceTest.java
    PaymentGatewayContractTest.java
    PaymentTestData.java
  support/
    TestClock.java
    DatabaseExtension.java
    ApiTestClient.java
~~~

Với dự án lớn, có thể tách test đơn vị, tích hợp và E2E thành source set hoặc module riêng. Không nên tạo cấu trúc quá sâu khiến việc tìm test khó hơn.

### Đặt lớp hỗ trợ gần nơi sử dụng

Nếu helper chỉ phục vụ một nhóm test, đặt nó gần nhóm đó. Chỉ đưa vào thư mục support chung khi nhiều khu vực thực sự dùng và có hợp đồng ổn định.

Lớp hỗ trợ dùng chung có tác động rộng. Thay đổi một mặc định có thể làm nhiều test thay đổi hành vi. Cần có chủ sở hữu, tài liệu ngắn và kiểm thử cho chính helper khi logic của nó đủ phức tạp.

### Tránh kế thừa chỉ để chia sẻ vài dòng

Kế thừa từ BaseTest có thể tiện nhưng dễ tạo phụ thuộc ẩn: thứ tự setup, biến toàn cục, hook tự động và cleanup khó theo dõi. Ưu tiên composition, extension hoặc helper rõ ràng. Dùng kế thừa khi thực sự có quan hệ và lifecycle chung ổn định.

## 12. Kiểm soát cấu hình và phụ thuộc của bộ kiểm thử

Một bộ kiểm thử có thể không ổn định nếu phụ thuộc vào cấu hình ẩn hoặc phiên bản thư viện không được kiểm soát.

Nên:

- Quản lý phiên bản thư viện kiểm thử trong build file.
- Dùng cấu hình theo môi trường và không hard-code bí mật.
- Tách cấu hình dùng chung khỏi dữ liệu nghiệp vụ của test.
- Kiểm tra cấu hình bắt buộc ngay khi khởi tạo.
- Cung cấp thông báo rõ khi môi trường hoặc phụ thuộc không sẵn sàng.
- Ghi nhận phiên bản dịch vụ và công cụ liên quan khi kết quả phụ thuộc.
- Tránh truy cập Internet hoặc dịch vụ thật trong test đơn vị.
- Giới hạn quyền của tài khoản và tài nguyên kiểm thử.

Nếu một test cần thông tin xác thực, lấy từ cơ chế quản lý bí mật phù hợp và không ghi giá trị đó vào log hoặc thông báo lỗi.

## 13. Làm cho kiểm thử dễ chạy và dễ điều tra

Mã kiểm thử có thể rất tốt nhưng vẫn khó duy trì nếu nhóm không biết chạy một test riêng, không tìm được log hoặc không phân biệt lỗi sản phẩm với lỗi môi trường.

Một bộ kiểm thử dễ vận hành nên có:

- Cách chạy một test hoặc một nhóm test cụ thể.
- Cách chạy toàn bộ test phù hợp với tầng.
- Quy ước đặt tên và phân loại test.
- Thông tin về môi trường và dữ liệu cần thiết.
- Log có định danh tương quan khi gọi nhiều dịch vụ.
- Thông báo lỗi có ngữ cảnh.
- Quy tắc retry rõ ràng và không che giấu flaky test.
- Hướng dẫn cleanup khi test bị dừng giữa chừng.

### Không dùng retry để che giấu tính không ổn định

Chạy lại tự động có thể hữu ích khi hạ tầng có lỗi tạm thời, nhưng nếu test chỉ đạt sau nhiều lần thử, nhóm cần điều tra nguyên nhân. Báo cáo nên giữ lại lần thất bại ban đầu và phân biệt kết quả retry với kết quả ổn định.

### Phân loại test để quản lý thời gian chạy

Có thể dùng tag hoặc nhóm riêng:

- unit: nhanh, cô lập, chạy thường xuyên.
- integration: cần dịch vụ hoặc tài nguyên tích hợp.
- e2e: hành trình xuyên hệ thống, chi phí cao hơn.
- slow: test dài cần lịch chạy riêng.
- flaky-investigation: test đang được điều tra, không nên biến thành nhóm bị bỏ quên.

Tên tag và cơ chế lọc tùy framework. Cần tránh loại bỏ test khỏi pipeline mà không có chủ sở hữu và kế hoạch xử lý.

## 14. Thiết kế để kiểm thử song song an toàn

Khi bộ kiểm thử chạy song song, dữ liệu và tài nguyên dùng chung dễ tạo xung đột.

Cần xem xét:

- Định danh riêng cho mỗi test hoặc worker.
- Schema, database hoặc namespace tách biệt.
- Không dùng biến static có thể thay đổi giữa các test.
- Không ghi vào cùng một tệp hoặc tài khoản dùng chung.
- Port và tài nguyên mạng được cấp phát an toàn.
- Cleanup chỉ xóa tài nguyên do test sở hữu.
- Test không phụ thuộc thứ tự chạy hoặc thời gian thực.
- Test double và fake không chia sẻ trạng thái ngoài ý muốn.

Nếu không thể chạy song song an toàn, hãy giới hạn song song cho nhóm test cụ thể và ghi rõ lý do. Không nên dùng khóa toàn cục cho toàn bộ bộ kiểm thử nếu chỉ một vài test có xung đột; hãy thu hẹp phạm vi đồng bộ.

## 15. Ví dụ tổng hợp: thiết kế bộ kiểm thử cho dịch vụ đơn hàng

Giả sử dịch vụ đơn hàng có các hành vi tạo đơn, tính tổng tiền, hủy đơn và thanh toán. Dịch vụ phụ thuộc vào repository, cổng thanh toán và đồng hồ hệ thống.

### Tách kiểm thử theo mục tiêu

- Kiểm thử đơn vị cho công thức tính tổng, điều kiện hủy và chuyển trạng thái.
- Kiểm thử thành phần cho OrderService với repository và cổng thanh toán giả.
- Kiểm thử tích hợp cho repository thật và hợp đồng với cổng thanh toán sandbox.
- Kiểm thử E2E cho hành trình tạo đơn và thanh toán thành công.

Mỗi tầng có dữ liệu và lớp hỗ trợ phù hợp. Không nên dùng một kịch bản E2E dài để kiểm tra mọi giá trị biên của công thức.

### Dữ liệu và hỗ trợ

- OrderTestData tạo đơn với dữ liệu mặc định hợp lệ.
- OrderBuilder cho phép thay đổi số lượng, trạng thái và tổng tiền.
- TestClock cố định thời gian để kiểm tra hạn hủy.
- FakePaymentGateway trả kết quả có thể điều khiển.
- OrderRepositoryTest dùng cơ sở dữ liệu thử nghiệm riêng.
- OrderAssertions xác minh các bất biến nghiệp vụ quan trọng.

### Ví dụ kiểm thử quy tắc hủy

~~~java
@Test
void rejectsCancellationAfterOrderHasShipped() {
    Order order = OrderBuilder.anOrder()
        .withStatus(OrderStatus.SHIPPED)
        .build();

    CancellationResult result = orderService.cancel(order.id());

    assertEquals(CancellationStatus.REJECTED, result.status());
    assertEquals(OrderStatus.SHIPPED, order.status());
}
~~~

Test thể hiện điều kiện quan trọng ngay trong builder và kiểm tra cả kết quả từ chối lẫn trạng thái không bị thay đổi.

### Ví dụ kiểm thử xử lý thanh toán thất bại

~~~java
@Test
void leavesOrderUnpaidWhenGatewayDeclinesPayment() {
    FakePaymentGateway gateway =
        FakePaymentGateway.alwaysDeclines("CARD_DECLINED");
    OrderService service = new OrderService(repository, gateway, clock);
    Order order = OrderTestData.aPendingOrder();

    PaymentResult result = service.pay(order.id());

    assertEquals(PaymentStatus.DECLINED, result.status());
    assertEquals(OrderStatus.PAYMENT_FAILED,
                 repository.findById(order.id()).orElseThrow().status());
}
~~~

Fake cho phép tạo kết quả từ chối ổn định. Kiểm thử tích hợp riêng cần xác minh hợp đồng và cách dịch vụ giao tiếp với phụ thuộc thật hoặc sandbox.

## 16. Những dấu hiệu cho thấy mã kiểm thử khó bảo trì

Hãy xem xét thiết kế lại khi gặp các dấu hiệu:

- Nhiều test có cùng một khối setup dài nhưng không có fixture rõ.
- Thay đổi một factory làm hàng loạt test không liên quan thất bại.
- Tên test không thể hiện điều kiện hoặc kết quả.
- Test cần chạy theo thứ tự mới đạt.
- Dữ liệu được hard-code và tái sử dụng giữa nhiều test.
- Helper có quá nhiều tham số hoặc hành vi ẩn.
- Assertion nằm sâu trong nhiều lớp và khó biết test đang xác minh điều gì.
- BaseTest chứa nhiều hook, trạng thái và biến dùng chung.
- Test dùng sleep để chờ thay vì chờ điều kiện.
- Test thất bại nhưng log không cho biết dữ liệu hoặc bước gây lỗi.
- Mock quá nhiều khiến test chỉ xác minh cách gọi nội bộ.
- Test flaky bị retry liên tục mà không có kế hoạch xử lý.

Không phải mọi dấu hiệu đều cần một lần refactor lớn. Có thể bắt đầu bằng việc làm rõ tên, tách một fixture, loại bỏ trạng thái dùng chung hoặc bổ sung thông báo assertion.

## 17. Refactor mã kiểm thử một cách an toàn

Khi refactor, mục tiêu là cải thiện khả năng đọc và bảo trì mà không làm thay đổi ý nghĩa kiểm chứng.

Một quy trình phù hợp:

1. Chọn nhóm test có vấn đề cụ thể.
2. Xác định hành vi và assertion cần được giữ nguyên.
3. Ghi nhận thời gian chạy và các phụ thuộc.
4. Tách dữ liệu lặp thành factory hoặc builder có tên rõ.
5. Tách thao tác kỹ thuật khỏi assertion nghiệp vụ.
6. Loại bỏ trạng thái dùng chung hoặc phụ thuộc thứ tự.
7. Chạy lại test riêng, nhóm test liên quan và pipeline phù hợp.
8. So sánh kết quả, thời gian chạy và khả năng điều tra lỗi.
9. Cập nhật hướng dẫn hoặc quy ước nếu cách dùng thay đổi.

Không nên tạo abstraction tổng quát trước khi hiểu các trường hợp sử dụng. Hai đoạn mã trông giống nhau có thể đại diện cho hai quy tắc nghiệp vụ khác nhau. Chỉ hợp nhất khi ý nghĩa và trách nhiệm thực sự giống nhau.

## 18. Quy ước và tài liệu cho lớp hỗ trợ

Các lớp hỗ trợ dùng chung cần có quy ước để tránh mỗi người sử dụng theo một cách.

Nên ghi ngắn gọn:

- Mục đích và phạm vi sử dụng.
- Giá trị mặc định được tạo ra.
- Những thuộc tính nào bắt buộc phải chỉ định.
- Cách tạo dữ liệu riêng và cleanup.
- Những phụ thuộc bên ngoài.
- Cách xử lý lỗi và tài nguyên.
- Ví dụ sử dụng trong một test.
- Người hoặc nhóm sở hữu khi helper được dùng rộng.

Không cần tài liệu dài cho mọi factory nhỏ. Nhưng helper có lifecycle, cấu hình hoặc side effect cần được giải thích rõ.

## 19. Danh sách rà soát chất lượng mã kiểm thử

Trước khi hợp nhất một thay đổi liên quan đến test, có thể rà soát:

| Khía cạnh | Câu hỏi |
|---|---|
| Ý định | Tên và nội dung test có nói rõ hành vi cần kiểm chứng không? |
| Cấu trúc | Arrange, Act và Assert có dễ nhận ra không? |
| Tính độc lập | Test có thể chạy riêng và chạy song song an toàn không? |
| Dữ liệu | Dữ liệu có riêng, ổn định và phù hợp với tình huống không? |
| Cleanup | Tài nguyên và dữ liệu có được dọn an toàn khi thất bại không? |
| Assertion | Kết quả có đủ cụ thể để phát hiện hành vi sai không? |
| Abstraction | Factory, builder và helper có giảm độ phức tạp không? |
| Test double | Mock hoặc fake có phù hợp với câu hỏi cần kiểm tra không? |
| Khả năng điều tra | Khi thất bại, log và thông báo có đủ ngữ cảnh không? |
| Vòng đời | Có chủ sở hữu và kế hoạch cập nhật khi yêu cầu thay đổi không? |

Danh sách này là công cụ hỗ trợ rà soát, không phải yêu cầu phải tạo thêm lớp cho mọi test. Nếu một test nhỏ đã rõ và độc lập, giữ nguyên cấu trúc đơn giản thường là lựa chọn tốt.

## 20. Những sai lầm thường gặp

- **Tạo framework kiểm thử quá sớm:** abstraction chưa được kiểm chứng làm tăng độ phức tạp.
- **Dùng helper chung cho mọi thứ:** trách nhiệm bị trộn lẫn và hành vi ẩn khó theo dõi.
- **Dùng dữ liệu cố định dùng chung:** test ảnh hưởng lẫn nhau và không ổn định.
- **Không kiểm soát thời gian hoặc tính ngẫu nhiên:** lỗi khó tái hiện.
- **Cleanup không đầy đủ:** trạng thái cũ ảnh hưởng lần chạy tiếp theo.
- **Mock tất cả phụ thuộc:** bỏ qua lỗi hợp đồng và tích hợp thật.
- **Assertion quá yếu:** test đạt dù hành vi nghiệp vụ vẫn sai.
- **Assertion quá chi tiết vào nội bộ:** refactor hợp lệ làm test thất bại.
- **Kế thừa BaseTest quá rộng:** lifecycle và trạng thái dùng chung trở nên khó hiểu.
- **Không ghi nhận giới hạn của dữ liệu hoặc môi trường:** kết quả bị diễn giải quá mức.
- **Không duy trì helper dùng chung:** thay đổi mặc định làm nhiều test hỏng mà không rõ nguyên nhân.
- **Chỉ đo số lượng test:** nhiều test không đồng nghĩa với bằng chứng tốt.

## 21. Mẫu thiết kế một kiểm thử và lớp hỗ trợ

Có thể dùng mẫu sau để rà soát hoặc thiết kế một nhóm test:

~~~text
MỤC TIÊU KIỂM THỬ:
Hành vi hoặc quy tắc cần xác minh:

ĐIỀU KIỆN:
Trạng thái ban đầu:
Dữ liệu cần thiết:
Phụ thuộc:
Thời gian / cấu hình:

TEST:
Tên test:
Arrange:
Act:
Assert:
Kết quả mong đợi:

DỮ LIỆU:
Factory / Builder / Fixture:
Định danh và phạm vi dữ liệu:
Cách cleanup:
Tính độc lập và chạy song song:

LỚP HỖ TRỢ:
Tên lớp:
Trách nhiệm:
API sử dụng:
Side effect:
Người sở hữu:

BẰNG CHỨNG:
Kết quả chạy:
Log / dữ liệu quan sát:
Giới hạn:
Hành động tiếp theo:
~~~

Mẫu này có thể được thu gọn cho kiểm thử đơn vị đơn giản hoặc mở rộng cho kiểm thử tích hợp và E2E. Mục tiêu là làm rõ ý định, dữ liệu, phụ thuộc và bằng chứng, không tạo thêm thủ tục không cần thiết.

## Kết luận

Mã kiểm thử có thể duy trì cần diễn đạt rõ hành vi, dùng dữ liệu độc lập và dự đoán được, đồng thời tổ chức các lớp hỗ trợ theo trách nhiệm cụ thể. Arrange–Act–Assert giúp người đọc nhận ra mục tiêu; factory, builder và fixture giúp tạo dữ liệu nhất quán; client, Page Object, assertion helper và test double giúp đóng gói chi tiết kỹ thuật ở đúng ranh giới.

Mỗi abstraction cần làm cho test dễ hiểu hoặc dễ thay đổi hơn. Dữ liệu cần có vòng đời rõ ràng, thời gian và phụ thuộc cần kiểm soát, còn kết quả phải đủ thông tin để điều tra khi thất bại. Khi nhóm duy trì các nguyên tắc này cùng với quy ước và chủ sở hữu rõ ràng, bộ kiểm thử có thể phát triển theo sản phẩm mà không trở thành một hệ thống khó sửa hơn chính phần mềm cần bảo vệ.
