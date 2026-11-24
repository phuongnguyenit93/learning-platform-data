# Giới hạn API và constructor để giảm khả năng trộn họ ngoài ý muốn

Trong **Abstract Factory**, mỗi concrete factory thường tạo ra một **họ sản phẩm tương thích**. Chẳng hạn, `WindowsUiFactory` tạo nút và checkbox theo Windows, còn `MacUiFactory` tạo nút và checkbox theo macOS. Tuy nhiên, chỉ viết phương thức `createButton()` và `createCheckbox()` chưa đủ để ngăn client vô tình trộn các sản phẩm thuộc hai họ.

Bài học thuộc chương **Bảo đảm tương thích** của module **Học về abstract factory trong design pattern**. Trọng tâm là **giới hạn bề mặt API và quyền gọi constructor** để nơi sử dụng không dễ tùy ý tạo, thay thế hoặc ghép chéo các sản phẩm. Đây là một kỹ thuật kiểm soát cấu trúc nhằm giảm lỗi, không phải lời hứa rằng mọi sự không tương thích đều được Java tự động phát hiện.

## 1. Trộn họ sản phẩm là gì và vì sao nguy hiểm?

Giả sử một ứng dụng có hai loại sản phẩm:

- `Button`: hiển thị nút và phản hồi thao tác nhấn.
- `Checkbox`: hiển thị lựa chọn và quản lý trạng thái được chọn.

Và hai họ triển khai:

| Họ sản phẩm | Button | Checkbox |
| --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacButton` | `MacCheckbox` |

Hai nút đều thực hiện interface `Button`; hai checkbox đều thực hiện interface `Checkbox`. Tính **tương thích về interface** cho phép client gọi cùng phương thức, nhưng **tương thích trong một họ** còn có thể bao gồm quy ước giao diện, đơn vị đo, phiên bản giao thức, cách quản lý tài nguyên hoặc cơ chế phát sự kiện.

Ví dụ, một màn hình dùng `WindowsButton` cùng `MacCheckbox` có thể vẫn biên dịch được, nhưng:

- Các thành phần có màu sắc, kích thước hoặc cách xử lý phím tắt thiếu nhất quán.
- Trong một toolkit thật, mỗi widget có thể phụ thuộc một native event loop hoặc context riêng.
- Trong ví dụ không phải UI, `SqlTransaction` và `SqlStatement` được tạo từ hai connection khác nhau có thể làm sai ranh giới transaction.

**Mục tiêu thiết kế:** tại mỗi ranh giới sử dụng, client nhận được một **bộ sản phẩm được cấu hình nhất quán**, trong khi lựa chọn họ nằm ở một nơi có trách nhiệm rõ ràng.

## 2. Abstract Factory bảo đảm được điều gì?

Interface factory điển hình:

```java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
```

Hai phương thức trả về các **product interface** nên client không cần quan tâm lớp cụ thể. Concrete factory có thể chọn một họ:

```java
final class WindowsUiFactory implements UiFactory {
    public Button createButton() { return new WindowsButton(); }
    public Checkbox createCheckbox() { return new WindowsCheckbox(); }
}
```

Nếu client **chỉ gọi các phương thức trên cùng một factory được cung cấp**, các sản phẩm nhận về sẽ thuộc cùng họ **khi concrete factory được cài đặt đúng**.

Nhưng interface `UiFactory` tự nó không tạo ra một ràng buộc ở mức kiểu rằng `createButton()` và `createCheckbox()` nhất thiết trả về cùng họ. Một implementation lỗi vẫn có thể trả về sản phẩm Windows ở phương thức đầu và macOS ở phương thức sau.

Do đó cần phân biệt ba lớp bảo đảm:

1. **Thiết kế API:** giới hạn đường đi khiến client không dễ chọn từng sản phẩm một cách độc lập.
2. **Cài đặt factory:** mỗi concrete factory thực sự tạo đúng những sản phẩm thuộc họ của mình.
3. **Kiểm thử và kiểm tra tích hợp:** xác minh các quy tắc tương thích về hành vi, vòng đời và môi trường chạy mà kiểu dữ liệu chung không biểu đạt hết.

## 3. Phản ví dụ: Public constructor cho phép ghép chéo

Giả sử các product interface đã tồn tại nhưng client được tự lắp màn hình:

```java
interface Button {
    void click();
}

interface Checkbox {
    boolean isChecked();
}

final class SettingsScreen {
    private final Button saveButton;
    private final Checkbox notifications;

    public SettingsScreen(Button saveButton, Checkbox notifications) {
        this.saveButton = saveButton;
        this.notifications = notifications;
    }
}
```

Khi hai concrete factory cùng xuất hiện trong client, lời gọi sau có thể hợp lệ về mặt kiểu:

```java
UiFactory windows = new WindowsUiFactory();
UiFactory mac = new MacUiFactory();

SettingsScreen screen = new SettingsScreen(
    windows.createButton(),  // Nút Windows
    mac.createCheckbox()     // Checkbox macOS
);
```

Vấn đề không nằm ở việc `Button` và `Checkbox` là interface. Vấn đề là **API của `SettingsScreen` nhận hai sản phẩm tách rời**, nên bất kỳ client nào cũng có quyền chọn và phối hợp chúng.

Một đường đi nguy hiểm tương tự là để constructor sản phẩm cụ thể công khai:

```java
public WindowsButton() { /* ... */ }
public MacCheckbox() { /* ... */ }
```

Khi đó client có thể bỏ qua factory hoàn toàn. Factory vẫn tồn tại, nhưng không còn là nơi thống nhất quyết định họ sản phẩm.

Một dạng khác là API có setter độc lập:

```java
screen.setButton(windows.createButton());
screen.setCheckbox(mac.createCheckbox());
```

Kể cả màn hình được tạo đúng ban đầu, các setter này có thể phá vỡ tính nhất quán về sau. Nếu việc thay thế từng phần không phải yêu cầu nghiệp vụ, tránh cung cấp các lối chỉnh sửa đó trong public API.

## 4. Tư duy thiết kế: Giảm số đường tạo bộ sản phẩm không hợp lệ

Một hướng giải quyết là **để client chọn họ một lần**, còn thư viện tạo các thành phần liên quan qua cùng factory:

```text
Caller
  │
  ├── chọn Platform.WINDOWS hoặc Platform.MAC một lần
  ▼
UiKit.forPlatform(platform)   ← đầu vào public được kiểm soát
  │
  └── giữ một UiFactory nội bộ
         ├── createButton()
         └── createCheckbox()
                   │
                   ▼
          SettingsScreen(UiKit)
          nhận một bộ nhất quán
```

Thay vì `SettingsScreen(Button, Checkbox)`, ta cho client truyền một **family handle** (ở ví dụ là `UiKit`) và để màn hình tự yêu cầu cả hai thành phần qua handle đó. Cách này giúp constructor của màn hình thể hiện rõ yêu cầu: “Tôi cần **một họ widget**”, chứ không phải “Tôi cần hai widget tùy ý”.

Một số quyết định tương ứng:

| Bề mặt API | Thiết kế dễ trộn họ | Thiết kế hạn chế trộn họ |
| --- | --- | --- |
| Khởi tạo màn hình | `SettingsScreen(Button, Checkbox)` công khai | `SettingsScreen(UiKit)` công khai |
| Chọn họ | Hai tham số nền tảng độc lập cho nút và checkbox | Chọn một `Platform` cho cả bộ |
| Concrete product | Constructor `public` | Lớp triển khai và constructor được ẩn sau factory |
| Concrete factory | Caller tùy ý phối hợp nhiều factory | Một điểm cấu hình tạo ra family handle |
| Thay sản phẩm | Setter công khai cho từng thành phần | Không công khai setter trừ khi có yêu cầu cụ thể |
| Vòng đời | Client tùy ý dùng lại object có state | Factory/kit quy định khi nào tạo mới và khi nào chia sẻ |

**Giảm bề mặt API** ở đây có nghĩa là không cung cấp những thao tác mà client không cần, đặc biệt những thao tác dễ làm mất bất biến của một bộ sản phẩm.

## 5. Ví dụ Java hoàn chỉnh: Chọn họ một lần và ẩn constructor

Ví dụ Java 17 sau mô phỏng màn hình có nút Lưu và checkbox. Các concrete product và concrete factory được khai báo `private` bên trong lớp chứa ví dụ; caller bên ngoài không thể trực tiếp khởi tạo chúng. `UiKit` chỉ có constructor `private`, được cung cấp thông qua phương thức tạo có kiểm soát `forPlatform(...)`.

Lưu mã thành `Demo.java`:

```java
import java.util.Objects;

public final class Demo {
    private Demo() {}

    public enum Platform {
        WINDOWS, MAC
    }

    // Product interfaces
    public interface Button {
        String appearance();
        void setOnClick(Runnable action);
        void click();
    }

    public interface Checkbox {
        String appearance();
        void toggle();
        boolean isChecked();
    }

    // Abstract factory chỉ được dùng bên trong thư viện
    private interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Family handle: caller không thể tự phối hai factory
    public static final class UiKit {
        private final UiFactory factory;

        private UiKit(UiFactory factory) {
            this.factory = Objects.requireNonNull(factory);
        }

        public static UiKit forPlatform(Platform platform) {
            return switch (Objects.requireNonNull(platform)) {
                case WINDOWS -> new UiKit(new WindowsFactory());
                case MAC -> new UiKit(new MacFactory());
            };
        }

        // Chỉ thành phần nội bộ được lấy từng sản phẩm
        private Button createButton() {
            return factory.createButton();
        }

        private Checkbox createCheckbox() {
            return factory.createCheckbox();
        }
    }

    // API công khai nhận đúng một family handle
    public static final class SettingsScreen {
        private final Button saveButton;
        private final Checkbox notifications;
        private int saveCount;

        public SettingsScreen(UiKit kit) {
            Objects.requireNonNull(kit);
            this.saveButton = kit.createButton();
            this.notifications = kit.createCheckbox();
            saveButton.setOnClick(() -> saveCount++);
        }

        public String preview() {
            return saveButton.appearance() + " | " + notifications.appearance();
        }

        public void toggleNotifications() {
            notifications.toggle();
        }

        public void clickSave() {
            saveButton.click();
        }

        public boolean notificationsEnabled() {
            return notifications.isChecked();
        }

        public int saveCount() {
            return saveCount;
        }
    }

    // Sản phẩm thuộc họ Windows: lớp/constructor ẩn
    private static final class WindowsButton implements Button {
        private Runnable action = () -> {};

        private WindowsButton() {}

        @Override
        public String appearance() {
            return "WindowsButton";
        }

        @Override
        public void setOnClick(Runnable action) {
            this.action = Objects.requireNonNull(action);
        }

        @Override
        public void click() {
            action.run();
        }
    }

    private static final class WindowsCheckbox implements Checkbox {
        private boolean checked;

        private WindowsCheckbox() {}

        @Override
        public String appearance() {
            return "WindowsCheckbox";
        }

        @Override
        public void toggle() {
            checked = !checked;
        }

        @Override
        public boolean isChecked() {
            return checked;
        }
    }

    // Sản phẩm thuộc họ macOS: lớp/constructor ẩn
    private static final class MacButton implements Button {
        private Runnable action = () -> {};

        private MacButton() {}

        @Override
        public String appearance() {
            return "MacButton";
        }

        @Override
        public void setOnClick(Runnable action) {
            this.action = Objects.requireNonNull(action);
        }

        @Override
        public void click() {
            action.run();
        }
    }

    private static final class MacCheckbox implements Checkbox {
        private boolean checked;

        private MacCheckbox() {}

        @Override
        public String appearance() {
            return "MacCheckbox";
        }

        @Override
        public void toggle() {
            checked = !checked;
        }

        @Override
        public boolean isChecked() {
            return checked;
        }
    }

    // Concrete factories tạo các sản phẩm đúng họ
    private static final class WindowsFactory implements UiFactory {
        private WindowsFactory() {}

        @Override
        public Button createButton() {
            return new WindowsButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    private static final class MacFactory implements UiFactory {
        private MacFactory() {}

        @Override
        public Button createButton() {
            return new MacButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    public static void main(String[] args) {
        Platform platform =
            args.length > 0 && args[0].equalsIgnoreCase("mac")
                ? Platform.MAC
                : Platform.WINDOWS;

        UiKit kit = UiKit.forPlatform(platform);
        SettingsScreen screen = new SettingsScreen(kit);
        System.out.println(screen.preview());

        screen.toggleNotifications();
        screen.clickSave();
        System.out.println(
            "notifications=" + screen.notificationsEnabled()
                + ", saves=" + screen.saveCount()
        );
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac Demo.java
java Demo windows
java Demo mac
```

Với `java Demo mac`, kết quả minh họa:

```text
MacButton | MacCheckbox
notifications=true, saves=1
```

Với `java Demo windows`, dòng đầu là `WindowsButton | WindowsCheckbox`; trạng thái và số lần Lưu vẫn giống nhau.

Ở mức minh họa, `appearance()` chỉ trả về tên kiểu widget để ta thấy rõ cách chọn họ. Trong UI thật, lớp cụ thể có thể vẽ native widget, gắn sự kiện và quản lý context; các hành vi người dùng vẫn phải thỏa interface chung.

### 5.1. Vì sao caller không dễ trộn sản phẩm?

- `SettingsScreen` chỉ công khai constructor nhận **một** `UiKit`; không có constructor nhận `Button` và `Checkbox` riêng.
- `UiKit.forPlatform(...)` là cách public duy nhất để lấy family handle; `UiKit` là `final`, constructor là `private`, và thuộc tính factory không thể thay đổi sau khởi tạo.
- `WindowsFactory`, `MacFactory` và các concrete product là lớp `private`, không có constructor public để mã bên ngoài gọi.
- Hai phương thức `UiKit.createButton()` và `UiKit.createCheckbox()` là `private`; caller không thể lấy từng sản phẩm rồi tự lắp ghép từ hai kit khác nhau. `SettingsScreen`, với tư cách lớp lồng trong cùng lớp bao, vẫn có thể truy cập chúng theo quy tắc **nestmate private access** của Java.

Ví dụ sau **không biên dịch được** trong một lớp client khác:

```java
// Không hợp lệ: các concrete product là private bên trong Demo.
new Demo.WindowsButton();
new Demo.MacCheckbox();

// Không hợp lệ: không có constructor nhận hai sản phẩm.
new Demo.SettingsScreen(buttonFromWindows, checkboxFromMac);
```

Phần kiểm soát này nằm ở **API công khai**. Mã bên trong `Demo` vẫn có quyền tạo hoặc trộn object nếu lập trình viên viết sai, vì vậy kiểm thử factory và review code vẫn cần thiết.

## 6. Chọn mức giới hạn constructor và visibility phù hợp

Java cung cấp nhiều mức tiếp cận, mỗi mức bảo vệ một phạm vi khác nhau:

| Cách giới hạn | Tác dụng | Giới hạn cần hiểu |
| --- | --- | --- |
| Constructor `private` | Chỉ mã có quyền truy cập private (ví dụ cùng nest) mới gọi trực tiếp được | Không thay thế kiểm thử hành vi hay tính đúng đắn của factory |
| Concrete class lồng `private` | Che hoàn toàn tên lớp triển khai khỏi API bên ngoài lớp bao | Mọi logic trong cùng nest vẫn có thể truy cập |
| Lớp/constructor package-private | Chặn mã từ package khác trong kiểm tra truy cập thông thường | Mọi lớp cùng package vẫn có thể tạo; cùng package không phải một ranh giới bảo vệ tuyệt đối |
| `final` cho family handle | Ngăn subclass thay thế hoặc sửa invariant bằng kế thừa | Không ngăn lỗi nằm ngay trong implementation |
| Factory interface không công khai | Client chỉ chọn thông qua một entry point đã kiểm soát | Khó hỗ trợ plugin bên ngoài nếu cần bên thứ ba tự cài factory |
| Chỉ nhận một `UiKit` thay vì hai product | Giảm khả năng ghép chéo ở constructor | Không chứng minh factory nội bộ luôn tạo đúng họ |

Trong thư viện Java có cấu trúc package/module rõ ràng, có thể đặt interfaces công khai trong gói API và các concrete class trong gói `internal` hoặc `impl`. Với JPMS, chỉ `exports` các package API cần thiết; không export package triển khai. Cách tổ chức này giúp giảm khả năng mã ngoài module phụ thuộc vào chi tiết cài đặt, nhưng việc hạn chế truy cập vẫn tùy cấu hình module và các cơ chế reflection; đây không phải một biện pháp bảo mật độc lập.

**Lưu ý:** Ẩn constructor không nhất thiết đồng nghĩa phải dùng singleton. Trong ví dụ, một `UiKit` có thể được dùng để tạo nhiều `SettingsScreen`, nhưng mỗi lần factory vẫn tạo ra `Button` và `Checkbox` **mới**. Nếu sản phẩm có trạng thái và bị chia sẻ tùy tiện, nhiều màn hình có thể ảnh hưởng nhau.

## 7. Các quy tắc API giúp duy trì bất biến của một họ

### 7.1. Chọn họ ở composition root

Hãy chọn `UiKit` theo nền tảng hoặc cấu hình lúc khởi động ứng dụng rồi inject nó vào nơi sử dụng. Tránh rải điều kiện `if (os == ...)` quanh từng màn hình; một nơi chọn họ giúp việc thay đổi cấu hình dễ kiểm soát hơn.

Nếu nhiều màn hình cần chung chủ đề, có thể truyền **cùng một kit**, nhưng cần phân biệt **chia sẻ factory** (thường hợp lý) với **chia sẻ widget có trạng thái** (phải được thiết kế cẩn thận).

### 7.2. Không nhận các product rời nếu client không cần

Constructor `SettingsScreen(UiKit)` làm mối liên hệ họ sản phẩm hiển nhiên. Ngược lại, hai tham số `Button` và `Checkbox` không cho biết chúng phải tương thích. Nếu cần cung cấp các sản phẩm rời vì yêu cầu tích hợp, hãy thiết kế một object chứa bộ sản phẩm được kiểm tra trước khi truyền, hoặc xác nhận tính tương thích ở boundary đó.

### 7.3. Tránh setter làm thay đổi riêng một thành viên của họ

Với API `setButton()`, `setCheckbox()`, client có thể thay từng thành phần tại runtime. Nếu sản phẩm phụ thuộc chung một event loop/context, thao tác thay riêng có thể phá bất biến.

Nếu thực sự cần chuyển chủ đề hoặc nền tảng lúc chạy, thiết kế phương thức ở **cấp bộ**, ví dụ `replaceKit(newKit)`, và quy định rõ cách giải phóng những widget cũ, tạo lại cả bộ và chuyển trạng thái cần thiết. Trong ứng dụng thực, quá trình này có thể cần transaction hoặc rollback khi tạo bộ mới thất bại.

### 7.4. Không để factory nhận biến thể riêng từng phương thức

API sau vô tình trao quyền trộn họ cho caller:

```java
Button createButton(Platform buttonPlatform);
Checkbox createCheckbox(Platform checkboxPlatform);
```

Nếu một factory được hiểu là **một họ**, các phương thức tạo sản phẩm không nên nhận lại tham số chọn họ. Thay vào đó, tạo factory/kit từ `Platform` một lần rồi gọi `createButton()` và `createCheckbox()` trên cùng đối tượng đó.

### 7.5. Kiểm soát tính đầy đủ của họ sản phẩm

Khi thêm loại sản phẩm `Dialog`, cần bổ sung hợp đồng `createDialog()` vào abstract factory và triển khai ở **mọi** concrete factory. Đây là điểm đánh đổi của Abstract Factory: thêm một họ mới khá thuận lợi khi các loại sản phẩm ổn định; thêm loại sản phẩm mới khiến mọi factory phải cập nhật.

Không nên âm thầm dùng `WindowsDialog` làm fallback cho `MacFactory` chỉ vì chưa có `MacDialog`. Nếu một họ chưa hỗ trợ một tính năng, hãy biểu đạt khả năng hỗ trợ bằng API rõ ràng hoặc từ chối cấu hình không hợp lệ.

## 8. Phân biệt ràng buộc tại compile time và kiểm tra tại runtime

Hạn chế constructor giúp tránh một số lỗi ngay từ khi biên dịch, nhưng có những ràng buộc không biểu diễn được chỉ bằng hai product interface `Button` và `Checkbox`.

Ví dụ, nếu hệ thống mở cho plugin tự cài đặt `UiFactory`, implementation có thể làm sai:

```java
final class BrokenMacFactory implements UiFactory {
    public Button createButton() {
        return new MacButton();
    }

    public Checkbox createCheckbox() {
        return new WindowsCheckbox(); // Sai họ dù hợp lệ về kiểu.
    }
}
```

Đây là **mã giả định ở phạm vi nội bộ** vì các lớp cụ thể trong ví dụ mục 5 là private. Nó cho thấy điều gì xảy ra nếu một factory có quyền truy cập các triển khai nhưng cài đặt sai. Hệ thống kiểu của Java chỉ biết `WindowsCheckbox implements Checkbox`, không suy ra “nút và checkbox cùng thuộc họ macOS”.

Có ba chiến lược bổ sung, tùy yêu cầu:

1. **Đóng tập factory được phép:** ẩn concrete factory và chỉ cấp `UiKit.forPlatform(...)` cho những họ do thư viện quản lý, như ví dụ trên. Đây là lựa chọn đơn giản khi tập biến thể tương đối ổn định.
2. **Kiểm tra metadata về họ tại runtime:** nếu kiến trúc plugin bắt buộc cho phép factory từ bên ngoài, có thể xác thực family ID, version, context hoặc những capability liên quan tại boundary. Family ID chỉ là một tín hiệu; các sản phẩm nói cùng ID vẫn có thể không tương thích thật sự.
3. **Mã hóa ràng buộc trong kiểu:** với những API phức tạp, có thể dùng generic family marker hoặc sealed hierarchies để biểu đạt thêm quan hệ giữa sản phẩm. Cách này tăng độ phức tạp, cần tránh unchecked cast và vẫn không thay thế được kiểm thử tích hợp.

Không nên mặc định thêm family ID vào mọi `Button` và `Checkbox` nếu client không có nhu cầu quan sát họ. Làm vậy có thể làm lộ chi tiết nền tảng vào hợp đồng chung chỉ để xử lý một lỗi vốn có thể được ngăn ngay từ constructor hoặc composition root.

## 9. Kiểm thử bảo đảm tương thích và kiểm thử API

Lý tưởng là kết hợp hai loại kiểm tra:

- **Kiểm tra API ở compile time:** mã client bên ngoài không truy cập được concrete product, không gọi được constructor `UiKit` và không có cách công khai để truyền widget Windows + macOS vào cùng `SettingsScreen`.
- **Kiểm tra hành vi/tích hợp:** khi chọn Windows, cả hai sản phẩm thuộc Windows; chọn macOS thì cả hai thuộc macOS; các thao tác chung vẫn hoạt động và state giữa các màn hình độc lập khi đó là yêu cầu.

Với mã `Demo` ở mục 5, ví dụ JUnit 5 sau kiểm tra kết quả quan sát được:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UiKitTest {
    @Test
    void windowsKitCreatesMatchingProducts() {
        Demo.UiKit kit = Demo.UiKit.forPlatform(Demo.Platform.WINDOWS);
        Demo.SettingsScreen screen = new Demo.SettingsScreen(kit);

        assertEquals("WindowsButton | WindowsCheckbox", screen.preview());
    }

    @Test
    void macKitCreatesMatchingProducts() {
        Demo.UiKit kit = Demo.UiKit.forPlatform(Demo.Platform.MAC);
        Demo.SettingsScreen screen = new Demo.SettingsScreen(kit);

        assertEquals("MacButton | MacCheckbox", screen.preview());
    }

    @Test
    void sharingKitDoesNotShareScreenState() {
        Demo.UiKit kit = Demo.UiKit.forPlatform(Demo.Platform.MAC);
        Demo.SettingsScreen first = new Demo.SettingsScreen(kit);
        Demo.SettingsScreen second = new Demo.SettingsScreen(kit);

        first.toggleNotifications();
        first.clickSave();

        assertTrue(first.notificationsEnabled());
        assertEquals(1, first.saveCount());
        assertFalse(second.notificationsEnabled());
        assertEquals(0, second.saveCount());
    }

    @Test
    void nullPlatformIsRejected() {
        assertThrows(
            NullPointerException.class,
            () -> Demo.UiKit.forPlatform(null)
        );
    }
}
```

Vì `appearance()` chỉ là nhãn minh họa, các assertion về chuỗi ở đây giúp thấy trực quan hai sản phẩm cùng họ. Trong dự án thực, hãy kiểm tra tính tương thích bằng những observable contract có ý nghĩa: context chung, giao thức tương thích, hành vi sự kiện hoặc kết quả render tích hợp. Không nên gắn test nghiệp vụ lâu dài vào tên class hay format log.

Để kiểm tra **không thể gọi API bị cấm**, có thể xây dựng compilation test hoặc module consumer test chuyên biệt; không trộn đoạn mã cố ý không biên dịch vào cùng bộ unit test thông thường. Việc compile fail phải được xác nhận đúng lý do do giới hạn visibility, không phải do lỗi cú pháp.

## 10. Các sai lầm dễ gặp khi giới hạn API

| Sai lầm | Vì sao chưa giải quyết được vấn đề? | Hướng sửa |
| --- | --- | --- |
| Ẩn constructor sản phẩm nhưng vẫn công khai `SettingsScreen(Button, Checkbox)` | Caller vẫn có thể ghép sản phẩm của hai factory khác nhau. | Chỉ nhận một family handle hoặc bộ sản phẩm đã kiểm tra. |
| Dùng `UiFactory` nhưng cho client tự tạo factory ở mọi nơi | Mỗi màn hình có thể chọn họ riêng ngoài ý muốn. | Đưa quyết định chọn họ về nơi cấu hình, inject từ đó. |
| `UiKit` có `setFactory(...)` công khai | Có thể thay factory giữa hai lần gọi `create...` hoặc đổi họ khi widget cũ vẫn còn. | Giữ factory bất biến; thay bộ sản phẩm bằng thao tác có quy trình. |
| Chỉ dùng `Objects.requireNonNull(...)` | Null check không kiểm tra hai đối tượng có cùng họ hay không. | Hạn chế API ghép rời và kiểm tra tương thích thật sự nếu cần. |
| Factory tạo một widget singleton có trạng thái dùng chung | Nhiều màn hình có thể ảnh hưởng lẫn nhau dù cùng họ. | Định nghĩa vòng đời sản phẩm và tạo mới khi cần trạng thái độc lập. |
| Mọi lớp/constructor đều `private` bất kể nhu cầu | Gây khó cho extension point hoặc plugin đã được yêu cầu. | Chỉ đóng các đường tạo bộ không hợp lệ; giữ API mở đúng vị trí cần mở rộng. |
| Coi việc cùng family ID là đủ | Cùng nhãn không chứng minh tương thích phiên bản, context, hành vi. | Kiểm tra contract và điều kiện tích hợp cụ thể. |

## 11. Nếu cần cho phép mở rộng bởi bên thứ ba thì sao?

Ẩn toàn bộ concrete factory rất phù hợp với thư viện có **tập họ đóng** như Windows và macOS. Nhưng nếu nền tảng hỗ trợ plugin, các nhà phát triển bên ngoài có thể cần thêm `LinuxUiFactory`, `WebUiFactory` hoặc họ sản phẩm riêng. Khi đó ta phải cân bằng hai nhu cầu:

- **Khả năng mở rộng:** cung cấp extension point để plugin khai báo một **factory hoàn chỉnh** cho tất cả loại sản phẩm bắt buộc.
- **Tính nhất quán:** đăng ký factory ở một registry có kiểm tra; client chỉ nhận một family handle trỏ tới đúng factory đã được chấp nhận, không lắp từng sản phẩm.

Có thể giữ `UiFactory` ở một package API dành cho plugin, còn `SettingsScreen` vẫn chỉ nhận `UiKit`. Registry quản lý việc đăng ký, chọn và xác thực factory; việc có cho phép thay plugin lúc chạy hay không phụ thuộc hợp đồng vòng đời. Không nên vì yêu cầu plugin mà mở public mọi constructor của concrete product trong lõi ứng dụng.

Trong hệ thống có hai chiều biến thể phức tạp (ví dụ chủ đề giao diện **và** phiên bản giao thức), một factory có thể chưa đủ để biểu đạt toàn bộ tương thích. Khi đó hãy thiết kế rõ các trục cấu hình hoặc quy tắc kiểm tra compatibility; không kỳ vọng chỉ tên một family là giải quyết mọi quan hệ.

## 12. Checklist review và bài tập thực hành

Khi xem một pull request áp dụng Abstract Factory, hãy đặt các câu hỏi:

1. Client chọn họ sản phẩm ở đâu? Quyết định có tập trung và dễ theo dõi không?
2. Constructor của client nhận một factory/family handle hay nhận nhiều sản phẩm riêng lẻ?
3. Có public constructor, setter hoặc `createProduct(platform)` nào cho phép vượt qua quyết định chọn họ không?
4. Concrete factory có trả về đủ loại sản phẩm, đúng họ, đúng context và đúng vòng đời không?
5. Có nguy cơ hai lời gọi tạo sản phẩm dùng factory đã bị thay đổi giữa chừng không?
6. Tests có kiểm tra cả tính nhất quán của một họ và hành vi mà client cần không?
7. Nếu có plugin, extension point nằm ở cấp **factory hoàn chỉnh** hay yêu cầu client tự lắp sản phẩm?

**Bài tập 1 — tìm lỗi:** Một `ReportScreen` nhận `Formatter` và `Exporter` riêng; caller truyền `CsvFormatter` cùng `PdfExporter`. Nếu cặp này không hỗ trợ cùng định dạng trung gian, màn hình có thể lỗi lúc chạy. Hãy thiết kế `ReportFactory` tạo ra một cặp tương thích và thay constructor để nhận một factory hoặc một `ReportKit`. Chỉ ra cách hạn chế public constructor và setter để tránh trộn lại về sau.

**Bài tập 2 — mở rộng:** Từ ví dụ `Demo.java`, bổ sung `Dialog` vào từng họ. Thêm `Dialog createDialog()` vào `UiFactory`, triển khai `WindowsDialog` và `MacDialog`, rồi cho `SettingsScreen` nhận dialog từ cùng `UiKit`. Viết test chứng minh `UiKit.forPlatform(MAC)` tạo đủ ba loại sản phẩm macOS.

**Bài tập 3 — cân bằng thiết kế:** Giả sử ứng dụng cho phép plugin bên ngoài đăng ký `UiFactory`. Thảo luận lý do không thể giữ toàn bộ factory interface ở mức `private`; đề xuất registry xác thực một factory trước khi cấp handle cho client. Nêu ít nhất hai quy tắc tương thích cần kiểm tra ngoài việc so sánh tên họ.

**Ghi nhớ:** Abstract Factory giúp tập trung cách tạo một họ sản phẩm, còn **thiết kế API và constructor** quyết định client có dễ phá vỡ sự nhất quán đó hay không. Hãy chọn họ một lần, truyền factory hoặc family handle như một đơn vị, ẩn các lối tạo/ghép rời không cần thiết và kiểm thử các ràng buộc mà hệ thống kiểu chưa thể chứng minh. Mục tiêu là làm cho cách sử dụng đúng trở nên tự nhiên và lỗi trộn họ khó xảy ra hơn.
