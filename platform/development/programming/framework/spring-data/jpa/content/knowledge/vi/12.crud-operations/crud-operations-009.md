# delete, deleteById, deleteAll và ảnh hưởng đến callback

Spring Data JPA cung cấp nhiều cách xóa entity: **delete(entity)**, **deleteById(id)**, **deleteAll()**, **deleteAll(entities)** và các biến thể xóa theo lô. Tên phương thức có vẻ tương tự nhau, nhưng cách thực thi có thể khác đáng kể.

Khác biệt quan trọng nhất là: thao tác xóa theo vòng đời entity đi qua JPA EntityManager và có thể kích hoạt callback như **@PreRemove**, **@PostRemove** cùng cascade remove. Ngược lại, bulk delete bằng JPQL hoặc các phương thức batch thường thực hiện một lệnh DELETE trực tiếp, bỏ qua lifecycle callback và cascade của JPA.

Bài này giải thích cách các phương thức xóa phổ biến hoạt động, thời điểm callback được gọi, ảnh hưởng của cascade/orphanRemoval, giới hạn của bulk delete và cách chọn phương thức phù hợp.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên, Jakarta Persistence và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Đây là các tệp trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Những phương thức xóa thường gặp

Repository kế thừa **JpaRepository** có sẵn các phương thức:

| Phương thức | Ý nghĩa tổng quát | Cách thực hiện thường gặp |
|---|---|---|
| **delete(entity)** | Xóa một entity | Dùng entity lifecycle qua EntityManager |
| **deleteById(id)** | Xóa theo khóa chính | Tìm entity rồi xóa nếu tồn tại |
| **deleteAll()** | Xóa toàn bộ entity của repository | Tải entity rồi xóa từng entity |
| **deleteAll(entities)** | Xóa các entity được truyền vào | Xóa từng entity |
| **deleteAllById(ids)** | Xóa các entity theo danh sách ID | Xóa từng ID theo lifecycle |
| **deleteAllInBatch()** | Xóa toàn bộ bằng bulk query | Một truy vấn bulk DELETE |
| **deleteAllInBatch(entities)** | Xóa tập entity theo lô | Bulk DELETE theo ID |
| **deleteAllByIdInBatch(ids)** | Xóa tập ID theo lô | Bulk DELETE theo ID |

Các phương thức lifecycle và bulk có tác động khác nhau đến callback, cascade và persistence context. Đừng chọn chỉ dựa vào tên phương thức hoặc giả định tất cả đều gọi **EntityManager.remove()**.

## 2. Callback vòng đời entity khi xóa

Jakarta Persistence cung cấp hai callback chính cho thao tác xóa:

- **@PreRemove**: được gọi khi entity lifecycle remove được thực hiện, trước khi lệnh DELETE được thực thi.
- **@PostRemove**: được gọi sau khi thao tác xóa entity đã được thực thi tại database.

Ví dụ:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @Transient
    private boolean preRemoveInvoked;

    @Transient
    private boolean postRemoveInvoked;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    @PreRemove
    void beforeRemove() {
        preRemoveInvoked = true;
    }

    @PostRemove
    void afterRemove() {
        postRemoveInvoked = true;
    }

    public boolean isPreRemoveInvoked() {
        return preRemoveInvoked;
    }

    public boolean isPostRemoveInvoked() {
        return postRemoveInvoked;
    }
}
~~~

Hai field đánh dấu callback ở trên chỉ phục vụ minh họa/test; **@Transient** nghĩa là chúng không được lưu vào database.

Callback cũng có thể đặt trong entity listener:

~~~java
@Entity
@EntityListeners(BookLifecycleListener.class)
public class Book {
    // ...
}
~~~

~~~java
public class BookLifecycleListener {

    @PreRemove
    public void beforeRemove(Book book) {
        // Xử lý cục bộ trước khi entity bị xóa.
    }

    @PostRemove
    public void afterRemove(Book book) {
        // Được gọi sau khi thao tác DELETE của entity đã thực thi.
    }
}
~~~

Lifecycle callback có thể được dùng cho kiểm tra hoặc xử lý cục bộ gắn với entity. Tránh gọi truy vấn database, sửa quan hệ phức tạp hoặc thực hiện I/O bên ngoài như gửi email trong callback. Đặc biệt, **@PostRemove không đồng nghĩa transaction đã commit**: transaction vẫn có thể rollback sau khi callback chạy.

## 3. delete(entity): xóa một entity qua lifecycle

Ví dụ:

~~~java
@Transactional
public void deleteBook(Long id) {
    Book book = bookRepository.findById(id)
        .orElseThrow();

    bookRepository.delete(book);
}
~~~

Với entity managed, Spring Data JPA gọi cơ chế remove của EntityManager. Entity chuyển sang trạng thái removed; SQL DELETE được thực thi khi flush phù hợp.

Thông thường, luồng này kích hoạt:

- **@PreRemove**.
- CascadeType.REMOVE trên các association được cấu hình.
- orphanRemoval khi điều kiện tương ứng được đáp ứng.
- **@PostRemove** sau khi lệnh DELETE thực thi.

Nếu entity truyền vào đang detached, implementation của Spring Data JPA có thể tìm entity hiện có theo ID và xử lý remove thông qua một managed instance. Vì vậy, không nên dựa vào việc object truyền vào luôn là chính instance bị xóa. Nếu cần thay đổi nghiệp vụ trước khi xóa, cách rõ ràng là tải entity trong transaction rồi xóa entity managed đó.

Nếu entity được xem là mới hoặc không có bản ghi tương ứng, thao tác delete có thể là no-op theo implementation. Khi cần xác định chính xác hành vi với phiên bản Spring Data đang dùng, xem implementation **SimpleJpaRepository** và kiểm thử trên database thực tế.

## 4. deleteById(id): tìm theo ID rồi xóa

Ví dụ:

~~~java
bookRepository.deleteById(10L);
~~~

Trong implementation phổ biến của **SimpleJpaRepository**, deleteById tìm entity theo ID rồi gọi delete nếu tìm thấy. Vì vậy, đây là đường xóa theo lifecycle entity, không phải mặc định là một câu JPQL bulk DELETE.

Khi entity tồn tại, callback **@PreRemove** và **@PostRemove** có thể được kích hoạt. Cascade remove và orphanRemoval cũng được áp dụng theo mapping.

Nếu ID không tồn tại, deleteById thường không làm gì và không có callback remove cho entity không tồn tại.

Cần phân biệt:

- **deleteById**: thuận tiện khi chỉ có ID; thường phải tìm entity trước để thực hiện lifecycle remove.
- **delete(entity)**: dùng khi đã có entity instance.
- Cả hai đều không nên bị nhầm với bulk delete.

Nếu cần trả về thông báo nghiệp vụ “không tìm thấy”, hãy gọi **findById** trước và tự xử lý trường hợp vắng mặt. Không dựa vào deleteById để phân biệt lỗi không tồn tại nếu hợp đồng API cần phân biệt rõ.

## 5. deleteAll() và deleteAll(Iterable entities)

### deleteAll()

~~~java
bookRepository.deleteAll();
~~~

Với implementation tiêu chuẩn của Spring Data JPA, **deleteAll()** tải các entity rồi xóa từng entity qua delete. Vì vậy, các callback lifecycle và cascade JPA có thể chạy cho từng entity.

Đổi lại, phương thức này có thể tốn tài nguyên:

- Cần tải các entity vào bộ nhớ.
- Có thể phát sinh nhiều câu SELECT và DELETE.
- Cascade có thể làm tăng thêm số thao tác.
- Với bảng lớn, thời gian và bộ nhớ có thể tăng đáng kể.

Không dùng deleteAll() trên bảng lớn chỉ vì muốn xóa nhanh. Hãy xác định rõ có cần callback/cascade JPA hay không trước khi chọn.

### deleteAll(Iterable entities)

~~~java
List<Book> books = bookRepository.findAllById(ids);
bookRepository.deleteAll(books);
~~~

Phương thức này xóa các entity được truyền vào theo lifecycle. Nếu các entity còn managed, remove được gọi trực tiếp; nếu detached, implementation có thể tìm lại entity hiện có trước khi xóa.

Nếu collection có nhiều entity, vẫn cần cân nhắc bộ nhớ và số câu SQL. Phương thức này không tự biến thao tác thành một bulk DELETE duy nhất.

## 6. deleteAllById(ids): xóa nhiều ID theo lifecycle

Ví dụ:

~~~java
bookRepository.deleteAllById(List.of(10L, 11L, 12L));
~~~

Phương thức này thuận tiện khi chỉ có danh sách ID. Implementation thông thường xử lý từng ID bằng đường deleteById, do đó có thể tải từng entity và thực hiện remove.

Điều này có nghĩa callback và cascade JPA có thể được kích hoạt cho từng entity tồn tại. Đổi lại, số truy vấn có thể tăng theo số ID.

Nếu danh sách rất lớn và không cần lifecycle callback hoặc cascade JPA, hãy cân nhắc bulk delete. Nếu cần các hành vi lifecycle, giữ đường xóa từng entity và kiểm soát batch size/transaction phù hợp.

## 7. Bulk delete: deleteAllInBatch và deleteAllByIdInBatch

Spring Data JPA cung cấp các phương thức batch:

~~~java
bookRepository.deleteAllInBatch();
bookRepository.deleteAllByIdInBatch(ids);
~~~

Các phương thức này thực hiện bulk JPQL DELETE trực tiếp trên database thay vì tải từng entity rồi gọi remove.

Ví dụ truy vấn bulk tương đương:

~~~sql
DELETE FROM books;
~~~

Hoặc theo ID:

~~~sql
DELETE FROM books
WHERE id IN (?, ?, ?);
~~~

Bulk delete có ưu điểm:

- Ít thao tác round-trip hơn so với tải và xóa từng entity.
- Không cần khởi tạo toàn bộ entity trong bộ nhớ.
- Phù hợp với thao tác xóa số lượng lớn khi nghiệp vụ không cần lifecycle callback JPA.

Nhưng bulk delete bỏ qua entity lifecycle thông thường:

- Không gọi **@PreRemove** hoặc **@PostRemove** cho từng entity.
- Không kích hoạt cascade REMOVE của JPA.
- Không áp dụng orphanRemoval theo quy trình entity lifecycle.
- Không đồng bộ tự động các entity đang nằm trong persistence context với trạng thái database sau bulk query.

Nếu database có foreign key, database vẫn kiểm tra constraint. Nếu foreign key có **ON DELETE CASCADE**, database có thể tự xóa hàng phụ thuộc. Đây là hành vi của database, không phải cascade JPA.

### Persistence context có thể bị stale

Giả sử một Book đang managed trong persistence context. Sau đó ứng dụng gọi bulk DELETE để xóa hàng Book đó. Object Book trong bộ nhớ vẫn có thể tồn tại và được context xem là managed, dù hàng đã bị xóa ở database.

Điều này tạo ra trạng thái không đồng bộ giữa persistence context và database.

Trước bulk delete, cân nhắc flush các thay đổi đang chờ. Sau bulk delete, có thể clear persistence context hoặc refresh các entity liên quan nếu cần. Spring Data JPA có các tùy chọn **flushAutomatically** và **clearAutomatically** trên **@Modifying** cho bulk query tự khai báo:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Transactional
@Query("delete from Book b where b.archived = true")
int deleteArchivedBooks();
~~~

**clearAutomatically = true** sẽ clear persistence context sau truy vấn; tất cả entity managed trong context đó có thể trở thành detached. Chỉ bật khi hiểu rõ tác động tới các thay đổi và entity khác trong cùng transaction.

## 8. Derived delete query: deleteBy... khác bulk JPQL

Spring Data JPA cho phép khai báo derived delete query:

~~~java
@Transactional
long deleteByAuthorId(Long authorId);
~~~

Khác với bulk JPQL DELETE dùng **@Modifying @Query**, derived delete query của Spring Data JPA thường tìm các entity phù hợp rồi xóa từng entity để có thể áp dụng lifecycle callback.

Ví dụ:

~~~java
@Transactional
List<Book> deleteByArchivedTrue();
~~~

Tùy chữ ký và phiên bản Spring Data, method có thể trả về số lượng hoặc các entity đã xóa. Khi trả về entity, các object kết quả được materialize trước khi xóa; điều này có thể tốn bộ nhớ nếu kết quả lớn.

So sánh:

| Cách viết | Cách thực hiện | Lifecycle callback |
|---|---|---|
| **deleteById(id)** | Tìm entity rồi remove | Có thể chạy |
| **deleteAll()** | Tải và xóa từng entity trong implementation chuẩn | Có thể chạy |
| Derived **deleteBy...** | Tìm entity rồi xóa từng entity | Có thể chạy |
| **@Modifying @Query("delete ...")** | Bulk JPQL DELETE | Không chạy cho từng entity |
| **deleteAllInBatch()** | Bulk DELETE | Không chạy cho từng entity |

Đừng chỉ nhìn tên bắt đầu bằng delete để kết luận có hay không có callback. Hãy xác định phương thức là derived delete lifecycle hay bulk modifying query.

## 9. Callback không phải sự kiện sau commit

Một điểm dễ gây lỗi là dùng **@PostRemove** để gửi email, gọi HTTP hoặc phát thông báo tới hệ thống khác.

Ví dụ, callback được gọi sau khi SQL DELETE thực thi nhưng transaction vẫn chưa commit. Nếu một thao tác sau đó trong cùng transaction thất bại, database rollback và hàng bị xóa sẽ xuất hiện trở lại. Trong khi đó, email hoặc HTTP request đã gửi ra ngoài không tự được hoàn tác.

Vì vậy:

- Callback JPA nên giữ công việc cục bộ và ngắn.
- Không xem **@PostRemove** là **AFTER_COMMIT**.
- Nếu cần gửi sự kiện sau commit, dùng cơ chế sự kiện transaction-aware của Spring, chẳng hạn **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)**.
- Với yêu cầu bảo đảm gửi sự kiện bền vững, cân nhắc transactional outbox để ghi sự kiện trong cùng transaction database rồi worker gửi sau.

Ví dụ service phát sự kiện nghiệp vụ:

~~~java
@Transactional
public void deleteBook(Long id) {
    Book book = bookRepository.findById(id).orElseThrow();

    bookRepository.delete(book);
    publisher.publishEvent(new BookDeletedEvent(id));
}
~~~

Listener sau commit:

~~~java
@Component
public class BookDeletedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(BookDeletedEvent event) {
        // Gửi thông báo hoặc thực hiện tác vụ bên ngoài sau commit.
    }
}
~~~

Cách này đảm bảo listener chỉ chạy khi transaction chứa sự kiện commit thành công. Nếu yêu cầu không được mất sự kiện khi process dừng sau commit, cần cơ chế bền vững như outbox thay vì chỉ dựa vào in-memory event.

## 10. Kiểm thử callback và bulk delete

Một integration test có thể xác nhận lifecycle callback:

~~~java
@DataJpaTest
class BookDeleteLifecycleTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private BookRepository bookRepository;

    @Test
    void deleteTriggersRemoveCallbacks() {
        Book book = new Book("Spring Data JPA");
        entityManager.persist(book);
        entityManager.flush();

        bookRepository.delete(book);

        assertThat(book.isPreRemoveInvoked()).isTrue();

        entityManager.flush();

        assertThat(book.isPostRemoveInvoked()).isTrue();
    }
}
~~~

Test này giả định entity có callback đánh dấu transient như ví dụ ở phần trước. **@PreRemove** được kiểm tra khi remove được gọi; **@PostRemove** được kiểm tra sau khi flush thực thi thao tác DELETE.

Với bulk delete, có thể viết test riêng để xác nhận callback không được gọi cho từng entity. Trước khi kiểm tra database, clear persistence context hoặc đọc lại trong context mới để tránh trạng thái stale.

Không chỉ assert số lượng hàng còn lại. Hãy kiểm tra callback, cascade và trạng thái persistence context nếu đó là hành vi quan trọng của nghiệp vụ.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Callback không chạy khi xóa hàng loạt | Dùng bulk JPQL hoặc batch delete | Dùng lifecycle delete nếu cần callback |
| Cascade REMOVE không chạy | Bulk DELETE bỏ qua entity lifecycle | Dùng remove từng entity hoặc database FK cascade phù hợp |
| Entity trong bộ nhớ vẫn tồn tại sau bulk delete | Persistence context không được đồng bộ | Flush trước và clear/refresh sau bulk query |
| Xóa chậm khi dùng deleteAll | Tải và xóa từng entity, callback/cascade tăng số SQL | Chọn batch delete nếu không cần lifecycle |
| Derived delete có nhiều truy vấn | Spring Data tải entity rồi xóa từng entity | Đánh giá trade-off giữa callback và hiệu năng |
| Gửi email nhưng transaction rollback | Dùng @PostRemove như callback sau commit | Dùng AFTER_COMMIT event hoặc outbox |
| Database từ chối xóa do foreign key | Còn hàng phụ thuộc và không có cascade phù hợp | Xác định chính sách xóa, FK và thứ tự xóa |
| Callback thấy trạng thái object không như mong đợi | Nhầm thời điểm callback với thời điểm commit | Kiểm tra lifecycle và transaction timing |

## 12. Checklist chọn phương thức xóa

- [ ] Xác định có cần **@PreRemove** hoặc **@PostRemove** hay không.
- [ ] Xác định có cần CascadeType.REMOVE hoặc orphanRemoval hay không.
- [ ] Dùng **delete(entity)** khi đã có entity và cần lifecycle behavior.
- [ ] Dùng **deleteById(id)** khi có ID; nhớ entity tồn tại mới có lifecycle remove.
- [ ] Dùng **deleteAll()** hoặc **deleteAll(entities)** khi cần xóa từng entity và chấp nhận chi phí tải/xóa.
- [ ] Dùng **deleteAllById(ids)** khi cần xóa danh sách ID theo lifecycle.
- [ ] Dùng **deleteAllInBatch()** hoặc bulk JPQL khi ưu tiên hiệu năng và chấp nhận bỏ qua callback/cascade JPA.
- [ ] Flush trước bulk query nếu cần giữ thay đổi đang chờ.
- [ ] Clear/refresh persistence context sau bulk query khi có entity liên quan đang managed.
- [ ] Không gửi thông báo bên ngoài trong **@PostRemove**.
- [ ] Dùng **AFTER_COMMIT** hoặc outbox cho side effect cần xảy ra sau khi commit.
- [ ] Kiểm thử trên database thực tế với constraint và cascade tương ứng.

## 13. Kết luận

Các phương thức **delete**, **deleteById**, **deleteAll** và derived **deleteBy...** thường đi qua entity lifecycle nên có thể kích hoạt callback và cascade JPA. Các phương thức batch và bulk JPQL thực hiện DELETE trực tiếp, không gọi callback cho từng entity và không áp dụng cascade JPA theo lifecycle thông thường.

Hãy chọn phương thức xóa theo yêu cầu nghiệp vụ: cần callback/cascade thì dùng lifecycle remove; cần xóa số lượng lớn và không cần các hành vi đó thì cân nhắc bulk delete. Luôn phân biệt callback sau khi SQL thực thi với sự kiện sau transaction commit, đồng thời quản lý persistence context sau bulk query để tránh dữ liệu stale.