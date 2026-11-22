# So sánh một loader chung, loader theo plugin và nhóm plugin dùng chung phụ thuộc

## 1. Vấn đề cần giải quyết: nhiều plugin, nhiều phiên bản dependency

Giả sử ứng dụng Java (host) có ba plugin: **A** xuất báo cáo, **B** xử lý tài liệu và **C** phân tích dữ liệu. A được build với `lib-json:1.x`, B cần `lib-json:2.x`, C cũng dùng `lib-json:2.x`. Host cần nạp chúng trong cùng JVM mà không sửa plugin của nhà cung cấp.

Có ba lựa chọn chính về **phạm vi chia sẻ lớp (class loading boundary)**:

1. **Một loader chung:** đặt JAR plugin và dependency trong cùng một vùng định nghĩa class.
2. **Một loader riêng cho từng plugin:** mỗi plugin nhìn thấy dependency của mình, dùng chung API của host qua parent loader.
3. **Nhóm plugin dùng chung phụ thuộc:** mỗi nhóm có loader chứa dependency chung theo một phiên bản được chọn; các plugin thành viên có loader con hoặc cùng một vùng loader, tùy mức độ cách ly mong muốn.

Cả ba vẫn chạy trong **cùng JVM và process**. Sự khác nhau chủ yếu là class identity, phiên bản thư viện nào được định nghĩa, scope của static state, khả năng giải phóng plugin, bộ nhớ và độ phức tạp vận hành. Class loader **không** tạo sandbox bảo mật để chạy mã không tin cậy.

Bài này sử dụng Java 17+ và JAR trên **class path** để xây mô hình trước, sau đó so sánh cách áp dụng với JPMS (Java Platform Module System). “Một loader chung” là một chiến lược triển khai, không nhất thiết là duy nhất một instance class loader trong toàn JVM: JDK vẫn có bootstrap/platform/application loaders và các loader khác.

## 2. Nền tảng quyết định đúng: tên class không đủ định danh kiểu

### 2.1. Class identity = tên nhị phân + defining loader

JVM coi một class/interface được xác định bởi **binary name và defining `ClassLoader`**. Hai class đều tên `com.acme.lib.Model` nhưng được định nghĩa bởi hai loader độc lập là **hai runtime type khác nhau**.

~~~text
HostClassLoader
├── PluginALoader  → com.acme.lib.Model (v1)
└── PluginBLoader  → com.acme.lib.Model (v2)

Tên class giống nhau, nhưng:
(Model, PluginALoader) != (Model, PluginBLoader)
~~~

Hệ quả: object `Model` v1 của A không thể ép sang `Model` v2 của B chỉ vì `getClass().getName()` giống nhau. Ép kiểu có thể ném `ClassCastException`; ở một số quan hệ chữ ký/biên dịch khác, JVM có thể phát sinh `LinkageError`. Tương tự, `static` field, cache, singleton và class initialization thuộc phạm vi **class được định nghĩa**: hai phiên bản ở hai loader có static state riêng (dù vẫn có thể chia sẻ tài nguyên process khác).

**Initiating loader** là loader được yêu cầu tìm class; nó có thể ủy quyền cho **defining loader** khác. Vì vậy, hai plugin loader khác nhau vẫn có thể nhìn thấy **chính cùng một `Class<?>`** khi cả hai cùng delegate tới parent đã định nghĩa API hoặc thư viện dùng chung.

### 2.2. Parent-first là hành vi mặc định đáng dựa vào

Với triển khai `ClassLoader.loadClass(name, resolve)` mặc định, JVM/loader:

1. Kiểm tra class đã load qua `findLoadedClass`.
2. Thử `loadClass` của **parent** (hoặc bootstrap khi không có parent).
3. Nếu parent không tìm thấy, dùng `findClass` của loader hiện tại.
4. Resolve class theo tham số nếu cần.

`URLClassLoader` kế thừa mô hình delegation này đối với class thông thường. **Vị trí parent rất quan trọng:** nếu parent đã định nghĩa `com.acme.lib.Model` v1, loader con mặc định sẽ nhận v1 dù trong JAR của nó có bản v2 cùng tên. Sự hiện diện của hai JAR **không tự tạo hai runtime class**.

Có thể xây loader `child-first` cho **gói private được kiểm soát** khi framework có yêu cầu đặc biệt, nhưng không nên dùng child-first toàn cục: nếu plugin định nghĩa lại service API hoặc DTO của host, cast và giao tiếp qua interface có thể gãy. Ngoài ra còn package sealing, resources, loader constraints, JNI và deadlock khi delegation không còn là cây đơn giản. Hãy dùng parent-first làm mặc định và ghi rõ ngoại lệ nếu cần.

### 2.3. Phân biệt bốn thứ thường bị gọi chung là “cô lập”

- **Cô lập version:** cho phép cùng một binary class name có các bản bytecode khác nhau, được định nghĩa bởi loader riêng.
- **Cô lập type/static state:** tránh dùng chung `Class` object và static singleton giữa các plugin.
- **Cô lập dependency/resource:** giới hạn JAR, class/resource và provider metadata được tìm thấy từ một loader. Resource lookup còn phụ thuộc `getResource(s)`, parent và TCCL, nên phải kiểm tra riêng.
- **Cô lập lỗi, bảo mật, CPU/bộ nhớ:** **không** được bảo đảm chỉ bởi loader. Exception, thread, native library, JVM crash, process-level state và tài nguyên OS vẫn chung. Muốn chạy mã không tin cậy hoặc cần giới hạn tài nguyên cứng, dùng process/container riêng.

## 3. Sơ đồ ba mô hình

### 3.1. Mô hình A — Một plugin/dependency loader chung

~~~text
ApplicationClassLoader
  └── PluginUniverseLoader
        ├── plugin-a.jar
        ├── plugin-b.jar
        ├── plugin-c.jar
        ├── lib-json-1.jar
        └── lib-utils.jar

A, B, C cùng nhìn thấy class do PluginUniverseLoader định nghĩa.
~~~

Một vùng loader chỉ có thể định nghĩa **một class cho một binary name**. Nếu đặt `lib-json-1.jar` và `lib-json-2.jar` cùng có `com.acme.json.Json` vào cùng search path, loader không chọn version khác nhau theo plugin. Trong mô hình `URLClassLoader` thông thường với parent không chứa class này, URL/JAR chứa class được tìm thấy trước sẽ thắng cho tên đó; phiên bản còn lại không có “cơ hội thứ hai” để được định nghĩa cùng tên trong loader ấy.

**Phù hợp:** ít plugin, cùng được build/test chung; chúng dùng một dependency graph đã được resolve duy nhất; nâng cấp/khởi động lại đồng thời chấp nhận được. Chi phí loader, memory duplication và khâu quản lý thấp.

**Đổi lại:** các plugin chịu chung tập version và static state của thư viện chung. B thay đổi yêu cầu lên API chỉ có trong v2 có thể gặp `NoSuchMethodError` nếu loader đã chọn v1; thêm JAR khác không đảm bảo sửa được. Nếu đặt toàn bộ plugin vào cùng loader, việc thay class của một plugin bằng **loader mới** thường kéo theo thay cả vùng loader, trừ khi có một cơ chế reload phức tạp khác.

### 3.2. Mô hình B — Loader riêng cho từng plugin

~~~text
ApplicationClassLoader
  ├── Host API / contracts / shared DTO
  │
  ├── PluginALoader
  │     ├── plugin-a.jar
  │     └── lib-json-1.jar
  │
  ├── PluginBLoader
  │     ├── plugin-b.jar
  │     └── lib-json-2.jar
  │
  └── PluginCLoader
        ├── plugin-c.jar
        └── lib-json-2.jar
~~~

Mỗi plugin loader có search path riêng. Vì `lib-json` không nằm trong parent và các plugin loaders không delegate cho nhau, A có `Json` v1, B và C có **hai bản `Json` v2 được định nghĩa độc lập**. B và C dùng cùng bytecode/version cũng **không** có cùng class identity nếu mỗi loader tự định nghĩa thư viện.

**Phù hợp:** các plugin cập nhật/kiểm thử độc lập, có xung đột version, cần tháo một plugin khi các plugin khác tiếp tục chạy. Đây là lựa chọn phổ biến cho nền tảng plugin có nhiều bên phát triển.

**Đổi lại:** thư viện được load lặp lại, thêm class metadata/Metaspace, JIT compilation, static caches và tài nguyên; việc chuyển object dependency-private trực tiếp qua plugin khác không an toàn. Mỗi plugin phải giữ contract và DTO của host ở parent chung. Plugin chỉ có thể giải phóng loader khi không còn object, thread, listener, cache hay reference nào giữ lớp/loader của nó.

### 3.3. Mô hình C — Nhóm plugin dùng chung phụ thuộc

~~~text
ApplicationClassLoader
  ├── Host API / shared DTO
  │
  ├── GroupOneDepsLoader  (lib-json-1.jar)
  │     └── PluginALoader (plugin-a.jar)
  │
  └── GroupTwoDepsLoader  (lib-json-2.jar)
        ├── PluginBLoader (plugin-b.jar)
        └── PluginCLoader (plugin-c.jar)
~~~

Nhóm Một và Nhóm Hai có loader dependency riêng: chúng có thể dùng **hai phiên bản `Json` khác nhau**. Trong Nhóm Hai, B và C đều delegate tới `GroupTwoDepsLoader`, nên **chia sẻ cùng `Class<?>` `Json` v2 và static state của nó**. Phần implementation riêng của B/C vẫn có thể nằm trong hai child loaders khác nhau.

**Phù hợp:** nhiều plugin cần cùng bộ thư viện nặng và được kiểm soát tương thích theo “cohort”/nhóm; cần giảm nhân bản bộ nhớ nhưng vẫn tách được các nhóm dùng version khác nhau.

**Đổi lại:** nhóm có phiên bản và vòng đời dependency **gắn nhau**. Nếu B cần v3 còn C cần v2, phải thử compatibility hoặc tách B sang nhóm khác. Nếu muốn unload group dependency loader, cần bảo đảm **tất cả** plugin con và mọi object/class/thread liên quan đã được giải phóng. Một group loader còn tồn tại thì các class thư viện group vẫn có thể được giữ lại.

**Lưu ý kỹ thuật:** loader theo nhóm như sơ đồ thường chứa **dependency của nhóm**, còn mã plugin ở loader con. Một biến thể đặt cả plugin code và dependency vào **một loader cho mỗi nhóm** đơn giản hơn, nhưng mất mức tách code/lifecycle giữa các plugin cùng nhóm. Tên “nhóm plugin chia sẻ phụ thuộc” cần nói rõ hai biến thể này trước khi áp dụng.

## 4. Bảng so sánh tổng hợp

| Tiêu chí | Một loader chung | Một loader/plugin | Loader dependency theo nhóm + child/plugin |
| --- | --- | --- | --- |
| Phạm vi lớp plugin | Tất cả chung một vùng | Mỗi plugin riêng | Mỗi plugin riêng, dependency trong nhóm chung |
| Hai version cùng binary class name | Không trong cùng defining loader | Có, ở hai loaders | Có, giữa các nhóm; **không** thể cùng tên/khác version trong một group deps loader |
| Static field của dependency | Chung cho tất cả plugin dùng class ấy | Riêng cho từng plugin | Chung trong một nhóm, tách giữa nhóm |
| Class identity của dependency | Chung nếu cùng class đã define | Khác giữa plugin | Chung trong nhóm, khác giữa nhóm |
| Chi phí nhân bản class/JIT/cache | Thường thấp | Có thể cao | Trung gian |
| Tách release plugin | Kém nhất nếu plugin code chung loader | Tốt hơn về class loading, còn phụ thuộc lifecycle thực | Plugin code có thể tách; thay group deps tác động mọi thành viên |
| Khả năng nâng dependency độc lập | Tập trung toàn bộ | Từng plugin | Từng nhóm |
| Kiểm soát dependency graph | Một graph duy nhất | Mỗi plugin một graph | Một graph chung mỗi nhóm + private deps |
| Giao tiếp plugin ↔ host | Tương đối đơn giản nếu API thống nhất | Cần API/DTO parent chung | Cần API/DTO parent chung; tránh lộ class riêng của group qua biên khác group |
| Độ phức tạp deploy/debug | Thấp | Trung bình–cao | Cao nhất về quy tắc nhóm/version/lifecycle |
| Trường hợp nên ưu tiên | Plugin cùng đội, build/test chung | Plugin độc lập/xung đột versions | Plugin theo cụm, nhiều dependency nặng dùng chung |

Không có mô hình nào mặc nhiên “nhanh nhất”. Loader nhiều không đồng nghĩa runtime luôn chậm hơn: tác động thực tế phụ thuộc số class được load, JIT, kích thước dependency, resource giữ lại, concurrency và việc ứng dụng có tạo instance hay không. Đo **Metaspace, heap retained size, startup time, class count, CPU/JIT, số thread/file handle** trên workload thật trước khi tối ưu.

## 5. Ví dụ Java 17+ chạy được: quan sát cả ba mô hình bằng hai version của một class

Lab dưới đây không cần thư viện bên thứ ba. Nó tạo hai JAR đều chứa `demo.lib.Version` nhưng trả về `v1`/`v2`; PluginA được compile với v1, PluginB với v2. Host **không** chứa `demo.lib.Version` trong class path; host dùng reflection chỉ để gọi hai plugin demo, từ đó minh họa lookup/identity mà chưa cần thiết kế SPI hoàn chỉnh.

### 5.1. Cấu trúc source

~~~text
loader-compare/
├── src/
│   ├── v1/demo/lib/Version.java
│   ├── v2/demo/lib/Version.java
│   ├── a/demo/plugin/PluginA.java
│   ├── b/demo/plugin/PluginB.java
│   └── host/LoaderComparison.java
├── build/                 # Sinh sau khi compile
└── jars/                  # Sinh sau khi tạo JAR
~~~

Tệp `src/v1/demo/lib/Version.java`:

~~~java
package demo.lib;

public final class Version {
    public static String value() {
        return "v1";
    }
}
~~~

Tệp `src/v2/demo/lib/Version.java` có cùng binary name và chữ ký, nhưng thân phương thức trả `v2`:

~~~java
package demo.lib;

public final class Version {
    public static String value() {
        return "v2";
    }
}
~~~

Tệp `src/a/demo/plugin/PluginA.java`:

~~~java
package demo.plugin;

import demo.lib.Version;

public final class PluginA {
    public String run() {
        return "A:" + Version.value();
    }
}
~~~

Tệp `src/b/demo/plugin/PluginB.java`:

~~~java
package demo.plugin;

import demo.lib.Version;

public final class PluginB {
    public String run() {
        return "B:" + Version.value();
    }
}
~~~

Tệp `src/host/LoaderComparison.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderComparison {
    private static String run(ClassLoader loader, String className)
            throws ReflectiveOperationException {
        Class<?> type = Class.forName(className, true, loader);
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("run").invoke(instance);
    }

    private static Class<?> versionClass(ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName("demo.lib.Version", false, loader);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "Pass lib-v1.jar lib-v2.jar plugin-a.jar plugin-b.jar");
        }

        URL v1 = Path.of(args[0]).toUri().toURL();
        URL v2 = Path.of(args[1]).toUri().toURL();
        URL pluginA = Path.of(args[2]).toUri().toURL();
        URL pluginB = Path.of(args[3]).toUri().toURL();
        ClassLoader host = LoaderComparison.class.getClassLoader();

        // A: một loader chung; v1 đứng trước v2 trong URL search path.
        try (URLClassLoader one = new URLClassLoader(
                new URL[] { v1, v2, pluginA, pluginB }, host)) {
            System.out.println("ONE " +
                    run(one, "demo.plugin.PluginA") + " " +
                    run(one, "demo.plugin.PluginB"));
        }

        // B: mỗi plugin một loader, mỗi loader có version riêng.
        try (URLClassLoader a = new URLClassLoader(
                     new URL[] { pluginA, v1 }, host);
             URLClassLoader b = new URLClassLoader(
                     new URL[] { pluginB, v2 }, host)) {
            System.out.println("PER " +
                    run(a, "demo.plugin.PluginA") + " " +
                    run(b, "demo.plugin.PluginB") +
                    " sameLib=" + (versionClass(a) == versionClass(b)));
        }

        // C: dependency v1 ở loader nhóm; plugin code ở hai loader con.
        try (URLClassLoader group = new URLClassLoader(
                     new URL[] { v1 }, host);
             URLClassLoader a = new URLClassLoader(
                     new URL[] { pluginA }, group);
             URLClassLoader b = new URLClassLoader(
                     new URL[] { pluginB }, group)) {
            System.out.println("GROUP " +
                    run(a, "demo.plugin.PluginA") + " " +
                    run(b, "demo.plugin.PluginB") +
                    " sameLib=" + (versionClass(a) == versionClass(b)));
        }
    }
}
~~~

**Đọc code theo thứ tự:**

- `run(loader, className)` yêu cầu đúng loader nạp mã plugin. Nó chỉ dùng reflection để gọi demo; trong sản phẩm thực tế, hãy dùng interface API chia sẻ ở parent.
- `versionClass` trả về `Class<?>` cho `demo.lib.Version` mà mỗi loader nhìn thấy; `==` so sánh **runtime class identity**, không so sánh tên.
- Trường hợp ONE đặt v1 trước v2 trong URL search path. `Version` được định nghĩa theo v1; cả A và B nhìn thấy v1.
- Trường hợp PER dùng hai loader độc lập, mỗi loader chứa đúng một version và plugin tương ứng.
- Trường hợp GROUP để cả hai plugin delegate lên cùng group loader có v1: cả hai thấy v1, cùng `Class<?>`. B được compile với v2 nhưng `value()` vẫn tương thích chữ ký nên chạy được, dù **không còn dùng version đã compile**.

### 5.2. Biên dịch và đóng gói

Chạy từ thư mục `loader-compare` bằng **PowerShell** (Windows, JDK 17+ có `javac` và `jar`). Các lệnh dưới đây tạo đúng bốn JAR; không dùng build tool để người học thấy rõ dependency nào thuộc JAR nào:

~~~powershell
New-Item -ItemType Directory -Force build\v1,build\v2,build\a,build\b,build\host,jars | Out-Null

javac -encoding UTF-8 -d build\v1 src\v1\demo\lib\Version.java
javac -encoding UTF-8 -d build\v2 src\v2\demo\lib\Version.java

javac -encoding UTF-8 -cp build\v1 -d build\a src\a\demo\plugin\PluginA.java
javac -encoding UTF-8 -cp build\v2 -d build\b src\b\demo\plugin\PluginB.java

javac -encoding UTF-8 -d build\host src\host\LoaderComparison.java

jar --create --file jars\lib-v1.jar -C build\v1 .
jar --create --file jars\lib-v2.jar -C build\v2 .
jar --create --file jars\plugin-a.jar -C build\a .
jar --create --file jars\plugin-b.jar -C build\b .

java -cp build\host LoaderComparison jars\lib-v1.jar jars\lib-v2.jar jars\plugin-a.jar jars\plugin-b.jar
~~~

**Stdout kỳ vọng chính xác** (trên JDK 17+ với đúng bốn JAR vừa tạo và host chỉ có `build\host` trong class path):

~~~text
ONE A:v1 B:v1
PER A:v1 B:v2 sameLib=false
GROUP A:v1 B:v1 sameLib=true
~~~

Đây là kết quả quan trọng nhất:

- **ONE:** chung classloader nên cả hai bị chi phối bởi **một lựa chọn version**; hiện tượng “first found wins” ở đây gắn với URL order và việc parent không chứa `Version`.
- **PER:** cùng tên `demo.lib.Version` nhưng hai class khác nhau; A/B độc lập về version.
- **GROUP:** mỗi plugin có loader riêng **nhưng** cả hai thấy dependency từ group parent, nên chia sẻ type và version.

Với một mô hình GROUP nhiều nhóm thực tế, tạo `Group1Loader` từ v1 cho plugin A và `Group2Loader` từ v2 cho B/C. Khi so sánh `versionClass(group1Child) == versionClass(group2Child)`, kết quả `false` vì hai group loaders định nghĩa độc lập. Mô hình lab một nhóm được chọn để làm nổi bật cơ chế **chia sẻ bên trong nhóm**.

### 5.3. Thử phá tương thích để hiểu NoSuchMethodError

Hãy thêm method `public static String newFeature()` **chỉ** ở `Version` v2, sửa `PluginB.run()` gọi method đó, rồi compile lại B với v2.

- Với **PER**, B thấy `Version` v2 nên có thể gọi `newFeature()`.
- Với **ONE** nếu v1 được tìm trước, B sẽ tìm method trên `Version` v1 và có thể ném `NoSuchMethodError` khi lời gọi được liên kết/thực thi.
- Với **GROUP** đang ghim v1, B cũng gặp vấn đề; phải nâng version của cả group nếu tương thích ngược với A, hoặc chuyển B sang group khác.

Không nên sửa thứ tự JAR một cách tùy tiện như chiến lược tương thích. Build/test nên xác định dependency graph và version ngay từ đầu; runtime loader chỉ hiện thực hóa quyết định đó.

## 6. Ranh giới API chia sẻ: điều kiện để plugin tương tác an toàn

Sơ đồ có parent loader chung cho **host API, DTO, event contract và interface dịch vụ**. Trong plugin platform thực tế, đây là quy tắc nền tảng:

~~~text
Host / ApiLoader  →  com.example.api.Plugin, Request, Result
       │
       ├── PluginALoader → plugin A + thư viện private v1
       │
       └── PluginBLoader → plugin B + thư viện private v2

Host gọi qua com.example.api.Plugin,
không ép kiểu trực tiếp class private của A/B.
~~~

Ví dụ **chữ ký minh họa, không phải chương trình độc lập**:

~~~java
package com.example.api;

public interface Plugin {
    String id();
    Result execute(Request request);
}
~~~

`Request` và `Result` cũng phải là các type được host và các plugin nhìn thấy **từ cùng defining loader**, hoặc dùng dạng dữ liệu chuyển đổi rõ ràng (ví dụ byte array, JSON với schema/version), tránh truyền các object library-private khác class identity qua biên.

Nếu `plugin-a.jar` đóng gói một bản sao `com.example.api.Plugin` và loader A định nghĩa bản sao đó (chẳng hạn do child-first sai), object A có thể không cast được sang `Plugin` phía host. Với parent-first và API đã ở parent, bản sao ở child thường bị parent “che”, nhưng cách đóng gói trùng API vẫn làm hệ thống khó kiểm soát, đặc biệt khi phiên bản API khác nhau.

**Quy tắc đóng gói:**

- Tách `plugin-api.jar` ra khỏi implementation và đặt API trong parent/shared layer.
- Plugin compile với API theo `provided`/`compileOnly` nếu build tool hỗ trợ, tránh nhét lại vào plugin runtime JAR.
- Chỉ công khai DTO đủ ổn định; không để API chứa type cụ thể từ `lib-json-v1` nếu các plugin cần hai version khác nhau.
- Nếu plugin A phải gọi B, ưu tiên đi qua **host-owned interface/event bus** hoặc serializable payload với schema. Đừng truyền nguyên object `com.thirdparty.JsonNode` nếu type đó đang được định nghĩa riêng ở mỗi loader.
- Test compatibility giữa API host và plugin đã build từ các version cũ. **Cùng class identity không đảm bảo binary/source compatibility** nếu chữ ký đã thay đổi.

## 7. Cách xác định dependency nào phải chung, nào phải riêng

Không thể quyết định chỉ dựa vào tên JAR. Hãy phân loại **mỗi dependency** theo vai trò:

| Loại dependency | Nơi nên đặt | Lý do và cảnh báo |
| --- | --- | --- |
| JDK/Java SE APIs | Built-in/platform loaders theo JVM | Không sao chép vào plugin |
| Service API, DTO/event contract host | Parent chung | Đảm bảo class identity và cast qua ranh giới |
| Thư viện dữ liệu xuất hiện trong public API | Hoặc nâng lên API chung với version thống nhất, hoặc đổi boundary sang DTO riêng | Nếu để mỗi plugin giữ một version riêng mà public API dùng type đó thì integration dễ gãy |
| Thư viện thuần private, mỗi plugin cần version khác | Plugin loader | Tránh version collision |
| Thư viện lớn, nhiều plugin dùng **cùng version tương thích** | Group dependency loader | Giảm duplicate class/static cache; đổi lại coupling |
| Runtime framework dùng TCCL/`ServiceLoader` | Quyết định riêng phạm vi discovery và resource visibility | Đặt library ở đâu chưa đủ; phải kiểm tra TCCL/resource/config |
| Native library/JNI, global agent, process singleton | Cần chính sách riêng ở cấp JVM/process | Classloader không đảm bảo cô lập native code hay OS resources |

**Một trường hợp quan trọng:** hai plugin đều dùng `lib-x:2.0` chưa chắc nên chia sẻ group loader. Nếu thư viện có static mutable singleton, global registration, thread pool, logging context hoặc cache dùng riêng theo tenant, chia sẻ class có thể làm **chia sẻ state ngoài ý muốn**. Cần đánh giá behavior và ownership, không chỉ version.

Ngược lại, nếu `lib-x` là thư viện thuật toán bất biến, version đã ghim và có kích thước class metadata lớn, group loader thường tiết kiệm hơn việc mỗi plugin nạp riêng.

## 8. Class loader tree khác dependency graph

Đồ thị phụ thuộc build thường là DAG:

~~~text
Plugin A → API, Lib X, Lib Y
Plugin B → API, Lib X, Lib Z
Plugin C → API, Lib X, Lib Z
~~~

Nhưng một `ClassLoader` thông thường có **một parent**. Bạn không thể trực tiếp gán cho loader B hai parent “API loader” và “X loader” độc lập như hai cạnh dependency tùy ý. Cần tổ chức cây loader phù hợp (API → group deps → plugin), hoặc dùng cách routing/delegation tùy biến đã thiết kế cẩn thận.

Trong group model:

~~~text
ApiLoader
   └── GroupDepsLoader
         ├── PluginBLoader
         └── PluginCLoader
~~~

Plugin B nhìn thấy cả API (qua ancestor) và dependency nhóm. Dependency private B nằm ở child B, nên C **không tự nhìn thấy** các private class của B. Nếu B phải truy cập trực tiếp implementation của C, cần cầu nối do host kiểm soát; đừng âm thầm thêm delegation vòng B ↔ C. Delegation vòng hoặc loader tùy biến không parallel-capable có thể gây deadlock/classloading race, nhất là khi nhiều thread nạp class song song.

Đối với **các package trùng tên**, loader boundary có thể tránh trùng giữa hai **nhóm**. Trong **cùng group loader**, cùng binary name vẫn chỉ được định nghĩa một lần; không biến group thành “multi-version magic”.

## 9. TCCL, ServiceLoader và resource: cách ly class chưa đủ

### 9.1. Thread Context ClassLoader (TCCL)

Một số framework/library khám phá implementation qua `Thread.currentThread().getContextClassLoader()`. Overload `ServiceLoader.load(MyService.class)` sử dụng TCCL của thread gọi; vì vậy host gọi từ thread pool có TCCL là loader host có thể **không tìm thấy** provider chỉ hiện diện trong loader plugin.

Có thể thiết lập TCCL quanh lời gọi plugin khi framework yêu cầu. Đoạn dưới đây là **minh họa, không độc lập** (biến `pluginLoader` và `action` phải được khai báo):

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    action.run();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Dùng `finally` để tránh rò TCCL trên thread của pool sau khi trả về. Nếu plugin tự khởi tạo thread, thread ấy có thể kế thừa TCCL và **giữ loader cũ**, nên lifecycle phải quản lý cả executor/thread do plugin tạo.

Khi muốn chỉ rõ phạm vi tìm provider, có thể dùng `ServiceLoader.load(Service.class, pluginLoader)`. Tuy nhiên với parent-first/resource delegation, phạm vi đó có thể bao gồm cả provider metadata ở parent; **không nên xem đây là danh sách “chỉ plugin hiện tại” tuyệt đối** khi không kiểm soát resource discovery. Nếu cần whitelist, registry theo plugin ID, quyền và version, nên có catalog/metadata rõ ràng.

### 9.2. Service provider metadata cũng là resource

Class path SPI dùng `META-INF/services/<FQCN>`. `ServiceLoader` tìm resource theo loader, sau đó load implementation. Khi dependency hoặc provider JAR bị đặt sai ở parent/group, host có thể thấy một provider ngoài phạm vi mong đợi, hoặc nhìn thấy metadata nhưng không load được implementation và phát sinh `ServiceConfigurationError`.

Khi đóng gói fat JAR/shaded JAR, cần xử lý **merge service files** đúng cách. Chỉ gộp class files mà ghi đè một metadata file có thể làm provider biến mất dù bytecode còn trong JAR.

### 9.3. JPMS và ModuleLayer

Với **named modules**, JPMS dùng `module-info.java` để khai báo `requires`, `exports`, `opens`, `uses`, `provides` và đặt module vào `ModuleLayer`. Java 17 cung cấp:

- `ModuleLayer.defineModulesWithOneLoader(...)`: một loader cho các module trong layer đó.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: một loader **cho mỗi module** trong configuration đó.
- `ModuleLayer.defineModules(...)`: ánh xạ module name sang loader qua function tùy chỉnh (phải tuân thủ module readability, package/class-loading constraints và thiết kế cụ thể).

**Không đồng nhất “one loader per module” với “one loader per plugin”**. Một plugin có thể gồm nhiều module; một module có thể chứa nhiều package/feature. Module graph có các quy tắc resolution/readability/export riêng, còn class loader graph quyết định các type được định nghĩa ở đâu. Một module layer dùng chung loader còn có thể không tạo được khi có overlapping packages hoặc split delegation, theo quy tắc API.

Vì thế: class-path `URLClassLoader` và JPMS layer là **hai mô hình quản lý khác nhau**. Chỉ chuyển JAR sang module path không tự cô lập được version conflict; cần thiết kế module names, configuration, layer và loader mapping nhất quán.

## 10. Chi phí bộ nhớ và vòng đời: cái giá của cô lập

### 10.1. Cái gì được nhân bản?

Với N plugin dùng bản sao cùng thư viện nhưng mỗi plugin loader định nghĩa riêng các class của thư viện:

- **Metaspace / class metadata** cho các class được load trong mỗi loader có thể tăng.
- **JIT compilation / code cache** và class initialization có thể được thực hiện riêng cho những runtime class độc lập.
- **Static state/cache**, registry, thread, pool và các tài nguyên do thư viện tạo có thể lặp lại.
- **Heap** còn tùy object thực sự được tạo và giữ lại. Không phải cứ có JAR trong URL list là toàn bộ class và object đều bị load ngay.

Group loader giảm một phần duplication nếu các plugin thực sự delegate cùng thư viện group. Nhưng nó cũng tạo **shared fate**: class/static cache của thư viện được giữ sống miễn group loader vẫn được dùng bởi một plugin nào đó. Vì vậy không nên hứa mức tiết kiệm MB cố định mà chưa đo.

### 10.2. Đóng URLClassLoader không đồng nghĩa unload ngay

`URLClassLoader` implement `Closeable`. `close()` đóng resource/JAR file handle mà loader đã mở (với những giới hạn của API), giúp giải phóng file handle và tránh tình trạng file không thể thay thế trên một số hệ điều hành. Nó **không** “xóa bytecode đang chạy”, không ngắt thread, không gọi `Plugin.stop()` và không buộc class unloading ngay lập tức.

Để một thế hệ plugin loader có thể được GC/unload khi JVM cho phép:

1. Ngăn nhận request mới vào thế hệ cũ.
2. Đợi request hiện tại hoàn tất hoặc có chính sách timeout/cancel rõ ràng.
3. Gọi hook `stop/close` của các plugin và những resource thuộc quyền sở hữu của chúng.
4. Dừng thread, executor, timer, listener, callback, watcher; xóa registry/static cache tham chiếu plugin.
5. Khôi phục TCCL cho thread pool và bỏ mọi reference tới instance, `Class<?>`, `Method`, `ClassLoader` hoặc object từ dependency group.
6. Đóng loader **theo thứ tự con → cha** và bỏ tham chiếu tới loader cũ.
7. Chỉ kết luận leak/unload dựa trên heap/classloading evidence thực tế; GC và class unloading không có cam kết xảy ra tức thì.

**Đối với group:** không đóng/loại bỏ `GroupDepsLoader` khi một child plugin khác vẫn đang sử dụng class của nó. Muốn nâng `lib-json-2` lên `lib-json-3` cho cả nhóm, thường tạo **group loader mới**, tạo các plugin loaders mới, khởi động/validate chúng, chuyển traffic và sau đó giải phóng **toàn bộ** thế hệ group cũ.

### 10.3. Không hot-swap thư viện chỉ nhờ sửa JAR trên đĩa

Khi class đã được định nghĩa, sửa JAR file không khiến class đó đổi bytecode. `ServiceLoader.reload()` chỉ reset provider cache của **đối tượng ServiceLoader**, không tự thay JAR URLs/class loader hoặc lifecycle. Để nạp một phiên bản thực sự khác với cùng binary names, thường cần một **defining loader mới** (hoặc cơ chế instrumentation có giới hạn riêng, ngoài phạm vi kiến trúc plugin thông thường).

Đừng đóng loader cũ khi có thread khác đang load class từ loader ấy; API `URLClassLoader.close()` không bảo đảm kết quả khi nó chạy đồng thời với việc load class.

## 11. Cấu hình build và kiểm thử trước khi triển khai

### 11.1. Khóa phiên bản và kiểm tra dependency graph

Trước khi xây loader, cần biết **đúng JAR nào** được đưa vào từng loader:

- Liệt kê transitive dependencies của plugin, kiểm tra duplicate class và conflict theo **binary names**, không chỉ tên Maven artifact.
- Ghim version của shared dependencies mỗi group và xây compatibility matrix giữa plugin A/B/C với version group.
- Không để dependency private bị “leak” sang parent/application class path vì parent-first sẽ khiến plugin không chọn được version riêng.
- Đặt common API ở parent, compile/test nhiều phiên bản plugin với API tối thiểu được hỗ trợ.
- Kiểm tra resource/service files, native libraries, log binding, XML parser, bytecode tooling, plugin shading/relocation.

**Shading/relocation** là một chiến lược khác: đổi package/binary names của thư viện bundled để hai bản có thể tồn tại ngay cả trong cùng defining loader. Nhưng nó ảnh hưởng tới reflection, serialization, resource paths, SPI metadata, native binding và public signatures; phải test kỹ và không coi là giải pháp mặc định.

### 11.2. Test matrix nên bao phủ gì?

| Test | Một loader chung | Per-plugin loader | Group loader |
| --- | --- | --- | --- |
| Hai plugin dùng hai version xung đột | Phải phát hiện và báo incompatibility trước deploy | Chạy đồng thời nếu không lộ type qua API | Phải tách hai group nếu không có version tương thích |
| Type identity | Các class chung có cùng defining loader | Library-private classes khác identity | Cùng nhóm chung identity, khác nhóm thì khác |
| Constructor/static singleton | Chia sẻ cùng runtime class | Khởi tạo riêng mỗi loader | Chia sẻ trong nhóm |
| Lỗi `NoSuchMethodError` khi lệch binary | Đặc biệt cần test xung đột version | Test riêng từng dependency set | Test compatibility toàn nhóm |
| Resource/SPI lookup | Kiểm tra duplicate/merged provider files | Kiểm tra đúng loader/TCCL | Kiểm tra không lộ provider sang plugin thành viên khác |
| Thay version một plugin | Thường thay thế vùng chung | Tạo loader thế hệ mới cho plugin đó | Có thể cần tái lập group nếu đổi shared dependency |
| Dừng/unload | Thực hiện ở scope loader chung | Thử đóng từng plugin riêng | Thử drain cả group trước khi đóng shared deps |
| Memory/cpu | Đo baseline | Đo class count/metaspace per loader | Đo tiết kiệm và shared static resource |

Mỗi test quan trọng nên kiểm tra cả **mã cũ và mới cùng tồn tại tạm thời** trong giai đoạn chuyển traffic: hệ plugin không lỗi chỉ lúc khởi động mà còn khi lifecycle overlap. Đặc biệt, một plugin cũ có thread giữ TCCL là loader của nó có thể khiến redeploy lâu dần tăng Metaspace.

### 11.3. Công cụ chẩn đoán

- `jar tf plugin.jar`: xem class và `META-INF/services` có trong JAR.
- `javap -classpath ... -p com.acme.Type`: đối chiếu method/field signatures lúc build.
- `jdeps ...`: hỗ trợ kiểm tra phụ thuộc JAR/module.
- `java -Xlog:class+load=info ...`: quan sát nguồn class loading trên JVM hỗ trợ unified logging.
- `jcmd <pid> VM.classloaders` hoặc các diagnostic commands phù hợp JDK: quan sát cây loader và số class trong môi trường đang chạy; một số option/tool thay đổi theo JVM.
- Heap dump/profiler: tìm reference giữ loader cũ, `Thread.contextClassLoader`, listener, static map, singleton và plugin instance.

Đo class identity trực tiếp trong code chẩn đoán (đoạn **minh họa**, cần biến `obj` đã có):

~~~java
Class<?> type = obj.getClass();
System.out.println("name=" + type.getName());
System.out.println("definingLoader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

`toString()` của loader và thông tin `CodeSource` có thể tùy implementation; đừng dùng tên hiển thị của loader làm khóa định danh vĩnh viễn. Nếu có thể, cấu hình **plugin ID + plugin version + generation ID + loader identity** trong log/metrics để phân tích lỗi release.

## 12. Chọn kiến trúc từ yêu cầu thật

### Trường hợp 1: một ứng dụng nội bộ với vài plugin do một đội phát triển

Plugin được build trong cùng pipeline, dependencies được quản lý bằng một BOM hoặc dependency constraints và phát hành cùng host. **Một loader chung** là phương án dễ quản trị. Khi phát hiện yêu cầu hai version cùng tên class, cân nhắc thống nhất version hoặc cô lập plugin trước khi đi xa hơn.

### Trường hợp 2: marketplace nạp JAR của nhiều nhà cung cấp

Các nhà cung cấp phát hành độc lập, có thể dùng logging/JSON/HTTP libraries ở versions khác nhau. **Loader riêng cho từng plugin** thường hợp lý; contract của marketplace ở parent, các thư viện private không lộ qua API. Cần catalog plugin, signature/trust policy, host API compatibility, health-check, quota thực thi nếu dùng process isolation và lifecycle rõ.

### Trường hợp 3: hàng chục plugin thuộc vài “bộ sản phẩm”

Bốn plugin báo cáo dùng cùng bộ thư viện lớn v2, bảy plugin phân tích dùng thư viện v3, một plugin đặc biệt cần v1. **Group deps loaders** có thể giảm nhân bản class trong mỗi cohort; quản lý version như **group release unit**. Nếu một plugin trong nhóm muốn upgrade làm thay đổi public ABI không tương thích, tách nhóm hoặc upgrade toàn bộ cohort.

### Trường hợp 4: plugin có chứa mã không tin cậy hoặc yêu cầu giới hạn lỗi cứng

**Không chọn dựa riêng vào class loader**. Chạy plugin trong process/container riêng với kiểm soát OS, tài nguyên, giao thức giao tiếp, timeout và chính sách dữ liệu; các mô hình loader chỉ giải quyết class organization bên trong từng JVM.

### Cây quyết định thực dụng

~~~text
Các plugin có cần cùng binary name nhưng khác version không?
├─ Không
│  └─ Plugin có release/lifecycle riêng đáng kể không?
│     ├─ Không → Một loader chung thường đủ
│     └─ Có   → Per-plugin loader hoặc nhóm nếu dependency chung có lợi
└─ Có
   └─ Có phân thành các nhóm version tương thích ổn định không?
      ├─ Không → Per-plugin loader
      └─ Có   → Group dependency loader + child loaders
                 (ghi rõ version, ownership, upgrade strategy)
~~~

Quyết định sau cùng phải được thử bằng **dependency compatibility, class identity, lifecycle và đo tài nguyên**, không chỉ sơ đồ đẹp.

## 13. Các lỗi thiết kế phổ biến

### 13.1. Đặt cùng API vào nhiều loader rồi cast qua ranh giới

Biểu hiện thường là `ClassCastException` trong khi log in tên class giống hệt. **Kiểm tra defining loader** của interface host và implementation plugin; chuyển shared API lên parent và giữ đúng version contract. Không giải bằng ép kiểu thô hoặc reflection nếu ranh giới type vẫn sai.

### 13.2. Nạp dependency private ở application class path

Với parent-first, private dependency trong plugin không thể thắng class cùng tên đã nằm trong parent. Bản vá đúng thường là sửa **deployment class path/loader placement**, không phải đổi thứ tự URL ở child nếu parent đã định nghĩa class.

### 13.3. “Dùng nhóm để chia sẻ tất cả”

Nếu group chứa một thư viện stateful, các plugin có thể dùng chung cache, singleton và thread pool theo cách ngoài dự tính. Group chỉ nên chia sẻ dependency đã kiểm chứng tương thích cả **API lẫn hành vi runtime**, có chủ sở hữu cấu hình/tài nguyên rõ ràng.

### 13.4. Mỗi plugin có loader riêng nên nghĩ rằng có thể truyền object bất kỳ

Một object của `com.vendor.dto.Record` do A định nghĩa không trở thành type B đang dùng. Khi cần trao đổi dữ liệu, hãy dùng DTO host-owned, Java primitive/collection với element types thuộc API chung, hoặc payload serialized có schema. Với `List<SomePrivateType>`, generics bị type erasure nhưng các element vẫn có class identity riêng; không thể coi đó là cầu nối an toàn.

### 13.5. Lẫn lộn ServiceLoader discovery với dependency isolation

`ServiceLoader.load(service, loader)` chỉ tìm provider theo phạm vi class/module/resource của loader. Nó không tự dựng một loader per-plugin, không tự nhóm version và không tự dừng provider cũ khi `reload()`. Cần plugin registry và lifecycle manager độc lập.

### 13.6. Quên dọn thread và callback, dẫn đến “unload không được”

Đã gọi `URLClassLoader.close()` mà heap vẫn tăng không chứng minh JVM lỗi. Tìm references còn giữ loader: thread TCCL, registered callback, scheduled task, static registry của host, outstanding `Method`/`Class<?>`, object trong cache. Đặc biệt với group deps, chỉ cần một plugin child còn sống là group có thể vẫn cần tồn tại.

### 13.7. Đánh đồng JPMS với sandbox

JPMS giúp thiết lập module readability/encapsulation và service binding; class loader giúp tổ chức phạm vi class. Chúng **không** cô lập CPU, heap, network/file access hay JVM crash đối với mã độc. Chọn security boundary ở cấp process/OS khi bài toán yêu cầu.

## 14. Checklist hoàn thành khi xây plugin platform

Trước khi đưa một kiến trúc vào production, cần trả lời được:

1. **Ranh giới:** class nào thuộc host API, class nào thuộc plugin, class nào thuộc group?
2. **Phiên bản:** mỗi group/plugin cho phép một hay nhiều version của cùng binary name? Maven/Gradle dependency tree có được khóa nhất quán không?
3. **Identity:** API, DTO, annotation/exception class được chia sẻ từ cùng defining loader chưa?
4. **Discovery:** SPI metadata, resource paths và TCCL có lộ provider sai phạm vi không?
5. **Lifecycle:** plugin start/stop, refresh, drain request, executor shutdown, close loader và release reference được thực hiện bởi ai?
6. **Concurrency:** có race giữa load/discovery/release, request đang chạy và update generation không?
7. **Memory:** đã đo metaspace, class unloading, heap, JIT và static caches của từng lựa chọn chưa?
8. **Compatibility:** thử thiếu dependency, lệch API version, `NoSuchMethodError`, `ClassCastException`, nhóm bị phân tách version chưa?
9. **Observability:** log có plugin ID, generation, dependency group và loader identity để truy tìm lỗi không?
10. **Trust:** mã plugin có tin cậy không, và nếu không tin cậy đã dùng ranh giới process/container chưa?

Nếu chỉ có một điểm phải nhớ, đó là: **đặt class vào loader nào chính là quyết định class nào được chia sẻ, version nào có thể cùng tồn tại và đơn vị nào phải được nâng cấp/giải phóng cùng nhau**. Một loader chung dễ vận hành nhưng dùng một vùng version; loader/plugin cô lập version tốt nhưng nhân bản class; group loaders chia sẻ có kiểm soát nhưng gắn các thành viên vào cùng vòng đời dependency.

## 15. Tài liệu tham khảo chuẩn (Java SE 17)

- `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `URLClassLoader` (constructor, parent delegation, `close()`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- `Class` (`getClassLoader()`, identity): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- `ServiceLoader` và lựa chọn loader/layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `ModuleLayer` (`defineModulesWithOneLoader`/`ManyLoaders`/`defineModules`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- The Java Virtual Machine Specification SE 17, chương 5 “Loading, Linking, and Initializing”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
