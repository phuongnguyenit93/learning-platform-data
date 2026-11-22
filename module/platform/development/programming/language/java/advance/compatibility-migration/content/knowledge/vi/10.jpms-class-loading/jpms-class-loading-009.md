# Nạp tài nguyên theo class loader và khả năng nhìn thấy giữa module

Trong Java, tìm được một lớp và tìm được một tài nguyên đi kèm lớp đó là hai việc có liên quan nhưng không giống nhau. Trước Java 9, nhiều ứng dụng đặt file cấu hình, template, ảnh, schema hoặc resource bundle trong JAR rồi dùng `ClassLoader.getResourceAsStream()` để đọc. Khi chuyển sang Java Platform Module System (JPMS), tài nguyên vẫn nằm trong JAR nhưng khả năng truy cập có thể thay đổi theo **module sở hữu tài nguyên**, **package chứa tài nguyên**, **API được dùng để tìm**, và **class loader thực hiện tra cứu**.

Một dự án nâng JDK hoặc chuyển thư viện từ classpath sang module path có thể gặp tình huống: class vẫn được nạp bình thường, ứng dụng vẫn khởi động, nhưng một file `.properties` hoặc `.xml` bỗng trả về `null` khi đọc. Bài học này giải thích cách Java tìm tài nguyên, cách JPMS giới hạn khả năng nhìn thấy, các lỗi thường gặp và phương pháp kiểm thử khi migration.

## 1. Phân biệt class, classpath resource và tài nguyên của module

**Class** là kiểu Java được định danh bởi binary name và defining class loader. **Resource** là dữ liệu được đặt trong classpath, module hoặc một nguồn mà class loader có thể cung cấp; resource thường được xác định bằng chuỗi đường dẫn phân tách bằng dấu `/`.

Ví dụ một JAR có cấu trúc:

~~~text
com/acme/order/OrderService.class
com/acme/order/defaults.properties
com/acme/order/templates/receipt.txt
config/application.properties
META-INF/services/com.acme.spi.Codec
~~~

Một số tài nguyên có thể được tìm theo tên:

~~~text
com/acme/order/defaults.properties
com/acme/order/templates/receipt.txt
config/application.properties
~~~

Tên resource trong API nạp tài nguyên thường dùng dấu `/` ngay cả khi đang chạy trên Windows. Nó không phải đường dẫn file hệ điều hành và không cần tồn tại dưới dạng file vật lý tách rời. Tài nguyên có thể ở trong JAR, runtime image hoặc một kho được custom class loader cung cấp.

Sự khác biệt quan trọng:

- **Tìm class:** thường dựa vào binary name, cơ chế phân giải lớp và class loader.
- **Tìm resource:** dựa vào resource name, quy tắc của phương thức tra cứu, thứ tự loader, module và quy tắc encapsulation.
- **Đọc resource:** nhận một `URL` hoặc `InputStream`; đọc được hay không còn phụ thuộc cách xử lý stream, encoding và lỗi I/O.
- **Tìm thấy một class không bảo đảm tìm thấy resource cùng package.** JPMS có chính sách bảo vệ tài nguyên trong package của named module.

Khi khảo sát một lỗi migration, hãy hỏi trước: resource được đóng gói ở đâu, thuộc module nào, và được truy cập bằng API nào?

## 2. Cách đặt tên resource khi dùng Class và ClassLoader

Hai API thường gặp có quy tắc tên khác nhau:

~~~java
Class<?> owner = com.acme.order.OrderService.class;

// Tương đối với package com.acme.order:
URL samePackage = owner.getResource("defaults.properties");

// Tuyệt đối từ gốc vùng tìm kiếm của Class:
URL absolute = owner.getResource("/config/application.properties");

// Tìm từ gốc của class loader; không thêm dấu / ở đầu:
ClassLoader loader = owner.getClassLoader();
URL byLoader = loader.getResource("com/acme/order/defaults.properties");
~~~

### 2.1. Class.getResource / Class.getResourceAsStream

Với `SomeClass.class.getResource("name.txt")`, chuỗi không bắt đầu bằng `/` sẽ được ghép tương đối với package của `SomeClass`.

Với `SomeClass.class.getResource("/config/name.txt")`, dấu `/` đầu tiên chỉ rằng tên tài nguyên được hiểu là tuyệt đối; dấu `/` này được loại bỏ khi tạo tên để tra cứu. Đây **không** phải đường dẫn tuyệt đối tới filesystem.

Ví dụ:

~~~java
package com.acme.order;

public final class OrderService {
    public static InputStream openDefaults() {
        return OrderService.class
                .getResourceAsStream("defaults.properties");
    }
}
~~~

Lời gọi trên tìm tên logic `com/acme/order/defaults.properties`, không phải `defaults.properties` ở gốc JAR.

Ưu điểm của `Class.getResourceAsStream` là resource được gắn với class làm mốc. Khi class chuyển package hoặc được chuyển sang module khác, vị trí resource cần được xem lại tương ứng.

### 2.2. ClassLoader.getResource / getResourceAsStream

Với `ClassLoader`, tên được chỉ định **tương đối với gốc** không gian resource mà loader tìm kiếm. Đừng dùng dấu `/` mở đầu:

~~~java
ClassLoader loader = OrderService.class.getClassLoader();

try (InputStream in = loader.getResourceAsStream(
        "com/acme/order/defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Không tìm thấy defaults.properties");
    }
    // Đọc nội dung từ in.
}
~~~

Một lỗi thường gặp là viết `loader.getResourceAsStream("/com/acme/order/defaults.properties")` vì suy luận theo quy tắc của `Class.getResourceAsStream`. Cách viết đó không tuân theo contract chuẩn của `ClassLoader.getResource` và có thể trả về `null`.

### 2.3. Class loader bootstrap có thể được biểu diễn bằng null

`SomeClass.class.getClassLoader()` có thể trả về `null` với lớp được định nghĩa bởi bootstrap loader. Không nên gọi ngay `getResource` trên kết quả mà không xét tình huống này.

Nếu muốn đọc resource gắn với một lớp cụ thể, `SomeClass.class.getResourceAsStream(...)` thường là cách đơn giản hơn. Nếu cần một loader do ứng dụng quyết định, phải ghi rõ loader nào được chọn và vì sao.

## 3. Ba môi trường cần phân biệt: classpath, module path và module layer

Java có thể chạy mã theo nhiều cách:

1. **Classpath / unnamed module:** các class từ classpath thuộc unnamed module của defining loader. Đây là mô hình truyền thống, thường gặp ở các ứng dụng chưa modularize.
2. **Named module trên module path:** module có tên và có thể có `module-info.class`, với ranh giới package, exports, opens và quan hệ đọc module.
3. **Custom module layer / class loader:** ứng dụng plugin hoặc container có thể tạo layer và class loader riêng, khiến resource visibility và thứ tự lookup khác môi trường classpath đơn giản.

Một module tự nó không đồng nghĩa một class loader riêng. Nhiều module có thể được định nghĩa bởi cùng loader, và nhiều module layer có thể dùng loader khác nhau. Vì vậy, chỉ nhìn tên module không đủ để biết resource sẽ được tìm theo đường nào.

Mẫu sơ đồ khái niệm:

~~~text
Ứng dụng
   |
   +-- Classpath -> unnamed module của loader
   |
   +-- Module path -> named modules
   |                     |
   |                     +-- exports: API của type
   |                     +-- opens: truy cập phản chiếu và một số resource
   |
   +-- Plugin layer -> các module và loader riêng
                         |
                         +-- ranh giới visibility khác
~~~

Khi migration, một JAR chuyển từ classpath sang module path có thể vẫn chứa đúng resource cũ, nhưng cơ chế encapsulation sẽ thay đổi vì nó nay thuộc một named module.

## 4. Exports, opens và quyền truy cập tài nguyên

JPMS đưa ra hai nhóm khai báo dễ bị nhầm:

- `exports com.acme.lib.api;`: cho phép các module có quan hệ đọc thích hợp truy cập các public type trong package được export.
- `opens com.acme.lib.internal;`: mở package cho deep reflection tại runtime, đồng thời có ý nghĩa đối với truy cập resource nằm trong package của named module.
- `opens com.acme.lib.internal to com.acme.app;`: mở có điều kiện cho module đích được nêu.
- `open module com.acme.lib { ... }`: các package trong module được mở theo cơ chế open module.

**Exports không đồng nghĩa opens.** Một package được export không nhất thiết cho phép các API loader công khai liệt kê hoặc lấy mọi resource bên trong package đó.

Ví dụ:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.app;
}
~~~

Ở đây, `com.acme.catalog.api` được export để module khác sử dụng các public type. Package `com.acme.catalog.internal` chỉ được mở cho `com.acme.app`, không phải tự động mở công khai cho mọi module hoặc mọi lời gọi `ClassLoader.getResource`.

### 4.1. Truy cập tài nguyên bằng Module.getResourceAsStream

Từ Java 9, có thể truy cập tài nguyên của một module xác định thông qua `Module.getResourceAsStream(String)`:

~~~java
Module catalogModule = CatalogApi.class.getModule();

try (InputStream in = catalogModule.getResourceAsStream(
        "com/acme/catalog/internal/defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Không truy cập được resource");
    }
    // Đọc resource.
}
~~~

`CatalogApi` là một public type được phép tham chiếu từ code gọi trong ví dụ. Tên truyền vào `Module.getResourceAsStream` là tên resource theo `/` và không có dấu `/` ở đầu.

Với resource nằm trong một package của **named module**, quy tắc truy cập phụ thuộc vào package có được mở tới **module của caller** hay không; code bên trong cùng module được phép truy cập resource của chính module đó. Nếu package được mở có điều kiện bằng `opens ... to ...`, module gọi phải nằm trong tập được cho phép.

Một resource không thuộc package của module có thể được xử lý khác với resource ở package bị encapsulate. Không nên suy đoán chỉ theo phần mở rộng `.properties`: vị trí trong package và API truy cập mới là yếu tố quan trọng.

`Module.getResourceAsStream` có thể ném `IOException` khi có lỗi đọc; trả `null` nếu không tìm thấy hoặc không thể truy cập theo hợp đồng của API. Cần phân biệt hai tình huống này trong chẩn đoán.

### 4.2. Hạn chế riêng của ClassLoader.getResource trong named module

Khi dùng `ClassLoader.getResource` hoặc `getResources` để tìm **resource không phải class file** nằm trong một package của named module, các quy tắc encapsulation của JPMS áp dụng. Đối với nhóm API này, resource trong package của named module thường chỉ được tìm thấy khi package đó **được mở vô điều kiện** (unconditionally opened). Việc `opens p to some.module` có điều kiện không tự làm resource được công khai qua `ClassLoader.getResource`.

Đây là lý do một số ứng dụng thấy:

~~~java
Module target = SomeApi.class.getModule();

// Lookup có chủ đích theo module và quyền của caller:
InputStream a = target.getResourceAsStream(
        "com/acme/secret/config.xml");

// Lookup theo loader có thể không nhìn thấy cùng resource:
InputStream b = SomeApi.class.getClassLoader()
        .getResourceAsStream("com/acme/secret/config.xml");
~~~

Kết quả `a` và `b` không bắt buộc giống nhau. API đầu biết chính xác module đích và kiểm tra khả năng truy cập theo quan hệ module. API sau tra cứu theo loader, trong đó resource bị encapsulate có thể bị ẩn.

**Ngoại lệ cần nhớ:** tài nguyên mang tên kết thúc bằng `.class` được đối xử đặc biệt trong một số quy tắc tra cứu tài nguyên của class loader. Không dùng trường hợp ngoại lệ cho class file làm bằng chứng rằng resource cấu hình trong cùng package cũng công khai.

### 4.3. Bảng tổng hợp theo cách tra cứu

| Cách truy cập | Cách xác định tên | Điểm cần lưu ý |
|---|---|---|
| `SomeClass.class.getResource("x.txt")` | Tương đối package của `SomeClass` | Mốc là class; hành vi trong named module cần xét module/package |
| `SomeClass.class.getResource("/p/x.txt")` | Tên tuyệt đối sau khi bỏ `/` đầu | Không phải filesystem path |
| `loader.getResource("p/x.txt")` | Từ gốc không gian resource của loader | Có hạn chế đặc biệt với resource trong package của named module |
| `loader.getResources("p/x.txt")` | Tra cứu nhiều URL có cùng tên | Không bảo đảm tìm thấy resource bị encapsulate; tránh giả định thứ tự |
| `module.getResourceAsStream("p/x.txt")` | Theo module được chỉ định | Áp dụng quy tắc `opens` đối với module gọi |
| `Thread.currentThread().getContextClassLoader()` rồi `getResource` | Theo context loader | Không nhất thiết là loader của class hiện tại |

Bảng dùng để chọn API tra cứu phù hợp; nó không thay thế việc xác định module path, class loader và quyền opens của hệ thống cụ thể.

## 5. Vì sao Class.getResource và ClassLoader.getResource có thể cho kết quả khác?

Trong môi trường classpath đơn giản, hai cách có thể cùng tìm thấy resource sau khi đã đổi tên tương đối/tuyệt đối cho đúng. Với JPMS, `Class.getResource` sử dụng class làm mốc trong ngữ cảnh module của class đó, trong khi `ClassLoader.getResource` là tra cứu theo loader và áp dụng quy tắc encapsulation dành cho loader.

Do đó không nên tự ý thay:

~~~java
InputStream in = MyComponent.class.getResourceAsStream("rules.json");
~~~

bằng:

~~~java
InputStream in = MyComponent.class.getClassLoader()
        .getResourceAsStream("com/acme/component/rules.json");
~~~

rồi coi là refactor chắc chắn tương đương. Bên cạnh khác biệt mốc đường dẫn, ranh giới module và cách đọc resource có thể làm kết quả khác nhau.

Khi mã nằm trong module sở hữu resource, dùng `Class.getResourceAsStream` theo mốc class hoặc `Module.getResourceAsStream` là lựa chọn rõ ý định. Khi mã cần tìm resource plugin do loader khác cung cấp, `ClassLoader` hoặc context class loader có thể phù hợp hơn nhưng phải có thiết kế visibility tương ứng.

## 6. Thread context class loader và thư viện/plugin

Một thư viện đôi khi không biết trước các lớp hoặc resource mà ứng dụng sử dụng sẽ nằm ở class loader nào. Ví dụ framework cần nạp driver, plugin, provider hoặc file cấu hình do ứng dụng triển khai. Trong trường hợp đó, thư viện có thể dùng **thread context class loader (TCCL)**:

~~~java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

URL config = contextLoader == null
        ? null
        : contextLoader.getResource("plugin/plugin.properties");
~~~

TCCL khác với defining loader của thư viện. Nó có thể được container hoặc caller đặt để một thư viện framework tìm thấy resource do ứng dụng/plugin cung cấp.

Các điểm cần nhớ:

- Không mặc định TCCL luôn bằng `SomeLibrary.class.getClassLoader()`.
- TCCL có thể thay đổi giữa thread xử lý request, thread của executor và thread nền.
- Khi chạy async, task có thể kế thừa hoặc không kế thừa context loader mong muốn tùy cơ chế tạo thread.
- Với custom loader, thứ tự parent delegation và cách triển khai `getResource` ảnh hưởng kết quả.
- Khi chạm ranh giới module, TCCL không vô hiệu hóa quy tắc encapsulation của JPMS.

Nếu cần đổi TCCL tạm thời, phải khôi phục lại bằng `finally`:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi thư viện được thiết kế để sử dụng TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là kỹ thuật tích hợp có chủ đích, không phải cách mặc định để sửa mọi lỗi resource lookup. Trong môi trường nhiều plugin, việc đặt sai context loader có thể làm code chọn nhầm resource cùng tên từ plugin khác.

## 7. Resource trùng tên và thứ tự ưu tiên

Một tên như `config/defaults.properties` có thể xuất hiện trong nhiều JAR hoặc nhiều module. `ClassLoader.getResource` thường trả về một kết quả nếu tìm thấy; `ClassLoader.getResources` cho phép lấy một enumeration các URL tương ứng.

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Enumeration<URL> resources =
        loader.getResources("config/defaults.properties");

while (resources.hasMoreElements()) {
    URL url = resources.nextElement();
    System.out.println(url);
}
~~~

Đoạn code minh họa việc tìm nhiều resource; ở môi trường thật cần kiểm tra loader khác `null` và xử lý `IOException` theo ngữ cảnh.

Không nên thiết kế hệ thống dựa vào thứ tự các resource cùng tên nếu thứ tự đó không được hợp đồng loader cam kết. Với named modules, thứ tự hoặc tập module được tìm qua loader có thể không phải thứ tự trong module graph mà developer hình dung. Với custom loader, behavior còn do implementation quyết định.

Nếu muốn chọn đúng cấu hình của một module, **hãy tìm theo module đích** hoặc dùng namespace resource đủ riêng biệt, ví dụ:

~~~text
com/acme/catalog/config/defaults.properties
com/acme/payments/config/defaults.properties
~~~

Đừng dùng một tên chung như `config.properties` ở gốc nhiều JAR rồi trông chờ “JAR nào đứng trước sẽ thắng”, trừ khi đây là contract đã được xác định và kiểm thử.

## 8. Những resource không nằm trong package Java

Không phải mọi resource trong JAR đều thuộc package Java. Ví dụ:

~~~text
config/application.properties
templates/receipt.mustache
META-INF/services/com.acme.spi.Codec
META-INF/native-image/...
~~~

Việc một đường dẫn nằm trong JAR không đồng nghĩa nó là package được khai báo trong JPMS. Quy tắc encapsulation đối với resource trong package của named module cần phân biệt với resource không nằm trong package đó.

Một nhóm file thường được đặt ngoài package để phục vụ cơ chế discovery hoặc hệ thống cấu hình. Tuy nhiên, đặt resource ở gốc JAR cũng không tự giải quyết vấn đề tên bị trùng hoặc loader lựa chọn sai. Tên resource vẫn nên được namespace hợp lý.

Đặc biệt, `META-INF/services` thường được dùng trong cơ chế service provider truyền thống. Trong named module, việc cung cấp và tiêu thụ service có các khai báo module riêng; không nên đơn giản thay `ServiceLoader` bằng việc đọc file resource rồi tự nạp class.

## 9. ServiceLoader, uses/provides và module layer

`ServiceLoader` là cơ chế chuẩn để tìm provider triển khai một service interface. Nó liên quan đến class loader và resource discovery, nhưng không chỉ là một lời gọi `getResources("META-INF/services/...")` thông thường.

Ở classpath, provider thường được liệt kê trong:

~~~text
META-INF/services/com.acme.spi.Codec
~~~

Một named module có thể khai báo:

~~~java
module com.acme.codec.provider {
    requires com.acme.codec.api;
    provides com.acme.spi.Codec
        with com.acme.impl.JsonCodec;
}
~~~

Module sử dụng service có thể khai báo:

~~~java
module com.acme.app {
    requires com.acme.codec.api;
    uses com.acme.spi.Codec;
}
~~~

Sau đó ứng dụng nạp provider:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.getClass().getName());
}
~~~

Với named modules, hãy kiểm tra module descriptor, layer, loader và đường tìm provider theo contract của `ServiceLoader`. `ServiceLoader.load(service)` sử dụng cơ chế gắn với context class loader; `ServiceLoader.load(layer, service)` có thể được dùng khi cần tìm provider trong một module layer cụ thể.

Trong hệ thống plugin, nếu tạo custom `ModuleLayer` mà lại gọi `ServiceLoader` theo một loader/layer không phù hợp, provider có thể không xuất hiện dù module provider đã được resolve. Đây là lỗi discovery, không nhất thiết là thiếu class hay thiếu resource file.

## 10. ResourceBundle và dữ liệu đa ngôn ngữ

`ResourceBundle` thường dùng các file:

~~~text
com/acme/app/messages.properties
com/acme/app/messages_vi.properties
com/acme/app/messages_en.properties
~~~

Trên classpath, code có thể đọc:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.acme.app.messages",
        Locale.forLanguageTag("vi"));

String title = bundle.getString("screen.title");
~~~

Trong môi trường named modules, cách tìm bundle và provider cũng chịu ảnh hưởng module, caller context, package visibility và các overload/module-aware API của `ResourceBundle`. Không mặc định mọi bundle hoạt động giống hệt như khi còn trên classpath.

Khi migration:

1. Ghi lại base name của bundle.
2. Kiểm tra vị trí file theo resource path và package.
3. Kiểm tra encoding, locale fallback và key được sử dụng.
4. Kiểm tra module chứa bundle và các quy tắc opens/provider liên quan.
5. Dùng API module-aware phù hợp nếu muốn chọn rõ module chứa bundle.
6. Kiểm thử các locale mà hệ thống thực sự hỗ trợ.

Nếu resource bundle không được tìm thấy, có thể nhận `MissingResourceException` thay vì `null` như các lời gọi `getResourceAsStream`. Cần phân biệt lỗi tải bundle với lỗi không có key trong bundle.

## 11. Tài nguyên trong thư viện modular và automatic module

Một JAR không có `module-info.class` nhưng đặt trên module path có thể trở thành **automatic module**. Khả năng tương tác và chính sách export/open của automatic module khác với named module được mô tả rõ bằng `module-info.java`.

Trong migration, cần ghi lại:

- JAR có explicit module descriptor hay không.
- JAR được đặt trên classpath hay module path.
- Nếu là automatic module, module name được xác định thế nào.
- Nếu là explicit named module, package nào được `exports` và `opens`.
- Resource nằm trong package nào của module.
- Code gọi resource thuộc module và loader nào.
- Có custom module layer hoặc plugin loader không.

Chỉ thấy một JAR có tên `some-library.jar` chưa đủ để kết luận nó chạy như unnamed, automatic hay explicit named module. Cùng JAR nhưng cách launch khác có thể dẫn đến hành vi resource lookup khác.

## 12. Mô hình minh họa: module chứa cấu hình và module tiêu thụ

Giả sử có hai module:

~~~text
com.acme.catalog
  module-info.java
  com/acme/catalog/api/CatalogApi.java
  com/acme/catalog/internal/DefaultsMarker.java
  com/acme/catalog/internal/defaults.properties

com.acme.app
  module-info.java
  com/acme/app/Main.java
~~~

Module catalog khai báo:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.app;
}
~~~

Module app khai báo:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Trong `Main`, ứng dụng lấy module từ một public API type của catalog:

~~~java
package com.acme.app;

import com.acme.catalog.api.CatalogApi;
import java.io.IOException;
import java.io.InputStream;

public class Main {
    public static void main(String[] args) throws IOException {
        Module catalog = CatalogApi.class.getModule();

        try (InputStream in = catalog.getResourceAsStream(
                "com/acme/catalog/internal/defaults.properties")) {
            if (in == null) {
                throw new IllegalStateException("Resource bị thiếu hoặc không truy cập được");
            }
            System.out.println(in.read());
        }
    }
}
~~~

Trong ví dụ, resource nằm trong package `com.acme.catalog.internal` của named module. `opens ... to com.acme.app` cho phép module app tiếp cận resource theo quy tắc của `Module.getResourceAsStream`. Tuy nhiên, không nên kỳ vọng một lời gọi `CatalogApi.class.getClassLoader().getResource(...)` tự động tìm được resource đó, vì package không được mở vô điều kiện.

Ví dụ dùng `in.read()` để chứng minh stream tồn tại; mã ứng dụng thật nên parse file theo đúng encoding và định dạng, sử dụng `Properties.load`, `InputStreamReader` hoặc parser tương ứng.

### 12.1. Thêm một resource vào package không mở

Nếu provider chuyển `defaults.properties` vào package `com.acme.catalog.secrets` mà module không `opens` package đó cho app, lời gọi từ module app có thể trả `null` dù file vẫn được đóng gói trong JAR. Việc sửa đường dẫn cho đúng nhưng quên module policy vẫn chưa đủ.

### 12.2. Mở mọi package để tránh lỗi có nên không?

Không nên vội đổi thành `open module com.acme.catalog` chỉ để một file cấu hình được đọc. Cách đó mở toàn bộ package cho deep reflection và làm yếu ranh giới encapsulation của module. Ưu tiên mở đúng package tới đúng module khi hợp đồng yêu cầu, hoặc cung cấp API công khai của provider trả về dữ liệu cấu hình thay vì buộc consumer đọc file nội bộ.

Nếu resource là chi tiết triển khai, giải pháp thiết kế tốt hơn có thể là:

~~~java
public final class CatalogDefaults {
    public static Properties loadDefaults() throws IOException {
        Properties properties = new Properties();
        try (InputStream in = CatalogDefaults.class
                .getResourceAsStream("defaults.properties")) {
            if (in == null) {
                throw new FileNotFoundException("defaults.properties");
            }
            properties.load(in);
        }
        return properties;
    }
}
~~~

Khi API đọc nằm trong module sở hữu resource, consumer chỉ gọi API công khai và không cần biết đường dẫn nội bộ. Để ví dụ biên dịch, class cần import `java.util.Properties`, `java.io.InputStream`, `java.io.IOException` và `java.io.FileNotFoundException`; mục đích đoạn mã là minh họa cách đóng gói việc đọc resource.

## 13. Không chuyển URL resource thành File một cách máy móc

Một cách viết dễ lỗi:

~~~java
URL url = MyComponent.class.getResource("template.txt");
File file = new File(url.getFile());
~~~

Nó có thể hoạt động khi chạy từ IDE với resource là file trong thư mục output, nhưng thất bại khi đóng gói vào JAR, fat JAR hoặc custom runtime image. URL có thể dùng scheme `jar:`, đường dẫn chứa ký tự được percent-encode hoặc do loader tùy chỉnh cung cấp.

Nếu mục tiêu là đọc nội dung, ưu tiên stream:

~~~java
try (InputStream in = MyComponent.class
        .getResourceAsStream("template.txt")) {
    if (in == null) {
        throw new IllegalStateException("Thiếu template.txt");
    }

    String content = new String(in.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(content);
}
~~~

Ví dụ sử dụng `InputStream.readAllBytes()` có từ Java 9 và cần các import tương ứng. Với file lớn, đọc theo luồng để tránh giữ toàn bộ dữ liệu trong bộ nhớ. Không mặc định encoding; hãy chọn charset theo hợp đồng của resource.

Nếu thư viện bên ngoài đòi `Path` hoặc `File`, có thể cần copy resource ra thư mục tạm được quản lý an toàn và xóa sau khi sử dụng. Việc đó khác với giả định resource vốn là file thật.

## 14. Đóng gói resource trong Gradle và Maven

Lỗi không tìm thấy tài nguyên cũng có thể đơn giản do build không đưa file vào artifact. JPMS không thể làm một file xuất hiện nếu file chưa được đóng gói.

Trong cấu trúc Gradle/Maven phổ biến:

~~~text
src/main/java/...
src/main/resources/com/acme/order/defaults.properties
src/test/resources/...
~~~

Các công cụ build thường đưa resource từ `src/main/resources` vào output main, còn resource test có phạm vi riêng. Cần xác nhận cấu hình source set, filtering và packaging thực tế của dự án, vì plugin có thể thay đổi mặc định.

Kiểm tra file đã được đóng gói:

~~~bash
jar tf build/libs/example.jar
~~~

Hoặc với artifact Maven:

~~~bash
jar tf target/example.jar
~~~

Tìm tên resource chính xác, gồm chữ hoa/chữ thường. Filesystem Windows thường không phân biệt hoa thường trong nhiều cấu hình, trong khi resource entry trong JAR có tên chính xác và môi trường Linux thường phân biệt. Lỗi khác biệt chữ hoa/chữ thường có thể chỉ lộ ra sau khi deploy.

Với multi-module build, file có thể nằm trong JAR của module A nhưng code ở module B dùng `getClassLoader` của chính B để tìm. Hãy xác định artifact thực tế chứa resource trước khi sửa cấu hình module.

### 14.1. Multi-release JAR

Một JAR có thể chứa các mục theo phiên bản trong `META-INF/versions/N/`. Khi chạy trên JDK khác nhau, class/resource được chọn có thể thay đổi theo cơ chế multi-release JAR và API/JAR loader được sử dụng. Nếu resource không đồng nhất qua các versioned entry, cần kiểm tra cả metadata manifest và hành vi trên các JDK mục tiêu.

Không nên suy đoán rằng hai runtime cùng nạp một resource chỉ vì chúng đang dùng cùng tên JAR. Hãy quan sát resource thực tế được đọc và kiểm tra artifact đầu vào.

## 15. Quy trình điều tra khi getResource trả null

Khi migration và resource lookup thất bại, hãy điều tra có thứ tự:

**Bước 1 — Ghi tên resource tuyệt đối.** Nếu code dùng `Class.getResource("x")`, suy ra tên package-prefixed thực tế. Nếu dùng `ClassLoader`, xác định code có thêm `/` sai hay không.

**Bước 2 — Xác nhận file trong artifact.** Dùng `jar tf` hoặc xem build output. Kiểm tra tên entry chính xác, đường dẫn và chữ hoa/chữ thường.

**Bước 3 — Xác định module chứa resource.** Nó là unnamed, automatic hay explicit named module? JAR chạy trên classpath hay module path?

**Bước 4 — Xác định API lookup.** Dùng `Class.getResource`, `ClassLoader.getResource`, `Module.getResourceAsStream`, `ResourceBundle` hay framework riêng? Mỗi API có contract khác nhau.

**Bước 5 — Xác định caller, module và loader.** Class làm mốc thuộc module nào? Caller của `Module.getResourceAsStream` thuộc module nào? Loader là application, platform, context hay plugin loader?

**Bước 6 — Kiểm tra package và opens.** Resource có nằm trong package của named module không? Package được mở vô điều kiện hay chỉ mở cho một module đích? Cách mở có đáp ứng lookup API đang dùng không?

**Bước 7 — Kiểm tra trùng tên.** Có resource cùng tên trong nhiều JAR/module không? Loader có trả một resource khác với mong đợi không?

**Bước 8 — Kiểm tra đóng gói và môi trường.** IDE, test runtime, fat JAR, JDK image và production có dùng cùng classpath/module path và cùng resource không?

**Bước 9 — Chạy một test tối thiểu.** Tạo test đọc đúng resource với cùng launch configuration, và ghi rõ phiên bản JDK, class loader, module name và kết quả lookup.

**Bước 10 — Sửa đúng tầng.** Sửa path nếu sai tên; sửa packaging nếu thiếu file; sửa `opens` nếu thiếu quyền hợp lệ; sửa loader/layer nếu tìm nhầm nơi; sửa thiết kế API nếu consumer đang phải đọc resource triển khai nội bộ.

### 15.1. Log thông tin module và loader

Trong mã chẩn đoán có thể in:

~~~java
Class<?> owner = MyComponent.class;

System.out.println("Class: " + owner.getName());
System.out.println("Module: " + owner.getModule().getName());
System.out.println("Named module: " + owner.getModule().isNamed());
System.out.println("Defining loader: " + owner.getClassLoader());
System.out.println("Context loader: "
        + Thread.currentThread().getContextClassLoader());
~~~

`Module.getName()` có thể trả `null` cho unnamed module. Không mặc định hai class có cùng loader chỉ vì chúng thuộc cùng package source; luôn kiểm tra class thực tế ở runtime.

### 15.2. Không dùng null để phân biệt quá nhiều nguyên nhân

`getResourceAsStream` trả về `null` có thể có nhiều nguyên nhân: tên sai, resource chưa đóng gói, loader không thấy, module encapsulation hoặc lựa chọn module không đúng. Không nên xử lý bằng cách đổi đồng loạt classpath, mở toàn bộ module hoặc tắt bảo mật khi chưa xác định chính xác nguyên nhân.

## 16. Kiểm thử tương thích trong migration JPMS

Nên kiểm thử ít nhất các tổ hợp triển khai thực sự được hỗ trợ:

| Tổ hợp | Cách chạy | Điều cần xác minh |
|---|---|---|
| Legacy | Toàn bộ trên classpath | Resource lookup cũ còn hoạt động |
| Mixed | Ứng dụng classpath, thư viện có thể là module | Loader/module lookup có đúng không |
| Modular | Named modules trên module path | `exports`, `opens` và resource visibility |
| Plugin | Custom loader hoặc layer | Module/resource có tìm qua đúng loader/layer không |
| Packaged | JAR/fat JAR/runtime image | Resource thực sự nằm trong artifact cuối |
| CI/prod | JDK và OS mục tiêu | Path, encoding và behavior nhất quán |

Bộ test nên bao gồm:

- Resource cùng package với class chủ sở hữu.
- Resource ở package khác trong cùng module.
- Resource ở package chỉ `opens` tới một module.
- Resource ở package chưa mở.
- Resource ở gốc JAR hoặc ngoài package.
- Resource trùng tên trong hai dependency.
- Resource được đọc qua context loader và custom loader nếu ứng dụng dùng plugin.
- Resource được đọc sau khi đóng gói artifact thật, không chỉ trong IDE.
- Locale bundle và service provider nếu ứng dụng sử dụng.

Với resource nhạy cảm, test nên xác nhận rằng package **không được phép** truy cập từ module ngoài dự kiến. Tính đúng đắn của modularization không chỉ là “đọc được file cần đọc” mà còn là “không mở thêm tài nguyên ngoài hợp đồng”.

## 17. Checklist trước khi phát hành

- [ ] Đã phân biệt `Class.getResource`, `ClassLoader.getResource` và `Module.getResourceAsStream`.
- [ ] Đã xác nhận tên resource tương đối/tuyệt đối và quy tắc dấu `/`.
- [ ] Đã kiểm tra tài nguyên nằm trong JAR/runtime image cuối cùng.
- [ ] Đã xác định class loader và module của class/caller ở runtime.
- [ ] Đã xác định package chứa resource thuộc named module hay không.
- [ ] Đã phân biệt `exports` và `opens`, kể cả mở có điều kiện.
- [ ] Đã kiểm tra quy tắc chỉ mở vô điều kiện cho một số lookup qua `ClassLoader`.
- [ ] Đã kiểm tra TCCL, custom loader và module layer nếu có plugin/framework.
- [ ] Đã xem xét resource trùng tên và thứ tự lookup không được bảo đảm.
- [ ] Đã kiểm thử ResourceBundle/ServiceLoader bằng API phù hợp nếu sử dụng.
- [ ] Đã kiểm tra việc đọc stream, đóng stream và encoding.
- [ ] Đã kiểm thử sau khi đóng gói và trên JDK/OS mục tiêu.
- [ ] Đã tránh mở toàn bộ module chỉ để workaround một lỗi resource path.

## 18. Kết luận

Nạp tài nguyên trong Java phụ thuộc vào **resource name**, **class hoặc loader làm mốc**, **module sở hữu resource** và **quy tắc encapsulation**. Khi chuyển từ classpath sang JPMS, một resource có thể vẫn tồn tại trong JAR nhưng không được trả về bởi `ClassLoader.getResource` nếu nó nằm trong package của named module không được mở phù hợp. `Module.getResourceAsStream` giúp truy cập rõ theo module và quyền của caller; `Class.getResourceAsStream` thuận tiện khi resource thuộc implementation của một class; `ClassLoader` và TCCL phù hợp hơn cho một số thiết kế plugin hoặc resource discovery.

Khi lỗi xảy ra, đừng mặc định đó là lỗi đường dẫn hoặc thiếu file. Hãy lần lượt xác minh artifact, đường dẫn, API lookup, module, loader, `opens` và launch configuration. Kết hợp kiểm thử trên classpath, module path, custom layer và artifact cuối sẽ giúp bảo đảm migration giữ đúng cả khả năng đọc tài nguyên lẫn ranh giới đóng gói mà JPMS đặt ra.
