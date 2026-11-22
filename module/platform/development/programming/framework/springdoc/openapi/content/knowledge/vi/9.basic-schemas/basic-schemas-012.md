# Giới hạn độ dài, khoảng số, mẫu chuỗi và kích thước mảng

Schema trong OpenAPI không chỉ mô tả một giá trị là `string`, `integer` hay `array`. Schema còn có thể diễn đạt giới hạn để client biết dữ liệu hợp lệ cần có hình dạng ra sao: chuỗi phải dài bao nhiêu, số nằm trong khoảng nào, chuỗi phải khớp mẫu nào và mảng được chứa tối thiểu hoặc tối đa bao nhiêu phần tử.

Với Spring Boot, các ràng buộc thường được khai báo bằng Bean Validation như `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax` và `@Pattern`. Springdoc có thể đọc metadata này để tạo schema OpenAPI. Tuy nhiên, tài liệu sinh ra và validation runtime là hai phần cần kiểm tra riêng: một schema chỉ mô tả giới hạn không tự khiến Spring từ chối request sai dữ liệu.

## 1. Nhóm ràng buộc trong Schema Object

Các keyword thường dùng cho chủ đề này:

| Kiểu dữ liệu | Keyword OpenAPI/JSON Schema | Ý nghĩa |
|---|---|---|
| Chuỗi | `minLength` | Số ký tự tối thiểu. |
| Chuỗi | `maxLength` | Số ký tự tối đa. |
| Chuỗi | `pattern` | Biểu thức chính quy mà giá trị phải khớp. |
| Số | `minimum` | Giá trị nhỏ nhất, mặc định là bao gồm biên. |
| Số | `maximum` | Giá trị lớn nhất, mặc định là bao gồm biên. |
| Số | `exclusiveMinimum` | Cận dưới loại trừ. |
| Số | `exclusiveMaximum` | Cận trên loại trừ. |
| Mảng | `minItems` | Số phần tử tối thiểu. |
| Mảng | `maxItems` | Số phần tử tối đa. |
| Mảng | `uniqueItems` | Các phần tử phải duy nhất theo so sánh giá trị JSON. |

Những giới hạn này thường được đặt trên `Schema Object` của property hoặc item. Chúng có thể xuất hiện trong `components.schemas`, request body, response hoặc parameter schema.

Ví dụ một DTO sản phẩm có tên, giá và danh sách nhãn:

```yaml
type: object
required:
  - name
  - price
  - tags
properties:
  name:
    type: string
    minLength: 3
    maxLength: 80
    pattern: '^[A-Za-z0-9 -]+$'
  price:
    type: number
    minimum: 0.01
    maximum: 999999.99
  tags:
    type: array
    minItems: 1
    maxItems: 10
    uniqueItems: true
    items:
      type: string
      minLength: 1
      maxLength: 30
```

Schema cho biết cấu trúc dữ liệu và một số giới hạn có thể kiểm tra tự động. Các quy tắc nghiệp vụ phức tạp hơn, chẳng hạn tổng giá trị phải phù hợp với loại sản phẩm, vẫn cần được mô tả và kiểm tra ở tầng ứng dụng.

## 2. Giới hạn độ dài chuỗi

### 2.1. `minLength` và `maxLength`

`minLength` quy định số ký tự tối thiểu; `maxLength` quy định số ký tự tối đa. Ví dụ tên sản phẩm phải có từ 3 đến 80 ký tự:

```yaml
name:
  type: string
  minLength: 3
  maxLength: 80
```

Với Bean Validation, dùng `@Size` trên `String` hoặc kiểu `CharSequence`:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 3, max = 80)
        String name
) {}
```

Springdoc có thể ánh xạ giới hạn `@Size` của chuỗi thành `minLength` và `maxLength`. `@NotBlank` bổ sung yêu cầu chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng. `@Size(min = 3)` và `@NotBlank` giải quyết hai khía cạnh khác nhau: độ dài và nội dung không chỉ gồm whitespace.

`@Size` không tự loại bỏ khoảng trắng đầu/cuối. Nếu nghiệp vụ cần trim chuỗi, hãy chuẩn hóa dữ liệu hoặc dùng validation phù hợp trước khi xử lý.

### 2.2. Phân biệt `@Size`, `@NotEmpty` và `@NotBlank`

| Annotation | `null` có hợp lệ? | Chuỗi rỗng có hợp lệ? | Chuỗi chỉ có khoảng trắng có hợp lệ? |
|---|---:|---:|---:|
| `@Size(min = 1)` | Có | Không | Có |
| `@NotEmpty` | Không | Không | Có |
| `@NotBlank` | Không | Không | Không |

`@Size` chỉ kiểm tra kích thước và thường không tự yêu cầu giá trị khác `null`. Nếu field bắt buộc, kết hợp với `@NotNull`, `@NotEmpty` hoặc `@NotBlank` theo kiểu dữ liệu và quy tắc mong muốn.

Ví dụ:

```java
public record ProfileRequest(
        @NotBlank
        @Size(max = 60)
        String displayName,

        @NotEmpty
        @Size(max = 200)
        String biography
) {}
```

`displayName` phải có nội dung không phải whitespace và tối đa 60 ký tự. `biography` phải khác null, khác rỗng và không vượt quá 200 ký tự; chuỗi chỉ có khoảng trắng vẫn qua `@NotEmpty`, nên nếu không chấp nhận trường hợp đó, dùng `@NotBlank`.

### 2.3. Độ dài chuỗi Unicode

Độ dài trong schema và cách Java đếm `String.length()` có thể khác nhau với một số ký tự Unicode nằm ngoài Basic Multilingual Plane, chẳng hạn emoji được biểu diễn bằng surrogate pair trong UTF-16. JSON Schema định nghĩa độ dài chuỗi theo số ký tự Unicode; một số cơ chế kiểm tra Java dựa trên `CharSequence.length()` đếm đơn vị UTF-16.

Nếu giới hạn độ dài có ý nghĩa nghiệp vụ chặt chẽ với nội dung đa ngôn ngữ, hãy kiểm thử cả chữ có dấu, ký tự tổ hợp và emoji. Không nên giả định mọi cách đếm ký tự ở client, schema validator và Java runtime đều cho cùng kết quả với mọi chuỗi Unicode.

## 3. Mẫu chuỗi với `pattern`

`pattern` dùng biểu thức chính quy để mô tả định dạng chuỗi. Ví dụ mã đơn hàng gồm chữ in hoa, chữ số và dấu gạch ngang:

```yaml
orderCode:
  type: string
  minLength: 5
  maxLength: 24
  pattern: '^[A-Z0-9-]+$'
```

Trong Java, dùng `@Pattern`:

```java
public record CreateOrderRequest(
        @NotBlank
        @Size(min = 5, max = 24)
        @Pattern(regexp = "^[A-Z0-9-]+$")
        String orderCode
) {}
```

`@Pattern` kiểm tra chuỗi khớp biểu thức chính quy theo cơ chế regex của Java. Springdoc có thể chuyển biểu thức được khai báo sang keyword `pattern` trong schema.

### 3.1. Nên neo biểu thức bằng `^` và `$`

Trong JSON Schema, `pattern` thường được hiểu là biểu thức cần khớp ở một vị trí trong chuỗi; nó không mặc nhiên yêu cầu toàn bộ chuỗi khớp. Nếu muốn kiểm tra toàn bộ chuỗi, hãy dùng anchor `^` ở đầu và `$` ở cuối:

```regex
^[A-Z]{2}-[0-9]{6}$
```

Biểu thức này phù hợp với mã như `AB-123456`. Nếu bỏ anchor, một chuỗi dài hơn có chứa đoạn khớp vẫn có thể thỏa điều kiện pattern của JSON Schema.

### 3.2. Khác biệt giữa regex Java và regex OpenAPI

Bean Validation `@Pattern` dùng cú pháp regex của Java, còn `pattern` trong OpenAPI/JSON Schema dựa trên cú pháp regular expression theo ECMA-262. Phần lớn mẫu đơn giản như `[A-Z0-9-]+` có thể dùng chung, nhưng một số tính năng nâng cao hoặc escape có thể khác nhau.

Để tăng khả năng tương thích giữa server và client validator:

- Ưu tiên nhóm ký tự, lượng từ và anchor phổ biến.
- Tránh phụ thuộc vào lookbehind, named group hoặc tính năng riêng của một regex engine nếu không cần thiết.
- Kiểm thử cùng bộ giá trị mẫu trên Java validation và công cụ kiểm tra OpenAPI/JSON Schema mà consumer sử dụng.
- Kiểm tra escape khi đặt regex trong Java string và YAML/JSON. Ví dụ, dấu gạch chéo ngược có thể cần escape thêm trong Java string literal.

Ví dụ regex ngày tháng dạng `YYYY-MM-DD` chỉ kiểm tra hình dạng chuỗi:

```java
@Pattern(regexp = "^\\d{4}-\\d{2}-\\d{2}$")
String dateText
```

Mẫu này không bảo đảm ngày có tồn tại trong lịch. Giá trị `2026-19-45` vẫn có thể khớp hình dạng. Nếu dữ liệu là ngày, nên dùng kiểu `LocalDate` và format phù hợp thay vì chỉ dùng regex để mô phỏng toàn bộ quy tắc ngày tháng.

### 3.3. Dùng `format` hay `pattern`?

`format` mô tả một định dạng dữ liệu đã biết, ví dụ `email`, `date`, `date-time`, `uuid` hoặc `uri`. `pattern` mô tả quy tắc regex cụ thể của ứng dụng.

```yaml
email:
  type: string
  format: email

productCode:
  type: string
  pattern: '^[A-Z]{3}-[0-9]{5}$'
```

Không nên viết regex quá phức tạp để thay thế định dạng chuẩn nếu OpenAPI đã có `format` phù hợp. Ngược lại, `format: email` không nhất thiết tương đương hoàn toàn với mọi quy tắc kiểm tra email ở server; nếu nghiệp vụ có giới hạn riêng, cần thêm validation và mô tả rõ.

## 4. Khoảng số và cận bao gồm/loại trừ

### 4.1. `minimum` và `maximum`

`minimum` và `maximum` biểu diễn cận bao gồm theo mặc định. Ví dụ giá sản phẩm từ 0 đến 1.000.000:

```yaml
price:
  type: number
  minimum: 0
  maximum: 1000000
```

Với Bean Validation, dùng `@Min` và `@Max` cho các kiểu số nguyên phù hợp:

```java
public record QuantityRequest(
        @Min(1)
        @Max(500)
        Integer quantity
) {}
```

Đối với `BigDecimal` hoặc giá trị thập phân, dùng `@DecimalMin` và `@DecimalMax`:

```java
public record PriceRequest(
        @DecimalMin("0.01")
        @DecimalMax("999999.99")
        BigDecimal price
) {}
```

Hai annotation `@DecimalMin` và `@DecimalMax` mặc định bao gồm cận. Dùng `inclusive = false` nếu giá trị tại biên không được phép.

### 4.2. Cận loại trừ

Ví dụ số lượng phải lớn hơn 0 và nhỏ hơn 100:

```java
public record DiscountRequest(
        @DecimalMin(value = "0", inclusive = false)
        @DecimalMax(value = "100", inclusive = false)
        BigDecimal percentage
) {}
```

OpenAPI 3.0 và 3.1 biểu diễn cận loại trừ khác nhau:

| Ý nghĩa | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Lớn hơn 0 | `minimum: 0` và `exclusiveMinimum: true` | `exclusiveMinimum: 0` |
| Nhỏ hơn 100 | `maximum: 100` và `exclusiveMaximum: true` | `exclusiveMaximum: 100` |

Trong OpenAPI 3.0, `exclusiveMinimum` và `exclusiveMaximum` là boolean kết hợp với `minimum`/`maximum`. Trong OpenAPI 3.1, các keyword exclusive nhận chính giá trị số làm cận theo JSON Schema 2020-12. Khi đổi phiên bản OpenAPI đầu ra, hãy kiểm tra schema sinh ra thay vì giả định biểu diễn cũ vẫn đúng.

### 4.3. `@Positive`, `@PositiveOrZero`, `@Negative`

Bean Validation còn có các annotation biểu diễn dấu của số:

| Annotation | Điều kiện |
|---|---|
| `@Positive` | Lớn hơn 0. |
| `@PositiveOrZero` | Lớn hơn hoặc bằng 0. |
| `@Negative` | Nhỏ hơn 0. |
| `@NegativeOrZero` | Nhỏ hơn hoặc bằng 0. |

Ví dụ:

```java
public record InventoryAdjustment(
        @PositiveOrZero Integer remaining,
        @NegativeOrZero Integer correction
) {}
```

Springdoc có thể ánh xạ những ràng buộc số phổ biến thành cận tương ứng. Hãy xác nhận kết quả trong `/v3/api-docs`, đặc biệt khi kết hợp nhiều annotation hoặc dùng kiểu số đặc biệt.

### 4.4. `@Digits` và độ chính xác thập phân

`@Digits(integer = 6, fraction = 2)` giới hạn số chữ số ở phần nguyên và phần thập phân. Đây là quy tắc về số chữ số, không hoàn toàn giống một khoảng `minimum`/`maximum`.

```java
public record PaymentRequest(
        @Digits(integer = 6, fraction = 2)
        @DecimalMin(value = "0.01")
        BigDecimal amount
) {}
```

Khi cần mô tả độ chính xác trong OpenAPI, cân nhắc `multipleOf` nếu quy tắc thật sự tương ứng bước số, ví dụ `multipleOf: 0.01` cho bội số của một phần trăm đơn vị. Tuy nhiên, `multipleOf` không diễn đạt đầy đủ mọi giới hạn số chữ số của `@Digits`, đặc biệt với phần nguyên. Hãy giữ validation runtime và bổ sung mô tả rõ ràng nếu schema không thể thể hiện chính xác quy tắc.

## 5. Kích thước mảng

### 5.1. `minItems` và `maxItems`

Với mảng, `minItems` là số phần tử tối thiểu và `maxItems` là số phần tử tối đa:

```yaml
tags:
  type: array
  minItems: 1
  maxItems: 10
  items:
    type: string
```

Bean Validation `@Size` có thể dùng cho `Collection`, `Map` và array Java:

```java
public record ProductRequest(
        @NotEmpty
        @Size(max = 10)
        List<String> tags
) {}
```

`@NotEmpty` yêu cầu collection khác null và có ít nhất một phần tử. `@Size(max = 10)` đặt giới hạn trên. Springdoc có thể biểu diễn các giới hạn này bằng `minItems`/`maxItems`.

Nếu cần giới hạn cả số lượng tối thiểu và tối đa, có thể dùng `@Size(min = 1, max = 10)`; khi đó `@NotEmpty` thường không cần thiết để kiểm tra kích thước, nhưng vẫn cần xem xét yêu cầu `null`. `@Size` chấp nhận null, nên nếu field bắt buộc phải có, kết hợp `@NotNull` hoặc `@NotEmpty`.

### 5.2. `uniqueItems`

`uniqueItems: true` yêu cầu các phần tử mảng không trùng nhau theo phép so sánh giá trị JSON:

```yaml
permissions:
  type: array
  uniqueItems: true
  items:
    type: string
```

Ví dụ `['READ', 'WRITE']` hợp lệ, còn `['READ', 'READ']` vi phạm uniqueness.

Java `Set` không hoàn toàn tương đương với mọi trường hợp của `uniqueItems`. `Set` phụ thuộc `equals()`/`hashCode()` của kiểu Java; JSON Schema so sánh giá trị JSON theo quy tắc của schema. Nếu dùng `List`, server có thể nhận phần tử trùng lặp dù OpenAPI mô tả `uniqueItems: true`, trừ khi validation runtime cũng kiểm tra uniqueness.

Hibernate Validator có constraint `@UniqueElements` cho collection, nhưng đây là extension của Hibernate Validator chứ không phải annotation chuẩn Bean Validation. Nếu dùng, cần bảo đảm dependency và kiểm tra việc springdoc có chuyển constraint đó thành `uniqueItems` trong phiên bản dự án hay không. Khi cần chắc chắn, khai báo schema rõ ràng và kiểm thử runtime riêng.

### 5.3. Ràng buộc cho từng phần tử

Schema mảng có thể vừa giới hạn số lượng phần tử vừa giới hạn từng item:

```yaml
tags:
  type: array
  minItems: 1
  maxItems: 10
  uniqueItems: true
  items:
    type: string
    minLength: 1
    maxLength: 30
    pattern: '^[a-z0-9-]+$'
```

Với Java, dùng type-use constraints trên phần tử collection:

```java
public record ProductRequest(
        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) @Pattern(regexp = "^[a-z0-9-]+$") String> tags
) {}
```

Để validation phần tử lồng nhau hoặc DTO lồng nhau được thực thi, cần cascade validation phù hợp, thường dùng `@Valid` trên property collection. Ví dụ:

```java
public record OrderRequest(
        @NotEmpty
        @Size(max = 50)
        List<@Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
        @NotBlank String productCode,
        @Positive Integer quantity
) {}
```

Giới hạn mảng và ràng buộc từng phần tử là hai tầng khác nhau. `maxItems: 50` không giới hạn số lượng ký tự của `productCode`; cần khai báo constraint trên item hoặc thuộc tính bên trong item.

## 6. Khai báo giới hạn trực tiếp bằng Swagger Annotations

Khi Bean Validation không thể biểu diễn đầy đủ schema mong muốn hoặc cần bổ sung metadata riêng cho tài liệu, có thể dùng `@Schema` và `@ArraySchema`.

Ví dụ cho chuỗi:

```java
@Schema(
        description = "Mã sản phẩm viết hoa, gồm chữ, số và dấu gạch ngang",
        minLength = 5,
        maxLength = 24,
        pattern = "^[A-Z0-9-]+$"
)
private String productCode;
```

Ví dụ cho mảng:

```java
@ArraySchema(
        minItems = 1,
        maxItems = 10,
        uniqueItems = true,
        schema = @Schema(type = "string", minLength = 1, maxLength = 30)
)
private List<String> tags;
```

Các annotation Swagger bổ sung mô tả OpenAPI. Chúng không thay thế Bean Validation. Nếu chỉ khai báo `minLength`, `maximum` hoặc `uniqueItems` trong annotation mà không có validation runtime, Spring có thể vẫn nhận request vi phạm giới hạn đó.

Tránh khai báo cùng một quy tắc ở nhiều nơi với các giá trị khác nhau. Ví dụ, `@Size(max = 80)` nhưng `@Schema(maxLength = 100)` tạo ra tài liệu mâu thuẫn với hành vi server. Hãy dùng một nguồn ràng buộc chính khi có thể, sau đó kiểm tra metadata được springdoc sinh ra.

## 7. `required`, `nullable` và giới hạn giá trị là ba khái niệm khác nhau

Một thuộc tính có thể:

- **Bắt buộc**: phải xuất hiện trong JSON object.
- **Nullable**: nếu xuất hiện, giá trị có thể là `null`.
- **Có giới hạn**: nếu có giá trị, phải thỏa `minLength`, `maximum`, `maxItems` hoặc constraint khác.

Ví dụ, `nickname` có thể không bắt buộc nhưng nếu được gửi thì phải dài từ 2 đến 30 ký tự:

```yaml
type: object
properties:
  nickname:
    type: string
    minLength: 2
    maxLength: 30
```

Ở đây `nickname` không có trong danh sách `required`, nên có thể bị bỏ qua. Nếu được gửi, nó vẫn phải thỏa giới hạn độ dài. Việc cho phép `null` là một quy tắc khác và phụ thuộc phiên bản OpenAPI.

OpenAPI 3.0 thường dùng `nullable: true` để cho phép null bên cạnh type. OpenAPI 3.1 dựa trên JSON Schema 2020-12, có thể dùng union type như `type: [string, 'null']`. Không nhầm việc thiếu field với giá trị null; trong Spring, `@NotNull` và cơ chế binding/constructor cũng có thể ảnh hưởng validation khi field không được gửi.

## 8. Bean Validation được springdoc chuyển thành schema ra sao?

Springdoc đọc metadata của model và các annotation mà thư viện hỗ trợ để tạo schema. Một số ánh xạ phổ biến:

| Bean Validation | Schema thường tương ứng | Ghi chú |
|---|---|---|
| `@Size(min, max)` trên chuỗi | `minLength`, `maxLength` | `@Size` cũng áp dụng cho collection/map/array. |
| `@Pattern(regexp)` | `pattern` | Regex Java và regex JSON Schema có khác biệt. |
| `@Min`, `@DecimalMin` | `minimum` hoặc cận loại trừ | Phụ thuộc `inclusive` và phiên bản OpenAPI. |
| `@Max`, `@DecimalMax` | `maximum` hoặc cận loại trừ | Phụ thuộc `inclusive` và phiên bản OpenAPI. |
| `@Positive`, `@PositiveOrZero` | Cận dưới số | Kiểm tra output với phiên bản đang dùng. |
| `@Negative`, `@NegativeOrZero` | Cận trên số | Kiểm tra output với phiên bản đang dùng. |
| `@NotNull` | Required/không nullable tùy vị trí và phiên bản | Không đồng nghĩa với `minLength` hoặc `minItems`. |
| `@NotEmpty` | Required và kích thước tối thiểu ở kiểu phù hợp | Cần kiểm tra schema thực tế. |
| `@Digits` | Có thể cần metadata bổ sung | Không phải mọi giới hạn chữ số đều ánh xạ chính xác sang một keyword. |

Để springdoc có thể đọc các constraint, dự án cần dependency Bean Validation tương ứng, thường là `spring-boot-starter-validation` trong Spring Boot. Nếu thiếu provider hoặc annotation nằm ở package không được runtime sử dụng, metadata có thể không được xử lý như mong muốn.

Với nested DTO, dùng `@Valid` để kích hoạt cascade validation ở runtime. Springdoc vẫn có thể đọc schema của kiểu lồng nhau, nhưng điều đó không bảo đảm validation lồng nhau đã được bật.

## 9. Kiểm tra schema sinh ra

Sau khi thêm constraint, khởi động ứng dụng và đọc tài liệu tại `/v3/api-docs` hoặc đường dẫn đã cấu hình. Tìm schema tương ứng và kiểm tra:

1. Kiểu property có đúng là `string`, `integer`, `number` hoặc `array` không?
2. `minLength` và `maxLength` có khớp `@Size` không?
3. `pattern` có đúng biểu thức, dấu anchor và escape không?
4. `minimum`/`maximum` có đúng cận và tính bao gồm/loại trừ không?
5. Với OpenAPI 3.0/3.1, exclusive bound có đúng hình thức của phiên bản không?
6. `minItems`, `maxItems`, `uniqueItems` có xuất hiện đúng ở schema mảng không?
7. Ràng buộc item có nằm trong `items` thay vì đặt nhầm ở cấp array không?
8. Required và nullable có phản ánh đúng yêu cầu request không?

Ví dụ kết quả mong muốn cho `CreateProductRequest`:

```yaml
CreateProductRequest:
  type: object
  required:
    - name
    - price
    - tags
  properties:
    name:
      type: string
      minLength: 3
      maxLength: 80
    price:
      type: number
      minimum: 0.01
      maximum: 999999.99
    tags:
      type: array
      minItems: 1
      maxItems: 10
      uniqueItems: true
      items:
        type: string
        minLength: 1
        maxLength: 30
```

Đây là cấu trúc minh họa. Kết quả thực tế có thể dùng `$ref` cho schema, đặt `required` theo metadata của record/constructor và biểu diễn cận số khác nhau tùy phiên bản OpenAPI.

## 10. Kiểm tra validation ở runtime

Tài liệu OpenAPI giúp client phát hiện dữ liệu sai trước khi gửi, nhưng server vẫn phải xác thực request. Ví dụ:

```java
public record CreateProductRequest(
        @NotBlank
        @Size(min = 3, max = 80)
        String name,

        @NotNull
        @DecimalMin("0.01")
        @DecimalMax("999999.99")
        BigDecimal price,

        @NotEmpty
        @Size(max = 10)
        List<@NotBlank @Size(max = 30) String> tags
) {}
```

Controller:

```java
@PostMapping("/api/products")
ProductResponse create(
        @Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

`@Valid` yêu cầu Spring kích hoạt Bean Validation trên request body. Các lỗi như tên quá ngắn, giá âm hoặc danh sách nhãn rỗng sẽ tạo lỗi validation. Ứng dụng nên chuẩn hóa lỗi thành response nhất quán, thường là `400 Bad Request`, và mô tả response lỗi đó trong OpenAPI.

### 10.1. Ví dụ integration test

Với MockMvc, có thể kiểm tra dữ liệu không hợp lệ bị từ chối:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsNameShorterThanMinimum() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "AB",
                                  "price": 10.00,
                                  "tags": ["java"]
                                }
                                """))
                .andExpect(status().isBadRequest());
    }
}
```

Test trên giả định ứng dụng đã cấu hình xử lý validation error thành HTTP 400. Nếu ứng dụng dùng error handler riêng, điều chỉnh assertion cho phù hợp và kiểm tra nội dung response lỗi.

Nên có cả test biên hợp lệ và không hợp lệ: giá trị đúng bằng minimum, thấp hơn minimum, chuỗi đúng maxLength, dài hơn maxLength, mảng có số phần tử tối thiểu/tối đa và mảng có phần tử trùng khi uniqueness là yêu cầu.

## 11. Những lỗi thường gặp

- **Chỉ dùng `@Size` nhưng quên `@NotNull`/`@NotBlank`**: `@Size` cho phép null; kết hợp constraint theo yêu cầu bắt buộc.
- **Nhầm `maxLength` với số byte**: giới hạn độ dài chuỗi không phải giới hạn kích thước UTF-8 hay dung lượng request.
- **Dùng regex không có anchor**: một chuỗi dài hơn có thể chứa đoạn khớp nhưng không đúng định dạng toàn chuỗi.
- **Dùng regex Java có tính năng không tương thích JSON Schema**: ưu tiên cú pháp chung và kiểm tra bằng cả hai validator.
- **Nhầm cận bao gồm và cận loại trừ**: kiểm tra `inclusive` của `@DecimalMin`/`@DecimalMax` và dạng OpenAPI 3.0/3.1.
- **Dùng `@Min` cho số thập phân**: với `BigDecimal`, dùng `@DecimalMin`/`@DecimalMax`.
- **Chỉ giới hạn mảng mà không giới hạn item**: đặt constraint ở `items` hoặc phần tử generic khi cần.
- **Cho rằng `uniqueItems: true` tự kiểm tra runtime**: bổ sung validation hoặc logic kiểm tra uniqueness phía server.
- **Cho rằng schema annotation thay thế Bean Validation**: `@Schema` và `@ArraySchema` chỉ bổ sung tài liệu.
- **Không kiểm tra output sau đổi phiên bản OpenAPI**: exclusive bounds và nullability có thể đổi cách biểu diễn giữa 3.0 và 3.1.

## 12. Quy trình thiết kế constraint cho DTO

1. **Xác định kiểu dữ liệu**: chuỗi, số nguyên, số thập phân, collection hay array.
2. **Xác định giới hạn nghiệp vụ**: độ dài, khoảng số, regex, số phần tử, uniqueness.
3. **Chọn Bean Validation**: `@Size`, `@Pattern`, `@Min`, `@DecimalMin`, `@Positive`, `@NotBlank`, `@NotEmpty` hoặc constraint phù hợp.
4. **Bổ sung schema metadata nếu cần**: dùng `@Schema`, `@ArraySchema` hoặc customizer khi constraint không được ánh xạ đầy đủ.
5. **Kiểm tra phiên bản OpenAPI**: đặc biệt với exclusive bounds và nullable.
6. **Đọc `/v3/api-docs`**: xác nhận constraint nằm đúng property/item và có giá trị chính xác.
7. **Kiểm thử runtime**: gửi giá trị hợp lệ, sát biên và vượt biên; xác nhận server từ chối dữ liệu sai.
8. **Kiểm thử consumer**: xác nhận Swagger UI, SDK generator hoặc validator hiểu schema giống hợp đồng dự kiến.

## 13. Checklist review

- [ ] `minLength`/`maxLength` phù hợp với giới hạn chuỗi.
- [ ] `pattern` có anchor khi cần khớp toàn chuỗi và dùng regex tương thích.
- [ ] `minimum`/`maximum` đúng giá trị và đúng tính bao gồm biên.
- [ ] `exclusiveMinimum`/`exclusiveMaximum` phù hợp phiên bản OpenAPI 3.0 hoặc 3.1.
- [ ] `minItems`/`maxItems` áp dụng ở cấp array.
- [ ] `uniqueItems` có validation runtime tương ứng nếu uniqueness là yêu cầu nghiệp vụ.
- [ ] Ràng buộc của từng phần tử được đặt trong schema `items` và validation type-use phù hợp.
- [ ] Required và nullable được xem xét độc lập với giới hạn giá trị.
- [ ] Bean Validation provider đã có trong runtime và `@Valid` được đặt đúng vị trí.
- [ ] `/v3/api-docs` đã được kiểm tra sau khi thay đổi DTO hoặc annotation.
- [ ] Integration test bao phủ giá trị hợp lệ, biên và không hợp lệ.

## 14. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Schema Object](https://spec.openapis.org/oas/v3.1.2.html#schema-object)
- [OpenAPI Specification 3.0.4 – Schema Object](https://spec.openapis.org/oas/v3.0.4.html#schema-object)
- [JSON Schema – Validation keywords](https://json-schema.org/draft/2020-12/json-schema-validation)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [springdoc-openapi FAQ](https://springdoc.org/faq.html)

Các giới hạn schema giúp người tiêu thụ API hiểu dữ liệu hợp lệ trước khi gửi request. Hãy khai báo constraint bằng Bean Validation để server thực thi, để springdoc chuyển chúng thành OpenAPI, rồi kiểm tra output và runtime ở các giá trị biên. Khi schema và validation cùng mô tả một quy tắc, hợp đồng API sẽ đáng tin cậy hơn cho Swagger UI, SDK và các hệ thống tích hợp.
