# Thay phụ thuộc lớp cụ thể bằng constructor injection trong client

## 1. Vấn đề cần tái cấu trúc

Trong mẫu thiết kế **Abstract Factory**, client nên yêu cầu các sản phẩm cùng họ thông qua một **abstract factory** và chỉ làm việc với **product interface**. Tuy nhiên, một ứng dụng thường khởi đầu bằng cách tạo trực tiếp các đối tượng cụ thể:

~~~java
class SettingsPanel {
    private final LightButton saveButton = new LightButton();
    private final LightCheckbox notifications = new LightCheckbox();
}
~~~

Cách viết trên đủ dùng nếu ứng dụng chỉ có giao diện Light. Khi cần hỗ trợ Dark, client bắt đầu xuất hiện các nhánh `if` hoặc `switch` để chọn `LightButton`, `DarkButton`, `LightCheckbox` và `DarkCheckbox`. Càng nhiều loại sản phẩm và biến thể, số nơi phải chỉnh sửa càng lớn.

**Mục tiêu tái cấu trúc:** Đưa quyết định chọn họ sản phẩm ra **điểm lắp ráp ứng dụng** (*composition root*), sau đó **truyền một factory qua constructor của client**. Client sử dụng `UiFactory`, `Button` và `Checkbox` thay vì tự gọi `new` các lớp sản phẩm cụ thể.

Bài học thuộc chương **Tái cấu trúc** của module Abstract Factory và tập trung vào kỹ thuật *constructor injection*:

- Nhận biết khi nào client đang phụ thuộc concrete class.
- Tạo abstraction nhỏ cho factory và các sản phẩm.
- Di chuyển việc chọn concrete factory đến composition root.
- Chuyển client sang nhận factory bắt buộc qua constructor.
- Giữ hành vi cũ trong lúc thay đổi cấu trúc và thêm được một họ sản phẩm mới.
- Kiểm thử kết quả, ranh giới phụ thuộc và các tình huống lỗi.

Constructor injection là một cách thực hiện **dependency injection (DI)**: đối tượng phụ thuộc được bên ngoài truyền vào lúc khởi tạo client, thay vì client tự chọn và tự tạo dependency ấy. Kỹ thuật này có thể thực hiện hoàn toàn bằng Java thông thường, không cần DI framework.

## 2. Xác định phụ thuộc trước khi sửa

Giả sử màn hình cài đặt `SettingsPanel` hiển thị Button và Checkbox. Ứng dụng có hai họ giao diện:

| Loại sản phẩm | Họ Light | Họ Dark | Abstraction client nên dùng |
| --- | --- | --- | --- |
| Nút lưu | `LightButton` | `DarkButton` | `Button` |
| Ô bật thông báo | `LightCheckbox` | `DarkCheckbox` | `Checkbox` |
| Đối tượng tạo sản phẩm | `LightUiFactory` | `DarkUiFactory` | `UiFactory` |

Đoạn mã sau phản ánh một cách mở rộng thiếu thuận lợi:

~~~java
class SettingsPanel {
    String render(String theme) {
        if ("dark".equals(theme)) {
            DarkButton button = new DarkButton();
            DarkCheckbox checkbox = new DarkCheckbox();
            return button.render() + " | " + checkbox.render();
        }

        LightButton button = new LightButton();
        LightCheckbox checkbox = new LightCheckbox();
        return button.render() + " | " + checkbox.render();
    }
}
~~~

Ở đây, `SettingsPanel` biết cả bốn lớp sản phẩm và tự quyết định họ dựa trên chuỗi cấu hình. Thêm họ High Contrast sẽ buộc sửa logic màn hình. Khi bổ sung một loại sản phẩm khác như `Slider`, số nhánh tạo đối tượng cũng phải cập nhật theo.

Trong phần còn lại, chúng ta tái cấu trúc **một phiên bản đang chạy với Light** rồi mở rộng sang Dark. Cách làm đó giúp phân biệt hai nhiệm vụ: **giữ nguyên hành vi** sau refactor và **mở rộng khả năng lựa chọn họ**.

### 2.1. Cấu trúc trước và sau

~~~mermaid
flowchart LR
    subgraph Before["Trước refactor"]
        C1["SettingsPanel"] --> LB["new LightButton()"]
        C1 --> LC["new LightCheckbox()"]
    end
    subgraph After["Sau refactor"]
        Root["Bootstrap / composition root"] -->|"new LightUiFactory hoặc DarkUiFactory"| Concrete["ConcreteFactory"]
        Root -->|"truyền UiFactory qua constructor"| C2["SettingsPanel"]
        C2 -->|"createButton / createCheckbox"| F["UiFactory"]
        Concrete -.->|"implements"| F
        F --> B["Button interface"]
        F --> K["Checkbox interface"]
    end
~~~

Sơ đồ “sau refactor” mô tả **vai trò** của các đối tượng. Trong Java, lời gọi `factory.createButton()` thực thi trong concrete factory tương ứng, rồi trả sản phẩm về client qua interface `Button`; bản thân interface không tạo đối tượng.

## 3. Mã trước refactor: client tự tạo lớp cụ thể

Đặt ví dụ dưới đây trong file `BeforeInjection.java`. Đây là một chương trình chạy độc lập bằng Java 17+.

~~~java
public final class BeforeInjection {

    static final class LightButton {
        String render() {
            return "LightButton";
        }
    }

    static final class LightCheckbox {
        private boolean checked;

        void setChecked(boolean checked) {
            this.checked = checked;
        }

        boolean isChecked() {
            return checked;
        }

        String render() {
            return "LightCheckbox";
        }
    }

    static final class SettingsPanel {
        // Client tự chọn và tự tạo sản phẩm Light.
        private final LightButton saveButton = new LightButton();
        private final LightCheckbox notifications = new LightCheckbox();

        void setNotificationsEnabled(boolean enabled) {
            notifications.setChecked(enabled);
        }

        String render() {
            return saveButton.render()
                + " | " + notifications.render()
                + " | notifications=" + notifications.isChecked();
        }
    }

    public static void main(String[] args) {
        SettingsPanel panel = new SettingsPanel();
        panel.setNotificationsEnabled(true);
        System.out.println(panel.render());
    }
}
~~~

Chạy:

~~~bash
javac BeforeInjection.java
java BeforeInjection
~~~

Kết quả dự kiến:

~~~text
LightButton | LightCheckbox | notifications=true
~~~

Đây là **mốc hành vi** cần bảo toàn sau refactor. Việc gán `true` cho Checkbox và đầu ra tương ứng phải không thay đổi khi vẫn chọn Light.

### 3.1. Vì sao phụ thuộc hiện tại gây khó khăn?

Client có ba trách nhiệm đang bị trộn lẫn:

1. **Chọn implementation:** quyết định dùng `LightButton` và `LightCheckbox`.
2. **Tạo đối tượng:** gọi constructor của từng concrete product.
3. **Thực hiện chức năng:** bật thông báo và render màn hình.

Trong Abstract Factory, hai trách nhiệm đầu nên thuộc về phần cấu hình và concrete factory; trách nhiệm thứ ba vẫn thuộc client. Tách các trách nhiệm này làm thay đổi quan hệ phụ thuộc và giúp mở rộng theo họ sản phẩm.

## 4. Các bước refactor an toàn

### Bước 1 — Viết lại hợp đồng của product interface

Xác định những thao tác mà `SettingsPanel` thực sự cần: Button có `render()`; Checkbox có `render()`, `setChecked(boolean)` và `isChecked()`.

~~~java
interface Button {
    String render();
}

interface Checkbox {
    String render();
    void setChecked(boolean checked);
    boolean isChecked();
}
~~~

Các concrete product sau đó implements interface tương ứng. Nếu các implementation trước đây đã cùng kế thừa một interface có đủ hợp đồng, tái sử dụng interface đó thay vì tự tạo một interface mới chỉ vì cần DI.

**Không đẩy toàn bộ API của concrete product lên interface.** Giữ đúng các thao tác mà client cần để tránh tạo abstraction quá lớn. Những chi tiết như màu, mã CSS hay renderer riêng có thể ở lại concrete product.

### Bước 2 — Định nghĩa abstract factory

~~~java
interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

`UiFactory` biểu diễn lời hứa: mỗi factory có thể tạo **đủ hai loại sản phẩm thuộc cùng một họ**. Nó không chứa `if` chọn Light/Dark và không cần biết cấu hình nhập từ command line.

### Bước 3 — Đưa logic chọn sản phẩm vào concrete factory

~~~java
final class LightUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new LightButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new LightCheckbox();
    }
}
~~~

`DarkUiFactory` thực hiện cùng hợp đồng nhưng trả `DarkButton` và `DarkCheckbox`. Concrete factory là nơi được phép biết **lớp sản phẩm cụ thể**; client không cần biết.

### Bước 4 — Inject factory qua constructor của client

Thay thế các field concrete và việc tự gọi `new`:

~~~java
// Trước
private final LightButton saveButton = new LightButton();
private final LightCheckbox notifications = new LightCheckbox();
~~~

bằng:

~~~java
// Sau: client chỉ phụ thuộc abstraction.
private final Button saveButton;
private final Checkbox notifications;

SettingsPanel(UiFactory factory) {
    java.util.Objects.requireNonNull(factory, "factory");
    saveButton = java.util.Objects.requireNonNull(
        factory.createButton(), "createButton returned null"
    );
    notifications = java.util.Objects.requireNonNull(
        factory.createCheckbox(), "createCheckbox returned null"
    );
}
~~~

Constructor bảo đảm rằng một `SettingsPanel` được tạo thành công luôn có đủ hai sản phẩm. Kiểm tra `null` đưa lỗi cấu hình lên thời điểm khởi tạo, thay vì để `NullPointerException` xảy ra muộn khi render.

**Đây là eager creation:** client nhận factory qua constructor và gọi ngay các factory method để tạo product. Nếu ứng dụng chỉ cần sản phẩm khi màn hình được mở, có thể lưu `UiFactory` làm field và gọi factory method khi cần. Dù dùng eager hay lazy, quyết định chọn concrete factory vẫn nằm ngoài client.

### Bước 5 — Lắp factory ở composition root

~~~java
UiFactory factory = new DarkUiFactory();
SettingsPanel panel = new SettingsPanel(factory);
~~~

Composition root là nơi duy nhất trong ví dụ này biết cấu hình và concrete factory. Khi muốn đổi Light thành Dark, chỉ thay **đối tượng được truyền vào**, không phải sửa logic `SettingsPanel`.

### Bước 6 — Xác nhận hành vi và xóa nhánh cũ

Chạy lại kịch bản Light đã ghi nhận trước refactor và so sánh kết quả. Tiếp theo chạy kịch bản Dark, kiểm tra Button/Checkbox cùng họ và hoạt động đúng. Sau khi mọi caller được chuyển sang constructor mới, xóa các constructor cũ tự tạo concrete product và các nhánh chọn theme bị trùng trách nhiệm.

## 5. Mã Java sau refactor: ví dụ hoàn chỉnh

Đặt toàn bộ đoạn sau vào `AfterInjection.java`. Mã minh họa có thể biên dịch độc lập bằng JDK 17+. Thuộc tính `theme()` được thêm để thể hiện rõ **họ** của sản phẩm trong ví dụ và phục vụ kiểm tra tính nhất quán.

~~~java
import java.util.Locale;
import java.util.Objects;

public final class AfterInjection {

    enum Theme {
        LIGHT, DARK
    }

    // Abstract products
    interface UiProduct {
        Theme theme();
        String render();
    }

    interface Button extends UiProduct {}

    interface Checkbox extends UiProduct {
        void setChecked(boolean checked);
        boolean isChecked();
    }

    // Light product family
    record LightButton() implements Button {
        @Override
        public Theme theme() {
            return Theme.LIGHT;
        }

        @Override
        public String render() {
            return "LightButton";
        }
    }

    static final class LightCheckbox implements Checkbox {
        private boolean checked;

        @Override
        public Theme theme() {
            return Theme.LIGHT;
        }

        @Override
        public void setChecked(boolean checked) {
            this.checked = checked;
        }

        @Override
        public boolean isChecked() {
            return checked;
        }

        @Override
        public String render() {
            return "LightCheckbox";
        }
    }

    // Dark product family
    record DarkButton() implements Button {
        @Override
        public Theme theme() {
            return Theme.DARK;
        }

        @Override
        public String render() {
            return "DarkButton";
        }
    }

    static final class DarkCheckbox implements Checkbox {
        private boolean checked;

        @Override
        public Theme theme() {
            return Theme.DARK;
        }

        @Override
        public void setChecked(boolean checked) {
            this.checked = checked;
        }

        @Override
        public boolean isChecked() {
            return checked;
        }

        @Override
        public String render() {
            return "DarkCheckbox";
        }
    }

    // Abstract factory
    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Concrete factories
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

    // Client: không có tham chiếu tới các concrete product/factory
    static final class SettingsPanel {
        private final Button saveButton;
        private final Checkbox notifications;

        SettingsPanel(UiFactory factory) {
            Objects.requireNonNull(factory, "factory");
            saveButton = Objects.requireNonNull(
                factory.createButton(), "createButton returned null"
            );
            notifications = Objects.requireNonNull(
                factory.createCheckbox(), "createCheckbox returned null"
            );
        }

        void setNotificationsEnabled(boolean enabled) {
            notifications.setChecked(enabled);
        }

        boolean notificationsEnabled() {
            return notifications.isChecked();
        }

        Theme buttonTheme() {
            return saveButton.theme();
        }

        Theme checkboxTheme() {
            return notifications.theme();
        }

        String render() {
            return saveButton.render()
                + " | " + notifications.render()
                + " | notifications=" + notifications.isChecked();
        }
    }

    // Composition root: chọn và inject concrete factory
    public static void main(String[] args) {
        String family = args.length == 0
            ? "light"
            : args[0].toLowerCase(Locale.ROOT);

        UiFactory factory = switch (family) {
            case "light" -> new LightUiFactory();
            case "dark" -> new DarkUiFactory();
            default -> throw new IllegalArgumentException(
                "Unsupported family: " + family
            );
        };

        SettingsPanel panel = new SettingsPanel(factory);
        panel.setNotificationsEnabled(true);
        System.out.println(panel.render());
    }
}
~~~

Chạy:

~~~bash
javac AfterInjection.java
java AfterInjection light
java AfterInjection dark
~~~

Output dự kiến:

~~~text
LightButton | LightCheckbox | notifications=true
DarkButton | DarkCheckbox | notifications=true
~~~

Mỗi dòng trên thuộc **một lần chạy riêng** với argument Light hoặc Dark. Bản Light giữ cùng nội dung đầu ra với `BeforeInjection`; bản Dark chạy qua **cùng một client**, chỉ khác concrete factory do `main()` lựa chọn.

### 5.1. Phân biệt việc inject factory và inject sản phẩm

Constructor ở trên nhận **`UiFactory`**, sau đó client gọi `createButton()` và `createCheckbox()`. Một phương án khác là inject trực tiếp `Button` và `Checkbox`:

~~~java
SettingsPanel(Button button, Checkbox checkbox) {
    this.saveButton = Objects.requireNonNull(button);
    this.notifications = Objects.requireNonNull(checkbox);
}
~~~

Phương án inject từng sản phẩm có thể phù hợp khi client chỉ cần các dependency đã được lắp ráp sẵn. Tuy nhiên, nhiệm vụ của bài là chuyển client sang **constructor injection của factory** để client có thể chủ động tạo **các sản phẩm cùng họ** theo thời điểm và số lượng cần thiết.

Nếu inject riêng `LightButton` và `DarkCheckbox` từ hai nguồn khác nhau, việc chọn họ sẽ phân tán và dễ vi phạm tính nhất quán. Chọn inject factory hay inject trọn một **product bundle** phụ thuộc quy tắc vòng đời và cách client sử dụng sản phẩm.

## 6. Luồng gọi sau khi chuyển sang constructor injection

~~~mermaid
sequenceDiagram
    autonumber
    participant Root as Composition root
    participant Factory as DarkUiFactory
    participant Client as SettingsPanel
    participant Button as DarkButton
    participant Checkbox as DarkCheckbox

    Root->>Factory: new DarkUiFactory()
    Root->>Client: new SettingsPanel(factory: UiFactory)
    activate Client
    Client->>Factory: createButton()
    Factory->>Button: new DarkButton()
    Button-->>Factory: instance
    Factory-->>Client: Button
    Client->>Factory: createCheckbox()
    Factory->>Checkbox: new DarkCheckbox()
    Checkbox-->>Factory: instance
    Factory-->>Client: Checkbox
    deactivate Client
    Root->>Client: setNotificationsEnabled(true)
    Client->>Checkbox: setChecked(true)
    Root->>Client: render()
    Client->>Button: render()
    Client->>Checkbox: render()
    Client-->>Root: "DarkButton | DarkCheckbox | notifications=true"
~~~

Trong sequence này:

- `main()` chọn `DarkUiFactory` dựa trên đầu vào. **Client không chọn họ.**
- Constructor nhận một tham chiếu kiểu `UiFactory`, nhưng tại runtime tham chiếu ấy trỏ tới `DarkUiFactory`.
- Hai lời gọi factory method được **dynamic dispatch** đến `DarkUiFactory` và trả về `DarkButton`, `DarkCheckbox`.
- Các sản phẩm được lưu dưới kiểu `Button` và `Checkbox`. Khi client gọi `render()`, Java thực thi phương thức của concrete product tương ứng.

**Constructor injection không có nghĩa DI framework tự động tạo đúng họ.** Với Java thủ công, composition root là nơi chịu trách nhiệm chọn và cấp dependency; với Spring hoặc framework khác, nhiệm vụ đó thường được thể hiện qua cấu hình binding/bean.

## 7. Kiểm thử để bảo vệ refactor

Tái cấu trúc thành công cần chứng minh hai điều: **hành vi cũ được giữ** khi dùng Light, và client hoạt động với một họ mới **mà không phải sửa logic**. Có thể thêm lớp kiểm thử thứ ba: client thật sự dựa vào factory do caller inject.

Ví dụ JUnit 5 dưới đây đặt trong file `AfterInjectionTest.java`, cùng package với `AfterInjection.java`. Cấu hình dependency `junit-jupiter` (bao gồm `junit-jupiter-params`) ở dự án kiểm thử.

### 7.1. Chạy cùng contract trên từng họ

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class AfterInjectionTest {

    record FamilyCase(
        String name,
        AfterInjection.Theme expectedTheme,
        Supplier<AfterInjection.UiFactory> createFactory,
        String expectedOutput
    ) {
        @Override
        public String toString() {
            return name;
        }
    }

    static Stream<FamilyCase> families() {
        return Stream.of(
            new FamilyCase(
                "Light",
                AfterInjection.Theme.LIGHT,
                AfterInjection.LightUiFactory::new,
                "LightButton | LightCheckbox | notifications=true"
            ),
            new FamilyCase(
                "Dark",
                AfterInjection.Theme.DARK,
                AfterInjection.DarkUiFactory::new,
                "DarkButton | DarkCheckbox | notifications=true"
            )
        );
    }

    @ParameterizedTest(name = "{0} - constructor injection")
    @MethodSource("families")
    void one_client_works_with_each_family(FamilyCase c) {
        AfterInjection.SettingsPanel panel =
            new AfterInjection.SettingsPanel(c.createFactory().get());

        assertEquals(c.expectedTheme(), panel.buttonTheme());
        assertEquals(c.expectedTheme(), panel.checkboxTheme());

        panel.setNotificationsEnabled(true);
        assertTrue(panel.notificationsEnabled());
        assertEquals(c.expectedOutput(), panel.render());

        panel.setNotificationsEnabled(false);
        assertFalse(panel.notificationsEnabled());
    }

    @Test
    void rejects_missing_factory() {
        NullPointerException error = assertThrows(
            NullPointerException.class,
            () -> new AfterInjection.SettingsPanel(null)
        );

        assertEquals("factory", error.getMessage());
    }

    @Test
    void client_uses_factory_it_was_given() {
        List<String> calls = new ArrayList<>();

        AfterInjection.UiFactory recordingFactory =
            new AfterInjection.UiFactory() {

                @Override
                public AfterInjection.Button createButton() {
                    calls.add("createButton");
                    return new AfterInjection.Button() {
                        @Override
                        public AfterInjection.Theme theme() {
                            return AfterInjection.Theme.LIGHT;
                        }

                        @Override
                        public String render() {
                            return "FakeButton";
                        }
                    };
                }

                @Override
                public AfterInjection.Checkbox createCheckbox() {
                    calls.add("createCheckbox");
                    return new AfterInjection.Checkbox() {
                        private boolean checked;

                        @Override
                        public AfterInjection.Theme theme() {
                            return AfterInjection.Theme.LIGHT;
                        }

                        @Override
                        public void setChecked(boolean value) {
                            checked = value;
                        }

                        @Override
                        public boolean isChecked() {
                            return checked;
                        }

                        @Override
                        public String render() {
                            return "FakeCheckbox";
                        }
                    };
                }
            };

        AfterInjection.SettingsPanel panel =
            new AfterInjection.SettingsPanel(recordingFactory);

        assertEquals(
            List.of("createButton", "createCheckbox"),
            calls
        );

        panel.setNotificationsEnabled(true);

        assertEquals(
            "FakeButton | FakeCheckbox | notifications=true",
            panel.render()
        );
    }
}
~~~

Các test minh họa có tổng cộng **4 lượt chạy**: hai lượt tham số hóa (Light và Dark), một test từ chối factory `null` và một test xác nhận factory được inject thực sự được gọi.

Test recording factory không cần biết `LightButton` hoặc `DarkButton`. Nếu client vô tình quay lại `new LightButton()` và `new LightCheckbox()`, output `FakeButton | FakeCheckbox` sẽ không xuất hiện như kỳ vọng. Đây là một kiểm tra hành vi hữu ích cho **đường phụ thuộc** sau refactor.

### 7.2. Những assertion nào thực sự quan trọng?

| ID | Điều cần chứng minh | Dấu hiệu thất bại |
| --- | --- | --- |
| **RF-01** | Với factory Light, kết quả giống trước refactor | Output thay đổi hoặc Checkbox không nhận trạng thái |
| **RF-02** | Với factory Dark, không phải sửa client | Output không phải Dark hoặc có sản phẩm Light xen vào |
| **RF-03** | Client dùng factory do caller truyền vào | Recording factory không ghi được lời gọi |
| **RF-04** | Client yêu cầu đủ các loại sản phẩm | Thiếu `createButton()` hoặc `createCheckbox()` |
| **RF-05** | Đầu vào factory không hợp lệ bị từ chối sớm | Constructor nhận `null` và lỗi chỉ xảy ra về sau |
| **RF-06** | Product của factory đúng họ mong đợi | `buttonTheme()` hoặc `checkboxTheme()` khác oracle Light/Dark |

Kỳ vọng phải đến từ **đặc tả hoặc fixture độc lập**, không lấy từ chính sản phẩm đang được kiểm thử. Chẳng hạn, phép so `assertEquals(panel.buttonTheme(), panel.checkboxTheme())` chỉ xác nhận hai sản phẩm cùng khai báo một họ; nếu cả hai đều sai họ, test vẫn có thể xanh. `expectedTheme` ở fixture giúp phát hiện trường hợp ấy.

## 8. Các tình huống dễ gây lỗi khi migration

### 8.1. Inject concrete factory thay vì abstract factory

~~~java
// Đỡ hardcode việc new product, nhưng vẫn gắn client với họ Light.
SettingsPanel(LightUiFactory factory) {
    this.saveButton = factory.createButton();
    this.notifications = factory.createCheckbox();
}
~~~

Constructor này chỉ nhận `LightUiFactory`; muốn dùng `DarkUiFactory` lại phải sửa kiểu tham số hoặc viết constructor khác. Kiểu tham số nên là `UiFactory` để client không phụ thuộc family cụ thể.

### 8.2. Constructor mặc định tự khởi tạo concrete factory

~~~java
// Vẫn cố định Light ngay trong client.
SettingsPanel() {
    this(new LightUiFactory());
}
~~~

Đây có thể là bước chuyển tiếp ngắn hạn khi nhiều caller cũ chưa được cập nhật, nhưng nếu giữ lâu dài, client vẫn biết `LightUiFactory` và khó bảo đảm mọi lối khởi tạo đều dùng cấu hình chính thức. Nên cập nhật caller về một constructor nhận `UiFactory`, rồi loại bỏ constructor mặc định.

### 8.3. Đặt Service Locator bên trong client

~~~java
SettingsPanel() {
    UiFactory factory = GlobalRegistry.resolve(UiFactory.class);
    this.saveButton = factory.createButton();
    this.notifications = factory.createCheckbox();
}
~~~

Client không còn gọi trực tiếp `new LightUiFactory()` nhưng vẫn **tự tìm dependency** thông qua một registry toàn cục. Quan hệ phụ thuộc bị ẩn, việc khởi tạo trong test phải cấu hình global state và test dễ ảnh hưởng lẫn nhau.

Với constructor injection, dependency bắt buộc được biểu diễn tường minh trong chữ ký constructor: `SettingsPanel(UiFactory factory)`.

### 8.4. Chọn một họ cho Button và họ khác cho Checkbox

~~~java
UiFactory light = new LightUiFactory();
UiFactory dark = new DarkUiFactory();

Button button = light.createButton();
Checkbox checkbox = dark.createCheckbox();
~~~

Các product vẫn đáp ứng interface nhưng không thuộc cùng họ. Trong bài tập, một client nhận **một factory** và dùng factory ấy để tạo cả Button và Checkbox. Nếu hệ thống có nhiều factory độc lập, cần xác định rõ các quy tắc phối hợp product giữa những factory đó.

### 8.5. Inject một factory nhưng tiếp tục dùng concrete class trong logic

~~~java
Button button = factory.createButton();

if (button instanceof LightButton) {
    // Logic riêng Light bên trong client.
}
~~~

Dù việc khởi tạo đã được tách ra, client vẫn phụ thuộc implementation. Nếu hành vi là chung của mọi Button, đưa hành vi đó vào `Button` interface. Nếu đó là capability đặc thù, thiết kế một abstraction bổ sung hoặc chuyển xử lý đến nơi có trách nhiệm, thay vì để client chuyển kiểu theo concrete class.

### 8.6. Bỏ qua vòng đời của factory và sản phẩm

Constructor injection **không tự giải quyết ownership**. Trong ví dụ, Button và Checkbox là đối tượng không cần đóng. Với database session, connection, writer hoặc resource khác, phải quy định ai sở hữu resource và đóng lúc nào.

- Nếu factory chỉ mượn connection pool từ bootstrap, `SettingsPanel` không nên đóng pool.
- Nếu factory trả về product handle có `close()`, xác định caller hoặc session nào sở hữu handle đó.
- Nếu thay factory khi màn hình đang hoạt động, product cũ **không tự biến đổi thành product mới**. Cần xây dựng lại phần phụ thuộc hoặc cung cấp một luồng tái cấu hình an toàn.

## 9. Giữ hành vi cũ trong các bước chuyển đổi thực tế

Một refactor trên code production thường có nhiều caller và test. Có thể tiến hành theo các checkpoint nhỏ:

| Giai đoạn | Chỉnh sửa | Kiểm chứng nên có |
| --- | --- | --- |
| **0. Chốt hành vi** | Ghi nhận output, thao tác UI, bất biến họ Light | Regression test hiện tại xanh |
| **1. Tạo abstraction** | Tạo/chuẩn hóa `Button`, `Checkbox`, `UiFactory` | Các concrete product/factory biên dịch và đáp ứng contract |
| **2. Inject vào client** | Thay field concrete bằng interface; thêm `SettingsPanel(UiFactory)` | Client chạy với Light, giữ hành vi ban đầu |
| **3. Cập nhật caller** | Composition root tạo `LightUiFactory` và truyền qua constructor | Không còn caller tạo client không có dependency |
| **4. Thêm họ Dark** | Thêm product/factory Dark, đăng ký ở composition root | Cùng test chạy cho Dark; cả hai product cùng họ |
| **5. Gỡ đường cũ** | Xóa `new` product trong client, constructor mặc định hoặc nhánh chọn theme trùng lặp | Không còn phụ thuộc concrete product/factory trong client |

Cách tổ chức checkpoint giúp tìm lỗi sớm. Một thay đổi về cấu trúc dependency nên được kiểm tra bằng hành vi đã có, còn việc thêm theme mới nên có ca test riêng để tránh nhầm lỗi regression với lỗi triển khai tính năng mới.

**Không xóa hoặc thay đổi các thành phần ngoài phạm vi đã kiểm soát.** Khi tái cấu trúc một hệ thống thực, trước khi xóa một constructor cũ cần tìm đầy đủ caller và chuyển chúng sang chữ ký mới.

## 10. Constructor injection tác động thế nào tới khả năng mở rộng?

Sau refactor, muốn thêm họ High Contrast (khi cả Button và Checkbox đã có interface ổn định):

~~~java
final class HighContrastUiFactory implements UiFactory {
    @Override
    public Button createButton() {
        return new HighContrastButton();
    }

    @Override
    public Checkbox createCheckbox() {
        return new HighContrastCheckbox();
    }
}
~~~

Đoạn trên là phác thảo mở rộng: cần định nghĩa `HighContrastButton` và `HighContrastCheckbox` theo hợp đồng các abstract product. Điểm lựa chọn factory trong composition root được bổ sung một cấu hình mới; client vẫn nhận `UiFactory`.

Nhưng nếu yêu cầu mới là **thêm loại sản phẩm `Slider` vào mọi họ**, cần mở rộng `UiFactory` bằng `createSlider()` và cập nhật các concrete factory hiện có. Constructor injection giúp **tách phụ thuộc client khỏi lớp cụ thể**, không làm biến mất chi phí mở rộng hợp đồng abstract factory.

Một tiêu chí đánh giá thiết kế là: **client có còn phải sửa vì một concrete family mới, dù hành vi nghiệp vụ của client không đổi hay không?** Nếu câu trả lời là có, hãy tìm xem concrete class hoặc logic chọn family còn bị rò vào client ở đâu.

## 11. Phân biệt constructor injection với các phương thức đưa dependency khác

| Cách cấp dependency | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Constructor injection** | `new SettingsPanel(uiFactory)` | Dependency bắt buộc, thể hiện ngay khi tạo object |
| **Method injection** | `panel.show(uiFactory)` | Factory chỉ cần ở một thao tác; caller phải truyền mỗi lần |
| **Setter injection** | `panel.setFactory(uiFactory)` | Có thể đổi dependency sau tạo; dễ có trạng thái chưa cấu hình nếu không kiểm soát |
| **Service Locator** | `Registry.resolve(UiFactory.class)` trong client | Quan hệ phụ thuộc bị ẩn sau tra cứu toàn cục |
| **Hardcode concrete class** | `new LightUiFactory()` trong client | Khó thay họ và khó cô lập test |

Constructor injection thường phù hợp khi factory là **dependency bắt buộc** xuyên suốt vòng đời của client. Nếu client chỉ thực hiện một lệnh ngắn và factory là tham số cho lệnh đó, method injection cũng có thể hợp lý. Không có quy tắc rằng mọi dependency trong mọi dự án đều phải inject qua constructor.

### 11.1. Không cần DI container cho bài toán này

`new SettingsPanel(new LightUiFactory())` ở bootstrap đã là constructor injection, vì **bên ngoài client** quyết định tạo factory. Spring hoặc Guice chỉ tự động hóa bước cấu hình/lắp ráp; việc phụ thuộc vào interface và quy ước ownership vẫn là thiết kế của ứng dụng.

### 11.2. Kiểm tra scope khi factory có state

Một factory có thể là stateless và được dùng lại; hoặc có thể giữ configuration, tenant context hoặc session. Nếu có state hoặc tài nguyên, phải xác định factory được tạo **mỗi request**, **mỗi phiên**, hay **toàn ứng dụng**. Đưa cùng một instance factory stateful vào nhiều client không tự bảo đảm thread safety.

Với thiết kế hiện tại, `SettingsPanel` chỉ dùng factory trong constructor và giữ các product tạo được. Nếu muốn thay họ về sau, hệ thống có thể **dựng một SettingsPanel mới với factory mới**. Tránh sửa reference factory trong một client đang giữ product cũ mà không có chiến lược đồng bộ.

## 12. Bài tập thực hành

Một hệ thống xuất báo cáo có hai họ:

- `PdfExportFactory` tạo `PdfHeader` và `PdfTable`.
- `HtmlExportFactory` tạo `HtmlHeader` và `HtmlTable`.

Đoạn code ban đầu:

~~~java
class ReportPage {
    private final PdfHeader header = new PdfHeader();
    private final PdfTable table = new PdfTable();

    String export() {
        return header.render() + table.render();
    }
}
~~~

**Yêu cầu:**

1. Định nghĩa `Header`, `Table` và `ExportFactory`, trong đó factory có `createHeader()` và `createTable()`.
2. Tạo `PdfExportFactory` và `HtmlExportFactory`, mỗi factory trả sản phẩm cùng họ.
3. Đổi `ReportPage` để nhận `ExportFactory` qua constructor, lưu sản phẩm dưới kiểu interface.
4. Ở composition root, chọn PDF hoặc HTML dựa trên cấu hình và truyền factory vào `ReportPage`.
5. Viết test dùng một fake factory để xác nhận `ReportPage` thực sự dùng dependency được inject.
6. Viết test dùng hai factory thật, xác nhận các sản phẩm thuộc cùng một họ và output đúng định dạng.
7. Chỉ ra vì sao `new PdfHeader()` vẫn nằm trong `ReportPage` là chưa hoàn thành refactor.

**Gợi ý thiết kế:**

~~~java
interface ExportFactory {
    Header createHeader();
    Table createTable();
}

class ReportPage {
    private final Header header;
    private final Table table;

    ReportPage(ExportFactory factory) {
        java.util.Objects.requireNonNull(factory);
        this.header = java.util.Objects.requireNonNull(
            factory.createHeader()
        );
        this.table = java.util.Objects.requireNonNull(
            factory.createTable()
        );
    }

    String export() {
        return header.render() + table.render();
    }
}
~~~

Đoạn gợi ý giả định đã có hai product interface `Header` và `Table` khai báo `render()`; phần còn lại của bài tập là hiện thực hai họ và test. Đừng sửa thân `ReportPage.export()` để thêm một nhánh `if (pdf)`: mục tiêu là giữ logic client độc lập với concrete family.

## 13. Checklist review sau refactor

- [ ] Constructor client nhận `UiFactory` hoặc abstraction tương đương, **không nhận một concrete factory cố định**.
- [ ] Client không trực tiếp `new` concrete product.
- [ ] Client không tự đọc cấu hình để chọn Light/Dark; composition root chịu trách nhiệm chọn họ.
- [ ] Các concrete factory tạo đủ product đúng interface và cùng họ.
- [ ] Product được lưu và sử dụng qua interface; không ép kiểu về concrete class trong client.
- [ ] Factory là dependency bắt buộc, được kiểm tra ở lúc khởi tạo client.
- [ ] Các caller của constructor cũ đã được cập nhật; nhánh cũ không còn cần thiết được loại bỏ.
- [ ] Regression test của họ hiện có vẫn xanh.
- [ ] Cùng một bộ test chạy với nhiều concrete factory, có kỳ vọng độc lập.
- [ ] Trường hợp factory dùng tài nguyên hoặc có state, phạm vi sử dụng và quyền đóng đã được xác định.
- [ ] Thêm concrete family mới chỉ cần concrete products, concrete factory, cấu hình chọn và test, nếu product interfaces không thay đổi.

## 14. Ghi nhớ

Khi client tự gọi `new LightButton()`, nó vừa thực hiện nghiệp vụ vừa quyết định lớp sản phẩm cần tạo. **Constructor injection của Abstract Factory** chuyển quyết định đó ra ngoài: composition root chọn concrete factory, client nhận `UiFactory`, sau đó gọi các factory method và sử dụng product qua interface.

Cấu trúc này làm phụ thuộc rõ ràng, giúp test bằng fake factory và cho phép thay Light bằng Dark mà không sửa logic màn hình. Để refactor an toàn, hãy chốt hành vi ban đầu, chuyển từng ranh giới phụ thuộc, kiểm tra lại bằng test và giữ tính nhất quán của toàn bộ họ sản phẩm.
