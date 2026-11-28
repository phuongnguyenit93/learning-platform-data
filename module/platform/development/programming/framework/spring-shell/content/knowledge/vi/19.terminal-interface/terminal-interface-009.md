# Thông báo tiến trình và cập nhật màn hình có kiểm soát

Command có thể phải đọc hàng nghìn bản ghi, tải file lớn, đồng bộ dữ liệu hoặc chờ dịch vụ bên ngoài. Nếu không có thông tin trong lúc xử lý, người dùng khó biết ứng dụng còn hoạt động hay đã bị treo. Nếu command in một dòng cho mỗi bước nhỏ, terminal lại nhanh chóng đầy nội dung và khó theo dõi kết quả.

Spring Shell có thể trình bày tiến trình theo nhiều cách. Với tác vụ đơn giản, command cập nhật một dòng trạng thái bằng `PrintWriter`. Với giao diện terminal tương tác, Terminal UI cung cấp `ProgressView`, spinner và event để hiển thị phần trăm cùng trạng thái xử lý. Dù chọn cách nào, command nên cập nhật theo nhịp có kiểm soát và kết thúc bằng một thông báo rõ ràng.

## Chọn cách thông báo theo môi trường chạy

Trước khi tạo progress indicator, hãy xác định command đang chạy trong terminal tương tác hay được gọi từ script/CI.

| Môi trường | Cách hiển thị phù hợp | Lý do |
| --- | --- | --- |
| Interactive terminal, tác vụ đơn giản | Cập nhật một dòng bằng `\r` và `flush()` | Người dùng thấy tiến trình mà không tạo nhiều dòng output |
| Interactive terminal, tác vụ dài hoặc có nhiều bước | `ProgressView` trong Terminal UI | Có spinner, mô tả và phần trăm; màn hình được quản lý theo view |
| Script, CI hoặc output được chuyển hướng | In các mốc tiến trình thưa hoặc chỉ in kết quả cuối | Tránh ký tự điều khiển làm log khó đọc |
| Không biết trước tổng số bước | Spinner hoặc trạng thái “đang xử lý” | Không hiển thị phần trăm thiếu căn cứ |

Tiến trình nên phản ánh công việc thực tế đã hoàn thành. Nếu mỗi bản ghi có chi phí xử lý rất khác nhau, phần trăm dựa trên số bản ghi chỉ là ước lượng. Khi đó, hãy hiển thị tên giai đoạn hoặc số lượng đã xử lý thay vì tạo cảm giác phần trăm chính xác tuyệt đối.

## Cập nhật một dòng bằng `PrintWriter`

Với command không cần giao diện toàn màn hình, có thể ghi lại trên cùng một dòng bằng ký tự carriage return `\r`. Ký tự này đưa con trỏ về đầu dòng hiện tại; `flush()` đẩy nội dung đang đệm ra terminal để người dùng nhìn thấy ngay.

Ví dụ helper cập nhật theo phần trăm:

```java
import java.io.PrintWriter;

public final class LineProgressReporter {

    private final PrintWriter writer;
    private final int total;
    private int lastPercent = -5;

    public LineProgressReporter(PrintWriter writer, int total) {
        if (total <= 0) {
            throw new IllegalArgumentException("total phải lớn hơn 0");
        }
        this.writer = writer;
        this.total = total;
    }

    public void update(int completed) {
        int bounded = Math.max(0, Math.min(completed, total));
        int percent = (int) ((long) bounded * 100 / total);

        // Chỉ cập nhật khi tăng ít nhất 5 điểm phần trăm hoặc đã hoàn tất.
        if (percent != 100 && percent - lastPercent < 5) {
            return;
        }

        writer.printf("\rĐang xử lý: %3d%% (%d/%d)",
                percent, bounded, total);
        writer.flush();
        lastPercent = percent;
    }

    public void finish() {
        writer.println();
        writer.flush();
    }
}
```

Helper giới hạn số lần cập nhật bằng cách chỉ ghi khi phần trăm tăng ít nhất 5 điểm hoặc đã hoàn tất. Với tổng 10.000 bản ghi, terminal không phải vẽ lại 10.000 lần. `finish()` xuống dòng trước khi result handler in kết quả cuối, tránh để thông báo hoàn thành nối vào dòng tiến trình.

### Lấy writer theo phiên bản Spring Shell

API context cung cấp writer khác nhau giữa hai major version:

```java
// Spring Shell 3.4.x: lấy writer từ CommandContext trong target programmatic.
PrintWriter writer = context.getTerminal().writer();

// Spring Shell 4.x
PrintWriter writer = context.outputWriter();
```

Truyền writer vào helper rồi cập nhật theo số lượng thực tế:

```java
import java.util.List;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Command(name = "data import", description = "Nhập dữ liệu từ nguồn")
public String importData(CommandContext context) {
    List<ImportRecord> records = importService.loadPendingRecords();

    if (records.isEmpty()) {
        return "Không có dữ liệu cần nhập.";
    }

    LineProgressReporter progress =
            new LineProgressReporter(context.outputWriter(), records.size());

    int completed = 0;
    try {
        for (ImportRecord record : records) {
            importService.importOne(record);
            progress.update(++completed);
        }
    }
    finally {
        progress.finish();
    }

    return "Đã nhập " + completed + " bản ghi.";
}
```

Đoạn ví dụ trên dùng `CommandContext` của Spring Shell 4.x. Trong 3.4.x, `getTerminal().writer()` có sẵn trên `CommandContext` của target programmatic; hãy dùng đúng kiểu đăng ký command và import của phiên bản đó. Helper chỉ xuống dòng và flush khi kết thúc, còn thông báo cuối do command trả về để result handler hiển thị một lần.

### Không cập nhật quá dày

Không nên ghi một dòng cho mỗi vòng lặp nếu công việc có thể chạy hàng nghìn lần mỗi giây. Các quy tắc thực tế:

- Với tác vụ có tổng số bước, cập nhật mỗi 1–5% hoặc sau một số lượng bản ghi cố định.
- Với tác vụ có thời gian xử lý dài nhưng không biết tổng số bước, cập nhật trạng thái theo mốc thời gian, chẳng hạn mỗi nửa giây.
- Luôn cập nhật mốc hoàn tất, kể cả khi lần cập nhật trước chưa đạt ngưỡng.
- Gọi `flush()` sau khi ghi một trạng thái cần hiển thị ngay; không cần flush cho từng log chi tiết.
- Sau khi dùng `\r`, ghi `\n` trước khi in thông báo tiếp theo.

Nếu output được chuyển hướng vào file hoặc CI log, `\r` có thể được lưu như ký tự điều khiển thay vì ghi đè dòng trước. Trong chế độ non-interactive, hãy dùng output theo dòng và giảm tần suất cập nhật.

## Khi không biết tổng số bước

Không có tổng số bước thì không thể tính phần trăm đáng tin cậy. Hãy dùng thông báo dạng:

```text
Đang kết nối tới máy chủ...
Đang tải dữ liệu...
Đang kiểm tra chữ ký...
Đang ghi dữ liệu...
Đã hoàn tất đồng bộ.
```

Trong terminal tương tác, có thể cập nhật một dòng với trạng thái ngắn:

```java
writer.print("\rĐang chờ phản hồi từ máy chủ...");
writer.flush();

// Sau khi tác vụ kết thúc
writer.println("\rĐã nhận phản hồi.");
writer.flush();
```

Không tự đặt phần trăm theo thời gian đã trôi qua nếu ứng dụng không có cơ sở ước lượng. Với tác vụ không xác định thời lượng, spinner thể hiện “đang hoạt động” chính xác hơn một thanh phần trăm tăng giả.

## `ProgressView` trong Spring Shell Terminal UI

`ProgressView` là một view dựng sẵn để hiển thị thông tin tiến trình. View có trạng thái gồm:

- `tickStart`: giá trị bắt đầu của thang tiến trình.
- `tickEnd`: giá trị kết thúc.
- `tickValue`: giá trị hiện tại.
- `running`: trạng thái đang chạy.
- `startTime` và `updateTime`: thời điểm bắt đầu và cập nhật gần nhất.

`ProgressView` mặc định có ba thành phần hiển thị: text mô tả, spinner và phần trăm. Có thể tạo thang từ `0` đến `100` hoặc truyền giới hạn riêng bằng constructor `ProgressView(int tickStart, int tickEnd)`. Các phương thức thường dùng:

| Phương thức | Tác dụng |
| --- | --- |
| `setDescription(String)` | Đặt mô tả tác vụ |
| `setSpinner(Spinner)` | Chọn spinner cụ thể |
| `start()` | Bắt đầu runtime logic của progress view |
| `setTickValue(int)` | Đặt giá trị hiện tại trong giới hạn đã khai báo |
| `tickAdvance(int)` | Tăng hoặc giảm tick hiện tại |
| `getState()` | Đọc trạng thái tiến trình |
| `stop()` | Dừng runtime logic |

Nếu `setTickValue()` nhận giá trị nhỏ hơn hoặc lớn hơn giới hạn, view giữ giá trị trong khoảng `tickStart` đến `tickEnd`. `tickAdvance()` cũng hỗ trợ số âm để lùi tiến trình, nhưng trong tác vụ thông thường chỉ nên tăng khi một bước thực sự hoàn tất.

### Đưa progress view vào vùng hiển thị của command

`ProgressView` là một `View`, vì vậy cần gắn nó vào cơ chế render của Terminal UI. Với command chạy trong REPL, `ViewComponentBuilder` tạo một `ViewComponent` không chiếm toàn màn hình. Component có thể chạy bất đồng bộ trong lúc command thực hiện công việc.

Ví dụ dưới đây dùng API Spring Shell 4.x:

```java
import java.util.List;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.jline.tui.component.ViewComponent;
import org.springframework.shell.jline.tui.component.ViewComponentBuilder;
import org.springframework.shell.jline.tui.component.view.control.ProgressView;
import org.springframework.stereotype.Component;

@Component
public class ImportCommands {

    private final ViewComponentBuilder viewComponentBuilder;
    private final ImportService importService;

    public ImportCommands(
            ViewComponentBuilder viewComponentBuilder,
            ImportService importService) {
        this.viewComponentBuilder = viewComponentBuilder;
        this.importService = importService;
    }

    @Command(name = "data import", description = "Nhập dữ liệu với thanh tiến trình")
    public String importData() {
        List<ImportRecord> records = importService.loadPendingRecords();
        if (records.isEmpty()) {
            return "Không có dữ liệu cần nhập.";
        }

        ProgressView progress = new ProgressView(0, records.size());
        progress.setDescription("Đang nhập dữ liệu");

        ViewComponent component = viewComponentBuilder.build(progress);
        ViewComponent.ViewComponentRun viewRun = component.runAsync();

        int completed = 0;
        try {
            progress.start();
            for (ImportRecord record : records) {
                importService.importOne(record);
                progress.setTickValue(++completed);
            }
        }
        finally {
            progress.stop();
            component.exit();
            viewRun.await();
        }

        return "Đã nhập " + completed + " bản ghi.";
    }
}
```

`ViewComponent` quản lý vòng lặp hiển thị trong khi command tiếp tục chạy. `runAsync()` khởi chạy vòng lặp view; command cập nhật `tickValue` sau mỗi bản ghi hoàn tất. Khối `finally` dừng progress và yêu cầu view thoát cả khi service ném exception. Ví dụ tập trung vào lifecycle của progress view; các kiểu `ImportRecord`, `ImportService` và phần đăng ký command thuộc ứng dụng.

Với tác vụ có thể bị hủy hoặc chạy lâu, hãy quản lý thêm trạng thái worker và hủy công việc nền khi component bị đóng. Không để view tiếp tục chạy sau khi command đã kết thúc.

### Khác biệt package giữa 3.4.x và 4.x

Terminal UI giữ các khái niệm tương tự nhưng package thay đổi giữa hai major version:

| Thành phần | Spring Shell 3.4.x | Spring Shell 4.x |
| --- | --- | --- |
| `ProgressView` | `org.springframework.shell.component.view.control.ProgressView` | `org.springframework.shell.jline.tui.component.view.control.ProgressView` |
| `ViewComponent` | `org.springframework.shell.component.ViewComponent` | `org.springframework.shell.jline.tui.component.ViewComponent` |
| `ViewComponentBuilder` | `org.springframework.shell.component.ViewComponentBuilder` | `org.springframework.shell.jline.tui.component.ViewComponentBuilder` |
| `TerminalUI` | `org.springframework.shell.component.view.TerminalUI` | `org.springframework.shell.jline.tui.component.view.TerminalUI` |
| `EventLoop` | `org.springframework.shell.component.view.event.EventLoop` | `org.springframework.shell.jline.tui.component.view.event.EventLoop` |

Khi chuyển code từ 3.4.x lên 4.x, hãy cập nhật import theo bảng này và kiểm tra lại dependency/API đã resolve. Không chỉ thay package `ProgressView`; `ViewComponent`, builder, event loop và các view khác cũng thuộc cây package mới.

## Event của `ProgressView`

Progress view phát ba event theo vòng đời:

| Event | Thời điểm |
| --- | --- |
| `ProgressViewStartEvent` | Bắt đầu theo dõi tiến trình |
| `ProgressViewStateChangeEvent` | Trạng thái tiến trình thay đổi |
| `ProgressViewEndEvent` | Dừng theo dõi tiến trình |

Các event hữu ích khi ứng dụng cần ghi nhận thời gian, cập nhật một status bar hoặc đo lường tiến trình. Ví dụ với Spring Shell 4.x, có thể theo dõi state change qua event loop của `ViewComponent`:

```java
component.getEventLoop()
        .viewEvents(ProgressView.ProgressViewStateChangeEvent.class, progress)
        .subscribe(event -> {
            ProgressView.ProgressState state = event.args().state();
            metrics.recordProgress(state.tickValue(), state.tickEnd());
        });
```

`EventLoop` điều phối event và nhịp cập nhật view. Dùng event để quan sát trạng thái hoặc cập nhật dữ liệu phụ trợ; không ghi thêm dòng terminal cho mỗi event vì như vậy sẽ phá vỡ màn hình progress. Nếu đăng ký subscriber sống lâu hơn component, hãy hủy subscription khi component kết thúc.

## Cập nhật màn hình có kiểm soát

Terminal UI quản lý vùng hiển thị qua `View`, `Screen` và `EventLoop`. `TerminalUI` cung cấp `redraw()` để yêu cầu vẽ lại toàn màn hình; yêu cầu này được chuyển vào event loop và xử lý sớm nhất có thể. Không cần tự xóa terminal rồi vẽ lại toàn bộ màn hình trong mỗi vòng lặp nghiệp vụ.

Một số nguyên tắc:

- Để `ProgressView` quản lý spinner, phần trăm và mô tả trong vùng view của nó.
- Chỉ cập nhật `tickValue` khi công việc có tiến triển thực sự.
- Không gọi `TerminalUI.redraw()` liên tục trong vòng lặp; event loop chịu trách nhiệm điều phối redraw.
- Không trộn `System.out`, mã ANSI tự viết và TUI rendering trên cùng một vùng màn hình.
- Dùng `StatusBarView` cho trạng thái ngắn tồn tại xuyên suốt màn hình; dùng `ProgressView` cho tác vụ có điểm bắt đầu và kết thúc.
- Dọn dẹp view, spinner, subscription và worker trong `finally` hoặc lifecycle hook tương ứng.

Terminal UI của Spring Shell được tài liệu 4.0.4 đánh dấu là tính năng experimental và có thể có thay đổi gây ảnh hưởng tương thích. Nếu ứng dụng cần giao diện TUI phức tạp, hãy khóa phiên bản, kiểm thử trên terminal mục tiêu và kiểm tra migration guide trước khi nâng cấp.

## Xử lý tiến trình khi command chạy non-interactive

TUI và spinner được thiết kế cho terminal tương tác. Khi command chạy từ file script, CI hoặc output được chuyển hướng, hãy chọn output văn bản ổn định:

```text
Import started: 1200 records
Import progress: 25% (300/1200)
Import progress: 50% (600/1200)
Import progress: 75% (900/1200)
Import progress: 100% (1200/1200)
Import completed: 1200 records
```

Trong môi trường tự động:

- Không phụ thuộc vào màu, spinner, cursor movement hoặc full-screen redraw.
- Ghi theo mốc tiến trình đủ thưa để log không bị phình lớn.
- Dùng thông điệp ổn định để hệ thống giám sát có thể tìm kiếm nếu cần.
- Trả exit code đúng khi tác vụ thất bại; thông báo “đang chạy” không có nghĩa là command đã thành công.
- Không đưa bí mật hoặc dữ liệu nhạy cảm vào mô tả tiến trình.

Nếu output cần được máy khác phân tích, cân nhắc định dạng có cấu trúc như JSON Lines thay vì chuỗi có ký tự `\r` hoặc spinner.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| In một dòng cho mỗi bản ghi | Terminal/log bị spam | Cập nhật theo phần trăm hoặc mốc thời gian |
| Dùng `\r` trong log CI | Ký tự carriage return xuất hiện nguyên dạng hoặc làm log khó đọc | Dùng `println` theo mốc hoặc chỉ in kết quả cuối |
| Hiển thị phần trăm khi không biết tổng | Người dùng nhận thông tin sai lệch | Dùng spinner hoặc mô tả trạng thái |
| Không gọi `flush()` khi cập nhật một dòng | Tiến trình có thể bị giữ trong buffer | Flush sau mỗi lần cập nhật cần hiển thị ngay |
| Quên xuống dòng sau progress line | Kết quả cuối nối vào dòng tiến trình | In newline trước thông báo hoàn tất |
| Tạo `ProgressView` nhưng không gắn vào view component | Không có vùng hiển thị để render | Dùng `ViewComponentBuilder` hoặc `TerminalUI` |
| Quên `start()`/`stop()` | Spinner/runtime logic không theo đúng vòng đời | Bắt đầu trước khi làm việc và dừng trong `finally` |
| Quên `component.exit()` | Vòng lặp render có thể tiếp tục sau command | Yêu cầu component thoát trong cleanup |
| Gọi redraw liên tục | Terminal nhấp nháy hoặc tốn tài nguyên | Để event loop điều phối cập nhật |
| Dùng import 3.x trong 4.x | Không biên dịch | Cập nhật package theo major version |
| TUI vẫn chạy sau lỗi nghiệp vụ | Giao diện bị treo hoặc giữ terminal | Dừng view và worker trong `finally` |

## Kiểm thử thông báo tiến trình

Kiểm thử cần xác minh cả nội dung lẫn vòng đời hiển thị:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Tổng số bước bằng 0 | Command trả thông báo “không có dữ liệu”, không tạo thang `0..0` |
| Tác vụ thành công | Tiến trình đạt giá trị cuối và thông báo hoàn tất xuất hiện một lần |
| Tác vụ thất bại giữa chừng | View được dừng và component thoát; exception vẫn được xử lý theo hợp đồng command |
| Tác vụ có hàng nghìn bước | Số lần ghi progress line được giới hạn |
| Tác vụ không biết tổng | Không hiển thị phần trăm giả |
| Terminal tương tác | `\r`, flush hoặc TUI hiển thị đúng |
| Output chuyển hướng | Không có spinner hoặc ký tự điều khiển gây nhiễu log |
| View event | Start/state change/end được phát đúng vòng đời |
| Resize terminal | View vẫn nằm trong vùng hiển thị hợp lệ |
| Cancel/interrupt | Worker dừng và UI được dọn dẹp |
| Nâng cấp Spring Shell | Package và hành vi TUI được kiểm tra lại trên phiên bản mới |

Với line reporter, có thể kiểm thử bằng `StringWriter`/`PrintWriter` để xác minh ngưỡng cập nhật và thông báo kết thúc. Với TUI, dùng test harness terminal của Spring Shell để kiểm tra view và event trong một môi trường terminal mô phỏng; unit test chỉ gọi `setTickValue()` không chứng minh màn hình thực sự được render.

## Quy trình triển khai progress indicator

1. Xác định tổng số bước có biết trước hay không và chọn phần trăm hoặc spinner.
2. Chọn output line-based cho command đơn giản/script, hoặc `ProgressView` cho terminal tương tác.
3. Nếu cập nhật một dòng, dùng `PrintWriter`, `\r`, `flush()` và giới hạn tần suất.
4. Nếu dùng TUI, khai báo `ProgressView`, gắn nó vào `ViewComponent`/`TerminalUI` và quản lý vòng đời `start()`/`stop()`.
5. Chỉ tăng tick sau khi một đơn vị công việc hoàn tất.
6. Dùng `finally` để dừng view, yêu cầu component thoát và hủy subscription.
7. Kiểm thử terminal tương tác, non-interactive, output chuyển hướng, lỗi và hủy tác vụ.

Thông báo tiến trình tốt giúp người dùng hiểu command còn đang làm việc và biết công việc đã đi đến đâu. Cập nhật theo mốc có ý nghĩa, để event loop quản lý việc vẽ lại và dọn dẹp view đúng lúc sẽ giữ terminal dễ đọc, tránh log bị spam và giúp command hoạt động ổn định trong cả môi trường tương tác lẫn tự động hóa.

## Tài liệu tham khảo

- [ProgressView – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/tui/views/progress.html)
- [Terminal UI – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/tui/index.html)
- [TerminalUI API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/TerminalUI.html)
- [ViewComponent API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/ViewComponent.html)
- [ViewComponentBuilder API – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/ViewComponentBuilder.html)
- [ViewComponentExecutor API – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/ViewComponentExecutor.html)
- [EventLoop API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/event/EventLoop.html)
- [ProgressView API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/control/ProgressView.html)
- [ProgressView – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/tui/views/progress.html)
- [ProgressView API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ProgressView.html)
- [ViewComponent API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/ViewComponent.html)
