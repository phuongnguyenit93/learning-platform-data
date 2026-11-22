# Tùy chỉnh đường dẫn tài nguyên liên kết trên thuộc tính quan hệ

Trong Spring Data REST, một thuộc tính quan hệ của entity có thể được công bố thành **association resource** để client đọc hoặc thay đổi liên kết giữa các tài nguyên. Annotation **@RestResource** đặt trực tiếp trên thuộc tính quan hệ cho phép tùy chỉnh hai phần của liên kết đó: **path** quyết định đoạn đường dẫn URL, còn **rel** quyết định tên quan hệ trong HAL link.

Bài này thuộc nhóm **Đường dẫn tài nguyên** của Spring Data REST. Trọng tâm là cách tùy chỉnh endpoint của một association mà không làm thay đổi đường dẫn collection/item của repository.

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết association resource được tạo từ thuộc tính quan hệ của entity.
- Dùng **@RestResource(path = ..., rel = ...)** trên thuộc tính để tùy chỉnh endpoint và HAL link relation.
- Phân biệt path của association với path của repository, và phân biệt rel với tên thuộc tính Java.
- Kiểm tra đường dẫn thực tế qua HAL representation và HTTP request.
- Hiểu phạm vi của exported = false, quan hệ hai chiều và các điểm cần kiểm tra khi cập nhật association.

## 1. Association resource trong Spring Data REST

Giả sử repository employees quản lý entity Employee. Một nhân viên có thể tham chiếu đến người quản lý của mình:

~~~java
@Entity
public class Employee {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Employee manager;
}
~~~

Khi repository được Spring Data REST công bố, tài nguyên nhân viên có URI dạng:

~~~text
/employees/{id}
~~~

Thuộc tính manager là một quan hệ đến một entity khác. Spring Data REST có thể biểu diễn quan hệ này bằng một link trong representation của nhân viên và cung cấp association resource để truy cập quan hệ đó.

Với tên mặc định, association thường được truy cập theo dạng:

~~~text
/employees/{id}/manager
~~~

Đường dẫn này có cấu trúc gồm:

- /employees: đường dẫn collection do repository công bố.
- /{id}: item resource của một nhân viên.
- /manager: association resource ứng với thuộc tính quan hệ manager.

Association resource là endpoint cho quan hệ giữa các tài nguyên. Nó khác item resource của entity liên quan: item resource của người quản lý có URI riêng, còn association resource biểu diễn liên kết từ nhân viên hiện tại đến người quản lý.

## 2. Dùng @RestResource để tùy chỉnh path và rel

Import annotation:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
~~~

Đặt annotation ngay trên thuộc tính quan hệ:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;
~~~

Khi đó:

- path = "supervisor" tùy chỉnh đoạn URL của association resource.
- rel = "reportsTo" tùy chỉnh tên link relation trong HAL representation.
- Tên thuộc tính Java vẫn là manager.
- Quan hệ JPA vẫn là manager; annotation không đổi kiểu quan hệ, khóa ngoại hay cấu trúc bảng.

Ví dụ repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "employees")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Đường dẫn association sau khi tùy chỉnh có dạng:

~~~text
/employees/{id}/supervisor
~~~

Trong khi đó, link relation được biểu diễn bằng tên reportsTo.

Ví dụ representation HAL rút gọn của nhân viên có ID 42:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "https://api.example.com/employees/42"
    },
    "reportsTo": {
      "href": "https://api.example.com/employees/42/supervisor"
    }
  }
}
~~~

Client theo HAL nên tìm link theo relation reportsTo, sau đó dùng href mà server trả về. Client không cần tự ghép URL từ tên thuộc tính hoặc giả định cấu trúc đường dẫn.

## 3. Phân biệt path và rel

Hai thuộc tính phục vụ hai mục đích khác nhau:

| Thuộc tính | Vai trò | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| path | Đoạn đường dẫn URL của association resource | path = "supervisor" | /employees/42/supervisor |
| rel | Tên quan hệ trong HAL _links | rel = "reportsTo" | _links.reportsTo |

Một ví dụ khác:

~~~java
@ManyToOne
@RestResource(path = "lead", rel = "teamLead")
private Employee manager;
~~~

Link trả về có thể có dạng:

~~~json
{
  "_links": {
    "teamLead": {
      "href": "https://api.example.com/employees/42/lead"
    }
  }
}
~~~

Ở ví dụ này, URL kết thúc bằng /lead, còn key trong _links là teamLead.

Không nên coi rel là tên URL hay path là tên field. Khi thiết kế API, path nên ngắn, ổn định và dễ đọc; rel nên diễn đạt ý nghĩa quan hệ mà client cần hiểu.

## 4. Tùy chỉnh quan hệ một-nhiều hoặc nhiều-nhiều

Cùng cơ chế này áp dụng cho association dạng collection. Ví dụ một nhân viên có thể tham gia nhiều nhóm:

~~~java
@Entity
public class Employee {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    @RestResource(path = "teams", rel = "memberOf")
    private Set<Team> teams = new HashSet<>();
}
~~~

Với repository:

~~~java
@RepositoryRestResource(path = "employees")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Association resource có đường dẫn dạng:

~~~text
/employees/{id}/teams
~~~

Và link trong HAL có relation memberOf:

~~~json
{
  "_links": {
    "memberOf": {
      "href": "https://api.example.com/employees/42/teams"
    }
  }
}
~~~

Client có thể theo link này để đọc collection liên quan. Các thao tác thay đổi association phụ thuộc cardinality, cấu hình mapping và các phương thức HTTP mà Spring Data REST hỗ trợ cho resource đó. Khi tích hợp, hãy kiểm tra request/response thực tế của association thay vì suy ra rằng endpoint collection association có cùng hành vi với endpoint collection repository.

@RestResource chỉ tùy chỉnh cách association được công bố. Nó không tự tạo quan hệ JPA, không thay thế @ManyToMany, @OneToMany, @ManyToOne hoặc @OneToOne, và không tự cấu hình cascade hay fetch strategy.

## 5. Phạm vi của annotation trên thuộc tính

Khi đặt @RestResource trên thuộc tính quan hệ, annotation tác động đến resource/link đại diện cho quan hệ đó.

Nó không tự thay đổi:

- Đường dẫn collection của repository, ví dụ /employees.
- Đường dẫn item resource, ví dụ /employees/42.
- Tên thuộc tính Java, ví dụ manager.
- Tên cột hoặc khóa ngoại trong database.
- Tên JSON property do Jackson serialize theo cấu hình riêng.
- Quan hệ sở hữu trong JPA hoặc cách Hibernate ghi dữ liệu.

Để phân biệt các cấu hình:

| Nhu cầu | Cơ chế thường dùng |
| --- | --- |
| Đổi đường dẫn collection repository | @RepositoryRestResource(path = "...") trên repository |
| Đổi path/rel của association | @RestResource(path = "...", rel = "...") trên thuộc tính quan hệ |
| Ẩn association resource | @RestResource(exported = false) trên thuộc tính quan hệ |
| Đổi tên JSON property | Cấu hình Jackson, ví dụ @JsonProperty, nếu phù hợp với representation đang dùng |
| Đổi tên cột hoặc khóa ngoại | Mapping JPA như @Column, @JoinColumn |
| Kiểm soát ai được phép truy cập | Spring Security và cấu hình bảo mật tương ứng |

Không dùng @RepositoryRestResource(path = ...) để đổi riêng đường dẫn của một association. Annotation repository điều khiển resource của repository; annotation trên thuộc tính điều khiển association resource tương ứng.

## 6. Ẩn một association resource

Nếu không muốn công bố một quan hệ cụ thể, có thể đặt exported = false:

~~~java
@ManyToOne
@RestResource(exported = false)
private Employee manager;
~~~

Khi thuộc tính này không được export, Spring Data REST không công bố association resource đó như một association endpoint thông thường và link tương ứng không được đưa ra theo cách công bố association mặc định.

Điều này không đồng nghĩa với việc entity hoặc repository bị ẩn hoàn toàn. Repository employees vẫn có thể được công bố, và các thuộc tính/quan hệ khác vẫn có thể xuất hiện theo cấu hình của chúng.

exported = false cũng không phải cơ chế phân quyền. Nếu client không được phép xem hoặc thay đổi dữ liệu, hãy cấu hình xác thực, authorization và các chính sách bảo vệ dữ liệu tương ứng.

## 7. Quan hệ hai chiều

Một quan hệ JPA hai chiều thường có hai thuộc tính Java. Ví dụ:

~~~java
@Entity
public class Employee {

    @ManyToOne
    @RestResource(path = "supervisor", rel = "reportsTo")
    private Employee manager;

    @OneToMany(mappedBy = "manager")
    private Set<Employee> directReports = new HashSet<>();
}
~~~

manager và directReports là hai thuộc tính khác nhau. Mỗi thuộc tính có thể được Spring Data REST biểu diễn thành association riêng nếu được export và mapping phù hợp.

Tùy chỉnh trên manager không tự động đổi path hoặc rel của directReports. Nếu cần đặt tên cho cả hai association, hãy khai báo annotation trên từng thuộc tính:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;

@OneToMany(mappedBy = "manager")
@RestResource(path = "reports", rel = "directReports")
private Set<Employee> directReports = new HashSet<>();
~~~

Trong JPA, mappedBy xác định phía inverse của quan hệ; phía sở hữu vẫn quyết định cách cập nhật liên kết được ghi xuống database. Việc đổi path/rel không thay đổi quy tắc owning side. Khi cập nhật association qua REST, cần kiểm tra cả trạng thái object graph và dữ liệu đã lưu.

## 8. Các điểm cần lưu ý khi đặt tên

Khi chọn path và rel, hãy cân nhắc:

1. **Không trùng đường dẫn:** path association cần tránh xung đột với các resource hoặc mapping khác dưới item resource.
2. **Ổn định theo thời gian:** URL là hợp đồng API. Đổi path có thể làm client cũ không còn theo được endpoint đã lưu.
3. **Có ý nghĩa nghiệp vụ:** supervisor hoặc teams dễ hiểu hơn các tên kỹ thuật như employeeRef.
4. **Phân biệt số ít và số nhiều:** association một giá trị thường dùng tên số ít; association collection thường dùng tên số nhiều.
5. **rel rõ nghĩa:** relation nên mô tả quan hệ từ tài nguyên hiện tại, ví dụ reportsTo, memberOf hoặc directReports.
6. **Tránh phụ thuộc tên field nội bộ:** nếu đổi tên field Java nhưng muốn giữ API ổn định, hãy đặt path và rel tường minh.
7. **Kiểm tra ký tự path:** dùng tên path phù hợp với quy tắc URI và cách đặt route của ứng dụng.

Tên path và rel nên được xem là một phần của hợp đồng công khai. Nếu đã có client tiêu thụ API, cần đánh giá ảnh hưởng tương thích trước khi đổi chúng.

## 9. Kiểm tra association resource qua HTTP

Với repository employees và thuộc tính manager đã được tùy chỉnh thành path = "supervisor" và rel = "reportsTo", có thể kiểm tra theo trình tự:

**Bước 1 — Lấy item resource**

~~~http
GET /employees/42
Accept: application/hal+json
~~~

Xác nhận response có link _links.reportsTo và href trỏ tới /employees/42/supervisor.

**Bước 2 — Theo association link**

~~~http
GET /employees/42/supervisor
Accept: application/hal+json
~~~

Xác nhận response đại diện cho nhân viên được liên kết hoặc trạng thái association tương ứng.

**Bước 3 — Kiểm tra đường dẫn mặc định**

Thử đối chiếu với /employees/42/manager trong môi trường kiểm thử để xác nhận client phải dùng path đã cấu hình. Không dựa vào tên field để tự tạo URL khi server đã công bố HAL link.

**Bước 4 — Kiểm tra quan hệ collection**

Nếu thuộc tính là collection như teams, lấy item resource, theo link relation memberOf rồi xác nhận association resource trả về các phần tử liên quan.

**Bước 5 — Kiểm tra ghi và xóa quan hệ**

Thử các thao tác association được Spring Data REST hỗ trợ với đúng media type và cardinality của quan hệ. Xác nhận cả response HTTP, link HAL và dữ liệu persistence sau request. Dùng dữ liệu kiểm thử có thể khôi phục để tránh làm thay đổi quan hệ thật.

Ví dụ dùng curl để đọc link:

~~~bash
curl -H "Accept: application/hal+json" \
  http://localhost:8080/employees/42
~~~

Nếu ứng dụng có base path hoặc chạy sau reverse proxy, URL thực tế sẽ bao gồm tiền tố tương ứng. Hãy dùng href mà server trả về thay vì giả định host và base path.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Link vẫn dùng tên field cũ | Annotation đặt sai vị trí, chưa được nhận diện trong persistent property mapping hoặc ứng dụng chưa nạp bản build mới | Kiểm tra annotation nằm trên đúng thuộc tính quan hệ và restart/rebuild ứng dụng |
| URL đã đổi nhưng HAL relation chưa đổi | Chỉ cấu hình path, chưa cấu hình rel | Khai báo cả hai thuộc tính nếu muốn kiểm soát rõ URL và tên link |
| HAL relation đã đổi nhưng client gọi sai URL | Client dùng rel như một path segment | Đọc href trong link relation rồi gọi chính URL đó |
| Association không xuất hiện | Quan hệ không được export, repository không được công bố hoặc mapping không được nhận diện | Kiểm tra repository exposure, thuộc tính quan hệ, exported và cấu hình Spring Data REST |
| Đổi annotation nhưng endpoint vẫn không hoạt động | URL được gọi không đúng base path hoặc item ID; route khác chiếm path; client đang dùng cache | Kiểm tra self link, association href, status HTTP và log routing |
| Cập nhật association không lưu như mong đợi | Mapping JPA, owning side, cascade hoặc transaction không phù hợp | Kiểm tra owning side, cập nhật hai phía của object graph khi cần và xác nhận dữ liệu persistence |
| Quan hệ ngược có path không như mong muốn | Chỉ tùy chỉnh một trong hai thuộc tính của quan hệ hai chiều | Đặt @RestResource riêng trên từng thuộc tính cần công bố |

## 11. Quy trình triển khai

1. Xác định repository gốc và item resource chứa thuộc tính quan hệ.
2. Xác định quan hệ là đơn trị hay collection, một chiều hay hai chiều.
3. Kiểm tra mapping JPA hiện có và bảo đảm thuộc tính thực sự là association.
4. Đặt @RestResource(path = "...", rel = "...") trên đúng thuộc tính cần tùy chỉnh.
5. Giữ @RepositoryRestResource(path = "...") ở repository để quản lý đường dẫn collection độc lập.
6. Khởi động ứng dụng và lấy item resource với Accept: application/hal+json.
7. Đọc _links để xác nhận relation và href mới.
8. Gọi association href để kiểm tra resource được định tuyến đúng.
9. Nếu quan hệ có thể ghi, kiểm thử các thao tác cập nhật phù hợp với cardinality và xác nhận dữ liệu đã lưu.
10. Kiểm tra tương thích client trước khi phát hành thay đổi path/rel.

## 12. Checklist nhanh

- [ ] @RestResource nằm trên đúng thuộc tính quan hệ.
- [ ] path phản ánh tên endpoint association mong muốn.
- [ ] rel phản ánh ý nghĩa quan hệ mà client cần theo dõi.
- [ ] Đã phân biệt path/rel của association với path repository.
- [ ] HAL representation trả về relation và href như dự kiến.
- [ ] Client dùng href từ HAL thay vì tự ghép URL.
- [ ] Quan hệ hai chiều được cấu hình riêng ở từng thuộc tính cần công bố.
- [ ] exported = false chỉ được dùng khi thật sự muốn ẩn association.
- [ ] JPA owning side và persistence behavior vẫn đúng sau khi cập nhật.
- [ ] Bảo mật được xử lý riêng với việc công bố association.

## 13. Ghi nhớ

Để tùy chỉnh association resource trên một thuộc tính quan hệ, đặt **@RestResource** ngay trên thuộc tính đó:

~~~java
@ManyToOne
@RestResource(path = "supervisor", rel = "reportsTo")
private Employee manager;
~~~

- path tạo đoạn URL /supervisor cho association resource.
- rel tạo tên _links.reportsTo trong HAL representation.
- @RepositoryRestResource(path = "employees") vẫn quản lý collection resource /employees.
- Annotation không đổi tên field, mapping JPA, khóa ngoại hoặc quy tắc phân quyền.

Hãy để client khám phá API qua link relation và href mà server công bố. Khi đó, server có thể điều chỉnh path nội bộ mà client vẫn dựa trên hợp đồng liên kết có ý nghĩa.

## Tài liệu tham khảo

- Spring Data REST Reference — Associations: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Customizing the REST endpoint paths: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Spring Data REST — RestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RestResource.html
- Spring Data REST — RepositoryRestResource API: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html
