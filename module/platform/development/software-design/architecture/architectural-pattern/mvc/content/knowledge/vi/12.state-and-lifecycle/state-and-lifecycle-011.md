# Dọn tài nguyên và kết thúc vòng đời thành phần

## 1. Vì sao MVC cần quản lý vòng đời?

Một ứng dụng Model–View–Controller không chỉ xử lý dữ liệu và tạo giao diện. Trong quá trình phục vụ request, ứng dụng còn mở kết nối, đọc tệp, tạo luồng xử lý nền, giữ trạng thái phiên và sử dụng các client gọi dịch vụ bên ngoài. Những đối tượng này có thời điểm bắt đầu, phạm vi sử dụng và thời điểm phải giải phóng.

Nếu tài nguyên không được đóng đúng lúc, ứng dụng có thể cạn connection pool, giữ file handle, tiếp tục chạy thread sau khi request đã kết thúc hoặc giữ dữ liệu người dùng lâu hơn cần thiết. Nếu dọn quá sớm, một thành phần khác có thể đang dùng tài nguyên đó và request sẽ thất bại.

Vì vậy, cần phân biệt ba câu hỏi:

- **Thành phần sống bao lâu?** Ví dụ Controller thường tồn tại cùng ApplicationContext, còn request chỉ tồn tại trong một lần xử lý.
- **Ai sở hữu tài nguyên?** Thành phần tạo hoặc nhận quyền sở hữu tài nguyên phải xác định ai chịu trách nhiệm đóng nó.
- **Khi nào phải dọn?** Có thể là cuối một thao tác, cuối request, khi session kết thúc hoặc khi ứng dụng shutdown.

Quản lý vòng đời đúng giúp MVC giữ ranh giới trách nhiệm rõ ràng, sử dụng tài nguyên có giới hạn an toàn và kết thúc ứng dụng có trật tự.

## 2. Phân biệt vòng đời request, session, bean và tài nguyên

Trong ứng dụng Spring MVC, các đối tượng có phạm vi sống khác nhau:

| Phạm vi | Vòng đời điển hình | Ví dụ |
|---|---|---|
| Request | Từ khi server tiếp nhận request đến khi xử lý request kết thúc | `HttpServletRequest`, request attributes, request-scoped bean |
| Session | Tồn tại qua nhiều request của một phiên đến khi bị invalidate hoặc timeout | Giỏ hàng, wizard state, session-scoped bean |
| ApplicationContext / singleton bean | Từ lúc Spring tạo bean đến khi context đóng | Controller, Service, Repository, client dùng chung |
| Prototype bean | Mỗi lần container cấp một instance mới; container không tự quản lý đầy đủ bước hủy sau khi bàn giao | Đối tượng tác vụ ngắn hạn được tạo theo yêu cầu |
| Tài nguyên cục bộ | Trong phạm vi thao tác đã mở tài nguyên | `InputStream`, `ResultSet`, file handle |

Một Controller Spring thường là singleton. Nhiều request có thể đồng thời đi qua cùng một instance Controller. Do đó, không nên lưu dữ liệu riêng của request vào field mutable của Controller.

Request-scoped bean phù hợp với dữ liệu gắn với request hiện tại. Session-scoped bean phù hợp với trạng thái có chủ đích kéo dài qua nhiều request. Singleton bean phù hợp với dịch vụ dùng chung và thường phải an toàn luồng.

Điều quan trọng là **vòng đời của bean không tự động giống vòng đời của mọi tài nguyên mà bean sử dụng**. Một singleton Service có thể mở một `InputStream` trong một phương thức; stream đó phải được đóng ngay khi thao tác kết thúc, không đợi đến khi ứng dụng shutdown.

## 3. Ai chịu trách nhiệm đóng tài nguyên?

Nguyên tắc cơ bản là quản lý theo quyền sở hữu (ownership): thành phần nào tạo hoặc nhận quyền sở hữu tài nguyên thì phải bảo đảm tài nguyên được giải phóng đúng một lần, kể cả khi có exception.

| Tài nguyên | Nơi thường quản lý | Thời điểm giải phóng |
|---|---|---|
| Stream đọc/ghi file | Phương thức thực hiện thao tác | Ngay khi đọc/ghi xong hoặc khi lỗi |
| JDBC `Connection`, `Statement`, `ResultSet` tự mở | Phương thức hoặc framework truy cập dữ liệu | Cuối thao tác; framework có thể quản lý trong transaction |
| Transaction | Transaction manager / ranh giới use case | Commit hoặc rollback khi use case kết thúc |
| HTTP client dùng chung | Bean sở hữu client trong ApplicationContext | Khi context đóng |
| Executor hoặc scheduler | Thành phần quản lý tác vụ nền | Khi ứng dụng shutdown hoặc thành phần dừng |
| Request-scoped resource | Thành phần request-scoped sở hữu resource | Khi request kết thúc, hoặc sớm hơn nếu thao tác đã hoàn tất |
| Session state | Thành phần quản lý session | Khi hoàn tất, hủy hoặc hết hạn phiên |

Không đóng một dependency chỉ vì đã sử dụng nó. Ví dụ, Service nhận `DataSource`, `EntityManager` hoặc HTTP client qua constructor thường không sở hữu chúng. Nếu Service tự đóng dependency dùng chung, request khác có thể bị ảnh hưởng. Hãy đóng tài nguyên do phương thức tự mở; để container hoặc thành phần sở hữu quản lý dependency được chia sẻ.

## 4. Tài nguyên ngắn hạn: dùng try-with-resources

Với tài nguyên Java triển khai `AutoCloseable`, ưu tiên `try-with-resources`. Java sẽ gọi `close()` khi rời khỏi khối, kể cả khi thân khối phát sinh exception.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public byte[] readPreview(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
~~~

Phương thức này đóng stream ngay sau khi đọc xong. Không cần lưu stream vào field của Controller hoặc chờ callback hủy bean.

Với JDBC thuần, có thể đóng connection và các đối tượng phụ thuộc bằng cùng cơ chế:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT title FROM books WHERE id = ?")) {
    statement.setObject(1, bookId);
    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            return result.getString("title");
        }
    }
}
~~~

Ví dụ giả định các kiểu JDBC và `dataSource` đã được khai báo. Khi dùng Spring `JdbcTemplate` hoặc repository JPA, hãy để framework quản lý connection và transaction theo cơ chế của nó; không tự lấy rồi đóng connection đang được transaction manager quản lý.

### Vì sao không nên tự đóng bằng finally thủ công?

Có thể viết `try/finally`, nhưng phải xử lý trường hợp mở tài nguyên thất bại, nhiều tài nguyên lồng nhau và exception trong lúc đóng. `try-with-resources` làm rõ ownership và xử lý exception đóng tài nguyên nhất quán hơn.

Nếu phải quản lý tài nguyên không triển khai `AutoCloseable`, hãy đặt thao tác giải phóng trong `finally` và bảo đảm nhánh lỗi không bỏ qua bước dọn.

## 5. Transaction và tài nguyên persistence

Trong MVC web, Controller thường gọi Service để thực hiện use case. Transaction nên nằm ở ranh giới nghiệp vụ phù hợp, thường là phương thức Service, để nhiều thao tác đọc/ghi có thể được commit hoặc rollback cùng nhau.

~~~java
@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void renameBook(BookId id, String newTitle) {
        Book book = books.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
        book.rename(newTitle);
        books.save(book);
    }
}
~~~

Với cấu hình Spring phù hợp, transaction manager mở hoặc tham gia transaction trước khi thực thi phương thức và commit/rollback khi phương thức kết thúc. Repository/JPA provider quản lý persistence context và các tài nguyên liên quan theo transaction.

Không giữ transaction mở trong lúc người dùng đọc biểu mẫu hoặc chờ xác nhận. Một HTTP request có thể kéo dài do mạng hoặc thao tác người dùng; transaction dài sẽ giữ connection và lock, làm giảm khả năng phục vụ các request khác.

Đối với dữ liệu nhiều bước, mỗi lần lưu một bước nên là một transaction ngắn. Không mở một transaction ở bước đầu rồi cố giữ qua nhiều request.

## 6. Kết thúc vòng đời singleton bean trong Spring

Spring quản lý vòng đời của singleton bean trong ApplicationContext. Khi context đóng bình thường, Spring có thể gọi các callback hủy đã đăng ký để bean giải phóng tài nguyên mà nó sở hữu.

Các cơ chế thường gặp:

- `@PreDestroy`: đánh dấu phương thức cần gọi khi bean bị hủy.
- `DisposableBean.destroy()`: callback theo interface của Spring.
- `@Bean(destroyMethod = "...")`: chỉ định phương thức hủy trên bean được tạo từ cấu hình Java.
- `AutoCloseable.close()` hoặc phương thức `close`/`shutdown` được Spring nhận diện theo quy ước destroy method.

Ưu tiên callback chuẩn như `@PreDestroy` hoặc khai báo destroy method khi cần giải phóng tài nguyên. Không cần tự gọi các callback này trong mỗi request.

### Ví dụ dùng @PreDestroy

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

@Component
public class ReportWorker {
    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    public void stop() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

`ReportWorker` sở hữu executor do chính nó tạo, vì vậy nó chịu trách nhiệm dừng executor khi bean bị hủy. `shutdown()` ngừng nhận task mới và cho task đã nhận cơ hội hoàn tất; sau thời gian chờ, `shutdownNow()` yêu cầu các task đang chạy dừng. Việc ngắt thread chỉ là yêu cầu; mỗi task cần phản hồi interruption đúng cách.

`@PreDestroy` không phải nơi phù hợp để thực hiện một quy trình nghiệp vụ dài hoặc cần bảo đảm giao dịch. Callback nên hoàn tất nhanh, có giới hạn thời gian và giải phóng tài nguyên thuộc sở hữu của bean.

### Khai báo bean có destroy method

Nếu một thư viện cung cấp client triển khai `AutoCloseable`, có thể để Spring quản lý việc đóng:

~~~java
@Configuration
public class PartnerClientConfiguration {
    @Bean(destroyMethod = "close")
    public PartnerApiClient partnerApiClient(PartnerSettings settings) {
        return PartnerApiClient.connect(settings);
    }
}
~~~

Ví dụ giả định `PartnerApiClient` có phương thức `close()` và `PartnerSettings` là bean cấu hình. Client được chia sẻ cho các thành phần khác; các thành phần sử dụng không tự đóng nó. Spring gọi destroy method khi ApplicationContext đóng.

Không đăng ký nhiều callback khác nhau cùng đóng một tài nguyên nếu chúng có thể chạy lặp hoặc cạnh tranh. Xác định một chủ sở hữu và một đường giải phóng rõ ràng.

## 7. Request scope và cleanup cuối request

Request-scoped bean có vòng đời gắn với một HTTP request. Spring có thể gọi destruction callback đã đăng ký khi request scope kết thúc. Cách này hữu ích với đối tượng chỉ có ý nghĩa trong request, nhưng không nên dùng request scope để giữ mọi loại tài nguyên một cách tùy tiện.

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestAuditContext {
    private String correlationId;

    public void setCorrelationId(String value) {
        this.correlationId = value;
    }

    public String getCorrelationId() {
        return correlationId;
    }

    @PreDestroy
    public void cleanup() {
        // Giải phóng dữ liệu hoặc resource chỉ thuộc request này.
    }
}
~~~

Ví dụ minh họa callback vòng đời; nếu đối tượng chỉ chứa vài giá trị Java thuần thì thường không cần phương thức cleanup. Không giữ `HttpServletRequest`, stream hoặc dữ liệu request trong singleton sau khi request kết thúc.

Với tài nguyên cần đóng ngay sau một thao tác, vẫn nên dùng `try-with-resources` tại nơi mở tài nguyên. Dựa vào callback cuối request có thể khiến tài nguyên bị giữ lâu hơn cần thiết.

### Filter và interceptor

Servlet Filter có thể bao quanh xử lý request để đặt và dọn context xuyên suốt chuỗi filter/servlet. Mẫu thường dùng là thiết lập trước `chain.doFilter(...)` và dọn trong `finally` để bước dọn vẫn chạy khi handler phát sinh lỗi.

Interceptor của Spring MVC cung cấp `afterCompletion` cho phần dọn sau khi handler hoàn tất xử lý đồng bộ. Với request xử lý bất đồng bộ, vòng đời có thêm callback và dispatch tiếp theo; không nên giả định `afterCompletion` của lần dispatch ban đầu là thời điểm cuối cùng của toàn bộ công việc async.

Nếu dùng `ThreadLocal` cho correlation ID hoặc context tạm, luôn gọi `remove()` trong `finally` trên đúng thread đã đặt giá trị. Thread pool tái sử dụng thread; không dọn có thể làm request sau nhìn thấy dữ liệu của request trước.

## 8. Session scope và dữ liệu phiên

Session-scoped bean sống qua nhiều request trong cùng session. Spring có thể gọi destruction callback khi session bị invalidate hoặc hết hạn, tùy môi trường và session implementation.

Session scope phù hợp với trạng thái ngắn hạn như tiến trình wizard hoặc lựa chọn của người dùng. Không nên giữ connection, file stream, transaction hoặc executor trong session-scoped bean. Những tài nguyên này có vòng đời và chi phí khác với phiên người dùng.

Khi người dùng hoàn tất wizard, hãy xóa trạng thái wizard theo cơ chế của ứng dụng ngay lúc đó thay vì chờ session timeout. Session timeout là cơ chế dự phòng cho phiên bị bỏ dở, không phải cách duy nhất để dọn trạng thái đã hoàn tất.

Với ứng dụng dùng session phân tán hoặc lưu ở hệ thống ngoài, thời điểm và khả năng chạy destruction callback có thể phụ thuộc nhà cung cấp. Không đặt một bảo đảm nghiệp vụ quan trọng duy nhất vào callback hủy session; hãy thực hiện cập nhật nghiệp vụ tường minh và dùng job dọn dữ liệu hết hạn khi cần.

## 9. Prototype bean và trách nhiệm hủy

Với scope `prototype`, Spring tạo một instance mới mỗi lần bean được yêu cầu nhưng không quản lý đầy đủ bước hủy sau khi bàn giao instance cho caller. Nếu prototype sở hữu tài nguyên, caller phải có trách nhiệm giải phóng.

~~~java
try (ExportSession export = exportSessionProvider.create()) {
    export.write(reportData);
}
~~~

Đoạn ví dụ giả định `ExportSession` triển khai `AutoCloseable` và provider tạo instance mới. Caller đóng session xuất dữ liệu khi hoàn tất.

Nếu cần callback hủy phức tạp của Spring cho prototype, có thể dùng `AutowireCapableBeanFactory.destroyBean(instance)` tại nơi sở hữu instance, nhưng phải thiết kế rõ ai gọi và gọi đúng một lần. Trong nhiều trường hợp, một factory trả về đối tượng `AutoCloseable` với ownership tường minh sẽ dễ hiểu hơn.

Không chọn prototype chỉ vì muốn một đối tượng mới cho mỗi request. Request scope và factory method có thể phù hợp hơn tùy mục đích.

## 10. Tác vụ bất đồng bộ và vòng đời ứng dụng

Ứng dụng web có thể gửi email, tạo báo cáo hoặc xử lý ảnh ở background executor. Khi request kết thúc, task có thể vẫn đang chạy. Vì vậy, vòng đời task không đồng nghĩa với vòng đời request.

Không truyền trực tiếp `HttpServletRequest`, request-scoped bean hoặc stream đã đóng vào tác vụ chạy nền. Hãy trích xuất dữ liệu bất biến cần thiết, chuyển thành command/job riêng và để task tự sở hữu tài nguyên mà nó mở.

Ví dụ, task tạo báo cáo có thể nhận `ReportId` và truy vấn dữ liệu cần thiết khi chạy. Nếu task cần ghi file, nó mở và đóng stream bên trong task bằng `try-with-resources`.

Khi ứng dụng shutdown, cần ngừng nhận task mới, cho task đang chạy một khoảng thời gian hoàn tất và sau đó yêu cầu dừng những task còn lại. Spring hỗ trợ quản lý lifecycle cho các thành phần triển khai `Lifecycle` hoặc `SmartLifecycle`; `SmartLifecycle` còn cho phép điều phối thứ tự start/stop qua phase và callback dừng.

Đối với tác vụ quan trọng không được mất khi process dừng, không chỉ dựa vào executor trong bộ nhớ. Hãy lưu công việc vào hàng đợi hoặc bảng outbox bền vững, có retry và cơ chế idempotency. Shutdown hook chỉ hỗ trợ dừng có trật tự; nó không thay thế lưu trữ bền vững.

## 11. Dọn tài nguyên khi request lỗi hoặc bị hủy

Request có thể kết thúc theo nhiều cách: thành công, validation thất bại, exception, client ngắt kết nối hoặc timeout. Cleanup phải được đặt ở ranh giới bảo đảm chạy cho những đường kết thúc mà ứng dụng kiểm soát.

- Tài nguyên cục bộ: dùng `try-with-resources` để đóng khi ra khỏi scope.
- Transaction: để transaction manager commit/rollback theo kết quả phương thức.
- Context tạm theo thread: dọn trong `finally`.
- Tài nguyên request-scoped: dùng destruction callback khi phù hợp, đồng thời đóng tài nguyên sớm ngay khi thao tác kết thúc.
- Task nền: dùng `try/finally` hoặc `try-with-resources` bên trong task và xử lý cancellation/interruption.

Client có thể ngắt kết nối sau khi server đã bắt đầu xử lý. Không phải lúc nào server cũng có thể hủy tức thì công việc nền hoặc rollback một thao tác đã commit. Với thao tác có tác động nghiệp vụ, cần thiết kế idempotency, timeout và ranh giới transaction phù hợp thay vì giả định đóng kết nối đồng nghĩa mọi công việc bị hủy.

## 12. Cleanup phải an toàn và có thể lặp

Phương thức cleanup nên có một số đặc tính:

**Idempotent:** gọi lặp không làm hỏng trạng thái. Nếu tài nguyên đã đóng, lần dọn tiếp theo nên được xử lý an toàn.

**Có giới hạn thời gian:** không để shutdown bị treo vô hạn vì chờ một kết nối hoặc task không phản hồi.

**Không che lỗi chính:** nếu thao tác chính đã thất bại, exception trong lúc cleanup không nên làm mất nguyên nhân ban đầu. `try-with-resources` xử lý exception đóng như suppressed exception; khi cleanup thủ công, cần giữ lại và ghi nhận lỗi phù hợp.

**Có thể quan sát:** log sự kiện đóng tài nguyên hoặc task không dừng đúng hạn bằng ID tương quan, nhưng không ghi token, nội dung nhạy cảm hay toàn bộ dữ liệu request.

**Không thay thế nghiệp vụ:** xóa file tạm là cleanup kỹ thuật; hủy đơn hàng hoặc thu hồi quyền là thao tác nghiệp vụ cần use case và transaction riêng.

## 13. Kiểm thử vòng đời và cleanup

Kiểm thử cần xác minh cả đường thành công lẫn đường lỗi:

| Tình huống | Điều cần xác minh |
|---|---|
| Đọc file thành công | Stream được đóng sau khi đọc |
| Đọc file phát sinh exception | Stream vẫn được đóng |
| Transaction thành công | Commit xảy ra tại ranh giới dự kiến |
| Nghiệp vụ phát sinh exception | Transaction rollback theo cấu hình |
| ApplicationContext đóng | Singleton bean nhận callback hủy và đóng resource sở hữu |
| Executor shutdown | Không nhận task mới và dừng theo timeout đã đặt |
| Request kết thúc | Request context được giải phóng; ThreadLocal được remove |
| Session bị invalidate/timeout | Session state được dọn theo chính sách |
| Prototype resource kết thúc | Caller đóng instance đã nhận |
| Task nền bị interrupt | Task phản hồi interruption và vẫn chạy cleanup |

Unit test có thể dùng fake resource ghi nhận `close()` được gọi. Spring context test có thể khởi tạo và đóng `ApplicationContext` để xác minh callback. Integration test phù hợp để kiểm tra transaction, request/session scope và hành vi shutdown trong môi trường gần thực tế.

Không nên chỉ kiểm tra phương thức cleanup được gọi; cần kiểm tra tài nguyên thực sự ở trạng thái đóng hoặc task không còn chạy. Với callback phụ thuộc container, test phải đóng context tường minh để kích hoạt lifecycle.

## 14. Những sai lầm thường gặp

- **Đóng dependency dùng chung trong Controller hoặc Service:** có thể làm hỏng request khác đang sử dụng bean đó.
- **Giữ stream hoặc connection trong field singleton:** tài nguyên tồn tại lâu, dễ rò rỉ và không an toàn khi nhiều request đồng thời.
- **Dựa vào `@PreDestroy` để đóng mọi tài nguyên:** tài nguyên ngắn hạn cần được đóng ngay tại nơi mở.
- **Cho rằng prototype tự được Spring hủy:** caller chịu trách nhiệm sau khi nhận instance prototype.
- **Giữ transaction qua nhiều request hoặc màn hình:** làm giữ connection và lock quá lâu.
- **Dùng session để giữ resource:** session timeout không phải cơ chế quản lý stream, connection hoặc thread.
- **Không dọn ThreadLocal:** thread pool có thể tái sử dụng dữ liệu context của request trước.
- **Không xử lý async khi shutdown:** task nền có thể bị mất hoặc tiếp tục giữ tài nguyên sau khi ứng dụng dừng.
- **Dùng cleanup để thực hiện nghiệp vụ quan trọng:** callback shutdown hoặc session destruction không bảo đảm chạy trong mọi tình huống process dừng đột ngột.
- **Không kiểm thử đường exception:** tài nguyên chỉ được đóng ở nhánh thành công sẽ rò rỉ khi thao tác thất bại.

## 15. Kết luận

Quản lý vòng đời trong MVC đòi hỏi phân biệt thời gian sống của request, session, bean và từng tài nguyên cụ thể. Dùng `try-with-resources` cho tài nguyên ngắn hạn; dùng transaction manager cho transaction; dùng callback hủy như `@PreDestroy` hoặc destroy method cho tài nguyên thuộc singleton bean; dùng request/session scope đúng mục đích; và quản lý tác vụ nền với quy trình shutdown rõ ràng.

Khi thiết kế một thành phần, hãy xác định ai tạo và sở hữu từng tài nguyên, nó cần sống đến thời điểm nào, đường kết thúc nào có thể xảy ra và cơ chế nào bảo đảm cleanup chạy ngay cả khi có lỗi. Ownership rõ ràng và cleanup có giới hạn giúp ứng dụng ổn định trong lúc phục vụ request lẫn khi kết thúc hoạt động.
