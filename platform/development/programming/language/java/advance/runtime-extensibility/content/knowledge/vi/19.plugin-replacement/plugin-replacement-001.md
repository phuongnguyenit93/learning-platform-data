# Phân biệt reload bộ nhớ đệm SPI, thay đối tượng và thay định nghĩa lớp

Trong ứng dụng Java có khả năng mở rộng bằng plugin, từ **“reload”** thường bị dùng cho ba hành động khác nhau:

1. Xóa bộ nhớ đệm khám phá service của `ServiceLoader` để duyệt provider lại.
2. Thay **đối tượng provider đang được ứng dụng sử dụng**, chẳng hạn hoán đổi một reference trong registry.
3. Nạp **định nghĩa lớp mới** khi thay phiên bản bytecode/JAR, thường bằng một `ClassLoader` mới hoặc cơ chế tái định nghĩa lớp chuyên dụng.

Chúng **không tương đương**. Gọi `ServiceLoader.reload()` không tự thay bytecode; tạo một object provider mới không chứng minh class đã thay đổi; còn có định nghĩa class mới cũng không tự chuyển các request đang chạy sang object mới.

Bài này xây dựng ba mức thay thế, giải thích ranh giới và vòng đời, rồi chạy một chương trình **Java 17** dùng hai JAR plugin cùng chứa `demo.plugin.GreetingProvider` nhưng có implementation khác nhau. Mọi kết quả quan sát được đều có thể kiểm chứng qua object identity, class identity và `ClassLoader`.

## 1. Ba lớp trạng thái cần theo dõi

Khi một host Java sử dụng SPI, có ít nhất ba thành phần độc lập:

```text
SPI chung: demo.spi.Greeter
           |
           v
  ServiceLoader<Greeter>      (cache khám phá/instance)
           |
           v
  Greeter provider instance  (object được ứng dụng giữ)
           |
           v
  Class<?> + ClassLoader     (định nghĩa bytecode được JVM nạp)
```

Nếu ứng dụng có registry giữ provider đang dùng:

```text
ServiceLoader instance  ---->  cached provider A
                                    |
Host registry ----------->  active provider A
                                    |
                                Class A
                                    |
                           defining ClassLoader
```

Sau đó có thể xảy ra ba thay đổi **riêng biệt**:

| Hành động | Thứ được thay đổi trực tiếp | Điều **không tự thay đổi** |
|---|---|---|
| `ServiceLoader.reload()` | Cache provider thuộc **đúng instance** `ServiceLoader` | Đối tượng cũ host giữ, `Class<?>` đã định nghĩa, classpath, JAR trên đĩa |
| `active.set(newProvider)` | Reference active mà host dùng để chọn provider | Cache của `ServiceLoader`, bytecode/class hiện có, reference cũ đã được các request giữ |
| Nạp JAR mới bằng loader mới | Có thể tạo `Class<?>` mới và instance từ bytecode mới | Reference active, phiên đang xử lý, object/class của loader cũ |

Một thao tác **triển khai plugin mới** hoàn chỉnh có thể cần thực hiện cả ba theo một chiến lược; nhưng phải ghi rõ ai chịu trách nhiệm từng bước. Không nên coi `reload()` là API hot deployment toàn diện.

## 2. ServiceLoader là cơ chế khám phá provider, không phải bộ cập nhật mã

Trên **classpath**, các provider được đăng ký bằng tài nguyên:

```text
META-INF/services/<tên nhị phân đầy đủ của service type>
```

Ví dụ SPI `demo.spi.Greeter` sẽ có tài nguyên:

```text
META-INF/services/demo.spi.Greeter
```

Trong file đăng ký có tên đầy đủ của implementation, ví dụ:

```text
demo.plugin.GreetingProvider
```

`ServiceLoader.load(Greeter.class, loader)` sẽ dùng class loader được truyền để tìm service configuration, kiểm tra kiểu provider và khởi tạo provider theo quy tắc tương ứng. Các provider thường được phát hiện/khởi tạo **lười** khi ứng dụng duyệt iterator hoặc stream; chỉ tạo đối tượng `ServiceLoader` chưa bảo đảm mọi provider đã được instantiate.

Một instance `ServiceLoader` duy trì **cache các provider đã được nạp**. Khi lặp lại bằng `iterator()` mà chưa gọi `reload()`, provider đã được cache thường chính là **object từng trả trước đó**. Điều này cho phép cùng một service loader trả lại object mà nó đã nạp, thay vì xây mới mỗi lần duyệt.

### Chính xác `reload()` làm gì?

```java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);

Greeter before = services.iterator().next();
services.reload();
Greeter after = services.iterator().next();
```

Đây là **trích đoạn minh họa**, giả định `Greeter`, `pluginLoader` đã có và service loader chỉ tìm được ít nhất một provider. Trong chương trình hoàn chỉnh ở dưới, ta kiểm tra luôn số lượng provider.

Hành vi cần nhớ:

- `services.reload()` **xóa cache** provider của `services`; lần duyệt tiếp theo có thể khám phá và khởi tạo provider lại. Với provider classpath có public constructor không tham số như ví dụ này, nó tạo một **instance mới**.
- `reload()` **không xóa object `before` mà ứng dụng đang giữ**. Reference `before` vẫn trỏ đến object cũ; nếu object chưa bị đóng theo chính sách ứng dụng, nó vẫn có thể sử dụng.
- `reload()` **không xóa class khỏi JVM và không gọi `ClassLoader` mới**. Nếu provider class đã được định nghĩa bởi cùng loader, instance mới tiếp tục có cùng `Class<?>`.
- **Static fields, static caches và static initializer của lớp đã nạp không được reset chỉ vì reload service.** Instance mới vẫn nhìn thấy static state thuộc cùng class.
- `reload()` **không tự đưa một JAR mới vào classpath hoặc module path**, không thay một JAR đã mở, không cập nhật các URL của class loader, không chọn provider cho host.
- Iterator/stream đang dùng trước khi gọi `reload()` cần được bỏ và tạo vòng duyệt mới; đừng vừa duyệt vừa reload, vì có thể gặp lỗi do cache thay đổi.

`ServiceLoader` cũng không được bảo đảm thread-safe cho những thao tác dùng chung trên cùng instance. Nếu một luồng đang duyệt còn luồng khác gọi `reload()`, đừng kỳ vọng đó là quy trình cập nhật an toàn. Cần có đồng bộ và ownership phù hợp, hoặc xây một snapshot immutable riêng sau khám phá.

### Khi nào reload cache thực sự hữu ích?

Bạn có thể dùng `reload()` khi **cấu hình khám phá mà class loader hiện tại có khả năng nhìn thấy** đã thay đổi theo cách được hỗ trợ và muốn duyệt lại service. Tuy nhiên, không được suy ra rằng mọi cách “thả file JAR vào thư mục” sẽ được loader tự nhận. Với `URLClassLoader` đã tạo cố định từ URL JAR, gọi `reload()` **không tự thêm URL** mới.

Đặc biệt, nếu bytecode của một class đã được loader định nghĩa, reload không thay class definition đó. Để làm mới phiên bản implementation, cần giải quyết class loading hoặc instrumentation, không chỉ cache.

## 3. Thay đối tượng: chuyển reference active có kiểm soát

Giả sử host giữ provider đang hoạt động trong:

```java
AtomicReference<Greeter> active =
        new AtomicReference<>(oldProvider);
```

Khi có một provider object mới đủ điều kiện chạy:

```java
active.set(newProvider);
```

Đây là **trích đoạn**, không phải chương trình độc lập. `AtomicReference` bảo đảm việc đọc/ghi reference qua API đó có tính nguyên tử và phù hợp về visibility giữa các luồng, nhưng **không** tự tổ chức thay thế trọn vẹn mọi resource.

Các điểm quan trọng:

1. **Object identity đổi:** `active.get()` trả `newProvider` cho các lượt đọc sau khi reference được cập nhật.
2. **Class identity có thể không đổi:** nếu `oldProvider` và `newProvider` được tạo từ cùng class loader, `oldProvider.getClass() == newProvider.getClass()` là `true`.
3. **Reference cũ không biến mất:** một request đã làm `Greeter p = active.get()` trước lần thay vẫn có thể tiếp tục gọi `p` sau khi registry được đổi.
4. **Không tự đóng plugin cũ:** nếu object cũ giữ file, socket, thread, executor hoặc callback, ứng dụng phải xác định cách dừng/thu hồi.
5. **Không reset static state:** hai object khác nhau nhưng thuộc cùng `Class<?>` có thể vẫn chia sẻ static fields.

Ví dụ với provider có số thứ tự instance:

```text
v1#1:Java  <-- object đầu tiên
v1#2:Java  <-- object khác, cùng class và cùng static counter
```

Việc nhìn thấy `#2` thay cho `#1` chứng minh object khác nhau nhưng **không** chứng minh bytecode đã được thay.

Trong hệ thống đa luồng, `active.set(...)` chỉ là **đổi điểm vào**. Nếu plugin cũ không được phép bị dừng khi request đang chạy, host cần **quiescence / draining / lease / reference counting** hoặc giao thức chuyển giao phù hợp. Không đóng ngay class loader/resource cũ khi vẫn có request sử dụng nó.

## 4. Thay định nghĩa lớp: vấn đề nằm ở class loader

JVM phân biệt class không chỉ bằng tên đầy đủ. Về danh tính nạp lớp, một class được xác định bởi **tên nhị phân và class loader định nghĩa nó**:

```text
("demo.plugin.GreetingProvider", loaderV1)
    !=
("demo.plugin.GreetingProvider", loaderV2)
```

Ký hiệu trên là mô tả mô hình, không phải cú pháp Java.

Nếu hai plugin JAR đều chứa class có cùng tên `demo.plugin.GreetingProvider`:

- `loaderV1` có thể định nghĩa class này từ `plugin-v1.jar`.
- `loaderV2` có thể định nghĩa một class **cùng tên** từ `plugin-v2.jar`.
- Hai đối tượng `Class<?>` khác nhau: `v1.getClass() != v2.getClass()`.
- Những static fields của lớp thuộc hai class loader được giữ **riêng**.
- Nếu host dùng SPI đúng cách, cả hai class đều có thể được ép kiểu thành **cùng một interface** `demo.spi.Greeter`.

Để đạt điều cuối, host phải **chia sẻ định nghĩa SPI từ một class loader cha**. Nếu mỗi loader con tự định nghĩa bản sao `demo.spi.Greeter`, chúng là hai interface khác nhau dù có cùng tên; host có thể gặp `ClassCastException` hoặc `ServiceConfigurationError` khi provider không phải subtype của kiểu mà host yêu cầu.

Sơ đồ:

```text
                 Application ClassLoader (parent)
                      spi.jar + host.jar
                              |
                       demo.spi.Greeter
                              |
              +---------------+---------------+
              |                               |
        loaderV1                         loaderV2
     plugin-v1.jar                    plugin-v2.jar
              |                               |
  demo.plugin.GreetingProvider   demo.plugin.GreetingProvider
           Class #1                         Class #2
      static count = 2                  static count = 1
              |                               |
              +---------------+---------------+
                              |
                       host dùng Greeter
```

Trong demo, application classpath **không chứa provider JAR**. Bởi thế quy tắc delegation parent-first mặc định của `URLClassLoader` không khiến parent nạp nhầm provider. Mỗi child chỉ có URL trỏ tới đúng JAR của mình.

**Cảnh báo:** Nếu host classpath cũng chứa class provider trùng tên, parent-first có thể khiến child thấy class của parent thay vì class trong JAR riêng. Với kiến trúc plugin phức tạp, phải thiết kế namespace, package và quy tắc delegation rõ ràng. Không tùy tiện dùng child-first cho cả package SPI, vì như vậy có thể nhân đôi hợp đồng.

## 5. Ví dụ chạy được: cùng provider name, hai bản JAR

Bài toán: host biết duy nhất SPI `Greeter`, trong khi provider phiên bản 1 và 2 được đóng gói thành **hai artifact độc lập**, có cùng class name nhưng khác bytecode.

Ta sẽ quan sát ba giai đoạn:

1. `ServiceLoader` duyệt hai lần cho cùng cache → trả lại cùng instance.
2. Gọi `reload()`, duyệt lại → instance khác, class vẫn cùng.
3. Tạo loader mới trỏ tới JAR v2 và chuyển `active` sang provider mới → class khác, vẫn là cùng SPI chung.

### 5.1. Cây tệp

Tạo các tệp sau bên trong thư mục `spi-replacement-demo`:

```text
spi-replacement-demo/
├── contract/
│   └── src/demo/spi/Greeter.java
├── plugin-v1/
│   ├── src/demo/plugin/GreetingProvider.java
│   └── resources/META-INF/services/demo.spi.Greeter
├── plugin-v2/
│   ├── src/demo/plugin/GreetingProvider.java
│   └── resources/META-INF/services/demo.spi.Greeter
└── host/
    └── src/demo/host/Main.java
```

Khi biên dịch, ta tạo bốn JAR:

```text
dist/
├── spi.jar
├── host.jar
├── plugin-v1.jar
└── plugin-v2.jar
```

Không đặt hai phiên bản provider lên cùng application classpath. `host.jar` chỉ phụ thuộc `spi.jar` tại compile time, không import implementation cụ thể.

### 5.2. Hợp đồng SPI — chỉ một bản

Tệp `contract/src/demo/spi/Greeter.java`:

```java
package demo.spi;

public interface Greeter {
    String id();

    String greet(String name);
}
```

SPI giữ chữ ký ổn định. Những phiên bản plugin có thể thay mã nội bộ, nhưng đều `implements Greeter`. `id()` minh họa định danh nghiệp vụ; hai phiên bản cùng trả `"greeting"`, vì **chúng là hai bản thay thế của cùng chức năng**, không phải hai loại dịch vụ khác nhau.

Cần phân biệt định danh nghiệp vụ với **class identity**: hai provider cùng `id()` không có nghĩa là cùng object, cùng bytecode hoặc cùng class loader. Nếu host cùng lúc đăng ký nhiều provider có cùng ID vào **một registry đang hoạt động**, phải có chính sách chọn phiên bản rõ ràng.

### 5.3. Implementation phiên bản 1

Tệp `plugin-v1/src/demo/plugin/GreetingProvider.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class GreetingProvider implements Greeter {
    private static int constructed;
    private final int number = ++constructed;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public String greet(String name) {
        return "v1#" + number + ":" + name;
    }
}
```

`constructed` là static field tăng khi khởi tạo object; `number` lưu số thứ tự của từng instance. Ví dụ thực thi tuần tự, không chia sẻ constructor giữa luồng. Trong ứng dụng thực tế có concurrency, bộ đếm dùng để kiểm tra có thể cần `AtomicInteger` hoặc đồng bộ phù hợp.

### 5.4. Implementation phiên bản 2

Tệp `plugin-v2/src/demo/plugin/GreetingProvider.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class GreetingProvider implements Greeter {
    private static int constructed;
    private final int number = ++constructed;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public String greet(String name) {
        return "v2#" + number + ":" + name;
    }
}
```

Hai source file cùng khai báo `public final class GreetingProvider` trong `package demo.plugin`, nhưng **khác return value**. Mỗi source được biên dịch vào một output directory khác và đóng một JAR khác.

Nếu lấy cả hai source đưa cho một lời gọi `javac` với cùng package/class, sẽ đụng định nghĩa trùng. Cơ chế cô lập ở đây diễn ra **khi nạp class**, không phải khi biên dịch hai tệp cùng tên vào một thư mục.

### 5.5. Đăng ký bằng `META-INF/services`

Trong **cả hai** thư mục resource:

```text
plugin-v1/resources/META-INF/services/demo.spi.Greeter
plugin-v2/resources/META-INF/services/demo.spi.Greeter
```

nội dung file **giống nhau**:

```text
demo.plugin.GreetingProvider
```

Điều này hợp lệ vì mỗi `URLClassLoader` chỉ có URL cho một provider JAR; mỗi loader tìm ra lớp có cùng tên nhưng định nghĩa khác nhau. File đăng ký phải nằm trong JAR tương ứng, không đặt trong `spi.jar`/`host.jar`.

Cả hai provider là class công khai với constructor không tham số công khai mặc định; chúng phù hợp với cơ chế khởi tạo provider trên classpath trong ví dụ.

## 6. Host: quan sát cache, đổi object, đổi class

Tệp `host/src/demo/host/Main.java` đầy đủ:

```java
package demo.host;

import demo.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceLoader;
import java.util.concurrent.atomic.AtomicReference;

public final class Main {
    private static Greeter exactlyOne(ServiceLoader<Greeter> services) {
        Iterator<Greeter> iterator = services.iterator();

        if (!iterator.hasNext()) {
            throw new IllegalStateException("No provider");
        }
        Greeter result = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalStateException("More than one provider");
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path dist = Path.of("dist").toAbsolutePath();
        ClassLoader parent = Greeter.class.getClassLoader();

        URL[] v1 = {
                dist.resolve("plugin-v1.jar").toUri().toURL()
        };
        URL[] v2 = {
                dist.resolve("plugin-v2.jar").toUri().toURL()
        };

        try (URLClassLoader loaderV1 = new URLClassLoader(v1, parent);
             URLClassLoader loaderV2 = new URLClassLoader(v2, parent)) {

            ServiceLoader<Greeter> servicesV1 =
                    ServiceLoader.load(Greeter.class, loaderV1);

            Greeter first = exactlyOne(servicesV1);
            Greeter cached = exactlyOne(servicesV1);
            System.out.println("cached same object: " + (first == cached));
            System.out.println("before reload: " + first.greet("Java"));

            servicesV1.reload();
            Greeter fresh = exactlyOne(servicesV1);
            System.out.println("after reload: " + fresh.greet("Java"));
            System.out.println("same object after reload: " + (first == fresh));
            System.out.println("same Class after reload: "
                    + (first.getClass() == fresh.getClass()));
            System.out.println("old object still works: "
                    + first.greet("Java"));

            AtomicReference<Greeter> active = new AtomicReference<>(first);
            active.set(fresh);
            System.out.println("active after object swap: "
                    + active.get().greet("Java"));

            Greeter v2Provider = exactlyOne(
                    ServiceLoader.load(Greeter.class, loaderV2));
            active.set(v2Provider);
            System.out.println("active after loader switch: "
                    + active.get().greet("Java"));
            System.out.println("old object still works after switch: "
                    + first.greet("Java"));

            System.out.println("same binary name: "
                    + first.getClass().getName().equals(
                            v2Provider.getClass().getName()));
            System.out.println("same runtime Class: "
                    + (first.getClass() == v2Provider.getClass()));

            boolean sharedContract =
                    loaderV1.loadClass("demo.spi.Greeter") == Greeter.class
                    && loaderV2.loadClass("demo.spi.Greeter") == Greeter.class;
            System.out.println("shared SPI Class: " + sharedContract);
        }
    }
}
```

Chương trình chỉ import `demo.spi.Greeter`. Nó **không import** `demo.plugin.GreetingProvider`, không gọi constructor provider bằng tay và không ghép các plugin JAR vào application classpath.

`exactlyOne(...)` yêu cầu mỗi loader cung cấp **đúng một provider**; đây là chính sách của demo. Trong hệ thống thật, nếu một vùng class loader có nhiều provider, cần bộ chọn theo ID/capability/cấu hình thay vì lấy phần tử đầu tiên. Trả về `Greeter` còn giúp host không phụ thuộc vào tên implementation.

`AtomicReference<Greeter>` mô phỏng registry active. Trong ví dụ nó chỉ được cập nhật tuần tự trong `main`; việc có `AtomicReference` **không tự tạo cơ chế lifecycle an toàn** cho một hệ thống server đa luồng.

## 7. Biên dịch và chạy với Java 17+

Cần có JDK 17 trở lên (`java`, `javac`, `jar`). Đứng ở thư mục gốc `spi-replacement-demo` chứa các thư mục `contract`, `plugin-v1`, `plugin-v2`, `host`.

### 7.1. Linux/macOS (Bash)

```bash
mkdir -p out/spi out/plugin-v1 out/plugin-v2 out/host dist

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/Greeter.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/spi.jar:dist/host.jar" demo.host.Main
```

### 7.2. Windows PowerShell

Trong Windows, các phần tử classpath phân cách bằng dấu `;`. Khi dùng PowerShell, nên đặt chuỗi classpath trong dấu nháy đơn:

```powershell
New-Item -ItemType Directory -Force out/spi,out/plugin-v1,out/plugin-v2,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/Greeter.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/GreetingProvider.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp 'dist/spi.jar;dist/host.jar' demo.host.Main
```

**Lưu ý quan trọng:** `java -cp` cuối chỉ chứa `spi.jar` và `host.jar`, không chứa hai plugin JAR. Host tự mở `plugin-v1.jar` và `plugin-v2.jar` qua hai `URLClassLoader` khác nhau. Nếu chạy từ thư mục khác, `Path.of("dist")` không còn trỏ đúng vị trí và cần chỉnh lại path hoặc working directory.

### 7.3. Stdout chính xác

```text
cached same object: true
before reload: v1#1:Java
after reload: v1#2:Java
same object after reload: false
same Class after reload: true
old object still works: v1#1:Java
active after object swap: v1#2:Java
active after loader switch: v2#1:Java
old object still works after switch: v1#1:Java
same binary name: true
same runtime Class: false
shared SPI Class: true
```

Giải nghĩa:

- `cached same object: true`: duyệt lại cùng `ServiceLoader` trước `reload()` trả instance đã cache.
- `before reload: v1#1:Java`: provider v1 đầu tiên đã được khởi tạo, `constructed == 1`.
- `after reload: v1#2:Java`: khi duyệt sau `reload()`, constructor v1 chạy lần nữa, tạo instance thứ hai.
- `same object after reload: false`: hai lần khởi tạo cho hai Java object khác nhau.
- `same Class after reload: true`: cả hai object vẫn cùng runtime class và cùng defining class loader.
- `old object still works`: cache bị xóa không đồng nghĩa JVM tự hủy object cũ.
- `active after object swap: v1#2:Java`: chỉ registry active đổi sang instance mới.
- `active after loader switch: v2#1:Java`: host tạo provider qua loader v2 rồi trỏ active sang nó; static counter của bản v2 bắt đầu riêng ở 1.
- `same binary name: true` nhưng `same runtime Class: false`: hai phiên bản có tên Java giống nhau, song JVM coi là hai class khác vì khác defining loader.
- `shared SPI Class: true`: cả hai child ủy quyền cùng `demo.spi.Greeter` về parent, nên cả hai có thể được host gọi thông qua SPI.

Ví dụ đã phân biệt được **thay cache**, **thay object** và **thay class** bằng quan sát độc lập, thay vì suy đoán từ một dòng log “reloaded”.

## 8. Bảng so sánh chi tiết: trạng thái nào còn sống?

Giả sử `loaderV1` đã định nghĩa `GreetingProvider` v1, và host đang giữ `first`.

| Phép thử | Sau `ServiceLoader.reload()` | Sau `active.set(fresh)` cùng loader | Sau tạo loader v2 và `active.set(v2)` |
|---|---|---|---|
| Cache của instance ServiceLoader v1 | Bị xóa; sẽ khám phá lại khi duyệt | Không đổi bởi `active.set` | Không đổi tự động |
| Đối tượng `first` | Còn nếu host giữ reference | Vẫn còn nếu host/request giữ | Vẫn có thể còn |
| Đối tượng provider active | Không tự đổi | Đổi thành `fresh` | Đổi thành v2 |
| `Class<?>` của provider mới | Thường cùng class nếu vẫn cùng loader | Cùng với `first` trong demo | Khác vì định nghĩa bởi loader v2 |
| Static state v1 | Vẫn tồn tại | Vẫn được `fresh` chia sẻ | Không biến mất nếu loader v1 còn sống |
| Static state v2 | Không liên quan | Không liên quan | Bắt đầu trong class v2 khi được khởi tạo |
| Bytecode của class v1 đã nạp | Không bị thay | Không bị thay | Không bị thay |
| Các request đã lấy provider v1 | Không tự đổi | Không tự đổi | Không tự đổi |
| Tài nguyên/JAR của loader cũ | Không tự đóng | Không tự đóng | Không tự đóng |

Nếu một provider tự lưu state ở static field, object mới của **cùng class** có thể mang cảm giác “mới hoàn toàn” nhưng vẫn ảnh hưởng hoặc bị ảnh hưởng bởi state chung. Muốn cô lập một class version, class loader là một phần thiết yếu của thiết kế; muốn dọn state cũ, còn phải giải quyết references và lifecycle.

## 9. Thay file JAR trên đĩa không phải thay class đã nạp

Một class sau khi được định nghĩa trong JVM không tự đổi bytecode chỉ vì file JAR nguồn bị thay:

```text
plugin.jar v1 trên đĩa
      |
      v
ClassLoader đã define GreetingProvider v1
      |
      v
Thay plugin.jar bằng file v2 ở cùng đường dẫn
      |
      x
Không tự sửa GreetingProvider đã định nghĩa
```

Cơ chế `ClassLoader.loadClass()` thường kiểm tra lớp đã được nạp trước khi tìm và định nghĩa lớp mới. Vì vậy, dù loader có đọc lại tài nguyên service, nếu class `demo.plugin.GreetingProvider` đã được loader đó định nghĩa, `ServiceLoader.reload()` không làm nó trở thành class v2.

Thay nội dung JAR ngay dưới một `URLClassLoader` đang hoạt động còn có rủi ro do JAR URL/resource caching, file locks và trạng thái triển khai; không nên coi đó là phương pháp nâng cấp đáng tin cậy.

**Chiến lược dễ kiểm soát:** dùng artifact phiên bản hóa, ví dụ `plugin-v1.jar`, `plugin-v2.jar`; tạo loader mới trỏ tới đúng artifact mới; kiểm chứng provider trước khi chuyển traffic. Nhờ vậy không yêu cầu “ghi đè” định nghĩa lớp trong loader cũ.

## 10. “Định nghĩa lớp mới” khác “redefine class tại chỗ”

Có **hai** loại thay đổi bytecode thường cùng được gọi là “thay lớp”:

### 10.1. Tạo `Class<?>` mới bằng loader mới

Đây là chiến lược của demo:

```text
old loader -> old Class<?> -> old provider
new loader -> new Class<?> -> new provider
```

Ưu điểm: có thể giữ hai phiên bản song song để kiểm thử, chuyển traffic dần và rollback bằng cách chuyển registry về provider cũ khi còn hợp lệ.

Giới hạn: các object cũ vẫn thuộc class cũ; không thể tự ép object phiên bản cũ thành class mới chỉ vì hai class cùng tên. Static state của hai loader tách biệt; thông tin muốn chuyển phải qua dữ liệu chung/SPI/DTO hoặc quy trình migration có chủ đích.

### 10.2. Redefinition/retransformation qua Java Instrumentation

Java có API `java.lang.instrument.Instrumentation`, ví dụ `redefineClasses(...)` và `retransformClasses(...)` khi agent/JVM hỗ trợ. Đây là cơ chế chuyên dụng **thay định nghĩa bytecode của một class đã nạp** trong phạm vi các hạn chế của JVM/agent.

Khác biệt cơ bản:

- Không cần tạo một `Class<?>` mới bằng class loader mới cho tên class đó.
- Những instance hiện có vẫn thuộc runtime class đã được tái định nghĩa; các lần gọi method tiếp theo có thể dùng phần mã đã được thay.
- Class initialization không tự chạy lại chỉ vì redefine; static fields không được xem như một bộ nhớ mới hoàn toàn.
- Các frame method đã đang thực thi có thể tiếp tục dùng bytecode cũ cho tới khi kết thúc, thay vì bị sửa giữa lệnh.
- Các JVM phổ biến giới hạn thay đổi **cấu trúc lớp** như thêm/xóa field hoặc method, thay đổi chữ ký/hệ thừa kế; cần kiểm tra khả năng `isRedefineClassesSupported()`/`isRetransformClassesSupported()` và những ràng buộc thực tế.

**`ServiceLoader.reload()` không gọi `Instrumentation` và không kích hoạt HotSwap.** Thay loader bằng artifact phiên bản hóa và redefine tại chỗ là **hai chiến lược khác nhau**, có phạm vi và rủi ro khác nhau. Bài này chỉ **giải thích** Instrumentation, không cung cấp agent HotSwap runnable vì đó là một cơ chế triển khai độc lập với bài toán làm mới cache SPI.

## 11. Quy trình thay plugin an toàn trong ứng dụng server

Một lần nâng cấp plugin có thể được thiết kế theo pha:

```text
[1] Chuẩn bị artifact mới, kiểm tra checksum/phiên bản/phụ thuộc
                       |
                       v
[2] Tạo class loader mới, giữ SPI/API chung ở parent
                       |
                       v
[3] Khám phá provider mới, kiểm tra contract/cấu hình
                       |
                       v
[4] Khởi tạo, warm-up, health-check, xác minh tương thích
                       |
                       v
[5] Chuyển registry active sang provider mới (atomic pointer)
                       |
                       v
[6] Đợi request cũ dùng provider cũ kết thúc
                       |
                       v
[7] Gỡ callback, dừng thread/worker, đóng resource
                       |
                       v
[8] Đóng loader cũ khi an toàn; bỏ reference để JVM có thể GC/unload
```

Lệnh `AtomicReference.set(newProvider)` chỉ xử lý một phần của bước [5]. Nó **không thay** các bước [6]–[8]. Khi thực hiện bước [4], không được để provider mới làm thay đổi dữ liệu production chưa được phép; kiểm tra warm-up cần được thiết kế an toàn.

Một `PluginHandle` trong ứng dụng thật thường chứa ít nhất provider, loader, version, trạng thái lifecycle và bộ đếm request đang sử dụng. Registry nên trỏ tới **handle**, không chỉ riêng object provider, để hệ thống biết loader nào cần giữ sống và khi nào được đóng.

Minh họa ý tưởng, **không phải một chương trình độc lập**:

```java
record PluginHandle(
        String version,
        Greeter provider,
        AutoCloseable loader) {}

AtomicReference<PluginHandle> current = ...;

PluginHandle candidate = prepareAndValidateNewPlugin();
PluginHandle old = current.getAndSet(candidate);

// Không đóng old.loader() ngay nếu request đang giữ old.
// Cần chờ drain/in-flight requests, hủy resource rồi mới close.
```

Các biến và hàm `prepareAndValidateNewPlugin()` là ký hiệu trong thiết kế, không có trong chương trình chạy của phần 6. Việc dùng `getAndSet` bảo đảm đổi handle atomically tại điểm đọc registry, nhưng request đã lấy handle cũ vẫn giữ nó. Nếu muốn mạnh hơn, cần giao thức lease/acquire/release để tránh race giữa request mới và việc drain.

### Rollback

Nếu chuyển sang provider v2 rồi phát hiện lỗi:

- Có thể chuyển registry **về provider v1** khi artifact, loader, instance và tài nguyên v1 vẫn còn ở trạng thái sử dụng được.
- Không thể giả định rollback chỉ bằng `ServiceLoader.reload()`; cache không phải lịch sử phiên bản.
- Nếu đã đóng hoặc giải phóng v1, có thể phải tạo loader/instance v1 mới; state của plugin cũ có thể cần phục hồi hoặc migration ngược.
- Việc rollback bytecode không tự rollback dữ liệu đã thay đổi bên ngoài như database/schema hoặc message đã gửi.

## 12. Những ràng buộc khi unload một plugin

Đóng `URLClassLoader` bằng `close()` **đóng các tài nguyên do loader quản lý** như các JAR/file mà nó đang giữ, nhưng **không buộc JVM lập tức unload class** và không hủy các object provider còn sống.

Class unloading phụ thuộc khả năng thu hồi class loader và những reference liên quan. Các nguồn giữ plugin ở lại thường gặp:

- Registry/caches vẫn giữ instance hoặc `Class<?>` cũ.
- Request đang chạy hoặc thread do plugin tạo vẫn giữ đối tượng thuộc loader cũ.
- `ThreadLocal`, timer, scheduler hoặc executor giữ callback/class từ plugin.
- Thread context class loader (`Thread.currentThread().getContextClassLoader()`) của thread sống còn trỏ tới loader cũ.
- Listener, MBean, shutdown hook, logging/app framework registry hoặc resource provider đã đăng ký nhưng chưa tháo.
- Một `ServiceLoader` được host giữ có thể còn giữ provider instance trong cache cho tới khi reload/bỏ reference.
- Object của plugin bị chuyển ra ngoài qua một API chung và tiếp tục sống ở host.

Vì vậy cần chính sách `start`, `stop`, đóng resource, xóa callback/registration, dọn cache và kiểm tra classloader leak. Có thể dùng tham chiếu yếu trong kiểm thử để quan sát khả năng thu hồi, nhưng **không** dựa vào thời điểm GC như một deadline chắc chắn.

Class loader chỉ cô lập **namespace của class**; nó không tự sandbox mã không đáng tin cậy, không tách process, quyền truy cập mạng hoặc filesystem. Khi plugin không đáng tin, cần biện pháp cách ly mạnh hơn.

## 13. Lưu ý khi SPI chạy trong module path/JPMS

Demo ở trên dùng **classpath + tài nguyên `META-INF/services` + URLClassLoader**. Với named modules trong Java Platform Module System, provider thường được khai báo bằng `provides ... with ...` trong `module-info.java`, còn consumer dùng `uses`. Khi xây dựng một `ModuleLayer` mới cho plugin, có thể dùng API `ServiceLoader.load(layer, ServiceType.class)` phù hợp kiến trúc module.

Các điểm chung vẫn giữ nguyên:

- `ServiceLoader` khám phá và cache provider, **không tự cập nhật bytecode**.
- Host phải có ranh giới API/SPI chung mà plugin thật sự dùng được; không nhân đôi service type qua vùng class loading.
- Chuyển provider active là một quyết định routing/lifecycle riêng.
- Tạo `ModuleLayer`/class loader mới cho artifact mới khác với redefine class tại chỗ.
- Provider cũ không tự dừng khi có một module layer mới được tạo.

Không nên copy nguyên cú pháp classpath của demo sang module path rồi giả định chỉ cần tài nguyên `META-INF/services`; cách đăng ký và discovery của named modules phải tuân theo JPMS.

## 14. Sai lầm hay gặp và cách chẩn đoán

| Hiện tượng/niềm tin sai | Thực tế | Hướng khắc phục |
|---|---|---|
| “`reload()` là thay plugin JAR” | Nó chỉ xóa cache của một `ServiceLoader` | Dùng loader/layer mới nếu cần định nghĩa class mới |
| “Object sau reload mới thì code cũng mới” | Instance mới có thể vẫn thuộc `Class<?>` cũ | So sánh `getClass()` và defining class loader |
| “Gọi `reload()` sẽ hủy provider cũ” | Reference cũ vẫn có thể hoạt động | Quản lý stop/close và quyền sở hữu object |
| “Đổi `AtomicReference` sẽ cập nhật mọi request” | Request đã đọc reference cũ vẫn có thể tiếp tục dùng cũ | Draining/lease, kế hoạch chuyển giao |
| “Đè file JAR là JVM lập tức dùng v2” | Lớp đã định nghĩa không tự bị đổi | Artifact phiên bản hóa và loader mới, hoặc Instrumentation theo điều kiện hỗ trợ |
| “Cùng class name thì là cùng class” | Class identity phụ thuộc defining loader | In `getClassLoader()` và so sánh `Class<?>` |
| “Mỗi plugin đóng SPI của riêng nó cũng được” | Gây hai service type khác nhau, có thể không ép kiểu | Dùng SPI do parent/layer chung sở hữu |
| “`URLClassLoader.close()` nghĩa là unload class” | Nó đóng resource, không bắt GC unload ngay | Dọn reference, thread, callbacks và lifecycle |
| “Static counter sẽ reset sau `reload()`” | Same class giữ static state | Kiểm tra loader và static fields |
| “Có `ServiceLoader` là tự hỗ trợ concurrent reload” | `ServiceLoader` không bảo đảm thread-safe | Đừng reload trong lúc thread khác duyệt |
| “Ứng dụng chỉ có một provider vì lấy `.next()`” | Có thể có nhiều provider hoặc duplicate config | Kiểm tra 0/1/n ứng viên, chọn theo chính sách |
| “Loader mới bảo đảm không rò memory” | Host/thread vẫn có thể giữ loader cũ | Quan sát vòng đời instance và tham chiếu |

### Các phép kiểm tra hữu ích

Khi một lần nâng cấp không thay hành vi như mong muốn, hãy log có kiểm soát:

```java
Class<?> type = provider.getClass();
System.out.println("provider id = " + provider.id());
System.out.println("binary name = " + type.getName());
System.out.println("defining loader = " + type.getClassLoader());
```

Đây là trích đoạn cần đặt trong phương thức có biến `provider` kiểu `Greeter`. Chỉ log tên class/loader không đủ để chứng minh source artifact; trong hệ thống lớn cần thông tin thêm về artifact version, checksum và cơ chế định tuyến.

Nếu phải so sánh thật sự, dùng:

```java
boolean sameObject = oldProvider == newProvider;
boolean sameClass = oldProvider.getClass() == newProvider.getClass();
boolean sameLoader =
        oldProvider.getClass().getClassLoader()
                == newProvider.getClass().getClassLoader();
```

Ba giá trị trả lời ba câu hỏi khác nhau. Nhớ rằng hai object khác nhau có thể cùng class; hai class có cùng tên có thể khác loader; và chỉ đổi reference không đồng nghĩa đã thay bytecode.

## 15. Bài tập áp dụng

1. **Bỏ `reload()`:** dùng `ServiceLoader` v1 duyệt hai lần và so sánh object. Dự đoán vì sao cả hai lần đều nhận `v1#1`.
2. **Chỉ `reload()` cache:** gọi lại `servicesV1.reload()`, in static instance ordinal và so sánh `Class<?>`. Giải thích vì sao instance tăng nhưng class vẫn y nguyên.
3. **Không chuyển active:** tạo `v2Provider` qua `loaderV2` nhưng không gọi `active.set(v2Provider)`. Vì sao host vẫn dùng provider v1?
4. **Chuyển active sớm:** mô phỏng request A lấy `Greeter old = active.get()` trước khi đổi registry; request B lấy sau khi đổi. Cho cả hai gọi `greet("Java")` và chỉ ra vì sao A vẫn dùng bản cũ.
5. **Phá ranh giới SPI:** cố tình đóng thêm `Greeter.class` vào mỗi JAR và sử dụng chiến lược child-first cho cả package `demo.spi`. Phân tích vì sao host có thể gặp lỗi “provider not a subtype” hoặc ép kiểu; sau đó khôi phục shared SPI từ parent.
6. **Thay JAR sai cách:** thử nạp v1 rồi thay file JAR tại cùng URL (trên môi trường thử nghiệm có thể dọn lại). Giải thích vì sao không được dựa vào `reload()` để thay định nghĩa class và vì sao việc ghi đè JAR đang mở còn rủi ro.
7. **Thiết kế rollout:** mô tả `prepare -> validate -> swap -> drain -> close` và cách rollback nếu v2 lỗi sau khi đã xử lý một số request. Vì sao atomic pointer chỉ giải quyết một phần bài toán?
8. **HotSwap vs loader mới:** nêu trường hợp phù hợp với Instrumentation và trường hợp phù hợp với versioned artifact cùng class loader mới; chỉ ra tác động của static state và object identity ở hai chiến lược.

## 16. Checklist trước khi bật thay plugin ở môi trường thật

- **Versioning:** artifact/JAR có định danh, checksum, dependency và giao thức tương thích rõ ràng?
- **Shared contract:** toàn bộ plugin dùng đúng một SPI/API type từ parent, chữ ký không chứa class private của loader con?
- **Discovery:** provider được đăng ký đúng, class loader/layer nào phụ trách tìm, có kiểm tra số lượng và lựa chọn provider?
- **Cache:** phân biệt rõ `ServiceLoader` nào được reload; iterator cũ được bỏ, không thao tác đồng thời trái quy định?
- **Object:** biết object nào đang active, đã warm-up và kiểm thử provider mới trước khi chuyển chưa?
- **Class:** đã có định nghĩa class mới từ loader/layer mới khi yêu cầu đổi bytecode, hay vẫn chỉ tạo object mới từ class cũ?
- **Traffic:** có phương pháp xử lý request in-flight, đồng bộ trạng thái và migration khi cần?
- **Resources:** có stop callback, xóa listener, đóng file/socket/executor và giải phóng loader cũ?
- **Security:** plugin có đáng tin cậy, có giới hạn tài nguyên và quyền phù hợp không?
- **Observability:** log được provider ID, version, class name, loader identity, thời điểm swap và lỗi rollback mà không lộ thông tin nhạy cảm?

**Kết luận:** `ServiceLoader.reload()` chỉ **làm mới cache khám phá SPI**; đổi một reference trong registry chỉ **chọn một object khác**; muốn nạp một bản bytecode khác thường phải dùng **class loader/module layer mới** hoặc cơ chế **Instrumentation** chuyên dụng. Bất kể cách nào, host vẫn phải quản lý vòng đời của provider cũ và request đang chạy. Đó là ranh giới quyết định giữa “làm mới bộ nhớ đệm”, “đổi instance” và “triển khai plugin mới” thực sự.