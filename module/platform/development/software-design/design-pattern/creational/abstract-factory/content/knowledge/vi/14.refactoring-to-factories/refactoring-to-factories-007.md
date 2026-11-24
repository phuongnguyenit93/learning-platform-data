# So sánh hành vi trước và sau tái cấu trúc bằng kiểm thử hồi quy

## 1. Tại sao refactor sang Abstract Factory vẫn cần kiểm thử hồi quy?

Khi tái cấu trúc code để áp dụng **Abstract Factory**, mục tiêu thường là thay đổi **cách tạo và liên kết các đối tượng**, trong khi hành vi đã được người dùng chấp nhận vẫn giữ nguyên.

Giả sử ứng dụng có màn hình cài đặt với nút Save và ô chọn thông báo. Phiên bản ban đầu chỉ hỗ trợ giao diện Light: `SettingsPanel` tự tạo `LightButton` và `LightCheckbox`. Sau khi tái cấu trúc, client nhận `UiFactory` qua constructor để có thể chọn cả họ Light hoặc Dark.

Lợi ích kiến trúc là rõ ràng: client không còn quyết định concrete product. Nhưng việc thay đổi vị trí khởi tạo đối tượng có thể vô tình làm sai hành vi:

- Callback của nút Save không còn đọc trạng thái mới nhất của Checkbox.
- Checkbox sau refactor bị khởi tạo ở trạng thái khác trước.
- Client lấy Button từ Light nhưng Checkbox từ Dark.
- Hai lần thao tác Save tạo thêm event ngoài dự kiến.
- Màn hình render khác đi vì client dùng sai factory hoặc tạo lại sản phẩm quá sớm.
- Một lỗi mới chỉ xuất hiện trên nhánh Dark, trong khi nhánh Light vẫn chạy đúng.

**Kiểm thử hồi quy (regression testing)** so sánh kết quả của những thao tác đã có với **hợp đồng hành vi được chấp nhận**. Với bài này, ta dùng hai cách bổ trợ:

1. **Characterization test / golden baseline:** Ghi rõ kết quả mong đợi của phiên bản trước refactor để có mốc độc lập.
2. **Differential test:** Chạy **cùng một kịch bản** trên client cũ và client mới, rồi so sánh phần kết quả có ý nghĩa nghiệp vụ.

Bài học thuộc chương **Tái cấu trúc** trong module *Học về Abstract Factory trong design pattern*. Sau bài này, bạn sẽ biết cách định nghĩa tiêu chí tương đương, xây test trước khi sửa cấu trúc, đo khác biệt chính đáng và phát hiện hồi quy trong quá trình chuyển đổi.

## 2. Phải định nghĩa “hành vi giữ nguyên” trước khi so sánh

Không phải mọi chi tiết của chương trình trước và sau refactor cần giống hệt nhau. Tên class, số object được tạo hay vị trí đặt lệnh `new` có thể thay đổi đúng theo mục tiêu refactor.

Điều cần bảo toàn là **hành vi quan sát được theo hợp đồng**.

| Nhóm quan sát | Kịch bản màn hình cài đặt | Điều cần giữ khi chọn cùng họ Light |
| --- | --- | --- |
| Giá trị ban đầu | Checkbox chưa được chọn | `notifications=false` |
| Thao tác thay đổi | Bật thông báo | `notifications=true` |
| Hành động người dùng | Nhấn Save lần thứ nhất | Ghi lại đúng một giá trị `true` |
| Thao tác tiếp theo | Tắt thông báo rồi nhấn Save | Ghi tiếp đúng một giá trị `false` |
| Biểu diễn màn hình | Render Button và Checkbox | Chuỗi Light tương ứng với trạng thái hiện hành |
| Đường lỗi đã quy định | Dependency không hợp lệ | Có lỗi tường minh, theo hợp đồng mới hoặc cũ được phê duyệt |

Hành vi không nên so sánh máy móc:

| Chi tiết triển khai | Có cần giống nhau? | Lý do |
| --- | --- | --- |
| Tên biến local, tên class concrete | Không | Chúng không phải kết quả mà client bên ngoài phụ thuộc |
| Vị trí gọi constructor | Không | Chính phần này đang được tái cấu trúc |
| Object identity, địa chỉ bộ nhớ | Thường không | Có thể tạo object mới nhưng hành vi vẫn đúng |
| Timestamp, random ID, mã correlation | Chỉ khi là hợp đồng | Nếu không, chuẩn hóa trước khi so sánh |
| Thứ tự các event nghiệp vụ | Có, nếu hợp đồng quy định | Sai thứ tự có thể làm sai hiệu ứng người dùng |
| Số lần lưu dữ liệu | Có | Nhấn Save một lần mà lưu hai lần là hồi quy |
| Exception type/message | Tùy đặc tả | Tránh khóa test vào thông điệp nội bộ không ổn định |

**Nguyên tắc:** So sánh một *behavioral projection* — tức tập thông tin mà client/ người dùng thực sự quan sát hoặc phụ thuộc — thay vì so sánh toàn bộ implementation.

## 3. Chốt kịch bản chuẩn trước khi bắt đầu refactor

Thay vì chỉ thử một lần render, nên chọn một chuỗi hành động có cả khởi tạo, thay đổi trạng thái và tương tác giữa các sản phẩm.

Trong ví dụ, một lượt kiểm thử gồm:

1. Render màn hình ở trạng thái mặc định.
2. Bật thông báo và render lại.
3. Nhấn Save; xác nhận ghi nhận trạng thái `true`.
4. Tắt thông báo và nhấn Save lần hai; xác nhận ghi nhận trạng thái `false`.
5. Kiểm tra danh sách các giá trị đã lưu và không xuất hiện event dư.

Bảng trace mong đợi cho họ Light:

| Bước | Hành động | Kết quả quan sát |
| --- | --- | --- |
| 0 | Khởi tạo và render | `LightButton \| LightCheckbox \| notifications=false` |
| 1 | `setNotificationsEnabled(true)` rồi render | `LightButton \| LightCheckbox \| notifications=true` |
| 2 | `save()` rồi render | Vẫn `notifications=true`, có một event lưu `true` |
| 3 | `setNotificationsEnabled(false)`, `save()` rồi render | `notifications=false`, lịch sử lưu là `[true, false]` |

Đây là **kết quả tham chiếu được nêu trong yêu cầu của ví dụ**, không phải kết quả đã thu được khi chạy chương trình ở môi trường thực. Trong dự án đang có người dùng, kết quả tham chiếu nên được đối chiếu với tài liệu nghiệp vụ, regression tests hiện hành hoặc hành vi phiên bản trước được chủ sản phẩm xác nhận.

## 4. Thiết kế thí nghiệm trước/sau

Để tránh hai bộ test khác nhau về dữ liệu và thứ tự thao tác, dùng một **test driver chung** cho cả legacy client lẫn refactored client.

~~~mermaid
flowchart TB
    S["Cùng một kịch bản thao tác"] --> O["LegacySettingsPanel"]
    S --> N["SettingsPanel(UiFactory)"]
    O --> T1["ScenarioTrace cũ"]
    N --> T2["ScenarioTrace mới"]
    G["Golden baseline được phê duyệt"] --> V{"So sánh theo hợp đồng"}
    T1 --> V
    T2 --> V
    V -->|"Khớp"| P["Giữ nguyên hành vi Light"]
    V -->|"Khác"| F["Điều tra hồi quy hoặc khác biệt được chấp nhận"]
~~~

Ta cần tách **ba câu hỏi độc lập**:

- **Legacy có thỏa baseline không?** Nếu không, baseline hoặc mã cũ đã có vấn đề; chưa được kết luận refactor gây lỗi.
- **Client mới có cùng kết quả với legacy cho Light không?** Nếu không, có thay đổi hành vi cần giải thích.
- **Client mới có tạo và phối hợp đúng họ Dark không?** Đây là yêu cầu mở rộng, cần expected riêng cho Dark; không thể bắt Dark render giống Light.

Cách chia này tránh một nhầm lẫn: chỉ so sánh hai implementation với nhau có thể khiến test xanh khi **cả hai cùng sai** so với yêu cầu nghiệp vụ.

## 5. Mô hình Java dùng để đối chiếu

Ví dụ bên dưới dùng Java 17+, hoàn chỉnh trong **một file `SettingsRegressionDemo.java`**. Nó chứa:

- Hai abstract product `Button` và `Checkbox`.
- Các concrete product thuộc hai họ Light và Dark.
- Một `LegacySettingsPanel` tự tạo concrete product Light.
- Một `SettingsPanel` nhận `UiFactory` qua constructor.
- Một `runScenario()` chung, trả về `ScenarioTrace` để so sánh.

### 5.1. Interface và các sản phẩm cụ thể

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class SettingsRegressionDemo {

    enum Theme {
        LIGHT, DARK
    }

    interface UiProduct {
        Theme theme();
        String render();
    }

    interface Button extends UiProduct {
        void onClick(Runnable callback);
        void click();
    }

    interface Checkbox extends UiProduct {
        void setChecked(boolean checked);
        boolean isChecked();
    }

    interface UiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Chỉ có hai loại concrete Button, nhưng cùng contract.
    static final class LightButton implements Button {
        private Runnable callback = () -> {};

        @Override
        public Theme theme() { return Theme.LIGHT; }

        @Override
        public String render() { return "LightButton"; }

        @Override
        public void onClick(Runnable callback) {
            this.callback = Objects.requireNonNull(callback);
        }

        @Override
        public void click() { callback.run(); }
    }

    static final class DarkButton implements Button {
        private Runnable callback = () -> {};

        @Override
        public Theme theme() { return Theme.DARK; }

        @Override
        public String render() { return "DarkButton"; }

        @Override
        public void onClick(Runnable callback) {
            this.callback = Objects.requireNonNull(callback);
        }

        @Override
        public void click() { callback.run(); }
    }

    static final class LightCheckbox implements Checkbox {
        private boolean checked;

        @Override
        public Theme theme() { return Theme.LIGHT; }

        @Override
        public String render() { return "LightCheckbox"; }

        @Override
        public void setChecked(boolean checked) {
            this.checked = checked;
        }

        @Override
        public boolean isChecked() { return checked; }
    }

    static final class DarkCheckbox implements Checkbox {
        private boolean checked;

        @Override
        public Theme theme() { return Theme.DARK; }

        @Override
        public String render() { return "DarkCheckbox"; }

        @Override
        public void setChecked(boolean checked) {
            this.checked = checked;
        }

        @Override
        public boolean isChecked() { return checked; }
    }

    // Những phần còn lại được thêm vào class này ở mục sau.
}
~~~

Hai họ có cách hiển thị riêng nhưng cùng hợp đồng: nút nhận callback rồi chạy callback khi click; ô chọn lưu đúng trạng thái boolean. Ví dụ chọn callback đồng bộ để trace dễ đối chiếu. Hệ thống UI dùng callback bất đồng bộ phải có cơ chế chờ event hoàn thành trước khi assert.

### 5.2. Định nghĩa một kịch bản mà cả client cũ và mới đều chạy được

Bổ sung các kiểu lồng nhau dưới đây **bên trong `SettingsRegressionDemo`**:

~~~java
interface SettingsWorkflow {
    void setNotificationsEnabled(boolean enabled);
    void save();
    String render();
    List<Boolean> savedEvents();
}

record ScenarioTrace(
    String initially,
    String afterEnable,
    String afterFirstSave,
    String afterDisable,
    List<Boolean> savedValues
) {}

static ScenarioTrace runScenario(SettingsWorkflow panel) {
    String initial = panel.render();

    panel.setNotificationsEnabled(true);
    String enabled = panel.render();

    panel.save();
    String saved = panel.render();

    panel.setNotificationsEnabled(false);
    panel.save();
    String disabled = panel.render();

    // Chốt một bản sao bất biến để không bị đổi bởi test sau.
    return new ScenarioTrace(
        initial,
        enabled,
        saved,
        disabled,
        List.copyOf(panel.savedEvents())
    );
}
~~~

`ScenarioTrace` là *behavioral projection* của ví dụ. Nó chỉ giữ trạng thái render và các event đã lưu. Test không cần biết từng client tạo bao nhiêu biến local, constructor nằm ở class nào hoặc sử dụng container DI gì.

Một đặc tính quan trọng: `runScenario()` **không kiểm tra type concrete** và không tạo sản phẩm. Driver làm việc với `SettingsWorkflow`, vì vậy chạy cùng lời gọi trên cả hai phiên bản.

### 5.3. Phiên bản trước refactor: phụ thuộc concrete class

~~~java
static final class LegacySettingsPanel implements SettingsWorkflow {
    private final LightButton button = new LightButton();
    private final LightCheckbox checkbox = new LightCheckbox();
    private final List<Boolean> saves = new ArrayList<>();

    LegacySettingsPanel() {
        button.onClick(() -> saves.add(checkbox.isChecked()));
    }

    @Override
    public void setNotificationsEnabled(boolean enabled) {
        checkbox.setChecked(enabled);
    }

    @Override
    public void save() {
        button.click();
    }

    @Override
    public String render() {
        return button.render()
            + " | " + checkbox.render()
            + " | notifications=" + checkbox.isChecked();
    }

    @Override
    public List<Boolean> savedEvents() {
        return List.copyOf(saves);
    }
}
~~~

Client này phụ thuộc trực tiếp vào `LightButton` và `LightCheckbox`. Chạy cùng một kịch bản Light sẽ tạo baseline. Quan trọng là ta **không chỉnh sửa hành vi bên trong sản phẩm** trong giai đoạn đầu refactor; ta muốn biết tác động của việc chuyển quyền tạo ra ngoài client.

### 5.4. Phiên bản sau refactor: nhận Abstract Factory qua constructor

~~~java
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

static final class SettingsPanel implements SettingsWorkflow {
    private final Button button;
    private final Checkbox checkbox;
    private final List<Boolean> saves = new ArrayList<>();

    SettingsPanel(UiFactory factory) {
        Objects.requireNonNull(factory, "factory");

        button = Objects.requireNonNull(
            factory.createButton(), "createButton returned null"
        );
        checkbox = Objects.requireNonNull(
            factory.createCheckbox(), "createCheckbox returned null"
        );

        // Giữ bất biến cả hai product thuộc cùng họ.
        if (button.theme() != checkbox.theme()) {
            throw new IllegalArgumentException(
                "Factory returned products from different families"
            );
        }

        button.onClick(() -> saves.add(checkbox.isChecked()));
    }

    List<Theme> productThemes() {
        return List.of(button.theme(), checkbox.theme());
    }

    @Override
    public void setNotificationsEnabled(boolean enabled) {
        checkbox.setChecked(enabled);
    }

    @Override
    public void save() {
        button.click();
    }

    @Override
    public String render() {
        return button.render()
            + " | " + checkbox.render()
            + " | notifications=" + checkbox.isChecked();
    }

    @Override
    public List<Boolean> savedEvents() {
        return List.copyOf(saves);
    }
}
~~~

**So sánh trách nhiệm trước/sau:**

| Trách nhiệm | Trước refactor | Sau refactor |
| --- | --- | --- |
| Chọn họ Light/Dark | Cố định trong client | Composition root tạo concrete factory |
| Khởi tạo product | Client gọi trực tiếp `new LightButton()`, `new LightCheckbox()` | Client gọi `factory.createButton()` và `factory.createCheckbox()` |
| Interface sử dụng | Concrete class | `Button` và `Checkbox` |
| Đăng ký callback Save | Trong client | Vẫn trong client, dùng product interface |
| Lưu lịch sử Save | `List<Boolean> saves` | Vẫn cùng semantics |
| Hỗ trợ Dark | Phải viết lại client | Dùng `new SettingsPanel(new DarkUiFactory())` |

`SettingsPanel` thêm kiểm tra tính nhất quán họ như một biện pháp phòng lỗi cấu hình. Đây là **ràng buộc mới cho đầu vào không hợp lệ**; nó không thay đổi hành vi chuẩn của họ Light được dùng để đo hồi quy. Kiểm thử cho trường hợp factory trộn họ phải được xem là test riêng cho contract mới.

### 5.5. Đặt chương trình chạy mẫu ở composition root

Thêm vào bên trong `SettingsRegressionDemo`:

~~~java
public static void main(String[] args) {
    ScenarioTrace legacy = runScenario(new LegacySettingsPanel());

    ScenarioTrace refactoredLight = runScenario(
        new SettingsPanel(new LightUiFactory())
    );

    ScenarioTrace refactoredDark = runScenario(
        new SettingsPanel(new DarkUiFactory())
    );

    System.out.println(
        "Light behavior preserved: " + legacy.equals(refactoredLight)
    );
    System.out.println(
        "Dark first render: " + refactoredDark.initially()
    );
}
~~~

Sau khi ghép các đoạn ở mục 5.1–5.5 vào cùng class, chạy:

~~~bash
javac SettingsRegressionDemo.java
java SettingsRegressionDemo
~~~

Output **dự kiến**:

~~~text
Light behavior preserved: true
Dark first render: DarkButton | DarkCheckbox | notifications=false
~~~

Kết quả `true` là điều ví dụ được thiết kế để chứng minh; trong dự án thực tế, bạn vẫn phải chạy test, ghi nhận kết quả và xử lý mọi sai khác.

## 6. Từ ví dụ đến bộ JUnit 5 regression test

Đặt tệp kiểm thử minh họa `SettingsRegressionDemoTest.java` cùng package với `SettingsRegressionDemo.java` và cấu hình JUnit Jupiter 5 cùng `junit-jupiter-params` cho test tham số hóa.

### 6.1. Golden baseline: cố định kết quả nghiệp vụ đã được chấp nhận

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.stream.Stream;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class SettingsRegressionDemoTest {

    private static SettingsRegressionDemo.ScenarioTrace lightBaseline() {
        String off =
            "LightButton | LightCheckbox | notifications=false";
        String on =
            "LightButton | LightCheckbox | notifications=true";

        return new SettingsRegressionDemo.ScenarioTrace(
            off, on, on, off, List.of(true, false)
        );
    }

    private static SettingsRegressionDemo.ScenarioTrace darkExpected() {
        String off =
            "DarkButton | DarkCheckbox | notifications=false";
        String on =
            "DarkButton | DarkCheckbox | notifications=true";

        return new SettingsRegressionDemo.ScenarioTrace(
            off, on, on, off, List.of(true, false)
        );
    }

    @Test
    void legacy_matches_approved_light_baseline() {
        var result = SettingsRegressionDemo.runScenario(
            new SettingsRegressionDemo.LegacySettingsPanel()
        );

        assertEquals(lightBaseline(), result);
    }

    @Test
    void refactored_light_matches_legacy_and_baseline() {
        var legacy = SettingsRegressionDemo.runScenario(
            new SettingsRegressionDemo.LegacySettingsPanel()
        );

        var after = SettingsRegressionDemo.runScenario(
            new SettingsRegressionDemo.SettingsPanel(
                new SettingsRegressionDemo.LightUiFactory()
            )
        );

        // Hai cơ chế tạo đối tượng cho cùng kết quả.
        assertEquals(legacy, after);

        // Cả hai còn phải khớp oracle độc lập.
        assertEquals(lightBaseline(), after);
    }

    // Các kiểm thử khác được bổ sung vào class này bên dưới.
}
~~~

Vì `ScenarioTrace` là một `record`, `assertEquals` so sánh các component theo `equals()`. Với `List<Boolean>`, phép so sánh kiểm tra cả **số lần lưu** và **thứ tự giá trị**, nên sẽ phát hiện callback chạy hai lần hoặc lưu nhầm state.

Đừng lấy kết quả của legacy ngay trong test rồi coi đó là toàn bộ oracle. Nếu legacy vốn lưu sai hoặc bị thay đổi cùng lúc với refactor, hai bản có thể cùng lỗi. `lightBaseline()` là một mốc riêng phải được phê duyệt; về sau chỉ thay mốc khi thay đổi nghiệp vụ được xác nhận.

### 6.2. Họ mới cần expected mới, đồng thời dùng cùng client

Việc Dark hiển thị `DarkButton` thay vì `LightButton` là khác biệt **có chủ đích**, không phải hồi quy. Test nên kiểm tra semantics chung và phần thay đổi được cho phép.

Bổ sung trong `SettingsRegressionDemoTest`:

~~~java
static Stream<Arguments> supportedFactories() {
    return Stream.of(
        Arguments.of(
            "Light",
            (Supplier<SettingsRegressionDemo.UiFactory>)
                SettingsRegressionDemo.LightUiFactory::new,
            SettingsRegressionDemo.Theme.LIGHT,
            lightBaseline()
        ),
        Arguments.of(
            "Dark",
            (Supplier<SettingsRegressionDemo.UiFactory>)
                SettingsRegressionDemo.DarkUiFactory::new,
            SettingsRegressionDemo.Theme.DARK,
            darkExpected()
        )
    );
}

@ParameterizedTest(name = "{0} family follows shared workflow")
@MethodSource("supportedFactories")
void shared_workflow_is_correct_for_each_family(
        String family,
        Supplier<SettingsRegressionDemo.UiFactory> factorySupplier,
        SettingsRegressionDemo.Theme expectedTheme,
        SettingsRegressionDemo.ScenarioTrace expected) {

    var panel = new SettingsRegressionDemo.SettingsPanel(
        factorySupplier.get()
    );

    assertEquals(
        List.of(expectedTheme, expectedTheme),
        panel.productThemes()
    );

    assertEquals(
        expected,
        SettingsRegressionDemo.runScenario(panel)
    );
}
~~~

Mỗi họ chạy cùng `runScenario`, nhưng có kết quả render mong đợi riêng và cùng lịch sử sự kiện `[true, false]`. Nhờ đó, test xác minh hai điều:

- **Shared contract:** Bật/tắt thông báo và nhấn Save hoạt động như nhau về semantics.
- **Family invariant:** Button và Checkbox được chọn thuộc cùng họ mong đợi, không trộn Light/Dark.

### 6.3. Chứng minh client thật sự dùng factory được inject

Hai test so sánh Light có thể chưa bắt được tình huống `SettingsPanel` âm thầm quay lại tự tạo `LightButton` và `LightCheckbox` nếu output Light vẫn giống nhau. Dùng **recording factory** trả các product giả có tên hiển thị khác Light/Dark để kiểm tra ranh giới phụ thuộc.

Bổ sung vào cùng class test:

~~~java
static final class RecordingFactory
        implements SettingsRegressionDemo.UiFactory {

    int createButtonCalls;
    int createCheckboxCalls;

    @Override
    public SettingsRegressionDemo.Button createButton() {
        createButtonCalls++;
        return new SettingsRegressionDemo.Button() {
            private Runnable callback = () -> {};

            @Override
            public SettingsRegressionDemo.Theme theme() {
                return SettingsRegressionDemo.Theme.LIGHT;
            }

            @Override
            public String render() {
                return "InjectedButton";
            }

            @Override
            public void onClick(Runnable newCallback) {
                callback = newCallback;
            }

            @Override
            public void click() {
                callback.run();
            }
        };
    }

    @Override
    public SettingsRegressionDemo.Checkbox createCheckbox() {
        createCheckboxCalls++;
        return new SettingsRegressionDemo.Checkbox() {
            private boolean checked;

            @Override
            public SettingsRegressionDemo.Theme theme() {
                return SettingsRegressionDemo.Theme.LIGHT;
            }

            @Override
            public String render() {
                return "InjectedCheckbox";
            }

            @Override
            public void setChecked(boolean value) {
                checked = value;
            }

            @Override
            public boolean isChecked() {
                return checked;
            }
        };
    }
}

@Test
void refactored_client_uses_injected_factory() {
    var factory = new RecordingFactory();
    var panel = new SettingsRegressionDemo.SettingsPanel(factory);

    assertEquals(1, factory.createButtonCalls);
    assertEquals(1, factory.createCheckboxCalls);

    assertEquals(
        "InjectedButton | InjectedCheckbox | notifications=false",
        panel.render()
    );

    panel.setNotificationsEnabled(true);
    panel.save();
    assertEquals(List.of(true), panel.savedEvents());
}
~~~

Một `SettingsPanel` tự ý tạo concrete Light product sẽ không cho output `InjectedButton | InjectedCheckbox`, nên test này kiểm tra đúng mục tiêu tái cấu trúc **di chuyển quyền tạo sản phẩm ra factory**.

### 6.4. Kiểm tra lỗi cấu hình sau refactor

Ví dụ còn có hợp đồng mới: không cho tạo panel từ factory trộn họ hoặc nhận factory `null`. Đây là các ca kiểm tra **tính hợp lệ đầu vào**, được tách riêng khỏi bài test tương đương với legacy.

~~~java
@Test
void rejects_null_factory() {
    assertThrows(NullPointerException.class,
        () -> new SettingsRegressionDemo.SettingsPanel(null));
}

@Test
void rejects_mixed_product_families() {
    SettingsRegressionDemo.UiFactory mixed =
        new SettingsRegressionDemo.UiFactory() {
            @Override
            public SettingsRegressionDemo.Button createButton() {
                return new SettingsRegressionDemo.LightButton();
            }

            @Override
            public SettingsRegressionDemo.Checkbox createCheckbox() {
                return new SettingsRegressionDemo.DarkCheckbox();
            }
        };

    assertThrows(IllegalArgumentException.class,
        () -> new SettingsRegressionDemo.SettingsPanel(mixed));
}
~~~

Tổng bộ test minh họa ở mục 6 có **7 lượt chạy**: 1 baseline của legacy, 1 đối chiếu legacy/refactored Light, 2 lượt tham số hóa Light/Dark, 1 recording factory và 2 kiểm tra lỗi đầu vào.

## 7. Bảng kiểm thử hồi quy nên dùng trong PR refactor

Một ma trận giúp reviewer thấy **bài nào giữ hành vi cũ** và **bài nào bảo vệ tính năng hoặc kiến trúc mới**.

| ID | Test/kịch bản | Phiên bản cũ | Phiên bản mới Light | Phiên bản mới Dark | Mục tiêu |
| --- | --- | :---: | :---: | :---: | --- |
| **RG-01** | Render mặc định | ✓ | ✓ | ✓ | Giá trị bắt đầu đúng |
| **RG-02** | Bật/tắt thông báo | ✓ | ✓ | ✓ | State thay đổi đúng |
| **RG-03** | Save hai lần | ✓ | ✓ | ✓ | Lưu đúng `[true, false]`, đúng thứ tự |
| **RG-04** | Output của cùng họ Light | ✓ | ✓ | — | Không đổi hành vi cũ |
| **RG-05** | Button/Checkbox cùng họ | N/A | ✓ | ✓ | Không trộn concrete product |
| **RG-06** | Dùng factory được inject | N/A | ✓ | ✓ | Client không tự chọn concrete product |
| **RG-07** | Reject factory `null` hoặc mixed | N/A | ✓ | ✓ | Bảo vệ contract khởi tạo mới |

Dấu ✓ nghĩa là **yêu cầu kiểm tra**, chưa thể hiện kết quả chạy thực tế. Ký hiệu N/A là trường hợp không áp dụng với thiết kế cũ. Khi chạy CI, gắn trạng thái PASS/FAIL và đường dẫn test report tương ứng; không ghi PASS chỉ vì đã viết code test.

**Điểm quan trọng:** Không nên đưa mọi dòng vào một `assertEquals(legacy, newClient)` khổng lồ. Test tương đương bảo vệ hành vi đã có; test factory injection và tính nhất quán họ bảo vệ thiết kế mới. Mỗi loại lỗi cần một nguyên nhân thất bại rõ ràng.

## 8. Xử lý thay đổi có chủ đích trong kết quả

Trong refactor, có thể cần đổi một phần output do yêu cầu mới. Ví dụ chuyển Light sang Dark, hoặc trước đây tên widget là `LightButton` nhưng giờ UI thật dùng aria-label ổn định và style token.

Nếu so sánh nguyên chuỗi mà không có quy tắc, test có thể thất bại vì một khác biệt hợp lệ hoặc — tệ hơn — team cập nhật snapshot mà không xem nội dung.

Hãy chia kết quả thành hai phần:

| Phần | Chính sách so sánh |
| --- | --- |
| State nghiệp vụ: `isChecked` và lịch sử Save | Phải tương đương tuyệt đối cho cùng chuỗi thao tác |
| Tên theme hoặc style | So với expected của họ được chọn |
| Nội dung text hiển thị cho người dùng | Giữ theo yêu cầu cũ hoặc xác nhận yêu cầu mới |
| Mã event hoặc timestamp phát sinh | Chuẩn hóa nếu không thuộc hợp đồng |
| Chi tiết implementation, log nội bộ | Không đưa vào phép so hành vi trừ khi có yêu cầu |
| Số lần gọi repository hoặc tác động bên ngoài | Kiểm tra khi có rủi ro tạo tác dụng phụ trùng lặp |

### 8.1. Ví dụ chuẩn hóa output không ổn định

Giả sử một báo cáo có trường `generatedAt` phụ thuộc thời gian và `requestId` ngẫu nhiên. Không nên xóa hai trường này khỏi mọi assertion một cách mù quáng. Có thể tiêm `Clock` và `IdGenerator` cố định trong test để kiểm soát dữ liệu.

Nếu chỉ cần so sánh phần output nghiệp vụ, tạo một phép chiếu có tên rõ ràng:

~~~java
record BusinessResult(
    String documentType,
    int totalItems,
    boolean exportedSuccessfully
) {}
~~~

Hai phiên bản có thể tạo metadata khác nhau nhưng trả cùng `BusinessResult` theo contract. Tuy nhiên, nếu yêu cầu nghiệp vụ nói file xuất phải giữ nguyên định dạng và timestamp, metadata đó lại là **thành phần cần kiểm tra**. Quy tắc lọc phải xuất phát từ đặc tả.

### 8.2. Golden master phải được review

Golden master (snapshot hoặc fixture tham chiếu) có ích cho output phức tạp, nhưng dễ trở thành *“approve all”*: mỗi lần test thất bại thì cập nhật file tham chiếu để có màu xanh. Quy trình đúng là:

1. Xác nhận khác biệt xuất phát từ yêu cầu mới hay lỗi.
2. Xem diff có thể đọc được, nhất là phần tiền, quyền hạn, số lần xử lý và dữ liệu người dùng.
3. Chỉ cập nhật baseline khi bên sở hữu yêu cầu xác nhận hành vi mới là đúng.
4. Giữ các assertion quan trọng độc lập với snapshot, ví dụ số lần thanh toán hoặc state transition.

Trong ví dụ này, `lightBaseline()` được viết bằng dữ liệu mong đợi cụ thể thay vì lưu file snapshot riêng, nên việc review các thay đổi nhìn thấy ngay trong code.

## 9. Những cách kiểm thử có thể tạo cảm giác an toàn giả

### Chỉ chạy test trên client mới

Nếu không chốt baseline từ trước, test mới có thể chỉ xác nhận implementation mới **đang làm những gì nó tự chọn**, không chứng minh đã giữ nghiệp vụ cũ. Hãy bắt đầu từ behavior đã chấp nhận và test hiện hành.

### So sánh cùng một đối tượng với chính nó

~~~java
// Sai: luôn đúng trừ khi chính lời gọi thay đổi bất thường.
assertEquals(panel.render(), panel.render());
~~~

Cần hai triển khai độc lập hoặc một expected được viết từ hợp đồng, và nên chạy kịch bản có nhiều thao tác trạng thái.

### Lấy expected từ kết quả actual

~~~java
String expected = newPanel.render();
assertEquals(expected, newPanel.render());
~~~

Đây không phải kiểm thử hồi quy có giá trị. Nếu dùng differential testing, phải đặt **legacy và refactored vào hai instance** nhận cùng đầu vào; đồng thời kiểm tra với baseline được phê duyệt.

### Chỉ test một trạng thái

Một bài test `render()` ban đầu có thể xanh dù callback Save không còn chạy. Hãy đưa cả chuỗi tương tác qua hệ thống và kiểm tra **tác dụng phụ** như dữ liệu đã lưu, event đã phát hoặc request đã gửi.

### Không xác nhận tính nhất quán của family

Client mới có thể dùng `LightButton` với `DarkCheckbox`. Cả hai hợp lệ theo product interface nhưng không thuộc cùng họ. Hãy kiểm tra cả family invariant và output trong test mới.

### Cho các test dùng chung đối tượng mutable

Nếu test thứ nhất bật Checkbox còn test thứ hai giả định nó đang tắt, kết quả phụ thuộc thứ tự chạy. Mỗi test nên tạo instance `LegacySettingsPanel` và `SettingsPanel` mới, dùng fake repository hoặc trạng thái test cô lập.

### Bỏ qua kết quả bất đồng bộ

Nếu Save phát event hoặc ghi database bất đồng bộ, kiểm tra ngay sau click có thể đọc kết quả trước khi xử lý xong. Sử dụng future/callback completion hoặc cơ chế đợi có timeout được framework cung cấp. Không dùng `Thread.sleep` cố định để “đợi cho chắc”.

### Đọc thẳng output nội bộ thay vì hợp đồng public

Một test gọi reflection để xem field concrete có thể thất bại chỉ vì refactor đổi tên field, dù hành vi vẫn đúng. Test refactor nên ưu tiên API/đầu ra public và ràng buộc kiến trúc được xác định rõ.

## 10. Dùng lỗi chủ động để đánh giá độ nhạy của suite

Trước khi tin rằng suite đủ khả năng phát hiện hồi quy, hãy dự đoán lỗi nào làm test thất bại:

| Lỗi giả định đưa vào sau refactor | Test có thể phát hiện | Giải thích |
| --- | --- | --- |
| `SettingsPanel` lưu `false` thay vì đọc Checkbox hiện tại khi Save | `refactored_light_matches_legacy_and_baseline`, test mọi họ | `savedValues` không còn `[true, false]` |
| `Button.click()` gọi callback hai lần | Baseline/differential và các test shared workflow | Danh sách Save có event dư |
| `Checkbox` mặc định `true` | Test baseline + expected mỗi họ | `initially()` sai |
| `DarkUiFactory.createCheckbox()` trả `LightCheckbox` | `shared_workflow_is_correct_for_each_family` | `productThemes()` không khớp DARK |
| Client âm thầm `new LightButton()`, bỏ qua factory truyền vào | `refactored_client_uses_injected_factory` | Product giả không được sử dụng; output khác |
| Client chỉ sửa chuỗi render nhưng không lưu state đúng | Test ghi sự kiện Save | `savedValues` không phản ánh thao tác |
| Cả legacy lẫn new client sai giống nhau do sửa chung product | `legacy_matches_approved_light_baseline` | Oracle cố định phát hiện sai lệch |

Có thể sử dụng **mutation testing** để tự động hoán đổi biểu thức hoặc xóa lời gọi và xem các test có “giết” biến thể lỗi không. Nhưng mutation score không thay thế review yêu cầu nghiệp vụ; test vẫn có thể thiếu một tình huống quan trọng chưa được mô tả.

## 11. Tách mức kiểm thử cho một refactor lớn

Không phải tất cả lỗi đều được phát hiện tốt bằng cùng một loại test.

| Mức kiểm thử | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Unit / contract** | Concrete product còn thực hiện đúng interface? | Button chỉ gọi callback đúng một lần, Checkbox lưu state |
| **Factory invariant** | Concrete factory tạo đủ loại và đúng họ? | Dark factory trả Button/Checkbox đều thuộc Dark |
| **Regression / characterization** | Cùng kịch bản cũ còn cùng kết quả? | Baseline Light trước/sau refactor |
| **Client integration** | Client dùng dependency injected và cộng tác sản phẩm đúng? | Recording factory, workflow lưu thông báo |
| **End-to-end / UI** | Người dùng thực thấy và thao tác đúng? | Toggle và Save trên màn hình thật |
| **Resource lifecycle** | Chuyển/đóng product có rò tài nguyên? | Handler, listener, session được hủy đúng lúc |

Nếu trước refactor dùng concrete product thật còn sau refactor chỉ test với mock, suite có thể bỏ lọt lỗi của concrete factory. Nên kết hợp **test dùng factory thật** với **fake/recording factory** kiểm tra dependency injection.

Với hệ thống có database, queue hoặc API bên ngoài, thêm test về số lần ghi dữ liệu và transaction khi cần. Dùng fake hoặc test environment đủ cô lập để kiểm tra hệ quả mà không gây tác động ngoài ý muốn.

## 12. Quy trình áp dụng trong repository

Một quy trình phù hợp khi tái cấu trúc client từ concrete products sang Abstract Factory:

1. **Khoanh vùng hành vi:** Liệt kê các thao tác và output hiện được người dùng phụ thuộc; ghi rõ những đầu vào và lỗi quan trọng.
2. **Chốt baseline:** Viết characterization tests cho code cũ, thêm oracle độc lập cho các yêu cầu đã xác nhận.
3. **Làm cho test xác định:** Cô lập database/network, đặt seed và clock, tránh phụ thuộc thứ tự test.
4. **Đưa product interface vào:** Giữ logic nghiệp vụ cũ, đưa các thao tác chung vào abstraction.
5. **Tạo concrete factory cho họ cũ:** Factory mới trả đúng những concrete product legacy đang dùng.
6. **Inject factory vào client:** Thay `new` concrete product trong client bằng `factory.createX()`, giữ callback và state transition.
7. **Chạy đối chiếu cùng dữ liệu:** So `ScenarioTrace` của bản cũ và bản mới, xem riêng mọi khác biệt.
8. **Mở rộng họ mới:** Thêm factory mới và chạy lại shared contract; không bắt output Dark giống Light.
9. **Cập nhật các caller và xóa đường cũ:** Chỉ khi các call site đã chuyển sang API mới và regression tests đạt, gỡ phần khởi tạo legacy không còn dùng.
10. **Xác nhận ở tầng tích hợp:** Với UI/DB thật, kiểm tra thêm hành vi người dùng và tác dụng phụ mà test in-memory không mô phỏng được.

Đối với hệ thống lớn, có thể đưa phiên bản mới sau một feature flag để kiểm tra dần. Cần tránh hai implementation cùng thực hiện **tác dụng phụ thật** trong lúc so sánh (ví dụ cùng gửi thanh toán hoặc email). Nếu muốn so sánh song song, chỉ chạy trên read-only dữ liệu, sandbox hoặc cơ chế dry-run có quy định.

### 12.1. Mẫu báo cáo thay đổi cho reviewer

| Câu hỏi | Bằng chứng nên cung cấp |
| --- | --- |
| Hành vi nào được bảo toàn? | Danh sách kịch bản và baseline được chấp nhận |
| Hành vi nào thay đổi có chủ đích? | Yêu cầu mới, ví dụ Dark được hỗ trợ |
| Mã nào thay đổi trách nhiệm? | Client bỏ `new` concrete product; composition root chọn factory |
| Có bỏ sót factory implementation? | Matrix mọi concrete family và product contract |
| Các trường hợp lỗi có được kiểm tra? | Factory `null`, mixed family, exception từ product nếu có |
| Kết quả chạy thực tế? | JUnit report/CI run, thay vì ghi PASS chỉ dựa trên code mẫu |

## 13. Bài tập tự thực hành

Một hệ thống xuất hóa đơn có client `InvoicePage` tự tạo `PdfHeader` và `PdfTable`. Yêu cầu là refactor sang `InvoiceFactory` để hỗ trợ cả PDF và HTML.

### Đề bài

1. Chọn ba kịch bản nghiệp vụ trước refactor: hóa đơn không có dòng, một dòng và nhiều dòng có tổng tiền.
2. Viết golden baseline cho số dòng, tổng tiền và cấu trúc đầu ra PDF đã được phê duyệt.
3. Tạo `Header`, `Table` và `InvoiceFactory`; chuyển `InvoicePage` sang constructor injection.
4. Chạy **cùng ba kịch bản PDF** trên legacy client và refactored client, so sánh các chỉ số nghiệp vụ.
5. Tạo `HtmlInvoiceFactory`. Viết expected HTML riêng nhưng giữ cùng tổng tiền, số dòng và thứ tự dữ liệu.
6. Viết một recording factory để chứng minh client gọi `createHeader()` và `createTable()` thay vì tự khởi tạo `PdfHeader`.
7. Tiêm lỗi cố ý: `HtmlInvoiceFactory.createTable()` trả nhầm `PdfTable`. Chọn assertion có thể phát hiện.
8. Giải thích vì sao không được chạy cả bản cũ và mới để **phát hành hai hóa đơn thật** chỉ nhằm so sánh.

### Gợi ý lời giải

Tạo một record kết quả dùng chung cho hai định dạng:

~~~java
record InvoiceTrace(
    int lineCount,
    long totalMinorUnits,
    List<String> itemIds,
    boolean exported
) {}
~~~

So sánh `InvoiceTrace` theo hợp đồng cho **cùng dữ liệu đầu vào**, và kiểm tra định dạng/metadata riêng cho PDF hoặc HTML. Sử dụng số nguyên đơn vị tiền nhỏ nhất hoặc `BigDecimal` theo quy ước nghiệp vụ; không dùng `double` để suy tổng tiền chính xác.

Nếu test PDF cũ và mới đều cho `totalMinorUnits=10000` nhưng thứ tự các dòng đảo ngược, bộ test chỉ kiểm tra tổng sẽ bỏ sót hồi quy. Vì vậy, `itemIds` có thứ tự là một phần của projection nếu hóa đơn yêu cầu giữ thứ tự dòng.

## 14. Checklist hoàn thành

- [ ] Xác định rõ behavior cũ cần bảo toàn và behavior mới được phép thay đổi.
- [ ] Có baseline độc lập trước khi sửa client hoặc concrete product.
- [ ] Driver chạy **cùng thứ tự thao tác và cùng đầu vào** cho legacy/refactored.
- [ ] So sánh được state, output và tác dụng phụ quan trọng, không chỉ constructor.
- [ ] Client refactored nhận `AbstractFactory` qua constructor và dùng product interface.
- [ ] Test xác minh client thật sự gọi factory được inject.
- [ ] Tất cả concrete family hiện có đều được chạy qua shared contract tests.
- [ ] Kiểm tra đúng họ, đủ loại sản phẩm và tình huống cộng tác.
- [ ] Fixture/test độc lập, không chia sẻ mutable state hoặc phụ thuộc clock/random.
- [ ] Khác biệt có chủ đích được mô tả, review và không che khuất các hồi quy khác.
- [ ] Không chạy song song tác dụng phụ thật để làm differential test.
- [ ] Lưu kết quả test thực tế và bằng chứng CI khi áp dụng vào dự án.

## 15. Ghi nhớ

Refactor sang Abstract Factory có thể thay đổi **toàn bộ đường tạo đối tượng** mà vẫn phải bảo toàn những gì người dùng quan sát được. Một chiến lược đáng tin cậy là chốt **baseline của hành vi cũ**, chạy cùng **kịch bản thao tác** trên bản legacy và refactored, rồi so sánh **output, trạng thái và tác dụng phụ** bằng các expected độc lập.

Với cùng họ Light, kết quả cũ và mới phải tương đương theo hợp đồng. Với họ Dark mới, phần hành vi chung vẫn phải đúng còn khác biệt về biến thể cần được kiểm thử theo expected của Dark. Kết hợp regression test, kiểm thử sản phẩm, kiểm thử tính nhất quán họ và recording factory giúp bảo vệ cả **hành vi** lẫn **mục tiêu kiến trúc** của lần tái cấu trúc.
