# Cô lập hai phiên bản thư viện mà không nhân đôi kiểu hợp đồng

Một ứng dụng Java có thể phải chạy đồng thời hai plugin, mỗi plugin được biên dịch với **một phiên bản khác nhau của cùng thư viện**. Nếu đưa cả hai phiên bản lên một classpath chung, các lớp trùng tên đầy đủ có thể xung đột: JVM chỉ dùng một định nghĩa lớp cho mỗi tên trong phạm vi một class loader. Một plugin có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc nhận hành vi không đúng phiên bản.

Giải pháp ở ranh giới plugin là **cô lập implementation và thư viện phụ thuộc bằng các class loader khác nhau**, đồng thời giữ **một bản duy nhất của kiểu hợp đồng SPI/API trong class loader cha**. Hai plugin có thể nạp hai lớp cùng tên nhị phân nhưng vẫn được ứng dụng gọi qua cùng một interface.

Bài này minh họa kiến trúc đó bằng Java 17, hai phiên bản `demo.lib.TextEngine` có API **khác nhau**, hai provider mang cùng tên đầy đủ `demo.plugin.TransformPlugin`, và một `demo.spi.TextPlugin` dùng chung. Ví dụ có lệnh biên dịch, đóng JAR, chạy và kết quả chính xác.

## 1. Vấn đề: trùng tên lớp trên một classpath

Giả sử thư viện `text-lib` có hai phiên bản:

| Đặc điểm | `text-lib-v1.jar` | `text-lib-v2.jar` |
|---|---|---|
| Tên class | `demo.lib.TextEngine` | `demo.lib.TextEngine` |
| API công khai | `transform(String)` | `render(String)` |
| Hành vi | Thêm `[v1]`, chuyển chữ thường | Thêm `[v2]`, chuyển chữ hoa |
| Plugin phụ thuộc | Plugin cũ `legacy` | Plugin mới `modern` |

Cả hai phiên bản có **cùng tên nhị phân** `demo.lib.TextEngine` nhưng không có cùng tập phương thức. Khi một class loader thông thường nạp tên `demo.lib.TextEngine` từ một classpath chứa cả hai JAR, class loader đó không tạo hai phiên bản `Class` độc lập chỉ vì có hai JAR. Phiên bản được tìm thấy theo cơ chế tra cứu classpath sẽ được dùng cho định danh lớp đó trong loader.

Ví dụ plugin mới đã được biên dịch gọi `TextEngine.render(String)`. Nếu lúc chạy tên `TextEngine` lại được liên kết tới bản v1 không có `render(String)`, lời gọi có thể thất bại với `NoSuchMethodError`. Đổi thứ tự hai JAR để sửa plugin mới có thể làm hỏng plugin cũ. Việc ép toàn bộ plugin lên một phiên bản cũng không luôn khả thi vì các API khác nhau.

**Mục tiêu của bài** không phải tải hai lớp cùng tên vào *một* loader; ta tạo **hai không gian nạp lớp** độc lập cho phần triển khai và vẫn dùng **một không gian chung** cho hợp đồng giao tiếp.

## 2. Danh tính lớp trong JVM: tên chưa đủ

Trong JVM, danh tính kiểu lớp về mặt nạp lớp phụ thuộc vào **tên nhị phân và class loader định nghĩa lớp đó**. Hai class có cùng tên đầy đủ nhưng do hai loader khác nhau định nghĩa là **hai kiểu khác nhau**.

```text
Class identity ≈ (binary class name, defining class loader)

("demo.lib.TextEngine", loader-v1) !=
("demo.lib.TextEngine", loader-v2)
```

Ký hiệu trên chỉ mô tả quy tắc danh tính kiểu, không phải cú pháp Java. Trong mã thực tế, có thể kiểm tra bằng phép so sánh hai đối tượng `Class<?>`:

```java
// Minh họa biểu thức, được dùng đầy đủ trong Main.java ở dưới.
boolean sameType =
        loaderV1.loadClass("demo.lib.TextEngine")
        == loaderV2.loadClass("demo.lib.TextEngine");
```

Kết quả cần đạt là `false`. Hai loader có thể nạp hai bản `TextEngine` độc lập, kể cả khi tên class giống hệt nhau.

Tuy nhiên, chính quy tắc này gây vấn đề khác nếu ta cũng nhân đôi hợp đồng `demo.spi.TextPlugin`:

```text
demo.spi.TextPlugin do parent định nghĩa
            KHÁC
demo.spi.TextPlugin do child định nghĩa
```

Nếu provider `implements` bản interface do child định nghĩa còn host kỳ vọng bản interface do parent định nghĩa, tên interface nhìn giống nhau nhưng **không cùng kiểu**. Có thể gặp lỗi provider “not a subtype”, `ClassCastException` hoặc các lỗi liên kết kiểu liên quan.

Vì thế phải áp dụng đồng thời **hai ràng buộc**:

1. **Private to child:** lớp implementation và thư viện riêng của mỗi plugin được định nghĩa trong loader của plugin đó.
2. **Shared from parent:** interface SPI, các DTO và kiểu chung dùng trong chữ ký giao tiếp được lấy từ class loader cha. Các JAR plugin không tự đóng thêm bản sao của hợp đồng.

Một class loader chỉ là cơ chế tải lớp; nó không tự sửa lỗi thiết kế khi chữ ký SPI đưa những kiểu chỉ tồn tại trong class loader con ra phía host.

## 3. Kiến trúc parent–child đúng ranh giới

Ta tổ chức như sau:

```text
ỨNG DỤNG / PARENT CLASS LOADER
  classpath:
    spi.jar
    host.jar

  demo.spi.TextPlugin          <-- MỘT hợp đồng duy nhất
  demo.host.Main
  demo.host.PluginClassLoader
                  |
         +--------+--------+
         |                 |
         v                 v
   PLUGIN LOADER V1   PLUGIN LOADER V2
      URL riêng          URL riêng
   plugin-v1.jar      plugin-v2.jar
   lib-v1.jar         lib-v2.jar

   demo.plugin.       demo.plugin.
     TransformPlugin    TransformPlugin
   demo.lib.          demo.lib.
     TextEngine         TextEngine
   (API v1)           (API v2)
         |                 |
         +--------+--------+
                  |
        Cả hai implements/gọi
          demo.spi.TextPlugin
           được parent nạp
```

Đường đi của một lần gọi:

1. Host sử dụng **một** `TextPlugin.class` từ parent để yêu cầu các dịch vụ.
2. Host tạo hai class loader khác nhau, mỗi loader chỉ biết JAR của một plugin và bản thư viện tương ứng.
3. Mỗi loader tìm provider thông qua `ServiceLoader.load(TextPlugin.class, loader)`.
4. Khi nạp tên `demo.plugin.TransformPlugin` hoặc `demo.lib.TextEngine`, loader con lấy class từ bộ JAR riêng của nó.
5. Khi provider cần `demo.spi.TextPlugin`, nó ủy quyền về parent và nhận **chính interface host đang dùng**.
6. Host chỉ giữ/thao tác các đối tượng qua `TextPlugin`, nên có thể gọi cả hai provider mà không cần import `TextEngine` của bất kỳ phiên bản nào.

**Ranh giới phụ thuộc:** `spi.jar` và `host.jar` nằm trên **application classpath**; các JAR `plugin-v1.jar`, `lib-v1.jar`, `plugin-v2.jar`, `lib-v2.jar` **không nằm trên application classpath**. Host mở chúng qua `URLClassLoader` riêng ở runtime.

Nếu parent không có lớp `demo.lib.*` hoặc `demo.plugin.*`, hai `URLClassLoader` sử dụng ủy quyền parent-first mặc định cũng có thể nạp các lớp chỉ tồn tại trong từng child. Ví dụ bên dưới thêm quy tắc **child-first có giới hạn** cho đúng hai package riêng để việc nạp vẫn theo ý định nếu môi trường parent vô tình chứa tên lớp trùng. Hợp đồng SPI luôn theo đường parent-first.

## 4. Cấu trúc mã nguồn và JAR đầu ra

Tạo các thư mục/tệp:

```text
isolation-demo/
├── contract/
│   └── src/demo/spi/TextPlugin.java
├── lib-v1/
│   └── src/demo/lib/TextEngine.java
├── lib-v2/
│   └── src/demo/lib/TextEngine.java
├── plugin-v1/
│   ├── src/demo/plugin/TransformPlugin.java
│   └── resources/META-INF/services/demo.spi.TextPlugin
├── plugin-v2/
│   ├── src/demo/plugin/TransformPlugin.java
│   └── resources/META-INF/services/demo.spi.TextPlugin
└── host/
    └── src/demo/host/
        ├── PluginClassLoader.java
        └── Main.java
```

Sau khi biên dịch:

```text
dist/
├── spi.jar
├── host.jar
├── lib-v1.jar
├── lib-v2.jar
├── plugin-v1.jar
└── plugin-v2.jar
```

Đây là **sáu JAR**, nhưng chỉ `spi.jar` và `host.jar` được truyền cho `java -cp` khi chạy `Main`. Bốn JAR còn lại do mã host mở bằng hai loader riêng.

## 5. Định nghĩa đúng một hợp đồng SPI

Tệp `contract/src/demo/spi/TextPlugin.java`:

```java
package demo.spi;

public interface TextPlugin {
    String id();

    String transform(String text);
}
```

Hợp đồng này chỉ dùng kiểu JDK `String` và không nhắc đến `demo.lib.TextEngine`, tên lớp provider hay phiên bản thư viện. `id()` trả về định danh plugin ổn định; `transform()` là hành vi mà host được phép gọi. Những dữ liệu phức tạp hơn nên đi qua các kiểu API/DTO do parent sở hữu, hoặc kiểu chuẩn của JDK.

**Không đặt `TextPlugin.class` vào các JAR plugin**. Khi biên dịch một plugin, `spi.jar` có mặt trên **compile classpath** để trình biên dịch kiểm tra `implements`. Khi đóng JAR plugin, chỉ đóng class của plugin và metadata của plugin; không copy class SPI vào đó.

Trong ví dụ, v1 và v2 có thể thay đổi mọi chi tiết nội bộ mà không cần thay chữ ký `TextPlugin`.

## 6. Hai phiên bản thư viện có API khác nhau

### 6.1. Bản v1

Tệp `lib-v1/src/demo/lib/TextEngine.java`:

```java
package demo.lib;

import java.util.Locale;

public final class TextEngine {
    private TextEngine() {}

    public static String transform(String input) {
        return "[v1] " + input.toLowerCase(Locale.ROOT);
    }
}
```

### 6.2. Bản v2

Tệp `lib-v2/src/demo/lib/TextEngine.java`:

```java
package demo.lib;

import java.util.Locale;

public final class TextEngine {
    private TextEngine() {}

    public static String render(String input) {
        return "[v2] " + input.toUpperCase(Locale.ROOT);
    }
}
```

Hai tệp cùng khai báo `package demo.lib` và `public final class TextEngine`, nhưng **v1 có `transform(String)` còn v2 có `render(String)`**. Đây là khác biệt API có chủ đích để minh họa xung đột phiên bản. Chúng **không được biên dịch chung vào cùng thư mục output**: làm vậy sẽ có hai định nghĩa của một class cùng tên.

`Locale.ROOT` giúp việc chuyển chữ thường/chữ hoa trong ví dụ không phụ thuộc locale mặc định của máy.

## 7. Hai provider cùng tên class, biên dịch với dependency riêng

### 7.1. Provider v1

Tệp `plugin-v1/src/demo/plugin/TransformPlugin.java`:

```java
package demo.plugin;

import demo.spi.TextPlugin;
import demo.lib.TextEngine;

public final class TransformPlugin implements TextPlugin {
    @Override
    public String id() {
        return "legacy";
    }

    @Override
    public String transform(String input) {
        return TextEngine.transform(input);
    }
}
```

Provider cũ gọi đúng API của `TextEngine` v1.

### 7.2. Provider v2

Tệp `plugin-v2/src/demo/plugin/TransformPlugin.java`:

```java
package demo.plugin;

import demo.spi.TextPlugin;
import demo.lib.TextEngine;

public final class TransformPlugin implements TextPlugin {
    @Override
    public String id() {
        return "modern";
    }

    @Override
    public String transform(String input) {
        return TextEngine.render(input);
    }
}
```

Provider mới gọi đúng API của `TextEngine` v2. Chú ý hai provider cũng cùng tên `demo.plugin.TransformPlugin`, nhưng mã bytecode khác nhau và được đóng vào hai JAR khác nhau.

Cả hai provider đều là class `public` và có constructor không tham số công khai do Java cấp khi không tự khai báo constructor. Điều này phù hợp với kiểu provider classpath mà `ServiceLoader` sẽ khởi tạo.

Khi biên dịch, mỗi provider phải nhìn thấy:

```text
plugin-v1:  spi.jar + lib-v1.jar
plugin-v2:  spi.jar + lib-v2.jar
```

**Không** dùng cùng lúc cả `lib-v1.jar` và `lib-v2.jar` trên compile classpath của một provider. Mỗi provider phải liên kết đúng API phiên bản nó được thiết kế để sử dụng.

## 8. Đăng ký SPI cho từng provider JAR

Trên classpath, `ServiceLoader` nhận diện provider thông qua tài nguyên:

```text
META-INF/services/demo.spi.TextPlugin
```

Nội dung tệp `plugin-v1/resources/META-INF/services/demo.spi.TextPlugin`:

```text
demo.plugin.TransformPlugin
```

Nội dung tệp `plugin-v2/resources/META-INF/services/demo.spi.TextPlugin`:

```text
demo.plugin.TransformPlugin
```

Hai tệp có **cùng tên và cùng nội dung** vì hai JAR đều cung cấp class có cùng tên nhị phân. Tuy nhiên, mỗi tệp được đóng bên trong **JAR của chính provider đó**. `ServiceLoader.load(TextPlugin.class, loaderV1)` khám phá provider từ các tài nguyên mà `loaderV1` nhìn thấy, còn `loaderV2` làm tương tự trong phạm vi của nó.

Đây là chi tiết cần phân biệt với cấu hình thông thường: cùng một dòng `demo.plugin.TransformPlugin` **không tạo ra cùng một `Class`** nếu tên lớp đó được định nghĩa bởi hai class loader khác nhau.

Không đặt tài nguyên đăng ký của các provider này vào `spi.jar` hoặc `host.jar`. Parent phải sở hữu hợp đồng, nhưng không nên vô tình công bố provider riêng của child trong chính classpath của host.

## 9. Class loader cô lập implementation nhưng ủy quyền SPI về parent

Tệp `host/src/demo/host/PluginClassLoader.java`:

```java
package demo.host;

import java.net.URL;
import java.net.URLClassLoader;

public final class PluginClassLoader extends URLClassLoader {
    public PluginClassLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        synchronized (getClassLoadingLock(name)) {
            Class<?> loaded = findLoadedClass(name);

            if (loaded == null) {
                if (name.startsWith("demo.plugin.")
                        || name.startsWith("demo.lib.")) {
                    loaded = findClass(name);
                } else {
                    loaded = super.loadClass(name, false);
                }
            }

            if (resolve) {
                resolveClass(loaded);
            }
            return loaded;
        }
    }
}
```

Đây là phiên bản tối giản của một bộ nạp lớp dành cho cấu trúc package **đã biết trước**, không phải trình quản lý plugin đa năng.

Các điểm cần đọc kỹ:

- `demo.plugin.*` và `demo.lib.*` là **package riêng của mỗi plugin**. `findClass(name)` buộc chúng được tìm trong URL của loader tương ứng, không lấy nhầm từ parent.
- `demo.spi.*`, `demo.host.*`, `java.*` và các package không nằm trong danh sách private đi theo `super.loadClass(...)`, tức là sử dụng quy tắc ủy quyền mặc định. Nhờ vậy `demo.spi.TextPlugin` được parent nạp.
- Không có `catch ClassNotFoundException` để tự rơi về parent khi class *thuộc package private* bị thiếu. Đây là chính sách **fail closed**: một plugin thiếu dependency riêng phải báo lỗi thay vì lặng lẽ dùng phiên bản khác từ host.
- `findLoadedClass(name)` tránh định nghĩa trùng class trong cùng loader. Đồng bộ bằng `getClassLoadingLock(name)` bảo vệ đường nạp lớp và `resolveClass` xử lý bước liên kết khi được yêu cầu.
- Tách loader riêng cho **mỗi nhóm plugin và dependency cần cô lập**. Nếu dùng chung một loader chứa hai phiên bản `TextEngine` trùng tên, xung đột lại xuất hiện trong chính loader chung đó.

**Không áp dụng child-first cho mọi package.** Nếu child-first cả `demo.spi.*`, các bản SPI trong từng child có thể được định nghĩa khác parent, phá vỡ khả năng ép kiểu provider thành `TextPlugin`. Nhiều framework còn sở hữu API có quy tắc class loading riêng; danh sách private cần được giới hạn và kiểm thử.

Với ứng dụng thực, nên có chính sách rõ ràng cho resource loading, package sealing, native library, signed JAR, dependency bắc cầu và logging. `URLClassLoader` không tự bảo đảm mọi dạng phụ thuộc đều có thể cô lập.

## 10. Host khám phá mỗi provider và kiểm tra danh tính kiểu

Tệp `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.TextPlugin;

import java.net.URL;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    private static TextPlugin loadOnly(ClassLoader loader) {
        List<TextPlugin> providers = new ArrayList<>();

        for (TextPlugin provider
                : ServiceLoader.load(TextPlugin.class, loader)) {
            providers.add(provider);
        }

        if (providers.size() != 1) {
            throw new IllegalStateException(
                    "Expected 1 provider, found " + providers.size());
        }

        return providers.get(0);
    }

    public static void main(String[] args) throws Exception {
        Path dist = Path.of("dist").toAbsolutePath();
        ClassLoader parent = TextPlugin.class.getClassLoader();

        URL[] oldJars = {
                dist.resolve("plugin-v1.jar").toUri().toURL(),
                dist.resolve("lib-v1.jar").toUri().toURL()
        };
        URL[] newJars = {
                dist.resolve("plugin-v2.jar").toUri().toURL(),
                dist.resolve("lib-v2.jar").toUri().toURL()
        };

        try (PluginClassLoader oldLoader =
                     new PluginClassLoader(oldJars, parent);
             PluginClassLoader newLoader =
                     new PluginClassLoader(newJars, parent)) {

            TextPlugin oldPlugin = loadOnly(oldLoader);
            TextPlugin newPlugin = loadOnly(newLoader);

            System.out.println(
                    oldPlugin.id() + " => "
                            + oldPlugin.transform("Hello Java"));
            System.out.println(
                    newPlugin.id() + " => "
                            + newPlugin.transform("Hello Java"));

            System.out.println("same provider name: "
                    + oldPlugin.getClass().getName().equals(
                            newPlugin.getClass().getName()));
            System.out.println("same provider Class: "
                    + (oldPlugin.getClass() == newPlugin.getClass()));
            System.out.println("same library Class: "
                    + (oldLoader.loadClass("demo.lib.TextEngine")
                    == newLoader.loadClass("demo.lib.TextEngine")));
            System.out.println("shared SPI Class: "
                    + (oldLoader.loadClass("demo.spi.TextPlugin")
                    == TextPlugin.class
                    && newLoader.loadClass("demo.spi.TextPlugin")
                    == TextPlugin.class));
        }
    }
}
```

`Main` không có câu lệnh `import demo.plugin.TransformPlugin` hay `import demo.lib.TextEngine`. Host chỉ dùng `TextPlugin`, một kiểu được nạp bởi parent. Mỗi `ServiceLoader` được tạo **với class loader cụ thể**; nếu gọi overload không truyền loader, kết quả còn phụ thuộc context class loader của luồng và không bảo đảm mô hình cô lập đang mong muốn.

Phương thức `loadOnly()` kiểm tra có **đúng một provider trong từng phạm vi**. Đây là chính sách của ví dụ. Trong hệ thống nhiều provider, bạn có thể xây registry và chọn theo ID/capability/cấu hình, nhưng phải giữ việc khám phá tách biệt theo loader để tránh xung đột.

`try-with-resources` gọi `close()` cho hai `URLClassLoader` khi kết thúc. Điều này đóng tài nguyên mở của loader, **không đồng nghĩa tất cả class lập tức được unload**; JVM chỉ có thể thu hồi class khi loader và những đối tượng/luồng/tài nguyên giữ tham chiếu liên quan không còn sống.

## 11. Biên dịch sáu JAR với Java 17+

Ví dụ được kiểm tra với mã tương thích Java 17 (`javac --release 17`). Đứng tại thư mục `isolation-demo` đã tạo đúng cây tệp trên. Các lệnh biên dịch sau **cố tình tách từng output directory** để hai class trùng tên không ghi đè nhau.

### 11.1. Linux/macOS (Bash)

```bash
mkdir -p out/spi out/lib-v1 out/lib-v2 out/plugin-v1 out/plugin-v2 out/host dist

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/TextPlugin.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -d out/lib-v1 lib-v1/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v1.jar -C out/lib-v1 .

javac --release 17 -encoding UTF-8 -d out/lib-v2 lib-v2/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v2.jar -C out/lib-v2 .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar:dist/lib-v1.jar -d out/plugin-v1 plugin-v1/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar:dist/lib-v2.jar -d out/plugin-v2 plugin-v2/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/PluginClassLoader.java host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp dist/spi.jar:dist/host.jar demo.host.Main
```

### 11.2. Windows PowerShell

PowerShell và Windows Java classpath sử dụng dấu `;` để ngăn các JAR. Dùng dấu nháy quanh chuỗi classpath khi chứa `;`:

```powershell
New-Item -ItemType Directory -Force out/spi,out/lib-v1,out/lib-v2,out/plugin-v1,out/plugin-v2,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/spi contract/src/demo/spi/TextPlugin.java
jar --create --file dist/spi.jar -C out/spi .

javac --release 17 -encoding UTF-8 -d out/lib-v1 lib-v1/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v1.jar -C out/lib-v1 .

javac --release 17 -encoding UTF-8 -d out/lib-v2 lib-v2/src/demo/lib/TextEngine.java
jar --create --file dist/lib-v2.jar -C out/lib-v2 .

javac --release 17 -encoding UTF-8 -cp 'dist/spi.jar;dist/lib-v1.jar' -d out/plugin-v1 plugin-v1/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v1.jar -C out/plugin-v1 . -C plugin-v1/resources .

javac --release 17 -encoding UTF-8 -cp 'dist/spi.jar;dist/lib-v2.jar' -d out/plugin-v2 plugin-v2/src/demo/plugin/TransformPlugin.java
jar --create --file dist/plugin-v2.jar -C out/plugin-v2 . -C plugin-v2/resources .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host host/src/demo/host/PluginClassLoader.java host/src/demo/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp 'dist/spi.jar;dist/host.jar' demo.host.Main
```

**Kiểm tra classpath:** ở **lệnh `java` cuối**, chỉ có `spi.jar` và `host.jar`. Các JAR `lib-v1`, `lib-v2`, `plugin-v1`, `plugin-v2` được mở bởi mã Java từ `Path.of("dist")`; nếu bạn đang chạy tại thư mục khác, cần sửa đường dẫn thư mục `dist` trong chương trình hoặc chạy từ đúng thư mục gốc của demo.

### 11.3. Kết quả chuẩn

Stdout khi chạy thành công:

```text
legacy => [v1] hello java
modern => [v2] HELLO JAVA
same provider name: true
same provider Class: false
same library Class: false
shared SPI Class: true
```

Giải thích từng dòng:

- `legacy` gọi đúng `TextEngine.transform` của v1, tạo `[v1] hello java`.
- `modern` gọi đúng `TextEngine.render` của v2, tạo `[v2] HELLO JAVA`.
- Tên nhị phân của hai provider **giống nhau**, nhưng hai đối tượng `Class` khác nhau vì chúng được định nghĩa trong hai loader riêng.
- Hai bản `demo.lib.TextEngine` cũng là hai đối tượng `Class` khác nhau, nên API v1/v2 không va chạm.
- Mỗi child khi yêu cầu `demo.spi.TextPlugin` đều nhận chính `TextPlugin.class` từ parent. Đây là điều kiện để host tương tác với cả hai qua cùng một interface.

## 12. Xác minh JAR thật sự đóng gói đúng ranh giới

Dùng lệnh `jar --list` (giống nhau trên các hệ điều hành):

```bash
jar --list --file dist/spi.jar
jar --list --file dist/plugin-v1.jar
jar --list --file dist/plugin-v2.jar
jar --list --file dist/lib-v1.jar
jar --list --file dist/lib-v2.jar
```

Các điều kiện cần kiểm tra:

| Artifact | Phải có | Không nên có |
|---|---|---|
| `spi.jar` | `demo/spi/TextPlugin.class` | `demo/lib/TextEngine.class`, lớp provider, file đăng ký provider |
| `plugin-v1.jar` | `demo/plugin/TransformPlugin.class`, `META-INF/services/demo.spi.TextPlugin` | `demo/spi/TextPlugin.class`, `TextEngine.class` của bản khác |
| `plugin-v2.jar` | `demo/plugin/TransformPlugin.class`, file đăng ký tương ứng | Bản sao SPI, lớp thư viện v1 |
| `lib-v1.jar` | `demo/lib/TextEngine.class` bản v1 | Class contract, class plugin |
| `lib-v2.jar` | `demo/lib/TextEngine.class` bản v2 | Class contract, class plugin |
| `host.jar` | `demo/host/Main.class`, `demo/host/PluginClassLoader.class` | Class provider hoặc thư viện private |

Có thể thấy hai JAR plugin chứa class **cùng đường dẫn** `demo/plugin/TransformPlugin.class`; đó là chủ ý và chỉ an toàn vì mỗi plugin được mở từ **loader riêng**.

Nếu dùng Maven hoặc Gradle, điều tương đương là: `spi.jar` là dependency biên dịch chung, **không được shade/relocate bản sao SPI vào từng plugin**; phụ thuộc riêng được đóng trong vùng class loading riêng và không rò lên classpath của host. Các dependency chuyển tiếp cũng phải được rà soát, vì xung đột không chỉ xảy ra với thư viện trực tiếp.

## 13. Vì sao các cách tưởng như đơn giản có thể sai?

### 13.1. Đưa hai JAR trùng class vào classpath của host

Lệnh dưới đây minh họa **cấu hình sai**; không cần chạy để hiểu hậu quả:

```bash
# Minh họa cấu hình SAI khi muốn cô lập hai phiên bản
java -cp "dist/spi.jar:dist/host.jar:dist/lib-v1.jar:dist/lib-v2.jar:dist/plugin-v1.jar:dist/plugin-v2.jar" demo.host.Main
```

Khi host đã thấy các class và tài nguyên provider, ranh giới discovery/parent delegation bị nhiễm: parent có thể tìm tài nguyên đăng ký provider của cả hai plugin, trong khi chính parent chỉ có một định nghĩa cho từng tên class. Kết quả phụ thuộc cấu hình và có thể làm `ServiceLoader` nhìn thấy provider ngoài ý muốn hoặc lỗi API. Đừng biến `-cp` của host thành một danh sách chung chứa mọi phiên bản plugin.

### 13.2. Đặt `spi.jar` độc lập vào từng loader và nạp child-first cả SPI

Nếu mỗi child tự định nghĩa `demo.spi.TextPlugin`, thì dù provider bên trong child có `implements TextPlugin`, **đó không phải `TextPlugin.class` mà host đang giữ**. Thông báo phổ biến khi `ServiceLoader` khám phá provider không phải subtype có thể là `ServiceConfigurationError`; phép ép kiểu thủ công cũng có thể gây `ClassCastException`.

Giải pháp là công bố hợp đồng trong parent và buộc các loader nhận SPI từ parent. Chỉ đưa các package implementation/dependency riêng vào danh sách child-first.

### 13.3. Để kiểu thư viện private xuất hiện trong chữ ký SPI

Hợp đồng sau **không phù hợp** với mục tiêu cô lập v1 và v2:

```java
// Minh họa thiết kế cần tránh, không phải ví dụ có thể chạy độc lập.
public interface BadPlugin {
    demo.lib.TextEngine getEngine();
}
```

Host sẽ phải hiểu kiểu `demo.lib.TextEngine` nào, trong khi v1/v2 là hai lớp khác nhau. Thay vào đó, trả về kiểu chung trong `spi.jar`, một DTO được parent định nghĩa, hoặc dữ liệu chuẩn như `String`, `byte[]`, `InputStream` với quy định sở hữu/vòng đời rõ ràng.

Không chỉ return type: tham số, exception công khai, callback và interface cha cũng phải được đánh giá theo cùng nguyên tắc. Đừng trao đổi trực tiếp object của thư viện private qua hai vùng loader rồi ép kiểu ở phía host.

### 13.4. Cứ `close()` loader là có thể nâng cấp nóng

`URLClassLoader.close()` đóng các tài nguyên mà loader quản lý; class và instance có thể vẫn tồn tại nếu registry, thread, context class loader, callback, singleton hoặc static field ở nơi khác còn giữ tham chiếu. Thay plugin lúc JVM đang chạy đòi hỏi quy trình dừng sử dụng, đóng tài nguyên, gỡ đăng ký, giải phóng tham chiếu, tạo loader mới và kiểm tra tính an toàn của request đang chạy.

Không nên mô tả `ServiceLoader.reload()` như chức năng “thay JAR”. Nó chỉ xóa cache provider của đối tượng `ServiceLoader` tương ứng, không tự thay URL, phiên bản JAR, class loader hay các instance đã được host giữ.

## 14. Lỗi điển hình và cách xác định nguyên nhân

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `NoSuchMethodError` khi plugin gọi thư viện | Provider biên dịch với API v2 nhưng runtime liên kết tên class vào bản v1 (hoặc ngược lại) | Kiểm tra JAR trong từng loader và phương thức thực có trong class |
| `ServiceConfigurationError: ... not a subtype` | Provider thực thi bản SPI khác loader với SPI host | Kiểm tra danh tính `TextPlugin.class`, chính sách parent-first và việc đóng SPI vào plugin |
| `ClassCastException` dù tên class giống | Hai object `Class<?>` được định nghĩa bởi hai loader khác nhau | So sánh `Class.getClassLoader()` và `Class<?>` thay vì chỉ `getName()` |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Plugin thiếu JAR riêng hoặc phụ thuộc chuyển tiếp | Kiểm tra `oldJars`/`newJars`, nội dung JAR và đường dẫn thật |
| `Expected 1 provider, found 0` | Không tìm thấy file `META-INF/services` hoặc JAR provider ngoài phạm vi loader | Kiểm tra file đăng ký và số provider mà loader phát hiện |
| `Expected 1 provider, found 2` | Một loader thấy nhiều tài nguyên provider hoặc parent đã công bố provider | Rà soát host classpath, `getResources` và thành phần nào sở hữu metadata |
| Chạy một plugin đúng, thêm plugin thứ hai thì lỗi | Hai bản của thư viện bị gộp vào một loader hoặc host classpath | Tách loader và bảo đảm host chỉ chứa contract/host |
| Loader được đóng nhưng lớp chưa unload | Có tham chiếu sống tới class, instance, luồng hoặc loader | Kiểm tra registry, thread context loader, callback, cache và lifecycle |
| Class nạp đúng nhưng dữ liệu trả về không ép kiểu được | Kiểu private của child rò qua chữ ký hoặc payload | Đưa kiểu giao tiếp vào SPI/API do parent sở hữu |

Các lỗi liên kết trong JVM có thể phát sinh **muộn**, ở lần đầu thực thi một đường mã cần đến method/class đó. Việc plugin khởi tạo thành công chưa chứng minh toàn bộ dependency đã tương thích. Nên chạy smoke test qua các chức năng quan trọng của mỗi provider.

## 15. Những giới hạn của cô lập bằng class loader

Class loader giúp giải quyết xung đột **class namespace**, nhưng không tự cung cấp:

- **Cô lập tiến trình hoặc quyền:** provider chạy trong JVM của host và có thể truy cập tài nguyên tương ứng. Không coi class loader là sandbox để chạy mã không tin cậy.
- **Cô lập trạng thái hệ thống:** system properties, environment, tiến trình, file, port, một số cache/JDK singleton và tài nguyên native có thể vẫn được chia sẻ.
- **Tương thích tuyệt đối:** thư viện dùng JNI/native libraries, reflective access, context class loader, `ServiceLoader` lồng nhau hoặc callback phức tạp có thể yêu cầu cấu hình bổ sung.
- **Tự động quản lý bản vá bảo mật:** mỗi phiên bản thư viện vẫn phải được quản lý SBOM, CVE, giấy phép và vòng đời phát hành riêng.
- **Hot reload an toàn:** dừng plugin cũ và tạo loader mới là bài toán vòng đời, nhất là trong ứng dụng đa luồng.

Trong môi trường lớn, có thể dùng framework plugin, module layer JPMS hoặc process isolation nếu yêu cầu phức tạp hơn. Java Platform Module System dùng khái niệm module/layer và khai báo `uses`/`provides`; ví dụ này **chủ ý chỉ dùng classpath và `URLClassLoader`** để tập trung vào ranh giới kiểu chung và dependency riêng.

## 16. Kiểm tra thiết kế trước khi đưa vào dự án

Hãy trả lời các câu hỏi sau cho mỗi kiến trúc plugin:

1. **Ai sở hữu SPI?** Có đúng một class loader cha định nghĩa interface và các kiểu giao tiếp chung không?
2. **Package nào private?** Loader con chỉ tự định nghĩa lớp implementation và dependency thật sự được cô lập, hay vô tình tạo thêm một bản API?
3. **Mỗi plugin nhìn thấy phiên bản nào?** Compile classpath và runtime URL của nó có cùng phiên bản thư viện cần thiết không?
4. **Provider discovery nằm ở đâu?** Có truyền đúng class loader vào `ServiceLoader` và đặt `META-INF/services` trong đúng plugin JAR không?
5. **Kiểu nào vượt qua biên giới?** Có DTO, exception hoặc callback mang kiểu riêng của child gây khó ép kiểu ở host không?
6. **Lỗi phát hiện khi nào?** Có kiểm tra provider, chạy smoke test và ghi log class loader/JAR để chẩn đoán liên kết sai không?
7. **Vòng đời thế nào?** Ai đóng loader, hủy provider, dừng thread và giải phóng tài nguyên khi gỡ plugin?
8. **Ranh giới an toàn?** Các plugin có đáng tin cậy, và có cần cô lập bằng tiến trình thay vì chỉ class loader không?

## 17. Bài tập củng cố

1. **Chứng minh phụ thuộc phiên bản:** đổi riêng phương thức của `lib-v2` từ `render(String)` sang `render(String, boolean)` nhưng chưa biên dịch lại provider v2. Dự đoán lỗi liên kết nào có thể xuất hiện khi gọi `modern` và giải thích vì sao `legacy` vẫn hoạt động trong loader riêng. Sau đó biên dịch lại provider v2 theo API mới.
2. **Cố tình làm sai classpath:** thêm hai bản thư viện vào host classpath và quan sát vì sao kết quả khám phá có thể thay đổi. Trước khi thử, hãy lưu bản lệnh đúng để khôi phục môi trường demo.
3. **Kiểm tra danh tính lớp:** in `oldPlugin.getClass().getClassLoader()` và `newPlugin.getClass().getClassLoader()`. Vì sao tên class giống nhau nhưng không thể kết luận chúng là cùng kiểu?
4. **Đưa một DTO dùng chung:** thêm `demo.spi.TransformRequest` vào `spi.jar`, đổi hợp đồng thành `transform(TransformRequest)`. Kiểm tra cả hai plugin dùng đúng DTO từ parent.
5. **Thêm provider thứ ba:** tạo một bản phụ thuộc v3 trong loader thứ ba. Host chỉ cần giữ các đối tượng qua interface chung. Thiết kế thêm định danh và quy tắc chọn provider, không phụ thuộc vào thứ tự discovery.
6. **Giải phóng loader:** mô tả điều gì sẽ giữ một loader không thể được thu hồi nếu một thread của plugin tiếp tục chạy sau khi host đóng loader.

**Nguyên tắc quyết định:** để chạy song song hai phiên bản thư viện có tên class trùng nhau, cần **loader riêng cho dependency riêng**; để host nói chuyện được với cả hai, cần **một lớp hợp đồng chung do parent định nghĩa**. Việc tổ chức JAR, classpath, cơ chế ủy quyền và kiểu dữ liệu vượt biên giới phải cùng tuân thủ nguyên tắc đó.