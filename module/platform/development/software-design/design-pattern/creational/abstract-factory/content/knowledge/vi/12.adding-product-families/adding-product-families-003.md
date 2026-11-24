# Đăng ký factory mới trong cấu hình hoặc cơ chế khám phá biến thể

Khi một ứng dụng đã dùng **Abstract Factory** để tạo các bộ sản phẩm tương thích, việc viết thêm một concrete factory mới chỉ là một phần của công việc. Ứng dụng còn phải **biết factory đó tồn tại** và **chọn được nó khi chạy**. Bài học thuộc chương **Thêm họ sản phẩm** này giải thích hai cách tổ chức việc đó trong Java: đăng ký tường minh vào một **factory registry** rồi chọn bằng cấu hình, hoặc khám phá các factory có sẵn qua **Java ServiceLoader**.

Ví dụ xuyên suốt là ứng dụng có hai loại sản phẩm **Button** và **Checkbox**. Ban đầu ứng dụng hỗ trợ hai họ giao diện **Light** và **Dark**. Sau đó, ta thêm họ **High Contrast** để phục vụ nhu cầu tương phản cao mà không phải thay đổi mã sử dụng sản phẩm.

## 1. Phân biệt ba việc: hiện thực, đăng ký và lựa chọn

Khi thêm một họ sản phẩm, cần tách biệt ba công việc thường bị gộp lại:

| Công việc | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Hiện thực (implementation)** | Họ mới tạo ra những sản phẩm nào? | HighContrastThemeFactory tạo HighContrastButton và HighContrastCheckbox |
| **Đăng ký (registration)** | Hệ thống tìm thấy cách tạo họ đó ở đâu? | Ánh xạ khóa high-contrast đến nhà cung cấp factory |
| **Lựa chọn (selection)** | Lần chạy này dùng họ nào? | Cấu hình ui.theme=high-contrast |

**Đăng ký không đồng nghĩa với lựa chọn.** Đăng ký ba họ Light, Dark và High Contrast chỉ cho biết ứng dụng **có thể** tạo cả ba; giá trị cấu hình xác định **họ nào được dùng** cho một màn hình cụ thể.

Ma trận sản phẩm giữ nguyên logic của Abstract Factory:

| Họ / Loại | Button | Checkbox | Factory |
| --- | --- | --- | --- |
| Light | LightButton | LightCheckbox | LightThemeFactory |
| Dark | DarkButton | DarkCheckbox | DarkThemeFactory |
| High Contrast | HighContrastButton | HighContrastCheckbox | HighContrastThemeFactory |

Client chỉ làm việc qua các interface **Button**, **Checkbox** và **ThemeFactory**. Registry hoặc cơ chế khám phá nằm ở **composition root** (vị trí lắp ghép các phụ thuộc), nơi ứng dụng được phép biết các lớp triển khai và quy tắc cấu hình.

### Luồng khởi tạo

~~~mermaid
flowchart LR
    A["Cấu hình: ui.theme"] --> B["Chọn khóa họ sản phẩm"]
    C["Đăng ký tường minh"] --> R["ThemeFactoryRegistry"]
    D["ServiceLoader"] --> R
    B --> R
    R --> F["ThemeFactory đã chọn"]
    F --> P1["Button tương ứng"]
    F --> P2["Checkbox tương ứng"]
    P1 --> U["SettingsPanel"]
    P2 --> U
~~~

**Điểm thiết kế quan trọng:** nhánh *đăng ký* có thể dùng cách tường minh hoặc khám phá tự động, trong khi mã **SettingsPanel** và hợp đồng **ThemeFactory** vẫn giữ nguyên.

## 2. Đăng ký tường minh bằng Factory Registry

**Factory Registry** là bảng ánh xạ từ **khóa nhận diện họ** đến **cách tạo concrete factory**. Khóa có thể là light, dark hoặc high-contrast. Thay vì truyền tên lớp Java trong cấu hình, ta dùng khóa có ý nghĩa với người vận hành và kiểm soát các factory hợp lệ ngay khi khởi động.

Một registry nên có ít nhất ba quy tắc:

1. **Không chấp nhận khóa rỗng hoặc sai định dạng.** Có thể chuẩn hóa khoảng trắng và chữ hoa/chữ thường ở một vị trí.
2. **Từ chối đăng ký trùng khóa.** Hai nhà cung cấp cùng tự nhận high-contrast sẽ tạo ra kết quả không rõ ràng nếu âm thầm ghi đè.
3. **Báo lỗi rõ khi chọn khóa không tồn tại.** Tránh lặng lẽ trả về Light khi người dùng yêu cầu Dark và khiến cấu hình sai khó phát hiện.

### 2.1. Ví dụ Java hoàn chỉnh

Để chạy độc lập, ví dụ sau đặt các interface và lớp lồng nhau trong một tệp **Main.java**. Trong dự án thực tế, có thể tách chúng thành các tệp và package theo từng trách nhiệm.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public class Main {
    // Hai loại sản phẩm trừu tượng.
    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }

    // Abstract Factory: tạo một bộ sản phẩm theo cùng chủ đề.
    interface ThemeFactory {
        Button createButton();
        Checkbox createCheckbox();
    }

    // Họ Light.
    static final class LightButton implements Button {
        public String render() {
            return "[Light] Button";
        }
    }

    static final class LightCheckbox implements Checkbox {
        public String render() {
            return "[Light] Checkbox";
        }
    }

    static final class LightThemeFactory implements ThemeFactory {
        public Button createButton() {
            return new LightButton();
        }

        public Checkbox createCheckbox() {
            return new LightCheckbox();
        }
    }

    // Họ Dark.
    static final class DarkButton implements Button {
        public String render() {
            return "[Dark] Button";
        }
    }

    static final class DarkCheckbox implements Checkbox {
        public String render() {
            return "[Dark] Checkbox";
        }
    }

    static final class DarkThemeFactory implements ThemeFactory {
        public Button createButton() {
            return new DarkButton();
        }

        public Checkbox createCheckbox() {
            return new DarkCheckbox();
        }
    }

    // Họ mới: High Contrast.
    static final class HighContrastButton implements Button {
        public String render() {
            return "[High Contrast] Button";
        }
    }

    static final class HighContrastCheckbox implements Checkbox {
        public String render() {
            return "[High Contrast] Checkbox";
        }
    }

    static final class HighContrastThemeFactory implements ThemeFactory {
        public Button createButton() {
            return new HighContrastButton();
        }

        public Checkbox createCheckbox() {
            return new HighContrastCheckbox();
        }
    }

    // Registry lưu cách tạo factory, chưa cần tạo sẵn mọi factory.
    static final class ThemeFactoryRegistry {
        private final Map<String, Supplier<? extends ThemeFactory>>
                registrations = new LinkedHashMap<>();

        void register(String id, Supplier<? extends ThemeFactory> supplier) {
            String key = normalize(id);
            Objects.requireNonNull(supplier, "Factory supplier không được null");

            if (registrations.putIfAbsent(key, supplier) != null) {
                throw new IllegalStateException(
                        "Trùng khóa factory: " + key);
            }
        }

        ThemeFactory create(String id) {
            String key = normalize(id);
            Supplier<? extends ThemeFactory> supplier = registrations.get(key);

            if (supplier == null) {
                throw new IllegalArgumentException(
                        "Không có họ '" + key + "'. Các họ hỗ trợ: "
                                + registrations.keySet());
            }

            return Objects.requireNonNull(
                    supplier.get(), "Factory đã đăng ký trả về null: " + key);
        }

        private static String normalize(String id) {
            if (id == null) {
                throw new IllegalArgumentException("Khóa factory là null");
            }
            String key = id.trim().toLowerCase(Locale.ROOT);
            if (!key.matches("[a-z][a-z0-9-]*")) {
                throw new IllegalArgumentException(
                        "Khóa factory không hợp lệ: " + id);
            }
            return key;
        }
    }

    // Client không biết concrete factory hoặc concrete product.
    static final class SettingsPanel {
        private final Button button;
        private final Checkbox checkbox;

        SettingsPanel(ThemeFactory factory) {
            Objects.requireNonNull(factory, "factory");
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();
        }

        String show() {
            return button.render() + System.lineSeparator()
                    + checkbox.render();
        }
    }

    public static void main(String[] args) {
        ThemeFactoryRegistry registry = new ThemeFactoryRegistry();

        // ĐĂNG KÝ: có thể tạo được ba họ.
        registry.register("light", LightThemeFactory::new);
        registry.register("dark", DarkThemeFactory::new);
        registry.register("high-contrast", HighContrastThemeFactory::new);

        // LỰA CHỌN: đổi cấu hình mà không sửa SettingsPanel.
        String selected = System.getProperty("ui.theme", "light");
        ThemeFactory factory = registry.create(selected);

        System.out.println(new SettingsPanel(factory).show());
    }
}
~~~

Ví dụ chỉ dùng các tính năng có từ **Java 8**. Biên dịch bằng JDK có hỗ trợ UTF-8:

~~~text
javac -encoding UTF-8 Main.java
java Main
[Light] Button
[Light] Checkbox

java -Dui.theme=dark Main
[Dark] Button
[Dark] Checkbox

java -Dui.theme=high-contrast Main
[High Contrast] Button
[High Contrast] Checkbox
~~~

Lệnh với tham số hệ thống **-Dui.theme=high-contrast** chứng minh ứng dụng đã đăng ký họ mới và có thể chọn nó bằng cấu hình, trong khi **SettingsPanel** không có điều kiện if/else cho ba chủ đề.

### 2.2. Vì sao registry lưu Supplier thay vì factory instance?

Một **Supplier** mô tả cách tạo factory khi cần. Cách này hữu ích khi factory có cấu hình hoặc vòng đời riêng: registry không phải khởi tạo tất cả factory lúc đăng ký. Trong ví dụ, cú pháp **HighContrastThemeFactory::new** là tham chiếu đến constructor, tương đương một hàm không tham số trả về instance mới.

Đây là **lựa chọn thiết kế**, không phải yêu cầu bắt buộc của Abstract Factory. Nếu factory bất biến và dùng chung được, registry có thể giữ instance thay vì Supplier. Khi factory quản lý tài nguyên đắt tiền như kết nối, cần thiết kế vòng đời và đóng tài nguyên đúng cách; một registry đơn giản không tự giải quyết vấn đề đó.

### 2.3. Cách thêm một họ mới bằng đăng ký tường minh

Giả sử sau này có một họ **Sepia** (tông nâu):

1. Tạo **SepiaButton** và **SepiaCheckbox**, triển khai hai interface sản phẩm sẵn có.
2. Tạo **SepiaThemeFactory** triển khai đầy đủ createButton() và createCheckbox().
3. Đăng ký khóa tại composition root:

~~~java
registry.register("sepia", SepiaThemeFactory::new);
~~~

4. Chọn họ mới qua cấu hình:

~~~text
java -Dui.theme=sepia Main
~~~

Lúc này không cần sửa **ThemeFactory**, **Button**, **Checkbox** hoặc **SettingsPanel**. Phần phải thay đổi là mã của họ mới, nơi đăng ký và khâu đóng gói/triển khai. Nếu các loại sản phẩm ban đầu không đủ để mô tả họ mới, bài toán không còn đơn thuần là *thêm họ*; cần cân nhắc thay đổi hợp đồng.

## 3. Lấy lựa chọn factory từ tệp cấu hình

Ví dụ trên dùng Java system property để tập trung vào đăng ký. Trong ứng dụng triển khai thực tế, người vận hành có thể dùng một tệp cấu hình:

~~~properties
# ui.properties
ui.theme=high-contrast
~~~

Có thể thay đoạn đọc **System.getProperty** trong Main bằng cách tải **Properties**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Properties;

Properties settings = new Properties();
try (InputStream input = Files.newInputStream(Paths.get("ui.properties"))) {
    settings.load(input);
}

String selected = settings.getProperty("ui.theme", "light");
ThemeFactory factory = registry.create(selected);
~~~

Đây là **đoạn thay thế ở vị trí chọn factory**, không phải chương trình độc lập. Khi dùng cách này, tệp **ui.properties** phải tồn tại tại đường dẫn ứng dụng mong đợi; nếu không tìm thấy, thao tác mở tệp ném IOException và cần xử lý theo chính sách khởi động của hệ thống.

Nên phân biệt rõ:

- **Danh sách factory đăng ký:** xác định **những họ ứng dụng có thể cung cấp**.
- **Giá trị ui.theme:** xác định **họ đang được yêu cầu** trong lần chạy hiện tại.
- **Các tệp JAR đã đóng gói:** xác định **lớp hiện thực có thực sự được cung cấp** để tạo instance hay không.

Nếu đặt ui.theme=sepia mà chưa đăng ký SepiaThemeFactory, registry sẽ **báo lỗi khóa không tồn tại**. Chỉ sửa tệp cấu hình không làm một lớp Java hoặc một plugin chưa tồn tại tự xuất hiện.

### Đăng ký từ cấu hình và sự đánh đổi của reflection

Một số hệ thống muốn khai báo trực tiếp cả ánh xạ **khóa → tên lớp** trong tệp cấu hình, ví dụ:

~~~properties
ui.theme=sepia
theme.factory.sepia=com.example.theme.SepiaThemeFactory
~~~

Để thực sự hỗ trợ cách này, ứng dụng cần một bộ nạp đọc tiền tố **theme.factory.**, tải lớp tương ứng, kiểm tra lớp đó triển khai **ThemeFactory**, tạo instance (hoặc supplier) và đưa vào registry. Trong Java, bộ nạp thường dùng reflection như **Class.forName**, **asSubclass** và **getDeclaredConstructor**. Ví dụ trên là **định dạng cấu hình dự kiến**, không phải một tính năng của chương trình Main đã viết ở mục 2.

Cách tiếp cận qua tên lớp có các chi phí cần xét:

- Tên lớp là chi tiết triển khai bị đưa vào cấu hình, dễ sai khi đổi package hoặc tên lớp.
- Lớp phải có mặt trong classpath/module path và phải đáp ứng quy ước khởi tạo.
- Lỗi có thể xuất hiện muộn khi khởi động do tên lớp sai, constructor không truy cập được hoặc dependency thiếu.
- Nếu nguồn cấu hình không đáng tin cậy, việc tự động nạp một lớp bất kỳ là rủi ro đáng kể.

Với dự án nhỏ hoặc số họ hữu hạn, **đăng ký tường minh** thường dễ đọc và dễ kiểm soát hơn. Nếu yêu cầu thực sự là nạp các họ được phát triển và đóng gói thành plugin độc lập, có thể dùng cơ chế **ServiceLoader** của Java.

## 4. Khám phá factory bằng Java ServiceLoader

**ServiceLoader** là cơ chế SPI (*Service Provider Interface*) có sẵn trong Java. Thay vì ứng dụng phải biết từng lớp triển khai, các plugin **công bố nhà cung cấp** của một interface. Ứng dụng gọi ServiceLoader để tìm những nhà cung cấp có mặt trên đường nạp lớp hoặc đường module.

ServiceLoader không tìm bằng cách quét tất cả lớp xem tên có đuôi Factory hay không. Nó dựa trên **đăng ký provider hợp lệ**: thông thường là tệp dịch vụ trong **META-INF/services** khi chạy bằng classpath, hoặc khai báo **provides ... with ...** khi chạy với Java Platform Module System (JPMS).

### 4.1. Thiết kế Service Provider Interface

Khác với ThemeFactory (tạo **Button** và **Checkbox**), một **ThemeFactoryProvider** công bố **ID của họ** và biết cách **tạo ThemeFactory**. Tách hai hợp đồng giúp ứng dụng khám phá từng plugin mà không buộc các concrete factory trực tiếp cung cấp metadata về đăng ký.

Khi tách thành dự án plugin thực tế, **Button**, **Checkbox**, **ThemeFactory** và **ThemeFactoryProvider** nên là các interface **public top-level**, nằm trong một API JAR chung. Chẳng hạn trong package **demo.api**:

~~~java
// File: demo/api/ThemeFactoryProvider.java
package demo.api;

public interface ThemeFactoryProvider {
    String id();
    ThemeFactory createFactory();
}
~~~

Các interface sản phẩm và abstract factory của API chung có thể khai báo như sau:

~~~java
// File: demo/api/Button.java
package demo.api;
public interface Button {
    String render();
}

// File: demo/api/Checkbox.java
package demo.api;
public interface Checkbox {
    String render();
}

// File: demo/api/ThemeFactory.java
package demo.api;
public interface ThemeFactory {
    Button createButton();
    Checkbox createCheckbox();
}
~~~

**Chú ý:** ba khai báo public trên là nội dung của **ba tệp Java riêng biệt** được ghi tên trong comment, không được chép nguyên cả ba vào một tệp Java. Các interface này đảm bảo phía ứng dụng và các plugin cùng dùng một hợp đồng nhị phân nhất quán.

### 4.2. Tạo provider cho họ High Contrast

Trong plugin, triển khai ThemeFactory và một provider công khai:

~~~java
// File: demo/highcontrast/HighContrastThemeFactory.java
package demo.highcontrast;

import demo.api.Button;
import demo.api.Checkbox;
import demo.api.ThemeFactory;

public final class HighContrastThemeFactory implements ThemeFactory {
    @Override
    public Button createButton() {
        return () -> "[High Contrast] Button";
    }

    @Override
    public Checkbox createCheckbox() {
        return () -> "[High Contrast] Checkbox";
    }
}
~~~

~~~java
// File: demo/highcontrast/HighContrastProvider.java
package demo.highcontrast;

import demo.api.ThemeFactory;
import demo.api.ThemeFactoryProvider;

public final class HighContrastProvider implements ThemeFactoryProvider {
    public HighContrastProvider() {
        // Constructor public, không tham số cho classpath ServiceLoader.
    }

    @Override
    public String id() {
        return "high-contrast";
    }

    @Override
    public ThemeFactory createFactory() {
        return new HighContrastThemeFactory();
    }
}
~~~

Provider này là đối tượng được ServiceLoader khám phá. **HighContrastThemeFactory** vẫn là concrete factory tuân theo mẫu Abstract Factory; provider chỉ đảm nhiệm vai trò **đưa factory vào danh sách khả dụng**.

### 4.3. Khai báo provider khi dùng classpath

Trong plugin JAR, thêm tệp tài nguyên có đường dẫn chính xác:

~~~text
META-INF/services/demo.api.ThemeFactoryProvider
~~~

Nội dung tệp là **tên đầy đủ của lớp provider**, mỗi dòng một tên:

~~~text
demo.highcontrast.HighContrastProvider
~~~

Tệp này phải được **đóng gói vào plugin JAR**. Đặt tên sai package của interface, sai tên lớp provider hoặc bỏ sót resource khi build đều có thể khiến ServiceLoader không tìm thấy provider. Trên classpath, provider cần là lớp triển khai hợp lệ và có constructor public không tham số để ServiceLoader có thể khởi tạo theo quy ước thông thường.

### 4.4. Đưa provider được khám phá vào registry

Ứng dụng có thể giữ các họ cốt lõi ở phần đăng ký tường minh, rồi thêm các họ từ plugin:

~~~java
// Đoạn minh họa tại composition root.
// ThemeFactoryRegistry có API register(id, supplier) như mục 2;
// các lớp và SPI ở đây phải được tách ra thành kiểu public dùng chung.
ThemeFactoryRegistry registry = new ThemeFactoryRegistry();
registry.register("light", LightThemeFactory::new);
registry.register("dark", DarkThemeFactory::new);

for (ThemeFactoryProvider provider
        : java.util.ServiceLoader.load(ThemeFactoryProvider.class)) {
    registry.register(provider.id(), provider::createFactory);
}

String selected = System.getProperty("ui.theme", "light");
ThemeFactory factory = registry.create(selected);
SettingsPanel panel = new SettingsPanel(factory);
~~~

Đây là **đoạn mã lắp ghép** cho kiến trúc nhiều JAR, không thay thế trực tiếp Main.java một tệp của mục 2 nếu chưa tách các interface/registry thành kiểu dùng chung. Với plugin HighContrastProvider được đóng gói đúng và có mặt khi chạy, registry sẽ nhận thêm khóa **high-contrast**; SettingsPanel và mã duyệt registry không phải biết tên lớp HighContrastThemeFactory.

Việc **khám phá** và việc **lựa chọn** vẫn độc lập: có plugin không có nghĩa hệ thống bắt buộc dùng plugin đó. Cấu hình chỉ chọn high-contrast khi người vận hành yêu cầu.

### 4.5. Dùng ServiceLoader với Java Module System

Nếu ứng dụng dùng **JPMS** (module-info.java), thay cho tệp META-INF/services ở classpath, module ứng dụng khai báo **uses**, còn module chứa plugin khai báo **provides**:

~~~java
// module-info.java của ứng dụng
module demo.app {
    requires demo.api;
    uses demo.api.ThemeFactoryProvider;
}
~~~

~~~java
// module-info.java của plugin High Contrast
module demo.highcontrast {
    requires demo.api;
    provides demo.api.ThemeFactoryProvider
            with demo.highcontrast.HighContrastProvider;
}
~~~

Module **demo.api** phải export package **demo.api** để ứng dụng và plugin sử dụng được các interface. Ứng dụng chạy theo module path cần cấu hình/module resolution phù hợp để provider module được nhìn thấy. Đây là cơ chế đăng ký của JPMS; không nên giả định chỉ đưa một JAR lên ổ đĩa là ServiceLoader tự nạp nó.

## 5. So sánh đăng ký tường minh và khám phá tự động

| Tiêu chí | Registry đăng ký tường minh | ServiceLoader khám phá provider |
| --- | --- | --- |
| **Thêm họ mới** | Thêm sản phẩm, concrete factory và một dòng đăng ký tại composition root | Phát triển provider, khai báo dịch vụ/module và đóng gói plugin |
| **Phụ thuộc lúc biên dịch** | Mã đăng ký thường tham chiếu lớp factory cụ thể | Ứng dụng chỉ cần SPI; plugin phụ thuộc vào API chung |
| **Cách chọn họ** | Dùng khóa cấu hình đã đăng ký | Vẫn dùng khóa cấu hình sau khi khám phá provider |
| **Độ đơn giản** | Dễ đọc, dễ lần theo việc khởi tạo | Nhiều yếu tố hơn: classpath/module path, resource, phiên bản SPI |
| **Khả năng mở rộng bằng JAR mới** | Thường cần cập nhật mã lắp ghép và đóng gói lại ứng dụng | Có thể thêm plugin tương thích mà không sửa mã ứng dụng, nếu cơ chế đóng gói/nạp hỗ trợ |
| **Khả năng phát hiện lỗi** | Nhiều lỗi lộ ngay trong quá trình biên dịch | Một số lỗi chỉ xuất hiện khi tìm và tạo provider lúc chạy |
| **Kiểm soát nhà cung cấp** | Danh sách được chọn tường minh | Cần kiểm soát plugin nào hiện diện và được phép đăng ký |

**Gợi ý lựa chọn:** ứng dụng chỉ có vài chủ đề được phát triển cùng nhau thường phù hợp với registry tường minh. Nền tảng mở rộng bằng plugin do nhiều nhóm phát triển có thể hưởng lợi từ ServiceLoader, với điều kiện có quy ước rõ về SPI, phiên bản, đóng gói và xử lý lỗi.

## 6. Các lỗi cần dự liệu khi thêm họ sản phẩm

### 6.1. Khóa trùng, sai hoặc thiếu

Nếu hai provider cùng công bố **id=dark**, việc âm thầm ghi đè tạo ra hành vi phụ thuộc thứ tự nạp. **Không nên dựa vào thứ tự khám phá của ServiceLoader** để chọn factory mặc định. Registry ở mục 2 từ chối khóa trùng, và khi lựa chọn một khóa chưa đăng ký, nó báo danh sách khóa hợp lệ.

Khóa nên ngắn gọn, ổn định và tách khỏi tên lớp Java. Một chuẩn nhất quán như **light**, **dark**, **high-contrast** giúp cấu hình, kiểm thử và tài liệu dễ theo dõi.

### 6.2. Provider có tên nhưng không nạp được

Việc khám phá có thể thất bại do:

- Tệp META-INF/services thiếu hoặc sai nội dung.
- Provider class không tồn tại trong artifact được chạy.
- Provider không triển khai đúng interface SPI hoặc không có cách khởi tạo hợp lệ.
- Phiên bản thư viện/API không tương thích hoặc dependency của plugin bị thiếu.
- Khai báo uses/provides hoặc cấu hình module path chưa đúng.

Java có thể ném **ServiceConfigurationError** khi xử lý provider không hợp lệ. Ứng dụng nên báo lỗi có ngữ cảnh (provider, JAR hoặc khóa liên quan) và quyết định rõ **dừng khởi động** hay **bỏ qua plugin tùy chọn**. Không nên nuốt mọi lỗi rồi âm thầm chuyển sang một họ khác, vì điều đó che giấu cấu hình sai.

### 6.3. Factory mới tạo thiếu sản phẩm hoặc sai họ

Một provider được nạp thành công **chưa đủ** chứng minh concrete factory đúng. Ví dụ HighContrastThemeFactory có thể vô tình trả về LightCheckbox. Hợp đồng Java chỉ quy định kiểu trả về là Checkbox, chưa thể hiện họ sản phẩm trong type system.

Vì vậy, mỗi họ mới cần kiểm chứng:

1. Tạo được **tất cả các loại sản phẩm** ThemeFactory công bố.
2. Các sản phẩm thuộc **cùng họ** và tuân theo quy tắc giao diện/tương thích thực tế.
3. Client hoạt động qua abstract products, không cần ép kiểu về concrete product.
4. Tạo lỗi rõ ràng khi cấu hình chọn họ không có sẵn.

### 6.4. Thay factory khi hệ thống đã chạy

Registry tạo điều kiện chọn họ ở lúc khởi tạo. Nếu **SettingsPanel** đã lưu Button và Checkbox, thay khóa ui.theme hoặc thêm provider mới **không tự chuyển** những đối tượng đang tồn tại sang họ khác. Muốn đổi chủ đề khi chạy, ứng dụng phải chủ động tạo lại các sản phẩm hoặc có cơ chế cập nhật, đồng thời xử lý dữ liệu và trạng thái đang sử dụng.

### 6.5. Nạp plugin ngoài phạm vi tin cậy

Provider là mã Java có thể thực thi trong tiến trình ứng dụng. Chỉ tải plugin từ nguồn và đường nạp được kiểm soát; không nên dùng một chuỗi tên lớp do nguồn không đáng tin cậy gửi vào để tùy ý thực thi reflection. ServiceLoader hỗ trợ cơ chế khám phá; nó **không phải sandbox bảo mật** cho mã plugin.

## 7. Quy trình kiểm chứng việc đăng ký factory mới

Đối với cả đăng ký tường minh và ServiceLoader, hãy kiểm tra hai lớp hành vi: **registry tìm đúng factory** và **factory tạo đúng bộ sản phẩm**.

| Tình huống kiểm tra | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Chọn họ cũ | ui.theme=light hoặc dark | Client nhận đúng Button và Checkbox cùng chủ đề |
| Chọn họ mới | ui.theme=high-contrast | Client nhận cả hai sản phẩm High Contrast |
| Không khai báo khóa | Không cấp ui.theme | Dùng giá trị mặc định được tài liệu hóa |
| Khóa không tồn tại | ui.theme=unknown | Báo lỗi rõ, liệt kê khóa đang có |
| Khóa bị đăng ký hai lần | Hai lần register cùng id | Từ chối trùng khóa, không ghi đè ngầm |
| Provider chưa được đóng gói | Bỏ plugin JAR hoặc resource dịch vụ | Không tìm thấy khóa mới hoặc báo lỗi nạp provider tùy trường hợp |
| Provider sai hợp đồng | Một factory trả sản phẩm khác họ | Kiểm thử tương thích phát hiện sai lệch |
| Thêm họ nhưng giữ nguyên client | Chỉ thay đăng ký/đóng gói và cấu hình | SettingsPanel vẫn không sửa |

Trong chương trình Main ở mục 2, có thể thử tình huống trùng khóa bằng cách **tạm thời** thêm lệnh sau sau lần đăng ký light đầu tiên:

~~~java
registry.register("LIGHT", DarkThemeFactory::new);
~~~

Vì registry chuẩn hóa chữ hoa/chữ thường, lệnh trên phải ném **IllegalStateException** cho khóa light. Đây là ví dụ kiểm tra khả năng phát hiện cấu hình mâu thuẫn; không giữ lệnh này trong bản chạy bình thường.

Với ServiceLoader, nên có kiểm thử tích hợp riêng đóng gói plugin JAR thật, kiểm tra resource **META-INF/services** đã được đưa vào JAR và việc khám phá/đăng ký hoạt động dưới đúng cách chạy classpath hoặc module path mà sản phẩm sử dụng.

## 8. Những quyết định thiết kế khi dùng nhiều factory

### Nên chọn một factory tại đâu?

Thông thường, đặt việc khám phá, đăng ký và lựa chọn ở **composition root**, tại nơi xây dựng SettingsPanel hay các dịch vụ tương tự. Nếu nhiều vùng trong ứng dụng dùng các họ khác nhau (ví dụ bản xem trước hai chủ đề cùng lúc), mỗi vùng có thể nhận một **ThemeFactory riêng**; registry là danh mục lựa chọn chứ không buộc toàn bộ tiến trình chỉ được dùng duy nhất một họ.

### Có nên cho từng client truy cập registry trực tiếp?

Không bắt buộc. Trong ví dụ, client chỉ nhận **ThemeFactory** đã được chọn. Nếu SettingsPanel trực tiếp đọc cấu hình và tra registry, nó sẽ biết thêm cơ chế chọn họ; điều này làm tăng phụ thuộc và khiến kiểm thử khó hơn. Chỉ cho client truy cập registry khi chính nghiệp vụ cần liệt kê và thay đổi các họ, chẳng hạn màn hình cho người dùng chọn chủ đề.

### Có cần factory tạo mọi sản phẩm trong hệ thống?

Không. Một concrete factory nên tạo **bộ sản phẩm liên quan theo cùng một quy tắc tương thích**. Nếu các nhóm sản phẩm hoàn toàn độc lập, không nên gộp chúng vào một interface lớn chỉ để có một registry duy nhất. Việc thêm **loại sản phẩm** mới buộc cập nhật interface factory và các concrete factory; thêm **họ** mới chủ yếu bổ sung một bộ hiện thực phù hợp với hợp đồng hiện có.

### Khi nào tránh mở rộng bằng plugin?

Nếu các họ ít thay đổi, có thể biên dịch và phát hành cùng ứng dụng, registry tường minh thường dễ theo dõi và ít rủi ro cấu hình hơn. ServiceLoader có ích khi sự độc lập về **phát triển, đóng gói và triển khai** đủ quan trọng để chấp nhận quản lý SPI, dependency và lỗi nạp provider.

## 9. Bài tập vận dụng

**Bài A — Thêm họ Sepia vào registry:** dựa trên Main.java ở mục 2, tạo SepiaButton, SepiaCheckbox và SepiaThemeFactory, đăng ký id sepia rồi chọn bằng tham số hệ thống. Xác nhận cả hai dòng đầu ra thuộc họ Sepia và không sửa SettingsPanel.

**Bài B — Thử các trường hợp cấu hình sai:** thử id rỗng, id có khoảng trắng, id trùng khác chữ hoa/chữ thường và id chưa đăng ký. Giải thích khi nào registry nên từ chối, khi nào có thể chuẩn hóa.

**Bài C — Chuyển một họ thành plugin:** đưa HighContrastThemeFactory và HighContrastProvider vào JAR riêng, tạo META-INF/services/demo.api.ThemeFactoryProvider, gọi ServiceLoader từ ứng dụng. Xác nhận không có plugin thì khóa high-contrast không có sẵn, có plugin thì ứng dụng chọn được qua ui.theme=high-contrast.

**Bài D — Phân tích thay đổi khi đang chạy:** ứng dụng đang hiển thị chủ đề Light thì một plugin mới được thêm vào. Hãy mô tả điều kiện để provider được khám phá lại (nếu có cơ chế nạp lại) và các bước cần thiết để xây dựng lại màn hình theo họ mới. Không giả định ServiceLoader tự theo dõi thư mục plugin hay tự đổi đối tượng đã tạo.

## 10. Ghi nhớ

- **Hiện thực** tạo các sản phẩm và concrete factory của họ mới; **đăng ký** làm cho họ đó có thể được tìm thấy; **lựa chọn** quyết định sử dụng họ nào trong lần chạy cụ thể.
- **Registry tường minh** phù hợp khi danh sách factory được kiểm soát trong ứng dụng. Cấu hình chọn bằng khóa ổn định, không cần để client biết tên lớp cụ thể.
- **ServiceLoader** phù hợp với kiến trúc plugin: provider công bố ID và cách tạo factory, còn ứng dụng khám phá nhà cung cấp thông qua SPI và metadata đóng gói.
- **Không có cơ chế nào tự bảo đảm tính nhất quán giữa các sản phẩm** nếu concrete factory triển khai sai; vẫn phải kiểm tra bộ sản phẩm của từng họ.
- Khi thêm một họ mới, mục tiêu của Abstract Factory là giữ **hợp đồng và mã client ổn định**, đồng thời tập trung thay đổi tại hiện thực họ, khâu đăng ký hoặc khám phá, cấu hình và đóng gói.
