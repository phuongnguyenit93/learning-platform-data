# HAL-FORMS media type

HAL-FORMS là một hypermedia media type mở rộng cách biểu diễn HAL bằng khả năng mô tả các thao tác có thể thực hiện tại runtime. Ngoài dữ liệu tài nguyên, link và embedded resource, một tài liệu HAL-FORMS có thể chứa mục `_templates` để công bố các mẫu thao tác. Mỗi template mô tả HTTP method, target, content type và những property mà client gửi khi thực hiện thao tác.

Trong Spring HATEOAS, media type này có định danh `application/prs.hal-forms+json`. Client yêu cầu nó qua HTTP header `Accept`; server trả representation với `Content-Type` tương ứng. Các template được tạo từ affordance gắn trên link và metadata của input model. Nhờ vậy, client có thể khám phá cách tạo hoặc cập nhật tài nguyên mà không cần tự suy ra mọi endpoint và trường request từ mã nguồn.

Bài học này tập trung vào hợp đồng ở mức HTTP và JSON: định danh media type, content negotiation, cấu trúc tài liệu, ý nghĩa `_templates`, cấu hình Spring HATEOAS, cách controller công bố affordance, metadata của property, options, quốc tế hóa và kiểm thử representation được serialize.

Sau bài học, bạn có thể:

- Nhận diện định danh `application/prs.hal-forms+json` và phân biệt nó với `application/hal+json`.
- Phân biệt vai trò của `Accept`, `Content-Type` response và `contentType` trong một template.
- Đọc cấu trúc HAL-FORMS gồm dữ liệu tài nguyên, `_links` và `_templates`.
- Giải thích các thuộc tính `method`, `target`, `contentType`, `title` và `properties`.
- Kích hoạt HAL-FORMS trong Spring HATEOAS.
- Gắn affordance vào link controller để tạo template.
- Hiểu cách input model và validation annotation tạo property metadata.
- Cấu hình options, prompt, placeholder và template title.
- Kiểm thử media type, template và request được mô tả bằng MockMvc.

## 1. Định danh của HAL-FORMS

Định danh media type mà HAL-FORMS sử dụng là:

~~~http
application/prs.hal-forms+json
~~~

Spring HATEOAS cung cấp các hằng số tương ứng trong `MediaTypes`:

~~~java
MediaTypes.HAL_FORMS_JSON
MediaTypes.HAL_FORMS_JSON_VALUE
~~~

`HAL_FORMS_JSON` có kiểu `org.springframework.http.MediaType`; `HAL_FORMS_JSON_VALUE` là chuỗi tương ứng, tiện dùng trong annotation hoặc cấu hình.

~~~java
import org.springframework.hateoas.MediaTypes;
~~~

Ví dụ dùng trong kiểm thử:

~~~java
mvc.perform(get("/customers")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_FORMS_JSON
    ));
~~~

Phần `+json` cho biết cú pháp biểu diễn dựa trên JSON. Tuy nhiên, không nên chỉ xem HAL-FORMS là JSON thông thường có thêm một vài trường tùy ý. Các tên dành riêng như `_links` và `_templates` có ngữ nghĩa theo media type, và client cần hiểu các quy tắc đó để điều hướng cũng như gửi request đúng cách.

### 1.1. HAL-FORMS và HAL là hai media type khác nhau

HAL dùng định danh:

~~~http
application/hal+json
~~~

HAL-FORMS dùng:

~~~http
application/prs.hal-forms+json
~~~

HAL tập trung vào resource, link relation và embedded resource. HAL-FORMS giữ cách biểu diễn tài nguyên tương tự HAL, đồng thời thêm `_templates` để mô tả thao tác có thể gửi.

Hai media type có hình thức gần nhau nhưng không thể dùng thay thế tùy ý. Client yêu cầu HAL không được mặc định rằng response sẽ chứa form template. Client yêu cầu HAL-FORMS cần biết cách đọc `_templates`, xác định method và properties rồi gửi request theo template.

| Khả năng | HAL | HAL-FORMS |
|---|---|---|
| Dữ liệu tài nguyên | Có | Có |
| `_links` | Có | Có |
| `_embedded` | Có | Có |
| `_templates` | Không thuộc cấu trúc HAL cơ bản | Có |
| Mô tả HTTP method của thao tác | Không qua form template | Có |
| Mô tả input properties | Không qua form template | Có |
| Client cần hỗ trợ | HAL | HAL-FORMS |

HAL-FORMS không thay thế link. Template thường được gắn với một link và mở rộng ý nghĩa của thao tác mà client có thể thực hiện tại target đó.

## 2. Content negotiation qua HTTP

Media type được chọn thông qua cơ chế content negotiation của HTTP. Client dùng `Accept` để cho server biết loại representation mà nó muốn nhận.

Yêu cầu một tài liệu HAL-FORMS:

~~~http
GET /customers HTTP/1.1
Host: api.example.com
Accept: application/prs.hal-forms+json
~~~

Nếu server hỗ trợ và chọn HAL-FORMS, response có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
~~~

Khi client yêu cầu HAL:

~~~http
GET /customers HTTP/1.1
Host: api.example.com
Accept: application/hal+json
~~~

server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

### 2.1. Phân biệt Accept và Content-Type

Ba vị trí sau có ý nghĩa khác nhau:

| Header hoặc thuộc tính | Hướng dữ liệu | Ý nghĩa |
|---|---|---|
| `Accept` | Client gửi đến server | Client muốn nhận representation nào |
| `Content-Type` của response | Server gửi đến client | Media type thực tế của representation |
| `contentType` trong `_templates` | Metadata do server công bố | Media type mà client cần gửi khi submit template |

Ví dụ, client đọc collection dưới dạng HAL-FORMS nhưng template tạo khách hàng yêu cầu JSON:

~~~http
GET /customers
Accept: application/prs.hal-forms+json
~~~

Response có thể chứa:

~~~json
{
  "_templates": {
    "default": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "name",
          "required": true
        }
      ]
    }
  }
}
~~~

Khi submit template, client gửi request body bằng JSON:

~~~http
POST /customers
Content-Type: application/json
Accept: application/hal+json
~~~

`Content-Type` của request POST được hướng dẫn bởi `contentType` trong template. Nó không phải `application/prs.hal-forms+json`, vì client đang gửi payload tạo khách hàng chứ không gửi lại tài liệu mô tả form.

### 2.2. Không nhầm contentType của template với produces

`@RequestMapping(consumes = "...")` mô tả media type mà endpoint chấp nhận làm request body. Thông tin này có thể được đưa vào thuộc tính `contentType` của template.

`produces` mô tả media type mà endpoint có thể trả về. `Accept` của client tham gia chọn representation response. Hai cơ chế này có vai trò riêng:

~~~java
@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
public EntityModel<CustomerRepresentation> create(
        @RequestBody CreateCustomerRequest request) {
    // ...
}
~~~

Các import cho ví dụ:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
~~~

Trong ví dụ, JSON là định dạng request body. HAL JSON là định dạng response được endpoint công bố. Một request GET khác có thể yêu cầu representation HAL-FORMS để khám phá template POST.

## 3. Cấu trúc tài liệu HAL-FORMS

Một tài liệu HAL-FORMS có thể chứa ba nhóm thành phần:

1. Các thuộc tính dữ liệu của tài nguyên.
2. `_links` chứa các link relation và href.
3. `_templates` chứa các template thao tác.

Ví dụ:

~~~json
{
  "id": "42",
  "firstName": "Frodo",
  "lastName": "Baggins",
  "role": "ring bearer",
  "_links": {
    "self": {
      "href": "https://api.example.com/employees/42"
    },
    "employees": {
      "href": "https://api.example.com/employees"
    }
  },
  "_templates": {
    "default": {
      "method": "put",
      "properties": [
        {
          "name": "firstName",
          "required": true
        },
        {
          "name": "lastName",
          "required": true
        },
        {
          "name": "role",
          "required": true
        }
      ]
    },
    "partiallyUpdateEmployee": {
      "method": "patch",
      "properties": [
        {
          "name": "firstName"
        },
        {
          "name": "lastName"
        },
        {
          "name": "role"
        }
      ]
    }
  }
}
~~~

Trong tài liệu này:

- Dữ liệu ở cấp cao nhất mô tả employee hiện tại.
- `self` trỏ đến employee.
- `employees` trỏ đến collection.
- `default` mô tả thao tác PUT thay thế employee.
- `partiallyUpdateEmployee` mô tả thao tác PATCH.

Client có thể dùng dữ liệu hiện tại để điền trước các trường, dùng `self` làm target khi template không chỉ định target riêng, rồi gửi request theo method được mô tả.

### 3.1. _links vẫn giữ ngữ nghĩa HAL

HAL-FORMS không loại bỏ link relation. `_links` vẫn là nơi công bố quan hệ điều hướng giữa tài nguyên hiện tại và các tài nguyên liên quan.

Ví dụ:

~~~json
"_links": {
  "self": {
    "href": "/employees/42"
  },
  "employees": {
    "href": "/employees"
  }
}
~~~

Link `self` có thể mang affordance PUT và PATCH. Link `employees` có thể mang affordance POST để tạo employee mới. Client cần đọc relation và href thay vì tự ghép URL từ ID hoặc tên controller.

### 3.2. _templates là một map theo tên thao tác

`_templates` là một object JSON, trong đó mỗi key là tên template và value là mô tả form.

Nếu chỉ có một template, tên được dùng là `default` theo quy ước của HAL-FORMS. Khi có nhiều affordance, các template có thể được đặt tên theo tên affordance hoặc tên phương thức được trỏ tới. Có thể đặt tên rõ ràng trong quá trình xây affordance để client có một định danh ổn định.

Ví dụ:

~~~json
"_templates": {
  "default": {
    "method": "post",
    "properties": []
  },
  "cancelOrder": {
    "method": "post",
    "properties": []
  }
}
~~~

Tên template không phải HTTP method và cũng không phải link relation. Nó định danh một mẫu thao tác trong tài liệu.

## 4. Các thuộc tính của template

Một template HAL-FORMS có thể chứa các thuộc tính sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| `method` | HTTP method dùng khi submit template |
| `target` | URI nhận request |
| `contentType` | Media type của request body |
| `title` | Tiêu đề hiển thị cho template |
| `properties` | Danh sách trường mà client gửi |

### 4.1. method

`method` cho biết client cần dùng HTTP method nào khi thực hiện thao tác.

Ví dụ:

~~~json
{
  "method": "put",
  "properties": []
}
~~~

Giá trị này thường được suy ra từ mapping của controller method, chẳng hạn `@PostMapping`, `@PutMapping`, `@PatchMapping` hoặc `@DeleteMapping`.

Client không nên tự thay method bằng một giá trị khác vì nó có thể làm thay đổi ngữ nghĩa thao tác và không còn khớp với endpoint.

### 4.2. target

`target` cho biết URI mà client gửi form đến. Nếu target của affordance giống link mà affordance được gắn vào, thuộc tính này có thể được lược bỏ. Khi đó client dùng href của link.

Nếu affordance trỏ đến một URI khác, `target` được đưa vào template để chỉ rõ địa chỉ submit.

Ví dụ:

~~~json
{
  "method": "post",
  "target": "/orders/42/cancellation",
  "properties": []
}
~~~

Điều này cho phép một representation đơn hàng công bố thao tác hủy ở endpoint riêng, trong khi link self của đơn hàng vẫn trỏ đến `/orders/42`.

### 4.3. contentType

`contentType` cho biết media type mà server mong đợi trong request body khi client submit template.

Thuộc tính này được đưa vào khi controller method có khai báo `consumes`, hoặc media type đầu vào được cấu hình tường minh khi xây affordance.

Ví dụ:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public EntityModel<CustomerRepresentation> create(
        @RequestBody CreateCustomerRequest request) {
    // ...
}
~~~

Template được tạo từ method này có thể chứa:

~~~json
{
  "method": "post",
  "contentType": "application/json"
}
~~~

Nếu endpoint không khai báo `consumes` và affordance cũng không cấu hình media type đầu vào tường minh, template có thể không có thuộc tính `contentType`. Client khi đó phải tuân theo hợp đồng endpoint hoặc metadata khác được công bố.

### 4.4. title

`title` là tên thân thiện với người dùng, có thể được client hiển thị khi tạo giao diện. Giá trị có thể được khai báo thông qua resource bundle `rest-messages`.

Ví dụ:

~~~json
{
  "title": "Create customer",
  "method": "post",
  "properties": []
}
~~~

Title không thay thế tên template. Tên template là key trong `_templates`; title là nhãn dành cho người dùng.

### 4.5. properties

`properties` là danh sách trường client có thể gửi khi submit template. Mỗi phần tử mô tả một property của input model.

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "email",
      "required": true,
      "type": "email"
    },
    {
      "name": "displayName",
      "required": true,
      "type": "text"
    }
  ]
}
~~~

Tên property phải khớp với hợp đồng request mà endpoint nhận. Client dùng metadata này để xây dựng dữ liệu gửi đi. Server vẫn phải xác thực request độc lập.

## 5. Metadata của property

Spring HATEOAS có thể tạo property metadata từ kiểu Java, validation annotation, Jackson annotation và cấu hình HAL-FORMS.

Các thuộc tính thường gặp:

| Metadata | Ý nghĩa | Nguồn có thể dùng trong Spring HATEOAS |
|---|---|---|
| `name` | Tên property | Tên thuộc tính input model |
| `readOnly` | Trường chỉ đọc | Không có setter hoặc Jackson `READ_ONLY` |
| `regex` | Mẫu định dạng | `@Pattern` |
| `required` | Trường bắt buộc | `@NotNull` |
| `min`, `max` | Giới hạn giá trị | `@Size`, `@Range`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax` |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi | Hibernate Validator `@Length` |
| `options` | Danh sách lựa chọn | `HalFormsConfiguration` |
| `prompt` | Nhãn hoặc hướng dẫn | Resource bundle `rest-messages` |
| `placeholder` | Ví dụ định dạng | Resource bundle `rest-messages` |
| `type` | Kiểu control đầu vào | `@InputType`, validation annotation hoặc kiểu Java |

Một số thuộc tính có giá trị mặc định theo đặc tả nên được lược bỏ khi serialize. Ví dụ, `required` mặc định là `false`; Spring HATEOAS không cần phát ra `required: false` trong mọi property. Với template PATCH, các property được xem là không bắt buộc theo cách diễn giải của template.

### 5.1. readOnly

`readOnly` cho biết property không nên được client gửi như một giá trị có thể chỉnh sửa. Spring HATEOAS có thể nhận biết thuộc tính không có setter. Có thể dùng Jackson `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` để đánh dấu tường minh.

Ví dụ:

~~~java
public class CustomerInput {

    private UUID id;
    private String name;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Import:

~~~java
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonProperty;
~~~

Không nên đưa trường server quản lý như ID, thời điểm tạo hoặc trạng thái nội bộ vào request model chỉ để hiển thị chúng trong form. Tốt hơn là tách input model khỏi response representation.

### 5.2. required và validation

Spring HATEOAS có thể suy ra `required` từ `@NotNull`.

~~~java
public class CreateCustomerRequest {

    @NotNull
    private String name;

    @NotNull
    @Email
    private String email;

    // getters and setters
}
~~~

Import validation:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
~~~

Template có thể mô tả:

~~~json
{
  "name": "email",
  "required": true,
  "type": "email"
}
~~~

Metadata giúp client kiểm tra sơ bộ trước khi gửi request. Nó không thay thế Bean Validation, kiểm tra quyền hoặc quy tắc nghiệp vụ ở server.

### 5.3. regex và giới hạn

`@Pattern` có thể cung cấp `regex`:

~~~java
@Pattern(regexp = "[A-Z]{2}[0-9]{6}")
private String customerCode;
~~~

Import:

~~~java
import jakarta.validation.constraints.Pattern;
~~~

Các giới hạn số hoặc kích thước có thể được suy ra từ annotation validation tương ứng. Ví dụ `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Size` hoặc Hibernate Validator `@Range`.

Với chuỗi, Hibernate Validator `@Length` có thể cung cấp `minLength` và `maxLength`. Hãy kiểm tra metadata thực tế được serialize theo phiên bản validation provider mà ứng dụng sử dụng.

### 5.4. type và @InputType

Kiểu input có thể được suy ra từ kiểu Java hoặc validation annotation. Ví dụ `String` thường trở thành `text`, `LocalDate` có thể trở thành `date`, còn `@Email` có thể được diễn giải thành kiểu `email`.

Khi cần chỉ định rõ kiểu control, dùng `@InputType`:

~~~java
@InputType("email")
private String email;
~~~

Import:

~~~java
import org.springframework.hateoas.InputType;
~~~

`@InputType` cho phép ghi đè kiểu được suy ra tự động. Giá trị này hướng dẫn client cách hiển thị input; nó không thay đổi kiểu Java và cũng không thay thế validation.

## 6. Tạo template từ affordance của controller

Trong Spring HATEOAS, template HAL-FORMS thường được tạo từ affordance gắn vào link. Affordance mô tả một thao tác mà endpoint hỗ trợ. Khi serialize bằng HAL-FORMS, affordance được chuyển thành template.

Ví dụ controller quản lý khách hàng:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;
    private final CustomerModelAssembler assembler;

    public CustomerController(
            CustomerService service,
            CustomerModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<CustomerRepresentation>> all() {

        var customers = service.findAll().stream()
            .map(assembler::toModel)
            .toList();

        Link self = linkTo(methodOn(CustomerController.class).all())
            .withSelfRel()
            .andAffordance(
                afford(methodOn(CustomerController.class).create(null))
            );

        return CollectionModel.of(customers, self);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public EntityModel<CustomerRepresentation> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        return assembler.toModel(service.create(request));
    }
}
~~~

Trong ví dụ:

- `GET /customers` trả về collection.
- Link self của collection được tạo từ mapping `all()`.
- `andAffordance(...)` gắn thao tác tạo khách hàng vào link self.
- `create(...)` được ánh xạ bằng POST.
- `@RequestBody` cho Spring HATEOAS biết kiểu input model.
- `consumes` cung cấp media type của request body.

Lời gọi `methodOn(...).create(null)` chỉ mô tả phương thức controller cho link builder; nó không gọi logic tạo khách hàng.

Các import chính:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 6.1. Tách input model khỏi response model

Input model định nghĩa dữ liệu client được phép gửi:

~~~java
public class CreateCustomerRequest {

    @NotNull
    @Size(min = 2, max = 80)
    private String name;

    @NotNull
    @Email
    private String email;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Response representation có thể có cấu trúc khác:

~~~java
public record CustomerRepresentation(
    UUID id,
    String name,
    String email,
    String status
) {}
~~~

Import validation và định danh:

~~~java
import java.util.UUID;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

Tách hai kiểu giúp template chỉ công bố các trường request hợp lệ. ID và trạng thái do server quản lý không cần xuất hiện trong form tạo mới.

### 6.2. Một link có thể mang nhiều affordance

Một representation employee có thể gắn PUT và PATCH vào link self:

~~~java
Link self = linkTo(
    methodOn(EmployeeController.class).one(id)
).withSelfRel()
 .andAffordance(
    afford(methodOn(EmployeeController.class).update(null, id))
 )
 .andAffordance(
    afford(methodOn(EmployeeController.class).partiallyUpdate(null, id))
 );
~~~

Khi trả HAL-FORMS, mỗi affordance có thể trở thành một template riêng. Client có thể chọn template PUT để thay thế tài nguyên hoặc PATCH để cập nhật một phần.

Nếu cần tên thao tác ổn định, hãy đặt tên affordance tường minh trong quá trình xây dựng thay vì phụ thuộc hoàn toàn vào tên method Java.

## 7. Cấu hình HAL-FORMS trong Spring HATEOAS

Với Spring MVC, kích hoạt HAL-FORMS bằng `@EnableHypermediaSupport`:

~~~java
@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL_FORMS
)
public class HypermediaConfiguration {
}
~~~

Import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
~~~

Annotation này đăng ký hạ tầng cần thiết để serialize representation model theo media type được chọn, bao gồm các Jackson module và hỗ trợ link discovery tương ứng khi dependency cần thiết có trên classpath.

Trong ứng dụng Spring Boot, hãy kiểm tra cấu hình hypermedia hiện có trước khi thêm cấu hình khác. Tránh đăng ký lặp các converter hoặc module không cần thiết.

### 7.1. MediaTypes và converter

Spring HATEOAS có các thành phần liên quan:

- `MediaTypes.HAL_FORMS_JSON` và `HAL_FORMS_JSON_VALUE`: định danh media type.
- `HalFormsJacksonModule`: serialize và deserialize các thành phần HAL-FORMS.
- `HalFormsHttpMessageConverter`: converter HTTP cho HAL-FORMS.
- `HalFormsLinkDiscoverer`: tìm link trong tài liệu HAL-FORMS.
- `HalFormsConfiguration`: tùy chỉnh metadata và options.

Converter HAL-FORMS kiểm tra representation được trả về. Nếu không có template nào được đăng ký, nó có thể chuyển media type được render về HAL JSON. Vì vậy, chỉ bật HAL-FORMS hoặc gửi `Accept` HAL-FORMS không bảo đảm mọi response đều có `_templates`; representation cần có affordance để tạo template.

### 7.2. Không ép produces nếu muốn content negotiation

Nếu muốn endpoint hỗ trợ nhiều dạng representation, hãy để `Accept` tham gia chọn media type. Việc cố định `produces` vào một media type duy nhất có thể khiến client không yêu cầu được dạng khác.

Ví dụ client HAL-FORMS:

~~~http
GET /customers
Accept: application/prs.hal-forms+json
~~~

Client HAL:

~~~http
GET /customers
Accept: application/hal+json
~~~

Cấu hình converter và hypermedia support quyết định representation nào có thể được trả về.

## 8. Options cho property

Một property có tập giá trị hợp lệ có thể công bố `options`. Ví dụ, đơn hàng chỉ cho phép hai phương thức giao hàng: STANDARD và EXPRESS.

Cấu hình:

~~~java
@Configuration
public class HalFormsOptionsConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {

        HalFormsConfiguration configuration =
            new HalFormsConfiguration();

        configuration.withOptions(
            CreateOrderRequest.class,
            "shippingMethod",
            metadata -> HalFormsOptions.inline("STANDARD", "EXPRESS")
        );

        return configuration;
    }
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsConfiguration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsOptions;
~~~

Options inline có thể được serialize thành một cấu trúc tương tự:

~~~json
{
  "name": "shippingMethod",
  "type": "text",
  "options": {
    "inline": [
      "STANDARD",
      "EXPRESS"
    ]
  }
}
~~~

### 8.1. Options từ một tài nguyên từ xa

Khi danh sách lựa chọn thay đổi theo dữ liệu, có thể tham chiếu đến một resource chứa các lựa chọn:

~~~java
configuration.withOptions(
    CreateOrderRequest.class,
    "shippingMethod",
    metadata -> HalFormsOptions.remote(
        Link.of("/shipping-methods")
    )
);
~~~

Import:

~~~java
import org.springframework.hateoas.Link;
~~~

Client có thể đọc nguồn options để lấy danh sách giá trị và nhãn. Cấu trúc dữ liệu của resource options cần tuân theo quy ước mà client HAL-FORMS hỗ trợ.

Options giúp client hiển thị lựa chọn hợp lệ, nhưng server vẫn phải kiểm tra giá trị được gửi có hợp lệ trong ngữ cảnh request hiện tại hay không.

## 9. Quốc tế hóa title, prompt và placeholder

Một số thuộc tính HAL-FORMS được thiết kế để hiển thị cho người dùng. Spring HATEOAS hỗ trợ resource bundle `rest-messages` để định nghĩa và quốc tế hóa các giá trị này.

### 9.1. Template title

Có thể đặt title cho template theo key:

~~~properties
_templates.default.title=Create customer
_templates.createCustomer.title=Create customer
~~~

Nếu chỉ có một template, tên template là `default`. Nếu có nhiều template, key có thể sử dụng tên affordance. Key theo tên affordance được ưu tiên khi khớp.

### 9.2. Property prompt và placeholder

Ví dụ:

~~~properties
CreateCustomerRequest.name._prompt=Customer name
CreateCustomerRequest.email._prompt=Email address
CreateCustomerRequest.email._placeholder=name@example.com
~~~

`_prompt` cung cấp nhãn hoặc hướng dẫn cho field; `_placeholder` cung cấp ví dụ định dạng. Có thể định nghĩa key toàn cục, theo tên kiểu hoặc theo tên kiểu đầy đủ.

Nếu request có `Accept-Language`, Spring có thể chọn thông điệp theo locale đã cấu hình. Khi cache response theo ngôn ngữ, cần tính đến header này để không trả nhầm prompt hoặc title.

## 10. Luồng trao đổi giữa client và server

Một client HAL-FORMS thường thực hiện các bước sau:

1. Gửi GET với `Accept: application/prs.hal-forms+json`.
2. Đọc dữ liệu tài nguyên và `_links`.
3. Đọc `_templates` để tìm thao tác phù hợp.
4. Chọn template theo tên hoặc ngữ cảnh giao diện.
5. Xác định target từ thuộc tính `target`; nếu không có, dùng href của link mang affordance.
6. Tạo input theo `properties`, `required`, `type`, `options` và các ràng buộc khác.
7. Gửi request bằng `method` và `contentType` được mô tả.
8. Đọc response mới và tiếp tục điều hướng theo link được công bố.

Ví dụ chuỗi HTTP:

~~~http
GET /customers HTTP/1.1
Accept: application/prs.hal-forms+json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
~~~

Client chọn template `default`, điền dữ liệu và gửi:

~~~http
POST /customers HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Nguyễn An",
  "email": "an@example.com"
}
~~~

Server xử lý request theo controller, validation và quy tắc nghiệp vụ. Response có thể trả tài nguyên mới cùng link self.

### 10.1. Template không phải HTML form

HAL-FORMS mô tả thao tác và property. Nó không chứa bố cục trang, màu sắc, thứ tự nhóm field hoặc mã JavaScript. Client có thể tạo HTML form từ metadata, nhưng đó là trách nhiệm của client.

Client cũng phải có khả năng gửi HTTP method được mô tả. HTML form thuần chỉ hỗ trợ GET và POST; PUT, PATCH hoặc DELETE thường cần JavaScript hoặc HTTP client.

### 10.2. Template không cấp quyền

Server có thể chỉ công bố affordance khi thao tác khả dụng với trạng thái tài nguyên hoặc người dùng hiện tại. Điều đó giúp client hiển thị đúng các hành động có thể thực hiện.

Tuy nhiên, việc ẩn template không bảo vệ endpoint. Client có thể tự gửi request. Server vẫn phải xác thực quyền, kiểm tra dữ liệu và áp dụng quy tắc nghiệp vụ khi nhận request.

## 11. Kiểm thử media type HAL-FORMS

Kiểm thử cần xác nhận cả header HTTP lẫn nội dung template.

Ví dụ:

~~~java
@WebMvcTest(CustomerController.class)
@Import({
    CustomerModelAssembler.class,
    HypermediaConfiguration.class
})
class CustomerControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CustomerService service;

    @Test
    void returnsHalFormsWithCreateTemplate() throws Exception {

        given(service.findAll()).willReturn(List.of());

        mvc.perform(get("/customers")
                .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_FORMS_JSON
            ))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/customers")))
            .andExpect(jsonPath("$._templates.default.method")
                .value("post"))
            .andExpect(jsonPath("$._templates.default.contentType")
                .value("application/json"))
            .andExpect(jsonPath("$._templates.default.properties").isArray());
    }
}
~~~

Ví dụ giả định controller công bố affordance POST như mục 6. Tùy phiên bản Spring Boot, có thể dùng `@MockitoBean` thay cho `@MockBean`.

Các import thường dùng:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

### 11.1. Kiểm thử HAL và HAL-FORMS riêng

Nếu endpoint hỗ trợ cả hai media type, kiểm tra HAL:

~~~java
mvc.perform(get("/customers")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates").doesNotExist());
~~~

Kiểm tra HAL-FORMS:

~~~java
mvc.perform(get("/customers")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_FORMS_JSON
    ))
    .andExpect(jsonPath("$._templates.default.method").exists());
~~~

Nếu representation không có affordance, converter HAL-FORMS có thể trả về HAL JSON. Vì vậy, test phải chuẩn bị một model có affordance thực sự và kiểm tra cả `Content-Type` lẫn `_templates`.

### 11.2. Kiểm thử request được mô tả

Template chỉ mô tả thao tác. Cần kiểm thử riêng endpoint nhận request:

~~~java
mvc.perform(post("/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("""
            {
              "name": "Nguyễn An",
              "email": "an@example.com"
            }
            """))
    .andExpect(status().isCreated());
~~~

Kiểm thử này xác nhận endpoint xử lý request thực tế. Kiểm thử HAL-FORMS xác nhận template mô tả đúng endpoint. Hai phần cần được kiểm tra độc lập để tránh trường hợp template công bố sai method hoặc field.

## 12. Caching và tương thích

Một URI có thể trả HAL hoặc HAL-FORMS tùy header `Accept`. Nếu title và prompt được quốc tế hóa, response còn phụ thuộc `Accept-Language`.

Khi dùng cache dùng chung, cần bảo đảm các biến thể representation được phân biệt theo header liên quan. Với response thay đổi theo `Accept`, cấu hình cache và `Vary` phù hợp để cache không trả HAL cho client yêu cầu HAL-FORMS hoặc ngược lại. Nếu response thay đổi theo locale, cũng cần tính đến `Accept-Language`.

Template là một phần của hợp đồng API. Các thay đổi sau có thể ảnh hưởng client:

- Đổi tên template.
- Đổi tên property.
- Thay đổi HTTP method hoặc target.
- Thay đổi content type của request.
- Thay đổi `required`, `type`, `options` hoặc ràng buộc field.
- Loại bỏ affordance mà client đang sử dụng.

Hãy kiểm thử template quan trọng như kiểm thử response body và quản lý các thay đổi tương thích như với bất kỳ hợp đồng API công khai nào.

## 13. Lỗi thường gặp khi làm việc với HAL-FORMS

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng `application/hal+json` nhưng mong có `_templates` | Client không nhận metadata form | Yêu cầu `application/prs.hal-forms+json` |
| Nghĩ HAL và HAL-FORMS có thể thay thế nhau | Client diễn giải sai representation | Xử lý hai media type riêng |
| Nhầm `contentType` trong template với Content-Type response | Client gửi body sai định dạng | Phân biệt media type response và request body |
| Không gắn affordance vào link | Không có template để serialize | Dùng `andAffordance(...)` hoặc API affordance tương ứng |
| Dùng response DTO làm input model | Form chứa trường server quản lý | Tạo request DTO riêng |
| Nghĩ `required` thay thế validation | Request không hợp lệ vẫn có thể đến server | Validate ở server |
| Coi template là HTML | Client không biết cách tạo giao diện | Xây client diễn giải HAL-FORMS |
| Cho rằng converter luôn trả HAL-FORMS | Có thể nhận HAL khi không có template | Kiểm tra affordance và `Content-Type` |
| Bỏ qua `Accept-Language` trong cache | Prompt hoặc title sai locale | Cache theo locale |
| Ẩn affordance để bảo vệ endpoint | Request trực tiếp vẫn có thể được gửi | Kiểm tra quyền ở server |

## 14. Quy trình triển khai HAL-FORMS

Khi thêm HAL-FORMS vào một API Spring HATEOAS, có thể thực hiện theo trình tự:

1. Xác định client cần nhận HAL-FORMS và hỗ trợ media type này.
2. Kích hoạt `HypermediaType.HAL_FORMS` trong cấu hình.
3. Tạo request DTO riêng cho mỗi thao tác nhận dữ liệu.
4. Khai báo mapping và `consumes` phù hợp với request body.
5. Gắn affordance của controller method vào link thích hợp.
6. Thêm validation annotation hoặc `@InputType` cho các property cần mô tả.
7. Cấu hình options, prompt, placeholder và title nếu cần.
8. Yêu cầu representation bằng `Accept: application/prs.hal-forms+json`.
9. Kiểm tra `Content-Type`, `_links` và `_templates` trong response.
10. Kiểm thử request thực tế, quyền truy cập và validation ở server.
11. Kiểm tra cache theo `Accept` và `Accept-Language`.
12. Quản lý thay đổi template như thay đổi hợp đồng API.

## 15. Kết luận

HAL-FORMS là media type `application/prs.hal-forms+json`, mở rộng cách biểu diễn HAL bằng `_templates`. Template mô tả HTTP method, target, content type và các property mà client gửi. Spring HATEOAS tạo template từ affordance gắn trên link và metadata của input model, sau đó serialize qua hạ tầng HAL-FORMS khi client yêu cầu đúng media type.

Cần phân biệt `Accept` của client, `Content-Type` của representation response và `contentType` trong template. HAL-FORMS vẫn dùng `_links` để điều hướng; `_templates` bổ sung mô tả thao tác. Metadata giúp client chuẩn bị request nhưng không thay thế giao diện, validation hoặc phân quyền. Khi cấu hình content negotiation đúng, công bố affordance rõ ràng và kiểm thử cả template lẫn request thật, API có thể cung cấp một hợp đồng hypermedia giàu khả năng khám phá hơn.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms): định danh media type, cấu hình, cấu trúc tài liệu và template.
- [Spring HATEOAS Reference — Defining HAL-FORMS metadata](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms.metadata): metadata của template, property, options và quốc tế hóa.
- [Spring HATEOAS API — MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html): các hằng số `HAL_FORMS_JSON` và `HAL_FORMS_JSON_VALUE`.
- [Spring HATEOAS API — HalFormsOptions](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsOptions.html): options inline và remote.
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/): cấu trúc media type và `_templates`.

