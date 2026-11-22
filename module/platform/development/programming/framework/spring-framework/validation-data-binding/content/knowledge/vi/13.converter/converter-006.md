# Chuyển đổi String sang Enum và quy tắc phân biệt chữ hoa, chữ thường trong Spring

## 1. Bài toán và kết quả cần hiểu

Trong Java, `enum` biểu diễn một tập hằng số hữu hạn, có kiểu rõ ràng. Khi nhận tham số HTTP, dữ liệu biểu mẫu hoặc chuỗi cấu hình, Spring thường nhận giá trị ban đầu dưới dạng `String` rồi cần chuyển về kiểu `enum` để gán cho tham số/phần tử đối tượng.

Ví dụ:

```java
public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    DONE
}
```

Đối với tên hằng `DONE`, hai chuỗi `"DONE"` và `"done"` **không giống nhau**. Quy tắc phân biệt chữ hoa, chữ thường là một phần của chính sách chuyển đổi. Spring Framework mặc định sử dụng tên hằng enum theo cách **phân biệt hoa/thường**; muốn chấp nhận `done`, `Done` và `DONE` như nhau thì cần chọn hoặc cấu hình một cơ chế chuyển đổi phù hợp.

Sau bài này, cần phân biệt được: hành vi của Java `Enum.valueOf`; cách `ConversionService` của Spring chuyển `String` thành enum; vai trò của `Converter` tùy chỉnh; cách lỗi đi vào data binding; và ranh giới giữa query/path/form với JSON body.

## 2. Nền tảng Java: tên hằng enum là giá trị chính xác

`Enum.valueOf(OrderStatus.class, text)` tìm hằng số có **tên trùng chính xác** với `text`. Phương thức này không tự `trim()`, không tự chuyển chữ hoa/chữ thường và không tìm theo nhãn hiển thị hay mã nghiệp vụ.

- `Enum.valueOf(OrderStatus.class, "DONE")` → `OrderStatus.DONE`.
- `Enum.valueOf(OrderStatus.class, "done")` → ném `IllegalArgumentException`.
- `Enum.valueOf(OrderStatus.class, " DONE ")` → ném `IllegalArgumentException` nếu truyền trực tiếp, vì có khoảng trắng.
- `Enum.valueOf(OrderStatus.class, "IN_PROGRESS")` → `OrderStatus.IN_PROGRESS`.
- `Enum.valueOf(OrderStatus.class, "IN-PROGRESS")` → lỗi: dấu gạch nối không phải dấu gạch dưới.
- `Enum.valueOf(..., null)` → ném `NullPointerException`; đây là quy tắc của API Java, cần phân biệt với xử lý đầu vào null của Spring.

`name()` trả tên khai báo, ví dụ `DONE`. `toString()` có thể được override để hiện nhãn khác, nhưng **không làm `Enum.valueOf` đổi cách tìm**. Không nên dựa vào nhãn thân thiện với người dùng để suy ra tên hằng Java.

## 3. Spring chuyển String sang Enum như thế nào?

### 3.1. ConversionService và ConverterFactory mặc định

`ConversionService` là hợp đồng chuyển đổi kiểu của Spring. Các dịch vụ mặc định như `DefaultConversionService` đăng ký bộ chuyển đổi `String` → `Enum` thông qua `StringToEnumConverterFactory`. Về bản chất, nhánh chuyển đổi enum kiểm tra chuỗi rỗng, sau đó tra tên hằng bằng `Enum.valueOf(targetEnumType, source.trim())`.

Luồng khái niệm:

```text
Nguồn chuỗi (query / path / form)
          |
          v
Spring ConversionService / WebDataBinder
          |
          v
StringToEnumConverterFactory (mặc định)
          |
          +-- source == "" ---------> null
          |
          +-- source.trim()
                    |
                    v
          Enum.valueOf(enumType, text)
                    |
             tên trùng chính xác?
                /          \
              có           không
              |              |
            Enum        lỗi chuyển đổi
```

Vì có `trim()` ở bước Spring mặc định, `" DONE "` có thể trở thành `DONE` và thành công, mặc dù truyền nguyên chuỗi đó cho `Enum.valueOf` trực tiếp sẽ lỗi. Tuy nhiên `trim()` **không** biến `"done"` thành `"DONE"`.

### 3.2. Bảng hành vi mặc định

Giả sử kiểu đích là `OrderStatus { NEW, IN_PROGRESS, DONE }` và dịch vụ sử dụng `StringToEnumConverterFactory` của Spring Framework:

| Chuỗi đầu vào | Kết quả | Giải thích |
| --- | --- | --- |
| `"NEW"` | `NEW` | Tên trùng chính xác |
| `"new"` hoặc `"New"` | Lỗi chuyển đổi | Khác hoa/thường |
| `" DONE "` | `DONE` | Spring loại khoảng trắng đầu/cuối |
| `"IN_PROGRESS"` | `IN_PROGRESS` | Trùng tên hằng |
| `"in_progress"` | Lỗi chuyển đổi | Khác hoa/thường |
| `"IN-PROGRESS"` | Lỗi chuyển đổi | Dấu `-` không phải `_` |
| `""` | `null` | Chuỗi rỗng đúng nghĩa được bộ chuyển đổi mặc định xử lý riêng |
| `"   "` | Lỗi chuyển đổi | Chuỗi ban đầu không rỗng; sau `trim()` tên thành `""`, không khớp hằng nào |
| `"UNKNOWN"` | Lỗi chuyển đổi | Enum không có hằng tương ứng |

Với `ConversionService.convert(null, OrderStatus.class)`, dịch vụ thường trả `null` mà không gọi `Converter.convert` cho đầu vào null. Phải phân biệt `null`, chuỗi rỗng `""` và chuỗi toàn khoảng trắng `"   "`; không giả định ba trường hợp đều giống nhau.

Khi không tìm thấy enum, `Enum.valueOf` ném `IllegalArgumentException`; khi đi qua `ConversionService`, lỗi thường được bọc thành `ConversionFailedException`. Cách framework chuyển lỗi đó thành phản hồi HTTP hoặc `BindingResult` còn phụ thuộc vị trí dữ liệu được bind.

## 4. Ví dụ Java 17+ độc lập để kiểm chứng quy tắc

Tạo file `EnumCaseDemo.java`:

```java
import java.util.Locale;

public class EnumCaseDemo {
    enum OrderStatus {
        NEW, IN_PROGRESS, DONE
    }

    public static void main(String[] args) {
        System.out.println(Enum.valueOf(OrderStatus.class, "DONE"));

        try {
            Enum.valueOf(OrderStatus.class, "done");
        } catch (IllegalArgumentException ex) {
            System.out.println("done -> INVALID");
        }

        String normalized = " in_progress "
                .trim()
                .toUpperCase(Locale.ROOT);

        System.out.println(Enum.valueOf(OrderStatus.class, normalized));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac EnumCaseDemo.java
java EnumCaseDemo
```

Stdout chính xác:

```text
DONE
done -> INVALID
IN_PROGRESS
```

Ví dụ này dùng **Java thuần** để cho thấy phép chuẩn hóa trước `Enum.valueOf`. Nó chưa sử dụng Spring, nên không tự chứng minh cấu hình cụ thể của một ứng dụng Spring MVC hay Spring Boot.

## 5. Enum được bind ở đâu trong Spring MVC?

Với tham số URI, query hoặc biểu mẫu, Spring MVC dùng cơ chế type conversion của `WebDataBinder`/`FormattingConversionService` được cấu hình cho ứng dụng. Một ví dụ fragment controller (đặt trong ứng dụng đã có Spring Web MVC):

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders")
    public String list(@RequestParam OrderStatus status) {
        return "status=" + status.name();
    }
}
```

Nếu MVC đang dùng quy tắc enum mặc định của Spring Framework:

- `GET /orders?status=DONE` → bind được `OrderStatus.DONE`; ví dụ controller trả `status=DONE`.
- `GET /orders?status=done` → lỗi chuyển kiểu; trong MVC thông thường dẫn tới HTTP 400, controller không được gọi.
- `GET /orders?status=%20DONE%20` → khoảng trắng được loại trước khi đối chiếu tên.
- `GET /orders?status=UNKNOWN` → lỗi chuyển kiểu; không phải một giá trị enum hợp lệ.

Cơ chế tương tự áp dụng cho `@PathVariable`, `@RequestHeader` và thuộc tính enum trong `@ModelAttribute`, tùy `ConversionService` thực tế. Với `@ModelAttribute`, lỗi có thể được ghi thành `typeMismatch` trong `BindingResult`; với tham số phương thức không bind được, Spring MVC có thể ném ngoại lệ như `MethodArgumentTypeMismatchException`. Cần kiểm tra đường xử lý cụ thể thay vì khẳng định mọi lỗi conversion đều đi qua Bean Validation.

Nếu đầu vào rỗng chuyển thành `null`, một tham số `@RequestParam` bắt buộc vẫn có thể bị xem là thiếu và dẫn tới lỗi HTTP 400. Tham số tùy chọn cần được thiết kế rõ ràng, ví dụ `required = false` hoặc `Optional<OrderStatus>`, đồng thời phải định nghĩa hành vi khi không có giá trị.

## 6. Khi cần không phân biệt hoa/thường: tạo Converter rõ ràng

Nếu hợp đồng API muốn chấp nhận `done`, `Done` và `DONE`, có thể viết một `Converter<String, OrderStatus>`. Ví dụ dưới đây áp dụng riêng cho `OrderStatus`, tránh vô tình thay chính sách của tất cả enum trong hệ thống.

**File `src/main/java/com/example/demo/OrderStatus.java`:**

```java
package com.example.demo;

public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    DONE
}
```

**File `src/main/java/com/example/demo/OrderStatusConverter.java`:**

```java
package com.example.demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class OrderStatusConverter implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        String normalized = source.trim();

        // Chính sách tự chọn: chuỗi trắng được xem là không có giá trị.
        if (normalized.isEmpty()) {
            return null;
        }

        try {
            return OrderStatus.valueOf(normalized.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Unknown OrderStatus: '" + source + "'", ex);
        }
    }
}
```

**File `src/main/java/com/example/demo/WebConversionConfig.java`:**

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new OrderStatusConverter());
    }
}
```

**File `src/main/java/com/example/demo/OrderController.java`:**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders")
    public String list(@RequestParam OrderStatus status) {
        return "status=" + status.name();
    }
}
```

Các file này là những thành phần của **dự án Spring MVC/Spring Boot có sẵn dependency Web**, không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`. Khi `WebConversionConfig` được component scan, registry MVC có converter vừa đăng ký. Gọi `GET /orders?status=done` hoặc `GET /orders?status=%20DoNe%20` sẽ bind thành `DONE` và controller trên trả `status=DONE`.

Giải thích các quyết định trong converter:

1. `trim()` loại khoảng trắng đầu/cuối, nhưng không chuẩn hóa dấu `-`, `_` hoặc khoảng trắng bên trong.
2. `toUpperCase(Locale.ROOT)` giúp so khớp enum viết chữ in hoa theo một locale ổn định; không sử dụng locale của máy chủ hoặc người dùng để điều khiển định danh enum.
3. `valueOf` xác nhận giá trị sau chuẩn hóa vẫn phải là hằng enum có thật. `"finished"` không thể tự biến thành `DONE`.
4. `normalized.isEmpty()` trả `null` theo **chính sách của ví dụ**. Điểm này khác mặc định Spring ở trường hợp `"   "`; nếu hợp đồng API muốn từ chối mọi giá trị rỗng/trắng thì thay nhánh này bằng ngoại lệ.
5. Ném ngoại lệ với giá trị không hợp lệ để Spring báo lỗi bind rõ ràng. Không nên tự động dùng `DONE`, phần tử đầu tiên hoặc `null` cho chuỗi không nhận diện được, vì che khuất lỗi của client.

Không phải lúc nào cũng cần chuyển tất cả enum sang chữ hoa: nếu tên hằng có quy ước khác, hoặc API chấp nhận alias, mã miền `"in-progress"`, mã số hay nhãn tiếng Việt, hãy lập bảng ánh xạ tường minh. `equalsIgnoreCase` có thể được dùng khi duyệt các hằng, nhưng vẫn phải xử lý trường hợp không có hằng nào khớp.

## 7. Kiểm thử ConversionService trước khi dùng qua HTTP

Để tách quy tắc conversion khỏi controller, kiểm thử trực tiếp `DefaultConversionService`. Ví dụ JUnit 5 dưới đây giả định các file `OrderStatus` và `OrderStatusConverter` ở mục 6 đã có trên classpath, cùng dependency `spring-core` và JUnit Jupiter:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.*;

class OrderStatusConversionTest {
    @Test
    void defaultConversionIsCaseSensitive() {
        var service = new DefaultConversionService();

        assertEquals(OrderStatus.DONE,
                service.convert(" DONE ", OrderStatus.class));
        assertNull(service.convert("", OrderStatus.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert("done", OrderStatus.class));
        assertThrows(ConversionFailedException.class,
                () -> service.convert("   ", OrderStatus.class));
    }

    @Test
    void customConversionAcceptsMixedCase() {
        var service = new DefaultConversionService();
        service.addConverter(new OrderStatusConverter());

        assertEquals(OrderStatus.DONE,
                service.convert(" dOnE ", OrderStatus.class));
        assertEquals(OrderStatus.IN_PROGRESS,
                service.convert("in_progress", OrderStatus.class));
        assertNull(service.convert("   ", OrderStatus.class));

        assertThrows(ConversionFailedException.class,
                () -> service.convert("finished", OrderStatus.class));
    }
}
```

Bộ test thứ nhất xác nhận mặc định Spring Framework; bộ test thứ hai xác nhận **converter do ta chủ động đăng ký**. Chúng không chứng minh toàn bộ ứng dụng web đang dùng đúng cùng registry: nên có thêm integration test với `MockMvc` cho endpoint thật, kiểm tra cả case hợp lệ, case sai, đầu vào rỗng và mã HTTP tương ứng.

Bảng test tích hợp gợi ý khi sử dụng converter tùy chỉnh của mục 6:

| `status` trên URL | Giá trị sau conversion | Hành vi mong đợi |
| --- | --- | --- |
| `DONE` | `DONE` | Thành công |
| `done` | `DONE` | Thành công |
| `DoNe` | `DONE` | Thành công |
| `%20done%20` | `DONE` | Thành công |
| `in_progress` | `IN_PROGRESS` | Thành công |
| `in-progress` | Không khớp | Lỗi đầu vào |
| `unknown` | Không khớp | Lỗi đầu vào |
| `%20%20%20` | `null` | Với `@RequestParam` bắt buộc, thông thường 400 vì thiếu giá trị sau chuyển đổi |

## 8. Phân biệt chuyển kiểu với validation, JSON và cấu hình

**Conversion là bước đi trước validation.** Bộ chuyển đổi phải tạo được `OrderStatus` từ chuỗi trước khi các ràng buộc Bean Validation như `@NotNull` trên thuộc tính có kiểu enum phát huy tác dụng. `@NotNull` chỉ kiểm tra giá trị null, **không tự chấp nhận `done` hoặc chuẩn hóa chuỗi**. Nếu conversion thất bại, có thể xuất hiện lỗi type mismatch ở tầng binding; không nên kỳ vọng mọi đầu vào enum sai đều tạo thông báo `@NotNull`.

**`@RequestBody` JSON thường đi qua Jackson**, ví dụ body `{"status":"done"}` của DTO được deserialize bằng `ObjectMapper`. `Converter<String, OrderStatus>` đã đăng ký ở `WebMvcConfigurer.addFormatters` không tự trở thành deserializer JSON. Chính sách enum JSON cần cấu hình Jackson thích hợp (chẳng hạn cơ chế case-insensitive enum hoặc `@JsonCreator`), đồng bộ với hợp đồng API.

**Binding cấu hình của Spring Boot có thể khác Spring MVC.** Spring Boot cung cấp các converter và cơ chế relaxed binding trong một số ngữ cảnh cấu hình, trong đó có hỗ trợ enum không phân biệt hoa/thường. Không suy ra từ việc `@ConfigurationProperties` nhận `done` rằng mọi `@RequestParam` của ứng dụng đều nhận `done`. Hãy kiểm tra `ConversionService` thực sự được sử dụng trong luồng cần xử lý và test trên chính phiên bản/cấu hình dự án.

**Chữ hoa/thường là một quyết định về API contract.** Nếu client đã được quy định gửi đúng tên enum, ưu tiên giữ chính sách strict để bắt lỗi gõ sớm. Nếu cho phép nhiều kiểu viết để cải thiện trải nghiệm, cần mô tả rõ quy tắc chuẩn hóa, ví dụ `case-insensitive + trim`, và phạm vi áp dụng. Nếu enum là một phần API công khai ổn định, việc đổi tên hằng `NEW` thành `CREATED` có thể làm client cũ hỏng ngay cả khi bật bỏ qua hoa/thường.

## 9. Những lỗi phổ biến và cách tìm nguyên nhân

- **`done` bị lỗi dù enum có `DONE`:** kiểm tra case-sensitive default; chọn gửi `DONE` hoặc đăng ký converter phù hợp.
- **`" DONE "` chạy nhưng `"  "` lỗi:** Spring mặc định trim trước `valueOf` nhưng chỉ đặc biệt xử lý chuỗi **rỗng từ đầu**; cần quyết định chính sách cho whitespace-only.
- **Đã viết converter nhưng endpoint vẫn lỗi:** kiểm tra class cấu hình có được scan không, converter đã được thêm vào `FormatterRegistry` của MVC chưa, có registry/`ConversionService` khác đang được dùng không.
- **Query parameter chạy nhưng JSON body vẫn lỗi:** Jackson deserialize JSON theo cơ chế riêng; kiểm tra cấu hình mapper.
- **Một enum áp dụng được nhưng enum khác không:** `Converter<String, OrderStatus>` chỉ phụ trách `OrderStatus`. Muốn áp dụng nhiều enum, cân nhắc `ConverterFactory<String, Enum>` và đánh giá ảnh hưởng toàn hệ thống trước khi đăng ký.
- **Giá trị hiển thị của enum được dịch hoặc override `toString()`:** mặc định tra theo `name()`; nếu cần mã miền hoặc nhãn, tạo mapping riêng, tránh trộn tên Java với định dạng giao tiếp.
- **Lỗi HTTP bị hiểu nhầm là lỗi `@NotNull`:** xem nguyên nhân gốc (type conversion hay constraint violation), tham số bắt buộc, và `BindingResult`/exception handler.

## 10. Tóm lược quy tắc thực hành

1. Bắt đầu từ enum và hợp đồng đầu vào: tên hằng nào được phép, có chấp nhận khác hoa/thường, khoảng trắng hoặc alias không?
2. Với `ConversionService` mặc định của Spring Framework, `String` → `Enum` **phân biệt hoa/thường**, có `trim()`; `""` trả null, còn chuỗi toàn khoảng trắng có thể lỗi.
3. Khi cần bỏ qua hoa/thường, chuẩn hóa có chủ đích bằng `Locale.ROOT` và `Enum.valueOf` trong một converter, rồi đăng ký đúng registry. Đừng nuốt giá trị lạ thành default.
4. Test riêng converter và test binding thực tế (query/path/form). Nếu có JSON body, test Jackson độc lập; nếu có binding cấu hình, test Spring Boot trong ngữ cảnh đó.
5. Coi tên hằng enum là một phần hợp đồng giữa các hệ thống nếu chúng được gửi trực tiếp qua API.

### Tài liệu tham khảo

- Spring Framework — [Type Conversion trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- Spring Framework — [Type Conversion và ConverterFactory](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).
- Mã nguồn Spring Framework — [StringToEnumConverterFactory](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/StringToEnumConverterFactory.java).
