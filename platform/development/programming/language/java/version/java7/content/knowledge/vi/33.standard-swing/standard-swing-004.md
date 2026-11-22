# Đăng ký và hủy event mask theo vòng đời giao diện Swing

## 1. Bài toán và mục tiêu

Một ứng dụng Swing có thể tạo nhiều cửa sổ, mở/đóng dialog, ẩn/hiện một view hoặc chuyển qua lại các tab. Nếu đăng ký `AWTEventListener` khi mở màn hình mà không hủy lúc màn hình kết thúc, listener tiếp tục nhận event không còn liên quan, giữ tham chiếu tới view/controller, chạy logic lặp hoặc khiến GUI chậm dần. Hủy quá sớm lại làm tính năng ngừng quan sát dù view vẫn đang hoạt động.

Bài học tập trung vào cặp API AWT vẫn được hỗ trợ trong Java hiện đại:

~~~java
Toolkit.getDefaultToolkit().addAWTEventListener(observer, eventMask);
Toolkit.getDefaultToolkit().removeAWTEventListener(observer);
~~~

Mục tiêu: hiểu ý nghĩa `eventMask`, phân biệt listener cấp Toolkit với listener trên component, quản lý start/stop/close theo lifecycle, xử lý đúng EDT và kiểm chứng không đăng ký trùng hoặc leak.

**Lưu ý phạm vi thực tế:** Javadoc `Toolkit.addAWTEventListener` coi listener cấp Toolkit là công cụ cho nhu cầu đặc biệt như accessibility, event tracing và diagnostic. Với hành động thường ngày của một nút, form hoặc phím tắt Swing, ưu tiên `addActionListener`, `addMouseListener`, `addFocusListener` hoặc `InputMap`/`ActionMap`. Ta chỉ dùng event mask toàn Toolkit khi thật sự cần quan sát nhiều component theo chính sách chung.

## 2. Event mask là gì?

`java.awt.AWTEvent` định nghĩa các mask kiểu `long`, mỗi mask đại diện một **nhóm sự kiện**. Chọn nhiều nhóm bằng toán tử OR bit `|`:

~~~java
long mask = AWTEvent.MOUSE_EVENT_MASK
          | AWTEvent.MOUSE_MOTION_EVENT_MASK
          | AWTEvent.KEY_EVENT_MASK;
~~~

| Mask | Nhóm event | Ghi chú |
| --- | --- | --- |
| `MOUSE_EVENT_MASK` | Mouse pressed, released, clicked, entered, exited | Không bao gồm mouse moved/dragged hay wheel. |
| `MOUSE_MOTION_EVENT_MASK` | Mouse moved, dragged | Tần suất cao; không log tràn lan. |
| `MOUSE_WHEEL_EVENT_MASK` | Mouse wheel | Có mask riêng. |
| `KEY_EVENT_MASK` | Key pressed, released, typed | Dễ nhận sự kiện từ nhiều ô nhập liệu; hạn chế ghi phím. |
| `FOCUS_EVENT_MASK` | Focus gained/lost của component | Khác focus của cửa sổ. |
| `WINDOW_EVENT_MASK` | Window opened, closing, closed, activated... | `WINDOW_CLOSING` và `WINDOW_CLOSED` khác nhau. |
| `HIERARCHY_EVENT_MASK` | Thay đổi cây UI, trạng thái displayable/showing | Đối với lifecycle một panel, `HierarchyListener` cục bộ dễ kiểm soát hơn. |

**Mask khác event ID.** `AWTEvent.MOUSE_EVENT_MASK` yêu cầu Toolkit gọi observer cho một nhóm mouse event; `MouseEvent.MOUSE_PRESSED` là ID của sự kiện nhấn chuột cụ thể. Dùng mask ở thời điểm **đăng ký**, rồi kiểm tra `event instanceof MouseEvent` và `event.getID()` ở callback nếu cần lọc chi tiết.

Mask của Toolkit chỉ lọc **loại event**, không chỉ định cửa sổ nguồn. `Toolkit.addAWTEventListener` có phạm vi quan sát các AWTEvent dispatch qua Toolkit của ứng dụng; không phải hook bàn phím/chuột toàn hệ điều hành hay cho các process khác. Muốn observer chỉ phục vụ một cửa sổ, phải tự lọc `event.getSource()` về đúng cửa sổ đó.

### So sánh ba cơ chế đăng ký

| Cơ chế | Đăng ký / hủy | Phạm vi |
| --- | --- | --- |
| Component listeners | `button.addActionListener(a)` / `button.removeActionListener(a)`, `panel.addMouseListener(m)` / `panel.removeMouseListener(m)` | Một component và loại sự kiện tương ứng. |
| Toolkit observer | `toolkit.addAWTEventListener(listener, mask)` / `toolkit.removeAWTEventListener(listener)` | Nhiều component/window trong phạm vi Toolkit; phải lọc source nếu chỉ muốn một view. |
| `Component.enableEvents(mask)` | `enableEvents(mask)` / `disableEvents(mask)` trong subclass; thường override `processEvent` hoặc phương thức xử lý tương ứng | Cơ chế nhận event mức thấp của chính component đó; không đăng ký observer cấp Toolkit. |

Không gọi `removeAWTEventListener` để thay thế `disableEvents` và ngược lại. Hai cặp này phục vụ các cơ chế khác nhau.

## 3. Vòng đời của registration

Một **owner** (window, panel hoặc controller) nên sở hữu đúng listener mà nó tạo ra. Owner giữ trạng thái để bảo đảm lệnh start/stop **idempotent**: gọi nhiều lần liên tiếp vẫn chỉ có tối đa một registration do owner quản lý.

| Thời điểm | Hành động | Lý do |
| --- | --- | --- |
| Khởi tạo controller/view nhưng chưa hiển thị | Chưa cần add | Chưa có phiên quan sát đang chạy. |
| Window/panel bắt đầu hiển thị | `start()` nếu chưa registered | Bật mask cần dùng. |
| Window bị ẩn, view chuyển khỏi màn hình | `stop()` nếu chỉ quan sát khi hiển thị | Tránh sự kiện ngoài phiên đang active. |
| Window/panel hiển thị lại | `start()` idempotent | Tái kích hoạt mà không add chồng. |
| View dispose/hủy vĩnh viễn | `close()` và gỡ listener gắn với lifecycle khi cần | Tránh Toolkit giữ tham chiếu tới controller/view đã kết thúc. |

**Sự kiện đóng cửa sổ:**
- `windowClosing` là yêu cầu đóng từ thao tác người dùng; ứng dụng có thể từ chối đóng.
- `windowClosed` được phát sau khi window được `dispose()`. Đây là điểm dọn cuối phù hợp cho scope gắn với một `JFrame`.
- `JFrame.HIDE_ON_CLOSE` chỉ ẩn window, không bảo đảm có `windowClosed`; nếu muốn ngừng quan sát lúc ẩn, phải xử lý sự kiện hidden hoặc tự gọi stop.
- Gọi `frame.dispose()` bằng code không yêu cầu người dùng bấm nút X, vì thế không nên chỉ gắn cleanup vào `windowClosing`.

**Quy tắc bắt buộc:** lưu **cùng một đối tượng listener** để add và remove. Hai biểu thức lambda nhìn giống nhau như `e -> handle(e)` được tạo ở hai thời điểm có thể là hai instance khác nhau. Đừng tạo lambda mới ở lệnh remove. Listener cấp Toolkit có thể giữ tham chiếu tới controller hoặc cửa sổ kể cả sau `dispose()`; GC không thay thế cleanup chủ động.

## 4. Ví dụ Java 17+: observer gắn với vòng đời JFrame

Chương trình hoàn chỉnh sau quan sát mouse press **chỉ trong một JFrame**. Nó dùng `componentShown` để start, `componentHidden` để stop, và `windowClosed` để close vĩnh viễn. Các lời gọi chồng nhau vẫn an toàn nhờ cờ `registered`/`closed`.

**Tệp `EventMaskLifecycleDemo.java`:**

~~~java
import java.awt.AWTEvent;
import java.awt.BorderLayout;
import java.awt.Component;
import java.awt.Toolkit;
import java.awt.event.AWTEventListener;
import java.awt.event.ComponentAdapter;
import java.awt.event.ComponentEvent;
import java.awt.event.MouseEvent;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;

public final class EventMaskLifecycleDemo {
    private static final long MASK = AWTEvent.MOUSE_EVENT_MASK;

    private static final class MouseMaskScope implements AutoCloseable {
        private final JFrame owner;
        private final Toolkit toolkit = Toolkit.getDefaultToolkit();
        private final AWTEventListener listener = this::onEvent;
        private boolean registered;
        private boolean closed;

        MouseMaskScope(JFrame owner) {
            this.owner = owner;
        }

        void start() {
            requireEdt();
            if (closed || registered) {
                return;
            }
            toolkit.addAWTEventListener(listener, MASK);
            registered = true;
            System.out.println("Mask: ON");
        }

        void stop() {
            requireEdt();
            if (!registered) {
                return;
            }
            toolkit.removeAWTEventListener(listener);
            registered = false;
            System.out.println("Mask: OFF");
        }

        @Override
        public void close() {
            requireEdt();
            if (closed) {
                return;
            }
            closed = true;
            stop();
        }

        private void onEvent(AWTEvent event) {
            if (!(event instanceof MouseEvent mouse)
                    || mouse.getID() != MouseEvent.MOUSE_PRESSED) {
                return;
            }
            if (!(event.getSource() instanceof Component source)) {
                return;
            }
            if (SwingUtilities.getWindowAncestor(source) != owner) {
                return;
            }
            System.out.println("Mouse press inside tracked window");
        }

        private static void requireEdt() {
            if (!SwingUtilities.isEventDispatchThread()) {
                throw new IllegalStateException("Use Swing EDT");
            }
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(EventMaskLifecycleDemo::createAndShowUi);
    }

    private static void createAndShowUi() {
        JFrame frame = new JFrame("Event mask lifecycle");
        frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);

        JButton click = new JButton("Click inside");
        JButton close = new JButton("Dispose window");
        close.addActionListener(e -> frame.dispose());

        JPanel controls = new JPanel();
        controls.add(click);
        controls.add(close);
        frame.add(controls, BorderLayout.CENTER);

        MouseMaskScope scope = new MouseMaskScope(frame);

        frame.addComponentListener(new ComponentAdapter() {
            @Override
            public void componentShown(ComponentEvent event) {
                scope.start();
            }

            @Override
            public void componentHidden(ComponentEvent event) {
                scope.stop();
            }
        });

        frame.addWindowListener(new WindowAdapter() {
            @Override
            public void windowClosed(WindowEvent event) {
                scope.close();
            }
        });

        frame.setSize(420, 160);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }
}
~~~

Biên dịch và chạy trên máy có giao diện đồ họa:

~~~bash
javac -encoding UTF-8 EventMaskLifecycleDemo.java
java EventMaskLifecycleDemo
~~~

Ứng dụng yêu cầu môi trường desktop; chạy ở CI headless không thể tạo `JFrame`. Bấm `Click inside` vài lần rồi `Dispose window`. Trace minh họa khi người dùng nhấn chuột hai lần trong cửa sổ:

~~~text
Mask: ON
Mouse press inside tracked window
Mouse press inside tracked window
Mask: OFF
~~~

Đây là **trace ví dụ, không phải stdout cố định**: nút đóng cũng có thể phát `MOUSE_PRESSED`, và số dòng mouse phụ thuộc số lần nhấn thực tế. Chỉ kỳ vọng một dòng `Mask: ON` cho mỗi lần scope đăng ký thực sự và một dòng `Mask: OFF` cho lần hủy thực sự; `stop()` gọi lặp không tạo thêm dòng.

### Vì sao ví dụ cần nhiều lớp bảo vệ?

- `MouseMaskScope.listener` là **một field ổn định**, được dùng lại trong `addAWTEventListener` và `removeAWTEventListener`.
- `registered` ngăn `componentShown` lặp làm add nhiều lần; `closed` chặn hồi sinh scope đã đóng.
- `SwingUtilities.getWindowAncestor(source) == owner` bỏ qua những event từ window khác. Nếu app mở dialog/popup riêng, phải định nghĩa chính xác scope muốn tính những window đó hay không.
- `componentHidden` hủy khi ẩn; `windowClosed` đảm bảo dọn sau dispose. Bất kể thứ tự callback, logic stop/close là idempotent.
- `requireEdt()` giúp phát hiện start/stop trên sai thread; `SwingUtilities.invokeLater` chuyển thao tác tạo UI từ `main` sang EDT.
- Mask chỉ là `MOUSE_EVENT_MASK`. Lọc riêng `MOUSE_PRESSED` tránh log các mouse entered/exited/released/clicked không cần thiết.

### Vấn đề cần cân nhắc khi dùng source filter

Một `AWTEventListener` cấp Toolkit có thể thấy event từ nhiều component trong cùng process, gồm nhiều JFrame. Điều kiện ancestor trong ví dụ phù hợp khi chỉ cần một window. Nhưng nó không tự bao gồm một `JDialog` sở hữu bởi window đó (dialog là một `Window` riêng), không tự phân biệt hành vi của các tab và không phải bộ lọc bảo mật. Nếu yêu cầu quan sát một cây `JPanel`, sử dụng `SwingUtilities.isDescendingFrom(source, panel)` (hoặc `source == panel`) để giới hạn đúng cây; khi panel rời khỏi cây hoặc được thay thế, cập nhật phạm vi tương ứng.

## 5. Lifecycle của JPanel, tab hoặc view động

`JPanel` có thể được gắn vào frame đã hiển thị, chuyển sang tab khác hoặc bị tháo khỏi container mà frame vẫn còn sống. Dùng riêng `windowClosed` của frame sẽ quá muộn nếu observer chỉ dành cho một panel. Trong trường hợp này, `HierarchyListener` + `panel.isShowing()` thường phù hợp:

~~~java
// Đoạn minh họa đặt trong controller đã có biến panel và scope.
HierarchyListener lifecycleListener = event -> {
    long flags = event.getChangeFlags();
    boolean changed =
            (flags & (HierarchyEvent.SHOWING_CHANGED
                    | HierarchyEvent.DISPLAYABILITY_CHANGED)) != 0;
    if (!changed) {
        return;
    }
    if (panel.isShowing()) {
        scope.start();
    } else {
        scope.stop();
    }
};
panel.addHierarchyListener(lifecycleListener);

// Khi controller kết thúc vĩnh viễn:
panel.removeHierarchyListener(lifecycleListener);
scope.close();
~~~

Đoạn này **không phải chương trình độc lập**; phải có `panel`, `scope` và import `java.awt.event.HierarchyEvent`, `java.awt.event.HierarchyListener`. Các dòng cleanup cuối chỉ chạy ở thời điểm **hủy controller**, không nằm ngay sau `addHierarchyListener` trong lúc view còn hoạt động. Với Swing, `isShowing()` xét cả trạng thái của ancestor nên đáng tin hơn `isVisible()` khi parent bị ẩn. `DISPLAYABILITY_CHANGED` mô tả thay đổi resource/displayability, `SHOWING_CHANGED` mô tả chuyển trạng thái thực sự đang hiển thị.

Nếu chỉ cần pause/resume theo tab, cũng có thể quản lý lifecycle tập trung tại controller lúc chọn/bỏ chọn tab; quan trọng là một nơi duy nhất chịu trách nhiệm `start/stop`. Nếu view bị remove rồi add lại, quyết định có dùng lại scope hay tạo scope mới dựa trên **tuổi thọ controller**, không phải chỉ dựa vào số lần add/remove component.

### `enableEvents` / `disableEvents` trong custom component

Một subclass custom có thể chọn nhận các event mức thấp của **chính component đó** bằng `enableEvents(mask)` và override phương thức xử lý thích hợp. Đây là API vẫn hiện hành, nhưng là trường hợp khác hẳn observer toàn Toolkit:

~~~java
// Ví dụ minh họa nằm trong subclass của JComponent:
enableEvents(AWTEvent.MOUSE_EVENT_MASK);
// ... subclass có thể override processMouseEvent(MouseEvent event).
disableEvents(AWTEvent.MOUSE_EVENT_MASK);
~~~

Chỉ subclass mới gọi được các phương thức `protected` này. Đừng cố gọi `disableEvents` để hủy `Toolkit.addAWTEventListener`, và đừng dùng cách này khi `addMouseListener` là đủ. Khi subclass nhận event, nhớ giữ hành vi xử lý phù hợp (ví dụ khi override `processMouseEvent` thì cân nhắc gọi `super.processMouseEvent(event)` để không cắt listener thông thường).

## 6. EDT, hiệu năng và dữ liệu quan sát

Swing phần lớn **không thread-safe**. Tạo/đổi trạng thái component và quản lý các hook gắn với vòng đời UI trên **Event Dispatch Thread (EDT)**. Nếu một worker ngoài EDT muốn bắt đầu/kết thúc quan sát, hãy điều phối:

~~~java
SwingUtilities.invokeLater(scope::stop);
~~~

Đây là **đoạn minh họa** với `scope` có sẵn; không dùng `invokeLater` để né việc quản lý vòng đời hoặc biến listener thành shared mutable state khó kiểm soát.

Callback toàn Toolkit chạy trong luồng xử lý event và có thể được gọi rất thường xuyên. Không làm I/O lâu, gọi HTTP, `Thread.sleep`, chờ lock, truy vấn DB hoặc log mọi mouse-move trong callback. Hãy lọc theo event ID và owner trước, sau đó thực hiện thao tác nhẹ; nếu cần công việc dài, chuyển ra background worker và quay lại EDT khi cập nhật GUI.

**Sự kiện bàn phím đặc biệt nhạy cảm:** `KEY_EVENT_MASK` có thể nhìn thấy phím được gõ vào các ô nhập trong ứng dụng. Không dùng nó để ghi lại nội dung mật khẩu/thông tin bí mật. Với phím tắt tại một màn hình, dùng `InputMap`/`ActionMap` và `KeyStroke` của Swing thay vì quan sát toàn Toolkit.

**Event mask không phải cơ chế chặn event.** `AWTEventListener` quan sát event được dispatch; để ngăn thao tác, hãy sử dụng trạng thái `setEnabled(false)`, focus policy hoặc logic tương tác phù hợp của component. Không giả định việc thấy `MouseEvent` trong Toolkit observer cho phép chặn mọi thao tác của người dùng.

## 7. Kiểm tra việc đăng ký/hủy đúng

Khi chạy ứng dụng trong môi trường desktop, nên kiểm thử các tình huống sau:

1. **Mở lần đầu:** `start()` được gọi lúc UI hiển thị, chỉ một lần add thực sự.
2. **Nhận event:** nhấn chuột trong owner sẽ có callback; thao tác trong một cửa sổ khác không kích hoạt logic của owner này.
3. **Ẩn/hiện nhiều lần:** mỗi chu kỳ thay đổi active tạo tối đa một ON và một OFF; sau khi hiện lại quan sát hoạt động.
4. **Dispose từ nhiều đường:** nút X, nút gọi `frame.dispose()`, logic đóng chương trình đều dẫn tới cleanup; không dựa riêng vào `windowClosing`.
5. **Tạo instance mới:** observer từ instance cũ không còn nhận event; observer mới không bị trộn với instance cũ.
6. **Màn hình động:** panel bị tháo khỏi cây, đổi tab hoặc ẩn ancestor thì `isShowing()` được đồng bộ với scope.
7. **Đúng EDT:** không update Swing UI trực tiếp từ worker thread; listener chạy ngắn, không làm UI đứng.

`Toolkit.getAWTEventListeners()` và `getAWTEventListeners(mask)` giúp xem observer đang có khi debug; kết quả có thể chứa `AWTEventListenerProxy` kèm mask. Tuy nhiên, cùng một listener được thêm nhiều lần vẫn có thể chỉ xuất hiện **một lần** trong mảng kết quả. Vì vậy **độ dài mảng không là bằng chứng đã tránh double-registration**. Tự quản lý trạng thái owner và đo số lần callback trong một kịch bản có kiểm soát đáng tin hơn. Không bao giờ gỡ listener thuộc framework hoặc owner khác.

Một bài test Swing trực quan cần màn hình thật hoặc virtual display; việc chạy `JFrame` trong môi trường `java.awt.headless=true` sẽ thất bại do giới hạn môi trường, không chứng minh `AWTEventListener` đã bị loại bỏ.

## 8. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Add listener trong `paintComponent`, `actionPerformed` hoặc mỗi lần refresh | Đăng ký lặp và xử lý dư | Gắn vào lifecycle start của owner, kiểm tra `registered`. |
| Remove bằng một lambda khác instance | Listener cũ không bị gỡ | Lưu đúng instance vào field và remove field đó. |
| Chỉ dùng mask mà không lọc source | Xử lý event của window khác | Lọc component/ancestor/window tại callback. |
| Chỉ cleanup trong `windowClosing` | Bỏ sót code gọi `dispose()`, xử lý sai tình huống close bị hủy | Dùng `windowClosed` cho dispose, hidden cho pause. |
| Chỉ cleanup trong `windowClosed` khi UI được ẩn tạm | Listener tiếp tục chạy trong thời gian hidden | Dùng component/hierarchy visibility lifecycle hoặc stop chủ động. |
| Dùng `isVisible()` cho panel nằm trong tab/parent ẩn | Hiểu sai trạng thái hoạt động | Dùng `isShowing()` và hierarchy changes khi phù hợp. |
| Chặn EDT bằng logging hoặc việc nặng | UI giật/đơ | Mask hẹp, filter sớm, chuyển việc dài ra background. |
| Gỡ tất cả listener trên Toolkit để dọn | Phá hành vi thư viện/owner khác | Chỉ remove listener do scope của mình sở hữu. |
| Dùng Toolkit observer cho shortcut đơn giản | Scope quá rộng và logic phức tạp | Dùng `InputMap`/`ActionMap`, listener cục bộ. |

## 9. Checklist đưa vào dự án

- [ ] Xác định đúng owner: component, panel, JFrame hoặc công cụ quan sát toàn ứng dụng.
- [ ] Phân biệt mask (`AWTEvent.*_EVENT_MASK`) và ID (`MouseEvent.MOUSE_PRESSED`).
- [ ] Giữ một listener instance; start/stop idempotent; close khi owner kết thúc vĩnh viễn.
- [ ] Lọc source và owner ngay trong callback của Toolkit listener.
- [ ] Bắt đúng lifecycle: visible/hidden, hierarchy showing hoặc dispose, tùy owner.
- [ ] Gỡ luôn local lifecycle listener khi controller thật sự kết thúc nếu cần.
- [ ] Cập nhật Swing trên EDT; giữ callback nhanh và tránh dữ liệu phím nhạy cảm.
- [ ] Thử ẩn/hiện, mở/đóng nhiều lần, nhiều cửa sổ và dispose từ code.
- [ ] Chọn listener hoặc key bindings cục bộ cho phần lớn yêu cầu UI thông thường.

## Tài liệu API còn hiệu lực

- [Oracle JDK 25: `Toolkit.addAWTEventListener`, `removeAWTEventListener`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Toolkit.html).
- [Oracle JDK 25: `AWTEvent` và các event mask](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/AWTEvent.html).
- [Oracle JDK 25: `Component` — showing, displayability, enableEvents/disableEvents](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Component.html).
- [Oracle JDK 25: `HierarchyEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/event/HierarchyEvent.html) và [`WindowEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/event/WindowEvent.html).
- [Oracle JDK 25: `javax.swing` — Swing threading policy](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/package-summary.html).

**Ghi nhớ:** event mask xác định **nhóm sự kiện**; listener cấp Toolkit quan sát rộng hơn một view; còn **vòng đời owner** mới quyết định khi nào phải add, stop và remove đúng instance.