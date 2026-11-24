# Khám phá ConcreteFactory qua Java ServiceLoader cho kiến trúc plugin

> **Chương:** Tích hợp kiến trúc  
> **Học phần:** `SOFTWARE_DESIGN_DESIGN_PATTERN_CREATIONAL_ABSTRACT_FACTORY` — Học về Abstract Factory trong Design Pattern.  
> **Mục tiêu:** Sử dụng `java.util.ServiceLoader` để phát hiện những `ConcreteFactory` được đóng gói dưới dạng plugin, chọn đúng họ sản phẩm thông qua một hợp đồng chung, và đánh giá giới hạn của cách tích hợp này.

## 1. Từ Abstract Factory đến nhu cầu mở rộng bằng plugin

Giả sử một ứng dụng desktop đã dùng Abstract Factory để tạo hai loại widget:

- `Button`: nút tương tác.
- `Checkbox`: ô lựa chọn.

Mỗi họ giao diện cung cấp những phiên bản tương ứng:

| Họ widget | ConcreteFactory | Button | Checkbox |
| --- | --- | --- | --- |
| Windows | `WindowsUiFactory` | `WindowsButton` | `WindowsCheckbox` |
| macOS | `MacUiFactory` | `MacButton` | `MacCheckbox` |

Với cách triển khai thông thường, điểm khởi động có thể chọn factory bằng một `switch`:

~~~java
UiFactory factory;
switch (platform) {
    case "windows":
        factory = new WindowsUiFactory();
        break;
    case "macos":
        factory = new MacUiFactory();
        break;
    default:
        throw new IllegalArgumentException("Unsupported platform");
}
~~~

Đoạn mã này minh họa ý tưởng chọn biến thể, nhưng **ứng dụng lõi phải biết tên các lớp factory cụ thể**. Nếu nhóm phát triển muốn phân phối một plugin Linux độc lập, mã khởi động phải sửa để nhận biết `LinuxUiFactory` và bản ứng dụng lõi phải được đóng gói hoặc biên dịch lại.

Với **kiến trúc plugin**, mục tiêu thay đổi: ứng dụng lõi chỉ biết **hợp đồng `UiFactory`**, còn những plugin độc lập có thể cung cấp các implementation cụ thể. Khi khởi động, ứng dụng **khám phá** các factory đã có trên classpath hoặc module path, sau đó lựa chọn factory qua một định danh như `"windows"` hay `"macos"`.

Đó là nhu cầu phù hợp với `ServiceLoader` của Java.

> **Phân biệt:** Abstract Factory quyết định *cách tạo một họ sản phẩm tương thích*; `ServiceLoader` quyết định *cách tìm những implementation của một interface dịch vụ*. Hai cơ chế phối hợp nhưng không thay thế nhau.

## 2. ServiceLoader là gì, và nó tìm được gì?

`java.util.ServiceLoader<S>` là cơ chế phát hiện *service provider* dựa trên quy ước của Java. Ứng dụng xác định một **service type** (thường là interface), còn các thư viện/plugin công bố lớp triển khai (*provider*) của service đó.

Trong bài này:

| Khái niệm ServiceLoader | Vai trò trong Abstract Factory |
| --- | --- |
| Service type | `UiFactory` — AbstractFactory |
| Provider class | `WindowsUiFactory`, `MacUiFactory` — ConcreteFactory |
| Provider instance | Đối tượng factory được ServiceLoader tạo khi được duyệt |
| Plugin JAR | Gói chứa ConcreteFactory và ConcreteProduct của một họ |
| Client | Màn hình dùng `UiFactory` và các product interface |

Sơ đồ luồng:

~~~mermaid
flowchart TD
    subgraph Host["Ứng dụng lõi"]
        A["Main / Composition root"]
        B["ServiceLoader<UiFactory>"]
        C["Registry theo id"]
        D["LoginScreen"]
    end
    subgraph Plugins["Plugin JAR"]
        E["WindowsUiFactory"]
        F["MacUiFactory"]
    end
    A --> B
    B -->|phát hiện provider| E
    B -->|phát hiện provider| F
    E --> C
    F --> C
    A -->|chọn id| C
    C -->|UiFactory đã chọn| D
    D -->|createButton và createCheckbox| G["Cùng một họ widget"]
~~~

Chương trình không cần import `WindowsUiFactory` hoặc `MacUiFactory`. Các lớp ấy chỉ cần thực hiện đúng interface dịch vụ và được khai báo theo quy tắc ServiceLoader.

### Hai cách công bố provider

Java hỗ trợ hai hình thức chính:

1. **Trên classpath truyền thống:** trong plugin JAR có file `META-INF/services/<tên đầy đủ của service interface>`. Mỗi dòng không phải chú thích ghi tên đầy đủ của một provider class.
2. **Trong named module (JPMS):** plugin dùng mệnh đề `provides ... with ...` của `module-info.java`, còn module sử dụng dịch vụ khai báo `uses ...`.

Bài sẽ triển khai trước bằng **classpath + `META-INF/services`**, sau đó giải thích khác biệt khi dùng Java modules.

## 3. Thiết kế ranh giới API giữa host và plugin

Một plugin chỉ tích hợp được với host khi cả hai cùng biết **hợp đồng chung**. Hợp đồng phải nằm trong một thư viện API mà host và plugin cùng phụ thuộc vào.

Ta đặt API tại package `demo.api`:

~~~java
// api/src/demo/api/UiFactory.java
package demo.api;

public interface UiFactory {
    // Định danh dùng để chọn provider đã khám phá.
    String id();

    // Các product interface thuộc hợp đồng dùng chung.
    Button createButton();
    Checkbox createCheckbox();

    interface Button {
        String render();
    }

    interface Checkbox {
        String render();
    }
}
~~~

Trong ví dụ này, `Button` và `Checkbox` là **interface lồng bên trong `UiFactory`** để số tệp ít hơn. Đây vẫn là hai product interface riêng biệt về trách nhiệm. Trong dự án lớn, hoàn toàn có thể tách chúng thành `demo.api.Button` và `demo.api.Checkbox`.

Các quy tắc API:

- `id()` trả về định danh **ổn định, duy nhất** cho mỗi họ. Ví dụ: `"windows"` hoặc `"macos"`.
- `createButton()` và `createCheckbox()` trả về **interface**, không ràng buộc host vào lớp sản phẩm cụ thể.
- Mọi ConcreteFactory phải tạo ra hai sản phẩm **thuộc cùng một họ**.
- Host **không** phải biết tên các class triển khai Button, Checkbox hoặc factory của từng plugin.

Lưu ý rằng kiểu `String` cho phép plugin mới tự giới thiệu định danh chưa tồn tại trong mã lõi; nếu dùng enum cố định cho mọi biến thể, hệ thống có thể phải sửa API để thêm một giá trị enum mới. Khi tập biến thể được quản lý tập trung và cố định, enum vẫn là lựa chọn hợp lý. Khi plugin bên ngoài có thể đặt định danh mới, chuỗi đã chuẩn hóa hoặc một value object thường linh hoạt hơn.

## 4. Tách cấu trúc dự án thành API, ứng dụng và plugin

Ví dụ sử dụng cấu trúc thư mục tối giản:

~~~text
plugin-demo/
├── api/
│   └── src/demo/api/UiFactory.java
├── app/
│   └── src/demo/app/Main.java
├── windows/
│   ├── src/demo/plugins/windows/WindowsUiFactory.java
│   └── resources/META-INF/services/demo.api.UiFactory
└── mac/
    ├── src/demo/plugins/mac/MacUiFactory.java
    └── resources/META-INF/services/demo.api.UiFactory
~~~

Cách chia phụ thuộc:

~~~mermaid
flowchart LR
    APP["app.jar"] --> API["api.jar"]
    WIN["windows-plugin.jar"] --> API
    MAC["mac-plugin.jar"] --> API
    APP -. "không phụ thuộc compile-time" .-> WIN
    APP -. "không phụ thuộc compile-time" .-> MAC
~~~

`app.jar` chỉ cần `api.jar` để **biên dịch**. Trong lúc **chạy**, plugin JAR nào được cung cấp thì ServiceLoader có thể khám phá provider trong JAR đó.

Các plugin có thể được phát triển, kiểm thử và đóng gói riêng, miễn là tuân theo phiên bản API tương thích. Cách này giúp điểm mở rộng được đặt tại **ranh giới kiến trúc**, thay vì thêm `if` theo tên plugin trong mã màn hình.

## 5. Viết ConcreteFactory và ConcreteProduct trong plugin Windows

Tạo tệp `windows/src/demo/plugins/windows/WindowsUiFactory.java`:

~~~java
package demo.plugins.windows;

import demo.api.UiFactory;

public final class WindowsUiFactory implements UiFactory {

    // Provider dạng classpath cần lớp public và constructor public không tham số.
    public WindowsUiFactory() {
    }

    @Override
    public String id() {
        return "windows";
    }

    @Override
    public UiFactory.Button createButton() {
        return new WindowsButton();
    }

    @Override
    public UiFactory.Checkbox createCheckbox() {
        return new WindowsCheckbox();
    }

    private static final class WindowsButton implements UiFactory.Button {
        @Override
        public String render() {
            return "[Windows] Button";
        }
    }

    private static final class WindowsCheckbox
            implements UiFactory.Checkbox {
        @Override
        public String render() {
            return "[Windows] Checkbox";
        }
    }
}
~~~

Đây là một provider của service `UiFactory`. Lớp provider **public**, triển khai `UiFactory` và có **public constructor không tham số** để cơ chế ServiceLoader trên classpath có thể tạo instance.

Các ConcreteProduct ở đây được viết thành lớp `private static` lồng trong factory để giữ ví dụ gọn. Sản phẩm được trả về qua `UiFactory.Button` và `UiFactory.Checkbox`, nên host không cần truy cập các lớp private đó.

Các chuỗi `render()` chỉ mô phỏng kết quả hiển thị, không phải widget Windows thật.

### Công bố provider Windows bằng metadata

Tạo file văn bản UTF-8 với đường dẫn chính xác:

~~~text
windows/resources/META-INF/services/demo.api.UiFactory
~~~

**Nội dung file** chỉ gồm tên đầy đủ của provider class:

~~~text
demo.plugins.windows.WindowsUiFactory
~~~

Ở đây:

- `demo.api.UiFactory` trong **tên file** là tên đầy đủ của *service interface*.
- `demo.plugins.windows.WindowsUiFactory` trong **nội dung** là tên đầy đủ của *provider class*.

Không ghi `WindowsUiFactory.class`, không ghi đường dẫn có dấu `/` và không ghi tên JAR. Dòng chú thích bắt đầu bằng `#` được cho phép, nhưng không cần dùng trong ví dụ.

File này phải được đặt **bên trong JAR ở đúng đường dẫn `META-INF/services/demo.api.UiFactory`** sau khi đóng gói. Để file trong thư mục nguồn mà không đưa vào JAR là lỗi khiến ServiceLoader không tìm được provider.

## 6. Viết plugin macOS độc lập

Tạo `mac/src/demo/plugins/mac/MacUiFactory.java`:

~~~java
package demo.plugins.mac;

import demo.api.UiFactory;

public final class MacUiFactory implements UiFactory {

    public MacUiFactory() {
    }

    @Override
    public String id() {
        return "macos";
    }

    @Override
    public UiFactory.Button createButton() {
        return new MacButton();
    }

    @Override
    public UiFactory.Checkbox createCheckbox() {
        return new MacCheckbox();
    }

    private static final class MacButton implements UiFactory.Button {
        @Override
        public String render() {
            return "[macOS] Button";
        }
    }

    private static final class MacCheckbox implements UiFactory.Checkbox {
        @Override
        public String render() {
            return "[macOS] Checkbox";
        }
    }
}
~~~

Tạo metadata thứ hai:

~~~text
mac/resources/META-INF/services/demo.api.UiFactory
~~~

Với nội dung:

~~~text
demo.plugins.mac.MacUiFactory
~~~

Giờ hệ thống có **hai JAR plugin riêng biệt**, mỗi JAR tự công bố provider của cùng một service interface. Tên file `META-INF/services/demo.api.UiFactory` trong cả hai JAR là **giống nhau**; khi ServiceLoader quét những JAR trên classpath, nó đọc các tài nguyên service configuration phù hợp.

Nếu sau này có plugin Linux, người phát triển có thể tạo `LinuxUiFactory` và descriptor mới trong JAR Linux. Host đã biết `UiFactory` nên **không cần import tên lớp Linux**.

## 7. Khám phá, đăng ký và chọn ConcreteFactory ở ứng dụng lõi

Tạo `app/src/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.UiFactory;
import java.util.Collections;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    private Main() {
    }

    // Chuẩn hóa id của cả provider và cấu hình người dùng.
    static String normalizeId(String value) {
        Objects.requireNonNull(value, "variant id");
        String id = value.trim().toLowerCase(Locale.ROOT);
        if (id.isEmpty()) {
            throw new IllegalArgumentException("Variant id is empty");
        }
        return id;
    }

    // Khám phá provider và xây registry chỉ đọc theo id.
    static Map<String, UiFactory> discoverFactories() {
        Map<String, UiFactory> factories = new TreeMap<>();

        ServiceLoader<UiFactory> loader =
                ServiceLoader.load(UiFactory.class);

        // ServiceLoader khởi tạo provider khi được duyệt.
        for (UiFactory candidate : loader) {
            String id = normalizeId(candidate.id());
            UiFactory previous = factories.putIfAbsent(id, candidate);

            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate UiFactory id: " + id);
            }
        }

        if (factories.isEmpty()) {
            throw new IllegalStateException(
                    "No UiFactory provider was discovered");
        }

        return Collections.unmodifiableMap(factories);
    }

    // Client không biết các ConcreteProduct hoặc ConcreteFactory.
    static final class LoginScreen {
        private final UiFactory.Button button;
        private final UiFactory.Checkbox checkbox;

        LoginScreen(UiFactory factory) {
            Objects.requireNonNull(factory, "factory");
            this.button = factory.createButton();
            this.checkbox = factory.createCheckbox();
        }

        void show() {
            System.out.println(button.render());
            System.out.println(checkbox.render());
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Main <variant-id>");
        }

        Map<String, UiFactory> factories = discoverFactories();
        String selectedId = normalizeId(args[0]);

        UiFactory selected = factories.get(selectedId);
        if (selected == null) {
            throw new IllegalArgumentException(
                    "Unsupported variant: " + selectedId
                            + "; supported: " + factories.keySet());
        }

        System.out.println("Supported: " + factories.keySet());
        System.out.println("Selected: " + selectedId);

        // Cùng một factory tạo cả Button và Checkbox.
        new LoginScreen(selected).show();
    }
}
~~~

### Tại sao cần registry sau khi khám phá?

Bản thân `ServiceLoader` cho phép **duyệt danh sách provider**. Nó không quyết định provider nào cần dùng cho cấu hình `"windows"` hoặc `"macos"` của ứng dụng.

`discoverFactories()` làm ba việc bổ sung:

1. Duyệt những `UiFactory` do ServiceLoader cung cấp.
2. Lập bảng `id → factory`, đồng thời từ chối hai provider dùng trùng một id.
3. Đưa ra danh sách **biến thể thực sự sẵn sàng** để chọn.

`TreeMap` giúp danh sách id hiển thị ổn định theo thứ tự từ điển; **không nên dựa vào thứ tự ServiceLoader khám phá provider** để quyết định một factory ưu tiên hơn factory khác.

Đoạn mã không dùng một `switch` liệt kê các plugin. Khi nhận id đã đăng ký, host nhận được `UiFactory` rồi tạo Button và Checkbox theo đúng cách đã làm trước đó.

### Tại sao không trả thẳng Button/Checkbox từ ServiceLoader?

Service type ở đây là `UiFactory`, **không phải** `Button` hay `Checkbox`. Nếu khám phá riêng từng loại sản phẩm, ứng dụng lại phải tự ghép đúng Button của Windows với Checkbox của Windows. Bằng cách khám phá **một ConcreteFactory cho mỗi họ**, trách nhiệm tạo ra **bộ sản phẩm tương thích** vẫn nằm ở Abstract Factory.

## 8. Biên dịch, đóng gói và chạy trên Windows PowerShell

Đoạn lệnh sau giả sử bạn đang đứng tại thư mục `plugin-demo` và đã tạo đủ **sáu tệp** như các mục trước: bốn tệp Java và hai service descriptor.

Cần JDK hỗ trợ `javac` và cú pháp `jar --create` (JDK 9 trở lên). Các lệnh PowerShell dưới đây hoạt động với cách tổ chức thư mục đã mô tả:

~~~powershell
New-Item -ItemType Directory -Force -Path out/api,out/app,out/windows,out/mac,dist | Out-Null

javac -encoding UTF-8 -d out/api api/src/demo/api/UiFactory.java

javac -encoding UTF-8 -cp out/api -d out/app app/src/demo/app/Main.java

javac -encoding UTF-8 -cp out/api -d out/windows windows/src/demo/plugins/windows/WindowsUiFactory.java

javac -encoding UTF-8 -cp out/api -d out/mac mac/src/demo/plugins/mac/MacUiFactory.java

Copy-Item -Path windows/resources/META-INF -Destination out/windows -Recurse -Force
Copy-Item -Path mac/resources/META-INF -Destination out/mac -Recurse -Force

jar --create --file dist/ui-api.jar -C out/api .
jar --create --file dist/ui-app.jar -C out/app .
jar --create --file dist/ui-windows.jar -C out/windows .
jar --create --file dist/ui-mac.jar -C out/mac .
~~~

Kiểm tra nội dung JAR của plugin Windows:

~~~powershell
jar --list --file dist/ui-windows.jar
~~~

Danh sách phải bao gồm những đường dẫn tương đương:

~~~text
META-INF/services/demo.api.UiFactory
demo/plugins/windows/WindowsUiFactory.class
~~~

JAR còn có các lớp lồng cho Windows Button và Checkbox. Nếu thiếu `META-INF/services/demo.api.UiFactory`, hãy kiểm tra bước copy resource.

Chạy với **cả hai plugin** trên classpath:

~~~powershell
java -cp 'dist/*' demo.app.Main windows
java -cp 'dist/*' demo.app.Main macos
~~~

`dist/*` được Java launcher mở rộng để bao gồm các JAR nằm trong thư mục `dist`. Đây là tính năng classpath wildcard của Java, không cần dùng dấu `*` để chỉ định class name.

Đầu ra dự kiến cho lựa chọn Windows:

~~~text
Supported: [macos, windows]
Selected: windows
[Windows] Button
[Windows] Checkbox
~~~

Với lựa chọn macOS:

~~~text
Supported: [macos, windows]
Selected: macos
[macOS] Button
[macOS] Checkbox
~~~

Cùng `ui-app.jar` và `ui-api.jar` được chạy trong cả hai lần. Khác biệt đến từ **provider được lựa chọn**, không phải từ mã `LoginScreen`.

## 9. Chứng minh plugin có thể được bổ sung hoặc bỏ khỏi bản phát hành

Không cần xóa JAR trên đĩa để thử nghiệm. Chỉ cần truyền classpath chứa **một plugin**:

~~~powershell
java -cp 'dist/ui-api.jar;dist/ui-app.jar;dist/ui-windows.jar' demo.app.Main windows
~~~

Kết quả:

~~~text
Supported: [windows]
Selected: windows
[Windows] Button
[Windows] Checkbox
~~~

Nếu yêu cầu `macos` trong cùng cách khởi chạy:

~~~powershell
java -cp 'dist/ui-api.jar;dist/ui-app.jar;dist/ui-windows.jar' demo.app.Main macos
~~~

Ứng dụng báo lỗi tương tự:

~~~text
java.lang.IllegalArgumentException: Unsupported variant: macos; supported: [windows]
~~~

Đây là **kết quả mong đợi**: macOS không được coi là được hỗ trợ nếu JAR macOS không có trên classpath. Không nên âm thầm dùng Windows để thay thế một id chưa được đăng ký trừ khi sản phẩm có chính sách fallback tường minh.

Trong PowerShell, dấu phân tách các phần classpath là `;`. Trên Linux/macOS, khi tự liệt kê từng JAR, dấu phân tách thường là `:`. Biểu thức wildcard `dist/*` trong ví dụ trước tránh phải liệt kê từng JAR trong cả hai trường hợp.

### Thêm plugin mới mà không sửa mã lõi

Để thêm Linux với mô hình này:

1. Triển khai `LinuxUiFactory implements UiFactory`, trong đó `id()` trả `"linux"`.
2. Đảm bảo `createButton()` và `createCheckbox()` cùng tạo các ConcreteProduct Linux.
3. Đóng gói plugin cùng `META-INF/services/demo.api.UiFactory` chứa tên `LinuxUiFactory` đầy đủ.
4. Đưa JAR Linux vào classpath trong **lần khởi động tiếp theo**; khởi chạy ứng dụng với id `linux`.

`Main.java` không cần thêm nhánh `case "linux"`, và `LoginScreen` không cần biết lớp Linux.

Tuy vậy, **plugin mới phải tương thích với API của host**. Nếu bản plugin biên dịch theo một phiên bản `UiFactory` khác không tương thích, cơ chế discovery có thể thất bại hoặc xuất hiện lỗi liên kết khi chạy.

## 10. Những lỗi tích hợp thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không khám phá được provider | Thiếu descriptor hoặc JAR plugin không có trên classpath | `jar --list --file ...`, kiểm tra classpath |
| `ServiceConfigurationError` | Sai tên class, class không load được, không phải subtype của service, thiếu constructor thích hợp, lỗi khởi tạo… | Kiểm tra thông báo lỗi và nguyên nhân lồng bên trong |
| Có provider nhưng không chọn được id | `id()` khác với id trong cấu hình | In danh sách `supported` đã chuẩn hóa |
| Hai provider có cùng id | Hai plugin công bố cùng tên biến thể | Từ chối ngay khi đăng ký, yêu cầu định danh duy nhất |
| Client thấy Button Windows và Checkbox macOS | Một ConcreteFactory đã trả sai họ sản phẩm | Kiểm thử từng factory theo hợp đồng cùng họ |
| Chạy được từ IDE nhưng không chạy từ JAR | Resource `META-INF/services` không được đóng gói | Kiểm tra danh sách file thực tế trong JAR |
| Chỉ nhìn thấy một provider trong JAR tổng hợp | Khi tạo *fat JAR*, các service descriptor cùng tên bị ghi đè | Cấu hình công cụ đóng gói để **gộp** nội dung service descriptor |
| Lỗi `NoClassDefFoundError` hoặc liên kết | Plugin thiếu dependency hoặc API không tương thích | Kiểm tra phiên bản thư viện và runtime classpath |

### ServiceConfigurationError có nên bị bỏ qua?

Thường **không nên lặng lẽ nuốt lỗi** chỉ để tiếp tục khởi động. `ServiceConfigurationError` cho thấy provider metadata hoặc quá trình tải/tạo provider có vấn đề. Trong hệ thống bắt buộc có UI tương ứng với biến thể được cấu hình, bỏ qua lỗi có thể làm registry trở nên thiếu provider mà không ai phát hiện.

Ở ví dụ, lỗi từ ServiceLoader được phép lan ra, khiến ứng dụng báo lỗi sớm. Nếu plugin là tùy chọn và hệ thống có cơ chế cô lập lỗi, có thể thiết kế chính sách riêng để vô hiệu hóa plugin không hợp lệ, nhưng phải **ghi log nguyên nhân**, xác định chính xác plugin bị lỗi và báo danh sách khả dụng còn lại.

### Nên đăng ký một instance hay nhà cung cấp tạo factory?

Ví dụ dùng `Map<String, UiFactory>`: khi duyệt ServiceLoader, factory được khởi tạo và lưu lại theo id. Cách này phù hợp với **factory không giữ trạng thái thay đổi**.

Nếu mỗi request/màn hình cần factory mới hoặc factory chứa trạng thái không thể dùng chung, nên xác định rõ vòng đời:

- Một khả năng là dùng `ServiceLoader.Provider<UiFactory>` (Java 9+) qua `ServiceLoader.stream()` để có thể gọi `get()` khi cần.
- Một khả năng khác là provider tự đóng vai trò *factory provider* chuyên cấp những `UiFactory` mới.

Không nên mặc định rằng việc gọi `factory.createButton()` làm factory hoàn toàn an toàn để dùng chung giữa nhiều luồng. Vòng đời và thread-safety phụ thuộc vào implementation cụ thể.

## 11. Classpath ServiceLoader và Java Module System

Ví dụ đã chạy theo **classpath**. Với **Java Platform Module System (JPMS)**, khai báo dịch vụ nằm ở `module-info.java`.

Giả sử các module có tên:

- `demo.ui.api`: chứa interface `demo.api.UiFactory`.
- `demo.ui.app`: chứa mã ứng dụng khám phá và sử dụng.
- `demo.ui.windows`: chứa plugin Windows.
- `demo.ui.mac`: chứa plugin macOS.

Các module descriptor tối thiểu có dạng:

**Module API:**

~~~java
module demo.ui.api {
    exports demo.api;
}
~~~

**Module ứng dụng:**

~~~java
module demo.ui.app {
    requires demo.ui.api;
    uses demo.api.UiFactory;
}
~~~

**Module plugin Windows:**

~~~java
module demo.ui.windows {
    requires demo.ui.api;
    provides demo.api.UiFactory
        with demo.plugins.windows.WindowsUiFactory;
}
~~~

**Module plugin macOS:**

~~~java
module demo.ui.mac {
    requires demo.ui.api;
    provides demo.api.UiFactory
        with demo.plugins.mac.MacUiFactory;
}
~~~

Với **named module**, mệnh đề `provides ... with ...` thay thế việc chỉ dựa vào descriptor `META-INF/services`; module sử dụng service phải khai báo `uses`. Các provider module còn cần **được resolve vào module layer** mà ServiceLoader tìm kiếm. Chỉ có file JAR trên module path chưa bảo đảm module đó đã được resolve; khi cần có thể điều chỉnh module roots, tùy cấu trúc khởi chạy.

Việc dùng named module cũng có các yêu cầu riêng về khả năng truy cập provider. Chẳng hạn một provider class có thể được khởi tạo theo các quy tắc module thay vì dựa duy nhất vào public constructor như ví dụ classpath. Nên chọn **một chế độ đóng gói rõ ràng** và kiểm thử chính xác cách chạy đó.

> Đừng trộn hướng dẫn tùy tiện: file `META-INF/services` trong ví dụ runnable là cơ chế **classpath**; `uses/provides` là cơ chế khai báo provider của **JPMS**.

## 12. ServiceLoader có tự tải plugin được thêm vào lúc chạy không?

`ServiceLoader` tìm provider dựa trên class loader hoặc module layer liên quan. Khi duyệt, nó tạo provider và duy trì một bộ nhớ đệm nội bộ; `reload()` có thể xóa bộ nhớ đệm để lần duyệt sau khám phá lại theo **môi trường class loading đang có**.

Tuy nhiên:

- `reload()` **không tự thêm một JAR mới** vào classpath JVM đang chạy.
- `reload()` **không tự tạo module layer mới** cho plugin vừa tải xuống.
- `ServiceLoader` không phải hệ thống quản lý vòng đời, cập nhật nóng hay cô lập dependency đầy đủ.
- Một `ServiceLoader` instance **không phải cấu trúc thread-safe** để nhiều luồng tùy ý duyệt và reload đồng thời.

Vì vậy, với ví dụ đang học, việc thêm/bỏ plugin được thực hiện **khi đóng gói và khởi động lại**. Nếu ứng dụng cần nạp plugin nóng, phải thiết kế thêm class loader riêng, module layer, cơ chế tải JAR, hủy tài nguyên, tương thích API và chuyển đổi trạng thái. ServiceLoader chỉ là **một phần của hệ thống đó**.

## 13. Kiểm thử plugin ở ba cấp độ

### Cấp 1 — Kiểm thử hợp đồng của từng ConcreteFactory

Mỗi plugin nên có test xác minh:

- `id()` khác rỗng và đúng định danh đã công bố.
- `createButton()` và `createCheckbox()` trả về sản phẩm hợp lệ.
- Hai sản phẩm thuộc cùng họ của factory.
- Hành vi các sản phẩm thỏa product interface.

Ví dụ kiểm tra khái niệm cho Windows:

~~~java
UiFactory factory = new WindowsUiFactory();

if (!"windows".equals(factory.id())) {
    throw new AssertionError("Wrong provider id");
}

if (!"[Windows] Button".equals(factory.createButton().render())) {
    throw new AssertionError("Wrong Windows Button");
}

if (!"[Windows] Checkbox".equals(factory.createCheckbox().render())) {
    throw new AssertionError("Wrong Windows Checkbox");
}
~~~

Đoạn kiểm tra này nằm trong **bộ kiểm thử của plugin Windows**, nơi được phép tham chiếu trực tiếp `WindowsUiFactory`. Ứng dụng lõi vẫn không import provider cụ thể.

### Cấp 2 — Kiểm thử discovery sau đóng gói

Chạy ứng dụng với một tập JAR cụ thể:

| JAR có mặt trên classpath | `supported` mong đợi |
| --- | --- |
| API + app + Windows | `[windows]` |
| API + app + macOS | `[macos]` |
| API + app + Windows + macOS | `[macos, windows]` |
| API + app, không có plugin | Khởi động thất bại với thông báo không có provider |

Đây là **integration test** quan trọng. Một provider có thể đúng về code Java nhưng vẫn không được khám phá vì thiếu hoặc sai descriptor khi đóng gói.

### Cấp 3 — Kiểm thử lỗi và tính ổn định

Các ca nên bao phủ:

1. Cấu hình yêu cầu id chưa được hỗ trợ.
2. Hai plugin trả về cùng id sau khi chuẩn hóa chữ hoa/thường.
3. Provider class sai tên trong descriptor.
4. Một plugin có phương thức tạo trả về sản phẩm sai họ.
5. Thay một bộ plugin trên classpath mà không sửa app.jar.
6. Plugin mới biên dịch với API không tương thích, để kiểm tra chính sách versioning và thông báo lỗi.

Các test này giúp phát hiện rủi ro **ở biên giữa host và plugin** — nơi lỗi không phải lúc nào cũng được nhìn thấy chỉ bằng unit test cho từng lớp.

## 14. Những quyết định kiến trúc cần cân nhắc

### Có nên cho plugin tự quyết định id?

Cho `id()` trả về chuỗi giúp thêm biến thể mới mà không cập nhật enum trong host. Nhưng hệ thống phải có chính sách:

- Chuẩn hóa id bằng một quy tắc thống nhất (`trim` và `Locale.ROOT` trong ví dụ).
- Bắt buộc không rỗng và không trùng.
- Quy định tên có cần namespace hay không, ví dụ `"vendor.theme"` khi nhiều bên cùng phát triển.
- Quy định **phiên bản API** mà plugin hỗ trợ.

Nếu các plugin nằm trong cùng một tổ chức và tập biến thể hữu hạn, một enum trong API có thể kiểm soát tính hợp lệ tốt hơn, đổi lại việc thêm tên mới sẽ cần cập nhật thư viện API.

### Có cần ưu tiên plugin nào nếu trùng id?

Trong ví dụ, **trùng id là lỗi**. Đây là chính sách dễ kiểm tra và tránh phụ thuộc thứ tự duyệt provider. Nếu muốn cho phép một plugin ghi đè plugin khác, cần định nghĩa rõ quy tắc ưu tiên, ghi log provider được chọn và có test cho các trường hợp xung đột. Không nên dùng “provider nào được phát hiện trước” làm chính sách ngầm.

### Có nên cho plugin từ nguồn không tin cậy chạy trong host?

ServiceLoader **không tạo sandbox bảo mật**. Provider JAR được tải có thể thực thi mã Java với quyền của tiến trình. Chỉ nạp plugin đã được phê duyệt và kiểm soát nguồn/phân phối. Đối với plugin bên thứ ba không đáng tin cậy, có thể cần cô lập tiến trình hoặc kiến trúc mở rộng an toàn hơn.

### Plugin có phải lúc nào cũng cần?

Không. Nếu ứng dụng chỉ có hai họ Windows/macOS được phát triển và phát hành cùng nhau, một hàm `switch` tập trung tạo factory có thể đơn giản và đủ rõ. ServiceLoader phù hợp hơn khi cần **đóng gói provider độc lập**, giảm phụ thuộc của host vào triển khai, hoặc cho phép nhiều nhóm phát triển plugin theo hợp đồng chung.

## 15. Bài tập vận dụng

**Bài 1 — Thêm Linux.** Tạo `LinuxUiFactory`, các ConcreteProduct Linux và descriptor `META-INF/services/demo.api.UiFactory`. Đóng gói `ui-linux.jar`, thêm JAR vào classpath rồi chạy với id `linux`. Không chỉnh `Main.java`. Xác nhận màn hình tạo đúng hai sản phẩm Linux.

**Bài 2 — Phát hiện descriptor bị thiếu.** Bỏ tài nguyên `META-INF/services` khỏi bản đóng gói thử nghiệm của plugin macOS và giữ nguyên class `MacUiFactory`. Vì sao class vẫn tồn tại trong JAR nhưng ServiceLoader không tự tìm thấy nó trên classpath?

**Bài 3 — Trùng id.** Tạo provider thứ hai trả về `"WINDOWS"`. Sau chuẩn hóa, cả hai cùng có id `"windows"`. Hãy quan sát lỗi và giải thích vì sao từ chối đăng ký tốt hơn chọn theo thứ tự duyệt.

**Bài 4 — Khác biệt với enum registry.** So sánh registry `EnumMap<Platform, Supplier<UiFactory>>` được viết cố định trong host với `ServiceLoader<UiFactory>`. Cách nào phù hợp nếu một nhà phát triển bên ngoài muốn phát hành thêm plugin Linux mà không sửa ứng dụng lõi?

**Bài 5 — Thử nghiệm module path.** Viết `module-info.java` cho các module API, app và Windows. Cấu hình để module cung cấp service được resolve, sau đó dùng `ServiceLoader.load(UiFactory.class)` và kiểm tra provider được phát hiện.

### Câu hỏi tự kiểm tra

1. `ServiceLoader` tìm `ConcreteFactory` bằng thông tin nào khi dùng classpath?
2. Vì sao tên file descriptor phải là tên đầy đủ của **service interface**, còn nội dung là tên đầy đủ của **provider class**?
3. Tại sao nên đưa `UiFactory` và các product interface vào API dùng chung?
4. Nếu plugin Windows có class factory nhưng không đóng gói descriptor, host sẽ thấy gì?
5. Vì sao host cần bước chọn id sau khi ServiceLoader khám phá provider?
6. `ServiceLoader.reload()` có tự tải một JAR mới được chép vào thư mục lúc runtime không?
7. Khi thêm plugin Linux, phần nào vẫn cần viết mới và phần nào của host có thể giữ nguyên?

## 16. Tổng kết trách nhiệm

| Thành phần | Trách nhiệm thực tế |
| --- | --- |
| `UiFactory` | Hợp đồng AbstractFactory dùng chung |
| `WindowsUiFactory`, `MacUiFactory` | ConcreteFactory tạo đúng họ Button/Checkbox |
| `META-INF/services` hoặc `provides` | Công bố ConcreteFactory như service provider |
| `ServiceLoader` | Phát hiện và khởi tạo provider khả dụng theo cơ chế class loading |
| Registry theo id | Chống trùng, liệt kê và lựa chọn biến thể được hỗ trợ |
| Composition root | Chọn một factory và truyền vào client |
| `LoginScreen` | Gọi product interface, không phụ thuộc vào plugin cụ thể |

Khi kết hợp đúng, **Abstract Factory giữ tính nhất quán của họ sản phẩm**, còn **Java ServiceLoader tách quá trình khám phá ConcreteFactory khỏi mã lõi**. Kết quả là ứng dụng có thể phân phối thêm hoặc bớt plugin bằng cách thay thành phần triển khai khi khởi động, đồng thời giữ nguyên hợp đồng và mã client. Việc bảo đảm descriptor đúng, API tương thích, id không trùng và vòng đời plugin rõ ràng là những điều kiện để cách tích hợp này hoạt động ổn định.

