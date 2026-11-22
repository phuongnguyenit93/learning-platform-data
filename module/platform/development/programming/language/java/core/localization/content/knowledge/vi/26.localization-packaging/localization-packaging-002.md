# Class loader và phạm vi tìm tài nguyên trong Java

## 1. Khi tài nguyên có trong dự án nhưng Java vẫn báo “không tìm thấy”

Một ứng dụng Java đa ngôn ngữ thường lưu thông điệp trong `.properties`, template, ảnh, cấu hình hoặc dữ liệu văn bản đi kèm mã chương trình. Lúc chạy trong IDE, chương trình có thể tìm được `messages_vi.properties`, nhưng sau khi đóng gói JAR hoặc chuyển sang một plugin lại nhận `null` hay `MissingResourceException`.

Điều này không nhất thiết do file bị xóa. Rất có thể **file tồn tại nhưng không nằm trong phạm vi tìm kiếm của class loader hoặc module đang được dùng**.

Ví dụ, một resource được đóng gói ở đường dẫn:

```text
demo/messages_vi.properties
```

nhưng code gọi:

```java
SomeClass.class.getClassLoader()
        .getResource("messages_vi.properties");
```

Thì class loader sẽ tìm tên `messages_vi.properties` **ngay dưới gốc của đường tìm tài nguyên**, không tự thêm `demo/`. Nếu file nằm ở `demo/messages_vi.properties`, tên đúng cho `ClassLoader.getResource` thường là `"demo/messages_vi.properties"`.

Một tình huống khác: code trong ứng dụng chính dùng **application class loader**, nhưng file bản dịch nằm trong **plugin JAR do một URLClassLoader khác nạp**. Đường tìm của application loader không tự bao gồm tất cả plugin loaders trong JVM.

Với Java 9+ và Java 17, còn có **Java Platform Module System (JPMS)**: một resource trong **named module** có thể bị đóng gói và không được hiển thị cho code bên ngoài module, ngay cả khi package chứa resource đã được export cho truy cập type.

Bài học tập trung vào: classpath, class loader identity, tên resource, cách tìm tương đối/tuyệt đối, `ResourceBundle`, JAR, thread context class loader, named module, lỗi thường gặp và kiểm thử trên Java 17.

## 2. Tài nguyên khác lớp Java và khác file hệ điều hành

Một **resource** là dữ liệu được ứng dụng dùng lúc chạy nhưng không nhất thiết là mã class: file `.properties`, `.json`, `.txt`, hình ảnh, template, chứng thư, v.v. Trước hết cần phân biệt:

| Đối tượng | Ví dụ | Cách truy cập điển hình |
| --- | --- | --- |
| Class Java | `demo.App` | `ClassLoader.loadClass("demo.App")` |
| Resource trên classpath | `demo/messages_vi.properties` | `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream` |
| ResourceBundle | `demo.Messages` với các file `Messages_vi.properties` | `ResourceBundle.getBundle("demo.Messages", locale)` |
| File ngoài trên đĩa | `/etc/app/config.properties` hoặc `C:\data\settings.txt` | `Path`, `Files`, `FileInputStream` |
| Resource trong JAR | Entry `demo/messages_vi.properties` | Thường đọc qua resource stream từ class loader/module |
| Resource thuộc named module | `demo/messages_vi.properties` bên trong module `app.main` | `Class.getResourceAsStream` hoặc `Module.getResourceAsStream` với quy tắc đóng gói |

**Resource trên classpath không phải là đường dẫn file hệ điều hành**. Java tìm tên resource bằng một chuỗi `/`-separated bên trong các root đã cấu hình; nó có thể đến từ thư mục hoặc từ một JAR. Nếu file nằm trong JAR, thường không thể áp dụng `Path.of(url.toURI())` như với một file bình thường trên đĩa.

Không nên dùng `new File("src/main/resources/...")` cho code runtime: `src/main/resources` là đường dẫn nguồn trong dự án, **không phải một đường dẫn đảm bảo tồn tại khi chạy bản phân phối**.

### 2.1. “Classpath root” là gì?

Ví dụ có cấu trúc đầu ra:

```text
out/
  demo/
    App.class
    messages.txt
  l10n/
    Messages.properties
    Messages_vi.properties
  settings.json
```

Khi chạy `java -cp out demo.App`, `out` là **classpath root**, không phải thư mục `demo`:

- Tên `demo/messages.txt` chỉ tới `out/demo/messages.txt`.
- Tên `l10n/Messages_vi.properties` chỉ tới `out/l10n/Messages_vi.properties`.
- Tên `settings.json` chỉ tới `out/settings.json`.
- Tên `messages.txt` sẽ không tự chỉ tới `out/demo/messages.txt`.

Nếu tài nguyên ở JAR, classpath root sẽ được hiểu là **gốc các entry trong JAR**. Ví dụ entry `l10n/Messages_vi.properties` trong `app.jar` có cùng tên resource logic như trong `out/l10n/…`.

## 3. ClassLoader và phạm vi tìm kiếm

`java.lang.ClassLoader` có trách nhiệm nạp class và có API tìm resource. Mỗi class ở runtime được nhận diện không chỉ bởi **tên đầy đủ** mà còn bởi **defining class loader**. Hai loader khác nhau có thể định nghĩa hai class trùng tên mà JVM xem là hai type khác nhau.

Đối với resource, điều quan trọng là:

- Mỗi loader có **đường tìm** và chiến lược ủy quyền riêng.
- Resource chỉ được tìm thấy nếu nó có thể nhìn thấy qua loader đang sử dụng **và** tuân quy tắc module/encapsulation.
- `getResource(...)` trả **`URL`** hoặc `null`.
- `getResourceAsStream(...)` trả **`InputStream`** hoặc `null`.
- Có thể xuất hiện **nhiều resource trùng tên** trên classpath; API một kết quả không có nghĩa đã kiểm tra hết tất cả.
- Với parent delegation mặc định, lớp cha có thể được tìm trước lớp con; custom loader có thể triển khai chiến lược khác.

### 3.1. Ba loader quan trọng trong Java 17

Trong runtime Java tiêu chuẩn thường có:

1. **Bootstrap class loader:** nạp những lớp lõi của nền tảng; trong Java API thường được biểu diễn bằng `null` khi hỏi loader của một số class nền tảng.
2. **Platform class loader:** `ClassLoader.getPlatformClassLoader()`; liên quan các module nền tảng.
3. **System/application class loader:** `ClassLoader.getSystemClassLoader()`; thường nạp application classes theo cấu hình launcher.

Tuy vậy, hệ thống thực tế có thể có loaders khác: `URLClassLoader`, container loader, plugin loader, module layer, test runner, app server hoặc framework loader.

**Không giả định loader của mọi class chính là system loader.** Cách đáng tin là xem class đang xét được nạp từ đâu bằng `MyClass.class.getClassLoader()` và biết rõ loader nào quản lý tài nguyên cần tìm.

Ví dụ minh họa:

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader mine = MyClass.class.getClassLoader();
ClassLoader context = Thread.currentThread()
        .getContextClassLoader();
```

Đoạn này nằm trong một method có class `MyClass` ở phạm vi nhìn thấy. Ba tham chiếu **có thể trùng hoặc khác nhau**; không lấy việc bằng nhau trong một lần chạy local làm quy tắc cho mọi container/plugin.

### 3.2. Parent delegation không phải tìm ở tất cả loaders

Ở `ClassLoader.getResource(name)` tiêu chuẩn, cơ chế mặc định tìm từ parent rồi mới tìm local khi cần. Ví dụ:

```text
Application / Parent Loader
          |
          +----> plugin loader A
          |
          +----> plugin loader B
```

Nếu A và B là hai child loaders riêng, resource chỉ nằm trong B **không tự động xuất hiện** khi code hỏi A hoặc hỏi parent. Parent không biết mọi child và một child không phải đương nhiên tra cứu sibling.

Một số framework triển khai **child-first** hay quy tắc tùy chỉnh để cô lập plugin. Không khẳng định mọi `ClassLoader` đều parent-first nếu đang làm việc trong môi trường có loader tùy chỉnh.

## 4. Class.getResource và ClassLoader.getResource: khác tên và vị trí gốc

Hai họ API trông giống nhau nhưng cách giải tên khác nhau:

| API | Tên `"hello.txt"` có ý nghĩa gì? | Tên `"/demo/hello.txt"` có ý nghĩa gì? |
| --- | --- | --- |
| `demo.App.class.getResource(name)` | Tương đối với package `demo` → `demo/hello.txt` | Gốc tuyệt đối của resource namespace → `demo/hello.txt` |
| `demo.App.class.getResourceAsStream(name)` | Tương đối với package `demo` | Dùng gốc tuyệt đối khi có `/` đầu tên |
| `demo.App.class.getClassLoader().getResource(name)` | Tên trực tiếp tính từ classpath resource root | **Không** thêm slash đầu; dùng `demo/hello.txt` |
| `ClassLoader.getSystemResource(name)` | Gốc tìm của system class loader | **Không** dùng slash đầu như `Class.getResource` |

**Quy tắc thực hành:**

- Với `Class.getResource("name")`, **không có `/` đầu** → tên được tiền tố bằng package của class anchor.
- Với `Class.getResource("/some/path")`, **có `/` đầu** → tên từ gốc; Java bỏ slash này khi chuyển cho cơ chế tìm resource phù hợp.
- Với `ClassLoader.getResource("some/path")`, dùng **tên tính từ root, không có slash đầu**. Không truyền `"/some/path"` theo thói quen của `Class.getResource`.

Trong **named module**, `Class.getResource` còn biết module mà class anchor thuộc về; chính sách truy cập khác với `ClassLoader.getResource` tìm xuyên các module. Những quy tắc module sẽ được trình bày riêng ở phần sau.

### 4.1. Vì sao hai cách tìm cùng một file?

Nếu `demo.App` có resource `demo/hello.txt` trong cùng classpath root, cả ba cách sau có thể tìm cùng entry:

```java
App.class.getResource("hello.txt");
App.class.getResource("/demo/hello.txt");
App.class.getClassLoader().getResource("demo/hello.txt");
```

Đây là code minh họa trong class `App` thuộc package `demo` (hoặc method có import `demo.App`).

**Sai phổ biến:** `App.class.getClassLoader().getResource("/demo/hello.txt")` — slash đầu thuộc cú pháp của `Class.getResource`, không phải cú pháp classloader API. Trên class loader chuẩn, tên này thường trả `null`.

### 4.2. Không chỉ để đọc bản dịch

Cùng quy tắc áp dụng cho ảnh `logo.png`, file text `email-template.txt`, tệp JSON `schema.json` hoặc properties. Việc extension là `.properties` không khiến Java tự nhận ra chúng là resource bundle; chỉ `ResourceBundle.getBundle(...)` mới có cơ chế bundle naming, locale candidates và cache riêng.

## 5. Ví dụ Java 17 độc lập: nhìn rõ phạm vi tìm resource

Chuẩn bị cấu trúc thư mục:

```text
project/
  src/
    demo/
      ResourceScopeDemo.java
  resources/
    demo/
      greeting.txt
```

Nội dung file `resources/demo/greeting.txt` (UTF-8):

```text
Xin chào
```

Lưu `src/demo/ResourceScopeDemo.java`:

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class ResourceScopeDemo {
    public static void main(String[] args) throws Exception {
        Class<?> anchor = ResourceScopeDemo.class;
        ClassLoader loader = anchor.getClassLoader();

        System.out.println("relative=" +
                (anchor.getResource("greeting.txt") != null));
        System.out.println("absolute=" +
                (anchor.getResource("/demo/greeting.txt") != null));
        System.out.println("loaderRoot=" +
                (loader.getResource("demo/greeting.txt") != null));
        System.out.println("wrongLoaderPath=" +
                (loader.getResource("greeting.txt") != null));

        try (InputStream input = Objects.requireNonNull(
                anchor.getResourceAsStream("greeting.txt"),
                "greeting.txt not found")) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            System.out.println("content=" + text);
        }
    }
}
```

Biên dịch và chuẩn bị classpath (shell Bash trên macOS/Linux; Windows PowerShell làm các thao tác copy tương đương):

```bash
mkdir -p out/demo
javac -encoding UTF-8 -d out src/demo/ResourceScopeDemo.java
cp resources/demo/greeting.txt out/demo/greeting.txt
java -cp out demo.ResourceScopeDemo
```

Stdout với đúng cấu trúc đã chỉ định:

```text
relative=true
absolute=true
loaderRoot=true
wrongLoaderPath=false
content=Xin chào
```

Diễn giải:

- `getResource("greeting.txt")` từ `demo.ResourceScopeDemo` tìm `demo/greeting.txt`.
- `getResource("/demo/greeting.txt")` bắt đầu từ root và tới cùng resource.
- `loader.getResource("demo/greeting.txt")` dùng path tính từ root.
- `loader.getResource("greeting.txt")` tìm sai vị trí nên nhận `null` trong classpath test chỉ chứa resource đã nêu.
- `InputStream` được đóng bằng `try-with-resources`, và byte UTF-8 được decode tường minh.

Không dùng `Objects.requireNonNull` nếu sản phẩm muốn fallback mềm; ví dụ này cố ý **fail fast** khi một resource bắt buộc không có để tránh màn hình trống mà không có thông báo.

### 5.1. Resource path là path logic, không phải OS path

Ngay cả trên Windows, tên resource vẫn dùng dấu gạch chéo **`/`**, ví dụ `"demo/greeting.txt"`, không dùng `"demo\\greeting.txt"` tùy hệ điều hành. Đường dẫn classpath được JVM thiết lập theo cú pháp của launcher; bản thân resource entry có tên slash-separated.

**Cần phân biệt:** trong lệnh `java -cp`, các **classpath entries** được phân tách bằng ký tự phụ thuộc OS (thường `:` trên Unix, `;` trên Windows). Nhưng **tên resource bên trong entry** vẫn dùng `/`.

## 6. Null, URL và InputStream: tìm thấy không đồng nghĩa đọc thành công

`Class.getResource`/`ClassLoader.getResource` trả `URL` hoặc `null`. `getResourceAsStream` trả `InputStream` hoặc `null`, không tự ném `FileNotFoundException` khi resource không thấy.

Ví dụ đúng về xử lý lỗi:

```java
try (InputStream in = App.class.getResourceAsStream(
        "/l10n/Messages_vi.properties")) {

    if (in == null) {
        throw new IllegalStateException("Missing resource");
    }

    byte[] data = in.readAllBytes();
    // Decode bằng charset đã thỏa thuận với người tạo resource.
}
```

Đây là đoạn minh họa trong method của `App`, có xử lý `IOException` và import `InputStream`.

Với resource tùy loại, `URL.openStream()` hoặc `getResourceAsStream` có thể ném `IOException` trong lúc đọc; kiểm tra resource URL có tồn tại **không** bảo đảm file có thể đọc được đầy đủ. Thực tế còn có quyền truy cập, file JAR hỏng, resource provider hoặc sự cố I/O.

**Không biến mọi thiếu resource thành `null` rồi tiếp tục lặng lẽ.** Trong hệ thống đa ngôn ngữ, file thông điệp bắt buộc vắng mặt nên được báo lỗi rõ, có fallback được thiết kế và test.

### 6.1. Đọc resource trong JAR

Khi đóng gói, URL có thể có dạng ý tưởng:

```text
jar:file:/opt/app/app.jar!/demo/greeting.txt
```

Đây **không phải** một đường dẫn `Path` của default filesystem có thể truyền trực tiếp vào `Files.readString(Path.of(url.toURI()))` trong mọi môi trường.

Khi chỉ cần nội dung text hoặc binary, dùng stream:

```java
try (InputStream in =
        App.class.getResourceAsStream("/demo/greeting.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing resource");
    }
    String text = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
}
```

Đoạn này nằm trong method của `App` với `StandardCharsets` được import. Cách đọc stream hoạt động cho classpath directory và JAR nếu loader/module cho phép truy cập. Đừng giả định URL luôn mở được dưới dạng file path hoặc file có thể ghi.

## 7. ResourceBundle dùng class loader như thế nào?

`java.util.ResourceBundle` giải quyết một tầng cao hơn: lấy **family** tài nguyên theo `baseName` và `Locale`, có quy tắc ứng viên, fallback và cache.

Ví dụ family:

```text
l10n/
  Messages.properties
  Messages_en.properties
  Messages_vi.properties
  Messages_vi_VN.properties
```

Các file thường chứa cặp `key=value`. Gọi:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "l10n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

Khi tìm, `ResourceBundle` xem `baseName` là tên đầy đủ **theo package, dùng dấu chấm**, không phải filename đầy đủ:

- `"l10n.Messages"` → `l10n/Messages.properties` và các biến thể theo locale.
- `"l10n.Messages_vi"` không phải baseName thích hợp nếu muốn hệ thống tự chọn locale từ `l10n.Messages`.
- Không truyền `"l10n/Messages.properties"` rồi mong `getBundle` xử lý như `getResourceAsStream`.
- Nếu không thấy bundle thích hợp và không có đường fallback hợp lệ, `getBundle` ném `MissingResourceException`, không trả `null`.

Trong Java 17, các overload không truyền `ClassLoader` được định nghĩa theo **caller module** (và các quy tắc loader liên quan khi chạy trong unnamed module), không nên giả định luôn dùng **thread context class loader**.

### 7.1. Chỉ định loader rõ ràng khi cần

Với ứng dụng classpath hoặc plugin thuộc unnamed module, có overload:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "l10n.Messages", locale, targetLoader);
```

Ý nghĩa:

- `"l10n.Messages"` là base name.
- `locale` là locale mục tiêu, **không phải class loader**.
- `targetLoader` định nghĩa phạm vi classpath/resource để tìm bundle trong ngữ cảnh API phù hợp.

Đừng đưa system loader vào overload này nếu resource thực sự chỉ thuộc child plugin loader. Cũng không nên lạm dụng loader tùy chỉnh cho tất cả bundle trong **named module**: JPMS có quy tắc module, visibility và provider riêng; có thể cần overload nhận `Module` hoặc `ResourceBundleProvider`.

### 7.2. Java 17 runnable: cùng loader, hai locale

Chuẩn bị:

```text
project/
  src/demo/BundleScopeDemo.java
  resources/l10n/Messages.properties
  resources/l10n/Messages_vi.properties
```

File `resources/l10n/Messages.properties`:

```properties
hello=Hello
appName=Example
```

File `resources/l10n/Messages_vi.properties` (UTF-8):

```properties
hello=Xin chào
appName=Ví dụ
```

Mã nguồn `src/demo/BundleScopeDemo.java`:

```java
package demo;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleScopeDemo {
    public static void main(String[] args) {
        ClassLoader loader =
                BundleScopeDemo.class.getClassLoader();

        ResourceBundle root = ResourceBundle.getBundle(
                "l10n.Messages", Locale.ROOT, loader);
        ResourceBundle vietnamese = ResourceBundle.getBundle(
                "l10n.Messages",
                Locale.forLanguageTag("vi-VN"),
                loader);

        System.out.println("root=" + root.getString("hello"));
        System.out.println("vi=" + vietnamese.getString("hello"));
        System.out.println("viName=" +
                vietnamese.getString("appName"));
    }
}
```

Bash:

```bash
mkdir -p out/l10n
javac -encoding UTF-8 -d out src/demo/BundleScopeDemo.java
cp resources/l10n/Messages*.properties out/l10n/
java -cp out demo.BundleScopeDemo
```

Với bộ file và JDK 17 chuẩn, stdout:

```text
root=Hello
vi=Xin chào
viName=Ví dụ
```

`ResourceBundle` tìm một bản dịch phù hợp từ family. Ở ví dụ này có `Messages_vi.properties` mà không cần `Messages_vi_VN.properties`; locale `vi-VN` có thể nhận biến thể `vi` theo cơ chế candidate lookup. Đó là **cơ chế lựa chọn bundle**, không phải `ClassLoader` tự đoán ngôn ngữ.

**Chú ý encoding:** kể từ JDK 9, `PropertyResourceBundle` mặc định đọc `.properties` theo UTF-8 và có chiến lược tương thích legacy ISO-8859-1; cấu hình system property như `java.util.PropertyResourceBundle.encoding` có thể ảnh hưởng. Với Java 17, nên lưu bundle trong UTF-8 nhất quán và pin/runtime test nếu có dữ liệu cũ.

### 7.3. Bundle caching: sửa file chưa chắc đọc được ngay

`ResourceBundle.getBundle` mặc định sử dụng cache; cùng baseName/locale/loader có thể trả bundle đã cache thay vì đọc lại file ngay. Khi thay file dịch lúc ứng dụng đang chạy, chỉ thay file không đủ để bảo đảm ứng dụng đã nạp bản mới.

Có API như:

```java
ResourceBundle.clearCache(loader);
```

Tuy nhiên:

- Nó liên quan cache của resource bundles, không làm thay đổi classpath hoặc khả năng thấy resource của loader.
- Không làm tài nguyên trong JAR tự cập nhật nếu file JAR không được thay đúng cách.
- Với named modules và provider, quản lý cache/visibility có quy tắc riêng.
- Cache theo loader có liên quan vòng đời plugin và nguy cơ giữ tham chiếu dữ liệu cũ.

Đây là đoạn minh họa trong method có biến `loader`. Không xem `clearCache` là giải pháp cho đường dẫn sai hoặc mở package thiếu.

## 8. Custom class loader và plugin: resource không tự “đi xuyên” mọi loader

Một plugin có thể được lưu riêng ngoài classpath chính:

```text
project/
  src/demo/PluginResourceDemo.java
  plugin-data/
    plugin/
      Labels.properties
```

File `plugin-data/plugin/Labels.properties`:

```properties
title=Plugin loaded
```

Ta tạo `URLClassLoader` nhìn vào thư mục `plugin-data`. Loader này biết resource mà application classpath không bắt buộc biết.

### Java 17 runnable: loader riêng cho một bundle

Tệp `src/demo/PluginResourceDemo.java`:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Locale;
import java.util.ResourceBundle;

public class PluginResourceDemo {
    public static void main(String[] args) throws Exception {
        URL root = Path.of("plugin-data")
                .toAbsolutePath().toUri().toURL();

        // Parent null: cô lập khỏi application classpath
        // trong demo đơn giản này.
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[]{root}, null)) {

            boolean visible = pluginLoader.getResource(
                    "plugin/Labels.properties") != null;

            ResourceBundle labels = ResourceBundle.getBundle(
                    "plugin.Labels", Locale.ROOT, pluginLoader);

            System.out.println("pluginVisible=" + visible);
            System.out.println("title=" +
                    labels.getString("title"));
        }
    }
}
```

Chạy từ thư mục `project` bằng Bash:

```bash
mkdir -p out
javac -encoding UTF-8 -d out src/demo/PluginResourceDemo.java
java -cp out demo.PluginResourceDemo
```

Stdout nếu đúng file `plugin-data/plugin/Labels.properties` như mô tả:

```text
pluginVisible=true
title=Plugin loaded
```

**Vì sao dùng `parent=null` trong ví dụ?** Để nhấn mạnh resource root của plugin và tránh tình huống parent ứng dụng đã có một resource cùng tên. Trong plugin production, parent loader không nên tùy tiện đặt `null`: plugin có thể cần API class từ host hoặc nhiều thư viện, và chính sách delegation ảnh hưởng type identity/security. Hãy dùng chiến lược loader của framework hoặc thiết kế classloading rõ ràng.

**Đừng lầm:** `URLClassLoader` được truyền URL của **thư mục gốc** `plugin-data`, không phải URL của `plugin-data/plugin/Labels.properties`. Resource path `plugin/Labels.properties` được tìm tương đối với root đó.

### 8.1. Khi plugin nằm trong JAR

Nếu plugin được đóng gói trong `plugin.jar` với entry `plugin/Labels.properties`, một `URLClassLoader` có URL của **chính file JAR** có thể đọc resource bằng cùng tên logic. Cách cài đặt phụ thuộc packaging, dependency visibility và Java module architecture.

Không thể chỉ thêm JAR vào một thư mục bất kỳ rồi mong application loader vốn đã được tạo sẽ tự quét nó. Phải thiết lập classpath/module path từ lúc khởi động hoặc xây plugin loader/layer phù hợp.

## 9. Thread context class loader (TCCL): công cụ của framework, không phải phép màu

Mỗi thread Java có thể có một **context class loader**, thường đọc bằng:

```java
ClassLoader tccl = Thread.currentThread()
        .getContextClassLoader();
```

Một số thư viện và frameworks (bao gồm những cơ chế service discovery nhất định) sử dụng TCCL để tìm class/resource khi code thư viện không biết trước loader cụ thể của ứng dụng/plugin.

Nhưng không phải **mọi** resource API tự dùng TCCL:

- `MyClass.class.getResource(...)` dựa vào class anchor và module của nó.
- `MyClass.class.getClassLoader().getResource(...)` dùng defining loader của class.
- `ClassLoader.getSystemResource(...)` dùng system loader.
- `ResourceBundle.getBundle(baseName, locale, loader)` dùng **loader được truyền**.
- `ResourceBundle.getBundle(baseName, locale)` phụ thuộc caller module/loader theo overload Java 17, **không có lời hứa tự dùng TCCL**.
- `Thread.currentThread().getContextClassLoader()` chỉ trả tham chiếu; caller phải **chủ động dùng** nó nếu đó là chính sách thư viện.

**Không nên “sửa” thiếu resource bằng cách set TCCL bừa bãi.** Thay đổi TCCL cho thread dùng chung có thể ảnh hưởng thư viện khác, nhất là thread pool, async jobs và application server.

### 9.1. Khi cần tạm đặt TCCL

Một framework đôi khi làm:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi thư viện được thiết kế dùng TCCL.
    // Ví dụ explicit: dùng chính TCCL để tra resource.
    ClassLoader current = thread.getContextClassLoader();
    URL url = current.getResource("plugin/Labels.properties");
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là code minh họa trong method có `pluginLoader` và import `java.net.URL`. `try/finally` bảo đảm khôi phục loader cũ khi hoàn tất. Với thread pool hoặc callback bất đồng bộ, **không** giả định TCCL sẽ tự được truyền qua mọi cơ chế và được restore bởi mọi thư viện.

### 9.2. Phân biệt ba identity

Trong plugin system, có thể khác nhau giữa:

1. **Defining loader của class đang gọi** (`SomeService.class.getClassLoader()`).
2. **System loader** (`ClassLoader.getSystemClassLoader()`).
3. **Context loader của thread** (`Thread.currentThread().getContextClassLoader()`).

Nếu kết quả khác nhau, việc chọn API không chính xác có thể khiến chương trình chỉ chạy được trong IDE nhưng không chạy trong app server. Hãy ghi log **danh tính loader** ở mức metadata không nhạy cảm khi chẩn đoán, tránh log dump toàn bộ đường dẫn nội bộ hoặc bí mật.

## 10. JPMS: named modules đặt thêm ranh giới tìm resource

Kể từ Java 9, bên cạnh class loader còn có **module**. Java 17 phân biệt:

- **Unnamed module**: thường chứa classes/resources chạy theo classpath.
- **Named module**: có module name và quy tắc `module-info.java`, exports, opens, requires và resource encapsulation.

Một class trong named module có thể truy cập tài nguyên **thuộc module của chính nó** qua `Class.getResourceAsStream` (với tên đúng). Tuy nhiên, `ClassLoader.getResource` tìm theo loader qua nhiều modules áp dụng quy tắc encapsulation chặt chẽ hơn.

Theo Java 17 API, resource **không phải `.class`** trong package của named module thường chỉ tìm thấy qua `ClassLoader.getResource` nếu package đó được **opened unconditionally**. Một package chỉ `exports` cho class access **không tương đương** `opens` cho resource access.

### 10.1. Exports và opens không giống nhau

| Khai báo | Mục tiêu chính | Có đồng nghĩa resource nhìn thấy qua mọi loader không? |
| --- | --- | --- |
| `exports demo.api;` | Cho module khác dùng public types trong package | **Không** |
| `opens demo.i18n;` | Mở package cho deep reflection và một số truy cập resource | Có thể cho phép truy cập resource theo các quy tắc JPMS |
| `opens demo.i18n to some.module;` | Mở có điều kiện cho một module khác | **Không đủ** cho `ClassLoader.getResource` đòi *unconditional* opens |
| Không `opens` | Package được đóng gói | Module chủ có thể đọc nội bộ; bên ngoài có thể bị từ chối |

**Cảnh báo phạm vi:** `ClassLoader.getResource` và `Module.getResourceAsStream` có điều kiện khác nhau. Trên named module, `ClassLoader.getResource` yêu cầu unconditional opens cho resource không phải `.class` trong package. `Module.getResourceAsStream` có thể cho phép resource khi package được mở tới **module caller**, và code bên trong module chủ có quyền nội bộ thích hợp. Không suy một hành vi từ API kia.

### 10.2. Module.getResourceAsStream

`Module.getResourceAsStream(name)` có khả năng đọc resource từ **module được chỉ định** theo Java 17 API; nó ném `IOException` khi đọc không thành công và trả `null` nếu tài nguyên không tồn tại hoặc không nhìn thấy.

Ví dụ bên trong một class của named module:

```java
Module ownModule = SomeClass.class.getModule();

try (InputStream stream = ownModule.getResourceAsStream(
        "demo/i18n/Messages_vi.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Resource not accessible");
    }
    // Đọc resource ...
}
```

Đây là code minh họa trong method có `SomeClass` thuộc module, import `java.io.InputStream`, xử lý `IOException`. Tên ở đây được định nghĩa theo resource path bên trong module.

Để truy cập resource của **module khác**, cần xem package có được mở phù hợp với module đang gọi hay không; chỉ biết `Module` object không tự phá được ranh giới encapsulation.

### 10.3. Khác biệt giữa Class.getResource và ClassLoader.getResource trong named module

Theo tài liệu Java 17:

- `Class.getResource` giải tên resource tương đối với package của class anchor (hoặc tuyệt đối khi có `/` đầu) rồi áp dụng truy cập theo module chứa class đó.
- `ClassLoader.getResource` có phạm vi theo loader và các điều kiện visibility nghiêm hơn cho các resource không phải `.class` trong named module.
- `Module.getResourceAsStream` tham chiếu module cụ thể, phù hợp khi code muốn nhận resource trong đúng module (vẫn tuân đóng gói).
- `ResourceBundle` ở named modules có cơ chế lookup/provider riêng và không nên giản lược thành một `getResource` duy nhất.

Vì vậy, khi tài nguyên bản dịch nằm **cạnh class trong cùng named module**, `Anchor.class.getResourceAsStream("...")` hoặc `Anchor.class.getModule().getResourceAsStream("full/path")` thường là ý tưởng dễ kiểm soát hơn là tìm qua system class loader.

### 10.4. Ví dụ minh họa module-info.java

```java
module demo.app {
    exports demo.api;

    // Ví dụ: mở package chứa resource ra ngoài không điều kiện.
    opens demo.i18n;
}
```

Đây là **file descriptor minh họa**, không phải chương trình chạy độc lập; để biên dịch phải có package `demo.api`, `demo.i18n` và cấu trúc dự án/module hợp lệ. Mở package vô điều kiện **không phải lúc nào cũng mong muốn**. Nếu chỉ code nội bộ module cần đọc tài nguyên, không tự động mở tài nguyên cho tất cả bên ngoài vì có thể tăng bề mặt truy cập.

Không dùng `opens` chỉ để chữa lỗi đường dẫn khi resource vốn không được đóng gói vào module/JAR; kiểm tra packaging trước.

## 11. ResourceBundle trong named modules và provider

`ResourceBundle.getBundle` có nhiều overload từ Java 9:

```java
ResourceBundle local = ResourceBundle.getBundle(
        "demo.i18n.Messages", locale);

ResourceBundle fromModule = ResourceBundle.getBundle(
        "demo.i18n.Messages", locale, module);
```

Đây là code minh họa với `locale` và `module` đã tồn tại. Overload nhận `Module` cho phép yêu cầu tìm bundle **on behalf of một module cụ thể**, vẫn tuân resource encapsulation.

Các điểm quan trọng:

1. Trong named module, `getBundle(baseName, locale)` có ngữ nghĩa **caller module**; không đơn giản dùng system loader cho mọi bundle.
2. Bundle cùng module có thể được đóng gói và tải theo quy tắc nội bộ; module khác chỉ truy cập được khi visibility/provider cho phép.
3. `ResourceBundleProvider` có thể giúp cung cấp bundle qua service provider module; liên quan khai báo `uses`/`provides` trong `module-info.java`.
4. `ResourceBundle.Control` chủ yếu dành cho unnamed modules/classpath; các overload với `Control` có thể ném `UnsupportedOperationException` khi dùng từ named module.
5. Với resource bundle `.properties`, phải đảm bảo file thực sự có trong module artifact và đúng baseName/locale suffix.
6. Java có cache resource bundles, vì vậy thay class loader/module hoặc file translation có thể cần xem vòng đời cache và cập nhật.

### Một lỗi migration hay gặp

Ứng dụng chuyển từ classpath sang module path, vẫn gọi:

```java
ResourceBundle.getBundle(
        "demo.i18n.Messages", Locale.forLanguageTag("vi-VN"),
        ClassLoader.getSystemClassLoader());
```

Code có thể không còn tìm được bundle đóng gói trong named module vì resource encapsulation, dù trước khi modularize chạy bình thường. Không nên mở mọi package ra toàn cục chỉ để giữ nguyên lời gọi cũ. Cần chọn lại cách load theo **module của caller**, dùng `Module` overload hoặc provider API theo kiến trúc dự án.

## 12. Đóng gói JAR: có file nguồn chưa chắc có resource trong artifact

Một lỗi rất phổ biến khi deploy:

```text
src/main/resources/l10n/Messages_vi.properties  ✓ có trên máy dev
target/app.jar / build/libs/app.jar               ? chưa chắc chứa
```

Maven/Gradle/IDE thường có cơ chế copy resources, nhưng cấu hình tùy dự án có thể loại trừ file, đổi thư mục đầu ra hoặc lọc nội dung. Do đó, khi resource không thấy sau deploy, nên kiểm tra **JAR artifact thực** thay vì chỉ kiểm tra `src/main/resources`.

Một ví dụ:

```bash
jar tf app.jar
```

Đầu ra phải có entry tài nguyên cần thiết, ví dụ `l10n/Messages_vi.properties`, **nếu đó là nơi ứng dụng kỳ vọng tìm**. Tên entry phải khớp đường dẫn resource, bao gồm chữ hoa/thường (JAR entry names thường phân biệt case).

Các câu hỏi cần kiểm tra:

- Resource có thật trong JAR hay nằm ở thư mục nguồn nhưng chưa được copy?
- Resource nằm tại root nào? Có bị thừa tiền tố như `resources/` không?
- Classpath của `java -cp` hoặc `java -jar` thực sự là gì?
- Khi dùng `java -jar`, tham số `-cp` trong nhiều tình huống không quyết định classpath như ta nghĩ; cần hiểu launcher và manifest của JAR.
- Trong fat JAR/launcher đặc biệt, có custom nested-JAR loader hay resource URI khác `jar:file` thường?
- Module path có đổi quy tắc visibility so với classpath?
- Có bản dịch trùng tên ở nhiều dependency JAR không?

### Đừng biến URL resource thành Path mặc định

Resource trong JAR là **JAR entry**, không phải file path bình thường. Nếu cần bytes, dùng `InputStream`. Nếu một thư viện bên thứ ba **bắt buộc** cần file path vật lý, có thể cần extract resource ra thư mục tạm có quản lý vòng đời và an toàn, hoặc dùng filesystem provider thích hợp; đừng ép mọi URL thành `Path.of(...)`.

## 13. Resource trùng tên: getResource và getResources

Có thể hai dependency cùng đóng gói:

```text
config/defaults.properties
```

Khi đó:

- `loader.getResource("config/defaults.properties")` thường chỉ trả **một** URL tìm thấy theo search order của loader.
- `loader.getResources("config/defaults.properties")` trả `Enumeration<URL>` để duyệt những resource phù hợp mà loader thấy.
- `loader.resources("config/defaults.properties")` (Java 9+) trả `Stream<URL>`.
- `ClassLoader.getSystemResources(name)` dùng **system loader**, không phải một phép quét tất cả loader đang sống.

Đối với named modules, `getResources` cũng chịu giới hạn visibility/opens. Thứ tự resource trong nhiều modules cùng loader có thể không được xác định; không dựa vào “JAR nào thắng” nếu ứng dụng cần cấu hình có thứ tự rõ.

### Ví dụ duyệt mọi URL

```java
ClassLoader loader = App.class.getClassLoader();
Enumeration<URL> urls = loader.getResources(
        "config/defaults.properties");

while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    // Log/trích xuất có kiểm soát.
}
```

Đây là code minh họa trong method với `App` và import `java.net.URL`, `java.util.Enumeration`, xử lý `IOException`.

Đừng dùng `getResource` để hợp nhất nhiều bản dịch trùng tên một cách tự động. `ResourceBundle` có quy tắc candidate/fallback theo locale, không phải thuật toán merge toàn bộ resources `.properties` trong các JAR. Nếu plugin được phép đóng góp nhiều bundle, thiết kế provider/namespace hoặc loader strategy rõ ràng.

## 14. Khi nào ResourceBundle gặp MissingResourceException?

`MissingResourceException` có thể xuất hiện vì những nguyên nhân khác nhau:

1. `baseName` sai (dùng slash thay dot, thêm `.properties`, sai package).
2. Không có bản bundle phù hợp và không có root/default fallback theo chính sách.
3. Bundle file có nhưng không được copy vào classpath/JAR.
4. Code đang dùng **sai class loader**; bản dịch nằm trong plugin loader khác.
5. Code được chuyển sang **named module** và resource không thấy theo module encapsulation.
6. Tài nguyên có trong artifact nhưng classpath/module path khác với giả định.
7. File bundle có nhưng **key** được yêu cầu không tồn tại trong chuỗi bundle/parent.
8. Tên file bị khác chữ hoa/thường hoặc dùng locale suffix không đúng quy ước.

Cần phân biệt hai lỗi:

- **Không tìm được bundle family:** `getBundle(...)` ném `MissingResourceException`.
- **Có bundle nhưng thiếu key:** `bundle.getString("some.key")` cũng ném `MissingResourceException`, nhưng nguyên nhân là không thấy key trong bundle và chuỗi fallback của nó.

Không nên “fix” mọi lỗi này bằng cách tự tạo bundle rỗng, vì có thể che mất bản dịch bắt buộc. Khi chuẩn bị nội dung cho nhiều locale, nên có **root fallback** phù hợp và kiểm thử toàn bộ key bắt buộc.

### 14.1. Chẩn đoán resource trước khi chẩn đoán fallback

Một quy trình hiệu quả:

1. Xác nhận resource name theo namespace của API đang dùng.
2. Xác nhận file có trong **artifact đã deploy**.
3. Xác nhận class loader/module mà code thực sự dùng.
4. Dùng `getResource` hoặc `getResourceAsStream` với **đúng** namespace để xem tài nguyên có nhìn thấy hay không.
5. Nếu raw resource có thể nhìn thấy, mới kiểm tra `ResourceBundle` naming, candidate locale, key, cache và provider.
6. Với named modules, kiểm tra `exports`/`opens`/resource access, không suy thẳng từ kết quả classloader lookup.

**Điểm tinh vi:** raw lookup bằng `ClassLoader.getResource` có thể thất bại với resource ở named module dù code trong cùng module vẫn tải bundle hoặc resource qua API module-aware được. Vì thế, bước 4 phải dùng **đúng API và scope của tình huống**, không coi system loader là “tiêu chuẩn tuyệt đối” để chẩn đoán mọi module.

## 15. Thread context loader trong service/plugin thực tế

Một thư viện chung thường được nạp bằng parent loader nhưng cần tra resources của plugin/user module. Nếu thư viện chỉ gọi `Library.class.getResource(...)`, nó sẽ neo vào library class/module, không nhất thiết thấy resources của plugin.

Có vài cách thiết kế:

| Cách | Khi nào phù hợp | Rủi ro cần quản lý |
| --- | --- | --- |
| Truyền `ClassLoader` tường minh | Plugin/resource do loader riêng quản lý | Caller phải truyền loader đúng |
| Truyền `Class<?> anchor` | Resource đặt cạnh class thuộc plugin | Cần hiểu relative/absolute naming và module |
| Truyền `Module` | Tài nguyên đóng gói trong named module | Phải tuân encapsulation |
| Dùng TCCL theo contract của framework | Thư viện được thiết kế tìm qua context | Phải restore khi dùng thread pool |
| Dùng `ResourceBundleProvider` | Bundle phân phối ở các provider modules | Cần module descriptor/service plumbing |
| Đưa mọi resource vào system classpath | Demo đơn giản | Không thích hợp cho nhiều kiến trúc cô lập |

Một API của thư viện có thể nhận một **anchor class** hoặc loader được chỉ định bởi host, ví dụ:

```java
static InputStream findRequiredResource(
        Class<?> anchor, String absoluteName) {
    InputStream in = anchor.getResourceAsStream(absoluteName);
    if (in == null) {
        throw new IllegalArgumentException(
                "Resource missing: " + absoluteName);
    }
    return in;
}
```

Đây là method helper minh họa; caller phải đóng stream trả về. Nếu `absoluteName` không bắt đầu bằng `/`, nó được hiểu tương đối với package của `anchor`. Nếu thư viện muốn tham chiếu module tài nguyên thay vì class cụ thể, thiết kế overload nhận `Module` và các quy tắc access phù hợp.

## 16. Locale, class loader và bundle lookup là ba trục khác nhau

Một lỗi hiểu sai thường gặp là cho rằng:

> “Đã truyền `Locale.forLanguageTag("vi-VN")` thì Java phải tự nhìn thấy file `Messages_vi.properties` ở bất kỳ chỗ nào trên máy.”

Không đúng. Có ba quyết định riêng:

| Trục | Câu hỏi | API/concept |
| --- | --- | --- |
| **Locale** | Muốn nội dung dịch cho ngôn ngữ/khu vực nào? | `Locale` |
| **Resource naming** | Family/path nào chứa dữ liệu? | `baseName`, resource name |
| **Class loader/module scope** | Dữ liệu nào được runtime hiện tại phép tìm? | `ClassLoader`, `Class`, `Module` |

Có thể đúng locale nhưng sai loader; đúng loader nhưng sai baseName; đúng baseName nhưng file không có trong JAR; đúng file nhưng package không mở ra cho module caller.

Ngoài ra, `Locale.setDefault(...)` thay đổi default locale toàn JVM, **không** làm thêm JAR vào classpath và không sửa visibility của named module. Không dùng setDefault để xử lý lỗi đóng gói resource.

### Vì sao bài này là một phần localization?

Localization không chỉ là chọn mẫu định dạng số/ngày, mà còn là **bảo đảm nội dung dịch được đóng gói và tra cứu đúng nơi**. Khi ứng dụng nhiều module/plugin, bản dịch có thể được chia theo feature. Nếu class loader scope sai, UI có thể mất nhãn hoặc rơi về ngôn ngữ mặc định dù mã locale hoàn toàn hợp lệ.

## 17. An toàn và tính đúng đắn khi đọc tài nguyên

Resource lookup là một hành vi đọc dữ liệu nằm trong đường tìm của loader/module. Khi tạo API lấy resource theo input bên ngoài, cần kiểm soát:

- Không nối trực tiếp một đường dẫn do người dùng nhập vào tên resource rồi xem là an toàn; whitelist tên/bundle nếu có thể.
- Tránh lộ danh sách đường dẫn nội bộ trong thông báo lỗi công khai.
- Dùng tên tài nguyên cố định từ domain/application khi đọc nội dung bắt buộc.
- Đừng tin rằng mọi `.properties` đến từ resource root đều là dữ liệu đã kiểm chứng nếu plugin third-party có quyền đóng góp vào classpath/loader.
- Không dùng tên tài nguyên chung chung dễ trùng giữa dependencies nếu có thể đặt namespace riêng.
- Đóng stream bằng `try-with-resources`, xác định charset (UTF-8 cho văn bản theo contract).
- Với plugin không đáng tin, class loader **không tự là sandbox bảo mật**. Đừng dùng custom loader như cơ chế cô lập quyền truy cập tuyệt đối.
- Với named module, không mở vô điều kiện package chứa dữ liệu nhạy cảm chỉ để tiện tìm resource; áp dụng nguyên tắc tối thiểu quyền trong kiến trúc.

Vấn đề resource path không phải mọi thứ đều quy về `../`: loader/provider có thể xử lý tên khác nhau, vì vậy tốt nhất không thiết kế public endpoint “đọc bất kỳ resource name nào” từ classpath.

## 18. Cách kiểm thử khi đóng gói thay đổi

### 18.1. Test ở cả IDE và artifact thật

Không chỉ chạy unit test với thư mục `src/test/resources`, vì các tài nguyên test thường không có trong JAR production. Với bản release, chạy integration test từ **JAR/module đã đóng gói** và kiểm tra những bundle bắt buộc.

Các test cần có:

- Mỗi resource cần thiết có trong artifact ở đúng entry path.
- `getResourceAsStream` không null khi được gọi từ scope đúng.
- UTF-8 decode đúng thông điệp tiếng Việt và ký tự ngoài ASCII.
- Bundle `vi-VN`, `en-US` và root hoạt động theo nội dung sản phẩm.
- Thiếu key tạo lỗi rõ ràng hoặc fallback đã được định nghĩa.
- Chạy ở môi trường Windows/Linux để không phụ thuộc path separator của hệ điều hành trong resource names.

### 18.2. Test nhiều class loaders

Nếu dùng plugin:

1. Một resource chỉ có trong plugin loader A.
2. Một resource chỉ có trong plugin loader B.
3. Một resource có tên trùng trong parent/child.
4. Một resource vắng mặt.
5. Một plugin loader được đóng/dispose rồi khởi tạo mới.

Kiểm tra API lấy đúng resource theo **scope chủ đích**, không tự trộn. Không giả định `ClassLoader.getSystemClassLoader()` nhìn thấy resource của B khi nó chỉ nằm trong URLClassLoader B.

### 18.3. Test named modules

Trên Java 17, kiểm tra:

- Resource cùng module có đọc được qua `Class.getResourceAsStream` / `Module.getResourceAsStream` đúng path không?
- Module khác truy cập package không được mở có bị từ chối theo dự kiến không?
- `opens` và `exports` có đúng mục tiêu không?
- `ClassLoader.getResource` có tuân yêu cầu unconditional open cho non-class resource không?
- `ResourceBundle.getBundle` có tìm được bundle theo caller module/provider setup không?
- Chuyển từ classpath sang module path có làm thay đổi cache/search hay không?

Không dùng một bộ test classpath để khẳng định JPMS hoạt động đúng mà không kiểm thử module path.

### 18.4. Test fallback và cache

Khi thiếu `Messages_vi_VN.properties` nhưng có `Messages_vi.properties`, xác nhận kết quả chọn bản `vi` đúng với chính sách. Khi thiếu key trong bundle chi tiết, kiểm tra parent/root fallback nếu đó là hành vi mong muốn. Nếu có hot reload, test cache invalidation và vòng đời class loader. **Không xóa cache như bước chữa lỗi mặc định** khi chưa xác nhận scope chính xác.

## 19. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `ClassLoader.getResource("/a/b.txt")` | Tìm sai theo convention loader | Dùng `"a/b.txt"` |
| `SomeClass.class.getResource("file.txt")` nhưng file ở root | Tìm tương đối trong package sai | Dùng `"/file.txt"` hoặc đặt đúng package |
| Dùng `new File("src/main/resources/…")` sau khi deploy | Không còn thư mục source | Đọc stream resource runtime |
| URL JAR entry ép thành `Path` của default FS | Lỗi scheme/path | Dùng `getResourceAsStream` |
| Truyền `ResourceBundle.getBundle("a/b.properties", locale)` | Sai baseName | Dùng `"a.b"` (tên family) |
| File nguồn tồn tại nhưng bị loại khỏi JAR | Production không tìm thấy | Kiểm tra artifact với `jar tf` |
| Dùng application loader cho resource chỉ có trong plugin | `null`/`MissingResourceException` | Truyền plugin loader/anchor phù hợp |
| Dùng TCCL nhưng API không hề đọc TCCL | Đổi context không có tác dụng | Xem contract API và truyền loader rõ |
| Không restore TCCL trong thread pool | Request khác bị ảnh hưởng | `try/finally` khôi phục |
| Đổi `Locale.setDefault` để “tìm” bundle | Không sửa scope, gây tác động chéo | Sửa loader/module/path |
| `exports package` và nghĩ là `opens package` | Resource bị encapsulate | Chọn đúng access theo JPMS |
| Coi `ClassLoader.getResource` là phép tìm xuyên mọi module | Không thấy resource kín | Dùng module-aware API đúng context |
| Hai JAR cùng resource name, tin thứ tự luôn ổn định | Đọc bản ngoài dự kiến | Namespace riêng, kiểm tra `getResources` |
| `ResourceBundle.clearCache` để “thêm” resource mới | Loader vẫn không thấy file | Sửa classpath/loader và artifact |
| Đọc file dịch bằng charset mặc định | Dấu tiếng Việt lỗi trên máy khác | UTF-8 rõ ràng/ResourceBundle đúng JDK |
| Coi `getResource != null` là đã đọc thành công | Stream có thể lỗi khi đọc | Đọc trong `try-with-resources`, xử lý I/O |
| Dùng `ClassLoader` như sandbox plugin | Không đủ cô lập bảo mật | Thiết kế permissions/isolations thực |
| Khẳng định test trong IDE đủ cho JAR/module | Runtime layout khác | Integration test artifact đóng gói |

## 20. Bài tập tự luyện và đáp án

**Bài 1.** Class `com.acme.App` muốn đọc `com/acme/help.txt`. Hai lời gọi nào tương đương nếu chạy trên classpath chuẩn?

**Đáp án:** `App.class.getResource("help.txt")` và `App.class.getResource("/com/acme/help.txt")`. Với class loader, dùng `App.class.getClassLoader().getResource("com/acme/help.txt")`.

**Bài 2.** File `Messages_vi.properties` nằm ở `l10n/` trong JAR. `ResourceBundle.getBundle` cần baseName nào?

**Đáp án:** `"l10n.Messages"`, không phải `"l10n/Messages_vi.properties"`.

**Bài 3.** Loader A và B đều là con của parent P; resource chỉ nằm trong B. Liệu hỏi `A.getResource(name)` có bắt buộc tìm được resource B không?

**Đáp án:** Không. Phạm vi và chiến lược delegation không tự bao gồm sibling loaders.

**Bài 4.** Vì sao `Files.readString(Path.of("src/main/resources/a.txt"))` có thể chạy trong IDE nhưng lỗi ở JAR production?

**Đáp án:** Vì thư mục source không nhất thiết được ship. Resource nên đọc từ runtime classpath/module bằng stream.

**Bài 5.** `ClassLoader.getResource` tìm không thấy một `.properties` trong named module nhưng `SomeClass.class.getResourceAsStream` từ class cùng module đọc được. Có mâu thuẫn không?

**Đáp án:** Không. Hai API có cơ chế/module encapsulation khác nhau; `ClassLoader.getResource` có hạn chế với package không opened unconditionally.

**Bài 6.** Người dùng đổi locale từ `en-US` sang `vi-VN` nhưng loader không thấy bundle `l10n.Messages`. Gọi `Locale.setDefault(viVN)` có sửa được scope loader không?

**Đáp án:** Không. Locale chỉ ảnh hưởng cách chọn candidate/fallback, không làm resource bên ngoài loader trở nên nhìn thấy.

**Bài 7.** `Thread.currentThread().setContextClassLoader(pluginLoader)` có chắc làm `ResourceBundle.getBundle("x.Y", locale)` dùng plugin loader không?

**Đáp án:** Không. Overload này dùng caller context/module theo API; nếu cần plugin loader trong classpath setup, truyền `pluginLoader` rõ bằng overload ba tham số.

**Bài 8.** Hai dependency JAR đều có `config/settings.properties`, nên làm gì nếu kết quả cần xác định?

**Đáp án:** Đặt namespace riêng hoặc thiết kế policy merge/priority rõ. Có thể dùng `getResources` để phát hiện các bản cùng tên; không dựa vô điều kiện vào thứ tự “resource đầu tiên”.

**Bài 9.** Module X `exports x.messages` nhưng không `opens` package này. Resource `x/messages/Messages.properties` có chắc đọc được qua system class loader từ module khác không?

**Đáp án:** Không. `exports` không đồng nghĩa `opens`; resource non-class trong named module chịu encapsulation theo API tìm kiếm.

**Bài 10.** Khi file dịch trong JAR được cập nhật, gọi `ResourceBundle.clearCache(loader)` có luôn đủ không?

**Đáp án:** Không. Phải đảm bảo loader thực sự nhìn thấy artifact mới, JAR đã được reload/đổi đúng cách và module visibility phù hợp; cache chỉ là một phần.

**Bài 11.** Một hàm nhận `Class<?> anchor` rồi gọi `anchor.getResourceAsStream("a.txt")`. Vì sao thay anchor sang class ở package khác có thể đổi kết quả?

**Đáp án:** Vì tên không có slash đầu được giải **tương đối với package của anchor**. Nếu muốn root path cố định, truyền `"/path/a.txt"`.

**Bài 12.** Vì sao nên tránh một tên `messages.properties` chung cho mọi plugin?

**Đáp án:** Nó có thể va chạm giữa classpath entries hoặc loaders khi delegation/namespace không rõ. Đặt bundle theo package/feature riêng như `pluginA.i18n.Messages` sẽ dễ kiểm soát hơn.

## 21. Tổng kết

- **Class loader quyết định phạm vi class/resource nhìn thấy**, không phải chỉ kiểm tra file có tồn tại trên đĩa.
- `Class.getResource("relative")` tìm tương đối package; `Class.getResource("/absolute")` bắt đầu từ root; `ClassLoader.getResource("root/path")` dùng tên **không có slash đầu**.
- Resource trong JAR thường phải đọc qua `InputStream`, không coi nó luôn là `File`/`Path` bình thường.
- **ResourceBundle** có baseName kiểu `package.Name`, locale candidates, fallback và cache; có thể chọn loader/module rõ ràng trong các overload phù hợp.
- **Plugin loader** không tự được application loader hay sibling loader tra cứu. TCCL chỉ có tác dụng khi API/thư viện thực sự dùng nó.
- **Named modules** thêm resource encapsulation. `exports` khác `opens`; `ClassLoader.getResource` và `Module.getResourceAsStream` không có cùng quy tắc visibility.
- Khi deploy, phải kiểm tra **artifact JAR/module thực tế**, path đúng, loader/module scope và cache/fallback; đừng chỉ kiểm tra source folder.
- Dùng UTF-8 cho text theo contract, đóng streams, tránh resource name do input không đáng tin kiểm soát, và không xem class loader là sandbox.
- **Để localization hoạt động đáng tin, chọn đúng cả Locale, bundle name và class loader/module scope.**

### Tài liệu chính thức Java SE 17

- [Class — getResource / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — getResource / getResources / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [ResourceBundle — class loaders, modules, caching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Module — getResourceAsStream / isOpen / isExported](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [URLClassLoader — plugin loader example](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
