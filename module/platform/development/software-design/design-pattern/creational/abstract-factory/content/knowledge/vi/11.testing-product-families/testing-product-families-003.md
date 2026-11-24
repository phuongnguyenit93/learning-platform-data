# Dùng bộ contract test chung để kiểm tra mọi họ thực hiện đúng product interface

## 1. Bài toán: các họ sản phẩm có cùng lời hứa hành vi

**Abstract Factory** là mẫu thiết kế khởi tạo cho phép client làm việc với **một họ sản phẩm liên quan** thông qua các interface chung, thay vì phụ thuộc lớp cụ thể. Ví dụ, ứng dụng hỗ trợ giao diện sáng (Light) và tối (Dark):

- `LightUiFactory` cung cấp `LightButton` và `LightCheckbox`.
- `DarkUiFactory` cung cấp `DarkButton` và `DarkCheckbox`.
- `SettingsPanel` chỉ biết `UiFactory`, `Button` và `Checkbox`.

Các họ có thể khác màu sắc, tài nguyên và cách render. Nhưng vì cùng thực hiện `Button`, mọi button đều phải tuân theo quy tắc chung: một cú click khi đang bật sẽ chạy callback; khi bị vô hiệu hóa thì không chạy callback. Tương tự, `Checkbox` phải lưu và trả lại đúng trạng thái chọn.

Lỗi thường gặp là viết test riêng cho Light và Dark, sau đó sao chép cùng những assertion. Khi thêm một họ, lập trình viên có thể quên một ca kiểm thử; khi hợp đồng thay đổi, mỗi bộ test lại cần sửa thủ công.

**Contract test** giải quyết bằng cách định nghĩa **một bộ kiểm thử hành vi của interface** và chạy nguyên bộ đó với **từng concrete factory**. Đối tượng được thử là sản phẩm thật mà factory trả về, còn dữ liệu test chỉ thay đổi theo họ.

Mục tiêu sau bài này:

1. Phân biệt hợp đồng của product interface với đặc điểm riêng của concrete product.
2. Viết bộ contract test dùng chung cho từng loại sản phẩm và chạy trên tất cả họ.
3. Thiết lập dữ liệu và kết quả mong đợi độc lập để test có thể phát hiện factory trả sai sản phẩm.
4. Kiểm tra các bất biến ở mức factory và các hành vi cộng tác mà unit contract test chưa chứng minh.
5. Mở rộng số họ hoặc số loại sản phẩm mà không phải sao chép hàng loạt test.

## 2. Product interface phải mô tả cả hành vi

Một interface chỉ khai báo tên phương thức và kiểu tham số. **Hợp đồng hành vi** còn nói rõ trạng thái ban đầu, điều kiện hợp lệ, hậu điều kiện và những trường hợp biên.

Với ví dụ học tập, quy ước chung là:

| Interface | Thao tác | Hợp đồng mà mọi họ phải giữ |
| --- | --- | --- |
| `Button` | `isEnabled()` | Button mới tạo ở trạng thái enabled |
| `Button` | `onClick(handler)` | Đăng ký handler mới **thay thế** handler cũ |
| `Button` | `click()` khi enabled | Gọi handler hiện tại **đúng một lần**, đồng bộ |
| `Button` | `click()` khi disabled | Không gọi handler |
| `Button` | `setEnabled(true/false)` | Giá trị đọc qua `isEnabled()` phản ánh thao tác vừa thực hiện |
| `Checkbox` | `isChecked()` | Checkbox mới tạo ở trạng thái unchecked |
| `Checkbox` | `setChecked(value)` | `isChecked()` trả về chính `value`, kể cả sau khi gán lặp |
| Cả hai | `theme()` | Trả về đúng họ Light hoặc Dark theo factory được chọn |
| `UiFactory` | `createButton()`, `createCheckbox()` | Không trả `null`; mỗi lần gọi tạo instance sản phẩm độc lập |

Các lựa chọn như “click đồng bộ”, “handler mới thay thế handler cũ” hay “mỗi lần tạo là một instance mới” là **quy định minh họa của hệ thống này**, không phải luật bắt buộc cho mọi Abstract Factory. Nếu API thực tế cho phép singleton hoặc callback bất đồng bộ, cần viết hợp đồng và test đúng theo API đó.

Hợp đồng chung không nên ép mọi họ có cùng màu, class CSS, hiệu ứng animation hay cơ chế render. Đây là những chi tiết có thể khác nhau mà client vẫn hoạt động đúng.

## 3. Kiến trúc cần kiểm thử

~~~mermaid
flowchart TB
    Client["SettingsPanel (client)"] --> AF["UiFactory"]
    AF --> LF["LightUiFactory"]
    AF --> DF["DarkUiFactory"]
    LF --> LB["LightButton : Button"]
    LF --> LC["LightCheckbox : Checkbox"]
    DF --> DB["DarkButton : Button"]
    DF --> DC["DarkCheckbox : Checkbox"]
    BT["Button contract tests"] -.-> LB
    BT -.-> DB
    CT["Checkbox contract tests"] -.-> LC
    CT -.-> DC
~~~

Có hai cấp độ trách nhiệm:

- **Product contract:** `LightButton` và `DarkButton` phải cùng đáp ứng mọi quy tắc của `Button`; tương tự với `Checkbox`.
- **Family invariant:** `LightUiFactory` phải trả về **cả Button lẫn Checkbox thuộc Light**; `DarkUiFactory` phải trả về cả hai thuộc Dark.

Việc mọi product đều hợp lệ riêng lẻ **chưa chứng minh** factory ghép đúng họ. Nếu `LightUiFactory.createCheckbox()` trả về `DarkCheckbox`, contract `Checkbox` vẫn có thể thành công hoàn toàn. Vì thế phải có thêm assertion về họ mong đợi.

## 4. Tạo ví dụ Java đủ nhỏ để quan sát hành vi

Ví dụ dùng **Java 17+** và JUnit Jupiter 5. Các interface sau giữ nguyên ý nghĩa cho cả hai họ; `theme()` là thuộc tính định danh họ được thêm vào ví dụ để kiểm tra factory.

~~~java
enum Theme {
    LIGHT, DARK
}

interface Product {
    Theme theme();
}

interface Button extends Product {
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void onClick(Runnable handler);
    void click();
}

interface Checkbox extends Product {
    boolean isChecked();
    void setChecked(boolean checked);
}

interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

Trong dự án thật, product có thể cung cấp style token, cấu hình renderer hoặc metadata khác thay vì `theme()`. Nếu không muốn expose thông tin họ trong production interface, có thể kiểm tra thông qua cấu hình/renderer public hoặc một test adapter được thiết kế riêng; không cần sửa interface chỉ để phản ánh tên class.

Đây là một bộ hiện thực tối giản để chạy ví dụ. Phần trạng thái chung đặt trong base class; mỗi họ vẫn có lớp product và concrete factory riêng.

~~~java
import java.util.Objects;

abstract class BaseButton implements Button {
    private final Theme theme;
    private boolean enabled = true;
    private Runnable handler = () -> {};

    protected BaseButton(Theme theme) {
        this.theme = theme;
    }

    @Override
    public Theme theme() {
        return theme;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void onClick(Runnable handler) {
        this.handler = Objects.requireNonNull(handler);
    }

    @Override
    public void click() {
        if (enabled) {
            handler.run();
        }
    }
}

abstract class BaseCheckbox implements Checkbox {
    private final Theme theme;
    private boolean checked;

    protected BaseCheckbox(Theme theme) {
        this.theme = theme;
    }

    @Override
    public Theme theme() {
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
}

final class LightButton extends BaseButton {
    LightButton() {
        super(Theme.LIGHT);
    }
}

final class DarkButton extends BaseButton {
    DarkButton() {
        super(Theme.DARK);
    }
}

final class LightCheckbox extends BaseCheckbox {
    LightCheckbox() {
        super(Theme.LIGHT);
    }
}

final class DarkCheckbox extends BaseCheckbox {
    DarkCheckbox() {
        super(Theme.DARK);
    }
}

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

final class DarkUiFactory implements UiFactory {
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

Việc base class dùng chung logic chỉ giúp ví dụ ngắn gọn. Trong hệ thống thật, các sản phẩm có thể hoàn toàn khác code; **contract test không dựa vào base class**, chỉ gọi các phương thức public trên interface. Đây mới là lý do test dùng được cho các họ độc lập.

## 5. Thiết kế fixture theo họ, không theo lớp cụ thể

Thay vì viết riêng `LightButtonTest` và `DarkButtonTest` với các assertion giống nhau, khai báo **danh sách factory** để truyền vào một suite tham số hóa.

~~~java
import java.util.function.Supplier;
import java.util.stream.Stream;

record FactoryCase(
    String name,
    Theme expectedTheme,
    Supplier<UiFactory> createFactory
) {
    @Override
    public String toString() {
        return name;
    }
}

static Stream<FactoryCase> families() {
    return Stream.of(
        new FactoryCase("Light", Theme.LIGHT, LightUiFactory::new),
        new FactoryCase("Dark", Theme.DARK, DarkUiFactory::new)
    );
}
~~~

Đưa `FactoryCase` và `families()` vào class test ở phần tiếp theo. `Supplier<UiFactory>` tạo **factory mới cho mỗi lần chạy**, giúp tránh state từ test trước làm ảnh hưởng test sau. Dữ liệu `expectedTheme` được viết rõ theo đặc tả, **không suy ra từ `product.theme()` hay một giá trị tự báo cáo của factory đang được kiểm thử**.

Mỗi khi thêm họ `HighContrast`, chỉ cần bổ sung một `FactoryCase("HighContrast", Theme.HIGH_CONTRAST, HighContrastUiFactory::new)` và cập nhật enum `Theme` trong ví dụ. Bộ contract test sẽ tự chạy trên họ mới.

Nếu các factory cần database, mạng hoặc tài nguyên dùng chung, fixture cần thiết lập và dọn dẹp chúng theo vòng đời JUnit. Đảm bảo mỗi lần chạy độc lập hoặc cô lập bằng transaction/test container; không tái sử dụng một product đang có state giữa các ca.

## 6. Bộ contract test dùng chung bằng JUnit 5

Sử dụng dependency **JUnit Jupiter API + Params** (thông thường có trong `junit-jupiter`). Trong ví dụ, code của mục 5 được đặt vào class `UiFactoryContractTest` bên dưới; các import và phương thức test đặt trong cùng class.

### 6.1. Contract của Button: trạng thái, click và disabled

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class UiFactoryContractTest {

    // Chèn FactoryCase và families() từ mục 5 tại đây.

    @ParameterizedTest(name = "{0} / Button contract")
    @MethodSource("families")
    void every_button_obeys_interface_contract(FactoryCase c) {
        Button button = c.createFactory().get().createButton();

        assertNotNull(button);
        assertEquals(c.expectedTheme(), button.theme());
        assertTrue(button.isEnabled(), "Button mới phải enabled");

        AtomicInteger firstHandlerCalls = new AtomicInteger();
        button.onClick(firstHandlerCalls::incrementAndGet);

        button.click();
        assertEquals(1, firstHandlerCalls.get(),
            "Một click enabled phải gọi handler đúng một lần");

        button.setEnabled(false);
        assertFalse(button.isEnabled());
        button.click();
        assertEquals(1, firstHandlerCalls.get(),
            "Click disabled không được gọi handler");

        button.setEnabled(true);
        assertTrue(button.isEnabled());
        button.click();
        assertEquals(2, firstHandlerCalls.get(),
            "Bật lại phải khôi phục khả năng click");

        AtomicInteger secondHandlerCalls = new AtomicInteger();
        button.onClick(secondHandlerCalls::incrementAndGet);
        button.click();

        assertEquals(2, firstHandlerCalls.get(),
            "Đăng ký handler mới thay thế handler cũ");
        assertEquals(1, secondHandlerCalls.get());
    }

    @ParameterizedTest(name = "{0} / Checkbox contract")
    @MethodSource("families")
    void every_checkbox_obeys_interface_contract(FactoryCase c) {
        Checkbox checkbox = c.createFactory().get().createCheckbox();

        assertNotNull(checkbox);
        assertEquals(c.expectedTheme(), checkbox.theme());
        assertFalse(checkbox.isChecked(), "Checkbox mới phải unchecked");

        checkbox.setChecked(true);
        assertTrue(checkbox.isChecked());

        checkbox.setChecked(true);
        assertTrue(checkbox.isChecked(),
            "Gán lặp cùng giá trị không làm đảo trạng thái");

        checkbox.setChecked(false);
        assertFalse(checkbox.isChecked());
    }

    @ParameterizedTest(name = "{0} / Factory contract")
    @MethodSource("families")
    void factory_creates_correct_independent_products(FactoryCase c) {
        UiFactory factory = c.createFactory().get();

        Button firstButton = factory.createButton();
        Button secondButton = factory.createButton();
        Checkbox firstCheckbox = factory.createCheckbox();
        Checkbox secondCheckbox = factory.createCheckbox();

        assertAll(
            () -> assertNotNull(firstButton),
            () -> assertNotNull(secondButton),
            () -> assertNotNull(firstCheckbox),
            () -> assertNotNull(secondCheckbox)
        );

        assertNotSame(firstButton, secondButton);
        assertNotSame(firstCheckbox, secondCheckbox);

        assertEquals(c.expectedTheme(), firstButton.theme());
        assertEquals(c.expectedTheme(), secondButton.theme());
        assertEquals(c.expectedTheme(), firstCheckbox.theme());
        assertEquals(c.expectedTheme(), secondCheckbox.theme());

        firstCheckbox.setChecked(true);
        assertFalse(secondCheckbox.isChecked(),
            "Hai Checkbox được tạo riêng không chia sẻ state");
    }
}
~~~

Khi cấu hình đúng, JUnit thực hiện **3 phương thức tham số hóa × 2 họ = 6 lượt chạy**. Từng lượt có assertion độc lập; nếu một họ bị lỗi, tên hiển thị chỉ rõ họ đó và contract bị vi phạm.

Lưu ý: `AtomicInteger` trong ví dụ dùng làm bộ đếm callback dễ quan sát, **không có nghĩa** interface `Button` bắt buộc thread-safe. Contract đang quy định callback chạy đồng bộ trong lời gọi `click()`.

### 6.2. Vì sao tách Button, Checkbox và Factory contract?

- `every_button_obeys_interface_contract` đo hành vi riêng của **abstract product Button** trên mọi họ.
- `every_checkbox_obeys_interface_contract` đo hành vi riêng của **abstract product Checkbox** trên mọi họ.
- `factory_creates_correct_independent_products` đo cam kết của **abstract factory**: đủ loại, đúng họ, mỗi lần tạo độc lập.

Các phương thức test dùng API của interface. Nếu thêm `DarkButton` từ thư viện khác với implementation mới, test vẫn áp dụng. Nếu factory trả sai loại, lỗi sẽ xuất hiện ngay tại thao tác nhận/sử dụng sản phẩm qua kiểu interface hoặc ở invariant về họ.

**Không chỉ kiểm tra `instanceof Button`.** Một `DarkButton` có thể đúng interface về mặt kiểu nhưng `click()` gọi handler hai lần hoặc bỏ qua trạng thái disabled. Chỉ kiểm tra kiểu sẽ bỏ sót vi phạm hành vi này.

## 7. Kiểm tra sự cộng tác mà product contract chưa bao phủ

Một họ chỉ thật sự hữu ích khi các sản phẩm của nó cộng tác trong client. Thêm một `SettingsPanel` sử dụng đúng hai interface mà không hề biết Light hay Dark:

~~~java
final class SettingsPanel {
    private final Button toggleButton;
    private final Checkbox notifications;

    SettingsPanel(UiFactory factory) {
        toggleButton = factory.createButton();
        notifications = factory.createCheckbox();

        toggleButton.onClick(() ->
            notifications.setChecked(!notifications.isChecked())
        );
    }

    void toggleNotifications() {
        toggleButton.click();
    }

    boolean notificationsEnabled() {
        return notifications.isChecked();
    }

    Theme buttonTheme() {
        return toggleButton.theme();
    }

    Theme checkboxTheme() {
        return notifications.theme();
    }
}
~~~

Và chạy một test tích hợp cho **mọi** factory trong `families()`:

~~~java
@ParameterizedTest(name = "{0} / Product collaboration")
@MethodSource("families")
void products_in_family_collaborate(FactoryCase c) {
    SettingsPanel panel = new SettingsPanel(c.createFactory().get());

    assertEquals(c.expectedTheme(), panel.buttonTheme());
    assertEquals(c.expectedTheme(), panel.checkboxTheme());

    assertFalse(panel.notificationsEnabled());

    panel.toggleNotifications();
    assertTrue(panel.notificationsEnabled());

    panel.toggleNotifications();
    assertFalse(panel.notificationsEnabled());
}
~~~

Đặt phương thức test này trong `UiFactoryContractTest`. Sau khi thêm, tổng số lượt chạy tham số hóa trong ví dụ tăng thành **4 × 2 = 8**.

Test cộng tác bắt lỗi ở ranh giới product: handler của Button phải tác động được lên Checkbox, state phải nhất quán trong toàn bộ màn hình và không được trộn theme. Tuy nhiên, một bài test kiểu này không thay thế kiểm thử giao diện thực hoặc screenshot regression nếu đặc tả có yêu cầu màu sắc và rendering chính xác.

## 8. Ma trận truy vết contract cho từng họ

Một bộ contract test không tự bảo đảm **đã đăng ký tất cả concrete factory**. Nguồn `families()` cần được duy trì cùng danh sách các họ được hỗ trợ trong ứng dụng, ví dụ qua một registry đã kiểm tra hoặc kiểm soát trong review.

| Mã | Hợp đồng / invariant | Light | Dark | Test |
| --- | --- | :---: | :---: | --- |
| CT-B01 | Button mới enabled | ✓ | ✓ | `every_button_obeys_interface_contract` |
| CT-B02 | Click enabled gọi handler đúng một lần | ✓ | ✓ | `every_button_obeys_interface_contract` |
| CT-B03 | Click disabled không chạy handler | ✓ | ✓ | `every_button_obeys_interface_contract` |
| CT-B04 | Thay handler, bật lại vẫn đúng | ✓ | ✓ | `every_button_obeys_interface_contract` |
| CT-C01 | Checkbox mới unchecked | ✓ | ✓ | `every_checkbox_obeys_interface_contract` |
| CT-C02 | Set/get checked ổn định, kể cả gán lặp | ✓ | ✓ | `every_checkbox_obeys_interface_contract` |
| CT-F01 | Factory trả đúng theme của cả hai loại | ✓ | ✓ | `factory_creates_correct_independent_products` |
| CT-F02 | Mỗi lần tạo instance độc lập | ✓ | ✓ | `factory_creates_correct_independent_products` |
| CT-I01 | Button cộng tác với Checkbox trong client | ✓ | ✓ | `products_in_family_collaborate` |

Dấu ✓ ở đây thể hiện **ca cần được chạy**, không phải kết quả test đã chạy thành công. Lưu PASS/FAIL thực tế từ JUnit XML hoặc CI bên cạnh ma trận nếu cần bằng chứng kiểm thử.

Thống kê theo **ô contract × họ** giúp thấy lỗ hổng bao phủ tốt hơn việc chỉ đếm số phương thức test: một phương thức tham số hóa có thể xác minh nhiều ô và chạy nhiều lần.

## 9. Làm sao biết bộ contract test thực sự bắt được lỗi?

Hãy cố ý tạo các phiên bản implementation sai trong môi trường thử nghiệm, sau đó dự đoán assertion nào thất bại.

| Lỗi cài vào sản phẩm/factory | Assertion dự kiến phát hiện |
| --- | --- |
| `DarkButton.click()` gọi handler hai lần | CT-B02: `assertEquals(1, firstHandlerCalls.get())` |
| `LightButton.click()` vẫn chạy khi disabled | CT-B03: bộ đếm tăng không đúng |
| `DarkButton.onClick()` cộng dồn handler cũ | CT-B04: bộ đếm handler cũ tăng sau khi thay |
| `LightCheckbox.setChecked(true)` tự đảo state mỗi lần gọi | CT-C02: gán lặp `true` thất bại |
| `LightUiFactory.createCheckbox()` trả `DarkCheckbox` | CT-F01 hoặc assertion theme ở Checkbox |
| `DarkUiFactory.createButton()` trả cùng instance dùng chung | CT-F02: `assertNotSame(...)` |
| Client tạo Checkbox từ factory khác | CT-I01: theme trong màn hình không nhất quán |

Một số lỗi có thể không bị bắt nếu hợp đồng chưa đề cập tới chúng. Ví dụ, `Button.onClick(null)` nên ném exception hay bỏ đăng ký handler? Đây là **quyết định hợp đồng**; nếu ứng dụng đòi `NullPointerException` thì thêm một test cụ thể với `assertThrows`. Không áp đặt hành vi chưa được quy định lên mọi họ.

Có thể dùng mutation testing để đo khả năng bộ test nhận ra các thay đổi sai hành vi. Tuy nhiên, điểm mutation cao không chứng minh mọi quy tắc nghiệp vụ đều đã được mô tả trong contract.

## 10. Mở rộng bộ contract test đúng cách

### 10.1. Thêm một họ sản phẩm mới

Khi thêm `HighContrastUiFactory`:

1. Hiện thực đủ `Button`, `Checkbox` theo hợp đồng chung.
2. Bổ sung `HIGH_CONTRAST` vào tập theme mong đợi (nếu mô hình có enum này).
3. Thêm một `FactoryCase` vào `families()`; cung cấp expected theme theo đặc tả.
4. Chạy toàn bộ suite. Mọi contract test hiện có sẽ tự chạy cho họ mới.
5. Thêm test cho yêu cầu **riêng** của High Contrast, ví dụ độ tương phản nếu quy định; không nhét tiêu chí riêng vào contract chung của Button.

### 10.2. Thêm một loại sản phẩm mới

Khi thêm `Dialog` vào `UiFactory`:

- Xác định hợp đồng của `Dialog`, chẳng hạn `open()` làm `isOpen()` thành `true` và `close()` đưa về `false` nếu API quy định như vậy.
- Viết **một phương thức test contract mới** `every_dialog_obeys_interface_contract` dùng cùng nguồn `families()`.
- Mở rộng factory invariant để xác nhận mọi họ đều tạo `Dialog` đúng họ.
- Mở rộng test client nếu luồng cộng tác có sử dụng Dialog.

Không tạo bản sao `LightDialogTest` và `DarkDialogTest` nếu các assertion chỉ khác factory khởi tạo.

### 10.3. Khi những họ có thêm năng lực riêng

Có thể sản phẩm Cloud có thao tác async, còn sản phẩm Local không có. Nếu `AsyncButton` là năng lực **tùy chọn** chứ không thuộc `Button` chung, không nên ép mọi `Button` phải hỗ trợ. Tách contract bổ sung cho interface có năng lực đó và đăng ký **đúng những factory hỗ trợ**. Nếu thao tác là bắt buộc theo `Button`, mọi họ phải thực hiện hoặc sửa thiết kế interface cho đúng.

### 10.4. Giới hạn của nguồn dữ liệu viết thủ công

Nguồn `families()` viết tay có thể quên family mới. Để tránh test xanh giả do **bỏ sót implementation**, có thể:

- Dùng danh sách factory từ registry chính thức của ứng dụng khi registry chính là nguồn sự thật.
- Viết một assertion so sánh tập họ đăng ký cho test với tập họ được hỗ trợ từ cấu hình/registry độc lập.
- Thêm checklist review: mỗi concrete factory mới phải xuất hiện trong bộ contract test.
- Hiển thị tên họ trong report CI để dễ nhận thấy họ bị bỏ sót.

Đừng quét classpath tùy ý và mặc định mọi lớp có hậu tố `Factory` đều là production factory hợp lệ; cách tìm kiếm cần phù hợp cách ứng dụng đăng ký implementation.

## 11. Phân biệt contract test với những lớp kiểm thử khác

| Loại kiểm thử | Phát hiện loại lỗi nào? | Dùng factory/sản phẩm nào? |
| --- | --- | --- |
| **Product contract test** | Concrete product vi phạm hành vi chung của interface | Product thật của từng họ |
| **Factory invariant test** | Factory thiếu loại, sai họ hoặc trả instance trái contract | Concrete factory thật |
| **Client integration test** | Sản phẩm kết hợp sai trong một luồng sử dụng | Client thật + factory thật hoặc fixture tương đương |
| **Visual/UI test** | Màu, căn chỉnh, accessibility/interaction trên UI thật | UI framework/rendering |
| **Resource lifecycle test** | Rò rỉ handle, đóng sai thứ tự, giữ state qua các lần dùng | Factory/product thật và tài nguyên/fake có đếm close |
| **Unit test với mock product** | Client gọi đúng phương thức trên dependency đã mock | Mock/stub theo kịch bản |

**Mock product không thể thay thế hoàn toàn product contract test.** Một mock luôn trả giá trị đúng theo cấu hình của test, nên nó không xác minh concrete `DarkCheckbox` có thật sự lưu trạng thái hay `DarkButton` có bỏ qua click khi disabled.

Ngược lại, product contract test **không cần** dựng toàn bộ màn hình, kết nối network, hoặc chạy visual snapshot trong từng lượt. Giữ suite ổn định và nhanh, rồi đặt những kiểm chứng tốn kém hơn ở lớp tích hợp phù hợp.

## 12. Những lỗi thường gặp khi viết bộ test chung

**Lỗi 1 – Viết expected dựa trên actual.**

~~~java
// Sai: khẳng định một sản phẩm bằng chính giá trị nó khai báo.
assertEquals(button.theme(), button.theme());

// Đúng: so với kỳ vọng độc lập gắn với case.
assertEquals(c.expectedTheme(), button.theme());
~~~

Kể cả `assertEquals(factory.theme(), button.theme())` cũng có thể bỏ sót lỗi nếu factory và product cùng khai báo sai theme. Trường hợp này chỉ đạt một bất biến tương đối; muốn kiểm tra đúng họ đích phải có oracle độc lập.

**Lỗi 2 – Chỉ kiểm tra constructor không ném lỗi.**

~~~java
// Chưa đủ để khẳng định tuân theo interface.
assertNotNull(factory.createButton());
~~~

Button không null vẫn có thể bỏ qua `setEnabled(false)` hoặc gửi nhiều callback. Contract test phải thực thi các hậu điều kiện quan sát được.

**Lỗi 3 – Dùng trực tiếp lớp cụ thể trong test dùng chung.**

~~~java
// Làm test bị gắn cứng với một họ:
LightButton button = new LightButton();

// Đúng hướng cho một bộ test nhiều họ:
Button button = c.createFactory().get().createButton();
~~~

Nếu cần test riêng cho phần rendering của `LightButton`, hãy đặt nó ở một test khác, có mục tiêu rõ ràng.

**Lỗi 4 – Dùng chung đối tượng có state giữa các lượt test.**

Nếu `families()` giữ một singleton factory có state, hoặc các test cùng chia sẻ Button và Checkbox, kết quả phụ thuộc vào thứ tự chạy. Dùng supplier tạo fixture độc lập, reset tài nguyên và tránh làm thay đổi state toàn cục.

**Lỗi 5 – Bắt các họ có đặc tính khác nhau hoạt động giống nhau ở phần không thuộc interface.**

Hợp đồng chung nên kiểm tra hành vi client được phép trông đợi. Kiểm thử hiệu ứng riêng của Dark hoặc Light phải tách ra để không phá ý nghĩa thay thế được của các abstract product.

**Lỗi 6 – Bỏ sót họ mới dù toàn bộ test hiện có đều xanh.**

Tham số hóa giảm việc nhân bản logic, nhưng vẫn cần giám sát danh sách implementation được test. Tập họ chính thức là một phần quan trọng của độ bao phủ.

## 13. Bài tập thực hành

Ứng dụng đa nền tảng có ba họ sản phẩm: `DesktopFactory`, `MobileFactory` và `WebFactory`. Mỗi họ tạo `Button` và `TextInput`. Các hợp đồng giả định:

- `Button.setEnabled(false)` khiến `click()` không gọi callback.
- `TextInput.setText(value)` phải làm `getText()` trả về đúng `value`, kể cả chuỗi rỗng.
- Factory trả về một instance độc lập mỗi lần tạo sản phẩm.
- Client `LoginForm` dùng Button để gửi nội dung TextInput.

Hãy:

1. Viết `FactoryCase` cho cả ba họ và một bộ test `@ParameterizedTest` dùng chung cho Button.
2. Viết một bộ contract test cho TextInput với ít nhất ba giá trị: chuỗi rỗng, Unicode và chuỗi dài.
3. Thêm kiểm tra factory trả về đúng family cho cả hai product, sử dụng oracle mong đợi độc lập.
4. Viết một integration test xác nhận `LoginForm` đọc đúng giá trị TextInput khi Button enabled và không submit khi Button disabled.
5. Cố ý làm `MobileButton` bỏ qua `setEnabled(false)` và chỉ ra assertion nào cần thất bại.

**Định hướng đáp án:** Với ba factory và ba nhóm test (Button, TextInput, factory invariant), có **9 lượt chạy tham số hóa**; thêm integration test cho ba họ sẽ là **12 lượt chạy**. Mọi phương thức test dùng interface chung và chỉ khác dữ liệu factory đầu vào. Test TextInput không cần phân biệt kiểu render của Desktop/Mobile/Web trừ khi đặc tả yêu cầu.

## 14. Checklist áp dụng vào dự án

- [ ] Mỗi product interface có mô tả rõ trạng thái đầu, thao tác, hậu điều kiện và trường hợp biên.
- [ ] Một bộ contract test riêng cho từng interface mà client thực sự phụ thuộc.
- [ ] Mọi concrete family được đăng ký trong nguồn dữ liệu test, có kỳ vọng độc lập.
- [ ] Fixture tạo được product thật và độc lập giữa các lần chạy.
- [ ] Contract test xác minh **hành vi**, không chỉ kiểu dữ liệu hay `null`.
- [ ] Test factory kiểm tra đúng họ, đủ loại và điều kiện tạo instance theo hợp đồng.
- [ ] Có ít nhất một test tích hợp cho tình huống cộng tác quan trọng của client.
- [ ] Trường hợp không thuộc hợp đồng chung được thử trong bộ test riêng thích hợp.
- [ ] Khi thêm family hoặc product type, cập nhật nguồn dữ liệu và ma trận bao phủ.
- [ ] Báo cáo test hiển thị rõ **family × contract**, giúp xác định implementation bị lỗi.

## 15. Ghi nhớ

Abstract Factory giúp client sử dụng **các interface sản phẩm ổn định** trong khi thay đổi cả họ triển khai. Bộ **contract test chung** kiểm chứng lời hứa đó bằng một tập assertion hành vi duy nhất, chạy cho tất cả concrete factory qua dữ liệu tham số hóa. Kết hợp **product contract**, **factory invariant** và **client integration** sẽ phát hiện cả sản phẩm sai hành vi lẫn factory ghép sai họ, đồng thời giảm công sức kiểm thử mỗi khi bổ sung một họ sản phẩm mới.
