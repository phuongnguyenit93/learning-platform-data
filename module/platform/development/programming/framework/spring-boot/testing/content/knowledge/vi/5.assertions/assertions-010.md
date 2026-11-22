# Viết assertion có giá trị: tránh luôn đúng, quá yếu và phụ thuộc chi tiết không liên quan

> **Module:** Spring Boot – testing  
> **Chủ đề cha:** Assertion  
> **Mục tiêu:** Viết assertion kiểm tra đúng hợp đồng hành vi, đủ mạnh để phát hiện regression, rõ ràng khi thất bại và bền trước những thay đổi triển khai không làm đổi hành vi. Ví dụ sử dụng Java 17+, JUnit Jupiter, AssertJ, Mockito và Spring Boot.

## 1. Assertion là một “lời hứa” có thể bị bác bỏ

Trong test tự động, **assertion** so sánh hành vi quan sát được của đối tượng đang kiểm tra (*actual*) với kỳ vọng độc lập (*expected*) xuất phát từ yêu cầu hoặc hợp đồng hệ thống. Nếu hành vi sai, ít nhất một assertion quan trọng phải thất bại.

Một test có thể **chạy xanh nhưng không chứng minh điều gì**:

```java
@Test
void misleadingTest() {
    int result = 2 + 2;
    assertTrue(true);
    assertEquals(result, result);
}
```

Hai assertion luôn pass với mọi giá trị của `result`. Đổi logic từ cộng sang trừ cũng không bị bắt. Ví dụ này minh họa một phương thức JUnit đặt trong test class có import phù hợp, **không phải chương trình Java độc lập**.

Với hợp đồng “2 + 2 = 4”, viết:

```java
@Test
void addsTwoNumbers() {
    int actual = calculator.add(2, 2);
    assertEquals(4, actual);
}
```

Ở đây `4` là kỳ vọng từ yêu cầu và `actual` là kết quả của **mã đang kiểm tra**. Đoạn này là minh họa, giả định có `calculator`; dự án chạy được ở phần 4.

Để tự đánh giá assertion, đặt ba câu hỏi:

1. **Nếu phương thức trả sai thì assertion có fail không?** Nếu thay kết quả bằng `null`, `0`, rỗng, giá trị khác biên hoặc sai trạng thái mà test vẫn xanh, assertion có thể quá yếu.
2. **Expected có độc lập với actual không?** Nếu expected được tính lại từ cùng kết quả hoặc cùng hàm đang kiểm tra, test dễ thành vòng tròn xác nhận.
3. **Assertion có bám đúng hợp đồng quan sát được không?** Nếu chỉ đổi thứ tự nội bộ, tên class, ID sinh tự động hay log mà tính năng vẫn đúng, test không nên fail trừ khi chính thứ đó là một phần hợp đồng.

**Một assertion tốt vừa nhạy với lỗi thực vừa không nhạy quá mức với chi tiết không liên quan.** Không đánh giá chất lượng bằng việc đếm bao nhiêu dòng `assertEquals`.

## 2. Ba loại assertion cần tránh

### 2.1. Assertion luôn đúng (tautology)

Ví dụ sai:

```java
assertTrue(true);
assertEquals(actual, actual);
assertNotNull(new Object());
assertTrue(result == null || result != null);
assertEquals(items.size(), items.size());
```

Những biểu thức này không có *oracle* độc lập, tức tiêu chuẩn để biết kết quả đúng hay sai. Ngay cả khi gọi hàm thật, so sánh kết quả với chính nó vẫn không bảo vệ logic.

Một trường hợp tinh vi hơn:

```java
int expected = service.calculateTotal(cart);
int actual = service.calculateTotal(cart);
assertEquals(expected, actual);
```

Nếu hàm sai một cách ổn định, hai lần gọi vẫn có thể trả cùng giá trị sai và test pass. **Không lấy đầu ra của chính hàm dưới test để tạo expected**, trừ trường hợp đang kiểm tra tính nhất quán/idempotency có chủ đích và còn các assertion khác xác lập hợp đồng.

Một lỗi mock rất phổ biến:

```java
when(repository.findById(7L)).thenReturn(Optional.of(book));
assertEquals(Optional.of(book), repository.findById(7L));
```

Test chỉ xác nhận Mockito trả lại giá trị đã stub. Đối tượng cần kiểm tra là `service`, thì phải **gọi service**, rồi assert đầu ra/hệ quả của service. Mock chỉ là phụ thuộc thay thế, không phải bằng chứng service hoạt động.

### 2.2. Assertion quá yếu

Assertion có thể fail trong vài trường hợp nhưng vẫn cho phép rất nhiều hành vi sai:

```java
assertNotNull(receipt);             // Receipt có thể chứa total = 0.
assertTrue(total.signum() >= 0);    // Mọi số không âm đều được chấp nhận.
assertFalse(responseBody.isEmpty()); // Một JSON lỗi vẫn không rỗng.
assertTrue(statusCode < 500);       // 400/404 cũng có thể pass.
assertDoesNotThrow(() -> service.quote(lines)); // Chưa kiểm tra tổng tiền.
```

Các assertion này **không sai về cú pháp** và có thể đúng khi chính tính chất “không null”, “không ném lỗi” hoặc “không lỗi server” là yêu cầu. Nhưng nếu hợp đồng là “đơn hàng 100.00 được giảm 10.00, phải trả 90.00”, chúng không đủ.

Thay bằng những kết quả có ý nghĩa:

```java
Quote actual = service.quote(List.of(
        new CartLine("SKU-1", new BigDecimal("100.00"), 1)));

assertAll("quote at discount threshold",
        () -> assertEquals(new BigDecimal("100.00"), actual.subtotal()),
        () -> assertEquals(new BigDecimal("10.00"), actual.discount()),
        () -> assertEquals(new BigDecimal("90.00"), actual.total()));
```

Đây là đoạn minh họa nằm trong test class với imports cần thiết. Các class `Quote`, `CartLine`, `QuoteService` hoàn chỉnh được định nghĩa ở phần 4. Vì quy tắc giảm giá và tổng tiền đều nằm trong hợp đồng, kiểm tra cả ba trường giúp phát hiện các loại sai khác nhau.

### 2.3. Assertion phụ thuộc chi tiết không liên quan

Ví dụ:

- Giao diện chỉ yêu cầu danh sách sản phẩm **không sắp xếp**, nhưng test lại assert thứ tự chính xác; thay đổi thứ tự truy vấn hợp lệ làm test đỏ.
- API cho phép ID duy nhất do DB sinh, nhưng test đòi ID phải là `1`; chạy cùng dữ liệu khác làm test đỏ.
- Contract yêu cầu số tiền là 90.00, nhưng test bắt JSON có khoảng trắng hoặc thứ tự field y như một chuỗi cố định; việc đổi serializer hợp lệ làm test đỏ.
- Yêu cầu chỉ là có gửi email xác nhận, nhưng test assert gọi **ba** phương thức helper nội bộ theo một thứ tự nhất định dù hành vi ngoài không đổi.
- Test xác nhận chính xác timestamp `Instant.now()` của máy chạy, thay vì cung cấp `Clock` cố định hoặc kiểm tra đặc tính thật của timestamp.
- Test assert toàn bộ stack trace, câu chữ log hoặc tên class implementation dù không là giao diện/hợp đồng công khai.

Quy tắc: **assert kết quả quan sát được ở đúng ranh giới đang kiểm thử**. Chỉ assert thứ tự, thời điểm, định dạng, số lần gọi hoặc tên chi tiết khi chúng **đúng là một phần yêu cầu**.

## 3. Từ yêu cầu sang assertion có sức phát hiện lỗi

Trước khi viết code, đổi từng yêu cầu thành ví dụ đầu vào/đầu ra hoặc thay đổi trạng thái có thể quan sát.

Giả sử chức năng báo giá giỏ hàng có quy tắc:

1. Mỗi dòng: `unitPrice × quantity`.
2. Tổng tạm tính là tổng tiền của tất cả dòng, làm tròn về hai chữ số thập phân bằng `HALF_UP`.
3. Nếu subtotal **từ 100.00 trở lên**, được giảm **10%**; dưới ngưỡng không giảm.
4. Tổng thanh toán là `subtotal - discount`.
5. Giỏ trống, số lượng không dương hoặc đơn giá âm là không hợp lệ.

Thiết kế bảng ví dụ **trước khi viết assertion**:

| Tình huống | Đầu vào | Subtotal | Discount | Total | Mục tiêu phát hiện |
| --- | --- | ---: | ---: | ---: | --- |
| Dưới ngưỡng | 1 × 99.99 | 99.99 | 0.00 | 99.99 | Không giảm sai trước ngưỡng |
| Đúng ngưỡng | 1 × 100.00 | 100.00 | 10.00 | 90.00 | Nhánh `>= 100` |
| Trên ngưỡng | 1 × 120.00 | 120.00 | 12.00 | 108.00 | Tính đúng phần trăm |
| Nhiều số lượng | 3 × 20.00 | 60.00 | 0.00 | 60.00 | Không bỏ qua quantity |
| Tổng nhiều dòng | 2 × 40.00 + 1 × 20.00 | 100.00 | 10.00 | 90.00 | Không chỉ tính dòng đầu |
| Giỏ trống | `[]` | — | — | — | Phải báo lỗi đầu vào |
| Số lượng `0` | 1 dòng có quantity 0 | — | — | — | Không được nhận dữ liệu không hợp lệ |

Một test chỉ có `assertNotNull(quote)` sẽ **không phân biệt** được các kết quả 90.00, 100.00 hay 0.00. Một test so sánh ba giá trị của Quote và có case ở hai bên ngưỡng sẽ bắt được nhiều thay đổi sai.

Đừng chép công thức tính tiền nguyên xi vào test rồi dùng công thức đó làm expected một cách vô thức. Với dữ liệu nhỏ trong bảng, expected được tính **độc lập từ quy tắc nghiệp vụ** và giữ cố định trong test. Khi công thức nghiệp vụ phức tạp, có thể dùng bảng golden examples đã được review, reference implementation độc lập, property-based testing hoặc kiểm tra tính chất bất biến (*invariant*) tùy yêu cầu.

## 4. Dự án Java 17 / Spring Boot 3.5 / JUnit Jupiter chạy được

Ví dụ dưới đây có thể dùng để thực hành. Nó vừa làm rõ hợp đồng báo giá vừa cho thấy **assertion ở unit test, MVC slice test và integration test phải kiểm tra đúng ranh giới của mỗi mức**.

Cấu trúc project Maven:

```text
assertion-quality/
├── pom.xml
└── src/
    ├── main/java/com/example/quality/
    │   ├── AssertionQualityApplication.java
    │   ├── CartLine.java
    │   ├── Quote.java
    │   ├── QuoteService.java
    │   └── QuoteController.java
    └── test/java/com/example/quality/
        ├── QuoteServiceTest.java
        ├── QuoteControllerSliceTest.java
        └── QuoteIntegrationTest.java
```

### 4.1. Maven

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>assertion-quality</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Starter test cung cấp JUnit Jupiter, AssertJ, Mockito, Spring Test và các helper test phổ biến. Trong project này không có database hoặc security; lỗi của những thành phần đó nằm ngoài phạm vi minh họa. Dòng Spring Boot 3.5 dùng `jakarta.*` khi cần Jakarta API, và Spring Framework 6.2 cung cấp `@MockitoBean`.

### 4.2. Mã ứng dụng

```java
// AssertionQualityApplication.java
package com.example.quality;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssertionQualityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssertionQualityApplication.class, args);
    }
}
```

```java
// CartLine.java
package com.example.quality;

import java.math.BigDecimal;

public record CartLine(String sku, BigDecimal unitPrice, int quantity) {}
```

```java
// Quote.java
package com.example.quality;

import java.math.BigDecimal;

public record Quote(BigDecimal subtotal, BigDecimal discount,
                    BigDecimal total) {}
```

```java
// QuoteService.java
package com.example.quality;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private static final BigDecimal THRESHOLD = new BigDecimal("100.00");
    private static final BigDecimal RATE = new BigDecimal("0.10");

    public Quote quote(List<CartLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Cart must not be empty");
        }
        for (CartLine line : lines) {
            if (line == null || line.unitPrice() == null
                    || line.unitPrice().signum() < 0
                    || line.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid cart line");
            }
        }

        BigDecimal subtotal = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal discount = subtotal.compareTo(THRESHOLD) >= 0
                ? subtotal.multiply(RATE).setScale(2, RoundingMode.HALF_UP)
                : new BigDecimal("0.00");

        return new Quote(subtotal, discount, subtotal.subtract(discount));
    }
}
```

```java
// QuoteController.java
package com.example.quality;

import java.util.List;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping("/checkout/quote")
    public Quote quote(@RequestBody List<CartLine> lines) {
        return service.quote(lines);
    }
}
```

Mã service dùng hai chữ số thập phân theo hợp đồng của ví dụ. Controller nhận JSON array và trả JSON object có `subtotal`, `discount`, `total`. Với request hợp lệ, HTTP status mặc định là **200 OK**. Trong dự án thực tế, nên định nghĩa validation/error mapping phù hợp (ví dụ trả HTTP 400 cho đầu vào không hợp lệ); ví dụ này chỉ assert lỗi đầu vào ở **tầng service**, không tuyên bố controller đã xử lý 400.

### 4.3. Unit test: assert giá trị nghiệp vụ, không chỉ khác `null`

```java
// QuoteServiceTest.java
package com.example.quality;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

class QuoteServiceTest {
    private final QuoteService service = new QuoteService();

    @ParameterizedTest
    @CsvSource({
        "99.99, 99.99, 0.00, 99.99",
        "100.00, 100.00, 10.00, 90.00",
        "120.00, 120.00, 12.00, 108.00"
    })
    void appliesDiscountAtTheCorrectBoundary(
            String price, String expectedSubtotal,
            String expectedDiscount, String expectedTotal) {

        Quote actual = service.quote(List.of(
                new CartLine("SKU-1", new BigDecimal(price), 1)));

        assertAll("quote must follow the business rules",
                () -> assertEquals(new BigDecimal(expectedSubtotal),
                        actual.subtotal(), "subtotal"),
                () -> assertEquals(new BigDecimal(expectedDiscount),
                        actual.discount(), "discount"),
                () -> assertEquals(new BigDecimal(expectedTotal),
                        actual.total(), "total"));
    }

    @Test
    void accountsForAllLinesAndQuantities() {
        Quote actual = service.quote(List.of(
                new CartLine("A", new BigDecimal("40.00"), 2),
                new CartLine("B", new BigDecimal("20.00"), 1)));

        assertEquals(new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("10.00"),
                new BigDecimal("90.00")), actual);
    }

    @Test
    void rejectsEmptyCartWithRelevantException() {
        IllegalArgumentException error = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(List.of()));

        assertEquals("Cart must not be empty", error.getMessage());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.quote(List.of(
                        new CartLine("A", new BigDecimal("20.00"), 0))));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.quote(List.of(
                        new CartLine("A", new BigDecimal("-1.00"), 1))));
    }
}
```

**Vì sao các assertion này có giá trị?**

- Ba dòng dữ liệu kiểm tra **dưới ngưỡng, đúng ngưỡng, trên ngưỡng**; nếu lập trình viên lỡ đổi `>=` thành `>`, case 100.00 sẽ fail.
- Test nhiều dòng sẽ fail nếu service chỉ lấy dòng đầu, bỏ qua quantity hoặc tính sai discount.
- `assertEquals(new Quote(...), actual)` dựa vào **record equality theo các component**; nó kiểm tra ba giá trị chính mà không cần so sánh từng field thủ công. Nếu thay record bằng class thông thường không có `equals` theo giá trị, phải assert từng field hoặc dùng AssertJ field extraction.
- `assertThrowsExactly` khẳng định **đúng loại exception**; `assertThrows` chấp nhận cả subclass nên phù hợp khi hợp đồng chỉ yêu cầu họ exception.
- Message `"Cart must not be empty"` chỉ nên assert chính xác nếu coi nó là một phần contract/mức chẩn đoán quan trọng. Nếu văn bản có thể đổi vì localization/biên tập, assert exception type và mã lỗi ổn định sẽ ít giòn hơn.
- Không assert tên method/private helper hay số lần stream `map` chạy; đó là triển khai nội bộ.

Trong ví dụ, phép tính cho `100.00` trả `Quote(100.00, 10.00, 90.00)` theo cách biểu diễn giá trị của `BigDecimal`. **Đây là giá trị hợp đồng cố định của test, không phải stdout của Maven.**

### 4.4. MVC slice: assert status, contract JSON và binding có ý nghĩa

`@WebMvcTest` nạp lớp MVC cần thiết và mock service. Vì service **không chạy thật**, một test slice phải assert controller nhận đúng request, trả đúng status và serialization, chứ không dùng kết quả mock để tuyên bố đã kiểm tra công thức giảm giá.

```java
// QuoteControllerSliceTest.java
package com.example.quality;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    QuoteService service;

    @Test
    void bindsRequestAndRendersQuoteContract() throws Exception {
        when(service.quote(anyList())).thenReturn(new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("10.00"),
                new BigDecimal("90.00")));

        mockMvc.perform(post("/checkout/quote")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                [{"sku":"A","unitPrice":100.00,"quantity":1}]
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotal").value(100.0))
                .andExpect(jsonPath("$.discount").value(10.0))
                .andExpect(jsonPath("$.total").value(90.0));

        verify(service).quote(argThat(lines ->
                lines.size() == 1
                && "A".equals(lines.get(0).sku())
                && new BigDecimal("100.00")
                        .compareTo(lines.get(0).unitPrice()) == 0
                && lines.get(0).quantity() == 1));
    }
}
```

**Bước quan trọng:** `verify` ở đây có ý nghĩa vì đang bảo vệ **boundary controller → service** và các trường request. Nếu chỉ viết `verify(service).quote(anyList())` thì một controller truyền danh sách sai vẫn có thể pass. Tuy nhiên không cần verify cách controller tạo local variable, gọi private helper, hay các tương tác không liên quan contract.

Assertion `jsonPath("$.total").value(90.0)` kiểm tra **giá trị JSON dạng số** mà client đọc được, không khóa vào thứ tự key hoặc khoảng trắng của JSON. Nó không khẳng định mọi chi tiết của serialization; các field quan trọng khác đã được kiểm tra riêng.

### 4.5. Integration: assert giá trị thật đi xuyên các tầng

```java
// QuoteIntegrationTest.java
package com.example.quality;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void apiReturnsPriceCalculatedByRealService() throws Exception {
        mockMvc.perform(post("/checkout/quote")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                [{"sku":"A","unitPrice":100.00,"quantity":1}]
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotal").value(100.0))
                .andExpect(jsonPath("$.discount").value(10.0))
                .andExpect(jsonPath("$.total").value(90.0));
    }
}
```

Ở đây không dùng `@MockitoBean`: controller và service thật được Spring wiring cùng nhau. Nếu tính 10% bị lỗi, test sẽ đỏ. `MockMvc` chạy request trong Spring MVC test infrastructure **không mở socket HTTP thật**. Nếu cần kiểm tra network/server, chọn `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client; lựa chọn đó liên quan phạm vi integration, không quyết định assertion mạnh hay yếu.

### 4.6. Chạy

Cần JDK 17+ và Maven khả dụng. Từ thư mục chứa `pom.xml`:

```bash
mvn test
mvn -Dtest=QuoteServiceTest test
mvn -Dtest=QuoteControllerSliceTest test
mvn -Dtest=QuoteIntegrationTest test
```

Ba lớp test chứa **9 test invocations**: parameterized test chạy 3 lần, bốn unit method khác, một MVC slice method và một integration method → tổng **9 test invocations** (3 + 4 + 1 + 1 = 9). Con số sẽ thay đổi khi thêm/sửa test. Maven có thể in `BUILD SUCCESS` khi pass; đừng dựa vào chuỗi log cố định vì môi trường, đường dẫn, thời gian và dependency versions khiến output khác nhau. Các con số nghiệp vụ cố định trong assertion mới là oracle đáng tin.

## 5. Assertion hiệu quả cho từng loại giá trị

### 5.1. Số nguyên, chuỗi và Boolean

Chọn exact equality khi hợp đồng yêu cầu chính xác:

```java
assertEquals(3, actualCount);
assertEquals("PAID", actualStatus);
assertTrue(actualActive);
```

Nhưng `assertTrue(actualActive)` chỉ có ý nghĩa nếu active là hành vi đang kiểm tra và đầu vào khiến kỳ vọng **phải là true**. Nếu không phụ thuộc mã dưới test, Boolean assertion dễ trở thành câu kiểm tra hiển nhiên.

Với chuỗi, xác định đúng hợp đồng: nếu API yêu cầu thông báo chính xác thì `assertEquals("...", actual)`; nếu nội dung có phần động hợp lệ, assert những trường/đặc tính ổn định. Không dùng `contains("OK")` như tiêu chuẩn thành công nếu response lỗi vẫn có chữ `"OK"`.

### 5.2. `BigDecimal` và số thực

`BigDecimal.equals` phân biệt **giá trị và scale**:

```java
assertFalse(new BigDecimal("90.0").equals(new BigDecimal("90.00")));
assertEquals(0,
        new BigDecimal("90.0").compareTo(new BigDecimal("90.00")));
```

Nếu contract yêu cầu lưu/trả đúng **2 chữ số thập phân**, assertion `assertEquals(new BigDecimal("90.00"), actual)` phù hợp khi output có scale 2. Nếu chỉ quan tâm giá trị tiền tệ, có thể dùng:

```java
assertEquals(0, actual.compareTo(new BigDecimal("90.00")));
```

Các đoạn này cần import `BigDecimal` và JUnit assertions; `actual` là biến của test đang xét, không phải mã độc lập. Trong AssertJ có thể dùng `assertThat(actual).isEqualByComparingTo("90.00")` cho so sánh theo giá trị.

Với `double`/`float`, kết quả phép tính nhị phân có thể sai khác nhỏ:

```java
assertEquals(0.3, calculator.calculateRate(), 1e-10);
```

Đây là minh họa khi hợp đồng cho phép sai số `1e-10`, cần xác định tolerance từ yêu cầu trước. **Không dùng delta quá rộng** như `100.0` để biến mọi kết quả thành “gần đúng”, cũng không dùng tolerance khi tiền tệ phải có quy tắc làm tròn xác định. Trong mã giá/tiền, ưu tiên `BigDecimal` theo chính sách làm tròn.

### 5.3. Collection: thứ tự và phần tử trùng

Giả sử API trả tập SKU mà thứ tự không được đảm bảo:

```java
assertThat(actualSkus).containsExactlyInAnyOrder("A", "B", "C");
```

Đây là AssertJ; yêu cầu `import static org.assertj.core.api.Assertions.assertThat;`. Nó so sánh tất cả phần tử, kể cả số lần xuất hiện, **không phụ thuộc thứ tự**. Nếu hợp đồng thật sự yêu cầu xếp theo giá/tên, chọn `containsExactly(...)` để bảo vệ thứ tự. Không dùng `contains("A")` khi yêu cầu là “trả đúng cả ba SKU, không thừa không thiếu”.

Cẩn thận với `Set`: việc đặt dữ liệu thành `Set` có thể loại phần tử trùng trước khi assertion quan sát được lỗi duplication. Nếu duplicate là lỗi cần phát hiện, kiểm tra ngay ở List/response thực tế hoặc kiểm tra số lượng riêng.

### 5.4. Exception: đúng loại, đúng điều kiện

Assertion yếu:

```java
assertThrows(Exception.class, () -> service.quote(List.of()));
```

Nó có thể pass vì một exception không liên quan. Trong ví dụ, hợp đồng rõ ràng là `IllegalArgumentException`:

```java
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> service.quote(List.of()));
assertEquals("Cart must not be empty", error.getMessage());
```

`assertThrows(IllegalArgumentException.class, ...)` cũng đúng nếu cho phép subclass. Chọn `assertThrowsExactly` khi **đúng class** là hợp đồng. Tránh kiểm tra stack trace hoặc câu chữ thông điệp khi có thể thay đổi mà hành vi xử lý lỗi không đổi.

Đặc biệt, đặt **đúng hành động cần kiểm tra** vào lambda:

```java
// Sai mục tiêu: exception ở chỗ tạo test data, service có thể chưa được gọi.
assertThrows(IllegalArgumentException.class, () -> {
    var input = createInvalidDataThatThrows();
    service.quote(input);
});
```

Đoạn minh họa này dùng một helper giả định. Test có thể pass trước khi gọi `service.quote`. Khi nguyên nhân lỗi cần phân biệt, hãy dựng fixture trước và giới hạn lambda vào đúng invocation:

```java
List<CartLine> invalid = List.of(
        new CartLine("A", new BigDecimal("20.00"), 0));
assertThrowsExactly(IllegalArgumentException.class,
        () -> service.quote(invalid));
```

### 5.5. Thời gian, UUID và dữ liệu động

Sai hướng thường gặp:

```java
assertEquals(Instant.now(), actual.createdAt());
```

Hai lần gọi clock ở các thời điểm khác nhau, nên test có thể fail ngẫu nhiên. Khi thời điểm chính xác là contract, **tiêm `Clock`** và đóng băng nó.

Ví dụ Java hoàn chỉnh gồm hai tệp, có thể thêm vào cùng project:

```java
// src/main/java/com/example/quality/ExpiryPolicy.java
package com.example.quality;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant expiry() {
        return Instant.now(clock).plus(Duration.ofHours(24));
    }
}
```

```java
// src/test/java/com/example/quality/ExpiryPolicyTest.java
package com.example.quality;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExpiryPolicyTest {
    @Test
    void expiresExactlyOneDayAfterCreation() {
        Clock fixed = Clock.fixed(
                Instant.parse("2030-01-01T00:00:00Z"), ZoneOffset.UTC);

        assertEquals(
                Instant.parse("2030-01-02T00:00:00Z"),
                new ExpiryPolicy(fixed).expiry());
    }
}
```

Kết quả ở đây **chính xác và không phụ thuộc đồng hồ thật**. Nếu muốn xác minh UUID, đừng assert UUID sinh ra có chuỗi cố định khi hợp đồng chỉ yêu cầu tính hợp lệ/duy nhất. Có thể cung cấp generator giả vào constructor để test đúng output, hoặc kiểm tra định dạng/tính duy nhất theo phạm vi cần thiết.

### 5.6. JSON/HTTP: assert hợp đồng, tránh snapshot giòn

Kiểm tra endpoint nên hỏi:

- Status đúng cụ thể là `200`, `201`, `400` hay `404`?
- Content-Type phù hợp?
- Các trường nghiệp vụ bắt buộc, giá trị và kiểu dữ liệu có đúng?
- Với lỗi, client nhận mã lỗi/định dạng lỗi ổn định theo contract?
- Header `Location`, `ETag` hoặc `Retry-After` chỉ khi có yêu cầu về chúng?

Không nhất thiết assert **toàn bộ JSON như một string có thứ tự key, khoảng trắng và indentation cố định**. Dùng JsonPath, JSON structural comparison hoặc typed DTO assertion. Nhưng cũng tránh chỉ check body không rỗng hoặc status nằm trong khoảng 200–499 vì có thể bỏ lọt lỗi contract.

Ví dụ khi đúng contract yêu cầu tạo tài nguyên `201 Created`, chỉ `status().is2xxSuccessful()` là quá yếu: nó có thể bỏ qua việc endpoint vô tình trả 200. Ngược lại, nếu contract cho phép 200 **hoặc** 204, không ép 200 vì ý thích của test author.

### 5.7. Side effect và interaction với mock

Hợp đồng của một service có thể là **phát hành đúng một sự kiện** chứ không có return value. Khi đó interaction assertion có giá trị:

```java
verify(eventPublisher).publish(argThat(event ->
        "ORDER_PAID".equals(event.type())
        && orderId.equals(event.orderId())));
```

Đoạn này minh họa, giả định `eventPublisher` và `orderId` có trong test class, event type có getter/record accessors `type()` và `orderId()`. Nếu số lần phát hành là yêu cầu, có thể thêm `verify(eventPublisher, times(1))...`; lệnh `verify` không khai báo `times` mặc định xác nhận một lời gọi phù hợp. Không verify mọi method nội bộ chỉ để tăng số assertion: refactor hợp lệ sẽ khiến test dễ gãy.

Cũng cần phân biệt **mocked effect** và **effect thật**. `verify(repository).save(...)` chứng minh lời gọi vào mock, **không chứng minh dữ liệu đã commit vào database**. Muốn kiểm tra persistence thật phải dùng integration test, truy vấn lại repository hoặc kiểm tra DB state ở môi trường phù hợp.

## 6. Những cách khiến test “xanh giả” dù có assertion

### 6.1. Assertion kiểm tra sai đối tượng

```java
Quote quote = service.quote(lines);
assertEquals(expectedTotal, expectedTotal);
```

Service được gọi nhưng kết quả `quote` không hề được kiểm tra. Assertion phải quan sát đầu ra, exception, state change hoặc interaction thực của lời gọi đang kiểm thử.

### 6.2. Test assertion không bao giờ được thực thi

```java
if (Boolean.getBoolean("run.extra.assertions")) {
    assertEquals(expected, actual);
}
```

Nếu property không bật, assertion có thể không chạy. Nếu điều kiện là prerequisite hợp lệ, dùng cơ chế `Assumptions`/`@EnabledIf...` có chủ đích và đo **skipped**; đừng im lặng bỏ assertion rồi coi test pass.

Với callback bất đồng bộ:

```java
CompletableFuture.runAsync(() -> assertEquals(expected, actual));
```

Test có thể kết thúc trước khi future hoàn thành; assertion có thể fail trong luồng khác mà test không chờ và không quan sát lỗi. Cách thông thường:

```java
CompletableFuture<Void> future =
        CompletableFuture.runAsync(
                () -> assertEquals(expected, actual));
future.join(); // Đảm bảo chờ; lỗi trong task được báo lại.
```

Hai đoạn là minh họa trong test class (cần `java.util.concurrent.CompletableFuture` và các biến `expected`, `actual`). Với Reactor, Kafka, HTTP async hoặc listener, sử dụng đúng test utility để **đợi tới trạng thái/hệ quả mong đợi và assert nó**; tránh `Thread.sleep(...)` cố định dẫn đến flaky test.

### 6.3. Assertion sau early return

```java
if (result == null) {
    return;
}
assertEquals(expected, result.value());
```

Khi `result == null`, test hoàn thành mà không fail. Nếu `null` là lỗi, hãy dùng:

```java
assertNotNull(result, "result must exist");
assertEquals(expected, result.value());
```

Trong AssertJ, `assertThat(result).isNotNull()` trước các field assertions cũng có ý nghĩa; nhưng **chỉ `isNotNull()` là quá yếu** nếu cần đúng `value`. Đừng dùng `return` sớm để né assertion thiếu dữ liệu.

### 6.4. Fixture và expected cùng bị tạo bởi logic lỗi

Nếu expected được sinh bằng cùng hàm/mapper/utility đang được kiểm thử, cả actual lẫn expected có thể chia sẻ lỗi và test pass. Hãy chuẩn bị **ví dụ độc lập**, hợp đồng mẫu được review, hoặc oracle khác. Tránh ép “không được reuse helper trong test”: helper để tạo data hợp lệ vẫn tốt, nhưng **helper tính ra expected bằng chính thuật toán cần kiểm chứng** là nguy cơ.

### 6.5. Assertion thất bại nhưng bị catch và nuốt

```java
try {
    assertEquals(expected, actual);
} catch (AssertionError ignored) {
    // Sai: test trở thành xanh mặc dù assertion thất bại.
}
```

Không nuốt `AssertionError`. Nếu thật sự muốn kiểm tra một assertion tự viết có fail không, hãy assert riêng với API phù hợp và làm rõ test đang kiểm tra **framework assertion**, không phải hành vi domain.

## 7. Đúng mức chi tiết: kiểm tra theo hợp đồng

Lấy một thay đổi code: service sử dụng `List` thay vì `Stream`, hoặc thay internal cache nhưng vẫn trả đúng tổng tiền.

| Assertion | Thay đổi trên nên làm fail? | Đánh giá |
| --- | --- | --- |
| `assertEquals(90.00, quote.total())` theo kiểu số tiền phù hợp | Không | Bảo vệ output, không khóa triển khai |
| `verify(helper).sumUsingStream(...)` | Không, nếu helper là nội bộ tùy chọn | Dễ giòn; verify không đúng boundary |
| Assert vị trí thứ 1 của một list không có contract order | Không | Dễ fail sai khi reorder hợp lệ |
| Assert đúng mã lỗi API công khai `INVALID_CART` | Có nếu mã lỗi đổi | Hợp lý nếu mã lỗi là contract |
| Assert chuỗi log chứa tên method private | Thường không | Log này không đại diện hành vi người dùng |
| Assert số email đã gửi = 1 | Có nếu gửi 2 | Hợp lý khi đúng một email là contract |
| Assert ID của đơn hàng do DB sinh = 1 | Thường không | Dữ liệu và sequence có thể khác |
| Assert ID có thể dùng truy xuất lại đúng đơn hàng | Có | Kiểm tra hành vi thực của ID |

Vì thế không có công thức “luôn dùng `assertEquals`”, “không bao giờ verify mock”, hay “tuyệt đối không assert message”. **Câu hỏi quyết định là yêu cầu nào sẽ bị vi phạm nếu assertion fail.**

### 7.1. Tối thiểu nhưng đủ mạnh

Không phải mọi test đều phải assert mọi field. Một test đặt tên `returns404WhenBookMissing` chỉ cần kiểm tra status 404 và error contract có ý nghĩa; nó không cần kiểm tra log/trace/time nội bộ. Nhưng một test đặt tên `calculatesDiscountAtThreshold` mà chỉ assert không ném exception thì chưa đủ.

Cách tối ưu là: **mỗi test mô tả một hành vi cụ thể, assertion chứng minh được hành vi ấy, và các điều kiện khác có liên quan rõ ràng**.

### 7.2. `assertAll` và failure message

JUnit Jupiter hỗ trợ gom nhiều assertion bằng `assertAll`:

```java
assertAll("quote fields",
        () -> assertEquals(new BigDecimal("100.00"), quote.subtotal()),
        () -> assertEquals(new BigDecimal("10.00"), quote.discount()),
        () -> assertEquals(new BigDecimal("90.00"), quote.total()));
```

Khác với ba assert tuần tự (dừng ở assert fail đầu tiên), `assertAll` đánh giá các executable và tổng hợp nhiều lỗi để chẩn đoán thuận tiện. **Nó không tự làm assertion mạnh hơn**: nếu cả ba so sánh actual với chính actual, vẫn là ba tautology. Đặt failure message có ý nghĩa, ví dụ `"discount for exactly 100.00"` thay vì `"test failed"`.

## 8. Kiểm chứng sức mạnh assertion bằng thay đổi sai có kiểm soát

Chọn một thay đổi nhỏ có thể làm hỏng hành vi mà không làm hỏng compile, rồi xem test có bắt không.

Ví dụ thay dòng trong `QuoteService`:

```java
// Đúng:
subtotal.compareTo(THRESHOLD) >= 0

// Sai có chủ đích để kiểm tra test:
subtotal.compareTo(THRESHOLD) > 0
```

Nếu assertion tại ngưỡng 100.00 đủ mạnh, test sẽ fail: expected discount 10.00 nhưng actual discount 0.00, expected total 90.00 nhưng actual total 100.00.

Thử các “mutant” khác trong môi trường local rồi khôi phục code đúng:

| Đột biến giả định | Test phù hợp cần fail |
| --- | --- |
| Chỉ tính dòng đầu tiên | `accountsForAllLinesAndQuantities` |
| Bỏ qua `quantity` | `accountsForAllLinesAndQuantities` |
| Đổi tỷ lệ giảm `0.10` thành `0.05` | Case 100.00, 120.00 |
| Luôn trả discount `0.00` | Case ngưỡng trở lên |
| Bỏ kiểm tra giỏ trống | `rejectsEmptyCartWithRelevantException` |
| Controller bỏ field `discount` trong JSON | MVC slice/integration JSON contract |
| Controller truyền dữ liệu khác vào service | MVC slice `argThat` binding assertion |

Đây là tư duy của **mutation testing**: không chỉ hỏi “code được chạy đến chưa?” mà hỏi “test có ngăn một thay đổi sai không?”. Công cụ như PIT có thể tự tạo một số mutant cho Java, nhưng không có công cụ nào bảo đảm đầy đủ các quy tắc nghiệp vụ. Khi tạo mutant, **không commit thay đổi sai**, dùng nó làm phép thử chất lượng bộ test.

### 8.1. Test đỏ vì refactor hợp lệ cũng cần đánh giá

Nếu đổi tên private helper, thứ tự map fields trong JSON, thời gian compile hay sắp xếp của tập không có contract thứ tự làm nhiều test đỏ, hãy xem lại assertion trước khi ép sửa production. Những failure đó có thể phản ánh test đang khóa vào triển khai.

Ngược lại, nếu đổi output công khai hoặc semantics nghiệp vụ mà test vẫn xanh, bộ test có thể thiếu trường hợp biên hoặc expected không độc lập.

## 9. Chọn assertion theo cấp độ kiểm thử trong Spring Boot

| Cấp độ | Quan sát nên ưu tiên | Assertion hay sai mục tiêu |
| --- | --- | --- |
| **Unit** | Kết quả tính toán, trạng thái, exception, sự kiện gửi ra collaborator | Assert Spring context có bean khi test không tạo context; verify mọi private helper |
| **MVC slice** | URL/status/header, request binding, JSON/validation contract, lời gọi collaborator ở boundary | Khẳng định logic service thật đúng trong khi service đã mock |
| **Repository slice** | Entity mapping, query output, constraint/transaction với DB thử nghiệm đúng loại | Assert `save` trả non-null nhưng chưa kiểm chứng dữ liệu truy xuất |
| **Integration** | Kết quả qua nhiều tầng thật, state thay đổi, transaction và lỗi xử lý | Chỉ kiểm tra Mockito stub thay vì thành phần thật |
| **E2E** | Hành trình từ client ngoài và kết quả quan sát được, lỗi cấu hình/deploy | Assert class nội bộ hoặc dữ liệu cứng dễ đổi của môi trường |

Ví dụ với repository: nếu yêu cầu “lưu một sách và đọc lại theo ID”, assertion meaningful là **truy vấn lại và kiểm tra title/owner phù hợp**; `assertNotNull(repository.save(book))` đơn lẻ có thể pass dù mapping hoặc query đọc lỗi. Với E2E thanh toán: ngoài status thành công, kiểm tra đơn hàng đã chuyển đúng trạng thái và không có giao dịch trùng theo hợp đồng.

**Không dùng hai tầng test để chứng minh cùng một điều bằng cùng một mock.** Tầng khác nhau nên bắt được loại lỗi khác nhau; cùng một giá trị expected có thể lặp giữa unit và integration nhưng đường chạy thực khác nhau.

## 10. Checklist review assertion trước khi merge

Đối với từng test quan trọng, hãy xác minh:

- [ ] Tên test và mô tả yêu cầu thống nhất: “test này bảo vệ điều gì?”.
- [ ] Có invocation thật của phương thức/endpoint/luồng cần kiểm tra.
- [ ] Expected được xác lập độc lập từ quy tắc, ví dụ được review hoặc contract.
- [ ] Không dùng `assertTrue(true)`, `assertEquals(x,x)`, so sánh mock với chính stub, hoặc assertion sau nhánh `return` không an toàn.
- [ ] Không chỉ `assertNotNull`/`is2xxSuccessful`/`doesNotThrow` khi contract còn đòi nội dung/giá trị cụ thể.
- [ ] Có case bình thường, trường hợp biên và case sai đầu vào quan trọng.
- [ ] Exception được xác minh đủ chính xác theo contract; lambda chỉ bao thao tác cần kiểm tra.
- [ ] Nếu test có async/callback, đã đợi và quan sát kết quả/assertion thật.
- [ ] Collection/JSON/thời gian/số thực được so sánh theo semantics: thứ tự khi có yêu cầu, tolerance phù hợp, clock cố định, không khóa ID động.
- [ ] Mockito verify kiểm tra boundary/side effect có ý nghĩa, không cột test vào private implementation.
- [ ] Nếu test đỏ do refactor không thay đổi hành vi, đã xem assertion có giòn không.
- [ ] Có thể chỉ ra một thay đổi sai cụ thể khiến test này phải đỏ.
- [ ] Với Spring Boot, hiểu thành phần nào đang chạy thật và thành phần nào đã mock.

## 11. Bài tập tự đánh giá

**Bài 1.** Test giá tiền dưới đây có vấn đề gì?

```java
Quote quote = service.quote(lines);
assertNotNull(quote);
assertTrue(quote.total().signum() >= 0);
```

**Đáp án:** Không kiểm tra giảm giá/tổng tiền theo hợp đồng; một implementation luôn trả `0.00` có thể pass. Chuyển thành những expected cố định cho subtotal/discount/total và thêm ca ngưỡng.

**Bài 2.** Đã dùng `assertThrows(RuntimeException.class, ...)` để kiểm tra giỏ trống. Rủi ro gì?

**Đáp án:** Một `NullPointerException` hoặc exception không liên quan cũng có thể pass, do nó là subclass của `RuntimeException`. Nếu contract yêu cầu `IllegalArgumentException`, dùng type đó; dùng `assertThrowsExactly` khi class chính xác là điều cần bảo vệ.

**Bài 3.** API trả sản phẩm A, B, C theo thứ tự tùy ý. Dùng `containsExactly("A","B","C")` có hợp lý không?

**Đáp án:** Không nếu order không thuộc contract. Dùng `containsExactlyInAnyOrder` để kiểm tra đủ phần tử mà không ràng buộc thứ tự.

**Bài 4.** Tại sao `assertEquals(Instant.now(), saved.createdAt())` không ổn định?

**Đáp án:** Hai lần gọi đồng hồ khác thời điểm. Tiêm `Clock.fixed` hoặc assert khoảng thời gian hợp lý khi time window mới là hợp đồng.

**Bài 5.** Một MockMvc test stub service trả 90.00 rồi assert JSON total 90.00. Nó chứng minh service đã giảm giá đúng chưa?

**Đáp án:** Chưa. Nó chứng minh controller/serialization của mock response. Cần unit/integration test cho service tính thật.

**Bài 6.** Bạn thay `>=` bằng `>` trong chính sách giảm giá. Test có ca subtotal 120.00 nhưng không có 100.00 vẫn xanh. Thiếu gì?

**Đáp án:** Thiếu assertion **đúng ngưỡng 100.00**. Giá trị biên là dữ liệu đặc biệt quan trọng đối với điều kiện so sánh.

**Bài 7.** Nếu yêu cầu công khai là “mỗi đơn hàng thanh toán phát ra đúng một sự kiện”, verify gọi publisher có bị xem là chi tiết triển khai không?

**Đáp án:** Không khi đó là kết quả có thể quan sát ở boundary event. Nên verify một lần, đúng loại sự kiện/order ID; đừng verify thứ tự của các helper private không nằm trong hợp đồng.

## 12. Tài liệu tham khảo

- [JUnit 5 User Guide – Assertions](https://docs.junit.org/5.13.1/user-guide/index.html): `assertEquals`, `assertAll`, `assertThrows`, `assertThrowsExactly`, `assertDoesNotThrow` và assertion cơ bản.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi `@WebMvcTest`, `@SpringBootTest`, `@AutoConfigureMockMvc` và `@MockitoBean`.
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): test request/response ở Spring MVC không cần HTTP server thật.
- [AssertJ Core Documentation](https://assertj.github.io/doc/): fluent assertion, collection và so sánh theo ngữ nghĩa.
- [PIT Mutation Testing](https://pitest.org/): thử thay đổi code có kiểm soát để đánh giá khả năng test phát hiện lỗi.

**Kết luận học tập:** Assertion tốt là một cam kết có ý nghĩa: nếu hợp đồng nghiệp vụ bị phá vỡ, nó phải fail; nếu chỉ đổi chi tiết triển khai hợp lệ, nó nên tiếp tục pass. Hãy viết **expected độc lập, đủ cụ thể, đúng boundary và ổn định theo contract**.