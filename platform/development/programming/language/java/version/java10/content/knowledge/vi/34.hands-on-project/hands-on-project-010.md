# Java 10 — Thực hành tổng hợp: kiểm thử mã hóa biểu mẫu có dữ liệu tiếng Việt

## 1. Mục tiêu bài thực hành

Khi người dùng nhập **“Nguyễn Văn An”**, **“cà phê sữa đá”**, **“Đà Nẵng”** hoặc các chuỗi có dấu, emoji, khoảng trắng và ký tự đặc biệt vào một HTML form, dữ liệu cần được chuyển thành chuỗi byte theo **bộ mã thống nhất** để gửi qua HTTP. Một lỗi rất thường gặp là server nhận được tên thành ký tự lỗi, dấu `+` bị biến thành dấu cách, hoặc giá trị chứa `&` bị tách thành hai tham số.

Bài này thực hành đúng định dạng **`application/x-www-form-urlencoded`** cùng **UTF-8**, kiểm thử phép **encode → decode → so sánh kết quả** bằng Java, sau đó xây dựng một HTTP POST **chạy hoàn toàn trên loopback `127.0.0.1`** để kiểm tra dữ liệu tiếng Việt được gửi/nhận đúng.

Đây là kiến thức **vẫn còn áp dụng trên Java hiện đại**. Điểm gắn với Java 10 là hai overloads được thêm từ **Java 10**:

```java
URLEncoder.encode(String value, Charset charset);
URLDecoder.decode(String value, Charset charset);
```

Hai dòng trên là **chữ ký API minh họa**, không phải Java statements hoàn chỉnh. Trong code thật ta gọi:

```java
URLEncoder.encode(text, StandardCharsets.UTF_8);
URLDecoder.decode(encoded, StandardCharsets.UTF_8);
```

Sử dụng `Charset` tường minh giúp tránh phụ thuộc vào default charset của hệ điều hành/JVM. Dù Java các bản mới có default charset tiến gần UTF-8, **truyền explicit `StandardCharsets.UTF_8` vẫn là cách bảo đảm protocol đúng và dễ review**.

### Sau bài này bạn sẽ làm được

1. Giải thích từng bước biến chuỗi tiếng Việt thành UTF-8 bytes và `%HH`.
2. Dùng đúng `URLEncoder.encode(..., StandardCharsets.UTF_8)` và `URLDecoder.decode(..., StandardCharsets.UTF_8)`.
3. Phân biệt `application/x-www-form-urlencoded` với URL path, URI và query syntax nói chung.
4. Kiểm tra `space → +` và `literal + → %2B`.
5. Kiểm tra đúng các ký tự `&`, `=`, `%`, dấu cách không ngắt, xuống dòng CRLF và emoji.
6. Bảo toàn **nhiều trường trùng tên**, thứ tự tham số, khóa tiếng Việt và giá trị rỗng.
7. Hiểu Unicode **NFC/NFD**, vì sao hai chuỗi trông giống nhau chưa chắc có bytes giống nhau.
8. Bắt lỗi escape `%` thiếu/không hợp lệ và phân biệt với lỗi **UTF-8 bytes không hợp lệ**.
9. Tránh giải mã hai lần với `URI.getQuery()`.
10. Gửi một form POST qua `HttpClient` và xử lý bằng `HttpServer` trong môi trường test Java 17+.
11. Viết assertions tin cậy, có cả positive và negative tests.
12. Tổ chức form encoding trong ứng dụng mà không làm yếu validation, logging hoặc bảo mật.

**Special Note:** ví dụ dùng các API còn hiện hành. `URLEncoder` và `URLDecoder` overload với `Charset` có từ Java 10; `java.net.http.HttpClient` xuất hiện dạng chính thức từ Java 11 nên được dùng trong bài kiểm thử Java 17+, **không gán nhầm HttpClient là API chuẩn Java 10**.

## 2. `application/x-www-form-urlencoded` chính xác là gì?

Đây là định dạng lâu đời nhưng vẫn rất phổ biến của các HTML forms. Một form gồm **danh sách có thứ tự các cặp tên/giá trị**.

Ví dụ dữ liệu logic:

| Tên trường | Giá trị |
|---|---|
| `họ tên` | `Nguyễn Văn An` |
| `món` | `cà phê sữa đá` |
| `tag` | `Java` |
| `tag` | `Tiếng Việt` |

Khi biểu diễn theo định dạng này:
- **Tên trường** và **giá trị trường** được encode **riêng biệt**;
- Dùng `=` ngăn tên với giá trị đã encode;
- Dùng `&` ngăn các cặp;
- Dùng `+` cho dấu cách ASCII U+0020 trong dữ liệu;
- Các byte không thuộc nhóm được phép giữ nguyên thành `%HH`;
- UTF-8 là charset được khuyến nghị/sử dụng để liên thông.

Dạng trừu tượng:

```text
encodedName1=encodedValue1&encodedName2=encodedValue2
```

Một chi tiết quan trọng từ **WHATWG URL Standard**: `application/x-www-form-urlencoded` được định nghĩa trên **danh sách các tuples name/value**, vì vậy **các tên bị lặp phải được bảo toàn** nếu ngữ nghĩa ứng dụng cần chúng.

**Không nên** parse thẳng form bằng `Map<String, String>` nếu dữ liệu có thể gồm nhiều giá trị cùng key, như checkbox group hay danh sách `tag`.

## 3. Điểm mới Java 10: overload nhận `Charset`

Trước khi có overload mới, ứng dụng Java có thể gọi:

```java
URLEncoder.encode(text, "UTF-8");
URLDecoder.decode(encoded, "UTF-8");
```

Cặp overload trên vẫn tồn tại, nhưng tham số charset là **String**, và phương thức có thể khai báo `UnsupportedEncodingException`.

Java 10 bổ sung:

```java
URLEncoder.encode(text, StandardCharsets.UTF_8);
URLDecoder.decode(encoded, StandardCharsets.UTF_8);
```

Ưu điểm:
- Không phải viết literal tên bộ mã và không gặp lỗi gõ `"UTF8-X"`;
- Không phải xử lý checked exception chỉ vì tên charset có sẵn;
- Dễ kiểm thử và đọc code;
- Giữ ý định protocol **UTF-8** rõ ràng.

### 3.1. Đừng dùng overload không khai báo charset

Tránh:

```java
// Anti-pattern: default charset phụ thuộc môi trường
URLEncoder.encode(text);
URLDecoder.decode(encoded);
```

Các overload một đối số là **deprecated** vì phụ thuộc default encoding, nên kết quả có thể khác nhau theo môi trường và không phù hợp với hệ thống cần định dạng giao tiếp rõ ràng.

### 3.2. Không cần tự cài bảng mã Việt Nam

`StandardCharsets.UTF_8` hỗ trợ toàn bộ Unicode, bao gồm:
- Dấu tiếng Việt: `ă â ê ô ơ ư đ`;
- Chữ có dấu tổ hợp: `ễ ắ ộ ỳ`;
- Ký tự Trung/Nhật/Hàn khi cùng form;
- Emoji và ký tự ngoài BMP, ví dụ `🇻🇳`.

**Không** chuyển tiếng Việt sang ASCII không dấu để “né lỗi encoding”, trừ khi business requirement có một trường dữ liệu riêng cho dạng không dấu.

## 4. Cơ chế UTF-8 → phần trăm `%HH`

`URLEncoder.encode(String, UTF_8)` trước hết biểu diễn những ký tự cần escape bằng **UTF-8 bytes**, sau đó mỗi byte cần encode được viết thành dấu `%` và **hai ký tự hexadecimal**.

Ví dụ `ễ` trong từ `Nguyễn`:
- UTF-8 là ba bytes `E1 BB 85`;
- Form-encoded representation là **`%E1%BB%85`**.

Tương tự:
- `ă` → UTF-8 `C4 83` → `%C4%83`;
- Space U+0020 → `+` trong form encoding;
- `+` trong dữ liệu → `%2B`.

Bởi vậy:

```text
Input:    Nguyễn Văn An
Encoded:  Nguy%E1%BB%85n+V%C4%83n+An
Decoded:  Nguyễn Văn An
```

**Đây là kết quả thực nghiệm trên OpenJDK 24.0.2**, và phù hợp cách form encoding dùng UTF-8.

### 4.1. Mỗi `%HH` là một byte, không phải một ký tự Unicode

Ví dụ `ễ` được encode thành **ba chuỗi `%HH`** vì ba UTF-8 bytes. Không suy rằng một ký tự tiếng Việt luôn thành đúng một `%XX`.

Khi decode, `URLDecoder` gom các byte percent-encoded phù hợp rồi dùng `UTF_8` để tái tạo chuỗi Unicode.

### 4.2. Encoding làm tăng kích thước dữ liệu

Một chuỗi 10 ký tự tiếng Việt có thể chứa hơn 10 bytes trong UTF-8 và dài hơn nhiều trong form body sau khi percent-encode.

Đừng giới hạn form theo số **ký tự hiển thị** rồi suy ra giới hạn số **bytes gửi qua HTTP**. Cần xét:
- `String.length()` trong Java đếm UTF-16 code units;
- UTF-8 tính theo số bytes;
- Percent-encoded ASCII body có thể dài gấp ba mỗi byte cần escape;
- Emoji có thể dùng bốn UTF-8 bytes và thành bốn `%HH`.

Trong production, giới hạn **request body bytes**, số lượng fields và length của từng value theo chính sách server.

## 5. Những ký tự dễ gây lỗi

| Dữ liệu đầu vào | Form encoded UTF-8 | Ý nghĩa |
|---|---|---|
| `a b` | `a+b` | Space U+0020 đổi thành `+` |
| `a+b` | `a%2Bb` | Plus nguyên gốc bắt buộc escape |
| `a&b` | `a%26b` | `&` không được chia nhầm field |
| `x=1` | `x%3D1` | `=` trong value là dữ liệu |
| `50%` | `50%25` | `%` phải escape |
| `a/b` | `a%2Fb` | Slash trong form component |
| `a?b` | `a%3Fb` | Question mark là dữ liệu |
| `a#b` | `a%23b` | Dấu thăng là dữ liệu |
| `a@b` | `a%40b` | At sign |
| `a\rb` | `a%0Db` | CR khi giá trị thực chứa CR |
| `a\nb` | `a%0Ab` | LF khi giá trị thực chứa LF |
| `a\r\nb` | `a%0D%0Ab` | CRLF khi giá trị thực chứa CRLF |
| `*` | `*` | Nằm trong nhóm được URLEncoder giữ nguyên |
| `~` | `%7E` | URLEncoder form-encodes dấu ~ |
| `a b` (NBSP U+00A0) | `a%C2%A0b` | Không phải dấu cách U+0020 |

Lưu ý các ký hiệu `\n` và `\r` ở bảng là **escape notation**; code thật phải sử dụng `"\n"` hoặc `"\r\n"` để tạo control characters.

### 5.1. Space vs plus

Đây là quy tắc quan trọng nhất:

```text
Dữ liệu "a b"  --> "a+b"   --> decode --> "a b"
Dữ liệu "a+b"  --> "a%2Bb" --> decode --> "a+b"
```

Nếu developer gửi **dấu `+` thô** khi muốn biểu diễn plus trong value, server áp dụng form decoding sẽ hiểu nó là **space**.

Không dùng `replace("+", " ")` rồi tự decode phần còn lại không theo chuẩn; dùng `URLDecoder.decode(..., UTF_8)` trên **mỗi value được tách đúng**.

### 5.2. Dấu `&` và `=`

Một giá trị `"a+b & x=1%"` cần được encode thành chuỗi có những đoạn:

```text
a%2Bb+%26+x%3D1%25
```

Nếu ghép thẳng vào:

```text
note=a+b & x=1%
```

bộ phân tích form có thể:
- Biến `+` thành space;
- Xem `&` là dấu phân cách trường;
- Xem `=` là ngăn tên/giá trị của một trường khác;
- Hiểu `%` thiếu 2 chữ hex là escape lỗi.

**Nguyên tắc:** encode **tên** và **giá trị** riêng, sau đó mới ghép các ký tự phân cách `=` và `&`.

## 6. Hàm tiện ích hoàn chỉnh — `FormCodec.java`

Để tái sử dụng và tránh lỗi ghép chuỗi thủ công, xây dựng `FormCodec` có:
- `encode(String)` và `decode(String)` dùng UTF-8;
- `encodePairs(List<Pair>)` giữ nguyên thứ tự các cặp và tên trùng;
- `decodePairs(String)` tách `&` trước, rồi chỉ lấy dấu `=` **đầu tiên** trong từng cặp;
- Giữ những giá trị rỗng;
- Từ chối percent escape không hợp lệ thông qua `URLDecoder`.

Lưu tệp **`FormCodec.java`**:

```java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public final class FormCodec {
    private FormCodec() {}

    public record Pair(String name, String value) {}

    public static String encode(String value) {
        return URLEncoder.encode(
                Objects.requireNonNull(value),
                StandardCharsets.UTF_8);
    }

    public static String decode(String value) {
        return URLDecoder.decode(
                Objects.requireNonNull(value),
                StandardCharsets.UTF_8);
    }

    public static String encodePairs(List<Pair> fields) {
        StringJoiner joiner = new StringJoiner("&");
        for (Pair field : Objects.requireNonNull(fields)) {
            joiner.add(
                    encode(field.name()) + "=" +
                    encode(field.value()));
        }
        return joiner.toString();
    }

    public static List<Pair> decodePairs(String body) {
        List<Pair> fields = new ArrayList<>();
        for (String part :
                Objects.requireNonNull(body).split("&", -1)) {
            if (part.isEmpty()) {
                continue;
            }

            int separator = part.indexOf('=');
            String name = separator < 0
                    ? part
                    : part.substring(0, separator);
            String value = separator < 0
                    ? ""
                    : part.substring(separator + 1);

            fields.add(new Pair(
                    decode(name),
                    decode(value)));
        }
        return List.copyOf(fields);
    }
}
```

### 6.1. Vì sao dùng `record Pair`?

`record` cung cấp `equals`/`hashCode` theo giá trị. Nhờ vậy có thể kiểm thử trực tiếp:

```java
decodedPairs.equals(originalPairs)
```

**`record` được chuẩn hóa từ Java 16**, không phải Java 10. Bài thực hành yêu cầu Java 17+ nên dùng record là hợp lệ và hiện đại. Nếu bạn cần mã Java 10 đúng phiên bản ngôn ngữ, thay record bằng class có constructor, getters và `equals`.

### 6.2. Vì sao trả về `List<Pair>` mà không phải `Map<String,String>`?

Vì HTML forms có thể có nhiều trường tên `tag`:

```text
tag=Java&tag=Ti%E1%BA%BFng+Vi%E1%BB%87t
```

`List<Pair>` giữ đủ hai occurrences và thứ tự. Chuyển sang `Map<String,String>` bằng `put` có thể làm mất một giá trị.

### 6.3. Quy tắc parse

Đối với một phần tử:

```text
key=a%3Db
```

Hàm nhận:
- name raw = `key`;
- value raw = `a%3Db`;
- value decoded = `a=b`.

Với:

```text
flag
```

Hàm coi:
- name = `flag`;
- value = empty string.

Với chuỗi `&` liên tiếp tạo đoạn rỗng, hàm **bỏ qua đoạn rỗng**, phù hợp hướng tiếp cận phổ biến của form parser. Nếu ứng dụng cần phân biệt chính xác mọi tình huống “không có equals” và “equals rỗng”, phải lưu thêm metadata thay vì chỉ record Pair.

### 6.4. Giới hạn bảo mật của `FormCodec` mẫu

Hàm mẫu phục vụ học và test; nó **chưa**:
- Giới hạn tổng kích thước request;
- Giới hạn số cặp form;
- Giới hạn độ dài tên/giá trị;
- Kiểm tra content type / charset từ request;
- Kiểm tra authentication/authorization;
- Áp dụng domain validation;
- Từ chối byte sequences UTF-8 lỗi ở chế độ strict.

Khi đưa vào server thật, hãy đặt các giới hạn **trước khi** đọc toàn bộ body, dùng framework HTTP parser đáng tin và kiểm soát validation sau khi decode.

## 7. Chương trình kiểm thử 1 — dữ liệu tiếng Việt và ký tự đặc biệt

Tạo tệp **`VietnameseFormDemo.java`**:

```java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.List;

public class VietnameseFormDemo {
    public static void main(String[] args) {
        String original = "Nguyễn Văn An";
        String encoded =
                URLEncoder.encode(
                        original, StandardCharsets.UTF_8);
        String decoded =
                URLDecoder.decode(
                        encoded, StandardCharsets.UTF_8);

        System.out.println("encodedName=" + encoded);
        System.out.println("decodedName=" + decoded);
        System.out.println("roundTrip=" + original.equals(decoded));

        List<FormCodec.Pair> originalFields = List.of(
                new FormCodec.Pair(
                        "họ tên", "Nguyễn Văn An"),
                new FormCodec.Pair(
                        "món", "cà phê sữa đá"),
                new FormCodec.Pair("tag", "Java"),
                new FormCodec.Pair("tag", "Tiếng Việt"),
                new FormCodec.Pair(
                        "ký tự", "a+b & x=1%"),
                new FormCodec.Pair("trống", ""),
                new FormCodec.Pair(
                        "dòng", "dòng 1\r\ndòng 2"),
                new FormCodec.Pair(
                        "emoji", "☕🇻🇳"));

        String body =
                FormCodec.encodePairs(originalFields);
        List<FormCodec.Pair> parsed =
                FormCodec.decodePairs(body);

        System.out.println("fields=" + parsed.size());
        System.out.println("pairsRoundTrip=" +
                parsed.equals(originalFields));
        System.out.println("repeatedTags=" +
                parsed.stream()
                        .filter(p -> p.name().equals("tag"))
                        .count());

        System.out.println("encodedPlus=" +
                body.contains("a%2Bb"));
        System.out.println("encodedAmpersand=" +
                body.contains("%26"));
        System.out.println("encodedEquals=" +
                body.contains("%3D"));
        System.out.println("encodedPercent=" +
                body.contains("%25"));
        System.out.println("encodedCRLF=" +
                body.contains("%0D%0A"));

        System.out.println("formSpaceIsPlus=" +
                URLEncoder.encode(
                        "a b", StandardCharsets.UTF_8)
                        .equals("a+b"));

        System.out.println("literalPlusIsEscaped=" +
                URLEncoder.encode(
                        "a+b", StandardCharsets.UTF_8)
                        .equals("a%2Bb"));

        System.out.println("plusDecodesToSpace=" +
                URLDecoder.decode(
                        "a+b", StandardCharsets.UTF_8)
                        .equals("a b"));

        System.out.println("emptyPreserved=" +
                parsed.contains(
                        new FormCodec.Pair("trống", "")));

        String composed = "\u1EBF";
        String decomposed = "e\u0302\u0301";

        System.out.println("looksSameAfterNfc=" +
                Normalizer.normalize(
                        composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed,
                                Normalizer.Form.NFC)));

        System.out.println("rawBytesDifferent=" +
                !FormCodec.encode(composed)
                        .equals(FormCodec.encode(decomposed)));
    }
}
```

### 7.1. Biên dịch

Đặt `FormCodec.java` và `VietnameseFormDemo.java` trong cùng thư mục:

```bash
javac --release 17 -encoding UTF-8 FormCodec.java VietnameseFormDemo.java
```

Chạy:

```bash
java VietnameseFormDemo
```

### 7.2. Stdout chính xác đã kiểm chứng

Trên OpenJDK **24.0.2**, biên dịch bằng `javac --release 17`, chương trình in:

```text
encodedName=Nguy%E1%BB%85n+V%C4%83n+An
decodedName=Nguyễn Văn An
roundTrip=true
fields=8
pairsRoundTrip=true
repeatedTags=2
encodedPlus=true
encodedAmpersand=true
encodedEquals=true
encodedPercent=true
encodedCRLF=true
formSpaceIsPlus=true
literalPlusIsEscaped=true
plusDecodesToSpace=true
emptyPreserved=true
looksSameAfterNfc=true
rawBytesDifferent=true
```

### 7.3. Ý nghĩa từng nhóm assertions

- `roundTrip=true`: encode/decode với cùng UTF-8 bảo toàn tên tiếng Việt.
- `fields=8`: danh sách có tám cặp form.
- `pairsRoundTrip=true`: bảo toàn **cả name/value lẫn thứ tự và những trường trùng**.
- `repeatedTags=2`: có hai cặp `tag`.
- Các cờ `encodedPlus/Ampersand/Equals/Percent`: ký tự điều khiển cú pháp không phá cấu trúc form.
- `encodedCRLF=true`: cặp xuống dòng CR+LF của trường được mã hóa đúng.
- `emptyPreserved=true`: một empty field không bị mất.
- `looksSameAfterNfc=true` và `rawBytesDifferent=true`: Unicode normalization là một mối quan tâm khác với đúng charset.

## 8. Unicode tiếng Việt: NFC và NFD

**UTF-8 không tự chuẩn hóa Unicode.**

Hai chuỗi có thể hiển thị giống nhau trên màn hình:
- Ký tự tiền tổ hợp **`ế`** (U+1EBF);
- Dãy **`e` + combining circumflex U+0302 + combining acute U+0301**.

Cả hai có thể hiển thị trông giống `ế`, nhưng là **hai chuỗi mã code points khác nhau**, nên:
- Java `String.equals` có thể trả false;
- UTF-8 bytes khác nhau;
- `URLEncoder.encode(..., UTF_8)` cho chuỗi percent encoding khác nhau.

Trong ví dụ:
 
```java
String composed = "\u1EBF";
String decomposed = "e\u0302\u0301";
```

Khi dùng:

```java
Normalizer.normalize(text, Normalizer.Form.NFC)
```

hai chuỗi tương ứng có thể được canonical-normalize thành dạng NFC giống nhau.

### 8.1. Encoding đúng không giải quyết hết vấn đề tìm kiếm/tên người

Nếu yêu cầu nghiệp vụ so sánh các tên được nhập từ nhiều nguồn, cần quyết định **chính sách normalization**:
- Lưu dữ liệu gốc hay dạng chuẩn hóa?
- Search có cần accent-insensitive matching không?
- Tên hiển thị có giữ chính tả gốc không?
- Có được chuẩn hóa NFKC hay có rủi ro thay ý nghĩa?
- Có yêu cầu audit field raw input?

**Không tự bỏ dấu tiếng Việt** hoặc dùng `Normalizer.Form.NFKC` cho mọi field mà chưa có domain rules; normalization có thể thay cách một số ký tự được biểu diễn.

### 8.2. Round-trip test đúng điều gì?

`decode(encode(value, UTF_8), UTF_8).equals(value)` kiểm tra rằng form encoding không làm mất nội dung chuỗi Java **có Unicode hợp lệ** và đang được xử lý trong cùng charset.

Nó **không** yêu cầu hai chuỗi Unicode tương đương về mặt thị giác phải có cùng encoding. Việc canonical normalization là **một bước nghiệp vụ riêng**.

### 8.3. Emoji và surrogate pairs

Java `String` lưu text dưới UTF-16 code units. Ký tự ngoài BMP dùng surrogate pairs, nhưng UTF-8 có biểu diễn riêng. Ví dụ `"☕🇻🇳"` qua `URLEncoder` và `URLDecoder` đã được kiểm thử bảo toàn giá trị trong `pairsRoundTrip=true`.

Không viết vòng lặp tự duyệt từng `char` rồi percent-encode từng đơn vị UTF-16 như một ký tự Unicode riêng; hãy để `URLEncoder` làm việc với charset.

## 9. Chương trình kiểm thử 2 — đầu vào lỗi, dấu `=` và trường không có giá trị

Form decoder cần nhận diện **escape sequences không hợp lệ**.

Tạo tệp **`MalformedFormDemo.java`**:

```java
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class MalformedFormDemo {
    public static void main(String[] args) {
        for (String value :
                new String[] {"%", "%A", "%ZZ"}) {
            try {
                URLDecoder.decode(
                        value, StandardCharsets.UTF_8);
                System.out.println(
                        "unexpectedAccepted=" + value);
            } catch (IllegalArgumentException expected) {
                System.out.println("rejected=" + value);
            }
        }

        String invalidUtf8 = URLDecoder.decode(
                "%C3%28", StandardCharsets.UTF_8);
        System.out.println("invalidUtf8HasReplacement=" +
                invalidUtf8.contains("\uFFFD"));

        System.out.println("onlyFirstEqualsIsDelimiter=" +
                FormCodec.decodePairs("x=a%3Db").equals(
                    java.util.List.of(
                        new FormCodec.Pair("x", "a=b"))));

        System.out.println("nameOnlyHasEmptyValue=" +
                FormCodec.decodePairs("flag").equals(
                    java.util.List.of(
                        new FormCodec.Pair("flag", ""))));
    }
}
```

Biên dịch và chạy cùng `FormCodec.java`:

```bash
javac --release 17 -encoding UTF-8 FormCodec.java MalformedFormDemo.java
java MalformedFormDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

```text
rejected=%
rejected=%A
rejected=%ZZ
invalidUtf8HasReplacement=true
onlyFirstEqualsIsDelimiter=true
nameOnlyHasEmptyValue=true
```

### 9.1. Phân biệt hai loại lỗi

**Lỗi 1 — phần trăm không hợp lệ:**

- `%`: thiếu hai hex digits;
- `%A`: escape chưa đủ hai hex digits;
- `%ZZ`: hai ký tự không phải hexadecimal.

Trong overload này, chúng bị `URLDecoder` từ chối bằng `IllegalArgumentException` trên JDK đã kiểm tra. Oracle docs cũng tài liệu hóa `IllegalArgumentException` đối với malformed escapes.

**Lỗi 2 — bytes percent-encoded không tạo UTF-8 hợp lệ:**

```text
%C3%28
```

Đây là phần trăm hợp lệ về mặt cú pháp (`C3` và `28` đều hex), nhưng dãy bytes không tạo một UTF-8 sequence đúng. Oracle `URLDecoder.decode(String, Charset)` tài liệu hóa việc thay thế **erroneous bytes** bằng replacement character của charset. Trong thử nghiệm, kết quả có **U+FFFD** nên `invalidUtf8HasReplacement=true`.

**Không được giả định `URLDecoder` luôn ném exception cho mọi lỗi encoding UTF-8.** Nếu ứng dụng có chính sách bắt buộc UTF-8 strict, cần kiểm tra **raw bytes** bằng `CharsetDecoder` với `CodingErrorAction.REPORT` ở đúng giai đoạn, hoặc dùng một form parser có chế độ reject malformed inputs.

### 9.2. Vì sao kiểm tra byte-level quan trọng?

Nếu hệ thống thực hiện kiểm tra an ninh trên raw bytes, rồi một tầng khác decode bằng replacement semantics, có thể xuất hiện **bất nhất giữa các tầng**. Hãy quyết định rõ:
- Chấp nhận replacement U+FFFD hay từ chối toàn bộ request?
- Có cảnh báo/audit input lỗi không?
- Có giới hạn ký tự control không?
- Có cần Unicode normalization không?

Không tiếp tục xử lý dữ liệu **mơ hồ về cách decode** trong một chức năng nhạy cảm về bảo mật.

## 10. Không decode toàn bộ URL như một form value

**`URLEncoder` không phải bộ mã hóa URL path tổng quát.** Tên API dễ làm người mới hiểu nhầm.

`URLEncoder.encode` được đặc tả cho **`application/x-www-form-urlencoded`**. Nó mã hóa space thành `+` và có tập ký tự được giữ nguyên/escape theo quy tắc riêng của form.

Trong khi đó, URL gồm nhiều thành phần:

```text
scheme://host:port/path?name=value&tag=...
                  ^      ^             ^
                 path   query          form-like parameters (if server uses form rules)
```

Mỗi thành phần có quy tắc biểu diễn riêng. Không lấy nguyên URL `https://.../?q=...` đưa qua `URLEncoder.encode` rồi dùng nó như một URL hoàn chỉnh; dấu `:`, `/`, `?` có thể bị encode và làm sai cấu trúc.

### 10.1. Khi nào có thể dùng URLEncoder cho query?

Khi **từng query parameter name/value** được server diễn giải theo form decoding, có thể dùng:

```java
String q = URLEncoder.encode(
        "Nguyễn Văn An", StandardCharsets.UTF_8);
URI uri = URI.create(
        "https://example.invalid/search?q=" + q);
```

Đây là **mảnh code** trong method có imports `URI` và `URLEncoder`; `example.invalid` là domain minh họa, không yêu cầu kết nối mạng.

Nhưng **không** dùng form encoding như phương pháp mặc định để mã hóa từng **path segment** hoặc fragment vì space/plus/percent-encode semantics khác nhau.

### 10.2. `getRawQuery()` khác `getQuery()`

`java.net.URI.getRawQuery()` giữ nguyên percent-encoded text của query. `URI.getQuery()` trả về query đã giải mã theo quy tắc URI cho percent escapes.

Nếu sau `getQuery()` lại gọi `URLDecoder`, bạn có thể **giải mã hai lần** và biến dấu `+` thành space.

Chương trình kiểm thử sau làm rõ đúng tình huống đó.

## 11. Chương trình kiểm thử 3 — biên giới URI và form decoding

Tạo **`UriFormBoundaryDemo.java`**:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriFormBoundaryDemo {
    public static void main(String[] args) {
        String original = "a+b";
        URI uri = URI.create(
                "https://example.invalid/search?q=" +
                URLEncoder.encode(
                        original, StandardCharsets.UTF_8));

        String rawQuery = uri.getRawQuery();
        String decodedUriQuery = uri.getQuery();

        System.out.println("rawQuery=" + rawQuery);
        System.out.println("uriQuery=" + decodedUriQuery);

        System.out.println("formDecodedCorrect=" +
                URLDecoder.decode(
                    rawQuery.substring(2),
                    StandardCharsets.UTF_8));

        System.out.println("doubleDecodedIncorrect=" +
                URLDecoder.decode(
                    decodedUriQuery.substring(2),
                    StandardCharsets.UTF_8));

        System.out.println("nbspAsPercent=" +
                URLEncoder.encode(
                        "a\u00A0b", StandardCharsets.UTF_8)
                        .equals("a%C2%A0b"));

        System.out.println("asteriskUnescaped=" +
                URLEncoder.encode(
                        "*", StandardCharsets.UTF_8)
                        .equals("*"));

        System.out.println("tildePercentEncoded=" +
                URLEncoder.encode(
                        "~", StandardCharsets.UTF_8)
                        .equals("%7E"));

        System.out.println("singleLF=" +
                URLEncoder.encode(
                        "a\nb", StandardCharsets.UTF_8)
                        .equals("a%0Ab"));

        System.out.println("crlf=" +
                URLEncoder.encode(
                        "a\r\nb", StandardCharsets.UTF_8)
                        .equals("a%0D%0Ab"));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 UriFormBoundaryDemo.java
java UriFormBoundaryDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

```text
rawQuery=q=a%2Bb
uriQuery=q=a+b
formDecodedCorrect=a+b
doubleDecodedIncorrect=a b
nbspAsPercent=true
asteriskUnescaped=true
tildePercentEncoded=true
singleLF=true
crlf=true
```

### 11.1. Giải thích phép giải mã hai lần

`original = "a+b"`.

Sau form encoding:
- `a+b` → `a%2Bb`;
- URL query = `q=a%2Bb`.

`URI.getRawQuery()` giữ `q=a%2Bb`. Tách `q=` rồi gọi `URLDecoder.decode(...,UTF_8)` cho **`a+b`**, chính xác.

`URI.getQuery()` đã giải mã `%2B` thành ký tự plus `+`. Nếu lại gọi `URLDecoder`, plus bị hiểu là **space** → **`a b`**, sai so với dữ liệu gốc.

**Cách làm đúng:** nếu tự parse form-like query, bắt đầu từ **`getRawQuery()`**, tách `&`/`=` và decode **một lần** ở đúng lớp. Tốt hơn, dùng URI/query parser của framework đáng tin, tránh trộn APIs có quy tắc decoding khác nhau.

### 11.2. Những ký tự nhìn như space

NBSP U+00A0 là **no-break space**, không phải ASCII U+0020, nên:

```text
"a b"   --> "a+b"
"a b"   --> "a%C2%A0b"
```

Nếu business logic cần gộp các loại whitespace thành một kiểu duy nhất, đó là **validation/normalization policy**, không phải chức năng mặc định của `URLEncoder`.

### 11.3. `\n` và `\r\n`

Java API `URLEncoder` mã hóa **chuỗi nhận được**:
- `"a\nb"` → `a%0Ab`;
- `"a\r\nb"` → `a%0D%0Ab`.

Khi trình duyệt submit HTML form, những bước tạo entry list/chuẩn hóa line breaks của HTML có thể dẫn đến **CRLF** theo HTML form submission rules. Không tự suy rằng `URLEncoder` sẽ tự chuyển mọi LF sang CRLF trước khi encode. Test cả **dữ liệu đầu vào** và **bản form body thực tế**.

## 12. Định dạng HTML form và cách gửi

Một form HTML có thể viết:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Kiểm thử biểu mẫu tiếng Việt</title>
</head>
<body>
  <form action="/submit"
        method="post"
        enctype="application/x-www-form-urlencoded"
        accept-charset="UTF-8">
    <label for="full-name">Họ tên</label>
    <input id="full-name" name="họ tên"
           value="Nguyễn Văn An">

    <label for="note">Ghi chú</label>
    <textarea id="note" name="ghi chú">cà phê &amp; bánh mì</textarea>

    <label for="tag">Thẻ</label>
    <select id="tag" name="tag">
      <option value="Tiếng Việt">Tiếng Việt</option>
      <option value="Java">Java</option>
    </select>

    <button type="submit">Gửi</button>
  </form>
</body>
</html>
```

Đây là **ví dụ HTML minh họa**, không phải trang đã chạy trong browser của bài. Cú pháp:
- `method="post"`: dữ liệu form nằm trong HTTP request body;
- `enctype="application/x-www-form-urlencoded"`: chọn cách serialize pairs;
- `accept-charset="UTF-8"`: thể hiện dự định dùng UTF-8;
- `<meta charset="utf-8">`: giúp browser hiểu file HTML;
- Các trường có `name`: name được gửi cùng value;
- `&amp;` trong HTML source là **HTML entity**, trình duyệt hiển thị ký tự `&`.

### 12.1. Không coi giá trị trong HTML source là form body đã encode

Trong source:

```html
<textarea name="ghi chú">cà phê &amp; bánh mì</textarea>
```

Trình duyệt đọc text thành **`cà phê & bánh mì`** trước, sau đó form serializer mới chuyển thành các bytes/`%HH`. Nếu developer tự percent-encode sẵn giá trị rồi browser lại encode form, có thể xảy ra **double encoding**.

### 12.2. GET và POST

**GET form** thường đưa form-encoded params vào query string:

```text
/search?h%E1%BB%8D+t%C3%AAn=Nguy%E1%BB%85n+V%C4%83n+An
```

**POST form** đưa params vào body theo media type `application/x-www-form-urlencoded`.

Cả hai cần quy tắc encode/decode nhất quán. Tuy nhiên:
- GET query có thể bị lưu trong browser history, proxy/CDN logs, server logs, analytics và referrer tùy hoàn cảnh.
- Không gửi passwords, tokens, OTP hay dữ liệu nhạy cảm trong query chỉ để thuận tiện.
- POST body cũng không tự bảo mật; vẫn cần HTTPS, auth, CSRF defenses khi phù hợp, logs được kiểm soát và input validation.

`Content-Type` mô tả body của POST, còn URL query là một phần của URL request target; đừng nhầm hai vị trí.

## 13. HTTP Content-Type và charset

Với POST kiểu này, header thường có dạng:

```http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Đây là **một dòng HTTP header mẫu**, không phải chương trình Java.

Trong `HttpClient`:

```java
.header("Content-Type",
        "application/x-www-form-urlencoded; charset=UTF-8")
.POST(HttpRequest.BodyPublishers.ofString(
        formBody, StandardCharsets.UTF_8))
```

Hai đoạn trên là **mảnh của builder chain** trong chương trình đầy đủ sắp tới.

### 13.1. Vì sao phải đồng nhất charset?

Encode và decode phải dùng cùng một charset:

```text
Java String "Nguyễn"
      |
      v
UTF-8 bytes
      |
      v
Percent encoding
      |
      v
POST body / Query
      |
      v
Percent decoding
      |
      v
UTF-8 decode
      |
      v
Java String "Nguyễn"
```

Nếu một bên cố giải mã bytes UTF-8 theo Latin-1 hoặc charset khác, dấu tiếng Việt có thể biến thành mojibake như `Nguyá»…n`. Nguyên nhân là **mis-decoding bytes**, không phải bản thân các dấu tiếng Việt không được URI hỗ trợ.

### 13.2. Java `HttpClient` không có từ Java 10 ở dạng API chuẩn

`java.net.http.HttpClient` và `HttpRequest` được chuẩn hóa trong **Java 11** (JEP 321). Vì Special Note yêu cầu kiến thức hiện còn áp dụng, ví dụ integration dùng **JDK 17+**; phần form codec vẫn tập trung vào overload `Charset` ra đời từ **Java 10**.

Nếu một project buộc phải chạy runtime Java 10, ví dụ HttpClient chính thức ở đây **không thể biên dịch bằng `--release 10`**. Đây là giới hạn phiên bản được nêu rõ, không phải lời khuyên dùng Java 10 cũ cho sản xuất.

## 14. Chương trình kiểm thử 4 — POST biểu mẫu tiếng Việt qua loopback

Ví dụ này tự tạo HTTP server local và HTTP client cùng một tiến trình Java:
- Server chỉ bind vào **`127.0.0.1`**, với **port động do OS cấp**;
- Client POST `application/x-www-form-urlencoded; charset=UTF-8`;
- Body bao gồm trường `họ tên`, `ghi chú` và hai trường `tag`;
- Server đọc bytes bằng UTF-8, parse bằng `FormCodec.decodePairs`;
- Server trả một chuỗi tiếng Việt dạng `text/plain; charset=UTF-8`;
- Client đối chiếu status và response.

Không truy cập một dịch vụ mạng công khai nào, không gửi dữ liệu người dùng thật.

### 14.1. Tệp `HttpFormLoopbackDemo.java`

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;

public class HttpFormLoopbackDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/submit", exchange -> {
            try {
                String method = exchange.getRequestMethod();
                String contentType = exchange.getRequestHeaders()
                        .getFirst("Content-Type");

                if (!"POST".equals(method) ||
                        contentType == null ||
                        !contentType.toLowerCase(
                                java.util.Locale.ROOT)
                            .startsWith(
                                "application/x-www-form-urlencoded")) {
                    byte[] error =
                            "Unsupported form".getBytes(
                                    StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(
                            415, error.length);
                    exchange.getResponseBody().write(error);
                    return;
                }

                String formBody = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);

                List<FormCodec.Pair> fields =
                        FormCodec.decodePairs(formBody);

                String name = fields.stream()
                        .filter(p -> p.name().equals("họ tên"))
                        .findFirst().orElseThrow().value();

                String message =
                        "Đã nhận: " + name +
                        "; fields=" + fields.size();

                byte[] response =
                        message.getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(
                        200, response.length);
                exchange.getResponseBody().write(response);
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            String form = FormCodec.encodePairs(List.of(
                    new FormCodec.Pair(
                            "họ tên", "Nguyễn Văn An"),
                    new FormCodec.Pair(
                            "ghi chú", "cà phê & bánh mì"),
                    new FormCodec.Pair("tag", "Java"),
                    new FormCodec.Pair(
                            "tag", "Tiếng Việt")));

            HttpRequest request =
                    HttpRequest.newBuilder(
                        URI.create(
                            "http://127.0.0.1:" +
                            server.getAddress().getPort() +
                            "/submit"))
                    .header(
                        "Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                    .POST(
                        HttpRequest.BodyPublishers.ofString(
                            form, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response =
                    HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("status=" +
                    response.statusCode());
            System.out.println("reply=" +
                    response.body());
            System.out.println("containsVietnamese=" +
                    response.body().contains(
                            "Nguyễn Văn An"));
        } finally {
            server.stop(0);
        }
    }
}
```

### 14.2. Biên dịch với module server của JDK

`HttpServer` là API thuộc module **`jdk.httpserver`**; nó được dùng cho demo và công cụ đơn giản, không phải một production web server thay thế framework đầy đủ.

Đặt `FormCodec.java` và `HttpFormLoopbackDemo.java` cùng thư mục:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 FormCodec.java HttpFormLoopbackDemo.java
```

Chạy:

```bash
java --add-modules jdk.httpserver HttpFormLoopbackDemo
```

### 14.3. Stdout chính xác đã kiểm chứng

OpenJDK **24.0.2**, `javac --release 17`:

```text
status=200
reply=Đã nhận: Nguyễn Văn An; fields=4
containsVietnamese=true
```

**Đây là phép thử HTTP POST thật trên loopback**, không phải mô phỏng chuỗi trả về. Server bind `127.0.0.1` ở port do hệ điều hành cấp; client kết nối tới port ấy, gửi bytes, server decode và trả tiếng Việt.

### 14.4. Vì sao test local hữu ích?

Test thuần `URLDecoder.decode(URLEncoder.encode(...))` chỉ xác minh **codec**. Một test HTTP loopback còn có thể phát hiện:
- Quên header `Content-Type`;
- Gửi request body khác với encoded string;
- Trộn charset giữa client, server và response;
- Tách query/body sai;
- Dữ liệu tiếng Việt không được chuyển thành response đúng.

Tuy nhiên, loopback vẫn không kiểm thử reverse proxy, TLS termination, HTTP server framework hoặc browser thực tế. Khi đưa ứng dụng vào production, cần integration tests ở những tầng đó.

### 14.5. Các giới hạn của demo server

Server demo:
- Không xác thực người dùng;
- Không kiểm soát CSRF;
- Dùng `readAllBytes()` mà **chưa giới hạn body size**;
- Chỉ kiểm tra `Content-Type` bằng prefix đơn giản;
- Không giới hạn số lượng trường hoặc kiểm tra schema đầy đủ;
- Không có error handler thân thiện nếu body percent escapes bị lỗi;
- Không xử lý nhiều kiểu HTTP/form hoặc request timeouts nâng cao.

**Không copy nguyên `HttpServer` handler này để làm API public production.** Trong hệ thống thật, dùng web framework đã được kiểm thử, giới hạn body/header sizes, timeouts, auth và validation.

## 15. Phân biệt dữ liệu form, query và path

| Ngữ cảnh | Ví dụ | Phương pháp |
|---|---|---|
| **Form POST body** | `name=Nguy%E1%BB%85n+V%C4%83n+An` | `URLEncoder` cho mỗi name/value |
| **Form-like query** | `?q=Nguy%E1%BB%85n+V%C4%83n+An` | Dùng query builder/parser phù hợp, tránh double-decode |
| **URL path segment** | `/users/Nguy%E1%BB%85n%20V%C4%83n` | Dùng URI/path-segment encoder, **không** form encoder |
| **URL fragment** | `#section-name` | Quy tắc của fragment, **không** lấy `URLEncoder` áp cho toàn fragment |
| **JSON body** | `{"name":"Nguyễn Văn An"}` | JSON serialization + UTF-8, không phải form encoding |
| **Multipart form** | `multipart/form-data` | Boundary + từng part, không phải `name=value&name2=value2` |

Không dùng `URLEncoder` để thay **JSON serializer** hoặc encode một **URL nguyên vẹn**. Các thành phần URL có những quy tắc reserved characters khác nhau.

### 15.1. Nếu URI đã được percent-decode?

Một số APIs/frameworks trả **decoded values**. Gọi `URLDecoder` lần hai có thể:
- Biến `%25` thành percent rồi thành escape tiếp;
- Biến literal plus thành space;
- Tạo ra slash/dot segments sau validation;
- Làm các tầng application và security parser hiểu URL khác nhau.

Cần ghi rõ tại mỗi boundary:
- Đầu vào đã được decode hay chưa?
- Áp dụng form encoding hay percent encoding chung?
- Có decode chính xác một lần không?
- Validation đã được thực hiện trên dạng nào?

## 16. Các trường hợp rỗng, lặp, không có `=` và thứ tự

`application/x-www-form-urlencoded` là danh sách **name/value pairs**, không phải một map đơn giản.

Ví dụ:

```text
tag=Java&tag=Ti%E1%BA%BFng+Vi%E1%BB%87t&empty=&flag
```

Có thể biểu diễn như:
- Pair `("tag", "Java")`;
- Pair `("tag", "Tiếng Việt")`;
- Pair `("empty", "")`;
- Pair `("flag", "")` nếu parser chọn coi trường không có `=` là value rỗng.

### 16.1. Không tự loại duplicate keys khi domain cần chúng

Multi-select, checkbox groups hoặc form động có thể tạo nhiều fields cùng `name`. Nếu code dùng:

```java
Map<String, String> map = new HashMap<>();
map.put("tag", "Java");
map.put("tag", "Tiếng Việt");
```

đây chỉ là **mảnh code minh họa**: entry thứ hai thay entry thứ nhất. Dữ liệu bị mất. Để giữ duplicates, dùng `List<Pair>` hoặc `Map<String, List<String>>` đã được framework parse đúng.

### 16.2. Empty string khác null trong domain

`name=` là một form field với value rỗng. `name` không có equals cũng được nhiều parser (và ví dụ `FormCodec`) coi là value rỗng. Nhưng **không có field `name` trong request** có thể có ý nghĩa khác.

Nên quyết định rõ:
- Field bắt buộc hay không;
- Vắng field có default không;
- Empty field có hợp lệ không;
- Whitespace-only field được xử lý thế nào;
- Có normalization trước validation hay sau validation không.

`URLEncoder` chỉ giải quyết **biểu diễn bytes**, không quyết định domain rules.

### 16.3. Thứ tự fields

WHATWG form serialization xuất entries theo thứ tự trong danh sách tuples. Khi cần bảo toàn thứ tự (ví dụ multi-value tags), hãy giữ `List<Pair>`. Không dựa vào `HashMap` để giữ insertion order; nếu dùng map, chọn cấu trúc và semantics phù hợp.

## 17. Line breaks, textarea và normalization

Trong dữ liệu Java:
- `"\n"` là Line Feed (LF);
- `"\r"` là Carriage Return (CR);
- `"\r\n"` là cặp CRLF.

Kết quả mã hóa:

```text
"a\nb"    -> a%0Ab
"a\r\nb"  -> a%0D%0Ab
```

Trình duyệt khi submit biểu mẫu theo HTML form rules có thể chuẩn hóa line breaks sang CRLF ở những bước tạo dữ liệu. Vì thế:
- Nếu input đến từ browser textarea, test actual request body;
- Nếu input là chuỗi Java tạo thủ công, `URLEncoder` encode đúng **những ký tự đang có**;
- Nếu server hoặc database đòi dạng newline cố định, xử lý normalization theo policy sau khi decode;
- Không thay toàn bộ `\n` thành `\r\n` một cách thiếu kiểm soát nếu có nguy cơ `\r\r\n`.

### 17.1. Ký tự điều khiển và header injection

Một field có thể chứa CR/LF khi decode. Không chép trực tiếp user input đã decode vào HTTP response header, email header, log line hoặc CSV mà chưa dùng encoding/validation đúng với output context.

Form encoding **không phải escaping an toàn cho HTML, SQL, HTTP headers hoặc log sinks**.

## 18. Kiểm thử charset mismatch

Tình huống:

```text
Input Unicode     "Tiếng Việt"
Encode UTF-8      bytes UTF-8
Percent-encode    ASCII %HH
Decode ISO-8859-1 các bytes ấy
Kết quả           mojibake, không phải chuỗi gốc
```

Không cần đưa legacy charset vào production code mới chỉ để kiểm thử. Thay vào đó:
1. Yêu cầu giao thức form dùng UTF-8;
2. Kiểm tra client code dùng `StandardCharsets.UTF_8`;
3. Kiểm tra server parser được cấu hình UTF-8;
4. Kiểm tra response charset;
5. Kiểm tra lưu trữ database và logs cũng hỗ trợ Unicode;
6. Có regression tests chứa các dấu tiếng Việt thực tế.

**Đừng “sửa” mojibake bằng cách bỏ dấu tên người hoặc dùng string replacement tùy ý.** Tìm nơi bytes được decode sai rồi sửa ở boundary đó.

### 18.1. Ký tự hợp lệ nhưng không thể biểu diễn trong charset cũ

Một số charsets có tập ký tự hạn chế. Khi encoding không thể biểu diễn một ký tự, encoder có thể thay thế nó tùy coding-error policy. Kết quả encode/decode roundtrip sẽ không bảo toàn Unicode.

Với UTF-8, Unicode scalar values hợp lệ được biểu diễn đầy đủ. Tuy nhiên **Java String có thể chứa unpaired surrogate**, vốn không phải Unicode scalar value hợp lệ; cần có chính sách validation nếu input đến từ tầng không đáng tin.

### 18.2. Không dùng `String.getBytes()` không charset

Tránh:

```java
byte[] bytes = value.getBytes();
```

Khi bytes là một phần của protocol, hãy dùng:

```java
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
```

Hai dòng này là **mảnh code** để minh họa lựa chọn charset. Không suy rằng default charset của tất cả JDK/platform/OS luôn ổn định trong mọi deployment.

## 19. Các mức kiểm thử: unit, property và integration

| Cấp test | Ví dụ kiểm tra | Lỗi có thể phát hiện |
|---|---|---|
| **Unit — ASCII** | `a b` ↔ `a+b` | Quy tắc space/plus |
| **Unit — Unicode** | `Nguyễn Văn An` roundtrip | UTF-8 percent encoding |
| **Unit — dấu phân cách** | `a+b & x=1%` | Mã hóa `+`/`&`/`=`/`%` |
| **Unit — pairs** | Hai trường `tag`, empty value | Parse list, duplicates |
| **Unit — Unicode normalization** | NFC vs NFD | So sánh canonical representation |
| **Negative — escape syntax** | `%`, `%A`, `%ZZ` | Từ chối malformed percent escape |
| **Negative — UTF-8 bytes** | `%C3%28` | Phân biệt replacement vs strict rejection |
| **Unit — URI boundary** | `getRawQuery` vs `getQuery` | Double-decode bugs |
| **Integration — HTTP loopback** | POST encoded form, server decode, response UTF-8 | Charset/content-type/body mismatch |
| **Integration — real framework** | Client → service → storage | Proxy, framework parser, database encodings |
| **Security** | Large input, CRLF, duplicate keys, malformed input | Resource exhaustion, parser inconsistency |

### 19.1. Property-based tests

Một invariant hữu ích:

```text
decode(encode(s, UTF_8), UTF_8) == s
```

Áp dụng cho nhiều `s` là Unicode text hợp lệ. Có thể sinh:
- Vietnamese syllables với `ă â ê ô ơ ư đ`;
- Mixed case `Đà Nẵng` và `đà nẵng`;
- Spaces ở đầu/cuối và giữa từ;
- Tabs/newlines;
- Literal reserved chars;
- Emoji và non-BMP;
- Empty strings;
- NFC/NFD variants.

Nhưng invariant trên **chưa kiểm thử**:
- Parsing nhiều pairs;
- Actual body size/content type;
- URL component mixup;
- UTF-8 malformed rejection policy;
- Server-side validation.

Nên kết hợp property-based tests với những fixed examples có expected encoding chính xác.

### 19.2. Golden tests không nên dựa vào platform default

Golden expected:

```text
Nguyễn Văn An -> Nguy%E1%BB%85n+V%C4%83n+An
```

có thể ổn định khi **Charset = UTF-8** và đúng form encoding. Không tạo golden test từ một lần `URLEncoder.encode(value)` thiếu charset trên máy developer rồi coi đó là contract giữa các platforms.

## 20. Kiểm thử form với frameworks hiện hành

Các Java web frameworks có cơ chế parse form parameters riêng. Nguyên tắc vẫn tương tự:
- Cấu hình request encoding theo UTF-8;
- Không decode lại các values framework đã decode;
- Không ép multi-valued parameters thành một string nếu domain cần danh sách;
- Kiểm tra content type, body size, validation và errors;
- Đảm bảo response content type/charset phù hợp;
- Dùng API built-in của framework khi có thể, thay vì tự viết parser `split("&")` trong production.

Ví dụ `FormCodec` trong bài cho phép **hiểu thuật toán và viết unit tests**. Khi đã dùng server framework mature, ưu tiên parser của nó vì nó xử lý những trường hợp khó hơn: streaming, limits, invalid bytes, content type, request body, charset và error responses.

### 20.1. Đừng decode hai lần trong controller

Một phương thức controller nhận `String name` do framework đã parse có thể đã là Unicode text gốc. Đưa nó qua `URLDecoder.decode(name,UTF_8)` lần nữa có thể biến `a+b` thành `a b` hoặc làm sai các ký tự percent còn lại.

Cần xác định **đầu vào controller là raw bytes, raw query hay decoded form value**.

### 20.2. Không validate giá trị trước khi biết charset/decoder semantics

Một policy chặn `/` nhưng chỉ chạy trên raw `%2F` sẽ sai nếu downstream decode thành slash sau đó. Tương tự chặn `&` trên raw bytes nhưng server lại parse theo delimiters. Validation nên đặt **sau khi đã parse/percent-decode đúng một lần**, đồng thời có input limits và canonicalization policy rõ ràng.

## 21. Bảo mật: encoding không phải sanitation

**Form encoding** giúp biểu diễn dữ liệu trong một protocol. Nó **không** tự ngăn:
- SQL injection;
- Cross-site scripting (XSS);
- HTTP header injection;
- Log forging;
- Path traversal;
- Authorization bypass;
- CSRF;
- Unicode confusables;
- Denial of service do input quá dài.

Bảo vệ theo **ngữ cảnh sử dụng sau decode**:
- SQL: prepared statements/parameterized queries;
- HTML: escape output theo HTML context;
- URL path: validate và encode từng path segment bằng URI-aware API;
- HTTP headers: framework APIs và chặn controls;
- Logging: structured logging, redaction và length limits;
- File paths: canonicalization và access checks, không lấy raw form value làm đường dẫn tùy ý;
- Authorization: xác minh identity và quyền thực hiện thao tác.

### 21.1. Không ghi nhạy cảm vào query/logs

Dữ liệu tiếng Việt có thể là tên thật hoặc PII. Dù được percent-encoded, **vẫn có thể decode dễ dàng**. `Nguy%E1...` không phải encryption.

- Tránh đưa passwords/tokens/ID nhạy cảm lên query;
- Không log body đầy đủ theo mặc định;
- Giới hạn quyền xem logs và retention;
- Dùng TLS/HTTPS trên đường mạng không tin cậy;
- Không xem việc mã hóa percent thành `%HH` là che giấu dữ liệu.

### 21.2. Giới hạn tài nguyên

Một người dùng có thể gửi:
- Hàng trăm nghìn pairs;
- Keys rất dài;
- Percent escape lặp vô hạn;
- Body nhiều megabytes;
- Chuỗi hợp lệ nhưng cực lớn sau decode.

Vì thế server production phải có:
- Giới hạn request body bytes;
- Giới hạn số lượng fields và kích cỡ mỗi field;
- Timeouts và concurrency limits;
- Error handling rõ khi malformed input;
- Kiểm tra data schema sau decode;
- Giám sát lưu lượng bất thường.

`readAllBytes()` trong server demo **không phù hợp làm production parser nếu thiếu size limits**.

### 21.3. Dữ liệu Unicode có thể gây bất nhất validation

Một số ký tự gần giống nhau nhưng khác code points, ví dụ `a` Latin và các ký tự có hình gần giống từ script khác. Unicode normalization NFC không xử lý mọi **confusables**.

Nếu dữ liệu dùng làm tên tài khoản, định danh, khóa lookup hoặc domain validation, cần chính sách riêng cho Unicode spoofing và giới hạn character categories. Không coi form encoding đúng là giải pháp cho vấn đề semantic identity.

## 22. Lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Tên biến thành `Nguy...` lỗi dấu | Client/server khác charset | UTF-8 nhất quán cả hai bên |
| Space ra `+` rồi coi là lỗi | Đây là quy tắc của form encoding | Decode bằng `URLDecoder` đúng chỗ |
| Literal `+` biến thành space | Không encode plus thành `%2B` hoặc double decode | Encode từng value; decode một lần |
| Giá trị có `&` bị tách cặp | Ghép raw value vào body | Encode `&` thành `%26` |
| Giá trị có `=` bị cắt | Parser tách mọi `=` | Tách dấu `=` đầu tiên của mỗi pair |
| `%` gây exception | Percent escape thiếu/không phải hex | Input validation, báo HTTP 400 phù hợp |
| UTF-8 lỗi nhưng không ném exception | `URLDecoder` có replacement semantics | Dùng strict decoder/parser nếu policy cần |
| Hai `tag` chỉ còn một | Đưa vào `Map<String,String>` | `List<Pair>` hoặc multimap |
| Empty value biến mất | Filter các fields có value rỗng | Định nghĩa rõ empty vs absent |
| NFC/NFD nhập tên trông giống nhau nhưng không bằng | Unicode code points khác | Normalization theo business policy |
| Emoji biến thành `?` | Charset cũ hoặc tự encode từng `char` | UTF-8 API với Unicode hợp lệ |
| Dấu cách NBSP không thành `+` | NBSP không phải U+0020 | Xử lý theo domain policy |
| GET query bị double-decoded | `URI.getQuery()` rồi `URLDecoder` | Dùng `getRawQuery()` và decode một lần |
| URL path bị `+`/`%2F` sai | Lạm dụng form encoder cho path | URI/path-aware encoder |
| Newlines khác nhau | Browser/textarea CRLF vs Java string LF | Test actual submission; thống nhất policy |
| POST thiếu content type | Client chỉ gửi body string | Set form Content-Type rõ |
| POST body không dùng UTF-8 | `BodyPublishers` sai charset | `BodyPublishers.ofString(body, UTF_8)` |
| Server trả tiếng Việt lỗi | Response body/header charset không khớp | UTF-8 cả bytes và `Content-Type` |
| Form-encoding được coi là bảo mật | `%HH` dễ decode | TLS, auth, output escaping, input validation |
| Lấy code `HttpClient` Java 11 chạy `--release 10` | Sai API version | Java 17+ cho integration; Java 10 Charset overload |
| Server demo OOM khi body lớn | `readAllBytes()` không giới hạn | Streaming/size limits trong production |
| Nối tên và value xong mới encode toàn chuỗi | Dấu phân cách `=`/`&` cũng bị encode | Encode từng component trước khi join |

## 23. Checklist kiểm thử form tiếng Việt

- [ ] Code dùng `StandardCharsets.UTF_8` rõ ràng cho `URLEncoder` và `URLDecoder`?
- [ ] Không gọi overload default-charset đã deprecated?
- [ ] Golden test `Nguyễn Văn An` cho đúng `Nguy%E1%BB%85n+V%C4%83n+An`?
- [ ] Tests có `ă â ê ô ơ ư đ` và tổ hợp dấu tiếng Việt?
- [ ] Có test `a b` ↔ `a+b` và `a+b` ↔ `a%2Bb`?
- [ ] Có test `&`, `=`, `%`, `?`, `#` trong field values?
- [ ] Có test tên trường Unicode, không chỉ giá trị?
- [ ] Có test repeated fields và thứ tự?
- [ ] Có test empty value và field không có `=`?
- [ ] Có test CRLF, LF và textarea-origin differences?
- [ ] Có test emoji/non-BMP và dấu cách NBSP?
- [ ] Có test Unicode NFC/NFD theo domain policy?
- [ ] Có negative tests `%`, `%A`, `%ZZ`?
- [ ] Đã phân biệt invalid UTF-8 replacement với invalid percent escape?
- [ ] Có giới hạn kích cỡ body, số lượng fields và độ dài values?
- [ ] Parser decode đúng một lần, không lẫn `URI.getQuery()` và `URLDecoder`?
- [ ] Có phân biệt form body/query/path/multipart/JSON?
- [ ] POST client đặt `Content-Type` và body charset đúng?
- [ ] Server parser có thể nhận UTF-8, không dựa vào host default?
- [ ] Response body/header charset phù hợp nếu trả dữ liệu tiếng Việt?
- [ ] Có HTTP integration test với loopback hoặc test service?
- [ ] Có test TLS/real web framework khi deploy không?
- [ ] Có bảo vệ auth, CSRF, logging, validation và output escaping?
- [ ] Không coi percent encoding là encryption hoặc sanitization?
- [ ] Có test trên cùng Java/runtime và hệ điều hành CI/CD?
- [ ] Đã xác nhận những API mới hơn Java 10 trong integration được ghi đúng mốc?

## 24. Câu hỏi ôn tập và đáp án

**1.** Điểm mới của Java 10 liên quan form encoding là gì?

**Đáp án:** Hai overload `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)`, giúp truyền charset dạng type-safe.

**2.** Charset được khuyến nghị cho form tiếng Việt?

**Đáp án:** UTF-8, thường dùng `StandardCharsets.UTF_8`.

**3.** `URLEncoder.encode("a b", UTF_8)` cho gì?

**Đáp án:** `a+b`.

**4.** `URLEncoder.encode("a+b", UTF_8)` cho gì?

**Đáp án:** `a%2Bb`.

**5.** Vì sao phải escape `&` bên trong value?

**Đáp án:** Vì `&` được dùng làm dấu phân tách giữa các cặp form.

**6.** Vì sao phải escape `=` trong value?

**Đáp án:** Vì `=` là dấu phân tách name và value.

**7.** `Nguyễn Văn An` được encode chính xác thành gì?

**Đáp án:** `Nguy%E1%BB%85n+V%C4%83n+An`.

**8.** UTF-8 có tự chuẩn hóa NFC/NFD không?

**Đáp án:** Không. Charset encoding và Unicode normalization là hai bước khác nhau.

**9.** `List<Pair>` tốt hơn `Map<String,String>` khi nào?

**Đáp án:** Khi form cho nhiều trường trùng tên và cần giữ thứ tự hoặc mọi values.

**10.** `URLDecoder.decode("%ZZ", UTF_8)` làm gì?

**Đáp án:** Ném `IllegalArgumentException` do malformed percent escape trên JDK được kiểm thử.

**11.** `URLDecoder.decode("%C3%28", UTF_8)` có chắc ném exception không?

**Đáp án:** Không. Charset overload có replacement semantics cho erroneous UTF-8 bytes.

**12.** Có thể decode một string lấy từ `URI.getQuery()` bằng `URLDecoder` lần nữa không?

**Đáp án:** Không nên nếu query đã được percent-decoded; có nguy cơ biến literal plus thành space. Dùng raw query/parser đúng.

**13.** Có thể dùng `URLEncoder` để encode nguyên `https://example.com/a?b=c` không?

**Đáp án:** Không. Đó là form component encoder, không phải whole URL builder.

**14.** Vì sao POST body cần `Content-Type`?

**Đáp án:** Để server biết media type và quy tắc parse request body.

**15.** `HttpClient` là API chuẩn từ Java phiên bản nào?

**Đáp án:** Java 11; ví dụ integration sử dụng JDK 17+.

**16.** Vì sao nên dùng loopback HTTP test ngoài unit test?

**Đáp án:** Nó kiểm tra body serialization, headers, bytes, server parsing và response decoding qua một HTTP exchange thật.

**17.** `readAllBytes()` trong demo có thể dùng production trực tiếp không?

**Đáp án:** Không nếu thiếu body size limits, timeouts, validation và security controls.

**18.** Form encoding có ngăn SQL injection không?

**Đáp án:** Không. Cần parameterized queries và validation.

**19.** Khi gặp ký tự tiếng Việt sai, nên bỏ dấu hay sửa charset?

**Đáp án:** Xác định nơi encode/decode bytes bị sai và thống nhất UTF-8; không tùy tiện làm mất dữ liệu gốc.

**20.** Kết quả nào chứng minh các chương trình trong bài đã chạy đúng?

**Đáp án:** `VietnameseFormDemo` có `roundTrip=true` và `pairsRoundTrip=true`; `MalformedFormDemo` từ chối escapes lỗi; `UriFormBoundaryDemo` cho thấy `formDecodedCorrect=a+b` khác `doubleDecodedIncorrect=a b`; `HttpFormLoopbackDemo` trả `status=200`, `reply=Đã nhận: Nguyễn Văn An; fields=4`.

## 25. Bài tập mở rộng

### Bài tập 1 — Kiểm thử thêm các tên tiếng Việt

Thêm các cases:
- `"Đặng Thị Hương"`;
- `"Bùi Quốc Anh"`;
- `"Thành phố Hồ Chí Minh"`;
- `"Tây Nguyên"`;
- `"điện thoại"`.

Với mỗi chuỗi, assert:

```java
String value = "Thành phố Hồ Chí Minh";
assert value.equals(
        URLDecoder.decode(
            URLEncoder.encode(
                value, StandardCharsets.UTF_8),
            StandardCharsets.UTF_8));
```

Đây là **mảnh code** chạy trong method/bài test khi Java assertions được bật (ví dụ `java -ea`). Không dùng `assert` như cơ chế validation request production.

### Bài tập 2 — Repeated checkbox fields

Mô phỏng:

```text
skill=Java&skill=SQL&skill=Ti%E1%BA%BFng+Vi%E1%BB%87t
```

Dùng `FormCodec.decodePairs` rồi đếm số cặp tên `skill`, kiểm tra đúng ba values và thứ tự.

### Bài tập 3 — Chính sách Unicode normalization

Lấy hai chuỗi `"\u1EBF"` và `"e\u0302\u0301"`. So sánh:
- Original values bằng `equals`?
- Form-encoded values giống nhau?
- Sau `Normalizer.normalize(..., NFC)` có bằng nhau không?

Giải thích tại sao đối với trường **họ tên** không nên tự biến thành ASCII không dấu.

### Bài tập 4 — Negative form parser test

Thử các inputs `"%"`, `"%A"` và `"%ZZ"`. Thêm test cho body `"name=%C3%28"`, kiểm tra hiện tượng replacement U+FFFD.

Đề xuất chính sách production: từ chối malformed UTF-8 thay vì âm thầm thay ký tự. Nhưng để thực thi phải dùng **strict percent-byte decoding** phù hợp, không chỉ `URLDecoder` rồi đi tìm `U+FFFD` (vì U+FFFD có thể là một ký tự hợp lệ do người dùng cố tình nhập).

### Bài tập 5 — Kiểm thử multipart và JSON (khác form)

Thêm một endpoint nhận `application/json` với dữ liệu:

```json
{"họ tên":"Nguyễn Văn An","ghi chú":"cà phê & bánh mì"}
```

So sánh body JSON với `application/x-www-form-urlencoded`. Dùng JSON serializer/parser đúng chuẩn; **không** áp `URLEncoder` cho toàn bộ JSON.

## 26. Tài liệu chính thức và chuẩn hiện hành

- [Oracle Java SE 10 — `URLEncoder`](https://docs.oracle.com/javase/10/docs/api/java/net/URLEncoder.html): `encode(String, Charset)` ghi rõ **Since: 10**, application/x-www-form-urlencoded và UTF-8.
- [Oracle Java SE 10 — `URLDecoder`](https://docs.oracle.com/javase/10/docs/api/java/net/URLDecoder.html): `decode(String, Charset)` **Since: 10** và xử lý malformed percent escapes.
- [Oracle Java SE 25 — `URLEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLEncoder.html): API vẫn hiện hành, tập ký tự được escape và legacy overloads bị deprecated.
- [Oracle Java SE 25 — `URLDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLDecoder.html): `decode(String,Charset)`, erroneous byte replacement và `IllegalArgumentException` đối với malformed escapes.
- [WHATWG URL Living Standard — application/x-www-form-urlencoded](https://url.spec.whatwg.org/#application/x-www-form-urlencoded): serialize/parse danh sách name/value pairs, `+` là space và percent-encoding.
- [WHATWG Encoding Living Standard](https://encoding.spec.whatwg.org/): UTF-8 cho việc trao đổi Unicode giữa các hệ thống.
- [Oracle Java SE 25 — `URI`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URI.html): `getQuery()` và `getRawQuery()`, phân biệt decoded URI component.
- [Oracle Java SE 25 — `Normalizer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): `Form.NFC`, `Form.NFD` và Unicode normalization.
- [Oracle Java SE 11 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofString(String, Charset)` và quy tắc chuyển text thành body bytes.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): Java HTTP Client chuẩn trong Java 11.
- [Oracle Java SE 25 — `HttpServer`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): module `jdk.httpserver` hỗ trợ HTTP server đơn giản để kiểm thử.
- [WHATWG HTML Living Standard — Form submission](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#form-submission-algorithm): tạo entries và gửi form theo browser semantics.

**Kết luận:** với biểu mẫu có dữ liệu tiếng Việt, hãy **encode từng tên và từng giá trị** bằng `URLEncoder.encode(value, StandardCharsets.UTF_8)`, ghép thành `name=value&...` và decode **một lần** bằng `URLDecoder.decode(value, StandardCharsets.UTF_8)` ở đúng lớp xử lý. Kiểm thử phải bao gồm **dấu tiếng Việt, plus/space, `&`/`=`/`%`, trường trùng tên, CRLF, emoji, NFC/NFD và malformed escapes**, đồng thời cần một HTTP integration test để xác nhận bytes thực tế. **Đúng form encoding không thay thế input validation, authorization hay output escaping**.