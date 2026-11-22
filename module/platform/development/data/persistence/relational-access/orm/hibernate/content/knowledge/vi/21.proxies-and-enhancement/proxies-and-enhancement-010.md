# Không để tuần tự hóa, debugger, log hoặc toString vô tình tải cả đồ thị

## 1. Vì sao một dòng log có thể phát ra hàng chục câu SQL?

Hibernate ORM thường dùng lazy loading để chỉ tải association khi ứng dụng thực sự cần dữ liệu. Một entity có thể chứa proxy hoặc persistent collection thay vì toàn bộ object graph ngay khi được truy vấn.

Ví dụ:

```java
Department department = session.find(Department.class, 10L);

// Collection employees có thể vẫn chưa được khởi tạo.
log.debug("Department: {}", department);
```

Nếu `Department.toString()` duyệt qua `employees`, dòng log có thể khởi tạo collection. Nếu mỗi Employee lại tham chiếu Department, Project hoặc Task, việc in object có thể tiếp tục đi sâu vào graph.

Những tác nhân tưởng như chỉ để quan sát dữ liệu cũng có thể kích hoạt getter:

- Java serialization hoặc serializer JSON.
- Jackson khi chuyển entity thành response.
- Debugger hiển thị object, mở cây thuộc tính hoặc evaluate expression.
- Logger định dạng message và gọi `toString()`.
- Lombok tạo `toString()`, `equals()` hoặc `hashCode()` từ các field.
- IDE, template engine hoặc thư viện mapping tự introspect bean.

Hệ quả có thể là N+1 SELECT, tải cả đồ thị, `LazyInitializationException`, `StackOverflowError`, tăng bộ nhớ/độ trễ và lộ dữ liệu trong log hoặc JSON.

Mục tiêu là giữ việc quan sát entity **không làm thay đổi hành vi tải dữ liệu ngoài ý muốn**. Cần hiểu proxy và enhancement hoạt động ra sao, những thao tác nào kích hoạt lazy loading, cách thiết kế toString/logging/DTO và cách kiểm chứng SQL thực tế.

## 2. Lazy proxy và persistent collection hoạt động thế nào?

### 2.1. Proxy cho association to-one

Ví dụ:

```java
@Entity
public class Employee {
    @Id
    private Long id;

    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;
}
```

Khi tải Employee, Hibernate có thể gán một proxy cho Department. Proxy giữ định danh cần thiết và trì hoãn việc tải state của Department đến khi ứng dụng truy cập thuộc tính cần dữ liệu.

```text
Employee#501 được tải
        |
        +-- id = 501
        +-- fullName = "An"
        +-- department = proxy Department#10
                                  |
                                  | truy cập thuộc tính cần initialize
                                  v
                           SELECT departments ...
```

Không phải mọi method gọi trên proxy đều nhất thiết khởi tạo target. Một số thao tác lấy identifier có thể được Hibernate xử lý mà không tải toàn bộ entity, tùy proxy, access strategy và phiên bản. **Không giả định getter ID luôn miễn phí SQL nếu chưa kiểm chứng mapping cụ thể.**

### 2.2. Persistent collection cho to-many

Với:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
private List<Employee> employees = new ArrayList<>();
```

Hibernate thường quản lý collection bằng một wrapper như persistent collection. Wrapper theo dõi trạng thái initialized và phối hợp tải dữ liệu khi collection được truy cập.

Những thao tác thường làm collection khởi tạo:

```java
department.getEmployees().size();
department.getEmployees().isEmpty();
department.getEmployees().iterator();
department.getEmployees().get(0);
department.getEmployees().stream().count();
```

Chi tiết có thể khác với extra-lazy collection hoặc mapping cụ thể. Quy tắc thực tế: khi cần nội dung collection, Hibernate thường phải tải collection hoặc thực hiện truy vấn tương ứng.

### 2.3. Bytecode enhancement và lazy attribute

Hibernate có thể dùng bytecode enhancement để chèn logic theo dõi field access, dirty tracking và lazy attribute loading. Với enhancement, một số thuộc tính lazy có thể được nạp khi field được truy cập mà không cần proxy subclass theo cách truyền thống.

Enhancement không làm serializer, debugger hay logger trở nên vô hại. Khi công cụ đọc thuộc tính được intercept, Hibernate vẫn có thể thực hiện load. Proxy và enhancement khác nhau ở cách phát hiện access, nhưng **việc quan sát giá trị lazy vẫn có thể kích hoạt database I/O**.

### 2.4. LAZY không phải cam kết “không có SQL”

`FetchType.LAZY` cho phép provider trì hoãn việc nạp dữ liệu. Nó không có nghĩa getter không bao giờ phát SQL, collection có thể được đọc sau khi Session đóng, serializer sẽ bỏ qua association, hay debugger có thể mở object graph mà không tác động Hibernate.

Hãy coi proxy và persistent collection là **đối tượng có hành vi**, không phải POJO đã chứa sẵn toàn bộ dữ liệu.

## 3. Đồ thị entity hai chiều có thể tự gọi đệ quy

Ví dụ Department:

```java
@Entity
public class Department {
    @Id
    private Long id;
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();

    @Override
    public String toString() {
        return "Department{" +
            "id=" + id +
            ", name='" + name + '\'' +
            ", employees=" + employees +
            '}';
    }
}
```

Employee:

```java
@Entity
public class Employee {
    @Id
    private Long id;
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    private Department department;

    @Override
    public String toString() {
        return "Employee{" +
            "id=" + id +
            ", fullName='" + fullName + '\'' +
            ", department=" + department +
            '}';
    }
}
```

Khi gọi `System.out.println(department)`, chuỗi lời gọi có thể thành:

```text
Department.toString()
  -> employees.toString()
      -> Employee.toString()
          -> department.toString()
              -> employees.toString()
                  -> ...
```

Ngoài việc khởi tạo collection, chuỗi này có thể lặp vô hạn và gây `StackOverflowError`. Nếu proxy gọi getter dẫn tới truy vấn, việc in object còn có thể kéo theo SQL.

**Không đưa association hai chiều vào `toString()` của entity.** Một cách an toàn hơn là chỉ hiển thị identifier và vài scalar field có ý nghĩa.

## 4. Thiết kế toString() an toàn cho entity

`toString()` dành cho entity thường phục vụ log/debug ngắn gọn, không phải xuất toàn bộ object graph.

```java
@Entity
public class Department {
    @Id
    private Long id;

    private String code;
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();

    @Override
    public String toString() {
        return "Department{" +
            "id=" + id +
            ", code='" + code + '\'' +
            ", name='" + name + '\'' +
            '}';
    }
}
```

Ví dụ chỉ sử dụng scalar field trên instance. Nó không gọi getter của association, không duyệt collection và không phụ thuộc Session còn mở.

Nguyên tắc:

- Chỉ đưa vào `toString()` scalar field nhỏ, không nhạy cảm và không lazy.
- Không đưa collection, to-one association hoặc entity tham chiếu vào chuỗi.
- Không gọi method tiện ích có thể duyệt graph.
- Tránh in BLOB, JSON document hoặc text dài.
- Không in password, token, secret, payment data hoặc dữ liệu cá nhân không cần thiết.
- Không giả định identifier luôn có; entity transient có thể chưa được gán ID.

### Có nên gọi getter ID trong toString()?

Với nhiều mapping, identifier có thể lấy từ proxy mà không initialize target, nhưng hành vi phụ thuộc proxy, access strategy và provider. Nếu cần bảo đảm `toString()` không phát SQL, hãy dùng cách biểu diễn identifier đã được kiểm chứng với mapping/version thực tế. Không truy cập association chỉ để in tên entity liên quan.

## 5. Lombok @Data và @ToString có thể vô tình duyệt association

`@Data` thường tạo getter/setter, `toString()`, `equals()`, `hashCode()` và constructor theo quy tắc Lombok. Các method sinh có thể bao gồm association fields. Nếu entity có collection lazy hoặc quan hệ hai chiều, gọi chúng có thể initialize association, truy cập proxy hoặc đệ quy.

Không nên đặt `@Data` mặc định lên entity Hibernate.

### 5.1. Dùng explicit inclusion cho toString

```java
import lombok.ToString;

@Entity
@ToString(onlyExplicitlyIncluded = true)
public class Department {

    @Id
    @ToString.Include
    private Long id;

    @ToString.Include
    private String code;

    @ToString.Include
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();
}
```

`onlyExplicitlyIncluded = true` chỉ đưa field/method có `@ToString.Include` vào chuỗi. Đây là allow-list rõ ràng hơn so với include tất cả rồi nhớ exclude từng association.

Một cách khác là `@ToString.Exclude` trên association, nhưng explicit inclusion thường dễ kiểm soát khi entity có nhiều field.

### 5.2. @EqualsAndHashCode cũng cần cẩn thận

`equals()` và `hashCode()` có thể được gọi khi thêm entity vào `HashSet`, dùng làm key `HashMap`, so sánh entity hoặc framework kiểm tra equality. Nếu method sinh tự động duyệt association, nó có thể initialize lazy state hoặc gây vòng lặp.

Hash code cũng nguy hiểm nếu field tham gia hash thay đổi sau khi object đã nằm trong hash collection. Hãy xác định equality strategy phù hợp entity identity; không dùng toàn bộ quan hệ làm equality chỉ vì Lombok có thể sinh code.

### 5.3. Một cấu hình Lombok thận trọng

```java
@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
@Entity
public class Department {

    @Id
    @ToString.Include
    @EqualsAndHashCode.Include
    private Long id;

    @ToString.Include
    private String code;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();
}
```

Đây chỉ là ví dụ allow-list field, **không phải equality strategy phổ quát**. Với ID generated, hai entity transient có `id = null` có thể bị coi bằng nhau nếu chỉ so sánh ID đơn giản. Cần thiết kế equals/hashCode phù hợp vòng đời transient/managed/detached và proxy semantics; nhiều dự án tự viết method để kiểm soát các trường hợp này.

## 6. Logging: phân biệt lazy initialization và eager argument evaluation

Logging có hai thời điểm đáng chú ý:

1. Java đánh giá biểu thức truyền vào logger.
2. Logging framework định dạng message và gọi `toString()` nếu cần.

### 6.1. String concatenation luôn được đánh giá trước

```java
log.debug("Department: " + department);
```

Java phải tạo chuỗi trước khi gọi `debug()`. Vì vậy `department.toString()` có thể được gọi **ngay cả khi DEBUG đang tắt**.

### 6.2. Parameterized logging trì hoãn định dạng khi level tắt

```java
log.debug("Department: {}", department);
```

Với SLF4J và backend tương thích, nếu DEBUG bị tắt, logger thường không định dạng message và không gọi `toString()` của argument. Điều này tránh chi phí định dạng.

Nhưng khi DEBUG bật, logger sẽ cần biểu diễn object và có thể gọi `toString()`. Nếu method này duyệt association, lazy loading vẫn xảy ra.

### 6.3. Argument expression vẫn chạy ngay

```java
log.debug("Employee count: {}", department.getEmployees().size());
```

Dù DEBUG tắt, Java vẫn phải tính `department.getEmployees().size()` trước khi gọi logger. Collection có thể được khởi tạo và SQL có thể chạy.

Parameterized logging **không trì hoãn việc đánh giá mọi biểu thức Java**. Nó chỉ giúp trì hoãn phần định dạng message khi logger không bật level.

### 6.4. Logging an toàn hơn

```java
log.debug(
    "Department id={}, code={}",
    departmentId,
    departmentCode
);
```

Ưu tiên scalar value đã có sẵn từ command, DTO hoặc projection. Tránh truyền entity graph vào logger nếu không kiểm soát được `toString()`.

Một số logging API hỗ trợ supplier/lambda để trì hoãn tạo message. Supplier chỉ trì hoãn code nằm trong lambda; nếu code đó truy cập association thì lazy loading vẫn xảy ra khi lambda được thực thi.

## 7. Debugger có thể gọi getter mà lập trình viên không chủ ý

Nhiều IDE có tính năng tự hiển thị object:

- Evaluate `toString()` để hiện object trong Variables.
- Tự gọi getter để tạo bean/property view.
- Render collection bằng cách gọi size hoặc iterator.
- Mở rộng node association trong object tree.
- Thực thi watch expression.

Nếu debugger tự gọi `department.getEmployees()`, Hibernate có thể khởi tạo collection. Khi mở rộng node Employee, debugger lại hiển thị Department, tạo chuỗi truy cập sâu hơn.

Dấu hiệu:

- Ứng dụng chạy bình thường khi không attach debugger nhưng chậm khi debug.
- SQL xuất hiện ngay sau khi mở rộng object trong Variables.
- Collection chuyển từ uninitialized sang initialized sau khi inspect.
- `LazyInitializationException` xuất hiện khi IDE gọi getter trên detached proxy.

Giảm tác động:

- Tắt tùy chọn tự gọi `toString()` hoặc tự evaluate property/getter nếu IDE hỗ trợ.
- Không mở rộng association lazy khi chỉ cần scalar field.
- Dùng watch expression chỉ đọc ID hoặc field đã biết là loaded.
- Không gọi `getEmployees().size()` trong Evaluate chỉ để “xem thử”.
- Khi cần xem dữ liệu, viết query/DTO debug có phạm vi rõ ràng trong transaction.
- Dùng SQL log để nhận biết query phát sinh lúc inspect.

Tên setting cụ thể thay đổi theo IntelliJ IDEA, Eclipse, VS Code và plugin debugger. Nguyên tắc là kiểm soát **automatic property evaluation** và tránh mở rộng lazy object graph ngoài ý muốn.

## 8. Java serialization: entity không phải wire format

Java serialization dùng object graph traversal để ghi trạng thái đối tượng vào stream. Nếu entity tham chiếu collection, collection tham chiếu child, child lại tham chiếu parent, serializer có thể đi qua toàn bộ graph.

```java
try (ObjectOutputStream out =
        new ObjectOutputStream(outputStream)) {
    out.writeObject(department);
}
```

Hành vi phụ thuộc entity/association có implement `Serializable` hay không, Hibernate proxy/persistent collection version, collection đã initialize chưa, Session còn mở hay đã đóng và custom serialization hooks.

### Proxy detached và collection lazy

```java
Department department;

try (Session session = sessionFactory.openSession()) {
    department = session.find(Department.class, 10L);
    // Không truy cập employees.
}

// Session đã đóng.
serialize(department);
```

Nếu serialization cố đọc collection chưa khởi tạo, Hibernate không thể tự chạy SELECT bằng Session đã đóng. Tùy proxy/collection và cơ chế serialization, thao tác có thể ném `LazyInitializationException` hoặc exception khác, ghi một biểu diễn proxy/initializer chưa có dữ liệu association, hoặc thất bại vì một thành phần không serializable. Hành vi có thể khác giữa các phiên bản.

**Không dựa vào serialization nội bộ của proxy để trao đổi dữ liệu giữa service/process.** Java serialization của entity Hibernate không phải hợp đồng API ổn định.

### Vì sao không chỉ giữ Session mở trong lúc serialize?

Giữ Session mở có thể khiến serialization thành công bằng cách lazy-load toàn bộ graph, nhưng có thể tạo N+1, tải dữ liệu ngoài nhu cầu, kéo dài transaction/connection và phơi bày field nội bộ. Giải pháp tốt hơn là chuyển entity sang DTO trong transaction có fetch plan rõ ràng.

## 9. JSON serialization và Jackson: getter là đường vào lazy loading

Jackson thường introspect bean properties và gọi getter để tạo JSON. Nếu getter trả proxy/collection lazy, serializer có thể duyệt tiếp vào object đó.

Ví dụ controller:

```java
@GetMapping("/departments/{id}")
public Department getDepartment(@PathVariable Long id) {
    return departmentRepository.findById(id).orElseThrow();
}
```

Khi Spring/Jackson serialize kết quả, graph có thể bị duyệt:

```text
Department
  -> employees
      -> Employee
          -> department
              -> employees
                  -> ...
```

Rủi ro gồm lazy loading khi serialize, N+1, vòng lặp JSON, LazyInitializationException và trả quá nhiều dữ liệu không thuộc hợp đồng API.

### 9.1. @JsonIgnore

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@JsonIgnore
private List<Employee> employees = new ArrayList<>();
```

`@JsonIgnore` hướng Jackson bỏ qua property này. Nhưng nó không đổi fetch strategy Hibernate, không biến entity thành DTO và không ảnh hưởng debugger/logger/serializer khác. Nếu API cần employees, hãy định nghĩa response model phù hợp.

### 9.2. @JsonManagedReference và @JsonBackReference

```java
public class Department {
    @JsonManagedReference
    private List<Employee> employees;
}

public class Employee {
    @JsonBackReference
    private Department department;
}
```

Các annotation này có thể ngăn vòng lặp serialization theo cấu hình thích hợp. Tuy nhiên, **ngăn vòng lặp không đồng nghĩa ngăn lazy loading**: Jackson vẫn có thể duyệt employees và tải collection.

### 9.3. @JsonIdentityInfo

Jackson có thể dùng object identity để biểu diễn tham chiếu lặp thay vì serialize cùng object vô hạn. Cách này giải quyết một phần biểu diễn cycle, nhưng không tự bảo đảm Hibernate association không được initialize.

**Giải quyết vòng tham chiếu JSON và kiểm soát fetch plan là hai vấn đề riêng.**

## 10. Hibernate module cho Jackson không thay thế DTO

Jackson có module tích hợp Hibernate theo phiên bản (ví dụ module dành cho Hibernate 6). Module có thể hiểu proxy/persistent collection và cung cấp tùy chọn serialize proxy chưa khởi tạo theo cách phù hợp.

Một số tùy chọn có thể ảnh hưởng:

- Có ép tải lazy property khi serialize hay không.
- Có serialize identifier của proxy chưa initialize hay không.
- Cách xử lý persistent collection và Hibernate proxy.
- Cách xử lý entity đã detached.

Tên class/package và tùy chọn thay đổi theo phiên bản Jackson Hibernate module; chọn module khớp Hibernate major version.

### Cẩn thận với FORCE_LAZY_LOADING

Nếu cấu hình buộc module tải lazy property trong serialization, serializer có thể phát SQL và tải graph. Điều này biến quá trình render response thành nơi thực hiện truy vấn ngầm.

Không bật force lazy loading chỉ để tránh lỗi detached proxy mà không đo số query và phạm vi dữ liệu.

### Serialize identifier thay vì tải proxy

Một số cấu hình module có thể biểu diễn proxy chưa initialize bằng identifier. Điều này hữu ích trong một số response, nhưng cấu trúc JSON có thể khác entity đã initialize; không bảo đảm mọi association được biểu diễn đồng nhất; không thay thế DTO và không giải quyết field nhạy cảm.

## 11. DTO là ranh giới an toàn giữa entity và API

Một cách chắc chắn để serializer không đi qua entity graph là **không trả entity Hibernate trực tiếp ra ngoài service/controller**.

Entity:

```java
@Entity
public class Department {
    @Id
    private Long id;
    private String code;
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();
}
```

DTO:

```java
public record DepartmentResponse(
    Long id,
    String code,
    String name,
    List<EmployeeSummary> employees
) {}

public record EmployeeSummary(
    Long id,
    String fullName
) {}
```

Map trong transaction:

```java
@Transactional(readOnly = true)
public DepartmentResponse getDepartment(long id) {
    Department department = repository.findById(id)
        .orElseThrow(DepartmentNotFoundException::new);

    List<EmployeeSummary> employees =
        department.getEmployees().stream()
            .map(e -> new EmployeeSummary(
                e.getId(),
                e.getFullName()
            ))
            .toList();

    return new DepartmentResponse(
        department.getId(),
        department.getCode(),
        department.getName(),
        employees
    );
}
```

Ví dụ cố ý truy cập collection trong transaction. Fetch plan phải phù hợp số Department/Employee; nếu chỉ một Department, JOIN fetch hoặc entity graph có thể hợp lý. Nếu nhiều Department, BATCH/SUBSELECT hoặc DTO projection có thể tốt hơn.

Khi method trả về, response chỉ chứa scalar và DTO Java thông thường. Jackson không còn cần đi qua Hibernate proxy để tạo JSON.

### DTO không tự làm query nhanh

Nếu mapper gọi getter trên collection LAZY của 100 entity, vẫn có thể tạo N+1 trước khi DTO được tạo. DTO bảo vệ **ranh giới serialization**, nhưng cần fetch plan đúng ở tầng đọc dữ liệu.

## 12. DTO projection trực tiếp từ query

Nếu API chỉ cần một số field, có thể tránh hydrate entity graph:

```java
public record DepartmentRow(
    Long id,
    String code,
    String name
) {}
```

```java
List<DepartmentRow> rows = entityManager.createQuery(
    "select new com.example.api.DepartmentRow(" +
    " d.id, d.code, d.name" +
    ") from Department d " +
    "where d.active = true",
    DepartmentRow.class
).getResultList();
```

Projection trả dữ liệu cần thiết, không mang collection lazy của entity ra ngoài. Nếu cần employee summary, có thể viết query riêng lấy employee rows cho tập department IDs, DTO query có join/aggregate hoặc chia batch theo ID.

## 13. Explicit fetch plan: chỉ tải thứ API thực sự cần

### 13.1. JOIN FETCH cho một owner

```java
Department department = entityManager.createQuery(
    "select distinct d " +
    "from Department d " +
    "left join fetch d.employees " +
    "where d.id = :id",
    Department.class
)
.setParameter("id", id)
.getSingleResult();
```

Phù hợp khi một Department và collection cần được tải cùng nhau. Cần lưu ý số lượng child và các collection khác.

### 13.2. EntityGraph

```java
EntityGraph<Department> graph =
    entityManager.createEntityGraph(Department.class);
graph.addAttributeNodes("employees");

Department department = entityManager.find(
    Department.class,
    id,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

EntityGraph biểu đạt association cần fetch theo use case. Provider quyết định SQL shape; không giả định EntityGraph luôn tương đương JOIN FETCH.

### 13.3. Batch/subselect cho nhiều owner

Nếu trang cần collection của nhiều owner, cân nhắc `@BatchSize` hoặc `@Fetch(FetchMode.SUBSELECT)` khi nhóm owner và tỷ lệ collection cần dùng phù hợp. Nếu chỉ cần subset field, DTO projection thường rõ ràng hơn.

### 13.4. Không dùng EAGER để chữa lỗi serialize

Đổi collection sang EAGER có thể làm graph lớn hơn được tải trong nhiều use case, tăng query và memory. Chọn fetch plan ở query/service boundary, không biến mọi association thành eager chỉ để Jackson không gặp lazy proxy.

## 14. Không dùng OSIV như cách bảo đảm serialize an toàn

Open Session in View (OSIV) có thể giữ Session mở trong suốt request web. Điều đó khiến lazy getter trong lúc Jackson serialize có thể truy cập database.

Nhưng OSIV không làm serialization miễn phí:

- SQL có thể phát ở giai đoạn render response.
- N+1 khó phát hiện hơn vì không nằm trong service method.
- Transaction nghiệp vụ có thể đã kết thúc nhưng Session vẫn mở.
- Response latency phụ thuộc truy vấn phát sinh khi serialize.
- Dữ liệu có thể được đọc ở thời điểm khác với các bước nghiệp vụ trước đó.

OSIV là lựa chọn kiến trúc có trade-off, không phải giải pháp cho việc trả entity trực tiếp. DTO và fetch plan rõ ràng giúp kiểm soát API tốt hơn.

## 15. Serialization có thể làm lộ dữ liệu không nên công khai

Entity thường có field phục vụ persistence:

```java
@Entity
public class UserAccount {
    @Id
    private Long id;
    private String email;
    private String passwordHash;
    private String resetToken;

    @OneToMany(fetch = FetchType.LAZY, mappedBy = "user")
    private List<LoginSession> loginSessions;
}
```

Trả entity này trực tiếp từ controller có nguy cơ serialize password hash, reset token, login sessions hoặc field audit không thuộc quyền caller.

`@JsonIgnore` có thể giảm nguy cơ ở một property, nhưng allow-list DTO an toàn hơn vì response chỉ chứa những field được thiết kế để công khai.

**Không dùng entity làm hợp đồng API chỉ vì Jackson có thể serialize nó.** Schema database và schema response có vòng đời, quyền truy cập và yêu cầu tương thích khác nhau.

## 16. equals() và hashCode() cũng có thể tải graph

Không chỉ `toString()` mới nguy hiểm:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Department that)) {
        return false;
    }
    return Objects.equals(employees, that.employees);
}
```

So sánh hai collection có thể khởi tạo collection lazy, so sánh từng Employee, truy cập Department ngược lại và tạo recursion hoặc query phát sinh.

`hashCode()` cũng nguy hiểm nếu dùng association/collection. Khi entity là key trong HashMap/HashSet, một thao tác tưởng như thuần Java có thể kích hoạt lazy loading.

Nguyên tắc:

- Tránh dùng association và collection trong equals/hashCode.
- Chọn identity strategy phù hợp entity lifecycle.
- Cẩn thận với ID generated chưa có ở trạng thái transient.
- Cẩn thận với proxy subclass và cách so sánh class.
- Không để field mutable tham gia hash code khi entity đang ở trong hash collection.
- Kiểm thử equality giữa proxy, managed, detached và transient entity.

Không có một đoạn equals/hashCode đơn giản đúng cho mọi entity. Với nhiều ứng dụng, dùng business key bất biến có uniqueness thật hoặc một chiến lược ID có xử lý transient rõ ràng.

## 17. Các công cụ khác cũng có thể introspect entity

Ngoài Jackson và debugger, các thư viện sau có thể gọi getter hoặc duyệt field:

- Bean introspection và expression language.
- Template engine khi render object.
- Mapping framework như ModelMapper hoặc bean copier.
- Validation framework khi đọc property.
- JSON/XML serializers khác.
- Snapshot/testing assertion library.
- Audit/change tracking utility.
- IDE-generated watches hoặc auto display.

Hãy tìm các dấu hiệu: thư viện nhận entity thay vì DTO; tự khám phá properties; gọi getter/iterator/toString; getter có thể kích hoạt lazy load; SQL phát sinh tại thời điểm gọi thư viện chứ không phải query chính.

Nếu mapper tự động copy mọi field, giới hạn mapping theo allow-list hoặc map thủ công sang DTO. Không cho thư viện khám phá toàn bộ entity graph mặc định.

## 18. Cách kiểm tra một thao tác có khởi tạo lazy state hay không

Hibernate cung cấp helper:

```java
import org.hibernate.Hibernate;

boolean initialized =
    Hibernate.isInitialized(department.getEmployees());
```

`Hibernate.isInitialized(...)` cho biết proxy/collection đã initialized hay chưa. Nó hữu ích trong test và chẩn đoán. Tuy nhiên, biểu thức `department.getEmployees()` vẫn gọi getter; với một số mapping/bytecode enhancement, cần chú ý cách lấy reference. Helper này không thay thế SQL monitoring.

Jakarta Persistence cũng có:

```java
boolean loaded = entityManagerFactory
    .getPersistenceUnitUtil()
    .isLoaded(department, "employees");
```

`PersistenceUnitUtil.isLoaded(entity, attributeName)` là API kiểm tra trạng thái loaded theo hợp đồng JPA. Không dùng `getEmployees().size()` để “kiểm tra đã load chưa”, vì chính thao tác ấy có thể khởi tạo collection.

### SQL log

Trong ứng dụng Spring Boot với Hibernate 6:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bật tạm thời ở môi trường kiểm thử. Bind parameter logs có thể chứa dữ liệu nhạy cảm.

### Hibernate Statistics

Có thể bật statistics:

```properties
hibernate.generate_statistics=true
```

Sau đó dùng `SessionFactory.getStatistics()` để xem số entity/collection fetch và query execution theo phiên bản. Statistics có phạm vi và overhead riêng; trong test nên reset hoặc cô lập số đo giữa các kịch bản.

### StatementInspector

Hibernate cung cấp `org.hibernate.resource.jdbc.spi.StatementInspector` để quan sát SQL statement trước khi gửi JDBC. Đây là hook hữu ích trong integration test, nhưng chỉ đếm SQL không đủ xác định statement do serializer hay service phát. Có thể kết hợp correlation ID, thread context và thời điểm thực thi.

## 19. Kiểm thử: serialize không được tạo thêm SQL ngoài dự kiến

Một test hữu ích tách ba pha:

1. Tải entity theo fetch plan đã định.
2. Chụp số SQL hoặc trạng thái collection.
3. Serialize DTO/response và xác nhận không phát query ngoài dự kiến.

Ví dụ khái niệm:

```java
DepartmentResponse response =
    departmentService.getDepartment(id);

long beforeSerialization =
    sessionFactory.getStatistics().getPrepareStatementCount();

objectMapper.writeValueAsString(response);

long afterSerialization =
    sessionFactory.getStatistics().getPrepareStatementCount();

assertEquals(beforeSerialization, afterSerialization);
```

Ví dụ cần điều chỉnh cho test environment: Statistics là bộ đếm cấp SessionFactory, có thể bị nhiễu nếu test chạy song song; cần reset/cô lập và không chạy query khác giữa hai mốc.

Nếu dự án có lý do phải serialize entity, viết test riêng với đúng ObjectMapper/module production:

- Đảm bảo có lazy association chưa initialize.
- Ghi nhận số SQL trước serialization.
- Serialize và kiểm tra SQL phát sinh.
- Kiểm tra JSON không chứa field nhạy cảm.
- Thử association hai chiều để phát hiện recursion.
- Thử detached entity để thấy hành vi khi Session đóng.

### Kiểm tra debugger

Debugger khó tự động hóa hơn. Trong môi trường phát triển, tắt auto toString/getter evaluation, so sánh SQL khi không inspect và khi mở node collection, không thêm watch expression có tác dụng phụ và dùng DTO/query debug riêng khi cần xem association.

## 20. Mẫu triển khai service an toàn

Một service đọc dữ liệu có thể:

1. Chọn fetch plan.
2. Tải entity/association trong transaction.
3. Chuyển sang DTO với allow-list field.
4. Trả DTO ra controller.
5. Để Jackson serialize DTO thuần Java.

Ví dụ:

```java
@Service
public class DepartmentQueryService {

    private final EntityManager entityManager;

    public DepartmentQueryService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public DepartmentResponse getDepartment(long id) {
        Department department = entityManager.createQuery(
            "select distinct d " +
            "from Department d " +
            "left join fetch d.employees " +
            "where d.id = :id",
            Department.class
        )
        .setParameter("id", id)
        .getSingleResult();

        List<EmployeeSummary> employees =
            department.getEmployees().stream()
                .map(employee -> new EmployeeSummary(
                    employee.getId(),
                    employee.getFullName()
                ))
                .toList();

        return new DepartmentResponse(
            department.getId(),
            department.getCode(),
            department.getName(),
            employees
        );
    }
}
```

Đây là ví dụ cho một Department và collection cần dùng ngay. Nếu collection có thể rất lớn, đừng join fetch toàn bộ; hãy phân trang Employee bằng query riêng và trả DTO phù hợp.

Controller:

```java
@RestController
@RequestMapping("/departments")
public class DepartmentController {

    private final DepartmentQueryService queryService;

    public DepartmentController(DepartmentQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    public DepartmentResponse get(@PathVariable long id) {
        return queryService.getDepartment(id);
    }
}
```

Controller không nhận entity Hibernate; response model đã được tạo trong service. Serializer không cần gọi getter trên proxy hoặc collection wrapper.

## 21. Cẩn thận với logging trong exception handler

Khi bắt lỗi, nhiều ứng dụng ghi:

```java
log.error("Failed to process department: {}", department, ex);
```

Nếu log level bật và `toString()` duyệt association, error handling có thể tạo thêm SQL ngay sau lỗi chính. Nếu transaction đã rollback hoặc Session đóng, logger thậm chí có thể gây thêm LazyInitializationException/exception phụ.

Nên ghi:

```java
log.error(
    "Failed to process departmentId={}, requestId={}",
    departmentId,
    requestId,
    ex
);
```

Giữ log exception và correlation ID; không cần serialize entity graph để điều tra.

## 22. Tránh đưa entity vào message queue hoặc distributed cache

Java serialization của entity có thể gắn với Hibernate proxy/initializer, persistent collection wrapper, lazy attribute interceptor, entity class/version và association graph lớn.

Đưa object đó vào message broker hoặc distributed cache làm producer/consumer phụ thuộc chi tiết ORM, classpath và version. Consumer không có Session của producer để lazy-load.

Thay vào đó, định nghĩa message contract:

```java
public record DepartmentChangedEvent(
    Long departmentId,
    String departmentCode,
    String eventId,
    Instant occurredAt
) {}
```

Message nên chứa identifier và dữ liệu cần thiết theo hợp đồng sự kiện. Nếu consumer cần thêm thông tin, nó tải theo service/database riêng và có xử lý version/idempotency phù hợp.

## 23. Những hiểu nhầm thường gặp

### “LAZY nghĩa là serializer sẽ bỏ qua association”

Không. Serializer có thể gọi getter và khởi tạo lazy association.

### “Jackson chỉ đọc field nên không gọi Hibernate”

Không thể mặc định. Jackson có nhiều cách introspect; getter/field visibility và module/configuration quyết định hành vi. Dù đọc field trực tiếp, không nên coi đây là cách bảo đảm an toàn cho entity graph.

### “@JsonIgnore sửa được N+1”

Nó có thể loại một property khỏi JSON nhưng không sửa fetch plan chung, logging/debugger hoặc các đường truy cập khác.

### “@JsonManagedReference giải quyết lazy loading”

Không. Nó giúp quản lý tham chiếu vòng trong JSON, không ngăn association được truy cập.

### “Parameterized logging không thể gây lazy loading”

Không. Nó tránh định dạng khi level tắt, nhưng khi level bật có thể gọi toString; argument expression cũng luôn được đánh giá trước.

### “Debugger chỉ hiển thị dữ liệu đã có”

Không. IDE có thể gọi getter/toString hoặc duyệt collection khi render object.

### “Lombok @Data an toàn cho mọi entity”

Không. Các method sinh tự động có thể duyệt mọi field, kể cả lazy association và quan hệ hai chiều.

### “Giữ Session mở là giải pháp tốt nhất”

Không. Nó có thể biến serialization thành nguồn phát query không kiểm soát, tăng N+1 và giữ tài nguyên lâu hơn.

### “DTO tự động loại bỏ N+1”

Không. Mapper có thể gọi collection lazy và phát N+1 trước khi tạo DTO. DTO cần đi cùng fetch plan phù hợp.

### “Nếu object serialize được thì có thể dùng làm API”

Không. Serializable không đồng nghĩa schema ổn định, an toàn hoặc phù hợp để công khai.

## 24. Quy trình điều tra khi log/serialize làm tải cả graph

Khi thấy SQL phát sinh lúc log, debug hoặc serialize:

1. **Xác định điểm kích hoạt.** Logger gọi `toString()`, Jackson gọi getter, debugger evaluate property hay mapper duyệt graph?
2. **Xác định association lazy.** Proxy to-one, persistent collection hay lazy basic attribute nào được khởi tạo?
3. **Đọc SQL log.** Một query hay chuỗi N+1? Query phát sinh trong service, serialization hay exception handler?
4. **Kiểm tra vòng quan hệ.** Có parent-child tham chiếu hai chiều khiến toString/serializer đệ quy không?
5. **Kiểm tra code sinh tự động.** Lombok `@Data`, `@ToString`, `@EqualsAndHashCode` có bao gồm association không?
6. **Kiểm tra Session scope.** Collection được truy cập khi Session mở hay sau khi detach/close?
7. **Chọn response/log shape.** DTO allow-list hoặc scalar IDs có đủ không?
8. **Chọn fetch plan.** JOIN, EntityGraph, BATCH, SUBSELECT hay projection theo use case?
9. **Đo lại số query và dữ liệu.** Không chỉ xác nhận exception biến mất.
10. **Thêm regression test.** Serialize/log response không được tạo SQL ngoài dự kiến và không lộ dữ liệu nhạy cảm.

## 25. Bài thực hành: tìm một dòng log gây N+1

Tạo Department có nhiều Employee, mapping employees LAZY.

### Phần A — toString nguy hiểm

1. Viết `Department.toString()` in cả employees.
2. Tải 20 Department trong một Session.
3. Gọi `log.debug("Departments: {}", departments)` khi DEBUG bật.
4. Quan sát SQL và số collection được khởi tạo.
5. Thử tắt DEBUG và so sánh với `log.debug("Departments: " + departments)`.

Mục tiêu: phân biệt parameterized logging với string concatenation và nhận ra `toString()` có thể duyệt graph.

### Phần B — Debugger

1. Đặt breakpoint sau query Department.
2. Quan sát SQL trước khi inspect.
3. Mở rộng `employees` trong Variables.
4. Quan sát SQL phát sinh.
5. Tắt automatic toString/property evaluation và lặp lại.

### Phần C — Jackson

1. Trả trực tiếp entity Department từ controller test.
2. Dùng ObjectMapper production để serialize.
3. Kiểm tra SQL, recursion và LazyInitializationException.
4. Thêm DTO response và map trong transaction.
5. Xác nhận serialize DTO không phát thêm SQL.

### Phần D — Lombok

1. Thêm `@Data` vào một entity hai chiều.
2. Gọi `toString()`, `equals()` và `hashCode()`.
3. Quan sát lazy initialization/recursion.
4. Chuyển sang explicit inclusion và equality strategy phù hợp.

### Phần E — Detached entity

1. Tải Department nhưng không initialize employees.
2. Đóng Session.
3. Thử serialize.
4. Ghi nhận hành vi theo Hibernate/Jackson module đang dùng.
5. Chuyển sang DTO được tạo trong transaction và so sánh.

## 26. Checklist thiết kế an toàn

| Vị trí | Nên làm | Tránh |
|---|---|---|
| Entity `toString()` | ID và scalar field nhỏ, không nhạy cảm | Collection/to-one association |
| Lombok | Getter/setter chọn lọc, explicit include/exclude | `@Data` mặc định trên entity graph |
| equals/hashCode | Identity strategy rõ ràng, không duyệt association | So sánh collection hoặc entity graph |
| Logging | ID, business key, correlation ID, scalar đã có | Truyền entity graph hoặc gọi getter lazy trong argument |
| Debugger | Xem scalar/ID, tắt auto evaluation nếu cần | Mở rộng toàn bộ association lazy |
| Java serialization | Dùng DTO/message contract | Dùng Hibernate entity/proxy làm wire format |
| Jackson | Serialize DTO allow-list | Trả entity graph trực tiếp |
| Fetch plan | Query/EntityGraph/BATCH/SUBSELECT theo use case | Đổi mọi association sang EAGER |
| Session | Map DTO khi context còn hợp lệ | Trông chờ lazy loading sau khi Session đóng |
| Kiểm thử | Đếm SQL, kiểm tra initialized state và field response | Chỉ kiểm tra JSON “có kết quả” |

## 27. Nguyên tắc cần ghi nhớ

1. **Hibernate proxy và persistent collection là các object có hành vi**, có thể tải dữ liệu khi getter/iterator/size hoặc thao tác tương ứng được gọi.
2. **Bytecode enhancement không loại bỏ rủi ro lazy loading do quan sát.** Field access có thể được intercept và kích hoạt tải thuộc tính.
3. **Không đưa association vào toString() của entity.** Graph hai chiều có thể vừa tạo N+1 vừa đệ quy vô hạn.
4. **Tránh @Data mặc định trên entity.** Kiểm soát riêng toString, equals và hashCode; exclude association một cách tường minh.
5. **Parameterized logging chỉ trì hoãn formatting**, không trì hoãn argument expression; khi DEBUG bật, logger vẫn có thể gọi toString.
6. **Debugger có thể tự gọi getter/toString hoặc duyệt collection.** Kiểm soát auto evaluation và dùng scalar watch expressions.
7. **Java serialization và JSON serialization không phải fetch strategy.** Chúng có thể duyệt object graph và khởi tạo lazy state.
8. **@JsonIgnore/back-reference xử lý cách biểu diễn JSON**, không thay thế fetch plan và không bảo vệ mọi đường truy cập.
9. **DTO allow-list là ranh giới API rõ ràng**, nhưng cần map với fetch plan phù hợp để tránh N+1 ngay trong service.
10. **Kiểm chứng bằng SQL log, statistics và integration test.** Một thao tác log/serialize an toàn phải không tạo query ngoài dự kiến và không làm lộ dữ liệu.

Khi một thao tác tưởng như chỉ để xem object lại khiến Hibernate tải nhiều dữ liệu, hãy lần theo chuỗi **công cụ quan sát → getter/toString/property traversal → proxy/collection initialization → SQL**. Thiết kế entity gọn, DTO rõ ràng và fetch plan có chủ đích sẽ giữ cho log, debugger và serialization không trở thành một truy vấn database ẩn.

### Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Bytecode enhancement](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#BytecodeEnhancement)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM Javadocs — Hibernate utility class](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/Hibernate.html)
- [Hibernate ORM Javadocs — PersistentCollection](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/collection/spi/PersistentCollection.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Jackson Datatype Hibernate modules](https://github.com/FasterXML/jackson-datatype-hibernate)
- [Lombok — @ToString](https://projectlombok.org/features/ToString)
- [Lombok — @EqualsAndHashCode](https://projectlombok.org/features/EqualsAndHashCode)
- [SLF4J Manual — Parameterized logging](https://www.slf4j.org/manual.html)
