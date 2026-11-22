# Java 7 — Locale và Unicode: Chuỗi tên phù hợp người dùng bằng các phương thức getDisplay

## 1. Bài toán: mã ổn định, nhãn dễ hiểu

Một ứng dụng đa ngôn ngữ thường phải hiển thị tên ngôn ngữ, quốc gia/vùng, hệ chữ viết hoặc biến thể cho người dùng. Ví dụ dữ liệu cấu hình lưu mã `de-DE`, nhưng giao diện có thể cần hiển thị **German (Germany)** cho người đọc tiếng Anh, hoặc một cách dịch tiếng Việt phù hợp khi người đọc chọn tiếng Việt.

Java có nhóm API `java.util.Locale.getDisplay*` giúp biến các **mã locale** thành **chuỗi có thể trình bày cho người dùng**, theo ngôn ngữ hiển thị được chọn. Chúng có từ các phiên bản Java trước đây và **vẫn được hỗ trợ trong Java 17+**. Với script và Unicode language tags, Java 7 bổ sung các thành phần quan trọng; những ví dụ trong bài sử dụng API Java 17+ hiện hành.

Điểm cốt lõi:

- **Locale đang được mô tả**: ví dụ `Locale.forLanguageTag("de-DE")`, nghĩa là tiếng Đức ở Đức.
- **Locale của người xem giao diện**: ví dụ `Locale.ENGLISH` hoặc `Locale.forLanguageTag("vi-VN")`.
- **Mã để lưu/trao đổi**: `toLanguageTag()`, hoặc các mã riêng `getLanguage()`, `getCountry()`, `getScript()`, `getVariant()`.
- **Nhãn để hiển thị**: `getDisplayName(viewerLocale)`, `getDisplayLanguage(viewerLocale)`, `getDisplayCountry(viewerLocale)`, `getDisplayScript(viewerLocale)`, `getDisplayVariant(viewerLocale)`.

**Không thay mã BCP 47 bằng chuỗi hiển thị khi lưu database, làm ID hoặc so sánh quyền truy cập.** Tên hiển thị có thể thay đổi theo ngôn ngữ người dùng, phiên bản JDK, CLDR hoặc provider; một tên có thể không đủ để phân biệt hai locale. Mã language tag là lựa chọn phù hợp hơn cho định danh/cấu hình.

### 1.1. Hai Locale trong cùng một biểu thức

```java
Locale subject = Locale.forLanguageTag("de-DE");
Locale viewer  = Locale.forLanguageTag("vi-VN");
String label   = subject.getDisplayName(viewer);
```

Đây là **snippet trong một method**, với `import java.util.Locale;`. Đọc theo thứ tự:

1. `subject` là đối tượng được đặt tên.
2. `viewer` chỉ **ngôn ngữ/cách hiển thị** mà ứng dụng muốn dùng.
3. `label` là tên có thể hiển thị cho người dùng đang chọn tiếng Việt, **không phải** mã `de-DE`.

Kết quả cụ thể của `label` phụ thuộc dữ liệu địa phương hóa của runtime. Không hardcode một câu dịch tiếng Việt rồi coi đó là output bắt buộc của mọi JVM.

### 1.2. Mục tiêu học tập

Sau khi học, bạn có thể:

- Phân biệt các phương thức lấy **mã** với các phương thức lấy **display name**.
- Dùng đúng overload có tham số `Locale inLocale`, tránh phụ thuộc nhầm vào default locale toàn tiến trình.
- Hiểu thành phần language, region, script, variant, Unicode extensions khi tạo tên.
- Tạo giao diện chọn locale với khóa bền vững và nhãn địa phương hóa.
- Hiểu `Locale.Category.DISPLAY` khác `Locale.Category.FORMAT`.
- Phân loại trường hợp trống, thiếu bản dịch, fallback về tiếng Anh/mã ISO.
- Tôn trọng Unicode, tên viết bằng hệ chữ RTL, sort theo `Collator` thay vì theo byte.
- Mở rộng cách dùng sang `Currency.getDisplayName(Locale)` và `ZoneId.getDisplayName(TextStyle,Locale)`.
- Viết test đúng: kiểm tra invariants ổn định thay vì cố định toàn bộ chuỗi dịch giữa nhiều bản JDK.

## 2. Locale là gì? Không nhầm ngôn ngữ với vùng

`java.util.Locale` mô tả các lựa chọn liên quan ngôn ngữ/địa phương hóa. Các thành phần chính:

| Thành phần | Ví dụ | Lấy mã | Ý nghĩa |
| --- | --- | --- | --- |
| Language | `de`, `vi`, `zh` | `getLanguage()` | Mã ngôn ngữ, thường theo ISO 639 |
| Script | `Latn`, `Hant`, `Cyrl` | `getScript()` | Hệ chữ, ISO 15924 |
| Region | `DE`, `VN`, `TW` | `getCountry()` | Quốc gia/vùng theo mã region BCP 47 |
| Variant | `POSIX` | `getVariant()` | Biến thể theo convention/tags |
| Unicode extension | `u-nu-thai` | `getUnicodeLocaleType("nu")` | Một thuộc tính hành vi địa phương hóa |
| Toàn bộ language tag | `zh-Hant-TW` | `toLanguageTag()` | Biểu diễn BCP 47 để trao đổi |

**Lưu ý:** `getCountry()` trả region code, không phải tên quốc gia/vùng được dịch. Với locale `zh-Hant-TW`:

```java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");
String languageCode = locale.getLanguage(); // "zh"
String scriptCode   = locale.getScript();   // "Hant"
String regionCode   = locale.getCountry();  // "TW"
String tag          = locale.toLanguageTag();// "zh-Hant-TW"
```

Các comment là mã có cấu trúc, ổn định về mặt ý nghĩa cho locale đã tạo. Nếu muốn **chuỗi trình bày** như tên của tiếng Trung, hệ chữ truyền thống hoặc vùng Đài Loan, gọi các phương thức `getDisplay*` với locale đích.

### 2.1. BCP 47 và Locale.forLanguageTag

Trong Java 17:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS  = Locale.forLanguageTag("en-US");
Locale chineseTW  = Locale.forLanguageTag("zh-Hant-TW");
```

Đây là snippet Java 17+, không cần thư viện ngoài. `Locale.forLanguageTag` là cách rõ ràng khi input là **BCP 47 language tag**; dùng dấu gạch ngang `-` giữa các subtags, không thay thế bằng dấu gạch dưới từ định dạng legacy `en_US`.

Đối với đầu vào không được kiểm soát, cần biết `forLanguageTag` có cơ chế xử lý các subtags không well-formed một cách tương đối dễ dãi: có thể bỏ subtag không hợp lệ và phần còn lại. Nếu ứng dụng bắt buộc input **đúng cú pháp**, dùng `new Locale.Builder().setLanguageTag(tag).build()` và xử lý `IllformedLocaleException` thay vì im lặng chấp nhận một tag bị cắt bớt.

### 2.2. Locale.Builder hữu ích khi có script/variant/extension

```java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setVariant("POSIX")
        .build();
```

Đây là snippet trong method. Builder kiểm tra cấu trúc các thành phần theo yêu cầu cú pháp; nó **không xác nhận mọi subtag có tồn tại và được dịch trong CLDR/IANA**. Kết quả từ `toLanguageTag()` ở ví dụ là `en-US-POSIX`.

### 2.3. Locale không chứa bản dịch cho mọi ngôn ngữ trên thế giới

Một locale có thể biểu diễn tag hợp lệ, nhưng JDK hiện tại không nhất thiết có dữ liệu dịch tên tương ứng cho mọi ngôn ngữ/vùng/variant/script. Các phương thức getDisplay có **fallback**; không suy rằng bản dịch tiếng Việt luôn có đủ chỉ vì caller truyền `vi-VN`.

### 2.4. ROOT và "und"

`Locale.ROOT` là locale không mang language/region/script/variant riêng. `Locale.ROOT.toLanguageTag()` trả `und` (*undetermined*). `Locale.ROOT.getDisplayName(Locale.ENGLISH)` trả chuỗi rỗng trong tình huống không có thành phần để trình bày. Khi xây dropdown, nên xử lý rõ trường hợp này thay vì vẽ một lựa chọn rỗng không thể nhấp.

## 3. Bảng các phương thức getDisplay của Locale

| API | Ý nghĩa của nhãn | Nếu thành phần không có |
| --- | --- | --- |
| `getDisplayLanguage(inLocale)` | Tên ngôn ngữ theo `inLocale` | Chuỗi rỗng nếu thiếu mã language |
| `getDisplayCountry(inLocale)` | Tên vùng/quốc gia theo `inLocale` | Chuỗi rỗng nếu thiếu mã region |
| `getDisplayScript(inLocale)` | Tên hệ chữ viết theo `inLocale` | Chuỗi rỗng nếu thiếu mã script |
| `getDisplayVariant(inLocale)` | Tên biến thể theo `inLocale` | Chuỗi rỗng nếu thiếu mã variant |
| `getDisplayName(inLocale)` | Tên tổng hợp cho locale, có thể gồm optional Unicode extensions | Chuỗi rỗng nếu không có thành phần cần biểu diễn |
| `getDisplayLanguage()` và các overload không tham số | Theo locale mặc định của category `DISPLAY` | Phụ thuộc cấu hình của JVM |

**Tham số `inLocale` chỉ định ngôn ngữ của nhãn**, không biến đổi locale đang được đặt tên.

### 3.1. getDisplayLanguage(Locale)

```java
Locale target = Locale.forLanguageTag("de-DE");
String englishLanguage = target.getDisplayLanguage(Locale.ENGLISH);
```

Trên môi trường kiểm thử Windows/JDK 24, `englishLanguage` là `"German"`. Tuy nhiên các nhãn có thể được cập nhật theo dữ liệu JDK/CLDR; đừng đưa chúng vào persistent keys.

### 3.2. getDisplayCountry(Locale)

```java
String englishCountry = target.getDisplayCountry(Locale.ENGLISH);
```

Với `de-DE`, kết quả trong môi trường kiểm thử là `"Germany"`. Tên quốc gia/vùng có thể thay đổi theo locale người xem, tiêu chuẩn chính tả và bản cập nhật dữ liệu ngôn ngữ.

### 3.3. getDisplayScript(Locale)

```java
Locale chineseTraditional = Locale.forLanguageTag("zh-Hant-TW");
String scriptLabel = chineseTraditional.getDisplayScript(Locale.ENGLISH);
```

Cần truyền locale có **script subtag** (ở đây `Hant`) thì mới có display script có ý nghĩa. Nếu locale không khai báo script, API trả chuỗi rỗng; nó **không** tự suy ra script chắc chắn dựa trên language hoặc region.

### 3.4. getDisplayVariant(Locale)

```java
Locale variant = new Locale.Builder()
        .setLanguage("en").setRegion("US")
        .setVariant("POSIX").build();
String variantLabel = variant.getDisplayVariant(Locale.ENGLISH);
```

Đây là snippet trong method. Tên variant có thể là tên được dịch hoặc fallback về dạng mã/nhãn được JDK biết. Nếu locale không có variant, kết quả là rỗng.

### 3.5. getDisplayName(Locale)

```java
String full = target.getDisplayName(Locale.ENGLISH);
```

Đây là cách lấy **tên đầy đủ** phục vụ hiển thị, kết hợp những thành phần như language, script, region, variant và **các Unicode extensions tùy chọn**. Cách đặt dấu ngoặc, dấu phẩy, cách dịch tên extension và thứ tự trình bày có quy tắc được Javadoc mô tả và có thể địa phương hóa.

Ví dụ kiểm thử `de-DE` trong Locale.ENGLISH trả `"German (Germany)"`. Không tự dựng `language + " (" + country + ")"` cho mọi ngôn ngữ, vì cấu trúc/tách từ/dấu câu có thể khác; hãy ưu tiên `getDisplayName(viewerLocale)`.

## 4. Đặc điểm quan trọng: cùng một subject, nhiều tên hiển thị

Giả sử subject là `Locale.forLanguageTag("de-DE")`. Người dùng chọn tiếng Anh và tiếng Việt:

```java
Locale target = Locale.forLanguageTag("de-DE");
Locale englishUI = Locale.ENGLISH;
Locale vietnameseUI = Locale.forLanguageTag("vi-VN");

String englishLabel = target.getDisplayName(englishUI);
String vietnameseLabel = target.getDisplayName(vietnameseUI);
String stableValue = target.toLanguageTag();
```

Đây là snippet Java 17+. Hai labels có thể khác nhau, còn `stableValue` vẫn là `de-DE`. Một biểu mẫu chọn ngôn ngữ nên biểu diễn dữ liệu như:

```text
Option:
  value = de-DE                    // máy đọc / API / database
  label = getDisplayName(userUI)   // người đọc

Không được đảo vai:
  value = tên được dịch
  label = mã kỹ thuật làm tên chính cho mọi người dùng
```

### 4.1. Locale UI là sở thích của người xem, không nhất thiết của server

Nếu server có default locale tiếng Anh nhưng người dùng đăng nhập và chọn tiếng Việt, phải truyền `vi-VN` một cách **tường minh** cho label. Không trông cậy vào cấu hình của máy chủ:

```java
String label = requestedLocale.getDisplayName(userUiLocale);
```

Với ứng dụng nhiều tenants/users, đây là điểm rất quan trọng vì mỗi request có thể cần ngôn ngữ UI khác nhau.

### 4.2. Lấy mã ISO khác với tên hiển thị

- `target.getLanguage()` trả `de` — thích hợp khi phải đọc mã.
- `target.getCountry()` trả `DE` — mã vùng.
- `target.toLanguageTag()` trả `de-DE` — mã locale hoàn chỉnh.
- `target.getDisplayName(Locale.ENGLISH)` trả tên hiển thị theo tiếng Anh.

Nếu trong UI bạn ghi `"de"` rồi cho rằng đó là “tên tiếng Đức”, người dùng không biết nó đại diện cho điều gì. Ngược lại, nếu bạn lấy chữ `"German"` rồi đưa vào API cần BCP 47 tag, đó cũng là lỗi.

### 4.3. Tên ngôn ngữ nội sinh và tên đã dịch

Trong giao diện đa ngôn ngữ, đôi khi cần hiển thị hai nhãn:

- **Endonym**: ngôn ngữ được gọi bằng chính ngôn ngữ đó, chẳng hạn gọi `target.getDisplayLanguage(target)`.
- **Exonym/translated label**: ngôn ngữ được gọi bằng ngôn ngữ của người xem, chẳng hạn `target.getDisplayLanguage(uiLocale)`.

Hai cách đều có thể hợp lý. Với dropdown chọn ngôn ngữ, có thể trình bày **hai nhãn** để người dùng tìm được ngôn ngữ ngay cả khi đang ở UI họ chưa hiểu. Nhưng không tự ghép strings thành khóa lưu trữ; phải giữ `toLanguageTag()`.

### 4.4. Không dùng getDisplayName để quyết định content locale

Nhãn là kết quả mô tả, không phải thuật toán negotiation. Dùng user preference, profile setting, `Accept-Language` negotiation hoặc supported locale allowlist để chọn locale nội dung, rồi dùng getDisplayName khi hiển thị. Không lấy chuỗi đã dịch rồi cố reverse-parse thành locale.

## 5. Chương trình chạy được 1: DisplayNameBasicsDemo

**Tệp: `DisplayNameBasicsDemo.java`**

Chương trình phân biệt mã locale với tên tiếng Anh và tên tiếng Việt. Nó cố ý chỉ in **boolean** với tên tiếng Việt để phần expected output không phụ thuộc bản dịch cụ thể của CLDR.

```java
import java.util.Locale;

public class DisplayNameBasicsDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("de-DE");
        Locale ui = Locale.forLanguageTag("vi-VN");
        Locale english = Locale.ENGLISH;
        String englishName = target.getDisplayName(english);
        String vietnameseName = target.getDisplayName(ui);

        System.out.println("language tag = " + target.toLanguageTag());
        System.out.println("language code = " + target.getLanguage());
        System.out.println("region code = " + target.getCountry());
        System.out.println("English language = " +
                target.getDisplayLanguage(english));
        System.out.println("English country = " +
                target.getDisplayCountry(english));
        System.out.println("English full name = " + englishName);
        System.out.println("Vietnamese full name present = " +
                !vietnameseName.isBlank());
        System.out.println("language code unchanged = " +
                target.getLanguage().equals("de"));
        System.out.println("UI locale used explicitly = " +
                ui.toLanguageTag().equals("vi-VN"));
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac --release 17 DisplayNameBasicsDemo.java
java DisplayNameBasicsDemo
```

**Stdout đã kiểm thử bằng Windows/JDK 24:**

```text
language tag = de-DE
language code = de
region code = DE
English language = German
English country = Germany
English full name = German (Germany)
Vietnamese full name present = true
language code unchanged = true
UI locale used explicitly = true
```

### 5.1. Vì sao code dùng `forLanguageTag`?

Vì bài đang làm việc với language tag BCP 47 có dấu gạch ngang. `Locale.forLanguageTag("de-DE")` biểu diễn đầy đủ cặp ngôn ngữ-vùng trong cú pháp chuẩn dùng với API/web.

### 5.2. Vì sao in tên tiếng Anh nhưng không in bản dịch tiếng Việt?

Chuỗi tiếng Anh cho `de-DE` hiện là tên rất quen thuộc; demo xác nhận đúng trên JDK đang chạy. Tuy nhiên cả tên tiếng Anh và tiếng Việt đều là **dữ liệu địa phương hóa** và có thể đổi ở phiên bản/JDK provider khác. Tập tests mạnh hơn nên kiểm tra:
- `getDisplayName(ui)` không rỗng cho một locale phổ biến.
- Tag mã vẫn là `de-DE`.
- Hai trường `getLanguage()`, `getCountry()` không biến đổi theo locale người xem.
- UI truyền đúng `ui` thay vì lỡ dùng default.

### 5.3. Vì sao tên có thể khác mà mã không khác?

Vì dữ liệu locale mô tả **bản sắc của language tag**, còn tên hiển thị là **bản dịch của mô tả đó**. Một ứng dụng đa ngôn ngữ cần tách hai tầng này để không phát sinh key migrations chỉ do CLDR đổi cách viết.

### 5.4. Có thể dùng `Locale.GERMANY` không?

`Locale.GERMANY` là một constant locale đại diện cho German ở Germany. Dùng constant nếu phù hợp. Nhưng khi input đến từ cấu hình/API dynamic, `Locale.forLanguageTag("de-DE")` thuận tiện và nhất quán hơn. Không cần tự tạo tên locale bằng string concatenation thủ công.

## 6. Script, region, variant và optional Unicode extensions

Một language tag có thể phức tạp hơn `language-region`. Ví dụ:

```text
zh-Hant-TW
│  │    └── region = TW
│  └─────── script = Hant
└────────── language = zh

en-US-POSIX
│  │  └──── variant = POSIX
│  └─────── region = US
└────────── language = en

en-US-u-nu-thai
│  │  │ │  └── Unicode locale type = thai
│  │  │ └──── Unicode locale key = nu (numbering system)
│  └──└────── extension section
└──────────── language = en
```

Đây là sơ đồ, không phải file nguồn. Với `zh-Hant-TW`, hệ chữ `Hant` quan trọng vì cùng language code có thể có hai writing systems. Nếu UI chỉ hiển thị tên language mà bỏ script/region, người dùng có thể chọn nhầm.

### 6.1. getDisplayScript không suy script bị thiếu

Nếu target là `en-US` và không khai báo script, `getDisplayScript(Locale.ENGLISH)` trả rỗng. Nó **không** tự trả “Latin” chỉ vì tiếng Anh thường dùng Latin script. Không ép UI phải hiển thị một script không có trong dữ liệu khi sử dụng API getDisplayScript.

### 6.2. getDisplayVariant có thể fallback

Variant là phần ít phổ biến; những mã tùy biến có thể không có translation. API trả tên phù hợp nếu có, fallback nếu không. Nếu subject không có variant, kết quả là rỗng — điều đó là đúng, không phải dấu hiệu lỗi hay bị thiếu dữ liệu một cách bất thường.

### 6.3. Unicode locale extension ảnh hưởng định dạng, không biến tag thành nhãn

`en-US-u-nu-thai` chứa Unicode locale keyword `nu=thai`. Java có:

```java
Locale locale = Locale.forLanguageTag("en-US-u-nu-thai");
String numbering = locale.getUnicodeLocaleType("nu"); // "thai"
String tag = locale.toLanguageTag(); // "en-US-u-nu-thai"
```

`getDisplayName(Locale)` theo Java SE 17 có thể kết hợp **optional Unicode extensions** khi tạo tên đầy đủ. Nhưng tên/sự hỗ trợ localization của các extensions phụ thuộc runtime data. Nếu cần **khôi phục chính xác extension**, dùng `getUnicodeLocaleType("nu")` hoặc `toLanguageTag()`, **không phân tích chuỗi getDisplayName**.

### 6.4. Đừng nhầm variant với Unicode extension

BCP 47 có cú pháp riêng cho variants và extensions. Một lựa chọn hệ số viết, lịch hoặc collation có thể được biểu diễn qua Unicode locale extension, không nhất thiết qua variant. Không tự gắn suffix tùy ý rồi mong `Locale`, `NumberFormat` và CLDR hiểu cùng semantics.

## 7. Chương trình chạy được 2: DisplayComponentsDemo

**Tệp: `DisplayComponentsDemo.java`**

Mục tiêu là dùng đủ các method: `getDisplayScript`, `getDisplayVariant`, `getDisplayName`; xem mã language/script/region, và đọc Unicode numbering extension bằng API chuyên dụng.

```java
import java.util.Locale;

public class DisplayComponentsDemo {
    public static void main(String[] args) {
        Locale written = Locale.forLanguageTag("zh-Hant-TW");
        Locale variant = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setVariant("POSIX").build();
        Locale extension = Locale.forLanguageTag("en-US-u-nu-thai");
        Locale plain = Locale.forLanguageTag("en-US");
        Locale ui = Locale.ENGLISH;

        System.out.println("script tag = " + written.toLanguageTag());
        System.out.println("language code = " + written.getLanguage());
        System.out.println("script code = " + written.getScript());
        System.out.println("region code = " + written.getCountry());
        System.out.println("display script present = " +
                !written.getDisplayScript(ui).isBlank());
        System.out.println("display full name present = " +
                !written.getDisplayName(ui).isBlank());
        System.out.println("variant tag = " + variant.toLanguageTag());
        System.out.println("variant code = " + variant.getVariant());
        System.out.println("display variant present = " +
                !variant.getDisplayVariant(ui).isBlank());
        System.out.println("unicode numbering = " +
                extension.getUnicodeLocaleType("nu"));
        System.out.println("extension retained in tag = " +
                extension.toLanguageTag().contains("-u-nu-thai"));
        System.out.println("plain script display empty = " +
                plain.getDisplayScript(ui).isEmpty());
        System.out.println("plain variant display empty = " +
                plain.getDisplayVariant(ui).isEmpty());
    }
}
```

Chạy:

```bash
javac --release 17 DisplayComponentsDemo.java
java DisplayComponentsDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
script tag = zh-Hant-TW
language code = zh
script code = Hant
region code = TW
display script present = true
display full name present = true
variant tag = en-US-POSIX
variant code = POSIX
display variant present = true
unicode numbering = thai
extension retained in tag = true
plain script display empty = true
plain variant display empty = true
```

### 7.1. Tại sao không assert đúng cách dịch tên của Hant?

CLDR, JDK locale data và cách trình bày trong từng ngôn ngữ có thể thay đổi. Dù JDK thường có nhãn tiếng Anh cho Hant, một test tốt về **API behavior** nên kiểm tra thành phần có tồn tại và phương thức trả nhãn không rỗng, còn nội dung dịch cụ thể có thể được kiểm thử ở UI snapshot có versioned data được kiểm soát.

### 7.2. Vì sao `getDisplayScript` rỗng khi tag không có script?

Locale `en-US` chỉ khai báo language và region. Không có script field thì method trả rỗng theo contract. Nếu UI cần danh sách script trong một setting chuyên biệt, phải lấy script từ dữ liệu có thật; không suy ra ngầm rồi ghi thành thuộc tính của locale.

### 7.3. POSIX và BCP 47

`Locale.Builder` kiểm tra cú pháp variant; `POSIX` được biểu diễn đúng trong `en-US-POSIX`. Điều đó không chứng minh mọi Java provider đều có một bản dịch user-friendly riêng cho variant. Đối với nhãn UI, có thể fallback về variant code khi không có tên được dịch.

### 7.4. Optional extensions và tên đầy đủ

Một tên từ `getDisplayName(ui)` có thể bao gồm một số extension labels nếu data hỗ trợ. Trong trường hợp backend cần identity chính xác, luôn giữ `toLanguageTag()`. Phần hiển thị không phải serialization format.

## 8. Hai category mặc định: DISPLAY và FORMAT

`Locale.getDefault()` trả locale mặc định chung của JVM. Java cũng cung cấp:

```java
Locale defaultForLabels =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale defaultForFormatting =
        Locale.getDefault(Locale.Category.FORMAT);
```

Đây là hai category **khác nhau**:

- **DISPLAY:** dành cho các tên hiển thị, nhãn ngôn ngữ, tên tiền tệ, các text mang tính UI.
- **FORMAT:** dành cho định dạng số, ngày, tiền và các biểu diễn chịu quy tắc formatting.

Khi gọi `target.getDisplayName()` **không có tham số**, API dùng **locale mặc định thuộc category DISPLAY**. Khi gọi `target.getDisplayName(uiLocale)`, nó dùng **đúng tham số explicit**, không phụ thuộc default của server.

### 8.1. Tại sao không nên dựa vào default locale cho mọi request?

Trong web service đa tenant, request A có thể cần tiếng Việt, request B cần tiếng Pháp. `Locale.setDefault(...)` thay đổi trạng thái **toàn JVM**, không phải thread-local riêng của request. Đổi default giữa chừng có thể khiến response khác bị hiển thị sai. Cách an toàn hơn:

```java
Locale requested = Locale.forLanguageTag("fr-CA");
Locale userUi = Locale.forLanguageTag("vi-VN");
String visibleLabel = requested.getDisplayName(userUi);
```

**Không gọi `Locale.setDefault` trong request handler** để thay ngôn ngữ của từng người dùng.

### 8.2. Khi nào overload không tham số phù hợp?

Ứng dụng desktop/CLI single-user với một default DISPLAY locale cố định có thể dùng `getDisplayName()` cho tiện. Nhưng vẫn nên ưu tiên overload explicit nếu code được dùng trong library, UI nhiều người dùng hoặc unit test cần deterministic behavior.

### 8.3. Không đồng nhất DISPLAY với FORMAT

Nếu một người dùng chọn nhãn giao diện tiếng Việt nhưng muốn định dạng số kiểu en-US, ứng dụng có thể dùng hai locale khác nhau. Không được suy rằng `getDefault(Category.FORMAT)` luôn bằng `getDefault(Category.DISPLAY)`. Cần truyền đúng locale cho từng API.

### 8.4. Có thể setCategory DISPLAY riêng không?

Java có `Locale.setDefault(Locale.Category.DISPLAY, someLocale)`. Tuy nhiên đây là state global của JVM, không phù hợp làm giải pháp ngôn ngữ per-request. Trong test/unit code nếu buộc dùng, phải lưu và phục hồi default trong `finally`, tránh chạy song song những tests thay global state.

## 9. Trường hợp nhãn không được dịch và fallback

Các phương thức `getDisplayLanguage/Country/Script/Variant` ưu tiên dùng localized name phù hợp `inLocale`. Khi dữ liệu không có translation, tài liệu Java mô tả fallback, ví dụ về tên tiếng Anh, cuối cùng có thể là mã ISO/identifier. Nếu không có thành phần trong locale, API có thể trả **chuỗi rỗng**.

Hệ quả quan trọng:

- Đừng hứa tất cả ngôn ngữ/vùng có translation đầy đủ.
- Đừng coi kết quả bằng code là một exception; nhiều trường hợp đó là fallback hợp lệ.
- Đừng tự cắt chuỗi trên ký tự `(` hoặc `,` để lấy language/region.
- Đừng kiểm tra `getDisplayName().equals("German (Germany)")` trong regression test xuyên nhiều JDK versions rồi coi bất kỳ đổi tên nào là bug code.
- Với UI, cân nhắc tên rõ ràng, mã BCP 47 ở secondary line và fallback thân thiện.
- Mỗi lựa chọn chỉ có một **stable value**, nhưng label có thể dịch lại khi người dùng đổi ngôn ngữ UI.

### 9.1. Cách fallback đơn giản

```java
static String safeLabel(Locale target, Locale userUi) {
    String label = target.getDisplayName(userUi);
    return label.isBlank() ? target.toLanguageTag() : label;
}
```

Đây là method Java 17+ với import `java.util.Locale`. Với `Locale.ROOT`, `getDisplayName` rỗng nên fallback thành `und`. Nếu UI không nên có lựa chọn `und`, có thể chủ động loại nó khỏi danh sách supported locales thay vì cố dịch thành một language chưa biết.

### 9.2. Không coi chuỗi rỗng là lỗi trong mọi trường hợp

`getDisplayScript(Locale.ENGLISH)` trả rỗng cho `en-US` vì tag **không khai báo script**. Điều này khác với lỗi “JDK thiếu tài nguyên translation của Hant”. UI cần phân biệt “không có thành phần” và “có thành phần nhưng chỉ có fallback code”.

### 9.3. Thông báo cho người dùng khi dữ liệu chưa đầy đủ

Với một picker chứa language tag hiếm, có thể hiển thị label từ runtime và một mã secondary như `"xx-YY"` để hỗ trợ nhận diện. Không invent một tên tiếng bản địa khi không có dữ liệu đáng tin; dùng authoritative locale data/translation resources được quản lý trong product nếu UX đòi hỏi cao hơn.

## 10. Thiết kế dropdown chọn ngôn ngữ/vùng đúng

Một option tốt cần hai trường riêng:

```text
Option {
    tag:   "vi-VN",                 // stable machine-readable value
    label: getDisplayName(uiLocale) // user-facing localized text
}
```

Khi người dùng chọn một option, backend lưu **tag**, không lưu **label**. Khi UI locale đổi, lấy lại nhãn với getDisplayName(newUiLocale), không migrate ID.

### 10.1. Tại sao không dùng label làm key?

- Tên có thể dịch sang ngôn ngữ khác.
- CLDR/JDK có thể cập nhật danh xưng.
- Hai locales có thể có tên giống hoặc khó phân biệt nếu thiếu region/script.
- Display name có dấu câu/case/Unicode khác theo provider.
- UI labels không nhất thiết là một định dạng có thể parse lại thành language tag.

Khóa bền vững là một BCP 47 language tag được ứng dụng kiểm soát và canonicalize phù hợp.

### 10.2. Sort theo ngôn ngữ người dùng

Một danh sách hiển thị tiếng Việt không nên mặc định dùng `String.compareTo` để sắp theo Unicode code units nếu mục tiêu là thứ tự đọc tự nhiên. Dùng:

```java
Collator collator = Collator.getInstance(userUiLocale);
options.sort(Comparator.comparing(Option::label, collator));
```

Đây là snippet Java 17+; cần `java.text.Collator` và `java.util.Comparator`, với `Option.label()` là String. Không chia sẻ một `Collator` mutable giữa threads nếu không có thiết kế thread-safety phù hợp; mỗi request/function có thể tạo hoặc cung cấp bản riêng theo lifecycle.

### 10.3. Tên script giúp phân biệt

Nếu sản phẩm hỗ trợ `zh-Hans` và `zh-Hant` hoặc `sr-Cyrl` và `sr-Latn`, không chỉ dùng `getDisplayLanguage`; nên dùng `getDisplayName` hoặc thêm region/script label để user hiểu lựa chọn nào đang được chọn.

### 10.4. Không đưa mọi Locale JVM biết vào UI một cách tự động

`Locale.getAvailableLocales()` phản ánh các locales mà runtime hỗ trợ theo providers, không phải danh sách ngôn ngữ mà sản phẩm đã **dịch nội dung/kiểm thử đầy đủ**. Tạo allowlist các locale sản phẩm thật sự hỗ trợ, sau đó dùng getDisplayName để trình bày.

### 10.5. Kết hợp endonym và translated label

Một tùy chọn:

```java
String translated = target.getDisplayName(userUi);
String nativeName = target.getDisplayName(target);
String label = translated.equals(nativeName)
        ? translated
        : translated + " — " + nativeName;
```

Đây là snippet minh họa cho UI hai nhãn. Để code production, nên xử lý blank/fallback và cân nhắc duplicate, RTL, chiều dài. Không coi phép nối bằng dấu gạch là localization hoàn chỉnh cho mọi ngôn ngữ; tốt hơn dùng layout riêng cho primary/secondary labels.

## 11. Chương trình chạy được 3: LocalePickerDemo

**Tệp: `LocalePickerDemo.java`**

Chương trình tạo bốn options theo danh sách supported locales, lấy display name theo UI tiếng Việt, giữ stable BCP 47 tag, sort bằng `Collator` và xử lý ROOT fallback. Nó chỉ in các điều kiện ổn định, không in một bản dịch CLDR cụ thể.

```java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class LocalePickerDemo {
    record Option(String tag, String label) {}

    static Option option(Locale target, Locale ui) {
        String display = target.getDisplayName(ui);
        String tag = target.toLanguageTag();
        return new Option(tag, display.isBlank() ? tag : display);
    }

    public static void main(String[] args) {
        Locale viewer = Locale.forLanguageTag("vi-VN");
        List<Locale> available = List.of(
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("vi-VN"),
                Locale.forLanguageTag("fr-FR"),
                Locale.forLanguageTag("zh-Hant-TW"));
        List<Option> options = new ArrayList<>();
        for (Locale target : available) {
            options.add(option(target, viewer));
        }
        Collator collator = Collator.getInstance(viewer);
        options.sort(Comparator.comparing(Option::label, collator));

        Set<String> keys = new HashSet<>();
        boolean labelsPresent = true;
        boolean sorted = true;
        for (int i = 0; i < options.size(); i++) {
            Option current = options.get(i);
            keys.add(current.tag());
            labelsPresent &= !current.label().isBlank();
            if (i > 0) {
                sorted &= collator.compare(
                        options.get(i - 1).label(), current.label()) <= 0;
            }
        }

        System.out.println("options = " + options.size());
        System.out.println("distinct stable tags = " +
                (keys.size() == options.size()));
        System.out.println("display labels nonblank = " + labelsPresent);
        System.out.println("collator sorted = " + sorted);
        System.out.println("script tag retained = " +
                keys.contains("zh-Hant-TW"));
        System.out.println("missing label falls back to tag = " +
                option(Locale.ROOT, viewer).label().equals("und"));
    }
}
```

Chạy:

```bash
javac --release 17 LocalePickerDemo.java
java LocalePickerDemo
```

**Stdout đã kiểm thử bằng Windows/JDK 24:**

```text
options = 4
distinct stable tags = true
display labels nonblank = true
collator sorted = true
script tag retained = true
missing label falls back to tag = true
```

### 11.1. Vì sao Option là record?

Java 17 hỗ trợ records và `record Option(String tag,String label)` giúp biểu diễn cặp stable ID/display label ngắn gọn, immutable theo các String fields. Không cần tạo một mutable bean chỉ cho hai values.

### 11.2. Vì sao tạo ArrayList từ danh sách?

`List.of(...)` bất biến; kết quả từ `stream().toList()` cũng không thích hợp để sort in-place. Demo tạo `new ArrayList<>()` để có thể `options.sort(...)`. Nếu UI framework tự sort, không cần mutate list trong service.

### 11.3. Vì sao Collator phụ thuộc viewer?

Thứ tự theo ngôn ngữ người dùng có thể khác thứ tự code-point. `Collator.getInstance(viewer)` tạo collator cho locale UI, phù hợp ý định đọc hiểu. Khi dữ liệu có cùng collator sort key, có thể thêm tie-breaker ổn định theo tag để tránh thứ tự khác nhau giữa runs nếu thiết kế yêu cầu.

### 11.4. Vì sao giữ Set tag?

`HashSet` dùng kiểm tra sự duy nhất của các tags; việc tags là machine-readable tránh phụ thuộc labels có thể trùng. Nếu hai khác nhau về tag nhưng label giống nhau, dropdown nên tăng thông tin phân biệt như region/script/tag.

### 11.5. Tại sao fallback về `und`?

Với `Locale.ROOT`, không có language/region để hiển thị, nên `getDisplayName` rỗng. `toLanguageTag()` trả `und`, làm fallback có text. Trong production, nếu `und` không có ý nghĩa với người dùng, tốt hơn là loại khỏi supported options hoặc hiển thị một thông điệp dịch sẵn bởi `ResourceBundle` của sản phẩm.

## 12. Currency và java.time: các API tên hiển thị liên quan

Chủ đề getDisplay không dừng ở `Locale`. Java có những API hiển thị tên cho loại dữ liệu khác, với tham số Locale của người xem.

### 12.1. Currency.getDisplayName(Locale)

`java.util.Currency` là đối tượng mô tả tiền tệ ISO 4217. Ví dụ:

```java
Currency eur = Currency.getInstance("EUR");
String code = eur.getCurrencyCode();         // "EUR"
String name = eur.getDisplayName(userUi);    // Tên tiền tệ theo UI locale.
String symbol = eur.getSymbol(userUi);       // Ký hiệu tiền tệ.
```

Đây là snippet với imports `java.util.Currency` và biến `Locale userUi` đã được khai báo. **Tên**, **mã** và **ký hiệu** có vai trò khác nhau. Đừng lưu chuỗi display name để đại diện duy nhất một loại tiền tệ trong database.

Khi không có tên được dịch, `Currency.getDisplayName(userUi)` fallback về currency code. Đừng tự suy rằng tên luôn được dịch hoặc luôn chứa ký hiệu `€`.

### 12.2. ZoneId.getDisplayName(TextStyle, Locale)

Trong Java 17+, nên dùng API hiện hành `java.time.ZoneId` cho múi giờ:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
String id = paris.getId(); // "Europe/Paris"
String display = paris.getDisplayName(TextStyle.FULL, userUi);
```

Đây là snippet với `import java.time.ZoneId;` và `import java.time.format.TextStyle;`. Nếu runtime không tìm thấy tên địa phương hóa, API trả full ID. **ID múi giờ** vẫn được dùng để lưu/trao đổi; tên hiển thị chỉ dùng cho UI.

Không trộn **múi giờ** với **locale**: một locale vi-VN không có nghĩa múi giờ của người dùng phải là Asia/Ho_Chi_Minh, và ngược lại.

### 12.3. Month và DayOfWeek.getDisplayName

Các đối tượng `java.time.Month`, `DayOfWeek` cũng có `getDisplayName(TextStyle,Locale)`. Ví dụ:

```java
String weekday = java.time.DayOfWeek.MONDAY
        .getDisplayName(TextStyle.FULL, userUi);
```

Đây là snippet với TextStyle và userUi như trên. Cũng nên dùng tên hiển thị thay vì tự hardcode một mảng tiếng Anh rồi dịch thủ công cho mỗi ngôn ngữ.

### 12.4. getDisplayName không định dạng tiền/ngày

Nếu cần **giá trị** tiền hoặc ngày trong một locale, dùng `NumberFormat`, `DateTimeFormatter`, v.v. Tên hiển thị của `Currency` hoặc `ZoneId` không thay thế quy tắc format đầy đủ. Chẳng hạn `Currency.getDisplayName` cho một tên, nhưng cách đặt biểu tượng tiền trước/sau số và phân tách thập phân do `NumberFormat` quyết định.

## 13. Chương trình chạy được 4: DISPLAY vs FORMAT, Currency và ZoneId

**Tệp: `DisplayCategoryDemo.java`**

Demo này không thay đổi default locale JVM. Nó chỉ đọc `Locale.Category.DISPLAY/FORMAT` và chứng minh overload không tham số tương đương overload dùng DISPLAY default cho các tên trên `Locale`. Đồng thời nó minh họa `Currency.getDisplayName(Locale)` và `ZoneId.getDisplayName(TextStyle,Locale)`.

```java
import java.time.ZoneId;
import java.time.format.TextStyle;
import java.util.Currency;
import java.util.Locale;

public class DisplayCategoryDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("fr-CA");
        Locale displayDefault = Locale.getDefault(Locale.Category.DISPLAY);
        Locale formatDefault = Locale.getDefault(Locale.Category.FORMAT);
        Locale ui = Locale.forLanguageTag("vi-VN");
        Currency eur = Currency.getInstance("EUR");
        ZoneId paris = ZoneId.of("Europe/Paris");

        System.out.println("target tag = " + target.toLanguageTag());
        System.out.println("no-arg uses DISPLAY default = " +
                target.getDisplayName().equals(
                        target.getDisplayName(displayDefault)));
        System.out.println("no-arg language uses DISPLAY default = " +
                target.getDisplayLanguage().equals(
                        target.getDisplayLanguage(displayDefault)));
        System.out.println("no-arg country uses DISPLAY default = " +
                target.getDisplayCountry().equals(
                        target.getDisplayCountry(displayDefault)));
        System.out.println("FORMAT category exists = " +
                (formatDefault != null));
        System.out.println("currency code = " + eur.getCurrencyCode());
        System.out.println("currency display name present = " +
                !eur.getDisplayName(ui).isBlank());
        System.out.println("zone ID = " + paris.getId());
        System.out.println("zone display name present = " +
                !paris.getDisplayName(TextStyle.FULL, ui).isBlank());
    }
}
```

Chạy:

```bash
javac --release 17 DisplayCategoryDemo.java
java DisplayCategoryDemo
```

**Stdout đã kiểm thử bằng Windows/JDK 24:**

```text
target tag = fr-CA
no-arg uses DISPLAY default = true
no-arg language uses DISPLAY default = true
no-arg country uses DISPLAY default = true
FORMAT category exists = true
currency code = EUR
currency display name present = true
zone ID = Europe/Paris
zone display name present = true
```

### 13.1. Vì sao output stable?

Demo không in trực tiếp tên vùng, tiền tệ hoặc múi giờ có thể đổi theo JDK provider; nó in mã và các bất biến được hợp đồng API hỗ trợ. Các tên dịch vẫn được gọi **thực sự** và được xác nhận không rỗng.

### 13.2. DISPLAY vs FORMAT không nhất thiết giống nhau

Hai categories là hai mặt khác nhau của i18n. Một setting có thể là display language `vi-VN`, formatting locale `en-US`. Trong ứng dụng web, truyền explicit locale là cách tránh race và bất ngờ khi default JVM không trùng user preference.

### 13.3. Một code EUR không phải một ký hiệu hiển thị cố định

`Currency.getCurrencyCode()` trả `EUR`. `getSymbol(ui)` và `getDisplayName(ui)` phụ thuộc locale người xem, có thể khác nhau. Nếu user cần phân biệt nhiều currencies có ký hiệu giống nhau, code EUR là thành phần định danh đáng tin hơn trong database.

### 13.4. ZoneId ID và localized zone name là hai dữ liệu khác

`Europe/Paris` là timezone identifier. `getDisplayName(TextStyle.FULL,ui)` trả tên trình bày hoặc ID fallback. Một display name có thể mơ hồ hoặc thay đổi theo dữ liệu timezone; hệ thống lên lịch nên giữ ZoneId, không parse display string ngược thành ID.

## 14. Locale.Category.DISPLAY mặc định và quản lý toàn JVM

Một ứng dụng dùng:

```java
Locale.getDefault(Locale.Category.DISPLAY)
```

để biết display locale mặc định. Điều này hữu ích ở môi trường chỉ có một người dùng, nhưng trong hệ thống multi-tenant cần tách khỏi context từng request.

### 14.1. Tránh thay Locale.setDefault cho từng request

Sai về mô hình concurrency:

```java
Locale.setDefault(Locale.Category.DISPLAY,
        Locale.forLanguageTag("vi-VN"));
String label = target.getDisplayName();
```

Đây là snippet **anti-pattern trong web request**: default được thay toàn JVM, request khác có thể thay lại ngay sau đó. Không có bảo đảm mỗi thread nhìn được một default riêng theo user của nó.

Đúng hơn:

```java
Locale uiLocale = Locale.forLanguageTag("vi-VN");
String label = target.getDisplayName(uiLocale);
```

Khi code chạy trong shared service, truyền explicit UI locale qua method parameters hoặc request context đã được thiết kế thread-safe.

### 14.2. Nếu test buộc phải thay default

Trong tests isolated:

```java
Locale old = Locale.getDefault(Locale.Category.DISPLAY);
try {
    Locale.setDefault(Locale.Category.DISPLAY, Locale.FRENCH);
    // Kiểm thử hành vi default DISPLAY trong môi trường riêng.
} finally {
    Locale.setDefault(Locale.Category.DISPLAY, old);
}
```

Đây là **snippet**, nên tránh chạy song song với các tests/requests khác vì nó sửa global state. Có thể viết test tốt hơn bằng overload explicit và không cần thay default.

### 14.3. Không dựa vào locale mặc định của container

Máy development có thể mặc định en-US, container staging mặc định en-GB, còn production vi-VN. Nếu gọi `getDisplayName()` trong service mà không chọn rõ locale, chuỗi hiển thị có thể khác giữa môi trường. Với public API trả labels, truyền userUiLocale rõ hoặc cung cấp một locale cố định phù hợp yêu cầu sản phẩm.

## 15. Unicode: tên hiển thị không phải ASCII

Localized display names có thể chứa dấu tiếng Việt, chữ Hán, Cyrillic, Arabic, dấu phụ và các ký tự ngoài ASCII. Các lỗi cần tránh:

- Chuyển byte với charset mặc định mà không thống nhất UTF-8 trên API/file.
- Cắt string theo byte length, làm hỏng chuỗi Unicode.
- Đổi chữ hoa/thường bằng `toUpperCase()` không có locale nếu thao tác liên quan ngôn ngữ.
- Dùng `String.compareTo()` để sắp text theo quy tắc chữ cái của người dùng.
- Tìm regex bằng `[A-Za-z]` rồi coi đó là mọi chữ cái.
- Thay Unicode combining marks mà không hiểu normalization.
- Quên xử lý bidi/RTL khi hiển thị tên ngôn ngữ viết từ phải sang trái.

### 15.1. String.length đo UTF-16 units, không đo số grapheme

Trong Java, `String.length()` trả số **UTF-16 code units**. Một ký tự nhìn thấy trên màn hình có thể gồm nhiều code points, dấu phụ hoặc emoji sequence. Nếu UI cần truncate display label theo số ký tự nhìn thấy, không tùy tiện cắt `label.substring(0,10)` rồi suy rằng luôn giữ nguyên 10 ký tự người dùng đọc.

Sử dụng khả năng typography/layout của UI framework, hoặc Unicode-aware segmentation theo yêu cầu sản phẩm. Đây là vấn đề **presentation**, không phải trách nhiệm của `Locale.getDisplayName`.

### 15.2. Normalizer để xử lý user-authored text, không phá CLDR labels

`java.text.Normalizer` có thể hỗ trợ NFC/NFD normalization trong những trường hợp cần so sánh hoặc lưu Unicode do người dùng nhập. Nhưng **không** normalize/casefold nhãn để biến nó thành ID. Locale identity nên dùng BCP 47 tag được chuẩn hóa phù hợp.

### 15.3. Collator để sắp xếp

`Collator.getInstance(userUiLocale)` giúp sort theo ngôn ngữ người đọc. Không dùng kết quả `Collator.compare(a,b)==0` làm khóa phân biệt duy nhất: Collator có thể xem một số khác biệt là không đáng kể theo strength/collation settings.

Nếu cần order ổn định và hoàn toàn quyết định, thêm tie-breaker theo `toLanguageTag()` sau so sánh display label.

### 15.4. RTL và Unicode bidi

Với các tên bản địa như tiếng Arabic hoặc Hebrew, UI có thể phải xử lý direction/bidi isolation ở cấp component. Không chèn thủ công các dấu bidi control bất thường vào mã lưu trữ để “sửa” hiển thị; hãy dùng UI component có hỗ trợ Unicode BiDi và giữ dữ liệu gốc sạch.

### 15.5. Security: nhãn dịch là dữ liệu, không là HTML

Nếu web UI render localized labels, hãy dùng text nodes/escaping đúng thay vì chèn vào HTML không được kiểm soát. Điều này đặc biệt quan trọng khi danh sách chứa tên tùy chỉnh từ người dùng hoặc remote sources, không chỉ labels từ JDK. `getDisplayName` không phải cơ chế HTML escaping.

## 16. Nhận language tag từ bên ngoài: validate và allowlist

Một ứng dụng có thể nhận `"vi-VN"` từ profile, request parameter hoặc HTTP header. Thứ tự xử lý hợp lý:

1. Đọc tag ở dạng string với giới hạn độ dài.
2. Kiểm tra **syntax BCP 47** theo policy.
3. Chuyển thành Locale.
4. Kiểm tra locale có thuộc **supported locales** của sản phẩm không.
5. Quyết định fallback content locale và UI locale nếu tag không hỗ trợ.
6. Chỉ sau đó gọi `getDisplayName(userUiLocale)` để hiển thị.

### 16.1. Locale.forLanguageTag và Locale.Builder có khác nhau

`Locale.forLanguageTag(tag)` thuận tiện nhưng **lenient** với một số malformed input: có thể bỏ phần không hợp lệ. `new Locale.Builder().setLanguageTag(tag).build()` phát hiện trường hợp không well-formed bằng `IllformedLocaleException`.

Ví dụ helper validation:

```java
static Locale validatedLocale(String tag) {
    if (tag == null || tag.isBlank() || tag.length() > 100) {
        throw new IllegalArgumentException("Invalid language tag");
    }
    try {
        return new Locale.Builder().setLanguageTag(tag).build();
    } catch (java.util.IllformedLocaleException e) {
        throw new IllegalArgumentException("Malformed BCP 47 tag", e);
    }
}
```

Đây là một method Java 17+ với `import java.util.Locale;`. Cú pháp hợp lệ **không có nghĩa sản phẩm có bản dịch**; vẫn cần allowlist.

### 16.2. Không dùng getDisplayName để parse tag

Một tên được dịch không xác định duy nhất language tag. Đừng nhận `"German (Germany)"` rồi viết parser tách ngoặc để lấy `de-DE`. Tên có thể đổi ngôn ngữ, dấu câu và thứ tự; BCP 47 tag mới là dạng trao đổi chính xác.

### 16.3. Accept-Language là một danh sách ưu tiên

HTTP `Accept-Language` có thể chứa nhiều ranges với trọng số, chẳng hạn `vi-VN,vi;q=0.9,en;q=0.7`. Không chuyển nguyên header vào `Locale.forLanguageTag(...)` và kỳ vọng lấy đúng một Locale. Dùng parser/negotiation thích hợp, ví dụ `Locale.LanguageRange.parse` và `Locale.lookup` khi phù hợp, hoặc framework locale resolver đã được kiểm thử.

Đừng để header từ client tự quyết định một locale mà product chưa dịch nội dung; phải giao với supported locales và có fallback rõ.

### 16.4. Locale data có thể được cập nhật

Bản thân format tag có chuẩn và API, nhưng tên quốc gia/ngôn ngữ có thể thay đổi theo CLDR, tiêu chuẩn địa lý/chính tả và JDK updates. Nếu một sản phẩm cần các nhãn đã được kiểm định/approve cố định vì thương hiệu hoặc pháp lý, quản lý chúng trong **translation resources được version hóa** thay vì giả định JDK API là copywriting chính thức không thay đổi.

## 17. Testing đúng cho getDisplay

### 17.1. Những gì nên assert

- `toLanguageTag()` trả mã kỳ vọng khi tạo Locale hợp lệ.
- `getLanguage/getCountry/getScript/getVariant` trả đúng các thành phần đã khai báo.
- `getDisplayName(uiLocale)` không rỗng với một locale phổ biến.
- Component không có trong Locale → phương thức getDisplay thành phần đó trả rỗng.
- Null tham số inLocale → API ném NullPointerException theo Javadoc.
- No-arg display method tương đương overload dùng `Locale.getDefault(Locale.Category.DISPLAY)` trong cùng trạng thái default.
- Option value không đổi khi viewer locale đổi.
- Dropdown không dùng label làm key.
- Fallback cho ROOT/und rõ ràng.
- Danh sách sắp theo `Collator` và tie-breaker nếu cần.
- Language tag malformed/unsupported được xử lý theo policy.

### 17.2. Những gì không nên assert cứng nếu không khóa JDK data

- Chuỗi dịch tiếng Việt/tiếng Pháp **phải** chính xác một cụm từ trên mọi JDK.
- Dấu phẩy và dấu ngoặc của getDisplayName luôn ASCII.
- Mọi locale đều có tên được dịch.
- Hai nhãn khác nhau cho tất cả các locale khác nhau.
- Tên vùng/quốc gia không bao giờ đổi trong tương lai.
- Một local provider với Unicode extension luôn hiển thị full extension bằng cùng wording.
- Mọi JVM có cùng danh sách supported locales.

### 17.3. Snapshot/UI tests cần quản lý môi trường

Nếu product cần test pixel/text snapshot chính xác, hãy cố định:
- JDK version/vendor và locale providers.
- CLDR/locale data version nếu môi trường cho phép.
- Locale UI explicit.
- Font và UI rendering environment nếu ảnh hưởng snapshot.
- Test fixtures/translation resources do product quản lý.

Đây là cách kiểm soát regression UI, khác với unit tests kiểm tra **hợp đồng Java API**.

### 17.4. Đừng test một default toàn JVM trong suite chạy song song

`Locale.setDefault` làm thay đổi global state và có thể tạo flaky tests giữa các threads. Ưu tiên overload explicit ở lớp service và tách tests default-category nếu thật sự cần.

## 18. Hiệu năng, cache và vòng đời

Phần lớn giao diện gọi getDisplay cho vài options; hiệu năng hiếm khi là bottleneck. Nhưng trong API cần render nhiều locale labels qua nhiều requests, có thể cân nhắc cache:

```text
Cache key:
  (targetLanguageTag, viewerLanguageTag, JDK/translation-data version)
Cache value:
  displayLabel
```

**Điểm quan trọng:** Cache key phải chứa **cả target và viewer locale**, không chỉ target. Nếu key chỉ là `de-DE` thì request tiếng Việt có thể nhận label tiếng Anh đã được cache ở request trước.

### 18.1. Có nên cache mã code thay vì Locale?

`Locale` là immutable/value-like theo ý nghĩa API, có thể chia sẻ; không cần parse lại tag liên tục nếu pipeline đã giữ đối tượng Locale. Nhưng cache labels vẫn phải xét khi thay language UI hoặc update JDK data.

### 18.2. Đừng cache nhãn vĩnh viễn trong database

Nếu nhãn do CLDR cung cấp, cache có TTL/version strategy, hoặc tạo lại khi hiển thị. Đừng materialize getDisplayName thành một field “localeName” rồi coi đó là dữ liệu chuẩn không bao giờ đổi.

### 18.3. Có cần benchmark?

Nếu có danh sách vài chục locales, việc render UI/network thường chiếm phần lớn chi phí. Chỉ benchmark khi profiler cho thấy getDisplay/Collator thực sự nằm trên hot path. Benchmark phải kiểm soát JIT warmup, provider, cache hit ratio và số lượng labels.

### 18.4. ResourceBundle khi nào hữu ích?

`ResourceBundle` hữu ích cho **bản dịch nội dung của chính sản phẩm**, nút bấm, help texts và thuật ngữ nghiệp vụ. Nó không thay thế getDisplay hoàn toàn; bạn có thể dùng:
- `getDisplayName(uiLocale)` cho tên locale chung.
- `ResourceBundle` cho tên/nhãn sản phẩm cần wording cố định.
- Một mapping product-approved nếu tên ngôn ngữ cần điều chỉnh chính tả/branding.

## 19. Những lỗi thường gặp

**1. “getLanguage trả tên ngôn ngữ cho người dùng.”** Sai: trả mã.

**2. “getCountry trả tên vùng/quốc gia theo tiếng Việt.”** Sai: trả mã vùng.

**3. “Locale.toString là chuẩn lưu BCP 47 tag.”** Không nên: dùng `toLanguageTag()` khi cần BCP 47.

**4. “en_US là cách viết chuẩn của BCP 47.”** Sai: dùng `en-US`.

**5. “Cứ gọi getDisplayName() là theo ngôn ngữ của user web.”** Sai: nó dùng JVM default DISPLAY, không nhất thiết là user locale.

**6. “getDisplayName(ui) biến target locale thành ui.”** Sai: nó chỉ dùng ui để **dịch tên target**.

**7. “Có thể lấy getDisplayName làm database primary key.”** Sai: nhãn dịch có thể đổi/trùng.

**8. “Mọi locale có display name được dịch 100%.”** Sai: có fallback về tiếng Anh/code.

**9. “Tên dịch hiện tại sẽ không bao giờ đổi ở JDK mới.”** Sai: locale data updates có thể thay đổi.

**10. “getDisplayScript luôn suy ra hệ chữ từ language.”** Sai: component script không có → rỗng.

**11. “getDisplayVariant luôn trả tên của một variant, kể cả không có variant.”** Sai: rỗng khi thiếu.

**12. “getDisplayName chỉ ghép language và country.”** Sai: có thể gồm script, variant và optional Unicode extensions.

**13. “Có thể reverse parse getDisplayName thành language tag.”** Không an toàn: cách dịch và dấu câu biến đổi.

**14. “Locale.forLanguageTag kiểm tra mọi tag được IANA/CLDR support.”** Sai: nó xử lý cú pháp/normalization, không xác nhận dịch đầy đủ.

**15. “Locale.Builder xác nhận subtag có đăng ký hợp pháp trên registry.”** Không: Builder chủ yếu kiểm tra well-formed syntax.

**16. “Locale.ROOT.getDisplayName luôn tạo tên user-friendly.”** Không: khi không có thành phần, có thể trả rỗng.

**17. “Locale.ROOT.toLanguageTag là một chuỗi rỗng.”** Sai: trả `und`.

**18. “Cứ có mã Hant thì lúc nào cũng in đúng một chuỗi tiếng Việt.”** Sai: runtime data/provider quyết định localization cụ thể.

**19. “Unicode extension có thể được đọc bằng cách tách getDisplayName.”** Sai: dùng `getUnicodeLocaleType` hoặc `toLanguageTag`.

**20. “Một variant POSIX phải được dịch giống nhau trên mọi JDK.”** Không bảo đảm.

**21. “Default DISPLAY và FORMAT luôn bằng nhau.”** Không có bảo đảm.

**22. “Locale.setDefault là thay ngôn ngữ riêng cho request.”** Sai: global JVM state.

**23. “Collator.compare(a,b) không cần locale người xem.”** Có thể sort sai theo ngôn ngữ người dùng.

**24. “String.compareTo luôn đúng thứ tự chữ cái cho mọi tiếng.”** Sai: so code units, không phải collation locale.

**25. “Collator.compare==0 nghĩa hai language tags giống nhau.”** Sai: comparison của labels không định danh locale.

**26. “Mọi JVM có cùng Locale.getAvailableLocales.”** Không nhất thiết: providers/versions khác.

**27. “getAvailableLocales là danh sách ngôn ngữ product đã dịch đủ.”** Sai: cần supported allowlist của product.

**28. “Chọn language chỉ cần getDisplayLanguage, không cần script/region.”** Không luôn: có thể gây nhầm hai phương án.

**29. “Dùng label làm cache key là đủ.”** Sai: labels có thể trùng và tùy viewer locale.

**30. “Cache theo target tag thôi là đủ cho labels đa ngôn ngữ.”** Sai: phải xét viewer locale.

**31. “Mọi chuỗi hiển thị Unicode là ASCII 1 byte/ký tự.”** Sai: Unicode có nhiều scripts và code points.

**32. “String.length là số grapheme người dùng thấy.”** Sai: đo UTF-16 code units.

**33. “Có thể cắt Unicode bằng bytes mà không làm hỏng text.”** Sai: phải xử lý encoding/segmentation.

**34. “Currency.getCurrencyCode giống Currency.getDisplayName.”** Sai: code vs tên hiển thị.

**35. “ZoneId.getDisplayName là timezone ID chuẩn lưu trữ.”** Sai: `getId()` là identifier.

**36. “Locale vi-VN mặc định xác định múi giờ Asia/Ho_Chi_Minh.”** Sai: locale không định danh time zone.

**37. “Một tên vùng hiển thị có thể dùng để parse/resolve mọi quốc gia.”** Sai: localization có thể mơ hồ và thay đổi.

**38. “getDisplayName tự escape HTML.”** Không: render text an toàn do UI framework.

**39. “Test chính xác một nhãn CLDR trên mọi JVM là unit test ổn định.”** Không: có thể flaky khi dữ liệu cập nhật.

**40. “Muốn UI theo user locale thì dùng getDisplay*(userUiLocale).”** Đúng: tường minh và dễ kiểm soát.

## 20. Checklist áp dụng trong sản phẩm

- [ ] Đã phân biệt locale **được đặt tên** với locale **của người xem**?
- [ ] Có tạo Locale từ BCP 47 tag hợp lệ bằng `Locale.forLanguageTag` hoặc `Locale.Builder`?
- [ ] Khi input không đáng tin, đã validate cú pháp và giới hạn độ dài?
- [ ] Có supported locale allowlist, không lấy trực tiếp mọi locale của JVM làm UI options?
- [ ] Stable option value lấy từ `toLanguageTag()`?
- [ ] Không lưu `getDisplayName` như khóa định danh?
- [ ] Có truyền explicit `userUiLocale` vào `getDisplayName(userUiLocale)`?
- [ ] Không dùng no-arg getDisplayName trong môi trường multi-user mà không hiểu default?
- [ ] Có hiểu default category DISPLAY khác FORMAT?
- [ ] Không đổi `Locale.setDefault` theo từng request?
- [ ] Có dùng `getDisplayLanguage` khi chỉ cần tên language?
- [ ] Có dùng `getDisplayCountry` khi cần tên region?
- [ ] Có dùng `getDisplayScript` khi locale khai báo script?
- [ ] Có dùng `getDisplayVariant` khi locale có variant?
- [ ] Có dùng `getDisplayName` khi cần tên tổng hợp?
- [ ] Có phân biệt Unicode extensions với variant/script?
- [ ] Nếu cần đọc extension, có dùng `getUnicodeLocaleType` hoặc tag?
- [ ] Không đoán script khi Locale không có script field?
- [ ] Đã xử lý kết quả rỗng cho thiếu thành phần/ROOT?
- [ ] Đã có fallback khi JDK không có bản dịch?
- [ ] Không phân tích dấu ngoặc/dấu phẩy của display name?
- [ ] Đã kiểm thử UI theo ít nhất hai viewer locales?
- [ ] Đã xét trường hợp labels trùng/khó phân biệt; có secondary code/script/region?
- [ ] Có dùng `Collator` với locale người dùng khi sort labels?
- [ ] Nếu cần sort ổn định, có tie-breaker theo tag?
- [ ] Không dùng `String.compareTo` làm collation theo ngôn ngữ?
- [ ] Đã hỗ trợ Unicode và UTF-8 trong API/file/text transport?
- [ ] Đã cân nhắc RTL/bidi và UI typography?
- [ ] Không dùng String.length như số grapheme chính xác?
- [ ] Có HTML escape/render text an toàn nếu dùng web?
- [ ] Nếu hiển thị currency, có dùng `Currency.getDisplayName(ui)`?
- [ ] Nếu hiển thị timezone, có dùng `ZoneId.getDisplayName(TextStyle,ui)`?
- [ ] Không nhầm tên hiển thị với currency code/timezone ID?
- [ ] Nếu caching labels, key gồm target và viewer?
- [ ] Có chính sách cập nhật cache khi JDK/CLDR thay đổi?
- [ ] Unit tests kiểm tra hợp đồng API, tránh hardcode mọi localized text?
- [ ] Có kiểm thử format/translation của product bằng resources nếu yêu cầu wording cố định?
- [ ] Đã dùng API Java 17+ hiện hành, không dựa vào API lỗi thời?

## 21. Câu hỏi tự kiểm tra

**1.** `Locale.getLanguage()` trả gì? — Mã ngôn ngữ, ví dụ de.

**2.** `Locale.getDisplayLanguage(Locale.ENGLISH)` trả gì? — Tên language bằng tiếng Anh nếu dữ liệu có, ví dụ German.

**3.** `getCountry()` khác `getDisplayCountry(ui)` thế nào? — Region code khác localized region name.

**4.** `toLanguageTag()` dùng để làm gì? — Biểu diễn Locale theo BCP 47 để lưu/trao đổi.

**5.** `getDisplayName(Locale)` dùng để làm gì? — Tạo tên locale phù hợp người dùng bằng locale hiển thị đã chọn.

**6.** Trong `target.getDisplayName(viewer)`, đâu là subject? — `target`.

**7.** Trong cùng biểu thức, `viewer` có thay target locale không? — Không; nó chỉ chọn ngôn ngữ/cách dịch label.

**8.** Vì sao label không nên làm database key? — Có thể đổi theo viewer/JDK và trùng.

**9.** `getDisplayScript` cần dữ liệu gì? — Script subtag, ví dụ Hant.

**10.** Locale không có script thì `getDisplayScript` ra sao? — Chuỗi rỗng.

**11.** Locale không có variant thì `getDisplayVariant` ra sao? — Chuỗi rỗng.

**12.** `getDisplayName` có thể gồm những phần nào? — Language, script, region, variant và optional Unicode extensions.

**13.** Có thể parse getDisplayName ngược thành tag không? — Không an toàn.

**14.** `Locale.forLanguageTag("zh-Hant-TW")` có language gì? — zh.

**15.** Script của tag trên? — Hant.

**16.** Region của tag trên? — TW.

**17.** `getUnicodeLocaleType("nu")` của `en-US-u-nu-thai` là gì? — thai.

**18.** BCP 47 ngăn subtags bằng dấu gì? — Dấu gạch ngang.

**19.** `Locale.Builder` có vai trò gì? — Tạo Locale, kiểm tra syntax các thành phần.

**20.** Builder có bảo đảm CLDR dịch đủ mọi subtag? — Không.

**21.** Default nào dùng cho `getDisplayName()` không tham số? — `Locale.Category.DISPLAY`.

**22.** FORMAT locale khác DISPLAY thế nào? — Cho định dạng giá trị so với hiển thị tên.

**23.** Có nên gọi `Locale.setDefault` mỗi HTTP request không? — Không; ảnh hưởng toàn JVM.

**24.** Locale.ROOT có language tag gì? — und.

**25.** Locale.ROOT.getDisplayName có thể trả rỗng không? — Có khi không có thành phần hiển thị.

**26.** Khi getDisplayName trả rỗng nên làm gì? — Dùng fallback theo product policy, ví dụ tag hoặc ẩn option.

**27.** Một JDK có thể thiếu bản dịch cho một region không? — Có; API fallback.

**28.** Bản dịch từ CLDR có thể đổi khi nâng JDK? — Có.

**29.** Sort labels theo ngôn ngữ user dùng gì? — `Collator.getInstance(userUiLocale)`.

**30.** `String.compareTo` có sắp đúng chữ Việt như Collator không? — Không bảo đảm.

**31.** `Currency.getDisplayName(ui)` khác `getCurrencyCode()` ra sao? — Tên hiển thị khác mã ISO.

**32.** `ZoneId.getDisplayName(TextStyle.FULL,ui)` trả gì? — Text hiển thị cho zone; không phải ID bảo đảm.

**33.** Khi lưu timezone dùng gì? — `ZoneId.getId()`.

**34.** Locale có tự xác định timezone không? — Không.

**35.** `String.length()` có đo số grapheme chính xác không? — Không; UTF-16 code units.

**36.** Có nên so tên hiển thị để phân biệt hai locales không? — Không; dùng tags.

**37.** Cache key của display labels cần gì? — Cả target locale và viewer locale, thêm version/policy nếu cần.

**38.** Nếu user gửi Accept-Language chứa danh sách ưu tiên, có chuyển nguyên chuỗi vào forLanguageTag được không? — Không; phải parse/negotiation.

**39.** Vì sao không nên hardcode mọi display string trong cross-JDK unit test? — Locale data có thể đổi.

**40.** Quy tắc nhớ lâu nhất? — **Lưu BCP 47 tag, hiển thị bằng getDisplay*(viewerLocale), không đảo vai hai lớp dữ liệu.**

## 22. Tài liệu chính thức Java SE 17

- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `getDisplayLanguage/Country/Script/Variant/Name`, `getLanguage/GetCountry/getScript/getVariant`, `forLanguageTag`, `toLanguageTag`, `Category.DISPLAY`, Unicode extensions.
- [Locale.Builder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): tạo locale và validate syntax BCP 47 components.
- [Currency — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): `getDisplayName(Locale)`, `getCurrencyCode()` và `getSymbol(Locale)`.
- [ZoneId — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): `getDisplayName(TextStyle,Locale)` và `getId()`.
- [Collator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): sắp xếp localized text.
- [Locale.LanguageRange — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html): parser ngôn ngữ ưu tiên cho negotiation.
- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization khi xử lý user-authored strings.
- [DayOfWeek — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html): `getDisplayName(TextStyle,Locale)` cho ngày trong tuần.
- [JDK Locale Service Provider](https://docs.oracle.com/en/java/javase/17/intl/locale.html): kiến thức nền về locale data và provider.

**Ghi nhớ:** Hãy tách **mã locale** khỏi **tên hiển thị cho người dùng**. Lưu/trao đổi bằng `toLanguageTag()` và các mã thành phần, hiển thị bằng `getDisplayName(userUiLocale)` hoặc các phương thức `getDisplayLanguage/Country/Script/Variant(userUiLocale)`. Không dùng overload mặc định trong dịch vụ đa người dùng mà bỏ qua `Locale.Category.DISPLAY`. Nếu thiếu translation có thể fallback về tiếng Anh/mã; nếu không có thành phần có thể trả rỗng. Đối với dropdown, giữ stable tag value, label localized và sort bằng `Collator` theo UI locale. Tên được dịch không phải khóa cơ sở dữ liệu, không phải dữ liệu chuẩn để reverse parse, và có thể thay đổi theo bản JDK/CLDR.