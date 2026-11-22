# Thực hành: Hệ mở rộng nhiều provider bằng ServiceLoader

## Mục tiêu của bài

Trong một ứng dụng Java, bạn có thể muốn thêm thuật toán xử lý dữ liệu, bộ mã hóa, nguồn cấu hình, bộ gửi thông báo, bộ chuyển đổi tài liệu hoặc một chiến lược thanh toán **mà không sửa trực tiếp mã nguồn của ứng dụng chính**. Cách tiếp cận phổ biến là định nghĩa **hợp đồng dịch vụ (Service Provider Interface, SPI)**; các thành phần độc lập triển khai hợp đồng đó; ứng dụng tìm và chọn implementation khi chạy.

**`java.util.ServiceLoader`** là cơ chế SPI tiêu chuẩn của Java, xuất hiện từ Java 6 và vẫn được hỗ trợ trong Java 17/Java SE 26. Nó nhận một service type (thường là interface), tìm **0, 1 hoặc nhiều providers** trong môi trường classpath/module path và cung cấp API để duyệt chúng. Host không phải import trực tiếp các implementation classes.

Bài thực hành **“Hệ mở rộng nhiều provider bằng ServiceLoader”** hướng dẫn bạn xây dựng một hệ thống thật với:

- **Một SPI JAR** chỉ chứa interface `demo.spi.TextPlugin`.
- **Một host JAR** chỉ phụ thuộc SPI, dùng `ServiceLoader` để khám phá và lựa chọn provider.
- **Hai provider JARs độc lập**: `UppercasePlugin` chuyển chữ in hoa và `BracketPlugin` bọc chuỗi bằng ngoặc vuông.
- **Hai file khai báo provider** `META-INF/services/demo.spi.TextPlugin` được đóng trong từng provider JAR, định dạng UTF-8.
- **Ba tình huống chạy**: không provider, một provider, hai providers.
- **Lựa chọn ổn định** dựa trên `id()` và `priority()`, không phụ thuộc thứ tự classpath/khám phá.
- **`ServiceLoader.stream()`**, `Provider.type()`, `Provider.get()`, **`reload()`** và các giới hạn lazy loading/cache.
- **Hai negative tests**: hai providers có cùng ID nghiệp vụ, và descriptor trỏ tới provider class không tồn tại.
- **Phương án JPMS** với `module-info.java`, `uses`/`provides`, được kiểm thử riêng.
- Thiết kế lifecycle, error isolation, bảo mật plugin, tương thích API, test và checklist triển khai.

Sau bài, bạn có thể giải thích cách mở rộng hệ thống chỉ bằng **thêm/bớt provider artifacts**, vì sao **SPI class phải thống nhất** giữa host/providers, tại sao **`reload()` không tự tìm JAR mới mà class loader không thấy**, và cách xử lý **`ServiceConfigurationError`** đúng thay vì im lặng bỏ qua một cấu hình lỗi.

**Tính hiện hành:** Source dùng Java **17+**, `String.isBlank()`, `Stream.toList()`, `java.util.ServiceLoader`, chuẩn classpath `META-INF/services` và module JPMS. Các bước biên dịch/đóng JAR đã được chạy thật trên **OpenJDK 24.0.2 với `javac --release 17`**. Đường dẫn Javadoc tham khảo là bản **Java SE 17 và Java SE 26**. Không đưa API legacy đã lỗi thời vào thiết kế.

---

## 1. Bài toán: tại sao không viết `new` cho tất cả provider?

Giả sử ứng dụng xử lý văn bản và hỗ trợ hai cách biến đổi:

~~~java
// PHẢN VÍ DỤ: host bị gắn chặt với implementation classes.
TextPlugin upper = new UppercasePlugin();
TextPlugin brackets = new BracketPlugin();
~~~

Ban đầu cách viết này có vẻ đơn giản. Nhưng khi có thêm nhà cung cấp thứ ba, một plugin từ đối tác hoặc một implementation theo tenant, bạn thường phải:

1. Sửa import trong host.
2. Sửa logic khởi tạo và lựa chọn.
3. Biên dịch/deploy lại host chỉ để thêm một implementation.
4. Kéo mọi provider dependencies vào một classpath/build.
5. Xử lý trực tiếp khác biệt cấu hình, lỗi và thứ tự giữa providers.

Một hệ mở rộng tốt cần **dependency hướng từ implementation về hợp đồng**:

~~~text
                   Ứng dụng Host
               chỉ biết TextPlugin SPI
                         │
                         ▼
                 ServiceLoader
                         │
           ┌─────────────┴─────────────┐
           │                           │
           ▼                           ▼
   upper.jar provider          brackets.jar provider
   UppercasePlugin             BracketPlugin
   implements TextPlugin       implements TextPlugin
           │                           │
           └─────────────┬─────────────┘
                         ▼
                 API chung: TextPlugin
~~~

**Host biết interface; provider biết interface; host không cần biết provider class names ở compile time.** Hệ thống vẫn có thể thêm hoặc bỏ JAR trong **quá trình build/deploy rồi khởi động lại**, mà không phải sửa source host.

Cần phân biệt: **thêm JAR trước khi launch** khác với **hot-load một JAR mới vào JVM đang chạy**. `ServiceLoader` hỗ trợ khám phá theo class-loader/module environment, nhưng **không phải trình quản lý plugin hot-reload hoàn chỉnh**.

---

## 2. Những thành phần của Java SPI

### 2.1. Service type

**Service** là một interface hoặc class đóng vai trò hợp đồng thống nhất. Ví dụ:

~~~java
package demo.spi;

public interface TextPlugin {
    String id();
    int priority();
    String apply(String input);
}
~~~

Contract quy định:

- `id()` là mã định danh **logic** duy nhất của một plugin trong registry của host.
- `priority()` là độ ưu tiên do ứng dụng tự định nghĩa; ví dụ **số nhỏ hơn được ưu tiên trước**.
- `apply(input)` tạo văn bản đã chuyển đổi.

`ServiceLoader` không tự hiểu `id` và `priority`: đây là các methods **do chúng ta thiết kế**, phục vụ selection policy.

### 2.2. Provider

Provider là implementation của service:

~~~java
package demo.providers.upper;

import demo.spi.TextPlugin;

public final class UppercasePlugin implements TextPlugin {
    public UppercasePlugin() {}

    public String id() { return "uppercase"; }
    public int priority() { return 10; }
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Ở dạng **classpath-based SPI**, provider được khai báo trong file `META-INF/services/...` phải là **public concrete class**, implement service interface và có **public no-argument constructor** theo contract. `ServiceLoader` tự khởi tạo khi cần.

### 2.3. Provider configuration file

Với service binary name `demo.spi.TextPlugin`, resource path phải chính xác:

~~~text
META-INF/services/demo.spi.TextPlugin
~~~

Nội dung trong `upper.jar`:

~~~text
demo.providers.upper.UppercasePlugin
~~~

Nội dung trong `brackets.jar`:

~~~text
demo.providers.brackets.BracketPlugin
~~~

Đây là **resource nằm trong JAR**, không phải Java source và cũng không phải một path do host tự đọc bằng `Files.readString`. Java ServiceLoader tìm bằng class loader resource mechanism.

### 2.4. Host

Host gọi:

~~~java
ServiceLoader<TextPlugin> loader =
        ServiceLoader.load(TextPlugin.class);
~~~

Không có `new UppercasePlugin()` hay `new BracketPlugin()` trong host. Nó chỉ dùng những methods của `TextPlugin`.

### 2.5. Provider count là dữ liệu động

Cùng một host:

~~~text
Classpath: api.jar + host.jar
  → 0 providers

Classpath: api.jar + host.jar + brackets.jar
  → 1 provider

Classpath: api.jar + host.jar + upper.jar + brackets.jar
  → 2 providers
~~~

Ứng dụng phải có behavior hợp lệ trong cả ba trường hợp. **Không bao giờ mặc định có ít nhất một provider**, trừ khi deployment có validation bắt buộc và fail fast khi không thỏa.

---

## 3. Thiết kế SPI tốt trước khi viết implementation

### 3.1. Interface càng nhỏ càng dễ tương thích

Contract mẫu:

~~~java
public interface TextPlugin {
    String id();
    int priority();
    String apply(String input);
}
~~~

**Định nghĩa nghiệp vụ phải rõ:**

- Input có cho phép null không? Bài demo giả định input khác null.
- `id()` có chuẩn hóa case hay không? Bài demo phân biệt nguyên trạng, không tự đổi case.
- `priority()` số nhỏ hơn được chọn trước hay ngược lại? Bài demo số nhỏ hơn trước.
- `apply()` có side effects, network calls, logging, I/O không? Bài demo thuần tính toán.
- Một instance có thread-safe không? Không được suy đoán từ interface; cần contract riêng.
- Có thể tạo nhiều instances không? Bài demo cho phép.
- Lỗi chuyển đổi trả exception hay error value? Cần quy định.

Một SPI không có contract rõ sẽ buộc mỗi plugin tự diễn giải, tạo khó khăn khi host có nhiều implementations từ nhiều tác giả.

### 3.2. Ổn định binary compatibility

Các providers có thể được biên dịch ở một thời điểm khác host. Nếu thay:

~~~java
// Thay chữ ký method: KHÔNG còn tương thích binary.
String apply(String input, boolean strict);
~~~

trong khi JAR cũ chỉ có `apply(String)`, ứng dụng có thể gặp lỗi linking/`AbstractMethodError` khi gọi. Không xem việc JVM load provider thành công là chứng minh mọi methods còn tương thích.

Nên:

1. Dùng semantic version cho SPI artifact.
2. Giữ method signatures public ổn định khi có thể.
3. Test provider JAR cũ với host mới.
4. Chỉ thêm default methods nếu semantics thực sự tương thích; đừng coi đó là phép màu bảo đảm an toàn.
5. Nếu cần breaking change, công bố SPI v2 và migration/adapter policy.
6. Không để provider tự bundle một bản API class không tương thích.

### 3.3. Đừng biến SPI thành toàn bộ domain model

Một provider chỉ cần biết input/output hợp đồng của chức năng nó cung cấp. Không nên expose toàn bộ database repositories, runtime internals, credentials hay user sessions nếu không cần. Tăng surface area cũng làm tăng coupling và rủi ro bảo mật.

### 3.4. Factory SPI nếu plugin có khởi tạo đắt đỏ

Với một provider cần tạo kết nối, codec hoặc engine nặng, có thể định nghĩa SPI dưới dạng **factory**:

~~~java
// MẢNH MINH HỌA.
public interface EngineFactory {
    String id();
    Engine create(Config config);
}
~~~

Khi đó ServiceLoader tạo **factory provider**, còn ứng dụng chỉ tạo engine theo nhu cầu. Cách này giúp trì hoãn khởi tạo tài nguyên đến lúc thực sự cần và có lifecycle rõ hơn.

---

## 4. Cấu trúc dự án thực hành: hai provider JARs độc lập

Các đường dẫn ở đây là **relative path trong thư mục thực hành**, không phải repository của bất kỳ dự án nào khác.

~~~text
service-loader-demo/
├── src/
│   ├── api/
│   │   └── demo/spi/TextPlugin.java
│   ├── host/
│   │   └── demo/app/PluginHost.java
│   ├── upper/
│   │   └── demo/providers/upper/UppercasePlugin.java
│   └── brackets/
│       └── demo/providers/brackets/BracketPlugin.java
├── build/
│   ├── api/
│   ├── host/
│   ├── upper/
│   │   └── META-INF/services/demo.spi.TextPlugin
│   └── brackets/
│       └── META-INF/services/demo.spi.TextPlugin
├── api.jar
├── host.jar
├── upper.jar
└── brackets.jar
~~~

**Tối thiểu có bốn JARs** để chứng minh tính độc lập thực sự: API, host, hai implementations. Host compile với **api.jar/build/api בלבד**, không compile với source hoặc JAR của provider.

Hai provider JARs đều chứa descriptor cùng tên `META-INF/services/demo.spi.TextPlugin` nhưng nội dung mỗi file trỏ đến **class của plugin riêng**. Java ServiceLoader sẽ tìm các resources ở các JARs khác nhau qua class loader.

### 4.1. File `src/api/demo/spi/TextPlugin.java`

~~~java
package demo.spi;

public interface TextPlugin {
    String id();
    int priority();
    String apply(String input);
}
~~~

Đây là toàn bộ SPI. Không import implementation class.

### 4.2. File `src/upper/demo/providers/upper/UppercasePlugin.java`

~~~java
package demo.providers.upper;

import java.util.Locale;
import demo.spi.TextPlugin;

public final class UppercasePlugin implements TextPlugin {
    public UppercasePlugin() {}

    public String id() {
        return "uppercase";
    }

    public int priority() {
        return 10;
    }

    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**Giải thích:**

- `id()` trả `"uppercase"`, là key chọn provider.
- `priority()` trả 10, có độ ưu tiên cao hơn 20 theo policy demo.
- `Locale.ROOT` giúp chuyển hoa theo ngữ nghĩa ngôn ngữ-neutral, tránh phụ thuộc vào default locale của máy.
- Public zero-arg constructor làm class hợp lệ cho **classpath provider loading**.
- Không có init I/O hoặc secrets trong constructor.

### 4.3. File `src/brackets/demo/providers/brackets/BracketPlugin.java`

~~~java
package demo.providers.brackets;

import demo.spi.TextPlugin;

public final class BracketPlugin implements TextPlugin {
    public BracketPlugin() {}

    public String id() {
        return "brackets";
    }

    public int priority() {
        return 20;
    }

    public String apply(String input) {
        return "[" + input + "]";
    }
}
~~~

Provider này không biết UppercasePlugin. Nó có thể được phát hành, cập nhật hoặc gỡ riêng, miễn giữ contract của TextPlugin và classpath/module resolution hợp lệ.

### 4.4. Hai file dịch vụ trong build resource trees

**File thứ nhất:**

~~~text
build/upper/META-INF/services/demo.spi.TextPlugin
~~~

Nội dung chính xác:

~~~text
demo.providers.upper.UppercasePlugin
~~~

**File thứ hai:**

~~~text
build/brackets/META-INF/services/demo.spi.TextPlugin
~~~

Nội dung chính xác:

~~~text
demo.providers.brackets.BracketPlugin
~~~

Đặt đúng **binary name của service** vào tên file và **binary name của provider** vào nội dung. Không viết `.class`, `.java`, `new`, Maven coordinate hay `demo.spi.TextPlugin=...` trong nội dung.

### 4.5. Tên file, encoding và whitespace

Theo Java SE 26 `ServiceLoader` Javadoc:

- Service descriptor phải được mã hóa **UTF-8**.
- Mỗi provider class name trên một dòng.
- Dòng trống và khoảng trắng/tab bao quanh tên được bỏ qua.
- Dấu `#` bắt đầu comment; phần sau trong cùng dòng bị bỏ qua.
- Các bản ghi trùng **cùng class name** có thể được bỏ qua khi discovery.
- File có thể chứa nhiều provider class names; nhưng trong bài mỗi plugin JAR khai báo một class.

**Nhớ:** Java ServiceLoader loại bỏ trùng lặp **cùng tên lớp provider** theo quy tắc discovery, nhưng **không biết hai class khác nhau cùng trả `id() = "uppercase"` là trùng ID nghiệp vụ**. Host phải tự chặn semantic duplicate.

---

## 5. File host: discovery, lựa chọn, validation và reload

### 5.1. File `src/host/demo/app/PluginHost.java` hoàn chỉnh

~~~java
package demo.app;

import demo.spi.TextPlugin;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.ServiceLoader.Provider;

public final class PluginHost {
    private PluginHost() {}

    public static void main(String[] args) {
        ServiceLoader<TextPlugin> loader = ServiceLoader.load(TextPlugin.class);
        List<Provider<TextPlugin>> descriptors = loader.stream()
                .sorted(Comparator.comparing(p -> p.type().getName()))
                .toList();
        System.out.println("discovered=" + descriptors.size());

        Map<String, TextPlugin> byId = new HashMap<>();
        for (Provider<TextPlugin> descriptor : descriptors) {
            TextPlugin plugin = descriptor.get();
            String id = plugin.id();
            if (id == null || id.isBlank()) {
                throw new IllegalStateException("Blank plugin id");
            }
            if (byId.putIfAbsent(id, plugin) != null) {
                throw new IllegalStateException("Duplicate plugin id: " + id);
            }
        }

        List<TextPlugin> ordered = new ArrayList<>(byId.values());
        ordered.sort(Comparator.comparingInt(TextPlugin::priority)
                .thenComparing(TextPlugin::id));
        for (TextPlugin plugin : ordered) {
            System.out.println("plugin=" + plugin.id() + "@"
                    + plugin.priority() + ":" + plugin.apply("java spi"));
        }

        TextPlugin selected = byId.get("uppercase");
        System.out.println("selectedUppercase="
                + (selected == null ? "NOT_FOUND" : selected.apply("java spi")));
        System.out.println("loadedIds="
                + String.join(",", ordered.stream().map(TextPlugin::id).toList()));

        loader.reload();
        System.out.println("afterReloadDescriptors=" + loader.stream().count());
    }
}
~~~

**Mã này là file runnable**, không phải pseudocode. Nó chỉ import `demo.spi.TextPlugin` và JDK classes; **không import** `UppercasePlugin`, `BracketPlugin` hoặc bất kỳ provider implementation package nào.

### 5.2. Luồng xử lý của host

~~~text
ServiceLoader.load(TextPlugin.class)
                 │
                 ▼
          stream() descriptors
                 │
                 ▼
         Sort by provider type
         (để in/test ổn định)
                 │
                 ▼
          descriptor.get()
        instantiate từng provider
                 │
                 ▼
        Validate id() nonblank
                 │
                 ▼
        Duplicate ID? → fail fast
                 │
                 ▼
           Map ID → instance
                 │
                 ▼
        Sort priority asc, id asc
                 │
                 ▼
        Execute apply("java spi")
                 │
                 ▼
        Select id="uppercase"
                 │
                 ▼
        loader.reload() + recount
~~~

### 5.3. Vì sao tách `Provider.type()` và `Provider.get()`?

`ServiceLoader.stream()` trả **`Stream<ServiceLoader.Provider<TextPlugin>>`**. Một `Provider` có:

- `type()`: trả type provider được công bố, giúp inspect/filter theo class hoặc annotation **trước khi instantiate**.
- `get()`: tạo hoặc cung cấp một instance provider theo API contract.

Dòng:

~~~java
List<Provider<TextPlugin>> descriptors = loader.stream()
        .sorted(Comparator.comparing(p -> p.type().getName()))
        .toList();
~~~

thu thập các provider descriptors và sắp xếp theo tên class. **Nó không gọi `descriptor.get()` nên chưa chủ động instantiate providers để chạy `apply`.** Việc class loading/introspection vẫn có thể có chi phí hoặc lỗi; “không instantiate” không đồng nghĩa “không load metadata/class”.

Trong vòng lặp, `descriptor.get()` mới lấy instance. Nếu constructor/provider factory lỗi, `ServiceConfigurationError` có thể xuất hiện.

### 5.4. Vì sao không dùng thứ tự khám phá để chọn provider?

Theo JDK specification, thứ tự từ nhiều JAR/class loaders/modules phụ thuộc lookup/module layers; không có một priority policy thống nhất mà bạn có thể dùng làm luật nghiệp vụ cho mọi deployment.

**Hãy định nghĩa policy riêng.** Demo đặt:

~~~text
UppercasePlugin → priority=10, id=uppercase
BracketPlugin   → priority=20, id=brackets
~~~

Sau khi nạp, host sắp xếp bằng:

~~~java
ordered.sort(Comparator.comparingInt(TextPlugin::priority)
        .thenComparing(TextPlugin::id));
~~~

Đây là **thứ tự business** do host chọn, không phải ServiceLoader guarantee. Nếu priority bằng nhau, `id` là tie-breaker. Nếu hai providers cùng id, host ném exception thay vì chọn tình cờ một provider nào đó.

### 5.5. Vì sao chọn provider theo ID?

~~~java
TextPlugin selected = byId.get("uppercase");
System.out.println("selectedUppercase="
        + (selected == null ? "NOT_FOUND" : selected.apply("java spi")));
~~~

Ứng dụng không phải lúc nào cũng muốn chạy mọi providers. Trong thực tế có thể chọn theo:

- Cấu hình admin đã được validate.
- Format, encoding, region hoặc loại input.
- Capabilities/methods do SPI công bố.
- Priority và fallback policy đã dokument hóa.
- Tenant, license hoặc workload routing nếu policy cho phép.

**Không tự chọn `findFirst()` làm provider “tốt nhất”** khi chưa xác định một ordering contract phù hợp.

### 5.6. Host xử lý zero-provider

Nếu không có plugin JAR, `stream().toList()` rỗng, chương trình vẫn chạy:

~~~text
discovered=0
selectedUppercase=NOT_FOUND
loadedIds=
afterReloadDescriptors=0
~~~

Đó là một behavior hợp lệ nếu plugins là optional. Nếu hệ thống yêu cầu ít nhất một provider để phục vụ requests, hãy **fail fast ở startup** với thông báo thiếu capability, không để lỗi xảy ra muộn khi nhận traffic.

---

## 6. Biên dịch và đóng JAR trên Linux/macOS

Ở thư mục `service-loader-demo`, tạo các files nguồn như mục 4 và 5. Lệnh dưới đây tạo các thư mục output, biên dịch độc lập và đóng resources:

~~~bash
mkdir -p build/api build/host build/upper build/brackets
mkdir -p build/upper/META-INF/services
mkdir -p build/brackets/META-INF/services

# 1. Biên dịch SPI độc lập.
javac -encoding UTF-8 --release 17 \
      -d build/api src/api/demo/spi/TextPlugin.java

# 2. Biên dịch host chỉ cần SPI, KHÔNG cần providers.
javac -encoding UTF-8 --release 17 \
      -cp build/api -d build/host \
      src/host/demo/app/PluginHost.java

# 3. Biên dịch từng provider độc lập với nhau.
javac -encoding UTF-8 --release 17 \
      -cp build/api -d build/upper \
      src/upper/demo/providers/upper/UppercasePlugin.java

javac -encoding UTF-8 --release 17 \
      -cp build/api -d build/brackets \
      src/brackets/demo/providers/brackets/BracketPlugin.java

# 4. Tạo file service descriptors đúng UTF-8.
printf '%s\n' 'demo.providers.upper.UppercasePlugin' \
      > build/upper/META-INF/services/demo.spi.TextPlugin

printf '%s\n' 'demo.providers.brackets.BracketPlugin' \
      > build/brackets/META-INF/services/demo.spi.TextPlugin

# 5. Đóng 4 JARs độc lập.
jar cf api.jar -C build/api .
jar cf host.jar -C build/host .
jar cf upper.jar -C build/upper .
jar cf brackets.jar -C build/brackets .

# 6. Kiểm tra resources thực sự được đóng trong JAR.
jar tf upper.jar
jar tf brackets.jar
~~~

`jar tf` của mỗi provider JAR phải thấy entry:

~~~text
META-INF/services/demo.spi.TextPlugin
~~~

Nếu provider `.class` có trong JAR nhưng file resource thiếu, ServiceLoader **có thể tìm 0 provider** trên classpath, vì Java không tự scan tất cả classes để tìm implementation.

### 6.1. Chạy ba biến thể trên Linux/macOS

Dấu tách các entries classpath ở Linux/macOS là `:`:

~~~bash
# 0 provider JAR:
java -cp "api.jar:host.jar" demo.app.PluginHost

# 1 provider:
java -cp "api.jar:host.jar:brackets.jar" demo.app.PluginHost

# 2 providers:
java -cp "api.jar:host.jar:upper.jar:brackets.jar" \
     demo.app.PluginHost
~~~

**Classpath chỉ thay những JAR được nhìn thấy; không phải đổi source của host.** Đây chính là khả năng mở rộng cơ bản mà SPI/ServiceLoader mang lại.

---

## 7. Biên dịch và chạy trên Windows PowerShell

PowerShell 5.1 có thể dùng cùng `javac`, `jar`, `java`. Khác biệt chính là path và dấu tách classpath `;`.

~~~powershell
New-Item -ItemType Directory -Force `
  build\api,build\host,build\upper,build\brackets | Out-Null

New-Item -ItemType Directory -Force `
  build\upper\META-INF\services,build\brackets\META-INF\services |
  Out-Null

javac -encoding UTF-8 --release 17 -d build\api `
  src\api\demo\spi\TextPlugin.java

javac -encoding UTF-8 --release 17 -cp build\api -d build\host `
  src\host\demo\app\PluginHost.java

javac -encoding UTF-8 --release 17 -cp build\api -d build\upper `
  src\upper\demo\providers\upper\UppercasePlugin.java

javac -encoding UTF-8 --release 17 -cp build\api -d build\brackets `
  src\brackets\demo\providers\brackets\BracketPlugin.java

# Dùng .NET để ghi UTF-8 không BOM, tránh phụ thuộc encoding
# mặc định của một số phiên bản PowerShell.
$enc = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
  "build\upper\META-INF\services\demo.spi.TextPlugin",
  "demo.providers.upper.UppercasePlugin" + [Environment]::NewLine,
  $enc)

[System.IO.File]::WriteAllText(
  "build\brackets\META-INF\services\demo.spi.TextPlugin",
  "demo.providers.brackets.BracketPlugin" + [Environment]::NewLine,
  $enc)

jar cf api.jar -C build\api .
jar cf host.jar -C build\host .
jar cf upper.jar -C build\upper .
jar cf brackets.jar -C build\brackets .

jar tf upper.jar
jar tf brackets.jar

java -cp "api.jar;host.jar" demo.app.PluginHost
java -cp "api.jar;host.jar;brackets.jar" demo.app.PluginHost
java -cp "api.jar;host.jar;upper.jar;brackets.jar" demo.app.PluginHost
~~~

Đây là PowerShell, không phải `cmd.exe`: ký tự xuống dòng `` ` `` chỉ hoạt động khi nằm cuối dòng, **không có dấu cách theo sau**. Bạn có thể đặt lệnh `javac` trên một dòng nếu muốn đơn giản hơn.

### 7.1. Kiểm tra cấu trúc JAR là một phần của QA

Khi `javac` chạy thành công chưa có nghĩa provider đã được deploy đúng. **Kiểm tra file service descriptor thực sự có trong JAR cuối** và tên provider trong nội dung khớp class bytecode.

Trong Maven/Gradle, đặt file vào:

~~~text
src/main/resources/META-INF/services/demo.spi.TextPlugin
~~~

Đối với từng provider project, hệ thống build thông thường đưa resource này vào JAR. Nếu dùng fat/shaded/uber JAR, phải **merge** các files `META-INF/services` của tất cả providers; không để provider cuối ghi đè descriptor của provider trước.

---

## 8. Stdout đã kiểm chứng: 0, 1 và 2 providers

Các kết quả dưới đây không phải output ước đoán. Hệ thống đã được biên dịch và chạy trong thư mục tạm trên **OpenJDK 24.0.2**, với từng Java file compile bằng `javac --release 17`, từng provider đóng thành JAR riêng, và so khớp chính xác từng dòng.

### 8.1. Không provider

Lệnh:

~~~bash
java -cp "api.jar:host.jar" demo.app.PluginHost
~~~

Trên Windows, dùng `;` thay `:`. Stdout:

~~~text
discovered=0
selectedUppercase=NOT_FOUND
loadedIds=
afterReloadDescriptors=0
~~~

**Giải thích:** Interface và host JAR không tự sinh implementation. Host không crash khi service collection rỗng; selection theo ID trả NOT_FOUND. `reload()` không tự tải một JAR chưa có trong classpath.

### 8.2. Một provider: brackets

Lệnh:

~~~bash
java -cp "api.jar:host.jar:brackets.jar" demo.app.PluginHost
~~~

Stdout:

~~~text
discovered=1
plugin=brackets@20:[java spi]
selectedUppercase=NOT_FOUND
loadedIds=brackets
afterReloadDescriptors=1
~~~

**Giải thích:** Chỉ BracketPlugin hiện diện. `id=uppercase` không tồn tại, nên host **không tự dùng provider khác thay thế** cho một ID cụ thể nếu chưa có fallback policy.

### 8.3. Hai providers đồng thời

Lệnh:

~~~bash
java -cp "api.jar:host.jar:upper.jar:brackets.jar" demo.app.PluginHost
~~~

Stdout:

~~~text
discovered=2
plugin=uppercase@10:JAVA SPI
plugin=brackets@20:[java spi]
selectedUppercase=JAVA SPI
loadedIds=uppercase,brackets
afterReloadDescriptors=2
~~~

**Giải thích:**

1. ServiceLoader tìm được cả hai resource descriptors.
2. `Provider.get()` tạo các implementation instances.
3. Host validate mỗi id khác blank và không trùng.
4. Host sắp xếp **priority thấp trước**: uppercase 10, brackets 20.
5. `apply("java spi")` của uppercase dùng Locale.ROOT cho `"JAVA SPI"`.
6. Brackets bọc thành `"[java spi]"`.
7. Lựa chọn ID `uppercase` dùng đúng UppercasePlugin.
8. `reload()` clear cache của ServiceLoader, sau đó tìm lại **hai descriptors vẫn trong cùng classpath**.

### 8.4. Một tính chất quan trọng từ kết quả

**Không hề có dòng `new UppercasePlugin()` trong `PluginHost` và host đã compile thành công chỉ với `build/api`.** Điều đó chứng minh tách code bằng SPI, thay vì hardcode danh sách providers.

Nếu muốn thêm provider `MarkdownPlugin`, một nhóm khác có thể tạo JAR mới triển khai cùng SPI và resource descriptor. Sau đó deployment đặt JAR đó lên classpath hoặc module path tương thích, host có thể tìm provider mà không sửa code import provider.

---

## 9. Lỗi cấu hình: semantic duplicate và ServiceConfigurationError

Một kiến trúc nhiều provider cần **negative tests** chứ không chỉ case hai plugins hoạt động tốt.

### 9.1. Hai classes cùng trả `id="uppercase"`

Tạo thêm provider class trong dự án thử nghiệm:

**File `src/duplicate/demo/providers/duplicate/DuplicateUppercasePlugin.java`:**

~~~java
package demo.providers.duplicate;

import demo.spi.TextPlugin;

public final class DuplicateUppercasePlugin implements TextPlugin {
    public DuplicateUppercasePlugin() {}

    public String id() { return "uppercase"; }
    public int priority() { return 30; }
    public String apply(String input) {
        return "duplicate:" + input;
    }
}
~~~

Descriptor trong `build/duplicate/META-INF/services/demo.spi.TextPlugin`:

~~~text
demo.providers.duplicate.DuplicateUppercasePlugin
~~~

Biên dịch:

~~~bash
mkdir -p build/duplicate/META-INF/services
javac -encoding UTF-8 --release 17 -cp build/api \
      -d build/duplicate \
      src/duplicate/demo/providers/duplicate/DuplicateUppercasePlugin.java

printf '%s\n' 'demo.providers.duplicate.DuplicateUppercasePlugin' \
      > build/duplicate/META-INF/services/demo.spi.TextPlugin

jar cf duplicate.jar -C build/duplicate .

java -cp "api.jar:host.jar:upper.jar:duplicate.jar" \
     demo.app.PluginHost
~~~

Lệnh Java ở trên **được kỳ vọng thất bại**. Host sẽ in discovery count, sau đó `putIfAbsent` phát hiện semantic duplicate và ném:

~~~text
java.lang.IllegalStateException: Duplicate plugin id: uppercase
~~~

Trên OpenJDK 24.0.2, negative test đã xác nhận **exit code khác 0** và thông điệp chứa `"Duplicate plugin id: uppercase"`. Không cố định nguyên stack trace vì line numbers và wrapper launch details có thể đổi theo môi trường.

**Quan trọng:** ServiceLoader có thể loại bỏ duplicate class names trong descriptors. Nhưng `UppercasePlugin` và `DuplicateUppercasePlugin` là **hai classes khác nhau**; chúng vẫn đều được phát hiện và khởi tạo. Việc trùng `id()` là chuyện **business registry**, chỉ host mới biết.

### 9.2. Descriptor trỏ đến lớp không tồn tại

Tạo một JAR lỗi, chứa resource:

~~~text
META-INF/services/demo.spi.TextPlugin
~~~

Với nội dung:

~~~text
demo.providers.nonexistent.MissingPlugin
~~~

Nếu JAR được đưa vào classpath nhưng class không tồn tại/không load được, ServiceLoader có thể ném **`java.util.ServiceConfigurationError`** trong lúc discover/iterate/instantiate providers.

Đây là một **`Error`**, không phải `Exception` thông thường. Vì vậy:

~~~java
// MẢNH MINH HỌA.
try {
    for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
        // ...
    }
} catch (java.util.ServiceConfigurationError error) {
    // Báo lỗi cấu hình plugin và dừng startup, hoặc xử lý theo policy.
}
~~~

**Không khuyên catch(Error) chung rồi im lặng tiếp tục**, vì có thể che lỗi cấu hình nghiêm trọng. Theo Javadoc, nếu một provider có lỗi trong quá trình iterator, JVM có thể nỗ lực khám phá tiếp nhưng **không bảo đảm có thể recover**. Hệ thống production cần policy fail fast hoặc cô lập plugin artifact từ trước khi đưa vào JVM.

Negative test với `bad.jar` đã xác nhận **exit code khác 0** và lỗi chứa **ServiceConfigurationError**.

### 9.3. Các nguyên nhân ServiceConfigurationError khác

- Resource file có nội dung sai format.
- Tên provider class sai package/binary name.
- Provider implementation không nằm trong class loader visibility.
- Public no-argument constructor thiếu hoặc không đúng yêu cầu với classpath provider.
- Provider abstract/nonpublic hoặc không implement đúng SPI.
- Constructor throw exception.
- Lỗi linkage, dependency của provider không tìm thấy.
- Module `provides` chỉ tới class/factory không tuân thủ rules.
- Service type không accessible hoặc named module caller thiếu `uses` directive.
- JAR shading làm mất/ghi đè service descriptors.

**Đừng chuyển tất cả những lỗi đó thành “không tìm thấy plugin”**: zero providers hợp lệ khác với broken provider configuration.

---

## 10. Lazy loading, cache và reload() chính xác

### 10.1. ServiceLoader không luôn tạo tất cả providers ngay

Theo Java SE 26 Javadoc, provider discovery và instantiation là **lazy/on-demand**. Ví dụ:

~~~java
ServiceLoader<TextPlugin> loader =
        ServiceLoader.load(TextPlugin.class);
~~~

Dòng này tạo loader object; chưa nhất thiết khởi tạo mọi provider.

~~~java
for (TextPlugin plugin : loader) {
    // iterator() lazily discovers/instantiates
}
~~~

Iterator lần đầu tìm classes và instantiate từng provider khi cần. **ServiceLoader duy trì cache** cho các providers đã nạp; iteration sau có thể dùng lại cached instances theo contract của iterator.

### 10.2. `stream()` và Provider descriptor

~~~java
ServiceLoader<TextPlugin> loader =
        ServiceLoader.load(TextPlugin.class);

var types = loader.stream()
        .map(ServiceLoader.Provider::type)
        .toList();
~~~

`Provider.type()` có thể dùng để xem type/annotations trước khi gọi `Provider.get()`. Đây là API từ Java 9, vẫn đang được hỗ trợ.

**Phân biệt:** `stream()` không phải stream trực tiếp của `TextPlugin` instances; nó là stream của **Provider descriptors**. Muốn instance:

~~~java
var providers = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Trong named modules có provider factory method, `Provider.type()` có thể biểu thị **return type của factory** thay vì provider implementation class; đừng dựa trên `type()` luôn phản ánh class cụ thể.

### 10.3. Cache của iterator khác assumptions về Provider.get()

Với đường `loader.iterator()`, Javadoc mô tả caching các provider instances đã loaded, dùng lại trong iteration sau.

Với đường `loader.stream()`, Javadoc mô tả caching các **provider metadata/descriptors** đã phát hiện. Đừng xây logic lifecycle dựa trên giả định `Provider.get()` luôn trả cùng một instance mỗi lần; nếu hệ thống cần singleton, hãy **materialize registry và sở hữu lifecycle của instance** rõ ràng.

Ví dụ host tạo:

~~~java
Map<String,TextPlugin> byId = new HashMap<>();
~~~

và giữ một instance cho mỗi ID trong suốt lượt xử lý. Một ứng dụng server có thể nâng nó thành immutable registry sau startup, nếu providers thread-safe hoặc được quản lý bằng factory/cơ chế khác.

### 10.4. `reload()` thật sự làm gì?

~~~java
loader.reload();
~~~

Theo Javadoc:

- **Xóa cache của ServiceLoader**.
- Những lần iterator/stream tiếp theo sẽ **khám phá lại** trong class-loader/module environment đang thấy.
- Sau reload, các iterators/streams cũ có thể fail fast với **ConcurrentModificationException**; phải bỏ chúng và lấy iterator/stream mới.
- `reload()` **không tự thêm file JAR mới vào classpath**.
- `reload()` **không thay class definitions đã load**, không tự unload classes, không đóng provider resources.
- `reload()` không phải một transaction thay toàn bộ active plugin registry.

Trong demo, `afterReloadDescriptors` bằng 0, 1 hoặc 2 như trước, vì classpath không đổi.

### 10.5. Khi nào dùng reload trong hệ plugin thực?

Nếu host đang dùng một **class loader được quản lý riêng** hoặc một **ModuleLayer** có tập providers thay đổi theo cách được hỗ trợ, bạn có thể cần tạo ServiceLoader mới hoặc reload cache sau khi class loader nhìn thấy providers bổ sung.

Nhưng với **classpath system class loader bình thường**, không được giả định copy JAR mới vào một folder là loader tự nhìn thấy JAR đó. Muốn dynamic installation thực sự phải thiết kế:

- Class loader mới có JAR URLs phù hợp hoặc module layer mới.
- Dependency/class identity rules.
- Tạo registry mới và validate trước khi publish.
- Chuyển in-flight requests sang registry mới theo policy.
- Đóng plugin resources/threads.
- Giải phóng references và class loader cũ khi không còn dùng.
- Chạy security/compatibility checks.

**Hot loading là một bài toán kiến trúc riêng**, không phải một flag của ServiceLoader.

### 10.6. Thread safety

`ServiceLoader` **không thread-safe**. Không chia sẻ một ServiceLoader mutable cho nhiều request threads rồi gọi `iterator()`/`stream()`/`reload()` đồng thời.

Cách dễ kiểm soát hơn:

1. Khám phá providers ở startup trên một thread.
2. Validate IDs/capabilities.
3. Tạo immutable map/list registry.
4. Đưa registry vào service qua constructor/atomic publication.
5. Chỉ thay registry theo một lifecycle được đồng bộ.
6. Không reload trong khi còn giữ iterators/streams cũ.

Nếu providers cũng không thread-safe, cần giới hạn concurrency hoặc tạo instances theo request/factory phù hợp; ServiceLoader không tự biến provider thành thread-safe.

---

## 11. Java 9+ module system: `uses` và `provides`

Java hiện đại có **JPMS (Java Platform Module System)**, cho phép đăng ký providers bằng **module-info.java**, thay vì phụ thuộc hoàn toàn vào classpath resource files.

### 11.1. Service module

~~~java
// module-info.java của module demo.api
module demo.api {
    exports demo.spi;
}
~~~

Service interface `demo.spi.TextPlugin` nằm trong module `demo.api`. Những modules cần compile với interface phải `requires demo.api`.

### 11.2. Host module

~~~java
// module-info.java của module demo.host
module demo.host {
    requires demo.api;
    uses demo.spi.TextPlugin;
}
~~~

**`uses` là thiết yếu cho named module gọi ServiceLoader** đối với service type này. Nếu thiếu, chương trình có thể gặp ServiceConfigurationError khi ServiceLoader được gọi từ named module.

**Host không cần `requires demo.upper` hoặc `requires demo.brackets`**. Việc phụ thuộc trực tiếp vào provider modules sẽ làm mất lợi ích SPI.

### 11.3. Upper provider module

~~~java
// module-info.java của module demo.upper
module demo.upper {
    requires demo.api;
    provides demo.spi.TextPlugin
        with demo.providers.upper.UppercasePlugin;
}
~~~

Provider class là public, implement TextPlugin và có public no-arg constructor; package implementation **không cần export** chỉ để ServiceLoader có thể khởi tạo provider qua module service binding.

### 11.4. Brackets provider module

~~~java
// module-info.java của module demo.brackets
module demo.brackets {
    requires demo.api;
    provides demo.spi.TextPlugin
        with demo.providers.brackets.BracketPlugin;
}
~~~

`provides ... with ...` mô tả provider nào implement service. Có thể khai báo nhiều classes sau `with` theo syntax module system. Ở đây giữ mỗi module một provider để phù hợp bài thực hành.

### 11.5. Lệnh compile/run modular

Nếu chuyển các source từ phần classpath sang layout module-aware:

~~~text
modular-src/
├── demo.api/
│   ├── module-info.java
│   └── demo/spi/TextPlugin.java
├── demo.host/
│   ├── module-info.java
│   └── demo/app/PluginHost.java
├── demo.upper/
│   ├── module-info.java
│   └── demo/providers/upper/UppercasePlugin.java
└── demo.brackets/
    ├── module-info.java
    └── demo/providers/brackets/BracketPlugin.java
~~~

Build theo từng module (các sources hiện có được đặt vào đúng module source tree):

~~~bash
mkdir -p mods/demo.api mods/demo.host mods/demo.upper mods/demo.brackets

javac -encoding UTF-8 --release 17 \
  -d mods/demo.api \
  modular-src/demo.api/module-info.java \
  modular-src/demo.api/demo/spi/TextPlugin.java

javac -encoding UTF-8 --release 17 --module-path mods \
  -d mods/demo.host \
  modular-src/demo.host/module-info.java \
  modular-src/demo.host/demo/app/PluginHost.java

javac -encoding UTF-8 --release 17 --module-path mods \
  -d mods/demo.upper \
  modular-src/demo.upper/module-info.java \
  modular-src/demo.upper/demo/providers/upper/UppercasePlugin.java

javac -encoding UTF-8 --release 17 --module-path mods \
  -d mods/demo.brackets \
  modular-src/demo.brackets/module-info.java \
  modular-src/demo.brackets/demo/providers/brackets/BracketPlugin.java

# Module launch, không dùng -cp.
java --module-path mods --module demo.host/demo.app.PluginHost
~~~

Đây là **cách chuyển các source đã có sang module-aware structure**, không phải lệnh chạy ngay khi chưa tạo source layout. Khi dùng named modules, `uses`/`provides` trong module-info là nguồn đăng ký chính. Không cần tạo `META-INF/services` cho từng provider module như cách classpath.

### 11.6. Kiểm thử modular thực tế

Một bộ JPMS thu gọn với cùng ý tưởng và hợp đồng service đã được kiểm thử riêng trên **OpenJDK 24.0.2, `--release 17`**:

~~~text
MODULAR_BOTH:
providers=2
ids=brackets,uppercase

MODULAR_ONE:
providers=1
ids=uppercase
~~~

Các dòng trên là output **của bộ kiểm thử JPMS thu gọn**, không phải stdout của `PluginHost` đầy đủ ở mục 8. Bộ test đặt cả `demo.upper` và `demo.brackets` trên module path rồi bỏ module `demo.brackets`; discovery nhận đúng số providers. Việc named module **`uses`** và provider modules **`provides`** hoạt động đã được xác nhận thực tế.

### 11.7. Khác biệt quan trọng giữa classpath và JPMS

| Khía cạnh | Classpath SPI | Named-module SPI |
| --- | --- | --- |
| Nơi đăng ký provider | `META-INF/services/<service name>` | `module-info.java` `provides ... with ...` |
| Host khai báo usage | Không cần module-info | `uses service` |
| API module dependency | `-cp api.jar` | `requires demo.api` |
| Plugin dependency | Provider compile với SPI JAR/classes | `requires demo.api` |
| Provider package | Public class theo classpath rule | Có thể encapsulated, không export package |
| Discovery | Theo class loader resources | Theo resolved modules/module layers |
| Ordering | Phụ thuộc class loader resource lookup | Theo module service discovery rules; không dùng làm business priority |
| Runtime install | Cần class-loader strategy | Có thể thiết kế custom ModuleLayer |
| Provider factory method | Không dùng trong classpath config model | Có thể dùng trong explicit named module theo Javadoc |

**Không dùng `ServiceLoader.loadInstalled()`** để tìm application plugin JAR bình thường: method đó dùng platform class loader và bỏ qua providers trên application classpath/module path theo contract được công bố.

### 11.8. ModuleLayer động

Java cung cấp `ServiceLoader.load(ModuleLayer layer, Class<S> service)` để tìm providers trong một module layer và các ancestor layers phù hợp. Nó **không** tìm providers trong unnamed modules.

Dùng khi ứng dụng có kiến trúc plugin modules/layers riêng. Việc tạo layer đúng nghĩa đòi giải quyết module dependencies, class loaders, readability, service binding và lifecycle. Không cần ModuleLayer custom chỉ để dùng hai providers cố định khi startup.

---

## 12. ClassLoader và identity: lỗi triển khai phổ biến nhất

### 12.1. ServiceLoader.load dùng context class loader

~~~java
ServiceLoader<TextPlugin> loader =
        ServiceLoader.load(TextPlugin.class);
~~~

Overload một tham số sử dụng **thread context class loader**. Trong nhiều ứng dụng console đơn giản, đó là application class loader và nhìn thấy JARs trên classpath.

Trong application servers, test runners, frameworks hoặc nhiều module layers, **thread context class loader có thể khác** loader dùng để định nghĩa TextPlugin, vì thế kết quả discovery cũng khác.

Có thể chọn explicit class loader:

~~~java
ServiceLoader<TextPlugin> loader =
        ServiceLoader.load(
                TextPlugin.class,
                TextPlugin.class.getClassLoader());
~~~

Điều này chỉ phù hợp nếu class loader được chọn có thể thấy các provider JARs/module context bạn muốn. Nếu plugins nằm trong child loader riêng, dùng loader/layer do plugin manager sở hữu thay vì mặc định dùng SPI class loader.

### 12.2. Cùng binary name không đồng nghĩa cùng class identity

Trong Java, class identity phụ thuộc:

~~~text
(binary name, defining ClassLoader)
~~~

Nếu `demo.spi.TextPlugin` có hai bản class được định nghĩa bởi hai class loaders khác nhau, chúng **không phải cùng một Java Class object**, dù tên bytecode giống hệt. Một provider implement “TextPlugin của loader B” có thể **không assignable** tới “TextPlugin của loader A”.

Điều này dễ xảy ra nếu mỗi plugin JAR đóng gói **một bản riêng của SPI class** và hệ thống dùng child-first loaders không được thiết kế đúng.

**Cách tốt:** Giữ SPI API trong module/JAR do host và plugin loaders cùng nhìn thấy theo parent delegation hoặc explicit module readability. Không tùy tiện shade/relocate service interface bên trong từng provider artifact.

### 12.3. ClassLoader leak

Nếu một plugin được tải bằng URLClassLoader riêng, những references sau có thể giữ loader cũ sống:

- Threads do plugin tạo.
- ThreadLocal values.
- Static fields trong thư viện chung trỏ đến objects plugin.
- ScheduledExecutor, event bus handlers, JMX registrations.
- Callback/listeners và registries.
- ServiceLoader cache/Provider references còn được giữ.
- Files/network connections/GC roots không được dọn.

Gọi **reload() không đảm bảo unload classes**. Nếu có hot plugin replacement, cần dừng plugin, close resources, unregister callbacks, loại references và quản lý class-loader lifecycle.

### 12.4. Không sử dụng remote classpath URLs không đáng tin

Javadoc ServiceLoader lưu ý nếu class loader có remote network URLs, việc tìm resource config có thể truy cập các URLs đó. Không tải provider jars/classes từ nguồn bên ngoài chưa kiểm chứng. Một class load/constructor đã là thực thi mã bên trong JVM với quyền của process.

---

## 13. Lựa chọn provider khi có nhiều implementations

### 13.1. Chính sách selection phải deterministic

Một hệ thống nhiều providers thường cần **khác biệt giữa discovery và selection**:

~~~text
Discovery:
  ServiceLoader tìm tất cả candidates hợp lệ trong environment.

Validation:
  Kiểm tra id/capability/version/compatibility.

Selection:
  Chọn provider theo config, priority, region hoặc feature policy.

Execution:
  Gọi operation của selected provider.

Lifecycle:
  Close/shutdown và report metrics.
~~~

**Không nên đặt toàn bộ selection vào thứ tự `iterator().next()`** khi không có contract rằng cái đầu tiên là tốt nhất.

### 13.2. Khi priority bằng nhau

Một comparator có tie-breaker:

~~~java
Comparator<TextPlugin> comparator =
        Comparator.comparingInt(TextPlugin::priority)
                .thenComparing(TextPlugin::id);
~~~

Nếu hai providers khác ID cùng priority, thứ tự theo id giúp deterministic. Nếu hai providers cùng id, host dùng `putIfAbsent` để **fail fast**. Trong production, có thể thêm validator cho version, capabilities và duplicated feature coverage.

### 13.3. Không phải mọi plugin đều cần chạy

Host demo gọi `apply` trên cả hai để chứng minh discovery. Nhưng trong hệ thống thật, nếu input cần một định dạng, chỉ nên gọi provider phù hợp:

~~~java
// MẢNH MINH HỌA nếu byId đã được tạo.
TextPlugin chosen = byId.get(requestedId);
if (chosen == null) {
    throw new IllegalArgumentException(
            "Unknown plugin: " + requestedId);
}
String result = chosen.apply(input);
~~~

Nếu `requestedId` đến từ untrusted input, phải validate/allowlist theo policy; không cho người ngoài chọn một provider có đặc quyền khác chỉ bằng chuỗi ID.

### 13.4. Provider fallback và lỗi

Hãy phân biệt:

- **No providers:** hệ thống không có capability; có thể fail fast hoặc disabled feature.
- **Requested ID missing:** trả NOT_FOUND/validation error.
- **Provider configuration broken:** ServiceConfigurationError; thường là deployment defect.
- **Provider init fails:** cần biết provider artifact/version/cause; có thể fail startup.
- **Provider execution fails:** là runtime failure của plugin; nên bao bằng policy/time budget, không tự động retry gây side effect.
- **Duplicate ID:** host configuration invalid, không nên chọn ngẫu nhiên.
- **Provider slow/unresponsive:** áp timeout/circuit breaker nếu thao tác có network/IO, không block host vô hạn.

Đừng gom cả sáu trường hợp vào một exception `"Plugin not available"` rồi làm mất nguyên nhân để điều tra.

### 13.5. Provider ưu tiên thấp có thể làm hỏng discovery?

Có. Dù host định chọn một provider khác, khi host cố tải toàn bộ provider list, một descriptor lỗi hoặc constructor throw có thể ném ServiceConfigurationError **trước khi selection hoàn tất**.

Các ứng dụng cần lỗi không lan rộng nên thực hiện plugin artifact validation từ deployment/startup, cô lập nguồn provider không đáng tin và quyết định rõ fail-fast/disable-plugin. **Không hứa ServiceLoader sẽ luôn bỏ qua provider hỏng và tiếp tục**; tài liệu không bảo đảm recovery trọn vẹn.

---

## 14. Phát hành bằng Maven/Gradle và lưu ý fat JAR

### 14.1. Các module build độc lập

Một dự án thực tế có thể có:

~~~text
text-spi/
text-host/          depends on text-spi
text-upper-plugin/  depends on text-spi
text-bracket-plugin/depends on text-spi
~~~

Host không phụ thuộc **compile-time** vào từng provider. Với deployment, provider JARs được gắn vào runtime classpath/module path của ứng dụng.

**Phân biệt** `compileOnly`/`implementation`/`runtimeOnly` của các build tools theo workflow cụ thể, nhưng nguyên tắc vẫn là **host compile với SPI**, còn deployment chọn providers.

### 14.2. Resources theo convention

Mỗi plugin project có:

~~~text
src/main/java/demo/providers/upper/UppercasePlugin.java
src/main/resources/META-INF/services/demo.spi.TextPlugin
~~~

Khi build đúng, file service descriptor được copy vào JAR tại path từ root archive. Nếu resource nằm dưới `src/main/java` mà build tool không copy, provider có thể biến mất khỏi discovery.

### 14.3. Fat JAR/shading và descriptor merging

Khi đóng nhiều provider JARs vào một uber JAR, hai files:

~~~text
META-INF/services/demo.spi.TextPlugin
~~~

có thể **trùng đường dẫn archive entry**. Nếu build tool chỉ lấy một file, ServiceLoader sẽ chỉ thấy một provider và “mất” provider còn lại.

Giải pháp: cấu hình **service descriptor merge/aggregation** của plugin build tương ứng (ví dụ Maven Shade ServicesResourceTransformer hoặc Gradle Shadow mergeServiceFiles, tùy phiên bản plugin), rồi kiểm tra **nội dung cuối** có cả hai FQCNs.

Không chỉ kiểm tra `.class` tồn tại; descriptor cuối phải liệt kê tất cả providers mong muốn.

### 14.4. Descriptor có nhiều entries

Cùng một JAR vẫn có thể khai báo nhiều providers:

~~~text
demo.providers.upper.UppercasePlugin
demo.providers.brackets.BracketPlugin
~~~

Nhưng khi đã tách ra hai JARs độc lập, cách tiện là mỗi JAR có descriptor riêng. ServiceLoader sẽ tìm các resources thích hợp qua class loader.

### 14.5. Resource encoding cần kiểm tra

Trên các shell/CI, cấu hình encoding khác nhau có thể tạo UTF-8 BOM hoặc nội dung sai. **Sử dụng UTF-8 không BOM cho service descriptor**, một provider name mỗi dòng, và test `jar tf`/resource contents. Không dùng Unicode invisible characters trong tên class.

---

## 15. Kiểm thử hệ thống plugin đa provider

### 15.1. Ma trận kiểm thử cơ bản

| Test | Runtime artifacts | Expected |
| --- | --- | --- |
| Không provider | api.jar + host.jar | discovered=0 |
| Một provider | api + host + brackets | discovered=1, brackets hoạt động |
| Hai providers | api + host + upper + brackets | discovered=2, cả hai chạy |
| Selection theo ID | upper hiện diện | selectedUppercase=JAVA SPI |
| ID không tồn tại | chỉ brackets | selectedUppercase=NOT_FOUND |
| Priority ordering | 10 và 20 | uppercase trước brackets |
| Reload cùng classpath | không đổi JAR set | afterReloadDescriptors giữ nguyên |
| Duplicate semantic ID | upper + duplicate | IllegalStateException |
| Descriptor class không tồn tại | bad.jar | ServiceConfigurationError |
| Descriptor thiếu | class có nhưng không config | Provider không được discover |
| Wrong class loader | loader không thấy provider | Không discover provider |
| Broken constructor | ctor throw | ServiceConfigurationError |
| Provider incompatible API | old/wrong SPI version | Linkage/instantiation/runtime failure |
| Fat JAR merge lỗi | descriptor bị ghi đè | Thiếu providers |
| JPMS two providers | uses + hai provides | Cả hai được phát hiện |
| JPMS one provider | uses + một provides | Chỉ provider được thấy |

**Những trường hợp đã chạy và PASS:** 0, 1, 2 providers; ID selection; priority; reload count; semantic duplicate; bad descriptor; JPMS two và one. Các trường hợp khác là **kế hoạch test mở rộng**, không được mô tả là đã chạy.

### 15.2. Contract tests dùng chung cho mọi provider

Mỗi provider nên vượt qua một bộ tests chuẩn:

- `id()` khác null/blank.
- `id()` ổn định giữa những lần gọi.
- `priority()` phù hợp range/semantics.
- `apply(input)` trả output không null nếu contract cấm null.
- Không tự thay đổi input data/shared state trái contract.
- Nếu output có encoding/locale rules, test Unicode/Locale.ROOT.
- Constructor không có side effect nặng hoặc nguy hiểm.
- Có test cho invalid input và error mapping.
- Có test concurrency nếu host gọi đồng thời.
- Có test resource closure nếu provider là AutoCloseable hoặc expose close.
- Không leak threads/class loaders qua lifecycle.

### 15.3. Packaging tests trước khi deploy

Với provider JAR:

1. Dùng `jar tf` kiểm tra `META-INF/services/...`.
2. Đọc file descriptor, xác nhận FQCN đúng.
3. Xác nhận classfile trong JAR có binary name và version đúng.
4. Chạy một host test với chỉ provider JAR đó.
5. Chạy host với hai/more providers.
6. Xác nhận runtime classpath và module path đúng.
7. Kiểm tra không duplicate SPI package/classes.
8. Nếu shading, test merged descriptor.
9. Nếu JPMS, kiểm tra `module-info` provides/uses.
10. Chạy Java17+ và JDK deployed runtime.
11. Nếu plugin từ đối tác, kiểm tra provenance/checksum/signature.
12. Chặn plugin không compatible version.

### 15.4. Regression tests trên classpath order

Trên classpath, thứ tự resource lookup có thể ảnh hưởng thứ tự discover; đừng test bằng cách assert provider đầu tiên cố định nếu không có rule. Test nên assert:

~~~text
Set discovered IDs = {"uppercase", "brackets"}
Ordered business priority = ["uppercase", "brackets"]
~~~

Khi đảo thứ tự upper.jar và brackets.jar trên classpath, host vẫn phải chọn theo priority/id. Điều này giảm lỗi “chạy máy này đúng, máy kia sai” do tình cờ classpath ordering.

### 15.5. Security tests

Với plugin JAR không do team core phát triển:

- Kiểm tra artifact source/provenance.
- Quét dependency vulnerabilities và malicious behavior.
- Kiểm tra API/permissions mà host cung cấp.
- Kiểm tra network/file/thread access theo threat model.
- Rate-limit plugin operations và có timeout.
- Xác minh không ghi logs chứa secrets/PII.
- Nếu code không đáng tin, **chạy trong process/container cách ly phù hợp**, không chỉ dựa vào interface.
- Test provider failure/interrupt/shutdown không làm treo host.

`ServiceLoader` là **discovery mechanism**, không phải security boundary. Plugin chạy trong JVM thường có quyền gần với ứng dụng chủ; đừng dùng SPI để chạy code hoàn toàn không đáng tin trong cùng process.

---

## 16. Logging, observability và lifecycle của plugin system

### 16.1. Metrics hữu ích

Khi production có nhiều providers, có thể theo dõi:

~~~text
plugin.discovery.count = 2
plugin.registry.count = 2
plugin.load.failure.count = 0
plugin.invocation.count{pluginId="uppercase"} = ...
plugin.invocation.errors{pluginId="brackets"} = ...
plugin.invocation.durationMs = ...
~~~

Các dòng là **ví dụ schema**, không phải stdout chương trình. Chỉ dùng labels có cardinality bị giới hạn như known plugin IDs; không gắn user IDs/request IDs không giới hạn.

### 16.2. Startup validation

Một startup process tốt:

~~~text
1. Load API and allowed provider artifacts
2. ServiceLoader discovery
3. Validate descriptors and constructors
4. Validate id uniqueness, versions, priorities
5. Validate configured required providers are present
6. Initialize resources and health check
7. Publish immutable plugin registry
8. Begin accepting requests
~~~

Nếu một bước thất bại, fail fast hoặc degrade theo policy được công bố. Không để ứng dụng báo READY khi một required plugin không có khả năng chạy.

### 16.3. Shutdown

Nếu provider giữ ExecutorService, sockets, files hoặc scheduled jobs, SPI nên có lifecycle contract (ví dụ một `close()` method rõ hoặc `AutoCloseable` và ownership rules). Khi host ngừng hoạt động:

1. Ngừng nhận công việc mới.
2. Hoàn thành/huỷ in-flight tasks theo policy.
3. Close các provider resources.
4. Unregister listeners/management beans.
5. Giải phóng class loader references nếu có dynamic plugin loaders.
6. Đảm bảo không leak threads.
7. Ghi audit/log outcome không chứa secrets.

`ServiceLoader.reload()` **không gọi `close()` cho các provider instances trước đó**. Nếu bạn thiết kế hot-reload, host phải tự quản lý cleanup.

### 16.4. Nguyên tắc một registry cho một lifecycle

Không truyền `ServiceLoader` mutable tới mọi request. Khám phá và validate ở startup rồi dùng một registry đã được tạo. Nếu cần đổi runtime provider set:

- Xây registry mới trong background/isolation.
- Validate tất cả providers mới.
- Publish registry bằng atomic reference sau khi sẵn sàng.
- Drain/close registry cũ.
- Không dùng iterator/stream từ loader cũ sau reload.
- Có rollback nếu provider mới thất bại.

Đó là kiến trúc bổ sung, không phải built-in feature của ServiceLoader.

---

## 17. So sánh với cách viết plugin không sử dụng ServiceLoader

### 17.1. Hardcoded switch

~~~java
// PHẢN VÍ DỤ:
switch (id) {
    case "uppercase": return new UppercasePlugin();
    case "brackets": return new BracketPlugin();
    default: throw new IllegalArgumentException();
}
~~~

Nhược điểm: host phải biết và compile với mọi implementation. Thêm provider có thể cần sửa/rebuild host.

### 17.2. Reflection với class name từ config

~~~java
// PHẢN VÍ DỤ: không có type-safe/validation/allowlist.
Class<?> clazz = Class.forName(userProvidedClassName);
Object plugin = clazz.getDeclaredConstructor().newInstance();
~~~

Cách này có thể tạo rủi ro security nếu class name đến từ untrusted input, còn compatibility và constructor rules phải tự viết. **ServiceLoader không biến plugin code thành an toàn**, nhưng tạo một contract discovery chuẩn và packaging rõ hơn so với nạp tên class ngẫu nhiên.

### 17.3. Dependency Injection container

Spring/CDI hoặc framework DI khác có thể tìm beans/implementations trong application context. Nếu ứng dụng đã có DI và mọi provider nằm trong cùng build/deploy, DI có thể phù hợp hơn.

ServiceLoader đặc biệt hữu ích cho **SPI JDK-style, thư viện tự mở rộng, công cụ command-line, pluggable codecs, drivers, modules**. Hai cách không loại trừ nhau; framework có thể bridge ServiceLoader providers vào DI registry.

### 17.4. ServiceLoader không giải quyết mọi bài toán plugin

| Vấn đề | ServiceLoader hỗ trợ | Cần tự xây/thêm |
| --- | --- | --- |
| Khám phá classes triển khai SPI | Có | Packaging đúng |
| Classpath service descriptors | Có | Tạo/merge resources |
| JPMS uses/provides | Có | Module configuration |
| Lazy loading và cache | Có | Lifecycle policy |
| `reload()` cache | Có | Hot JAR install/unload |
| Business priority | Không | `priority()` và sort |
| Semantic ID collision | Không | Registry validation |
| API version negotiation | Không | Compatibility policy |
| Sandboxing untrusted code | Không | Isolation/security architecture |
| Timeout/circuit breaker | Không | Execution boundary |
| Dependency injection | Không trực tiếp | DI/factory integration |
| Resource cleanup | Không | close/shutdown lifecycle |
| Monitoring/audit | Không | Metrics/logging layer |

---

## 18. Các lỗi phổ biến và cách khắc phục

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `discovered=0` dù có JAR | Thiếu `META-INF/services` | Kiểm tra `jar tf` |
| Descriptor có nhưng provider không thấy | FQCN sai | So khớp package/class |
| Provider class nằm trong wrong JAR | Class loader không thấy class | Kiểm tra runtime classpath |
| ServiceConfigurationError khi construct | Không có public no-args ctor | Sửa provider classpath SPI |
| ServiceConfigurationError is not caught | Code chỉ catch Exception | Bắt precise Error khi boundary cần |
| `ClassCastException`/not a subtype | API class bị định nghĩa ở loader khác | Shared SPI identity |
| `NoClassDefFoundError` | Thiếu provider dependencies | Package/deploy đầy đủ |
| `AbstractMethodError` | SPI mới không tương thích provider cũ | Semantic version/contract tests |
| Provider thứ hai không chạy | Fat JAR ghi đè descriptor | Merge service resources |
| Duplicate plugin id | Hai classes trả cùng id | Fail fast/rename/reconfigure |
| Chạy provider sai | Chọn theo discovery order | Policy priority/ID |
| `findFirst()` trả provider bất ngờ | Ordering không phải business contract | Explicit selection |
| `reload()` vẫn thấy số cũ | Class loader không thấy JAR mới | Correct loader/layer lifecycle |
| `reload()` rồi iterator lỗi | Iterator cũ bị invalidated | Tạo iterator/stream mới |
| ConcurrentModificationException | Reload trong khi đang duyệt | Đồng bộ lifecycle |
| Memory leak sau reload | Providers giữ threads/references | Close/clear registries |
| Named module không tìm provider | Thiếu `uses`/`provides` | Sửa module-info |
| Provider module không được resolve | Module path/service binding sai | Kiểm tra module resolution |
| Dùng loadInstalled cho app jars | Platform loader không thấy app jars | Dùng load phù hợp |
| ServiceProvider.get ném lỗi | Constructor/provider factory fail | Validate packaging, log cause |
| Catch(Error) rồi continue mù quáng | Che lỗi môi trường | Fail fast/isolation policy |
| Plugin tự log API keys | Secret leak | Restrict capabilities/log redaction |
| Hot-update JAR đang chạy gây hành vi lạ | Classloader/classes chưa được reload đúng | Restart hoặc managed loader |
| Provider quá chậm | Không có timeout | Budget/circuit breaker |
| Provider state race | Provider không thread-safe | Contract/instance strategy |
| Java code build pass nhưng module fail | Thiếu requires/uses | Kiểm thử JPMS riêng |

### 18.1. Cách debug theo thứ tự hiệu quả

Nếu providers không xuất hiện:

1. In runtime classpath/module path có kiểm soát.
2. Xác minh JAR thực sự có trong process/class loader đang dùng.
3. Kiểm tra `jar tf provider.jar`.
4. Kiểm tra entry `META-INF/services/<SPI binary name>`.
5. Kiểm tra nội dung FQCN hợp lệ và UTF-8.
6. Kiểm tra provider public concrete class + constructor hoặc named-module provider rules.
7. Kiểm tra provider implements **cùng Class object** của SPI.
8. Kiểm tra TCCL (`Thread.currentThread().getContextClassLoader()`).
9. Kiểm tra `module-info` uses/provides nếu JPMS.
10. Bắt và báo root cause của ServiceConfigurationError.
11. Test với một provider đơn trước rồi thêm provider thứ hai.
12. Test ID uniqueness và priority policy.

**Không khuyên reflection scan tất cả classpath packages** như một cách sửa nhanh. Nó có thể tốn kém, sai module semantics và tăng security surface.

---

## 19. Bài tập thực hành

1. Chạy đầy đủ ba case zero/one/two và đối chiếu stdout với bài.
2. Xóa `brackets.jar` khỏi classpath, không sửa host, kiểm tra chỉ còn uppercase.
3. Đảo thứ tự hai provider JARs trên classpath và kiểm tra business sort vẫn đúng.
4. Thêm một provider mới `PrefixPlugin` có id prefix, priority=15; đóng JAR riêng và descriptor.
5. Gắn PrefixPlugin vào runtime classpath, xác nhận discovered=3.
6. Thêm provider priority=10 với ID khác, kiểm tra tie-breaker theo id.
7. Tạo provider `id()` trả blank, kiểm tra host fail fast.
8. Tạo hai classes khác nhau cùng trả id uppercase, xác nhận duplicate semantic ID.
9. Liệt kê JAR entries bằng `jar tf`, xác minh descriptor có trong provider JAR.
10. Xóa descriptor nhưng giữ `.class`, kiểm tra ServiceLoader không tự scan class.
11. Đổi một ký tự trong FQCN của descriptor và quan sát ServiceConfigurationError.
12. Tạo provider có private no-arg constructor trên classpath và test failure.
13. Tạo provider constructor ném RuntimeException và test ServiceConfigurationError/cause.
14. Tạo host không import provider classes, kiểm tra `javac` compile chỉ với API.
15. Refactor host chọn ID qua command-line args thay vì hardcode uppercase.
16. Thêm whitelist provider IDs được phép theo config.
17. Thêm `supportedFormats()` vào SPI qua một default method tương thích và chạy contract tests.
18. Thử một thay đổi SPI breaking rồi xác nhận provider cũ không compatible.
19. Thêm provider factory SPI để khởi tạo object tốn kém theo nhu cầu.
20. Dùng ServiceLoader.iterator thay stream, giải thích lazy/caching khác nhau.
21. Thử Provider.type() để inspect annotation trước Provider.get().
22. Gọi loader.reload() và tạo iterator mới; không dùng iterator cũ.
23. Viết test chứng minh `reload()` không tự add JAR ngoài classpath.
24. Gói cả hai plugins thành fat JAR, merge descriptors và kiểm tra đủ hai entries.
25. Tạo bốn module-info.java với uses/provides, biên dịch/running JPMS.
26. Bỏ `uses` ở host module và xem lỗi.
27. Bỏ module provider khỏi module path và xem provider count thay đổi.
28. Thử `ServiceLoader.load(ModuleLayer, TextPlugin.class)` trong một custom layer được quản lý.
29. Thiết kế interface lifecycle close() và cleanup khi shutdown.
30. Thử một provider không thread-safe với concurrent requests, xác định cần synchronization.
31. Đặt time budget khi plugin thực hiện I/O và đo failure response.
32. Xây plugin artifact validation trước deploy.
33. Test class loader copy riêng SPI gây class identity mismatch trong sandbox.
34. Kiểm tra không log secrets/PII trong plugin errors.
35. Thiết kế registry immutable và hot-swap bằng atomic publication, có drain state.
36. So sánh ServiceLoader với DI container trong một ứng dụng của bạn.
37. Viết test cho `findFirst()` không dùng làm business priority.
38. Kiểm tra đường dẫn `src/main/resources/META-INF/services/...` trong Maven/Gradle.
39. Thiết kế ma trận compatibility Java 17/21/26 và SPI v1/v2.
40. Viết runbook khi plugin được phát hành nhưng host không discover.

---

## 20. Checklist trước khi đưa vào môi trường thật

- [ ] Service interface nằm trong API artifact nhỏ, ổn định.
- [ ] Host compile chỉ phụ thuộc SPI, không import implementation classes.
- [ ] Provider compile theo cùng public SPI contract và version.
- [ ] Với classpath, provider là public concrete class có public no-arg constructor.
- [ ] Resource `META-INF/services/<full binary service name>` có trong từng provider JAR.
- [ ] Descriptor được ghi UTF-8 và chứa full binary names chính xác.
- [ ] Maven/Gradle resource copying được kiểm tra trong JAR cuối.
- [ ] Fat JAR/shading merge service descriptors, không ghi đè.
- [ ] Đã chạy zero-provider case hoặc có mandatory-provider fail-fast policy.
- [ ] Đã chạy one-provider và multiple-provider cases.
- [ ] Host validate id nonblank và semantic uniqueness.
- [ ] Host chọn provider bằng config/priority/ID, không dựa discovery order.
- [ ] Có tie-breaker deterministic khi priority bằng nhau.
- [ ] Không tự assume `findFirst()` là provider ưu tiên.
- [ ] Có cause logging cho ServiceConfigurationError với dữ liệu đã redacted.
- [ ] Không swallow provider configuration failures.
- [ ] Provider runtime errors có isolation/timeout/retry policy.
- [ ] `ServiceLoader.stream()` và Provider.get() được hiểu đúng.
- [ ] Provider initialization không tạo side effects nguy hiểm.
- [ ] Không chia sẻ ServiceLoader mutable giữa threads không đồng bộ.
- [ ] `reload()` không được coi là hot-install hoặc automatic close.
- [ ] Có lifecycle close/unregister để tránh classloader/thread leaks.
- [ ] TCCL/classloader visibility được kiểm thử trong môi trường triển khai.
- [ ] Tránh bundle nhiều copies khác identity của SPI class.
- [ ] Nếu dùng JPMS: `requires`, `uses`, `provides` khai báo đúng.
- [ ] Provider packages có thể encapsulated trong named modules.
- [ ] Không phụ thuộc `loadInstalled` để tìm application plugins.
- [ ] API binary compatibility và Java runtime versions được kiểm thử.
- [ ] Plugin JAR từ nguồn tin cậy; supply-chain controls phù hợp.
- [ ] Plugin code không đáng tin không chạy cùng JVM nếu thiếu isolation.
- [ ] Không expose secrets/credentials tới mọi provider.
- [ ] Logs và metrics có cardinality giới hạn, không lộ user IDs.
- [ ] Deployment có canary/rollback/health checks cho plugin artifacts.
- [ ] Các tests xấu: duplicate ID, missing class, missing descriptor, missing dependency.
- [ ] Trước khi báo READY, required providers đã pass validation/health checks.
- [ ] Có runbook khi ServiceLoader tìm không đủ providers.

## Kết luận

**ServiceLoader là cách hiện hành, tiêu chuẩn và type-safe ở mức SPI để tạo hệ mở rộng nhiều provider trong Java.** Chỉ cần một **API chung**, các provider JARs hoặc named modules độc lập, cùng metadata cấu hình đúng, host có thể khám phá 0/1/n implementations **mà không import cụ thể implementation classes**.

Để chuyển từ demo thành production system, quan trọng nhất là: **contract và version ổn định**, resource/module packaging chính xác, selection deterministic theo ID/priority, fail-fast với semantic duplicate/broken descriptors, hiểu lazy/cache/reload, kiểm soát class loaders và provider lifecycle, bảo mật nguồn plugin, và kiểm thử môi trường thực.

Bộ thực hành đã được kiểm chứng trên OpenJDK 24.0.2 với `--release 17`: zero/one/two provider JARs cho kết quả chính xác, duplicate ID và bad descriptor bị chặn, và **JPMS uses/provides với hai module providers** cũng hoạt động. Điều này minh họa rõ ràng lợi ích mở rộng của Java SPI: **thêm/bớt implementation thông qua deployment artifacts, không sửa mã host**.

**Tài liệu chính thức còn được hỗ trợ:**

- [ServiceLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceLoader.Provider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html)
- [ServiceConfigurationError — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceConfigurationError.html)
- [Module system — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [ModuleLayer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [URLClassLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLClassLoader.html)
- [JAR file specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)