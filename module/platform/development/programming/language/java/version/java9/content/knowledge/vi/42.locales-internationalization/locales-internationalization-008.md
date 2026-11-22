# ResourceBundleProvider cho dịch vụ bản dịch trong Java 9+ (vẫn áp dụng hiện nay)

## 1. Bài toán và khi nào nên dùng

Trong ứng dụng đa ngôn ngữ, `ResourceBundle` lưu các cặp khóa–giá trị như `hello=Bonjour`; mã nguồn chọn văn bản theo `Locale`. Với ứng dụng modular (JPMS, có `module-info.java`), bản dịch có thể nằm trong **module riêng**: một bản dịch tiếng Pháp, một bản dịch tiếng Việt, v.v. `ResourceBundleProvider` (ra mắt ở Java 9 và vẫn có trong Java SE hiện hành) là **SPI — Service Provider Interface** để `ResourceBundle.getBundle(...)` tìm các gói dịch được cung cấp bởi những named module khác qua cơ chế `ServiceLoader`.

Dùng `ResourceBundleProvider` khi muốn tách bản dịch khỏi module gọi, đóng gói ngôn ngữ thành các provider/module có thể triển khai riêng, hoặc tự xây cách cung cấp `ResourceBundle`. Nếu tất cả tệp `Messages_*.properties` đã nằm trong cùng module của ứng dụng và cách nạp mặc định đáp ứng nhu cầu, chỉ dùng `ResourceBundle.getBundle(...)` thường đã đủ; không cần tự tạo provider.

Phân biệt ba thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `Locale` | Mô tả ngôn ngữ và tùy chọn vùng, ví dụ `fr`, `fr-CA`, `vi-VN`. |
| `ResourceBundle` | Truy xuất thông điệp theo khóa, có cơ chế tìm phiên bản ngôn ngữ và fallback. |
| `ResourceBundleProvider` / `AbstractResourceBundleProvider` | Hợp đồng SPI và lớp tiện ích để module dịch cung cấp các `ResourceBundle` cho module khác. |

Đây là API dành cho **gói tài nguyên của ứng dụng**; không nhầm với `LocaleServiceProvider` dùng để bổ sung dữ liệu cho các dịch vụ locale của JDK như định dạng ngày, số, tiền tệ.

## 2. Cơ chế hoạt động trong JPMS

Giả sử mã gọi dùng:

```java
ResourceBundle messages =
        ResourceBundle.getBundle("demo.app.Messages", Locale.FRENCH);
String greeting = messages.getString("hello");
```

`"demo.app.Messages"` là **base name logic** của bộ tài nguyên, không bắt buộc phải có lớp Java `Messages`. Với base name này, Java suy ra **kiểu dịch vụ bắt buộc phải có tên** `demo.app.spi.MessagesProvider` theo công thức:

```text
<package-của-base-name>.spi.<tên-đơn-của-base-name>Provider
demo.app.Messages  ->  demo.app.spi.MessagesProvider
```

Luồng tìm kiếm:

1. Module ứng dụng khai báo `uses demo.app.spi.MessagesProvider;`.
2. Module dịch khai báo `provides demo.app.spi.MessagesProvider with demo.fr.FrenchProvider;`.
3. Khi gọi `ResourceBundle.getBundle`, Java dùng cơ chế dịch vụ để tìm những provider đã được **resolve** trong module layer.
4. Java thử các locale ứng viên theo quy tắc của `ResourceBundle`. Provider nhận `getBundle(baseName, locale)`, trả về một `ResourceBundle` phù hợp hoặc **`null`** nếu không có.
5. Khi một bundle được tìm thấy, mã gọi đọc khóa bằng `getString`. Nếu không tìm được bundle trong quá trình tra cứu, `ResourceBundle.getBundle` có thể ném `MissingResourceException`.

Một provider không tự động được sử dụng chỉ vì tệp JAR của nó có mặt trên máy: module phải tham gia vào **module graph** lúc chạy. Bài thực hành dưới đây dùng `--add-modules demo.fr` để bảo đảm điều đó.

`AbstractResourceBundleProvider` giúp giảm mã lặp: mặc định hỗ trợ định dạng `java.properties`; có thể cấu hình `java.class` và/hoặc `java.properties`, ghi đè `toBundleName` để ánh xạ sang tên tài nguyên thực tế. Nếu dùng định dạng khác như XML hoặc dữ liệu từ dịch vụ ngoài, cần tự cài đặt `getBundle` phù hợp; **không** truyền chuỗi `"xml"` vào constructor của `AbstractResourceBundleProvider`.

## 3. Ví dụ chạy được: ứng dụng và module dịch tiếng Pháp

Ví dụ gồm **hai named module**. Module `demo.app` chứa mã gọi và interface SPI; module `demo.fr` chứa provider cùng bản dịch tiếng Pháp. Không có phụ thuộc trực tiếp từ ứng dụng sang implementation tiếng Pháp.

```text
src/
├── demo.app/
│   ├── module-info.java
│   └── demo/app/
│       ├── Main.java
│       └── spi/MessagesProvider.java
└── demo.fr/
    ├── module-info.java
    └── demo/fr/
        ├── FrenchProvider.java
        └── Messages_fr.properties
```

### 3.1. Khai báo module ứng dụng

**`src/demo.app/module-info.java`**

```java
module demo.app {
    exports demo.app.spi;
    uses demo.app.spi.MessagesProvider;
}
```

`exports` cho phép module cung cấp dịch vụ nhìn thấy interface `MessagesProvider`; `uses` đăng ký nhu cầu sử dụng SPI. Module ứng dụng không cần `requires demo.fr`.

**`src/demo.app/demo/app/spi/MessagesProvider.java`**

```java
package demo.app.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
```

Interface được đặt **đúng tên và đúng package theo base name**. Nếu đổi base name thành `com.shop.i18n.Labels` thì SPI tương ứng phải là `com.shop.i18n.spi.LabelsProvider`.

### 3.2. Viết mã gọi

**`src/demo.app/demo/app/Main.java`**

```java
package demo.app;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        for (Locale locale : new Locale[] {
                Locale.FRENCH, Locale.CANADA_FRENCH
        }) {
            ResourceBundle bundle =
                    ResourceBundle.getBundle("demo.app.Messages", locale);
            System.out.println(
                    locale.toLanguageTag() + ": " + bundle.getString("hello"));
        }
    }
}
```

Gọi với `fr-CA` minh họa cơ chế fallback: nếu không có bản riêng cho Canada, quá trình tìm kiếm có thể dùng bản tiếng Pháp chung `fr`.

### 3.3. Khai báo module cung cấp bản dịch

**`src/demo.fr/module-info.java`**

```java
module demo.fr {
    requires demo.app;
    provides demo.app.spi.MessagesProvider
            with demo.fr.FrenchProvider;
}
```

`requires demo.app` để triển khai interface SPI. `provides ... with ...` đăng ký implementation với hệ thống dịch vụ. Không cần `exports demo.fr`: lớp provider được khai báo qua `provides`.

**`src/demo.fr/demo/fr/FrenchProvider.java`**

```java
package demo.fr;

import demo.app.spi.MessagesProvider;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

public final class FrenchProvider
        extends AbstractResourceBundleProvider
        implements MessagesProvider {

    public FrenchProvider() {
        super("java.properties");
    }

    @Override
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!"demo.app.Messages".equals(baseName)
                || !Locale.FRENCH.equals(locale)) {
            return null;
        }
        return super.getBundle(baseName, locale);
    }

    @Override
    protected String toBundleName(String baseName, Locale locale) {
        return "demo.fr.Messages_fr";
    }
}
```

Ý nghĩa:

- `getBundle` kiểm tra đúng base name và chỉ hỗ trợ ứng viên locale `fr`; trả `null` khi không hỗ trợ, để quá trình tìm kiếm tiếp tục.
- `super.getBundle(...)` tìm bundle nằm **trong module provider** theo tên do `toBundleName` cung cấp.
- `toBundleName` ánh xạ base name logic `demo.app.Messages` sang tài nguyên vật lý `demo/fr/Messages_fr.properties`. Điều này tránh việc nhiều named module cùng sở hữu một Java package (lỗi **split package**).
- Lớp implementation là `public`, có constructor `public` không tham số, để hệ thống dịch vụ có thể khởi tạo.

**`src/demo.fr/demo/fr/Messages_fr.properties`**

```properties
hello=Bonjour
```

Từ Java 9, `PropertyResourceBundle` ưu tiên đọc tệp `.properties` ở UTF-8 (có cơ chế tương thích với ISO-8859-1 khi chuỗi byte không hợp lệ). Với bản dịch mới, hãy lưu tệp UTF-8 để viết trực tiếp tiếng Việt, tiếng Pháp có dấu; không cần chuyển mọi ký tự thành dạng `\uXXXX`.

### 3.4. Biên dịch và chạy

Từ thư mục chứa `src/`, dùng JDK **17 trở lên**; các API trong bài cũng có từ Java 9. Các lệnh sau dành cho shell Bash/Zsh:

```bash
mkdir -p mods/demo.app mods/demo.fr

javac -encoding UTF-8 -d mods/demo.app \
  src/demo.app/module-info.java \
  src/demo.app/demo/app/spi/MessagesProvider.java \
  src/demo.app/demo/app/Main.java

javac -encoding UTF-8 --module-path mods -d mods/demo.fr \
  src/demo.fr/module-info.java \
  src/demo.fr/demo/fr/FrenchProvider.java

mkdir -p mods/demo.fr/demo/fr
cp src/demo.fr/demo/fr/Messages_fr.properties mods/demo.fr/demo/fr/

java --module-path mods --add-modules demo.fr \
  --module demo.app/demo.app.Main
```

Trên PowerShell, có thể thay lệnh `cp` bằng `Copy-Item`; phần `javac` và `java` giữ nguyên ý nghĩa. Việc **copy tệp `.properties` vào thư mục output** là bắt buộc vì `javac` chỉ biên dịch mã Java, không tự sao chép tài nguyên.

**Kết quả stdout:**

```text
fr: Bonjour
fr-CA: Bonjour
```

Ví dụ này đã được biên dịch/chạy trên OpenJDK 24.0.2. `fr-CA` nhận `Bonjour` từ `fr` nhờ thứ tự locale ứng viên, dù `FrenchProvider` chỉ trả bundle khi đối số locale là `Locale.FRENCH`.

## 4. Áp dụng vào dịch vụ bản dịch thực tế

### Tách ngôn ngữ thành module

Giữ base name và interface SPI ổn định trong module dùng chung. Mỗi gói ngôn ngữ có module riêng, ví dụ `demo.fr`, `demo.vi`, cùng `provides demo.app.spi.MessagesProvider with ...` nhưng implement và tài nguyên khác nhau. Module ứng dụng tiếp tục gọi `ResourceBundle.getBundle("demo.app.Messages", requestedLocale)` mà không cần `if/else` liệt kê từng provider.

Khi đóng gói thực tế, bảo đảm provider module được giải quyết trong module layer; có thể dùng cấu hình module graph, `--add-modules`, hoặc service binding của công cụ đóng gói. Không giả định rằng mọi JAR trên `--module-path` đều được nạp. Nếu phân phối nhiều gói ngôn ngữ, đặt tài nguyên trong **package khác nhau**, tránh split package giữa các named module.

### Fallback và bản dịch còn thiếu

`ResourceBundle` xét các locale ứng viên theo ngôn ngữ, vùng, biến thể; có thể xem xét locale mặc định của JVM và bundle gốc tùy trường hợp. Ví dụ, yêu cầu `fr-CA` có thể rơi về `fr`; không nên giả định chỉ thử đúng một tệp. Trong hệ thống sản xuất, chuẩn bị bundle gốc hoặc ngôn ngữ mặc định với các khóa chung và **kiểm thử các đường fallback** mà sản phẩm cần. Nếu không có bundle phù hợp, `getBundle` có thể ném `MissingResourceException`; nếu bundle tồn tại nhưng thiếu khóa, `getString("key")` cũng ném `MissingResourceException`.

`getBundle` có cơ chế **cache**. Sửa tệp dịch khi tiến trình đang chạy không có nghĩa nội dung thay đổi được nhìn thấy ngay; thiết kế chiến lược reload/triển khai và kiểm thử cache nếu cần cập nhật động. Truy xuất trong mã giao diện nên dùng khóa ổn định, tham số định dạng rõ ràng, giữ các placeholder nhất quán giữa ngôn ngữ; `ResourceBundle` chỉ giải quyết việc chọn văn bản, không tự xử lý đầy đủ quy tắc số nhiều, giới tính hay dịch nội dung.

### Khi nào tự cài đặt thay vì kế thừa lớp tiện ích?

- **Tài nguyên `.properties` hoặc lớp `ResourceBundle` trong module provider:** ưu tiên `AbstractResourceBundleProvider`.
- **Ánh xạ tên gói đặc biệt:** ghi đè `toBundleName`, như ví dụ.
- **XML, cơ sở dữ liệu, API dịch bên ngoài hoặc định dạng khác:** tự triển khai `ResourceBundleProvider.getBundle(baseName, locale)`, tạo/trả một `ResourceBundle` hợp lệ và tự xử lý lỗi, I/O, cache phù hợp. Một provider có thể trả `null` khi không hỗ trợ base name/locale.

## 5. Phân biệt với ResourceBundle.Control và những lỗi hay gặp

`ResourceBundle.Control` là API cấu hình cách tìm bundle trong ngữ cảnh classpath/unnamed module. Khi mã trong **named module** gọi overload `ResourceBundle.getBundle(..., ResourceBundle.Control)`, Java ném `UnsupportedOperationException`. Vì vậy, để triển khai bản dịch nằm ở module riêng, dùng cơ chế `uses`/`provides` của `ResourceBundleProvider`; không bê nguyên ví dụ `Control.newBundle` dành cho classpath vào JPMS. Điều này **không có nghĩa** `ResourceBundle` hay tệp `.properties` đã lỗi thời.

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `MissingResourceException` khi gọi `getBundle` | Sai base name, sai quy tắc đặt tên SPI, thiếu `uses`/`provides`, provider chưa được resolve, file `.properties` không nằm trong output, hoặc provider luôn trả `null`. |
| `MissingResourceException` khi `getString` | Thiếu khóa ở bundle đang được chọn và chuỗi parent/fallback. |
| `ServiceConfigurationError` | Implementation không khởi tạo được, không thực hiện đúng SPI, hoặc khai báo `provides` sai; xem nguyên nhân gốc trong stack trace. |
| Provider đúng nhưng không tìm thấy resource | `toBundleName` ánh xạ sai tên/package, tệp chưa được đóng gói, hoặc truy cập tài nguyên bị hạn chế bởi module. |
| Hai module không resolve cùng lúc | Có thể gặp **split package** nếu hai module dùng chung package tài nguyên; di chuyển tài nguyên vào package thuộc riêng từng provider. |
| Locale hoặc ngôn ngữ trả về bất ngờ | Kiểm tra `Locale` truyền vào, default locale, thứ tự các bundle ứng viên và cache. |

Checklist nhanh khi tự xây module ngôn ngữ: (1) base name là một hằng thống nhất, (2) tên SPI khớp chính xác quy ước, (3) module gọi có `uses`, (4) module dịch có `provides` và implementation công khai, (5) provider module đã resolve khi chạy, (6) tài nguyên được đóng gói đúng tên UTF-8, (7) kiểm thử locale cơ bản, locale vùng, khóa thiếu và fallback.

## 6. Câu hỏi tự kiểm tra

1. Với base name `com.shop.text.Labels`, tên đầy đủ của service interface phải là gì?  
   **Đáp án:** `com.shop.text.spi.LabelsProvider`.
2. Nếu provider chỉ hỗ trợ `Locale.FRENCH`, nên trả gì khi được hỏi `Locale.JAPANESE`?  
   **Đáp án:** `null` để cơ chế tìm kiếm tiếp tục, không trả tùy tiện bản dịch tiếng Pháp.
3. Vì sao ví dụ đặt `Messages_fr.properties` ở package `demo.fr` và ghi đè `toBundleName`?  
   **Đáp án:** cho phép bản dịch nằm trong provider module độc lập, tránh split package với `demo.app` và ánh xạ đúng tài nguyên.
4. Bỏ `--add-modules demo.fr` trong lệnh chạy ví dụ có thể gây điều gì?  
   **Đáp án:** provider module có thể không được resolve; `getBundle` không tìm thấy bản dịch và có thể ném `MissingResourceException`.

## Tài liệu chính thức (API vẫn được duy trì)

- [`ResourceBundleProvider` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): quy tắc đặt tên SPI, cách khai báo `uses`/`provides` và hợp đồng `getBundle`.
- [`AbstractResourceBundleProvider` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html): format hợp lệ, ánh xạ `toBundleName` và cách tìm resource trong module provider.
- [`ResourceBundle` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): fallback, cache và khác biệt giữa named module với classpath.
- [`PropertyResourceBundle` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): mã hóa UTF-8 và xử lý file `.properties`.