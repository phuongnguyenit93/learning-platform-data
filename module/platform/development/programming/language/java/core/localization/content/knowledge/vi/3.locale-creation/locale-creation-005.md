# Đọc language, country, script, variant và extension của `Locale` trong Java

## 1. Mục tiêu của bài học

Một `java.util.Locale` không chỉ chứa “ngôn ngữ” và “quốc gia”. Nó có thể gồm **language** (ngôn ngữ), **country/region** (vùng), **script** (hệ chữ viết), **variant** (biến thể) và **extension** (thông tin mở rộng, ví dụ loại lịch hoặc hệ số). Đọc đúng những trường này giúp chương trình chọn tài nguyên ngôn ngữ, biểu diễn locale trong log, hiển thị tên thân thiện và tôn trọng tùy chọn của người dùng.

Sau bài này, bạn cần biết:

- Phân biệt `getLanguage()`, `getCountry()`, `getScript()` và `getVariant()`.
- Đọc các extension qua `getExtensionKeys()` và `getExtension(char)`.
- Đọc riêng các thành phần của Unicode locale extension `u` bằng `getUnicodeLocaleAttributes()`, `getUnicodeLocaleKeys()` và `getUnicodeLocaleType(String)`.
- Phân biệt giá trị **chuỗi rỗng**, **`null`** và **tập rỗng** khi trường không được khai báo.
- Hiểu biểu diễn BCP 47 và cách tạo, kiểm tra, lưu trữ một `Locale` trong Java 17+.

Đây là bài về **đọc cấu trúc `Locale`**. Không coi các trường này là bằng chứng địa chỉ, quốc tịch, múi giờ hay mã tiền tệ thực của một giao dịch.

## 2. Giải phẫu một BCP 47 language tag

Java hỗ trợ tạo `Locale` từ language tag BCP 47, ví dụ:

```text
en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
│  │    │  │     │ │           │       │
│  │    │  │     │ │           │       └── extension x, private use = demo
│  │    │  │     │ │           └────────── Unicode keyword nu = thai
│  │    │  │     │ └────────────────────── Unicode keyword ca = japanese
│  │    │  │     └──────────────────────── extension u
│  │    │  └────────────────────────────── variant = posix
│  │    └───────────────────────────────── country/region = US
│  └────────────────────────────────────── script = Latn
└───────────────────────────────────────── language = en
```

| Phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Language | `en`, `vi`, `zh` | Chọn ngôn ngữ; mã thường viết thường. |
| Script | `Latn`, `Cyrl`, `Hans`, `Hant` | Xác định hệ chữ; mã ISO 15924, thường viết hoa chữ đầu. |
| Country/region | `US`, `VN`, `419` | Xác định vùng; hai chữ cái hoặc ba chữ số theo BCP 47. |
| Variant | `posix` | Biến thể riêng theo quy ước của tag. |
| Extension | `u-...`, `x-...` | Tùy chọn bổ sung và phần private-use. |

Không phải tag nào cũng chứa đủ năm thành phần. `"vi"` là một tag hợp lệ không khai báo vùng, script hay extension; `"vi-VN"` khai báo vùng nhưng vẫn không khai báo script. **Thiếu trường nghĩa là không được chỉ định**, không có nghĩa hệ chữ hoặc vùng của người dùng “không tồn tại”.

Phân tích thủ công bằng `tag.split("-")` rất dễ sai: script và country là các phần tùy chọn, variant có thể nhiều subtag, extension `u` lại gồm nhiều keyword. Java đã cung cấp getter để đọc cấu trúc này an toàn hơn.

## 3. Bốn getter cơ bản

| API | Kết quả ví dụ với `en-Latn-US-posix` | Kiểu | Khi không có |
| --- | --- | --- | --- |
| `locale.getLanguage()` | `"en"` | `String` | `""` |
| `locale.getCountry()` | `"US"` | `String` | `""` |
| `locale.getScript()` | `"Latn"` | `String` | `""` |
| `locale.getVariant()` | `"posix"` | `String` | `""` |

Java trả **mã định danh** chứ không phải tên tự nhiên: `getLanguage()` là `"vi"`, còn `getDisplayLanguage(Locale.ENGLISH)` có thể dùng để lấy tên ngôn ngữ tiếng Anh cho giao diện. Tương tự, `getCountry()` trả mã vùng `"VN"`, khác `getDisplayCountry(...)`.

### 3.1. Language — `getLanguage()`

`getLanguage()` đọc mã ngôn ngữ, thường là mã ISO 639 theo quy tắc BCP 47. Các tag `en`, `en-US` và `en-Latn-US` đều có language là `en`.

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale english = Locale.forLanguageTag("en-US");
System.out.println(vietnamese.getLanguage()); // vi
System.out.println(english.getLanguage());    // en
```

*Đây là đoạn Java minh họa đặt bên trong phương thức, chưa phải chương trình độc lập.*

`getLanguage()` chỉ mô tả language; nó không bảo đảm ứng dụng có bản dịch cho ngôn ngữ đó. `Locale.ROOT.getLanguage()` là `""`.

### 3.2. Country / Region — `getCountry()`

`getCountry()` đọc mã vùng. Nó thường là mã hai chữ cái như `US`, `VN` nhưng theo BCP 47 cũng có thể là mã vùng ba chữ số như `419`.

```java
Locale a = Locale.forLanguageTag("en-US");
Locale b = Locale.forLanguageTag("es-419");
System.out.println(a.getCountry()); // US
System.out.println(b.getCountry()); // 419
```

Tag `vi-US` có `getLanguage()` là `"vi"` và `getCountry()` là `"US"`; kết hợp này chỉ nói về ngữ cảnh locale. **Không tự tính múi giờ bằng country** (một nước có thể có nhiều múi giờ), và không thay đổi đơn vị tiền tệ thật của dữ liệu dựa vào country. Với định dạng tiền và thời gian, hãy quản lý `Currency` và `ZoneId` theo yêu cầu riêng.

### 3.3. Script — `getScript()`

Script là mã hệ chữ viết ISO 15924, ví dụ `Latn` (Latin), `Cyrl` (Cyrillic), `Hans` (Chinese simplified), `Hant` (Chinese traditional). Cùng language có thể có nhiều script.

| Tag | Language | Script | Country |
| --- | --- | --- | --- |
| `sr-Latn-RS` | `sr` | `Latn` | `RS` |
| `sr-Cyrl-RS` | `sr` | `Cyrl` | `RS` |
| `zh-Hans-CN` | `zh` | `Hans` | `CN` |
| `zh-Hant-TW` | `zh` | `Hant` | `TW` |
| `vi-VN` | `vi` | `""` | `VN` |

Chỉ dựa trên `getLanguage()` có thể chọn sai bản chữ viết (ví dụ hệ Latin so với Cyrillic ở `sr`). Tuy nhiên, `getScript()` trả `""` khi tag không chỉ định script; đừng suy diễn ngược rằng câu chữ người dùng không có hệ chữ.

### 3.4. Variant — `getVariant()`

Variant mô tả một biến thể hoặc quy ước cụ thể, ví dụ `posix` trong `en-US-posix`:

```java
Locale locale = Locale.forLanguageTag("en-US-posix");
System.out.println(locale.getVariant()); // posix
```

Trong BCP 47, variant subtag thường có 5–8 ký tự chữ/số hoặc đúng bốn ký tự bắt đầu bằng số; có thể có nhiều variant. Một số `Locale` tạo bằng constructor Java cũ chứa variant legacy với dấu gạch dưới. Vì thế, đừng tự tách hoặc tự nối variant khi trao đổi language tag. Dùng `toLanguageTag()` để xuất định danh theo cú pháp BCP 47 và `Locale.Builder` khi cần kiểm tra từng thành phần.

Script mô tả *hệ chữ*, variant mô tả *biến thể*; không thể thay thế nhau. Trong ứng dụng thông thường, variant có thể vắng mặt.

## 4. Extension — đọc theo key

Ngoài bốn thành phần cơ sở, `Locale` có thể chứa extension. Mỗi extension bắt đầu bằng một singleton key (chữ hoặc số), rồi đến các subtag. Java cung cấp:

- `getExtensionKeys()` — trả `Set<Character>` gồm các key hiện có, ví dụ `['u', 'x']` nếu viết dưới dạng danh sách cho dễ hiểu.
- `getExtension('u')` — trả toàn bộ phần nội dung extension `u` (không gồm tiền tố `u-`).
- `getExtension('x')` — trả phần private-use sau `x-`.
- `getExtension(key)` — trả `null` nếu key vắng mặt.

**Không giả định thứ tự lặp `Set` là cố định**. Dùng `TreeSet` nếu cần in các key theo thứ tự để kiểm thử hoặc đối chiếu kết quả.

### 4.1. Unicode locale extension `u`

Tag `en-US-u-ca-japanese-nu-thai` chứa hai Unicode locale keyword:

- `ca=japanese`: loại lịch Nhật.
- `nu=thai`: hệ chữ số Thái.

Với một `Locale` tạo từ tag này:

```java
Locale locale =
        Locale.forLanguageTag("en-US-u-ca-japanese-nu-thai");

String rawExtension = locale.getExtension('u');
// "ca-japanese-nu-thai"

String calendar = locale.getUnicodeLocaleType("ca");
// "japanese"

String numbering = locale.getUnicodeLocaleType("nu");
// "thai"
```

Các getter chuyên cho `u`:

| Getter | Tác dụng | Ví dụ |
| --- | --- | --- |
| `getUnicodeLocaleKeys()` | Các keyword key trong extension `u` | `ca`, `nu` |
| `getUnicodeLocaleType("ca")` | Type của keyword `ca` | `japanese` |
| `getUnicodeLocaleType("nu")` | Type của keyword `nu` | `thai` |
| `getUnicodeLocaleAttributes()` | Các Unicode attribute trong extension `u` | `attr` trong `en-u-attr-ca-gregory` |

**Attribute khác keyword:** với `en-u-attr-ca-gregory`, `attr` là attribute (không có type), còn `ca` là keyword với type `gregory`. Vì vậy, `getUnicodeLocaleAttributes()` chứa `"attr"` và `getUnicodeLocaleType("ca")` trả `"gregory"`.

Extension thể hiện tùy chọn hoặc ngữ cảnh, không bảo đảm mọi Java formatter tự động áp dụng toàn bộ tùy chọn. Ví dụ `ca=japanese` không tự buộc mọi `DateTimeFormatter` chuyển sang niên lịch Nhật; cần kiểm tra loại chronology được API sử dụng và cấu hình rõ ràng khi cần. Tương tự, phải kiểm tra hỗ trợ dữ liệu locale thực tế trước khi kỳ vọng chữ số theo `nu`.

### 4.2. Private-use extension `x`

`en-US-x-demo` có `getExtension('x')` là `"demo"`. `x` dành cho thỏa thuận riêng, không có ý nghĩa chung được mọi ứng dụng Java hiểu giống nhau. Không diễn giải `x-demo` thành quốc gia, script, thông tin cá nhân hay tính năng có sẵn nếu hệ thống không định nghĩa quy ước riêng.

### 4.3. Extension vắng mặt

Với `Locale.forLanguageTag("vi-VN")`:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
System.out.println(locale.getExtensionKeys().isEmpty()); // true
System.out.println(locale.getExtension('u') == null);    // true
System.out.println(locale.getUnicodeLocaleKeys().isEmpty()); // true
```

Điểm cần nhớ: thiếu language/country/script/variant thì getter trả `""`; thiếu một extension/type thì getter trả `null`; thiếu các key/attribute thì getter trả **tập rỗng**. Không gọi `getExtension('u').isEmpty()` khi chưa xử lý khả năng `null`.

## 5. Ví dụ Java 17+ chạy độc lập, đọc đầy đủ các phần

Tạo tệp **`LocalePartsDemo.java`** với nội dung dưới đây. Để kết quả có thể đối chiếu chính xác, ví dụ dùng `TreeSet` khi in các tập key và attribute.

```java
import java.util.Locale;
import java.util.TreeSet;

public class LocalePartsDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag(
                "en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo");

        System.out.println("tag=" + locale.toLanguageTag());
        System.out.println("language=" + locale.getLanguage());
        System.out.println("country=" + locale.getCountry());
        System.out.println("script=" + locale.getScript());
        System.out.println("variant=" + locale.getVariant());

        System.out.println("extensionKeys="
                + new TreeSet<>(locale.getExtensionKeys()));
        System.out.println("extension_u=" + locale.getExtension('u'));
        System.out.println("extension_x=" + locale.getExtension('x'));
        System.out.println("unicodeKeys="
                + new TreeSet<>(locale.getUnicodeLocaleKeys()));
        System.out.println("calendar="
                + locale.getUnicodeLocaleType("ca"));
        System.out.println("numbering="
                + locale.getUnicodeLocaleType("nu"));

        Locale attributes = Locale.forLanguageTag(
                "en-u-attr-ca-gregory");
        System.out.println("attributes="
                + new TreeSet<>(attributes.getUnicodeLocaleAttributes()));

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        System.out.println("missingScriptIsEmpty="
                + vietnamese.getScript().isEmpty());
        System.out.println("missingExtensionIsNull="
                + (vietnamese.getExtension('u') == null));
    }
}
```

Dùng JDK 17 hoặc mới hơn, chạy trong cùng thư mục chứa tệp:

```bash
javac -encoding UTF-8 LocalePartsDemo.java
java LocalePartsDemo
```

**Đầu ra chính xác:**

```text
tag=en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
language=en
country=US
script=Latn
variant=posix
extensionKeys=[u, x]
extension_u=ca-japanese-nu-thai
extension_x=demo
unicodeKeys=[ca, nu]
calendar=japanese
numbering=thai
attributes=[attr]
missingScriptIsEmpty=true
missingExtensionIsNull=true
```

### Giải thích đầu ra

1. `getLanguage()` chỉ trả `en`, không trả nguyên language tag; `getScript()` trả `Latn`, `getCountry()` trả `US`.
2. `getVariant()` là `posix`; thông tin extension không lẫn vào variant.
3. `getExtensionKeys()` trả các singleton `u` và `x`; nó không trực tiếp trả Unicode keyword `ca` hoặc `nu`.
4. `getExtension('u')` trả `ca-japanese-nu-thai`, không chứa tiền tố `u-`; `getExtension('x')` trả `demo`, không có `x-`.
5. `getUnicodeLocaleKeys()` trả `ca` và `nu`; mỗi giá trị cụ thể được lấy bằng `getUnicodeLocaleType(...)`.
6. `getUnicodeLocaleAttributes()` cho `en-u-attr-ca-gregory` trả attribute `attr`, không trả keyword `ca`.
7. Locale `vi-VN` không chứa script hoặc extension, nên điều kiện `isEmpty()` với script và so sánh `== null` với extension đều là `true`.

Ví dụ này chỉ đọc và in thông tin cấu trúc. Nó không gọi `Locale.setDefault(...)`, do đó không thay đổi locale mặc định chung của JVM.

## 6. Tạo Locale đúng cách để các getter có ý nghĩa

### `Locale.forLanguageTag(...)`

Đây là API thuận tiện để đọc định danh được lưu hoặc truyền qua biên hệ thống:

```java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");
System.out.println(locale.getLanguage()); // zh
System.out.println(locale.getScript());   // Hant
System.out.println(locale.getCountry());  // TW
```

`forLanguageTag` có thể xử lý đầu vào sai theo cách linh hoạt, ví dụ dừng tại subtag không hợp lệ thay vì luôn báo lỗi. Vì vậy **tạo được đối tượng không đồng nghĩa đầu vào đúng hoặc locale được ứng dụng hỗ trợ**. Tại request boundary, cần xác thực cú pháp và kiểm tra danh sách locale sản phẩm hỗ trợ nếu điều đó là yêu cầu của hệ thống.

### `Locale.Builder`

Khi có sẵn từng thành phần, dùng Builder để gắn chúng tường minh và kiểm tra cú pháp chặt hơn:

```java
Locale custom = new Locale.Builder()
        .setLanguage("en")
        .setScript("Latn")
        .setRegion("US")
        .setVariant("posix")
        .setUnicodeLocaleKeyword("ca", "japanese")
        .setUnicodeLocaleKeyword("nu", "thai")
        .setExtension('x', "demo")
        .build();

System.out.println(custom.toLanguageTag());
// en-Latn-US-posix-u-ca-japanese-nu-thai-x-demo
```

Các đoạn trong mục này là mã minh họa nằm trong phương thức Java. `Locale.Builder` có thể ném `IllformedLocaleException` nếu giá trị không hợp lệ theo cú pháp, nhưng nó không kiểm tra ứng dụng có bản dịch cho locale hay không.

Khi trao đổi giữa các hệ thống, dùng `toLanguageTag()` thay vì `toString()`. `Locale.toString()` có biểu diễn legacy của Java và không phải mã BCP 47 chuẩn để truyền qua API. Khi cần tên dễ đọc cho người dùng, các phương thức `getDisplayLanguage(...)`, `getDisplayScript(...)`, `getDisplayCountry(...)` hoặc `getDisplayName(...)` dùng một locale hiển thị khác để mô tả thành phần, thay vì dùng các getter mã kỹ thuật như nhãn UI.

## 7. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao không đúng | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng `split("-")` rồi lấy vị trí cố định | Script, region và variant đều tùy chọn; extension gồm nhiều subtag. | Dùng các getter của `Locale`. |
| Coi `getCountry()` là tên quốc gia | Nó trả mã vùng, ví dụ `VN`, `US` hoặc `419`. | Dùng `getDisplayCountry(displayLocale)` để hiển thị. |
| Chỉ so sánh language cho mọi bản dịch | Script có thể phân biệt Latin, Cyrillic, giản thể, phồn thể. | Cân nhắc language + script + region khi chọn locale hỗ trợ. |
| Cho rằng country luôn hai chữ cái | BCP 47 cho phép mã vùng số ba chữ số. | Không tự áp regex hai chữ cái cho mọi trường hợp. |
| Coi không có script là lỗi | Nhiều language tag hợp lệ không khai báo script. | Kiểm tra `getScript().isEmpty()`. |
| Gọi `getExtension('u').isEmpty()` | Khi không có extension, getter trả `null`. | Kiểm tra `null` trước. |
| Nhầm Unicode key với extension key | `u` là extension key; `ca` và `nu` là keyword bên trong nó. | Dùng `getUnicodeLocaleKeys()` và `getUnicodeLocaleType(...)`. |
| Tin `ca=japanese` tự đổi mọi định dạng ngày | Formatter/chronology có thể có quy tắc riêng. | Kiểm tra API định dạng được dùng. |
| Tin locale lấy từ input đồng nghĩa có bản dịch | `Locale` chỉ mô tả định danh, không mang tài nguyên của sản phẩm. | Kiểm tra locale hỗ trợ và fallback của ứng dụng. |
| Đổi `Locale.setDefault(...)` theo request | Default locale là trạng thái chung của JVM, dễ ảnh hưởng người dùng đồng thời. | Truyền `Locale` tường minh theo request. |

## 8. Tự luyện để xác nhận đã nắm kiến thức

**Bài 1.** Với `vi-VN`, `sr-Latn-RS` và `zh-Hant-TW`, viết hàm in `getLanguage()`, `getCountry()`, `getScript()` và `getVariant()`. Chỉ ra trường nào trả `""`. Vì sao `sr-Latn-RS` và `sr-Cyrl-RS` không nên bị coi như nhau nếu sản phẩm có bản dịch theo script?

**Bài 2.** Phân tích `en-u-attr-ca-gregory-nu-latn` bằng `getExtension('u')`, `getUnicodeLocaleAttributes()`, `getUnicodeLocaleKeys()` và `getUnicodeLocaleType(...)`. Kết quả cần chỉ ra attribute `attr`, keyword `ca=gregory` và `nu=latn`. In các `Set` bằng `TreeSet` để thứ tự có thể dự đoán.

**Bài 3.** Tạo cùng locale bằng `Locale.Builder` và `Locale.forLanguageTag(...)`. Kiểm tra `toLanguageTag()` và `equals(...)`. Thử một subtag sai cú pháp, quan sát parser mềm dẻo khác Builder kiểm tra chặt chẽ thế nào.

**Bài 4.** Viết phương thức nhận `Locale` và trả ra dữ liệu gồm language, region, script, variant và các Unicode keyword, nhưng phải xử lý đúng trường trống/null và **không tạo giá trị mặc định giả**. Khi cần serial hóa toàn bộ locale, dùng `toLanguageTag()`.

**Tiêu chí hoàn thành:** giải thích được ý nghĩa từng getter và kiểu kết quả khi thiếu dữ liệu; đọc được extension `u` với attribute/keyword, phần `x`; biết cách tạo locale từ language tag hoặc Builder; và không nhầm mã ngôn ngữ với tên hiển thị, múi giờ hay lựa chọn bản dịch thực tế của ứng dụng.