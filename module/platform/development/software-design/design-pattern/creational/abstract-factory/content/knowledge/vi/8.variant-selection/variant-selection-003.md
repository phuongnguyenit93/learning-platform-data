# Dùng enum và registry khi cần quản lý danh sách biến thể được hỗ trợ

> **Chương:** Lựa chọn biến thể  
> **Học phần:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Dùng `enum` để định danh biến thể một cách an toàn về kiểu, dùng *registry* để quản lý những biến thể thực sự có thể khởi tạo, và chọn đúng `AbstractFactory` trước khi tạo các sản phẩm cùng họ.

## 1. Bài toán: có nhiều biến thể, nhưng không phải biến thể nào cũng sẵn sàng

Giả sử ứng dụng desktop sử dụng mẫu **Abstract Factory** để cung cấp các thành phần giao diện theo hệ điều hành:

| Biến thể giao diện | Button | Checkbox | Factory |
| --- | --- | --- | --- |
| Windows | `WindowsButton` | `WindowsCheckbox` | `WindowsFactory` |
| macOS | `MacButton` | `MacCheckbox` | `MacFactory` |
| Linux (dự kiến) | `LinuxButton` | `LinuxCheckbox` | `LinuxFactory` |

Màn hình đăng nhập chỉ cần gọi:

~~~java
GUIFactory factory = /* factory được chọn tại điểm khởi động */;
Button button = factory.createButton();
Checkbox checkbox = factory.createCheckbox();
~~~

Khi một màn hình sử dụng **cùng một concrete factory**, Button và Checkbox đều thuộc một **họ sản phẩm**. Vấn đề tiếp theo là **chọn factory nào** khi ứng dụng chạy.

Trong phiên bản hiện tại, sản phẩm đã triển khai Windows và macOS nhưng **chưa** cung cấp Linux. Ứng dụng cần:

1. Nhận lựa chọn nền tảng từ cấu hình hoặc môi trường chạy.
2. Biết chính xác danh sách biến thể **đang được hỗ trợ**.
3. Chọn đúng concrete factory tương ứng với biến thể được yêu cầu.
4. Thông báo rõ ràng nếu biến thể chưa được hỗ trợ, thay vì âm thầm dùng factory khác.
5. Cho mã màn hình tiếp tục phụ thuộc vào `GUIFactory`, không tự lựa chọn lớp cụ thể.

Đó là tình huống phù hợp để kết hợp **enum + registry** tại điểm lắp ghép ứng dụng (*composition root*).

## 2. Phân biệt enum, registry và Abstract Factory

Ba thành phần giải quyết ba trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `enum Platform` | Định danh **những tên biến thể đã được biết trong mã nguồn** | `WINDOWS`, `MACOS`, `LINUX` |
| `FactoryRegistry` | Lưu ánh xạ từ biến thể đến cách tạo factory **đang được đăng ký** | `WINDOWS → WindowsFactory::new` |
| `GUIFactory` | Định nghĩa cách tạo **những loại sản phẩm cùng họ** | `createButton()`, `createCheckbox()` |

**Enum không đồng nghĩa với danh sách biến thể đã hỗ trợ.** Một giá trị `LINUX` có thể tồn tại trong enum để phục vụ lộ trình phát triển, nhưng nếu chưa có `LinuxFactory` hoàn chỉnh thì registry không nên cho phép chọn Linux.

Ngược lại, chỉ cần thêm `LinuxFactory` vào dự án cũng chưa có nghĩa ứng dụng đã sẵn sàng: điểm khởi động còn phải đăng ký và kiểm thử biến thể đó.

Ví dụ:

~~~java
enum Platform {
    WINDOWS,
    MACOS,
    LINUX
}
~~~

Enum giúp trình biên dịch kiểm tra giá trị trong miền xác định, dễ tích hợp với `switch` hoặc `EnumMap`, và tránh các lỗi chính tả như `"WINODWS"` khi chuyền chuỗi qua nhiều tầng mã. Tuy nhiên, enum là **tập tên được định nghĩa khi biên dịch**; muốn thêm một giá trị chưa từng có, thông thường phải sửa mã nguồn và triển khai lại ứng dụng.

## 3. Vì sao không chọn factory bằng điều kiện ở mỗi màn hình?

Một cách đơn giản là đặt điều kiện vào mã nghiệp vụ:

~~~java
GUIFactory factory;

if (platform == Platform.WINDOWS) {
    factory = new WindowsFactory();
} else {
    factory = new MacFactory();
}
~~~

Đoạn mã trên ẩn một lỗi chính sách: mọi giá trị khác `WINDOWS`, kể cả `LINUX`, đều bị coi là macOS. Ứng dụng có thể vẽ một giao diện sai mà không báo lỗi.

Một biến thể khác là viết `switch` trong nhiều màn hình. Dù mỗi `switch` có thể đúng, các vị trí ấy đều phải được cập nhật khi thêm hoặc bỏ hỗ trợ một hệ điều hành.

Cách tổ chức tốt hơn là:

- **Một điểm chọn** factory theo biến thể trong phần khởi tạo ứng dụng.
- **Một danh sách đăng ký** cho biết biến thể nào có factory hợp lệ.
- **Một hợp đồng chung** `GUIFactory` để mã màn hình không cần biết Windows hay macOS.

> Với ứng dụng nhỏ chỉ có vài biến thể cố định, **một hàm `switch` tập trung duy nhất** vẫn có thể đủ. Registry trở nên hữu ích khi cần truy vấn danh sách được hỗ trợ, cấu hình bật/tắt một phần biến thể, quản lý các factory provider, hoặc mở rộng cách đăng ký về sau.

## 4. Thiết kế luồng chọn biến thể

~~~mermaid
flowchart TD
    A["Cấu hình / hệ điều hành"] --> B["Chuyển đầu vào thành Platform"]
    B --> C["FactoryRegistry"]
    C --> D{"Có đăng ký biến thể?"}
    D -->|Có| E["Lấy factory provider"]
    E --> F["Tạo một GUIFactory"]
    F --> G["Truyền factory cho màn hình"]
    G --> H["createButton()"]
    G --> I["createCheckbox()"]
    D -->|Không| J["Báo biến thể chưa được hỗ trợ"]
~~~

Để bảo đảm các sản phẩm trong màn hình thuộc cùng một họ, **hãy chọn factory một lần** rồi truyền factory ấy vào màn hình. Không tra registry riêng lẻ mỗi khi tạo Button hoặc Checkbox; làm vậy dễ dẫn đến việc một phần giao diện dùng cấu hình mới trong khi phần khác còn dùng cấu hình cũ.

Các bất biến nên được duy trì:

~~~text
requestedPlatform phải có trong registeredPlatforms

selectedFactory = registry.createFactory(requestedPlatform)

button = selectedFactory.createButton()
checkbox = selectedFactory.createCheckbox()

family(button) = family(checkbox) = requestedPlatform
~~~

`family(...)` là ký hiệu diễn giải ràng buộc về cùng họ; không bắt buộc là phương thức có thật của sản phẩm. Mẫu Abstract Factory tạo ra điểm tập trung để thực hiện ràng buộc đó, còn đội phát triển phải bảo đảm mỗi concrete factory trả đúng sản phẩm của họ mình.

## 5. Lựa chọn cấu trúc dữ liệu: EnumMap và Supplier

Với khóa thuộc kiểu enum, Java có `EnumMap<Platform, ...>`. Đây là một lựa chọn tự nhiên cho ánh xạ từ `Platform` sang factory provider:

~~~java
Map<Platform, Supplier<GUIFactory>> providers =
        new EnumMap<>(Platform.class);

providers.put(Platform.WINDOWS, WindowsFactory::new);
providers.put(Platform.MACOS, MacFactory::new);
~~~

`Supplier<GUIFactory>` là giao diện hàm với phương thức `get()`. Với `WindowsFactory::new`, mỗi lần gọi `get()` sẽ tạo một `WindowsFactory` mới.

Điều đó giúp phân biệt hai thời điểm:

1. **Đăng ký**: khai báo cách tạo factory cho từng nền tảng khi ứng dụng khởi động.
2. **Lựa chọn**: khi đã biết nền tảng, gọi provider tương ứng để tạo factory cho màn hình hoặc phạm vi sử dụng.

Có thể lưu trực tiếp `Map<Platform, GUIFactory>` nếu factory không có trạng thái thay đổi và có chủ đích dùng chung một instance. Dùng `Supplier` có lợi khi cần khởi tạo theo nhu cầu, tạo instance riêng hoặc phối hợp với dependency injection. **Supplier không tự làm registry an toàn luồng**; trạng thái của các đối tượng được tạo vẫn phải được quản lý theo yêu cầu thực tế.

## 6. Ví dụ Java hoàn chỉnh: enum + registry + Abstract Factory

Ví dụ sau gồm một enum có ba tên biến thể, nhưng registry chỉ đăng ký hai factory đã sẵn sàng. Những sản phẩm GUI được mô phỏng bằng cách trả về chuỗi, nên không cần thư viện giao diện đồ họa để thấy kết quả.

Lưu toàn bộ mã vào `VariantSelectionDemo.java`:

~~~java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

public class VariantSelectionDemo {

    enum Platform {
        WINDOWS, MACOS, LINUX
    }

    // Các product interface
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    // Abstract Factory: tạo trọn một họ giao diện
    interface GUIFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    static final class WindowsButton implements Button {
        @Override
        public String render() {
            return "[Windows] Button";
        }
    }

    static final class WindowsCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[Windows] Checkbox";
        }
    }

    static final class MacButton implements Button {
        @Override
        public String render() {
            return "[macOS] Button";
        }
    }

    static final class MacCheckbox implements Checkbox {
        @Override
        public String render() {
            return "[macOS] Checkbox";
        }
    }

    static final class WindowsFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new WindowsButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new WindowsCheckbox();
        }
    }

    static final class MacFactory implements GUIFactory {
        @Override
        public Button createButton() {
            return new MacButton();
        }

        @Override
        public Checkbox createCheckbox() {
            return new MacCheckbox();
        }
    }

    static final class FactoryRegistry {
        private final EnumMap<Platform, Supplier<GUIFactory>> providers =
                new EnumMap<>(Platform.class);

        FactoryRegistry(Map<Platform, Supplier<GUIFactory>> registrations) {
            Objects.requireNonNull(registrations, "registrations");

            registrations.forEach((platform, supplier) -> {
                Objects.requireNonNull(platform, "platform");
                Objects.requireNonNull(supplier, "supplier");
                providers.put(platform, supplier);
            });

            if (providers.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one platform must be registered");
            }
        }

        // Trả về bản sao không thể chỉnh sửa từ bên ngoài.
        Set<Platform> supportedPlatforms() {
            return Collections.unmodifiableSet(
                    EnumSet.copyOf(providers.keySet()));
        }

        GUIFactory createFactory(Platform platform) {
            Objects.requireNonNull(platform, "platform");

            Supplier<GUIFactory> supplier = providers.get(platform);
            if (supplier == null) {
                throw new IllegalArgumentException(
                        "Unsupported platform: " + platform
                                + "; supported: " + supportedPlatforms());
            }

            return Objects.requireNonNull(
                    supplier.get(), "Factory provider returned null");
        }
    }

    // Composition root: chỉ đăng ký các biến thể đã có factory.
    static FactoryRegistry initializeRegistry() {
        Map<Platform, Supplier<GUIFactory>> registrations =
                new EnumMap<>(Platform.class);

        registrations.put(Platform.WINDOWS, WindowsFactory::new);
        registrations.put(Platform.MACOS, MacFactory::new);
        // LINUX chưa đăng ký vì chưa triển khai đầy đủ họ Linux.

        return new FactoryRegistry(registrations);
    }

    // Client chỉ biết Abstract Factory và product interface.
    static void showLoginScreen(GUIFactory factory) {
        Button loginButton = factory.createButton();
        Checkbox rememberLogin = factory.createCheckbox();

        System.out.println(loginButton.render());
        System.out.println(rememberLogin.render());
    }

    public static void main(String[] args) {
        FactoryRegistry registry = initializeRegistry();

        System.out.println("Supported: " + registry.supportedPlatforms());

        showLoginScreen(registry.createFactory(Platform.WINDOWS));
        showLoginScreen(registry.createFactory(Platform.MACOS));

        // Chủ động thử biến thể nằm trong enum nhưng chưa được hỗ trợ.
        try {
            registry.createFactory(Platform.LINUX);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Dùng JDK để biên dịch và chạy:

~~~bash
javac VariantSelectionDemo.java
java VariantSelectionDemo
~~~

Đầu ra dự kiến:

~~~text
Supported: [WINDOWS, MACOS]
[Windows] Button
[Windows] Checkbox
[macOS] Button
[macOS] Checkbox
Unsupported platform: LINUX; supported: [WINDOWS, MACOS]
~~~

Quan sát những điểm sau:

- `Platform.LINUX` là giá trị hợp lệ của **enum** nhưng **không có provider** trong registry.
- `supportedPlatforms()` trả về **danh sách thực sự được đăng ký**, không đơn thuần là `Platform.values()`.
- `createFactory()` trả về một `GUIFactory`; client không cần trực tiếp tạo `WindowsButton` hay `MacCheckbox`.
- Tất cả sản phẩm của mỗi lần gọi `showLoginScreen(...)` đến từ **một factory đã chọn**.
- Khi gặp biến thể không hỗ trợ, registry phát sinh lỗi có thông tin các lựa chọn hợp lệ. Đoạn `try/catch` trong `main` chỉ minh họa kết quả; ứng dụng thật có thể dừng khởi động hoặc hiển thị thông báo cấu hình phù hợp.

## 7. Chọn biến thể từ cấu hình bên ngoài

Thực tế, nền tảng có thể xuất phát từ file cấu hình, biến môi trường, đối số dòng lệnh hoặc lựa chọn người dùng. Những nguồn này thường cung cấp **chuỗi**, còn registry yêu cầu `Platform`.

Nên chuyển đổi và kiểm tra ở **ranh giới hệ thống**, trước khi trao enum cho phần còn lại của ứng dụng:

~~~java
import java.util.Locale;
import java.util.Objects;

static Platform parsePlatform(String raw) {
    Objects.requireNonNull(raw, "raw");

    try {
        return Platform.valueOf(
                raw.trim().toUpperCase(Locale.ROOT));
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Unknown platform name: " + raw, ex);
    }
}
~~~

Ví dụ:

~~~java
String raw = "windows"; // Lấy từ cấu hình
Platform requested = parsePlatform(raw);

FactoryRegistry registry = initializeRegistry();
GUIFactory factory = registry.createFactory(requested);
showLoginScreen(factory);
~~~

Ở đây có **hai loại lỗi** khác nhau cần thông báo rõ:

| Đầu vào | Bước xảy ra lỗi | Ý nghĩa |
| --- | --- | --- |
| `"winodws"` | `parsePlatform()` | Tên biến thể không thuộc enum |
| `"linux"` | `createFactory()` | Tên hợp lệ nhưng ứng dụng chưa đăng ký hỗ trợ |
| `"macos"` | Không có lỗi | Tên hợp lệ và đã đăng ký |
| `"windows"` | Không có lỗi | Tên hợp lệ và đã đăng ký |

Không nên tự động đổi một giá trị không hỗ trợ thành Windows hoặc macOS nếu sản phẩm chưa có chính sách *fallback* rõ ràng. Fallback ngầm có thể che giấu cấu hình sai và làm giao diện đi lệch kỳ vọng. Nếu cần fallback, hãy xác định cụ thể khi nào được dùng, hiển thị thông báo phù hợp và kiểm thử tình huống ấy.

### Vì sao nên truyền factory vào client?

Một màn hình không nhất thiết phải biết tên enum hoặc tra registry:

~~~java
final class LoginScreen {
    private final Button loginButton;
    private final Checkbox rememberLogin;

    LoginScreen(GUIFactory factory) {
        this.loginButton = factory.createButton();
        this.rememberLogin = factory.createCheckbox();
    }

    void show() {
        System.out.println(loginButton.render());
        System.out.println(rememberLogin.render());
    }
}
~~~

Điểm khởi động thực hiện việc lựa chọn **một lần**, sau đó truyền `GUIFactory` đến nơi cần dùng. Cách này giúp thay đổi cấu hình chọn biến thể mà không phải sửa mã hiển thị màn hình, đồng thời dễ thay factory giả khi kiểm thử.

## 8. Thêm hoặc tạm ngừng hỗ trợ biến thể

### Khi triển khai thêm Linux

Giả sử nhóm hoàn thành `LinuxButton`, `LinuxCheckbox` và `LinuxFactory`, trong đó các phương thức tạo đều trả về sản phẩm Linux. Thay đổi tại điểm đăng ký là:

~~~java
registrations.put(Platform.LINUX, LinuxFactory::new);
~~~

Nếu `LINUX` đã có trong enum, không cần thêm enum constant. Nhưng phải xác nhận **mọi loại sản phẩm** trong hợp đồng `GUIFactory` đã được `LinuxFactory` hiện thực và hoạt động đúng.

Với registry trên, `supportedPlatforms()` sẽ tự đưa Linux vào danh sách được hỗ trợ sau khi đăng ký. Client chỉ nhận `GUIFactory` nên không cần một nhánh mới để chọn từng Button hoặc Checkbox.

### Khi tạm ngừng hỗ trợ một biến thể

Nếu phiên bản phát hành hiện tại không cho phép Linux, đơn giản là **không đăng ký** `LINUX` trong bản registry đang triển khai. Enum vẫn có thể chứa giá trị đó; registry quyết định tập hợp sẵn sàng được sử dụng.

Đây cũng là lý do có thể cần hai khái niệm riêng:

- **Known variants:** tất cả giá trị của `Platform.values()`.
- **Supported variants:** khóa thực tế trong `FactoryRegistry.supportedPlatforms()`.

Một sản phẩm có nhiều bản phân phối hoặc tính năng được mở theo giai đoạn thường hưởng lợi từ sự tách biệt này.

### Registry nên bất biến sau khi khởi tạo

Trong ví dụ, constructor **sao chép các mục đăng ký** sang `EnumMap` nội bộ, và registry **không cung cấp phương thức công khai để thêm/xóa** sau đó. Vì vậy, mã bên ngoài không thể vô tình cập nhật bảng chọn factory khi màn hình đang chạy.

Nếu hệ thống thực sự cần thay đổi cấu hình hỗ trợ trong lúc chạy, phải thiết kế rõ việc chuyển đổi có tính nhất quán, đồng bộ truy cập và vòng đời những màn hình đã nhận factory cũ. Không nên tự động biến một registry đơn giản thành kho trạng thái toàn cục có thể sửa từ bất kỳ đâu.

## 9. Quy tắc đăng ký: đầy đủ, duy nhất và dễ chẩn đoán

Registry giúp tập trung việc chọn biến thể, nhưng còn ba yêu cầu cần kiểm tra khi khởi động.

**Thứ nhất, tính đầy đủ của họ:** mỗi provider phải trả về concrete factory tạo được **tất cả loại sản phẩm trong `GUIFactory`** thuộc đúng họ. Đăng ký `LinuxFactory` khi mới có LinuxButton nhưng chưa có LinuxCheckbox là chưa hoàn tất.

**Thứ hai, không đăng ký trùng:** nếu nhiều module cùng đóng góp provider, dùng `put(...)` có thể **ghi đè** provider cũ mà không cảnh báo. Khi thiết kế quy trình đăng ký động, có thể dùng:

~~~java
static void registerUnique(
        Map<Platform, Supplier<GUIFactory>> target,
        Platform platform,
        Supplier<GUIFactory> supplier) {
    Objects.requireNonNull(target);
    Objects.requireNonNull(platform);
    Objects.requireNonNull(supplier);

    if (target.putIfAbsent(platform, supplier) != null) {
        throw new IllegalStateException(
                "Duplicate platform registration: " + platform);
    }
}
~~~

Các lệnh `registrations.put(...)` trong ví dụ hoàn chỉnh ở mục 6 được viết cố định tại một chỗ và không bị trùng. Đoạn `registerUnique(...)` hữu ích hơn khi có nhiều nơi đăng ký hoặc cơ chế nạp provider.

**Thứ ba, lỗi phải có ngữ cảnh:** thông báo nên cho biết biến thể được yêu cầu và các biến thể được hỗ trợ. Có thể bổ sung mã lỗi hoặc hướng dẫn sửa cấu hình tùy ứng dụng. Không cần để người dùng cuối nhìn thấy tên lớp Java; thông tin kỹ thuật phù hợp hơn với log chẩn đoán.

### Không nhầm registry với Service Locator trong toàn bộ hệ thống

Registry chỉ nên phục vụ **lựa chọn phụ thuộc tại điểm khởi động hoặc cấu hình**. Nếu mọi màn hình gọi một registry toàn cục để lấy đối tượng tùy lúc, phụ thuộc của màn hình sẽ trở nên khó thấy, khó kiểm thử và khó xác định trạng thái biến thể nhất quán. Truyền `GUIFactory` qua constructor là hướng rõ ràng hơn.

## 10. Kiểm thử hành vi chọn biến thể

Cần kiểm thử **quy tắc đăng ký** và **sản phẩm cùng họ**. Với ví dụ ở mục 6, có thể bổ sung các phép kiểm tra sau trong một lớp kiểm thử hoặc trong mã thử nghiệm:

~~~java
FactoryRegistry registry = initializeRegistry();

if (!registry.supportedPlatforms().equals(
        EnumSet.of(Platform.WINDOWS, Platform.MACOS))) {
    throw new AssertionError("Unexpected supported variants");
}

GUIFactory windows = registry.createFactory(Platform.WINDOWS);
if (!(windows.createButton() instanceof WindowsButton)
        || !(windows.createCheckbox() instanceof WindowsCheckbox)) {
    throw new AssertionError("Windows factory mixes product families");
}

GUIFactory mac = registry.createFactory(Platform.MACOS);
if (!(mac.createButton() instanceof MacButton)
        || !(mac.createCheckbox() instanceof MacCheckbox)) {
    throw new AssertionError("macOS factory mixes product families");
}

try {
    registry.createFactory(Platform.LINUX);
    throw new AssertionError("LINUX should be unsupported");
} catch (IllegalArgumentException expected) {
    // Đúng kỳ vọng: LINUX có trong enum nhưng chưa đăng ký.
}
~~~

Những kiểm tra `instanceof` này phù hợp ở **kiểm thử các concrete factory**, nơi ta cố ý xác nhận họ sản phẩm. Mã client thông thường vẫn chỉ nên phụ thuộc vào các product interface.

Bộ tình huống kiểm thử tối thiểu:

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Chọn Windows | Factory Windows, Button/Checkbox thuộc Windows |
| Chọn macOS | Factory macOS, Button/Checkbox thuộc macOS |
| Yêu cầu Linux chưa đăng ký | Lỗi rõ ràng, không fallback ngầm |
| Đọc tên enum sai từ cấu hình | Báo tên biến thể không hợp lệ |
| Registry không có mục nào | Từ chối khởi tạo registry |
| Đăng ký trùng qua `registerUnique` | Báo lỗi tại thời điểm đăng ký |
| Thêm provider Linux đầy đủ | Danh sách hỗ trợ có Linux; client không đổi |

Có thể kiểm tra thêm việc `supportedPlatforms()` không cho phép mã bên ngoài sửa tập biến thể, và trường hợp một `Supplier` trả về `null` được phát hiện rõ ràng.

## 11. Giới hạn của enum + registry và lựa chọn thay thế

| Tình huống | Hướng tiếp cận phù hợp | Lưu ý |
| --- | --- | --- |
| Hai biến thể cố định, không cần liệt kê khả năng hỗ trợ | Một hàm `switch` tập trung | Đơn giản hơn registry |
| Nhiều giá trị enum, chỉ một số được triển khai trong bản phát hành | `EnumMap<Platform, Supplier<GUIFactory>>` | Tách rõ known và supported variants |
| Cần nạp provider ở lúc khởi động qua các module | Registry được xây từ danh sách provider có kiểm tra trùng | Vẫn cần quy tắc nhất quán cho cả họ |
| Plugin bên ngoài được phép tạo **tên biến thể hoàn toàn mới** mà lõi không biết trước | Khóa định danh mở, chẳng hạn chuỗi đã chuẩn hóa hoặc value object | Enum đóng không biểu diễn được giá trị mới nếu không sửa mã lõi |
| Chỉ thay màu, font và khoảng cách của cùng một bộ widget | Theme / stylesheet | Chưa chắc cần nhiều concrete factory |

Registry là **cơ chế tra cứu và lựa chọn**, không thay thế Abstract Factory. Sau khi registry chọn đúng `GUIFactory`, chính factory ấy vẫn phải tạo các Button, Checkbox và những loại sản phẩm khác **cùng một họ**.

Với plugin động thực sự, có thể dùng `ServiceLoader` hoặc cơ chế nạp module để tìm provider; tuy nhiên, nếu plugin có thể mang tên hoàn toàn mới thì enum được biên dịch sẵn có thể không phù hợp làm khóa duy nhất. Trước khi thiết kế cơ chế động, cần xác định khả năng mở rộng là **bật/tắt tập enum có sẵn** hay **thêm tên biến thể mới ở runtime**.

## 12. Bài tập vận dụng

**Bài 1 — Bổ sung Linux.** Triển khai `LinuxButton`, `LinuxCheckbox`, `LinuxFactory` trong ví dụ. Sau đó đăng ký `Platform.LINUX`, chạy lại chương trình và kiểm tra danh sách hỗ trợ cũng như đầu ra của cả hai sản phẩm Linux.

**Bài 2 — Cấu hình không hợp lệ.** Viết hàm nhận chuỗi `"macos"`, `"linux"` và `"maccos"`. Hãy phân biệt đầu vào hợp lệ/được hỗ trợ, hợp lệ/chưa hỗ trợ và không phải tên enum hợp lệ. Tránh tự đổi tất cả lỗi sang Windows.

**Bài 3 — Phát hiện đăng ký trùng.** Thay các lệnh `put` trong giai đoạn khởi tạo bằng `registerUnique`. Thử đăng ký hai provider cho `WINDOWS` và giải thích vì sao phát hiện lỗi sớm tốt hơn ghi đè im lặng.

**Bài 4 — Đặt đúng trách nhiệm.** Có hai thiết kế:

~~~text
A. LoginScreen nhận Platform, tự tra Registry toàn cục
   rồi tạo Button và Checkbox.

B. Điểm khởi động tra Registry một lần,
   truyền GUIFactory vào LoginScreen qua constructor.
~~~

Thiết kế **B** thường phù hợp hơn khi muốn làm rõ phụ thuộc và duy trì một họ giao diện ổn định trong màn hình. Hãy mô tả trường hợp ngoại lệ mà thiết kế A có thể vẫn được chủ động chọn, và cách kiểm soát việc thay đổi nền tảng giữa lúc màn hình đang tồn tại.

### Câu hỏi tự kiểm tra

1. Vì sao `Platform.values()` không phải lúc nào cũng là danh sách biến thể được hỗ trợ?
2. Tại sao registry chỉ nên trả về `GUIFactory`, không trả riêng các sản phẩm Button và Checkbox do nhiều nguồn lựa chọn?
3. `EnumMap` và `Supplier` đóng vai trò gì?
4. Điều gì xảy ra khi tên biến thể hợp lệ nhưng không có factory được đăng ký?
5. Khi nào enum trở thành giới hạn đối với hệ sinh thái plugin?
6. Vì sao giữ registry ở điểm khởi động và tiêm factory vào client giúp việc kiểm thử dễ hơn?

**Ghi nhớ:** **enum** mô tả miền tên biến thể được biết trong mã, **registry** mô tả tập biến thể **đã sẵn sàng để chọn**, còn **Abstract Factory** bảo đảm cách tạo một họ sản phẩm thống nhất sau khi lựa chọn. Tách ba trách nhiệm này giúp quản lý biến thể minh bạch, báo lỗi đúng chỗ và giữ mã màn hình tập trung vào hành vi của nó.

