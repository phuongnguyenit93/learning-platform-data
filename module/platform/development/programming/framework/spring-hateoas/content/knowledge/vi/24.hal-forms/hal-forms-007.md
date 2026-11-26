# Required property

Trong HAL-FORMS, thuộc tính `required` cho biết client có cần cung cấp giá trị của một property khi gửi form hay không. Spring HATEOAS có thể suy ra metadata này từ kiểu input của affordance. Cách chuẩn để đánh dấu một property là bắt buộc là đặt Bean Validation `@NotNull` lên property tương ứng.

`required` là metadata hướng dẫn client tạo form và chuẩn bị request. Nó không tự thực thi validation ở server. Muốn từ chối request thiếu dữ liệu, controller vẫn cần dùng `@Valid` hoặc cơ chế validation tương ứng và khai báo ràng buộc trên input model.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của `required` trong HAL-FORMS template.
- Dùng `@NotNull` để tạo metadata `required: true`.
- Kết hợp `@NotBlank`, `@Email`, `@Pattern`, `@Min` và `@Max` để mô tả dữ liệu.
- Phân biệt metadata form với validation thực tế ở server.
- Hiểu vì sao property trong template dùng `PATCH` được xem là không bắt buộc.
- Thiết kế input model riêng cho `POST`, `PUT` và `PATCH`.
- Kiểm thử required property trong response `application/prs.hal-forms+json`.

## Required property trong HAL-FORMS là gì?

HAL-FORMS mô tả thao tác của API bằng các template trong `_templates`. Mỗi template có thể chứa danh sách `properties`. Một property mô tả trường client có thể hoặc cần gửi khi thực hiện thao tác.

```json
{
  "_templates": {
    "default": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        { "name": "reference", "required": true, "type": "text" },
        { "name": "deliveryAddress", "required": true, "type": "text" },
        { "name": "contactEmail", "type": "email" }
      ]
    }
  }
}
```

Trong ví dụ, `reference` và `deliveryAddress` được đánh dấu bắt buộc. `contactEmail` không có `required`, nên mặc định là không bắt buộc. `method` cho biết client gửi `POST`, còn `contentType` cho biết định dạng body mà endpoint nhận.

Theo HAL-FORMS, `required` mặc định là `false`. Spring HATEOAS thường bỏ thuộc tính có giá trị mặc định này khi serialize. Vì vậy, property không có `required` được hiểu là không bắt buộc; không nhất thiết phải có `"required": false` trong JSON.

## Spring HATEOAS suy ra required như thế nào?

Spring HATEOAS phân tích kiểu input được khai báo trong controller method mà affordance tham chiếu. Metadata Bean Validation trên các property được dùng để tạo mô tả form.

| Annotation hoặc quy tắc | Metadata HAL-FORMS liên quan |
|---|---|
| `@NotNull` | `required: true` |
| Không có ràng buộc bắt buộc | Mặc định `required: false`, thường được lược bỏ |
| Template dùng HTTP method `PATCH` | Tất cả property tự động được xem là không bắt buộc |
| `@Pattern` | `regex` |
| `@Min`, `@DecimalMin` | `min` |
| `@Max`, `@DecimalMax` | `max` |
| `@Size` | Metadata giới hạn `min` và `max` theo kiểu property |
| `@Email` | Có thể suy ra `type: email` |
| `@InputType` | Chỉ định rõ kiểu input khi cần |
| Property không có setter | Có thể được đánh dấu `readOnly: true` |

Đối với `required`, annotation cần chú ý là `@NotNull`. `@NotBlank` và `@NotEmpty` có ngữ nghĩa validation riêng. Nếu muốn Spring HATEOAS công bố rõ `required: true`, hãy khai báo thêm `@NotNull` thay vì dựa vào việc framework suy luận từ các annotation khác.

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

class CreateOrderInput {
    @NotNull
    @NotBlank
    private String reference;

    // getter và setter
}
```

`@NotNull` cung cấp metadata bắt buộc cho HAL-FORMS. `@NotBlank` bổ sung quy tắc từ chối chuỗi rỗng hoặc chỉ có khoảng trắng khi validation được thực thi.

## Khai báo input model cho thao tác tạo

Không nên dùng trực tiếp JPA entity làm request model. Hãy tạo một input model dành riêng cho API, chứa các trường client được phép gửi và các ràng buộc phù hợp.

```java
import java.time.LocalDate;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

class CreateOrderInput {
    @NotNull @NotBlank
    private String reference;

    @NotNull @NotBlank
    private String deliveryAddress;

    @NotNull
    private LocalDate requestedDate;

    @Email
    private String contactEmail;

    @Pattern(regexp = "[A-Z]{2}-[0-9]{6}")
    private String customerCode;

    public String getReference() { return reference; }
    public void setReference(String reference) { this.reference = reference; }
    public String getDeliveryAddress() { return deliveryAddress; }
    public void setDeliveryAddress(String deliveryAddress) { this.deliveryAddress = deliveryAddress; }
    public LocalDate getRequestedDate() { return requestedDate; }
    public void setRequestedDate(LocalDate requestedDate) { this.requestedDate = requestedDate; }
    public String getContactEmail() { return contactEmail; }
    public void setContactEmail(String contactEmail) { this.contactEmail = contactEmail; }
    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) { this.customerCode = customerCode; }
}
```

Metadata dự kiến:

| Property | Annotation | Metadata nổi bật |
|---|---|---|
| `reference` | `@NotNull`, `@NotBlank` | `required: true`, `type: text` |
| `deliveryAddress` | `@NotNull`, `@NotBlank` | `required: true`, `type: text` |
| `requestedDate` | `@NotNull` | `required: true`, `type: date` |
| `contactEmail` | `@Email` | `type: email`, không bắt buộc |
| `customerCode` | `@Pattern` | `regex`, không bắt buộc |

`@Email` và `@Pattern` mô tả định dạng khi giá trị được cung cấp; chúng không tự biến trường thành required. Property muốn bắt buộc cần có `@NotNull`.

## Gắn input model vào affordance

Spring HATEOAS lấy input model từ tham số có `@RequestBody` của controller method. Dùng `afford(methodOn(...))` để gắn mô tả thao tác tạo vào link collection:

```java
import java.util.List;
import jakarta.validation.Valid;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

record OrderView(long id, String reference, String status) {
}

interface OrderService {
    List<OrderView> findAll();
    OrderView create(CreateOrderInput input);
}

@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<OrderView> all() {
        Link self = linkTo(methodOn(OrderController.class).all())
            .withSelfRel()
            .andAffordance(afford(methodOn(OrderController.class).create(null)));

        return CollectionModel.of(orders.findAll(), self);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderView create(@Valid @RequestBody CreateOrderInput input) {
        return orders.create(input);
    }
}
```

`methodOn(OrderController.class).create(null)` là lời gọi proxy để Spring HATEOAS đọc chữ ký phương thức `create`. Nó không gọi controller thật và không tạo đơn hàng. Kiểu `CreateOrderInput` được dùng làm nguồn metadata property; `@NotNull` trên các trường giúp tạo `required: true`.

`@Valid` có vai trò khác: nó yêu cầu Spring chạy Bean Validation khi request `POST` được gửi. Cùng một input model vì thế vừa mô tả biểu mẫu cho client, vừa cung cấp quy tắc kiểm tra dữ liệu ở server.

Nếu endpoint khai báo `consumes = application/json`, HAL-FORMS có thể đưa `contentType: application/json` vào template. Nếu không khai báo `consumes`, thuộc tính này có thể không xuất hiện.

## Ví dụ response HAL-FORMS

Client yêu cầu biểu diễn HAL-FORMS bằng media type:

```http
GET /orders HTTP/1.1
Host: api.example.test
Accept: application/prs.hal-forms+json
```

Response minh họa:

```json
{
  "_links": {
    "self": { "href": "https://api.example.test/orders" }
  },
  "_embedded": {
    "orders": []
  },
  "_templates": {
    "default": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        { "name": "reference", "required": true, "type": "text" },
        { "name": "deliveryAddress", "required": true, "type": "text" },
        { "name": "requestedDate", "required": true, "type": "date" },
        { "name": "contactEmail", "type": "email" },
        { "name": "customerCode", "regex": "[A-Z]{2}-[0-9]{6}", "type": "text" }
      ]
    }
  }
}
```

Tên collection trong `_embedded` phụ thuộc relation của kiểu representation và cấu hình relation provider; `orders` ở đây là tên minh họa. Phần quan trọng là ba property có `@NotNull` được công bố `required: true`, còn hai property tùy chọn không có thuộc tính `required` vì giá trị mặc định là `false`.

Nếu chỉ có một affordance trong representation, HAL-FORMS thường đặt tên template là `default`. Khi có nhiều affordance, template được đặt tên theo tên affordance hoặc phương thức tương ứng, trừ khi tên được tùy chỉnh.

## Required property và validation ở server

Hai cơ chế này liên quan nhưng không đồng nhất:

| Cơ chế | Vai trò | Ví dụ |
|---|---|---|
| HAL-FORMS `required` | Hướng dẫn client trường nào cần nhập | `"required": true` |
| Bean Validation `@NotNull` | Kiểm tra giá trị không null ở server khi validation chạy | `@NotNull String reference` |
| `@Valid` trên `@RequestBody` | Kích hoạt kiểm tra các ràng buộc trên input object | `create(@Valid @RequestBody CreateOrderInput input)` |
| Logic nghiệp vụ | Kiểm tra điều kiện phụ thuộc trạng thái hoặc dữ liệu khác | Ngày giao không nằm trong quá khứ |

Nếu chỉ có metadata `required: true` mà endpoint không chạy validation, server vẫn có thể nhận dữ liệu thiếu. Ngược lại, server có thể validate dữ liệu dù client không hiển thị form HAL-FORMS. Vì vậy, không dùng metadata của form làm ranh giới bảo mật hoặc thay thế validation.

Để Bean Validation hoạt động trong Spring Boot, thêm starter validation phù hợp với phiên bản dự án:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Nếu ứng dụng tự quản lý dependency, cần có Jakarta Validation API và một validation provider tương thích.

## Phân biệt @NotNull, @NotBlank và @NotEmpty

Ba annotation có ý nghĩa khác nhau:

| Annotation | `null` | Chuỗi rỗng `""` | Chuỗi chỉ có khoảng trắng |
|---|---:|---:|---:|
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ |
| `@NotEmpty` | Không hợp lệ | Không hợp lệ | Hợp lệ |
| `@NotBlank` | Không hợp lệ | Không hợp lệ | Không hợp lệ |

Đối với một chuỗi bắt buộc và không được để trống, thường dùng cả `@NotNull` và `@NotBlank` nếu cần Spring HATEOAS công bố `required: true` dựa trên `@NotNull`, đồng thời server kiểm tra chuỗi trắng bằng `@NotBlank`.

Đối với collection hoặc chuỗi mà chỉ cần khác rỗng, `@NotEmpty` diễn đạt điều kiện validation đó. Tuy nhiên, nếu muốn metadata HAL-FORMS có `required: true`, hãy đặt thêm `@NotNull`.

Với trường số hoặc ngày, `@NotNull` thường là cách biểu đạt trường bắt buộc. Tránh dùng kiểu primitive như `int` hoặc `long` cho trường mà client có thể bỏ qua, vì primitive luôn có giá trị mặc định và không thể biểu diễn `null`. Dùng `Integer` hoặc `Long` nếu cần phân biệt trường không được gửi với giá trị `0`.

## PATCH tự động xem property là không bắt buộc

Một template dùng HTTP method `PATCH` được Spring HATEOAS xử lý đặc biệt: tất cả property trong template được xem là không bắt buộc. Đây là hành vi phù hợp với cập nhật từng phần, nơi client chỉ gửi những trường muốn thay đổi.

```java
class PatchOrderInput {
    private String deliveryAddress;
    private String deliveryNote;

    public String getDeliveryAddress() { return deliveryAddress; }
    public void setDeliveryAddress(String deliveryAddress) { this.deliveryAddress = deliveryAddress; }
    public String getDeliveryNote() { return deliveryNote; }
    public void setDeliveryNote(String deliveryNote) { this.deliveryNote = deliveryNote; }
}
```

Affordance cho `PATCH`:

```java
Link self = linkTo(methodOn(OrderController.class).one(id))
    .withSelfRel()
    .andAffordance(afford(methodOn(OrderController.class)
        .patch(null, id)));
```

Template HAL-FORMS tương ứng:

```json
{
  "_templates": {
    "patch": {
      "method": "patch",
      "properties": [
        { "name": "deliveryAddress", "type": "text" },
        { "name": "deliveryNote", "type": "text" }
      ]
    }
  }
}
```

Không có `required` nghĩa là false. Ngay cả khi input model của `PATCH` có `@NotNull`, Spring HATEOAS vẫn tự đánh dấu các property trong template PATCH là không bắt buộc. Điều đó không có nghĩa `@NotNull` bị vô hiệu hóa khi server chạy Bean Validation. Nếu field bị bỏ qua trong request và object sau deserialize vẫn có giá trị `null`, validation có thể thất bại.

Vì vậy, DTO cho `PATCH` thường nên tách riêng khỏi DTO `PUT` hoặc `POST`, không đặt ràng buộc `@NotNull` lên những field có thể không xuất hiện. Nếu cần phân biệt “không gửi field” với “gửi field có giá trị null”, hãy xác định rõ semantics cập nhật một phần và dùng kiểu dữ liệu/JSON binding phù hợp.

## PUT và POST thường dùng property bắt buộc

Với thao tác tạo (`POST`) hoặc thay thế toàn bộ representation (`PUT`), các trường bắt buộc thường được đánh dấu bằng `@NotNull` trên input model. Ví dụ template `PUT`:

```json
{
  "_templates": {
    "replace": {
      "method": "put",
      "properties": [
        { "name": "reference", "required": true, "type": "text" },
        { "name": "deliveryAddress", "required": true, "type": "text" },
        { "name": "deliveryNote", "type": "text" }
      ]
    }
  }
}
```

`PUT` thường thay thế toàn bộ biểu diễn nên các trường cần có phải được xác định rõ trong input model. Nếu API dùng semantics khác, hãy tài liệu hóa và đặt ràng buộc theo đúng hợp đồng thực tế; HTTP method không tự quyết định toàn bộ quy tắc nghiệp vụ.

## Property chỉ đọc và property bắt buộc

`required` và `readOnly` mô tả hai khía cạnh khác nhau:

- `required: true`: client phải cung cấp giá trị khi gửi template.
- `readOnly: true`: client không được chỉnh sửa property đó qua template.

Một property không nên vừa bắt buộc client gửi vừa chỉ đọc. Spring HATEOAS có thể suy ra `readOnly: true` khi property không có setter. Nếu muốn đánh dấu rõ bằng Jackson, dùng `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` trên field hoặc accessor phù hợp.

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotNull;

class OrderInputView {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @NotNull
    private String reference;

    public Long getId() { return id; }
    public String getReference() { return reference; }
    public void setReference(String reference) { this.reference = reference; }
}
```

`id` là trường server quản lý và được đánh dấu chỉ đọc; `reference` là trường client phải cung cấp nếu affordance sử dụng model này và không phải template PATCH. Trong thực tế, nên tách response model và request model để tránh đưa các trường server quản lý vào input payload.

## Tùy chỉnh kiểu và giới hạn property

Required chỉ là một trong các metadata của property. Có thể kết hợp các annotation khác để mô tả định dạng hoặc phạm vi giá trị:

```java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

class PaymentInput {
    @NotNull
    @DecimalMin("1.00")
    @DecimalMax("500000.00")
    private java.math.BigDecimal amount;

    @NotNull
    @Pattern(regexp = "VND|USD|EUR")
    private String currency;

    public java.math.BigDecimal getAmount() { return amount; }
    public void setAmount(java.math.BigDecimal amount) { this.amount = amount; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
}
```

HAL-FORMS có thể mô tả `amount` bằng `required`, `min`, `max` và kiểu số phù hợp; `currency` có thể có `required` và `regex`. `@Pattern` mô tả biểu thức khớp, nhưng nếu client cần danh sách lựa chọn có thể chọn, hãy cân nhắc `options` thay vì chỉ cung cấp regex.

Đối với kiểu dữ liệu riêng không thể gắn annotation trực tiếp, `HalFormsConfiguration` cho phép đăng ký pattern cho kiểu đó. Ví dụ API hiện tại cung cấp `withPattern(Class<?>, String)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsConfiguration;

@Configuration
class HalFormsMetadataConfiguration {
    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        return new HalFormsConfiguration()
            .withPattern(CustomerCode.class, "[A-Z]{2}-[0-9]{6}");
    }
}
```

Trong ví dụ, `CustomerCode` là kiểu value object do ứng dụng định nghĩa. Khi kiểu này xuất hiện trong input model, metadata property có thể nhận `regex` từ cấu hình. Cách tùy chỉnh cụ thể phụ thuộc phiên bản Spring HATEOAS và media type configuration đang dùng.

## Kiểm thử required property trong HAL-FORMS

Kiểm thử endpoint nên xác nhận media type và property bắt buộc thực sự xuất hiện với `required: true`. Ví dụ dưới đây giả định controller có endpoint danh sách gắn affordance `create` như phần trước:

```java
import static org.hamcrest.Matchers.contains;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(HalFormsTestConfiguration.class)
class OrderRequiredPropertyTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void exposesRequiredPropertiesInHalFormsTemplate() throws Exception {
        given(orders.findAll()).willReturn(List.of());

        mockMvc.perform(get("/orders").accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
            .andExpect(jsonPath(
                "$._templates.default.properties[?(@.name == 'reference')].required"
            ).value(contains(true)))
            .andExpect(jsonPath(
                "$._templates.default.properties[?(@.name == 'deliveryAddress')].required"
            ).value(contains(true)));
    }
}

@TestConfiguration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HalFormsTestConfiguration {
}
```

Trong ví dụ, `HalFormsTestConfiguration` bật message conversion cho HAL-FORMS trong test slice. Ở ứng dụng Spring Boot, hãy dùng auto-configuration nếu đã cấu hình sẵn media type; nếu tự quản lý hypermedia, có thể bật `@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)` ở cấu hình ứng dụng.

Nên kiểm thử thêm:

- Property có `@NotNull` được xuất với `required: true` trong template `POST` hoặc `PUT`.
- Property không có `@NotNull` được lược bỏ thuộc tính `required`.
- Template `PATCH` không công bố property nào là bắt buộc.
- `@Valid` thực sự từ chối request thiếu trường bắt buộc.
- Property có `@JsonProperty(Access.READ_ONLY)` không bị trình bày như trường client cần nhập.
- Validation constraint và metadata `regex`, `min`, `max`, `type` nhất quán.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ dùng `@NotBlank` và kỳ vọng chắc chắn có `required: true` | Metadata bắt buộc có thể không được suy ra như mong muốn | Thêm `@NotNull` để công bố required rõ ràng |
| Nghĩ `required: true` tự validate request | Server vẫn có thể nhận dữ liệu thiếu | Dùng `@Valid` và Bean Validation trên input model |
| Đánh dấu tất cả property của PATCH là bắt buộc | Client không thể cập nhật từng phần theo đúng ý nghĩa | Dùng input model PATCH riêng và để property tùy chọn |
| Đưa `@NotNull` vào DTO PATCH cho trường có thể bỏ qua | Validation có thể từ chối request thiếu trường | Chỉ đặt ràng buộc phù hợp với semantics PATCH |
| Dùng primitive cho trường có thể không gửi | Không phân biệt được trường bị bỏ qua và giá trị mặc định | Dùng wrapper như `Integer`, `Long` hoặc kiểu nullable phù hợp |
| Không khai báo `consumes` nhưng kỳ vọng `contentType` cụ thể | Template có thể không có `contentType` | Khai báo `consumes` hoặc metadata media type cho affordance |
| Dùng entity làm input model | Lộ trường nội bộ và trộn request với persistence | Tạo DTO/input model riêng cho API |
| Coi property không có `required` là lỗi serialize | Hiểu sai giá trị mặc định HAL-FORMS | `required` mặc định false nên thường được lược bỏ |

## Ghi nhớ

Trong Spring HATEOAS, `@NotNull` trên property của input model là cách chuẩn để tạo metadata `required: true` trong HAL-FORMS. `@NotBlank`, `@Email`, `@Pattern`, `@Min`, `@Max` và các ràng buộc khác bổ sung quy tắc hoặc kiểu dữ liệu, nhưng không thay thế `@NotNull` khi cần đánh dấu trường bắt buộc. Metadata chỉ hướng dẫn client; `@Valid` và Bean Validation mới kiểm tra request ở server. Các template `PATCH` tự động xem tất cả property là không bắt buộc, vì vậy nên dùng input model riêng cho cập nhật từng phần và tránh ràng buộc `@NotNull` trên trường có thể bị bỏ qua.

## Tài liệu tham khảo

- [Spring HATEOAS – Defining HAL-FORMS metadata](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [HalFormsConfiguration API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsConfiguration.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
