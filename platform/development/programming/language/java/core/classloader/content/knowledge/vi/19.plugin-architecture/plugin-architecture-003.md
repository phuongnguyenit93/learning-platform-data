# Mỗi plugin một ClassLoader hay nhiều plugin dùng chung ClassLoader?

Khi thiết kế **kiến trúc plugin Java**, một quyết định quan trọng là: **mỗi plugin có một defining class loader riêng**, hay **nhiều plugin cùng được nạp qua một loader**? Cả hai mô hình đều có thể đúng. Khác biệt cốt lõi là **ranh giới namespace, khả năng dùng các phiên bản dependency khác nhau, chia sẻ kiểu và trạng thái, mức độ độc lập khi nâng cấp/unload, cách tìm resource và chi phí vận hành**.

**Quy tắc định hướng:** Nếu các plugin có vòng đời độc lập, cần các phiên bản dependency khác nhau hoặc có nguy cơ trùng binary class name, nên xem xét **mỗi plugin một loader**. Nếu các thành phần được phát hành và kiểm thử như một tập thống nhất, dùng cùng dependency versions và cần trao đổi trực tiếp nhiều class nội bộ, **một loader dùng chung** có thể đơn giản hơn. Trong cả hai trường hợp, hãy đưa **API/SPI giao tiếp chung** lên một loader cha hoặc một cơ chế module contract nhất quán.

Bài học này giả định Java 17+ và bàn về plugin chạy **trong cùng một JVM**. ClassLoader là công cụ tổ chức runtime classes và resource lookup; **không phải biện pháp sandbox để thực thi mã không đáng tin**.

## 1. Đầu tiên: “một loader” thay đổi điều gì?

Theo *Java Virtual Machine Specification (JVMS)*, danh tính của một runtime class/interface được xác định bởi:

```text
(binary name, defining class loader)
```

Ví dụ tên nhị phân `impl.Greeting`:

```text
Plugin A loader ──define──> impl.Greeting  (runtime type A)
Plugin B loader ──define──> impl.Greeting  (runtime type B)

Tên: giống nhau
Defining loader: khác nhau
Kết quả: hai runtime classes KHÁC NHAU
```

Nhưng nếu cả hai plugin được đưa vào **cùng một loader**:

```text
SharedLoader:
  plugin-a.jar chứa impl/Greeting.class
  plugin-b.jar chứa impl/Greeting.class
       |
       +--> SharedLoader.loadClass("impl.Greeting")
                      |
                      +--> một runtime class được loader đó chọn
```

Một defining loader **không thể định nghĩa hai runtime classes khác nhau có cùng binary name**. Nếu thư viện/JAR thứ hai cũng chứa `impl.Greeting`, code không tự động được dùng “bản dành cho plugin B”. Thường một bản sẽ được tìm trước theo classpath/URL search policy; yêu cầu lặp lại trả cùng `Class<?>` đã được loader ghi nhận.

Cần phân biệt **gọi `loadClass`** và **được loader định nghĩa**. Với parent-first delegation, child có thể gọi `loadClass("shared.api.Plugin")` nhưng nhận lớp do parent định nghĩa. Chỉ gọi loader con không chứng minh class thuộc riêng loader con.

### Ba khái niệm dễ nhầm

| Khái niệm | Danh tính/quy tắc | Hệ quả |
|---|---|---|
| **Runtime class** | Tên nhị phân + defining loader | Hai bản cùng tên ở loader khác nhau là hai kiểu khác nhau |
| **Runtime package** | Tên package + defining loader | Hai class cùng package name ở loader khác nhau không tự dùng chung package-private access |
| **Plugin instance** | Một object cụ thể được tạo từ class | Có thể có nhiều instances ngay cả khi chỉ có một class/loader |

**Một loader cho nhiều plugin** không đồng nghĩa “chỉ có một object plugin”. Các plugin vẫn có thể tạo nhiều instances. Nhưng chúng dùng chung runtime type nếu loader chỉ định nghĩa một class với cùng tên, và **static fields** của runtime class đó cũng được chia sẻ.

## 2. Mô hình A: mỗi plugin một loader

Một sơ đồ parent-first đơn giản:

```text
Host / Application ClassLoader
  ├── spi.Plugin                    (public interface)
  ├── spi.Context                   (shared DTO)
  └── host.PluginManager
       ^                  ^
       | parent           | parent
       |                  |
Plugin A URLClassLoader   Plugin B URLClassLoader
  ├── impl.Greeting         ├── impl.Greeting
  ├── acme.lib.Helper v1    ├── acme.lib.Helper v2
  ├── a.properties          └── b.properties
  └── META-INF/services/... 
```

Mỗi plugin loader có danh sách URLs hoặc một nguồn bytecode riêng. Nó giữ **namespace định nghĩa** riêng cho những classes parent không cung cấp.

**Ưu điểm:**

1. Hai plugin có thể có những class **cùng binary name** với định nghĩa độc lập (nếu chúng thật sự do loader riêng định nghĩa).
2. Các phiên bản thư viện private có thể cùng tồn tại: `acme.lib.Helper` v1 và v2 là các runtime types khác nhau.
3. Có thể phân biệt, giám sát và quản lý vòng đời plugin theo từng loader.
4. Dễ thiết kế việc **thay loader mới** khi cập nhật riêng một plugin mà không buộc mọi plugin khác phải cùng thế hệ.
5. Resource lookup có thể được gắn với loader cụ thể, giảm va chạm tên config/template.

**Chi phí/rủi ro:**

- Cùng một thư viện private có thể bị nạp **lặp lại** ở nhiều loaders; metadata, bytecode representation và static state không tự được chia sẻ.
- Object của một private type do loader A định nghĩa không cast trực tiếp thành type cùng tên do loader B định nghĩa.
- Giao tiếp A↔B khó hơn nếu các phương thức nhận/trả class private; cần chia sẻ contract/DTO ổn định.
- TCCL, ServiceLoader, resource lookup và caching có thể khiến code vô tình lấy provider/resource sai plugin.
- Unload không tự động: thread, static cache ở host, event listeners, JDBC drivers, logging, MBeans, executors và reference tới Class/instance có thể giữ loader sống.

**Điểm tinh tế về parent-first:** Hai `URLClassLoader` con với cùng parent **chưa bảo đảm phiên bản thư viện khác nhau** nếu parent đã có phiên bản thư viện đó. Nếu parent chứa `acme.lib.Helper`, cả hai child mặc định có thể ủy quyền parent và nhận **một** phiên bản của parent. Muốn isolation thật, phải định nghĩa rõ **shared classes ở parent** và **private classes chỉ thuộc plugin loaders**, hoặc dùng policy child-first có kiểm soát.

## 3. Mô hình B: nhiều plugin dùng chung một loader

```text
Host / Application ClassLoader
  └── spi.Plugin
        ^
        | parent
        |
One Shared URLClassLoader
  ├── plugin-a.jar
  ├── plugin-b.jar
  ├── common-helper.jar
  └── resource descriptors của cả nhóm
```

Một `URLClassLoader` chung được tạo với URLs của nhiều plugin và dependencies. Mọi class do loader này **thực sự định nghĩa** dùng cùng loader identity.

**Ưu điểm:**

1. Ít boundaries class-loader hơn, nên các classes cùng loader dễ dùng chung **package-private access** khi cùng runtime package (vẫn phải tuân thủ các quy tắc Java khác).
2. Một phiên bản dependency chung có thể được nạp và khởi tạo **một lần cho toàn nhóm**, tránh duplication.
3. Những plugin được phát hành như một bộ đồng phiên bản dễ gọi class của nhau khi tất cả classes đều nằm trong một namespace.
4. Resource scanning từ một loader chung có thể đơn giản khi intentionally tổng hợp descriptors từ toàn nhóm.
5. Giảm độ phức tạp trong module/class identity khi plugin thực chất chỉ là “các tính năng cùng ứng dụng” chứ không có nhu cầu isolation.

**Chi phí/rủi ro:**

- Hai JAR có cùng binary class name tạo **xung đột**: không thể chọn đồng thời hai definitions riêng trong cùng defining loader.
- Một plugin muốn `foo.Bar v1` còn plugin khác muốn `foo.Bar v2` có thể gặp `NoSuchMethodError`, `NoClassDefFoundError`, sai hành vi hoặc lệch binary compatibility.
- Những **static fields/singletons** thuộc class chung được chia sẻ giữa các plugin; dễ rò trạng thái hoặc tạo coupling ngoài ý muốn.
- Khó thay thế chỉ một plugin implementation với **cùng binary name** bằng bytecode mới trong cùng loader: JVM không có thao tác “định nghĩa lại bằng `defineClass`” đơn giản.
- Loader chung chỉ có thể được collectible khi toàn bộ classes/instances/references của nhóm đã hết được sử dụng theo điều kiện JVM. Một plugin còn hoạt động có thể khiến cả nhóm khó unload.
- Thứ tự các URLs/JARs và resources trùng tên ảnh hưởng kết quả; “plugin B có JAR riêng” không đồng nghĩa B luôn dùng class trong JAR ấy.

Dùng chung loader có thể phù hợp với một **bộ plugin tích hợp do cùng team phát hành**, được kiểm thử chung và triển khai/nâng cấp đồng bộ. Đừng chọn chỉ vì “ít ClassLoader objects hơn” mà bỏ qua yêu cầu versioning và lifecycle.

## 4. Bảng đối chiếu lựa chọn

| Tiêu chí | Mỗi plugin một loader | Một loader cho nhiều plugin |
|---|---|---|
| **Class identity** | Mỗi child có thể định nghĩa private classes riêng | Một binary name chỉ có một definition trong loader chung |
| **Dependency trùng tên khác version** | Có thể cách ly nếu parent không chiếm namespace đó | Thường xung đột; phải thống nhất version hoặc relocate |
| **API giữa host và plugins** | Phải chia sẻ contract ở parent/loader chung | Vẫn nên chia sẻ contract ổn định ở parent |
| **Plugin A gọi private class của B** | Phức tạp; cần contract/loader visibility thích hợp | Thường dễ hơn khi class visible trong cùng loader |
| **Package-private giữa plugins** | Khác runtime package nếu defining loader khác | Có thể cùng runtime package khi package name trùng |
| **Static state của private dependencies** | Riêng theo runtime class/loader | Dùng chung nếu cùng runtime class |
| **Resource trùng tên** | Có namespace lookup theo loader, nhưng delegation vẫn ảnh hưởng | Dễ shadowing, cần chính sách precedence/aggregation |
| **Thay một plugin** | Có thể tạo loader mới riêng, phải cleanup đúng | Thường cần loader mới cho cả nhóm nếu đổi class đã định nghĩa |
| **Unloading** | Có thể cleanup theo plugin, không bảo đảm tức thời | Một tham chiếu còn sống có thể giữ namespace cả nhóm |
| **Memory/metadata** | Có nguy cơ lặp class metadata, caches, static state | Có thể tiết kiệm nếu dùng chung classes |
| **Bảo mật mã không tin cậy** | Không phải sandbox | Cũng không phải sandbox |
| **Độ đơn giản code ban đầu** | Nhiều loader/lifecycle hơn | Ít loader hơn, nhưng cần kiểm soát conflict |

Không nên biến bảng thành quy tắc tuyệt đối. Chính sách delegation, module layers, cách triển khai JAR, container/framework và class loader implementation có thể thay đổi chi tiết. Phải đo/kiểm chứng theo sản phẩm thực tế.

## 5. Demo Java 17+: hai plugin trùng tên class, thử cả hai mô hình

Ví dụ cho phép quan sát chính xác **tác động của defining loader**. Hai plugin có cùng class **`impl.Greeting`**, cùng interface `spi.Plugin` nhưng trả kết quả khác. Ta sẽ thử:

- Một `URLClassLoader` chỉ chứa plugin A.
- Một `URLClassLoader` chỉ chứa plugin B.
- Một `URLClassLoader` chung chứa **cả A và B**, theo thứ tự URL A rồi B.

Host chỉ có **SPI và mã ứng dụng** trên classpath. Nó **không** có plugin implementations, nên parent-first delegation không làm mất isolation của hai plugins.

Cấu trúc nguồn/output:

```text
plugin-demo/
├── src/
│   ├── spi/Plugin.java
│   ├── app/PluginLoaderDemo.java
│   ├── alpha/impl/Greeting.java
│   └── beta/impl/Greeting.java
└── out/
    ├── host/
    │   ├── spi/Plugin.class
    │   └── app/PluginLoaderDemo.class
    ├── alpha/
    │   ├── impl/Greeting.class
    │   └── plugin.properties
    └── beta/
        ├── impl/Greeting.class
        └── plugin.properties
```

### 5.1. Shared SPI

**`src/spi/Plugin.java`:**

```java
package spi;

public interface Plugin {
    String id();
}
```

Class/interface này phải được host định nghĩa. Hai plugin cùng `implements spi.Plugin` và do parent delegation dùng đúng runtime interface của host, không tự đóng gói một bản khác của API.

### 5.2. Plugin A

**`src/alpha/impl/Greeting.java`:**

```java
package impl;

import spi.Plugin;

public class Greeting implements Plugin {
    @Override
    public String id() {
        return "alpha";
    }
}
```

### 5.3. Plugin B

**`src/beta/impl/Greeting.java`:**

```java
package impl;

import spi.Plugin;

public class Greeting implements Plugin {
    @Override
    public String id() {
        return "beta";
    }
}
```

Hai source files có **cùng package/name** nhưng khác nội dung. Chúng được biên dịch vào **hai output directories riêng**. Nếu đặt cả hai cùng compiler output và cùng classpath không kiểm soát, ví dụ có thể bị đè class file hoặc không cho thấy đúng bài toán.

### 5.4. Host runner

**`src/app/PluginLoaderDemo.java`:**

```java
package app;

import spi.Plugin;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

public final class PluginLoaderDemo {
    private static String id(Class<?> type) throws Exception {
        Plugin plugin = (Plugin) type
                .getDeclaredConstructor().newInstance();
        return plugin.id();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = PluginLoaderDemo.class.getClassLoader();

        URL alpha = Path.of(args[0]).toUri().toURL();
        URL beta = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader a =
                     new URLClassLoader(new URL[] {alpha}, host);
             URLClassLoader b =
                     new URLClassLoader(new URL[] {beta}, host);
             URLClassLoader shared =
                     new URLClassLoader(new URL[] {alpha, beta}, host)) {

            Class<?> typeA = a.loadClass("impl.Greeting");
            Class<?> typeB = b.loadClass("impl.Greeting");

            System.out.println("Different implementation types: "
                    + (typeA != typeB));
            System.out.println("Loader A owns A: "
                    + (typeA.getClassLoader() == a));
            System.out.println("Loader B owns B: "
                    + (typeB.getClassLoader() == b));
            System.out.println("Shared API type: "
                    + (a.loadClass("spi.Plugin")
                        == b.loadClass("spi.Plugin")));
            System.out.println("A: " + id(typeA));
            System.out.println("B: " + id(typeB));

            Class<?> sharedType =
                    shared.loadClass("impl.Greeting");
            System.out.println("Shared loader first: "
                    + id(sharedType));
            System.out.println("Shared class reused: "
                    + (sharedType
                        == shared.loadClass("impl.Greeting")));

            Enumeration<URL> urls =
                    shared.getResources("plugin.properties");
            List<String> found = new ArrayList<>();

            while (urls.hasMoreElements()) {
                try (InputStream in =
                        urls.nextElement().openStream()) {
                    found.add(new String(in.readAllBytes(),
                            StandardCharsets.UTF_8).trim());
                }
            }
            System.out.println("Shared resources: "
                    + String.join(",", found));
        }
    }
}
```

Lớp runner sử dụng **Java 17 syntax/APIs**. `URLClassLoader` là một `Closeable`, vì vậy `try-with-resources` giải phóng các tài nguyên loader quản lý khi code kết thúc. Nhưng `close()` **không ép class unloading ngay lập tức** và không nên đóng loader khi plugin còn phải load lớp/tài nguyên mới.

`id(Class<?>)` dùng reflection tạo instance và cast sang interface `spi.Plugin` của host. Vì cả A và B đều delegate interface này cho parent, cast thành công. Nếu chúng tự định nghĩa `spi.Plugin` riêng, có thể gặp lỗi identity/cast hoặc linkage.

### 5.5. Biên dịch và chạy

Dùng **Bash** từ thư mục `plugin-demo`:

```bash
mkdir -p out/host out/alpha out/beta

javac --release 17 -d out/host \
  src/spi/Plugin.java src/app/PluginLoaderDemo.java

javac --release 17 -cp out/host -d out/alpha \
  src/alpha/impl/Greeting.java

javac --release 17 -cp out/host -d out/beta \
  src/beta/impl/Greeting.java

printf 'alpha\n' > out/alpha/plugin.properties
printf 'beta\n' > out/beta/plugin.properties

java -cp out/host app.PluginLoaderDemo out/alpha out/beta
```

Trên **Windows PowerShell**, chạy tương đương:

```powershell
New-Item -ItemType Directory -Force -Path out/host, out/alpha, out/beta | Out-Null
javac --release 17 -d out/host src/spi/Plugin.java src/app/PluginLoaderDemo.java
javac --release 17 -cp out/host -d out/alpha src/alpha/impl/Greeting.java
javac --release 17 -cp out/host -d out/beta src/beta/impl/Greeting.java

[System.IO.File]::WriteAllText(
    "out/alpha/plugin.properties", "alpha",
    [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText(
    "out/beta/plugin.properties", "beta",
    [System.Text.UTF8Encoding]::new($false))

java -cp out/host app.PluginLoaderDemo out/alpha out/beta
```

Trong PowerShell, cách khởi tạo `UTF8Encoding($false)` giúp tạo resource **không có BOM**. Trên Bash, `printf` tạo nội dung UTF-8 bình thường cho ví dụ ASCII này. Đường dẫn `out/alpha` và `out/beta` được truyền dưới dạng tham số chương trình; `Path.of(...).toUri().toURL()` dựng URLs của hai thư mục.

**Đầu ra xác nhận bằng `javac --release 17` và JDK 24:**

```text
Different implementation types: true
Loader A owns A: true
Loader B owns B: true
Shared API type: true
A: alpha
B: beta
Shared loader first: alpha
Shared class reused: true
Shared resources: alpha,beta
```

### 5.6. Phân tích từng kết quả

**`Different implementation types: true`**

Loader A và B cùng gọi `loadClass("impl.Greeting")`, nhưng parent không có class này. A tự tìm/định nghĩa bản trong `out/alpha`, B tìm/định nghĩa bản trong `out/beta`. `typeA != typeB` vì runtime identity khác defining loader.

**`Loader A owns A` và `Loader B owns B`**

`getClassLoader()` xác nhận **defining loader** chính là loader plugin tương ứng. Nếu parent vô tình chứa `impl.Greeting`, hai dòng này có thể không còn đúng: phải kiểm tra tình huống đó khi thực hiện isolation.

**`Shared API type: true`**

`spi.Plugin` chỉ có một bản ở `out/host`. Parent-first delegation khiến A và B nhận cùng đối tượng `Class<?>` của interface. Đây là cơ sở để host gọi `Plugin.id()` với instance từ cả hai loader.

**`A: alpha` và `B: beta`**

Hai plugin trả đúng behavior riêng mặc dù implementation có **cùng binary name**.

**`Shared loader first: alpha`**

Loader chung có URLs theo thứ tự `alpha` rồi `beta`. Cả hai thư mục đều có `impl/Greeting.class`. Với cấu hình `URLClassLoader` trong demo, class được tìm trước là **bản alpha**. Việc có thêm bản beta không tạo ra class thứ hai cùng tên trong loader chung.

**`Shared class reused: true`**

Lời gọi `shared.loadClass("impl.Greeting")` lần sau trả đúng `Class<?>` đã được nạp bởi shared loader, không tự chọn bản beta.

**`Shared resources: alpha,beta`**

`getResources("plugin.properties")` **liệt kê nhiều URL**. Một loader có thể có **hai resources cùng tên** trong các nguồn URLs, dù nó chỉ định nghĩa **một class cùng binary name**. Vì vậy không được nhầm **resource enumeration** với **class definition selection**.

**Giới hạn ví dụ:** Đây là case parent-first với directories trên classpath JDK chuẩn, không có custom child-first policy, named modules hay framework-specific nested JAR URLs. `URLClassLoader` có quy tắc riêng về class/resource URLs; các container khác có thể có policies và lifecycle khác nhau.

## 6. Chia sẻ API: điều kiện quan trọng của cả hai mô hình

Một ứng dụng plugin nên phân rõ:

```text
shared.api.*          -> hợp đồng host/plugins giao tiếp
plugin.impl.*         -> code triển khai riêng
plugin.private.libs.* -> dependencies nội bộ tùy plugin
```

Ví dụ SPI:

```java
package shared.api;

public interface Plugin {
    String name();
    void start(PluginContext context);
    void stop();
}
```

Đây là **interface minh họa**, không đủ để chạy độc lập vì cần `PluginContext` phù hợp. Điểm quan trọng là **class identity** của `Plugin` và `PluginContext` phải đồng nhất ở những nơi trao đổi object.

Khi dùng **mỗi plugin một loader**, public SPI/DTO và interfaces được host định nghĩa là cách dễ hiểu nhất để bảo đảm cùng runtime types. Plugin phải **delegate** namespace API lên parent, hoặc hệ thống phải thiết kế module/layer contract tương đương.

Nếu plugin loader A tự định nghĩa `shared.api.Plugin` nhưng host có một bản `shared.api.Plugin` khác, câu lệnh như:

```java
Plugin plugin = (Plugin) instanceFromPlugin;
```

có thể ném `ClassCastException`, ngay cả khi cả hai `Plugin` cùng package name và bytecode tương tự. **Tên giống nhau không làm classes từ hai defining loaders trở thành một Java type.**

Với **một loader chung**, nhiều implementation types có thể tham chiếu lẫn nhau dễ hơn, nhưng shared API với host vẫn nên được phân định rõ để tránh phiên bản contract bị “shadow” bởi JAR plugin.

### Cẩn thận với parameter/return types

Giả sử API host:

```java
public interface Processor {
    shared.api.Result process(shared.api.Input input);
}
```

Đây là đoạn minh họa (cần có hai classes trong package `shared.api`). Nếu những method signatures thay bằng `pluginA.internal.Result` mà plugin B/host không nạp được hoặc nạp từ loader khác, code có thể gặp `NoClassDefFoundError`, lỗi access hoặc `LinkageError`. Giữ **cross-plugin boundary** chỉ trên public shared contracts ổn định, tránh để internal implementation types lọt vào chữ ký API chung.

## 7. Dependency conflict: khác tên plugin chưa đủ cách ly

Một plugin A dùng `org.example.json.Parser v1`, plugin B dùng `org.example.json.Parser v2`:

**Hai loaders riêng:**

```text
host (không chứa Parser)
   ├── loader A -> org.example.json.Parser v1
   └── loader B -> org.example.json.Parser v2
```

Nếu cả A và B thực sự tự định nghĩa `Parser`, hai phiên bản có thể cùng tồn tại. Nhưng object của bản v1 không tự tương thích với kiểu bản v2 nếu trao đổi trực tiếp qua boundary. Dùng shared DTO/serialized payload hoặc adapter có contract rõ.

**Một loader chung:**

```text
shared loader:
    plugin-a.jar -> Parser v1
    plugin-b.jar -> Parser v2

loader.loadClass("org.example.json.Parser")
    -> một trong hai definitions theo policy lookup
```

Không thể có hai runtime classes `org.example.json.Parser` v1 và v2 **cùng được shared loader định nghĩa dưới cùng binary name**. Việc chuyển thứ tự JAR có thể đảo lỗi, không giải quyết yêu cầu phiên bản đồng thời.

### Có thể dùng shading/relocation thay isolation?

Trong một số dự án, dependency được **relocate** thành binary names khác nhau khi build:

```text
pluginA.shadow.json.Parser
pluginB.shadow.json.Parser
```

Khi đó một loader chung có thể định nghĩa hai classes vì **tên khác nhau**. Tuy nhiên shading cần xử lý reflective names, `META-INF/services`, resources, native code và các references liên quan. Đây là **chiến lược build** khác, không phải plugin class-loader isolation mặc định.

### Điểm thất bại phổ biến của “hai loader riêng”

Nếu host loader có dependency phiên bản v1 và cả A/B loader đều **parent-first**, loader B có thể luôn nhận Parser v1 từ parent, dù URL của B chứa v2. Để thực sự cho B dùng v2, cần thiết kế:

- Không đưa private dependency cần đa phiên bản vào parent/shared loader.
- Chỉ đưa **contracts** thật sự chung lên parent.
- Dùng loader strategy/container hỗ trợ plugin-private namespace khi cần.
- Có tests xác nhận `Parser.class.getClassLoader()` và behavior/version thực tế.

Một loader riêng là **điều kiện cho isolation**, không tự động bảo đảm isolation nếu class loading vẫn ủy quyền phiên bản không mong muốn từ parent.

## 8. Static fields, singleton và trạng thái plugin

Static fields thuộc **runtime class**, không thuộc “chuỗi tên class” toàn JVM.

Nếu hai loaders định nghĩa hai bản `plugin.State`:

```text
(loader A, plugin.State).counter = 10
(loader B, plugin.State).counter = 20
```

mỗi bản có **static state riêng**. Đây có thể là điều mong muốn cho cache/config của plugin, hoặc có thể gây nhầm khi tác giả nghĩ rằng `State.INSTANCE` là singleton toàn JVM.

Nếu A và B dùng **một defining loader chung** cho `plugin.State`, static field sẽ được chia sẻ cho cả hai. Khi đó code cần thiết kế synchronization, tenant isolation và lifecycle cho state chung.

Một lưu ý quan trọng: **statics trong class do parent định nghĩa được chia sẻ bất kể plugin loaders có riêng hay không**. Nếu thư viện logging/global registry hoặc shared API giữ static cache ở parent, cả A và B vẫn có thể tác động tới cùng state đó.

### Không thể gỡ “static singleton cũ” chỉ bằng cách thay JAR

Nếu đã định nghĩa `plugin.State` trong loader và nó đã được sử dụng, thay bytes trên disk **không làm định nghĩa runtime class cũ thay đổi**. Với per-plugin loader có thể tạo loader **mới** cho thế hệ plugin mới, nhưng phải dọn references tới loader cũ. Với shared loader, thay một plugin cùng tên thường đòi tạo **loader mới cho nhóm**, ảnh hưởng các plugin còn lại.

## 9. Resource, cấu hình và ServiceLoader

Plugin JARs không chỉ chứa bytecode:

```text
plugin-a.jar:
  impl/Greeting.class
  plugin.properties
  META-INF/services/spi.Plugin

plugin-b.jar:
  impl/Greeting.class
  plugin.properties
  META-INF/services/spi.Plugin
```

**Khi mỗi plugin có loader riêng:** code có thể dùng loader A để lấy `plugin.properties` của A, loader B cho B. Nhưng **parent delegation** của `getResource` mặc định thường ưu tiên resource ở parent, nếu có cùng tên. Nếu plugin cần child-first resources, phải kiểm soát đúng lookup policy hoặc đặt tên resources theo plugin để tránh collisions.

**Khi dùng loader chung:** `getResource("plugin.properties")` thường trả **một URL** đầu tiên, còn `getResources("plugin.properties")` có thể trả **nhiều URL**. Đừng thiết kế plugin B đọc “file của B” bằng `getResource` chung rồi cho rằng loader biết plugin nào gọi.

### SPI và ServiceLoader

Với classpath SPI, provider descriptor:

```text
META-INF/services/spi.Plugin
```

chứa binary names của provider implementations, ví dụ:

```text
plugins.alpha.AlphaPlugin
plugins.beta.BetaPlugin
```

Đây là ví dụ metadata, không phải code runnable của demo phần 5; trong demo phần 5 có **hai implementations cùng binary name `impl.Greeting`** để chứng minh class collision.

`ServiceLoader.load(Plugin.class, pluginLoader)` dùng **loader được truyền**. `ServiceLoader.load(Plugin.class)` dùng **thread context class loader (TCCL)** theo Java SE 17 API. Điều này ảnh hưởng cách plugin manager chọn tập providers.

- **Mỗi plugin một loader:** load service providers qua đúng loader tương ứng, xác minh SPI type được parent định nghĩa và descriptor có trong plugin.
- **Loader chung:** service discovery có thể tổng hợp nhiều providers; phải phân biệt providers theo metadata/ID, không phụ thuộc tuyệt đối vào thứ tự nếu contract không đảm bảo.
- Nếu hai descriptors đều trỏ tới **cùng provider binary name** nhưng chỉ có **một shared loader**, tên được resolve trong namespace đó, không tạo ra hai provider implementations tương ứng hai JARs.
- Với named modules, `ServiceLoader` còn hỗ trợ `provides ... with ...` trong `module-info.java` và discovery theo `ModuleLayer`; không chỉ dựa trên `META-INF/services`.

## 10. TCCL, thread pools và async tasks

TCCL thuộc **thread**, được `ServiceLoader.load(serviceType)` và một số frameworks sử dụng cho discovery; nó không đổi defining loader của class hay tự truyền vào worker pool đã tồn tại. Trong callback/task của plugin, nếu cần TCCL thì set đúng plugin loader **trên worker thực thi** và khôi phục context cũ trong `finally`. Ưu tiên `ServiceLoader.load(serviceType, pluginLoader)` khi có owner tường minh. Quên restore gây tìm nhầm providers và giữ loader cũ sau reload.

## 11. Reload/unload: một loader riêng không bảo đảm GC

Loader riêng giúp thay **một plugin generation** độc lập, nhưng chỉ sau khi dừng nhận công việc mới, drain requests/tasks, unregister listeners, đóng tài nguyên và bỏ host references. Tạo **loader mới** cho cùng binary names; không dùng `close()` hoặc thay JAR để redefine class trong loader cũ. Loader chung gắn vòng đời cả nhóm: muốn thay riêng một class đã được định nghĩa thường phải tạo namespace/loader mới cho nhóm hoặc đổi cách phân chia. JVM/GC không hứa thời điểm unload.

## 12. Mô hình trung gian: nhóm loader hoặc shared library loader

Hai cực “mỗi plugin một loader” và “mọi plugin dùng chung một loader” không phải là các lựa chọn duy nhất.

Ví dụ:

```text
Application Host Loader
    └── shared.api.*
          ^
          |
Common Plugin API/Library Loader
    ├── stable.shared.lib.*
    ├── contracts.*
    ^
    | parent
    +-----------+-----------+
    |                       |
PluginGroupLoader-X     PluginGroupLoader-Y
    |                       |
    +--> A, B                +--> C, D
```

Một nhóm plugin có thể dùng chung một loader khi **được quản lý vòng đời và dependencies chung**, nhóm khác có loader riêng. Hoặc có loader nền chứa stable shared libraries, mỗi plugin loader là child.

Cần hiểu:

- Nếu private dependency bị đưa vào parent **quá sớm**, các child parent-first sẽ không tự có phiên bản riêng.
- Shared library loader có thể tiết kiệm tài nguyên, nhưng làm **định nghĩa dependency chung thành ràng buộc version** giữa các plugin.
- Cây parent-child một chiều không tự hỗ trợ tất cả quan hệ chéo A→B. Muốn plugin dùng API nhau có thể cần **contract loader chung**, registry/service bus hoặc loader delegation rõ.
- Tránh graph loader có vòng dependency dẫn tới class-loading recursion hoặc deadlock. `ClassCircularityError` và `LinkageError` cũng có thể xuất hiện trong những tình huống liên quan class resolution/constraints.

Mô hình trung gian nên được thiết kế theo **dependency graph và lifecycle domains**, không đơn thuần theo số lượng file JAR.

## 13. JPMS, ModuleLayer và plugin loaders

Java 9+ có **Java Platform Module System (JPMS)**:

- `Module` định danh một module runtime và access rules.
- `ModuleLayer` tổ chức các modules được resolved trong một configuration.
- `ClassLoader` thực hiện nạp/định nghĩa classes, có thể gắn với một hoặc nhiều modules.

Với plugins được đóng thành **named modules**:

- `ModuleLayer.defineModulesWithOneLoader(...)`: tạo layer trong đó các modules được định nghĩa cho một loader được tạo.
- `ModuleLayer.defineModulesWithManyLoaders(...)`: tạo layer với một loader cho mỗi module trong configuration.
- Có thể dùng module mapping theo loader do bạn kiểm soát khi yêu cầu đặc thù và hiểu cơ chế `defineModules`.

Đây là những API khác với việc tạo nhiều `URLClassLoader` từ JARs đơn thuần. **Module không đồng nghĩa plugin**: một plugin có thể gồm nhiều modules, và một module có thể chứa nhiều thành phần. Chọn one/many loader trong `ModuleLayer` dựa trên module resolution, visibility và nhu cầu lifecycle, không coi một method là đáp án tự động.

**Giới hạn quan trọng:**

- `exports` và `opens` xác định khả năng truy cập code/resources/reflective access của named modules, không bị bỏ qua chỉ vì cùng class loader.
- Split packages giữa modules trong cùng loader có thể chịu ràng buộc của JPMS.
- Service providers có thể được đăng ký bằng `provides ... with ...` trong module descriptor.
- `ModuleLayer` không tự bảo đảm plugin hoàn toàn độc lập hoặc được unload khi không còn cần; vẫn có lifecycle/reference vấn đề tương tự.

Nếu plugin architecture đã dùng named modules, hãy thiết kế một **ModuleLayer/plugin manager** chuyên biệt thay vì chỉ xếp JAR URLs và kỳ vọng JPMS hiểu hết các quan hệ.

## 14. Khi cần child-first thay cho URLClassLoader parent-first

`URLClassLoader` thông thường kế thừa policy **parent-first**. Với case A và B của demo, parent không chứa `impl.Greeting` nên isolation hoạt động. Nhưng nếu parent có cùng binary name hoặc các dependency cần version riêng, child-first có thể được yêu cầu cho **private namespace**.

Một bản thiết kế:

```text
loadClass(name):
    lock bằng getClassLoadingLock(name)
    nếu đã loaded -> trả kết quả
    nếu name là JDK hoặc shared.api -> delegate parent trước
    nếu name thuộc plugin-private:
         thử findClass của child
         nếu ClassNotFoundException -> fallback parent theo policy
    các tên khác -> parent-first
    resolve khi cần
```

Đây là **giả mã**, không phải runnable Java method. Khi tự override `loadClass`, phải kiểm tra:

1. `findLoadedClass` và locking để tránh duplicate class definitions.
2. `resolveClass` theo tham số `resolve` nếu cần.
3. Không tự định nghĩa `java.*` từ custom loader; `defineClass` có namespace restrictions.
4. Không duplicate shared SPI/DTO contracts giữa parent/child.
5. Không bắt/nuốt `VerifyError`, `LinkageError`, `SecurityException` như lỗi “không tìm thấy”.
6. Chính sách resource `getResource` và `getResources` phải đồng bộ nơi cần thiết với class policy.
7. Java package sealing, CodeSource, certificates, module access và native resources có thể ảnh hưởng loader thực tế.

**Nếu plugin của bạn chỉ cần đọc JARs/thư mục và parent không chứa private classes**, hãy bắt đầu với `URLClassLoader` chuẩn. Một custom child-first loader tự viết không phải lựa chọn mặc định.

## 15. Vấn đề bảo mật và cô lập lỗi

Cả per-plugin loader lẫn shared loader đều chạy bytecode trong cùng JVM, chia sẻ quyền process và các nguồn CPU/RAM/OS. Nếu threat model bao gồm plugin không tin cậy hoặc yêu cầu hard stop, cần process/OS sandbox và giao thức rõ; ClassLoader chỉ cô lập runtime types/dependencies.

## 16. Quan sát/đo đạc khi quyết định

Để chọn có căn cứ, nên thử các workload thực tế và đo:

| Quan sát | Một loader/plugin có thể tốt hơn khi | Shared loader có thể tốt hơn khi |
|---|---|---|
| Kích thước class metadata, metaspace | Plugins sử dụng ít code trùng hoặc isolation quan trọng hơn | Plugins cùng nhiều dependencies, tiết kiệm duplicate metadata |
| Startup/load latency | Plugins độc lập và nạp lazy theo nhu cầu | Cả nhóm luôn chạy đồng thời, cache classes chung |
| Đổi phiên bản dependency | Nhiều thư viện trùng binary name khác versions | Có BOM/dependency lock thống nhất |
| Độc lập deploy/reload | A/B có release cadence riêng | Nhóm deploy atomically |
| Chia sẻ objects trực tiếp | Đa số giao tiếp qua public SPI/DTO | Plugins cố tình dùng chung nhiều implementation internals |
| Debugging | Có tooling log loader/class origins tốt | Ít namespace hơn nhưng phải xử lý class shadowing |
| Plugin failures | Có quy trình stop/cleanup riêng | Một lỗi/coupling có thể ảnh hưởng nhóm chung |

Không có bảo đảm “mỗi plugin một loader luôn nhanh hơn” hay “một loader luôn ít bộ nhớ hơn” cho mọi hệ thống. Nên đo **số classes thực nạp**, metaspace, heap retained references, runtime behavior, latency và phụ thuộc cụ thể, thay vì dùng số JAR làm proxy.

### Log chẩn đoán tối thiểu

Trong code đã có đối tượng `Class<?> type`:

```java
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
System.out.println("package=" + type.getPackageName());
```

Đây là snippet minh họa bên trong method, không phải chương trình độc lập. Đừng so sánh loaders bằng tên in ra từ `toString()`; nếu cần identity chắc chắn hãy dùng `==` trên đối tượng `ClassLoader` hoặc `Class<?>` trong cùng JVM.

Có thể thêm module/code source/version metadata nếu phù hợp; đừng suy ra class-file nguồn đáng tin chỉ từ resource URL nếu loader thực hiện bytecode transformation.

## 17. Các tình huống thường gặp và lựa chọn gợi ý

### Trường hợp 1: IDE/editor cho cài plugin bên thứ ba

Plugins có vòng đời/version khác nhau, dependency conflict tiềm ẩn và cần unload khi người dùng tắt plugin. **Ưu tiên mỗi plugin một loader hoặc nhóm độc lập theo lifecycle**, parent chứa SPI công khai. Nếu code không tin cậy, cần cô lập process/quyền thêm.

### Trường hợp 2: 20 “plugins” thực chất là các feature modules cùng một sản phẩm

Tất cả phát hành đồng bộ, dependency lock chung và không bao giờ hot swap riêng. **Một loader chung** hoặc JPMS layer/module grouping có thể đơn giản, miễn đã kiểm tra binary name collisions.

### Trường hợp 3: Hai plugin cùng dùng thư viện JSON nhưng phiên bản khác nhau

Nếu cần cả hai versions đồng thời, **tách defining loaders cho private library** hoặc relocate dependencies có kiểm thử. Không đặt một bản JSON parser private lên parent rồi kỳ vọng child parent-first chọn bản khác.

### Trường hợp 4: Plugin A phải gọi một service của B

Đừng trao đổi trực tiếp `b.internal.Foo` qua boundary nếu có thể tránh. Cung cấp **shared SPI/DTO** và registry/service locator quản lý endpoints/versions; host điều phối A↔B. Nếu cần gọi direct private classes, một loader chung hoặc layer/module graph có chủ đích sẽ phù hợp hơn, nhưng giảm isolation.

### Trường hợp 5: Nâng cấp plugin trong lúc host vẫn chạy

**Per-plugin loader + generation mới** cho phép thay code của riêng plugin ở mức class identity, miễn plugin cũ được quiesce/cleanup và không còn references sống. Với shared loader, thay cùng binary name của một plugin thường buộc build namespace mới cho cả nhóm.

### Trường hợp 6: Nhiều providers cùng SPI nhưng classnames trùng

Service descriptors của A và B đều khai báo `impl.Greeting`. Một shared loader không tự biết “`impl.Greeting` trong A” khác “trong B”; hãy đổi provider binary names, dùng loaders riêng hoặc có plugin-specific mapping. ServiceLoader là discovery mechanism, **không giải quyết class identity collision** thay bạn.

## 18. Checklist quyết định trước khi triển khai

- [ ] Plugins có cần **đa phiên bản của cùng binary class name** không?
- [ ] Plugin có cần được **deploy/reload/unload độc lập** không?
- [ ] Shared API/SPI và DTO đã có **một defining loader chung** chưa?
- [ ] Parent loader có vô tình chứa private libraries khiến child isolation không có hiệu lực không?
- [ ] Có nhiều `META-INF/services`, config/templates trùng resource names không?
- [ ] TCCL của plugin execution thread được set/reset đúng lúc không?
- [ ] Các cross-plugin method signatures có lộ class private không?
- [ ] Có cần JPMS `ModuleLayer`, named modules, qualified exports/opens không?
- [ ] Có đo duplicate classes/metaspace và overhead hay chỉ suy đoán?
- [ ] Có quản lý listeners/ThreadLocal/executors/ServiceLoader cache/native registrations cho unload không?
- [ ] Có test conflict thực sự: **cùng binary name** ở hai plugin với hành vi khác?
- [ ] Nếu mã plugin không đáng tin, có isolation/security **ngoài class loader** chưa?

**Quy trình khởi đầu hợp lý:** Đặt contracts ở host loader; triển khai thí điểm hai plugins có tên dependency trùng nhau; dùng `URLClassLoader` đơn giản cho các child; test loader identities, type casting, resource discovery và lifecycle. Chỉ phát triển custom delegation/ModuleLayer nâng cao khi thí điểm chứng minh cần thiết.

## 19. Câu hỏi tự kiểm tra

**1. Hai plugin cùng khai báo `impl.Greeting` nhưng mỗi plugin có defining loader khác nhau. Đây có phải cùng runtime type không?** Không. Class identity còn phụ thuộc defining loader.

**2. Một shared loader có thể đồng thời `defineClass` hai bản `impl.Greeting` khác nhau không?** Không trong cùng một defining loader. Một tên nhị phân gắn với một runtime class của loader đó.

**3. Có hai URLClassLoader riêng thì phụ thuộc A v1 và B v2 chắc chắn cách ly chưa?** Chưa. Nếu parent chứa cùng class name, parent-first delegation có thể khiến cả hai dùng bản parent.

**4. Hai plugin có loaders riêng có thể cùng implement một SPI interface do parent định nghĩa không?** Có. Đây là thiết kế phổ biến; plugin implementation types khác nhau nhưng shared SPI type là một.

**5. Hai plugin được nạp bởi cùng loader có nghĩa chỉ có một instance không?** Không. Nhiều instances vẫn có thể được tạo từ một hoặc nhiều runtime classes. Static fields của cùng runtime class mới được chia sẻ.

**6. Tại sao `getResources` có thể trả hai file cấu hình còn `loadClass` chỉ chọn một definition?** Resource enumeration có thể trả nhiều URLs, còn một defining loader chỉ có một runtime class cho mỗi binary name.

**7. `URLClassLoader.close()` có làm JVM unload ngay plugin classes không?** Không. Class unloading phụ thuộc references, GC và runtime lifecycle.

**8. Dùng ServiceLoader có tự giải quyết version conflict/trùng provider class name không?** Không. ServiceLoader phát hiện providers nhưng vẫn dùng class loader/module type identity rules.

**9. Nếu hai plugin phải hot-reload độc lập, mô hình nào thuận lợi hơn?** Thường per-plugin loader, với quiesce/cleanup và API boundary rõ. Không phải bảo đảm unload ngay.

**10. Nếu plugin code không đáng tin, một loader riêng có đủ bảo mật không?** Không. Cần thêm process/container/OS isolation và các biện pháp thực thi an toàn phù hợp.

**11. Dùng một loader chung có thể tiết kiệm metaspace không?** Có thể khi share nhiều classes/dependencies, nhưng cần đo workload; không bảo đảm mọi trường hợp tốt hơn.

**12. Chuyển sang JPMS có đồng nghĩa mỗi module tự có loader riêng không?** Không. ModuleLayer có các chiến lược mapping module→loader; module và loader là hai loại runtime entities khác nhau.

## 20. Nguồn chuẩn để đọc thêm

- Java SE 17 API, `ClassLoader` — defining/initiating loaders, parent delegation, `loadClass`, `defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader` — class/resource lookup từ URLs và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `ServiceLoader` — service providers, classpath descriptors và named modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API, `ModuleLayer` — `defineModulesWithOneLoader` và `defineModulesWithManyLoaders`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java Virtual Machine Specification `5.3, *Creation of Classes and Interfaces*, runtime identity và defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `Thread` — TCCL: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Ghi nhớ:** **Mỗi plugin một loader** ưu tiên tính độc lập về namespace, dependency versions và lifecycle; **nhiều plugin chung một loader** ưu tiên khả năng dùng chung classes/static state và triển khai đồng bộ. Dù chọn mô hình nào, hãy giữ **shared contracts được định nghĩa nhất quán**, kiểm tra delegation thực tế, biết các giới hạn của service/resource lookup và quản lý rõ vòng đời plugin.
