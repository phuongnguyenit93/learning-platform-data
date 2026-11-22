# Constraint trên nested object và collection

## Mục tiêu học tập

Trong module **SPRING_REST_DOCS**, request API thường không chỉ chứa field phẳng. Một DTO có thể chứa object con, danh sách object, tập hợp mã định danh hoặc map. Ví dụ một đơn hàng có địa chỉ giao hàng lồng nhau và danh sách dòng sản phẩm. Các constraint đặt ở nhiều cấp phải được kiểm tra đúng để API từ chối dữ liệu sai.

Jakarta Bean Validation hỗ trợ **cascade validation** bằng @Valid và **container element constraints** để ràng buộc phần tử bên trong collection, map hoặc container được hỗ trợ. Spring REST Docs có thể giúp đưa mô tả constraint vào snippet, nhưng cần hiểu cách ánh xạ từ thuộc tính DTO sang field path JSON.

Sau bài này, bạn có thể:

- Phân biệt constraint trên object tham chiếu, object con và từng phần tử collection.
- Dùng @Valid để cascade validation vào nested object và phần tử collection.
- Kết hợp @NotNull, @NotEmpty, @Size, @Valid và constraint trên generic type.
- Ràng buộc key/value của Map và phần tử của List/Set.
- Hiểu property path của lỗi validation.
- Dùng ConstraintDescriptions cho từng class DTO và ánh xạ mô tả sang JSON field path trong REST Docs.
- Tránh giả định Spring REST Docs tự động đệ quy toàn bộ object graph.

## 1. Nested object và collection trong request

Ví dụ API tạo đơn hàng:

```json
{
  "customerId": 42,
  "shippingAddress": {
    "recipient": "An Nguyen",
    "street": "12 Nguyen Trai",
    "postalCode": "700000"
  },
  "items": [
    { "productId": 101, "quantity": 2 },
    { "productId": 205, "quantity": 1 }
  ],
  "notes": "Giao trong giờ hành chính"
}
```

| JSON path | Kiểu dữ liệu | Quy tắc ví dụ |
| --- | --- | --- |
| customerId | Number | Bắt buộc, dương |
| shippingAddress | Object | Bắt buộc và phải validate object con |
| shippingAddress.recipient | String | Không được blank |
| shippingAddress.postalCode | String | Theo định dạng mã bưu chính API quy định |
| items | Array | Bắt buộc, từ 1 đến 50 phần tử |
| items[].productId | Number | Bắt buộc, dương |
| items[].quantity | Number | Bắt buộc, từ 1 đến 100 |
| notes | String | Tùy chọn, tối đa 500 ký tự |

Một constraint đặt trên field cha không tự động kiểm tra mọi field con. Cần cấu hình cascade đúng nơi và khai báo constraint cho từng cấp.

## 2. @Valid và cascade validation

### 2.1. @Valid trên nested object

DTO địa chỉ:

```java
public class AddressInput {

    @NotBlank
    @Size(max = 120)
    private String street;

    @NotBlank
    @Size(max = 80)
    private String recipient;

    @NotBlank
    @Pattern(regexp = "^[0-9]{6}$")
    private String postalCode;

    // Getter/setter
}
```

DTO đơn hàng:

```java
public class CreateOrderRequest {

    @NotNull
    @Positive
    private Long customerId;

    @NotNull
    @Valid
    private AddressInput shippingAddress;
}
```

Hai annotation trên shippingAddress có nhiệm vụ khác nhau:

- @NotNull yêu cầu object địa chỉ phải được cung cấp.
- @Valid yêu cầu Validator tiếp tục kiểm tra constraint trên object AddressInput.

Nếu chỉ có @Valid, giá trị shippingAddress bằng null không làm cascade validation vào object con; không có object để kiểm tra. Nếu địa chỉ bắt buộc, kết hợp @NotNull và @Valid.

Nếu chỉ có @NotNull, object tham chiếu không được null nhưng constraint trên street, recipient và postalCode không nhất thiết được kiểm tra qua cascade.

### 2.2. @Valid không thay thế constraint trên object cha

@Valid là chỉ thị cascade validation, không có nghĩa object đó bắt buộc tồn tại. Nó cũng không tự kiểm tra object con có đủ field, giá trị dương hay đúng định dạng. Những điều kiện đó phải được khai báo trong AddressInput hoặc custom validator.

### 2.3. Cascade qua nhiều cấp

Validation có thể đi sâu qua nhiều object nếu từng thuộc tính tham chiếu được đánh dấu cascade:

```java
public class CustomerInput {

    @NotBlank
    private String name;

    @NotNull
    @Valid
    private ContactInput contact;
}

public class ContactInput {

    @NotBlank
    @Email
    private String email;
}

public class CreateCustomerRequest {

    @NotNull
    @Valid
    private CustomerInput customer;
}
```

Khi Validator kiểm tra CreateCustomerRequest, cascade đi qua customer rồi contact. Constraint ở từng DTO được áp dụng khi đường cascade tới object tương ứng.

Không mặc định mọi object field đều tự cascade. Hãy xác minh mỗi điểm đi vào object con có @Valid hoặc cơ chế cascade phù hợp.

## 3. Constraint trên collection và từng phần tử

### 3.1. Bắt buộc collection có phần tử

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<Long> productIds;
}
```

Ý nghĩa:

- @NotEmpty từ chối null và collection rỗng.
- @Size(max = 50) giới hạn tối đa 50 phần tử.

Nếu chỉ dùng @Size(max = 50), collection null vẫn có thể hợp lệ. Nếu chỉ dùng @NotNull, collection rỗng vẫn hợp lệ.

### 3.2. Ràng buộc từng phần tử bằng container element constraint

Jakarta Bean Validation hỗ trợ đặt constraint trực tiếp trên generic type:

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<@NotNull @Positive Long> productIds;
}
```

Ở đây:

- @NotEmpty và @Size áp dụng lên List.
- @NotNull và @Positive áp dụng lên từng phần tử Long.

Một list có ba phần tử nhưng phần tử thứ hai null sẽ vi phạm @NotNull. Giá trị 0 hoặc số âm vi phạm @Positive.

Đây là **container element constraint**, được hỗ trợ từ Bean Validation 2.0. Dự án phải dùng API/provider có hỗ trợ metadata này; cấu hình cũ chỉ hỗ trợ Bean Validation 1.1 sẽ không hiểu đầy đủ cú pháp này.

### 3.3. Cascade validation trên từng object trong List

Khi collection chứa DTO con, kết hợp @Valid trên type argument:

```java
public class OrderItemInput {

    @NotNull
    @Positive
    private Long productId;

    @NotNull
    @Min(1)
    @Max(100)
    private Integer quantity;
}

public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    private List<@NotNull @Valid OrderItemInput> items;
}
```

Các tầng kiểm tra:

1. List items không được null hoặc rỗng nhờ @NotEmpty.
2. List có tối đa 50 phần tử nhờ @Size.
3. Mỗi phần tử không null nhờ @NotNull trên type argument.
4. Với mỗi object khác null, @Valid cascade vào OrderItemInput.
5. productId và quantity được kiểm tra bởi constraint trong OrderItemInput.

Nếu quên @Valid trên type argument, constraint của OrderItemInput có thể không được cascade khi chỉ validate CreateOrderRequest.

## 4. Constraint trên Set, Collection và mảng

Container element constraint không chỉ áp dụng cho List:

```java
public class AssignRolesRequest {

    @NotEmpty
    @Size(max = 10)
    private Set<@NotBlank @Pattern(regexp = "^[A-Z_]+$") String> roles;
}
```

Set phải có từ một đến mười role; mỗi phần tử là chuỗi không blank và chỉ chứa chữ in hoa hoặc dấu gạch dưới.

Với mảng:

```java
public class BulkDeleteRequest {

    @NotNull
    @Size(min = 1, max = 100)
    private Long @Positive [] ids;
}
```

Cú pháp type-use trên mảng thể hiện constraint cho component type. Với cú pháp phức tạp, kiểm tra metadata của Validator và một bài test thực tế để xác nhận annotation được đọc ở đúng vị trí.

Constraint ở cấp collection và constraint ở cấp phần tử là hai cấp riêng. @Size trên list không kiểm tra từng phần tử; @NotBlank trên type argument không giới hạn số phần tử list.

## 5. Constraint trên Map: key và value

Jakarta Bean Validation cho phép đặt constraint trên key/value type argument của Map:

```java
public class UpdateSettingsRequest {

    @NotEmpty
    @Size(max = 30)
    private Map<
            @NotBlank @Pattern(regexp = "^[a-z][a-z0-9_.-]*$") String,
            @NotBlank @Size(max = 200) String
    > settings;
}
```

Trong ví dụ:

- Map phải có ít nhất một entry và tối đa 30 entry.
- Mỗi key không blank và phải đúng pattern.
- Mỗi value không blank và tối đa 200 ký tự.

Nếu value là object phức tạp:

```java
public class UpdatePreferencesRequest {

    @NotEmpty
    private Map<
            @NotBlank String,
            @NotNull @Valid PreferenceInput
    > preferences;
}
```

@Valid trên value type argument cascade validation vào từng PreferenceInput. Constraint trên key vẫn được kiểm tra riêng.

Khi tài liệu hóa Map thành JSON object, key động có thể không biểu diễn như field path cố định. Nên mô tả quy tắc key/value bằng đoạn giải thích hoặc snippet bổ sung, thay vì cố tạo descriptor cho từng key không biết trước.

## 6. Optional và container khác

Bean Validation có thể hỗ trợ value extraction cho container được provider hỗ trợ. Một trường hợp quen thuộc là Optional:

```java
public class SearchRequest {

    private Optional<@Size(min = 2, max = 40) String> keyword =
            Optional.empty();
}
```

Constraint trên type argument áp dụng cho giá trị bên trong container khi có giá trị được trích xuất. Cách xử lý phụ thuộc value extractor và provider. Không nên giả định mọi wrapper tùy chỉnh tự được hỗ trợ; có thể cần đăng ký ValueExtractor riêng.

Optional cũng không thay thế quy ước JSON của API. Jackson có thể deserialize field thiếu, null hoặc giá trị cụ thể theo cấu hình; hãy kiểm tra mapping thực tế trước khi viết tài liệu về tính bắt buộc/tùy chọn.

## 7. Kích hoạt validation trên HTTP endpoint

Khai báo constraint trên DTO mới chỉ tạo metadata. Để Spring MVC kiểm tra request body, controller thường kích hoạt validation bằng @Valid:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateOrderRequest request) {
        // Tạo đơn hàng
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Ứng dụng cần Bean Validation provider trên classpath. Khi request không hợp lệ, Spring MVC thường tạo lỗi validation (ví dụ MethodArgumentNotValidException trong cấu hình MVC thông dụng), sau đó exception handler quyết định response HTTP và body lỗi.

Một bài test tài liệu nên kiểm chứng cả hai hành vi:

- Request hợp lệ: endpoint xử lý thành công và snippet mô tả payload.
- Request không hợp lệ: endpoint trả lỗi như hợp đồng API quy định; test có thể tài liệu hóa cấu trúc lỗi.

Đừng suy luận response status/body chỉ từ annotation DTO. Kết quả còn phụ thuộc controller, validation activation và exception handling.

## 8. Property path của lỗi validation

Khi nested object hoặc collection có lỗi, Bean Validation tạo ConstraintViolation với property path thể hiện đường dẫn tới phần tử lỗi:

```java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);

for (ConstraintViolation<CreateOrderRequest> violation : violations) {
    System.out.println(violation.getPropertyPath());
    System.out.println(violation.getMessage());
}
```

Một số path có thể có dạng:

- shippingAddress.postalCode
- items[0].quantity
- items[1].productId
- preferences[theme].value

Đây là biểu diễn đường dẫn theo mô hình object/metadata validation. Chi tiết node, index hoặc key có thể khác theo loại container và provider.

### 8.1. Property path không phải JSON path tự động

Property path là đường dẫn theo mô hình object. JSON path là cách REST Docs định danh field trong payload JSON. Hai đường dẫn thường tương ứng nhưng không luôn giống nhau:

- Jackson có thể đổi tên field bằng @JsonProperty.
- DTO có thể được flatten hoặc chuyển đổi trước khi validate.
- Map key có thể là động.
- Một field Java có thể được serialize thành cấu trúc khác.

Khi tài liệu hóa, dùng tên field/path theo JSON thực tế trong descriptor REST Docs và giữ mapping rõ ràng với property path validation.

## 9. Tài liệu hóa nested field bằng Spring REST Docs

Spring REST Docs nhận field path JSON trong payload descriptor. Với nested DTO, cần mô tả đúng các field con.

Ví dụ:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng."),
    fieldWithPath("shippingAddress")
        .description("Thông tin địa chỉ giao hàng."),
    fieldWithPath("shippingAddress.recipient")
        .description("Người nhận."),
    fieldWithPath("shippingAddress.street")
        .description("Địa chỉ đường."),
    fieldWithPath("shippingAddress.postalCode")
        .description("Mã bưu chính."),
    fieldWithPath("items")
        .description("Danh sách sản phẩm."),
    fieldWithPath("items[].productId")
        .description("Mã sản phẩm."),
    fieldWithPath("items[].quantity")
        .description("Số lượng.")
)
```

REST Docs dùng field path để kiểm tra cấu trúc payload. Cú pháp wildcard/mảng cần phù hợp với payload và field path parser của REST Docs; hãy xác minh snippet từ test thay vì giả định mọi biểu thức JSONPath đều được chấp nhận.

### 9.1. ConstraintDescriptions cho nested class

ConstraintDescriptions lấy constraint cho property của class được truyền vào. Với nested object, truy vấn riêng class con:

```java
ConstraintDescriptions addressConstraints =
        new ConstraintDescriptions(AddressInput.class);

List<String> postalCodeRules =
        addressConstraints.descriptionsForProperty("postalCode");
```

Sau đó ánh xạ mô tả sang field path JSON:

```java
fieldWithPath("shippingAddress.postalCode")
        .description("Mã bưu chính. " +
                String.join(" ", postalCodeRules))
```

Tương tự với phần tử collection:

```java
ConstraintDescriptions itemConstraints =
        new ConstraintDescriptions(OrderItemInput.class);

List<String> quantityRules =
        itemConstraints.descriptionsForProperty("quantity");

fieldWithPath("items[].quantity")
        .description("Số lượng sản phẩm. " +
                String.join(" ", quantityRules))
```

ConstraintDescriptions không tự biết AddressInput được nhúng dưới shippingAddress hoặc OrderItemInput là phần tử của items. Ứng dụng tự ánh xạ property constraint sang JSON path.

### 9.2. Constraint trên phần tử generic

Container element constraint như List<@Positive Long> nằm trên type argument, không phải property annotation trực tiếp trên field productIds. ConstraintDescriptions mặc định tập trung vào **property constraints**; đừng giả định truy vấn descriptionsForProperty("productIds") sẽ tự trả về mọi constraint đặt trên generic element.

Các cách xử lý:

1. Ghi mô tả phần tử thủ công trong field descriptor, dựa trên DTO và test validation.
2. Tạo metadata helper riêng để đọc container element descriptor từ Bean Validation metadata API, sau đó chuyển thành mô tả.
3. Cài resolver/custom description flow phù hợp nếu muốn tự động hóa quy ước riêng.

Ví dụ descriptor thủ công:

```java
fieldWithPath("productIds")
        .description(
                "Danh sách ID; không rỗng, tối đa 50 phần tử. " +
                "Mỗi ID phải khác null và là số dương."
        )
```

Phần mô tả phải được kiểm chứng bằng test, không chỉ sao chép annotation mà không xác minh validator thực thi.

## 10. Test nested và collection constraint

Nên có test bao phủ từng cấp:

| Ca kiểm thử | Điều kiện | Kết quả validation mong đợi |
| --- | --- | --- |
| Thiếu address | shippingAddress = null | Vi phạm @NotNull trên field cha |
| Address có street rỗng | shippingAddress.street = "" | Vi phạm @NotBlank trong object con |
| Postal code sai | postalCode không khớp regex | Vi phạm @Pattern trong object con |
| Danh sách rỗng | items = [] | Vi phạm @NotEmpty |
| Danh sách quá dài | items có 51 phần tử | Vi phạm @Size(max=50) |
| Phần tử null | items chứa null | Vi phạm @NotNull trên type argument |
| Quantity bằng 0 | items[0].quantity = 0 | Vi phạm @Min(1) |
| Map key sai format | settings có key không khớp regex | Vi phạm constraint trên key |
| Map value blank | settings có value whitespace | Vi phạm @NotBlank trên value |

Ví dụ test Validator:

```java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);

assertThat(violations)
        .extracting(violation ->
                violation.getPropertyPath().toString())
        .contains("items[0].quantity");
```

Property path cụ thể phụ thuộc cấu trúc DTO và provider. Trong test dự án, xác minh path thực tế rồi dùng assertion ổn định phù hợp.

## 11. Giới hạn và lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Object con null nhưng không có lỗi | Chỉ có @Valid, thiếu @NotNull | Thêm @NotNull nếu object bắt buộc |
| Constraint nested DTO không chạy | Thiếu @Valid tại điểm cascade | Đánh dấu @Valid trên thuộc tính object con |
| List có phần tử sai nhưng không bị phát hiện | Thiếu @Valid trên type argument khi list chứa DTO | Dùng List<@Valid ItemInput> |
| List có phần tử null | Chưa đặt @NotNull trên type argument | Dùng List<@NotNull @Valid ItemInput> |
| Collection rỗng vẫn hợp lệ | Chỉ có @Size(max=...) hoặc @NotNull | Thêm @NotEmpty nếu phải có phần tử |
| ConstraintDescriptions không hiển thị constraint phần tử | Constraint nằm trên generic type, không phải property metadata mặc định | Mô tả thủ công hoặc đọc container element metadata riêng |
| Nested field không tìm được mô tả | Truy vấn class cha thay vì class con | Tạo ConstraintDescriptions cho nested DTO |
| JSON descriptor không khớp validation path | Jackson đổi tên/biến đổi payload hoặc parser path khác | Đối chiếu payload JSON và property path |
| Container element constraint không có hiệu lực | Bean Validation API/provider cũ | Dùng API/provider hỗ trợ Bean Validation 2.0+ |
| Validation không chạy ở HTTP endpoint | Controller thiếu @Valid hoặc thiếu provider | Kiểm tra controller, validation dependency và exception handling |
| Map key động không thể liệt kê thành field descriptor | Key do client gửi quyết định lúc chạy | Mô tả quy tắc key/value ở phần giải thích riêng |

## 12. Bài thực hành

1. Tạo AddressInput với recipient, street và postalCode.
2. Tạo OrderItemInput với productId và quantity.
3. Tạo CreateOrderRequest có shippingAddress và List items, áp dụng @NotNull, @Valid, @NotEmpty, @Size và container element constraints.
4. Viết test Validator cho nested object, list rỗng, phần tử null và quantity sai.
5. In property path của ConstraintViolation để quan sát đường dẫn tới field lỗi.
6. Viết MockMvc test tài liệu hóa request hợp lệ với field path cho shippingAddress và items.
7. Tạo ConstraintDescriptions riêng cho AddressInput và OrderItemInput; đưa mô tả postalCode/quantity vào field descriptor tương ứng.
8. Xác minh constraint generic của List bằng test thực tế; quyết định mô tả thủ công hay xây metadata helper.

**Câu hỏi tự đánh giá**

1. @Valid khác @NotNull như thế nào?
2. Vì sao @Valid cần đặt ở điểm bắt đầu cascade?
3. List<@NotNull @Valid ItemInput> kiểm tra những cấp nào?
4. @Size trên List giới hạn từng phần tử hay số lượng phần tử?
5. Constraint trên Map key khác constraint trên Map value ra sao?
6. Container element constraints yêu cầu thế hệ Bean Validation nào?
7. Vì sao property path của Validator không nhất thiết trùng JSON field path?
8. ConstraintDescriptions có tự đệ quy vào DTO con và generic element không?

## Tài liệu tham khảo chính thức

- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): cascade validation, container element constraints, value extraction và property path.
- [Jakarta Validation API — Valid](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/valid): đánh dấu cascade validation.
- [Jakarta Validation API — ConstraintViolation](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraintviolation): message, invalid value và property path.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp Validator với Spring.
- [Spring REST Docs — Documenting Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field descriptors và mô tả payload.
- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): ConstraintDescriptions và property constraints.

**Kết luận thực hành:** Đặt constraint ở đúng cấp dữ liệu: constraint object cha để kiểm tra tham chiếu, @Valid để cascade, container element constraint để kiểm tra từng phần tử hoặc key/value. Khi tạo tài liệu, truy vấn constraint cho từng DTO tương ứng và ánh xạ mô tả sang JSON field path thực tế. Test validation và REST Docs cùng xác minh hợp đồng request, nhưng property metadata không tự thay thế việc mô tả mọi nested/container rule.
