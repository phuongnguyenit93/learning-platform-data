# Khóa ghép với @EmbeddedId và @IdClass

## 1. Mục tiêu

Trong JPA, một Entity thường có một thuộc tính làm khóa chính. Tuy nhiên, có những bảng chỉ xác định duy nhất một bản ghi khi kết hợp nhiều cột. Khóa chính gồm từ hai thuộc tính trở lên được gọi là khóa ghép (composite primary key).

Ví dụ:
- Một bản sao vật lý của sách được xác định bằng ISBN và số thứ tự bản sao.
- Một đăng ký học được xác định bằng mã sinh viên và mã khóa học.
- Một dòng đơn hàng được xác định bằng mã đơn hàng và số thứ tự dòng.

JPA hỗ trợ hai cách ánh xạ khóa ghép phổ biến:
- `@EmbeddedId`: gom các thành phần khóa vào một lớp `@Embeddable`, rồi nhúng lớp đó vào Entity.
- `@IdClass`: khai báo từng thành phần khóa trực tiếp trên Entity bằng nhiều `@Id`, đồng thời chỉ định một lớp khóa riêng bằng `@IdClass`.

Sau bài học, bạn có thể thiết kế hai kiểu khóa ghép, hiểu yêu cầu của lớp khóa, dùng chúng với Spring Data `JpaRepository`, viết truy vấn theo từng thành phần khóa và tránh các lỗi thường gặp.

## 2. Khi nào cần khóa ghép?

Giả sử bảng `book_copies` lưu các bản sao của sách. ISBN xác định đầu sách, nhưng một đầu sách có thể có nhiều bản sao. Vì vậy, ISBN riêng lẻ không duy nhất. Số bản sao cũng chỉ có ý nghĩa trong phạm vi một ISBN.

Khóa chính phù hợp là cặp `(isbn, copy_number)`.

```sql
CREATE TABLE book_copies (
    isbn VARCHAR(17) NOT NULL,
    copy_number INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    available BOOLEAN NOT NULL,
    PRIMARY KEY (isbn, copy_number)
);
```

Một vài dòng dữ liệu minh họa:

| isbn | copy_number | title | available |
| --- | ---: | --- | --- |
| 9780134685991 | 1 | Effective Java | true |
| 9780134685991 | 2 | Effective Java | false |
| 9781492078005 | 1 | Learning SQL | true |

Hai bản sao đầu có cùng ISBN nhưng khác `copy_number`, nên vẫn là hai bản ghi khác nhau. Khi truy vấn hoặc cập nhật một bản sao, ứng dụng phải cung cấp cả hai thành phần khóa.

Chỉ dùng khóa ghép khi các thành phần đó thực sự xác định danh tính của bản ghi theo mô hình dữ liệu. Nếu bảng có một ID thay thế (surrogate key) đơn giản và các cột nghiệp vụ được bảo vệ bằng unique constraint, khóa đơn có thể dễ dùng hơn. Quyết định cần dựa trên mô hình miền, các khóa ngoại và cách dữ liệu được nhận diện trong hệ thống.

## 3. Yêu cầu chung của lớp khóa ghép

Dù dùng `@EmbeddedId` hay `@IdClass`, lớp khóa phải đáp ứng các yêu cầu cơ bản:

1. Là lớp có thể tuần tự hóa (`Serializable`).
2. Có constructor không tham số với quyền truy cập `public` hoặc `protected`.
3. Cài đặt `equals()` và `hashCode()` dựa trên các thành phần khóa.
4. Các giá trị trong khóa phải tương ứng với khóa chính ở database và không được thay đổi sau khi Entity đã được lưu.
5. Các thành phần khóa cần được gán đầy đủ trước khi persist. Khóa ghép thường do ứng dụng cung cấp; không nên giả định JPA sẽ tự sinh từng phần khóa như `@GeneratedValue` của khóa đơn.

`equals()` và `hashCode()` rất quan trọng vì lớp khóa được dùng làm giá trị định danh trong persistence context, cache và các cấu trúc dữ liệu Java. Hai đối tượng khóa chứa cùng các thành phần phải được xem là bằng nhau.

Ví dụ, hai `BookCopyId("9780134685991", 1)` phải bằng nhau và có cùng hash code. Nếu chỉ so sánh tham chiếu đối tượng, việc tìm Entity bằng một instance khóa mới có thể không hoạt động như mong muốn ở các ngữ cảnh Java khác.

Với khóa chứa chuỗi, hãy thống nhất quy tắc chuẩn hóa dữ liệu. Ví dụ ISBN nên được lưu theo một định dạng chuẩn. Nếu database dùng collation không phân biệt hoa/thường trong khi `equals()` của Java phân biệt hoa/thường, quy tắc so sánh ở hai phía có thể không tương thích.

## 4. Cách 1: Dùng @EmbeddedId

`@EmbeddedId` gom toàn bộ thành phần khóa vào một value object. Lớp khóa được đánh dấu `@Embeddable`; Entity chứa một thuộc tính duy nhất được đánh dấu `@EmbeddedId`.

### 4.1. Tạo lớp BookCopyId

`src/main/java/com/example/library/book/BookCopyId.java`:

```java
package com.example.library.book;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class BookCopyId implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Column(name = "isbn", nullable = false, length = 17)
    private String isbn;

    @Column(name = "copy_number", nullable = false)
    private Integer copyNumber;

    protected BookCopyId() {
        // JPA cần constructor không tham số.
    }

    public BookCopyId(String isbn, Integer copyNumber) {
        if (isbn == null || isbn.isBlank()) {
            throw new IllegalArgumentException("ISBN is required");
        }
        if (copyNumber == null || copyNumber <= 0) {
            throw new IllegalArgumentException("Copy number must be positive");
        }
        this.isbn = isbn.trim();
        this.copyNumber = copyNumber;
    }

    public String getIsbn() {
        return isbn;
    }

    public Integer getCopyNumber() {
        return copyNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof BookCopyId that)) {
            return false;
        }
        return Objects.equals(isbn, that.isbn)
                && Objects.equals(copyNumber, that.copyNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(isbn, copyNumber);
    }
}
```

Giải thích:
- `@Embeddable` cho phép lớp được nhúng vào Entity và các thuộc tính của nó trở thành các cột trong bảng Entity đó.
- `@Column` đặt tên và ràng buộc cho từng cột thành phần của khóa.
- Constructor không tham số có `protected` để JPA có thể tạo instance.
- Constructor công khai giúp ứng dụng tạo khóa hợp lệ và kiểm tra dữ liệu đầu vào.
- `equals()` so sánh cả ISBN lẫn số thứ tự bản sao; `hashCode()` dùng cùng hai thành phần.
- `@Serial` và `serialVersionUID` là cách khai báo phiên bản serialization của Java; chúng không thay thế yêu cầu `Serializable` của lớp khóa.

### 4.2. Dùng khóa trong Entity

`src/main/java/com/example/library/book/BookCopy.java`:

```java
package com.example.library.book;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_copies")
public class BookCopy {
    @EmbeddedId
    private BookCopyId id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false)
    private boolean available;

    protected BookCopy() {
        // JPA cần constructor không tham số.
    }

    public BookCopy(BookCopyId id, String title, boolean available) {
        if (id == null) {
            throw new IllegalArgumentException("Book copy ID is required");
        }
        if (title == null || title.isBlank() || title.length() > 200) {
            throw new IllegalArgumentException("Title must contain 1 to 200 characters");
        }
        this.id = id;
        this.title = title.trim();
        this.available = available;
    }

    public BookCopyId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isAvailable() {
        return available;
    }
}
```

Vì `@EmbeddedId` đặt trên field, Entity này sử dụng field access. JPA ánh xạ các field trong `BookCopyId` thành các cột `isbn` và `copy_number`, cùng với các cột `title` và `available` của Entity.

Về mặt cấu trúc, khóa được truy cập qua `bookCopy.getId().getIsbn()` và `bookCopy.getId().getCopyNumber()`. Đây là điểm khác biệt rõ với `@IdClass`, nơi các thuộc tính khóa nằm trực tiếp trên Entity.

### 4.3. Khai báo Repository

`src/main/java/com/example/library/book/BookCopyRepository.java`:

```java
package com.example.library.book;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookCopyRepository extends JpaRepository<BookCopy, BookCopyId> {
    List<BookCopy> findById_IsbnOrderById_CopyNumberAsc(String isbn);
}
```

Tham số kiểu ID của `JpaRepository` là `BookCopyId`, không phải `Long`, vì khóa chính của Entity là một đối tượng gồm hai thành phần.

Phương thức `findById_IsbnOrderById_CopyNumberAsc` là derived query đi theo đường dẫn thuộc tính `id.isbn` và sắp xếp theo `id.copyNumber`. Dấu gạch dưới (`_`) chỉ rõ ranh giới của đường dẫn thuộc tính, giúp Spring Data phân tích tên phương thức không mơ hồ.

### 4.4. Sử dụng Repository

```java
BookCopyId id = new BookCopyId("9780134685991", 2);

BookCopy copy = new BookCopy(id, "Effective Java", true);
bookCopyRepository.save(copy);

BookCopy found = bookCopyRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Book copy not found"));

List<BookCopy> allCopies = bookCopyRepository
        .findById_IsbnOrderById_CopyNumberAsc("9780134685991");
```

Đoạn code này giả định `bookCopyRepository` đã được inject vào một Spring bean. Khi lưu, Hibernate tạo bản ghi với khóa chính gồm cả `isbn` và `copy_number`. Khi tìm theo ID, truyền vào một `BookCopyId` có đủ hai thành phần.

## 5. Cách 2: Dùng @IdClass

Với `@IdClass`, các thuộc tính khóa được khai báo trực tiếp trên Entity và mỗi thuộc tính được đánh dấu `@Id`. Lớp khóa riêng chỉ mô tả cùng tên và kiểu dữ liệu của các thuộc tính đó.

Ví dụ, một sinh viên chỉ có một bản ghi đăng ký cho mỗi khóa học. Khóa ghép là `(student_id, course_code)`.

### 5.1. Tạo lớp StudentCourseId

`src/main/java/com/example/library/course/StudentCourseId.java`:

```java
package com.example.library.course;

import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

public class StudentCourseId implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private Long studentId;
    private String courseCode;

    public StudentCourseId() {
        // JPA cần constructor không tham số.
    }

    public StudentCourseId(Long studentId, String courseCode) {
        this.studentId = Objects.requireNonNull(studentId, "studentId is required");
        this.courseCode = Objects.requireNonNull(courseCode, "courseCode is required");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof StudentCourseId that)) {
            return false;
        }
        return Objects.equals(studentId, that.studentId)
                && Objects.equals(courseCode, that.courseCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseCode);
    }
}
```

### 5.2. Khai báo Entity với nhiều @Id

`src/main/java/com/example/library/course/StudentCourse.java`:

```java
package com.example.library.course;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "student_courses")
@IdClass(StudentCourseId.class)
public class StudentCourse {
    @Id
    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Id
    @Column(name = "course_code", nullable = false, length = 30)
    private String courseCode;

    @Column(nullable = false, length = 20)
    private String status;

    protected StudentCourse() {
        // JPA cần constructor không tham số.
    }

    public StudentCourse(Long studentId, String courseCode, String status) {
        if (studentId == null || studentId <= 0) {
            throw new IllegalArgumentException("Student ID must be positive");
        }
        if (courseCode == null || courseCode.isBlank() || courseCode.length() > 30) {
            throw new IllegalArgumentException("Course code is required");
        }
        if (status == null || status.isBlank() || status.length() > 20) {
            throw new IllegalArgumentException("Status is required");
        }
        this.studentId = studentId;
        this.courseCode = courseCode.trim();
        this.status = status.trim();
    }

    public Long getStudentId() {
        return studentId;
    }

    public String getCourseCode() {
        return courseCode;
    }

    public String getStatus() {
        return status;
    }
}
```

Quy tắc quan trọng của `@IdClass`: tên và kiểu của mỗi thuộc tính trong `StudentCourseId` phải khớp với thuộc tính ID tương ứng trên Entity. Ví dụ, Entity có `studentId` kiểu `Long` và `courseCode` kiểu `String`, thì lớp ID cũng phải có hai thuộc tính đúng tên và đúng kiểu đó.

`@IdClass(StudentCourseId.class)` liên kết Entity với lớp khóa. Không đặt `@EmbeddedId` cùng lúc trên Entity này. Hai chiến lược là hai cách ánh xạ thay thế nhau.

### 5.3. Repository và cách dùng

`src/main/java/com/example/library/course/StudentCourseRepository.java`:

```java
package com.example.library.course;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StudentCourseRepository
        extends JpaRepository<StudentCourse, StudentCourseId> {
    List<StudentCourse> findByStudentId(Long studentId);
}
```

Với `@IdClass`, các thành phần khóa là thuộc tính trực tiếp của Entity nên derived query có thể dùng trực tiếp `studentId` hoặc `courseCode`.

```java
StudentCourse registration = new StudentCourse(101L, "JAVA-101", "ACTIVE");
studentCourseRepository.save(registration);

StudentCourseId id = new StudentCourseId(101L, "JAVA-101");
StudentCourse found = studentCourseRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Registration not found"));

List<StudentCourse> registrations = studentCourseRepository.findByStudentId(101L);
```

Generic ID của `JpaRepository` vẫn là `StudentCourseId`, dù Entity có hai field được đánh dấu `@Id`.

## 6. So sánh @EmbeddedId và @IdClass

| Tiêu chí | `@EmbeddedId` | `@IdClass` |
| --- | --- | --- |
| Vị trí các thuộc tính khóa | Nằm trong một object được nhúng vào Entity. | Nằm trực tiếp trên Entity, mỗi field có `@Id`. |
| Lớp khóa | Được đánh dấu `@Embeddable`. | Lớp POJO riêng, liên kết qua `@IdClass`. |
| Truy cập khóa | `entity.getId().getPart()` hoặc `entity.id.part`. | `entity.getPart()` hoặc `entity.part`. |
| Derived query theo thành phần | Đi theo đường dẫn, ví dụ `findById_Isbn`. | Dùng trực tiếp tên thuộc tính, ví dụ `findByStudentId`. |
| Độ gom nhóm | Các thành phần khóa được gom thành một value object rõ ràng. | Các thành phần khóa hiển thị trực tiếp trên Entity. |
| Repository ID type | Lớp `@Embeddable`. | Lớp `@IdClass`. |

### Nên chọn cách nào?

Ưu tiên `@EmbeddedId` khi muốn biểu diễn khóa như một value object độc lập, có thể tái sử dụng và gom các thao tác liên quan tới khóa vào một lớp. Cách này thường giúp Entity gọn hơn khi khóa có nhiều thành phần.

Chọn `@IdClass` khi mô hình hiện tại cần các thuộc tính khóa nằm trực tiếp trên Entity, hoặc khi muốn truy vấn theo các thuộc tính ID mà không đi qua thuộc tính `id` lồng nhau.

Cả hai cách đều hợp lệ. Không có quy tắc rằng một cách luôn nhanh hơn cách kia; hiệu năng truy vấn phụ thuộc vào SQL, index, database và cách ứng dụng truy cập dữ liệu.

## 7. Truy vấn JPQL với khóa ghép

JPQL làm việc với Entity và thuộc tính Java, không làm việc trực tiếp với tên bảng/cột SQL. Với `@EmbeddedId`, cần đi qua thuộc tính ID để truy cập một thành phần.

Ví dụ:

```java
@Query("select b from BookCopy b where b.id.isbn = :isbn")
List<BookCopy> findAllCopies(@Param("isbn") String isbn);
```

Với `@IdClass`, các thành phần khóa nằm trực tiếp trên Entity:

```java
@Query("select sc from StudentCourse sc where sc.studentId = :studentId")
List<StudentCourse> findRegistrations(@Param("studentId") Long studentId);
```

Nếu dùng derived query, Spring Data cũng phân tích đường dẫn thuộc tính tương ứng. Với khóa nhúng, dấu gạch dưới trong tên phương thức giúp làm rõ điểm tách giữa `id` và thuộc tính con.

## 8. Dùng khóa ghép với quan hệ Entity

Một trường hợp phổ biến là khóa ghép chứa khóa ngoại của Entity cha. Với `@EmbeddedId`, JPA cung cấp `@MapsId` để ánh xạ một quan hệ vào một phần của khóa nhúng.

Ví dụ, dòng đơn hàng có khóa `(order_id, line_number)`. Entity `OrderLine` có thể chứa `@EmbeddedId OrderLineId`, đồng thời có quan hệ `@ManyToOne` tới `PurchaseOrder` và đánh dấu `@MapsId("orderId")` trên quan hệ đó. `orderId` trong khóa nhúng được lấy từ khóa chính của `PurchaseOrder`.

```java
@Entity
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    // Các thuộc tính khác của dòng đơn hàng.
}
```

Đoạn code minh họa này giả định `OrderLineId` có thuộc tính `orderId` cùng tên và kiểu với khóa chính của `PurchaseOrder`. Cần khai báo đầy đủ hai Entity, lớp ID và các cột tương ứng trong dự án thực tế. `@MapsId` tránh phải duy trì độc lập hai giá trị cho cùng một phần khóa.

Với quan hệ phức tạp, hãy thiết kế cẩn thận để tránh vòng lặp serialization, tải lazy ngoài transaction và cập nhật khóa sau khi Entity đã được persist. Khóa chính nên bất biến trong suốt vòng đời Entity.

## 9. Kiểm thử repository với H2

Ví dụ dưới đây kiểm tra cả hai kiểu ánh xạ trong test slice JPA. Các lớp `BookCopy`, `BookCopyId`, `StudentCourse`, `StudentCourseId` và hai repository phải nằm trong package được Spring Boot quét.

`src/test/java/com/example/library/CompositeIdRepositoryTest.java`:

```java
package com.example.library;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import com.example.library.book.BookCopy;
import com.example.library.book.BookCopyId;
import com.example.library.book.BookCopyRepository;
import com.example.library.course.StudentCourse;
import com.example.library.course.StudentCourseId;
import com.example.library.course.StudentCourseRepository;

@DataJpaTest
class CompositeIdRepositoryTest {
    @Autowired
    private BookCopyRepository bookCopyRepository;

    @Autowired
    private StudentCourseRepository studentCourseRepository;

    @Test
    void savesAndFindsEntityUsingEmbeddedId() {
        BookCopyId id = new BookCopyId("9780134685991", 1);
        bookCopyRepository.save(new BookCopy(id, "Effective Java", true));
        bookCopyRepository.flush();

        BookCopy found = bookCopyRepository.findById(
                new BookCopyId("9780134685991", 1)).orElseThrow();

        assertThat(found.getTitle()).isEqualTo("Effective Java");
        assertThat(found.getId()).isEqualTo(id);
    }

    @Test
    void queriesEmbeddedIdParts() {
        bookCopyRepository.saveAll(List.of(
                new BookCopy(new BookCopyId("9780134685991", 2), "Effective Java", false),
                new BookCopy(new BookCopyId("9780134685991", 1), "Effective Java", true),
                new BookCopy(new BookCopyId("9781492078005", 1), "Learning SQL", true)));
        bookCopyRepository.flush();

        List<BookCopy> copies = bookCopyRepository
                .findById_IsbnOrderById_CopyNumberAsc("9780134685991");

        assertThat(copies)
                .extracting(copy -> copy.getId().getCopyNumber())
                .containsExactly(1, 2);
    }

    @Test
    void savesAndFindsEntityUsingIdClass() {
        studentCourseRepository.save(
                new StudentCourse(101L, "JAVA-101", "ACTIVE"));
        studentCourseRepository.flush();

        StudentCourse found = studentCourseRepository.findById(
                new StudentCourseId(101L, "JAVA-101")).orElseThrow();

        assertThat(found.getStatus()).isEqualTo("ACTIVE");
        assertThat(studentCourseRepository.findByStudentId(101L)).hasSize(1);
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và cả ba test đều thành công. Test đầu xác nhận tra cứu bằng instance ID mới có cùng giá trị; test thứ hai kiểm tra derived query theo thành phần của `@EmbeddedId`; test thứ ba xác nhận `@IdClass` hoạt động với `findById` và truy vấn theo thuộc tính ID.

Để kiểm tra mapping trong một ứng dụng hoàn chỉnh, cần có dependency `spring-boot-starter-data-jpa`, driver database (H2 cho ví dụ), và một lớp `@SpringBootApplication` ở package gốc.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lỗi mapping khi khởi động | Lớp khóa thiếu constructor không tham số hoặc thiếu `Serializable`. | Kiểm tra constructor và khai báo `implements Serializable`. |
| Không tìm thấy Entity bằng ID | Lớp khóa không cài đặt `equals()`/`hashCode()` đúng hoặc một thành phần khóa không khớp. | So sánh đầy đủ các thành phần và dùng cùng kiểu dữ liệu với Entity. |
| `@IdClass` không khớp mapping | Tên hoặc kiểu field trong ID class khác thuộc tính `@Id` của Entity. | Đảm bảo tên và kiểu khớp chính xác từng thành phần. |
| Repository dùng sai kiểu ID | Khai báo `JpaRepository<Entity, Long>` dù Entity có khóa ghép. | Dùng lớp ID ghép làm generic thứ hai. |
| Derived query không tìm được thuộc tính | Dùng đường dẫn sai với khóa nhúng hoặc viết tên property không đúng. | Dùng `findById_Isbn` cho `@EmbeddedId`; dùng trực tiếp `findByStudentId` cho `@IdClass`. |
| Lỗi khóa chính trùng | Hai Entity có cùng toàn bộ thành phần khóa. | Kiểm tra dữ liệu và quy tắc tạo khóa trước khi persist. |
| Thành phần khóa bị null | Ứng dụng tạo ID chưa đầy đủ. | Kiểm tra tất cả thành phần trước khi gọi `save`. |
| Cập nhật khóa chính sau khi lưu gây lỗi | Khóa định danh của Entity bị thay đổi trong vòng đời persistence. | Xem khóa là bất biến; nếu danh tính nghiệp vụ thay đổi, cân nhắc mô hình lại dữ liệu. |
| Dùng `@GeneratedValue` cho một phần của khóa ghép | Khả năng sinh một phần khóa không được hỗ trợ đồng nhất giữa provider và chiến lược. | Gán đầy đủ khóa ghép trong ứng dụng hoặc thiết kế lại bằng khóa thay thế. |

## 11. Nguyên tắc thiết kế

1. Chỉ dùng khóa ghép khi nhiều thuộc tính thực sự cùng xác định một bản ghi.
2. Giữ lớp khóa nhỏ, bất biến sau khi sử dụng và có `equals()`/`hashCode()` dựa trên tất cả thành phần.
3. Chọn `@EmbeddedId` nếu muốn gom khóa thành một value object; chọn `@IdClass` nếu muốn các thành phần khóa nằm trực tiếp trên Entity.
4. Khai báo generic ID của Repository bằng đúng lớp khóa ghép.
5. Dùng tên thuộc tính Java khi viết derived query, JPQL và `Sort`; không nhầm với tên cột trong SQL.
6. Với `@EmbeddedId` và quan hệ tới Entity cha, cân nhắc `@MapsId` để ánh xạ một phần khóa từ quan hệ.
7. Không thay đổi khóa sau khi Entity đã được persist; nếu cần thay đổi định danh, hãy đánh giá lại mô hình dữ liệu.
8. Cân nhắc khả năng mở rộng của khóa ghép khi thiết kế khóa ngoại ở các bảng khác: mỗi bảng tham chiếu sẽ phải lưu đủ các thành phần khóa.

## 12. Checklist hoàn thành

- [ ] Giải thích được vì sao một bảng cần khóa ghép.
- [ ] Tạo được lớp `@Embeddable` có `Serializable`, constructor không tham số, `equals()` và `hashCode()`.
- [ ] Ánh xạ Entity bằng `@EmbeddedId` và dùng lớp ID làm generic Repository.
- [ ] Tạo được ID class có tên/kiểu field khớp các thuộc tính `@Id` trên Entity.
- [ ] Ánh xạ Entity bằng `@IdClass` và truy vấn theo từng thành phần khóa.
- [ ] Phân biệt cách truy cập thuộc tính khóa và derived query của hai chiến lược.
- [ ] Biết khi nào dùng `@MapsId` và vì sao khóa chính nên bất biến.
- [ ] Chạy được kiểm thử repository cho cả hai kiểu ánh xạ.

Khi hoàn thành, bạn có thể biểu diễn khóa ghép đúng chuẩn JPA, sử dụng khóa đó xuyên suốt Entity và Repository, đồng thời lựa chọn giữa `@EmbeddedId` và `@IdClass` theo cấu trúc miền dữ liệu.