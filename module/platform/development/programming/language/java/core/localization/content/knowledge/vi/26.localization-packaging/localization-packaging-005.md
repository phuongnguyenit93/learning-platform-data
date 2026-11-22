# Giới hạn ResourceBundle.Control trong named module

`ResourceBundle` là cơ chế Java tiêu chuẩn để tìm thông điệp và tài nguyên theo `Locale`. Trước Java Platform Module System (JPMS), một ứng dụng thường chạy trên **classpath** và có thể tùy biến quá trình tìm bundle bằng `ResourceBundle.Control`: thứ tự locale dự phòng, định dạng file, thời gian cache, reload hay logic tìm bundle.

Kể từ Java 9, một ứng dụng có thể được triển khai trong **named module** bằng `module-info.java`. Đây là điểm thay đổi quan trọng:

> **Trong named module, các overload `ResourceBundle.getBundle(...)` có tham số `ResourceBundle.Control` không được hỗ trợ và sẽ ném `UnsupportedOperationException`.**

Quy tắc này còn áp dụng khi tham số `Control` chỉ là một đối tượng mặc định lấy từ `ResourceBundle.Control.getControl(...)`; không cần subclass đặc biệt mới phát sinh lỗi. Vì thế việc lấy mã nguồn đang chạy trên classpath rồi chỉ thêm `module-info.java` có thể làm đoạn tùy biến resource bundle bị hỏng, dù file `.properties` vẫn tồn tại.

Hướng đi đúng tùy bài toán:
- Nếu bundle nằm **trong cùng named module** và dùng định dạng chuẩn, gọi overload **không nhận `Control`**, như `ResourceBundle.getBundle(baseName, locale)`.
- Nếu cần bundle được cung cấp **qua nhiều named modules**, xem cơ chế **`ResourceBundleProvider`**, `ServiceLoader` và các chỉ thị `uses`/`provides` trong `module-info.java`.
- Nếu cần đọc bundle thuộc **một module chỉ định**, tìm hiểu `ResourceBundle.getBundle(baseName, locale, Module)` và quy tắc đóng gói/mở package.
- Nếu cần tùy biến định dạng không chuẩn, provider có thể **tự tải nội dung** hoặc sử dụng `AbstractResourceBundleProvider` cho các định dạng `java.class` / `java.properties` được hỗ trợ; đừng giả định `Control` sẽ hoạt động trở lại.

Bài học này tập trung vào **giới hạn của `ResourceBundle.Control` trong named module**, giải thích nguyên nhân kiến trúc, cách phát hiện, API thay thế, ví dụ Java 17+ và checklist migration để tránh mất localization trong dự án modular.

## 1. Bối cảnh: `ResourceBundle` và `Control` giải quyết những vấn đề gì?

Một bundle thông thường gồm những file:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
Messages_fr.properties
~~~

Mỗi file lưu key/value tương ứng ngôn ngữ:

~~~properties
greeting=Hello
goodbye=Goodbye
~~~

Chương trình yêu cầu bundle theo locale:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", Locale.ENGLISH);

System.out.println(bundle.getString("greeting"));
~~~

Đây là **snippet trong phương thức**, cần import `java.util.ResourceBundle` và `java.util.Locale`. `getBundle` tìm bundle theo base name, locale, môi trường module/class loader và chính sách fallback; nó không dịch văn bản tự động.

Trong ứng dụng không modular hoặc trên classpath, `ResourceBundle.Control` từng được dùng để can thiệp:
- `getFormats`: danh sách định dạng sẽ thử, ví dụ `java.class` hoặc `java.properties`.
- `getCandidateLocales`: các locale candidate cần xét và thứ tự.
- `getFallbackLocale`: locale dự phòng khi chưa tìm được bundle phù hợp.
- `getTimeToLive` và `needsReload`: chính sách cache và reload.
- `newBundle`: cơ chế tạo bundle, có thể từ định dạng không chuẩn như XML.

Đó là công cụ **tùy biến cơ chế tìm/tạo bundle**, không phải lớp chứa văn bản dịch. Chuyển ứng dụng sang JPMS cần xem lại cách tùy biến này.

## 2. Named module, unnamed module và classpath

| Loại triển khai | Đặc trưng | Liên quan `Control` |
| --- | --- | --- |
| **Unnamed module** | Lớp ứng dụng trên classpath, không thuộc named module | Các overload `getBundle(..., Control)` được thiết kế để hoạt động tại đây |
| **Named module** | Module có tên trong module graph, thường khai báo bằng `module-info.java` | Các overload có `Control` bị từ chối bằng `UnsupportedOperationException` |
| **Automatic module** | JAR không có module descriptor nhưng được đặt trên module path và Java suy tên module | Là named module; không được tùy tiện xem như classpath |
| **java.base** | Module hệ thống có tên chứa `ResourceBundle` và `Control` | API `Control` vẫn tồn tại, nhưng bối cảnh module gọi `getBundle` quyết định giới hạn |

Một class trong unnamed module có thể dùng một đối tượng `Control`. Khi cùng class được đóng gói vào named module, lời gọi có tham số `Control` trở thành trường hợp không được hỗ trợ.

**Điểm tinh tế:** “Classloader có tồn tại” không đồng nghĩa “đang chạy ở unnamed module”. Named module vẫn có class loader. Kiểm tra `getClass().getClassLoader() != null` không xác định chế độ sử dụng `ResourceBundle.Control`.

Có thể kiểm tra module thực của class đang gọi:

~~~java
Module module = MyApp.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

Đây là snippet, `MyApp` là class ứng dụng. Với named module `demo.app`, `isNamed()` trả `true` và `getName()` là `demo.app`; với class thông thường trên classpath, module thường là unnamed, có `isNamed() == false`.

## 3. API nào bị giới hạn?

Hai overload quan trọng:

~~~java
ResourceBundle.getBundle(
        String baseName,
        Locale targetLocale,
        ResourceBundle.Control control);

ResourceBundle.getBundle(
        String baseName,
        Locale targetLocale,
        ClassLoader loader,
        ResourceBundle.Control control);
~~~

Đây là chữ ký phương thức minh họa từ Java API, không phải các lời gọi Java hợp lệ nguyên văn; khi dùng, phải truyền **giá trị biến**, không phải tên kiểu.

Trong Java 17, nếu được **gọi từ named module**, các overload nhận `ResourceBundle.Control` sẽ ném `UnsupportedOperationException`. Đừng chỉ kiểm tra một overload có ba tham số rồi thử overload bốn tham số để “lách” hạn chế: cả hai đều nhận `Control`.

Những overload sau **không có `Control` và vẫn được hỗ trợ theo hợp đồng riêng**:

~~~java
ResourceBundle.getBundle(baseName);
ResourceBundle.getBundle(baseName, locale);
ResourceBundle.getBundle(baseName, locale, loader);
ResourceBundle.getBundle(baseName, module);
ResourceBundle.getBundle(baseName, locale, module);
~~~

Tuy nhiên “được hỗ trợ” không đồng nghĩa mọi overload tìm ra đúng bundle. **Base name, caller module, loader/module được chỉ định, exports/opens và cách triển khai provider** vẫn ảnh hưởng việc tìm tài nguyên.

## 4. Đừng nhầm `UnsupportedOperationException` với `MissingResourceException`

Hai lỗi phản ánh hai vấn đề khác nhau:

| Ngoại lệ | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` | Gọi overload `getBundle` nhận `Control` từ named module | Đổi chiến lược tải bundle/API; không chỉ sửa tên file |
| `MissingResourceException` | Không tìm thấy bundle hoặc key phù hợp theo quy tắc tra cứu | Kiểm tra base name, locale, đường dẫn, module encapsulation, provider |
| `IllegalArgumentException` | Tùy trường hợp, `Control`/candidate locales không hợp lệ khi được phép dùng | Xem triển khai `Control` |
| `NullPointerException` | Truyền tham số bắt buộc là `null` | Kiểm tra đầu vào theo Javadoc |

Giả sử module có `Messages_fr.properties` hoàn toàn hợp lệ, nhưng code gọi:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_DEFAULT);

ResourceBundle bundle =
        ResourceBundle.getBundle("demo.app.Messages",
                Locale.FRENCH, control);
~~~

Ở **named module**, lỗi xảy ra **trước khi cần suy luận tài nguyên tồn tại hay không**: chính overload có `Control` là trường hợp không được hỗ trợ.

**Không “sửa” bằng cách tạo thêm `Messages.properties` hoặc thay đường dẫn** nếu stack trace ghi `UnsupportedOperationException` từ overload có Control; cần sửa API trước.

## 5. Ví dụ đầy đủ: một named module có bundle trong cùng module

Giả sử cấu trúc dự án:

~~~text
src/
└── demo.app/
    ├── module-info.java
    └── demo/
        └── app/
            ├── Main.java
            ├── Messages.properties
            └── Messages_fr.properties
~~~

**`src/demo.app/module-info.java`**:

~~~java
module demo.app {
}
~~~

**`src/demo.app/demo/app/Main.java`**:

~~~java
package demo.app;

import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                Main.class.getModule().getName());

        ResourceBundle french = ResourceBundle.getBundle(
                "demo.app.Messages", Locale.FRENCH);

        System.out.println(french.getString("greeting"));

        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        try {
            ResourceBundle.getBundle(
                    "demo.app.Messages", Locale.FRENCH, control);
        } catch (UnsupportedOperationException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

**`src/demo.app/demo/app/Messages.properties`**:

~~~properties
greeting=Hello
~~~

**`src/demo.app/demo/app/Messages_fr.properties`**:

~~~properties
greeting=Bonjour
~~~

Trên môi trường shell có `javac`, `java` và `cp` (Linux/macOS), từ thư mục chứa `src`:

~~~bash
javac --module-source-path src -d out -m demo.app
cp src/demo.app/demo/app/Messages*.properties out/demo.app/demo/app/
java --module-path out -m demo.app/demo.app.Main
~~~

**Lưu ý:** `javac` biên dịch source `.java` nhưng không tự copy file `.properties` vào output trong quy trình này. Vì vậy lệnh `cp` là phần thiết yếu; khi dùng Maven/Gradle, cấu hình resource packaging tương ứng. Trên Windows/PowerShell có thể dùng `Copy-Item` thay `cp`.

Kết quả dự kiến với JDK 17+:

~~~text
demo.app
Bonjour
UnsupportedOperationException
~~~

Hai lời gọi thực hiện trên cùng bundle name và locale, nhưng kết quả khác nhau do **overload có Control**. `ResourceBundle.getBundle(baseName, locale)` đọc bundle chuẩn nằm trong cùng module, còn `getBundle(baseName, locale, control)` bị chặn do ngữ cảnh named module.

Trong ví dụ, chỉ có một module, không cần `opens` hay `exports` cho một consumer bên ngoài vì chính code **bên trong module** truy xuất resource của mình. Quy tắc truy cập thay đổi khi tài nguyên nằm trong module khác.

## 6. Classpath có thể chạy cùng cú pháp `Control`

Nếu dùng `ResourceBundle.Control` từ unnamed module (classpath), API vẫn có giá trị, đặc biệt để hỗ trợ format, fallback hoặc TTL không mặc định.

Một chương trình chạy độc lập trên classpath:

**`ClasspathControlDemo.java`**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class ClasspathControlDemo {
    public static void main(String[] args) {
        System.out.println(
                ClasspathControlDemo.class
                        .getModule().isNamed());

        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        System.out.println(control.getFormats("Messages"));
        System.out.println(control.getCandidateLocales(
                "Messages", Locale.forLanguageTag("fr-CA")));
    }
}
~~~

Biên dịch và chạy trên classpath (không tạo `module-info.java`):

~~~bash
javac ClasspathControlDemo.java
java -cp . ClasspathControlDemo
~~~

Kết quả với JDK 17:

~~~text
false
[java.class, java.properties]
[fr_CA, fr, ]
~~~

`Control` tồn tại và các phương thức `getFormats`/`getCandidateLocales` vẫn có thể được gọi. **Điều bị giới hạn là cách đưa `Control` vào một `ResourceBundle.getBundle` được gọi từ named module**, không phải việc class `ResourceBundle.Control` đã bị xóa khỏi JDK.

Ở classpath, nếu gọi `getBundle(..., control)` mà không có bundle tương ứng, vẫn có thể nhận `MissingResourceException` theo quy tắc thông thường. Đừng diễn giải rằng Control sẽ luôn tìm ra resource.

## 7. Vì sao JPMS thay đổi chiến lược tìm bundle?

JPMS đưa ra **module graph**, **encapsulation** và **service binding**:
- Mỗi named module định nghĩa những package mà code bên ngoài được phép truy cập.
- Resource trong package của named module có thể bị **đóng gói** theo quy tắc `Module.getResourceAsStream` và cơ chế tìm resource của `ResourceBundle`.
- Classpath search toàn cục không còn là mô hình duy nhất cho tài nguyên.
- Với những bundle được đóng gói ở module riêng, `ResourceBundleProvider` + `ServiceLoader` là hướng mở rộng tích hợp với module system.

Một subclass của `ResourceBundle.Control` thường can thiệp trực tiếp cách xây tên resource, chọn loader hoặc đọc nguồn tài nguyên. Điều này không thay thế một cách tương đương các quy tắc **module visibility** và **service provider discovery**.

**Đừng cố giải quyết bằng một custom ClassLoader để lách module encapsulation.** Ngoài tính mong manh, việc truy xuất resource cần tuân theo hợp đồng và quyền truy cập của JPMS.

Khi migration, hãy xác định trước **bundle thuộc cùng module** hay **được cung cấp bởi module khác**; cách giải quyết khác nhau.

## 8. Trường hợp đơn giản: bỏ `Control`, giữ bundle chuẩn cùng module

Trước khi module hóa, code có thể dùng:

~~~java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", locale, control);
~~~

Đây là snippet, `locale` đã tồn tại. `FORMAT_PROPERTIES` chỉ định tìm định dạng `java.properties` trong đường tra cứu có Control. Khi mã trên chuyển sang named module, overload có Control không hợp lệ.

Nếu chương trình chỉ có file `.properties` chuẩn và **không cần behavior tùy chỉnh**, cách viết mới thường là:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", locale);
~~~

Phải đảm bảo resource được đóng gói đúng trong **module chứa caller** hoặc được tìm theo quy tắc có hiệu lực; nếu trong module khác, cần xử lý module/package hoặc provider.

**Không tuyên bố bỏ Control luôn giữ nguyên mọi hành vi**. Nếu trước đó cố tình chỉ tìm `java.properties`, tùy biến locale candidates, fallback hoặc TTL, cần phân tích khác biệt của thuật toán mặc định. Việc xóa tham số chỉ là giải pháp đúng cho trường hợp không thực sự phụ thuộc custom Control.

## 9. Các overload với `Module` trong Java 9+

Một overload có thể chỉ rõ module dùng để tìm bundle:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", Locale.FRENCH, targetModule);
~~~

Đây là snippet; `targetModule` là đối tượng `Module` đã xác định (ví dụ `SomeClass.class.getModule()`). Nó **không nhận Control**.

Một cách sử dụng trong class thuộc module mong muốn:

~~~java
Module mine = MyApp.class.getModule();

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.app.Messages", Locale.FRENCH, mine);
~~~

Đây là snippet; `MyApp` là class thuộc module tương ứng.

**Giới hạn cần nhớ:** `Module` không tự mở mọi package. Với bundle ở module khác, cần bảo đảm resource có thể truy cập qua hợp đồng module encapsulation, hoặc dùng provider service theo thiết kế. Chọn overload nhận `Module` **không cho phép** đưa `Control` trở lại.

Đặc biệt, overload `getBundle(baseName, locale, ClassLoader)` có những quy tắc riêng khi caller named module và class loader trùng loader của caller; không nên giả định nó luôn mô phỏng hoạt động của classpath. Khi biết chính xác module cần truy cập, overload nhận `Module` giúp thể hiện ý định rõ ràng hơn.

## 10. `exports` khác `opens` trong module-info

Hai directive thường bị nhầm:

- **`exports p;`:** xuất package để module khác truy cập **kiểu public** khi quan hệ module hợp lệ.
- **`opens p;`:** mở package cho cơ chế **deep reflection/resource encapsulation** theo các quy tắc có liên quan, bao gồm những tình huống truy xuất resource trong package từ module khác.

Một file `.properties` thường nằm trong đường dẫn phản ánh package:

~~~text
demo/app/Messages_fr.properties
~~~

Nếu code của **module khác** cần tải tài nguyên đóng gói trong package của named module, việc chỉ `exports` không đảm bảo mọi cách đọc resource sẽ hoạt động. `opens` có thể cần thiết theo quy tắc `Module.getResourceAsStream` và ResourceBundle.

Ví dụ mô tả ý tưởng trong `module-info.java`:

~~~java
module demo.resources {
    opens demo.resources.i18n;
}
~~~

Đây là **ví dụ directive**; package `demo.resources.i18n` phải thuộc module và đường dẫn file được đóng gói đúng. Không nên mở toàn bộ module bằng `open module` chỉ để sửa một bundle, nếu chỉ cần mở một package được kiểm soát.

**Quan trọng:** `opens` không làm overload `ResourceBundle.getBundle(..., Control)` trở thành hợp lệ. Nó giải quyết **khả năng nhìn thấy tài nguyên**, trong khi UOE xảy ra vì **API Control không được hỗ trợ trong named module**.

## 11. `ResourceBundleControlProvider` cũng bị bỏ qua trong named module

Java còn có SPI:

~~~java
java.util.spi.ResourceBundleControlProvider
~~~

Nó cho phép cung cấp `ResourceBundle.Control` để thay đổi hành vi mặc định khi client gọi overload `getBundle` không truyền Control trong những ngữ cảnh hỗ trợ.

Nhưng tài liệu `ResourceBundle` Java 17 xác nhận:

**Các implementation của `ResourceBundleControlProvider` bị bỏ qua đối với named modules.**

Vì vậy cách khắc phục sau **không đáng tin và không được hỗ trợ**:

~~~text
Bỏ tham số Control trực tiếp khỏi getBundle(...)
    ↓
Đăng ký ResourceBundleControlProvider
    ↓
Mong provider này áp custom Control cho named module
~~~

Không có “đường vòng” như vậy. `ResourceBundleControlProvider` và `ResourceBundleProvider` là **hai SPI khác nhau**:

| SPI | Mục tiêu | Named modules |
| --- | --- | --- |
| `ResourceBundleControlProvider` | Cấp custom `ResourceBundle.Control` cho lookup | Bị bỏ qua trong named modules |
| `ResourceBundleProvider` | Cung cấp `ResourceBundle` thông qua service discovery | Là hướng hỗ trợ named modules |

Đừng nhầm hậu tố tên `ControlProvider` và `Provider` rồi cấu hình `provides` nhầm interface.

## 12. `ResourceBundleProvider` là cơ chế thay thế phù hợp

Interface chuẩn:

~~~java
java.util.spi.ResourceBundleProvider
~~~

Nó định nghĩa:

~~~java
ResourceBundle getBundle(String baseName, Locale locale);
~~~

Một provider có thể:
- trả một `ResourceBundle` phù hợp hoặc `null` nếu không hỗ trợ baseName/locale;
- được công bố bằng `provides ... with ...` trong module chứa implementation;
- được module tiêu thụ khai báo bằng `uses ...`;
- triển khai logic tải bundle theo định dạng chuẩn hoặc định dạng riêng.

`ResourceBundle.getBundle` sẽ dùng cơ chế tìm provider qua `ServiceLoader` theo quy tắc JPMS.

**Điểm dễ sai:** `ResourceBundleProvider` không có nghĩa chỉ cần `implements ResourceBundleProvider` bất kỳ và xong. Java quy định **tên service type theo base name**:
- Base name `com.example.app.Messages`;
- Service interface phải có tên `com.example.app.spi.MessagesProvider`.

Công thức:

~~~text
<package của baseName>.spi.<simple name của baseName>Provider
~~~

Tức `Messages` trong `com.example.app` tương ứng `com.example.app.spi.MessagesProvider`. Đây là một **service type cụ thể**, không phải chỉ dùng chung mỗi interface `java.util.spi.ResourceBundleProvider` trong `module-info.java`.

## 13. Ví dụ khai báo interface service đúng quy tắc

Giả sử base name:

~~~text
com.example.app.Messages
~~~

**File `com/example/app/spi/MessagesProvider.java`**:

~~~java
package com.example.app.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {
}
~~~

Với module tiêu thụ, **`module-info.java`** cần khai báo:

~~~java
module com.example.app {
    exports com.example.app.spi;
    uses com.example.app.spi.MessagesProvider;
}
~~~

`exports` được dùng để module triển khai provider có thể tham chiếu interface service public. `uses` tuyên bố module tiêu thụ dùng service đó; đây là thành phần quan trọng để `ResourceBundle.getBundle` tìm provider trong module graph.

Ở phía implementation, một module khác cần:

~~~java
module com.example.translation {
    requires com.example.app;

    provides com.example.app.spi.MessagesProvider
        with com.example.translation.MessagesProviderImpl;
}
~~~

**Lưu ý:** Đây là những đoạn của cấu trúc dự án đa module, không phải toàn bộ chương trình độc lập. Class `MessagesProviderImpl` phải tồn tại, implement đúng interface và được đóng gói trong module provider. Nội dung implementation sẽ được minh họa ở phần tiếp.

Không tự khai báo `provides java.util.spi.ResourceBundleProvider with ...` khi service type thực tế mà `ResourceBundle.getBundle` đang tra là `com.example.app.spi.MessagesProvider`.

## 14. `AbstractResourceBundleProvider` giúp triển khai provider chuẩn

Java có class:

~~~java
java.util.spi.AbstractResourceBundleProvider
~~~

Class này triển khai cơ chế cơ bản cho `ResourceBundleProvider` với các định dạng **`java.class`** và **`java.properties`**. Các constructor hỗ trợ danh sách định dạng được cho phép; chẳng hạn:

~~~java
super("java.properties");
~~~

Trong implementation class, điều đó yêu cầu provider chỉ tìm bundle định dạng properties.

Ví dụ theo cấu trúc nhiều module:

**`com/example/translation/MessagesProviderImpl.java`**:

~~~java
package com.example.translation;

import java.util.Locale;
import java.util.ResourceBundle;
import java.util.spi.AbstractResourceBundleProvider;

import com.example.app.spi.MessagesProvider;

public final class MessagesProviderImpl
        extends AbstractResourceBundleProvider
        implements MessagesProvider {

    public MessagesProviderImpl() {
        super("java.properties");
    }

    @Override
    public ResourceBundle getBundle(
            String baseName, Locale locale) {

        if (!"com.example.app.Messages".equals(baseName)
                || !Locale.FRENCH.equals(locale)) {
            return null;
        }

        return super.getBundle(baseName, locale);
    }

    @Override
    protected String toBundleName(
            String baseName, Locale locale) {

        return "com.example.translation.Messages_"
                + locale.getLanguage();
    }
}
~~~

Bundle `Messages_fr.properties` có thể được đóng gói trong module provider dưới đường dẫn tương ứng:

~~~text
com/example/translation/Messages_fr.properties
~~~

Nội dung minh họa:

~~~properties
greeting=Bonjour
~~~

**Những điều phải đúng khi tích hợp:**
1. Service interface tuân đúng quy tắc tên theo baseName.
2. Consumer module có `uses` và provider module có `provides`.
3. Provider module được **resolved** vào module graph khi chạy.
4. Resource được **đóng gói** tại đường dẫn mà `toBundleName` trả về.
5. Provider trả `null` cho locale/baseName không hỗ trợ, không bịa bundle cho mọi locale.
6. Chạy kiểm thử trên module path thực tế, không chỉ classpath.

`AbstractResourceBundleProvider` chỉ hỗ trợ định dạng đã nêu trong API. Nếu cần XML/JSON hoặc nguồn từ database, implementation có thể tự tạo `ResourceBundle` thích hợp; class trừu tượng **không tự biết** cách đọc mọi định dạng đặc biệt.

## 15. Đường đi của một lời gọi dùng SPI

Một chuỗi lookup mẫu:

~~~text
Consumer named module: com.example.app
    |
    | ResourceBundle.getBundle(
    |    "com.example.app.Messages", Locale.FRENCH)
    v
ResourceBundle suy ra service type:
    com.example.app.spi.MessagesProvider
    |
    | module com.example.app: uses ...
    v
ServiceLoader tìm provider module đã resolved
    |
    | module com.example.translation: provides ...
    v
MessagesProviderImpl.getBundle(baseName, locale)
    |
    +-- có bundle -> ResourceBundle
    |
    +-- không hỗ trợ -> null
~~~

Đây là **sơ đồ luồng**, không phải một lệnh Java.

Việc provider được triển khai trong module khác không có nghĩa mọi resource được “export” thành class public. `ResourceBundleProvider` là **giao diện truy xuất có kiểm soát**; provider có thể tự lấy tài nguyên trong module của nó rồi cung cấp thông điệp cho caller.

Đối với những hệ thống có nhiều module cung cấp locale khác nhau, cần thiết kế package resource tránh **split packages** giữa các named modules. Có thể nhóm resource theo ngôn ngữ/vùng hoặc dùng `toBundleName` để ánh xạ sang package riêng của module provider.

## 16. Tại sao phải tránh split packages?

JPMS không hỗ trợ tùy tiện việc **nhiều named modules trong cùng layer chứa cùng một package**. Đây là điểm khác với nhiều tổ chức JAR trước Java 9.

Giả sử hai module đều cố đặt class/resource dưới package:

~~~text
com/example/app/i18n/
~~~

Nếu chúng còn đưa các class của cùng package vào những module khác nhau, cấu trúc có thể gây xung đột/split package. Dù chỉ dùng resource, quy tắc package và lookup vẫn cần xem xét cẩn thận.

Cách tổ chức thường dễ kiểm soát hơn:

~~~text
Provider tiếng Pháp:
    com/example/translation/fr/Messages_fr.properties

Provider tiếng Nhật:
    com/example/translation/ja/Messages_ja.properties
~~~

Mỗi provider có thể tùy chỉnh `toBundleName` để ánh xạ baseName logic sang vị trí thực tế **không bị trùng package giữa named modules**. Không tự chia module theo locale mà không kiểm tra cấu trúc package và cơ chế service discovery.

Nếu chỉ một module ứng dụng chứa tất cả bundle `Messages_en.properties`, `Messages_fr.properties`, `Messages_vi.properties`, không nhất thiết phải dùng SPI để phân tán tài nguyên. Giữ thiết kế đơn giản khi nhu cầu chưa đòi provider.

## 17. Không có thay thế 1:1 cho mọi callback của `Control`

Một người dùng `Control` cũ thường viết:

~~~java
class MyControl extends ResourceBundle.Control {
    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return 5_000;
    }
}
~~~

Đây là **đoạn class minh họa**, cần import `ResourceBundle` và `Locale` hoặc dùng tên đầy đủ. `getTimeToLive` cho biết TTL theo mili giây trong hệ thống lookup Control, không phải lời hứa mọi bundle tự refresh sau đúng 5 giây.

Khi chuyển sang named modules, `ResourceBundleProvider` không có một phương thức cùng chữ ký `getTimeToLive`. Nó là **mô hình cung cấp bundle**, chứ không phải bản sao từng callback của Control.

Bảng đối chiếu:

| Tùy biến `Control` cũ | Hướng thiết kế lại trong named module |
| --- | --- |
| `getFormats` | Bundle chuẩn trong module hoặc provider chọn cách load |
| `newBundle` | `ResourceBundleProvider` tự tạo/trả bundle |
| `toBundleName` | Override `AbstractResourceBundleProvider.toBundleName` nếu dùng class này |
| `getCandidateLocales` | Thiết kế hỗ trợ locale/fallback theo hợp đồng provider/module; không giả định được copy nguyên callback |
| `getFallbackLocale` | Quy định locale fallback và test behavior thực tế; có thể xử lý ở tầng ứng dụng/provider |
| `getTimeToLive` | Quản lý cache/phiên bản/reload theo thiết kế module/ứng dụng, không trông chờ TTL Control |
| `needsReload` | Cơ chế invalidation/reload có chủ đích ở ứng dụng hoặc provider |

**Không hứa `AbstractResourceBundleProvider` hỗ trợ XML chỉ vì `Control.newBundle` đã từng đọc XML**. `AbstractResourceBundleProvider` mặc định chỉ làm việc với những format chuẩn mà constructor cho phép; muốn format khác phải có implementation riêng.

## 18. Cache: `clearCache` không biến named module thành Control

`ResourceBundle` có cache mặc định. Có các API như:

~~~java
ResourceBundle.clearCache();
ResourceBundle.clearCache(loader);
~~~

Đây là snippet với biến `loader` có kiểu `ClassLoader`. Nhưng xóa cache **không thay thế** cơ chế `Control.getTimeToLive`, không sửa lỗi `UnsupportedOperationException` và không bảo đảm mọi nguồn tài nguyên ngoài (database, file config, remote store) được reload ngay theo ý muốn.

Một hệ thống dịch động nên xác định:
- Ai sở hữu source of truth của thông điệp?
- Bản dịch được **version** như thế nào?
- Cache nằm trong `ResourceBundle`, provider hay service bên ngoài?
- Khi bản dịch đổi, ứng dụng lấy cấu hình mới theo sự kiện, TTL hay deploy mới?
- Có cần tránh nhiều request nhìn thấy bản dịch khác nhau trong cùng transaction?

`ResourceBundle.clearCache()` theo Javadoc còn có **phạm vi cache gắn với caller module**. Vì vậy không tự suy luận một lệnh clearCache từ module bất kỳ có thể xóa mọi tài nguyên của mọi provider/module.

## 19. Exception không nói file `.properties` hỏng

Một tình huống migration phổ biến:

~~~text
Trước:
    app.jar trên classpath
    ResourceBundle.getBundle(baseName, locale, control)
    -> tải thành công

Sau:
    thêm module-info.java
    đưa lên module path
    dùng nguyên getBundle(..., control)
    -> UnsupportedOperationException
~~~

Không nên lập tức:
- thay charset của file `.properties`;
- đổi tên `Messages_fr.properties`;
- xóa cache;
- thêm `opens` vô điều kiện;
- chuyển tất cả dữ liệu dịch về một file khác;
- tải thư viện Unicode mới.

Các bước trên không xử lý nguyên nhân đầu tiên là **overload nhận Control bị cấm** trong named module. Chỉ sau khi bỏ hoặc thay cơ chế Control, nếu xuất hiện `MissingResourceException`, mới kiểm tra visibility/resource packaging.

Ngoài ra, lỗi trong việc dùng `ClassLoader` để tìm tài nguyên có thể là vấn đề **module encapsulation** khác. Hãy xem stack trace và chữ ký overload bị gọi, đừng gộp mọi lỗi thành “ResourceBundle không hỗ trợ module”.

## 20. Diagnostic checklist cho lỗi tải bundle

Khi có lỗi, xác minh theo thứ tự:

1. **Caller nằm trong module nào?** Kiểm tra `Caller.class.getModule().isNamed()` và `getName()`.
2. **Có dùng overload `getBundle` nhận `Control` không?** Nếu có từ named module, dự kiến `UnsupportedOperationException`.
3. **Có dùng `ResourceBundleControlProvider` cũ không?** Named modules bỏ qua provider loại này.
4. **Bundle ở cùng module hay module khác?** Nếu cùng module, thử API không Control và xác minh resource đã được đóng gói.
5. **Base name có đúng package/path không?** `com.example.app.Messages` tương ứng file `com/example/app/Messages_fr.properties` trong định dạng chuẩn.
6. **Có sai locale hoặc key không?** Phân biệt thiếu bundle và thiếu key.
7. **Nếu ở module khác, package có được truy xuất theo JPMS không?** Xem `opens`/resource encapsulation.
8. **Nếu qua SPI, tên service interface có đúng quy tắc không?** `package.spi.SimpleNameProvider`.
9. **Consumer đã khai báo `uses` chưa?** Provider đã khai báo `provides` chưa?
10. **Provider module đã resolved trong module graph chưa?** Không chỉ đặt JAR trên đĩa rồi suy luận chắc chắn service sẽ chạy.
11. **Provider có trả `null` cho locale đang yêu cầu không?** Kiểm tra locale candidates/fallback.
12. **Có split package giữa provider modules không?** Kiểm tra package và `toBundleName`.
13. **Tài nguyên đã được copy khi build chưa?** `javac` không tự copy `.properties` vào thư mục output.
14. **Có giả định TTL/auto reload từ Control cũ không?** Thiết kế lại quản lý phiên bản/cache.

Đây là quy trình chẩn đoán **theo từng tầng** thay vì đoán một lỗi duy nhất.

## 21. `UnsupportedOperationException` khác `MissingResourceException` trong kiểm thử

Khi unit test chạy trên classpath nhưng production chạy module path, test có thể **không tái hiện lỗi** do caller ở unnamed module trong test.

Ví dụ kịch bản:

| Môi trường | Caller module | Lời gọi `getBundle(..., Control)` |
| --- | --- | --- |
| Test dùng classpath | Unnamed | Có thể chạy được nếu resource và Control hợp lệ |
| Java modular runtime | Named | Ném `UnsupportedOperationException` |
| Test module path | Named | Tái hiện đúng giới hạn |
| Automatic module trên module path | Named | Không tự giả định như classpath |

Vì vậy trong CI:
- Có ít nhất một bài **integration test chạy trên module path**.
- Dùng `java --module-path ... -m module/name.Main` cho bài test gần môi trường production.
- Đừng chỉ chạy `java -cp ...` rồi kết luận integration ResourceBundle trong named module đã đúng.
- Kiểm tra cả trường hợp **bundle ở cùng module**, **bundle từ provider module**, **locale không hỗ trợ** và **resource bị encapsulate**.
- Với bài test cho đường lookup có Control, kỳ vọng lỗi ở named module và đường hợp lệ ở classpath nếu muốn minh họa khác biệt.

Chính **ngữ cảnh caller** là một phần hợp đồng API; đơn thuần kiểm tra resource file có tồn tại chưa đủ.

## 22. Một chương trình chẩn đoán ngữ cảnh module

Một đoạn class đơn giản, dùng được cả classpath và named module:

**`ModuleContextDemo.java`**

~~~java
public class ModuleContextDemo {
    public static void main(String[] args) {
        Module current =
                ModuleContextDemo.class.getModule();

        System.out.println(current.isNamed());
        System.out.println(current.getName());
    }
}
~~~

Biên dịch/chạy trên classpath:

~~~bash
javac ModuleContextDemo.java
java ModuleContextDemo
~~~

Kết quả:

~~~text
false
null
~~~

Trong một **named module**, kết quả sẽ đổi thành `true` và tên module đã khai báo (sau khi tổ chức class/package và build theo JPMS). Ví dụ trên giúp phân biệt runtime mode mà không phụ thuộc biến môi trường.

Tuy nhiên, đừng dùng `isNamed()` như cách “bật tắt” custom Control một cách vô thức rồi trả bundle sai. Tốt hơn là thiết kế **hai đường tương thích có kiểm thử**, hoặc migrate hoàn toàn sang API không Control/SPI nếu product xác định chạy named modules.

## 23. Thiết kế locale fallback khi không có Control

Trong ứng dụng classpath, người viết có thể từng override:

~~~java
@Override
public Locale getFallbackLocale(String baseName, Locale locale) {
    return Locale.ENGLISH;
}
~~~

Đây là **snippet của subclass `ResourceBundle.Control`**, không phải method của `ResourceBundleProvider`.

Sau migration, cần xác định:
- Bundle nào là root/default `Messages.properties`?
- Có cung cấp các biến thể `Messages_en`, `Messages_en_US`, `Messages_fr_CA` không?
- Khi locale yêu cầu chưa được hỗ trợ, muốn fallback về **root**, về **English**, hay báo lỗi?
- Fallback nên do quy tắc `ResourceBundle` mặc định, provider, hay tầng gọi quyết định?
- Nếu nhiều provider module hỗ trợ các locale khác nhau, cần tránh fallback không mong muốn làm nhận bundle của module khác.

Không tự giả định `ResourceBundleProvider` có callback `getFallbackLocale`. Cách cung cấp bundle từ provider khác Control; phải kiểm thử fallback locale và missing key trên chính module graph triển khai.

## 24. Class-based bundle, properties và giới hạn truy xuất

Với bundle trong named module, hai định dạng chuẩn thường là:
- **`java.properties`:** file `Messages_fr.properties` chứa các cặp key/value.
- **`java.class`:** class kế thừa `ListResourceBundle` hoặc `ResourceBundle` theo quy tắc tên bundle.

Cả hai đều có **quy tắc truy xuất trong JPMS**, và việc ứng dụng tìm được class/resource của một module khác không phải lúc nào giống classpath.

Một lưu ý:
- Tài nguyên class-based còn liên quan việc truy cập kiểu/class của bundle.
- Với file properties, đường dẫn package/resource cần được đóng gói và kiểm tra accessibility.
- Bundle nội bộ trong cùng module thường đơn giản hơn bundle phân phối qua nhiều module.
- Khi dùng provider, tài nguyên có thể nằm trong module provider và được provider tải theo cách thích hợp.

**Đừng dùng `opens` toàn bộ module như một “fix chung”** nếu có thể giữ bundle nội bộ hoặc dùng service provider. Càng mở rộng surface càng cần xem lại các yêu cầu bảo mật và encapsulation của dự án.

## 25. Service discovery và named modules

`ServiceLoader` là nền tảng của mô hình provider. Với named modules, service discovery phụ thuộc module graph và directive:
- Consumer có `uses service.Type;`.
- Provider có `provides service.Type with implementation.Type;`.
- Provider module được đưa vào cấu hình chạy/resolution.
- Implementation thực sự có thể được khởi tạo và trả bundle.

Ví dụ phần launch tích hợp (mang tính sơ đồ):

~~~bash
java --module-path out --add-modules com.example.translation \
  -m com.example.app/com.example.app.Main
~~~

Lệnh trên dành cho shell hỗ trợ `\` nối dòng, với giả định có các module đã build đúng trong `out`. `--add-modules` giúp bảo đảm provider module được resolved trong ví dụ này. Trong ứng dụng thực, dịch vụ có thể được resolved thông qua service binding/runtime image hoặc cấu hình module khác.

Nếu `provides` đúng nhưng provider không nằm trong layer/module graph được lookup, `getBundle` vẫn có thể không thấy nó. Đặt tên file `module-info.java` đúng là **điều kiện cần nhưng chưa đủ** cho service discovery.

## 26. Các lỗi phổ biến khi migrate

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Giữ nguyên `getBundle(..., Control)` | Named module không hỗ trợ overload có Control | Bỏ Control nếu không cần tùy biến; hoặc thiết kế provider |
| Thử overload `ClassLoader + Control` để lách | Vẫn có tham số Control | Không dùng overload đó trong named module |
| Đăng ký `ResourceBundleControlProvider` mới | SPI này bị bỏ qua trong named modules | Dùng `ResourceBundleProvider` khi cần |
| Nghĩ `Control` bị xóa khỏi JDK | Class vẫn có mặt | Phân biệt class API và cách dùng trong named module |
| Cứ thêm `opens` để chữa UOE | `opens` không sửa overload không hỗ trợ | Sửa API trước, encapsulation sau |
| Tự dùng `exports` để mở file properties | Exports public types, không đủ cho mọi resource lookup | Hiểu `opens`/module access đúng tình huống |
| Dùng service interface sai tên | Lookup SPI dựa vào tên quy ước từ baseName | `package.spi.SimpleNameProvider` |
| Quên `uses` hoặc `provides` | ServiceLoader không tìm đúng provider | Khai báo trong module descriptor |
| Chỉ đặt JAR provider trên đĩa | Chưa chắc resolved | Kiểm tra module graph/launch options |
| Quên copy `.properties` | Biên dịch Java không tự copy resource | Đưa resource vào output/JAR |
| Đóng gói nhiều provider trong cùng package | Split package xung đột | Tách package hoặc custom `toBundleName` |
| Mong `getTimeToLive` tiếp tục chạy | Control callback không được áp dụng | Thiết kế TTL/cache ngoài Control |
| Test trên classpath rồi deploy module path | Bối cảnh caller khác | Integration test modular |
| Quên fallback khi locale thiếu | Kết quả resource/fallback khác mong muốn | Kiểm thử từng locale/provider |

## 27. Checklist QA dành cho ứng dụng đa ngôn ngữ modular

Một bộ kiểm thử tối thiểu:

1. **Trong cùng named module:** `getBundle(baseName, locale)` tải được `.properties` hợp lệ.
2. **Giới hạn Control:** `getBundle(baseName, locale, control)` ném `UnsupportedOperationException`.
3. **Classpath reference test:** overload Control vẫn tồn tại và có thể sử dụng trong unnamed module.
4. **Localization keys:** cùng key có giá trị khác nhau ở hai locale, ví dụ French/English.
5. **Missing resource:** khi không có bundle, nhận `MissingResourceException` và phân biệt với UOE.
6. **Package encapsulation:** consumer module khác không tự vượt quyền truy cập resource.
7. **Service interface naming:** service interface tuân `package.spi.BaseNameProvider`.
8. **Service binding:** có `uses`, `provides`, và provider module resolved.
9. **Provider scope:** provider hỗ trợ đúng locale, trả `null` khi không hỗ trợ.
10. **Packaging:** file resources có mặt trong output/JAR thực tế, không chỉ trong `src`.
11. **Fallback:** locale không tìm thấy có kết quả theo yêu cầu sản phẩm.
12. **Caching:** thay thông điệp được nhận diện theo chính sách cache/reload được thiết kế mới.
13. **Không dùng workaround classloader:** module boundaries vẫn được tuân thủ.
14. **Regression:** chạy ở cùng JDK/modular deployment mà production dùng, không chỉ classpath.

Khi debug, ghi thêm tên caller module và base name/locale **không nhạy cảm**. Đừng log toàn bộ nội dung bản dịch có thể chứa dữ liệu cá nhân của người dùng.

## 28. Bài tập tự kiểm tra

**Câu 1.** Vì sao code chạy được trên classpath nhưng ném `UnsupportedOperationException` khi chuyển sang named module?

**Đáp án:** Các overload `ResourceBundle.getBundle` nhận `ResourceBundle.Control` được thiết kế cho unnamed module và **không được hỗ trợ khi gọi từ named module**.

**Câu 2.** Nếu chỉ có `Messages_fr.properties` trong cùng named module, có nhất thiết phải tạo `ResourceBundleProvider` không?

**Đáp án:** Không. Có thể dùng `ResourceBundle.getBundle(baseName, Locale.FRENCH)` và đóng gói file resource chuẩn đúng vị trí.

**Câu 3.** Nếu đã `opens` package chứa bundle, `getBundle(..., Control)` có hết UOE không?

**Đáp án:** Không. `opens` liên quan module resource access; không thay đổi hạn chế của overload Control.

**Câu 4.** `ResourceBundleControlProvider` có tác dụng thay `ResourceBundleProvider` trong named module không?

**Đáp án:** Không. Các custom `ResourceBundleControlProvider` bị bỏ qua trong named modules.

**Câu 5.** Với baseName `com.example.app.Messages`, service type nên đặt tên gì?

**Đáp án:** `com.example.app.spi.MessagesProvider`.

**Câu 6.** Consumer module khai báo gì để dùng bundle provider service?

**Đáp án:** `uses com.example.app.spi.MessagesProvider;` và provider khai báo `provides ... with ...;`.

**Câu 7.** `AbstractResourceBundleProvider` mặc định có hiểu XML tùy ý không?

**Đáp án:** Không. Nó hỗ trợ `java.class`/`java.properties` như các format được API cho phép; custom format cần implementation khác.

**Câu 8.** Nếu trước đó override `getTimeToLive` trong `Control`, chuyển sang SPI có một callback y hệt không?

**Đáp án:** Không. Provider không phải bản sao 1:1 của các callback Control; phải thiết kế cache/version/reload theo yêu cầu.

**Câu 9.** `MissingResourceException` khác UOE trong bài này thế nào?

**Đáp án:** MissingResourceException nghĩa là không tìm thấy bundle hoặc key; UOE là overload Control không được hỗ trợ trong named module.

**Câu 10.** Có thể dựa vào integration test chạy `java -cp` để xác nhận named-module behavior không?

**Đáp án:** Không. Cần test chạy trên **module path**, vì unnamed và named module có khác biệt hành vi.

## 29. Quy trình migration đề xuất

1. **Kiểm kê toàn bộ lời gọi `ResourceBundle.getBundle`** và tìm những nơi có `Control`, kể cả overload dùng `ClassLoader`.
2. **Xác định module graph** sau migration; phân biệt caller named/unnamed và bundle local/provider.
3. **Với bundle chuẩn trong cùng module**, thử API không Control và kiểm chứng resource packaging, locale, fallback.
4. **Với tùy biến định dạng hoặc bundle phân phối giữa modules**, thiết kế `ResourceBundleProvider`, service type đúng tên, `uses`/`provides` và cách lấy tài nguyên trong module provider.
5. **Tách callback Control thành yêu cầu nghiệp vụ**: định dạng, địa điểm resource, fallback, TTL/reload; không tìm cách copy nguyên subclass.
6. **Rà soát encapsulation**: chỉ mở package cần thiết; không mở toàn module vô điều kiện và không dùng custom loader để phá quyền truy cập.
7. **Kiểm tra build** để bảo đảm các file `.properties` nằm trong artifact cuối; Java compiler không luôn copy chúng.
8. **Viết integration tests trên module path** với nhiều locale, thiếu bundle, UOE, SPI binding, fallback và cache.
9. **Giám sát khi triển khai**: phân biệt UOE, MissingResourceException và lỗi provider resource loading.
10. **Nếu phải giữ cả classpath và module path**, định nghĩa rõ hai đường hoạt động, version kiểm thử và kế hoạch loại bỏ cơ chế không phù hợp với JPMS.

**Ghi nhớ:** `ResourceBundle.Control` **không bị xóa khỏi Java**, nhưng **các overload `ResourceBundle.getBundle` nhận Control không được hỗ trợ trong named modules**. Với bundle chuẩn nằm trong module, ưu tiên API `getBundle` không Control; với mô hình mở rộng giữa module hoặc định dạng riêng, dùng **`ResourceBundleProvider`/`ServiceLoader`** và hiểu `uses`/`provides`, resource encapsulation, fallback và cache. Giới hạn này thuộc **kiến trúc JPMS**, không phải lỗi font, charset hay file bản dịch.

**Tài liệu Java SE 17 chính thức:**
- [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [ResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
- [AbstractResourceBundleProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html)
- [ResourceBundleControlProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleControlProvider.html).