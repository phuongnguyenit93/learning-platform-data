# Ủy quyền bắt buộc cho kiểu nền tảng và API dùng chung

Khi xây dựng **class loader tùy chỉnh** cho plugin, application server hay môi trường chạy nhiều phiên bản thư viện, không thể chỉ quyết định “mọi lớp đều child-first để plugin tự chủ”. Có những **ranh giới phải được tôn trọng**: các kiểu nền tảng do Java runtime cung cấp không được tùy tiện định nghĩa lại; các **kiểu API dùng chung giữa host và plugin** phải có **cùng định nghĩa JVM** nếu muốn truyền object, ép kiểu, gọi interface hoặc trao đổi callback an toàn.

Trong bài này, “ủy quyền bắt buộc” có **hai tầng ý nghĩa cần phân biệt**:

1. **Ràng buộc được runtime/API thực thi:** ví dụ các subclass ClassLoader thông thường **không được định nghĩa class trong package bắt đầu bằng `java.`** qua `defineClass`; vi phạm có thể ném `SecurityException`. Không thể dùng child-first như cách hợp pháp để thay thế `java.lang.String` bằng bản do plugin tự tạo.
2. **Bất biến kiến trúc cần thực thi trong ứng dụng:** một interface hoặc DTO dùng chung như `com.acme.api.Greeter` cần được host và plugin tham chiếu tới **cùng đối tượng `Class<?>`** từ một defining loader chung. Java không tự áp đặt “mọi package `com.acme.api.*` phải parent-first”; **nhà thiết kế loader phải thực hiện chính sách ấy**.

Chiến lược thực tế thường là **parent-first cho lớp nền tảng và API contract dùng chung; child-first có chọn lọc cho implementation/dependency riêng cần cô lập**. Điều này bảo vệ type identity, nhưng phải thực hiện cẩn thận để không vô tình cho plugin ghi đè API hoặc để host nạp bản implementation sai.

## 1. Defining loader khác initiating loader
Một plugin có thể gọi `loadClass("com.acme.api.Greeter")` nhưng nhận chính `Class<?>` do parent định nghĩa. Loader gọi API là **initiating loader**, còn `Greeter.class.getClassLoader()` cho biết **defining loader**. Nếu child tự định nghĩa bản `Greeter` thứ hai, JVM nhận diện đó là kiểu khác, dù binary name và bytes giống nhau.

```text
Host loader defines com.acme.api.Greeter  ──┐
                                           ├── Host và plugin dùng chung Class<?> nếu delegate
Plugin loader delegates shared API ────────┘

Plugin loader defines duplicate Greeter  ───── Kiểu khác với bản host
```

Hãy xác nhận `apiFromPlugin == apiFromHost` thay vì chỉ so chuỗi `getName()`. Điều này phân biệt **ràng buộc kiến trúc** cần shared identity với quy tắc thực thi của JVM về namespace được bảo vệ như `java.*` ở phần tiếp theo.

## 2. Tại sao phải ưu tiên loader nền tảng?

Java có các built-in class loader, thường được mô tả theo vai trò:

| Loader | Vai trò chung |
| --- | --- |
| **Bootstrap** | Cơ chế nạp các lớp nền tảng cốt lõi, thường thấy `String.class.getClassLoader() == null` trên API. |
| **Platform** | Nạp những class/module nền tảng được gán cho platform loader của runtime. |
| **Application/system** | Nạp nhiều class ứng dụng, classpath và module ứng dụng tùy cấu hình. |
| **Custom/plugin** | Có thể nạp implementation và thư viện cô lập, thường có parent là loader host/shared API. |

Từ Java 9, lớp nền tảng nằm trong **runtime image theo module**, không phải một `rt.jar` cũ. Phân bổ class/module cho bootstrap/platform/application **không có nghĩa mọi class có tiền tố `javax.`, `jdk.` hoặc mọi module đều được bootstrap nạp**. Vì thế, không nên xây danh sách “mọi `javax.*` là lõi Java” mà không xét **module, ownership, runtime và dependency thực tế**: một số API `javax.*` do JDK cung cấp, nhưng tên `javax.*` khác có thể đến từ thư viện bên ngoài.

### Điều gì thực sự bị cấm ở mức API?

Một class loader tùy chỉnh không được gọi `defineClass` theo cách định nghĩa các class có binary name trong **`java.*`**. API `ClassLoader#defineClass` quy định `SecurityException` cho trường hợp cố định nghĩa class thuộc package bắt đầu bằng `java.` từ loader không được phép. Đây là ràng buộc của Java runtime, **khác** với một convention parent-first do đội phát triển tự tạo.

Ngược lại, Java **không có quy tắc phổ quát** rằng mọi tên `com.company.api.*` hay mọi tên `javax.*` bắt buộc phải được parent định nghĩa. Nhà thiết kế loader phải xác định đúng các API contract cần chia sẻ và bắt buộc delegation cho chúng.

**Không coi việc cấm định nghĩa `java.*` là cơ chế sandbox đầy đủ.** Class loader không tự cung cấp một ranh giới bảo mật toàn diện cho code không tin cậy; còn phải xét module access, quyền và cơ chế isolation của hệ thống.

## 3. API dùng chung: quan trọng hơn việc class “load được”

Ví dụ host và plugin giao tiếp qua:

~~~java
package com.acme.api;
public interface Greeter {
    String greet();
}
~~~

Đoạn này là **fragment hợp đồng**, có thể biên dịch nếu lưu trong tệp `Greeter.java` thuộc package đúng.

Nếu mỗi plugin chứa bản copy của `Greeter.class` và dùng child-first cho cả `com.acme.api.*`:

~~~text
HostLoader
└── com.acme.api.Greeter (Greeter-H)
                 |
                 | host mong object implements Greeter-H
                 v
PluginLoader
├── com.acme.api.Greeter (Greeter-P)       <-- định nghĩa lại
└── com.acme.impl.GreeterImpl implements Greeter-P

Greeter-H != Greeter-P
hostGreeterClass.isInstance(pluginObject) == false
~~~

Hệ quả có thể gồm:

- Host ép kiểu `GreeterImpl` sang `Greeter-H` và nhận `ClassCastException`.
- `ServiceLoader` tìm thấy provider nhưng kết luận provider không phải subtype của service type, gây `ServiceConfigurationError`.
- Một số chữ ký phương thức giữa các class do loader khác nhau định nghĩa bị vi phạm loader constraint, dẫn tới `LinkageError` ở giai đoạn linking.
- Generic erasure/reflective invocation có thể che sai sót đến khi cast hoặc phương thức được gọi.

**Chính sách đúng:** `com.acme.api.*` phải được tải qua **một loader chung ổn định** mà cả host và plugin thực sự nhìn thấy. Các lớp implementation `com.acme.impl.*` hoặc `plugin.impl.*` có thể được plugin loader nạp theo child-first khi thật sự cần cô lập.

### “API chung” gồm những loại kiểu nào?

Không chỉ interface chính. Hãy xét tất cả class mà các phía **truyền trực tiếp qua boundary**:

- API interface và abstract base class.
- DTO, request/response, enum, exception type trong method signatures.
- Callback, event/listener interface, service/provider contract.
- Annotation hoặc marker type mà framework/host đọc theo `Class<?>` identity.
- Kiểu trong parameter và return type của method, bao gồm các tham chiếu còn được runtime kiểm tra.

Một dependency “chỉ là internal implementation” có thể vẫn cần riêng nếu plugin phụ thuộc phiên bản khác; ngược lại, một DTO vô tình bundle trong plugin mà host cũng dùng có thể phá contract. Vì vậy, hãy xác định **ranh giới chia sẻ theo kiến trúc**, không chỉ dựa vào tên package có chữ `api`.

## 4. Parent-first cho API, child-first cho implementation: chính sách chọn lọc

Một chính sách thường dùng:

| Namespace / loại | Hướng tìm đề xuất | Lý do |
| --- | --- | --- |
| `java.*` và class/module nền tảng của runtime | Ưu tiên runtime/parent; không tự định nghĩa lại class cốt lõi | Tránh vi phạm bảo vệ namespace và phá runtime assumptions. |
| `com.acme.api.*` do host sở hữu | **Parent-first bắt buộc theo thiết kế** | Host/plugin phải nhìn cùng một định nghĩa `Class<?>`. |
| `plugin.impl.*` do plugin sở hữu | **Child-first có chọn lọc** | Host có thể có bản khác; cần dùng implementation của plugin hiện tại. |
| Thư viện implementation riêng của plugin | Child-first khi có nhu cầu isolation rõ ràng | Cho phép dependency version khác mà không làm mất hợp đồng chung. |
| Các package không được plugin cho phép override | Parent-first hoặc chính sách rõ theo ownership | Tránh nạp nhầm class ngoài phạm vi plugin. |

Không nên triển khai đơn giản theo kiểu “mọi thứ không phải `java.*` đều child-first” vì sẽ nhân bản API chia sẻ. Ngược lại, “mọi thứ parent-first” có thể khiến host version của một implementation được dùng thay vì bản child mà plugin cần.

Đặc tả JVM không áp đặt child-first/parent-first duy nhất cho mọi custom loader. **Bất biến cần duy trì là những kiểu phải giao tiếp chung được định nghĩa chung, và những lớp private được cô lập đúng chủ đích.**

## 5. Thực hành Java 17: loader an toàn và loader tạo bản sao API

Ví dụ độc lập này **tự biên dịch** một API interface cho host và một bản sao interface cùng implementation cho plugin, sau đó thử hai chính sách:

- **Safe loader:** child-first riêng cho `plugin.impl.*`, parent-first cho `api.shared.*` và các tên còn lại.
- **Unsafe loader:** child-first cho `plugin.impl.*` **và** `api.shared.*`, tạo định nghĩa trùng của interface contract.

Nhờ biên dịch nguồn giống nhau, phép thử chứng minh rằng **bytecode giống nhau không thay thế việc chia sẻ defining loader**.

Tạo một tệp **`DelegationBoundaryDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DelegationBoundaryDemo {
    private static final String API = "api.shared.Greeter";
    private static final String IMPL = "plugin.impl.GreeterImpl";

    static final class PluginLoader extends URLClassLoader {
        private final boolean shareApi;

        PluginLoader(URL[] urls, ClassLoader parent, boolean shareApi) {
            super(urls, parent);
            this.shareApi = shareApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            boolean pluginImplementation = name.startsWith("plugin.impl.");
            boolean privateApiCopy =
                    !shareApi && name.startsWith("api.shared.");

            if (!pluginImplementation && !privateApiCopy) {
                // JVM/platform + host API: parent-first.
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);

                if (type == null) {
                    try {
                        type = findClass(name);
                    } catch (ClassNotFoundException absent) {
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

    private static void write(Path file, String content)
            throws Exception {
        Files.createDirectories(file.getParent());
        Files.writeString(file, content);
    }

    private static void compile(JavaCompiler compiler, Path output,
                                Path... sources) {
        String[] args = new String[5 + sources.length];
        args[0] = "--release";
        args[1] = "17";
        args[2] = "-d";
        args[3] = output.toString();
        args[4] = "-g:none";

        for (int i = 0; i < sources.length; i++) {
            args[5 + i] = sources[i].toString();
        }

        int status = compiler.run(null, null, null, args);
        if (status != 0) {
            throw new IllegalStateException("Compiler failed: " + status);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        Path root = Files.createTempDirectory("delegation-boundary-");
        Path hostDir = Files.createDirectories(root.resolve("host"));
        Path childDir = Files.createDirectories(root.resolve("child"));

        Path hostApiSource =
                root.resolve("host-src/api/shared/Greeter.java");
        Path childApiSource =
                root.resolve("child-src/api/shared/Greeter.java");
        Path childImplSource =
                root.resolve("child-src/plugin/impl/GreeterImpl.java");

        String apiSource =
                "package api.shared; "
                + "public interface Greeter { String greet(); }";

        write(hostApiSource, apiSource);
        write(childApiSource, apiSource);
        write(childImplSource,
                "package plugin.impl; "
                + "public final class GreeterImpl "
                + "implements api.shared.Greeter { "
                + "public GreeterImpl() {} "
                + "public String greet() { return \"hello-plugin\"; } "
                + "}");

        compile(compiler, hostDir, hostApiSource);
        compile(compiler, childDir, childApiSource, childImplSource);

        try (URLClassLoader host = new URLClassLoader(
                    new URL[] { hostDir.toUri().toURL() }, null);
             PluginLoader safe = new PluginLoader(
                    new URL[] { childDir.toUri().toURL() }, host, true);
             PluginLoader unsafe = new PluginLoader(
                    new URL[] { childDir.toUri().toURL() }, host, false)) {

            Class<?> hostApi = host.loadClass(API);

            Object good =
                    safe.loadClass(IMPL).getDeclaredConstructor().newInstance();

            System.out.println("Safe API shared: "
                    + (safe.loadClass(API) == hostApi));
            System.out.println("Safe implementation local: "
                    + (good.getClass().getClassLoader() == safe));
            System.out.println("Safe implements host API: "
                    + hostApi.isInstance(good));
            System.out.println("Safe greeting: "
                    + hostApi.getMethod("greet").invoke(good));

            Object bad = unsafe.loadClass(IMPL)
                    .getDeclaredConstructor().newInstance();

            System.out.println("Unsafe API duplicated: "
                    + (unsafe.loadClass(API) != hostApi));
            System.out.println("Unsafe implements host API: "
                    + hostApi.isInstance(bad));

            try {
                hostApi.cast(bad);
                System.out.println("Unexpected cast success");
            } catch (ClassCastException e) {
                System.out.println("Unsafe cast: ClassCastException");
            }

            System.out.println("Platform String delegated: "
                    + (safe.loadClass("java.lang.String") == String.class
                       && unsafe.loadClass("java.lang.String") == String.class));
        }
    }
}
~~~

Biên dịch/chạy từ thư mục chứa tệp bằng **JDK 17+**:

~~~bash
javac --release 17 DelegationBoundaryDemo.java
java DelegationBoundaryDemo
~~~

**Stdout chính xác** với JDK tiêu chuẩn có module compiler `jdk.compiler`:

~~~text
Safe API shared: true
Safe implementation local: true
Safe implements host API: true
Safe greeting: hello-plugin
Unsafe API duplicated: true
Unsafe implements host API: false
Unsafe cast: ClassCastException
Platform String delegated: true
~~~

### Giải thích vì sao kết quả này quan trọng

1. Chương trình sinh **hai nguồn API có nội dung giống hệt** và biên dịch vào hai thư mục khác nhau, cùng với implementation ở thư mục child. Đây là trường hợp plugin có bản sao API dù host đã có.
2. `host` (một `URLClassLoader` có parent `null`) định nghĩa `api.shared.Greeter`; bootstrap loader vẫn có thể cung cấp các lớp nền tảng.
3. `safe` nhận class implementation từ `childDir` bằng child-first cho `plugin.impl.*` nhưng mọi yêu cầu `api.shared.*` dùng `super.loadClass`, qua đó **ủy quyền parent host**. `GreeterImpl` vì vậy implements **chính interface host**.
4. `unsafe` tự gọi `findClass` với cả `plugin.impl.*` và `api.shared.*`, khiến interface API bản child được **định nghĩa lại** bởi unsafe loader. Object này implements bản API riêng, không phải API host.
5. `hostApi.isInstance(good)` bằng `true`; `hostApi.isInstance(bad)` bằng `false` và `hostApi.cast(bad)` ném `ClassCastException` dù tên `api.shared.Greeter` giống nhau.
6. `safe.loadClass("java.lang.String")` và `unsafe.loadClass("java.lang.String")` vẫn qua đường `super.loadClass`, trả `String.class` của nền tảng chứ không cố tự định nghĩa một bản.
7. Hai loader `safe` và `unsafe` là hai đối tượng riêng, nên cùng tên implementation `plugin.impl.GreeterImpl` ở mỗi loader cũng là hai định nghĩa khác nhau. Điều đó **được phép** vì implementation là chi tiết riêng; điều không nên là làm mất identity của **contract chia sẻ**.
8. `getClassLoadingLock(name)`, `findLoadedClass(name)` và `resolveClass(type)` được dùng để tránh nạp trùng trong loader và tôn trọng cơ chế resolve. Mọi fallback sang `super.loadClass` vẫn tuân theo chính sách parent.
9. `try-with-resources` đóng các URLClassLoader sau ví dụ; không có lời hứa rằng đóng loader sẽ unload class ngay. Các tệp sinh trong thư mục tạm có thể được dọn sau khi chạy.

**Lưu ý giới hạn:** Loader trong ví dụ chỉ có hai prefix thử nghiệm, không phải một plugin sandbox hoặc class loader production hoàn chỉnh. Nó không xử lý dependency tree phức tạp, module layers, package sealing, metadata `ProtectionDomain`, xung đột resource hay lifecycle của server. Chính sách parent-first cho API là lựa chọn **bắt buộc bởi hợp đồng của ví dụ**, không phải quy tắc tự động cho mọi package có tên `api.shared`.

## 6. Thiết kế package policy không làm mất quyền kiểm soát

Một loader child-first sản xuất thực tế nên phân loại theo **ownership** thay vì theo tên lớp dự đoán tùy tiện:

~~~text
Request: com.acme.api.PaymentService
  → parent/shared loader (API chung)
  → không cho plugin định nghĩa lại

Request: plugin.payment.impl.CardProcessor
  → plugin loader trước (implementation riêng)
  → fallback có điều kiện nếu không có

Request: java.lang.String
  → delegation về runtime/parent
  → không tự cố định nghĩa

Request: some.shared.dto.PaymentRequest
  → loader định nghĩa DTO contract chung

Request: vendor.private.parser.ParserImpl
  → phiên bản plugin riêng nếu cần isolation
~~~

Mấu chốt là phân biệt **API được host và plugin cùng dùng** với **implementation/private dependency**. Nếu cùng một thư viện cần chia sẻ một phần và cô lập phần khác, cần thiết kế rõ type boundary, module graph, relocation hoặc công cụ đóng gói; không chỉ thêm vài điều kiện `startsWith` một cách tình cờ.

### Những API nào phải xuất hiện trên parent/shared loader?

- Interface/base class trong chữ ký host–plugin.
- DTO, enum, exception, annotation và listener type được trao đổi trực tiếp.
- Service/provider contract khi dùng `ServiceLoader` hoặc framework discovery.
- Kiểu được dùng làm khóa trong registry hoặc được kiểm tra bằng `instanceof` / `Class<?>` identity.
- Các loại payload do callback host nhận ở runtime.

Điều này không có nghĩa đưa toàn bộ ứng dụng lên parent loader. Chia sẻ **đúng phần hợp đồng**, giữ lại isolation cho implementation riêng và resource/dependency cần cô lập.

### Loader được chọn phải thực sự thấy API

Chọn `parent-first` không tự tạo class bị thiếu. Nếu parent **không có** API, đường fallback child có thể vẫn định nghĩa bản API riêng. Với contract bắt buộc, cần **đảm bảo parent sở hữu API** lúc triển khai và có thể chọn **fail fast** thay vì âm thầm fallback để tránh split identity.

Một loader production có thể áp dụng rule mạnh hơn:

~~~text
Nếu name thuộc shared API:
    chỉ cho parent tải; nếu parent không tìm thấy → báo lỗi ngay
Nếu name thuộc plugin implementation:
    tìm local trước, fallback có kiểm soát
Các namespace khác:
    dùng chính sách đã cấu hình
~~~

Đây là **pseudocode**, không phải lời gọi Java đầy đủ. Ví dụ runnable dùng `super.loadClass` cho API để minh họa delegation mặc định, nên nếu API hoàn toàn vắng mặt ở parent thì fallback của parent-first vẫn có thể tìm local. **Đừng coi điều đó đã thực thi fail-fast contract**.

## 7. Resource và service provider phải đồng bộ với chính sách lớp

Không chỉ class có vấn đề. Với plugin, `getResource`, `getResources` và `getResourceAsStream` có thể tìm file cấu hình, `META-INF/services/...` hay metadata trong JAR của parent/child.

- API contract nên được định nghĩa chung; metadata/provider discovery cần tìm đúng provider có thể triển khai **cùng interface API**.
- Nếu implementation được tải child-first nhưng `getResource` vẫn parent-first, plugin có thể nhận **cấu hình hoặc schema của phiên bản host**.
- `getResources` thường được dùng để **tổng hợp nhiều resource**, nhất là SPI; không nên tự thay bằng “chỉ lấy entry đầu” mà bỏ provider hợp lệ.
- `ServiceLoader.load(Service.class)` thường sử dụng **thread context class loader (TCCL)**; loader này phải nhìn thấy provider phù hợp với interface chung.
- Cần xem module encapsulation trên Java 9+, vì named module có quy tắc truy cập resource và service riêng.

**Đừng cố chữa lỗi interface bị định nghĩa trùng chỉ bằng đảo thứ tự resource.** Nếu provider thực sự implements bản interface khác defining loader, `ServiceConfigurationError` hay `ClassCastException` vẫn có thể xảy ra.

## 8. Module system (JPMS) có làm parent delegation hết cần thiết?

Không. Từ Java 9, module system thêm **module identity, readability, exports, opens, services** và khả năng xây module layer tùy biến; nó không biến mọi loại class cùng tên ở mọi loader thành một type chung.

Cần phân biệt:

| Khái niệm | Trả lời câu hỏi |
| --- | --- |
| **Class loader** | Ai định nghĩa `Class<?>` này? |
| **Module** | Class thuộc module nào, module đọc và truy cập package nào? |
| **Module layer** | Những module được giải quyết và tổ chức vào layer nào? |
| **Delegation policy** | Khi tìm class theo tên, loader ưu tiên parent hay local? |

Nếu plugin sống trong named module hoặc custom layer, phải xác định class loader được gán cho module và các cạnh `requires`/`exports`/`opens` phù hợp. **Cho phép đọc một module không tự hợp nhất hai định nghĩa class do hai loader khác nhau tạo**; ngược lại, một loader có thể bị module visibility/access chặn dù parent delegation tìm được class.

Trong Java hiện đại, cũng không nên suy rằng mọi module JDK được bootstrap loader định nghĩa; phân phối class giữa bootstrap/platform/application phụ thuộc runtime/module. Quy tắc bền vững là **đừng tự thay thế namespace nền tảng, giữ một định nghĩa API contract chia sẻ và tuân theo cơ chế module hợp lệ**.

## 9. Lỗi thường gặp và dấu hiệu chẩn đoán

| Triệu chứng | Căn nguyên khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `ClassCastException: A cannot be cast to A` | Hai định nghĩa class/interface cùng tên nhưng khác defining loader. | So `Class<?>` bằng `==`, `getClassLoader()` ở cả hai phía. |
| `ServiceConfigurationError: ... not a subtype` | Provider không thực sự implements **interface do consumer sử dụng**. | Xác minh service type, provider type và loader/TCCL của discovery. |
| `LinkageError` / loader constraint violation | Chữ ký/phụ thuộc qua boundary liên kết các kiểu có identity mâu thuẫn. | Xem thông báo đầy đủ, method descriptor và API duplicate. |
| `SecurityException` khi cố define `java.*` | Loader custom tự định nghĩa class trong namespace được bảo vệ. | Không override platform class; delegation về loader runtime. |
| `ClassNotFoundException` cho API chung | Parent không nhìn thấy contract hoặc cấu hình classpath/module path sai. | Đảm bảo một nguồn API trên shared loader và kiểm tra visibility. |
| `NoClassDefFoundError` khi sử dụng implementation | Dependency thiếu, không link được hoặc class đã khởi tạo lỗi trước đó. | Kiểm tra cause/stack trace và defining loader các dependency. |
| Resource plugin bị lấy từ host | Resource delegation vẫn parent-first dù implementation child-first. | Log `getResource` và `getResources`, thống nhất chính sách resource. |
| Sai hành vi sau hot redeploy | Object/cache/thread từ loader cũ được chuyển sang loader mới. | Dọn lifecycle, TCCL, registry và singleton chứa reference cũ. |

### Đo identity thay vì chỉ in tên

Fragment sau giả sử `pluginType` là `Class<?>` của implementation, `hostApi` là `Class<?>` của API và `pluginObject` là một instance:

~~~java
System.out.println("Impl loader: "
        + pluginType.getClassLoader());
System.out.println("Host API loader: "
        + hostApi.getClassLoader());
System.out.println("Implements host API: "
        + hostApi.isInstance(pluginObject));
System.out.println("Actual type: "
        + pluginObject.getClass().getName());
~~~

Đây là **fragment**, không phải chương trình độc lập; cần khai báo biến đúng. Hãy đối chiếu thêm:

~~~java
Class<?> apiSeenByPlugin =
        pluginType.getClassLoader()
                  .loadClass(hostApi.getName());

System.out.println("Same API Class: "
        + (apiSeenByPlugin == hostApi));
~~~

Nếu biểu thức cuối là `false`, đã có **split API identity**. Không nên chỉ so chuỗi `getName()` vì chúng có thể bằng nhau ngay cả khi Class khác.

## 10. Những anti-pattern cần tránh

### 10.1. Child-first mọi thứ ngoại trừ java.*

~~~java
// Pseudocode sai về mặt chính sách chia sẻ:
if (!name.startsWith("java.")) {
    return findClass(name);
}
return getParent().loadClass(name);
~~~

Ngoài vấn đề snippet không xử lý cache/fallback/resolve, quy tắc này **không bảo vệ shared API** như `com.acme.api.*`. Nó có thể định nghĩa lại contract và gây cast/linkage errors.

### 10.2. Chỉ cần “bytecode bằng nhau” là cùng kiểu

Không đúng. JVM dùng **binary name + defining loader**; các lớp được định nghĩa từ cùng một API JAR nhưng bởi hai loader khác nhau **không tự trở thành cùng kiểu**.

### 10.3. Parent-first toàn bộ mà không xét implementation riêng

Nếu host và plugin cùng có `vendor.parser.Parser` nhưng cần hai phiên bản khác nhau, parent-first có thể cho plugin dùng bản host ngoài ý muốn. Chỉ chia sẻ những contract cần chia sẻ; implementation có thể child-first theo policy cụ thể.

### 10.4. Dùng TCCL như công cụ sửa định danh kiểu

`Thread.currentThread().setContextClassLoader(loader)` thay đổi loader mà những API dựa trên TCCL sẽ dùng, **không thay class đã được loader khác định nghĩa**. Nó không tự làm `ClassCastException` biến mất; đồng thời nếu quên restore trong worker pool có thể giữ loader plugin cũ.

### 10.5. Mang cả API JAR trong plugin rồi tin parent-first là đủ

Nếu parent chứa API và plugin dùng parent-first, bản API trong plugin có thể không được định nghĩa khi runtime, nhưng vẫn tạo rủi ro cấu hình khi đổi loader policy hoặc packaging. Tốt nhất **không bundle lặp API contract** nếu không cần; kiểm tra dependency exclusion, scope và artefact phân phối.

### 10.6. Quên đồng bộ, cache và fallback khi override loadClass

Một implementation custom phải tránh định nghĩa trùng và race; xử lý `findLoadedClass`, `getClassLoadingLock`, `resolveClass` phù hợp và duy trì fallback parent chính xác. Không gọi `findClass` bừa với mọi class; không bắt `LinkageError` rồi tự “thử lại” bằng cách định nghĩa lớp khác cùng tên.

### 10.7. Nghĩ class loader là sandbox đầy đủ

Parent delegation và cấm định nghĩa `java.*` giúp bảo vệ một phần namespace và type consistency, **không phải mô hình cách ly bảo mật đầy đủ**. Với plugin không tin cậy, cần thiết kế kiểm soát quyền, hệ module, boundary tiến trình/container và kiểm tra nguồn code theo threat model thực.

## 11. Checklist thiết kế cho loader/plugin

1. **Liệt kê namespace nền tảng** mà plugin không được tự định nghĩa; giữ cơ chế runtime/parent thích hợp.
2. **Liệt kê API contract chung**, bao gồm interface, DTO, enum, exception, annotation, callback và SPI service type.
3. **Đảm bảo shared loader thật sự có những contract đó**; nên fail fast nếu thiếu API bắt buộc.
4. **Tách implementation/dependency riêng** của plugin; chỉ dùng child-first có chọn lọc khi có lý do rõ.
5. **Kiểm tra class identity** với `==` và `isInstance` khi object đi qua host–plugin boundary.
6. **Đảm bảo `loadClass` có cơ chế cache/lock/resolve/fallback đúng**, không định nghĩa lại class trong cùng loader.
7. **Xem chính sách resource** (`getResource`, `getResources`, `META-INF/services`) tương thích với class policy.
8. **Xem TCCL/thread pool/lifecycle**, đặc biệt khi framework tìm provider bằng TCCL hoặc có hot redeploy.
9. **Với named modules**, kiểm tra module readability, exports/opens và loader–module assignment.
10. **Viết test có duplicate API trong child** để xác nhận loader an toàn vẫn trả cùng `Class<?>` của parent. Tương tự, test rằng plugin implementation thật sự đến từ child và không bị host “nuốt mất”.

## 12. Tự kiểm tra

**Câu 1.** JVM có bắt mọi `com.example.api.*` phải parent-first không?

**Đáp án:** Không. Đây là **chính sách ứng dụng** cần thực thi nếu các class đó là hợp đồng dùng chung. `java.*` lại có quy tắc bảo vệ namespace đặc biệt khi loader tùy chỉnh dùng `defineClass`.

**Câu 2.** Plugin và host cùng đọc một JAR chứa interface `Greeter` nhưng mỗi bên tự định nghĩa qua loader riêng. Hai `Greeter` có cùng identity không?

**Đáp án:** Không. Dù cùng binary name và bytes, defining loader khác nhau nên là hai kiểu.

**Câu 3.** Vì sao plugin có thể child-first với `plugin.impl.*` nhưng phải parent-first với `api.shared.*`?

**Đáp án:** Implementation là chi tiết riêng cần cô lập; API contract là loại kiểu mà host/plugin phải cùng nhìn thấy để truyền object và cast an toàn.

**Câu 4.** Hai child loader có cùng parent thì tự bảo đảm API cùng một kiểu chưa?

**Đáp án:** Chưa. Parent phải **thực sự định nghĩa/cung cấp API**; nếu thiếu và mỗi child fallback tự định nghĩa, identity vẫn khác. Với contract bắt buộc nên kiểm tra/fail fast.

**Câu 5.** Chỉ set TCCL sang host loader có giải quyết được provider implements interface trùng tên nhưng khác defining loader không?

**Đáp án:** Không. TCCL ảnh hưởng đường tìm lớp/resource của các API sử dụng nó, nhưng không đổi identity của class đã được định nghĩa.

**Câu 6.** Kiểu `java.lang.String` trong chương trình Java hiện đại có nên được loader plugin định nghĩa lại không?

**Đáp án:** Không. Dùng class nền tảng do runtime cung cấp; cố định nghĩa `java.*` bằng custom ClassLoader thông thường vi phạm quy tắc bảo vệ package.

## Ghi nhớ

**Ủy quyền cho lớp nền tảng** bảo đảm plugin không tự thay thế các kiểu mà runtime quản lý. **Ủy quyền cho API contract dùng chung** bảo đảm host và plugin sử dụng **cùng một định nghĩa class/interface**, không chỉ cùng tên. Chiến lược thường phù hợp là **parent-first đối với platform + shared API**, **child-first có giới hạn đối với implementation riêng**. Với API contract quan trọng, parent phải thực sự sở hữu class đó; nếu không, hãy báo lỗi cấu hình thay vì âm thầm tạo bản sao. Khi debug, xác nhận bằng `Class<?> ==`, `getClassLoader()` và `isInstance(...)`.

**Tài liệu chuẩn:**

- Java SE 17 API, `ClassLoader` (delegation, `loadClass`, `defineClass`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- *Java Virtual Machine Specification* §5.3, class identity/creation: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Language Specification* §12.2, loading: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
