# Giữ thao tác giao diện trên luồng sự kiện trong Java Swing

## 1. Vấn đề: tại sao giao diện Swing cần một luồng riêng?

Trong Swing, khi người dùng nhấn nút, gõ phím, kéo cửa sổ hoặc khi hệ thống yêu cầu vẽ lại, các sự kiện được xử lý trên **Event Dispatch Thread (EDT)** — luồng điều phối sự kiện của giao diện. Phần lớn component Swing như `JFrame`, `JButton`, `JLabel`, `JTextField`, `JTable` và các model liên quan **không được thiết kế để thao tác đồng thời tùy ý từ nhiều luồng**.

Vì vậy, hai nguyên tắc cần giữ cùng lúc:

1. **Tạo và cập nhật trạng thái giao diện Swing trên EDT** (trừ những thao tác được tài liệu API công bố rõ là an toàn từ luồng khác).
2. **Không đặt công việc chậm lên EDT**: mạng, truy vấn cơ sở dữ liệu, xử lý file lớn, vòng lặp tính toán dài, `Thread.sleep`, đợi khóa hay chờ một tác vụ nền hoàn thành phải được đưa ra khỏi EDT.

Nếu bỏ nguyên tắc thứ nhất, chương trình có thể có data race, hiển thị bất nhất hoặc lỗi khó tái hiện. Nếu bỏ nguyên tắc thứ hai, EDT bận và không kịp xử lý sự kiện tiếp theo: cửa sổ ngừng phản hồi, repaint chậm và nút bấm không hoạt động như mong đợi.

Đây là kiến thức **vẫn áp dụng trên Java 17+ và các bản Java hiện đại**. Bài dùng các API Swing chính thức đang được hỗ trợ: `SwingUtilities`, `EventQueue`, `SwingWorker`, `javax.swing.Timer` và try-with-resources khi công việc nền mở tài nguyên. Không sử dụng các cách quản lý giao diện lỗi thời hoặc API nội bộ.

## 2. Mô hình luồng hoạt động

Một chương trình Swing điển hình có ít nhất hai nhóm công việc:

- **EDT**: tạo/đặt component, nhận `ActionEvent`, cập nhật label, model, thanh tiến độ, điều khiển trạng thái nút, vẽ lại và xử lý các tương tác nhỏ.
- **Luồng nền**: tải dữ liệu từ mạng, đọc file, xử lý ảnh, tính toán hoặc tác vụ khác có thể kéo dài. Khi có kết quả, luồng nền **gửi công việc cập nhật UI trở lại EDT**.

Sơ đồ:

```text
main()
  |
  | SwingUtilities.invokeLater(...)
  v
EDT: tạo và hiển thị JFrame
  |
  | người dùng click "Bắt đầu"
  v
EDT: actionPerformed -> kiểm tra input, đổi nút, gọi worker.execute()
  |                                             |
  | trả về ngay                                 v
  |                                   Worker: doInBackground()
  |                                   (I/O hoặc tính toán)
  |                                             |
  |                      publish(...) / kết quả hoàn thành
  |                         |                   |
  v                         v                   v
EDT vẫn nhận click       EDT: process(...)   EDT: done(...)
và vẽ giao diện          cập nhật progress   nhận kết quả, bật lại nút
```

Điểm quan trọng: `ActionListener.actionPerformed(...)` chạy trên EDT đối với sự kiện nút Swing thông thường, nhưng nó **không được tự thực hiện tác vụ dài**. Việc một callback chạy đúng EDT không có nghĩa mọi thứ trong callback đều phù hợp để chạy ở đó.

## 3. Khởi tạo giao diện đúng trên EDT

`main` không tự động là EDT. Để xây dựng và hiển thị cửa sổ một cách nhất quán, chuyển việc khởi tạo Swing sang EDT:

```java
import javax.swing.JFrame;
import javax.swing.SwingUtilities;

public final class StartSwing {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Swing on EDT");
            frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
            frame.setSize(360, 180);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
```

Ví dụ này độc lập; lưu `StartSwing.java` và chạy:

```bash
javac -encoding UTF-8 StartSwing.java
java StartSwing
```

**Kết quả:** một cửa sổ tiêu đề “Swing on EDT” xuất hiện; chương trình không in dòng nào ra stdout. Ví dụ cần môi trường máy tính có hệ thống cửa sổ; trên server *headless*, `JFrame` sẽ không tạo được giao diện.

- `SwingUtilities.invokeLater(Runnable)` **xếp công việc vào hàng đợi sự kiện** và trả về ngay cho luồng gọi. Công việc được thực thi trên EDT sau khi EDT xử lý các sự kiện đang chờ trước nó. Nó không bảo đảm thời điểm tuyệt đối và không làm cho công việc chậm trở nên nhanh.
- Nếu gọi `invokeLater` ngay khi đang ở EDT, runnable vẫn được xếp hàng để chạy **sau**, không chạy đồng bộ ngay tại chỗ.
- `EventQueue.invokeLater(...)` ở `java.awt` cũng dùng để gửi việc tới hàng đợi của EDT; `SwingUtilities.invokeLater(...)` là cách viết quen thuộc khi làm việc với Swing.

Khi chương trình không có giao diện đang hoạt động hoặc chạy trong môi trường headless, không nên mặc định ép khởi tạo `JFrame`.

## 4. Kiểm tra luồng đang chạy và điều hướng cập nhật UI

Dùng `SwingUtilities.isEventDispatchThread()` để biết code hiện chạy trên EDT hay không:

```java
// Mảnh mã: statusLabel là JLabel đã được khởi tạo trên EDT.
if (SwingUtilities.isEventDispatchThread()) {
    statusLabel.setText("Sẵn sàng");
} else {
    SwingUtilities.invokeLater(() -> statusLabel.setText("Sẵn sàng"));
}
```

Đây là **đoạn minh họa**, không phải lớp Java độc lập. Mẫu trên hữu ích ở điểm giao giữa luồng nền và UI. Tuy nhiên, thiết kế tốt thường đã biết mình đang ở EDT hay không: handler giao diện cập nhật trực tiếp, còn worker thì gửi sự kiện hoặc kết quả về EDT.

Một guard để phát hiện dùng nhầm luồng trong quá trình phát triển:

```java
private static void requireEdt() {
    if (!SwingUtilities.isEventDispatchThread()) {
        throw new IllegalStateException("Swing UI must be accessed on EDT");
    }
}
```

Dùng guard ở những hàm tạo hoặc sửa nhiều component, đặc biệt khi API có thể được gọi từ nhiều nơi. Guard là cách phát hiện lỗi sớm; nó không tự chuyển công việc sang EDT.

### `invokeLater` và `invokeAndWait` có khác nhau gì?

| API | Luồng gọi | Cách hoạt động | Dùng khi nào |
| --- | --- | --- | --- |
| `SwingUtilities.invokeLater(task)` | EDT hoặc luồng khác | Đưa `task` vào hàng đợi, trả về mà không đợi task kết thúc | Cập nhật UI bất đồng bộ, dựng cửa sổ từ `main` |
| `SwingUtilities.invokeAndWait(task)` | **Chỉ luồng không phải EDT** | Đợi EDT chạy `task` xong; có thể ném `InterruptedException` hoặc `InvocationTargetException` | Trường hợp hiếm khi caller thực sự cần đợi một thay đổi nhỏ trên EDT |
| `SwingUtilities.isEventDispatchThread()` | Bất kỳ luồng | Trả về boolean cho luồng gọi hiện tại | Kiểm tra bất biến luồng khi debug/test |

Không gọi `invokeAndWait` **từ EDT**: lệnh chờ chính EDT thực hiện việc trong hàng đợi là không hợp lệ và có thể gây treo nếu áp dụng sai cách. Dù gọi từ luồng nền, `invokeAndWait` vẫn có nguy cơ deadlock nếu luồng gọi đang giữ khóa mà EDT cần lấy. Trong luồng ứng dụng thông thường, **ưu tiên `invokeLater` hoặc `SwingWorker`** hơn đợi đồng bộ.

Một lỗi kín đáo là đặt tính toán nặng bên trong `invokeLater`:

```java
// Sai về độ phản hồi: toàn bộ công việc chậm vẫn chạy trên EDT.
SwingUtilities.invokeLater(() -> {
    verySlowOperation();
    statusLabel.setText("Xong");
});
```

`invokeLater` chỉ **thay đổi luồng thực thi**, không biến `verySlowOperation()` thành tác vụ nền. Cần thực hiện tính toán ở worker rồi chỉ cập nhật `statusLabel` trên EDT.

## 5. Đưa tác vụ chậm sang `SwingWorker`

`SwingWorker<T, V>` là lựa chọn chuẩn, vẫn được hỗ trợ, khi có một tác vụ nền gắn với giao diện Swing:

- `T`: kiểu dữ liệu trả về cuối cùng của `doInBackground()`.
- `V`: kiểu dữ liệu trung gian gửi qua `publish(...)` để `process(List<V>)` xử lý trên EDT.
- `doInBackground()` chạy trên **worker thread**, thích hợp cho tác vụ chậm; không truy cập hoặc sửa component Swing ở đây.
- `process(...)` chạy trên **EDT**, dùng để cập nhật dần trạng thái, danh sách hoặc tiến độ.
- `done()` chạy trên **EDT** khi worker hoàn tất, thất bại hoặc được hủy; cập nhật trạng thái cuối và nhận kết quả bằng `get()`.
- `execute()` kích hoạt tác vụ một lần; **một instance `SwingWorker` chỉ được thực thi một lần**. Muốn làm lại, tạo instance mới.

Không gọi `worker.get()` từ EDT trong lúc worker còn chạy: `get()` sẽ **chặn EDT**. Gọi `get()` trong `done()` để nhận kết quả là mẫu hợp lý vì khi `done` được gọi worker đã kết thúc; vẫn phải xử lý `ExecutionException`, `InterruptedException` và `CancellationException`.

`publish(...)`/`process(...)` có thể **gộp nhiều lần publish thành một lần gọi process**: `process` nhận một `List<V>` và không được giả định cứ một bước tính toán thì có chính xác một callback. Khi chỉ hiển thị tiến độ gần nhất, dùng phần tử cuối của danh sách; khi cần hiển thị đầy đủ mọi bản ghi, xử lý cả danh sách theo thứ tự.

Ngoài `publish`, `SwingWorker.setProgress(int)` (giá trị 0–100) gửi sự kiện property change `"progress"`; listener thường được thông báo trên EDT. Các sự kiện tiến độ cũng có thể được gộp. Không dựa vào từng số phần trăm để thực hiện nghiệp vụ quan trọng.

### Chụp đầu vào trước khi chạy nền

Handler trên EDT nên đọc thông tin cần thiết từ component **trước khi** khởi chạy worker:

```java
// Đoạn minh họa trong ActionListener (đang chạy trên EDT).
String keyword = searchField.getText();
searchButton.setEnabled(false);
// Sau đó truyền "keyword" (snapshot String) cho tác vụ nền.
```

Worker dùng `keyword` thay vì liên tục gọi `searchField.getText()` ngoài EDT. Nếu dữ liệu đầu vào là một danh sách/model có thể thay đổi, tạo bản sao không thay đổi hoặc hợp đồng đồng bộ phù hợp rồi mới giao cho worker. Khi worker hoàn thành, xác minh kết quả còn thuộc yêu cầu hiện tại nếu người dùng đã đổi lựa chọn, chuyển màn hình hoặc đóng cửa sổ.

## 6. Ví dụ độc lập Java 17+: giao diện vẫn phản hồi trong lúc xử lý

Ví dụ sau hiển thị:

- **Bắt đầu:** thực hiện tác vụ 5 bước trên `SwingWorker`, mỗi bước mất khoảng 300 ms; trong `doInBackground` không cập nhật Swing.
- **Bấm thử:** tăng bộ đếm click trên EDT, để kiểm tra cửa sổ có còn phản hồi khi tác vụ nền đang chạy.
- **Hủy:** gửi yêu cầu hủy bằng `cancel(true)`; worker hợp tác dừng khi được ngắt và `done` phục hồi trạng thái nút.
- Thanh tiến độ: `publish(...)` gửi số phần trăm; `process(...)` cập nhật `JProgressBar` trên EDT.
- Khi xong: `done()` gọi `get()`, hiển thị kết quả hoặc lỗi và cho phép bắt đầu lượt mới.

Lưu thành **`SwingEdtDemo.java`**:

```java
import java.awt.BorderLayout;
import java.awt.FlowLayout;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.util.List;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.SwingUtilities;
import javax.swing.SwingWorker;

public final class SwingEdtDemo {
    private final JFrame frame = new JFrame("Swing EDT demo");
    private final JLabel status = new JLabel("Sẵn sàng");
    private final JLabel counter = new JLabel("Clicks: 0");
    private final JButton start = new JButton("Bắt đầu");
    private final JButton cancel = new JButton("Hủy");
    private final JButton click = new JButton("Bấm thử");
    private final JProgressBar progress = new JProgressBar(0, 100);

    private SwingWorker<Integer, Integer> current;
    private int clicks;

    private static void requireEdt() {
        if (!SwingUtilities.isEventDispatchThread()) {
            throw new IllegalStateException("UI access outside EDT");
        }
    }

    private void showWindow() {
        requireEdt();
        cancel.setEnabled(false);
        progress.setStringPainted(true);

        start.addActionListener(event -> startWork());
        cancel.addActionListener(event -> {
            if (current != null && !current.isDone()) {
                current.cancel(true);
            }
        });
        click.addActionListener(event -> {
            clicks++;
            counter.setText("Clicks: " + clicks);
        });

        JPanel controls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        controls.add(start);
        controls.add(cancel);
        controls.add(click);
        controls.add(counter);

        JPanel content = new JPanel(new BorderLayout(10, 10));
        content.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12));
        content.add(status, BorderLayout.NORTH);
        content.add(progress, BorderLayout.CENTER);
        content.add(controls, BorderLayout.SOUTH);

        frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
        frame.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosed(WindowEvent event) {
                if (current != null && !current.isDone()) {
                    current.cancel(true);
                }
            }
        });
        frame.setContentPane(content);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    private void startWork() {
        requireEdt();
        if (current != null && !current.isDone()) {
            return;
        }

        start.setEnabled(false);
        cancel.setEnabled(true);
        progress.setValue(0);
        status.setText("Đang xử lý...");

        current = new SwingWorker<>() {
            @Override
            protected Integer doInBackground() throws Exception {
                int sum = 0;
                for (int step = 1; step <= 5; step++) {
                    if (isCancelled()) {
                        return sum;
                    }
                    Thread.sleep(300); // Giả lập I/O chậm, CHỈ ở worker thread.
                    sum += step;
                    publish(step * 20);
                }
                return sum;
            }

            @Override
            protected void process(List<Integer> values) {
                requireEdt();
                if (!isCancelled()) {
                    progress.setValue(values.get(values.size() - 1));
                }
            }

            @Override
            protected void done() {
                requireEdt();
                start.setEnabled(true);
                cancel.setEnabled(false);

                try {
                    // done() chỉ chạy sau khi worker kết thúc, không đợi dài.
                    int result = get();
                    progress.setValue(100);
                    status.setText("Hoàn tất, tổng = " + result);
                } catch (CancellationException ex) {
                    status.setText("Đã hủy");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    status.setText("Gián đoạn khi nhận kết quả");
                } catch (ExecutionException ex) {
                    status.setText("Lỗi: "
                            + ex.getCause().getClass().getSimpleName());
                }
            }
        };
        current.execute();
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new SwingEdtDemo().showWindow());
    }
}
```

Biên dịch và chạy bằng **Java 17 trở lên**, trên máy có giao diện đồ họa:

```bash
javac -encoding UTF-8 SwingEdtDemo.java
java SwingEdtDemo
```

**Quan sát trực tiếp:** cửa sổ ban đầu có “Sẵn sàng”, thanh tiến độ 0% và nút “Hủy” bị vô hiệu hóa. Khi bấm “Bắt đầu”, nhãn hiển thị “Đang xử lý...”, thanh tiến độ tăng và nút “Bấm thử” vẫn cho phép tăng `Clicks`. Nếu không hủy và không có lỗi, sau khoảng 1,5 giây nhãn sẽ là **“Hoàn tất, tổng = 15”**, thanh tiến độ 100%; “Bắt đầu” được bật lại. Nếu bấm “Hủy”, nhãn chuyển sang **“Đã hủy”** khi `done` chạy. Chương trình không chủ động ghi gì ra stdout.

Mã có thể biên dịch với API Swing công khai; điều kiện chạy là JDK 17+ và môi trường desktop không headless. Khoảng thời gian chỉ là ước lượng: thread scheduling và tải hệ thống khiến thời điểm cập nhật UI không bảo đảm chính xác.

### Vì sao ví dụ giữ đúng luồng?

1. `main` chỉ đặt một runnable trên EDT; toàn bộ `JFrame` và component được tạo trong `showWindow()` trên EDT.
2. Các listener của Swing thực hiện rất ít việc: đổi trạng thái nút, tăng bộ đếm, tạo worker hoặc yêu cầu hủy.
3. `Thread.sleep(300)` nằm trong `doInBackground()`, **không chạy trên EDT**.
4. `publish(...)` chỉ gửi dữ liệu trung gian; `process(...)` mới sửa `JProgressBar` trên EDT.
5. `done()` chạy trên EDT và phục hồi điều khiển kể cả khi tác vụ lỗi/hủy; `get()` ở đây lấy kết quả đã hoàn tất.
6. Nhấn “Bắt đầu” lần nữa tạo một `SwingWorker` **mới**, vì worker cũ không được `execute()` lại.
7. Khi cửa sổ đóng, `cancel(true)` là yêu cầu hủy để worker có cơ hội dừng; trong ví dụ `Thread.sleep` phản ứng với interruption. Một tác vụ I/O thực có thể cần timeout hoặc cơ chế đóng socket/stream riêng.

### Cảnh báo thực tế về `cancel(true)`

`cancel(true)` đánh dấu tác vụ là canceled và **yêu cầu interrupt** luồng nếu tác vụ đang chạy; nó không bảo đảm lập tức chấm dứt mọi lời gọi I/O hay mọi phép tính. Công việc nền cần hợp tác: kiểm tra `isCancelled()`, chú ý `InterruptedException`, giới hạn timeout và đóng tài nguyên thích hợp. `done()` vẫn chạy và `get()` sẽ ném `CancellationException` đối với worker đã được hủy. Không dùng `Thread.stop()` để buộc dừng tác vụ.

## 7. Ví dụ đối chiếu: code khiến giao diện bị treo

Trong một handler nút, đây là hai lỗi điển hình:

```java
// Sai: listener thông thường chạy trên EDT.
button.addActionListener(event -> {
    Thread.sleep(2000); // Chưa xử lý checked exception; vừa sai luồng.
    label.setText("Xong");
});
```

Đây là **mảnh mã cố ý sai** để minh họa lỗi; lời gọi `sleep` còn cần xử lý `InterruptedException` để biên dịch. Kể cả khi bọc try/catch, tác vụ vẫn khóa EDT suốt khoảng 2 giây.

```java
// Sai dù worker có thực thi nền: get() ở EDT đợi cho đến khi xong.
button.addActionListener(event -> {
    SwingWorker<String, Void> worker = makeWorker();
    worker.execute();
    String result = worker.get(); // Checked exceptions + khóa EDT.
    label.setText(result);
});
```

Đây cũng là **mảnh mã minh họa lỗi**; `makeWorker` và biến UI giả định có sẵn, `get` phải xử lý ngoại lệ. Sửa đúng bằng cách nhận kết quả ở `done()` hoặc callback được chuyển về EDT.

Một lỗi khác là tự tạo `new Thread(() -> label.setText("Xong")).start()`. Cách này đưa việc sửa component lên luồng nền, vi phạm nguyên tắc luồng Swing. Nếu cần thread nền ngoài `SwingWorker`, hãy làm việc nặng ở đó rồi dùng `SwingUtilities.invokeLater(() -> label.setText(...))` cho phần UI.

## 8. `javax.swing.Timer` có thay được `SwingWorker` không?

`javax.swing.Timer` là API đang được hỗ trợ để phát sự kiện theo lịch. `ActionListener` của Swing Timer chạy trên **EDT**, phù hợp với tác vụ giao diện rất ngắn như cập nhật đồng hồ, nhấp nháy con trỏ hoặc kiểm tra thời điểm cần vẽ lại. Nó **không phải luồng xử lý nặng**.

Ví dụ minh họa trong một đối tượng UI được tạo trên EDT:

```java
javax.swing.Timer timer = new javax.swing.Timer(1000, event -> {
    clockLabel.setText(java.time.LocalTime.now().toString());
});
timer.start();
```

Đây là **mảnh mã**, giả định `clockLabel` đã tồn tại trên EDT. Callback cập nhật label rất nhanh nên phù hợp; nếu thay bằng truy vấn mạng hoặc `Thread.sleep`, Timer sẽ làm EDT đứng hình tương tự listener của nút.

Phân biệt `javax.swing.Timer` và `java.util.Timer`: callback `java.util.Timer` chạy trên luồng Timer, **không mặc nhiên là EDT**, nên không được sửa trực tiếp component Swing ở đó. Trong bài toán chỉ cập nhật UI theo thời gian, Swing Timer thường đơn giản hơn.

| Nhu cầu | Giải pháp thường dùng |
| --- | --- |
| Phản hồi click, thay đổi label hoặc model ngay | Thực hiện ngắn gọn trên EDT |
| Mở cửa sổ từ `main`/luồng khác | `SwingUtilities.invokeLater` |
| Tải file / I/O / tính toán dài, rồi cập nhật UI | `SwingWorker`, trả kết quả qua `process`/`done` |
| Công việc nền do `ExecutorService` quản lý | Làm việc trong executor, gửi kết quả UI qua `invokeLater` |
| Cập nhật đồng hồ UI định kỳ, callback rất ngắn | `javax.swing.Timer` |
| Bắt buộc đồng bộ với một công việc rất ngắn trên EDT từ luồng khác | Cân nhắc `invokeAndWait`, kiểm tra deadlock và tuyệt đối không gọi trên EDT |

## 9. Đồng bộ dữ liệu giữa worker và giao diện

Việc “chỉ sửa component trên EDT” còn liên quan tới **dữ liệu mà component hiển thị**:

- Không chia sẻ một `ArrayList` hoặc object mutable cho EDT và worker cùng cập nhật mà thiếu giao thức đồng bộ. Ưu tiên dữ liệu bất biến hoặc bản sao chuyển giao theo từng lần cập nhật.
- Khi hiển thị kết quả truy vấn, worker có thể trả dữ liệu dạng immutable `List.copyOf(...)`; `done()` trên EDT quyết định cách thêm vào `DefaultListModel` hoặc `DefaultTableModel`. Thông thường hãy sửa các Swing model được UI sử dụng trên EDT.
- Giữ thao tác EDT đủ ngắn: ngay cả khi cập nhật UI “đúng luồng”, thêm hàng trăm nghìn bản ghi vào `JTable` trong một callback vẫn có thể khiến giao diện tạm treo. Cân nhắc phân trang, cập nhật theo lô có kiểm soát hoặc mô hình dữ liệu hiệu quả.
- Nếu người dùng bắt đầu yêu cầu A rồi B, kết quả A có thể tới muộn hơn B. Dùng mã yêu cầu/generation id, cancellation hoặc điều kiện xác nhận kết quả còn phù hợp trước khi hiển thị. Không để kết quả cũ âm thầm ghi đè màn hình mới.
- `SwingWorker` có cơ chế trao đổi kết quả đã hoàn thành, nhưng điều đó **không làm cho mọi object dùng chung tự nhiên trở nên thread-safe**. Không truyền reference tới component để worker tự sửa nó.

Một mẫu thiết kế dễ bảo trì là phân biệt rõ ba bước: **đọc input trên EDT → tính toán/I/O bằng dữ liệu đã chụp ở worker → áp dụng kết quả trên EDT**. Các thành phần giao diện có thể còn sống hoặc đã đóng khi kết quả về; kiểm tra vòng đời cửa sổ nếu kết quả được giao từ một executor dài hạn.

## 10. Xử lý lỗi, đóng cửa sổ và giữ UX ổn định

Tác vụ nền có thể thất bại do lỗi mạng, file không tồn tại, timeout hoặc dữ liệu sai. Nếu chỉ bật lại nút trong nhánh thành công, UI sẽ kẹt ở trạng thái “Đang xử lý”. Vì vậy, đặt phần **khôi phục trạng thái điều khiển** vào `done()` hoặc khối hoàn tất tương đương.

- `ExecutionException` từ `get()` bao lấy lỗi do `doInBackground` ném ra. Dùng `getCause()` để xem nguyên nhân; không hiển thị stack trace hoặc dữ liệu nhạy cảm cho người dùng cuối.
- `CancellationException` là nhánh bình thường khi người dùng hủy; không nhầm với lỗi máy chủ.
- `InterruptedException` trong worker nên được tôn trọng: truyền lên, đặt lại trạng thái interrupt khi thích hợp, dừng việc còn lại và dọn tài nguyên.
- `done()` chạy trên EDT nên tránh thực hiện logging nặng, tải dữ liệu bổ sung, gửi request hoặc gọi phương thức có thể chặn.
- Khi đóng cửa sổ, dừng các Timer liên quan, yêu cầu hủy worker hoặc giải phóng các subscription/callback còn giữ tham chiếu UI. Với công việc được chia sẻ giữa nhiều màn hình, chỉ hủy nếu màn hình thực sự sở hữu tác vụ.
- Không dùng `System.exit(...)` như cách mặc định giải quyết một worker còn chạy. Thiết kế quyền sở hữu và vòng đời của task rõ ràng sẽ dễ xử lý hơn.

### Giữ ngắn các callback của Swing

Ngay cả khi thuật toán tính toán chạy trong `doInBackground`, các callback `process` và `done` có thể gây nghẽn nếu thao tác quá nhiều component hoặc thực hiện vòng lặp lớn. Hãy chuyển những phần có thể tính trước ra worker; trên EDT chỉ áp dụng kết quả đã sẵn sàng, số lượng thay đổi vừa đủ.

Thành phần dài hạn như `ExecutorService` do ứng dụng sở hữu nên được shutdown theo vòng đời ứng dụng. Không tạo một executor mới không giới hạn cho mỗi lần bấm nút rồi bỏ quên; nếu dùng `SwingWorker`, cũng không tạo vô hạn worker đồng thời theo cùng một sự kiện.

## 11. Cách kiểm thử đúng EDT và tính phản hồi

### Kiểm thử hành vi

1. Mở ứng dụng và bấm “Bắt đầu”; trong lúc tiến độ tăng, liên tục bấm “Bấm thử”. **Bộ đếm vẫn tăng** chứng tỏ EDT đang nhận sự kiện.
2. Bấm “Hủy”; kiểm tra UI phục hồi nút và có trạng thái hủy. Bấm “Bắt đầu” lại để chắc chắn tạo worker mới.
3. Thử tác vụ nền gây `IOException` hoặc lỗi có kiểm soát; xác minh `done` phục hồi UI, hiển thị lỗi an toàn và không để nút bị khóa.
4. Thử xử lý công việc chậm hơn bình thường, network timeout, cửa sổ bị đóng sớm, click liên tục nhiều lần.
5. Dùng log có tên luồng hoặc `SwingUtilities.isEventDispatchThread()` tại các điểm quan trọng để xác nhận `doInBackground` không chạy trên EDT và `process`/`done` có chạy trên EDT.

### Kiểm thử kỹ thuật

- Với test trên môi trường có GUI, có thể tạo và đọc trạng thái Swing trong `SwingUtilities.invokeAndWait(...)` **từ test thread khác EDT**, nhưng cần bảo đảm test không chờ worker bằng cách chặn EDT.
- Trên CI headless, có thể kiểm thử phần nghiệp vụ của worker tách khỏi UI. Test hiển thị Swing cần môi trường đồ họa hoặc giải pháp kiểm thử UI phù hợp.
- Không dùng giả định thời gian cố định để chứng minh EDT đúng. Máy chậm/nhanh khác nhau; nên đồng bộ test theo sự kiện hoặc trạng thái hoàn tất và timeout hợp lý.
- Khi debug, kiểm tra thread dump nếu ứng dụng treo: EDT có thể đang chờ `Future.get()`, khóa đồng bộ, I/O hoặc công việc tính toán dài. Xử lý nguồn chặn thay vì chỉ thêm `repaint()`.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Tạo `JFrame` và thao tác component tùy ý trong `main` | Có thể xảy ra sai luồng | Khởi tạo Swing qua `invokeLater` |
| Gọi I/O, `Thread.sleep` hoặc tính toán nặng trong `actionPerformed` | UI đứng hình, chậm repaint | Chuyển sang `SwingWorker.doInBackground` |
| Dùng `invokeLater` để chạy vòng lặp chậm | Vẫn khóa EDT | Chỉ gửi phần cập nhật UI, giữ tính toán ở worker |
| Chỉnh `JLabel`/`JTable` từ thread nền | Race, hiện thị không nhất quán | Dùng `process`/`done` hoặc `invokeLater` |
| `worker.get()` khi worker đang chạy trên EDT | Khóa giao diện | Nhận kết quả trong `done` |
| Tái sử dụng một `SwingWorker` cho nhiều lần click | Không chạy lại theo kỳ vọng | Tạo worker mới mỗi lượt |
| Xử lý mỗi `publish` như sự kiện UI riêng lẻ | Thiếu hoặc gộp lần cập nhật | Xử lý toàn bộ `List<V>` nhận ở `process` |
| Sửa Swing model đồng thời từ worker | Data race giữa model/UI | Chụp dữ liệu và cập nhật model trên EDT |
| Dùng `javax.swing.Timer` cho xử lý nặng | Timer callback làm treo EDT | Timer chỉ xử lý ngắn; chuyển việc chậm sang worker |
| Dùng `invokeAndWait` khi đang ở EDT | Gọi bất hợp lệ, có nguy cơ khóa | Gọi trực tiếp nếu đã ở EDT; async thì `invokeLater` |
| Hủy task nhưng không xử lý `CancellationException` | UI báo lỗi sai hoặc không phục hồi | Xử lý hủy trong `done`, worker hợp tác với interrupt |
| Kết quả yêu cầu cũ về sau yêu cầu mới | Màn hình hiển thị dữ liệu lỗi thời | Gắn generation id, kiểm tra trạng thái trước áp dụng |

## 13. Tự kiểm tra nhanh

**Tình huống A.** Một nút “Tải báo cáo” gọi HTTP mất 4 giây. Nút phải đổi trạng thái và ứng dụng vẫn cho người dùng tương tác.  
**Cách làm:** đọc tham số trên EDT; vô hiệu hóa nút “Tải” trên EDT; chạy HTTP trong `doInBackground` với timeout; hiển thị tiến độ nếu có; dùng `done` để cập nhật UI, bật lại nút và xử lý lỗi.

**Tình huống B.** Luồng nền vừa phân tích ảnh xong và muốn đưa kết quả lên `JLabel`.  
**Cách làm:** xử lý pixel ở worker; chuyển đối tượng kết quả qua `done` hoặc `SwingUtilities.invokeLater`; sửa `JLabel` trên EDT. Không gọi `label.setIcon(...)` trực tiếp trong luồng nền.

**Tình huống C.** Mỗi giây cập nhật nhãn đồng hồ trên cửa sổ, không có việc chậm.  
**Cách làm:** `javax.swing.Timer` với listener ngắn chạy trên EDT. Dừng Timer khi màn hình không còn dùng nó.

**Tình huống D.** Từ một luồng nền, cần chắc chắn EDT đã thực hiện một cập nhật rất nhỏ trước khi tiếp tục.  
**Cách làm:** có thể dùng `invokeAndWait` nếu thật sự cần đồng bộ, luồng gọi không phải EDT và không giữ khóa gây deadlock; còn nếu chỉ muốn thông báo kết quả, `invokeLater` thuận tiện hơn.

## 14. Tài liệu API chính thức

- [`SwingUtilities` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingUtilities.html): `invokeLater`, `invokeAndWait`, `isEventDispatchThread`.
- [`SwingWorker` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingWorker.html): `doInBackground`, `publish`/`process`, `done`, `setProgress`, `cancel`, `get`.
- [`EventQueue` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/EventQueue.html): event queue và điều phối sự kiện AWT/Swing.
- [`javax.swing.Timer` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/Timer.html): callback định kỳ trên EDT.
- [`JComponent` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/JComponent.html): quy tắc sử dụng và các ngoại lệ thread-safe được tài liệu hóa.

**Nguyên tắc áp dụng:** *UI trên EDT, việc nặng ở nền, kết quả quay về EDT*. Bất cứ khi nào viết handler Swing, hãy tự hỏi: “Code này sẽ chạy bao lâu, có đang đợi I/O hoặc khóa không, và mọi thay đổi component có nằm trên EDT không?”
