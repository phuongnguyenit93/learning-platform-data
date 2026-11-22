# Resource lookup trong modular JAR

## 1. Mục tiêu

JAR có thể chứa class, cấu hình, template, schema, ảnh, file ngôn ngữ và nhiều tài nguyên khác. Ứng dụng thường đọc những tài nguyên này bằng **Class.getResource()**, **ClassLoader.getResource()** hoặc **getResourceAsStream()**.

Khi một JAR được dùng như named module trên module path, resource lookup còn chịu quy tắc encapsulation của Java Platform Module System (JPMS). Một resource có thể nằm trong JAR nhưng vẫn không được module khác nhìn thấy nếu package chứa resource chưa được mở phù hợp. Vì vậy, việc đóng gói đúng file và việc cấp quyền truy cập resource là hai phần riêng biệt cần kiểm tra.

Bài này giải thích cách đặt resource trong modular JAR, khác biệt giữa các API lookup, quy tắc **opens**, cách đọc resource từ module hoặc module layer, và cách chẩn đoán trường hợp resource tồn tại nhưng lookup trả về null.

Sau bài học, bạn có thể:
- Đặt resource đúng đường dẫn trong JAR và kiểm tra nội dung artifact.
- Phân biệt đường dẫn tương đối/tuyệt đối của Class với đường dẫn của ClassLoader.
- Hiểu resource encapsulation trong named module.
- Dùng **opens** hoặc **--add-opens** khi module khác cần đọc resource trong package.
- Chọn API phù hợp khi resource thuộc classpath, module hoặc plugin layer.
- Tránh các lỗi phổ biến liên quan tới duplicate resource, URL của JAR và cache.

## 2. Resource trong JAR và modular JAR

Resource là dữ liệu được đóng gói cùng ứng dụng hoặc thư viện để chương trình đọc khi chạy. Ví dụ:

~~~text
com/example/app/
  Main.class
  config/
    defaults.properties
  templates/
    invoice.html
  schema/
    customer.json
  messages/
    messages_vi.properties
~~~

Một modular JAR còn chứa **module-info.class** ở thư mục gốc của archive:

~~~text
app.jar
  module-info.class
  com/example/app/Main.class
  com/example/app/config/defaults.properties
  com/example/app/templates/invoice.html
~~~

Resource thường được giữ theo package hoặc thư mục tương ứng với thành phần sở hữu nó. Ví dụ, cấu trúc dự án Maven/Gradle có thể là:

~~~text
src/
  main/
    java/
      module-info.java
      com/example/app/Main.java
    resources/
      com/example/app/config/defaults.properties
      com/example/app/templates/invoice.html
~~~

Trong quá trình build, resource từ **src/main/resources** được sao chép vào output directory và sau đó đóng gói vào JAR theo đúng đường dẫn tương đối. Với Gradle, bước xử lý resource thường do task **processResources** thực hiện; với Maven, resource được xử lý trong lifecycle resources. Cấu hình build có thể thay đổi đường dẫn hoặc lọc nội dung, nên hãy kiểm tra artifact cuối cùng.

Lệnh liệt kê nội dung JAR:

~~~bash
jar --list --file app.jar
~~~

Hoặc dạng ngắn tương đương:

~~~bash
jar -tf app.jar
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

**Có file trong source tree không đồng nghĩa file đã được đóng gói.** Resource có thể bị bỏ qua bởi cấu hình build, nằm sai thư mục, bị đổi tên khi filtering hoặc không được đưa vào artifact phát hành. Khi lookup thất bại, hãy kiểm tra JAR thực tế trước khi thay đổi code.

## 3. Quy tắc đặt tên resource

Resource path dùng dấu gạch chéo xuôi **/** để phân tách thư mục, kể cả khi ứng dụng chạy trên Windows. Không dùng dấu gạch chéo ngược trong resource name.

Ví dụ:

~~~text
com/example/app/config/defaults.properties
com/example/app/templates/invoice.html
com/example/app/messages/messages_vi.properties
~~~

Tên resource là đường dẫn bên trong archive, không phải đường dẫn file trên máy. Vì vậy, không truyền đường dẫn như **C:\project\resources\defaults.properties** cho ClassLoader.

Một số nguyên tắc:

- Dùng tên package/path ổn định và nhất quán với module sở hữu resource.
- Phân biệt chữ hoa/chữ thường; JAR và nhiều môi trường chạy xử lý resource path theo đúng tên entry.
- Không thêm ký tự **.** để thay dấu **/** trong resource path.
- Không giả định resource nằm cạnh thư mục làm việc hiện tại.
- Tránh tên resource chung chung như **config.properties** nếu nhiều thư viện có thể đóng gói cùng tên.
- Không đặt thông tin bí mật như password, private key hoặc token vào resource trong JAR; nội dung archive có thể được đọc.

## 4. Class.getResource(): lookup theo class

**Class.getResource(String name)** tìm resource gắn với class cụ thể. Quy tắc đường dẫn của API này có hai dạng.

**Tên tương đối:** nếu name không bắt đầu bằng dấu **/**, đường dẫn được tính tương đối với package của class.

~~~java
package com.example.app;

public class Main {
    public void loadDefaults() {
        var url = Main.class.getResource("config/defaults.properties");
        System.out.println(url);
    }
}
~~~

Với class **com.example.app.Main**, đường dẫn được tìm là:

~~~text
com/example/app/config/defaults.properties
~~~

**Tên tuyệt đối:** nếu name bắt đầu bằng **/**, dấu gạch chéo đầu tiên được bỏ đi và phần còn lại được tính từ gốc resource của module/JAR.

~~~java
var url = Main.class.getResource(
    "/com/example/app/config/defaults.properties"
);
~~~

Hai cách trên trỏ tới cùng resource trong ví dụ.

Có thể đọc trực tiếp thành InputStream:

~~~java
try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy defaults.properties");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

**Class.getResource()** thường phù hợp khi resource thuộc về chính class hoặc package của class. Nó giúp code tránh phụ thuộc vào thread context class loader và làm rõ thành phần sở hữu resource.

Lưu ý: **getResource()** trả về **null** khi không tìm thấy hoặc khi resource không được phép truy cập theo quy tắc encapsulation của module. Hãy kiểm tra cả đường dẫn lẫn module access.

## 5. ClassLoader.getResource(): lookup từ gốc class loader

**ClassLoader.getResource(String name)** luôn nhận tên resource tính từ gốc, không có dấu **/** ở đầu.

~~~java
ClassLoader loader = Main.class.getClassLoader();

var url = loader.getResource(
    "com/example/app/config/defaults.properties"
);
~~~

Nếu dùng tên có dấu **/**:

~~~java
loader.getResource(
    "/com/example/app/config/defaults.properties"
);
~~~

thì thông thường lookup không tìm thấy entry vì ClassLoader không loại bỏ dấu gạch chéo đầu tiên như **Class.getResource()**.

Đọc bằng stream:

~~~java
try (var input = loader.getResourceAsStream(
        "com/example/app/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource không tồn tại hoặc không truy cập được");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

Một số API ClassLoader thường dùng:

- **getResource(name)**: trả về URL của resource đầu tiên được tìm thấy.
- **getResources(name)**: trả về Enumeration gồm các resource cùng tên mà loader tìm được.
- **getResourceAsStream(name)**: mở resource thành InputStream; trả về null nếu không tìm thấy hoặc không truy cập được.

ClassLoader phù hợp khi ứng dụng cần tra cứu resource từ một loader cụ thể, đặc biệt trong framework, application server hoặc hệ thống plugin. Tuy nhiên, cần nhớ context class loader của thread có thể khác với defining class loader của class hiện tại.

## 6. So sánh Class và ClassLoader

| Tiêu chí | Class.getResource(name) | ClassLoader.getResource(name) |
|---|---|---|
| Đường dẫn tương đối | Tính từ package của class | Không có khái niệm tương đối theo package |
| Đường dẫn tuyệt đối | Bắt đầu bằng **/** | Không bắt đầu bằng **/** |
| Ví dụ | **Main.class.getResource("config/app.properties")** | **loader.getResource("com/example/config/app.properties")** |
| Resource sở hữu bởi | Class/module chứa class | Class loader được chọn |
| Khi phù hợp | Resource thuộc một class hoặc package cụ thể | Lookup theo loader, framework hoặc plugin |
| Kết quả | URL hoặc null | URL hoặc null |

Một lỗi phổ biến là chuyển code từ Class sang ClassLoader nhưng giữ nguyên dấu **/** đầu path. Hãy điều chỉnh đường dẫn theo API đang dùng.

Nếu code chạy trong môi trường có nhiều class loader, không nên tùy tiện dùng **ClassLoader.getSystemClassLoader()**. System loader có thể không nhìn thấy resource của plugin hoặc application server. Hãy chọn loader được kiến trúc ứng dụng quy định.

## 7. Resource encapsulation trong named module

Trên classpath, resource thường được tìm thông qua class loader và có thể được nhiều thành phần nhìn thấy theo thứ tự tìm kiếm của loader.

Trong named module, resource nằm trong package của module chịu quy tắc encapsulation. **Resource không phải class** trong package của named module chỉ được module khác truy cập nếu package đó được mở cho module gọi. Một resource có thể tồn tại trong modular JAR nhưng lookup từ module khác vẫn trả về null vì package chưa được mở.

Ví dụ module nguồn:

~~~java
module com.example.settings {
    exports com.example.settings.api;
}
~~~

Resource:

~~~text
com/example/settings/config/defaults.properties
~~~

Module consumer có thể đọc public API của **com.example.settings.api** nhưng chưa chắc đọc được resource trong package **com.example.settings.config**. Directive **exports** không mở package cho deep reflection hoặc resource access.

Nếu module khác cần đọc resource trong package config, module nguồn có thể khai báo qualified open:

~~~java
module com.example.settings {
    exports com.example.settings.api;

    opens com.example.settings.config
        to com.example.settings.reader;
}
~~~

Trong ví dụ này, package **com.example.settings.config** được mở cho module **com.example.settings.reader**. Module consumer vẫn cần đọc module nguồn, thường bằng **requires**:

~~~java
module com.example.settings.reader {
    requires com.example.settings;
}
~~~

Nếu cần cho mọi module đọc resource trong package, có thể dùng unqualified open:

~~~java
opens com.example.settings.config;
~~~

Hoặc mở tất cả package của module:

~~~java
open module com.example.settings {
    exports com.example.settings.api;
}
~~~

**open module** cho phép deep reflection vào các package ở runtime; nó không tự động export tất cả package cho truy cập code thông thường.

## 8. Dùng opens hay exports?

Chọn directive theo loại truy cập:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Consumer import và gọi public class trong package | **exports p** hoặc **exports p to m** |
| Framework đọc resource không phải class trong package của named module | **opens p** hoặc **opens p to m** |
| Framework dùng reflection sâu vào private field/constructor | **opens p** hoặc **opens p to m** |
| Chỉ cần cấp quyền mở ở runtime mà không sửa module descriptor | **--add-opens** |
| Cấp export tạm thời cho public API ở runtime/compile time | **--add-exports** |

Ví dụ, nếu module **com.example.settings.reader** chỉ cần đọc file properties trong package config, không cần export package đó cho code import class. Có thể dùng:

~~~java
opens com.example.settings.config
    to com.example.settings.reader;
~~~

Nếu consumer vừa cần gọi public type trong package đó vừa cần đọc resource, có thể khai báo cả **exports** và **opens**. Tuy nhiên, chỉ cấp đúng quyền mà integration thực sự cần.

Nếu consumer chạy trong unnamed module trên classpath, có thể mở package ở runtime bằng:

~~~bash
java --add-opens com.example.settings/com.example.settings.config=ALL-UNNAMED -cp app.jar com.example.Main
~~~

**ALL-UNNAMED** áp dụng cho các unnamed module trong tiến trình. Đây là phạm vi rộng hơn một qualified open tới named module cụ thể.

## 9. Module.getResourceAsStream(): đọc resource từ module cụ thể

Khi đã có đối tượng **Module**, có thể đọc resource trực tiếp từ module đó:

~~~java
Module module = Main.class.getModule();

try (var input = module.getResourceAsStream(
        "com/example/app/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy resource trong module");
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
~~~

Tên resource truyền cho **Module.getResourceAsStream()** là path phân tách bằng **/** và không dùng dấu **/** đầu như dạng absolute của Class.getResource().

API này hữu ích khi code muốn chỉ rõ resource thuộc module nào thay vì để class loader tìm trong một tập resource rộng hơn. Nó cũng tuân theo encapsulation: nếu resource nằm trong package của named module và package không mở cho module gọi, phương thức có thể trả về null.

Nếu resource được đọc bởi code ngay trong module sở hữu nó, module có thể truy cập resource nội bộ của mình theo quy tắc của API. Nếu module khác cần đọc, hãy mở package cho module đó.

## 10. ModuleReader: đọc nội dung module ở mức thấp

**ModuleReader** là API cấp thấp dùng để đọc nội dung của một module. Nó thường hữu ích cho công cụ module, custom class loader hoặc hệ thống cần duyệt resource của một module cụ thể.

Có thể tìm module bằng **ModuleFinder** và mở **ModuleReference**:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

ModuleReference reference = finder.find("com.example.settings")
    .orElseThrow();

try (ModuleReader reader = reference.open()) {
    var resource = reader.open(
        "com/example/settings/config/defaults.properties"
    );

    if (resource.isEmpty()) {
        throw new IllegalStateException("Resource không có trong module");
    }

    try (var input = resource.get()) {
        byte[] bytes = input.readAllBytes();
        System.out.println(bytes.length);
    }
}
~~~

Các API liên quan:

- **ModuleFinder** tìm module từ module path hoặc nguồn module khác.
- **ModuleReference** đại diện cho một module có thể được đọc.
- **ModuleReader.open(name)** mở resource thành InputStream nếu tìm thấy.
- **ModuleReader.read(name)** có thể trả về ByteBuffer.
- **ModuleReader.find(name)** tìm URI của resource.
- **ModuleReader.list()** liệt kê tên resource trong module.
- **close()** đóng reader và giải phóng resource liên quan.

Hãy đóng ModuleReader và InputStream bằng try-with-resources. Nếu dùng **read(name)** để nhận ByteBuffer, hãy gọi **release(buffer)** theo hợp đồng của ModuleReader sau khi không còn sử dụng buffer.

ModuleReader là công cụ cho thao tác module ở mức thấp. Với code ứng dụng thông thường chỉ cần đọc một file cấu hình, **Class.getResourceAsStream()** hoặc **Module.getResourceAsStream()** thường đơn giản hơn. ModuleReader cũng không phải một cơ chế để bỏ qua các chính sách truy cập của ứng dụng; hãy chỉ dùng nó trong thành phần có trách nhiệm quản lý module content và class loading.

## 11. Resource lookup trong plugin và module layer

Plugin có thể nằm trong một modular JAR riêng và được nạp vào **ModuleLayer**. Khi đó, resource của plugin thuộc module/plugin layer tương ứng.

Nếu code đã có class của plugin, cách đơn giản nhất thường là lấy resource qua class đó:

~~~java
try (var input = PluginImplementation.class.getResourceAsStream(
        "config/plugin-defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Plugin thiếu resource mặc định");
    }

    // Đọc cấu hình plugin.
}
~~~

Cách này gắn resource với module sở hữu implementation và tránh phải đoán class loader.

Nếu cần tìm resource theo module layer, hãy xác định module/plugin cụ thể rồi dùng API module hoặc ModuleReader phù hợp. Không giả định **ClassLoader.getSystemClassLoader()** có thể nhìn thấy mọi resource của module layer tùy chỉnh.

Khi dùng ServiceLoader cho plugin, provider và resource vẫn là hai việc riêng:
- **ServiceLoader** tìm implementation của service theo module descriptor hoặc provider configuration.
- Resource lookup tìm dữ liệu đi kèm implementation.
- Việc tìm thấy provider không tự mở mọi package resource của module plugin cho ứng dụng.

Nếu plugin cần cung cấp cấu hình cho host, hãy thiết kế API rõ ràng: plugin có thể tự đọc resource nội bộ rồi trả cấu hình qua interface, hoặc mở package resource cụ thể cho module host. Cách plugin tự đọc resource thường giúp giảm bề mặt package phải mở.

## 12. Resource trên classpath và module path

| Đặc điểm | Classpath | Module path |
|---|---|---|
| Cách tổ chức | JAR/thư mục trong unnamed module | Named module hoặc automatic module |
| Lookup phổ biến | ClassLoader/Class | Class/ClassLoader/Module |
| Encapsulation theo package | Không áp dụng JPMS như named module | Resource trong package chịu quy tắc encapsulation |
| Mở package | Không có module-info để khai báo opens cho unnamed module | Dùng opens/open module hoặc --add-opens |
| Xác định chủ sở hữu | Thường dựa vào loader và resource path | Có thể xác định rõ module sở hữu |
| Duplicate resource | Loader có thể trả entry đầu tiên theo thứ tự tìm kiếm | Nên xác định module cụ thể để tránh nhập nhằng |

Một modular JAR khi đặt trên classpath được xử lý như JAR thông thường trong unnamed module; module descriptor không được dùng để tạo named module. Khi đặt trên module path, module descriptor được dùng để phân giải module và các quy tắc encapsulation có hiệu lực.

Vì vậy, cùng một JAR có thể cho kết quả resource lookup khác nhau tùy cách chạy. Nếu ứng dụng hoạt động trên classpath nhưng trả null khi chuyển sang module path, hãy kiểm tra package chứa resource có được mở cho module gọi hay không.

## 13. Duplicate resource và thứ tự tìm kiếm

Nhiều JAR có thể chứa resource cùng tên, ví dụ:

~~~text
config/defaults.properties
~~~

Trên classpath, **ClassLoader.getResource(name)** trả về một resource được tìm thấy đầu tiên theo cơ chế tìm kiếm của loader. Nếu nhiều thư viện đóng gói cùng tên, kết quả có thể phụ thuộc thứ tự classpath hoặc parent delegation.

Dùng **getResources(name)** khi cần liệt kê mọi resource cùng tên:

~~~java
Enumeration<URL> resources =
    Thread.currentThread()
        .getContextClassLoader()
        .getResources("config/defaults.properties");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
~~~

Không giả định thứ tự kết quả là một hợp đồng ưu tiên cấu hình trừ khi loader/ứng dụng của bạn quy định rõ. Nếu có nhiều file cấu hình cần hợp nhất, hãy định nghĩa thứ tự và quy tắc merge trong ứng dụng.

Trong modular application, nếu cần resource của một module cụ thể, dùng class/module sở hữu resource thay vì lookup toàn cục qua system loader. Cách này giảm nguy cơ đọc nhầm file cùng tên từ dependency khác.

## 14. URL của resource không nhất thiết là file trên ổ đĩa

Một resource trong thư mục output khi chạy IDE có thể có URL dạng **file:**. Nhưng khi đóng gói trong JAR, URL thường có dạng **jar:** hoặc một dạng URL do class loader cung cấp.

Ví dụ minh họa:

~~~text
file:/app/classes/com/example/config/defaults.properties
jar:file:/app/lib/app.jar!/com/example/config/defaults.properties
~~~

Không nên làm như sau:

~~~java
File file = new File(
    Main.class.getResource("config/defaults.properties").getFile()
);
~~~

Cách trên có thể hoạt động khi resource nằm trong thư mục file nhưng thất bại khi resource ở bên trong JAR. URL của JAR không phải đường dẫn file thông thường.

Hãy đọc resource bằng stream:

~~~java
try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy resource");
    }

    // Xử lý dữ liệu từ input.
}
~~~

Nếu thực sự cần thao tác với URL, dùng **toURI()** và xử lý scheme phù hợp. Với URL dạng **jar:**, có thể cần **JarURLConnection** hoặc API FileSystem cho JAR. Không ép mọi URL thành **Path** bằng cách giả định scheme luôn là file.

## 15. Encoding và cách đọc nội dung

Resource dạng text cần chỉ định encoding rõ ràng. **Properties.load(InputStream)** sử dụng quy tắc ISO-8859-1 cho dạng properties truyền thống, trong khi file UTF-8 có thể được đọc bằng **Reader**.

Ví dụ đọc properties UTF-8:

~~~java
Properties properties = new Properties();

try (var input = Main.class.getResourceAsStream(
        "config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy defaults.properties");
    }

    try (var reader = new java.io.InputStreamReader(
            input,
            java.nio.charset.StandardCharsets.UTF_8)) {
        properties.load(reader);
    }
}
~~~

Với JSON, XML hoặc template, cũng nên chỉ định UTF-8:

~~~java
try (var input = Main.class.getResourceAsStream(
        "schema/customer.json")) {
    if (input == null) {
        throw new IllegalStateException("Không tìm thấy schema");
    }

    String json = new String(
        input.readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
    );
}
~~~

Nếu resource lớn, tránh đọc toàn bộ vào byte array hoặc String khi không cần. Dùng stream và parser có khả năng xử lý dữ liệu tuần tự để giảm bộ nhớ.

## 16. Hiệu năng và cache

Resource lookup thường rẻ hơn việc đọc và parse lại nội dung nhiều lần, nhưng chi phí thực tế phụ thuộc class loader, JAR, filesystem và cách xử lý dữ liệu.

Một số nguyên tắc:

1. **Không lookup và parse lặp lại trong hot path:** đọc cấu hình một lần khi khởi tạo component nếu nội dung không thay đổi.
2. **Cache dữ liệu đã parse khi phù hợp:** cache Properties/metadata đã đọc thay vì giữ InputStream mở.
3. **Luôn đóng stream:** không giữ file handle hoặc JAR connection lâu hơn cần thiết.
4. **Chọn loader ổn định:** tránh tra cứu qua context class loader nếu ứng dụng không kiểm soát thread context.
5. **Chú ý vòng đời plugin:** cache Class, URL, resource hoặc object từ plugin có thể giữ class loader/module layer sống lâu hơn dự kiến.
6. **Xử lý reload rõ ràng:** nếu hỗ trợ reload cấu hình, xác định thời điểm cache hết hiệu lực và tránh dùng dữ liệu cũ.
7. **Đo trước khi tối ưu:** không tạo cache phức tạp cho resource nhỏ nếu lookup không nằm trên đường thực thi quan trọng.

Nếu mở URL connection trực tiếp và cần thay resource trong lúc chạy hoặc tránh giữ cache URLConnection, có thể cấu hình **setUseCaches(false)** trước khi mở stream. Hành vi cache phụ thuộc URL handler; hãy kiểm tra trên môi trường triển khai thực tế.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| **getResource() trả null** | Sai path, resource không được đóng gói hoặc bị encapsulate | Kiểm tra JAR và package opens |
| Class.getResource tìm được nhưng ClassLoader.getResource không tìm được | Dùng path tương đối theo package hoặc có dấu / đầu path | Chuyển sang path root-relative, bỏ dấu / |
| Chạy classpath được nhưng module path trả null | Package chứa resource chưa mở cho module gọi | Thêm opens có phạm vi hẹp |
| **FileNotFoundException** khi chuyển URL sang File | Resource nằm trong JAR, URL không phải file path | Dùng getResourceAsStream hoặc xử lý jar URI |
| Đọc nhầm cấu hình | Nhiều JAR có resource cùng tên | Dùng class/module sở hữu resource hoặc getResources để kiểm tra |
| Resource không có trong artifact | Build tool không copy resource hoặc path source sai | Kiểm tra src/main/resources, output và jar --list |
| Resource tiếng Việt bị lỗi ký tự | Đọc bằng encoding không phù hợp | Dùng Reader và StandardCharsets.UTF_8 |
| JAR bị khóa hoặc không reload được | URLConnection/JAR cache hoặc stream chưa đóng | Đóng stream, xem xét setUseCaches(false) và thiết kế reload |
| Plugin không tìm được resource | Dùng system loader thay vì loader/module layer của plugin | Lookup qua class plugin hoặc module layer tương ứng |

Quy trình điều tra:

1. Ghi lại resource path chính xác và API lookup đang dùng.
2. Xác định path đó là tương đối theo class hay root-relative theo class loader.
3. Dùng **jar --list --file app.jar** xác nhận entry có trong artifact.
4. Xác định class/module sở hữu resource và module gọi lookup.
5. Nếu resource thuộc package của named module, kiểm tra **opens** tới module gọi.
6. Nếu dùng plugin, kiểm tra class loader, module layer và module graph.
7. Đóng gói lại và chạy trên đúng môi trường module path như production.

## 18. Bảo mật khi đọc resource

Resource trong JAR không phải vùng lưu trữ bí mật. Bất kỳ ai có artifact đều có thể giải nén và đọc nội dung resource. Không đặt secret, credential, private key hoặc dữ liệu người dùng nhạy cảm vào file cấu hình đóng gói.

Nếu resource path đến từ input bên ngoài, không nối trực tiếp path tùy ý vào một thư mục hoặc file hệ thống. Hãy xác thực tên resource theo allowlist và tránh path traversal như **../** khi ứng dụng chuyển resource name thành đường dẫn filesystem.

Khi đọc resource từ plugin, hãy xem nội dung như dữ liệu do plugin cung cấp. Chữ ký JAR có thể giúp xác định nguồn ký và tính toàn vẹn theo trust policy, nhưng không chứng minh resource hoặc code là an toàn.

**opens** kiểm soát khả năng truy cập package theo module; nó không mã hóa resource, không xác thực người dùng và không tạo sandbox. Chỉ mở package cho module cần thiết và không dùng open module rộng nếu ứng dụng chỉ cần một resource nhỏ.

## 19. Tự kiểm tra

**1. Vì sao Class.getResource("config/app.properties") và ClassLoader.getResource("config/app.properties") có thể tìm hai đường dẫn khác nhau?**

Vì Class tính path tương đối theo package của class nếu tên không bắt đầu bằng dấu /, còn ClassLoader luôn tìm từ gốc resource path.

**2. Resource có trong modular JAR nhưng ClassLoader.getResource() từ module khác trả null. Nguyên nhân có thể là gì?**

Resource nằm trong package của named module chưa được mở cho module gọi. Hãy kiểm tra directive opens hoặc cấu hình --add-opens.

**3. exports package có đủ để module khác đọc resource trong package không?**

Không nhất thiết. Exports dành cho public API; resource và deep reflection cần package được mở theo quy tắc JPMS.

**4. Vì sao không nên chuyển URL của resource trực tiếp thành File?**

Vì resource có thể nằm bên trong JAR và URL có scheme jar:, không phải file path thông thường. Dùng InputStream hoặc xử lý URL/URI theo scheme.

**5. Khi nào nên dùng ModuleReader?**

Khi cần đọc hoặc liệt kê nội dung của module ở mức thấp, chẳng hạn trong custom class loader hoặc công cụ module. Với ứng dụng thông thường, Class hoặc Module resource API đơn giản hơn.

**6. Vì sao resource lookup của plugin nên gắn với class/module plugin?**

Vì system class loader có thể không nhìn thấy plugin layer. Lookup qua class/module sở hữu resource giúp xác định đúng module và tránh nhầm resource cùng tên.

## 20. Ghi nhớ

Resource trong modular JAR được tìm bằng các API quen thuộc của Java, nhưng named module bổ sung quy tắc encapsulation. **Class.getResource()** hỗ trợ path tương đối theo package hoặc tuyệt đối từ gốc; **ClassLoader.getResource()** luôn nhận path từ gốc; **Module.getResourceAsStream()** đọc resource từ module cụ thể; **ModuleReader** phục vụ thao tác module ở mức thấp.

Nếu module khác cần đọc resource nằm trong package của named module, hãy mở package bằng **opens** hoặc **--add-opens** cho đúng module gọi. Luôn kiểm tra artifact thực tế, đóng stream, xử lý URL theo scheme, quản lý duplicate resource và không xem resource trong JAR là dữ liệu bí mật.

## Tài liệu tham khảo

- [Class — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [ModuleReader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleReader.html)
- [ModuleFinder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The Java Module System — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
