# Giữ cập nhật AWT và Swing trên luồng sự kiện (Event Dispatch Thread)

## 1. Vì sao giao diện Java cần một luồng chuyên xử lý sự kiện?

Trong ứng dụng desktop Java dùng AWT/Swing, phần lớn thao tác liên quan đến **cây component, trạng thái hiển thị, model gắn với component, phản hồi chuột/bàn phím, bố cục và vẽ lại** phải được thực hiện trên **Event Dispatch Thread (EDT)**, tức luồng phân phối sự kiện của AWT.

Quy tắc được tài liệu `javax.swing` của Java hiện đại nhấn mạnh: **Swing nói chung không thread-safe; trừ API được ghi rõ hỗ trợ thread-safe, mọi thao tác truy cập component và đối tượng Swing liên quan cần chạy trên EDT.** Việc mã chạy được trong thử nghiệm không bảo đảm an toàn nếu cập nhật component từ background thread.

AWT EventQueue xếp các tác vụ/sự kiện để EDT xử lý lần lượt:

~~~text
Nguồn sự kiện: nhấn nút, chuột, bàn phím, gọi từ background thread
                              │
                              v
                    AWT EventQueue
                              │
                        xử lý lần lượt
                              v
            Event Dispatch Thread (EDT)
       ┌───────────────────────────────────┐
       │ ActionListener / Swing Timer      │
       │ Cập nhật JLabel, JTable, JButton  │
       │ Cập nhật model và yêu cầu repaint │
       └───────────────────────────────────┘
                              │
                 giao tác vụ dài qua worker
                              v
                  Background thread(s)
              I/O, đọc dữ liệu, tính toán
                              │
              chuyển kết quả trở lại EDT
~~~

Khi EDT đang xử lý một `ActionListener` hoặc một `Runnable` dài, nó không thể tiếp tục phân phối các sự kiện tiếp theo. Hậu quả thường thấy là cửa sổ đứng hình, nút không phản hồi, trạng thái tiến độ không vẽ được hoặc thao tác đóng cửa sổ chậm.

**Phạm vi áp dụng:** Quy tắc EDT vẫn có hiệu lực trong Java 17, 21, 25 và các phiên bản hiện hành; nó không phải kiến thức chỉ dùng với Java 9. Từ hệ module Java 9, mã Java GUI nằm trong module chuẩn `java.desktop`. Một named module có thể cần:

~~~java
module demo.desktop {
    requires java.desktop;
}
~~~

Đây là ví dụ `module-info.java` dành cho dự án modular; nó không cần thiết nếu chạy chương trình đơn giản bằng classpath như các ví dụ phía dưới.

## 2. Quy tắc sở hữu dữ liệu: tính toán ở nền, đụng UI trên EDT

Phân biệt ba nhóm công việc.

| Công việc | Luồng phù hợp | Lý do |
| --- | --- | --- |
| Khởi tạo và hiện `JFrame`, gắn listener, cấu hình component | EDT | Cây UI thuộc Swing, vốn không thread-safe. |
| Cập nhật `JLabel.setText`, `JButton.setEnabled`, `JProgressBar.setValue` | EDT | Tránh tranh chấp trạng thái giao diện. |
| Thêm dòng vào `DefaultTableModel` đang gắn với `JTable`, phát sự kiện model | EDT | Các listener Swing có thể nhận thông báo và lập tức đổi giao diện. |
| Vẽ đồ họa trong `paintComponent(Graphics)` | Theo chu trình painting của Swing | Không tự khởi chạy việc vẽ trực tiếp từ worker. |
| Query database, HTTP request, đọc tệp lớn, nén, giải mã, tính toán dài | Background thread | Không khóa EDT, cho UI tiếp tục phản hồi. |
| Hiển thị kết quả từ worker | Quay lại EDT | Trạng thái component được sửa tại đúng nơi sở hữu. |
| Kiểm tra trạng thái đơn giản, thay chữ sau một click | EDT | Tác vụ rất ngắn nên không cần mở background thread. |

Nguyên tắc dễ nhớ: **EDT giữ trạng thái UI; worker giữ công việc nặng; kết quả được bàn giao qua hàng đợi/callback có ranh giới rõ ràng.**

Các method có contract thread-safe riêng (ví dụ một số lời gọi `repaint`) là ngoại lệ ở phạm vi method ấy; chúng **không** làm cho mọi setter, model và logic Swing tự động thread-safe. Không tự kết luận một method an toàn chỉ vì tên của nó bắt đầu bằng `get`.

## 3. Tạo giao diện đúng luồng ngay từ `main`

Luồng chạy phương thức `main` không mặc nhiên là EDT. Chuyển quyền tạo/hiện giao diện bằng `SwingUtilities.invokeLater` hoặc `EventQueue.invokeLater`.

~~~java
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public final class HelloEdt {
    private static void createAndShow() {
        JFrame frame = new JFrame("EDT");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.add(new JLabel("Giao diện được tạo trên EDT"));
        frame.setSize(360, 120);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(HelloEdt::createAndShow);
    }
}
~~~

Lưu thành `HelloEdt.java`; trong môi trường máy tính có desktop/GUI:

~~~bash
javac -encoding UTF-8 HelloEdt.java
java HelloEdt
~~~

Kết quả là một cửa sổ Swing có nhãn. Không có stdout. Đây là **chương trình GUI**: trên server/container chạy headless, việc tạo `JFrame` có thể gây `HeadlessException`. Headless không có nghĩa EDT không tồn tại; các thành phần Swing nhẹ và luồng sự kiện vẫn có thể được dùng để kiểm tra cách bàn giao công việc.

Tương đương nếu chọn API AWT:

~~~java
java.awt.EventQueue.invokeLater(HelloEdt::createAndShow);
~~~

Chỉ dùng đoạn này thay cho lời gọi trong `main`; nó không phải một chương trình độc lập khác.

## 4. `invokeLater`, `invokeAndWait` và kiểm tra luồng

### 4.1. `SwingUtilities.invokeLater(Runnable)`: đưa một tác vụ ngắn vào EDT

~~~java
// Đặt trong callback đã nhận được kết quả từ background thread.
String finalText = "Đã tải xong";
SwingUtilities.invokeLater(() -> statusLabel.setText(finalText));
~~~

Đoạn trên giả sử `statusLabel` đã được tạo trên EDT và đối tượng vẫn còn hợp lệ khi callback chạy. `finalText` là một giá trị bất biến được bàn giao qua lời gọi; không chia sẻ trực tiếp một buffer đang bị worker sửa liên tục.

- `invokeLater` có thể gọi từ mọi thread. Nó **xếp hàng bất đồng bộ**, không đợi UI được cập nhật.
- Nếu gọi khi đang ở EDT, `Runnable` vẫn được xếp cho lượt xử lý về sau; không chạy ngay tại chỗ. Điều này có ích khi cần chờ listener/model hiện tại kết thúc trước khi đổi UI lần nữa.
- Các nhiệm vụ được chuyển lên EDT nên ngắn. Đưa một vòng lặp nặng vào `invokeLater` vẫn làm ứng dụng đứng hình.
- Nếu `Runnable` ném exception không bắt, exception xảy ra trên EDT; thread gửi yêu cầu không tự nhận exception đó như một kết quả đồng bộ.

Không nên rải hàng nghìn `invokeLater` để báo từng byte hoặc từng phần trăm cực nhỏ. Hãy gộp tiến độ và giới hạn tần suất thông báo để EDT không bị ngập sự kiện.

### 4.2. `SwingUtilities.invokeAndWait(Runnable)`: đợi cho một tác vụ EDT kết thúc

~~~java
// Đoạn minh họa chạy từ một thread KHÁC EDT.
SwingUtilities.invokeAndWait(() -> statusLabel.setText("Sẵn sàng"));
// Thread gọi chỉ tiếp tục sau khi runnable trên EDT hoàn tất.
~~~

Phương thức này có thể ném `InterruptedException` và `InvocationTargetException`; code thực tế phải xử lý hoặc khai báo `throws` phù hợp. Nó **chặn thread gọi** cho đến khi EDT chạy xong tác vụ. Không gọi từ EDT: AWT `EventQueue.invokeAndWait` sẽ báo lỗi vì EDT không thể tự đợi chính mình. Cũng tránh dùng khi giữ lock mà EDT đang chờ, vì rất dễ gây deadlock.

Đối với cập nhật giao diện thông thường, `invokeLater` hoặc `SwingWorker` thường phù hợp hơn. `invokeAndWait` nên dành cho điểm tích hợp thực sự cần kết quả đồng bộ, ví dụ một test hoặc quá trình khởi tạo từ thread không phải EDT.

### 4.3. Kiểm tra quyền truy cập EDT

~~~java
if (!SwingUtilities.isEventDispatchThread()) {
    throw new IllegalStateException("UI update must run on EDT");
}
statusLabel.setText("Đang hiển thị");
~~~

Trong AWT, có thể dùng `EventQueue.isDispatchThread()` tương đương theo bối cảnh event queue. Đoạn kiểm tra trên **chỉ minh họa** và yêu cầu biến `statusLabel` từ giao diện đã tạo.

Một helper giao diện nếu được thiết kế để chấp nhận lời gọi từ nhiều thread có thể phân luồng minh bạch:

~~~java
static void onEdt(Runnable action) {
    if (SwingUtilities.isEventDispatchThread()) {
        action.run();
    } else {
        SwingUtilities.invokeLater(action);
    }
}
~~~

Chú ý helper này có **hành vi thời gian khác nhau**: trên EDT chạy ngay, từ worker thì chạy sau. Chỉ dùng khi contract của helper cho phép như vậy; nếu muốn luôn trì hoãn tới lượt xử lý tiếp theo, gọi `invokeLater` trực tiếp.

## 5. Vì sao UI bị treo dù mọi setter đều chạy trên EDT?

Đưa mọi thứ lên EDT là điều kiện **cần**, chưa phải điều kiện **đủ**. EDT phải được trả về nhanh sau mỗi event.

Ví dụ **sai**:

~~~java
// Đoạn minh họa nằm trong JButton ActionListener (vốn chạy trên EDT).
button.addActionListener(event -> {
    // SAI: giả lập một API chậm/đợi ngay trên EDT.
    try {
        Thread.sleep(3_000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
    statusLabel.setText("Xong");
});
~~~

Trong ba giây, nút, menu, repaint và input mới không được xử lý bình thường; người dùng thấy UI đứng. `SwingUtilities.invokeLater` bao lấy cả đoạn này **không sửa được vấn đề** vì nó vẫn chạy trên EDT.

Những nguyên nhân tương tự: gọi HTTP đồng bộ, đọc tập tin lớn, `Future.get()` để đợi worker, `Thread.join()`, `CountDownLatch.await()`, lấy database lock, chạy thuật toán tốn CPU hoặc dùng một `synchronized` block đang đợi thread khác.

Cách giải quyết là để worker xử lý phần tốn thời gian, sau đó cập nhật phần giao diện gọn trong `process`/`done` (mục 6).

## 6. Ví dụ GUI đầy đủ với `SwingWorker`: giao việc nền, cập nhật trên EDT

`javax.swing.SwingWorker<T,V>` giúp xử lý một tác vụ có thời lượng đáng kể và đưa trạng thái trở lại UI.

| Method | Luồng chạy | Cách dùng |
| --- | --- | --- |
| `execute()` | Thường được gọi từ EDT; lên lịch xử lý rồi trả về ngay | Khởi động đúng một lần cho một instance `SwingWorker`. |
| `doInBackground()` | Worker thread | Thực hiện I/O, tính toán, tạo kết quả `T`; **không truy cập component Swing**. |
| `publish(V...)` | Gọi từ worker | Gửi các bản cập nhật trung gian; SwingWorker có thể gộp nhiều lần gửi. |
| `process(List<V>)` | EDT | Nhận danh sách phần tử đã gửi, cập nhật label/progress/model. |
| `setProgress(int)` | Có thể gọi từ worker với 0–100 | Phát bound property `progress`; listener được giao về EDT; thay đổi có thể được gộp. |
| `done()` | EDT | Lấy kết quả cuối, xử lý lỗi/hủy, bật lại nút, cập nhật trạng thái. |
| `get()` | Thread gọi bị chặn nếu task chưa xong | Không đợi bằng `get()` trong listener/EDT; trong `done()` tác vụ đã kết thúc nên có thể đọc kết quả và bắt ngoại lệ. |
| `cancel(true)` | Có thể gọi khi người dùng muốn hủy | Đánh dấu hủy và thử interrupt; công việc phải hợp tác để dừng, không bảo đảm mọi I/O tự kết thúc. |

### 6.1. Chương trình thực hành có nút Bắt đầu/Hủy

Lưu đúng tên `ProgressWindow.java`:

~~~java
import java.awt.BorderLayout;
import java.util.List;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.SwingUtilities;
import javax.swing.SwingWorker;

public final class ProgressWindow {
    private JButton startButton;
    private JButton cancelButton;
    private JLabel status;
    private JProgressBar progressBar;
    private SwingWorker<String, Integer> worker;

    private void createAndShow() {
        JFrame frame = new JFrame("Swing + EDT");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        startButton = new JButton("Bắt đầu");
        cancelButton = new JButton("Hủy");
        cancelButton.setEnabled(false);
        status = new JLabel("Sẵn sàng");
        progressBar = new JProgressBar(0, 100);
        progressBar.setStringPainted(true);

        startButton.addActionListener(e -> startWork());
        cancelButton.addActionListener(e -> {
            if (worker != null) {
                worker.cancel(true);
            }
        });

        JPanel controls = new JPanel();
        controls.add(startButton);
        controls.add(cancelButton);

        frame.add(status, BorderLayout.NORTH);
        frame.add(progressBar, BorderLayout.CENTER);
        frame.add(controls, BorderLayout.SOUTH);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    private void startWork() {
        startButton.setEnabled(false);
        cancelButton.setEnabled(true);
        progressBar.setValue(0);
        status.setText("Đang thực hiện");

        worker = new SwingWorker<>() {
            @Override
            protected String doInBackground() throws Exception {
                for (int value = 10; value <= 100; value += 10) {
                    if (isCancelled()) {
                        return "Đã hủy";
                    }
                    Thread.sleep(120);
                    publish(value);
                }
                return "Hoàn tất";
            }

            @Override
            protected void process(List<Integer> chunks) {
                progressBar.setValue(chunks.get(chunks.size() - 1));
            }

            @Override
            protected void done() {
                try {
                    status.setText(get());
                } catch (CancellationException e) {
                    status.setText("Đã hủy");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    status.setText("Bị gián đoạn");
                } catch (ExecutionException e) {
                    status.setText("Lỗi: "
                            + e.getCause().getClass().getSimpleName());
                } finally {
                    startButton.setEnabled(true);
                    cancelButton.setEnabled(false);
                }
            }
        };
        worker.execute();
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(
                () -> new ProgressWindow().createAndShow());
    }
}
~~~

Trên máy có GUI:

~~~bash
javac -encoding UTF-8 ProgressWindow.java
java ProgressWindow
~~~

Thao tác và kết quả quan sát được (không phải stdout):

1. Chạy chương trình, cửa sổ có nhãn “Sẵn sàng”, progress bar 0%, nút “Bắt đầu” và nút “Hủy” đang bị vô hiệu hóa.
2. Nhấn “Bắt đầu”. Nút Start bị khóa, nút Hủy bật. Worker chạy vòng lặp ngắn **trên background thread**; tiến độ được gửi qua `publish`.
3. `process` chạy trên EDT, lấy phần tử cuối của đợt cập nhật và đặt giá trị progress bar. Thanh tiến độ tăng dần, giao diện vẫn cho phép người dùng thao tác.
4. Khi xong, `done` chạy trên EDT, gọi `get()` để lấy chuỗi “Hoàn tất”, bật lại nút Start, tắt Hủy.
5. Nếu nhấn “Hủy”, `cancel(true)` yêu cầu dừng, `get()` trong `done` ném `CancellationException`; UI hiển thị “Đã hủy”. Tiến độ đã nhận trước đó có thể vẫn còn trên thanh; đó là phần việc đã báo, không phải phép đo tổng công việc đã hoàn thành.

**Vì sao chương trình đúng ranh giới thread?** Hàm `createAndShow` và các `ActionListener` chạy trên EDT. `doInBackground` không gọi `status.setText` hay `progressBar.setValue`, chỉ tính và `publish`. `process`/`done` là callback SwingWorker bảo đảm chạy trên EDT, nên đặt trạng thái UI ở đó.

`Thread.sleep(120)` trong ví dụ chỉ mô phỏng công việc dài ở **worker**, không phải cách làm hiệu quả cho một công việc thật. Hãy thay bằng logic tính toán/I/O có cơ chế timeout hoặc hủy phù hợp.

### 6.2. Các điểm cần chú ý trong một ứng dụng thực tế

- Một instance `SwingWorker` chỉ nên `execute()` **một lần**. Với lần tải tiếp theo, tạo worker mới; ví dụ làm vậy trong `startWork()`.
- `publish/process` có cơ chế **coalescing**: nhiều phần tử có thể được gộp trong một callback `process`. Chỉ dùng nó cho trạng thái có thể gộp (như phần trăm mới nhất), hoặc xử lý mọi phần tử nếu đó là dữ liệu bắt buộc.
- `setProgress` phù hợp khi muốn một giá trị 0–100 và đăng ký `PropertyChangeListener`. Listener của SwingWorker chạy trên EDT; vì thế có thể cập nhật `JProgressBar` ở đó.
- `cancel(true)` chỉ phát tín hiệu hủy và có thể interrupt; các tác vụ I/O không hỗ trợ interrupt vẫn cần timeout/đóng tài nguyên riêng. Không dùng `Thread.stop()` hoặc can thiệp cưỡng ép vào EDT.
- Khi worker có exception, `get()` ném `ExecutionException`; lỗi gốc ở `getCause()`. Không nuốt lỗi rồi hiển thị “thành công”.
- `done()` vẫn được gọi khi hủy; phân biệt `CancellationException` với lỗi thực thi. Không gọi `get()` từ EDT trước khi worker kết thúc vì UI sẽ bị khóa.
- Nếu màn hình bị đóng, cần chính sách hủy và bỏ qua callback muộn; không để một task cũ ghi đè kết quả của một task mới. Có thể dùng generation ID hoặc kiểm tra task hiện hành trước khi apply.
- Trong ví dụ các trường `worker` và widget chỉ được đọc/ghi bởi EDT; không cần tự thêm `volatile` cho mỗi component. Nếu trạng thái ứng dụng còn được truy cập ở worker thì phải dùng cơ chế bàn giao an toàn, immutable snapshot hoặc cấu trúc đồng bộ phù hợp.

## 7. Ví dụ kiểm chứng EDT không cần mở cửa sổ

Đây là chương trình độc lập có thể chạy trên máy headless. Nó tạo `JLabel` nhẹ trên EDT, chạy `doInBackground` ngoài EDT, sửa nhãn trong `done` trên EDT, rồi cho **main thread** (không phải EDT) đợi một `CountDownLatch`.

Lưu `EdtThreadCheck.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;
import javax.swing.SwingWorker;

public final class EdtThreadCheck {
    public static void main(String[] args) throws Exception {
        CountDownLatch finished = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        SwingUtilities.invokeAndWait(() -> {
            JLabel status = new JLabel("Đang chờ");
            SwingWorker<String, Void> worker = new SwingWorker<>() {
                @Override
                protected String doInBackground() {
                    if (SwingUtilities.isEventDispatchThread()) {
                        throw new IllegalStateException("Background ran on EDT");
                    }
                    return "Hoàn tất";
                }

                @Override
                protected void done() {
                    try {
                        if (!SwingUtilities.isEventDispatchThread()) {
                            throw new IllegalStateException("done() not on EDT");
                        }
                        status.setText(get());
                        System.out.println("Background outside EDT: true");
                        System.out.println("done on EDT: "
                                + SwingUtilities.isEventDispatchThread());
                        System.out.println("Label: " + status.getText());
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        failure.set(e);
                    } catch (ExecutionException | RuntimeException e) {
                        failure.set(e);
                    } finally {
                        finished.countDown();
                    }
                }
            };
            worker.execute();
        });

        if (!finished.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out");
        }
        if (failure.get() != null) {
            throw new AssertionError("Worker failed", failure.get());
        }
    }
}
~~~

Biên dịch và chạy (đặt chuỗi cấu hình hệ thống trong dấu nháy kép để lệnh tương thích cả PowerShell):

~~~bash
javac -encoding UTF-8 EdtThreadCheck.java
java "-Djava.awt.headless=true" EdtThreadCheck
~~~

Stdout chính xác trên Java 17+:

~~~text
Background outside EDT: true
done on EDT: true
Label: Hoàn tất
~~~

Có hai ranh giới cần lưu ý: `SwingUtilities.invokeAndWait` được **main thread** gọi và chờ EDT chạy khối khởi tạo; `CountDownLatch.await` cũng được main thread gọi. Không có lệnh chờ nào chặn EDT. `AtomicReference` là nơi truyền lỗi giữa callback EDT và thread kiểm thử để phép kiểm không báo thành công giả.

Đoạn test headless chỉ xác minh quy tắc thread và lifecycle. Nó không chứng minh bố cục, thao tác chuột hoặc painting của một cửa sổ thật; phần ấy phải thử trên desktop có môi trường đồ họa.

## 8. Cập nhật định kỳ: chọn đúng loại Timer

`javax.swing.Timer` phát `ActionEvent` tới listener **trên EDT**, phù hợp với tác vụ nhỏ như cập nhật đồng hồ, thay màu/nhãn hoặc hoạt ảnh UI đơn giản.

~~~java
// Đoạn minh họa trong method khởi tạo UI đang chạy trên EDT.
javax.swing.Timer timer = new javax.swing.Timer(1_000, e -> {
    clockLabel.setText(java.time.LocalTime.now().toString());
});
timer.start();
~~~

Đây là **đoạn minh họa** vì cần có biến `clockLabel` được tạo trong GUI. Khi không cần nữa, gọi `timer.stop()`, ví dụ lúc đóng màn hình.

Không nhầm `javax.swing.Timer` với `java.util.Timer` hoặc `java.util.concurrent.ScheduledExecutorService`: callback của hai lựa chọn sau không tự chạy trên EDT, nên phải chuyển kết quả sang EDT. Dù dùng `javax.swing.Timer`, callback vẫn phải chạy nhanh; dùng timer để gọi HTTP hoặc query DB sẽ làm giao diện đóng băng.

Đối với animation thường xuyên, xác định mức làm mới hợp lý; EDT không phải một thread dành cho các vòng lặp vô tận.

## 9. Model, layout và painting phải nhất quán với EDT

### 9.1. `JTable`, `JList`, `JTree` và `Document`

Một lỗi phổ biến là không đụng trực tiếp `JTable` nhưng sửa `DefaultTableModel` từ background thread. Model phát event tới JTable/listener trên **thread đã phát sự kiện**; vì vậy việc sửa model có thể làm UI cập nhật sai luồng.

~~~java
// Đoạn minh họa gọi từ background thread khi đã có immutable rowData.
Object[] rowData = {"Mã 42", "Hoàn thành"};
SwingUtilities.invokeLater(() -> tableModel.addRow(rowData));
~~~

Ở đây `tableModel` là `DefaultTableModel` **đã gắn với JTable**. Mảng `rowData` phải được coi là dữ liệu bàn giao ổn định; không tiếp tục sửa mảng ở worker sau khi đặt lịch. Tốt hơn nữa là sử dụng record/immutable DTO hoặc đối tượng copy nếu dữ liệu nhiều trường.

Tương tự với `ListModel`, `TreeModel`, `JTextArea`/`Document` và các listener: trừ trường hợp API ghi rõ contract riêng, cập nhật model gắn UI ở EDT. Một số implementation của `Document` có đồng bộ nội bộ, nhưng notification và tương tác Swing vẫn phải được thiết kế theo threading contract cụ thể; không suy rộng thành tự do sửa mọi text component từ worker.

### 9.2. `repaint()` và `revalidate()` không sửa lỗi tranh chấp dữ liệu

`JComponent.repaint()` xếp yêu cầu vẽ lại; `revalidate()` yêu cầu bố cục lại theo cơ chế trì hoãn. Khi tạo/xóa component hoặc đổi trạng thái cần vẽ, chạy phần thay đổi trên EDT rồi gọi method tương ứng:

~~~java
// Đoạn minh họa chạy trên EDT.
panel.add(new javax.swing.JLabel("Mục mới"));
panel.revalidate(); // yêu cầu layout tính toán lại nếu cần
panel.repaint();    // yêu cầu vẽ lại khi cần
~~~

`panel` là container đã được tạo. Thường những setter hoặc model event đã tự yêu cầu cập nhật nên không phải lần nào cũng cần gọi cả hai.

**Không gọi trực tiếp `paint(Graphics)` hoặc `paintComponent(Graphics)` từ worker** để “ép UI vẽ”. Với custom painting, lưu trạng thái hình ảnh theo mô hình thread-safe/bàn giao đúng, yêu cầu `repaint()`, và thực hiện việc vẽ khi Swing gọi `paintComponent`. `repaint()` không đồng nghĩa hình đã vẽ xong tại thời điểm lời gọi trả về.

Một số lời gọi `repaint`/`revalidate` được tài liệu chỉ rõ là an toàn với thread khác; việc đó chỉ liên quan đến **yêu cầu lập lịch vẽ/bố cục**, không hợp thức hóa `setText`, thay cấu trúc container hay sửa model từ nền.

### 9.3. Đừng sửa UI trong callback painting

`paintComponent` nên nhanh, chỉ dùng dữ liệu đã sẵn có và `Graphics` được truyền vào. Không gọi network, query DB, `Thread.sleep`, hoặc gắn/xóa component ngay trong lúc vẽ; nếu cần cập nhật state, thực hiện ở callback khác trên EDT và yêu cầu repaint. Điều này giảm vẽ lặp và tái nhập khó đoán.

## 10. Một số lỗi thực tế và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và khắc phục |
| --- | --- | --- |
| Nhấn nút, cửa sổ “Not responding” | `ActionListener` đang làm I/O, `sleep` hoặc `get()` | Đo độ dài callback; chuyển phần chậm qua worker; giữ callback EDT ngắn. |
| Label đôi khi không đổi, bảng thỉnh thoảng lỗi chỉ số | Worker sửa component/model ngoài EDT | Gắn assert `isEventDispatchThread()` ở đoạn cập nhật; đưa về `process`/`done` hoặc `invokeLater`. |
| `invokeAndWait` bị treo hoặc báo lỗi | Gọi từ EDT, hoặc thread gọi giữ lock EDT cần | Không gọi từ EDT; tránh lock/wait tạo chu trình chờ; ưu tiên callback bất đồng bộ. |
| Worker kết thúc mà UI vẫn hiển thị “Đang tải” | Kết quả không được bàn giao về EDT, hoặc listener bị hủy | Dùng `done`, kiểm tra exception/cancellation và trạng thái màn hình. |
| Thanh tiến độ nhảy 20% rồi 60% | `publish/process` được gộp để tiết kiệm event | Dùng phần trăm mới nhất; không yêu cầu mỗi lần publish phải dẫn đến một lần vẽ. |
| Sau khi đóng/mở màn hình, kết quả cũ đè lên nội dung mới | Callback của job cũ vẫn đến sau | Cancel khi rời màn hình, sử dụng task ID và bỏ qua kết quả không còn thuộc phiên hiện tại. |
| Cửa sổ không cập nhật sau `add/remove` | Layout chưa được làm mới | Cập nhật container trên EDT; gọi `revalidate()`, `repaint()` khi cần. |
| Một timer mỗi giây vẫn làm UI đứng | Timer callback xử lý tác vụ nặng trên EDT | Để timer chỉ đổi UI nhẹ; đưa phần nặng sang worker riêng. |
| Chạy GUI trên CI báo `HeadlessException` | Môi trường không có display | Dùng test headless cho logic thread; test cửa sổ trên môi trường có GUI. |
| Cập nhật chưa xuất hiện ngay sau `invokeLater` | `invokeLater` không đồng bộ | Dùng callback/đồng bộ dành riêng cho test; không gọi `sleep` trên EDT để “đợi repaint”. |

### 10.1. Công cụ chẩn đoán

- Trong vùng phát sinh lỗi, log `Thread.currentThread().getName()` và `SwingUtilities.isEventDispatchThread()`. Tên thread có thể khác giữa JVM; boolean là kiểm tra API.
- Với ứng dụng không phản hồi, lấy thread dump bằng `jcmd <pid> Thread.print` hoặc công cụ giám sát phù hợp; xem EDT có đang ở network I/O, `Future.get`, lock, `sleep` hay vòng lặp không. Đây là công cụ chẩn đoán đang được hỗ trợ trên các JDK hiện đại.
- Trong code nội bộ, dùng guard `if (!SwingUtilities.isEventDispatchThread()) throw ...;` ở các method cập nhật UI quan trọng. Điều này giúp test bắt lỗi sớm; không thay thế việc thiết kế luồng đúng.
- Khi cần test hành vi SwingWorker, có thể dùng latch/atomic reference như mục 7. Cần bảo đảm thread đang `await` **không phải EDT**, tránh test tự gây deadlock.
- Bằng chứng lỗi có thể không ổn định về thời gian. Không dựa vào việc “chạy 10 lần không thấy lỗi” để kết luận một thao tác Swing ngoài EDT là an toàn.

## 11. Những nguyên tắc luôn có ích trong Java hiện nay

1. **Khởi tạo GUI trên EDT:** đặt lời gọi tạo/hiện `JFrame` trong `SwingUtilities.invokeLater`.
2. **Chỉ cập nhật component/model trên EDT:** quy tắc ngoại lệ phải xuất phát từ API tài liệu rõ ràng, không suy diễn.
3. **Giữ event handler ngắn:** mọi việc có thể chặn đáng kể cần đưa ra nền.
4. **Chọn đúng công cụ:** `SwingWorker` cho task dài gắn với UI; `javax.swing.Timer` cho tác vụ UI nhỏ theo chu kỳ; `invokeLater` cho một lượt bàn giao dữ liệu.
5. **Không đợi worker trên EDT:** `get`, `join`, `await`, I/O đồng bộ có thể khóa giao diện.
6. **Bàn giao dữ liệu đúng cách:** worker tính ra immutable snapshot hoặc kết quả độc lập; EDT mới cập nhật widget.
7. **Xử lý lifecycle:** lỗi, hủy, đóng cửa sổ, task kết thúc muộn và job trùng lặp.
8. **Tách cập nhật state và vẽ:** thay state đúng thread, để Swing tự gọi `paintComponent` sau `repaint`.
9. **Đọc contract của công cụ đang dùng:** AWT/Swing sử dụng EDT; các toolkit GUI khác có cơ chế thread riêng, không áp tự động luật EDT của Swing cho tất cả thư viện.
10. **Test ở cả hai lớp:** kiểm tra thread confinement có thể headless; kiểm tra bố cục và tương tác cần GUI thật.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao việc gọi `SwingUtilities.invokeLater(() -> loadFromNetwork())` vẫn có thể làm ứng dụng đóng băng?

Vì `loadFromNetwork()` vẫn được **thực hiện trên EDT**. `invokeLater` chỉ thay đổi thời điểm xử lý, không biến logic bên trong thành công việc nền.

**Câu 2.** Trong `SwingWorker`, có được gọi `label.setText(...)` ở `doInBackground()` không?

Với phần lớn API Swing, **không**. Chuyển dữ liệu sang `process` hoặc `done`, vốn chạy trên EDT.

**Câu 3.** `SwingWorker.publish(10)` rồi `publish(20)` có luôn khiến `process` được gọi hai lần không?

Không. `SwingWorker` có thể gộp các lần `publish` vào một callback `process(List<V>)`; điều này được thiết kế để giảm quá tải hàng đợi.

**Câu 4.** Vì sao `get()` trong `done()` thường phù hợp, còn `get()` ngay trong nút “Tải” lại nguy hiểm?

`done` chạy sau khi task đã kết thúc nên có thể lấy kết quả hoặc nhận exception/hủy; gọi `get` quá sớm trong listener EDT có thể chặn luồng giao diện.

**Câu 5.** Có được gọi `invokeAndWait` từ một `ActionListener` không?

Không. `ActionListener` Swing thông thường đã chạy trên EDT; cố gọi `invokeAndWait` từ EDT gây lỗi hoặc vi phạm contract.

**Câu 6.** Vì sao cần cập nhật `DefaultTableModel` trên EDT dù ta không gọi trực tiếp setter của `JTable`?

Model phát event cho các listener/component Swing; cập nhật từ worker có thể khiến event và logic UI chạy trên thread sai.

**Câu 7.** Nếu gọi `repaint()` từ worker, ta có thể sửa trực tiếp mọi field của component từ worker không?

Không. Một yêu cầu `repaint` thread-safe theo contract liên quan không đồng nghĩa toàn bộ state/model của Swing thread-safe.

## Tài liệu API chính thức, còn áp dụng

- [Java SE 25 — `javax.swing` package và Swing Threading Policy](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/package-summary.html)
- [Java SE 25 — `SwingUtilities.invokeLater`, `invokeAndWait`, `isEventDispatchThread`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingUtilities.html)
- [Java SE 25 — `java.awt.EventQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/EventQueue.html)
- [Java SE 25 — `SwingWorker`, `doInBackground`, `process`, `done` và `progress`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingWorker.html)
- [Java SE 25 — `javax.swing.Timer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/Timer.html)
- [Java SE 25 — `JComponent.revalidate` và `repaint`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/JComponent.html)
- [Java SE 25 — Module `java.desktop`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/module-summary.html)