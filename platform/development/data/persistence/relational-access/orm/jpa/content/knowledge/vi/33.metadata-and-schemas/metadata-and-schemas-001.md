# Khám phá mô hình ánh xạ bằng Metamodel trong JPA

Trong ứng dụng dùng **Jakarta Persistence (JPA)**, các annotation như `@Entity`, `@Id`, `@OneToMany` hay `@Embedded` mô tả cách Java domain model được ánh xạ sang dữ liệu quan hệ. Khi chương trình khởi động, persistence provider đọc annotation/XML mapping, xử lý kế thừa và các quy tắc cấu hình để xây dựng **mô hình ánh xạ đã được nhận diện**. JPA cho phép ứng dụng truy cập mô hình ấy qua **Metamodel API**.

Ví dụ, thay vì tự đọc annotation bằng Java reflection để đoán một class có phải entity hay thuộc tính `department` có phải quan hệ hay không, ta có thể hỏi trực tiếp:

~~~java
Metamodel model = emf.getMetamodel();
EntityType<Employee> employeeType =
    model.entity(Employee.class);

for (Attribute<? super Employee, ?> attribute
        : employeeType.getAttributes()) {
    System.out.println(
        attribute.getName() + " : "
        + attribute.getPersistentAttributeType()
    );
}
~~~

Một kết quả minh họa:

~~~text
id           : BASIC
version      : BASIC
createdAt    : BASIC
employeeCode : BASIC
department   : MANY_TO_ONE
address      : EMBEDDED
skills       : ELEMENT_COLLECTION
labels       : ELEMENT_COLLECTION
~~~

**Metamodel không phải cơ chế truy vấn dữ liệu của các bản ghi Employee.** Nó mô tả **cấu trúc ánh xạ**: những entity nào được quản lý, chúng có attributes nào, kiểu Java của attributes, loại quan hệ, thông tin khóa định danh và version, các mapped superclasses và embeddables.

JPA có hai cách dùng Metamodel cần phân biệt ngay:

1. **Runtime metamodel (dynamic metamodel):** dùng `EntityManagerFactory.getMetamodel()` hoặc `EntityManager.getMetamodel()` để **khám phá mapping lúc chạy**.
2. **Static canonical metamodel:** các lớp như `Employee_` được tạo bởi annotation processor để **xây Criteria API truy vấn có kiểm tra kiểu tại thời điểm biên dịch**.

~~~text
                Entity source / XML mapping
                            |
             +--------------+--------------+
             |                             |
             v                             v
    JPA provider bootstrap         Annotation processor
             |                             |
             v                             v
     Runtime Metamodel             Static Employee_, Department_
             |                             |
             v                             v
     Khám phá entity/attrs          Criteria API typed paths
     Kiểm tra metadata              Compile-time field checks
~~~

Hai cách này **bổ sung** cho nhau, nhưng không giống việc truy vấn `information_schema` của database. Một bảng SQL, index vật lý hoặc trigger có thể tồn tại trong DB mà không có đối tượng tương ứng trong JPA Metamodel.

## 1. Khi nào cần khám phá mô hình ánh xạ?

Những tình huống thực tế:

- Viết công cụ nội bộ liệt kê các entity được đăng ký trong persistence unit.
- Sinh tài liệu kỹ thuật về **entity → attributes → relationships** từ mapping đã được provider nhận diện.
- Kiểm tra lúc khởi động rằng một entity có `@Version`, ID hoặc các attributes cần thiết.
- Tạo bộ lọc/sắp xếp động dựa trên những thuộc tính đã được ánh xạ, có danh sách cho phép.
- Viết Criteria queries có tính an toàn kiểu hơn thay vì dùng strings cho mọi property.
- Đánh giá một entity dùng khóa đơn, embedded ID hay nhiều ID attributes.
- Xem entity có collection, map, embedded value object hay association.
- Kiểm tra một persistent property là inherited hay được khai báo trực tiếp ở entity.

Những bài toán **không** nên kỳ vọng JPA Metamodel tự giải quyết:

- So sánh chính xác các indexes, constraints, triggers và physical columns trong database.
- Trả lời data row đang có giá trị gì hoặc bao nhiêu bản ghi.
- Bảo đảm database schema đã được migration lên version mới.
- Tự chứng minh một foreign key thực sự tồn tại ở DB.
- Xác định user hiện hành có quyền xem entity nào.
- Biết SQL dialect cuối cùng provider sẽ dùng cho mỗi query.

Metamodel là **bản mô tả mapping logic của JPA**, không phải sơ đồ vật lý đầy đủ của hệ quản trị cơ sở dữ liệu.

## 2. Định vị API và namespace

Những kiểu chính thuộc package:

~~~java
import jakarta.persistence.metamodel.Metamodel;
import jakarta.persistence.metamodel.ManagedType;
import jakarta.persistence.metamodel.EntityType;
import jakarta.persistence.metamodel.EmbeddableType;
import jakarta.persistence.metamodel.MappedSuperclassType;
import jakarta.persistence.metamodel.Attribute;
import jakarta.persistence.metamodel.SingularAttribute;
import jakarta.persistence.metamodel.PluralAttribute;
import jakarta.persistence.metamodel.CollectionAttribute;
import jakarta.persistence.metamodel.ListAttribute;
import jakarta.persistence.metamodel.SetAttribute;
import jakarta.persistence.metamodel.MapAttribute;
import jakarta.persistence.metamodel.IdentifiableType;
import jakarta.persistence.metamodel.Type;
~~~

Các kiểu Persistence:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
~~~

Ví dụ trong bài dùng **Jakarta Persistence 3.x**. Với dự án JPA 2.x/Java EE cũ, nhiều API tương ứng nằm trong `javax.persistence.metamodel.*`. Không trộn `javax` và `jakarta` dependencies nếu provider chỉ hỗ trợ một thế hệ.

## 3. Bắt đầu từ EntityManagerFactory

Sau khi persistence unit đã được bootstrap:

~~~java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("shopPU");

try {
    Metamodel metamodel = emf.getMetamodel();

    System.out.println(
        "Số entity đã đăng ký: "
        + metamodel.getEntities().size()
    );
} finally {
    emf.close();
}
~~~

### Ý nghĩa

`EntityManagerFactory` giữ cấu hình mapping của **một persistence unit**. Vì vậy `getMetamodel()` trả về metadata của những managed types mà provider đã nhận diện cho persistence unit đó.

Không có nghĩa toàn bộ classes nằm trên Java classpath đều xuất hiện trong `getEntities()`.

### Có thể lấy từ EntityManager?

Có:

~~~java
EntityManager em = emf.createEntityManager();
try {
    Metamodel model = em.getMetamodel();
} finally {
    em.close();
}
~~~

Tuy nhiên, nếu chỉ cần đọc metadata của persistence unit, thường không cần tạo riêng một EntityManager. Dùng `emf.getMetamodel()` trực tiếp giúp phân biệt metadata khỏi persistence context và transaction.

### Có cần transaction để gọi getMetamodel()?

Không cần mở một transaction chỉ để duyệt metadata. Dữ liệu mapping đã được thiết lập khi provider bootstrap. Việc xây EntityManagerFactory có thể liên quan cấu hình database/dialect, nhưng thao tác duyệt metamodel không tương đương SELECT một bảng nghiệp vụ.

## 4. Mô hình đối tượng ví dụ xuyên suốt

Ta xây mô hình nhân sự đơn giản:

~~~text
AuditedEntity (@MappedSuperclass)
    |
    +-- Department (@Entity)
    |      id, version, createdAt
    |      code, name
    |      employees: List<Employee>       [one-to-many]
    |
    +-- Employee (@Entity)
           id, version, createdAt
           employeeCode, fullName
           department: Department          [many-to-one]
           address: Address                [embedded]
           skills: Set<String>             [element collection]
           labels: Map<String, String>     [element collection]

Address (@Embeddable)
    street, city, postalCode
~~~

Các đặc điểm giúp minh họa đầy đủ các loại metadata:

- `AuditedEntity` là mapped superclass, không phải entity/table độc lập bắt buộc.
- `Department` và `Employee` là entity types.
- `Address` là embeddable type.
- `department` và `employees` là hai phía của quan hệ.
- `skills` là collection chứa basic values.
- `labels` là map có key/value, phục vụ khám phá `MapAttribute`.
- `id`/`version` được kế thừa từ mapped superclass.

## 5. Mapped superclass AuditedEntity

~~~java
package com.example.hr.domain;

import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;
import java.time.Instant;

@MappedSuperclass
public abstract class AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AuditedEntity() {
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    protected void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

### Vì sao là @MappedSuperclass?

Những mapping `id`, `version` và `createdAt` được kế thừa bởi các entity con. Trong mô hình JPA này:

- Không gọi `em.persist(new AuditedEntity(...))` vì superclass này không phải entity có thể persist độc lập.
- Metamodel có thể biểu diễn AuditedEntity bằng `MappedSuperclassType`.
- Những inherited attributes của nó xuất hiện khi ta dùng `Employee.getAttributes()`.

### Cảnh báo về createdAt

Đây là ví dụ mapping; trong sản phẩm thật cần gán `createdAt` hợp lệ qua factory/domain callback/timestamp strategy. Đừng dùng `@Column(nullable=false)` và nghĩ provider tự biết thời điểm tạo nếu không có cấu hình tương ứng.

## 6. Embeddable Address

~~~java
package com.example.hr.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(name = "street")
    private String street;

    @Column(name = "city")
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected Address() {
    }

    public Address(
            String street,
            String city,
            String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

`Address` không có `@Id` và không phải một entity có identity riêng. Khi được `@Embedded` vào Employee, các properties của nó trở thành một phần persistent state của Employee theo mapping.

Trong Metamodel:

~~~text
Type: Address
PersistenceType: EMBEDDABLE
Attributes: street, city, postalCode
~~~

Việc các field này nằm ở cột nào trong bảng employee phụ thuộc mapping overrides/naming strategy và không thể xác định đầy đủ chỉ từ `EmbeddableType.getAttributes()`.

## 7. Entity Department

~~~java
package com.example.hr.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department extends AuditedEntity {

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String name;

    @OneToMany(
        mappedBy = "department",
        fetch = FetchType.LAZY)
    private List<Employee> employees =
        new ArrayList<>();

    protected Department() {
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}
~~~

Đặc điểm của `Department`:

- Kế thừa `id`/`version`/`createdAt`.
- `code`/`name` là basic singular attributes.
- `employees` là collection-valued association với persistent attribute type `ONE_TO_MANY`.

`getAttributes()` sẽ bao gồm cả inherited attributes; `getDeclaredAttributes()` sẽ chỉ trả các properties được khai báo trực tiếp ở Department.

## 8. Entity Employee

~~~java
package com.example.hr.domain;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

@Entity
@Table(name = "employees")
public class Employee extends AuditedEntity {

    @Column(name = "employee_code",
            nullable = false, unique = true)
    private String employeeCode;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @Embedded
    private Address address;

    @ElementCollection
    @CollectionTable(
        name = "employee_skills",
        joinColumns = @JoinColumn(name = "employee_id"))
    @Column(name = "skill")
    private Set<String> skills = new HashSet<>();

    @ElementCollection
    @CollectionTable(
        name = "employee_labels",
        joinColumns = @JoinColumn(name = "employee_id"))
    @MapKeyColumn(name = "label_key")
    @Column(name = "label_value")
    private Map<String, String> labels =
        new HashMap<>();

    @Transient
    private String displayText;

    protected Employee() {
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public Department getDepartment() {
        return department;
    }

    public Address getAddress() {
        return address;
    }

    public Set<String> getSkills() {
        return skills;
    }

    public Map<String, String> getLabels() {
        return labels;
    }
}
~~~

Các attributes đáng chú ý:

| Thuộc tính | Java type | JPA mapping | Loại metamodel |
| --- | --- | --- | --- |
| `employeeCode` | String | Basic column | Singular/BASIC |
| `fullName` | String | Basic column | Singular/BASIC |
| `department` | Department | Many-to-one | Singular/MANY_TO_ONE |
| `address` | Address | Embedded | Singular/EMBEDDED |
| `skills` | Set<String> | Element collection | SetAttribute/ELEMENT_COLLECTION |
| `labels` | Map<String,String> | Element collection | MapAttribute/ELEMENT_COLLECTION |
| `displayText` | String | `@Transient` | **Không thuộc persistent metamodel** |
| `id` | Long | `@Id` ở superclass | Inherited Singular/BASIC |
| `version` | Long | `@Version` ở superclass | Inherited Singular/BASIC |

Một điểm thường gây nhầm: **`@Transient` không phải một kiểu persistent attribute**. Tên `displayText` không xuất hiện chỉ vì nó là Java field của entity.

## 9. Metamodel.getEntities(): liệt kê những entity nào?

~~~java
Metamodel model = emf.getMetamodel();

for (EntityType<?> entity : model.getEntities()) {
    System.out.printf(
        "Entity name=%s, Java type=%s%n",
        entity.getName(),
        entity.getJavaType().getName()
    );
}
~~~

Ví dụ output:

~~~text
Entity name=Department, Java type=com.example.hr.domain.Department
Entity name=Employee, Java type=com.example.hr.domain.Employee
~~~

### Entity name khác Java class simple name khi nào?

Có thể khai báo:

~~~java
@Entity(name = "StaffMember")
public class Employee {
    // ...
}
~~~

Khi đó:

~~~text
EntityType.getName() -> "StaffMember"
EntityType.getJavaType().getName()
  -> "com.example.hr.domain.Employee"
~~~

Entity name là tên logic sử dụng trong JPQL, **không nhất thiết trùng tên bảng SQL**.

### Tại sao không nên dùng getName() để suy bảng?

Với:

~~~java
@Entity(name = "StaffMember")
@Table(name = "employees")
class Employee { ... }
~~~

JPQL dùng `StaffMember` nhưng bảng vật lý có thể là `employees`. Naming strategies, schemas và overrides có thể làm tên SQL khác nữa.

## 10. Metamodel.getManagedTypes(): rộng hơn Entities

~~~java
Metamodel model = emf.getMetamodel();

for (ManagedType<?> type : model.getManagedTypes()) {
    System.out.printf(
        "%s -> %s%n",
        type.getJavaType().getSimpleName(),
        type.getPersistenceType()
    );
}
~~~

Ví dụ:

~~~text
AuditedEntity -> MAPPED_SUPERCLASS
Department    -> ENTITY
Employee      -> ENTITY
Address       -> EMBEDDABLE
~~~

### Phân biệt ba nhóm

| Loại | API | Đặc điểm |
| --- | --- | --- |
| Entity | `EntityType<X>` | Có JPA entity identity và lifecycle riêng |
| Embeddable | `EmbeddableType<X>` | Value object nằm trong mapping khác |
| Mapped superclass | `MappedSuperclassType<X>` | Cung cấp mapping kế thừa, không là entity độc lập |

`getEntities()` chỉ liệt kê entity types; `getManagedTypes()` có phạm vi rộng hơn.

### Một basic Java type có xuất hiện ở getManagedTypes không?

Không đơn giản là có. `String`, `Long`, `BigDecimal` có thể là basic attribute types, nhưng không trở thành JPA managed type chỉ vì chúng xuất hiện trong attributes của entity.

## 11. getEmbeddables() và embeddable(Class)

~~~java
Set<EmbeddableType<?>> embeddedTypes =
    model.getEmbeddables();

for (EmbeddableType<?> type : embeddedTypes) {
    System.out.println(type.getJavaType().getName());
}
~~~

Truy cập cụ thể:

~~~java
EmbeddableType<Address> addressType =
    model.embeddable(Address.class);
~~~

Duyệt fields:

~~~java
addressType.getAttributes().forEach(attr ->
    System.out.println(
        attr.getName()
        + " -> " + attr.getJavaType().getSimpleName()
    )
);
~~~

Kết quả:

~~~text
street -> String
city -> String
postalCode -> String
~~~

### Embedded có ID không?

Một `@Embeddable` thông thường không tự có entity ID. Tuy nhiên, nó có thể là **kiểu giá trị của `@EmbeddedId`** trong một entity khác. Khi đó identity thuộc về entity chủ, không biến embeddable thành một entity độc lập.

## 12. Truy cập một ManagedType theo Java class

~~~java
ManagedType<Employee> managed =
    model.managedType(Employee.class);
~~~

`managedType(Class)` cho phép lấy metadata khi class là managed type thuộc persistence unit.

Nếu cần chắc đây là một entity:

~~~java
EntityType<Employee> employeeType =
    model.entity(Employee.class);
~~~

Nếu cần chắc đây là embeddable:

~~~java
EmbeddableType<Address> addressType =
    model.embeddable(Address.class);
~~~

### Điều gì xảy ra khi class không thuộc persistence unit?

Những phương thức lấy type cụ thể có thể ném `IllegalArgumentException` nếu class không phải loại managed type được yêu cầu.

Ví dụ:

~~~java
model.entity(String.class);
~~~

không hợp lệ. Một Java class bất kỳ không tự có entity metadata.

### Không dùng try/catch để dò tất cả classes của JVM

Thay vì quét classpath rồi gọi `entity(clazz)` với hàng nghìn classes, hãy duyệt `getEntities()`/`getManagedTypes()`. Đây là tập metadata đã được JPA provider đăng ký.

## 13. Type.getPersistenceType()

Mỗi `Type<?>` trong JPA metamodel có:

~~~java
Type.PersistenceType persistenceType =
    type.getPersistenceType();
~~~

Các nhóm thường gặp:

~~~java
Type.PersistenceType.ENTITY
Type.PersistenceType.EMBEDDABLE
Type.PersistenceType.MAPPED_SUPERCLASS
Type.PersistenceType.BASIC
~~~

### BASIC được thấy ở đâu?

Một attribute như `employeeCode: String` có:

~~~java
SingularAttribute<Employee, String> code =
    employeeType.getSingularAttribute(
        "employeeCode", String.class);

Type<String> codeType = code.getType();
System.out.println(
    codeType.getPersistenceType()
); // BASIC
~~~

Không nên nhầm `Type.PersistenceType.BASIC` với `Attribute.PersistentAttributeType.BASIC`: một enum mô tả **loại persistence type của value**, một enum mô tả **kiểu mapping của attribute**.

## 14. ManagedType.getAttributes()

Ví dụ:

~~~java
EntityType<Employee> employee =
    model.entity(Employee.class);

Set<Attribute<? super Employee, ?>> attrs =
    employee.getAttributes();

for (Attribute<? super Employee, ?> attr : attrs) {
    System.out.println(attr.getName());
}
~~~

`getAttributes()` bao gồm những persistent attributes của managed type, **kể cả inherited attributes** theo JPA mapping.

Vì Employee kế thừa AuditedEntity:

~~~text
id
version
createdAt
employeeCode
fullName
department
address
skills
labels
~~~

Thứ tự duyệt `Set` **không phải business contract**. Nếu muốn output ổn định cho tài liệu/test snapshots, sắp xếp theo tên:

~~~java
employee.getAttributes().stream()
    .sorted(Comparator.comparing(Attribute::getName))
    .forEach(attr ->
        System.out.println(attr.getName())
    );
~~~

### Những fields không xuất hiện

`static` fields, `@Transient` properties và những Java members không được map là persistent attributes sẽ không xuất hiện như các JPA persistent attributes.

## 15. getDeclaredAttributes(): chỉ attributes được khai báo tại type

~~~java
Set<Attribute<Employee, ?>> declared =
    employeeType.getDeclaredAttributes();
~~~

Khác biệt:

| API | Có thuộc tính kế thừa từ @MappedSuperclass? |
| --- | --- |
| `getAttributes()` | Có |
| `getDeclaredAttributes()` | Không, chỉ khai báo ở type đang xét |

Ví dụ:

~~~text
Employee.getAttributes():
  id, version, createdAt,
  employeeCode, fullName, department, address, skills, labels

Employee.getDeclaredAttributes():
  employeeCode, fullName, department, address, skills, labels
~~~

### Khi nào chọn getDeclaredAttributes?

- Sinh tài liệu phân lớp theo nguồn khai báo.
- Kiểm tra một entity subclass có thêm những mapping nào.
- Tránh in trùng các inherited attributes khi duyệt từng superclass/entity.

### Khi nào chọn getAttributes?

- Cần biết tất cả persistent properties được phép dùng trên Employee.
- Xây danh sách các thuộc tính Criteria path.
- Kiểm tra entity có một field ID/version dù nó nằm trong superclass.

## 16. getAttribute(name) và getDeclaredAttribute(name)

Lấy một attribute theo tên:

~~~java
Attribute<? super Employee, ?> id =
    employeeType.getAttribute("id");
~~~

Vì `id` được kế thừa, `getAttribute("id")` là lựa chọn phù hợp.

Nếu gọi:

~~~java
employeeType.getDeclaredAttribute("id");
~~~

thì Employee không khai báo trực tiếp field `id`. Theo semantics, lời gọi có thể ném `IllegalArgumentException`.

### Lỗi tên attribute

~~~java
employeeType.getAttribute("employee_code");
~~~

`employee_code` là tên **cột SQL**, không phải Java persistent attribute. Tên metamodel của field là `employeeCode`.

### Quy tắc

**Metamodel lookup dùng tên attribute Java/mapping, không phải tên cột vật lý.**

## 17. Attribute.getPersistentAttributeType()

`Attribute` có phương thức:

~~~java
Attribute.PersistentAttributeType kind =
    attribute.getPersistentAttributeType();
~~~

Các loại tiêu biểu:

| Giá trị | Mapping |
| --- | --- |
| `BASIC` | Basic value |
| `EMBEDDED` | Embedded value object |
| `MANY_TO_ONE` | Many-to-one association |
| `ONE_TO_ONE` | One-to-one association |
| `ONE_TO_MANY` | One-to-many association |
| `MANY_TO_MANY` | Many-to-many association |
| `ELEMENT_COLLECTION` | Collection/map của element values |

Ví dụ:

~~~java
for (Attribute<? super Employee, ?> attr
        : employeeType.getAttributes()) {
    System.out.println(
        attr.getName()
        + " -> "
        + attr.getPersistentAttributeType()
    );
}
~~~

`address` có type `EMBEDDED`, `department` có type `MANY_TO_ONE`, còn `skills`/`labels` có type `ELEMENT_COLLECTION`.

## 18. isAssociation() và isCollection()

Hai boolean methods:

~~~java
boolean association =
    attribute.isAssociation();

boolean collection =
    attribute.isCollection();
~~~

Giúp xây inspection tool không phụ thuộc tên enum:

~~~java
String flags =
    "association=" + attr.isAssociation()
    + ", collection=" + attr.isCollection();
~~~

### Hai tính chất độc lập

| Attribute | isAssociation | isCollection |
| --- | --- | --- |
| Basic String `employeeCode` | false | false |
| Embedded `address` | false | false |
| Many-to-one `department` | true | false |
| One-to-many `employees` | true | true |
| Element collection `skills` | false | true |

**Collection không nhất thiết là association.** `Set<String> skills` là element collection, không phải quan hệ đến một entity String.

### Khi nào hữu ích?

Một công cụ xây filter có thể từ chối attributes là collection để tránh tự tạo JOIN phức tạp:

~~~java
if (attr.isCollection()) {
    throw new IllegalArgumentException(
        "Không hỗ trợ filter trực tiếp collection");
}
~~~

## 19. getJavaType() và getJavaMember()

~~~java
Class<?> javaType = attr.getJavaType();
Member member = attr.getJavaMember();
~~~

`getJavaType()` cho biết kiểu Java khai báo của attribute:

~~~text
employeeCode -> String
department   -> Department
skills       -> Set
labels       -> Map
~~~

`getJavaMember()` có thể trỏ đến `java.lang.reflect.Field` hoặc `java.lang.reflect.Method` đại diện attribute mapping.

### Field access và property access

Với:

~~~java
@Id
private Long id;
~~~

thường dùng field access, `getJavaMember()` có thể là `Field`.

Với:

~~~java
@Id
public Long getId() { return id; }
~~~

thường dùng property access, `getJavaMember()` có thể là getter `Method`.

### Không dùng JavaMember để “giải mã SQL column” một cách tuyệt đối

Annotation trên field/getter chỉ là một nguồn mapping. XML overrides, `@AttributeOverride`, naming strategy và provider configuration có thể thay đổi physical columns. Metamodel chuẩn không cam kết cung cấp đầy đủ mọi tên cột/bảng thực tế.

### Không tự setAccessible và sửa object

Metamodel là công cụ **mô tả**, không phải lý do tự dùng reflection phá encapsulation và thay đổi managed entity fields ngoài domain methods.

## 20. SingularAttribute: kiểu tham số và value type

Một singular attribute có dạng:

~~~java
SingularAttribute<X, Y>
~~~

Trong đó:

- `X`: Java type khai báo/đại diện managed type.
- `Y`: Java type của giá trị attribute.

Ví dụ:

~~~java
SingularAttribute<Employee, String> code =
    employeeType.getSingularAttribute(
        "employeeCode",
        String.class
    );
~~~

Khi đó:

~~~java
Class<String> type = code.getJavaType();
boolean optional = code.isOptional();
boolean id = code.isId();
boolean version = code.isVersion();
~~~

### isId()/isVersion()

Các method trên giúp xác định một singular attribute có dùng để định danh entity hoặc quản lý version hay không.

Ví dụ:

~~~java
SingularAttribute<? super Employee, ?> idAttr =
    employeeType.getSingularAttribute("id");

System.out.println(idAttr.isId()); // true
~~~

### isOptional() có phải DB nullable không?

`SingularAttribute.isOptional()` mô tả optionality theo mapping JPA. Không nên biến trực tiếp thành kết luận “cột database hiện tại chắc chắn có NOT NULL constraint” khi schema có thể lệch, overrides/DDL constraints khác hoặc nhiều cột cùng tham gia một embedded/association mapping.

## 21. PluralAttribute: Collection, Set, List, Map

Một plural attribute có dạng khái quát:

~~~java
PluralAttribute<X, C, E>
~~~

Với:

- `X`: managed type chủ.
- `C`: collection Java type.
- `E`: element type.

Ví dụ:

~~~java
PluralAttribute<Employee, ?, ?> skills =
    employeeType.getPluralAttribute("skills");
~~~

Java generic wildcard chính xác trong code thực tùy type inference và API, nhưng ta có thể duyệt generic metadata:

~~~java
for (PluralAttribute<? super Employee, ?, ?> attr
        : employeeType.getPluralAttributes()) {

    System.out.println(
        attr.getName()
        + " collection=" + attr.getCollectionType()
        + " element=" + attr.getElementType()
            .getJavaType().getSimpleName()
    );
}
~~~

`getCollectionType()` trả một trong những dạng collection:

~~~java
PluralAttribute.CollectionType.COLLECTION
PluralAttribute.CollectionType.SET
PluralAttribute.CollectionType.LIST
PluralAttribute.CollectionType.MAP
~~~

### CollectionType khác PersistentAttributeType

`ELEMENT_COLLECTION` mô tả cách ánh xạ thuộc tính, còn `SET` mô tả hình dạng collection Java.

Ví dụ:

~~~text
skills
  PersistentAttributeType = ELEMENT_COLLECTION
  CollectionType = SET
  ElementType = BASIC/String
~~~

## 22. SetAttribute và ListAttribute

Truy cập type cụ thể:

~~~java
SetAttribute<Employee, String> skills =
    employeeType.getSet("skills", String.class);
~~~

Với Department:

~~~java
EntityType<Department> deptType =
    model.entity(Department.class);

ListAttribute<Department, Employee> employees =
    deptType.getList(
        "employees",
        Employee.class
    );
~~~

### Thông tin element type

~~~java
Type<Employee> elementType =
    employees.getElementType();

System.out.println(
    elementType.getPersistenceType()
); // ENTITY
~~~

Với `skills`:

~~~java
System.out.println(
    skills.getElementType().getPersistenceType()
); // BASIC
~~~

### Có được suy số row của association?

Không. Metamodel cho biết **mapping type**, không cho biết Department#10 hiện có bao nhiêu employees. Muốn biết số lượng phải dùng query phù hợp, ví dụ `COUNT(e)` với điều kiện department.

## 23. MapAttribute: key type và value type

Với:

~~~java
@ElementCollection
private Map<String, String> labels;
~~~

lấy metadata:

~~~java
MapAttribute<Employee, String, String> labels =
    employeeType.getMap(
        "labels",
        String.class,
        String.class
    );
~~~

Đọc:

~~~java
System.out.println(
    "key=" + labels.getKeyJavaType().getName()
);

System.out.println(
    "value=" + labels.getElementType()
        .getJavaType().getName()
);
~~~

Kết quả:

~~~text
key=java.lang.String
value=java.lang.String
~~~

### Map key không phải tự động là entity ID

Map key có thể là:

- Basic type như String/Integer.
- Entity-related key mapping tùy trường hợp.
- Embeddable key trong mapping phù hợp.

`MapAttribute` cho bạn metadata về key/value types; để biết chính xác bảng/cột key trong DB phải xem mapping chi tiết và provider schema/DDL.

## 24. getSingularAttributes() và getPluralAttributes()

Thay vì duyệt mọi Attribute rồi dùng `instanceof`, có thể dùng:

~~~java
Set<SingularAttribute<? super Employee, ?>> single =
    employeeType.getSingularAttributes();

Set<PluralAttribute<? super Employee, ?, ?>> plural =
    employeeType.getPluralAttributes();
~~~

### Dùng khi nào?

**Singular**:

- Basic types.
- Many-to-one/one-to-one associations.
- Embedded value objects.
- ID/version fields.

**Plural**:

- Collection/list/set/map.
- One-to-many/many-to-many associations.
- Element collections.

### Declared variants

JPA còn có:

~~~java
employeeType.getDeclaredSingularAttributes();
employeeType.getDeclaredPluralAttributes();
~~~

Giữ cùng ý nghĩa “chỉ thuộc tính khai báo tại type hiện tại”, khác với tập có cả inherited mappings.

## 25. Khám phá quan hệ JPA bằng Metamodel

Ví dụ:

~~~java
Attribute<? super Employee, ?> department =
    employeeType.getAttribute("department");

System.out.println(
    department.getPersistentAttributeType()
); // MANY_TO_ONE

System.out.println(
    department.isAssociation()
); // true
~~~

Với phía còn lại:

~~~java
Attribute<? super Department, ?> employees =
    deptType.getAttribute("employees");

System.out.println(
    employees.getPersistentAttributeType()
); // ONE_TO_MANY
~~~

### Có suy ra phía sở hữu quan hệ không?

Metamodel chuẩn cho biết loại mapping và Java type; nó **không cung cấp một API portable đầy đủ cho mọi chi tiết owning side, `mappedBy`, `@JoinColumn`, join table và khóa ngoại vật lý**.

Có thể đọc Java annotations bằng reflection, nhưng XML overrides/annotation access và naming strategies khiến cách đó không phải nguồn chuẩn duy nhất.

### Khi cần thông tin SQL cụ thể

Chọn một trong các hướng:

- Đọc mapping configuration của dự án.
- Dùng provider-specific mapping metadata (ví dụ Hibernate runtime mapping APIs).
- Kiểm tra schema thực qua database metadata/information_schema.
- Xem SQL được sinh trong integration tests.

Không đặt tên một bảng join dựa duy nhất vào `isAssociation()`.

## 26. Phân biệt relationship và embedded value object

So sánh:

~~~java
@ManyToOne
private Department department;

@Embedded
private Address address;
~~~

Metamodel:

| Attribute | PersistentAttributeType | isAssociation |
| --- | --- | --- |
| department | MANY_TO_ONE | true |
| address | EMBEDDED | false |

### Tại sao quan trọng?

Department là entity có identity riêng, có thể được join/query/lock theo entity lifecycle.

Address là một value object được map trong context của Employee. Không gọi:

~~~java
em.find(Address.class, someId);
~~~

vì Address không phải entity.

### Khám phá bên trong embeddable

~~~java
EmbeddableType<Address> addressType =
    model.embeddable(Address.class);

for (Attribute<? super Address, ?> field
        : addressType.getAttributes()) {
    System.out.println(field.getName());
}
~~~

Giúp một công cụ tài liệu hiển thị employee.address.street/city/postalCode, nhưng không khẳng định chính xác tên physical columns nếu có attribute overrides.

## 27. IdentifiableType và metadata ID

Entity có identity, còn mapped superclass có thể đóng góp ID mapping. JPA biểu diễn phần này qua `IdentifiableType<X>`.

Ví dụ:

~~~java
EntityType<Employee> employee =
    model.entity(Employee.class);

System.out.println(
    employee.hasSingleIdAttribute()
);
~~~

Với mô hình kế thừa `Long id`, kết quả dự kiến là `true`.

Lấy ID attribute:

~~~java
SingularAttribute<? super Employee, Long> id =
    employee.getId(Long.class);
~~~

### Tại sao có <? super Employee, Long>?

Vì `id` có thể được khai báo ở một **mapped superclass** như AuditedEntity, chứ không trực tiếp trong Employee.

### getDeclaredId() khác getId()

~~~java
employee.getId(Long.class);
~~~

có thể tìm ID được kế thừa.

~~~java
employee.getDeclaredId(Long.class);
~~~

chỉ liên quan ID được khai báo trực tiếp ở Employee và có thể ném exception nếu không tồn tại.

### Kiểm tra an toàn

Trước khi gọi API truy xuất ID đơn, xem entity có single ID attribute không. Với composite IDs, logic phải đi qua đường phù hợp thay vì giả định luôn có một Long id.

## 28. @Version trong metamodel

Với:

~~~java
@Version
private Long version;
~~~

truy vấn:

~~~java
boolean hasVersion =
    employee.hasVersionAttribute();

if (hasVersion) {
    SingularAttribute<? super Employee, Long> version =
        employee.getVersion(Long.class);

    System.out.println(version.isVersion());
}
~~~

### Có thể dùng để kiểm tra policy concurrency

Một hệ thống mong muốn mọi entity cần optimistic locking có version field có thể kiểm tra metamodel lúc startup.

Nhưng:

- Không phải entity nào cũng cần version.
- Một số provider hỗ trợ optimistic strategies khác dưới dạng extension.
- Có version không có nghĩa mọi native/bulk writers tự tăng version.
- Khi dùng composite/aggregate concurrency, bảo vệ invariant có thể rộng hơn một versioned row.

Metamodel giúp **phát hiện mapping metadata**, không tự chứng minh chiến lược concurrency được mọi writer tuân thủ.

## 29. @EmbeddedId và composite identity

Một entity có thể dùng:

~~~java
@Embeddable
public class EnrollmentId
        implements java.io.Serializable {

    private Long studentId;
    private Long courseId;

    public EnrollmentId() {
    }

    // equals() và hashCode() đúng theo giá trị ID.
}
~~~

~~~java
@Entity
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    private String status;
}
~~~

Metamodel:

~~~java
EntityType<Enrollment> type =
    model.entity(Enrollment.class);

SingularAttribute<? super Enrollment, EnrollmentId> id =
    type.getId(EnrollmentId.class);
~~~

`id` là một **singular attribute** kiểu embeddable, mặc dù nó chứa hai thành phần scalar.

### Đừng suy “composite key luôn có nhiều SingularAttribute.isId()”

Với `@EmbeddedId`, entity có một id attribute chứa value object. Metamodel phải được hiểu theo **mô hình mapping JPA**, không chỉ số cột của physical primary key trong DB.

### Equals/hashCode

Một embedded ID thực tế cần định nghĩa equality theo các thành phần ID một cách ổn định. Đây là vấn đề thiết kế identity, không được Metamodel tự sửa giúp.

## 30. @IdClass và nhiều ID attributes

Một lựa chọn khác:

~~~java
public class EnrollmentKey
        implements java.io.Serializable {

    private Long studentId;
    private Long courseId;

    public EnrollmentKey() {
    }

    // equals() và hashCode() đúng theo các key fields.
}
~~~

~~~java
@Entity
@IdClass(EnrollmentKey.class)
public class EnrollmentWithIdClass {

    @Id
    private Long studentId;

    @Id
    private Long courseId;

    private String status;
}
~~~

Với trường hợp nhiều attributes tạo thành ID:

~~~java
EntityType<EnrollmentWithIdClass> entityType =
    model.entity(EnrollmentWithIdClass.class);

if (!entityType.hasSingleIdAttribute()) {
    for (SingularAttribute<? super EnrollmentWithIdClass, ?>
            idAttr : entityType.getIdClassAttributes()) {

        System.out.println(idAttr.getName());
    }
}
~~~

Kết quả:

~~~text
studentId
courseId
~~~

### Không gọi getId(Long.class) rồi hy vọng chọn một trong hai

Đó là một entity với multi-attribute identity. Công cụ inspection phải xét `hasSingleIdAttribute()`/`getIdClassAttributes()` phù hợp.

### @EmbeddedId vs @IdClass

| Tiêu chí | @EmbeddedId | @IdClass |
| --- | --- | --- |
| ID trong entity | Một object ID | Nhiều fields @Id |
| Metamodel ID | Một singular attribute có Java type embeddable | Nhiều ID attributes |
| Criteria path | `root.get("id").get("studentId")` | `root.get("studentId")` |
| Thiết kế Java | Value object tập trung | Mapping fields trực tiếp |

Không mặc định một lựa chọn tốt hơn trong mọi domain; metamodel chỉ phản ánh mô hình đã chọn.

## 31. Kế thừa entity và mapped superclass

JPA có hai cơ chế thường bị nhầm:

1. **Java class inheritance + `@MappedSuperclass`**.
2. **JPA entity inheritance** với `@Inheritance`, nơi cả base và các subclasses có thể là entity types.

### Mapped superclass

~~~java
@MappedSuperclass
abstract class AuditedEntity {
    @Id Long id;
    @Version Long version;
}
~~~

Không có entity instance riêng để query trong JPQL.

### Entity inheritance

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
abstract class Payment {
    @Id Long id;
}

@Entity
class CardPayment extends Payment {
    String cardBrand;
}
~~~

Trong trường hợp này, cả Payment và CardPayment có thể xuất hiện ở `getEntities()` và có entity type metadata.

### Tại sao Metamodel hữu ích?

Một công cụ introspection có thể thấy cấu trúc inheritance ở mức mapping, thay vì đoán rằng mọi superclass đều là mapped superclass.

## 32. getSupertype() của IdentifiableType

Ví dụ:

~~~java
EntityType<Employee> type =
    model.entity(Employee.class);

IdentifiableType<? super Employee> parent =
    type.getSupertype();

if (parent != null) {
    System.out.println(
        parent.getJavaType().getName()
    );
}
~~~

Với mô hình Employee kế thừa AuditedEntity, parent là identifiable type tương ứng nếu mapping hierarchy có supertype nhận diện được.

### Không phải superclass Java nào cũng là JPA supertype

Một Java base class không được JPA map có thể tồn tại trong hierarchy nhưng không phải một managed/identifiable type mà metamodel mô tả giống `@MappedSuperclass` hoặc entity inheritance.

### Ứng dụng

- Sinh tài liệu lineage.
- Xác định fields ID/version được kế thừa từ đâu.
- Hiểu vì sao `getDeclaredAttribute("id")` không tìm thấy nhưng `getAttribute("id")` có.

## 33. Static metamodel là gì?

Runtime metamodel cho phép lấy attribute bằng string:

~~~java
employeeType.getSingularAttribute(
    "employeeCode",
    String.class
);
~~~

Nhưng nếu đổi tên field trong code:

~~~java
private String staffCode;
~~~

string `"employeeCode"` có thể tiếp tục compile rồi lỗi runtime.

**Static canonical metamodel** tạo ra những lớp Java có attributes được khai báo theo kiểu:

~~~java
Employee_.employeeCode
Department_.code
AuditedEntity_.id
~~~

Khi field được rename, đoạn code dựa vào `Employee_.employeeCode` có thể bị compiler báo lỗi sau khi generated source được cập nhật.

### Từ entity đến static metamodel

~~~text
Employee.java
  @Entity
  String employeeCode;
  Department department;
  Set<String> skills;
          |
          v
Annotation processor
          |
          v
Employee_.java
  SingularAttribute<Employee, String> employeeCode
  SingularAttribute<Employee, Department> department
  SetAttribute<Employee, String> skills
~~~

Đây là **source code được tạo lúc biên dịch**, không phải output của `emf.getMetamodel()` trực tiếp tại runtime.

## 34. Ví dụ static canonical metamodel

Một generated class minh họa:

~~~java
package com.example.hr.domain;

import jakarta.persistence.metamodel.MapAttribute;
import jakarta.persistence.metamodel.SetAttribute;
import jakarta.persistence.metamodel.SingularAttribute;
import jakarta.persistence.metamodel.StaticMetamodel;

@StaticMetamodel(Employee.class)
public abstract class Employee_ extends AuditedEntity_ {

    public static volatile
        SingularAttribute<Employee, String> employeeCode;

    public static volatile
        SingularAttribute<Employee, String> fullName;

    public static volatile
        SingularAttribute<Employee, Department> department;

    public static volatile
        SingularAttribute<Employee, Address> address;

    public static volatile
        SetAttribute<Employee, String> skills;

    public static volatile
        MapAttribute<Employee, String, String> labels;
}
~~~

Với superclass:

~~~java
@StaticMetamodel(AuditedEntity.class)
public abstract class AuditedEntity_ {

    public static volatile
        SingularAttribute<AuditedEntity, Long> id;

    public static volatile
        SingularAttribute<AuditedEntity, Long> version;

    public static volatile
        SingularAttribute<AuditedEntity, Instant> createdAt;
}
~~~

### Đừng tự sửa generated class

Các lớp `Employee_`, `Department_` thường được annotation processor tái sinh khi build. Sửa trực tiếp file trong generated-sources có thể bị ghi đè và khiến source thực không đồng bộ.

### Cụ thể về kiểu và inheritance

Ví dụ trên tập trung vào ý tưởng. Chi tiết modifiers, hằng tên thuộc tính, class header và cách xử lý inheritance có thể khác theo annotation processor/JPA version. Chỉ dựa vào **generated sources thật của build** để viết Criteria code trong dự án.

## 35. Static metamodel giúp Criteria API an toàn kiểu

Với Criteria API dùng string:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> cq =
    cb.createQuery(Employee.class);

Root<Employee> root =
    cq.from(Employee.class);

cq.where(
    cb.equal(
        root.get("employeeCode"),
        "EMP-001"
    )
);
~~~

Sai chính tả `"employeeCode"` thành `"employeCode"` vẫn có thể compile và chỉ lỗi runtime.

Với static metamodel:

~~~java
cq.where(
    cb.equal(
        root.get(Employee_.employeeCode),
        "EMP-001"
    )
);
~~~

`Employee_.employeeCode` có kiểu:

~~~java
SingularAttribute<Employee, String>
~~~

và `root.get(...)` có Path/Expression với kiểu giá trị phù hợp.

### Đây có phải bảo đảm mọi câu Criteria luôn hợp lệ?

Không. Compiler giúp bắt nhiều lỗi tên thuộc tính và kiểu Java, nhưng còn:

- SQL dialect và provider constraints.
- Unsupported functions/joins.
- Dữ liệu thực và transaction state.
- Collation, DB constraints và query performance.
- Error do parameters được tạo runtime.

**Compile-time type safety giảm một loại lỗi, không thay integration tests.**

## 36. Cấu hình annotation processor

Tùy provider/version, cần một annotation processor tạo canonical metamodel classes.

Ví dụ cấu hình Gradle mang tính minh họa với **một dòng Hibernate ORM 6.x tương thích Jakarta**:

~~~kotlin
dependencies {
    implementation(
        "org.hibernate.orm:hibernate-core:<hibernate-version>"
    )

    annotationProcessor(
        "org.hibernate.orm:hibernate-jpamodelgen:<hibernate-version>"
    )
}
~~~

Thay `<hibernate-version>` bằng **một phiên bản thật đồng bộ với BOM/runtime** trong dự án. Một số dòng Hibernate đời mới có thay đổi tên processor/artifact, ví dụ `hibernate-processor`; luôn chọn theo tài liệu của **phiên bản đang dùng**, không sao chép tọa độ dependencies từ bài khác nếu stack đã khác.

### Maven

Có thể cấu hình annotation processing qua compiler plugin/processor dependency tương ứng. Quan trọng là:

1. Processor được chạy trong compile.
2. Class `Employee_` xuất hiện trong generated sources.
3. IDE/compiler nhận generated sources.
4. Source thực và generated sources tương ứng đúng phiên bản Jakarta/Javax.

### Nếu không muốn phụ thuộc vào generator?

Runtime metamodel vẫn tồn tại khi JPA provider hỗ trợ. Có thể dùng Criteria API với string paths hoặc xử lý metadata động, nhưng sẽ mất một phần lợi ích compile-time refactoring safety.

## 37. Không trộn javax static metamodel với jakarta runtime

Hai thế hệ:

~~~java
javax.persistence.metamodel.SingularAttribute
~~~

và:

~~~java
jakarta.persistence.metamodel.SingularAttribute
~~~

không phải cùng Java type.

Nếu entity source sử dụng `jakarta.persistence.Entity` nhưng processor sinh `javax.persistence.metamodel.*`, Criteria code có thể lỗi compile hoặc không tương thích.

### Checklist khi migrate Jakarta

- Entity annotations đã chuyển sang `jakarta.persistence.*`?
- Criteria imports đã chuyển?
- Static metamodel processor có hỗ trợ Jakarta không?
- Generated sources có được clean/regenerate?
- Không còn old `javax.persistence.*` JPA API artifact gây xung đột classpath?
- Integration tests chạy trên provider phù hợp?

Tránh commit generated sources cũ không được tái sinh sau migration nếu build có thể tạo lại đúng cách.

## 38. Ví dụ Criteria query với static metamodel

Tìm nhân viên theo department code:

~~~java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> query =
    cb.createQuery(Employee.class);

Root<Employee> employee =
    query.from(Employee.class);

Join<Employee, Department> department =
    employee.join(
        Employee_.department,
        JoinType.INNER
    );

query.select(employee)
    .where(
        cb.equal(
            department.get(Department_.code),
            "ENG"
        )
    )
    .orderBy(
        cb.asc(
            employee.get(Employee_.employeeCode)
        )
    );

List<Employee> results =
    em.createQuery(query).getResultList();
~~~

Điểm nổi bật:

- `Employee_.department` diễn tả association có kiểu Department.
- `Department_.code` diễn tả property có kiểu String.
- Nếu rename property code, generated metamodel/compile sẽ giúp phát hiện các call sites.

### Có cần JPQL string nữa không?

Không bắt buộc. Criteria API thích hợp khi query cần xây dựng động, còn JPQL thường đọc nhanh hơn đối với query cố định. Metamodel hỗ trợ Criteria, nhưng không ép mọi service phải thay JPQL thành Criteria.

## 39. Query có điều kiện tùy chọn

Giả sử form tìm nhân viên nhận:

~~~text
departmentCode = "ENG" (có thể null)
nameContains = "an" (có thể null)
~~~

Criteria:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> cq =
    cb.createQuery(Employee.class);

Root<Employee> root = cq.from(Employee.class);
List<Predicate> filters = new ArrayList<>();

if (nameContains != null
        && !nameContains.isBlank()) {
    filters.add(
        cb.like(
            cb.lower(root.get(Employee_.fullName)),
            "%" + nameContains.toLowerCase(Locale.ROOT) + "%"
        )
    );
}

if (departmentCode != null
        && !departmentCode.isBlank()) {
    Join<Employee, Department> dept =
        root.join(Employee_.department);

    filters.add(
        cb.equal(
            dept.get(Department_.code),
            departmentCode
        )
    );
}

cq.select(root)
    .where(filters.toArray(Predicate[]::new));

List<Employee> employees =
    em.createQuery(cq).getResultList();
~~~

### Đừng quên LIKE escaping

Mẫu trên minh họa Criteria construction. Với input người dùng, `%` và `_` có ý nghĩa wildcard trong SQL LIKE; nếu cần tìm **chuỗi literal**, phải escape wildcard theo dialect/Criteria `like(..., escapeChar)` phù hợp.

### Không dùng string concatenation trong JPQL

Static metamodel cung cấp typed paths. Khi dùng CriteriaBuilder với parameters, provider tạo parameter binding và giúp tránh kiểu ghép chuỗi JPQL trực tiếp từ input cho values.

## 40. Criteria query qua embedded value object

Tìm Employee ở một thành phố:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> cq =
    cb.createQuery(Employee.class);

Root<Employee> root = cq.from(Employee.class);

cq.select(root).where(
    cb.equal(
        root.get(Employee_.address)
            .get(Address_.city),
        "Hà Nội"
    )
);
~~~

Điểm cần phân biệt:

- `Employee_.address` đại diện một `SingularAttribute<Employee, Address>`.
- `Address_.city` đại diện một `SingularAttribute<Address, String>`.
- Truy cập nested path của embeddable không tự có nghĩa tạo SQL JOIN đến một bảng Address độc lập.

### Nếu có AttributeOverride?

~~~java
@Embedded
@AttributeOverride(
    name = "city",
    column = @Column(name = "office_city"))
private Address address;
~~~

Criteria path vẫn là `address.city` về mặt Java model, còn physical SQL column có thể là `office_city`. Đây là ví dụ cho thấy Metamodel **logic** và database **physical** là hai lớp khác nhau.

## 41. Criteria join một collection

Tìm Department có Employee mang skill `"JPA"`:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Department> cq =
    cb.createQuery(Department.class);

Root<Department> dept = cq.from(Department.class);
ListJoin<Department, Employee> employee =
    dept.join(
        Department_.employees,
        JoinType.INNER
    );

SetJoin<Employee, String> skill =
    employee.join(
        Employee_.skills,
        JoinType.INNER
    );

cq.select(dept)
    .distinct(true)
    .where(cb.equal(skill, "JPA"));
~~~

### Vì sao distinct?

Một Department có nhiều Employees hoặc một Employee có nhiều skills matching trong những truy vấn tương tự; JOIN có thể tạo nhiều rows cho cùng Department. `distinct(true)` diễn đạt ý định chỉ lấy các Department khác nhau.

### Không đánh đồng SQL rows với số managed entities

Provider có thể materialize SQL rows và quản lý entity identity map để xử lý duplicates. Số JOIN rows không đồng nghĩa số Department objects độc lập.

### Performance

Collection JOIN có thể làm query tốn kém. Metamodel không tự thiết kế indexes hoặc chọn join strategy tối ưu; cần xem SQL/EXPLAIN khi workload lớn.

## 42. Criteria query với MapAttribute

Nếu Employee lưu nhãn theo ngôn ngữ:

~~~java
@ElementCollection
private Map<String, String> labels;
~~~

có thể join map:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> cq =
    cb.createQuery(Employee.class);

Root<Employee> root = cq.from(Employee.class);

MapJoin<Employee, String, String> label =
    root.join(
        Employee_.labels,
        JoinType.LEFT
    );

cq.select(root)
    .distinct(true)
    .where(
        cb.and(
            cb.equal(label.key(), "vi"),
            cb.like(label.value(), "%Java%")
        )
    );
~~~

Map key và value có paths riêng:

~~~java
label.key()
label.value()
~~~

### Lưu ý về Map join

Đây là truy vấn trên **element collection mapping** của Employee. Nếu muốn lọc một Map trong Java thuần không được JPA map, static metamodel sẽ không có MapAttribute tương ứng.

### Trường hợp phức tạp

Map có entity keys/values hoặc embeddable values cần mapping và join path phù hợp. Đừng suy mọi `Map<K,V>` được biểu diễn bằng một bảng key/value đơn giản y hệt.

## 43. Runtime metamodel cho truy vấn động

Một API có thể nhận một filter key:

~~~text
field=employeeCode
value=EMP-001
~~~

Trước khi dựng query, service có thể kiểm tra:

~~~java
EntityType<Employee> type =
    em.getMetamodel().entity(Employee.class);

Attribute<? super Employee, ?> attr =
    type.getAttribute(field);
~~~

Nếu field không tồn tại, `getAttribute` ném `IllegalArgumentException`. Có thể chuyển thành lỗi request phù hợp.

### Nhưng không nhận mọi attribute trong metamodel là public filter

Metamodel có thể chứa:

- Internal IDs.
- Tenant IDs.
- Version fields.
- Soft delete status.
- Sensitive attributes.
- Associations có chi phí JOIN lớn.

**Metadata tồn tại không đồng nghĩa client được phép truy vấn nó**.

### Phương án thực tế

Chỉ cho phép một allowlist những fields đã được API contract duyệt.

## 44. Allowlist bảo vệ dynamic sorting

Ví dụ:

~~~java
Set<String> allowedSorts = Set.of(
    "employeeCode",
    "fullName"
);

if (!allowedSorts.contains(sortBy)) {
    throw new IllegalArgumentException(
        "Thuộc tính sort không được hỗ trợ");
}
~~~

Sau đó có thể kiểm tra thêm metamodel:

~~~java
Attribute<? super Employee, ?> attr =
    employeeType.getAttribute(sortBy);

if (attr.isAssociation() || attr.isCollection()) {
    throw new IllegalArgumentException(
        "Không hỗ trợ sort trên quan hệ/collection");
}
~~~

Cuối cùng dựng Criteria order:

~~~java
Path<?> sortPath = root.get(sortBy);

cq.orderBy(
    descending
        ? cb.desc(sortPath)
        : cb.asc(sortPath)
);
~~~

### Vì sao vừa allowlist vừa metamodel?

- Allowlist biểu diễn **authorization/API contract**.
- Metamodel biểu diễn **mapping hợp lệ**.

Một attribute `salary` hợp lệ trong entity nhưng không thuộc public allowlist phải bị từ chối. Metamodel không làm công việc của authorization.

### Tính type safety khi dùng string

Ở cuối ví dụ, `root.get(sortBy)` vẫn là dynamic string path. Do đó compiler không kiểm tra trước field do user gửi. Ta dùng metamodel để validate runtime, không pretend rằng mọi dynamic query tự trở thành compile-time safe.

## 45. Dynamic filter cần kiểm tra Java type

Giả sử:

~~~text
field=employeeCode
operator=contains
value=EMP
~~~

Nhưng một request khác gửi:

~~~text
field=version
operator=contains
value=abc
~~~

Metamodel giúp phát hiện `version` là Long, không phù hợp `LIKE`:

~~~java
Attribute<? super Employee, ?> attr =
    employeeType.getAttribute(field);

if (attr.getJavaType() != String.class) {
    throw new IllegalArgumentException(
        "contains chỉ áp dụng cho String");
}
~~~

### Cẩn trọng primitive/wrapper types

`boolean.class` và `Boolean.class` không phải cùng `Class<?>`, và kiểu Java khai báo có thể primitive. Logic generic cần xét đúng type handling.

### Type convert của input

Một dynamic filter service phải chuyển input:

~~~text
"42" -> Long
"2025-11-01" -> LocalDate
"ACTIVE" -> enum
~~~

theo field type/format API contract. Metamodel cho biết Java type, nhưng không quyết định mọi parsing/locale/time zone policy.

## 46. Viết một utility liệt kê entity và thuộc tính

Ví dụ utility chỉ đọc metadata:

~~~java
package com.example.hr.tools;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.metamodel.Attribute;
import jakarta.persistence.metamodel.EntityType;
import jakarta.persistence.metamodel.Metamodel;
import java.util.Comparator;

public final class MetamodelReporter {

    private MetamodelReporter() {
    }

    public static void print(EntityManagerFactory emf) {
        Metamodel model = emf.getMetamodel();

        model.getEntities().stream()
            .sorted(Comparator.comparing(EntityType::getName))
            .forEach(entity -> {

                System.out.println(
                    "ENTITY " + entity.getName()
                    + " (" + entity.getJavaType().getName() + ")"
                );

                entity.getAttributes().stream()
                    .sorted(
                        Comparator.comparing(Attribute::getName)
                    )
                    .forEach(attr -> {
                        System.out.println(
                            "  " + attr.getName()
                            + " : " + attr.getJavaType()
                                .getSimpleName()
                            + " [" + attr
                                .getPersistentAttributeType()
                            + "]"
                        );
                    });
            });
    }
}
~~~

### Vì sao không mở EntityManager?

Utility chỉ đọc cấu trúc mapping từ EntityManagerFactory. Nó không cần persistence context hoặc DB transaction để duyệt metadata.

### Kết quả dùng để làm gì?

- Chẩn đoán mapping đã nhận diện.
- Sinh bảng đặc tả technical model.
- So sánh một số kỳ vọng của domain với model bootstrap.

### Không tự đăng output vào public endpoint

Các tên class, package, properties và associations có thể lộ cấu trúc nội bộ. Chỉ sử dụng trong tool nội bộ có quyền phù hợp, không trả toàn bộ metamodel cho anonymous clients.

## 47. In metadata có element type và flags

Một reporter sâu hơn:

~~~java
for (Attribute<? super Employee, ?> attr
        : employeeType.getAttributes()) {

    String detail = attr.getName()
        + " | java=" + attr.getJavaType().getSimpleName()
        + " | mapping=" + attr.getPersistentAttributeType()
        + " | association=" + attr.isAssociation()
        + " | collection=" + attr.isCollection();

    if (attr instanceof SingularAttribute<?, ?> single) {
        detail +=
            " | optional=" + single.isOptional()
            + " | id=" + single.isId()
            + " | version=" + single.isVersion();
    }

    if (attr instanceof PluralAttribute<?, ?, ?> plural) {
        detail +=
            " | element=" + plural.getElementType()
                .getJavaType().getSimpleName()
            + " | collectionType=" + plural.getCollectionType();
    }

    if (attr instanceof MapAttribute<?, ?, ?> map) {
        detail +=
            " | key=" + map.getKeyJavaType().getSimpleName();
    }

    System.out.println(detail);
}
~~~

### Vì sao kiểm tra instanceof?

`Attribute` là super-interface chung. Những thông tin:

- `isId`/`isVersion` chỉ có ở singular metadata.
- `getElementType`/`getCollectionType` ở plural metadata.
- `getKeyJavaType` ở map metadata.

Không ép mọi Attribute thành SingularAttribute rồi bị `ClassCastException` khi gặp `List<Employee>` hay `Map<String,String>`.

### Dùng Java pattern matching

Ví dụ `instanceof SingularAttribute<?, ?> single` dùng Java pattern matching hỗ trợ từ các JDK hiện đại. Với JDK cũ, dùng `instanceof` rồi cast tương ứng.

## 48. Metamodel không mô tả toàn bộ DDL

JPA annotation:

~~~java
@Entity
@Table(name = "employees")
class Employee {
    @Column(name = "employee_code", nullable = false)
    String employeeCode;
}
~~~

Metamodel có thể báo:

~~~text
Employee is ENTITY
employeeCode is BASIC
employeeCode Java type is String
~~~

Nhưng không có API JPA chuẩn tương đương:

~~~java
employeeType.getPhysicalTableName();
employeeCodeAttr.getActualColumnNames();
employeeType.getDatabaseIndexes();
employeeType.getForeignKeyConstraintName();
~~~

**Các methods trên chỉ là ví dụ không tồn tại trong JPA Metamodel API.**

### DDL có thể khác mapping vì sao?

- `@Table`/`@Column` overrides.
- Naming strategy do provider cấu hình.
- `@SecondaryTable`/inheritance strategies.
- Database schema/catalog configuration.
- Physical migrations đã/không chạy.
- Triggers, indexes và generated columns.
- Database types/precision/constraints khác với Java declarations.

Nếu mục tiêu là **kiểm tra schema vật lý**, phải dùng công cụ/schema metadata chuyên biệt thay vì coi Metamodel là schema catalog hoàn chỉnh.

## 49. Metamodel và DatabaseMetaData khác nhau

| Nguồn | Cho biết gì? | Không bảo đảm |
| --- | --- | --- |
| JPA Metamodel | Entities, attributes, associations, ID/version, Java types | Physical SQL tables/columns/indexes chính xác |
| JDBC DatabaseMetaData | Tables, columns, keys, indexes được driver/DB expose | Quy tắc domain/Java entity mapping đầy đủ |
| information_schema/DB catalog | Schema objects hiện hữu, tùy DBMS | Entity relationships logic/methods |
| Migration scripts (Flyway/Liquibase...) | Lịch sử thay đổi schema dự kiến | Tự chứng minh DB chưa drift |
| Provider-specific runtime mapping model | Chi tiết mapping SQL do provider nhận diện | Tính portable giữa providers |

### Kết hợp khi làm schema diff

Một công cụ kiểm tra mapping ↔ DB cần:

1. Đọc JPA managed model.
2. Lấy provider mapping metadata hoặc các annotation/XML overrides liên quan.
3. Đọc physical schema qua JDBC/database.
4. Chuẩn hóa identifiers, catalog/schema, naming strategies.
5. So sánh bằng các rules có ý thức về inheritance/embedded/secondary tables.

Chỉ `getEntities()` + `getAttributes()` không đủ để viết schema diff chính xác cho mọi JPA mapping.

## 50. AttributeOverride và AssociationOverride

Với một embeddable:

~~~java
@Embeddable
class Address {
    private String city;
}
~~~

Employee có thể override:

~~~java
@Embedded
@AttributeOverride(
    name = "city",
    column = @Column(name = "home_city"))
private Address homeAddress;

@Embedded
@AttributeOverride(
    name = "city",
    column = @Column(name = "work_city"))
private Address workAddress;
~~~

Metamodel:

~~~text
Employee.homeAddress -> Address (EMBEDDED)
Employee.workAddress -> Address (EMBEDDED)
Address.city -> String (BASIC)
~~~

Nhưng physical columns tương ứng có thể là:

~~~text
home_city
work_city
~~~

Do đó một `EmbeddableType<Address>` được dùng hai lần không tự chứa đủ context để biết mỗi path được map tới cột nào.

### Hệ quả cho tài liệu hóa

Công cụ report dựa trên JPA Metamodel nên ghi rõ:

> “Đây là tên logical attributes và Java types; physical column names phải được lấy từ mapping configuration/provider/database.”

Không tự suy tên column bằng cách nối `address.city`.

## 51. Inheritance strategy làm physical layout khác nhau

Ví dụ:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
class Payment { ... }
~~~

và:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
class Payment { ... }
~~~

cho hai physical layouts khác nhau dù logical Java hierarchy có thể tương tự:

- SINGLE_TABLE: nhiều entity subclasses chia sẻ bảng vật lý theo chiến lược.
- JOINED: superclass/subclass mapping tham gia các bảng được join.
- TABLE_PER_CLASS: các concrete classes có bảng theo chiến lược tương ứng.

### Metamodel cho biết gì?

Entity types, Java hierarchy, inherited attributes.

### Không tự có gì?

Một API portable đủ thông tin để suy toàn bộ DDL tables, discriminator, FK constraints và secondary SQL join plans từ mỗi `EntityType`.

Đừng cố biến `EntityType.getName()` thành physical table name trong mọi strategy.

## 52. Mapping bằng XML và @Access

JPA mapping không nhất thiết chỉ đến từ annotations:

~~~text
Java classes + orm.xml + persistence.xml + provider configuration
                         |
                         v
                 Runtime Metamodel
~~~

Nếu XML mapping override một property hoặc dùng access mode khác, code reflection tự đọc fields/annotations có thể cho kết quả khác với mapping đã được provider nhận diện.

### Tại sao metamodel hữu ích hơn reflection thuần trong việc khám phá model?

Vì nó biểu diễn **mô hình persistent đã được JPA nhận diện**. Các thao tác như `getAttribute("name")` phản ánh property của model, không đơn giản là mọi Java member có tên "name".

### Nhưng metamodel cũng có giới hạn

Nó không expose mọi vendor-specific mapping option. Muốn xem physical columns/join formula của Hibernate, cần runtime mapping API của Hibernate — không thể yêu cầu JPA chuẩn cung cấp mọi chi tiết vendor.

## 53. Multi-tenancy và metadata

Nếu có nhiều tenants:

~~~text
Tenant A -> Employee / Department
Tenant B -> Employee / Department
~~~

cả hai có thể dùng cùng persistence unit/metamodel ở Java level, dù dữ liệu nằm trong:

- Cùng schema với tenant_id.
- Khác schema.
- Khác database.

**Metamodel không tự có nghĩa “chỉ các entities người dùng hiện tại được quyền xem”.**

### Nguy cơ

Nếu ứng dụng mở một endpoint:

~~~text
GET /debug/metamodel
~~~

và trả toàn bộ tên entity/property cho mọi người, đó có thể là rò rỉ cấu trúc nội bộ.

### Hướng thiết kế

- Dùng tool nội bộ hoặc bảo vệ bằng quyền admin.
- Không để API nhận entity class name tùy ý rồi tự query mọi bảng.
- Giữ tenant/ACL predicate trong mỗi business query.
- Xác minh provider multi-tenant cache/key/isolation configuration nếu áp dụng.

Metamodel là **metadata kỹ thuật**, không phải security boundary.

## 54. Từ metamodel đến schema documentation

Một tài liệu kỹ thuật có thể có cấu trúc:

~~~text
Persistence unit: hrPU

ENTITY Employee
  Java class: com.example.hr.domain.Employee
  Parent mapping: AuditedEntity (MAPPED_SUPERCLASS)

  Attributes:
    id            Long        BASIC [ID, inherited]
    version       Long        BASIC [VERSION, inherited]
    createdAt     Instant     BASIC [inherited]
    employeeCode  String      BASIC
    fullName      String      BASIC
    department    Department  MANY_TO_ONE
    address       Address     EMBEDDED
    skills        Set<String> ELEMENT_COLLECTION
    labels        Map         ELEMENT_COLLECTION

ENTITY Department
  Attributes:
    ...

EMBEDDABLE Address
  street, city, postalCode
~~~

### Lợi ích

- Dễ kiểm tra domain model đã bootstrap.
- Giúp review mapping khi có nhiều modules.
- Là đầu vào cho công cụ thiết kế API nội bộ hoặc admin UI.

### Không biến thành tài liệu database vật lý

Đây là **sơ đồ ánh xạ logic**. Nếu người đọc cần cột SQL chính xác, phải bổ sung nguồn DB/provider mapping.

## 55. Kiểm tra mapping policy khi khởi động

Một ứng dụng có quy ước:

> Tất cả entity ghi nhiều lần phải có @Version.

Có thể viết helper:

~~~java
public static void assertVersioned(
        EntityManagerFactory emf,
        Set<Class<?>> requiredVersionedEntities) {

    Metamodel model = emf.getMetamodel();

    for (Class<?> javaType : requiredVersionedEntities) {
        EntityType<?> entity = model.entity(javaType);

        if (!entity.hasVersionAttribute()) {
            throw new IllegalStateException(
                "Entity thiếu version: "
                + javaType.getName()
            );
        }
    }
}
~~~

### Tại sao dùng allowlist?

Không phải mọi entity đều buộc phải versioned. Một số bảng append-only, immutable reference tables hoặc association entities có concurrency strategy riêng. Nếu buộc toàn bộ entities có @Version mà không xét nghiệp vụ, check có thể tạo false positives.

### Hạn chế

Kiểm tra này không chứng minh:

- Mọi UPDATE đi qua managed JPA entity.
- Bulk/native writes tự tăng version.
- Business invariants nhiều rows được bảo vệ.
- Column version trong DB có DDL đúng.

Đây là **kiểm tra mapping policy**, không phải concurrency test.

## 56. Kiểm tra một entity bắt buộc phải có attribute

Ví dụ một API phụ thuộc property `tenantId`:

~~~java
public static void requireTenantAttribute(
        Metamodel model,
        Class<?> entityClass) {

    EntityType<?> entity =
        model.entity(entityClass);

    Attribute<?, ?> tenant;

    try {
        tenant = entity.getAttribute("tenantId");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException(
            "Entity thiếu mapped tenantId: "
            + entityClass.getName(),
            ex
        );
    }

    if (tenant.getJavaType() != Long.class) {
        throw new IllegalStateException(
            "tenantId phải có Java type Long"
        );
    }
}
~~~

### Có cần mọi entity cùng tên tenantId?

Không. Domain có thể dùng tenantId, organizationId, workspaceId hoặc provider multi-tenancy mà không có persistent field trực tiếp trên mọi entity. Chỉ áp rule cho những entities có contract đó.

### Không coi field tồn tại là đủ an toàn

`tenantId` được map không có nghĩa mọi JPQL query đã có WHERE tenantId = current tenant. Cần test/query/security policy riêng.

## 57. Unit test không cần truy cập DB data nhưng cần JPA bootstrap

Một test metamodel:

~~~java
@Test
void employeeMappingContainsDepartment() {
    EntityType<Employee> type =
        emf.getMetamodel().entity(Employee.class);

    Attribute<? super Employee, ?> attr =
        type.getAttribute("department");

    assertEquals(
        Attribute.PersistentAttributeType.MANY_TO_ONE,
        attr.getPersistentAttributeType()
    );
}
~~~

Test này:

- Không cần tạo một Employee row.
- Không cần query employee data.
- Nhưng **cần EntityManagerFactory được bootstrap với mapping thật**.

### Tại sao không chỉ mock Metamodel?

Mock có thể trả dữ liệu ta tự dựng và không kiểm tra provider thực sự đã nhận diện annotation/XML thế nào. Nếu mục tiêu là xác nhận mapping, test nên dùng JPA provider thật.

### Tại sao test có thể khởi động DB?

Provider bootstrap có thể cần datasource/dialect/schema validation tùy cấu hình. “Không query entity data” không có nghĩa khởi tạo EMF luôn hoàn toàn offline.

## 58. Integration test inherited ID/version

Test:

~~~java
@Test
void employeeInheritsIdAndVersion() {
    EntityType<Employee> employee =
        emf.getMetamodel().entity(Employee.class);

    assertTrue(employee.hasSingleIdAttribute());
    assertTrue(employee.hasVersionAttribute());

    assertTrue(
        employee.getId(Long.class).isId()
    );

    assertTrue(
        employee.getVersion(Long.class).isVersion()
    );

    assertThrows(
        IllegalArgumentException.class,
        () -> employee.getDeclaredAttribute("id")
    );
}
~~~

Mục tiêu: phân biệt `getAttribute` với `getDeclaredAttribute` khi ID được kế thừa từ mapped superclass.

### Không assert thứ tự getAttributes()

API trả Set; thứ tự iteration không phải mapping contract. Nếu muốn snapshot report ổn định, sắp xếp.

## 59. Integration test plural/map attributes

~~~java
@Test
void employeeCollectionsAreMapped() {
    EntityType<Employee> type =
        emf.getMetamodel().entity(Employee.class);

    SetAttribute<Employee, String> skills =
        type.getSet("skills", String.class);

    assertEquals(
        PluralAttribute.CollectionType.SET,
        skills.getCollectionType()
    );

    assertEquals(
        Attribute.PersistentAttributeType.ELEMENT_COLLECTION,
        skills.getPersistentAttributeType()
    );

    MapAttribute<Employee, String, String> labels =
        type.getMap(
            "labels",
            String.class,
            String.class
        );

    assertEquals(
        String.class,
        labels.getKeyJavaType()
    );
}
~~~

### Lợi ích

Nếu ai đó đổi `skills` từ `Set<String>` thành một entity relationship, test có thể phát hiện sự thay đổi mapping quan trọng.

### Không chứng minh DDL

Test này không xác nhận employee_skills/employee_labels tables đã tồn tại hoặc có FK/index đúng. Đó là integration/schema test khác.

## 60. Test compile-time static metamodel

Một Criteria query:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Employee> cq =
    cb.createQuery(Employee.class);

Root<Employee> employee =
    cq.from(Employee.class);

cq.where(
    cb.equal(
        employee.get(Employee_.employeeCode),
        "EMP-001"
    )
);
~~~

Nếu `Employee_` không được sinh, **compile sẽ fail**. Đây là dấu hiệu annotation processing chưa được cấu hình đúng hoặc source generation thiếu dependencies.

### Test tách hai việc

1. **Build/compile test:** generated metamodel classes tồn tại và typed Criteria code compile.
2. **Runtime integration test:** Criteria query thật hoạt động trên provider/DBMS.

Không kết luận query đúng chỉ vì static metamodel class tồn tại.

## 61. Troubleshooting: getEntities() rỗng

Một chương trình:

~~~java
System.out.println(
    emf.getMetamodel().getEntities().size()
);
~~~

trả 0 có thể do:

- Persistence unit không quét/đăng ký entity class nào.
- Entity classes nằm ngoài phạm vi scanning.
- Mapping XML/annotation bị thiếu hoặc sai.
- Đang bootstrap **persistence unit khác** với đơn vị mong đợi.
- Project có modules khác classloader và entity không được provider nhìn thấy.

### Không sửa bằng cách quét classpath rồi gọi reflect ngẫu nhiên

Hãy kiểm tra cấu hình entity discovery của provider/framework trước. Metamodel là ảnh chụp những mappings đã được đăng ký, nó không tự biến classes chưa registered thành managed entities.

## 62. Troubleshooting: getAttribute("x") ném lỗi

Nguyên nhân phổ biến:

| Triệu chứng | Cần kiểm tra |
| --- | --- |
| `getAttribute("employee_code")` lỗi | Đang dùng tên SQL column thay vì Java property |
| `getDeclaredAttribute("id")` lỗi | ID được kế thừa từ mapped superclass |
| `getSingularAttribute("skills")` lỗi | skills là plural SetAttribute |
| `getSet("employees")` lỗi | employees là List, không phải Set |
| `getMap("labels", keyClass, valueClass)` lỗi | Key/value type không đúng |
| `getAttribute("displayText")` lỗi | Field @Transient không persistent |
| `entity(Address.class)` lỗi | Address là @Embeddable, không là entity |
| `entity(String.class)` lỗi | String không là managed entity |
| `getId(Long.class)` không phù hợp | Entity dùng composite ID/ID Java type khác |
| Static Employee_ class không tồn tại | Annotation processor chưa chạy |
| Employee_ dùng javax thay jakarta | Dependency/generator namespace mismatch |

### Không nuốt IllegalArgumentException rồi coi attribute là null

Nếu một attribute bắt buộc phải có trong mapping, việc mất nó có thể là lỗi cấu hình quan trọng. Hãy đưa ra thông báo kèm entity class và attribute name để sửa đúng nguồn.

## 63. Metamodel và performance

Đọc metadata không tương đương đọc DB row, nhưng cũng không nên:

- Rebuild/reflection-heavy report ở mọi HTTP request nếu output giống nhau.
- Duyệt toàn bộ getEntities/getAttributes cho mỗi điều kiện filter đơn giản.
- Expose metadata qua endpoint không giới hạn hoặc không authorize.

### Hướng tối ưu

Với dynamic filter/reporting framework, có thể xây một **metadata registry immutable** từ Metamodel khi khởi động:

~~~text
Startup:
  Metamodel -> allowed filter attributes
             -> Java types
             -> association metadata
             -> immutable registry

Request:
  Lookup registry -> validate request -> build Criteria query
~~~

Nhưng nếu model có tenant-specific rules, registry phải chỉ chứa thông tin **mapping**, còn authorization cần kiểm tra từng request.

### Không cần cache lại EntityManager

Giữ reference đến EntityManager để phục vụ metadata registry là sai lifecycle. Registry có thể giữ `EntityManagerFactory` hoặc immutable metadata descriptions phù hợp, nhưng request-specific EntityManager vẫn phải quản lý riêng.

## 64. API documentation từ Metamodel không phải OpenAPI tự động

Một công cụ có thể xem:

~~~text
Employee.employeeCode -> String BASIC
Employee.department -> Department MANY_TO_ONE
~~~

rồi tạo field descriptors. Nhưng không nên tự công bố API nhận tất cả fields của entity vì:

- Entity chứa internal fields (id/version/tenant).
- Associations có thể tạo N+1, cycles khi JSON serialize.
- Có fields không cho người dùng sửa.
- Một API có business-level names khác mapping names.
- Nullability của Java mapping không đủ diễn tả request validation.

### Đúng vai trò

Metamodel làm **nguồn metadata kỹ thuật để hỗ trợ developer tooling**; OpenAPI/request DTO/authorization/validation contract phải được thiết kế riêng.

## 65. Metamodel trong ứng dụng dùng Spring Data JPA

Nếu dùng Spring:

~~~java
@Component
public class MappingCatalog {

    private final EntityManagerFactory emf;

    public MappingCatalog(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public List<String> getEntityNames() {
        return emf.getMetamodel()
            .getEntities()
            .stream()
            .map(EntityType::getName)
            .sorted()
            .toList();
    }
}
~~~

### Không phải repository method

`EntityManagerFactory.getMetamodel()` không cần khai báo một Spring Data repository cho từng entity. Tầng infrastructure có thể truy cập mapping metadata trực tiếp.

### @Transactional có cần thiết không?

Không cần annotation transaction chỉ để đọc entity names. Nếu component đồng thời chạy Criteria query lấy **data rows**, operation ấy có transaction boundary theo use case.

### Generated metamodel

Spring Data có thể cung cấp abstractions query/specification; static metamodel là một cách xây Criteria typed paths nhưng không bắt buộc. Việc sử dụng phải phù hợp coding style của dự án.

## 66. So sánh Metamodel với reflection

Reflection:

~~~java
for (Field field : Employee.class.getDeclaredFields()) {
    System.out.println(field.getName());
}
~~~

có thể in:

~~~text
employeeCode
fullName
department
address
skills
labels
displayText
~~~

Nhưng:

- Không tự include inherited mapped properties như `id`.
- Có thể include `@Transient` hoặc Java fields không persistent.
- Không tự phân biệt ManyToOne và ElementCollection đúng khi mapping qua getters/XML.
- Không phản ánh một cách portable mọi provider mapping overrides.

Metamodel:

~~~java
employeeType.getAttributes();
~~~

nhắm tới **persistent attributes của model JPA đã bootstrap**.

### Có lúc reflection vẫn cần?

Có, nếu công cụ muốn đọc:

- Java method annotations ngoài JPA.
- Source-level/documentation annotations.
- Fields không persistent.

Nhưng đừng dùng reflection thuần thay Metamodel khi câu hỏi thực sự là “provider đã map attribute nào?”.

## 67. Có nên tạo một generic CRUD từ Metamodel?

Về kỹ thuật có thể:

1. Duyệt entity types.
2. Đọc attributes.
3. Sinh form fields.
4. Dựng dynamic Criteria queries.
5. Thực hiện persist/merge/remove.

Nhưng về nghiệp vụ, rủi ro cao:

- `@Id`, `@Version`, tenant IDs không nên được sửa tùy ý.
- Associations cần ownership/cascade/invariant rõ.
- Unique constraints/permission không hiển thị đầy đủ trong metamodel.
- Các lifecycle callbacks có side effects.
- Một update cần domain method, không phải reflection setter.
- Xóa có thể bị FK/retention policy.

### Lựa chọn an toàn

Chỉ dùng Metamodel để **xây admin tooling nội bộ có allowlist, authorization, validation và service commands rõ**, không tạo một API CRUD công khai “bất cứ entity nào, bất cứ field nào” chỉ vì metamodel liệt kê được chúng.

## 68. Case study: kiểm tra mô hình trước khi chạy một filter API

Yêu cầu:

> Chỉ cho phép filter Employee theo employeeCode, fullName và department.code.

Thiết kế metadata:

~~~text
Public filters:
  employeeCode      String       BASIC
  fullName          String       BASIC
  departmentCode    String       MANY_TO_ONE -> Department.code

Internal/not allowed:
  id
  version
  createdAt
  skills
  labels
~~~

Metamodel giúp xác nhận:

- `employeeCode` và `fullName` là attributes tồn tại.
- `department` là association tới Department.
- `Department.code` là String.

Nhưng API contract vẫn ánh xạ:

~~~text
public departmentCode
    -> Employee.department.code
~~~

theo một **explicit mapping**, không để người dùng truyền arbitrary path `department.employees.department...`.

### Hạn chế độ sâu

Nếu API cho phép dynamic nested paths không giới hạn, người dùng có thể tạo joins phức tạp, query rất chậm hoặc chạm dữ liệu không thuộc quyền. Giới hạn:

- Allowed fields.
- Allowed operators.
- Max join depth.
- Max page size.
- Tenant predicates.
- Query timeout/response size.

Metamodel là một công cụ kiểm tra cấu trúc cho các policy này.

## 69. Một bài tập tự xây metamodel explorer

Yêu cầu console tool:

~~~text
Input: EntityManagerFactory
Output:
  ENTITY/EMBEDDABLE/MAPPED_SUPERCLASS
  Java type
  Attribute name
  Attribute Java type
  PersistentAttributeType
  isAssociation / isCollection
  ID/version flags
  Collection element and map key types
~~~

Các bước:

1. Lấy `emf.getMetamodel()`.
2. Duyệt `getManagedTypes()` và sắp xếp theo Java class name.
3. Với mỗi `ManagedType<?>`, duyệt `getAttributes()`.
4. Ghi `getPersistentAttributeType()`, `getJavaType()`.
5. Nếu `instanceof SingularAttribute`, in optional/ID/version.
6. Nếu `instanceof PluralAttribute`, in collection type/element type.
7. Nếu `instanceof MapAttribute`, in key type.
8. Với IdentifiableType, khám phá parent/ID/version.
9. Tránh suy physical columns từ Java property names.
10. Chỉ chạy tool trong môi trường quyền nội bộ.

### Output mẫu

~~~text
ENTITY com.example.hr.domain.Employee
  id: Long / BASIC / id=true
  version: Long / BASIC / version=true
  employeeCode: String / BASIC
  department: Department / MANY_TO_ONE / association=true
  address: Address / EMBEDDED
  skills: Set / ELEMENT_COLLECTION / element=String
  labels: Map / ELEMENT_COLLECTION / key=String / value=String

EMBEDDABLE com.example.hr.domain.Address
  city: String / BASIC
  street: String / BASIC
  postalCode: String / BASIC
~~~

Một explorer như vậy là ví dụ tốt về **khám phá ánh xạ**, không cần chạm bản ghi của nhân viên.

## 70. Bài tập thực hành

### Bài 1 — Định nghĩa

JPA Metamodel mô tả điều gì?

**Gợi ý:** managed entity/embeddable/mapped-superclass types và persistent attributes của mapping đã được provider nhận diện.

### Bài 2 — Entry point

Viết API lấy metamodel từ EntityManagerFactory.

**Gợi ý:** `emf.getMetamodel()`.

### Bài 3 — EntityManager

`em.getMetamodel()` có khác với một SELECT tất cả rows không?

**Gợi ý:** có; đây là truy xuất mapping metadata.

### Bài 4 — getEntities vs getManagedTypes

Tại sao `getManagedTypes()` có thể chứa nhiều loại Java classes hơn `getEntities()`?

**Gợi ý:** bao gồm `@Embeddable` và `@MappedSuperclass`.

### Bài 5 — @MappedSuperclass

AuditedEntity có id/version được kế thừa. Nó có phải entity query độc lập không?

**Gợi ý:** không; nó cung cấp mapping cho subclasses.

### Bài 6 — getAttributes

Employee khai báo employeeCode nhưng kế thừa id. Method nào trả cả hai?

**Gợi ý:** `employeeType.getAttributes()`.

### Bài 7 — getDeclaredAttributes

Method nào bỏ inherited id khi chỉ liệt kê Employee-declared mappings?

**Gợi ý:** `getDeclaredAttributes()`.

### Bài 8 — Attribute lookup

Vì sao `getAttribute("employee_code")` lỗi khi field mapping là `employeeCode` và SQL column là employee_code?

**Gợi ý:** JPA metamodel dùng Java persistent attribute names.

### Bài 9 — Transient

Field `@Transient displayText` có xuất hiện ở persistent metamodel không?

**Gợi ý:** không.

### Bài 10 — Association

`@ManyToOne Department department` có `getPersistentAttributeType()` nào?

**Gợi ý:** `MANY_TO_ONE`.

### Bài 11 — Embedded

`@Embedded Address address` là ENTITY hay EMBEDDED?

**Gợi ý:** `Attribute.PersistentAttributeType.EMBEDDED`; Address là `EmbeddableType`.

### Bài 12 — Element collection

`Set<String> skills` map bằng @ElementCollection có phải entity association không?

**Gợi ý:** không; nó là collection của basic elements.

### Bài 13 — isCollection

Vì sao `@OneToMany List<Employee> employees` có cả `isAssociation()=true` và `isCollection()=true`?

**Gợi ý:** collection-valued entity relationship.

### Bài 14 — MapAttribute

Lấy Java type của map key bằng API nào?

**Gợi ý:** `mapAttribute.getKeyJavaType()`.

### Bài 15 — Plural element

Lấy Java type của element trong SetAttribute bằng gì?

**Gợi ý:** `getElementType().getJavaType()`.

### Bài 16 — JavaMember

`getJavaMember()` có chắc luôn là Field không?

**Gợi ý:** không; với property access có thể là Method.

### Bài 17 — isId

Kiểm tra một SingularAttribute có là ID không bằng method nào?

**Gợi ý:** `isId()`.

### Bài 18 — @Version

Kiểm tra EntityType có version mapping không?

**Gợi ý:** `hasVersionAttribute()`.

### Bài 19 — Composite key

`@EmbeddedId` có thể được xem là một singular attribute kiểu nào?

**Gợi ý:** kiểu embeddable ID.

### Bài 20 — IdClass

Với entity nhiều ID attributes, vì sao `getId(Long.class)` không phải cách tổng quát?

**Gợi ý:** phải dùng API cho multi-attribute ID như `getIdClassAttributes()`.

### Bài 21 — Entity name

`@Entity(name="StaffMember")` và `@Table(name="employees")` cho tên gì khác nhau?

**Gợi ý:** tên entity logic JPQL khác bảng SQL vật lý.

### Bài 22 — Static metamodel

`Employee_.employeeCode` giúp phát hiện loại lỗi gì lúc compile?

**Gợi ý:** property được rename/xóa hoặc dùng kiểu path không phù hợp.

### Bài 23 — Annotation processing

Nếu project không sinh `Employee_`, cần xem phần build nào?

**Gợi ý:** annotation processor tương thích JPA/Jakarta provider và generated source configuration.

### Bài 24 — Jakarta migration

`javax.persistence.metamodel.SingularAttribute` có dùng thay trực tiếp `jakarta.persistence.metamodel.SingularAttribute` không?

**Gợi ý:** không phải cùng Java type.

### Bài 25 — Criteria

Viết Criteria path lấy Employee.department.code bằng static metamodel.

**Gợi ý:** join `Employee_.department` rồi get `Department_.code`.

### Bài 26 — Embedded path

Vì sao `root.get(Employee_.address).get(Address_.city)` không nhất thiết tạo JOIN bảng Address?

**Gợi ý:** Address là embeddable value object.

### Bài 27 — Query JOIN

Khi JOIN Department.employees, `ListAttribute` có vai trò gì?

**Gợi ý:** cung cấp typed plural mapping cho Criteria ListJoin.

### Bài 28 — Map join

`MapJoin.key()` và `MapJoin.value()` biểu diễn điều gì?

**Gợi ý:** đường biểu thức key/value trong Criteria query.

### Bài 29 — Dynamic filter

User gửi `sortBy=version`, nhưng API chỉ cho phép sort employeeCode. Có nên cho phép chỉ vì version có trong Metamodel không?

**Gợi ý:** không; phải có allowlist và authorization riêng.

### Bài 30 — Type validation

Vì sao không nên dùng LIKE trên một Long attribute mà không kiểm tra Java type?

**Gợi ý:** operator phải phù hợp attribute type.

### Bài 31 — SQL column

Có API JPA chuẩn `EntityType.getPhysicalTableName()` không?

**Gợi ý:** không.

### Bài 32 — Schema drift

Metamodel nói employeeCode không nullable. Có chứng minh DB cột hiện tại có NOT NULL constraint không?

**Gợi ý:** không; kiểm tra physical schema/migrations.

### Bài 33 — AttributeOverride

Hai embedded Address dùng `home_city` và `work_city`. Vì sao một `EmbeddableType<Address>` không đủ nói mỗi path dùng cột nào?

**Gợi ý:** mapping overrides phụ thuộc chỗ nhúng.

### Bài 34 — Inheritance

JPA inheritance SINGLE_TABLE và JOINED có thể có logical entity hierarchy giống nhau nhưng physical schema khác nhau không?

**Gợi ý:** có.

### Bài 35 — Reflection

Vì sao chỉ duyệt `Employee.class.getDeclaredFields()` có thể thiếu ID inherited và in thêm @Transient?

**Gợi ý:** reflection fields khác JPA persistent model.

### Bài 36 — Startup policy

Muốn bảo đảm tất cả aggregate roots quan trọng có version, cần dùng API nào và còn giới hạn gì?

**Gợi ý:** `EntityType.hasVersionAttribute()`; không chứng minh mọi native writers tuân thủ.

### Bài 37 — Test mapping

Một mock Metamodel trả employeeCode là String. Đã chứng minh JPA provider nhận diện mapping thật chưa?

**Gợi ý:** chưa; integration test với EntityManagerFactory thật.

### Bài 38 — Thứ tự Set

Có nên assert `getAttributes()` trả đúng thứ tự khai báo fields không?

**Gợi ý:** không; sort output nếu cần ổn định.

### Bài 39 — Multi-tenancy

Metamodel có thay authorization/tenant filter của query không?

**Gợi ý:** không.

### Bài 40 — Tooling

Một admin tool cho phép sửa bất cứ entity property nào dựa trên Metamodel. Nguy cơ gì?

**Gợi ý:** over-posting, bỏ domain methods, thiếu tenant/ACL, concurrency và association rules.

## 71. Bảng ghi nhớ nhanh

| Khái niệm/API | Ý nghĩa |
| --- | --- |
| `EntityManagerFactory.getMetamodel()` | Lấy JPA runtime mapping metadata |
| `EntityManager.getMetamodel()` | Lấy metamodel từ EM |
| `Metamodel.getEntities()` | Tập entity types |
| `Metamodel.getEmbeddables()` | Tập embeddable types |
| `Metamodel.getManagedTypes()` | Tất cả managed types |
| `Metamodel.entity(Employee.class)` | Lấy metadata entity cụ thể |
| `Metamodel.embeddable(Address.class)` | Lấy metadata embeddable |
| `Metamodel.managedType(Class)` | Lấy managed type |
| `EntityType.getName()` | Tên entity logic, không phải physical table |
| `ManagedType.getAttributes()` | Persistent attrs gồm inherited |
| `getDeclaredAttributes()` | Chỉ attrs khai báo tại type |
| `getAttribute("name")` | Lookup persistent attribute theo Java name |
| `Attribute.getJavaType()` | Java type của attribute |
| `Attribute.getJavaMember()` | Mapped Field/Method |
| `Attribute.getPersistentAttributeType()` | BASIC/EMBEDDED/relationship/... |
| `isAssociation()` | Có phải entity association mapping |
| `isCollection()` | Có phải collection-valued attribute |
| `SingularAttribute<X,Y>` | Singular typed attribute |
| `SingularAttribute.isId()/isVersion()` | ID/version flags |
| `PluralAttribute<X,C,E>` | Collection-valued metadata |
| `getElementType()` | Kiểu element |
| `getCollectionType()` | COLLECTION/SET/LIST/MAP |
| `MapAttribute.getKeyJavaType()` | Java type của map key |
| `IdentifiableType.hasSingleIdAttribute()` | Kiểm tra ID đơn |
| `getIdClassAttributes()` | ID attributes cho @IdClass phù hợp |
| `IdentifiableType.hasVersionAttribute()` | Có version mapping |
| `IdentifiableType.getSupertype()` | Identifiable superclass mapping |
| `@StaticMetamodel` | Static metamodel class annotation |
| `Employee_` | Generated typed attributes cho Criteria |
| Runtime metamodel | Khám phá mapping lúc chạy |
| Static metamodel | Type-safe Criteria paths lúc compile |
| `@Transient` field | Không thuộc JPA persistent attributes |
| @Embedded | Value object, không entity độc lập |
| @MappedSuperclass | Mapping inheritance, không entity độc lập |
| SQL schema/DDL | Không được mô tả đầy đủ bởi Metamodel chuẩn |
| Dynamic filter | Cần allowlist và authorization |
| Metamodel tests | Cần provider bootstrap thật |

## Kết luận

**JPA Metamodel là một giao diện chuẩn để khám phá mô hình ánh xạ đã được persistence provider nhận diện.** Qua `EntityManagerFactory.getMetamodel()`, ứng dụng có thể liệt kê entities, mapped superclasses, embeddables, persistent attributes, Java types, relationship kinds, collection element/key types và ID/version metadata. Các API `getAttributes()`, `getDeclaredAttributes()`, `getSingularAttribute()`, `getPluralAttributes()`, `getId()` và `hasVersionAttribute()` giúp hiểu cấu trúc model mà không cần quét Java fields bằng reflection rồi tự đoán mapping.

**Runtime metamodel** thích hợp cho inspection, reporting và kiểm tra policy lúc chạy. **Static canonical metamodel** với những lớp sinh ra như `Employee_` thích hợp cho Criteria API typed paths, giảm lỗi chính tả property names và hỗ trợ refactoring khi compile. Chúng không thay thế nhau: một bên trả metadata động từ persistence unit, một bên sinh Java symbols để compiler kiểm tra.

Điều quan trọng nhất là **phân biệt logical JPA mapping với physical database schema**. Metamodel chuẩn không cho biết đầy đủ tên bảng/cột thực tế, indexes, triggers, constraints hoặc migration state. Khi cần kiểm chứng DDL, phải phối hợp provider mapping metadata, JDBC/database catalogs và schema migrations. Khi dựng filter/sort động, phải kết hợp metamodel với allowlist, tenant authorization, limits và query design; một attribute tồn tại trong model không có nghĩa client được phép đọc hoặc sửa nó.

Với một mô hình domain rõ ràng, cách tiếp cận thực tế là **dùng Metamodel để khám phá và kiểm tra mapping, dùng static metamodel cho Criteria có kiểu, dùng database tools để xác minh lược đồ vật lý và dùng transaction/constraints để bảo vệ dữ liệu thực**. Đó là ranh giới giúp công cụ siêu dữ liệu hữu ích mà không bị nhầm thành một hệ thống quản trị schema hoặc bảo mật ứng dụng.
