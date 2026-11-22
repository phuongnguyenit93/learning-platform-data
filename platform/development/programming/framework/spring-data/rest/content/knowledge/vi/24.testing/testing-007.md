# Kiểm tra thêm, thay thế, gỡ liên kết và quan hệ bắt buộc

## 1. Mục tiêu

Spring Data REST công bố association của entity thành association resource. Client có thể đọc trạng thái liên kết, gắn một entity đã tồn tại, thay thế quan hệ hoặc gỡ liên kết bằng HTTP method phù hợp.

Cần phân biệt hai nhóm association:

- **Quan hệ đơn (to-one):** một thuộc tính trỏ tới tối đa một entity, thường dùng ManyToOne hoặc OneToOne.
- **Quan hệ tập hợp (to-many):** một thuộc tính chứa nhiều entity, thường dùng OneToMany hoặc ManyToMany.

Các thao tác có ý nghĩa khác nhau theo cardinality:

- GET đọc trạng thái association.
- PUT gắn URI của resource vào association; với quan hệ đơn, thao tác này thay resource đang liên kết bằng resource mới.
- POST chỉ dành cho association tập hợp và thêm một phần tử.
- DELETE gỡ association nếu quan hệ có thể để trống. Với quan hệ bắt buộc, Spring Data REST có thể từ chối bằng 405 Method Not Allowed.

Xóa liên kết không đồng nghĩa xóa entity ở đầu bên kia. Bài này hướng dẫn kiểm tra cả HAL response, HTTP status và dữ liệu đã lưu sau mỗi thao tác.

## 2. Mô hình dữ liệu minh họa

Giả sử Person luôn thuộc một Department và có nhiều Role:

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String name;

        @ManyToOne(optional = false)
        @JoinColumn(name = "department_id", nullable = false)
        private Department department;

        @ManyToMany
        @JoinTable(
            name = "person_role",
            joinColumns = @JoinColumn(name = "person_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id")
        )
        private Set<Role> roles = new LinkedHashSet<>();

        // getters and setters
    }

    @Entity
    public class Department {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
    }

    @Entity
    public class Role {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
    }

Person.department là quan hệ đơn bắt buộc. Person.roles là quan hệ tập hợp. Collection được khởi tạo bằng LinkedHashSet để tránh trạng thái null và hạn chế phần tử trùng theo equals/hashCode.

Repository:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

    public interface DepartmentRepository
            extends JpaRepository<Department, Long> {
    }

    public interface RoleRepository
            extends JpaRepository<Role, Long> {
    }

Spring Data REST tạo item resource cho Person và association resource cho từng association được export. Tên relation/path mặc định thường dựa trên tên property; có thể tùy chỉnh bằng RestResource trên property hoặc RepositoryRestResource trên repository.

## 3. Khám phá association link trước khi thay đổi

Đầu tiên, GET item resource:

    GET /people/42
    Accept: application/hal+json

Response minh họa:

    {
      "name": "An",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "department": {
          "href": "http://localhost:8080/people/42/department"
        },
        "roles": {
          "href": "http://localhost:8080/people/42/roles"
        }
      }
    }

Hai href là association resource:

- department đại diện quan hệ đơn Person.department.
- roles đại diện collection association Person.roles.

Client nên theo href server cung cấp. Nếu path hoặc rel đã được tùy chỉnh, không tự ghép URL từ tên entity, ID hoặc tên property.

Đọc trạng thái association bằng GET:

    GET /people/42/department
    Accept: application/hal+json

    GET /people/42/roles
    Accept: application/hal+json

Quan hệ đơn thường trả representation hoặc link của entity đang liên kết. Quan hệ tập hợp thường trả collection representation, có thể có _embedded cùng self link của từng Role. Dùng response thực tế để xác định URI resource sẽ gửi trong request thay đổi.

## 4. Media type text/uri-list

Các thao tác bind association của Spring Data REST dùng media type text/uri-list. Body chứa URI của resource đã tồn tại, mỗi URI trên một dòng:

    http://localhost:8080/departments/7
    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

Không gửi JSON object Department hoặc Role vào association endpoint nếu contract yêu cầu text/uri-list. URI phải trỏ tới resource đích hợp lệ và có thể truy cập trong ứng dụng.

Nên lấy URI từ self link của resource đích. Cách này tránh phụ thuộc path mặc định và hỗ trợ cấu hình base path hoặc item URI tùy chỉnh.

## 5. Gắn hoặc thay thế quan hệ đơn bằng PUT

Để gắn Department vào Person, gửi PUT tới association resource với đúng một URI:

    PUT /people/42/department
    Content-Type: text/uri-list

    http://localhost:8080/departments/7

PUT bind resource được chỉ ra vào association. Với quan hệ đơn, nếu Person đang thuộc Department 4, gửi PUT với Department 7 sẽ thay liên kết hiện tại bằng Department 7.

Đọc lại association để xác nhận:

    GET /people/42/department
    Accept: application/hal+json

Response cần phản ánh Department 7. Có thể GET Person lần nữa để xác nhận link department vẫn tồn tại; nếu cần xác nhận dữ liệu đích, theo self link hoặc href của association.

Một association to-one chỉ nhận một URI. Nếu body chứa nhiều URI cho một quan hệ đơn, Spring Data REST trả 400 Bad Request theo contract association resource. Không dùng PUT với nhiều URI để biến quan hệ đơn thành collection.

Nếu URI Department không tồn tại hoặc caller không có quyền truy cập, thao tác có thể thất bại. Hãy kiểm tra status code và error response thực tế; không coi request đã thành công chỉ vì client đã gửi body.

## 6. Gỡ quan hệ đơn tùy chọn bằng DELETE

Nếu association to-one là tùy chọn, có thể gỡ liên kết bằng DELETE association resource:

    DELETE /people/42/mentor

Ví dụ này giả định Person có association mentor có thể để trống. DELETE tới association resource gỡ liên kết; nó không xóa entity Mentor khỏi repository.

Sau thao tác, GET lại Person hoặc association resource để xác nhận không còn liên kết. Tùy kiểu association và phiên bản framework, response thành công có thể là 204 No Content hoặc response thành công khác theo cấu hình.

Không gửi body chứa URI của entity cần xóa cùng DELETE association resource. Mục tiêu của request là gỡ association tại URI đích.

Nếu quan hệ không được phép để trống, Spring Data REST có thể trả 405 Method Not Allowed khi DELETE association. Đây là dấu hiệu thao tác unbind không được hỗ trợ cho association bắt buộc. Nếu cần chuyển Person sang Department khác, dùng PUT với URI Department mới.

## 7. Thêm phần tử vào quan hệ tập hợp bằng POST

Với association collection như Person.roles, POST thêm một Role vào tập hợp:

    POST /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3

POST chỉ dành cho collection association. Nó thêm resource được chỉ ra vào tập hợp hiện tại, thay vì thay thế toàn bộ danh sách.

Có thể gửi nhiều URI trong cùng body nếu cần thêm nhiều phần tử:

    POST /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

Sau khi POST, GET lại association resource và xác nhận các Role mới xuất hiện. Nếu collection dùng Set, phần tử trùng có thể không làm tăng số liên kết; behavior cụ thể còn phụ thuộc equals/hashCode và persistence mapping.

Không dùng POST trên association to-one. Với quan hệ đơn, dùng PUT để gắn hoặc thay thế resource liên kết.

## 8. Thay thế toàn bộ liên kết của collection bằng PUT

PUT có thể gửi danh sách URI mong muốn của collection association:

    PUT /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/5

Dùng thao tác này khi client muốn đồng bộ tập liên kết thành đúng danh sách đã gửi. Các URI trong body là tập resource cần được gắn sau thao tác; không gửi JSON array nếu endpoint yêu cầu text/uri-list.

Khác với POST, PUT bind danh sách URI được chỉ định vào association và thường được dùng để thay tập liên kết hiện tại. Client cần biết rõ danh sách cuối cùng mong muốn, vì bỏ sót một URI trong body có thể làm liên kết đó không còn trong tập sau khi cập nhật.

Nếu collection lớn, tránh tải toàn bộ danh sách về client chỉ để thay đổi một phần tử. Dùng endpoint nghiệp vụ chuyên biệt để thêm/gỡ một thành viên có thể phù hợp hơn, đặc biệt khi cần pagination, concurrency control hoặc kiểm tra quyền theo từng phần tử.

## 9. Gỡ một phần tử khỏi collection association

Association resource chuẩn công bố POST để thêm phần tử và PUT để bind danh sách URI. DELETE trên association resource có ý nghĩa unbind association; không nên mặc định rằng DELETE kèm body sẽ xóa đúng một phần tử trong collection.

Một cách reconciliation là:

1. GET collection association và lấy self URI của các phần tử hiện có.
2. Tạo danh sách URI mới, loại URI của phần tử cần gỡ.
3. PUT danh sách URI còn lại tới association resource với Content-Type text/uri-list.
4. GET lại association để xác nhận phần tử đã được gỡ.

Ví dụ Person 42 có Role 3, Role 5 và Role 8. Muốn gỡ Role 5, PUT danh sách còn lại:

    PUT /people/42/roles
    Content-Type: text/uri-list

    http://localhost:8080/roles/3
    http://localhost:8080/roles/8

Cách này thay tập liên kết theo danh sách mới; nó không xóa Role 5 khỏi RoleRepository. Nếu ứng dụng hoặc phiên bản framework cung cấp endpoint member-specific cho association, chỉ dùng khi endpoint đó được công bố/document rõ ràng và đã được kiểm thử.

Với collection rất lớn, cách tải toàn bộ rồi PUT lại có thể tốn kém và dễ ghi đè cập nhật đồng thời. Khi đó, tạo custom controller/service operation có ý nghĩa rõ ràng, ví dụ removeRole(personId, roleId), để xử lý đúng một liên kết trong transaction.

## 10. Phân biệt unlink và delete entity

Hai request sau có ý nghĩa khác nhau:

    DELETE /people/42/department

    DELETE /departments/7

Request đầu gỡ quan hệ department khỏi Person 42 nếu association có thể để trống. Request thứ hai xóa Department 7 khỏi repository. Không dùng DELETE item resource chỉ vì muốn gỡ liên kết của một Person.

Tương tự, gỡ Role 5 khỏi Person 42 không có nghĩa xóa Role 5 nếu Role còn được dùng bởi Person khác. Với ManyToMany, một Role thường được chia sẻ giữa nhiều Person; xóa Role entity có thể làm mất dữ liệu liên quan của nhiều aggregate.

Chú ý JPA mapping:

- CascadeType.REMOVE có thể khiến xóa parent lan sang entity liên quan.
- orphanRemoval=true có thể khiến entity con bị xóa khi bị loại khỏi collection của parent.
- Gỡ liên kết và xóa orphan là hai quyết định nghiệp vụ khác nhau.

Không thêm cascade remove hoặc orphanRemoval chỉ để association endpoint hoạt động. Chọn mapping dựa trên ownership và vòng đời thực của entity.

## 11. Quan hệ bắt buộc ở tầng JPA

Với quan hệ to-one bắt buộc, khai báo optional=false và ràng buộc cột phù hợp:

    @ManyToOne(optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

optional=false mô tả association không được phép thiếu theo JPA mapping. nullable=false yêu cầu cột foreign key không được null trong schema do mapping tạo hoặc cập nhật. Có thể bổ sung @NotNull nếu muốn Bean Validation kiểm tra trước persistence.

Không chỉ dựa vào UI để yêu cầu người dùng chọn Department. Server phải kiểm tra association trước khi lưu và database nên có foreign key/not-null constraint phù hợp.

Nếu association bắt buộc, DELETE association resource không thể dùng để đặt property thành null; Spring Data REST có thể trả 405 Method Not Allowed. Nếu cần chuyển Person sang Department khác, dùng PUT với URI Department mới thay vì DELETE rồi tạo lại liên kết.

## 12. Quan hệ tập hợp bắt buộc và quy tắc tối thiểu một phần tử

Collection-valued association thường luôn tồn tại như một collection trong object model, nhưng có thể rỗng. Điều đó khác với một association to-one có giá trị null.

Nếu nghiệp vụ yêu cầu Person phải có ít nhất một Role, cần định nghĩa quy tắc số lượng tối thiểu. Ví dụ:

    @ManyToMany
    @Size(min = 1, message = "Person must have at least one role")
    private Set<Role> roles = new LinkedHashSet<>();

@Size(min=1) biểu diễn yêu cầu collection có ít nhất một phần tử khi Bean Validation chạy. @NotEmpty cũng có thể dùng cho collection không được rỗng.

Không nên giả định mọi thao tác association resource đều tự kích hoạt đúng validation path của entity. Nếu invariant phải được giữ ở mọi đường cập nhật, hãy kiểm tra lifecycle event của Spring Data REST, validation listener hoặc service/domain operation thực tế và viết integration test cho association PUT/POST/DELETE.

Với quy tắc phức tạp như phải có ít nhất một Role đang active hoặc Person phải có Role thuộc cùng tenant, dùng validator/service kiểm tra nội dung association chứ không chỉ đếm số phần tử.

## 13. Đồng bộ hai phía của quan hệ JPA

Với bidirectional association, JPA có owning side và inverse side. Thay đổi collection ở một phía mà không cập nhật owning side có thể khiến database không lưu quan hệ như mong muốn.

Ví dụ helper methods:

    public void addRole(Role role) {
        roles.add(role);
        role.getPeople().add(this);
    }

    public void removeRole(Role role) {
        roles.remove(role);
        role.getPeople().remove(this);
    }

Ví dụ trên giả định Role có collection people và Person.roles được mapping phù hợp. Điều chỉnh helper theo vị trí mappedBy và owning side của entity thực tế.

Khi Spring Data REST xử lý association resource, framework dùng persistent metadata để cập nhật association. Hãy xác minh mapping, reload entity trong persistence context mới và kiểm tra cả hai phía nếu domain model có quan hệ hai chiều.

Không chỉ kiểm tra object đang nằm trong memory của request. Hãy đọc lại dữ liệu sau khi transaction hoàn tất để xác nhận foreign key hoặc join table đã thay đổi đúng.

## 14. Thứ tự thao tác và trạng thái response

Một luồng kiểm tra association nên có thứ tự:

1. GET parent resource để lấy association href.
2. GET association resource để đọc trạng thái hiện tại.
3. GET item resource của entity đích để xác nhận URI hợp lệ và có quyền truy cập.
4. Gửi PUT hoặc POST với text/uri-list theo cardinality.
5. Kiểm tra status code thành công.
6. GET lại association resource và xác nhận liên kết mới.
7. Reload parent/child qua repository để xác nhận persistence.

Status response có thể phụ thuộc Accept header và cấu hình return body của Spring Data REST. Association endpoint có thể trả 2xx với body hoặc 204 No Content. Hãy kiểm tra theo contract của phiên bản ứng dụng thay vì hard-code một status thành công duy nhất nếu cấu hình cho phép nhiều dạng response.

Các lỗi đáng chú ý:

- 400 Bad Request: ví dụ gửi nhiều URI cho association to-one.
- 404 Not Found: parent hoặc target URI không tồn tại, hoặc path sai.
- 405 Method Not Allowed: method không được export hoặc association bắt buộc không cho unbind.
- 401/403: caller chưa xác thực hoặc không có quyền.
- 409 hoặc lỗi persistence khác: có thể xuất hiện từ constraint/concurrency/custom exception handling; kiểm tra error contract thực tế.

## 15. Kiểm soát concurrency khi thay collection

Khi hai client cùng GET Person.roles, mỗi client có thể giữ một danh sách cũ. Nếu client A PUT danh sách mới trước, client B có thể PUT một danh sách khác được xây dựng từ snapshot cũ và vô tình làm mất thay đổi của A.

Với association collection lớn hoặc được cập nhật thường xuyên:

- Dùng ETag/If-Match nếu resource và API đã bật version-based conditional requests.
- Giữ thao tác add/remove theo phần tử trong service/controller để tránh thay toàn bộ tập.
- Thực hiện kiểm tra quyền và invariant trong cùng transaction.
- Cân nhắc optimistic locking trên aggregate root hoặc cơ chế version của join entity.
- Trả conflict rõ ràng khi snapshot client đã cũ.

Không tự động GET lại rồi PUT payload cũ với version mới mà không hợp nhất thay đổi. Điều đó có thể ghi đè cập nhật của client khác.

## 16. Kiểm thử association bằng MockMvc

Có thể viết integration test cho thao tác gắn Department:

    mockMvc.perform(put("/people/{id}/department", personId)
            .contentType("text/uri-list")
            .content(departmentUri))
        .andExpect(status().is2xxSuccessful());

Sau đó đọc lại association và xác nhận href của Department mới có mặt.

Kiểm thử thêm Role:

    mockMvc.perform(post("/people/{id}/roles", personId)
            .contentType("text/uri-list")
            .content(roleUri))
        .andExpect(status().is2xxSuccessful());

Kiểm thử thay tập Role:

    mockMvc.perform(put("/people/{id}/roles", personId)
            .contentType("text/uri-list")
            .content(roleUri3 + "\n" + roleUri8))
        .andExpect(status().is2xxSuccessful());

Các đoạn trên là skeleton. Trong test thật, tạo Person, Department và Role trước; dùng URI từ self link response thay vì giả định path nếu API đã tùy chỉnh.

Các test cần bao gồm:

- PUT to-one thay association cũ bằng association mới.
- PUT to-one với nhiều URI bị từ chối.
- DELETE to-one tùy chọn gỡ link.
- DELETE to-one bắt buộc bị từ chối.
- POST collection thêm một phần tử mà vẫn giữ các phần tử trước.
- PUT collection đồng bộ lại tập URI mong muốn.
- Gỡ một thành viên khỏi collection bằng danh sách còn lại hoặc custom remove operation.
- Không xóa entity đích khi chỉ gỡ association.
- Không cho phép collection rỗng nếu business rule yêu cầu ít nhất một phần tử.
- Caller thiếu quyền không thể thay đổi association.

Sau mỗi thao tác, kiểm tra GET association và trạng thái repository/database. Chỉ assert 2xx là chưa đủ để chứng minh liên kết đã thay đổi đúng.

## 17. Kiểm tra thủ công bằng curl

Thay Department hiện tại:

    curl -i -X PUT \
      -H "Content-Type: text/uri-list" \
      -H "Accept: application/hal+json" \
      --data "http://localhost:8080/departments/7" \
      http://localhost:8080/people/42/department

Thêm Role vào collection:

    curl -i -X POST \
      -H "Content-Type: text/uri-list" \
      -H "Accept: application/hal+json" \
      --data "http://localhost:8080/roles/3" \
      http://localhost:8080/people/42/roles

Gỡ association to-one tùy chọn:

    curl -i -X DELETE \
      -H "Accept: application/hal+json" \
      http://localhost:8080/people/42/mentor

Các URL là ví dụ. Hãy thay bằng href thực tế trong HAL response. Không gửi DELETE tới Department hoặc Role item resource nếu mục tiêu chỉ là gỡ liên kết.

## 18. Lỗi thường gặp

**Dùng JSON thay cho text/uri-list**

Association resource bind URI của resource đích. Dùng đúng Content-Type và URI của item đã export.

**Dùng POST cho quan hệ đơn**

POST chỉ hỗ trợ collection association. Dùng PUT để gắn hoặc thay thế quan hệ đơn.

**Dùng DELETE để xóa entity đích**

DELETE association resource gỡ liên kết; DELETE item resource xóa entity. Chọn đúng URI theo mục đích.

**Xóa association bắt buộc**

Quan hệ to-one optional=false hoặc cột foreign key not-null không thể bị đặt thành null. Spring Data REST có thể trả 405 cho DELETE association không optional.

**Cho rằng collection không được rỗng vì đã khai báo OneToMany**

Collection có thể rỗng. Nếu nghiệp vụ yêu cầu tối thiểu một phần tử, khai báo và thực thi invariant riêng.

**Xóa một phần tử bằng DELETE toàn collection**

DELETE trên association resource không phải lệnh xóa tùy chọn một member. Dùng PUT với danh sách còn lại hoặc custom operation rõ ràng.

**Nhầm unlink với orphan removal**

Nếu orphanRemoval=true, bỏ phần tử khỏi collection có thể xóa entity con khi lưu. Kiểm tra mapping trước khi dùng association endpoint.

**Chỉ kiểm tra response status**

Một request 2xx chưa chứng minh owning side hoặc join table đã được cập nhật. Reload entity và kiểm tra liên kết đã lưu.

**Bỏ qua cập nhật đồng thời**

PUT toàn bộ collection từ snapshot cũ có thể làm mất thay đổi của client khác. Dùng ETag/If-Match hoặc operation theo phần tử với kiểm tra version.

## 19. Bài tập thực hành

Với Person có Department bắt buộc và nhiều Role:

1. Khai báo Department bằng ManyToOne(optional=false) và JoinColumn(nullable=false).
2. Khai báo roles là collection và khởi tạo bằng Set rỗng.
3. Tạo dữ liệu Department, Role và Person qua repository hoặc fixture.
4. GET Person resource và đọc association href của department cùng roles.
5. GET association resource để xem trạng thái ban đầu.
6. PUT một URI Department khác vào association department; xác nhận Department mới thay thế Department cũ.
7. Thử PUT hai URI cho department và xác nhận request bị từ chối.
8. Thử DELETE department association bắt buộc và quan sát status/error.
9. POST thêm một Role vào roles; xác nhận các Role cũ vẫn còn.
10. PUT danh sách URI Role mong muốn để thay tập liên kết.
11. Gỡ một Role khỏi collection bằng cách PUT danh sách còn lại hoặc custom operation.
12. Xác nhận Role bị gỡ vẫn tồn tại ở Role repository nếu không có quy tắc xóa orphan.
13. Thêm constraint Size(min=1) hoặc validator nghiệp vụ nếu Person phải có ít nhất một Role.
14. Thử cập nhật làm collection rỗng và xác nhận invariant được thực thi.
15. Viết MockMvc integration test cho add, replace, remove, required-association rejection và quyền truy cập.
16. Reload dữ liệu trong transaction/persistence context mới để xác nhận quan hệ đã lưu.

Câu hỏi tự kiểm tra:

- PUT và POST khác nhau thế nào trên association resource?
- Vì sao PUT phù hợp để thay một quan hệ to-one?
- Vì sao POST chỉ dành cho collection association?
- DELETE association khác DELETE item resource ở đâu?
- Khi nào DELETE association trả 405?
- Làm thế nào gỡ một phần tử khỏi collection mà không xóa entity đích?
- Vì sao OneToMany không tự đảm bảo collection có ít nhất một phần tử?
- orphanRemoval và CascadeType.REMOVE có thể ảnh hưởng thế nào khi unlink?
- Vì sao cần reload entity sau request để xác nhận persistence?
- Làm sao tránh lost update khi hai client cùng PUT một collection?

## 20. Ghi nhớ

- Đọc HAL link trước khi thao tác; dùng href do server công bố.
- Association resource hỗ trợ GET, PUT, POST và DELETE theo cardinality cùng cấu hình.
- PUT bind URI vào association; với to-one, dùng một URI để gắn hoặc thay thế.
- POST chỉ dùng cho collection association và thêm phần tử.
- DELETE gỡ association nếu association có thể để trống; quan hệ bắt buộc có thể trả 405.
- Dùng text/uri-list và URI của resource đích.
- Gỡ liên kết không đồng nghĩa xóa entity đích.
- Gỡ một phần tử collection bằng PUT danh sách còn lại hoặc custom operation theo phần tử.
- optional=false, nullable=false và Bean Validation giúp thực thi quan hệ bắt buộc ở các lớp phù hợp.
- Collection có thể rỗng; quy tắc tối thiểu một phần tử cần validation/domain logic riêng.
- Kiểm tra owning side, cascade và orphanRemoval trước khi thay đổi association.
- Kiểm thử cả HAL response, HTTP status và dữ liệu đã lưu.

## Tài liệu tham khảo

- Spring Data REST Reference — Repository resources and Association Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Jakarta Persistence Specification — Relationships and optional associations: https://jakarta.ee/specifications/persistence/
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
