# `URLDecoder.decode(String, Charset)` — Giải mã dữ liệu biểu mẫu tường minh từ Java 10

## 1. Mục tiêu và bối cảnh

Trong ứng dụng web, dữ liệu biểu mẫu HTML hoặc tham số truy vấn được gửi theo quy ước **`application/x-www-form-urlencoded`** thường chứa các ký tự như `+` và các đoạn bắt đầu bằng `%`. Muốn chuyển dữ liệu đã mã hóa thành văn bản có nghĩa, Java cung cấp phương thức:

```java
String decoded = java.net.URLDecoder.decode(
        encoded, java.nio.charset.StandardCharsets.UTF_8);
```

Overload **`URLDecoder.decode(String, Charset)` được bổ sung ở Java 10** và vẫn được hỗ trợ trong Java hiện hành. Nó nhận một `String` đã được mã hóa theo quy ước **form URL encoding** và một đối tượng `Charset`, rồi trả về `String` đã giải mã.

Ví dụ:

```java
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String text = URLDecoder.decode(
        "ten=Nguy%E1%BB%85n+An", StandardCharsets.UTF_8);
System.out.println(text); // ten=Nguyễn An
```

Đoạn mã minh họa trên là các lệnh đặt trong phương thức và có import phù hợp; file chạy đầy đủ nằm ở phần 9.

Có ba điều cần nhớ ngay từ đầu:

1. **`+` được giải mã thành dấu cách** trong `application/x-www-form-urlencoded`. Muốn biểu diễn dấu cộng thật, nguồn thường phải dùng `%2B`.
2. **`%HH` biểu diễn một byte**, với `HH` là hai chữ số hex. Dãy nhiều byte liền nhau được giải mã theo `Charset` đã truyền, chẳng hạn UTF-8 cho chữ tiếng Việt.
3. **`URLDecoder` là decoder cho dữ liệu biểu mẫu, không phải decoder tổng quát cho toàn bộ URI**. Không áp dụng bừa lên path hoặc URL hoàn chỉnh, không giải mã trước khi tách các cặp tên–giá trị và không tự động giải mã lần hai.

## 2. Chữ ký API, phiên bản và hợp đồng chính xác

Chữ ký chuẩn:

```java
public static String decode(String s, Charset charset)
```

Trong đó:

| Thành phần | Ý nghĩa |
| --- | --- |
| `String s` | Chuỗi đã được mã hóa theo `application/x-www-form-urlencoded`. |
| `Charset charset` | Charset dùng để chuyển các **byte được biểu diễn bằng `%HH`** thành ký tự. |
| Kiểu trả về `String` | Văn bản sau khi giải mã các escape và chuyển `+` thành dấu cách. |
| `NullPointerException` | Xảy ra nếu `s` hoặc `charset` là `null`. |
| `IllegalArgumentException` | Có thể xảy ra nếu gặp escape không hợp lệ; cách xử lý chuỗi lỗi có phần phụ thuộc triển khai. |

Java 10 có ba overload nổi bật:

```java
// Không nên dùng cho giao thức trao đổi dữ liệu:
URLDecoder.decode(String s)

// Có từ Java 1.4, nhận tên charset:
URLDecoder.decode(String s, String enc)

// Có từ Java 10, nhận trực tiếp đối tượng Charset:
URLDecoder.decode(String s, Charset charset)
```

Các dòng trên biểu diễn **chữ ký và cách lựa chọn overload**, không phải những câu lệnh Java có thể biên dịch nguyên xi vì thiếu đối số thực.

### Vì sao ưu tiên overload `Charset`?

```java
String value = URLDecoder.decode(
        "caf%C3%A9", StandardCharsets.UTF_8);
```

- `StandardCharsets.UTF_8` là một đối tượng `Charset` được khai báo chuẩn, không cần tra cứu chuỗi tên `"UTF-8"`.
- Overload `decode(String, Charset)` **không khai báo checked exception `UnsupportedEncodingException`**. Vì vậy mã nguồn dễ dùng và không cần `throws`/`catch` chỉ để xử lý tra cứu một charset đã biết.
- Charset do caller lựa chọn tường minh, nên hành vi xử lý các escape byte không phụ thuộc **default charset**.
- Khi tham số đã là `Charset` từ cấu hình hợp lệ, có thể truyền trực tiếp; khi chỉ có tên charset, cần chuyển đổi/kiểm tra tên trước bằng API `Charset.forName` nếu phù hợp.

So sánh:

```java
String one = URLDecoder.decode(
        "caf%C3%A9", StandardCharsets.UTF_8);

// Overload nhận String tên charset vẫn có thể dùng,
// nhưng có checked UnsupportedEncodingException:
String two = URLDecoder.decode("caf%C3%A9", "UTF-8");
```

Không nên nhầm `UnsupportedEncodingException` với `IllegalArgumentException` do escape bị hỏng: chúng liên quan **hai loại lỗi khác nhau**. Với overload `Charset`, đối tượng charset đã được cung cấp, nhưng chuỗi form vẫn có thể không hợp lệ.

## 3. Cơ chế giải mã theo từng nhóm ký tự

`URLDecoder` làm ngược lại `URLEncoder` trong khuôn khổ `application/x-www-form-urlencoded`.

### 3.1. Các ký tự thông thường được giữ nguyên

Những ký tự alphanumeric `a-z`, `A-Z`, `0-9` cùng `.`, `-`, `*`, `_` không cần biểu diễn bằng escape trong quy tắc form encoding thông thường:

```java
System.out.println(URLDecoder.decode(
        "Java_10.File-1", StandardCharsets.UTF_8));
// Java_10.File-1
```

Không nên từ ví dụ đó suy ra mọi ký tự đặc biệt có thể đặt trực tiếp vào mọi vị trí của URL. **Quy tắc URL/URI và quy tắc biểu mẫu là hai ngữ cảnh khác nhau**.

### 3.2. Dấu cộng `+` có nghĩa là khoảng trắng

```java
System.out.println(URLDecoder.decode(
        "Java+10", StandardCharsets.UTF_8));
// Java 10
```

Với một giá trị text thực sự chứa dấu cộng `a+b`, dữ liệu form cần mã hóa dấu cộng bằng `%2B`:

```java
System.out.println(URLDecoder.decode(
        "a%2Bb", StandardCharsets.UTF_8));
// a+b
```

Bảng quan trọng:

| Chuỗi form đầu vào | Kết quả giải mã |
| --- | --- |
| `a+b` | `a b` |
| `a%20b` | `a b` |
| `a%2Bb` | `a+b` |
| `%2B` | `+` |
| `%25` | `%` |
| `x%3Dy` | `x=y` |
| `a%26b` | `a&b` |

**Không được đánh đồng `+` và `%2B`**. Dấu cộng chưa escape mang ý nghĩa *space* trong form encoding; `%2B` là một byte `2B` đại diện dấu cộng thực sự.

### 3.3. Escape `%HH` là byte, không phải mã Unicode trực tiếp

Mỗi `%HH` đại diện một byte (8 bit) có giá trị hex `HH`. Ví dụ:

```text
caf%C3%A9
   ^^  ^^
   C3  A9 — hai byte UTF-8 mã hóa chữ é
```

`URLDecoder.decode("caf%C3%A9", StandardCharsets.UTF_8)` cho `"café"`.

Đặc biệt:

- Các escape liên tiếp như `%C3%A9` được hiểu như **một chuỗi byte**, sau đó giải mã cùng charset.
- Không được diễn giải từng escape thành **một ký tự Java riêng lẻ** khi nó thuộc ký tự UTF-8 nhiều byte.
- Dùng UTF-8 với dữ liệu thực sự mã hóa theo UTF-8. Nếu byte nguồn được mã hóa theo Latin-1 thì phải giải mã theo charset thực tế.
- Hex có thể viết thường hoặc hoa; ví dụ `%2b` và `%2B` đều là escape hợp lệ cho byte `2B`.

### 3.4. UTF-8 cho chữ tiếng Việt

Ví dụ:

```java
String name = URLDecoder.decode(
        "Nguy%E1%BB%85n+An", StandardCharsets.UTF_8);

System.out.println(name); // Nguyễn An
```

Dãy `%E1%BB%85` tương ứng với ba byte UTF-8 mã hóa `ễ`; dấu `+` làm khoảng trắng. Tương tự, dữ liệu form cho `café` thường được tạo bởi UTF-8 thành `caf%C3%A9`.

## 4. Phân biệt form decoding với URI/URL decoding tổng quát

Tên lớp **`URLDecoder` rất dễ gây hiểu nhầm**. Javadoc mô tả nó là utility cho **HTML form decoding**, chứ không phải một hàm chuẩn để giải mã mọi component của URL.

### 4.1. Không dùng cho toàn bộ URL

**Cách làm sai:**

```java
String url = "https://example.test/search?q=a%2Bb";
// Không nên:
String decodedUrl = URLDecoder.decode(url, StandardCharsets.UTF_8);
```

Lời gọi trên coi toàn bộ URL như dữ liệu biểu mẫu. Nếu URL có dấu `+` hợp lệ với ý nghĩa riêng ở path hoặc query không theo form convention, kết quả có thể bị đổi thành dấu cách, làm thay đổi nội dung URI.

**Cách tiếp cận đúng:** dùng `java.net.URI` để xác định từng thành phần, sau đó chỉ dùng `URLDecoder` cho **giá trị nào thực sự theo quy ước form encoding**.

### 4.2. `URI.getRawQuery()` và `URI.getQuery()` khác nhau

```java
URI uri = URI.create(
        "https://example.test/search?q=a%2Bb");

System.out.println(uri.getRawQuery()); // q=a%2Bb
System.out.println(uri.getQuery());    // q=a+b
```

Hai lời gọi này làm việc với **query component**:

- `getRawQuery()` giữ nguyên các escape `%HH`; đây thường là đầu vào thích hợp nếu ứng dụng cần tự tách và giải mã các **form parameters**.
- `getQuery()` đã giải mã các escaped octets theo quy tắc `URI`. Nó **không biến `+` thành dấu cách theo form encoding**; trong ví dụ, kết quả có dấu cộng thật.
- **Không đưa tùy tiện `uri.getQuery()` vào `URLDecoder.decode(...)`**. Làm vậy có thể giải mã **lần thứ hai**, và dấu cộng đã được khôi phục từ `%2B` sẽ bị chuyển thành dấu cách.

Nếu query không dùng quy tắc form encoding mà là một component URI với quy ước riêng, không mặc định áp dụng `+` → space.

### 4.3. Không dùng trên path segment

Đối với path, dấu `+` có thể là một ký tự literal hợp lệ, không mang ý nghĩa dấu cách. Nếu:

```text
/files/a+b
```

được đưa vào `URLDecoder.decode(...)` thì `a+b` sẽ thành `a b`, thay đổi tên đường dẫn. Với path đã percent-encoded, hãy dùng **API xử lý URI path thích hợp**, xác định rõ khi nào cần giữ dạng raw và khi nào giải mã.

Tương tự, `%2F` có thể trở thành `/` khi decode; nếu ta giải mã **trước khi chia các path segment**, dấu slash mới tạo có thể thay đổi cấu trúc. Đây là lý do không dùng form decoder để thay thế một URI parser.

## 5. Khi có `&` và `=`: tách cặp trước, giải mã sau

Một query biểu mẫu thường có cấu trúc:

```text
name=value&name2=value2
```

Các dấu `&` và `=` **chưa escape** đóng vai trò dấu phân cách khi quy ước ứng dụng áp dụng. Ngược lại, `%26` và `%3D` là ký tự dữ liệu được escape.

Ví dụ:

```text
q=caf%C3%A9+%26+th%C3%A9&tag=a%2Bb&tag=c%20d
```

Sau khi parse đúng, ta muốn:

```text
q   = ["café & thé"]
tag = ["a+b", "c d"]
```

**Cách sai:**

```java
String allDecoded = URLDecoder.decode(rawForm, StandardCharsets.UTF_8);
// Sau decode, %26 thành '&' nên có thêm một '&' vốn là dữ liệu.
// Nếu tiếp tục split theo '&', ta sẽ chia nhầm giá trị q.
```

**Quy trình đúng với trường hợp form thông dụng:**

1. Xác định input là phần **raw form/query** chứ không phải URL đã giải mã.
2. Chia thành các cặp theo **dấu `&` còn ở dạng raw**.
3. Với mỗi cặp, tách tại **dấu `=` đầu tiên** để phân biệt tên và giá trị; các dấu `=` tiếp theo là dữ liệu của giá trị nếu ứng dụng chấp nhận.
4. **Giải mã tên và giá trị riêng biệt** bằng `URLDecoder.decode(..., StandardCharsets.UTF_8)`.
5. Giữ cấu trúc dữ liệu phù hợp, ví dụ `Map<String, List<String>>` nếu một tên có nhiều giá trị.

Đừng dùng `Map<String,String>` với `put` đơn giản nếu phải giữ **nhiều giá trị của cùng khóa**: cặp xuất hiện sau sẽ ghi đè cặp trước. Trong ví dụ trên, `tag` xuất hiện hai lần nên cần lưu cả `"a+b"` lẫn `"c d"`.

### Đoạn parser minh họa

```java
static Map<String, List<String>> parseForm(String rawForm) {
    Map<String, List<String>> result = new LinkedHashMap<>();

    if (rawForm.isEmpty()) {
        return result;
    }

    for (String pair : rawForm.split("&", -1)) {
        int separator = pair.indexOf('=');

        String rawKey = separator >= 0
                ? pair.substring(0, separator)
                : pair;
        String rawValue = separator >= 0
                ? pair.substring(separator + 1)
                : "";

        String key = URLDecoder.decode(
                rawKey, StandardCharsets.UTF_8);
        String value = URLDecoder.decode(
                rawValue, StandardCharsets.UTF_8);

        result.computeIfAbsent(
                key, k -> new ArrayList<>()).add(value);
    }
    return result;
}
```

Đây là **phương thức đặt trong một lớp** có import `java.net.URLDecoder`, `java.nio.charset.StandardCharsets` và các lớp `java.util` cần thiết. Chương trình đầy đủ có thể chạy ở phần 9.

**Giới hạn có chủ đích:** đây là parser giáo dục, không phải framework web hoàn chỉnh. Nó giữ cả tên rỗng và cặp rỗng theo quy tắc của đoạn code; chính sách xử lý `;`, byte stream request, Content-Type, kích thước tối đa, số tham số tối đa, tên lặp, lỗi escape và những trường hợp đặc thù phải được xác định rõ theo protocol/framework thực tế. Với ứng dụng web production, ưu tiên parser tin cậy sẵn có của framework khi phù hợp.

## 6. Dùng `URLEncoder.encode(String, Charset)` để tạo dữ liệu tương ứng

`URLDecoder` thực hiện giải mã. Khi cần **tạo** dữ liệu `application/x-www-form-urlencoded`, API đối xứng là:

```java
String encoded = java.net.URLEncoder.encode(
        value, StandardCharsets.UTF_8);
```

Overload nhận `Charset` của `URLEncoder.encode` cũng được bổ sung từ **Java 10**.

Ví dụ:

```java
String value = "A+B & café";

String encoded = URLEncoder.encode(
        value, StandardCharsets.UTF_8);

System.out.println(encoded);
// A%2BB+%26+caf%C3%A9

String restored = URLDecoder.decode(
        encoded, StandardCharsets.UTF_8);

System.out.println(value.equals(restored)); // true
```

Phân tích:

| Ký tự trong giá trị gốc | Sau `URLEncoder.encode` với UTF-8 | Khi `URLDecoder.decode` |
| --- | --- | --- |
| Khoảng trắng | `+` | Khoảng trắng |
| Dấu cộng literal `+` | `%2B` | Dấu cộng |
| Dấu `&` | `%26` | Dấu `&` |
| Chữ `é` | `%C3%A9` | `é` |
| Chữ `A` | `A` | `A` |

### Mã hóa riêng từng key và value

Nếu cần tự dựng query form:

```java
String rawKey = "search term";
String rawValue = "A+B & café";

String query = URLEncoder.encode(
        rawKey, StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode(
                rawValue, StandardCharsets.UTF_8);
```

Điều này bảo đảm dấu `&` và `=` **bên trong value** được escape theo quy tắc biểu mẫu trước khi ghép dấu phân cách. **Không dùng `URLEncoder.encode` để encode cả URL hoàn chỉnh**: nó sẽ encode luôn các ký tự cấu trúc như `:`, `/`, `?`, `&` theo ngữ cảnh của chuỗi đầu vào, khiến URL không giữ đúng cấu trúc ban đầu.

Khi hệ thống có API tạo URI hoặc cấu trúc request/form riêng, hãy ưu tiên API đó để tránh lỗi nối chuỗi.

## 7. Các tình huống charset: UTF-8, Latin-1 và dữ liệu lỗi

### 7.1. Charset phải khớp với nguồn

Dữ liệu `"café"` có thể được encode khác nhau:

```text
UTF-8:       caf%C3%A9
ISO-8859-1:  caf%E9
```

Giải mã đúng:

```java
String fromUtf8 = URLDecoder.decode(
        "caf%C3%A9", StandardCharsets.UTF_8);

String fromLatin1 = URLDecoder.decode(
        "caf%E9", StandardCharsets.ISO_8859_1);

System.out.println(fromUtf8.equals(fromLatin1)); // true
```

Chọn charset không đúng có thể khiến văn bản sai hoặc xuất hiện ký tự thay thế. **Chỉ định UTF-8 không thể tự sửa byte thực tế được tạo theo charset khác.**

### 7.2. Byte không hợp lệ và ký tự thay thế

Javadoc hiện hành nêu rằng khi các byte biểu diễn bằng `%HH` bị lỗi đối với charset đã chọn, decoder sử dụng **replacement value của Charset**. Ví dụ `%E9` là một byte Latin-1 hợp lệ cho `é`, nhưng đứng riêng lẻ không tạo thành một chuỗi UTF-8 hợp lệ.

```java
String mistaken = URLDecoder.decode(
        "caf%E9", StandardCharsets.UTF_8);

boolean replacementSeen = mistaken.contains(
        String.valueOf((char) 0xFFFD));
```

Trong ví dụ được kiểm thử với JDK, `replacementSeen` là `true` vì chuỗi chứa ký tự Unicode replacement `U+FFFD`.

**Quan trọng:** điều này khác với chuỗi form có escape syntax bị lỗi như `%GG` hoặc `%2`. Một bên là **escape hợp lệ về cú pháp nhưng byte không giải mã thành ký tự hợp lệ theo charset**, bên kia là **escape không hợp lệ về cú pháp**. Chính sách xử lý hai trường hợp không giống nhau.

Nếu hệ thống không được phép chấp nhận byte được thay thế lặng lẽ (ví dụ dữ liệu ký số hoặc identifier bắt buộc nguyên vẹn), đừng coi `URLDecoder.decode` là một bộ kiểm tra tính hợp lệ UTF-8 nghiêm ngặt. Cần áp dụng quy trình phân tích byte/decoder nghiêm ngặt ở ranh giới tin cậy hoặc dùng thư viện/framework có chính sách validation được xác định.

### 7.3. Dữ liệu lỗi `%` có thể dẫn tới `IllegalArgumentException`

Ví dụ escape không hoàn chỉnh hoặc không phải hex:

```text
%
%2
%GG
```

Javadoc của `URLDecoder` cho biết **một triển khai có thể** xử lý các chuỗi bất hợp lệ bằng cách giữ nguyên hoặc ném `IllegalArgumentException`. Trên JDK/OpenJDK được kiểm thử ở bài này, cả ba chuỗi trên **đều ném `IllegalArgumentException`**.

```java
try {
    URLDecoder.decode("%GG", StandardCharsets.UTF_8);
} catch (IllegalArgumentException ex) {
    System.out.println("Malformed form escape");
}
```

**Không nên tự diễn giải `%GG` thành một ký tự bình thường**, cũng không nên xây dựng contract phụ thuộc câu thông báo exception cố định. Với đầu vào từ bên ngoài, parser phải có chính sách rõ ràng: từ chối, ghi log an toàn và trả lỗi phù hợp; nếu cần tính tương thích nghiêm ngặt giữa triển khai, xác thực cú pháp escape theo định dạng trước khi decode.

### 7.4. `null` không có nghĩa “chuỗi rỗng”

```java
String empty = URLDecoder.decode("", StandardCharsets.UTF_8);
// empty.equals("") == true
```

Nhưng:

```java
// URLDecoder.decode(null, StandardCharsets.UTF_8); // NullPointerException
// URLDecoder.decode("x", (Charset) null);           // NullPointerException
```

Một `String` rỗng là đối số hợp lệ; **reference `null` là không hợp lệ**. Nếu dữ liệu có thể vắng mặt, hãy xử lý tình trạng thiếu input **trước khi gọi** decoder, thay vì mặc định nó sẽ trả chuỗi rỗng.

## 8. Những lỗi bảo mật và logic liên quan trực tiếp đến decode

### 8.1. Không decode hai lần

```java
String once = URLDecoder.decode(
        "a%252Bb", StandardCharsets.UTF_8);
// once = "a%2Bb"

String twice = URLDecoder.decode(
        once, StandardCharsets.UTF_8);
// twice = "a+b"
```

Dấu `%25` được decode thành `%` ở lần đầu; chuỗi mới `%2B` trở thành một escape hợp lệ ở lần thứ hai. Vì vậy kết quả **thay đổi** khi decode hai lần.

Một request có thể đi qua nhiều tầng framework, proxy hoặc code ứng dụng. Nếu một tầng đã decode và tầng sau decode lại, dữ liệu có thể vượt qua bước kiểm tra hoặc bị hiểu thành dấu phân cách không mong muốn. **Xác định chính xác tầng nào chịu trách nhiệm decode một lần, rồi validate dữ liệu đã chuẩn hóa**.

### 8.2. Không validate chuỗi chưa giải mã rồi giả định vẫn đúng sau decode

Ví dụ nếu một kiểm tra chỉ cấm ký tự `/` trong tên file nhưng không xét dữ liệu `%2F`, sau decode có thể xuất hiện slash. Đây là một minh họa về lỗi **kiểm tra sai thời điểm**, không phải bằng chứng rằng mọi `URLDecoder` phù hợp cho path.

Chính sách an toàn:

- Xác định rõ ngữ cảnh đang xử lý **form value, query component hay path**.
- Thực hiện decode/normalization theo đúng quy tắc đó **một lần**.
- Validate **giá trị cuối cùng được sử dụng**, không chỉ chuỗi raw đầu vào.
- Không ghép kết quả decode trực tiếp vào SQL, HTML, shell command hoặc đường dẫn file rồi cho rằng percent decoding đã bảo đảm an toàn. Cần sử dụng các API tham số hóa/escaping và quy tắc kiểm soát truy cập tương ứng.

### 8.3. Đừng coi form decoder là HTML decoder

`URLDecoder` không xử lý HTML entities như `&amp;` theo nghĩa của HTML escaping. Nó cũng không thay thế validation của JSON, Unicode normalization hay kiểm tra Content-Type.

Ví dụ `%26` được biến thành ký tự `&` theo percent decoding, nhưng **`&amp;` là một chuỗi theo quy tắc HTML khác**, không phải escape `%HH` của form encoding.

### 8.4. Giới hạn độ lớn input và số lượng parameter

Với request do người khác gửi, cần giới hạn byte length, số cặp field, độ dài key/value và số lượng giá trị trùng key theo chính sách ứng dụng/framework. `URLDecoder.decode(String, Charset)` nhận một `String`, không tự đóng vai trò bộ quản lý resource, giới hạn HTTP body hoặc chống denial-of-service cho cả parser.

Một ví dụ parser nhỏ phục vụ học thuật không nên được dùng nguyên xi ở server production nếu thiếu các kiểm soát này.

## 9. Chương trình Java 17+ hoàn chỉnh, đã kiểm thử

Lưu file có tên chính xác **`FormDecoderDemo.java`**:

```java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FormDecoderDemo {
    static Map<String, List<String>> parseForm(String rawForm) {
        Map<String, List<String>> result = new LinkedHashMap<>();
        if (rawForm.isEmpty()) {
            return result;
        }
        for (String pair : rawForm.split("&", -1)) {
            int separator = pair.indexOf('=');
            String rawKey = separator >= 0
                    ? pair.substring(0, separator)
                    : pair;
            String rawValue = separator >= 0
                    ? pair.substring(separator + 1)
                    : "";

            String key = URLDecoder.decode(
                    rawKey, StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    rawValue, StandardCharsets.UTF_8);

            result.computeIfAbsent(
                    key, k -> new ArrayList<>()).add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("plusAsSpace=" +
                URLDecoder.decode("a+b", StandardCharsets.UTF_8));
        System.out.println("encodedPlus=" +
                URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));
        System.out.println("percentSpace=" +
                URLDecoder.decode("a%20b", StandardCharsets.UTF_8));
        System.out.println("percentUtf8=" +
                URLDecoder.decode("caf%C3%A9", StandardCharsets.UTF_8));

        String raw = "q=caf%C3%A9+%26+th%C3%A9&tag=a%2Bb&tag=c%20d";
        Map<String, List<String>> params = parseForm(raw);
        System.out.println("formQuery=" + params);

        String value = "A+B & café";
        String encoded = URLEncoder.encode(
                value, StandardCharsets.UTF_8);
        System.out.println("encoded=" + encoded);
        System.out.println("roundTripOk=" + value.equals(
                URLDecoder.decode(encoded, StandardCharsets.UTF_8)));

        String latin1 = URLDecoder.decode(
                "caf%E9", StandardCharsets.ISO_8859_1);
        String mistaken = URLDecoder.decode(
                "caf%E9", StandardCharsets.UTF_8);
        System.out.println("latin1=" + latin1);
        System.out.println("wrongCharsetHasReplacement=" +
                mistaken.contains(String.valueOf((char) 0xFFFD)));

        int rejected = 0;
        for (String broken : List.of("%", "%2", "%GG")) {
            try {
                URLDecoder.decode(broken, StandardCharsets.UTF_8);
            } catch (IllegalArgumentException expected) {
                rejected++;
            }
        }
        System.out.println("malformedRejected=" + rejected);

        try {
            URLDecoder.decode(null, StandardCharsets.UTF_8);
        } catch (NullPointerException expected) {
            System.out.println("nullInputRejected=true");
        }

        try {
            URLDecoder.decode("x", (Charset) null);
        } catch (NullPointerException expected) {
            System.out.println("nullCharsetRejected=true");
        }

        URI uri = URI.create(
                "https://example.test/search?q=a%2Bb");
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("uriDecodedQuery=" + uri.getQuery());

        String once = URLDecoder.decode(
                "a%252Bb", StandardCharsets.UTF_8);
        System.out.println("decodeOnce=" + once);
        System.out.println("decodeTwice=" +
                URLDecoder.decode(once, StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 FormDecoderDemo.java
java FormDecoderDemo
```

**Stdout đã được kiểm chứng với JDK chạy ở môi trường thử nghiệm:**

```text
plusAsSpace=a b
encodedPlus=a+b
percentSpace=a b
percentUtf8=café
formQuery={q=[café & thé], tag=[a+b, c d]}
encoded=A%2BB+%26+caf%C3%A9
roundTripOk=true
latin1=café
wrongCharsetHasReplacement=true
malformedRejected=3
nullInputRejected=true
nullCharsetRejected=true
rawQuery=q=a%2Bb
uriDecodedQuery=q=a+b
decodeOnce=a%2Bb
decodeTwice=a+b
```

**Cách đọc kết quả:**

1. `plusAsSpace` khác `encodedPlus`: dấu `+` raw thành khoảng trắng; `%2B` thành dấu cộng thật.
2. `percentSpace` và `percentUtf8` xác nhận percent-decoding và UTF-8 cho các byte có escape.
3. `formQuery` thể hiện **tách cặp trước rồi decode từng key/value**, giữ nguyên ký tự `&` của dữ liệu trong `q` và giữ **hai giá trị `tag`**. `LinkedHashMap` giữ thứ tự insert của key trong minh họa.
4. `encoded` và `roundTripOk` cho thấy `URLEncoder.encode` + `URLDecoder.decode` dùng cùng UTF-8 có thể round-trip một giá trị biểu mẫu hợp lệ.
5. `latin1=café` nhưng `wrongCharsetHasReplacement=true` minh họa chọn sai charset có thể làm xuất hiện ký tự thay thế.
6. `malformedRejected=3` phản ánh **hành vi của JDK được thử nghiệm** với ba chuỗi escape lỗi; tài liệu API cho phép cách xử lý chuỗi bất hợp lệ phụ thuộc triển khai, nên đừng coi `3` là một ràng buộc phổ quát với mọi implementation.
7. Hai dòng `null...Rejected` phản ánh hợp đồng `NullPointerException` khi `s` hoặc `charset` là `null`.
8. `rawQuery` và `uriDecodedQuery` cho thấy **getRawQuery** giữ percent escapes trong khi **getQuery** đã giải mã chúng.
9. `decodeOnce` và `decodeTwice` chứng minh vì sao decode lại một chuỗi đã xử lý có thể thay đổi ý nghĩa.

Chương trình dùng tính năng ổn định, biên dịch với `--release 17` và có thể chạy trên JDK 17 trở lên; **chính overload `URLDecoder.decode(String, Charset)` đã có từ Java 10**.

## 10. So sánh với một số phương án dễ nhầm

| Tình huống | Nên dùng gì? | Không nên làm |
| --- | --- | --- |
| Decode một field `application/x-www-form-urlencoded` UTF-8 | `URLDecoder.decode(field, StandardCharsets.UTF_8)` | Dùng overload không charset |
| Encode một field form UTF-8 | `URLEncoder.encode(value, StandardCharsets.UTF_8)` | Encode cả URL hoàn chỉnh |
| Phân tích URL đầy đủ | `URI` hoặc URL/request parser phù hợp | Đưa cả URL vào `URLDecoder` |
| Parse raw form query `a=1&b=2` | Tách pair/`=` raw, rồi decode từng component | Decode cả query trước khi split |
| Giữ nhiều giá trị của cùng key | `Map<String, List<String>>` hoặc API multimap của framework | `Map.put` ghi đè các key lặp |
| Xử lý URL path | API xử lý URI/path đúng ngữ cảnh | Dùng form decoding làm mất nghĩa `+` |
| Kiểm tra byte UTF-8 nghiêm ngặt | Decoder/validator có chính sách lỗi rõ ràng | Dựa vào replacement của `URLDecoder` để chứng nhận dữ liệu hợp lệ |
| Request không đáng tin | Giới hạn kích thước, parse theo contract, validate sau decode | Decode lặp lại rồi ghép trực tiếp vào câu lệnh/đường dẫn |

### Overload không charset có còn phù hợp không?

`URLDecoder.decode(String)` vẫn tồn tại nhưng được đánh dấu **deprecated** vì kết quả có thể phụ thuộc default charset. Với Java 10–17, default charset có thể thay đổi theo môi trường; JDK 18+ có JEP 400 đặt UTF-8 làm default cho nhiều API, nhưng điều đó **không thay thế việc chỉ định charset theo hợp đồng** cho dữ liệu trao đổi.

Vì đề bài là overload `decode(String, Charset)`, hãy ưu tiên cách viết:

```java
URLDecoder.decode(rawField, StandardCharsets.UTF_8);
```

Khi các đối số không `null` và percent encoding đúng theo charset nguồn, mã sẽ rõ ràng và ít bị ảnh hưởng bởi thiết lập hệ thống.

## 11. Lỗi thường gặp và cách tránh

**Lỗi 1 — Nhầm `+` với dấu cộng thật.**  
Trong form encoding, `+` là dấu cách. Dấu cộng thật phải được escape thành `%2B`.

**Lỗi 2 — Decode query rồi mới split tại `&`.**  
`%26` có thể trở thành `&` là **dữ liệu value**; split sau decode sẽ chia nhầm cặp. Hãy split raw trước, decode key/value sau.

**Lỗi 3 — Dùng `URLDecoder` với path hoặc URL hoàn chỉnh.**  
Hàm này tuân theo quy tắc biểu mẫu, không phải mọi quy tắc URI. Với path chứa `+` hoặc `%2F`, dùng nó thiếu cân nhắc có thể đổi nghĩa.

**Lỗi 4 — Dùng `uri.getQuery()` rồi gọi `URLDecoder.decode`.**  
`getQuery()` đã percent-decode; decode lại vừa có nguy cơ biến `+` thành space, vừa xử lý thêm escape mới tạo. Ưu tiên raw query khi thật sự cần parse form.

**Lỗi 5 — Dùng charset tùy môi trường.**  
Đừng để `decode(String)` quyết định charset ngoài ý muốn. Truyền `StandardCharsets.UTF_8` hoặc charset do format quy định.

**Lỗi 6 — Cho rằng `%HH` là một ký tự Unicode độc lập.**  
Nó là một **byte**. UTF-8 nhiều byte như `%C3%A9` phải được giải mã thành một ký tự `é`, không xử lý từng byte thành ký tự riêng.

**Lỗi 7 — Coi byte UTF-8 lỗi luôn ném `IllegalArgumentException`.**  
Javadoc hiện hành mô tả chính sách **replacement** cho byte lỗi trong chuỗi `%HH`. Escape syntax lỗi và byte lỗi là hai nhóm khác nhau.

**Lỗi 8 — Coi `IllegalArgumentException` cho mọi chuỗi malformed là bắt buộc tuyệt đối trên mọi JDK.**  
Javadoc mô tả hành vi xử lý chuỗi escape không hợp lệ có thể phụ thuộc implementation. Cần kiểm tra/validate theo hợp đồng ứng dụng nếu yêu cầu nghiêm ngặt.

**Lỗi 9 — Parse key trùng bằng `Map<String,String>`.**  
Cặp `tag=a&tag=b` không nên tự động mất giá trị đầu nếu use case cần multivalue; chọn kiểu dữ liệu giữ toàn bộ giá trị.

**Lỗi 10 — Dùng decode làm bước bảo mật đủ dùng.**  
Percent decode không thay thế input validation, HTML output encoding, parameterized SQL, đường dẫn hợp lệ hoặc ranh giới tin cậy. Quy tắc an toàn phải được áp dụng sau khi chuẩn hóa dữ liệu.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `URLDecoder.decode("a+b", UTF_8)` trả gì?  
**Đáp án:** `"a b"` vì dấu `+` raw trong form encoding nghĩa là khoảng trắng.

**Câu 2.** Để nhận `"a+b"`, nguồn biểu mẫu phải chứa gì?  
**Đáp án:** `"a%2Bb"` — `%2B` được giải mã thành dấu cộng thật.

**Câu 3.** Vì sao `decode("caf%C3%A9", UTF_8)` cho `"café"`?  
**Đáp án:** Hai byte `C3 A9` đứng trong các escape liên tiếp là byte sequence UTF-8 của chữ `é`.

**Câu 4.** Vì sao không nên decode toàn bộ chuỗi `q=x%26y&tag=z` trước khi tách query?  
**Đáp án:** `%26` ở value sẽ thành dấu `&`, dễ bị hiểu sai là dấu phân cách cặp tham số. Tách raw pair trước rồi decode từng component.

**Câu 5.** `decode("caf%E9", UTF_8)` và `decode("caf%E9", ISO_8859_1)` có luôn cho cùng văn bản?  
**Đáp án:** Không. Byte `E9` đứng một mình hợp lệ trong Latin-1 với `é` nhưng không phải chuỗi UTF-8 đầy đủ. Chọn charset theo byte nguồn.

**Câu 6.** `URLDecoder.decode(null, UTF_8)` có trả chuỗi rỗng không?  
**Đáp án:** Không. Javadoc quy định `NullPointerException` khi input hoặc charset là `null`.

**Câu 7.** `URI.getRawQuery()` và `URI.getQuery()` khác gì?  
**Đáp án:** `getRawQuery()` giữ các escape percent; `getQuery()` giải mã escaped octets. Vì vậy không đưa `getQuery()` qua form decoder một cách máy móc.

**Câu 8.** Vì sao `decode("a%252Bb", UTF_8)` hai lần cho kết quả khác một lần?  
**Đáp án:** Lần đầu `%25` thành `%`, sinh `a%2Bb`; lần hai `%2B` thành dấu cộng. Đây là rủi ro double decoding.

## 13. Ghi nhớ

1. `URLDecoder.decode(String, Charset)` là API **từ Java 10**, dùng cho **`application/x-www-form-urlencoded`**, vẫn được hỗ trợ.
2. Nó chuyển `+` thành **space**, `%2B` thành **dấu cộng thật** và giải mã chuỗi **byte `%HH`** liên tiếp theo `Charset` đã truyền.
3. Ưu tiên `StandardCharsets.UTF_8` khi dữ liệu form được mã hóa UTF-8. Overload nhận `Charset` tránh checked `UnsupportedEncodingException` của overload nhận tên charset.
4. **Phân tích URI và phân tích form là hai công việc khác nhau**. Không decode toàn bộ URL hoặc path; nếu parse raw form query, tách cặp raw trước, decode từng key/value sau.
5. Byte sai charset có thể bị thay thế bằng ký tự replacement; escape syntax malformed có thể dẫn đến `IllegalArgumentException` tùy implementation. Input hoặc charset `null` ném `NullPointerException`.
6. Không decode hai lần, không dựa vào parser đơn giản như công cụ bảo mật hoàn chỉnh; validate và giới hạn dữ liệu **sau bước decode đúng ngữ cảnh**.
7. Khi cần tạo form value, dùng `URLEncoder.encode(value, Charset)` rồi ghép các component đã encode đúng dấu phân cách, không encode toàn bộ URL.

## Tài liệu chính thức và tham khảo còn áp dụng

- Java SE 26 API — `URLDecoder.decode(String, Charset)`, *Since 10*, ký tự `+`, percent escapes và lỗi: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLDecoder.html
- Java SE 26 API — `URLEncoder.encode(String, Charset)`, *Since 10*: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLEncoder.html
- Java SE 10 API — `URLDecoder` và mốc bổ sung overload nhận `Charset`: https://docs.oracle.com/javase/10/docs/api/java/net/URLDecoder.html
- Java SE 26 API — `URI.getRawQuery()` và `URI.getQuery()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URI.html
- Java SE 26 API — `StandardCharsets.UTF_8`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html
- OpenJDK JEP 400 — UTF-8 by Default, giải thích thay đổi default charset ở JDK 18: https://openjdk.org/jeps/400
- OWASP — Double Encoding, rủi ro decode nhiều lớp: https://owasp.org/www-community/Double_Encoding
