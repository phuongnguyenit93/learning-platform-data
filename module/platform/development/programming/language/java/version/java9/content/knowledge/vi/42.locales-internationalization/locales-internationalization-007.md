# ResourceBundle trong mô-đun có tên và quyền truy cập tài nguyên (JPMS)

## 1. Vấn đề cần hiểu

Từ Java 9 và vẫn áp dụng trong các phiên bản Java hiện đại, **named module** (mô-đun có tên, khai báo bằng `module-info.java`) có ranh giới đóng gói tài nguyên. Một tệp `.properties` nằm trên module path không mặc nhiên được nhìn thấy bởi tất cả mã trong ứng dụng, dù các mô-đun dùng cùng class loader.

`ResourceBundle` giải quyết việc lấy thông điệp theo `Locale`; JPMS quyết định mã nào có thể tìm thấy bundle nằm trong một mô-đun. Hai câu hỏi khác nhau phải được trả lời:

1. **Ai thực hiện lời gọi?** Mã trong chính mô-đun chứa bundle hay mã của mô-đun khác?
2. **Đường truy cập nào được dùng?** `ResourceBundle.getBundle(...)` theo mô-đun gọi, `getBundle(..., Module)` theo mô-đun được chỉ định, `Module.getResourceAsStream(...)` hay cơ chế dịch vụ `ResourceBundleProvider`?

Mục tiêu: đóng gói bundle cùng mã tiêu thụ khi thích hợp; chỉ công bố đúng API hoặc tài nguyên cần chia sẻ; hiểu vì sao bundle có trên đĩa mà lookup vẫn báo không tìm thấy.

## 2. Bundle, base name và đường dẫn thực tế

Một họ bundle có thể gồm:

~~~text
demo/catalog/i18n/Labels.properties
demo/catalog/i18n/Labels_vi.properties
demo/catalog/i18n/Labels_en.properties
demo/catalog/i18n/Labels_en_US.properties
~~~

- **Base name** dùng trong Java là `demo.catalog.i18n.Labels`, không kèm `.properties` hay hậu tố ngôn ngữ.
- `Locale.forLanguageTag("vi")` tìm ứng viên phù hợp như `Labels_vi.properties`; `Locale.forLanguageTag("en-US")` ưu tiên mức cụ thể trước các mức tổng quát.
- `Labels.properties` là bundle gốc. Khóa thiếu trong bundle con có thể được tra ở chuỗi bundle cha. Nếu không có khóa ở chuỗi tìm kiếm, `getString` ném `MissingResourceException`.
- Nếu không thấy bản dịch cho locale yêu cầu, `getBundle` có thể thử locale mặc định của tiến trình trước khi dùng bundle gốc; vì vậy không được suy từ tham số `Locale` rằng bản dịch trả về nhất định đúng locale đó. Dùng `bundle.getLocale()` để kiểm tra bản thực sự được chọn.
- Trong Java hiện đại, `PropertyResourceBundle` đọc `.properties` bằng **UTF-8 mặc định** (có cơ chế thử lại ISO-8859-1 khi đầu vào không hợp lệ). Nên lưu tệp UTF-8 nhất quán, đặc biệt cho tiếng Việt.

Tên có dấu chấm trong `getBundle` được ánh xạ đến đường dẫn dùng dấu `/`. Tên mô-đun (`demo.catalog`) và package chứa bundle (`demo.catalog.i18n`) là hai khái niệm độc lập: không lấy tên mô-đun để tự ghép vào base name.

## 3. Ví dụ chạy được: bundle được dùng trong chính named module

Đây là phương án nên ưu tiên khi mô-đun sở hữu bản dịch đồng thời sở hữu API trả về thông điệp. Mô-đun khác gọi API công khai, không cần truy cập trực tiếp tệp nội bộ.

Cấu trúc dự án:

~~~text
src/
  demo.catalog/
    module-info.java
    demo/catalog/api/Texts.java
    demo/catalog/i18n/Labels.properties
    demo/catalog/i18n/Labels_vi.properties
    demo/catalog/i18n/Labels_en.properties
  demo.app/
    module-info.java
    demo/app/Main.java
~~~

`src/demo.catalog/module-info.java`:

~~~java
module demo.catalog {
    exports demo.catalog.api;
}
~~~

`src/demo.catalog/demo/catalog/api/Texts.java`:

~~~java
package demo.catalog.api;

import java.util.Locale;
import java.util.ResourceBundle;

public final class Texts {
    private Texts() {}

    public static String greeting(Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("demo.catalog.i18n.Labels", locale);
        return bundle.getString("greeting");
    }
}
~~~

Ba tệp `.properties` (UTF-8):

~~~properties
# Labels.properties
greeting=Hello (default)!
~~~

~~~properties
# Labels_vi.properties
greeting=Xin chào!
~~~

~~~properties
# Labels_en.properties
greeting=Hello!
~~~

`src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.catalog;
}
~~~

`src/demo.app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.catalog.api.Texts;
import java.util.Locale;

public class Main {
    public static void main(String[] args) {
        System.out.println(Texts.greeting(Locale.forLanguageTag("vi")));
        System.out.println(Texts.greeting(Locale.ENGLISH));
    }
}
~~~

Biên dịch (chạy từ thư mục chứa `src`; mỗi lệnh `javac` dưới đây là một dòng):

~~~bash
javac -encoding UTF-8 --module-source-path src -d mods src/demo.catalog/module-info.java src/demo.catalog/demo/catalog/api/Texts.java src/demo.app/module-info.java src/demo.app/demo/app/Main.java
mkdir -p mods/demo.catalog/demo/catalog/i18n
cp src/demo.catalog/demo/catalog/i18n/*.properties mods/demo.catalog/demo/catalog/i18n/
java --module-path mods -m demo.app/demo.app.Main
~~~

Nếu dùng Windows PowerShell, thay riêng hai lệnh `mkdir` và `cp` bằng:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.catalog/demo/catalog/i18n | Out-Null
Copy-Item src/demo.catalog/demo/catalog/i18n/*.properties mods/demo.catalog/demo/catalog/i18n/
~~~

Kết quả:

~~~text
Xin chào!
Hello!
~~~

**Vì sao chạy được?** Lệnh `ResourceBundle.getBundle(String, Locale)` được gọi từ `Texts` thuộc `demo.catalog` nên nó tìm bundle theo ngữ cảnh của chính mô-đun đó. `exports demo.catalog.api` chỉ cho phép `demo.app` dùng kiểu `Texts`. Không cần `exports` hay `opens` package chứa bản dịch chỉ để `Texts` đọc bundle thuộc cùng mô-đun.

Lưu ý đóng gói: `javac` chỉ biên dịch mã Java; tệp `.properties` phải được sao chép/đóng gói vào thư mục output hoặc JAR của **đúng mô-đun**, giữ nguyên đường dẫn package. Trong Gradle/Maven, cấu hình resources của build thay cho thao tác sao chép thủ công.

## 4. `exports`, `opens` và quyền đọc tài nguyên là ba việc khác nhau

| Tình huống | Cách truy cập phù hợp | Quy tắc cần nhớ |
| --- | --- | --- |
| Mã tự dùng bundle của mô-đun mình | `ResourceBundle.getBundle(baseName, locale)` | Tra theo caller module; thường không cần mở package bundle ra ngoài. |
| Mô-đun khác chỉ cần thông điệp | API Java được `exports`, ví dụ `Texts.greeting` | Bản dịch vẫn là chi tiết nội bộ; bên dùng khai báo `requires` mô-đun API. |
| Mô-đun khác cần lấy trực tiếp bundle của mô-đun cụ thể | `ResourceBundle.getBundle(baseName, locale, module)` | Mô-đun đích phải được resolve; việc truy cập chịu quy tắc đóng gói tài nguyên. |
| Mô-đun khác cần đọc một tệp bất kỳ | `Module.getResourceAsStream("a/b/file.txt")` | Kiểm tra package chứa tài nguyên có mở cho mô-đun gọi hay không. |
| Nhiều mô-đun cung cấp bản dịch như plugin | `ResourceBundleProvider` + `uses`/`provides` | Cơ chế dịch vụ là đường chia sẻ phù hợp cho bundle phân phối trong provider modules. |

Phân biệt các chỉ thị trong `module-info.java`:

- `exports p;` cho các mô-đun đọc mô-đun này sử dụng **kiểu public** thuộc `p` ở thời điểm biên dịch và chạy. Nó **không tự mở** `p` cho việc tra cứu tài nguyên bị đóng gói.
- `opens p;` mở `p` một cách không điều kiện cho truy cập sâu lúc chạy, đồng thời cho phép truy cập các tài nguyên của package theo quy tắc `Module.getResourceAsStream`.
- `opens p to demo.consumer;` chỉ mở cho mô-đun được chỉ định; phù hợp khi cần cấp quyền truy cập hẹp.
- `requires other.module;` tạo quan hệ đọc mô-đun, **không thay thế** `opens` của mô-đun chứa tài nguyên.

Quy tắc kỹ thuật của `Module.getResourceAsStream`: nếu đường dẫn tài nguyên nằm trong **một package thực sự thuộc named module**, caller ở mô-đun khác chỉ tìm thấy nó khi package mở ít nhất cho caller. Tệp `.class` được loại trừ khỏi sự đóng gói tài nguyên này; tài nguyên ở đường dẫn không tương ứng package thuộc mô-đun cũng không bị đóng gói theo điều kiện đó. Vì vậy, đừng coi việc đặt `.properties` vào một thư mục tùy ý là biện pháp kiểm soát quyền; muốn kiểm tra đóng gói phải xác định package của mô-đun thực tế.

**Điểm dễ nhầm:** `ClassLoader.getResourceAsStream`/`getResource` chỉ tìm tài nguyên không phải `.class` trong package của named module khi package đó được mở **không điều kiện**, kể cả trong trường hợp lời gọi xuất phát từ chính mô-đun. Muốn đọc tài nguyên theo mô-đun, hãy ưu tiên API nhận `Module` hoặc `Module.getResourceAsStream` thay vì phụ thuộc vào ClassLoader search.

## 5. Ví dụ trực tiếp giữa hai mô-đun: cần mở package cho caller

Giả sử `demo.messages` chứa `sample/pack/Labels_vi.properties` và một lớp `Marker` cùng package (để `sample.pack` thật sự là package của mô-đun).

`src/demo.messages/module-info.java`:

~~~java
module demo.messages {
    opens sample.pack to demo.consumer;
}
~~~

`src/demo.messages/sample/pack/Marker.java`:

~~~java
package sample.pack;

final class Marker {}
~~~

`src/demo.messages/sample/pack/Labels.properties`:

~~~properties
greeting=Hello
~~~

`src/demo.messages/sample/pack/Labels_vi.properties`:

~~~properties
greeting=Xin chao
~~~

`src/demo.consumer/module-info.java`:

~~~java
module demo.consumer {
    requires demo.messages;
}
~~~

`src/demo.consumer/consumer/Main.java`:

~~~java
package consumer;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        Module source = ModuleLayer.boot()
                .findModule("demo.messages")
                .orElseThrow();

        ResourceBundle bundle = ResourceBundle.getBundle(
                "sample.pack.Labels",
                Locale.forLanguageTag("vi"),
                source
        );
        System.out.println(bundle.getString("greeting"));
    }
}
~~~

Biên dịch hai mô-đun cùng lượt, sao chép tài nguyên, rồi chạy:

~~~bash
javac -encoding UTF-8 --module-source-path src -d mods src/demo.messages/module-info.java src/demo.messages/sample/pack/Marker.java src/demo.consumer/module-info.java src/demo.consumer/consumer/Main.java
mkdir -p mods/demo.messages/sample/pack
cp src/demo.messages/sample/pack/*.properties mods/demo.messages/sample/pack/
java --module-path mods -m demo.consumer/consumer.Main
~~~

Kết quả:

~~~text
Xin chao
~~~

Nếu bỏ `opens sample.pack to demo.consumer;` trong ví dụ này, lời gọi từ `demo.consumer` không nhìn thấy bundle và có thể ném `MissingResourceException`. Thêm `exports sample.pack;` **không giải quyết** quyền đọc tài nguyên đó. Nếu mã ở mô-đun khác thật sự cần gọi `getBundle(..., Module)` trực tiếp, mở đúng package cho đúng mô-đun; đừng mở toàn bộ mô-đun theo thói quen.

`ModuleLayer.boot().findModule(...)` chỉ tìm mô-đun **đã được resolve** trong boot layer. Trong ví dụ, `requires demo.messages` bảo đảm mô-đun đích có mặt; tên mô-đun chỉ xuất hiện trên module path mà chưa được resolve thì `findModule` không tự nạp nó.

Với tệp thô không dùng `ResourceBundle`, cú pháp tương ứng là:

~~~java
// Đoạn minh họa đặt trong mã của mô-đun được cấp quyền đọc.
Module source = ModuleLayer.boot().findModule("demo.messages").orElseThrow();
try (var in = source.getResourceAsStream("sample/pack/Labels_vi.properties")) {
    if (in == null) {
        throw new IllegalStateException("Resource khong duoc tim thay/truy cap");
    }
    // Đọc InputStream ở đây; try-with-resources sẽ đóng luồng.
}
~~~

`Module.getResourceAsStream` nhận **đường dẫn** dùng `/`; `ResourceBundle.getBundle` nhận **base name** dùng dấu `.`. Hai API phục vụ nhu cầu khác nhau: một bên lấy byte, một bên chọn bản dịch/locale và tra key.

## 6. Bundle nằm ở provider module khác: `ResourceBundleProvider`

Khi sản phẩm tách bản dịch ra nhiều mô-đun (ví dụ một nhà cung cấp cho mỗi ngôn ngữ), đường mở rộng chuẩn hiện nay là `java.util.spi.ResourceBundleProvider` và `java.util.spi.AbstractResourceBundleProvider`. Tên interface dịch vụ phải tuân theo quy tắc:

~~~text
baseName:       demo.i18n.Labels
service type:   demo.i18n.spi.LabelsProvider
                └─ package của baseName + ".spi."
                   + tên đơn giản "Labels" + "Provider"
~~~

Một ví dụ tối thiểu gồm ba mô-đun:

**Mô-đun API `demo.api`:**

~~~java
// module-info.java
module demo.api {
    exports demo.i18n.spi;
}
~~~

~~~java
// demo/i18n/spi/LabelsProvider.java
package demo.i18n.spi;

import java.util.spi.ResourceBundleProvider;

public interface LabelsProvider extends ResourceBundleProvider {}
~~~

**Mô-đun bản dịch `demo.vi`:**

~~~java
// module-info.java
module demo.vi {
    requires demo.api;
    provides demo.i18n.spi.LabelsProvider
            with demo.vi.VietnameseLabels;
}
~~~

~~~java
// demo/vi/VietnameseLabels.java
package demo.vi;

import demo.i18n.spi.LabelsProvider;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

public final class VietnameseLabels
        extends AbstractResourceBundleProvider
        implements LabelsProvider {

    public VietnameseLabels() {
        super("java.properties");
    }

    @Override
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!"vi".equals(locale.getLanguage())) {
            return null; // Provider này không hỗ trợ locale khác.
        }
        return super.getBundle(baseName, locale);
    }
}
~~~

Tệp `demo.vi/demo/i18n/Labels_vi.properties`:

~~~properties
hello=Xin chào từ nhà cung cấp!
~~~

**Mô-đun dùng bản dịch `demo.client`:**

~~~java
// module-info.java
module demo.client {
    requires demo.api;
    uses demo.i18n.spi.LabelsProvider;
}
~~~

~~~java
// demo/client/Main.java
package demo.client;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "demo.i18n.Labels", Locale.forLanguageTag("vi"));
        System.out.println(bundle.getString("hello"));
    }
}
~~~

Sắp xếp file nguồn dưới `src/<module-name>/...` đúng như các path ghi trên; biên dịch các `module-info.java` và `.java` tương ứng bằng `javac --module-source-path src -d mods ...`, rồi sao chép `Labels_vi.properties` vào `mods/demo.vi/demo/i18n/`. Chạy:

~~~bash
java --module-path mods -m demo.client/demo.client.Main
~~~

Kết quả khi provider module đã được resolve và đăng ký dịch vụ:

~~~text
Xin chào từ nhà cung cấp!
~~~

Luồng xử lý: `demo.client` khai báo `uses`, `demo.vi` khai báo `provides`; `ResourceBundle` tìm dịch vụ dựa trên đúng tên `LabelsProvider` rồi gọi `getBundle` của provider. `AbstractResourceBundleProvider` đọc bundle nằm trong **mô-đun của provider**. Một provider không phục vụ locale được yêu cầu có thể trả `null` để hệ thống thử provider khác hoặc lối tìm kiếm phù hợp.

Không cần `exports` package triển khai `demo.vi` cho client. Chọn cơ chế provider khi bản dịch là thành phần mở rộng được nạp theo dịch vụ; với các thông điệp nội bộ đơn giản, cách ở mục 3 ít cấu hình hơn.

## 7. Quy trình quyết định và lỗi thực tế

1. **Bundle thuộc cùng mô-đun với code gọi?** Dùng `ResourceBundle.getBundle(baseName, locale)`. Xác minh base name và nơi build đã chép `.properties`.
2. **Bên ngoài chỉ cần kết quả đã dịch?** Expose một API public hẹp qua `exports`; giữ bundle nội bộ như `Texts` trong mục 3.
3. **Bên ngoài bắt buộc phải đọc bundle/tệp trực tiếp?** Có thể dùng `getBundle(..., Module)` hoặc `Module.getResourceAsStream`; xác minh target module được resolve và package được mở cho caller nếu tài nguyên bị đóng gói. Tránh `opens` rộng nếu chỉ một consumer cần quyền.
4. **Các gói bản dịch đến từ module nhà cung cấp độc lập?** Thiết kế service interface theo quy tắc `<base-package>.spi.<BaseName>Provider`; thêm `uses` ở consumer, `provides` ở provider và kiểm tra service resolution khi chạy.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `MissingResourceException` dù có tệp nguồn | Build không copy `.properties`, sai base name, sai module, package bị đóng gói | Kiểm tra JAR/mods, tên và đường dẫn chính xác; kiểm tra `opens` nếu đọc từ ngoài. |
| `getString("x")` báo thiếu khóa | Không có `x` ở bundle được chọn và chuỗi cha | Giữ bộ key tương thích giữa ngôn ngữ; thêm key vào bundle gốc. |
| Hiển thị nhầm ngôn ngữ | Có fallback sang locale mặc định | Ghi log `bundle.getLocale()` và bổ sung bản dịch cần thiết. |
| `ClassLoader.getResourceAsStream(...)` trả `null` | Tài nguyên thuộc package named module chưa mở không điều kiện | Dùng `Module.getResourceAsStream`/`ResourceBundle` đúng ngữ cảnh; không tự mở package rộng chỉ để chiều ClassLoader. |
| Có `requires`/`exports` nhưng vẫn không thấy tài nguyên | Đọc module khác không đồng nghĩa được quyền mở package | Phân biệt `requires`, `exports`, `opens`; thêm `opens p to consumer` khi cần. |
| Provider không được gọi | Sai tên interface theo baseName, thiếu `uses`/`provides` hoặc provider chưa được resolve | Kiểm tra module descriptor và module path; thử một test khởi chạy thật. |
| Có ý định dùng `ResourceBundle.Control` bên trong named module | Các overload `getBundle(..., Control)` không hỗ trợ từ named module, ném `UnsupportedOperationException` | Dùng các overload nhận `Module` hoặc mô hình `ResourceBundleProvider` phù hợp. |

**Về quyền truy cập:** bundle thông báo UI không nên chứa bí mật. `opens` là quyết định về khả năng nhìn thấy package/tài nguyên lúc chạy, không phải cơ chế mã hóa hoặc kiểm soát danh tính người dùng. Không sử dụng `--add-opens` như cấu hình cố định thay cho việc thiết kế API/package đúng; đó là công cụ điều chỉnh môi trường chạy, không sửa mô hình sở hữu tài nguyên.

**Về cache:** `ResourceBundle` có cache. Thay tệp `.properties` trên đĩa trong tiến trình đang chạy không đồng nghĩa lời gọi kế tiếp sẽ nạp nội dung mới; nên kiểm thử bằng một lần khởi chạy mới khi kiểm chứng bản dịch đã đóng gói, hoặc xây cơ chế cập nhật có kiểm soát nếu thực sự cần thay đổi tại runtime.

## 8. Tự kiểm tra kiến thức

- Nếu `demo.app` gọi `Texts.greeting(...)` thành công, liệu `demo.app` có đọc được `demo.catalog.i18n.Labels` trực tiếp? **Không suy ra được**: quyền dùng API public không cấp quyền mở package tài nguyên.
- Nếu `ResourceBundle.getBundle(..., Module)` trả `MissingResourceException`, có chắc file không tồn tại? **Không**: file có thể bị đóng gói, mô-đun chưa được resolve, tên base sai hoặc resource chưa được build đóng gói.
- Khi cần hỗ trợ một ngôn ngữ độc lập ở module khác, chọn `exports` package bundle hay `ResourceBundleProvider`? **Ưu tiên provider** khi đó thực sự là kiến trúc plugin bản dịch; `exports` không thay thế cấu hình dịch vụ.
- Khi cần in tiếng Việt, có phải chuyển mọi ký tự thành `\uXXXX`? **Không**: nguồn `.properties` UTF-8 là cách dùng hiện hành.

## Tài liệu API chính thức

- [`ResourceBundle` — Resource Bundles and Named Modules](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.html)
- [`Module.getResourceAsStream` — quy tắc đóng gói tài nguyên](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [`ClassLoader` — điều kiện mở package cho resource lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html)
- [`ResourceBundleProvider` — SPI cho bundle trong provider modules](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [`AbstractResourceBundleProvider` — hỗ trợ nạp bundle nội bộ provider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html)
- [`PropertyResourceBundle` — quy tắc mã hóa tệp properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PropertyResourceBundle.html)