# Theo dõi lỗi và thông tin biến thể tại điểm tạo sản phẩm để hỗ trợ vận hành

Trong mẫu thiết kế **Abstract Factory**, một factory cụ thể tạo các sản phẩm thuộc cùng một họ, chẳng hạn `LightButton` và `LightCheckbox` thuộc họ Light hoặc `DarkButton` và `DarkCheckbox` thuộc họ Dark. Mã nghiệp vụ thường chỉ nhìn thấy `Button`, `Checkbox` và `GuiFactory`. Tính trừu tượng này giúp thay thế các họ sản phẩm, nhưng đồng thời khiến người vận hành khó biết **họ nào đã được chọn, biến thể nào thực sự được tạo và lỗi xảy ra ở đâu** nếu hệ thống không ghi nhận thông tin thích hợp.

Bài thuộc chương **Tích hợp kiến trúc** hướng dẫn bổ sung khả năng quan sát (*observability*) **tại ranh giới tạo sản phẩm**. Ta sẽ phân biệt sự kiện chọn factory với sự kiện tạo sản phẩm, thiết kế thông tin theo dõi có cấu trúc, dùng một **decorator** để ghi thành công/thất bại và kiểm tra biến thể, đồng thời bảo vệ mã nghiệp vụ khỏi phụ thuộc trực tiếp vào hạ tầng logging hoặc tracing.

Mục tiêu là có đủ bằng chứng trả lời những câu hỏi vận hành như: “Vì sao màn hình đang dùng giao diện Dark?”, “Lệnh tạo Checkbox thất bại ở họ nào?”, “Có phiên bản factory mới nào làm tăng lỗi khởi tạo?” và “Hai sản phẩm vừa tạo có thực sự cùng họ không?”.

## 1. Xác định các điểm cần quan sát trong vòng đời Abstract Factory

Một ứng dụng có thể hỗ trợ các họ Light, Dark và HighContrast. Mỗi họ triển khai hai **loại sản phẩm**:

| Họ sản phẩm | Button | Checkbox | Concrete factory |
| --- | --- | --- | --- |
| Light | LightButton | LightCheckbox | LightGuiFactory |
| Dark | DarkButton | DarkCheckbox | DarkGuiFactory |
| HighContrast | HighContrastButton | HighContrastCheckbox | HighContrastGuiFactory |

Quá trình khởi tạo nên được nhìn thành **bốn giai đoạn** khác nhau:

1. **Đọc và kiểm tra cấu hình:** yêu cầu họ nào, chẳng hạn `ui.theme=dark`?
2. **Chọn hoặc xây dựng factory:** tìm thấy concrete factory phù hợp không; factory có được cấu hình đúng không?
3. **Tạo từng sản phẩm:** `createButton()` và `createCheckbox()` có thành công, mất bao lâu và trả về biến thể nào?
4. **Sử dụng sản phẩm:** `render()`, `press()` hay thao tác nghiệp vụ của sản phẩm có thành công không?

**Điểm tạo sản phẩm chỉ quan sát trực tiếp giai đoạn 3.** Một decorator bao quanh `GuiFactory` sẽ không tự thấy lỗi chọn sai tên factory ở giai đoạn 2 nếu sự kiện đó xảy ra **trước khi decorator được tạo**. Nó cũng không tự biết lỗi phát sinh sau này trong `Button.render()` ở giai đoạn 4. Cần đặt instrumentation theo đúng vị trí lỗi có thể xảy ra.

### Tình huống vận hành cụ thể

Giả sử ứng dụng chọn DarkGuiFactory thành công, tạo DarkButton thành công nhưng `createCheckbox()` ném ngoại lệ vì tài nguyên giao diện chưa có. Nếu chỉ ghi “khởi tạo màn hình thất bại”, người vận hành không biết cần kiểm tra lớp nào.

Một bản ghi tại factory boundary nên chỉ rõ:

~~~text
event=factory_product_create
result=failure
family=dark
factory=dark-gui
factory_version=1
product_type=checkbox
expected_variant=dark-checkbox-v1
error_kind=invalid_state
correlation_id=demo-001
~~~

Đây là **dữ liệu minh họa**, không phải bản ghi có định dạng bắt buộc của một thư viện Java. Thông tin biến thể kỳ vọng có thể biết được **trước khi gọi phương thức tạo**, nên ngay cả khi phương thức ném lỗi và chưa có instance nào được trả về, sự kiện vẫn có ngữ cảnh để chẩn đoán.

## 2. Phân biệt thông tin dự kiến với biến thể thực tế

Khi sử dụng Abstract Factory, có ba tên gọi dễ bị nhầm:

| Trường metadata | Ví dụ | Nguồn thông tin |
| --- | --- | --- |
| **familyId** | `dark` | Họ được chọn ở composition root |
| **productType** | `checkbox` | Loại sản phẩm mà client yêu cầu tạo |
| **expectedVariantId** | `dark-checkbox-v1` | Biến thể mà concrete factory được cấu hình phải tạo |
| **actualVariantId** | `dark-checkbox-v1` hoặc `light-checkbox-v1` | Metadata do sản phẩm thực tế trả về sau khi tạo |
| **factoryId / factoryVersion** | `dark-gui` / `1` | Phiên bản của concrete factory hoặc provider đã được đăng ký |

**Expected** và **actual** khác nhau về ý nghĩa. Không nên ghi `expectedVariantId` thành “biến thể thực tế” khi factory vừa thất bại hoặc trả nhầm sản phẩm. Một hệ thống gặp lỗi trộn họ có thể ghi:

~~~text
family=dark
product_type=checkbox
expected_variant=dark-checkbox-v1
actual_variant=light-checkbox-v1
result=failure
error_kind=family_mismatch
~~~

Trong thực tế, không phải sản phẩm nào cũng có API trả metadata. Có thể lấy thông tin từ **bộ mô tả factory** được đăng ký, từ một **interface metadata tùy chọn**, hoặc từ kiểm tra chuyên biệt ở tầng tích hợp. Nếu chưa xác minh được biến thể thực tế, hãy ghi `actual_variant=unknown`, không suy đoán từ tên lớp hay từ cấu hình.

### Định danh nên ổn định

Tên lớp Java như `com.example.ui.DarkButton` thường thay đổi khi refactor package, còn tên định danh vận hành như `dark-button-v1` có thể được giữ ổn định theo quy ước phát hành. Khi thiết kế metadata:

- Sử dụng **ID ngắn, có kiểm soát và được tài liệu hóa** cho họ, loại sản phẩm, biến thể và factory.
- Tách **ID logic** với **version** của factory hoặc plugin; cùng một họ có thể có nhiều bản triển khai theo thời gian.
- Quy định rõ “v1” có nghĩa là phiên bản của **biến thể**, **giao thức** hay **bản phát hành** để không nhầm lẫn.
- Không sử dụng đối tượng Java mặc định `toString()` như định danh lâu dài; nó có thể chứa địa chỉ hoặc thông tin không ổn định.

Một ID cùng họ **chưa chứng minh tương thích tuyệt đối**. Nếu Button và Checkbox cần chia sẻ phiên bản protocol, khả năng hiển thị hoặc trạng thái tài nguyên, cần bổ sung kiểm tra hành vi hoặc capability tương ứng.

## 3. Đặt instrumentation ở đâu trong kiến trúc?

**Composition root** chọn factory theo cấu hình rồi truyền nó vào client. Để theo dõi việc tạo sản phẩm mà không sửa mã nghiệp vụ, ta có thể bọc concrete factory bằng **decorator** cũng triển khai `GuiFactory`.

~~~mermaid
flowchart TB
    Config["Cấu hình: ui.theme"] --> Root["Composition root"]
    Root --> Concrete["LightGuiFactory / DarkGuiFactory"]
    Root --> Descriptor["FactoryDescriptor: family, version, variants"]
    Root --> Telemetry["CreationTelemetry"]
    Concrete --> Decorator["ObservingGuiFactory"]
    Descriptor --> Decorator
    Telemetry --> Decorator
    Root --> Decorator
    Screen["SettingsScreen"] --> Contract["GuiFactory"]
    Decorator -. "implements" .-> Contract
    Decorator -->|createButton| Concrete
    Decorator -->|createCheckbox| Concrete
    Decorator --> Events["CreationEvent: success / failure"]
    Events --> Telemetry
~~~

Sơ đồ thể hiện hai trách nhiệm tách biệt:

- **Concrete factory** vẫn chịu trách nhiệm tạo bộ sản phẩm đúng họ. Nó không cần biết cách xuất log, metric hoặc trace.
- **ObservingGuiFactory** quan sát lời gọi tạo, ghi metadata, thời lượng và lỗi, sau đó trả sản phẩm hoặc **ném lại lỗi gốc**.

Client chỉ nhận một `GuiFactory`. Nếu mai sau đổi từ log console sang OpenTelemetry, một backend metric hay tracing khác, hợp đồng `Button`, `Checkbox` và mã `SettingsScreen` không cần thay đổi.

### Vì sao truyền telemetry qua constructor?

Decorator nhận `CreationTelemetry` qua constructor cùng factory và metadata. Nó không gọi `GlobalServices.get(Logger.class)` hoặc dùng một Service Locator toàn cục. Điều này giúp kiểm thử decorator bằng một telemetry giả và làm rõ **ai sở hữu dependency hạ tầng**.

Nếu hệ thống dùng DI container, container có thể lắp ghép decorator ở composition root. Không cần đưa cả container vào concrete products hoặc cho mỗi sản phẩm tự tra cứu hạ tầng logging.

## 4. Thiết kế một sự kiện tạo sản phẩm có cấu trúc

Một sự kiện nên chứa dữ liệu đủ để chẩn đoán **một lần gọi tạo sản phẩm**, nhưng không lặp vô hạn dữ liệu của người dùng hoặc đối tượng tạo ra.

| Nhóm thông tin | Trường minh họa | Ý nghĩa vận hành |
| --- | --- | --- |
| **Bối cảnh** | `correlationId`, `operation` | Nối các sự kiện của cùng một request hoặc lần khởi tạo màn hình |
| **Quyết định chọn họ** | `familyId`, `factoryId`, `factoryVersion` | Biết chính xác provider nào đang hoạt động |
| **Sản phẩm** | `productType`, `expectedVariantId`, `actualVariantId` | Phân biệt loại sản phẩm và biến thể dự kiến/thực tế |
| **Kết quả** | `success` hoặc `failure` | Thống kê tỷ lệ tạo thành công |
| **Thời gian** | `durationNanos` hoặc histogram thời lượng | Đánh giá tốc độ tạo sản phẩm và thay đổi sau phát hành |
| **Lỗi có kiểm soát** | `errorKind` | Phân loại lỗi mà không phải dùng nguyên văn exception message |

**Không nên ghi toàn bộ nội dung cấu hình, mã thông báo truy cập, session, dữ liệu người dùng, connection string hoặc đối tượng sản phẩm** vào sự kiện. Nếu cần stack trace, hãy dùng kênh log lỗi có cơ chế kiểm soát truy cập và chính sách loại bỏ thông tin nhạy cảm.

### Ghi metadata tại thời điểm tạo

Với các sản phẩm có thể được tạo hàng nghìn lần, mỗi lời gọi ghi log chi tiết có thể tăng lưu lượng và chi phí. Nên phân biệt:

- **Log có cấu trúc:** có thể giữ sự kiện lỗi chi tiết để điều tra; sự kiện thành công có thể được lấy mẫu tùy lưu lượng.
- **Metric:** đếm số lần tạo thành công/thất bại, quan sát histogram thời lượng bằng các nhãn ít biến động như family, productType, outcome và factoryVersion.
- **Distributed trace:** dùng span hoặc event theo trace hiện hành để nối một lần chọn factory với các bước tạo sản phẩm, khi hệ thống có tracing.

Không nên đưa `correlationId`, ID người dùng, ID đối tượng hoặc đường dẫn động vào **metric labels** vì số lượng tổ hợp nhãn (*cardinality*) sẽ tăng mạnh. Các ID theo request phù hợp với trace/log; metric nên dùng **nhãn hữu hạn, có giới hạn giá trị**.

## 5. Ví dụ Java hoàn chỉnh: decorator quan sát và kiểm tra biến thể

Ví dụ sử dụng **Light** và **Dark**, mỗi họ có Button và Checkbox. Có thêm interface `VariantTagged` để các concrete products công bố ID biến thể khi được tạo. Interface này phục vụ ví dụ kiểm chứng; nó **không được thêm vào Button hoặc Checkbox** nên giữ nguyên hợp đồng sản phẩm cơ bản.

Để tiện chạy, toàn bộ mã được đặt trong **một tệp Main.java**, dùng Java 8 trở lên, không cần thư viện ngoài. Lớp `DarkGuiFactory` có một tùy chọn mô phỏng lỗi tạo Checkbox để quan sát đường đi thất bại.

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class Main {
    // Abstract Products và Abstract Factory giữ API đơn giản.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    interface GuiFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Metadata bổ sung: concrete product công bố họ và biến thể thực tế.
    interface VariantTagged {
        String familyId();
        String variantId();
    }

    // Hai concrete products của họ Light.
    static final class LightButton implements Button, VariantTagged {
        public String render() {
            return "[Light] Button";
        }

        public String familyId() {
            return "light";
        }

        public String variantId() {
            return "light-button-v1";
        }
    }

    static final class LightCheckbox implements Checkbox, VariantTagged {
        public String render() {
            return "[Light] Checkbox";
        }

        public String familyId() {
            return "light";
        }

        public String variantId() {
            return "light-checkbox-v1";
        }
    }

    // Hai concrete products của họ Dark.
    static final class DarkButton implements Button, VariantTagged {
        public String render() {
            return "[Dark] Button";
        }

        public String familyId() {
            return "dark";
        }

        public String variantId() {
            return "dark-button-v1";
        }
    }

    static final class DarkCheckbox implements Checkbox, VariantTagged {
        public String render() {
            return "[Dark] Checkbox";
        }

        public String familyId() {
            return "dark";
        }

        public String variantId() {
            return "dark-checkbox-v1";
        }
    }

    // Concrete factories chỉ chịu trách nhiệm tạo sản phẩm.
    static final class LightGuiFactory implements GuiFactory {
        public Button createButton() {
            return new LightButton();
        }

        public Checkbox createCheckbox() {
            return new LightCheckbox();
        }
    }

    static final class DarkGuiFactory implements GuiFactory {
        private final boolean failCheckbox;

        DarkGuiFactory(boolean failCheckbox) {
            this.failCheckbox = failCheckbox;
        }

        public Button createButton() {
            return new DarkButton();
        }

        public Checkbox createCheckbox() {
            if (failCheckbox) {
                throw new IllegalStateException(
                        "Mô phỏng thiếu tài nguyên tạo DarkCheckbox");
            }
            return new DarkCheckbox();
        }
    }

    // Dữ liệu đăng ký, biết trước cả khi tạo sản phẩm thất bại.
    static final class FactoryDescriptor {
        final String familyId;
        final String factoryId;
        final String factoryVersion;
        final String buttonVariantId;
        final String checkboxVariantId;

        FactoryDescriptor(
                String familyId, String factoryId, String factoryVersion,
                String buttonVariantId, String checkboxVariantId) {
            this.familyId = Objects.requireNonNull(familyId);
            this.factoryId = Objects.requireNonNull(factoryId);
            this.factoryVersion = Objects.requireNonNull(factoryVersion);
            this.buttonVariantId = Objects.requireNonNull(buttonVariantId);
            this.checkboxVariantId = Objects.requireNonNull(checkboxVariantId);
        }
    }

    // Bản ghi theo dõi: tất cả các trường đều có kiểu rõ ràng.
    static final class CreationEvent {
        final String correlationId;
        final String familyId;
        final String factoryId;
        final String factoryVersion;
        final String productType;
        final String expectedVariant;
        final String actualVariant;
        final String outcome;
        final String errorKind;
        final long durationNanos;

        CreationEvent(
                String correlationId, FactoryDescriptor descriptor,
                String productType, String expectedVariant,
                String actualVariant, String outcome, String errorKind,
                long durationNanos) {
            this.correlationId = correlationId;
            this.familyId = descriptor.familyId;
            this.factoryId = descriptor.factoryId;
            this.factoryVersion = descriptor.factoryVersion;
            this.productType = productType;
            this.expectedVariant = expectedVariant;
            this.actualVariant = actualVariant;
            this.outcome = outcome;
            this.errorKind = errorKind;
            this.durationNanos = durationNanos;
        }
    }

    interface CreationTelemetry {
        void record(CreationEvent event);
    }

    // Demo dùng console; hệ thống thật có thể dùng log/metrics/tracing.
    static final class ConsoleTelemetry implements CreationTelemetry {
        @Override
        public void record(CreationEvent e) {
            System.out.println(
                    "CREATE outcome=" + e.outcome
                    + " correlation=" + e.correlationId
                    + " family=" + e.familyId
                    + " factory=" + e.factoryId
                    + " version=" + e.factoryVersion
                    + " product=" + e.productType
                    + " expected=" + e.expectedVariant
                    + " actual=" + e.actualVariant
                    + " duration_ns=" + e.durationNanos
                    + " error=" + e.errorKind);
        }
    }

    static final class FamilyMismatchException extends IllegalStateException {
        FamilyMismatchException(String message) {
            super(message);
        }
    }

    // Decorator: ghi nhận từng lời gọi tạo sản phẩm.
    static final class ObservingGuiFactory implements GuiFactory {
        private final GuiFactory delegate;
        private final FactoryDescriptor descriptor;
        private final CreationTelemetry telemetry;
        private final String correlationId;

        ObservingGuiFactory(
                GuiFactory delegate, FactoryDescriptor descriptor,
                CreationTelemetry telemetry, String correlationId) {
            this.delegate = Objects.requireNonNull(delegate, "delegate");
            this.descriptor = Objects.requireNonNull(
                    descriptor, "descriptor");
            this.telemetry = Objects.requireNonNull(telemetry, "telemetry");
            this.correlationId = Objects.requireNonNull(
                    correlationId, "correlationId");
        }

        @Override
        public Button createButton() {
            return observe(
                    "button", descriptor.buttonVariantId,
                    delegate::createButton);
        }

        @Override
        public Checkbox createCheckbox() {
            return observe(
                    "checkbox", descriptor.checkboxVariantId,
                    delegate::createCheckbox);
        }

        private <T> T observe(
                String type, String expectedVariant, Supplier<T> creation) {
            long startedAt = System.nanoTime();
            String actualVariant = "unknown";

            try {
                T product = Objects.requireNonNull(
                        creation.get(), "Factory trả null cho " + type);

                // Bài học áp dụng chính sách bắt buộc có metadata.
                if (!(product instanceof VariantTagged)) {
                    throw new IllegalStateException(
                            "Sản phẩm thiếu VariantTagged: " + type);
                }

                VariantTagged tagged = (VariantTagged) product;
                actualVariant = tagged.variantId();
                if (!descriptor.familyId.equals(tagged.familyId())
                        || !expectedVariant.equals(actualVariant)) {
                    throw new FamilyMismatchException(
                            "Sản phẩm không khớp họ/biến thể dự kiến: "
                                    + type);
                }

                publishSafely(new CreationEvent(
                        correlationId, descriptor, type, expectedVariant,
                        actualVariant, "success", "none",
                        elapsedSince(startedAt)));
                return product;
            } catch (RuntimeException failure) {
                publishSafely(new CreationEvent(
                        correlationId, descriptor, type, expectedVariant,
                        actualVariant, "failure", errorKind(failure),
                        elapsedSince(startedAt)));
                throw failure; // Giữ nguyên lỗi tạo sản phẩm cho caller.
            }
        }

        private static long elapsedSince(long startedAt) {
            return Math.max(0L, System.nanoTime() - startedAt);
        }

        private static String errorKind(RuntimeException failure) {
            if (failure instanceof FamilyMismatchException) {
                return "family_mismatch";
            }
            if (failure instanceof NullPointerException) {
                return "contract_null";
            }
            if (failure instanceof IllegalArgumentException) {
                return "invalid_configuration";
            }
            if (failure instanceof IllegalStateException) {
                return "invalid_state";
            }
            return "unexpected_runtime";
        }

        private void publishSafely(CreationEvent event) {
            try {
                telemetry.record(event);
            } catch (RuntimeException telemetryFailure) {
                // Telemetry không được che lỗi hoặc ngăn sản phẩm hợp lệ.
                System.err.println("WARN creation_telemetry_unavailable");
            }
        }
    }

    // Client chỉ dùng Abstract Factory và Abstract Products.
    static final class SettingsScreen {
        private final Button button;
        private final Checkbox checkbox;

        SettingsScreen(GuiFactory factory) {
            Objects.requireNonNull(factory, "factory");
            this.button = Objects.requireNonNull(
                    factory.createButton(), "button");
            this.checkbox = Objects.requireNonNull(
                    factory.createCheckbox(), "checkbox");
        }

        String render() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }
    }

    public static void main(String[] args) {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Cách dùng: java Main [light|dark] [fail]");
        }

        String theme = args.length == 0 ? "light" : args[0];
        boolean fail = args.length == 2;
        if (fail && !"fail".equalsIgnoreCase(args[1])) {
            throw new IllegalArgumentException("Chỉ hỗ trợ tùy chọn fail");
        }

        // Composition root chọn họ, metadata và telemetry.
        GuiFactory concrete;
        FactoryDescriptor descriptor;
        if ("light".equalsIgnoreCase(theme)) {
            if (fail) {
                throw new IllegalArgumentException(
                        "Chỉ hỗ trợ mô phỏng lỗi cho họ dark");
            }
            concrete = new LightGuiFactory();
            descriptor = new FactoryDescriptor(
                    "light", "light-gui", "1",
                    "light-button-v1", "light-checkbox-v1");
        } else if ("dark".equalsIgnoreCase(theme)) {
            concrete = new DarkGuiFactory(fail);
            descriptor = new FactoryDescriptor(
                    "dark", "dark-gui", "1",
                    "dark-button-v1", "dark-checkbox-v1");
        } else {
            throw new IllegalArgumentException(
                    "Chủ đề không được hỗ trợ: " + theme);
        }

        GuiFactory factory = new ObservingGuiFactory(
                concrete, descriptor, new ConsoleTelemetry(), "demo-001");
        SettingsScreen screen = new SettingsScreen(factory);
        System.out.println(screen.render());
    }
}
~~~

### Biên dịch và xem sự kiện thành công

Tạo một tệp `Main.java`, đặt nội dung Java trên vào tệp rồi dùng JDK 8 trở lên:

~~~text
javac -encoding UTF-8 Main.java
java Main dark
~~~

Đầu ra có dạng (giá trị `duration_ns` thay đổi giữa các lần chạy):

~~~text
CREATE outcome=success correlation=demo-001 family=dark factory=dark-gui version=1 product=button expected=dark-button-v1 actual=dark-button-v1 duration_ns=... error=none
CREATE outcome=success correlation=demo-001 family=dark factory=dark-gui version=1 product=checkbox expected=dark-checkbox-v1 actual=dark-checkbox-v1 duration_ns=... error=none
[Dark] Button
[Dark] Checkbox
~~~

Trong ví dụ, mỗi sản phẩm được tạo **một lần**, nên có hai sự kiện thành công. Nếu client gọi `createButton()` nhiều lần thì decorator cũng ghi nhiều sự kiện, phản ánh đúng số **lời gọi tạo** mà nó quan sát.

### Mô phỏng lỗi của một loại sản phẩm

~~~text
java Main dark fail
~~~

Đầu ra trước khi JVM in stack trace có dạng:

~~~text
CREATE outcome=success correlation=demo-001 family=dark factory=dark-gui version=1 product=button expected=dark-button-v1 actual=dark-button-v1 duration_ns=... error=none
CREATE outcome=failure correlation=demo-001 family=dark factory=dark-gui version=1 product=checkbox expected=dark-checkbox-v1 actual=unknown duration_ns=... error=invalid_state
~~~

Sau đó `IllegalStateException` ban đầu vẫn được ném ra; `SettingsScreen` **không được tạo hoàn chỉnh** và chương trình kết thúc bằng lỗi. Không có một DarkCheckbox thành công nên `actual=unknown` là thông tin chính xác hơn việc tự điền `dark-checkbox-v1`.

Trong ứng dụng thực, lỗi có thể được tầng gọi chuyển thành kết quả lỗi có cấu trúc hoặc xử lý theo chính sách khởi tạo. Điều quan trọng là decorator **không tự chuyển sang họ Light**, không trả đối tượng giả và không nuốt lỗi.

### Giới hạn của ví dụ

`VariantTagged` là một hợp đồng metadata bổ sung được các concrete products chủ động triển khai. Decorator trong ví dụ **bắt buộc** có metadata để kiểm tra họ và biến thể. Nếu làm việc với thư viện/SDK cũ không cung cấp metadata, bạn có thể chọn một chính sách khác: ghi `actual=unknown` và dựa vào thông tin factory đã đăng ký, hoặc dùng adapter để gắn metadata. Không nên ép một SDK vốn hợp lệ trở thành lỗi chỉ vì nó không biết interface `VariantTagged`, trừ khi đó là yêu cầu của hệ thống.

Ví dụ cũng không xuất một trace thực thụ hay histogram metric; `CreationTelemetry` chỉ là cổng tích hợp được mô phỏng bằng console. Khi tích hợp backend quan sát thực tế, nên giữ **cùng ngữ nghĩa sự kiện** và giới hạn những nhãn được phép xuất.

## 6. Phân loại lỗi theo nơi và nguyên nhân

Mọi lỗi có thể đều xuất hiện trong quá trình khởi tạo, nhưng không nên gom chúng thành một nhãn chung như `create_failed`.

| Điểm lỗi | Ví dụ | Cách theo dõi và xử lý |
| --- | --- | --- |
| **Chọn factory** | Giá trị `ui.theme` không có provider | Ghi lỗi ở composition root hoặc registry; báo cấu hình không hợp lệ |
| **Tạo factory** | Constructor cần khóa cấu hình hoặc tài nguyên chưa có | Ghi factory ID, phiên bản, nguyên nhân khởi tạo |
| **Tạo sản phẩm** | `createCheckbox()` ném lỗi | Ghi productType, họ đã chọn, biến thể kỳ vọng, thời lượng và nhóm lỗi |
| **Vi phạm hợp đồng** | Factory trả `null` hoặc sai loại sản phẩm | Fail-fast, ghi `contract_null` hoặc loại lỗi tương ứng |
| **Sai họ/biến thể** | Dark factory trả LightCheckbox | Ghi expected/actual, từ chối ghép bộ sản phẩm |
| **Dùng sản phẩm** | `render()` lỗi sau khi màn hình đã tạo | Theo dõi tại thao tác sử dụng, không tính nhầm thành lỗi tạo sản phẩm |

**Nguyên tắc quan sát:** ghi đúng ngữ cảnh tại nơi có bằng chứng tốt nhất, rồi **liên kết các sự kiện** bằng correlation ID hoặc trace ID. Không nên cố gắng giải quyết mọi loại lỗi bằng một câu lệnh log trong phương thức `main()`.

### Lỗi một phần và tài nguyên đã tạo

Giả sử Button đã tạo và chiếm tài nguyên native, nhưng Checkbox thất bại. Khi đó việc báo lỗi mới là bước đầu; ứng dụng còn phải xác định **ai dọn dẹp Button đã tạo**. Constructor `SettingsScreen` trong ví dụ chỉ giữ đối tượng đơn giản không sở hữu tài nguyên, nên không trình bày cleanup.

Với tài nguyên thật, cần một cơ chế quản lý vòng đời rõ ràng: tạo bộ sản phẩm trong một scope có `try/finally`, dùng `AutoCloseable` khi thích hợp, hoặc đưa trách nhiệm rollback/cleanup vào tầng lắp ghép. **Decorator ghi log không thay thế việc quản lý tài nguyên.**

### Có nên retry tự động?

Không nên retry mọi lỗi `createCheckbox()` theo mặc định. Nếu lỗi do cấu hình sai hoặc trộn họ, retry không sửa được nguyên nhân. Nếu lỗi do tài nguyên hạ tầng tạm thời, việc retry có thể hợp lý nhưng cần xét **tính idempotent** của thao tác tạo, giới hạn số lần, thời gian và tác động tài nguyên. Cơ chế retry nên nằm ở tầng có đủ ngữ cảnh nghiệp vụ, được theo dõi riêng để không nhầm **số lần thử tạo** với **số request**.

## 7. Metrics và tracing: dùng dữ liệu đúng mục đích

Một thiết kế quan sát thực tế có thể bắt đầu với một số metric rõ nghĩa:

| Metric ví dụ | Loại | Nhãn nên giữ hữu hạn |
| --- | --- | --- |
| `factory_product_creation_total` | Counter | `family`, `product_type`, `outcome`, `factory_version` |
| `factory_product_creation_duration_seconds` | Histogram | `family`, `product_type`, `outcome` |
| `factory_selection_failure_total` | Counter | `reason` hoặc `source` được chuẩn hóa |
| `factory_family_mismatch_total` | Counter | `family`, `product_type` |

Tên metric chỉ mang tính minh họa. Cần thống nhất đơn vị: `System.nanoTime()` dùng nanosecond cho phép đo khoảng thời gian; khi xuất histogram theo giây phải **đổi đơn vị đúng**, không đưa nguyên giá trị nanosecond vào metric mang hậu tố `_seconds`.

Một trace có thể chứa:

~~~text
request trace
  └─ select GUI family: dark
       └─ build SettingsScreen
            ├─ create button: dark-button-v1 [success]
            └─ create checkbox: dark-checkbox-v1 [failure]
~~~

Trong hệ thống có tracing, span phải có quan hệ cha/con và trạng thái lỗi phù hợp. `correlationId` đơn thuần chỉ là một nhãn dùng để liên kết; nó **không tự tạo distributed trace**.

### Ba cạm bẫy vận hành

1. **High cardinality:** gắn ID người dùng hoặc request vào metric làm tăng mạnh số chuỗi dữ liệu. Đưa các ID này vào log/trace theo chính sách riêng.
2. **Double counting:** vừa đo trong concrete factory vừa đo ở decorator có thể làm đếm trùng một lần tạo. Quy định rõ **ranh giới ghi metric**; nếu đo cả hai tầng, tên metric phải biểu đạt các thao tác khác nhau.
3. **Lệch ngữ nghĩa vì cache/pool:** nếu factory trả đối tượng từ cache, sự kiện ở decorator đo **lời gọi lấy sản phẩm**, chưa chắc đo một **lần cấp phát đối tượng mới**. Cần gọi tên metric/sự kiện đúng, hoặc bổ sung metadata `created` và `reused` nếu nghiệp vụ cần phân biệt.

## 8. Tránh để observability làm thay đổi hành vi nghiệp vụ

Trong Java demo, `publishSafely()` bắt lỗi `RuntimeException` từ telemetry rồi xuất một cảnh báo ngắn. Mục đích là ngăn sự cố hệ thống quan sát làm **mất kết quả hợp lệ** hoặc **che ngoại lệ gốc của factory**.

Trong hệ thống thực, còn cần quyết định:

- **Telemetry có được phép chặn thread gọi không?** Nếu backend log chậm, việc ghi đồng bộ ở đường đi tạo sản phẩm sẽ làm tăng độ trễ; có thể cần buffer hoặc cơ chế ghi bất đồng bộ có giới hạn.
- **Khi buffer đầy, ưu tiên nào?** Có thể giảm log thành công trước, giữ dấu hiệu lỗi, hoặc sử dụng bộ đệm riêng nhưng tránh gây nghẽn hệ thống chính.
- **Nếu telemetry tự lỗi, có phát hiện được không?** Cần số liệu hoặc kênh chẩn đoán phụ cho tình trạng mất telemetry, tránh vòng lặp báo lỗi vô hạn.
- **Khi người dùng yêu cầu thông tin debug, quyền truy cập thế nào?** Log có thể chứa topology nội bộ và tên nhà cung cấp. Áp dụng phân quyền và thời hạn lưu trữ.

Không nên tự động ghi `exception.getMessage()` vào metric label hoặc vào log công khai. Message có thể chứa nội dung động, đường dẫn, ID hoặc bí mật. Thay vào đó, dùng `errorKind` hữu hạn như `invalid_configuration`, `invalid_state`, `contract_null` và `family_mismatch`; chỉ lưu chi tiết ở kênh được kiểm soát khi thật sự cần.

**Lưu ý về bảo đảm tương thích:** việc so sánh `familyId` và `variantId` trong ví dụ chỉ xác nhận metadata mà đối tượng tự công bố. Một sản phẩm có thể khai báo đúng ID nhưng thực thi sai giao thức hoặc dùng phiên bản không tương thích. Các quy tắc đó vẫn cần được kiểm chứng bằng hợp đồng và kiểm thử tích hợp.

## 9. Khi nào dùng decorator, khi nào ghi ngay trong concrete factory?

| Cách đặt instrumentation | Phù hợp khi | Điểm đánh đổi |
| --- | --- | --- |
| **Decorator bao quanh GuiFactory** | Muốn theo dõi thống nhất các lời gọi tạo cho nhiều họ | Cần lắp ghép decorator đúng nơi; không thấy chi tiết bên trong phương thức tạo |
| **Instrumentation trong concrete factory** | Cần đo nhiều bước nội bộ như đọc tài nguyên, nạp SDK hoặc thương lượng giao thức | Dễ lặp logic và tạo phụ thuộc hạ tầng trong mỗi họ |
| **Quan sát tại registry/composition root** | Muốn biết cấu hình chọn họ, không tìm thấy provider hoặc lỗi tạo factory | Không tự theo dõi từng sản phẩm sau khi factory đã được tạo |
| **Theo dõi ở client hoặc sản phẩm** | Cần quan sát `render()`, `press()` hoặc hành vi nghiệp vụ sau khởi tạo | Không phản ánh đầy đủ lỗi xảy ra trước khi sản phẩm trả về |

Thông thường có thể kết hợp: **registry theo dõi lựa chọn**, **decorator theo dõi tạo sản phẩm**, còn những thao tác vận hành bên trong hoặc sau khi tạo được quan sát tại tầng phù hợp. Mỗi tầng nên có tên sự kiện và trách nhiệm rõ ràng để tránh ghi trùng.

### Không nên sửa public product interface chỉ để thêm log

Nếu `Button` hiện chỉ yêu cầu `render()`, việc bắt mọi implementation phải thêm `getVariantInfo()` có thể phá tương thích với plugin cũ. Trong ví dụ, `VariantTagged` là interface bổ sung để các concrete products chủ động triển khai; cũng có thể dùng metadata ở registry hoặc adapter.

**Quyết định cần dựa trên hợp đồng công khai:** nếu sản phẩm phải mang danh tính họ theo yêu cầu nghiệp vụ, metadata có thể là một phần hợp đồng chính thức. Nếu chỉ phục vụ vận hành, nên cân nhắc cách bổ sung mà không buộc mọi tác giả sản phẩm sửa API.

## 10. Kiểm thử và checklist trước khi vận hành

Để kiểm thử decorator, có thể cấp `CreationTelemetry` giả lưu các `CreationEvent` vào một danh sách rồi tạo màn hình:

~~~java
// Đặt lớp này trong Main.java của ví dụ hoặc trong test cùng package.
static final class RecordingTelemetry implements CreationTelemetry {
    final java.util.List<CreationEvent> events =
            new java.util.ArrayList<>();

    @Override
    public void record(CreationEvent event) {
        events.add(event);
    }
}
~~~

Ví dụ sử dụng trong một kiểm thử tuần tự: tạo một `ObservingGuiFactory` với `RecordingTelemetry`, gọi `createButton()` và `createCheckbox()`, sau đó xác nhận **hai sự kiện thành công**, đúng family, productType và biến thể; cho một factory lỗi để xác nhận **một sự kiện failure** và ngoại lệ gốc vẫn được ném. `ArrayList` ở ví dụ không bảo đảm thread safety khi nhiều thread cùng ghi.

Các tình huống nên kiểm tra:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Tạo Button và Checkbox cùng họ | Có đúng hai sự kiện success, ID họ và biến thể chính xác |
| `createCheckbox()` ném lỗi | Có event failure cho Checkbox; exception gốc vẫn đến caller |
| Factory trả `null` | Ghi `contract_null`; không công bố sản phẩm null như thành công |
| Factory trả biến thể khác họ | Ghi expected và actual; phát hiện `family_mismatch` |
| Telemetry ném `RuntimeException` | Kết quả tạo thành công hoặc lỗi gốc không bị thay thế bởi lỗi telemetry |
| Không tìm thấy tên factory | Lỗi được ghi ở bước chọn factory, dù decorator chưa tồn tại |
| Hai lời gọi tạo đồng thời | Sự kiện không trộn ngữ cảnh/correlation và sink phù hợp với concurrency |
| Mã dùng cache hoặc pool | Metric mô tả chính xác “gọi factory” hay “cấp phát instance mới” |

### Checklist thiết kế

- [ ] Sự kiện phân biệt **chọn factory**, **tạo sản phẩm** và **dùng sản phẩm**.
- [ ] Có **family ID, factory ID/version, productType, expected variant** khi tạo thất bại.
- [ ] Chỉ ghi **actual variant** khi có nguồn dữ liệu có thể kiểm chứng.
- [ ] Dùng **correlation/trace ID** ở đúng phạm vi request, không lưu nhầm vào singleton cho mọi người dùng.
- [ ] Không lộ bí mật hoặc dữ liệu cá nhân vào log; metric label có cardinality hữu hạn.
- [ ] Lỗi sản phẩm không bị telemetry che khuất; không có cơ chế fallback sang họ khác một cách âm thầm.
- [ ] Có chính sách lấy mẫu, quản lý độ trễ, xử lý mất telemetry và quyền truy cập log.
- [ ] Kiểm thử trường hợp factory tạo thành công một phần, sai họ và lỗi do plugin/SDK.

## 11. Bài tập vận dụng

**Bài A — Thêm một họ mới:** triển khai HighContrastButton, HighContrastCheckbox và HighContrastGuiFactory; cung cấp FactoryDescriptor với các ID biến thể phù hợp. Thay factory tại composition root và chứng minh SettingsScreen cũng như ObservingGuiFactory không cần sửa thuật toán.

**Bài B — Phát hiện trộn họ:** cố tình sửa DarkGuiFactory.createCheckbox() trả về LightCheckbox. Chạy ứng dụng và kiểm tra telemetry có `error=family_mismatch`, `expected=dark-checkbox-v1`, `actual=light-checkbox-v1`, trong khi client không nhận màn hình hợp lệ.

**Bài C — Mô phỏng mất telemetry:** tạo `CreationTelemetry` luôn ném `IllegalStateException`. Kiểm chứng việc gọi factory tạo sản phẩm thành công vẫn trả đúng sản phẩm và lỗi gốc từ factory vẫn được ném nếu concrete factory thất bại.

**Bài D — Thiết kế metric:** từ `CreationEvent`, đề xuất Counter và Histogram để đo tỷ lệ lỗi tạo theo họ và loại sản phẩm. Hãy liệt kê các nhãn sẽ dùng, giải thích vì sao không đưa correlationId vào nhãn metric.

**Bài E — Thêm tracing:** nối một lần chọn factory với hai lời gọi tạo sản phẩm bằng các span tương ứng. Giải thích khi nào tạo span mới, khi nào chỉ thêm event vào span đang có và làm thế nào giữ ID liên kết khi xử lý bất đồng bộ.

**Bài F — Phân biệt tạo với sử dụng:** giả sử DarkCheckbox.render() ném lỗi sau khi SettingsScreen đã tạo thành công. Hãy xác định sự kiện nào vẫn phải là success, lỗi nào được ghi ở tầng sử dụng sản phẩm và vì sao không nên tính lỗi render thành lỗi createCheckbox.

## 12. Ghi nhớ

- **Factory boundary** là nơi phù hợp để ghi nhận **loại sản phẩm, họ, biến thể, kết quả tạo và thời lượng**, kể cả khi quá trình tạo thất bại.
- **Family/variant ID dự kiến** được biết từ cấu hình hoặc đăng ký factory; **biến thể thực tế** chỉ được khẳng định khi có bằng chứng sau khi tạo.
- **Decorator triển khai cùng abstract factory interface** giúp đưa quan sát vào một nơi mà client và concrete product không phải biết backend logging.
- **Lỗi tạo sản phẩm phải được bảo toàn**, và telemetry cần có chính sách xử lý lỗi riêng; decorator không được âm thầm đổi họ hay nuốt lỗi.
- **Log, metric và trace phục vụ các mục đích khác nhau**; các trường động theo request phù hợp với log/trace, không nên đưa vào metric labels có số giá trị lớn.
- Theo dõi tạo sản phẩm **không thay thế** theo dõi chọn factory, vận hành của sản phẩm, dọn dẹp tài nguyên hoặc kiểm thử tương thích thực tế.

Khi tích hợp Abstract Factory vào hệ thống lớn, thông tin biến thể và lỗi được ghi **đúng tại điểm tạo** giúp xác định nhanh vấn đề thuộc cấu hình, factory hay concrete product. Thiết kế đó hiệu quả nhất khi giữ nguyên ranh giới phụ thuộc của Abstract Factory và làm rõ **điều đã được quan sát** so với **điều chỉ được kỳ vọng**.
