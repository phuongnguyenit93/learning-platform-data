# Ánh xạ khóa ghép bằng `@IdClass`

Trong mô hình dữ liệu quan hệ, không phải hàng nào cũng được nhận diện bằng một cột `id`. Ví dụ, một nhân viên có thể được nhận diện duy nhất bởi **mã công ty + số nhân viên**, hoặc một dòng đơn hàng bởi **mã đơn hàng + số thứ tự dòng**. Hai giá trị kết hợp mới tạo thành khóa chính.

Jakarta Persistence (JPA) hỗ trợ ánh xạ trường hợp này bằng **`@IdClass`**: trên entity, nhiều thuộc tính được đánh dấu `@Id`; một lớp Java độc lập mô tả **giá trị định danh tổng hợp** để JPA dùng trong các thao tác như `EntityManager.find`. Bài học tập trung vào cách khai báo, cách tra cứu, vòng đời của khóa, quan hệ khóa ngoại và những lỗi dễ mắc khi dùng `@IdClass` trong ứng dụng Java.

## 1. Bắt đầu từ khóa ghép ở cơ sở dữ liệu

Giả sử cùng một doanh nghiệp có nhiều công ty thành viên. Mỗi công ty tự đánh số nhân viên, vì vậy `employee_number = 1001` có thể xuất hiện ở hai công ty khác nhau:

```text
employees
+--------------+-----------------+--------------------+
| company_code | employee_number | full_name          |
+--------------+-----------------+--------------------+
| HCM          |            1001 | Nguyen Minh Anh    |
| HCM          |            1002 | Tran Quoc Bao      |
| HN           |            1001 | Le Thu Ha          |
+--------------+-----------------+--------------------+

PRIMARY KEY (company_code, employee_number)
```

Cột `employee_number` **không duy nhất trên toàn bảng**; cột `company_code` cũng không duy nhất. Nhưng **cặp** `(company_code, employee_number)` là duy nhất. Schema SQL có thể khai báo:

```sql
CREATE TABLE employees (
    company_code VARCHAR(12) NOT NULL,
    employee_number BIGINT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    hired_at DATE,
    CONSTRAINT pk_employees
        PRIMARY KEY (company_code, employee_number)
);
```

Khóa chính ghép ở database bảo đảm:

- Không có hai hàng trùng **cùng cặp giá trị**.
- Các thành phần của primary key đều không được null.
- Các bảng khác có thể tham chiếu cặp giá trị thông qua foreign key ghép.
- Việc tra cứu theo toàn bộ khóa xác định tối đa một hàng.

**Đừng nhầm khóa ghép với hai khóa chính độc lập.** Một bảng có *một ràng buộc primary key*, nhưng ràng buộc đó chứa nhiều cột. Trong JPA, ta cần một định danh có nhiều thuộc tính tương ứng.

## 2. Vai trò của `@IdClass`

### 2.1. Hai nơi mô tả một khóa

Với `@IdClass`, định danh được mô tả ở **hai lớp có vai trò khác nhau**:

1. **Entity:** chứa các thuộc tính được ánh xạ tới cột khóa, mỗi thuộc tính có `@Id`; đây cũng là nơi định nghĩa `@Column`, quan hệ, các trường nghiệp vụ.
2. **Primary key class:** một Java class dùng làm **đối tượng giá trị khóa** khi gọi `find`, `getReference` hoặc các API cần ID tổng hợp.

```text
Entity: Employee                         Key class: EmployeeId
+---------------------------------+      +------------------------+
| @Id String companyCode          |<---->| String companyCode     |
| @Id Long employeeNumber         |<---->| Long employeeNumber    |
| String fullName                 |      | equals()/hashCode()    |
| LocalDate hiredAt               |      | Serializable           |
+---------------------------------+      +------------------------+
          |
          | @Table / @Column
          v
  employees(company_code, employee_number, full_name, hired_at)
            PRIMARY KEY (company_code, employee_number)
```

Điểm khác biệt quan trọng: **entity không buộc phải có một field tên `id` chứa `EmployeeId`**. Các phần khóa nằm trực tiếp trên entity, trong khi `EmployeeId` mô tả cách gom chúng thành một định danh logic.

### 2.2. Yêu cầu đối với primary key class

Theo mô hình `@IdClass` của JPA, lớp khóa nên đáp ứng đầy đủ những điều kiện sau:

| Yêu cầu | Vì sao cần |
|---|---|
| Là lớp có thể truy cập công khai và triển khai `Serializable` | JPA có thể truyền/biểu diễn identity theo cách tiêu chuẩn |
| Có constructor không tham số `public` | Provider có thể tạo đối tượng khóa |
| Có các thành phần khóa trùng **tên** với các thuộc tính `@Id` trên entity | JPA đối chiếu theo tên thuộc tính, không đối chiếu theo tên cột SQL |
| Có các kiểu dữ liệu tương ứng với thuộc tính khóa của entity | Giúp provider ghép/tách chính xác các thành phần ID |
| Override `equals(Object)` và `hashCode()` dựa trên **mọi** thành phần khóa | Hai giá trị khóa giống nhau phải bằng nhau và có hash giống nhau |
| Giữ các thành phần ID ổn định sau khi tạo | Tránh lỗi identity và collection dùng hash |

Trong trường hợp khóa `@Id` là thuộc tính quan hệ tới entity cha theo cơ chế **derived identity**, kiểu trong lớp khóa có quy tắc riêng: tương ứng với **kiểu khóa chính của entity được tham chiếu**, thay vì kiểu class entity. Phần 7 sẽ có ví dụ cụ thể.

Lớp khóa **không phải một `@Entity`** và không cần `@Id` trên các trường của chính nó. Với `@IdClass`, metadata ánh xạ cột chủ yếu thuộc về entity. Không nên thêm `@Embeddable` chỉ vì lớp khóa có nhiều field; đó là mô hình khác dành cho `@EmbeddedId`.

## 3. Ví dụ hoàn chỉnh: `EmployeeId` và `Employee`

### 3.1. Tạo lớp khóa `EmployeeId`

**`src/main/java/com/example/company/domain/EmployeeId.java`**

```java
package com.example.company.domain;

import java.io.Serializable;
import java.util.Objects;

public class EmployeeId implements Serializable {

    private static final long serialVersionUID = 1L;

    private String companyCode;
    private Long employeeNumber;

    public EmployeeId() {
        // Constructor không tham số cho JPA.
    }

    public EmployeeId(String companyCode, Long employeeNumber) {
        this.companyCode = Objects.requireNonNull(companyCode);
        this.employeeNumber = Objects.requireNonNull(employeeNumber);
    }

    public String getCompanyCode() {
        return companyCode;
    }

    public Long getEmployeeNumber() {
        return employeeNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof EmployeeId that)) {
            return false;
        }
        return Objects.equals(companyCode, that.companyCode)
            && Objects.equals(employeeNumber, that.employeeNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(companyCode, employeeNumber);
    }

    @Override
    public String toString() {
        return companyCode + "/" + employeeNumber;
    }
}
```

`equals` so sánh **cả hai thành phần**, vì `(HCM, 1001)` và `(HN, 1001)` là hai khóa khác nhau. `hashCode` cũng lấy cả hai thành phần theo cùng chính sách. Nếu `equals` so sánh hai trường nhưng `hashCode` chỉ dùng một trường, Java vẫn cho phép nhiều va chạm hash, song thiết kế hash kém phân bố hơn và dễ che giấu sai sót; quan trọng nhất là hai đối tượng được xem là bằng nhau phải luôn có hash bằng nhau.

Constructor không tham số phục vụ JPA; constructor có tham số phục vụ ứng dụng tạo một khóa đầy đủ, tránh `null` khi thực hiện tra cứu. Lớp khóa có field riêng (`private`) và getter cho các thành phần; provider ánh xạ chúng theo tên thuộc tính tương ứng.

Không nên sửa `companyCode` hoặc `employeeNumber` sau khi dùng một `EmployeeId` làm key của `HashMap` hoặc phần tử `HashSet`: hash thay đổi có thể khiến bộ sưu tập không tìm lại được phần tử. Quy ước sử dụng tốt là **tạo một đối tượng khóa đầy đủ rồi coi nó là value object bất biến về mặt hành vi**.

### 3.2. Tạo entity sử dụng `@IdClass`

**`src/main/java/com/example/company/domain/Employee.java`**

```java
package com.example.company.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

import java.time.LocalDate;
import java.util.Objects;

@Entity
@Table(name = "employees")
@IdClass(EmployeeId.class)
public class Employee {

    @Id
    @Column(name = "company_code",
            nullable = false, length = 12, updatable = false)
    private String companyCode;

    @Id
    @Column(name = "employee_number",
            nullable = false, updatable = false)
    private Long employeeNumber;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @Column(name = "hired_at")
    private LocalDate hiredAt;

    protected Employee() {
        // JPA sử dụng constructor không tham số.
    }

    public Employee(
            String companyCode,
            Long employeeNumber,
            String fullName,
            LocalDate hiredAt) {

        this.companyCode = Objects.requireNonNull(companyCode);
        this.employeeNumber = Objects.requireNonNull(employeeNumber);
        this.fullName = Objects.requireNonNull(fullName);
        this.hiredAt = hiredAt;
    }

    public String getCompanyCode() {
        return companyCode;
    }

    public Long getEmployeeNumber() {
        return employeeNumber;
    }

    public String getFullName() {
        return fullName;
    }

    public LocalDate getHiredAt() {
        return hiredAt;
    }

    public void rename(String newName) {
        this.fullName = Objects.requireNonNull(newName);
    }
}
```

Cần đọc kỹ bốn dòng ánh xạ định danh:

```java
@IdClass(EmployeeId.class)   // Khai báo kiểu đại diện khóa tổng hợp.
public class Employee {
    @Id                       // Thành phần khóa thứ nhất.
    private String companyCode;

    @Id                       // Thành phần khóa thứ hai.
    private Long employeeNumber;
}
```

Hai trường trên entity có tên **`companyCode`** và **`employeeNumber`**, khớp chính xác với trường trong `EmployeeId`. Tên cột SQL là `company_code` và `employee_number`; việc khác cách viết camelCase/snake_case hoàn toàn bình thường vì `@Column(name=...)` thực hiện ánh xạ cột.

Các thuộc tính `fullName` và `hiredAt` **không** nằm trong khóa, vì sửa tên hoặc ngày tuyển dụng không được làm thay đổi định danh của nhân viên.

### 3.3. Vì sao `@IdClass` được đặt trên entity, không đặt lên lớp khóa?

`@IdClass(EmployeeId.class)` nói với provider rằng khi cần xác định identity của `Employee`, các trường có `@Id` phải được kết hợp thành một khóa có kiểu `EmployeeId`. Lớp `EmployeeId` là dữ liệu về ID; nó không có vòng đời persistence riêng, không có bảng riêng và không được quản lý như một entity.

Ví dụ:

```java
EmployeeId id = new EmployeeId("HCM", 1001L);
Employee employee = entityManager.find(Employee.class, id);
```

JPA giải mã `id` thành điều kiện tương đương:

```sql
SELECT company_code, employee_number, full_name, hired_at
FROM employees
WHERE company_code = ?
  AND employee_number = ?;
```

SQL cụ thể, thứ tự cột, bí danh và việc truy cập cache phụ thuộc provider; ví dụ chỉ diễn tả ý nghĩa truy vấn theo khóa đầy đủ.

## 4. Field access, property access và việc khớp tên

JPA có thể ánh xạ thuộc tính qua **field** hoặc qua **getter/setter**. Với `@IdClass`, việc chọn access type phải nhất quán vì **tên thuộc tính khóa được xác định theo mô hình truy cập của entity**.

### 4.1. Field access

Trong ví dụ `Employee`, annotation `@Id` đặt trên field:

```java
@Id
@Column(name = "company_code")
private String companyCode;
```

Vì vậy entity dùng field access mặc định ở phạm vi phù hợp. Lớp khóa có thành phần tên `companyCode` tương ứng. Không cần `Employee` phải có `getId()`.

### 4.2. Property access

Một entity khác có thể đặt `@Id` trên getter:

```java
@Entity
@IdClass(ZoneId.class)
public class Zone {

    private String region;
    private String code;

    protected Zone() {}

    @Id
    public String getRegion() {
        return region;
    }

    protected void setRegion(String region) {
        this.region = region;
    }

    @Id
    public String getCode() {
        return code;
    }

    protected void setCode(String code) {
        this.code = code;
    }
}
```

`ZoneId` khi đó phải có các thành phần tên `region` và `code`, cùng kiểu `String`. Getter `getRegion()` tạo tên property `region`, không phải `getRegion`. Setter cần cho quá trình JPA nạp giá trị theo property access, với mức truy cập phù hợp cho provider.

**Tránh trộn `@Id` ở field với annotation ánh xạ khác ở getter mà không chủ đích.** Nếu thiết kế bắt buộc trộn, cần sử dụng `@Access(AccessType.FIELD)` hoặc `@Access(AccessType.PROPERTY)` thích hợp và tuân theo quy tắc metadata của JPA.

### 4.3. Sai tên và sai kiểu

Những cặp khai báo sau **không tương ứng**:

```java
// Trên entity:
@Id
private Long employeeNumber;

// Trong IdClass:
private Integer employeeNumber;  // Sai kiểu: Integer khác Long.
```

```java
// Trên entity:
@Id
private String companyCode;

// Trong IdClass:
private String company_code;     // Sai tên thuộc tính.
```

JPA không dùng `@Column(name="company_code")` để suy ra một field trong key class tên `company_code`. Nó ghép theo **tên thuộc tính Java**, rồi xét kiểu tương ứng.

Ngay cả `long` và `Long` cũng không nên tùy tiện dùng lệch giữa entity và key class. Giữ cùng kiểu khai báo giúp tránh khác biệt về phản xạ và metadata giữa provider.

## 5. Thêm, đọc, cập nhật và xóa entity dùng `@IdClass`

### 5.1. Thêm bản ghi

Trong ứng dụng Java SE dùng persistence unit có transaction `RESOURCE_LOCAL`, giả sử đã có một `EntityManager em` đang mở:

```java
Employee employee = new Employee(
    "HCM",
    1001L,
    "Nguyen Minh Anh",
    LocalDate.of(2026, 1, 10)
);

EntityTransaction tx = em.getTransaction();
tx.begin();
try {
    em.persist(employee);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Ví dụ cần các import phù hợp, gồm `EntityTransaction` và `LocalDate`. Với Jakarta EE hoặc Spring quản lý JTA/transaction, không tự gọi `getTransaction()` theo mẫu `RESOURCE_LOCAL` này.

Vì hai thành phần khóa do ứng dụng cung cấp, đối tượng phải có **`companyCode` và `employeeNumber` hợp lệ trước `persist`**. Với khóa tự cấp, JPA không tự tìm số nhân viên còn trống hoặc tự tạo mã công ty.

### 5.2. Tra cứu với `EntityManager.find`

`find` nhận **một đối tượng `EmployeeId`**, không nhận hai tham số khóa riêng lẻ:

```java
EmployeeId key = new EmployeeId("HCM", 1001L);

Employee employee = em.find(Employee.class, key);

if (employee != null) {
    System.out.println(employee.getFullName());
}
```

Nếu không tìm thấy, `find` trả về `null` khi truy vấn hợp lệ và không có lỗi khác. Cũng có thể sử dụng `getReference` khi chỉ cần tham chiếu do provider quản lý; cách xử lý entity không tồn tại và lazy proxy phụ thuộc thời điểm truy cập.

Không có API JPA chuẩn dạng:

```java
// Không phải cách gọi EntityManager.find tiêu chuẩn:
em.find(Employee.class, "HCM", 1001L);
```

### 5.3. Truy vấn JPQL

Một điểm dễ nhầm với `@EmbeddedId`: các phần khóa nằm **trực tiếp trên entity**, nên JPQL có thể truy cập:

```java
List<Employee> employees = em.createQuery(
        "select e from Employee e " +
        "where e.companyCode = :code " +
        "order by e.employeeNumber",
        Employee.class)
    .setParameter("code", "HCM")
    .getResultList();
```

Tìm đúng một khóa:

```java
Employee employee = em.createQuery(
        "select e from Employee e " +
        "where e.companyCode = :code " +
        "and e.employeeNumber = :number",
        Employee.class)
    .setParameter("code", "HCM")
    .setParameter("number", 1001L)
    .getSingleResult();
```

`getSingleResult()` có thể ném `NoResultException` nếu không tìm thấy; `find` thường thuận tiện hơn khi đã có toàn bộ khóa. JPQL `e.companyCode` là đường dẫn chuẩn theo tên thuộc tính Java, **không dùng tên SQL `company_code`**.

Vì entity mẫu không có field `id`, câu `e.id.companyCode` không phải đường dẫn thuộc tính thông thường của nó. Đó là kiểu truy cập quen thuộc với `@EmbeddedId`, không phải mặc định của `@IdClass`.

### 5.4. Cập nhật các trường không phải khóa

Sau khi đọc entity trong transaction:

```java
Employee employee = em.find(
    Employee.class,
    new EmployeeId("HCM", 1001L)
);

if (employee == null) {
    throw new IllegalArgumentException("Không tìm thấy nhân viên");
}
employee.rename("Nguyen Minh Anh Updated");
```

Nếu `employee` đang managed, JPA có thể phát hiện thay đổi của `fullName` và đồng bộ SQL `UPDATE` khi flush/commit. Điều kiện WHERE thường sử dụng **đầy đủ thành phần khóa**. Không cần tạo ID mới chỉ vì đổi tên nhân viên.

### 5.5. Xóa và kiểm tra tồn tại

```java
EmployeeId key = new EmployeeId("HCM", 1001L);
Employee employee = em.find(Employee.class, key);

if (employee != null) {
    em.remove(employee);
}
```

Đoạn này phải chạy trong transaction phù hợp khi thao tác ghi. Nếu có bảng khác tham chiếu khóa ghép, database có thể từ chối xóa theo foreign key. Cascade và chính sách xóa là quyết định nghiệp vụ, không được giải quyết tự động chỉ bởi `@IdClass`.

## 6. `@IdClass` và vòng đời định danh

### 6.1. Khóa ghép nên có đủ giá trị trước khi lưu

Với ví dụ `EmployeeId(companyCode, employeeNumber)`, cả hai thành phần được **assigned** trước `persist`. Việc dùng `@GeneratedValue` cho một thành phần của khóa ghép là trường hợp **không được bảo đảm tính portable** giữa các JPA provider: đặc tả không yêu cầu hỗ trợ sinh khóa tự động cho mọi cấu trúc composite ID như với khóa đơn.

Ví dụ không nên coi là cấu hình JPA portable:

```java
@Id
private String companyCode;

@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long employeeNumber;
```

Một provider cụ thể có thể hỗ trợ một biến thể, nhưng phải dựa vào tài liệu của chính provider, schema và cách INSERT, chứ không áp dụng như quy tắc phổ quát.

Nếu cần khóa thay đổi theo thời điểm lưu, cân nhắc:

- Cấp sẵn toàn bộ thành phần khóa bằng một dịch vụ cấp số có kiểm soát.
- Dùng **surrogate ID đơn** được sinh bởi database rồi đặt unique constraint trên bộ thuộc tính nghiệp vụ.
- Nếu khóa gồm quan hệ tới entity cha có ID được sinh, đảm bảo cha có khóa hợp lệ trước khi persist con và chọn mapping derived identity thích hợp.

### 6.2. Không thay đổi thành phần `@Id` của managed entity

Ví dụ sau là một thay đổi nguy hiểm:

```java
Employee employee = em.find(
    Employee.class,
    new EmployeeId("HCM", 1001L)
);

// Không làm:
employee.setCompanyCode("HN");
```

Nếu thay `companyCode` của object đang managed, identity mà persistence context dùng không còn khớp. Provider có thể phát hiện lỗi khi flush hoặc tạo hành vi không mong muốn. Trong database, các hàng con đang tham chiếu khóa cũ cũng có thể bị ảnh hưởng.

Vì thế ví dụ `Employee` không cung cấp setter cho `companyCode` và `employeeNumber`. Muốn chuyển nhân viên giữa công ty, cần mô hình nghiệp vụ rõ: chuyển một thuộc tính không định danh, tạo bản ghi mới, hoặc dùng khóa đơn surrogate không phụ thuộc mã công ty, tùy yêu cầu dữ liệu.

### 6.3. Managed, detached và merged

`@IdClass` không đổi quy tắc vòng đời JPA:

```text
new Employee(...): transient, có khóa gán sẵn
       |
       | persist()
       v
managed trong persistence context
       |
       | detach()/close()
       v
detached, vẫn giữ companyCode và employeeNumber
       |
       | merge()
       v
managed instance được trả về
```

`merge(detachedEmployee)` trả về một instance managed; object đưa vào không tự chuyển thành managed. Cả hai có thể có cùng cặp khóa nhưng là hai Java object khác nhau.

`@IdClass` mô tả cách JPA nhận diện entity, **không tự sinh `equals`/`hashCode` của entity**. Việc so sánh hai instance entity qua nhiều persistence context cần chính sách equality riêng. Quy tắc `equals`/`hashCode` bắt buộc trên **lớp khóa `EmployeeId`** không có nghĩa entity `Employee` tự được so sánh bằng hai trường đó.

## 7. `@IdClass` kết hợp quan hệ: derived identity

Một tình huống rất phổ biến là khóa của entity con gồm **khóa của entity cha + số thứ tự trong cha**. Ví dụ mỗi đơn hàng có dòng số 1, 2, 3...:

```text
purchase_orders
+----+------------+
| id | status     |
+----+------------+
| 42 | CREATED    |
+----+------------+
    |
    | FK: purchase_order_id
    v
purchase_order_lines
+-------------------+---------+----------+
| purchase_order_id | line_no | quantity |
+-------------------+---------+----------+
|                42 |       1 |        2 |
|                42 |       2 |        1 |
+-------------------+---------+----------+

PRIMARY KEY (purchase_order_id, line_no)
FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id)
```

### 7.1. Entity cha có khóa đơn

```java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() {
        return id;
    }
}
```

Để tập trung vào `@IdClass`, ví dụ này giả sử ID của đơn hàng đã được cấp trước khi thêm dòng.

### 7.2. Lớp khóa của dòng đơn

**`PurchaseOrderLineId.java`**

```java
package com.example.shop.domain;

import java.io.Serializable;
import java.util.Objects;

public class PurchaseOrderLineId implements Serializable {

    private static final long serialVersionUID = 1L;

    // Tên "order" khớp property @Id trong entity con.
    // Kiểu Long khớp kiểu khóa chính của PurchaseOrder.
    private Long order;

    private Integer lineNo;

    public PurchaseOrderLineId() {
    }

    public PurchaseOrderLineId(Long order, Integer lineNo) {
        this.order = Objects.requireNonNull(order);
        this.lineNo = Objects.requireNonNull(lineNo);
    }

    public Long getOrder() {
        return order;
    }

    public Integer getLineNo() {
        return lineNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof PurchaseOrderLineId that)) return false;

        return Objects.equals(order, that.order)
            && Objects.equals(lineNo, that.lineNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(order, lineNo);
    }
}
```

### 7.3. Entity con có quan hệ tham gia khóa

**`PurchaseOrderLine.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order_lines")
@IdClass(PurchaseOrderLineId.class)
public class PurchaseOrderLine {

    @Id
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "purchase_order_id",
        referencedColumnName = "id",
        nullable = false
    )
    private PurchaseOrder order;

    @Id
    @Column(name = "line_no", nullable = false, updatable = false)
    private Integer lineNo;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected PurchaseOrderLine() {
    }

    public PurchaseOrderLine(
            PurchaseOrder order, Integer lineNo, int quantity) {
        this.order = order;
        this.lineNo = lineNo;
        this.quantity = quantity;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public Integer getLineNo() {
        return lineNo;
    }
}
```

**Điểm đặc biệt:** trong entity con, thuộc tính `order` có kiểu `PurchaseOrder` vì đây là một quan hệ `@ManyToOne`. Nhưng trong `PurchaseOrderLineId`, thuộc tính **cùng tên `order`** lại có kiểu **`Long`**, tức là kiểu khóa chính của `PurchaseOrder`.

Đây là ngoại lệ quan trọng đối với quy tắc “tên và kiểu của `@Id` phải giống hệt giữa entity và IdClass”: khi một thuộc tính `@Id` là quan hệ tới entity cha và thuộc trường hợp **derived identity**, trường tương ứng trong key class mang kiểu ID của entity cha. Không thay thành `private PurchaseOrder order` trong key class chỉ vì thấy entity dùng `PurchaseOrder`; điều đó tạo lớp khóa không đúng mô hình chuẩn của derived identity.

### 7.4. Lược đồ SQL tương ứng

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(40) NOT NULL
);

CREATE TABLE purchase_order_lines (
    purchase_order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT pk_purchase_order_lines
        PRIMARY KEY (purchase_order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
);
```

Ta có thể tra cứu dòng số 2 của đơn hàng 42:

```java
PurchaseOrderLineId key =
    new PurchaseOrderLineId(42L, 2);

PurchaseOrderLine line =
    entityManager.find(PurchaseOrderLine.class, key);
```

Từ góc nhìn JPA, khóa vẫn là `PurchaseOrderLineId`. Từ góc nhìn SQL, điều kiện tra cứu sử dụng cả `purchase_order_id` và `line_no`.

### 7.5. Thứ tự lưu cha và con

Khi khóa của con phụ thuộc khóa của cha, entity cha phải có định danh phù hợp trước lúc JPA cần ghi bản ghi con. Nếu cha dùng `@GeneratedValue(IDENTITY)` và chưa có ID, cách persisting cha, cascading và flush có thể ảnh hưởng thời điểm ID sẵn có.

Không nên cho rằng tạo `new PurchaseOrderLine(new PurchaseOrder(...), 1, ...)` sẽ tự động lưu cả cha và con. Nếu muốn cascade `PERSIST`, phải khai báo và hiểu ranh giới tổng thể. Đối với bài học này, ví dụ sử dụng cha đã tồn tại hoặc đã được persist để giữ mô hình minh bạch.

## 8. `@IdClass` so với `@EmbeddedId`

JPA có hai cách chuẩn để biểu diễn khóa ghép. Cùng một khóa hai cột có thể dùng một trong hai:

### 8.1. Với `@IdClass`

```java
@Entity
@IdClass(EmployeeId.class)
public class Employee {

    @Id
    private String companyCode;

    @Id
    private Long employeeNumber;

    private String fullName;
}
```

JPQL truy cập các phần khóa trực tiếp:

```jpql
select e
from Employee e
where e.companyCode = :code
  and e.employeeNumber = :number
```

### 8.2. Với `@EmbeddedId`

```java
@Embeddable
public class EmployeeKey implements Serializable {

    private String companyCode;
    private Long employeeNumber;

    public EmployeeKey() {
    }

    // Constructor, getter, equals và hashCode...
}

@Entity
public class Employee {

    @EmbeddedId
    private EmployeeKey id;

    private String fullName;
}
```

JPQL truy cập lồng qua ID object:

```jpql
select e
from Employee e
where e.id.companyCode = :code
  and e.id.employeeNumber = :number
```

Bảng so sánh:

| Tiêu chí | `@IdClass` | `@EmbeddedId` |
|---|---|---|
| Vị trí các thuộc tính định danh trong entity | Nhiều field/property `@Id` nằm trực tiếp trên entity | Một field/property `@EmbeddedId` chứa object khóa |
| Lớp ID | Java class với tên/kiểu thành phần tương ứng; `Serializable` và equality/hash | Class `@Embeddable` có equality/hash và mapping của value object |
| Đường dẫn JPQL | `e.companyCode`, `e.employeeNumber` | `e.id.companyCode`, `e.id.employeeNumber` |
| Khả năng truy cập phần khóa trong Java | `employee.getCompanyCode()` | `employee.getId().getCompanyCode()` |
| Metadata trên entity | Khai báo `@Id` ở từng thuộc tính | Khai báo `@EmbeddedId` ở một thuộc tính |
| Khi có quan hệ làm thành phần ID | Có thể dùng `@Id @ManyToOne` theo quy tắc derived identity | Thường thấy `@MapsId` nối quan hệ với khóa nhúng |
| Khóa đưa vào `find` | Một instance của IdClass | Một instance của embedded ID class |
| Giá trị nghiệp vụ | Phù hợp khi ứng dụng thường thao tác trực tiếp các field khóa trên entity | Phù hợp khi muốn gom khóa thành value object rõ ràng |

Không nên dùng **đồng thời `@IdClass` và `@EmbeddedId` cho cùng một khóa entity** nếu không có lý do và mô hình đặc thù được hỗ trợ rõ ràng. Chọn một cách biểu diễn chính để tránh metadata xung đột và code khó hiểu.

### 8.3. Khi nào chọn `@IdClass`?

`@IdClass` thường thuận tiện khi:

- Entity đã có các thuộc tính khóa riêng lẻ và các truy vấn thường lọc trên chúng.
- Cần giữ getter của các thành phần ID trực tiếp trên entity.
- Có mô hình cũ mà nhiều field đã được dùng làm `@Id`.
- Một trong các thành phần khóa là quan hệ được biểu diễn qua `@Id @ManyToOne` theo derived identity.

`@EmbeddedId` có thể thuận tiện khi miền dữ liệu cần đối tượng khóa là **một value object được truyền và sử dụng thường xuyên**, hoặc muốn tổ chức toàn bộ metadata của các thành phần khóa trong một lớp nhúng. Hiệu năng không nên được kết luận chỉ bằng annotation: SQL, schema, index, truy vấn và provider mới quyết định chi phí thực tế.

## 9. `equals` và `hashCode`: lớp khóa khác entity

### 9.1. Vì sao key class phải có value equality?

Hai đối tượng khóa được tạo riêng:

```java
EmployeeId left = new EmployeeId("HCM", 1001L);
EmployeeId right = new EmployeeId("HCM", 1001L);

System.out.println(left == right);      // false
System.out.println(left.equals(right)); // true
```

`left` và `right` là hai object Java khác nhau nhưng biểu diễn **cùng khóa database**. JPA yêu cầu key class có quy tắc equality dựa trên giá trị, vì các API, cache và nội dung Java có thể cần nhận diện chúng cùng một định danh.

Các thuộc tính dùng tính `equals` phải gồm mọi thành phần khóa. Ví dụ chỉ dùng `employeeNumber` sẽ coi `(HCM,1001)` và `(HN,1001)` là bằng nhau, làm hỏng ý nghĩa composite key.

### 9.2. Hợp đồng Java và tính bất biến

Hợp đồng cơ bản:

- `a.equals(a)` là true.
- `equals` phải đối xứng, bắc cầu và nhất quán khi các giá trị so sánh không đổi.
- Nếu `a.equals(b)` là true, `a.hashCode() == b.hashCode()` phải đúng.
- Giá trị khóa dùng trong `HashMap`/`HashSet` không nên đổi khi đang nằm trong collection.

Ví dụ sai:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof EmployeeId that)) return false;
    return Objects.equals(employeeNumber, that.employeeNumber);
    // Bỏ mất companyCode => hai công ty có thể dùng cùng employeeNumber.
}
```

Ví dụ sai khác:

```java
@Override
public int hashCode() {
    return Objects.hash(companyCode, employeeNumber, System.nanoTime());
    // Hash không ổn định ngay cả khi cùng một khóa.
}
```

`hashCode` không dùng đồng hồ, trạng thái mutable không thuộc khóa, association lazy, hay giá trị ngẫu nhiên. Với key gồm hai chuỗi, cần xác định quy tắc chuẩn hóa chuỗi (chữ hoa/thường, khoảng trắng, Unicode) trước khi tạo và lưu khóa; nếu database dùng collation không phân biệt hoa/thường nhưng Java lại so sánh có phân biệt, hai tầng có thể bất đồng về uniqueness.

### 9.3. Entity `Employee` có cần override equality không?

`@IdClass` **không bắt buộc entity phải override `equals`/`hashCode`**. Nếu ứng dụng chỉ thao tác entity trong một persistence context, reference equality có thể đủ. Nếu cần so sánh managed và detached instances từ các context khác nhau, phải chọn chính sách equality của entity và cân nhắc proxy, inheritance, ID null và multi-tenancy.

Không nên copy thẳng `equals` từ `EmployeeId` vào entity rồi thêm tất cả field nghiệp vụ. Việc đổi `fullName` không làm thay đổi identity, nên equality theo các field này dễ không nhất quán.

## 10. Khóa ghép khi có tenant, quan hệ và index

### 10.1. Multi-tenancy và phạm vi unique

Một bài toán phổ biến: khóa gồm `tenant_id` + `record_no`. Hai tenant có thể cùng record number 17 mà không trùng nhau:

```sql
CREATE TABLE tenant_documents (
    tenant_id VARCHAR(36) NOT NULL,
    record_no BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    PRIMARY KEY (tenant_id, record_no)
);
```

Ứng dụng cần **luôn truyền đúng tenant** khi gọi `find` hoặc viết query. Có khóa ghép không tự thực thi phân quyền: người dùng tenant A không được phép truy cập dữ liệu tenant B chỉ vì biết cặp `tenant_id`, `record_no`.

Nếu tenant thực tế được tách bằng database riêng, một `record_no` giống nhau ở hai database vẫn là hai thực thể ở hai phạm vi lưu trữ khác nhau. Khi tổng hợp object từ nhiều nguồn, lớp khóa có thể phải chứa thông tin phạm vi tương ứng hoặc không được trộn các đối tượng như thể chúng có chung một không gian định danh.

### 10.2. Foreign key ghép phải đầy đủ thành phần

Giả sử bảng `employee_assignments` tham chiếu `employees`:

```sql
CREATE TABLE employee_assignments (
    assignment_id BIGINT PRIMARY KEY,
    company_code VARCHAR(12) NOT NULL,
    employee_number BIGINT NOT NULL,
    project_code VARCHAR(24) NOT NULL,
    CONSTRAINT fk_assignment_employee
        FOREIGN KEY (company_code, employee_number)
        REFERENCES employees(company_code, employee_number)
);
```

Nếu chỉ lưu `employee_number` làm foreign key, bản ghi không xác định được nhân viên thuộc công ty nào. Điều này có thể dẫn đến dữ liệu sai dù phía Java có đủ trường ID.

Ví dụ mapping:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumns({
    @JoinColumn(
        name = "company_code",
        referencedColumnName = "company_code"
    ),
    @JoinColumn(
        name = "employee_number",
        referencedColumnName = "employee_number"
    )
})
private Employee employee;
```

Khi sử dụng, cần import `jakarta.persistence.JoinColumns` và `JoinColumn`. Ở đây entity `EmployeeAssignment` có thể có khóa đơn riêng `assignmentId`; khóa ngoại ghép tới `Employee` không đòi hỏi bản thân `EmployeeAssignment` cũng dùng composite primary key.

### 10.3. Thứ tự cột trong chỉ mục

Một chỉ mục B-tree trên `(company_code, employee_number)` thường hỗ trợ tốt truy vấn theo cả hai thành phần và nhiều truy vấn lọc theo thành phần đầu `company_code`. Truy vấn chỉ theo `employee_number` có thể không tận dụng cùng chỉ mục hiệu quả như trường hợp có tiền tố phù hợp, tùy database và kế hoạch thực thi.

Vì vậy, **thứ tự cột của primary key/index và mẫu truy vấn thực tế** phải được cân nhắc khi thiết kế schema. Annotation `@IdClass` không tự tối ưu các điều kiện SQL hoặc quyết định mọi index phụ.

## 11. Những lỗi cấu hình thường gặp

| Triệu chứng / sai sót | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Provider báo primary-key class không khớp entity | Tên field trong IdClass khác tên thuộc tính `@Id` | Đồng bộ chính xác tên Java, không dùng tên cột SQL thay thế |
| Type mismatch của thành phần ID | Entity dùng `Long`, IdClass dùng `Integer` hoặc loại khác | Khớp kiểu; chú ý ngoại lệ derived identity |
| Lỗi khởi tạo key class | Thiếu constructor `public` không tham số, class không thể truy cập | Thêm public no-arg constructor và visibility phù hợp |
| Không thể dùng key như Serializable | IdClass không triển khai `Serializable` | Implement `Serializable` và định nghĩa giá trị khóa đúng |
| `find` không nhận object khóa | Truyền entity object, một String hoặc chỉ một thành phần | Truyền đúng instance của IdClass chứa đủ giá trị |
| Hai key khác nhau bị coi là bằng nhau | `equals` bỏ sót thành phần hoặc chuẩn hóa không nhất quán | So sánh đầy đủ các thành phần theo đúng semantics |
| `HashSet.contains` không tìm thấy key | Thay thành phần key sau khi thêm vào collection | Coi key là bất biến sau khi tạo/đưa vào collection |
| Persist thất bại vì khóa null | Một hoặc nhiều `@Id` chưa được gán | Cấp đủ khóa trước khi persist; xem quan hệ cha nếu dùng derived identity |
| Vi phạm PRIMARY KEY khi thêm hàng | Cặp khóa đã tồn tại | Xử lý trùng ở nghiệp vụ và để DB bảo đảm unique |
| Lỗi khi cập nhật khóa entity | Code cố sửa `@Id` của managed entity | Giữ identity ổn định, dùng mô hình khác nếu nghiệp vụ cần đổi mã |
| SQL lỗi foreign key tới bảng khóa ghép | Bảng con chỉ tham chiếu một phần khóa hoặc sai thứ tự/cột | Định nghĩa `@JoinColumns` và FK có đủ thành phần |
| Derived identity sai kiểu khóa | IdClass khai báo kiểu entity cha thay vì kiểu PK của cha | Khai báo loại ID cha tương ứng trong IdClass |
| Trộn `@EmbeddedId` và `@IdClass` tùy tiện | Hai mô hình khóa ghép bị chồng lấn | Chọn một mô hình mapping nhất quán |
| JPQL lỗi đường dẫn `e.id.x` | Entity `@IdClass` không có field `id` kiểu embeddable | Truy cập trực tiếp `e.companyCode`, `e.employeeNumber` |

### 11.1. Sai lầm cụ thể: dùng tên cột ở IdClass

Ví dụ không đúng:

```java
@Entity
@IdClass(EmployeeId.class)
class Employee {
    @Id
    @Column(name = "company_code")
    private String companyCode;
}

// Sai nếu trong EmployeeId lại viết:
private String company_code;
```

JPA cần `EmployeeId.companyCode`, bởi metadata ánh xạ dựa trên **thuộc tính**. Giá trị `company_code` chỉ thuộc thế giới schema SQL.

### 11.2. Sai lầm cụ thể: chỉ một phần khóa được đánh dấu `@Id`

```java
@IdClass(EmployeeId.class)
class Employee {
    @Id
    private String companyCode;

    private Long employeeNumber; // Thiếu @Id.
}
```

Mô hình entity không còn khai báo đủ các thành phần tương ứng với `EmployeeId`. Provider có thể báo lỗi metadata hoặc không nhận diện khóa như mong muốn. Muốn khóa gồm cả hai thì **cả hai thuộc tính phải mang `@Id`**.

### 11.3. Sai lầm cụ thể: cho business field tham gia khóa sai mục đích

Một nhân viên có thể đổi tên, nhóm hoặc chức danh. Nếu đưa `fullName` vào primary key, mọi lần đổi tên có thể kéo theo sửa identity, foreign key và cache, gây phức tạp không cần thiết. Lựa chọn khóa ghép nên được biện minh bằng **quy tắc định danh ổn định**, không phải vì có vài trường trông “đặc trưng”.

### 11.4. Sai lầm cụ thể: tin rằng một thành phần khóa có thể tự sinh portable

Với một số phiên bản Hibernate, có thể gặp ví dụ sinh một thành phần của composite ID bằng extension riêng. Nhưng không phải mọi JPA provider hoặc mọi dialect đều hỗ trợ như vậy. Đối với mã phải di chuyển giữa provider, **đừng coi `@GeneratedValue` trên một phần composite key là tính năng đảm bảo của chuẩn**; hãy chọn cách cấp khóa đã xác định trước hoặc khóa surrogate đơn.

## 12. Quy tắc lựa chọn khóa ghép trong thiết kế thực tế

Có hai câu hỏi tách biệt:

1. **Database có nên dùng composite primary key?**
2. **Nếu đã có composite key, JPA nên dùng `@IdClass` hay `@EmbeddedId`?**

Một số tình huống:

| Tình huống | Quyết định khởi đầu | Điều cần xem xét |
|---|---|---|
| Nhân viên duy nhất trong phạm vi công ty, mã công ty và số nhân viên bất biến | Composite PK `(company_code, employee_number)` với `@IdClass` | Quyền truy cập, foreign key, query theo công ty |
| Dòng đơn hàng duy nhất bởi đơn cha + số dòng | `@IdClass` với derived identity hoặc `@EmbeddedId` + `@MapsId` | Vòng đời ID cha, xóa/cascade, thay thứ tự dòng |
| Mã bên ngoài có thể đổi nhiều lần | Surrogate ID đơn + unique trên mã nghiệp vụ | Tránh đổi identity của nhiều bảng |
| Join table thuần chỉ chứa hai foreign key | Composite PK có thể phù hợp; nếu dùng entity association có thuộc tính riêng thì chọn mapping nhất quán | Nhu cầu truy cập trực tiếp, cascade, metadata bổ sung |
| Bảng đa tenant chia sẻ schema | PK hoặc unique constraint chứa tenant khi phù hợp | Không thay thế kiểm tra quyền |
| Bảng giao dịch rất lớn, khóa gồm nhiều chuỗi dài | Cân nhắc surrogate ID và unique index trên bộ mã | Kích thước index, JOIN, băng thông khóa ngoại |

Tùy ứng dụng, composite key thể hiện đúng quy tắc dữ liệu và giúp database bảo đảm tính duy nhất. Nhưng nó cũng làm mỗi foreign key, join và index liên quan có thể dài hơn. **Không nên tạo khóa ghép chỉ vì dữ liệu có hai trường duy nhất**: đôi khi một khóa đơn nội bộ kết hợp unique constraint trên cặp business fields là thiết kế dễ mở rộng hơn.

## 13. Bài thực hành: cấu hình và quan sát `@IdClass`

### Bài 1 — Khai báo entity với hai trường khóa

Tạo bảng `employees` theo SQL ở phần đầu, viết `EmployeeId` và `Employee` với:

- `@IdClass(EmployeeId.class)` trên entity.
- Hai `@Id` đặt đúng chỗ và có kiểu tương ứng trong key class.
- `equals`/`hashCode` đầy đủ trong `EmployeeId`.
- Một trường `fullName` không thuộc khóa.

Dùng `EntityManager.persist` để lưu `(HCM,1001)` và `(HN,1001)`. Tự giải thích vì sao hai bản ghi không xung đột dù cùng `employee_number`.

### Bài 2 — Tra cứu bằng composite key

Dùng:

```java
EmployeeId key = new EmployeeId("HCM", 1001L);
Employee result = em.find(Employee.class, key);
```

Sau đó thử thay `"HCM"` thành `"HN"` và đối chiếu nhân viên được tìm thấy. Viết JPQL tương đương với điều kiện trên hai trường và so sánh kết quả.

### Bài 3 — Quan sát lỗi mapping

Thử lần lượt trong môi trường học tập:

1. Đổi tên `EmployeeId.employeeNumber` thành `number`.
2. Đổi kiểu của nó từ `Long` thành `Integer`.
3. Bỏ một `@Id` trên `Employee`.
4. Bỏ constructor public không tham số của `EmployeeId`.

Quan sát thời điểm provider báo lỗi khi khởi tạo persistence unit hoặc thao tác khóa. Khôi phục cấu hình đúng trước thử nghiệm tiếp.

### Bài 4 — Giá trị khóa và `HashSet`

```java
EmployeeId a = new EmployeeId("HCM", 1001L);
EmployeeId b = new EmployeeId("HCM", 1001L);
EmployeeId c = new EmployeeId("HN", 1001L);

Set<EmployeeId> keys = new HashSet<>();
keys.add(a);
keys.add(b);
keys.add(c);

System.out.println(keys.size()); // 2
```

Tự giải thích vì sao `a` và `b` được xem là cùng khóa, còn `c` khác. Thử minh họa lỗi nếu `equals` bỏ qua `companyCode`.

### Bài 5 — Khóa phụ thuộc entity cha

Tạo `PurchaseOrder`, `PurchaseOrderLine` và `PurchaseOrderLineId` như phần 7. Lưu hai dòng số 1, 2 cho đơn hàng 42, tìm dòng bằng `new PurchaseOrderLineId(42L, 2)`. Kiểm tra schema có **PRIMARY KEY hai cột** và **FOREIGN KEY từ `purchase_order_id` tới đơn cha**.

Giải thích vì sao trong entity, `order` có kiểu `PurchaseOrder`, nhưng trong `PurchaseOrderLineId`, `order` có kiểu `Long`.

### Bài 6 — So sánh với `@EmbeddedId`

Viết lại `Employee` bằng `@EmbeddedId`. So sánh cấu trúc Java và JPQL giữa:

```jpql
-- IdClass: khóa nằm trực tiếp trên entity
select e from Employee e where e.companyCode = :code
```

và:

```jpql
-- EmbeddedId: khóa nằm trong thuộc tính id
select e from Employee e where e.id.companyCode = :code
```

Xác định cách nào làm code nghiệp vụ dễ hiểu hơn trong bài toán đang làm, không đánh giá chỉ theo số annotation.

## 14. Ghi nhớ cốt lõi

**`@IdClass` là cách ánh xạ một primary key gồm nhiều thành phần mà các thuộc tính `@Id` vẫn nằm trực tiếp trên entity.** Một lớp khóa riêng chứa các thành phần tương ứng, implements `Serializable`, có constructor không tham số `public` và định nghĩa `equals`/`hashCode` theo toàn bộ giá trị khóa.

Với `@IdClass`, cần nhớ ba mối liên hệ chính:

1. **Tên thuộc tính Java phải khớp giữa entity và IdClass**; tên cột SQL có thể khác nhờ `@Column`.
2. **Kiểu dữ liệu cũng phải tương ứng**; ngoại lệ quan trọng là derived identity, khi entity dùng `@Id` trên quan hệ cha nhưng IdClass lưu kiểu ID của entity cha.
3. **Vòng đời khóa phải ổn định**: cấp đủ thành phần trước khi persist, không thay identity của managed entity và để database thực thi PRIMARY KEY/FOREIGN KEY thực sự.

Khi tra cứu, hãy tạo **một đối tượng IdClass đầy đủ** rồi truyền vào `EntityManager.find`. Khi viết JPQL, truy cập các trường khóa **trực tiếp trên entity**. Chọn `@IdClass` thay vì `@EmbeddedId` khi cách tổ chức này phù hợp với domain và cách truy vấn; cả hai đều cần thiết kế schema, định danh và transaction nhất quán.
