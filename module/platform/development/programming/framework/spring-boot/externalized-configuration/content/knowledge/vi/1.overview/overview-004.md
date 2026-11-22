# Phân biệt cấu hình ứng dụng, định nghĩa bean và dữ liệu nghiệp vụ

Trong Spring Boot, ba khái niệm **cấu hình ứng dụng (application configuration)**, **định nghĩa bean (bean definition)** và **dữ liệu nghiệp vụ (business data)** thường xuất hiện trong cùng một luồng xử lý. Chúng có thể cùng tồn tại trong một lớp Java, nhưng có nguồn gốc, chủ sở hữu, vòng đời và cách thay đổi khác nhau. Phân biệt đúng giúp ứng dụng dễ triển khai ở nhiều môi trường, dễ kiểm thử và tránh biến Spring container thành nơi lưu trạng thái nghiệp vụ.

## 1. Nhìn nhanh vào ba lớp trách nhiệm

| Khía cạnh | Cấu hình ứng dụng | Định nghĩa bean | Dữ liệu nghiệp vụ |
| --- | --- | --- | --- |
| Câu hỏi trả lời | Ứng dụng **chạy với tham số nào** ở môi trường này? | Spring **tạo đối tượng nào, phụ thuộc vào ai, với vòng đời nào**? | Hệ thống **đang xử lý sự kiện, giao dịch, thực thể nào**? |
| Ví dụ | URL dịch vụ ngoài, timeout, pool size, tên topic, cờ bật tích hợp | `@Component`, `@Service`, `@Configuration`, `@Bean`, auto-configuration | Đơn hàng, số tiền thanh toán, trạng thái giao hàng, thông tin khách hàng |
| Nguồn thường gặp | `application.yml`, biến môi trường, tham số khởi động, kho secrets | Mã Java, annotation, cấu hình và cơ chế auto-configuration của framework | Database, request API, message/event, thao tác người dùng |
| Ai thường thay đổi? | Người vận hành hoặc nhóm phát triển theo môi trường | Lập trình viên qua thay đổi mã/phiên bản | Người dùng, nghiệp vụ và các tiến trình của hệ thống |
| Vòng đời điển hình | Được nạp/bind khi ứng dụng khởi động; khả năng cập nhật phụ thuộc cơ chế sử dụng | Được Spring đăng ký, khởi tạo và quản lý trong `ApplicationContext` | Được tạo, cập nhật, đọc và lưu theo luồng nghiệp vụ |
| Cách kiểm thử | Ghi đè property, kiểm tra binding/validation | Kiểm tra wiring, điều kiện tạo bean và dependency injection | Kiểm tra hành vi nghiệp vụ, giao dịch và dữ liệu đầu vào/đầu ra |

**Điểm mấu chốt:** cùng một giá trị có thể đi qua nhiều lớp, nhưng vai trò của nó thay đổi theo nơi nó được dùng. Một giá trị timeout là *cấu hình*; đối tượng `GatewayClient` được Spring tạo từ timeout đó là *bean*; đơn hàng truyền vào client là *dữ liệu nghiệp vụ*.

## 2. Cấu hình ứng dụng: các giá trị điều khiển cách ứng dụng vận hành

Spring Boot hỗ trợ **externalized configuration**: thay vì đóng cứng mọi giá trị theo từng môi trường vào mã nguồn, ứng dụng nhận property từ các nguồn như file cấu hình, biến môi trường hoặc tham số khi chạy. Spring `Environment` cung cấp mô hình truy cập các property; `@ConfigurationProperties` giúp bind một nhóm property vào đối tượng có kiểu rõ ràng.

Ví dụ trong `application.yml`:

~~~yaml
shipping:
  gateway:
    base-url: https://shipping.example.invalid
    timeout: 3s
    enabled: true
~~~

Đây là các **tham số kỹ thuật cho tích hợp giao hàng**: endpoint gọi ra ngoài, thời gian chờ và việc có kích hoạt thành phần tích hợp hay không. Môi trường development, staging và production có thể dùng giá trị khác nhau mà không cần nhân bản lớp `ShippingClient`.

Các đặc tính nhận diện cấu hình ứng dụng:

- Giá trị mô tả **môi trường hoặc chính sách vận hành** của một bản triển khai: host, port, thời gian chờ, mức retry, giới hạn kết nối, log level.
- Giá trị thường có **mặc định, ràng buộc hợp lệ và quy ước đặt tên**; có thể được override từ nguồn cấu hình có độ ưu tiên phù hợp.
- Giá trị nên được **kiểm tra sớm** để tránh ứng dụng khởi động với cấu hình sai. `@ConfigurationProperties` phù hợp để gom nhóm và dùng type-safe binding.
- Thông tin bí mật như token, password, API key vẫn là một loại cấu hình, nhưng nên lấy từ secret manager hoặc cơ chế bảo mật của môi trường, không hard-code vào repository và không in ra log.

Ví dụ Java để nhận nhóm cấu hình trên:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping.gateway")
public record ShippingGatewayProperties(
        URI baseUrl,
        Duration timeout,
        boolean enabled
) {}
~~~

Khi ứng dụng kích hoạt `@ConfigurationPropertiesScan` hoặc đăng ký kiểu này qua `@EnableConfigurationProperties`, Spring Boot bind các key như `base-url` và `timeout` vào `ShippingGatewayProperties`. Chuỗi `3s` được chuyển sang kiểu `Duration`.

**Phân biệt đối tượng chứa cấu hình với nguồn cấu hình:** `ShippingGatewayProperties` có thể là một bean do Spring quản lý; điều đó không biến `application.yml` thành một bean definition. File YAML cung cấp **giá trị**, còn việc đăng ký bean thuộc về cơ chế cấu hình Spring.

### Profile không phải dữ liệu nghiệp vụ

Các file như `application-dev.yml` và `application-prod.yml` có thể biểu diễn những giá trị theo môi trường. Profile giúp chọn bộ cấu hình hoặc thành phần Spring phù hợp, nhưng không nên dùng profile để biểu diễn trạng thái của từng đơn hàng, từng khách hàng hoặc một giao dịch cụ thể.

Ví dụ, “production gọi endpoint thật” là quyết định cấu hình; “đơn hàng 123 đã giao” là trạng thái nghiệp vụ cần được lưu và truy vết.

## 3. Định nghĩa bean: cách ghép các thành phần của ứng dụng

Một **bean definition** là thông tin mà Spring dùng để biết một thành phần phải được đăng ký và tạo ra như thế nào. Bean là **instance được Spring container quản lý**. Các cách khai báo phổ biến gồm:

- `@Component` và các specialization như `@Service`, `@Repository` để phát hiện thành phần qua component scanning.
- Phương thức `@Bean` trong `@Configuration` để định nghĩa đối tượng được tạo bằng mã Java, đặc biệt hữu ích cho lớp của thư viện bên ngoài.
- Auto-configuration của Spring Boot, thường có điều kiện dựa trên classpath, bean hiện có hoặc property.
- Các quy tắc như scope, qualifier, primary và điều kiện kích hoạt để quyết định instance nào được đưa vào `ApplicationContext`.

Tiếp tục ví dụ giao hàng. Giả sử `ShippingClient` là lớp Java nhận URL và timeout qua constructor:

~~~java
import java.net.URI;
import java.time.Duration;

public final class ShippingClient {
    private final URI baseUrl;
    private final Duration timeout;

    public ShippingClient(URI baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    // Các phương thức tích hợp dùng baseUrl và timeout.
}
~~~

Ta định nghĩa bean tương ứng:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ShippingClientConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "shipping.gateway",
        name = "enabled",
        havingValue = "true"
    )
    ShippingClient shippingClient(ShippingGatewayProperties properties) {
        return new ShippingClient(
            properties.baseUrl(),
            properties.timeout()
        );
    }
}
~~~

Phần `@Bean` mô tả **cách tạo và quản lý `ShippingClient`**; điều kiện `@ConditionalOnProperty` sử dụng **một giá trị cấu hình** để quyết định có đăng ký bean hay không. Property `shipping.gateway.enabled=true` tự nó không định nghĩa constructor, dependency hoặc vòng đời của bean.

Nếu điều kiện không khớp, Spring không đăng ký bean này. Thành phần bắt buộc inject `ShippingClient` cũng cần có cấu trúc phù hợp khi tích hợp tắt; nếu không, ứng dụng có thể lỗi do thiếu dependency. Đây là vấn đề **wiring**, không phải lỗi dữ liệu đơn hàng.

Cần nhớ thêm:

- Scope mặc định của phần lớn bean ứng dụng là **singleton trong một `ApplicationContext`**, không có nghĩa là singleton trên mọi tiến trình hay máy chủ.
- Container tạo và quản lý bean theo cấu trúc ứng dụng; **không tạo một singleton bean mới mỗi lần có request nghiệp vụ**.
- Đổi property chưa chắc tự làm một bean được tạo lại. Spring Boot cơ bản thường bind và tạo bean ở lúc khởi động; muốn cập nhật động cần thiết kế riêng cơ chế reload/refresh và xử lý đồng bộ trạng thái.
- Có thể khai báo bean bằng annotation hoặc cấu hình Java; bản chất vẫn là **đăng ký thành phần và dependency**, không phải chỗ lưu bảng dữ liệu.

## 4. Dữ liệu nghiệp vụ: sự thật mà ứng dụng xử lý và lưu giữ

Dữ liệu nghiệp vụ biểu diễn trạng thái hoặc lịch sử của lĩnh vực ứng dụng: đơn hàng nào được tạo, giá trị bao nhiêu, khách hàng nào sở hữu, hóa đơn nào đã thanh toán, kiện hàng đang ở trạng thái nào. Chúng đi qua API, command, event, service, repository và cơ sở dữ liệu.

Ví dụ một đối tượng dữ liệu đơn hàng rút gọn:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record ShippingOrder(
        UUID id,
        UUID customerId,
        BigDecimal totalAmount,
        String deliveryAddress,
        String status
) {}
~~~

Một use case có thể lấy `ShippingOrder` từ repository rồi gọi `ShippingClient` để gửi yêu cầu tới hệ thống giao hàng:

~~~java
public void requestShipment(UUID orderId) {
    ShippingOrder order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    shippingClient.createShipment(order);
}
~~~

Đoạn code use case ở trên mang tính minh họa: repository, exception và phương thức gọi tích hợp được định nghĩa trong module nghiệp vụ thực tế. Điều quan trọng là **đối tượng `order` đến từ dữ liệu nghiệp vụ**, còn `shippingClient` là dependency do Spring quản lý và đã nhận thông số vận hành.

Các đặc trưng của dữ liệu nghiệp vụ:

- Thường có **identity** (mã đơn hàng, mã khách hàng), trạng thái, thời điểm, quan hệ và quy tắc toàn vẹn.
- Có thể thay đổi **liên tục khi ứng dụng đang chạy** mà không khởi động lại server.
- Thay đổi phải đi qua validation, authorization, transaction và quy trình nghiệp vụ tương ứng.
- Cần cơ chế lưu trữ, truy vấn, phân quyền, audit và lưu vết tùy yêu cầu; không nên coi file cấu hình triển khai là nguồn sự thật của giao dịch.

Ví dụ sai ranh giới là viết `order.status=SHIPPED` hoặc `customer.42.creditLimit=...` trong `application.yml` để cập nhật nghiệp vụ hằng ngày. Những giá trị đó cần một mô hình dữ liệu và quy trình quản lý nghiệp vụ thích hợp.

## 5. Nhìn toàn luồng dữ liệu

~~~text
application.yml / environment / secrets
                 |
                 | bind cấu hình
                 v
       ShippingGatewayProperties
                 |
                 | injection
                 v
@Configuration + @Bean ---> ShippingClient (Spring-managed)
                                 |
API / event --> OrderService ----+----> gọi hệ thống giao hàng
                   |
                   v
            OrderRepository
                   |
                   v
           Bản ghi đơn hàng
~~~

Đọc sơ đồ theo thứ tự:

1. Nguồn externalized configuration cung cấp URL, timeout, cờ kích hoạt.
2. Spring bind các giá trị vào `ShippingGatewayProperties`.
3. Bean definition quyết định có tạo `ShippingClient` hay không và cách cấp dependency.
4. `OrderService` là thành phần thực hiện use case; nó nhận các dependency cần thiết qua constructor.
5. Request và database cung cấp dữ liệu từng đơn hàng; service thực hiện nghiệp vụ dựa trên dữ liệu đó rồi gọi client.

Có thể xem đây là ba câu hỏi khác nhau: **giá trị nào được dùng**, **đối tượng nào được tạo**, và **đối tượng đó xử lý bản ghi nghiệp vụ nào**.

## 6. Các trường hợp dễ nhầm lẫn

### 6.1. `@ConfigurationProperties` có phải bean definition không?

Lớp gắn `@ConfigurationProperties` mô tả **cấu trúc và quy tắc bind giá trị cấu hình**. Để Spring quản lý instance, vẫn cần cơ chế đăng ký bean (scan, enable hoặc phương thức `@Bean` thích hợp). Do đó có hai mặt:

- `shipping.gateway.timeout=3s` là **giá trị cấu hình**.
- Đăng ký `ShippingGatewayProperties` vào container là **hành vi tạo/định nghĩa bean**.

Không nên gọi toàn bộ `application.yml` là “cấu hình bean” khi nó đang chứa property của ứng dụng.

### 6.2. `@Value` lấy property thì biến có thành dữ liệu nghiệp vụ không?

Không. Inject một property vào field hoặc constructor chỉ là cách **tiêu thụ cấu hình ứng dụng**. Vai trò của giá trị phụ thuộc vào ý nghĩa của nó. `timeout` của HTTP client vẫn là cấu hình vận hành dù giá trị đã nằm trong object Java.

Với nhiều property có liên quan, `@ConfigurationProperties` thường dễ bảo trì hơn nhiều chuỗi `@Value` rải rác, vì nhóm được các giá trị theo một prefix và cho phép kiểu dữ liệu rõ ràng.

### 6.3. Feature flag thuộc lớp nào?

Một flag như `shipping.gateway.enabled` dùng để bật/tắt **thành phần tích hợp theo môi trường** thường là cấu hình ứng dụng. Nó có thể được điều kiện `@ConditionalOnProperty` dùng để quyết định bean definition.

Nhưng một flag do nhân viên vận hành chọn cho **từng khách hàng**, từng đợt thử nghiệm hoặc từng giao dịch, thay đổi ngay trong lúc hệ thống chạy, có thể là **dữ liệu/chính sách nghiệp vụ** trong database hay dịch vụ quản lý feature flag. Không thể phân loại chỉ bằng tên gọi “flag”.

### 6.4. Thuế suất, phí giao hàng, hạn mức và mức chiết khấu thì sao?

Đây thường là **quy tắc hoặc tham số nghiệp vụ**, có thể được lưu ở property hay bảng database tùy cách vận hành. Để quyết định, hỏi: ai có quyền thay đổi, thay đổi theo khách hàng/đơn hàng hay theo bản triển khai, có cần hiệu lực thời gian/audit/phê duyệt không?

- Một giới hạn request kỹ thuật, cố định cho toàn môi trường, thích hợp làm cấu hình.
- Bảng phí vận chuyển theo vùng, có ngày hiệu lực và được nhân viên nghiệp vụ cập nhật, thích hợp làm dữ liệu/chính sách nghiệp vụ có kiểm soát.
- Đoạn mã tính phí và các service tham gia xử lý là **logic và cấu trúc bean**, dù chúng đọc tham số từ một trong hai nguồn trên.

**Không có quy tắc “nằm trong YAML thì chắc chắn là cấu hình kỹ thuật”.** Ý nghĩa nghiệp vụ và vòng đời thay đổi mới là tiêu chí quyết định.

### 6.5. Một bean có thể chứa dữ liệu nghiệp vụ không?

Về kỹ thuật, một service singleton có thể có field mutable, nhưng **lưu trạng thái đơn hàng hiện tại vào field của singleton** thường gây nhầm dữ liệu giữa các request, race condition và khó mở rộng nhiều instance. Đối tượng nghiệp vụ nên đi theo method argument, transaction hoặc nơi lưu trữ phù hợp.

Bean có thể giữ tham chiếu tới repository, gateway, validator, immutable settings hoặc thành phần xử lý. Bean không nên là kho trạng thái tạm dùng chung của mọi người dùng nếu không có thiết kế đồng bộ và phạm vi rõ ràng.

### 6.6. Cấu hình trong database có còn là cấu hình không?

Có thể. **Nơi lưu không tự quyết định loại dữ liệu.** Một bảng lưu endpoint/timeout áp dụng toàn hệ thống có thể là kho cấu hình tập trung. Ngược lại, một file JSON đi kèm request chứa đơn hàng vẫn là dữ liệu nghiệp vụ. Cần xét người sở hữu, phạm vi áp dụng, thời điểm cập nhật và cách dữ liệu được tiêu thụ.

## 7. Phân loại bằng bốn câu hỏi

Khi gặp một biến, class, bảng hoặc đoạn code chưa rõ vai trò, hãy hỏi:

1. **Giá trị này mô tả môi trường hay một thực thể/giao dịch?** Ví dụ `http.client.timeout` mô tả cách chạy, còn `order.paidAt` mô tả trạng thái đơn hàng.
2. **Ai chịu trách nhiệm cập nhật?** Pipeline triển khai/đội vận hành thường thay đổi cấu hình; lập trình viên thay đổi bean definition; người dùng và nghiệp vụ thay đổi dữ liệu đơn hàng.
3. **Thay đổi cần tác động vào cái gì?** Đổi property hoặc khởi động lại ứng dụng; phát hành bản mã mới để đổi wiring; hay thực hiện command/transaction để đổi trạng thái nghiệp vụ?
4. **Phạm vi hiệu lực là gì?** Một ứng dụng/môi trường; một thành phần Spring; hay một khách hàng, đơn hàng, phiên giao dịch?

| Trường hợp cụ thể | Phân loại hợp lý | Vì sao? |
| --- | --- | --- |
| `spring.datasource.url` | Cấu hình ứng dụng | Xác định database kết nối theo môi trường |
| `@Bean DataSource dataSource(...)` | Định nghĩa bean | Mô tả cách Spring tạo và cung cấp đối tượng |
| `orders.status = "PAID"` | Dữ liệu nghiệp vụ | Trạng thái của một đơn hàng |
| `spring.jpa.show-sql` | Cấu hình ứng dụng | Điều khiển hành vi ghi log SQL |
| `@Service OrderService` | Thành phần/bean | Đăng ký lớp thực thi use case |
| Mã khuyến mãi người dùng nhập | Dữ liệu đầu vào nghiệp vụ | Gắn với giao dịch và cần xác thực |
| `shipping.gateway.timeout` | Cấu hình ứng dụng | Ràng buộc kỹ thuật khi gọi tích hợp |
| `@ConditionalOnProperty` trên bean | Quy tắc đăng ký bean | Dùng property để quyết định sự tồn tại của bean |

## 8. Sai lầm thường gặp và hướng xử lý

**Sai lầm 1 — Hard-code cấu hình theo môi trường trong `@Bean`.**

~~~java
@Bean
ShippingClient shippingClient() {
    return new ShippingClient(
        URI.create("https://production.example.invalid"),
        Duration.ofSeconds(3)
    );
}
~~~

Mã này gắn trực tiếp endpoint production vào cấu trúc tạo bean. Khi thay đổi môi trường phải sửa mã hoặc tạo nhánh điều kiện. Hãy đưa endpoint và timeout vào externalized configuration, bind thành kiểu rõ ràng, rồi inject vào bean factory như ví dụ ở phần 3.

**Sai lầm 2 — Đưa dữ liệu từng request vào service singleton.**

~~~java
@Service
class CheckoutService {
    private String currentOrderId; // Sai khi dùng chung giữa các request
}
~~~

Field dùng chung có thể bị request khác ghi đè. Truyền mã đơn hàng qua method argument và tải dữ liệu từ repository trong phạm vi use case/transaction thích hợp.

**Sai lầm 3 — Dùng property để mô tả trạng thái giao dịch.**

Đổi `order.123.status` bằng deploy YAML bỏ qua API, authorization, transaction và audit. Dùng domain model và nguồn dữ liệu nghiệp vụ, với các command cập nhật hợp lệ.

**Sai lầm 4 — Giả định sửa file YAML sẽ tự thay đổi bean đang chạy.**

Spring Boot thông thường tạo và bind cấu hình khi khởi động. Nếu muốn cập nhật không restart, phải thiết kế cơ chế nạp lại cấu hình và cách component nhận thay đổi; nhiều bean được tạo từ giá trị cũ vẫn giữ giá trị đó cho tới khi có cơ chế tái tạo/thay thế phù hợp.

**Sai lầm 5 — Nhầm lựa chọn bean với lựa chọn hành vi mỗi giao dịch.**

`@Profile` hoặc `@ConditionalOnProperty` phù hợp để quyết định loại thành phần lúc khởi động. Nếu thuật toán phải khác nhau theo từng khách hàng hoặc từng đơn hàng khi runtime, hãy thiết kế strategy/dispatcher dựa trên dữ liệu nghiệp vụ; không tạo/dỡ Spring bean cho mỗi request.

**Sai lầm 6 — Lưu secret như một property công khai.**

Password và token có thể được bind qua cùng cơ chế cấu hình nhưng yêu cầu phân quyền, masking, rotation và tránh commit. Không dùng giá trị thật trong tài liệu, test snapshot hoặc log.

## 9. Thiết kế và kiểm thử theo đúng ranh giới

Một thiết kế dễ bảo trì thường có các ranh giới sau:

- **Lớp settings** gom property theo nhóm chức năng và biểu diễn đúng kiểu (`URI`, `Duration`, số nguyên, boolean). Các ràng buộc như timeout dương, URL hợp lệ có thể được kiểm tra khi khởi động.
- **Lớp configuration/bean factory** nối dependencies, chọn implementation phù hợp và cấu hình client; tránh chứa thuật toán nghiệp vụ phức tạp.
- **Service nghiệp vụ** nhận dependency qua constructor, đọc/ghi domain data qua repository và thực thi use case; tránh tự đọc biến môi trường hay tự tạo client phân tán ở mọi method.
- **Domain model và persistence** quản lý identity, trạng thái, quy tắc và vòng đời dữ liệu; việc xử lý transaction nằm ở ranh giới nghiệp vụ thích hợp.

Cách kiểm thử tương ứng:

1. **Configuration binding test:** cung cấp giá trị property riêng cho test, khẳng định `baseUrl` và `timeout` được bind đúng kiểu, phát hiện giá trị thiếu/sai nếu có validation.
2. **Bean wiring test:** tạo Spring context với cấu hình bật/tắt để kiểm tra `ShippingClient` có hoặc không được đăng ký đúng ý định; kiểm tra phụ thuộc bắt buộc có cấu hình thay thế khi tích hợp tắt.
3. **Business test:** đưa `ShippingOrder` cụ thể vào use case, stub gateway/repository khi cần và kiểm tra kết quả, thay đổi trạng thái, tính toàn vẹn hoặc exception nghiệp vụ. Không cần sửa YAML cho từng đơn hàng test.

Ví dụ chỉ riêng việc đổi timeout trong một test không thể thay thế kiểm thử “đơn hàng bị hủy không được gửi giao hàng”. Tương tự, mock một `ShippingClient` không kiểm chứng được binding của `shipping.gateway.timeout`. Mỗi bài test nên xác nhận đúng loại trách nhiệm mà nó đang kiểm tra.

## 10. Ghi nhớ qua một tình huống

Giả sử hệ thống đang gửi đơn hàng qua cổng giao hàng:

- Đội vận hành đổi timeout gọi cổng từ 3 lên 5 giây: **thay cấu hình ứng dụng**.
- Lập trình viên thay HTTP client bằng implementation khác và đăng ký bằng `@Bean`: **thay định nghĩa/wiring bean**.
- Khách hàng sửa địa chỉ nhận hàng trước khi đơn được gửi: **thay dữ liệu nghiệp vụ**.
- Nhân viên quản trị cập nhật bảng phí theo khu vực, có ngày hiệu lực: **thay chính sách/dữ liệu nghiệp vụ**, dù tên bảng có chữ “config”.
- Một property quyết định có tạo `ShippingClient` khi khởi động: **cấu hình điều khiển điều kiện đăng ký bean**, là điểm giao giữa hai lớp đầu.

Hãy giữ ba câu hỏi riêng biệt khi đọc mã Spring Boot: **ứng dụng nhận giá trị từ đâu; Spring dùng những định nghĩa nào để tạo thành phần; thành phần ấy xử lý dữ liệu nghiệp vụ nào**. Khi trả lời được cả ba, việc đặt property, bean và domain object vào đúng chỗ sẽ rõ ràng hơn.