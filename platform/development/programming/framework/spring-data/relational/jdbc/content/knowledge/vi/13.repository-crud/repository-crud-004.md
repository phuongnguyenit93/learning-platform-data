# save và saveAll: kết quả trả về cùng phạm vi thao tác trong Spring Data JDBC

## 1. Vai trò của save và saveAll

Trong Spring Data JDBC, repository cung cấp các thao tác CRUD để lưu aggregate vào database. Hai phương thức thường dùng là:

- **§save(entity)§:** lưu một entity/aggregate root và trả về entity đã được lưu.
- **§saveAll(entities)§:** lưu nhiều entity/aggregate root và trả về tập các entity đã được lưu.

Ví dụ:

~~~java
Book saved = bookRepository.save(book);

Iterable<Book> savedBooks = bookRepository.saveAll(books);
~~~

Điểm quan trọng là **giá trị trả về có thể khác object đầu vào**. Trong quá trình lưu, Spring Data JDBC có thể nhận ID do database sinh, cập nhật version, chạy lifecycle callback hoặc tạo một instance mới nếu entity bất biến. Vì vậy, nên sử dụng kết quả trả về để tiếp tục xử lý.

Ngoài kết quả trả về, cần hiểu **phạm vi transaction**: một lần gọi repository có thể được thực thi trong một transaction theo cấu hình mặc định; nhiều lần gọi repository trong một nghiệp vụ cần một ranh giới transaction ở service nếu phải cùng thành công hoặc cùng rollback.

## 2. save(entity): lưu một aggregate và nhận lại kết quả

Trong §CrudRepository§, chữ ký phương thức là:

~~~java
<S extends T> S save(S entity);
~~~

Phương thức nhận entity và trả về một entity cùng kiểu cụ thể §S§. Với Spring Data JDBC, repository thường đại diện cho aggregate root; khi lưu root, các thành phần thuộc aggregate cũng được xử lý theo mapping của aggregate.

Ví dụ:

~~~java
Book input = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(input);

System.out.println(saved.getId());
~~~

Nếu database sinh ID, §saved§ chứa ID mới. Không nên giả định §input.getId()§ luôn được cập nhật hoặc luôn bằng ID trả về, đặc biệt với entity bất biến.

### 2.1. Vì sao phải dùng object trả về?

Có ba lý do thường gặp:

1. **Generated ID:** database tạo khóa chính sau khi INSERT; framework đưa giá trị đó vào kết quả đã lưu.
2. **Optimistic locking:** nếu entity dùng §@Version§, version có thể được cập nhật khi ghi.
3. **Immutable object:** record hoặc class bất biến không thể thay đổi field; framework có thể trả về một instance mới mang ID/version đã cập nhật.

Ví dụ với record:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
        @Id Long id,
        String title,
        BigDecimal price
) {}
~~~

Lưu mới:

~~~java
Book input = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(input);

System.out.println("Input ID: " + input.id());
System.out.println("Saved ID: " + saved.id());
~~~

Với record, §input§ không thể được sửa tại chỗ. §saved§ là kết quả cần sử dụng cho các thao tác tiếp theo:

~~~java
Long bookId = saved.id();
Book loaded = bookRepository.findById(bookId).orElseThrow();
~~~

**Quy tắc thực hành:** luôn gán kết quả của §save§ vào biến và truyền kết quả đó qua các bước tiếp theo. Đừng phụ thuộc vào việc framework có mutate object đầu vào hay không.

## 3. save quyết định INSERT hay UPDATE như thế nào?

§save§ không đơn giản có nghĩa là “luôn INSERT” hoặc “luôn UPDATE”. Spring Data xác định entity có phải entity mới hay không, rồi chọn thao tác persistence tương ứng.

Với chiến lược phát hiện trạng thái mặc định thường gặp:

- Nếu entity có property §@Version§, trạng thái version được xét trước; version null (với kiểu tham chiếu) thường cho biết entity mới.
- Nếu không có version property, identifier được dùng để nhận biết entity mới; identifier null thường biểu thị entity mới.
- Nếu entity triển khai §Persistable§, phương thức §isNew()§ có thể cung cấp quyết định riêng.

Bảng khái quát:

| Trạng thái | Hướng xử lý thông thường |
|---|---|
| Entity mới, ID null | INSERT |
| Entity đã tồn tại, ID có giá trị | UPDATE |
| Entity có version null | Thường được nhận diện là mới |
| Entity có ID tự gán trước khi lưu | Có thể bị nhận diện là đã tồn tại nếu không có chiến lược khác |

Chi tiết phát hiện entity mới phụ thuộc kiểu ID/version và cơ chế mà entity sử dụng. Khi dùng ID do ứng dụng gán sẵn, cần thiết kế rõ cách Spring Data biết object mới hay đã tồn tại; không nên kỳ vọng §save§ luôn tự thử UPDATE rồi tự chuyển sang INSERT nếu không tìm thấy hàng.

### 3.1. Ví dụ INSERT

Entity mới:

~~~java
Book book = new Book(
        null,
        "Spring Data JDBC",
        new BigDecimal("199000.00")
);

Book saved = bookRepository.save(book);
~~~

SQL về mặt ý tưởng:

~~~sql
INSERT INTO books (title, price)
VALUES (?, ?);
~~~

Database sinh ID theo schema, rồi Spring Data JDBC nhận lại giá trị phù hợp với dialect/driver.

### 3.2. Ví dụ UPDATE

Đọc entity đã tồn tại, thay đổi dữ liệu và lưu:

~~~java
Book existing = bookRepository.findById(bookId)
        .orElseThrow();

Book changed = new Book(
        existing.id(),
        "Spring Data JDBC - Updated",
        existing.price()
);

Book updated = bookRepository.save(changed);
~~~

SQL về mặt ý tưởng:

~~~sql
UPDATE books
SET title = ?, price = ?
WHERE id = ?;
~~~

Spring Data JDBC không theo dõi mọi thay đổi trên object trong bộ nhớ như dirty checking của JPA. Việc thay đổi một thuộc tính không tự gửi UPDATE; cần gọi thao tác lưu thích hợp.

## 4. saveAll(Iterable<S>): lưu nhiều entity

Trong §CrudRepository§, chữ ký phương thức là:

~~~java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
~~~

Phương thức nhận một §Iterable§ và trả về một §Iterable§ chứa các entity đã được lưu. Ví dụ:

~~~java
List<Book> input = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000")),
        new Book(null, "Book C", new BigDecimal("150000"))
);

Iterable<Book> savedBooks = bookRepository.saveAll(input);
~~~

Kết quả trả về không nên bị bỏ qua nếu ứng dụng cần ID, version hoặc instance mới của từng entity:

~~~java
for (Book saved : savedBooks) {
    System.out.println(saved.id() + " - " + saved.title());
}
~~~

### 4.1. saveAll không đồng nghĩa với một câu INSERT

Tên phương thức có chữ “All” không bảo đảm database nhận đúng **một câu SQL** để lưu tất cả entity. Với Spring Data JDBC, mỗi aggregate có thể cần một hoặc nhiều câu lệnh để lưu root và các thành phần con. Việc thực thi cũng phụ thuộc implementation, dialect và driver.

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Một lần gọi §saveAll§ | Một lời gọi API repository với nhiều entity |
| Một transaction | Một ranh giới commit/rollback cho các thao tác trong phạm vi đó |
| JDBC batch | Cơ chế gom nhiều statement cùng dạng để gửi/thi hành theo batch |
| Một câu SQL | Một statement duy nhất gửi đến database |

§saveAll§ là API lưu nhiều entity, **không phải cam kết JDBC batch hoặc một statement duy nhất**. Nếu cần tối ưu ghi khối lượng lớn, hãy đo hiệu năng và chọn chiến lược phù hợp, chẳng hạn JDBC batch qua §JdbcTemplate.batchUpdate§ khi dữ liệu có cấu trúc SQL phù hợp. Cách đó không tự thực hiện aggregate mapping hoặc lifecycle của Spring Data JDBC.

### 4.2. Kết quả saveAll và collection đầu vào

§saveAll§ nhận §Iterable§ để không buộc caller phải dùng riêng §List§. Với §CrudRepository§, kiểu trả về là §Iterable<S>§. Một số phiên bản/hệ thống có thể sử dụng §ListCrudRepository§, nơi các phương thức tương ứng trả về §List<S>§.

Khi viết code, hãy dựa trên **interface repository mà ứng dụng thực sự kế thừa** và kiểu trả về IDE/compiler hiển thị, thay vì ép kiểu mù quáng:

~~~java
Iterable<Book> saved = bookRepository.saveAll(input);
~~~

Nếu API trả về §Iterable§, có thể chuyển thành list khi thật sự cần:

~~~java
List<Book> savedList = StreamSupport
        .stream(saved.spliterator(), false)
        .toList();
~~~

Chuyển thành list sẽ tiêu thụ iterable để tạo một collection mới. Với dữ liệu lớn, cân nhắc bộ nhớ và không materialize toàn bộ kết quả nếu chỉ cần xử lý từng phần tử.

Không nên giả định collection đầu vào sẽ được mutate hoặc chứa ID mới sau khi gọi §saveAll§. Hãy đọc các instance trong **kết quả trả về**.

## 5. Kết quả trả về với entity có ID và version

### 5.1. ID do database sinh

Giả sử bảng:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Entity:

~~~java
@Table("books")
public record Book(
        @Id Long id,
        String title,
        BigDecimal price
) {}
~~~

Lưu nhiều entity mới:

~~~java
List<Book> inputs = List.of(
        new Book(null, "Book A", new BigDecimal("100000")),
        new Book(null, "Book B", new BigDecimal("120000"))
);

Iterable<Book> saved = bookRepository.saveAll(inputs);

for (Book book : saved) {
    // Sử dụng ID đã có trong kết quả saveAll.
    log.info("Saved book id={}", book.id());
}
~~~

Mỗi entity mới cần được ghi và nhận giá trị ID phù hợp. Nếu bỏ qua kết quả, ứng dụng có thể không có ID để liên kết dữ liệu tiếp theo hoặc trả kết quả cho caller.

### 5.2. Optimistic locking với @Version

Một entity có version:

~~~java
@Table("books")
public record Book(
        @Id Long id,
        @Version Long version,
        String title,
        BigDecimal price
) {}
~~~

Version giúp Spring Data JDBC phát hiện cập nhật dựa trên phiên bản mà caller đã đọc. Khi lưu thành công, version có thể được tăng. Nếu một transaction khác đã cập nhật bản ghi trước đó, lần lưu với version cũ có thể thất bại do optimistic locking.

Ví dụ:

~~~java
Book loaded = bookRepository.findById(bookId).orElseThrow();

Book changed = new Book(
        loaded.id(),
        loaded.version(),
        "New title",
        loaded.price()
);

Book saved = bookRepository.save(changed);

// Dùng saved.version() cho trạng thái mới.
~~~

Với object bất biến, kết quả trả về là nơi lấy version mới. Nếu tiếp tục dùng object cũ với version cũ, lần cập nhật sau có thể bị từ chối vì dữ liệu đã lỗi thời.

### 5.3. Khi saveAll chứa cả entity mới và entity đã tồn tại

Một iterable có thể chứa các entity ở nhiều trạng thái khác nhau. Spring Data xác định trạng thái từng entity theo metadata của entity đó; các phần tử mới có thể đi theo INSERT, phần tử đã tồn tại có thể đi theo UPDATE.

Không nên giả định tất cả phần tử trong §saveAll§ đều là INSERT. Cũng không nên giả định việc có ID nghĩa là database chắc chắn đang có hàng tương ứng; chiến lược phát hiện entity mới và trạng thái thực tế của database phải nhất quán.

## 6. saveAll và phạm vi transaction

Đây là phần quan trọng khi một nghiệp vụ cần ghi nhiều entity như một đơn vị.

Spring Data repository CRUD methods thường được cấu hình transaction theo mặc định. Khi gọi một phương thức repository thông qua proxy, cấu hình transaction của repository áp dụng cho lần gọi đó nếu transaction manager tương ứng đã được cấu hình.

Ví dụ:

~~~java
bookRepository.saveAll(books);
~~~

Với cấu hình CRUD repository mặc định, lời gọi §saveAll§ thường chạy trong transaction của phương thức repository. Nếu một thao tác ghi trong phạm vi đó phát sinh runtime exception và exception thoát ra ngoài, transaction có thể rollback theo chính sách transaction đang áp dụng.

Tuy nhiên, khi một nghiệp vụ gồm nhiều lần gọi repository riêng, nên đặt transaction ở service để xác định rõ toàn bộ phạm vi nghiệp vụ:

~~~java
@Service
public class CatalogService {

    private final BookRepository books;
    private final AuthorRepository authors;

    public CatalogService(
            BookRepository books,
            AuthorRepository authors
    ) {
        this.books = books;
        this.authors = authors;
    }

    @Transactional
    public void createAuthorAndBooks(
            Author author,
            List<Book> newBooks
    ) {
        Author savedAuthor = authors.save(author);

        List<Book> booksWithAuthor = newBooks.stream()
                .map(book -> book.withAuthorId(savedAuthor.id()))
                .toList();

        books.saveAll(booksWithAuthor);
    }
}
~~~

Trong ví dụ này, §@Transactional§ ở service thể hiện rằng tạo tác giả và lưu danh sách sách là một thao tác nghiệp vụ. Nếu các repository sử dụng cùng transaction manager/DataSource phù hợp, các lời gọi tham gia cùng transaction.

### 6.1. Hai lần save không tự động là một transaction chung

Ví dụ:

~~~java
bookRepository.save(bookA);
bookRepository.save(bookB);
~~~

Nếu không có transaction bao quanh ở tầng service, mỗi lời gọi repository có thể có transaction riêng theo cấu hình mặc định. Nếu lần đầu thành công nhưng lần thứ hai thất bại, lần đầu có thể đã commit.

Nếu hai bản ghi phải cùng thành công hoặc cùng thất bại:

~~~java
@Transactional
public void savePair(Book bookA, Book bookB) {
    bookRepository.save(bookA);
    bookRepository.save(bookB);
}
~~~

Hoặc dùng §saveAll§ nếu chúng là các aggregate cùng một repository và nghiệp vụ phù hợp:

~~~java
@Transactional
public Iterable<Book> saveBooks(List<Book> books) {
    return bookRepository.saveAll(books);
}
~~~

Transaction của service cũng giúp kết hợp nhiều thao tác khác nhau trong cùng use case, thay vì chỉ một repository method.

### 6.2. saveAll có phải luôn atomic không?

Không nên trả lời chỉ dựa vào tên phương thức. Tính atomic phụ thuộc:

- Repository method có được chạy trong transaction hay không.
- Transaction manager có được cấu hình đúng và quản lý cùng DataSource không.
- Database/table engine có hỗ trợ transaction không.
- Lỗi có làm transaction rollback theo policy hay không.
- Ứng dụng có bắt và nuốt exception bên trong transaction hay không.

Với cấu hình Spring Data JDBC thông dụng trên database hỗ trợ transaction, CRUD repository method thường có transaction boundary. Dù vậy, nếu tính nguyên tử là yêu cầu nghiệp vụ, hãy khai báo rõ §@Transactional§ ở service và kiểm thử trường hợp lỗi giữa chừng.

Mặc định Spring transaction rollback với §RuntimeException§ và §Error§; checked exception thường không tự rollback nếu không cấu hình §rollbackFor§ thích hợp. Nếu code bắt exception rồi tiếp tục, transaction có thể vẫn commit hoặc đã bị đánh dấu rollback-only tùy lỗi và transaction manager. Không nên che giấu lỗi persistence.

### 6.3. Self-invocation và proxy

§@Transactional§ trong cấu hình proxy mặc định chỉ được áp dụng khi lời gọi đi qua Spring proxy. Một method trong cùng object gọi method khác có annotation trên chính object đó thường không đi qua proxy:

~~~java
public void importBooks(List<Book> books) {
    this.saveAllInTransaction(books); // self-invocation
}

@Transactional
public void saveAllInTransaction(List<Book> books) {
    bookRepository.saveAll(books);
}
~~~

Trong ví dụ này, annotation trên §saveAllInTransaction§ có thể không mở transaction như mong đợi khi được gọi bằng §this§. Hãy đặt transaction ở method public được gọi từ bean khác hoặc tách use case sang bean service phù hợp.

## 7. saveAll không thay thế xử lý theo lô lớn

Với vài entity hoặc một tập aggregate có kích thước vừa phải, §saveAll§ là API tiện lợi. Nhưng nếu cần nhập hàng trăm nghìn hoặc hàng triệu hàng, cần đánh giá:

- Số câu SQL thực tế được phát sinh.
- Số lượng aggregate và số lượng child mỗi aggregate.
- Bộ nhớ dùng để giữ input và kết quả.
- Thời gian transaction và lock duration.
- Giới hạn parameter của database/driver.
- Khả năng retry và xử lý bản ghi lỗi.
- Yêu cầu lifecycle callback và mapping aggregate.

### 7.1. Chia chunk

Ví dụ xử lý từng nhóm để giới hạn bộ nhớ và phạm vi công việc:

~~~java
@Transactional
public void importBooks(List<Book> input) {
    int chunkSize = 500;

    for (int start = 0; start < input.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, input.size());
        List<Book> chunk = input.subList(start, end);

        Iterable<Book> savedChunk = bookRepository.saveAll(chunk);

        for (Book saved : savedChunk) {
            // Xử lý ID/version từ kết quả của chunk này.
        }
    }
}
~~~

Trong ví dụ trên, toàn bộ method vẫn nằm trong **một transaction** vì annotation bao quanh method. Chia chunk chỉ chia nhóm xử lý trong code, không tự tạo transaction riêng cho từng chunk.

Nếu muốn commit theo từng chunk, cần thiết kế transaction boundary khác (ví dụ method riêng với propagation phù hợp hoặc một orchestration rõ ràng). Điều đó thay đổi semantics: chunk trước có thể đã commit dù chunk sau thất bại.

### 7.2. JDBC batch khi cần hiệu năng ghi thuần

Nếu dữ liệu là các dòng đơn giản và không cần aggregate mapping/lifecycle của Spring Data JDBC, có thể cân nhắc:

~~~java
jdbcTemplate.batchUpdate(
        "INSERT INTO audit_events (event_type, message) VALUES (?, ?)",
        events,
        500,
        (ps, event) -> {
            ps.setString(1, event.type());
            ps.setString(2, event.message());
        }
);
~~~

§batchUpdate§ là cơ chế JDBC batch rõ ràng hơn cho SQL thuần. Tuy nhiên:

- Không tự gọi repository lifecycle.
- Không tự ánh xạ aggregate.
- Không tự thực hiện quy tắc new-state detection của entity.
- Không tự đồng bộ ID/version vào entity như repository.
- Cần tự quyết định transaction và xử lý lỗi.

Chọn công cụ dựa trên yêu cầu: aggregate persistence dùng repository; bulk SQL thuần có thể dùng JDBC batch.

## 8. save và saveAll với aggregate có child

Trong Spring Data JDBC, repository lưu aggregate root và các thành phần thuộc aggregate. Ví dụ:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        LocalDate orderedOn,
        @MappedCollection(idColumn = "order_id", keyColumn = "line_number")
        List<OrderLine> lines
) {}
~~~

Gọi:

~~~java
PurchaseOrder savedOrder = orderRepository.save(order);
~~~

hoặc:

~~~java
Iterable<PurchaseOrder> savedOrders =
        orderRepository.saveAll(orders);
~~~

có nghĩa là lưu các aggregate root được truyền vào, bao gồm dữ liệu con theo mapping. Không phải chỉ ghi một hàng vào bảng root.

Một aggregate có thể cần nhiều SQL statement:

1. INSERT/UPDATE bảng root.
2. Ghi dữ liệu child trong bảng liên quan.
3. Duy trì khóa ngoại và collection key theo mapping.
4. Thực hiện các thao tác xóa/thay thế child cần thiết khi cập nhật aggregate.

Vì vậy, §saveAll§ với 100 aggregate có thể phát sinh nhiều hơn 100 statement. Đừng suy luận hiệu năng chỉ từ số phần tử của iterable.

### 8.1. Kết quả trả về aggregate bất biến

Nếu root là record hoặc immutable class, kết quả §save§ có thể chứa root ID và các giá trị đã được cập nhật. Hãy giữ kết quả aggregate đã lưu nếu cần sử dụng ID của root hoặc dữ liệu được tạo trong lifecycle.

Ví dụ:

~~~java
PurchaseOrder saved = orderRepository.save(inputOrder);
Long orderId = saved.id();
~~~

Không nên tiếp tục dùng §inputOrder§ để lấy ID nếu nó được tạo với ID null.

### 8.2. Đừng dùng saveAll để thay thế ranh giới aggregate

Nếu nhiều object con thuộc cùng một root, chúng nên được biểu diễn trong aggregate theo thiết kế domain và lưu thông qua root. Nếu các object thực sự là các aggregate độc lập, có repository riêng, §saveAll§ có thể lưu một tập các root đó.

Một iterable chứa các object con không tự biến chúng thành aggregate root. Hãy xác định repository đang quản lý kiểu aggregate nào và phương thức §saveAll§ đang nhận loại entity nào.

## 9. Ví dụ service trả về kết quả đã lưu

Một service có thể trả về danh sách entity đã được lưu để caller sử dụng ID mới:

~~~java
@Service
public class BookImportService {

    private final BookRepository books;

    public BookImportService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public List<Book> importBooks(List<Book> input) {
        Iterable<Book> saved = books.saveAll(input);

        List<Book> result = new ArrayList<>();
        saved.forEach(result::add);

        return result;
    }
}
~~~

Caller:

~~~java
List<Book> savedBooks = bookImportService.importBooks(input);

List<Long> ids = savedBooks.stream()
        .map(Book::id)
        .toList();
~~~

Ví dụ này materialize kết quả thành §List§ vì caller cần stream để lấy ID. Nếu repository interface trả về §List§ ngay từ đầu, có thể trả trực tiếp. Nếu dữ liệu rất lớn, hãy cân nhắc cách xử lý streaming/chunk để tránh giữ toàn bộ kết quả trong bộ nhớ.

## 10. Lỗi thường gặp khi dùng save và saveAll

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ID sau save vẫn null | Đọc ID từ object đầu vào bất biến hoặc generated key chưa được cấu hình/hỗ trợ | Dùng object trả về; kiểm tra identity, dialect và driver |
| Entity có ID nhưng bị UPDATE thay vì INSERT | Cơ chế phát hiện entity mới xem ID đã được gán là entity tồn tại | Thiết kế §isNew()§/§Persistable§ hoặc version phù hợp |
| saveAll chạy lâu dù chỉ có một lời gọi | Mỗi aggregate/child có thể cần nhiều SQL; không có bảo đảm JDBC batch | Đo SQL, chia chunk hoặc chọn JDBC batch cho SQL thuần |
| Một số entity không được lưu | Lỗi constraint, conversion, mapping hoặc transaction | Đọc exception gốc và kiểm tra schema/data |
| Lưu hai entity nhưng chỉ một entity được giữ | Hai lời gọi save có transaction riêng hoặc transaction boundary không như mong muốn | Đặt §@Transactional§ ở service |
| Lỗi ở phần tử cuối nhưng dữ liệu trước vẫn còn | Không có transaction chung, exception bị bắt hoặc database không rollback | Kiểm tra transaction manager, rollback policy và database |
| Version dùng lại giá trị cũ | Caller bỏ qua object trả về hoặc đang dùng entity stale | Tiếp tục với version từ kết quả mới |
| saveAll trả về Iterable nhưng code ép List | Dựa vào kiểu trả về không đúng interface | Dùng §Iterable§ hoặc materialize tường minh |
| Input collection không có ID sau saveAll | Kỳ vọng framework mutate mọi phần tử đầu vào | Duyệt kết quả trả về để lấy ID/version |
| Aggregate child bị ghi lại ngoài dự kiến | Chưa hiểu lifecycle aggregate khi save root | Kiểm tra mapping và thiết kế aggregate boundary |

## 11. Bài tập thực hành

### Bài 1 — Dùng kết quả save

Tạo một §Book§ mới với ID null, gọi §save§, sau đó in ID của object đầu vào và object trả về. Thử với class mutable và Java record. Giải thích vì sao code nên dùng object trả về.

### Bài 2 — saveAll và generated ID

Tạo danh sách ba §Book§ mới, gọi §saveAll§, duyệt kết quả và thu thập ID. Kiểm tra số entity trả về và trạng thái dữ liệu trong database.

### Bài 3 — Trộn INSERT và UPDATE

Tạo một entity mới và một entity đã tồn tại, đưa cả hai vào §saveAll§. Quan sát trạng thái newness và thao tác SQL. Thử một entity có ID gán sẵn nhưng chưa có hàng trong database.

### Bài 4 — Version

Thêm §@Version§ vào entity. Đọc một entity, cập nhật qua repository, sau đó thử lưu một instance cũ mang version trước đó. Quan sát lỗi optimistic locking và dùng version từ kết quả mới.

### Bài 5 — Transaction với saveAll

Tạo một danh sách trong đó một phần tử vi phạm unique constraint. Gọi §saveAll§ trong một service có §@Transactional§, để exception thoát ra và kiểm tra các phần tử trước đó có rollback không. Lặp lại khi bỏ transaction ở service và so sánh với các lần gọi §save§ riêng.

### Bài 6 — Phân biệt batch và saveAll

Lưu nhiều bản ghi qua §saveAll§, bật SQL logging để quan sát số statement. Viết một ví dụ §JdbcTemplate.batchUpdate§ cho bảng log đơn giản và so sánh khả năng mapping/lifecycle.

### Bài 7 — Lưu aggregate

Tạo nhiều §PurchaseOrder§, mỗi order có các §OrderLine§. Gọi §saveAll§ trên repository root. Kiểm tra cả bảng root và child, sau đó cập nhật một aggregate và quan sát cách các hàng con được đồng bộ.

## 12. Ghi nhớ

- §save(entity)§ trả về entity đã được lưu; §saveAll(iterable)§ trả về tập các entity đã được lưu. Luôn dùng kết quả trả về khi cần ID, version hoặc instance bất biến mới.
- §save§ chọn INSERT hay UPDATE dựa trên cơ chế phát hiện entity mới, không chỉ dựa vào ý nghĩa tên phương thức.
- §saveAll§ không mặc nhiên là một SQL statement hoặc JDBC batch; một aggregate có thể cần nhiều statement.
- CRUD repository methods có transaction semantics mặc định khi được gọi qua repository proxy và có transaction manager phù hợp. Đặt §@Transactional§ ở service khi nhiều thao tác phải cùng thành công hoặc cùng rollback.
- Hai lần gọi §save§ riêng không tự động tạo một transaction nghiệp vụ chung nếu không có transaction bao quanh.
- Với §@Version§, tiếp tục dùng version từ object trả về để tránh lưu bằng trạng thái cũ.
- Khi lưu aggregate, repository quản lý root và các thành phần con theo mapping; số SQL có thể lớn hơn số root.
- Với bulk SQL thuần, JDBC batch có thể phù hợp hơn, nhưng nó không thay thế aggregate mapping và lifecycle của Spring Data JDBC.
