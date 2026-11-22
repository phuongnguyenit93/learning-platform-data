# Yêu cầu tương ứng giữa lớp khóa và thuộc tính entity trong JPA

Khi một bảng có **khóa chính ghép** (*composite primary key*), danh tính của mỗi hàng được xác định bởi **nhiều cột cùng nhau**. Ví dụ trong hệ thống bán hàng, một dòng đơn hàng có thể được xác định bởi `order_id` và `line_number`: số thứ tự dòng chỉ có ý nghĩa trong phạm vi một đơn hàng, còn cặp hai giá trị mới xác định duy nhất một dòng.

Trong **Jakarta Persistence (JPA)**, khóa ghép được biểu diễn bằng một **lớp khóa** (*primary key class*). Lớp này phải tương ứng với định danh mà entity ánh xạ. Nếu tên, kiểu dữ liệu hoặc cách khai báo giữa hai phía không khớp, JPA provider có thể không khởi tạo được mapping, không tạo được identity đúng, hoặc xảy ra lỗi khi tìm và cập nhật entity.

JPA có hai cách chính để mô hình hóa khóa ghép:

- **`@IdClass`**: các thành phần khóa vẫn xuất hiện trực tiếp dưới dạng những thuộc tính `@Id` trên entity. Lớp khóa riêng phải **khớp từng tên và kiểu** của các thành phần khóa tương ứng.
- **`@EmbeddedId`**: entity chứa một thuộc tính đại diện cho **toàn bộ khóa ghép**. Lớp khóa dùng `@Embeddable` và các trường bên trong nó tương ứng với những cột khóa; có thể kết hợp `@MapsId` để gắn khóa với quan hệ đến entity khác.

Phần quan trọng nhất của bài học là hiểu từ “**tương ứng**”: cần tương ứng theo **thuộc tính Java**, **kiểu Java**, **cấu trúc khóa** và **ánh xạ cột**, chứ không đơn thuần là hai lớp có số lượng field bằng nhau.

## 1. Bắt đầu từ khóa chính ghép ở database

Giả sử bảng `order_lines`:

```sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT pk_order_lines
        PRIMARY KEY (order_id, line_number)
);
```

Các hàng minh họa:

| order_id | line_number | product_code | quantity |
| ---: | ---: | --- | ---: |
| 1001 | 1 | KEYBOARD | 2 |
| 1001 | 2 | MOUSE | 1 |
| 1002 | 1 | MONITOR | 3 |

`line_number = 1` xuất hiện ở hai đơn hàng khác nhau mà không vi phạm khóa chính. Ngược lại, thêm dòng khác có cả `order_id = 1001` và `line_number = 1` sẽ bị constraint `PRIMARY KEY` từ chối.

Về mặt mô hình, định danh không phải chỉ là một `Long`:

```text
OrderLine identity
    |
    +-- orderId    : Long
    |
    +-- lineNumber : Integer

Khóa hợp lệ = cặp (orderId, lineNumber)
Ví dụ:       (1001, 1) khác (1002, 1)
```

JPA cần một giá trị định danh chứa **đủ cả hai thành phần** để `EntityManager.find()`, persistence context và quan hệ định danh hoạt động nhất quán.

## 2. Quy tắc nền tảng của lớp khóa ghép

Dù chọn `@IdClass` hay `@EmbeddedId`, một lớp khóa JPA thông thường cần đáp ứng những yêu cầu quan trọng:

1. Là một kiểu Java thích hợp để biểu diễn định danh ghép; nên khai báo **`public`** để sử dụng thuận tiện giữa các lớp.
2. Có **constructor không tham số** với khả năng truy cập theo hợp đồng JPA; cách portable và dễ hiểu là khai báo `public` constructor không tham số.
3. **Implements `java.io.Serializable`** theo yêu cầu của lớp khóa chính.
4. Triển khai `equals()` và `hashCode()` dựa trên **tất cả thành phần khóa**, để các giá trị định danh bằng nhau được so sánh nhất quán.
5. Kiểu của từng thành phần phải phù hợp với ánh xạ định danh của entity và kiểu dữ liệu database.
6. Giá trị khóa đã dùng để định danh một entity nên **ổn định**, tránh tự ý sửa các thành phần khóa sau khi entity đã được lưu và quản lý.

Với entity cần tính di động giữa các JPA provider, việc giữ lớp khóa đơn giản, không phụ thuộc vào bean/service, và dùng các kiểu giá trị thông dụng như `Long`, `Integer` hoặc `String` thường là thiết kế an toàn.

### 2.1. Vì sao equals() và hashCode() rất quan trọng?

Hai instance lớp khóa có cùng `orderId` và `lineNumber` phải được coi là **cùng giá trị định danh**:

```java
OrderLineId first = new OrderLineId(1001L, 1);
OrderLineId second = new OrderLineId(1001L, 1);

System.out.println(first == second);      // false: hai object khác nhau
System.out.println(first.equals(second)); // true: cùng giá trị khóa
```

Nếu lớp khóa chỉ giữ `equals()` và `hashCode()` mặc định từ `Object`, các bản sao có cùng dữ liệu thường bị coi là khác nhau. Điều đó vi phạm yêu cầu về **value equality** của primary key class và ảnh hưởng đến cách ứng dụng xử lý định danh, tập hợp `HashSet`, `HashMap` và cơ chế nhận diện identity của provider.

`hashCode()` phải nhất quán với `equals()`: hai khóa bằng nhau phải có cùng hash code. Khóa chính ghép chỉ sử dụng `orderId` để so sánh mà bỏ qua `lineNumber` cũng là lỗi, vì nhiều dòng của một đơn hàng có cùng `orderId`.

## 3. @IdClass: lớp khóa phải khớp với các thuộc tính @Id của entity

Đây là cách thể hiện rõ nhất quy tắc “lớp khóa và thuộc tính entity phải tương ứng”.

Với `@IdClass(OrderLineId.class)`, entity khai báo **từng thành phần khóa** bằng `@Id`. Lớp `OrderLineId` chứa những thành phần có **cùng tên và kiểu Java** tương ứng.

### 3.1. Lớp khóa OrderLineId

```java
package com.example.orders;

import java.io.Serializable;
import java.util.Objects;

public class OrderLineId implements Serializable {
    private static final long serialVersionUID = 1L;

    private Long orderId;
    private Integer lineNumber;

    public OrderLineId() {
        // Constructor không tham số cho JPA.
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof OrderLineId other)) {
            return false;
        }
        return Objects.equals(orderId, other.orderId)
            && Objects.equals(lineNumber, other.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

`OrderLineId` là một **lớp giá trị khóa**, không phải entity độc lập. Nó không cần `@Entity` và không có bảng riêng. Trong cách dùng `@IdClass` này, lớp khóa cũng **không bắt buộc có `@Embeddable`**. Vai trò của nó là gom các giá trị của những thuộc tính `@Id` đã được khai báo trực tiếp trên entity.

### 3.2. Entity có các @Id tương ứng

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@IdClass(OrderLineId.class)
public class OrderLine {
    @Id
    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Id
    @Column(name = "line_number", nullable = false)
    private Integer lineNumber;

    @Column(name = "product_code", nullable = false, length = 50)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(
            Long orderId,
            Integer lineNumber,
            String productCode,
            int quantity) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Ở hai lớp này, các thành phần định danh tương ứng như sau:

| Thuộc tính khóa trong entity | Thành phần lớp `OrderLineId` | Kiểu Java | Cột database |
| --- | --- | --- | --- |
| `OrderLine.orderId` có `@Id` | `OrderLineId.orderId` | `Long` | `order_id` |
| `OrderLine.lineNumber` có `@Id` | `OrderLineId.lineNumber` | `Integer` | `line_number` |

Tương ứng **theo tên Java** là `orderId ↔ orderId` và `lineNumber ↔ lineNumber`. Các tên cột `order_id`, `line_number` được xác định bằng `@Column`, nên **không buộc phải trùng với tên field Java**.

Ví dụ một key hợp lệ:

```java
OrderLineId key = new OrderLineId(1001L, 2);

OrderLine line = entityManager.find(OrderLine.class, key);

if (line != null) {
    System.out.println(line.getProductCode());
}
```

`find()` nhận **instance `OrderLineId`**, không nhận riêng `1001L` hoặc `2`, vì khóa chính của `OrderLine` là cặp hai giá trị.

### 3.3. Những yêu cầu tương ứng cụ thể khi dùng @IdClass

Với khóa cơ bản như `Long` hoặc `Integer`, cần kiểm tra các cặp sau:

- **Số thành phần khóa**: mọi thành phần `@Id` của entity phải được biểu diễn trong lớp khóa; lớp khóa cũng không được đưa thêm thành phần không tương ứng.
- **Tên**: `orderId` của entity tương ứng `orderId` trong lớp khóa, kể cả khi cột SQL tên `order_id`.
- **Kiểu Java**: `Long` tương ứng `Long`; không tự ý đổi lớp khóa thành `String` dù database có thể chuyển đổi chuỗi thành số.
- **Access type**: nếu entity dùng field access, metadata ánh xạ nằm trên field; nếu dùng property access, JPA sử dụng getter/setter. Cách biểu diễn lớp khóa phải tuân thủ quy tắc của kiểu truy cập tương ứng.
- **Identity equality**: `equals()` và `hashCode()` sử dụng cả hai thành phần, với semantics tương thích giá trị khóa database.

Ví dụ không hợp lệ do **không khớp tên**:

```java
// Trong OrderLine:
@Id
private Long orderId;

// Trong lớp khóa — sai tên:
private Long orderID;
```

`orderID` và `orderId` là hai tên Java khác nhau. `@Column(name = "order_id")` trên entity không sửa được sai lệch đó.

Ví dụ không hợp lệ do **không khớp kiểu**:

```java
// Trong OrderLine:
@Id
private Integer lineNumber;

// Trong OrderLineId — sai kiểu:
private String lineNumber;
```

Dù giá trị `"2"` có thể chuyển thành số 2 bằng Java, quy tắc matching yêu cầu kiểu đúng theo mapping của các thành phần khóa.

## 4. @EmbeddedId: tương ứng qua một thuộc tính khóa nhúng

`@EmbeddedId` biểu diễn khóa ghép bằng một thuộc tính của entity có kiểu là lớp `@Embeddable`. Khác với `@IdClass`, các field `orderId` và `lineNumber` **nằm trong object khóa**, thay vì phải khai báo thành hai field `@Id` độc lập trên entity.

### 4.1. Định nghĩa lớp khóa nhúng

```java
package com.example.orders;

import java.io.Serializable;
import java.util.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class OrderLineKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Column(name = "line_number", nullable = false)
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof OrderLineKey other)) {
            return false;
        }
        return Objects.equals(orderId, other.orderId)
            && Objects.equals(lineNumber, other.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

### 4.2. Entity sử dụng @EmbeddedId

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @EmbeddedId
    private OrderLineKey id;

    @Column(name = "product_code", nullable = false, length = 50)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(
            OrderLineKey id,
            String productCode,
            int quantity) {
        this.id = id;
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public OrderLineKey getId() {
        return id;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

**Đây là phương án mapping thay thế cho ví dụ `@IdClass`**, không phải hai phiên bản `OrderLine` được đưa vào cùng persistence unit đồng thời.

Tương ứng lúc này được biểu diễn:

```text
OrderLine
  id : OrderLineKey       (@EmbeddedId)
       |
       +-- orderId : Long       --> order_lines.order_id
       |
       +-- lineNumber : Integer --> order_lines.line_number

  productCode : String    --> order_lines.product_code
  quantity    : int       --> order_lines.quantity
```

Entity **không cần** khai báo thêm:

```java
@Id
private Long orderId;

@Id
private Integer lineNumber;
```

vì các thành phần khóa đã nằm trong thuộc tính `@EmbeddedId`. Việc trộn `@EmbeddedId` với những `@Id` độc lập trong cùng entity thường là mapping không đúng cho mô hình định danh này.

### 4.3. Tạo, lưu và tìm entity với EmbeddedId

```java
OrderLineKey key = new OrderLineKey(1001L, 2);
OrderLine line = new OrderLine(key, "MOUSE", 1);

entityManager.persist(line);

// Sau đó, trong ngữ cảnh EntityManager phù hợp:
OrderLine found = entityManager.find(
    OrderLine.class,
    new OrderLineKey(1001L, 2)
);
```

Nếu cần truy vấn theo một thành phần khóa bằng JPQL:

```java
List<OrderLine> lines = entityManager.createQuery(
        "SELECT l FROM OrderLine l " +
        "WHERE l.id.orderId = :orderId " +
        "ORDER BY l.id.lineNumber",
        OrderLine.class
    )
    .setParameter("orderId", 1001L)
    .getResultList();
```

Với `@IdClass`, đường dẫn JPQL tương ứng sẽ là `l.orderId` và `l.lineNumber`, vì hai thuộc tính khóa nằm trực tiếp trên entity.

## 5. Bảng đối chiếu @IdClass và @EmbeddedId

| Nội dung | `@IdClass` | `@EmbeddedId` |
| --- | --- | --- |
| Khai báo trên entity | `@IdClass(Key.class)` ở lớp, `@Id` trên từng thành phần khóa. | `@EmbeddedId` trên một thuộc tính kiểu lớp khóa. |
| Vị trí các thành phần khóa | Trực tiếp trên entity và có bản tương ứng trong lớp khóa. | Bên trong object khóa nhúng. |
| Yêu cầu tên/kiểu | **Tên và kiểu** của các thành phần lớp khóa phải khớp thuộc tính `@Id` tương ứng, trừ quy tắc đặc biệt cho association. | Entity có thuộc tính `@EmbeddedId` đúng kiểu lớp khóa; các thuộc tính trong `@Embeddable` ánh xạ tới cột khóa. |
| Lớp khóa | Không nhất thiết cần `@Embeddable`. | Phải được khai báo kiểu nhúng bằng `@Embeddable`. |
| Tên cột | Thường khai báo bằng `@Column` trên các field `@Id` của entity. | Thường khai báo bằng `@Column` trong lớp khóa hoặc `@AttributeOverride` ở nơi nhúng. |
| Đường dẫn JPQL | `l.orderId`, `l.lineNumber`. | `l.id.orderId`, `l.id.lineNumber`. |
| `EntityManager.find()` | Nhận instance của lớp `@IdClass`. | Nhận instance của lớp `@Embeddable` được dùng làm `@EmbeddedId`. |
| Quan hệ là thành phần khóa | Có quy tắc khớp kiểu đặc biệt khi `@Id` đặt trên association. | Thường phối hợp các giá trị khóa cơ bản với `@MapsId` trên association. |

Cả hai mô hình đều có thể đại diện **cùng một primary key trong database**. Chọn một mô hình dựa trên cách domain truy cập định danh và cấu trúc quan hệ, rồi sử dụng nhất quán trong entity.

## 6. Điểm đặc biệt: khóa ghép chứa quan hệ đến entity khác

Quy tắc “tên và kiểu hoàn toàn giống nhau” của `@IdClass` có một trường hợp cần hiểu cẩn thận: **thành phần khóa trên entity là quan hệ `@ManyToOne` hoặc `@OneToOne`**.

Giả sử bảng đăng ký khóa học `enrollments` được định danh bằng cặp:

- `student_id` trỏ đến sinh viên.
- `course_id` trỏ đến khóa học.

Mỗi sinh viên chỉ được đăng ký một lần trong mỗi khóa học.

```sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE courses (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL REFERENCES students(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    enrolled_at DATE NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
```

### 6.1. Các entity được tham chiếu

Hai entity được minh họa với khóa chính đơn kiểu `Long`, đã có dữ liệu được tạo trước:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "students")
public class Student {
    @Id
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Student() {
    }

    public Long getId() {
        return id;
    }
}
```

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "courses")
public class Course {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Course() {
    }

    public Long getId() {
        return id;
    }
}
```

Lược bỏ các constructor phục vụ tạo sinh viên và khóa học để tập trung vào ánh xạ quan hệ và định danh của `Enrollment`.

### 6.2. @IdClass khi @Id đặt trên @ManyToOne

Entity `Enrollment` có thể trực tiếp dùng hai association làm thành phần khóa:

```java
import java.time.LocalDate;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "enrollments")
@IdClass(EnrollmentPk.class)
public class Enrollment {
    @Id
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @Id
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private LocalDate enrolledAt;

    protected Enrollment() {
    }

    public Enrollment(
            Student student,
            Course course,
            LocalDate enrolledAt) {
        this.student = student;
        this.course = course;
        this.enrolledAt = enrolledAt;
    }
}
```

**Lớp khóa không dùng `Student` và `Course` làm kiểu của hai field**. Vì `Student` và `Course` có định danh cơ bản `Long`, lớp `EnrollmentPk` phải dùng kiểu ID tương ứng:

```java
import java.io.Serializable;
import java.util.Objects;

public class EnrollmentPk implements Serializable {
    private static final long serialVersionUID = 1L;

    private Long student;
    private Long course;

    public EnrollmentPk() {
    }

    public EnrollmentPk(Long student, Long course) {
        this.student = student;
        this.course = course;
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof EnrollmentPk other)) {
            return false;
        }
        return Objects.equals(student, other.student)
            && Objects.equals(course, other.course);
    }

    @Override
    public int hashCode() {
        return Objects.hash(student, course);
    }
}
```

Bảng tương ứng:

| Thành phần `@Id` trên Enrollment | Kiểu trên entity | Trường trong EnrollmentPk | Kiểu trong lớp khóa |
| --- | --- | --- | --- |
| `student` | `Student` (`@ManyToOne`) | `student` | `Long`, kiểu khóa chính của `Student` |
| `course` | `Course` (`@ManyToOne`) | `course` | `Long`, kiểu khóa chính của `Course` |

**Tên vẫn phải khớp**: `student ↔ student`, `course ↔ course`. Nhưng **kiểu của thành phần lớp khóa là kiểu định danh của entity được tham chiếu**, không phải kiểu entity tham chiếu.

Đây là quy tắc đặc thù cho **derived identity** trong JPA. Nếu entity được tham chiếu có khóa ghép, thành phần tương ứng trong lớp khóa của entity phụ thuộc sẽ dùng **kiểu lớp khóa chính** của entity được tham chiếu theo quy tắc JPA, thay vì `Long`.

Ví dụ tìm bản ghi:

```java
EnrollmentPk key = new EnrollmentPk(10L, 501L);
Enrollment enrollment = entityManager.find(Enrollment.class, key);
```

Không nên thay tên `student` thành `studentId` trong `EnrollmentPk` khi thuộc tính `@Id` trên entity vẫn được đặt tên `student`; hai tên sẽ không tương ứng.

### 6.3. Phương án thay thế: @EmbeddedId kết hợp @MapsId

Vẫn với bảng `enrollments`, có thể dùng khóa nhúng chứa hai khóa ngoại dạng scalar:

```java
import java.io.Serializable;
import java.util.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class EnrollmentId implements Serializable {
    private static final long serialVersionUID = 1L;

    @Column(name = "student_id")
    private Long studentId;

    @Column(name = "course_id")
    private Long courseId;

    public EnrollmentId() {
    }

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    public Long getStudentId() {
        return studentId;
    }

    public Long getCourseId() {
        return courseId;
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof EnrollmentId other)) {
            return false;
        }
        return Objects.equals(studentId, other.studentId)
            && Objects.equals(courseId, other.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

Entity tương ứng:

```java
import java.time.LocalDate;
import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;

@Entity
@Table(name = "enrollments")
public class Enrollment {
    @EmbeddedId
    private EnrollmentId id;

    @MapsId("studentId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @MapsId("courseId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private LocalDate enrolledAt;

    protected Enrollment() {
    }

    public Enrollment(
            Student student,
            Course course,
            LocalDate enrolledAt) {
        this.student = student;
        this.course = course;
        this.enrolledAt = enrolledAt;
        this.id = new EnrollmentId(student.getId(), course.getId());
    }

    public EnrollmentId getId() {
        return id;
    }
}
```

**Đây là phương án `Enrollment` thay thế cho cách `@IdClass` ở mục trước**, không đặt cả hai class `Enrollment` vào cùng package/persistence unit trong một dự án.

Ý nghĩa của `@MapsId`:

- `@MapsId("studentId")` nói rằng association `student` cung cấp định danh cho **thành phần `studentId`** trong `EnrollmentId`.
- `@MapsId("courseId")` nói rằng association `course` cung cấp định danh cho **thành phần `courseId`**.
- `@JoinColumn(name = "student_id")` và `@JoinColumn(name = "course_id")` xác định cột khóa ngoại.
- `EnrollmentId` là lớp khóa gồm hai giá trị scalar; nó **không cần chứa tham chiếu `Student` hoặc `Course`**.

Ở ví dụ constructor, giả định `Student` và `Course` đã tồn tại và có ID hợp lệ. Nếu ID của parent chưa được cấp, không nên đọc `getId()` rồi giả định ngay có giá trị để tạo khóa; cần thiết kế quy trình persist/flush và ranh giới transaction thích hợp.

Đối chiếu tên trong hai cách:

| Mô hình | Tên thuộc tính trên entity | Tên thành phần lớp khóa |
| --- | --- | --- |
| `@IdClass` với association `@Id` | `student`, `course` | `student`, `course` (kiểu `Long` theo ID của parent) |
| `@EmbeddedId` + `@MapsId` | `id`; association `student`, `course` | `id.studentId`, `id.courseId`; chuỗi trong `@MapsId` khớp tên **bên trong embedded key** |

Hai cách dùng tên khác nhau vì **quy tắc ánh xạ khác nhau**. Không thể lấy một lớp khóa viết cho `@IdClass` rồi đổi annotation thành `@EmbeddedId` mà không thiết kế lại cấu trúc entity và các tên thuộc tính liên quan.

## 7. Field access và property access ảnh hưởng quy tắc tương ứng

JPA có hai cách truy cập trạng thái:

- **Field access**: JPA đọc field trực tiếp; annotation như `@Id` nằm trên field.
- **Property access**: JPA dùng JavaBean getter/setter; annotation như `@Id` nằm trên getter.

Khi sử dụng `@IdClass`, tên thành phần khóa cần tương ứng với **thuộc tính persistent mà JPA nhận biết**. Với property access, tên property phát sinh từ getter: `getOrderId()` tương ứng property `orderId`, không phải `getOrderId`.

Ví dụ property access tường minh:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;

@Entity
@Access(AccessType.PROPERTY)
@IdClass(OrderLineId.class)
public class OrderLine {
    private Long orderId;
    private Integer lineNumber;

    protected OrderLine() {
    }

    @Id
    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    @Id
    public Integer getLineNumber() {
        return lineNumber;
    }

    public void setLineNumber(Integer lineNumber) {
        this.lineNumber = lineNumber;
    }
}
```

Lớp `OrderLineId` vẫn cần các thành phần `orderId` kiểu `Long` và `lineNumber` kiểu `Integer`. Trong property access, đừng tùy ý đặt `@Id` vào backing field rồi kỳ vọng provider vẫn sử dụng nó nếu chưa có `@Access` thích hợp.

Với `@EmbeddedId`, access type của lớp `@Embeddable` được xác định theo quy tắc truy cập JPA của nơi nhúng, trừ khi cấu hình `@Access` rõ ràng. Vì vậy, hãy tổ chức `@Column`, `@AttributeOverride` và các annotation tại vị trí mà JPA thực sự sử dụng.

## 8. Tên thuộc tính Java không nhất thiết trùng tên cột SQL

Quy tắc tương ứng của `@IdClass` yêu cầu tên Java tương ứng, nhưng tên cột database có thể được đặt khác:

```java
// Entity
@Id
@Column(name = "line_no")
private Integer lineNumber;
```

```java
// Lớp OrderLineId
private Integer lineNumber;
```

Đây vẫn là cặp tên hợp lệ vì **cả hai thuộc tính Java đều tên `lineNumber`**. Cột database `line_no` được quyết định bởi mapping.

Ngược lại, nếu lớp khóa dùng `lineNo` chỉ vì database đặt cột `line_no`:

```java
// Sai với @IdClass nếu entity vẫn dùng lineNumber:
private Integer lineNo;
```

thì quy tắc tên không còn khớp.

Với `@EmbeddedId`, tên field trong lớp `@Embeddable` đóng vai trò các đường dẫn thuộc tính như `id.lineNumber`. Có thể dùng `@Column(name = ...)` trong key class hoặc `@AttributeOverride` tại vị trí nhúng nếu cần điều chỉnh cột mà không đổi cấu trúc Java.

## 9. Sai lệch kiểu và các trường hợp dễ gây nhầm

### 9.1. Long không tự động tương ứng String

```java
// Entity:
@Id
private Long orderId;

// IdClass không khớp:
private String orderId;
```

Chuyển đổi `String` sang `Long` ở service layer không thay thế được hợp đồng mapping. Kiểu của thành phần trong `@IdClass` phải phù hợp với persistent ID attribute tương ứng.

### 9.2. Không đưa thêm field không thuộc khóa vào IdClass

```java
// Entity có @Id trên orderId và lineNumber.
// Lớp khóa sai:
public class OrderLineId implements Serializable {
    private Long orderId;
    private Integer lineNumber;
    private String productCode; // Không phải thành phần khóa.
}
```

`productCode` là dữ liệu nghiệp vụ của dòng hàng, nhưng không nằm trong constraint `PRIMARY KEY (order_id, line_number)`. Nó không được thêm vào lớp khóa `@IdClass` như thành phần identity. Nếu thay đổi `productCode` không làm thay đổi danh tính một hàng, nó không thuộc khóa.

### 9.3. Không bỏ sót thành phần khóa

```java
// Entity:
@Id
private Long orderId;

@Id
private Integer lineNumber;

// IdClass sai: thiếu lineNumber.
public class OrderLineId implements Serializable {
    private Long orderId;
}
```

Chỉ có `orderId` sẽ không phân biệt được hai dòng 1 và 2 của cùng đơn hàng. Lớp khóa phải mô tả đầy đủ identity.

### 9.4. Đừng đưa một entity association vào lớp khóa cơ bản

Với `@IdClass`, nếu `@Id` đặt trên `Student student` có `@ManyToOne`, lớp khóa dùng `Long student` khi `Student` có ID kiểu `Long`. Một lớp khóa chứa `Student student` không phải cách portable để thể hiện quy tắc derived identity cho association này.

Nếu muốn một mô hình có hai foreign key scalar tên `studentId` và `courseId`, có thể chọn `@EmbeddedId` + `@MapsId` như ví dụ trước, hoặc tổ chức mapping khác theo hợp đồng JPA.

### 9.5. Không trộn khóa ghép với sinh @GeneratedValue một cách tùy tiện

`@GeneratedValue` được dùng phổ biến cho **khóa chính đơn**. JPA không cung cấp một quy tắc di động tổng quát cho việc tự động sinh một thành phần bất kỳ của khóa ghép trong mọi provider.

Trong `OrderLine(orderId, lineNumber)`, `lineNumber` thường được nghiệp vụ xác định trong phạm vi đơn hàng; `orderId` có thể lấy từ đơn hàng đã tồn tại. Không nên thêm `@GeneratedValue(strategy = AUTO)` vào một thành phần `@Id` của khóa ghép rồi giả định mọi provider/database sẽ xử lý giống nhau.

Nếu cần một ID tự sinh độc lập cho từng dòng, có thể cân nhắc **khóa thay thế** (*surrogate key*) và đặt ràng buộc `UNIQUE(order_id, line_number)` cho cặp nghiệp vụ. Đây là một thiết kế khác, cần cân nhắc mục tiêu định danh của domain.

## 10. Lớp khóa và tính ổn định sau khi persist

Giá trị định danh không nên thay đổi khi entity đã được quản lý hoặc đã được lưu.

Giả sử:

```java
OrderLineId id = new OrderLineId(1001L, 1);
OrderLine line = entityManager.find(OrderLine.class, id);
```

Nếu entity tồn tại, nó được nhận diện bằng cặp `(1001, 1)`. Đổi `lineNumber` thành 2 trong một entity đã managed không tương đương cập nhật một thuộc tính bình thường: nó **thay đổi danh tính**. JPA không bảo đảm hỗ trợ việc ứng dụng thay đổi khóa chính của một entity đang tồn tại.

Cách thiết kế thường là:

- Giữ các thành phần khóa ổn định sau khi tạo entity.
- Không dùng giá trị thường xuyên biến đổi (ví dụ tên hiển thị) làm thành phần khóa chỉ vì lúc đầu có vẻ duy nhất.
- Nếu thực sự cần đổi định danh của một hàng, cân nhắc thao tác xóa/tạo lại hoặc một quy trình migration nghiệp vụ được thiết kế riêng, với các ràng buộc khóa ngoại liên quan.
- Đối với value object khóa, tránh setter công khai khi không cần. Constructor không tham số dành cho JPA vẫn có thể tồn tại, nhưng mã nghiệp vụ nên tạo khóa đầy đủ bằng constructor có tham số hoặc factory method.

`equals()` và `hashCode()` của lớp khóa phải dựa trên các giá trị định danh. Nếu thay đổi thành phần sau khi đã đưa khóa vào `HashMap` hoặc `HashSet`, cách tìm lại entry có thể gặp vấn đề vì hash code thay đổi. Đó là một lý do khác để coi lớp khóa như **value object ổn định**.

## 11. Tương ứng giữa khóa Java và constraint của database

Khi JPA mapping khai báo khóa ghép, database vẫn cần constraint tương ứng.

Ví dụ `@IdClass` hoặc `@EmbeddedId` ở trên đều muốn:

```sql
PRIMARY KEY (order_id, line_number)
```

Nếu bảng database chỉ có:

```sql
PRIMARY KEY (order_id)
```

thì dữ liệu có nhiều dòng của cùng một đơn hàng sẽ bị constraint từ chối, dù lớp khóa Java chứa cả hai trường.

Ngược lại, nếu database không hề có primary key hoặc unique constraint, nhiều hàng có thể trùng cặp ID do các writer bên ngoài ghi vào, khiến giả định danh tính của JPA bị phá vỡ.

Cần giữ nhất quán cả ba lớp:

```text
Java entity
   @Id orderId
   @Id lineNumber
        |
        v
Java key class (IdClass)
   Long orderId
   Integer lineNumber
        |
        v
Database table
   PRIMARY KEY (order_id, line_number)
```

Với quan hệ `Enrollment`, ngoài primary key ghép, database cũng cần các foreign key phù hợp tới `students(id)` và `courses(id)`. `@MapsId` hoặc `@JoinColumn` biểu diễn quan hệ trong JPA; ràng buộc database giúp dữ liệu luôn tham chiếu đúng khi có những nguồn ghi ngoài JPA.

## 12. Lỗi thường gặp khi cấu hình lớp khóa

| Hiện tượng | Nguyên nhân có thể | Cách điều chỉnh |
| --- | --- | --- |
| Provider báo lỗi về `@IdClass` khi khởi động. | Thiếu thành phần trong lớp khóa, tên hoặc kiểu Java không khớp. | Đối chiếu từng thuộc tính `@Id` với trường/property tương ứng của lớp khóa. |
| Provider không nhận biết primary key của entity. | Quên `@Id`, sai access type hoặc trộn mapping `@EmbeddedId`/`@Id`. | Chọn một mô hình khóa và đặt annotation ở điểm truy cập phù hợp. |
| `find()` không tìm được entity dù biết một phần ID. | Chỉ truyền một giá trị hoặc tạo key thiếu một thành phần. | Tạo key class với **đầy đủ các giá trị khóa**. |
| Có hai key cùng dữ liệu nhưng `equals()` trả false. | Lớp khóa thiếu hoặc viết sai `equals()`/`hashCode()`. | So sánh tất cả thành phần định danh, không dựa trên identity tham chiếu. |
| Khóa chứa `@ManyToOne` báo kiểu không tương ứng. | IdClass dùng loại association object thay vì loại khóa của entity tham chiếu. | Dùng tên association nhưng kiểu PK của entity tham chiếu theo quy tắc derived identity. |
| `@MapsId("student")` không hoạt động khi embedded key đặt tên `studentId`. | Chuỗi `@MapsId` không khớp tên thuộc tính trong embedded key. | Sửa thành `@MapsId("studentId")`. |
| Persist association phụ thuộc không có ID hợp lệ. | Parent entity chưa được persist/cấp ID; logic khởi tạo composite ID quá sớm. | Xác định trước vòng đời parent và cách tạo derived identity trong transaction. |
| SQL insert/update vi phạm constraint. | Mapping Java và schema database khác nhau hoặc dữ liệu khóa trùng. | Kiểm tra tên cột, khóa chính/khóa ngoại, dữ liệu thực tế và migration. |
| JPA hoạt động khác sau đổi provider. | Dùng cơ chế không portable cho sinh một phần khóa hoặc relationship trong key. | Dùng `@IdClass`/`@EmbeddedId`/`@MapsId` theo quy tắc JPA được hỗ trợ. |

## 13. Thực hành: chọn đúng mapping theo mô hình

### Tình huống A — Hai thành phần khóa là giá trị đơn

Bảng `order_lines` có `order_id` và `line_number`, cả hai là giá trị khóa scalar. Có thể dùng:

- `@IdClass` nếu muốn truy cập trực tiếp `line.orderId` và `line.lineNumber`.
- `@EmbeddedId` nếu muốn truyền một đối tượng `OrderLineKey` như value object đầy đủ.

Dù chọn cách nào, cột `order_id` phải được định nghĩa đúng kiểu với `Long` và `line_number` phù hợp `Integer` ở Java, đồng thời constraint database phải bao phủ cả hai cột.

### Tình huống B — Khóa phụ thuộc định danh của parent entity

Bảng `enrollments` được nhận diện bởi `(student_id, course_id)`:

- Với `@IdClass` và `@Id @ManyToOne Student student`, lớp khóa sử dụng trường `student` kiểu **`Long`** nếu `Student` có primary key kiểu `Long`.
- Với `@EmbeddedId`, lớp khóa có thể chứa `studentId` và `courseId` kiểu `Long`; dùng `@MapsId("studentId")`, `@MapsId("courseId")` trên các association.

Điểm cốt lõi: **sự tương ứng có thể nhìn khác nhau giữa hai cách ánh xạ, nhưng vẫn phải mô tả cùng primary key của hàng database**.

### Tình huống C — Khóa ghép đang thay đổi thường xuyên

Nếu `lineNumber` cần đổi do sắp xếp lại các dòng đơn hàng, việc dùng nó làm thành phần khóa chính có thể khiến identity không ổn định và các quan hệ tham chiếu phức tạp. Một lựa chọn là:

```sql
CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT uq_order_line_position
        UNIQUE (order_id, line_number)
);
```

Ở đây JPA có thể dùng `@Id @GeneratedValue` cho `id` và vẫn giữ ràng buộc nghiệp vụ trên cặp `(order_id, line_number)`. Đây **không còn là khóa chính ghép** theo mô hình ban đầu, nhưng có thể phù hợp hơn nếu vị trí dòng thường xuyên thay đổi.

Không có lựa chọn chung cho mọi ứng dụng; hãy phân biệt rõ **danh tính lâu dài** của entity với một **ràng buộc nghiệp vụ duy nhất**.

## 14. Câu hỏi tự kiểm tra

**1. Với `@IdClass`, vì sao entity `orderId` và lớp khóa `orderID` không tương ứng?**

Vì tên Java phân biệt chữ hoa/thường. Tên thành phần lớp khóa phải khớp tên thuộc tính định danh trên entity. Tên SQL có thể độc lập thông qua `@Column`.

**2. Nếu entity có hai thuộc tính `@Id` kiểu `Long` và `Integer`, lớp khóa có thể đổi cả hai thành `String` không?**

Không theo quy tắc matching của các thuộc tính khóa scalar. Lớp khóa phải biểu diễn kiểu phù hợp với từng `@Id`.

**3. `@IdClass` có bắt buộc lớp khóa mang `@Embeddable` không?**

Không. `@IdClass` tham chiếu một lớp khóa chính riêng; lớp khóa đó cần đáp ứng hợp đồng primary key class, trong đó có `Serializable`, constructor không tham số và `equals()`/`hashCode()`.

**4. Entity sử dụng `@EmbeddedId private OrderLineKey id;` có cần thêm `@Id private Long orderId;` không?**

Không. `orderId` là thành phần bên trong `OrderLineKey`. Thêm `@Id` độc lập sẽ trộn hai mô hình định danh.

**5. Với `@Id @ManyToOne Student student` và `Student.id` kiểu `Long`, thành phần tên `student` trong IdClass có kiểu gì?**

Thông thường là `Long`, tức kiểu định danh cơ bản của `Student`. Tên là `student` để khớp tên association trên entity.

**6. Với embedded key có `studentId`, giá trị trong `@MapsId(...)` nên là gì?**

`@MapsId("studentId")`, vì chuỗi tham số trỏ đến **tên thuộc tính bên trong embedded key**, không nhất thiết là tên association.

**7. Có nên tự cập nhật `lineNumber` của entity đã persist nếu đó là một phần khóa chính?**

Không nên. Khóa chính nên ổn định; việc sửa định danh của một entity đã được quản lý không được JPA bảo đảm hỗ trợ như sửa dữ liệu thường.

**8. Có thể bỏ ràng buộc `PRIMARY KEY` ở database vì JPA đã dùng `@EmbeddedId` không?**

Không nên. Mapping JPA mô tả định danh ở tầng object; constraint database vẫn cần bảo vệ tính duy nhất và tính toàn vẹn của bảng, kể cả với những nguồn ghi khác.

## 15. Ghi nhớ cốt lõi

**Yêu cầu tương ứng giữa lớp khóa và thuộc tính entity là nền tảng của khóa ghép JPA.** Với `@IdClass`, các thành phần lớp khóa phải tương ứng với những thuộc tính `@Id` của entity về **tên và kiểu**, trừ quy tắc đặc biệt khi một thành phần `@Id` là association: lúc đó lớp khóa dùng **kiểu định danh của entity được tham chiếu**.

Với `@EmbeddedId`, entity có một thuộc tính khóa nhúng, còn các thành phần khóa nằm trong `@Embeddable`. Khi khóa phụ thuộc quan hệ, `@MapsId` gắn association với tên thành phần nằm trong embedded key.

Trong cả hai mô hình, lớp khóa cần có constructor không tham số, triển khai `Serializable`, `equals()` và `hashCode()` nhất quán; thành phần khóa nên ổn định sau khi entity được lưu. Quan trọng nhất, **Java mapping phải mô tả đúng bộ cột mà database dùng làm primary key**. Khi kiểm tra đủ ba lớp — entity, key class và constraint SQL — việc lưu, tìm, so sánh và liên kết entity có khóa ghép sẽ rõ ràng và đáng tin cậy hơn.
