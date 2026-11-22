# Encoder, Decoder và padding với java.util.Base64

**`java.util.Base64`** là API chuẩn của Java được đưa vào từ **Java 8** và vẫn được hỗ trợ trong Java hiện nay. Nó giúp **mã hóa dữ liệu byte sang dạng ký tự ASCII** bằng bộ ký tự Base64 và **giải mã ngược về byte**. Ba biến thể chính là **Basic**, **URL/Filename-safe** và **MIME**. Một chi tiết quan trọng phải nắm chắc là ký tự **padding `=`**, vì nó liên quan trực tiếp đến số byte ban đầu, bộ mã hóa có hay không thêm `=` và bộ giải mã Java xử lý chuỗi thiếu/sai padding như thế nào.

Khái niệm trọng tâm: Base64 **không phải mã hóa bảo mật**, không tạo bí mật và không chứng minh tính nguyên vẹn. Bất kỳ người nào có chuỗi Base64 hợp lệ đều có thể giải mã thành byte gốc. Nó chỉ giải quyết bài toán **biểu diễn dữ liệu nhị phân bằng những ký tự phù hợp để truyền/lưu trong kênh xử lý text**.

Trong bài học thuộc chủ đề **Chuỗi và Base64**, ta sẽ học chính xác `Base64.Encoder`, `Base64.Decoder`, cách hoạt động theo nhóm 3 byte → 4 ký tự, `getEncoder`/`getDecoder`, `getUrlEncoder`/`getUrlDecoder`, `getMimeEncoder`/`getMimeDecoder`, `withoutPadding`, quy tắc giải mã khi không có `=`, xử lý UTF-8, `byte[]`, `ByteBuffer`, `InputStream/OutputStream`, kiểm tra đầu vào và lựa chọn biến thể trong ứng dụng. Có **sáu chương trình Java 17+ độc lập**, với đầu ra đã chạy kiểm tra; mọi API Base64 cốt lõi của bài vẫn áp dụng với Java 8.

## 1. Vì sao lại cần Encoder và Decoder?

Nhiều giao thức và định dạng dữ liệu truyền dưới dạng **text**, trong khi một hình ảnh, file PDF, public key, hash digest hoặc bản tin nhị phân là một chuỗi byte bất kỳ. Nếu chuyển thẳng byte sang `String` tùy charset, dữ liệu có thể hỏng, mất byte hoặc chứa ký tự điều khiển không hợp lệ.

**Encoder** chuyển byte → Base64 text. **Decoder** chuyển Base64 text → byte:

```text
Byte gốc (binary)
      │
      ▼
Base64.Encoder
      │
      ▼
Chuỗi ASCII (Base64)
      │
      ▼
Base64.Decoder
      │
      ▼
Byte gốc (binary)
```

Cặp biến đổi này **reversible** nếu dùng cùng biến thể Base64 tương thích và dữ liệu encoded không bị hỏng. Không có mật khẩu, khóa hoặc nonce trong thuật toán Base64; ai nhận encoded text đều có thể gọi Decoder.

Các tình huống thực tế gồm đưa ảnh nhỏ vào JSON khi contract yêu cầu string, biểu diễn phần bytes của một token, gói dữ liệu trong giao thức MIME, lưu một fingerprint dạng text hoặc tạo URL-safe token ngẫu nhiên. Việc Base64 có phù hợp hay không tùy định dạng đích và giới hạn kích thước; với file lớn, streaming hoặc truyền nhị phân trực tiếp thường tốt hơn nhét một chuỗi lớn vào JSON.

## 2. Ba biến thể quan trọng trong Java

| Biến thể | Lấy Encoder | Lấy Decoder | Alphabet/đặc trưng |
| --- | --- | --- | --- |
| **Basic** | `Base64.getEncoder()` | `Base64.getDecoder()` | RFC 4648, dùng `+` và `/`, **không** tự chèn newline |
| **URL and Filename safe** | `Base64.getUrlEncoder()` | `Base64.getUrlDecoder()` | RFC 4648 Base64URL, thay `+` → `-` và `/` → `_`, **không** tự xuống dòng |
| **MIME** | `Base64.getMimeEncoder()` | `Base64.getMimeDecoder()` | RFC 2045, encoder mặc định xuống dòng sau tối đa **76 ký tự** bằng CRLF; decoder bỏ qua ký tự không thuộc alphabet |

Cả ba đều làm việc trên **byte**, không đọc hiểu ngữ nghĩa Unicode hay định dạng nội dung. Phải chọn **đúng cặp encoder/decoder** và chuẩn mà hệ thống nhận yêu cầu. Không tự thay dấu cách, dấu gạch ngang hoặc dấu cộng trong encoded text mà không có lý do giao thức rõ.

Ví dụ:

```java
import java.util.Base64;

Base64.Encoder encoder = Base64.getEncoder();
Base64.Decoder decoder = Base64.getDecoder();
```

Hai dòng khai báo ở trên là **snippet trong method** sau khi import, không phải file class hoàn chỉnh. Các đối tượng encoder/decoder không giữ trạng thái nội dung giữa các lần gọi; theo JavaDoc, instances của hai lớp an toàn cho việc sử dụng từ nhiều thread. Điều này **không** biến mọi stream bọc bên ngoài thành tự động thread-safe.

## 3. Alphabet Base64 cơ bản và nguyên lý 6 bit

Bảng ký tự Base64 Basic có **64 ký tự dữ liệu**:

```text
A-Z  => 26 ký tự
a-z  => 26 ký tự
0-9  => 10 ký tự
+ /  =>  2 ký tự
--------------------
Tổng => 64 ký tự
```

64 = 2^6, nên mỗi ký tự dữ liệu biểu diễn **6 bit**. Thuật toán gom **3 byte = 24 bit**, chia thành **4 nhóm 6 bit**, tra bảng để tạo ra 4 ký tự Base64.

Ví dụ ASCII `foo` có ba byte; mã hóa thành:

```text
"foo"  → bytes 0x66 0x6f 0x6f
       → 01100110 01101111 01101111
       → 011001 100110 111101 101111
       → Z      m      9      v
       → "Zm9v"
```

Dấu `=` **không nằm trong bảng 64 ký tự dữ liệu**; nó là ký tự **padding** dùng khi nhóm cuối thiếu byte. Không nhầm `=` với byte 0 hoặc ký tự dữ liệu có chỉ số 64.

Base64URL dùng cùng cơ chế 6 bit nhưng thay hai ký tự cuối bằng `-` và `_`. Hai biến thể có thể trông giống hệt nhau nếu chuỗi đầu ra tình cờ không chứa `+`, `/`, `-` hay `_`; vì thế cần **biết contract**, không đoán biến thể dựa trên một vài ví dụ ngắn.

## 4. Padding `=` là gì?

Mỗi nhóm 3 byte tạo 4 ký tự. Nhưng nhóm cuối có thể còn **1 hoặc 2 byte**, khiến chưa đủ 24 bit. Encoder bổ sung các bit zero thích hợp và padding `=` để output theo form có chiều dài chia hết cho 4.

| Số byte còn lại ở nhóm cuối | Ký tự dữ liệu Base64 | Padding mặc định | Ví dụ |
| --- | --- | --- | --- |
| 0 (nhóm đầy đủ 3 byte) | 4 | 0 `=` | `foo` → `Zm9v` |
| 1 byte | 2 | 2 ký tự `==` | `f` → `Zg==` |
| 2 byte | 3 | 1 ký tự `=` | `fo` → `Zm8=` |

Với `n` byte nguồn, chiều dài Base64 **có padding**, nếu xét phần dữ liệu không xuống dòng, là:

```text
L = 4 × ceil(n / 3)

n = 0   → L = 0
n = 1   → L = 4
n = 2   → L = 4
n = 3   → L = 4
n = 4   → L = 8
n = 5   → L = 8
n = 6   → L = 8
```

Vì vậy Base64 thường tăng khoảng **33%** với payload lớn, chưa kể newline MIME, JSON escaping, headers và metadata. Với input rất nhỏ, tỷ lệ tăng có thể cao hơn nhiều: 1 byte thành 4 ký tự.

`withoutPadding()` chỉ bỏ các ký tự `=` cuối cùng, **không đổi bảng chữ cái**, không đổi nội dung byte và không làm thuật toán trở thành kiểu nén. Chuỗi không padding vẫn hoàn toàn có thể được Decoder của Java giải mã khi số ký tự cuối hợp lệ.

## 5. Các phương thức Encoder dùng thường xuyên

| API | Công dụng |
| --- | --- |
| `Base64.getEncoder()` | Basic Encoder |
| `Base64.getUrlEncoder()` | Base64URL Encoder |
| `Base64.getMimeEncoder()` | MIME Encoder |
| `Base64.Encoder.encodeToString(byte[])` | Trả một `String` chứa ký tự Base64 |
| `Base64.Encoder.encode(byte[])` | Trả mảng byte ASCII Base64 |
| `Base64.Encoder.encode(byte[], byte[])` | Mã hóa vào mảng đích đủ dung lượng, trả số byte ghi |
| `Base64.Encoder.encode(ByteBuffer)` | Mã hóa phần bytes còn lại trong buffer |
| `Base64.Encoder.wrap(OutputStream)` | Bọc output stream để mã hóa khi ghi |
| `Base64.Encoder.withoutPadding()` | Tạo encoder tương đương nhưng không tạo padding `=` |

Khi có `String` ban đầu, cần chọn charset để chuyển thành `byte[]` **trước**:

```java
byte[] source = "Xin chào".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

String encoded = java.util.Base64.getEncoder()
        .encodeToString(source);
```

Đây là snippet trong method. **Không** dùng `sourceString.getBytes()` không chỉ định charset khi giao thức yêu cầu byte ổn định trên nhiều hệ thống. `UTF-8` là lựa chọn thông dụng cho text Unicode, nhưng nội dung nguyên bản có thể không phải text; khi source là ảnh/PDF/gzip thì encode **byte gốc**, không tự chuyển qua String.

`encodeToString` trả encoded text chỉ dùng ký tự thuộc alphabet Base64 và padding; nó **không** biến byte gốc thành “Unicode đã được mã hóa an toàn” theo nghĩa bảo mật.

## 6. Chương trình hoàn chỉnh: Basic, padding và UTF-8

Tạo `BasicPaddingDemo.java`:

```java
import java.util.Base64;
import java.nio.charset.StandardCharsets;

public class BasicPaddingDemo {
    public static void main(String[] args) {
        String[] samples = {
                "", "f", "fo", "foo",
                "foob", "fooba", "foobar"
        };

        Base64.Encoder padded = Base64.getEncoder();
        Base64.Encoder bare = padded.withoutPadding();
        Base64.Decoder decoder = Base64.getDecoder();

        for (String input : samples) {
            byte[] bytes =
                    input.getBytes(StandardCharsets.UTF_8);

            String a = padded.encodeToString(bytes);
            String b = bare.encodeToString(bytes);

            System.out.println(
                    "bytes=" + bytes.length +
                    " padded='" + a +
                    "' unpadded='" + b +
                    "' decoded='" +
                    new String(decoder.decode(b),
                            StandardCharsets.UTF_8) + "'");
        }

        String message = "cà phê";
        String encoded = padded.encodeToString(
                message.getBytes(StandardCharsets.UTF_8));

        System.out.println("utf8 encoded=" + encoded);
        System.out.println(
                "utf8 roundtrip=" +
                new String(decoder.decode(encoded),
                        StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 BasicPaddingDemo.java
java BasicPaddingDemo
```

Đầu ra đã kiểm thử:

```text
bytes=0 padded='' unpadded='' decoded=''
bytes=1 padded='Zg==' unpadded='Zg' decoded='f'
bytes=2 padded='Zm8=' unpadded='Zm8' decoded='fo'
bytes=3 padded='Zm9v' unpadded='Zm9v' decoded='foo'
bytes=4 padded='Zm9vYg==' unpadded='Zm9vYg' decoded='foob'
bytes=5 padded='Zm9vYmE=' unpadded='Zm9vYmE' decoded='fooba'
bytes=6 padded='Zm9vYmFy' unpadded='Zm9vYmFy' decoded='foobar'
utf8 encoded=Y8OgIHBow6o=
utf8 roundtrip=cà phê
```

Có ba quy luật quan trọng:
1. Input 1 byte → 2 data chars và `==`; input 2 byte → 3 data chars và `=`; input 3 byte → 4 data chars không padding.
2. `withoutPadding()` làm gọn `Zg==` thành `Zg`, `Zm8=` thành `Zm8`, nhưng **Decoder Java vẫn đọc được**.
3. Text tiếng Việt `cà phê` phải chuyển thành **UTF-8 bytes** trước khi encode; sau decode phải dựng String cũng với UTF-8. Chuỗi Base64 `Y8OgIHBow6o=` chính là biểu diễn các UTF-8 bytes đó, không phải thuật toán encode riêng cho tiếng Việt.

Với `byte[0]`, encoder trả chuỗi rỗng và decoder trả mảng 0 byte. Không cần thêm padding cho trường hợp input rỗng.

## 7. Decoder nhận padding và chuỗi không padding ra sao?

`Base64.Decoder` nhận byte[]/String/ByteBuffer hoặc bọc InputStream để giải mã. JavaDoc nói rất cụ thể:

- Ký tự padding `=` **được chấp nhận** và biểu diễn phần kết thúc dữ liệu.
- **Padding không bắt buộc**: nếu đơn vị cuối chỉ có **2 hoặc 3 ký tự Base64 dữ liệu**, Decoder có thể suy ra padding còn thiếu tương ứng.
- **Nếu đã xuất hiện `=`**, số lượng padding phải đúng. Trường hợp thiếu một dấu hoặc thừa dấu là input không hợp lệ.
- Một ký tự dữ liệu đơn lẻ ở nhóm cuối không chứa đủ bit để tạo một byte, nên bị từ chối.
- Basic/URL Decoder đều có quy tắc từ chối ký tự **ngoài alphabet của biến thể đang dùng**. MIME Decoder thì khác vì cho phép bỏ qua các ký tự ngoài alphabet.

Bảng cụ thể với Basic Decoder:

| Input Base64 | Giải mã | Hợp lệ? |
| --- | --- | --- |
| `YQ==` | `a` | Có, 2 dấu đúng |
| `YQ` | `a` | Có, bỏ padding |
| `YWI=` | `ab` | Có, 1 dấu đúng |
| `YWI` | `ab` | Có, bỏ padding |
| `YWJj` | `abc` | Có, nhóm đầy đủ |
| `Y` | — | Không, nhóm cuối chỉ 1 ký tự |
| `YQ=` | — | Không, padding đã có nhưng thiếu |
| `YQ===` | — | Không, padding thừa |
| `YQ==x` | — | Không, ký tự dư sau kết thúc |
| `Y Q==` | — | Không, Basic không bỏ qua dấu cách |

**Không cần tự động thêm `=` bằng string hack trước khi gọi `Base64.getDecoder().decode(...)`** nếu chuỗi chỉ thiếu padding theo đúng quy tắc Java. Nếu giao thức yêu cầu canonical padded form, đó là một **ràng buộc giao thức riêng**, không phải điều kiện Decoder Java luôn bắt buộc.

## 8. API Decoder và cách bắt lỗi

Các phương thức chính:

```java
byte[] decoded = Base64.getDecoder().decode(base64Text);

byte[] decodedBytes = Base64.getDecoder()
        .decode(base64Text.getBytes(StandardCharsets.US_ASCII));

String original = new String(
        decoded, StandardCharsets.UTF_8);
```

Đây là snippets trong method, import `java.util.Base64` và `java.nio.charset.StandardCharsets`.

- `decode(String)` nhận encoded text, tạo ra `byte[]`; input hợp lệ phải chứa các ký tự alphabet theo biến thể đang dùng.
- `decode(byte[])` cũng trả byte gốc, với encoded representation ở dạng bytes.
- `decode(byte[], byte[])` điền vào mảng đích đủ lớn và trả số bytes được ghi. Nếu destination không đủ, ném `IllegalArgumentException`.
- `decode(ByteBuffer)` đọc bytes còn lại trong buffer và trả một buffer kết quả.
- `wrap(InputStream)` tạo stream đọc nội dung đã giải mã.
- Khi encoded input không hợp lệ, các method decode trực tiếp thường ném `IllegalArgumentException`; khi dùng wrapped InputStream, lỗi decode có thể xuất hiện dưới dạng `IOException` khi đọc.

Mẫu xử lý input không tin cậy:

```java
try {
    byte[] bytes = Base64.getDecoder().decode(payload);
    // Chỉ xử lý bytes khi đã giải mã thành công.
} catch (IllegalArgumentException ex) {
    // Báo lỗi input Base64 không hợp lệ cho caller.
}
```

Đây là snippet trong method có biến `payload`. **Không** catch lỗi rồi âm thầm trả byte[] rỗng, vì chuỗi Base64 rỗng **thực sự hợp lệ**; gộp “không hợp lệ” thành “dữ liệu rỗng” che mất lỗi quan trọng.

## 9. Chương trình hoàn chỉnh: Decoder chấp nhận và từ chối gì?

Tạo `DecodeValidationDemo.java`:

```java
import java.util.Base64;
import java.nio.charset.StandardCharsets;

public class DecodeValidationDemo {
    static String decode(String source) {
        try {
            return "'" + new String(
                    Base64.getDecoder().decode(source),
                    StandardCharsets.UTF_8) + "'";
        } catch (IllegalArgumentException ex) {
            return "IllegalArgumentException";
        }
    }

    public static void main(String[] args) {
        for (String s : new String[] {
                "YQ==", "YQ", "YWI=", "YWI", "YWJj",
                "Y", "YQ=", "YQ===", "YQ==x", "Y Q==", "=abc"
        }) {
            System.out.println(
                    "'" + s + "' => " + decode(s));
        }

        System.out.println(
                "normalize YQ=" +
                Base64.getEncoder().encodeToString(
                        Base64.getDecoder().decode("YQ")));

        System.out.println(
                "empty bytes=" +
                Base64.getDecoder().decode("").length);
    }
}
```

```bash
javac -encoding UTF-8 DecodeValidationDemo.java
java DecodeValidationDemo
```

```text
'YQ==' => 'a'
'YQ' => 'a'
'YWI=' => 'ab'
'YWI' => 'ab'
'YWJj' => 'abc'
'Y' => IllegalArgumentException
'YQ=' => IllegalArgumentException
'YQ===' => IllegalArgumentException
'YQ==x' => IllegalArgumentException
'Y Q==' => IllegalArgumentException
'=abc' => IllegalArgumentException
normalize YQ=YQ==
empty bytes=0
```

Phân biệt **Decoder lenient về thiếu padding** với việc **bỏ qua mọi input sai**. Java có thể chấp nhận `YQ` và xem tương đương `YQ==`, nhưng `YQ=` không có đủ ký tự padding nếu đã xuất hiện dấu. `Y Q==` chứa space nên Basic từ chối.

`normalize YQ=YQ==` cho thấy cách nhận một dạng không padding rồi xuất ra dạng có padding chuẩn của **Java Encoder**. Nhưng **được decode không đồng nghĩa đã kiểm chứng chữ ký/mã xác thực hoặc canonical encoding mà một protocol khác yêu cầu**.

## 10. Base64URL: khác Basic ở hai ký tự

Basic dùng `+` và `/` ở hai vị trí 62, 63. Base64URL thay tương ứng thành:

```text
Basic:     A-Z a-z 0-9 + /
URL-safe:  A-Z a-z 0-9 - _
                         ^ ^
```

Hai dạng dùng cơ chế bit như nhau. Bởi vậy Base64URL không phải nén, không phải encryption và không làm thay đổi nội dung decoded bytes. Nó chỉ chọn alphabet phù hợp hơn với đường dẫn và nhiều vị trí trong URL.

Một số giao thức như **JWT** thường dùng Base64URL **không padding** cho từng phân đoạn. Tuy nhiên:
- Đừng tự tách một chuỗi Base64URL bất kỳ rồi gọi đó là JWT hợp lệ.
- Decode payload không đồng nghĩa signature được xác thực.
- Nếu đã có thư viện JWT/OIDC đáng tin cậy, dùng thư viện đó để xác minh claims, chữ ký và chính sách.
- Base64URL giảm nhu cầu escape `+`/`/`, nhưng **không thay thế URL encoding cho mọi cấu trúc query/path tùy ý**.

**Dùng đúng cặp API**: `getUrlEncoder()` ↔ `getUrlDecoder()`. Basic decoder không được đảm bảo đọc được input chứa `-`/`_`, và URL decoder không chấp nhận `+`/`/` thay thế tùy tiện.

## 11. Chương trình hoàn chỉnh: Basic khác URL-safe

Tạo `UrlSafeDemo.java`:

```java
import java.util.Arrays;
import java.util.Base64;

public class UrlSafeDemo {
    public static void main(String[] args) {
        byte[] a = {
                (byte) 0xfb, (byte) 0xff, (byte) 0xff
        };

        String basic =
                Base64.getEncoder().encodeToString(a);
        String url =
                Base64.getUrlEncoder().encodeToString(a);

        System.out.println("basic=" + basic);
        System.out.println("url=" + url);

        byte[] b = {(byte) 0xfb, (byte) 0xff};
        String padded =
                Base64.getUrlEncoder().encodeToString(b);
        String unpadded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(b);

        System.out.println("URL padded=" + padded);
        System.out.println("URL unpadded=" + unpadded);
        System.out.println(
                "URL decoded same=" +
                Arrays.equals(
                        b,
                        Base64.getUrlDecoder()
                                .decode(unpadded)));

        try {
            Base64.getDecoder().decode(url);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "basic rejects URL alphabet=true");
        }

        try {
            Base64.getUrlDecoder().decode(basic);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "URL decoder rejects basic alphabet=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 UrlSafeDemo.java
java UrlSafeDemo
```

```text
basic=+///
url=-___
URL padded=-_8=
URL unpadded=-_8
URL decoded same=true
basic rejects URL alphabet=true
URL decoder rejects basic alphabet=true
```

Input byte `FB FF FF` được chọn cố ý vì mã hóa ra những ký tự khác biệt: Basic `+///`, URL-safe `-___`. Nếu thử chỉ với `hello`, hai biến thể có thể cho output giống nhau, che mất khác biệt thực sự.

`Base64.getUrlEncoder().withoutPadding()` là API Java 8 chuẩn cho đầu ra Base64URL không có `=`; **không cần tự cắt chuỗi bằng regex để bỏ padding**. URL decoder Java chấp nhận dạng thiếu padding đúng quy tắc, như `-_8`.

## 12. MIME Base64: xuống dòng và bộ giải mã bỏ qua ký tự ngoài alphabet

MIME Encoder mặc định:
- Dùng alphabet Basic với `+` và `/`.
- Phát encoded text thành các dòng tối đa **76 ký tự**.
- Ngăn dòng bằng cặp **CRLF** (`\r\n`).
- **Không** tự thêm CRLF ở cuối output.
- Có padding `=` mặc định cho nhóm cuối thiếu byte.

MIME Decoder:
- Chấp nhận line separators.
- **Bỏ qua mọi ký tự không thuộc bảng Base64**, không chỉ CRLF.
- Tương thích với nội dung MIME cần định dạng dòng.
- **Không thích hợp để xác thực chặt chuỗi Base64 nhận từ input không tin cậy** nếu giao thức đòi từ chối mọi ký tự ngoài alphabet.

Ví dụ:

```java
byte[] value = Base64.getMimeDecoder()
        .decode("Z m9v \n#");
```

Kết quả là bytes của `foo`, vì MIME Decoder bỏ qua dấu cách, newline và `#`. Trong khi đó, Basic Decoder **từ chối** input này.

Hệ quả quan trọng: nếu caller thêm dấu câu, khoảng trắng hoặc ký tự ngoài alphabet trong input MIME, decoder có thể **âm thầm bỏ chúng**. Đừng dùng tính khoan dung đó để thay thế một bước kiểm tra dữ liệu đúng chuẩn và chữ ký; trong giao thức yêu cầu canonical bytes/string, cần xác định một luật validation riêng.

## 13. Tùy chỉnh chiều dài dòng MIME

API:

```java
Base64.getMimeEncoder(int lineLength,
                      byte[] lineSeparator)
```

`lineLength` được **làm tròn xuống bội số 4**. Nếu sau khi làm tròn không còn số dương, encoder không chèn dòng. Ví dụ yêu cầu 10 ký tự mỗi dòng thì chiều dài thực tế là **8**.

`lineSeparator` không được chứa một **ký tự thuộc alphabet Base64 Basic**. Nếu có, `getMimeEncoder` ném `IllegalArgumentException`. Bạn có thể dùng `'\n'` cho một giao thức cụ thể, nhưng **MIME chuẩn RFC 2045 dùng CRLF**; không tùy tiện thay line separator nếu phía nhận yêu cầu đúng MIME.

Nhiều hệ thống hiện đại dùng Base64 Basic hoặc URL-safe trong JSON/API và không cần MIME wrapping. Chỉ chọn MIME khi **định dạng đích** thực sự yêu cầu dòng kiểu MIME hoặc bên nhận có decoder phù hợp.

## 14. Chương trình hoàn chỉnh: MIME và line separator

Tạo `MimeDemo.java`:

```java
import java.util.Arrays;
import java.util.Base64;
import java.nio.charset.StandardCharsets;

public class MimeDemo {
    public static void main(String[] args) {
        byte[] payload = new byte[60];
        Arrays.fill(payload, (byte) 'A');

        String mime = Base64.getMimeEncoder()
                .encodeToString(payload);

        System.out.println(
                "MIME line lengths=" +
                Arrays.stream(mime.split("\\r\\n", -1))
                        .map(String::length)
                        .toList());

        System.out.println(
                "MIME has CRLF=" +
                mime.contains("\r\n"));

        System.out.println(
                "MIME roundtrip=" +
                Arrays.equals(
                        payload,
                        Base64.getMimeDecoder().decode(mime)));

        try {
            Base64.getDecoder().decode(mime);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "basic rejects MIME newline=true");
        }

        String noisy = "Z m9v \n#";

        System.out.println(
                "MIME noisy=" +
                new String(
                        Base64.getMimeDecoder().decode(noisy),
                        StandardCharsets.UTF_8));

        try {
            Base64.getDecoder().decode(noisy);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "basic rejects noisy=true");
        }

        byte[] small = "123456789"
                .getBytes(StandardCharsets.US_ASCII);

        String custom = Base64.getMimeEncoder(
                10, new byte[] {'\n'})
                .encodeToString(small);

        System.out.println(
                "custom line lengths=" +
                Arrays.stream(custom.split("\n", -1))
                        .map(String::length).toList());

        try {
            Base64.getMimeEncoder(
                    8, new byte[] {'x'});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "invalid MIME separator=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 MimeDemo.java
java MimeDemo
```

```text
MIME line lengths=[76, 4]
MIME has CRLF=true
MIME roundtrip=true
basic rejects MIME newline=true
MIME noisy=foo
basic rejects noisy=true
custom line lengths=[8, 4]
invalid MIME separator=true
```

Đầu vào **60 bytes** tạo ra **80 Base64 data characters**. MIME mặc định tách thành dòng dài 76 và dòng cuối dài 4, không có CRLF tận cùng. Basic Decoder không cho newline; MIME Decoder đọc được CRLF.

`getMimeEncoder(10, new byte[]{'\n'})` tạo dòng dài **8**, không phải 10, vì mỗi nhóm encoded đủ có 4 ký tự. Ký tự `x` nằm trong Base64 alphabet nên không được dùng làm MIME line separator tùy chỉnh.

**Không nhầm MIME decoder “khoan dung ký tự lạ” với khả năng tự phát hiện hoặc sửa mọi payload bị hỏng.** Một số corruption làm mất ký tự dữ liệu thuộc alphabet hoặc sai padding vẫn có thể gây lỗi hoặc đổi decoded bytes.

## 15. `withoutPadding()` thay đổi Encoder, không phải Decoder

`Base64.Encoder.withoutPadding()` trả về **một Encoder tạo đầu ra không có dấu `=` cuối**. Nó **không sửa** nội dung bytes và **không yêu cầu** bạn tạo Decoder “không padding” riêng. Java cung cấp `getDecoder()`, `getUrlDecoder()` và `getMimeDecoder()` theo **biến thể alphabet**, và các decoder này có quy tắc chấp nhận thiếu padding như đã trình bày.

Ví dụ:

```java
byte[] raw = "fo".getBytes(StandardCharsets.US_ASCII);

String padded = Base64.getEncoder()
        .encodeToString(raw); // "Zm8="

String bare = Base64.getEncoder()
        .withoutPadding()
        .encodeToString(raw); // "Zm8"

boolean same = Arrays.equals(
        Base64.getDecoder().decode(padded),
        Base64.getDecoder().decode(bare));
```

Đây là snippet trong method có `import java.util.*;` và `java.nio.charset.StandardCharsets`. `same` sẽ true.

Một dạng Base64 không padding **không nhất thiết hợp lệ theo mọi protocol**, dù Java Decoder đọc được. Chẳng hạn, một API bên nhận có thể yêu cầu output theo RFC 4648 Basic **padded canonical form**, trong khi JWT Base64URL lại thường là unpadded. Hãy tuân thủ **contract của giao thức** chứ không dựa vào việc “Java giải mã được thì server nào cũng phải nhận”.

Không dùng `.replace("=", "")` trên một chuỗi không rõ tính hợp lệ để “chuẩn hóa”; nên encode trực tiếp bằng đúng API và chỉ loại padding khi giao thức cho phép.

## 16. Phân biệt encoding bytes và encoding text

Base64 hoạt động với **byte**, không biết Unicode. Với String gốc:

```java
String message = "cà phê";

byte[] utf8 = message.getBytes(
        StandardCharsets.UTF_8);

String b64 = Base64.getEncoder()
        .encodeToString(utf8);

byte[] restoredBytes = Base64.getDecoder()
        .decode(b64);

String restoredText = new String(
        restoredBytes, StandardCharsets.UTF_8);
```

Đây là snippet trong method; `restoredText` bằng `message`.

Sai thường gặp:
- `message.getBytes()` dựa charset mặc định thay vì chỉ định UTF-8 rõ ràng.
- `new String(binaryBytes)` với bytes nhị phân tùy ý không phải text.
- Tưởng Base64 giúp một byte[] ảnh biến thành text Unicode có thể chỉnh sửa tùy ý.
- Giải mã thành String dù payload là compressed bytes, public key DER, encrypted ciphertext hoặc file binary.
- Dùng UTF-16 trong lúc encode rồi dùng UTF-8 khi decode, khiến round trip text sai.

Khi payload thật sự là binary, sau `decode` **giữ kết quả ở `byte[]`** và xử lý theo định dạng binary đó. Chỉ tạo String nếu contract nói payload chứa text ở charset đã định nghĩa.

## 17. `encodeToString` vs `encode(byte[])`

Hai method đều làm cùng phép mã hóa nhưng trả kiểu khác:

```java
byte[] raw = {1, 2, 3};

String a = Base64.getEncoder()
        .encodeToString(raw);

byte[] b = Base64.getEncoder()
        .encode(raw);
```

`a` là Java String chứa ký tự Base64; `b` là **encoded ASCII bytes**, không phải byte nguồn. Nếu cần đưa vào JSON String, `encodeToString` rõ ràng hơn; nếu giao thức/OutputStream cần byte, `encode(byte[])` có thể giảm thao tác chuyển kiểu.

Ví dụ encoded bytes chỉ chứa US-ASCII, nên nếu muốn biểu diễn:
`new String(b, StandardCharsets.US_ASCII)` là hợp lý. **Đừng dùng `new String(raw, US_ASCII)` để giả định mọi binary byte đều là text hợp lệ**.

`decode(String)` đi ngược từ encoded String sang raw bytes. `decode(byte[])` nhận encoded bytes, **không nhận raw bytes** và cũng không biết nội dung nguồn có phải UTF-8 hay không.

## 18. `ByteBuffer`, vị trí và giới hạn

Encoder và Decoder có overload `ByteBuffer`. Với Java NIO, `ByteBuffer` có:
- `position()`: byte kế tiếp được đọc/ghi.
- `limit()`: ranh giới dữ liệu hiện hữu.
- `remaining()`: số bytes còn lại.
- `capacity()`: dung lượng tổng.

`Encoder.encode(ByteBuffer)` xử lý **bytes còn lại** từ position đến limit, có thể dùng `position`/`limit` để chỉ chọn một slice. Method trả buffer mới chứa encoded bytes; source buffer được tiêu thụ đến limit. `Decoder.decode(ByteBuffer)` có hành vi tương tự về việc đọc encoded bytes còn lại.

Khi kiểm thử với ByteBuffer, **đừng nhầm buffer đã thay đổi position với buffer đã mất hết nội dung**. Có thể `duplicate` hoặc `asReadOnlyBuffer` nếu bạn cần giữ vị trí ban đầu. Đọc `ByteBuffer` bằng `Charset.decode` thường cũng thay đổi position, nên phải thiết kế lifecycle.

API kiểu `encode(byte[], byte[])` và `decode(byte[], byte[])` yêu cầu bạn cấp mảng đích có đủ dung lượng và trả **số byte thực ghi**. Đó không phải thứ tự tham số source/destination của `ByteBuffer` API.

## 19. Chương trình hoàn chỉnh: ByteBuffer và mảng đích

Tạo `BufferDemo.java`:

```java
import java.util.Base64;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferDemo {
    public static void main(String[] args) {
        ByteBuffer src = ByteBuffer.wrap(
                new byte[] {'!', 'f', 'o', 'o', '?'});

        src.position(1);
        src.limit(4);

        ByteBuffer encoded =
                Base64.getEncoder().encode(src);

        System.out.println(
                "buffer encoded=" +
                StandardCharsets.US_ASCII
                        .decode(encoded).toString());

        System.out.println(
                "input consumed=" +
                (src.position() == src.limit()));

        ByteBuffer letters =
                StandardCharsets.US_ASCII.encode("Zm9v");

        ByteBuffer decoded =
                Base64.getDecoder().decode(letters);

        System.out.println(
                "buffer decoded=" +
                StandardCharsets.UTF_8
                        .decode(decoded).toString());

        System.out.println(
                "encoded input consumed=" +
                (letters.position() == letters.limit()));

        byte[] dest = new byte[8];
        int n = Base64.getEncoder().encode(
                new byte[] {'f', 'o', 'o'}, dest);

        System.out.println(
                "byte dest count=" + n +
                ", text=" +
                new String(
                        dest, 0, n, StandardCharsets.US_ASCII));

        byte[] out = new byte[3];
        int count = Base64.getDecoder().decode(
                "Zm9v".getBytes(StandardCharsets.US_ASCII),
                out);

        System.out.println(
                "decoded dest count=" + count +
                ", text=" +
                new String(
                        out, 0, count, StandardCharsets.UTF_8));

        try {
            Base64.getDecoder().decode(
                    "Zm9v".getBytes(StandardCharsets.US_ASCII),
                    new byte[2]);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "small destination rejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 BufferDemo.java
java BufferDemo
```

```text
buffer encoded=Zm9v
input consumed=true
buffer decoded=foo
encoded input consumed=true
byte dest count=4, text=Zm9v
decoded dest count=3, text=foo
small destination rejected=true
```

Trong ví dụ, mảng nguồn là `!foo?` nhưng `position=1` và `limit=4` nên Encoder chỉ đọc `foo`. Cả nguồn encoded lẫn encoded-text buffer đều được tiêu thụ tới limit. Vì vậy test tập trung vào **remaining bytes**, không phải toàn bộ capacity.

`byte[] dest` có độ dài 8 nhưng chỉ có **4 byte hợp lệ được ghi**; phải dùng biến trả về `n` khi tạo String. Không tự in cả mảng 8 byte vì phần dư không thuộc encoded output. Khi buffer đích quá nhỏ, Java ném `IllegalArgumentException`, không âm thầm cắt dữ liệu.

## 20. Mã hóa/giải mã theo stream khi dữ liệu lớn

Nếu dữ liệu đang chảy qua network/file stream, tạo `byte[]` rất lớn và một String Base64 tương ứng có thể gây tốn bộ nhớ. `Base64.Encoder.wrap(OutputStream)` và `Base64.Decoder.wrap(InputStream)` cho phép xử lý dạng streaming:

```java
try (OutputStream encoded =
        Base64.getEncoder().wrap(destination)) {
    encoded.write(sourceBytes);
}
```

Đây là snippet trong method có `destination` là OutputStream và `sourceBytes` là byte[], xử lý `IOException`.

`wrap(OutputStream)` tạo **một output stream ghi vào stream bên dưới sau khi encode**. **Phải đóng encoder wrapper** để nó hoàn tất nhóm cuối và phát padding cần thiết. Gọi `flush()` không nên bị nhầm thành “hoàn tất Base64 cuối cùng” nếu nhóm còn thiếu byte.

Với Decoder:

```java
try (InputStream decoded =
        Base64.getDecoder().wrap(encodedInput)) {
    // Đọc từ decoded để thu byte gốc.
}
```

`encodedInput` là stream chứa bytes encoded Base64. Khi đọc có input sai, wrapped decoder có thể báo `IOException`. Quản lý ownership cẩn thận: **đóng wrapper sẽ đóng underlying stream**; nếu không muốn đóng underlying stream, cần API/lifecycle được thiết kế rõ hơn.

Không đồng nghĩa `Stream<Path>` của `Files.walk` với Base64 stream: một bên duyệt file paths, một bên biến đổi nội dung bytes. Cả hai là resource-backed workflows nhưng có quyền sở hữu khác nhau.

## 21. Chương trình hoàn chỉnh: padding chỉ hoàn tất khi close stream

Tạo `StreamWrapDemo.java`:

```java
import java.io.*;
import java.util.Base64;
import java.nio.charset.StandardCharsets;

public class StreamWrapDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream sink =
                new ByteArrayOutputStream();

        try (OutputStream encoded =
                Base64.getEncoder().wrap(sink)) {

            encoded.write(
                    "fo".getBytes(StandardCharsets.UTF_8));

            System.out.println(
                    "before close='" +
                    sink.toString(StandardCharsets.US_ASCII) +
                    "'");
        }

        String data =
                sink.toString(StandardCharsets.US_ASCII);

        System.out.println(
                "after close='" + data + "'");

        try (InputStream decoded =
                Base64.getDecoder().wrap(
                        new ByteArrayInputStream(
                                sink.toByteArray()))) {

            System.out.println(
                    "decoded stream='" +
                    new String(
                            decoded.readAllBytes(),
                            StandardCharsets.UTF_8) +
                    "'");
        }

        ByteArrayOutputStream payload =
                new ByteArrayOutputStream();

        try (OutputStream encoded =
                Base64.getUrlEncoder()
                        .withoutPadding()
                        .wrap(payload)) {

            encoded.write(
                    "fo".getBytes(StandardCharsets.UTF_8));
        }

        System.out.println(
                "URL stream unpadded='" +
                payload.toString(StandardCharsets.US_ASCII) +
                "'");
    }
}
```

```bash
javac -encoding UTF-8 StreamWrapDemo.java
java StreamWrapDemo
```

```text
before close=''
after close='Zm8='
decoded stream='fo'
URL stream unpadded='Zm8'
```

**Giải thích:** hai byte `fo` chưa tạo thành nhóm 3 byte đầy đủ. Encoder wrapper giữ phần cuối; sau `close()` nó mới phát `Zm8=` theo padding mặc định. URL encoder có `withoutPadding` thì sau close chỉ phát `Zm8`.

Trong ví dụ dùng `ByteArrayOutputStream` để quan sát output trước/sau close. Với file/socket thật, đừng bỏ việc đóng encoder wrapper, vì có thể mất phần bytes cuối chưa hoàn tất. Đừng coi `flush()` là thay thế cho `close()` trong việc kết thúc Base64 encode.

**Lưu ý phiên bản:** `InputStream.readAllBytes()` và `ByteArrayOutputStream.toString(Charset)` là tiện ích JDK mới hơn Java 8; ví dụ chạy Java 17+. Chức năng `Base64.Encoder.wrap`/`Decoder.wrap` là API từ Java 8.

## 22. Thread safety và tái sử dụng Encoder/Decoder

Theo JavaDoc, `Base64.Encoder` và `Base64.Decoder` instances **an toàn để dùng đồng thời nhiều thread**. Có thể giữ một encoder dùng chung:

```java
private static final Base64.Encoder ENCODER =
        Base64.getUrlEncoder().withoutPadding();
```

Đây là field snippet thuộc một class. Mỗi thread có thể gọi `ENCODER.encodeToString(itsBytes)` cho input riêng.

Điều này **không** bảo đảm:
- Một `OutputStream` từ `wrap` có thể được nhiều thread ghi xen kẽ mà không đồng bộ.
- Một `ByteBuffer` input được chia sẻ và sửa position cùng lúc là thread-safe.
- Mảng byte đích được nhiều tasks ghi đồng thời không có data race.
- String decoded từ bytes là an toàn nếu charset sai.
- Dữ liệu encoded tự có integrity/authentication.

Tách **đối tượng Encoder/Decoder không trạng thái** khỏi **stateful input/output streams/buffers** và dùng ownership/đồng bộ phù hợp.

## 23. Kích thước, bộ nhớ và hiệu năng

Base64 padded dài `4 * ceil(n/3)` ký tự cho `n` bytes, không tính MIME line separators. Base64 thường chiếm nhiều hơn **khoảng 1/3** so với dữ liệu bytes gốc khi `n` lớn.

Những hệ quả:
- Một ảnh 12 MiB nếu encode vào Base64 string có thể tạo khoảng 16 MiB **ký tự ASCII encoded**, chưa tính object overhead, copies hay JSON serialization.
- Nếu vừa giữ source bytes, encoded byte[] và encoded String, peak memory lớn hơn.
- `Base64.getMimeEncoder()` chèn CRLF và khiến output lớn thêm.
- Nếu request body gửi Base64, endpoint phải có **giới hạn kích thước input** và sau decode.
- `String` là immutable nhưng không xóa nội dung nhạy cảm theo ý muốn; đừng log encoded secrets, token hoặc private key rồi nghĩ Base64 đã che nội dung.
- Truyền file lớn bằng raw binary stream hoặc multipart có thể hiệu quả hơn encode rồi nhúng JSON, tùy contract.

`withoutPadding` chỉ tiết kiệm tối đa **hai ký tự** ở cuối encoded segment, không giảm tỷ lệ tăng 33% của dữ liệu lớn. `Base64URL` chỉ thay alphabet, không làm chuỗi ngắn hơn theo cách đáng kể.

Khi dùng stream, vẫn cần giới hạn tổng bytes, deadline và quyền truy cập. Streaming giúp tránh toàn bộ nội dung nằm trong memory cùng lúc, nhưng không thay thế backpressure hoặc quotas.

## 24. Valid input, canonical form và normalize có kiểm soát

Một Decoder có thể chấp nhận **nhiều cách biểu diễn cùng bytes**:
- `YQ==` và `YQ` cùng giải mã thành `a` trong Java.
- Một protocol chỉ chấp nhận **padded Basic** có thể muốn giữ một dạng canonical.
- Một protocol như Base64URL cho token có thể yêu cầu **unpadded URL-safe**.

Một quy trình canonicalization khi có contract rõ:
1. Xác định biến thể expected: Basic, URL-safe hay MIME.
2. Decode input bằng decoder đúng biến thể; từ chối input sai.
3. Re-encode bytes bằng encoder đúng biến thể và chính sách padding.
4. So sánh chuỗi với input **nếu protocol thực sự bắt canonical form**.
5. Với dữ liệu có chữ ký/hash, xác minh integrity/authenticity bằng cơ chế riêng theo chuẩn giao thức, không chỉ bằng Base64.

Ví dụ:

```java
String input = "YQ";
byte[] bytes = Base64.getDecoder().decode(input);
String canonicalPadded =
        Base64.getEncoder().encodeToString(bytes);
// canonicalPadded == "YQ=="
```

Đây là snippet trong method. Nếu ứng dụng cho phép unpadded Basic, input `YQ` là hợp lệ. Nếu yêu cầu canonical padded, input `YQ` **không đúng format** dù Decoder Java vẫn chấp nhận.

Không tự động dùng `getMimeDecoder()` cho mọi đầu vào “để ít bị lỗi”: MIME decoder bỏ qua ký tự ngoài alphabet, có thể che giấu dữ liệu bị chỉnh sửa mà giao thức lẽ ra phải từ chối.

## 25. Những rủi ro bảo mật phải phân biệt

Base64 giải quyết vấn đề **encoding**, không giải quyết **confidentiality, integrity hoặc authenticity**.

Ví dụ:
- Username/password sau Base64 **không trở thành bí mật**. Basic Authorization trong HTTP còn cần TLS để bảo vệ trên đường truyền.
- JSON payload chứa Base64 encoded bytes vẫn là payload do caller kiểm soát. Phải validate loại dữ liệu, kích thước và nội dung decoded.
- JWT có hai phân đoạn JSON Base64URL nhưng việc **decode** không chứng minh token hợp lệ. Phải kiểm tra chữ ký, issuer, audience, expiration và policy bằng thư viện chuyên dụng.
- MIME decoder có thể âm thầm bỏ non-alphabet characters. Điều này thích hợp với định dạng MIME nhưng không tự thích hợp với strict security validation.
- Ký tự `=` không phải MAC, checksum hoặc xác nhận chính xác dữ liệu: chỉ là padding.

Đối với dữ liệu không tin cậy, đặt giới hạn cho encoded length **trước decode** và decoded size theo business policy. Tránh nhận một String hàng trăm MB rồi mới thử decode vì có thể gây chi phí memory lớn hoặc DoS. Kiểm tra syntax/padding theo chuẩn mong đợi và không lộ nội dung bí mật trong logs hoặc lỗi API.

Nếu protocol yêu cầu **canonical input**, đừng coi việc decoder chấp nhận dạng unpadded là đủ điều kiện vượt qua validation. Nếu protocol cần xác thực, sử dụng chữ ký/MAC/AEAD phù hợp, không tự coi Base64 là chứng cứ.

## 26. Lựa chọn biến thể theo ứng dụng

| Tình huống | API thường chọn | Lưu ý |
| --- | --- | --- |
| Binary trong JSON String theo RFC 4648 Basic | `getEncoder/getDecoder` | Contract phải cho padding/format cụ thể |
| Token cho URL path/filename | `getUrlEncoder/getUrlDecoder` | Có thể `withoutPadding` nếu protocol yêu cầu |
| MIME email body có dòng 76 ký tự CRLF | `getMimeEncoder/getMimeDecoder` | MIME decoder bỏ qua ký tự ngoài alphabet |
| Chuỗi Base64URL JWT | URL-safe và thường unpadded | Xác thực JWT bằng thư viện chuyên trách |
| Mã hóa byte[] nhỏ | `encodeToString` | Chọn UTF-8 khi nguồn là String |
| Input/output dữ liệu lớn | `wrap(OutputStream)/wrap(InputStream)` | Close, limits, stream ownership |
| Dữ liệu binary trong ByteBuffer | `encode/decode(ByteBuffer)` | Chỉ phần remaining và thay position |
| Yêu cầu strict validation | Basic/URL decoder đúng alphabet | Thêm canonical checks nếu protocol cần |
| Định dạng chưa rõ nguồn | Không tự chọn MIME để “chữa” | Hỏi hoặc dựa vào schema/contract |
| File binary đã truyền được trực tiếp | Có thể không cần Base64 | Tránh tăng kích thước vô ích |

Một giao thức có thể gọi trường dữ liệu là “base64” nhưng vẫn quy định rõ alphabet, padding, newline và charset. **Tên field không đủ thay thế contract**; kiểm tra tài liệu của phía gửi/nhận.

## 27. Phân biệt Base64 với công cụ chuyển đổi khác

- **Hex**: biểu diễn mỗi byte bằng 2 ký tự hex; thường dài ~2 lần số byte, dễ đọc/debug nhưng lớn hơn Base64.
- **URL percent-encoding**: mã hóa các ký tự cần escape trong URL, không phải chuyển byte nhị phân sang nhóm 6-bit của Base64.
- **UTF-8**: charset biến Unicode text thành bytes; Base64 biến bytes thành ASCII text. Hai công việc khác nhau.
- **Compression**: giảm dung lượng bằng mô hình lặp/entropy; Base64 thường **tăng dung lượng**.
- **Hash (SHA-256, v.v.)**: phép băm một chiều; kết quả hash bytes có thể được Base64 encode để hiển thị, nhưng Base64 không phải hash.
- **Encryption**: bảo vệ bí mật bằng key; ciphertext bytes có thể được Base64 encode để truyền qua JSON, nhưng Base64 không tạo tính bí mật.
- **Signature/MAC**: kiểm chứng authenticity/integrity; signature bytes có thể được Base64 encode để biểu diễn, nhưng Decoder không kiểm tra signature.

Mẫu phổ biến đúng:
`String → UTF-8 bytes → Base64 encoded String`;
và ngược lại `Base64 String → bytes → UTF-8 String`.
Với file binary, bỏ bước `String` ở hai đầu: `binary bytes → Base64 String → binary bytes`.

## 28. Những lỗi phổ biến

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Coi Base64 là encryption | Ai cũng decode được | Dùng encryption/TLS nếu cần bảo mật |
| Tưởng `=` là dữ liệu hoặc checksum | Chỉ là padding ở cuối | Hiểu nhóm 3 byte / 4 ký tự |
| Thêm `=` cho mọi input bằng tay | Decoder Java có thể tự xử lý thiếu padding; dữ liệu sai có thể bị che | Dùng Decoder phù hợp và policy |
| Cho rằng Java Decoder luôn yêu cầu padding | Java cho phép thiếu padding hợp lệ | Đọc đúng contract JavaDoc |
| Cho rằng mọi padding bị thiếu đều hợp lệ | Nếu đã có `=` nhưng số lượng sai thì từ chối | Dựa vào quy tắc nhóm cuối |
| Coi `YQ=` là tương đương `YQ` | Padding không đầy đủ | `YQ==` hoặc `YQ` |
| Chọn Basic Decoder cho Base64URL chứa `-`/`_` | Sai alphabet | `getUrlDecoder` |
| Chọn URL Decoder cho Basic chứa `+`/`/` | Sai alphabet | `getDecoder` |
| Dùng MIME decoder cho input cần strict | MIME bỏ qua non-alphabet chars | Chọn Basic/URL đúng |
| Dùng `withoutPadding` để đổi sang URL-safe | Nó chỉ bỏ `=` | Dùng `getUrlEncoder` trước |
| Tưởng không padding nghĩa là không đổi length | Vẫn tăng ~33% | Xem công thức size |
| Chuyển binary bytes thành String trước | Dữ liệu nhị phân có thể bị hỏng | Encode chính byte[] |
| Không chỉ rõ charset khi encode text | Round trip text có thể không nhất quán | `StandardCharsets.UTF_8` |
| Decode ảnh/PDF thành String | Bytes không phải text | Xử lý byte[] |
| Dùng stream wrapper nhưng không close | Mất nhóm cuối/padding | Try-with-resources |
| Dùng flush như “kết thúc mã hóa” | Chưa phát hết bytes cuối | Close wrapper đúng thời điểm |
| Không giới hạn kích thước input | Có thể OOM/DoS | Encoded + decoded size limits |
| Dùng `decode(String)` rồi bỏ qua lỗi | Input sai cần báo | Catch `IllegalArgumentException` |
| Trả mảng dest toàn bộ thay vì số bytes ghi | Lẫn bytes chưa dùng | Dùng count returned |
| Quên position/limit của ByteBuffer | Mã hóa nhầm vùng | Kiểm tra remaining |
| Chia sẻ mutable buffer hoặc stream giữa threads | Data race/lẫn dữ liệu | Ownership/đồng bộ |
| Coi decoded JWT payload là verified token | Chưa kiểm chữ ký/claims | Dùng JWT verifier chuyên dụng |
| Log Base64 encoded secret | Vẫn lộ secret | Không log dữ liệu nhạy cảm |
| Dùng MIME cho JSON chỉ vì “cũng là Base64” | Newlines không được chấp nhận ở Basic | Dùng Basic/URL theo schema |
| Tưởng RFC Base64 có một biến thể cho mọi mục đích | Basic, URL-safe, MIME khác nhau | Chốt chuẩn ở hai đầu |

## 29. Checklist khi code review

1. **Nguồn thực sự là byte[] hay String?** Nếu String, charset có chỉ định rõ?
2. **Chọn đúng alphabet** Basic, URL-safe hay MIME theo contract?
3. **Padding expected**: padded, unpadded hay cả hai được chấp nhận?
4. Có hiểu rằng một byte cuối cần `==`, hai byte cần `=`?
5. Dùng `withoutPadding` trên Encoder chứ không tự sửa chuỗi tùy tiện?
6. Decoder đúng biến thể có bắt lỗi `IllegalArgumentException` không?
7. MIME decoder có đang bị dùng ở đường input cần validation chặt không?
8. Chuỗi Base64 có giới hạn length trước decode không?
9. Mảng decoded có kiểm soát size và loại nội dung trước xử lý?
10. Có đúng nơi gọi `new String(bytes, UTF_8)` khi payload là UTF-8?
11. Có tránh biến binary bất kỳ thành String?
12. Nếu ByteBuffer, `position`/`limit` có được xử lý đúng?
13. Nếu decode vào mảng đích, có dùng **số byte trả về**?
14. Nếu stream encode, wrapper có được close để hoàn tất padding?
15. Nếu stream decode, wrapper và input bên dưới có lifecycle rõ?
16. Có log token, mật khẩu hoặc secret đã Base64 encode không?
17. Nếu dữ liệu cần integrity/authenticity, có chữ ký/MAC/AEAD riêng?
18. Nếu cần canonical form, có re-encode và kiểm tra theo giao thức?
19. Có test 0/1/2/3 bytes và input sai padding?
20. Có test ký tự `+ /` với Basic và `- _` với URL-safe?
21. Có test line breaks và ký tự ngoài alphabet khi MIME?
22. Có test Unicode UTF-8 và round trip binary?
23. Có đánh giá memory overhead và cách xử lý payload lớn?
24. Code có chạy đúng JDK tối thiểu mà dự án hỗ trợ không?

## 30. Câu hỏi tự kiểm tra

**Câu 1.** Base64 bảo mật nội dung không?  
**Đáp án:** Không; đây là phép biểu diễn byte bằng ASCII và có thể decode công khai.

**Câu 2.** Một nhóm bao nhiêu byte thành bao nhiêu ký tự?  
**Đáp án:** 3 byte (24 bit) → 4 ký tự dữ liệu Base64 (4 × 6 bit).

**Câu 3.** Một byte còn lại cần bao nhiêu dấu `=` ở dạng padded?  
**Đáp án:** Hai, ví dụ `f → Zg==`.

**Câu 4.** Hai byte còn lại cần bao nhiêu dấu `=`?  
**Đáp án:** Một, ví dụ `fo → Zm8=`.

**Câu 5.** `withoutPadding()` có đổi alphabet không?  
**Đáp án:** Không, chỉ bỏ padding cuối; phải chọn Basic/URL/MIME encoder trước.

**Câu 6.** Java Basic Decoder có chấp nhận `YQ` không?  
**Đáp án:** Có, nó có thể suy ra padding thiếu và decode thành `a`.

**Câu 7.** Java Basic Decoder có chấp nhận `YQ=` không?  
**Đáp án:** Không, vì đã có padding nhưng số lượng sai.

**Câu 8.** Input `Y` có hợp lệ không?  
**Đáp án:** Không, một ký tự dữ liệu không đủ tạo một byte.

**Câu 9.** Basic khác Base64URL ở ký tự nào?  
**Đáp án:** `+`/`/` của Basic được thay bằng `-`/`_`.

**Câu 10.** Muốn tạo chuỗi token Base64URL không padding dùng API gì?  
**Đáp án:** `Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)`.

**Câu 11.** MIME Encoder mặc định xuống dòng bao nhiêu ký tự?  
**Đáp án:** Tối đa 76 ký tự mỗi dòng và phân cách bằng CRLF.

**Câu 12.** MIME Decoder có bỏ qua ký tự không thuộc alphabet không?  
**Đáp án:** Có, kể cả một số dấu câu/dấu cách; vì vậy phải cân nhắc strict input policy.

**Câu 13.** Vì sao `getMimeEncoder(10, separator)` dùng line length 8?  
**Đáp án:** Chiều dài dòng được làm tròn xuống bội số 4.

**Câu 14.** Khi nào phải dùng UTF-8?  
**Đáp án:** Khi nguồn/đích là text Unicode theo UTF-8; binary gốc thì giữ byte[].

**Câu 15.** `encodeToString` trả kiểu gì?  
**Đáp án:** String chứa encoded ASCII characters.

**Câu 16.** `decode(String)` trả kiểu gì?  
**Đáp án:** byte[] gốc.

**Câu 17.** `Encoder.encode(ByteBuffer)` xử lý cả capacity không?  
**Đáp án:** Không, chỉ phần còn lại giữa position và limit.

**Câu 18.** Khi encode vào mảng đích cần chú ý gì?  
**Đáp án:** Mảng đích đủ dung lượng và dùng số bytes thực ghi được trả về.

**Câu 19.** Vì sao `wrap(OutputStream)` cần close?  
**Đáp án:** Để phát nhóm cuối và padding chưa hoàn tất.

**Câu 20.** `Base64.getMimeDecoder()` có thay thế xác thực integrity được không?  
**Đáp án:** Không; còn bỏ qua ký tự ngoài alphabet.

**Câu 21.** Một chuỗi Base64URL có tự là JWT hợp lệ không?  
**Đáp án:** Không; JWT cần cấu trúc và kiểm tra chữ ký/claims riêng.

**Câu 22.** Tăng kích thước Base64 thường là bao nhiêu với dữ liệu lớn?  
**Đáp án:** Khoảng 33%, thêm chi phí MIME/JSON nếu có.

**Câu 23.** Encoder/Decoder Java có thể dùng chung giữa nhiều threads không?  
**Đáp án:** Có, instances được document là thread-safe; không kéo theo wrapped streams hay ByteBuffer mutable cũng thread-safe.

**Câu 24.** Tại sao một protocol vẫn có thể từ chối `YQ` dù Java giải mã được?  
**Đáp án:** Protocol có thể yêu cầu canonical padded form `YQ==`.

## 31. Tóm tắt

- `Base64.Encoder` chuyển byte sang text ASCII; `Base64.Decoder` làm ngược lại. Base64 **không bảo mật**.
- Nhóm 3 byte → 4 ký tự. Input nhóm cuối 1 byte tạo `==`; 2 byte tạo `=` ở dạng padded.
- `withoutPadding()` bỏ `=` khi encode, **không** đổi alphabet hay tạo một loại Decoder mới.
- Java Decoder chấp nhận **thiếu** padding khi 2/3 data chars ở nhóm cuối, nhưng nếu `=` xuất hiện thì số lượng phải chính xác; input sai ném `IllegalArgumentException`.
- Basic dùng `+` và `/`; URL-safe thay bằng `-` và `_`; chọn đúng encoder/decoder.
- MIME dùng dòng tối đa 76 ký tự và CRLF mặc định; MIME decoder **bỏ qua các ký tự ngoài alphabet**, nên không phù hợp làm strict validator khi giao thức yêu cầu chặt.
- Dùng UTF-8 cho **text**, giữ nguyên binary bytes cho ảnh/file; đừng lẫn Base64 với charset hoặc encryption.
- Với dữ liệu lớn, dùng `wrap(OutputStream)`/`wrap(InputStream)` có ownership rõ, và **close encoder wrapper** để hoàn tất padding.
- ByteBuffer methods chỉ xử lý **remaining bytes** và cập nhật position; array-destination methods yêu cầu đủ dung lượng và trả số byte thực ghi.
- Giới hạn input size và xác thực chữ ký/tính nguyên vẹn ở tầng thích hợp. Decoder Base64 thành công **không đồng nghĩa dữ liệu đáng tin**.
- Java `java.util.Base64` có từ **Java 8** và vẫn là lựa chọn chuẩn hiện hành; bài ví dụ dùng Java 17+ để minh họa dễ chạy.

### Tài liệu chính thức

- [Oracle Java SE 26 — `java.util.Base64`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html): ba biến thể Basic, URL-safe, MIME và factories.
- [Oracle Java SE 26 — `Base64.Encoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Encoder.html): `withoutPadding`, `encodeToString`, `encode(ByteBuffer)`, `wrap(OutputStream)`.
- [Oracle Java SE 26 — `Base64.Decoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Decoder.html): optional padding, validation errors, buffer và wrapped stream.
- [Oracle Java SE 8 — `Base64`](https://docs.oracle.com/javase/8/docs/api/java/util/Base64.html): xác nhận Java 8 API cốt lõi.
- [RFC 4648 — Base16, Base32, and Base64 Data Encodings](https://www.rfc-editor.org/rfc/rfc4648): alphabet, padding, Base64URL.
- [RFC 2045 — MIME](https://www.rfc-editor.org/rfc/rfc2045): định dạng Base64 MIME, giới hạn dòng và CRLF.
