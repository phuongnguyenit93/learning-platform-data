# Giữ bài kiểm thử nhanh và không phụ thuộc mạng

Kiểm thử đơn vị có giá trị nhất khi người phát triển có thể chạy chúng thường xuyên, nhận kết quả trong thời gian ngắn và tin rằng kết quả phản ánh chính xác code đang thay đổi. Một bài test phải gọi API qua mạng, chờ database, khởi động broker hoặc phụ thuộc vào một dịch vụ đang chạy ở máy khác sẽ khó giữ được những đặc điểm đó.

Trong Spring Framework Testing, mục tiêu của kiểm thử đơn vị là xác nhận hành vi của một đơn vị code trong phạm vi được kiểm soát. Đơn vị đó có thể là một hàm tính toán, domain object, validator, policy hoặc application service. Những dependency bên ngoài được thay bằng implementation nhỏ, có thể dự đoán như fake, stub hoặc mock. Nhờ vậy, test kiểm tra quyết định của đơn vị mà không cần mở kết nối mạng.

Một bộ kiểm thử nhanh và độc lập mạng giúp:

- Chạy được ngay trong lúc viết code, trước khi commit và trong CI.
- Trả kết quả ổn định, ít bị ảnh hưởng bởi trạng thái của dịch vụ bên ngoài.
- Chỉ ra nguyên nhân lỗi gần với thành phần vừa thay đổi.
- Chạy song song mà không tranh chấp dữ liệu dùng chung.
- Giảm thời gian chờ khi phát triển và điều tra lỗi.

Độc lập mạng không có nghĩa ứng dụng không được sử dụng HTTP, database hoặc message broker. Nó có nghĩa là **kiểm thử đơn vị không cần những hệ thống đó để chứng minh hành vi của đơn vị đang được kiểm tra**. Các bài kiểm thử adapter và tích hợp vẫn cần xác nhận khả năng giao tiếp với hệ thống thật ở một tầng riêng.

## 1. Phân biệt kiểm thử đơn vị với kiểm thử cần hạ tầng

Hãy bắt đầu từ câu hỏi mà bài test cần trả lời:

- Một quy tắc tính phí có đúng không?
- Validator có từ chối dữ liệu không hợp lệ không?
- Application service có điều phối các bước nghiệp vụ theo đúng thứ tự không?
- Repository có lưu và đọc đúng dữ liệu trên database không?
- HTTP client có gửi request đúng giao thức và xử lý response đúng không?

Ba câu hỏi đầu thường có thể trả lời bằng kiểm thử đơn vị. Hai câu hỏi cuối cần đi qua adapter hoặc hạ tầng tương ứng.

~~~mermaid
flowchart TD
    A["Bài kiểm thử cần xác nhận điều gì?"] --> B{"Quyết định hoặc quy tắc của một đơn vị?"}
    B -->|"Có"| C["Unit test"]
    C --> D["Tạo đối tượng trực tiếp"]
    D --> E["Fake / Stub / Mock dependency"]
    E --> F["Không gọi mạng, không khởi động hạ tầng"]
    B -->|"Không"| G{"Hành vi adapter hoặc tích hợp?"}
    G -->|"Có"| H["Adapter / Integration test"]
    H --> I["HTTP server giả lập hoặc dịch vụ thật"]
    I --> J["Kiểm tra giao thức và tương tác"]
~~~

Ví dụ, một service tính tổng đơn hàng có thể nhận danh sách mặt hàng và một port để lấy chính sách giảm giá. Test của service không cần gọi hệ thống quản lý khuyến mại qua HTTP. Nó chỉ cần một fake trả về chính sách đã biết để kiểm tra cách service tính tổng.

Ngược lại, nếu mục tiêu là xác nhận HTTP client tạo đúng URL, header, body và xử lý status code, một unit test của quy tắc nghiệp vụ không đủ. Cần test adapter với một HTTP server giả lập hoặc một dịch vụ phù hợp. Việc test adapter sử dụng socket cục bộ cũng có chi phí và phạm vi khác với unit test thuần.

## 2. Giữ đơn vị kiểm thử nhỏ và tạo dependency trực tiếp

Một unit test thường không cần khởi động Spring ApplicationContext. Nếu class có constructor rõ ràng và dependency được truyền vào, test có thể tạo object bằng Java thông thường.

Ví dụ, dịch vụ áp dụng chính sách giảm giá:

~~~java
import java.math.BigDecimal;

public interface DiscountPolicy {
    BigDecimal discountFor(String customerId);
}

public final class OrderTotalService {

    private final DiscountPolicy discountPolicy;

    public OrderTotalService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    public BigDecimal total(
            String customerId,
            BigDecimal subtotal
    ) {
        BigDecimal discount =
                discountPolicy.discountFor(customerId);

        return subtotal.subtract(discount);
    }
}
~~~

Test có thể dùng một implementation đơn giản:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderTotalServiceTest {

    @Test
    void subtractsDiscountFromSubtotal() {
        DiscountPolicy policy =
                customerId -> new BigDecimal("10000");

        OrderTotalService service =
                new OrderTotalService(policy);

        BigDecimal actual = service.total(
                "CUSTOMER-01",
                new BigDecimal("80000")
        );

        assertEquals(new BigDecimal("70000"), actual);
    }
}
~~~

Bài test này không tạo Spring context, không truy cập database và không mở kết nối HTTP. Nó chỉ kiểm tra phép tính của **OrderTotalService** với một phản hồi giảm giá đã xác định.

Nếu class đang dùng field injection, static singleton hoặc tự tạo HTTP client bên trong method, test sẽ khó thay dependency. Có thể cải thiện thiết kế bằng constructor injection hoặc đưa thao tác bên ngoài qua một interface. Điều này không phải là tạo abstraction cho mọi thứ; chỉ cần một ranh giới rõ khi code thực sự phụ thuộc vào tài nguyên bên ngoài.

### Khi nào vẫn cần Spring?

Nếu hành vi được kiểm tra phụ thuộc vào chính cơ chế của Spring như transaction proxy, method security, AOP, conditional bean hoặc dependency injection, cần một test đi qua Spring container. Những test đó là container test hoặc integration test với phạm vi được chọn, không còn là unit test thuần.

Không nên dùng **@SpringBootTest** cho mọi test chỉ vì class sản phẩm được đánh dấu **@Service**. Annotation đó cho biết Spring quản lý bean trong ứng dụng; nó không bắt buộc mọi test của class phải khởi động ứng dụng.

Một quy tắc nghiệp vụ thuần Java vẫn có thể được kiểm tra bằng cách tạo object trực tiếp. Dành Spring context cho những câu hỏi thực sự cần xác nhận hành vi do Spring cung cấp.

## 3. Thay network dependency bằng fake, stub hoặc mock

Dependency mạng có thể là HTTP client, SDK của nhà cung cấp, repository gọi database, publisher gửi message hoặc gateway truy cập dịch vụ khác. Trong unit test, hãy điều khiển phản hồi của dependency để tập trung vào quyết định của đơn vị.

### Stub: trả về dữ liệu đã định trước

Stub phù hợp khi test cần một phản hồi cụ thể và không cần kiểm tra chi tiết tương tác.

~~~java
public interface ExchangeRatePort {
    BigDecimal rate(String from, String to);
}
~~~

~~~java
@Test
void convertsUsingProvidedExchangeRate() {
    ExchangeRatePort rates =
            (from, to) -> new BigDecimal("25000");

    CurrencyConverter converter =
            new CurrencyConverter(rates);

    BigDecimal actual = converter.convert(
            new BigDecimal("2"),
            "USD",
            "VND"
    );

    assertEquals(new BigDecimal("50000"), actual);
}
~~~

Stub làm cho kết quả có thể dự đoán. Test không phụ thuộc vào tỷ giá hiện tại, dịch vụ bên ngoài có hoạt động hay không, hoặc mạng của máy chạy test.

### Fake: mô phỏng hành vi bằng implementation nhỏ

Fake có thể giữ trạng thái trong bộ nhớ và thực hiện một phần hợp đồng của dependency. Ví dụ, một repository giả có thể lưu entity trong Map để kiểm tra application service:

~~~java
public final class InMemoryCustomerRepository
        implements CustomerRepository {

    private final Map<String, Customer> customers =
            new HashMap<>();

    @Override
    public Optional<Customer> findById(String id) {
        return Optional.ofNullable(customers.get(id));
    }

    @Override
    public Customer save(Customer customer) {
        customers.put(customer.id(), customer);
        return customer;
    }
}
~~~

Fake hữu ích khi test cần nhiều thao tác liên tiếp, chẳng hạn lưu một khách hàng rồi truy vấn lại. Tuy nhiên, fake chỉ mô phỏng hợp đồng mà nó được viết. Nó không chứng minh SQL, transaction, index hoặc locking của database thật hoạt động đúng.

### Mock: xác nhận một tương tác có ý nghĩa

Mock thích hợp khi điều cần xác nhận là một lời gọi quan trọng, chẳng hạn service phát lệnh gửi thông báo khi đơn hàng được xác nhận.

~~~java
@Test
void publishesConfirmationAfterOrderIsConfirmed() {
    OrderEventPublisher publisher =
            mock(OrderEventPublisher.class);

    OrderConfirmationService service =
            new OrderConfirmationService(publisher);

    service.confirm(new OrderId("ORDER-01"));

    verify(publisher).publish(
            argThat(event ->
                    event.orderId().equals("ORDER-01"))
    );
}
~~~

Ví dụ trên minh họa cách kiểm tra tương tác bằng Mockito. Cần khai báo import và cấu hình Mockito phù hợp trong dự án. Chỉ verify những tương tác thuộc hợp đồng cần bảo vệ; nếu test xác nhận mọi lời gọi nội bộ, nó sẽ trở nên mong manh khi implementation được refactor.

| Kỹ thuật | Điều nó cung cấp | Dùng khi |
|---|---|---|
| Stub | Phản hồi cố định | Cần kiểm soát đầu vào từ dependency |
| Fake | Hành vi đơn giản, thường có trạng thái | Cần nhiều bước tương tác trong bộ nhớ |
| Mock | Ghi nhận và xác minh lời gọi | Một tương tác là kết quả cần kiểm tra |

Cả ba cách đều có thể giữ unit test độc lập mạng nếu chúng không mở kết nối thật. Đừng nhầm một object mock với một HTTP server giả lập: mock một interface client không tạo ra một server có giao thức HTTP.

## 4. Tránh những nguồn làm test chậm hoặc phụ thuộc môi trường

Mạng là một nguồn gây chậm và không ổn định, nhưng không phải nguồn duy nhất. Một unit test có thể trở nên khó lặp lại nếu nó phụ thuộc vào thời gian hiện tại, số ngẫu nhiên, trạng thái dùng chung hoặc file bên ngoài.

### Không gọi HTTP hoặc SDK thật trong unit test

Không để test gọi trực tiếp một API công cộng, service staging, API nội bộ hay SDK tự kết nối ra Internet. Các tình huống có thể làm test thất bại dù code không đổi:

- DNS không phân giải được tên miền.
- Mạng công ty, VPN hoặc proxy không sẵn sàng.
- Dịch vụ bên ngoài bảo trì hoặc giới hạn tốc độ.
- Token hết hạn hoặc quyền truy cập thay đổi.
- Response thay đổi theo dữ liệu, thời điểm hoặc trạng thái tài khoản.
- Request mất nhiều thời gian do timeout hoặc retry.

Thay vì gọi dịch vụ thật, đưa thao tác đó sau một interface và cung cấp stub/fake trong unit test. Test adapter riêng sẽ kiểm tra request/response với một server giả lập khi cần.

### Không dùng database thật để kiểm tra quy tắc thuần

Một test tính toán hoặc quyết định nghiệp vụ không cần mở kết nối database. Nếu service đọc một giá trị từ repository, hãy truyền vào fake trả về dữ liệu xác định.

Database test vẫn cần thiết để xác nhận mapping, query và transaction. Hãy đặt chúng ở nhóm test phù hợp và để unit test chạy độc lập với nhóm đó.

### Không dùng thời gian hiện tại trực tiếp

Code gọi **LocalDate.now()**, **Instant.now()** hoặc **System.currentTimeMillis()** có thể cho kết quả khác nhau theo thời điểm chạy. Test chạy gần nửa đêm, khác múi giờ hoặc qua ranh giới ngày có thể thất bại khó tái hiện.

Hãy truyền **Clock** vào thành phần cần biết thời gian:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class SubscriptionService {

    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(LocalDate expiryDate) {
        LocalDate today = LocalDate.now(clock);
        return expiryDate.isBefore(today);
    }
}
~~~

Test có thể cố định thời gian:

~~~java
@Test
void treatsYesterdayAsExpired() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-12T00:00:00Z"),
            ZoneId.of("UTC")
    );

    SubscriptionService service =
            new SubscriptionService(clock);

    assertTrue(service.isExpired(
            LocalDate.of(2026, 11, 11)
    ));
}
~~~

Khi thời gian được điều khiển, test không phụ thuộc đồng hồ máy hoặc ngày chạy. Với nghiệp vụ liên quan múi giờ, hãy chọn ZoneId rõ ràng thay vì dựa vào timezone mặc định của máy.

### Không phụ thuộc số ngẫu nhiên không kiểm soát

Nếu code tạo UUID, số ngẫu nhiên hoặc mã tham chiếu, kết quả có thể thay đổi ở mỗi lần chạy. Nếu giá trị đó ảnh hưởng đến quyết định cần kiểm tra, có thể truyền một supplier hoặc generator qua constructor để test cấp giá trị cố định.

Ví dụ, thay vì tự gọi random generator trong service, khai báo một interface nhỏ cho việc cấp mã. Unit test sử dụng implementation trả về mã đã biết. Test vẫn có thể xác nhận rằng mã được sử dụng đúng mà không phải đoán giá trị ngẫu nhiên.

### Không dựa vào trạng thái dùng chung

Một test không nên phụ thuộc vào dữ liệu mà test khác tạo ra. Tránh static mutable state, singleton giữ dữ liệu test, thư mục chung có nội dung tích lũy hoặc thứ tự chạy test.

Mỗi test cần tự tạo fixture và dọn trạng thái của chính nó. Khi chạy song song, mỗi test phải có dữ liệu độc lập để không ghi đè hoặc đọc nhầm kết quả của test khác.

## 5. Thiết kế ranh giới để unit test không vô tình mở mạng

Một nguyên nhân phổ biến của test phụ thuộc mạng là code tự tạo client bên trong thành phần nghiệp vụ. Khi đó, test không có điểm thay thế dependency.

Ví dụ khó cô lập:

~~~java
public final class WeatherService {

    public String forecast(String city) {
        var client = HttpClient.newHttpClient();
        // Gửi request thật tới dịch vụ thời tiết
        // và phân tích response ở đây.
        return "sunny";
    }
}
~~~

Ngay cả khi phần xử lý kết quả rất nhỏ, method đã sở hữu trách nhiệm tạo client và giao tiếp mạng. Unit test gọi method có thể vô tình gửi request thật.

Tách thao tác ra một port:

~~~java
public interface WeatherGateway {
    WeatherForecast fetch(String city);
}

public final class WeatherService {

    private final WeatherGateway gateway;

    public WeatherService(WeatherGateway gateway) {
        this.gateway = gateway;
    }

    public WeatherForecast forecast(String city) {
        WeatherForecast forecast = gateway.fetch(city);

        if (forecast == null) {
            throw new IllegalStateException(
                    "Weather forecast is unavailable"
            );
        }

        return forecast;
    }
}
~~~

Unit test truyền một fake hoặc stub cho **WeatherGateway**:

~~~java
@Test
void returnsForecastFromGateway() {
    WeatherGateway gateway = city ->
            new WeatherForecast(city, "SUNNY");

    WeatherService service = new WeatherService(gateway);

    WeatherForecast actual = service.forecast("Hanoi");

    assertEquals("SUNNY", actual.condition());
}
~~~

Implementation thật của **WeatherGateway** sẽ dùng HTTP client. Adapter đó được kiểm thử riêng để xác nhận cách tạo request, xử lý status, timeout và chuyển đổi response. Việc tách này tạo hai câu hỏi độc lập:

- **WeatherService** có xử lý forecast theo đúng quy tắc không?
- HTTP adapter có giao tiếp đúng với dịch vụ thời tiết không?

Một unit test không cần biết URL thật, API key hay cấu trúc response của nhà cung cấp. Những chi tiết đó thuộc adapter.

### Constructor injection tạo điểm thay thế rõ ràng

Trong ứng dụng Spring, constructor injection là cách thuận tiện để cung cấp dependency và làm rõ những gì một class cần:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult pay(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

Trong runtime, Spring inject implementation thật của **PaymentGateway**. Trong unit test, test truyền fake hoặc mock. Không cần khởi động Spring để kiểm tra cách **PaymentService** xử lý kết quả của gateway.

Nếu class có nhiều dependency chỉ vì nó tự thực hiện database, HTTP, clock và random generation, hãy xem xét tách các trách nhiệm và đưa những nguồn thay đổi bên ngoài qua dependency phù hợp. Không nên tạo interface cho mọi class; ranh giới cần thiết là nơi code cần kiểm soát hoặc thay thế hành vi bên ngoài.

## 6. Phân loại test trong dự án Spring

Một dự án Spring thường có nhiều loại test. Có thể phân nhóm để người phát triển chạy đúng phần cần thiết:

| Nhóm | Ví dụ | Cần mạng/hạ tầng? | Mục đích |
|---|---|---|---|
| Unit test thuần | Domain service, validator, calculator | Không | Kiểm tra quy tắc và quyết định |
| Spring context test | Bean wiring, conditional configuration | Thường không cần mạng | Kiểm tra container |
| Spring MVC slice | MockMvc với controller | Không cần dịch vụ ngoài nếu dependency được thay thế | Kiểm tra HTTP adapter trong ứng dụng |
| Repository test | JPA với database test | Có thể cần database cục bộ/container | Kiểm tra persistence |
| HTTP adapter test | Client với MockWebServer/WireMock | Có thể dùng socket cục bộ | Kiểm tra giao thức HTTP |
| Integration test | Nhiều thành phần cùng database/broker | Có thể cần hạ tầng | Kiểm tra sự phối hợp thực tế |
| End-to-end test | Ứng dụng chạy qua các ranh giới | Thường có | Kiểm tra luồng từ đầu đến cuối |

**@WebMvcTest** có thể khởi tạo Spring MVC slice mà không cần gọi API bên ngoài nếu service dependency được thay bằng mock. Đây vẫn là test có Spring context, nhưng không nhất thiết cần mạng.

**@DataJpaTest** thường cần một database để kiểm tra persistence. Nếu cấu hình dùng embedded database, nó có thể chạy cục bộ; nếu dùng Testcontainers, nó cần môi trường container. Đây không phải unit test thuần.

**@SpringBootTest(webEnvironment = RANDOM_PORT)** thường khởi động ứng dụng với web server thật trong tiến trình test. Nó phù hợp cho một số kiểm thử tích hợp, nhưng không nên trở thành cách chạy mặc định cho mọi quy tắc nghiệp vụ.

Việc đặt tên nhóm test và cấu hình task chạy riêng giúp CI có thể chạy unit test thường xuyên, rồi chạy các nhóm tích hợp có chi phí cao hơn ở giai đoạn phù hợp. Cách phân nhóm phải phản ánh dependency thực tế, không chỉ dựa vào tên thư mục.

## 7. Giữ test nhanh mà vẫn có assertion có giá trị

Test nhanh không đồng nghĩa với test hời hợt. Một unit test có thể kiểm tra nhiều trường hợp đầu vào trong cùng một phương thức parameterized mà không cần khởi động thêm hạ tầng.

Ví dụ, kiểm tra ngưỡng tính phí:

~~~java
@ParameterizedTest
@CsvSource({
    "0, 30000",
    "499999, 30000",
    "500000, 0",
    "700000, 0"
})
void calculatesStandardShippingFee(
        String subtotal,
        String expectedFee
) {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal(subtotal),
            false
    );

    assertEquals(new BigDecimal(expectedFee), actual);
}
~~~

Bài test tạo object trực tiếp, dùng dữ liệu trong bộ nhớ và không phụ thuộc hệ thống ngoài. Mỗi dòng thể hiện một trường hợp có ý nghĩa, bao gồm cả ranh giới chính sách.

Một test tốt nên:

- Kiểm tra kết quả hoặc tương tác thuộc hợp đồng của đơn vị.
- Có tên thể hiện điều kiện và hành vi.
- Không kiểm tra chi tiết implementation không liên quan.
- Không gọi mạng hoặc đợi dịch vụ bên ngoài.
- Không dùng sleep để chờ một trạng thái không thuộc phạm vi.
- Không phụ thuộc thứ tự test.
- Có dữ liệu đầu vào xác định và assertion đủ mạnh.

Nếu một unit test mất vài giây dù chỉ thực hiện một phép tính, hãy xem lại setup, extension, static initializer, logging, context hoặc dependency đang bị khởi tạo. Thời gian test tăng bất thường thường là dấu hiệu test đã kéo thêm trách nhiệm ngoài phạm vi đơn vị.

## 8. Quản lý thời gian chạy trong JUnit và CI

Tốc độ phản hồi phụ thuộc cả vào cách tổ chức test suite. Một số thực hành giúp giữ nhóm unit test gọn:

- Chạy test class hoặc method đang phát triển trong IDE.
- Dùng task hoặc bộ lọc riêng để chạy nhóm unit test nhanh.
- Không đặt test cần Docker, database hoặc mạng vào nhóm được chạy như unit test.
- Tránh khởi động Spring context lặp lại khi test không cần context.
- Dùng fixture nhỏ, tránh tạo nhiều dữ liệu hoặc file lớn nếu không cần.
- Giữ log ở mức phù hợp để test không bị chậm bởi I/O không cần thiết.
- Khi test song song, bảo đảm mỗi test có dependency và dữ liệu riêng.

Trong Gradle, dự án có thể dùng JUnit Platform và các tag để tách nhóm test. Ví dụ minh họa:

~~~java
@Tag("unit")
class ShippingFeeCalculatorTest {
    // Unit tests
}

@Tag("integration")
class PaymentGatewayIntegrationTest {
    // Integration tests
}
~~~

Có thể cấu hình các task riêng để chỉ chạy tag cần thiết. Cú pháp và tên task phụ thuộc build script của dự án; hãy dùng cấu hình hiện có thay vì tự tạo một convention trùng lặp.

Một pipeline thường chạy unit test sớm để phản hồi nhanh cho mỗi thay đổi. Sau đó, các nhóm test cần database, broker hoặc môi trường triển khai có thể chạy ở stage phù hợp. Cách phân tầng này giúp lỗi logic được phát hiện nhanh, trong khi rủi ro tích hợp vẫn được kiểm tra.

Không nên loại bỏ integration test chỉ để giảm thời gian CI. Cần đặt chúng đúng nhóm, quản lý tài nguyên và chọn thời điểm chạy hợp lý.

## 9. Chẩn đoán khi unit test bất ngờ phụ thuộc mạng

Nếu một bài được xem là unit test nhưng chạy chậm, treo hoặc thất bại khi ngắt mạng, hãy tìm dependency đang mở kết nối.

Một số dấu hiệu:

- Test chạy lâu rồi thất bại với connect timeout hoặc DNS error.
- Test cần VPN, proxy, token hoặc biến môi trường của dịch vụ ngoài.
- Test chỉ xanh trong một môi trường có database/broker đang chạy.
- Test phụ thuộc dữ liệu hiện tại của một API.
- Test thất bại ngẫu nhiên theo tải mạng hoặc giới hạn tốc độ.
- Test có retry nhiều lần trước khi kết thúc.

Có thể lần theo call path từ method đang test tới nơi tạo kết nối. Tìm những điểm như **HttpClient**, **RestClient**, **WebClient**, **RestTemplate**, SDK của nhà cung cấp, JDBC connection, Redis client hoặc message producer. Kiểm tra constructor, static initializer và bean factory vì kết nối đôi khi được tạo trước khi test gọi method.

Khi đã tìm được ranh giới, chọn cách xử lý:

1. Truyền dependency qua constructor hoặc interface.
2. Cung cấp fake/stub/mock trong unit test.
3. Chuyển kiểm tra giao thức sang adapter test.
4. Chuyển kiểm tra tương tác với database/broker sang integration test.
5. Giữ unit test không cần credential, endpoint hoặc cấu hình mạng.

Một bài test không cần chứng minh rằng mạng đang hoạt động để xác nhận một phép tính nghiệp vụ. Nếu nó cần mạng, hãy xem lại câu hỏi kiểm thử và phân loại đúng tầng.

## 10. Ví dụ tổ chức một bộ test theo ranh giới

Giả sử hệ thống có chức năng đăng ký thuê bao. Luồng runtime gồm:

1. Controller nhận request.
2. Application service kiểm tra dữ liệu và quyết định trạng thái thuê bao.
3. Repository lưu dữ liệu.
4. Notification gateway gửi email.

Có thể chia test như sau:

| Thành phần | Bài kiểm thử | Dependency trong test |
|---|---|---|
| SubscriptionPolicy | Ngày hết hạn, điều kiện kích hoạt | Clock cố định |
| SubscriptionService | Quyết định đăng ký và xử lý kết quả | Fake repository, mock notification port |
| SubscriptionController | Mapping, validation, response | @WebMvcTest, mock service |
| SubscriptionRepository | Lưu và đọc thuê bao | Database test |
| EmailNotificationAdapter | Request gửi tới SMTP/provider | SMTP server giả lập hoặc adapter test |
| RegistrationFlow | Luồng nhiều thành phần phối hợp | Spring context và hạ tầng test cần thiết |

Unit test cho **SubscriptionService** có thể chạy hàng trăm trường hợp mà không gọi email hoặc database. Một fake repository có thể lưu đối tượng trong bộ nhớ, còn mock notification port giúp xác nhận thông báo chỉ được phát khi nghiệp vụ thành công.

Test repository sẽ xác nhận mapping và truy vấn trên database. Test email adapter sẽ xác nhận cấu trúc message hoặc giao thức gửi. Integration test sẽ xác nhận các bean được lắp ghép và luồng đăng ký phối hợp đúng trong cấu hình ứng dụng.

Nhờ phân chia này, khi unit test thất bại vì trạng thái thuê bao sai, người phát triển không phải kiểm tra database hoặc SMTP. Khi adapter test thất bại vì request sai, phạm vi điều tra tập trung vào adapter và hợp đồng giao tiếp.

## 11. Tiêu chí thực tế cho một unit test nhanh và độc lập mạng

Trước khi đưa test vào nhóm unit test, có thể tự trả lời:

- Test có tạo đối tượng cần kiểm tra trực tiếp hoặc qua fixture nhỏ không?
- Dependency bên ngoài có được thay bằng stub, fake hoặc mock không?
- Test có tránh gọi HTTP, database, broker và dịch vụ bên ngoài không?
- Thời gian, random và trạng thái dùng chung có được kiểm soát không?
- Test có thể chạy khi máy không kết nối Internet không?
- Test có độc lập với thứ tự chạy và các test khác không?
- Assertion có thể phát hiện một hành vi sai có ý nghĩa không?
- Nếu test thất bại, nguyên nhân có thể khoanh vùng ở đơn vị đang kiểm tra không?

Nếu câu trả lời cho câu hỏi về mạng là không, hãy xem xét tách adapter hoặc chuyển test sang nhóm phù hợp. Nếu test cần Spring context vì hành vi thực sự phụ thuộc container, hãy phân loại nó là context test và kiểm soát những dependency mà context khởi tạo.

Một bộ unit test tốt tạo phản hồi nhanh, lặp lại được và không đòi hỏi người phát triển chuẩn bị dịch vụ bên ngoài. Bằng cách giữ ranh giới dependency rõ ràng, sử dụng fake/stub/mock có chủ đích và kiểm soát các nguồn không xác định như thời gian hay random, kiểm thử đơn vị có thể chạy thường xuyên trong IDE và CI. Những bài kiểm thử cần xác nhận HTTP, database hoặc broker vẫn được thực hiện ở tầng adapter và tích hợp, nơi chúng có thể cung cấp bằng chứng phù hợp về khả năng giao tiếp với hạ tầng.

