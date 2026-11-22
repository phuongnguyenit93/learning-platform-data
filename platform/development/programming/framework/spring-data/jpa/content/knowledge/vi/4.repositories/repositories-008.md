# Phân biệt phương thức CRUD kế thừa và phương thức truy vấn tự khai báo trong Spring Data JPA

Spring Data JPA giúp thao tác dữ liệu thông qua repository interface. Khi kế thừa JpaRepository, repository nhận được các phương thức CRUD có sẵn như save, findById, findAll và deleteById. Khi cần truy vấn theo nghiệp vụ, ta khai báo thêm phương thức trong interface, chẳng hạn findByAuthorIgnoreCase hoặc một phương thức gắn với @Query.

Hai nhóm phương thức có cách định nghĩa và mục đích khác nhau. Hiểu đúng sự khác biệt giúp repository ngắn gọn, dễ đọc và tránh viết lại những chức năng Spring Data đã cung cấp.

## 1. Repository hoạt động như thế nào?

Repository là tầng truy cập dữ liệu. Với Spring Data JPA, ta thường tạo một interface kế thừa JpaRepository:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

Hai tham số kiểu của JpaRepository là:

- Book: kiểu entity mà repository quản lý.
- Long: kiểu dữ liệu của khóa chính trong entity Book.

Spring Data tạo implementation dạng proxy cho interface khi ứng dụng khởi động. Ta chỉ cần inject BookRepository vào service hoặc controller và gọi phương thức. Framework thực hiện phần truy cập dữ liệu qua JPA provider, thường là Hibernate.

Luồng xử lý cơ bản:

~~~mermaid
flowchart TD
    A[Service hoặc Controller] --> B[BookRepository interface]
    B --> C{Loại phương thức}
    C --> D[CRUD kế thừa]
    C --> E[Query method tự khai báo]
    D --> F[Spring Data repository implementation]
    E --> F
    F --> G[JPA EntityManager / Hibernate]
    G --> H[(Database)]
~~~

Repository interface không cần tự viết lớp triển khai cho các phương thức chuẩn. Tuy nhiên, mỗi phương thức tự khai báo vẫn phải có quy tắc truy vấn mà Spring Data có thể phân tích hoặc có phần định nghĩa truy vấn rõ ràng.

## 2. Phương thức CRUD kế thừa là gì?

Phương thức CRUD kế thừa là những phương thức đã được định nghĩa trong các interface nền tảng như CrudRepository, ListCrudRepository, PagingAndSortingRepository và JpaRepository. Khi repository của ứng dụng kế thừa JpaRepository, nó nhận được các thao tác phổ biến để tạo, đọc, cập nhật và xóa entity.

Ví dụ:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
    // Đã có sẵn các phương thức CRUD.
}
~~~

Không cần khai báo lại save, findById, findAll hoặc deleteById nếu chỉ sử dụng hành vi chuẩn.

### Các phương thức CRUD thường dùng

| Phương thức kế thừa | Ý nghĩa | Kiểu kết quả thường gặp |
|---|---|---|
| save(entity) | Lưu entity mới hoặc cập nhật entity | Entity đã lưu |
| saveAll(entities) | Lưu một tập entity | Danh sách entity |
| findById(id) | Tìm một entity theo khóa chính | Optional<T> |
| existsById(id) | Kiểm tra khóa chính có tồn tại | boolean |
| findAll() | Lấy tất cả entity | List<T> khi dùng JpaRepository |
| findAllById(ids) | Lấy entity theo danh sách khóa chính | List<T> |
| count() | Đếm số entity | long |
| deleteById(id) | Xóa entity theo khóa chính | void |
| delete(entity) | Xóa entity được truyền vào | void |
| deleteAll() | Xóa tất cả entity | void |

Kiểu trả về phụ thuộc interface nền tảng. Nếu kế thừa CrudRepository trực tiếp, findAll() và findAllById() trả về Iterable<T>. Với JpaRepository trong các phiên bản Spring Data hiện đại, các hợp đồng CRUD dạng List được sử dụng nên findAll() trả về List<T>.

JpaRepository còn cung cấp các chức năng liên quan đến JPA và phân trang/sắp xếp:

| Phương thức | Mục đích |
|---|---|
| findAll(Sort sort) | Lấy dữ liệu có sắp xếp |
| findAll(Pageable pageable) | Lấy một trang dữ liệu |
| flush() | Đồng bộ persistence context với database |
| saveAndFlush(entity) | Lưu entity và flush ngay |
| saveAllAndFlush(entities) | Lưu nhiều entity và flush |
| getReferenceById(id) | Lấy tham chiếu entity, thường có thể là proxy tải lười |
| deleteAllInBatch() | Xóa hàng loạt bằng thao tác bulk |

Một số phương thức batch có hành vi khác thao tác xóa từng entity. Bulk delete/update có thể bỏ qua lifecycle callback của entity và làm persistence context đang giữ dữ liệu cũ. Chỉ dùng chúng khi đã hiểu tác động tới cascade, cache và trạng thái entity.

### Ví dụ sử dụng CRUD kế thừa

~~~java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Book create(Book book) {
        return repository.save(book);
    }

    public Optional<Book> findOne(Long id) {
        return repository.findById(id);
    }

    public List<Book> findAll() {
        return repository.findAll();
    }

    public boolean exists(Long id) {
        return repository.existsById(id);
    }

    public void delete(Long id) {
        repository.deleteById(id);
    }
}
~~~

Các phương thức này phù hợp với thao tác tổng quát theo entity hoặc khóa chính. Chúng không cần biết nghiệp vụ cụ thể như tìm theo tác giả, lọc theo trạng thái hay tìm theo một đoạn tiêu đề.

### Lưu ý về save()

save() không đồng nghĩa lúc nào cũng thực hiện INSERT. Spring Data JPA xác định entity có phải entity mới hay không, sau đó thường gọi persist cho entity mới hoặc merge cho entity đã tồn tại. Với merge, đối tượng được trả về có thể là instance được quản lý khác với instance truyền vào. Vì vậy nên sử dụng giá trị trả về:

~~~java
Book saved = repository.save(book);
~~~

Không nên giả định gọi save() sẽ luôn phát sinh SQL ngay tại dòng lệnh đó. JPA có thể trì hoãn SQL đến thời điểm flush hoặc commit transaction.

### Lưu ý về findById() và getReferenceById()

findById(id) thực hiện thao tác tìm kiếm và trả về Optional<T>, phù hợp khi cần biết entity có tồn tại hay không.

getReferenceById(id) lấy một tham chiếu entity và có thể trả về proxy chưa tải dữ liệu ngay. Nếu khóa không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được truy cập. Hai phương thức không thay thế cho nhau.

## 3. Phương thức truy vấn tự khai báo là gì?

Phương thức truy vấn tự khai báo là phương thức do lập trình viên thêm vào repository interface để phục vụ nhu cầu truy vấn cụ thể. Spring Data có thể tạo truy vấn từ tên phương thức (derived query), hoặc sử dụng truy vấn được khai báo bằng annotation @Query.

Ví dụ:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByAuthorIgnoreCase(String author);

    Optional<Book> findByIsbn(String isbn);

    boolean existsByTitleIgnoreCase(String title);
}
~~~

Ba phương thức trên không phải phương thức CRUD chuẩn được kế thừa từ JpaRepository. Chúng được khai báo trong BookRepository để mô tả điều kiện truy vấn riêng của ứng dụng.

Có hai cách phổ biến để định nghĩa query method:

1. Derived query: Spring Data phân tích tên phương thức và suy ra điều kiện truy vấn.
2. Declared query: lập trình viên viết truy vấn rõ ràng bằng @Query, có thể dùng JPQL hoặc SQL gốc.

## 4. Derived query: tạo truy vấn từ tên phương thức

Derived query là cách khai báo truy vấn ngắn gọn bằng quy tắc đặt tên. Spring Data phân tích tiền tố, tên thuộc tính và từ khóa trong tên phương thức để tạo câu truy vấn.

Ví dụ entity Book có các thuộc tính title, author, isbn và published:

~~~java
List<Book> findByAuthor(String author);
~~~

Spring Data hiểu phương thức này là tìm các Book có thuộc tính author bằng giá trị truyền vào.

Ví dụ khác:

~~~java
List<Book> findByAuthorIgnoreCase(String author);

List<Book> findByTitleContainingIgnoreCase(String keyword);

List<Book> findByAuthorAndPublishedTrue(String author);

List<Book> findByPriceGreaterThan(BigDecimal minPrice);

List<Book> findByPublishedTrueOrderByTitleAsc();

Optional<Book> findByIsbn(String isbn);

boolean existsByTitleIgnoreCase(String title);

long countByPublishedTrue();

List<Book> findTop5ByOrderByTitleAsc();
~~~

Ý nghĩa:

- IgnoreCase: so sánh chuỗi không phân biệt chữ hoa/chữ thường.
- Containing: tìm chuỗi con, thường tương đương điều kiện LIKE với dấu phần trăm hai phía.
- And: kết hợp nhiều điều kiện bằng AND.
- PublishedTrue: kiểm tra thuộc tính boolean published có giá trị true.
- GreaterThan: so sánh lớn hơn.
- OrderByTitleAsc: sắp xếp theo title tăng dần.
- Top5: giới hạn kết quả ở tối đa năm bản ghi.
- existsBy: kiểm tra có bản ghi phù hợp hay không.
- countBy: đếm số bản ghi phù hợp.

### Một số từ khóa thường gặp

| Từ khóa | Ý nghĩa | Ví dụ |
|---|---|---|
| And | Kết hợp điều kiện AND | findByAuthorAndPublishedTrue |
| Or | Kết hợp điều kiện OR | findByAuthorOrTitle |
| Between | Nằm trong một khoảng | findByPriceBetween |
| LessThan | Nhỏ hơn | findByPriceLessThan |
| LessThanEqual | Nhỏ hơn hoặc bằng | findByPriceLessThanEqual |
| GreaterThan | Lớn hơn | findByPriceGreaterThan |
| IsNull | Giá trị null | findByPublishedAtIsNull |
| IsNotNull | Khác null | findByPublishedAtIsNotNull |
| In | Thuộc tập giá trị | findByAuthorIn |
| NotIn | Không thuộc tập giá trị | findByAuthorNotIn |
| Like | So khớp mẫu LIKE | findByTitleLike |
| Containing | Chứa chuỗi con | findByTitleContaining |
| StartingWith | Bắt đầu bằng | findByTitleStartingWith |
| EndingWith | Kết thúc bằng | findByTitleEndingWith |
| IgnoreCase | Không phân biệt hoa thường | findByAuthorIgnoreCase |
| OrderBy | Sắp xếp kết quả | findByPublishedTrueOrderByTitleDesc |
| Distinct | Loại bỏ kết quả trùng | findDistinctByAuthor |
| Top / First | Giới hạn số kết quả | findTop10ByOrderByTitleAsc |
| ExistsBy | Kiểm tra tồn tại | existsByIsbn |
| CountBy | Đếm kết quả | countByPublishedTrue |
| DeleteBy / RemoveBy | Xóa các entity phù hợp | deleteByPublishedFalse |

Từ khóa và tên thuộc tính phải khớp với mô hình entity. Derived query tham chiếu tên thuộc tính Java, không phải tên cột vật lý trong database.

### Chọn kiểu trả về

Kiểu trả về cho biết cách ứng dụng muốn nhận kết quả:

~~~java
Book findFirstByAuthorOrderByTitleAsc(String author);

Optional<Book> findByIsbn(String isbn);

List<Book> findByAuthor(String author);

Page<Book> findByPublishedTrue(Pageable pageable);

Slice<Book> findByAuthor(String author, Pageable pageable);

boolean existsByIsbn(String isbn);

long countByAuthor(String author);
~~~

- Dùng Optional<T> khi dự kiến có tối đa một kết quả và muốn thể hiện khả năng không tìm thấy.
- Dùng List<T> khi cần danh sách kết quả và chấp nhận tải toàn bộ danh sách.
- Dùng Page<T> khi cần dữ liệu một trang cùng thông tin tổng số phần tử/trang; thường có thêm truy vấn đếm.
- Dùng Slice<T> khi chỉ cần biết còn trang tiếp theo hay không, có thể tránh truy vấn tổng số bản ghi.
- Dùng boolean cho truy vấn tồn tại và long cho truy vấn đếm.

Nếu truy vấn có thể trả nhiều bản ghi, không nên khai báo Optional<T> hoặc một entity đơn lẻ trừ khi điều kiện được bảo đảm duy nhất. Nếu không, Spring Data có thể ném lỗi khi kết quả có nhiều hơn một dòng.

### Phân trang và sắp xếp

Ví dụ gọi repository từ service:

~~~java
Page<Book> page = repository.findByPublishedTrue(
        PageRequest.of(0, 20, Sort.by("title").ascending())
);
~~~

PageRequest.of(0, 20, ...) yêu cầu trang đầu tiên với tối đa 20 kết quả. Chỉ số trang bắt đầu từ 0. Tên thuộc tính trong Sort là thuộc tính entity, ví dụ title.

Dùng Page khi giao diện cần tổng số trang hoặc tổng số kết quả. Dùng Slice khi giao diện chỉ cần nút tải thêm và muốn tránh chi phí đếm tổng số dòng trên các tập dữ liệu lớn.

## 5. Khai báo truy vấn tường minh bằng @Query

Khi tên phương thức quá dài hoặc điều kiện phức tạp, có thể khai báo câu truy vấn bằng @Query.

### JPQL

JPQL truy vấn theo entity và thuộc tính Java, không truy vấn trực tiếp theo tên bảng/cột vật lý:

~~~java
@Query("select b from Book b where lower(b.author) = lower(:author)")
List<Book> searchByAuthor(@Param("author") String author);
~~~

Trong ví dụ:

- Book là tên entity.
- b.author là thuộc tính author của entity.
- :author là named parameter.
- @Param("author") liên kết tham số Java với tham số trong JPQL.
- lower() chuyển chuỗi về chữ thường để so sánh.

Một truy vấn khác có điều kiện nhiều trường:

~~~java
@Query("""
       select b
       from Book b
       where b.published = true
         and b.price >= :minimumPrice
       order by b.price desc
       """)
List<Book> findPublishedBooksAbovePrice(
        @Param("minimumPrice") BigDecimal minimumPrice);
~~~

Text block của Java 17 giúp viết JPQL nhiều dòng dễ đọc. JPQL hỗ trợ truy vấn theo mô hình đối tượng và được JPA provider chuyển thành SQL phù hợp với database.

### SQL gốc với nativeQuery

Nếu cần dùng cú pháp riêng của database hoặc truy vấn SQL đã được tối ưu, có thể khai báo native query:

~~~java
@Query(
    value = "select * from books where author = :author",
    nativeQuery = true
)
List<Book> findByAuthorUsingSql(@Param("author") String author);
~~~

Với native query:

- Câu truy vấn dùng tên bảng và tên cột của database.
- Cú pháp phụ thuộc hệ quản trị, có thể không di chuyển được giữa MySQL, PostgreSQL và H2.
- Kết quả có thể ánh xạ vào entity hoặc projection phù hợp.
- Cần kiểm tra SQL và mapping khi đổi database.

Ưu tiên JPQL khi truy vấn phù hợp với mô hình entity. Dùng native query khi có lý do rõ ràng như tính năng SQL riêng, CTE, window function hoặc truy vấn đặc thù mà JPQL không diễn đạt thuận tiện.

## 6. Truy vấn cập nhật và xóa với @Modifying

@Query thông thường được dùng cho truy vấn đọc. Khi câu JPQL hoặc SQL thực hiện UPDATE/DELETE, cần đánh dấu phương thức bằng @Modifying.

Ví dụ repository:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Book b set b.published = :published where b.id = :id")
    int updatePublishedStatus(
            @Param("id") Long id,
            @Param("published") boolean published);

    @Modifying
    @Query("delete from Book b where b.published = false")
    int deleteUnpublishedBooks();
}
~~~

Phương thức cập nhật trả về số dòng bị tác động. Cần gọi trong transaction, thường đặt transaction ở service:

~~~java
@Service
public class BookMaintenanceService {

    private final BookRepository repository;

    public BookMaintenanceService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int publish(Long id) {
        return repository.updatePublishedStatus(id, true);
    }

    @Transactional
    public int removeDrafts() {
        return repository.deleteUnpublishedBooks();
    }
}
~~~

Các điểm cần chú ý:

- @Modifying báo cho Spring Data biết query là thao tác thay đổi dữ liệu.
- @Transactional xác định ranh giới transaction; nên đặt ở service nếu thao tác là một phần của nghiệp vụ.
- flushAutomatically yêu cầu flush các thay đổi đang chờ trước khi chạy bulk query.
- clearAutomatically yêu cầu xóa persistence context sau query để tránh tiếp tục dùng entity cũ trong bộ nhớ.
- Bulk update/delete tác động trực tiếp lên database và không cập nhật từng entity đang được quản lý như thao tác thông thường. Nó có thể bỏ qua entity lifecycle callback và cơ chế dirty checking.

Không dùng bulk query nếu nghiệp vụ phụ thuộc vào callback, cascade hoặc logic được thực thi khi thay đổi từng entity mà chưa thiết kế cách xử lý tương ứng.

## 7. Ví dụ repository hoàn chỉnh

Entity minh họa:

~~~java
package com.example.library;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String author;

    @Column(nullable = false, unique = true)
    private String isbn;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean published;

    protected Book() {
    }

    public Book(
            String title,
            String author,
            String isbn,
            BigDecimal price,
            boolean published) {
        this.title = title;
        this.author = author;
        this.isbn = isbn;
        this.price = price;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthor() {
        return author;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isPublished() {
        return published;
    }
}
~~~

Repository kết hợp cả ba nhóm: CRUD kế thừa, derived query và truy vấn tường minh:

~~~java
package com.example.library;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {

    // Derived query: Spring Data suy ra điều kiện từ tên phương thức.
    List<Book> findByAuthorIgnoreCaseAndPublishedTrueOrderByTitleAsc(
            String author);

    Optional<Book> findByIsbn(String isbn);

    boolean existsByTitleIgnoreCase(String title);

    long countByPublishedTrue();

    Page<Book> findByPublishedTrue(Pageable pageable);

    // Declared JPQL query: truy vấn được viết rõ bằng @Query.
    @Query("""
           select b
           from Book b
           where lower(b.title) like lower(concat('%', :keyword, '%'))
           """)
    List<Book> searchTitle(@Param("keyword") String keyword);

    // Native SQL: dùng tên bảng/cột trong database.
    @Query(
        value = "select * from books where author = :author",
        nativeQuery = true
    )
    List<Book> findByAuthorNative(@Param("author") String author);

    // Bulk update: cần @Modifying và transaction khi gọi.
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Book b set b.published = true where b.id = :id")
    int publishById(@Param("id") Long id);
}
~~~

Ví dụ này cho thấy không cần khai báo lại save(), findById(), findAll() hoặc deleteById(). Chỉ các truy vấn riêng của nghiệp vụ mới được thêm vào interface.

## 8. So sánh hai nhóm phương thức

| Tiêu chí | CRUD kế thừa | Query method tự khai báo |
|---|---|---|
| Nguồn định nghĩa | Interface nền tảng của Spring Data | Repository interface của ứng dụng |
| Mục tiêu | CRUD tổng quát và thao tác repository chuẩn | Truy vấn theo điều kiện nghiệp vụ |
| Cách sử dụng | Gọi trực tiếp sau khi kế thừa JpaRepository | Khai báo phương thức mới |
| Cách tạo truy vấn | Implementation chuẩn của Spring Data | Phân tích tên phương thức hoặc dùng @Query |
| Ví dụ | save, findById, findAll, deleteById | findByAuthor, existsByIsbn, searchTitle |
| Mức độ tùy biến | Hành vi chuẩn, tổng quát | Có thể mô tả điều kiện, join, projection và SQL riêng |
| Khi nên dùng | Khi thao tác đúng theo CRUD cơ bản | Khi cần lọc, tìm kiếm, đếm, phân trang hoặc nghiệp vụ riêng |

Cần phân biệt hai loại query method tự khai báo:

| Loại | Cách định nghĩa | Khi phù hợp |
|---|---|---|
| Derived query | Đặt tên theo quy ước, ví dụ findByAuthorAndPublishedTrue | Điều kiện đơn giản, tên dễ hiểu |
| Declared query | Viết JPQL/SQL với @Query | Điều kiện phức tạp, join, projection hoặc SQL đặc thù |

## 9. Nên chọn cách nào trong từng tình huống?

- Lưu entity mới hoặc cập nhật entity: dùng save().
- Tìm entity theo khóa chính: dùng findById().
- Lấy danh sách tất cả entity: dùng findAll(), cân nhắc phân trang khi dữ liệu lớn.
- Xóa theo khóa chính: dùng deleteById().
- Tìm theo một hoặc vài thuộc tính: dùng derived query như findByAuthorIgnoreCase().
- Kiểm tra một điều kiện có bản ghi hay không: dùng existsBy...().
- Đếm theo điều kiện: dùng countBy...().
- Truy vấn nhiều điều kiện nhưng tên vẫn ngắn, dễ hiểu: tiếp tục dùng derived query.
- Truy vấn có join, biểu thức hoặc cấu trúc phức tạp: cân nhắc @Query JPQL.
- Truy vấn cần tính năng riêng của database: cân nhắc native SQL và kiểm tra tính tương thích.
- Truy vấn động với nhiều điều kiện tùy chọn: cân nhắc Specification, Criteria API, Querydsl hoặc custom repository implementation.

Không nên tạo phương thức có tên quá dài, khó đọc và khó kiểm tra. Khi tên derived query trở nên phức tạp, chuyển sang @Query hoặc một cơ chế truy vấn phù hợp hơn.

## 10. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| No property found for type | Tên thuộc tính trong derived query không tồn tại trong entity | Kiểm tra chính tả và đường dẫn thuộc tính Java |
| Failed to create query for method | Tên phương thức sai quy tắc hoặc kiểu tham số không phù hợp | Kiểm tra từ khóa, kiểu dữ liệu và tên thuộc tính |
| Incorrect JPQL | Dùng tên bảng/cột SQL trong JPQL | Dùng tên entity và thuộc tính Java |
| Native query không chạy khi đổi DB | SQL phụ thuộc dialect hoặc tên cột | Kiểm tra cú pháp theo DB đích và viết test tích hợp |
| NonUniqueResultException | Phương thức trả về một entity/Optional nhưng query có nhiều kết quả | Dùng List hoặc đảm bảo điều kiện duy nhất bằng constraint |
| Modifying query requires transaction | UPDATE/DELETE chạy ngoài transaction | Gọi từ service có @Transactional hoặc cấu hình transaction phù hợp |
| Entity trong bộ nhớ không phản ánh bulk update | Bulk query bỏ qua trạng thái entity đang được quản lý | Flush/clear persistence context hoặc tải lại entity |
| findAll gây chậm | Tải toàn bộ bảng lớn vào bộ nhớ | Dùng Pageable hoặc Slice |

Một lỗi derived query thường được phát hiện khi Spring khởi động và tạo repository. Vì vậy, cần chạy ứng dụng hoặc test repository sau khi thêm/sửa tên phương thức, không chỉ dựa vào việc code biên dịch thành công.

## 11. Kiểm thử repository

Có thể dùng @DataJpaTest để kiểm tra entity mapping và query method trong phạm vi persistence. Ví dụ:

~~~java
package com.example.library;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository repository;

    @Test
    void findsPublishedBooksByAuthorIgnoringCase() {
        repository.save(new Book(
                "Spring in Action",
                "Craig Walls",
                "ISBN-001",
                new BigDecimal("39.90"),
                true));

        repository.save(new Book(
                "Another Book",
                "Craig Walls",
                "ISBN-002",
                new BigDecimal("29.90"),
                false));

        var result = repository
                .findByAuthorIgnoreCaseAndPublishedTrueOrderByTitleAsc(
                        "CRAIG WALLS");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getTitle()).isEqualTo("Spring in Action");
    }

    @Test
    void findsBookByInheritedIdMethod() {
        Book saved = repository.save(new Book(
                "Effective Java",
                "Joshua Bloch",
                "ISBN-003",
                new BigDecimal("45.00"),
                true));

        var found = repository.findById(saved.getId());

        assertThat(found).isPresent();
        assertThat(found.get().getIsbn()).isEqualTo("ISBN-003");
    }
}
~~~

@DataJpaTest thường cấu hình một database kiểm thử nhúng nếu có trên classpath và chạy transaction cho từng test, rollback sau test. Nếu cần xác nhận hành vi SQL đặc thù của MySQL hoặc PostgreSQL, nên kiểm thử với đúng hệ quản trị đó, ví dụ thông qua Testcontainers.

## 12. Checklist tự đánh giá

- [ ] Giải thích được JpaRepository cung cấp các phương thức CRUD kế thừa.
- [ ] Biết rằng save() có thể lưu mới hoặc cập nhật entity.
- [ ] Phân biệt findById() với getReferenceById().
- [ ] Tạo được derived query từ tên thuộc tính và từ khóa.
- [ ] Chọn đúng kiểu trả về List, Optional, Page hoặc Slice.
- [ ] Biết dùng Pageable và Sort cho phân trang/sắp xếp.
- [ ] Viết được JPQL bằng @Query và liên kết tham số bằng @Param.
- [ ] Phân biệt JPQL với native SQL.
- [ ] Biết dùng @Modifying cho UPDATE/DELETE và đặt transaction phù hợp.
- [ ] Hiểu tác động của bulk query tới persistence context.
- [ ] Biết khi nào nên dùng CRUD kế thừa, derived query, @Query hoặc custom repository.
- [ ] Viết được test cho phương thức kế thừa và phương thức truy vấn tự khai báo.

## 13. Kết luận

CRUD kế thừa từ JpaRepository đáp ứng các thao tác dữ liệu tổng quát mà hầu hết repository cần có. Query method tự khai báo bổ sung khả năng truy vấn theo nghiệp vụ mà không phải tự viết lớp repository implementation.

Với điều kiện đơn giản, derived query thường ngắn và dễ bảo trì. Khi truy vấn phức tạp, @Query giúp thể hiện rõ JPQL hoặc SQL cần chạy. Chọn đúng loại phương thức giúp code ít trùng lặp, repository dễ hiểu và hành vi truy cập dữ liệu dễ kiểm thử.
