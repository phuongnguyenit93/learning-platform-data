# ProgressView, StatusBarView và trạng thái tác vụ

Một giao diện terminal hữu ích cần cho người dùng biết tác vụ đang làm gì, đã hoàn thành đến đâu và ứng dụng hiện ở trạng thái nào. Spring Shell 3.x cung cấp `ProgressView` để hiển thị tiến độ và `StatusBarView` để hiển thị các mục trạng thái theo chiều ngang.

Hai view này có mục đích khác nhau. `ProgressView` thay đổi theo tiến trình của một tác vụ; `StatusBarView` thường nằm ở cuối giao diện và hiển thị thông tin chung như môi trường, kết nối, trạng thái phiên hoặc phím tắt. Trạng thái nghiệp vụ của tác vụ vẫn cần được quản lý ở service hoặc task model; view chỉ phản ánh trạng thái đó cho người dùng.

Bài này sử dụng API Spring Shell 3.3.x, thuộc các package `org.springframework.shell.component.view.control` và `org.springframework.shell.component.view.event`.

## 1. Phân biệt tiến độ tác vụ và trạng thái ứng dụng

Tiến độ cho biết một công việc đang tiến triển đến đâu. Trạng thái ứng dụng cho biết môi trường hoặc phiên hiện tại đang ở điều kiện nào. Không nên gộp mọi thông tin vào một progress bar.

| Thông tin | Ví dụ | View phù hợp |
|---|---|---|
| Tiến độ của một tác vụ | Đã nhập 70/100 file | `ProgressView` |
| Giai đoạn đang chạy | Đang kiểm tra dữ liệu | `ProgressView` với mô tả hoặc text item |
| Trạng thái môi trường | `ENV: staging` | `StatusBarView` |
| Kết nối hiện tại | `DB: connected` | `StatusBarView` |
| Tác vụ hiện tại | `IMPORT: running` | `StatusBarView` |
| Phím tắt trợ giúp | `F1: Help` | `StatusBarView.StatusItem` có action và hotkey |

Ví dụ một màn hình terminal:

```text
┌──────────────────────────────────────────────────────────┐
│                    IMPORT USERS                           │
├──────────────────────────────────────────────────────────┤
│ Đang nhập dữ liệu từ users.csv                            │
│ [==============================------] 75%                │
│ Đã xử lý 750 / 1000 bản ghi                               │
├──────────────────────────────────────────────────────────┤
│ ENV: staging | DB: connected | TASK: running | F1: Help   │
└──────────────────────────────────────────────────────────┘
```

`ProgressView` biểu diễn phần tiến độ ở vùng nội dung. `StatusBarView` hiển thị các mục trạng thái ở cạnh dưới. Khi tác vụ hoàn tất, progress view có thể dừng, còn status bar vẫn giữ thông tin môi trường và phiên.

## 2. `ProgressView` hoạt động như thế nào?

`ProgressView` là một `BoxView` chuyên hiển thị thông tin tiến độ. Nó sử dụng `ProgressState` để giữ trạng thái runtime, gồm:

- `tickStart`: giá trị tick bắt đầu.
- `tickEnd`: giá trị tick kết thúc.
- `tickValue`: tick hiện tại.
- `running`: tác vụ/progress đang chạy hay đã dừng.
- `startTime`: thời điểm bắt đầu, tính bằng milliseconds.
- `updateTime`: thời điểm cập nhật gần nhất, tính bằng milliseconds.

`ProgressView` có ba item dựng sẵn:

- `text`: hiển thị mô tả tiến độ.
- `spinner`: hiển thị dấu hiệu tác vụ đang hoạt động.
- `percent`: hiển thị tỷ lệ hoàn thành.

Constructor mặc định tạo khoảng tick từ `0` đến `100` và sử dụng các item mặc định. Có thể khởi chạy runtime logic bằng `start()` và dừng bằng `stop()`.

```java
import org.springframework.shell.component.view.control.ProgressView;

ProgressView progressView = new ProgressView();
progressView.setDescription("Đang đồng bộ dữ liệu...");
progressView.start();
```

Gọi `start()` trên một progress view đã chạy không khởi động thêm một runtime logic khác. Gọi `stop()` để dừng runtime logic khi tác vụ kết thúc hoặc không còn cần hiển thị trạng thái chạy.

## 3. Cập nhật giá trị tiến độ

Hai phương thức cập nhật tick thường dùng:

- `setTickValue(value)`: đặt tick hiện tại thành một giá trị cụ thể.
- `tickAdvance(count)`: tăng hoặc giảm tick hiện tại theo số lượng được truyền vào.

`setTickValue()` giữ giá trị trong giới hạn của progress view. Nếu giá trị nhỏ hơn `tickStart`, nó được đưa về cận dưới; nếu lớn hơn `tickEnd`, nó được đưa về cận trên. `tickAdvance()` chấp nhận cả số âm để lùi tiến độ.

Ví dụ với một tác vụ có tổng cộng 200 bước:

```java
import org.springframework.shell.component.view.control.ProgressView;

ProgressView progressView = new ProgressView();
progressView.setDescription("Đang xử lý bản ghi...");
progressView.start();

int completed = 80;
int total = 200;
int percent = (int) (completed * 100L / total);

progressView.setTickValue(percent);
```

Khi `completed` bằng `80`, tick được đặt thành `40`. Nếu mỗi lần xử lý hoàn tất một bước, có thể dùng `tickAdvance(1)` thay vì tự tính tỷ lệ, miễn là tick range tương ứng với số bước thực tế.

Đừng dùng phần trăm nếu không biết tổng số công việc. Một tiến độ giả như `80%` rồi đứng yên vô thời hạn gây hiểu nhầm. Với tác vụ không biết tổng, dùng text và spinner mà không hiển thị phần trăm.

## 4. Tùy chỉnh các item của ProgressView

Có thể chỉ định các item và cách căn chỉnh bằng `ProgressViewItem`. Các factory dựng sẵn gồm `ofText(...)`, `ofSpinner(...)` và `ofPercent(...)`.

Ví dụ progress view có mô tả, spinner và phần trăm:

```java
import org.springframework.shell.component.view.control.ProgressView;
import org.springframework.shell.component.view.control.ProgressView.ProgressViewItem;
import org.springframework.shell.geom.HorizontalAlign;

ProgressView progressView = new ProgressView(
        ProgressViewItem.ofText(24, HorizontalAlign.LEFT),
        ProgressViewItem.ofSpinner(3, HorizontalAlign.LEFT),
        ProgressViewItem.ofPercent(6, HorizontalAlign.RIGHT));

progressView.setDescription("Đang tải artifact...");
progressView.start();
```

Trong ví dụ, mô tả và spinner được căn trái; phần trăm được căn phải. Các tham số size giúp phân bổ không gian cho item khi view được vẽ.

Với tác vụ không biết tổng số bước, có thể bỏ item phần trăm:

```java
import org.springframework.shell.component.view.control.ProgressView;
import org.springframework.shell.component.view.control.ProgressView.ProgressViewItem;
import org.springframework.shell.geom.HorizontalAlign;

ProgressView progressView = new ProgressView(
        ProgressViewItem.ofText(28, HorizontalAlign.LEFT),
        ProgressViewItem.ofSpinner(3, HorizontalAlign.LEFT));

progressView.setDescription("Đang chờ dịch vụ phản hồi...");
progressView.start();
```

Spinner thể hiện công việc còn hoạt động; text mô tả bước hiện tại. Không cần hiển thị một phần trăm ước lượng nếu không có cơ sở đáng tin cậy.

## 5. Mô hình hóa trạng thái tác vụ riêng với ProgressView

`ProgressView` là thành phần trình bày. Nó không thay thế task model hoặc trạng thái nghiệp vụ của service. Hãy lưu trạng thái tác vụ bằng một enum và snapshot riêng.

```java
enum TaskState {
    QUEUED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCELLED
}

record TaskProgress(
        String taskId,
        TaskState state,
        long completed,
        long total,
        String description) {

    int percent() {
        if (total <= 0) {
            return -1;
        }
        return (int) Math.min(100, completed * 100L / total);
    }
}
```

Quy ước `percent() == -1` nghĩa là chưa xác định được tổng số bước. Các trạng thái có ý nghĩa riêng:

| Trạng thái | Ý nghĩa | Hiển thị gợi ý |
|---|---|---|
| `QUEUED` | Đang chờ worker xử lý | `Đang chờ...` |
| `RUNNING` | Đang thực thi | Spinner và tiến độ nếu biết tổng |
| `SUCCEEDED` | Đã hoàn tất thành công | `Hoàn tất` và 100% nếu có tổng xác định |
| `FAILED` | Tác vụ thất bại | `Thất bại` cùng thông báo an toàn |
| `CANCELLED` | Tác vụ đã được hủy | `Đã hủy` và số bước đã xử lý |

Luồng trạng thái thường gặp:

```text
QUEUED ──> RUNNING ──> SUCCEEDED
                  ├──> FAILED
                  └──> CANCELLED
```

Chỉ worker hoặc service sở hữu tác vụ mới nên quyết định chuyển trạng thái. View nhận snapshot và render nó. Điều này giúp command khác, log và kiểm thử cùng nhìn thấy một trạng thái thống nhất.

## 6. Tách tác vụ chạy nền khỏi vòng lặp giao diện

Không chạy một tác vụ dài đồng bộ ngay trong luồng đang xử lý terminal UI. Nếu luồng giao diện bị chặn bởi đọc file, upload hoặc truy vấn database kéo dài, event loop không có cơ hội xử lý input và cập nhật màn hình đúng nhịp.

Kiến trúc nên tách ba phần:

1. **Worker/service:** thực hiện công việc và phát snapshot tiến độ.
2. **EventLoop:** nhận message và điều phối cập nhật trạng thái/redraw.
3. **View:** nhận snapshot và cập nhật `ProgressView` hoặc `StatusBarView`.

Spring Shell 3.x có `EventLoop` để điều phối event trong vòng đời component. API cung cấp `dispatch(Message<?>)`, `dispatch(Publisher<Message<?>>)` và `events()`. `EventLoop` cũng cung cấp `onDestroy(Disposable)` để giải phóng subscription khi event loop kết thúc.

## 7. Gửi snapshot tiến độ qua EventLoop

Worker có thể gửi một `TaskProgress` vào event loop dưới dạng Spring `Message`. Dùng `MessageBuilder` để tạo message:

```java
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.shell.component.view.event.EventLoop;

void publishProgress(EventLoop eventLoop, TaskProgress progress) {
    eventLoop.dispatch(MessageBuilder.withPayload(progress).build());
}
```

Worker gọi `publishProgress(...)` sau khi có thay đổi có ý nghĩa, ví dụ sau mỗi file được xử lý hoặc sau một batch. Không cần phát message cho từng byte hoặc từng vòng lặp nhỏ nếu điều đó khiến giao diện phải redraw quá thường xuyên.

Một view kế thừa `ProgressView` có thể lắng nghe các message `TaskProgress` và cập nhật nội dung:

```java
import org.springframework.messaging.Message;
import org.springframework.shell.component.view.control.ProgressView;
import org.springframework.shell.component.view.event.EventLoop;
import reactor.core.Disposable;

class TaskProgressView extends ProgressView {

    private final String taskId;

    TaskProgressView(String taskId) {
        this.taskId = taskId;
    }

    void bind(EventLoop eventLoop) {
        Disposable subscription = eventLoop.events()
                .map(Message::getPayload)
                .ofType(TaskProgress.class)
                .filter(progress -> taskId.equals(progress.taskId()))
                .subscribe(this::applyProgress);

        onDestroy(subscription);
    }

    private void applyProgress(TaskProgress progress) {
        setDescription(progress.description());

        if (progress.total() > 0) {
            setTickValue(progress.percent());
        }

        if (progress.state() == TaskState.RUNNING) {
            start();
        }
        else {
            stop();
        }
    }
}
```

Các điểm quan trọng:

- `taskId` lọc message để view không nhận tiến độ của tác vụ khác.
- `ProgressView` chỉ được cập nhật khi view nhận snapshot từ event loop.
- `onDestroy(subscription)` đăng ký cleanup để subscription không tiếp tục tồn tại sau vòng đời view.
- Khi trạng thái không còn `RUNNING`, gọi `stop()` để dừng runtime logic của progress view.

`EventLoop` là điểm điều phối event; cách triển khai cụ thể quyết định cách message được xử lý. Hãy gửi update qua event loop của UI thay vì để worker tùy ý ghi trực tiếp vào cấu trúc màn hình. Nếu ứng dụng có nhiều view hoặc nhiều task, mỗi view cần lọc theo task ID hoặc loại message phù hợp.

## 8. Ví dụ worker phát tiến độ theo từng file

Một tác vụ nhập dữ liệu từ nhiều file có tổng số bước xác định. Worker có thể phát trạng thái `QUEUED`, `RUNNING`, rồi trạng thái kết thúc:

```java
import java.util.concurrent.Executor;
import java.nio.file.Path;
import java.util.List;

import org.slf4j.Logger;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.shell.component.view.event.EventLoop;

class ImportWorker {

    private final Executor executor;
    private final Logger log;

    ImportWorker(Executor executor, Logger log) {
        this.executor = executor;
        this.log = log;
    }

    void submit(
            String taskId,
            List<Path> files,
            EventLoop eventLoop,
            ImportService importService) {

        publish(eventLoop, new TaskProgress(
                taskId, TaskState.QUEUED, 0, files.size(), "Đang chờ nhập dữ liệu"));

        executor.execute(() -> {
            long completed = 0;
            try {
                publish(eventLoop, new TaskProgress(
                        taskId, TaskState.RUNNING, completed, files.size(), "Bắt đầu nhập dữ liệu"));

                for (Path file : files) {
                    importService.importFile(file);
                    completed++;
                    publish(eventLoop, new TaskProgress(
                            taskId,
                            TaskState.RUNNING,
                            completed,
                            files.size(),
                            "Đã xử lý " + completed + "/" + files.size() + " file"));
                }

                publish(eventLoop, new TaskProgress(
                        taskId, TaskState.SUCCEEDED, completed, files.size(), "Nhập dữ liệu hoàn tất"));
            }
            catch (Exception exception) {
                log.error("Import task failed. taskId={}", taskId, exception);
                publish(eventLoop, new TaskProgress(
                        taskId,
                        TaskState.FAILED,
                        completed,
                        files.size(),
                        "Không thể nhập dữ liệu. Mã tác vụ: " + taskId));
            }
        });
    }

    private void publish(EventLoop eventLoop, TaskProgress progress) {
        eventLoop.dispatch(MessageBuilder.withPayload(progress).build());
    }
}
```

`executor`, `log` và `ImportService` trong ví dụ là dependency của worker. Executor nên được quản lý bởi Spring hoặc một thành phần sở hữu rõ ràng; không tạo thread mới cho từng lần cập nhật progress. Worker ghi log exception để chẩn đoán, còn view chỉ hiển thị thông báo an toàn.

Với danh sách rỗng, không chia cho `files.size()` để tính phần trăm. Hãy xử lý trường hợp không có file trước khi chạy worker, hoặc trả kết quả hoàn tất với tổng bằng `0` theo quy ước riêng.

## 9. Progress indeterminate khi chưa biết tổng công việc

Không phải tác vụ nào cũng biết tổng số bước. Ví dụ chờ server phản hồi, đồng bộ một stream hoặc chờ một tác vụ từ xa. Khi đó, dùng text và spinner mà không hiển thị phần trăm.

```java
import org.springframework.shell.component.view.control.ProgressView;
import org.springframework.shell.component.view.control.ProgressView.ProgressViewItem;
import org.springframework.shell.geom.HorizontalAlign;

ProgressView progressView = new ProgressView(
        ProgressViewItem.ofText(32, HorizontalAlign.LEFT),
        ProgressViewItem.ofSpinner(3, HorizontalAlign.LEFT));

progressView.setDescription("Đang chờ máy chủ xử lý...");
progressView.start();
```

Khi nhận kết quả cuối cùng, dừng spinner và cập nhật mô tả thành công hoặc thất bại. Nếu sau đó xác định được tổng số bước, có thể chuyển sang một progress view có item phần trăm hoặc dùng một view mới phù hợp với loại tác vụ.

## 10. Theo dõi thời gian và sự kiện của ProgressView

`ProgressView.getState()` trả về `ProgressState` hiện tại. Record này chứa `startTime` và `updateTime` tính bằng milliseconds, ngoài các giá trị tick và cờ `running`.

Progress view cũng phát các event:

- `ProgressViewStartEvent`: tiến trình theo dõi bắt đầu.
- `ProgressViewStateChangeEvent`: trạng thái tiến độ thay đổi.
- `ProgressViewEndEvent`: tiến trình theo dõi kết thúc.

Các event này hữu ích khi một view khác cần phản ứng với thay đổi tiến độ, ví dụ cập nhật nội dung phụ hoặc ghi nhận thời điểm kết thúc. Có thể dùng `EventLoop.viewEvents(...)` để nhận event có kiểu và lọc theo view.

Không nên lấy `updateTime` làm thời gian hoàn tất nghiệp vụ. Đây là thời điểm cập nhật progress view gần nhất. Thời điểm bắt đầu/kết thúc chính thức nên được task service lưu trong task model hoặc audit record.

## 11. `StatusBarView` hiển thị trạng thái chung

`StatusBarView` kế thừa `BoxView` và hiển thị các `StatusItem` theo chiều ngang. Mỗi item có tiêu đề; item cũng có thể có `Runnable` action và hotkey.

Ví dụ:

```java
import java.util.List;

import org.springframework.shell.component.view.control.StatusBarView;
import org.springframework.shell.component.view.event.KeyEvent;

StatusBarView statusBar = new StatusBarView(List.of(
        StatusBarView.StatusItem.of("ENV: staging"),
        StatusBarView.StatusItem.of("DB: connected"),
        StatusBarView.StatusItem.of("TASK: idle"),
        StatusBarView.StatusItem.of("F1: Help", this::showHelp, KeyEvent.Key.f1)
));
```

Trong ví dụ, ba item đầu chỉ hiển thị trạng thái. Item cuối gọi `showHelp()` khi được chọn và gắn phím F1. Action của item là `Runnable`, còn hotkey được truyền dưới dạng integer từ `KeyEvent.Key`.

`StatusBarView` phát `StatusBarViewOpenSelectedItemEvent` khi một item được yêu cầu mở. Event có `args().item()` để lấy `StatusItem` tương ứng. Nếu chỉ cần thực hiện thao tác đơn giản, gắn `Runnable` trực tiếp vào item thường là đủ.

## 12. Cập nhật StatusBarView khi trạng thái thay đổi

Tiêu đề của `StatusItem` được cung cấp khi tạo item. Khi trạng thái thay đổi, tạo danh sách item mới rồi gọi `setItems(...)`:

```java
void refreshStatusBar(
        StatusBarView statusBar,
        String environment,
        boolean databaseConnected,
        TaskState taskState) {

    statusBar.setItems(List.of(
            StatusBarView.StatusItem.of("ENV: " + environment),
            StatusBarView.StatusItem.of(
                    "DB: " + (databaseConnected ? "connected" : "disconnected")),
            StatusBarView.StatusItem.of("TASK: " + taskState),
            StatusBarView.StatusItem.of("F1: Help", this::showHelp, KeyEvent.Key.f1)
    ));
}
```

Gọi cập nhật status bar trên luồng điều phối UI hoặc thông qua event loop. Tránh để worker nền cập nhật view trực tiếp trong lúc terminal đang vẽ. Cũng không nên tạo lại status bar ở mỗi tick tiến độ; chỉ cập nhật khi một trạng thái chung thực sự thay đổi.

## 13. Ghép StatusBarView vào AppView

`AppView` là một bố cục terminal cấp ứng dụng, quản lý vùng nội dung chính, menu bar, status bar và hệ thống modal. Constructor nhận ba view: `main`, `menuBar` và `statusBar`.

```java
import org.springframework.shell.component.view.control.AppView;
import org.springframework.shell.component.view.control.StatusBarView;

StatusBarView statusBar = new StatusBarView();

// mainView và menuBarView đã được tạo bằng các view phù hợp với ứng dụng.
AppView appView = new AppView(mainView, menuBarView, statusBar);
appView.setStatusBarVisible(true);
```

`mainView` có thể là view nội dung như `GridView`, `BoxView` hoặc một view nghiệp vụ khác. Có thể gọi `setStatusBarVisible(false)` để ẩn status bar, hoặc `toggleStatusBarVisibility()` để đảo trạng thái hiển thị.

AppView xử lý hotkey theo thứ tự main view, menu bar rồi status bar. Vì vậy, hãy tránh gán cùng một phím cho các thao tác có ý nghĩa khác nhau ở nhiều vùng giao diện.

## 14. Thiết kế trạng thái cho tác vụ thành công, lỗi và hủy

Không nên để progress bar là nguồn duy nhất xác định tác vụ thành công. Một task có thể đã xử lý 100% số phần tử nhưng vẫn thất bại ở bước commit cuối. Ngược lại, tác vụ có thể bị hủy khi mới hoàn thành một phần.

Hãy giữ task state riêng:

| Trường hợp | Progress | Task state | Status bar |
|---|---|---|---|
| Đang chạy | Tăng theo công việc hoàn tất | `RUNNING` | `TASK: running` |
| Hoàn tất | 100% nếu có tổng xác định | `SUCCEEDED` | `TASK: succeeded` |
| Lỗi giữa chừng | Giữ tỷ lệ thực tế | `FAILED` | `TASK: failed` |
| Người dùng hủy | Giữ số bước đã xử lý | `CANCELLED` | `TASK: cancelled` |
| Chờ worker | Chưa có phần trăm | `QUEUED` | `TASK: queued` |

Nếu bước cuối còn thực hiện kiểm tra hoặc commit, chỉ đánh dấu `SUCCEEDED` sau khi bước đó thành công. Đừng đặt tick 100 chỉ vì vòng lặp xử lý dữ liệu đã kết thúc nếu công việc nghiệp vụ chưa hoàn tất.

Khi tác vụ thất bại, progress view có thể dừng spinner và hiển thị thông báo ngắn. Chi tiết exception và stack trace nên được ghi vào log. Status bar có thể giữ trạng thái `TASK: failed` cho đến khi người dùng đóng thông báo hoặc khởi chạy tác vụ mới.

## 15. Nhiều tác vụ đồng thời và cập nhật quá thường xuyên

Một `ProgressView` thường biểu diễn một tác vụ hoặc một giai đoạn chính. Nếu ứng dụng chạy nhiều tác vụ song song, hãy chọn một trong các cách:

- Hiển thị tiến độ của tác vụ đang được chọn; status bar cho biết số tác vụ còn lại.
- Dùng danh sách hoặc bảng để hiển thị nhiều task snapshot, mỗi dòng có trạng thái riêng.
- Mở một view chi tiết cho task được chọn, trong đó `ProgressView` hiển thị tiến độ của task đó.

Mỗi task cần ID riêng để message không cập nhật nhầm progress view. Nếu worker phát quá nhiều update, có thể gộp theo batch hoặc chỉ phát khi phần trăm thay đổi. Điều này giảm lượng message và số lần redraw mà vẫn giữ thông tin đủ hữu ích.

Không giả định `ProgressView` tự quản lý một hàng đợi nhiều tác vụ hoặc tự đồng bộ các worker. Task registry, concurrency limit và trạng thái mỗi task thuộc trách nhiệm của ứng dụng.

## 16. Vòng đời view và giải phóng tài nguyên

View có thể đăng ký subscription để nhận message từ `EventLoop`. Khi view không còn được dùng, subscription cần được dispose để tránh giữ reference tới view hoặc tiếp tục xử lý event.

`AbstractView.onDestroy(Disposable)` đăng ký một subscription để dispose khi view bị hủy. `AbstractView.destroy()` dọn running state của view để view có thể được garbage collect.

Với tác vụ có executor:

- Executor thuộc application/service nên được quản lý theo lifecycle của bean sở hữu nó.
- Không đóng executor dùng chung chỉ vì một progress view kết thúc.
- Khi command bị hủy, truyền cancellation signal tới worker nếu nghiệp vụ hỗ trợ.
- Khi task kết thúc, phát trạng thái terminal (`SUCCEEDED`, `FAILED` hoặc `CANCELLED`) rồi dừng progress runtime logic.
- Khi view đóng, dispose subscription và không để message cũ cập nhật một view mới.

Nếu task phải tiếp tục chạy sau khi người dùng rời view, task service cần tồn tại độc lập với view. View mới có thể lấy task snapshot hiện tại từ task registry rồi tiếp tục hiển thị.

## 17. Kiểm thử ProgressView và StatusBarView

Kiểm thử nên bao gồm cả dữ liệu tiến độ và vòng đời giao diện:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Progress mặc định | Tick range là 0–100 và có text, spinner, percent |
| `setTickValue(-1)` | Giá trị bị clamp về cận dưới |
| `setTickValue(150)` | Giá trị bị clamp về cận trên |
| `tickAdvance()` | Tick thay đổi theo count, kể cả count âm |
| `start()` và `stop()` | Runtime logic bắt đầu và dừng đúng lúc |
| Không biết tổng số bước | Dùng text/spinner, không hiển thị phần trăm giả |
| Worker gửi snapshot | View chỉ nhận message đúng task ID |
| Task thành công | Task state là `SUCCEEDED` và progress hoàn tất theo quy ước |
| Task thất bại | Giữ tiến độ thực tế, hiển thị lỗi an toàn và dừng spinner |
| Task bị hủy | Trạng thái là `CANCELLED`, không giả thành công |
| Chọn StatusItem | Runnable được thực thi đúng |
| Hotkey F1 | Action trợ giúp được gọi |
| View bị destroy | Subscription được dispose |

Unit test cho task model nên kiểm tra chuyển trạng thái và phần trăm. Integration test với terminal test harness có thể kiểm tra phím, status bar action và nội dung view. Không chỉ kiểm tra ảnh terminal; hãy xác nhận task service không bị đánh dấu thành công khi worker ném exception.

## 18. Bài tập thực hành

Xây dựng màn hình nhập dữ liệu gồm `ProgressView` ở vùng nội dung và `StatusBarView` ở cuối ứng dụng.

Yêu cầu:

1. Tác vụ nhập 100 file chạy trong executor nền.
2. Mỗi file hoàn tất phát một `TaskProgress` snapshot có task ID, completed, total, state và description.
3. `ProgressView` hiển thị spinner, mô tả và phần trăm theo số file đã nhập.
4. `StatusBarView` hiển thị môi trường, trạng thái database, trạng thái task và phím F1 trợ giúp.
5. Khi tác vụ thành công, status bar chuyển sang `TASK: succeeded`.
6. Khi một file lỗi, status bar chuyển sang `TASK: failed`; log giữ exception đầy đủ.
7. Thêm lựa chọn hủy và bảo đảm worker nhận cancellation signal.
8. Khi đóng view, subscription được dispose; task service vẫn quản lý tác vụ theo chính sách đã chọn.
9. Thử trường hợp không biết tổng số công việc và dùng progress view chỉ có text/spinner.
10. Kiểm thử nhiều task ID để không cập nhật nhầm view.

**Kết quả cần nộp:** task model, worker/service, `ProgressView`, `StatusBarView`, cấu hình `AppView`, sơ đồ trạng thái và kết quả kiểm thử thành công/lỗi/hủy.

## 19. Checklist trước khi phát hành giao diện tiến độ

- [ ] `ProgressView` chỉ phản ánh tiến độ của task model.
- [ ] Task state được quản lý độc lập với view.
- [ ] Tổng số bước được xác định trước khi hiển thị phần trăm.
- [ ] Tác vụ không xác định tổng dùng text/spinner.
- [ ] `setTickValue()` và `tickAdvance()` được dùng trong đúng tick range.
- [ ] Worker chạy nền và không chặn event loop.
- [ ] Progress update được gửi qua event loop của UI.
- [ ] Message được lọc theo task ID.
- [ ] `StatusBarView` chỉ hiển thị trạng thái chung và phím tắt cần thiết.
- [ ] Status item action/hotkey được kiểm thử.
- [ ] Task chỉ chuyển sang `SUCCEEDED` sau khi nghiệp vụ hoàn tất.
- [ ] Lỗi và hủy có trạng thái riêng.
- [ ] Subscription được dispose khi view bị destroy.
- [ ] Executor được đóng bởi thành phần sở hữu nó.
- [ ] Đã kiểm thử task chạy lâu, nhiều task và trường hợp lỗi.

## Tài liệu tham khảo

- [Spring Shell 3.3 API — `ProgressView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/ProgressView.html)
- [Spring Shell 3.3 API — `ProgressView.ProgressState`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/ProgressView.ProgressState.html)
- [Spring Shell 3.3 API — `ProgressView.ProgressViewItem`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/ProgressView.ProgressViewItem.html)
- [Spring Shell 3.3 API — `ProgressView.ProgressViewStateChangeEvent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/ProgressView.ProgressViewStateChangeEvent.html)
- [Spring Shell 3.3 API — `StatusBarView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/StatusBarView.html)
- [Spring Shell 3.3 API — `StatusBarView.StatusItem`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/StatusBarView.StatusItem.html)
- [Spring Shell 3.3 API — `StatusBarViewOpenSelectedItemEvent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/StatusBarView.StatusBarViewOpenSelectedItemEvent.html)
- [Spring Shell 3.3 API — `AppView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AppView.html)
- [Spring Shell 3.3 API — `EventLoop`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html)
- [Spring Shell 3.3 API — `AbstractView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AbstractView.html)
- [Spring Shell 3.3 API — `KeyEvent.Key`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/KeyEvent.Key.html)
