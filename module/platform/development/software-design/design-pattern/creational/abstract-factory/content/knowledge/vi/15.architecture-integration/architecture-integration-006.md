# Truyền cấu hình và dependency dùng chung mà không biến factory thành Service Locator

**Abstract Factory** là mẫu thiết kế khởi tạo dùng một hợp đồng để tạo **các sản phẩm thuộc cùng một họ**. Ví dụ, một ứng dụng hỗ trợ hai họ giao diện Light và Dark; mỗi họ có Button và Checkbox phù hợp với nhau. Trong hệ thống thật, việc tạo các sản phẩm này thường còn cần **cấu hình** (màu nhấn, chủ đề, ngôn ngữ) và **dependency dùng chung** (đồng hồ, dịch vụ ghi sự kiện, bộ nhớ đệm hoặc kết nối hạ tầng).

Trong chương **Tích hợp kiến trúc**, vấn đề không nằm ở việc có thể truyền một đối tượng vào constructor hay không. Vấn đề là **đường đi của các phụ thuộc có rõ ràng và kiểm soát được không**. Nếu mỗi factory được phép tìm bất kỳ dịch vụ nào qua một container toàn cục, Abstract Factory có thể dần trở thành **Service Locator**: mã che giấu những gì nó cần và khó kiểm thử độc lập.

Bài này hướng dẫn đặt cấu hình và dependency tại **composition root**, truyền tường minh qua constructor của concrete factory, chia sẻ hợp lý cho những sản phẩm cùng họ, đồng thời phân biệt trách nhiệm tạo sản phẩm với trách nhiệm tra cứu dịch vụ.

## 1. Bài toán tích hợp: một họ sản phẩm, nhiều đầu vào

Giả sử SettingsScreen gồm hai **loại sản phẩm**:

- **Button**: hiển thị nút và xử lý hành động nhấn.
- **Checkbox**: hiển thị ô chọn và xử lý thao tác đổi trạng thái.

Ứng dụng hỗ trợ hai **họ sản phẩm**:

| Họ | Button | Checkbox | Quy tắc thể hiện |
| --- | --- | --- | --- |
| Light | LightButton | LightCheckbox | Nền sáng, chữ tối |
| Dark | DarkButton | DarkCheckbox | Nền tối, chữ sáng |

Ngoài kiểu giao diện, cả Button và Checkbox cần dùng chung ba giá trị:

| Đầu vào | Vai trò | Nơi nên quyết định |
| --- | --- | --- |
| **UiConfig** | Chủ đề được chọn và màu nhấn | Đọc/kiểm tra cấu hình tại composition root |
| **Clock** | Cung cấp thời điểm ghi nhận hành động | Tạo hoặc nhận từ hạ tầng ở composition root |
| **EventSink** | Ghi sự kiện tương tác vào nơi được cấu hình | Lắp ghép implementation tại composition root |

**UiConfig là dữ liệu cấu hình**; **Clock và EventSink là dependency dịch vụ**. Việc phân biệt này quan trọng: cấu hình thường được **đọc và xác thực một lần**, trong khi dependency có thể có vòng đời riêng, cần được chia sẻ hoặc đóng đúng nơi.

### Cách tổ chức dễ gặp vấn đề

Một concrete factory tự mở tệp cấu hình, tự tạo clock, tự tìm logger và làm điều đó lặp lại mỗi lần có người yêu cầu Button:

~~~java
// Mã giả minh họa thiết kế không nên làm.
Button createButton() {
    String theme = GlobalSettings.get("ui.theme");
    EventSink sink = ServiceLocator.get(EventSink.class);
    Clock clock = ServiceLocator.get(Clock.class);
    return makeButton(theme, clock, sink);
}
~~~

Điều gì đang bị che giấu? Chữ ký của factory không cho biết cần Clock, EventSink hoặc cấu hình nào. Một unit test không thể cung cấp dependency giả qua API rõ ràng; thay đổi trạng thái toàn cục có thể tác động đến các màn hình khác. Thêm nữa, factory đang nhận trách nhiệm **chọn dịch vụ hạ tầng** ngoài nhiệm vụ **tạo họ sản phẩm**.

Trong phần tiếp theo, mọi đầu vào sẽ được lắp ghép trước, rồi truyền tường minh tới factory.

## 2. Ranh giới trách nhiệm giữa composition root, factory và client

**Composition root** là nơi cấp cao nhất lắp ghép các đối tượng của một phạm vi hoạt động, ví dụ phương thức `main()`, phần cấu hình dependency injection của ứng dụng hoặc điểm khởi tạo một request. Tại đây, ứng dụng có thể biết những lớp cụ thể cần chọn.

~~~mermaid
flowchart TB
    Source["Tham số / file cấu hình"] --> Root["Composition root"]
    Root --> Config["UiConfig đã xác thực"]
    Root --> Clock["Clock"]
    Root --> Sink["EventSink"]
    Root --> Select["Chọn LightGuiFactory hoặc DarkGuiFactory"]
    Config --> Select
    Clock --> Select
    Sink --> Select
    Select --> Contract["GuiFactory"]
    Contract --> Screen["SettingsScreen"]
    Select --> Button["Button cùng họ"]
    Select --> Checkbox["Checkbox cùng họ"]
    Button --> Screen
    Checkbox --> Screen
~~~

Sơ đồ thể hiện **luồng cấp phát và truyền phụ thuộc**, không hàm ý mọi đối tượng có thể tự lấy các dependency bất kỳ từ composition root.

Mỗi thành phần có trách nhiệm cụ thể:

1. **Composition root:** đọc, xác thực cấu hình; chọn họ; tạo/nhận các dependency hạ tầng; quyết định phạm vi chia sẻ và chủ sở hữu vòng đời.
2. **Abstract factory (`GuiFactory`):** công bố những thao tác tạo sản phẩm theo **loại**, ví dụ `createButton()` và `createCheckbox()`.
3. **Concrete factory:** nhận những thứ nó thực sự cần qua constructor; dùng chúng để tạo các biến thể thuộc **một họ**.
4. **Concrete product:** nhận cấu hình đã chuyển thành dữ liệu cần thiết và các dịch vụ nó sử dụng; không tự đi tìm các dịch vụ trong container.
5. **Client (`SettingsScreen`):** chỉ phụ thuộc vào GuiFactory, Button và Checkbox; không cần biết chủ đề cụ thể hay nơi tạo EventSink.

Với cách này, thay `LightGuiFactory` bằng `DarkGuiFactory` chỉ ảnh hưởng đến bước lắp ghép. Những phụ thuộc phục vụ nhiều sản phẩm vẫn được cấp phát có chủ đích, và mã client không chứa logic tìm dịch vụ.

## 3. Truyền cấu hình dưới dạng giá trị rõ nghĩa

Một factory cần hiểu các **giá trị liên quan đến việc tạo sản phẩm**, không nhất thiết cần đọc trực tiếp `System.getProperty`, YAML, JSON hay biến môi trường.

Ví dụ cấu hình UI gồm **theme** và **accentColor**:

~~~java
enum Theme {
    LIGHT, DARK
}

final class UiConfig {
    final Theme theme;
    final String accentColor;

    UiConfig(Theme theme, String accentColor) {
        this.theme = java.util.Objects.requireNonNull(theme, "theme");
        String accent = java.util.Objects.requireNonNull(
                accentColor, "accentColor").trim();
        if (accent.isEmpty()) {
            throw new IllegalArgumentException("accentColor rỗng");
        }
        this.accentColor = accent;
    }
}
~~~

Đây là **đối tượng giá trị bất biến**: không có setter; dữ liệu đầu vào được kiểm tra ngay khi khởi tạo. Với dự án thật, có thể dùng record nếu phiên bản Java cho phép, hoặc thư viện binding cấu hình. Quy tắc cốt lõi vẫn là **chuyển dữ liệu ngoài hệ thống thành một hợp đồng cấu hình có kiểu và đã được xác thực**.

Một factory Light có thể chuyển `UiConfig` thành `Palette` với màu nền và màu chữ phù hợp, rồi chia sẻ **cùng một Palette bất biến** cho Button và Checkbox. Chỉ những thông số mà sản phẩm thực sự cần mới đi tới sản phẩm.

### Vì sao không truyền nguyên một object chứa mọi cấu hình?

Nếu truyền `Map<String, Object>` khổng lồ hoặc nguyên đối tượng cấu hình toàn ứng dụng cho từng sản phẩm, chúng có thể vô tình phụ thuộc vào các khóa không liên quan. Khi đó một thay đổi ở module khác cũng có thể ảnh hưởng giao diện UI.

Hãy ưu tiên:

- **Cấu hình theo miền chức năng** như `UiConfig` hoặc `Palette`, có các field cụ thể.
- **Giá trị bất biến** để các sản phẩm trong một họ không quan sát những thay đổi cấu hình bất ngờ trong quá trình chạy.
- **Xác thực sớm** những giá trị bắt buộc và tổ hợp không được hỗ trợ.

Nếu cần đổi chủ đề khi ứng dụng đang chạy, hãy xác định rõ quy trình **tạo lại factory/sản phẩm** hoặc cập nhật trạng thái. Thay một biến cấu hình không tự biến các Button đã được tạo từ Light thành Dark.

## 4. Truyền dependency dùng chung bằng constructor injection

Đối với dịch vụ như `Clock` hoặc `EventSink`, concrete factory nên khai báo sự phụ thuộc **một lần** trong constructor:

~~~java
// Mã khái niệm: các kiểu Palette, Clock, EventSink được khai báo ở nơi khác.
final class LightGuiFactory implements GuiFactory {
    private final Palette palette;
    private final Clock clock;
    private final EventSink events;

    LightGuiFactory(UiConfig config, Clock clock, EventSink events) {
        if (config.theme != Theme.LIGHT) {
            throw new IllegalArgumentException("Factory không đúng theme");
        }
        this.palette = Palette.forLight(config.accentColor);
        this.clock = java.util.Objects.requireNonNull(clock);
        this.events = java.util.Objects.requireNonNull(events);
    }

    public Button createButton() {
        return new LightButton(palette, clock, events);
    }

    public Checkbox createCheckbox() {
        return new LightCheckbox(palette, clock, events);
    }
}
~~~

Đoạn trên mô tả cấu trúc; một phiên bản Java có thể biên dịch và chạy độc lập nằm ở mục 5.

**Điểm đáng chú ý:** factory **không tự tạo một EventSink mới mỗi lần gọi createButton()**. Nó dùng lại đối tượng đã được cấp phát và được chia sẻ theo phạm vi mà composition root quyết định.

Điều này giúp:

- **Nhất quán:** các sản phẩm cùng một factory dùng cùng bộ cấu hình và cùng nguồn sự kiện.
- **Kiểm thử:** thay `EventSink` hoặc `Clock` bằng phiên bản giả dễ dàng tại constructor.
- **Quản lý vòng đời:** nơi tạo dịch vụ có thể kiểm soát khi nào mở và đóng tài nguyên.
- **Đọc code:** một người nhìn constructor biết ngay factory phụ thuộc vào những gì.

**Không bắt buộc mọi dependency phải là singleton.** Một Clock dùng chung thường phù hợp với nhiều sản phẩm, nhưng một kết nối giao dịch hoặc đối tượng chứa trạng thái theo request có thể cần phạm vi ngắn hơn. Quy tắc là **chia sẻ đúng theo vòng đời và khả năng an toàn khi dùng đồng thời**, không mặc định chia sẻ toàn tiến trình.

## 5. Ví dụ Java hoàn chỉnh: config + Clock + EventSink

Ví dụ bên dưới chạy trong **một tệp Main.java**, không dùng thư viện ngoài và tương thích Java 8 trở lên. Để dễ đối chiếu đầu ra, `Clock.fixed` sử dụng một thời điểm cố định; trong hệ thống thật, composition root có thể cung cấp `Clock.systemUTC()`.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Locale;
import java.util.Objects;

public class Main {
    enum Theme {
        LIGHT, DARK
    }

    // Cấu hình theo miền UI, bất biến sau khi tạo.
    static final class UiConfig {
        final Theme theme;
        final String accentColor;

        UiConfig(Theme theme, String accentColor) {
            this.theme = Objects.requireNonNull(theme, "theme");
            String accent = Objects.requireNonNull(
                    accentColor, "accentColor").trim();
            if (accent.isEmpty()) {
                throw new IllegalArgumentException("Màu nhấn không được rỗng");
            }
            this.accentColor = accent;
        }
    }

    static final class Palette {
        final String background;
        final String foreground;
        final String accent;

        Palette(String background, String foreground, String accent) {
            this.background = Objects.requireNonNull(background);
            this.foreground = Objects.requireNonNull(foreground);
            this.accent = Objects.requireNonNull(accent);
        }
    }

    // Dịch vụ hạ tầng có thể thay thế trong kiểm thử.
    interface EventSink {
        void record(String action, Instant at);
    }

    static final class ConsoleEventSink implements EventSink {
        @Override
        public void record(String action, Instant at) {
            System.out.println("AUDIT " + at + " " + action);
        }
    }

    // Abstract Products: client không cần biết Light hay Dark.
    interface Button {
        String render();
        void press();
    }

    interface Checkbox {
        String render();
        void toggle();
    }

    // Abstract Factory chỉ công bố các loại sản phẩm cần tạo.
    interface GuiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Họ Light: mỗi sản phẩm nhận dependencies tường minh.
    static final class LightButton implements Button {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        LightButton(Palette palette, Clock clock, EventSink events) {
            this.palette = Objects.requireNonNull(palette);
            this.clock = Objects.requireNonNull(clock);
            this.events = Objects.requireNonNull(events);
        }

        @Override
        public String render() {
            return "[Light] Button bg=" + palette.background
                    + " fg=" + palette.foreground
                    + " accent=" + palette.accent;
        }

        @Override
        public void press() {
            events.record("light.button.press", clock.instant());
        }
    }

    static final class LightCheckbox implements Checkbox {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        LightCheckbox(Palette palette, Clock clock, EventSink events) {
            this.palette = Objects.requireNonNull(palette);
            this.clock = Objects.requireNonNull(clock);
            this.events = Objects.requireNonNull(events);
        }

        @Override
        public String render() {
            return "[Light] Checkbox bg=" + palette.background
                    + " fg=" + palette.foreground
                    + " accent=" + palette.accent;
        }

        @Override
        public void toggle() {
            events.record("light.checkbox.toggle", clock.instant());
        }
    }

    // Họ Dark: khác biến thể nhưng cùng interface sản phẩm.
    static final class DarkButton implements Button {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        DarkButton(Palette palette, Clock clock, EventSink events) {
            this.palette = Objects.requireNonNull(palette);
            this.clock = Objects.requireNonNull(clock);
            this.events = Objects.requireNonNull(events);
        }

        @Override
        public String render() {
            return "[Dark] Button bg=" + palette.background
                    + " fg=" + palette.foreground
                    + " accent=" + palette.accent;
        }

        @Override
        public void press() {
            events.record("dark.button.press", clock.instant());
        }
    }

    static final class DarkCheckbox implements Checkbox {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        DarkCheckbox(Palette palette, Clock clock, EventSink events) {
            this.palette = Objects.requireNonNull(palette);
            this.clock = Objects.requireNonNull(clock);
            this.events = Objects.requireNonNull(events);
        }

        @Override
        public String render() {
            return "[Dark] Checkbox bg=" + palette.background
                    + " fg=" + palette.foreground
                    + " accent=" + palette.accent;
        }

        @Override
        public void toggle() {
            events.record("dark.checkbox.toggle", clock.instant());
        }
    }

    // Concrete factories: giữ một tập input đã được lắp ghép.
    static final class LightGuiFactory implements GuiFactory {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        LightGuiFactory(UiConfig config, Clock clock, EventSink events) {
            Objects.requireNonNull(config, "config");
            if (config.theme != Theme.LIGHT) {
                throw new IllegalArgumentException("Cần cấu hình LIGHT");
            }
            this.palette = new Palette("white", "black", config.accentColor);
            this.clock = Objects.requireNonNull(clock, "clock");
            this.events = Objects.requireNonNull(events, "events");
        }

        @Override
        public Button createButton() {
            return new LightButton(palette, clock, events);
        }

        @Override
        public Checkbox createCheckbox() {
            return new LightCheckbox(palette, clock, events);
        }
    }

    static final class DarkGuiFactory implements GuiFactory {
        private final Palette palette;
        private final Clock clock;
        private final EventSink events;

        DarkGuiFactory(UiConfig config, Clock clock, EventSink events) {
            Objects.requireNonNull(config, "config");
            if (config.theme != Theme.DARK) {
                throw new IllegalArgumentException("Cần cấu hình DARK");
            }
            this.palette = new Palette("black", "white", config.accentColor);
            this.clock = Objects.requireNonNull(clock, "clock");
            this.events = Objects.requireNonNull(events, "events");
        }

        @Override
        public Button createButton() {
            return new DarkButton(palette, clock, events);
        }

        @Override
        public Checkbox createCheckbox() {
            return new DarkCheckbox(palette, clock, events);
        }
    }

    // Client chỉ yêu cầu bộ sản phẩm qua abstract factory.
    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;

        SettingsScreen(GuiFactory factory) {
            Objects.requireNonNull(factory, "factory");
            button = Objects.requireNonNull(
                    factory.createButton(), "button");
            checkbox = Objects.requireNonNull(
                    factory.createCheckbox(), "checkbox");
        }

        String render() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }

        void simulateInteraction() {
            button.press();
            checkbox.toggle();
        }
    }

    private static Theme parseTheme(String text) {
        String value = Objects.requireNonNull(text, "theme")
                .trim().toLowerCase(Locale.ROOT);
        if ("light".equals(value)) {
            return Theme.LIGHT;
        }
        if ("dark".equals(value)) {
            return Theme.DARK;
        }
        throw new IllegalArgumentException("Chủ đề không hỗ trợ: " + text);
    }

    // Composition root: chỉ ở đây chọn implementation và vòng đời.
    public static void main(String[] args) {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Cách dùng: java Main [light|dark] [accentColor]");
        }

        Theme theme = args.length == 0
                ? Theme.LIGHT : parseTheme(args[0]);
        String accent = args.length < 2 ? "blue" : args[1];
        UiConfig config = new UiConfig(theme, accent);

        // Cố định thời gian để ví dụ có output xác định.
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
        EventSink events = new ConsoleEventSink();

        GuiFactory factory = config.theme == Theme.LIGHT
                ? new LightGuiFactory(config, clock, events)
                : new DarkGuiFactory(config, clock, events);

        SettingsScreen screen = new SettingsScreen(factory);
        System.out.println(screen.render());
        screen.simulateInteraction();
    }
}
~~~

### Biên dịch và chạy

Lưu đoạn mã ở trên vào `Main.java`, dùng JDK 8 trở lên:

~~~text
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả:

~~~text
[Light] Button bg=white fg=black accent=blue
[Light] Checkbox bg=white fg=black accent=blue
AUDIT 2026-01-01T00:00:00Z light.button.press
AUDIT 2026-01-01T00:00:00Z light.checkbox.toggle
~~~

Chuyển chủ đề và màu nhấn chỉ bằng tham số:

~~~text
java Main dark cyan
~~~

Kết quả:

~~~text
[Dark] Button bg=black fg=white accent=cyan
[Dark] Checkbox bg=black fg=white accent=cyan
AUDIT 2026-01-01T00:00:00Z dark.button.press
AUDIT 2026-01-01T00:00:00Z dark.checkbox.toggle
~~~

**Điều cần quan sát:** `SettingsScreen` không đọc tham số khởi chạy, không biết `ConsoleEventSink` và không có nhánh `if` kiểm tra Light/Dark. Hai sản phẩm nhận **cùng instance Palette, Clock và EventSink** do factory chuyển vào; các implementation của họ khác nhau chỉ thay đổi **cách tạo sản phẩm và quy tắc giao diện**.

`Clock.fixed` chỉ nhằm tạo đầu ra xác định trong tài liệu. Trong môi trường thật, composition root có thể dùng `Clock.systemUTC()`, một Clock theo request hoặc dịch vụ thời gian được cung cấp từ bên ngoài, tùy yêu cầu kiểm thử và vận hành.

## 6. Factory khác Service Locator ở đâu?

Hai cơ chế này có thể cùng tạo hoặc trả về đối tượng, nhưng **hợp đồng phụ thuộc** khác nhau:

| Tiêu chí | Abstract Factory được lắp ghép tường minh | Service Locator |
| --- | --- | --- |
| **Mục đích** | Tạo một **bộ sản phẩm liên quan** thuộc họ được chọn | Tra cứu dịch vụ bất kỳ theo khóa/kiểu |
| **API** | `createButton()`, `createCheckbox()` theo loại sản phẩm | `get(Class<T>)`, `resolve("name")`, ... |
| **Phụ thuộc của factory** | Thể hiện rõ ở constructor hoặc API cấu hình có kiểu | Có thể bị che sau lời gọi tới container |
| **Những gì client biết** | Hợp đồng sản phẩm và factory được tiêm vào | Client có thể phải biết locator và khóa dịch vụ |
| **Khả năng kiểm thử** | Truyền trực tiếp fake Clock/EventSink/factory | Thường phải cấu hình hoặc thay đổi locator toàn cục |
| **Phạm vi trách nhiệm** | Tạo nhóm đối tượng theo một quy tắc nhất quán | Quản lý/tìm nhiều dịch vụ, dễ mở rộng không giới hạn |

Đây là mô tả **dạng Service Locator phổ biến** khi dùng như phụ thuộc ẩn hoặc toàn cục. Một **registry ở composition root** để chọn factory không tự động là sai thiết kế. Vấn đề xuất hiện khi mã nghiệp vụ hoặc concrete factory **được quyền lấy tùy ý các dependency** từ registry/container ở mọi nơi.

### Ví dụ phản mẫu: factory đóng vai Service Locator

~~~java
// Mã giả: không phải chương trình Java độc lập.
final class ProblematicGuiFactory implements GuiFactory {
    public Button createButton() {
        Clock clock = GlobalServices.get(Clock.class);
        EventSink events = GlobalServices.get(EventSink.class);
        UiConfig config = GlobalServices.get(UiConfig.class);
        return new LightButton(
                Palette.forLight(config.accentColor), clock, events);
    }

    public Checkbox createCheckbox() {
        return GlobalServices.get(Checkbox.class);
    }
}
~~~

Ở đây, `ProblematicGuiFactory` vừa che giấu Clock/EventSink/UiConfig, vừa yêu cầu container trả về một Checkbox bất kỳ, **không chứng minh nó thuộc họ Light**. Việc test factory phụ thuộc vào trạng thái đăng ký dịch vụ của toàn ứng dụng; khi thiếu service, lỗi chỉ xuất hiện lúc gọi `createButton()`.

Đối với bản thiết kế tốt hơn, các đầu vào cần thiết xuất hiện ngay trong constructor:

~~~java
// Đoạn minh họa chữ ký; cách cài đặt nằm trong ví dụ hoàn chỉnh.
LightGuiFactory(UiConfig config, Clock clock, EventSink events);
~~~

Đây là **chữ ký constructor** để so sánh, không phải câu lệnh Java đứng riêng. Nó giúp code review và các công cụ DI xác định phụ thuộc trước khi factory bắt đầu tạo sản phẩm.

### Có thể dùng DI container cùng Abstract Factory không?

**Có.** Một DI container có thể tạo Clock, EventSink, UiConfig rồi dựng một concrete factory và tiêm nó vào SettingsScreen. Nếu phải chọn họ dựa trên cấu hình, composition root có thể khai báo một phương thức/cấu hình **provider có kiểu** để xây dựng factory phù hợp.

Sử dụng container tại **composition root** để lắp ghép là một lựa chọn tổ chức bình thường. Trong các lớp nghiệp vụ và concrete products, tiếp tục nhận **những phụ thuộc cụ thể mà lớp thực sự cần**, thay vì mang cả `ApplicationContext`, `Injector` hoặc một `ServiceProvider` tổng quát vào rồi tùy ý truy vấn.

Nếu một dependency cần được tạo **theo yêu cầu** (lazy) hoặc nhiều lần, có thể tiêm một factory nhỏ hoặc `Supplier<T>` đúng kiểu đó. Việc tiêm `Supplier<Connection>` chỉ dành cho kết nối cần tạo **khác với** tiêm một locator tổng quát có khả năng trả bất kỳ dịch vụ nào.

## 7. Chọn phạm vi và vòng đời cho dependency dùng chung

Đối tượng được “dùng chung” không có nghĩa là **được chia sẻ toàn bộ tiến trình mãi mãi**. Cần gắn quyết định chia sẻ với vòng đời thật của tài nguyên và sản phẩm:

| Dependency hoặc giá trị | Phạm vi thường hợp lý | Điều cần kiểm soát |
| --- | --- | --- |
| **UiConfig/Palette bất biến** | Một factory hoặc một phiên cấu hình | Khi đổi cấu hình, tạo lại hoặc có quy trình cập nhật chủ động |
| **Clock không có trạng thái thay đổi** | Dùng chung cho nhiều factory/sản phẩm | Không nhầm Clock giả trong test với nguồn thời gian sản xuất |
| **EventSink/Logger** | Theo ứng dụng hoặc theo miền chức năng | An toàn khi nhiều lời gọi đồng thời; vòng đời và flush |
| **Connection/Transaction** | Theo request hoặc theo đơn vị công việc | Không chia sẻ connection có trạng thái tùy tiện giữa thread và request |
| **HTTP client hoặc pool** | Theo ứng dụng nếu implementation hỗ trợ | Cấu hình, resource ownership và việc đóng đúng thời điểm |
| **UserSession** | Theo phiên người dùng hoặc request | Không lưu trong singleton factory rồi làm rò trạng thái người dùng |

Nếu factory giữ một dependency được tạo bởi composition root, thông thường **factory không tự ý đóng dependency đó**; nơi sở hữu vòng đời quyết định thời điểm đóng. Ngược lại, nếu factory thực sự tạo một resource mà nó sở hữu, hợp đồng phải quy định việc giải phóng (ví dụ `AutoCloseable`) và client cần xử lý đúng.

### Lỗi scope mismatch

Một singleton factory vô tình nhận `RequestContext` (chứa user hiện tại) ở constructor, rồi dùng lâu dài cho mọi request. Khi ấy factory có thể giữ dữ liệu của request cũ hoặc gây lẫn thông tin giữa người dùng.

Cách xử lý là **đặt factory ở scope phù hợp** hoặc **truyền request context vào một thao tác có kiểu** nếu nghiệp vụ yêu cầu:

~~~java
// Minh họa một API tạo sản phẩm phụ thuộc request.
interface RequestButtonFactory {
    Button createButton(RequestContext context);
}
~~~

Đoạn này chỉ nêu **chữ ký ví dụ**, chưa phải một chương trình hoàn chỉnh. `RequestContext` là kiểu miền cần định nghĩa trong ứng dụng. Đừng truyền nguyên một container hoặc một map chứa mọi dữ liệu request vào factory chỉ để né việc mô tả phụ thuộc.

## 8. Kiểm thử và kiểm chứng ranh giới tích hợp

Thiết kế tốt cho phép kiểm tra hai vấn đề độc lập:

1. **Factory tạo đúng họ:** LightGuiFactory tạo cả LightButton và LightCheckbox với cùng các quy tắc màu; DarkGuiFactory tạo các biến thể Dark.
2. **Dependency được truyền đúng:** cả Button lẫn Checkbox ghi sự kiện qua EventSink được tiêm vào và dùng Clock được cung cấp.

Trong kiểm thử, có thể dùng một `Clock.fixed` và một fake EventSink ghi các sự kiện vào danh sách thay vì console:

~~~java
// Đặt bên trong lớp Main của ví dụ, hoặc chuyển các interface ra API chung.
static final class RecordingEventSink implements EventSink {
    final java.util.List<String> events = new java.util.ArrayList<>();

    @Override
    public void record(String action, java.time.Instant at) {
        events.add(at + " " + action);
    }
}
~~~

Khi tạo `LightGuiFactory(config, fixedClock, recordingSink)`, thực hiện `press()` và `toggle()`, danh sách phải chứa đúng hai sự kiện Light với cùng mốc thời gian dự kiến. Không cần sửa trạng thái toàn cục hay khởi động một DI container đầy đủ để kiểm tra hành vi này.

Với ứng dụng đa luồng, fake ở trên **chỉ dùng cho kiểm thử tuần tự**; `ArrayList` không an toàn nếu nhiều thread ghi đồng thời. Cần chọn fake và EventSink thật phù hợp với mô hình song song.

### Những câu hỏi hữu ích khi review

| Câu hỏi | Dấu hiệu tốt | Dấu hiệu cần sửa |
| --- | --- | --- |
| Factory lấy Clock/Logger từ đâu? | Constructor nêu rõ phụ thuộc | Gọi `GlobalServices.get(...)` trong phương thức tạo |
| Ai đọc file cấu hình? | Composition root hoặc module cấu hình | Từng Button/Checkbox tự đọc |
| Ai chọn Light hay Dark? | Một vị trí lắp ghép có quy tắc rõ | Mỗi client tự quyết định và trộn họ |
| Nhiều sản phẩm có dùng cùng cấu hình không? | Factory truyền cùng Palette đã xác thực | Mỗi sản phẩm tự tính/đọc màu và có thể lệch nhau |
| Factory có nắm vòng đời quá rộng không? | Phạm vi phù hợp với dependencies được giữ | Singleton giữ user/request context |
| Có thể thử bằng dependency giả không? | Inject Clock/EventSink/factory trực tiếp | Test phải sửa registry hoặc biến toàn cục |
| Client có biết container không? | Client nhận GuiFactory hoặc products cần dùng | Client gọi `container.resolve(...)` nhiều nơi |

## 9. Một số biến thể thiết kế nên cân nhắc

### 9.1. Dùng một nhóm phụ thuộc có kiểu khi constructor quá dài

Khi nhiều dependency **thật sự luôn đi cùng nhau** trong cùng phạm vi, có thể nhóm thành một đối tượng có các field rõ nghĩa, ví dụ `UiRuntimeDependencies` với `Clock` và `EventSink`. Đây không tự động là Service Locator nếu nhóm được **khai báo tường minh, có kiểu cố định**, không có API `get(Class<T>)`, và chỉ chứa những thành phần liên quan.

Tuy vậy, nếu đối tượng nhóm dần chứa hàng chục dịch vụ không liên quan và mọi lớp nhận toàn bộ gói, nó trở thành một **dependency bag** che khuất trách nhiệm. Hãy ưu tiên constructor riêng cho số ít phụ thuộc thật sự cần thiết.

### 9.2. Factory tạo nhiều sản phẩm có cùng thông tin

Trong ví dụ, Palette chỉ được tạo **một lần trong concrete factory**, sau đó truyền cho cả Button và Checkbox. Với thông tin cấu hình bất biến, cách này giúp các thành viên trong họ chia sẻ **cùng một snapshot**.

Nếu một sản phẩm đòi hỏi thiết lập riêng, factory có thể xây dựng một đối tượng giá trị phù hợp cho loại sản phẩm đó. Điều quan trọng là **quy tắc phối hợp được giữ tại một chỗ**, không phải mọi sản phẩm phải nhận đúng cùng một tập tham số.

### 9.3. Nhiều cấu hình cùng tồn tại

Một ứng dụng có thể mở hai cửa sổ, một Light và một Dark. Khi đó composition root có thể tạo **hai concrete factory khác nhau** với UiConfig riêng, nhưng vẫn dùng chung Clock hoặc EventSink nếu việc chia sẻ hợp lệ.

Điều này dễ thực hiện khi không có singleton toàn cục buộc mỗi tiến trình chỉ được có một theme. **Một factory đại diện cho một họ trong một phạm vi sử dụng**, không nhất thiết một factory duy nhất cho mọi màn hình.

### 9.4. Chọn factory từ registry mà vẫn tránh Service Locator

Khi thêm nhiều họ, composition root có thể dùng registry ánh xạ **theme ID → nhà cung cấp GuiFactory**. Registry chỉ phục vụ **chọn và xây dựng factory**; SettingsScreen vẫn nhận một GuiFactory cụ thể.

Không nên để SettingsScreen nhận registry tổng quát rồi tự gọi `registry.get(EventSink.class)`, `registry.get(Clock.class)`... Việc đó thay đổi hợp đồng client từ “tôi cần một factory tạo họ UI” thành “tôi có thể tự tìm mọi dịch vụ”, khiến kiến trúc khó kiểm soát.

## 10. Sai lầm thường gặp

**Sai lầm 1 — Factory tự đọc cấu hình mỗi lần tạo sản phẩm.** Khi giá trị thay đổi giữa hai lần gọi, Button và Checkbox có thể mang hai snapshot khác nhau. Đọc/xác thực cấu hình ở composition root và cung cấp một snapshot bất biến phù hợp.

**Sai lầm 2 — Factory nhận cả container DI rồi resolve tùy ý.** Constructor nhìn đơn giản nhưng ẩn nhiều phụ thuộc; khó kiểm thử và dễ phát sinh hành vi khác nhau giữa môi trường. Nên inject trực tiếp Clock, EventSink hoặc một factory/supplier có kiểu hẹp.

**Sai lầm 3 — Tạo resource đắt đỏ ở mọi createButton().** Nếu mọi nút bấm mở một kết nối mạng hoặc một thread pool riêng, chi phí và quản lý tài nguyên tăng không cần thiết. Dùng resource manager/pool được cấp và quản lý theo scope phù hợp.

**Sai lầm 4 — Biến mọi dependency thành singleton.** Đối tượng chứa trạng thái người dùng/giao dịch không nên chia sẻ toàn ứng dụng. Chọn scope dựa trên vòng đời, khả năng đồng thời và chủ sở hữu của tài nguyên.

**Sai lầm 5 — Trả về sản phẩm từ bất kỳ provider nào.** Nếu factory Light lấy một Checkbox bất kỳ từ locator, nó có thể nhận biến thể Dark. Concrete factory phải chịu trách nhiệm tạo **bộ sản phẩm nhất quán**, đồng thời kiểm tra thêm những ràng buộc cần thiết.

**Sai lầm 6 — Đưa lựa chọn theme vào client.** Mỗi SettingsScreen tự kiểm tra theme rồi tự tạo LightButton/DarkCheckbox làm mất lợi ích thay thế họ. Cho client nhận GuiFactory được chọn và truyền từ bên ngoài.

**Sai lầm 7 — Nghĩ rằng có DI container thì tự động đúng Abstract Factory.** DI giải quyết việc **cung cấp dependency**, còn Abstract Factory diễn đạt quy tắc **tạo các sản phẩm liên quan**. Dùng DI để lắp ghép factory, nhưng vẫn cần định nghĩa interface sản phẩm và bất biến của từng họ.

## 11. Bài tập thực hành

**Bài A — Thay dependency thật bằng fake:** từ `Main.java` ở mục 5, viết `RecordingEventSink` và dùng `Clock.fixed` với một mốc thời gian khác. Kiểm tra hai sản phẩm Light đều ghi sự kiện vào cùng sink và có thời điểm đúng mà không thay mã của Button/Checkbox.

**Bài B — Tách cách chọn theme:** chuyển logic lựa chọn Light/Dark thành một hàm ở composition root nhận UiConfig, Clock và EventSink. Đảm bảo SettingsScreen vẫn không nhận hoặc truy vấn một registry dịch vụ tổng quát.

**Bài C — Thêm họ HighContrast:** viết HighContrastButton, HighContrastCheckbox và HighContrastGuiFactory, truyền cùng các dependency rõ nghĩa qua constructor. Tạo sản phẩm có màu tương phản cao và giữ nguyên hai interface sản phẩm cùng SettingsScreen.

**Bài D — Review một Service Locator:** tìm trong một ví dụ tự tạo các lời gọi dạng `GlobalServices.get(...)`. Với mỗi lời gọi, xác định dependency thực sự cần thiết và sửa constructor hoặc chữ ký factory để biểu diễn nó. Giải thích cách thay thế bằng fake trong unit test.

**Bài E — Xử lý scope mismatch:** giả sử EventSink giữ user ID của request hiện tại. Phân tích vì sao singleton LightGuiFactory không nên giữ một EventSink có trạng thái của request đầu tiên; thiết kế factory theo request hoặc truyền context có kiểu để tránh chia sẻ nhầm.

## 12. Ghi nhớ

- **Composition root** đọc cấu hình, chọn họ và quyết định vòng đời dependency. Concrete factory tập trung vào **tạo các sản phẩm liên quan**.
- **Cấu hình có kiểu, bất biến** giúp các sản phẩm dùng cùng một snapshot đã xác thực. **Constructor injection** giúp phụ thuộc của factory hiển thị rõ ràng.
- **Dependency dùng chung** phải được chia sẻ đúng scope. Không tự động biến tất cả resource thành singleton hoặc để mỗi sản phẩm tự tạo tài nguyên đắt đỏ.
- **Service Locator** thường có API tra cứu dịch vụ tổng quát và tạo ra phụ thuộc ẩn; một **registry dùng ở composition root** hoặc DI container lắp ghép đối tượng không tự động là sai.
- **Abstract Factory và DI bổ trợ nhau**: DI cung cấp những phụ thuộc cần thiết, còn Abstract Factory bảo đảm các thành viên được tạo theo quy tắc của một họ sản phẩm.

Khi tích hợp Abstract Factory vào hệ thống lớn, hãy nhìn vào **đường đi của từng dependency**. Nếu có thể chỉ ra nó được tạo ở đâu, đi vào factory qua API nào, được chia sẻ trong phạm vi nào và được đóng bởi ai, kiến trúc sẽ dễ kiểm thử và ít có nguy cơ biến factory thành một Service Locator khó kiểm soát.
