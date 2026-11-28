# Unit test nghiệp vụ mà không khởi động terminal

Một command Spring Shell thường nhận option, chuyển dữ liệu đầu vào thành lời gọi service rồi định dạng kết quả để hiển thị. Quy tắc tính giá, kiểm tra trạng thái đơn hàng, áp dụng chiết khấu hoặc xác định quyền truy cập thuộc về nghiệp vụ. Những quy tắc đó cần được kiểm thử thường xuyên, nhưng không cần mở terminal, khởi động REPL hay tạo một Spring application context cho mỗi test.

Unit test nghiệp vụ gọi trực tiếp đối tượng cần kiểm tra, truyền dữ liệu đầu vào và xác nhận kết quả hoặc side effect. Các dependency bên ngoài như repository, cổng thanh toán hoặc dịch vụ tồn kho có thể được thay bằng mock hoặc fake. Test chạy nhanh, xác định và tập trung vào hành vi của lớp nghiệp vụ.

Trong Spring Shell 3.x, command là adapter giao tiếp với người dùng. Có thể kiểm thử service nghiệp vụ độc lập trước, sau đó kiểm thử method command bằng cách tạo command object và inject mock service. Những phần như phân tích cú pháp command, bind option, đăng ký command và output terminal cần một loại test khác ở tầng tích hợp.

Sau bài này, bạn có thể:

- Phân biệt unit test nghiệp vụ với command test và integration test.
- Viết test JUnit Jupiter mà không khởi động Spring context hoặc terminal.
- Dùng Mockito để thay dependency bên ngoài và AssertJ để kiểm tra kết quả.
- Kiểm thử quy tắc hợp lệ, biên, lỗi và tương tác với dependency.
- Kiểm thử command method như một adapter mà không giả lập terminal.
- Chọn fake, mock hoặc stub phù hợp.
- Nhận biết giới hạn của test gọi trực tiếp bean khi có transaction hoặc AOP proxy.
- Tổ chức test để chạy nhanh, ổn định và dễ bảo trì.

> Ví dụ dùng Java 17+, JUnit Jupiter 5, Mockito và AssertJ. Spring Shell 3.x chỉ xuất hiện ở lớp command; các unit test nghiệp vụ không cần khởi tạo Spring Shell.

## 1. Tách nghiệp vụ khỏi giao diện terminal

Hãy xét command:

~~~text
orders quote --customer-id C102 --sku BOOK-01 --quantity 2
~~~

Command nhận option, gọi service tính giá và trả kết quả. Việc parse `--quantity 2` thành số nguyên là trách nhiệm của Spring Shell. Việc tính subtotal, áp dụng chiết khấu và xác định tổng tiền là trách nhiệm của nghiệp vụ.

~~~mermaid
flowchart TD
    A[Người dùng nhập command] --> B[Spring Shell parser và argument binding]
    B --> C[OrderCommands]
    C --> D[OrderPricingService]
    D --> E[Quy tắc nghiệp vụ]
    E --> F[ProductCatalog / DiscountPolicy]
    F --> D
    D --> C
    C --> G[Kết quả hiển thị]
~~~

Unit test của `OrderPricingService` bắt đầu từ service và không đi qua các bước parser, terminal hoặc renderer. Nhờ vậy, khi quy tắc chiết khấu thay đổi, test không cần dựng một phiên shell chỉ để kiểm tra phép tính.

| Loại test | Phần được kiểm tra | Có cần terminal? | Có cần Spring context? |
|---|---|---:|---:|
| Unit test domain/service | Quy tắc nghiệp vụ trong một lớp hoặc nhóm nhỏ | Không | Không |
| Unit test command method | Logic chuyển option đã bind thành lời gọi service và thông báo | Không | Không |
| Spring Shell command test | Đăng ký command, parse tên lệnh/option và kết quả command | Thường không cần terminal vật lý; dùng test support | Thường có context test |
| Integration test | Nhiều bean, database, transaction, cấu hình hoặc hệ thống ngoài | Tùy mục tiêu | Thường có |
| End-to-end terminal test | Trải nghiệm nhập phím, prompt, terminal và output thực tế | Có | Có thể có |

Không cần kiểm thử tất cả các lớp bằng cùng một loại test. Hãy đặt test sát nơi quy tắc nằm: business rule được kiểm tra ở domain/service, còn parser và terminal được kiểm tra ở tầng Spring Shell.

## 2. Cấu hình test dependency

Nếu dự án dùng Spring Boot, `spring-boot-starter-test` thường cung cấp JUnit Jupiter, Mockito, AssertJ và các thư viện test phổ biến. Đặt dependency ở scope test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án không dùng Spring Boot starter, có thể khai báo riêng các thư viện cần thiết:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
~~~

Phiên bản dependency nên được quản lý bởi Spring Boot BOM hoặc dependency management của dự án để tránh ghép các phiên bản không tương thích.

Một test JUnit Jupiter thông thường chỉ cần:

~~~java
import org.junit.jupiter.api.Test;

class ExampleTest {

    @Test
    void calculatesExpectedValue() {
        // Arrange, Act, Assert.
    }
}
~~~

Không có `@SpringBootTest`, `SpringApplication.run(...)`, `Terminal`, `ShellTestClient` hoặc lệnh mở REPL trong test này. JUnit tạo test object, chạy method và kết thúc.

## 3. Ví dụ nghiệp vụ: tính báo giá đơn hàng

Tách các hợp đồng phụ thuộc bên ngoài khỏi service:

~~~java
import java.math.BigDecimal;

public interface ProductCatalog {
    BigDecimal unitPriceOf(String sku);
}

public interface DiscountPolicy {
    BigDecimal discountFor(String customerId, BigDecimal subtotal);
}
~~~

Định nghĩa dữ liệu:

~~~java
import java.math.BigDecimal;

public record OrderLine(String sku, int quantity) {
}

public record Quote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal total) {
}
~~~

Service chứa quy tắc nghiệp vụ:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class OrderPricingService {

    private static final BigDecimal ZERO = BigDecimal.ZERO;

    private final ProductCatalog catalog;
    private final DiscountPolicy discountPolicy;

    public OrderPricingService(
            ProductCatalog catalog,
            DiscountPolicy discountPolicy) {
        this.catalog = catalog;
        this.discountPolicy = discountPolicy;
    }

    public Quote calculate(String customerId, List<OrderLine> lines) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId không được để trống.");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Đơn hàng phải có ít nhất một dòng.");
        }

        BigDecimal subtotal = ZERO;
        for (OrderLine line : lines) {
            if (line == null || line.sku() == null || line.sku().isBlank()) {
                throw new IllegalArgumentException("SKU không hợp lệ.");
            }
            if (line.quantity() <= 0) {
                throw new IllegalArgumentException("Số lượng phải lớn hơn 0.");
            }

            BigDecimal unitPrice = Objects.requireNonNull(
                    catalog.unitPriceOf(line.sku()),
                    "Không tìm thấy giá sản phẩm.");
            if (unitPrice.signum() < 0) {
                throw new IllegalStateException("Giá sản phẩm không được âm.");
            }

            subtotal = subtotal.add(
                    unitPrice.multiply(BigDecimal.valueOf(line.quantity())));
        }

        BigDecimal discount = Objects.requireNonNull(
                discountPolicy.discountFor(customerId, subtotal),
                "DiscountPolicy phải trả về giá trị.");

        if (discount.signum() < 0 || discount.compareTo(subtotal) > 0) {
            throw new IllegalStateException("Mức chiết khấu không hợp lệ.");
        }

        return new Quote(subtotal, discount, subtotal.subtract(discount));
    }
}
~~~

Service không phụ thuộc vào Spring Shell, terminal hoặc application context. Nó nhận `ProductCatalog` và `DiscountPolicy` qua constructor, nên test có thể truyền mock hoặc fake.

Trong dự án thật, có thể thay `IllegalArgumentException` và `IllegalStateException` bằng exception nghiệp vụ có tên rõ ràng. Ví dụ này giữ code ngắn để tập trung vào cách tổ chức test.

## 4. Viết unit test với JUnit, Mockito và AssertJ

Test dùng `MockitoExtension` để khởi tạo mock và inject chúng vào service. Extension này chạy cùng JUnit Jupiter, không khởi động Spring:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderPricingServiceTest {

    @Mock
    ProductCatalog catalog;

    @Mock
    DiscountPolicy discountPolicy;

    @InjectMocks
    OrderPricingService service;

    @Test
    void calculatesSubtotalDiscountAndTotal() {
        when(catalog.unitPriceOf("BOOK-01"))
                .thenReturn(new BigDecimal("12.50"));
        when(discountPolicy.discountFor(
                "C102", new BigDecimal("25.00")))
                .thenReturn(new BigDecimal("2.50"));

        Quote quote = service.calculate(
                "C102",
                List.of(new OrderLine("BOOK-01", 2)));

        assertThat(quote.subtotal()).isEqualByComparingTo("25.00");
        assertThat(quote.discount()).isEqualByComparingTo("2.50");
        assertThat(quote.total()).isEqualByComparingTo("22.50");

        verify(catalog).unitPriceOf("BOOK-01");
        verify(discountPolicy).discountFor(
                "C102", new BigDecimal("25.00"));
    }
}
~~~

Test có ba phần:

1. **Arrange:** định nghĩa giá trả về từ catalog và mức chiết khấu.
2. **Act:** gọi `service.calculate(...)` trực tiếp.
3. **Assert:** kiểm tra subtotal, discount, total và những dependency được gọi.

`isEqualByComparingTo` phù hợp với `BigDecimal` khi muốn so sánh giá trị số mà không phụ thuộc scale. Ví dụ `25.0` và `25.00` có cùng giá trị dù `equals()` của `BigDecimal` phân biệt scale.

### Kiểm tra đầu vào không hợp lệ

Quy tắc đầu vào nên được kiểm thử mà không cần tạo mock behavior không liên quan:

~~~java
@Test
void rejectsAnEmptyOrder() {
    assertThatThrownBy(() -> service.calculate("C102", List.of()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("ít nhất một dòng");

    verifyNoInteractions(catalog, discountPolicy);
}
~~~

Test xác nhận service từ chối đơn hàng rỗng trước khi truy cập catalog hoặc discount policy. Điều này vừa kiểm tra kết quả vừa xác nhận thứ tự xử lý quan trọng.

### Kiểm tra số lượng ở biên

~~~java
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(ints = {0, -1, -10})
void rejectsNonPositiveQuantity(int quantity) {
    assertThatThrownBy(() -> service.calculate(
            "C102",
            List.of(new OrderLine("BOOK-01", quantity))))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Số lượng phải lớn hơn 0");

    verifyNoInteractions(catalog, discountPolicy);
}
~~~

Parameterized test chạy cùng một quy tắc với nhiều giá trị biên. Cách này ngắn và rõ hơn việc sao chép nhiều test gần giống nhau.

### Kiểm tra kết quả từ dependency không hợp lệ

~~~java
@Test
void rejectsDiscountGreaterThanSubtotal() {
    when(catalog.unitPriceOf("BOOK-01"))
            .thenReturn(new BigDecimal("10.00"));
    when(discountPolicy.discountFor(
            "C102", new BigDecimal("10.00")))
            .thenReturn(new BigDecimal("12.00"));

    assertThatThrownBy(() -> service.calculate(
            "C102",
            List.of(new OrderLine("BOOK-01", 1))))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("chiết khấu không hợp lệ");
}
~~~

Test này kiểm tra service không chấp nhận kết quả sai từ dependency. Nếu policy là thành phần do cùng nhóm phát triển, test giúp phát hiện lỗi phối hợp giữa các lớp. Không cần mock mọi method; chỉ mock những ranh giới mà test cần điều khiển.

## 5. Khi nào dùng mock, fake hoặc stub?

Mock không phải lựa chọn duy nhất. Chọn test double theo mục đích:

| Loại | Đặc điểm | Dùng khi |
|---|---|---|
| Stub | Trả dữ liệu đã định trước | Cần cung cấp đầu vào từ dependency |
| Mock | Có thể kiểm tra lời gọi và argument | Hành vi tương tác là một phần hợp đồng cần xác nhận |
| Fake | Implementation đơn giản nhưng chạy được, thường giữ dữ liệu trong bộ nhớ | Cần test nhiều quy tắc với dependency có hành vi thực |
| Spy | Bao quanh một đối tượng thật và quan sát một phần lời gọi | Cần theo dõi một tương tác cụ thể mà vẫn dùng implementation thật |

Ví dụ fake catalog:

~~~java
import java.math.BigDecimal;
import java.util.Map;

class InMemoryProductCatalog implements ProductCatalog {

    private final Map<String, BigDecimal> prices;

    InMemoryProductCatalog(Map<String, BigDecimal> prices) {
        this.prices = Map.copyOf(prices);
    }

    @Override
    public BigDecimal unitPriceOf(String sku) {
        BigDecimal price = prices.get(sku);
        if (price == null) {
            throw new IllegalArgumentException("SKU không tồn tại: " + sku);
        }
        return price;
    }
}
~~~

Test có thể dùng fake để kiểm tra một nhóm quy tắc giá với nhiều sản phẩm:

~~~java
@Test
void calculatesTotalForSeveralProducts() {
    ProductCatalog catalog = new InMemoryProductCatalog(Map.of(
            "BOOK-01", new BigDecimal("12.50"),
            "PEN-02", new BigDecimal("3.00")));

    DiscountPolicy noDiscount = (customerId, subtotal) -> BigDecimal.ZERO;
    OrderPricingService service = new OrderPricingService(catalog, noDiscount);

    Quote quote = service.calculate("C102", List.of(
            new OrderLine("BOOK-01", 2),
            new OrderLine("PEN-02", 3)));

    assertThat(quote.total()).isEqualByComparingTo("34.00");
}
~~~

Fake thường phù hợp khi muốn kiểm tra một nhóm đối tượng cộng tác mà không cần xác minh từng lời gọi. Mock hữu ích khi cần bảo đảm một dependency được gọi với đúng tham số hoặc không được gọi khi đầu vào sai.

## 6. Kiểm thử command method mà không dựng terminal

Command là adapter giữa Spring Shell và service. Nếu command method nhận tham số Java thông thường, có thể gọi method trực tiếp bằng unit test. Tạo command object bằng constructor và truyền mock service:

~~~java
@ShellComponent
public class OrderCommands {

    private final OrderPricingService pricingService;

    public OrderCommands(OrderPricingService pricingService) {
        this.pricingService = pricingService;
    }

    @ShellMethod(key = "orders quote", value = "Tính báo giá đơn hàng.")
    public String quote(
            @ShellOption("--customer-id") String customerId,
            @ShellOption("--sku") String sku,
            @ShellOption("--quantity") int quantity) {

        Quote quote = pricingService.calculate(
                customerId,
                List.of(new OrderLine(sku, quantity)));

        return "Tổng tiền: " + quote.total().toPlainString();
    }
}
~~~

Test command:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class OrderCommandsTest {

    @Test
    void delegatesToPricingServiceAndFormatsTheResult() {
        OrderPricingService pricingService =
                Mockito.mock(OrderPricingService.class);

        when(pricingService.calculate(eq("C102"), anyList()))
                .thenReturn(new Quote(
                        new BigDecimal("25.00"),
                        new BigDecimal("2.50"),
                        new BigDecimal("22.50")));

        OrderCommands commands = new OrderCommands(pricingService);

        String output = commands.quote("C102", "BOOK-01", 2);

        assertThat(output).isEqualTo("Tổng tiền: 22.50");
        verify(pricingService).calculate(
                eq("C102"),
                eq(List.of(new OrderLine("BOOK-01", 2))));
    }
}
~~~

Test này kiểm tra method command gọi service với dữ liệu đã bind và định dạng chuỗi trả về. Nó không kiểm tra Spring Shell có parse đúng câu lệnh `orders quote --customer-id C102 ...` hay không. Khi gọi method Java trực tiếp, annotation `@ShellMethod` và `@ShellOption` chỉ là metadata; parser không tham gia.

Nếu command method chỉ chuyển tiếp tham số và trả về kết quả, có thể không cần nhiều test cho từng dòng code. Hãy tập trung vào mapping, thông báo lỗi hoặc quy tắc chuyển đổi thực sự có ý nghĩa.

## 7. Giữ quy tắc nghiệp vụ ở service thay vì command

Một dấu hiệu thiết kế chưa tốt là command chứa nhiều phép tính hoặc quyết định nghiệp vụ:

~~~java
@ShellMethod(key = "orders discount")
public String discount(String customerId, BigDecimal amount) {
    if (amount.compareTo(new BigDecimal("100")) > 0) {
        amount = amount.multiply(new BigDecimal("0.9"));
    }
    // Nhiều quy tắc khác...
    return amount.toPlainString();
}
~~~

Khi quy tắc nằm trong command, test phải tạo command object và có thể bị ràng buộc với cách trình bày CLI. Nếu sau này nghiệp vụ được gọi từ REST API hoặc scheduler, logic có nguy cơ bị sao chép.

Đưa quy tắc vào service hoặc domain object:

~~~java
public class DiscountCalculator {

    public BigDecimal apply(BigDecimal amount) {
        if (amount.compareTo(new BigDecimal("100")) > 0) {
            return amount.multiply(new BigDecimal("0.9"));
        }
        return amount;
    }
}
~~~

Sau đó unit test trực tiếp `DiscountCalculator`. Command chỉ nhận input, gọi service và trình bày kết quả. Cách này giúp test không phụ thuộc terminal và giữ cùng một quy tắc cho mọi adapter.

## 8. Kiểm thử exception và thông báo lỗi

Service nên ném exception mô tả lỗi nghiệp vụ; command hoặc lớp giao diện quyết định cách trình bày. Có thể kiểm tra loại exception và dữ liệu liên quan:

~~~java
@Test
void rejectsUnknownProduct() {
    when(catalog.unitPriceOf("UNKNOWN"))
            .thenThrow(new ProductNotFoundException("UNKNOWN"));

    assertThatThrownBy(() -> service.calculate(
            "C102",
            List.of(new OrderLine("UNKNOWN", 1))))
            .isInstanceOf(ProductNotFoundException.class)
            .hasMessageContaining("UNKNOWN");
}
~~~

Không nên chỉ kiểm tra exception có xuất hiện mà bỏ qua trường hợp nào gây ra nó. Hãy xác nhận exception đúng, thông tin cần thiết được giữ và dependency không bị gọi thêm sau khi lỗi đã xảy ra.

Nếu command bắt exception để trả thông báo thân thiện, viết một test command riêng cho mapping đó. Không cần khởi động terminal để xác nhận một chuỗi kết quả được trả về đúng.

Không đưa stack trace, password, token hoặc dữ liệu nhạy cảm vào thông báo lỗi dành cho người dùng. Test có thể xác nhận thông báo công khai không chứa những trường dữ liệu đó.

## 9. Kiểm thử thời gian, random và file mà không khởi động ứng dụng

Một unit test ổn định không nên phụ thuộc vào thời điểm thực, mạng hoặc thư mục cá nhân của người phát triển. Đưa các nguồn biến động thành dependency có thể thay thế:

| Nguồn biến động | Cách làm dễ kiểm thử |
|---|---|
| Thời gian hiện tại | Inject `Clock`, dùng `Clock.fixed(...)` trong test |
| Sinh ID ngẫu nhiên | Inject generator hoặc supplier |
| HTTP/API bên ngoài | Inject client interface và dùng mock/fake |
| Database | Unit test service với repository mock; dùng integration test riêng cho truy vấn thật |
| File system | Inject interface lưu trữ hoặc dùng thư mục tạm của JUnit |
| Process bên ngoài | Inject process runner interface; không chạy executable thật trong unit test |
| Environment variable | Inject cấu hình qua constructor hoặc configuration object |

Ví dụ với `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-10-01T00:00:00Z"),
        ZoneOffset.UTC);
~~~

Service dùng clock được inject có thể kiểm tra hạn mức theo ngày hoặc thời gian hết hạn mà không phải chờ đồng hồ thật.

Với file system, JUnit có `@TempDir` để cấp thư mục tạm cho test. Ví dụ, một writer nhỏ nhận thư mục đích thay vì tự chọn một đường dẫn cố định:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class CsvFileWriter {

    Path write(Path directory, String fileName, String content)
            throws IOException {
        Path output = directory.resolve(fileName);
        return Files.writeString(output, content, StandardCharsets.UTF_8);
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CsvFileWriterTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void writesCsvToTheProvidedDirectory() throws IOException {
        CsvFileWriter writer = new CsvFileWriter();

        Path output = writer.write(
                temporaryDirectory,
                "orders.csv",
                "id,total\n1024,22.50\n");

        assertThat(Files.readString(output, StandardCharsets.UTF_8))
                .isEqualTo("id,total\n1024,22.50\n");
    }
}
~~~

Test dùng file tạm vẫn là test chạy ở mức file system, nhưng không cần terminal hoặc Spring context. Hãy dùng nó khi hành vi ghi/đọc file là một phần quan trọng của contract.

## 10. Điều unit test không chứng minh

Khi tạo service bằng `new` hoặc dùng `@InjectMocks`, test gọi trực tiếp target object. Đây là điều mong muốn để kiểm tra quy tắc nghiệp vụ, nhưng có những cơ chế Spring không được kích hoạt:

- `@Transactional` không được áp dụng qua transaction proxy.
- `@PreAuthorize` và method security proxy không tự chạy.
- `@Cacheable`, `@Async`, retry advice và các interceptor khác không được kích hoạt chỉ vì annotation xuất hiện.
- Dependency injection, bean lifecycle, configuration binding và auto-configuration không được kiểm tra.
- Spring Shell parser, command discovery, option binding, availability và terminal rendering không được kiểm tra.

Ví dụ, test tạo `new DefaultOrderService(...)` có thể xác nhận công thức tính giá. Nó không chứng minh transaction manager đã mở transaction hoặc dữ liệu được rollback khi exception xảy ra.

Hãy bổ sung test ở đúng tầng cho những điều cần kiểm chứng:

| Điều cần xác nhận | Loại test phù hợp |
|---|---|
| Quy tắc tính giá và chiết khấu | Unit test service/domain |
| Service bean được inject và proxy hoạt động | Spring context/integration test |
| `@Transactional` commit/rollback với database | Integration test có transaction manager và database phù hợp |
| `@PreAuthorize` từ chối principal thiếu authority | Spring Security method test hoặc integration test |
| Spring Shell parse command và bind option | Spring Shell command test support |
| Terminal hiển thị prompt, màu và phím tương tác | Terminal/end-to-end test |

Không cần biến mọi unit test thành `@SpringBootTest`. Dùng Spring context ở những test cần xác nhận hành vi do container cấu hình.

## 11. Những lỗi thường gặp khi viết unit test

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test chậm dù chỉ kiểm tra phép tính | Khởi động toàn bộ Spring Boot context | Gọi trực tiếp service và mock dependency |
| Test cần nhập phím hoặc chờ prompt | Đang kiểm thử nghiệp vụ qua terminal | Tách business logic khỏi command và test service |
| Test phụ thuộc database dùng chung | Unit test kết nối database thật | Mock repository hoặc dùng fake; dành database thật cho integration test |
| Test thất bại ngẫu nhiên theo thời gian | Dùng `now()` trực tiếp trong logic | Inject `Clock` và cố định thời gian trong test |
| Verify quá nhiều lời gọi nội bộ | Test phụ thuộc implementation | Ưu tiên assert kết quả và side effect quan trọng |
| Mock cả đối tượng nghiệp vụ | Test không còn thực thi quy tắc cần kiểm tra | Tạo domain object thật, chỉ mock ranh giới bên ngoài |
| Dùng `@InjectMocks` nhưng thiếu dependency | Constructor hoặc mock setup không khớp | Tạo service bằng constructor tường minh nếu cần |
| Test `@Transactional` bằng cách gọi `new` | Không có proxy hoặc transaction manager | Dùng integration test với Spring context |
| Test command method nhưng kỳ vọng parser hoạt động | Gọi method Java trực tiếp | Dùng Spring Shell command test cho parsing và binding |
| Test chỉ kiểm tra một kết quả thành công | Bỏ qua đầu vào biên và lỗi | Bổ sung test cho rỗng, null, giá trị biên và dependency failure |
| Test kiểm tra chuỗi quá chi tiết | Gắn chặt với cách trình bày không quan trọng | Kiểm tra phần thông tin có ý nghĩa với người dùng |

## 12. Checklist viết unit test nghiệp vụ

- Đặt quy tắc nghiệp vụ trong domain/service, không để chúng phụ thuộc terminal.
- Tạo đối tượng cần test trực tiếp bằng constructor.
- Chỉ mock dependency bên ngoài ranh giới đang kiểm tra.
- Dùng fake khi cần implementation nhỏ, xác định và có hành vi thực.
- Viết test theo Arrange – Act – Assert.
- Kiểm tra kết quả bằng AssertJ hoặc assertion của JUnit.
- Kiểm tra exception và trường hợp đầu vào biên.
- Xác nhận dependency quan trọng được gọi đúng hoặc không được gọi.
- Dùng `BigDecimal` cho tiền và so sánh theo giá trị số.
- Inject `Clock`, ID generator và các nguồn biến động.
- Không dùng `@SpringBootTest` cho test chỉ cần một lớp Java.
- Không kỳ vọng transaction/AOP proxy hoạt động khi gọi target object trực tiếp.
- Tách command method test khỏi parser/terminal test.
- Dùng integration test riêng để xác nhận Spring wiring, proxy, database và command registration.

## 13. Bài tập thực hành

Tạo unit test cho command `orders quote` và service tính giá:

1. Tạo `OrderPricingService` nhận `ProductCatalog` và `DiscountPolicy` qua constructor.
2. Viết test tính subtotal, discount và total cho một đơn hàng hợp lệ.
3. Viết test từ chối customer ID rỗng và danh sách dòng hàng rỗng.
4. Viết parameterized test cho quantity bằng 0 và số âm.
5. Viết test từ chối giá sản phẩm âm hoặc mức chiết khấu lớn hơn subtotal.
6. Dùng `MockitoExtension` để tạo mock dependency và `verify` lời gọi quan trọng.
7. Viết một fake `ProductCatalog` để kiểm thử nhiều dòng hàng mà không cần mock từng lần gọi.
8. Tạo `OrderCommands` bằng constructor với mock service; gọi method `quote(...)` trực tiếp và kiểm tra chuỗi trả về.
9. Xác nhận test command không kiểm tra parser, option binding hoặc terminal.
10. Chạy toàn bộ unit test bằng Maven/Gradle test task mà không mở Spring Shell REPL.
11. Liệt kê những điều cần một integration test riêng: transaction proxy, method security, database và command registration.

Khi hoàn thành, giải thích vì sao test service trực tiếp bằng `new` là phù hợp cho business rule, nhưng không thể chứng minh `@Transactional` đã hoạt động.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Testing](https://docs.spring.io/spring-shell/reference/3.3/testing.html): test command và các tiện ích kiểm thử của Spring Shell.
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): các cấp độ kiểm thử và test support của Spring Boot.
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter, parameterized tests và extension model.
- [Mockito – MockitoExtension API](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html): tích hợp Mockito với JUnit Jupiter.
- [Mockito – Documentation](https://site.mockito.org/): mock, stub, verify và test doubles.
- [AssertJ – Core](https://assertj.github.io/doc/): fluent assertions cho Java.
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): giới hạn và hành vi của transaction proxy cần kiểm thử ở tầng tích hợp.
