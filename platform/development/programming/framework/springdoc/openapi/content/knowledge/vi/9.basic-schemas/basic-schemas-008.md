# Map, khóa chuỗi và `additionalProperties`

Trong Java, `Map<K, V>` lưu các cặp khóa và giá trị. Khi dữ liệu được biểu diễn bằng JSON object, mỗi khóa trở thành tên thuộc tính của object. OpenAPI mô tả kiểu dữ liệu này bằng `type: object`; trường `additionalProperties` cho biết những thuộc tính động được phép có giá trị gì.

Với springdoc-openapi, khai báo kiểu generic rõ ràng thường đủ để thư viện suy ra schema cho map. Ví dụ `Map<String, Integer>` trở thành object có các giá trị số nguyên; `Map<String, ProductAttribute>` trở thành object có các giá trị theo schema `ProductAttribute`. Hiểu đúng `additionalProperties` giúp phân biệt object có tập field cố định với object có các khóa do client hoặc dữ liệu nghiệp vụ quyết định.

## 1. Object có field cố định và map có khóa động

Một DTO thông thường có các thuộc tính được biết trước:

```java
public record CustomerRequest(
    String name,
    String email
) {}
```

Schema OpenAPI tương ứng thường có `properties` cho `name` và `email`:

```yaml
type: object
properties:
  name:
    type: string
  email:
    type: string
```

Tên field đã được xác định trong model. Client biết trước các thuộc tính hợp lệ và ý nghĩa của từng thuộc tính.

Ngược lại, một map cho phép tên thuộc tính thay đổi theo dữ liệu:

```java
Map<String, Integer> stockByWarehouse;
```

Một giá trị JSON có thể là:

```json
{
  "warehouse-hcm": 120,
  "warehouse-hn": 85,
  "warehouse-dn": 42
}
```

Tên kho là các khóa động. API không khai báo trước từng kho; nó chỉ quy định rằng mỗi giá trị trong object phải là số nguyên. OpenAPI biểu diễn điều đó bằng `additionalProperties`.

| Khái niệm | Mục đích |
| --- | --- |
| `properties` | Mô tả các field có tên cố định của object. |
| `additionalProperties` | Mô tả giá trị của các field bổ sung có tên động, hoặc cho biết chúng có được phép hay không. |

`additionalProperties` không phải danh sách tên khóa được phép. Nó mô tả schema của giá trị tương ứng với mỗi khóa bổ sung.

## 2. Cách `Map<String, V>` được ánh xạ sang OpenAPI

Trong JSON, tên thuộc tính của object luôn là chuỗi. Vì vậy `Map<String, V>` là dạng map tự nhiên nhất cho JSON object. Kiểu `V` quyết định schema của từng giá trị:

| Kiểu Java | Schema OpenAPI thường được sinh |
| --- | --- |
| `Map<String, String>` | `type: object`, `additionalProperties: { type: string }` |
| `Map<String, Integer>` | `type: object`, `additionalProperties: { type: integer, format: int32 }` |
| `Map<String, BigDecimal>` | `type: object`, `additionalProperties: { type: number }` |
| `Map<String, Boolean>` | `type: object`, `additionalProperties: { type: boolean }` |
| `Map<String, ProductAttribute>` | `type: object`, `additionalProperties` tham chiếu schema `ProductAttribute` |
| `Map<String, List<String>>` | `type: object`, giá trị bổ sung là array có item kiểu string |

Ví dụ DTO có các nhãn tùy chỉnh:

```java
public record ProductRequest(
    @NotBlank
    String name,

    Map<String, String> labels
) {}
```

Client có thể gửi:

```json
{
  "name": "Bàn phím cơ",
  "labels": {
    "color": "black",
    "layout": "US",
    "switch": "linear"
  }
}
```

Schema của `labels` có dạng:

```yaml
labels:
  type: object
  additionalProperties:
    type: string
```

Springdoc thường suy luận schema giá trị từ tham số generic `String`. Không cần khai báo từng khóa `color`, `layout` hay `switch`, vì chúng là dữ liệu động.

## 3. Map có giá trị là object hoặc model riêng

Map không chỉ chứa kiểu nguyên thủy. Khi mỗi giá trị có cấu trúc rõ ràng, hãy tạo một DTO riêng để client hiểu các field bên trong:

```java
public record ProductAttribute(
    String value,
    String source,
    Instant updatedAt
) {}

public record ProductResponse(
    UUID id,
    String name,
    Map<String, ProductAttribute> attributes
) {}
```

Ví dụ response:

```json
{
  "id": "f8a5f7f4-c1ef-4e37-a2b7-c1c3d1d6a120",
  "name": "Bàn phím cơ",
  "attributes": {
    "color": {
      "value": "black",
      "source": "catalog",
      "updatedAt": "2026-11-20T09:30:00Z"
    },
    "layout": {
      "value": "US",
      "source": "supplier",
      "updatedAt": "2026-11-19T15:00:00Z"
    }
  }
}
```

Schema của `attributes` thường có dạng:

```yaml
type: object
additionalProperties:
  $ref: '#/components/schemas/ProductAttribute'
```

Mỗi khóa động ánh xạ đến một giá trị có cấu trúc theo `ProductAttribute`. Cách này giữ được tính linh hoạt của tên khóa, đồng thời vẫn mô tả chặt chẽ hình dạng của từng giá trị.

Nếu giá trị là danh sách, ví dụ `Map<String, List<ProductAttribute>>`, schema của `additionalProperties` sẽ là `type: array` và có `items` tham chiếu `ProductAttribute`. Với map lồng nhau như `Map<String, Map<String, String>>`, giá trị bổ sung lại là một object có `additionalProperties` riêng. Có thể lồng nhiều cấp, nhưng cấu trúc quá sâu sẽ làm client khó hiểu và khó kiểm tra.

## 4. `additionalProperties` có ba cách biểu diễn quan trọng

Trong OpenAPI, `additionalProperties` có thể là boolean hoặc một Schema Object:

| Giá trị | Ý nghĩa |
| --- | --- |
| `true` | Cho phép thuộc tính bổ sung với giá trị không bị ràng buộc bởi schema cụ thể. |
| `false` | Không cho phép thuộc tính bổ sung ngoài các field đã khai báo trong `properties`. |
| Một schema object | Cho phép thuộc tính bổ sung, nhưng giá trị của mỗi thuộc tính phải khớp schema đó. |

Ví dụ cho phép giá trị bất kỳ:

```yaml
type: object
additionalProperties: true
```

Ví dụ cấm field không được khai báo:

```yaml
type: object
properties:
  name:
    type: string
  email:
    type: string
additionalProperties: false
```

Ví dụ cho phép các khóa động nhưng mọi giá trị phải là Boolean:

```yaml
type: object
additionalProperties:
  type: boolean
```

Trong OpenAPI, nếu không khai báo `additionalProperties`, mặc định thông thường là cho phép các thuộc tính bổ sung. Vì vậy, nếu hợp đồng cần một object đóng, hãy khai báo rõ `false` và kiểm tra cách server xử lý field lạ.

## 5. Dùng `@Schema` để tùy chỉnh `additionalProperties`

Khi kiểu generic đã rõ, springdoc thường tự sinh schema phù hợp. Annotation `@Schema` hữu ích khi cần mô tả rõ hơn hoặc kiểu Java không giữ đủ thông tin generic.

Với một map chỉ chứa chuỗi:

```java
public class ProductMetadata {

    @Schema(
        description = "Các nhãn tùy chỉnh; mọi giá trị đều là chuỗi",
        additionalPropertiesSchema = String.class
    )
    private Map<String, Object> labels;

    public Map<String, Object> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, Object> labels) {
        this.labels = labels;
    }
}
```

Ở ví dụ này, Java khai báo giá trị là `Object`, nhưng annotation công bố giá trị trên wire contract là chuỗi. Chỉ sử dụng cách override này nếu ứng dụng thật sự bảo đảm mọi giá trị đều là chuỗi. Nếu runtime cho phép object, số hoặc Boolean, schema phải phản ánh đúng điều đó.

Nếu có thể, nên khai báo kiểu Java chính xác ngay từ đầu:

```java
private Map<String, String> labels;
```

Khi muốn đóng một DTO và cấm thuộc tính không biết trước, có thể dùng:

```java
@Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
public record CreateCustomerRequest(
    String name,
    String email
) {}
```

`Schema.AdditionalPropertiesValue.FALSE` yêu cầu schema OpenAPI không cho phép field bổ sung. Annotation này chỉ thay đổi hợp đồng được sinh ra. Jackson có thể vẫn bỏ qua field lạ theo cấu hình mặc định của ứng dụng; nếu server phải từ chối dữ liệu không được khai báo, hãy cấu hình và kiểm thử hành vi deserialize, chẳng hạn `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`.

`additionalPropertiesSchema` và `additionalProperties` là hai thuộc tính khác nhau của `@Schema`: thuộc tính thứ nhất chỉ định schema cho giá trị động; thuộc tính thứ hai chọn cho phép, cấm hoặc suy ra cách xử lý thuộc tính bổ sung. Cả hai cần được kiểm tra trong tài liệu của phiên bản `swagger-annotations` mà nhánh springdoc sử dụng.

## 6. Phân biệt map tự do với `Map<String, Object>`

`Map<String, Object>` linh hoạt vì giá trị có thể là chuỗi, số, Boolean, list hoặc object khác. Tuy nhiên, kiểu này làm hợp đồng yếu hơn:

```java
public record EventPayload(
    String eventType,
    Map<String, Object> data
) {}
```

Client biết `data` là một object nhưng không biết chắc mỗi khóa chứa kiểu gì. Schema có thể biểu diễn `additionalProperties` với schema rỗng hoặc dạng không ràng buộc, tùy phiên bản và cách springdoc xử lý `Object`.

Chỉ nên dùng map tự do khi dữ liệu thực sự là extension tùy biến hoặc cấu trúc không thể biết trước. Nếu các trường đã được xác định theo từng loại event, cân nhắc DTO cụ thể hoặc mô hình đa hình với `oneOf`/discriminator. Ví dụ, một event `ORDER_CREATED` có `orderId` và `total`, còn event `USER_REGISTERED` có `userId` và `registeredAt`; DTO riêng giúp tài liệu, validation và client code rõ ràng hơn.

Tránh dùng raw `Map` không có generic:

```java
// Không khuyến nghị: kiểu giá trị không được khai báo rõ.
Map attributes;

// Rõ ràng hơn: schema giá trị là chuỗi.
Map<String, String> attributes;
```

Raw type làm mất thông tin kiểu ở thời điểm biên dịch và có thể khiến schema sinh ra quá rộng. Nếu dùng `Object`, hãy mô tả rõ cấu trúc và ví dụ, đồng thời xác minh schema thực tế.

## 7. Khóa của Map phải phù hợp với tên thuộc tính JSON

JSON object dùng tên thuộc tính dạng chuỗi. Vì vậy, map dùng `String` làm khóa giúp hợp đồng đơn giản và dễ tương thích với các client:

```java
Map<String, BigDecimal> prices;
```

Nếu dùng kiểu khóa khác như `Map<Integer, String>` hoặc `Map<UUID, String>`, Jackson có thể chuyển khóa thành chuỗi khi serialize JSON và chuyển đổi ngược khi deserialize. Cách chuyển đổi phụ thuộc key serializer/deserializer hoặc converter được cấu hình. OpenAPI vẫn mô tả tên thuộc tính object dưới dạng chuỗi, nên kiểu khóa Java không tự trở thành kiểu số hoặc UUID trong cấu trúc JSON.

Ví dụ JSON cho map có khóa UUID vẫn có dạng:

```json
{
  "550e8400-e29b-41d4-a716-446655440000": "approved"
}
```

Nếu khóa mang ý nghĩa định danh, hãy mô tả quy ước định dạng khóa trong `description` và kiểm tra giá trị thực tế sau serialize. Nếu client cần một danh sách phần tử mà khóa là dữ liệu có kiểu riêng, có thể dùng array các object thay vì JSON object:

```json
[
  {
    "warehouseId": 101,
    "quantity": 120
  },
  {
    "warehouseId": 205,
    "quantity": 85
  }
]
```

Array cho phép `warehouseId` được mô tả là integer đúng nghĩa, trong khi khóa của JSON object luôn là chuỗi.

## 8. Ràng buộc số lượng entry và khóa map

OpenAPI Schema có các giới hạn `minProperties` và `maxProperties` để mô tả số lượng thuộc tính trong object. Có thể dùng `@Schema`:

```java
@Schema(
    description = "Tối đa 20 nhãn của sản phẩm",
    maxProperties = 20,
    additionalPropertiesSchema = String.class
)
private Map<String, String> labels;
```

`minProperties` và `maxProperties` áp dụng cho số cặp khóa/giá trị trong object. Chúng khác `minLength`/`maxLength`, vốn áp dụng cho chuỗi, và khác `minItems`/`maxItems`, vốn áp dụng cho array.

Có thể kiểm tra số lượng entry trong runtime bằng custom validation hoặc logic nghiệp vụ. Ví dụ, nếu API chỉ cho phép tối đa 20 nhãn, server phải thực sự từ chối map có hơn 20 phần tử. Metadata OpenAPI không tự thực thi giới hạn này.

Với tên khóa, có thể dùng container element constraint của Bean Validation để kiểm tra ở runtime:

```java
public record ProductLabels(
    Map<
        @NotBlank @Pattern(regexp = "^[a-z][a-z0-9_-]*$") String,
        @NotBlank @Size(max = 80) String
    > labels
) {}
```

Các constraint trên khóa và giá trị cần được kích hoạt bằng Bean Validation phù hợp. Việc chúng có được chuyển thành schema `propertyNames` hoặc schema giá trị trong OpenAPI hay không phụ thuộc phiên bản OpenAPI, springdoc và swagger-core; hãy kiểm tra `/v3/api-docs`. Trong OpenAPI 3.1, JSON Schema có `propertyNames` để mô tả quy tắc tên khóa. Không nên giả định mọi cấu hình OpenAPI 3.0 hoặc mọi client generator đều hiểu quy tắc đó.

## 9. Map lồng nhau và cấu trúc dữ liệu động

Map có thể chứa một map khác. Ví dụ cấu hình theo môi trường:

```java
Map<String, Map<String, String>> settingsByEnvironment;
```

JSON:

```json
{
  "development": {
    "logLevel": "DEBUG",
    "featureX": "true"
  },
  "production": {
    "logLevel": "WARN",
    "featureX": "false"
  }
}
```

Schema khái quát:

```yaml
type: object
additionalProperties:
  type: object
  additionalProperties:
    type: string
```

Mỗi cấp `additionalProperties` mô tả giá trị của các khóa ở cấp đó. Khi map lồng nhiều cấp, hãy đặt tên có ý nghĩa và cân nhắc tạo DTO cho từng cấp nếu cấu trúc bắt đầu ổn định. DTO giúp thêm mô tả, validation, ví dụ và kiểm soát các field tốt hơn.

## 10. Kiểm tra schema được springdoc sinh ra

Sau khi khai báo map hoặc tùy chỉnh `@Schema`, hãy kiểm tra đặc tả thực tế:

1. Khởi động ứng dụng và mở `/v3/api-docs` hoặc URL đã cấu hình.
2. Tìm model có thuộc tính map trong `components.schemas`.
3. Xác nhận map có `type: object` và `additionalProperties` mang đúng kiểu giá trị.
4. Với map giá trị là DTO, xác nhận `additionalProperties` tham chiếu đúng component schema.
5. Với object đóng, xác nhận `additionalProperties: false` được xuất ra.
6. Gửi JSON có khóa hợp lệ, giá trị hợp lệ; sau đó thử giá trị sai kiểu hoặc field lạ để kiểm tra runtime.
7. Kiểm tra serialize response để bảo đảm khóa và giá trị thực tế khớp schema.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Map xuất hiện như object không có kiểu giá trị | Dùng raw `Map` hoặc `Map<String, Object>` | Khai báo generic cụ thể hoặc mô tả schema giá trị bằng `additionalPropertiesSchema`. |
| Giá trị map trong Swagger UI có kiểu không đúng | Kiểu generic hoặc annotation override không khớp dữ liệu runtime | Kiểm tra `additionalProperties` trong `/v3/api-docs` và kiểu Java thực tế. |
| DTO cho phép field lạ dù schema ghi `false` | Jackson vẫn bỏ qua unknown properties | Cấu hình deserialize nghiêm ngặt và viết kiểm thử request. |
| Khóa số/UUID không deserialize được | Thiếu key deserializer hoặc format chuỗi không hợp lệ | Dùng `String` key hoặc cấu hình key serializer/deserializer rõ ràng. |
| Giới hạn số entry chỉ có trong tài liệu | `maxProperties` không được thực thi ở runtime | Thêm validation hoặc kiểm tra nghiệp vụ trong service. |
| Tên khóa sai quy tắc nhưng request vẫn được chấp nhận | Chưa có constraint cho map key | Dùng container element constraint và kiểm thử validation. |

## 11. Nguyên tắc áp dụng

- Dùng `Map<String, V>` khi tên khóa là dữ liệu động và mọi giá trị có cùng một kiểu.
- Ưu tiên generic cụ thể để springdoc sinh `additionalProperties` chính xác.
- Dùng DTO cho giá trị map có cấu trúc và dùng `Map<String, Object>` chỉ khi thực sự cần dữ liệu tự do.
- Dùng `additionalProperties: false` cho object đóng khi hợp đồng không cho phép field lạ; đồng bộ cấu hình Jackson nếu runtime cũng phải từ chối chúng.
- Nhớ rằng khóa JSON object luôn là chuỗi; dùng array object nếu khóa cần có kiểu dữ liệu riêng.
- Dùng `minProperties`, `maxProperties` và validation cho số entry; kiểm tra riêng quy tắc tên khóa.
- Kiểm tra schema sinh ra và serialize/deserialize thực tế trước khi công bố API.

`additionalProperties` là phần cốt lõi để mô tả object có khóa động trong OpenAPI. Khi kiểu generic, quy tắc khóa và schema giá trị được xác định rõ, client có thể xử lý map linh hoạt mà vẫn biết dữ liệu nào hợp lệ. Springdoc hỗ trợ suy luận phần lớn schema từ Java, còn ứng dụng cần thực thi các giới hạn và quy tắc mà hợp đồng đã công bố.

## Tài liệu tham khảo

- [OpenAPI Specification – Schema Object và `additionalProperties`](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@Schema`](https://docs.swagger.io/swagger-core/v2.2.46/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Jackson Databind – xử lý Map và JSON object](https://github.com/FasterXML/jackson-databind)
