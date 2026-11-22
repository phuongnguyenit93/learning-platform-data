# ResourceBundle: Tích hợp với ứng dụng classpath hiện đại trong Java

## 1. Tổng quan và mục tiêu

`java.util.ResourceBundle` là API của Java SE để chọn và đọc **tài nguyên theo `Locale`**, điển hình là nhãn giao diện, thông báo lỗi và message templates. Trong một ứng dụng Java hiện đại chạy trên **classpath**, thách thức quan trọng không chỉ là viết `messages_vi.properties`, mà còn là **đặt file đúng runtime classpath**, đóng gói đúng JAR, chọn locale rõ ràng và kiểm soát fallback.

Một chương trình có thể biên dịch thành công nhưng khi deploy lại ném `MissingResourceException` vì `.properties` không nằm trong artifact cuối. Hoặc người dùng yêu cầu tiếng Việt nhưng UI hiện tiếng Anh vì fallback sang default locale của JVM. Hai trường hợp này cần được phân biệt và kiểm thử.

Sau bài học, bạn có thể:

1. Đặt đúng các file trong `src/main/resources` và ánh xạ từ `i18n.messages` tới `i18n/messages_vi_VN.properties`.
2. Dùng `ResourceBundle.getBundle` với `Locale` cụ thể, hiểu `vi_VN → vi → root`, key fallback và locale fallback.
3. Đọc UTF-8 tiếng Việt theo hợp đồng Java SE hiện hành, đồng thời hiểu lựa chọn strict UTF-8.
4. Định dạng tham số bằng `MessageFormat`, kể cả dấu apostrophe trong pattern.
5. Chạy ứng dụng với class directory, một JAR hoặc nhiều JAR trên runtime classpath.
6. Phát hiện resource bị bỏ quên, sai base name, sai class loader, missing key, cache cũ.
7. Phân biệt classpath/unnamed module với **named modules JPMS** để không sử dụng sai `ResourceBundle.Control`.
8. Tích hợp resource bundles vào workflow Maven/Gradle và CI.

Ví dụ chính là dự án Java 17+ có **15 kiểm tra tự động**. Mã đã được biên dịch với `javac --release 17` và chạy thành công trên OpenJDK 24 trong ba kiểu đóng gói. Các API được đối chiếu theo Javadoc Java SE 26. Chỉ sử dụng kiến thức còn áp dụng, không tái hiện cách xử lý đã lỗi thời như bắt buộc chuyển toàn bộ text UTF-8 thành escapes.

## 2. Các thành phần cơ bản

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `ResourceBundle` | Hợp đồng tra tài nguyên theo base name + locale | `getBundle("i18n.messages", locale)` |
| `PropertyResourceBundle` | Bundle được đọc từ file `.properties` | `messages_vi.properties` |
| `ListResourceBundle` | Bundle hiện thực bằng class Java, có mảng key/value | Khi tài nguyên cần logic/objects khác strings |
| `Locale` | Language/script/region/variant của người dùng | `Locale.forLanguageTag("vi-VN")` |
| `ResourceBundle.Control` | Thay đổi formats, fallback, cache, reload trong **unnamed module** | `getNoFallbackControl(FORMAT_PROPERTIES)` |
| `MessageFormat` | Thay parameters và định dạng ngôn ngữ | `"Xin chào, {0}!"` |
| `ClassLoader` | Nhìn thấy resources tại runtime | `getResource("i18n/messages_vi.properties")` |
| `ResourceBundleProvider` | Cung cấp bundles qua services cho named modules | Cơ chế JPMS khi cần |
| Maven/Gradle resource processing | Copy source resources vào runtime output/JAR | `src/main/resources` → `target/classes` hoặc build output |

`java.util.Properties` là container key-value tổng quát. Nó không tự triển khai quy tắc chọn locale, parent chain và cache của `ResourceBundle`. Đừng tự viết nhiều câu `if (locale...)` để đọc từng file trong khi yêu cầu của bạn chính là resource family tiêu chuẩn.

### Khi nào không dùng ResourceBundle?

ResourceBundle thích hợp với **tài nguyên localized**. Đừng dùng nó làm nơi chứa mật khẩu, tokens, database URLs bí mật hoặc cấu hình nghiệp vụ không phụ thuộc locale. File `.properties` đóng gói trong JAR là dữ liệu có thể đọc được bởi người có artifact. Những dữ liệu này cần configuration/secret management phù hợp, không phải i18n.

## 3. Base name, tên file và resource path

Base name trong ví dụ:

```java
private static final String BASE = "i18n.messages";
```

Đây là tên logic có dấu chấm, **không** phải URL, relative filesystem path hay file name có đuôi `.properties`. Theo convention của classpath resource lookup:

| Locale | Bundle name | Resource path |
| --- | --- | --- |
| Root | `i18n.messages` | `i18n/messages.properties` |
| English | `i18n.messages_en` | `i18n/messages_en.properties` |
| Vietnamese | `i18n.messages_vi` | `i18n/messages_vi.properties` |
| Vietnamese in Viet Nam | `i18n.messages_vi_VN` | `i18n/messages_vi_VN.properties` |

Ví dụ runtime directory:

```text
build/classes/
├── dev/example/app/BundleDemo.class
└── i18n/
    ├── messages.properties
    ├── messages_en.properties
    ├── messages_vi.properties
    └── messages_vi_VN.properties
```

Với JAR, các entries tương ứng nằm ngay tại root của archive:

```text
dev/example/app/BundleDemo.class
i18n/messages.properties
i18n/messages_en.properties
i18n/messages_vi.properties
i18n/messages_vi_VN.properties
```

Nếu file thực tế ở `build/classes/src/main/resources/i18n/messages_vi.properties` thì vị trí **sai**. Phải copy **nội dung bên trong** `src/main/resources` vào root của runtime classpath entry.

Sai:

```java
ResourceBundle.getBundle("src/main/resources/i18n/messages", locale);
ResourceBundle.getBundle("i18n/messages_vi.properties", locale);
```

Đúng:

```java
ResourceBundle.getBundle("i18n.messages", locale);
```

`Locale.forLanguageTag("vi-VN")` dùng language tag theo BCP 47. Tuy nhiên tên file bundle được Java tạo theo quy tắc candidate suffix với dấu gạch dưới, ví dụ `_vi_VN`, không phải `messages_vi-VN.properties`.

## 4. Fallback giữa locale, region và root

Giả sử có các resource:

```properties
# messages.properties
shared=Shared root
status=Default status
```

```properties
# messages_vi.properties
greeting=Xin chào, {0}!
status=Sẵn sàng
```

```properties
# messages_vi_VN.properties
region=Khu vực Việt Nam
status=Đã sẵn sàng
```

Với `Locale.forLanguageTag("vi-VN")`:

- `status` lấy từ `messages_vi_VN.properties`, vì biến thể vùng khai báo key cụ thể.
- `greeting` không có ở `vi_VN` nên lấy từ parent `vi`.
- `shared` không có ở `vi_VN` hay `vi` nên lấy từ root bundle.

Đây là **key fallback trong parent chain**. Nó khác với bước **fallback sang default locale** khi không tìm được bundle ứng với requested locale.

### Default locale fallback có thể khiến test thiếu ổn định

Overload thông thường:

```java
ResourceBundle.getBundle("i18n.messages", Locale.FRANCE);
```

có thể xét thêm **`Locale.getDefault()` của JVM** tùy candidate lookup nếu thiếu resource cho requested locale. Như vậy cùng code có thể chạy ra ngôn ngữ khác nhau trên máy dev và CI.

Trong classpath app/unnamed module, ta có thể dùng:

```java
ResourceBundle.Control noDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle french = ResourceBundle.getBundle(
        "i18n.messages", Locale.FRANCE, noDefaultFallback);
```

`getNoFallbackControl` ngăn xét **default locale của JVM**, nhưng **vẫn cho phép parent/root fallback**. Nếu không có file `messages_fr*.properties` mà có `messages.properties`, bundle được resolve về root: `french.getLocale().equals(Locale.ROOT)` là `true`.

Đừng hiểu tên “no fallback” là xóa parent chain. Nó chỉ điều chỉnh **fallback locale bên ngoài candidate chain chính**.

### Locale được yêu cầu khác locale thực tế của bundle

`ResourceBundle#getLocale()` trả về **locale của bundle cuối cùng được chọn**. Vì có fallback, nó không bắt buộc trùng requested locale.

Chẳng hạn:

```java
ResourceBundle rb = ResourceBundle.getBundle(
        "i18n.messages", Locale.FRANCE, noDefaultFallback);
System.out.println(rb.getLocale().equals(Locale.ROOT)); // true
```

Đoạn này minh họa khi đã có biến `noDefaultFallback` và root bundle phù hợp. Nếu ứng dụng cần hiện thông báo về locale thực tế hoặc kiểm thử fallback, hãy kiểm tra `getLocale()`, không chỉ locale argument.

### Tránh `Locale.setDefault(...)` theo từng request

Trong backend có hàng trăm users, mỗi request có thể có language preference riêng. `Locale.setDefault` thay đổi trạng thái toàn JVM; không dùng nó cho từng HTTP request vì gây ảnh hưởng các luồng khác. Dùng locale explicit theo người dùng:

```java
Locale userLocale = Locale.forLanguageTag("vi-VN");
ResourceBundle rb = ResourceBundle.getBundle(
        "i18n.messages", userLocale);
```

Việc giải mã `Accept-Language` và lựa chọn trong tập locales hỗ trợ là trách nhiệm của application framework/policy. `ResourceBundle` không tự làm toàn bộ HTTP language negotiation.

## 5. UTF-8 properties trong Java hiện đại

Java 9 trở lên hỗ trợ **UTF-8 mặc định cho `PropertyResourceBundle` đọc từ `InputStream`**. Điều này cho phép ghi tiếng Việt trực tiếp:

```properties
greeting=Xin chào, {0}!
status=Đã sẵn sàng
```

Không cần chạy `native2ascii` như một bước bắt buộc cho mọi bản dịch trên JDK hiện đại.

Javadoc có một điểm quan trọng: khi đọc file và gặp bytes không hợp lệ theo UTF-8, `PropertyResourceBundle` có thể **thử lại theo ISO-8859-1** vì mục tiêu tương thích. Nếu contract bắt buộc **strict UTF-8**, hãy bật system property ngay lúc JVM khởi động:

```bash
java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' \
  -cp build/classes dev.example.app.BundleDemo
```

Ở Windows PowerShell 5.1 cũng nên quote cả JVM option:

```powershell
java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' -cp build/classes dev.example.app.BundleDemo
```

Property name chính xác là `java.util.PropertyResourceBundle.encoding`, nhận các giá trị `UTF-8` hoặc `ISO-8859-1` theo tài liệu. Nó được đọc khi lớp `PropertyResourceBundle` khởi tạo; sửa nó sau đó không bảo đảm thay đổi cách bundle đã cache được giải mã.

### Hai encoding ở hai bước

- `javac -encoding UTF-8` điều khiển compiler đọc source files `.java`.
- `-Djava.util.PropertyResourceBundle.encoding=UTF-8` điều khiển cách `PropertyResourceBundle` decode resource files `.properties` theo contract hiện hành.

Không đánh đồng nó với `Properties.load(InputStream)`, vì `Properties` có quy tắc input encoding khác. Không dùng encoding mặc định của shell/OS làm giả định bất biến cho file build.

### Định dạng file

Properties syntax còn bao gồm:

- `#` và `!` ở đầu logical line làm comment.
- `=` hoặc `:` phân tách key/value.
- Các ký tự `\` đặc biệt cho escaping.
- `\uXXXX` để mô tả Unicode escape khi cần.
- Cơ chế continuation qua backslash ở cuối dòng theo đặc tả.

Một file UTF-8 có code points đúng nhưng dùng escape sai vẫn có thể trả value khác. Nên kiểm thử **nội dung sau khi load từ artifact**, không chỉ nhìn file bằng editor.

## 6. Dùng MessageFormat để không hard-code vị trí từ

Từ resource:

```properties
greeting=Xin chào, {0}!
```

Định dạng bằng locale tường minh:

```java
ResourceBundle vi = ResourceBundle.getBundle(
        "i18n.messages", Locale.forLanguageTag("vi-VN"));

MessageFormat formatter = new MessageFormat(
        vi.getString("greeting"),
        Locale.forLanguageTag("vi-VN"));

String text = formatter.format(new Object[] {"Lan"});
// Xin chào, Lan!
```

Đây là đoạn minh họa bên trong method có imports `ResourceBundle`, `Locale` và `MessageFormat`. Message templates cho phép bản dịch đổi vị trí arguments khi cấu trúc câu của ngôn ngữ khác.

### Lưu ý apostrophe

`MessageFormat` có quoting rules riêng. Nếu muốn hiển thị dấu `'` trong pattern, phải dùng `''`:

```properties
quote=It''s ready for {0}.
```

Với `{0}` là `Lan`, output đúng:

```text
It's ready for Lan.
```

Đừng viết một bản dịch có apostrophe đơn mà không biết quy tắc `MessageFormat`; parser có thể hiểu đó là dấu bắt đầu vùng quote, khiến placeholder không được thay đúng.

### Number/date và concurrency

`MessageFormat` còn hiểu các placeholder có type, ví dụ `{0,number,integer}` hoặc `{1,date,short}`. Kết quả format số/ngày phụ thuộc locale và dữ liệu locale của JDK; khi test golden output cần chọn locale/version rõ ràng hoặc assert cấu trúc có ý nghĩa, không đoán separators ở mọi hệ thống.

`MessageFormat` là đối tượng mutable và **không đồng bộ**. Không chia sẻ một instance có thể bị chỉnh sửa giữa các request threads nếu chưa có chính sách synchronization/copying. Có thể tạo formatter ngắn hạn theo request; `ResourceBundle` được cache riêng và thường có thể dùng lại cho việc đọc.

Kết quả localization nếu đưa vào HTML, JSON hay SQL vẫn cần escaping/encoding của **ngữ cảnh đích**; `MessageFormat` không phải công cụ chống injection tổng quát.

## 7. Dự án hoàn chỉnh theo layout Maven/Gradle

```text
bundle-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── dev/example/app/
│       │       └── BundleDemo.java
│       └── resources/
│           └── i18n/
│               ├── messages.properties
│               ├── messages_en.properties
│               ├── messages_vi.properties
│               └── messages_vi_VN.properties
└── build/
    ├── classes/
    ├── app-all.jar
    ├── app-code.jar
    └── translations.jar
```

Java source ở `src/main/java`, còn tài nguyên ở `src/main/resources`. Với Maven/Gradle, bước resource processing thường copy chúng vào runtime output. Với `javac` thuần, **phải tự copy**. Không thêm `src/main/resources` vào base name.

### 7.1. `src/main/resources/i18n/messages.properties`

```properties
greeting=Hello from root, {0}!
status=Default status
shared=Shared root
quote=It''s ready for {0}.
```

### 7.2. `src/main/resources/i18n/messages_en.properties`

```properties
greeting=Hello, {0}!
status=Ready
```

### 7.3. `src/main/resources/i18n/messages_vi.properties`

```properties
greeting=Xin chào, {0}!
status=Sẵn sàng
```

### 7.4. `src/main/resources/i18n/messages_vi_VN.properties`

```properties
region=Khu vực Việt Nam
status=Đã sẵn sàng
```

Các file `vi`/`vi_VN` chủ động thiếu một số keys để kiểm tra parent fallback. Đây là bài học về **quan hệ keys**, không phải yêu cầu mọi locale files trong dự án production phải luôn thiếu bản dịch.

### 7.5. `src/main/java/dev/example/app/BundleDemo.java`

```java
package dev.example.app;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.ResourceBundle.Control;

public final class BundleDemo {
    private static final String BASE = "i18n.messages";
    private static final Control NO_DEFAULT_FALLBACK =
            Control.getNoFallbackControl(Control.FORMAT_PROPERTIES);
    private static int passed;

    private static ResourceBundle load(Locale locale) {
        return ResourceBundle.getBundle(
                BASE, locale, NO_DEFAULT_FALLBACK);
    }

    private static void check(String name, boolean good) {
        if (!good) {
            throw new AssertionError(name);
        }
        System.out.println("PASS " + name);
        passed++;
    }

    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        ResourceBundle vi = load(vietnam);
        ResourceBundle en = load(Locale.ENGLISH);
        ResourceBundle fr = load(Locale.FRANCE);

        check("exact-locale",
                vi.getLocale().equals(vietnam));
        check("vi-parent-key",
                vi.getString("greeting")
                        .equals("Xin chào, {0}!"));
        check("vi-region-override",
                vi.getString("status")
                        .equals("Đã sẵn sàng"));
        check("root-parent-key",
                vi.getString("shared")
                        .equals("Shared root"));
        check("vi-region-only",
                vi.getString("region")
                        .equals("Khu vực Việt Nam"));
        check("en-key",
                en.getString("status").equals("Ready"));
        check("root-fallback-no-default-locale",
                fr.getLocale().equals(Locale.ROOT)
                && fr.getString("greeting")
                        .equals("Hello from root, {0}!"));

        MessageFormat message = new MessageFormat(
                vi.getString("greeting"), vietnam);
        check("message-format",
                message.format(new Object[] {"Lan"})
                        .equals("Xin chào, Lan!"));

        MessageFormat quoted = new MessageFormat(
                vi.getString("quote"), vietnam);
        check("message-format-apostrophe",
                quoted.format(new Object[] {"Lan"})
                        .equals("It's ready for Lan."));

        check("keyset-parent",
                vi.containsKey("shared")
                && vi.keySet().contains("shared"));

        check("cache-same-bundle",
                vi == load(vietnam));

        check("resource-visible-on-classpath",
                BundleDemo.class.getClassLoader()
                        .getResource(
                                "i18n/messages_vi.properties") != null);

        check("explicit-classloader",
                ResourceBundle.getBundle(
                        BASE,
                        vietnam,
                        BundleDemo.class.getClassLoader(),
                        NO_DEFAULT_FALLBACK)
                        .getString("region")
                        .equals("Khu vực Việt Nam"));

        boolean missingKey = false;
        try {
            vi.getString("missing.key");
        } catch (MissingResourceException expected) {
            missingKey = true;
        }
        check("missing-key-throws", missingKey);

        boolean missingBase = false;
        try {
            ResourceBundle.getBundle(
                    "i18n.no_such_bundle",
                    Locale.ROOT,
                    NO_DEFAULT_FALLBACK);
        } catch (MissingResourceException expected) {
            missingBase = true;
        }
        check("missing-base-throws", missingBase);

        System.out.println("passed=" + passed);
    }
}
```

**Giải thích trọng tâm của code:**

- `BASE` tách khỏi tên file và giữ ổn định cho cả family.
- `Locale.forLanguageTag("vi-VN")` rõ hơn việc dựa vào default locale của host.
- `Control.getNoFallbackControl(FORMAT_PROPERTIES)` cố ý không fallback sang JVM default locale, nhưng vẫn có key lookup qua parent `vi`/root.
- `getLocale()` kiểm tra bundle được resolve thực tế.
- `MessageFormat` nhận pattern từ bundle và locale tương ứng.
- `containsKey/keySet` có thể thấy keys ở parent chain.
- `getResource(...)` xác minh file cụ thể hiện diện trên classpath (không phải test đầy đủ mọi bước của getBundle).
- Test cache chỉ phản ánh fixture hiện tại; không phải cam kết mọi scope/cache policy đều trả cùng instance.
- Phân biệt lỗi thiếu key (gọi `getString`) và thiếu family (gọi `getBundle`).

Mỗi `check` sẽ ném `AssertionError` nếu fail; lúc thành công in `PASS <name>` và tăng biến đếm. Ở cuối mới in `passed=15`.

### 7.6. Stdout chính xác đã kiểm thử

```text
PASS exact-locale
PASS vi-parent-key
PASS vi-region-override
PASS root-parent-key
PASS vi-region-only
PASS en-key
PASS root-fallback-no-default-locale
PASS message-format
PASS message-format-apostrophe
PASS keyset-parent
PASS cache-same-bundle
PASS resource-visible-on-classpath
PASS explicit-classloader
PASS missing-key-throws
PASS missing-base-throws
passed=15
```

Fixture được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24, đã xác minh **đúng 15 PASS** ở cả ba phương án class directory, một JAR và hai JAR riêng.

## 8. Cách chạy bằng class directory với javac thuần

### 8.1. Linux/macOS

Tại thư mục root của dự án:

```bash
mkdir -p build/classes

javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/main/java/dev/example/app/BundleDemo.java

cp -R src/main/resources/. build/classes/

java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' \
  -cp build/classes \
  dev.example.app.BundleDemo
```

Điểm quan trọng: `cp -R src/main/resources/. build/classes/` copy **nội dung bên trong folder resources**, để có `build/classes/i18n/messages.properties`. Compiler `javac` không tự copy `.properties` theo quy ước Maven/Gradle.

### 8.2. Windows PowerShell

```powershell
New-Item -ItemType Directory -Path build/classes -Force |
    Out-Null

javac --release 17 -encoding UTF-8 -d build/classes src/main/java/dev/example/app/BundleDemo.java

Copy-Item -Path src/main/resources/i18n -Destination build/classes -Recurse -Force

java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' -cp build/classes dev.example.app.BundleDemo
```

Dấu nháy đơn quanh `-D...` có ích cho Windows PowerShell 5.1, để option được truyền như **một đối số đầy đủ**. Trên Bash/Linux cũng có thể quote như vậy.

### 8.3. Kết quả

Sau khi resource files đã có trong classpath, chương trình in **15 PASS và `passed=15`** như phần 7.6.

Nếu chỉ compile Java source nhưng **quên copy resources**, `BundleDemo.class` vẫn tồn tại, nhưng runtime không có family `i18n.messages` để đọc. Chương trình sẽ thất bại trước khi in 15 PASS. Điều này cho thấy **compile success không chứng minh packaging success**.

## 9. Đóng gói trong một JAR trên classpath

Sau khi `build/classes` chứa cả class và resource files:

```bash
jar --create --file build/app-all.jar \
  -C build/classes .

java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' \
  -cp build/app-all.jar \
  dev.example.app.BundleDemo
```

PowerShell có thể viết mỗi lệnh trên một dòng:

```powershell
jar --create --file build/app-all.jar -C build/classes .
java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' -cp build/app-all.jar dev.example.app.BundleDemo
```

`-C build/classes .` có nghĩa lấy các entries **từ root của `build/classes`**, không đưa tên `build/classes` vào JAR entry path.

Xác minh:

```bash
jar --list --file build/app-all.jar
```

Trong kết quả cần thấy các entries:

```text
dev/example/app/BundleDemo.class
i18n/messages.properties
i18n/messages_en.properties
i18n/messages_vi.properties
i18n/messages_vi_VN.properties
```

Không assert thứ tự của `jar --list` vì archive cũng có thể chứa manifest và directory entries. Hãy kiểm tra paths cụ thể.

### `java -cp` khác `java -jar`

Lệnh `java -cp app-all.jar dev.example.app.BundleDemo` dùng **classpath** và chỉ đích danh main class.

Để chạy `java -jar app-all.jar`, JAR cần `Main-Class` trong manifest (hoặc cấu hình executable JAR tương ứng). Đừng nghĩ bất kỳ JAR có main class bên trong cũng được `java -jar` tự nhận ra. Khi dùng `-jar`, classpath resolution của Java launcher không giống lệnh `-cp` thông thường; đừng tùy tiện trộn hai cú pháp rồi mong translations JAR luôn được nạp. Bài này dùng `-cp` để minh họa classpath rõ ràng.

## 10. Tách class JAR và translations JAR

Đây là tình huống phổ biến khi nhóm dịch thuật hoặc packaging muốn phát hành resource bundle riêng.

Tạo file JAR code-only và file JAR chỉ chứa translations. Trên Linux/macOS:

```bash
mkdir -p build/classes-only
cp -R build/classes/dev build/classes-only/

jar --create --file build/app-code.jar \
  -C build/classes-only .

jar --create --file build/translations.jar \
  -C src/main/resources .

java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' \
  -cp "build/app-code.jar:build/translations.jar" \
  dev.example.app.BundleDemo
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Path build/classes-only -Force |
    Out-Null

Copy-Item -Path build/classes/dev -Destination build/classes-only -Recurse -Force

jar --create --file build/app-code.jar -C build/classes-only .
jar --create --file build/translations.jar -C src/main/resources .

java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' -cp "build/app-code.jar;build/translations.jar" dev.example.app.BundleDemo
```

Cả hai JAR phải nằm trong **runtime classpath** của ứng dụng. `app-code.jar` chứa `BundleDemo.class`, còn `translations.jar` chứa `i18n/...properties`. Class loader của ứng dụng sẽ có thể tìm resources trong JAR riêng và chương trình vẫn in **15/15 PASS**.

**Classpath separator:** Linux/macOS dùng dấu hai chấm `:`; Windows dùng dấu chấm phẩy `;`. Quote toàn bộ classpath string trong PowerShell nếu có dấu `;`.

### Negative test: bỏ translations.jar

Chạy chỉ code JAR:

```bash
java '-Djava.util.PropertyResourceBundle.encoding=UTF-8' \
  -cp build/app-code.jar \
  dev.example.app.BundleDemo
```

Kết quả mong đợi là runtime ném:

```text
java.util.MissingResourceException:
Can't find bundle for base name i18n.messages, locale vi_VN
```

Trong bài test trên OpenJDK 24, trường hợp thiếu resource-only JAR kết thúc với **exit code 1**. Stack trace đầy đủ, tên file và số dòng tùy JDK, nên đừng đưa toàn bộ stack trace vào golden output.

Lỗi này giúp phân biệt rõ: **bundle không nằm trên classpath** khác với **bundle có nhưng thiếu key**.

### Tránh trùng đường dẫn resources

Nếu hai JAR đều chứa `i18n/messages_vi.properties`, không có quy tắc “tự merge properties của cả hai file”. Resource lookup có thể phụ thuộc class loader và classpath ordering. Hãy có **một owner cho mỗi bundle name/locale**, hoặc thiết kế riêng cách tổng hợp resources. Kiểm tra duplicate paths khi build fat JAR/uber JAR.

## 11. Maven và Gradle resources pipeline

### 11.1. Gradle Java/application plugin

Một file `build.gradle` dạng Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'dev.example.app.BundleDemo'
}
```

Đây là **cấu hình minh họa theo Java/Gradle convention**, không phải file build đã được test trong fixture CLI. `src/main/resources` là source resources directory mặc định khi áp Java plugin; Gradle copy các entries vào output của `processResources`, rồi thêm chúng vào runtime classpath.

Các bước thường dùng:

```bash
./gradlew classes
./gradlew run
./gradlew jar
```

Trên Windows dùng `gradlew.bat` nếu dự án có wrapper. Hãy pin Gradle version/toolchain theo quy định dự án. `options.encoding = 'UTF-8'` dành cho Java source; không tự thay thế quy tắc resource encoding của JVM. Nếu cần set `-Djava.util.PropertyResourceBundle.encoding=UTF-8` cho app trong task `run`, cấu hình `JavaExec`/`applicationDefaultJvmArgs` phù hợp, không giả định JVM property của Gradle daemon được truyền xuống ứng dụng.

### 11.2. Maven theo conventions

Một `pom.xml` tối giản:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>bundle-demo</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
</project>
```

File này là ví dụ project cơ bản. Với production, hãy pin versions của Maven Compiler/Resources plugins theo toolchain được sử dụng; đừng coi việc một POM tối giản được viết ra là chứng nhận nó đã được build trên mọi Maven version.

`mvn package` thường đưa resources từ `src/main/resources` vào `target/classes` cùng với classes, sau đó đóng gói vào JAR. Để chạy bằng classpath:

```bash
mvn package
java -cp target/classes dev.example.app.BundleDemo
```

Nếu artifact có tên `target/bundle-demo-1.0-SNAPSHOT.jar`, có thể dùng:

```bash
jar --list --file target/bundle-demo-1.0-SNAPSHOT.jar
```

Đường dẫn thật phụ thuộc POM/build config. Đừng hard-code một tên jar không tồn tại rồi cho rằng ResourceBundle không hoạt động.

### 11.3. Resource filtering và encoding

Một số build setup cấu hình **resource filtering** để thay tokens trong file. Với translations, filtering ngoài ý muốn có thể thay đổi placeholders, dấu escape hoặc nội dung Unicode. Nên tắt filtering nếu không cần, hoặc pin charset và ký hiệu token thay thế, rồi **test resource bytes sau khi build**.

Việc file có trong `src/main/resources` không bảo đảm file có trong **fat JAR cuối cùng**. Kiểm tra jar entries và chạy chương trình kiểm thử bằng chính artifact đã publish nếu có thể.

## 12. ClassLoader và khả năng tìm thấy resource

Trong classpath app, bạn có thể probe resource path:

```java
ClassLoader loader = BundleDemo.class.getClassLoader();

java.net.URL url = loader.getResource(
        "i18n/messages_vi.properties");

System.out.println(url != null);
```

Đây là đoạn minh họa, không phải test đầy đủ mọi bước lookup. Nó chỉ trả lời câu hỏi **class loader đó có thấy file cụ thể tại path đó không**.

Có overload `ResourceBundle.getBundle` cho class loader explicit:

```java
ResourceBundle rb = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi-VN"),
        BundleDemo.class.getClassLoader());
```

Hoặc với `Control` trong unnamed module:

```java
ResourceBundle rb = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi-VN"),
        BundleDemo.class.getClassLoader(),
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES));
```

Điều này quan trọng trong plugin systems, application servers, tests, custom classloaders và executable launchers. `getBundle(String, Locale)` có context caller/module riêng; đừng mặc định nó luôn tìm qua **Thread Context ClassLoader** của từng thread theo ý muốn.

### Loader nào sở hữu translations?

Nếu một library chung gọi `getBundle` bằng context của chính library, resources được đóng gói ở plugin/app khác có thể không được nhìn thấy. Khi đó hãy quyết định rõ:

- Library sở hữu bundle family và đóng gói resources cùng mình; hoặc
- Application truyền `ClassLoader` / resource accessor theo một interface; hoặc
- Library nhận thông điệp đã localized từ ứng dụng, không tự tra bundles của khách hàng.

Không dùng một loader “có thể tìm mọi nơi” nếu hệ thống có isolation/security constraints; đặc biệt trong module layers.

### Tại sao probe thấy file mà getBundle vẫn fail?

`ClassLoader.getResource(...) != null` không bảo đảm toàn bộ ResourceBundle family hoạt động:

- Base name truyền sai.
- Requested locale và fallback policy không tìm được candidate cần thiết.
- File có syntax/encoding lỗi.
- Có class-based bundle trùng tên, khiến lookup strategy khác.
- Module/caller context khác.
- Cache và classloader scoping dẫn tới kết quả không dự đoán như test đơn giản.

Vì vậy hãy test **chính `getBundle` + `getString`**, không chỉ test có file tồn tại.

## 13. MissingResourceException và các lỗi cần xử lý riêng

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `getBundle` ném MissingResourceException | Không có bundle family trong loader/path thích hợp | Kiểm tra base name, JAR, runtime classpath, module visibility |
| `getString(key)` ném MissingResourceException | Bundle có nhưng key không nằm trong parent chain | Kiểm tra key spelling/coverage/fallback |
| Trả string tiếng Anh khi yêu cầu tiếng Việt | Đang fallback sang root/default | Đọc `bundle.getLocale()`, kiểm tra file `vi`/`vi_VN` |
| Tiếng Việt thành ký tự lạ | Source/resource encoding không thống nhất | Lưu UTF-8, kiểm tra property encoding/bytes, rebuild |
| Chạy từ IDE được nhưng JAR fail | IDE thêm resources directory, JAR cuối thiếu | Kiểm tra `jar --list` và package task |
| `containsKey` true dù `vi_VN` không có key | Key đến từ parent | Test translation coverage riêng |
| Sửa file nhưng output cũ | `ResourceBundle` cache | Redeploy/clearCache/reload policy |
| App plugin không nhìn thấy bundle | ClassLoader boundaries | Truyền đúng loader hoặc sở hữu resources rõ |
| Classpath trên Windows không load JAR thứ hai | Dùng `:` thay cho `;` | Sửa path separator theo OS |
| Named module gọi `Control` ném lỗi | Overload không được hỗ trợ | Dùng module-aware API/provider |

Không nên bắt mọi `MissingResourceException` rồi trả `""`: UI có thể âm thầm bị trống, và lỗi đóng gói khó được phát hiện. Với user-facing app, một policy hợp lý có thể hiển thị key/code tạm thời và ghi diagnostic, nhưng cần nhất quán theo sản phẩm, không ngầm nuốt mọi lỗi.

## 14. Cache và cập nhật translations

`ResourceBundle.getBundle` có cache mặc định. Cùng base name/locale/classloader và các điều kiện cache giống nhau có thể trả lại cùng `ResourceBundle` instance thay vì đọc file nhiều lần.

Các API cần biết:

- `ResourceBundle.clearCache()`: clear cache thuộc phạm vi caller module.
- `ResourceBundle.clearCache(ClassLoader loader)`: clear cache gắn với loader.
- `ResourceBundle.Control.getTimeToLive(...)` và `needsReload(...)`: điều khiển TTL/reload trong context có hỗ trợ Control.
- `ResourceBundle.Control.TTL_DONT_CACHE` và `TTL_NO_EXPIRATION_CONTROL`: biểu diễn policy về cache.

**Đừng** kỳ vọng sửa `messages_vi.properties` trên disk khi JVM đang chạy là UI tự cập nhật ngay. Nếu translations là một phần immutable của build artifact, cách đơn giản và dễ rollback là **rebuild + redeploy**.

Nếu cần hot reload:

1. Xác định source external translations, loader phù hợp và ownership của cache.
2. Cấu hình TTL/invalidation phù hợp.
3. Khi sửa file, xác minh loader nhìn thấy **nội dung mới** (không chỉ clear Java cache).
4. Kiểm thử nhiều threads và requests đang dùng các bản bundle khác nhau.
5. Đừng giả định thay JVM system property về encoding sau khi `PropertyResourceBundle` đã khởi tạo sẽ làm nó đọc lại theo charset khác.

`clearCache` không tự thêm một JAR chưa nằm trên classpath vào ClassLoader. **Cache invalidation khác resource visibility**.

## 15. Ranh giới giữa classpath và JPMS named modules

**Đây là cảnh báo quan trọng về Java hiện đại.**

Trong ứng dụng trên classpath, classes nằm ở **unnamed module** và `ResourceBundle.Control` vẫn là API hợp lệ:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.messages", Locale.forLanguageTag("vi-VN"), control);
```

Tuy nhiên Javadoc hiện hành nêu **`ResourceBundle.Control` không được hỗ trợ trong named modules**. Gọi overload `getBundle(..., Control)` từ named module có thể ném **`UnsupportedOperationException`**.

Nếu dự án chuyển sang JPMS:

- Đọc resource bundles cùng module qua `getBundle(baseName, locale)` theo quy tắc caller module.
- Cân nhắc `getBundle(baseName, locale, Module)` khi cần chỉ rõ module.
- Với tài nguyên được cung cấp bởi module dịch vụ khác, dùng `java.util.spi.ResourceBundleProvider` và `uses/provides` trong `module-info.java` theo hướng dẫn Java SE.
- Chú ý **encapsulation** của resource files trong named module; file nằm trong một JAR/module chưa chắc mọi module khác đọc được.
- Không áp `Control.getNoFallbackControl` như một giải pháp phổ quát nếu caller thuộc named module.

Không có yêu cầu phải chuyển mọi ứng dụng classpath sang JPMS để dùng ResourceBundle “hiện đại”. Maven/Gradle app **không có `module-info.java`** vẫn hoàn toàn có thể đóng gói localized properties và hoạt động đúng theo API.

## 16. Tích hợp i18n vào thiết kế ứng dụng

Một thiết kế thường dùng:

```text
HTTP/desktop/CLI request
           |
       chọn Locale
           |
           v
 LocalizationService
    ├── ResourceBundle.getBundle(baseName, locale)
    ├── getString(key)
    └── MessageFormat(pattern, locale)
           |
           v
   Localized UI/API message
```

Wrapper minh họa:

```java
static String translate(
        String key, Locale locale, Object... args) {
    ResourceBundle rb = ResourceBundle.getBundle(
            "i18n.messages", locale);
    MessageFormat format =
            new MessageFormat(rb.getString(key), locale);
    return format.format(args);
}
```

Đây là **method minh họa không standalone**. Thực tế có thể inject một bundle loader/fallback policy vào localization service, đặc biệt nếu ứng dụng classpath cần no-default-fallback như demo hoặc sau này chuyển JPMS.

### Business logic không nên tự dịch mọi thông báo

Tầng domain có thể giữ error codes ổn định (`ORDER_NOT_FOUND`) và application/presentation layer chuyển chúng thành localized text. Như vậy log và API machine-readable fields không phụ thuộc ngôn ngữ, trong khi UI message có thể dùng `ResourceBundle` theo từng request.

### Test compatibility của translations

Các keys trong bundle giống như một API. Nếu đổi `status` thành `state` mà chưa đổi Java code, `getString("status")` sẽ fail runtime. Nên có test kiểm tra required keys và placeholder parity.

Phân biệt:

- **Functional fallback:** App vẫn hoạt động nhờ lấy key từ parent.
- **Translation completeness:** File localized đã dịch đủ các câu cần thiết theo yêu cầu sản phẩm.

`bundle.containsKey(key)` có thể trả true chỉ vì root có key; nó **không chứng minh từng file localized đã dịch xong**.

## 17. Kiểm thử tích hợp trên artifact thật

| Test | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Directory classpath | Classes + `i18n` cùng trong build/classes | 15/15 PASS |
| Single JAR | app-all.jar có classes và resources | 15/15 PASS |
| Separate translations JAR | app-code.jar + translations.jar | 15/15 PASS |
| Missing translations JAR | Chỉ app-code.jar | MissingResourceException, exit khác 0 |
| Locale exact | `vi-VN` có file `vi_VN` | `getLocale()` là `vi-VN` |
| Parent language | Key greeting không có trong `vi_VN` | Lấy từ `vi` |
| Root fallback key | Key shared không có trong `vi_VN` và `vi` | Lấy root |
| Locale không được hỗ trợ | `Locale.FRANCE`, no-default-fallback | Trả bundle root |
| English | `messages_en.properties` | `status=Ready` |
| UTF-8 | Tiếng Việt có dấu | Đúng ký tự, không mojibake |
| MessageFormat | `{0}`, `It''s` | Đúng tên và apostrophe |
| Missing key | `vi.getString("missing.key")` | Ném MissingResourceException |
| Missing base | `getBundle("i18n.no_such_bundle")` | Ném MissingResourceException |
| Cache | Hai lần lookup giống nhau trong fixture | Đã xác minh cache hit |
| ClassLoader path | `getResource("i18n/messages_vi.properties")` | Non-null |
| Duplicate resource entries | Hai JAR trùng file path | Detect collision, không dựa vào merging |
| Maven/Gradle final artifact | JAR do CI tạo | Entries tồn tại, chạy test bằng chính JAR |
| Named module migration | Caller named module | Không gọi `Control` overload |
| Translation completeness | Các keys bắt buộc của từng ngôn ngữ | Report thiếu translation theo policy |

### CI nên test từ JAR, không chỉ source directory

Có thể tạo JAR rồi chạy `java -cp ...` với explicit JVM startup flags. Test phải kiểm tra:

- Process exit status.
- Stdout chính xác ở positive fixture.
- MissingResourceException và failure exit ở negative fixture.
- File entries trong JAR.
- Resource encoding và characters sau khi load.
- Behavior trong một môi trường clean, tránh cache/test contamination từ JVM đã chạy lâu.

Với cùng test fixture Java ở phần 7, stdout chính xác là 15 dòng PASS và `passed=15`, không phụ thuộc locale mặc định vì demo dùng no-default-locale-fallback Control.

## 18. Lỗi thường gặp và cách tránh

**Lỗi 1: truyền tên file thay vì base name.**  
Sai `"i18n/messages_vi.properties"`, đúng `"i18n.messages"` cộng với `Locale`.

**Lỗi 2: có file trên disk nhưng không có trong runtime classpath.**  
`javac` không tự copy resources; Maven/Gradle phải package thành artifact; nếu dùng CLI, copy thủ công.

**Lỗi 3: chỉ đưa app-code.jar lên `-cp`.**  
Resource family nằm trong translations.jar, nên phải thêm JAR đó vào runtime classpath.

**Lỗi 4: dùng sai phân cách classpath.**  
Windows `;`, Linux/macOS `:`. Quote chuỗi trong PowerShell.

**Lỗi 5: sai tên suffix locale.**  
`messages_vi_VN.properties` không phải `messages_vi-vn.properties`. Tên file có thể case-sensitive.

**Lỗi 6: tưởng locale yêu cầu luôn là locale bundle thực tế.**  
`getLocale()` có thể chỉ parent/root/default fallback; test nó.

**Lỗi 7: hiểu `getNoFallbackControl` là chặn parent lookup.**  
Nó chặn fallback sang **JVM default locale**, không chặn `vi_VN → vi → root`.

**Lỗi 8: dùng `Locale.setDefault` cho từng request.**  
Default locale thuộc toàn JVM, dễ ảnh hưởng nhiều threads. Truyền explicit locale.

**Lỗi 9: dùng `Properties.load(InputStream)` và cho rằng nó có cùng charset contract như `PropertyResourceBundle`.**  
Đọc Javadoc đúng API. Khi cần strict UTF-8 cho bundles, cấu hình system property trước khi load.

**Lỗi 10: format `MessageFormat` pattern có apostrophe sai.**  
`It''s` trong pattern mới tạo `It's`. Test từng translated pattern chứa `'` và `{0}`.

**Lỗi 11: chỉ test `containsKey` rồi bảo đảm dịch đủ.**  
Key có thể đến từ root parent; coverage cần test trực tiếp nguồn bản dịch theo policy.

**Lỗi 12: cho rằng ResourceBundle tự reload khi chỉnh file.**  
Cache mặc định; dùng cache invalidation/reload policy hoặc deploy lại.

**Lỗi 13: class loader plugin không thấy resources của plugin khác.**  
Truyền đúng loader hoặc thiết kế ownership rõ. `ResourceBundle.getBundle` không mặc định tìm mọi JAR đang tồn tại.

**Lỗi 14: hai JAR cùng chứa resource path và mong keys được merge.**  
Không có merge tự động. Phát hiện collision trong build pipeline.

**Lỗi 15: chuyển nguyên `Control` vào named module.**  
Overloads nhận Control không hỗ trợ trong named modules, cần module-aware API/provider.

**Lỗi 16: hard-code tiếng Việt trong business logic.**  
Để message ở resource family, giữ logic và error codes độc lập ngôn ngữ.

**Lỗi 17: dùng `String.format` cho mẫu `{0}` của MessageFormat.**  
Hai APIs dùng placeholder syntax khác nhau. Lấy template từ ResourceBundle và format đúng công cụ.

**Lỗi 18: xem bundle resources là nơi giấu secrets.**  
JAR contents có thể được đọc. Secret/config management phải là cơ chế khác.

**Lỗi 19: ép một method `MessageFormat` mutable dùng chung mọi threads.**  
Không mặc định thread-safe; tạo formatter theo call hoặc kiểm soát concurrency.

**Lỗi 20: bỏ kiểm tra artifact package cuối.**  
Build/test trong IDE có thể pass vì IDE thêm resource directory, còn release JAR có thể thiếu `i18n`; chạy integration test trên artifact.

## 19. Câu hỏi tự kiểm tra

**1. Với base name `i18n.messages` và locale `vi-VN`, tên file vùng phù hợp là gì?**  
`i18n/messages_vi_VN.properties` tại root của một classpath entry.

**2. Vì sao không truyền `src/main/resources/i18n/messages` làm base name?**  
`src/main/resources` là source path, không phải runtime resource path.

**3. Khi `vi_VN` thiếu key greeting nhưng `vi` có key, ứng dụng lấy ở đâu?**  
Từ bundle parent `vi`.

**4. `Control.getNoFallbackControl` có chặn root key fallback không?**  
Không. Nó chặn xét **default locale của JVM** khi lookup, vẫn dùng parent chain.

**5. `getBundle` thành công nhưng `getString("unknown")` có thể fail không?**  
Có, nếu key không ở bundle/parents; nó ném `MissingResourceException`.

**6. Java hiện đại có cần `native2ascii` cho toàn bộ tiếng Việt trong `.properties` không?**  
Không. `PropertyResourceBundle` từ Java 9 đọc UTF-8 mặc định; có policy fallback nếu bytes lỗi.

**7. Vì sao phải dùng `MessageFormat` thay vì nối chuỗi với `+` cho mọi bản dịch?**  
Các ngôn ngữ có trật tự từ khác nhau, và template có placeholders/locale-aware formatting.

**8. Pattern `It''s ready for {0}.` tạo output gì khi input là `Lan`?**  
`It's ready for Lan.`

**9. Muốn class JAR và translation JAR riêng, CLI cần gì?**  
Cả hai trên runtime classpath, phân tách bằng `:` hoặc `;` theo OS.

**10. Dùng `java -cp app-all.jar Main` có bắt buộc JAR manifest `Main-Class` không?**  
Không. `-cp` và main class explicit là đủ; `java -jar` mới cần executable JAR manifest.

**11. Vì sao `getResource(...) != null` chưa đủ để kết luận mọi lookup ResourceBundle đúng?**  
Nó chỉ kiểm tra path cụ thể trong class loader; còn base name, locale, fallback, format, cache và module context.

**12. Khi chuyển từ classpath sang named module, có giữ nguyên mọi overload `getBundle(..., Control)` không?**  
Không. Cần dùng module-aware API và `ResourceBundleProvider` khi thích hợp.

**13. Tại sao ứng dụng HTTP không nên gọi `Locale.setDefault()` cho từng request?**  
Vì ảnh hưởng global state của JVM và các request khác.

**14. Muốn phát hiện file bị bỏ quên khi deploy, kiểm tra gì?**  
JAR entries và integration test từ artifact đã package, không chỉ source tree.

**15. `ResourceBundle.clearCache` có làm xuất hiện file trong JAR chưa được đưa vào classpath không?**  
Không. Cache khác khả năng nhìn thấy resources của loader.

## Tài liệu chính thức đang được duy trì

- [Oracle Java SE 26 — `ResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): candidate locale lookup, parent key fallback, caching, ClassLoader, named modules và Control.
- [Oracle Java SE 26 — `ResourceBundle.Control`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): `FORMAT_PROPERTIES`, `getNoFallbackControl`, TTL và reload policy cho unnamed modules.
- [Oracle Java SE 26 — `PropertyResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8/ISO-8859-1 reading behavior, strict charset property.
- [Oracle Java SE 26 — `MessageFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/MessageFormat.html): patterns, quoting apostrophe, locale và thread-safety.
- [Oracle Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `forLanguageTag` và default locale.
- [Oracle Java SE 26 — `ResourceBundleProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): provider mechanism cho JPMS.
- [Oracle Java SE 26 — Internationalization Guide](https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.pdf): i18n API, property resource encoding, classpath và modules.

**Kết luận:** Trong một ứng dụng classpath Java hiện đại, ResourceBundle hoạt động tốt khi **base name, locale, file paths, encoding và runtime classpath được quản lý rõ ràng**. Viết test cho locale/key fallback, đóng gói resources từ JAR thật, và sử dụng `MessageFormat` khi có parameters. Khi chuyển sang named modules, đọc lại module-specific API thay vì mang nguyên `Control` từ classpath.
