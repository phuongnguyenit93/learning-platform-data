# Model chủ động (active model) và Model thụ động (passive model)

## 1. Vì sao có hai cách tổ chức Model trong MVC tương tác?

Trong MVC tương tác, Model giữ trạng thái và quy tắc của miền bài toán, View trình bày trạng thái đó, còn Controller tiếp nhận thao tác và điều phối hành động. Khi Model thay đổi, View cần biết lúc nào phải cập nhật để không hiển thị dữ liệu cũ. Có hai cách tổ chức luồng cập nhật thường gặp:

- **Model chủ động (active model):** Model phát thông báo khi trạng thái thay đổi. View hoặc thành phần quan tâm đăng ký lắng nghe và tự cập nhật khi nhận thông báo.
- **Model thụ động (passive model):** Model thay đổi trạng thái nhưng không tự phát thông báo cho View. Controller hoặc thành phần điều phối chủ động yêu cầu dữ liệu mới và gọi View cập nhật.

Trong bài này, active/passive mô tả **cơ chế thông báo và điều phối cập nhật giao diện** trong MVC tương tác. Nó không có nghĩa Model chủ động chạy nền, tự lưu dữ liệu hay tự gửi request. Nó cũng không đồng nghĩa với tên thư viện `Active Model`, `Active Record` hoặc khái niệm “anemic domain model” trong các hệ sinh thái khác.

## 2. Vị trí của Model trong luồng MVC

Model không cần biết View được dựng bằng cửa sổ desktop, HTML hay component phía trình duyệt. Model chịu trách nhiệm giữ trạng thái hợp lệ và cung cấp những hành vi miền có ý nghĩa. Controller nhận thao tác từ người dùng rồi gọi các hành vi đó. View hiển thị một ảnh chụp trạng thái (state snapshot) hoặc phản ứng với thông báo thay đổi.

Điểm khác nhau giữa active và passive nằm ở câu hỏi: **ai khởi động việc cập nhật View sau khi Model đổi?**

~~~mermaid
flowchart LR
    U[Người dùng] --> C[Controller]
    C -->|Lệnh nghiệp vụ| M[Model]
    M -->|Active: thông báo thay đổi| V[View]
    C -->|Passive: yêu cầu dữ liệu và refresh| V
    V --> U
~~~

Sơ đồ khái quát hai lựa chọn. Một hệ thống có thể kết hợp cả hai: Controller điều phối lệnh, Model phát thông báo thay đổi cho nhiều View, còn một số View khác chỉ được render khi Controller trả response.

## 3. Model chủ động (Active Model)

### 3.1. Cách hoạt động

Active Model thường đóng vai trò **Subject/Observable** trong mẫu Observer. View hoặc thành phần trình bày đăng ký làm **Observer/Listener**. Khi một hành động hợp lệ làm thay đổi trạng thái, Model phát thông báo; các observer nhận thông tin và cập nhật phần hiển thị liên quan.

Luồng điển hình:

1. View đăng ký lắng nghe thay đổi của Model.
2. Người dùng thao tác; Controller nhận sự kiện và gọi hành vi của Model.
3. Model kiểm tra quy tắc nghiệp vụ và thay đổi trạng thái nếu hợp lệ.
4. Sau khi trạng thái đã được cập nhật, Model phát thông báo mô tả phần thay đổi.
5. Các View đang lắng nghe đọc dữ liệu mới hoặc dùng payload bất biến của sự kiện để render lại.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Controller
    participant M as Active Model
    participant V1 as View danh sách
    participant V2 as View bộ đếm
    V1->>M: Đăng ký listener
    V2->>M: Đăng ký listener
    U->>C: Thêm một cuốn sách
    C->>M: addBook(book)
    M->>M: Kiểm tra và cập nhật trạng thái
    M-->>V1: booksChanged(snapshot)
    M-->>V2: booksChanged(count)
    V1->>M: Đọc danh sách mới (nếu cần)
    V2->>M: Đọc số lượng mới (nếu cần)
~~~

Trong mô hình này, Controller không cần biết có bao nhiêu View đang quan sát Model. Một thay đổi có thể cập nhật bảng danh sách, bộ đếm tổng số sách và biểu đồ thống kê cùng lúc.

### 3.2. Ví dụ Java với PropertyChangeSupport

Java cung cấp `PropertyChangeSupport` để triển khai cơ chế thông báo thay đổi thuộc tính. Ví dụ dưới đây dùng một danh mục sách nhỏ:

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class BookCatalogModel {
    private final List<Book> books = new ArrayList<>();
    private final PropertyChangeSupport changes =
            new PropertyChangeSupport(this);

    public void addBook(Book book) {
        Objects.requireNonNull(book, "book is required");

        List<Book> oldSnapshot = List.copyOf(books);
        books.add(book);
        List<Book> newSnapshot = List.copyOf(books);

        changes.firePropertyChange(
                "books", oldSnapshot, newSnapshot);
    }

    public List<Book> books() {
        return List.copyOf(books);
    }

    public void addPropertyChangeListener(
            PropertyChangeListener listener) {
        changes.addPropertyChangeListener(listener);
    }

    public void removePropertyChangeListener(
            PropertyChangeListener listener) {
        changes.removePropertyChangeListener(listener);
    }

    public record Book(String id, String title) {}
}
~~~

`addBook` kiểm tra đầu vào, cập nhật danh sách rồi phát sự kiện có tên `books`. Hai snapshot được tạo bằng `List.copyOf` để observer không nhận tham chiếu đến collection nội bộ có thể bị sửa tùy ý. Phương thức `books()` cũng trả về bản sao không thể sửa. Ví dụ giả định `Book` là immutable record.

View có thể đăng ký nhận sự kiện như sau:

~~~java
import java.beans.PropertyChangeEvent;
import java.beans.PropertyChangeListener;
import java.util.List;

public final class BookListView implements PropertyChangeListener {
    @Override
    public void propertyChange(PropertyChangeEvent event) {
        if ("books".equals(event.getPropertyName())) {
            @SuppressWarnings("unchecked")
            List<BookCatalogModel.Book> books =
                    (List<BookCatalogModel.Book>) event.getNewValue();
            render(books);
        }
    }

    private void render(List<BookCatalogModel.Book> books) {
        // Cập nhật bảng hoặc danh sách trên giao diện.
    }
}
~~~

Khi khởi tạo giao diện, thành phần lắp ráp ứng dụng đăng ký listener:

~~~java
BookCatalogModel model = new BookCatalogModel();
BookListView listView = new BookListView();
model.addPropertyChangeListener(listView);
~~~

Trong ứng dụng thật, View cần được nạp trạng thái ban đầu bằng `model.books()` khi khởi tạo; listener chỉ nhận những thay đổi phát sinh sau khi đăng ký. Khi View bị đóng hoặc không còn sử dụng, cần gọi `removePropertyChangeListener` để tránh giữ tham chiếu đến View đã hết vòng đời.

### 3.3. Ưu điểm và chi phí

Active Model hữu ích khi một thay đổi cần cập nhật nhiều phần giao diện hoặc nhiều thành phần phụ thuộc. View không phải liên tục hỏi Model xem dữ liệu có đổi hay chưa; Model thông báo khi có thay đổi.

Cách này cũng tạo ra chi phí thiết kế:

- Luồng cập nhật có thể khó lần theo vì một lệnh gọi Model kích hoạt nhiều listener gián tiếp.
- Listener có thể bị đăng ký trùng hoặc không được gỡ bỏ, gây cập nhật lặp và rò rỉ bộ nhớ.
- Một listener chậm hoặc phát sinh exception có thể ảnh hưởng đến quá trình phát thông báo nếu không có chính sách xử lý phù hợp.
- Nếu thông báo được phát trên thread không phù hợp, View có thể bị cập nhật sai luồng UI.
- Một thay đổi lớn có thể tạo quá nhiều thông báo nhỏ, làm giao diện render liên tục.

Active Model vì thế cần quy ước rõ về thời điểm phát sự kiện, payload, thứ tự xử lý, lỗi listener và vòng đời đăng ký.

## 4. Model thụ động (Passive Model)

### 4.1. Cách hoạt động

Passive Model không tự thông báo cho View khi trạng thái thay đổi. Nó cung cấp các hành vi để thay đổi dữ liệu và các phương thức đọc trạng thái. Sau khi gọi Model hoặc Service, Controller chủ động lấy dữ liệu mới rồi yêu cầu View render.

Luồng điển hình:

1. Người dùng thao tác và Controller nhận sự kiện.
2. Controller gọi hành vi của Model hoặc Service.
3. Model cập nhật trạng thái và trả kết quả.
4. Controller lấy snapshot mới hoặc dùng kết quả trả về.
5. Controller gọi phương thức cập nhật của View.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Controller
    participant M as Passive Model
    participant V as View
    U->>C: Thêm một cuốn sách
    C->>M: addBook(book)
    M->>M: Kiểm tra và cập nhật trạng thái
    M-->>C: Kết quả thao tác
    C->>M: books()
    M-->>C: Snapshot danh sách
    C->>V: render(snapshot)
    V-->>U: Danh sách mới
~~~

Ở đây, Controller biết rõ thời điểm cần refresh View. Model không cần giữ danh sách observer hoặc phụ thuộc vào cơ chế sự kiện.

### 4.2. Ví dụ Java

Model thụ động chỉ cung cấp hành vi và dữ liệu đọc:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class PassiveBookCatalogModel {
    private final List<Book> books = new ArrayList<>();

    public void addBook(Book book) {
        books.add(Objects.requireNonNull(book));
    }

    public List<Book> books() {
        return List.copyOf(books);
    }

    public record Book(String id, String title) {}
}
~~~

Controller điều phối cập nhật:

~~~java
import java.util.List;

// Interface của View dùng trong ví dụ Passive Model.
public interface PassiveBookListView {
    void render(List<PassiveBookCatalogModel.Book> books);
}

public final class BookController {
    private final PassiveBookCatalogModel model;
    private final PassiveBookListView view;

    public BookController(
            PassiveBookCatalogModel model,
            PassiveBookListView view) {
        this.model = model;
        this.view = view;
    }

    public void addBook(PassiveBookCatalogModel.Book book) {
        model.addBook(book);
        view.render(model.books());
    }
}
~~~

Ví dụ lược bỏ phần kiểm tra nghiệp vụ để tập trung vào cơ chế cập nhật View. Trong ứng dụng thực tế, Controller thường gọi Service để thực hiện use case; Service/Model kiểm tra invariant và trả kết quả, sau đó Controller chọn View hoặc response phù hợp.

### 4.3. Ưu điểm và giới hạn

Passive Model có luồng điều khiển tường minh: đọc action của Controller sẽ thấy khi nào dữ liệu thay đổi và khi nào View được render. Nó dễ kiểm thử, ít phụ thuộc vào listener và phù hợp với các request web độc lập.

Đổi lại, nếu nhiều View cần đồng bộ với cùng một Model, Controller có thể phải biết và cập nhật từng View. Nếu có thay đổi từ nguồn bên ngoài Controller hiện tại, View sẽ không tự biết cho đến khi một thành phần điều phối gọi refresh. Việc giữ nhiều bản trình bày nhất quán có thể trở nên khó khăn khi ứng dụng tương tác phức tạp.

## 5. So sánh Active Model và Passive Model

| Tiêu chí | Active Model | Passive Model |
|---|---|---|
| Thông báo thay đổi | Model phát sự kiện hoặc notification | Model không tự thông báo cho View |
| Ai khởi động refresh? | Model phát tín hiệu; observer cập nhật | Controller/coordinator gọi refresh |
| Quan hệ với View | View đăng ký lắng nghe hoặc nhận sự kiện | View được Controller gọi trực tiếp |
| Luồng điều khiển | Có phần gián tiếp qua listener | Tường minh trong Controller |
| Nhiều View cùng quan sát | Tự nhiên hơn vì nhiều observer có thể nhận một thay đổi | Controller phải điều phối các View liên quan |
| Vòng đời listener | Cần đăng ký và hủy đăng ký | Không cần listener của Model |
| Kiểm thử | Cần kiểm tra trạng thái và thông báo | Thường kiểm tra lệnh, kết quả và lần gọi render |
| Phù hợp | Giao diện tương tác dài hạn, nhiều vùng cần đồng bộ | Luồng đơn giản, request-response, ít View phụ thuộc |

Không có lựa chọn nào tốt hơn trong mọi trường hợp. Active Model giảm sự phụ thuộc trực tiếp giữa Controller và các View nhưng tăng tính gián tiếp. Passive Model làm luồng dễ đọc hơn nhưng Controller có thể trở thành nơi phải biết nhiều chi tiết trình bày.

## 6. Active Model có phải là Model chứa nghiệp vụ, còn Passive Model chỉ chứa dữ liệu?

Không nên đồng nhất hai cách phân loại này.

Trong bài này, **active/passive nói về việc Model có phát thông báo thay đổi hay không**. Còn câu hỏi Model có chứa hành vi nghiệp vụ hay chỉ chứa dữ liệu nói về cách tổ chức Domain Model.

Một Passive Model vẫn có thể có phương thức `borrowBook`, `returnBook`, `rename` và tự bảo vệ invariant. Nó chỉ không phát notification cho View. Ngược lại, một Active Model có thể thông báo khi một thuộc tính thay đổi nhưng không nên vì thế mà chứa logic trình bày hoặc phụ thuộc vào HTML.

Ví dụ:

- `Book.borrow()` kiểm tra sách có đang khả dụng hay không và thay đổi trạng thái. Đây là hành vi miền, không tự quyết định Model active hay passive.
- Sau khi `borrow()` thành công, Model phát `bookStatusChanged` để View cập nhật. Đây là cơ chế active.
- Nếu `borrow()` trả kết quả cho Controller và Controller gọi `view.render(...)`, đó là cơ chế passive.

## 7. Phân biệt notification, domain event và message

Trong thiết kế hệ thống, có một số loại thông báo dễ bị gọi chung là “event”, nhưng chúng có mục đích khác nhau:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Property-change notification | Báo một thuộc tính hoặc snapshot của Model đã đổi để giao diện đồng bộ | `booksChanged`, `selectedBookChanged` |
| Domain event | Ghi nhận một sự kiện có ý nghĩa nghiệp vụ đã xảy ra | `BookBorrowed`, `LoanOverdue` |
| Integration message | Thông điệp trao đổi với hệ thống hoặc tiến trình khác | Gửi sự kiện qua message broker |

View thường quan tâm đến notification đủ để render lại. Domain event diễn đạt điều đã xảy ra trong miền và có thể được dùng bởi nhiều chính sách nghiệp vụ. Integration message còn liên quan đến giao nhận, retry, idempotency và tính nhất quán giữa các hệ thống.

Không nên biến mọi lần đổi thuộc tính thành domain event. Ví dụ đổi trạng thái focus của một ô nhập liệu không phải sự kiện nghiệp vụ. Cũng không nên để Model MVC phát thông điệp ra message broker chỉ để cập nhật một nhãn trên giao diện; chọn cơ chế theo phạm vi và mục đích thực tế.

## 8. Lựa chọn theo loại ứng dụng

### Ứng dụng desktop hoặc giao diện tương tác dài hạn

Trong ứng dụng desktop chạy liên tục, nhiều vùng giao diện có thể cùng quan sát một Model. Ví dụ, khi thêm sách, bảng danh sách, số lượng tổng và biểu đồ theo thể loại đều cần cập nhật. Active Model với Observer/Property Change Listener có thể phù hợp.

Ở Java Swing, cập nhật component cần diễn ra trên Event Dispatch Thread (EDT). `PropertyChangeSupport` phát sự kiện đồng bộ trên thread gọi `firePropertyChange`; nếu Model thay đổi từ background thread, listener không được tự động chuyển sang EDT. View cần điều phối việc cập nhật, ví dụ bằng `SwingUtilities.invokeLater`, và Model cần có chiến lược an toàn luồng cho trạng thái dùng chung.

~~~java
model.addPropertyChangeListener(event -> {
    if ("books".equals(event.getPropertyName())) {
        SwingUtilities.invokeLater(() ->
                tableModel.replaceRows(model.books()));
    }
});
~~~

Đoạn minh họa cần import `javax.swing.SwingUtilities` và giả định `tableModel` thuộc giao diện Swing. Với JavaFX, cần dùng cơ chế property/binding và thread UI của JavaFX tương ứng.

### Ứng dụng web render phía máy chủ

Trong MVC web truyền thống, mỗi request thường tạo ra một response HTML rồi kết thúc. Controller gọi nghiệp vụ, lấy dữ liệu và render View. Đây là luồng gần với Passive Model: Controller quyết định khi nào render response.

Không cần bắt Model gửi notification đến template HTML đã được gửi về trình duyệt; response đã là một bản trình bày tại thời điểm xử lý request. Khi người dùng thao tác tiếp, browser gửi request mới và server tạo response mới.

### SPA và giao diện cập nhật bất đồng bộ

Trong SPA, trạng thái phía client có thể được quản lý bởi store hoặc state container. Khi state đổi, subscriber hoặc component được thông báo để render lại. Cơ chế này có nét tương đồng với Active Model/Observer, dù framework có thể triển khai bằng reactive stream, proxy, signal hoặc unidirectional data flow.

Nếu server cần đẩy thay đổi đến client mà không chờ request mới, có thể dùng WebSocket hoặc Server-Sent Events. Đây là cơ chế truyền thông giữa server và client; nó không tự động biến Domain Model thành Active Model. Nên giữ ranh giới: tầng nghiệp vụ phát domain event hoặc cập nhật trạng thái, một thành phần ứng dụng chuyển thay đổi thành thông điệp cho client.

## 9. Các nguyên tắc thiết kế khi dùng Active Model

**Phát thông báo sau khi trạng thái hợp lệ đã được cập nhật.** Không thông báo thành công trước khi Model hoàn tất hành động. Nếu thao tác thất bại do invariant, View không nên nhận một notification giả rằng trạng thái đã đổi.

**Thông báo thay đổi có ý nghĩa và đủ nhỏ.** Có thể thông báo thuộc tính hoặc loại thay đổi thay vì phát lại toàn bộ trạng thái sau mọi thao tác. Tuy nhiên, payload cần đủ thông tin để observer cập nhật chính xác mà không phải thực hiện quá nhiều truy vấn.

**Không để Model phụ thuộc vào View cụ thể.** Model có thể cung cấp interface listener hoặc publisher tổng quát, nhưng không nên import lớp bảng, component UI hay template HTML.

**Tránh chia sẻ collection có thể sửa.** Trả snapshot bất biến hoặc API đọc có kiểm soát để observer không thể thay đổi trạng thái nội bộ ngoài hành vi của Model.

**Quản lý vòng đời đăng ký.** View cần hủy đăng ký khi đóng hoặc không còn quan sát. Với listener theo ngữ cảnh tạm thời, có thể dùng cơ chế subscription có phương thức `close` để việc giải phóng dễ kiểm soát.

**Xác định chính sách lỗi và thứ tự.** Một listener lỗi không nên âm thầm ngăn các listener khác nhận sự kiện nếu ứng dụng yêu cầu tất cả observer được cập nhật. Cân nhắc ghi log, cô lập lỗi và tránh gọi callback trong khi đang giữ lock của Model.

**Quản lý thread và transaction.** Nếu Model dùng chung giữa nhiều thread, cần bảo vệ trạng thái và xác định notification phát trước hay sau commit. Không phát sự kiện “đã lưu” trước khi transaction thất bại hoặc rollback.

## 10. Kiểm thử Active Model và Passive Model

### Kiểm thử Active Model

- Khi thêm sách hợp lệ, trạng thái Model thay đổi và listener nhận đúng notification.
- Khi thao tác vi phạm invariant, trạng thái không đổi và không phát notification thành công.
- Payload thông báo không cho phép listener sửa collection nội bộ.
- Sau khi hủy đăng ký, listener không nhận các thay đổi tiếp theo.
- Nhiều listener nhận được thông báo theo chính sách đã thiết kế.
- Nếu cập nhật UI cần thread cụ thể, kiểm tra việc chuyển sang UI thread ở lớp adapter/View.

Ví dụ kiểm thử khái niệm:

~~~java
AtomicReference<PropertyChangeEvent> received = new AtomicReference<>();
model.addPropertyChangeListener(received::set);

model.addBook(new BookCatalogModel.Book("B-1", "Java cơ bản"));

assertEquals("books", received.get().getPropertyName());
assertEquals(1, model.books().size());
~~~

Đây là đoạn minh họa; mã kiểm thử đầy đủ cần tạo `model`, import các kiểu `java.beans` và `java.util.concurrent.atomic`, rồi kiểm tra thêm trường hợp listener được gỡ bỏ.

### Kiểm thử Passive Model

- Gọi hành vi hợp lệ làm Model thay đổi đúng.
- Controller gọi View với snapshot sau thao tác.
- Khi nghiệp vụ thất bại, Controller không render trạng thái thành công.
- Với request đọc, Controller chuyển dữ liệu đúng vào View Model.
- Khi có nhiều thao tác, thứ tự cập nhật và phản hồi được xác định rõ.

Passive Model thường dễ unit test vì không cần đăng ký listener hoặc xác minh chuỗi callback. Tuy nhiên, cần kiểm thử Controller để chắc chắn mọi nhánh thành công và lỗi đều chọn đúng View hoặc response.

## 11. Những lỗi thiết kế thường gặp

- **Cho rằng active nghĩa là tự chạy nền:** notification chỉ là tín hiệu thay đổi; nó không tự tạo thread hoặc thực hiện lưu trữ.
- **Để Model biết View cụ thể:** làm Model phụ thuộc công nghệ trình bày và khó tái sử dụng.
- **Không gỡ listener:** View đã đóng vẫn bị giữ trong bộ nhớ hoặc tiếp tục nhận sự kiện.
- **Phát sự kiện trước khi cập nhật xong:** observer đọc trạng thái trung gian hoặc trạng thái cuối cùng không được commit.
- **Phát quá nhiều sự kiện:** một thao tác logic tạo nhiều lần render không cần thiết.
- **Giả định listener chạy trên UI thread:** dễ gây lỗi khi Model thay đổi từ worker thread.
- **Coi Passive Model là mô hình dữ liệu nghèo hành vi:** Model thụ động vẫn cần bảo vệ quy tắc nghiệp vụ.
- **Nhầm property notification với domain event:** thay đổi phục vụ giao diện không nhất thiết là sự kiện nghiệp vụ.
- **Dùng notification để thay thế kiểm soát đồng thời:** listener không bảo đảm dữ liệu không bị ghi đè; transaction và đồng bộ trạng thái vẫn cần thiết.

## 12. Kết luận

Active Model phát thông báo khi trạng thái thay đổi để các View hoặc observer tự cập nhật. Passive Model không tự phát thông báo; Controller hoặc coordinator chủ động lấy dữ liệu mới và gọi View render. Hai cách tổ chức này khác nhau ở luồng điều khiển và mức độ phụ thuộc giữa các thành phần, không quyết định Model có chứa hành vi nghiệp vụ hay không.

Khi lựa chọn, hãy xem có bao nhiêu View cần phản ứng với cùng một thay đổi, giao diện có vòng đời dài hay xử lý theo từng request, thay đổi có đến từ nhiều nguồn hay không, và nhóm phát triển có thể quản lý listener, thread và lỗi callback ở mức nào. Chọn cơ chế đơn giản nhất vẫn giữ được tính nhất quán của trạng thái và trải nghiệm tương tác.
