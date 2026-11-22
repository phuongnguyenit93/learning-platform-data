# `readOnly` là gợi ý tối ưu và giới hạn bảo vệ dữ liệu

Trong Spring Data JPA, thuộc tính `readOnly` của `@Transactional` diễn đạt rằng một giao dịch chủ yếu dùng để đọc dữ liệu. Spring có thể chuyển thông tin này cho transaction manager, JDBC driver hoặc JPA provider để tối ưu việc xử lý. Tuy nhiên, `readOnly = true` là một **gợi ý ở tầng giao dịch**, không phải cam kết phổ quát rằng mọi câu lệnh ghi đều bị chặn.

Khi thiết kế giao dịch, cần phân biệt ba việc: khai báo ý định chỉ đọc trong ứng dụng, tối ưu mà framework/provider có thể thực hiện, và cơ chế thực sự ngăn ghi ở cơ sở dữ liệu. Ba việc này có liên quan nhưng không tương đương.

## 1. `readOnly` có ý nghĩa gì?

Có thể khai báo một phương thức chỉ đọc như sau:

~~~java
@Transactional(readOnly = true)
public List<Book> findBooks(String author) {
    return bookRepository.findByAuthor(author);
}
~~~

`readOnly` là một thuộc tính của định nghĩa giao dịch trong Spring. Giá trị mặc định là `false`. Khi đặt thành `true`, ứng dụng thông báo rằng giao dịch này không có mục đích thay đổi dữ liệu.

Transaction manager có thể dùng thông tin đó để chuẩn bị giao dịch theo cách phù hợp. Tùy cấu hình và nền tảng, nó có thể đặt cờ read-only trên JDBC connection hoặc truyền thuộc tính giao dịch xuống JPA provider. Một số hệ quản trị cơ sở dữ liệu có thể thực thi giao dịch chỉ đọc nếu nhận được thiết lập tương ứng. Một số driver hoặc provider chỉ xem đây là gợi ý tối ưu, hoặc không hỗ trợ đầy đủ.

Vì vậy, không nên hiểu đoạn mã trên như một lệnh SQL phổ quát kiểu “chỉ cho phép SELECT”. Annotation không tự tạo ra quyền truy cập ở cấp cơ sở dữ liệu và cũng không thay thế việc kiểm soát quyền của tài khoản kết nối.

## 2. Spring Data JPA có thể tối ưu giao dịch chỉ đọc như thế nào?

### 2.1. Ở tầng Spring và transaction manager

Spring lưu thuộc tính `readOnly` trong transaction definition. Khi bắt đầu giao dịch, transaction manager có thể áp dụng thuộc tính này nếu nó và nền tảng bên dưới hỗ trợ.

Với JDBC, một transaction manager có thể gọi `Connection.setReadOnly(true)`. Theo JDBC, đây là gợi ý cho driver; mức độ hỗ trợ và việc cơ sở dữ liệu có từ chối câu lệnh ghi hay không phụ thuộc driver và hệ quản trị cơ sở dữ liệu. Những transaction manager hoặc cấu hình khác có thể xử lý thuộc tính này theo cách khác.

### 2.2. Ở tầng JPA provider

Với Hibernate và cấu hình tích hợp Spring phù hợp, giao dịch chỉ đọc thường được tối ưu bằng cách chuyển flush mode sang `MANUAL`. Hibernate khi đó không tự động flush persistence context theo quy trình thông thường tại các thời điểm flush tự động. Tích hợp Hibernate cũng có thể đánh dấu các entity được tải trong giao dịch là read-only để giảm công việc dirty checking.

Các tối ưu này có thể giảm chi phí khi đọc nhiều entity hoặc xử lý một đồ thị đối tượng lớn. Hiệu quả cụ thể phụ thuộc phiên bản Hibernate, cách cấu hình transaction manager và cách ứng dụng truy cập dữ liệu.

JPA là đặc tả, còn Hibernate, EclipseLink và các provider khác có cơ chế nội bộ riêng. Không nên suy ra rằng mọi provider đều đặt cùng flush mode hoặc có cùng hành vi chỉ vì phương thức được đánh dấu `readOnly = true`.

### 2.3. Ở tầng cơ sở dữ liệu

Cơ sở dữ liệu có thể hỗ trợ giao dịch chỉ đọc ở cấp SQL hoặc cấp session. Nếu ứng dụng cần bảo đảm tài khoản chỉ được đọc, phải cấu hình quyền phù hợp trong cơ sở dữ liệu, chẳng hạn dùng tài khoản chỉ có quyền `SELECT`, hoặc một kết nối/replica được thiết lập để chỉ phục vụ truy vấn đọc.

Chỉ đặt annotation trong mã Java không đủ để tạo ra bảo đảm này. Muốn biết một thao tác ghi có bị từ chối hay không, cần kiểm tra cấu hình thực tế của transaction manager, driver và hệ quản trị cơ sở dữ liệu đang chạy.

## 3. Đặt ranh giới giao dịch ở đâu?

Thông thường, tầng service là nơi phù hợp để khai báo ranh giới giao dịch. Một phương thức service có thể gọi nhiều repository trong cùng một giao dịch, giúp toàn bộ thao tác đọc dùng chung một persistence context.

Spring Data JPA có cấu hình giao dịch sẵn cho các phương thức CRUD được kế thừa từ implementation mặc định `SimpleJpaRepository`: các thao tác đọc được đánh dấu read-only, còn các thao tác ghi có cấu hình giao dịch riêng. Tuy nhiên, các query method do ứng dụng tự khai báo thường không tự nhận cấu hình giao dịch mặc định. Có thể khai báo `@Transactional` trên query method hoặc, thường dễ quản lý hơn, khai báo ở service gọi repository.

Không nên rải annotation theo cảm tính ở mọi repository method. Hãy xác định nghiệp vụ nào là một đơn vị công việc, rồi đặt ranh giới giao dịch ở nơi điều phối nghiệp vụ đó.

## 4. Ví dụ: tách thao tác đọc và ghi

Ví dụ dưới đây giả định dự án đã có entity `Book` với các phương thức `getId()`, `getTitle()` và `setTitle(...)`, cùng cấu hình Spring Data JPA. Các đoạn mã dùng Java 17 trở lên.

Repository khai báo truy vấn theo tác giả:

~~~java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByAuthor(String author);
}
~~~

DTO trả về cho phía gọi:

~~~java
public record BookSummary(Long id, String title) {}
~~~

Service tách rõ phương thức đọc và phương thức cập nhật:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public List<BookSummary> findByAuthor(String author) {
        return books.findByAuthor(author)
                .stream()
                .map(book -> new BookSummary(book.getId(), book.getTitle()))
                .toList();
    }

    @Transactional
    public void renameBook(Long id, String newTitle) {
        Book book = books.findById(id).orElseThrow();
        book.setTitle(newTitle);
    }
}
~~~

Trong `findByAuthor`, giao dịch được đánh dấu chỉ đọc vì phương thức chỉ truy vấn và chuyển dữ liệu sang DTO. Việc ánh xạ sang DTO ngay trong ranh giới giao dịch cũng giúp tránh phụ thuộc vào lazy-loaded association sau khi giao dịch kết thúc.

Trong `renameBook`, `@Transactional` không đặt `readOnly = true`, nên giao dịch dùng chế độ đọc/ghi mặc định. Entity lấy từ repository đang được quản lý bởi persistence context. Khi phương thức kết thúc và giao dịch commit, JPA provider có thể dùng dirty checking để phát hiện thay đổi và ghi xuống cơ sở dữ liệu; vì vậy ví dụ không cần gọi `save(book)` lần nữa.

Nếu một nghiệp vụ vừa đọc vừa cập nhật, hãy dùng giao dịch đọc/ghi cho toàn bộ nghiệp vụ đó. Đừng đánh dấu giao dịch là read-only chỉ vì phần lớn câu lệnh bên trong là truy vấn.

## 5. `readOnly = true` bảo đảm điều gì và không bảo đảm điều gì?

| Tình huống | Cách hiểu đúng |
|---|---|
| Đánh dấu phương thức đọc bằng `@Transactional(readOnly = true)` | Thể hiện ý định chỉ đọc và cho phép các thành phần hỗ trợ áp dụng tối ưu. |
| Gọi `save()` hoặc một thao tác ghi trong giao dịch read-only | Annotation không bảo đảm thao tác sẽ luôn bị chặn. Hành vi phụ thuộc transaction manager, provider, driver và cơ sở dữ liệu. |
| Thay đổi một entity đang được quản lý | Provider có thể không tự động flush hoặc có thể giảm dirty checking trong chế độ read-only; không được dựa vào điều này như một cơ chế bảo vệ dữ liệu. |
| Muốn cấm một tài khoản ứng dụng cập nhật dữ liệu | Phải cấu hình quyền ở cơ sở dữ liệu hoặc cơ chế kiểm soát truy cập tương đương. |
| Muốn tối ưu truy vấn đọc | Dùng read-only transaction khi phù hợp, sau đó đo lường trên đúng provider và cơ sở dữ liệu của ứng dụng. |

Một ví dụ dễ gây nhầm lẫn là:

~~~java
@Transactional(readOnly = true)
public void renameBook(Long id, String newTitle) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.setTitle(newTitle);
}
~~~

Đây là cách khai báo sai ý định vì phương thức đang thay đổi dữ liệu. Với Hibernate, flush mode read-only có thể khiến thay đổi không được tự động flush như giao dịch đọc/ghi thông thường. Nhưng không thể kết luận rằng mọi thao tác ghi trong mọi cấu hình đều bị từ chối. Một câu lệnh JDBC trực tiếp, native query, explicit flush hoặc hành vi riêng của provider có thể có kết quả khác.

Nếu phương thức cần cập nhật, hãy khai báo giao dịch đọc/ghi:

~~~java
@Transactional
public void renameBook(Long id, String newTitle) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.setTitle(newTitle);
}
~~~

## 6. Giao dịch lồng nhau và propagation

Thuộc tính của giao dịch đang hoạt động có ảnh hưởng đến các phương thức tham gia vào giao dịch đó.

Với propagation mặc định là `REQUIRED`, nếu một phương thức được gọi khi đã có giao dịch, phương thức đó thường tham gia giao dịch hiện tại. Ví dụ, một service ngoài mở giao dịch read-only rồi gọi service cập nhật có `@Transactional` mặc định. Giao dịch bên trong thường tham gia giao dịch read-only đang tồn tại; annotation ở phương thức bên trong không tự biến giao dịch hiện tại thành giao dịch đọc/ghi.

~~~java
@Service
public class ReportService {
    private final BookService bookService;

    public ReportService(BookService bookService) {
        this.bookService = bookService;
    }

    @Transactional(readOnly = true)
    public void buildReportAndUpdateBook(Long id) {
        // Gọi phương thức cập nhật với propagation mặc định REQUIRED.
        // Phương thức bên trong có thể tham gia giao dịch read-only này.
        bookService.renameBook(id, "Tên mới");
    }
}
~~~

Ví dụ trên thể hiện một thiết kế cần tránh: một luồng được khai báo chỉ đọc lại gọi nghiệp vụ ghi. Hãy tách luồng đọc và ghi hoặc đặt ranh giới giao dịch phù hợp ở service điều phối.

Theo mặc định, Spring thường không kiểm tra nghiêm ngặt mọi khác biệt về read-only khi một phương thức tham gia giao dịch có sẵn. Có thể bật `validateExistingTransaction` trên transaction manager để phát hiện một số trường hợp cấu hình giao dịch tham gia không tương thích; cách bật phụ thuộc loại transaction manager.

Propagation `REQUIRES_NEW` có thể tạo một giao dịch độc lập thay vì tham gia giao dịch hiện tại. Chỉ dùng khi nghiệp vụ thật sự cần ranh giới commit/rollback riêng. Không nên dùng nó như cách chữa tùy tiện cho việc đặt sai `readOnly`, vì nó làm thay đổi ngữ nghĩa giao dịch và cách sử dụng tài nguyên kết nối.

### Lưu ý về proxy của Spring

Trong chế độ proxy mặc định, Spring áp dụng `@Transactional` khi lời gọi đi qua proxy. Một phương thức trong cùng object gọi trực tiếp phương thức khác bằng `this.someMethod()` thường không đi qua proxy, nên annotation trên phương thức được gọi có thể không được áp dụng như mong đợi.

Hãy đặt ranh giới giao dịch ở phương thức được gọi qua Spring bean, hoặc tổ chức service sao cho lời gọi đi qua proxy. Khi kiểm tra lỗi giao dịch, cần xem cả đường đi của lời gọi chứ không chỉ nhìn annotation trên mã nguồn.

## 7. Lỗi thường gặp

- **Coi read-only là cơ chế phân quyền.** Annotation không thay thế quyền `SELECT`/`INSERT`/`UPDATE`/`DELETE` của tài khoản cơ sở dữ liệu.
- **Đánh dấu cả service là read-only dù có phương thức ghi.** Nếu dùng annotation ở cấp class, cần khai báo lại chế độ đọc/ghi cho phương thức cập nhật và bảo đảm lời gọi thực sự đi qua proxy.
- **Cho rằng annotation bên trong luôn ghi đè giao dịch bên ngoài.** Với `REQUIRED`, phương thức bên trong thường tham gia giao dịch đã tồn tại.
- **Cho rằng mọi JPA provider hoạt động như Hibernate.** Flush mode và tối ưu dirty checking là chi tiết phụ thuộc provider và cấu hình.
- **Dựa vào việc không thấy dữ liệu được cập nhật trong một lần chạy để kết luận đã được bảo vệ.** Có thể thay đổi chưa flush, bị rollback hoặc bị ảnh hưởng bởi cấu hình khác. Muốn bảo vệ dữ liệu, hãy kiểm tra quyền và hành vi ở cơ sở dữ liệu.
- **Đặt transaction ở repository rời rạc mà bỏ qua nghiệp vụ.** Khi nhiều thao tác repository cần cùng một ranh giới nhất quán, service thường là nơi thích hợp hơn để quản lý transaction.

## 8. Cách kiểm chứng trong dự án

Khi áp dụng read-only transaction, hãy kiểm tra trên đúng cấu hình đang chạy:

1. Xác định transaction manager thực tế mà ứng dụng sử dụng, chẳng hạn `JpaTransactionManager` hoặc `DataSourceTransactionManager`.
2. Xác định JPA provider và phiên bản của nó. Với Hibernate, kiểm tra flush mode và hành vi dirty checking trong giao dịch read-only theo đúng phiên bản đang dùng.
3. Bật log SQL và log giao dịch trong môi trường kiểm thử để quan sát thời điểm câu lệnh được phát ra. Log giúp hiểu hành vi, nhưng không tự chứng minh rằng cơ sở dữ liệu đã chặn mọi câu lệnh ghi.
4. Viết integration test dùng đúng hệ quản trị cơ sở dữ liệu của ứng dụng nếu cần xác minh hành vi khi ghi trong giao dịch read-only.
5. Nếu yêu cầu là cấm ghi thật sự, kiểm tra bằng tài khoản chỉ có quyền đọc hoặc cấu hình read-only ở cấp cơ sở dữ liệu. Kiểm thử phải xác nhận câu lệnh ghi bị từ chối bởi chính cơ chế bảo vệ đó.

Không nên chỉ kiểm thử bằng mock repository để kết luận về flush, dirty checking hoặc quyền ghi. Những hành vi này phụ thuộc transaction manager, JPA provider, JDBC driver và cơ sở dữ liệu thật.

## 9. Quy tắc chọn chế độ giao dịch

- Dùng `@Transactional(readOnly = true)` cho service method chỉ truy vấn, tổng hợp hoặc chuyển dữ liệu đọc.
- Dùng `@Transactional` mặc định cho nghiệp vụ có thay đổi entity, gọi thao tác ghi hoặc cần cả đọc và ghi trong cùng một giao dịch.
- Đặt ranh giới giao dịch theo nghiệp vụ ở tầng service để các thao tác repository liên quan dùng chung một giao dịch.
- Dùng quyền cơ sở dữ liệu, tài khoản chỉ đọc hoặc cơ chế read-only ở tầng database khi cần bảo đảm không thể ghi.

Hãy xem `readOnly` là tín hiệu giúp Spring và JPA provider tối ưu giao dịch đọc. Việc bảo vệ dữ liệu vẫn phải được thiết kế và kiểm chứng ở đúng tầng có khả năng thực thi quyền truy cập.