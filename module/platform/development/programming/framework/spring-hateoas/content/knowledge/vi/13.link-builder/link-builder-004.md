# Building link từ controller

Trong REST API dùng hypermedia, server nên công bố các liên kết để client khám phá tài nguyên và bước tương tác tiếp theo. Với Spring HATEOAS và Spring MVC, `WebMvcLinkBuilder` giúp tạo URI dựa trên mapping của controller và handler method. Nhờ vậy, mã dựng representation không cần tự ghép chuỗi URL theo cấu trúc endpoint.

Hai API thường dùng nhất là `linkTo(...)` và `methodOn(...)`. `linkTo(...)` bắt đầu quá trình dựng link từ controller hoặc lời gọi handler; `methodOn(...)` tạo một proxy mô tả lời gọi đến handler để Spring HATEOAS xác định mapping và các giá trị đường dẫn. Sau khi tạo link builder, ứng dụng gắn quan hệ bằng `withSelfRel()` hoặc `withRel(...)` rồi thêm link vào `RepresentationModel`, `EntityModel` hay `CollectionModel`.

## 1. Vì sao nên tạo link từ controller?

Giả sử API có endpoint chi tiết nhân viên:

```java
@RestController
@RequestMapping("/employees")
class EmployeeController {

    @GetMapping("/{id}")
    EmployeeRepresentation one(@PathVariable Long id) {
        // Lấy nhân viên theo id
    }
}
```

Nếu tự tạo URI bằng chuỗi, mã dựng response có thể viết:

```java
String href = "/employees/" + employee.getId();
```

Cách này gắn chặt code với đường dẫn hiện tại. Khi class-level mapping, path variable hoặc context path thay đổi, các vị trí nối chuỗi có thể bị bỏ sót. Ngoài ra, tự nối chuỗi không tự xử lý đầy đủ việc encode các thành phần URI.

Spring HATEOAS cho phép tham chiếu trực tiếp mapping của controller:

```java
linkTo(methodOn(EmployeeController.class)
        .one(employee.getId()))
        .withSelfRel();
```

URI được xây dựng từ mapping của ứng dụng. Khi mapping thay đổi, link được tạo theo mapping mới, giúp giảm sự phụ thuộc vào cấu trúc URL được lặp lại trong mã nguồn.

## 2. WebMvcLinkBuilder, linkTo và methodOn

Với Spring MVC, class thường dùng là `WebMvcLinkBuilder` trong package `org.springframework.hateoas.server.mvc`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Hai cách tạo link cơ bản:

| Cách gọi | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| `linkTo(EmployeeController.class)` | Bắt đầu từ mapping của controller | Tạo link đến gốc controller hoặc nối thêm path segment |
| `linkTo(methodOn(EmployeeController.class).one(id))` | Bắt đầu từ mapping của handler cụ thể | Tạo link đến endpoint có path variable hoặc mapping cụ thể |

`methodOn(...)` không gọi thực thi phần thân phương thức controller. Nó tạo một proxy để ghi nhận phương thức và tham số được tham chiếu, từ đó Spring HATEOAS đọc mapping annotations và dựng URI tương ứng. Vì vậy, không đặt logic nghiệp vụ, truy vấn dữ liệu hay side effect trong biểu thức dùng để dựng link.

Ví dụ, khi gọi:

```java
linkTo(methodOn(EmployeeController.class).one(42L)).withSelfRel();
```

Spring HATEOAS sử dụng `@RequestMapping("/employees")`, `@GetMapping("/{id}")` và giá trị `42` của `@PathVariable` để tạo link đến resource nhân viên có ID `42`.

## 3. Tạo link bằng methodOn

Đây là cách thường được ưu tiên vì nó gắn link với handler method cụ thể:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(EmployeeController.class)
        .one(employee.getId()))
        .withSelfRel();
```

Các bước diễn ra:

1. `methodOn(EmployeeController.class)` tạo proxy cho controller.
2. `.one(employee.getId())` mô tả handler cần tham chiếu và truyền giá trị path variable.
3. `linkTo(...)` đọc mapping của handler để tạo link builder.
4. `withSelfRel()` gắn relation chuẩn `self` cho link.

Nếu controller có mapping như sau:

```java
@RestController
@RequestMapping("/employees")
class EmployeeController {

    @GetMapping("/{id}")
    EntityModel<EmployeeRepresentation> one(@PathVariable("id") Long id) {
        // ...
    }
}
```

Thì lời gọi `one(42L)` tạo link có path `/employees/42` (cộng với context path nếu ứng dụng có cấu hình). Host và scheme được xác định theo request context hoặc cơ chế tạo link đang dùng.

## 4. Tạo link từ class-level mapping và slash

Khi chỉ cần mapping gốc của controller, có thể dùng `linkTo(Controller.class)`:

```java
Link employees = linkTo(EmployeeController.class)
        .withRel("employees");
```

Nếu cần thêm một segment vào mapping gốc, dùng `slash(...)`:

```java
Link self = linkTo(EmployeeController.class)
        .slash(employee.getId())
        .withSelfRel();
```

Với controller có `@RequestMapping("/employees")`, link trên tạo đường dẫn chi tiết dựa trên mapping lớp và ID. `slash(...)` hữu ích cho các URI đơn giản có cấu trúc rõ ràng. Khi endpoint đã có handler method cụ thể, `methodOn(...)` thường diễn đạt ý định tốt hơn vì Spring HATEOAS có thể lấy path mapping và tham số từ chính handler.

Không nên nối `slash(...)` tùy tiện nhiều lần để mô phỏng một endpoint phức tạp nếu đã có handler method tương ứng. Tham chiếu mapping của handler giúp link ít bị lệch khi endpoint thay đổi.

## 5. Gắn relation cho link

Sau khi tạo link builder, cần xác định relation (*link relation*) để client hiểu ý nghĩa của liên kết:

```java
Link self = linkTo(methodOn(EmployeeController.class)
        .one(employee.getId())).withSelfRel();

Link department = linkTo(methodOn(DepartmentController.class)
        .one(employee.getDepartmentId())).withRel("department");

Link collection = linkTo(methodOn(EmployeeController.class)
        .all()).withRel("employees");
```

| Method | Kết quả |
| --- | --- |
| `withSelfRel()` | Gắn relation `self` |
| `withRel("department")` | Gắn relation tùy chỉnh `department` |
| `withRel(IanaLinkRelations.NEXT)` | Gắn relation chuẩn `next` |

Với relation chuẩn, có thể dùng hằng số trong `IanaLinkRelations` thay cho chuỗi tự gõ:

```java
import org.springframework.hateoas.IanaLinkRelations;

Link next = linkTo(methodOn(EmployeeController.class)
        .all()).withRel(IanaLinkRelations.NEXT);
```

Relation là một phần của hợp đồng API. Nên dùng tên ổn định và nhất quán; client nên dựa vào relation để hiểu ý nghĩa link thay vì phân tích chuỗi URI.

## 6. Tích hợp link builder vào RepresentationModelAssembler

Trong ứng dụng thực tế, logic dựng link thường được đặt trong assembler để controller không phải lặp lại việc chuyển đổi dữ liệu và tạo link ở nhiều endpoint.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class EmployeeModelAssembler implements
        RepresentationModelAssembler<Employee, EntityModel<EmployeeRepresentation>> {

    @Override
    public EntityModel<EmployeeRepresentation> toModel(Employee employee) {
        return EntityModel.of(
                EmployeeRepresentation.from(employee),
                linkTo(methodOn(EmployeeController.class)
                        .one(employee.getId())).withSelfRel(),
                linkTo(methodOn(DepartmentController.class)
                        .one(employee.getDepartmentId())).withRel("department"));
    }
}
```

Assembler nhận đối tượng `Employee`, chuyển dữ liệu công khai thành `EmployeeRepresentation`, rồi gắn link `self` và `department`. Các class `Employee`, `EmployeeRepresentation`, `EmployeeController` và `DepartmentController` là các kiểu của ứng dụng minh họa; handler được tham chiếu cần có mapping phù hợp.

Controller sử dụng assembler:

```java
@RestController
@RequestMapping("/employees")
class EmployeeController {

    private final EmployeeService employeeService;
    private final EmployeeModelAssembler assembler;

    EmployeeController(EmployeeService employeeService,
                       EmployeeModelAssembler assembler) {
        this.employeeService = employeeService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<EmployeeRepresentation> one(@PathVariable Long id) {
        return assembler.toModel(employeeService.getRequired(id));
    }
}
```

Controller chỉ truy vấn service và trả representation được assembler tạo. Việc tạo URI vẫn dựa trên mapping của controller, nên assembler có thể tham chiếu `EmployeeController.class` mà không cần tự nối path.

## 7. Tạo link cho collection

Một endpoint danh sách thường trả `CollectionModel` với link `self` ở cấp collection và link `self` cho từng phần tử:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

@GetMapping
CollectionModel<EntityModel<EmployeeRepresentation>> all() {
    List<EntityModel<EmployeeRepresentation>> employees =
            employeeService.findAll().stream()
                    .map(assembler::toModel)
                    .toList();

    return CollectionModel.of(employees,
            linkTo(methodOn(EmployeeController.class).all()).withSelfRel());
}
```

Link `self` ở root trỏ đến collection `/employees`; mỗi `EntityModel` có link `self` đến `/employees/{id}`. Đây là hai cấp tài nguyên khác nhau nên cần hai link riêng.

Với collection có phân trang, có thể dùng `PagedResourcesAssembler` để tạo `PagedModel` và các link điều hướng. Link builder tham chiếu handler của collection; việc giữ filter, sort và tham số phân trang cần được kiểm tra theo cách endpoint nhận request.

## 8. Path variable và tham số request

Khi handler có `@PathVariable`, truyền giá trị tương ứng vào lời gọi `methodOn(...)` để Spring HATEOAS dựng URI cụ thể:

```java
@GetMapping("/{employeeId}/projects/{projectId}")
ProjectRepresentation project(
        @PathVariable Long employeeId,
        @PathVariable Long projectId) {
    // ...
}
```

Tạo link:

```java
Link projectLink = linkTo(methodOn(EmployeeController.class)
        .project(employee.getId(), project.getId()))
        .withRel("project");
```

Với tham số query, ví dụ `@RequestParam`, hãy bảo đảm giá trị cần thiết được giữ trong link. Có thể tham chiếu handler có các tham số tương ứng bằng `methodOn(...)`; với truy vấn phức tạp hoặc URI được xây dựng riêng, có thể dùng `UriComponentsBuilder` để thêm query parameter và encode giá trị đúng cách. Không nên giả định mọi tham số Java đều tự động trở thành query parameter; mapping annotations quyết định cách Spring MVC diễn giải chúng.

Ví dụ handler tìm kiếm:

```java
@GetMapping("/search")
CollectionModel<EntityModel<EmployeeRepresentation>> search(
        @RequestParam String department,
        @RequestParam(required = false) String status) {
    // ...
}
```

Link đến kết quả tìm kiếm có thể tham chiếu handler cùng các giá trị query:

```java
Link searchLink = linkTo(methodOn(EmployeeController.class)
        .search("engineering", "ACTIVE"))
        .withRel("search");
```

Khi kiểm thử, hãy xác nhận link thực tế chứa các tham số cần thiết và không làm mất filter hoặc sort.

## 9. Link tuyệt đối và request context

Trong request Spring MVC, `WebMvcLinkBuilder` có thể sử dụng thông tin request hiện tại để tạo URI với scheme, host, port và context path phù hợp. Điều này giúp link phản ánh địa chỉ mà client dùng để gọi API.

Khi ứng dụng chạy sau reverse proxy hoặc API gateway, địa chỉ bên ngoài có thể khác địa chỉ nội bộ. Ví dụ, client gọi `https://api.example.test/platform/employees`, trong khi proxy chuyển tiếp đến ứng dụng ở `http://employee-service:8080/employees`. Nếu server không nhận diện đúng forwarded headers, link được tạo có thể chứa host nội bộ, scheme HTTP hoặc thiếu prefix `/platform`.

Hãy cấu hình forwarded headers theo hạ tầng và chỉ tin cậy chúng khi request đến từ proxy được quản lý. Không lấy host từ header tùy ý do client gửi lên để tạo URI công khai. Với tác vụ nền không có request context, dùng base URI công khai lấy từ cấu hình ứng dụng và xây link theo cách phù hợp.

## 10. Link builder không tự mô tả đầy đủ hành động HTTP

`linkTo(...)` và `methodOn(...)` tập trung tạo URI dựa trên mapping của controller. `withRel(...)` gắn ý nghĩa cho liên kết. Chỉ từ một `Link` cơ bản, client không nhất thiết biết HTTP method, schema của request body hoặc các trường cần nhập cho một hành động.

Ví dụ, relation `approve` có thể trỏ đến endpoint phê duyệt, nhưng client cần hợp đồng bổ sung để biết endpoint nhận `POST`, cần trường nào và điều kiện nào. Nếu muốn mô tả khả năng thao tác phong phú hơn, Spring HATEOAS có cơ chế affordance kết hợp với media type hỗ trợ metadata đó. Không nên giả định mọi link HAL cơ bản đều tự mô tả đầy đủ request.

Ngoài ra, link chỉ quảng bá khả năng điều hướng hoặc hành động tại thời điểm representation được tạo. Server vẫn phải kiểm tra xác thực, phân quyền và điều kiện nghiệp vụ khi nhận request theo link.

## 11. Kiểm thử link được tạo từ controller

Kiểm thử tích hợp với `MockMvc` giúp xác nhận URI được sinh ra đúng theo mapping và được serialize vào HAL:

```java
mockMvc.perform(get("/employees/{id}", 42L)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith("/employees/42")))
    .andExpect(jsonPath("$._links.department.href").exists());
```

Với endpoint collection:

```java
mockMvc.perform(get("/employees")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith("/employees")))
    .andExpect(jsonPath("$._embedded.employees[0]._links.self.href")
            .exists());
```

Đây là ví dụ minh họa; test thực tế cần service, dữ liệu và HAL converter phù hợp. Relation `_embedded.employees` phụ thuộc relation được cấu hình cho kiểu model, chẳng hạn bằng `@Relation`. Nếu test có host hoặc context path cụ thể, hãy xác nhận toàn bộ URI; nếu không, có thể kiểm tra path và query để tránh phụ thuộc môi trường.

Các tình huống nên kiểm thử:

- Mapping ở cấp class và method đều được đưa vào URI.
- Path variable được thay bằng giá trị đúng.
- Query parameter cần thiết được giữ và encode đúng.
- Link `self` và link quan hệ trỏ đến đúng handler.
- Collection có link cấp collection và link riêng cho phần tử.
- URI phản ánh đúng host, scheme và context path khi chạy sau proxy.
- Relation được giữ ổn định như hợp đồng API công bố.

## 12. Lỗi thường gặp

**Tự nối chuỗi URI:** thay đổi mapping dễ làm link sai hoặc thiếu context path. Ưu tiên `linkTo(methodOn(...))` khi có handler tương ứng.

**Gọi nhầm handler khi dùng methodOn:** nếu truyền sai tham số hoặc tham chiếu sai phương thức, URI có thể không khớp endpoint mong muốn. Đối chiếu lời gọi với mapping thực tế.

**Cho rằng methodOn thực thi controller:** `methodOn` tạo proxy mô tả lời gọi để dựng link. Không dùng nó để chạy nghiệp vụ hoặc truy vấn.

**Nhầm relation với path:** relation mô tả ý nghĩa liên kết; URI là đích đến. Client nên dựa vào relation thay vì phân tích path.

**Bỏ sót query parameter:** link tìm kiếm hoặc phân trang có thể làm mất filter và trả về tập kết quả khác. Kiểm tra URI thực tế sau khi serialize.

**Tin cậy forwarded headers từ mọi nguồn:** host giả có thể xuất hiện trong link tuyệt đối. Chỉ tin cậy header do proxy được quản lý chuyển tiếp.

**Nghĩ link là cơ chế phân quyền:** client có thể lưu hoặc tự gọi URI. Endpoint vẫn phải kiểm tra quyền và trạng thái nghiệp vụ.

## 13. Checklist xây link từ controller

- Dùng `WebMvcLinkBuilder` từ package `org.springframework.hateoas.server.mvc`.
- Ưu tiên `linkTo(methodOn(Controller.class).handler(...))` khi tham chiếu endpoint cụ thể.
- Dùng `linkTo(Controller.class)` và `slash(...)` khi cần bắt đầu từ mapping class-level.
- Truyền đúng giá trị path variable và giữ các query parameter cần thiết.
- Gắn relation rõ ràng bằng `withSelfRel()` hoặc `withRel(...)`.
- Tập trung logic dựng representation trong assembler khi được tái sử dụng.
- Không đặt logic nghiệp vụ hoặc side effect trong biểu thức `methodOn(...)`.
- Cấu hình request context và forwarded headers phù hợp với reverse proxy.
- Kiểm thử `href`, relation, path, query và context path trong response.
- Giữ việc xác thực, phân quyền và kiểm tra trạng thái ở endpoint/service.

Spring HATEOAS giúp liên kết giữa tài nguyên được tạo từ mapping thực tế của controller. Khi dùng `linkTo(...)`, `methodOn(...)` và relation một cách nhất quán, ứng dụng có thể công bố hypermedia link đáng tin cậy, giảm mã ghép URI thủ công và giúp client điều hướng theo hợp đồng API thay vì phụ thuộc vào cấu trúc URL được mã hóa sẵn.
