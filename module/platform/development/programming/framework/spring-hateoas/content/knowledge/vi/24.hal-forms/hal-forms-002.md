# Media type HAL-FORMS

HAL-FORMS là một media type hypermedia được thiết kế để bổ sung khả năng mô tả biểu mẫu và thao tác tại runtime cho tài nguyên HAL. Một response HAL thông thường công bố dữ liệu và các link trong thuộc tính **_links**. HAL-FORMS giữ cách biểu diễn đó, đồng thời bổ sung **_templates** để mô tả cách client có thể gửi một thao tác: HTTP method nào được dùng, gửi đến URI nào, dùng content type nào và cần cung cấp những trường dữ liệu nào.

Trong Spring HATEOAS, HAL-FORMS được tạo từ representation model cùng các affordance gắn với link. Affordance thường được suy ra từ mapping controller, kiểu request body và metadata validation. Khi client yêu cầu media type HAL-FORMS, Spring HATEOAS có thể chuyển metadata đó thành template mà client dùng để dựng form hoặc chuẩn bị request.

Bài học này tập trung vào media type HAL-FORMS, cách thương lượng nội dung qua HTTP, cấu trúc **_templates**, cách Spring HATEOAS bật hỗ trợ HAL-FORMS, cách khai báo affordance từ controller method, cách mô tả thuộc tính form và cách kiểm thử response.

## 1. HAL-FORMS giải quyết nhu cầu gì?

Một link HAL cơ bản cho biết client có thể điều hướng đến đâu. Ví dụ:

~~~json
{
  "id": "EMP-42",
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    }
  }
}
~~~

Client biết URI của nhân viên, nhưng chỉ từ link self thì chưa biết:

- Có thể cập nhật tài nguyên bằng PUT hay PATCH?
- Request cần gửi đến URI nào?
- Request body có những trường nào?
- Trường nào bắt buộc, trường nào chỉ đọc?
- Email phải đúng định dạng nào?
- Một trường chọn lựa có các giá trị hợp lệ nào?

Client có thể đã được lập trình sẵn các quy tắc đó, nhưng khi ấy nó phải biết trước nhiều chi tiết của API. HAL-FORMS cho phép server công bố một phần mô tả thao tác cùng representation:

~~~json
{
  "id": "EMP-42",
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    }
  },
  "_templates": {
    "updateEmployee": {
      "title": "Cập nhật nhân viên",
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "required": true,
          "type": "text"
        },
        {
          "name": "lastName",
          "required": true,
          "type": "text"
        }
      ]
    }
  }
}
~~~

Client có thể đọc template, dựng giao diện nhập liệu hoặc chuẩn bị request mà không phải tự đoán method và tên trường. Server vẫn là nơi thực thi nghiệp vụ và xác thực dữ liệu khi request được gửi.

HAL-FORMS không tự tạo một trang HTML. Nó công bố metadata để client có khả năng diễn giải template và chọn cách hiển thị hoặc tương tác phù hợp.

## 2. Media type HAL-FORMS

Media type của HAL-FORMS là:

~~~http
application/prs.hal-forms+json
~~~

Tên media type có thành phần **prs**, khác với **application/hal+json** của HAL. Trong Spring HATEOAS, có thể dùng các hằng số:

- **MediaTypes.HAL_FORMS_JSON**: đối tượng MediaType.
- **MediaTypes.HAL_FORMS_JSON_VALUE**: chuỗi media type dùng trong annotation hoặc header.
- **EnableHypermediaSupport.HypermediaType.HAL_FORMS**: loại hypermedia dùng khi bật cấu hình.

Ví dụ request:

~~~http
GET /employees/EMP-42 HTTP/1.1
Host: api.example.com
Accept: application/prs.hal-forms+json
~~~

Nếu server có thể tạo template HAL-FORMS cho representation, response có thể có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
~~~

Cần phân biệt hai header:

| Header | Ý nghĩa |
|---|---|
| Accept | Client cho biết media type mà nó muốn nhận |
| Content-Type | Server cho biết media type thực tế của response |

Client yêu cầu HAL-FORMS bằng Accept. Client phải đọc Content-Type của response để biết server thực sự trả HAL-FORMS hay một định dạng khác.

## 3. HAL và HAL-FORMS không thể thay thế tùy tiện

HAL-FORMS trông giống HAL vì vẫn dùng link và representation JSON. Tuy nhiên, hai media type không đồng nhất và không nên xem là có thể thay thế nhau trong mọi trường hợp.

| Khía cạnh | HAL | HAL-FORMS |
|---|---|---|
| Media type | application/hal+json | application/prs.hal-forms+json |
| Link | Có _links | Có _links |
| Tài nguyên nhúng | Có thể dùng _embedded | Có thể dùng _embedded |
| Mô tả thao tác | Link và metadata cơ bản | Bổ sung _templates |
| HTTP method của form | Không được mô tả đầy đủ bởi link cơ bản | Có thể mô tả bằng method |
| Trường request | Client thường phải biết từ hợp đồng khác | Có thể mô tả trong properties |
| Mục tiêu | Điều hướng giữa tài nguyên | Điều hướng và mô tả thao tác tại runtime |

HAL phù hợp khi client chỉ cần khám phá tài nguyên và theo link. HAL-FORMS hữu ích khi client cần biết cách gửi một thao tác có dữ liệu đầu vào, ví dụ tạo, cập nhật hoặc tìm kiếm.

HAL-FORMS vẫn có thể chứa dữ liệu tài nguyên và link giống HAL. Phần mở rộng chính là mô tả template thao tác trong **_templates**.

## 4. Cấu trúc tài liệu HAL-FORMS

Một tài liệu HAL-FORMS thường chứa:

- Các thuộc tính dữ liệu của tài nguyên.
- **_links**: link đến chính tài nguyên hoặc tài nguyên liên quan.
- **_templates**: một tập hợp template mô tả các thao tác mà client có thể gửi.

Ví dụ:

~~~json
{
  "id": "EMP-42",
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    },
    "employees": {
      "href": "/employees"
    }
  },
  "_templates": {
    "updateEmployee": {
      "title": "Cập nhật nhân viên",
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "prompt": "Tên",
          "required": true,
          "type": "text"
        },
        {
          "name": "lastName",
          "prompt": "Họ",
          "required": true,
          "type": "text"
        }
      ]
    }
  }
}
~~~

Mỗi key trong **_templates** là tên một template. Client chọn template phù hợp, đọc method và properties, sau đó gửi dữ liệu đến target tương ứng. Nếu template không khai báo target riêng, client dùng URI của link mà affordance được gắn vào.

### 4.1. Các thuộc tính của template

| Thuộc tính | Ý nghĩa |
|---|---|
| method | HTTP method cần dùng khi gửi thao tác, ví dụ post, put, patch hoặc delete |
| contentType | Media type của request body gửi đến server |
| target | URI đích nếu khác URI của link chứa affordance |
| title | Tiêu đề thân thiện để hiển thị cho người dùng |
| properties | Danh sách các trường mà client có thể gửi |

**method** là thành phần cốt lõi để client biết cách gửi request. Ví dụ, template cập nhật toàn bộ tài nguyên có thể dùng put; template cập nhật một phần có thể dùng patch.

**contentType** cho biết định dạng request body. Spring HATEOAS có thể suy ra giá trị này từ thuộc tính consumes của mapping controller hoặc từ cấu hình affordance. Nếu không có giá trị, theo quy tắc HAL-FORMS client xử lý mặc định như application/json.

**target** chỉ được cần đến khi thao tác gửi đến URI khác với link mà template đang gắn vào. Ví dụ, affordance POST tạo tài nguyên có thể được gắn vào link self của collection; nếu endpoint tạo có URI riêng, target sẽ chỉ ra đích gửi request.

### 4.2. Các thuộc tính của property

Mỗi phần tử trong properties mô tả một trường đầu vào:

| Thuộc tính | Ý nghĩa |
|---|---|
| name | Tên thuộc tính trong dữ liệu gửi đi |
| prompt | Nhãn dễ hiểu cho người dùng |
| type | Loại input mà client có thể dùng, ví dụ text, email, date |
| required | Cho biết trường có bắt buộc hay không |
| readOnly | Cho biết trường chỉ đọc |
| regex | Biểu thức chính quy để kiểm tra định dạng |
| min, max | Giới hạn giá trị số |
| minLength, maxLength | Giới hạn độ dài chuỗi |
| placeholder | Gợi ý định dạng hoặc giá trị mẫu |
| options | Danh sách lựa chọn hoặc link đến nguồn lựa chọn |

Không phải response nào cũng chứa đầy đủ mọi thuộc tính. HAL-FORMS có các giá trị mặc định; ví dụ, required mặc định là false nên có thể bị lược khỏi JSON. Client cần hiểu ý nghĩa của thuộc tính vắng mặt theo đặc tả thay vì giả định trường luôn được mô tả tường minh.

Với template dùng PATCH, các thuộc tính thường được xem là không bắt buộc vì thao tác chỉ gửi các trường cần thay đổi. Spring HATEOAS cũng xử lý metadata PATCH theo hướng này.

## 5. Bật hỗ trợ HAL-FORMS trong Spring HATEOAS

Spring HATEOAS hỗ trợ HAL-FORMS thông qua cấu hình hypermedia. Với ứng dụng Spring MVC, có thể bật như sau:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;

@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL_FORMS
)
public class HypermediaConfiguration {
}
~~~

Cấu hình này đăng ký hạ tầng cần thiết để serialize các representation model theo HAL-FORMS và chuyển affordance thành metadata template.

Trong ứng dụng Spring Boot, hãy kiểm tra auto-configuration và cấu hình hypermedia hiện có trước khi khai báo thêm cấu hình thủ công. Tránh đăng ký converter hoặc Jackson module trùng lặp.

Spring HATEOAS cung cấp converter HAL-FORMS và module Jackson riêng. Converter kiểm tra representation model có affordance nào được chuyển thành template hay không. Nếu không có template nào được đăng ký, converter có thể chuyển response về media type HAL JSON. Vì vậy, việc client gửi Accept HAL-FORMS chưa bảo đảm response luôn có Content-Type HAL-FORMS.

Đây là hành vi cần lưu ý khi kiểm thử content negotiation: hãy tạo affordance thực sự nếu mục tiêu là nhận template HAL-FORMS, sau đó kiểm tra cả Content-Type lẫn nội dung _templates.

## 6. Affordance là nguồn tạo template

HAL-FORMS không tự suy đoán mọi thao tác chỉ từ các link. Spring HATEOAS cần biết những handler method nào có thể được thực hiện trên tài nguyên. Thông tin đó được cung cấp thông qua affordance.

Affordance liên kết một thao tác HTTP với một link. Từ mapping controller, Spring HATEOAS có thể đọc:

- HTTP method.
- URI đích.
- Kiểu request body.
- Kiểu response.
- Các thuộc tính và metadata của kiểu dữ liệu đầu vào.

Sau đó, media type HAL-FORMS chuyển metadata affordance thành template trong _templates.

Ví dụ, tài nguyên nhân viên có link self. Link này có thể công bố hai thao tác: PUT để cập nhật đầy đủ và PATCH để cập nhật một phần.

~~~java
Link self = linkTo(
        methodOn(EmployeeController.class).one(id)
    )
    .withSelfRel()
    .andAffordance(afford(
        methodOn(EmployeeController.class).update(null, id)
    ))
    .andAffordance(afford(
        methodOn(EmployeeController.class).partiallyUpdate(null, id)
    ));
~~~

Trong ví dụ:

- Lời gọi one(id) xác định link self.
- update(null, id) tham chiếu handler PUT.
- partiallyUpdate(null, id) tham chiếu handler PATCH.
- null là placeholder cho request body khi ghi nhận mapping; nó không làm controller thực thi thao tác cập nhật.

Cần import các helper:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

methodOn tạo proxy ghi nhận lời gọi handler method. Biểu thức này dùng để đọc mapping và metadata, không gọi logic nghiệp vụ của controller.

## 7. Ví dụ controller công bố affordance PUT và PATCH

Giả sử API quản lý nhân viên có các handler:

~~~java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

public record EmployeeRepresentation(
    UUID id,
    String firstName,
    String lastName
) {}

@RestController
@RequestMapping("/employees")
public class EmployeeController {

    private final EmployeeService service;

    public EmployeeController(EmployeeService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public EntityModel<EmployeeRepresentation> one(
            @PathVariable UUID id) {
        Employee employee = service.findById(id);

        Link self = linkTo(
                methodOn(EmployeeController.class).one(id)
            )
            .withSelfRel()
            .andAffordance(afford(
                methodOn(EmployeeController.class).update(null, id)
            ))
            .andAffordance(afford(
                methodOn(EmployeeController.class)
                    .partiallyUpdate(null, id)
            ));

        return EntityModel.of(
            new EmployeeRepresentation(
                employee.getId(),
                employee.getFirstName(),
                employee.getLastName()
            ),
            self
        );
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> update(
            @Valid @RequestBody EmployeeInput input,
            @PathVariable UUID id) {
        service.update(id, input);
        return ResponseEntity.noContent().build();
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> partiallyUpdate(
            @Valid @RequestBody EmployeePatchInput input,
            @PathVariable UUID id) {
        service.partiallyUpdate(id, input);
        return ResponseEntity.noContent().build();
    }
}
~~~

Link self gắn hai affordance. Khi client yêu cầu HAL-FORMS, response có thể chứa hai template tương ứng với hai thao tác cập nhật.

Ví dụ dạng JSON rút gọn:

~~~json
{
  "id": "EMP-42",
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    }
  },
  "_templates": {
    "update": {
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "required": true,
          "type": "text"
        },
        {
          "name": "lastName",
          "required": true,
          "type": "text"
        }
      ]
    },
    "partiallyUpdate": {
      "method": "patch",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "type": "text"
        },
        {
          "name": "lastName",
          "type": "text"
        }
      ]
    }
  }
}
~~~

Tên template phụ thuộc tên affordance và cấu hình. Khi chỉ có một template, key default thường được dùng theo quy ước HAL-FORMS. Khi có nhiều affordance, template thường được đặt tên theo thao tác tương ứng. Spring HATEOAS cung cấp cấu hình withDefaultSingleTemplate(...) để điều chỉnh hành vi đặt tên template đơn trong các phiên bản hỗ trợ tùy chọn này.

## 8. Mô tả thuộc tính đầu vào bằng Bean Validation

Spring HATEOAS có thể dùng metadata của kiểu request để tạo thuộc tính HAL-FORMS. Vì vậy, kiểu input nên mô tả đúng dữ liệu client được phép gửi.

Ví dụ:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class EmployeeInput {

    @NotNull
    private String firstName;

    @NotNull
    private String lastName;

    @Email
    private String email;

    @Pattern(regexp = "[A-Z0-9]{6}")
    private String employeeCode;

    private String department;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public void setEmployeeCode(String employeeCode) {
        this.employeeCode = employeeCode;
    }

    public String getDepartment() {
        return department;
    }

    public void setDepartment(String department) {
        this.department = department;
    }
}
~~~

EmployeePatchInput là DTO riêng cho cập nhật một phần, trong đó các trường có thể để trống và không gắn @NotNull hàng loạt. Tách kiểu input cho PUT và PATCH giúp metadata của template phản ánh đúng quy tắc của từng thao tác; validation phía server vẫn phải phù hợp với ngữ nghĩa cập nhật một phần.

Ví dụ kiểu input PATCH tối giản:

~~~java
public class EmployeePatchInput {

    private String firstName;
    private String lastName;

    public String getFirstName() { return firstName; }
    public void setFirstName(String firstName) { this.firstName = firstName; }
    public String getLastName() { return lastName; }
    public void setLastName(String lastName) { this.lastName = lastName; }
}
~~~

Các metadata có thể được chuyển thành thuộc tính template:

- @NotNull có thể làm required thành true.
- @Pattern cung cấp regex.
- @Email giúp xác định kiểu input email.
- Kiểu Java như String hoặc LocalDate có thể được ánh xạ sang type phù hợp.
- Các ràng buộc về số và độ dài có thể được chuyển thành min, max, minLength hoặc maxLength tùy annotation và provider được hỗ trợ.

Ví dụ phần properties tương ứng:

~~~json
{
  "properties": [
    {
      "name": "firstName",
      "required": true,
      "type": "text"
    },
    {
      "name": "email",
      "type": "email"
    },
    {
      "name": "employeeCode",
      "regex": "[A-Z0-9]{6}",
      "type": "text"
    }
  ]
}
~~~

HAL-FORMS metadata giúp client trình bày input và hỗ trợ người dùng nhập dữ liệu. Nó không thay thế Bean Validation hoặc kiểm tra nghiệp vụ ở server. Request thực tế vẫn phải được validate trong controller/service trước khi thay đổi dữ liệu.

## 9. Trường chỉ đọc và kiểu input

Một property có thể được mô tả là chỉ đọc bằng thuộc tính readOnly. Spring HATEOAS có thể suy ra trạng thái này từ cấu trúc property, ví dụ không có setter. Có thể dùng Jackson annotation để khai báo rõ quyền truy cập:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private UUID id;
~~~

Với type, Spring HATEOAS suy luận từ kiểu Java và metadata validation. Ví dụ String thường thành text, LocalDate có thể thành date, email được nhận diện là email khi có annotation tương ứng.

Nếu một kiểu dữ liệu tùy chỉnh cần regex riêng, có thể đăng ký pattern trong HalFormsConfiguration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsConfiguration;
import org.springframework.hateoas.mediatype.hal.forms.HalFormsOptions;

@Configuration
public class HalFormsMetadataConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        return new HalFormsConfiguration()
            .withPattern(CreditCardNumber.class, "[0-9]{16}")
            .withOptions(
                EmployeeInput.class,
                "department",
                metadata -> HalFormsOptions.inline(
                    "ENGINEERING", "FINANCE", "OPERATIONS"
                )
            );
    }
}
~~~

Trong ví dụ, property có kiểu CreditCardNumber sẽ được mô tả với regex tương ứng. Dùng cấu hình này khi kiểu dữ liệu không thể gắn annotation trực tiếp hoặc khi muốn tập trung metadata cho kiểu tùy chỉnh.

## 10. Cung cấp lựa chọn cho property bằng options

Một số trường không nên để client nhập chuỗi tùy ý. Ví dụ, phương thức giao hàng chỉ được chọn trong danh sách mà server hỗ trợ.

HAL-FORMS có thuộc tính options để công bố lựa chọn. Ví dụ cấu hình ở mục trước dùng **HalFormsOptions.inline(...)** để đưa danh sách giá trị vào cùng template. Hãy gộp options và custom pattern vào cùng một bean HalFormsConfiguration để tránh nhiều bean cùng kiểu gây mơ hồ khi inject.

Dữ liệu options có thể được biểu diễn trong template:

~~~json
{
  "name": "department",
  "options": {
    "inline": [
      "ENGINEERING",
      "FINANCE",
      "OPERATIONS"
    ]
  }
}
~~~

Nếu danh sách lựa chọn lớn hoặc thay đổi thường xuyên, có thể dùng options remote để trỏ đến tài nguyên cung cấp giá trị:

~~~java
.withOptions(
    EmployeeInput.class,
    "department",
    metadata -> HalFormsOptions.remote("/departments")
)
~~~

Client có thể tải danh sách lựa chọn từ URI đó. Dù options được công bố inline hay remote, server vẫn phải kiểm tra giá trị gửi lên có hợp lệ và người dùng có quyền chọn hay không.

## 11. Đặt tiêu đề và prompt bằng resource bundle

Một template có thể có title để client hiển thị cho người dùng. Property có thể có prompt và placeholder. Spring HATEOAS hỗ trợ quốc tế hóa các chuỗi này thông qua resource bundle tên **rest-messages**.

Ví dụ file:

~~~properties
EmployeeInput._templates.update.title=Update employee
EmployeeInput._templates.partiallyUpdate.title=Update employee details
EmployeeInput.firstName._prompt=First name
EmployeeInput.firstName._placeholder=Enter first name
EmployeeInput.lastName._prompt=Last name
EmployeeInput.email._prompt=Email address
~~~

Có thể cung cấp các file ngôn ngữ riêng, ví dụ:

~~~text
rest-messages.properties
rest-messages_vi.properties
rest-messages_en.properties
~~~

Client gửi Accept-Language để yêu cầu ngôn ngữ phù hợp. Spring HATEOAS sử dụng resource bundle để điền title, prompt và placeholder khi serialize template.

Nên dùng chuỗi hướng dẫn rõ ràng, ngắn và nhất quán. Prompt là nội dung dành cho người dùng cuối, còn name là tên thuộc tính kỹ thuật được gửi trong request body.

## 12. Tạo affordance cho thao tác POST trên collection

HAL-FORMS không chỉ mô tả cập nhật một tài nguyên. Collection resource cũng có thể công bố template tạo tài nguyên mới.

Ví dụ, link self của collection employees gắn affordance POST:

~~~java
@GetMapping
public CollectionModel<EntityModel<EmployeeRepresentation>> all() {
    var employees = service.findAll()
        .stream()
        .map(assembler::toModel)
        .toList();

    Link self = linkTo(
            methodOn(EmployeeController.class).all()
        )
        .withSelfRel()
        .andAffordance(afford(
            methodOn(EmployeeController.class).create(null)
        ));

    return CollectionModel.of(employees, self);
}

@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> create(
        @RequestBody EmployeeInput input) {
    Employee created = service.create(input);
    return ResponseEntity.created(
        URI.create("/employees/" + created.getId())
    ).build();
}
~~~

Client yêu cầu HAL-FORMS từ collection resource có thể nhận template POST với các properties của EmployeeInput. Client không cần tự đoán cấu trúc request body từ entity database.

Đây là một cách công bố thao tác tạo tài nguyên. API cũng có thể cung cấp link đến một resource riêng dành cho quy trình tạo nếu quy trình cần nhiều bước hoặc có trạng thái trung gian.

## 13. Target và contentType của template

Khi affordance được gắn vào link, template thường dùng URI của link làm đích gửi request. Nếu endpoint thao tác có URI khác, HAL-FORMS có thể công bố thuộc tính target.

Ví dụ khái niệm:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    }
  },
  "_templates": {
    "submitPayment": {
      "method": "post",
      "target": "/payments",
      "contentType": "application/json",
      "properties": [
        {
          "name": "orderId",
          "required": true,
          "type": "text"
        },
        {
          "name": "amount",
          "required": true,
          "type": "number"
        }
      ]
    }
  }
}
~~~

Trong ví dụ, template được công bố trên representation đơn hàng nhưng request gửi đến /payments. target cho client biết URI đích khác self link.

contentType mô tả định dạng body mà client cần gửi. Spring HATEOAS có thể suy ra từ consumes trong @PostMapping, @PutMapping hoặc @RequestMapping. Nếu endpoint nhận JSON, khai báo consumes rõ ràng để metadata template phản ánh đúng hợp đồng request.

Client cần tuân theo method, target và contentType mà template công bố. Server vẫn xử lý request theo mapping thực tế và trả status phù hợp.

## 14. Luồng client sử dụng HAL-FORMS

Một client có thể tương tác với API theo trình tự:

~~~text
GET resource
    |
    | Accept: application/prs.hal-forms+json
    v
Read HAL-FORMS document
    |
    +-- Read resource data
    |
    +-- Find relation in _links
    |
    +-- Choose template in _templates
             |
             +-- Read method
             +-- Read target or link href
             +-- Read contentType
             +-- Render properties
             |
             v
       Collect user input
             |
             v
       Submit HTTP request
             |
             v
       Handle response and follow links
~~~

Client thực hiện các bước:

1. Gửi request với Accept HAL-FORMS.
2. Đọc dữ liệu tài nguyên và các link trong _links.
3. Chọn template phù hợp trong _templates.
4. Dựng form hoặc giao diện nhập liệu từ properties.
5. Thu thập giá trị theo name của từng property.
6. Gửi request đến target hoặc href liên quan, sử dụng method và contentType đã công bố.
7. Xử lý response và tiếp tục điều hướng theo link mới.

Một client có thể không hỗ trợ đầy đủ mọi thuộc tính options hoặc type. Theo đặc tả, client có thể bỏ qua metadata mà nó không hiểu và vẫn xử lý property theo cách cơ bản. Vì vậy, API không nên dựa vào một tính năng tùy chọn duy nhất để bảo đảm tính đúng đắn của nghiệp vụ.

## 15. HAL-FORMS không thay thế bảo mật và validation

Template công bố thao tác mà server mô tả tại thời điểm tạo response. Nó không phải quyền truy cập và không phải cam kết rằng request sau đó chắc chắn thành công.

Ví dụ, response có thể công bố affordance cancel khi đơn hàng đang ở trạng thái PROCESSING. Trước khi client gửi request, đơn hàng có thể đã chuyển sang DELIVERED. Endpoint vẫn phải kiểm tra trạng thái mới nhất.

Tương tự, property required hoặc regex trong template giúp client hỗ trợ nhập dữ liệu, nhưng client có thể gửi request trực tiếp mà không dùng form. Server vẫn cần:

- Xác thực người dùng.
- Kiểm tra quyền thực hiện thao tác.
- Validate request body bằng Bean Validation.
- Kiểm tra quy tắc nghiệp vụ.
- Kiểm tra trạng thái tài nguyên tại thời điểm xử lý.
- Trả lỗi HTTP và thông tin lỗi phù hợp.

HAL-FORMS giúp client hiểu cách sử dụng API. Việc thực thi thao tác và quyết định cho phép vẫn thuộc server.

## 16. Kiểm thử media type HAL-FORMS bằng MockMvc

Kiểm thử cần xác nhận cả content negotiation và template được tạo. Ví dụ:

~~~java
mockMvc.perform(get("/employees/{id}", employeeId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_FORMS_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.update.method")
        .value("put"))
    .andExpect(jsonPath("$._templates.partiallyUpdate.method")
        .value("patch"));
~~~

Tên key template trong test phải khớp với tên affordance thực tế và cấu hình HAL-FORMS của ứng dụng. Nếu chỉ có một affordance, key có thể là default theo quy ước template đơn.

Kiểm tra properties:

~~~java
mockMvc.perform(get("/employees/{id}", employeeId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._templates.update.properties[?(@.name=='firstName')].required"
    ).value(contains(true)));
~~~

Có thể bổ sung kiểm tra contentType, target, regex, type và options nếu các metadata đó là một phần hợp đồng API.

## 17. Kiểm thử fallback về HAL JSON

Spring HATEOAS có thể chuyển response về HAL JSON nếu representation model không có affordance nào tạo ra template. Điều này giúp tránh trả một tài liệu HAL-FORMS không có nội dung form hữu ích.

Do đó, ngoài test có affordance, nên có test cho endpoint không công bố template:

~~~java
mockMvc.perform(get("/employees/{id}/summary", employeeId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Test này cần phản ánh cấu hình và converter thực tế của ứng dụng. Nếu hợp đồng yêu cầu mọi response phải là HAL-FORMS, hãy bảo đảm representation luôn có ít nhất một affordance phù hợp hoặc thiết kế lại cách công bố template.

Không nên chỉ kiểm tra Accept header của request. Content-Type của response mới cho biết server đã chọn media type nào.

## 18. Những lỗi thường gặp khi dùng HAL-FORMS

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng application/hal+json khi client cần template | Response chỉ có link, không có _templates | Yêu cầu application/prs.hal-forms+json |
| Nghĩ HAL và HAL-FORMS là cùng một media type | Client xử lý sai cấu trúc và khả năng thao tác | Kiểm tra Content-Type và hỗ trợ từng media type |
| Chỉ tạo Link mà không khai báo affordance | Không có metadata thao tác để tạo template | Gắn affordance từ controller method |
| Gắn affordance sai handler | Method, URI hoặc request body được mô tả sai | Kiểm tra mapping và kiểu request của handler |
| Nghĩ server tự dựng HTML form | Không có giao diện form phía client | Xem _templates là metadata để client diễn giải |
| Nghĩ required hoặc regex thay thế validation | Request trực tiếp có thể bỏ qua metadata | Validate lại ở server |
| Không khai báo consumes | Template có thể thiếu contentType dự kiến | Khai báo consumes phù hợp cho handler |
| Không kiểm tra fallback converter | Client yêu cầu HAL-FORMS nhưng nhận HAL JSON | Kiểm tra cả Content-Type và _templates |
| Dùng tên template không ổn định trong test | Test gãy khi đổi tên affordance hoặc cấu hình | Quản lý tên affordance như một phần hợp đồng |
| Coi affordance là quyền truy cập | Request vẫn có thể bị từ chối hoặc bị gửi trái phép | Kiểm tra authentication và authorization tại endpoint |

## 19. Quy trình áp dụng HAL-FORMS

Khi muốn công bố biểu mẫu thao tác bằng Spring HATEOAS, có thể đi theo thứ tự:

1. Xác định tài nguyên và thao tác client cần thực hiện.
2. Bật hỗ trợ HAL-FORMS bằng HypermediaType.HAL_FORMS.
3. Tạo representation model có link phù hợp.
4. Gắn affordance đến các controller method POST, PUT, PATCH hoặc thao tác tương ứng.
5. Dùng kiểu request input riêng để mô tả các trường client cần gửi.
6. Thêm Bean Validation và metadata type để mô tả required, regex, type và giới hạn.
7. Dùng HalFormsConfiguration để khai báo options hoặc pattern cho kiểu tùy chỉnh.
8. Dùng rest-messages để đặt title, prompt và placeholder theo ngôn ngữ.
9. Yêu cầu media type application/prs.hal-forms+json từ client.
10. Kiểm thử _templates, properties, target, method, contentType và Content-Type thực tế.
11. Giữ validation, phân quyền và quy tắc nghiệp vụ ở server khi nhận request.

HAL-FORMS bổ sung khả năng mô tả thao tác tại runtime cho API hypermedia. Spring HATEOAS kết nối affordance với controller mapping và kiểu request để tạo template có thể được client diễn giải. Khi media type, method, target và metadata property được công bố rõ ràng, client có thể khám phá cách tương tác với tài nguyên mà không phải mã hóa cứng toàn bộ cấu trúc form. Server vẫn giữ quyền kiểm soát cuối cùng đối với validation, trạng thái và bảo mật của thao tác.

## Tài liệu tham khảo

- [HAL-FORMS Specification](https://rwcbook.com/hal-forms/)
- [Spring HATEOAS Reference Documentation – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [MediaTypes API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [EnableHypermediaSupport.HypermediaType API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/EnableHypermediaSupport.HypermediaType.html)
- [HalFormsConfiguration API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsConfiguration.html)
- [HalFormsOptions API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsOptions.html)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)

