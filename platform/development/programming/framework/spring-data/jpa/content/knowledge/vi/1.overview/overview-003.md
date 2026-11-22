# Entity, bảng, khóa định danh, Repository và giao dịch trong cùng một mô hình

Spring Data JPA kết nối mô hình đối tượng Java với dữ liệu quan hệ trong cơ sở dữ liệu. Để hiểu cách các thành phần phối hợp, ta dùng một ví dụ xuyên suốt: quản lý sách. Một cuốn sách được biểu diễn bằng entity **Book**, được lưu thành một hàng trong bảng **books**. Trường **id** là khóa chính; **BookRepository** cung cấp thao tác truy vấn và lưu trữ; **BookService** xác định một giao dịch nghiệp vụ có thể gồm nhiều thao tác repository.

Sau bài này, bạn có thể giải thích và triển khai được mối liên hệ giữa entity, bảng, khóa chính, repository và transaction; biết đặt ranh giới giao dịch ở đâu; và hiểu vì sao thay đổi một entity đã được quản lý có thể được ghi xuống cơ sở dữ liệu mà không cần gọi **save()** lần nữa.

## 1. Nhìn toàn bộ mô hình

| Thành phần | Vai trò trong ví dụ |
|---|---|
| Entity **Book** | Đối tượng Java đại diện cho một cuốn sách được lưu bền vững |
| Bảng **books** | Nơi cơ sở dữ liệu lưu các hàng sách |
| Khóa chính **id** | Định danh duy nhất một hàng và một entity |
| Repository **BookRepository** | Cổng truy cập dữ liệu: tìm, thêm, cập nhật, xóa |
| Service **BookService** | Thực hiện quy tắc nghiệp vụ và xác định ranh giới transaction |
| Transaction | Đảm bảo nhóm thay đổi dữ liệu được commit hoặc rollback như một đơn vị |

Luồng ghi một cuốn sách mới:

~~~text
BookService.register(...)
        |
        | @Transactional
        v
BookRepository.save(book)
        |
        v
JPA EntityManager / Hibernate
        |
        v
INSERT INTO books (...)
        |
        v
COMMIT transaction
~~~

Luồng cập nhật giá:

~~~text
BookService.changePrice(...)
        |
        | bắt đầu transaction
        v
BookRepository.findByIsbn(...)
        |
        v
Book đang được JPA quản lý (managed)
        |
        | book.changePrice(...)
        v
Dirty checking phát hiện thay đổi
        |
        v
UPDATE books SET price = ... WHERE id = ...
        |
        v
COMMIT transaction
~~~

Entity là khái niệm phía Java; bảng và hàng là cấu trúc phía cơ sở dữ liệu. JPA ánh xạ giữa hai phía. Repository làm việc với entity, còn transaction bao quanh một đơn vị công việc để các thao tác dữ liệu phối hợp nhất quán.

**Điều kiện của ví dụ:** các khối mã bên dưới là những tệp nguồn riêng trong một ứng dụng Spring Boot 3.x chạy Java 17 trở lên, có dependency **spring-boot-starter-data-jpa**, một DataSource được cấu hình và schema tương ứng trong database. Đây không phải chương trình độc lập có thể biên dịch chỉ bằng **javac**. Kết quả SQL cụ thể phụ thuộc Hibernate, dialect, database và cấu hình ứng dụng.

## 2. Entity ánh xạ tới bảng như thế nào?

Một entity là lớp Java được JPA quản lý và ánh xạ tới dữ liệu lưu trữ. Lớp thường được đánh dấu bằng **@Entity**. **@Table** cho biết tên bảng và có thể khai báo các ràng buộc ở mức bảng.

Ta dùng mô hình sách với bốn thuộc tính:

- **id**: khóa chính do cơ sở dữ liệu sinh.
- **title**: tên sách, bắt buộc.
- **isbn**: mã ISBN, bắt buộc và duy nhất trong ví dụ.
- **price**: giá sách, dùng **BigDecimal** để tránh sai số nhị phân thường gặp khi dùng **float** hoặc **double** cho tiền.

~~~java
package com.example.book.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.math.BigDecimal;

@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String title;

    @Column(nullable = false, length = 20)
    private String isbn;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    // JPA cần constructor không tham số; protected là đủ.
    protected Book() {
    }

    public Book(String title, String isbn, BigDecimal price) {
        this.title = requireText(title, "title");
        this.isbn = requireText(isbn, "isbn");
        this.price = requirePrice(price);
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = requirePrice(newPrice);
    }

    private static String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return value.trim();
    }

    private static BigDecimal requirePrice(BigDecimal value) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException("price must be greater than or equal to zero");
        }
        return value;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

### Ý nghĩa các annotation

- **@Entity**: đánh dấu lớp là entity. JPA sẽ quản lý vòng đời của các đối tượng thuộc lớp này.
- **@Table(name = "books")**: ánh xạ lớp tới bảng **books**. Nếu bỏ qua, tên bảng được suy ra theo quy tắc đặt tên của provider và cấu hình ứng dụng.
- **@Id**: đánh dấu thuộc tính định danh chính của entity. Một entity phải có định danh.
- **@GeneratedValue**: chỉ định cách sinh giá trị khóa chính. **IDENTITY** thường dùng với cột identity/auto-increment; chiến lược phù hợp phụ thuộc hệ quản trị cơ sở dữ liệu và schema thực tế.
- **@Column**: mô tả ánh xạ cột, chẳng hạn **nullable**, độ dài chuỗi, độ chính xác và số chữ số thập phân.
- **@UniqueConstraint**: khai báo ràng buộc duy nhất ở mức bảng. Trong ví dụ, hai hàng không được có cùng ISBN.

Các annotation mô tả mapping và có thể được Hibernate dùng khi sinh schema. Chúng không tự đảm bảo một schema đã tồn tại được cập nhật đúng trong mọi môi trường. Cơ sở dữ liệu vẫn cần có bảng, cột và constraint tương ứng.

### Quy tắc quan trọng khi viết entity

1. Entity cần constructor không tham số có phạm vi **public** hoặc **protected** để JPA khởi tạo.
2. Không khai báo entity là **final** và tránh làm các thuộc tính persistent thành **final**, vì provider cần khả năng quản lý entity.
3. Đặt annotation ở field như ví dụ nghĩa là JPA dùng field access. Nếu đặt annotation trên getter, JPA dùng property access. Không trộn hai kiểu tùy tiện trong cùng một entity.
4. Không cho phép thay đổi khóa chính sau khi entity đã được tạo. Khóa chính là định danh ổn định của hàng.
5. Không nên tạo **equals()** và **hashCode()** dựa trên tất cả field có thể thay đổi. Điều đó có thể làm entity hoạt động khó đoán trong **Set**, **Map** hoặc khi entity chuyển trạng thái.
6. Dùng **BigDecimal** cho tiền và dữ liệu thập phân cần độ chính xác. Không khởi tạo giá tiền bằng phép tính **double** rồi mới chuyển sang **BigDecimal**.

## 3. Khóa chính và khóa nghiệp vụ

Trong ví dụ, **id** là khóa chính (primary key). Mỗi hàng trong bảng **books** có một giá trị **id** duy nhất, không null. JPA dùng khóa này để nhận biết hai lần đọc có đang nói về cùng một entity hay không.

**isbn** là khóa nghiệp vụ (business key): nó có ý nghĩa trong miền nghiệp vụ và được dùng để tra cứu sách. Ta đặt unique constraint để cơ sở dữ liệu bảo vệ tính duy nhất của ISBN.

Hai loại khóa có mục đích khác nhau:

| Đặc điểm | **id** (khóa chính kỹ thuật) | **isbn** (khóa nghiệp vụ) |
|---|---|---|
| Mục đích | Định danh bản ghi ổn định | Nhận diện sách theo quy tắc nghiệp vụ |
| Giá trị | Thường do hệ thống sinh | Đến từ dữ liệu sách |
| Có thể thay đổi? | Nên xem là bất biến | Có thể có quy trình sửa theo nghiệp vụ |
| Dùng trong JPA | Được đánh dấu bằng **@Id** | Không phải định danh JPA trong ví dụ |
| Ràng buộc | Primary key | Unique constraint |

Không nên dùng một thuộc tính nghiệp vụ làm khóa chính chỉ vì hiện tại nó có vẻ duy nhất. Mã nghiệp vụ có thể đổi theo quy định, trong khi khóa chính nên ổn định trong suốt vòng đời dữ liệu. Ngược lại, khóa chính kỹ thuật không thay thế được ràng buộc duy nhất của dữ liệu nghiệp vụ.

### Chọn chiến lược sinh khóa

JPA cung cấp các chiến lược thường gặp:

- **GenerationType.IDENTITY**: cơ sở dữ liệu sinh khóa khi insert, thường phù hợp với cột identity hoặc auto-increment.
- **GenerationType.SEQUENCE**: dùng sequence của cơ sở dữ liệu; thường phù hợp với PostgreSQL và Oracle.
- **GenerationType.TABLE**: dùng một bảng riêng để quản lý giá trị sinh.
- **GenerationType.AUTO**: để provider chọn chiến lược phù hợp với dialect.

Không có chiến lược nào luôn tốt nhất cho mọi hệ quản trị. Hãy chọn theo database, khả năng hỗ trợ và cách schema được quản lý. Khi dùng **IDENTITY**, Hibernate có thể cần thực hiện insert sớm để lấy ID; vì vậy thời điểm phát sinh SQL có thể khác với các chiến lược khác.

## 4. Repository là cổng truy cập dữ liệu

Spring Data JPA cho phép khai báo interface repository mà không phải tự viết lớp triển khai CRUD cơ bản. Với entity **Book** có khóa chính kiểu **Long**, repository có thể viết như sau:

~~~java
package com.example.book.repository;

import com.example.book.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    boolean existsByIsbn(String isbn);

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
~~~

Khai báo **JpaRepository<Book, Long>** có nghĩa là repository quản lý entity **Book** và kiểu của khóa chính là **Long**.

Một số thao tác có sẵn:

| Phương thức | Ý nghĩa |
|---|---|
| **save(book)** | Lưu entity mới hoặc đồng bộ thay đổi của entity |
| **findById(id)** | Tìm theo khóa chính, trả về **Optional<Book>** |
| **findAll()** | Lấy danh sách entity |
| **existsById(id)** | Kiểm tra entity có tồn tại theo ID |
| **deleteById(id)** | Xóa theo ID |
| **flush()** | Yêu cầu persistence context đẩy thay đổi xuống database |

Spring Data JPA còn hỗ trợ tạo truy vấn từ tên phương thức:

- **findByIsbn** tạo truy vấn tìm sách theo ISBN.
- **existsByIsbn** tạo truy vấn kiểm tra ISBN tồn tại.
- **findByTitleContainingIgnoreCase** tìm tiêu đề có chứa từ khóa, không phân biệt hoa thường.

Khi quy tắc truy vấn phức tạp hơn, có thể dùng **@Query**, JPQL, native SQL hoặc Specification. Chỉ nên thêm truy vấn tùy chỉnh khi phương thức dẫn xuất không còn diễn đạt rõ ràng yêu cầu.

Repository không phải là bảng và cũng không phải nơi nên chứa toàn bộ quy tắc nghiệp vụ. Nó tập trung vào truy cập dữ liệu. Việc một ISBN có được phép đăng ký hay giá sách có được thay đổi hay không thuộc về logic nghiệp vụ của service/domain.

## 5. Transaction đặt ở service

Một thao tác nghiệp vụ có thể cần nhiều lần truy cập dữ liệu. Ví dụ đăng ký sách cần kiểm tra ISBN, tạo entity và lưu entity. Đổi giá cần tìm sách rồi cập nhật giá. Nếu mỗi lời gọi repository tự chạy trong một transaction độc lập, ta khó đảm bảo toàn bộ nghiệp vụ là một đơn vị nhất quán.

Đặt **@Transactional** ở service giúp nhóm các thao tác repository trong cùng một transaction:

~~~java
package com.example.book.service;

import com.example.book.domain.Book;
import com.example.book.repository.BookRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.NoSuchElementException;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Long register(String title, String isbn, BigDecimal price) {
        if (bookRepository.existsByIsbn(isbn)) {
            throw new IllegalStateException("ISBN already exists: " + isbn);
        }

        Book book = new Book(title, isbn, price);
        Book savedBook = bookRepository.save(book);
        return savedBook.getId();
    }

    @Transactional(readOnly = true)
    public BookView getByIsbn(String isbn) {
        Book book = bookRepository.findByIsbn(isbn)
            .orElseThrow(() -> new NoSuchElementException("Book not found: " + isbn));

        return BookView.from(book);
    }

    @Transactional
    public void changePrice(String isbn, BigDecimal newPrice) {
        Book book = bookRepository.findByIsbn(isbn)
            .orElseThrow(() -> new NoSuchElementException("Book not found: " + isbn));

        book.changePrice(newPrice);
        // book đang managed; JPA sẽ phát hiện thay đổi khi flush.
    }
}
~~~

DTO dùng để trả dữ liệu ra ngoài service:

~~~java
package com.example.book.service;

import com.example.book.domain.Book;

import java.math.BigDecimal;

public record BookView(Long id, String title, String isbn, BigDecimal price) {

    public static BookView from(Book book) {
        return new BookView(
            book.getId(),
            book.getTitle(),
            book.getIsbn(),
            book.getPrice()
        );
    }
}
~~~

### Vì sao service là ranh giới transaction phù hợp?

Service thể hiện một hành động nghiệp vụ hoàn chỉnh. Trong phương thức **register**, kiểm tra ISBN và lưu sách cùng nằm trong một transaction. Trong phương thức **changePrice**, việc tải entity và thay đổi giá cùng nằm trong transaction.

**@Transactional** thường được áp dụng thông qua proxy của Spring. Vì vậy:

- Phương thức cần transaction phải được gọi thông qua Spring bean/proxy.
- Tự gọi một phương thức transactional khác trong cùng một instance (self-invocation) thường không đi qua proxy, nên annotation của phương thức được gọi có thể không được áp dụng như mong đợi.
- Hãy đặt transaction trên phương thức service có ý nghĩa nghiệp vụ rõ ràng và gọi service thông qua dependency được Spring quản lý.

Các phương thức CRUD kế thừa từ **JpaRepository** có cấu hình transaction mặc định của Spring Data JPA. Tuy nhiên, đặt transaction ở service vẫn hữu ích vì nó bao trọn nhiều thao tác repository và làm rõ đơn vị công việc. Query method tự khai báo không nên được giả định là luôn có transaction riêng; transaction của service sẽ bao quanh chúng trong luồng này.

### **readOnly = true** có ý nghĩa gì?

**@Transactional(readOnly = true)** thể hiện phương thức chủ yếu đọc dữ liệu. Đây là gợi ý cho transaction manager/provider tối ưu một số thao tác; nó không phải cơ chế phân quyền và không nên được xem là hàng rào bảo mật ngăn mọi lệnh ghi.

Không dùng **readOnly = true** cho phương thức có ý định thay đổi entity.

## 6. JPA quản lý entity và tự ghi thay đổi

JPA theo dõi entity thông qua persistence context (ngữ cảnh lưu trữ). Một entity thường trải qua các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Transient / New | Đối tượng Java mới tạo, chưa được persistence context quản lý |
| Managed | Được persistence context quản lý; thay đổi có thể được tự động đồng bộ |
| Detached | Từng được quản lý nhưng hiện không còn gắn với persistence context |
| Removed | Được đánh dấu để xóa khi đồng bộ |

Khi gọi **findByIsbn** trong một transaction đang hoạt động, JPA trả về entity managed. Nếu gọi:

~~~java
Book book = bookRepository.findByIsbn(isbn)
    .orElseThrow();
book.changePrice(newPrice);
~~~

thì thay đổi thuộc tính **price** được persistence context theo dõi. Khi flush, Hibernate so sánh trạng thái entity và phát lệnh **UPDATE** cần thiết. Vì entity vẫn managed trong transaction hiện tại, không cần gọi **bookRepository.save(book)** thêm lần nữa.

Điều này được gọi là dirty checking. Nó là một đặc điểm cốt lõi của JPA.

Ngược lại, nếu đối tượng đã detached, việc thay đổi field của nó không tự động được đồng bộ. Khi cần lưu trạng thái detached, có thể dùng **save**/**merge** đúng cách và sử dụng đối tượng được trả về. **save()** không đồng nghĩa lúc nào cũng phát một câu **UPDATE**; Spring Data JPA xác định entity mới hay đã tồn tại rồi phối hợp với JPA để persist hoặc merge.

## 7. Flush, commit và rollback

Ba khái niệm này có liên quan nhưng không giống nhau:

- **Flush**: đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng SQL. Flush không tự kết thúc transaction.
- **Commit**: xác nhận transaction thành công. Các thay đổi trở thành dữ liệu đã commit theo cơ chế transaction của database.
- **Rollback**: hủy các thay đổi của transaction chưa commit khi transaction thất bại.

Một phương thức service được gọi qua proxy thường có trình tự:

1. Spring mở transaction trước khi chạy phần thân phương thức.
2. Các thao tác repository tham gia transaction hiện tại theo propagation mặc định **REQUIRED**.
3. JPA theo dõi entity và các thay đổi trong persistence context.
4. Khi cần, JPA flush SQL xuống database; flush cũng có thể xảy ra tự động trước một truy vấn hoặc khi transaction kết thúc.
5. Nếu phương thức hoàn tất bình thường, Spring commit transaction.
6. Nếu có lỗi phù hợp quy tắc rollback, Spring rollback transaction.

Mặc định, Spring rollback với unchecked exception (**RuntimeException** và **Error**) nhưng không tự động rollback với mọi checked exception. Nếu nghiệp vụ cần rollback cho checked exception, có thể khai báo **rollbackFor** phù hợp, ví dụ **@Transactional(rollbackFor = Exception.class)**. Chỉ dùng cấu hình này khi đã xác định rõ chính sách lỗi của nghiệp vụ.

Ví dụ, nếu **register** lưu sách rồi phát sinh một unchecked exception trước khi kết thúc transaction, thao tác ghi thuộc transaction đó sẽ được rollback. Điều này giúp tránh trạng thái chỉ hoàn thành một nửa của nghiệp vụ.

## 8. Ràng buộc dữ liệu phải được bảo vệ ở database

Trong service có đoạn:

~~~java
if (bookRepository.existsByIsbn(isbn)) {
    throw new IllegalStateException("ISBN already exists");
}
~~~

Kiểm tra này giúp trả lỗi dễ hiểu khi ISBN đã tồn tại. Tuy nhiên, nó không đủ để bảo vệ tính duy nhất trong tình huống đồng thời:

1. Request A kiểm tra ISBN và nhận kết quả chưa tồn tại.
2. Request B cũng kiểm tra cùng ISBN và nhận kết quả chưa tồn tại.
3. Cả hai cùng tiếp tục insert.

Nếu chỉ dựa vào kiểm tra ở Java, hai request có thể cùng vượt qua bước kiểm tra. Unique constraint ở database là lớp bảo vệ cuối cùng. Khi hai insert cạnh tranh, database sẽ từ chối một insert vi phạm constraint.

Vì vậy, nên kết hợp:

- Kiểm tra trong service để tạo phản hồi nghiệp vụ rõ ràng.
- Unique constraint trong schema để bảo vệ tính toàn vẹn trước truy cập đồng thời.
- Xử lý lỗi constraint phù hợp ở tầng ứng dụng để chuyển thành phản hồi có ý nghĩa.

Tương tự, **nullable = false** trong mapping cần tương ứng với **NOT NULL** trong schema thực tế. Không nên giả định annotation tự sửa một database đã triển khai mà không kiểm tra cấu hình schema.

## 9. Cấu hình schema trong môi trường phát triển và production

Hibernate có thể được cấu hình để tạo hoặc kiểm tra schema. Trong môi trường học tập, **spring.jpa.hibernate.ddl-auto=create-drop** hoặc **update** có thể tiện để thử nghiệm. Tuy nhiên, không nên mặc định dùng **update** làm chiến lược quản lý schema production.

Với ứng dụng cần dữ liệu lâu dài, nên quản lý thay đổi schema bằng migration có phiên bản, chẳng hạn Flyway hoặc Liquibase. Ứng dụng có thể dùng **spring.jpa.hibernate.ddl-auto=validate** để kiểm tra mapping so với schema đã được migration tạo ra.

Các giá trị **create**, **create-drop**, **update** và **validate** có hành vi khác nhau. Hãy chọn theo vòng đời môi trường và chiến lược dữ liệu; không sao chép cấu hình development sang production mà chưa đánh giá tác động.

## 10. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không lưu được entity | Lớp thiếu **@Entity**, thiếu ID hoặc mapping sai | Kiểm tra annotation, constructor và schema |
| Lỗi thiếu constructor | Entity không có constructor không tham số phù hợp | Thêm constructor **protected** hoặc **public** không tham số |
| ID luôn null trong code | Chưa insert/flush hoặc chiến lược sinh ID chưa phù hợp | Kiểm tra transaction và chiến lược **@GeneratedValue** |
| Trùng ISBN | Chỉ kiểm tra ở service, thiếu unique constraint | Tạo unique constraint và xử lý lỗi vi phạm |
| Thay đổi entity nhưng database không đổi | Entity đã detached hoặc thay đổi ngoài transaction quản lý | Tải entity trong transaction và thay đổi khi entity còn managed |
| Gọi **save()** nhiều lần không cần thiết | Chưa hiểu dirty checking | Với entity managed, thay đổi field trong transaction là đủ |
| Transaction không có tác dụng | Gọi nội bộ trong cùng bean hoặc bean không do Spring quản lý | Gọi qua Spring proxy và đặt annotation ở service phù hợp |
| Dữ liệu chỉ được ghi một phần | Nhiều thao tác không nằm trong cùng transaction | Bao các thao tác nghiệp vụ liên quan trong một transaction |
| **@Column** không khớp database | Mapping và schema migration khác nhau | Đồng bộ migration với entity và dùng validate khi phù hợp |
| Dùng **double** cho tiền | Sai số biểu diễn số thực nhị phân | Dùng **BigDecimal** và precision/scale phù hợp |

## 11. Checklist khi thiết kế một entity mới

- [ ] Xác định lớp nào thực sự cần được lưu bền vững và đánh dấu **@Entity**.
- [ ] Chọn bảng bằng **@Table** khi cần tên hoặc constraint rõ ràng.
- [ ] Xác định khóa chính ổn định bằng **@Id**.
- [ ] Chọn chiến lược **@GeneratedValue** phù hợp database.
- [ ] Khai báo nullability, độ dài, precision, scale và unique constraint phù hợp.
- [ ] Giữ quy tắc bất biến quan trọng trong constructor hoặc phương thức domain.
- [ ] Tạo repository với đúng kiểu entity và kiểu khóa chính.
- [ ] Đặt transaction ở service theo ranh giới nghiệp vụ.
- [ ] Dùng DTO khi cần đưa dữ liệu qua ranh giới API.
- [ ] Đồng bộ entity mapping với migration/schema thực tế.

## 12. Kết luận qua mô hình Book

Trong mô hình này, **Book** là entity Java; **books** là bảng lưu trữ; **id** là khóa chính; **isbn** là khóa nghiệp vụ có unique constraint; **BookRepository** cung cấp thao tác dữ liệu; và **BookService** định nghĩa transaction cho từng hành động nghiệp vụ.

Khi tạo sách, service gọi repository để lưu entity. Khi đổi giá, service tải entity trong transaction rồi thay đổi thuộc tính; JPA dirty checking phát hiện thay đổi và đồng bộ xuống database khi flush. Transaction quyết định toàn bộ thao tác được commit hay rollback. Nắm được mối liên hệ này giúp bạn thiết kế tầng persistence rõ ràng và tránh nhầm lẫn giữa object Java, bảng dữ liệu, repository và đơn vị giao dịch.