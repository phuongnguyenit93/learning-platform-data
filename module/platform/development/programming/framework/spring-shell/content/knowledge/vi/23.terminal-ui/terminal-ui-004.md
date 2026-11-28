# `InputView`, `ListView` và lựa chọn dữ liệu

Một command line có thể cần nhiều hơn việc đọc một option rồi trả về kết quả. Người dùng có thể muốn gõ từ khóa để lọc danh sách khách hàng, di chuyển qua các kết quả bằng phím mũi tên, rồi chọn một mục để xem hoặc xử lý. Terminal UI của Spring Shell cung cấp `InputView` và `ListView` để xây dựng kiểu tương tác này.

`InputView` là vùng nhập văn bản có con trỏ và các phím sửa nội dung. `ListView<T>` hiển thị danh sách đối tượng theo chiều dọc, hỗ trợ di chuyển, đánh dấu và mở mục đang chọn. Hai view phát event để ứng dụng phản ứng với nội dung nhập hoặc lựa chọn của người dùng. Bài viết sử dụng API Spring Shell 3.4.3 trong package `org.springframework.shell.component.view` và `org.springframework.shell.component.view.control`.

## Vai trò của `InputView` và `ListView`

Hai view phục vụ hai phần khác nhau của một màn hình tương tác:

| View | Vai trò | Dữ liệu quan trọng |
| --- | --- | --- |
| `InputView` | Nhận và chỉnh sửa chuỗi trong một vùng giới hạn | `getInputText()` và event `InputViewTextChangeEvent` |
| `ListView<T>` | Hiển thị các mục có kiểu dữ liệu T và điều hướng trong danh sách | Danh sách item, item hiện hành và event chọn/mở mục |

`InputView` kế thừa `BoxView`, vì vậy có thể đặt tiêu đề, đường viền và các thuộc tính trình bày của box. `ListView<T>` cũng kế thừa `BoxView`, đồng thời có `CellFactory` để quyết định cách vẽ từng item.

Đây là các view cấp thấp. Chúng cung cấp khả năng vẽ và nhận sự kiện; ứng dụng chịu trách nhiệm lọc dữ liệu, xác thực nội dung, lưu mục đã chọn và quyết định khi nào kết thúc màn hình. Nếu chỉ cần một câu hỏi nhập chuỗi hoặc một selector đơn giản trong wizard, các component cấp cao như `StringInput`, `SingleItemSelector` và `ComponentFlow` thường ít mã hơn.

## Khởi tạo `TerminalUI`

`TerminalUI` điều phối terminal, event loop, bàn phím, chuột và cây view. Trong ứng dụng Spring Shell 3.4.x, nên inject `TerminalUIBuilder` đã được auto-configure thay vì tự tạo mọi dịch vụ liên quan:

```java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.stereotype.Component;

@Component
public class CustomerBrowser {

    private final TerminalUIBuilder terminalUIBuilder;

    public CustomerBrowser(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void show() {
        TerminalUI ui = terminalUIBuilder.build();
        // Khai báo và gắn view trước khi gọi ui.run().
    }
}
```

Sau khi tạo view gốc, cấu hình và chạy giao diện:

```java
ui.configure(rootView);
ui.setRoot(rootView, true);
ui.run();
```

- `configure(view)` gắn các tích hợp cần thiết như event loop, theme resolver và view service.
- `setRoot(view, true)` đặt view gốc và yêu cầu dùng toàn màn hình.
- `run()` bắt đầu vòng lặp giao diện và chặn cho đến khi có yêu cầu thoát.

Nếu không cần toàn màn hình, truyền `false` vào `setRoot`. `TerminalUI.redraw()` gửi yêu cầu vẽ lại màn hình qua event loop; không nên tự xóa terminal và vẽ lại bằng mã ANSI trong mỗi callback.

## `InputView`: nhận và chỉnh sửa văn bản

Tạo `InputView` bằng constructor không tham số:

```java
import org.springframework.shell.component.view.control.InputView;

InputView input = new InputView();
input.setTitle("Tìm khách hàng");
```

`InputView` hiển thị văn bản trong một vùng `Rectangle` và hỗ trợ các thao tác sửa nội dung. Các binding mặc định:

| Phím | Tác dụng |
| --- | --- |
| `Left` | Di chuyển con trỏ sang trái |
| `Right` | Di chuyển con trỏ sang phải |
| `Backspace` | Xóa ký tự bên trái con trỏ |
| `Delete` | Xóa ký tự bên phải con trỏ |

Để đọc nội dung hiện tại, dùng `getInputText()`:

```java
String currentText = input.getInputText();
```

Phương thức này trả về chuỗi mà view đang biết tại thời điểm gọi. `InputView` không tự chuyển chuỗi thành số, không kiểm tra định dạng email và không lưu dữ liệu vào service. Hãy để command hoặc application service xác thực nội dung trước khi sử dụng.

### Theo dõi thay đổi bằng `InputViewTextChangeEvent`

Mỗi khi nội dung thay đổi, `InputView` phát event `InputViewTextChangeEvent`. Event có `args()` kiểu `InputViewTextChangeEventArgs`, chứa:

- `oldText()`: nội dung trước thay đổi.
- `newText()`: nội dung sau thay đổi.

Đăng ký listener qua event loop của `TerminalUI`:

```java
import org.springframework.shell.component.view.control.InputView;
import reactor.core.Disposable;

Disposable inputChanges = ui.getEventLoop()
        .viewEvents(InputView.InputViewTextChangeEvent.class, input)
        .subscribe(event -> {
            String previous = event.args().oldText();
            String current = event.args().newText();
            logger.debug("Input changed from '{}' to '{}'", previous, current);
        });

ui.getEventLoop().onDestroy(inputChanges);
```

Tham số `input` trong `viewEvents(..., input)` lọc event theo đúng view cần theo dõi. Nếu giao diện có nhiều ô nhập, bộ lọc này tránh xử lý nhầm event của một ô khác. `onDestroy(disposable)` đăng ký subscription để event loop tự dispose khi vòng đời kết thúc.

Không gọi truy vấn database hoặc API mạng đồng bộ cho mỗi ký tự người dùng gõ. Với tìm kiếm dữ liệu lớn, nên debounce/throttle event, giới hạn số kết quả hoặc chuyển việc tìm kiếm sang tác vụ bất đồng bộ. Khi kết quả bất đồng bộ quay về, cập nhật view thông qua event loop và yêu cầu redraw.

### `InputView` không tự có nút xác nhận

Các binding mặc định của `InputView` tập trung vào di chuyển con trỏ và xóa ký tự. View không tự định nghĩa hợp đồng lưu kết quả hoặc hoàn tất command. Nếu cần nút xác nhận, hãy kết hợp với `ButtonView` hoặc đăng ký một key binding phù hợp trong giao diện. Khi người dùng xác nhận, đọc `getInputText()`, kiểm tra giá trị rồi chuyển sang bước nghiệp vụ.

Không nên xem một event thay đổi văn bản là tín hiệu người dùng đã xác nhận. Người dùng có thể tiếp tục sửa nội dung sau mỗi event; chỉ xử lý nghiệp vụ khi có hành động xác nhận rõ ràng.

## `ListView<T>`: hiển thị danh sách đối tượng

`ListView<T>` là view hiển thị danh sách theo chiều dọc. Kiểu generic `T` có thể là `String` hoặc một đối tượng miền như `Customer`, `Environment` hay `DeploymentTarget`.

Ví dụ danh sách chuỗi:

```java
import java.util.List;

import org.springframework.shell.component.view.control.ListView;

ListView<String> list = new ListView<>();
list.setTitle("Môi trường triển khai");
list.setItems(List.of("development", "staging", "production"));
```

Nếu không cấu hình `CellFactory`, implementation mặc định hiển thị từng item bằng `toString()`. Vì vậy, đối tượng miền nên có `toString()` ngắn, rõ và phù hợp với terminal; không nên trả về toàn bộ dữ liệu nội bộ hoặc thông tin nhạy cảm.

Ví dụ đối tượng khách hàng:

```java
public record CustomerRow(String code, String name, String email) {

    @Override
    public String toString() {
        return code + " - " + name;
    }
}
```

Sau đó:

```java
ListView<CustomerRow> customersView = new ListView<>();
customersView.setTitle("Khách hàng");
customersView.setItems(customerRows);
```

### Thay đổi danh sách khi dữ liệu đầu vào thay đổi

`setItems(...)` thay danh sách item của view. Có thể dùng phương thức này khi lọc theo từ khóa, đổi trang hoặc nhận dữ liệu mới:

```java
import java.util.List;
import java.util.Locale;

String query = filter.getInputText().strip();

List<CustomerRow> filtered = customerRows.stream()
        .filter(customer -> customer.name()
                .toLowerCase(Locale.ROOT)
                .contains(query.toLowerCase(Locale.ROOT)))
        .toList();

customersView.setItems(filtered);
ui.redraw();
```

Nếu dữ liệu được nạp từ dịch vụ, chỉ đưa tập kết quả cần hiển thị vào view. Với danh sách lớn, không nên nạp toàn bộ bản ghi vào một `ListView`; hãy phân trang hoặc lọc trước ở service để giữ thời gian vẽ và điều hướng ổn định.

## Chọn cách hiển thị trạng thái của item

Constructor của `ListView` có thể nhận `ListView.ItemStyle`. Enum này quyết định dấu hiệu lựa chọn trên từng item:

| `ItemStyle` | Hiển thị | Phù hợp khi |
| --- | --- | --- |
| `NOCHECK` | Item bình thường, không có dấu chọn | Danh sách điều hướng hoặc mở chi tiết |
| `CHECKED` | Có trạng thái checked/unchecked | Danh sách cho phép đánh dấu nhiều mục |
| `RADIO` | Thể hiện lựa chọn kiểu radio | Chọn một mục trong một nhóm |

Ví dụ chọn một môi trường:

```java
ListView<String> environmentView = new ListView<>(
        ListView.ItemStyle.RADIO);
environmentView.setItems(List.of(
        "development", "staging", "production"));
```

Ví dụ danh sách có dấu check:

```java
ListView<String> featureView = new ListView<>(
        ListView.ItemStyle.CHECKED);
featureView.setItems(List.of(
        "authentication", "audit-log", "notifications"));
```

`CHECKED` điều khiển cách biểu diễn trạng thái checked của item; `RADIO` biểu diễn lựa chọn đơn. Nếu nghiệp vụ cần lấy tập nhiều mục đã chọn, hãy xác định rõ model lưu trạng thái của ứng dụng và kiểm thử cách đồng bộ nó với thao tác Space. Với trường hợp chỉ cần wizard chọn một hoặc nhiều mục và trả kết quả có cấu trúc, `SingleItemSelector` hoặc `MultiItemSelector` cấp cao có thể phù hợp hơn.

## Phím điều hướng và thao tác chuột của `ListView`

`ListView` có sẵn các view command `LINE_UP` và `LINE_DOWN` để di chuyển dòng đang hoạt động.

| Phím/thao tác | Hành vi mặc định |
| --- | --- |
| `Up` | Di chuyển mục đang hoạt động lên trên |
| `Down` | Di chuyển mục đang hoạt động xuống dưới |
| `Enter` | Yêu cầu mở mục đang hoạt động |
| `Space` | Thay đổi trạng thái checked của mục đang hoạt động |
| Lăn chuột lên/xuống | Di chuyển lựa chọn lên/xuống |
| Nhả nút chuột trái trên mục | Chọn/mở mục theo binding của view |

Hai event quan trọng:

- `ListViewSelectedItemChangedEvent`: item đang hoạt động thay đổi, thường xảy ra khi người dùng di chuyển bằng phím mũi tên.
- `ListViewOpenSelectedItemEvent`: người dùng yêu cầu mở item đang hoạt động, thường qua Enter hoặc thao tác chuột tương ứng.

Hai event này không có cùng ý nghĩa. Event thay đổi item phù hợp để cập nhật phần xem trước; event mở item phù hợp để chốt lựa chọn hoặc điều hướng sang màn hình chi tiết.

## Nhận item người dùng đã chọn

Event của `ListView` chứa `ListViewItemEventArgs<T>` trong `args()`. Record này có phương thức `item()` trả về đối tượng đã chọn.

Ví dụ một view chọn khách hàng:

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.ListView;
import reactor.core.Disposable;

public Optional<CustomerRow> chooseCustomer(
        TerminalUIBuilder terminalUIBuilder,
        List<CustomerRow> customerRows) {

    TerminalUI ui = terminalUIBuilder.build();
    ListView<CustomerRow> list = new ListView<>(ListView.ItemStyle.RADIO);
    list.setTitle("Chọn khách hàng - Enter để xác nhận");
    list.setItems(customerRows);

    ui.configure(list);
    ui.setRoot(list, true);

    AtomicReference<CustomerRow> selected = new AtomicReference<>();
    Disposable selection = ui.getEventLoop()
            .viewEvents(ListView.ListViewOpenSelectedItemEvent.class, list)
            .subscribe(event -> {
                CustomerRow item = (CustomerRow) event.args().item();
                selected.set(item);
                ui.getEventLoop().dispatch(ShellMessageBuilder.ofInterrupt());
            });

    ui.getEventLoop().onDestroy(selection);
    ui.run();

    return Optional.ofNullable(selected.get());
}
```

`ui.run()` chặn cho đến khi event loop nhận thông điệp interrupt. Khi người dùng mở một item, callback lưu đối tượng vào `AtomicReference` rồi gửi `ShellMessageBuilder.ofInterrupt()` để kết thúc vòng lặp. Sau đó method trả `Optional` để caller phân biệt trường hợp đã chọn và trường hợp người dùng thoát mà chưa chọn.

Trong code ứng dụng, hãy xử lý `Optional.empty()` như một lần hủy hoặc thoát. Không gọi service cập nhật dữ liệu nếu chưa có item được chọn và xác nhận.

## Phân biệt item đang trỏ tới và item được xác nhận

Khi người dùng nhấn Up hoặc Down, `ListViewSelectedItemChangedEvent` cho biết mục đang hoạt động thay đổi. Có thể dùng event đó để hiển thị xem trước:

```java
import java.util.function.Consumer;
import reactor.core.Disposable;

Disposable preview = ui.getEventLoop()
        .viewEvents(ListView.ListViewSelectedItemChangedEvent.class, list)
        .subscribe(event -> {
            CustomerRow active = (CustomerRow) event.args().item();
            updatePreview.accept(active);
            ui.redraw();
        });

ui.getEventLoop().onDestroy(preview);
```

`ListViewOpenSelectedItemEvent` mới là tín hiệu người dùng yêu cầu mở/chốt item. Nếu command thực hiện thao tác có tác động như xóa, phát hành hoặc thay đổi cấu hình, hãy dùng một bước xác nhận riêng trước khi gọi service. Di chuyển con trỏ hoặc xem trước dữ liệu không đồng nghĩa với việc người dùng đã chấp thuận thao tác.

## Tùy chỉnh cách vẽ item bằng `CellFactory`

`ListView` mặc định hiển thị `toString()` của item. Khi cần trình bày nhiều trường, có thể dùng `setCellFactory(...)` để tạo một `ListCell` riêng cho mỗi item.

```java
import org.springframework.shell.component.view.control.ListView;
import org.springframework.shell.component.view.control.cell.AbstractListCell;

static class CustomerCell extends AbstractListCell<CustomerRow> {

    CustomerCell(CustomerRow item, ListView.ItemStyle itemStyle) {
        super(item, itemStyle);
    }

    @Override
    protected String getText() {
        CustomerRow customer = getItem();
        return customer.code() + " | " + customer.name();
    }
}
```

Đăng ký cell factory:

```java
list.setCellFactory((view, item) ->
        new CustomerCell(item, view.getItemStyle()));
```

`AbstractListCell` cung cấp sẵn cách vẽ indicator và trạng thái chọn; lớp con chỉ cần tùy chỉnh phần text nếu muốn. Constructor nhận `itemStyle` để cell biết cách thể hiện trạng thái `NOCHECK`, `CHECKED` hoặc `RADIO` của list.

Nếu cần toàn quyền vẽ, có thể override `draw(Screen)` và dùng `Screen`, `Rectangle` cùng writer của Spring Shell để vẽ nội dung. Chỉ nên tự vẽ khi giao diện thực sự cần bố cục riêng; cell mặc định dễ bảo trì và thích ứng với theme hơn.

## Kết hợp `InputView` và `ListView` để tìm kiếm rồi chọn

Một mẫu thường gặp là đặt ô lọc phía trên danh sách. Khi người dùng gõ, `InputViewTextChangeEvent` cập nhật tập item của `ListView`; khi người dùng nhấn Enter trên một kết quả, event mở item trả về đối tượng tương ứng.

Ví dụ tạo layout bằng `GridView`:

```java
import org.springframework.shell.component.view.control.GridView;
import org.springframework.shell.component.view.control.InputView;
import org.springframework.shell.component.view.control.ListView;

InputView filter = new InputView();
filter.setTitle("Tìm theo mã hoặc tên");

ListView<CustomerRow> results = new ListView<>(ListView.ItemStyle.RADIO);
results.setTitle("Kết quả");
results.setItems(customerRows);

GridView root = new GridView();
root.setRowSize(3, -1);
root.addItem(filter, 0, 0, 1, 1, 0, 0);
root.addItem(results, 1, 0, 1, 1, 0, 0);

ui.configure(root);
ui.setRoot(root, true);
ui.setFocus(filter);
```

Đăng ký lọc theo nội dung nhập:

```java
import java.util.List;
import java.util.Locale;

import reactor.core.Disposable;

Disposable filterChanges = ui.getEventLoop()
        .viewEvents(InputView.InputViewTextChangeEvent.class, filter)
        .subscribe(event -> {
            String query = event.args().newText()
                    .strip()
                    .toLowerCase(Locale.ROOT);

            List<CustomerRow> filtered = customerRows.stream()
                    .filter(customer -> customer.code()
                            .toLowerCase(Locale.ROOT).contains(query)
                            || customer.name()
                            .toLowerCase(Locale.ROOT).contains(query))
                    .toList();

            results.setItems(filtered);
            ui.redraw();
        });

ui.getEventLoop().onDestroy(filterChanges);
```

Trong màn hình có nhiều view, hãy quản lý focus rõ ràng. Ví dụ có thể dùng Tab để chuyển focus từ ô nhập sang danh sách và Backtab để quay lại:

```java
import org.springframework.shell.component.view.event.KeyEvent;

import reactor.core.Disposable;

Disposable focusNavigation = ui.getEventLoop().keyEvents()
        .subscribe(event -> {
            if (event.getPlainKey() == KeyEvent.Key.Tab) {
                ui.setFocus(results);
            }
            else if (event.getPlainKey() == KeyEvent.Key.Backtab) {
                ui.setFocus(filter);
            }
        });

ui.getEventLoop().onDestroy(focusNavigation);
```

Sau đó đăng ký event mở item của danh sách như ví dụ chọn khách hàng ở trên. Khi kết quả lọc thay đổi, danh sách có thể rỗng; hãy xử lý trường hợp đó bằng trạng thái “Không tìm thấy kết quả” hoặc một view thông báo riêng. Không để command giả định luôn có item đang hoạt động.

`GridView` chỉ bố trí các view. Nó không tự lọc dữ liệu và không tự xác nhận lựa chọn. Phần lọc, focus, event và kết quả cuối vẫn do ứng dụng phối hợp.

## Event loop và vòng đời subscription

`EventLoop` là nơi điều phối event trong vòng đời của một component hoặc giao diện. Những phương thức thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `keyEvents()` | Luồng sự kiện bàn phím |
| `mouseEvents()` | Luồng sự kiện chuột |
| `viewEvents(Class)` | Lọc các event view theo kiểu |
| `viewEvents(Class, View)` | Lọc event theo kiểu và view phát ra |
| `dispatch(Message)` | Gửi message vào event loop |
| `onDestroy(Disposable)` | Tự dispose subscription khi event loop kết thúc |

Một subscription tồn tại quá lâu có thể tiếp tục nhận event sau khi view không còn được sử dụng. Hãy đăng ký mọi `Disposable` với `onDestroy(...)` hoặc chủ động dispose trong cleanup. Với callback có truy vấn bất đồng bộ, cần tránh để kết quả cũ ghi đè kết quả mới khi người dùng đã gõ từ khóa khác.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `InputView` với `StringInput` | Mong chờ context và kết quả component cấp cao | Dùng `getInputText()` và event; tự quản lý xác nhận/validation |
| Không gọi `ui.configure(view)` | View thiếu event loop, theme hoặc view service | Cấu hình view trước khi gắn root và chạy UI |
| Không gọi `ui.setRoot(...)` | Terminal UI không có view gốc để vẽ | Đặt root view trước `run()` |
| Đọc `getInputText()` rồi coi là đã xác nhận | Dữ liệu có thể còn đang được chỉnh sửa | Chờ hành động xác nhận riêng |
| Nhầm `SelectedItemChangedEvent` với event mở item | Di chuyển con trỏ bị xem như chốt lựa chọn | Dùng event thay đổi cho preview, event open để xác nhận |
| Dùng `toString()` chứa quá nhiều trường | Dòng danh sách khó đọc hoặc lộ dữ liệu | Tạo `CellFactory` và chỉ hiển thị trường cần thiết |
| Không lọc event theo view | Callback xử lý nhầm event của view khác | Dùng `viewEvents(Event.class, view)` |
| Không gọi redraw sau khi thay danh sách | Nội dung mới có thể chưa được vẽ lại | Gọi `ui.redraw()` sau cập nhật state |
| Không quản lý focus | Người dùng gõ vào sai view hoặc không điều hướng được | Dùng `ui.setFocus(view)` và binding chuyển focus |
| Không dispose subscription | Listener còn sống sau khi giao diện đóng | Đăng ký với `EventLoop.onDestroy(...)` |
| Nạp quá nhiều item cùng lúc | Vẽ chậm và điều hướng khó khăn | Lọc/phân trang trước khi gọi `setItems(...)` |
| Xem `CHECKED` như dữ liệu nghiệp vụ đã được lưu | Trạng thái UI không đồng nghĩa dữ liệu đã commit | Đồng bộ với model ứng dụng và kiểm thử kết quả cuối |

## Kiểm thử `InputView` và `ListView`

Kiểm thử nên bao gồm cả hành vi nhập, điều hướng và kết quả được chọn:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Nhập văn bản | `getInputText()` trả nội dung hiện tại |
| Sửa giữa chuỗi | Left/Right/Backspace/Delete hoạt động đúng |
| Event thay đổi text | `oldText` và `newText` đúng |
| Danh sách rỗng | View không lỗi và giao diện có thông báo phù hợp |
| Di chuyển danh sách | Up/Down thay đổi item đang hoạt động |
| Mở item | Enter phát `ListViewOpenSelectedItemEvent` với đúng item |
| Item style `NOCHECK` | Không hiển thị dấu chọn |
| Item style `CHECKED` | Hiển thị trạng thái checked/unchecked |
| Item style `RADIO` | Hiển thị lựa chọn đơn |
| Lọc dữ liệu | `setItems(...)` nhận đúng danh sách theo query |
| Cell factory | Nội dung và trạng thái chọn được vẽ đúng |
| Focus | Tab/Backtab chuyển tới đúng view |
| Thoát UI | Interrupt kết thúc `ui.run()` và subscription được dispose |
| Terminal hẹp | Nội dung không làm vỡ bố cục hoặc che mất lựa chọn |

Có thể kiểm thử hàm lọc độc lập bằng unit test thông thường. Với phím, chuột, focus, event loop và render, nên dùng terminal test support của Spring Shell để mô phỏng tương tác. Unit test gọi `setItems()` không chứng minh người dùng có thể di chuyển và mở đúng item trong terminal thật.

## Quy trình xây dựng màn hình tìm kiếm và chọn dữ liệu

1. Xác định dữ liệu cần nhập hoặc lọc và chọn `InputView` cho chuỗi tìm kiếm.
2. Chọn kiểu dữ liệu item cho `ListView<T>`; cung cấp `toString()` ngắn hoặc `CellFactory` riêng.
3. Chọn `ItemStyle.NOCHECK`, `CHECKED` hoặc `RADIO` theo cách lựa chọn.
4. Bố trí các view bằng `GridView` hoặc một view container phù hợp.
5. Tạo `TerminalUI`, gọi `configure(...)`, `setRoot(...)` và đặt focus ban đầu.
6. Theo dõi `InputViewTextChangeEvent` để lọc và cập nhật `ListView.setItems(...)`.
7. Dùng `ListViewSelectedItemChangedEvent` cho preview và `ListViewOpenSelectedItemEvent` để chốt mục.
8. Quản lý focus, interrupt và subscription trong vòng đời event loop.
9. Kiểm thử danh sách rỗng, dữ liệu lớn, terminal hẹp và trường hợp người dùng thoát mà không chọn.

`InputView` và `ListView` tạo nền tảng cho các màn hình terminal có tìm kiếm và lựa chọn dữ liệu. Khi xử lý event đúng vai trò, quản lý focus và lưu kết quả qua model ứng dụng, người dùng có thể lọc danh sách và chọn mục bằng bàn phím hoặc chuột mà command vẫn giữ được luồng xử lý rõ ràng.

## Tài liệu tham khảo

- [Terminal UI – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/tui/index.html)
- [Views – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/tui/views/index.html)
- [InputView – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/tui/views/input.html)
- [ListView – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/tui/views/list.html)
- [InputView API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/InputView.html)
- [InputViewTextChangeEventArgs API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/InputView.InputViewTextChangeEventArgs.html)
- [ListView API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ListView.html)
- [ListView.ItemStyle API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ListView.ItemStyle.html)
- [ListViewOpenSelectedItemEvent API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ListView.ListViewOpenSelectedItemEvent.html)
- [ListViewSelectedItemChangedEvent API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ListView.ListViewSelectedItemChangedEvent.html)
- [GridView API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/GridView.html)
- [TerminalUI API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUI.html)
- [TerminalUIBuilder API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUIBuilder.html)
- [EventLoop API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.html)
- [ShellMessageBuilder API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/message/ShellMessageBuilder.html)
- [AbstractListCell API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/cell/AbstractListCell.html)
