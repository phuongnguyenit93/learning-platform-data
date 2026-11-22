# Tương thích bytecode, thư viện và JDK khi biên dịch hoặc triển khai plugin Java

## 1. Câu hỏi cần giải quyết

Plugin Java có thể được phát triển bằng một JDK, compile theo một phiên bản SPI (Service Provider Interface), đóng gói kèm dependency, rồi triển khai vào host đang chạy JDK và thư viện khác. **Cài được JAR hoặc compile thành công chưa đủ chứng minh plugin có thể chạy đúng.** Việc tương thích phải được xem xét ở nhiều tầng riêng biệt.

Hãy hình dung ba trường hợp:

- Plugin được build ra bytecode Java 21 nhưng máy host chạy Java 17: JVM đích không hiểu class-file version mới.
- Plugin được build bằng --release 17 nên bytecode hoàn toàn phù hợp với Java 17, nhưng plugin gọi method chỉ có trong phiên bản thư viện mới; host lại nạp phiên bản cũ: bytecode hợp lệ vẫn gây lỗi liên kết.
- Host và plugin compile cùng một interface và cùng JDK, nhưng hai class loader định nghĩa hai bản class interface cùng tên: type identity không trùng, nên không thể cast một cách an toàn.

Để thiết kế hệ thống runtime extensibility, luôn phân biệt ít nhất bốn câu hỏi:

1. **Bytecode:** JVM đích có đọc được định dạng .class hay không?
2. **JDK/platform API:** những package, module và method của JDK mà bytecode tham chiếu có hiện diện và cho phép truy cập hay không?
3. **Library/SPI ABI:** runtime có đúng binary contract của API và các thư viện mà plugin đã dùng lúc compile hay không?
4. **Loading và hành vi:** class loader/ModuleLayer có định nghĩa đúng identity và version, và plugin có đáp ứng semantics của host hay không?

Chỉ khi cả bốn tầng phù hợp, host mới có thể coi plugin là ứng viên hợp lệ để kích hoạt. Trong production còn cần kiểm tra artifact provenance, trust boundary, quyền và tài nguyên; **compatibility không tự đồng nghĩa security**.

## 2. Hình dung hai thời điểm build và runtime

~~~text
BUILD TIME                                      RUNTIME
Source plugin                                  Host application
  |                                               |
  v                                               |-- Runtime JDK / runtime image
javac (toolchain, --release,                  |-- API/SPI mà host thật sự nạp
      compile classpath, module path)              |-- Runtime dependencies
  |                                               |-- ClassLoader / ModuleLayer
  v                                               v
.class + resources --> plugin.jar ------------> Load, verify, link
                                                  |
                                                  v
                                          ServiceLoader / reflection
                                                  |
                                                  v
                                          Create instance, invoke SPI
~~~

Compiler ghi vào bytecode các symbolic references tới class, method, field và descriptors của thư viện nhìn thấy khi compile. Sau đó JVM phải phân giải chúng thành các định nghĩa có thực theo class loader/module graph khi code chạy. Bởi vậy **compile classpath** và **runtime classpath/module path** phải được quản lý như hai cấu hình có liên quan, không phải hai tập JAR tùy ý.

Nên lưu các thuộc tính của một bản phát hành:

| Thành phần | Thông tin quan trọng |
| --- | --- |
| JDK build | Vendor, version, compiler options và build tool |
| Target bytecode | Java release, class-file major/minor, preview status |
| Host API/SPI | Interface/binary names, API version/range, checksum |
| Dependency | Exact versions và dependency graph, gồm cả transitive |
| Runtime JDK | Phiên bản tối thiểu, bản thực chạy, module availability |
| Loader/layer | Parent loader cho SPI, cô lập dependency, JPMS configuration |
| Plugin artifact | ID, version, SHA-256, manifest/module descriptor, publisher |
| Contract | Test kết quả, lỗi, thread-safety, lifecycle, format dữ liệu |

Không nên lưu riêng một trường “javaVersion: 17” rồi xem là đã đủ thông tin.

## 3. Class-file version: tầng tương thích cơ bản nhất

Một tệp .class có **major_version** và **minor_version**. JVM phải hỗ trợ class-file version trước khi định nghĩa và sử dụng class. Một số mốc thông dụng:

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |

JVM Java 17 không hỗ trợ class-file major 65 do JDK 21 tạo ra. Khi cố nạp, thường gặp **UnsupportedClassVersionError**. Ngược lại, class major 61 có thể nạp được trên JVM Java 17 và các runtime Java mới hơn có hỗ trợ định dạng đó, **nhưng khả năng nạp bytecode chưa bảo đảm dependency và hành vi đúng**.

Kiểm tra class trực tiếp:

~~~bash
javap -verbose -classpath plugin.jar com.example.plugin.Provider
~~~

Trong output tìm:

~~~text
major version: 61
~~~

**Không chỉ kiểm tra mỗi class chính.** Một plugin JAR có thể chứa nhiều class, dependency được đóng gói hoặc multi-release entries, mỗi phần có class-file version khác nhau. Máy build dùng JDK 21 cũng không có nghĩa mọi class tự động là major 65 nếu compiler được cấu hình target thấp hơn.

Class sử dụng **preview features** có thể có minor version đặc biệt **65535**, gắn với quy tắc phiên bản runtime và --enable-preview. Đừng dựa duy nhất vào major version để đánh giá hỗ trợ preview.

## 4. Dùng javac --release đúng cách

Lựa chọn thường ưu tiên khi muốn plugin chạy trên Java 17:

~~~bash
javac --release 17 -d out src/com/example/Plugin.java
~~~

**--release 17** yêu cầu compiler:
- Áp dụng language rules của Java 17.
- Sinh class file target cho Java 17, thông thường major 61.
- Compile code dựa trên **platform API được công bố cho release 17**, ngăn vô tình gọi JDK API chỉ mới xuất hiện ở phiên bản mới hơn trên máy build.

So với:

~~~bash
# Minh họa giới hạn của -source/-target khi build trên JDK mới:
javac -source 17 -target 17 -d out src/com/example/Plugin.java
~~~

Hai cờ -source và -target chủ yếu kiểm soát language/class target, **không tự khóa tập platform API ở đúng Java 17**. Một source có thể compile được trên JDK mới với -target 17 dù gọi method JDK chỉ có từ Java mới hơn, rồi thất bại khi host thực sự chạy Java 17.

**--release không giới hạn API của JAR bên thứ ba.** Nếu plugin compile với library-x v3 nhưng runtime chỉ cung cấp library-x v2, javac --release 17 vẫn có thể compile thành công vì API JDK target và API third-party library là hai việc khác nhau.

Không phối hợp **--release** với **-source** và **-target** trong cùng invocation. Compiler cũng chỉ hỗ trợ một số release target, tùy phiên bản javac thực tế. Nếu target không còn được hỗ trợ, chọn toolchain khác thay vì lặng lẽ bỏ --release.

Ví dụ một pipeline có thể dùng JDK build mới hơn để tạo class major 61 cho JDK runtime 17. Tuy nhiên, kết quả phải được kiểm thử trên **JDK 17 thật** và đúng dependency set; không suy ra tương thích runtime chỉ từ thông báo compile thành công.

### Maven và Gradle

**Mảnh cấu hình Maven pom.xml:**

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Dùng maven-compiler-plugin phù hợp, version toolchain/build cố định và dependency versions được khóa. Property này **không tự tải JDK đích, không bảo đảm thư viện tương thích**.

**Mảnh Gradle Kotlin DSL:**

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain xác định compiler; options.release xác định target release. Cần điều chỉnh target theo **runtime tối thiểu** mà nền tảng plugin thực sự hỗ trợ, không tùy tiện chọn theo JDK trên máy phát triển.

## 5. API Java chuẩn và thư viện bên thứ ba khác nhau

**JDK platform API** được kiểm soát bởi --release. **Third-party API** được kiểm soát bởi các JAR thực sự có mặt trên compile classpath hoặc module path. Vì vậy có thể xảy ra:

~~~text
Compile:
  JDK 24 + --release 17
  spi-api v2
  json-library v3
  plugin.jar => class major 61

Deploy:
  JDK 17
  spi-api v1
  json-library v2

Kết quả:
  Class-file version: hợp lệ
  Binary contract: có thể KHÔNG hợp lệ
~~~

Plugin ghi lời gọi method mà compiler đã thấy trong spi-api v2. Khi JVM đích lại có v1 thiếu method, **NoSuchMethodError** có thể xuất hiện đúng lúc lời gọi được resolve. Thiếu field tương ứng có thể tạo **NoSuchFieldError**. Nếu method bị đổi static/instance, có thể gặp **IncompatibleClassChangeError**.

Ràng buộc Java release thấp **không sửa** lỗi ABI của SPI và dependency. Host cần quản lý version/API contract riêng, theo dõi dependency tree và kiểm tra những class thực sự được loader sử dụng.

### Dependency trực tiếp, gián tiếp và optional

- **Direct:** plugin import API của library-x v3, runtime dùng library-x v2; lỗi thường dễ gắn với method/field bị thiếu.
- **Transitive:** library-x v3 cần library-y v4, nhưng host ép library-y v2. Plugin có thể chỉ import x mà vẫn bị lỗi từ y.
- **Optional:** chỉ thực sự optional nếu code path không dùng dependency đó hoặc có cơ chế fallback; “optional trong Maven” không phải cam kết mọi phương thức runtime sẽ luôn chạy.
- **Shaded/relocated:** có thể cô lập thư viện implementation, nhưng **không relocate/copy SPI chung** một cách khiến plugin dùng bản interface khác của host.
- **JNI/native:** .dll/.so/.dylib phụ thuộc OS/CPU/ABI, và có thể hỏng dù class-file Java hoàn toàn đúng.
- **Dynamically referenced:** reflection, ServiceLoader, ResourceBundle và class-name strings có thể yêu cầu class/resource không hiện ra trong static imports.

Đối với mọi dependency được load, cần xem **version compile thực**, **version runtime thực**, artifact hash và class loader/module resolution.

## 6. Source, binary và behavioral compatibility

Ba khái niệm quan trọng:

1. **Source compatibility:** source plugin cũ có compile lại được khi host đổi API không?
2. **Binary compatibility:** plugin đã được build từ trước có tiếp tục link được với API mới mà không recompile không?
3. **Behavioral compatibility:** sau khi link thành công, semantics, dữ liệu, thứ tự gọi, concurrency và exception contract có còn đúng không?

Không được đồng nhất ba khái niệm. Theo Java Language Specification, một thay đổi có thể bảo toàn binary nhưng khiến source recompile bị ambiguous overload hoặc đổi lựa chọn overload; cũng có thay đổi giữ binary contract mà làm sai nghiệp vụ.

| Thay đổi SPI/API | Điều cần lưu ý |
| --- | --- |
| Thêm overload vào class/interface | Thường không phá binary cũ; source recompile có thể chọn overload khác |
| Thêm method vào class | Thường binary compatible với client cũ; client mới không chạy trên library cũ nếu gọi method đó |
| Thêm abstract method vào interface | Có thể binary compatible, nhưng khi host mới gọi trên provider cũ có thể **AbstractMethodError** |
| Thêm default method | Thường binary compatible; có trường hợp xung đột default methods khi invoke |
| Xóa/đổi method mà binary cũ gọi | Có thể gây **NoSuchMethodError** |
| Thay descriptor do đổi parameter hoặc return type | Có thể tương đương xóa method cũ rồi thêm method mới |
| Thay static thành instance hoặc ngược lại | Có thể gây **IncompatibleClassChangeError** |
| Hạ mức truy cập public / thay module exports | Có thể gây **IllegalAccessError** |
| Xóa/đổi field | Có thể gây **NoSuchFieldError** hoặc lỗi liên kết tương ứng |
| Giữ chữ ký method nhưng đổi hành vi | JVM vẫn link được nhưng contract test có thể thất bại |
| Đổi schema/serialization, nullability, thread contract | Có thể chạy được nhưng sai semantics hoặc hỏng dữ liệu |

**Hướng tương thích không đối xứng:** nếu API v2 thêm method mới, các client compile cũ có thể tiếp tục chạy với v2. Nhưng client compile bằng v2 và **gọi method mới** không thể tự động chạy trên host v1 thiếu method. Tương thích ngược của API mới với binary cũ không đồng nghĩa binary mới tương thích với API cũ.

Đối với Java generics, method descriptors ở bytecode phản ánh **type erasure**. Việc đổi generic bound có thể khiến descriptor thay đổi. Khi không chắc một thay đổi có phá ABI không, dùng **javap -s** để so sánh binary descriptors; đừng chỉ nhìn source Java.

## 7. Ví dụ Java 17 đầy đủ: bytecode hợp lệ nhưng API runtime không tương thích

Ví dụ chủ động tạo hai bản interface **demo.api.Greeting**:

- **api-v1:** chỉ có greet().
- **api-v2:** cùng greet(), bổ sung static banner().
- **PluginGreeting:** compile với api-v2, gọi Greeting.banner().
- **Host:** compile với api-v1, dùng ServiceLoader để lấy plugin và gọi greet().
- **Runtime tốt:** dùng api-v2 với cùng plugin.
- **Runtime lỗi:** thay api-v2 bằng api-v1 với cùng plugin.

Mọi class được build bằng **--release 17**, cho nên bytecode target không thay đổi giữa hai runtime. Phần khác biệt duy nhất là **binary contract của thư viện API** được nạp.

### Cấu trúc tệp

~~~text
demo/
├── src/
│   ├── api-v1/demo/api/Greeting.java
│   ├── api-v2/demo/api/Greeting.java
│   ├── plugin/demo/impl/PluginGreeting.java
│   └── host/demo/host/Main.java
├── resources/
│   └── META-INF/services/demo.api.Greeting
└── out/
    ├── api-v1/
    ├── api-v2/
    ├── host/
    ├── plugin/
    └── plugin.jar
~~~

Chỉ đưa **một** trong api-v1 và api-v2 lên runtime classpath tại mỗi lần chạy. Không thử xếp cả hai cùng tên binary trên một loader rồi suy luận kết quả từ JAR được load trước.

### File src/api-v1/demo/api/Greeting.java

~~~java
package demo.api;

public interface Greeting {
    String greet(String name);
}
~~~

### File src/api-v2/demo/api/Greeting.java

~~~java
package demo.api;

public interface Greeting {
    String greet(String name);
    static String banner() { return "v2"; }
}
~~~

### File src/plugin/demo/impl/PluginGreeting.java

~~~java
package demo.impl;

import demo.api.Greeting;

public final class PluginGreeting implements Greeting {
    public PluginGreeting() {}

    @Override public String greet(String name) {
        return Greeting.banner() + ":" + name;
    }
}
~~~

Lớp plugin là public, implements đúng binary name của SPI, có public no-argument constructor. Nhưng method greet() **phụ thuộc vào banner() chỉ xuất hiện trong API v2**.

### File src/host/demo/host/Main.java

~~~java
package demo.host;

import demo.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Greeting plugin = ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow();
        System.out.println("Provider: " + plugin.getClass().getName());
        try {
            System.out.println("Result: " + plugin.greet("Java"));
        } catch (NoSuchMethodError failure) {
            System.out.println("Linkage: " + failure.getClass().getSimpleName());
        }
    }
}
~~~

Host không biết tên implementation lúc compile; ServiceLoader tìm provider từ service descriptor. Lệnh catch NoSuchMethodError chỉ phục vụ **minh họa một lỗi xác định**, giúp chương trình in output có thể kiểm tra được. Không dùng cách này để che toàn bộ LinkageError trong production.

### File resources/META-INF/services/demo.api.Greeting

~~~text
demo.impl.PluginGreeting
~~~

Đây là service configuration file của classpath. Tên file đúng binary name của SPI, còn dòng bên trong là binary name của implementation.

### Biên dịch và chạy trên Linux/macOS (bash)

Đứng tại thư mục demo:

~~~bash
mkdir -p out/api-v1 out/api-v2 out/host out/plugin

javac --release 17 -d out/api-v1 \
  src/api-v1/demo/api/Greeting.java

javac --release 17 -d out/api-v2 \
  src/api-v2/demo/api/Greeting.java

javac --release 17 -cp out/api-v1 -d out/host \
  src/host/demo/host/Main.java

javac --release 17 -cp out/api-v2 -d out/plugin \
  src/plugin/demo/impl/PluginGreeting.java

mkdir -p out/plugin/META-INF/services
cp resources/META-INF/services/demo.api.Greeting \
  out/plugin/META-INF/services/demo.api.Greeting

jar --create --file out/plugin.jar -C out/plugin .

# Trường hợp A: runtime có API v2
java -cp "out/api-v2:out/host:out/plugin.jar" demo.host.Main

# Trường hợp B: runtime chỉ có API v1
java -cp "out/api-v1:out/host:out/plugin.jar" demo.host.Main
~~~

### Biên dịch và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out/api-v1,out/api-v2,out/host,out/plugin | Out-Null

javac --release 17 -d out/api-v1 src/api-v1/demo/api/Greeting.java
javac --release 17 -d out/api-v2 src/api-v2/demo/api/Greeting.java
javac --release 17 -cp out/api-v1 -d out/host src/host/demo/host/Main.java
javac --release 17 -cp out/api-v2 -d out/plugin src/plugin/demo/impl/PluginGreeting.java

New-Item -ItemType Directory -Force out/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/demo.api.Greeting out/plugin/META-INF/services/demo.api.Greeting

jar --create --file out/plugin.jar -C out/plugin .

java -cp "out/api-v2;out/host;out/plugin.jar" demo.host.Main
java -cp "out/api-v1;out/host;out/plugin.jar" demo.host.Main
~~~

Dấu phân tách classpath trên Linux/macOS là dấu hai chấm **:**, trên Windows là dấu chấm phẩy **;**.

**Output trường hợp A, API v2 tương thích:**

~~~text
Provider: demo.impl.PluginGreeting
Result: v2:Java
~~~

**Output trường hợp B, API v1 thiếu method:**

~~~text
Provider: demo.impl.PluginGreeting
Linkage: NoSuchMethodError
~~~

ServiceLoader vẫn có thể tìm và khởi tạo provider ở trường hợp B vì constructor và interface greet() có thể phân giải. Khi host gọi greet(), JVM mới gặp symbolic reference tới Greeting.banner(), mà API v1 không có. Bởi vậy **discovery thành công và constructor chạy được chưa phải toàn bộ compatibility test**.

Kiểm tra class-file major của provider:

~~~bash
javap -verbose -classpath out/plugin.jar demo.impl.PluginGreeting
~~~

Trong output có dòng:

~~~text
major version: 61
~~~

**Kết luận của bài kiểm chứng:** cả hai trường hợp dùng cùng plugin class major 61; chỉ API runtime thay đổi. NoSuchMethodError là lỗi **library/SPI ABI**, không phải lỗi class-file target của Java 17.

## 8. Phân biệt các lỗi thường gặp

| Lỗi | Tầng thường gặp | Cần kiểm tra |
| --- | --- | --- |
| **UnsupportedClassVersionError** | JVM không hỗ trợ bytecode/preview target | java -version, javap major/minor, toàn bộ JAR dependencies |
| **NoSuchMethodError** | Library ABI mismatch | Method descriptor compile-time và class thực sự được load |
| **NoSuchFieldError** | Field ABI mismatch | Version field, descriptor, static/instance |
| **AbstractMethodError** | Interface/superclass evolution | Phương thức mới có implementation hợp lệ ở provider cũ không |
| **IncompatibleClassChangeError** | Thay đổi static/instance hoặc loại thành viên | API binary contract, class hierarchy/default method conflicts |
| **IllegalAccessError** | Accessibility / JPMS | public visibility, module readability/exports |
| **NoClassDefFoundError** | Dependency không định nghĩa được, lỗi linkage/init | Thiếu class, khởi tạo class lỗi, cause chain |
| **ClassNotFoundException** | Loader được yêu cầu tìm class theo tên | Tên binary, loader, classpath/module path |
| **ClassCastException** | Sai type hoặc duplicate SPI identity | Defining class loaders, module identity, API duplication |
| **ServiceConfigurationError** | Khai báo SPI/provider bất hợp lệ | META-INF/services, provides, constructor/provider method, cause |
| **ResolutionException** hoặc **LayerInstantiationException** | JPMS module graph/layer | Module names, dependencies, split packages |
| Sai kết quả, sai schema | Behavioral compatibility | Contract tests, dữ liệu mẫu, serialization, concurrency |

Lỗi có thể **xuất hiện muộn**: class đã được load hoặc provider đã được tạo nhưng JVM chưa cần resolve tất cả method/field. Đừng chỉ chạy một smoke test “ServiceLoader.findFirst() trả non-null” rồi công bố plugin là hợp lệ.

**NoClassDefFoundError không luôn có nghĩa file class không tồn tại.** Nó có thể theo sau một lỗi trong quá trình initialize class; xem cause và các log trước đó. **ClassCastException không nhất thiết do loader**, nhưng khi tên lớp giống nhau mà cast vẫn fail, hãy kiểm tra có hai loader định nghĩa hai SPI identity khác nhau hay không.

Bắt **ServiceConfigurationError** ở ranh giới discovery có thể hợp lý với hệ thống plugin để reject/quarantine provider lỗi. Nhưng đừng bắt và nuốt mọi Throwable rồi giả định tất cả lỗi JVM đều có thể tiếp tục một cách an toàn.

## 9. ClassLoader và type identity

Trong Java, type identity phụ thuộc vào **binary name và defining class loader**. Hai bản của demo.api.Greeting được định nghĩa bởi hai loader khác nhau không phải là một type chỉ vì cùng package và tên interface.

Mô hình thực tế cho plugin trên classpath:

~~~text
Parent/application ClassLoader
  ├── host app
  └── spi-api (một bản chung)
       ^
       |
Child ClassLoader A
  ├── plugin-A.jar
  └── implementation dependencies A

Child ClassLoader B
  ├── plugin-B.jar
  └── implementation dependencies B
~~~

Host nên cung cấp API/SPI từ parent, còn plugin loaders được cấu hình để cùng nhìn thấy **đúng Class object của interface** đó. Khi có nhu cầu cô lập thư viện implementation xung đột version, child-first strategies có thể hữu ích, nhưng **không áp dụng child-first vô tội vạ cho API chung**.

Những điều phải xác nhận:
- URLClassLoader hoặc custom loader nào được đưa vào ServiceLoader.load(Service.class, loader)?
- Code plugin và host có cùng Class object của SPI không?
- Khi module/plugin mới được cài, loader đang dùng có nhìn thấy JAR mới không?
- Khi thay plugin v1 bằng v2, loader cũ đã định nghĩa class chưa? Nếu rồi, cần loader mới và vòng đời chuyển đổi phù hợp.
- Tham chiếu từ thread context class loader, registry, static field, callback hoặc thread pool có giữ loader cũ không?

**ServiceLoader.reload() chỉ xóa cache của ServiceLoader**, không tự thay bytecode class đã load, không nâng dependency và không bảo đảm class unloading. Hot update là trách nhiệm của host.

## 10. JPMS: class-file hợp lệ nhưng module graph vẫn có thể lỗi

Java Platform Module System bổ sung các điều kiện:
- **requires** và readability giữa modules.
- **exports** cho public package API; **opens** cho reflection theo chính sách.
- **uses** ở consumer và **provides ... with ...** ở provider.
- Module path thực tế, resolved module graph, custom **ModuleLayer** và class loader.
- Trùng module name, split packages, automatic module name và dependency versions.

Ví dụ ba module descriptors riêng:

~~~java
// demo.api/module-info.java
module demo.api {
    exports demo.api;
}
~~~

~~~java
// demo.plugin/module-info.java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeting with demo.impl.PluginGreeting;
}
~~~

~~~java
// demo.host/module-info.java
module demo.host {
    requires demo.api;
    uses demo.api.Greeting;
}
~~~

Ba đoạn trên là **các file module-info.java khác nhau**, không phải một chương trình Java độc lập. Trong JPMS, module API xuất đúng package hợp đồng; module provider được phép giữ package implementation không exports/opens cho host mà ServiceLoader vẫn khởi tạo provider hợp lệ.

Một plugin compile đúng bytecode Java 17 vẫn có thể thất bại khi module chưa được resolve, host không có uses, package không còn được export hoặc module graph không hợp lệ. **Module descriptor là một phần của compatibility contract**, không chỉ là metadata trang trí.

Nếu dùng ModuleLayer mới để cài plugin, host phải tạo configuration/layer và dùng API khám phá tương ứng, ví dụ ServiceLoader.load(layer, Service.class). ServiceLoader không tự tạo layer hay nạp artifact từ Internet.

**Thay requires hoặc exports** có thể làm binary đã build bị IllegalAccessError hoặc khiến module resolution fail, dù method names và class-file major không thay đổi. Cần integration test theo đúng module path của môi trường triển khai.

## 11. Multi-release JAR và phiên bản JDK

Multi-release JAR (MR-JAR) cho phép chứa class implementations khác nhau tùy runtime:

~~~text
plugin.jar
├── META-INF/MANIFEST.MF           # Multi-Release: true
├── com/example/Plugin.class       # Base implementation
└── META-INF/versions/17/com/example/Plugin.class
~~~

Khi cấu hình manifest phù hợp, runtime hỗ trợ MR-JAR có thể chọn implementation ở version directory không vượt quá Java release đang chạy. Điều này có ích khi cùng artifact cần hỗ trợ runtime cũ hơn và tận dụng các API mới trên runtime mới hơn.

Ràng buộc:
- Base class phải chạy trên runtime tối thiểu bạn công bố.
- Class trong META-INF/versions/17 chỉ có ích khi runtime đủ mới; không biến toàn bộ artifact thành “tự chạy trên mọi Java”.
- API public qua các biến thể cần tuân thủ các yêu cầu consistency của MR-JAR; tránh để SPI contract thay đổi tùy JDK ngoài ý muốn.
- Dependencies và module graph vẫn phải hợp lệ trong từng runtime.
- Khi phân tích bằng **jdeps**, dùng **--multi-release** thích hợp với JAR dạng này; đừng quên kiểm tra nhiều runtime cần hỗ trợ.

Không cần dùng MR-JAR nếu toàn bộ hệ thống chỉ chạy Java 17 và một bản implementation đã đáp ứng yêu cầu.

## 12. Công cụ kiểm chứng

| Công cụ | Công dụng | Giới hạn |
| --- | --- | --- |
| **java -version** | Runtime JVM thực tế | Không cho biết library class nào đã được chọn |
| **javac -version** | Compiler thực tế | Không chứng minh target |
| **javac --release 17** | Kiểm soát language, class-file và platform API | Không khóa third-party API |
| **javap -verbose** | Xem class major/minor, constant pool | Cần kiểm tra tất cả class liên quan |
| **javap -s** | Xem binary descriptors | Không chỉ ra version runtime được loader chọn |
| **jar --list --file ...** | Liệt kê class/resources trong artifact | Không chứng minh provider có load thành công |
| **jar --describe-module --file ...** | Kiểm tra module descriptor/thông tin module | Không chứng minh đã resolve module trong layer |
| **jdeps --multi-release 17 ...** | Phân tích static dependencies | Không bao quát hoàn toàn reflection, ServiceLoader, JNI |
| **mvn dependency:tree** | Dependency graph Maven | Không tự kiểm chứng runtime được lắp đúng |
| **gradle dependencies / dependencyInsight** | Dependency resolution Gradle | Cần kiểm tra classpath runtime thật |
| **getClassLoader()/getModule()** | Runtime identity/class visibility | Không tự xác minh nguồn gốc artifact |
| **CodeSource/ProtectionDomain** | Gợi ý nơi class được nạp | Có thể null; không thay checksum hoặc signature |

Mảnh code quan sát runtime:

~~~java
// Đoạn minh họa; plugin là một object đã được host nhận.
Class<?> actual = plugin.getClass();
System.out.println("Class: " + actual.getName());
System.out.println("Loader: " + actual.getClassLoader());
System.out.println("Module: " + actual.getModule());
var protectionDomain = actual.getProtectionDomain();
System.out.println("Source: " +
        (protectionDomain == null ? null : protectionDomain.getCodeSource()));
~~~

Đừng dựa vào tên JAR giống nhau để kết luận rằng đó là **cùng artifact**. Một đường dẫn có thể chứa bản mới còn các class đã được JVM định nghĩa từ bản cũ; cần quản lý version/hash, loader và thời điểm activation.

## 13. Ma trận kiểm thử compatibility

Một compatibility matrix có thể bao gồm:

| Runtime | SPI runtime | Dependency runtime | Kết quả cần kiểm |
| --- | --- | --- | --- |
| JDK 17 | API v2 | Library versions đúng | Plugin Java17 được phát hiện, tạo và hoạt động |
| JDK 21 | API v2 | Library versions đúng | Regression/integration tests; không tự coi tương thích tuyệt đối |
| JDK 11 | API v2 | Dù đủ dependency | Plugin class major61 phải bị reject trước activation |
| JDK 17 | API v1 | Library versions đúng | Plugin yêu cầu banner() v2 phải bị reject hoặc test báo NoSuchMethodError |
| JDK 17 | API v2 | Thư viện gián tiếp quá cũ | Contract/linkage test phát hiện |
| JDK 17 | API v2 | Hai bản SPI ở hai loaders | Kiểm tra type identity, không tự động cast được |
| JDK 17 JPMS | API v2 | Module path thiếu module | Kiểm tra resolution/uses/provides trước activation |
| JDK 17 plugin v1 → v2 | API v2 | Dependency graph mới | Test loader mới, start, chuyển traffic, stop, rollback |

Đây là ma trận **minh họa**, không phải tuyên bố rằng mọi kịch bản được kiểm chứng chỉ từ một bài test. CI nên chạy thật trên **JDK tối thiểu** đã công bố, JDK sản xuất chính và các kết hợp thư viện có rủi ro.

Các bài contract test quan trọng:
- ServiceLoader có thấy provider và tạo được instance?
- Instance có assignable vào đúng SPI Class của host?
- Những method SPI mà host sẽ gọi có thực thi thành công trên runtime dependencies?
- Giá trị trả về, exception, data schema và concurrency có đúng hợp đồng?
- Các plugin khác có gây xung đột dependency hoặc duplicate classes không?
- JPMS layer/module graph đúng cấu hình thực tế không?
- Có thể start version mới, rollback và stop version cũ một cách kiểm soát không?

Chỉ kiểm tra constructor hoặc health endpoint chưa đủ: một lỗi symbolic method reference có thể xuất hiện trên đường thực thi hiếm được gọi.

## 14. Quy trình build và phát hành phù hợp

Một quy trình thường có:

1. **Định nghĩa runtime minimum:** ví dụ Java 17, SPI API version/range và module/classloader boundary.
2. **Chọn toolchain:** compiler version và **--release** phù hợp, annotation processor và dependency versions được khóa.
3. **Biên dịch/test:** compile plugin, chạy unit tests, static analysis và kiểm tra public SPI contract.
4. **Xác minh artifact:** xem class-file major/minor, manifest, module-info, META-INF/services và dependency graph.
5. **Integration test trên runtime đích:** đúng JDK version, API/SPI, dependencies và loader/layer; kiểm tra behavior, không chỉ discovery.
6. **Phát hành artifact versioned:** plugin version, checksum/signature phù hợp, build provenance, requirements rõ.
7. **Preflight khi host cài:** từ chối target JDK lớn hơn host, thiếu dependency, SPI version ngoài hỗ trợ hoặc sai module configuration.
8. **Kích hoạt có kiểm soát:** start provider, readiness/health, chuyển lưu lượng nếu đang nâng cấp.
9. **Rollback/retire:** quay lại artifact đã được test, stop và giải phóng resources; dùng loader/layer mới nếu cần thay bytecode.
10. **Quan sát:** log version plugin, version SPI, JVM, loader, artifact hash và cause của lỗi linkage.

Nếu host **nhận source rồi biên dịch động**, thêm chính sách compiler options, diagnostics, cache theo source hash + API version + dependency fingerprint, giới hạn tài nguyên, quyền truy cập và xử lý processor/build-time code. Nhận source Java hoặc JAR đều có thể là rủi ro security; compiler và class loader không phải sandbox.

### Metadata ví dụ

~~~text
pluginId: demo-greeting
pluginVersion: 2.0.0
targetJava: 17
spiApiRange: [2.0,3.0)
requiredDependencies: resolved versions + checksums
testedRuntimeJdks: actual CI test results
artifactSha256: actual generated hash
~~~

Đây là **mẫu metadata do ứng dụng tự thiết kế**, không phải cú pháp JVM/ServiceLoader hiểu tự động. Không ghi một JDK vào testedRuntimeJdks nếu pipeline chưa thực sự chạy test trên JDK đó.

## 15. Các sai lầm thường gặp

- **JDK build = JDK runtime:** compiler version và target release khác nhau; cần xác minh cả hai.
- **Thấy major61 thì mặc định chạy được mọi Java17:** runtime dependencies, APIs và behavior vẫn có thể không tương thích.
- **Dùng -target17 mà thiếu ràng buộc platform API:** có thể gọi JDK API mới không tồn tại trên Java17.
- **Dùng --release17 rồi bỏ qua thư viện:** cờ này không xử lý ABI của Jackson, Guava, JDBC driver hoặc SPI tùy chỉnh.
- **Chỉ thử ServiceLoader.findFirst():** nhiều symbolic references chưa được invoke nên linkage error có thể đến muộn.
- **Giữ hai bản SPI trong host/plugin:** class loader identity khác khiến cast và assignability sai.
- **Cài plugin bằng cách ghi đè JAR đã load:** JVM không tự thay class definition của loader cũ.
- **Bỏ qua dependency transitive:** plugin compile với library v3 nhưng runtime dependency graph lại chọn v1/v2.
- **Xem JPMS như classpath:** requires, exports, uses/provides và module resolution còn là các ràng buộc riêng.
- **Suy compatibility từ tên file hoặc manifest tự viết:** hash, classfile và runtime tests đáng tin hơn.
- **Chỉ kiểm tra một JVM vendor/version:** test matrix cần phản ánh những runtime mà sản phẩm cam kết hỗ trợ.
- **Đồng nhất binary compatibility với đúng nghiệp vụ:** giữ method descriptor không đảm bảo semantics và dữ liệu không đổi.

## 16. Checklist trước khi cho phép plugin hoạt động

- [ ] Runtime JVM tối thiểu và danh sách Java releases hỗ trợ đã được công bố.
- [ ] Compiler toolchain được kiểm soát, **--release** được cấu hình đúng.
- [ ] Mọi class có thể load và dependency quan trọng có class-file major/minor phù hợp.
- [ ] Platform API/JDK module dùng trong plugin tồn tại trên runtime target.
- [ ] Plugin compile với đúng API/SPI version/range và host thực thi đúng binary contract.
- [ ] Thư viện trực tiếp, transitive và native dependencies có version/ABI phù hợp.
- [ ] API/SPI chung có một type identity xuyên host và provider; không duplicate định nghĩa giữa loaders.
- [ ] Với JPMS, module descriptors, readability, exports/opens, uses/provides và layer được kiểm tra.
- [ ] Đã chạy integration/contract tests trên runtime đích, bao gồm những method SPI quan trọng.
- [ ] Có metadata artifact ID/version/hash, build provenance và policy reject trước activation.
- [ ] Có rollback/hot update dùng loader/layer và lifecycle phù hợp; không phụ thuộc ServiceLoader.reload() để thay bytecode.
- [ ] Trust boundary, code provenance và các giới hạn tài nguyên được thiết kế độc lập với compatibility.

**Kết luận:** Khi biên dịch hoặc triển khai plugin, phải đồng thời kiểm tra **bytecode target**, **JDK/platform API**, **library và SPI binary contract**, **class identity/module graph** và **hành vi runtime**. Bài thực hành dùng cùng một plugin Java17 major61 nhưng thay runtime API v2 bằng v1 đã gây NoSuchMethodError; đây là minh chứng rằng việc hỗ trợ class-file version chỉ là lớp kiểm tra đầu tiên.

## Tài liệu Java 17 chính thức

- JLS, Chapter 13 — Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- JVMS, Chapter 4 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- javac — --release và cross-compilation: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- jdeps — dependency analysis: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- ServiceLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
