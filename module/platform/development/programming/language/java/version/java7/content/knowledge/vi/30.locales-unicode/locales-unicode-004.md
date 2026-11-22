# Java Locale: đọc language, script, region và các phần mở rộng

## 1. Mục tiêu của bài học

Khi hệ thống nhận một ngôn ngữ ưa thích từ người dùng, header HTTP, cấu hình hoặc database, chỉ một mã như **zh**, **en** hay **vi** đôi khi chưa đủ. Ứng dụng còn cần xác định **hệ chữ viết (script)**, **vùng (region)** và các **phần mở rộng (extensions)** liên quan đến định dạng lịch, số hoặc thông tin riêng.

Java cung cấp **java.util.Locale** để biểu diễn những thành phần này. Ví dụ:

~~~text
zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo
│  │    │  │                 │         │
│  │    │  │                 │         └─ giá trị private-use: demo
│  │    │  └─────────────────┴─ phần mở rộng Unicode "u":
│  │    │                      ca=chinese, nu=hanidec
│  │    └─ region: TW
│  └─ script: Hant
└─ language: zh
~~~

Dạng tổng quát **BCP 47 language tag** thường được minh họa là **language[-script][-region][-variant...][-extension...][-private-use]**. Không phải tag nào cũng có đủ thành phần. Ví dụ **vi** chỉ có language; **sr-Latn** có language và script; **es-419** có language và region dạng mã số; **en-US-u-nu-latn** có thêm Unicode extension.

Các mục tiêu sau khi học:

- Phân biệt **language**, **script**, **region**, **variant** và **extension**.
- Biết đọc **getLanguage()**, **getScript()**, **getCountry()**, **getVariant()** và **toLanguageTag()**.
- Biết đọc **getExtensionKeys()**, **getExtension(char)** và nhóm Unicode locale **getUnicodeLocaleKeys/Type/Attributes**.
- Tạo/parse Locale đúng bằng **Locale.forLanguageTag(...)** hoặc **Locale.Builder**.
- Xử lý thành phần thiếu, tag không hợp lệ, khác biệt giữa mã chuẩn và tên hiển thị, các hệ thống định dạng thực tế.
- Không nhầm Locale với **bộ mã ký tự**, chuyển tự, Unicode normalization hay khả năng nhận diện ngôn ngữ từ văn bản.

**Lưu ý phạm vi:** Các API được trình bày vẫn là cơ chế hiện hành của Java. Ví dụ chương trình hoàn chỉnh dùng **JDK 17+**, không sử dụng constructor hay mô hình i18n cũ như một lựa chọn mới.

## 2. BCP 47: mỗi phần của tag có nghĩa riêng

**BCP 47** là chuẩn thông dụng cho language tag trong HTTP, nội dung đa ngôn ngữ và Java Locale. Dấu phân tách là **dấu gạch ngang (-)**, không phải dấu gạch dưới.

| Thành phần | Dạng thông thường | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| **language** | Mã ngôn ngữ, thường theo ISO 639 | **vi**, **en**, **sr**, **zh** | Ngôn ngữ |
| **script** | Mã ISO 15924 gồm 4 chữ cái | **Latn**, **Cyrl**, **Hant**, **Hans** | Hệ chữ được dùng; không phải charset |
| **region** | ISO 3166 alpha-2 hoặc UN M.49 3 chữ số | **VN**, **US**, **TW**, **419** | Vùng lãnh thổ/địa lý |
| **variant** | Subtag biến thể hợp lệ theo BCP 47 | **rozaj**, **1996** | Biến thể được nhận diện, khi có |
| **extension** | Singleton theo sau bởi subtags | **u-ca-buddhist**, **t-...** | Thông tin mở rộng |
| **private-use** | Bắt đầu bởi **x** | **x-myapp** | Dữ liệu riêng, không bảo đảm ý nghĩa chung |

Ví dụ thực tế:

- **vi-VN**: tiếng Việt, vùng Việt Nam, không chỉ rõ script.
- **sr-Cyrl-RS**: tiếng Serbia, chữ Cyrillic, vùng Serbia.
- **sr-Latn-RS**: tiếng Serbia, chữ Latin, vùng Serbia. Khác script dù cùng language và region.
- **zh-Hant-TW**: tiếng Trung, chữ Hán phồn thể, vùng Đài Loan.
- **zh-Hans-CN**: tiếng Trung, chữ Hán giản thể, vùng Trung Quốc.
- **es-419**: tiếng Tây Ban Nha, region 419 theo UN M.49 (Mỹ Latinh và Caribe), **không phải** mã quốc gia 2 ký tự.
- **en-US-u-nu-latn**: tiếng Anh/Mỹ và Unicode extension yêu cầu hệ chữ số **latn**.

Cách viết thông dụng khi xuất tag: **language** chữ thường, **script** chữ cái đầu hoa, **region** chữ hoa, các extension chữ thường. Khi dùng **Locale.forLanguageTag()** và **toLanguageTag()**, Java có thể chuẩn hóa viết hoa/thường, thứ tự hoặc alias theo các quy tắc của Locale. Đừng dùng chuỗi đầu vào nguyên dạng để suy luận danh tính sau parse; hãy đọc lại các thành phần và **toLanguageTag()**.

**Chú ý:** **script** trong language tag không tương đương với encoding. **Hant** là kiểu chữ Hán phồn thể, không phải **UTF-8** hay **UTF-16**. Tag **zh-Hant-TW** cũng **không chứng minh** một đoạn văn bản cụ thể chỉ chứa ký tự thuộc một script.

## 3. Đọc bốn thành phần cơ bản của Locale

Các getter hiện hành trả về chuỗi mã, không phải tên hiển thị đã dịch:

| API | Kết quả | Khi thành phần không được khai báo |
| --- | --- | --- |
| **getLanguage()** | Mã ngôn ngữ, thường chữ thường: **zh** | **""** |
| **getScript()** | Mã ISO 15924: **Hant** | **""** |
| **getCountry()** | Mã **region** (tên API lịch sử): **TW**, **419** | **""** |
| **getVariant()** | Biến thể, ví dụ **rozaj** | **""** |
| **toLanguageTag()** | Chuỗi BCP 47, như **zh-Hant-TW** | Với locale gốc không có language, tag có thể dùng **und** |
| **toString()** | Chuỗi debug Java Locale, thường có dấu **_** và **#** | Không dùng làm định dạng trao đổi BCP 47 |

Điểm quan trọng nhất khi đọc **region**: Java gọi API là **getCountry()**, nhưng giá trị theo đặc tả là **country/region**, có thể là mã số **UN M.49** chứ không nhất thiết là một quốc gia. Với tag **es-419**, giá trị **getCountry()** là **"419"**.

Ví dụ ngắn (đoạn minh họa bên trong một phương thức):

~~~java
Locale locale = Locale.forLanguageTag("sr-Latn-RS");

String language = locale.getLanguage(); // "sr"
String script = locale.getScript();     // "Latn"
String region = locale.getCountry();    // "RS"
String variant = locale.getVariant();   // ""
String tag = locale.toLanguageTag();    // "sr-Latn-RS"
~~~

Cần import **java.util.Locale**. Thành phần trống **không phải null**, do đó dùng **isEmpty()** khi phân nhánh:

~~~java
if (locale.getScript().isEmpty()) {
    // Người dùng không khai báo script: không tự kết luận là Latn.
}
~~~

**Không suy ra thiếu region là vùng hiện tại của server**. Ví dụ Locale chỉ có **en** không chứng minh người dùng ở Mỹ hay Anh. Khi ứng dụng cần region mặc định, quy định chính sách từ yêu cầu nghiệp vụ; không tự lấy **Locale.getDefault()** để “lấp chỗ trống” một cách vô thức.

### Mã và tên hiển thị

Các hàm **getLanguage/getScript/getCountry** phục vụ logic phân tích. Các hàm **getDisplayLanguage(Locale)**, **getDisplayScript(Locale)** và **getDisplayCountry(Locale)** phục vụ UI:

~~~java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");
String regionCode = locale.getCountry();              // "TW"
String visibleName = locale.getDisplayCountry(
        Locale.forLanguageTag("en"));
~~~

Dòng **visibleName** trả một tên có thể hiển thị bằng tiếng Anh theo dữ liệu locale của JDK. **Không hard-code một stdout cố định** cho tên hiển thị vì CLDR/JDK và cách dùng locale có thể cập nhật. Đối với truyền dữ liệu giữa hệ thống, dùng **toLanguageTag()** thay vì các giá trị display hoặc **Locale.toString()**.

## 4. Extension là gì? Chữ **u**, **t**, **x** khác nhau thế nào?

**Extension** là thông tin phụ thêm ngoài language, script, region và variant. Java cho phép lấy các extension đã được parse qua **getExtensionKeys()** và **getExtension(char)**.

Ví dụ tag:

~~~text
zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo
~~~

gồm hai extension singleton:

- **u**: **Unicode locale extension**, chứa tùy chọn như **ca** (calendar) và **nu** (numbering system).
- **x**: **private-use**. Giá trị **demo** do ứng dụng tự định nghĩa; không thể xem là chuẩn quốc tế.
- **t**: extension cho **transformed content** theo hệ sinh thái BCP 47. Nếu có, đọc nó qua API extension tổng quát; không nhầm nó với Unicode **u**.

API:

~~~java
Locale locale = Locale.forLanguageTag(
        "zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo");

Set<Character> keys = locale.getExtensionKeys();
// Có hai key 'u' và 'x' (thứ tự Set không được bảo đảm).

String unicodePart = locale.getExtension('u');
// "ca-chinese-nu-hanidec"

String privatePart = locale.getExtension('x');
// "demo"

String missing = locale.getExtension('a');
// null nếu không có extension 'a'.

boolean withExtensions = locale.hasExtensions(); // true
Locale base = locale.stripExtensions();
// base.toLanguageTag(): "zh-Hant-TW"
~~~

Đây là đoạn minh họa trong phương thức, cần import **java.util.Locale** và **java.util.Set**. **getExtension(char)** trả **giá trị** sau singleton, không chứa ký tự **u-** hoặc **x-** ở đầu. Hàm trả **null** khi không có key được yêu cầu; tham số singleton phải là một ký tự alphanumeric hợp lệ. **getExtensionKeys()** trả set không cho sửa; không phụ thuộc thứ tự khi in hoặc xử lý.

**stripExtensions()** trả Locale không còn các extension, giữ các thành phần nền language/script/region/variant. Nó không chỉnh sửa Locale gốc vì Locale là đối tượng bất biến (*immutable*).

**Điều không nên giả định:** Phần mở rộng **x-myapp** không được mọi thư viện tự hiểu. Một extension được giữ trong Locale không bảo đảm tất cả API định dạng có cách xử lý cụ thể cho extension đó.

## 5. Unicode locale extension **u**: attributes, keywords và types

Phần mở rộng **u** được xác định trong hệ sinh thái **Unicode Locale Identifier/UTS #35**. Nó có hai nhóm thông tin:

1. **Attributes**: các nhãn Unicode không có cặp key-type riêng, ví dụ **emoji**.
2. **Keywords**: cặp **key → type**, ví dụ **ca → chinese**, **nu → hanidec**.

Từ tag **zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo**:

| Thành phần u | API đọc | Kết quả |
| --- | --- | --- |
| Extension u nguyên phần | **getExtension('u')** | **"ca-chinese-nu-hanidec"** |
| Danh sách keyword keys | **getUnicodeLocaleKeys()** | Set gồm **ca**, **nu** |
| Calendar type | **getUnicodeLocaleType("ca")** | **"chinese"** |
| Numbering type | **getUnicodeLocaleType("nu")** | **"hanidec"** |
| Một key không tồn tại | **getUnicodeLocaleType("hc")** | **null** |
| Attributes | **getUnicodeLocaleAttributes()** | Set rỗng nếu không có attribute |

Ý nghĩa thường gặp:

- **ca**: định danh hệ lịch, như **gregory**, **buddhist**, **japanese**, **chinese**.
- **nu**: định danh hệ chữ số, như **latn**, **thai**, **arab**, **hanidec**.
- **hc**: quy ước chu kỳ giờ khi được khai báo.
- **co**: tùy chọn collation/sắp xếp, nếu một bộ so sánh tương ứng hỗ trợ.

Các key và type này là **chuỗi định danh**, không phải đối tượng Calendar, NumberFormat hoặc Collator. Bản thân việc **getUnicodeLocaleType("ca")** trả về **"chinese"** chỉ chứng minh tag đã mang tùy chọn đó, **không** bảo đảm mọi formatter trong runtime hỗ trợ đầy đủ kiểu lịch này hoặc tự động áp dụng như kỳ vọng. Khi sử dụng formatter, phải kiểm tra hỗ trợ thực tế của service/provider và yêu cầu nghiệp vụ.

### Phân biệt ba trạng thái của keyword type

**getUnicodeLocaleType(key)** có thể trả:

- **null**: không có key.
- **""** (chuỗi rỗng): key có trong extension **u** nhưng không có type cụ thể.
- Chuỗi không rỗng như **"latn"** hoặc **"buddhist"**: key có type.

Vì thế, đoạn này **chưa đủ**:

~~~java
String numbers = locale.getUnicodeLocaleType("nu");
if (numbers == null) {
    // Không có keyword nu.
} else if (numbers.isEmpty()) {
    // Có nu nhưng không kèm type cụ thể.
} else {
    // Có nu và type cụ thể, ví dụ "latn".
}
~~~

Đây là đoạn minh họa với biến **locale** có sẵn. Key phải là **hai ký tự chữ/số hợp lệ**; chuỗi key không đúng cú pháp có thể gây **IllegalArgumentException**, còn **null** gây **NullPointerException**. Không truyền tên key dài như **"calendar"** cho API này: chuẩn sử dụng **"ca"**.

**getUnicodeLocaleAttributes()** chỉ đọc attributes Unicode **u**; nó không trả **private-use x**. **getUnicodeLocaleKeys()** không liệt kê các singleton của mọi extension, chỉ liệt kê **Unicode keyword keys**. Muốn liệt kê singleton **u/x/t**, dùng **getExtensionKeys()**.

### Thứ tự trong Set

Không dựa vào thứ tự lặp của **getUnicodeLocaleKeys()**, **getUnicodeLocaleAttributes()** hoặc **getExtensionKeys()** khi viết test hay in kết quả. Dùng **TreeSet** trong ví dụ chương trình để xuất kết quả ổn định:

~~~java
System.out.println(new TreeSet<>(locale.getUnicodeLocaleKeys()));
// [ca, nu]
~~~

Đây là đoạn minh họa, cần import **java.util.TreeSet**. Không thay thứ tự tag bằng thứ tự giả định của cấu trúc Set.

## 6. Parse tag bằng forLanguageTag hoặc kiểm tra nghiêm bằng Builder

### Locale.forLanguageTag: phù hợp khi đọc tag BCP 47

~~~java
Locale locale = Locale.forLanguageTag("en-US-u-nu-latn");
~~~

**Locale.forLanguageTag(String)** phân tích tag và tạo Locale. Phương thức này **không phải validator nghiêm ngặt**: khi gặp subtag sai cấu trúc, nó có thể loại bỏ phần sai cùng phần theo sau, thay vì ném một exception cho toàn bộ input. Nó cũng có thể chuẩn hóa alias và viết hoa/thường. Nếu ứng dụng cần từ chối input không hợp lệ, đừng kết luận “forLanguageTag trả Locale là input đã hợp lệ hoàn toàn”.

### Locale.Builder: phù hợp khi cần kiểm tra cú pháp BCP 47

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
~~~

**Builder** kiểm tra cú pháp thành phần phù hợp với BCP 47, chuẩn hóa kiểu chữ và có thể ném **IllformedLocaleException** nếu chuỗi không đúng dạng. Với input là tag hoàn chỉnh, dùng:

~~~java
try {
    Locale checked = new Locale.Builder()
            .setLanguageTag("en_US") // Sai BCP 47: dùng "_".
            .build();
} catch (java.util.IllformedLocaleException invalid) {
    System.out.println("Invalid BCP 47 tag");
}
~~~

Đây là các đoạn minh họa, được sử dụng trong thân phương thức. Tag **en_US** không phải BCP 47 chuẩn; dạng thích hợp là **en-US**. **Builder.setLanguageTag** nghiêm ngặt hơn **Locale.forLanguageTag** đối với tag có phần sai.

Có thể dùng **setExtension(char, String)** để gán một extension tổng quát và **setUnicodeLocaleKeyword(String, String)** hoặc **addUnicodeLocaleAttribute(String)** để đặt nhóm Unicode **u**. Các phương thức này kiểm tra *cú pháp*, không có nghĩa mọi code key/type đều được tất cả formatter chấp nhận về mặt *ngữ nghĩa*.

**Quy tắc thực tế:**

1. Đầu vào của ứng dụng là language tag BCP 47 → parse với **forLanguageTag**, đọc các thành phần và cân nhắc chính sách kiểm tra.
2. API công khai cần từ chối tag sai dạng → dùng **new Locale.Builder().setLanguageTag(value).build()** và bắt **IllformedLocaleException**.
3. Có các trường riêng language/script/region → dùng **Locale.Builder** để kết hợp, không ghép chuỗi tùy tiện rồi hy vọng tag hợp lệ.
4. Lưu/trao đổi Locale qua JSON, DB, HTTP → ưu tiên **toLanguageTag()**, không sử dụng **Locale.toString()** với dấu gạch dưới.
5. Nếu các hệ thống khác nhau cùng xử lý alias và dữ liệu locale, kiểm thử các tag quan trọng trên những JDK thực tế; cú pháp hợp lệ không bảo đảm mọi application data đều có bản dịch phù hợp.

**Tương thích phiên bản:** Trong một số phiên bản Java mới có factory **Locale.of(...)**, nhưng code học tập JDK 17+ ở đây dùng **forLanguageTag** và **Builder**, vốn vẫn phù hợp và hỗ trợ script/extensions. **Locale.of(...)** không phải API JDK 17, vì vậy không sử dụng nó trong ví dụ chạy JDK 17.

## 7. Chương trình Java 17+ chạy được và stdout đã kiểm chứng

Chương trình này đọc tag có language, script, region, **Unicode u** và **private x**; đồng thời tạo Locale bằng Builder, đọc Unicode attribute và xác minh Builder từ chối tag sai cú pháp.

Lưu thành **LocalePartsDemo.java**:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.TreeSet;

public class LocalePartsDemo {
    private static void describe(Locale locale) {
        System.out.println("tag=" + locale.toLanguageTag());
        System.out.println("language=" + locale.getLanguage());
        System.out.println("script=" + locale.getScript());
        System.out.println("region=" + locale.getCountry());
        System.out.println("variant=" + locale.getVariant());
        System.out.println("extensionKeys="
                + new TreeSet<>(locale.getExtensionKeys()));
        System.out.println("unicodeKeys="
                + new TreeSet<>(locale.getUnicodeLocaleKeys()));
        System.out.println("calendar="
                + locale.getUnicodeLocaleType("ca"));
        System.out.println("numbers="
                + locale.getUnicodeLocaleType("nu"));
        System.out.println("unicodeExtension="
                + locale.getExtension('u'));
        System.out.println("privateUse="
                + locale.getExtension('x'));
        System.out.println("missingKey="
                + locale.getUnicodeLocaleType("hc"));
        System.out.println("baseTag="
                + locale.stripExtensions().toLanguageTag());
    }

    public static void main(String[] args) {
        Locale parsed = Locale.forLanguageTag(
                "zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo");
        describe(parsed);

        Locale built = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .addUnicodeLocaleAttribute("emoji")
                .setUnicodeLocaleKeyword("nu", "latn")
                .build();
        System.out.println("built=" + built.toLanguageTag());
        System.out.println("attributes="
                + new TreeSet<>(built.getUnicodeLocaleAttributes()));

        try {
            new Locale.Builder().setLanguageTag("en_US");
            System.out.println("invalidTag=accepted");
        } catch (IllformedLocaleException expected) {
            System.out.println("invalidTag=rejected");
        }
    }
}
~~~

Chạy trên **JDK 17+** bằng terminal:

~~~bash
javac LocalePartsDemo.java
java LocalePartsDemo
~~~

**Stdout chính xác của ví dụ:**

~~~text
tag=zh-Hant-TW-u-ca-chinese-nu-hanidec-x-demo
language=zh
script=Hant
region=TW
variant=
extensionKeys=[u, x]
unicodeKeys=[ca, nu]
calendar=chinese
numbers=hanidec
unicodeExtension=ca-chinese-nu-hanidec
privateUse=demo
missingKey=null
baseTag=zh-Hant-TW
built=sr-Latn-RS-u-emoji-nu-latn
attributes=[emoji]
invalidTag=rejected
~~~

**Mã đã được biên dịch bằng javac và chạy bằng java trên JDK 24**; kết quả kiểm tra khớp toàn bộ stdout trên. Chỉ dùng API có sẵn trong JDK 17 trở lên; không cần dependency bên ngoài.

### Đọc từng nhóm kết quả

- **language=zh, script=Hant, region=TW**: từ một BCP 47 tag, ba getter trả đúng ba mã riêng. **variant=** rỗng vì tag không có biến thể.
- **extensionKeys=[u, x]**: Java xác định hai singleton. Kết quả in có thứ tự vì chương trình chủ động dùng **TreeSet**.
- **unicodeKeys=[ca, nu]**: nhóm Unicode **u** có hai keyword keys; **calendar=chinese** và **numbers=hanidec** là các giá trị đã khai báo.
- **unicodeExtension=ca-chinese-nu-hanidec**: API trả phần giá trị của singleton **u**, không có ký tự **u-** đầu.
- **privateUse=demo**: phần mở rộng **x** được đọc riêng, không nằm trong Unicode keyword map.
- **missingKey=null**: không có keyword Unicode **hc**, không phải chuỗi rỗng.
- **baseTag=zh-Hant-TW**: **stripExtensions()** loại bỏ cả **u** và **x**, không làm mất language/script/region.
- **built=sr-Latn-RS-u-emoji-nu-latn**: Builder cho phép tạo Locale từ trường riêng, Unicode attribute **emoji** và keyword **nu=latn**.
- **invalidTag=rejected**: Builder bắt lỗi **en_US**, giúp xác minh input có cú pháp BCP 47 đúng thay vì nhận giá trị được “sửa” một cách im lặng.

Nếu đổi input sang **vi-VN**, **getScript()** sẽ rỗng; điều đó không có nghĩa dữ liệu văn bản không sử dụng script, chỉ là **tag chưa khai báo script**. Không gán script mặc định bằng suy đoán.

## 8. Cách áp dụng vào hệ thống đa ngôn ngữ

### Bài toán A: đọc preference thành các trường lưu cấu hình

Từ **sr-Latn-RS-u-nu-latn**, có thể đưa các mã vào một DTO:

~~~java
// Đoạn minh họa trong phương thức; Locale đã được import.
Locale locale = Locale.forLanguageTag("sr-Latn-RS-u-nu-latn");

String language = locale.getLanguage();       // "sr"
String script = locale.getScript();           // "Latn"
String region = locale.getCountry();          // "RS"
String numbers = locale.getUnicodeLocaleType("nu"); // "latn"
~~~

Lưu **toLanguageTag()** cùng bản Locale đã chuẩn hóa thường đơn giản hơn việc lưu bốn chuỗi rời rạc mà bỏ sót variant hoặc extensions. Nếu schema bắt buộc tách cột, hãy đặt tên **region** thay vì mặc định country là quốc gia; kiểm tra chuỗi rỗng và null đúng API.

### Bài toán B: chọn ngôn ngữ nội dung khác với định dạng số

Một người dùng có thể muốn **nội dung bằng tiếng Anh** nhưng định dạng số theo **nu-thai**. Language tag có thể chứa cả hai, nhưng ứng dụng cần phân biệt:

- **Language/script/region** giúp chọn bản dịch hoặc locale phù hợp với nội dung.
- **Unicode extension key** là một *preference* bổ sung, không nhất thiết mọi thư viện định dạng đều hỗ trợ.
- Một template được dịch sang ngôn ngữ cụ thể không nhất thiết tự thay đổi calendar hoặc numbering system.

Do đó, code cần hỏi **getUnicodeLocaleType("nu")** và kiểm thử formatter thực tế; không được “dịch” **nu=thai** thành “người dùng viết tiếng Thái”. Đó là **tùy chọn số**, không phải language code.

### Bài toán C: lấy tên hiển thị cho danh sách lựa chọn

Nếu cần hiện “Vietnamese”, “Serbian (Latin)” hoặc “Chinese (Traditional)” trong một UI tiếng Anh, hãy dùng các API **getDisplayLanguage/getDisplayScript/getDisplayCountry** với một Locale hiển thị explicit. Không render mã **Hant/TW** là tên thân thiện mà không chuyển đổi.

Tuy nhiên, UI text có thể đổi theo dữ liệu địa phương hóa của runtime, nên test ổn định nên so **code/tag**, không nhất thiết assert từng chữ của tên hiển thị qua mọi JDK/CLDR.

### Bài toán D: Accept-Language từ HTTP

Header **Accept-Language** thường có **danh sách** và trọng số chất lượng, chẳng hạn:

~~~text
vi-VN, en-US;q=0.8, en;q=0.6
~~~

**Đừng truyền nguyên header này vào Locale.forLanguageTag()**: đây không phải một language tag duy nhất. Java có **Locale.LanguageRange.parse(...)**, **Locale.filter(...)**, **Locale.lookup(...)** để diễn giải danh sách ưu tiên và chọn từ các locale ứng dụng hỗ trợ:

~~~java
// Đoạn minh họa; cần java.util.Locale và java.util.List.
var ranges = Locale.LanguageRange.parse(
        "vi-VN, en-US;q=0.8, en;q=0.6");
var supported = java.util.List.of(
        Locale.forLanguageTag("en-US"),
        Locale.forLanguageTag("vi-VN"));
Locale chosen = Locale.lookup(ranges, supported);
~~~

Với danh sách ví dụ, ứng dụng có thể chọn Locale phù hợp theo RFC 4647. Phải quyết định fallback nếu **chosen** là null; chỉ liệt kê ngôn ngữ thực sự hỗ trợ, không coi **getAvailableLocales()** là danh sách bản dịch đang tồn tại trong sản phẩm.

## 9. Locale không phải Unicode normalization hoặc bộ mã ký tự

Tên nhóm kiến thức là **Locale và Unicode**, nên cần phân biệt rõ các phạm vi:

| Khái niệm | Giải quyết câu hỏi gì? | API ví dụ |
| --- | --- | --- |
| **Locale** | Ngôn ngữ/script/region/biến thể/extension được yêu cầu | Locale.getLanguage/getScript/getCountry |
| **Charset/encoding** | Byte được mã hóa/giải mã ra ký tự thế nào? | StandardCharsets.UTF_8 |
| **Unicode normalization** | Hai chuỗi ký tự tương đương nên chuẩn hóa về NFC/NFD? | java.text.Normalizer |
| **Unicode case mapping** | Chuyển chữ hoa/thường theo quy tắc nào? | String.toLowerCase(Locale) |
| **Collation/sorting** | So chuỗi theo thứ tự thích hợp cho ngôn ngữ nào? | Collator.getInstance(Locale) |
| **Number/date formatting** | Định dạng theo locale và provider cụ thể? | NumberFormat, DateTimeFormatter |

Ví dụ, hai chuỗi có thể trông như cùng một chữ **é**, nhưng một chuỗi được mã hóa bằng một code point tiền hợp, chuỗi còn lại gồm **e + combining acute accent**. **Locale.forLanguageTag("fr-FR")** không tự normalize hai chuỗi; nếu nghiệp vụ cần chuẩn hóa, dùng **Normalizer.normalize(text, Normalizer.Form.NFC)** với chính sách lưu trữ/so sánh phù hợp.

Ngược lại, một **script code** như **Cyrl** không thể thay thế UTF-8 hay UTF-16 khi đọc byte từ file. Việc đọc Locale không chứng minh encoding đầu vào đúng và không phân tích chính xác mọi hệ chữ có trong văn bản.

Khi xử lý keyword kỹ thuật không phụ thuộc ngôn ngữ, ví dụ identifier dạng ASCII hoặc mã protocol, cân nhắc **Locale.ROOT** với case conversion để tránh việc kết quả thay đổi theo default locale của máy:

~~~java
String normalizedKey = input.toLowerCase(Locale.ROOT);
~~~

Đây là đoạn minh họa, cần biến **input**. Tuy vậy, lowercasing không tương đương một thuật toán Unicode case folding đầy đủ; với định danh có yêu cầu bảo mật, cần tiêu chuẩn chuẩn hóa/so sánh của chính protocol. Với chữ hiển thị cho người dùng, lại cần chính sách locale-sensitive phù hợp.

## 10. Thành phần hợp lệ không đồng nghĩa dữ liệu bản dịch có sẵn

Có vài cấp độ kiểm chứng tách biệt:

1. **Cú pháp tag** hợp lệ hay không — **Locale.Builder** có thể kiểm tra.
2. **Mã language/script/region** có ý nghĩa và nằm trong chính sách ứng dụng hay không — cần kiểm chứng danh mục cho phép và yêu cầu hệ thống.
3. **Resource bundle** có bản dịch thích hợp không — phải xem tài nguyên thực sự đã đóng gói, không chỉ việc Locale tạo được.
4. **Formatter** có hiểu extension như **ca/nu** hay không — tùy API/provider và hệ lịch hoặc hệ chữ số hỗ trợ.
5. **Người dùng có chủ đích chọn** preference đó không — không suy từ IP, tên vùng hoặc script một cách tự động.

Một Locale chứa **u-ca-chinese** hợp cú pháp nhưng **không phải lời hứa** DateTimeFormatter hoặc NumberFormat trên mọi JDK/locale sẽ xử lý đúng toàn bộ kiểu lịch và số như mong muốn. Phải kiểm thử kết quả của **formatter được ứng dụng sử dụng**. Một type Unicode đúng cấu trúc vẫn có thể không được hỗ trợ bởi một service cụ thể.

**Locale.getDefault()** và các category **DISPLAY/FORMAT** là cấu hình của JVM, có thể khác giữa máy developer, CI và server. Khi tạo nội dung hoặc dữ liệu có yêu cầu ổn định, **truyền Locale rõ ràng** cho formatter, collator hoặc display APIs thay vì lệ thuộc default.

## 11. Các lỗi thường gặp và cách khắc phục

| Hiểu sai/cách viết sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng **getCountry()** và nghĩ luôn là một quốc gia ISO alpha-2 | Có thể là region số như **419** | Hiểu là country/region, giữ giá trị đúng chuẩn |
| Dùng **getScript()** để xác định UTF-8/UTF-16 | Script và encoding là hai khái niệm khác nhau | Đọc charset riêng; dùng StandardCharsets khi giải mã |
| Gộp **zh-Hant** với **zh-Hans** chỉ vì cùng language | Khác script có thể ảnh hưởng nội dung được chọn | Giữ script trong key lựa chọn khi có |
| Dùng **Locale.toString()** lưu vào HTTP/JSON | Java debug string có dấu **_** và **#**, không phải BCP 47 | Dùng **toLanguageTag()** |
| Parse **en_US** như BCP 47 chuẩn | Phân tách sai | Dùng **en-US** và Builder để bắt lỗi |
| Dùng **forLanguageTag** làm validator tuyệt đối | Có thể bỏ phần malformed/trailing | Dùng Builder nghiêm và kiểm tra policy |
| Gọi **getUnicodeLocaleType("calendar")** | Key phải có hai chữ/số; calendar dùng **ca** | Gọi **getUnicodeLocaleType("ca")** |
| Coi **null** và **""** là như nhau | Key vắng mặt khác key có type rỗng | Kiểm tra đúng hai trạng thái |
| Dùng **getExtension('u')** rồi nghĩ bao gồm cả **x** | Mỗi singleton đọc một extension | Đọc **getExtensionKeys** hoặc **getExtension('x')** |
| Coi **getUnicodeLocaleKeys()** là danh sách extension singleton | Nó chỉ cho các key bên trong **u** | Dùng **getExtensionKeys()** cho u/x/t |
| Coi **x-private** có ý nghĩa thống nhất với mọi thư viện | Private-use do từng hệ thống định nghĩa | Cần hợp đồng ứng dụng rõ ràng |
| Dựa vào thứ tự Set trả về từ Locale | API không cam kết thứ tự mong muốn | Dùng TreeSet/sắp xếp khi cần xuất ổn định |
| Tag **u-nu-thai** chứng minh người dùng nói tiếng Thái | Đây là keyword hệ chữ số, không phải language | Đọc getLanguage để biết language |
| Coi tag có extension thì formatter chắc chắn hỗ trợ | Khả năng tùy formatter/provider | Kiểm thử từng loại định dạng |
| Dùng Locale mặc định của server để gán vùng cho tag thiếu region | Cấu hình server không đại diện người dùng | Quy định fallback rõ ràng |
| Truyền nguyên HTTP Accept-Language cho forLanguageTag | Header chứa nhiều tag và q-values | Dùng Locale.LanguageRange.parse và lookup/filter |
| Tự định nghĩa chuỗi language+script+region thiếu validate | Có thể tạo tag sai | Dùng Locale.Builder |
| Test cố định tên quốc gia đã dịch qua mọi bản JDK | Dữ liệu CLDR có thể thay đổi | Test mã/tag, kiểm soát provider nếu cần |

## 12. Checklist áp dụng cho hệ thống thực tế

**Khi nhận một tag:**

1. Xác nhận đầu vào là **một BCP 47 tag** hay **danh sách Accept-Language**; chọn parser tương ứng.
2. Nếu input do bên ngoài cung cấp và yêu cầu nghiêm ngặt, dùng **Locale.Builder.setLanguageTag** và xử lý **IllformedLocaleException**.
3. Đọc **getLanguage/getScript/getCountry/getVariant**; thành phần vắng mặt trả **""**, không tự suy luận từ môi trường server.
4. Kiểm tra **hasExtensions()**, sau đó dùng **getExtensionKeys()** nếu cần; đọc **u** bằng các getter Unicode, **x** bằng getExtension('x').
5. Phân biệt **null**, chuỗi rỗng và type thực tế của Unicode keyword.
6. Lưu tag bằng **toLanguageTag()**, nếu cần tách dữ liệu thì giữ script và extensions để không mất thông tin.

**Khi áp dụng lựa chọn:**

1. Chọn tập các locale có nội dung thực sự hỗ trợ, với fallback đã định nghĩa.
2. Chuyển đổi mã sang tên hiển thị bằng API display với Locale explicit; không giả định display text cố định trên mọi JDK.
3. Áp dụng keyword số/lịch/collation **chỉ khi service thực tế hỗ trợ** và có test.
4. Phân biệt lựa chọn UI, format và dữ liệu ứng dụng; không coi một Locale là giải pháp tự động cho encoding/normalization.
5. Kiểm tra cùng tag quan trọng trên JDK/CLDR/formatter được dùng ở production.

### Câu hỏi tự kiểm tra

1. **zh-Hant-TW** cho kết quả language, script và region nào? → **zh**, **Hant**, **TW**.
2. **getCountry()** có thể trả **419** không? → Có, vì nó biểu diễn country/region, gồm UN M.49.
3. **Locale.forLanguageTag("vi")** có getScript() bằng gì? → **""**, không phải mặc định **Latn**.
4. **getExtension('u')** trả gì trên tag có **u-nu-thai**? → **"nu-thai"**.
5. **getUnicodeLocaleType("nu")** trả gì khi tag không có key **nu**? → **null**.
6. **Key u-nu** có mặt nhưng không có type thì trả null hay chuỗi rỗng? → **""**.
7. **getUnicodeLocaleKeys()** có chứa **x** không? → Không. **x** là singleton extension được đọc qua getExtensionKeys/getExtension.
8. **stripExtensions()** xóa cả language và region không? → Không; nó bỏ extensions.
9. **Locale.toString()** hay **toLanguageTag()** phù hợp khi trao đổi BCP 47? → **toLanguageTag()**.
10. **Locale.Builder** có đảm bảo hệ lịch được formatter hỗ trợ không? → Không; nó kiểm tra cú pháp các phần của Locale, không bảo đảm mọi locale data/provider.
11. **en_US** là language tag BCP 47 chuẩn không? → Không; dùng **en-US**.
12. **Header Accept-Language chứa q-values** nên đọc bằng gì? → **Locale.LanguageRange.parse(...)** và cơ chế filter/lookup.
13. **Locale.getScript()** có thể thay Unicode Normalizer không? → Không, đó là hai chức năng khác nhau.

**Kết luận:** **Locale** lưu nhiều chiều của lựa chọn ngôn ngữ. Dùng **getLanguage()** cho language, **getScript()** cho script, **getCountry()** cho region; dùng **getExtensionKeys/getExtension** và **getUnicodeLocaleAttributes/Keys/Type** cho phần mở rộng. **Locale.Builder** phù hợp kiểm tra cú pháp nghiêm ngặt, **toLanguageTag()** phù hợp trao đổi BCP 47, và việc một extension tồn tại **không đồng nghĩa** mọi formatter hiểu hoặc áp dụng nó.

**Tài liệu chuẩn đang được duy trì:**

- [Oracle Java SE 27 — Locale](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html): BCP 47, language/script/region, extensions, Unicode attributes và keywords.
- [Oracle Java SE 27 — Locale.Builder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.Builder.html): kiểm tra cú pháp, setLanguageTag, setScript, setRegion, setUnicodeLocaleKeyword.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): đối chiếu API dành cho ví dụ JDK 17+.
- [IETF BCP 47 — RFC 5646](https://www.rfc-editor.org/rfc/rfc5646): cấu trúc language tags.
- [Unicode CLDR / UTS #35](https://unicode.org/reports/tr35/): Unicode locale extension và định danh keyword/type.
