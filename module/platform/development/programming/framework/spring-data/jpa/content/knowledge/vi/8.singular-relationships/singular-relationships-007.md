# optional, nullable, khóa ngoại và ràng buộc duy nhất trong Spring Data JPA

Trong quan hệ đơn của JPA, bốn khái niệm **optional**, **nullable**, **foreign key (khóa ngoại)** và **unique constraint (ràng buộc duy nhất)** có liên quan nhưng giải quyết các vấn đề khác nhau. Hiểu đúng từng khái niệm giúp mô hình Java phản ánh đúng cardinality của domain, database bảo vệ tính toàn vẹn dữ liệu và ứng dụng xử lý được cả trường hợp thiếu quan hệ lẫn dữ liệu trùng.

Tài liệu dùng Jakarta Persistence với namespace `jakarta.persistence` (Spring Boot 3 / Spring Framework 6 trở lên). Dự án cũ dùng JPA 2 và Spring Boot 2 thường dùng `javax.persistence`; không trộn hai namespace trong cùng một ứng dụng.

## 1. Phân biệt bốn khái niệm

| Khái niệm | Nằm ở đâu | Trả lời câu hỏi | Ví dụ |
|---|---|---|---|
| `optional` | Mapping quan hệ JPA | Quan hệ có được phép không tồn tại không? | Một nhân viên có thể chưa có phòng ban |
| `nullable` | Cột database được ánh xạ bởi `@JoinColumn` | Cột khóa ngoại có được phép chứa SQL NULL không? | `department_id` có thể NULL |
| Foreign key | Schema database | Giá trị khóa ngoại có tham chiếu tới một hàng hợp lệ không? | `employee.department_id` phải trỏ tới `department.id` |
| Unique constraint | Schema database | Giá trị khóa ngoại có bị trùng giữa các hàng không? | Một hồ sơ chỉ được gắn với tối đa một nhân viên |

Có thể ghi nhớ:

- `optional` diễn tả tính bắt buộc của association trong mô hình JPA.
- `nullable` diễn tả khả năng lưu SQL NULL trong cột join.
- Foreign key ngăn tham chiếu tới hàng không tồn tại.
- Unique constraint ngăn nhiều hàng sở hữu cùng một giá trị khóa ngoại.

Một quan hệ có thể nullable nhưng vẫn có foreign key: cột được phép là NULL, còn khi có giá trị thì giá trị đó phải tham chiếu tới hàng tồn tại. Một quan hệ one-to-one thường cần thêm unique constraint để database bảo vệ tính duy nhất của đầu tham chiếu.

## 2. Quan hệ đơn và phía sở hữu khóa ngoại

Trong quan hệ đơn, một entity tham chiếu tới một entity khác bằng một association. Ví dụ:

- Một nhân viên có thể thuộc một phòng ban.
- Một nhân viên có thể có một hồ sơ cá nhân.
- Một tài khoản có thể có một người quản lý.

Trong quan hệ relational, liên kết thường được lưu bằng một cột foreign key ở một bảng. Entity sở hữu cột này là **owning side** của association. Với `@ManyToOne` và `@OneToOne` dùng `@JoinColumn`, phía có `@JoinColumn` thường là owning side.

Ví dụ bảng:

```sql
create table department (
    id bigint primary key,
    name varchar(150) not null
);

create table employee (
    id bigint primary key,
    name varchar(150) not null,
    department_id bigint null,
    constraint fk_employee_department
        foreign key (department_id) references department(id)
);
```

Cột `employee.department_id` nằm ở bảng employee, do đó entity Employee sở hữu quan hệ tới Department. Nhiều nhân viên có thể có cùng department_id; đó là quan hệ many-to-one. Khi department_id là NULL, nhân viên chưa được gắn phòng ban. Khi department_id có giá trị, foreign key yêu cầu phòng ban tương ứng phải tồn tại.

## 3. optional trong JPA

Thuộc tính `optional` của `@ManyToOne` và `@OneToOne` mô tả association có được phép không tồn tại hay không.

- `optional = true`: association có thể không được thiết lập; giá trị tham chiếu trong entity có thể là `null`.
- `optional = false`: association là bắt buộc; entity cần có một đối tượng liên quan hợp lệ.

Mặc định của `optional` trên các annotation quan hệ này là `true`.

Ví dụ association tùy chọn:

```java
@Entity
@Table(name = "employee")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "department_id", nullable = true)
    private Department department;
}
```

Employee có thể tồn tại mà chưa có Department. Trong Java, `employee.getDepartment()` có thể trả về `null`. Khi lưu xuống database, `department_id` có thể nhận SQL NULL.

Ví dụ association bắt buộc:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

Với mapping này, một Employee phải có Department. Nếu ứng dụng tạo Employee mà không thiết lập department, dữ liệu không đáp ứng mô hình. Tùy provider và thời điểm flush, lỗi có thể được phát hiện trước khi ghi hoặc khi database thực thi NOT NULL/foreign key constraint.

### 3.1. optional không phải là cascade

`optional` không quyết định entity liên quan được persist, merge hay remove tự động. Đó là nhiệm vụ của cascade:

- `CascadeType.PERSIST`: lan truyền persist.
- `CascadeType.MERGE`: lan truyền merge.
- `CascadeType.REMOVE`: lan truyền remove.
- `CascadeType.ALL`: gồm các thao tác cascade tương ứng.

Một association có thể optional nhưng không cascade. Ví dụ Employee tham chiếu tới Department đã tồn tại; lưu Employee không nên tự động tạo hoặc xóa Department.

### 3.2. optional không phải fetch type

`optional` cũng không quyết định quan hệ được tải lazy hay eager:

- `optional` nói quan hệ có bắt buộc không.
- `fetch` nói chiến lược tải association.

Hai thuộc tính này độc lập. Ví dụ `@ManyToOne(fetch = FetchType.LAZY, optional = true)` là quan hệ tùy chọn và được yêu cầu tải lazy. JPA quy định mặc định fetch của ManyToOne là EAGER, còn OneToOne cũng mặc định EAGER. LAZY với một số kiểu quan hệ là yêu cầu/hint và khả năng thực thi còn phụ thuộc provider, proxy hoặc bytecode enhancement.

## 4. nullable và @JoinColumn

`@JoinColumn` mô tả cột dùng để nối tới bảng liên quan. Một số thuộc tính thường dùng:

- `name`: tên cột foreign key trong bảng hiện tại.
- `referencedColumnName`: cột ở bảng đích được tham chiếu; nếu bỏ qua, thường tham chiếu primary key.
- `nullable`: cột có cho phép SQL NULL không; mặc định `true`.
- `unique`: yêu cầu unique constraint đơn cột khi tạo schema; mặc định `false`.
- `insertable`, `updatable`: cột có tham gia INSERT/UPDATE do provider tạo hay không.
- `foreignKey`: cấu hình metadata cho foreign key được tạo bởi schema generation.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(
    name = "department_id",
    nullable = true,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

Ở đây `nullable = true` cho phép cột department_id lưu NULL. Nó không cho phép một ID bất kỳ không tồn tại trong bảng department. Nếu department_id là 999 nhưng không có department.id = 999, foreign key vẫn từ chối thao tác ghi.

### 4.1. optional và nullable nên đồng bộ

Với association bắt buộc, cấu hình thường dùng:

```java
@ManyToOne(optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

Với association tùy chọn:

```java
@ManyToOne(optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
```

Không nên khai báo `optional = false` nhưng `nullable = true`, hoặc `optional = true` nhưng `nullable = false`, nếu không có lý do rất cụ thể. Hai thuộc tính mô tả cùng một quy tắc ở hai lớp khác nhau; cấu hình mâu thuẫn có thể khiến provider, validation và database thể hiện hành vi không thống nhất.

### 4.2. nullable không đồng nghĩa với @NotNull

`nullable` là metadata về cột trong mapping và schema generation. `@NotNull` là constraint của Bean Validation. Database NOT NULL là constraint được lưu trong schema và được database thực thi.

```java
@NotNull
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

Ba lớp có mục đích khác nhau:

1. JPA mapping diễn tả quan hệ bắt buộc.
2. Bean Validation có thể phát hiện giá trị null trước khi thao tác database, nếu validation được bật và lifecycle event tương ứng được kích hoạt.
3. Database NOT NULL bảo vệ dữ liệu bất kể ứng dụng nào ghi vào database.

Nếu chỉ dùng Bean Validation mà database không có NOT NULL, một ứng dụng khác hoặc câu SQL trực tiếp vẫn có thể lưu NULL. Nếu chỉ có NOT NULL ở database, lỗi thường xuất hiện muộn hơn tại flush/commit. Với dữ liệu quan trọng, hãy giữ mapping và database constraint nhất quán.

## 5. Foreign key: bảo vệ tính toàn vẹn tham chiếu

Foreign key đảm bảo giá trị ở cột tham chiếu phải tồn tại trong cột được tham chiếu của bảng đích. Nó ngăn dữ liệu mồ côi (orphan reference) như Employee trỏ tới Department đã bị xóa hoặc chưa từng tồn tại.

Ví dụ:

```sql
alter table employee
add constraint fk_employee_department
foreign key (department_id)
references department(id);
```

Foreign key có thể đi cùng cột nullable:

- `department_id = NULL`: không có association; được chấp nhận nếu cột nullable.
- `department_id = 10` và Department 10 tồn tại: được chấp nhận.
- `department_id = 999` nhưng Department 999 không tồn tại: bị từ chối.
- Xóa Department đang được Employee tham chiếu: bị từ chối theo hành vi mặc định nếu chưa cấu hình chính sách xóa phù hợp.

### 5.1. Khai báo foreign key trong JPA

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(
    name = "department_id",
    nullable = true,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

Tên constraint giúp database schema dễ đọc và thuận tiện khi migration. Annotation `@ForeignKey` mô tả constraint cho schema generation. Nếu schema đã được tạo bằng Flyway/Liquibase hoặc công cụ DBA, cần tạo foreign key thật trong database; chỉ có annotation trong code không tự sửa schema đang chạy.

`ConstraintMode.NO_CONSTRAINT` có thể yêu cầu provider không sinh foreign key trong DDL. Không nên dùng để che lỗi dữ liệu hoặc bỏ qua tính toàn vẹn tham chiếu nếu hệ thống cần bảo vệ referential integrity.

### 5.2. Foreign key không tự tạo tính duy nhất

Với quan hệ many-to-one, nhiều hàng employee được phép trỏ cùng một department. Foreign key chỉ bảo đảm department được tham chiếu tồn tại.

Nếu muốn mỗi nhân viên có một badge riêng và một badge không được gán cho nhiều nhân viên, chỉ có foreign key là chưa đủ; cần unique constraint trên badge_id. Đây là khác biệt quan trọng giữa many-to-one và one-to-one.

### 5.3. Chính sách khi xóa hàng được tham chiếu

Database hỗ trợ các hành vi như:

- `RESTRICT` hoặc `NO ACTION`: không cho xóa hàng cha khi vẫn có hàng con tham chiếu.
- `ON DELETE CASCADE`: xóa các hàng con tham chiếu.
- `ON DELETE SET NULL`: đặt cột foreign key ở hàng con thành NULL khi hàng cha bị xóa; cột phải nullable.
- `ON DELETE SET DEFAULT`: đặt về giá trị mặc định nếu database và schema hỗ trợ.

Các hành vi này thuộc constraint của database. Chúng khác với JPA cascade:

- `CascadeType.REMOVE` yêu cầu JPA lan truyền thao tác remove qua object graph.
- `orphanRemoval = true` yêu cầu xóa child khi child bị loại khỏi quan hệ được quản lý.
- `ON DELETE CASCADE` là hành vi database khi xóa hàng được tham chiếu.

Không coi ba cơ chế này là tương đương. Nếu database tự xóa hàng con, persistence context đang mở có thể giữ entity state cũ nếu provider không biết thao tác xóa đã xảy ra. Hãy chọn một chính sách rõ ràng, kiểm thử cùng database thực tế và tránh để ORM/database thực hiện các hành vi xung đột.

## 6. Unique constraint và quan hệ one-to-one

Unique constraint ngăn nhiều hàng có cùng giá trị trên một cột hoặc một tổ hợp cột. Với quan hệ one-to-one dùng foreign key, unique constraint trên FK bảo đảm mỗi hàng đích được tham chiếu tối đa bởi một hàng nguồn.

Ví dụ một Employee có thể có Profile, và một Profile chỉ thuộc về tối đa một Employee:

```sql
create table profile (
    id bigint primary key,
    display_name varchar(150) not null
);

create table employee_profile_link (
    id bigint primary key,
    profile_id bigint null,
    constraint fk_employee_profile
        foreign key (profile_id) references profile(id),
    constraint uk_employee_profile
        unique (profile_id)
);
```

Trong ví dụ này, `profile_id` vừa là foreign key vừa có unique constraint. Hai constraint bảo vệ hai quy tắc khác nhau:

- FK: profile được tham chiếu phải tồn tại.
- UNIQUE: một profile không thể được gắn vào hai hàng employee_profile_link.

Nếu không có UNIQUE, database vẫn có thể chấp nhận nhiều hàng cùng profile_id dù Java mapping khai báo OneToOne. Khi đó schema thực tế không bảo vệ cardinality one-to-one.

### 6.1. Khai báo OneToOne với unique FK

```java
@Entity
@Table(name = "employee")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        unique = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;
}
```

`unique = true` trên `@JoinColumn` là cách khai báo unique constraint đơn cột trong metadata schema generation. Nếu cần đặt tên constraint ổn định cho migration, có thể khai báo ở cấp bảng:

```java
@Entity
@Table(
    name = "employee",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_employee_profile",
            columnNames = "profile_id"
        )
    }
)
public class Employee {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;
}
```

Trong ví dụ thứ hai, unique constraint được khai báo ở `@Table`, nên không cần lặp `unique = true` trên `@JoinColumn`.

### 6.2. Owning side và mappedBy

Trong one-to-one hai chiều, chỉ một phía sở hữu foreign key. Phía còn lại khai báo `mappedBy` trỏ đến thuộc tính association của owning side:

```java
@Entity
public class Profile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
    private Employee employee;
}
```

Ở đây Employee sở hữu cột profile_id; Profile là inverse side. Việc thay đổi chỉ inverse side mà không cập nhật owning side có thể không ghi thay đổi FK như mong đợi. Khi association hai chiều, helper method nên cập nhật cả hai phía.

```java
public void assignProfile(Profile profile) {
    this.profile = profile;
    if (profile != null) {
        profile.setEmployee(this);
    }
}
```

Nếu bỏ association, helper method cũng nên đặt cả hai phía về null theo đúng mô hình. Nếu association là bắt buộc, thao tác bỏ liên kết cần được ngăn hoặc thay thế bằng một quy trình nghiệp vụ hợp lệ.

### 6.3. Optional one-to-one và nhiều giá trị NULL

Một one-to-one tùy chọn thường cần cho phép nhiều hàng Employee chưa có Profile. Khi đó profile_id là nullable và có unique constraint.

Tuy nhiên, cách database xử lý nhiều giá trị NULL trong unique constraint khác nhau theo hệ quản trị và loại index. Nhiều database cho phép nhiều NULL trong unique column; một số cấu hình/engine có cách xử lý khác. Không giả định rằng hành vi của một database sẽ giống database khác. Hãy xác nhận bằng integration test trên đúng engine production.

Nếu database không cho phép nhiều NULL trong unique index nhưng nghiệp vụ cần nhiều nhân viên chưa có profile, có thể dùng filtered/partial unique index chỉ áp dụng cho các giá trị khác NULL nếu database hỗ trợ. Ví dụ cú pháp partial index của PostgreSQL:

```sql
create unique index uk_employee_profile_not_null
on employee(profile_id)
where profile_id is not null;
```

Đây là DDL đặc thù database; không phải annotation JPA portable.

## 7. ManyToOne, OneToOne và cardinality

| Mapping | FK nằm ở đâu | Unique trên FK? | Ý nghĩa |
|---|---|---|---|
| `@ManyToOne` | Bảng entity nguồn | Thường không | Nhiều hàng nguồn có thể tham chiếu một hàng đích |
| `@OneToOne` với `@JoinColumn` | Bảng owning side | Cần có | Mỗi hàng nguồn tham chiếu tối đa một hàng đích và ngược lại theo FK |
| `@OneToOne` dùng shared primary key | PK của bảng phụ đồng thời là FK | PK vốn đã unique | Một hàng phụ ứng với tối đa một hàng chính |
| `@OneToMany` hai chiều | Thường FK ở bảng child | Không | Một parent có nhiều child; child thường thuộc một parent |

Ví dụ ManyToOne:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "manager_id", nullable = true)
private Employee manager;
```

Nhiều nhân viên có thể cùng một manager. Nếu đặt unique constraint lên manager_id, mỗi manager chỉ được tham chiếu bởi tối đa một nhân viên, làm thay đổi cardinality thực tế và có thể khiến dữ liệu hợp lệ bị từ chối.

Ví dụ OneToOne với shared primary key:

```java
@Entity
public class EmployeeDetails {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Employee employee;
}
```

Trong mô hình này, EmployeeDetails.id vừa là primary key vừa là foreign key tới Employee.id. Do primary key không thể NULL và vốn unique, quan hệ phụ thuộc là bắt buộc đối với mỗi hàng EmployeeDetails. Nếu Employee không có hàng EmployeeDetails, sự vắng mặt được biểu diễn bằng việc không có hàng ở bảng phụ, không phải một hàng với id NULL.

## 8. Unique constraint cho cột đơn và nhiều cột

Unique constraint không chỉ áp dụng cho foreign key. Nó còn dùng để bảo vệ business key như email, mã nhân viên hoặc cặp tenant/email.

Unique một cột:

```java
@Entity
@Table(
    name = "account",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_account_email",
        columnNames = "email"
    )
)
public class Account {
    @Id
    private Long id;

    @Column(name = "email", nullable = false)
    private String email;
}
```

Unique nhiều cột:

```java
@Entity
@Table(
    name = "tenant_user",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_tenant_user_email",
        columnNames = {"tenant_id", "email"}
    )
)
public class TenantUser {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false)
    private String email;
}
```

Constraint tổ hợp bảo đảm cùng một email có thể xuất hiện ở hai tenant khác nhau, nhưng không thể trùng trong cùng tenant. Nếu muốn email unique toàn hệ thống, chỉ cần unique trên email. Chọn constraint theo đúng phạm vi duy nhất của nghiệp vụ.

`@Column(unique = true)` là shorthand cho unique constraint một cột khi tạo schema. `@Table(uniqueConstraints = ...)` hữu ích khi cần tên rõ ràng hoặc constraint nhiều cột. Đối với FK của association, có thể dùng `@JoinColumn(unique = true)` hoặc khai báo unique constraint ở `@Table`.

Unique constraint khác với kiểm tra tồn tại trước khi insert. Hai request đồng thời có thể cùng thấy email chưa tồn tại và cùng cố insert. Chỉ database unique constraint mới là chốt bảo vệ an toàn trước race condition.

## 9. Mapping JPA và database constraint: ai thực thi điều gì?

| Cơ chế | Vai trò | Có bảo vệ khi ghi SQL ngoài JPA không? |
|---|---|---|
| `optional = false` | Metadata quan hệ bắt buộc trong JPA | Không tự nó; phụ thuộc schema constraint thực tế |
| `nullable = false` | Metadata cột và DDL schema generation | Không tự nó nếu schema chưa có NOT NULL |
| `@NotNull` | Bean Validation ở lifecycle validation phù hợp | Không |
| NOT NULL | Database constraint | Có |
| `@ForeignKey` | Metadata để provider tạo FK | Không nếu FK thật không tồn tại |
| FOREIGN KEY | Database referential integrity | Có |
| `unique = true` / `@UniqueConstraint` | Metadata để tạo unique constraint | Không nếu constraint thật không tồn tại |
| UNIQUE | Database constraint | Có |

Điểm quan trọng: annotation không tự động sửa schema production nếu ứng dụng đang dùng migration có kiểm soát. Khi dùng `spring.jpa.hibernate.ddl-auto=validate`, Hibernate chủ yếu xác minh mapping tương thích schema theo khả năng provider; không coi nó là công cụ tạo hoặc sửa mọi constraint cần thiết. Hãy quản lý constraint bằng Flyway, Liquibase hoặc quy trình DDL của đội database.

## 10. Ví dụ thiết kế đầy đủ

Giả sử hệ thống có Department, Employee và Profile:

- Employee bắt buộc có tên.
- Employee có thể chưa được gán Department.
- Một Department có thể có nhiều Employee.
- Employee có thể chưa có Profile.
- Một Profile chỉ được gán cho tối đa một Employee.

Entity Department:

```java
@Entity
@Table(name = "department")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Department() {}

    public Department(String name) {
        this.name = name;
    }
}
```

Entity Profile:

```java
@Entity
@Table(name = "profile")
public class Profile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String displayName;

    protected Profile() {}

    public Profile(String displayName) {
        this.displayName = displayName;
    }
}
```

Entity Employee:

```java
@Entity
@Table(
    name = "employee",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_employee_profile",
        columnNames = "profile_id"
    )
)
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "department_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_department")
    )
    private Department department;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;

    protected Employee() {}

    public Employee(String name) {
        this.name = name;
    }

    public void assignDepartment(Department department) {
        this.department = department;
    }

    public void assignProfile(Profile profile) {
        this.profile = profile;
    }
}
```

Trong mapping này:

- department_id nullable và có FK, không unique. Nhiều Employee được phép dùng cùng Department; Employee có thể chưa có Department.
- profile_id nullable, có FK và unique. Employee có thể chưa có Profile; mỗi Profile chỉ được tham chiếu bởi tối đa một Employee.
- name NOT NULL. Database không cho lưu Employee thiếu tên.
- Hai association không cascade mặc định. Department/Profile phải tồn tại trước khi được tham chiếu, trừ khi ứng dụng chủ động cấu hình cascade phù hợp.

DDL tương ứng về ý nghĩa:

```sql
create table employee (
    id bigint generated by default as identity primary key,
    name varchar(150) not null,
    department_id bigint null,
    profile_id bigint null,
    constraint fk_employee_department
        foreign key (department_id) references department(id),
    constraint fk_employee_profile
        foreign key (profile_id) references profile(id),
    constraint uk_employee_profile
        unique (profile_id)
);
```

Cú pháp identity có thể khác theo database; đây là DDL minh họa. Hãy dùng cú pháp migration phù hợp với engine đang chạy.

## 11. Gán và bỏ association an toàn

Với association tùy chọn, code nghiệp vụ có thể cho phép gán hoặc bỏ liên kết:

```java
@Transactional
public void assignDepartment(Long employeeId, Long departmentId) {
    Employee employee = employeeRepository.findById(employeeId)
        .orElseThrow(() -> new EntityNotFoundException("Employee not found"));

    Department department = departmentRepository.findById(departmentId)
        .orElseThrow(() -> new EntityNotFoundException("Department not found"));

    employee.assignDepartment(department);
}
```

Nếu Employee đang managed trong transaction, dirty checking sẽ ghi FK khi flush/commit. Không nhất thiết phải gọi save thêm một lần. Nếu Employee detached, cần xử lý lại lifecycle phù hợp.

Bỏ association:

```java
@Transactional
public void unassignDepartment(Long employeeId) {
    Employee employee = employeeRepository.findById(employeeId)
        .orElseThrow(() -> new EntityNotFoundException("Employee not found"));

    employee.assignDepartment(null);
}
```

Đoạn này chỉ hợp lệ nếu association là optional và cột FK cho phép NULL. Nếu mapping là `optional = false` và database NOT NULL, việc bỏ liên kết sẽ vi phạm mô hình hoặc constraint. Nếu nghiệp vụ không cho phép bỏ, hãy từ chối thao tác ở service layer với lỗi nghiệp vụ dễ hiểu.

Với one-to-one unique FK, khi đổi Profile của Employee, hãy đảm bảo profile mới chưa được gán cho Employee khác. Có thể truy vấn để hiển thị lỗi thân thiện, nhưng vẫn phải dựa vào unique constraint ở database vì hai request đồng thời có thể vượt qua bước kiểm tra ứng dụng.

## 12. Migration khi thay đổi optionality hoặc constraint

Thay đổi association từ optional sang required là thay đổi dữ liệu và schema, không chỉ sửa annotation.

Một quy trình an toàn:

1. Kiểm kê số hàng đang có FK NULL.
2. Quyết định cách xử lý từng hàng thiếu liên kết: gán giá trị hợp lệ, tạo entity liên quan hoặc loại bỏ dữ liệu theo nghiệp vụ.
3. Deploy code có khả năng xử lý trạng thái chuyển tiếp nếu cần triển khai nhiều phiên bản.
4. Backfill các FK NULL.
5. Thêm hoặc xác nhận foreign key constraint.
6. Xác nhận không còn NULL rồi thêm NOT NULL.
7. Chuyển mapping JPA sang `optional = false` và `nullable = false`.
8. Kiểm thử ghi/đọc và rollback migration trong môi trường staging.

Ví dụ kiểm tra dữ liệu trước khi đổi thành bắt buộc:

```sql
select count(*) as missing_department
from employee
where department_id is null;
```

Nếu kết quả khác 0, không thể áp NOT NULL mà chưa xử lý dữ liệu.

Khi thêm unique constraint:

```sql
select profile_id, count(*) as usage_count
from employee
where profile_id is not null
group by profile_id
having count(*) > 1;
```

Trước khi thêm UNIQUE, phải xử lý các nhóm trùng theo quy tắc nghiệp vụ. Không tự ý xóa bản ghi hoặc chọn một bản ghi thắng nếu chưa xác định chính sách dữ liệu.

Một migration PostgreSQL minh họa cho cột FK tùy chọn có unique constraint:

```sql
alter table employee
    add column profile_id bigint null;

alter table employee
    add constraint fk_employee_profile
    foreign key (profile_id) references profile(id);

create unique index uk_employee_profile_not_null
    on employee(profile_id)
    where profile_id is not null;
```

Partial index trong ví dụ là cú pháp PostgreSQL. Nếu dùng MySQL, SQL Server, Oracle hoặc database khác, hãy kiểm tra cú pháp và quy tắc NULL/UNIQUE của engine. Migration nên được kiểm thử trên đúng loại database mà production sử dụng.

## 13. Kiểm thử các quy tắc association

Unit test kiểm tra service logic, nhưng foreign key, NOT NULL và UNIQUE cần được kiểm thử với database thật hoặc Testcontainers dùng đúng engine.

Ví dụ repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
    boolean existsByProfileId(Long profileId);
}
```

Ví dụ test lưu Employee không có Department và Profile:

```java
@DataJpaTest
class EmployeeAssociationTest {
    @Autowired
    private EmployeeRepository employeeRepository;

    @Test
    void allowsMissingOptionalAssociations() {
        Employee employee = new Employee("An");

        Employee saved = employeeRepository.saveAndFlush(employee);

        assertThat(saved.getId()).isNotNull();
        assertThat(saved.getDepartment()).isNull();
        assertThat(saved.getProfile()).isNull();
    }
}
```

Test unique nên tạo hai Employee cùng tham chiếu một Profile và xác nhận lần flush thứ hai bị database từ chối. Ví dụ khung:

```java
@Test
void rejectsProfileAssignedToTwoEmployees() {
    Profile profile = profileRepository.saveAndFlush(
        new Profile("An")
    );

    employeeRepository.saveAndFlush(employee("Employee A", profile));

    assertThatThrownBy(() ->
        employeeRepository.saveAndFlush(employee("Employee B", profile))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

Đây là ví dụ minh họa; cần có factory method `employee(...)`, repository và import tương ứng trong test class. Sau khi một transaction gặp constraint violation, transaction có thể bị đánh dấu rollback-only; nên tách test hoặc quản lý transaction cẩn thận để tránh test tiếp tục dùng transaction lỗi.

Các tình huống nên kiểm thử:

- Lưu association optional với FK NULL.
- Lưu association có FK hợp lệ.
- Từ chối FK trỏ tới hàng không tồn tại.
- Từ chối NULL khi association required.
- Từ chối hai hàng dùng cùng giá trị unique.
- Xóa hàng được tham chiếu theo đúng chính sách ON DELETE.
- Kiểm tra nhiều giá trị NULL trên unique nullable FK theo database thực tế.
- Kiểm tra race condition khi hai request đồng thời gán cùng Profile.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Có thể lưu entity với quan hệ NULL dù nghiệp vụ bắt buộc | Mapping vẫn optional hoặc database thiếu NOT NULL | Đồng bộ optional=false, nullable=false và migration NOT NULL |
| Lỗi FK khi insert/update | ID liên quan không tồn tại hoặc persist sai thứ tự | Load entity đích, kiểm tra cascade có chủ đích và xác nhận FK |
| OneToOne nhưng có nhiều hàng cùng FK | Database chưa có unique constraint | Thêm unique constraint/index và xử lý dữ liệu trùng |
| Không thể lưu nhiều hàng chưa có quan hệ one-to-one | Database unique index xử lý NULL theo cách không phù hợp | Dùng partial/filtered unique index nếu engine hỗ trợ |
| Annotation đã sửa nhưng database không đổi | Dùng migration/ddl-auto validate hoặc schema đã tồn tại | Viết migration DDL riêng và triển khai đúng thứ tự |
| Bỏ liên kết gây lỗi constraint | Cột FK NOT NULL hoặc association required | Kiểm tra nghiệp vụ; chỉ cho phép null khi quan hệ optional |
| Xóa entity đích bị từ chối | Hàng khác đang tham chiếu bằng FK | Chuyển liên kết, xóa hàng con theo nghiệp vụ hoặc chọn chính sách ON DELETE |
| Cascade xóa ngoài ý muốn | Dùng CascadeType.REMOVE/ALL không đúng ranh giới ownership | Chỉ cascade thao tác cần thiết; phân biệt JPA cascade và DB cascade |
| Hai request cùng gán một Profile | Chỉ kiểm tra exists trước khi lưu, thiếu unique constraint | Để database unique constraint làm lớp bảo vệ cuối cùng và xử lý lỗi vi phạm |

## 15. Checklist thiết kế

- [ ] Association có thực sự tùy chọn theo nghiệp vụ không?
- [ ] `optional` trên `@ManyToOne`/`@OneToOne` đã phản ánh đúng cardinality?
- [ ] `nullable` trên `@JoinColumn` có khớp với optionality?
- [ ] Cột FK có foreign key constraint thật trong database?
- [ ] One-to-one có unique constraint trên FK hoặc PK/FK shared key?
- [ ] Many-to-one có tránh unique constraint ngoài ý muốn?
- [ ] Unique constraint có đúng phạm vi business key và có tên ổn định?
- [ ] Database production xử lý nhiều NULL trong unique index như kỳ vọng?
- [ ] Chính sách xóa có phân biệt JPA cascade, orphanRemoval và ON DELETE?
- [ ] Migration đã backfill dữ liệu trước khi thêm NOT NULL/UNIQUE?
- [ ] Integration test chạy trên đúng database engine?
- [ ] Service xử lý lỗi constraint violation thành phản hồi nghiệp vụ phù hợp?

## 16. Kết luận

`optional` mô tả association có bắt buộc hay không trong JPA. `nullable` mô tả cột FK có thể chứa SQL NULL. Foreign key bảo vệ việc tham chiếu tới hàng tồn tại. Unique constraint bảo vệ tính duy nhất của giá trị tham chiếu.

Với ManyToOne tùy chọn, cấu hình thường là `optional = true`, `nullable = true`, có foreign key và không unique. Với OneToOne tùy chọn, cấu hình thường là `optional = true`, `nullable = true`, có foreign key và có unique constraint. Với quan hệ bắt buộc, đồng bộ `optional = false` và `nullable = false`, đồng thời bảo đảm database có NOT NULL và FK.

Hãy xem annotation là mô tả mapping, còn constraint trong database là lớp bảo vệ dữ liệu cuối cùng. Dùng migration để tạo và thay đổi constraint, kiểm thử trên database thật, và luôn xác định rõ cardinality cũng như chính sách xóa trước khi đưa mapping vào production.
