# Lập ma trận kiểm thử theo họ sản phẩm, loại sản phẩm và tình huống cộng tác

## 1. Vì sao Abstract Factory cần ma trận kiểm thử?

Trong **Abstract Factory**, client yêu cầu một factory tạo ra **cả họ sản phẩm có thể làm việc cùng nhau**. Chẳng hạn, giao diện sáng (Light) và tối (Dark) đều cung cấp `Button`, `Checkbox` và `Dialog`. Mỗi sản phẩm có thể hoạt động đúng khi đứng riêng lẻ, nhưng ứng dụng vẫn sai nếu một màn hình Light vô tình sử dụng `DarkCheckbox`.

Vì vậy, bài kiểm thử không chỉ trả lời “factory có tạo được đối tượng không?”, mà còn phải trả lời:

1. **Đúng họ:** Sản phẩm từ factory Light thuộc Light; sản phẩm từ factory Dark thuộc Dark.
2. **Đúng loại:** Lời gọi tạo `Button`, `Checkbox`, `Dialog` trả về sản phẩm đúng hợp đồng và có hành vi mong đợi.
3. **Cộng tác đúng:** Những sản phẩm cùng xuất hiện trong một luồng sử dụng phải tương thích, không bị trộn họ và tạo ra kết quả đúng.
4. **Đổi họ an toàn:** Khi ứng dụng đổi factory, các thành phần phụ thuộc được tạo lại nhất quán.

**Mục tiêu học tập:** Tự xác định ba trục của ma trận, lập các ca kiểm thử có thể truy vết, triển khai kiểm thử tham số hóa và phát hiện những lỗi mà việc chỉ kiểm tra từng sản phẩm không bắt được.

## 2. Xác định đối tượng và bất biến trước khi lập ma trận

Giả sử ứng dụng quản lý tùy chọn hiển thị có hai họ giao diện. `SettingsView` dùng nút **Save**, ô chọn **Enable notifications** và hộp thoại **Saved**. Client nhận một `UiFactory` thông qua constructor, không tự khởi tạo từng sản phẩm cụ thể.

~~~mermaid
flowchart TD
    A["SettingsView (client)"] --> F["UiFactory"]
    F --> L["LightUiFactory"]
    F --> D["DarkUiFactory"]
    L --> LB["LightButton"]
    L --> LC["LightCheckbox"]
    L --> LD["LightDialog"]
    D --> DB["DarkButton"]
    D --> DC["DarkCheckbox"]
    D --> DD["DarkDialog"]
~~~

| Vai trò | Khái niệm trong ví dụ | Trách nhiệm cần kiểm thử |
| --- | --- | --- |
| Abstract Factory | `UiFactory` | Công khai thao tác tạo từng loại sản phẩm |
| Concrete Factory | `LightUiFactory`, `DarkUiFactory` | Trả về đủ sản phẩm thuộc họ của mình |
| Abstract Product | `Button`, `Checkbox`, `Dialog` | Giữ hợp đồng hành vi mà client sử dụng |
| Concrete Product | `LightButton`, `DarkButton`, … | Hiện thực hành vi và thuộc tính riêng của từng họ |
| Client | `SettingsView` | Chỉ phụ thuộc interface, phối hợp các sản phẩm cùng factory |

Một **bất biến** là điều kiện phải luôn đúng trong phạm vi được kiểm thử. Với ví dụ này, tập bất biến tối thiểu là:

- **I1 – Đồng nhất họ:** Với họ mong đợi `F`, mọi sản phẩm được factory tương ứng tạo ra đều báo họ `F`.
- **I2 – Đầy đủ loại:** Mỗi factory cung cấp đủ ba loại; không có sản phẩm `null`, sai interface hoặc không đáp ứng hợp đồng.
- **I3 – Đồng nhất trong cộng tác:** Toàn bộ sản phẩm mà `SettingsView` sử dụng trong cùng một lần dựng đều thuộc một họ.
- **I4 – Đúng hành vi:** Chọn thông báo và nhấn Save khiến ô chọn được bật và hộp thoại xác nhận mở ra.
- **I5 – Không giữ sản phẩm cũ sau đổi họ:** Khi chuyển Light → Dark hoặc Dark → Light, client dựng lại toàn bộ bộ sản phẩm, không giữ thành phần của giao diện trước đó.

Ở hệ thống thực, thuộc tính nhận diện họ có thể là theme token, driver type, vendor identifier hoặc cấu hình giao thức. Không nhất thiết phải có phương thức `family()` trong production; đây chỉ là một cách làm rõ tiêu chí của ví dụ.

## 3. Chọn ba trục kiểm thử

### Trục A – Họ sản phẩm (family)

- **Light:** `LightUiFactory`, kết quả mong đợi `Theme.LIGHT`.
- **Dark:** `DarkUiFactory`, kết quả mong đợi `Theme.DARK`.

Giá trị mong đợi phải lấy từ **đặc tả độc lập** của ca kiểm thử. Đừng viết `assertEquals(factory.family(), product.family())` làm kiểm chứng duy nhất: nếu cả factory lẫn sản phẩm cùng khai báo sai là Dark, phép so sánh đó vẫn có thể thành công.

### Trục B – Loại sản phẩm (product type)

- **Button:** Đăng ký và kích hoạt hành động click.
- **Checkbox:** Thay đổi và đọc trạng thái chọn.
- **Dialog:** Mở và đọc trạng thái hiển thị.

Mỗi loại có một hành vi cốt lõi riêng. Các ca kiểm thử cùng dùng tiêu chí “khác `null`” sẽ không đủ để phát hiện lỗi hành vi.

### Trục C – Tình huống cộng tác (scenario)

| Mã | Tình huống | Đối tượng và kết quả quan sát |
| --- | --- | --- |
| **S0** | Tạo và kiểm tra hợp đồng độc lập | Factory tạo đúng loại, đúng họ; hành vi riêng của sản phẩm chạy được |
| **S1** | Dựng màn hình với cả ba loại | `SettingsView` chứa Button, Checkbox, Dialog cùng họ |
| **S2** | Luồng “Enable notifications → Save → Saved” | Checkbox được bật, click kích hoạt đúng handler, Dialog mở; toàn bộ luồng dùng cùng họ |
| **S3** | Chuyển họ khi ứng dụng đang hoạt động | Màn hình được dựng lại với toàn bộ sản phẩm của họ đích, không giữ sản phẩm cũ |

**S0, S1, S2** có thể quan sát trên từng loại sản phẩm; **S3** là luồng ở cấp màn hình. Không ép S3 thành ba bài kiểm thử giống nhau chỉ để lấp một phép nhân Descartes.

## 4. Lập ma trận kiểm thử có tiêu chí chấp nhận

### 4.1. Ma trận bao phủ

Ký hiệu **✓** nghĩa là phải có assertion tương ứng; **—** nghĩa là kiểm tra ở cấp màn hình thay vì từng loại.

| Họ sản phẩm | Loại sản phẩm | S0: Hợp đồng | S1: Cùng họ trong màn hình | S2: Luồng Save | S3: Chuyển họ |
| --- | --- | :---: | :---: | :---: | :---: |
| Light | Button | ✓ | ✓ | ✓ | — |
| Light | Checkbox | ✓ | ✓ | ✓ | — |
| Light | Dialog | ✓ | ✓ | ✓ | — |
| Dark | Button | ✓ | ✓ | ✓ | — |
| Dark | Checkbox | ✓ | ✓ | ✓ | — |
| Dark | Dialog | ✓ | ✓ | ✓ | — |
| **Light → Dark** | **Toàn màn hình** | — | — | — | ✓ |
| **Dark → Light** | **Toàn màn hình** | — | — | — | ✓ |

Ma trận có **18 điểm kiểm tra ở giao ba trục** (`2 họ × 3 loại × 3 tình huống S0–S2`) và **2 điểm chuyển họ**. Đây là **20 điểm bao phủ logic**, không bắt buộc phải là 20 phương thức test: một ca tích hợp S2 có thể đồng thời kiểm tra ba sản phẩm.

### 4.2. Mô tả ca kiểm thử đủ để thực thi

| ID mẫu | Điều kiện đầu vào | Hành động | Kết quả mong đợi |
| --- | --- | --- | --- |
| `AF-L-B-S0` | Factory Light | Tạo Button, gắn handler rồi click | Button thuộc Light, handler chạy đúng một lần |
| `AF-L-C-S0` | Factory Light | Tạo Checkbox, đặt `true` rồi `false` | Thuộc Light, trạng thái phản ánh đúng mỗi lần gán |
| `AF-L-D-S0` | Factory Light | Tạo Dialog rồi mở | Thuộc Light, trạng thái mở bằng `true` |
| `AF-D-B-S0` | Factory Dark | Làm như `AF-L-B-S0` | Thuộc Dark và handler chạy đúng một lần |
| `AF-D-C-S0` | Factory Dark | Làm như `AF-L-C-S0` | Thuộc Dark và trạng thái đúng |
| `AF-D-D-S0` | Factory Dark | Làm như `AF-L-D-S0` | Thuộc Dark và Dialog mở được |
| `AF-L-ALL-S1/S2` | Dựng `SettingsView` bằng Light | Kiểm tra họ, bật notifications và Save | Ba sản phẩm đều Light; checkbox bật; dialog mở |
| `AF-D-ALL-S1/S2` | Dựng `SettingsView` bằng Dark | Làm như dòng trên | Ba sản phẩm đều Dark; luồng Save thành công |
| `AF-L-D-S3` | Màn hình đang ở Light | Chọn Dark | Mọi sản phẩm mới đều Dark và không cùng reference với sản phẩm cũ |
| `AF-D-L-S3` | Màn hình đang ở Dark | Chọn Light | Mọi sản phẩm mới đều Light và không cùng reference với sản phẩm cũ |

Một test có tên rõ ràng, đầu vào và kết quả mong đợi cụ thể sẽ giúp tìm lỗi nhanh hơn một tập test chỉ mang tên `testFactory1`, `testFactory2`.

## 5. Ví dụ Java: hợp đồng đủ để viết test

Mã dưới đây mô tả API của ứng dụng giả định. Hai implementation `LightUiFactory` và `DarkUiFactory` cùng các sản phẩm cụ thể do ứng dụng cung cấp; khi áp dụng trong dự án, thay các tên này bằng implementation thật.

~~~java
enum Theme {
    LIGHT, DARK
}

interface UiProduct {
    Theme family();
}

interface Button extends UiProduct {
    void onClick(Runnable handler);
    void click();
}

interface Checkbox extends UiProduct {
    void setChecked(boolean checked);
    boolean isChecked();
}

interface Dialog extends UiProduct {
    void open();
    boolean isOpen();
}

interface UiFactory {
    Button createButton();
    Checkbox createCheckbox();
    Dialog createDialog();
}
~~~

Client sử dụng **một factory duy nhất** cho mỗi lần dựng màn hình. Mã đơn giản hóa dưới đây phơi bày các trạng thái cần quan sát; ứng dụng thực có thể dùng UI toolkit và các callback khác.

~~~java
import java.util.List;

final class SettingsView {
    private final Button saveButton;
    private final Checkbox notifications;
    private final Dialog confirmation;

    SettingsView(UiFactory factory) {
        saveButton = factory.createButton();
        notifications = factory.createCheckbox();
        confirmation = factory.createDialog();
        saveButton.onClick(confirmation::open);
    }

    void enableNotificationsAndSave() {
        notifications.setChecked(true);
        saveButton.click();
    }

    boolean notificationsEnabled() {
        return notifications.isChecked();
    }

    boolean confirmationVisible() {
        return confirmation.isOpen();
    }

    List<UiProduct> products() {
        return List.of(saveButton, notifications, confirmation);
    }
}

final class SettingsHost {
    private SettingsView current;

    SettingsHost(UiFactory initialFactory) {
        useFactory(initialFactory);
    }

    void useFactory(UiFactory factory) {
        current = new SettingsView(factory);
    }

    SettingsView current() {
        return current;
    }
}
~~~

**Điểm thiết kế quyết định khả năng kiểm thử:** `SettingsHost.useFactory()` dựng lại `SettingsView` bằng factory mới. Nếu ứng dụng chỉ thay Button khi đổi theme nhưng giữ Checkbox và Dialog cũ, bất biến I5 sẽ bị phá vỡ dù từng sản phẩm riêng lẻ đều tốt.

## 6. Thực thi kiểm thử bằng JUnit 5

Các ví dụ sử dụng **Java 17+** (có `record` và `switch` expression), **JUnit Jupiter 5** cùng `junit-jupiter-params`. Để chạy trong dự án, cần cung cấp các concrete factory và concrete product tương ứng với hợp đồng đã mô tả.

### 6.1. Sinh tổ hợp họ × loại bằng dữ liệu

`@ParameterizedTest` giúp giữ cùng một logic kiểm tra trong khi chạy với từng họ và từng loại sản phẩm. Dữ liệu `expected` được ghi cứng trong fixture để làm oracle độc lập với factory.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class AbstractFactoryMatrixTest {
    record FamilyCase(String name, Theme expected, Supplier<UiFactory> make) {
        @Override
        public String toString() {
            return name;
        }
    }

    enum ProductType {
        BUTTON, CHECKBOX, DIALOG
    }

    static Stream<FamilyCase> families() {
        return Stream.of(
            new FamilyCase("Light", Theme.LIGHT, LightUiFactory::new),
            new FamilyCase("Dark", Theme.DARK, DarkUiFactory::new)
        );
    }

    static Stream<Arguments> productCases() {
        return families().flatMap(f ->
            Stream.of(ProductType.values())
                  .map(type -> Arguments.of(f, type))
        );
    }

    static UiProduct create(UiFactory factory, ProductType type) {
        return switch (type) {
            case BUTTON -> factory.createButton();
            case CHECKBOX -> factory.createCheckbox();
            case DIALOG -> factory.createDialog();
        };
    }

    @ParameterizedTest(name = "{0} / {1} / S0")
    @MethodSource("productCases")
    void product_has_expected_family_and_behavior(
            FamilyCase family, ProductType type) {

        UiProduct product = create(family.make().get(), type);

        assertNotNull(product);
        assertEquals(family.expected(), product.family());

        switch (type) {
            case BUTTON -> {
                Button button = (Button) product;
                AtomicInteger clicks = new AtomicInteger();
                button.onClick(clicks::incrementAndGet);
                button.click();
                assertEquals(1, clicks.get());
            }
            case CHECKBOX -> {
                Checkbox checkbox = (Checkbox) product;
                checkbox.setChecked(true);
                assertTrue(checkbox.isChecked());
                checkbox.setChecked(false);
                assertFalse(checkbox.isChecked());
            }
            case DIALOG -> {
                Dialog dialog = (Dialog) product;
                dialog.open();
                assertTrue(dialog.isOpen());
            }
        }
    }

    @ParameterizedTest(name = "{0} / S1 + S2")
    @MethodSource("families")
    void products_collaborate_in_one_family(FamilyCase family) {
        SettingsView view = new SettingsView(family.make().get());

        // S1: mọi sản phẩm của client đều thuộc họ được chọn.
        assertEquals(3, view.products().size());
        for (UiProduct product : view.products()) {
            assertNotNull(product);
            assertEquals(family.expected(), product.family());
        }

        // S2: kiểm tra kết quả của luồng cộng tác, không chỉ khởi tạo.
        view.enableNotificationsAndSave();
        assertTrue(view.notificationsEnabled());
        assertTrue(view.confirmationVisible());
    }
}
~~~

Chạy bộ test tham số hóa này tạo **6 lần chạy S0** và **2 lần chạy tích hợp S1 + S2**. Các assertion trong mỗi lần chạy tích hợp bao phủ ba loại sản phẩm, nên số lần chạy có thể nhỏ hơn số ô được đánh dấu trong ma trận.

Nếu ứng dụng dùng sự kiện bất đồng bộ, thay cách quan sát đồng bộ bằng callback, fake clock hoặc cơ chế chờ được UI framework cung cấp; không dựa vào `Thread.sleep()` tùy ý.

### 6.2. Kiểm tra thay đổi họ ở cấp client

Khi chuyển theme, cần so sánh cả **họ mong đợi** và **danh tính của các đối tượng mới**. Ví dụ mở rộng cùng class test ở trên:

~~~java
record SwitchCase(
    String name,
    Supplier<UiFactory> from,
    Supplier<UiFactory> to,
    Theme expectedTarget
) {
    @Override
    public String toString() {
        return name;
    }
}

static Stream<SwitchCase> switches() {
    return Stream.of(
        new SwitchCase(
            "Light -> Dark",
            LightUiFactory::new,
            DarkUiFactory::new,
            Theme.DARK
        ),
        new SwitchCase(
            "Dark -> Light",
            DarkUiFactory::new,
            LightUiFactory::new,
            Theme.LIGHT
        )
    );
}

@ParameterizedTest(name = "{0} / S3")
@MethodSource("switches")
void switching_recreates_the_complete_family(SwitchCase c) {
    SettingsHost host = new SettingsHost(c.from().get());
    SettingsView oldView = host.current();
    var oldProducts = oldView.products();

    host.useFactory(c.to().get());

    SettingsView newView = host.current();
    var newProducts = newView.products();
    assertNotSame(oldView, newView);
    assertEquals(oldProducts.size(), newProducts.size());

    for (int i = 0; i < newProducts.size(); i++) {
        assertNotSame(oldProducts.get(i), newProducts.get(i));
        assertEquals(c.expectedTarget(), newProducts.get(i).family());
    }

    newView.enableNotificationsAndSave();
    assertTrue(newView.notificationsEnabled());
    assertTrue(newView.confirmationVisible());
}
~~~

Để biên dịch, đặt `SwitchCase`, `switches()` và phương thức test vào **cùng class** `AbstractFactoryMatrixTest` của ví dụ trước. Đoạn trên được tách riêng nhằm nhấn mạnh kiểm thử vòng đời thay đổi factory.

## 7. Ca âm và lỗi chủ động cần phát hiện

Kiểm thử “đường đi thành công” chưa đủ. Dùng các biến thể sai có chủ đích sau để kiểm tra độ nhạy của bộ test:

| Sai sót đưa vào implementation | Ca cần thất bại | Vì sao |
| --- | --- | --- |
| `LightUiFactory.createCheckbox()` trả về `DarkCheckbox` | `AF-L-C-S0`, Light S1/S2 | Sai họ ngay từ factory; client sẽ trộn theme |
| `DarkUiFactory.createDialog()` trả về `null` | `AF-D-D-S0`, Dark S1/S2 | Thiếu loại sản phẩm; màn hình không thể cộng tác đầy đủ |
| Handler của `Button.click()` không được gọi | Ca Button S0, S2 | Sản phẩm vẫn tạo được nhưng luồng Save bị đứt |
| `Dialog.open()` không cập nhật trạng thái mở | Ca Dialog S0, S2 | Luồng thao tác hoàn tất nhưng người dùng không thấy xác nhận |
| `SettingsHost` giữ lại `Checkbox` của họ cũ | S3 cả chiều đổi phù hợp | Danh tính/họ sau đổi không nhất quán |
| Test tính họ bằng `factory.family()` thay vì oracle độc lập | Có thể **không phát hiện lỗi** | Factory và sản phẩm cùng báo nhầm một họ vẫn khiến test xanh |

**Ca âm thực sự** ở phía client có thể đưa vào một factory cố ý trộn Light/Dark và xác nhận việc kiểm tra invariant từ chối màn hình đó. Với kiến trúc hiện tại, `SettingsView` chưa tự chặn factory sai; test hiện có sẽ phát hiện bằng assertion. Nếu hệ thống yêu cầu từ chối cấu hình sai ngay khi chạy, bổ sung validation trong client hoặc tầng cấu hình rồi viết ca test `assertThrows(...)` cho validation ấy. Không viết `assertThrows` khi production chưa có hợp đồng ném exception.

Có thể bổ sung các tình huống ranh giới theo đặc tả: đăng ký nhiều handler, nhấn Save liên tiếp, mở Dialog hai lần, hoặc factory không hỗ trợ loại sản phẩm mới. Chỉ xác định pass/fail khi hành vi mong đợi đã được quy định.

## 8. Tối ưu số lượng ca khi hệ thống mở rộng

Giả sử sản phẩm thực có **4 họ**, **6 loại sản phẩm** và **5 tình huống**. Nhân thẳng mọi trục tạo ra `4 × 6 × 5 = 120` tổ hợp, trong khi vài tình huống chỉ áp dụng cho client tổng thể. Nên phân lớp kiểm thử theo ý nghĩa:

1. **Contract test ở mức sản phẩm:** Chạy mọi cặp họ × loại được hỗ trợ; luôn ưu tiên bao phủ đầy đủ vì đây là cấu trúc cốt lõi của Abstract Factory.
2. **Integration test ở mức luồng:** Chạy từng tình huống cộng tác quan trọng với mỗi họ; một test có thể quan sát nhiều loại sản phẩm cùng lúc.
3. **Lifecycle test:** Kiểm tra chuyển factory, khởi tạo lại, lỗi cấu hình hoặc khôi phục trạng thái theo yêu cầu; đây là phép thử trên tổ hợp họ nguồn → họ đích.
4. **Risk-based test:** Tăng thêm trường hợp ở nơi dễ gây lỗi, như sản phẩm chia sẻ resource, cùng transaction, hoặc có trạng thái tồn tại lâu.

**Không được sử dụng pairwise một cách máy móc** để bỏ kiểm tra một cặp họ × loại quan trọng. Pairwise có ích khi nhiều chiều độc lập có miền giá trị lớn, nhưng không thay thế bất biến “mọi loại sản phẩm đều thuộc đúng họ”.

Khi thêm một sản phẩm `Slider`, hãy thêm `Slider` vào fixture `ProductType`, test hợp đồng của từng họ và luồng client có sử dụng nó. Khi thêm họ `HighContrast`, hãy thêm factory vào nguồn dữ liệu `families()` và các chiều chuyển họ liên quan. Đây là lợi thế của ma trận dữ liệu thay vì sao chép hàng loạt phương thức test.

## 9. Quy trình áp dụng vào một dự án thật

1. **Liệt kê** tất cả concrete factory, các interface sản phẩm và các client tạo hoặc phối hợp nhiều sản phẩm.
2. **Ghi đặc tả độc lập** cho từng họ/loại: kiểu, token, giao thức, hiệu ứng, yêu cầu tương thích và hành vi kết thúc.
3. **Vẽ ma trận** họ × loại × tình huống; đánh dấu rõ ô có thể kiểm chứng và ô không áp dụng. Gán ID, mức ưu tiên và kết quả mong đợi.
4. **Tạo fixture** cho từng factory. Mỗi lần chạy cần instance mới để test không rò rỉ trạng thái qua nhau.
5. **Thực thi contract test** trước; nếu factory trả sai loại hoặc sai họ thì dừng điều tra lỗi ở tầng tạo sản phẩm.
6. **Thực thi integration và lifecycle test** trên client thật. Kiểm tra kết quả quan sát được, reference/state khi đổi factory và những tình huống lỗi có chủ đích.
7. **Đối chiếu kết quả với ma trận**, cập nhật ô pass/fail/blocked và liên kết tới test tương ứng. Không coi ô không áp dụng là pass.

Có thể theo dõi kết quả ở dạng ngắn gọn:

| Test ID | Họ | Loại | Scenario | Kết quả | Bằng chứng |
| --- | --- | --- | --- | --- | --- |
| `AF-L-C-S0` | Light | Checkbox | S0 | PASS/FAIL | Assertion theme + checked state |
| `AF-D-ALL-S2` | Dark | Cả ba | S2 | PASS/FAIL | Notifications bật; dialog mở |
| `AF-L-D-S3` | Light → Dark | Cả ba | S3 | PASS/FAIL | Mọi reference mới; cùng họ Dark |

Các cột `PASS/FAIL` trên là **mẫu để ghi kết quả chạy**, không phải kết quả đã được thực thi trong bài học.

## 10. Sai lầm thường gặp

- **Chỉ test concrete factory có thể khởi tạo:** Không phát hiện thành phần sai họ hoặc client giữ sản phẩm cũ.
- **Chỉ mock interface của sản phẩm:** Test client có thể xanh dù concrete factory nối sai implementation. Cần ít nhất một lớp test dùng factory và sản phẩm thật.
- **Dùng cùng một nguồn cho expected và actual:** Dẫn tới test tự xác nhận chính điều mà mã lỗi khai báo.
- **Dựa vào tên class hoặc snapshot để kiểm tra mọi hành vi:** Tên class, CSS snapshot hay ảnh giao diện không thay thế xác nhận luồng nghiệp vụ và tương thích.
- **Đếm số hàm test thay cho độ phủ:** Một test tham số hóa có thể chạy nhiều tổ hợp; một test tích hợp có thể xác minh nhiều ô ma trận.
- **Gán mọi tình huống cho mọi sản phẩm:** Chuyển họ là hành vi của client tổng thể, nên kiểm tra tại đúng cấp độ.

## 11. Bài tập tự luyện

Một ứng dụng xuất báo cáo có hai factory: `PdfReportFactory` và `HtmlReportFactory`. Mỗi họ tạo `Header`, `Table` và `Footer`. Client `ReportComposer` dựng báo cáo và có thao tác xuất file.

Hãy xây dựng ma trận cho:

- Hai họ PDF/HTML, ba loại Header/Table/Footer.
- S0: sản phẩm đúng định dạng; S1: bố cục báo cáo dùng cùng họ; S2: xuất báo cáo thành công; S3: đổi định dạng và dựng lại báo cáo.
- Một factory sai cố ý, chẳng hạn `PdfReportFactory` trả về `HtmlFooter`.

**Gợi ý đáp án:** Có 6 cặp họ × loại cần contract test; 2 luồng compose/export; và ít nhất 2 chiều đổi định dạng nếu ứng dụng cho phép đổi hai chiều. Assertion không chỉ kiểm tra có chuỗi đầu ra: phải kiểm tra cấu trúc PDF/HTML đúng định dạng, thành phần không trộn và kết quả xuất có thể được mở bởi bộ đọc phù hợp. Với test PDF, có thể dùng parser để xác nhận cấu trúc; với HTML, kiểm tra DOM. Các phép thử nặng về định dạng nên tách khỏi kiểm thử nhỏ của factory.

## 12. Ghi nhớ

Ma trận kiểm thử Abstract Factory nên bắt đầu từ **bất biến đồng nhất họ**, sau đó mở rộng theo **loại sản phẩm** và **tình huống cộng tác thực tế**. Kiểm thử sản phẩm riêng lẻ bảo vệ hợp đồng của factory; kiểm thử tích hợp bảo vệ cách client phối hợp các sản phẩm; kiểm thử đổi họ bảo vệ toàn bộ vòng đời. Một bộ test tốt chứng minh rằng các sản phẩm của **cùng một họ** thực sự làm việc cùng nhau trong các luồng sử dụng quan trọng.
