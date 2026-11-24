# Đổi factory có kiểm soát và tái tạo các sản phẩm đang phụ thuộc họ cũ

## 1. Vì sao đổi factory không chỉ là thay một tham chiếu?

**Abstract Factory** cho phép client yêu cầu nhiều loại sản phẩm tương thích thông qua một factory chung. Chẳng hạn, `LightUiFactory` tạo `LightButton` và `LightCheckbox`, còn `DarkUiFactory` tạo `DarkButton` và `DarkCheckbox`. Khi ứng dụng hỗ trợ đổi giao diện Light ↔ Dark trong lúc chạy, một câu hỏi quan trọng xuất hiện: **Điều gì xảy ra với các sản phẩm đã được tạo từ factory cũ?**

Xét đoạn code:

~~~java
UiFactory factory = new LightUiFactory();
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();

// Sau một thao tác chọn theme:
factory = new DarkUiFactory();
~~~

Việc gán lại biến `factory` **không làm đối tượng `button` và `checkbox` biến thành Dark**. Chúng vẫn là các đối tượng Light đã được cấp phát trước đó. Nếu client chỉ tạo thêm `DarkDialog` từ factory mới, một màn hình có thể vô tình trộn nhiều họ sản phẩm.

Bài học thuộc chương **Lựa chọn biến thể** của module Abstract Factory, tập trung vào **đổi factory có kiểm soát và tái tạo các sản phẩm đang phụ thuộc họ cũ**. Nội dung giúp bạn:

1. Xác định những sản phẩm nào phải được tái tạo khi chuyển biến thể.
2. Tách trạng thái nghiệp vụ cần giữ lại khỏi trạng thái hiển thị phụ thuộc họ.
3. Tạo một bộ sản phẩm mới hoàn chỉnh **trước khi** đưa vào sử dụng.
4. Xử lý thất bại trong quá trình khởi tạo để màn hình cũ vẫn hoạt động.
5. Giải phóng sản phẩm cũ theo đúng quyền sở hữu và thứ tự tài nguyên.
6. Kiểm thử việc chuyển đổi ở cả đường thành công, lỗi và thao tác lặp.

Ví dụ sử dụng **Java 17+**, hai họ giao diện Light/Dark và bộ kiểm thử minh họa bằng JUnit Jupiter 5. Ứng dụng dòng lệnh sử dụng `render()` trả chuỗi để thể hiện sự thay đổi; một UI framework thật sẽ có bước thay widget/tree và thường phải thực hiện commit trên UI thread.

## 2. Ba lớp trạng thái cần phân biệt

Khi đổi factory, không phải mọi trạng thái đều nên bị mất. Hãy phân biệt:

| Loại trạng thái | Ví dụ | Xử lý khi đổi họ |
| --- | --- | --- |
| **Trạng thái nghiệp vụ** | Người dùng đã bật thông báo (`notificationsEnabled = true`), dữ liệu form, lựa chọn ngôn ngữ | Giữ trong model/controller, áp dụng lại cho bộ sản phẩm mới |
| **Trạng thái trình bày** | Theme token, CSS class, renderer, hiệu ứng Light/Dark, các widget concretely được tạo | Tạo lại hoặc cập nhật theo cơ chế chính thức của họ mới |
| **Tài nguyên có vòng đời** | Listener, subscription, file handle, bitmap, native widget, session, lease | Xác định owner và đóng/hủy theo hợp đồng sau khi chuyển đổi an toàn |

Một lỗi phổ biến là lưu trạng thái nghiệp vụ **chỉ bên trong widget cũ**. Khi widget bị thay, dữ liệu người dùng biến mất. Trong ví dụ, `SettingsHost` giữ biến `notificationsEnabled` độc lập với `Checkbox`. Checkbox mới được khởi tạo bằng giá trị ấy.

**Bất biến quan trọng:** Ở mọi thời điểm client công khai một màn hình hoạt động, Button và Checkbox phải cùng họ với lựa chọn đang có hiệu lực, và trạng thái nghiệp vụ của màn hình phải được bảo toàn.

Có thể viết hình thức:

\[
\forall p \in \operatorname{Products}(\operatorname{activeView}),
\quad p.\operatorname{theme}() = \operatorname{selectedTheme}
\]

Bất biến này không yêu cầu mọi sản phẩm trong ứng dụng toàn cục cùng một theme; nó áp dụng cho **một phạm vi cần giữ nhất quán**, chẳng hạn một màn hình hoặc phiên giao diện.

## 3. Ai chọn factory và ai chịu trách nhiệm thay sản phẩm?

Trong thiết kế có kiểm soát, có bốn vai trò:

- **Composition root / factory selector:** Nhận lựa chọn Light/Dark, chọn hoặc tạo concrete factory thích hợp. Nơi này được phép biết `LightUiFactory` và `DarkUiFactory`.
- **SettingsHost (owner/controller):** Giữ trạng thái nghiệp vụ, quản lý phiên màn hình hiện hành, điều phối việc thay cả bộ sản phẩm.
- **SettingsView:** Sở hữu các product handle do factory trả về; chịu trách nhiệm giải phóng chúng khi không còn được dùng.
- **Concrete factory và concrete product:** Factory tạo bộ sản phẩm của họ mình; product thực thi interface và có vòng đời riêng.

~~~mermaid
flowchart TB
    Picker["Lựa chọn theme / composition root"] -->|"chọn UiFactory"| Host["SettingsHost"]
    Host -->|"prepare từ factory mới"| Next["SettingsView mới"]
    Host -->|"đang sở hữu"| Old["SettingsView cũ"]
    Next -->|"sở hữu"| NewButton["Button mới"]
    Next -->|"sở hữu"| NewCheck["Checkbox mới"]
    Old -->|"sở hữu"| OldButton["Button cũ"]
    Old -->|"sở hữu"| OldCheck["Checkbox cũ"]
    Host -->|"snapshot/restore trạng thái nghiệp vụ"| Model["notificationsEnabled"]
~~~

**Factory không nhất thiết sở hữu sản phẩm sau khi trả về.** Trong ví dụ, factory chuyển quyền sở hữu product handle cho `SettingsView`. Nếu implementation có pool dùng chung, widget có thể sở hữu lease của mình mà không được đóng cả pool. Vòng đời thật phải được ghi rõ trong contract.

## 4. Quy trình chuyển họ gồm hai giai đoạn

Không nên thay một sản phẩm mỗi khi nhận được và hiển thị ngay. Thay vào đó, có thể dùng quy trình **prepare → validate → commit → cleanup**.

| Bước | Hành động | Bất biến cần giữ |
| --- | --- | --- |
| **0. Nhận yêu cầu** | Người dùng chọn họ đích, ví dụ Dark | Màn hình cũ vẫn là họ Light |
| **1. Chụp trạng thái** | Lấy giá trị nghiệp vụ cần giữ, ví dụ notifications = true | Không mất dữ liệu người dùng |
| **2. Prepare** | Dùng factory đích tạo Button, Checkbox và thiết lập trạng thái | Bộ cũ vẫn có thể sử dụng |
| **3. Validate** | Kiểm tra không null, đúng họ, đủ các sản phẩm và hợp đồng cần thiết | Không công bố bộ mới thiếu hoặc trộn họ |
| **4. Commit** | Đưa **toàn bộ** bộ mới vào vị trí active trong một thao tác được điều phối | Client không quan sát một màn hình nửa Light, nửa Dark |
| **5. Cleanup** | Ngắt listener và đóng sản phẩm cũ theo quy định ownership | Không giữ resource cũ không còn dùng |

Nếu bước **prepare hoặc validate thất bại**, đóng các sản phẩm mới đã được tạo rồi **giữ nguyên active view cũ**. Đây là *rollback trước commit*.

Nếu **cleanup của bộ cũ lỗi sau khi commit**, bộ mới đã trở thành active. Không nên âm thầm gọi đây là rollback: phải báo cáo lỗi cleanup riêng và xử lý tài nguyên cũ theo chính sách hệ thống. Ví dụ Java ở phần sau trả một kết quả `SwitchOutcome` để phân biệt chuyển đổi thành công với lỗi cleanup.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Host as SettingsHost
    participant NewFactory as DarkUiFactory
    participant NewView as View mới
    participant OldView as View Light cũ

    User->>Host: chọn DARK
    Host->>Host: snapshot notificationsEnabled
    Host->>NewFactory: createButton()
    NewFactory-->>Host: DarkButton
    Host->>NewFactory: createCheckbox()
    NewFactory-->>Host: DarkCheckbox
    Host->>NewView: áp dụng model và kiểm tra cùng họ
    alt Prepare thành công
        Host->>Host: activeView = NewView, theme = DARK
        Host->>OldView: close()
        Host-->>User: SwitchOutcome(changed=true, cleanupError?)
    else Prepare thất bại
        Host->>NewView: dọn các product đã tạo được
        Host-->>User: thông báo lỗi; activeView vẫn là Light
    end
~~~

Sơ đồ là mô hình luồng trách nhiệm; với thao tác chuẩn bị bất đồng bộ, bước commit phải được đồng bộ với luồng thao tác UI và trạng thái hiện hành.

## 5. Ví dụ Java: model nắm state, view nắm product

Toàn bộ chương trình dưới đây có thể đặt trong file `ControlledSwitchDemo.java`. Các product là đối tượng mô phỏng, có `close()` để minh họa vòng đời. Phương thức `close()` của chúng được định nghĩa không ném checked exception, dù interface `AutoCloseable` nói chung cho phép ném exception.

### 5.1. Abstract factory và các abstract product

~~~java
import java.util.Objects;

public final class ControlledSwitchDemo {

    enum Theme {
        LIGHT, DARK
    }

    interface UiProduct extends AutoCloseable {
        Theme theme();
        String render();

        @Override
        void close(); // hợp đồng riêng của ví dụ: không checked exception
    }

    interface Button extends UiProduct {}

    interface Checkbox extends UiProduct {
        boolean isChecked();
        void setChecked(boolean value);
    }

    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Các concrete product và factory tiếp tục ở mục 5.2.
}
~~~

**Để chạy độc lập**, hãy ghép lần lượt các đoạn code ở mục 5.1–5.4 vào bên trong class `ControlledSwitchDemo` (các `import` ở đầu file, mỗi class lồng nhau đặt trong body của class ngoài). Mục 5.5 cung cấp `main()`; không tạo nhiều class `ControlledSwitchDemo`.

### 5.2. Concrete products thuộc hai họ

~~~java
static abstract class BaseProduct implements UiProduct {
    private final Theme theme;
    private boolean closed;

    BaseProduct(Theme theme) {
        this.theme = Objects.requireNonNull(theme);
    }

    @Override
    public final Theme theme() {
        return theme;
    }

    final void requireOpen() {
        if (closed) {
            throw new IllegalStateException("Product already closed");
        }
    }

    @Override
    public void close() {
        closed = true;
    }
}

static abstract class BaseButton extends BaseProduct
        implements Button {

    BaseButton(Theme theme) {
        super(theme);
    }

    @Override
    public final String render() {
        requireOpen();
        return theme() == Theme.LIGHT ? "LightButton" : "DarkButton";
    }
}

static abstract class BaseCheckbox extends BaseProduct
        implements Checkbox {

    private boolean checked;

    BaseCheckbox(Theme theme) {
        super(theme);
    }

    @Override
    public final boolean isChecked() {
        requireOpen();
        return checked;
    }

    @Override
    public final void setChecked(boolean value) {
        requireOpen();
        checked = value;
    }

    @Override
    public final String render() {
        requireOpen();
        String prefix = theme() == Theme.LIGHT
            ? "LightCheckbox" : "DarkCheckbox";
        return prefix + "(" + checked + ")";
    }
}

static final class LightButton extends BaseButton {
    LightButton() { super(Theme.LIGHT); }
}

static final class LightCheckbox extends BaseCheckbox {
    LightCheckbox() { super(Theme.LIGHT); }
}

static final class DarkButton extends BaseButton {
    DarkButton() { super(Theme.DARK); }
}

static final class DarkCheckbox extends BaseCheckbox {
    DarkCheckbox() { super(Theme.DARK); }
}

static final class LightUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}

static final class DarkUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new DarkButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new DarkCheckbox();
    }
}
~~~

`BaseProduct` chỉ giúp giảm code minh họa. Abstract Factory **không yêu cầu** các concrete product cùng kế thừa một base class; từng họ có thể dùng renderer, thư viện và kỹ thuật khác nhau miễn thực hiện đúng interface.

### 5.3. SettingsView chuẩn bị đủ bộ product và cleanup khi lỗi

Một `SettingsView` sở hữu **hai product handle**, giữ chúng dưới kiểu interface và có hàm dựng `prepare`. Trong thời gian prepare, đối tượng chưa được công bố cho client.

~~~java
static final class SettingsView implements AutoCloseable {
    private final Button button;
    private final Checkbox checkbox;

    private SettingsView(Button button, Checkbox checkbox) {
        this.button = button;
        this.checkbox = checkbox;
    }

    static SettingsView prepare(
            UiFactory factory,
            Theme expected,
            boolean notificationsEnabled) {

        Objects.requireNonNull(factory, "factory");
        Objects.requireNonNull(expected, "expected");

        Button button = null;
        Checkbox checkbox = null;

        try {
            button = Objects.requireNonNull(
                factory.createButton(),
                "createButton returned null"
            );
            checkbox = Objects.requireNonNull(
                factory.createCheckbox(),
                "createCheckbox returned null"
            );

            // Oracle lấy từ lựa chọn ở host, không lấy từ factory.
            if (button.theme() != expected || checkbox.theme() != expected) {
                throw new IllegalStateException(
                    "Factory produced a mixed or unexpected family"
                );
            }

            checkbox.setChecked(notificationsEnabled);
            return new SettingsView(button, checkbox);
        } catch (RuntimeException | Error cause) {
            // Chỉ các handle tạo thành công mới cần dọn.
            closeOnFailure(checkbox, cause);
            closeOnFailure(button, cause);
            throw cause;
        }
    }

    private static void closeOnFailure(
            UiProduct product, Throwable cause) {
        if (product == null) {
            return;
        }
        try {
            product.close();
        } catch (RuntimeException | Error closeError) {
            if (cause != closeError) {
                cause.addSuppressed(closeError);
            }
        }
    }

    void setNotificationsEnabled(boolean value) {
        checkbox.setChecked(value);
    }

    String render() {
        return button.render() + " | " + checkbox.render();
    }

    @Override
    public void close() {
        // Đóng thứ tự ngược lúc tạo; vẫn thử đóng button nếu
        // checkbox.close() lỗi.
        RuntimeException first = null;

        try {
            checkbox.close();
        } catch (RuntimeException ex) {
            first = ex;
        }

        try {
            button.close();
        } catch (RuntimeException ex) {
            if (first == null) {
                first = ex;
            } else if (first != ex) {
                first.addSuppressed(ex);
            }
        }

        if (first != null) {
            throw first;
        }
    }
}
~~~

Có ba điểm cần quan sát:

- `SettingsView.prepare()` kiểm tra **đúng họ đích** trước khi trả view. Giá trị `expected` đến từ lựa chọn đã biết của host, không phải từ phương thức `factory.theme()` tự khai báo.
- Khi `createButton()` thành công nhưng `createCheckbox()` lỗi, `button` vẫn được đóng. Khi factory trả sản phẩm sai họ, **cả hai handle đã tạo** được đóng.
- `SettingsView.close()` thử đóng cả hai handle dù một lần đóng ném `RuntimeException`. Ví dụ xử lý lỗi thông thường; với lỗi nghiêm trọng thuộc `Error`, production cần quy ước failure/shutdown riêng.

Ở đây, view có **quyền đóng** sản phẩm vì hợp đồng `UiFactory` quy định chuyển giao product handle mới cho view. Nếu một factory trả singleton dùng chung, phải thiết kế ownership khác; không được dùng cơ chế close như ví dụ một cách máy móc.

### 5.4. SettingsHost: prepare trước, commit toàn bộ, rồi dọn bộ cũ

`SettingsHost` là controller chịu trách nhiệm giữ trạng thái nghiệp vụ và quản lý view đang hoạt động. Các phương thức `synchronized` mô phỏng một phạm vi đồng bộ đơn giản, tránh thao tác chuyển đổi đồng thời trong ví dụ dòng lệnh.

~~~java
record SwitchOutcome(
    boolean changed,
    RuntimeException cleanupError
) {
    boolean cleanupSucceeded() {
        return cleanupError == null;
    }
}

static final class SettingsHost implements AutoCloseable {
    private Theme selectedTheme;
    private boolean notificationsEnabled;
    private SettingsView activeView;

    SettingsHost(UiFactory initialFactory, Theme initialTheme) {
        selectedTheme = Objects.requireNonNull(
            initialTheme, "initialTheme"
        );
        activeView = SettingsView.prepare(
            initialFactory, initialTheme, false
        );
    }

    synchronized Theme selectedTheme() {
        ensureOpen();
        return selectedTheme;
    }

    synchronized void setNotificationsEnabled(boolean enabled) {
        ensureOpen();
        // Chỉ cập nhật model khi thao tác trên view thành công.
        activeView.setNotificationsEnabled(enabled);
        notificationsEnabled = enabled;
    }

    synchronized boolean notificationsEnabled() {
        ensureOpen();
        return notificationsEnabled;
    }

    synchronized String render() {
        ensureOpen();
        return activeView.render();
    }

    synchronized SwitchOutcome changeTo(
            Theme target, UiFactory targetFactory) {

        ensureOpen();
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(targetFactory, "targetFactory");

        // Chính sách ví dụ: chọn lại đúng họ hiện tại là no-op.
        if (target == selectedTheme) {
            return new SwitchOutcome(false, null);
        }

        // PREPARE: nếu ném lỗi, activeView/theme vẫn nguyên.
        SettingsView replacement = SettingsView.prepare(
            targetFactory, target, notificationsEnabled
        );

        // COMMIT: công bố cả bộ mới trong cùng critical section.
        SettingsView previous = activeView;
        activeView = replacement;
        selectedTheme = target;

        // CLEANUP: lỗi ở đây là lỗi sau commit; phải báo riêng.
        RuntimeException cleanupError = null;
        try {
            previous.close();
        } catch (RuntimeException ex) {
            cleanupError = ex;
        }

        return new SwitchOutcome(true, cleanupError);
    }

    private void ensureOpen() {
        if (activeView == null) {
            throw new IllegalStateException("SettingsHost is closed");
        }
    }

    @Override
    public synchronized void close() {
        if (activeView != null) {
            SettingsView last = activeView;
            activeView = null;
            last.close();
        }
    }
}
~~~

**Trách nhiệm được chia rõ:**

- `SettingsHost` sở hữu `SettingsView` đang active.
- `SettingsView` sở hữu Button và Checkbox đã được tạo cho nó.
- Factory là dependency được truyền vào cho thao tác xây dựng; ví dụ này **không sở hữu hay đóng factory**.
- Model `notificationsEnabled` tồn tại ở `SettingsHost`, nên không bị mất khi tạo view mới.
- `changeTo()` không công bố view mới nếu bước tạo hoặc kiểm tra họ thất bại.

Chính sách **no-op khi chọn lại cùng họ** nhằm tránh tạo tài nguyên không cần thiết. Nếu ứng dụng cần *reload* theme hiện tại sau khi cấu hình thay đổi, hãy định nghĩa thao tác `refresh()` riêng hoặc một cờ cho phép rebuild; không lén đổi nghĩa của no-op.

Đối với giao diện có nhiều thread và render bất đồng bộ, `synchronized` không tự động đồng bộ với event loop của UI framework. Cần điều phối các callback/in-flight operation và commit trên luồng mà framework quy định; phần 10 phân tích thêm.

### 5.5. Composition root: nơi chọn concrete factory

Đoạn cuối nằm trong cùng `ControlledSwitchDemo`:

~~~java
public static void main(String[] args) {
    // Chỉ composition root biết concrete factory nào được chọn.
    try (SettingsHost host = new SettingsHost(
            new LightUiFactory(), Theme.LIGHT)) {

        host.setNotificationsEnabled(true);
        System.out.println(host.render());

        SwitchOutcome outcome = host.changeTo(
            Theme.DARK, new DarkUiFactory()
        );

        if (!outcome.cleanupSucceeded()) {
            // Ứng dụng thật nên dùng logger/monitoring phù hợp.
            System.err.println(
                "Old-view cleanup failed: "
                    + outcome.cleanupError().getMessage()
            );
        }

        System.out.println(host.render());
        System.out.println(
            "Current theme: " + host.selectedTheme()
        );
        System.out.println(
            "Notifications: " + host.notificationsEnabled()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ControlledSwitchDemo.java
java ControlledSwitchDemo
~~~

Output dự kiến:

~~~text
LightButton | LightCheckbox(true)
DarkButton | DarkCheckbox(true)
Current theme: DARK
Notifications: true
~~~

`notificationsEnabled` vẫn là `true` sau khi chuyển sang Dark. Đây là bằng chứng trong ví dụ rằng **trạng thái nghiệp vụ ở host được áp lại cho sản phẩm mới**.

Lưu ý các đoạn 5.1–5.5 là **các phần của một file Java duy nhất**. Không đặt các class lồng `static` ở cấp top-level. Nếu sử dụng package trong dự án thực, giữ cùng package cho file test truy cập các nested type package-private.

## 6. Vì sao việc thay biến factory đơn thuần là sai?

Một client có thể giữ cả factory lẫn product lâu dài:

~~~java
final class BrokenSettingsScreen {
    private UiFactory factory;
    private final Button button;
    private final Checkbox checkbox;

    BrokenSettingsScreen(UiFactory factory) {
        this.factory = factory;
        this.button = factory.createButton();
        this.checkbox = factory.createCheckbox();
    }

    void selectDark() {
        factory = new DarkUiFactory();
        // button và checkbox vẫn là sản phẩm từ factory cũ.
    }
}
~~~

Sau `selectDark()`, `factory` trỏ tới Dark nhưng product fields vẫn trỏ tới Light. Không có thao tác tự động nào của Abstract Factory cập nhật những reference ấy.

Đoạn này là **phác thảo lỗi**, dựa trên các interface của ví dụ và minh họa sự cố. Các product cũ còn đang nắm tài nguyên thì việc chỉ thay factory còn có thể gây rò rỉ.

Thay thế đúng cần làm theo một chính sách tường minh:

1. **Tạo lại toàn bộ những sản phẩm phụ thuộc họ** trong một phạm vi nhất quán.
2. **Chuyển trạng thái nghiệp vụ cần giữ** vào sản phẩm mới.
3. **Thay toàn bộ tham chiếu có thể quan sát** một cách được điều phối.
4. **Dọn sản phẩm cũ** khi đã xác nhận không còn consumer nào sử dụng.

Một số UI framework cho phép đổi theme bằng **style tokens trên cùng widget** thay vì tạo widget mới. Nếu product có hợp đồng cập nhật theme trực tiếp và bảo đảm nhất quán, đó có thể là hướng khác. Nhưng **khi kiến trúc Abstract Factory đã tạo các concrete product phụ thuộc họ và chúng không hỗ trợ tự đổi họ**, chỉ thay factory vẫn không đủ: cần tái tạo sản phẩm hoặc thiết kế cơ chế cập nhật có chủ đích.

## 7. Ma trận trạng thái trước, trong và sau khi chuyển đổi

| Thời điểm | `selectedTheme` | View đang active | Giá trị checkbox | Điều kiện |
| --- | --- | --- | --- | --- |
| Khởi tạo Light | LIGHT | LightButton + LightCheckbox | false | Sẵn sàng nhận thao tác |
| Người dùng bật thông báo | LIGHT | LightButton + LightCheckbox | true | Model của host cũng là true |
| Bắt đầu chuẩn bị Dark | LIGHT | **Vẫn là Light** | true | Product Dark chưa công bố |
| Chuẩn bị Dark thành công | LIGHT | Vẫn là Light trước commit | true | Các product Dark đã được kiểm tra |
| Commit | DARK | DarkButton + DarkCheckbox | true | Cùng lúc đổi view + theme trong vùng đồng bộ |
| Cleanup | DARK | Dark tiếp tục hoạt động | true | Đóng sản phẩm Light cũ |

Nếu trong bước chuẩn bị Dark xuất hiện lỗi, bảng dừng ở trạng thái **Light đang hoạt động**. Không có giai đoạn active chứa DarkButton nhưng LightCheckbox.

Khi sản phẩm mới cần tài nguyên tốn kém (ảnh, network, session), giai đoạn chuẩn bị đôi khi phải dùng buffer hoặc màn hình tạm chưa gắn lên UI. Chỉ gắn view mới vào cây hiển thị sau khi đạt điều kiện commit.

## 8. Phân biệt rollback trước commit và lỗi cleanup sau commit

### 8.1. Lỗi khi dựng view mới

Có thể xảy ra ở nhiều thời điểm:

- `createButton()` ném exception trước khi trả sản phẩm.
- `createButton()` thành công nhưng `createCheckbox()` ném exception.
- Factory trả `null`.
- Factory trả Checkbox khác họ so với theme đích.
- Product mới không nhận được trạng thái nghiệp vụ (`setChecked` lỗi).
- Tài nguyên trong concrete product không thể khởi tạo (file, socket, native view).

Trong mọi trường hợp **trước commit**, `SettingsView.prepare()` giữ danh sách handle đã nhận, đóng chúng rồi ném lỗi. `SettingsHost.changeTo()` chưa đổi `activeView` hoặc `selectedTheme`, vì thế user vẫn nhìn thấy màn hình cũ.

**Trách nhiệm cleanup được phân định:** Nếu concrete factory mở tài nguyên phụ nhưng ném lỗi *trước khi trả product*, chính factory phải dọn tài nguyên chưa chuyển giao. `SettingsView` chỉ có thể đóng các handle đã được factory trả về thành công.

### 8.2. Lỗi khi đóng sản phẩm cũ

Sau commit, người dùng đã chuyển sang Dark. Nếu `LightCheckbox.close()` lỗi:

- `SettingsView.close()` vẫn thử đóng `LightButton`.
- `SettingsHost.changeTo()` trả `SwitchOutcome(changed=true, cleanupError=...)`.
- Client cần **kiểm tra `cleanupSucceeded()`** và ghi log/cảnh báo hoặc chuyển lỗi tới cơ chế xử lý tài nguyên.
- Không tự đặt lại theme thành Light: bộ Light có thể đã đóng một phần và không còn hoạt động.

Trong code thực, hậu quả của cleanup failure cần được xác định theo loại tài nguyên: có thể ghi nhận và tiếp tục, thử dọn lại theo cơ chế an toàn, hoặc báo mức độ nghiêm trọng cao nếu nguy cơ rò rỉ. Việc thử lại close chỉ đúng nếu contract resource cho phép.

### 8.3. Không đổi họ nếu các thao tác cũ còn phụ thuộc tài nguyên

Nếu Button cũ đang phát sự kiện, một animation chưa kết thúc hoặc một request bất đồng bộ vẫn dùng renderer cũ, việc đóng ngay có thể sai. Có ba lựa chọn kiến trúc:

- **Đợi hoặc hủy có kiểm soát** công việc cũ rồi mới cleanup.
- **Ngắt listener và vô hiệu hóa view cũ**, bảo đảm callback không dùng tài nguyên đã đóng.
- **Giữ lease/refcount** cho đến khi consumer cuối cùng hoàn tất nếu cần chạy song song qua giai đoạn chuyển đổi.

Cách chọn phụ thuộc UI framework và hợp đồng sản phẩm. Trong demo đồng bộ, không có callback hay task đang chạy, nên `previous.close()` ngay sau commit là hợp lệ.

## 9. Kiểm thử chuyển họ với factory có thể ghi nhận

Một bản test tốt phải kiểm tra **họ mới được dùng**, **model vẫn được giữ**, **handle cũ được đóng**, và **thất bại chuẩn bị không phá màn hình cũ**. Chỉ xác nhận chuỗi Dark xuất hiện là chưa đủ.

Các test sau dùng JUnit Jupiter 5 và class `ControlledSwitchDemo` từ mục 5. Đặt trong file `ControlledSwitchDemoTest.java` cùng package.

### 9.1. Factory giả theo dõi việc tạo và đóng

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ControlledSwitchDemoTest {

    static final class RecordingButton
            implements ControlledSwitchDemo.Button {

        final ControlledSwitchDemo.Theme theme;
        final boolean failClose;
        int closeCalls;

        RecordingButton(
                ControlledSwitchDemo.Theme theme, boolean failClose) {
            this.theme = theme;
            this.failClose = failClose;
        }

        @Override
        public ControlledSwitchDemo.Theme theme() {
            return theme;
        }

        @Override
        public String render() {
            return "RecordingButton";
        }

        @Override
        public void close() {
            closeCalls++;
            if (failClose) {
                throw new IllegalStateException("forced close failure");
            }
        }
    }

    static final class RecordingCheckbox
            implements ControlledSwitchDemo.Checkbox {

        final ControlledSwitchDemo.Theme theme;
        boolean checked;
        int closeCalls;

        RecordingCheckbox(ControlledSwitchDemo.Theme theme) {
            this.theme = theme;
        }

        @Override
        public ControlledSwitchDemo.Theme theme() {
            return theme;
        }

        @Override
        public boolean isChecked() {
            return checked;
        }

        @Override
        public void setChecked(boolean checked) {
            this.checked = checked;
        }

        @Override
        public String render() {
            return "RecordingCheckbox(" + checked + ")";
        }

        @Override
        public void close() {
            closeCalls++;
        }
    }

    static final class RecordingFactory
            implements ControlledSwitchDemo.UiFactory {

        final ControlledSwitchDemo.Theme buttonTheme;
        final ControlledSwitchDemo.Theme checkboxTheme;
        final boolean failCheckboxCreation;
        final boolean failButtonClose;

        RecordingButton button;
        RecordingCheckbox checkbox;

        RecordingFactory(
                ControlledSwitchDemo.Theme buttonTheme,
                ControlledSwitchDemo.Theme checkboxTheme,
                boolean failCheckboxCreation,
                boolean failButtonClose) {
            this.buttonTheme = buttonTheme;
            this.checkboxTheme = checkboxTheme;
            this.failCheckboxCreation = failCheckboxCreation;
            this.failButtonClose = failButtonClose;
        }

        @Override
        public ControlledSwitchDemo.Button createButton() {
            button = new RecordingButton(buttonTheme, failButtonClose);
            return button;
        }

        @Override
        public ControlledSwitchDemo.Checkbox createCheckbox() {
            if (failCheckboxCreation) {
                throw new IllegalStateException("cannot create checkbox");
            }
            checkbox = new RecordingCheckbox(checkboxTheme);
            return checkbox;
        }
    }

    // Đặt các test của mục 9.2 trong class này.
}
~~~

### 9.2. Bộ test cho các đường chuyển đổi quan trọng

~~~java
@Test
void switching_preserves_state_and_closes_old_products() {
    var light = new RecordingFactory(
        ControlledSwitchDemo.Theme.LIGHT,
        ControlledSwitchDemo.Theme.LIGHT,
        false, false
    );
    var dark = new RecordingFactory(
        ControlledSwitchDemo.Theme.DARK,
        ControlledSwitchDemo.Theme.DARK,
        false, false
    );

    try (var host = new ControlledSwitchDemo.SettingsHost(
            light, ControlledSwitchDemo.Theme.LIGHT)) {

        host.setNotificationsEnabled(true);

        var result = host.changeTo(
            ControlledSwitchDemo.Theme.DARK, dark
        );

        assertTrue(result.changed());
        assertTrue(result.cleanupSucceeded());
        assertEquals(ControlledSwitchDemo.Theme.DARK,
            host.selectedTheme());
        assertTrue(host.notificationsEnabled());
        assertTrue(dark.checkbox.isChecked());

        assertEquals(1, light.button.closeCalls);
        assertEquals(1, light.checkbox.closeCalls);
        assertEquals(0, dark.button.closeCalls);
        assertEquals(0, dark.checkbox.closeCalls);
    }

    // Khi host đóng, product Dark cũng được đóng đúng một lần.
    assertEquals(1, dark.button.closeCalls);
    assertEquals(1, dark.checkbox.closeCalls);
}

@Test
void failing_to_create_new_product_keeps_old_view() {
    var light = new RecordingFactory(
        ControlledSwitchDemo.Theme.LIGHT,
        ControlledSwitchDemo.Theme.LIGHT,
        false, false
    );
    var broken = new RecordingFactory(
        ControlledSwitchDemo.Theme.DARK,
        ControlledSwitchDemo.Theme.DARK,
        true, false
    );

    try (var host = new ControlledSwitchDemo.SettingsHost(
            light, ControlledSwitchDemo.Theme.LIGHT)) {

        host.setNotificationsEnabled(true);
        String oldRender = host.render();

        assertThrows(IllegalStateException.class, () ->
            host.changeTo(ControlledSwitchDemo.Theme.DARK, broken));

        assertEquals(oldRender, host.render());
        assertEquals(ControlledSwitchDemo.Theme.LIGHT,
            host.selectedTheme());
        assertTrue(host.notificationsEnabled());

        assertEquals(1, broken.button.closeCalls);
        assertEquals(0, light.button.closeCalls);
        assertEquals(0, light.checkbox.closeCalls);
    }
}

@Test
void mixed_family_is_rejected_before_commit() {
    var light = new RecordingFactory(
        ControlledSwitchDemo.Theme.LIGHT,
        ControlledSwitchDemo.Theme.LIGHT,
        false, false
    );
    var mixed = new RecordingFactory(
        ControlledSwitchDemo.Theme.DARK,
        ControlledSwitchDemo.Theme.LIGHT,
        false, false
    );

    try (var host = new ControlledSwitchDemo.SettingsHost(
            light, ControlledSwitchDemo.Theme.LIGHT)) {

        assertThrows(IllegalStateException.class, () ->
            host.changeTo(ControlledSwitchDemo.Theme.DARK, mixed));

        assertEquals(ControlledSwitchDemo.Theme.LIGHT,
            host.selectedTheme());
        assertEquals(1, mixed.button.closeCalls);
        assertEquals(1, mixed.checkbox.closeCalls);
        assertEquals(0, light.button.closeCalls);
    }
}

@Test
void old_view_cleanup_failure_does_not_undo_commit() {
    var light = new RecordingFactory(
        ControlledSwitchDemo.Theme.LIGHT,
        ControlledSwitchDemo.Theme.LIGHT,
        false, true // LightButton.close() cố ý lỗi
    );
    var dark = new RecordingFactory(
        ControlledSwitchDemo.Theme.DARK,
        ControlledSwitchDemo.Theme.DARK,
        false, false
    );

    try (var host = new ControlledSwitchDemo.SettingsHost(
            light, ControlledSwitchDemo.Theme.LIGHT)) {

        var result = host.changeTo(
            ControlledSwitchDemo.Theme.DARK, dark);

        assertTrue(result.changed());
        assertFalse(result.cleanupSucceeded());
        assertNotNull(result.cleanupError());
        assertEquals("forced close failure",
            result.cleanupError().getMessage());

        // Commit đã xong, host không trở lại view Light.
        assertEquals(ControlledSwitchDemo.Theme.DARK,
            host.selectedTheme());
        assertEquals(1, light.button.closeCalls);
        assertEquals(1, light.checkbox.closeCalls);
    }
}

@Test
void selecting_same_theme_is_a_no_op() {
    var light = new RecordingFactory(
        ControlledSwitchDemo.Theme.LIGHT,
        ControlledSwitchDemo.Theme.LIGHT,
        false, false
    );
    try (var host = new ControlledSwitchDemo.SettingsHost(
            light, ControlledSwitchDemo.Theme.LIGHT)) {

        var result = host.changeTo(
            ControlledSwitchDemo.Theme.LIGHT, light);

        assertFalse(result.changed());
        assertTrue(result.cleanupSucceeded());
        assertEquals(0, light.button.closeCalls);
        assertEquals(0, light.checkbox.closeCalls);
    }
}
~~~

Đặt các phương thức `@Test` bên trong `ControlledSwitchDemoTest` của mục 9.1. Vì `SettingsHost` lồng trong `ControlledSwitchDemo` và các class nằm cùng package, test có thể truy cập các nested type không `private` trong ví dụ.

### 9.3. Ma trận bao phủ

| Test | Chuyển họ | Prepare | Commit | Cleanup | Kết quả mong đợi |
| --- | --- | --- | --- | --- | --- |
| `switching_preserves_state_and_closes_old_products` | Light → Dark | Thành công | Có | Thành công | Dark active; model giữ nguyên; Light đã đóng |
| `failing_to_create_new_product_keeps_old_view` | Light → Dark | Lỗi giữa chừng | Không | Dọn product Dark đã tạo | Light vẫn active |
| `mixed_family_is_rejected_before_commit` | Light → Dark | Product trộn họ | Không | Dọn cả bộ mới | Light vẫn active |
| `old_view_cleanup_failure_does_not_undo_commit` | Light → Dark | Thành công | Có | Báo lỗi | Dark active; lỗi cleanup được quan sát |
| `selecting_same_theme_is_a_no_op` | Light → Light | Bỏ qua | Không | Không | Không tạo/đóng product mới |

Các test minh họa là **mã nguồn đề xuất**, không phải kết quả thực thi đã thu thập. Khi áp dụng vào hệ thống thật, cần bổ sung chiều Dark → Light, test lỗi từ `setChecked`, thiếu product, và kiểm thử resource/handler mà UI framework sử dụng.

## 10. Khi có nhiều thread, event loop hoặc công việc bất đồng bộ

Ví dụ dùng `synchronized` để bảo đảm các thao tác trên `SettingsHost` chạy lần lượt và không công bố view đang tạo dở. Với ứng dụng nhiều thread hoặc UI thật, việc chuyển đổi đòi hỏi thêm cơ chế điều phối:

**UI thread:** Widget thường phải được tạo, gắn hoặc hủy trên thread do framework quy định. Không xây dựng/cập nhật cây UI trên worker thread nếu framework cấm. Có thể preload asset ngoài UI thread rồi commit thao tác gắn view trên UI thread.

**Tác vụ đang chạy:** Một callback hoặc request cũ có thể giữ reference tới product Light khi host đã chuyển Dark. Trước cleanup cần ngắt listener hoặc đảm bảo các lượt sử dụng product cũ đã hoàn tất. Chỉ khóa ở host không bảo vệ những reference đã bị phát tán ra ngoài.

**Hai yêu cầu đổi theme gần nhau:** Người dùng chọn Dark, ngay sau đó chọn Light. Nếu bước prepare bất đồng bộ, kết quả Dark đến muộn có thể ghi đè lựa chọn Light mới hơn. Có thể gắn **revision/generation number** vào mỗi yêu cầu và chỉ commit khi request vẫn là mới nhất:

~~~text
request#41: chọn DARK → bắt đầu chuẩn bị Dark
request#42: chọn LIGHT → bắt đầu chuẩn bị Light
request#42: hoàn tất trước → kiểm tra revision=42 → commit Light
request#41: hoàn tất sau → revision=41 đã cũ → hủy view Dark vừa tạo
~~~

Kỹ thuật revision cần đi kèm cleanup khi bỏ kết quả và kiểm tra đồng bộ khi commit. Nếu trạng thái nghiệp vụ có thể thay đổi trong lúc chuẩn bị, hoặc giữ model lock đến lúc snapshot/commit phù hợp, hoặc **áp dụng lại snapshot mới nhất ngay trước commit**; tránh đưa state đã lỗi thời vào view mới.

**Không khóa xuyên qua tác vụ mạng chậm:** Phương thức `synchronized changeTo()` trong demo gọi prepare đồng bộ bên trong lock vì sản phẩm giả lập rất nhẹ. Với factory gọi mạng hoặc có thể chờ lâu, nên chia quá trình thành prepare bên ngoài critical section, sau đó validate revision và commit ngắn gọn bên trong. Việc đó cũng cần xác định rõ bên nào sở hữu/cancel tài nguyên chuẩn bị dở.

## 11. Chọn concrete factory mà không làm client phụ thuộc concrete class

Để `SettingsHost` không biết cách tạo `LightUiFactory` hay `DarkUiFactory`, điểm điều phối bên ngoài có thể có hàm:

~~~java
static ControlledSwitchDemo.UiFactory selectFactory(
        ControlledSwitchDemo.Theme theme) {
    return switch (theme) {
        case LIGHT -> new ControlledSwitchDemo.LightUiFactory();
        case DARK -> new ControlledSwitchDemo.DarkUiFactory();
    };
}
~~~

Cách chọn này là mã **composition root**, không phải logic của `SettingsView`. Khi người dùng chọn Dark, controller ngoài gọi:

~~~java
var target = ControlledSwitchDemo.Theme.DARK;
var factory = selectFactory(target);
var result = host.changeTo(target, factory);
~~~

`host` ở đây là `ControlledSwitchDemo.SettingsHost` đã được tạo trước đó; đoạn code chỉ minh họa lời gọi từ adapter ngoài. Trong hệ thống thật có DI container, config map hoặc plugin registry, bước chọn factory có thể đi qua một registry; nguyên tắc vẫn giữ: **client cần sản phẩm chỉ nhìn thấy interface**.

Để tránh truyền nhầm theme và factory, có thể đưa việc chọn thành một đối tượng cấu hình đáng tin cậy `FactorySelection(theme, factory)` hoặc thiết kế resolver xác nhận binding. Mặc dù có thêm object, các test vẫn cần kiểm tra kết quả thực tế do factory trả về, vì một binding sai có thể gắn nhầm concrete factory.

## 12. Những cách đổi họ dễ gây lỗi

### 12.1. Thay factory nhưng giữ sản phẩm cũ

Đây là lỗi gốc: tham chiếu factory mới không cập nhật các product đã cấp phát. Hệ quả thường xuất hiện khi client lưu product thành field nhưng thao tác đổi theme chỉ cập nhật field factory.

### 12.2. Thay Button ngay, đến Checkbox mới thay sau

Nếu view đang hoạt động được cập nhật từng phần, callback hoặc render có thể quan sát một màn hình trộn họ. Chuẩn bị đủ bộ, validate, sau đó commit bằng cơ chế đồng bộ với framework.

### 12.3. Tạo xong product mới rồi quên trạng thái nghiệp vụ

Nếu Checkbox mới mặc định `false`, người dùng có thể mất trạng thái đã bật. Lưu state tại model/controller; áp dụng lại sau khi khởi tạo và trước commit.

### 12.4. Đóng sản phẩm cũ trước khi biết họ mới có tạo được không

Nếu tạo Dark thất bại sau khi đã đóng Light, ứng dụng không có view hoạt động. Ưu tiên chuẩn bị bộ mới trong khi view cũ còn an toàn, rồi đóng cái cũ sau commit. Nếu tài nguyên chỉ cho phép mở một họ tại một thời điểm, cần một giao thức chuyển đổi khác có checkpoint/khôi phục rõ ràng; không được tuyên bố quy trình prepare song song luôn khả thi.

### 12.5. Factory trả sản phẩm thuộc sai họ nhưng vẫn đúng interface

`DarkUiFactory.createCheckbox()` trả về `LightCheckbox` vẫn có thể biên dịch vì cả hai đều thực hiện `Checkbox`. Phải kiểm tra invariant của họ, không chỉ `instanceof Checkbox` hoặc `not null`.

### 12.6. Nuốt lỗi cleanup sau commit

Việc đóng product cũ có thể thất bại và rò rỉ listener/session/handle. `SwitchOutcome.cleanupError` trong ví dụ giữ lỗi này để caller đưa vào log hoặc cơ chế xử lý. Đừng báo “đã dọn sạch” nếu thực tế chưa dọn xong.

### 12.7. Giao product reference cho component ngoài mà không quản lý vòng đời

Nếu một component khác giữ trực tiếp `LightButton` sau khi host đổi Dark, việc đóng hoặc tái tạo trong host không khiến reference đó được cập nhật. Dùng facade ổn định, API lấy snapshot trạng thái, thông báo thay view, hoặc cơ chế ownership/lease rõ ràng; ngăn caller tiếp tục dùng product cũ đã đóng.

### 12.8. Tái dùng một product instance giữa hai họ không có hợp đồng rõ

Để tiết kiệm chi phí, factory có thể cache sản phẩm. Nếu cùng instance dùng cho nhiều phiên hoặc nhiều theme, cần bảo đảm product thật sự có thể đổi họ, state độc lập và việc close không ảnh hưởng các consumer khác. Không giả định `createX()` luôn trả instance mới hoặc luôn trả shared instance; quyết định nằm ở product/factory contract.

## 13. Quy trình áp dụng vào code production

1. **Vẽ đường sở hữu:** Xác định controller nào giữ factory, component nào giữ product, resource nào do bootstrap/pool sở hữu.
2. **Lập danh sách phụ thuộc họ:** Widget, service adapter, renderer, formatter, listener, subscription, model view… chỉ đưa vào rebuild những phần phụ thuộc họ, không xóa trạng thái nghiệp vụ.
3. **Đặt invariant:** Tập product cần nhất quán; kiểm tra loại, họ, dữ liệu bắt buộc và trạng thái phục hồi.
4. **Thiết kế prepare:** Xây view mới tách khỏi view active, dọn toàn bộ resource đã tạo nếu gặp lỗi.
5. **Thiết kế commit:** Chỉ công bố view mới khi đủ điều kiện; đồng bộ trên đúng luồng, chặn yêu cầu chuyển đổi cũ ghi đè yêu cầu mới.
6. **Thiết kế cleanup:** Ngắt callback, hoàn tất hoặc hủy task cũ, đóng tài nguyên theo thứ tự; báo lỗi cleanup sau commit.
7. **Viết test:** Thành công cả hai chiều, lỗi khi tạo từng loại, sai họ, no-op, trạng thái nghiệp vụ, lỗi đóng, đa luồng/bất đồng bộ nếu có.
8. **Đo lường thực tế:** Theo dõi thời gian đổi theme, số resource đang mở, lỗi initialization và cleanup, đồng thời kiểm tra không có màn hình trộn họ.

Quy trình này cũng áp dụng khi chuyển family là **database driver**, **họ formatter xuất báo cáo**, **nhà cung cấp dịch vụ** hay **bộ UI widget**; chỉ khác thứ tự đóng và dữ liệu nào cần chuyển.

## 14. Bài tập thực hành

Một ứng dụng báo cáo có hai factory:

- `PdfReportFactory` tạo `PdfHeader` và `PdfTable`.
- `HtmlReportFactory` tạo `HtmlHeader` và `HtmlTable`.

Người dùng đang soạn báo cáo PDF có bộ lọc ngày, danh sách dòng được chọn và phần ghi chú chưa lưu. Khi đổi định dạng xuất từ PDF sang HTML, ứng dụng phải dùng Header/Table của HTML nhưng **không được mất** các giá trị đang soạn.

**Yêu cầu:**

1. Xác định trạng thái nào là nghiệp vụ cần giữ và thành phần nào là product phụ thuộc họ phải tạo lại.
2. Vẽ sequence diagram cho yêu cầu `PDF → HTML` với giai đoạn prepare, validate, commit, cleanup.
3. Giả sử `HtmlTable` ném exception trong constructor: quy định ai đóng `HtmlHeader` đã tạo và view nào còn hoạt động.
4. Giả sử `PdfHeader.close()` lỗi **sau khi HTML đã được commit**: hệ thống nên hiển thị định dạng nào và báo lỗi ra sao?
5. Viết `ReportHost.changeTo(ExportFormat target, ExportFactory factory)` dùng factory qua interface và trả kết quả có thể phân biệt lỗi chuẩn bị với lỗi cleanup.
6. Viết test từ `PDF → HTML` và `HTML → PDF` xác nhận cả hai product cùng định dạng; bổ sung test hai lệnh đổi liên tiếp trong môi trường bất đồng bộ.

**Gợi ý:** Lưu bộ lọc ngày, dòng được chọn và ghi chú tại `ReportModel`. `ReportView` chỉ sở hữu Header/Table cùng định dạng. Prepare HTML phải thành công trước khi công bố; nếu lỗi, giữ PDF. Sau commit, cleanup PDF có lỗi thì theo dõi lỗi resource nhưng không quay lại một view PDF có thể đã đóng dở.

## 15. Checklist tự đánh giá

- [ ] Việc chọn biến thể được thực hiện ở composition root/selector, không nằm rải rác trong client.
- [ ] Đổi factory đồng thời xác định **những product cũ nào phải thay**, không chỉ đổi reference factory.
- [ ] Trạng thái nghiệp vụ nằm ngoài các product phụ thuộc họ hoặc có cơ chế snapshot/restore rõ ràng.
- [ ] Bộ product mới được tạo đầy đủ và kiểm tra **đúng họ** trước commit.
- [ ] Khi prepare/validate lỗi, mọi handle mới đã nhận được cleanup và view cũ tiếp tục hoạt động.
- [ ] Commit bảo đảm consumer không quan sát view trộn họ hoặc trạng thái nửa chuyển đổi.
- [ ] Product cũ được đóng theo quyền sở hữu sau khi không còn lượt sử dụng nào phụ thuộc chúng.
- [ ] Lỗi cleanup **sau commit** được báo riêng; không tự động coi đó là rollback.
- [ ] Yêu cầu đổi lặp/no-op có chính sách rõ ràng.
- [ ] Khi có async hoặc nhiều thread, yêu cầu cũ không thể ghi đè yêu cầu mới và các callback cũ không dùng resource đã đóng.
- [ ] Test có cả đường thành công, rollback trước commit, sai họ và cleanup failure.

## 16. Ghi nhớ

Trong Abstract Factory, factory quyết định **họ của những sản phẩm được tạo ở lần gọi tiếp theo**; nó không biến đổi những sản phẩm đã tồn tại. Vì vậy, đổi biến thể an toàn cần xác định lại **toàn bộ tập sản phẩm phụ thuộc họ cũ** và chuyển đổi theo quy trình **chuẩn bị → kiểm tra → commit → dọn dẹp**. Giữ trạng thái nghiệp vụ trong model, chỉ công bố bộ mới khi đã nhất quán, và xử lý tách biệt lỗi trước/sau commit để hệ thống vừa bảo toàn dữ liệu, vừa kiểm soát tốt vòng đời tài nguyên.
