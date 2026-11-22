# Kiểm thử validator, mapper và phép biến đổi dữ liệu

## 1. Tại sao ba nhóm kiểm thử này quan trọng?

Trong ứng dụng Spring Boot, nhiều lỗi nghiệp vụ không nằm ở controller hay câu lệnh database mà xuất hiện khi **kiểm tra đầu vào**, **chuyển đổi DTO thành mô hình khác** hoặc **chuẩn hóa dữ liệu**. Ví dụ: một SKU chứa khoảng trắng bị lưu sai định dạng, giá tiền bị làm tròn sai, một trường bị bỏ quên khi ánh xạ, hoặc số lượng âm vượt qua validator.

Ba nhóm trách nhiệm có thể tách ra để kiểm thử độc lập:

1. **Validator** nhận dữ liệu và xác định dữ liệu có đáp ứng ràng buộc hay không. Kết quả có thể là danh sách lỗi, kết quả hợp lệ/không hợp lệ hoặc exception được thiết kế trước.
2. **Mapper** biến đối tượng nguồn thành đối tượng đích, bảo đảm các trường được lấy đúng, kiểu dữ liệu và giá trị mặc định đúng hợp đồng.
3. **Phép biến đổi dữ liệu (transformation)** chuẩn hóa hoặc tính toán từ giá trị đầu vào, chẳng hạn `trim`, chuẩn hóa SKU, đổi định dạng tiền, làm tròn hoặc tính thành tiền.

Tách các trách nhiệm cho phép mỗi unit test trả lời một câu hỏi rõ ràng. **Validator** không nên vô tình sửa dữ liệu; **mapper** không nên làm mất trường; **transformation** không nên cho kết quả phụ thuộc ngầm vào locale, timezone hoặc lần chạy trước.

Đây là bài về **unit test nghiệp vụ**: kiểm tra trực tiếp phương thức Java và assertion JUnit Jupiter. Nếu không cần Spring ApplicationContext để thực hiện logic, không phải thêm `@SpringBootTest`. Các cơ chế validation tự động tại HTTP boundary và mapper sinh mã có thể được kiểm thử ở mức tích hợp riêng khi mục tiêu yêu cầu.

## 2. Xác định hợp đồng trước khi viết assertion

Một test tốt phải dựa vào quy tắc được xác định trước, không đoán kết quả sau khi chạy. Xét đầu vào đặt hàng:

| Trường | Dữ liệu thô | Quy tắc |
| --- | --- | --- |
| `sku` | `" ab-7 "` | Bắt buộc có ký tự không trắng; khi mapping thì bỏ khoảng trắng hai đầu và chuyển thành chữ hoa theo `Locale.ROOT` |
| `quantity` | `3` | Phải lớn hơn 0 |
| `unitPriceText` | `"12.345"` | Bắt buộc là số thập phân hợp lệ và lớn hơn 0; khi chuyển thành đơn giá tiền thì làm tròn đến 2 chữ số thập phân bằng `HALF_UP` |

Trong **ví dụ học tập này**, quy tắc thành tiền là:

~~~text
đơn giá làm tròn trước: 12.345 -> 12.35
thành tiền = 12.35 × 3 = 37.05
~~~

Làm tròn đơn giá **trước khi nhân** là một lựa chọn nghiệp vụ có chủ đích cho ví dụ. Một hệ thống khác có thể nhân trước rồi làm tròn tổng; không được thay quy tắc mà không đổi cả đặc tả và test.

Để đo lường đúng, viết tình huống dưới dạng Given/When/Then:

- **Given:** request có SKU `" ab-7 "`, số lượng `3`, giá `"12.345"`.
- **When:** validator kiểm tra, sau đó mapper chuyển request hợp lệ thành dòng đặt hàng.
- **Then:** validator không báo lỗi; kết quả có SKU `"AB-7"`, số lượng `3`, đơn giá `12.35`, thành tiền `37.05`.

Cần thêm các ca **âm/biên**: request null, SKU trống, số lượng bằng 0 hoặc âm, giá không phải số, giá bằng 0, giá âm, chữ hoa/thường, số chữ số thập phân và các giá trị sát ngưỡng làm tròn.

## 3. Test validator: xác nhận chấp nhận và từ chối đúng tình huống

Validator có thể trả về danh sách mã lỗi để test dễ nhận diện quy tắc bị vi phạm. Hợp đồng ví dụ:

| Điều kiện đầu vào | Kết quả validator |
| --- | --- |
| Request null | `["request.required"]` |
| SKU null, rỗng hoặc toàn khoảng trắng | Có `"sku.required"` |
| Số lượng ≤ 0 | Có `"quantity.positive"` |
| Giá null hoặc trống | Có `"price.required"` |
| Giá không phân tích được thành `BigDecimal` | Có `"price.invalid"` |
| Giá ≤ 0 | Có `"price.positive"` |
| Mọi điều kiện hợp lệ | Danh sách lỗi rỗng |

Khi có nhiều điều kiện sai cùng lúc, bài test nên xác nhận **đủ các lỗi cần thiết**. Nếu thứ tự lỗi là một phần hợp đồng của API, có thể assert theo thứ tự. Nếu thứ tự không phải hợp đồng, dùng một tập hợp hoặc `containsExactlyInAnyOrder` của thư viện assertion phù hợp thay vì buộc thứ tự không cần thiết.

**Hai nguyên tắc:**

- Đừng chỉ assert `errors.isEmpty() == false` cho dữ liệu sai: điều đó không chứng minh đúng **loại lỗi** được phát hiện.
- Đừng gắn test với chuỗi thông điệp dịch cho người dùng nếu code lỗi ổn định mới là hợp đồng; thông điệp hiển thị có thể đổi ngôn ngữ hoặc wording.

Một validator thuần Java có thể được test bằng `new OrderValidator()`. Không cần mock các lớp Java thuần hay khởi động web server. Với validation bằng annotation Jakarta Bean Validation, cần gọi **validation engine** hoặc đi qua integration boundary; phần 9 phân biệt rõ.

## 4. Test mapper: kiểm tra đầy đủ kết quả và dữ liệu không bị đánh mất

Mapper chuyển một kiểu dữ liệu sang kiểu khác, chẳng hạn request DTO → domain model, entity → response DTO hoặc CSV row → import model.

Các lỗi phổ biến:

- Gán nhầm `quantity` sang trường khác, quên map `sku` hoặc map giá sai.
- Biến `null` thành chuỗi `"null"` hoặc tự đặt giá trị mặc định sai.
- Dùng một kiểu/scale tiền khác đặc tả.
- Làm thay đổi đối tượng đầu vào ngoài ý muốn.
- Tự giả định mapper đã làm validation mà thực ra không có.

Đối với ví dụ này, **validator chịu trách nhiệm phát hiện dữ liệu sai trước khi mapper được gọi**. Mapper được phép giả định request đã được xác nhận hợp lệ; đây là precondition có tài liệu. Vì vậy test mapper tập trung vào **đối tượng kết quả cụ thể**, không lặp lại mọi trường hợp không hợp lệ của validator.

Một ca mapper đạt khi kiểm tra đủ các trường thiết yếu:

~~~text
OrderRequest(" ab-7 ", 3, "12.345")
  -> OrderLine(
       sku = "AB-7",
       quantity = 3,
       unitPrice = 12.35,
       lineTotal = 37.05
     )
~~~

Nếu chỉ assert đối tượng đích khác `null`, test vẫn xanh khi mapper bỏ sót trường. Hãy so sánh **giá trị đích**, dùng `assertAll` cho nhiều trường liên quan. Với Java record, so sánh trực tiếp cả record cũng hữu ích nếu mọi thành phần có `equals` phù hợp, nhưng assertion từng field giúp định vị lỗi nhanh hơn.

**Không nên mock chính mapper khi đang kiểm tra mapping.** Với MapStruct hoặc mapper viết tay, dùng triển khai mapper thật. Nếu mục tiêu là một service phụ thuộc mapper, khi đó có thể mock mapper để cô lập logic service; đấy là một test khác.

## 5. Test phép biến đổi: làm tròn, chuẩn hóa và hàm thuần

Phép biến đổi nên có input/output xác định. Ví dụ:

- `normalizeSku(" ab-7 ")` trả `"AB-7"`.
- `money("1.004")` trả `1.00`.
- `money("1.005")` trả `1.01` với `RoundingMode.HALF_UP`.
- `money("1.006")` trả `1.01`.
- `money("12.345")` trả `12.35`.

Test cả giá trị **ngay dưới**, **đúng tại** và **ngay trên** ranh giới làm tròn. Một happy path đơn lẻ không thể bảo vệ quy tắc làm tròn.

Với tiền, dùng `new BigDecimal(String)` thay vì `new BigDecimal(double)` khi chuyển từ văn bản thập phân. Floating point nhị phân không biểu diễn chính xác nhiều số thập phân; đưa một giá trị `double` vào `BigDecimal` có thể giữ lại sai số không mong muốn. Cũng phải quyết định **scale** và **rounding mode** bằng hợp đồng, không dựa vào hành vi mặc định ngầm.

Khi chuẩn hóa mã định danh hoặc từ khóa để tìm kiếm, truyền `Locale.ROOT` cho `toUpperCase`/`toLowerCase` nếu yêu cầu là quy tắc mã máy độc lập locale. `String.strip()` xử lý ký tự khoảng trắng theo Java, còn `trim()` có tập ký tự được xử lý khác; test nên theo đúng loại dữ liệu hệ thống hỗ trợ.

Một hàm thuần (pure function) không phụ thuộc database/mạng/thời gian và không sửa dữ liệu bên ngoài, thường là nơi lý tưởng cho **parameterized test**. Cũng có thể kiểm tra tính lặp lại, ví dụ chuẩn hóa SKU hai lần cho cùng kết quả: `normalizeSku(normalizeSku(x)) == normalizeSku(x)`. **Không mặc định mọi phép biến đổi đều idempotent**; phép cộng phí hoặc đổi tiền có thể không thỏa tính chất đó.

## 6. Ví dụ Java 17 đầy đủ: request, validator, mapper và transformation

Các tệp dưới đây cùng thuộc package `com.example.testing`, có thể dùng trong dự án Spring Boot 3.x/Java 17+ với JUnit Jupiter. Mã chính là Java thuần nên không yêu cầu Spring context.

### 6.1. DTO đầu vào và mô hình kết quả

**Tệp `src/main/java/com/example/testing/OrderRequest.java`:**

~~~java
package com.example.testing;

public record OrderRequest(
        String sku,
        int quantity,
        String unitPriceText
) {
}
~~~

**Tệp `src/main/java/com/example/testing/OrderLine.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal lineTotal
) {
}
~~~

`record` tạo constructor, accessor (ví dụ `sku()`) và `equals` theo các thành phần. Record phù hợp cho mô hình dữ liệu trong ví dụ, nhưng không tự kiểm tra ràng buộc; `new OrderRequest(null, 0, null)` vẫn tạo được record trừ khi tự viết kiểm tra trong constructor.

### 6.2. Validator thuần Java

**Tệp `src/main/java/com/example/testing/OrderValidator.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public final class OrderValidator {
    public List<String> validate(OrderRequest request) {
        if (request == null) {
            return List.of("request.required");
        }

        List<String> errors = new ArrayList<>();

        if (request.sku() == null || request.sku().isBlank()) {
            errors.add("sku.required");
        }

        if (request.quantity() <= 0) {
            errors.add("quantity.positive");
        }

        String priceText = request.unitPriceText();

        if (priceText == null || priceText.isBlank()) {
            errors.add("price.required");
        } else {
            try {
                BigDecimal price = new BigDecimal(priceText.strip());
                if (price.signum() <= 0) {
                    errors.add("price.positive");
                }
            } catch (NumberFormatException ex) {
                errors.add("price.invalid");
            }
        }

        return List.copyOf(errors);
    }
}
~~~

Các mã lỗi xuất hiện theo thứ tự `sku`, `quantity`, `price` khi nhiều trường cùng sai. Test có thể khẳng định thứ tự này vì đó là hành vi cụ thể của ví dụ. Validator không sửa request và không tự tạo `OrderLine`.

Với một hệ thống thật, có thể bổ sung ràng buộc về số lượng tối đa, độ dài SKU, số chữ số thập phân, giá trần hoặc currency. Chỉ đưa ràng buộc vào test khi chúng thực sự nằm trong yêu cầu nghiệp vụ.

### 6.3. Transformation tách thành hàm nhỏ

**Tệp `src/main/java/com/example/testing/OrderTransforms.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public final class OrderTransforms {
    private OrderTransforms() {
    }

    public static String normalizeSku(String sku) {
        return sku.strip().toUpperCase(Locale.ROOT);
    }

    public static BigDecimal money(String rawPrice) {
        return new BigDecimal(rawPrice.strip())
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Hai method này có precondition: tham số phải khác `null`; với `money`, chuỗi phải là số hợp lệ. Bước validation kiểm tra điều đó trước khi mapping. Chúng không đọc cấu hình Spring và không sửa state chia sẻ, nên rất dễ test riêng.

### 6.4. Mapper thực thi hợp đồng ánh xạ

**Tệp `src/main/java/com/example/testing/OrderMapper.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class OrderMapper {
    public OrderLine toLine(OrderRequest request) {
        Objects.requireNonNull(request, "request");

        String sku = OrderTransforms.normalizeSku(request.sku());
        BigDecimal unitPrice = OrderTransforms.money(
                request.unitPriceText()
        );
        BigDecimal lineTotal = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
        );

        return new OrderLine(
                sku,
                request.quantity(),
                unitPrice,
                lineTotal
        );
    }
}
~~~

Theo hợp đồng ví dụ, validator phải được gọi và trả danh sách rỗng **trước khi** `toLine` được dùng trong luồng nghiệp vụ. Mapper không thay thế validation và không kiểm tra lại toàn bộ điều kiện. `BigDecimal.multiply` giữ scale kết quả phù hợp với hai số trong ví dụ: `12.35 × 3 = 37.05`.

### 6.5. Cách phối hợp hai trách nhiệm

Đoạn sau minh họa điểm nối của luồng nghiệp vụ, **không phải một tệp Java độc lập**:

~~~java
OrderRequest request = new OrderRequest(" ab-7 ", 3, "12.345");
OrderValidator validator = new OrderValidator();

List<String> errors = validator.validate(request);
if (!errors.isEmpty()) {
    throw new IllegalArgumentException(String.join(", ", errors));
}

OrderLine line = new OrderMapper().toLine(request);
~~~

Nếu đưa đoạn này vào class Java, cần import `java.util.List` và các class cùng package. Quy tắc ở đây là: **reject trước, map sau**, tránh mapper phải xử lý giá trị sai không thuộc phạm vi của nó.

## 7. JUnit Jupiter: test validator qua ca hợp lệ, không hợp lệ và biên

**Tệp `src/test/java/com/example/testing/OrderValidatorTest.java`:**

~~~java
package com.example.testing;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderValidatorTest {
    private final OrderValidator validator = new OrderValidator();

    @Test
    void validate_whenRequestIsValid_returnsNoErrors() {
        OrderRequest request = new OrderRequest(
                " ab-7 ", 3, "12.345"
        );

        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void validate_whenRequestIsNull_returnsRequiredError() {
        assertEquals(
                List.of("request.required"),
                validator.validate(null)
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = { "  " })
    void validate_whenSkuIsBlank_returnsSkuRequired(String sku) {
        OrderRequest request = new OrderRequest(sku, 1, "2.50");

        assertEquals(
                List.of("sku.required"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(ints = { 0, -1 })
    void validate_whenQuantityIsNotPositive_returnsQuantityError(
            int quantity
    ) {
        OrderRequest request = new OrderRequest(
                "SKU-1", quantity, "2.50"
        );

        assertEquals(
                List.of("quantity.positive"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = { "abc", "12,50" })
    void validate_whenPriceCannotBeParsed_returnsInvalidPrice(
            String rawPrice
    ) {
        OrderRequest request = new OrderRequest("SKU-1", 1, rawPrice);

        assertEquals(
                List.of("price.invalid"),
                validator.validate(request)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = { "0", "-0.01" })
    void validate_whenPriceIsNotPositive_returnsPositivePriceError(
            String rawPrice
    ) {
        OrderRequest request = new OrderRequest("SKU-1", 1, rawPrice);

        assertEquals(
                List.of("price.positive"),
                validator.validate(request)
        );
    }

    @Test
    void validate_whenSeveralFieldsAreInvalid_returnsAllErrors() {
        OrderRequest request = new OrderRequest(" ", 0, null);

        assertEquals(
                List.of(
                        "sku.required",
                        "quantity.positive",
                        "price.required"
                ),
                validator.validate(request)
        );
    }
}
~~~

### Vì sao những assertion này có ý nghĩa?

- Ca **hợp lệ** chứng minh validator không từ chối dữ liệu tốt, tránh lỗi “cái gì cũng invalid”.
- Ca **null request** chứng minh logic không ném `NullPointerException` ngoài ý muốn.
- `@NullAndEmptySource` và `@ValueSource` bao phủ giá trị null, chuỗi rỗng và khoảng trắng.
- Giá `"12,50"` bị từ chối vì `BigDecimal(String)` trong hợp đồng đang nhận biểu diễn dùng dấu chấm, không tự suy luận locale.
- Ca nhiều lỗi bảo đảm validator không dừng quá sớm rồi bỏ sót các trường sai còn lại.

`@ParameterizedTest` thực thi một lượt cho mỗi giá trị, vì vậy tên test cần mô tả **quy tắc chung**. Không phải tạo một method riêng cho từng giá trị tương tự nếu một parameterized test diễn đạt rõ hơn.

## 8. JUnit Jupiter: test mapper và phép biến đổi

**Tệp `src/test/java/com/example/testing/OrderMapperTest.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderMapperTest {
    private final OrderMapper mapper = new OrderMapper();

    @Test
    void toLine_whenRequestIsValid_mapsAllFields() {
        OrderRequest request = new OrderRequest(
                " ab-7 ", 3, "12.345"
        );

        OrderLine result = mapper.toLine(request);

        assertAll(
                () -> assertEquals("AB-7", result.sku()),
                () -> assertEquals(3, result.quantity()),
                () -> assertEquals(
                        new BigDecimal("12.35"),
                        result.unitPrice()
                ),
                () -> assertEquals(
                        new BigDecimal("37.05"),
                        result.lineTotal()
                )
        );

        // Mapper không thay đổi giá trị record nguồn.
        assertEquals(" ab-7 ", request.sku());
        assertEquals("12.345", request.unitPriceText());
    }

    @Test
    void toLine_whenInputIsNull_throwsNullPointerException() {
        assertThrows(
                NullPointerException.class,
                () -> mapper.toLine(null)
        );
    }
}
~~~

Test này kiểm tra **mọi trường kết quả quan trọng** và khẳng định dữ liệu đầu vào không bị thay đổi. `assertAll` giúp thực hiện các assertion trong cùng một nhóm, nhưng vẫn giữ một mục tiêu: kiểm tra hợp đồng mapping của một request.

Đối tượng `OrderLine` được tạo mới nên không cần mock một repository hay Spring bean để kiểm tra ánh xạ. Nếu mapper có logic phức tạp, có thể tạo nhiều ca để bảo đảm không bỏ sót trường, giữ nguyên `null` theo quy tắc được duyệt hoặc ánh xạ danh sách đúng thứ tự.

**Tệp `src/test/java/com/example/testing/OrderTransformsTest.java`:**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTransformsTest {

    @Test
    void normalizeSku_whenLowercaseAndPadded_returnsCanonicalSku() {
        assertEquals(
                "AB-7",
                OrderTransforms.normalizeSku(" ab-7 ")
        );
    }

    @Test
    void normalizeSku_whenAlreadyCanonical_remainsUnchanged() {
        assertEquals(
                "AB-7",
                OrderTransforms.normalizeSku("AB-7")
        );
    }

    @ParameterizedTest
    @CsvSource({
            "1.004, 1.00",
            "1.005, 1.01",
            "1.006, 1.01",
            "12.345, 12.35",
            "2, 2.00"
    })
    void money_whenGivenDecimal_roundsHalfUpToTwoPlaces(
            String input,
            String expected
    ) {
        assertEquals(
                new BigDecimal(expected),
                OrderTransforms.money(input)
        );
    }

    @Test
    void money_whenInputIsPadded_acceptsWhitespace() {
        assertEquals(
                new BigDecimal("1.20"),
                OrderTransforms.money(" 1.2 ")
        );
    }
}
~~~

`@CsvSource` cấp các giá trị dạng chuỗi, tránh chuyển qua `double` trước khi đưa vào `BigDecimal`. `assertEquals(new BigDecimal("2.00"), ...)` còn xác minh **scale 2**, vì `BigDecimal.equals` xét cả giá trị lẫn scale (`2.0` và `2.00` không bằng nhau theo `equals`). Đây là lựa chọn phù hợp khi scale của đơn giá là một phần hợp đồng.

Nếu chỉ quan tâm giá trị số mà không quan tâm scale, có thể so sánh bằng `compareTo(...) == 0`. Không thay đổi kiểu so sánh mà không hiểu yêu cầu đầu ra.

## 9. Khi dùng Jakarta Bean Validation trong Spring Boot

Đối với ứng dụng Spring Boot 3.x, các annotation Jakarta Bean Validation như `@NotBlank`, `@Positive` và `@Valid` thuộc package **`jakarta.validation`** (khác các tên `javax.validation` trong nhiều dự án Spring Boot 2.x cũ).

Ví dụ DTO:

~~~java
package com.example.testing;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateOrderDto(
        @NotBlank String sku,
        @Positive int quantity
) {
}
~~~

Đây là **một tệp riêng `CreateOrderDto.java`**. Annotation là **metadata về ràng buộc**; việc gọi `new CreateOrderDto(" ", 0)` tự nó **không chạy Bean Validation**. Để kiểm thử rule, cần dùng `jakarta.validation.Validator` với provider tương ứng (thường Hibernate Validator trong cấu hình starter validation).

Ví dụ test Bean Validation trực tiếp:

~~~java
package com.example.testing;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CreateOrderDtoValidationTest {

    @Test
    void validate_whenSkuBlankAndQuantityZero_reportsBothFields() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<String> invalidFields = validator
                    .validate(new CreateOrderDto(" ", 0))
                    .stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of("sku", "quantity"), invalidFields);
        }
    }
}
~~~

Test dùng **set tên trường** vì trình tự các `ConstraintViolation` không phải thứ tự nghiệp vụ nên không nên assert theo vị trí. Các annotation/provider phải có trên classpath test; chỉ thêm annotation trong mã mà không có implementation thì chưa đủ để thực thi validation.

Trong `build.gradle` (Gradle Groovy DSL) của dự án Spring Boot 3.x, các dependency liên quan thường là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây chỉ là phần **liên quan đến validation/test**, giả định dự án đã có Spring Boot plugin, dependency management/repositories và Java toolchain phù hợp. `spring-boot-starter-validation` cung cấp API và implementation validation cần thiết; `spring-boot-starter-test` cung cấp JUnit Jupiter cùng các tiện ích test.

Nếu cần kiểm tra **request HTTP** có được validate tự động và trả HTTP 400 theo cấu hình ứng dụng hay không, đó là test tầng web với `@WebMvcTest`/`MockMvc` hoặc test tích hợp phù hợp. Khi đó assertion phải kiểm tra status, response body và hợp đồng error handler; một unit test gọi `Validator` trực tiếp **không chứng minh** controller đã cấu hình `@Valid` đúng.

## 10. Mapper sinh mã (MapStruct) và mapper viết tay: kiểm thử thế nào?

Với mapper viết tay như `OrderMapper` ở trên, tạo instance bằng `new OrderMapper()`. Với **MapStruct**, annotation processor tạo class triển khai khi build; nếu muốn kiểm tra mapping, phải dùng **implementation được sinh thật** thay vì mock interface mapper.

Những trường hợp nên bao phủ:

| Tình huống | Assertion gợi ý |
| --- | --- |
| Đối tượng nguồn hợp lệ | Mọi field quan trọng trong target đúng |
| Nguồn có `null` | Kết quả/null/default tuân theo `nullValueMappingStrategy` hoặc cấu hình mapping thực tế |
| Đổi tên trường nguồn/đích | Đích vẫn nhận đúng giá trị từ field được chỉ định |
| Mapping danh sách | Số lượng, thứ tự và từng item đúng hợp đồng |
| Mapping kiểu số/ngày | Precision, scale, timezone/format đúng |
| Mapping enum | Mọi giá trị được hỗ trợ ánh xạ đúng; nhánh không hỗ trợ có hành vi rõ ràng |
| Mapping vào object có sẵn | Các field không thuộc phạm vi update được giữ hay thay đúng đặc tả |

Không cần viết test riêng cho mọi setter 1:1 không có rủi ro; hãy tập trung vào **quy tắc mapping quan trọng, ranh giới dữ liệu và những field dễ bỏ sót**. Với mapper generated, lỗi cấu hình có thể lộ ở bước compile. Unit test vẫn có giá trị để chứng minh **kết quả runtime** đúng.

Cần phân biệt **test mapping** với **test service sử dụng mapper**: trong test mapping thì dùng mapper thật; trong test service khác, có thể mock mapper để cô lập service. Nếu mapper do Spring quản lý bằng `componentModel = "spring"`, chỉ khởi động Spring context khi mục tiêu là kiểm tra wiring hoặc behavior phụ thuộc bean; logic mapper đơn giản thường có thể test trực tiếp với implementation được sinh và dependency phù hợp.

## 11. Thiết kế thêm test biến đổi dữ liệu theo ranh giới thật

Các phép biến đổi thường có nhiều ranh giới ngoài ví dụ SKU/tiền:

| Loại biến đổi | Ca nên thử | Sai lầm thường gặp |
| --- | --- | --- |
| Chuỗi | null, rỗng, blank, Unicode, khoảng trắng, hoa/thường | Dùng locale máy chạy nên casing khác giữa môi trường |
| Tiền | 0, âm, số rất nhỏ/lớn, 1.004/1.005, scale | Dùng `double` rồi làm tròn không đúng |
| Ngày/giờ | Gần nửa đêm, đổi ngày, DST, timezone | Dùng `ZoneId.systemDefault()` khi yêu cầu timezone cố định |
| Danh sách | Rỗng, một phần tử, trùng lặp, thứ tự | Vô ý drop hoặc reorder phần tử |
| Trạng thái/enum | Mọi giá trị hợp lệ và giá trị không hỗ trợ | Âm thầm map unknown sang default sai |
| Dữ liệu có `null` | Null object, null field, thiếu trường | NPE hoặc tạo kết quả sai thay vì chính sách null đã thống nhất |
| Dữ liệu cấu trúc | Nested object, ID, trường tùy chọn | Bỏ sót nested field hoặc tạo đối tượng chia sẻ mutable |

Với timezone, **ấn định rõ `ZoneId` hoặc `Clock`** và dùng ngày giờ cố định trong test. Không lấy `LocalDateTime.now()` rồi assert một chuỗi được hard-code, vì test có thể fail vào ranh giới giây/ngày.

Với dữ liệu đã chuẩn hóa, chọn thêm một số tính chất hữu ích nếu đúng hợp đồng:

- **Deterministic:** cùng input và cùng cấu hình cho cùng output.
- **Idempotent:** chuẩn hóa lần hai không làm thay đổi kết quả lần đầu (khi quy tắc có tính chất này).
- **Non-mutating:** không sửa nguồn nếu mapper/transform được thiết kế là pure.
- **Total vs partial:** xác định rõ input nào được chấp nhận và input nào gây lỗi. Hàm chỉ được định nghĩa cho input hợp lệ thì test exception theo hợp đồng, không gượng ép hỗ trợ mọi input.

Các tính chất là tiêu chí thiết kế test, không phải lý do để bỏ test ví dụ cụ thể/edge cases.

## 12. Lỗi phổ biến khi test validator, mapper và transformation

1. **Chỉ test happy path.** Với validator, điều này dễ bỏ qua null, blank, số âm và giá sai định dạng. **Sửa:** lập bảng phân vùng hợp lệ/không hợp lệ và giá trị biên.
2. **Không kiểm tra mã lỗi chính xác.** Chỉ assert danh sách lỗi không rỗng làm test xanh khi validator trả sai rule. **Sửa:** assert error code hoặc field path đúng hợp đồng.
3. **Mock validator/mapper trong chính unit test của nó.** Khi đó chỉ kiểm tra kết quả do mock trả lại. **Sửa:** dùng implementation thật cho đối tượng đang kiểm thử.
4. **Gộp validator và mapper vào một test duy nhất.** Khi test fail khó xác định lỗi thuộc kiểm tra đầu vào hay ánh xạ. **Sửa:** unit test từng phần; thêm một vài test tích hợp luồng phối hợp nếu có yêu cầu.
5. **Quên ràng buộc scale và mode của tiền.** Dùng `assertEquals(12.35, someDouble)` dễ gặp sai số và không nói rõ rounding mode. **Sửa:** `BigDecimal(String)`, `setScale` và assertion đúng scale.
6. **Phụ thuộc locale/timezone máy chạy.** Test pass ở máy dev nhưng fail CI. **Sửa:** truyền `Locale`, `ZoneId` hoặc `Clock` theo hợp đồng.
7. **Cho rằng Jakarta annotation tự chạy khi tạo DTO.** `new` không kích hoạt Bean Validation. **Sửa:** gọi `Validator.validate` hoặc kiểm thử đúng Spring validation boundary.
8. **Assert thứ tự violation khi không có hợp đồng thứ tự.** Kết quả có thể đổi giữa implementation/version. **Sửa:** so sánh set hoặc nội dung không phụ thuộc thứ tự.
9. **Test mapping chỉ assert result khác null.** Mapper làm rơi field vẫn pass. **Sửa:** assert toàn bộ trường nghiệp vụ thiết yếu.
10. **Đưa I/O thật vào unit test của phép biến đổi thuần.** Test chậm và phụ thuộc môi trường. **Sửa:** tách dữ liệu thành hàm thuần; test database/HTTP/file riêng nếu cần chứng minh tích hợp.
11. **Sửa assertion để khớp output hiện tại khi thấy test đỏ.** Điều này có thể hợp thức hóa bug. **Sửa:** đối chiếu với rule đã được duyệt, xác định code hay test sai rồi mới sửa.
12. **Dữ liệu test không nêu chính sách đầu vào.** Một test đòi mapper tự validate, test khác giả định đã validate. **Sửa:** ghi rõ precondition và biên trách nhiệm của mỗi lớp.

## 13. Cách chạy test và tự kiểm phạm vi

Các tệp ở phần 6–8 cùng package `com.example.testing`, đặt trong source set `main`/`test` tương ứng. `CreateOrderDto.java` và bài test Jakarta ở phần 9 chỉ yêu cầu khi đã thêm starter validation.

Chạy riêng từng lớp từ thư mục có Gradle Wrapper trên macOS/Linux:

~~~bash
./gradlew test --tests "com.example.testing.OrderValidatorTest"
./gradlew test --tests "com.example.testing.OrderMapperTest"
./gradlew test --tests "com.example.testing.OrderTransformsTest"
./gradlew test --tests "com.example.testing.CreateOrderDtoValidationTest"
~~~

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Lớp cuối cần dependency `spring-boot-starter-validation` và provider Jakarta. Các test này không in `System.out.println`, nên không có một chuỗi stdout cố định của mã ứng dụng. Test runner thông báo PASS/FAIL và kết quả chi tiết tùy Gradle/JUnit/IDE.

Trước khi chốt mỗi bộ test, đối chiếu:

- [ ] Hợp đồng của validator, mapper và transformation được nêu riêng, rõ ràng.
- [ ] Có ca hợp lệ, trường hợp lỗi và ranh giới thực tế của từng quy tắc.
- [ ] Validator trả đúng lỗi, kể cả khi có nhiều trường cùng sai.
- [ ] Mapper trả đúng **mọi field quan trọng**; không âm thầm mất dữ liệu.
- [ ] Precision, scale, rounding mode, locale, timezone được xác định và có assertion khi liên quan.
- [ ] Test không mock chính hàm/lớp đang cần chứng minh.
- [ ] Test chạy độc lập, dữ liệu không phụ thuộc state cũ hoặc môi trường CI.
- [ ] Unit test không tự nhận đã chứng minh HTTP validation hay wiring Spring nếu chưa chạy tầng đó.

**Ghi nhớ:** validator bảo vệ **điều kiện hợp lệ**; mapper bảo vệ **tính đúng và đầy đủ của ánh xạ**; transformation bảo vệ **quy tắc chuẩn hóa/tính toán**. Kiểm thử từng trách nhiệm bằng input có chủ đích, assertion cụ thể và các giá trị biên, rồi chỉ thêm kiểm thử phối hợp ở nơi cần chứng minh luồng nghiệp vụ hoàn chỉnh.