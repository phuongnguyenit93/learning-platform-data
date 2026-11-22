# Các trường hợp đặc biệt của tên locale và cách kiểm tra chuỗi ứng viên

## 1. Vì sao không thể suy ra chuỗi bundle chỉ bằng cách cắt hậu tố?

Trong Java, `ResourceBundle` tìm tài nguyên phù hợp với một `Locale` từ **base name** và danh sách **candidate locales** (các locale ứng viên). Với trường hợp đơn giản `vi-VN`, ta thường hình dung:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages              (ROOT)
```

Nhưng quy tắc này **chưa đủ** cho locale có script, variant, ngôn ngữ có cách đặt tên lịch sử hoặc các quy tắc đặc biệt như tiếng Hoa và tiếng Na Uy. Ví dụ `zh-TW` có thể được hiểu theo chữ phồn thể và sinh các tên chứa `Hant` dù thẻ đầu vào không ghi script.

Để chẩn đoán chính xác, không nên tự ghép tên theo `locale.toString()`, không chỉ tách `locale.toLanguageTag()` theo dấu gạch nối, và không giả định mọi `Locale` sẽ tạo danh sách dài/ngắn giống nhau. Hãy dùng chính `ResourceBundle.Control.getCandidateLocales(baseName, locale)` và `Control.toBundleName(baseName, candidate)` để quan sát thứ tự tên mà cơ chế classpath tiêu chuẩn sẽ xem xét.

Bài này tập trung vào **chuỗi ứng viên và những ngoại lệ của tên locale**. Cần phân biệt danh sách ứng viên với việc thực sự tìm được tệp bundle, với fallback sang default locale, và với việc tra cứu một khóa thông qua parent bundle.

## 2. Ba tên liên quan nhưng không đồng nhất

| Khái niệm | Ví dụ | Dùng ở đâu? |
| --- | --- | --- |
| **Language tag** | `zh-Hant-TW` | Trao đổi/biểu diễn ngôn ngữ theo BCP 47; `Locale.forLanguageTag(...)`, `toLanguageTag()` |
| **Locale instance** | Language `zh`, script `Hant`, region `TW` | Tham số cho Java API và cơ chế chọn ứng viên |
| **Bundle name** | `com.example.i18n.Messages_zh_Hant_TW` | Tên ứng viên dùng để tìm class hoặc file tài nguyên |
| **Resource path** | `com/example/i18n/Messages_zh_Hant_TW.properties` | Vị trí thực trong classpath/JAR của bundle kiểu `.properties` |

Bundle name gắn vào **base name** không chứa phần mở rộng. Với `FORMAT_PROPERTIES`, Java chuyển tên đó sang đường dẫn tài nguyên có dấu `/` và phần mở rộng `.properties`.

Điểm tinh tế: `Locale.toString()` là một cách biểu diễn để đọc/log thông tin `Locale`, **không phải hợp đồng đặt tên tệp bundle**. Ví dụ locale có script có thể được biểu diễn dạng `zh_TW_#Hant` khi gọi `toString()`, nhưng tên bundle ứng viên là `Messages_zh_Hant_TW`. Hãy gọi `Control.toBundleName(...)` để có tên thực cần tìm.

## 3. API dùng để tự kiểm tra ứng viên

Trong chế độ **classpath/unnamed module**, `ResourceBundle.Control` cung cấp:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_DEFAULT);

List<Locale> candidates =
        control.getCandidateLocales(
                "com.example.i18n.Messages",
                requested);

for (Locale candidate : candidates) {
    System.out.println(
            control.toBundleName(
                    "com.example.i18n.Messages",
                    candidate));
}
```

Đây là **đoạn mã minh họa** dùng các biến `requested` và import `Locale`, `List`, `ResourceBundle`; chương trình độc lập có thể chạy được trình bày ở phần 4.

- `getCandidateLocales(baseName, requested)` trả danh sách **có thứ tự** từ ứng viên cụ thể đến ứng viên rộng hơn, kết thúc bằng `Locale.ROOT` trong cấu hình chuẩn.
- `toBundleName(baseName, candidate)` biến từng `Locale` ứng viên thành **tên bundle** theo quy tắc Java; đây là bước nên dùng khi kiểm tra lỗi đặt tên file.
- `FORMAT_DEFAULT` có thể thử class bundle và properties bundle; chọn `FORMAT_PROPERTIES` khi chỉ cần bundle `.properties`.
- Danh sách trả về chỉ mô tả **tên được cân nhắc**. Nó không chứng minh bất kỳ tên nào tồn tại trên classpath, cũng không nói bundle nào thực sự sẽ được chọn.

**Quan trọng:** `getCandidateLocales` là một phương thức của `ResourceBundle.Control`. Các overload nhận `Control` của `ResourceBundle.getBundle` có giới hạn với **named modules**; không sao chép máy móc ví dụ này sang chương trình chạy trên module path. Cơ chế module-aware được nói rõ hơn ở phần 9.

## 4. Chương trình Java 17+ in chuỗi tên ứng viên thực tế

Tạo tệp **`CandidateNamesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class CandidateNamesDemo {
    private static final String BASE = "demo.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getControl(
                    ResourceBundle.Control.FORMAT_DEFAULT);

    private static void print(String name, Locale locale) {
        List<Locale> candidates =
                CONTROL.getCandidateLocales(BASE, locale);

        String names = candidates.stream()
                .map(candidate ->
                        CONTROL.toBundleName(BASE, candidate))
                .collect(Collectors.joining(" -> "));

        System.out.println(name + ": " + names);
    }

    public static void main(String[] args) {
        print("vi-VN", Locale.forLanguageTag("vi-VN"));
        print("zh-TW", Locale.forLanguageTag("zh-TW"));
        print("zh-CN", Locale.forLanguageTag("zh-CN"));
        print("sr-Latn-RS", Locale.forLanguageTag("sr-Latn-RS"));
        print("en-US-u-nu-thai",
                Locale.forLanguageTag("en-US-u-nu-thai"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CandidateNamesDemo.java
java -cp . CandidateNamesDemo
```

Dưới đây là các dòng đầu ra của thuật toán `Control` chuẩn trên JDK hiện đại, với chính base name `demo.Messages` được truyền vào (dòng dài được giữ nguyên):

```text
vi-VN: demo.Messages_vi_VN -> demo.Messages_vi -> demo.Messages
zh-TW: demo.Messages_zh_Hant_TW -> demo.Messages_zh_Hant -> demo.Messages_zh_TW -> demo.Messages_zh -> demo.Messages
zh-CN: demo.Messages_zh_Hans_CN -> demo.Messages_zh_Hans -> demo.Messages_zh_CN -> demo.Messages_zh -> demo.Messages
sr-Latn-RS: demo.Messages_sr_Latn_RS -> demo.Messages_sr_Latn -> demo.Messages_sr_RS -> demo.Messages_sr -> demo.Messages
en-US-u-nu-thai: demo.Messages_en_US -> demo.Messages_en -> demo.Messages
```

Chương trình này **không cần có tệp `demo/Messages*.properties`** vì chỉ liệt kê ứng viên, chưa gọi `getBundle` để nạp tài nguyên. Nếu muốn chứng minh một bundle được chọn, phải cung cấp file/class bundle thật và thực hiện `getBundle`; xem phần 8.

## 5. Những trường hợp đặc biệt cần hiểu

### 5.1. Tiếng Hoa: script được bổ sung theo vùng

Với `Locale.forLanguageTag("zh-TW")`, Java có trường hợp đặc biệt suy luận script **`Hant`** (chữ phồn thể). Do đó, thứ tự ứng viên có thể là:

```text
Messages_zh_Hant_TW
Messages_zh_Hant
Messages_zh_TW
Messages_zh
Messages
```

Tương tự, `zh-CN` được xem theo script **`Hans`** (chữ giản thể):

```text
Messages_zh_Hans_CN
Messages_zh_Hans
Messages_zh_CN
Messages_zh
Messages
```

Điều này có hai hệ quả:

1. Dù chỉ yêu cầu `zh-TW`, Java vẫn có thể dùng tài nguyên `Messages_zh_Hant.properties` nếu không có file cụ thể hơn, trước khi xét `Messages_zh_TW.properties`.
2. Đừng dựa vào việc chuỗi đầu vào không có `Hant` để kết luận các ứng viên cũng không có script.

Với thẻ `zh-Hant-TW` đã ghi script tường minh, thứ tự ứng viên cơ bản cũng bắt đầu từ `zh_Hant_TW`, rồi `zh_Hant`, `zh_TW`, `zh` và bundle gốc. Những ví dụ trên là **quy tắc ứng viên của Java**, không phải cách tuyên bố rằng mọi hệ thống người dùng Đài Loan/Trung Quốc đều có cùng một nhu cầu ngôn ngữ. Chất lượng bản dịch còn cần l10n thực tế.

### 5.2. Locale có script tường minh: script có thể đứng trước region trong thứ tự tìm

Với `sr-Latn-RS` (tiếng Serbia dùng chữ Latin tại Serbia), Java xét:

```text
Messages_sr_Latn_RS
Messages_sr_Latn
Messages_sr_RS
Messages_sr
Messages
```

Dù `sr_Latn` không chỉ rõ region, nó có thể được xét **trước** `sr_RS` vì script ảnh hưởng mạnh đến bộ chữ/khả năng sử dụng nội dung. Điều này cho thấy thứ tự fallback không đơn giản là “bỏ region trước rồi bỏ script” trong mọi trường hợp.

**Lưu ý khi đặt file:** dùng `Messages_sr_Latn_RS.properties`, không lấy chuỗi `Locale.toString()` làm tên file trực tiếp.

### 5.3. Tiếng Na Uy: `no`, `nb`, `nn` và variant lịch sử `NY`

Java giữ một số quy tắc tương thích lịch sử cho tiếng Na Uy:

- `no` là mã Norwegian nói chung.
- `nb` biểu diễn Norwegian Bokmål.
- `nn` biểu diễn Norwegian Nynorsk.
- Locale lịch sử `new Locale("no", "NO", "NY")` biểu diễn một trường hợp đặc biệt cũ liên quan đến Nynorsk.

Đối với `nb-NO`, ứng viên theo thuật toán chuẩn:

```text
Messages_nb_NO
Messages_no_NO
Messages_nb
Messages_no
Messages
```

Đối với `nn-NO`:

```text
Messages_nn_NO
Messages_nn
Messages_no_NO_NY
Messages_no_NO
Messages_no
Messages
```

Với **constructor kiểu cũ** `new Locale("no", "NO", "NY")`, chuỗi ứng viên cũng bắt đầu bằng `nn_NO`, `nn`, rồi mới tới `no_NO_NY`:

```text
Messages_nn_NO
Messages_nn
Messages_no_NO_NY
Messages_no_NO
Messages_no
Messages
```

Đây là **ngoại lệ cụ thể**, không phải quy tắc chung để `Locale` đổi mọi language thành một language khác. `NY` là variant lịch sử không đáp ứng cú pháp variant BCP 47 thông thường; vì vậy **không** dùng `new Locale.Builder().setVariant("NY")` làm ví dụ thay thế (builder có thể ném `IllformedLocaleException`). Muốn khảo sát chính xác trường hợp legacy, dùng constructor như trên hoặc một giá trị locale legacy nhận từ hệ thống cũ.

### 5.4. Các mã ngôn ngữ lịch sử và mã hiện đại

Một số mã ngôn ngữ từng dùng trong Java có dạng lịch sử:

| Dạng cũ | Dạng hiện đại tương ứng |
| --- | --- |
| `iw` | `he` (Hebrew) |
| `in` | `id` (Indonesian) |
| `ji` | `yi` (Yiddish) |

API `Locale` có quy tắc tương thích cho các mã này; chẳng hạn `Locale.forLanguageTag("iw-IL").toLanguageTag()` có thể trả `he-IL`. Tùy cách xây dựng locale và quy tắc tương thích của JDK, các tên hiển thị từ `getLanguage()`/`toString()` không phải cơ sở an toàn để bạn tự viết thuật toán đổi tên bundle.

**Thực hành đúng:** cho một locale legacy cụ thể, gọi `getCandidateLocales` và `toBundleName` trên runtime mục tiêu; sau đó kiểm tra các tên resource/class thực sự đã đóng gói. Việc file mang dạng tên cũ hay mới còn có thể liên quan tới tài nguyên đang duy trì và tương thích với JDK.

### 5.5. Variant: không phải lúc nào cũng có một hậu tố duy nhất

Với locale có variant hợp lệ, Java có thể tạo nhiều ứng viên bằng cách **cắt dần các thành phần variant** trước khi bỏ các thành phần cụ thể khác. Khi có script, danh sách có thể có cả nhánh chứa script và nhánh không chứa script.

Ví dụ nguyên tắc tên có dạng:

```text
Messages_en_US_POSIX
Messages_en_US
Messages_en
Messages
```

Danh sách thực tế phụ thuộc locale, script, variant và các trường hợp đặc biệt của Java. Đừng xây dựng fallback bằng cách liên tục gọi `lastIndexOf('_')` trên `Locale.toString()`; cách đó có thể sai thứ tự và bỏ qua nhánh như `zh_Hant` hoặc `nn_NO`.

### 5.6. Unicode locale extensions không tự biến thành hậu tố bundle

Thẻ:

```text
en-US-u-nu-thai
```

có extension `u-nu-thai` yêu cầu hệ chữ số Thai trong những API hiểu thuộc tính Unicode locale. Nhưng trong `ResourceBundle.Control.getCandidateLocales` tiêu chuẩn, phần extension này **không sinh tệp** như `Messages_en_US_u_nu_thai.properties`. Chuỗi ứng viên cơ bản là:

```text
Messages_en_US
Messages_en
Messages
```

Tương tự, thông tin như lịch `u-ca-japanese` có thể có ý nghĩa với một số dịch vụ ngày/giờ nhưng không đồng nghĩa tồn tại một bundle message riêng cho từng extension. Ứng dụng nào muốn phân biệt thông điệp theo extension phải thiết kế quy tắc riêng và kiểm thử, không suy ra tự động từ `getBundle`.

## 6. Chương trình riêng quan sát ngoại lệ của tiếng Na Uy

Tạo **`NorwegianCandidatesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class NorwegianCandidatesDemo {
    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getControl(
                    ResourceBundle.Control.FORMAT_DEFAULT);

    private static void print(String label, Locale locale) {
        String names = CONTROL
                .getCandidateLocales("demo.Messages", locale).stream()
                .map(candidate ->
                        CONTROL.toBundleName("demo.Messages", candidate))
                .collect(Collectors.joining(" -> "));
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        print("nb-NO", Locale.forLanguageTag("nb-NO"));
        print("nn-NO", Locale.forLanguageTag("nn-NO"));
        print("no_NO_NY", new Locale("no", "NO", "NY"));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 NorwegianCandidatesDemo.java
java -cp . NorwegianCandidatesDemo
```

Đầu ra của chuỗi ứng viên chuẩn:

```text
nb-NO: demo.Messages_nb_NO -> demo.Messages_no_NO -> demo.Messages_nb -> demo.Messages_no -> demo.Messages
nn-NO: demo.Messages_nn_NO -> demo.Messages_nn -> demo.Messages_no_NO_NY -> demo.Messages_no_NO -> demo.Messages_no -> demo.Messages
no_NO_NY: demo.Messages_nn_NO -> demo.Messages_nn -> demo.Messages_no_NO_NY -> demo.Messages_no_NO -> demo.Messages_no -> demo.Messages
```

Cách kiểm tra này giúp bạn không phải phỏng đoán thứ tự đặc biệt từ tên file trên đĩa. Tương tự, có thể thay giá trị `Locale` trong `print` để khảo sát các locale khác.

## 7. Chuỗi ứng viên khác với default-locale fallback

Một nhầm lẫn phổ biến là cho rằng `getCandidateLocales(...)` đã cho biết **toàn bộ thứ tự mà mọi lời gọi `ResourceBundle.getBundle(...)` chắc chắn sẽ tìm kiếm**. Thực tế cần phân biệt:

**A. Danh sách ứng viên cho requested locale.** `getCandidateLocales(baseName, requestedLocale)` nêu các lựa chọn thuộc requested locale, bao gồm `Locale.ROOT` theo control tiêu chuẩn.

**B. Vòng fallback sang locale mặc định.** Khi không tìm thấy bundle thích hợp theo quy tắc tìm kiếm, `ResourceBundle.Control.getFallbackLocale(baseName, locale)` có thể trả **default locale của JVM** để thử một danh sách ứng viên khác. Nhánh này không có nghĩa `getCandidateLocales` của requested locale đã tự chứa mọi locale của máy.

**C. Parent bundle khi tra khóa.** Một bundle đã được chọn vẫn có thể truy vấn parent khi thiếu một khóa; vì thế bản dịch của khóa có thể đến từ resource khác với `bundle.getLocale()`.

**D. Bundle gốc `Locale.ROOT`.** Bundle gốc là một ứng viên chung trong chuỗi; nó không phải một ngôn ngữ cụ thể và không đồng nghĩa với default locale JVM. `Locale.ROOT.toLanguageTag()` trả `und`.

Ví dụ: chỉ in ứng viên của `fr-CA` không đủ để biết Java sau đó có thử locale mặc định `en-US` hay không, hoặc bundle gốc có tồn tại hay không. Phải biết cấu hình control và những tài nguyên được đóng gói.

Để bỏ **nhánh fallback sang default locale JVM** khi làm việc với bundle properties trên classpath:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "demo.Messages",
                Locale.forLanguageTag("fr-CA"),
                control);
```

Đây là trích đoạn; nó yêu cầu `java.util.Locale`, `java.util.ResourceBundle` và tài nguyên thực cho `demo.Messages`. Cách gọi này **không loại bỏ bundle gốc**, cũng không tắt việc tìm khóa ở parent.

## 8. Kiểm tra ứng viên nào thực sự được nạp

In candidate names chỉ trả lời câu hỏi **Java sẽ cân nhắc những tên nào**. Để biết tên nào tồn tại và đã được chọn, cần một ví dụ với file `.properties` thật.

Tạo cấu trúc sau trong thư mục làm việc:

```text
workspace/
├── LoadedBundleDemo.java
└── demo/
    ├── Messages.properties
    ├── Messages_zh.properties
    └── Messages_zh_Hant.properties
```

**Tệp `demo/Messages.properties`:**

```properties
message=ROOT
```

**Tệp `demo/Messages_zh.properties`:**

```properties
message=CHINESE
```

**Tệp `demo/Messages_zh_Hant.properties`:**

```properties
message=TRADITIONAL
```

**Tệp `LoadedBundleDemo.java`:**

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class LoadedBundleDemo {
    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static void show(String languageTag) {
        Locale requested = Locale.forLanguageTag(languageTag);
        ResourceBundle bundle =
                ResourceBundle.getBundle("demo.Messages", requested, CONTROL);

        System.out.println(requested.toLanguageTag()
                + " -> loaded=" + bundle.getLocale().toLanguageTag()
                + ", value=" + bundle.getString("message"));
    }

    public static void main(String[] args) {
        show("zh-TW");
        show("zh-CN");
        show("fr-CA");
    }
}
```

Từ thư mục `workspace`, chạy:

```bash
javac -encoding UTF-8 LoadedBundleDemo.java
java -cp . LoadedBundleDemo
```

Kết quả với đúng ba tệp properties và control trên:

```text
zh-TW -> loaded=zh-Hant, value=TRADITIONAL
zh-CN -> loaded=zh, value=CHINESE
fr-CA -> loaded=und, value=ROOT
```

**Giải thích:**

- Với `zh-TW`, trong các ứng viên không có file `Messages_zh_Hant_TW.properties`, nhưng có `Messages_zh_Hant.properties`, nên Java chọn bundle `zh-Hant`.
- Với `zh-CN`, không có các file `zh_Hans_CN`, `zh_Hans` hoặc `zh_CN`; `Messages_zh.properties` phù hợp trước khi tới root.
- Với `fr-CA`, không có bundle tiếng Pháp, nên dùng `Messages.properties` gốc. `Locale.ROOT.toLanguageTag()` là `und`.
- Vì dùng `getNoFallbackControl`, chương trình không thử một nhánh default locale JVM để làm thay đổi kết quả.

Nếu có thêm file `Messages_zh_TW.properties`, thứ tự ứng viên vẫn xét `zh_Hant` trước `zh_TW` cho requested locale `zh-TW`. Vì vậy file `Messages_zh_Hant.properties` ở ví dụ có thể tiếp tục được chọn. Để ép một thông điệp vùng đặc biệt cho `zh-TW`, cần đặt tài nguyên ở ứng viên ưu tiên phù hợp (ví dụ `Messages_zh_Hant_TW.properties`) hoặc thiết kế cách chọn tường minh.

## 9. Giới hạn khi dự án dùng JPMS/named modules

`ResourceBundle.Control` là công cụ thiết thực để khám phá thứ tự ứng viên trong cơ chế classpath. Tuy nhiên, khi resource bundle thuộc **named module**, hệ thống module có cơ chế nạp riêng, và một số overload của `ResourceBundle.getBundle` có tham số `Control` không được hỗ trợ, có thể ném `UnsupportedOperationException`.

Với dự án JPMS:

- Dùng overload `getBundle(baseName, locale)` hoặc API nhận `Module` theo thiết kế/module caller phù hợp.
- Kiểm tra tài nguyên đã được đóng gói vào module, chính sách truy cập của package và khai báo dịch vụ nếu sử dụng `ResourceBundleProvider`.
- Kiểm thử trên **module path thực tế**. Không dùng kết quả chạy classpath làm bằng chứng rằng mọi tên tài nguyên và mức truy cập JPMS đều giống hệt.
- Có thể dùng `Control.getCandidateLocales` độc lập để **hiểu quy tắc candidate naming**, nhưng không xem nó là phép đo đầy đủ cơ chế module provider thực tế.

Ví dụ chạy của bài cố ý sử dụng classpath để hành vi `Control` và các file properties được minh họa trực tiếp.

## 10. Cách chẩn đoán khi fallback không như dự kiến

Khi thấy Java chọn sai bản dịch, hãy kiểm tra có hệ thống:

1. **Ghi lại input:** giá trị `locale.toLanguageTag()`, language, script, region, variant và extension thực tế. Lưu ý `Locale.toString()` có thể khác language tag.
2. **In toàn bộ candidates:** gọi `getCandidateLocales` và `toBundleName` như phần 4 hoặc 6. Kiểm tra thứ tự, nhất là `zh`, `sr`, `nb`, `nn`, legacy variant và các extension.
3. **Đối chiếu file/class thực:** kiểm tra đường dẫn tương ứng trong classpath hoặc JAR, kể cả chữ hoa/thường. Không giả định file tồn tại chỉ vì tên xuất hiện trong danh sách.
4. **Kiểm tra loại bundle:** mặc định có thể ưu tiên bundle dạng class hơn `.properties` có cùng tên ứng viên; ví dụ bài chọn `FORMAT_PROPERTIES` để tránh nhập nhằng.
5. **Kiểm tra fallback tới default:** quan sát `Locale.getDefault()` và loại `Control` đang dùng. Khi cần kiểm thử ổn định, có thể dùng no-fallback control như phần 8.
6. **Xác định bundle được nạp:** `bundle.getLocale()` cho biết locale của bundle được chọn. Giá trị khóa vẫn có thể lấy từ parent nếu bundle con thiếu khóa.
7. **Kiểm tra runtime:** phiên bản JDK, classloader, tài nguyên trong build artifact, module path và cache `ResourceBundle`. Nếu dữ liệu thay đổi nhưng process còn sống, cache có thể khiến việc nạp không phản ánh file vừa sửa.
8. **Kiểm thử đúng trường hợp biên:** vùng có script suy luận, vùng có script tường minh, tiếng Na Uy, mã ngôn ngữ cũ, extension Unicode, locale chỉ có language, và locale không có bundle nào.

| Triệu chứng | Điều cần xem trước | Lý do |
| --- | --- | --- |
| `zh-TW` chọn bản dịch phồn thể chung thay vì file `zh_TW` | Danh sách `zh_Hant*` đứng trước `zh_TW` | Script inference có quy tắc đặc biệt |
| `nn-NO` lấy tài nguyên `no_NO_NY` | Ứng viên tiếng Na Uy lịch sử | Java có nhánh tương thích đặc biệt |
| `en-US-u-nu-thai` không tìm file có `u_nu_thai` | Candidate list bỏ Unicode extension | Extension không tự thành suffix bundle |
| `locale.toString()` nhìn khác tên file | So sánh với `toBundleName` | Hai chuỗi có hợp đồng biểu diễn khác nhau |
| `getCandidateLocales` liệt kê file nhưng `getBundle` báo thiếu | Tệp/class không có trên runtime classpath/module | Ứng viên chỉ là tên có thể được thử |
| Một khóa hiển thị ngôn ngữ khác `bundle.getLocale()` | Key fallback sang parent | Nguồn khóa và bundle được chọn có thể khác nhau |
| Chạy tốt trên classpath nhưng lỗi trên module path | Quy tắc JPMS và cách gọi `Control` | Module lookup và quyền truy cập khác nhau |

## 11. Ghi nhớ

- Chuỗi ứng viên của `ResourceBundle` là **một quy tắc có thứ tự**, không chỉ là cắt dần từng phần của thẻ BCP 47.
- Các trường hợp cần lưu ý nhất: **script** (`sr-Latn-RS`), **script suy luận cho tiếng Hoa** (`zh-TW` → `zh_Hant*`, `zh-CN` → `zh_Hans*`), **tiếng Na Uy** (`nb`, `nn`, `no_NO_NY`), **mã ngôn ngữ lịch sử**, **variant**, và **Unicode extension**.
- Dùng `ResourceBundle.Control.getCandidateLocales` rồi `toBundleName` để in tên bundle ứng viên; không tự dựng tên file từ `Locale.toString()`.
- Một tên ứng viên xuất hiện **không chứng minh tài nguyên tồn tại**. Dùng `getBundle`, `bundle.getLocale()`, kiểm tra key và artifact để xác nhận điều thực sự được nạp.
- **Chuỗi ứng viên**, **fallback sang default locale** và **tra khóa qua parent** là ba khái niệm khác nhau; nắm rõ từng tầng sẽ giúp chẩn đoán đúng lỗi bản địa hóa.
