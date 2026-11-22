# Giao tiếp qua interface, DTO và exception có định danh thống nhất trong kiến trúc plugin

## 1. Bài toán cốt lõi: plugin chạy độc lập nhưng phải hiểu cùng hợp đồng

Kiến trúc plugin thường có **host application** và nhiều **plugin class loaders**. Host muốn gọi một plugin mà không biết trước implementation cụ thể; plugin muốn dùng thư viện riêng, có thể khác phiên bản với plugin khác. Điều này đặt ra hai yêu cầu tưởng như đối lập:

- **Cô lập:** class triển khai và dependency private của plugin A không bị trộn với class tương ứng của plugin B.
- **Giao tiếp được:** host và mọi plugin phải hiểu thống nhất các kiểu đi qua API boundary: interface, data-transfer objects (DTO), exceptions và các kiểu lồng trong chữ ký.

Trong JVM, kiểu runtime không chỉ được nhận diện theo tên như `api.Request`. **Định danh runtime class/interface là cặp (binary name, defining class loader)**. Nếu host dùng `api.Request` do loader H định nghĩa, còn plugin dùng một bản `api.Request` do loader P định nghĩa, đó là **hai kiểu khác nhau**, dù source/bytecode và tên package giống hệt.

**Nguyên tắc thiết kế: chia sẻ kiểu hợp đồng, cô lập kiểu triển khai.**

```text
            Host / Shared API loader (H)
            ├── api.Plugin              [H]
            ├── api.Request             [H]
            ├── api.Result              [H]
            └── api.PluginFailure       [H]
                     |
          +----------+-----------+
          |                      |
   Plugin loader A (A)     Plugin loader B (B)
   ├── plugin.Worker [A]   ├── plugin.Worker [B]
   └── impl.Formatter [A]  └── impl.Formatter [B]

   plugin.Worker [A] != plugin.Worker [B]
   api.Request nhìn từ A == api.Request nhìn từ H
   api.Request nhìn từ B == api.Request nhìn từ H
```

Ở mô hình này, host nhận được object đúng interface, trao đổi DTO cùng runtime identity và bắt được checked exception đúng loại. Plugin vẫn được quyền dùng `impl.Formatter` của riêng mình.

Bài này giải thích **lý do**, **thiết kế loader graph**, **cách định nghĩa API**, **ví dụ Java 17 nhiều file chạy được**, **các lỗi thường gặp** và **kiểm thử identity/binary compatibility**.

## 2. Phân biệt binary name, defining loader và initiating loader

Một class Java như:

```java
package api;
public record Request(String text) {}
```

có **binary name** `api.Request`. Nếu class được loader H định nghĩa, runtime identity là `("api.Request", H)`.

Nếu loader A không tự định nghĩa `api.Request` mà ủy quyền tới H, `loaderA.loadClass("api.Request")` có thể trả cùng đối tượng `Class<?>` với `Request.class` ở host.

Nếu loader A dùng child-first và tự định nghĩa một bản copy `api.Request`, runtime có thể tồn tại hai class:

```text
("api.Request", H) != ("api.Request", A)
```

Không thể “hợp nhất” hai loại trên chỉ bằng cách cast, đổi tên loader, cho chúng cùng source code, hoặc copy cùng JAR. Java runtime type identity gắn với **defining loader**, không gắn với đường dẫn file hay hash của bytecode.

Phân biệt:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Binary name** | `api.Request`, `api.Plugin`, `plugin.Worker` |
| **Defining loader** | Loader thực sự định nghĩa runtime class; `clazz.getClassLoader()` trả thông tin này với ordinary classes |
| **Initiating loader** | Loader được JVM ghi nhận đã khởi xướng nạp/resolve class, có thể nhận class do parent định nghĩa |
| **Parent loader** | Loader được một loader con hỏi trước trong `loadClass` mặc định |
| **Runtime type identity** | Binary name kết hợp defining loader |
| **Loading constraint** | Quy tắc JVM đòi cùng tên kiểu trong một số chữ ký liên kết qua loaders phải resolve tới **cùng runtime class** |

Hai class loader objects có thể có cùng `getName()` nhưng vẫn khác nhau. Tên loader chỉ phục vụ chẩn đoán. Khi kiểm tra định danh thật, so sánh `Class<?>` bằng `==` hoặc kiểm tra đối tượng defining loader.

### Class<?> khác với tên class

`clazzA.getName().equals(clazzB.getName())` có thể là `true` nhưng `clazzA == clazzB` là `false`. Trong plugin architecture, kiểm tra tên thôi không đủ để chứng minh host và plugin dùng chung API.

Khi cần kiểm tra:

```java
System.out.println(hostType == pluginViewType);
System.out.println(hostType.getClassLoader()
        == pluginViewType.getClassLoader());
```

Đây là **snippet minh họa**, yêu cầu hai biến `Class<?>` có thật. So sánh defining loader là một tín hiệu, còn so sánh `Class<?>` bằng `==` trực tiếp xác nhận cùng runtime class.

## 3. Chữ ký giao tiếp phải được thiết kế ở shared loader

Giả sử host công bố:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

Đây là hợp đồng lý tưởng để **một** loader chung định nghĩa. Host và plugin phải thống nhất:

1. `api.Plugin` — interface để host có thể cast implementation và gọi method.
2. `api.Request` — kiểu dữ liệu tham số host gửi vào.
3. `api.Result` — kiểu trả về plugin gửi lại.
4. `api.PluginFailure` — exception host muốn bắt theo class cụ thể.

Nếu mỗi plugin tự đóng gói một bản API và định nghĩa nó trong loader riêng, các vấn đề có thể xuất hiện ở nhiều bước:

- Plugin implementation có thể không còn `instanceof Plugin` theo `Plugin.class` của host.
- Cast từ implementation sang `api.Plugin` của host có thể ném `ClassCastException`.
- JVM có thể ném `LinkageError` do **loading constraint violation** khi liên kết method/field descriptors bắt buộc phải dùng cùng runtime reference type.
- Một `catch (PluginFailure e)` của host không bắt được một exception class cùng binary name nhưng do loader khác định nghĩa nếu nó không phải subtype của đúng runtime `PluginFailure` host biết.
- DTO copy ở hai loaders không thể trao đổi trực tiếp như cùng Java type; serialization/deserialization cũng có thể chọn sai loader khi tái tạo object.

**Không phải hai class trùng tên ở hai loaders luôn là lỗi.** Việc tách hai bản `impl.Formatter` hoặc `plugin.Worker` có thể hoàn toàn đúng. Rủi ro phát sinh khi những runtime types **phải dùng chung** theo hợp đồng lại bị định nghĩa trùng.

## 4. Lựa chọn kiểu nào được phép qua boundary

Bảng hướng dẫn thiết kế:

| Loại dữ liệu | Chính sách khuyến nghị | Lý do |
|---|---|---|
| `api.Plugin` hoặc shared SPI | Một định nghĩa trong shared API loader | Host và plugin có cùng interface identity |
| `api.Request` / `api.Result` | Shared API loader | DTO qua lại không bị khác runtime type |
| `api.PluginFailure` và exception contract | Shared API loader | Host catch đúng exception type; compiler/VM hiểu chữ ký thống nhất |
| `java.lang.String`, primitive, Java core types | JVM built-in loader phù hợp | Các loại nền tảng được dùng chung |
| `impl.Formatter`, plugin-internal services | Plugin loader riêng | Có thể giữ phiên bản/cấu hình khác nhau |
| Loại phụ thuộc version như `thirdparty.Parser` | Plugin loader riêng nếu không xuất hiện ở public API | Cho phép nhiều phiên bản cùng tồn tại |
| `List<Request>` / `Map<String, Result>` | `List`/`Map` từ JDK, còn `Request`/`Result` từ shared API | Generics không xóa yêu cầu identity của phần tử |
| Plugin-specific exception chỉ xử lý nội bộ | Plugin loader, bắt/chuyển thành shared `PluginFailure` tại boundary | Host không cần import private error types |
| DTO serialization schema hoặc JSON | Shared schema/adapter có version contract rõ | Tránh truyền object private; serialization vẫn cần compatibility tests |

Một API tốt thường **nhỏ, ổn định và không có plugin-private dependencies** trong public signatures.

### Record DTO trong Java 17

`record` phù hợp cho dữ liệu bất biến đơn giản:

```java
package api;

public record Request(String text) {}
```

Đây là một **file riêng `Request.java`**. Record tạo accessor `text()`, constructor canonical và equality/hashCode theo thành phần. Nhưng **record không giải quyết classloader identity**: nếu hai loaders định nghĩa hai bản `api.Request` riêng, chúng vẫn là hai runtime classes khác nhau.

Nếu DTO chứa các field là class của plugin, ví dụ `privateparser.Node ast`, thì ngay cả DTO class được chia sẻ cũng mang dependency không ổn định qua boundary. Hãy dùng shared interfaces/records hoặc chuyển sang dữ liệu trung gian có schema xác định.

### Checked exception cũng là một kiểu runtime

`throws PluginFailure` là một phần của Java source method contract và được compiler dùng để buộc xử lý checked exception; JVM method descriptor *không chứa* danh sách `throws`. Class exception vẫn có runtime identity và cần được resolve đúng khi ném/catch.

Vì vậy **không nên** đưa bản copy `api.PluginFailure` vào plugin loader rồi mong `catch (api.PluginFailure)` của host nhận ra qua tên. Một class exception của plugin có thể là subtype của một shared base type, nhưng host phải catch **đúng shared base class** nếu muốn một contract ổn định.

## 5. Parent delegation giúp thống nhất shared API

Một sơ đồ loader đơn giản:

```text
          App/Shared API loader H
          ├── api.Plugin
          ├── api.Request
          ├── api.Result
          └── api.PluginFailure
                    ^
                    |
          +---------+----------+
          |                    |
      Loader A             Loader B
      plugin.*             plugin.*
      impl.*               impl.*
```

Mỗi plugin loader dùng `H` làm parent. `ClassLoader.loadClass` mặc định thường kiểm tra lớp đã được nạp, hỏi parent, sau đó mới gọi `findClass`/đọc bytes riêng khi parent không có class.

Với `api.*`, H trả về class chung. Với `plugin.*` và `impl.*`, H không có, nên A/B tự định nghĩa. Như vậy **parent-first đủ để vừa chia sẻ API vừa cô lập implementation**, nếu classpath của parent không chứa class implementation của plugin.

Cần lưu ý:

- Parent **không phải** superclass Java của class loader object.
- Có cùng parent **không bảo đảm** mọi child-first custom loader đều chia sẻ API; nếu override `loadClass` để tự định nghĩa `api.*`, vẫn có thể nhân bản types.
- `parent == null` ở loader mặc định hướng về bootstrap, **không tự nhìn thấy** API của application loader; chọn parent null cho plugin cần shared API thường đòi cơ chế lookup riêng.
- Trên một application server hay JPMS multi-layer setup, `ClassLoader.getSystemClassLoader()` chưa chắc là loader sở hữu shared API. Nên chọn loader của chính interface chung, ví dụ `Plugin.class.getClassLoader()`, khi phù hợp.
- Nếu shared interface do bootstrap loader định nghĩa, `getClassLoader()` có thể bằng `null`; phải đọc contract API của loader/factory nhận parent để hiểu trường hợp đặc biệt.

### Đừng cô lập API bằng child-first

Nếu cần child-first để nạp `thirdparty.*` riêng, áp dụng **selective child-first** cho package đã xác định. Những package `api.*` được host/plugin cùng dùng phải ưu tiên parent.

Hình mẫu kiến trúc:

```text
loadClass(name):
    if name startsWith "api.":
        use parent-first
    else if name startsWith "thirdparty.":
        try own classes first
        fallback according to explicit policy
    else:
        default parent-first or plugin policy
```

Đây là **pseudocode**, không phải implementation Java đầy đủ. Một override `loadClass` thực tế phải dùng `findLoadedClass`, `getClassLoadingLock(name)` và xử lý đúng `resolveClass`/errors. Không bắt mọi `LinkageError` rồi fallback sang một bản API khác như thể đó là lỗi class not found.

## 6. Demo Java 17 hoàn chỉnh: shared interface, DTO và checked exception

Demo có **hai plugin** nạp qua **hai `URLClassLoader` khác nhau**. Mỗi plugin tự định nghĩa class cùng binary name `plugin.Worker` và `impl.Formatter`, nhưng cả hai ủy quyền `api.*` về application loader.

Kết quả cần quan sát:

1. Host có thể cast cả hai object sang `api.Plugin`.
2. Plugin A/B nhận cùng loại `Request` và trả cùng loại `Result` của host.
3. Host bắt được chính xác `api.PluginFailure` do plugin ném.
4. Hai implementation classes khác identity, private helpers cũng khác identity.
5. Class loader của cả hai plugin trả cùng `Class<?>` cho các loại shared API.

### 6.1. Cấu trúc project

Tạo cây thư mục:

```text
src/
  api/
    Plugin.java
    Request.java
    Result.java
    PluginFailure.java
  plugin-a/
    impl/
      Formatter.java
    plugin/
      Worker.java
  plugin-b/
    impl/
      Formatter.java
    plugin/
      Worker.java
  host/
    PluginHost.java
out/
  api/
  plugin-a/
  plugin-b/
  host/
```

Thư mục `out` sẽ được tạo bởi lệnh biên dịch; không trộn source/output của plugin A và B trong cùng một classpath khi build host.

### 6.2. Shared API — chỉ biên dịch một bản

File `src/api/Plugin.java`:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

File `src/api/Request.java`:

```java
package api;

public record Request(String text) {}
```

File `src/api/Result.java`:

```java
package api;

public record Result(String message) {}
```

File `src/api/PluginFailure.java`:

```java
package api;

public class PluginFailure extends Exception {
    public PluginFailure(String message) {
        super(message);
    }
}
```

Các file này là **bốn source files độc lập**. `Request`/`Result` là records Java 17, `PluginFailure` là checked exception vì kế thừa `Exception`. Tất cả phải được loader chung H định nghĩa một lần.

### 6.3. Plugin A — private Formatter phiên bản A

File `src/plugin-a/impl/Formatter.java`:

```java
package impl;

public final class Formatter {
    public String format(String input) {
        return "A:" + input;
    }
}
```

File `src/plugin-a/plugin/Worker.java`:

```java
package plugin;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import impl.Formatter;

public final class Worker implements Plugin {
    @Override
    public Result handle(Request request) throws PluginFailure {
        if (request.text().isBlank()) {
            throw new PluginFailure("blank");
        }
        return new Result(new Formatter().format(request.text()));
    }
}
```

`Formatter` là implementation detail. Không được đặt kiểu `impl.Formatter` trong chữ ký `api.Plugin.handle`.

### 6.4. Plugin B — cùng binary names, behavior khác

File `src/plugin-b/impl/Formatter.java`:

```java
package impl;

public final class Formatter {
    public String format(String input) {
        return "B:" + input;
    }
}
```

File `src/plugin-b/plugin/Worker.java`:

```java
package plugin;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import impl.Formatter;

public final class Worker implements Plugin {
    @Override
    public Result handle(Request request) throws PluginFailure {
        if (request.text().isBlank()) {
            throw new PluginFailure("blank");
        }
        return new Result(new Formatter().format(request.text()));
    }
}
```

Plugin A/B có cùng binary name cho `plugin.Worker` và `impl.Formatter`; nhưng class bytes của `Formatter` được lưu trong output directories riêng. Mỗi plugin loader sẽ định nghĩa một bản runtime độc lập.

### 6.5. Host — tải và gọi plugin bằng shared types

File `src/host/PluginHost.java`:

```java
package host;

import api.Plugin;
import api.PluginFailure;
import api.Request;
import api.Result;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    private static URL url(String directory) throws Exception {
        return Path.of(directory).toUri().toURL();
    }

    private static Plugin create(URLClassLoader loader)
            throws Exception {
        Class<?> implementation =
                Class.forName("plugin.Worker", true, loader);
        Object instance =
                implementation.getDeclaredConstructor().newInstance();
        return (Plugin) instance;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader apiLoader = Plugin.class.getClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                     "plugin-A",
                     new URL[] { url("out/plugin-a") },
                     apiLoader);
             URLClassLoader loaderB = new URLClassLoader(
                     "plugin-B",
                     new URL[] { url("out/plugin-b") },
                     apiLoader)) {

            Plugin pluginA = create(loaderA);
            Plugin pluginB = create(loaderB);

            Request request = new Request("hello");
            Result answerA = pluginA.handle(request);
            Result answerB = pluginB.handle(request);

            System.out.println("A result: " + answerA.message());
            System.out.println("B result: " + answerB.message());

            Class<?> workerA = pluginA.getClass();
            Class<?> workerB = pluginB.getClass();
            Class<?> formatterA = loaderA.loadClass("impl.Formatter");
            Class<?> formatterB = loaderB.loadClass("impl.Formatter");

            System.out.println("Worker identity differs: "
                    + (workerA != workerB));
            System.out.println("Formatter identity differs: "
                    + (formatterA != formatterB));

            System.out.println("Both implement shared Plugin: "
                    + (pluginA instanceof Plugin
                    && pluginB instanceof Plugin));

            boolean sharedApi =
                    loaderA.loadClass("api.Plugin") == Plugin.class
                    && loaderB.loadClass("api.Plugin") == Plugin.class
                    && loaderA.loadClass("api.Request") == Request.class
                    && loaderB.loadClass("api.Request") == Request.class
                    && loaderA.loadClass("api.Result") == Result.class
                    && loaderB.loadClass("api.Result") == Result.class
                    && loaderA.loadClass("api.PluginFailure")
                            == PluginFailure.class
                    && loaderB.loadClass("api.PluginFailure")
                            == PluginFailure.class;

            System.out.println("All shared API identities match: "
                    + sharedApi);

            System.out.println("Request defining loader shared: "
                    + (Request.class.getClassLoader() == apiLoader));

            try {
                pluginA.handle(new Request(""));
            } catch (PluginFailure expected) {
                System.out.println("Caught from A: "
                        + expected.getMessage());
                System.out.println("A failure class shared: "
                        + (expected.getClass() == PluginFailure.class));
            }

            try {
                pluginB.handle(new Request(""));
            } catch (PluginFailure expected) {
                System.out.println("B failure class shared: "
                        + (expected.getClass() == PluginFailure.class));
            }
        }
    }
}
```

`URLClassLoader(String name, URL[] urls, ClassLoader parent)` có từ Java 9 nên hợp lệ trên Java 17. Loader A/B dùng **cùng** `apiLoader` làm parent; mỗi loader có URLs riêng.

Lưu ý:

- `Class.forName("plugin.Worker", true, loader)` yêu cầu lookup qua loader plugin được chọn và initialization theo API.
- `getDeclaredConstructor().newInstance()` tạo implementation object qua public implicit no-arg constructor.
- `(Plugin) instance` cast hợp lệ vì `api.Plugin` luôn được parent định nghĩa.
- `Result` do `plugin.Worker` tạo là đúng `api.Result` shared type, nên host gọi `message()` mà không cần reflection/serialization trung gian.
- `PluginFailure` do implementation ném là đúng exception class của host. `catch (PluginFailure)` bắt được từ cả hai plugin.
- `getClass().getClassLoader()` của implementation là loader plugin, trong khi `Request.class.getClassLoader()` là loader chung.
- `try-with-resources` đóng hai `URLClassLoader` sau khi dùng; đóng loader **không tức thì unload** class hay tiêu hủy các object có reference còn sống.

### 6.6. Biên dịch và chạy

Với Bash trên Linux/macOS, chạy tại thư mục chứa `src`:

```bash
mkdir -p out/api out/plugin-a out/plugin-b out/host

javac -d out/api \
  src/api/Plugin.java \
  src/api/Request.java \
  src/api/Result.java \
  src/api/PluginFailure.java

javac -cp out/api -d out/plugin-a \
  src/plugin-a/impl/Formatter.java \
  src/plugin-a/plugin/Worker.java

javac -cp out/api -d out/plugin-b \
  src/plugin-b/impl/Formatter.java \
  src/plugin-b/plugin/Worker.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api:out/host" host.PluginHost
```

Trên Windows PowerShell (class path separator là dấu `;`):

```powershell
New-Item -ItemType Directory -Force out/api,out/plugin-a,out/plugin-b,out/host

javac -d out/api src/api/Plugin.java src/api/Request.java src/api/Result.java src/api/PluginFailure.java

javac -cp out/api -d out/plugin-a src/plugin-a/impl/Formatter.java src/plugin-a/plugin/Worker.java

javac -cp out/api -d out/plugin-b src/plugin-b/impl/Formatter.java src/plugin-b/plugin/Worker.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api;out/host" host.PluginHost
```

**Tuyệt đối không đưa `out/plugin-a` hoặc `out/plugin-b` vào classpath của host ở bước chạy demo.** Nếu parent nhìn thấy `plugin.Worker` hoặc `impl.Formatter`, parent-first delegation có thể trả class của parent trước, làm mất tính cô lập.

### 6.7. Stdout dự kiến trên JDK 17+

Với cấu trúc sạch và không thay classpath đã nêu:

```text
A result: A:hello
B result: B:hello
Worker identity differs: true
Formatter identity differs: true
Both implement shared Plugin: true
All shared API identities match: true
Request defining loader shared: true
Caught from A: blank
A failure class shared: true
B failure class shared: true
```

**Phân tích kết quả:**

1. `A:hello` và `B:hello` chứng minh hai plugin dùng `Formatter` riêng.
2. `workerA != workerB` dù cùng binary name `plugin.Worker` chứng minh class identity khác giữa defining loaders.
3. `formatterA != formatterB` xác nhận private dependency cùng tên cũng được cô lập.
4. Cả hai đều `instanceof Plugin` vì interface `api.Plugin` do **một** parent loader định nghĩa.
5. `sharedApi` so sánh **bốn shared classes** từ góc nhìn của hai loader; kết quả true chứng minh contract identity thống nhất trong demo.
6. `Request.class.getClassLoader() == apiLoader` cho biết defining loader của DTO ở host là loader chung.
7. Hai lệnh `catch (PluginFailure)` từ A và B đều thành công; exception class đúng `PluginFailure.class` của host, không phải một exception copy cùng tên.

**Giới hạn demo:** project chạy trên class path kiểu truyền thống; trong named modules hoặc khi dùng `ModuleLayer`, còn phải xét `requires`, `exports`, `opens` và mapper module-to-loader. Việc cùng loader không tự vượt qua access rules.

## 7. Điều gì xảy ra nếu plugin đóng gói lại API?

Có hai tình huống riêng.

### Tình huống A: Plugin JAR chứa bản copy API nhưng loader vẫn parent-first

Nếu plugin artifact có các class `api.*` nhưng parent loader đã định nghĩa `api.Plugin`, `api.Request`, `api.Result` và `api.PluginFailure`, thuật toán `loadClass` mặc định thường trả class từ parent trước. Bản copy ở child classpath **có thể không được định nghĩa** trong đường lookup đó.

Tuy nhiên đóng gói trùng API vẫn là rủi ro quản lý dependency: một thay đổi delegation, một parent cấu hình sai hoặc một plugin loader child-first có thể làm bản copy trở thành runtime class khác.

**Cách làm tốt hơn:** build plugin với API dependency ở dạng **compile-only/provided**; đóng gói private implementation dependencies nhưng không bundle lại shared API vào plugin runtime artifact khi không cần.

### Tình huống B: Plugin child-first tự định nghĩa API

Giả sử plugin có bản `api.Plugin` riêng do loader P định nghĩa:

```text
api.Plugin [H] != api.Plugin [P]
```

Class `plugin.Worker` ở P implements `api.Plugin [P]`. Host cầm `api.Plugin [H]` và muốn:

```java
api.Plugin plugin = (api.Plugin) implementation;
```

Đây là snippet minh họa các biến/class đã tồn tại. Nếu `implementation` chỉ implements bản interface P, phép cast không thỏa runtime assignability với H và có thể ném `ClassCastException`.

Kể cả khi methods có cùng tên, descriptor chuỗi giống hệt, JVM **không suy ra cùng runtime interface type**.

Nếu method overriding hoặc cross-loader resolution bắt buộc các tên kiểu như `api.Request` hay `api.Result` phải đồng nhất mà hai loaders lại resolve khác nhau, JVM có thể từ chối liên kết bằng `LinkageError` do **loader constraint violation**.

**Không phải mọi trường hợp phải đợi tới cast.** Với một số liên kết method/interface hoặc field, lỗi có thể phát sinh ngay trong loading/linking. Không hardcode thời điểm exception cho mọi JVM.

## 8. Loading constraints bảo vệ tính nhất quán chữ ký

Trong JVM, class/interface identity được xác định theo binary name và defining loader. Khi class từ hai loaders tham gia một số quan hệ linking, JVM áp đặt các **loading constraints**.

Xét:

```java
package api;

public interface Plugin {
    Result handle(Request request) throws PluginFailure;
}
```

Method descriptor JVM (không chứa `throws`) là:

```text
(Lapi/Request;)Lapi/Result;
```

Nếu class `plugin.Worker` do loader P định nghĩa implements `api.Plugin` do loader H định nghĩa, JVM cần duy trì tính nhất quán của các kiểu tham chiếu trong descriptor phù hợp với quy tắc linking/preparation, như:

```text
api.Request^P = api.Request^H
api.Result^P  = api.Result^H
```

Đây là ký hiệu khái niệm cho yêu cầu resolve cùng runtime class, không phải biểu thức Java. Dùng parent delegation cho `api.*` khiến P và H nhìn thấy cùng runtime class và đáp ứng constraint.

**Quan trọng về exceptions:** `throws PluginFailure` được biểu diễn trong `Exceptions` attribute của method/class metadata, **không phải trong method descriptor**. Vì vậy **không khẳng định JVM áp đặt loading constraint cho `api.PluginFailure` chỉ vì nó xuất hiện trong `throws`**. Tuy vậy, nếu host cần catch chính xác exception type, identity của `PluginFailure` vẫn phải thống nhất qua shared loader. Những symbolic references khác tới exception type cũng có thể có quy tắc linking riêng.

### Generic không tự cứu được runtime identity

Ví dụ:

```java
List<Request> handleAll(List<Request> requests);
```

Mã trên là snippet method declaration cần `import java.util.List`. Ở bytecode, kiểu generic arguments bị erasure; descriptor thông thường là:

```text
(Ljava/util/List;)Ljava/util/List;
```

`Request` có thể nằm trong generic `Signature` metadata chứ không nằm trực tiếp trong descriptor ở đây. Điều đó **không làm hai `Request` ở hai defining loaders trở thành cùng type**. Khi truy xuất phần tử, compiler có thể chèn `checkcast` theo expected runtime class; một bản DTO khác loader có thể gây `ClassCastException`.

Đừng coi generic type parameters là kênh chuyển object an toàn giữa hai không gian loader riêng.

## 9. Exception identity và chiến lược xử lý lỗi plugin

### 9.1. Chia sẻ exception contract

Host thường cần catch và xử lý lỗi domain:

```java
try {
    Result result = plugin.handle(request);
} catch (PluginFailure error) {
    // Ghi log, trả kết quả nghiệp vụ, retry theo policy.
}
```

Đoạn minh họa cần `plugin` và `request` đúng shared types. Việc host catch chính xác `PluginFailure` hoạt động khi plugin ném **chính runtime `api.PluginFailure`** hoặc subclass hợp lệ của nó.

Trong demo phần 6, cả plugin A/B gọi:

```java
throw new PluginFailure("blank");
```

Tên `PluginFailure` được import từ package `api` và parent loader cung cấp cùng class host biết.

### 9.2. Private exception nên được chuyển tại boundary

Plugin có thể phụ thuộc một thư viện riêng ném `vendor.ParseException` hoặc `impl.InternalFault`. Host không nên phải import private exception class mà plugin loader sở hữu. Một adapter ở plugin boundary:

```java
@Override
public Result handle(Request request) throws PluginFailure {
    try {
        return executeInternal(request);
    } catch (VendorParseException error) {
        throw new PluginFailure("Input format is invalid");
    }
}
```

Đây là **pseudocode gần Java**: muốn biên dịch cần các method `executeInternal` và class `VendorParseException` được khai báo, cùng shared `Result`/`Request`/`PluginFailure`. Nếu yêu cầu giữ cause thì thiết kế shared `PluginFailure` có constructor `(String, Throwable)`, nhưng chú ý cause có thể mang private exception object/class tới host.

Một chính sách production thường gồm:

- Phân loại lỗi theo shared error codes hoặc shared exception hierarchy nhỏ.
- Không rò class implementation/private-library trong public signature.
- Giữ thông tin nguyên nhân trong logs theo chính sách dữ liệu/riêng tư, tránh expose toàn bộ stack trace hoặc secrets tới plugin khác.
- Phân biệt checked business failure với fatal runtime failures; đừng bắt mọi `Throwable` rồi giấu `OutOfMemoryError`/`ThreadDeath` như một lỗi nghiệp vụ bình thường.

### 9.3. Catch cùng tên nhưng khác loader không tương đương

Giả sử host định nghĩa `api.PluginFailure [H]`, plugin P tự định nghĩa `api.PluginFailure [P]`. Hai class này cùng extends `Exception` nhưng **không có quan hệ kế thừa** với nhau. Câu lệnh `catch (api.PluginFailure)` ở host chỉ bắt những `Throwable` assignable sang **host runtime class H**.

Nếu muốn host xử lý một private exception, cần một **shared supertype** hoặc chuyển nó thành shared exception/DTO tại plugin adapter boundary; không dựa vào `getName()`.

## 10. DTO compatibility: cùng runtime class chưa đủ cho tiến hóa API

Việc thống nhất defining loader xử lý **runtime type identity**, nhưng **không tự bảo đảm binary/source compatibility** giữa host và plugin versions.

Ví dụ host API v2 đổi record:

```java
public record Request(String text, int timeout) {}
```

Nếu plugin được biên dịch theo v1 `Request(String text)` nhưng runtime host chỉ có v2, lời gọi constructor/signature/method phù hợp có thể thay đổi, gây `NoSuchMethodError` hoặc lỗi liên kết khác. Dù runtime chỉ có **một** `api.Request` do H định nghĩa, bản thân public ABI đã thay đổi không tương thích.

Quy tắc thiết kế:

1. Version shared API độc lập với plugin implementation version.
2. Đặt nguyên tắc compatibility rõ: những thay đổi constructor, record components, interface methods, exception contracts phải được xét trước khi phát hành.
3. Cân nhắc factory methods, builders hoặc DTO envelopes có version field nếu cần tiến hóa schema.
4. Kiểm thử plugin biên dịch với API cũ chạy trên host mới trong phạm vi compatibility được cam kết.
5. Tránh để `vendor.*`, `impl.*` xuất hiện trong public fields, method parameters/returns, exception contract và serialized forms.
6. Nếu DTO đi qua process/JVM khác, classloader identity không còn là cơ chế truyền object; cần serialization schema/protocol có versioning.

### Record không luôn là DTO tốt nhất

Records tuyệt vời cho message bất biến trong cùng một JVM khi shared API ổn định; nhưng thay đổi record component list thường làm thay canonical constructor và một số contract. Với API cần backward compatibility kéo dài, có thể phù hợp hơn khi dùng interface, builder-based value object hoặc versioned message schema.

Không nên dùng Java `Serializable` như một giải pháp mặc định để “vượt class loaders”: deserialization vẫn cần chọn loader, kiểm tra type và serial compatibility; đặc biệt phải quản lý an toàn input không tin cậy.

## 11. ServiceLoader và loader của provider

Với classpath SPI, provider JAR ghi `META-INF/services/api.Plugin` chứa tên provider như `plugin.Worker`. Host dùng `ServiceLoader.load(Plugin.class, pluginLoader)` để chọn loader rõ ràng; provider phải assignable sang **chính `Plugin.class` của host**. Bản duplicate SPI do child định nghĩa có thể gây `ServiceConfigurationError: not a subtype`. Overload một tham số dùng TCCL của thread; named modules có cơ chế `uses`/`provides` và `ServiceLoader.load(layer, service)`.

## 12. Trường hợp nhiều class loader: arrays, generics, resources và reflection

### Array của DTO

`Request[]` là reference array type. Nếu `Request` do loader H định nghĩa, array class có defining-loader behavior gắn với component/element type theo JVM. Plugin A/B sử dụng chung `Request` sẽ dùng chung runtime array class tương ứng.

Nếu plugin B định nghĩa bản `Request` riêng, `Request[]` của nó cũng không tương thích với `Request[]` host theo cách Java type system kỳ vọng. Không thể dựa vào array covariance để làm hai component types khác loader trở nên cùng type.

### Generics và bridge methods

`List<Result>` chỉ bảo toàn generic type information theo Java source/reflection metadata ở mức nhất định, còn JVM verifier/casts xử lý runtime types thực tế. Với interface/generic methods được compiler bridge, classloader identity của shared API vẫn phải được thống nhất để đảm bảo method dispatch/linking.

Không tự suy từ generic `Signature` trong class file rằng hai DTO trùng tên giữa loaders là tương thích.

### Tài nguyên và classpath

Class lookup khác với resource lookup:

```java
ClassLoader loader = plugin.getClass().getClassLoader();
java.net.URL resource = loader.getResource("plugin.properties");
```

Snippet minh họa cần biến `plugin`. Nếu plugin dùng private configuration/resource, ưu tiên resource lookup theo **plugin loader** cụ thể. Nếu resource là contract của host, dùng shared API anchor/classloader theo thiết kế.

Service configuration files trong `META-INF/services` cũng là resources; parent delegation/resource lookup và duplicate descriptors cần được kiểm thử.

### Reflection

`Class.forName("plugin.Worker", true, loaderA)` tìm implementation của A, nhưng việc tạo object/cast vẫn phụ thuộc constructor/accessibility và shared interface identity. Nếu dùng `getDeclaredConstructor().newInstance()`, method/constructor access checks và JPMS exports/opens có thể ảnh hưởng khi chuyển sang named modules.

`Class.forName(String)` overload một tham số **không tự dùng TCCL**; nó dùng loader của caller. Do đó plugin discovery bằng reflection nên chỉ rõ loader để tránh tìm bản class của host hoặc plugin khác.

## 13. ClassLoader isolation và giới hạn của nó

Shared API identity không đồng nghĩa resource hay quyền truy cập của plugin được cách ly hoàn toàn. Static state của classes ở parent có thể chia sẻ giữa các plugin; instance/`Class<?>`/thread/TCCL/caches có thể giữ loader cũ reachable sau redeploy. `URLClassLoader.close()` không ép unload. Mã plugin không tin cậy cần process/OS isolation, vì classloader riêng không cấm dùng JDK file/network APIs.

## 14. Chẩn đoán vấn đề ở ranh giới host–plugin

### Lỗi: ClassCastException dù class implements interface cùng tên

Kiểm tra:

1. `hostPluginClass == loaderA.loadClass("api.Plugin")`?
2. `pluginObject.getClass().getInterfaces()` chứa đúng runtime `Plugin.class` chưa?
3. Plugin có tự đóng gói `api.Plugin` và dùng child-first không?
4. Tên class giống nhau nhưng defining loaders có khác nhau không?

**Hướng sửa:** chỉ định nghĩa API trong shared loader, cho plugin delegate package API về parent. Không “cast qua Object” để che lỗi; runtime type vẫn sai.

### Lỗi: LinkageError với thông điệp loader constraint violation

Kiểm tra field/method descriptor ở host/plugin boundary:

```bash
javap -classpath out/api -s -p api.Plugin
javap -classpath out/plugin-a -p plugin.Worker
```

Ví dụ demo, `Plugin.handle` có descriptor:

```text
(Lapi/Request;)Lapi/Result;
```

Nếu plugin resolver thấy hai bản `api.Request`/`api.Result` từ hai defining loaders, JVM có thể yêu cầu identity thống nhất do method overriding/linking và báo lỗi.

Sửa bằng module/classloader architecture, không đơn giản bằng thay tên source file. Với Java 17 HotSpot có thể dùng class loading log để xác định nguồn class:

```bash
java -Xlog:class+load=info -cp "out/api:out/host" host.PluginHost
```

Log có thể rất dài và format phụ thuộc JVM. Cần kết hợp `Class.getClassLoader()` để xác nhận defining loader.

### Lỗi: catch không bắt được exception plugin

Có thể do:

- Plugin ném private exception không phải subtype của shared `PluginFailure`.
- Plugin tự định nghĩa bản `api.PluginFailure` khác loader.
- Code đã catch nhầm exception family.

**Hướng sửa:** bắt/chuyển đổi lỗi tại adapter boundary thành shared exception (hoặc shared error DTO) và kiểm tra runtime `Class<?>` của exception.

### Lỗi: NoSuchMethodError sau nâng cấp shared API

Một plugin được compile với ABI khác với host API runtime; type identity có thể chung nhưng method descriptor/constructor đã thay đổi. Kiểm tra API version/ABI; không kết luận ngay classloader collision.

### Lỗi: ServiceConfigurationError trong SPI

Provider không assignable với shared service interface, thiếu public provider constructor hoặc cấu hình `META-INF/services` sai. Kiểm tra cả loader dùng để tìm provider và loader định nghĩa interface.

### Lỗi: ClassNotFoundException với shared DTO

Parent loader không thấy API class, plugin loader parent-null không có đường tìm shared types, hoặc runtime thiếu JAR. Kiểm tra build artifacts, classpath/module path, parent delegation và tên binary.

### Lỗi: Works locally, fails in application server

Trong container, `getSystemClassLoader()` chưa chắc là owner của shared API; TCCL có thể là loader của deployment/worker khác. Hãy dùng anchor `Plugin.class.getClassLoader()` hoặc factory/registry cung cấp loader đúng, sau đó kiểm tra cả module access nếu JPMS được dùng.

## 15. Checklist thiết kế và kiểm thử

Trước khi phát hành một plugin, xác nhận:

1. **API boundary rõ ràng:** mọi interface/DTO/checked exception chính đều nằm trong shared API artifact.
2. **Một defining loader cho shared types:** host và tất cả plugin resolve `api.*` qua cùng loader.
3. **Không bundle API không cần thiết:** plugin compile against shared API nhưng không tự định nghĩa duplicate API classes.
4. **Private implementations riêng:** plugin-specific code và versioned dependencies được sở hữu bởi plugin loader.
5. **Không lộ private types:** public method parameters/returns, public fields và exception contract không dùng plugin-private classes.
6. **Binary compatibility:** version host API và plugin build được kiểm tra; generic changes, record component changes, default methods và constructors được đánh giá.
7. **Exception contract:** host bắt chính xác shared exception hoặc chung base type; nội bộ plugin có adapter chuyển lỗi.
8. **SPI đúng loader:** plugin providers dùng chung service interface identity, có service descriptor/module provider declaration đúng.
9. **Concurrency:** class loader custom override `loadClass` phải tránh define cùng tên hai lần; dùng cơ chế khóa theo tên thích hợp.
10. **Lifecycle:** plugin shutdown hooks, thread locals, TCCL, listeners, caches, URLs được dọn.
11. **Quan sát:** log loader name và defining loader identity, module, classpath roots, nhưng không ghi secrets hoặc object payload nhạy cảm.
12. **Test chéo phiên bản:** chạy plugin A/B song song và cùng DTO/exception handling để bảo vệ shared boundary.

Một bài test integration mạnh không chỉ assert `a.handle(...)` đúng nội dung; hãy assert thêm:

```java
assert loaderA.loadClass("api.Plugin") == Plugin.class;
assert loaderB.loadClass("api.Request") == Request.class;
assert pluginA.getClass() != pluginB.getClass();
```

Đây là **snippet assertions**, không phải class chạy độc lập. Java `assert` mặc định **bị tắt** trừ khi chạy với `-ea`; trong test suite hãy dùng assertions của framework hoặc bật `-ea`. Code demo ở phần 6 dùng `System.out.println` để quan sát dù không bật assertion.

## 16. Các ngộ nhận thường gặp

| Nhận định sai | Điều đúng |
|---|---|
| “Chung package/tên là chung interface.” | Runtime identity còn phụ thuộc defining loader. |
| “Plugin và host phải dùng chung toàn bộ thư viện.” | Chỉ cần chia sẻ contract types; private dependencies có thể khác phiên bản. |
| “Cùng source code DTO thì cast được giữa loaders.” | Không nếu defining loaders khác nhau. |
| “Tạo hai loader có cùng parent là tự động an toàn.” | Child-first có thể định nghĩa duplicate API; phải xem lookup policy. |
| “Class loader name khác nhau là định danh class khác nhau.” | Tên chỉ để chẩn đoán; defining loader object quyết định identity. |
| “Exception cùng tên sẽ bị catch đúng.” | Catch kiểm tra runtime exception type/subtype, không chỉ class name. |
| “`throws` nằm trong JVM method descriptor.” | `throws` được ghi ở metadata `Exceptions`, không trong descriptor tham số/trả về. |
| “Generic `List<Request>` bảo đảm mọi phần tử đúng identity.” | Erasure không hợp nhất hai `Request` runtime classes. |
| “Record tự giải quyết version compatibility.” | Thay đổi record components/constructors có thể phá ABI/schema. |
| “Cứ dùng child-first mọi package để cô lập tốt nhất.” | Có thể tạo duplicate shared API và lỗi linkage. |
| “`URLClassLoader.close()` ngay lập tức unload plugin.” | Close không tự xóa mọi references hoặc classes. |
| “Cùng interface name đảm bảo ServiceLoader nhận provider.” | Provider phải assignable sang đúng shared service `Class<?>`. |

## 17. Bài tập tự kiểm tra

**Câu 1.** Loader A/B cùng định nghĩa `impl.Formatter` nhưng đều delegate `api.Plugin` về parent H. Điều đó có hợp lệ không?

**Đáp án:** Có. Private implementation khác defining loader có thể cùng tên, còn shared interface được giữ một runtime identity chung.

**Câu 2.** Hai class `api.Request` có cùng binary name và bytecode nhưng do H/P định nghĩa độc lập. `requestH.getClass() == requestP.getClass()` sẽ là gì?

**Đáp án:** `false`, vì hai runtime class identities khác defining loader.

**Câu 3.** Vì sao host nên định nghĩa `api.PluginFailure`?

**Đáp án:** Host muốn bắt và xử lý lỗi theo một runtime exception type ổn định; plugin phải ném chính shared exception hoặc subtype hợp lệ, không tự định nghĩa bản copy.

**Câu 4.** Method descriptor của `Result handle(Request request) throws PluginFailure` chứa tên kiểu nào?

**Đáp án:** `(Lapi/Request;)Lapi/Result;`. `PluginFailure` trong `throws` không nằm trong method descriptor; nó được lưu qua metadata ngoại lệ.

**Câu 5.** Nếu plugin dùng child-first cho `api.*` và implement bản `api.Plugin` riêng, host cast object plugin sang `Plugin` của H chắc chắn thành công không?

**Đáp án:** Không. Nếu class chỉ implements interface riêng của P, nó không assignable sang `api.Plugin` do H định nghĩa; có thể gặp `ClassCastException` hoặc lỗi linking liên quan.

**Câu 6.** `List<Request>` có tự làm các bản `Request` từ hai loaders tương thích không?

**Đáp án:** Không. Generics erasure không thay runtime class identity; cast hoặc use tại runtime vẫn có thể thất bại.

**Câu 7.** Host có API v2 nhưng plugin compile với API v1 và gọi method đã xóa. Nếu defining loader của shared API chỉ có một, chương trình vẫn có thể lỗi không?

**Đáp án:** Có. `NoSuchMethodError` hoặc lỗi binary compatibility vẫn có thể xảy ra vì ABI không khớp; loader identity chung không bảo đảm mọi version tương thích.

**Câu 8.** Vì sao trong demo `a.getClass() != b.getClass()` nhưng cả hai vẫn `instanceof Plugin`?

**Đáp án:** A/B định nghĩa riêng implementation `plugin.Worker`, nhưng cả hai cùng implement đúng runtime interface `api.Plugin` của parent.

**Câu 9.** `catch (PluginFailure e)` có bắt được một class tên `api.PluginFailure` của loader khác chỉ vì trùng binary name?

**Đáp án:** Không. Cần exception object thuộc đúng runtime class host biết hoặc subclass hợp lệ của nó.

**Câu 10.** Khi hot reload plugin A, có cần tạo lại shared API loader mỗi lần không?

**Đáp án:** Thông thường không. Tạo loader mới cho implementation phiên bản mới, giữ shared API loader ổn định khi contract host vẫn tương thích; dọn references tới plugin cũ để hỗ trợ unloading.

## 18. Tổng kết và tài liệu tham khảo

**Ba nguyên tắc cốt lõi:**

1. **Chung định danh cho contract:** interface, DTO và exception dùng qua host–plugin boundary phải được resolve về **cùng `Class<?>`**.
2. **Khác định danh cho implementation:** class triển khai và private versioned dependencies có thể được loaders riêng định nghĩa để cô lập.
3. **Kiểm tra cả linking, ABI và lifecycle:** parent delegation, Java/JVMS loading constraints, checked exceptions, ServiceLoader, version compatibility và resource cleanup đều là phần của plugin architecture bền vững.

**Nguồn chính thức (Java 17):**

- [JVMS 17 — 5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loaders.
- [JVMS 17 — 5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): yêu cầu nhất quán kiểu giữa loaders.
- [JVMS 17 — 4.3 Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): method descriptor và các reference type names.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation, `findClass`, `loadClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): plugin URL paths, parent và `close`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider lookup, explicit loader, TCCL.
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record type semantics.
- [JLS 17 — 13 Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): khả năng tương thích nhị phân khi thay đổi API.