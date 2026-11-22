# Kiến thức cần có và thứ tự học các cơ chế mở rộng của Java

## 1. Hiểu đúng mục tiêu: “mở rộng lúc chạy” là gì?

Một ứng dụng Java có khả năng mở rộng (runtime extensibility) khi nó có **điểm mở rộng được thiết kế trước** để tìm, nạp, khởi tạo hoặc kết hợp thêm hành vi mà không phải sửa logic lõi cho từng biến thể. “Động” có nhiều mức: chọn sẵn một implementation từ cấu hình; phát hiện provider trong JAR; tạo lời gọi hoặc proxy lúc chạy; nạp mã qua class loader riêng; thậm chí can thiệp bytecode bằng Java agent. Không phải bài toán nào cũng cần cấp độ mạnh nhất.

Hãy luôn tách năm câu hỏi:

1. **Hợp đồng (contract):** Thành phần mở rộng phải implement interface/API nào, nhận dữ liệu gì, trả kết quả gì?
2. **Khám phá (discovery):** Ứng dụng biết implementation nào tồn tại bằng cấu hình, registry, `ServiceLoader` hay quét metadata?
3. **Nạp và liên kết (loading/linking):** JVM nhìn thấy class/JAR/module qua class path, module path hoặc `ClassLoader` nào?
4. **Kích hoạt và điều phối (invocation/lifecycle):** Ai tạo đối tượng, gọi phương thức, quản lý dependency, cấu hình, lỗi và dừng plugin?
5. **Cách ly và vận hành (isolation/operations):** Version, quyền truy cập, tài nguyên, log, độ tin cậy, cập nhật và giải phóng class loader được kiểm soát ra sao?

Ví dụ, một hệ thống xuất báo cáo có `ReportExporter` và các implementation `CsvExporter`/`JsonExporter`. Nếu các loại xuất đã biết khi biên dịch, chọn bằng constructor injection hoặc factory là đủ. Nếu muốn bổ sung JAR nhà cung cấp mới vào bản phân phối, hãy bắt đầu với SPI/`ServiceLoader`. Chỉ cân nhắc loader riêng khi thật sự cần nạp JAR ở đường dẫn tùy biến hoặc cách ly phiên bản; chỉ dùng instrumentation khi cần quan sát/chỉnh hành vi bytecode mà API thông thường không cho phép.

## 2. Kiến thức nền phải có trước

| Nền tảng | Cần nắm chắc | Vì sao quan trọng |
| --- | --- | --- |
| Java Core và OOP | `interface`, `abstract class`, overriding, polymorphism, generics, exception, visibility, `equals`/`hashCode` | Xây hợp đồng extension ổn định, xử lý lỗi khi plugin chạy |
| Thiết kế API | Dependency inversion, composition, immutable DTO, backward compatibility, versioning | Tránh để plugin phụ thuộc vào implementation nội bộ |
| Biên dịch và đóng gói | `javac`, `java`, `jar`, package, JAR manifest, resources, Maven/Gradle ở mức cơ bản | Hiểu vì sao class/provider hiện diện hoặc không được phát hiện |
| JVM căn bản | Bytecode, `Class<?>`, class loading → linking → initialization, heap/GC, exception stack trace | Giải thích hiệu ứng khởi tạo class, linkage và khả năng unload |
| Phân phối mã | Class path, module path, dependencies, JAR conflicts, semantic versioning | Phân biệt lỗi không tìm thấy class với lỗi không tương thích binary |
| Công cụ kiểm tra | Unit/integration test, `jar tf`, `javap`, `jdeps`, log | Xác thực cả lúc plugin có và vắng mặt |

**Điểm kiểm tra đầu vào:** tự tạo một interface, hai implementation, factory chọn implementation theo tham số; đóng gói ứng dụng thành JAR và chạy bằng Java 17+. Nếu chưa hiểu `-cp`, resource trong JAR, public/package-private và khác biệt giữa compile-time type với runtime object, nên luyện những phần này trước.

## 3. Thứ tự học khuyến nghị (từ ít rủi ro đến chuyên sâu)

| Chặng | Nội dung chính | Bài thực hành tối thiểu | Khi nào đủ để chuyển chặng |
| --- | --- | --- | --- |
| **0. Nền tảng và hợp đồng** | Java 17+, interface, class path/JAR, DIP, semantic versioning | Ứng dụng có hai implementation, thay bằng cấu hình | Đổi implementation mà không sửa business logic |
| **1. Mô hình lớp của JVM** | `Class`, class loader, delegation, resource, load/link/init | In class loader của từng class; thử `Class.forName` | Giải thích được `ClassNotFoundException` và initialization |
| **2. SPI/`ServiceLoader`** | Service contract, provider, `META-INF/services`, lazy discovery, cache | Nạp một provider từ class path, thêm provider thứ hai | Thêm JAR/provider, host không cần sửa mã |
| **3. JPMS** | `module-info.java`, `requires`/`exports`/`opens`, `uses`/`provides` | Chuyển ví dụ SPI sang module path | Giải thích được lỗi access và module resolution |
| **4. Reflection/annotations** | `Class`/`Method`/`Constructor`, annotation retention, kiểm tra type/access | Đọc annotation của plugin và gọi phương thức được phép | Không dựa vào private API hay tên class tùy tiện |
| **5. Proxy và lời gọi động** | `Proxy`/`InvocationHandler`, decorator, `MethodHandle` căn bản | Thêm logging/validation quanh interface | Phân biệt proxy với provider discovery và instrumentation |
| **6. Loader riêng và kiến trúc plugin** | `URLClassLoader`, TCCL, identity, resource cleanup, `ModuleLayer` khi cần | Nạp provider từ plugin JAR ngoài class path | Quản lý được lifecycle, version và lỗi ép kiểu |
| **7. Bytecode/agent (nhánh nâng cao)** | `java.lang.instrument`, `premain`, `ClassFileTransformer`, giới hạn retransformation | Agent ghi log class được nạp trong ứng dụng thử nghiệm | Biết rõ khi nào agent có lợi và rủi ro triển khai |

Đây là **thứ tự theo dependency kiến thức**, không phải yêu cầu dự án nào cũng hoàn thành tất cả. Đa số hệ thống mở rộng nghiệp vụ nên dừng ở chặng 2–5; chặng 6–7 dành cho plugin platform, framework, công cụ quan sát, profiling hoặc công cụ phân tích.

## 4. Chặng 1 — Class, class loading và vòng đời khởi tạo

### 4.1. Phân biệt ba việc thường bị gộp nhầm

- **Loading:** class loader tìm bytecode và định nghĩa đối tượng `Class`; có thể ủy quyền cho loader cha.
- **Linking:** JVM xác minh bytecode, chuẩn bị cấu trúc và giải quyết symbolic references theo thời điểm JVM chọn.
- **Initialization:** chạy các initializer tĩnh và khởi tạo static field theo quy tắc ngôn ngữ.

`Class.forName("demo.Plugin")` theo overload một tham số mặc định yêu cầu initialization; `ClassLoader.loadClass("demo.Plugin")` thông thường chỉ nạp, chưa buộc khởi tạo. Khi cần điều khiển, dùng `Class.forName(name, initialize, loader)`. Không dùng khởi tạo class như một “plugin registry” trá hình qua static block: khó dự đoán side effect và kiểm thử.

Một lớp Java được nhận diện bởi **(binary name, defining class loader)**. Hai loader khác nhau có thể định nghĩa hai class đều tên `demo.Plugin` nhưng JVM coi là **hai kiểu khác nhau**. Đây là nguyên nhân của `ClassCastException` tưởng như vô lý trong hệ plugin.

### 4.2. Hiểu delegation trước khi viết custom loader

Loader thông dụng ưu tiên hỏi parent trước khi tự tìm class. Bootstrap, platform và application/system class loader có vai trò khác nhau; không nên giả định implementation class loader luôn có tên cụ thể. Class loader cũng tìm **resource**, chẳng hạn cấu hình provider tại `META-INF/services/...`.

Quan sát trên Java 17+:

~~~java
public class LoaderMap {
    public static void main(String[] args) {
        System.out.println(String.class.getClassLoader()); // Thường là null: bootstrap
        System.out.println(LoaderMap.class.getClassLoader());
        System.out.println(Thread.currentThread().getContextClassLoader());
    }
}
~~~

Lưu thành `LoaderMap.java`, chạy `javac LoaderMap.java` rồi `java LoaderMap`. Dòng đầu thường in `null` do class của nền tảng được bootstrap loader định nghĩa; **hai dòng sau phụ thuộc môi trường**, nên không gán stdout cố định. Context class loader của thread (TCCL) quan trọng với framework/`ServiceLoader` vì mã thư viện có thể cần thấy provider của ứng dụng.

**Cần phân biệt lỗi:** `ClassNotFoundException` thường xảy ra khi lookup bằng tên không tìm được class; `NoClassDefFoundError` có thể xuất hiện khi JVM cần class nhưng không định nghĩa/khởi tạo được (kể cả class từng lỗi initialization); `NoSuchMethodError` thường gợi ý binary incompatibility giữa bản compile và runtime. Đừng xử lý tất cả bằng cách “thêm JAR” mà chưa đọc cause và class path thực tế.

## 5. Chặng 2 — Thiết kế extension point và Service Provider Interface

`ServiceLoader` là bước đầu tiên nên dùng khi cần plugin có sẵn trên class path hoặc module path. Nó phát hiện các provider của một **service type** thông qua metadata chuẩn, rồi tạo instance khi duyệt (lazy). Hợp đồng thường là interface nhỏ, ổn định, tài liệu hóa input/output và exception.

### 5.1. Ví dụ SPI chạy được với class path (Java 17+)

Tạo cấu trúc:

~~~text
src/
├── demo/
│   ├── Greeting.java
│   ├── VietnameseGreeting.java
│   └── Main.java
└── META-INF/
    └── services/
        └── demo.Greeting
~~~

`src/demo/Greeting.java`:

~~~java
package demo;

public interface Greeting {
    String greet(String name);
}
~~~

`src/demo/VietnameseGreeting.java`:

~~~java
package demo;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {}

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

`src/demo/Main.java`:

~~~java
package demo;

import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
        for (Greeting provider : loader) {
            System.out.println(provider.greet("An"));
        }
    }
}
~~~

Nội dung **nguyên văn** của resource `src/META-INF/services/demo.Greeting` là một dòng tên lớp provider đầy đủ:

~~~text
demo.VietnameseGreeting
~~~

Chạy trong thư mục chứa `src` (PowerShell, máy có JDK 17+):

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/Greeting.java src/demo/VietnameseGreeting.java src/demo/Main.java
Copy-Item -Recurse -Force src/META-INF out/META-INF
java -cp out demo.Main
~~~

Stdout của ứng dụng:

~~~text
Xin chào, An
~~~

Resource `META-INF/services/demo.Greeting` phải nằm trong **class path runtime** (ở đây là `out`), không chỉ tồn tại trong source tree. Trong JAR thực tế, kiểm tra `jar tf plugin.jar`. Muốn có nhiều provider, thêm tên lớp vào file provider hoặc đóng gói provider trong JAR độc lập; host chỉ phụ thuộc `Greeting`. Khi triển khai thật, thường tách `api.jar`, `host.jar` và các `provider.jar`.

### 5.2. Cần hiểu đúng những giới hạn

- `ServiceLoader.load(ServiceType.class)` mặc định sử dụng context class loader của thread đối với phương thức overload thông dụng này; cũng có overload nhận class loader để chọn phạm vi tìm provider. Với named modules, dịch vụ có thể được khai báo trực tiếp trong module descriptor.
- Provider được phát hiện qua tên và metadata nhưng việc duyệt/khởi tạo có thể phát sinh `ServiceConfigurationError` do tên sai, class không truy cập được, cấu hình hỏng, dependency thiếu hoặc constructor/provider method không hợp lệ. Lỗi khi chạy code của provider còn có thể là lỗi nghiệp vụ khác.
- `ServiceLoader` có cache provider đã nạp; `reload()` xóa cache của instance loader để duyệt lại. Nó **không tự tải JAR mới vào class loader cũ**, không hủy các đối tượng plugin đang được dùng, và không tạo cơ chế hot-reload hoàn chỉnh.
- Không dựa vào thứ tự provider như quy tắc ưu tiên kinh doanh. Nếu có nhiều implementation, định nghĩa rõ `id`, capability, priority, trùng ID, chính sách chọn và thông báo lỗi.
- Khi provider cần cấu hình, database connection, secret hoặc dependency lớn, có thể dùng provider factory/adapter hoặc container DI; `ServiceLoader` chỉ làm **discovery/instantiation theo quy tắc SPI**, không thay cho dependency injection container và lifecycle manager.

**Bài tập:** thêm `EnglishGreeting`, để cả hai provider được nhận diện. Sau đó định nghĩa `String id()`, chọn provider theo `id` và kiểm thử trường hợp thiếu hoặc trùng provider. Làm bài này trước khi chuyển sang reflection tự động.

## 6. Chặng 3 — Java Platform Module System (JPMS)

JPMS (Java 9+) bổ sung mô tả dependency và encapsulation ở cấp module. Cần học sau class path/SPI để nhận ra khác biệt giữa **lớp tồn tại** và **module có đọc/truy cập được lớp**.

| Từ khóa trong `module-info.java` | Ý nghĩa thiết yếu |
| --- | --- |
| `requires x;` | Module hiện tại phụ thuộc và đọc module `x` |
| `exports pkg;` | Cho module khác truy cập public types trong package `pkg` theo quy tắc module |
| `exports pkg to x;` | Chỉ xuất public API của package tới các module chỉ định |
| `opens pkg;` / `opens pkg to x;` | Cho phép deep reflection theo phạm vi khai báo; không tương đương `exports` |
| `uses pkg.Service;` | Khai báo module sử dụng service |
| `provides pkg.Service with impl.Provider;` | Đăng ký provider trong named module |

Ví dụ **ba file descriptor mang tính minh họa**, thuộc ba module độc lập (không đặt chung một file):

~~~java
// module-info.java của greeting.api
module greeting.api {
    exports greeting.spi;
}

// module-info.java của greeting.host
module greeting.host {
    requires greeting.api;
    uses greeting.spi.Greeting;
}

// module-info.java của greeting.provider
module greeting.provider {
    requires greeting.api;
    provides greeting.spi.Greeting with greeting.impl.VietnameseGreeting;
}
~~~

Provider implementation phải thỏa contract/điều kiện mà `ServiceLoader` yêu cầu trong module. Nếu dùng module path, điều quan trọng còn là **module có được resolve vào layer đang sử dụng hay không**; khi cần, kiểm tra cấu hình khởi chạy/`--add-modules` hoặc tạo layer phù hợp. Không giả định chuyển JAR lên module path là mọi provider tự có mặt.

`exports` cho phép truy cập public API; `opens` phục vụ truy cập reflective sâu vào non-public members. Với JDK 17+, mã dựa vào reflection vào internals bị strong encapsulation chặn theo mặc định. `--add-opens` là công cụ tương thích/diagnostic theo phạm vi, không phải thiết kế API lý tưởng. Một named module không đồng nghĩa với sandbox bảo mật cho plugin.

**Bài tập:** chạy ví dụ SPI với ba module, cho host chỉ thấy package API; cố gắng reflect vào trường private của một class ở module khác rồi giải thích nguyên nhân access failure; sửa bằng khai báo `opens` hẹp khi đó là nhu cầu được cho phép.

## 7. Chặng 4 — Reflection và annotations: đọc metadata, gọi hành vi đã cho phép

Reflection trả lời câu hỏi “class này có constructor/method/annotation nào?” thông qua `Class`, `Constructor`, `Method`, `Field` và `Annotation`. Nó hợp với framework binding, serialization, dependency injection hoặc xây một registry có metadata. Nên **ưu tiên interface gọi trực tiếp** khi hợp đồng đã biết lúc biên dịch; reflection chỉ thêm giá trị khi type/member được xác định động.

Ví dụ tự chạy (Java 17+), file `ReflectionDemo.java`:

~~~java
public class ReflectionDemo {
    public static class Greeting {
        public Greeting() {}

        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName("ReflectionDemo$Greeting");
        Object instance = type.getDeclaredConstructor().newInstance();
        Object result = type.getMethod("greet", String.class).invoke(instance, "An");
        System.out.println(result);
    }
}
~~~

Chạy `javac ReflectionDemo.java` rồi `java ReflectionDemo`; stdout:

~~~text
Xin chào, An
~~~

Ký hiệu `$` trong binary name biểu thị nested class ở ví dụ; nếu chuyển sang package riêng, dùng tên fully qualified phù hợp. `getMethod` tìm public method; `getDeclaredMethod` chỉ xem method khai báo trực tiếp và **không tự cấp quyền truy cập private**.

### Annotation cần học cùng reflection

- Tạo annotation với `@Retention(RetentionPolicy.RUNTIME)` nếu muốn đọc lúc chạy; `SOURCE` hoặc `CLASS` không đồng nghĩa với runtime visibility.
- Chọn `@Target` phù hợp (TYPE, METHOD, FIELD...). Khi thiết kế plugin registry, annotation chỉ là **metadata**, còn phải có cơ chế khám phá class, xác thực kiểu, khởi tạo và quản lý lifecycle.
- Không quét mọi package hoặc mọi JAR theo cảm tính. Quét class path/module path phụ thuộc packaging, scope, hiệu năng và môi trường đóng gói; hãy chọn một thư viện/framework đã kiểm chứng khi thực sự cần scanning.

**Lỗi thường gặp:** ép kiểu sai; gọi method với kiểu tham số không khớp; constructor không truy cập được; exception của method bị bọc trong `InvocationTargetException`; `InaccessibleObjectException` vì module không mở package; việc đổi tên class/method làm string-based lookup gãy khi refactor. Luôn giữ error context và giới hạn danh sách type được phép nạp.

## 8. Chặng 5 — Dynamic proxy, decorator và MethodHandle

### 8.1. Chọn proxy để bọc hành vi của interface

JDK dynamic proxy tạo một object implement một hay nhiều **interface**. `InvocationHandler` nhận method/arguments và quyết định chuyển tiếp, thêm logging, metric, transaction boundary hoặc validation. Nó **không tìm provider**, không phải class loader và không sửa bytecode gốc của class đích. Nếu chỉ cần bọc một component cụ thể bằng mã tĩnh, decorator thường dễ hiểu và dễ debug hơn.

Ví dụ độc lập `ProxyDemo.java` trên Java 17+:

~~~java
import java.lang.reflect.Proxy;

public class ProxyDemo {
    public interface Greeting {
        String greet(String name);
    }

    static final class RealGreeting implements Greeting {
        @Override
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args) {
        Greeting target = new RealGreeting();
        Greeting proxy = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[] { Greeting.class },
                (self, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return method.invoke(target, arguments);
                    }
                    System.out.println("Trước: " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } finally {
                        System.out.println("Sau: " + method.getName());
                    }
                });

        System.out.println(proxy.greet("An"));
    }
}
~~~

Lệnh: `javac ProxyDemo.java` và `java ProxyDemo`. Stdout chính xác:

~~~text
Trước: greet
Sau: greet
Xin chào, An
~~~

Ở production, cần xử lý method từ `Object` (như `equals`/`hashCode`/`toString`), default methods, exception unwrap (`InvocationTargetException`), null arguments, concurrent calls và giới hạn truy cập theo module. Việc handler tự gọi lại cùng proxy có thể gây đệ quy vô hạn. Với class không có interface, JDK `Proxy` không đủ; thư viện tạo subclass/bytecode có trade-off riêng về `final`, constructor, method và module access.

### 8.2. Học MethodHandle sau khi hiểu reflection

`MethodHandle` trong `java.lang.invoke` biểu diễn một target gọi method/field có dạng type rõ ràng (`MethodType`) và khả năng kết hợp/adapt lời gọi. `MethodHandles.Lookup` gắn với quyền truy cập của caller; không phải “vé vượt encapsulation”. `privateLookupIn` phải thỏa quy tắc module/`opens` khi đi qua ranh giới module.

Không cần học sâu `invokedynamic` hay `LambdaMetafactory` ngay từ đầu. Đây là nhánh phù hợp khi xây runtime/framework, code generation hoặc tối ưu cơ chế lời gọi động sau khi **đo bằng benchmark thích hợp**. Không khẳng định mặc định `MethodHandle` luôn nhanh hơn `Method.invoke` trong mọi tình huống; JIT, call-site shape và warmup có ảnh hưởng.

## 9. Chặng 6 — Plugin JAR ngoài class path, class loader riêng và isolation

Sau khi SPI hoạt động trong một bản phân phối cố định, bài toán mới thường là nạp thư viện từ `plugins/*.jar`, cho plugin phụ thuộc phiên bản khác nhau, bật/tắt plugin và giải phóng tài nguyên. Khi đó mới cân nhắc `URLClassLoader` (classpath-style plugin) hoặc `ModuleLayer` (plugin modular) cùng kiến trúc rõ ràng.

**Mô hình cơ bản:**

~~~text
Host application
    |
    +-- Parent / shared API loader --> plugin-api.jar (interface, DTO)
    |
    +-- Plugin loader A -----------> plugin-a.jar + dependencies A
    |
    +-- Plugin loader B -----------> plugin-b.jar + dependencies B
~~~

Giữ API giao tiếp chung ở class loader mà host và plugin cùng nhìn thấy. Plugin implementation có thể nằm trong loader con; nếu plugin đóng gói lại bản sao API và định nghĩa lại bằng loader khác, cast sang interface của host có thể thất bại dù full name trùng nhau.

Một **đoạn minh họa, không phải chương trình độc lập** cho trường hợp một JAR plugin đã tồn tại và API được chia sẻ:

~~~java
try (var loader = new java.net.URLClassLoader(
        new java.net.URL[] { pluginJar.toUri().toURL() },
        Greeting.class.getClassLoader())) {
    var services = java.util.ServiceLoader.load(Greeting.class, loader);
    for (Greeting provider : services) {
        provider.greet("An"); // Sử dụng bên trong phạm vi vòng đời loader
    }
}
~~~

Ở đây `pluginJar` là biến `Path` và `Greeting` là service API đã được định nghĩa ở ứng dụng; muốn ví dụ chạy cần cung cấp JAR hợp lệ cùng provider metadata. `URLClassLoader.close()` đóng tài nguyên/file đã mở, **không lập tức unload class hoặc hủy instance**. Muốn loader có khả năng được GC phải chấm dứt plugin, dừng thread/executor, bỏ listener/timer/registry/static cache, xử lý `Thread.contextClassLoader` và xóa mọi strong reference giữ loader/class/instance. Hot-reload là **vòng đời cả plugin/class loader**, không phải chỉ gọi `reload()`.

Chỉ viết child-first loading khi có lý do rõ ràng và hiểu package/API nào phải luôn do parent định nghĩa; custom delegation sai gây split package, duplicate types, `LinkageError` và lỗi khó gỡ. `ModuleLayer` giải quyết phạm vi/module resolution theo cơ chế JPMS, nhưng không tự biến plugin thành môi trường cách ly bảo mật hoặc quản lý lifecycle hoàn chỉnh.

### Thiết kế hợp đồng plugin thực tế

Một hệ plugin trưởng thành thường định nghĩa:

- **Identity/capability:** ID, tên, phiên bản API, tập chức năng hỗ trợ và chính sách khi trùng ID.
- **Lifecycle:** `discover → validate → configure → start → invoke → stop → release`; mỗi bước có trạng thái và lỗi rõ ràng.
- **Compatibility:** semantic versioning, API/DTO ổn định; thử binary compatibility giữa host và provider được compile từ bản cũ.
- **Resource ownership:** thread, socket, connection pool, file handle, shutdown hook, listener, TCCL; ai mở thì chịu trách nhiệm đóng.
- **Failure isolation:** timeout, circuit breaker hoặc quy tắc disable provider ở mức nghiệp vụ; một plugin lỗi không làm dừng tất cả nếu có thể phục hồi.
- **Trust:** chỉ nạp JAR từ nguồn tin cậy, kiểm soát phân phối/chữ ký/hash khi cần. **Class loader và JPMS không phải sandbox** để chạy mã độc hoặc không tin cậy trong cùng JVM.

## 10. Chặng 7 — Instrumentation và Java agent (học sau cùng)

`java.lang.instrument` cho agent quan sát/chuyển đổi bytecode lúc class được load hoặc theo năng lực mà JVM hỗ trợ. Dùng khi xây APM, profiler, coverage, tracing hoặc công cụ framework cần can thiệp nơi không có extension point bằng interface. Đây là giải pháp có ảnh hưởng rộng và khó chẩn đoán hơn SPI/proxy.

Các khái niệm cần học theo thứ tự:

1. **Class file/bytecode:** constant pool, method descriptor, verifier, stack frame; thử `javap -c -p SomeClass`.
2. **Khởi động agent:** JAR có manifest `Premain-Class`, class agent có `public static void premain(String, Instrumentation)`, chạy ứng dụng với `-javaagent:path/to/agent.jar`.
3. **Transformer:** `ClassFileTransformer` nhận class bytes theo lifecycle JVM; hiểu class loader context, filter package, idempotency và tránh tự instrument các class của agent.
4. **Redefine/retransform:** phân biệt `redefineClasses` và `retransformClasses`; support là **khả năng tùy chọn**, cần manifest/capability tương ứng và còn giới hạn JVM đối với thay đổi cấu trúc class.
5. **Thư viện bytecode:** cân nhắc Byte Buddy cho use case phổ biến; ASM/JVMS phù hợp khi thật sự cần can thiệp mức thấp và hiểu verifier.
6. **Vận hành:** overhead, thứ tự nhiều transformer/agent, startup failure, class loader leak, logging, chính sách triển khai, tương thích JDK.

Ví dụ **chữ ký minh họa, không chạy độc lập**:

~~~java
import java.lang.instrument.Instrumentation;

public final class ObservationAgent {
    public static void premain(String arguments, Instrumentation instrumentation) {
        System.out.println("Agent khởi động trước main");
        // Đăng ký ClassFileTransformer nếu có yêu cầu cụ thể.
    }
}
~~~

Để chạy phải đóng gói class này thành agent JAR, đặt `Premain-Class: ObservationAgent` trong manifest và truyền `-javaagent:...` vào JVM; chỉ viết method `premain` trong source chưa đủ. Không đồng nhất instrumentation với plugin business logic, không lạm dụng agent để “vá” API thiếu thiết kế.

## 11. Chọn cơ chế theo tình huống

| Nhu cầu thực tế | Lựa chọn bắt đầu | Khi nào cần nâng cấp |
| --- | --- | --- |
| Đổi chiến lược trong ứng dụng đã biết trước | Interface + DI/factory/strategy | Cần provider bên ngoài build → SPI |
| Nhà cung cấp phân phối implementation qua JAR | `ServiceLoader` + service API | Cần nạp JAR sau startup/cách ly dependencies → loader/layer |
| Đọc metadata/annotation hoặc gọi method theo cấu hình | Reflection có whitelist và validation | Cần lời gọi kết hợp/tối ưu đặc thù → `MethodHandle` |
| Gắn logging, metric, validation quanh interface | Decorator hoặc JDK dynamic proxy | Cần intercept class cụ thể → công cụ proxy bytecode với ràng buộc rõ |
| Nhiều plugin dùng thư viện phiên bản xung đột | Loader riêng + API chia sẻ + lifecycle | Plugin modular phức tạp → JPMS layers |
| Theo dõi method của mã không có extension point | Instrumentation/agent | Cần kiểm soát bytecode chi tiết → Byte Buddy/ASM |
| Khởi chạy mã **không tin cậy** | Tách process/container và kiểm soát quyền tại OS | Không dùng custom class loader/JPMS như hàng rào an toàn |

**Nguyên tắc chọn:** giải quyết ở tầng thấp nhất vẫn thỏa yêu cầu. API ổn định + discovery rõ ràng thường có lợi hơn reflection quét khắp class path; proxy quanh interface thường dễ kiểm thử hơn instrument bytecode; custom loader cần kế hoạch lifecycle trước khi triển khai.

## 12. Bài thực hành tích hợp theo từng mốc

### Lab A — Extension contract (chặng 0–1)

- Thiết kế `ReportExporter` với `String format()` và `byte[] export(Report input)`.
- Có `CsvExporter` và `TextExporter`; dùng factory chọn theo input; kiểm thử output, lỗi định dạng không hỗ trợ và chính sách exception.
- Quan sát class loader và package của hai implementation; đóng gói và chạy từ JAR.

**Hoàn thành khi:** host chỉ biết interface, đổi exporter không sửa logic xuất báo cáo; hiểu vị trí API và implementation.

### Lab B — Service discovery (chặng 2–3)

- Đóng gói service API, host, provider thành các phần riêng; đăng ký `META-INF/services`.
- Thêm provider thứ hai mà không sửa host. Khi provider bị thiếu, in thông báo rõ thay vì âm thầm cho output trống.
- Thử resource sai chính tả, provider không có constructor phù hợp, missing dependency và quan sát nguyên nhân.
- Chuyển sang JPMS `uses/provides`; kiểm tra sự khác nhau giữa class path và module path.

**Hoàn thành khi:** biết chính xác provider được discover từ đâu và lỗi vì sao.

### Lab C — Metadata và cross-cutting behavior (chặng 4–5)

- Tạo annotation runtime `@PluginInfo(id="csv")`; đọc từ class provider và validate ID.
- Chỉ gọi public API qua interface; thử phản ví dụ `setAccessible(true)` khi module không mở package.
- Bọc `ReportExporter` bằng JDK proxy, đo thời gian và ghi log mỗi lời gọi; bắt lỗi của provider và giữ nguyên cause.

**Hoàn thành khi:** phân biệt contract, metadata, discovery và interception là bốn trách nhiệm khác nhau.

### Lab D — Plugin platform nhỏ (chặng 6, tùy chọn)

- Host đọc đúng một JAR ở đường dẫn do người vận hành chỉ định; dùng loader riêng và `ServiceLoader.load(ServiceType.class, loader)`.
- Đảm bảo service API được chia sẻ đúng loader; kiểm thử plugin từ chối version API không tương thích.
- Tắt plugin: stop executor/listener, đóng tài nguyên, bỏ reference, đóng loader; xác minh bằng log/heap dump khi nghi ngờ leak.
- Thử plugin bị lỗi và trường hợp hai plugin cần dependency versions khác nhau; ghi rõ giới hạn thực tế của phương án đã chọn.

**Hoàn thành khi:** host báo được vòng đời, lỗi, phiên bản và nguồn JAR; không dựa vào restart tùy tiện để che lỗi quản lý tài nguyên.

### Lab E — Agent chỉ dành cho nhánh chuyên sâu (chặng 7)

- Viết agent log thời điểm `premain` chạy; xác nhận agent bắt đầu trước application `main`.
- Khi đã hiểu class file, thêm transformer chỉ quan sát class cụ thể và trả nguyên bytes; tiếp đó mới thử biến đổi an toàn qua thư viện đã kiểm chứng.
- Đo overhead, kiểm thử class loading và fallback khi agent bị tắt.

**Hoàn thành khi:** biết giải thích manifest, transformer lifecycle và vì sao agent yêu cầu kiểm thử rộng hơn plugin thông thường.

## 13. Lỗi thường gặp và cách chẩn đoán có hệ thống

| Triệu chứng | Hướng kiểm tra đầu tiên |
| --- | --- |
| `ServiceLoader` không thấy provider | Provider resource đúng `META-INF/services/<FQCN>` chưa; trong JAR có chưa; context loader/module layer đúng chưa; module đã resolve chưa |
| `ServiceConfigurationError` | Tên class, implements service, cách tạo provider/constructor, visibility, dependency và exception gốc |
| `ClassNotFoundException` | Binary name, class path/module path, loader đang dùng, JAR thực tế |
| `NoClassDefFoundError` / `NoSuchMethodError` | Dependency transitives, class initialization failure, version binary giữa compile/runtime |
| `ClassCastException` dù tên class giống nhau | So sánh `type.getClassLoader()` và loader của interface/shared API; xem plugin có đóng gói trùng API không |
| `InaccessibleObjectException` | `module-info.java`, `opens`, module nào thực hiện reflection; hạn chế workaround `--add-opens` |
| Mất bộ nhớ sau khi tắt plugin | Thread/TCCL, registry, static cache, listener, instance, references đến `Class` và loader |
| Agent không chạy | `-javaagent`, `Premain-Class`, đúng method signature, JAR và khả năng JVM |
| Chạy chậm hoặc lỗi khó trace | Đo độ trễ/khởi tạo, exception cause, scope discovery, thử không có proxy/agent, benchmark trước khi tối ưu |

Công cụ nên sử dụng đúng lúc: `jar tf file.jar` xem resource/class đóng gói; `javap -p -c ClassName` xem chữ ký/bytecode; `jdeps` kiểm tra dependency; `java --show-module-resolution ...` xem module graph; `java -Xlog:class+load=info ...` xem log class loading trên JVM hỗ trợ unified logging. Không mặc định coi tên output, thứ tự class loading hoặc thời điểm unload là ổn định giữa các môi trường.

## 14. Tiêu chí tự đánh giá và thứ tự ưu tiên khi áp dụng

Sau lộ trình, người học phải tự trả lời và chứng minh bằng chương trình nhỏ:

1. **Khi nào interface + DI đủ và khi nào cần SPI?** Biết chọn không phát sinh reflection hoặc class loader không cần thiết.
2. **`Class.forName` khác `ServiceLoader` ở điểm nào?** Một bên nạp class theo tên; bên kia khám phá provider đã đăng ký theo service contract.
3. **Vì sao plugin có class cùng tên vẫn không ép kiểu được?** Chỉ ra class identity gồm tên + defining loader.
4. **Vì sao `exports` không thay `opens`?** Nêu được khác nhau giữa public API access và deep reflection.
5. **Proxy có làm host phát hiện plugin không?** Không; proxy bọc/định tuyến lời gọi theo interface đã biết.
6. **`reload()` có “hot deploy” JAR mới không?** Không; phải giải quyết class loader và vòng đời plugin.
7. **Vì sao Java agent là bước cuối?** Nó can thiệp rộng vào runtime, có điều kiện capability/verification, rủi ro tương thích và overhead lớn hơn extension point thông thường.
8. **Làm sao thử độ tin cậy?** Test provider thiếu, provider hỏng, version lệch, shutdown, nạp lại, log, resource leak và giữ compatibility.

**Lộ trình thực dụng cho đa số dự án:** nắm Java Core + JAR/class path → hiểu class loading → xây contract → dùng `ServiceLoader` → học JPMS/strong encapsulation → reflection/annotation → proxy/MethodHandle → chỉ sau đó học loader riêng và instrumentation nếu đề bài thật sự cần. Kết quả quan trọng nhất không phải dùng thật nhiều kỹ thuật “động”, mà là **xây extension point rõ ràng, ổn định, quan sát được và quản lý được vòng đời**.

## 15. Tài liệu chuẩn để tra cứu tiếp

- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Proxy` và `InvocationHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Java SE 17 API, `MethodHandles`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 API, `java.lang.instrument`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JPMS và `--add-opens`: https://dev.java/learn/organizing/modules/add-exports-opens/
- JDK 17 migration và strong encapsulation: https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html
