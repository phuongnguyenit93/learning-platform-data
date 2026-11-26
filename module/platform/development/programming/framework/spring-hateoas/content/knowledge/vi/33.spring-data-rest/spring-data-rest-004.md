# Association resource

Spring Data REST có thể tự động công bố một tài nguyên con cho mỗi association của một item resource. Tài nguyên con này được gọi là **association resource**. Nó cho phép client đọc hoặc thay đổi quan hệ giữa hai tài nguyên bằng các HTTP request riêng, thay vì gửi lại toàn bộ entity cha.

Ví dụ, một nhân viên có một quản lý trực tiếp và nhiều vai trò. Khi repository của `Employee` được export, Spring Data REST có thể công bố các link `manager` và `roles` trên representation của nhân viên. Client theo link để đọc association, gán một quản lý hoặc thêm vai trò bằng URI của tài nguyên đích.

Bài học này giải thích cấu trúc và vòng đời của association resource, cách Spring Data REST tạo link, sự khác nhau giữa quan hệ đơn và collection association, cách dùng `GET`, `PUT`, `POST`, `DELETE` với media type `text/uri-list`, cách tùy chỉnh hoặc ẩn association, và cách kiểm thử hợp đồng qua HTTP.

## 1. Association resource là gì?

Trong mô hình miền, một entity thường tham chiếu đến entity khác. Ví dụ:

- Một nhân viên thuộc về một phòng ban.
- Một nhân viên có một quản lý trực tiếp.
- Một nhân viên có nhiều vai trò.
- Một đơn hàng có nhiều dòng hàng.

Spring Data REST nhận diện các association được khai báo trên domain type và tạo association resource dưới item resource tương ứng. Đường dẫn mặc định được tạo từ đường dẫn item và tên property association.

Ví dụ:

~~~text
GET /employees/1
    |
    +-- self     -> /employees/1
    +-- manager  -> /employees/1/manager
    +-- roles    -> /employees/1/roles
~~~

Trong đó:

- `/employees/1` là item resource của nhân viên.
- `/employees/1/manager` là association resource của quan hệ quản lý.
- `/employees/1/roles` là association resource của tập hợp vai trò.

Association resource đại diện cho **quan hệ từ một entity cha đến entity hoặc tập hợp entity liên quan**. Nó không phải một bản sao của tài nguyên đích và cũng không phải endpoint xóa tài nguyên đích.

Spring Data REST công bố association resource cho các association của domain type được export. Tên path và relation mặc định lấy từ tên property; có thể tùy chỉnh bằng `@RestResource` trên property.

## 2. Mô hình ví dụ: Employee và Role

Giả sử ứng dụng quản lý nhân viên. Mỗi nhân viên có thể có một quản lý trực tiếp và nhiều vai trò.

Entity Employee:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;

import org.springframework.data.rest.core.annotation.RestResource;

@Entity
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "manager_id")
    private Employee manager;

    @ManyToMany
    @JoinTable(
        name = "employee_role",
        joinColumns = @JoinColumn(name = "employee_id"),
        inverseJoinColumns = @JoinColumn(name = "role_id")
    )
    @RestResource(path = "roles", rel = "roles")
    private Set<Role> roles = new LinkedHashSet<>();

    protected Employee() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Employee getManager() {
        return manager;
    }

    public void setManager(Employee manager) {
        this.manager = manager;
    }

    public Set<Role> getRoles() {
        return roles;
    }
}
~~~

Entity Role:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToMany;

@Entity
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToMany(mappedBy = "roles")
    private Set<Employee> employees = new LinkedHashSet<>();

    protected Role() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong ví dụ này:

- `Employee.manager` là association to-one vì mỗi nhân viên có tối đa một quản lý.
- `Employee.roles` là association to-many vì một nhân viên có thể có nhiều vai trò.
- `Employee.roles` là phía sở hữu của quan hệ many-to-many do khai báo `@JoinTable`.
- `Role.employees` là phía inverse vì dùng `mappedBy = "roles"`.

Spring Data REST không tự quyết định quy tắc nghiệp vụ của quan hệ. Mapping JPA vẫn quyết định cách association được lưu trong cơ sở dữ liệu; ràng buộc miền và quyền thao tác vẫn phải được bảo vệ ở server.

## 3. Export repository để Spring Data REST tạo resource

Repository của hai domain type có thể được export như sau:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "employees",
    collectionResourceRel = "employees"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "roles",
    collectionResourceRel = "roles"
)
public interface RoleRepository
        extends JpaRepository<Role, Long> {
}
~~~

Với cấu hình mặc định, Spring Data REST export collection resource và item resource cho các repository phù hợp. Ví dụ:

~~~text
/employees
/employees/{id}
/roles
/roles/{id}
~~~

Nếu ứng dụng đặt base path:

~~~properties
spring.data.rest.base-path=/api
~~~

thì các đường dẫn công khai sẽ có dạng:

~~~text
/api/employees
/api/employees/{id}
/api/roles
/api/roles/{id}
~~~

Các ví dụ tiếp theo giả định base path là `/api`. Khi chạy ứng dụng, hãy khám phá root resource và theo các link được trả về thay vì tự giả định host hoặc base path.

## 4. Association link xuất hiện trên item resource

Khi client đọc một nhân viên:

~~~http
GET /api/employees/1
Accept: application/hal+json
~~~

HAL response có thể chứa dữ liệu nhân viên và các link association:

~~~json
{
  "id": 1,
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees/1"
    },
    "employee": {
      "href": "http://localhost:8080/api/employees/1"
    },
    "manager": {
      "href": "http://localhost:8080/api/employees/1/manager"
    },
    "roles": {
      "href": "http://localhost:8080/api/employees/1/roles"
    }
  }
}
~~~

Các relation `manager` và `roles` dẫn đến association resource. Client không cần biết tên property Java hoặc tự ghép URI; nó đọc relation trong `_links` rồi theo `href`.

Tên relation trong response phụ thuộc metadata export và cấu hình. Trong ví dụ, `@RestResource(path = "roles", rel = "roles")` đặt rõ cả path và relation cho association roles.

Một association link có thể xuất hiện dù client chưa tải dữ liệu association. Đây là điều có chủ đích: representation item cung cấp khả năng khám phá, còn client quyết định khi nào cần gọi association resource.

## 5. Phân biệt association resource với embedded resource

Association resource và embedded resource giải quyết hai nhu cầu khác nhau.

| Cách biểu diễn | Ý nghĩa | Cách client lấy dữ liệu |
|---|---|---|
| Association link | Công bố URI để truy cập quan hệ | Gửi request đến association resource |
| Embedded resource | Đưa representation của tài nguyên liên quan vào response hiện tại | Đọc dữ liệu ngay trong response |
| Trường ID trong JSON | Dữ liệu định danh theo hợp đồng ứng dụng | Client vẫn cần URI hoặc link để điều hướng |

Ví dụ response item chỉ có association link:

~~~json
{
  "id": 1,
  "name": "Nguyen An",
  "_links": {
    "manager": {
      "href": "/api/employees/1/manager"
    }
  }
}
~~~

Client gọi link manager khi cần đọc quản lý. Nếu association được nhúng trong projection hoặc cấu hình representation, dữ liệu có thể xuất hiện trực tiếp trong `_embedded` hoặc dưới một thuộc tính tương ứng. Việc nhúng không làm mất ý nghĩa của association resource nếu link vẫn được công bố.

Không nên nhầm association resource với một endpoint tùy chỉnh do ứng dụng tự viết. Association resource là cơ chế export tự động của Spring Data REST dựa trên mapping domain và repository.

## 6. Các HTTP method được hỗ trợ

Association resource hỗ trợ `GET`, `PUT`, `POST` và `DELETE`. Mỗi method có semantics riêng:

| Method | Phạm vi | Media type request | Tác dụng |
|---|---|---|---|
| GET | To-one và collection | Không cần body | Đọc trạng thái association |
| PUT | To-one hoặc collection | `text/uri-list` | Gắn tài nguyên được URI trỏ đến vào association |
| POST | Chỉ collection association | `text/uri-list` | Thêm phần tử mới vào collection association |
| DELETE | Association resource | Không cần body | Gỡ liên kết association |

Các điểm cần nhớ:

- `GET` trả trạng thái quan hệ; response có thể là `application/hal+json` hoặc `application/json`.
- `PUT` và `POST` nhận URI của tài nguyên đích qua `text/uri-list`, không nhận một JSON entity tùy ý.
- `POST` chỉ được hỗ trợ cho collection association và dùng để thêm phần tử.
- `DELETE` gỡ association; nó không có nghĩa là xóa entity ở repository của tài nguyên đích.
- Gửi nhiều URI cho association to-one sẽ nhận `400 Bad Request`.
- Association không optional có thể từ chối thao tác gỡ với `405 Method Not Allowed`.

Hãy xem association resource như một endpoint quản lý quan hệ. Việc tạo, sửa hoặc xóa entity đích vẫn thuộc collection/item resource của chính entity đó.

## 7. Đọc association to-one bằng GET

Với quan hệ manager, client theo link từ item resource:

~~~http
GET /api/employees/1/manager
Accept: application/hal+json
~~~

Association resource trả trạng thái quan hệ hiện tại. Nếu nhân viên 1 có quản lý là nhân viên 7, representation được trả về sẽ mô tả tài nguyên quản lý theo cấu hình export.

Ví dụ dạng response:

~~~json
{
  "id": 7,
  "name": "Tran Binh",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees/7"
    }
  }
}
~~~

Điểm quan trọng là response mô tả đối tượng đang được liên kết. Client có thể theo self link của manager để truy cập item resource đầy đủ.

Nếu quan hệ chưa được gán, response có thể thể hiện trạng thái rỗng theo cách serializer và phiên bản Spring Data REST xử lý. Client cần xử lý trường hợp association chưa có giá trị thay vì giả định luôn có một manager.

## 8. Gán hoặc thay manager bằng PUT

Để gán manager cho nhân viên, gửi URI của tài nguyên manager đến association resource:

~~~http
PUT /api/employees/1/manager
Content-Type: text/uri-list

http://localhost:8080/api/employees/7
~~~

Ví dụ bằng curl:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/api/employees/7" \
  http://localhost:8080/api/employees/1/manager
~~~

Spring Data REST đọc URI, phân giải tài nguyên đích và gắn nó vào association manager của nhân viên 1.

Đây là request cập nhật quan hệ. Body không phải JSON:

~~~json
{
  "id": 7
}
~~~

Nếu gửi JSON thay vì `text/uri-list`, request không khớp media type mà association resource yêu cầu.

Vì manager là to-one association, chỉ gửi một URI. Nếu gửi nhiều URI, Spring Data REST trả `400 Bad Request`. Nếu cần bỏ manager hiện tại, dùng DELETE trên association resource khi mapping cho phép association không có giá trị.

## 9. Đọc collection association bằng GET

Để đọc các vai trò của nhân viên:

~~~http
GET /api/employees/1/roles
Accept: application/hal+json
~~~

Response có thể chứa collection representation:

~~~json
{
  "_embedded": {
    "roles": [
      {
        "id": 2,
        "name": "REVIEWER",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/roles/2"
          }
        }
      },
      {
        "id": 3,
        "name": "APPROVER",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/roles/3"
          }
        }
      }
    ]
  }
}
~~~

Tên relation trong `_embedded` có thể được tùy chỉnh bằng metadata relation của resource hoặc repository. Hãy đọc response thực tế và dùng link thay vì hard-code tên key hoặc URI trong client.

Nếu collection lớn, cần cân nhắc pagination hoặc thiết kế riêng cho việc truy vấn. Association resource đọc trạng thái association hiện tại; nó không tự biến mọi collection thành một API tìm kiếm có bộ lọc tùy ý.

## 10. Thêm phần tử vào collection bằng POST

Để thêm vai trò APPROVER vào nhân viên 1, gửi URI của role đến association resource:

~~~http
POST /api/employees/1/roles
Content-Type: text/uri-list

http://localhost:8080/api/roles/3
~~~

Ví dụ curl:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/api/roles/3" \
  http://localhost:8080/api/employees/1/roles
~~~

`POST` được hỗ trợ cho collection association và thêm phần tử mới vào collection. Có thể gửi nhiều URI, mỗi URI trên một dòng:

~~~text
http://localhost:8080/api/roles/3
http://localhost:8080/api/roles/4
~~~

Đây là thao tác gắn tài nguyên đã tồn tại vào collection. Nó không tạo mới role. Nếu cần tạo role mới, client phải dùng collection resource của repository roles, sau đó theo URI tài nguyên được tạo và liên kết nó với employee.

Với collection association, dùng POST khi mục tiêu là thêm phần tử mà không gửi lại toàn bộ entity cha.

## 11. Gỡ association bằng DELETE

DELETE trên association resource gỡ liên kết giữa tài nguyên cha và tài nguyên liên quan:

~~~http
DELETE /api/employees/1/manager
~~~

Đối với manager optional, thao tác này bỏ tham chiếu manager khỏi employee 1. Nó không xóa employee 7 khỏi repository employees.

Với association resource của collection, DELETE tác động lên association được đại diện bởi endpoint đó. Không suy luận rằng DELETE trên association resource là DELETE item resource của từng phần tử liên quan. Nếu use case cần gỡ một thành viên cụ thể khỏi collection, hãy xác minh semantics của phiên bản và hợp đồng endpoint đang dùng; khi cần semantics riêng, tạo command/controller tường minh.

Nếu association không optional, Spring Data REST có thể trả `405 Method Not Allowed` khi client cố gỡ association. Ví dụ, một quan hệ bắt buộc theo mô hình miền không thể bị xóa khỏi entity cha bằng association resource.

## 12. Tùy chỉnh path và relation bằng @RestResource

Mặc định, path và relation của association lấy từ tên property. Annotation `@RestResource` cho phép đổi chúng:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "manager_id")
@RestResource(
    path = "supervisor",
    rel = "manager"
)
private Employee manager;
~~~

Trong ví dụ:

- Path association resource trở thành `/employees/{id}/supervisor`.
- Relation trong HAL vẫn là `manager`.

Điều này tách tên URI công khai khỏi tên property Java. Bạn có thể refactor tên field nội bộ mà vẫn giữ path và relation công khai ổn định.

Có thể dùng `exported = false` để không công bố association resource:

~~~java
@ManyToMany
@RestResource(exported = false)
private Set<Role> internalRoles = new LinkedHashSet<>();
~~~

Ẩn association resource sẽ loại bỏ khả năng truy cập công khai thông qua cơ chế export của Spring Data REST. Nếu ứng dụng có projection hoặc serializer khác công bố dữ liệu association, cần kiểm tra riêng các đường xuất dữ liệu đó.

## 13. Association resource và quyền sở hữu quan hệ JPA

Spring Data REST xử lý request HTTP, nhưng cách quan hệ được lưu vẫn do mapping JPA quyết định.

Với quan hệ `@ManyToOne`, phía chứa foreign key thường là owning side. Trong ví dụ, Employee.manager sở hữu cột `manager_id`.

Với `@ManyToMany`, phía khai báo `@JoinTable` là owning side; phía có `mappedBy` là inverse side. Nếu thay đổi quan hệ trong code Java, cần cập nhật đúng owning side để thay đổi được ghi xuống database.

Khi duy trì quan hệ hai chiều, nên cung cấp domain helper để đồng bộ hai phía:

~~~java
public void assignManager(Employee newManager) {
    this.manager = newManager;
}
~~~

Ví dụ này chỉ cập nhật owning side của quan hệ manager. Nếu domain model còn có collection subordinates ở phía manager, helper cần cập nhật cả collection đó theo quy tắc miền của ứng dụng.

Đối với many-to-many, không nên dùng cascade remove một cách tùy tiện. Một role có thể được nhiều nhân viên dùng chung; gỡ liên kết khỏi một employee không có nghĩa là xóa role dùng chung khỏi hệ thống.

Hãy phân biệt ba thao tác:

1. Gỡ quan hệ giữa hai entity.
2. Xóa entity đích khỏi repository của nó.
3. Xóa entity cha khỏi repository của nó.

Association resource thực hiện thao tác thứ nhất.

## 14. Repository exposure và giới hạn API

Association resource chỉ là một phần của bề mặt API được Spring Data REST export. Hãy quyết định rõ repository và association nào được công bố.

Có thể ẩn toàn bộ repository:

~~~java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.jpa.repository.JpaRepository;

@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Hoặc chỉ ẩn association property:

~~~java
import java.util.List;

import jakarta.persistence.OneToMany;
import org.springframework.data.rest.core.annotation.RestResource;

@OneToMany(mappedBy = "employee")
@RestResource(exported = false)
private List<AuditRecord> auditRecords;
~~~

Không nên xem việc một link không xuất hiện là cơ chế bảo mật duy nhất. Client có thể gửi request trực tiếp đến URI nếu biết hoặc đoán được nó. Hãy cấu hình Spring Security cho các đường dẫn association resource và kiểm tra quyền thao tác ở server.

Ví dụ chính sách có thể yêu cầu người dùng có quyền quản lý nhân sự mới được PUT manager hoặc POST roles. Quyền đọc association cũng có thể khác quyền cập nhật association. Không mặc định rằng có quyền GET item thì tự động có quyền sửa mọi association của item đó.

## 15. Validation và sự kiện khi thay đổi association

Một URI hợp lệ về cú pháp chưa chắc là một quan hệ hợp lệ về nghiệp vụ. Ví dụ:

- Không cho nhân viên tự làm quản lý của chính mình.
- Không cho gán quản lý thuộc đơn vị khác.
- Không cho thêm role đã ngừng hoạt động.
- Không cho nhân viên đã nghỉ việc nhận thêm vai trò.
- Không cho tạo vòng lặp trong cây quản lý.

Các quy tắc này cần được kiểm tra ở server. Spring Data REST cung cấp repository events và validation integration để ứng dụng phản ứng trước hoặc sau khi entity và association được lưu. Có thể dùng listener hoặc validator phù hợp với phiên bản để kiểm tra invariant trước khi thay đổi được commit.

Không nên chỉ dựa vào giao diện client hoặc việc link association có được công bố hay không. Request PUT/POST vẫn có thể được gửi thủ công.

Nếu quy tắc liên kết phức tạp, có side effect hoặc cần trả lỗi nghiệp vụ có cấu trúc riêng, một custom controller/application service có thể phù hợp hơn association resource mặc định. Khi đó, hãy giữ logic trong domain/service và để controller chỉ điều phối request.

## 16. Kiểm thử association resource bằng MockMvc

Integration test nên kiểm tra association link trên item resource trước, rồi kiểm tra request thao tác với association.

Ví dụ xác nhận item resource công bố link:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/employees/{id}", 1L)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.manager.href").exists())
    .andExpect(jsonPath("$._links.roles.href").exists());
~~~

Kiểm tra GET association:

~~~java
mockMvc.perform(get("/api/employees/{id}/manager", 1L)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

Kiểm tra PUT association bằng URI list:

~~~java
mockMvc.perform(put("/api/employees/{id}/manager", 1L)
        .contentType("text/uri-list")
        .content("http://localhost/api/employees/7"))
    .andExpect(status().is2xxSuccessful());
~~~

Kiểm tra POST collection association:

~~~java
mockMvc.perform(post("/api/employees/{id}/roles", 1L)
        .contentType("text/uri-list")
        .content("http://localhost/api/roles/3"))
    .andExpect(status().is2xxSuccessful());
~~~

Các test này giả định ứng dụng có fixture employee và role tương ứng, base path là `/api`, repository và association được export, và cấu hình bảo mật cho phép request. Nếu ứng dụng yêu cầu CSRF, test cần thêm token phù hợp.

Sau thao tác PUT hoặc POST, nên GET lại association resource để xác nhận quan hệ đã thay đổi đúng. Chỉ kiểm tra status 2xx chưa đủ để chứng minh mapping JPA đã cập nhật đúng owning side.

## 17. Các trường hợp lỗi cần kiểm thử

Ngoài luồng thành công, hãy kiểm tra các tình huống:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Gửi nhiều URI cho association to-one | `400 Bad Request` |
| POST vào association to-one | Method không được hỗ trợ |
| DELETE association không optional | `405 Method Not Allowed` |
| Dùng JSON body thay cho `text/uri-list` | Request không đáp ứng media type association |
| URI đích không tồn tại | Request bị từ chối theo cơ chế phân giải tài nguyên |
| Repository đích không được export hoặc không thể phân giải | Kiểm tra hành vi export và URI mapping |
| Người dùng không có quyền thay đổi association | Bị từ chối bởi security policy |
| Association bị ẩn bằng `exported = false` | Link/resource không được công bố qua exporter |

Status cụ thể cho các trường hợp lỗi có thể phụ thuộc cấu hình, phiên bản và cách ứng dụng xử lý exception. Hãy kiểm tra response thực tế trong integration test thay vì dựa vào giả định của client.

## 18. Khi nào association resource mặc định là chưa đủ?

Association resource phù hợp khi thao tác chủ yếu là gắn hoặc gỡ tham chiếu giữa các tài nguyên đã tồn tại. Nó đặc biệt hữu ích cho CRUD API đơn giản, nơi client cần liên kết entity qua URI.

Tuy nhiên, có những use case cần workflow nghiệp vụ riêng:

- Gán quản lý phải kiểm tra phân cấp tổ chức và quyền.
- Thêm thành viên vào nhóm phải kiểm tra quota.
- Liên kết sản phẩm vào đơn hàng cần tính lại giá hoặc kiểm tra tồn kho.
- Chuyển quan hệ cần ghi audit hoặc phát sự kiện domain.
- Một thao tác cần cập nhật nhiều aggregate trong cùng transaction.

Khi đó, không nên cố ép toàn bộ nghiệp vụ vào association resource tự động. Hãy tạo application service và endpoint command rõ ràng, ví dụ `POST /employees/1/manager-assignment`, rồi để service kiểm tra invariant và thực hiện transaction.

Association resource vẫn có thể được giữ cho thao tác liên kết đơn giản nếu hợp đồng cho phép. Hãy lựa chọn dựa trên semantics nghiệp vụ, không chỉ dựa trên việc framework có thể tự export endpoint.

## 19. Quy trình làm việc với association resource

Khi thiết kế một association resource trong Spring Data REST, hãy thực hiện theo thứ tự:

1. Xác định association là to-one hay collection-valued.
2. Khai báo mapping JPA đúng owning side và inverse side.
3. Export repository của tài nguyên cha và các tài nguyên đích cần truy cập.
4. Đọc item resource để khám phá association link.
5. Dùng `@RestResource` để ổn định path và relation nếu cần.
6. Dùng GET để đọc trạng thái association.
7. Dùng PUT với `text/uri-list` để gắn URI vào association.
8. Dùng POST với `text/uri-list` để thêm phần tử vào collection association.
9. Dùng DELETE để gỡ association khi mapping cho phép.
10. Kiểm tra validation, quyền truy cập và invariant nghiệp vụ ở server.
11. Kiểm thử cả link, media type, method và trạng thái quan hệ sau thao tác.
12. Dùng custom controller/application service khi thao tác liên kết có workflow nghiệp vụ phức tạp.

Association resource là một phần quan trọng trong cách Spring Data REST biến mô hình miền thành API có thể khám phá. Nó cho client một URI riêng để đọc và quản lý quan hệ, trong khi URI của entity cha và entity đích vẫn giữ vai trò độc lập. Khi hiểu rõ semantics của GET, PUT, POST, DELETE, dùng đúng `text/uri-list`, kiểm soát mapping JPA và bảo vệ các invariant, ứng dụng có thể công bố association API nhất quán mà không biến việc liên kết thành thao tác cập nhật toàn bộ entity.

## Tài liệu tham khảo

- [Spring Data REST Reference – Repository resources, Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference – Customizing exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST API – Repository event types](https://docs.spring.io/spring-data/rest/docs/current/api/allclasses-index.html)
- [Spring Data JPA Reference – Defining repository interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html)
- [Spring Data REST Reference – Events](https://docs.spring.io/spring-data/rest/docs/current/reference/html/#events)

