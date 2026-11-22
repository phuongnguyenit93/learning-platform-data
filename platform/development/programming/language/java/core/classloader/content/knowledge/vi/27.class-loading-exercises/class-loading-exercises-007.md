# Tái hiện và sửa lỗi cùng tên lớp nhưng không ép kiểu được trong Java

> **Java Core → ClassLoader → Thực hành.** Hai đối tượng có class cùng **binary name**, cùng source code, thậm chí cùng bytecode lấy từ một thư mục/JAR, vẫn có thể **không ép kiểu được** nếu các lớp đó được định nghĩa bởi **hai ClassLoader khác nhau**. Lỗi hay gặp trong hệ plugin, application server, OSGi, hot reload, test class loaders hoặc ứng dụng đóng gói trùng bản host API. Bài thực hành dùng Java 17+ để (1) tái hiện `ClassCastException` với hai loaders độc lập, (2) **sửa** bằng giao diện dùng chung do parent/host loader định nghĩa, và (3) cố tình tạo lại lỗi khi plugin tự định nghĩa bản sao API theo child-first. Mọi chương trình đều có file, lệnh build, stdout đã kiểm tra và giải thích gắn với runtime class identity.

## 1. Vấn đề: tên lớp là giống nhau nhưng type identity thì khác

Trong Java, runtime type của một class hoặc interface thông thường **không được quyết định chỉ bởi tên đầy đủ**. Theo JVM Specification `5.3`:

```text
Runtime class identity = (binary name, defining ClassLoader)
```

Ví dụ cùng binary name `dup.Token`:

```text
                 ClassLoader L1
                      |
                      v
           defineClass("dup.Token")
                      |
                      v
                Class<?> A

                 ClassLoader L2
                      |
                      v
           defineClass("dup.Token")
                      |
                      v
                Class<?> B

A.getName() == B.getName()     // nội dung String giống nhau
A == B                         // false
A.getClassLoader() == L1       // true
B.getClassLoader() == L2       // true
```

Điều đó có nghĩa:

- Một instance của `A` **không tự động là** instance của `B`.
- `B.class` không thể cast thành `A.class` chỉ nhờ hai class có cùng tên.
- `Class.cast` cũng dùng **runtime type identity**, không chỉ so sánh `getName()`.
- Nếu cả hai được định nghĩa bởi hai loaders khác nhau, kể cả nội dung bytecode trùng nhau 100%, `ClassCastException` vẫn có thể xảy ra.
- Hai Java packages cũng có thể là **hai runtime packages khác nhau** khi cùng package name nhưng defining loader khác; package-private access và các quy tắc liên kết liên quan chịu ảnh hưởng.
- JVM không “hợp nhất” hai lớp khác loaders sau khi chúng đã được định nghĩa.

Đây là cơ chế đúng của JVM để cho phép nhiều phiên bản một thư viện tồn tại cạnh nhau và cô lập namespaces, **không phải bug của phép cast**.

## 2. Tái hiện tối giản: cùng một file .class, hai URLClassLoader

Ta cố tình dùng **cùng một thư mục chứa đúng một `dup/Token.class`** và tạo **hai instance `URLClassLoader` khác nhau**, đều có parent là platform loader. Vì `dup.Token` không có ở parent, mỗi loader phải tự định nghĩa một runtime class.

Các nguồn:

```text
src/
  dup/dup/Token.java
  host/api/Message.java
  plugin/impl/HelloPlugin.java
  app/
    LoaderIdentityDemo.java
    DuplicateApiDemo.java
build/
  duplicate/                  (javac tạo)
  host/                       (javac tạo)
  plugin/                     (javac tạo)
  app/                        (javac tạo)
plugin.jar                    (jar tạo)
plugin-with-api.jar           (jar tạo)
```

Ta sẽ dùng cả năm file nguồn xuyên suốt các thử nghiệm để người học có thể copy thành một project duy nhất.

### File 1: src/dup/dup/Token.java

```java
package dup;

public final class Token {
    public String value() {
        return "token";
    }
}
```

Class này không implements interface nào từ host. Đây là một kiểu cụ thể dùng để **chứng minh cast hỏng**.

### Lấy cùng một class bằng hai loaders

Đoạn code sau sẽ xuất hiện trong `LoaderIdentityDemo.main` ở mục 5:

```java
URL classes = Path.of("build/duplicate")
        .toAbsolutePath().toUri().toURL();

try (URLClassLoader left = new URLClassLoader(
             new URL[]{classes},
             ClassLoader.getPlatformClassLoader());
     URLClassLoader right = new URLClassLoader(
             new URL[]{classes},
             ClassLoader.getPlatformClassLoader())) {

    Class<?> a = Class.forName("dup.Token", true, left);
    Class<?> b = Class.forName("dup.Token", true, right);

    Object rightObject = b.getDeclaredConstructor().newInstance();
    a.cast(rightObject);  // ném ClassCastException
}
```

Đây là **trích đoạn** của chương trình đầy đủ, không phải file Java độc lập. `Class.forName(name, true, loader)` nạp/tìm lớp theo loader được chỉ định và yêu cầu initialization; trong ví dụ `Token` không có static initializer đặc biệt. Cùng directory URL **không** làm hai loader trở thành cùng một object.

## 3. Vì sao JVM không chấp nhận cast?

Một phép cast runtime không chỉ hỏi tên lớp trùng không, mà hỏi quan hệ kiểu thực:

```text
Object rightObject là instance của:
   (dup.Token, defining loader = right)

Lệnh a.cast(rightObject) yêu cầu nó là instance của:
   (dup.Token, defining loader = left)

Hai Class<?> khác identity -> không có quan hệ assignable
                           -> ClassCastException
```

`java.lang.Class#cast(Object)` kiểm tra đối tượng có thể được cast đến type mà `Class<?>` này đại diện không. `Class#isInstance(Object)` và `Class#isAssignableFrom(Class<?>)` cũng hữu ích để kiểm tra trước:

```java
System.out.println(a.isInstance(rightObject)); // false
System.out.println(a.isAssignableFrom(b));      // false
System.out.println(a == b);                     // false
```

Các dòng là snippet đặt trong scope có `a`, `b`, `rightObject` của ví dụ mục 2. Chúng không thể “sửa” quan hệ type identity; chỉ phản ánh trạng thái thực tế.

Cũng có thể xảy ra tình huống subclass quan hệ được chia sẻ khiến cast tới **interface/superclass chung** thành công, dù ép kiểu giữa **hai concrete implementation classes** vẫn thất bại. Đây là chìa khóa để sửa trong kiến trúc plugin.

### Tại sao phản chiếu gọi method vẫn có thể thành công?

Ngay khi hai concrete types không cast trực tiếp được, reflection có thể gọi public method trên đúng `Class<?>` và object tương ứng:

```java
Object value = b.getDeclaredConstructor().newInstance();
Object result = b.getMethod("value").invoke(value);
```

Cách này **không biến** `value` thành instance của class `a`. Reflection vẫn kiểm tra access và method receiver; chỉ tránh yêu cầu static cast vào concrete type không tương thích.

Dùng reflection cho mọi lời gọi là giải pháp tình thế nhiều rủi ro (mất type safety, cần xử lý `InvocationTargetException`, các vấn đề JPMS/reflection), không phải thiết kế giao tiếp plugin khuyến nghị.

## 4. Cách sửa: một API chung do host/parent định nghĩa

Hệ plugin nên chia rõ:

```text
System/host ClassLoader
    └── api.Message         <-- chỉ định nghĩa MỘT LẦN
          ^
          |
    +-----+------------------------------+
    |                                    |
PluginLoader A                      PluginLoader B
    └── impl.HelloPlugin               └── impl.HelloPlugin
         implements api.Message             implements api.Message
```

Hai concrete implementation classes vẫn khác identity:

```text
(impl.HelloPlugin, Loader A)
(impl.HelloPlugin, Loader B)
```

**Nhưng cả hai đều implements chính xác một runtime interface:**

```text
(api.Message, HostLoader)
```

Host có thể cast từng implementation object về `api.Message`, sau đó gọi `message()` theo interface chung. Không cần cast object của plugin A thành class implementation do plugin B định nghĩa.

### File 2: src/host/api/Message.java

```java
package api;

public interface Message {
    String message();
}
```

File này **thuộc ứng dụng host**, được compile vào `build/host` và đặt trong host application's classpath. Nó **không** được đóng bản thứ hai vào `plugin.jar` của giải pháp đúng.

### File 3: src/plugin/impl/HelloPlugin.java

```java
package impl;

import api.Message;

public final class HelloPlugin implements Message {
    @Override
    public String message() {
        return "hello-from-plugin";
    }
}
```

Khi biên dịch plugin, compiler phải nhìn thấy host API qua `-cp build/host`. Nhưng **compile-time classpath không đồng nghĩa phải đóng bản API vào JAR plugin**. `plugin.jar` sẽ chỉ chứa `impl/HelloPlugin.class`. Khi JVM resolve interface của plugin, parent loader của plugin phải trả về chính `api.Message` của host.

### Khi nào nên dùng shared API?

- Host cần gọi các method của plugin qua contract rõ ràng.
- Có nhiều plugin loaders sống cạnh nhau, mỗi loader chứa implementation/dependency khác nhau.
- Cần hot reload implementation nhưng host API ổn định.
- Tránh dùng reflection cho mọi operation.
- Muốn public contract có thể kiểm thử về Java source và binary compatibility.

**Đừng ép plugin implementation objects với nhau:**

```java
// KHÔNG làm với implementation từ loader khác:
// HelloPluginFromA typed = (HelloPluginFromA) objectFromB;

// NÊN:
// Message typed = (Message) objectFromAOrB;
```

Hai dòng trên là **pseudocode** vì các tên `HelloPluginFromA` và `objectFromB` không phải class/biến Java đã khai báo. Trong chương trình đầy đủ, code sử dụng trực tiếp interface `Message`.

## 5. Chương trình đầy đủ: LoaderIdentityDemo.java

**File `src/app/LoaderIdentityDemo.java`** tạo cả tình huống cast hỏng và tình huống đã sửa.

```java
import api.Message;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL classes = Path.of("build/duplicate")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> a = Class.forName("dup.Token", true, left);
            Class<?> b = Class.forName("dup.Token", true, right);
            Object rightObject =
                    b.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class object: "
                    + (a == b));
            System.out.println("distinct defining loaders: "
                    + (a.getClassLoader() == left
                       && b.getClassLoader() == right));
            System.out.println("same runtime module: "
                    + (a.getModule() == b.getModule()));

            try {
                a.cast(rightObject);
                System.out.println("cross-loader cast: succeeded");
            } catch (ClassCastException ex) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }
        }

        URL pluginJar = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();
        ClassLoader hostLoader = Message.class.getClassLoader();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[]{pluginJar}, hostLoader);
             URLClassLoader second = new URLClassLoader(
                     new URL[]{pluginJar}, hostLoader)) {

            Class<?> p1 = Class.forName(
                    "impl.HelloPlugin", true, first);
            Class<?> p2 = Class.forName(
                    "impl.HelloPlugin", true, second);

            Message m1 = (Message) p1
                    .getDeclaredConstructor().newInstance();
            Message m2 = (Message) p2
                    .getDeclaredConstructor().newInstance();

            System.out.println("plugin impl classes identical: "
                    + (p1 == p2));
            System.out.println("shared host interface: "
                    + (p1.getInterfaces()[0] == Message.class
                       && p2.getInterfaces()[0] == Message.class));
            System.out.println("both cast to host API: "
                    + (m1 instanceof Message
                       && m2 instanceof Message));
            System.out.println("first plugin result: "
                    + m1.message());
            System.out.println("second plugin result: "
                    + m2.message());
        }
    }
}
```

### Cơ chế của phần thứ nhất

- `left` và `right` có **cùng URL** trỏ `build/duplicate` nhưng là **hai object loader khác nhau**.
- Vì `dup.Token` không có trong platform loader, `left` và `right` mỗi bên định nghĩa riêng một class từ cùng bytes.
- `a.getName().equals(b.getName()) == true`, nhưng `a == b == false`.
- Hai classes nằm trong **hai unnamed modules khác nhau** gắn với hai loaders (trong ví dụ), nên `a.getModule() == b.getModule()` là `false`.
- `a.cast(rightObject)` cố cast instance của B sang A: JVM từ chối như mong đợi.

### Cơ chế của phần thứ hai

- `Message.class` được host/system loader định nghĩa nhờ `build/host` có trong `-cp`.
- Hai plugin loaders dùng **chính loader của `Message.class` làm parent**.
- `plugin.jar` chỉ chứa implementation; `impl.HelloPlugin` do mỗi child loader tự định nghĩa.
- Khi load interface `api.Message`, parent trả về một `Class<?>` chung.
- Dù `p1 != p2`, cả hai instances có thể cast về cùng `Message` và gọi `message()` an toàn.
- Demo dùng `p1.getInterfaces()[0]` vì `HelloPlugin` của demo có đúng một direct interface. Trong ứng dụng thật, đừng dựa vào index 0; dùng `Message.class.isAssignableFrom(p1)` và kiểm tra interface hierarchy.

## 6. Lệnh biên dịch, đóng JAR và chạy

Từ thư mục gốc chứa `src`, thực hiện:

```bash
javac --release 17 -d build/duplicate src/dup/dup/Token.java
javac --release 17 -d build/host src/host/api/Message.java
javac --release 17 -cp build/host -d build/plugin src/plugin/impl/HelloPlugin.java
jar --create --file plugin.jar -C build/plugin .
javac --release 17 -cp build/host -d build/app src/app/LoaderIdentityDemo.java
```

Trên **Linux/macOS**, dấu ngăn cách nhiều entries trong Java classpath là `:`:

```bash
java -cp "build/app:build/host" LoaderIdentityDemo
```

Trên **Windows PowerShell/CMD**, classpath separator là `;`:

```powershell
java -cp "build/app;build/host" LoaderIdentityDemo
```

Không đưa `build/duplicate`, `build/plugin` hoặc `plugin.jar` vào **host application classpath**. Nếu đặt chúng vào đó, host/system loader có thể nạp `dup.Token` hoặc `impl.HelloPlugin` trước child theo parent-first, làm thí nghiệm **không còn đo hai defining loaders khác nhau**.

`Plugin.jar` không cần copy `api/Message.class`, vì `Message` đã có ở host. Tách compile classpath khỏi final plugin archive là mấu chốt thực hành.

### Stdout chính xác đã chạy trên OpenJDK 24 với javac --release 17

```text
same binary name: true
same Class object: false
distinct defining loaders: true
same runtime module: false
cross-loader cast: ClassCastException
plugin impl classes identical: false
shared host interface: true
both cast to host API: true
first plugin result: hello-from-plugin
second plugin result: hello-from-plugin
```

Mười dòng này không phụ thuộc tên thư mục tuyệt đối. Kết quả cho thấy vấn đề là **type identity theo loader**, và sửa đúng ở **shared parent API**, không phải sửa phép cast bằng ép cưỡng bức.

**Đây là một test chức năng, không phải chứng minh plugin được sandbox.** Plugin classes chạy trong cùng JVM process; loaders không tự cấp/thu hồi quyền filesystem/network.

## 7. Phản ví dụ: plugin đóng gói lại API và dùng child-first

Một nguồn lỗi rất thường gặp:

```text
Host:
  build/host/api/Message.class
  (defined by system ClassLoader)

Plugin JAR:
  api/Message.class           <-- bản sao API bị đóng nhầm
  impl/HelloPlugin.class

Child-first PluginLoader:
  ưu tiên api.* từ plugin JAR
  ưu tiên impl.* từ plugin JAR
```

Lúc này:

```text
Host API:
    (api.Message, HostLoader)

Plugin API:
    (api.Message, PluginLoader)

Plugin implementation:
    (impl.HelloPlugin, PluginLoader)
    implements (api.Message, PluginLoader)
```

Dù `HelloPlugin` có khai báo source `implements api.Message`, nó **implements bản API mà child loader tự định nghĩa**, không phải API của host. Host nhìn nó qua `Message.class.isAssignableFrom(pluginClass)` sẽ được `false`. Cast sang `api.Message` của host ném `ClassCastException`.

### Tạo JAR lỗi có chứa bản sao API

Sau khi làm xong phần build mục 6, chạy:

```bash
jar --create --file plugin-with-api.jar \
    -C build/plugin . \
    -C build/host api/Message.class
```

Trên Windows PowerShell, chạy cùng lệnh trên **một dòng**:

```powershell
jar --create --file plugin-with-api.jar -C build/plugin . -C build/host api/Message.class
```

`plugin-with-api.jar` chứa cả `impl/HelloPlugin.class` và `api/Message.class`. Đây là artifact **cố ý sai** để tái hiện bug, không được dùng làm plugin artifact đã sửa.

### File 5: src/app/DuplicateApiDemo.java

```java
import api.Message;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class DuplicateApiDemo {
    static final class ChildFirst extends URLClassLoader {
        ChildFirst(URL url, ClassLoader parent) {
            super(new URL[]{url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> c = findLoadedClass(name);

                if (c == null) {
                    if (name.startsWith("api.")
                            || name.startsWith("impl.")) {
                        try {
                            c = findClass(name);
                        } catch (ClassNotFoundException missing) {
                            c = super.loadClass(name, false);
                        }
                    } else {
                        c = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(c);
                }
                return c;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin-with-api.jar")
                .toAbsolutePath().toUri().toURL();

        try (ChildFirst loader = new ChildFirst(
                jar, Message.class.getClassLoader())) {

            Class<?> childApi = Class.forName(
                    "api.Message", false, loader);
            Class<?> plugin = Class.forName(
                    "impl.HelloPlugin", true, loader);
            Object instance =
                    plugin.getDeclaredConstructor().newInstance();

            System.out.println("same api binary name: "
                    + childApi.getName()
                              .equals(Message.class.getName()));
            System.out.println("same api Class object: "
                    + (childApi == Message.class));
            System.out.println("plugin implements child api: "
                    + (plugin.getInterfaces()[0] == childApi));
            System.out.println("host API assignable: "
                    + Message.class.isAssignableFrom(plugin));

            try {
                Message typed = (Message) instance;
                System.out.println("host API cast: succeeded");
            } catch (ClassCastException expected) {
                System.out.println(
                        "host API cast: ClassCastException");
            }
        }
    }
}
```

### Vì sao override loadClass có khóa?

Ví dụ child-first này chỉ phục vụ chứng minh bug. Tuy nhiên để tránh tự tạo thêm race/double-define, code vẫn:

1. Khóa `synchronized(getClassLoadingLock(name))`.
2. Kiểm tra `findLoadedClass(name)`.
3. Thử child-first cho `api.` và `impl.` rồi fallback parent qua `super.loadClass(name,false)`.
4. Gọi `resolveClass` khi `resolve == true`.

**Đây không phải classloader production đã qua review**. Trong hệ thống thật, policy child-first phải cân nhắc protected packages (`java.`), class-loading locks, package sealing, certificates, module access, dependency API và security boundaries. Đặc biệt, **không nên child-first cho chính gói API chia sẻ với host**.

### Biên dịch và chạy ví dụ lỗi duplicate API

```bash
javac --release 17 -cp build/host -d build/app src/app/DuplicateApiDemo.java
```

Linux/macOS:

```bash
java -cp "build/app:build/host" DuplicateApiDemo
```

Windows:

```powershell
java -cp "build/app;build/host" DuplicateApiDemo
```

**Stdout đã kiểm chứng bằng OpenJDK 24, bytecode build với `--release 17`:**

```text
same api binary name: true
same api Class object: false
plugin implements child api: true
host API assignable: false
host API cast: ClassCastException
```

Cả host và child đều có `api.Message` theo cùng binary name, nhưng `Class<?>` khác nhau; plugin implements bản child API. Đây là **đúng loại lỗi** khi plugin JAR đóng trùng host API và child-first loader làm shadow API của host.

## 8. Sửa triệt để duplicate API

Để sửa trường hợp mục 7 trong ứng dụng thật:

1. **Đưa host API vào shared parent classpath/module** và đảm bảo nó được nạp bởi một loader ổn định.
2. **Không đóng API class thứ hai vào plugin JAR**. Nếu plugin chỉ cần API lúc compile, đánh dấu dependency dạng *provided/compileOnly* phù hợp với Maven/Gradle.
3. **Delegation policy cho API namespace phải parent-first**. Nếu bắt buộc child-first cho third-party libraries để hỗ trợ nhiều versions, tách rule rõ ràng: `java.` và `api.` của host là parent-first, còn `impl.`/thư viện plugin do child xử lý theo thiết kế.
4. **Tạo lại plugin loader** sau thay đổi. Một loader đã định nghĩa class sai không tự thay definition chỉ vì bạn xóa bản `api/Message.class` khỏi JAR trên disk.
5. **Kiểm tra type identity** bằng `api.Message.class.isAssignableFrom(implClass)` trước khi cast trong hệ plugin.
6. **Chạy integration test đúng topology loader thực tế**. Unit test chỉ chạy tất cả lớp trên một classpath không thể tái hiện bug do nhiều defining loaders.
7. **Quản lý version của API hợp đồng**. Shared API phải binary-compatible giữa host và plugin; nếu interfaces/method signatures thay đổi không tương thích, còn có thể gặp `NoSuchMethodError`, `AbstractMethodError` hoặc lỗi linkage khác.

### Maven: plugin API dependency dạng provided

Một fragment `pom.xml` của plugin:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>plugin-api</artifactId>
    <version>1.0.0</version>
    <scope>provided</scope>
</dependency>
```

Đây là **fragment cấu hình minh họa**, tọa độ artifact `com.example:plugin-api:1.0.0` là tên ví dụ. `provided` nói dependency có sẵn lúc compile nhưng thông thường không được đóng thành runtime transitively included dependency của plugin; nếu dùng shaded/assembly plugin, kiểm tra artifact thật vì custom packaging rules có thể vẫn copy nó.

Với Maven Shade, kiểm tra dependencies/exclusions/relocations để bảo đảm `api.Message` không bị đóng một bản khác vào plugin. **Relocate API shared** không tạo ra shared type identity; nó sẽ đổi tên API và phá contract với host.

### Gradle: dùng compileOnly cho shared API

Một fragment Gradle Groovy DSL:

```groovy
dependencies {
    compileOnly 'com.example:plugin-api:1.0.0'
}
```

Đây là cú pháp minh họa. `compileOnly` không tự đảm bảo một uber-JAR do task đóng gói tùy chỉnh tạo ra không sao chép API; cần xem nội dung final plugin JAR.

### Kiểm tra JAR có bản trùng API

```bash
jar tf plugin.jar
jar tf plugin-with-api.jar
```

Ở ví dụ:

```text
plugin.jar:
  impl/HelloPlugin.class

plugin-with-api.jar:
  impl/HelloPlugin.class
  api/Message.class
```

Hai đoạn này **trích lược các entry liên quan**, không phải full output của `jar tf` (vì còn META-INF/MANIFEST.MF). Trong production, scan tất cả plugin artifacts và nested/shaded JARs nếu runtime loader giải nén/tải chúng.

## 9. Vì sao parent-first quan trọng khi sửa lỗi cast?

`ClassLoader.loadClass` mặc định kiểm tra lớp đã nạp, hỏi parent trước rồi mới gọi `findClass` của child. Khi child `loadClass("api.Message")` nhưng parent đã cung cấp API đó, **defining loader là parent**; child chỉ có thể đóng vai trò initiating loader. Vì vậy bản API trùng có trong plugin JAR vẫn có thể *chưa* gây lỗi khi loader parent-first.

Phản ví dụ ở mục 7 cố tình áp dụng **child-first cho `api.*`**, khiến plugin định nghĩa một `api.Message` khác và host cast thất bại. Cách sửa là giữ `api.*`/shared contracts parent-first, tách namespace implementation và dependencies riêng. Nếu cần child-first cho thư viện private, phải giữ `getClassLoadingLock`, `findLoadedClass`, delegation, `resolveClass` và phân loại exception đúng; không áp một policy cho mọi package.

**Kiểm chứng thực tế:** `Message.class.isAssignableFrom(pluginClass)` cùng `pluginClass.getClassLoader()` đáng tin hơn việc đối chiếu class name hay source JAR. TCCL và reflective access không thay đổi runtime identity đã được JVM định nghĩa.

## 10. Chẩn đoán ClassCastException thực tế

Thông báo lỗi có thể giống:

```text
java.lang.ClassCastException: class dup.Token cannot be cast to class dup.Token
(dup.Token is in unnamed module of loader ...;
 dup.Token is in unnamed module of loader ...)
```

Đây là **mẫu thông báo**; OpenJDK version, tên loader và module metadata có thể làm format/wording khác. Phần “cannot be cast to chính nó” không vô lý nếu **hai runtime types** có defining loaders khác nhau.

### Mẫu log type identity đúng cách

```java
static void describe(Object obj) {
    if (obj == null) {
        System.out.println("<null>");
        return;
    }
    Class<?> type = obj.getClass();
    System.out.println("typeName=" + type.getName());
    System.out.println("typeIdentity=" +
            System.identityHashCode(type));
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("loaderIdentity=" +
            System.identityHashCode(type.getClassLoader()));
    System.out.println("module=" + type.getModule());
}
```

Đây là **snippet method** đặt trong class bất kỳ; dùng `System.identityHashCode` hỗ trợ phân biệt objects trong logs, nhưng hash có thể collision — **không dùng hash thay phép so sánh `==`**.

Các điểm cần ghi riêng cho **expected type** và **actual object**:

- `expected.getName()` và `actual.getClass().getName()`.
- `expected == actual.getClass()`.
- `expected.isInstance(actual)`.
- `expected.isAssignableFrom(actual.getClass())`.
- `expected.getClassLoader()` và `actual.getClass().getClassLoader()`, so sánh **identity**.
- `getModule()` và vị trí source (`ProtectionDomain.CodeSource`) khi có.
- Khi có custom plugin loader, ghi `pluginId`, loader generation, parent và source JAR/version.

**Cẩn thận `null`:** Bootstrap loader được biểu diễn bằng `null` trong `Class.getClassLoader()`. Hai classes có loader null chưa tự kết luận mọi điều về type identity nếu bạn chưa xem tên/module; tuy nhiên đối với `String.class`, đây là expected bootstrap behavior.

### Đừng chỉ nhìn tên JAR

Hai URLClassLoader có thể đọc **chính một `plugin.jar`** nhưng tạo hai implementation classes không tương thích với nhau. Ngược lại, hai classes đọc từ hai JAR khác nhau có thể cùng implement **một host API** và cùng cast thành interface đó.

`CodeSource.location` giúp debug artifact/version, nhưng **không thay thế** so sánh defining-loader identity. Với generated classes, custom loaders hoặc JDK runtime classes, `CodeSource` có thể `null`.

### JVM class loading logs

Với OpenJDK/HotSpot Java 17+:

```bash
java -Xlog:class+load=info -cp "build/app:build/host" LoaderIdentityDemo
```

Đây là câu lệnh Linux/macOS; Windows thay dấu `:` bằng `;`. `-Xlog:class+load=info` in nhiều lines thêm vào output, có thể cho biết nguồn JAR/directory/loader; lệnh **không có exact stdout giống mục 6** vì logging chi tiết.

Log source path giúp xác định artifact, nhưng muốn biết class đang chạy thuộc **instance loader nào**, cần kết hợp `getClassLoader()`, object identity và debugger/heap data. `-Xlog` là tùy chọn HotSpot/Unified Logging, không phải API bảo đảm trên mọi JVM vendor.

## 11. Một số nguyên nhân gần giống nhưng cách sửa khác

| Triệu chứng | Nguyên nhân có thể | Cách phân biệt |
| --- | --- | --- |
| `ClassCastException` dù tên giống nhau | Hai defining loaders định nghĩa cùng binary name. | So `Class<?> ==` và `getClassLoader()`. |
| `ClassCastException` giữa hai tên khác nhau | Hai unrelated types bình thường. | Xem actual/expected names và hierarchy trước. |
| `NoClassDefFoundError` khi nạp plugin | Class API/dependency thiếu hoặc định nghĩa không tìm được. | Kiểm tra cause, loader search/delegation và JAR. |
| `ClassNotFoundException` khi `Class.forName` | Caller chọn sai loader hoặc dependency không có. | Truyền đúng loader, kiểm tra loader hierarchy/classpath. |
| `LinkageError` “loader constraint violation” | JVM phát hiện hai loader resolve cùng type trong signature/override context không nhất quán. | Xem offending class names, method descriptors, loader identities. |
| `NoSuchMethodError` | API binary version mismatch, method signature thay đổi. | So API contract/version và `javap` signatures. |
| `AbstractMethodError` | Implementation không khớp interface/abstract method được runtime mong đợi. | Build lại plugin theo contract binary phù hợp. |
| `IllegalAccessError` / `InaccessibleObjectException` | Java/JPMS access policies hoặc reflection boundaries. | Xem module readability/exports/opens, khác lỗi type identity. |
| Duplicate class definition `LinkageError` | **Cùng loader** cố define lại một binary name. | Kiểm tra `findLoadedClass`/`getClassLoadingLock` và override `loadClass`. |
| `UnsupportedClassVersionError` | Runtime JVM không hỗ trợ class-file major/minor. | Đọc version bytecode/JDK, không phải cast issue. |

Không sửa bằng cách catch `ClassCastException` rồi bỏ qua; điều đó chỉ che lỗi kiến trúc và có thể làm plugin hoạt động nửa chừng.

### Loader constraint violation không giống lỗi cast

Java linking có **loading constraints** cho những type xuất hiện trong inherited method signatures hoặc các tình huống liên kết yêu cầu type identity nhất quán giữa loaders. Nếu một loader đã nạp tên `api.Message` bằng class A nhưng một hierarchy liên quan yêu cầu cùng tên được nhìn thấy như class B, JVM có thể ném `LinkageError` ngay khi kiểm tra constraints.

`ClassCastException` là lỗi cast của object không tương thích; `LinkageError` có thể xuất hiện sớm hơn trong loading/linking. Hai hiện tượng có chung gốc “lớp trùng tên nhưng loader khác”, nhưng **không phải subtype exception giống nhau**.

## 12. Chú ý với ServiceLoader, TCCL và framework containers

`ServiceLoader` có thể được dùng để tìm plugin providers, nhưng bạn phải đảm bảo **service interface** do loader được cả host và provider nhìn thấy theo cùng identity.

Ví dụ contract mong đợi:

```java
ServiceLoader<Message> services =
        ServiceLoader.load(Message.class, pluginLoader);
```

Đây là **snippet** cần `import java.util.ServiceLoader;` cùng biến `pluginLoader`. Nó còn yêu cầu service registration metadata (`META-INF/services/api.Message`) hoặc module `provides`/`uses` đúng. Dù `ServiceLoader` tìm được class provider, nếu provider thực hiện **bản API khác loader**, có thể lỗi vì không phải subtype của service.

Một vài container dùng thread context class loader (TCCL) để chọn provider/dependency:

```java
Thread t = Thread.currentThread();
ClassLoader old = t.getContextClassLoader();
try {
    t.setContextClassLoader(pluginLoader);
    // Thực hiện provider lookup / plugin call...
} finally {
    t.setContextClassLoader(old);
}
```

TCCL thay **ngữ cảnh tìm** cho API có hỗ trợ nó; nó **không tái định nghĩa** bản `api.Message` đã nạp bởi host. Thay TCCL cũng không biến `impl.HelloPlugin` đã định nghĩa sai thành subtype của host interface.

Application servers (Tomcat, Jakarta EE), OSGi, Spring Boot DevTools hoặc plugin frameworks có loader hierarchy tùy biến. Nên inspect topology cụ thể thay vì mặc định mọi loader là parent-first hoặc mọi dependency nằm trên system classpath.

## 13. Vòng đời hot reload: tránh ép kiểu qua generation cũ

Trong một hệ plugin hot reload:

```text
Generation 1:
    loader-v1 -> impl.HelloPlugin (runtime type 1)

Generation 2:
    loader-v2 -> impl.HelloPlugin (runtime type 2)

Host:
    api.Message -> định nghĩa một lần, sống xuyên generations
```

Một object `impl.HelloPlugin` của loader-v1 **không** cast được thành concrete type của loader-v2, kể cả hai cùng có source. Nhưng cả hai có thể cast sang `api.Message` nếu API nằm ở host loader và binary-compatible.

Để dỡ generation cũ:

1. Ngăn tasks mới dùng object implementation cũ.
2. Unregister event handlers, service provider references và caches giữ `Class<?>`/plugin instances.
3. Dừng tasks, xử lý TCCL/ThreadLocal có thể giữ loader cũ.
4. Đóng `URLClassLoader` nếu là loại hỗ trợ `close`.
5. Bỏ host references đến objects/`Class<?>`/loader generation cũ.
6. Quan sát reachability/GC nếu cần, nhưng không khẳng định class unloading diễn ra ngay.

`URLClassLoader.close()` **không xóa classes đã load**, không sửa type identity và không “ép” old instance thành new generation. Nó đóng tài nguyên loader theo API; muốn thay implementation, dùng loader mới và đổi các references ở application layer.

### Không truyền implementation object qua boundary như kiểu public API

Nếu host API khai báo:

```java
public interface Message {
    String message();
}
```

đây là contract an toàn trong demo vì chỉ dùng Java `String` thuộc runtime và được host/plugin chia sẻ.

Nhưng nếu API trả về `impl.HelloPlugin` hoặc một kiểu `plugin.private.Data` do child loader định nghĩa, host có thể không resolve/cast được kiểu đó. Thiết kế public plugin contract bằng **các types thuộc host/shared API hoặc Java/JDK types** có identity thống nhất; sử dụng DTO/boundary protocol phù hợp khi cách ly sâu hơn.

Tham số generic cũng cần lưu ý: `List<PluginImpl>` vẫn có thể mang instance của class do plugin loader định nghĩa; **type erasure không biến implementation types thành shared types** và có thể ném cast ở nơi đọc phần tử.

## 14. Anti-pattern và hướng sửa thực tế

| Sai lầm | Tại sao lỗi | Cách sửa |
| --- | --- | --- |
| “Cùng binary name thì cast được.” | Thiếu defining loader identity. | So `Class<?>` và loader, dùng shared abstraction. |
| “Cùng JAR bytes thì cùng Class.” | Hai loader instances vẫn tạo hai namespaces. | Tạo một loader khi thực sự cần cùng concrete type, hoặc dùng shared API. |
| Đóng `plugin-api.jar` vào cả host và child-first plugin | Hai runtime copies `api.Message`. | Provided/compileOnly API; parent-first API namespace. |
| Dùng child-first cho cả `api.*` và `impl.*` | Plugin tự định nghĩa API thay vì dùng host API. | Child-first selective cho implementation deps; host API always parent-first. |
| Chỉ xóa file API khỏi plugin JAR khi JVM đã load | Class đã được define không tự thay thế. | Tạo class loader generation mới/restart và rebuild artifact. |
| Dùng reflection làm “sửa” type identity | Chỉ gọi method qua reflection, không tạo subtyping thật. | Shared interface or explicit data transfer boundary. |
| Ép `ClassLoader.getSystemClassLoader()` sang `URLClassLoader` | Java 9+ system loader thường không phải URLClassLoader. | Dùng API phù hợp hoặc custom loader đúng loại. |
| Thấy `CodeSource.location` giống nhau nên bỏ qua loader | Archive/path không quyết định Class identity. | Xem `getClassLoader()` trực tiếp. |
| Đổi TCCL và kỳ vọng cast cũ thành công | TCCL không sửa class đã định nghĩa. | Sửa owner loader/API hierarchy, nạp lại generation. |
| Lặp `defineClass` với cùng name và loader | JVM từ chối duplicate class definition. | `findLoadedClass` và proper locking/loader policy. |
| Tắt JPMS/`--add-opens` để sửa `ClassCastException` | Mở reflective access không hợp nhất Class identities. | Sửa định nghĩa API/loader graph. |
| Chỉ kiểm tra bằng `instanceof` với class đã link tại host | Có thể thấy false nhưng chưa hiểu loader. | Log expected/actual `Class<?>` + loaders + modules. |

## 15. Checklist từng bước khi một plugin không ép kiểu được

1. **Đọc lỗi chính xác.** Xác nhận thực sự là `ClassCastException`, `LinkageError` loader constraint, hay lỗi khác.
2. **Ghi expected class:** binary name, `Class<?>` object, defining loader, module, version.
3. **Ghi actual class:** `object.getClass()`, name, loader, module, source location nếu có.
4. **So sánh bằng `==`**, không chỉ `getName()` hay `toString()`.
5. **Kiểm tra API dùng chung:** `HostApi.class == pluginClass.getInterfaces()[...]` có phù hợp, hoặc dùng `HostApi.class.isAssignableFrom(pluginClass)`.
6. **Kiểm tra JAR:** bản sao `api.*` có bị shading/assembly/loader copy vào plugin không?
7. **Kiểm tra delegation:** parent-first cho host API chưa, child-first có vô tình shadow shared packages?
8. **Kiểm tra runtime:** dependency/JAR nào đang thực sự được load; xác minh parent loader vs child loader.
9. **Sửa build/deployment:** loại duplicate API khỏi plugin artifact, pin API version, chia shared loader.
10. **Thay loader generation:** không kỳ vọng runtime type đã định nghĩa tự biến đổi.
11. **Chạy integration test** với ít nhất hai child loader instances và hai phiên bản plugin nếu dự án hỗ trợ hot reload.
12. **Quản lý lifecycle** để old instances/caches không bị đưa sang generation mới.

Không coi plugin JAR có checksum giống nhau là đủ; checksum xác minh bytes, còn vấn đề ở **defining loader identity**.

## 16. Bài tập tự kiểm tra và đáp án

1. **Hai loader riêng cùng đọc một file `dup.Token.class`, vì sao `Class<?>` khác nhau?**  
   Runtime identity gồm binary name và defining loader; hai instances loader độc lập định nghĩa hai runtime types.

2. **`Class.getName()` của A và B giống nhau chứng minh cast hợp lệ?**  
   Không. So identity `A == B` hoặc quan hệ `isAssignableFrom`.

3. **Nếu cùng một loader gọi `loadClass("dup.Token")` nhiều lần, có tạo nhiều classes?**  
   Theo đường chuẩn, `findLoadedClass` và synchronization tránh định nghĩa lại; trả một `Class<?>` cho name/loader thích hợp.

4. **Khi hai implementations từ hai plugin loaders khác nhau, cast về cùng host interface có thể thành công không?**  
   Có, nếu cả hai implement đúng **một** runtime interface do parent/host định nghĩa.

5. **Plugin JAR có bản sao API nhưng parent-first API lookup trả host API, cast có thể thành công?**  
   Có thể. Bản sao trong JAR vẫn là rủi ro thiết kế/packaging; nếu child-first hoặc hierarchy đổi thì có thể lỗi.

6. **Tại sao `Message.class.isAssignableFrom(pluginClass)` false trong `DuplicateApiDemo`?**  
   Plugin implements `api.Message` do child loader định nghĩa; host `Message.class` có defining loader khác.

7. **Chỉ sửa TCCL có biến một class child API thành host API không?**  
   Không. TCCL chỉ giúp lookup trong các APIs có dùng nó, không sửa Class identity đã tồn tại.

8. **`CodeSource.location` giống nhau có nghĩa hai classes runtime giống nhau?**  
   Không. Cùng JAR có thể được load bởi nhiều child loader instances.

9. **`URLClassLoader.close()` có làm instance cũ cast được sang class phiên bản mới?**  
   Không. Close không redefine lớp và không thay type identity.

10. **Ứng dụng cần hai plugin dùng dependencies khác version, nên cast implementation với nhau không?**  
    Không. Dùng shared host API, DTO hoặc giao thức rõ ràng.

11. **`ClassCastException` và `LinkageError` duplicate definition giống nhau?**  
    Không. ClassCastException là cast sai; duplicate definition do cùng defining loader cố định nghĩa trùng name; loader constraint errors thuộc linking.

12. **Trong Maven/Gradle, làm sao giảm nguy cơ đóng trùng host API?**  
    `provided` hoặc `compileOnly` tương ứng, kiểm tra final JAR và giữ parent-first API namespace.

13. **Vì sao cần kiểm thử trên loader topology của production?**  
    Unit test dùng một app loader duy nhất có thể che class identity mismatch xảy ra với custom child loaders.

14. **Khi API contract nhận tham số thuộc package private của plugin, có vấn đề gì?**  
    Host có thể không resolve được cùng class identity cho type ấy; public boundary nên dùng shared/host types.

## 17. Tài liệu chuẩn

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `findLoadedClass`, `defineClass` và defining loader.
- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity là binary name + defining loader; initiating vs defining loader và loading constraints.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `cast`, `isInstance`, `isAssignableFrom`, `getClassLoader`, `getModule`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): constructors, URL sources, `close`.
- [Java SE 21 — ClassCastException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCastException.html): ý nghĩa phép ép kiểu thất bại.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): SPI service/provider identity và loader.
- [Java SE 21 — Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html): runtime packages và package metadata.
