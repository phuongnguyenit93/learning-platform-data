# Tạo `Locale` từ nhãn ngôn ngữ hoặc `Locale.Builder` (Java 10+)

## 1. Bài toán: biểu diễn ngôn ngữ và quy ước vùng miền đúng cách

Trong Java, `java.util.Locale` biểu diễn **một bộ nhận diện ngôn ngữ/vùng miền**, có thể bao gồm ngôn ngữ, hệ chữ viết (script), vùng (region), biến thể (variant) và các extension dùng cho quy ước địa phương. Nó thường được dùng để chọn quy tắc định dạng số, ngày tháng, tiền tệ, tài nguyên dịch và sắp xếp chuỗi theo locale.

Ví dụ:

- `vi-VN`: tiếng Việt tại Việt Nam.
- `en-US`: tiếng Anh tại Hoa Kỳ.
- `en-GB`: tiếng Anh tại Vương quốc Anh.
- `zh-Hant-TW`: tiếng Trung với script phồn thể (`Hant`) và vùng Đài Loan (`TW`).
- `es-419`: tiếng Tây Ban Nha tại khu vực có mã số `419`.
- `en-US-u-ca-buddhist-nu-thai`: nhãn có Unicode locale extension yêu cầu kiểu lịch và cách biểu diễn chữ số.

Nếu một hệ thống lưu cấu hình locale trong dạng nhãn như `vi-VN`, cách tạo đối tượng trực tiếp là:

```java
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
System.out.println(locale.toLanguageTag()); // vi-VN
```

Đây là các lệnh minh họa **trong một phương thức**. `Locale.forLanguageTag(String)` đọc nhãn ngôn ngữ theo chuẩn **IETF BCP 47**; `Locale.Builder` cho phép xây dựng từ nhiều phần hoặc kiểm tra chặt chẽ cú pháp.

**Lưu ý lịch sử phiên bản:** các API `Locale.forLanguageTag` và `Locale.Builder` có từ Java 7, vẫn hoạt động ở Java 10 và các JDK hiện hành. Bài này trình bày **cách dùng còn phù hợp trong Java hiện đại**, không khẳng định Java 10 là phiên bản đầu tiên giới thiệu chúng. Constructor `new Locale(...)` đã được đánh dấu deprecated từ Java 19; code mới nên ưu tiên `forLanguageTag`, `Builder` hoặc `Locale.of(...)` khi chạy trên JDK hỗ trợ.

## 2. Hiểu cấu trúc nhãn BCP 47

BCP 47 là cách viết một nhãn ngôn ngữ thành chuỗi dùng dấu gạch ngang `-`. Một mẫu dễ hình dung:

```text
language [- Script] [- REGION] [- variant] [- extension ...]

vi-VN
en-US
zh-Hant-TW
es-419
en-US-u-ca-buddhist-nu-thai
```

Các thành phần không phải lúc nào cũng xuất hiện đủ và cú pháp BCP 47 chi tiết hơn mẫu đơn giản trên.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Ngôn ngữ (`language`) | `vi`, `en`, `zh` | Mã ngôn ngữ |
| Script | `Latn`, `Hans`, `Hant` | Hệ chữ viết được sử dụng |
| Region | `VN`, `US`, `GB`, `419` | Quốc gia hoặc khu vực |
| Variant | `posix` | Biến thể cụ thể, phải theo quy tắc subtag BCP 47 |
| Extension `u` | `u-ca-buddhist`, `u-nu-thai` | Quy ước Unicode locale như lịch và hệ chữ số |
| Private use `x` | `x-team` | Phần mở rộng riêng; không tự hứa hỗ trợ định dạng |

Quy ước cách viết phổ biến là **language chữ thường**, **script chữ đầu viết hoa**, **region chữ hoa**, **extension chữ thường**. Các so sánh nhãn BCP 47 về cơ bản không phân biệt hoa/thường; `Locale` chuẩn hóa một số phần theo quy ước này.

Cách viết đúng là **`vi-VN`**, không phải `vi_VN`. Dấu gạch dưới `_` thường xuất hiện trong cách hiển thị `Locale.toString()`, nhưng **không phải ký tự phân cách chuẩn cho BCP 47 language tag**.

Quan trọng: một nhãn **đúng cú pháp** chưa chắc là nhãn được đăng ký trong IANA Language Subtag Registry hoặc được tất cả provider/JDK hỗ trợ đầy đủ. `Locale.Builder` chủ yếu xác minh **cú pháp**, không xác minh mọi locale thực sự có sẵn tài nguyên dịch, số liệu CLDR hoặc định dạng mong muốn.

## 3. Cách 1: `Locale.forLanguageTag(String)`

`Locale.forLanguageTag` tạo một `Locale` từ chuỗi BCP 47:

```java
Locale vi = Locale.forLanguageTag("vi-vn");
Locale us = Locale.forLanguageTag("en-US");
Locale traditional = Locale.forLanguageTag("zh-Hant-TW");

System.out.println(vi.toLanguageTag()); // vi-VN
System.out.println(vi.getLanguage());   // vi
System.out.println(vi.getCountry());    // VN
System.out.println(traditional.getScript()); // Hant
```

Các dòng này cần `import java.util.Locale;` và đặt trong một phương thức. Java phân biệt phương thức **`getCountry()`** (trả region/country) với `getLanguage()` và `getScript()`.

Những đặc điểm cần biết:

1. Nhận một chuỗi language tag theo BCP 47.
2. Chuẩn hóa hoa/thường cho language, script, region và extension theo quy tắc của `Locale`.
3. Trả `Locale`; không cần tự tách từng đoạn với `String.split("-")`.
4. **Khá khoan dung với nhãn lỗi:** nếu có subtag sai cú pháp, nó **bỏ subtag sai đầu tiên và mọi subtag theo sau**.
5. Không mặc định báo lỗi chỉ vì mã ngôn ngữ/vùng thiếu dữ liệu định dạng tương ứng trên JDK.

Đặc tính ở mục 4 dễ bị bỏ sót. Ví dụ:

```java
Locale result = Locale.forLanguageTag("en-US-bad!");
System.out.println(result.toLanguageTag()); // en-US
```

Subtag `bad!` sai cú pháp. `forLanguageTag` **không ném** `IllformedLocaleException` cho trường hợp đó, mà cắt phần sai và giữ `en-US`. Nếu dữ liệu là cấu hình có tính quyết định hoặc do người dùng nhập, việc bỏ qua phần đuôi có thể **che giấu lỗi đầu vào**.

Đối với nhãn `en_US` chứa gạch dưới:

```java
Locale invalid = Locale.forLanguageTag("en_US");
System.out.println(invalid.toLanguageTag()); // und
```

`und` là subtag “Undetermined” trong BCP 47, không có nghĩa Java đã hiểu đúng `en_US`. **Đừng dùng `forLanguageTag` như một bộ validator nghiêm ngặt** rồi cho rằng mọi chuỗi trả về `Locale` đều là input hợp lệ.

## 4. Cách 2: `Locale.Builder` tạo locale từ các trường

Khi các phần của locale được thu thập riêng, `Locale.Builder` giúp mô tả rõ ý định:

```java
Locale locale = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();

System.out.println(locale.toLanguageTag()); // zh-Hant-TW
```

Các phương thức chính:

| Phương thức | Vai trò | Ví dụ |
| --- | --- | --- |
| `setLanguage(String)` | Đặt mã ngôn ngữ | `"vi"` |
| `setScript(String)` | Đặt hệ chữ viết | `"Hant"` |
| `setRegion(String)` | Đặt region | `"TW"` hoặc `"419"` |
| `setVariant(String)` | Đặt biến thể theo cú pháp BCP 47 | `"posix"` |
| `setLanguageTag(String)` | Đọc một tag và **thay toàn bộ trạng thái** builder | `"en-US"` |
| `setLocale(Locale)` | Sao chép thông tin từ một Locale khác vào builder | `Locale.US` |
| `setUnicodeLocaleKeyword(key, type)` | Thêm/sửa một Unicode locale keyword | `"nu", "latn"` |
| `setExtension(key, value)` | Thiết lập extension tổng quát | `'x', "team"` |
| `clearExtensions()` | Xóa extension, giữ language/script/region/variant | Không có tham số |
| `clear()` | Xóa toàn bộ trạng thái builder | Không có tham số |
| `build()` | Tạo một `Locale` từ trạng thái hiện tại | Không có tham số |

Ví dụ xây locale từ các trường do ứng dụng quản lý:

```java
String language = "es";
String region = "419";

Locale latinAmerica = new Locale.Builder()
        .setLanguage(language)
        .setRegion(region)
        .build();

System.out.println(latinAmerica.toLanguageTag()); // es-419
```

Mẫu này đặc biệt hữu ích khi frontend cho chọn riêng ngôn ngữ, vùng và hệ chữ viết, hoặc khi backend cần **điều chỉnh một trường** mà vẫn giữ các thông tin còn lại.

**Không tự nối chuỗi khi các thành phần đến từ nguồn khác nhau** rồi bỏ qua kiểm tra cú pháp. Builder đã cung cấp ràng buộc theo cấu trúc BCP 47 và trả về loại ngoại lệ phù hợp khi trường không hợp lệ.

## 5. Khác biệt quan trọng nhất: xử lý tag không hợp lệ

`Locale.forLanguageTag(String)` và `new Locale.Builder().setLanguageTag(String)` có mục đích khác nhau khi input **sai cú pháp**.

```java
var lenient = Locale.forLanguageTag("en-US-bad!");
System.out.println(lenient.toLanguageTag()); // en-US

// Lời gọi dưới đây ném IllformedLocaleException:
new Locale.Builder()
        .setLanguageTag("en-US-bad!")
        .build();
```

Tài liệu Java chính thức mô tả rõ:

- **`forLanguageTag`:** gặp subtag sai cú pháp → bỏ subtag sai đầu tiên **và mọi subtag theo sau**; không phải cơ chế báo lỗi nghiêm ngặt.
- **`Builder.setLanguageTag`:** gặp tag sai cú pháp → ném **`IllformedLocaleException`**.
- **Builder setter từng trường:** cũng kiểm tra trường có tuân thủ cú pháp thích hợp hay không; ném `IllformedLocaleException` nếu sai.
- **Nhưng** Builder không xác minh mọi subtag đã được đăng ký trong kho IANA hoặc tài nguyên locale thực sự tồn tại trên JDK.

Bảng quyết định:

| Nguồn dữ liệu | Ưu tiên | Vì sao |
| --- | --- | --- |
| Tag tin cậy, mục tiêu đọc nhanh | `Locale.forLanguageTag(tag)` | Trực tiếp và ngắn |
| Tag từ file cấu hình cần báo lỗi nhập sai | `new Locale.Builder().setLanguageTag(tag).build()` | Không âm thầm cắt đuôi lỗi |
| Language/script/region do ứng dụng tách riêng | Builder setter từng trường | Kiểm tra cấu trúc và rõ nghĩa |
| Danh sách locale được phép theo nghiệp vụ | Builder + **allowlist** hoặc validation riêng | Đúng cú pháp không đồng nghĩa được phép |
| Cấu hình chạy trên JDK 19+ với language/region đã đáng tin cậy | `Locale.of(...)` | Factory hiện hành, nhưng **không kiểm tra cú pháp chặt như Builder** |

**Mã validation gợi ý:**

```java
static Locale parseStrict(String tag) {
    Objects.requireNonNull(tag, "localeTag");
    if (tag.isBlank()) {
        throw new IllegalArgumentException("localeTag must not be blank");
    }
    return new Locale.Builder().setLanguageTag(tag).build();
}
```

Đây là phương thức minh họa trong một lớp; cần import `java.util.Locale`, `java.util.Objects`. Quy tắc từ chối blank là **chính sách ứng dụng**, không phải behavior tự động của `Builder`: Javadoc cho biết `Builder.setLanguageTag("")` hoặc `null` **reset builder** giống `clear()`. Nếu muốn field bắt buộc có tag, phải **tự cấm blank/null** trước.

Ngoài cú pháp, ứng dụng còn có thể yêu cầu “chỉ hỗ trợ `vi-VN` và `en-US`”; lúc đó cần kiểm tra các locale được cho phép theo mục đích cụ thể. Builder không thay công đoạn kiểm tra nghiệp vụ này.

## 6. Tag BCP 47 và `toLanguageTag()`: đúng định dạng để trao đổi

Đã có một `Locale`, muốn xuất lại nhãn BCP 47 hãy dùng `toLanguageTag()`:

```java
Locale locale = Locale.forLanguageTag("zh-hant-tw");

String tag = locale.toLanguageTag(); // zh-Hant-TW
```

`Locale.toString()` và `Locale.toLanguageTag()` **không thay thế nhau**:

```java
Locale vi = Locale.forLanguageTag("vi-VN");

String protocolTag = vi.toLanguageTag(); // vi-VN
String debugText = vi.toString();        // vi_VN
```

- `toLanguageTag()` là biểu diễn theo IETF BCP 47, dùng thích hợp khi lưu/trao đổi language tag.
- `toString()` là biểu diễn lịch sử của Java, có thể chứa `_` và ký tự cấu trúc khác; chủ yếu phù hợp để debug.
- `getLanguage()`, `getScript()`, `getCountry()` và `getVariant()` cho phép đọc thành phần nếu thật sự cần.

Một số tag có alias/legacy conversion hoặc các phần không biểu diễn chính xác theo model của `Locale`, nên không nên giả định chuỗi `toLanguageTag()` **luôn giống tuyệt đối input ban đầu** hoặc round-trip ký tự 100% trong mọi trường hợp. Khi cần lưu **đúng chuỗi gốc** do người dùng nhập phục vụ audit, lưu riêng chuỗi đó và nhãn canonicalized nếu phù hợp.

Không tự dùng `locale.toString().replace('_','-')` để tạo tag: cách này có thể sai khi có script, extension, variant hoặc dữ liệu đặc biệt. Dùng đúng API `toLanguageTag()`.

## 7. Unicode locale extensions: lịch, cách biểu diễn chữ số và các quy ước

BCP 47 có extension `u` cho những thuộc tính Unicode locale. Ví dụ:

```text
en-US-u-ca-buddhist-nu-thai
  |  |  |  |        |
  |  |  |  |        +-- numbering system: thai
  |  |  |  +----------- calendar: buddhist
  +--+--+-------------- locale base: en-US
```

Có thể đọc tag này trực tiếp:

```java
Locale settings = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai");

System.out.println(settings.toLanguageTag());
// en-US-u-ca-buddhist-nu-thai

System.out.println(settings.getUnicodeLocaleType("ca"));
// buddhist

System.out.println(settings.getUnicodeLocaleType("nu"));
// thai
```

Đoạn trên là mã minh họa trong một phương thức.

Khi muốn xây extension từ các phần:

```java
Locale numbered = new Locale.Builder()
        .setLanguage("en")
        .setRegion("GB")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(numbered.toLanguageTag());
// en-GB-u-nu-latn
```

**Cách hiểu đúng:**

- `ca` là keyword về calendar, ví dụ `buddhist`, `gregory`.
- `nu` là keyword về numbering system, ví dụ `latn`, `thai`.
- Builder chuyển các keyword thành extension `u` trong tag.
- `getUnicodeLocaleType(key)` đọc lại type đã được lưu trong locale; nếu key không có thì có thể trả `null`.
- Không phải mọi formatter, provider hoặc phiên bản JDK **đều bắt buộc hỗ trợ mọi giá trị extension**, kể cả khi tag hợp lệ. API sử dụng locale có thể áp dụng quy tắc fallback hoặc chỉ dùng phần thông tin nó hỗ trợ.

**Đừng suy luận rằng thay `nu` trong tag sẽ luôn bắt buộc mọi thư viện in đúng hệ chữ số đó.** `Locale` biểu diễn *yêu cầu/ưu tiên về quy ước*, còn khả năng thực thi thuộc về thư viện và dữ liệu locale của môi trường.

## 8. Builder có trạng thái, nhưng `Locale` được xây là bất biến

`Locale.Builder` là đối tượng cấu hình mutable: mỗi setter có thể đổi state và trả chính builder để nối phương thức. Mỗi lần gọi `build()` tạo ra một `Locale` đại diện cho cấu hình ở thời điểm đó.

```java
var builder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US");

Locale us = builder.build();

builder.setRegion("GB");
Locale gb = builder.build();

System.out.println(us.toLanguageTag()); // en-US
System.out.println(gb.toLanguageTag()); // en-GB
```

Việc chỉnh `builder` **không sửa** `us` đã được tạo. Đây là một mô hình tốt cho cấu hình cục bộ trong một luồng xử lý.

Tuy nhiên, cũng có những thao tác **thay toàn bộ state**:

```java
var builder = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN");

builder.setLanguageTag("en-US"); // thay toàn bộ trạng thái cũ
Locale result = builder.build();
// result.toLanguageTag() == "en-US"
```

`setLanguageTag` không phải một phép “nối thêm hậu tố” vào locale cũ; nó **reset builder rồi điền từ tag mới**. `setLocale(Locale)` cũng thay state theo đối tượng truyền vào.

Nếu chỉ muốn bỏ extension nhưng giữ language/region:

```java
Locale withNumbering = new Locale.Builder()
        .setLanguageTag("en-GB-u-nu-latn")
        .build();

Locale withoutNumbering = new Locale.Builder()
        .setLocale(withNumbering)
        .clearExtensions()
        .build();

// withoutNumbering.toLanguageTag() == "en-GB"
```

`clearExtensions()` bỏ phần mở rộng; `clear()` bỏ **toàn bộ** các trường builder. Đừng dùng `clear()` khi ý định chỉ bỏ quy ước Unicode.

## 9. Script khác region: không suy luận một trường từ trường còn lại

Một locale có thể cần thêm trường script để phân biệt cách viết, ví dụ:

```java
Locale traditional = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();

Locale simplified = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hans")
        .setRegion("CN")
        .build();
```

- `zh` nhận diện ngôn ngữ.
- `Hant` và `Hans` mô tả script.
- `TW` và `CN` mô tả region.
- Không phải mọi ngôn ngữ đều cần khai báo script; nhiều locale quen thuộc chỉ cần language và region.

Ứng dụng không nên tự kết luận mọi người ở cùng region dùng chung một ngôn ngữ/script, hoặc mọi người dùng ngôn ngữ giống nhau thì luôn có format ngày/tiền tệ giống hệt. Locale là **tham số cấu hình được chọn**, không phải phép suy đoán chính xác sở thích của từng cá nhân.

Nếu backend cần biết ngôn ngữ và vùng **được người dùng chọn**, ưu tiên lưu/nhận đúng tag (hoặc các trường tách biệt) thay vì đoán từ IP, múi giờ hay mã quốc gia riêng lẻ.

## 10. `Locale.of` trên JDK mới: dùng khi phù hợp, nhưng không nhầm với Builder

Từ Java **19**, có factory `Locale.of(...)` tạo locale từ language, country và variant:

```java
// Chỉ dùng khi biên dịch/chạy trên JDK 19+:
Locale vi = Locale.of("vi", "VN");
```

Đây là đoạn minh họa dành riêng cho JDK 19+, **không** đưa vào chương trình Java 17 chạy mẫu ở phần sau.

Vì các constructor `new Locale("vi", "VN")` được deprecated từ Java 19, với mã mới nên cân nhắc:

- **Java 17+ và đầu vào là tag:** `Locale.forLanguageTag("vi-VN")`.
- **Java 17+ và cần kiểm tra chặt trường/tag:** `new Locale.Builder()...build()`.
- **JDK 19+ và các trường đã được kiểm soát:** `Locale.of("vi","VN")`.

**Lưu ý:** `Locale.of` **không thực hiện đầy đủ kiểm tra well-formed BCP 47** như `Locale.Builder`. Do đó nếu dữ liệu đến từ người dùng/cấu hình cần báo lỗi sai cú pháp, Builder thường phù hợp hơn, kể cả trên JDK mới.

Không sửa mã Java 17 thành `Locale.of(...)` nếu dự án còn phải biên dịch trên JDK 17.

## 11. Locale đúng cú pháp không bảo đảm có nội dung dịch hoặc dữ liệu định dạng

`Locale` chỉ mô tả một lựa chọn ngôn ngữ/quy ước. Tạo `Locale.forLanguageTag("vi-VN")` **không làm ứng dụng tự dịch** chuỗi tiếng Anh thành tiếng Việt.

Những lớp có thể sử dụng locale:

```java
Locale vietnam = Locale.forLanguageTag("vi-VN");

NumberFormat numberFormat =
        NumberFormat.getNumberInstance(vietnam);

DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(vietnam);
```

Các dòng trên cần import `java.util.Locale`, `java.text.NumberFormat`, `java.time.format.DateTimeFormatter` và `java.time.format.FormatStyle`; đây là đoạn minh họa trong một phương thức.

Lưu ý:

- `NumberFormat` chọn dấu phân cách, quy tắc số… theo dữ liệu locale mà implementation hỗ trợ.
- `DateTimeFormatter` chọn cách biểu diễn ngày theo formatter/locale đã cấu hình; cần cung cấp một ngày cụ thể khi format.
- `ResourceBundle` có thể chọn các tài nguyên do **chính ứng dụng cung cấp** và áp dụng quy tắc fallback; tạo Locale không tự sinh bản dịch.
- Kết quả dạng text của formatter có thể khác theo dữ liệu locale provider/JDK. **Đừng hardcode một output tiếng Việt cụ thể trong test** nếu test không kiểm soát phiên bản dữ liệu CLDR hoặc quy tắc formatting.

Nếu nhãn có subtag hợp lệ nhưng chưa được môi trường hỗ trợ, ứng dụng có thể cần chọn một locale fallback được xác định rõ (ví dụ `en-US` hoặc `vi-VN`) theo yêu cầu sản phẩm.

## 12. `Locale.getDefault()` và ảnh hưởng của môi trường

Java có **default locale** tùy môi trường/runtime:

```java
Locale current = Locale.getDefault();
System.out.println(current.toLanguageTag());
```

Output của đoạn trên **không cố định**; nó có thể khác giữa máy phát triển, CI và production. Đây không phải ví dụ thích hợp để viết expected stdout chính xác.

Khi code phải cho kết quả theo một locale nhất định, truyền locale **tường minh** vào formatter/parser:

```java
Locale locale = Locale.forLanguageTag("en-US");
NumberFormat parser = NumberFormat.getNumberInstance(locale);
```

Không nên gọi `Locale.setDefault(...)` trong một unit test chỉ để làm một phép format ổn định: việc thay default locale của JVM có thể ảnh hưởng tới các test hoặc thread khác. Thay vào đó truyền locale trực tiếp cho API được kiểm tra.

Với ứng dụng web, default locale của server **không phải tự động là sở thích ngôn ngữ của từng request**. Đọc lựa chọn của người dùng hoặc header theo một quy trình phù hợp rồi truyền locale riêng cho thao tác tương ứng.

## 13. Header `Accept-Language` không phải một language tag đơn lẻ

Một header HTTP như:

```text
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7
```

**Không được** truyền nguyên cả giá trị `"vi-VN,vi;q=0.9,en-US;q=0.7"` vào `Locale.forLanguageTag(...)` và kỳ vọng Java hiểu toàn bộ các mức ưu tiên. Đây là một **danh sách language range có q-value**, không phải một nhãn BCP 47 đơn.

Java có API hiện hành `Locale.LanguageRange.parse(...)` và cơ chế `Locale.lookup(...)` / `Locale.filter(...)` theo RFC 4647 để phối hợp với danh sách locale mà ứng dụng hỗ trợ.

Ví dụ minh họa:

```java
var preferred = Locale.LanguageRange.parse(
        "vi-VN,vi;q=0.9,en-US;q=0.7");

var supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"));

Locale chosen = Locale.lookup(preferred, supported);
```

Đoạn trên cần import `java.util.Locale` và `java.util.List`.

**Không nhầm:**

- `Locale.forLanguageTag`: đọc **một tag**.
- `Locale.LanguageRange.parse`: đọc **danh sách ưu tiên language ranges**.
- `Locale.lookup/filter`: tìm lựa chọn phù hợp trong tập locale **được ứng dụng hỗ trợ**.

Lựa chọn locale phù hợp có thể còn chịu quy tắc fallback riêng của sản phẩm. Nếu không tìm được locale phù hợp, `Locale.lookup` có thể trả `null`; ứng dụng nên định nghĩa fallback và kiểm tra kết quả.

## 14. Hợp đồng ở ranh giới dữ liệu: lưu tag hay lưu các trường?

Cách thiết kế dữ liệu phụ thuộc cách ứng dụng nhận locale.

### Trường hợp A: cấu hình sẵn một BCP 47 tag

```java
String configuredTag = "vi-VN";
Locale locale = new Locale.Builder()
        .setLanguageTag(configuredTag)
        .build();
```

Nếu config cần fail-fast khi sai cú pháp, Builder giúp phát hiện đầu vào lỗi. Sau đó có thể kiểm tra locale đó có nằm trong **danh sách hỗ trợ** của ứng dụng hay không.

### Trường hợp B: frontend cho chọn ngôn ngữ và vùng riêng

```java
String language = "vi";
String region = "VN";

Locale locale = new Locale.Builder()
        .setLanguage(language)
        .setRegion(region)
        .build();
```

Đầu vào có cấu trúc nên dùng setter cho từng trường; nếu region sai cú pháp thì Builder báo lỗi thay vì tạo một Locale bất thường.

### Trường hợp C: cần giữ preference đặc biệt

```java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("ca", "buddhist")
        .setUnicodeLocaleKeyword("nu", "thai")
        .build();
```

Để lưu/trao đổi các extension, dùng `locale.toLanguageTag()`. Tránh chỉ lưu `locale.getLanguage()` và `locale.getCountry()` rồi làm mất script hoặc Unicode extensions quan trọng.

**Lời khuyên:** khi persistence/protocol cho phép, lưu một chuỗi BCP 47 chuẩn hóa bằng `toLanguageTag()` sẽ giúp giữ nhiều thông tin hơn so với chỉ ghi riêng hai trường language và region.

## 15. Lỗi và ngoại lệ nên kiểm tra

| Đầu vào / thao tác | Hành vi | Cách xử lý |
| --- | --- | --- |
| `Locale.forLanguageTag("en-US-bad!")` | Bỏ phần lỗi, còn `en-US` | Nếu cần strict, dùng Builder |
| `new Locale.Builder().setLanguageTag("en-US-bad!")` | `IllformedLocaleException` | Trả lỗi validation có ngữ cảnh |
| `Locale.forLanguageTag("en_US")` | Không diễn giải đúng dạng BCP 47; trong ví dụ `toLanguageTag()` là `und` | Chấp nhận `en-US`, không dùng gạch dưới |
| `new Locale.Builder().setLanguageTag(null)` | Reset builder | Nếu field bắt buộc, tự kiểm tra null trước |
| `new Locale.Builder().setLanguageTag("")` | Reset builder | Tự cấm blank nếu domain yêu cầu |
| `new Locale.Builder().setRegion("USA")` | `IllformedLocaleException` vì region không theo đúng cú pháp | Dùng `US` hoặc mã numeric-3 hợp lệ |
| `Locale.of("en","US")` trên JDK 17 | Không có API này để biên dịch | Dùng `forLanguageTag` hoặc Builder |
| `Locale.getDefault()` trong test cần output ổn định | Phụ thuộc môi trường | Truyền Locale cố định |
| `Locale.toString()` gửi qua protocol đòi BCP 47 | Có thể xuất `vi_VN`, không đúng kiểu tag | Dùng `toLanguageTag()` |
| `new Locale.Builder().setLanguage("xx").setRegion("YY")` | Có thể qua kiểm tra cú pháp dù không phải locale nghiệp vụ cho phép | Cần allowlist/registry validation riêng |

**Không dùng các constructor `new Locale(...)` đã deprecated cho mã mới** khi có factory/Builder tương ứng. Dùng class và phương thức còn hiệu lực giúp code đáp ứng Special Note mà vẫn chạy được trên Java 17+.

## 16. Chương trình Java 17+ hoàn chỉnh: chuẩn hóa, Builder và strict validation

Tạo tệp `LocaleBuilderDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleBuilderDemo {

    static void expectIllformed(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=none");
        } catch (IllformedLocaleException e) {
            System.out.println(
                    label + "=" + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        var vi = Locale.forLanguageTag("vi-vn");
        System.out.println("vi=" + vi.toLanguageTag());
        System.out.println("parts="
                + vi.getLanguage() + "," + vi.getCountry());

        var chinese = new Locale.Builder()
                .setLanguage("zh")
                .setScript("Hant")
                .setRegion("TW")
                .build();
        System.out.println("chinese=" + chinese.toLanguageTag());
        System.out.println("script=" + chinese.getScript());

        var latinAmerica = new Locale.Builder()
                .setLanguage("es")
                .setRegion("419")
                .build();
        System.out.println("region419=" + latinAmerica.toLanguageTag());

        var augmented = new Locale.Builder()
                .setLanguageTag("en-US")
                .setRegion("GB")
                .setUnicodeLocaleKeyword("nu", "latn")
                .build();
        System.out.println("augmented=" + augmented.toLanguageTag());
        System.out.println("numbering="
                + augmented.getUnicodeLocaleType("nu"));

        var ext = Locale.forLanguageTag(
                "en-US-u-ca-buddhist-nu-thai");
        System.out.println("extension=" + ext.toLanguageTag());
        System.out.println("calendar="
                + ext.getUnicodeLocaleType("ca"));
        System.out.println("numbering2="
                + ext.getUnicodeLocaleType("nu"));

        var truncated = Locale.forLanguageTag("en-US-bad!");
        System.out.println("lenient=" + truncated.toLanguageTag());

        expectIllformed("strict",
                () -> new Locale.Builder()
                        .setLanguageTag("en-US-bad!")
                        .build());

        var clean = new Locale.Builder()
                .setLocale(augmented)
                .clearExtensions()
                .build();
        System.out.println("clean=" + clean.toLanguageTag());

        System.out.println("same="
                + vi.equals(Locale.forLanguageTag("vi-VN")));

        System.out.println("underscore="
                + Locale.forLanguageTag("en_US").toLanguageTag());
    }
}
```

Biên dịch và chạy:

```bash
javac LocaleBuilderDemo.java
java LocaleBuilderDemo
```

Output đã kiểm chứng:

```text
vi=vi-VN
parts=vi,VN
chinese=zh-Hant-TW
script=Hant
region419=es-419
augmented=en-GB-u-nu-latn
numbering=latn
extension=en-US-u-ca-buddhist-nu-thai
calendar=buddhist
numbering2=thai
lenient=en-US
strict=IllformedLocaleException
clean=en-GB
same=true
underscore=und
```

**Giải thích stdout:**

1. `vi=vi-VN`: tag `vi-vn` được chuẩn hóa cách viết; `getLanguage/getCountry` cho `vi,VN`.
2. `chinese` và `script`: Builder giữ ngôn ngữ `zh`, script `Hant`, region `TW`.
3. `region419=es-419`: region có thể là mã số ba chữ số theo cú pháp hợp lệ, không chỉ mã quốc gia hai chữ cái.
4. `augmented` và `numbering`: setLanguageTag rồi đổi region, thêm Unicode keyword `nu=latn`.
5. `extension`, `calendar`, `numbering2`: đọc tag có hai Unicode locale keywords.
6. `lenient=en-US`: `forLanguageTag` bỏ phần không hợp lệ.
7. `strict=IllformedLocaleException`: Builder xử lý cùng input theo chế độ strict cú pháp.
8. `clean=en-GB`: `clearExtensions` bỏ numbering extension nhưng giữ language và region.
9. `same=true`: hai biểu diễn của `vi-VN` cho locale tương đương; dùng `equals` thay vì so sánh `==`.
10. `underscore=und`: `en_US` không được coi là `en-US` theo BCP 47.

Ví dụ chỉ dùng các API có sẵn trong Java 17, **không cần `Locale.of` của Java 19**. Mọi dòng output cố ý dùng mã ASCII để tránh sai khác do console locale, terminal encoding và dữ liệu định dạng địa phương.

## 17. Các trường hợp cần test thêm

**A. Tag hợp lệ có chữ hoa/chữ thường khác nhau**

```java
Locale a = Locale.forLanguageTag("EN-us");
Locale b = Locale.forLanguageTag("en-US");

if (!a.equals(b)) {
    throw new AssertionError("Locale normalization failed");
}
```

**B. Builder phát hiện region sai cú pháp**

```java
// Trong một bài test JUnit:
// assertThrows(IllformedLocaleException.class,
//         () -> new Locale.Builder().setRegion("USA"));
```

**C. Đầu vào là tag bị cắt âm thầm**

```java
String userInput = "en-US-bad!";
Locale lenient = Locale.forLanguageTag(userInput);
// lenient.toLanguageTag() == "en-US"
```

Đây là phép kiểm tra chứng minh tại sao **không chỉ dùng `forLanguageTag` để validate dữ liệu người dùng**.

**D. Cú pháp hợp lệ không đảm bảo tài nguyên**

```java
Locale hypothetical = new Locale.Builder()
        .setLanguageTag("xx-YY")
        .build();
```

Builder chỉ xác minh cấu trúc cú pháp. Việc `xx-YY` có phải lựa chọn được sản phẩm hỗ trợ không là việc riêng của **allowlist**/tài nguyên. Không dùng kết quả `build()` để kết luận “mọi bản dịch và formatter cho locale này đều tồn tại”.

**E. Extension và bảo toàn thông tin**

```java
Locale original = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai");

String persistedTag = original.toLanguageTag();
// Tránh chỉ lưu original.getLanguage() khi extension quan trọng.
```

Không nên bỏ script, variant và extension chỉ vì cách lưu trữ hiện tại mới có language/country.

## 18. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `Locale.forLanguageTag` để validate strict một config từ người dùng | Phần tag sai có thể bị cắt và lỗi bị che | Dùng `new Locale.Builder().setLanguageTag(tag).build()` |
| Dùng `en_US` như BCP 47 tag | Không được hiểu là `en-US` | Dùng `en-US` |
| Dùng `locale.toString()` để ghi language tag cho REST/DB | Có thể dùng `_` và cú pháp nội bộ | Dùng `locale.toLanguageTag()` |
| Gọi `setLanguageTag` sau khi set nhiều trường và tưởng nó bổ sung | Nó reset state builder | Set tag trước, rồi mới ghi đè trường muốn thay |
| Gọi `clear()` khi chỉ muốn xóa Unicode keyword | Mất language/script/region luôn | Dùng `clearExtensions()` hoặc xóa keyword thích hợp |
| Nghĩ `Locale.Builder` kiểm tra IANA registration và supported locales | Nó chủ yếu kiểm tra syntax | Kiểm tra registry/allowlist/business support riêng |
| Nghĩ tag có `nu-thai` thì mọi formatter phải in chữ số Thai | Phụ thuộc khả năng hỗ trợ của provider/API | Test API thực tế và có fallback |
| Chọn `Locale.getDefault()` rồi hardcode output của test | Phụ thuộc máy và dữ liệu locale JDK | Truyền Locale cụ thể, hạn chế assert string localized |
| Dùng `Locale.of` nhưng dự án cần biên dịch JDK 17 | API chỉ từ JDK 19 | Dùng Builder/forLanguageTag cho Java 17 |
| Dùng các constructor `Locale` deprecated trong mã mới | Không theo API tạo Locale hiện hành | Dùng `forLanguageTag`/Builder/`Locale.of` |
| Nghĩ Locale là text translator | Không có tài nguyên dịch tự động | Cung cấp resource translations/fallback |
| Truyền cả `Accept-Language` có q-values vào `forLanguageTag` | Đầu vào không phải một BCP 47 tag | Parse `Locale.LanguageRange` và match supported locales |

## 19. Bài tập tự kiểm tra

### Câu 1: đọc một tag

```java
var locale = Locale.forLanguageTag("zh-hant-tw");
```

Giá trị `locale.toLanguageTag()`, `getLanguage()`, `getScript()`, `getCountry()`?

**Đáp án:** `zh-Hant-TW`, `zh`, `Hant`, `TW`. Java chuẩn hóa case theo vị trí subtag.

### Câu 2: xử lý lỗi cú pháp

```java
var a = Locale.forLanguageTag("en-US-bad!");
var b = new Locale.Builder()
        .setLanguageTag("en-US-bad!");
```

Điều gì xảy ra?

**Đáp án:** `a.toLanguageTag()` là `en-US` vì `forLanguageTag` bỏ subtag sai và phần theo sau. Câu lệnh tạo builder `b` **ném `IllformedLocaleException`** ngay ở `setLanguageTag`, trước khi gán cho `b`.

### Câu 3: Builder và ghi đè region

```java
var result = new Locale.Builder()
        .setLanguageTag("en-US")
        .setRegion("GB")
        .build();
```

`result.toLanguageTag()` là gì?

**Đáp án:** `en-GB`. Đầu tiên builder nạp tag `en-US`; setter tiếp theo thay region thành `GB`.

### Câu 4: Extension

```java
var locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("GB")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();
```

`locale.getUnicodeLocaleType("nu")` và `toLanguageTag()`?

**Đáp án:** `latn` và `en-GB-u-nu-latn`. Không vì vậy mà mọi thư viện formatter chắc chắn dùng cùng cơ chế xử lý số; cần xem hợp đồng của formatter.

### Câu 5: Cách nào hợp lệ trên Java 17?

Trong ba cách `Locale.forLanguageTag("vi-VN")`, `new Locale.Builder().setLanguage("vi").setRegion("VN").build()`, `Locale.of("vi","VN")`, cách nào dùng được khi biên dịch với JDK 17?

**Đáp án:** Hai cách đầu. `Locale.of` chỉ có từ Java 19; dùng nó trong source cần compile Java 17 là lỗi tương thích.

### Câu 6: Tag đúng cú pháp nhưng ứng dụng không hỗ trợ

Nếu `new Locale.Builder().setLanguageTag("xx-YY").build()` thành công, có được suy ra rằng ứng dụng đã có tất cả các bản dịch và định dạng cho `xx-YY`?

**Đáp án:** Không. Builder kiểm tra cú pháp; phải xác định supported locale list, dữ liệu tài nguyên và chính sách fallback của ứng dụng.

## 20. Checklist áp dụng khi tạo `Locale`

1. Xác định đầu vào là **một BCP 47 language tag**, hay các trường language/script/region riêng biệt.
2. Với tag tin cậy, dùng `Locale.forLanguageTag`; với input cần fail-fast khi sai cú pháp, dùng `Locale.Builder.setLanguageTag`.
3. Với các trường riêng, dùng `setLanguage`, `setScript`, `setRegion` thay vì nối chuỗi tùy tiện.
4. Không dùng `_` trong tag; ưu tiên `vi-VN`, `en-US`, `zh-Hant-TW`.
5. Khi lưu/trao đổi, dùng `toLanguageTag`, không dùng `toString`.
6. Nếu có Unicode locale extension, bảo toàn bằng tag và thao tác `setUnicodeLocaleKeyword` khi phù hợp.
7. Nhớ rằng `setLanguageTag` **reset** Builder; `clearExtensions` khác `clear`.
8. Tách **validation cú pháp** khỏi **validation các locale mà sản phẩm hỗ trợ**.
9. Không giả định `Locale` tự mang bản dịch/định dạng đầy đủ; xử lý fallback khi thư viện/tài nguyên thiếu.
10. Tránh output phụ thuộc `Locale.getDefault()` trong test; truyền Locale cố định.
11. Không đưa nguyên header `Accept-Language` vào `forLanguageTag`; parse ranges và chọn từ tập hỗ trợ.
12. Với code Java 17, không dùng `Locale.of` (từ Java 19); tránh constructor `new Locale(...)` đã deprecated trên JDK hiện đại.

## Kết luận

Để tạo `Locale` hiện đại từ nhãn ngôn ngữ, `Locale.forLanguageTag("vi-VN")` là cách ngắn gọn khi input đã được tin cậy. Khi cần **xác thực cú pháp nghiêm ngặt**, **xây dựng từ language/script/region** hoặc **thêm Unicode extension**, `Locale.Builder` cung cấp các setter có kiểm tra và `build()` trả về Locale bất biến.

Hãy ghi nhớ khác biệt quan trọng nhất: **`forLanguageTag` có thể cắt bỏ subtag sai; `Builder.setLanguageTag` ném `IllformedLocaleException`**. Dùng `toLanguageTag()` để trao đổi BCP 47, không dựa vào `toString()`; đồng thời phân biệt một nhãn đúng cú pháp với locale thực sự được ứng dụng/JDK hỗ trợ. Các API này vẫn phù hợp cho Java 10 và Java 17+ hiện nay.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): mô hình language/script/region/extension, `forLanguageTag`, `toLanguageTag`, `Locale.of` và khuyến nghị tránh constructor deprecated.
- [Java SE 26 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html): các setter, `setLanguageTag` strict, `setUnicodeLocaleKeyword`, `clearExtensions` và `build`.
- [Java SE 26 — `IllformedLocaleException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IllformedLocaleException.html): ngoại lệ khi Builder nhận các phần locale không đúng cú pháp.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): cú pháp BCP 47 và các subtag.
- [RFC 4647 — Matching of Language Tags](https://www.rfc-editor.org/rfc/rfc4647): lựa chọn/matching language preferences.
- [Java SE 26 — `Locale.LanguageRange`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.LanguageRange.html): xử lý danh sách language ranges.
- [Unicode CLDR Project](https://cldr.unicode.org/): nguồn dữ liệu địa phương hóa được các nền tảng thư viện sử dụng; kết quả phụ thuộc phiên bản/provider thực tế.
