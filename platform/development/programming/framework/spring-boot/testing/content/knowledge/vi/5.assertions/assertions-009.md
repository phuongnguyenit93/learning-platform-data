# Soft assertions và phạm vi sử dụng có kiểm soát

Khi kiểm thử một đối tượng trả về, một HTTP response hoặc một bản ghi cơ sở dữ liệu, ta thường phải xác nhận **nhiều thuộc tính cùng lúc**. Với assertion thông thường, phép kiểm tra đầu tiên thất bại sẽ ném lỗi và các câu lệnh sau đó không được thực hiện. Nếu chỉ muốn biết *tất cả trường nào của cùng một kết quả đang sai*, việc sửa một lỗi rồi chạy lại để phát hiện lỗi tiếp theo là kém hiệu quả.

**Soft assertions** cho phép thu thập nhiều assertion failure rồi báo cáo chung ở cuối một nhóm. Trong Java/Spring Boot, hai cơ chế phổ biến là **JUnit Jupiter `assertAll`** và **AssertJ `SoftAssertions`/`assertSoftly`**. Cần sử dụng chúng có kiểm soát: chỉ gom các kiểm tra **độc lập, an toàn và có ý nghĩa ngay cả khi một kiểm tra khác sai**. Những điều kiện nền tảng như response bị null, HTTP status sai, JSON không giải mã được hoặc bản ghi không tồn tại vẫn nên được kiểm tra **fail-fast**.

Bài học này giải thích cơ chế, sự khác biệt, cách áp dụng ở unit/Web/integration test, ví dụ Java 17+ có thể chạy, lỗi phổ biến và cách quyết định phạm vi gom assertion.

## 1. Fail-fast và soft assertions: sự khác biệt về luồng chạy

Giả sử một đơn hàng phải có các giá trị:

| Trường | Giá trị mong đợi | Giá trị thực tế trong tình huống lỗi |
|---|---:|---:|
| `subtotalVnd` | 600.000 | 600.000 |
| `shippingVnd` | 0 | 30.000 |
| `payableVnd` | 600.000 | 630.000 |
| `currency` | `VND` | `VND` |

Với các assertion **fail-fast** liên tiếp:

```java
assertEquals(600_000L, quote.subtotalVnd());
assertEquals(0L, quote.shippingVnd());
assertEquals(600_000L, quote.payableVnd());
assertEquals("VND", quote.currency());
```

Khi `shippingVnd` thực tế bằng 30.000, dòng thứ hai ném lỗi; hai assertion phía sau không chạy. Báo cáo chưa thể hiện ngay lỗi `payableVnd`, dù nó có thể xuất phát từ cùng một nguyên nhân tính phí sai.

Với JUnit Jupiter **`assertAll`**:

```java
assertAll("Order quote",
        () -> assertEquals(600_000L, quote.subtotalVnd()),
        () -> assertEquals(0L, quote.shippingVnd()),
        () -> assertEquals(600_000L, quote.payableVnd()),
        () -> assertEquals("VND", quote.currency()));
```

JUnit chạy từng `Executable` được cung cấp, thu thập các failure và báo cáo chung; với dữ liệu ví dụ, ta có thể thấy cả `shippingVnd` và `payableVnd` không khớp. **Một test vẫn là FAIL** nếu có ít nhất một assertion sai. Soft assertions không biến kết quả thành “pass một phần” và không sửa hoặc bỏ qua lỗi nghiệp vụ.

Cả hai đoạn trên là **snippet bên trong một phương thức test có biến `quote`**. Bản hoàn chỉnh có đầy đủ import, package, class và dữ liệu ở phần ví dụ thực hành.

### Khác biệt về trách nhiệm

- **Assertion** mô tả một điều phải đúng, ví dụ “payable bằng 600.000”.
- **Fail-fast** dừng tại vị trí assertion ném lỗi, hữu ích khi kết quả còn lại sẽ vô nghĩa nếu điều kiện trước sai.
- **Soft/grouped assertion** cố gắng kiểm các điều kiện độc lập rồi tổng hợp failure, hữu ích để phát hiện nhiều sai khác của cùng một snapshot kết quả.
- **Test case** là tình huống có setup, hành động, expected behavior. Nhiều tình huống độc lập vẫn nên là các test case riêng dù mỗi test có thể dùng soft assertions.

Không đánh đồng “gom lỗi” với “tiếp tục bất kể điều gì xảy ra”: lỗi trong setup, exception khi gọi dependency, `NullPointerException` do truy cập trường chưa tồn tại hoặc một thao tác có side effect không được soft assertions tự động xử lý an toàn.

## 2. JUnit Jupiter: `Assertions.assertAll`

JUnit Jupiter cung cấp `assertAll` nhận một nhóm `Executable` (thường là lambda). Mỗi `Executable` được thực thi để JUnit thu thập lỗi và thông báo, thường dưới dạng `MultipleFailuresError` của OpenTest4J khi có nhiều failure. Cách hiển thị chi tiết tùy phiên bản JUnit, plugin build và IDE.

Đoạn minh họa:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertAll("Quote fields",
        () -> assertEquals(600_000L,
                quote.subtotalVnd(), "subtotalVnd"),
        () -> assertEquals(0L,
                quote.shippingVnd(), "shippingVnd"),
        () -> assertEquals(600_000L,
                quote.payableVnd(), "payableVnd"),
        () -> assertEquals("VND",
                quote.currency(), "currency"));
```

Hai dòng `import` chỉ minh họa các import cần có trong file, phần `assertAll` đặt trong test method.

### Tại sao mỗi điều kiện cần một lambda?

Sai lầm phổ biến:

```java
assertAll("Quote",
        () -> {
            assertEquals(0L, quote.shippingVnd());
            assertEquals(600_000L, quote.payableVnd());
        });
```

Nếu assertion đầu tiên sai, **lambda này** bị kết thúc trước khi chạy assertion thứ hai. `assertAll` có thể tiếp tục các lambda khác, nhưng không cứu được những câu lệnh sau failure trong cùng một lambda. Hãy dùng:

```java
assertAll("Quote",
        () -> assertEquals(0L, quote.shippingVnd()),
        () -> assertEquals(600_000L, quote.payableVnd()));
```

Như vậy hai điều kiện có cơ hội được kiểm độc lập. JUnit còn cho phép lồng nhóm nhỏ `assertAll("Amounts", ...)` và `assertAll("Metadata", ...)` nếu test có nhiều trường và việc phân nhóm giúp đọc báo cáo. Tránh tạo quá nhiều cấp heading cho một test ngắn.

**Ưu điểm:** dùng trực tiếp Assertions của JUnit, phù hợp với nhóm nhỏ cố định. **Giới hạn:** người viết phải đóng gói các assertion vào lambda riêng để gom đúng; một lỗi xảy ra khi tạo input trước `assertAll` vẫn làm test dừng ngay.

## 3. AssertJ: `SoftAssertions` và `assertSoftly`

AssertJ có API fluent cho nhiều kiểu giá trị, collection và object. Trong các dự án Spring Boot thông thường, `spring-boot-starter-test` cung cấp AssertJ trên test classpath. Hai cách sử dụng quan trọng:

### Cách thủ công: nhớ gọi `assertAll()`

```java
SoftAssertions softly = new SoftAssertions();

softly.assertThat(quote.subtotalVnd())
        .as("subtotalVnd").isEqualTo(600_000L);
softly.assertThat(quote.shippingVnd())
        .as("shippingVnd").isZero();
softly.assertThat(quote.payableVnd())
        .as("payableVnd").isEqualTo(600_000L);
softly.assertThat(quote.currency())
        .as("currency").isEqualTo("VND");

softly.assertAll();
```

Cần `import org.assertj.core.api.SoftAssertions;`. Mỗi lời gọi qua `softly.assertThat` ghi nhận failure của chính đối tượng `softly`. **`softly.assertAll()` ở cuối là bắt buộc** để phát ra failure đã tích lũy. Quên dòng này có thể khiến test xanh dù một số assertion đã sai.

### Cách khuyến nghị: `assertSoftly` tự tổng hợp

```java
assertSoftly(softly -> {
    softly.assertThat(quote.subtotalVnd())
            .as("subtotalVnd").isEqualTo(600_000L);
    softly.assertThat(quote.shippingVnd())
            .as("shippingVnd").isZero();
    softly.assertThat(quote.payableVnd())
            .as("payableVnd").isEqualTo(600_000L);
    softly.assertThat(quote.currency())
            .as("currency").isEqualTo("VND");
});
```

Cần `import static org.assertj.core.api.SoftAssertions.assertSoftly;`. Trong luồng hoàn thành bình thường của callback, `assertSoftly` tổng hợp lỗi ở cuối khối, giảm rủi ro quên `assertAll`.

**Lưu ý:** chỉ các assertion gọi qua **`softly.assertThat(...)`** được gom vào nhóm này. Viết `assertThat(...)` thông thường từ AssertJ hoặc `assertEquals(...)` của JUnit ở giữa callback vẫn áp dụng cơ chế fail-fast của riêng chúng. Nếu một câu lệnh ném exception vì dữ liệu không tồn tại, soft assertions không bảo đảm được việc đánh giá tất cả trường khác. Không đặt `SoftAssertions` vào static field dùng chung giữa nhiều test hoặc nhiều thread.

## 4. Ví dụ chạy được: báo giá đơn hàng trong Java 17+

Để phân biệt cơ chế, dùng cùng một lớp production cho hai test với kết quả hợp lệ, và một test riêng xác nhận đầu vào sai.

**Quy tắc nghiệp vụ:** với số lượng lớn hơn 0 và đơn giá không âm, subtotal bằng số lượng nhân đơn giá; từ 500.000 VND trở lên miễn vận chuyển, dưới ngưỡng trả 30.000 VND; payable bằng subtotal cộng shipping, currency luôn là `VND`. Số lượng không hợp lệ phải bị từ chối.

### 4.1. File production

Tạo **`src/main/java/com/example/shop/pricing/OrderPricing.java`**:

```java
package com.example.shop.pricing;

public final class OrderPricing {

    public record Quote(long subtotalVnd,
                        long shippingVnd,
                        long payableVnd,
                        String currency) {
    }

    public Quote quote(int quantity, long unitPriceVnd) {
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid quantity or price");
        }

        long subtotal = Math.multiplyExact((long) quantity, unitPriceVnd);
        long shipping = subtotal >= 500_000L ? 0L : 30_000L;
        long payable = Math.addExact(subtotal, shipping);

        return new Quote(subtotal, shipping, payable, "VND");
    }
}
```

`record` là tính năng Java 17. `Math.multiplyExact` và `Math.addExact` ném `ArithmeticException` khi phép tính tràn `long`; ví dụ tránh việc số tiền tràn âm thầm.

### 4.2. File kiểm thử hoàn chỉnh

Tạo **`src/test/java/com/example/shop/pricing/OrderPricingTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.SoftAssertions.assertSoftly;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderPricingTest {
    private final OrderPricing pricing = new OrderPricing();

    @Test
    void softAssertionsCheckAllFieldsOfFreeShippingQuote() {
        OrderPricing.Quote quote = pricing.quote(2, 300_000L);

        assertSoftly(softly -> {
            softly.assertThat(quote.subtotalVnd())
                    .as("subtotalVnd").isEqualTo(600_000L);
            softly.assertThat(quote.shippingVnd())
                    .as("shippingVnd").isZero();
            softly.assertThat(quote.payableVnd())
                    .as("payableVnd").isEqualTo(600_000L);
            softly.assertThat(quote.currency())
                    .as("currency").isEqualTo("VND");
        });
    }

    @Test
    void junitAssertAllChecksAllFieldsOfPaidShippingQuote() {
        OrderPricing.Quote quote = pricing.quote(2, 200_000L);

        assertAll("Quote below free-shipping threshold",
                () -> assertEquals(400_000L,
                        quote.subtotalVnd(), "subtotalVnd"),
                () -> assertEquals(30_000L,
                        quote.shippingVnd(), "shippingVnd"),
                () -> assertEquals(430_000L,
                        quote.payableVnd(), "payableVnd"),
                () -> assertEquals("VND",
                        quote.currency(), "currency"));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> pricing.quote(0, 300_000L));
    }
}
```

Các file có đầy đủ `package`, `class` và import; tương thích Java 17+ khi dự án có JUnit Jupiter/AssertJ, chẳng hạn `spring-boot-starter-test`. Đây là **unit test thuần Java**, không cần `@SpringBootTest`, application context hay database.

Có thể chạy với Maven Wrapper tại thư mục module:

```bash
./mvnw -Dtest=OrderPricingTest test
```

Hoặc Gradle Wrapper khi task `test` đã cấu hình JUnit Platform:

```bash
./gradlew test --tests "com.example.shop.pricing.OrderPricingTest"
```

Trên Windows sử dụng `mvnw.cmd` hoặc `gradlew.bat`. Hai lệnh là hai phương án tùy build tool, không cần chạy cả hai. Kết quả mong đợi: **3 test pass, 0 test fail**; output text chính xác của build tool phụ thuộc cấu hình và phiên bản plugin, không có stdout nghiệp vụ cố định.

Hai test báo giá kiểm tra **bốn thuộc tính của một kết quả được tạo bằng một lệnh gọi**; test số lượng bằng 0 là một kịch bản độc lập, nên viết thành method riêng. Cách này giúp thất bại được định vị theo hành vi, đồng thời vẫn gom được nhiều mismatch của cùng một quote.

## 5. Thấy rõ lợi ích bằng hai mismatch cố ý

Giả sử `quote = pricing.quote(2, 300_000L)` trả `shippingVnd = 0` và `payableVnd = 600_000`. Nếu trong một test tạm thời viết sai kỳ vọng:

```java
assertSoftly(softly -> {
    softly.assertThat(quote.shippingVnd())
            .as("shippingVnd").isEqualTo(30_000L);
    softly.assertThat(quote.payableVnd())
            .as("payableVnd").isEqualTo(630_000L);
});
```

Đoạn trên **cố tình làm test FAIL**, dùng biến `quote` đã tạo ở nơi khác; **không giữ nó trong suite chính thức**. Kết quả có ý nghĩa là **một test thất bại với hai mismatch**: phí thực tế 0 so với kỳ vọng 30.000 và tổng thực tế 600.000 so với kỳ vọng 630.000. Cách format exception và stack trace khác nhau tùy AssertJ/IDE/runner.

Bài tập kiểm chứng cơ chế: trước hết thấy đúng **hai sai khác**; sửa expected về 0 và 600.000 thì test phải pass. Nếu dùng `new SoftAssertions()` thủ công, hãy thử bỏ `softly.assertAll()` trong bài tập cục bộ để hiểu vì sao việc thiếu nó gây **false positive**; sau đó khôi phục ngay cơ chế tổng hợp trước khi commit.

## 6. Chọn phạm vi sử dụng trong Spring Boot

### 6.1. Web/MVC: kiểm tra một HTTP response

Với `@WebMvcTest` hoặc `@SpringBootTest` dùng `MockMvc`, chiến lược an toàn là:

1. Thực hiện request **một lần**.
2. Kiểm tra **fail-fast** status phù hợp (ví dụ HTTP 200), body tồn tại, nội dung giải mã JSON được, schema tối thiểu đúng.
3. Dùng **soft assertions** để so sánh các field nghiệp vụ của **response đã hợp lệ**.
4. Khi test fail, phân biệt lỗi nền tảng với lỗi giá trị trường.

Ví dụ **minh họa bên trong test đã khai báo và cấu hình `MockMvc mockMvc`, `ObjectMapper objectMapper`, endpoint `GET /api/quotes` và import phù hợp**:

```java
MvcResult result = mockMvc.perform(
        get("/api/quotes")
                .param("quantity", "2")
                .param("unitPriceVnd", "300000"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode json = objectMapper.readTree(
        result.getResponse().getContentAsString());
assertTrue(json.isObject(), "Body must be a JSON object");

assertSoftly(softly -> {
    softly.assertThat(json.has("subtotalVnd"))
            .as("subtotalVnd exists").isTrue();
    softly.assertThat(json.path("subtotalVnd").asLong())
            .as("subtotalVnd").isEqualTo(600_000L);
    softly.assertThat(json.path("shippingVnd").asLong())
            .as("shippingVnd").isZero();
    softly.assertThat(json.path("payableVnd").asLong())
            .as("payableVnd").isEqualTo(600_000L);
    softly.assertThat(json.path("currency").asText())
            .as("currency").isEqualTo("VND");
});
```

Đoạn này **không phải file chạy độc lập**: endpoint, kiểu JSON, injection, `MvcResult`, `JsonNode` và các import phụ thuộc phiên bản/framework của ứng dụng. Trong thực tế, hãy kiểm tra cả **sự tồn tại và kiểu dữ liệu** của từng trường trước khi chuyển đổi; `asLong()`/`asText()` của JSON tree có thể tạo giá trị mặc định với node không tồn tại hoặc không đúng kiểu, khiến thông báo khó hiểu. Điều kiện schema hoặc kiểu dữ liệu mang tính gác cổng nên được kiểm tra fail-fast trước khi so các giá trị.

Nếu HTTP status là 401/403/500, test nên dừng và báo lỗi status; không có ý nghĩa khi tiếp tục so `payableVnd` trên response lỗi. Đối với kiểm thử quyền truy cập hoặc rò rỉ dữ liệu, cần các test riêng thể hiện rõ tác động bảo mật, thay vì dựa vào một nhóm soft assertion khổng lồ.

### 6.2. Repository/integration: một bản ghi được truy xuất

Giả sử repository đã lưu đơn hàng và cần đọc lại để xác nhận các trường `status`, `currency`, `total`. Hãy xác minh **bản ghi tồn tại** trước:

```java
OrderEntity stored = repository.findById(orderId)
        .orElseThrow(() -> new AssertionError("Order was not persisted"));

assertSoftly(softly -> {
    softly.assertThat(stored.getStatus())
            .as("status").isEqualTo(OrderStatus.PENDING);
    softly.assertThat(stored.getCurrency())
            .as("currency").isEqualTo("VND");
    softly.assertThat(stored.getTotalVnd())
            .as("totalVnd").isEqualTo(600_000L);
});
```

Đây chỉ là **mẫu triển khai trong integration test của ứng dụng có các kiểu `OrderEntity`, `OrderStatus` và biến `repository`, `orderId`**; nó không tự biên dịch độc lập. Nếu bản ghi không tồn tại, exception “Order was not persisted” diễn đạt **nguyên nhân gốc** tốt hơn một danh sách `NullPointerException` từ các getter. Soft assertions không thay thế việc kiểm tra transaction, migration, locking hay constraint bằng database phù hợp.

### 6.3. Service/DTO: snapshot sau một hành động

Một service trả về DTO có thể được so đồng thời các trường như `id`, `status`, `total`, `currency`, nếu tất cả đều xuất phát từ một lần gọi service và không cần side effect mới. Đây là trường hợp áp dụng đẹp: **một hành động, một snapshot, nhiều thuộc tính độc lập**.

Không nên thiết kế một test vừa tạo đơn, vừa thanh toán, vừa hủy đơn, vừa hoàn tiền rồi gom toàn bộ assertion vào một khối soft. Những giai đoạn có điều kiện phụ thuộc và side effect khác nhau phải có các điểm xác nhận fail-fast hoặc tách thành nhiều test theo rủi ro.

## 7. Khi nào nên dùng soft, khi nào cần fail-fast?

| Tình huống | Lựa chọn | Vì sao |
|---|---|---|
| Nhiều trường của cùng JSON/DTO đã parse thành công | Soft/grouped | Thu thập toàn bộ khác biệt độc lập |
| Tổng tiền, phí, mã tiền tệ trong một kết quả báo giá | Soft/grouped | Thấy nhiều biểu hiện của một lỗi tính toán |
| HTTP status sai, body không đọc được | Fail-fast | Phần tiếp theo không có nền tảng đáng tin |
| Đối tượng null, record không tồn tại | Fail-fast | Tránh dereference null và lỗi dây chuyền |
| Authorization, side effect quan trọng, transaction | Test riêng và fail-fast tại ranh giới | Lỗi nghiêm trọng cần tín hiệu chính xác |
| Nhiều scenario khác nhau: hợp lệ, lỗi, timeout, retry | Tách thành test method | Mỗi scenario có setup và expected behavior riêng |
| Nhiều tập input cùng một rule | `@ParameterizedTest` | Tên và dữ liệu từng invocation rõ hơn một test khổng lồ |
| Một object phức tạp cần đối chiếu toàn bộ | Cân nhắc so sánh object/recursive comparison | Có thể rõ hơn hàng chục assertion lặp |
| Kiểm tra thứ tự các bước workflow | Fail-fast theo bước | Bước sau có thể vô nghĩa nếu bước trước thất bại |

**Câu hỏi ra quyết định:** “Nếu assertion A sai, assertion B có vẫn đo được một sự thật có ý nghĩa và an toàn hay không?” Nếu **có**, nhóm soft có giá trị. Nếu **không**, kiểm tra A trước rồi mới vào nhóm hoặc chia test.

### Ví dụ không nên làm

```java
assertSoftly(softly -> {
    softly.assertThat(response).isNotNull();
    softly.assertThat(response.getCustomer().getName())
            .isEqualTo("Lan");
});
```

Nếu `response` hoặc `getCustomer()` là null, câu lệnh thứ hai gây `NullPointerException`. Assertion mềm ở dòng trên **không bảo vệ** getter sau. Cách phù hợp hơn:

```java
assertNotNull(response, "response must exist");
assertNotNull(response.getCustomer(), "customer must exist");

assertSoftly(softly -> {
    softly.assertThat(response.getCustomer().getName())
            .as("customer.name").isEqualTo("Lan");
    softly.assertThat(response.getCustomer().isActive())
            .as("customer.active").isTrue();
});
```

Hai đoạn chỉ mô tả tư duy trong test của ứng dụng giả định có `response`; cần import `assertNotNull` từ JUnit và `assertSoftly` từ AssertJ. Điều kiện nền tảng được xác minh fail-fast, sau đó các field có thể đánh giá độc lập mới được gom.

## 8. Giới hạn kỹ thuật và anti-pattern cần tránh

1. **Quên `softly.assertAll()`** khi dùng `new SoftAssertions()`. Các failure tích lũy có thể không làm test fail. Ưu tiên `assertSoftly` hoặc bảo đảm điểm kết thúc được gọi đúng.
2. **Trộn assertion thường vào khối soft** rồi tưởng mọi lỗi đều được gom. `assertEquals` JUnit và `assertThat` AssertJ thông thường vẫn ném lỗi ngay.
3. **Đặt nhiều assertion trong một `Executable` của `assertAll`**. Assertion đầu tiên sai khiến các dòng tiếp trong lambda không chạy; chia thành các lambda độc lập.
4. **Gom giá trị phụ thuộc nhau mà thiếu precondition**: trước khi kiểm `customer.name`, phải xác minh `customer` có tồn tại. Tránh nhiều exception nhiễu.
5. **Chia sẻ một `SoftAssertions` instance giữa test hoặc thread**. Failure bị tích lũy xuyên ngữ cảnh và kết quả có thể không xác định. Tạo mới trong từng test/khối.
6. **Gom các trường không thuộc hợp đồng** như timestamp ngẫu nhiên hay ID phát sinh không cần thiết. Các assertion đó khiến suite khó bảo trì, không chứng minh yêu cầu quan trọng.
7. **Nhồi quá nhiều hành vi vào một test**. Một report có 30 mismatch không thay thế được các test có tên, fixture và ranh giới riêng. Chia scenario trước khi tăng số assertion.
8. **Cho rằng soft assertions giúp bao phủ tốt hơn**. Chúng tăng khả năng *quan sát nhiều mismatch trong một lượt*, không tự tăng phạm vi dữ liệu, đường đi hay dependency thật. Unit test có repository mock vẫn không chứng minh SQL/transaction.
9. **Dùng gom lỗi để lờ side effect nguy hiểm**. Khi thanh toán hoặc phân quyền sai, test cần dừng/khẳng định ở ranh giới nghiêm trọng; đừng tiếp tục gây thêm các thao tác thay đổi trạng thái chỉ để có thêm failure.
10. **Thiếu nhãn và thông điệp**. Dùng `assertAll("Quote fields", ...)`, `"payableVnd"` hoặc `as("payableVnd")` để một người khác đọc log biết ngay trường bị ảnh hưởng.

## 9. Cách kiểm tra soft assertion đã được dùng đúng

Thực hiện theo quy trình ngắn:

1. Viết một scenario có tên rõ và một hành động tạo kết quả cụ thể.
2. Đặt gác cổng fail-fast cho status, việc parse, object tồn tại và các điều kiện cần thiết.
3. Liệt kê các thuộc tính **độc lập** cần đối chiếu trên một snapshot.
4. Chọn `assertAll` nếu cần một nhóm JUnit nhỏ, chọn `assertSoftly` nếu cần AssertJ fluent và nhãn `as(...)`.
5. Kiểm tra từng điều kiện thật sự được nhóm, không có assertion fail-fast bất ngờ ở giữa.
6. Thử gây hai mismatch có chủ đích trong test cục bộ: phải xuất hiện hai sai khác và test phải FAIL; sửa lại expected để test PASS.
7. Chạy riêng test và chạy chung suite, xác nhận không phụ thuộc thứ tự hay trạng thái chia sẻ.
8. Giữ số lượng assertion có chủ đích; test với scope quá rộng nên tách theo hành vi hoặc dùng parameterized test.

## 10. Checklist trước khi commit

- [ ] Test xác nhận nhiều thuộc tính của **một kết quả**, thay vì nhiều workflow không liên quan.
- [ ] HTTP/parse/null/record tồn tại đã được kiểm tra fail-fast khi chúng là điều kiện cần.
- [ ] Mỗi điều kiện mềm vẫn có nghĩa khi điều kiện mềm khác sai.
- [ ] Với JUnit `assertAll`, các kiểm tra độc lập ở những lambda riêng.
- [ ] Với AssertJ, các assertion cần gom đều dùng `softly.assertThat`.
- [ ] Đã gọi `SoftAssertions.assertAll()` nếu dùng thủ công hoặc chọn `assertSoftly`.
- [ ] Không chia sẻ `SoftAssertions` instance qua các test/thread.
- [ ] Những lỗi liên quan đến quyền, giao dịch, side effect có test và ranh giới rõ.
- [ ] Tên assertion và message giúp xác định trường/kịch bản gây lỗi.
- [ ] Bộ test **đỏ khi expected cố tình sai**, **xanh khi code và expected đúng**.

**Ghi nhớ:** soft assertions phù hợp với **nhiều quan sát độc lập trên một snapshot đã hợp lệ**; fail-fast phù hợp với **điều kiện nền tảng, rủi ro lớn và bước có phụ thuộc**. `assertAll` của JUnit Jupiter và `assertSoftly` của AssertJ đều hữu ích nếu được đặt trong phạm vi test rõ ràng và không che giấu lỗi gốc.
