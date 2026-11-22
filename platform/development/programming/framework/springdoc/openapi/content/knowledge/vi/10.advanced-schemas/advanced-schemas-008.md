# Đa hình, discriminator và ánh xạ giá trị sang schema

Một API đôi khi nhận hoặc trả về nhiều dạng dữ liệu có chung một vai trò. Ví dụ, phương thức thanh toán có thể là thẻ ngân hàng hoặc chuyển khoản; thông báo có thể là sự kiện tạo đơn hàng hoặc hủy đơn hàng. Nếu mô hình Java chỉ dùng một kiểu cha, client vẫn cần biết payload cụ thể thuộc dạng nào để đọc đúng các thuộc tính.

OpenAPI giải quyết bài toán này bằng các schema kết hợp như `oneOf`, `anyOf`, `allOf` và trường `discriminator`. Springdoc có thể sinh các cấu trúc đó từ kiểu Java cùng annotation Swagger/OpenAPI. Jackson lại chịu trách nhiệm chọn lớp Java khi deserialize JSON. Hai phần cần dùng chung tên thuộc tính phân biệt và cùng ánh xạ giá trị để hợp đồng công bố khớp với runtime.

## 1. Đa hình trong hợp đồng API

Đa hình cho phép một vị trí trong request hoặc response chứa một trong nhiều cấu trúc dữ liệu. Thay vì khai báo một object có hàng loạt field tùy chọn, ta định nghĩa một kiểu cơ sở và các kiểu cụ thể.

Ví dụ, `PaymentMethod` là kiểu cơ sở. API hỗ trợ hai dạng:

- `CardPayment`: thanh toán bằng thẻ, có token và bốn chữ số cuối.
- `BankTransferPayment`: thanh toán bằng chuyển khoản, có mã ngân hàng và mã tham chiếu.

JSON có thể có một trong hai dạng:

```json
{
  "kind": "card",
  "token": "tok_abc123",
  "last4": "4242"
}
```

Hoặc:

```json
{
  "kind": "bank-transfer",
  "bankCode": "VCB",
  "reference": "ORDER-2026-001"
}
```

Thuộc tính `kind` cho biết payload đang sử dụng biến thể nào. Client có thể đọc trường này để quyết định cách xử lý các thuộc tính còn lại.

## 2. Phân biệt `oneOf`, `anyOf` và `allOf`

OpenAPI có nhiều cách kết hợp schema. Chọn đúng toán tử sẽ quyết định ý nghĩa kiểm tra payload:

| Từ khóa | Ý nghĩa | Trường hợp thường dùng |
| --- | --- | --- |
| `oneOf` | Payload phải hợp lệ với **chính xác một** schema trong danh sách. | Các biến thể loại trừ nhau, chẳng hạn thẻ hoặc chuyển khoản. |
| `anyOf` | Payload phải hợp lệ với **ít nhất một** schema trong danh sách; có thể đồng thời khớp nhiều schema. | Các cấu trúc có thể chồng lấn hoặc một payload có thể thỏa nhiều mô hình. |
| `allOf` | Payload phải thỏa **tất cả** schema trong danh sách. | Kết hợp thuộc tính chung với thuộc tính mở rộng, hoặc mô tả quan hệ kế thừa. |

Ví dụ `oneOf`:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
```

Ví dụ `allOf` để kết hợp phần chung và phần riêng:

```yaml
CardPayment:
  allOf:
    - $ref: '#/components/schemas/PaymentBase'
    - type: object
      properties:
        last4:
          type: string
```

`allOf` không có nghĩa là chọn một kiểu con. Nó ghép các ràng buộc schema; một payload phải đáp ứng tất cả thành phần. Nếu cần biểu diễn nhiều lựa chọn loại trừ nhau, `oneOf` thường phù hợp hơn.

## 3. Discriminator giúp nhận diện biến thể

`discriminator` chỉ định thuộc tính trong payload dùng để nhận diện schema cụ thể. Nó có hai phần quan trọng:

- `propertyName`: tên thuộc tính phân biệt, ví dụ `kind`.
- `mapping`: ánh xạ giá trị xuất hiện trong JSON sang schema tương ứng.

Ví dụ:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: kind
    mapping:
      card: '#/components/schemas/CardPayment'
      bank-transfer: '#/components/schemas/BankTransferPayment'
```

Với cấu hình này:

- `"kind": "card"` trỏ đến schema `CardPayment`.
- `"kind": "bank-transfer"` trỏ đến schema `BankTransferPayment`.

Giá trị bên trái của `mapping` là giá trị wire format trong JSON. Giá trị bên phải là tên schema hoặc tham chiếu schema. Không nhất thiết tên giá trị JSON phải giống tên lớp Java. Việc ánh xạ tường minh giúp giữ tên hợp đồng ổn định ngay cả khi đổi tên class hoặc package trong mã nguồn.

Nếu không khai báo mapping tường minh, công cụ có thể suy luận mapping ngầm từ tên schema. Cách suy luận đó kém rõ ràng khi tên class, tên component và giá trị discriminator khác nhau. Với API công khai, nên khai báo mapping tường minh để client không phải đoán.

Thuộc tính discriminator cần xuất hiện trong các biến thể và nên được yêu cầu trong payload. Nếu schema của subtype không mô tả trường `kind`, một số công cụ sinh client hoặc validator có thể không hiểu đầy đủ hợp đồng, dù runtime Jackson vẫn phân loại được JSON.

## 4. Kết hợp annotation OpenAPI với Jackson

Springdoc dùng annotation `@Schema` để mô tả cấu trúc OpenAPI. Jackson dùng `@JsonTypeInfo` và `@JsonSubTypes` để chọn subtype khi đọc hoặc ghi JSON. Hai bộ annotation giải quyết hai trách nhiệm khác nhau.

Định nghĩa kiểu cơ sở:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.EXISTING_PROPERTY,
    property = "kind",
    visible = true
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank-transfer")
})
@Schema(
    name = "PaymentMethod",
    description = "Một trong các phương thức thanh toán được hỗ trợ",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPayment.class),
        @DiscriminatorMapping(value = "bank-transfer", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {}
```

Định nghĩa các biến thể:

```java
@Schema(name = "CardPayment", description = "Thanh toán bằng thẻ")
public record CardPayment(
    @NotBlank
    @Schema(allowableValues = {"card"}, example = "card")
    String kind,

    @NotBlank
    String token,

    @NotBlank
    @Pattern(regexp = "^[0-9]{4}$")
    String last4
) implements PaymentMethod {}
```

```java
@Schema(name = "BankTransferPayment", description = "Thanh toán bằng chuyển khoản")
public record BankTransferPayment(
    @NotBlank
    @Schema(allowableValues = {"bank-transfer"}, example = "bank-transfer")
    String kind,

    @NotBlank
    String bankCode,

    @NotBlank
    String reference
) implements PaymentMethod {}
```

Trong ví dụ, `As.EXISTING_PROPERTY` cho Jackson biết `kind` là thuộc tính thật của subtype và serializer sẽ ghi giá trị từ thuộc tính đó. `visible = true` giữ type id để deserializer chuyển nó vào constructor của record. Các record có field `kind`, nên giá trị được lưu trong object sau deserialize. Các constraint và `allowableValues` cũng giúp mô tả trường discriminator là bắt buộc và có giá trị cụ thể cho từng biến thể.

Đặt kiểu cơ sở trong một request:

```java
public record CreatePaymentRequest(
    @NotNull
    @Valid
    PaymentMethod paymentMethod
) {}
```

Và sử dụng trong controller:

```java
@PostMapping("/payments")
@Operation(summary = "Tạo thanh toán")
ResponseEntity<PaymentResponse> create(
    @Valid @RequestBody CreatePaymentRequest request
) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(paymentService.create(request.paymentMethod()));
}
```

Khi deserialize `CreatePaymentRequest`, Jackson đọc `paymentMethod.kind`, sau đó chọn `CardPayment` hoặc `BankTransferPayment` theo `@JsonSubTypes`. Springdoc dùng `oneOf` và discriminator mapping để mô tả lựa chọn tương ứng cho client.

## 5. Tên schema và discriminator mapping phải nhất quán

Một lỗi phổ biến là dùng tên Java class làm giá trị discriminator mà không kiểm tra schema component được sinh ra. Hãy phân biệt ba tên:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên thuộc tính discriminator | `kind` | Tên field trong JSON. |
| Giá trị discriminator | `bank-transfer` | Giá trị JSON mà Jackson dùng để chọn subtype. |
| Tên schema | `BankTransferPayment` | Component OpenAPI mô tả cấu trúc subtype. |

Ánh xạ tường minh kết nối giá trị JSON với tên schema. Nếu đổi tên class Java, mapping vẫn có thể giữ `bank-transfer` cho API cũ. Nếu đổi giá trị discriminator, đó là thay đổi hợp đồng và có thể làm client cũ không còn deserialize được payload mới.

Có thể dùng `@Schema(name = "...")` để kiểm soát tên component thay vì để thư viện suy ra từ tên lớp. Sau khi đổi tên schema, kiểm tra `discriminator.mapping` và mọi `$ref` trong đặc tả để bảo đảm chúng cùng trỏ đến component tồn tại.

## 6. Khi nào dùng `@JsonTypeName`, `@JsonSubTypes` và `@DiscriminatorMapping`?

Các annotation có vai trò khác nhau:

| Annotation | Thư viện | Trách nhiệm |
| --- | --- | --- |
| `@JsonTypeInfo` | Jackson | Chọn chiến lược lưu type id trong JSON và tên thuộc tính discriminator. |
| `@JsonSubTypes` | Jackson | Đăng ký các subtype và giá trị type id để deserialize/serialize. |
| `@JsonTypeName` | Jackson | Đặt tên type id mặc định cho một subtype. |
| `@Schema(oneOf = ...)` | Swagger/OpenAPI | Công bố danh sách schema thay thế. |
| `@Schema(discriminatorProperty = ...)` | Swagger/OpenAPI | Công bố thuộc tính phân biệt. |
| `@DiscriminatorMapping` | Swagger/OpenAPI | Ánh xạ giá trị discriminator sang schema cụ thể. |

Nếu đã khai báo tên subtype trong `@JsonSubTypes.Type(name = "card")`, không cần lặp lại `@JsonTypeName` cho cùng mục đích. `@JsonTypeName` hữu ích khi muốn subtype tự mang tên type id mặc định và cấu hình Jackson được tổ chức theo cách khác. Dù chọn cách nào, hãy giữ giá trị type id trùng với khóa mapping OpenAPI.

Không nhầm `@DiscriminatorMapping` với cấu hình Jackson. Chỉ thêm mapping OpenAPI không làm Jackson biết cách khởi tạo subtype. Ngược lại, chỉ thêm `@JsonSubTypes` có thể giúp runtime hoạt động nhưng đặc tả vẫn thiếu `oneOf` hoặc discriminator mapping cho client.

## 7. Phân biệt discriminator với kế thừa Java

Discriminator không yêu cầu các schema phải có quan hệ kế thừa Java. Nó là metadata trong OpenAPI để nhận diện biến thể. Có thể dùng discriminator với các schema độc lập miễn là mỗi schema có thuộc tính phân biệt và mapping phù hợp.

Khi các subtype thực sự kế thừa một lớp cơ sở, springdoc hoặc Swagger Core có thể biểu diễn thuộc tính chung bằng `allOf`. Ví dụ:

```yaml
PaymentBase:
  type: object
  required:
    - kind
  properties:
    kind:
      type: string

CardPayment:
  allOf:
    - $ref: '#/components/schemas/PaymentBase'
    - type: object
      required:
        - token
      properties:
        token:
          type: string
```

Trong khi đó, schema cơ sở có thể liệt kê các subtype bằng `oneOf`. `allOf` thể hiện phần cấu trúc được kết hợp; `oneOf` thể hiện các lựa chọn cụ thể. Không nên thay thế hai ý nghĩa này cho nhau.

## 8. Những trường hợp mapping không khớp

Giả sử Jackson khai báo:

```java
@JsonSubTypes.Type(value = CardPayment.class, name = "card")
```

Nhưng OpenAPI lại ánh xạ:

```yaml
discriminator:
  propertyName: kind
  mapping:
    credit-card: '#/components/schemas/CardPayment'
```

Client gửi `"kind": "credit-card"` theo tài liệu nhưng Jackson không biết giá trị này, vì runtime chỉ đăng ký `card`. Request có thể thất bại khi deserialize. Ngược lại, nếu Jackson chấp nhận một type id mà OpenAPI không liệt kê, tài liệu không phản ánh hết khả năng runtime.

Giữ đồng bộ các mục sau:

- `propertyName` trong OpenAPI phải trùng với `property` trong `@JsonTypeInfo`.
- Khóa trong `discriminatorMapping` phải trùng với tên subtype trong `@JsonSubTypes.Type(name = ...)` hoặc type id do Jackson cấu hình.
- Schema đích của mapping phải có trong `components.schemas`.
- Thuộc tính discriminator cần được mô tả trong các subtype và có giá trị phù hợp.
- Các subtype trong `oneOf` phải mô tả những payload mà runtime thật sự chấp nhận.

## 9. Kiểm tra đặc tả và deserialize runtime

Với API đa hình, chỉ nhìn Swagger UI là chưa đủ. Cần kiểm tra cả đặc tả và Jackson:

1. Mở `/v3/api-docs` và tìm schema cơ sở `PaymentMethod`.
2. Xác nhận `oneOf` liệt kê đúng `CardPayment` và `BankTransferPayment`.
3. Xác nhận `discriminator.propertyName` là `kind` và mapping chứa `card`, `bank-transfer` với `$ref` hợp lệ.
4. Kiểm tra mỗi subtype có thuộc tính `kind` và các field riêng cần thiết.
5. Gửi request có `kind: card`; xác minh Jackson tạo `CardPayment`.
6. Gửi request có `kind: bank-transfer`; xác minh Jackson tạo `BankTransferPayment`.
7. Gửi type id không biết, thiếu discriminator hoặc thiếu field bắt buộc; xác minh ứng dụng trả lỗi đầu vào phù hợp.
8. Kiểm tra response để bảo đảm Jackson serialize đúng type id và cấu trúc schema.

Ví dụ kiểm thử deserialize đơn giản:

```java
@Test
void readsCardPaymentFromDiscriminator() throws Exception {
    String json = """
        {
          "kind": "card",
          "token": "tok_abc123",
          "last4": "4242"
        }
        """;

    PaymentMethod payment = objectMapper.readValue(json, PaymentMethod.class);

    assertThat(payment).isInstanceOf(CardPayment.class);
}
```

Kiểm thử này xác nhận cấu hình Jackson. Một kiểm thử khác cần xác nhận đặc tả OpenAPI có mapping đúng; hai việc không thay thế nhau.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI chỉ hiển thị schema cha | Chưa khai báo `oneOf` hoặc subtype chưa được phát hiện | Dùng `@Schema(oneOf = {...})` và kiểm tra `components.schemas`. |
| Discriminator mapping trỏ đến schema không tồn tại | Tên schema thay đổi hoặc mapping được khai báo sai | Dùng `@Schema(name = ...)` và kiểm tra mọi `$ref`. |
| Jackson báo type id không hợp lệ | `@JsonSubTypes` không chứa giá trị client gửi | Đồng bộ type id giữa Jackson và OpenAPI mapping. |
| Field discriminator biến mất khỏi object subtype | Jackson dùng `visible = false` mặc định | Dùng `visible = true` nếu subtype cần bind field đó; hoặc thiết kế subtype không cần lưu field. |
| Client generator tạo kiểu dữ liệu sai | `oneOf`, `allOf` hoặc discriminator không thể hiện đúng quan hệ | Kiểm tra cấu trúc schema và thử generator mục tiêu với một payload mẫu. |
| Payload khớp nhiều subtype trong `oneOf` | Các schema bị chồng lấn hoặc thiếu thuộc tính phân biệt | Thiết kế subtype loại trừ nhau và thêm discriminator bắt buộc có giá trị rõ ràng. |

## 10. Nguyên tắc áp dụng

- Dùng `oneOf` khi payload phải thuộc chính xác một biến thể; dùng `anyOf` khi nhiều schema có thể cùng khớp; dùng `allOf` để kết hợp ràng buộc hoặc mô tả cấu trúc kế thừa.
- Dùng một thuộc tính discriminator ổn định như `kind` hoặc `type`.
- Khai báo mapping tường minh khi giá trị JSON khác tên schema hoặc cần giữ hợp đồng ổn định qua đổi tên lớp Java.
- Đồng bộ `@JsonTypeInfo`, `@JsonSubTypes`, `@Schema` và `@DiscriminatorMapping`.
- Mô tả discriminator trong các subtype và bảo đảm giá trị đó được runtime xử lý đúng.
- Kiểm tra `/v3/api-docs`, request deserialize và response serialize như các bước riêng.
- Không dùng discriminator như một cơ chế xác thực hoặc kiểm tra bảo mật; nó chỉ chọn cách diễn giải cấu trúc dữ liệu.

`discriminator` kết nối giá trị nhận diện trong JSON với schema mô tả từng biến thể. Khi `oneOf`, mapping OpenAPI và cấu hình Jackson thống nhất, client có thể hiểu payload đa hình và server có thể deserialize đúng subtype. Tên type id là một phần của hợp đồng công khai, vì vậy cần quản lý nó cẩn thận khi thay đổi model.

## Tài liệu tham khảo

- [OpenAPI Specification – Composition and Inheritance](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@Schema` và `@DiscriminatorMapping`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Jackson Annotations – Polymorphic Type Handling](https://github.com/FasterXML/jackson-annotations)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
