# Locale.of và các hằng Locale có sẵn trong Java

## 1. Bài toán: tạo đúng Locale để xử lý ngôn ngữ và vùng

Một ứng dụng có thể cần hiển thị nội dung cho người dùng Việt Nam (`vi-VN`), người dùng tiếng Anh ở Hoa Kỳ (`en-US`), tiếng Anh ở Anh (`en-GB`) hoặc tiếng Pháp ở Canada (`fr-CA`). Mỗi lựa chọn đại diện cho một **`Locale`**: tập thông tin nhận diện ngôn ngữ và bối cảnh vùng, có thể gồm script (hệ chữ), variant và các extension.

Trong Java, lớp `java.util.Locale` cung cấp các đối tượng dùng bởi `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`, `Collator` và nhiều API khác. Để tạo một `Locale` phổ biến, có thể gọi factory `Locale.of(...)` hoặc dùng các **hằng được định nghĩa sẵn** như `Locale.US`, `Locale.ENGLISH`, `Locale.JAPAN`.

**Điều cốt lõi:** `Locale` là mô tả *ngôn ngữ/vùng*, không phải câu đã được dịch, không phải múi giờ hay đơn vị tiền của giao dịch. `Locale.of("vi", "VN")` không tự động biến chuỗi tiếng Anh thành tiếng Việt; nó tạo đối tượng ngữ cảnh để các thành phần phù hợp biết cách xử lý.

Mục tiêu bài học: hiểu các overload của `Locale.of`, chọn chính xác các hằng phổ biến, phân biệt ngôn ngữ và vùng, đọc lại các thành phần của locale, biết lúc nào dùng thẻ BCP 47/`Locale.Builder` và tránh lỗi phiên bản JDK.

## 2. Tạo Locale với Locale.of(...) — có từ Java 19

Từ **Java 19**, `Locale` cung cấp ba factory method tĩnh:

```java
Locale.of(String language)
Locale.of(String language, String country)
Locale.of(String language, String country, String variant)
```

Ba tham số có ý nghĩa khác nhau:

| Tham số | Giá trị thường gặp | Chức năng |
| --- | --- | --- |
| `language` | `"vi"`, `"en"`, `"fr"`, `"ja"` | Mã ngôn ngữ (thường từ ISO 639), được chuẩn hóa về chữ thường |
| `country` / region | `"VN"`, `"US"`, `"GB"`, `"JP"` | Mã quốc gia/vùng (thường ISO 3166-1 alpha-2 hoặc UN M.49 dạng ba chữ số), được chuẩn hóa về chữ hoa |
| `variant` | `"POSIX"` | Biến thể bổ sung, giữ nguyên chữ hoa/thường; chỉ dùng khi thực sự có yêu cầu |

Ví dụ:

```java
Locale vietnamese = Locale.of("vi");              // Chỉ ngôn ngữ
Locale vietnam = Locale.of("vi", "VN");            // Ngôn ngữ + vùng
Locale americanEnglish = Locale.of("en", "US");
Locale withVariant = Locale.of("en", "US", "POSIX");
```

Các đối tượng này được tạo bằng factory, **không thay đổi** `Locale` mặc định của JVM và không trực tiếp thay đổi format của một ứng dụng. Hãy chuyển `Locale` đến API cần dùng.

`Locale.of` chuẩn hóa hai thành phần language và country: `Locale.of("EN", "us")` biểu diễn cùng locale với `Locale.of("en", "US")`. Factory này **không kiểm tra đầy đủ cú pháp** của mã được cung cấp; truyền ký hiệu tùy tiện vẫn có thể tạo ra đối tượng không có ý nghĩa đối với provider dữ liệu locale. Các tham số `null` gây `NullPointerException`. Vì vậy, phải kiểm tra lựa chọn locale của hệ thống ở tầng ứng dụng.

### Điểm rất dễ nhầm: Locale.of không nhận một thẻ BCP 47 duy nhất

Hai cách viết sau có ý nghĩa khác nhau:

```java
Locale correct = Locale.of("en", "US");
Locale alsoCorrect = Locale.forLanguageTag("en-US");

// SAI MỤC ĐÍCH: toàn bộ "en-US" được xem là một tham số language.
Locale incorrect = Locale.of("en-US");
```

`Locale.of(String)` cần **mã ngôn ngữ riêng**, ví dụ `"en"`, chứ không phân tích chuỗi ghép `"en-US"` thành language + region. Nếu nhận một chuỗi thẻ locale từ cấu hình, HTTP header hoặc hồ sơ người dùng, dùng `Locale.forLanguageTag("en-US")`; nếu cần kiểm tra cú pháp BCP 47 nghiêm ngặt, cân nhắc `Locale.Builder`.

### Khi nào dùng overload thứ ba?

`Locale.of("en", "US", "POSIX")` có thêm variant. Variant là một phần định danh locale; không dùng variant để nhét múi giờ, tên người dùng, mã tiền hoặc bất kỳ nhãn tùy ý nào. Các trường hợp cần script như `zh-Hant-TW` hoặc extension như `th-TH-u-nu-thai` nên dùng `Locale.forLanguageTag` hoặc `Locale.Builder`; `Locale.of` không có đối số dành riêng cho script và extension.

## 3. Các hằng Locale thường dùng

Java đã định nghĩa những đối tượng phổ biến bằng hằng `public static final`. Dùng hằng khi nó có **đúng ý nghĩa** mà chương trình cần: code gọn, tránh nhập sai mã, và rõ mục đích.

### 3.1. Hằng chỉ có ngôn ngữ

| Hằng | Language tag | Ý nghĩa |
| --- | --- | --- |
| `Locale.ENGLISH` | `en` | Tiếng Anh, chưa chỉ định vùng |
| `Locale.FRENCH` | `fr` | Tiếng Pháp, chưa chỉ định vùng |
| `Locale.GERMAN` | `de` | Tiếng Đức, chưa chỉ định vùng |
| `Locale.ITALIAN` | `it` | Tiếng Ý, chưa chỉ định vùng |
| `Locale.JAPANESE` | `ja` | Tiếng Nhật, chưa chỉ định vùng |
| `Locale.KOREAN` | `ko` | Tiếng Hàn, chưa chỉ định vùng |
| `Locale.CHINESE` | `zh` | Tiếng Trung, chưa chỉ định vùng/script |

Ví dụ, `Locale.ENGLISH` tương đương về giá trị với `Locale.of("en")`; nó **không tự động** mang quốc gia Hoa Kỳ. Điều này quan trọng khi chọn tài nguyên dịch theo ngôn ngữ, thay vì áp đặt vùng mặc định.

### 3.2. Hằng có ngôn ngữ và vùng

| Hằng | Language tag | Ý nghĩa |
| --- | --- | --- |
| `Locale.US` | `en-US` | Tiếng Anh ở Hoa Kỳ |
| `Locale.UK` | `en-GB` | Tiếng Anh ở Vương quốc Anh |
| `Locale.CANADA` | `en-CA` | Tiếng Anh ở Canada |
| `Locale.CANADA_FRENCH` | `fr-CA` | Tiếng Pháp ở Canada |
| `Locale.FRANCE` | `fr-FR` | Tiếng Pháp ở Pháp |
| `Locale.GERMANY` | `de-DE` | Tiếng Đức ở Đức |
| `Locale.ITALY` | `it-IT` | Tiếng Ý ở Ý |
| `Locale.JAPAN` | `ja-JP` | Tiếng Nhật ở Nhật Bản |
| `Locale.KOREA` | `ko-KR` | Tiếng Hàn ở Hàn Quốc |
| `Locale.CHINA` | `zh-CN` | Tiếng Trung ở Trung Quốc |
| `Locale.TAIWAN` | `zh-TW` | Tiếng Trung trong ngữ cảnh Đài Loan |

Các hằng liên quan đến tiếng Trung cần hiểu thêm:

- `Locale.PRC` là alias có cùng giá trị với `Locale.CHINA`.
- `Locale.SIMPLIFIED_CHINESE` có cùng giá trị với `Locale.CHINA` (`zh-CN`).
- `Locale.TRADITIONAL_CHINESE` có cùng giá trị với `Locale.TAIWAN` (`zh-TW`).

**Đừng suy luận rằng các hằng trên chứa script `Hans` hay `Hant`.** Tên `SIMPLIFIED_CHINESE` và `TRADITIONAL_CHINESE` là tên hằng lịch sử gắn với vùng; việc muốn *chỉ định script tường minh* cần `Locale.forLanguageTag("zh-Hans-CN")` hoặc `Locale.forLanguageTag("zh-Hant-TW")`. `zh-TW` và `zh-Hant-TW` có thể dẫn đến kết quả hiển thị tương tự trong một số API, nhưng **không phải hai đối tượng `Locale` có cùng thành phần**.

### 3.3. Locale.ROOT là trường hợp đặc biệt

`Locale.ROOT` có language, country và variant rỗng. Nó không biểu diễn tiếng Anh hay quốc gia nào. Đây là locale trung tính, thường hữu ích khi phần xử lý cần quy tắc độc lập với tùy chọn của người dùng, hoặc làm locale gốc trong các hệ thống tài nguyên.

Ví dụ:

```java
Locale root = Locale.ROOT;

System.out.println(root.getLanguage().isEmpty()); // true
System.out.println(root.getCountry().isEmpty());  // true
System.out.println(root.toLanguageTag());         // und
```

`"und"` là thẻ “undetermined language” trong kết quả BCP 47. Không dùng `Locale.ROOT` làm “bản dịch tiếng Anh mặc định” một cách mặc nhiên; bản dịch dự phòng phải được cấu hình riêng.

### 3.4. Không phải mọi locale đều có hằng

API không có hằng `Locale.VIETNAM` hoặc `Locale.VIETNAMESE`. Với tiếng Việt:

```java
Locale vietnam = Locale.of("vi", "VN"); // Java 19+
Locale vietnamFromTag = Locale.forLanguageTag("vi-VN"); // Java 7+
```

Hai đối tượng biểu diễn cùng language/region và so sánh bằng `equals`. Không nên “mượn” `Locale.CHINESE` hay `Locale.ENGLISH` làm fallback chỉ vì chưa thấy hằng phù hợp.

## 4. Ví dụ Java 21: tạo, so sánh và đọc Locale

Tạo tệp **`LocaleFactoryDemo.java`** (một file Java độc lập):

```java
import java.util.Locale;

public class LocaleFactoryDemo {
    public static void main(String[] args) {
        Locale vietnam = Locale.of("vi", "VN");
        Locale us = Locale.of("EN", "us");
        Locale traditional = Locale.forLanguageTag("zh-Hant-TW");

        System.out.println("Vietnam tag: " + vietnam.toLanguageTag());
        System.out.println("US equals constant: " + us.equals(Locale.US));
        System.out.println("ENGLISH tag: " + Locale.ENGLISH.toLanguageTag());
        System.out.println("US tag: " + Locale.US.toLanguageTag());
        System.out.println("ROOT tag: " + Locale.ROOT.toLanguageTag());
        System.out.println("Script/region: "
                + traditional.getScript() + "/" + traditional.getCountry());
        System.out.println("CHINA aliases: "
                + Locale.CHINA.equals(Locale.SIMPLIFIED_CHINESE));
        System.out.println("TAIWAN aliases: "
                + Locale.TAIWAN.equals(Locale.TRADITIONAL_CHINESE));
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac -encoding UTF-8 LocaleFactoryDemo.java
java LocaleFactoryDemo
```

Kết quả:

```text
Vietnam tag: vi-VN
US equals constant: true
ENGLISH tag: en
US tag: en-US
ROOT tag: und
Script/region: Hant/TW
CHINA aliases: true
TAIWAN aliases: true
```

Điểm cần quan sát:

1. `Locale.of("EN", "us")` được chuẩn hóa thành `en-US`, nên `equals(Locale.US)` là `true`.
2. `Locale.ENGLISH` là `en`, khác `Locale.US` là `en-US`: chọn ngôn ngữ chưa đồng nghĩa chọn vùng.
3. `Locale.ROOT.toLanguageTag()` trả về `und`; đây không phải ngôn ngữ cụ thể.
4. Với thẻ `zh-Hant-TW`, `getScript()` trả `"Hant"` và `getCountry()` trả `"TW"`. Factory `Locale.of("zh", "TW")` không tự động chứa `Hant`.
5. Các hằng alias so sánh bằng nhau theo `equals` vì có cùng giá trị locale.

Lưu ý: nếu dùng `Locale.of` trong file này với JDK 17, biên dịch sẽ thất bại vì method chưa tồn tại ở Java 17; lỗi thuộc **mức phiên bản API**, không phải thiếu `import`.

## 5. Chọn cách tạo Locale phù hợp

| Tình huống | API nên dùng | Lý do |
| --- | --- | --- |
| Cần locale đã có hằng, ví dụ tiếng Anh ở Mỹ | `Locale.US` | Rõ nghĩa và ít nhập sai |
| Đã biết mã language và region riêng, trên Java 19+ | `Locale.of("vi", "VN")` | Ngắn, đúng với dữ liệu thành phần |
| Chỉ cần ngôn ngữ, Java 19+ | `Locale.of("fr")` | Giữ region chưa được chỉ định |
| Nhận chuỗi language tag BCP 47 | `Locale.forLanguageTag("en-GB")` | Phân tích thành phần từ một chuỗi thẻ |
| Cần script/extension, hoặc kiểm tra cú pháp chặt hơn | `new Locale.Builder()...build()` | Tạo đầy đủ trường và kiểm tra tính đúng dạng |
| Dự án vẫn biên dịch với Java 17 | `Locale.forLanguageTag("vi-VN")` hoặc `new Locale("vi", "VN")` | `Locale.of` chưa có ở Java 17; constructor cũ về sau bị đánh dấu deprecated |

### Ví dụ dùng Builder để biểu thị script

```java
Locale traditionalChinese = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();

System.out.println(traditionalChinese.toLanguageTag());
// zh-Hant-TW
```

Builder báo lỗi cú pháp không đúng dạng thông qua `IllformedLocaleException`. Nó không thể chứng minh ngôn ngữ/vùng đó có bản dịch trong ứng dụng hoặc được các locale provider hỗ trợ đầy đủ. `Locale.forLanguageTag` có cách xử lý một số thẻ sai dạng theo hướng khoan dung hơn Builder; nếu input cần xác thực nghiêm ngặt, phải định nghĩa chính sách kiểm tra riêng.

### Với Java 17 phải làm gì?

`Locale.forLanguageTag("vi-VN")` tồn tại từ Java 7 và là cách ngắn gọn, không phải sử dụng constructor cũ, khi nguồn đầu vào là thẻ ngôn ngữ. `new Locale("vi", "VN")` vẫn hoạt động trên Java 17; các constructor `Locale(String...)` được đánh dấu **deprecated từ Java 19**. Đừng sao chép `Locale.of` vào thư viện phải chạy/biên dịch với mức `--release 17`.

## 6. Cách đọc thông tin bên trong một Locale

Các phương thức thường gặp:

| Phương thức | Kết quả | Ghi chú |
| --- | --- | --- |
| `getLanguage()` | Ví dụ `"vi"` | Mã language, không phải tên hiển thị |
| `getCountry()` | Ví dụ `"VN"` | Mã region; có thể rỗng |
| `getScript()` | Ví dụ `"Hant"` | Rỗng nếu không đặt script |
| `getVariant()` | Ví dụ `"POSIX"` | Rỗng nếu không có variant |
| `toLanguageTag()` | Ví dụ `"vi-VN"` | Dạng thẻ BCP 47, phù hợp lưu/chuyển thông tin locale giữa hệ thống |
| `toString()` | Ví dụ `"vi_VN"` | Biểu diễn mang tính truyền thống của Java; không phải BCP 47 |
| `getDisplayLanguage(displayLocale)` | Tên ngôn ngữ dành cho người đọc | Phụ thuộc locale hiển thị và dữ liệu JDK |
| `getDisplayCountry(displayLocale)` | Tên vùng dành cho người đọc | Phụ thuộc locale hiển thị và dữ liệu JDK |
| `getDisplayName(displayLocale)` | Tên có thể hiển thị cho người dùng | Không nên hardcode stdout theo mọi JDK/CLDR |

Ví dụ:

```java
Locale selected = Locale.of("vi", "VN");
Locale ui = Locale.US;

System.out.println(selected.getLanguage()); // vi
System.out.println(selected.getCountry());  // VN
System.out.println(selected.toString());    // vi_VN
System.out.println(selected.toLanguageTag()); // vi-VN

// Tên hiển thị theo ngôn ngữ giao diện (ở đây là tiếng Anh):
String label = selected.getDisplayName(ui);
```

Không dùng `toString()` làm language tag gửi qua HTTP hoặc làm giá trị cấu hình BCP 47, vì nó thường dùng dấu gạch dưới (`vi_VN`) thay cho dấu gạch ngang (`vi-VN`). Trong hệ thống sử dụng BCP 47, dùng `toLanguageTag()` để xuất và `forLanguageTag(...)` để nhập.

Chỉ gọi `Locale.getAvailableLocales()` không có nghĩa tất cả các locale trả về đều đã có chuỗi dịch trong ứng dụng. Đây là tập locale các provider hỗ trợ trong runtime, khác với danh sách ngôn ngữ mà **sản phẩm** quyết định hỗ trợ. Hãy quản lý danh sách hỗ trợ riêng (ví dụ `Set<Locale>` hoặc tập các language tag được cho phép).

## 7. Ứng dụng thực tế và các sai lầm cần tránh

Giả sử dịch vụ thông báo có người dùng chọn tiếng Việt, còn một quản trị viên chọn tiếng Anh ở Mỹ. Chương trình chọn `Locale.of("vi","VN")` cho thông báo người thứ nhất và `Locale.US` cho người thứ hai; sau đó đưa locale vào `ResourceBundle`/formatter tương ứng. **Không nên gọi `Locale.setDefault(...)` cho từng request**: mặc định locale là trạng thái chung của JVM và có thể ảnh hưởng các request khác chạy đồng thời.

Những lỗi hay gặp:

- **Nhầm language-only với language + country:** `Locale.ENGLISH` là `en`, không tương đương `Locale.US`. Việc định dạng ngày/số có thể khác tùy locale và provider.
- **Truyền cả `"vi-VN"` vào `Locale.of(String)`:** factory không tự tách thẻ; dùng `Locale.of("vi", "VN")` hoặc `forLanguageTag("vi-VN")`.
- **Gọi `Locale.of` trong code biên dịch cho Java 17:** API có từ Java 19. Chọn API tương thích mức phiên bản thực tế; code demo của bài này chạy trên JDK 21.
- **Dùng `Locale.CHINA` và cho rằng script `Hans` đã được lưu:** hằng có tag `zh-CN`, không phải `zh-Hans-CN`; script cần khai báo tường minh khi là một phần yêu cầu.
- **Coi `Locale.ROOT` là locale của người dùng:** root là locale trung tính, không đại diện cho một ngôn ngữ cụ thể.
- **Tin rằng `Locale.of` kiểm tra tất cả mã đầu vào:** factory chuẩn hóa case nhưng không bảo đảm mọi giá trị có cú pháp, ngữ nghĩa hay tài nguyên hợp lệ.
- **Lấy locale để suy ra múi giờ hoặc tiền tệ giao dịch:** `Locale` không chứa `ZoneId` và không quyết định đơn vị tiền của một đơn hàng. Các giá trị đó cần được chọn riêng theo nghiệp vụ.
- **So sánh hiển thị tên locale như giá trị chuẩn:** `getDisplayName` có thể đổi theo ngôn ngữ UI và phiên bản dữ liệu; so sánh định danh bằng `equals` hoặc language tag đã kiểm soát.
- **Dùng `Locale.getDefault()` ở chỗ cần locale người dùng:** kết quả phụ thuộc tiến trình/máy chủ. Truyền locale tường minh.

## 8. Tự kiểm tra kiến thức

**Câu 1.** `Locale.of("en")` và `Locale.US` có bằng nhau không?

**Đáp án:** Không. Đối tượng thứ nhất chỉ có language `en`, đối tượng thứ hai có language `en` và country `US`. `Locale.ENGLISH` mới tương đương về giá trị với `Locale.of("en")`.

**Câu 2.** Đầu vào cấu hình chứa một chuỗi `"zh-Hant-TW"`. Nên dùng phương thức nào?

**Đáp án:** `Locale.forLanguageTag("zh-Hant-TW")` để phân tích đầy đủ language, script và region. Nếu xây từ những trường riêng và cần kiểm tra cú pháp chặt, dùng `Locale.Builder`.

**Câu 3.** `Locale.of("fr", "CA")` có giống `Locale.CANADA` không?

**Đáp án:** Không. `Locale.CANADA` có tag `en-CA`; `Locale.of("fr", "CA")` có tag `fr-CA` và bằng `Locale.CANADA_FRENCH`.

**Câu 4.** Tại sao ví dụ sử dụng JDK 21?

**Đáp án:** Vì `Locale.of(...)` bắt đầu từ **Java 19**. Dự án Java 17 có thể dùng `Locale.forLanguageTag(...)`; không được dựa vào `Locale.of(...)` khi cần tương thích Java 17.

**Câu 5.** Hai locale `zh-TW` và `zh-Hant-TW` có giống nhau hoàn toàn không?

**Đáp án:** Không. Thẻ thứ hai khai báo script `Hant` tường minh; thẻ thứ nhất không chứa script dù provider có thể suy luận cách xử lý thích hợp cho vùng.

## 9. Ghi nhớ

- `Locale.of(language[, country[, variant]])` là factory có từ **Java 19**, dành cho những thành phần locale tách riêng. Nó không phải parser của một chuỗi language tag.
- Hằng `Locale.ENGLISH`, `Locale.US`, `Locale.FRANCE`, `Locale.JAPAN`… giúp dùng locale thông dụng với ngữ nghĩa rõ. Một hằng chỉ ngôn ngữ **khác** hằng có ngôn ngữ và vùng.
- `Locale.ROOT` là locale trung tính; `Locale.CHINA`/`SIMPLIFIED_CHINESE` và `Locale.TAIWAN`/`TRADITIONAL_CHINESE` là những cặp hằng có cùng giá trị.
- Cần script, extension hoặc đầu vào language tag: dùng `Locale.forLanguageTag`/`Locale.Builder`. Cần chạy Java 17: tránh `Locale.of`.
- Dùng `toLanguageTag()` khi trao đổi thẻ BCP 47, `equals` để so sánh giá trị locale và truyền locale tường minh khi định dạng/dịch theo từng người dùng.

**Tài liệu tham khảo chính thức:** [Java SE 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html); [Java SE 17 — java.util.Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).