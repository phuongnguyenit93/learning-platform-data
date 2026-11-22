# Kiểm thử chuỗi dự phòng, thiếu bundle và thiếu khóa trong Java ResourceBundle

## 1. Vì sao fallback localization phải được kiểm thử?

Một ứng dụng đa ngôn ngữ có thể hiển thị tiếng Anh, tiếng Việt, tiếng Pháp hoặc nhiều biến thể vùng như `fr-CA` và `fr-FR`. Thông điệp của ứng dụng thường được lưu dưới dạng **resource bundle**, và Java cung cấp `java.util.ResourceBundle` để chọn bản dịch phù hợp theo `Locale`.

Rủi ro không chỉ là “file dịch có tồn tại không?”. Một ứng dụng có thể chạy không báo lỗi nhưng:

- Người dùng yêu cầu `fr-CA`, trong khi một số khóa phải lấy từ `fr` hoặc bundle gốc.
- Người dùng yêu cầu `de-DE` nhưng ứng dụng **vô tình sử dụng bản dịch tiếng Anh** vì ngôn ngữ mặc định của JVM là `en`.
- Có bundle đúng locale, nhưng thiếu một khóa quan trọng; Java âm thầm tra **parent bundle** và trả thông điệp gốc.
- Không có bundle nào khớp, làm `ResourceBundle.getBundle(...)` ném `MissingResourceException`.
- Bundle được tìm thấy nhưng `getString(key)` ném `MissingResourceException` vì khóa không tồn tại trong toàn bộ chuỗi cha.
- File dịch được đóng gói trên máy phát triển nhưng bị bỏ khỏi JAR/runtime production, dẫn đến lỗi chỉ xuất hiện sau triển khai.
- Một bản dịch được sửa nhưng ứng dụng vẫn dùng bundle cũ do cache.
- QA chỉ kiểm tra “`getBundle` thành công” nên không phát hiện ngôn ngữ hiển thị sai hoặc khóa quan trọng không được dịch.

Bài này hướng dẫn **kiểm thử chuỗi dự phòng, thiếu bundle và thiếu khóa** bằng Java 17+, gồm những test thực sự chạy được, cách đọc `getLocale()`, ý nghĩa `containsKey()` và `keySet()`, các chế độ fallback và quy trình kiểm tra resource bundles tại build/CI.

**Ý chính:** “Tìm thấy bundle”, “có khóa”, “khóa có bản dịch đúng locale” và “chuỗi hiển thị đúng” là **bốn điều kiện khác nhau**. Cần kiểm chứng đúng điều kiện mà sản phẩm yêu cầu, không suy ra chúng tương đương.

## 2. ResourceBundle là gì?

`ResourceBundle` cung cấp một tập các giá trị được tra bằng **key** và được lựa chọn theo `Locale`. Ví dụ ứng dụng có các file:

```text
messages.properties
messages_en.properties
messages_fr.properties
messages_fr_CA.properties
```

Tên cơ sở (*base name*) là `messages`. Trong ứng dụng Java nằm trong package `com.example.i18n`, tên có thể là `com.example.i18n.messages`, tương ứng với các file dưới đường dẫn package.

Một lời gọi điển hình:

```java
Locale requested = Locale.CANADA_FRENCH;
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", requested);

String title = bundle.getString("title");
```

Đây là **mảnh mã** cần import `java.util.Locale` và `java.util.ResourceBundle`.

Điều cần tách biệt:

- `"messages"` là **base name** của bundle; không phải key.
- `Locale.CANADA_FRENCH` tương ứng `fr-CA`, là **locale được yêu cầu**.
- `bundle.getLocale()` cho biết **locale của bundle thực tế được chọn** ở đầu chuỗi tra cứu, không nhất thiết bằng locale yêu cầu.
- `bundle.getString("title")` lấy một giá trị theo key, và có thể tìm tiếp ở **bundle cha** nếu bundle hiện tại không khai báo key đó.

Đối với các bundle `.properties`, giá trị thường là `String`. Java còn hỗ trợ bundle dạng class (ví dụ `ListResourceBundle`). Việc chọn định dạng và triển khai liên quan đến class loader, module và cơ chế load; những ví dụ thực hành trong bài dùng **bundle .properties trên classpath** để quan sát rõ fallback.

## 3. Hai loại fallback phải phân biệt

Có **hai cơ chế thường bị gọi chung là “fallback”**, nhưng tác động khác nhau.

### 3.1. Fallback trong chuỗi bundle cha

Giả sử một bundle `messages_fr_CA.properties` tồn tại nhưng không có key `shared`. Khi gọi `getString("shared")`, Java có thể tìm trong bundle cha `messages_fr.properties` và tiếp tục đến `messages.properties`.

Đây là **key inheritance/parent lookup**.

Ví dụ:

```text
messages_fr_CA.properties
    title=Titre CA

messages_fr.properties
    title=Titre FR
    onlyFr=Seulement FR

messages.properties
    title=Base title
    shared=Base shared
    onlyBase=Base only
```

Với `fr-CA`:

| Key | Nguồn giá trị | Kết quả |
|---|---|---|
| `title` | `messages_fr_CA.properties` | `Titre CA` |
| `onlyFr` | `messages_fr.properties` | `Seulement FR` |
| `shared` | `messages.properties` | `Base shared` |
| `onlyBase` | `messages.properties` | `Base only` |

**Điểm tinh tế:** mặc dù `shared` đến từ root bundle, `bundle.getLocale()` vẫn có thể trả `fr-CA` vì đó là locale của bundle được chọn để bắt đầu tra cứu. `getLocale()` **không** trả “nguồn locale của key vừa đọc”.

### 3.2. Fallback của toàn bộ bundle sang default Locale

Nếu Java không tìm được bundle phù hợp cho locale được yêu cầu, cơ chế mặc định có thể thử **locale mặc định của JVM** rồi mới chọn root bundle. Ví dụ:

- Yêu cầu `de-DE`.
- Default locale của JVM là `en`.
- Có `messages_en.properties`.
- Không có `messages_de_DE.properties` hoặc `messages_de.properties`.

Khi đó `getBundle("messages", Locale.GERMANY)` có thể trả **bundle tiếng Anh**, thậm chí khi `messages.properties` cũng có mặt.

Đây là **default-locale fallback**, một lựa chọn bundle khác với việc một key riêng lẻ rơi về parent.

Hai cơ chế có tác động sản phẩm rất khác nhau:

- Parent lookup giúp tái sử dụng các key chung và bản dịch cơ sở.
- Default-locale fallback có thể khiến toàn bộ lựa chọn locale yêu cầu bị đổi sang locale mặc định của tiến trình.

Nếu sản phẩm chỉ cho phép locale được yêu cầu hoặc root, có thể dùng `ResourceBundle.Control.getNoFallbackControl(...)` trong các tình huống API hỗ trợ. Nhưng cần hiểu chính xác: **NoFallbackControl tắt fallback sang default locale; nó không tự loại bỏ root bundle hoặc key inheritance.**

## 4. Chuỗi candidate locales: fr-CA → fr → ROOT

Với base name `messages` và locale `fr-CA`, một chuỗi candidate điển hình là:

```text
messages_fr_CA.properties
          |
          v
messages_fr.properties
          |
          v
messages.properties
```

Trong Java, `Locale.ROOT` đại diện candidate gốc (không có language/region cụ thể). Đối với ví dụ này, `ResourceBundle.Control` mặc định cho danh sách:

```text
fr-CA
fr
und
```

Trong đó `und` là kết quả của `Locale.ROOT.toLanguageTag()`. Giá trị `und` **không phải tên suffix file `messages_und.properties`** trong sơ đồ này: bundle gốc ở `messages.properties`.

Một cách kiểm tra candidate list cho các bundle classpath:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

for (Locale candidate :
        control.getCandidateLocales(
                "messages", Locale.CANADA_FRENCH)) {
    System.out.println(candidate.toLanguageTag());
}
```

Mã trên là **mảnh ví dụ**, cần import `java.util.ResourceBundle` và `Locale`.

Lưu ý:

- Candidate locales có thể phức tạp hơn sơ đồ `language_REGION → language → root`, ví dụ khi có script, variant và các trường hợp ngôn ngữ đặc biệt.
- `ResourceBundle.Control` là API cho một số overload/classpath/unnamed-module; overload nhận `Control` có hạn chế với **named modules**. Không áp mẫu classpath của bài này cho mọi ứng dụng JPMS mà không xem lại hợp đồng API.
- `getCandidateLocales(...)` mô tả **danh sách thử cho locale mục tiêu**, không bao gồm riêng bước fallback sang default locale khi vòng chọn ban đầu không tìm được bundle thích hợp.
- `getBundle` có thể dùng bundle dạng class lẫn property tùy cấu hình; bài này chọn `FORMAT_PROPERTIES` khi cần kiểm tra chính xác phần resource dạng file.

## 5. Chuẩn bị bộ file .properties cho bài thực hành

Tạo một thư mục trống riêng cho bài kiểm thử, ví dụ `bundle-demo`. Tất cả file sau nằm **cùng thư mục** với class demo, hoặc trên classpath tương ứng khi biên dịch/chạy.

Cấu trúc:

```text
bundle-demo/
├── BundleFallbackTests.java
├── messages.properties
├── messages_en.properties
├── messages_fr.properties
├── messages_fr_CA.properties
├── labels_en.properties
└── labels_fr.properties
```

### File messages.properties — root bundle

```properties
title=Base title
shared=Base shared
onlyBase=Base only
```

### File messages_en.properties — tiếng Anh

```properties
title=English title
```

### File messages_fr.properties — tiếng Pháp

```properties
title=Titre FR
onlyFr=Seulement FR
```

### File messages_fr_CA.properties — tiếng Pháp Canada

```properties
title=Titre CA
```

### File labels_en.properties — bundle không có root

```properties
language=English
```

### File labels_fr.properties — bundle không có root

```properties
language=Francais
```

Chúng ta cố tình thiết kế:

- `messages` **có root**, có `en`, `fr` và `fr-CA`, nhưng **không có de**.
- `labels` **không có root**, có `en` và `fr`, nhưng **không có de**.
- Một số key chỉ nằm trong bundle cha; một key `notThere` thì **không có trong bất kỳ file nào**.

Bộ dữ liệu này giúp quan sát rõ từng tình huống, tránh test sai vì file root hoặc default locale xuất hiện ngoài ý muốn.

Ví dụ dùng ký tự ASCII để stdout dễ tái lập. Trong dự án thật, `.properties` có thể chứa tiếng Việt có dấu. Trên Java 17, cơ chế nạp `ResourceBundle` cho properties theo mặc định có quy tắc encoding UTF-8 và fallback xử lý encoding theo API; không nên đánh đồng với mọi overload của `java.util.Properties.load(...)`. Hãy test với **đường nạp thực tế** và kiểm soát encoding của tool build.

## 6. Java 17+: kiểm thử đầy đủ 13 tình huống

Tạo file `BundleFallbackTests.java` với nội dung sau. Đây là chương trình độc lập, chỉ dùng Java SE, không cần JUnit.

```java
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.MissingResourceException;

public class BundleFallbackTests {
    private static int passed;

    private static void eq(
            String name, String expected, String actual) {

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected +
                    " actual=" + actual);
        }

        System.out.println("PASS " + name + "=" + actual);
        passed++;
    }

    private static void missing(
            String name, Runnable task) {

        try {
            task.run();
            throw new AssertionError(
                    "Expected missing: " + name);
        } catch (MissingResourceException expected) {
            System.out.println(
                    "PASS " + name + "=MissingResourceException");
            passed++;
        }
    }

    public static void main(String[] args) {
        // Chỉ dùng trong JVM thử nghiệm độc lập.
        Locale.setDefault(Locale.ENGLISH);

        ResourceBundle ca = ResourceBundle.getBundle(
                "messages", Locale.CANADA_FRENCH);

        eq("selected",
                "fr-CA",
                ca.getLocale().toLanguageTag());

        eq("specific",
                "Titre CA",
                ca.getString("title"));

        eq("parent-fr",
                "Seulement FR",
                ca.getString("onlyFr"));

        eq("root-key",
                "Base shared",
                ca.getString("shared"));

        eq("contains-root",
                "true",
                Boolean.toString(ca.containsKey("onlyBase")));

        missing("missing-key",
                () -> ca.getString("notThere"));

        ResourceBundle de = ResourceBundle.getBundle(
                "messages", Locale.GERMANY);

        eq("default-fallback-locale",
                "en",
                de.getLocale().toLanguageTag());

        eq("default-fallback-value",
                "English title",
                de.getString("title"));

        ResourceBundle no = ResourceBundle.getBundle(
                "messages",
                Locale.GERMANY,
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));

        eq("no-default-fallback-locale",
                "und",
                no.getLocale().toLanguageTag());

        eq("no-default-fallback-value",
                "Base title",
                no.getString("title"));

        ResourceBundle label = ResourceBundle.getBundle(
                "labels", Locale.GERMANY);

        eq("labels-default-fallback",
                "English",
                label.getString("language"));

        missing("labels-no-fallback",
                () -> ResourceBundle.getBundle(
                        "labels",
                        Locale.GERMANY,
                        ResourceBundle.Control.getNoFallbackControl(
                                ResourceBundle.Control.FORMAT_PROPERTIES)));

        missing("bundle-absent",
                () -> ResourceBundle.getBundle(
                        "absent", Locale.FRANCE));

        System.out.println("TOTAL=" + passed);
    }
}
```

Biên dịch và chạy, trong thư mục chứa toàn bộ file:

```bash
javac BundleFallbackTests.java
java -cp . BundleFallbackTests
```

Output **đã biên dịch và chạy thành công bằng JDK**:

```text
PASS selected=fr-CA
PASS specific=Titre CA
PASS parent-fr=Seulement FR
PASS root-key=Base shared
PASS contains-root=true
PASS missing-key=MissingResourceException
PASS default-fallback-locale=en
PASS default-fallback-value=English title
PASS no-default-fallback-locale=und
PASS no-default-fallback-value=Base title
PASS labels-default-fallback=English
PASS labels-no-fallback=MissingResourceException
PASS bundle-absent=MissingResourceException
TOTAL=13
```

Nếu chạy trong IDE, thiết lập working directory/classpath sao cho file `.properties` nằm trên **classpath**, không chỉ là các file tùy ý nằm đâu đó trên ổ đĩa. Đối với chương trình này, run trên classpath trực tiếp giúp Java tìm được các resource cùng package mặc định.

**Lưu ý kiểm thử:** `Locale.setDefault(Locale.ENGLISH)` chỉ nhằm cố định kết quả trong một JVM demo tách biệt. Đây là **global mutable state**, không phải cách chọn locale cho từng request trong production. Unit test chung JVM với test khác nên lưu và khôi phục default locale trong `try/finally` hoặc, tốt hơn, chạy test cần thay global defaults trong process riêng.

## 7. Giải thích từng nhóm assertion

### 7.1. Bundle cụ thể được chọn: fr-CA

`ResourceBundle.getBundle("messages", Locale.CANADA_FRENCH)` trả bundle có locale `fr-CA`, vì file `messages_fr_CA.properties` tồn tại.

`eq("selected", "fr-CA", ...)` xác nhận **bundle được chọn**, còn `eq("specific", "Titre CA", ...)` xác nhận value của một key được cung cấp trực tiếp trong bundle này.

Cả hai assertion cần thiết: `getLocale()==fr-CA` không chứng minh **mọi key** đều có bản dịch tại `fr-CA`.

### 7.2. Một key được lấy từ cha fr

`onlyFr` không có trong `messages_fr_CA.properties` nhưng có trong `messages_fr.properties`. Vì vậy:

```text
getString("onlyFr") => Seulement FR
```

Test này xác nhận đường **key inheritance** của `fr-CA → fr`.

### 7.3. Một key được lấy từ root

`shared` và `onlyBase` chỉ có trong `messages.properties`. Vậy:

```text
getString("shared") => Base shared
containsKey("onlyBase") => true
```

Cả hai vẫn đúng khi bundle được chọn là `fr-CA`.

**Quan trọng:** `containsKey("onlyBase")` là `true` **dù key chỉ nằm ở root**. `containsKey` không phải API kiểm tra “key có bản dịch riêng trong locale hiện tại không?”.

Tương tự, `keySet()` và `getKeys()` có thể bao gồm những key kế thừa từ parent. Nếu bộ kiểm thử yêu cầu **mỗi locale phải dịch đầy đủ**, không thể chỉ chạy `bundle.keySet().contains(key)` rồi kết luận key đó được dịch tại locale hiện tại.

### 7.4. Thiếu key trong mọi bundle

`notThere` không nằm trong bundle `fr-CA`, `fr`, `root`. Vì vậy:

```text
ca.getString("notThere") => MissingResourceException
```

Lỗi này xảy ra ở **lúc truy xuất key**, không phải vì `getBundle("messages", fr-CA)` thất bại. Test phải phân biệt **missing bundle** và **missing key** ngay ở điểm gọi tương ứng.

### 7.5. Default-locale fallback thay cho locale được yêu cầu

Với `Locale.GERMANY` (`de-DE`), không có bundle `de` hoặc `de-DE`. Bởi default locale của JVM đã đặt là `en` và có `messages_en.properties`, Java chọn bundle tiếng Anh:

```text
requested: de-DE
selected:  en
title:     English title
```

Điều này quan trọng vì `messages.properties` vẫn tồn tại! Không nên tự kết luận “không có German thì Java chắc chắn chọn root”. Trong trường hợp này, **default-locale fallback ưu tiên bản tiếng Anh**.

Ứng dụng có thể thấy kết quả hợp lệ về kỹ thuật, nhưng không đúng chiến lược localization mong muốn. Vì vậy, test bắt buộc locale nào **không được rơi về default locale khác** phải xác nhận `getLocale()` hoặc dùng chính sách lookup không fallback sang default.

### 7.6. NoFallbackControl không loại bỏ root

Khi dùng:

```java
ResourceBundle.Control.getNoFallbackControl(
        ResourceBundle.Control.FORMAT_PROPERTIES)
```

với `messages` và `de-DE`, output trong ví dụ:

```text
no-default-fallback-locale=und
no-default-fallback-value=Base title
```

`und` ở đây biểu diễn `Locale.ROOT`. Lý do:

- Không tìm `de-DE` hoặc `de`.
- Không thử lại với default locale `en`.
- Nhưng `messages.properties` là **root bundle hợp lệ**, nên nó vẫn có thể được chọn.

**NoFallbackControl không đồng nghĩa “strict exact locale only”.** Nó chỉ chặn **fallback sang default locale**, không cấm root, không cấm lookup qua parent bundle. Nếu bài toán yêu cầu **không bao giờ dùng root hoặc parent**, cần validation cụ thể về locale và nguồn từng key, không chỉ đổi control.

### 7.7. Thiếu root cho phép thử rõ lỗi missing bundle

Bộ `labels` chỉ có `labels_en.properties` và `labels_fr.properties`.

Với default locale en, yêu cầu `de-DE` sẽ fallback sang `labels_en.properties` và lấy `English`.

Khi dùng `getNoFallbackControl(FORMAT_PROPERTIES)` cho yêu cầu `de-DE`, không có `labels_de_DE`, `labels_de` hoặc `labels.properties`, và default en đã bị chặn. Kết quả:

```text
MissingResourceException
```

Trường hợp này thể hiện **missing bundle đúng nghĩa** dù file `labels_en.properties` có mặt trên classpath.

### 7.8. Base name không tồn tại

Không có file hay class phù hợp cho `absent`. Vì vậy:

```java
ResourceBundle.getBundle("absent", Locale.FRANCE);
```

ném `MissingResourceException`. Test kiểm tra đúng loại lỗi ở bước tìm bundle. Không nên bắt lỗi này rồi gọi `getString` trên một biến bundle chưa được khởi tạo.

## 8. MissingResourceException: hai thời điểm lỗi khác nhau

`MissingResourceException` có thể xuất hiện khi:

**A. Không tìm được bundle nào thỏa điều kiện lựa chọn**

```java
ResourceBundle missing =
        ResourceBundle.getBundle("absent", Locale.FRANCE);
```

**B. Bundle tìm được, nhưng toàn bộ chuỗi tra cứu thiếu một key**

```java
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "messages", Locale.CANADA_FRENCH);

String value = bundle.getString("notThere");
```

Cả hai là mảnh mã minh họa có thể ném `MissingResourceException`, nhưng thông điệp vận hành khác nhau:

| Lỗi | Nguyên nhân thường gặp | Điều cần kiểm tra |
|---|---|---|
| Missing bundle | Base name sai, thiếu tài nguyên trên classpath/module, locale fallback bị chặn và không có root | Đường dẫn, package, JAR/module, default locale và control |
| Missing key | Bundle đã nạp, không có key trong bundle và các parent | Tên key, bản dịch, root bundle, chính sách key bắt buộc |
| Có giá trị nhưng sai ngôn ngữ | Default-locale fallback hoặc parent lookup không mong muốn | `getLocale()`, chính sách locale, nguồn từng key và output |
| Có giá trị nhưng nội dung sai | Bản dịch cũ, whitespace/placeholder/encoding sai | Test snapshot/argument-contract và quy trình QA bản dịch |

Để viết handler tốt, cần biết hành động nào đang thực hiện. Không nên trả một thông báo chung “translation failed” cho cả thiếu cả bundle và thiếu một key tùy chọn.

### Có thể bắt lỗi để hiển thị dự phòng, nhưng phải có chính sách

Ví dụ một helper cho **khóa UI không trọng yếu**:

```java
static String optionalText(
        ResourceBundle bundle,
        String key,
        String fallbackText) {

    try {
        return bundle.getString(key);
    } catch (MissingResourceException e) {
        return fallbackText;
    }
}
```

Đây là mảnh mã đặt trong class có import `ResourceBundle` và `MissingResourceException`.

Nó chỉ xử lý **missing key** trên bundle đã tồn tại. Với missing bundle, cần xử lý tại lời gọi `getBundle(...)` trước đó. Đừng bắt mọi `RuntimeException` rồi coi là thiếu bản dịch: lỗi logic, `ClassCastException` hay lỗi định dạng khác cần được phát hiện rõ.

Một chiến lược tốt:

- Khóa thiết yếu như tiêu đề xác nhận thanh toán, nội dung pháp lý hoặc thông điệp an toàn: **fail QA/build** nếu thiếu.
- Khóa phụ ít quan trọng: có thể dùng fallback text đã được phê duyệt, kèm đo lường lỗi.
- Không vô tình hiển thị `null`, chuỗi rỗng hoặc key nội bộ cho người dùng nếu product contract cấm.
- Ghi telemetry kèm key/locale thực tế, nhưng tránh log dữ liệu cá nhân từ argument values.

Không nên thay toàn bộ hệ thống thiếu dịch bằng việc `catch MissingResourceException { return key; }` vì lỗi có thể bị che giấu hàng tháng.

## 9. getLocale() giúp gì và không giúp gì?

`bundle.getLocale()` cho biết locale của **bundle được load**, có thể khác locale được yêu cầu do fallback. Nó rất hữu ích cho diagnostics:

```java
Locale requested = Locale.GERMANY;
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", requested);

System.out.println(
        "requested=" + requested.toLanguageTag());
System.out.println(
        "resolved=" + bundle.getLocale().toLanguageTag());
```

Trong cấu hình demo default en và có file en, kết quả:

```text
requested=de-DE
resolved=en
```

Tuy nhiên, **getLocale không truy vết key**. Với `fr-CA`, `getLocale()==fr-CA`, dù `shared` có giá trị từ root. Nếu cần kiểm chứng “key này do file fr_CA thực sự định nghĩa”, API thông thường của `ResourceBundle` không cung cấp một `getSourceLocaleForKey(key)` công khai.

Hãy cân nhắc:

- Kiểm tra riêng nội dung các file dịch trong pipeline build.
- Sử dụng test fixture/file parsing có chủ đích để đánh giá key nào nằm trực tiếp trong từng bundle.
- Duy trì thông tin provenance khi build catalog từ hệ quản lý bản dịch.
- So sánh với tập key bắt buộc theo mỗi locale, nhưng phải **phân biệt direct keys với inherited keys**.

Không dùng `getLocale()==requested` làm bằng chứng mọi key đều được dịch đầy đủ.

## 10. containsKey(), keySet() và getKeys(): hiểu tính kế thừa

Trong `ResourceBundle`:

```java
bundle.containsKey("title");
bundle.keySet();
bundle.getKeys();
```

là những API kiểm tra các key có thể truy cập. Với chuỗi parent bundles, các kết quả có thể bao gồm **key thừa kế**.

Ví dụ `messages_fr_CA.properties` chỉ định nghĩa trực tiếp `title`, nhưng trong demo:

```text
ca.containsKey("onlyBase") == true
```

vì `onlyBase` được tìm trong `messages.properties`.

**Sai lầm kiểm thử:**

```java
if (bundle.containsKey("important")) {
    // Đánh dấu bản dịch fr-CA hoàn chỉnh.
}
```

Lý do sai: `important` có thể chỉ ở root hoặc bundle cha. Nếu chính sách sản phẩm cho phép fallback thì điều này có thể chấp nhận; nếu yêu cầu dịch riêng tại `fr-CA` thì test chưa đủ.

Một cách dùng phù hợp hơn:

- Dùng `containsKey` để biết **lookup có khả năng tìm giá trị hay không**.
- Dùng `keySet` để liệt kê **các khóa được cung cấp qua chuỗi bundle**, không để suy ra nguồn dịch trực tiếp.
- Dùng file-level inspection hoặc provenance metadata khi cần phân tích độ phủ bản dịch.
- Dùng `getString` và assertion output để xác nhận **chất lượng thông điệp**, không chỉ sự hiện diện của key.

## 11. Phân biệt root fallback và default-locale fallback bằng test rõ ràng

Để phòng nhầm lẫn, nên luôn có hai test:

**Test 1: default-locale fallback được bật**

```java
Locale.setDefault(Locale.ENGLISH);
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "messages", Locale.GERMANY);
```

Với dữ liệu demo:

```text
getLocale() = en
title = English title
```

**Test 2: default-locale fallback bị tắt**

```java
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "messages",
                Locale.GERMANY,
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));
```

Kết quả:

```text
getLocale() = ROOT (toLanguageTag() là "und")
title = Base title
```

Hai trường hợp khác nhau **dù đều có root bundle**. Nếu một test chỉ có root nhưng không có `messages_en.properties`, nó có thể không phơi bày sự khác biệt giữa chế độ có và không có default-locale fallback.

Vì vậy, fixture kiểm thử nên có **các bundle phân biệt được bằng nội dung**, ví dụ `Base title` và `English title`, để phát hiện nhánh thực tế được chọn.

## 12. Khi nào NoFallbackControl chưa đủ?

`ResourceBundle.Control.getNoFallbackControl(...)` không làm cho `getBundle` trở thành “chỉ nhận đúng locale hoàn chỉnh”.

Nó vẫn cho phép:

- Candidate parent locale, ví dụ yêu cầu `fr-CA` có thể chọn `fr` nếu file `fr_CA` thiếu.
- Root bundle `messages.properties`.
- Key inheritance từ bundle con lên bundle cha/root.

Nếu hợp đồng sản phẩm yêu cầu **locale chính xác** (ví dụ chỉ được dùng `fr-CA`, tuyệt đối không được hiển thị thông điệp tiếng Pháp chung), cần viết test/validation theo yêu cầu đó.

Một bước kiểm tra **bundle được chọn có cùng locale hay không**:

```java
Locale requested = Locale.CANADA_FRENCH;
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "messages",
                requested,
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));

if (!requested.equals(bundle.getLocale())) {
    throw new IllegalStateException(
            "Required locale was not selected");
}
```

Đây là mảnh code không xử lý tình huống `getBundle` ném `MissingResourceException`. Quan trọng hơn, ngay cả khi `bundle.getLocale()==requested`, **các key vẫn có thể đến từ cha**, nên cần thêm kiểm tra độ phủ bản dịch nếu yêu cầu strict **ở cấp key**.

Trong các ứng dụng JPMS dạng **named module**, các overload dùng `ResourceBundle.Control` có giới hạn và có thể ném `UnsupportedOperationException`. Cần sử dụng cơ chế resource bundle phù hợp với module và không sao chép máy móc các ví dụ classpath/unnamed-module.

## 13. Kiểm thử thiếu file và cách đóng gói

Không có bundle trên classpath là lỗi khác với bundle không có key. Trong dự án thật, lỗi missing bundle thường đến từ:

1. Sai base name: code gọi `"messages"` nhưng resource nằm dưới `com/example/i18n/messages.properties`.
2. Sai package hoặc tên file: `messages_fr_CA.properties` khác một tên tùy ý như `message_fr_CA.properties`.
3. File ở `src/test/resources` nhưng không được đưa vào production artifact.
4. Build plugin lọc nhầm các file `*.properties`.
5. Shading/assembly hoặc đóng gói module không giữ đúng resource path.
6. ClassLoader được chọn không nhìn thấy resource của ứng dụng.
7. Môi trường production chỉ chứa một phần resource bundles.
8. Ứng dụng thay base name giữa các version nhưng deploy chưa đồng bộ.

### Kiểm tra resource trong JAR

Một lệnh phổ biến:

```bash
jar tf app.jar
```

Hãy tìm các file như:

```text
com/example/i18n/messages.properties
com/example/i18n/messages_en.properties
com/example/i18n/messages_fr.properties
com/example/i18n/messages_fr_CA.properties
```

Việc file tồn tại trong JAR chưa chứng minh Java đang dùng đúng classloader/module hoặc có key cần thiết; nhưng nó giúp phân biệt lỗi **đóng gói** với lỗi **fallback**.

Khi có nhiều classloaders (plugin architecture, app server, custom loaders), cùng một base name có thể được tìm trong loader khác nhau. Các overload `getBundle` có thể dùng caller module/loader theo hợp đồng Java; test integration phải chạy trong cấu hình triển khai thực, không chỉ trong test classpath phẳng.

## 14. Cache: tại sao sửa file dịch mà vẫn thấy chuỗi cũ?

`ResourceBundle` có **cơ chế cache nội bộ**. Nếu một ứng dụng đã load bundle, việc sửa file `.properties` sau đó không đồng nghĩa mọi lời gọi `getBundle` sẽ lập tức thấy nội dung mới.

Ví dụ:

```java
ResourceBundle first =
        ResourceBundle.getBundle(
                "messages", Locale.FRENCH);
```

Nếu file được sửa trong lúc ứng dụng còn chạy, `ResourceBundle.getBundle(...)` có thể tiếp tục dùng dữ liệu đã được cache theo loader, locale và chính sách kiểm soát tương ứng.

Các phương thức liên quan:

```java
ResourceBundle.clearCache();
ResourceBundle.clearCache(classLoader);
```

Nhưng **clearCache không phải cơ chế hot reload bản dịch tổng quát**. Cần hiểu class loader, module, cách tài nguyên được phân phối, TTL và bộ nhớ đệm riêng của ứng dụng. Nếu app đã lưu một biến static trỏ tới `ResourceBundle` cũ, clear cache không tự đổi biến static đó.

Trong kiểm thử:

- Dùng resource fixtures bất biến trong một test run khi có thể.
- Nếu test tạo/sửa file trong runtime, quản lý classloader và bundle cache có chủ đích.
- Tránh phụ thuộc vào thứ tự chạy của các test có cùng base name và default locale.
- Tách integration test reload ra khỏi unit test lookup cơ bản.
- Đừng “fix” lỗi missing key bằng cách luôn xóa cache trong mỗi request; giải quyết đúng vấn đề tài nguyên và vòng đời deploy.

`ResourceBundle.Control` còn có cơ chế TTL và reload cho những tình huống được API hỗ trợ; thiết kế reload cần xét cả hiệu năng và tính nhất quán dữ liệu dịch.

## 15. Kiểm thử encoding và ký tự có dấu

Bundle tiếng Việt, Pháp hoặc Nhật thường có ký tự Unicode. Một lỗi encoding có thể khiến **bundle và key đều tồn tại**, nhưng output sai, ví dụ chữ bị mất dấu hoặc xuất hiện ký tự thay thế.

Khi dùng file `.properties` trong Java 17:

- Đảm bảo encoding file trong repository/build đúng hợp đồng.
- Với `ResourceBundle` mặc định, Java 9+ có quy tắc đọc UTF-8 và xử lý fallback encoding theo API; không đánh đồng với việc đọc `Properties.load(InputStream)`.
- Nếu ứng dụng dùng custom `ResourceBundle.Control` hoặc helper tự nạp file, kiểm tra encoding mà helper thực sự dùng.
- Với chuỗi có dấu, assert **chính xác ký tự** và whitespace trong output; tránh chỉ kiểm tra “không rỗng”.
- Nếu dùng MessageFormat sau khi lấy chuỗi từ bundle, còn phải kiểm tra cú pháp placeholder/nháy đơn — đó là một lớp lỗi **riêng** với missing key.

Ví dụ một giá trị như:

```properties
title=Thông báo
```

nên được kiểm tra bằng cùng JDK/runtime, classloader và cơ chế nạp sẽ dùng trong production. Chỉ có `containsKey("title")==true` không chứng minh text hiển thị đúng tiếng Việt.

## 16. ResourceBundle và MessageFormat: key tồn tại chưa đủ

Ứng dụng thường làm:

```java
String pattern = bundle.getString("invoice.summary");
String result = new MessageFormat(pattern, locale)
        .format(new Object[]{count, amount});
```

Hai mảnh API có hai nguồn lỗi độc lập:

1. `bundle.getString(...)` có thể bị missing key hoặc fallback sang bản dịch khác.
2. `MessageFormat` có thể nhận pattern sai cú pháp hoặc pattern hợp lệ nhưng placeholder bị vô hiệu vì dấu nháy đơn chưa escape.

Vì vậy, ma trận QA locale cần kết hợp:

- Bundle được chọn đúng không?
- Key bắt buộc có thể truy cập không?
- Key có nguồn dịch đúng yêu cầu không?
- Pattern có hợp lệ không?
- Placeholder index/type có đúng không?
- Định dạng số/ngày theo locale có đúng không?
- Output sau format có đúng text, thứ tự tham số và dấu câu không?

Khi fallback xảy ra, thông điệp có thể dùng **ngôn ngữ của bundle cha**, trong khi ứng dụng truyền locale **của người dùng** cho `MessageFormat`. Điều này có thể tạo ra hỗn hợp: văn bản root English nhưng số theo locale French. Hệ thống phải xác định chính sách chấp nhận hay từ chối cách hiển thị đó.

Không tự động suy ra locale của pattern bằng `bundle.getLocale()` cho từng key kế thừa, vì giá trị có thể đến từ cha sâu hơn. Đối với các thông điệp nhạy cảm về văn phong, cần quản lý provenance bản dịch ở tầng catalog nếu quan trọng.

## 17. Mô hình fallback trong ứng dụng phải là quyết định sản phẩm

Không có một chính sách duy nhất phù hợp mọi hệ thống.

### Phương án A: cho phép root fallback

Thích hợp khi root bundle là bản dịch được phê duyệt (ví dụ English), và một số bản địa hóa có thể chưa đầy đủ. Ưu điểm là ứng dụng không sập khi thiếu một key ở locale con.

Rủi ro: giao diện trộn ngôn ngữ, người dùng có thể thấy câu chưa được dịch. Cần ghi nhận coverage và giữ danh sách những key bắt buộc phải dịch.

### Phương án B: không cho fallback sang default JVM

Dùng `getNoFallbackControl` khi mô hình classpath cho phép, hoặc thiết kế lookup tương đương trong hệ thống bundle khác. Ưu điểm là tránh phụ thuộc vào ngôn ngữ mặc định của server khi locale yêu cầu không được hỗ trợ.

Rủi ro: vẫn có root fallback. Không thể tuyên bố strict exact locale chỉ nhờ control này.

### Phương án C: chỉ cho phép những locale đã được sản phẩm công bố

Trước khi `getBundle`, kiểm tra locale yêu cầu nằm trong **allowlist** hoặc chính sách negotiation. Nếu chưa được hỗ trợ, đưa ra một locale dự phòng có chủ đích, ví dụ default sản phẩm `en-US`, thay vì dựa vào default JVM.

Lợi ích: dễ dự đoán và ít bị ảnh hưởng bởi cấu hình máy chủ. Nhưng vẫn cần test key coverage và fallback bên trong từng bundle.

### Phương án D: bắt buộc đủ key trong từng locale

Thích hợp cho thông điệp luật pháp, thanh toán, an toàn hoặc hệ thống yêu cầu dịch đầy đủ. Cần kiểm tra **direct keys** của từng catalog hoặc metadata do pipeline dịch cung cấp, và fail build nếu thiếu.

Điều này không thể thực hiện chỉ bằng `bundle.keySet()` vì kết quả có thể bao gồm inherited keys.

**Khuyến nghị:** xác định rõ locale nào được hỗ trợ, root là ngôn ngữ nào, fallback nào được phép, key nào bắt buộc, và hành vi mong muốn khi vi phạm. Sau đó viết test phản ánh đúng chính sách.

## 18. Cách viết test có thể tái lập

Vấn đề lớn trong test `ResourceBundle` là phụ thuộc **global state** và dữ liệu hệ thống.

### Cố định default Locale một cách an toàn

Trong chương trình demo độc lập, `Locale.setDefault(Locale.ENGLISH)` giúp test rõ fallback. Trong bộ unit test chạy chung JVM, cần cẩn trọng.

Mảnh mã minh họa:

```java
Locale previous = Locale.getDefault();
try {
    Locale.setDefault(Locale.ENGLISH);
    // Chạy test dựa trên default locale.
} finally {
    Locale.setDefault(previous);
}
```

Đây không phải giải pháp đầy đủ cho **parallel tests**: test khác có thể đọc default locale trong lúc nó đang bị đổi. Với test cần đổi global locale, nên dùng một JVM/process tách biệt hoặc cơ chế cô lập thích hợp của build.

### Không để file ngoài ý muốn ảnh hưởng fixture

Nếu test gọi `messages`, có thể tình cờ trùng base name với bundle từ dependency. Hãy đặt test fixtures trong package riêng để tránh collision, ví dụ `com.example.testbundles.messages`, và kiểm soát classpath.

Với chương trình đơn giản ở trên, tên `messages` trong package mặc định được dùng có chủ đích để dễ chạy. Production code nên đặt resource theo package/module rõ ràng.

### Không dùng Java system default làm oracle

Những câu trả lời như “locale dự phòng chắc chắn là tiếng Anh” chỉ đúng nếu test đã cố định default locale và có file English. Trên máy khác, default locale có thể là `vi-VN` hoặc `fr-FR`.

Để test robust, hoặc:

- Truyền `Locale` tường minh và dùng chế độ hạn chế fallback phù hợp.
- Hoặc chạy trong môi trường có default locale được kiểm soát rõ, không phụ thuộc thiết lập host.
- Hoặc assert theo chính sách fallback sản phẩm, không theo default JVM bất định.

## 19. Kiểm thử các locale đặc biệt và vùng

Không phải mọi locale chỉ có hai mức `language_REGION`. `Locale` có thể chứa script, variant và BCP 47 extensions. Ví dụ:

```text
zh-Hant-TW
sr-Latn-RS
fr-CA
en-US
vi-VN
```

Chuỗi candidate và fallback có thể phức tạp hơn `fr-CA → fr → ROOT`. `ResourceBundle.Control.getCandidateLocales(...)` có các quy tắc đặc biệt cho một số language/script. Khi cần test, dùng chính API lấy danh sách candidate thay vì tự viết dự đoán suffix.

Đồng thời, tên file trong bundle thường dùng suffix kiểu underscore theo ứng dụng (`messages_fr_CA.properties`) chứ không phải BCP 47 hyphen trực tiếp (`messages_fr-CA.properties`). Đừng tự ghép tên file từ `locale.toLanguageTag()` mà bỏ qua quy tắc `ResourceBundle`.

**Không phải mọi BCP 47 extension đều ảnh hưởng lựa chọn resource bundle theo cách bạn dự đoán.** Khi yêu cầu có numbering system/calendar extension, cần test riêng cả bundle lookup và các dịch vụ định dạng liên quan.

## 20. Những lỗi thường gặp

**1. Cho rằng getBundle thành công nghĩa là có bản dịch đúng locale.** Nó có thể chọn default locale hoặc root.

**2. Cho rằng getLocale()==requested chứng minh mọi key được dịch riêng.** Key có thể đến từ parent.

**3. Cho rằng containsKey chỉ tìm trong bundle hiện tại.** Nó có thể xem cả parent chain.

**4. Cho rằng NoFallbackControl cấm mọi fallback.** Nó chỉ cấm fallback sang default JVM, không cấm root hoặc các candidate cha.

**5. Quên bundle root cũng là fallback hợp lệ.** `messages.properties` có thể che việc thiếu file locale.

**6. Bỏ qua việc default locale có thể ưu tiên một bundle en hiện có trước root.** Đó là một nguồn hiển thị sai ngôn ngữ.

**7. Bắt MissingResourceException chung rồi nghĩ luôn thiếu cả file.** Thiếu key cũng ném cùng exception.

**8. Dùng keySet để báo bản dịch địa phương đã hoàn thiện.** Nó có thể chứa inherited keys.

**9. Không test case chỉ có bundle tiếng Anh nhưng không có root.** Đây là cách đơn giản để phơi bày default-locale fallback và lỗi missing bundle.

**10. Không phân biệt base name và key.** `messages` là base, `title` là key, chúng lỗi ở các thời điểm khác nhau.

**11. Để test bị ảnh hưởng bởi Locale.getDefault của hệ điều hành.** Kết quả khác nhau giữa CI và máy phát triển.

**12. Đổi Locale.setDefault trong test chạy song song.** Đây là global state, có thể làm test khác không ổn định.

**13. Không kiểm tra resource đã được đóng vào JAR.** Local test có file nhưng production thiếu.

**14. Sửa file trong runtime rồi mong ResourceBundle luôn tự reload.** Cơ chế cache có thể giữ bản cũ.

**15. Cho rằng mọi UTF-8/Properties API đọc file giống nhau.** Hợp đồng encoding phụ thuộc cách nạp.

**16. Chỉ test giá trị không rỗng.** Một bản dịch sai ngôn ngữ nhưng không rỗng vẫn là lỗi.

**17. Dùng một fallback text cho tất cả thông điệp quan trọng.** Có thể che thiếu dịch pháp lý hoặc an toàn.

**18. Dùng ResourceBundle.Control classpath ví dụ trong named modules mà không xem tài liệu.** Có những overload không được hỗ trợ trong named module.

**19. Quên việc parser MessageFormat có thể sai dù key có tồn tại.** Validation chuỗi dịch và validation pattern là hai bước riêng.

**20. Coi ROOT là một locale người dùng bắt buộc đã chọn.** `Locale.ROOT` là bundle cơ sở, thường không mang tên ngôn ngữ/vùng.

## 21. Checklist QA và kiểm thử hồi quy

| Trường hợp | Kỳ vọng cần xác minh |
|---|---|
| Locale cụ thể có bundle | `getLocale()` và key ưu tiên đúng |
| Locale vùng thiếu key | Tìm đúng giá trị từ parent language |
| Language bundle thiếu key | Tìm đúng giá trị root |
| Root bundle chỉ có một số key | Key khác toàn chain ném `MissingResourceException` |
| Locale yêu cầu không có bundle | Có thể fallback sang JVM default theo cấu hình |
| Locale yêu cầu không có bundle, bật no-default fallback | Không chọn bundle default locale; có thể chọn ROOT |
| Bundle chỉ có locale default nhưng không có root | Không fallback: `MissingResourceException` |
| Không có bundle với base name | `getBundle` ném `MissingResourceException` |
| `containsKey` cho inherited key | Có thể true |
| `keySet()` | Có thể chứa key từ parent |
| `getLocale()` khi key đến từ root | Vẫn phản ánh bundle được chọn |
| Resource path trong JAR/module | Đúng tên base, package, suffix locale |
| File bản dịch có Unicode | Đọc đúng encoding và ký tự |
| MessageFormat trên chuỗi từ bundle | Placeholder và loại argument đúng |
| Cache/reload | Hành vi đúng theo chính sách deploy |
| Thay đổi JVM default locale | Không vô tình đổi chính sách sản phẩm |
| Nhiều bản dịch cho cùng key | Ưu tiên candidate phù hợp |
| Bản dịch bắt buộc | Phải có trong catalog theo quy tắc coverage |

Nên đặt các ca **thiếu dữ liệu có chủ đích** vào fixture test. Một bộ file đầy đủ ở mọi locale thường **không giúp phát hiện lỗi fallback** vì không bao giờ chạy vào nhánh parent/root/default.

## 22. Bài tập tự kiểm tra

**Câu 1.** Nếu `messages_fr_CA.properties` không có key `shared`, nhưng root có, `getString("shared")` có thể thành công không?

**Đáp án:** Có. Java có thể tìm qua parent chain và lấy giá trị từ root.

**Câu 2.** Khi giá trị `shared` đến từ root, `bundle.getLocale()` chắc chắn là `Locale.ROOT` không?

**Đáp án:** Không. Nó cho locale của bundle được chọn, có thể vẫn là `fr-CA`.

**Câu 3.** `containsKey("onlyBase")` trên bundle `fr-CA` có thể trả true khi key chỉ ở root không?

**Đáp án:** Có. API xét cả các key được kế thừa.

**Câu 4.** Khi không có `messages_de_DE`/`messages_de` nhưng default locale là en và có `messages_en`, kết quả có thể là gì?

**Đáp án:** Có thể chọn bundle en; trong ví dụ JDK đã kiểm chứng, `getLocale()` trả en.

**Câu 5.** Dùng `getNoFallbackControl(...)` có ngăn không cho chọn root không?

**Đáp án:** Không. Nó ngăn fallback sang **default locale**, nhưng root và parent chain vẫn có thể được sử dụng.

**Câu 6.** Nếu chỉ có `labels_en.properties`, không có root/de, và ta yêu cầu de với NoFallbackControl thì sao?

**Đáp án:** `ResourceBundle.getBundle(...)` ném `MissingResourceException`.

**Câu 7.** `getBundle(...)` thành công, nhưng `getString("notThere")` ném exception: thiếu gì?

**Đáp án:** Thiếu **key**, không phải thiếu toàn bộ bundle.

**Câu 8.** Có nên dùng `keySet()` để khẳng định một bản dịch `fr-CA` đã dịch đủ mọi key không?

**Đáp án:** Không. Tập key có thể gồm inherited keys. Cần kiểm tra direct resources hoặc catalog metadata.

**Câu 9.** Vì sao sửa `messages_fr.properties` rồi gọi lại `getBundle` có thể vẫn thấy text cũ?

**Đáp án:** Do ResourceBundle cache. Cần chính sách reload/lifecycle rõ ràng; không nên giả định tự tải lại ngay.

**Câu 10.** Test nào giúp phát hiện default locale fallback một cách rõ nhất?

**Đáp án:** Cố định default locale trong JVM test, tạo bundle của default locale với text phân biệt root, yêu cầu một locale không có bundle rồi so `getLocale()`/output giữa chế độ mặc định và NoFallbackControl.

## 23. Kết luận

Khi kiểm thử `ResourceBundle`, đừng chỉ hỏi **“có hiển thị được chuỗi không?”**. Hãy xác định chuỗi đến từ **bundle nào**, key được tìm qua **nhánh nào**, và hành vi đó có phù hợp với chính sách localization hay không.

- `ResourceBundle.getBundle(...)` chọn bundle theo candidate locales và có thể fallback sang default locale.
- `getString(key)` có thể tìm key qua parent chain; key bị thiếu toàn chain sẽ ném `MissingResourceException`.
- `getLocale()` phản ánh bundle được chọn, **không chứng minh nguồn của từng key**.
- `containsKey()` và `keySet()` có thể bao gồm key kế thừa.
- `getNoFallbackControl(...)` chặn **default-locale fallback**, không tự cấm root hoặc parent fallback.
- Phải test cả **missing bundle**, **missing key**, **fallback hợp lệ** và **fallback sai yêu cầu**.
- Cần chạy integration tests trên artifact thật, kiểm soát classloader, encoding, cache và các thông điệp quan trọng.

**Tài liệu chính thức:** [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) · [ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html) · [MissingResourceException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/MissingResourceException.html) · [Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html).
