# Phân biệt định dạng trường của Spring với tuần tự hóa JSON

> **Bối cảnh:** Spring MVC, cơ chế data binding/field formatting của Spring Framework và JSON (de)serialization qua Jackson. Ví dụ dùng Java 17, Spring Boot 3.3.x để chạy thử Spring MVC. Trọng tâm là **định dạng số**; định dạng ngày được nhắc thêm để làm rõ ranh giới giữa hai cơ chế.

## 1. Hai cơ chế giải quyết hai bài toán khác nhau

**Field formatting** của Spring biến đổi giữa *chuỗi người dùng nhập hoặc nhìn thấy* và *giá trị Java có kiểu* trong quá trình binding hoặc hiển thị biểu mẫu. Ví dụ, một người dùng theo locale `en-US` nhập `1,234.50`; Spring có thể phân tích chuỗi đó thành `BigDecimal("1234.50")`. Khi hiển thị lại form, formatter có thể in số thành `1,234.50`.

**JSON serialization** biến một object Java thành phần thân HTTP chứa JSON; **JSON deserialization** làm chiều ngược lại. Khi endpoint dùng `@RequestBody` hoặc trả object qua `@ResponseBody`/`@RestController`, Spring MVC thường chọn JSON `HttpMessageConverter` dùng Jackson. Số JSON là token theo cú pháp JSON, ví dụ `1234.50`, **không có dấu phân tách hàng nghìn tùy locale**.

| Câu hỏi | Spring field formatting | JSON qua Jackson |
| --- | --- | --- |
| Dữ liệu đầu vào thường gặp | Query parameter, path variable, form field, `@ModelAttribute` | Body `application/json` với `@RequestBody` |
| Thành phần chính | `WebDataBinder`, `ConversionService`, `Converter`, `Formatter` | `HttpMessageConverter`, `ObjectMapper`, serializer/deserializer |
| Annotation tiêu biểu | `@NumberFormat`, `@DateTimeFormat` | `@JsonFormat`, `@JsonSerialize`, `@JsonDeserialize`, `@JsonProperty` |
| Quan tâm đến locale | Có thể dùng `Locale` để parse/print chuỗi hiển thị | JSON number có cú pháp độc lập với locale; cấu hình Jackson riêng nếu cần |
| Đích tác động | Chuỗi ↔ giá trị trường/đối số Java khi binding hoặc render form | Cách object ↔ JSON body được đọc/ghi |
| Có tự động điều khiển cơ chế còn lại không? | Không | Không |

Lưu ý: `@ModelAttribute` có thể nhận query parameter và dữ liệu form; còn `@RequestBody` đọc body thông qua message converter. Dù hai đường đi có thể cùng tạo ra một object Java, **chúng không dùng chung quy tắc format theo annotation một cách mặc định**.

## 2. Đường đi của một giá trị số

### 2.1. Query/form → Spring data binding

```text
GET /amount/form?amount=1%2C234.50
     │  chuỗi "1,234.50", locale en-US
     ▼
Spring MVC argument resolution / @ModelAttribute
     ▼
WebDataBinder → FormattingConversionService
     ▼
@NumberFormat(pattern = "#,##0.00")
     ▼
BigDecimal(1234.50) trong object Java
```

`Formatter<T>` cung cấp `parse(String, Locale)` để đọc chuỗi và `print(T, Locale)` để tạo chuỗi hiển thị. `ConversionService` là API chuyển kiểu thống nhất của Spring, có thể phối hợp `Converter` và `Formatter`. Một formatter có thể được đăng ký chung hoặc được chọn qua annotation trên trường.

`@NumberFormat` ở đây mô tả cách số được **parse/print trong binding/formatting**. Nó không đổi bản chất của `BigDecimal` thành text, không tự làm tròn giá trị nghiệp vụ để lưu xuống database, và không ép Jackson xuất JSON theo pattern này.

Ví dụ pattern `#,##0.00` được diễn giải theo quy tắc định dạng số và locale. Với `en-US`, dấu phẩy phân nhóm nghìn và dấu chấm phân cách phần thập phân; ở nhiều locale khác, ký hiệu có thể đảo ngược. Đừng suy từ cùng một chuỗi `1,234` ra cùng một số ở mọi locale.

### 2.2. JSON body → Jackson deserialization

```text
POST /amount/json
Content-Type: application/json

{"amount":1234.50}
     ▼
@RequestBody → JSON HttpMessageConverter → Jackson
     ▼
AmountJson(BigDecimal("1234.50"))
```

Ở đường này, Jackson đọc token JSON theo cấu hình của chính nó. Nếu DTO có `@NumberFormat`, Jackson **không mặc nhiên dùng** formatter của Spring để parse chuỗi JSON.

Chiều trả dữ liệu:

```text
Java object có amount = BigDecimal("1234.50")
     ▼
@RestController / @ResponseBody
     ▼
JSON HttpMessageConverter → Jackson
     ▼
{"amount":1234.50}
```

JSON number hợp lệ là `1234.50`; `1,234.50` không phải một token số JSON hợp lệ. Chuỗi `"1,234.50"` là *JSON string* hợp lệ, nhưng không phải JSON number; Jackson mặc định không được giả định sẽ hiểu dấu phẩy phân nhóm nghìn khi bind chuỗi ấy vào `BigDecimal`.

## 3. Ví dụ chạy được: cùng trường `amount`, hai đường xử lý

Tạo dự án Maven Java 17 với cấu trúc:

```text
format-vs-json/
├── pom.xml
└── src/main/java/demo/FormatBoundaryApplication.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>format-vs-json</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**`src/main/java/demo/FormatBoundaryApplication.java`**:

```java
package demo;

import java.math.BigDecimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormatBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatBoundaryApplication.class, args);
    }

    @RestController
    public static class AmountController {

        // Spring bind chuỗi query vào thuộc tính của @ModelAttribute.
        @GetMapping(value = "/amount/form",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public String fromForm(@ModelAttribute AmountForm form) {
            BigDecimal amount = form.getAmount();
            return amount == null
                    ? "amount=<missing>"
                    : "amount=" + amount.toPlainString();
        }

        // Jackson đọc JSON body và ghi JSON response.
        @PostMapping(value = "/amount/json",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.APPLICATION_JSON_VALUE)
        public AmountJson fromJson(@RequestBody AmountJson payload) {
            return payload;
        }
    }

    public static class AmountForm {
        @NumberFormat(pattern = "#,##0.00")
        private BigDecimal amount;

        public BigDecimal getAmount() {
            return amount;
        }

        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    public record AmountJson(BigDecimal amount) { }
}
```

Chạy từ thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn spring-boot:run
```

**Thử 1 — binding một giá trị biểu mẫu** (dùng terminal thứ hai):

```bash
curl -sS -G 'http://localhost:8080/amount/form' \
  -H 'Accept-Language: en-US' \
  --data-urlencode 'amount=1,234.50'
```

Phần thân phản hồi:

```text
amount=1234.50
```

Ở đây `@NumberFormat` giúp Spring đọc giá trị hiển thị `1,234.50` và tạo `BigDecimal`. `toPlainString()` chỉ được dùng để tạo kết quả dễ quan sát trong ví dụ; đây **không phải serialization JSON**.

**Thử 2 — JSON body**:

```bash
curl -sS -X POST 'http://localhost:8080/amount/json' \
  -H 'Content-Type: application/json' \
  -d '{"amount":1234.50}'
```

Phần thân phản hồi dự kiến (với Jackson mặc định trong dự án mẫu):

```json
{"amount":1234.50}
```

Jackson xử lý `BigDecimal` theo JSON number. `AmountJson` không có `@NumberFormat`, và thêm annotation đó vào DTO JSON cũng không làm Jackson áp dụng pattern format của Spring.

**Thử 3 — gửi kiểu “số có phân nhóm nghìn” trong JSON**:

```json
{"amount":1,234.50}
```

Đây là **JSON không hợp lệ**: dấu phẩy ngăn cách các phần tử/cặp thuộc tính, không có vai trò phân nhóm nghìn trong literal số. Gửi `{"amount":"1,234.50"}` thì tài liệu JSON hợp lệ về cú pháp nhưng giá trị `amount` lại là chuỗi; với Jackson mặc định, nó không thỏa định dạng chuỗi số thông thường để chuyển thành `BigDecimal`.

## 4. Hai DTO cùng kiểu Java vẫn có thể có cách biểu diễn khác nhau

Đây là đoạn code minh họa đặt trong các DTO tương ứng (không phải chương trình độc lập):

```java
// DTO dùng cho query/form binding:
public class SearchForm {
    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    // Constructor/getter/setter phù hợp với kiểu binding đã chọn.
}

// DTO dùng cho JSON body:
public record SearchJson(
    BigDecimal amount,
    @JsonFormat(pattern = "dd/MM/yyyy") LocalDate fromDate
) { }
```

Các import tương ứng: `org.springframework.format.annotation.NumberFormat`, `org.springframework.format.annotation.DateTimeFormat`, `com.fasterxml.jackson.annotation.JsonFormat`, `java.math.BigDecimal` và `java.time.LocalDate`.

- `@DateTimeFormat` giúp Spring parse/print trường ngày ở đường binding. Nó không tự bắt JSON dùng cùng pattern.
- `@JsonFormat(pattern = "dd/MM/yyyy")` yêu cầu **Jackson** định dạng một kiểu ngày có hỗ trợ pattern đó. Với `LocalDate`, cần module Java Time của Jackson; `spring-boot-starter-web` trong ví dụ Boot 3 đã cung cấp/cấu hình module này.
- `@JsonFormat` không phải “bản sao JSON” của `@NumberFormat`: ý nghĩa của `pattern` tùy serializer/deserializer và kiểu dữ liệu. Không nên giả định `@JsonFormat(pattern = "#,##0.00")` sẽ làm `BigDecimal` thành số JSON có dấu phân nhóm.
- `@JsonProperty("amount")` thay tên thuộc tính JSON; nó không biến dấu phân cách thập phân theo locale. Ngược lại, `@NumberFormat` không đổi tên JSON property.

Nếu API **thực sự phải trả số đã định dạng để hiển thị** (ví dụ `"1,234.50"`), hãy thiết kế một trường `String` rõ nghĩa như `displayAmount` ở response DTO, hoặc dùng Jackson custom serializer ghi **JSON string** có kiểm soát. Giữ trường `amount` kiểu JSON number cho tính toán, sắp xếp và tích hợp giữa hệ thống.

Ví dụ response có hai trường tách biệt:

```json
{
  "amount": 1234.50,
  "displayAmount": "1,234.50"
}
```

`displayAmount` được tạo bằng lớp trình bày tương ứng với locale của người xem; client khác locale không nhất thiết dùng đúng chuỗi này. Tránh dùng chuỗi trình bày làm dữ liệu nghiệp vụ hoặc định dạng chuẩn giao tiếp.

## 5. Phân biệt lỗi binding và lỗi đọc JSON

| Tình huống | Nơi phát sinh vấn đề | Hướng xử lý |
| --- | --- | --- |
| Query/form nhập chuỗi số không phù hợp locale/pattern | Spring binding/`ConversionService`; có thể thành lỗi trường trong `BindingResult` | Hiển thị lỗi nhập liệu, kiểm tra locale/pattern, đặt `BindingResult` sau `@ModelAttribute` nếu muốn xử lý tại controller |
| Body JSON sai cú pháp, chẳng hạn `{"amount":1,234.50}` | JSON parser/message converter; thường dẫn tới `HttpMessageNotReadableException` và HTTP 400 | Sửa JSON theo cú pháp chuẩn |
| Body hợp lệ nhưng không deserialize được vào DTO | Jackson mapping/deserialization | Kiểm tra kiểu trường và JSON contract; dùng custom deserializer khi có yêu cầu rõ |
| Đầu ra JSON dùng khác pattern form | Hai cơ chế được cấu hình riêng | Kiểm tra `@NumberFormat`/`ConversionService` ở form và Jackson configuration/annotation ở JSON |

Trong Spring MVC, lỗi binding/validation có thể được ánh xạ thành HTTP 400 theo cấu hình và chữ ký method; **đừng mặc định mọi lỗi đều có cùng exception hoặc body lỗi**. `@Valid`/Bean Validation kiểm tra ràng buộc dữ liệu *sau hoặc kết hợp với* quá trình chuyển kiểu, và không thay thế formatter/deserializer.

## 6. Nguyên tắc thiết kế và các lỗi thường gặp

1. **Chọn đúng đường dữ liệu:** Query/form/`@ModelAttribute` cần nghĩ đến `Converter`/`Formatter`/`@NumberFormat`; JSON request/response cần nghĩ đến Jackson và JSON message converter.
2. **Tách dữ liệu máy đọc khỏi trình bày:** JSON number `1234.50` là contract ổn định; dấu phân nhóm hàng nghìn, dấu thập phân và ký hiệu tiền tệ nên được xử lý ở tầng hiển thị. Không truyền `"1.234,50"` như giá trị số chuẩn chung nếu API không định nghĩa rõ loại chuỗi đó.
3. **Kiểm soát locale một cách có chủ đích:** Test `en-US` và locale phục vụ người dùng; kiểm tra locale resolver, ký tự khoảng trắng/dấu phân nhóm và input thực tế. Không xem `Locale.getDefault()` của JVM là luôn trùng locale của request.
4. **Giữ độ chính xác:** Dùng `BigDecimal` cho tiền hoặc số thập phân cần độ chính xác thập phân; `double` có thể gây sai số nhị phân. Chỉ làm tròn theo quy tắc nghiệp vụ rõ ràng; format hiển thị không được ngầm thay đổi amount gốc.
5. **Không lẫn annotation:** `@NumberFormat` không định dạng JSON; `@JsonFormat` không điều khiển Spring form binding; `@JsonProperty` không đổi cách parse số. Các annotation không đồng bộ tự động chỉ vì đặt trên cùng một field.
6. **Không nhầm cú pháp JSON:** `{"amount":1,234.50}` sai cú pháp; `{"amount":"1,234.50"}` là chuỗi, không phải số. JSON number luôn dùng dấu chấm cho phần thập phân và không có dấu phân nhóm nghìn.
7. **Test cả hai chiều:** Với form, test parse và print theo locale; với JSON, test deserialize request và serialize response, bao gồm lỗi kiểu/cú pháp và độ chính xác `BigDecimal`. Assert giá trị số và kiểu JSON, đừng chỉ so sánh một đoạn text được in ra.

## 7. Checklist chọn công cụ

- Cần đọc `1,234.50` theo locale `en-US` từ query/form thành `BigDecimal`? → `@NumberFormat` hoặc `Formatter<BigDecimal>` qua `ConversionService`.
- Cần trả `{"amount":1234.50}` từ `@RestController`? → DTO JSON với `BigDecimal` và Jackson mặc định là điểm xuất phát.
- Cần đổi biểu diễn ngày của JSON? → Xem `@JsonFormat`/Jackson Java Time, độc lập với `@DateTimeFormat` dùng trong form.
- Cần trường hiển thị có dấu nhóm hoặc ký hiệu tiền tệ? → Tạo `displayAmount` kiểu chuỗi và format rõ locale; không đổi ngữ nghĩa trường số gốc.
- Cần chẩn đoán lỗi parse? → Xác định request đi qua `WebDataBinder` hay qua JSON message converter trước khi thay annotation/configuration.

**Kết luận:** Spring field formatting xử lý **chuỗi theo ngữ cảnh nhập/xuất trường**; JSON serialization xử lý **biểu diễn object trong message body**. Một DTO có thể được cả hai đường sử dụng, nhưng các cơ chế chuyển đổi và annotation của chúng vẫn có ranh giới riêng.

### Đọc thêm (tài liệu chính thức)

- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
