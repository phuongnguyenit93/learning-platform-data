# Kiểm chứng API: Kiểm tra lỗi startup, linkage và nạp tài nguyên trong Java 11+

## 1. Vì sao chương trình biên dịch thành công nhưng không chạy được?

Một dịch vụ Java có thể **biên dịch và pass unit test** nhưng thất bại ở môi trường triển khai với thông báo như:

- `Could not find or load main class` ngay khi chạy lệnh `java`.
- `NoClassDefFoundError` do thiếu class/dependency khi runtime cần dùng nó.
- `NoSuchMethodError` hoặc `NoSuchFieldError` do class được nạp có **API binary khác** so với class mà ứng dụng đã biên dịch.
- `ExceptionInInitializerError` khi khởi tạo static state thất bại.
- `IllegalStateException: missing ...` khi code bắt buộc đọc một resource mà JAR không đóng gói.
- `ServiceConfigurationError` vì file `META-INF/services/...` không có, sai nội dung hoặc lớp provider không hợp lệ.
- `FindException`/`ResolutionException` khi dùng module path và module graph không hợp lệ.

**Các lỗi này không cùng nguyên nhân.** Từ góc nhìn **kiểm chứng API**, phải phân biệt ít nhất ba câu hỏi:

1. **Startup:** Launcher tìm đúng entry point và dựng được môi trường chạy chưa?
2. **Linkage/binary compatibility:** JVM có tải, xác minh, phân giải và gọi được **class, method, field thật** trong artifact cuối không?
3. **Resource/service loading:** File cấu hình, template, service-provider descriptor, module resource có thật và **được tìm thấy bởi loader/module phù hợp** không?

Bài dùng cơ chế **Java 11+ còn được hỗ trợ hiện nay**. Ví dụ được biên dịch với `javac --release 11` và chạy thử bằng OpenJDK 21; không dựa vào endorsed/ext directories, boot-classpath hacks, cơ chế tải lớp lỗi thời hay cờ JVM đã bị loại bỏ.

### Một nguyên tắc cần nhớ

**“Compile PASS” không bằng “Runtime PASS”.** Compiler chỉ thấy các dependency/class files được cung cấp lúc compile. Lúc runtime, classpath/module path, JAR content, phiên bản dependency, loader identity, quyền truy cập tài nguyên và môi trường có thể khác. Đôi khi JVM chỉ phân giải một method khi code path thật sự được thực thi; vì vậy **ứng dụng có thể in startup banner rồi mới lỗi**.

## 2. Hình dung các giai đoạn có thể phát sinh lỗi

Một cách nhìn phù hợp với Java Virtual Machine Specification (JVMS):

~~~text
Lệnh launch (java / -jar / -m)
       |
       v
Chọn main class và xây dựng classpath/module graph
       |
       +--> Lỗi launcher: main class/JAR/module không tồn tại
       |
       v
Loading: tìm bytes class theo binary name và defining ClassLoader
       |
       +--> ClassNotFoundException hoặc NoClassDefFoundError tùy ngữ cảnh
       |
       v
Linking: verify, prepare, resolve các tham chiếu khi cần
       |
       +--> VerifyError, NoSuchMethodError, IllegalAccessError,
       |    IncompatibleClassChangeError, NoSuchFieldError, ...
       |
       v
Initialization: chạy static initializer / static field initialization
       |
       +--> ExceptionInInitializerError; lần dùng tiếp có thể
       |    gặp NoClassDefFoundError: Could not initialize class ...
       |
       v
main(...) / chương trình / reflection / ServiceLoader
       |
       +--> Missing resources, ServiceConfigurationError,
       |    lỗi runtime config hoặc linkage phát sinh muộn
~~~

**Sơ đồ mang tính hướng dẫn**, không khẳng định JVM bắt buộc eager-resolve mọi reference theo một lịch cố định. Thời điểm class được load, reference được resolve hoặc verifier chạy phụ thuộc hành vi hợp lệ của JVM. Vì vậy test **chỉ khởi động main** chưa đủ để bảo đảm mọi API path sẽ hoạt động.

### Phân biệt “chưa tìm được class” và “class đã từng khởi tạo thất bại”

`NoClassDefFoundError` thường liên quan tới thiếu class lúc runtime, nhưng cũng có thể xuất hiện vì **class đã bị đánh dấu khởi tạo lỗi** trước đó. Đọc cả **message, cause chain và lỗi đầu tiên trong logs**, đừng dựa vào tên error duy nhất.

## 3. Bảng nhận diện lỗi startup, linkage và resource

| Triệu chứng | Nhóm | Nghi vấn chính | Bước kiểm chứng |
| --- | --- | --- | --- |
| `Could not find or load main class` | Launcher/startup | Sai binary name, classpath không chứa main | `jar --list`, `java -cp ... fully.qualified.Main` |
| `no main manifest attribute` | Executable JAR | JAR thiếu `Main-Class` | `jar --describe-module` không thay manifest; xem `META-INF/MANIFEST.MF` |
| `ClassNotFoundException` | Dynamic class lookup | `Class.forName`/loader không tìm thấy name | Kiểm class name, loader và artifact |
| `NoClassDefFoundError` | Loading/linkage | Thiếu class runtime hoặc failed initialization | Đọc cause, `jdeps --missing-deps`, JAR entries |
| `NoSuchMethodError` | Binary API linkage | Compile v1, runtime v2 thiếu method descriptor | `javap -p -s` trên **runtime JAR** |
| `NoSuchFieldError` | Binary API linkage | Runtime class không có field được bytecode tham chiếu | `javap -p -s`, dependency version |
| `IncompatibleClassChangeError` | Binary incompatibility | Ví dụ API đổi static/instance hoặc class/interface shape | Đối chiếu binaries và JVM linkage |
| `AbstractMethodError` | Binary compatibility | Class implementation thiếu method cần được gọi | Kiểm interface/implementation versions |
| `IllegalAccessError` | Access/linkage | Quyền truy cập bytecode/package/nest/module không hợp lệ | `javap` và runtime/module/class loader |
| `UnsupportedClassVersionError` | Classfile version | Bytecode target mới hơn JVM chạy | `java -version`, `javap -verbose`, `javac --release` |
| `VerifyError` / `ClassFormatError` | Verify/classfile | Class bytecode hỏng hoặc transformer sai | Rebuild sạch, kiểm obfuscator/shading |
| `ExceptionInInitializerError` | Class initialization | Static initializer ném exception | Tìm `getCause()` và lỗi gốc |
| `UnsatisfiedLinkError` | Native linkage | JNI library không tìm thấy hoặc native symbol mismatch | Kiểm platform, binary architecture, library path |
| `getResourceAsStream(...) == null` | Resource loading | Sai path, thiếu file trong JAR, module encapsulation | `jar --list`, Class vs ClassLoader semantics |
| `ServiceConfigurationError` | SPI/provider | `META-INF/services` sai hoặc provider không tạo được | Kiểm descriptor/`uses`/`provides` |
| Module resolution error | JPMS startup | Sai `--module-path`, thiếu `requires`/module, split package | `--show-module-resolution`, `jar --describe-module` |

**Không nên catch mọi `LinkageError` rồi bỏ qua để server tiếp tục chạy**. LinkageError thường có nghĩa chương trình đang chạy với artifact/API không tương thích. Cần sửa dependency/deployment, không “tự chữa” bằng việc nuốt lỗi hoặc mở quyền truy cập bừa bãi. Có thể catch Error trong **test có chủ đích** để xác minh triệu chứng, nhưng không coi đó là chiến lược phục hồi production.

## 4. Startup: `java -cp`, `java -jar` và `java -m` không giống nhau

Ba chế độ launch chính của Java 11:

~~~bash
# Main class trên classpath
java -cp 'app.jar:lib-v1.jar' demo.app.ApiProbe

# Executable JAR có Main-Class trong manifest
java -jar app.jar

# Main class của một named module
java --module-path mods -m demo.resource/demo.resource.Resources
~~~

Các lệnh trên là **mẫu**, cần artifacts tương ứng. Trên Windows, dấu phân cách classpath thường là **`;`** thay cho **`:`** trên Linux/macOS.

### `java -jar` và classpath của application

Oracle Java 11 launcher docs nêu rõ: khi chạy `java -jar app.jar`, những cài đặt classpath ngoài như `-cp`/`CLASSPATH` **không được dùng như trong chế độ main class**. Nếu app.jar chỉ chứa application classes mà dependency nằm ở `lib-v1.jar` riêng, chạy `java -jar app.jar` có thể thiếu dependency.

Những cách phân phối hợp lệ gồm:

- Đóng dependencies trong một executable/fat JAR bằng công cụ build hỗ trợ đúng metadata.
- Dùng `Main-Class` cùng **manifest `Class-Path`** trỏ tới các thư viện cạnh JAR bằng **đường dẫn tương đối** hợp lệ.
- Chạy main class với một classpath được thiết lập **rõ ràng**.
- Dùng module path và module metadata hợp lệ nếu ứng dụng là JPMS module.

**Không có một cờ `-cp` đặt cạnh `-jar` khiến `-jar` tự động nạp tất cả dependencies bạn muốn**. Không mặc định JAR cùng thư mục được tải nếu thiếu launcher/manifest config.

### Tên class khi launch là binary name

Nếu file `ApiProbe.java` khai báo `package demo.app;`, lệnh chạy phải dùng **`demo.app.ApiProbe`**, không phải tên file `ApiProbe.java` hoặc đường dẫn `demo/app/ApiProbe.class` trong chế độ main class. Đảm bảo entry point có chữ ký:

~~~java
public static void main(String[] args)
~~~

Trên JDK 11, đây là dạng entry point phổ biến và tương thích. Không lấy những thay đổi cách launch trên JDK rất mới áp vào Java 11 mà không kiểm tương thích.

## 5. Dựng tình huống API v1/v2 để kiểm binary compatibility

Ví dụ chạy thật sử dụng **hai phiên bản của cùng một API class** và một app client:

~~~text
src-v1/demo/lib/Greeting.java         <-- phiên bản API được dùng khi compile
src-v2/demo/lib/Greeting.java         <-- phiên bản runtime thiếu method
src-app/demo/app/ApiProbe.java        <-- app client
src-app/demo/app/banner.txt           <-- resource cần đóng gói

build/v1/...    --> lib-v1.jar
build/v2/...    --> lib-v2.jar
build/app/...   --> app.jar
~~~

**Ý tưởng:** `app.jar` được compile với `Greeting.greet()` của v1. V2 vẫn cung cấp class `demo.lib.Greeting` nhưng **đã bỏ `greet()` và đổi sang `salute()`**. JVM không báo compile error cho app được xây từ v1, nhưng khi runtime dùng v2, bytecode `invokestatic` tới `greet()` không thể resolve: **`NoSuchMethodError`**.

### API v1 — `src-v1/demo/lib/Greeting.java`

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {}

    public static String greet() {
        return "hello-v1";
    }
}
~~~

### API v2 — `src-v2/demo/lib/Greeting.java`

~~~java
package demo.lib;

public final class Greeting {
    private Greeting() {}

    public static String salute() {
        return "hello-v2";
    }
}
~~~

**Đây là một thay đổi cố ý làm hỏng binary compatibility**, không phải khuyến nghị thiết kế API. Đổi hoặc xóa method được client cũ dùng mà không hỗ trợ tương thích sẽ làm client đã biên dịch thất bại, ngay cả khi class cùng tên vẫn tồn tại.

### Ứng dụng — `src-app/demo/app/ApiProbe.java`

~~~java
package demo.app;

import demo.lib.Greeting;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ApiProbe {
    private static String read(InputStream stream) throws Exception {
        if (stream == null) {
            throw new IllegalStateException(
                    "missing demo/app/banner.txt");
        }
        try (InputStream in = stream) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("resourceRelative="
                + read(ApiProbe.class.getResourceAsStream("banner.txt")));
        System.out.println("resourceAbsolute="
                + read(ApiProbe.class.getResourceAsStream(
                        "/demo/app/banner.txt")));
        System.out.println("resourceLoader="
                + read(ApiProbe.class.getClassLoader().getResourceAsStream(
                        "demo/app/banner.txt")));
        System.out.println("api=" + Greeting.greet());
    }
}
~~~

Tệp **`src-app/demo/app/banner.txt`** có đúng nội dung:

~~~text
ready
~~~

Chương trình này cố ý **đọc resource trước khi gọi API**. Nhờ vậy cùng một client có thể chứng minh lỗi resource packaging và lỗi API linkage là **hai nhóm khác nhau**: bản app thiếu resource hỏng trước khi chạm tới `Greeting.greet()`; bản app có resource nhưng chạy với API v2 hỏng khi gọi method.

`InputStream.readAllBytes()` đã có từ Java 9, `StandardCharsets.UTF_8` là API chuẩn; code chạy được với `--release 11` và không cần thư viện ngoài Java.

## 6. Biên dịch và đóng JAR chính xác

Trong Bash trên Linux/macOS, từ thư mục chứa ba `src-*` ở trên:

~~~bash
mkdir -p build/v1 build/v2 build/app

javac --release 11 -d build/v1 \
  src-v1/demo/lib/Greeting.java

javac --release 11 -d build/v2 \
  src-v2/demo/lib/Greeting.java

# App compile against v1, NOT v2.
javac --release 11 -cp build/v1 -d build/app \
  src-app/demo/app/ApiProbe.java

# javac KHONG tu copy .txt resources; packaging phai copy rieng.
cp src-app/demo/app/banner.txt build/app/demo/app/banner.txt

jar --create --file lib-v1.jar -C build/v1 .
jar --create --file lib-v2.jar -C build/v2 .
jar --create --file app.jar --main-class demo.app.ApiProbe \
  -C build/app .
~~~

**Cần phân biệt compile dependencies với runtime dependencies.** `javac -cp build/v1` chỉ cho compiler thấy API v1 lúc xây app. Nó **không nhúng `Greeting.class` vào `app.jar`**. Runtime phải có đúng library bạn quyết định phân phối.

**Stdout chính xác đã kiểm chứng bằng OpenJDK 21, compiler target 11:**

~~~bash
java -cp 'app.jar:lib-v1.jar' demo.app.ApiProbe
~~~

~~~text
resourceRelative=ready
resourceAbsolute=ready
resourceLoader=ready
api=hello-v1
~~~

Như vậy class, resource và method v1 đều được nạp thành công. Chương trình không có output khác trừ lỗi môi trường nếu path/JAR sai.

### Kiểm inventory của JAR

~~~bash
jar --list --file app.jar
jar --list --file lib-v1.jar
jar --list --file lib-v2.jar
~~~

Những entries phải hiện diện:

~~~text
app.jar:
  demo/app/ApiProbe.class
  demo/app/banner.txt

lib-v1.jar:
  demo/lib/Greeting.class

lib-v2.jar:
  demo/lib/Greeting.class
~~~

**Cùng tên entry không chứng minh cùng binary API**. Hai JAR v1/v2 đều có `demo/lib/Greeting.class` nhưng method signatures bên trong khác. `jar --list` là kiểm tra **có tệp hay không**, không thay `javap` hoặc runtime smoke test.

## 7. Tái hiện bốn kiểu lỗi mà compile-time test có thể bỏ lỡ

### Trường hợp A — runtime API v2, lỗi `NoSuchMethodError`

~~~bash
java -cp 'app.jar:lib-v2.jar' demo.app.ApiProbe
~~~

**Phần output quan trọng thực tế:**

~~~text
resourceRelative=ready
resourceAbsolute=ready
resourceLoader=ready
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String demo.lib.Greeting.greet()'
~~~

Thông báo đã được **xuống dòng/rút gọn** để dễ đọc. Ứng dụng đọc đủ ba resource nhưng hỏng khi JVM resolve method đã compile với v1. **Cách sửa:** runtime phải cung cấp một `Greeting` có đúng **binary descriptor** mà client cần, hoặc phải rebuild và kiểm chứng client với API v2 phù hợp; không đổi classpath ngẫu nhiên đến khi may mắn chạy được.

### Trường hợp B — thiếu library hoàn toàn

~~~bash
java -cp app.jar demo.app.ApiProbe
~~~

**Phần output thực tế có ý nghĩa:**

~~~text
resourceRelative=ready
resourceAbsolute=ready
resourceLoader=ready
java.lang.NoClassDefFoundError: demo/lib/Greeting
Caused by: java.lang.ClassNotFoundException: demo.lib.Greeting
~~~

Ứng dụng vẫn vào `main()` và đọc resource, nhưng khi gọi `Greeting.greet()` JVM không tìm được định nghĩa class. Đây là một **linkage/loading failure** sau startup, không phải “main class không tồn tại”.

Chạy **`java -jar app.jar`** trong ví dụ này cũng thiếu library vì JAR chưa có manifest `Class-Path` để chỉ ra `lib-v1.jar`. Không suy rằng mọi `java -jar` đều thất bại với thư viện ngoài: manifest Class-Path hợp lệ hoặc launcher đóng gói đặc thù có thể giải quyết dependencies.

### Trường hợp C — thiếu resource trong JAR

Tạo một JAR cố ý chỉ đóng gói class mà không chứa `banner.txt`:

~~~bash
jar --create --file app-no-resource.jar \
  --main-class demo.app.ApiProbe \
  -C build/app demo/app/ApiProbe.class

java -cp 'app-no-resource.jar:lib-v1.jar' demo.app.ApiProbe
~~~

**Đoạn lỗi đã kiểm chứng:**

~~~text
Exception in thread "main" java.lang.IllegalStateException:
  missing demo/app/banner.txt
~~~

Đây là **fail-fast error do chính code đưa ra** khi `getResourceAsStream(...)` trả `null`; Java không tự ném `IllegalStateException` cho mọi resource miss. Nếu không kiểm `null` và dùng stream trực tiếp, lỗi có thể biến thành `NullPointerException` muộn hơn và khó chẩn đoán hơn.

### Trường hợp D — launcher không tìm được main class

~~~bash
java -cp lib-v1.jar demo.app.ApiProbe
~~~

**Kết quả thực tế:**

~~~text
Error: Could not find or load main class demo.app.ApiProbe
Caused by: java.lang.ClassNotFoundException: demo.app.ApiProbe
~~~

`lib-v1.jar` có `Greeting.class` nhưng **không có `demo/app/ApiProbe.class`**. Đây là lỗi **entry point/classpath**, khác với trường hợp B (main đã chạy rồi nhưng thiếu một dependency tại callsite).

### Bảng đối chiếu kết quả

| Runtime setup | Resource | API call | Kết quả |
| --- | --- | --- | --- |
| `app.jar + lib-v1.jar` | Có | `Greeting.greet` có | PASS, `api=hello-v1` |
| `app.jar + lib-v2.jar` | Có | Thiếu `greet` trong v2 | `NoSuchMethodError` |
| Chỉ `app.jar` | Có | Thiếu `Greeting` | `NoClassDefFoundError` |
| `app-no-resource.jar + lib-v1.jar` | Thiếu | Chưa gọi | `IllegalStateException` của app |
| Chỉ `lib-v1.jar` với main `ApiProbe` | Không có main class | Không tới app | Launcher không tìm main |

**Lỗi có thể xuất hiện muộn.** JVM có thể không resolve một tham chiếu tới method/class cho tới khi thực thi đường code đó. Để kiểm chứng API, test phải **thực sự gọi các endpoints/methods cần bảo đảm** chứ không chỉ xem `java -version`, start container hoặc health-check nông.

## 8. Kiểm binary API bằng `javap` và phụ thuộc bằng `jdeps`

### `javap`: thấy class có member nào thật

~~~bash
javap -p -s -classpath lib-v1.jar demo.lib.Greeting
javap -p -s -classpath lib-v2.jar demo.lib.Greeting
~~~

Hai phiên bản đều có binary name `demo.lib.Greeting`, nhưng chữ ký khác:

~~~text
v1:
  public static java.lang.String greet();
  descriptor: ()Ljava/lang/String;

v2:
  public static java.lang.String salute();
  descriptor: ()Ljava/lang/String;
~~~

Điều cần kiểm là **tên + parameter types + return type ở descriptor bytecode**, cộng với static/instance kind và access level. `javap -s` cho descriptor; `-p` in cả các thành viên không phải public để chẩn đoán. **`NoSuchMethodError`** xảy ra khi reference tới method descriptor cần dùng không có ở class runtime. Một thay đổi field/method static thành instance hoặc thay class/interface shape có thể thuộc nhóm **`IncompatibleClassChangeError`** thay vì chỉ `NoSuchMethodError`.

### `jdeps`: tìm dependencies class-level bị thiếu

~~~bash
jdeps --missing-deps app.jar
~~~

**Kết quả đã kiểm chứng, rút gọn:**

~~~text
app.jar -> not found
demo.app.ApiProbe -> demo.lib.Greeting   not found
~~~

Kết quả này chỉ ra `app.jar` tham chiếu `demo.lib.Greeting` mà **`jdeps` không tìm thấy trong các module/classpath đưa cho nó**. Khi cung cấp đúng v1:

~~~bash
jdeps --class-path lib-v1.jar app.jar
~~~

`jdeps` phân tích dependencies ở mức class/module, nhưng **không phải trình kiểm tra toàn bộ binary compatibility hoặc mọi đường reflection/resource**. Nếu v2 cung cấp `Greeting.class` cùng tên, `jdeps` có thể không đánh dấu missing class dù method `greet()` đã biến mất. Cần **`javap` hoặc một binary compatibility checker phù hợp**, và quan trọng nhất là **runtime smoke test**.

### Kiểm version bytecode

~~~bash
javap -verbose -classpath app.jar demo.app.ApiProbe
java -version
~~~

Trong output `javap -verbose`, Java 11 class files có **`major version: 55`**. Nếu bạn build trên JDK 21 mà quên `--release 11`, classfile target có thể mới hơn runtime mục tiêu. `UnsupportedClassVersionError` nghĩa JVM không hỗ trợ class file version được nạp — **không sửa bằng cách đổi Java source package**. Build với `--release 11` khi Java 11 là runtime contract, đồng thời chạy test bằng **runtime thấp nhất được hỗ trợ**.

### Xem class được load từ đâu

Có thể bật Unified Logging:

~~~bash
java -Xlog:class+load=info:file=class-load.log:uptime,level,tags \
  -cp 'app.jar:lib-v2.jar' demo.app.ApiProbe
~~~

File `class-load.log` giúp xác định class được nạp từ JAR/module nào trong môi trường cụ thể. Cần kiểm **thứ tự classpath**, các JAR bị nhân bản, plugin/custom classloaders và fat-JAR relocation. Class log thường lớn, có thông tin về nội bộ hệ thống; chỉ bật trong chẩn đoán được cho phép và có chính sách cleanup.

**Không coi việc tên class giống nhau là class identity giống nhau** trong hệ thống custom ClassLoader: identity dựa trên binary name **và defining class loader**. Classpath collision trong một loader và cùng class name do nhiều loaders định nghĩa là hai trường hợp cần phân biệt.

## 9. Class loading khác class initialization: lỗi static đầu tiên và những lần sau

Một số `NoClassDefFoundError` xuất hiện **không phải vì thiếu tệp `.class`**, mà vì class đã thất bại trong static initialization.

Tạo **`InitProbe.java`**:

~~~java
public class InitProbe {
    static class Broken {
        static final String DATA = load();

        static String load() {
            throw new IllegalStateException("invalid config");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.DATA);
            } catch (LinkageError error) {
                System.out.println("attempt" + attempt + "="
                        + error.getClass().getSimpleName());
                if (error.getCause() != null) {
                    System.out.println("cause" + attempt + "="
                            + error.getCause().getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 11 InitProbe.java
java InitProbe
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
attempt1=ExceptionInInitializerError
cause1=IllegalStateException
attempt2=NoClassDefFoundError
cause2=ExceptionInInitializerError
~~~

**Giải thích:**

- Ở lần đầu, `Broken.DATA` kích hoạt initialization; phương thức `load()` ném `IllegalStateException`, JVM báo **`ExceptionInInitializerError`**.
- Class bị đánh dấu initialization failed. Lần cố sử dụng tiếp trong cùng JVM dẫn đến **`NoClassDefFoundError`** mang thông tin “Could not initialize class”, với nguyên nhân liên quan `ExceptionInInitializerError`.
- Đọc **lỗi đầu tiên** mới thấy cấu hình nguyên nhân. Nếu chỉ nhìn log `NoClassDefFoundError` lần thứ hai rồi bổ sung JAR, bạn có thể sửa sai chỗ.

Đoạn catch `LinkageError` chỉ để **minh họa trong test**. Trong server production, không nên nuốt lỗi khởi tạo quan trọng và tiếp tục phục vụ request như không có gì xảy ra. Sửa nguyên nhân rồi khởi động lại tiến trình theo quy trình quản trị.

## 10. Nạp resource: `Class.getResourceAsStream` khác `ClassLoader.getResourceAsStream`

Với package `demo.app` và resource `demo/app/banner.txt`:

~~~java
// Tương đối so với package của ApiProbe:
ApiProbe.class.getResourceAsStream("banner.txt");

// Tuyệt đối từ gốc classpath/module:
ApiProbe.class.getResourceAsStream("/demo/app/banner.txt");

// ClassLoader nhận path tương đối từ classpath root, KHÔNG có slash đầu:
ApiProbe.class.getClassLoader()
        .getResourceAsStream("demo/app/banner.txt");
~~~

**Ba cách đều tìm `ready` trong fixture classpath đã kiểm chứng.**

### Quy tắc path quan trọng

- `Class.getResourceAsStream("banner.txt")`: nếu không có `/` đầu, tìm **tương đối package** của class.
- `Class.getResourceAsStream("/demo/app/banner.txt")`: nếu có `/` đầu, tìm **absolute resource name**.
- `ClassLoader.getResourceAsStream("demo/app/banner.txt")`: nhận path dạng `/`-separated **từ root**, không dùng leading slash như cơ chế `Class`.
- Các hàm có thể trả **`null`** nếu không tìm được/không được phép truy cập; **phải kiểm null** trước khi đọc.
- Dùng **`InputStream` + UTF-8** hoặc reader đúng encoding. Không dùng `File`/`Paths.get(resourceUrl.toURI())` cho mọi resource trong JAR vì resource URL có thể dùng scheme `jar:` và **không phải file OS bình thường**.
- Dùng `try-with-resources` để đóng stream.
- Kiểm **case sensitivity**, dấu `/` và cả đường dẫn entry thực trong JAR. File tồn tại trong project không đủ nếu chưa được copy vào artifact.
- Tránh file resource trùng tên trong nhiều JAR; lookup order trong một số cấu hình không được quy định như bạn mong đợi.

### Mã fail-fast khi thiếu resource

~~~java
static String requiredText(Class<?> owner, String relativeName)
        throws Exception {
    try (InputStream in = owner.getResourceAsStream(relativeName)) {
        if (in == null)
            throw new IllegalStateException(
                    "Required resource missing: " + relativeName);
        return new String(
                in.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Đây là **đoạn minh họa cần đặt trong class và thêm imports**; không phải chương trình chạy độc lập. Nếu tài nguyên là cấu hình bắt buộc, nên fail startup rõ nguyên nhân. Với resource optional, xử lý fallback có chủ đích, không che các lỗi permission hoặc schema hỏng.

### File config có trong `src/main/resources` nhưng thiếu trong JAR?

Maven/Gradle thường copy resources khi dùng đúng conventions, nhưng custom assembly/shading/exclude rules có thể làm mất chúng. **Kiểm file artifact cuối**:

~~~bash
jar --list --file app.jar
jar --list --file app.jar | grep 'demo/app/banner.txt'
~~~

Đừng chỉ nhìn file ở local source tree hoặc output IDE. Test cả **JAR phân phối thực tế** bằng cùng lệnh/launcher production.

## 11. Named modules (JPMS): tìm được class nhưng không thấy resource

Từ Java 9 và vẫn áp dụng ở Java 11+, **named modules** có thêm cơ chế encapsulation. Với resource **không có đuôi `.class`** trong package của named module, `ClassLoader.getResourceAsStream(...)` nói chung chỉ tìm được nếu package đó **được `opens` unconditionally**; còn `Class.getResourceAsStream(...)` tìm trong module và tuân theo quyền truy cập dựa trên caller.

**Điều này có thể gây trường hợp trông kỳ lạ:** cùng một file trong module, code của module đọc được qua `Class.getResourceAsStream` nhưng `ClassLoader.getResourceAsStream` trả `null`.

Ví dụ **đã kiểm chứng bằng `javac --release 11` trên OpenJDK 21**:

~~~text
modsrc/
  demo.resource/
    module-info.java
    demo/resource/Resources.java
    demo/resource/config.txt
~~~

### `modsrc/demo.resource/module-info.java`

~~~java
module demo.resource {
    exports demo.resource;
}
~~~

Package `demo.resource` chỉ được `exports`, **không được `opens`**. `exports` cấp quyền truy cập public types theo JPMS, **không đồng nghĩa mở mọi non-class resource cho tìm kiếm chung qua ClassLoader**.

### `modsrc/demo.resource/demo/resource/Resources.java`

~~~java
package demo.resource;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class Resources {
    private static String read(InputStream in) throws Exception {
        if (in == null) return "missing";
        try (InputStream stream = in) {
            return new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("namedModule="
                + Resources.class.getModule().isNamed());
        System.out.println("classLookup="
                + read(Resources.class.getResourceAsStream("config.txt")));
        System.out.println("loaderLookup="
                + read(Resources.class.getClassLoader().getResourceAsStream(
                        "demo/resource/config.txt")));
        System.out.println("moduleLookup="
                + read(Resources.class.getModule().getResourceAsStream(
                        "demo/resource/config.txt")));
    }
}
~~~

`config.txt` có nội dung:

~~~text
module-ready
~~~

### Biên dịch và chạy với module path

~~~bash
mkdir -p mods

javac --release 11 --module-source-path modsrc -d mods \
  modsrc/demo.resource/module-info.java \
  modsrc/demo.resource/demo/resource/Resources.java

cp modsrc/demo.resource/demo/resource/config.txt \
  mods/demo.resource/demo/resource/config.txt

java --module-path mods -m demo.resource/demo.resource.Resources
~~~

**Stdout chính xác từ test:**

~~~text
namedModule=true
classLookup=module-ready
loaderLookup=missing
moduleLookup=module-ready
~~~

### Kết luận đúng từ kết quả

- Class nằm trong named module và có thể đọc resource của **chính mình** bằng `Class.getResourceAsStream`.
- ClassLoader resource lookup không nhìn thấy non-class resource trong package không `opens` unconditionally, dù file ở đúng output path.
- `Module.getResourceAsStream` từ code nằm trong cùng module tìm được resource.
- **Không phải thiếu file**: cùng file tồn tại và Class/Module lookup đọc được.

**Không tự thêm `opens` toàn bộ packages chỉ để làm biến mất `null`.** Nếu code sở hữu chính module, dùng cách lookup của `Class`/`Module` phù hợp, hoặc thiết kế vị trí resource và exports/opens theo nhu cầu hợp lệ. `opens package` mở đường cho deep reflection và resource access ở mức module, có tác động encapsulation cần cân nhắc.

### Module startup khác classpath startup

Trong JPMS có các lỗi như module không tìm được/graph không resolve được, split packages, module không `requires` dependency hoặc provider không được khai báo đúng. Dùng:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m demo.resource/demo.resource.Resources

jar --describe-module --file some-module.jar
jdeps --module-path mods --module demo.resource
~~~

Đây là **mẫu chẩn đoán**; `some-module.jar` phải được thay bằng file có thật. `--show-module-resolution` giúp nhìn module graph được lựa chọn; `jar --describe-module` xem module descriptor. **ClassLoader search trên module path không giống classpath scanning** và JPMS có quy tắc đọc/đóng gói riêng.

## 12. `ServiceLoader`: descriptor hoặc provider có thể mất khi đóng JAR

Ngoài resource cấu hình, một lỗi đóng gói phổ biến là **Service Provider Interface (SPI)** không được khám phá.

### Trên classpath

Ví dụ interface `demo.spi.Greeter`, implementation `demo.impl.GreeterImpl`:

~~~java
// demo/spi/Greeter.java
package demo.spi;
public interface Greeter {
    String message();
}
~~~

~~~java
// demo/impl/GreeterImpl.java
package demo.impl;
import demo.spi.Greeter;

public class GreeterImpl implements Greeter {
    public String message() {
        return "service-ready";
    }
}
~~~

~~~java
// demo/cli/ServiceProbe.java
package demo.cli;
import demo.spi.Greeter;
import java.util.ServiceLoader;

public final class ServiceProbe {
    public static void main(String[] args) {
        int count = 0;
        for (Greeter provider : ServiceLoader.load(Greeter.class)) {
            count++;
            System.out.println("provider=" + provider.message());
        }
        System.out.println("providerCount=" + count);
    }
}
~~~

Đặt descriptor trong JAR tại **`META-INF/services/demo.spi.Greeter`**, nội dung:

~~~text
demo.impl.GreeterImpl
~~~

**Đã kiểm chứng:**

- Nếu class, provider **và descriptor** đều trong cùng JAR: `provider=service-ready`, `providerCount=1`.
- Nếu bỏ **descriptor** nhưng class implementation vẫn còn: `providerCount=0`. Đây không phải lỗi class loading; provider **không được khám phá**.
- Nếu descriptor trỏ tới `missing.impl.DoesNotExist`: `ServiceConfigurationError: Provider missing.impl.DoesNotExist not found` khi ServiceLoader cố lấy provider.

**ServiceConfigurationError extends `Error`, không đồng nghĩa `LinkageError`.** Không bắt chung mọi lỗi SPI dưới `ClassNotFoundException`. Các providers còn có thể hỏng khi instantiate/initialize hoặc không thỏa điều kiện API; cần xem cause và tên provider thực tế.

### Trong named modules

JPMS ưu tiên khai báo trong `module-info.java`:

~~~java
module example.services {
    uses demo.spi.Greeter;
    provides demo.spi.Greeter with demo.impl.GreeterImpl;
}
~~~

Đây là **snippet minh họa** về cú pháp, không phải một module mẫu độc lập hoàn chỉnh vì cần source classes đúng module. Với provider ở module khác, việc khai báo `uses`, `provides` và `requires`/exports phù hợp phải được thiết kế theo module graph. Không cố dùng một descriptor classpath cũ để thay cho việc xác định module graph khi đã chạy trong named-module mode.

**Sau shading/fat-JAR build:** nhiều JAR có thể có `META-INF/services/*`. Một công cụ merge không đúng có thể chỉ giữ descriptor của provider cuối, xóa providers khác hoặc không rewrite tên class sau relocation. Kiểm **JAR cuối** và thực sự gọi `ServiceLoader.load` trong integration test.

## 13. Công cụ chẩn đoán: nên dùng theo thứ tự nào?

### Bước 1 — lưu lại điều kiện chạy thật

Thu **full command** (`java`, `-cp`/`-jar`/`-m`, JVM flags), working directory, JDK vendor/build, OS/architecture, environment/container image, artifact SHA-256 và dependency lockfile. Không log password/token nằm trong JVM command-line hoặc environment.

~~~bash
java -version
java --list-modules
~~~

`java --list-modules` cho biết modules có trong runtime hiện tại; với custom `jlink` image, module cần dùng có thể bị bỏ. Một application compile trên full JDK không chắc chạy được trên runtime image rút gọn nếu module bắt buộc vắng mặt.

### Bước 2 — xác minh artifact

~~~bash
jar --list --file app.jar
jar --list --file lib-v1.jar
javap -p -s -classpath lib-v1.jar demo.lib.Greeting
~~~

Kiểm main, `META-INF/MANIFEST.MF`, resource entries, service descriptors, API class/method/field. Không suy đoán từ tên file/JAR; có thể JAR v2 bị đổi tên thành “v1” hoặc trùng dependency khác.

### Bước 3 — phân tích phụ thuộc

~~~bash
jdeps --missing-deps app.jar
jdeps --class-path lib-v1.jar app.jar
~~~

`jdeps` tìm tham chiếu class/module tĩnh, nhưng **không biết mọi tên class do reflection tạo từ string**, resource path hay provider chỉ xuất hiện ở runtime. Nếu `jdeps` báo ổn mà `ServiceLoader` thất bại, tiếp tục kiểm descriptor và class initialization.

### Bước 4 — xem class loading và API linkage

~~~bash
java -Xlog:class+load=info:file=classes.log:uptime,level,tags \
  -cp 'app.jar:lib-v1.jar' demo.app.ApiProbe
~~~

Nếu phát sinh `NoSuchMethodError`, đối chiếu **runtime class origin và signature** bằng `javap -s`. Nếu có `NoClassDefFoundError`, kiểm nguyên nhân đầu tiên và distinguishing error message như `Could not initialize class`.

### Bước 5 — chạy resource/SPI checks bằng chính launcher sẽ triển khai

Đọc một **required config** với đường dẫn đúng của `Class`/`ClassLoader`; trả lỗi rõ path nếu null. Gọi `ServiceLoader.load(...).iterator()` và kiểm ít nhất một provider khi provider bắt buộc. Chạy sau build shading, packaging và qua final artifact — không chỉ từ IDE.

### Bước 6 — thử trên runtime thấp nhất được hỗ trợ

Nếu module đặt mục tiêu Java 11:

~~~bash
javac --release 11 -d build/app src-app/demo/app/ApiProbe.java
~~~

Lệnh này cần thêm `-cp build/v1` như phần 6 vì client có external API dependency; đây là **mẫu chưa đủ compile dependency**. Cấu hình build thực phải luôn cung cấp đầy đủ compile dependencies khi dùng `--release 11`, rồi **run integration tests bằng Java 11** nếu Java 11 nằm trong support matrix.

`javac --release 11` kiểm API và bytecode target của compilation, **không thay kiểm thử trên runtime thực**. Native libraries, module resolution, class loaders, metadata và version-skew có thể chỉ lỗi lúc chạy.

## 14. Kiểm thử tự động nên có những trường hợp nào?

| Ca kiểm thử | Điều kiện PASS | Lỗi cần bắt |
| --- | --- | --- |
| Main class trên runtime classpath | Process exit code 0 | Classpath/main sai |
| Executable JAR | `java -jar` và dependencies đúng | Manifest/main/Classpath sai |
| Named module | `java -m` resolve đúng graph | Missing module/`requires`/split packages |
| API v1 expected | Gọi method/field thật thành công | NoSuchMethodError/NoSuchFieldError |
| API v2 incompatible | Negative test thất bại như mong đợi | Bộ kiểm không phát hiện binary break |
| Runtime thiếu dependency | Phát hiện NoClassDefFoundError | Silent missing dependency |
| Resource required | Load được UTF-8 content từ **JAR cuối** | Resource bị exclude/sai path |
| Resource intentionally omitted | Bị fail-fast với message rõ | NPE mơ hồ hoặc silently default |
| Service descriptor | `ServiceLoader` thấy đúng providers | SPI metadata mất sau shading |
| Broken provider | Test phát hiện ServiceConfigurationError | Provider không được kiểm |
| Static initializer failure | Phát hiện original exception chain | Chỉ nhìn NoClassDefFoundError lần sau |
| Java 11 bytecode | `major version 55` khi target 11 | UnsupportedClassVersionError |
| Custom runtime image | Module cần thiết có trong image | Startup/module resolution failure |
| Real launcher/container | Same classpath/module path/user/workdir | IDE works, deployment fails |

**Không nên cố tình gây lỗi production để “kiểm thử”.** Các negative cases trên chạy ở build/CI/staging với JAR cố ý thiếu tài nguyên/đổi API. Pipeline phải xác nhận process exit status và lỗi dự kiến; đừng so một dòng stderr mong manh từ mọi JDK vendor/version.

### Đề xuất smoke test tối thiểu

1. Kiểm JAR entries và manifest trong artifact cuối.
2. Khởi động bằng **đúng command production** trong container image tương ứng.
3. Nạp **required configuration** và thực hiện một lời gọi thật tới critical API.
4. Khám phá **SPI providers bắt buộc**, kiểm name/type/version.
5. Thực hiện health/functional checks đảm bảo endpoint chính thực sự trả đúng output.
6. Nếu module path, xác minh module resolution và Class/Module resource access.
7. Fail build/deploy khi thiếu resource/dependency hoặc có runtime linkage error.
8. Log đủ exception cause chain để điều tra, không lộ secrets hay thông tin khách hàng.

**Một `200 OK` ở endpoint health nông không chứng minh** database drivers, crypto provider, serialization adapter hoặc API path ít dùng sẽ không bị lỗi binary compatibility về sau. Có thể cần test các luồng nghiệp vụ quan trọng để kích hoạt loading/initialization sớm trong staging.

## 15. Những nhầm lẫn làm tăng thời gian debug

| Ngộ nhận | Thực tế |
| --- | --- |
| “Compile thành công nghĩa là deploy được.” | Runtime dependencies và resources có thể khác compile path. |
| “Tên class có trong JAR thì method chắc có.” | Class v1/v2 cùng binary name có thể khác descriptors. |
| “NoClassDefFoundError luôn do thiếu file.” | Có thể do lần class initialization trước đã hỏng. |
| “ClassNotFoundException và NoClassDefFoundError là một.” | Checked dynamic lookup khác LinkageError khi JVM resolve compiled reference. |
| “`java -jar` vẫn dùng `-cp` như mode main class.” | `-jar` dùng JAR manifest/distribution semantics, bỏ thiết lập classpath bên ngoài. |
| “File có trong project nên getResourceAsStream tìm được.” | Build phải đóng gói resource vào JAR/runtime view đúng. |
| “Class.getResourceAsStream có slash và không slash giống nhau.” | Relative package lookup khác absolute name. |
| “ClassLoader.getResourceAsStream nhận slash đầu.” | ClassLoader dùng root-relative name không có leading slash. |
| “Module exports có nghĩa resources luôn public.” | JPMS resource encapsulation/opens có quy tắc riêng. |
| “Không thấy provider tức code không có implementation.” | Có thể thiếu hoặc sai `META-INF/services`/module provides. |
| “jdeps sạch đồng nghĩa mọi reflection/resource đều đủ.” | `jdeps` không khám phá hết dynamic strings/runtime service lookup. |
| “Bật `-Xlog:class+load` rồi copy logs công khai cũng được.” | Logs có thể lộ nội bộ, cần phân quyền/cleanup. |
| “Thêm `--add-opens` mọi packages sẽ sửa mọi lỗi startup.” | Không thay classpath, binary ABI, missing resources hoặc module graph; giảm encapsulation. |
| “Nuốt mọi LinkageError để tiếp tục server.” | Che một artifact/runtime không tương thích, gây lỗi khó dự đoán. |
| “Shading chỉ cần rename file path.” | Phải xử lý bytecode references, service descriptors, resource relocation nhất quán. |

## 16. Checklist khi xác nhận API/package cho Java 11+

- [ ] Dùng cùng **source commit và artifact checksum** cho test và deployment.
- [ ] Compile với `--release 11` khi Java 11 là baseline; test trên runtime thấp nhất hỗ trợ.
- [ ] Classpath, module path và launcher `-cp/-jar/-m` đúng theo mô hình triển khai.
- [ ] JAR có main class và manifest entry phù hợp nếu chạy `-jar`.
- [ ] API classes ở đúng runtime JAR; không có version skew hoặc duplicate class nguy hiểm.
- [ ] Kiểm **method/field descriptors** bằng `javap`, không chỉ có `.class`.
- [ ] `jdeps --missing-deps` không báo missing dependencies tĩnh; dynamic references test riêng.
- [ ] Critical API thực sự được **invoke trong integration test**, không chỉ load main.
- [ ] Static initializer đọc config/khởi tạo dependencies có error handling và cause logging phù hợp.
- [ ] Required resources nằm trong JAR cuối, path/case/encoding đúng và được fail-fast nếu thiếu.
- [ ] `Class.getResourceAsStream`/`ClassLoader`/`Module` dùng đúng resource lookup semantics.
- [ ] Named modules có module graph, `requires`/`uses`/`provides` và quyền resource access phù hợp.
- [ ] `META-INF/services` được merge/relocate hợp lệ khi tạo fat JAR.
- [ ] Có smoke test trong môi trường container/runtime tương đương production.
- [ ] Dùng `-Xlog:class+load` có giới hạn khi debug, giữ log tránh lộ thông tin nhạy cảm.
- [ ] Không dùng workaround mở tất cả packages hoặc bỏ qua `LinkageError` để che lỗi binary.
- [ ] Negative tests missing class/resource/API/provider được thực hiện **trong CI/staging**, không tác động production.

**Kết luận:** Kiểm chứng API Java 11+ phải vượt qua ba lớp: **launcher tìm đúng entry point**, **JVM liên kết đúng binary API** và **class/module loader tìm được resources/providers cần thiết**. Hãy kiểm chính **artifact cuối** bằng `jar`, `javap`, `jdeps`, runtime smoke tests và resource checks. **Lỗi startup**, **linkage** và **nạp tài nguyên** có thể có biểu hiện gần nhau nhưng cần những phép kiểm khác nhau; phân loại đúng giúp sửa nguyên nhân thay vì thay cờ JVM hoặc version dependency mò mẫm.

## Tài liệu chính thức và hiện hành

- [Oracle Java SE 11 — java launcher](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-cp`, `-jar`, `-m` và cách chọn entry point.
- [Java SE 11 JVMS `5 — Loading, Linking, Initializing](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html): thời điểm và lỗi class loading/linking/initialization.
- [Oracle Java SE 11 — LinkageError](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/LinkageError.html): phân loại lỗi binary incompatibility.
- [Oracle Java SE 11 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/NoClassDefFoundError.html): missing definition khi JVM/class loader cần.
- [Oracle Java SE 11 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/ExceptionInInitializerError.html): static initializer failed và cause.
- [Oracle Java SE 11 — Class](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getResourceAsStream` và class-scoped lookup.
- [Oracle Java SE 11 — ClassLoader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/ClassLoader.html): class/resource lookup và tên path.
- [Oracle Java SE 11 — Module](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Module.html): `getResourceAsStream` và JPMS resource encapsulation.
- [Oracle Java SE 11 — ServiceLoader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/ServiceLoader.html): provider discovery qua descriptor/module.
- [Oracle Java SE 11 — JAR File Specification](https://docs.oracle.com/en/java/javase/11/docs/specs/jar/jar.html): manifest `Main-Class`/`Class-Path`, resource/JAR structure.
- [Oracle Java SE 11 — jdeps](https://docs.oracle.com/en/java/javase/11/tools/jdeps.html): phân tích dependencies tĩnh.
- [Oracle Java SE 11 — javap](https://docs.oracle.com/en/java/javase/11/tools/javap.html): signatures/descriptors/bytecode inspection.
- [Oracle Java SE 11 — jar](https://docs.oracle.com/en/java/javase/11/tools/jar.html): `--list`/`--create`/`--describe-module`.
- [Oracle Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): module resource encapsulation vẫn áp dụng.
- [Oracle Java SE 25 — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): SPI còn là API được hỗ trợ.
- [Oracle Java SE 25 — java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): behavior của classpath, JAR và modules trên JDK hiện hành.

Bài chỉ dùng **kiến thức Java 11+ còn áp dụng hiện nay**. Ba nhóm kiểm chứng đã được chạy trên OpenJDK 21 với `javac --release 11`: executable JAR cùng API v1/v2 và resource thiếu, static initialization failure, JPMS resource visibility; thêm thử nghiệm ServiceLoader descriptor chuẩn/thiếu/sai. Những error excerpts trong bài được rút gọn khi cần để dễ học, còn stdout của các chương trình thành công là kết quả thực tế đã kiểm.