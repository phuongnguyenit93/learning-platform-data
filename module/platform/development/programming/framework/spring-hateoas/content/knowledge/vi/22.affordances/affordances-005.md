# Affordance cho PUT

Trong REST API có hypermedia, một link thông thường cho client biết tài nguyên hoặc endpoint có thể truy cập qua `href`. Affordance bổ sung mô tả về một thao tác có thể thực hiện tại link đó, chẳng hạn HTTP method, kiểu nội dung và các trường đầu vào. Với thao tác cập nhật tài nguyên bằng `PUT`, Spring HATEOAS có thể suy ra metadata từ mapping controller và kiểu request body, sau đó công bố metadata đó trong định dạng hỗ trợ affordance như HAL-FORMS.

Affordance giúp client khám phá cách cập nhật tài nguyên từ response hiện tại. Client có thể đọc link `self`, xem template PUT được công bố, tạo request với đúng method và các trường dữ liệu được mô tả. Server vẫn chịu trách nhiệm xác thực, phân quyền và kiểm tra dữ liệu khi request PUT thực sự được gửi tới.

## PUT và affordance khác nhau thế nào?

`PUT` là HTTP method dùng để tạo hoặc thay thế trạng thái của tài nguyên tại URI đích. Trong hợp đồng REST, PUT có tính idempotent: gửi cùng một request nhiều lần phải tạo ra cùng trạng thái đích như gửi một lần. Với endpoint cập nhật, API thường yêu cầu client gửi representation đầy đủ theo quy ước của tài nguyên.

Affordance không phải một HTTP method mới. Nó là metadata gắn với link, mô tả thao tác có thể thực hiện tại URI đó. Một link `self` có thể đồng thời cung cấp affordance cho `PUT`, trong khi `href` vẫn là URI của tài nguyên.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `rel` | Ý nghĩa của link | `self` |
| `href` | URI đích | `/api/employees/42` |
| Affordance | Mô tả thao tác có thể thực hiện | `PUT` tới URI của nhân viên |
| Input metadata | Mô tả dữ liệu client cần gửi | `displayName`, `email`, `department` |

Nếu API chỉ trả một link `self`, client biết nơi đọc tài nguyên nhưng phải biết trước cách cập nhật. Khi link có affordance PUT và response dùng HAL-FORMS, client có thêm thông tin để xây dựng request cập nhật.

## Khai báo endpoint PUT

Trước tiên, controller cần có endpoint PUT với mapping, path variable và request body rõ ràng. Ví dụ, API thay thế thông tin công khai của một nhân viên:

```java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<Void> replace(
        @PathVariable UUID id,
        @Valid @RequestBody ReplaceEmployeeRequest request
) {
    employeeService.replace(id, request);
    return ResponseEntity.noContent().build();
}
```

`ReplaceEmployeeRequest` mô tả input mà client gửi tới PUT:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record ReplaceEmployeeRequest(
        @NotBlank String displayName,
        @Email @NotBlank String email,
        @NotBlank String department
) {}
```

`@Valid` yêu cầu Spring kích hoạt Bean Validation cho request body khi nhận request. Các ràng buộc như `@NotBlank` và `@Email` được kiểm tra ở server; việc affordance mô tả input không thay thế validation này. Cần xác định rõ PUT có ý nghĩa thay thế đầy đủ representation nào, trường nào bắt buộc và cách xử lý giá trị bị bỏ qua.

Nếu endpoint chỉ cập nhật một phần tài nguyên, hãy cân nhắc `PATCH` với semantics và media type phù hợp. Không nên dùng PUT như một bản cập nhật từng trường nếu hợp đồng API định nghĩa PUT là thay thế toàn bộ trạng thái có thể chỉnh sửa.

## Gắn affordance PUT vào self link

Spring HATEOAS cho phép tạo affordance từ lời gọi controller được mô tả bởi `methodOn(...)`. Sau đó, gắn affordance vào link bằng `andAffordance(...)`.

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class EmployeeModelAssembler implements
        RepresentationModelAssembler<Employee, EntityModel<EmployeeResponse>> {

    @Override
    public EntityModel<EmployeeResponse> toModel(Employee employee) {
        UUID id = employee.getId();

        Link self = linkTo(methodOn(EmployeeController.class).one(id))
                .withSelfRel()
                .andAffordance(afford(
                        methodOn(EmployeeController.class).replace(id, null)
                ));

        EmployeeResponse content = new EmployeeResponse(
                id, employee.getDisplayName(), employee.getEmail());
        return EntityModel.of(content, self);
    }
}
```

`methodOn(EmployeeController.class).replace(id, null)` là cách Spring HATEOAS đọc mapping và chữ ký của endpoint PUT. Controller proxy được dùng để thu thập metadata; phương thức `replace(...)` không được thực thi và không có dữ liệu nào được cập nhật ở bước tạo affordance. `null` là placeholder cho tham số request body; kiểu `ReplaceEmployeeRequest` được xác định từ chữ ký phương thức.

`andAffordance(...)` gắn thao tác PUT vào link `self`. Link vẫn có relation `self` và URI của endpoint đọc tài nguyên; affordance mô tả thao tác PUT tại URI đó. Khi controller có nhiều thao tác tại cùng URI, có thể gắn thêm affordance tương ứng vào cùng link.

## Tích hợp assembler và controller

Để response của endpoint GET công bố affordance PUT, assembler tạo content và self link. Controller chỉ cần lấy dữ liệu rồi trả model:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/employees")
public class EmployeeController {

    private final EmployeeService employeeService;
    private final EmployeeModelAssembler assembler;

    public EmployeeController(
            EmployeeService employeeService,
            EmployeeModelAssembler assembler
    ) {
        this.employeeService = employeeService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<EmployeeResponse> one(@PathVariable UUID id) {
        return assembler.toModel(employeeService.findRequired(id));
    }

    @PutMapping(value = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> replace(
            @PathVariable UUID id,
            @Valid @RequestBody ReplaceEmployeeRequest request
    ) {
        employeeService.replace(id, request);
        return ResponseEntity.noContent().build();
    }
}
```

`one(...)` và `replace(...)` cùng ánh xạ tới `/api/employees/{id}`. Assembler tham chiếu tới đúng phương thức PUT để mô tả thao tác cập nhật; controller không cần tự tạo template JSON.

## HAL-FORMS biểu diễn affordance PUT

HAL cơ bản biểu diễn relation và `href` trong `_links`, nhưng không có cấu trúc chuẩn để mô tả đầy đủ input template cho thao tác PUT. HAL-FORMS bổ sung `_templates`, trong đó mỗi template mô tả method, target, content type và các property đầu vào.

Client yêu cầu HAL-FORMS bằng media type:

```http
GET /api/employees/42 HTTP/1.1
Accept: application/prs.hal-forms+json
```

Response minh họa có thể chứa:

```json
{
  "id": "42",
  "displayName": "Nguyen An",
  "email": "an@example.com",
  "department": "Engineering",
  "_links": {
    "self": {
      "href": "/api/employees/42"
    }
  },
  "_templates": {
    "default": {
      "method": "PUT",
      "target": "/api/employees/42",
      "contentType": "application/json",
      "properties": [
        { "name": "displayName", "required": true },
        { "name": "email", "required": true },
        { "name": "department", "required": true }
      ]
    }
  }
}
```

Đây là response minh họa để giải thích cấu trúc HAL-FORMS. Các property và metadata thực tế được tạo dựa trên chữ ký endpoint, kiểu request body, Jackson mapping và cấu hình Spring HATEOAS. Hãy kiểm tra response thực tế của phiên bản thư viện đang dùng thay vì giả định mọi annotation validation đều được chuyển thành thuộc tính template giống hệt nhau.

Với template `default`, client biết method là `PUT`, target là URI cập nhật và content type là JSON. Các property mô tả những trường input mà template công bố. Client có thể dùng metadata đó để tạo biểu mẫu cập nhật mà không phải tự đoán tên trường từ response GET.

## Cấu hình và thương lượng media type HAL-FORMS

Spring HATEOAS hỗ trợ HAL-FORMS như một media type hypermedia. Spring Boot cung cấp auto-configuration cho tích hợp Spring HATEOAS; khi cần HAL-FORMS, hãy xác nhận media type và converter tương ứng được bật trong cấu hình ứng dụng. Với cấu hình Spring MVC tự quản lý, có thể bật rõ loại hypermedia:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
public class HypermediaConfiguration {
}
```

Endpoint trả representation cần cho phép media type HAL-FORMS. Có thể khai báo `produces` nếu muốn giới hạn endpoint:

```java
@GetMapping(
        value = "/{id}",
        produces = "application/prs.hal-forms+json"
)
public EntityModel<EmployeeResponse> one(@PathVariable UUID id) {
    return assembler.toModel(employeeService.findRequired(id));
}
```

Nếu ứng dụng cần hỗ trợ nhiều dạng response, cấu hình converter và media type để đáp ứng những giá trị `Accept` mà client gửi. Khi client yêu cầu `application/hal+json`, server có thể trả HAL thông thường mà không biểu diễn input template HAL-FORMS. Client cần yêu cầu đúng media type nếu muốn đọc `_templates`.

## Dùng input DTO để mô tả các trường PUT

Affordance được suy ra từ endpoint mà nó tham chiếu. Vì vậy, chữ ký phương thức PUT cần thể hiện đúng kiểu request body. DTO riêng giúp kiểm soát trường nào client được phép gửi:

```java
public record ReplaceEmployeeRequest(
        String displayName,
        String email,
        String department
) {}
```

Không dùng trực tiếp entity persistence làm request body nếu entity có trường nội bộ như `id`, `createdAt`, `salaryGrade` hoặc cờ quản trị mà client không được sửa. DTO cập nhật xác định ranh giới dữ liệu mà endpoint cho phép nhận.

Jackson annotation như `@JsonProperty` và `@JsonIgnore` ảnh hưởng tên và khả năng tuần tự hóa property. Khi thay đổi DTO hoặc Jackson configuration, hãy kiểm tra lại template HAL-FORMS vì danh sách property công bố có thể thay đổi theo metadata được introspect.

Bean Validation như `@NotBlank`, `@Email` và `@Size` vẫn có nhiệm vụ kiểm tra request tại server. Template affordance hỗ trợ client hiểu input nhưng không đảm bảo request hợp lệ. Server cần trả lỗi validation phù hợp nếu dữ liệu gửi lên vi phạm quy tắc.

## Phân biệt affordance PUT và affordance PATCH

PUT thường mô tả thay thế trạng thái tài nguyên theo hợp đồng đã công bố. PATCH thường mô tả cập nhật một phần và cần xác định rõ định dạng patch, ví dụ JSON Merge Patch hoặc JSON Patch. Không nên suy ra rằng hai method có cùng danh sách trường hoặc cùng cách xử lý trường bị bỏ qua.

| Tiêu chí | PUT | PATCH |
|---|---|---|
| Ý nghĩa thường dùng | Thay thế representation có thể chỉnh sửa | Áp dụng thay đổi một phần |
| Tính idempotent | Có theo semantics HTTP | Không được bảo đảm cho mọi định dạng patch |
| Input | Thường là representation thay thế | Tài liệu hóa các thao tác hoặc trường cần thay đổi |
| Affordance | Template có method `PUT` | Template có method `PATCH` và content type patch tương ứng |

Affordance chỉ mô tả endpoint được công bố. Việc chọn PUT hay PATCH phải xuất phát từ semantics của API và cách server xử lý request body.

## Kiểm thử affordance PUT

Kiểm thử cần xác nhận response có link `self`, template PUT và các property input mong đợi. Với MockMvc, yêu cầu HAL-FORMS:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;

mockMvc.perform(get("/api/employees/{id}", employeeId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.default.method").value("PUT"))
    .andExpect(jsonPath("$._templates.default.properties[0].name")
            .value("displayName"));
```

Tên template và thứ tự property trong response có thể phụ thuộc cấu hình và phiên bản. Với test hợp đồng dài hạn, nên tìm property theo tên hoặc kiểm tra tập hợp property thay vì phụ thuộc vào thứ tự mảng nếu thứ tự không phải yêu cầu của API.

Có thể kiểm tra request PUT thực sự được xử lý và validation hoạt động:

```java
mockMvc.perform(put("/api/employees/{id}", employeeId)
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "displayName": "Nguyen An",
                  "email": "an@example.com",
                  "department": "Engineering"
                }
                """))
    .andExpect(status().isNoContent());
```

Test đầu xác nhận affordance được công bố trong response; test thứ hai xác nhận endpoint PUT thực sự hoạt động. Cần có thêm test dữ liệu không hợp lệ để xác nhận Bean Validation và exception handler trả lỗi đúng hợp đồng.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ trả link `self` | Client biết URI nhưng không biết cách cập nhật | Gắn affordance PUT vào link |
| Gắn affordance vào sai mapping | Template trỏ tới method hoặc URI không đúng | Dùng `methodOn(...)` với đúng phương thức PUT |
| Dùng entity làm request body | Có thể công bố trường nội bộ hoặc trường không được phép sửa | Tạo DTO input riêng |
| Dùng PUT cho cập nhật một phần mà không định nghĩa semantics | Client và server hiểu khác nhau về trường bị bỏ qua | Chọn PUT thay thế đầy đủ hoặc PATCH có semantics rõ |
| Chỉ kiểm tra `_links` | Không phát hiện template hoặc input property bị thiếu | Yêu cầu HAL-FORMS và kiểm tra `_templates` |
| Client chỉ yêu cầu HAL JSON | Không nhận metadata template HAL-FORMS | Thương lượng `application/prs.hal-forms+json` |
| Xem affordance là cơ chế phân quyền | Client có thể gọi endpoint trực tiếp | Xác thực và phân quyền ở endpoint PUT |
| Cho rằng template thay thế validation | Request vẫn có thể chứa dữ liệu sai | Dùng Bean Validation và kiểm thử lỗi |

## Quy trình triển khai affordance PUT

1. Xác định tài nguyên và URI dùng chung cho GET và PUT.
2. Khai báo endpoint `@PutMapping` với request DTO thể hiện input được phép cập nhật.
3. Định nghĩa semantics PUT rõ ràng, gồm trường bắt buộc và cách thay thế dữ liệu.
4. Tạo self link bằng `linkTo(methodOn(...).one(id))`.
5. Gắn affordance bằng `andAffordance(afford(methodOn(...).replace(id, null)))`.
6. Trả representation qua endpoint GET và cấu hình HAL-FORMS khi cần công bố template.
7. Kiểm thử `_links`, `_templates`, method, content type và các property input.
8. Kiểm thử endpoint PUT riêng cho trường hợp hợp lệ, validation lỗi và quyền truy cập.

## Kết luận

Affordance cho PUT giúp response hypermedia mô tả thao tác thay thế tài nguyên cùng URI, method và dữ liệu đầu vào cần thiết. Spring HATEOAS tạo affordance từ chữ ký `@PutMapping` bằng `afford(methodOn(...))`, rồi gắn nó vào self link. Khi response được tuần tự hóa theo HAL-FORMS, client có thể khám phá template PUT trong `_templates` và xây dựng request phù hợp. DTO input, semantics PUT rõ ràng, validation ở server và kiểm thử cả template lẫn endpoint giúp hợp đồng cập nhật tài nguyên dễ khám phá và đáng tin cậy.
