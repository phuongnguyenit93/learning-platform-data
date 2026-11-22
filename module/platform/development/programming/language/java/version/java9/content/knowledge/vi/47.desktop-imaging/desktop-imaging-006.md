# Desktop: sự kiện mở tệp, URI và yêu cầu thoát trong Java

## 1. Bối cảnh và mục tiêu

Một ứng dụng Java có giao diện desktop thường nhận thao tác từ **hệ điều hành** chứ không chỉ từ các nút trong cửa sổ: người dùng nhấp đúp một tài liệu đã được liên kết với ứng dụng; bấm một liên kết URI tùy biến (deep link); hoặc chọn **Quit/Thoát** từ menu hệ thống. Những yêu cầu này cần được chuyển tới đúng xử lý trong ứng dụng, đồng thời không làm mất tài liệu chưa lưu.

Từ **Java 9**, module `java.desktop` cung cấp các giao diện xử lý sự kiện ứng dụng tại gói **`java.awt.desktop`** thông qua lớp **`java.awt.Desktop`**. Đây là API tiêu chuẩn của Java SE còn được hỗ trợ trên các JDK hiện đại, thay cho việc ứng dụng tự gọi API cũ của một hãng/OS để xử lý cùng loại sự kiện.

Ba trường hợp của bài:

1. **Mở tệp:** hệ điều hành yêu cầu *ứng dụng của chúng ta* mở một hoặc nhiều tệp → `Desktop.setOpenFileHandler(...)` nhận `OpenFilesEvent`.
2. **Mở URI:** hệ điều hành gửi một URI tới *ứng dụng của chúng ta* → `Desktop.setOpenURIHandler(...)` nhận `OpenURIEvent`.
3. **Yêu cầu thoát:** hệ điều hành muốn ứng dụng dừng → `Desktop.setQuitHandler(...)` nhận `QuitEvent` cùng một `QuitResponse` để ứng dụng chấp thuận hoặc hủy.

**Điều kiện quan trọng:** các sự kiện trên chỉ đến khi **OS và bộ đóng gói/đăng ký ứng dụng thực sự hỗ trợ**. Gọi `setOpenFileHandler` không tự động liên kết đuôi tệp của người dùng; gọi `setOpenURIHandler` không tự đăng ký URI scheme ở hệ điều hành; chạy bằng `java MainClass` cũng không bảo đảm menu Quit của OS được chuyển vào handler. Vì thế phải kiểm tra tính năng khả dụng và thử trên bản ứng dụng được đóng gói đúng.

### Luồng tổng thể

```text
[File Manager / Browser / OS application menu]
          |
          |  file association / URI association / native quit request
          v
[OS gửi sự kiện cho ứng dụng được đăng ký]
          |
          v
[java.awt.Desktop + java.awt.desktop handlers]
          |
          +-- OpenFilesEvent  --> kiểm tra danh sách File --> mở tài liệu phù hợp
          +-- OpenURIEvent    --> kiểm tra scheme/route --> xử lý deep link
          +-- QuitEvent       --> kiểm tra dữ liệu chưa lưu --> QuitResponse
          |
          v
[UI trên Event Dispatch Thread + nghiệp vụ ứng dụng]
```

Các luồng native event, UI và I/O có yêu cầu khác nhau: chuyển thao tác thay đổi Swing UI về **Event Dispatch Thread (EDT)**; nếu phải đọc file lớn hoặc truy cập mạng, thực hiện công việc nặng bên ngoài EDT và chỉ cập nhật UI sau khi có kết quả.

## 2. API và dữ liệu sự kiện hiện hành

| Nhu cầu | Điều kiện hỗ trợ | Cách đăng ký | Handler, event và dữ liệu |
| --- | --- | --- | --- |
| Nhận yêu cầu mở tệp | `Desktop.Action.APP_OPEN_FILE` | `desktop.setOpenFileHandler(handler)` | `OpenFilesHandler.openFiles(OpenFilesEvent)`; `event.getFiles()` là `List<File>`, `event.getSearchTerm()` có thể có tùy OS |
| Nhận yêu cầu mở URI | `Desktop.Action.APP_OPEN_URI` | `desktop.setOpenURIHandler(handler)` | `OpenURIHandler.openURI(OpenURIEvent)`; `event.getURI()` trả `java.net.URI` |
| Nhận yêu cầu thoát | `Desktop.Action.APP_QUIT_HANDLER` | `desktop.setQuitHandler(handler)` | `QuitHandler.handleQuitRequestWith(QuitEvent, QuitResponse)`; gọi đúng một quyết định `performQuit()` hoặc `cancelQuit()` |
| Đặt cách thoát mặc định | Hành vi `Desktop` của môi trường | `desktop.setQuitStrategy(strategy)` | `QuitStrategy.NORMAL_EXIT` (gọi `System.exit(0)`) hoặc `QuitStrategy.CLOSE_ALL_WINDOWS` |
| Nghe hệ thống chuyển foreground, ẩn app, sleep… | Tùy loại listener/platform | `desktop.addAppEventListener(listener)` | `SystemEventListener` và các subtype chuyên biệt; **không thay** ba handler nói trên |

### Phân biệt hành động “gửi ra ngoài” và “nhận từ OS”

Đây là lỗi rất phổ biến vì cùng dùng tên `Desktop`:

| Lời gọi Java | Hướng giao tiếp | Chức năng |
| --- | --- | --- |
| `desktop.open(file)` | **Ứng dụng Java → OS** | Nhờ OS mở file bằng chương trình được liên kết |
| `desktop.browse(uri)` | **Ứng dụng Java → OS** | Nhờ OS mở URI bằng browser/ứng dụng liên kết |
| `desktop.setOpenFileHandler(...)` | **OS → ứng dụng Java** | Nhận sự kiện người dùng yêu cầu **app hiện tại** mở file |
| `desktop.setOpenURIHandler(...)` | **OS → ứng dụng Java** | Nhận URI mà OS chuyển **vào app hiện tại** |
| `desktop.setQuitHandler(...)` | **OS → ứng dụng Java** | Cho app cơ hội xử lý một yêu cầu thoát của OS |

`Desktop.Action.OPEN` và `Desktop.Action.BROWSE` **khác** `Desktop.Action.APP_OPEN_FILE`/`APP_OPEN_URI`. Kiểm tra `isSupported(OPEN)` không thể chứng minh handler nhận file được hệ điều hành hỗ trợ.

### Phân biệt event và method

- `OpenFilesEvent.getFiles()` có thể chứa **nhiều file trong một event**, nên xử lý danh sách; không tự chọn phần tử đầu tiên rồi bỏ qua phần còn lại nếu ứng dụng có nghĩa vụ mở cả tập.
- `OpenFilesEvent.getSearchTerm()` có thể trả thông tin tìm kiếm từ OS (ví dụ ngữ cảnh mở file thông qua công cụ tìm kiếm), nhưng ứng dụng không được giả định nó luôn có.
- `OpenURIEvent.getURI()` trả đối tượng URI, có thể là deep link do hệ thống chuyển đến. Đó là **đầu vào ngoài**; cần kiểm tra scheme, host, path, quyền hạn và tham số trước khi xử lý.
- `QuitEvent` cho biết có yêu cầu thoát. Quyết định cuối cùng ở **`QuitResponse`**, không phải giá trị trả về của `handleQuitRequestWith`, vì phương thức đó trả `void`.

## 3. Kiểm tra khả năng hỗ trợ và đăng ký đúng thời điểm

Một ứng dụng desktop nên thực hiện theo thứ tự:

1. Kiểm tra môi trường có GUI bằng `GraphicsEnvironment.isHeadless()` khi định tạo Swing/AWT.
2. Kiểm tra `Desktop.isDesktopSupported()` **trước** `Desktop.getDesktop()`.
3. Lấy instance `Desktop`, sau đó kiểm tra từng `desktop.isSupported(Desktop.Action.APP_...)`. Một API có trên JDK không đồng nghĩa action tương ứng hoạt động trên OS.
4. Đăng ký các handler **càng sớm càng tốt trong quá trình khởi tạo**, trước khi coi ứng dụng là sẵn sàng nhận tài liệu và trước khi người dùng thao tác nhiều.
5. Chuyển nội dung event thành yêu cầu nghiệp vụ; tránh viết logic đọc/ghi file, mạng, hiển thị dialog chậm trực tiếp trong callback native.
6. Có đường xử lý tương đương cho môi trường **không hỗ trợ native event**, ví dụ menu File → Open, nút mở tài liệu, tham số dòng lệnh hoặc `WindowListener` cho cửa sổ.

Đoạn kiểm tra cấu hình cơ bản (đây là **mã minh họa**, cần thêm import và lớp chứa):

```java
if (!GraphicsEnvironment.isHeadless() && Desktop.isDesktopSupported()) {
    Desktop desktop = Desktop.getDesktop();

    if (desktop.isSupported(Desktop.Action.APP_OPEN_FILE)) {
        desktop.setOpenFileHandler(event ->
            System.out.println("Số tệp: " + event.getFiles().size())
        );
    }
    if (desktop.isSupported(Desktop.Action.APP_OPEN_URI)) {
        desktop.setOpenURIHandler(event ->
            System.out.println("URI: " + event.getURI())
        );
    }
    if (desktop.isSupported(Desktop.Action.APP_QUIT_HANDLER)) {
        desktop.setQuitHandler((event, response) -> {
            // Chỉ cho thoát nếu đã hoàn tất công việc cần thiết.
            response.performQuit();
        });
    }
}
```

Đoạn trên giúp nhận diện API, nhưng việc **luôn** `performQuit()` chỉ phù hợp với ứng dụng không có dữ liệu chưa lưu. Với editor thực tế cần hỏi người dùng, lưu trạng thái và có nhánh `cancelQuit()`.

### Không được “tự chữa” thiếu hỗ trợ bằng catch rồi bỏ qua tùy tiện

Một action có thể không hỗ trợ và `set...Handler` ném `UnsupportedOperationException`; xử lý bằng cách kiểm tra từng action là bước chính. Có thể ghi log chẩn đoán nếu nền tảng thay đổi giữa lúc kiểm tra và đăng ký. Tuy nhiên, không viết code phụ thuộc riêng vào một tên OS rồi bỏ qua `isSupported(...)`, vì khả năng native event còn phụ thuộc runtime/desktop session/packaging.

## 4. Ví dụ Java 17+ chạy độc lập: nhận file, deep link và native Quit

Chương trình **`DesktopEventsDemo.java`** có cửa sổ Swing ghi nhật ký sự kiện và ba nút:

- **Thử mở 2 tệp:** gọi trực tiếp phương thức xử lý danh sách file, để bạn kiểm tra phần ứng dụng **ngay cả khi OS không hỗ trợ native open-file**.
- **Thử URI:** đưa `learnapp://lesson/start` vào cùng phương thức xử lý URI, kiểm tra chỉ chấp nhận route đã cho phép.
- **Thoát cửa sổ:** đóng cửa sổ bình thường. Nút này là thao tác Swing, **không phải giả lập native `QuitEvent`**. Native Quit chỉ được thử bằng menu/hành vi Quit của hệ điều hành khi action/packaging hỗ trợ.

Ứng dụng thực hành **chỉ hiển thị đường dẫn file**, không đọc hoặc thực thi nội dung file, giúp tập trung vào cơ chế event và tránh nhầm file association với quyền tự động đọc mọi tệp.

**Tệp `DesktopEventsDemo.java`:**

```java
import java.awt.BorderLayout;
import java.awt.Desktop;
import java.awt.GraphicsEnvironment;
import java.io.File;
import java.net.URI;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;
import java.awt.desktop.QuitResponse;

public final class DesktopEventsDemo {
    private final JFrame frame = new JFrame("Java Desktop Events");
    private final JTextArea log = new JTextArea(15, 68);
    private final AtomicBoolean nativeQuitPending = new AtomicBoolean(false);

    public static void main(String[] args) {
        if (GraphicsEnvironment.isHeadless()) {
            System.err.println("Cần môi trường đồ họa để chạy ví dụ Swing.");
            return;
        }
        SwingUtilities.invokeLater(() -> new DesktopEventsDemo().start());
    }

    private void start() {
        log.setEditable(false);
        log.setLineWrap(true);
        log.setWrapStyleWord(true);

        JPanel controls = new JPanel();

        JButton testFiles = new JButton("Thử mở 2 tệp");
        testFiles.addActionListener(e -> acceptFiles(List.of(
            new File("example-a.txt"),
            new File("example-b.txt")
        )));
        controls.add(testFiles);

        JButton testUri = new JButton("Thử URI");
        testUri.addActionListener(e ->
            acceptUri(URI.create("learnapp://lesson/start"))
        );
        controls.add(testUri);

        JButton close = new JButton("Thoát cửa sổ");
        close.addActionListener(e -> frame.dispose());
        controls.add(close);

        frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE);
        frame.add(new JScrollPane(log), BorderLayout.CENTER);
        frame.add(controls, BorderLayout.SOUTH);

        // Đăng ký native handlers trước khi hiển thị cửa sổ.
        registerNativeHandlers();

        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    private void registerNativeHandlers() {
        if (!Desktop.isDesktopSupported()) {
            addLine("Desktop API không khả dụng trên môi trường này.");
            return;
        }
        Desktop desktop = Desktop.getDesktop();

        if (desktop.isSupported(Desktop.Action.APP_OPEN_FILE)) {
            desktop.setOpenFileHandler(event -> {
                // Chụp dữ liệu từ event trước khi chuyển sang EDT.
                List<File> files = List.copyOf(event.getFiles());
                SwingUtilities.invokeLater(() -> acceptFiles(files));
            });
            addLine("Có hỗ trợ nhận yêu cầu mở tệp.");
        } else {
            addLine("OS/JDK không hỗ trợ APP_OPEN_FILE.");
        }

        if (desktop.isSupported(Desktop.Action.APP_OPEN_URI)) {
            desktop.setOpenURIHandler(event -> {
                URI uri = event.getURI();
                SwingUtilities.invokeLater(() -> acceptUri(uri));
            });
            addLine("Có hỗ trợ nhận URI từ hệ điều hành.");
        } else {
            addLine("OS/JDK không hỗ trợ APP_OPEN_URI.");
        }

        if (desktop.isSupported(Desktop.Action.APP_QUIT_HANDLER)) {
            desktop.setQuitHandler((event, response) -> {
                // Native Quit có thể được yêu cầu nhiều lần trước khi đáp lời.
                if (!nativeQuitPending.compareAndSet(false, true)) {
                    return;
                }
                SwingUtilities.invokeLater(
                    () -> decideNativeQuit(response)
                );
            });
            addLine("Có hỗ trợ xử lý yêu cầu Quit của hệ điều hành.");
        } else {
            addLine("OS/JDK không hỗ trợ APP_QUIT_HANDLER.");
        }
    }

    private void acceptFiles(List<File> files) {
        addLine("Yêu cầu mở " + files.size() + " tệp:");
        for (File file : files) {
            // Bản demo chỉ ghi đường dẫn, không tự mở nội dung ngoài ý muốn.
            addLine("  " + file.toPath().toAbsolutePath().normalize());
        }
    }

    private void acceptUri(URI uri) {
        boolean allowed = "learnapp".equalsIgnoreCase(uri.getScheme())
            && "lesson".equalsIgnoreCase(uri.getHost())
            && "/start".equals(uri.getPath())
            && uri.getRawQuery() == null
            && uri.getRawFragment() == null;

        if (allowed) {
            addLine("Deep link hợp lệ: mở màn hình bài học /start");
        } else {
            addLine("Từ chối URI không thuộc route cho phép: " + uri);
        }
    }

    private void decideNativeQuit(QuitResponse response) {
        try {
            int choice = JOptionPane.showConfirmDialog(
                frame,
                "Hệ điều hành yêu cầu thoát ứng dụng. Tiếp tục?",
                "Xác nhận thoát",
                JOptionPane.YES_NO_OPTION
            );

            if (choice == JOptionPane.YES_OPTION) {
                response.performQuit();
            } else {
                response.cancelQuit();
                addLine("Đã hủy yêu cầu Quit từ hệ điều hành.");
            }
        } finally {
            nativeQuitPending.set(false);
        }
    }

    private void addLine(String message) {
        // Mọi lời gọi tới addLine() ở đây đều chạy trên Swing EDT.
        log.append(message + System.lineSeparator());
        log.setCaretPosition(log.getDocument().getLength());
    }
}
```

Tại thư mục chứa file nguồn, dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DesktopEventsDemo.java
java DesktopEventsDemo
```

**Kết quả có thể xác minh:** một cửa sổ xuất hiện. Khi bấm **Thử mở 2 tệp**, vùng nhật ký ghi một dòng số tệp bằng `2`, rồi hai đường dẫn tuyệt đối (phần thư mục khác nhau trên từng máy). Khi bấm **Thử URI**, ứng dụng ghi đúng:

```text
Deep link hợp lệ: mở màn hình bài học /start
```

Các dòng hiển thị tính năng `APP_OPEN_FILE`, `APP_OPEN_URI` và `APP_QUIT_HANDLER` phụ thuộc OS/JDK. Vì là chương trình Swing, **không có stdout cố định trong terminal trên máy có GUI**. Trong môi trường headless, ví dụ in thông báo lỗi đồ họa ra **stderr** rồi kết thúc.

### 4.1. Vì sao code hoạt động đúng?

- Các lambda của `setOpenFileHandler` và `setOpenURIHandler` nhận event, sao chép phần dữ liệu cần dùng và chuyển cập nhật UI về EDT bằng `SwingUtilities.invokeLater`; không giả định callback native luôn chạy trên EDT.
- `acceptFiles` duyệt **tất cả file**; có thể thay mỗi lượt ghi log thành “xác thực loại file → kiểm tra quyền → đọc file qua worker thread → hiển thị từng tab” trong editor thật.
- `acceptUri` chỉ chấp nhận **scheme + host + path + điều kiện query/fragment** đã định trước. Gọi `getURI()` chưa đồng nghĩa được phép tải URL hay mở một file tùy ý từ path.
- `QuitResponse` là phản hồi **một lần** cho yêu cầu OS. `performQuit()` chấp thuận và thực hiện chiến lược thoát mặc định; `cancelQuit()` yêu cầu OS hủy lượt thoát đó.
- `nativeQuitPending` ngăn tạo nhiều dialog cho các lời yêu cầu Quit lặp lại trong khi quyết định đầu tiên chưa hoàn tất; theo hợp đồng `QuitHandler`, các yêu cầu lặp lại trước khi phản hồi được chuyển cùng `QuitResponse` đang chờ.
- Nút **Thoát cửa sổ** chỉ đóng `JFrame`. Nó **không** giả lập một `QuitEvent`/`QuitResponse` được hệ điều hành phát ra. Muốn bảo vệ tài liệu chưa lưu khi người dùng bấm nút X, cần cài riêng `WindowListener` và dùng chính quy trình hỏi lưu dữ liệu của ứng dụng.

**Giới hạn minh họa:** đoạn ví dụ log đường dẫn, không xây editor, không có lưu trạng thái. Trong ứng dụng có tài liệu chưa lưu, phải nối `decideNativeQuit` với trạng thái của tài liệu và chỉ `performQuit` sau khi lưu thành công hoặc người dùng chủ động chọn bỏ thay đổi.

## 5. Cơ chế Quit: phản hồi một lần, hủy và hoàn tất

`Desktop.setQuitHandler(...)` không giống `Runtime.addShutdownHook(...)`:

- **QuitHandler** là một lần OS **đề nghị** ứng dụng thoát, có thể bị hủy. Người dùng có thể chọn giữ ứng dụng mở để lưu tài liệu.
- **Shutdown hook** chạy trong nhiều tình huống JVM đang kết thúc nhưng không cung cấp phương tiện tiêu chuẩn để veto yêu cầu Quit của OS. Không dùng shutdown hook làm thay thế cho `QuitResponse.cancelQuit()`.
- Một lệnh `System.exit(0)` gọi trực tiếp trong ứng dụng có thể kết thúc JVM mà **không tạo native QuitEvent**; không nên chờ `QuitHandler` tự chặn mọi đường thoát.

Theo hợp đồng của `QuitHandler.handleQuitRequestWith(...)`:

1. Ứng dụng phải **gọi `performQuit()` hoặc `cancelQuit()`**, hoặc tự bảo đảm ứng dụng thực sự kết thúc.
2. Nếu xử lý cần UI phức tạp, có thể giữ `QuitResponse` và trả lời từ một thread khác sau khi hoàn tất; không cần buộc callback native đợi trong thao tác blocking.
3. OS có thể phát nhiều lời yêu cầu Quit **trước khi request đầu được trả lời**; handler có thể bị gọi nhiều lần với **cùng `QuitResponse`**.
4. Một khi đã gọi một trong hai phương thức trên, `QuitResponse` đã dùng **không thể thay đổi quyết định**.
5. `cancelQuit()` có thể **hủy cả quá trình đăng xuất/khởi động lại/tắt máy đang chờ** nếu hệ điều hành đang yêu cầu ứng dụng thoát trong quá trình đó. Không nên từ chối bừa bãi.

Một quy trình thoát cho ứng dụng lưu tài liệu thường có ba nhánh:

| Trạng thái / lựa chọn của người dùng | Hành động đúng |
| --- | --- |
| Không có dữ liệu chưa lưu | Chuẩn bị dừng, `response.performQuit()` |
| Có dữ liệu chưa lưu, chọn **Lưu** | Lưu hoàn tất và kiểm tra thành công, sau đó `performQuit()` |
| Chọn **Hủy**, hoặc thao tác lưu thất bại và người dùng muốn ở lại | `response.cancelQuit()` |
| Chọn **Không lưu rồi thoát** | Ghi nhận quyết định rõ ràng và `performQuit()` |

Khi gọi `performQuit()`, JSSE không liên quan; đây là API desktop. Hành động thực tế phụ thuộc `QuitStrategy`: `NORMAL_EXIT` gọi `System.exit(0)`, còn `CLOSE_ALL_WINDOWS` đóng các cửa sổ. Với chiến lược đóng cửa sổ, cần hiểu các `WindowListener` của ứng dụng có thể tham gia; không lẫn “đóng một JFrame” với “chấp nhận lệnh Quit toàn ứng dụng”.

### Tránh mất dữ liệu khi hệ điều hành chấm dứt đột ngột

Ngay cả khi đã đăng ký QuitHandler, hệ thống có thể cưỡng chế kết thúc tiến trình do crash, kill, hết tài nguyên hoặc một chính sách khởi động lại. `Desktop.enableSuddenTermination()` còn cho phép hệ thống trên nền tảng hỗ trợ dừng ứng dụng **mà không thông báo QuitHandler/shutdown hooks**. Vì thế không dùng thao tác đó nếu ứng dụng đang có trạng thái chưa lưu; hãy có autosave/khôi phục dữ liệu phù hợp.

Tất cả cơ chế này là quản trị vòng đời **desktop GUI**, không phải cách dừng dịch vụ backend/headless trong container.

## 6. Mở file: xử lý nhiều mục, định dạng và quyền truy cập

`OpenFilesEvent` là **yêu cầu từ OS**, không chứng minh nội dung file an toàn. Khi thay hàm `acceptFiles(...)` của demo bằng chức năng mở tài liệu thật, nên:

1. Kiểm tra `File` → `Path` hợp lệ, file tồn tại, file thường và ứng dụng được phép đọc.
2. Chỉ chấp nhận định dạng mà ứng dụng hỗ trợ; **đuôi tệp là gợi ý**, không phải bằng chứng nội dung.
3. Đặt giới hạn kích thước trước khi nạp file vào bộ nhớ; tránh khóa EDT khi đọc file lớn.
4. Khi đọc tài liệu có thể chứa macro/script/serialization hoặc URI bên ngoài, sử dụng parser an toàn và chính sách nội dung của ứng dụng.
5. Nếu event có nhiều file, mở từng tài liệu theo yêu cầu hoặc báo lỗi rõ cho từng file; tránh âm thầm bỏ qua file thứ hai.
6. Khi file mở từ OS lúc ứng dụng mới khởi động, cần có mô hình tiếp nhận yêu cầu **trước khi tất cả cửa sổ/tab sẵn sàng**, có thể đưa vào queue ứng dụng rồi xử lý tuần tự.

Đối với Swing, dùng `SwingWorker` hoặc `ExecutorService` để đọc file ngoài EDT, đưa phần kết quả hiển thị về EDT. Không để callback hệ điều hành tự gọi các hàm I/O kéo dài hàng giây.

Một số nền tảng cung cấp `event.getSearchTerm()` khi người dùng mở file từ giao diện tìm kiếm. Chỉ dùng làm gợi ý hiển thị highlight; không dùng search term như tên file, quyền truy cập hoặc chuỗi để xây câu lệnh hệ thống.

## 7. Mở URI: deep link cần được kiểm soát

`OpenURIEvent` hữu ích khi OS đã liên kết một URI với ứng dụng, ví dụ:

```text
learnapp://lesson/start
```

Nhưng `java.net.URI` chỉ phân tích cú pháp; URI của bên ngoài có thể chứa scheme, host, query, fragment hoặc mã hóa percent. Để tránh vô tình cho người khác yêu cầu mở đường dẫn hệ thống, tải URL độc hại hoặc thực hiện thao tác có quyền:

- Dùng **allowlist** cho scheme, route và loại hành động; không chuyển trực tiếp URI vào `Desktop.browse(uri)`, `ProcessBuilder` hoặc `Files.readString(Path.of(uri))` mà không xác thực.
- Xác minh origin/người dùng và quyền nghiệp vụ nếu deep link dẫn tới chức năng nhạy cảm. Deep link không tự mang quyền xác thực; không làm thay đổi dữ liệu chỉ vì URI có `action=delete` hay tham số khác.
- Nếu ứng dụng hỗ trợ URL HTTP(S), không biến việc nhận link thành proxy SSRF hoặc tải tài nguyên nội bộ tùy ý; kiểm soát địa chỉ và chính sách mạng như đối với input khác.
- Hạn chế độ dài và định dạng tham số; không tự giải mã percent-encoding nhiều lần rồi dùng kết quả như một path đã kiểm chứng.
- Định nghĩa hành vi khi ứng dụng đang mở, khi chưa đăng nhập, khi link không hợp lệ và khi app được kích hoạt nhiều lần.

Mẫu trong `acceptUri` chủ động chỉ chấp nhận một route chính xác. Một ứng dụng lớn hơn nên dùng router có parse/validate rõ ràng và test cho các đường dẫn, query và URI bị từ chối.

**Đừng đồng nhất URI với URL:** `URI` là định danh tài nguyên tổng quát, có thể dùng scheme tự định nghĩa; `URL` thường gắn với thao tác định vị/truy cập tài nguyên và các protocol handler. `OpenURIEvent` không có nghĩa JDK đã tự truy cập mạng hoặc tải tài nguyên đích.

## 8. Kết nối với hệ điều hành và đóng gói ứng dụng

### Mở tệp bằng liên kết OS

Trên hệ điều hành desktop, người dùng thường chọn “Open With…” hoặc nhấp đôi vào đuôi file đã liên kết với ứng dụng. Việc đăng ký liên kết là **công việc của hệ điều hành hoặc bộ cài**, không nằm trong `setOpenFileHandler(...)`.

Với JDK hiện hành, công cụ **`jpackage`** hỗ trợ `--file-associations` để mô tả loại file mà ứng dụng xử lý. Ví dụ file thuộc tính:

**`association.properties`:**

```properties
extension=demo
mime-type=application/x-demo-document
description=Demo document
```

Một lệnh **minh họa** khi đã có JAR ở thư mục `app-input`:

```bash
jpackage --name DesktopEventsDemo --input app-input --main-jar DesktopEventsDemo.jar --file-associations association.properties
```

Lệnh thực tế cần chọn kiểu package, quyền và thao tác cài đặt thích hợp trên từng OS; việc tạo/cài bộ package phải kiểm tra trên **chính nền tảng đích**. Trong demo, app chỉ ghi đường dẫn `.demo` vào log; một editor thật cần tự triển khai đọc file. `jpackage` tạo liên kết file không đồng nghĩa bản Java chạy thẳng từ terminal sẽ nhận native event tương tự.

**Đặc thù macOS:** theo Javadoc `Desktop.setOpenFileHandler(...)`, thông báo mở file qua desktop integration của JDK chỉ đến khi Java app là **bundled application** và có `CFBundleDocumentTypes` tương ứng trong `Info.plist`. Vì vậy chỉ thử `java DesktopEventsDemo` và thấy callback không được gọi **chưa đủ** để kết luận code sai.

### URI scheme tùy chỉnh

Đối với `learnapp://...`, cần đăng ký ứng dụng là handler cho scheme đó trong hệ điều hành. Trên **macOS**, `Info.plist` sử dụng `CFBundleURLTypes`/`CFBundleURLSchemes` để mô tả scheme. Trên Windows/Linux có các cơ chế đăng ký giao thức ứng dụng riêng; cấu hình association cho **đuôi file** bằng `--file-associations` **không tự thay thế** đăng ký URI scheme.

Chỉ khi OS đã định tuyến URI về ứng dụng và nền tảng Java hỗ trợ `APP_OPEN_URI` thì handler mới có cơ hội nhận `OpenURIEvent`. Một số launcher có thể chuyển đường dẫn/URI qua **tham số dòng lệnh** hoặc kích hoạt một process thứ hai thay vì gửi event vào process đang chạy; thiết kế ứng dụng phải xét mô hình single-instance/multiple-instance của bộ đóng gói thực tế.

### Yêu cầu Quit từ menu OS

Menu Quit của macOS hoặc thao tác thoát do OS gửi có thể tạo sự kiện native. Trên những nền tảng khác, các action `APP_QUIT_HANDLER` có thể không khả dụng. Đóng cửa sổ bằng nút X, người dùng gọi lệnh Quit của ứng dụng và `System.exit(...)` là các đường khác nhau; nếu cần quy trình xác nhận lưu tài liệu nhất quán, hãy gom logic nghiệp vụ thành **một hàm** rồi gọi từ `WindowListener`, menu File → Exit và native `QuitHandler` tương ứng.

## 9. Kiểm thử và QA theo đúng phạm vi

### Kiểm thử không cần đóng gói

Chạy `DesktopEventsDemo` từ terminal có giao diện:

1. Cửa sổ tạo được, không có ngoại lệ `HeadlessException`.
2. Bấm **Thử mở 2 tệp** → thấy số lượng `2` và hai đường dẫn riêng.
3. Bấm **Thử URI** → thấy route `/start` được chấp nhận.
4. Bấm **Thoát cửa sổ** → cửa sổ được đóng.
5. Đọc ba dòng thông tin hỗ trợ action để biết những native handler nào **có thể** đăng ký trên runtime này.

Những kiểm thử này **chưa chứng minh OS đã gửi event**; chúng xác nhận phần xử lý nội bộ và quá trình đăng ký không gây lỗi trong môi trường hiện tại.

### Kiểm thử native integration trên app được đóng gói

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Mở file loại đã liên kết từ file manager | OS định tuyến đến app; handler nhận `OpenFilesEvent` khi nền tảng hỗ trợ |
| Mở nhiều file một lần | `getFiles()` được xử lý đầy đủ hoặc app nhận các yêu cầu mở tương ứng theo cách OS chuyển |
| Mở URI scheme đã đăng ký | `OpenURIEvent.getURI()` nhận đúng URI; router từ chối link ngoài allowlist |
| Tạo file/URI mở lúc app chưa có cửa sổ | Đăng ký đủ sớm; không mất yêu cầu khi UI chưa sẵn sàng |
| Chọn Quit khi không có dữ liệu chưa lưu | `performQuit()` và ứng dụng thoát theo chiến lược mong muốn |
| Chọn Hủy tại hộp thoại Quit | `cancelQuit()` và ứng dụng tiếp tục chạy |
| Gửi nhiều yêu cầu Quit liên tục | Không mở nhiều hộp thoại trùng, không dùng `QuitResponse` đã trả lời lần hai |
| Thử trên OS không hỗ trợ action | Vẫn có menu/nút nội bộ, không crash do `UnsupportedOperationException` |

Khi test luồng native Quit, hãy dùng một tài liệu thử nghiệm; không thử can thiệp logout/shutdown của máy đang làm việc thật chỉ để tạo event.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `Desktop.getDesktop()` ném lỗi hoặc không có GUI | Headless/container hoặc nền tảng thiếu Desktop API | Kiểm tra `GraphicsEnvironment.isHeadless()` và `Desktop.isDesktopSupported()` trước |
| `setOpenFileHandler`/`setOpenURIHandler` bị từ chối | Action không được platform/JDK hỗ trợ | Kiểm tra **đúng** `APP_OPEN_FILE`/`APP_OPEN_URI`; cung cấp lối mở file/URI khác |
| Đã đăng ký handler nhưng nhấp đôi file không có callback | Chưa đăng ký file association, app chưa được đóng gói đúng, launcher đưa path qua args | Kiểm tra bộ cài, `Info.plist`/file association và cách OS phát sự kiện |
| Deep link không gọi ứng dụng | Scheme chưa đăng ký với OS; chỉ thiết lập Java handler | Thiết lập đăng ký URI scheme theo nền tảng, kiểm thử app bundled |
| Tưởng `desktop.open(file)` là nhận event của app hiện tại | Nhầm chiều API | Phân biệt `open`/`browse` gửi ra OS và `setOpen...Handler` nhận vào |
| Ứng dụng treo khi mở file lớn | Đọc/parse file ngay trên EDT hoặc callback native | Đưa I/O sang worker thread, cập nhật UI trên EDT |
| App bỏ sót file thứ hai | Chỉ đọc `getFiles().get(0)` | Duyệt toàn bộ `List<File>` hoặc báo rõ chính sách nhiều file |
| Quit bị treo hoặc giữ OS trong trạng thái chờ | Handler chưa gọi `performQuit()` hay `cancelQuit()` | Bảo đảm mỗi request có một quyết định, kể cả khi lỗi/lưu bị hủy |
| Sau khi bấm Hủy app vẫn thoát | Đã tự gọi `System.exit(0)` hoặc `frame.dispose()` ở nhánh hủy | Chỉ thoát sau khi người dùng chấp thuận và hoàn tất lưu |
| Native Quit không chạy khi bấm X | `WindowEvent` khác native `QuitEvent` | Thêm `WindowListener`/menu Exit riêng, dùng chung hàm kiểm tra dữ liệu chưa lưu |
| Native Quit không được gọi dù đã set handler | OS không hỗ trợ hoặc cho phép sudden termination | Kiểm tra action, đóng gói và chính sách sudden termination |
| Các URI ngoài ý muốn kích hoạt tính năng | Không kiểm tra scheme/route/đăng nhập | Dùng allowlist và xác thực/ủy quyền trước khi thực thi nghiệp vụ |

## 11. Ghi nhớ về thiết kế hiện đại

**Handler nhận sự kiện OS chỉ nên là một adapter mỏng.** Tách rõ:

```text
Native/Desktop adapter:
  OpenFilesEvent / OpenURIEvent / QuitEvent
                |
                v
Application commands:
  openDocuments(files) / openDeepLink(uri) / requestQuit()
                |
                v
Validation, model, persistence, UI state
                |
                v
EDT cho UI; worker thread cho I/O; QuitResponse cho native Quit
```

Kiến trúc đó giúp hành vi mở file/URI hoạt động từ menu Swing, tham số dòng lệnh, deep link và OS native event theo cùng quy tắc. Nó cũng giúp kiểm thử nghiệp vụ mà không cần giả mạo event hệ điều hành.

Trong Java 9+, ưu tiên `java.awt.desktop` và `java.awt.Desktop` chuẩn, chạy trên JDK đang được hỗ trợ. Không xây code mới dựa trên bộ giao diện cũ chỉ có ở một hệ điều hành; không coi APIs của Swing/AWT hay Desktop là bảo đảm chạy trong server/headless. Tương lai của desktop integration phụ thuộc bản JDK, OS, provider desktop session và cơ chế cài đặt ứng dụng cụ thể, vì vậy **khả năng thực tế luôn cần kiểm thử trên bản đóng gói cuối**.

## Tài liệu tham khảo

- [Java SE 25: `java.awt.Desktop`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Desktop.html) — `isDesktopSupported`, `isSupported`, ba `set...Handler`, `setQuitStrategy` và giới hạn macOS.
- [Java SE 25: `OpenFilesHandler`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/OpenFilesHandler.html) — hợp đồng callback mở file.
- [Java SE 25: `OpenFilesEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/OpenFilesEvent.html) — `getFiles`, `getSearchTerm`.
- [Java SE 25: `OpenURIEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/OpenURIEvent.html) — `getURI`.
- [Java SE 25: `QuitHandler`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/QuitHandler.html) và [`QuitResponse`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/QuitResponse.html) — một lần trả lời, các yêu cầu trùng và tác động của hủy Quit.
- [Java SE 25: `QuitStrategy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/desktop/QuitStrategy.html) — chiến lược kết thúc ứng dụng.
- [Oracle: jpackage, hỗ trợ file associations](https://docs.oracle.com/en/java/javase/23/jpackage/support-application-features.html) — đăng ký đuôi file thông qua bộ đóng gói.
- [Apple: `CFBundleURLTypes`](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleurltypes) — đăng ký URI scheme tùy biến với macOS.

Các ví dụ dùng API chuẩn có từ Java 9 và còn được duy trì; bài thực hành chọn **Java 17+** để biên dịch trên môi trường hiện đại.