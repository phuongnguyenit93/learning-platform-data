# Locale và Unicode trong Java: Thẻ ngôn ngữ BCP 47 trong trao đổi dữ liệu

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng đa ngôn ngữ có thể nhận yêu cầu từ trình duyệt, ứng dụng di động, hệ thống quản lý nội dung và dịch vụ bên ngoài. Các bên cần **thống nhất cách biểu diễn ngôn ngữ của nội dung** thay vì truyền các tên tự đặt như `vietnamese`, `English_UK` hay `中文繁體`. Chuẩn **IETF BCP 47** cung cấp những chuỗi language tag như `vi-VN`, `en-US`, `sr-Latn-RS` và `zh-Hant-TW`.

Bài **“Thẻ ngôn ngữ BCP 47 trong trao đổi dữ liệu”** thuộc chủ đề **“Locale và Unicode”** của Java 7; các API trong bài vẫn được dùng trong **Java 17+**. Người học cần nắm:

1. Cấu tạo language tag, gồm **language / script / region / variant / extension / private-use** và các quy tắc viết.
2. Phân biệt **mã tag dùng để trao đổi dữ liệu** với object `java.util.Locale` và dữ liệu Unicode thực tế.
3. Sử dụng `Locale.forLanguageTag(...)`, `Locale.toLanguageTag()`, `Locale.Builder.setLanguageTag(...)`, `getLanguage()`, `getScript()`, `getCountry()`.
4. Biết khác biệt giữa parser **dễ dãi** và validator **báo lỗi cú pháp**, cũng như giới hạn của IANA registry validation.
5. Hiểu ngữ nghĩa **`Accept-Language`**, **`Content-Language`** và trọng số ưu tiên `q` trong HTTP hiện hành (RFC 9110).
6. Dùng `Locale.LanguageRange.parse(...)`, `Locale.lookupTag(...)`, `Locale.filterTags(...)` để chọn ngôn ngữ thật sự được hệ thống hỗ trợ theo RFC 4647.
7. Thiết kế JSON/API/database có trường language tag nhất quán; tránh nhầm **ngôn ngữ**, **encoding** và **vị trí địa lý**.
8. Kiểm thử code Java 17+ đầy đủ với stdout có thể tái lập, gồm các trường hợp tag sai và fallback.

**Kết luận trước:** dữ liệu trao đổi nên dùng BCP 47 tag dạng string (ví dụ `zh-Hant-TW`); phía Java chuyển sang `Locale` bằng API chuyên dụng, rồi dùng matching theo ngôn ngữ thực sự có sẵn. Đừng xem `Locale.toString()` hoặc tên hiển thị của ngôn ngữ là định dạng trao đổi chuẩn.

## 2. BCP 47 là gì, có phải “một RFC” không?

**BCP 47** là *Best Current Practice 47* của IETF; khái niệm này được mô tả bởi **RFC 5646** (cấu trúc/đăng ký language tags) **cùng RFC 4647** (cách so khớp language tags). Vì vậy:

- **RFC 5646:** Chuỗi tag hợp lệ có cấu trúc gì, subtag nào mang ý nghĩa gì, IANA Language Subtag Registry quản lý những subtag đã đăng ký ra sao.
- **RFC 4647:** Cách biểu diễn **language ranges** và cách *filter/lookup* giữa những ưu tiên của người dùng với các ngôn ngữ ứng dụng có sẵn.
- **RFC 9110:** Cách HTTP hiện đại dùng những tag/ranges trong `Content-Language` và `Accept-Language`; gồm trọng số `q` và quy tắc truyền nhận.

BCP 47 **không phải character encoding**. Nó không bắt buộc chuỗi tiếng Việt phải được mã hóa bằng UTF-8, không biến `zh-Hant` thành một bộ font, và không xác định ngôn ngữ lập trình Java hay JSON.

### 2.1. Một tag mẫu

```text
sr-Latn-RS
│  │    └── region: RS
│  └─────── script: Latn
└────────── language: sr

zh-Hant-TW
│  │    └── region: TW
│  └─────── script: Hant
└────────── language: zh
```

**`sr-Latn-RS`** thể hiện tiếng Serbia dùng chữ Latin và được gắn với vùng RS; **`zh-Hant-TW`** gắn tiếng Trung với chữ Hán phồn thể và vùng TW. Script và region là hai thông tin độc lập: **`zh-Hant` không đồng nghĩa `zh-TW`**, dù chúng có thể liên quan trong sản phẩm cụ thể. Khi phân phối bản dịch, phân biệt script có thể quan trọng hơn region.

### 2.2. Dấu nối phải là `-`, không phải `_`

BCP 47 dùng **dấu gạch nối ASCII `-`** giữa subtags. `en-US` là dạng thông dụng; `en_US` là cách biểu diễn locale kiểu cũ trong nhiều thư viện/hệ thống, **không phải BCP 47 tag có cú pháp hợp lệ**.

Trong Java:
- `locale.toLanguageTag()` dùng dấu `-`.
- `locale.toString()` thường dùng dấu `_` và có thêm biểu diễn đặc thù Java, dùng cho debug, **không gửi lên wire như BCP 47**.
- Không thay mọi dấu gạch dưới bằng dấu nối một cách mù quáng khi chưa kiểm tra protocol cũ, variant và private-use.

## 3. Cấu trúc của một language tag

Một biểu diễn rút gọn của cấu trúc thông dụng là:

```text
language [- script] [- region] [- variant ...]
         [- extension ...] [- private-use ...]

Ví dụ:
en
en-US
sr-Latn-RS
zh-Hant-TW
de-CH-1901
en-US-u-ca-gregory
de-DE-x-company
```

**Đây là sơ đồ học tập**, không thay thế toàn bộ ABNF của RFC 5646; RFC còn có *extlang*, các grandfathered tags, trường hợp chỉ có private-use và các quy tắc thứ tự chi tiết.

| Thành phần | Dạng thông dụng | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| Language | Mã ngôn ngữ ISO 639 (thường 2–3 ký tự chữ cái) | `vi`, `en`, `zh` | Ngôn ngữ chính |
| Extlang | Subtag lịch sử/đặc thù với ràng buộc cú pháp | `zh-cmn` | Một phần của cú pháp BCP 47; không phải lúc nào cũng cần |
| Script | 4 chữ cái ISO 15924 | `Latn`, `Cyrl`, `Hant`, `Hans` | Hệ chữ viết |
| Region | 2 chữ cái hoặc 3 chữ số theo registry | `VN`, `US`, `419` | Vùng địa lý/đăng ký |
| Variant | Thông thường 5–8 ký tự chữ-số hoặc 4 ký tự bắt đầu bằng số | `1901` | Biến thể được chỉ định theo quy tắc |
| Extension | Một singleton rồi các subtags hợp lệ | `u-ca-gregory` | Bổ sung thông tin có cơ chế đăng ký |
| Private use | `x` rồi subtags riêng | `x-company` | Có ý nghĩa theo thỏa thuận giữa hai bên |

Các subtag không nhất thiết xuất hiện đủ. `vi` có thể dùng khi nội dung chỉ phân loại theo tiếng Việt; `vi-VN` dùng khi ứng dụng chủ động phân biệt phiên bản liên quan đến vùng VN.

### 3.1. Language không nhất thiết hai chữ cái

RFC 5646 cho phép những language subtags hợp lệ không chỉ là hai ký tự. Java `Locale` cũng có thể chứa language code ba chữ cái hoặc dài hơn theo cú pháp phù hợp. Không viết validator cứng:

```java
// KHÔNG ĐÚNG làm validator BCP 47 tổng quát:
tag.matches("[a-z]{2}-[A-Z]{2}");
```

Regex này loại bỏ `en`, `zh-Hant`, `sr-Latn-RS`, `es-419`, các extensions và nhiều tag hợp lệ khác.

### 3.2. Script rất quan trọng

`zh-Hans` (chữ Hán giản thể) và `zh-Hant` (chữ Hán phồn thể) là hai tag khác nhau về script; không tự suy script từ region với một mapping tùy tiện. `sr-Latn` và `sr-Cyrl` cũng khác nhau. Việc ứng dụng phân biệt khi nào cần hai bản dịch là quyết định nội dung, không phải việc Java tự dịch văn bản.

### 3.3. Region không chứng minh nơi ở của người dùng

`en-US` là tag xác định variety/vùng liên quan ngôn ngữ, **không phải tín hiệu vị trí GPS**, quốc tịch hoặc thông tin an toàn để phân quyền. Một người ở Việt Nam hoàn toàn có thể chọn nội dung `en-US`. Không dùng tag làm bằng chứng nguồn gốc danh tính.

### 3.4. Variant theo registry

`de-CH-1901` có variant `1901` liên quan tới quy ước chính tả; không được thêm những variant tùy ý chỉ vì trông đúng về số ký tự. Cú pháp hợp lệ chưa chắc subtag đã có ý nghĩa được đăng ký cho ngôn ngữ ấy.

### 3.5. Unicode locale extension `u`

`en-US-u-ca-buddhist-nu-thai` có Unicode locale extension:
- `u`: singleton cho loại extension này.
- `ca-buddhist`: calendar keyword.
- `nu-thai`: numbering-system keyword.

Những extension này có thể hữu ích cho **locale formatting**, nhưng **không đồng nghĩa nguồn văn bản được viết bằng ngôn ngữ khác**. Một văn bản vẫn có thể bằng tiếng Anh dù UI dùng một lịch hoặc hệ chữ số khác.

### 3.6. Private-use `x`

`de-DE-x-internal` là ví dụ có private-use subtag. Bên ngoài giao thức riêng giữa hai hệ thống, subtag `internal` không có ngữ nghĩa chung được chuẩn hóa. Không đưa các giá trị private-use làm giả định mặc định cho public API nếu không có thỏa thuận rõ.

## 4. Viết hoa/thường và canonical form

BCP 47 tag được so sánh **không phân biệt chữ hoa/chữ thường** trong cú pháp thông thường. Nhưng dạng trình bày nhất quán giúp code review và lưu trữ:

- Language thường **chữ thường**: `sr`, `en`, `vi`.
- Script thường **Title Case**: `Latn`, `Hant`, `Cyrl`.
- Region thường **CHỮ HOA**: `RS`, `TW`, `VN`.
- Extensions thường được chuẩn hóa chữ thường.

Ví dụ:

```java
Locale locale = Locale.forLanguageTag("SR-latn-rs");
String canonical = locale.toLanguageTag(); // "sr-Latn-RS"
```

Đây là snippet trong method có import `java.util.Locale`. `Locale` normalize case trong quá trình parse/tag rendering.

**Không nhầm “canonical về cách viết” với “đã được IANA xác nhận mọi subtag”.** `Locale.toLanguageTag()` có thể tạo tag *well-formed* từ dữ liệu đầu vào nhưng không tra cứu đầy đủ IANA registry để bảo đảm mọi mã ngôn ngữ/vùng đã được đăng ký.

### 4.1. Một tag trông hợp lệ vẫn có thể vô nghĩa trong ứng dụng

Ví dụ `xx-YY` có thể đáp ứng hình thức language/region (hai chữ cái), nhưng các subtag không nhất thiết có registration hợp lệ hay ứng dụng có nội dung tương ứng. Nếu hệ thống chỉ có bản dịch `vi-VN`, `en-US`, `zh-Hant-TW` thì phải **allowlist các tag được hỗ trợ** thay vì nhận mọi chuỗi regex-pass làm ngôn ngữ khả dụng.

### 4.2. Grandfathered/legacy tags

BCP 47 còn giữ đường tương thích cho một số grandfathered tags. `Locale.forLanguageTag(...)` có quy tắc chuyển đổi những mã cũ đã có preferred value. Đừng tự duy trì một bảng ánh xạ đầy đủ bằng trí nhớ hoặc giả định việc canonicalization của hai JDK versions luôn giữ nguyên chuỗi ban đầu. Nếu cần bảo toàn nguyên văn tag người gửi, lưu riêng raw input và phiên bản canonical.

### 4.3. Empty/undetermined tag

`und` là mã cho **undetermined language**. Nó có ngữ nghĩa hợp lệ trong BCP 47, nhưng một API “chọn ngôn ngữ bản dịch bắt buộc” có thể không chấp nhận nó. Hãy phân biệt:
- **Cú pháp:** `und` có thể là tag well-formed.
- **Chính sách sản phẩm:** trường `preferredLanguage` phải là một language thực và có bản dịch hay không?

Ví dụ demo mục 13 có **application policy** từ chối `und` khi bắt buộc có ngôn ngữ chính, không khẳng định `und` là BCP 47 sai.

## 5. BCP 47 trong Java 17+: `Locale` và bộ API cơ bản

### 5.1. Từ wire string sang `Locale`

```java
Locale locale = Locale.forLanguageTag("zh-Hant-TW");

System.out.println(locale.getLanguage());    // zh
System.out.println(locale.getScript());      // Hant
System.out.println(locale.getCountry());     // TW
System.out.println(locale.toLanguageTag());  // zh-Hant-TW
```

Đây là snippet runnable trong `main` với `import java.util.Locale;`; chương trình hoàn chỉnh được cung cấp ở mục 13.

`Locale` đại diện cho lựa chọn locale, không bao gồm bản dịch hoặc business rules. Muốn định dạng ngày/số/tiền tệ, chuyển `Locale` cho `DateTimeFormatter`, `NumberFormat`, `Collator` hoặc API tương ứng, với các giới hạn locale data của runtime.

### 5.2. Đưa `Locale` về string trao đổi

```java
String wireTag = locale.toLanguageTag();
```

Dùng `toLanguageTag` thay vì `toString` khi ghi metadata ngôn ngữ lên HTTP headers, JSON, database hoặc message bus. `Locale.toString` cho biểu diễn Java dành cho debug, có thể có `_`, dấu `#` hoặc các thông tin khác không phải BCP 47 wire format.

### 5.3. `Locale` immutable và thread-safe cho việc đọc

`Locale` là immutable class; có thể chia sẻ một instance như giá trị cấu hình, nhưng **không nên thay `Locale.setDefault(...)` global** để xử lý các requests khác ngôn ngữ trong cùng server. Default locale của JVM có phạm vi quá rộng và dễ gây data races/misformat. Truyền `Locale` tường minh xuống formatter/service trong request context.

### 5.4. Không phụ thuộc default locale để tạo tag

`Locale.getDefault()` phản ánh cấu hình môi trường process, không đồng nghĩa preference của user. Một service container có default `en-US` không được mặc nhiên kết luận mọi khách hàng đều muốn tiếng Anh. Chuỗi tag được lấy từ **user setting đã xác minh**, negotiated request hoặc content metadata rõ ràng.

## 6. Phân biệt parser dễ dãi và validator nghiêm ngặt

Đây là **điểm nguy hiểm nhất** khi đưa tag qua API, vì một input sai có thể bị “sửa thành hợp lệ” mà caller không hay biết.

### 6.1. `Locale.forLanguageTag` là parser tolerant

Theo Javadoc, `Locale.forLanguageTag(tag)` **bỏ qua subtag ill-formed đầu tiên và tất cả subtags phía sau**. Do đó:

```java
String result = Locale.forLanguageTag("en_US").toLanguageTag();
// "und" trên JDK 17 trong ví dụ.
```

Vì `en_US` không có cấu trúc BCP 47 hợp lệ, parser không ném exception mà tạo một locale tương ứng với phần parse được (ở đây không có language hợp lệ). Nếu code sử dụng `forLanguageTag` rồi không kiểm tra có thể silently đổi ý nghĩa dữ liệu.

### 6.2. `Locale.Builder.setLanguageTag` dùng để kiểm tra well-formed

```java
try {
    Locale strict = new Locale.Builder()
            .setLanguageTag("en_US")  // IllformedLocaleException
            .build();
} catch (IllformedLocaleException expected) {
    // Báo lỗi input có cú pháp sai.
}
```

Dùng `Locale.Builder` khi **không muốn bỏ qua phần sai cú pháp**. Exception là `java.util.IllformedLocaleException` (subclass của `RuntimeException`).

### 6.3. Strict syntax ≠ registry/allowlist validation

`Builder.setLanguageTag` kiểm tra *well-formed syntax*, chứ **không xác minh mọi subtag đã tồn tại trong IANA Language Subtag Registry**. Ứng dụng cần thêm các lớp kiểm soát nếu nghiệp vụ yêu cầu:

1. Không chấp nhận `null` hoặc chuỗi rỗng cho trường bắt buộc.
2. Giới hạn độ dài input (để tránh parser abuse).
3. Kiểm tra cú pháp bằng `Locale.Builder.setLanguageTag`.
4. Yêu cầu có language chính nếu trường `preferredLanguage` không chấp nhận `und` hoặc pure private-use.
5. So với **allowlist các tag mà hệ thống thật sự có bản dịch**.
6. Nếu cần semantics registry đầy đủ, dùng dữ liệu registry/thư viện đã được quản lý và cập nhật, không tự dùng một regex thiếu subtag rules.

### 6.4. Xử lý input sai nên là quyết định API

Đối với request tạo dữ liệu có trường ngôn ngữ không hợp lệ, có thể trả lỗi validation phù hợp (ví dụ HTTP 400) thay vì silent fallback. Đối với **UI language negotiation** từ một header tùy chọn, có thể dùng fallback mà không làm fail toàn request. Hai chính sách khác nhau có mục đích khác nhau; đừng áp dụng một cách xử lý cho mọi endpoint.

### 6.5. Đừng dùng `new Locale(...)` chỉ để phân tích wire tag

Constructor legacy với `language`/`country`/`variant` sử dụng tham số khác cú pháp BCP 47 và không thay thế parser. Nên tạo:

```java
Locale locale = Locale.forLanguageTag("sr-Latn-RS");
```

hoặc:

```java
Locale locale = new Locale.Builder()
        .setLanguageTag("sr-Latn-RS")
        .build();
```

Không cố tách `sr-Latn-RS` thủ công thành `language, country, variant` bằng `split("-")` rồi đoán index, vì script, region, variants và extensions đều optional.

## 7. Unicode locale extensions và ý nghĩa định dạng

BCP 47 có cơ chế extension; `u` dùng các Unicode locale keywords, ví dụ:

```java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai");
String calendar = locale.getUnicodeLocaleType("ca"); // buddhist
String numbering = locale.getUnicodeLocaleType("nu"); // thai
```

Có thể đọc `calendar`, `numbering` từ locale object. Nhưng:
- `u-ca` mô tả một **calendar preference**; không có nghĩa văn bản được viết bằng tiếng Thái.
- `u-nu` mô tả **numbering system**; không nói người dùng thuộc quốc tịch nào.
- Một formatting API có thể hỗ trợ một subset locale data theo JDK/provider. **Đừng khẳng định mọi Unicode extension bắt buộc tạo định dạng riêng** trên mọi hệ thống.
- Nếu API sản phẩm chỉ cho phép `language-script-region`, có thể chọn loại bỏ extensions theo một **chính sách được tài liệu hóa**, nhưng đừng silently xóa thông tin mang ý nghĩa khi schema đã hứa giữ full tag.

### 7.1. Lưu cả tag hay chỉ các trường riêng?

Nếu ý định là giữ full locale preferences, lưu **một BCP 47 string duy nhất** giúp giữ script, variant và extensions. Nếu ứng dụng cần tìm kiếm/filter theo language/region riêng, có thể tạo các trường chỉ mục dẫn xuất, nhưng phải xác định field nào là source of truth.

### 7.2. Không tự suy Unicode normalization từ tag

`vi-VN` không xác định chuỗi Unicode là NFC hay NFD. Hai chuỗi hiển thị giống nhau có thể khác các code points. Nếu cần so sánh/lưu trữ Unicode theo một normalization form, dùng `java.text.Normalizer` theo contract nghiệp vụ. **BCP 47 không tự normalize text và không tự translate.**

## 8. Trao đổi trong JSON, message bus và database

Một schema dữ liệu đơn giản có thể chứa:

```json
{
  "id": "article-42",
  "languageTag": "vi-VN",
  "title": "Ví dụ về BCP 47",
  "body": "Nội dung được viết bằng tiếng Việt."
}
```

Đây là **mẫu dữ liệu**; `languageTag` là tên trường do hệ thống tự đặt, không phải tên field bắt buộc của mọi chuẩn JSON. Giao thức giữa hai dịch vụ phải thỏa thuận:
- Tên field, dạng string, nullability.
- Cho phép ngôn ngữ chung như `vi` hay chỉ cụ thể như `vi-VN`.
- Có chấp nhận script/region/variant/extensions không?
- Mức độ strict syntax và allowlist/registry validation.
- Cách phản hồi khi tag không có bản dịch tương ứng.
- Có canonicalize khi lưu không? Có cần giữ raw input để audit không?
- Mức độ tin cậy giữa metadata ngôn ngữ và văn bản thật.

### 8.1. Lưu metadata của từng bản dịch

Ví dụ:

```json
{
  "documentId": "policy-42",
  "translations": {
    "vi-VN": {"title": "Điều khoản"},
    "en-US": {"title": "Terms"},
    "zh-Hant-TW": {"title": "條款"}
  }
}
```

Những keys là BCP 47 tags; frontend/backend có thể truyền nhất quán. Nếu **nhóm dịch thuật** đổi nội dung một bản dịch, tag cho biết nhãn của bản dịch, không tự bảo đảm câu chữ thực sự đúng language.

Nếu dùng language tags làm JSON keys:
- Chuẩn hóa trước khi ghi và có unique constraint phù hợp.
- Xác định policy case-insensitive comparison để tránh `en-US` và `en-us` thành hai keys logic khác nhau.
- Không trộn `en_US` vào cùng bảng.
- Định nghĩa cách fallback khi không có exact key.

### 8.2. Database schema nên chọn gì?

Một cột `language_tag VARCHAR(...)` có thể lưu canonical BCP 47 string và index cho lookup. Không chọn `CHAR(2)` chỉ vì vài ngôn ngữ có hai ký tự. Độ dài cần theo schema/app policy (BCP 47 cho phép nhiều subtags); nếu giới hạn, phải validate có thông báo lỗi thay vì cắt chuỗi.

Nếu có `locale_region` hoặc `script` riêng, derive chúng bằng parser nhất quán và giữ source-of-truth rõ ràng. Không dùng location của IP để lặng lẽ ghi đè language tag khách hàng đã chọn.

### 8.3. Event/message contracts

Một event có thể chứa cả `contentLanguage` (ngôn ngữ của payload) và `preferredLanguage` (ngôn ngữ người nhận mong muốn). Đừng dùng một field `locale` đa nghĩa khiến một consumer hiểu nó là nơi ở hoặc timezone. Với hệ thống bất đồng bộ, phiên bản schema và fallback policy cần nhất quán giữa producer/consumer.

### 8.4. Không dùng tag làm cơ chế phân quyền

Language tag được cung cấp từ user/header là **dữ liệu không tin cậy**. `Accept-Language: en-US` không chứng minh quyền truy cập vào nội dung giới hạn cho khu vực Mỹ. Authorization, residency, licensing và locale negotiation là những chính sách khác nhau.

## 9. HTTP `Accept-Language`: không phải một language tag đơn lẻ

HTTP `Accept-Language` (RFC 9110 `12.5.4`) là một **danh sách language ranges được ưu tiên**, có thể kèm trọng số `q`:

```http
GET /articles HTTP/1.1
Host: example.test
Accept-Language: fr-CA, en-GB;q=0.8, vi-VN;q=0.5
```

Đây là **ví dụ giao thức**, `example.test` là tên miền minh họa. Ý nghĩa:
- Ưu tiên hàng đầu `fr-CA` (q mặc định `1.0`).
- Chấp nhận `en-GB` với ưu tiên `0.8`.
- Chấp nhận `vi-VN` với ưu tiên `0.5`.
- Nếu server **chỉ có `en-GB` và `vi-VN`**, lựa chọn hợp lý theo lookup là `en-GB`, không tự bịa bản dịch `fr-CA`.
- Header không nói rằng body request của client nhất thiết bằng `fr-CA`.

### 9.1. Trọng số `q`

RFC 9110 định nghĩa `qvalue` trong khoảng `0` đến `1`. Không khai báo `q` thì weight mặc định là `1`. `q=0` thể hiện không chấp nhận representation đó; sender không nên tạo hơn ba chữ số thập phân của qvalue.

Ví dụ:

```text
Accept-Language: en-US;q=0.9, vi-VN;q=0.8
Accept-Language: de, en;q=0.5
Accept-Language: *
```

`*` là language-range wildcard trong matching, không phải tag cụ thể của nội dung. Không lưu `*` vào trường `Content-Language` hoặc vào database field đòi **một** BCP 47 language tag.

### 9.2. Khai báo language preference có thể tiết lộ thông tin

`Accept-Language` thường được gửi bởi browser theo cấu hình người dùng. Một danh sách chi tiết nhiều tags có thể góp phần fingerprinting, nên server tránh lưu đầy đủ raw header vô thời hạn nếu không cần thiết. Không coi header là định danh chắc chắn hoặc một thông tin luôn chính xác; client có thể không gửi, gửi sai hoặc cố tình sửa.

### 9.3. Ranges khác tags

`Accept-Language: en` là một **range yêu cầu ngôn ngữ Anh**. Một representation có tag `en-US` hoặc `en-GB` có thể nằm trong tập ứng viên theo matching policy. **`Content-Language: en-US`** lại là một **tag gắn nội dung thực sự**. Hai header có vai trò khác nhau.

### 9.4. Server có thể có preference khác

Một số dịch vụ ưu tiên lựa chọn ngôn ngữ đã lưu trong profile, lựa chọn rõ ràng qua route (`/vi/...`) hoặc query param hơn browser header. Đây là **quy tắc sản phẩm** cần tài liệu hóa. `Accept-Language` không nên im lặng ghi đè lựa chọn đã lưu của người dùng.

## 10. HTTP `Content-Language`: metadata của representation

RFC 9110 `8.5` mô tả `Content-Language` là thông tin **ngôn ngữ của nội dung representation** và có thể chứa một hoặc nhiều language tags.

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Language: vi-VN
Vary: Accept-Language
```

Đây là ví dụ response:
- `Content-Language: vi-VN` nói payload được gắn với tiếng Việt.
- `Content-Type: application/json; charset=utf-8` nói media type/encoding, **không quyết định ngôn ngữ tự nhiên**.
- `Vary: Accept-Language` nói cho caches rằng representation có thể biến đổi theo header request đó; thêm `Vary` chỉ khi thực sự dùng header để chọn response.

### 10.1. Không lẫn `Content-Language` với `Accept-Language`

| Header | Xuất hiện ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `Accept-Language` | Thường request | Client muốn các ngôn ngữ nào, ưu tiên như thế nào |
| `Content-Language` | Request hoặc response khi thích hợp | Ngôn ngữ phục vụ đối tượng đọc của representation hiện có |
| `Content-Type` | Request/response | Media type và một số tham số như charset |
| `Vary` | Response | Những request headers ảnh hưởng việc chọn representation để cache |

Nếu một JSON response chứa nhiều bản dịch, `Content-Language` có thể không thể hiện đầy đủ ngữ nghĩa từng field. Khi đó metadata cấp trường/translation map là quan trọng hơn. Không tùy tiện gắn `Content-Language` một tag rồi giả định mọi chuỗi trong JSON đều theo tag đó.

### 10.2. Ngôn ngữ, script, region và encoding tách biệt

`zh-Hant-TW` diễn đạt language/script/region; `UTF-8` là cách mã hóa byte cho Unicode. `zh-Hant` không định nghĩa codepage riêng, không yêu cầu một font duy nhất và không thay thế header/mime encoding.

### 10.3. Thêm `Vary` phù hợp

Nếu response body phụ thuộc `Accept-Language`, `Vary: Accept-Language` là cơ chế HTTP thích hợp cho cache. Nếu ứng dụng có cache keys theo user profile hoặc nội dung cá nhân hóa, cần thêm privacy/cache controls phù hợp, không chỉ `Vary`. Không dùng mỗi language tag để phân chia dữ liệu được phân quyền.

## 11. RFC 4647: Lookup và Filtering là hai mục tiêu khác nhau

RFC 4647 quy định các kỹ thuật *language matching*.

### 11.1. Lookup: cần chọn **một** representation

Một dịch vụ chỉ trả một bản dịch có thể sử dụng `Locale.lookupTag`:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse(
            "fr-CA, en-GB;q=0.8, vi-VN;q=0.5");

List<String> supported =
        List.of("vi-VN", "en-GB", "en-US", "zh-Hant-TW");

String selected = Locale.lookupTag(priorities, supported);
// "en-GB" với các ứng viên trên.
```

Snippet cần import `java.util.*`. Hàm `lookupTag` trả **tag phù hợp nhất trong tập được cung cấp**, hoặc `null` khi không có match. Không tự tạo tag mà server không có nội dung thật.

**Chú ý:** Những tag như `fr-CA` có thể không match một ứng viên `fr-FR` theo lookup mà bạn kỳ vọng bằng trực giác; thuật toán RFC 4647 có quy tắc thu ngắn range riêng. Nếu muốn fallback dialect bằng language-family, phải thiết kế/kiểm thử policy rõ, không tự tin rằng mọi biến thể cùng language luôn hoán đổi được.

### 11.2. Filtering: cần trả **nhiều** representations hợp lệ

`Locale.filterTags` trả danh sách các tag match ranges theo filter mechanism:

```java
List<String> matches = Locale.filterTags(
    Locale.LanguageRange.parse("zh, en;q=0.5"),
    List.of("en-US", "zh-Hant-TW", "vi-VN", "zh-Hans-CN"));

// Với ứng viên/test hiện tại:
// [zh-Hant-TW, zh-Hans-CN, en-US]
```

Điểm khác biệt:
- Lookup: chọn **một** candidate hoặc không có kết quả.
- Filtering: trả **một tập** candidates phù hợp theo priority policy.
- Filtering không tự dịch bản `zh-Hans-CN` sang `zh-Hant-TW`.
- Không để một candidate bị lọc từ tag lạ nhưng lại tự coi như “có content” khi hệ thống không có file/string translation tương ứng.

### 11.3. Ngôn ngữ priority list từ header

`Locale.LanguageRange.parse` có sẵn từ Java 8 và vẫn hợp lệ trên Java 17. Nó hỗ trợ cú pháp priority list, q weights và có thể mở rộng những equivalent language ranges theo JDK registry mapping. Không tự viết parser `header.split(",")` cho mọi trường hợp rồi bỏ qua `q`; cách này dễ sai với extensions, whitespace và cú pháp xấu.

### 11.4. Không có match thì sao?

`Locale.lookupTag(...)` có thể trả `null`; ứng dụng cần **fallback được quyết định trước**. Ví dụ:
- Default của ứng dụng: `vi-VN`.
- Bản dịch gốc của bài viết: `en-US`.
- Một tag do người dùng chọn và đã kiểm tra hiện có content.

Không có một fallback duy nhất do BCP 47 áp đặt cho mọi sản phẩm. Nếu một tag bị `q=0` (không chấp nhận), đừng cố chọn lại đúng tag đó chỉ để có response; thiết kế chính sách RFC 9110 và nội dung tối thiểu hợp lý.

### 11.5. Không dùng matching như access control

Nếu người dùng yêu cầu `fr` nhưng không có bản dịch, một số ứng dụng sẽ trả default, một số hiện giao diện chọn ngôn ngữ và một số có thể trả `406 Not Acceptable` tùy HTTP semantics/chính sách. **Không** được để negotiation xác định quyền truy cập vào dữ liệu bí mật.

## 12. Lựa chọn ngôn ngữ trong backend: quy trình có thể bảo trì

Một request điển hình:

```text
HTTP request
    |
    +-- Explicit user choice? ---- Yes ---> Validate & select supported tag
    |
    +-- Saved profile preference? - Yes --> Validate & select supported tag
    |
    +-- Accept-Language present? -- Yes --> Parse LanguageRange + RFC4647 lookup
    |
    +-- No match --------------------------> Documented default/fallback
    |
    v
Load actual content/translation for selected tag
    |
    v
Set Content-Language according to response representation
Set Vary: Accept-Language when request header drives selection
    |
    v
Serialize UTF-8 response with explicit metadata if needed
```

Đây là **mô hình ứng dụng**, không phải thứ tự bắt buộc của RFC. Nếu người dùng chủ động chọn language trong tài khoản, ứng dụng có thể đặt lựa chọn đó cao hơn browser header.

### 12.1. Dữ liệu vào phải có giới hạn

`Accept-Language` là header do client điều khiển. Đặt giới hạn kích thước và số lượng elements phù hợp để tránh input parsing quá lớn. Catch exceptions cụ thể và quyết định fallback/HTTP error rõ. Không log nguyên raw header trong mọi request khi không cần.

### 12.2. Supported tags nên lấy từ nội dung thật

`List.of("vi-VN","en-GB","en-US",...)` phải phản ánh những bản dịch **đã triển khai**, không phải tất cả locales mà JDK nhận ra. Việc `Locale.forLanguageTag("eo")` thành công không có nghĩa ứng dụng của bạn đã có bản dịch Esperanto.

### 12.3. Fallback không được biến thành silent data corruption

Trong UI negotiation, việc header sai và chọn default có thể chấp nhận. Trong database mutation, nếu client gửi `languageTag=en_US`, chuẩn hóa thành `und` rồi lưu là sai nghiệp vụ. Hãy trả validation error với trường cụ thể.

### 12.4. Chọn đúng tag cho response

Giả sử client yêu cầu `fr-CA` nhưng server chọn `en-GB`. Header response phải phản ánh **bản dịch đã gửi** (ví dụ `Content-Language: en-GB`), không sao chép yêu cầu `fr-CA` như thể response đang bằng tiếng Pháp.

## 13. Chương trình Java 17+ hoàn chỉnh: parse, validate, negotiate và serialize tags

File **`Bcp47ExchangeDemo.java`** dùng **JDK 17+** và không cần thư viện ngoài. Nó kiểm chứng:

1. `Locale.forLanguageTag("SR-latn-rs")` chuẩn hóa thành `sr-Latn-RS`, tách language/script/region.
2. Unicode extension `u-ca-buddhist-nu-thai` cung cấp calendar và numbering keywords.
3. Parser tolerant biến `en_US` thành `und`; validator `Locale.Builder` nghiêm ngặt **từ chối `en_US`**.
4. Validation policy của ứng dụng có thể từ chối `und` khi bắt buộc có ngôn ngữ chính.
5. `Accept-Language` với q-weights chọn `en-GB` khi `fr-CA` không có trong supported list.
6. Script-aware lookup chọn `zh-Hant-TW`.
7. Không có match hoặc header bị lỗi thì chọn fallback `vi-VN` trong **UI selection policy**.
8. `filterTags` trả các ứng viên theo preference.
9. Chuẩn hóa tag trước khi tạo `Content-Language` của response.

**Mức độ xác minh:** chương trình đã được biên dịch và thực thi bằng `javac/java` trên JDK 17+, exit code 0, với stdout chính xác dưới đây. Đây là test cho **hành vi API** và chính sách demo, không xác nhận IANA registry semantic của mọi tag hoặc nội dung bản dịch của một ứng dụng thực.

### 13.1. Mã đầy đủ `Bcp47ExchangeDemo.java`

```java
import java.util.*;
import java.util.stream.Collectors;

public final class Bcp47ExchangeDemo {
    private static void check(boolean yes, String message) {
        if (!yes) throw new AssertionError(message);
    }

    // Application validation: strict syntax, no undefined/only-private tag.
    public static String canonicalTag(String raw) {
        if (raw == null || raw.isBlank() || raw.length() > 100) {
            throw new IllegalArgumentException("missing or oversized tag");
        }
        final Locale locale;
        try {
            locale = new Locale.Builder().setLanguageTag(raw).build();
        } catch (IllformedLocaleException ex) {
            throw new IllegalArgumentException("malformed BCP 47 tag", ex);
        }
        if (locale.getLanguage().isEmpty()) {
            throw new IllegalArgumentException("language required");
        }
        return locale.toLanguageTag();
    }

    // UI fallback policy. Not a substitute for validating a stored tag.
    public static String selectResponseTag(
            String acceptLanguage, List<String> supported, String fallback) {
        if (acceptLanguage == null || acceptLanguage.isBlank()
                || acceptLanguage.length() > 512) {
            return fallback;
        }
        try {
            List<Locale.LanguageRange> priorities =
                    Locale.LanguageRange.parse(acceptLanguage);
            String selected = Locale.lookupTag(priorities, supported);
            return selected == null ? fallback : selected;
        } catch (IllegalArgumentException malformedHeader) {
            return fallback;
        }
    }

    public static void main(String[] args) {
        Locale serbian = Locale.forLanguageTag("SR-latn-rs");
        check("sr-Latn-RS".equals(serbian.toLanguageTag()), "canonical");
        check("sr".equals(serbian.getLanguage()), "language");
        check("Latn".equals(serbian.getScript()), "script");
        check("RS".equals(serbian.getCountry()), "region");
        System.out.println("canonical.tag=" + serbian.toLanguageTag());
        System.out.println("canonical.parts=sr|Latn|RS");

        Locale unicode = Locale.forLanguageTag(
                "en-US-u-ca-buddhist-nu-thai");
        check("buddhist".equals(unicode.getUnicodeLocaleType("ca")),
                "calendar extension");
        check("thai".equals(unicode.getUnicodeLocaleType("nu")),
                "numbering extension");
        System.out.println("unicode.calendar="
                + unicode.getUnicodeLocaleType("ca"));
        System.out.println("unicode.numbers="
                + unicode.getUnicodeLocaleType("nu"));

        check("und".equals(
                Locale.forLanguageTag("en_US").toLanguageTag()),
                "lenient truncation");
        boolean strictRejects = false;
        try {
            canonicalTag("en_US");
        } catch (IllegalArgumentException expected) {
            strictRejects = true;
        }
        check(strictRejects, "strict syntax");
        System.out.println("parse.lenientUnd=true");
        System.out.println("parse.strictRejected=true");
        check("zh-Hant-TW".equals(canonicalTag("ZH-hant-tw")),
                "strict canonicalization");
        System.out.println("parse.strictCanonical=zh-Hant-TW");
        boolean undRejected = false;
        try {
            canonicalTag("und");
        } catch (IllegalArgumentException expected) {
            undRejected = true;
        }
        check(undRejected, "application requires a language");
        System.out.println("parse.undRejectedByPolicy=true");

        List<String> supported =
                List.of("vi-VN", "en-GB", "en-US", "zh-Hant-TW");
        check("en-GB".equals(selectResponseTag(
                "fr-CA, en-GB;q=0.8, vi-VN;q=0.5",
                supported, "vi-VN")), "weighted lookup");
        System.out.println("http.weightedLookup=en-GB");
        check("zh-Hant-TW".equals(selectResponseTag(
                "zh-Hant-TW, en-US;q=0.6", supported, "vi-VN")),
                "script-aware");
        System.out.println("http.scriptLookup=zh-Hant-TW");
        check("vi-VN".equals(selectResponseTag(
                "de-DE", supported, "vi-VN")), "fallback");
        System.out.println("http.noMatchFallback=vi-VN");
        check("vi-VN".equals(selectResponseTag(
                "en_US;q=wat", supported, "vi-VN")), "invalid header");
        System.out.println("http.invalidFallback=vi-VN");

        List<String> filtered = Locale.filterTags(
                Locale.LanguageRange.parse("zh, en;q=0.5"),
                List.of("en-US", "zh-Hant-TW", "vi-VN", "zh-Hans-CN"));
        check(filtered.equals(
                List.of("zh-Hant-TW", "zh-Hans-CN", "en-US")),
                "filter order");
        System.out.println("http.filter=" + String.join(",", filtered));

        String outgoingContentLanguage = canonicalTag("VI-vn");
        check("vi-VN".equals(outgoingContentLanguage), "response tag");
        System.out.println("http.contentLanguage=" + outgoingContentLanguage);
        System.out.println("checks=PASS");
    }
}
```

### 13.2. Lệnh chạy

```bash
javac -encoding UTF-8 Bcp47ExchangeDemo.java
java Bcp47ExchangeDemo
```

Chỉ cần JDK 17+. Không cần web server, HTTP client, database, ICU4J, thư viện i18n hay bất kỳ JAR bên ngoài. Code tự chứa chính sách giả lập chọn ngôn ngữ từ các dữ liệu cho trước.

### 13.3. Stdout chính xác đã kiểm chứng

```text
canonical.tag=sr-Latn-RS
canonical.parts=sr|Latn|RS
unicode.calendar=buddhist
unicode.numbers=thai
parse.lenientUnd=true
parse.strictRejected=true
parse.strictCanonical=zh-Hant-TW
parse.undRejectedByPolicy=true
http.weightedLookup=en-GB
http.scriptLookup=zh-Hant-TW
http.noMatchFallback=vi-VN
http.invalidFallback=vi-VN
http.filter=zh-Hant-TW,zh-Hans-CN,en-US
http.contentLanguage=vi-VN
checks=PASS
```

Kết quả được in không phụ thuộc thời gian, network hay locale mặc định của hệ điều hành. Đây là stdout thật của Java demo đã compile/run, không phải ví dụ output suy đoán.

### 13.4. Giải thích `canonical.*`

Locale nhận input `SR-latn-rs` nhưng `toLanguageTag()` trả `sr-Latn-RS`. `getLanguage()`, `getScript()` và `getCountry()` trả từng thành phần tương ứng. **Chuẩn hóa cách viết** không xác nhận người dùng hiện ở quốc gia RS.

### 13.5. Giải thích `unicode.*`

`en-US-u-ca-buddhist-nu-thai` được Java tách thành calendar preference `buddhist` và numbering-system preference `thai`. Demo chỉ đọc keywords; **không giả định formatter nào cũng support và thực thi chúng y hệt**.

### 13.6. Giải thích `parse.*`

`Locale.forLanguageTag("en_US")` không ném mà bỏ phần sai, trả locale biểu diễn `und` trong test. `new Locale.Builder().setLanguageTag("en_US")` ném exception, được ứng dụng chuyển thành validation failure. `und` là tag có nghĩa “undetermined”, nhưng demo cố tình từ chối theo **chính sách trường bắt buộc xác định ngôn ngữ**.

### 13.7. Giải thích `http.weightedLookup`

Danh sách supported: `vi-VN`, `en-GB`, `en-US`, `zh-Hant-TW`. Người dùng thích `fr-CA` nhất, nhưng server không có bản tương ứng; `en-GB` là ứng viên match có ưu tiên tiếp theo, nên được chọn. Không tự sinh chuỗi nội dung tiếng Pháp bằng một tag giả.

### 13.8. Giải thích `http.scriptLookup`

Một requested range `zh-Hant-TW` match representation có sẵn. Đây là minh họa cần phân biệt `Hant` và `Hans`; đừng dùng `zh` chung rồi vô tình gửi bản chữ giản thể cho người yêu cầu phồn thể nếu sản phẩm có chính sách tách hai bản.

### 13.9. Giải thích `http.filter`

`Locale.filterTags(...)` trả ba candidates phù hợp theo thứ tự preference của input/test. `vi-VN` không nằm trong kết quả vì không match `zh` hoặc `en`. Đó là **filtering**, không phải “translate” hay tạo kết quả từ một model.

### 13.10. Giải thích `http.contentLanguage`

Chính sách output gọi `canonicalTag("VI-vn")`, nhận `vi-VN`. Đó là tag thích hợp để gắn làm metadata cho một response đã chọn là bản tiếng Việt. **Không nhất thiết** lấy tag này từ raw `Accept-Language`; phải dựa trên bản nội dung thực sự được gửi.

## 14. Thiết kế tests cho BCP 47

### 14.1. Ma trận test tối thiểu

| Input / tình huống | Mục tiêu test |
| --- | --- |
| `vi-VN` | Parse thành language `vi`, region `VN` |
| `en` | Tag không cần region vẫn hợp lệ |
| `sr-Latn-RS` | Tách script và region |
| `zh-Hant-TW` | Giữ phân biệt script |
| `es-419` | Region có thể là 3 chữ số |
| `en-US-u-ca-buddhist` | Unicode calendar extension |
| `en-US-u-nu-thai` | Unicode numbering extension |
| `de-CH-1901` | Variant và registered semantics |
| `en_US` | Strict validation từ chối |
| `und` | Policy tùy trường, không mặc nhiên BCP 47 sai |
| `null`, chuỗi trắng | Trả validation error khi trường bắt buộc |
| Tag rất dài | Giới hạn input |
| Unsupported nhưng syntactically well-formed | Không giả định có bản dịch |
| `Accept-Language` có `q` | Ưu tiên theo quality values |
| `Accept-Language` có `*` | Xử lý wildcard theo matching/fallback policy |
| `Accept-Language` sai | Chính sách fallback hoặc validation rõ |
| Không có candidate | Kết quả null + fallback có tài liệu |
| `Content-Language` | Tag phản ánh nội dung thực tế |
| Các keys JSON khác case | Canonicalize / unique constraint |
| Nội dung NFC/NFD | Unicode normalization là vấn đề riêng |
| API giới hạn supported tags | Chỉ chọn nội dung thực tồn tại |

### 14.2. Property-based checks hữu ích

Một số properties:
- Với tag được app chấp nhận, `Locale.toLanguageTag()` trả chuỗi không rỗng theo cú pháp BCP 47.
- Sau canonicalization, không tạo hai keys logic khác nhau chỉ vì case input khác.
- Matching không trả tag ngoài **supported list**.
- Fallback luôn là tag thực sự được service hỗ trợ.
- `Content-Language` của response tương ứng resource/translation đã chọn.
- Khi input sai, hệ thống không silently lưu `und` như thể đó là language hợp lệ của bài viết.

**Chú ý:** Java Javadoc không bảo đảm mọi language tags *round-trip* giữ nguyên chuỗi gốc do legacy mappings/variants. Không assert `tag.equals(Locale.forLanguageTag(tag).toLanguageTag())` cho **mọi** tag có thể tồn tại.

### 14.3. Kiểm thử nội dung, không chỉ parser

BCP 47 xác định nhãn ngôn ngữ, **không kiểm tra câu chữ dịch thuật**. Một endpoint trả header `Content-Language: vi-VN` nhưng body thực là tiếng Anh có thể pass syntax test mà vẫn sai nghiệp vụ. Integration test nên lấy một key đã biết, so bản dịch/metadata thực với translation catalog và policy fallback.

### 14.4. Test HTTP cache negotiation

Nếu body thay đổi theo `Accept-Language`, xác minh response có `Vary: Accept-Language` và CDN/cache key được thiết kế đúng. Đừng chia sẻ cached response cá nhân hóa giữa users chỉ vì ngôn ngữ giống nhau.

## 15. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Truyền `en_US` như một BCP 47 tag | Sai cú pháp, parser có thể bỏ phần lỗi | Dùng `en-US` |
| Lưu `Locale.toString()` trong API | Không bảo đảm wire tag, có dấu `_` | `toLanguageTag()` |
| Dùng `split("-")` và đoán field thứ hai là region | Script/variants/extensions là optional | `Locale.forLanguageTag` / Builder |
| Chỉ chấp nhận regex `xx-YY` | Loại bỏ nhiều tag hợp lệ | Dùng parser BCP 47 |
| Coi `forLanguageTag` là validator strict | Silently bỏ ill-formed subtags | `Locale.Builder.setLanguageTag` |
| Coi Builder syntax pass là có IANA registration | Có thể well-formed nhưng không registered | Registry data/allowlist theo requirement |
| Coi `und` là một lỗi RFC | `und` có nghĩa undetermined | Policy sản phẩm quyết định |
| Coi region là nơi ở/quốc tịch | Sai ngữ nghĩa | Chỉ xem metadata language variety |
| Coi script là region | Mất khác biệt `Hant/Hans`, `Latn/Cyrl` | Lưu và match script |
| Coi BCP 47 là encoding | Lẫn ngôn ngữ với charset | UTF-8 và Content-Language độc lập |
| Thấy tag hợp lệ nên cho rằng có bản dịch | Có thể không có resources | Supported list từ catalog |
| Tự viết `Accept-Language.split(",")` mà bỏ q | Sai thứ tự ưu tiên | `Locale.LanguageRange.parse` |
| Coi `Accept-Language` như một tag | Có danh sách và wildcard | RFC 4647 ranges |
| Bỏ qua `q=0` | Có thể chọn representation không chấp nhận | Áp dụng HTTP negotiation policy |
| Lấy raw preference làm `Content-Language` | Header có thể không khớp body đã chọn | Set theo thực tế response |
| Không có fallback rõ | Lỗi null/khác ngôn ngữ ngẫu nhiên | Documented default |
| Coi filter và lookup là một | Một cái nhiều kết quả, một cái một | Chọn API theo mục tiêu |
| Dùng `Locale.setDefault` cho từng request | Tác dụng global, dễ race | Truyền Locale per request |
| Coi language tag là authorization | Lỗ hổng quyền/giấy phép | Phân quyền độc lập |
| Log mọi raw header dài | Tốn storage, có rủi ro privacy | Giới hạn/lọc logs |
| Nghĩ `u-nu` đổi ngôn ngữ văn bản | Nó biểu diễn preference numbering | Phân biệt language và formatting |
| Dùng tag để thay Unicode Normalizer | NFC/NFD không liên quan trực tiếp | Normalize text khi cần |
| Sao chép header locale không có encoding | Data transport có thể fail | UTF-8/media type riêng |

## 16. Checklist ứng dụng thực tế

- [ ] Schema ghi rõ field là **BCP 47 language tag**, không phải display name.
- [ ] Giá trị dùng dấu `-`, không dùng `_` trên wire.
- [ ] Có phân biệt language/script/region khi sản phẩm cần.
- [ ] Không ép region cho tag chỉ có language.
- [ ] Có thể lưu Unicode extensions nếu hợp đồng yêu cầu.
- [ ] Không suy quốc tịch/vị trí từ tag.
- [ ] Sử dụng `Locale.toLanguageTag()` để serialize.
- [ ] Có `Locale.Builder.setLanguageTag` nếu cần strict syntax.
- [ ] Không tự coi cú pháp hợp lệ là IANA registry validity.
- [ ] Có allowlist những bản dịch ứng dụng thực sự hỗ trợ.
- [ ] Có giới hạn kích thước input.
- [ ] Có chính sách riêng cho `und` và private-use tags.
- [ ] Đọc `Accept-Language` như priority list, không phải single tag.
- [ ] Xử lý weights/qvalues theo RFC 9110.
- [ ] Dùng `Locale.LanguageRange.parse` và `lookupTag` / `filterTags` theo mục tiêu.
- [ ] Có fallback documented khi không match.
- [ ] Không dùng request language làm header response khi content khác.
- [ ] Có `Content-Language` phản ánh actual representation khi phù hợp.
- [ ] Có `Vary: Accept-Language` khi header ảnh hưởng response cached.
- [ ] Encoding (UTF-8) và language metadata được xử lý riêng.
- [ ] Không mutate global default locale mỗi request.
- [ ] Nếu API lưu user preference, lỗi sai cú pháp không silent convert thành `und`.
- [ ] Đã kiểm tra JSON/database canonicalization và uniqueness.
- [ ] Language tag không được dùng làm bằng chứng authorization/region access.
- [ ] Test cases bao gồm scripts, variants, extensions và invalid syntax.
- [ ] Test flow trên chính supported translations của sản phẩm.
- [ ] Java code JDK 17+ đã compile/run; stdout matches.

## 17. FAQ

**1. BCP 47 có phải tên của một ngôn ngữ không?**  
Không. Đây là thực hành chuẩn về cách **gắn nhãn ngôn ngữ**, gồm RFC 5646 và RFC 4647.

**2. `en_US` là BCP 47 tag hợp lệ không?**  
Không. Dạng BCP 47 dùng `en-US`. `en_US` có thể xuất hiện trong biểu diễn locale cũ nhưng không nên dùng trên API mới.

**3. `Locale.forLanguageTag` có ném exception khi tag sai không?**  
Không theo cách strict: nó bỏ ill-formed subtag đầu và phần còn lại. Muốn báo lỗi syntax dùng `Locale.Builder.setLanguageTag`.

**4. `Locale.toString` có tương đương `toLanguageTag` không?**  
Không. `toLanguageTag` cho chuỗi IETF BCP 47 phù hợp trao đổi dữ liệu.

**5. `zh-Hant` có giống `zh-TW` không?**  
Không. Cái đầu xác định script, cái sau xác định region. Không tự hoán đổi.

**6. `sr-Latn-RS` tách được thành những gì?**  
Language `sr`, script `Latn`, region `RS`.

**7. Có cần luôn gửi region như `VN` không?**  
Không. `vi` có thể đủ. Chọn độ cụ thể theo nội dung/hợp đồng sản phẩm.

**8. `und` là lỗi không?**  
Không mặc nhiên. Nó biểu thị ngôn ngữ chưa xác định; ứng dụng có thể từ chối theo policy riêng.

**9. Cú pháp hợp lệ có nghĩa đã được IANA đăng ký?**  
Không. Cần kiểm tra registry/validity hoặc allowlist riêng nếu quan trọng.

**10. `Accept-Language` có phải chỉ một tag không?**  
Không. Nó là tập **ranges có thứ tự/trọng số**, có thể có wildcard.

**11. `q=0.8` nghĩa là gì?**  
Một quality weight thể hiện ưu tiên tương đối; không phải xác suất một user biết ngôn ngữ.

**12. Lookup và filtering khác nhau gì?**  
Lookup chọn một tag hoặc null; filtering trả một danh sách tags phù hợp.

**13. Nếu client muốn `fr-CA` nhưng server chỉ có `en-GB`?**  
Áp dụng matching và fallback policy đã công bố. Không tạo ra translation mà hệ thống không có.

**14. `Content-Language` có nên sao chép nguyên `Accept-Language` không?**  
Không. Nó mô tả representation thực sự gửi.

**15. `Content-Language` có thay `charset=utf-8` không?**  
Không. Language và character encoding là hai đặc tính khác nhau.

**16. Có phải `Locale.setDefault` nên được gọi theo từng request?**  
Không. Nó ảnh hưởng phạm vi JVM; truyền Locale tường minh theo request.

**17. `u-ca`, `u-nu` làm gì?**  
Chúng là Unicode locale extension keywords liên quan calendar và numbering preferences; không tự dịch văn bản.

**18. `x-private` có dùng được trên API public không?**  
Có cú pháp private-use hợp lệ trong các trường hợp quy định, nhưng ý nghĩa chỉ tồn tại theo thỏa thuận; không nên dùng thay tag chuẩn nếu không cần.

**19. Language tag có cho biết user đang ở đâu không?**  
Không. Đừng dùng cho authorization, thuế, residency hoặc giấy phép nội dung.

**20. Làm sao kiểm chứng ứng dụng thật?**  
Kiểm tra parser, matching, translation catalog, response header và cache behavior; test demo chỉ xác nhận một tập hành vi API.

## 18. Kết luận và tài liệu chuẩn còn áp dụng

Để trao đổi metadata ngôn ngữ bền vững giữa các hệ thống:

1. **Dùng BCP 47 tag** như `vi-VN`, `sr-Latn-RS`, `zh-Hant-TW`.
2. **Serialize bằng `Locale.toLanguageTag()`**, không dùng `Locale.toString()`.
3. **Tách parse và validation:** `forLanguageTag` tolerant; `Locale.Builder.setLanguageTag` strict syntax, nhưng chưa thay registry/allowlist checks.
4. **Phân biệt tag và range:** `Content-Language` mô tả ngôn ngữ nội dung, `Accept-Language` cung cấp priorities/ranges.
5. **Match bằng API Java 17+** như `Locale.LanguageRange.parse`, `Locale.lookupTag` hoặc `Locale.filterTags`, rồi chỉ phục vụ những bản dịch thực tế có sẵn.
6. **Có fallback rõ** và không dùng language preference làm dữ liệu phân quyền.
7. **Đừng nhầm ngôn ngữ với encoding/Unicode normalization/timezone/quốc gia**.
8. **Dùng RFC 5646, RFC 4647, RFC 9110 và IANA registry** làm chuẩn để kiểm tra semantics.

### Tài liệu chính thức

- [Oracle Java SE 17 — `Locale`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `toLanguageTag`, `forLanguageTag`, `lookupTag`, `filterTags`.
- [Oracle Java SE 17 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setLanguageTag` và `IllformedLocaleException`.
- [Oracle Java SE 17 — `Locale.LanguageRange`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html): `parse` và language priority lists.
- [Oracle Java SE 17 — `IllformedLocaleException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IllformedLocaleException.html): exception khi cú pháp tag sai.
- [RFC 5646 — Tags for Identifying Languages (BCP 47)](https://www.rfc-editor.org/rfc/rfc5646): cấu trúc language tags, registry, script/region/variant/extensions/private-use.
- [RFC 4647 — Matching of Language Tags (BCP 47)](https://www.rfc-editor.org/rfc/rfc4647): matching, lookup và filtering.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `8.5 Content-Language`, `12.5.4 Accept-Language`, `12.4.2 Quality Values` và `Vary`.
- [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry): dữ liệu subtag đã được đăng ký và preferred values.
- [Unicode UTS #35 — Locale Data Markup Language](https://unicode.org/reports/tr35/): Unicode locale extensions và cách trao đổi locale preferences.
- [Oracle Java SE 17 — `Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization là chức năng riêng, không phải language tagging.
