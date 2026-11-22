# Ánh xạ đường dẫn collection hoặc Map ra hợp đồng API trong Spring Validation

## 1. Vấn đề: lỗi nằm sâu trong danh sách hoặc Map thì trả đường dẫn nào?

Một REST API nhận dữ liệu lồng nhau có thể chứa danh sách sản phẩm, các địa chỉ, cấu hình theo khóa động hoặc danh sách đối tượng con. Khi Spring MVC và Jakarta Validation kiểm tra dữ liệu, lỗi thường có **đường dẫn field nội bộ** như:

```text
lineItems[0].sku
lineItems[1].quantity
preferences[alerts].enabled
preferences[weekly.news].enabled
```

Nhưng frontend cần biết **vị trí nào trong JSON request** đang bị lỗi để đánh dấu đúng ô nhập, cuộn đến dòng trong danh sách hoặc hiển thị thông báo cạnh cấu hình có khóa cụ thể.

Vấn đề là:

- `FieldError#getField()` của Spring có thể dùng cú pháp **dấu chấm và ngoặc vuông** theo property path.
- Mảng JSON được đánh số **từ 0**; Map JSON là **object với key dạng string**.
- Key của Map có thể chứa dấu chấm, dấu gạch chéo, dấu ngã hoặc ký tự đặc biệt.
- Một path từ Java object **không nhất thiết** trùng với field name trong JSON nếu dùng `@JsonProperty`, naming strategy, alias hoặc DTO mapping.
- Một array index có thể đổi khi người dùng chèn, xóa hoặc sắp xếp lại dòng.
- Một lỗi có thể gắn với cả collection hoặc object, **không phải** một phần tử cụ thể.

Vì vậy, thay vì trả nguyên chuỗi Spring path rồi bắt client đoán ý nghĩa, nên **định nghĩa một hợp đồng API rõ ràng về vị trí lỗi**. Bài sử dụng **JSON Pointer (RFC 6901)** cho request nhận JSON, đồng thời giải thích khi nào không thể chuyển an toàn và cần trả một lỗi ở mức object/request.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện path của `List`, array, `Map` và nested bean trong `BindingResult` / `FieldError`.
2. Phân biệt đường dẫn Java/Spring với đường dẫn của tài liệu JSON gửi qua HTTP.
3. Chuyển những trường hợp **đã được ràng buộc cú pháp** sang JSON Pointer, xử lý escape đúng theo RFC 6901.
4. Trả response có `pointer`, `code`, `message`, bảo đảm mã lỗi không phụ thuộc cách dịch.
5. Tách validation errors khỏi JSON parse/deserialization errors và method validation.
6. Viết kiểm thử `MockMvc` để kiểm chứng thứ tự, index, Map key và những tình huống không thể suy ra path.
7. Tránh lộ thông tin nhạy cảm trong Map key, tránh mass assignment và tránh một parser tùy tiện biến key thành đường dẫn giả.

**Phạm vi kỹ thuật:** Spring Framework 6.x, Spring MVC, Java 17+, Spring Boot 3.x, Jakarta Validation. Những ví dụ `WebFlux` có pipeline exception khác nên không được coi là tương đương tuyệt đối.

## 2. Đường dẫn Spring được hình thành như thế nào?

Ví dụ một Java DTO:

```java
public record CheckoutRequest(
        List<CartLine> lineItems,
        Map<String, NotificationPreference> preferences) {
}

public record CartLine(String sku, Integer quantity) {
}

public record NotificationPreference(Boolean enabled) {
}
```

Các class trên là **fragment mô hình**, chưa có constraints. Khi bổ sung `@Valid` trên nested values và constraint phù hợp, Bean Validation có thể phát hiện:

- Sản phẩm đầu tiên thiếu SKU: `lineItems[0].sku`.
- Sản phẩm thứ hai có quantity dưới mức yêu cầu: `lineItems[1].quantity`.
- Cấu hình `alerts` không có giá trị `enabled`: `preferences[alerts].enabled`.
- Map key chứa dấu chấm `weekly.news`: `preferences[weekly.news].enabled`.

Spring chuyển các vi phạm Jakarta Validation sang `FieldError` hoặc `ObjectError` trong `BindingResult`; việc dựng field path thường đi qua `SpringValidatorAdapter`. Với `@Valid @RequestBody` trên một object đơn lẻ trong Spring MVC, lỗi constraint thường được đưa vào `MethodArgumentNotValidException`, và exception này cung cấp `getBindingResult()`.

Ví dụ đọc các field errors trong một handler:

```java
List<FieldError> errors =
        ex.getBindingResult().getFieldErrors();

for (FieldError error : errors) {
    String springPath = error.getField();
    String[] lookupCodes = error.getCodes();
    boolean conversionFailure = error.isBindingFailure();
}
```

Đoạn trên là **fragment** trong nơi đã có biến `MethodArgumentNotValidException ex` và các imports cần thiết. Chú ý: `getField()` là chuỗi metadata của Spring, còn `getCodes()` là các mã tra cứu thông điệp; cả hai **không tự động là hợp đồng API public ổn định**.

### Vì sao Map key chứa dấu chấm đặc biệt nguy hiểm khi split?

Giả sử:

```text
preferences[weekly.news].enabled
```

Nếu code đơn giản gọi `path.split("\\.")`, nó có thể tách key `weekly.news` thành hai đoạn `weekly` và `news`. Kết quả này sai: key trong JSON là một chuỗi **duy nhất** `"weekly.news"`.

Trong đường dẫn Spring, dấu chấm ở **ngoài** ngoặc vuông thường dùng để đi xuống thuộc tính JavaBean, còn dấu chấm ở **trong** ngoặc có thể thuộc về nội dung key của Map. Một bộ chuyển đường dẫn đúng phải **phân tích từng segment**, không chỉ thay chuỗi ký tự tùy tiện.

### Bảng ví dụ trước và sau khi chuyển đổi

| Nguồn Spring | Ý nghĩa dữ liệu | Pointer API dự kiến |
| --- | --- | --- |
| `name` | Property gốc | `/name` |
| `lineItems[0].sku` | SKU của phần tử đầu tiên | `/lineItems/0/sku` |
| `lineItems[12].quantity` | Số lượng của phần tử thứ 13 | `/lineItems/12/quantity` |
| `lineItems` | Lỗi ở cả danh sách | `/lineItems` |
| `preferences[alerts].enabled` | Map key `alerts` | `/preferences/alerts/enabled` |
| `preferences[weekly.news].enabled` | Map key có dấu chấm | `/preferences/weekly.news/enabled` |
| `preferences[team/a~b].enabled` | Map key có `/` và `~` | `/preferences/team~1a~0b/enabled` |
| `shipping.address.postcode` | Thuộc tính lồng nhau | `/shipping/address/postcode` |
| Lỗi cấp object | Không có field path duy nhất | `""` (pointer đến root) |

Các ví dụ là **quy ước chuyển đường dẫn** cho DTO có property name trùng JSON name. Đối với key phức tạp chứa ký tự quoting, ngoặc vuông đóng, escape hoặc việc chuyển kiểu key của Map, không nên dùng một phép thay thế chuỗi chung mà không kiểm chứng format thực tế.

## 3. JSON Pointer (RFC 6901): định nghĩa và escape

JSON Pointer có dạng một chuỗi gồm các **reference tokens** phân cách bằng `/`. Trường `pointer` trong hợp đồng của bài sẽ là **string representation** của RFC 6901, không phải URI fragment.

Ví dụ request:

```json
{
  "lineItems": [
    {"sku": "ABC", "quantity": 2},
    {"sku": "", "quantity": 0}
  ],
  "preferences": {
    "alerts": {"enabled": true},
    "weekly.news": {"enabled": null}
  }
}
```

Các pointer:

- `/lineItems/0/sku` → `"ABC"`.
- `/lineItems/1/quantity` → `0`.
- `/preferences/alerts/enabled` → `true`.
- `/preferences/weekly.news/enabled` → `null`.

**Quy tắc escape bắt buộc theo RFC 6901**: trong mỗi token,

- Ký tự `~` được thay thành `~0`.
- Ký tự `/` được thay thành `~1`.

Ví dụ token `team/a~b` trở thành `team~1a~0b`. Token có dấu chấm như `weekly.news` **không** cần escape dấu chấm trong JSON Pointer.

Thứ tự encode là:

```java
static String escapePointerToken(String token) {
    return token.replace("~", "~0").replace("/", "~1");
}
```

Khi **decode** một token, thứ tự ngược đúng theo RFC là thay `~1` thành `/` **trước**, sau đó thay `~0` thành `~`. Nếu làm ngược, token chứa `~01` có thể bị giải mã sai.

### Pointer rỗng và pointer có một slash không giống nhau

- Chuỗi **`""`** đại diện **toàn bộ JSON document** (root).
- Chuỗi **`"/"`** đại diện member có key **rỗng** của object gốc.
- Chuỗi **`"/lineItems"`** trỏ đến collection, không phải từng phần tử.
- Chuỗi **`"/lineItems/0"`** trỏ đến object phần tử đầu tiên.

Cần nêu rõ quy tắc này trong API schema. Tránh dùng `"/"` để biểu thị “không biết lỗi ở đâu”; nó có nghĩa khác `""` trong JSON Pointer.

### Pointer trong JSON string khác URI fragment

- String pointer: `/preferences/team~1a~0b/enabled`.
- URI fragment representation: có thể có dấu `#` phía trước và còn phải percent-encode theo quy tắc URI fragment.

Không tự thêm dấu `#` vào trường `pointer` nếu hợp đồng định nghĩa **string representation**. Nếu bạn đưa pointer vào đường dẫn/fragment của URL, phải thực hiện URI encoding phù hợp, không chỉ escape `~` và `/`.

### Pointer cú pháp hợp lệ nhưng có thể không resolve được trên body lỗi

Ví dụ JSON gửi lên **thiếu hẳn** field `enabled`:

```json
{"preferences":{"alerts":{}}}
```

Jakarta `@NotNull` trên `enabled` vẫn có thể tạo field path `preferences[alerts].enabled`, vì model sau deserialization có giá trị `null`. Tuy nhiên, pointer `/preferences/alerts/enabled` **không resolve thành một member đã có trong JSON gốc**, vì request không gửi key đó.

Do vậy, nếu API dùng pointer để **chỉ vị trí field được kỳ vọng theo schema**, hãy tài liệu hóa rằng một pointer có thể biểu thị **địa chỉ logic cần sửa** chứ không đảm bảo reference tồn tại trong raw request. Nếu người dùng cần tuân thủ JSON Pointer evaluation nghiêm ngặt, cân nhắc trả lỗi ở parent pointer `/preferences/alerts` và cung cấp một trường riêng `missingField="enabled"`. Quyết định này thuộc **API contract**, không thể giải quyết chỉ bằng string parser.

## 4. Ba cách trả vị trí lỗi trong API

### 4.1. Cách A: trả nguyên Spring property path

Ví dụ:

```json
{
  "field": "lineItems[1].quantity",
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

Ưu điểm: ít chuyển đổi, gần `BindingResult`. Nhược điểm: client phải biết cú pháp property path của Spring; dễ gây phụ thuộc vào refactor Java và khó xử lý Map keys đặc biệt.

Phù hợp khi frontend và backend cùng dùng quy ước nội bộ, có test rõ ràng, không xem path là hợp đồng độc lập dài hạn.

### 4.2. Cách B: trả JSON Pointer theo request contract

Ví dụ:

```json
{
  "pointer": "/lineItems/1/quantity",
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

Ưu điểm: chuẩn vị trí rõ ràng với JSON; frontend có thể liên kết pointer với cây biểu mẫu mà không cần hiểu cú pháp Java. Rủi ro: server phải ánh xạ **đúng tên JSON** và Map keys, xử lý escape và container indexes.

Đây là hướng được minh họa bằng code runnable phía dưới.

### 4.3. Cách C: trả danh sách path segments có cấu trúc

Ví dụ:

```json
{
  "segments": ["lineItems", 1, "quantity"],
  "code": "MIN_VALUE",
  "message": "Quantity must be at least 1"
}
```

Một Map key dạng chuỗi `"0"` khác array index số `0` khi dùng kiểu dữ liệu JSON phù hợp, vì thế segments có kiểu rõ ràng giúp biểu diễn ý nghĩa tốt hơn. Tuy nhiên, đây là **schema tự định nghĩa**, không phải chính JSON Pointer RFC 6901; client và server phải thống nhất định dạng, dữ liệu số/nguyên, cách xử lý parent và lỗi root.

Nếu nhu cầu là xử lý form trong frontend chứ không phải generic JSON tree, một API có thể chọn path segments thay cho pointer. Nhưng **đừng gửi cả ba định dạng mà không chỉ rõ định dạng nào là canonical**; hệ thống sẽ phải bảo trì nhiều đại diện dễ lệch nhau.

### Quyết định bài học

Chúng ta chọn một trường **`pointer` dạng JSON Pointer string**, một trường **`code` ổn định** và một trường **`message`** để hiển thị. Nếu không thể ánh xạ path an toàn, ví dụ sẽ dùng pointer `""` (root fallback), không công bố đường dẫn đoán mò.

## 5. Mã lỗi ổn định không nên phụ thuộc vào đường dẫn

Một lỗi ở `lineItems[0].sku` và một lỗi ở `lineItems[8].sku` có thể cùng mang mã `REQUIRED_TEXT`. Index thể hiện **vị trí hiện tại**, không phải một loại lỗi khác.

Ví dụ:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    },
    {
      "pointer": "/lineItems/8/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    }
  ]
}
```

Không đặt tên mã theo index, ví dụ `LINE_0_SKU_EMPTY` hoặc `LINE_8_SKU_EMPTY`. Khi user thêm một dòng đầu danh sách, các index thay đổi, nhưng lỗi “text required” không đổi về ngữ nghĩa.

**Những điều cần ổn định** trong API contract:

- Tên trường response như `code`, `errors`, `pointer`.
- Ý nghĩa của `code`: ví dụ `REQUIRED_TEXT`, `MIN_VALUE`, `REQUIRED_VALUE`.
- Cú pháp của pointer: JSON Pointer string, quy tắc escape và root fallback.
- Hành vi khi không thể biểu diễn path.
- Quy tắc HTTP status cho validation errors và lỗi deserialize.
- Cách sắp xếp errors nếu client hoặc test cần thứ tự ổn định.

**Những điều có thể thay đổi có kiểm soát:** câu `message` đã dịch, thứ tự lỗi đầu vào của validator, index theo trạng thái mảng lúc request, và cách Java class tổ chức nội bộ miễn translation layer giữ API contract.

## 6. Ví dụ chạy được bằng Java 17: Spring Boot MVC, List và Map

### 6.1. Mục tiêu của ví dụ

Tạo endpoint `POST /baskets` nhận JSON có:

- `lineItems` là `List<LineItem>`, mỗi phần tử có `sku` và `quantity`.
- `preferences` là `Map<String, NotificationPreference>`, mỗi value có `enabled`.
- Dữ liệu sai constraint đi qua `MethodArgumentNotValidException`.
- HTTP response chứa một danh sách lỗi có pointer đã chuyển đúng cú pháp.
- JSON không đọc được trả mã riêng `UNREADABLE_BODY`, **không** có danh sách pointer giả.
- Tên Java property trùng tên JSON field trong demo; các tình huống `@JsonProperty`/naming strategy khác cần một lớp mapping riêng.

Một số payload thử nghiệm:

```json
{
  "lineItems": [
    {"sku": "", "quantity": 0},
    {"sku": "SKU-2", "quantity": 3}
  ],
  "preferences": {
    "alerts": {"enabled": null}
  }
}
```

Lỗi dự kiến ở `/lineItems/0/sku`, `/lineItems/0/quantity` và `/preferences/alerts/enabled`.

### 6.2. Cấu trúc thư mục

```text
nested-errors-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── NestedErrorsApplication.java
    │   ├── CreateBasketRequest.java
    │   ├── BasketController.java
    │   ├── SpringFieldPath.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── SpringFieldPathTest.java
        └── BasketControllerTest.java
```

### 6.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>nested-errors-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

Các starter Spring Boot quản lý đồng bộ phiên bản MVC/Jackson/Hibernate Validator. `spring-boot-starter-validation` cần thiết để `@Valid` đánh giá các Jakarta constraints của ví dụ.

### 6.4. NestedErrorsApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedErrorsApplication.class, args);
    }
}
```

### 6.5. CreateBasketRequest.java

```java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateBasketRequest(
        @NotEmpty List<@Valid LineItem> lineItems,
        @NotNull Map<String, @Valid NotificationPreference> preferences
) {

    public record LineItem(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity
    ) {
    }

    public record NotificationPreference(
            @NotNull Boolean enabled
    ) {
    }
}
```

**Tại sao đặt `@Valid` trong các type arguments?**

- `List<@Valid LineItem>` yêu cầu cascade validation vào **từng phần tử** danh sách.
- `Map<String, @Valid NotificationPreference>` yêu cầu cascade vào **từng value** của Map.
- `@NotEmpty` trên list yêu cầu collection có ít nhất một phần tử (và không null).
- `@NotNull` trên Map yêu cầu map không null, **nhưng không cấm map rỗng**.
- `@NotNull` trên `enabled` cho phép phát hiện dữ liệu null hoặc thiếu key `enabled` trong value object.
- `@Min(1)` áp dụng cho `Integer quantity` sau khi Jackson đọc được số; `"abc"` không parse thành Integer thường gây lỗi deserialization trước validation.

Không cần tạo một `ConstraintValidator` riêng cho mỗi phần tử. Jakarta Validation hỗ trợ container-element validation và cascaded validation khi có provider tương thích.

**Lưu ý:** vị trí `@Valid` và `@NotNull` có ý nghĩa. `List<@Valid LineItem>` không tự khẳng định mọi element khác null; nếu muốn cấm phần tử `null`, thêm `@NotNull` vào element type phù hợp. Tương tự, `Map<String, @Valid NotificationPreference>` không tự cấm value null nếu bạn không có constraint thích hợp trên value.

### 6.6. SpringFieldPath.java — parser có giới hạn rõ ràng

Code dưới đây thực thi phép chuyển cho những path dùng trong demo:

- Property name: chữ ASCII, chữ số sau ký tự đầu và dấu gạch dưới.
- Segment chỉ số/key đặt trong ngoặc vuông, ví dụ `[0]`, `[alerts]`, `[weekly.news]` hoặc `[team/a~b]`.
- Không xử lý cú pháp property path tùy ý có quoting, bracket nesting, escape phức tạp hoặc các key chứa `]`.
- Từ chối path rỗng, quá dài, không đúng cú pháp; trả `Optional.empty()` thay vì dựng ra pointer sai.
- Chuyển mỗi token sang RFC 6901 đúng quy tắc escape `~` và `/`.

**Đây là một adapter minh họa có grammar giới hạn, không phải parser tổng quát cho mọi Spring property path.** Trong hệ thống hỗ trợ arbitrary Map keys, nên đi từ dữ liệu đường dẫn có cấu trúc (ví dụ các `Path.Node` của Jakarta Validation) hoặc dùng một thư viện/parser đã được chứng minh, kiểm thử với escaping của Spring, Jackson naming strategy và keys thật. Không dùng heuristic đơn giản này làm bảo đảm phổ quát.

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public final class SpringFieldPath {

    private SpringFieldPath() {
    }

    public static Optional<String> toJsonPointer(String field) {
        if (field == null || field.isEmpty()
                || field.length() > 512) {
            return Optional.empty();
        }

        List<String> tokens = new ArrayList<>();
        int i = 0;

        while (i < field.length()) {
            char current = field.charAt(i);
            if (current == '.' || current == ']') {
                return Optional.empty();
            }

            if (current == '[') {
                // Không chấp nhận index/key ở root đối với DTO demo.
                if (tokens.isEmpty()) {
                    return Optional.empty();
                }

                int end = field.indexOf(']', i + 1);
                if (end < 0) {
                    return Optional.empty();
                }

                String key = field.substring(i + 1, end);
                // Chỉ hỗ trợ key nằm trong grammar minh họa.
                if (!key.matches("[A-Za-z0-9._~/:-]+")) {
                    return Optional.empty();
                }

                tokens.add(key);
                i = end + 1;
            } else {
                int start = i;

                while (i < field.length()
                        && field.charAt(i) != '.'
                        && field.charAt(i) != '['
                        && field.charAt(i) != ']') {
                    i++;
                }

                String name = field.substring(start, i);
                if (!name.matches("[A-Za-z_][A-Za-z0-9_]*")) {
                    return Optional.empty();
                }

                tokens.add(name);
            }

            if (i == field.length()) {
                break;
            }

            if (field.charAt(i) == '.') {
                i++;
                // Không cho phép dấu chấm ở cuối hoặc trước '['.
                if (i == field.length()
                        || field.charAt(i) == '.'
                        || field.charAt(i) == '[') {
                    return Optional.empty();
                }
            } else if (field.charAt(i) != '[') {
                return Optional.empty();
            }
        }

        if (tokens.isEmpty()) {
            return Optional.empty();
        }

        return Optional.of(tokens.stream()
                .map(SpringFieldPath::escapeToken)
                .collect(Collectors.joining("/", "/", "")));
    }

    private static String escapeToken(String token) {
        return token.replace("~", "~0").replace("/", "~1");
    }
}
```

Đây là class Java 17 **độc lập trong project**. Những quyết định đáng chú ý:

1. Không split bởi dấu chấm khi đang ở bracket segment.
2. Kiểm tra bracket có đóng `]` và nội dung key nằm trong tập ký tự hỗ trợ.
3. Không chuyển một Spring path không hiểu thành địa chỉ JSON bất kỳ.
4. Áp escape **trên mỗi token**, không trên toàn chuỗi pointer sau khi đã nối. Nếu escape toàn bộ dấu `/` sau khi nối, bạn sẽ biến cả dấu phân cách thành `~1` và tạo kết quả sai.
5. `String#replace("~","~0")` chạy trước `replace("/","~1")` để không phá hỏng slash escape.
6. Parser giới hạn 512 UTF-16 code units cho field path; production cần thêm kiểm soát số token, độ sâu và độ dài từng key tùy rủi ro.

### 6.7. BasketController.java

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BasketController {

    @PostMapping("/baskets")
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateBasketRequest request) {

        // Chỉ chạy khi JSON đọc được và validation thành công.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "created",
                        "lines", request.lineItems().size()
                ));
    }
}
```

Controller cố ý **không có direct constraint** như `@NotNull` trên method parameter và không khai báo `BindingResult` liền sau DTO. Nhờ vậy, lỗi nested DTO trong ví dụ điển hình được Spring MVC đưa vào `MethodArgumentNotValidException` và handler bên dưới có thể truy cập toàn bộ `BindingResult` của request object.

Spring MVC 6.1+ có built-in method validation khi constraint đặt trực tiếp lên method parameters hoặc return value. Với chữ ký như `@Min(1) @RequestParam int page`, bạn có thể cần xử lý `HandlerMethodValidationException`; không gộp nó với lỗi individual DTO của ví dụ.

### 6.8. ApiErrorAdvice.java

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record FieldIssue(
            String pointer,
            String code,
            String message
    ) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = new ArrayList<>();

        for (FieldError error :
                ex.getBindingResult().getFieldErrors()) {

            String pointer = SpringFieldPath
                    .toJsonPointer(error.getField())
                    .orElse(""); // Root fallback nếu path không được hỗ trợ.

            String code = stableCode(error);
            issues.add(new FieldIssue(
                    pointer, code, safeMessage(code)
            ));
        }

        for (ObjectError error :
                ex.getBindingResult().getGlobalErrors()) {

            // Lỗi cấp object: không gán bừa một field cụ thể.
            issues.add(new FieldIssue(
                    "",
                    "INVALID_OBJECT",
                    "Request object violates a rule"
            ));
        }

        issues.sort(Comparator
                .comparing(FieldIssue::pointer)
                .thenComparing(FieldIssue::code)
                .thenComparing(FieldIssue::message));

        Map<String, Object> body = Map.of(
                "code", "VALIDATION_FAILED",
                "errors", issues
        );

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "code", "UNREADABLE_BODY",
                "message", "JSON body cannot be read"
        );

        return new ResponseEntity<>(body, headers, status);
    }

    private static String stableCode(FieldError error) {
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }

        String[] codes = error.getCodes();
        List<String> candidates = codes == null
                ? List.of()
                : Arrays.asList(codes);

        if (candidates.contains("NotBlank")) {
            return "REQUIRED_TEXT";
        }
        if (candidates.contains("NotNull")) {
            return "REQUIRED_VALUE";
        }
        if (candidates.contains("NotEmpty")) {
            return "REQUIRED_COLLECTION";
        }
        if (candidates.contains("Min")) {
            return "MIN_VALUE";
        }
        return "INVALID_FIELD";
    }

    private static String safeMessage(String code) {
        return switch (code) {
            case "REQUIRED_TEXT" -> "A text value is required";
            case "REQUIRED_VALUE" -> "A value is required";
            case "REQUIRED_COLLECTION" ->
                    "At least one element is required";
            case "MIN_VALUE" -> "Value must meet the minimum";
            case "INVALID_TYPE" -> "Value has an invalid type";
            default -> "Field value is invalid";
        };
    }
}
```

**Điểm quan trọng trong error handler:**

- `handleMethodArgumentNotValid(...)` thuộc `ResponseEntityExceptionHandler` của **Spring MVC**, không phải WebFlux.
- Handler chỉ trả ba trường public cho từng field error: `pointer`, `code`, `message`. Không serialize nguyên `FieldError`.
- `stableCode(...)` lấy metadata constraint/binding và chuyển về vocabulary do API sở hữu. Nó **không trả nguyên mã Spring** như `NotBlank.createBasketRequest.lineItems[0].sku` ra client.
- `safeMessage(...)` là thông điệp an toàn cố định để demo độc lập; production có thể dùng `MessageSource` và `Locale` để dịch, **nhưng không dịch code**.
- Lỗi global dùng `pointer=""` để chỉ root theo hợp đồng.
- Nếu parser không hỗ trợ một path, dùng root fallback thay vì trả một pointer đoán sai. Production có thể thêm `locationKnown=false` để phân biệt rõ “lỗi thực sự ở root” và “không đủ dữ liệu ánh xạ”; ví dụ tối giản chưa thêm trường đó.
- Danh sách được sắp theo `pointer` rồi `code` để test không phụ thuộc thứ tự duyệt của Jakarta Validation.
- Khi JSON sai cú pháp hoặc không deserialize được, Spring MVC thường ném `HttpMessageNotReadableException` trước khi có DTO. Handler riêng trả `UNREADABLE_BODY`, không tự suy ra field pointer từ chuỗi JSON chưa parse.
- `HttpStatusCode status` và `HttpHeaders headers` do Spring truyền vào; code giữ nguyên status mặc định (thường 400 trong hai nhánh).

**Giới hạn bảo mật:** thông báo default an toàn do ứng dụng xác định; code không xuất `FieldError#getRejectedValue()`, `Throwable#getMessage()` hoặc giá trị Map key chưa được cho phép. Tuy nhiên `pointer` vẫn chứa **key của Map**, nên production phải cân nhắc việc key có phải email, token, account ID hoặc dữ liệu riêng tư hay không.

### 6.9. SpringFieldPathTest.java — unit test cho path parser

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringFieldPathTest {

    private void check(String input, String expected) {
        assertEquals(expected,
                SpringFieldPath.toJsonPointer(input).orElseThrow());
    }

    @Test
    void nestedArrayIndex() {
        check("lineItems[0].sku", "/lineItems/0/sku");
        check("lineItems[12].quantity",
                "/lineItems/12/quantity");
        check("lineItems", "/lineItems");
    }

    @Test
    void mapKeyContainingDotIsOneToken() {
        check("preferences[weekly.news].enabled",
                "/preferences/weekly.news/enabled");
    }

    @Test
    void slashAndTildeAreEscapedByRfc6901() {
        check("preferences[team/a~b].enabled",
                "/preferences/team~1a~0b/enabled");
    }

    @Test
    void deepBeanProperty() {
        check("shipping.address.postcode",
                "/shipping/address/postcode");
    }

    @Test
    void invalidOrUnsupportedPathsAreNotGuessed() {
        assertTrue(SpringFieldPath.toJsonPointer("").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "preferences[complex]key].enabled").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "lineItems..sku").isEmpty());
        assertTrue(SpringFieldPath.toJsonPointer(
                "lineItems[0].").isEmpty());
    }
}
```

Những test này **chỉ chứng minh parser của API adapter**. Chúng chưa chứng minh Spring/Hibernate Validator thật đã tạo ra các path cụ thể như thế nào. Vì vậy cần thêm integration tests qua MVC.

### 6.10. BasketControllerTest.java — integration test qua MockMvc

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasketControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void nestedListAndMapErrorsExposePointers() throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"","quantity":0}
                              ],
                              "preferences":{
                                "alerts":{"enabled":null}
                              }
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors.length()").value(3))
                .andExpect(jsonPath("$.errors[*].pointer",
                        hasItems(
                            "/lineItems/0/sku",
                            "/lineItems/0/quantity",
                            "/preferences/alerts/enabled"
                        )))
                .andExpect(jsonPath("$.errors[*].code",
                        hasItems(
                            "REQUIRED_TEXT",
                            "MIN_VALUE",
                            "REQUIRED_VALUE"
                        )));
    }

    @Test
    void errorOnSecondArrayElementUsesIndexOne()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"A-1","quantity":1},
                                {"sku":"","quantity":2}
                              ],
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/lineItems/1/sku"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("REQUIRED_TEXT"));
    }

    @Test
    void mapKeyContainingDotRemainsOneToken()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"OK","quantity":1}
                              ],
                              "preferences":{
                                "weekly.news":{"enabled":null}
                              }
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/preferences/weekly.news/enabled"));
    }

    @Test
    void emptyCollectionErrorTargetsCollection()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[],
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].pointer")
                        .value("/lineItems"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("REQUIRED_COLLECTION"));
    }

    @Test
    void malformedJsonUsesDifferentErrorCode()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"lineItems\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void incompatibleJsonShapeIsNotBeanValidation()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":"not-an-array",
                              "preferences":{}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void successfulRequestReachesController()
            throws Exception {
        mvc.perform(post("/baskets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "lineItems":[
                                {"sku":"A-1","quantity":3}
                              ],
                              "preferences":{
                                "alerts":{"enabled":true}
                              }
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.lines").value(1));
    }
}
```

**Mục tiêu của 7 integration tests**:

- Spring thật bind JSON vào record DTO, Jakarta Validation cascade vào cả `List` và `Map`.
- Nested errors được chuyển thành JSON Pointer đúng các vị trí.
- Array index thứ hai là `1`, không phải `2`.
- Map key có dấu chấm không bị split nhầm thành hai thuộc tính.
- Lỗi `@NotEmpty` ở collection root dùng `/lineItems`.
- JSON sai cú pháp hoặc shape không tương thích có mã `UNREADABLE_BODY` riêng.
- Payload hợp lệ gọi controller và nhận HTTP 201.

**Lưu ý kiểm chứng:** các assertion trong test dựa trên quy ước property path của Spring/Jakarta Validation trong cấu hình demo. Nếu nâng phiên bản provider, thay `Map` key type hoặc cấu hình custom validator, nên kiểm tra field path thực tế. Không coi parser giới hạn này là hỗ trợ mọi dạng key.

### 6.11. Chạy project

Từ thư mục `nested-errors-demo` trên máy có JDK 17+ và Maven:

```bash
mvn -q clean test
```

Bộ test gồm **5 unit tests** cho parser và **7 integration tests** cho Web MVC, tổng cộng **12 test**. Kỳ vọng các assertion đi qua và Maven trả exit code 0 trong cấu hình đã mô tả. Không đưa stdout Maven như một sự kiện đã đo vì kết quả thực tế còn phụ thuộc dependency resolution và phiên bản môi trường.

Khởi chạy server:

```bash
mvn spring-boot:run
```

Gửi body chứa lỗi:

```bash
curl -i -X POST 'http://localhost:8080/baskets' \
  -H 'Content-Type: application/json' \
  --data '{
    "lineItems":[{"sku":"","quantity":0}],
    "preferences":{"alerts":{"enabled":null}}
  }'
```

Một response theo contract demo (thứ tự trường trong mỗi JSON object không bắt buộc cố định):

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/quantity",
      "code": "MIN_VALUE",
      "message": "Value must meet the minimum"
    },
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    },
    {
      "pointer": "/preferences/alerts/enabled",
      "code": "REQUIRED_VALUE",
      "message": "A value is required"
    }
  ]
}
```

Response list được sắp xếp theo pointer và code, nhưng **thứ tự JSON object keys** không phải hợp đồng. Các mã `MIN_VALUE`, `REQUIRED_TEXT` và `REQUIRED_VALUE` là **mã do demo quy định**, không phải constant của Spring Framework.

## 7. Những điều cần biết khi chuyển từ Spring property path sang JSON Pointer

### 7.1. Đường dẫn Java không nhất thiết là đường dẫn JSON

Giả sử DTO:

```java
public record CreateOrderRequest(
        @JsonProperty("items")
        List<@Valid LineItem> lineItems) {
}
```

Đây là fragment cần import `com.fasterxml.jackson.annotation.JsonProperty` và có class `LineItem` phù hợp. Jackson nhận property JSON tên `items`, nhưng Spring validation có thể báo field path `lineItems[0].sku` theo **tên Java property**. Nếu chỉ chuyển hình thức dấu chấm/ngoặc, bạn sẽ tạo pointer `/lineItems/0/sku`, **không trỏ đúng document JSON**. Hợp đồng public cần `/items/0/sku`.

Giải pháp:

- Với DTO đơn giản, giữ JSON property names và JavaBean names thống nhất.
- Nếu có `@JsonProperty`, `PropertyNamingStrategies.SNAKE_CASE`, `@JsonAlias`, `@JsonUnwrapped`, polymorphism hoặc custom deserializer, cần **schema-aware mapping** từ Java path segment sang tên JSON thực.
- Có thể dùng Jackson introspection trên DTO có kiểu và bối cảnh hiện tại để dịch tên property; đừng thay chuỗi toàn cục kiểu `replace("lineItems","items")` trên path có key Map trùng chữ.
- Những path không thể dịch chắc chắn nên trả root-level error hoặc metadata khác với thông báo an toàn.

Điểm này là **vấn đề thiết kế contract**, không phải lỗi RFC 6901.

### 7.2. Tên property trong Map là dữ liệu, không phải tên field Java

Với:

```json
{
  "preferences": {
    "weekly.news": {
      "enabled": null
    }
  }
}
```

Key `weekly.news` là một **string trong JSON object**. Parser phải giữ nguyên token này khi dựng pointer. Nếu key chứa dấu cách, dấu ngoặc vuông hoặc backslash, ví dụ parser ở trên **chủ động từ chối** vì không có đủ quy tắc đảm bảo round-trip. Một ứng dụng cho phép key tùy ý cần parser và test tương ứng; không sửa bằng cách bỏ các ký tự “khó”.

Với `Map<Long, Value>` hoặc `Map<UUID, Value>`, Jackson còn có thể chuyển tên key JSON thành kiểu Java khác. Nếu chuyển ngược từ `FieldError.getField()` sang pointer, bạn phải hiểu cách key được biểu diễn và có thể không khôi phục nguyên văn key JSON. Trong trường hợp này, việc giữ metadata từ decoder hoặc schema-aware mapping có thể cần thiết hơn string parser.

### 7.3. JSON Pointer array index được hiểu theo loại dữ liệu hiện tại

Một pointer `/lineItems/0/sku` có token `"0"`. RFC 6901 định nghĩa cách giải quyết token này dựa trên **giá trị hiện tại là JSON array hay object**:

- Nếu current node là array: token `0` là **phần tử đầu tiên**.
- Nếu current node là object: token `"0"` có thể là **key tên "0"**.

Do đó, chỉ từ chuỗi pointer không thể kết luận token `0` là array index nếu chưa biết cấu trúc document. Nếu client muốn phân biệt ngay ở cấp schema, có thể dùng typed segments thay vì pointer string.

### 7.4. List index không phải định danh nghiệp vụ bền vững

Nếu user xóa phần tử đầu rồi submit lại, `lineItems[2]` hôm nay không chắc là cùng sản phẩm như lần request trước. Không dùng index làm ID vĩnh viễn trong database, audit hoặc job retry.

Một API có thể trả thêm `itemId` hoặc `clientRowId` do client cung cấp, nhưng:

- Không lấy giá trị này từ `FieldError#getRejectedValue()` một cách vô điều kiện.
- Không tin `itemId` là bằng chứng authorization.
- Nếu cần mapping ID → vị trí, xác minh ID tồn tại trong request/schema và thuộc quyền caller.
- Với duplicate IDs, một ID có thể không xác định duy nhất dòng nào; vẫn cần vị trí hoặc lỗi cấp collection.

Thông thường `pointer` chỉ mô tả **vị trí trong request hiện tại**, còn ID đại diện **định danh nghiệp vụ** là hai khái niệm riêng.

## 8. Những loại lỗi không có field pointer cụ thể

### 8.1. Collection-level constraint

Ví dụ `@NotEmpty` trên `lineItems` tạo lỗi ở **toàn danh sách**, không phải `lineItems[0]`. Pointer nên là `/lineItems`.

Với `@Size(max=20)` trên list, cũng nên báo ở collection-level, vì điều kiện số lượng phần tử không gắn với riêng một item.

### 8.2. Object-level hoặc cross-field constraint

Một class-level constraint có thể yêu cầu `startDate` trước `endDate` hoặc không cho kết hợp hai loại cấu hình. Nếu validator phát ra `ObjectError`, không nên bịa field path. Root pointer `""` có thể là hợp đồng phù hợp.

Nếu validator chủ động thêm property node cho một field cụ thể, ví dụ `endDate`, adapter có thể map thành `/endDate`. Cách nào đúng phụ thuộc vào **ý nghĩa constraint**, không chỉ tên annotation.

### 8.3. Element-level constraint trên List

Ví dụ:

```java
public record Request(
        List<@NotBlank String> tags) {
}
```

Đây là fragment. Nếu phần tử thứ hai của tags là chuỗi rỗng, lỗi có thể được biểu diễn bằng path chứa vị trí phần tử, như `tags[1]`. Không cố chèn thêm một field giả kiểu `value` vì phần tử chính là string bị lỗi.

### 8.4. Map key constraint, không phải Map value constraint

Ví dụ:

```java
public record Request(
        Map<@NotBlank String, @Valid NotificationPreference> preferences) {
}
```

Đây là fragment. `@NotBlank` trên **key của Map** có thể tạo path kiểu container-element key, phụ thuộc provider và cách Spring chuyển `ConstraintViolation.getPropertyPath()` thành field. Về ngữ nghĩa, lỗi nằm ở **tên key**, không phải một property có tên `enabled` trong value.

Nếu API cho phép dynamic keys và yêu cầu báo “tên khóa không hợp lệ”, hãy cân nhắc một error code như `INVALID_MAP_KEY` với `pointer` trỏ đến entry/parent và metadata phù hợp. Đừng tự thêm `/key` vào JSON Pointer như thể object có field con `key` nếu tài liệu JSON không chứa field đó.

### 8.5. JSON body không đọc được

Với `@RequestBody`:

```text
{"lineItems":,}
```

Spring MVC không tạo được DTO. `HttpMessageNotReadableException` không đi qua cùng nhánh `BindingResult#getFieldErrors()`. Bạn có thể có thông tin location của parser Jackson, nhưng không nên tự tuyên bố có field pointer đáng tin nếu không thể xác định chính xác node trong document lỗi.

Demo trả `UNREADABLE_BODY` thay vì phát một pointer sai.

### 8.6. Method validation trong Spring MVC 6.1+

Một method:

```java
@GetMapping("/baskets")
public List<BasketSummary> list(
        @RequestParam @Min(1) int page) {
    // ...
}
```

Đây là fragment; cần controller imports, `BasketSummary` và implementation. Direct constraint `@Min(1)` trên tham số có thể kích hoạt **`HandlerMethodValidationException`**, không phải individual DTO `MethodArgumentNotValidException`. Metadata được nhóm theo `ParameterValidationResult`.

Nếu muốn lỗi query parameter có vị trí, định nghĩa nguồn lỗi rõ:

```json
{
  "source": "query",
  "parameter": "page",
  "code": "MIN_VALUE"
}
```

Không gán mặc định `pointer="/page"` rồi khẳng định trỏ vào JSON body khi request là GET và không có body JSON. Nhiều API nên dùng một đối tượng `source` có `pointer` **chỉ khi source là body**, còn query/header/path parameters có các trường riêng.

## 9. Đọc metadata cấu trúc khi không còn đủ thông tin từ FieldError

Trong Jakarta Bean Validation, `ConstraintViolation#getPropertyPath()` cung cấp một `jakarta.validation.Path` chứa nhiều `Path.Node`. Những node này có thể mang:

- Tên property.
- Loại node (property, bean, container element, parameter...).
- `isInIterable()` để biết node nằm trong iterable.
- `getIndex()` khi đường dẫn thuộc List/array.
- `getKey()` khi liên quan Map.

Ví dụ fragment (cần có biến `ConstraintViolation<?> violation`):

```java
for (jakarta.validation.Path.Node node :
        violation.getPropertyPath()) {

    String property = node.getName();
    boolean iterable = node.isInIterable();
    Integer index = node.getIndex();
    Object key = node.getKey();

    // Chọn cách chuyển chỉ sau khi biết node kind,
    // mapping tên JSON và kiểu container.
}
```

Điểm mạnh của structured path là biết **key hoặc index** với nhiều thông tin hơn một chuỗi đã được định dạng. Nhưng adapter sang JSON Pointer vẫn phải hiểu **tên JSON thực tế**, kiểu key, null/missing field, container element và naming strategy.

**Ranh giới quan trọng:** khi bạn chỉ nhận `FieldError` từ `BindingResult`, không phải lúc nào bạn còn giữ được chính đối tượng `ConstraintViolation` nguyên bản cùng toàn bộ structured nodes. Đừng viết code ép `FieldError` sang `ConstraintViolation`; chúng là hai API khác nhau. Nếu nhu cầu chuyển Map keys tùy ý rất phức tạp, hãy thiết kế integration riêng với validation engine hoặc truyền metadata path có cấu trúc ngay từ điểm tạo lỗi.

Spring `SpringValidatorAdapter` thường dùng stringified property path của Jakarta violation để xác định field cho Spring Errors; điều này tiện cho HTML form binding nhưng có thể **mất thông tin để reverse-map một cách tuyệt đối sang JSON**.

## 10. Bảo mật khi công bố đường dẫn có Map key động

### 10.1. Key có thể chính là dữ liệu nhạy cảm

Một Map có thể có key là địa chỉ email, token, device ID, account ID, số điện thoại, mã khôi phục hoặc định danh nội bộ. Nếu trả:

```json
{
  "pointer": "/tokens/private-secret-abc/active",
  "code": "REQUIRED_VALUE"
}
```

thì key đã được công bố trong error response. Kể cả khi user là người gửi request, việc phản chiếu thông tin này vào logs, analytics hoặc màn hình dùng chung vẫn có rủi ro.

Các biện pháp:

- Xác định field/key nào được phép phản chiếu vào error response.
- Với key nhạy cảm, có thể trả parent pointer và code riêng thay vì path chứa key.
- Giới hạn độ dài pointer, độ sâu path, số errors tối đa trong response.
- Không serialize rejected values từ `FieldError#getRejectedValue()`.
- Không trả raw exception, SQL messages hoặc stack trace.
- Tránh log toàn bộ payload hoặc JSON Pointer khi chúng chứa bí mật.

### 10.2. Không cho phép path injection do ghép chuỗi thiếu escape

Sai:

```java
String pointer = "/preferences/" + userKey + "/enabled";
```

Nếu `userKey="team/a"`, pointer thành `/preferences/team/a/enabled`, tương đương **hai segments** `team` và `a`. Đúng là escape từng token:

```java
String escapedKey = userKey
        .replace("~", "~0")
        .replace("/", "~1");

String pointer = "/preferences/" + escapedKey + "/enabled";
```

Đây là fragment; dữ liệu `userKey` phải được kiểm soát về null/length/schema và không chứa bí mật cần che giấu. Mục tiêu là bảo toàn ngữ nghĩa của một **Map key duy nhất**, không phải một cơ chế kiểm tra quyền hay lọc dữ liệu độc hại.

### 10.3. Pointer không phải authorization boundary

JSON Pointer chỉ chỉ ra vị trí một trường. Client biết `/users/123/role` không đồng nghĩa được phép sửa role. Tầng service phải kiểm tra quyền với resource và operation, không dựa trên việc tên field đã được validation thành công.

Đối với `@ModelAttribute` property binding, cân nhắc `setAllowedFields(...)` hoặc DTO chuyên dụng để chống mass assignment; đối với `@RequestBody` JSON, Jackson deserialize theo schema/DTO và không chịu `allowedFields` theo cách property binding form-urlencoded. Validator chỉ xác nhận constraint, không tự đảm bảo authorization.

## 11. Ánh xạ lỗi cho frontend: UX và vòng đời một request

### 11.1. Hiển thị lỗi theo pointer

Một frontend có thể có state tương ứng:

```json
{
  "lineItems": [
    {"sku": "A", "quantity": 1},
    {"sku": "", "quantity": 0}
  ]
}
```

Nếu nhận lỗi:

```json
{
  "pointer": "/lineItems/1/sku",
  "code": "REQUIRED_TEXT",
  "message": "A text value is required"
}
```

UI có thể đánh dấu field `sku` của dòng thứ hai. Để xử lý một pointer, client cần **thư viện JSON Pointer chuẩn hoặc một parser có test riêng**, thay vì dùng `split("/")` rồi quên giải mã `~0`/`~1`. Ngoài ra, một số path có thể không resolve trên payload gốc vì đó là field **bắt buộc nhưng bị thiếu**.

### 11.2. Không lưu lỗi cũ theo index sau khi danh sách thay đổi

Nếu người dùng xóa dòng đầu tiên sau khi server trả lỗi, `/lineItems/1/sku` có thể giờ trỏ đến dòng khác. Các cách thường dùng:

- Gắn lỗi với snapshot request đã submit và xóa/đồng bộ lại khi form state đổi.
- Dùng ID ổn định của hàng tại frontend (khác index) để ánh xạ lỗi tạm thời.
- Khi submit lại, server sẽ trả pointer theo danh sách mới.
- Không đưa các pointer của lần submit cũ vào state của lần submit mới một cách mù quáng.

### 11.3. Mã lỗi và thông báo có vai trò khác nhau

Client có thể chọn một icon theo `REQUIRED_TEXT`, chọn hành vi focus theo pointer, và hiển thị `message` đã dịch. Không dùng text như `"A text value is required"` làm nhánh logic, vì khi đổi locale thì text thay đổi. Mã lỗi nên được backend công bố, version và test hợp đồng.

### 11.4. Một field có nhiều lỗi

Ví dụ cùng field `quantity` có thể vi phạm nhiều constraints nếu annotation/nhóm validation chồng nhau. API nên trả **danh sách errors**, không gộp vào Map pointer → một message duy nhất rồi làm mất những lỗi còn lại. Nếu UI chỉ hiển thị một message, đó là quyết định presentation priority của frontend hoặc backend, cần tài liệu hóa.

Demo giữ từng `FieldError` và sắp thứ tự ổn định; không tự xóa các lỗi trùng pointer.

## 12. Các lỗi thường gặp và cách khắc phục

### 12.1. Dùng replace dấu ngoặc và dấu chấm không có parser

Mẫu không an toàn:

```java
String pointer = "/" + springPath
        .replace("[", "/")
        .replace("]", "")
        .replace(".", "/");
```

Với `preferences[weekly.news].enabled`, kết quả sai vì key `weekly.news` bị tách thành hai path tokens. Hãy token hóa theo đúng grammar hoặc chuyển từ structured metadata.

### 12.2. Không escape dấu slash và tilde của Map key

`team/a~b` phải thành `team~1a~0b`. Nếu không, một API client giải mã pointer sẽ đi tới node khác hoặc báo not found. Escape trên từng token, không escape dấu `/` phân cách.

### 12.3. Dùng pointer "/" cho root

Root là `""`. Dấu `"/"` trỏ đến member có key rỗng. Nếu API không biết vị trí lỗi, định nghĩa fallback rõ thay vì dùng slash tùy ý.

### 12.4. Tưởng field path luôn bằng JSON field name

`@JsonProperty("items")` trên property `lineItems` làm thay đổi JSON name. Một simple Java path parser không biết điều đó. Cần translation theo DTO schema hoặc bỏ công bố pointer không chính xác.

### 12.5. Coi Map key có dấu chấm là nested bean property

Trong `preferences[weekly.news].enabled`, dấu chấm trong bracket thuộc **một key**. Nếu frontend lấy sai, có thể hiển thị lỗi ở field không tồn tại.

### 12.6. Gán collection-level error cho item đầu tiên

`@NotEmpty List<?> lineItems` vi phạm khi danh sách trống; lúc đó không có item đầu tiên để gắn lỗi. Pointer nên trỏ `/lineItems`, không tạo `/lineItems/0` giả.

### 12.7. Trả lỗi JSON decoding như FieldError

Nếu JSON sai cú pháp hoặc field có kiểu không đọc được, Spring MVC thường dừng trong HTTP message converter và tạo `HttpMessageNotReadableException`. Không có `BindingResult` giống như một DTO đã được validate. Xử lý riêng với mã đọc body.

### 12.8. Test chỉ một phần tử

Nếu test chỉ `lineItems[0]` thì dễ bỏ sót bug index off-by-one. Có test `lineItems[1]`, `lineItems[12]` khi phù hợp, và việc xóa/chèn/sắp xếp lại danh sách.

### 12.9. Không hỗ trợ arbitrary Map key nhưng vẫn tuyên bố đã hỗ trợ

Key có thể chứa `]`, dấu nháy, dấu cách, Unicode, escape sequence, số hoặc cấu trúc khác. Parser demo chỉ chấp nhận một subset; khi gặp key ngoài subset, nó trả `Optional.empty()`. Production phải mở rộng bằng dữ liệu có cấu trúc, test round-trip và giới hạn an toàn — không âm thầm bỏ ký tự khiến key bị đổi.

### 12.10. Trả internal Spring field path như định danh API lâu dài

Một refactor model name, Java property hoặc Bean Validation adapter có thể làm path nội bộ khác đi. Nếu response contract đã công bố `pointer` theo JSON schema, hãy bảo vệ nó bằng integration tests và chủ động migration khi JSON contract thực sự đổi.

### 12.11. Nhầm lỗi field với query/header errors

Nếu lỗi xảy ra ở `@RequestParam int page`, source là query, không phải JSON body. Không dựng `pointer="/page"` như thể một field body luôn tồn tại. Trả `source="query"`, `parameter="page"` hoặc schema lỗi tương ứng.

### 12.12. Không kiểm soát số lượng lỗi

Một danh sách lớn có thể tạo nhiều nghìn `FieldError`. Việc serialize tất cả cùng pointer dài có thể tăng kích thước response và leak key data. Đặt giới hạn errors, max request size, độ sâu nesting, hợp đồng truncation và logging phù hợp với application.

## 13. Kiểm thử hợp đồng API một cách có hệ thống

| Tình huống | Ví dụ | Điều phải kiểm chứng |
| --- | --- | --- |
| Nested object | `shipping.address.postcode` | `/shipping/address/postcode` |
| Phần tử đầu tiên | `lineItems[0].sku` | `/lineItems/0/sku` |
| Phần tử thứ hai | `lineItems[1].quantity` | `/lineItems/1/quantity` |
| Index hai chữ số | `lineItems[12].sku` | `/lineItems/12/sku` |
| Map key đơn giản | `preferences[alerts].enabled` | `/preferences/alerts/enabled` |
| Map key có dấu chấm | `preferences[weekly.news].enabled` | Không tách key làm hai |
| Map key có slash và tilde | `preferences[team/a~b].enabled` | `/preferences/team~1a~0b/enabled` |
| Map key không thuộc grammar | Ví dụ chứa `]` | Root fallback hoặc error cấu trúc riêng; không đoán |
| List rỗng | `@NotEmpty lineItems` | Lỗi ở `/lineItems` |
| Missing nested property | `{"alerts":{}}` | Nêu rõ pointer có thể là logical target |
| Class-level constraint | Lỗi liên trường | Root error hoặc field node tường minh |
| JSON không đọc được | Syntax/type mismatch | `UNREADABLE_BODY`, không giả pointer |
| JSON name khác Java name | `@JsonProperty("items")` | API pointer theo JSON name, không phải Java name |
| Query parameter lỗi | `page=0` với `@Min(1)` | Không gán nhầm source body |
| Cùng pointer nhiều constraints | Nhiều `FieldError` | Không làm mất lỗi |
| Map key nhạy cảm | Key chứa email/token | Không tiết lộ thông tin khi không được phép |

Một test contract tốt phải kiểm tra **cả đường dẫn lẫn mã lỗi và HTTP status**, không chỉ xem số lượng errors. Nếu API hỗ trợ nhiều version của DTO hoặc tên field có alias, chạy cùng test case trên từng version.

## 14. Hướng phát triển production-grade

Parser minh họa trong project cố tình giới hạn grammar cho một bài học runnable. Một hệ thống lớn có thể cần thêm:

1. **Schema-aware JSON property translation** theo cấu hình Jackson thực tế, tránh Java field name bị lộ ra API.
2. **Structured path adapter** từ Jakarta `Path.Node` khi giữ được metadata, để phân biệt property, iterable index và Map key.
3. **Explicit location model**: `source=body/query/header/path` kèm pointer hoặc parameter tương ứng.
4. **Consistent error envelope**: mã request-level, list lỗi field/global, trace ID, locale và optional Problem Details.
5. **Stable business codes** độc lập chỉ số collection và tên key.
6. **Security redaction** cho key nhạy cảm và rejected values.
7. **Bounded response**: số lỗi, độ dài pointer, số segment và nested depth.
8. **Contract tests** sau khi nâng cấp Spring, Hibernate Validator, Jackson hoặc thay naming strategy.
9. **Frontend pointer decoder** tuân thủ RFC 6901, có test cho `~0`, `~1`, Map keys, empty token và missing property.
10. **Error schema versioning** để đổi quy tắc pointer hoặc field names mà không làm vỡ client cũ.

### ProblemDetail và trường pointer

Spring hỗ trợ `ProblemDetail`/RFC 9457. Một error response có thể có:

```json
{
  "type": "https://api.example.org/problems/validation-failed",
  "title": "Request validation failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/lineItems/0/sku",
      "code": "REQUIRED_TEXT",
      "message": "A text value is required"
    }
  ]
}
```

Đây là **schema gợi ý**, khác output chính xác của demo runnable. `errors` và `pointer` là **extension fields do ứng dụng định nghĩa**, không phải field bắt buộc của RFC 9457. Nếu dùng chuẩn Problem Details, giữ semantics của `type/title/status/detail/instance` và chỉ mở rộng trong một namespace/contract rõ ràng.

### Phân biệt pointer đến request input và pointer đến response

Với endpoint tạo resource, DTO request có thể khác domain entity và response representation. Pointer trong validation error nên được giải thích là **vị trí trong request input schema**, không phải nhất thiết trong object database hay JSON response trả về. Điều này đặc biệt quan trọng khi sử dụng mapping DTO → entity hoặc đổi tên fields giữa hai representation.

## 15. Checklist triển khai

- [ ] Định nghĩa rõ trường `pointer` là JSON Pointer string representation theo RFC 6901.
- [ ] Giữ `code` ổn định, không phụ thuộc index hoặc message đã dịch.
- [ ] Phân biệt Spring path, Jakarta structured path và JSON property names.
- [ ] Có test index 0, index 1 và index nhiều chữ số.
- [ ] Không split bằng dấu chấm khi key ở trong bracket.
- [ ] Escape `~` thành `~0` và `/` thành `~1` theo **từng token**.
- [ ] Phân biệt `""` root với `"/"` empty-key member.
- [ ] Khi field bị thiếu, tài liệu hóa pointer là logical field location hoặc chọn parent pointer.
- [ ] Không dựng pointer nếu path ngoài grammar hoặc JSON naming strategy không tương thích.
- [ ] Có quy tắc cho collection-level và object-level validation.
- [ ] Phân biệt `MethodArgumentNotValidException` với JSON decoding và method validation.
- [ ] Không trả raw rejected value hoặc Map key nhạy cảm nếu contract không cho phép.
- [ ] Giới hạn số lỗi, độ dài pointer, độ sâu path và request body size.
- [ ] Kiểm thử API bằng `MockMvc`, không chỉ bằng unit test của string parser.
- [ ] Khi DTO đổi `@JsonProperty` hoặc field naming strategy, cập nhật/tests adapter theo JSON contract.
- [ ] Nếu frontend thay đổi thứ tự list, không gắn lỗi cũ mù quáng theo index.
- [ ] Với field query/header, dùng location model khác JSON body pointer.

## 16. Kết luận

**Ánh xạ đường dẫn collection hoặc Map ra hợp đồng API** không chỉ là thay dấu `.` và cặp ngoặc vuông thành dấu `/`.

Spring `BindingResult`/`FieldError` biểu diễn vị trí lỗi theo **property path**; JSON Pointer RFC 6901 biểu diễn vị trí theo **cấu trúc tài liệu JSON**. Một phép chuyển đúng cần hiểu **array index, Map key, nested property, escape `~` và `/`, tên JSON thực sự và trường hợp thiếu field**.

Một API có thể dùng `pointer` + `code` + `message` để frontend hiển thị lỗi chính xác trong danh sách hoặc Map. Khi không chắc chắn về ngữ nghĩa đường dẫn, nên trả lỗi ở mức parent/root và làm rõ fallback, **không công bố đường dẫn sai**. Kết hợp typed validation paths, mapping theo DTO schema, giới hạn bảo mật và contract tests sẽ giúp hệ thống có thông báo lỗi dễ dùng, nhất quán và bền vững khi mở rộng.

## Tài liệu tham khảo

- [RFC 6901 — JavaScript Object Notation (JSON) Pointer](https://www.rfc-editor.org/rfc/rfc6901)
- [Spring Framework 6.2 — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — SpringValidatorAdapter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html)
- [Spring Framework — MVC @RequestBody and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Jakarta Bean Validation 3.0 — ConstraintViolation and Path](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Spring Framework — Problem Details / Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
