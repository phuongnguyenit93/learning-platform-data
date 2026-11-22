# ResourceBundleProvider cho tài nguyên trong hệ mô-đun Java (JPMS)

## Mục tiêu

Trong Java Core, `java.util.ResourceBundle` tải thông điệp hoặc dữ liệu theo `Locale`. Khi ứng dụng chạy bằng classpath, các file `.properties` và các lớp `ListResourceBundle` thường được tra qua class loader. Khi chuyển sang **Java Platform Module System (JPMS)**, tài nguyên có thể được đóng gói trong **named modules** có giới hạn truy cập riêng. Nếu ứng dụng muốn lấy bundle từ **một module cung cấp độc lập**, API phù hợp là **`java.util.spi.ResourceBundleProvider`**.

`ResourceBundleProvider` là **service provider interface (SPI)** có từ Java 9, được tích hợp với cơ chế tìm bundle và `ServiceLoader`. Thông qua `uses` và `provides ... with ...` trong `module-info.java`, module consumer có thể phát hiện một hoặc nhiều module cung cấp tài nguyên mà không import implementation cụ thể.

Sau bài, bạn có thể:

- Phân biệt bundle nằm **cùng named module** với bundle được cung cấp bởi **named module khác**.
- Biết chính xác cách đặt tên service interface theo **logical base name** của bundle.
- Dùng `ResourceBundleProvider#getBundle(String, Locale)` và ý nghĩa của kết quả `null`.
- Triển khai `AbstractResourceBundleProvider` cho file `.properties` và override `toBundleName` để đổi vị trí tài nguyên.
- Viết ba module API, provider và consumer với `exports`, `requires`, `uses`, `provides` đúng vai trò.
- Biên dịch và chạy một ví dụ **Java 17+ hoạt động thực sự** bằng `--module-source-path` và `--module-path`.
- Hiểu vấn đề **split package**, module resolution, candidate locale, fallback, cache và encapsulation.
- Phân biệt `ResourceBundleProvider` với `ResourceBundle.Control` khi nâng cấp ứng dụng classpath sang JPMS.
- Chẩn đoán lỗi thiếu module provider, thiếu file resource, sai tên service hoặc `MissingResourceException`.

Đây là bài thuộc nhóm **Đóng gói và mở rộng**: trọng tâm là cung cấp bản dịch bằng SPI trong JPMS, không phải bản thân cú pháp định dạng số/ngày hay hệ thống dịch tự động.

## 1. Vì sao không chỉ dùng ResourceBundle.getBundle trực tiếp?

Một ứng dụng nhỏ có thể để file dịch và code trong cùng module:

```text
com.example.app
  module-info.java
  com/example/app/Main.class
  com/example/app/Messages_vi.properties
```

Khi tài nguyên được đóng gói đúng và truy cập từ chính module đó, `ResourceBundle.getBundle(baseName, locale)` có thể nạp bundle local; **không bắt buộc** tạo một interface provider cho mọi ứng dụng dùng JPMS.

Nhu cầu khác xuất hiện khi bản dịch được phân phối riêng, ví dụ:

- Sản phẩm có lõi chỉ biết các key, còn nhóm địa phương hóa phát hành module tiếng Việt, Anh, Pháp riêng.
- Plugin cần bổ sung ngôn ngữ sau khi ứng dụng chính đã biên dịch.
- Một thư viện chỉ công bố API tài nguyên, không muốn đóng gói mọi bản dịch.
- Một module provider muốn nạp nguồn tùy biến thay vì để consumer tìm file nội bộ.

Nếu bundle ở named module khác, việc gọi `ClassLoader.getResourceAsStream` từ consumer **không luôn nhìn thấy tài nguyên** do quy tắc encapsulation. `ResourceBundleProvider` cho phép chính **module sở hữu resource** chịu trách nhiệm tạo hoặc nạp `ResourceBundle`, rồi trả về cho cơ chế nạp bundle của Java.

```text
com.demo.bundle.app
    |
    | ResourceBundle.getBundle("com.demo.bundle.Messages", locale)
    | uses com.demo.bundle.spi.MessagesProvider
    v
com.demo.bundle.api
    |
    | interface MessagesProvider extends ResourceBundleProvider
    ^
    | implements
com.demo.bundle.impl
    |
    +-- DemoProvider
    +-- Messages_vi.properties
    +-- Messages_en.properties
```

Consumer vẫn phải biết **logical base name** và **message key**, nhưng không cần phụ thuộc trực tiếp vào class implementation hoặc package vật lý của file dịch.

## 2. Những thuật ngữ và vai trò cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Base name** | Định danh logic của family bundle | `com.demo.bundle.Messages` |
| **Locale** | Ngôn ngữ/vùng yêu cầu | `vi-VN`, `en-US` |
| **Service type** | Interface có tên theo quy tắc đặc biệt của ResourceBundleProvider | `com.demo.bundle.spi.MessagesProvider` |
| **Provider implementation** | Class trả bundle theo base name/locale | `com.demo.impl.DemoProvider` |
| **API module** | Nơi định nghĩa/export service interface | `com.demo.bundle.api` |
| **Consumer module** | Module gọi `ResourceBundle.getBundle` | `com.demo.bundle.app` |
| **Provider module** | Module triển khai service, sở hữu resources | `com.demo.bundle.impl` |
| **Physical bundle name** | Nơi provider tra cứu file/class resource thực tế | `com.demo.impl.Messages_vi` |
| **Resolved locale** | Locale của bundle thực sự đã nạp | `vi` |

**Logical base name không nhất thiết trùng physical bundle name.** Đây là điểm mở rộng quan trọng: caller vẫn dùng tên family ổn định trong khi các provider module có thể tổ chức resource ở các package khác nhau.

## 3. Quy tắc đặt tên service interface

Theo Java SE 17, service type cho một bundle có `baseName` phải mang tên đầy đủ:

```text
<package of baseName> + ".spi."
+ <simple name of baseName> + "Provider"
```

Ví dụ:

| Base name | Service interface |
| --- | --- |
| `com.demo.bundle.Messages` | `com.demo.bundle.spi.MessagesProvider` |
| `org.acme.ui.Errors` | `org.acme.ui.spi.ErrorsProvider` |
| `io.example.labels.Buttons` | `io.example.labels.spi.ButtonsProvider` |

Interface đúng cho ví dụ:

```java
package com.demo.bundle.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

Lưu ý interface này **kế thừa** phương thức `getBundle(String, Locale)`. Nó cần có tên phù hợp với family `com.demo.bundle.Messages`.

Hai nhầm lẫn phổ biến:

1. Đặt `MessagesProvider` trong package `com.demo.bundle` thay vì `com.demo.bundle.spi` và hy vọng Java tìm đúng.
2. Chỉ viết `uses java.util.spi.ResourceBundleProvider;` trong consumer, trong khi tên service type được tìm theo family là `com.demo.bundle.spi.MessagesProvider`.

Trong trường hợp này, tên không phải sở thích tùy ý của nhóm phát triển: nó là **hợp đồng đặt tên của API**. Nếu gọi `ResourceBundle.getBundle("...Messages", locale)` thì các module phải thống nhất service type tương ứng.

## 4. Module API, consumer và provider liên kết ra sao?

### API module

```java
module com.demo.bundle.api {
    exports com.demo.bundle.spi;
}
```

`exports` công khai package chứa interface để provider và consumer tham chiếu được kiểu Java.

### Consumer module

```java
module com.demo.bundle.app {
    requires com.demo.bundle.api;
    uses com.demo.bundle.spi.MessagesProvider;
}
```

`requires` cho phép app đọc API module; `uses` công bố module sử dụng service đó.

### Provider module

```java
module com.demo.bundle.impl {
    requires com.demo.bundle.api;

    provides com.demo.bundle.spi.MessagesProvider
            with com.demo.impl.DemoProvider;
}
```

`provides ... with ...` đăng ký implementation class. Class này phải implement đúng interface, đáp ứng yêu cầu service loading của JPMS. Ví dụ dùng class `public` với constructor no-arg `public`.

Những khai báo bắt buộc phải **khớp chính xác cùng một interface**. Việc app không có `requires com.demo.bundle.impl;` là chủ đích để tránh dependency trực tiếp vào implementation; provider sẽ được service binding phát hiện khi module được resolve.

**Không dùng `open module` để chữa sai service name.** Việc mở package cho reflection khác với cơ chế đăng ký service và nạp resources đúng cách.

## 5. Hợp đồng ResourceBundleProvider#getBundle

SPI gốc trong `java.util.spi` có chữ ký:

```java
ResourceBundle getBundle(String baseName, Locale locale);
```

Không tự tạo file Java trong package `java.util.spi`; đây là chữ ký API có sẵn.

Provider được gọi khi `ResourceBundle` tìm bundle phù hợp theo candidate locale:

- `baseName` là tên logic mà consumer yêu cầu.
- `locale` là ứng viên locale được thử, không nhất thiết là requested locale cuối cùng.
- Trả `ResourceBundle` khi provider có tài nguyên tương ứng.
- Trả `null` khi provider **không có tài nguyên cho cặp baseName/locale**.

Ví dụ trong subclass của `AbstractResourceBundleProvider`:

```java
@Override
public ResourceBundle getBundle(String baseName, Locale locale) {
    if (!"com.demo.bundle.Messages".equals(baseName)) {
        return null;
    }
    return super.getBundle(baseName, locale);
}
```

Đây là đoạn minh họa trong lớp provider đã có `import java.util.ResourceBundle;` và `import java.util.Locale;`.

`null` **không phải exception**: nó cho phép quá trình nạp thử candidate khác hoặc nguồn phù hợp khác. Nhưng không nên bắt mọi lỗi I/O, dữ liệu hỏng hay bug và trả `null` một cách âm thầm; việc đó làm mất tín hiệu vận hành.

Nếu tìm không được bundle, `ResourceBundle.getBundle` có thể ném `MissingResourceException`. Nếu bundle tìm được nhưng một key không tồn tại, `bundle.getString(key)` cũng có thể ném `MissingResourceException`. Hai trường hợp cần được phân biệt khi điều tra.

## 6. AbstractResourceBundleProvider và toBundleName

`java.util.spi.AbstractResourceBundleProvider` cung cấp implementation cơ bản tìm bundle **bên trong module của provider**. Constructor:

```java
public DemoProvider() {
    super("java.properties");
}
```

`java.properties` và `java.class` là các format được lớp cơ sở hỗ trợ. Với format khác như XML hoặc JSON, implement `getBundle` phù hợp thay vì cố truyền chuỗi format không được hỗ trợ cho superclass.

Phương thức:

```java
protected String toBundleName(String baseName, Locale locale);
```

được dùng để tạo tên tài nguyên ứng với một locale. Mặc định nó theo quy tắc tên chuẩn kiểu `Messages_vi` hoặc `Messages_en_US`.

Nếu đưa nhiều module bản dịch vào cùng module graph, đặt chúng cùng một package Java có thể gây vấn đề **split package**. Provider có thể override để chuyển sang package vật lý riêng:

```java
@Override
protected String toBundleName(String baseName, Locale locale) {
    return "com.demo.impl.Messages"
            + (locale.equals(Locale.ROOT)
                ? "" : "_" + locale.toString());
}
```

Kết quả với locale `vi` là `com.demo.impl.Messages_vi`, tương ứng:

```text
com/demo/impl/Messages_vi.properties
```

Consumer vẫn gọi baseName `com.demo.bundle.Messages`. Việc map vật lý nằm trong implementation, không phơi ra trong API của consumer.

Các provider riêng khác có thể chọn package `com.demo.impl.fr`, `com.demo.impl.de`... khi thiết kế mở rộng, miễn là tránh xung đột package và đúng quy tắc module/resource.

## 7. Ví dụ Java 17+ hoàn chỉnh với ba named modules

Mô hình dưới đây đã được biên dịch và chạy bằng JDK 21, chỉ dùng các API tồn tại trên Java 17. Giá trị bản dịch minh họa là ASCII để output không phụ thuộc charset của terminal; file dịch thực tế có thể lưu văn bản tiếng Việt có dấu bằng UTF-8.

### 7.1. Cây thư mục

```text
resourcebundle-provider-demo/
├── src/
│   ├── com.demo.bundle.api/
│   │   ├── module-info.java
│   │   └── com/demo/bundle/spi/MessagesProvider.java
│   ├── com.demo.bundle.impl/
│   │   ├── module-info.java
│   │   └── com/demo/impl/
│   │       ├── DemoProvider.java
│   │       ├── Messages_vi.properties
│   │       └── Messages_en.properties
│   └── com.demo.bundle.app/
│       ├── module-info.java
│       └── com/demo/app/Main.java
└── mods/                          (sinh ra khi build)
```

Các thư mục dưới `src` cần đúng tên module trong `module-info.java` khi sử dụng `--module-source-path`.

### 7.2. Module API

Tệp `src/com.demo.bundle.api/module-info.java`:

```java
module com.demo.bundle.api {
    exports com.demo.bundle.spi;
}
```

Tệp `src/com.demo.bundle.api/com/demo/bundle/spi/MessagesProvider.java`:

```java
package com.demo.bundle.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

### 7.3. Module cung cấp

Tệp `src/com.demo.bundle.impl/module-info.java`:

```java
module com.demo.bundle.impl {
    requires com.demo.bundle.api;

    provides com.demo.bundle.spi.MessagesProvider
            with com.demo.impl.DemoProvider;
}
```

Tệp `src/com.demo.bundle.impl/com/demo/impl/DemoProvider.java`:

```java
package com.demo.impl;

import com.demo.bundle.spi.MessagesProvider;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

public final class DemoProvider extends AbstractResourceBundleProvider
        implements MessagesProvider {

    public DemoProvider() {
        super("java.properties");
    }

    @Override
    protected String toBundleName(String baseName, Locale locale) {
        return "com.demo.impl.Messages"
                + (locale.equals(Locale.ROOT)
                    ? "" : "_" + locale.toString());
    }

    @Override
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!"com.demo.bundle.Messages".equals(baseName)) {
            return null;
        }

        String language = locale.getLanguage();
        if (!language.equals("vi") && !language.equals("en")) {
            return null;
        }

        return super.getBundle(baseName, locale);
    }
}
```

Class này công bố public constructor không tham số và đúng interface. `toBundleName` nạp file theo package `com.demo.impl` thay vì logical package. `getBundle` từ chối family không đúng hoặc ngôn ngữ không phục vụ, còn trường hợp khác để superclass tìm resource.

Tệp `src/com.demo.bundle.impl/com/demo/impl/Messages_vi.properties`:

```properties
welcome=Xin chao
```

Tệp `src/com.demo.bundle.impl/com/demo/impl/Messages_en.properties`:

```properties
welcome=Hello
```

Để chuyển sang bản dịch có dấu, lưu UTF-8 và kiểm tra encoding của build. `PropertyResourceBundle` từ Java 9 hỗ trợ UTF-8 theo hợp đồng với fallback ISO-8859-1 trong trường hợp phù hợp; không nhầm với hành vi `Properties.load(InputStream)`.

### 7.4. Module consumer

Tệp `src/com.demo.bundle.app/module-info.java`:

```java
module com.demo.bundle.app {
    requires com.demo.bundle.api;
    uses com.demo.bundle.spi.MessagesProvider;
}
```

Tệp `src/com.demo.bundle.app/com/demo/app/Main.java`:

```java
package com.demo.app;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        ResourceBundle vi = ResourceBundle.getBundle(
                "com.demo.bundle.Messages",
                Locale.forLanguageTag("vi-VN"));

        ResourceBundle en = ResourceBundle.getBundle(
                "com.demo.bundle.Messages",
                Locale.US);

        System.out.println("VI=" + vi.getString("welcome")
                + " (" + vi.getLocale().toLanguageTag() + ")");

        System.out.println("EN=" + en.getString("welcome")
                + " (" + en.getLocale().toLanguageTag() + ")");
    }
}
```

App không import `DemoProvider`, chỉ biết baseName và hợp đồng service.

### 7.5. Biên dịch và copy file resource

Chạy từ thư mục `resourcebundle-provider-demo` với Bash trên Linux/macOS:

```bash
mkdir -p mods

javac -encoding UTF-8 \
  --module-source-path src \
  -d mods \
  $(find src -name '*.java')

cp src/com.demo.bundle.impl/com/demo/impl/*.properties \
   mods/com.demo.bundle.impl/com/demo/impl/
```

Các lệnh `find`, `cp` và cú pháp `$(...)` thuộc Bash; không dùng nguyên xi trong PowerShell. Với PowerShell, có thể lấy danh sách file Java bằng `Get-ChildItem -Recurse -Filter *.java` rồi truyền đường dẫn cho `javac`, và dùng `Copy-Item` để copy `.properties`.

**Điểm thường quên:** `javac` biên dịch file Java nhưng không tự copy mọi tài nguyên ngoài Java vào `mods`. Nếu file properties chỉ nằm trong `src`, runtime sẽ không có nội dung để provider nạp. Khi dùng Maven/Gradle, kiểm tra tài nguyên thực sự đã đi vào build output/JAR và đúng đường dẫn.

### 7.6. Chạy chương trình

```bash
java --module-path mods \
  --module com.demo.bundle.app/com.demo.app.Main
```

Stdout:

```text
VI=Xin chao (vi)
EN=Hello (en)
```

Ở runtime dùng kiểm thử, service binding resolve module provider từ module path do app khai báo `uses` phù hợp. Có thể thêm rõ module provider vào graph:

```bash
java --module-path mods \
  --add-modules com.demo.bundle.impl \
  --module com.demo.bundle.app/com.demo.app.Main
```

Output vẫn như trên.

Tại sao là `vi` và `en`? Code yêu cầu `vi-VN` và `en-US` nhưng provider chỉ có `Messages_vi.properties` và `Messages_en.properties`. `ResourceBundle` tìm candidate ít cụ thể hơn nên `bundle.getLocale()` cho `vi` hoặc `en`.

Ví dụ ba module đã được **biên dịch và chạy**, bao gồm cả cách khởi chạy có và không có `--add-modules`; không phải một bộ snippets chưa kiểm chứng.

## 8. Candidate locale, fallback và resolved locale

Một request `Locale.forLanguageTag("vi-VN")` có thể dẫn đến:

```text
Requested: vi-VN
    |
Candidate: vi_VN (không có Messages_vi_VN.properties)
    |
Candidate: vi    (có Messages_vi.properties)
    |
Resolved locale: vi
```

Đây là **sơ đồ minh họa trường hợp cụ thể**, không phải toàn bộ quy tắc fallback của mọi locale. `ResourceBundle` có thể xét script/variant, root bundle và default locale theo hợp đồng API khi không tìm thấy candidate.

Nên phân biệt:

- `requestedLocale`: người dùng hoặc chương trình yêu cầu.
- `candidateLocale`: một ứng viên được cơ chế nạp thử.
- `resolvedLocale`: locale của bundle thực tế trả về, lấy qua `bundle.getLocale()`.

Provider nên trả `null` khi không hỗ trợ candidate để thuật toán có thể thử tiếp. Không tự trả nội dung tiếng Anh cho mọi candidate nếu ứng dụng yêu cầu nhận biết locale fallback rõ ràng.

Nếu hệ thống cần kiểm soát “chỉ cho phép vi và en”, xác định danh sách ngôn ngữ hỗ trợ ở tầng ứng dụng, chọn fallback tường minh và kiểm thử cả bundle locale được trả về. Đừng giả định `getBundle` luôn trả chính xác requested locale.

## 9. Service binding, module path và encapsulation

`--module-path` chỉ định vị trí các modules khả dụng, không phải yêu cầu JVM nạp mọi file ở đó vào graph một cách vô điều kiện. Một provider chỉ được sử dụng khi module tương ứng được **resolve**.

Những yếu tố cần kiểm tra:

1. Module app được chạy bằng `--module`.
2. API module có trong graph nhờ `requires`.
3. App có `uses` đúng service type gắn với baseName.
4. Provider có `provides` đúng và hiện diện trên module path.
5. Runtime thực hiện service binding hoặc thêm provider bằng `--add-modules` khi cần.
6. Đường dẫn tài nguyên bên trong compiled provider module thực sự tồn tại.

Module implementation không nhất thiết `exports` package của nó cho app, vì app không import class implementation. Trong ví dụ, provider đọc resources local qua `AbstractResourceBundleProvider` mà không cần `open module`.

Điều đó **không** có nghĩa mọi tài nguyên trong mọi module đều truy cập được từ bất kỳ `ClassLoader` nào. Quy tắc encapsulation của `Module.getResourceAsStream` và nguồn tài nguyên riêng vẫn phải được tôn trọng.

### Split package là gì?

JPMS hạn chế cách nhiều named modules cùng sở hữu một package Java. Nếu các module bản dịch độc lập cùng đặt resources/lớp vào physical package `com.demo.bundle`, cấu trúc dễ gây xung đột package. Dùng physical package riêng, ví dụ `com.demo.impl`, và override `toBundleName` để giữ logical baseName ổn định.

## 10. So sánh với ResourceBundle.Control

`ResourceBundle.Control` là một cơ chế tùy biến loading, format, candidate locales, TTL trong môi trường classpath/unnamed module. Với named modules, cách dùng một instance `Control` qua các overload `ResourceBundle.getBundle` có những giới hạn và `UnsupportedOperationException` ở các trường hợp không hỗ trợ.

Bảng phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `ResourceBundle.getBundle` | API lấy bundle cho base name/locale |
| `ResourceBundleProvider` | SPI để bundle được cung cấp từ provider modules |
| `AbstractResourceBundleProvider` | Implementation nền cho provider đọc `java.properties`/`java.class` |
| `ResourceBundle.Control` | Tùy biến loading ở ngữ cảnh truyền thống, không thay thế SPI JPMS |
| `ResourceBundleControlProvider` | SPI khác nhằm cung cấp Control; không phải provider bản dịch cho named module |

Khi chuyển một codebase Java 8 dùng `Control` sang JPMS, cần xem lại loại module, cách gọi overload và kiến trúc resource. Không nên chỉ copy subclass `Control` rồi mặc định toàn bộ logic nạp custom format vẫn hoạt động như cũ.

Provider có thể tự tạo bundle từ XML/JSON hoặc một nguồn dữ liệu khác thông qua `getBundle`. Nhưng `AbstractResourceBundleProvider` chỉ chấp nhận các format chuẩn được nó hỗ trợ; dữ liệu từ nguồn khác cần implementation phù hợp.

## 11. Cache và tính an toàn khi có nhiều luồng

`ResourceBundle` cache các bundle đã nạp theo cơ chế chuẩn. Vì vậy:

- Chỉnh file tài nguyên của một module/JAR đã được load không bảo đảm `getBundle` đọc lại ngay.
- Khi phát hành resource mới, có thể cần lifecycle deploy/restart thích hợp.
- `ResourceBundle.clearCache()` có tác dụng với cache trong phạm vi được API định nghĩa; không nên gọi mỗi request.
- Một provider dùng nguồn dữ liệu động phải có policy refresh/version/caching rõ, không dựa vào việc sửa file ngẫu nhiên.

Các implementation chuẩn như `PropertyResourceBundle` và `ListResourceBundle` có bảo đảm thread safety cho các thao tác mặc định tương ứng. Nhưng provider tùy biến có thể có `Map`, network client hoặc cache mutable; cần bảo vệ khi nhiều luồng cùng truy cập.

SPI chỉ giải quyết vấn đề **khám phá và phân phối resource**, không bảo đảm mọi state bên trong implementation đều thread-safe.

## 12. Chẩn đoán MissingResourceException

Nếu `ResourceBundle.getBundle("com.demo.bundle.Messages", locale)` thất bại, kiểm tra tuần tự:

1. **Base name** có chính xác và không chứa hậu tố file hay locale không?
2. Service interface có tên đúng `com.demo.bundle.spi.MessagesProvider` theo quy tắc Java 17 không?
3. API module có export package SPI không?
4. Consumer có `requires com.demo.bundle.api` và `uses com.demo.bundle.spi.MessagesProvider` không?
5. Provider module có `provides ... with ...` khớp interface không?
6. Provider class có constructor hợp lệ và thực sự implement interface không?
7. Provider module có mặt trên module path và được resolve không?
8. `getBundle` của provider có trả `null` vì check baseName hoặc locale quá chặt không?
9. `toBundleName` có sinh tên bundle vật lý đúng không?
10. Tệp `Messages_vi.properties` có được copy vào output ở đúng path không?
11. Một candidate locale hay root bundle phù hợp có tồn tại không?
12. Có cache cũ hoặc runtime đang chạy artifact khác với file vừa build không?

Nếu bundle tải được nhưng `getString("welcome")` thất bại, cần điều tra **key**, không nhất thiết điều tra module graph từ đầu.

Một số công cụ hỗ trợ:

```bash
java --show-module-resolution --module-path mods \
  --module com.demo.bundle.app/com.demo.app.Main

jar --list --file provider.jar

jar --describe-module --file provider.jar
```

Hai lệnh `jar` giả định bạn đã tạo một modular JAR tên `provider.jar`. Đó là tên minh họa, không phải file có sẵn ở cây thư mục demo trước khi đóng gói.

## 13. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Mọi bundle trong named module phải có SPI | Local bundle có thể được nạp trực tiếp | Chỉ dùng provider khi cần tách module/mở rộng |
| Chỉ dùng `uses ResourceBundleProvider` | Service type có tên suy ra từ baseName | Tạo và khai báo interface đúng package `spi` |
| Tên provider có thể đặt tùy ý | Không đúng theo quy tắc service type | Tuân công thức package + `.spi.` + simple name + Provider |
| App cần import DemoProvider | Phá lợi ích tách implementation | App dùng ResourceBundle và service declaration |
| Provider không cần `provides` | Service loader cần metadata module | Khai báo `provides ... with ...` |
| `javac` copy properties | Compiler không tự copy các resource ngoài Java | Copy hoặc cấu hình build resource task |
| File tài nguyên phải nằm cùng package logical | Provider có thể tự map tên vật lý | Override `toBundleName` |
| Trả bundle tiếng Anh cho mọi locale | Che mất candidate và fallback đúng | Trả `null` cho locale không hỗ trợ |
| Requested locale luôn trùng resolved locale | Có thể fallback `vi-VN` sang `vi` | Kiểm tra `getLocale()` |
| Có module provider trên đĩa là đủ | Module cần được resolve vào graph | Kiểm tra module path và service binding |
| Mở toàn bộ module giải quyết mọi lỗi | Sai name, path và metadata vẫn sai | Sửa đúng service/resource contracts |
| Dùng `Control` như khi chạy classpath | Named module có giới hạn riêng | Dùng provider khi cần |
| Đổi file resource thì app tự refresh | Bundle có caching/lifecycle | Quản lý phiên bản và refresh |
| Tạo nhiều provider trùng locale không có policy | Có thể phụ thuộc thứ tự phát hiện | Tránh overlap hoặc xác định ưu tiên |

## 14. Bài tập tự kiểm tra

**Bài 1 — service name.** Với base name `org.acme.ui.Words`, hãy tạo service type đúng quy tắc. Viết `uses` ở consumer và `provides` ở provider.

**Bài 2 — bổ sung tiếng Pháp.** Thêm `Messages_fr.properties` vào module triển khai và nới logic provider. Gọi `Locale.FRANCE` nhưng chỉ có file cho `fr` thì resolved locale thường là gì?

**Bài 3 — tách gói.** Giả sử có một provider bản dịch tiếng Đức trong module khác. Hãy đặt tài nguyên vào package vật lý riêng và override `toBundleName` để không gây split package.

**Bài 4 — kiểm tra build.** Bỏ bước copy `.properties` khỏi lệnh biên dịch. Vì sao code Java có thể compile thành công mà runtime không có bundle?

**Bài 5 — provider resolution.** Provider module không được resolve. Hãy kiểm tra từng điều kiện của module path, service metadata và `--add-modules` để tìm nguyên nhân.

**Bài 6 — Control và provider.** Một thư viện legacy dùng `ResourceBundle.Control` để đọc XML. Khi chuyển sang named module, bạn sẽ tổ chức `ResourceBundleProvider#getBundle` như thế nào?

**Bài 7 — fallback.** Phân biệt `requestedLocale = vi-VN`, candidate `vi-VN` và `vi`, cùng `getLocale() = vi` trong ví dụ. Làm sao để test fallback không phụ thuộc default locale?

**Bài 8 — cập nhật bản dịch.** Một dịch vụ muốn cập nhật resource mà không restart. Vì sao caching và lifecycle của named module khiến việc sửa file đơn giản không đủ? Đề xuất policy version/refresh.

## 15. Kết luận

**`java.util.spi.ResourceBundleProvider` là cơ chế cung cấp bundle giữa các named modules của JPMS.** Module consumer biết base name và service type theo quy tắc, khai báo `uses`; module provider implements interface và khai báo `provides ... with ...`. Nhờ vậy ứng dụng có thể thêm gói dịch mà không phụ thuộc trực tiếp vào lớp triển khai.

`AbstractResourceBundleProvider` giúp đọc `.properties` hoặc bundle class trong provider module. Override `toBundleName` cho phép lưu resource ở package vật lý riêng và giữ logical base name ổn định. `ResourceBundle` tiếp tục xử lý candidate locale, fallback và cache; provider cần trả `null` đúng trường hợp và được resolve hợp lệ trong module graph.

**Nguyên tắc cốt lõi:** *Hợp đồng dịch nằm ở base name và service interface; module triển khai sở hữu resource. Khai báo đúng service, đóng gói đúng file, kiểm chứng module resolution và kết quả locale thực tế.*

### Tài liệu API

- [`ResourceBundleProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [`AbstractResourceBundleProvider` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html)
- [`ResourceBundle` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`ServiceLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
