# Thực hành: Nạp hai plugin dùng hai phiên bản thư viện riêng bằng classloader độc lập

## 1. Mục tiêu và kết quả cần đạt

Một ứng dụng host Java phải chạy đồng thời hai plugin, mỗi plugin phụ thuộc vào **một phiên bản khác nhau của cùng thư viện**. Ví dụ plugin A cần `vendor.Helper` phiên bản `1.0`, còn plugin B cần `vendor.Helper` phiên bản `2.0`. Hai JAR thư viện đều chứa class có tên nhị phân `vendor.Helper`, nên nếu đặt cả hai lên cùng application classpath, classloader thường chỉ định nghĩa một bản cho tên đó và plugin còn lại có thể chạy sai hoặc gặp `NoSuchMethodError`.

Giải pháp thực hành: đặt hợp đồng SPI ở **parent classloader**, còn mỗi plugin và JAR thư viện riêng vào **một child URLClassLoader độc lập**. Mục tiêu kiểm chứng:

- Cả hai provider đều ép kiểu được về cùng interface `spi.Plugin` của host.
- Plugin A trả kết quả chứa version `1.0`, plugin B trả version `2.0`.
- Hai class `vendor.Helper` có **cùng tên nhị phân nhưng khác identity** vì được định nghĩa bởi hai loader khác nhau.
- Plugin A không thể nhìn thấy private dependency của plugin B thông qua loader của mình.
- Dừng plugin, bỏ tham chiếu và đóng loader đúng vòng đời; không nhầm classloader isolation với security sandbox.

```text
                           Parent / AppClassLoader
                           spi.Plugin (API chung)
                                    |
                         +----------+----------+
                         |                     |
                    URLClassLoader A       URLClassLoader B
                     plugin-a.jar           plugin-b.jar
                     helper-v1.jar          helper-v2.jar
                         |                     |
               vendor.Helper v1        vendor.Helper v2
                         |                     |
                   '1.0: alpha'          '2.0: beta'
```

## 2. Cơ chế class identity và parent delegation

Trong JVM, một runtime class được xác định bởi **binary name cùng defining classloader**, không chỉ bằng tên package/class. Vì thế hai loader khác nhau có thể định nghĩa `vendor.Helper` từ bytecode khác nhau. Nhưng `spi.Plugin` mà cả hai provider implement phải là **cùng runtime class** do parent loader định nghĩa; nếu child chứa và nạp một bản sao API theo child-first, host có thể gặp `ClassCastException` dù tên interface giống hệt.

Ví dụ dùng `URLClassLoader` mặc định theo **parent-first delegation**. Điều này phù hợp khi:

1. Parent classpath chứa duy nhất **API chung + host**, không chứa `vendor.Helper` hoặc class implementation plugin.
2. Mỗi child có đúng plugin JAR và dependency JAR cùng phiên bản của nó.
3. Plugin implementations là class mới trong child nên parent không tìm thấy; child sẽ định nghĩa chúng.
4. Dependency `vendor.Helper` không nằm trong parent, nên từng child sẽ tải bản của mình.

**Lưu ý quan trọng:** URLClassLoader riêng không tự cô lập dependency nếu parent đã tải cùng tên class. Không nên đưa cả hai `helper-v*.jar` lên system classpath rồi kỳ vọng child chọn đúng bản. Đây là lý do đường dẫn chạy bên dưới chỉ chứa host và API.

## 3. Cấu trúc dự án

```text
plugin-isolation-demo/
  src/
    api/spi/Plugin.java
    lib-v1/vendor/Helper.java
    lib-v2/vendor/Helper.java
    plugin-a/plugins/PluginA.java
    plugin-b/plugins/PluginB.java
    host/Host.java
  build/
    api/
    lib-v1/
    lib-v2/
    plugin-a/
    plugin-b/
    host/
  dist/
    api.jar
    helper-v1.jar
    helper-v2.jar
    plugin-a.jar
    plugin-b.jar
    host.jar
```

Đây là **classpath-based plugin isolation** bằng `URLClassLoader`, không phải ví dụ JPMS named modules. Khi dùng JPMS layer riêng, phải xem thêm module resolution và split packages. Bài thực hành hiện tại tập trung vào khả năng đặt hai phiên bản thư viện chung tên class trong hai classloader độc lập.

## 4. Viết hợp đồng SPI chung

Tạo `src/api/spi/Plugin.java`:

```java
package spi;

public interface Plugin extends AutoCloseable {
    String id();
    String execute(String input);
    @Override
    default void close() throws Exception {}
}
```

Interface nằm trong `api.jar` do host/parent loader sở hữu. Các JAR plugin **không đóng gói bản sao** `spi/Plugin.class`; khi biên dịch, plugin chỉ tham chiếu API trên compilation classpath.

## 5. Tạo hai phiên bản của cùng thư viện

Thư viện V1 ở `src/lib-v1/vendor/Helper.java`:

```java
package vendor;

public final class Helper {
    private Helper() {}
    public static String transform(String input) {
        return "1.0: " + input;
    }
}
```

Thư viện V2 ở `src/lib-v2/vendor/Helper.java`:

```java
package vendor;

public final class Helper {
    private Helper() {}
    public static String transform(String input) {
        return "2.0: " + input;
    }
}
```

Hai source có cùng package, class name và method signature để chứng minh rõ version nào được tải; version thật ngoài đời có thể thay cả implementation hoặc API. Khi compile vào thư mục/JAR tách biệt, JVM sẽ có thể nạp đồng thời cả hai bản trong hai loader.

## 6. Tạo hai plugin độc lập

`src/plugin-a/plugins/PluginA.java`:

```java
package plugins;

import spi.Plugin;
import vendor.Helper;

public final class PluginA implements Plugin {
    @Override public String id() { return "plugin-A"; }
    @Override public String execute(String input) {
        return Helper.transform(input);
    }
}
```

`src/plugin-b/plugins/PluginB.java`:

```java
package plugins;

import spi.Plugin;
import vendor.Helper;

public final class PluginB implements Plugin {
    @Override public String id() { return "plugin-B"; }
    @Override public String execute(String input) {
        return Helper.transform(input);
    }
}
```

Mỗi plugin phụ thuộc vào `spi.Plugin` chung nhưng gọi `vendor.Helper` từ bản dependency **trong loader của chính nó**. Để kiểm chứng, host sẽ đọc class `vendor.Helper` bằng đúng loader của từng plugin.

## 7. Host nạp plugin bằng hai URLClassLoader

Tạo `src/host/Host.java`:

```java
import spi.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Host {
    static URL url(String file) throws Exception {
        return Path.of("dist", file).toAbsolutePath().toUri().toURL();
    }

    static Plugin load(URLClassLoader loader, String className)
            throws Exception {
        Class<?> clazz = Class.forName(className, true, loader);
        return clazz.asSubclass(Plugin.class)
                .getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = Plugin.class.getClassLoader();
        try (URLClassLoader loaderA = new URLClassLoader(
                     new URL[]{url("plugin-a.jar"), url("helper-v1.jar")}, parent);
             URLClassLoader loaderB = new URLClassLoader(
                     new URL[]{url("plugin-b.jar"), url("helper-v2.jar")}, parent)) {

            Plugin a = load(loaderA, "plugins.PluginA");
            Plugin b = load(loaderB, "plugins.PluginB");
            try {
                System.out.println(a.id() + " -> " + a.execute("alpha"));
                System.out.println(b.id() + " -> " + b.execute("beta"));

                Class<?> helperA = loaderA.loadClass("vendor.Helper");
                Class<?> helperB = loaderB.loadClass("vendor.Helper");
                System.out.println("same helper class? " + (helperA == helperB));
                System.out.println("same API? " +
                        (a instanceof Plugin && b instanceof Plugin));
            } finally {
                try { a.close(); } finally { b.close(); }
            }
        }
    }
}
```

Ở đây `new URLClassLoader(urls, parent)` cấp cho hai plugin hai **namespace độc lập**. Hàm `Class.forName(..., loader)` dùng đúng loader. `asSubclass(Plugin.class)` xác nhận provider dùng cùng API class identity; nếu class không tương thích sẽ báo lỗi ngay. `try-with-resources` đóng cả hai loader, nhưng trong ứng dụng thật phải đảm bảo không còn callback/thread đang sử dụng plugin trước khi đóng.

### Lưu ý về teardown

Ví dụ dùng `try/finally` lồng để vẫn thử đóng B khi đóng A ném lỗi. Trong production nên tổng hợp exceptions bằng `addSuppressed`, dừng request, đóng executor/listener/socket và chỉ sau đó đóng loader. `URLClassLoader.close()` giải phóng tài nguyên do loader giữ; nó **không tự unload mọi class hoặc dừng thread của plugin**.

## 8. Biên dịch các thành phần tách biệt trên Java 17+

Đứng ở thư mục gốc `plugin-isolation-demo` và chạy trong shell bash:

```bash
mkdir -p build/api build/lib-v1 build/lib-v2 build/plugin-a build/plugin-b build/host dist
javac --release 17 -d build/api src/api/spi/Plugin.java
javac --release 17 -d build/lib-v1 src/lib-v1/vendor/Helper.java
javac --release 17 -d build/lib-v2 src/lib-v2/vendor/Helper.java
javac --release 17 -cp build/api:build/lib-v1 -d build/plugin-a src/plugin-a/plugins/PluginA.java
javac --release 17 -cp build/api:build/lib-v2 -d build/plugin-b src/plugin-b/plugins/PluginB.java
javac --release 17 -cp build/api -d build/host src/host/Host.java

jar --create --file dist/api.jar -C build/api .
jar --create --file dist/helper-v1.jar -C build/lib-v1 .
jar --create --file dist/helper-v2.jar -C build/lib-v2 .
jar --create --file dist/plugin-a.jar -C build/plugin-a .
jar --create --file dist/plugin-b.jar -C build/plugin-b .
jar --create --file dist/host.jar -C build/host .

java -cp dist/api.jar:dist/host.jar Host
```

Trên Windows, `javac -cp` và `java -cp` dùng dấu phân cách `;` thay vì `:`; ví dụ `-cp "build/api;build/lib-v1"`. `Path` trong `Host` lấy file từ thư mục `dist` dựa trên working directory; chạy chương trình từ gốc dự án.

Output kỳ vọng:

```text
plugin-A -> 1.0: alpha
plugin-B -> 2.0: beta
same helper class? false
same API? true
```

Hai class có cùng `vendor.Helper` nhưng `helperA != helperB`, vì mỗi child loader định nghĩa class riêng. Ngược lại hai provider đều implement một `spi.Plugin` runtime class từ parent nên phép kiểm tra `instanceof Plugin` đều true.

## 9. Vì sao cách đơn giản hơn thường thất bại?

Nếu đặt mọi JAR vào cùng classpath:

```bash
java -cp dist/api.jar:dist/host.jar:dist/plugin-a.jar:dist/plugin-b.jar:dist/helper-v1.jar:dist/helper-v2.jar Host
```

thì application classloader có thể tìm thấy `vendor.Helper` ở parent trước child loader; cả plugin có thể dùng cùng version V1, phá mục tiêu isolation. Lệnh này là **ví dụ cấu hình sai, không phải bước chạy chuẩn**. Ngoài ra khi parent chứa implementation plugin, class `plugins.PluginA` có thể được định nghĩa bởi parent, làm bạn hiểu lầm rằng classloader riêng đã được sử dụng.

Vì vậy chỉ đặt `api.jar` và `host.jar` trên parent classpath; plugin và thư viện được trao riêng cho child loaders.

## 10. Khi hai phiên bản có API không tương thích

Trong ví dụ, cả hai version có method `transform(String)` nên source compile đơn giản. Thực tế V2 có thể đổi method signature hoặc return type. Plugin A và B phải compile với version thư viện đúng của mình; nếu vô tình chạy plugin B với V1, có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi logic.

Quy tắc là: mỗi plugin bundle/loader gồm **toàn bộ dependency phù hợp** và API chung được chia sẻ ở parent. Nếu cả hai plugin cần tương tác, đừng truyền trực tiếp object thuộc `vendor.Helper` qua ranh giới; chuyển qua DTO/interface trong API chung hoặc dữ liệu chuẩn như `String`, `byte[]`, immutable records thuộc parent API.

## 11. TCCL, ServiceLoader và tài nguyên

Một số thư viện khám phá dịch vụ bằng thread context classloader (TCCL) hoặc `ServiceLoader.load(Service.class)` mặc định, nên có thể không nhìn đúng resources của plugin. Khi chạy code plugin cần TCCL cụ thể, host có thể tạm đặt loader:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(loaderA);
    a.execute("work");
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là đoạn minh họa trong method có biến `loaderA` và plugin `a`, không phải chương trình đầy đủ. Không quên phục hồi TCCL: nếu giữ loader trong thread pool lâu sống, nó có thể ngăn garbage collection của classloader đã dừng.

Plugin còn có thể có `META-INF/services` riêng. Với `ServiceLoader.load(service, loaderA)`, phải bảo đảm SPI interface `service` là class identity từ parent và descriptor nằm đúng plugin/dependency JAR. Không dùng TCCL hoặc `ServiceLoader` để cố ép type objects của plugin-private dependencies qua boundary.

## 12. Kiểm thử cô lập và vòng đời

Test không nên chỉ nhìn output. Nên xác nhận:

1. **Class identity:** `loaderA.loadClass("vendor.Helper") != loaderB.loadClass("vendor.Helper")`.
2. **API chung:** `a instanceof spi.Plugin` và `b instanceof spi.Plugin`.
3. **Phiên bản:** output A chứa V1, B chứa V2 như expected.
4. **Không rò rỉ:** parent classpath không chứa plugin/vendor classes.
5. **Negative test:** cố ý gán dependency V1 cho B và quan sát mismatch hoặc hành vi sai.
6. **Reload:** tạo loader mới với JAR phiên bản mới; không định nghĩa lại class cùng name trong loader cũ.
7. **Teardown:** dừng plugin, close loader, unregister listener và dọn threads.
8. **Artifact test:** chạy host từ JAR phân phối, không chỉ class files trong IDE.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hai plugin đều dùng V1 | `vendor.Helper` nằm trên parent classpath | Bỏ dependency riêng khỏi parent |
| `ClassCastException` sang `spi.Plugin` | Mỗi child chứa/nạp bản sao API | Parent sở hữu API, child không bundle API |
| `NoSuchMethodError` | Plugin load sai version dependency | Bundle đúng per-plugin dependency |
| `ClassNotFoundException` | JAR không nằm trong URLs của loader tương ứng | Kiểm tra URL list và filenames |
| Resources/SPI không được tìm thấy | Loader/TCCL sai hoặc descriptors thiếu | Dùng đúng classloader, giữ resource files |
| Jar vẫn bị khóa hoặc loader leak | Không close loader, thread/listener giữ reference | Lifecycle stop và dọn TCCL/registry |
| `LinkageError` khi reload | Define lại tên class trong cùng loader | Tạo loader mới cho phiên bản mới |

## 14. Giới hạn bảo mật

Classloader isolation chỉ tách **namespace class** và hỗ trợ quản lý phiên bản dependency; các plugin vẫn chạy trong cùng JVM, cùng user OS, heap, thread pools và có thể làm hỏng state của host. Không dùng `URLClassLoader` như sandbox cho code chưa tin cậy. Với plugin không tin cậy, chuyển sang JVM/process hoặc container riêng với quyền OS tối thiểu và IPC có schema, timeout, quota.

## 15. Checklist hoàn thành bài thực hành

- [ ] Hai phiên bản `vendor.Helper` được biên dịch và đóng gói **riêng**.
- [ ] Host + API chỉ xuất hiện trên parent classpath.
- [ ] Mỗi plugin có child `URLClassLoader` với đúng plugin JAR và vendor JAR.
- [ ] Provider implement interface `spi.Plugin` duy nhất từ parent.
- [ ] Chạy cùng lúc plugin A/V1 và plugin B/V2, đúng output.
- [ ] Kiểm chứng `vendor.Helper` identity khác nhau.
- [ ] Quản lý TCCL khi thư viện cần và phục hồi trong `finally`.
- [ ] Đóng plugin và loader theo lifecycle, kiểm tra memory leaks.
- [ ] Không nhầm dependency isolation với security isolation.

**Kết luận:** mô hình **một parent API + một classloader cho mỗi plugin và dependency set riêng** cho phép Java chạy đồng thời hai phiên bản thư viện trùng tên class. Bài thực hành nhấn mạnh phải kiểm chứng **class identity**, **API sharing**, **artifact classpath sạch** và **vòng đời loader**, không chỉ kiểm tra một dòng output.
