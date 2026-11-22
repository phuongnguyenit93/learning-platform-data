# Passive View và Supervising Controller trong MVP

## 1. MVP và vị trí của hai biến thể

Model–View–Presenter (MVP) là một mẫu tổ chức giao diện tương tác. Nó tách phần hiển thị khỏi logic điều phối màn hình bằng cách đặt Presenter ở giữa View và Model hoặc các use case của ứng dụng.

Trong MVP, ba vai trò thường được hiểu như sau:

- **Model:** dữ liệu và hành vi nghiệp vụ, thường được truy cập qua Entity, Repository hoặc Application Service. Model không cần biết màn hình đang hiển thị ra sao.
- **View:** thành phần giao diện mà người dùng nhìn thấy và tương tác. View nhận dữ liệu để trình bày, phát sự kiện khi người dùng thao tác.
- **Presenter:** nhận sự kiện từ View, gọi use case, quyết định trạng thái hiển thị và cập nhật View thông qua hợp đồng đã định nghĩa.

Một luồng điển hình:

~~~mermaid
flowchart LR
    U[Người dùng] --> V[View]
    V -->|Sự kiện| P[Presenter]
    P -->|Gọi use case| M[Model / Service]
    M -->|Kết quả| P
    P -->|Dữ liệu trình bày| V
    V --> U
~~~

Trong thực tế có nhiều cách triển khai MVP. Hai biến thể thường được nhắc đến là **Passive View** và **Supervising Controller**. Chúng cùng giữ Presenter làm đầu mối điều phối, nhưng khác nhau ở lượng logic hiển thị được giao cho View.

Ở đây, tên *Supervising Controller* là tên thường dùng trong mô tả của Martin Fowler. Một số tài liệu MVP gọi vai trò tương ứng là *Supervising Presenter*. Điểm cần hiểu là cách chia trách nhiệm, không phải tên class bắt buộc.

## 2. Passive View: View thụ động

Passive View đẩy phần lớn logic trình bày sang Presenter. View chủ yếu cung cấp các thao tác để Presenter đọc dữ liệu người dùng và cập nhật giao diện; nó không tự quyết định luồng nghiệp vụ hoặc cách phản hồi phức tạp.

Ví dụ với form tạo sách, View có thể:

- Hiển thị tiêu đề, nhãn và giá trị trường.
- Thu thập nội dung người dùng nhập và phát sự kiện Save.
- Hiển thị lỗi mà Presenter cung cấp.
- Bật hoặc tắt trạng thái đang lưu.
- Hiển thị thông báo thành công.

Presenter chịu trách nhiệm kiểm tra dữ liệu theo quy tắc của màn hình, gọi use case, chuyển kết quả thành dữ liệu hiển thị và yêu cầu View cập nhật. View không tự gọi Service hoặc tự quyết định rằng ISBN đã tồn tại.

### Hợp đồng View

Trong Passive View, Presenter làm việc với một interface thay vì truy cập trực tiếp vào Swing, JavaFX, Android View hoặc DOM element.

~~~java
import java.util.Map;
import java.util.function.Consumer;

public record CreateBookInput(String title, String isbn) {}

public interface BookFormView {
    void setTitle(String title);
    void setSaving(boolean saving);
    void showErrors(Map<String, String> errors);
    void showSuccess(String message);
    void onSave(Consumer<CreateBookInput> handler);
}

public interface BookCreator {
    void create(CreateBookInput input);
}
~~~

`BookFormView` mô tả những gì Presenter cần từ màn hình. Nó không để lộ `JTextField`, `Button`, `Node` hay phần tử HTML. Nhờ đó, Presenter có thể được kiểm thử bằng một View giả mà không cần khởi chạy toolkit giao diện.

`onSave` đăng ký callback để View thông báo thao tác của người dùng. View thu thập giá trị từ các control và gửi thành `CreateBookInput`; việc thu thập giá trị là trách nhiệm giao tiếp với giao diện, còn validation và quyết định nghiệp vụ thuộc Presenter hoặc use case.

### Presenter điều phối toàn bộ phản hồi

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public final class BookFormPresenter {
    private final BookFormView view;
    private final BookCreator bookCreator;

    public BookFormPresenter(
            BookFormView view,
            BookCreator bookCreator) {
        this.view = view;
        this.bookCreator = bookCreator;
    }

    public void start() {
        view.setTitle("Tạo sách mới");
        view.onSave(this::save);
    }

    private void save(CreateBookInput input) {
        Map<String, String> errors = validate(input);
        if (!errors.isEmpty()) {
            view.showErrors(errors);
            return;
        }

        view.setSaving(true);
        try {
            bookCreator.create(input);
            view.showErrors(Map.of());
            view.showSuccess("Đã tạo sách thành công.");
        } catch (DuplicateIsbnException exception) {
            view.showErrors(Map.of(
                    "isbn", "ISBN này đã được sử dụng."));
        } finally {
            view.setSaving(false);
        }
    }

    private Map<String, String> validate(CreateBookInput input) {
        Map<String, String> errors = new LinkedHashMap<>();
        if (input.title() == null || input.title().isBlank()) {
            errors.put("title", "Tiêu đề không được để trống.");
        }
        if (input.isbn() == null || input.isbn().isBlank()) {
            errors.put("isbn", "ISBN không được để trống.");
        }
        return errors;
    }
}
~~~

Ví dụ giả định `DuplicateIsbnException` là lỗi nghiệp vụ được use case phát sinh. Presenter chuyển lỗi đó thành thông điệp dành cho form. Trong ứng dụng thật, các quy tắc như ISBN hợp lệ hoặc duy nhất vẫn phải được bảo vệ ở Model/Service; validation trong Presenter chủ yếu phục vụ phản hồi sớm và trải nghiệm màn hình.

### View triển khai chỉ làm nhiệm vụ giao tiếp

Một View Swing có thể triển khai interface như sau:

~~~java
public final class SwingBookFormView implements BookFormView {
    private final JTextField titleField = new JTextField();
    private final JTextField isbnField = new JTextField();
    private final JButton saveButton = new JButton("Lưu");
    private final JLabel heading = new JLabel();
    private final JLabel status = new JLabel();
    private Consumer<CreateBookInput> saveHandler = input -> {};

    public SwingBookFormView() {
        saveButton.addActionListener(event -> saveHandler.accept(
                new CreateBookInput(
                        titleField.getText(),
                        isbnField.getText())));
    }

    @Override
    public void setTitle(String title) {
        heading.setText(title);
    }

    @Override
    public void setSaving(boolean saving) {
        saveButton.setEnabled(!saving);
        status.setText(saving ? "Đang lưu..." : "");
    }

    @Override
    public void showErrors(Map<String, String> errors) {
        // Hiển thị lỗi theo tên trường; không tự quyết định quy tắc.
    }

    @Override
    public void showSuccess(String message) {
        status.setText(message);
    }

    @Override
    public void onSave(Consumer<CreateBookInput> handler) {
        this.saveHandler = handler;
    }
}
~~~

Đây là đoạn minh họa, lược bỏ phần bố trí layout và hiển thị lỗi chi tiết; các import Swing và `Map` cần được bổ sung. Listener chỉ gom giá trị trường rồi chuyển sự kiện cho Presenter. Nó không gọi Service, kiểm tra ISBN hoặc tự quyết định có thể lưu hay không.

### Đặc điểm của Passive View

- View gần như không chứa logic trình bày có điều kiện; Presenter quyết định dữ liệu và trạng thái cần hiển thị.
- Hợp đồng View thường có nhiều phương thức nhỏ như `showErrors`, `setSaving`, `showSuccess`.
- Presenter có thể được kiểm thử độc lập với framework giao diện.
- View implementation có thể thay đổi từ Swing sang JavaFX hoặc một công nghệ khác mà Presenter ít bị ảnh hưởng.

Đổi lại, Presenter có thể trở nên dài và phải gọi nhiều phương thức View. Một thay đổi nhỏ trong giao diện đôi khi cần cập nhật cả interface và Presenter. Nếu lạm dụng, hợp đồng View sẽ chứa quá nhiều thao tác mang tính chi tiết của widget.

## 3. Supervising Controller: View hỗ trợ binding đơn giản

Supervising Controller vẫn dùng Presenter để điều phối hành vi, nhưng cho phép View thực hiện một số công việc trình bày đơn giản. Ví dụ:

- Bind một thuộc tính dữ liệu vào text field hoặc label.
- Bind danh sách dữ liệu vào table/list control.
- Hiển thị trạng thái rỗng khi collection không có phần tử.
- Áp dụng định dạng hiển thị cơ bản như ngày tháng hoặc nhãn.
- Đồng bộ thuộc tính hiển thị với một presentation state đơn giản.

Presenter vẫn chịu trách nhiệm gọi use case, quyết định luồng tương tác, xử lý các điều kiện phức tạp và cập nhật presentation state. View không tự quyết định quyền nghiệp vụ, tính hợp lệ của hành động hoặc cách phối hợp nhiều use case.

### Presentation state cho màn hình

Giả sử màn hình danh sách sách có tiêu đề, danh sách kết quả và trạng thái rỗng. Có thể biểu diễn dữ liệu hiển thị bằng một model dành riêng cho màn hình:

~~~java
import java.util.List;
import java.util.UUID;

public record BookRow(UUID id, String title, String author) {}

public record BookListState(
        String heading,
        String query,
        List<BookRow> rows
) {
    public BookListState {
        rows = List.copyOf(rows);
    }

    public boolean isEmpty() {
        return rows.isEmpty();
    }
}
~~~

`BookListState` là presentation state, không phải Domain Entity. Nó chứa dữ liệu ở dạng View cần để trình bày. Hàm `isEmpty()` là phép suy ra đơn giản từ collection; các quyết định nghiệp vụ không nên được đặt trong đối tượng này.

### Hợp đồng View có khả năng bind

~~~java
import java.util.List;
import java.util.function.Consumer;

public interface BookListView {
    void bind(BookListState state);
    void onSearch(Consumer<String> handler);
    void onOpen(Consumer<java.util.UUID> handler);
}

public interface BookSearch {
    List<Book> search(String query);
}

public interface BookRowMapper {
    BookRow toRow(Book book);
}
~~~

View nhận state và dùng cơ chế binding của framework để cập nhật control. Presenter đăng ký xử lý sự kiện tìm kiếm và mở chi tiết.

Ví dụ cách View JavaFX bind state vào control:

~~~java
headingLabel.setText(state.heading());
queryField.setText(state.query());
tableView.setItems(FXCollections.observableArrayList(state.rows()));
emptyLabel.visibleProperty().bind(
        Bindings.isEmpty(tableView.getItems()));
~~~

Đoạn mã thể hiện binding/ánh xạ dữ liệu đơn giản. Với JavaFX, các property observable có thể giúp đồng bộ hai chiều hoặc cập nhật tự động khi state thay đổi; ví dụ trên tạo danh sách mới nên phù hợp với lần bind ban đầu. Nếu cần cập nhật liên tục, dùng observable state hoặc gọi bind lại khi Presenter phát state mới.

### Presenter xử lý quyết định và cập nhật state

~~~java
import java.util.List;
import java.util.UUID;

public final class BookListPresenter {
    private final BookListView view;
    private final BookSearch search;
    private final BookRowMapper mapper;

    public BookListPresenter(
            BookListView view,
            BookSearch search,
            BookRowMapper mapper) {
        this.view = view;
        this.search = search;
        this.mapper = mapper;
    }

    public void start() {
        view.onSearch(this::searchBooks);
        view.onOpen(this::openBook);
        searchBooks("");
    }

    private void searchBooks(String rawQuery) {
        String query = rawQuery == null ? "" : rawQuery.trim();
        List<BookRow> rows = search.search(query).stream()
                .map(mapper::toRow)
                .toList();

        view.bind(new BookListState(
                "Danh sách sách", query, rows));
    }

    private void openBook(UUID id) {
        // Điều phối use case mở chi tiết hoặc yêu cầu navigation.
    }
}
~~~

Ví dụ giả định `BookRowMapper` chuyển Domain Model thành `BookRow`. Presenter chuẩn hóa query, gọi use case và tạo state cho màn hình. View có thể bind state vào label và table, đồng thời tự áp dụng các quy tắc hiển thị đơn giản như ẩn nhãn “Không có kết quả” khi danh sách không rỗng.

Ở biến thể này, View có thêm trách nhiệm trình bày so với Passive View, nhưng không trở thành nơi chứa quy tắc nghiệp vụ. Ví dụ, View có thể bind `isEmpty` để hiện trạng thái rỗng; nó không tự quyết định người dùng có quyền xem sách nào hoặc có được phép xóa sách hay không.

## 4. So sánh Passive View và Supervising Controller

| Tiêu chí | Passive View | Supervising Controller |
|---|---|---|
| Logic trong View | Tối thiểu; chủ yếu nhận lệnh hiển thị và chuyển sự kiện | Có binding và logic trình bày đơn giản |
| Vai trò Presenter | Quyết định gần như toàn bộ nội dung và trạng thái hiển thị | Điều phối use case và quyết định phức tạp; cung cấp state để View bind |
| Data binding | Presenter thường cập nhật View qua interface | View có thể bind thuộc tính và collection đơn giản |
| Độ phức tạp Presenter | Có thể lớn do phải điều khiển từng chi tiết hiển thị | Có thể nhẹ hơn với màn hình nhiều trường dữ liệu |
| Độ phức tạp View | Ít logic, nhưng có thể nhiều phương thức giao diện | Nhiều binding và một ít logic trình bày |
| Kiểm thử Presenter | Rất thuận tiện với fake View | Vẫn thuận tiện; kiểm tra thêm state và quyết định |
| Kiểm thử View | Chủ yếu kiểm tra ánh xạ lệnh thành control | Cần kiểm tra binding, formatting và trạng thái hiển thị |
| Phù hợp | Màn hình có quy tắc tương tác phức tạp hoặc cần kiểm soát chặt | Màn hình CRUD, form và danh sách có nhiều binding đơn giản |

Không có biến thể nào luôn tốt hơn. Passive View tối đa hóa khả năng kiểm thử và kiểm soát logic, nhưng có thể tạo Presenter và interface quá lớn. Supervising Controller giảm lượng mã điều khiển hiển thị, nhưng cần giữ View ở đúng phạm vi trình bày để tránh logic nghiệp vụ rò rỉ vào giao diện.

## 5. Phân biệt logic trình bày và logic nghiệp vụ

Ranh giới này quyết định việc một đoạn logic nên nằm ở View hay Presenter/Model.

| Công việc | Vị trí thường phù hợp |
|---|---|
| Gán text vào label, bind collection vào table | View |
| Ẩn/hiện trạng thái rỗng dựa trên collection | View trong Supervising Controller; Presenter trong Passive View |
| Chuẩn hóa dữ liệu tìm kiếm trước khi gọi use case | Presenter hoặc application layer theo quy ước |
| Kiểm tra ISBN có tồn tại trong hệ thống | Service/Model |
| Quyết định người dùng có quyền sửa sách | Security/application policy |
| Điều phối lưu dữ liệu rồi chuyển sang màn hình kết quả | Presenter |
| Định dạng ngày theo locale | View hoặc formatter trình bày |
| Tính số tiền phải trả theo chính sách nghiệp vụ | Domain/Application Model |
| Chuyển mã trạng thái miền thành nội dung phù hợp màn hình | Presenter/mapper hoặc presentation layer |

Ví dụ, việc đổi `2026-11-19` thành `19/11/2026` là định dạng trình bày. Việc xác định một hợp đồng có hết hạn hay không là quy tắc nghiệp vụ. Việc hiện nút “Hủy” dựa trên cờ `canCancel` là trình bày; server vẫn phải kiểm tra quyền và trạng thái khi nhận lệnh hủy.

## 6. MVP khác MVC ở điểm nào?

MVP và MVC cùng tách dữ liệu, giao diện và điều phối, nhưng quan hệ giữa các thành phần thường khác nhau.

| Khía cạnh | MVC web phía máy chủ | MVP |
|---|---|---|
| Thành phần điều phối | Controller nhận HTTP request và chọn response/View | Presenter nhận sự kiện từ View và điều phối màn hình |
| Quan hệ View | Controller thường trả View logic và Model attributes; template render response | View thường giữ hợp đồng interface mà Presenter gọi trực tiếp |
| Vòng đời | Thường theo từng HTTP request | Thường gắn với màn hình hoặc phiên tương tác |
| Giao tiếp | Request/response và model binding | Callback/event từ View và lệnh cập nhật View |
| Công nghệ thường gặp | Spring MVC, ASP.NET MVC, server-side templates | Desktop UI, mobile UI, SPA hoặc UI component tương tác |

Đây là khác biệt điển hình, không phải ranh giới tuyệt đối. Một ứng dụng web phía client có thể dùng MVP ở frontend; một ứng dụng MVC có thể có presentation layer và view model khá phong phú. Tên mẫu không quan trọng bằng việc xác định ai sở hữu state, ai xử lý event và nơi nào chứa quy tắc.

Presenter không đơn giản là đổi tên Controller. Trong MVP, View thường gọi Presenter qua event/callback và Presenter cập nhật View qua interface. Trong MVC web truyền thống, Controller xử lý một request và trả response; View thường không giữ tham chiếu trực tiếp đến Controller sau khi render.

## 7. Vòng đời Presenter và View

Presenter thường được tạo khi màn hình được mở và kết thúc khi màn hình bị đóng hoặc thay thế. Vòng đời cần được quản lý rõ để tránh giữ tham chiếu đến View đã bị hủy.

Một số nguyên tắc:

- Đăng ký event handler khi màn hình được khởi tạo hoặc khi Presenter bắt đầu.
- Hủy đăng ký listener khi màn hình bị đóng nếu framework hoặc event source giữ tham chiếu lâu dài.
- Hủy hoặc bỏ qua kết quả bất đồng bộ nếu View đã không còn hoạt động.
- Không cập nhật Swing/JavaFX UI từ background thread; chuyển kết quả về UI thread theo cơ chế của framework.
- Không giữ state riêng của màn hình trong singleton service dùng chung.
- Nếu Presenter được giữ lâu hơn View, dùng `detach()` hoặc lifecycle callback để xóa tham chiếu.

Ví dụ hợp đồng có thể bổ sung:

~~~java
public interface ScreenPresenter {
    void start();
    void stop();
}
~~~

`stop()` có thể hủy subscription, listener hoặc tác vụ đang chờ. Nó không nên đóng dependency dùng chung mà Presenter không sở hữu, chẳng hạn một application service singleton.

## 8. Xử lý tác vụ bất đồng bộ

Một Presenter có thể gọi use case chạy nền để tìm kiếm hoặc tải dữ liệu. Khi thao tác hoàn tất, kết quả cần được chuyển về UI thread trước khi cập nhật View.

Ví dụ với JavaFX, có thể dùng `Task` hoặc `Platform.runLater`; với Swing, dùng `SwingWorker` hoặc `SwingUtilities.invokeLater`. Không gọi trực tiếp phương thức thay đổi widget từ executor thread.

Presenter cần xử lý trạng thái loading, lỗi và kết quả cũ. Nếu người dùng nhập nhiều truy vấn liên tiếp, kết quả của truy vấn trước có thể về sau truy vấn mới. Có thể dùng request sequence/token để bỏ qua kết quả đã lỗi thời.

Không để View tự gọi nhiều Service song song rồi tự quyết định kết quả nào được hiển thị; việc điều phối thứ tự và trạng thái tương tác thuộc Presenter hoặc application layer.

## 9. Kiểm thử Passive View

Vì View được biểu diễn bằng interface nhỏ, có thể viết fake để ghi nhận những lệnh Presenter gửi đến:

~~~java
import java.util.Map;
import java.util.function.Consumer;

final class FakeBookFormView implements BookFormView {
    String title;
    boolean saving;
    Map<String, String> errors = Map.of();
    String successMessage;
    Consumer<CreateBookInput> saveHandler;

    @Override
    public void setTitle(String title) { this.title = title; }

    @Override
    public void setSaving(boolean saving) { this.saving = saving; }

    @Override
    public void showErrors(Map<String, String> errors) {
        this.errors = Map.copyOf(errors);
    }

    @Override
    public void showSuccess(String message) {
        this.successMessage = message;
    }

    @Override
    public void onSave(Consumer<CreateBookInput> handler) {
        this.saveHandler = handler;
    }

    void submit(CreateBookInput input) {
        saveHandler.accept(input);
    }
}
~~~

Test có thể tạo `FakeBookFormView`, tiêm vào Presenter cùng một `BookCreator` giả, gọi `start()` rồi kích hoạt `submit()`. Sau đó kiểm tra lỗi, trạng thái saving, thông báo thành công và việc use case được gọi.

Ví dụ kiểm tra dữ liệu không hợp lệ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void blankTitleShowsErrorWithoutCallingUseCase() {
    FakeBookFormView view = new FakeBookFormView();
    BookCreator creator = mock(BookCreator.class);
    BookFormPresenter presenter = new BookFormPresenter(view, creator);
    presenter.start();

    view.submit(new CreateBookInput("  ", "9780132350884"));

    assertEquals(
            "Tiêu đề không được để trống.",
            view.errors.get("title"));
    verifyNoInteractions(creator);
}
~~~

Test cần JUnit và Mockito. Nó kiểm tra Presenter quyết định đúng khi input không hợp lệ; không cần dựng giao diện thật. Các quy tắc miền vẫn cần test riêng trong Service/Model.

## 10. Kiểm thử Supervising Controller

Với Supervising Controller, có hai nhóm hành vi cần kiểm tra:

1. **Presenter:** use case được gọi đúng, state được tạo đúng, điều kiện phức tạp và luồng tương tác được xử lý đúng.
2. **View binding:** thuộc tính state được ánh xạ đúng vào control, định dạng đơn giản đúng, trạng thái rỗng/loading/error hiển thị theo dữ liệu.

Unit test Presenter có thể kiểm tra `BookListState` mà không cần khởi động UI toolkit. View test dùng framework giao diện hoặc test component để xác minh binding. Một integration test nhỏ xác minh sự kiện từ View đi đến Presenter và state mới được phản ánh trên màn hình.

Không nên chỉ kiểm tra Presenter trả đúng state rồi kết luận binding của View hoạt động. Một lỗi tên property hoặc binding expression có thể khiến UI không cập nhật dù Presenter hoàn toàn đúng.

## 11. Khi nào nên chọn từng biến thể?

**Chọn Passive View khi:**

- Màn hình có nhiều nhánh tương tác và quy tắc hiển thị phức tạp.
- Muốn kiểm thử Presenter độc lập tối đa với UI framework.
- Giao diện có nhiều implementation hoặc cần thay đổi công nghệ.
- Cần kiểm soát chặt mọi trạng thái và thông điệp View hiển thị.

**Chọn Supervising Controller khi:**

- Màn hình chủ yếu hiển thị dữ liệu và form có binding đơn giản.
- Framework đã có data binding tốt và dễ kiểm thử.
- Muốn giảm các lệnh setter lặp lại trong Presenter.
- Logic nghiệp vụ và điều phối vẫn được giữ ở Presenter/Service.

Có thể kết hợp hai cách trong cùng ứng dụng. Một màn hình wizard có thể dùng Passive View vì nhiều bước và điều kiện phức tạp; một màn hình danh sách có thể dùng Supervising Controller vì phần lớn công việc là bind dữ liệu vào bảng và bộ lọc.

## 12. Những sai lầm thường gặp

- **Để View gọi Service trực tiếp:** luồng điều phối bị phân tán và Presenter không còn là điểm kiểm soát.
- **Để Presenter truy cập widget cụ thể:** Presenter bị gắn với framework và khó kiểm thử.
- **Đưa quy tắc nghiệp vụ vào Presenter:** cùng một quy tắc có thể bị bỏ qua khi use case được gọi từ API hoặc tác vụ nền.
- **Đưa quá nhiều logic vào View của Supervising Controller:** View dần trở thành nơi quyết định hành vi thay cho Presenter.
- **Coi mọi phép biến đổi dữ liệu là nghiệp vụ:** định dạng ngày hoặc hiển thị trạng thái rỗng có thể thuộc presentation layer.
- **Coi mọi phép biến đổi là trình bày:** tính giá, quyền truy cập hoặc điều kiện chuyển trạng thái phải được bảo vệ ở tầng nghiệp vụ.
- **Tạo một Presenter khổng lồ cho toàn ứng dụng:** Presenter nên có phạm vi theo màn hình hoặc use case có liên quan.
- **Không quản lý listener và async task:** có thể giữ View cũ trong bộ nhớ hoặc cập nhật giao diện đã đóng.
- **Kiểm thử Presenter nhưng bỏ qua binding:** Supervising View có thể hiển thị sai dù state đúng.
- **Dùng Passive View cho mọi màn hình một cách máy móc:** interface và Presenter có thể phình to không cần thiết.

## 13. Kết luận

Passive View và Supervising Controller là hai cách phân chia trách nhiệm trong MVP. Passive View giữ View thật thụ động, để Presenter quyết định và phát lệnh cho gần như mọi thay đổi hiển thị. Supervising Controller cho View thực hiện binding và trình bày đơn giản, trong khi Presenter vẫn nắm luồng tương tác, use case và quyết định phức tạp.

Khi chọn biến thể, hãy nhìn vào độ phức tạp của màn hình, khả năng binding của UI framework và mức độ cần kiểm thử độc lập. Dù chọn cách nào, View không nên sở hữu quy tắc nghiệp vụ; Presenter không nên phụ thuộc trực tiếp vào widget; Model/Service vẫn phải bảo vệ invariant và quyền truy cập. Ranh giới rõ ràng giúp giao diện dễ thay đổi, Presenter dễ kiểm thử và hành vi ứng dụng nhất quán.
