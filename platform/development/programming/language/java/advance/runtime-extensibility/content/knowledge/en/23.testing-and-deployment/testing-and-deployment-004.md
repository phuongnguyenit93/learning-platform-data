# Kiểm thử phụ thuộc trùng phiên bản, tài nguyên trùng và hợp đồng bị đóng gói lặp

## 1. Mục tiêu: kiểm thử bản đóng gói thật, không chỉ mã nguồn

Trong một hệ plugin Java, quá trình biên dịch thành công **không bảo đảm** các JAR khi triển khai sẽ nạp đúng lớp, tài nguyên và giao diện SPI. Một plugin có thể dùng thư viện phiên bản A lúc build nhưng lại gặp phiên bản B lúc chạy. Hai JAR có thể cùng chứa `config/plugin.properties` hoặc `META-INF/services/...`; một API chung có thể bị đóng gói thêm lần nữa bên trong plugin. Những vấn đề này thường chỉ lộ ra khi host thực sự dùng classloader và các artifact sau đóng gói.

Bài học tập trung vào **ba nhóm xung đột cần kiểm thử tách biệt**:

1. **Phụ thuộc trùng phiên bản / duplicate classes:** nhiều JAR chứa cùng tên nhị phân của lớp, ví dụ `demo.lib.Version` nhưng bytecode hoặc API khác nhau; loader cuối cùng chọn bản nào?
2. **Tài nguyên trùng đường dẫn:** nhiều JAR cùng chứa `config/plugin.properties`, `META-INF/services/demo.api.Codec` hoặc metadata cấu hình khác; lời gọi lấy *một* tài nguyên khác gì với lấy *tất cả*?
3. **Hợp đồng bị đóng gói lặp (duplicate API/SPI contract):** lớp `demo.api.Codec` có mặt cả trong host và plugin. Nếu các classloader **định nghĩa hai bản riêng**, provider có thể không tương thích với kiểu `Codec` mà host yêu cầu, dù cùng tên gói và phương thức.

Đây là những **lỗi của topology nạp lớp và artifact**, không phải ba cách gọi khác nhau của một lỗi. Cần kiểm thử cả cấu trúc JAR, kết quả runtime và cơ chế nạp thực tế.

### Cùng tên không đồng nghĩa cùng lớp

Định danh runtime của một lớp Java phụ thuộc vào **tên nhị phân và classloader đã định nghĩa lớp**. Một `demo.api.Codec` do loader của host định nghĩa và một `demo.api.Codec` do loader của plugin định nghĩa có thể là **hai kiểu JVM khác nhau**. Khi đó, việc lớp provider “implements Codec” chỉ đúng đối với bản `Codec` mà chính lớp provider nhìn thấy.

Ngược lại, **cùng classloader** chỉ định nghĩa một lớp mang cùng tên nhị phân một lần trong cùng namespace. Nếu có hai JAR với `demo.lib.Version` trên cùng đường tìm kiếm, classloader thường chọn một định nghĩa theo chính sách tìm kiếm; nó **không tự hòa trộn hai phiên bản**. Ngay cả khi việc chạy không ném lỗi, một bản được chọn âm thầm cũng có thể tạo sai lệch nghiệp vụ.

## 2. Phân biệt các kiểu va chạm

| Hiện tượng | Bề mặt va chạm | Biểu hiện có thể gặp | Điều cần kiểm thử |
|---|---|---|---|
| Hai bản `demo.lib.Version` trong hai JAR | **Class binary name** và classloader | Chọn nhầm bản, `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError` hoặc khác hành vi | Class được loader nào định nghĩa? Đến từ artifact nào? |
| Hai `config/plugin.properties` | **Resource path** | Đọc nhầm cấu hình, lấy một trong nhiều bản, dữ liệu bị đè khi tạo fat JAR | `getResource` so với `getResources`, nội dung từng URL và chính sách merge |
| Hai `META-INF/services/demo.api.Codec` | **Service descriptor path** | Provider thiếu/trùng tên, `ServiceConfigurationError`, thứ tự khác kỳ vọng | Descriptor trong từng artifact và kết quả `ServiceLoader` thật |
| API `demo.api.Codec` nằm trong host lẫn plugin | **Class identity** | `ClassCastException`, “not a subtype”, `ServiceConfigurationError` | `hostApi == pluginApi` và `hostApi.isAssignableFrom(providerType)` |
| Package trùng trong JPMS | **Module/package graph** | `ResolutionException`, `LayerInstantiationException` hoặc khó phân giải dependency | Module path, layer, loader và split packages |
| Cùng phiên bản nhưng bytecode/tài nguyên khác | **Artifact integrity** | Runtime không tương ứng lockfile hoặc build đã ký | Hash của JAR, manifest và nội dung thực tế |

Cần phân biệt **mức độ trùng**: việc hai JAR cùng chứa `META-INF/MANIFEST.MF` hoặc `META-INF/services/...` không phải lúc nào cũng là bug. Nhưng **cùng đường dẫn** buộc hệ thống phải có chính sách xử lý, kiểm thử được khi merge hoặc load. Ngược lại, hai bản của **service interface** bị định nghĩa bởi hai loader khác nhau thường là lỗi ranh giới API trong hệ SPI có host/provider tương tác trực tiếp.

## 3. Lớp trùng phiên bản: phân tích theo classloader

### 3.1. Parent-first, child-first và thứ tự JAR

`URLClassLoader` thông dụng có cơ chế ủy quyền **parent-first** cho việc nạp lớp; loader con tìm cha trước, sau đó tìm các URL của mình. Khi các class trùng tên nằm **trong cùng đường tìm kiếm của một loader**, việc ưu tiên URL/classpath có thể quyết định bản được nạp. Với hai plugin loader riêng biệt, mỗi loader có thể thấy một bản dependency khác nhau.

```text
                       Host API loader
                         demo.api.Codec
                        /              \
            PluginLoader A             PluginLoader B
            plugin-a.jar               plugin-b.jar
            demo.lib.Version v1        demo.lib.Version v2
            demo.plugin.CodecPlugin    demo.plugin.CodecPlugin
                 |                           |
         implements host Codec        implements host Codec
```

Điều kiện quan trọng là cả hai plugin **dùng chung một bản hợp đồng `demo.api.Codec` từ host**, nhưng có thể định nghĩa `demo.lib.Version` riêng. Nếu host vô tình đặt cả `demo.lib.Version` phiên bản v1 vào classpath cha, cơ chế parent-first có thể khiến **cả hai plugin đều dùng v1**, bất kể JAR riêng của B chứa v2.

Không áp dụng quy tắc “JAR ở trước sẽ thắng” cho **mọi** custom classloader. Tùy policy ủy quyền, module path và cơ chế đóng gói, lớp thắng có thể khác. Kiểm thử phải sử dụng **đúng loader topology production**, không chỉ classpath đơn giản của unit test.

### 3.2. Khi nào lỗi xuất hiện?

- Nếu v1 và v2 cùng phương thức nhưng hành vi khác, chương trình có thể **chạy không lỗi nhưng cho kết quả sai**.
- Nếu mã plugin đã được biên dịch dựa trên `Version.newMethod()` nhưng runtime nạp bản cũ không có phương thức, việc phân giải liên kết khi sử dụng có thể gây `NoSuchMethodError`.
- Nếu phụ thuộc bị thiếu hoặc class cần thiết không tìm được, có thể gặp `ClassNotFoundException` trong lookup phản chiếu hoặc `NoClassDefFoundError` khi JVM cố sử dụng lớp cần thiết.
- Nếu chữ ký interface/implementation thay đổi không tương thích, có thể gặp `AbstractMethodError` hoặc lỗi liên kết/kiểu khác.

**Đừng dựa vào thông báo lỗi để kết luận chắc chắn tên JAR gây ra nó.** Ghi lại `Class.getClassLoader()`, `Class.getModule()` và, nếu được phép, `ProtectionDomain.getCodeSource()` để kiểm tra nguồn. `CodeSource` có thể là `null` hoặc không đủ thông tin trong một số môi trường; một classloader có thể được cấu hình tùy biến.

### 3.3. Build-time dependency resolution không phải runtime resolution

Maven/Gradle thường chọn phiên bản dependency tại thời điểm giải quyết cấu hình build. Nhưng một plugin manager có thể tự mở thêm JAR ngoài classpath mà dependency graph của host không phản ánh hết. Ngược lại, plugin có thể đóng gói fat JAR/shaded JAR chứa thêm những lớp ngoài dự kiến.

Do đó cần kết hợp **dependency graph**, **JAR content**, **classloader source** và **integration test chạy đúng artifact**. Chỉ nhìn `mvn dependency:tree` chưa chứng minh `URLClassLoader` của host sẽ chọn bản thư viện nào.

## 4. Tài nguyên trùng: getResource, getResources và merge

### 4.1. Tệp tài nguyên không có class identity

Resource được tìm theo **tên đường dẫn**, ví dụ:

```text
config/plugin.properties
META-INF/services/demo.api.Codec
log-config.xml
META-INF/some-framework.index
```

Tài nguyên **không** được kiểm tra subtype như một lớp. Nếu hai JAR chứa cùng đường dẫn, `ClassLoader.getResource("config/plugin.properties")` trả về **một** URL được tìm thấy; `getResources("config/plugin.properties")` trả về **Enumeration** các URL được loader nhìn thấy. Với `URLClassLoader` chuẩn, thứ tự các URL cung cấp một phần hành vi tìm kiếm; với loader tùy biến, packaging và ủy quyền, không nên dựa vào thứ tự không được hợp đồng ứng dụng đảm bảo.

Để xem *tất cả* cấu hình:

```java
// Đoạn minh họa trong method cho phép IOException.
Enumeration<URL> urls = loader.getResources("config/plugin.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    System.out.println(url);
}
```

Đoạn này cần import `java.net.URL`, `java.util.Enumeration` và có `loader` phù hợp. Kết quả URL phụ thuộc máy và đường dẫn nên không thể đưa stdout cố định ở đây. **In danh sách URL** là một kiểm tra quan trọng để phân biệt “không thấy”, “chỉ thấy một” và “thấy nhiều”.

### 4.2. Không tùy tiện merge mọi tài nguyên

Một số tệp có thể cần **gộp nội dung có hiểu biết về định dạng** (ví dụ nhiều `META-INF/services/<service-name>`). Tài nguyên cấu hình lại có thể cần **chọn bản có ưu tiên**, fail-fast khi trùng hoặc phân vùng theo tên plugin. Không có quy tắc merge chung cho mọi loại tài nguyên.

Tình huống thường gặp với **uber/fat JAR**: khi công cụ build gom nhiều JAR làm một, hai entry cùng đường dẫn có thể bị bỏ mất, ghi đè hoặc được xử lý bằng một transformer/plugin đặc biệt. Không được giả định chỉ vì hai dependency có service descriptor thì JAR cuối cùng giữ đủ provider của cả hai. Kiểm thử **artifact cuối cùng** quan trọng hơn kiểm thử các JAR nguồn riêng lẻ.

### 4.3. META-INF/services là một trường hợp riêng

Để công bố SPI trên classpath:

```text
Tệp: META-INF/services/demo.api.Codec
Nội dung:
demo.plugin.CodecPlugin
```

Tên file là **tên nhị phân của service interface**; mỗi dòng provider hợp lệ là tên nhị phân của lớp triển khai. `ServiceLoader` có thể đọc nhiều tệp descriptor cùng tên trong các JAR mà loader nhìn thấy. Provider có tên trùng có quy tắc xử lý trong ServiceLoader; nhưng đừng dùng việc loại trùng ấy để che một lỗi packaging, nhất là khi các JAR chứa **hai class khác nhau với cùng tên provider**.

Một tệp descriptor có nội dung hợp lệ chưa chứng minh provider tạo được. Sai classloader, thiếu class, thiếu constructor/factory hợp lệ hoặc hai bản service interface sẽ gây lỗi khi thực sự duyệt ServiceLoader.

## 5. Hợp đồng SPI bị đóng gói lặp: lỗi nguy hiểm nhất khi tách loader

### 5.1. Hai bản demo.api.Codec không phải một hợp đồng duy nhất

Giả sử host có:

```java
package demo.api;

public interface Codec {
    String id();
}
```

Plugin biên dịch cùng một source interface và đóng cả `demo/api/Codec.class` vào JAR của mình. Nếu classloader của plugin có policy **child-first cho package demo.api**, nó có thể định nghĩa bản `Codec` riêng. Khi đó:

```text
Host's demo.api.Codec          (host loader)
Plugin's demo.api.Codec        (child-first loader)
              |
     CodecPlugin implements plugin Codec

Host Codec.class.isAssignableFrom(CodecPlugin.class) == false
```

Dù `Codec.class.getName()` và bản plugin cùng trả `demo.api.Codec`, **class identity khác nhau**. `ServiceLoader.load(Codec.class, pluginLoader)` nhận kiểu service từ host nhưng gặp provider không phải subtype của kiểu đó và có thể ném `ServiceConfigurationError`. Một phép cast thủ công có thể ném `ClassCastException`.

**Không hiểu nhầm:** sự hiện diện vật lý của `Codec.class` trong plugin JAR **chưa chắc** khiến hai bản được định nghĩa. Nếu loader dùng parent-first và parent đã có `Codec`, class trong JAR plugin có thể bị bỏ qua. Tuy nhiên, đóng gói duplicate vẫn là rủi ro phát hành vì topology có thể thay đổi và dễ gây bất tương thích. Kiểm thử phải phát hiện **cả trùng file khi đóng gói** và **trùng class identity lúc chạy**.

### 5.2. Quy tắc đóng gói hợp đồng

- Giữ một API/SPI ổn định do host hoặc module chung quản lý, chẳng hạn `demo.api.Codec`.
- Plugin **compile against** API nhưng không đóng thêm bản API riêng vào plugin JAR khi host sẽ cấp API đó.
- Chọn rõ policy ủy quyền: package hợp đồng thường là **parent-first** ngay cả khi dependency implementation cần child-first.
- Không coi các class có tên/phương thức giống nhau là tương thích. Dùng `==` trên `Class<?>`, `isAssignableFrom` và thử `ServiceLoader` thật.
- Với JPMS, xem xét module readability, exports, package ownership và layer. Tách layer không tự chữa lỗi nhân bản hợp đồng.

## 6. Ví dụ Java 17+ hoàn chỉnh: ba loại va chạm trong một lần chạy

Ví dụ tạo **hai plugin JAR riêng**, mỗi JAR chứa phiên bản khác nhau của `demo.lib.Version` nhưng cùng triển khai hợp đồng `demo.api.Codec` do host cung cấp. Mỗi JAR cũng chứa một `config/plugin.properties` cùng đường dẫn để kiểm thử resource collision.

Sau đó ví dụ tạo **bad-plugin.jar** cố tình đóng gói thêm `demo/api/Codec.class` và dùng custom classloader child-first chỉ cho `demo.api.`. Host sẽ chứng minh: trùng class file biến thành **trùng class identity** khi policy nạp thực sự định nghĩa API ở loader con.

### 6.1. Cấu trúc thư mục

```text
duplicate-demo/
├── api/demo/api/Codec.java
├── lib-v1/demo/lib/Version.java
├── lib-v2/demo/lib/Version.java
├── plugin/demo/plugin/CodecPlugin.java
├── host/Host.java
└── resources/
    ├── a/
    │   ├── config/plugin.properties
    │   └── META-INF/services/demo.api.Codec
    └── b/
        ├── config/plugin.properties
        └── META-INF/services/demo.api.Codec
```

Các thư mục đầu ra `out/...` và `jars/...` được tạo bằng lệnh build ở mục 6.7; không nằm trong source tree ban đầu.

### 6.2. Hợp đồng dùng chung: api/demo/api/Codec.java

```java
package demo.api;

public interface Codec {
    String id();
}
```

**Chỉ một bản** API nằm trên application classpath của host. Hai plugin có thể tham chiếu interface này nhờ classloader cha.

### 6.3. Hai phiên bản thư viện: cùng tên nhị phân, khác hành vi

**lib-v1/demo/lib/Version.java:**

```java
package demo.lib;

public final class Version {
    private Version() { }

    public static String text() {
        return "v1";
    }
}
```

**lib-v2/demo/lib/Version.java:**

```java
package demo.lib;

public final class Version {
    private Version() { }

    public static String text() {
        return "v2";
    }
}
```

Cả hai tạo cùng một `demo/lib/Version.class` nhưng thân phương thức `text()` khác nhau. Trên một loader dùng chung, chỉ một định nghĩa thắng. Trên **hai loader riêng**, v1 và v2 có thể cùng tồn tại đúng như được dự tính.

### 6.4. Provider dùng API chung: plugin/demo/plugin/CodecPlugin.java

```java
package demo.plugin;

import demo.api.Codec;
import demo.lib.Version;

public final class CodecPlugin implements Codec {
    public CodecPlugin() {
    }

    @Override
    public String id() {
        return "codec-" + Version.text();
    }
}
```

Provider được biên dịch chống lại `lib-v1`, trong khi plugin B đóng gói `lib-v2`. Vì hai phiên bản vẫn giữ **cùng public method signature**, class được liên kết thành công và kết quả runtime phụ thuộc phiên bản `Version` mà loader thực tế chọn.

Nếu v2 thay đổi chữ ký không tương thích (ví dụ xóa `text()`) thì thử nghiệm có thể thất bại bằng lỗi liên kết ở lần gọi `id()`, minh họa khác biệt giữa hành vi sai âm thầm và lỗi runtime.

### 6.5. Hai bộ resource có đường dẫn trùng

**resources/a/config/plugin.properties:**

```properties
name=A
```

**resources/b/config/plugin.properties:**

```properties
name=B
```

Cả hai JAR đều có `config/plugin.properties`, nhưng nội dung khác nhau. Host sẽ dùng `getResources` và đọc từng tệp để chứng minh tìm được **cả A và B**, thay vì chỉ quan sát `getResource` trả một URL.

**resources/a/META-INF/services/demo.api.Codec** và **resources/b/META-INF/services/demo.api.Codec** đều chứa:

```text
demo.plugin.CodecPlugin
```

Hai provider ở **hai loader riêng** dù có cùng tên nhị phân vẫn là các class khác nhau. Test sẽ lấy `CodecPlugin` từ A/B, đối chiếu class identity và kết quả cung cấp dịch vụ.

### 6.6. Host và child-first loader để tái hiện duplicate contract

**host/Host.java:**

```java
import demo.api.Codec;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Properties;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Host {
    private static URL jar(String filename) throws Exception {
        return Path.of("jars", filename).toAbsolutePath().toUri().toURL();
    }

    private static String providers(ClassLoader loader) {
        List<String> names = new ArrayList<>();
        for (Codec codec : ServiceLoader.load(Codec.class, loader)) {
            names.add(codec.id());
        }
        Collections.sort(names);
        return names.toString();
    }

    private static String version(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("demo.lib.Version");
        return (String) type.getMethod("text").invoke(null);
    }

    private static List<String> resources(ClassLoader loader)
            throws Exception {
        Enumeration<URL> urls =
                loader.getResources("config/plugin.properties");
        List<String> names = new ArrayList<>();

        while (urls.hasMoreElements()) {
            Properties properties = new Properties();
            try (InputStream in = urls.nextElement().openStream()) {
                properties.load(in);
            }
            names.add(properties.getProperty("name"));
        }

        Collections.sort(names);
        return names;
    }

    static final class ChildFirstApiLoader extends URLClassLoader {
        ChildFirstApiLoader(URL url, ClassLoader parent) {
            super(new URL[] {url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.startsWith("demo.api.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    try {
                        type = findClass(name);
                    } catch (ClassNotFoundException notInJar) {
                        type = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = Host.class.getClassLoader();
        URL jarA = jar("plugin-a.jar");
        URL jarB = jar("plugin-b.jar");
        URL badJar = jar("bad-plugin.jar");

        try (URLClassLoader a = new URLClassLoader(
                        new URL[] {jarA}, parent);
             URLClassLoader b = new URLClassLoader(
                        new URL[] {jarB}, parent);
             URLClassLoader combinedA = new URLClassLoader(
                        new URL[] {jarA, jarB}, parent);
             URLClassLoader combinedB = new URLClassLoader(
                        new URL[] {jarB, jarA}, parent);
             ChildFirstApiLoader bad = new ChildFirstApiLoader(
                        badJar, parent)) {

            System.out.println("a=" + providers(a));
            System.out.println("b=" + providers(b));

            Class<?> fromA = a.loadClass("demo.plugin.CodecPlugin");
            Class<?> fromB = b.loadClass("demo.plugin.CodecPlugin");
            System.out.println("provider.class.same=" + (fromA == fromB));

            System.out.println("combined.aFirst=" + version(combinedA));
            System.out.println("combined.bFirst=" + version(combinedB));
            System.out.println("resources=" + resources(combinedA));

            Class<?> duplicateApi = bad.loadClass("demo.api.Codec");
            Class<?> badProvider = bad.loadClass("demo.plugin.CodecPlugin");

            System.out.println("bad.api.same="
                    + (duplicateApi == Codec.class));
            System.out.println("bad.assignable="
                    + Codec.class.isAssignableFrom(badProvider));

            try {
                ServiceLoader.load(Codec.class, bad).findFirst()
                        .orElseThrow();
                System.out.println("bad.spi=found");
            } catch (ServiceConfigurationError error) {
                System.out.println("bad.spi=ServiceConfigurationError");
            }
        }
    }
}
```

Giải thích mã:

- `a` và `b` đều **nhờ host loader nạp `demo.api.Codec`**, nhưng định nghĩa plugin/dependency từ JAR riêng. Do đó `ServiceLoader.load(Codec.class, a/b)` tạo được provider, trả `codec-v1` và `codec-v2`.
- `fromA == fromB` là `false` vì hai loader đã định nghĩa hai bản `demo.plugin.CodecPlugin`, dù cùng tên nhị phân. Việc này **không làm mất tương thích SPI** vì cả hai đều implements API của host.
- `combinedA` chứa A rồi B, còn `combinedB` chứa B rồi A. Với `URLClassLoader` và đường nạp ở ví dụ, `demo.lib.Version` của JAR đầu tiên được chọn: đó là bằng chứng phải kiểm tra thứ tự và chính sách nạp khi có dependency trùng.
- `resources(combinedA)` dùng `getResources`, đọc `name` của **hai** resource và sắp xếp để stdout ổn định. Không dựa vào thứ tự các URL do bất kỳ loader khác cung cấp.
- `bad-plugin.jar` chứa cả `demo/api/Codec.class`. `ChildFirstApiLoader` chỉ ưu tiên phiên bản trong JAR đối với tên `demo.api.`, còn những tên khác vẫn ủy quyền bình thường.
- Bản API trong bad loader không phải `Codec.class` của host, nên `bad.api.same=false`. Provider do bad loader định nghĩa implements **bản Codec của bad loader**, làm `isAssignableFrom` trả false.
- Khi host yêu cầu `ServiceLoader` tạo provider cho **host Codec.class** qua bad loader, provider không phải subtype hợp lệ, dẫn tới `ServiceConfigurationError`. Chúng ta **chỉ in loại lỗi**, không phụ thuộc toàn bộ message có thể khác phiên bản JDK.

**Lưu ý:** custom child-first loader này là **fixture kiểm thử có chủ đích** để tái hiện lỗi đóng gói API lặp. Không xem đây là classloader production hoặc cơ chế sandbox. Nó cũng không cần thay loader cho các namespace hệ thống `java.*`.

### 6.7. Biên dịch và đóng gói JAR, PowerShell trên JDK 17+

Chạy từ thư mục `duplicate-demo` có các tệp ở mục 6.1:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\v1,out\v2,out\plugin,out\host,jars | Out-Null

javac -d out\api api\demo\api\Codec.java
javac -d out\v1 lib-v1\demo\lib\Version.java
javac -d out\v2 lib-v2\demo\lib\Version.java

javac -cp "out\api;out\v1" -d out\plugin plugin\demo\plugin\CodecPlugin.java
javac -cp out\api -d out\host host\Host.java

jar --create --file jars\plugin-a.jar -C out\plugin . -C out\v1 . -C resources\a .
jar --create --file jars\plugin-b.jar -C out\plugin . -C out\v2 . -C resources\b .
jar --create --file jars\bad-plugin.jar -C out\plugin . -C out\v1 . -C out\api . -C resources\a .

java -cp "out\api;out\host" Host
```

**Lưu ý quan trọng:** tham số `-cp` của lệnh `java` **không** chứa ba plugin JAR. Nếu đưa chúng vào classpath cha, parent-first delegation có thể làm các test chọn phiên bản khác và mất ý nghĩa. `Host` chủ động tạo `URLClassLoader` với đúng JAR được chọn.

Trước khi chạy có thể kiểm tra `jar --list --file jars\plugin-a.jar` và các JAR khác. Các mục đáng chú ý:

```text
plugin-a.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  config/plugin.properties

plugin-b.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  config/plugin.properties

bad-plugin.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  demo/api/Codec.class                <-- bản hợp đồng bị đóng lặp
  META-INF/services/demo.api.Codec
  config/plugin.properties
```

Khối này **minh họa các entry phải tồn tại**, không phải bản sao nguyên văn của `jar --list`: lệnh thực tế còn in manifest và directory entries.

**Stdout kỳ vọng của chương trình:**

```text
a=[codec-v1]
b=[codec-v2]
provider.class.same=false
combined.aFirst=v1
combined.bFirst=v2
resources=[A, B]
bad.api.same=false
bad.assignable=false
bad.spi=ServiceConfigurationError
```

Đây là kết quả cho **đúng file, đúng classpath và JDK 17+** của ví dụ. Kết quả thể hiện cả ba loại xung đột:

1. **Trùng phiên bản:** hai loader riêng cho phép v1/v2 cùng tồn tại; dùng loader gộp thì thứ tự URL thay đổi class `Version` được chọn.
2. **Trùng resource:** cả `config/plugin.properties` của A và B được tìm bằng `getResources`; nếu chỉ gọi `getResource`, host chỉ nhận một URL.
3. **Trùng hợp đồng:** bad loader tạo bản `Codec` khác với bản host và phát sinh lỗi subtype ngay khi `ServiceLoader` duyệt provider.

Trên macOS/Linux, thay dấu phân cách classpath `;` bằng `:` và dùng lệnh shell tạo thư mục tương đương. Lệnh PowerShell ở trên không phải cú pháp Bash.

### 6.8. Vì sao dùng cả kiểm thử tích cực và tiêu cực?

Một test chỉ xác nhận plugin A chạy được là chưa đủ. Cần chứng minh **đúng thư viện** được nạp, **đúng tập resource** được tìm và **sai packaging** phải bị phát hiện.

- **Positive:** `a=[codec-v1]`, `b=[codec-v2]`; hai provider đều subtype của API chung.
- **Order-sensitive:** `combined.aFirst=v1` và `combined.bFirst=v2`; cho thấy duplicate classes có thể đổi hành vi khi đổi thứ tự URL.
- **Resource enumeration:** `resources=[A, B]`; cả hai tài nguyên có cùng path thực sự hiện diện.
- **Negative:** bad JAR cố tình đóng gói API lặp; kiểm tra `bad.api.same=false`, `bad.assignable=false` và loại lỗi `ServiceConfigurationError`.

Đây là **test regression có mục tiêu**. Trong CI, thay `System.out.println` bằng assertion và bảo đảm test dùng **artifact thực** sau build, tránh việc IDE/classpath unit test vô tình cho hành vi khác production.

## 7. Kiểm thử SPI provider registration và resource packaging

### 7.1. Đọc descriptor theo đúng service class

Nếu service type là `demo.api.Codec`, descriptor phải có tên:

```text
META-INF/services/demo.api.Codec
```

Chỉ cần sai một ký tự trong đường dẫn hoặc dùng tên provider thay tên service là `ServiceLoader` có thể không khám phá provider.

Trong trường hợp service type là **nested class**, tên nhị phân có thể chứa dấu `$`; tên file phải theo `Class.getName()`, không tùy tiện dùng `getCanonicalName()`. Có thể dựng path an toàn bằng:

```java
// Đoạn minh họa trong host.
String path = "META-INF/services/" + Codec.class.getName();
Enumeration<URL> descriptors = pluginLoader.getResources(path);
```

`getResources` giúp liệt kê từng descriptor hiện có trước khi gọi `ServiceLoader`. Nếu JAR bị merge, cần kiểm tra rằng danh sách class provider sau merge vẫn hợp lệ, không mất dòng provider quan trọng.

### 7.2. Khẳng định đúng provider được tạo

Với `ServiceLoader`, việc tồn tại descriptor hoặc `Class.forName` thành công chưa đủ. Nên thực sự **duyệt**:

```java
// Đoạn minh họa.
List<String> ids = new ArrayList<>();
for (Codec codec : ServiceLoader.load(Codec.class, pluginLoader)) {
    ids.add(codec.id());
}
Collections.sort(ids);
```

Có thể gặp `ServiceConfigurationError` ngay ở bước tải/khởi tạo provider vì tên class sai, thiếu dependency, lỗi định danh API hoặc constructor/factory không hợp lệ. Với provider trên classpath, cơ chế thông thường cần lớp provider hợp lệ với constructor public không tham số. Với **named module** (JPMS), quy tắc provider declaration và factory `provider()` có thể khác, nên test phải dùng topology module tương ứng.

### 7.3. Tên provider trùng không cho biết bytecode giống nhau

Hai descriptor cùng chứa `demo.plugin.CodecPlugin` nhưng trong hai JAR có thể tồn tại **hai class cùng tên nhưng khác bytecode**. Nếu chúng bị đưa vào **cùng một loader**, cách tìm class chọn một; `ServiceLoader` xử lý descriptor theo quy tắc riêng. Nếu chúng được nạp bằng hai loader riêng, hai class độc lập có thể cùng tồn tại. Vì vậy kiểm thử chỉ so tên provider sẽ bỏ sót lỗi liên quan class identity/bytecode.

## 8. Kiểm thử contract packaging trong CI

### 8.1. Quy định artifact nào được phép chứa API

Với kiến trúc host/plugin tiêu biểu:

```text
host / api.jar:
  demo/api/Codec.class

plugin-a.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  (không chứa demo/api/Codec.class)
```

Nếu plugin chỉ **compile against** API do host cấp, dependency API nên ở cấu hình phù hợp để **không được đóng vào artifact phát hành**. Ví dụ:

- Maven: dependency API có thể dùng scope `provided` nếu host chắc chắn cấp cùng API ở runtime; kiểm tra fat JAR/shading plugin thật sự loại API khỏi artifact.
- Gradle Java: `compileOnly` có thể tránh đưa API vào runtime artifact mặc định khi host cấp API; nhưng cấu hình plugin shadow/fat JAR và runtime packaging phải được kiểm tra riêng.
- Trong JPMS, API có thể là module chung được resolve ở parent layer. Không đóng duplicate API theo cách làm đổi định danh kiểu giữa host/plugin.

**Đừng suy luận scope build tự động bảo đảm packaging.** Một build plugin tùy chỉnh có thể vô tình thêm class API vào JAR cuối. Luôn kiểm tra entry thực tế.

### 8.2. Lệnh kiểm tra artifact

Trên PowerShell:

```powershell
jar --list --file jars\plugin-a.jar
jar --list --file jars\plugin-b.jar
jar --list --file jars\bad-plugin.jar

# Kiểm tra các entry mang tên nhị phân và tài nguyên cần quan tâm:
jar --list --file jars\bad-plugin.jar | Select-String 'demo/api/Codec.class'
jar --list --file jars\plugin-a.jar | Select-String 'META-INF/services/demo.api.Codec'
jar --list --file jars\plugin-b.jar | Select-String 'config/plugin.properties'

Get-FileHash jars\plugin-a.jar -Algorithm SHA256
Get-FileHash jars\plugin-b.jar -Algorithm SHA256
```

`Get-FileHash` xác nhận nội dung artifact cụ thể trong một lần build/triển khai, nhưng hash **không chứng minh** tính tương thích hoặc hành vi đúng. Nếu CI sinh ra một JAR khác với JAR được test, kết quả test có thể không bảo vệ bản phát hành thực tế.

### 8.3. Dependency graph: cần thiết nhưng chưa đủ

Các lệnh tham khảo:

```powershell
# Maven: in cây dependency đã giải quyết.
mvn dependency:tree

# Gradle: xem cấu hình runtimeClasspath.
./gradlew dependencies --configuration runtimeClasspath

# Gradle: điều tra bản module bị chọn khi trùng phiên bản.
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
```

Đây là **lệnh tham khảo cho dự án Maven/Gradle**, không chạy trong cấu trúc `duplicate-demo` thuần `javac`. Tên cấu hình có thể khác ở project thực tế; build plugin riêng có thể sử dụng cấu hình runtime khác host. Với Maven, có thể dùng plugin kiểm soát dependency convergence/version upper bounds; với Gradle, dùng constraints/resolution strategy phù hợp. Nhưng kết quả dependency tree **không tự chứng minh** nội dung JAR đã được shadow/merged hoặc classloader production sẽ chọn class nào.

### 8.4. So sánh cấu trúc và hành vi

Để chống lỗi này trong CI, nên có ít nhất hai lớp test:

1. **Static packaging checks:** từng artifact phải chứa resource/descriptor dự kiến, không có bản API bị cấm, không chứa class duplicate ngoài allowlist và tuân thủ quy tắc version.
2. **Runtime classloader integration:** tạo loader/layer như production, chạy `ServiceLoader`, khẳng định subtype, version hành vi và danh sách resource đầy đủ.

Nếu chỉ chạy unit test trong IDE, host và plugin có thể dùng chung một application classloader mà không phản ánh child-first, parent-first, layer động, file system watcher hoặc các JAR tách rời của production.

## 9. Ma trận kiểm thử theo tổ hợp plugin

Không nên chỉ test từng plugin đơn lẻ. Các lỗi va chạm thường xuất hiện khi **kết hợp nhiều plugin** hoặc thay đổi thứ tự nạp.

| Case | Thiết lập | Kết quả cần khẳng định |
|---|---|---|
| **A-only** | Chỉ JAR A, API host | Provider A sử dụng đúng v1 |
| **B-only** | Chỉ JAR B, API host | Provider B sử dụng đúng v2 |
| **A+B, isolated loaders** | Mỗi plugin có loader riêng, API chung từ parent | Cả A và B chạy, cùng assignable tới host API |
| **A trước B, loader gộp** | Hai URL theo thứ tự A,B | Biết rõ version được chọn; phát hiện nếu kết quả không tương thích |
| **B trước A, loader gộp** | Hai URL theo thứ tự B,A | Phát hiện khác biệt khi hoán đổi thứ tự |
| **Duplicate resource** | A và B chứa cùng `config/plugin.properties` | Liệt kê đủ nguồn và nội dung; không âm thầm chọn nhầm |
| **Duplicate SPI descriptor** | Hai descriptor cùng service name | Provider thực tế có đúng danh sách/không mất registration |
| **Duplicate host API packaged** | Plugin JAR vô tình chứa `demo/api/Codec.class` | Static check fail ngay, bất kể runtime parent-first có che trùng |
| **Child-first API duplication** | Loader plugin tự định nghĩa API | Runtime `Class` identity khác; contract test fail đúng kỳ vọng |
| **Missing dependency** | Bỏ một thư viện mà plugin dùng | Test phát hiện lỗi nạp/liên kết với context rõ |
| **Binary-incompatible dependency** | Build với method mới, runtime dùng JAR cũ | Test phát hiện `LinkageError`/`NoSuchMethodError` tại nhánh sử dụng |
| **JPMS layer/module path** | Provider được resolve vào named module/layer | Test uses/provides, module readability, layer ancestry, split package |

Khi thực thi, cần ghi lại **JDK version**, OS, danh sách JAR/sha256, classpath/module path, TCCL, policy delegation, namespace của loader và cấu trúc layer. Không có các dữ liệu này, một lỗi “provider not found” thường khó tái hiện ở máy khác.

## 10. Quan hệ với JPMS và ModuleLayer

### 10.1. Same name, different module không giống duplicate classpath

JPMS xác lập quan hệ module readability, exports và cấu trúc package. Hai named module khác nhau trong một layer có thể bị hạn chế bởi quy tắc package, đặc biệt khi chúng được định nghĩa vào cùng loader. Xung đột có thể khiến bước resolve/define layer thất bại trước khi mã plugin được gọi.

Không nên “sửa” lỗi `ResolutionException` bằng việc đẩy mọi module về classpath rồi coi hệ thống đã tương đương. Khi chuyển sang unnamed module, các quy tắc tìm kiếm provider và truy cập cũng thay đổi. Kiểm thử runtime phải phản ánh **cách triển khai thực tế**.

### 10.2. Dependency trong module khác với dependency trong URLClassLoader

Với module path, `module-info.java` mô tả `requires`, `exports`, `uses` và `provides`. `ServiceLoader.load(layer, service)` tìm provider trong layer và tổ tiên, **không tìm provider ở unnamed module** theo overload này. Với `ServiceLoader.load(service, loader)`, phạm vi chọn loader khác; do đó test resource/provider phải dùng đúng overload mà production đang dùng.

Nếu plugin được chuyển từ classpath sang module path (hoặc biến thành automatic module), bộ test cần chạy lại: resolution, provider discovery, version conflict và packaging có thể khác. Một JAR có `META-INF/services` không tự bảo đảm mọi kiểu `ServiceLoader` lookup đều thấy nó.

## 11. Ghi log và chẩn đoán khi thất bại

### 11.1. Ghi định danh classloader và nguồn lớp

Trong code chẩn đoán:

```java
// Đoạn minh họa trong phạm vi đã có service Class<?>.
Class<?> type = demo.api.Codec.class;
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

var pd = type.getProtectionDomain();
if (pd != null && pd.getCodeSource() != null) {
    System.out.println("source=" + pd.getCodeSource().getLocation());
}
```

Chuỗi `ClassLoader.toString()` và URL của `CodeSource` thay đổi theo JDK/đường dẫn. Không dùng chúng làm stdout cố định; dùng làm thông tin điều tra. Với classloader riêng, nên gắn **ID logic** của plugin/loader vào log thay vì chỉ in hash ngẫu nhiên.

### 11.2. Lỗi điển hình

| Dấu hiệu | Chỗ cần xác minh trước |
|---|---|
| `ClassNotFoundException` | Tên nhị phân, JAR URL, parent loader, đường nạp |
| `NoClassDefFoundError` | Thiếu lớp phụ thuộc hoặc lỗi khởi tạo class trước đó; đọc `cause` |
| `NoSuchMethodError` | API đã compile và phiên bản class thực sự loaded không tương thích |
| `ClassCastException` | Hai định danh kiểu khác nhau, loader/API bị duplicate |
| `ServiceConfigurationError` | Descriptor, subtype, constructor/factory, lỗi provider |
| Provider “mất” sau merge JAR | Descriptor SPI bị overwrite/không merge đúng |
| Cấu hình plugin A xuất hiện ở B | Resource path trùng, loader/resource priority sai |
| `ResolutionException` / `LayerInstantiationException` | Module graph, readability, dependency và package definitions |
| Chạy riêng được, chạy chung lỗi | Classpath conflict, loader policy, duplicate resources, static singleton/cache |

Cần tách **lỗi build graph** khỏi **lỗi artifact** và **lỗi runtime loader**. Ví dụ lỗi `ClassCastException` có thể đến từ duplicate API dù Maven dependency graph hoàn toàn không có version conflict vì class API đã bị đóng gói thủ công vào plugin JAR.

## 12. Chính sách phát hành tránh lỗi tái diễn

**Một nguồn sự thật cho hợp đồng:** API/SPI chung nên được phát hành với version được quản lý và do host cấp rõ. Plugin phải khai báo phiên bản API tối thiểu/tối đa được hỗ trợ, nhưng không đóng lặp class hợp đồng khi runtime yêu cầu thống nhất identity.

**Namespace dependency rõ:** quyết định lớp thư viện nào được chia sẻ với host, lớp nào được cô lập theo plugin. Child-first có chọn lọc phải **loại trừ API/SPI shared** và các namespace nền tảng; không dùng một chính sách chung một cách tùy tiện.

**Resource policy rõ:** phân loại từng loại tài nguyên cần chọn một bản, hợp nhất hay từ chối trùng. Với `META-INF/services`, cấu hình build fat JAR cần transformer/merge có kiểm thử; với cấu hình `config/plugin.properties`, thường nên đặt path theo plugin namespace hoặc có chính sách ưu tiên minh bạch.

**Reproducible artifact:** ghi hash/artifact ID, Java version, classpath/module path và kiểm thử **JAR cuối cùng** trước triển khai. Nếu plugin JAR có thể được tải lại khi host đang chạy, test cả lifecycle unload/reload; classloader cũ có thể còn được giữ bởi thread, callback hoặc cache.

**Fail-fast với duplicate contract:** static packaging scan nên từ chối `demo/api/Codec.class` trong artifact plugin nếu contract do host sở hữu. Runtime check `Codec.class.isAssignableFrom(providerType)` hoặc `ServiceLoader` là lớp bảo vệ thứ hai, không phải lý do bỏ qua kiểm tra đóng gói.

## 13. Câu hỏi ôn tập và bài tập

1. **Vì sao hai JAR có cùng `demo.lib.Version` chưa chắc xảy ra lỗi?** Nếu hai loader khác nhau định nghĩa mỗi bản, chúng có thể cùng tồn tại. Nếu cùng loader, một bản được chọn và chỉ có thể phát hiện bằng hành vi/metadata hoặc lỗi liên kết.
2. **Tại sao `getResource` không đủ để kiểm thử resource collision?** Vì nó chỉ trả một URL; `getResources` có thể cho thấy nhiều bản và cho phép kiểm tra nội dung từng bản.
3. **Khi nào “duplicate API file” thực sự thành “duplicate API class identity”?** Khi các loader khác nhau cùng định nghĩa class API tương ứng, không chỉ khi có hai bản file trên đĩa.
4. **Tại sao `ClassCastException` có thể xuất hiện dù tên class và tên interface giống hệt?** Vì type identity phụ thuộc cả loader đã định nghĩa class, không chỉ tên nhị phân.
5. **Tại sao classpath test chạy được nhưng production dùng JPMS có thể lỗi?** Vì cách resolve module, access, layer/provider discovery và package checks khác nhau.
6. **Vì sao kiểm tra dependency tree không đủ?** Nó không luôn phản ánh nội dung fat JAR/shaded JAR hoặc các JAR do host nạp động.
7. **Nếu hai `META-INF/services` cùng tên bị merge, nên assert điều gì?** Descriptor thành phẩm còn đủ provider hợp lệ và `ServiceLoader` thực sự tạo đúng provider theo topology production.
8. **Thay thứ tự URL có thể đổi hành vi khi lớp trùng phiên bản không?** Có trong mô hình URLClassLoader của ví dụ; đó là lý do nên test cả hai thứ tự.
9. **Có nên đưa API JAR vào mỗi plugin “cho chắc”?** Không nếu hệ thống yêu cầu API do host cấp một lần; việc nhân bản dễ gây lỗi khi policy loader thay đổi.

**Bài tập A:** đổi method `Version.text()` ở v2 thành `Version.label()` và biên dịch plugin theo v2, nhưng runtime dùng v1. Quan sát `NoSuchMethodError` ở nhánh sử dụng; ghi rõ loader nào đã định nghĩa `Version`.

**Bài tập B:** chuyển một cấu hình `config/plugin.properties` sang đường dẫn riêng `plugins/a/config.properties` và cập nhật phép đọc; so sánh với chính sách cho phép resource trùng nhưng dùng `getResources`.

**Bài tập C:** xóa `demo/api/Codec.class` khỏi bad JAR rồi chạy lại child-first loader. Giải thích vì sao loader phải ủy quyền tìm `Codec` cho host khi bản API trong JAR không tồn tại, và dự đoán `bad.api.same`/`bad.assignable` sẽ thay đổi thế nào.

**Bài tập D:** tạo CI test chạy chỉ trên JAR đóng gói cuối cùng, xuất bảng: tên class/resource, các JAR chứa nó, giá trị SHA-256 và loader mong đợi. Đưa một duplicate API vào để chứng minh test fail trước khi phát hành.

## 14. Tài liệu tham khảo

- Java SE 17 — `ClassLoader` (`loadClass`, `getResource`, `getResources`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ServiceLoader`, classpath và named-module providers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `Class` (`getName`, `getClassLoader`, `isAssignableFrom`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java Virtual Machine Specification 17 — Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
