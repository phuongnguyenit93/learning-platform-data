# Lạm dụng CascadeType.ALL hoặc REMOVE trên quan hệ dùng chung

Trong JPA/Hibernate, cascade cho phép một thao tác lifecycle trên entity này được truyền sang entity liên quan. Cơ chế này rất hữu ích khi một entity thực sự sở hữu vòng đời của entity khác, chẳng hạn `PurchaseOrder` sở hữu các `OrderLine` riêng của nó. Nhưng cascade trở nên nguy hiểm khi được áp dụng máy móc cho một quan hệ dùng chung như `Order -> Product`, `Student -> Course`, `User -> Role` hoặc `Article -> Category`.

Lỗi điển hình là:

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses = new HashSet<>();
```

Một lập trình viên xóa một `Student`, nghĩ rằng Hibernate chỉ xóa các liên kết trong bảng join, nhưng `CascadeType.ALL` còn bao gồm `REMOVE`. Vì vậy, thao tác remove có thể được truyền sang các `Course` được nhiều sinh viên dùng chung. Kết quả có thể là xóa nhầm dữ liệu dùng chung, lỗi foreign key vì course còn được tham chiếu, hoặc một graph bị xóa rộng hơn ý định nghiệp vụ.

**Nguyên tắc cốt lõi:** Cascade phải phản ánh quyền sở hữu vòng đời, không chỉ phản ánh việc hai entity có liên kết với nhau. Nếu một entity có thể tồn tại độc lập hoặc được nhiều aggregate khác tham chiếu, thao tác xóa parent thường không được xóa target đó.

Bài học phân biệt từng cascade type, giải thích vì sao `ALL` đặc biệt nguy hiểm trên `@ManyToOne` và `@ManyToMany`, cách thiết kế association dùng chung, sự khác nhau giữa ORM cascade và database `ON DELETE CASCADE`, cách xử lý join rows và orphan removal, cùng các integration tests phát hiện xóa nhầm trước khi triển khai.

---

## 1. Cascade là gì?

Một association có thể khai báo các thao tác được truyền từ entity nguồn sang entity đích:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi gọi:

```java
entityManager.persist(order);
```

JPA có thể áp dụng `persist()` cho các `OrderLine` trong association được cấu hình cascade PERSIST.

Cascade trả lời câu hỏi:

> Khi thực hiện một thao tác lifecycle trên entity A, thao tác nào được lan truyền tới entity B qua association này?

Cascade **không** trả lời:
- Ai sở hữu foreign key?
- Entity B có thể được dùng chung không?
- Xóa A có đồng nghĩa xóa B về mặt nghiệp vụ không?
- Database có `ON DELETE CASCADE` không?
- Một child bị tách khỏi collection có bị xóa không?
- Association có phải aggregate boundary không?

Những câu hỏi này cần được thiết kế riêng.

## 2. Các giá trị của CascadeType

Jakarta Persistence định nghĩa các thao tác cascade:

| Cascade type | Thao tác được truyền | Tình huống thường gặp |
| --- | --- | --- |
| `PERSIST` | `persist()` | Tạo aggregate mới cùng các entity con riêng |
| `MERGE` | `merge()` | Đồng bộ detached graph khi lifecycle thực sự gắn nhau |
| `REMOVE` | `remove()` | Xóa dependent entity thuộc riêng parent |
| `REFRESH` | `refresh()` | Làm mới graph phụ thuộc cùng parent |
| `DETACH` | `detach()` | Detach graph có vòng đời persistence gắn nhau |
| `ALL` | Tất cả các thao tác trên | Chỉ khi mọi thao tác đều có semantics phù hợp |

`CascadeType.ALL` tương đương việc bật cả `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH`. Vì vậy, thêm `ALL` chỉ để một thao tác `save()` tiện hơn có thể vô tình bật luôn quyền xóa target.

### 2.1. ALL không phải là “lưu mọi thứ liên quan”

Cách hiểu sai thường gặp:

> Hai entity có association thì dùng `CascadeType.ALL` để Hibernate tự quản lý cả hai.

Cách hiểu đúng:

> Chỉ cascade những thao tác mà entity nguồn thực sự có quyền thực hiện lên entity đích.

Một `Order` có thể tham chiếu `Product`, nhưng không sở hữu lifecycle của `Product`. Một `Student` có thể đăng ký `Course`, nhưng không sở hữu lifecycle của `Course`.

## 3. Shared reference khác dependent child

Hãy phân biệt hai mô hình:

<escape>
```text
Aggregate có child riêng:

PurchaseOrder
  |
  +-- OrderLine A
  +-- OrderLine B

OrderLine chỉ có ý nghĩa trong Order này.
Xóa Order thường đồng nghĩa xóa các OrderLine.


Quan hệ tới dữ liệu dùng chung:

PurchaseOrder A ----+
                    |
PurchaseOrder B ----+---- Product X
                    |
PurchaseOrder C ----+

Product X có thể được nhiều Order tham chiếu.
Xóa một Order không được xóa Product X.
```
</escape>

| Đặc điểm | Dependent child | Shared reference |
| --- | --- | --- |
| Có thể tồn tại độc lập? | Thường không | Có |
| Được nhiều parent dùng chung? | Thường không | Có thể |
| Parent có quyền xóa target? | Thường có | Thường không |
| `REMOVE` cascade | Có thể phù hợp | Thường nguy hiểm |
| `orphanRemoval` | Có thể phù hợp | Thường không phù hợp |
| Ví dụ | `OrderLine`, `OrderAddress` riêng | `Product`, `Role`, `Category`, `Course` |

Tên association không quyết định ownership. Cần xem domain lifecycle: ai tạo, ai quản lý, ai có quyền xóa và target có được tham chiếu từ nơi khác không.

## 4. Ví dụ nguy hiểm: `@ManyToOne(cascade = ALL)`

Một Order tham chiếu Product:

```java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, cascade = CascadeType.ALL)
    @JoinColumn(name = "product_id")
    private Product product;
}
```

`Product` là dữ liệu danh mục dùng chung:

```java
@Entity
class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
```

Đặt `ALL` ở `PurchaseOrder.product` có nghĩa thao tác remove Order có thể cascade remove Product. Điều đó sai nếu Product còn được Order khác hoặc module khác sử dụng.

### 4.1. Kết quả có thể là lỗi FK hoặc xóa nhầm

Nếu Product còn được Order B tham chiếu, DB có thể từ chối DELETE do FK. Nếu không có reference khác, Hibernate có thể xóa Product mặc dù nghiệp vụ chỉ yêu cầu xóa Order A.

Cả hai kết quả đều cho thấy mapping trao quyền xóa quá rộng cho Order.

### 4.2. Mapping phù hợp hơn

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

Không khai báo cascade nếu Product được quản lý độc lập. Order chỉ giữ reference tới Product.

Nếu Order cần ghi snapshot tên/giá sản phẩm tại thời điểm đặt hàng, hãy lưu snapshot fields trong `OrderLine` hoặc một value object phù hợp. Không dùng cascade để biến Product catalog thành child riêng của Order.

## 5. Ví dụ nguy hiểm: `@ManyToMany(cascade = ALL)`

Mô hình Student/Course:

```java
@Entity
class Student {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany(cascade = CascadeType.ALL)
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
```

```java
@Entity
class Course {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
```

Một Course có thể được nhiều Students đăng ký. Xóa Student không có nghĩa xóa Course.

Nếu cascade REMOVE lan sang Course, Hibernate có thể cố xóa target entity. Database có thể chặn vì `student_courses` hoặc association khác vẫn tham chiếu Course; hoặc xóa target khi không còn reference nào dù Course vẫn là một tài nguyên danh mục cần tồn tại.

### 5.1. Hành vi cần có khi xóa Student

Thông thường, khi xóa Student:
- Các membership rows của Student trong `student_courses` được xóa để không còn association.
- Các Course rows vẫn tồn tại.
- Enrollment/history cần giữ lại nếu có yêu cầu nghiệp vụ riêng.

Mapping thường không cần cascade REMOVE:

```java
@ManyToMany
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
```

Nếu cần `PERSIST` hoặc `MERGE`, hãy đánh giá riêng. Trong hệ thống Course được tạo/quản lý bởi catalog service, Student enrollment thường chỉ liên kết Course đã tồn tại; service nên resolve Course reference thay vì cascade persist nó.

## 6. Vì sao `REMOVE` đặc biệt nguy hiểm trên quan hệ dùng chung?

`REMOVE` biến thao tác xóa nguồn thành một yêu cầu xóa đích. Với target dùng chung, nguồn thường không có đủ thông tin để biết mọi consumer khác.

Ví dụ:
- Xóa một `User` có thể cascade xóa `Role` mà nhiều users khác đang dùng.
- Xóa một `Article` có thể cascade xóa `Category` mà nhiều articles khác tham chiếu.
- Xóa một `Order` có thể cascade xóa `Product` hoặc `Customer`.
- Xóa một `TeamMembership` không nên xóa `User` hoặc `Team`.
- Xóa một `Invoice` không nên xóa `Currency` hoặc `TaxRate` reference.

Quyền xóa entity dùng chung cần thuộc service/aggregate sở hữu entity đó, với kiểm tra usage và policy riêng.

## 7. JPA portability: REMOVE cascade chỉ phù hợp trên OneToOne/OneToMany

Jakarta Persistence quy định portable applications chỉ nên áp dụng cascade REMOVE cho `@OneToOne` và `@OneToMany`. Việc dùng REMOVE cascade trên `@ManyToOne` hoặc `@ManyToMany` không phải mapping portable theo specification.

Một số Hibernate versions có thể chấp nhận hoặc thực thi mapping ngoài vùng portable, nhưng không nên dựa vào behavior đó cho thiết kế ứng dụng đa provider hoặc nâng cấp lâu dài.

Điều này làm các cấu hình sau đặc biệt đáng xem lại:

```java
@ManyToOne(cascade = CascadeType.REMOVE)
private Product product;
```

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
```

`ALL` bao gồm REMOVE, nên nó cũng mang rủi ro portability và lifecycle nêu trên. Hãy đối chiếu đúng Jakarta Persistence version và Hibernate version của ứng dụng.

## 8. Cascade PERSIST trên shared reference cũng có thể sai

Không phải chỉ REMOVE mới nguy hiểm.

Giả sử request gửi:

```json
{
  "product": {
    "id": 10,
    "name": "Laptop"
  }
}
```

Service tạo Order và gắn một object Product mới chỉ có ID:

```java
Product product = new Product();
product.setId(10L);

PurchaseOrder order = new PurchaseOrder();
order.setProduct(product);

entityManager.persist(order);
```

Nếu association có `cascade = PERSIST`, Hibernate có thể cố persist Product object đó như entity mới. Kết quả có thể là:
- Entity đã tồn tại bị xem như detached entity.
- Duplicate primary key.
- `EntityExistsException`/persistence exception.
- Một Product mới được tạo nếu ID được gán sai hoặc mapping cho phép.
- Request có thể ghi đè/làm sai ownership nếu service dùng graph từ client không an toàn.

### 8.1. Resolve reference bằng persistence context

Với shared entity đã tồn tại:

```java
Product product =
    entityManager.getReference(Product.class, productId);

PurchaseOrder order = new PurchaseOrder();
order.setProduct(product);

entityManager.persist(order);
```

`getReference()` cho phép tạo reference managed tới entity theo ID mà không cần load toàn bộ state ngay; truy cập proxy có thể phát SELECT và ID không tồn tại có thể chỉ phát hiện muộn.

Nếu cần kiểm tra tồn tại/trạng thái/giá/quyền tenant, hãy query và validate Product trước khi tạo Order. `getReference()` không thay thế authorization hoặc business validation.

### 8.2. Không nhận nguyên entity graph từ request rồi cascade persist

API nên nhận IDs/commands và service resolve references trong transaction. Điều này tránh client vô tình gửi một graph có cascade persist/merge tới shared catalog entities.

## 9. Cascade MERGE có thể ghi đè shared entity state

Giả sử Product là shared reference. Một detached Order graph được gửi về:

```java
Product detachedProduct = new Product();
detachedProduct.setId(10L);
detachedProduct.setName("Tên cũ từ form");

PurchaseOrder detachedOrder = new PurchaseOrder();
detachedOrder.setProduct(detachedProduct);
```

Nếu Order có `cascade = MERGE`, gọi:

```java
PurchaseOrder managed = entityManager.merge(detachedOrder);
```

có thể merge state của Product vào managed Product theo cascade. Một form cũ hoặc client gửi thiếu/stale fields có thể ghi đè trạng thái catalog dùng chung.

Với shared references, thường nên:
- Không cascade MERGE tới target.
- Resolve target managed trong transaction.
- Gắn reference vào aggregate đang sửa.
- Chỉ cập nhật Product qua Product service/use case sở hữu nó.

Không dùng `merge()` trên detached object graph từ client như một cách cập nhật aggregate an toàn mà không kiểm soát field ownership.

## 10. Cascade REFRESH và DETACH cũng có phạm vi

`ALL` còn gồm `REFRESH` và `DETACH`.

- `REFRESH` trên nguồn có thể refresh target shared mà caller không định refresh, làm mất state chưa flush của target trong persistence context.
- `DETACH` có thể detach target đang được các phần khác của use case sử dụng; các thay đổi sau đó không còn được dirty checking.
- `MERGE` có thể lan state.
- `PERSIST` có thể cố tạo target.
- `REMOVE` có thể xóa target.

Do đó, câu hỏi không phải chỉ “có muốn cascade delete không?”. Phải xem toàn bộ thao tác lifecycle nào có thể lan qua association.

## 11. So sánh các mapping theo ownership

| Mapping | Target thường dùng chung? | Cascade REMOVE mặc định nên thế nào? |
| --- | --- | --- |
| `Order -> OrderLine` qua `@OneToMany` | Không, child thuộc riêng Order | Có thể phù hợp |
| `OrderLine -> Product` qua `@ManyToOne` | Có | Không |
| `Order -> Customer` qua `@ManyToOne` | Có | Không |
| `Student -> Course` qua `@ManyToMany` | Có | Không |
| `User -> Role` qua `@ManyToMany` | Có | Không |
| `Article -> Category` qua `@ManyToOne` | Có | Không |
| `User -> Profile` qua private `@OneToOne` | Tùy ownership | Có thể phù hợp nếu profile thực sự dependent |
| `Order -> ShippingAddress` riêng cho order | Thường không | Có thể phù hợp |

Bảng là gợi ý theo domain thường gặp, không thay thế phân tích lifecycle. Một quan hệ `@OneToOne` vẫn có thể trỏ tới tài nguyên dùng chung hoặc được quản lý độc lập; mapping cardinality không tự chứng minh ownership.

## 12. Cascade REMOVE và orphanRemoval là hai cơ chế khác nhau

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

- `CascadeType.REMOVE`: khi gọi remove parent, remove được truyền sang children.
- `orphanRemoval=true`: khi child bị loại khỏi association private ownership, provider lên lịch remove child theo orphan-removal semantics.

Cả hai có thể phù hợp với `OrderLine` riêng của Order, nhưng không phải công cụ xóa shared Product/Role/Course.

### 12.1. orphanRemoval không có nghĩa “xóa liên kết thôi”

Với private child, bỏ khỏi collection có thể xóa row child. Nếu child cần tồn tại độc lập hoặc có thể được chuyển giữa parents, orphanRemoval có thể phá dữ liệu.

Với ManyToMany shared target, không dùng orphanRemoval để mô hình hóa việc bỏ membership; thao tác đó nên xóa association row. Nếu membership có attributes/lifecycle riêng, chuyển nó thành entity trung gian.

## 13. Xóa membership khác xóa target

Trong ManyToMany:

```text
students
  id

courses
  id

student_courses
  student_id
  course_id
```

Khi Student bỏ Course:
- Xóa row `(student_id, course_id)` trong `student_courses`.
- Giữ nguyên `students`/`courses` rows.

Khi Student bị xóa:
- Xóa các join rows liên quan Student.
- Giữ Course rows.
- Nếu Course không còn student nào, đó vẫn là quyết định riêng; Course catalog có thể cần giữ nguyên.

Không cần cascade REMOVE tới Course để xóa membership.

### 13.1. Database FK cho join table

DDL thường có:

```sql
CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    PRIMARY KEY (student_id, course_id),
    CONSTRAINT fk_student_courses_student
        FOREIGN KEY (student_id) REFERENCES students(id),
    CONSTRAINT fk_student_courses_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
);
```

Xóa Student có thể xóa join rows qua ORM hoặc DB FK `ON DELETE CASCADE` trên phía `student_id`, tùy thiết kế. FK `course_id` vẫn bảo vệ Course khỏi bị xóa khi còn memberships.

DB cascade ở join table chỉ xóa rows phụ thuộc trong join table; nó không có nghĩa xóa entity Course.

## 14. Database `ON DELETE CASCADE` không giống JPA CascadeType.REMOVE

Hai cơ chế có cùng từ “cascade” nhưng chạy ở hai lớp khác nhau.

| Tiêu chí | JPA `CascadeType.REMOVE` | DB `ON DELETE CASCADE` |
| --- | --- | --- |
| Thực thi bởi | ORM/provider | Database |
| Kích hoạt khi | JPA `remove()` trên source | SQL DELETE parent |
| Cần entity graph loaded? | Không nhất thiết, provider xử lý mapping | Không |
| Gọi entity callbacks cho từng child? | ORM lifecycle có thể chạy callbacks | Không gọi Java callbacks |
| Native SQL DELETE có kích hoạt? | Không tự kích hoạt ORM cascade | Có nếu FK được khai báo |
| Envers per-entity audit? | ORM lifecycle có thể ghi audit theo mapping | DB cascade không tự gọi Envers |
| Ảnh hưởng cache ORM | Provider quản lý theo ORM operation | External/native DB changes có thể để cache stale |

Không thêm DB `ON DELETE CASCADE` để “sửa” mapping JPA sai. Hãy quyết định rõ database có quyền xóa row nào và ORM có cần lifecycle callbacks/audit cho từng entity không.

## 15. `CascadeType.REMOVE` trên `@ManyToOne`: tình huống nguy hiểm cụ thể

Ví dụ:

```java
@Entity
class OrderLine {

    @ManyToOne(cascade = CascadeType.REMOVE)
    @JoinColumn(name = "product_id")
    private Product product;
}
```

Khi remove OrderLine, Hibernate có thể truyền REMOVE sang Product. Nhưng Product có thể được nhiều OrderLines tham chiếu.

Kịch bản:
1. Product#10 được dùng bởi OrderLine#1 và OrderLine#2.
2. Xóa OrderLine#1.
3. Cascade REMOVE cố xóa Product#10.
4. FK từ OrderLine#2 hoặc bảng khác ngăn DELETE, hoặc target bị xóa nếu không có reference khác.

Mapping an toàn thường là:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

OrderLine có thể bị xóa, Product vẫn tồn tại.

## 16. `CascadeType.ALL` trên ManyToMany: tác động theo cả hai chiều?

Cần đọc chính xác cascade được khai báo ở phía nào. Cascade lan từ source entity qua association đó; nó không có nghĩa mọi entity trong toàn hệ thống tự cascade theo cả hai hướng.

Ví dụ cascade ALL ở `Student.courses`:
- Persist Student có thể persist Course targets.
- Merge Student có thể merge Course targets.
- Remove Student có thể remove Course targets.
- Refresh/Detach cũng có thể lan.

Nếu phía Course cũng khai báo cascade ALL ngược về Student, graph có thể tạo cascade traversal phức tạp, thao tác lặp và xóa lan rộng. Không cấu hình ALL đối xứng trên shared many-to-many.

## 17. Khi nào Cascade PERSIST/MERGE có thể hợp lý với shared association?

Không phải mọi cascade đều luôn sai trên shared references. Ví dụ một catalog object được tạo mới cùng use case có thể được persist riêng trước rồi gắn vào aggregate.

Tuy nhiên, nếu entity đích có lifecycle độc lập:
- `PERSIST` thường không cần nếu target đã tồn tại và được resolve.
- `MERGE` thường không cần nếu target chỉ là reference.
- `REMOVE` thường không đúng.
- `REFRESH`/`DETACH` cần cân nhắc theo persistence context usage.

Một mapping có thể chọn cascade subset rất hẹp, nhưng chỉ khi semantics đã rõ và test chứng minh. Tránh dùng ALL như default.

## 18. Mô hình hóa quan hệ dùng chung bằng entity trung gian

Nếu ManyToMany có attributes riêng, chẳng hạn Student đăng ký Course với ngày đăng ký, trạng thái và điểm, hãy tạo entity `Enrollment`:

```text
Student 1 ---- * Enrollment * ---- 1 Course
```

```java
@Entity
class Enrollment {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Student student;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Course course;

    private Instant enrolledAt;
    private EnrollmentStatus status;
}
```

Khi xóa Student:
- Có thể xóa Enrollment rows nếu chúng thuộc lifecycle Student theo policy.
- Không xóa Course.
- Có thể giữ enrollment history theo retention/audit rules.

Mapping:

```java
@OneToMany(
    mappedBy = "student",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<Enrollment> enrollments = new ArrayList<>();
```

Phía Enrollment tham chiếu Course mà không cascade REMOVE:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
private Course course;
```

Đây là mô hình rõ hơn khi quan hệ có lifecycle nghiệp vụ riêng. Có thể cần `REMOVE`/orphan removal với Enrollment tùy retention, nhưng Course vẫn là shared reference.

## 19. Quy tắc aggregate boundary

Trong thiết kế domain-driven, aggregate root kiểm soát lifecycle của entities thuộc aggregate. Một reference sang aggregate khác thường được biểu diễn bằng identity/reference, không trao toàn bộ quyền lifecycle.

Ví dụ:
- `Order` sở hữu `OrderLine`.
- `OrderLine` tham chiếu `Product`.
- `Enrollment` thuộc Student/course registration workflow nhưng tham chiếu `Course`.
- `User` có membership/role assignment; `Role` có thể được dùng bởi nhiều users.

Cascade không tự định nghĩa aggregate boundary, nhưng mapping cascade nên phản ánh boundary đã chọn.

### 19.1. Xóa aggregate root không phải xóa mọi thứ có thể đi tới

Một graph object có thể đi qua nhiều references. Nếu dùng ALL trên mọi association, thao tác remove có thể biến thành traversal xóa một phần lớn graph.

Hãy phân biệt:
- Composition/ownership.
- Association/reference.
- Membership entity.
- Shared lookup/catalog.
- Historical record.
- External resource.

## 20. `merge()` và DTO/entity graph từ client

Một pattern rủi ro:

```java
@Transactional
public void updateOrder(PurchaseOrder requestEntity) {
    entityManager.merge(requestEntity);
}
```

Client có thể gửi:
- Product object detached với tên/giá cũ.
- Customer object thiếu fields.
- Collection bị bỏ trống vì UI không tải hết.
- Child bị bỏ khỏi collection.
- References thuộc tenant khác.
- Nested graph không được phép update.

Nếu mapping dùng cascade MERGE/ALL, state có thể lan sâu và gây thay đổi ngoài ý định.

### 20.1. Dùng command DTO và resolve shared references

Ví dụ:

```java
public record UpdateOrderCommand(
    Long orderId,
    Long productId,
    int quantity
) {}
```

Service:

```java
@Transactional
public void updateOrder(UpdateOrderCommand command) {
    PurchaseOrder order =
        entityManager.find(
            PurchaseOrder.class,
            command.orderId()
        );

    Product product =
        entityManager.find(
            Product.class,
            command.productId()
        );

    if (order == null || product == null) {
        throw new EntityNotFoundException();
    }

    order.changeProduct(product);
    order.changeQuantity(command.quantity());
}
```

Đây là skeleton minh họa; cần tenant/authorization/business validation. Shared Product được resolve từ DB và gắn vào Order managed; không merge toàn bộ object Product do client gửi.

## 21. Xóa parent có cần load shared collection không?

Nếu xóa Student:
- ORM mapping không cascade REMOVE tới Course.
- Join rows cần được xóa theo mapping hoặc database constraint policy.
- Có thể cần xóa association trước khi xóa parent tùy mapping/provider/schema.
- Không cần xóa Course entities.

Nếu association collection rất lớn, load toàn bộ Course entities chỉ để xóa membership có thể tốn kém. Có thể cân nhắc bulk/native deletion hoặc DB FK `ON DELETE CASCADE` trên join table, nhưng cần quản lý cache, callbacks, Envers và persistence context.

Không dùng cascade REMOVE lên Course như một cách tránh phải xóa join rows.

## 22. Xóa association qua collection và owning side

Với bidirectional ManyToMany, owning side điều khiển join table. Nếu chỉ sửa inverse collection, membership có thể không đổi trong DB.

Khi bỏ một Course khỏi Student:

```java
student.removeCourse(course);
```

helper nên cập nhật owning collection và inverse collection trong memory nếu cả hai sides đang được giữ.

SQL logic là:

```sql
DELETE FROM student_courses
WHERE student_id = ?
  AND course_id = ?;
```

Không phải:

```sql
DELETE FROM courses
WHERE id = ?;
```

Đây là khác biệt quan trọng giữa xóa liên kết và xóa target.

## 23. Soft delete trên shared reference

Nếu Product được soft-delete:
- Xóa Order không nên soft-delete Product chỉ vì cascade ALL.
- Xóa membership có thể chỉ xóa join row.
- Product soft delete cần đi qua Product lifecycle policy.
- Existing Orders có thể vẫn cần hiển thị Product snapshot hoặc reference.
- Filter có thể ẩn Product khỏi query mới nhưng historical Order vẫn cần đọc được.

Soft delete không làm cascade semantics an toàn hơn. Một cascade REMOVE tới shared target có thể đặt deleted marker cho Product và làm nó biến mất khỏi toàn bộ consumers.

## 24. Envers và audit history khi cascade REMOVE

Nếu REMOVE cascade tới shared target, Envers có thể ghi delete revision cho target nếu target audited và thao tác đi qua Hibernate lifecycle. Đây là hậu quả audit rất lớn:
- Product có thể có delete revision không đúng nghiệp vụ.
- Role có thể biến mất khỏi lịch sử users khác.
- Collection memberships có thể bị audit thay đổi.
- Historical reads có thể thể hiện target bị xóa ngoài ý muốn.

DB `ON DELETE CASCADE` hoặc native SQL không nhất thiết tạo cùng Envers per-entity audit events.

Test Envers nếu ứng dụng dùng auditing:
1. Tạo hai parents cùng tham chiếu target.
2. Commit revision.
3. Xóa một parent.
4. Kiểm tra target không có delete revision nếu policy giữ target.
5. Kiểm tra membership/association history.
6. Đọc historical graph trước và sau.

## 25. Cascade và optimistic locking

Xóa parent với cascade REMOVE có thể chạm nhiều child rows/entities. Khi có version columns:
- Hibernate có thể kiểm tra version trên từng entity được remove.
- Concurrent updates có thể tạo optimistic-lock failure.
- Delete order/lock order có thể dẫn tới deadlock.
- Một cascade graph lớn làm transaction dài.

Không dùng ALL trên shared graph để thay thế explicit delete workflow. Với dependent children, hãy xác định transaction size, lock behavior và conflict handling.

## 26. Database constraints bảo vệ shared references

Ví dụ Product được OrderLine tham chiếu:

```sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_order_lines_product
FOREIGN KEY (product_id)
REFERENCES products(id)
ON DELETE RESTRICT;
```

Constraint RESTRICT/NO ACTION ngăn xóa Product khi còn references (chi tiết timing phụ thuộc DBMS/constraint). Đây là lớp bảo vệ cuối khi có:
- Một service khác.
- Native SQL.
- Script vận hành.
- Concurrent transactions.
- Mapping cascade sai.

Đừng bỏ FK chỉ để Cascade REMOVE chạy được. FK violation có thể là tín hiệu mapping đang cố xóa một shared target không nên bị xóa.

### 26.1. Unique và index cho join table

Join table nên có PK/UNIQUE `(student_id, course_id)` để ngăn duplicate membership, cùng indexes phù hợp cho lookup theo hai phía. Khi xóa Student hoặc Course, index giúp DB tìm association rows hiệu quả.

## 27. `CascadeType.REMOVE` không thay thế business delete policy

Một thao tác delete có thể phải:
- Kiểm tra trạng thái.
- Kiểm tra references còn hoạt động.
- Ghi audit.
- Phát domain event.
- Xóa association records.
- Anonymize PII.
- Giữ invoice/order snapshots.
- Đảm bảo retention/legal hold.

Cascade REMOVE chỉ lan truyền lifecycle operation; nó không thực hiện các quy tắc nghiệp vụ đó.

Hãy dùng service/use case rõ ràng cho xóa entity dùng chung. Có thể từ chối delete nếu target còn usage, hoặc soft-delete theo policy; không để một association annotation quyết định thay nghiệp vụ.

## 28. Mapping an toàn cho một số quan hệ phổ biến

### Order -> OrderLine: private dependent child

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

`REMOVE` tường minh có thể phù hợp nếu xóa Order phải xóa OrderLine; `ALL` đôi khi phù hợp nếu mọi lifecycle operation đều có cùng boundary. Nhưng hãy xem xét merge/detach/refresh semantics và test đầy đủ.

### OrderLine -> Product: shared catalog reference

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

Không cascade REMOVE/ALL.

### Student -> Course: shared many-to-many

```java
@ManyToMany
@JoinTable(name = "student_courses", ...)
private Set<Course> courses = new HashSet<>();
```

Không cascade REMOVE/ALL; chỉ quản lý membership rows.

### User -> Role: shared security reference

```java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(name = "user_roles", ...)
private Set<Role> roles = new HashSet<>();
```

Không cascade REMOVE tới Role. Việc xóa User không được xóa quyền dùng chung. Việc xóa Role là use case quản trị riêng có kiểm tra mọi user assignments.

### Article -> Category: shared taxonomy reference

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "category_id")
private Category category;
```

Xóa Article không xóa Category. Category lifecycle do taxonomy/catalog quản lý.

## 29. Khi nào `CascadeType.ALL` có thể hợp lý?

ALL có thể phù hợp khi:
- Target thực sự là dependent/private child.
- Target không được chia sẻ với aggregate khác.
- Mọi cascade operations đều đúng với domain lifecycle.
- Remove parent phải remove child.
- Merge/refresh/detach propagation cũng có ý nghĩa.
- Reparenting không được phép hoặc được quản lý rõ.
- Database constraints và tests phản ánh cùng ownership.

Ví dụ một `OrderAddress` chỉ thuộc một Order và không thể tồn tại độc lập có thể phù hợp cascade ALL, tùy mapping và lifecycle. Tuy nhiên, không bắt buộc phải dùng ALL; khai báo subset tường minh thường dễ review hơn.

### 29.1. Dùng cascade subset theo ý định

Thay vì:

```java
cascade = CascadeType.ALL
```

có thể dùng:

```java
cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE
}
```

hoặc chỉ:

```java
cascade = CascadeType.PERSIST
```

nếu đó là các thao tác thực sự cần lan truyền. Không thêm REMOVE chỉ vì các thao tác khác cần cascade.

## 30. Test âm: xóa một parent không được xóa shared target

Đây là integration test quan trọng.

Scenario:
1. Tạo Product P.
2. Tạo Order A tham chiếu P.
3. Tạo Order B cũng tham chiếu P.
4. Commit.
5. Xóa Order A.
6. Commit.
7. Mở EntityManager mới.
8. Assert Product P còn tồn tại.
9. Assert Order B vẫn tham chiếu P.
10. Assert chỉ association của Order A bị xóa.

Test có thể dùng FK `ON DELETE RESTRICT` để bảo vệ thêm. Nếu mapping sai cascade REMOVE, test sẽ phát hiện lỗi FK hoặc Product bị xóa ngoài ý muốn.

## 31. Test ManyToMany: membership biến mất, target còn nguyên

```java
@Test
void deletingStudentDoesNotDeleteSharedCourses() {
    Long studentId;
    Long courseId;

    // Arrange: persist Student A, Student B và Course C.
    // Cả hai students cùng liên kết Course C.
    // Commit transaction.

    // Act: xóa Student A và commit.

    // Assert bằng EntityManager mới:
    // - Student A không tồn tại.
    // - Student B còn tồn tại.
    // - Course C còn tồn tại.
    // - Student B vẫn có Course C.
    // - Không còn join row của Student A.
}
```

Đây là pseudocode để thể hiện test contract; fixture phải tạo hai students cùng course và sử dụng transaction/context riêng. Không chỉ assert `studentA` đã bị xóa.

### 31.1. Test SQL join table trực tiếp khi cần

Có thể query:

```sql
SELECT student_id, course_id
FROM student_courses
WHERE course_id = :courseId;
```

Sau khi xóa Student A, kết quả phải còn membership của Student B. Điều này kiểm tra đúng association table, tránh việc L1 collection che lỗi.

## 32. Test phát hiện cascade REMOVE trên ManyToOne

Scenario:
1. Tạo Product P.
2. Tạo hai OrderLines cùng tham chiếu P.
3. Commit.
4. Xóa OrderLine 1.
5. Flush/commit.
6. Assert Product P còn.
7. Assert OrderLine 2 còn và FK vẫn là P.

Nếu `OrderLine.product` cascade REMOVE, test có thể:
- Nhận FK constraint violation khi xóa P.
- Hoặc xóa P nếu không còn references.
- Làm hỏng invariant của catalog.

Test nên chạy trên DBMS thật để constraint behavior được xác nhận.

## 33. Test PERSIST/MERGE không lan sang shared target

Ngoài delete tests, hãy kiểm tra:
- Tạo Order với Product đã tồn tại không cố persist duplicate Product.
- Merge detached Order không ghi đè Product name/price ngoài ý muốn.
- Product update phải qua use case quản lý Product.
- Invalid Product ID được từ chối theo policy.
- Cross-tenant Product ID không được gắn vào Order.

Có thể assert Product version/fields không thay đổi sau Order update. Nếu Product có `@Version`, kiểm tra version không tăng khi chỉ thay đổi Order.

## 34. Test orphanRemoval chỉ trên dependent child

Nếu Order sở hữu riêng OrderLine:
1. Tạo Order có hai lines.
2. Bỏ một line qua helper.
3. Flush/commit.
4. Assert line bị xóa.
5. Assert line còn lại tồn tại.
6. Assert Product được line tham chiếu vẫn tồn tại.

Điều này chứng minh orphanRemoval xóa child riêng mà không cascade xóa shared Product.

Không cấu hình orphanRemoval trên shared ManyToMany targets; membership removal nên xóa join row.

## 35. Test Envers và audit policy

Nếu Product/Role/Course được audit:
- Xóa parent không tạo delete revision cho shared target.
- Association membership có lịch sử đúng nếu mapping audited.
- Xóa target chỉ xảy ra qua target-owning service.
- Native DB cascade có behavior audit riêng.
- Historical snapshots vẫn đọc được theo policy.

Audit tests quan trọng vì cascade REMOVE sai có thể tạo ra dữ liệu lịch sử hợp lệ về mặt kỹ thuật nhưng sai về nghiệp vụ.

## 36. Xóa shared target có kiểm tra references

Nếu business cần xóa Product, đó phải là use case của Product:

```java
@Transactional
public void deleteProduct(Long productId) {
    Product product =
        entityManager.find(Product.class, productId);

    if (product == null) {
        return;
    }

    if (orderLineRepository.existsByProductId(productId)) {
        throw new ProductStillReferencedException(productId);
    }

    entityManager.remove(product);
}
```

Ví dụ này chỉ minh họa policy “không xóa khi còn OrderLine”. Ứng dụng có thể chọn:
- Soft delete.
- Retire/inactive.
- Chặn nếu còn references.
- Anonymize.
- Xóa vật lý sau retention.

Không để xóa Product là side effect của việc xóa OrderLine.

### 36.1. Pre-check phải được bảo vệ bởi database/concurrency

`existsByProductId()` rồi `remove()` có thể race với transaction khác tạo reference mới. FK vẫn là lớp bảo vệ cuối. Tùy DBMS và policy, có thể cần locking, transaction isolation hoặc state transition trước khi xóa.

Nếu Product đang được tham chiếu, DB FK `RESTRICT` giúp ngăn xóa vật lý ngay cả khi pre-check bị race.

## 37. Cascade và multi-tenant/security boundaries

Cascade ALL trên một reference có thể vượt qua ranh giới tenant nếu entity graph chứa target ID sai tenant và ORM cho phép gắn reference đó.

Thiết kế:
- Resolve shared target trong tenant/security scope.
- Composite FK nếu schema cần bảo đảm tenant consistency.
- Không nhận detached graph tùy ý từ client.
- Không cascade REMOVE qua shared references.
- Test cùng logical IDs ở nhiều tenants.
- Kiểm tra bulk/native paths và database row-level security nếu có.

Cascade không phải cơ chế authorization. Nó không kiểm tra caller có quyền xóa target hay không.

## 38. Kiểm tra mapping trong code review

Khi thấy `CascadeType.ALL` hoặc `CascadeType.REMOVE`, hỏi:
1. Entity đích có thể được tham chiếu từ nơi khác không?
2. Entity đích có thể tồn tại độc lập không?
3. Xóa source có thực sự yêu cầu xóa target không?
4. Target có được module/service khác quản lý không?
5. Association là `ManyToOne`, `ManyToMany`, `OneToMany` hay `OneToOne`?
6. Có `mappedBy` không?
7. `orphanRemoval` có phù hợp private ownership không?
8. Có FK/UNIQUE constraints bảo vệ không?
9. Envers/callback/cache có bị ảnh hưởng không?
10. Có integration test chứng minh target shared vẫn còn không?

Nếu không thể trả lời câu 3 bằng một quy tắc nghiệp vụ rõ ràng, không thêm REMOVE cascade.

## 39. Tìm cascade nguy hiểm trong repository

Có thể tìm nhanh:

```shell
rg -n -U "@ManyToOne[\s\S]{0,300}CascadeType\.(ALL|REMOVE)" src
rg -n -U "@ManyToMany[\s\S]{0,300}CascadeType\.(ALL|REMOVE)" src
rg -n "CascadeType\.ALL|CascadeType\.REMOVE" src
```

Regex nhiều dòng chỉ là gợi ý; annotations có thể được tách dòng hoặc đặt ở getter, XML mapping hoặc generated metadata.

Review từng match theo association lifecycle. Không tự động xóa mọi `ALL`: một số private dependent relationships có thể cần cascade remove. Phải phân loại shared target vs owned child.

## 40. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Xóa Order làm Product bị xóa | `ManyToOne` cascade REMOVE/ALL | Bỏ REMOVE cascade trên shared reference |
| Xóa Student gây FK violation ở Course | `ManyToMany` cascade REMOVE | Chỉ xóa membership rows |
| Xóa một user làm Role biến mất | `User.roles` cascade ALL | Quản lý Role độc lập |
| Tạo Order bị duplicate Product | Cascade PERSIST tới detached shared Product | Resolve target bằng managed reference |
| Update Order ghi đè tên Product | Cascade MERGE qua shared reference | Dùng command DTO và resolve Product |
| Xóa parent kéo theo graph lớn | ALL trên nhiều shared associations | Thiết kế cascade theo aggregate boundary |
| DB cascade xóa target ngoài dự kiến | FK `ON DELETE CASCADE` đặt sai phía | Rà DDL và FK direction |
| Collection bị xóa nhưng target còn? | Membership semantics bị hiểu nhầm | Kiểm tra join-table rows và target table |
| OrphanRemoval xóa entity dùng chung | Dùng orphanRemoval sai lifecycle | Chỉ dùng với private dependent child |
| Audit có delete revision sai | REMOVE cascade tới audited shared target | Sửa mapping và test Envers |
| Shared target bị stale trong cache | Native/DB cascade bypass ORM cache | Invalidate/evict cache có kiểm soát |
| Cascade trên ManyToMany không portable | REMOVE không phù hợp association type | Tuân thủ Jakarta Persistence contract |
| `CascadeType.ALL` được thêm để sửa save lỗi | Nhầm cascade với ownership/reference resolution | Chọn PERSIST/MERGE subset hoặc persist riêng |
| Xóa Product đôi lúc thành công, đôi lúc lỗi FK | Có/không còn references | Dùng explicit delete policy và FK |
| Pre-check không có references nhưng DELETE fail | Concurrent transaction thêm reference | DB constraint, locking/isolation và retry policy |
| Xóa Student mất lịch sử Enrollment | Enrollment lifecycle bị gắn sai | Entity trung gian và retention policy |
| `merge()` làm detached target thay đổi | Cascade MERGE quá rộng | Resolve managed target, cập nhật qua owner service |
| Soft delete làm shared target biến mất | REMOVE cascade kích hoạt soft-delete marker | Không cascade remove tới shared target |
| Rollback sau cascade để lại side effects | Listener gửi message/email trước commit | After-commit/outbox phù hợp |
| Xóa parent cần load hàng nghìn targets | Mapping cascade REMOVE không đúng | Xóa join rows qua query/DB policy, giữ target |
| Test chỉ assert parent biến mất | Không kiểm tra target còn hay mất | Assert shared target và references sau reload |

## 41. Quy trình chọn cascade cho association

**Bước 1 — Xác định lifecycle.** Entity đích là private child hay shared reference?

**Bước 2 — Xác định thao tác cần lan truyền.** Có thật sự cần PERSIST, MERGE, REMOVE, REFRESH hoặc DETACH không?

**Bước 3 — Không chọn ALL theo thói quen.** Bật đúng subset có ý nghĩa.

**Bước 4 — Kiểm tra loại association.** REMOVE cascade chỉ nên dùng portable trên OneToOne/OneToMany theo Jakarta Persistence.

**Bước 5 — Xem orphanRemoval riêng.** Chỉ bật khi child có private ownership và bị loại khỏi quan hệ đồng nghĩa remove.

**Bước 6 — Kiểm tra shared consumers.** Tạo fixture có ít nhất hai parents tham chiếu cùng target.

**Bước 7 — Kiểm tra DDL.** FK/unique/join-table constraints phải bảo vệ invariant.

**Bước 8 — Test remove.** Xóa một parent và xác nhận target shared vẫn còn.

**Bước 9 — Test persist/merge.** Xác nhận thao tác parent không tạo/ghi đè target ngoài ý muốn.

**Bước 10 — Test cache/audit/transaction.** Kiểm tra Envers, callbacks, soft delete, rollback và concurrency nếu ứng dụng dùng.

**Bước 11 — Review bulk/native paths.** DB-level cascade có thể bỏ qua ORM lifecycle.

**Bước 12 — Ghi rõ policy.** Tài liệu hóa ai sở hữu target và ai có quyền xóa nó.

## 42. Bài tập tình huống

### Bài 1 — `CascadeType.ALL`

`OrderLine.product` là `ManyToOne` tới Product catalog. Có nên dùng ALL?

**Đáp án:** Không theo mặc định. Product được dùng chung; REMOVE/MERGE/PERSIST cascade có thể lan lifecycle ngoài ý muốn.

### Bài 2 — Xóa Student

Student có ManyToMany tới Course. Xóa Student có nên xóa Course?

**Đáp án:** Không. Xóa membership/join rows; giữ Course.

### Bài 3 — FK violation

Xóa OrderLine làm Hibernate cố DELETE Product nhưng DB báo FK violation. Nguyên nhân có thể?

**Đáp án:** Cascade REMOVE/ALL trên `OrderLine.product`; Product còn được tham chiếu nơi khác.

### Bài 4 — ALL và PERSIST

Cần cascade PERSIST tới private child. Có bắt buộc dùng ALL không?

**Đáp án:** Không. Khai báo riêng `CascadeType.PERSIST` nếu đó là thao tác duy nhất cần lan truyền.

### Bài 5 — Detached Product

Request gửi Product object với ID đã tồn tại. Cascade PERSIST có thể gây gì?

**Đáp án:** Provider có thể coi object detached như entity cần persist, dẫn tới entity-exists/duplicate-key error. Resolve managed reference theo ID.

### Bài 6 — Cascade MERGE

Detached Order chứa Product name cũ. Cascade MERGE có thể làm gì?

**Đáp án:** Merge state cũ vào shared Product và ghi đè catalog state ngoài ý muốn.

### Bài 7 — `orphanRemoval`

Bỏ Course khỏi Student ManyToMany có nên xóa Course như orphan không?

**Đáp án:** Không. Xóa membership row, Course có lifecycle độc lập.

### Bài 8 — Private child

Order sở hữu riêng OrderLine. Khi xóa Order, có thể cascade REMOVE không?

**Đáp án:** Có thể phù hợp nếu child chỉ thuộc Order và lifecycle được xác định rõ.

### Bài 9 — JPA portability

REMOVE cascade trên ManyToMany có portable theo Jakarta Persistence không?

**Đáp án:** Không. Portable applications chỉ nên dùng cascade REMOVE cho OneToOne/OneToMany.

### Bài 10 — Database cascade

DB `ON DELETE CASCADE` trên `student_courses.student_id` xóa gì khi xóa Student?

**Đáp án:** Join-table rows của Student; không tự xóa Course nếu FK hướng từ join table tới Course được cấu hình bình thường.

### Bài 11 — Product vẫn còn

Sau khi xóa Order A, Product P còn được Order B tham chiếu. Assertion quan trọng?

**Đáp án:** Product P vẫn tồn tại và Order B vẫn tham chiếu đúng P sau reload.

### Bài 12 — Cascade ALL trên User.roles

Xóa User làm Role bị xóa. Cách sửa?

**Đáp án:** Bỏ cascade REMOVE/ALL trên shared Role; chỉ xóa user-role membership.

### Bài 13 — Entity trung gian

Enrollment có `enrolledAt` và `status`. Có nên giữ ManyToMany thuần?

**Đáp án:** Entity trung gian Enrollment biểu diễn lifecycle/attributes của membership rõ hơn; Course vẫn là shared reference.

### Bài 14 — Soft delete

Cascade REMOVE tới Product có `@SoftDelete` có thể gây gì?

**Đáp án:** Product bị đánh dấu deleted và biến mất khỏi queries dù nhiều orders vẫn cần tham chiếu.

### Bài 15 — Envers

Cascade REMOVE sai trên Product audited có thể tạo audit event nào?

**Đáp án:** Delete revision cho Product không đúng nghiệp vụ và làm historical graph sai.

### Bài 16 — `getReference`

Dùng `getReference(Product.class, id)` có kiểm tra Product tồn tại ngay không?

**Đáp án:** Không nhất thiết; proxy có thể chỉ phát hiện missing row khi được khởi tạo. Thực hiện lookup/validation nếu cần.

### Bài 17 — Pre-check race

Service kiểm tra Product không có references rồi xóa; transaction khác đồng thời tạo OrderLine. Bảo vệ cuối?

**Đáp án:** FK constraint, locking/isolation hoặc workflow retire/disable có kiểm soát.

### Bài 18 — Merge object trả về

`managed = em.merge(detached)`; nên tiếp tục thao tác object nào?

**Đáp án:** Managed instance được trả về. Object đầu vào vẫn detached.

### Bài 19 — DB cascade và callbacks

Native SQL xóa parent kích hoạt DB ON DELETE CASCADE. `@PreRemove` của children có chạy không?

**Đáp án:** Không. Database không gọi Java entity lifecycle callbacks.

### Bài 20 — Kiểm thử shared target

Một test xóa parent chỉ assert parent không tồn tại. Còn thiếu gì?

**Đáp án:** Assert shared target vẫn tồn tại, các parents khác vẫn tham chiếu target và join rows của parent đã xóa được dọn đúng.

## 43. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): cascade semantics, association mappings, orphan removal và portable use of REMOVE.
- [Jakarta Persistence API — `CascadeType`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/cascadetype): các cascade operations và ý nghĩa `ALL`.
- [Jakarta Persistence API — `ManyToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): many-to-one association và cascade configuration.
- [Jakarta Persistence API — `ManyToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytomany): many-to-many ownership và join-table mapping.
- [Jakarta Persistence API — `OneToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetomany): collection relationships, cascade và orphan removal.
- [Hibernate ORM User Guide — Cascading](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc-cascade): Hibernate lifecycle cascade and orphan removal.
- [Hibernate ORM User Guide — Associations](https://docs.hibernate.org/orm/7.2/userguide/html_single/#associations): owning/inverse sides, many-to-one, one-to-many and many-to-many.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc): persist, merge, remove và managed state.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): repository save semantics and persist/merge behavior.
- [PostgreSQL Documentation — Foreign Key Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): FK, ON DELETE actions and referential integrity.

**Ghi chú phiên bản:** Cascade semantics cơ bản thuộc Jakarta Persistence, nhưng SQL ordering, exception timing, soft-delete integration, cache behavior và Envers effects phụ thuộc Hibernate version, mapping và DBMS. Đặc biệt, không dựa vào behavior của một provider cho REMOVE cascade trên association types ngoài phạm vi portable. Hãy chạy integration tests với schema, constraints và version triển khai thực tế.

## Kết luận

`CascadeType.ALL` không phải lựa chọn mặc định cho mọi association. Nó bao gồm cả REMOVE, MERGE, PERSIST, REFRESH và DETACH; vì vậy, trên quan hệ tới `Product`, `Course`, `Role`, `Customer` hoặc `Category` dùng chung, nó có thể trao cho một aggregate quyền thay đổi hoặc xóa dữ liệu do aggregate khác sở hữu. Với bidirectional `ManyToMany`, xóa một parent thường chỉ cần dọn membership rows trong join table và giữ target entities.

Hãy xác định dependent child và shared reference theo vòng đời nghiệp vụ, rồi khai báo cascade subset tường minh. `REMOVE` có thể phù hợp cho private `OneToOne`/`OneToMany` children; `orphanRemoval` cũng chỉ nên dùng khi child có private ownership. FK constraints và DB `ON DELETE` là cơ chế riêng, không thay thế ORM lifecycle hay Envers callbacks.

Một integration test có ít nhất hai parents cùng tham chiếu một target là cách đơn giản để bắt lỗi nguy hiểm: xóa một parent, commit, mở Persistence Context mới và chứng minh target vẫn tồn tại, parent còn lại vẫn liên kết đúng, còn association của parent đã xóa được dọn sạch.
