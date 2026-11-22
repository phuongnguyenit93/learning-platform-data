# Kiểm thử mã hóa ký tự, số thực, múi giờ và dữ liệu đầu vào khi nâng cấp lên Java 17

**Chủ đề:** Java 17  
**Chương:** Nâng cấp lên Java 17  
**Bài học:** Kiểm thử mã hóa ký tự, số thực, múi giờ và dữ liệu đầu vào

Khi nâng cấp ứng dụng lên Java 17, nhiều lỗi không xuất phát từ thay đổi API mà từ môi trường chạy và cách chương trình diễn giải dữ liệu. Một chuỗi có thể được đọc bằng charset khác, một phép tính số thực có thể cho kết quả khác trên runtime cũ và mới, quy tắc múi giờ có thể thay đổi theo cơ sở dữ liệu timezone, hoặc dữ liệu trước đây được chấp nhận nay bị parse/validate theo cách khác.

Vì vậy, kiểm thử nâng cấp cần đi xa hơn việc xác nhận ứng dụng khởi động và các unit test hiện có đều pass. Cần tạo bộ dữ liệu đầu vào có chủ đích, cố định những yếu tố môi trường có thể kiểm soát, chạy cùng kịch bản trên runtime cũ và Java 17, rồi so sánh kết quả theo hợp đồng của ứng dụng.

Có bốn nhóm cần chú ý:

1. **Mã hóa ký tự:** charset mặc định, UTF-8, dữ liệu Unicode, byte không hợp lệ và việc chuyển đổi giữa byte với String.
2. **Số thực:** ngữ nghĩa dấu phẩy động luôn strict từ Java 17, sai số nhị phân, giá trị biên và phép tính tài chính.
3. **Múi giờ:** timezone database (tzdb), vùng có daylight saving time (DST), khoảng giờ bị bỏ qua hoặc lặp lại, locale và timezone mặc định.
4. **Dữ liệu đầu vào:** parsing, chuẩn hóa Unicode, định dạng ngày/giờ/số, khoảng giá trị, null và dữ liệu sai định dạng.

Bài học này dùng API Java 17 hiện hành như `StandardCharsets`, `java.time`, `Clock`, `BigDecimal`, `CharsetDecoder` và `Locale` tường minh. Mục tiêu là tạo test có thể chạy lặp lại trên nhiều máy và phát hiện thay đổi thực sự ảnh hưởng đến người dùng.

## 1. Xây dựng nguyên tắc kiểm thử khi nâng cấp runtime

Trước khi xem từng nhóm dữ liệu, cần thống nhất cách so sánh. Một kết quả khác nhau giữa hai lần chạy không tự động chứng minh Java 17 có lỗi. Khác biệt có thể đến từ:

- Phiên bản JDK và thư viện chuẩn.
- Hệ điều hành hoặc image/container.
- Charset mặc định của tiến trình.
- Locale và timezone mặc định.
- Phiên bản timezone database.
- Cấu hình JVM, classpath/module path hoặc dependency.
- Dữ liệu fixture không giống nhau.

### 1.1. Dùng cùng fixture trên runtime cũ và Java 17

Tạo một tập fixture cố định cho các tình huống quan trọng. Với mỗi fixture, lưu:

- Dữ liệu đầu vào chính xác (byte, text, số hoặc timestamp).
- Cấu hình charset, locale và timezone nếu có.
- Kết quả kỳ vọng theo hợp đồng.
- Kết quả thực tế trên runtime cũ.
- Kết quả thực tế trên Java 17.
- Phiên bản JDK và môi trường chạy.

Không tạo lại dữ liệu bằng một quy trình khác nhau cho mỗi runtime. Ví dụ, nếu muốn so sánh cách đọc một file UTF-8, hãy dùng đúng cùng một file byte trên cả hai runtime, không tạo file mới bằng charset mặc định của từng máy.

### 1.2. Phân biệt test xác định và test phụ thuộc môi trường

Test xác định nên chỉ rõ charset, locale, timezone và clock. Ví dụ:

- Đọc file bằng `StandardCharsets.UTF_8`.
- Parse số theo `Locale.GERMANY`.
- Tạo thời điểm từ `Instant`.
- Chuyển đổi thời gian bằng `ZoneId.of("Asia/Ho_Chi_Minh")`.
- Dùng `Clock.fixed(...)` cho logic phụ thuộc thời gian hiện tại.

Test phụ thuộc môi trường vẫn cần thiết nếu ứng dụng chủ ý dùng mặc định của máy. Nhưng hãy đặt chúng thành nhóm riêng và chạy trong môi trường CI đại diện cho production. Đừng để một test phụ thuộc timezone của máy developer quyết định tính đúng đắn của logic nghiệp vụ.

### 1.3. So sánh theo hợp đồng, không so sánh mù quáng

Không phải mọi byte hoặc số thập phân phải giống nhau trong mọi tình huống. Hãy xác định kiểu so sánh phù hợp:

| Dữ liệu | Cách so sánh phù hợp |
|---|---|
| File hoặc protocol UTF-8 | So sánh byte nếu hợp đồng yêu cầu byte giống hệt; nếu chỉ yêu cầu văn bản, so sánh chuỗi sau decode |
| Unicode | So sánh code point hoặc dạng chuẩn hóa nếu hợp đồng quy định normalization |
| `double`/`float` | So sánh bit, ULP hoặc tolerance theo yêu cầu tính toán |
| Tiền tệ | So sánh `BigDecimal` theo quy tắc scale/rounding đã công bố |
| Thời điểm tuyệt đối | So sánh `Instant` |
| Giờ địa phương | So sánh local date/time và `ZoneId` theo hợp đồng |
| Input validation | So sánh kết quả chấp nhận/từ chối và loại lỗi được công bố |

Một test tốt phải trả lời được “điều gì được bảo đảm?” trước khi viết assertion.

## 2. Kiểm thử charset và mã hóa ký tự

Charset ánh xạ byte sang ký tự và ngược lại. Nếu chương trình dùng charset mặc định mà không chỉ định rõ, kết quả có thể phụ thuộc hệ điều hành hoặc cấu hình môi trường.

### 2.1. Java 17 vẫn có charset mặc định phụ thuộc môi trường

Điểm quan trọng khi nâng cấp là **Java 17 chưa áp dụng UTF-8 làm charset mặc định phổ quát**. JEP 400 chuẩn hóa UTF-8 làm mặc định từ JDK 18. Trên Java 17, `Charset.defaultCharset()` vẫn có thể phụ thuộc môi trường chạy.

Do đó, không nên giả định ứng dụng chạy Java 17 ở Windows, Linux và container đều dùng cùng charset mặc định. Một chương trình có thể đọc đúng file trên máy phát triển nhưng đọc sai trên máy chủ nếu file và charset mặc định không trùng nhau.

Kiểm tra môi trường bằng:

```java
import java.nio.charset.Charset;

public class CharsetEnvironment {
    public static void main(String[] args) {
        System.out.println("default charset = " + Charset.defaultCharset());
        System.out.println("file.encoding = " + System.getProperty("file.encoding"));
        System.out.println("java.version = " + System.getProperty("java.version"));
        System.out.println("os.name = " + System.getProperty("os.name"));
    }
}
```

Thông tin này hữu ích cho chẩn đoán và ghi nhận môi trường. Nó không thay thế việc chỉ định charset trong code. Không nên dùng việc sửa `file.encoding` như hợp đồng dữ liệu của ứng dụng; API đọc/ghi nên nói rõ charset cần dùng.

### 2.2. Luôn chỉ định charset cho dữ liệu có hợp đồng

Các API có thể dùng charset mặc định nếu không truyền charset, ví dụ:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
```

Hoặc các constructor đọc ký tự từ byte stream mà không chỉ định charset. Nếu dữ liệu được trao đổi giữa hệ thống, lưu trên đĩa hoặc gửi qua mạng, hãy chọn charset theo giao thức và truyền tường minh.

Ví dụ UTF-8:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Với file:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");

Files.writeString(path, "Xin chào Việt Nam", StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
```

Đối với protocol yêu cầu UTF-8, cả hai đầu gửi/nhận phải tuân thủ UTF-8. Không dựa vào charset mặc định của từng JVM.

### 2.3. Tìm các điểm dùng charset mặc định

Khi nâng cấp codebase, tìm các lời gọi không truyền charset, đặc biệt:

- `String.getBytes()` không đối số.
- `new String(byte[])` không truyền charset.
- `InputStreamReader(InputStream)` không truyền charset/decoder.
- `OutputStreamWriter(OutputStream)` không truyền charset/encoder.
- `FileReader` hoặc `FileWriter` constructor không có charset.
- API parsing hoặc thư viện bên thứ ba dùng default charset nội bộ.

Không phải mọi API có default đều sai. Với dữ liệu mang tính nội bộ của máy và được định nghĩa rõ theo môi trường, default có thể là chủ ý. Nhưng với file cấu hình, log cần đọc lại, CSV, HTTP payload, message queue hoặc dữ liệu tích hợp, charset phải là một phần của hợp đồng.

### 2.4. Tạo fixture Unicode có khả năng phát hiện lỗi

Một fixture chỉ có ASCII không đủ để kiểm tra charset vì phần lớn charset phổ biến mã hóa ASCII giống nhau. Hãy có các nhóm ký tự khác nhau:

| Nhóm | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| ASCII | `Hello 123` | Trường hợp cơ bản |
| Tiếng Việt có dấu | `Tiếng Việt: ắ, ệ, ộ` | Ký tự ngoài ASCII |
| Ký tự Latin mở rộng | `Ångström`, `Łódź` | Bảng ký tự mở rộng |
| CJK | `東京`, `中文` | Ký tự ngoài Latin |
| Emoji/supplementary | `🙂`, `𠜎` | Code point ngoài BMP |
| Dạng tổ hợp | `é` và `e` + combining acute accent | Khác biệt biểu diễn Unicode |

Test round-trip UTF-8:

```java
import java.nio.charset.StandardCharsets;

String[] samples = {
    "Hello 123",
    "Tiếng Việt: ắ, ệ, ộ",
    "Ångström và Łódź",
    "東京と中文",
    "🙂 và 𠜎"
};

for (String sample : samples) {
    byte[] encoded = sample.getBytes(StandardCharsets.UTF_8);
    String decoded = new String(encoded, StandardCharsets.UTF_8);

    if (!sample.equals(decoded)) {
        throw new AssertionError("UTF-8 round-trip failed: " + sample);
    }
}
```

Nên bổ sung test đọc/ghi file, stream, HTTP body và message broker nếu ứng dụng có các đường dữ liệu này. Round-trip trên một `String` trong bộ nhớ chưa kiểm tra hết các điểm tích hợp.

### 2.5. Byte không hợp lệ và chính sách decoder

Một luồng byte có thể chứa chuỗi UTF-8 sai định dạng. Nếu decoder thay byte sai bằng ký tự thay thế, ứng dụng có thể âm thầm chấp nhận dữ liệu đã bị biến đổi. Với input cần chính xác, hãy chọn chính sách lỗi rõ ràng.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String value = decoder.decode(ByteBuffer.wrap(inputBytes)).toString();
    process(value);
} catch (CharacterCodingException invalidEncoding) {
    rejectInput(invalidEncoding);
}
```

`REPORT` khiến decoder báo lỗi thay vì âm thầm thay thế dữ liệu. Chính sách `REPLACE` hoặc `IGNORE` chỉ nên dùng khi hợp đồng cho phép mất hoặc thay ký tự.

Kiểm thử ít nhất ba trường hợp:

- Byte UTF-8 hợp lệ.
- Byte sequence bị cắt giữa một ký tự nhiều byte.
- Byte sequence chứa continuation byte hoặc leading byte không hợp lệ.

### 2.6. Unicode normalization và so sánh chuỗi

Hai chuỗi có thể hiển thị giống nhau nhưng có biểu diễn code point khác nhau. Ví dụ ký tự `é` có thể được biểu diễn bằng một code point dựng sẵn hoặc chữ `e` cộng dấu sắc kết hợp.

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "é";

System.out.println(composed.equals(decomposed)); // false

String normalizedA =
        Normalizer.normalize(composed, Normalizer.Form.NFC);
String normalizedB =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(normalizedA.equals(normalizedB)); // true
```

Nếu ứng dụng tìm kiếm, so sánh tên hoặc lưu khóa văn bản, cần xác định normalization form trong hợp đồng. NFC thường phù hợp để chuẩn hóa văn bản tương đương về mặt canonical; NFKC còn áp dụng compatibility normalization và có thể làm thay đổi các khác biệt có ý nghĩa trong một số miền dữ liệu.

Không tự động chuẩn hóa mọi chuỗi. Password, chữ ký số, token, identifier theo giao thức hoặc dữ liệu opaque có thể yêu cầu giữ nguyên byte/code point ban đầu.

### 2.7. String.length() không phải số ký tự người dùng nhìn thấy

Trong Java, `String.length()` đếm UTF-16 code unit. Một code point ngoài BMP chiếm hai code unit. Một ký tự người dùng nhìn thấy cũng có thể gồm nhiều code point, ví dụ emoji có modifier hoặc chuỗi emoji ghép bằng zero-width joiner.

Nếu quy tắc nghiệp vụ nói “tối đa 20 ký tự”, cần định nghĩa rõ đó là:

- 20 UTF-16 code unit.
- 20 Unicode code point.
- 20 grapheme cluster (đơn vị gần với ký tự người dùng nhìn thấy).

Đếm code point:

```java
int codePoints = value.codePointCount(0, value.length());
```

Đây vẫn không phải bộ đếm grapheme cluster. Nếu giới hạn độ dài có ý nghĩa với người dùng, cần dùng quy tắc Unicode phù hợp và test chuỗi có dấu tổ hợp, emoji và ký tự ngoài BMP.

## 3. Kiểm thử số thực khi nâng cấp lên Java 17

Java 17 có một thay đổi ngôn ngữ/runtime đáng chú ý liên quan đến dấu phẩy động: JEP 306 khôi phục ngữ nghĩa **always-strict floating-point**. Từ Java 17, mọi biểu thức dấu phẩy động đều được đánh giá theo ngữ nghĩa strict của Java; modifier `strictfp` không còn cần thiết để yêu cầu hành vi này.

Điều này đặc biệt đáng kiểm tra nếu ứng dụng từng chạy trên JDK cũ và phụ thuộc vào kết quả tính toán dấu phẩy động ở những nền tảng có thể sử dụng extended exponent value set. Trên nhiều hệ thống hiện đại, kết quả có thể không đổi; nhưng khi nâng cấp, nên xác nhận bằng test thay vì giả định.

### 3.1. Ý nghĩa của always-strict

Trước Java 17, Java có khái niệm floating-point value set cho phép một số biểu thức không strict có thể dùng phạm vi số mũ mở rộng trên một số kiến trúc. Điều này có thể khiến kết quả trung gian khác nhau tùy nền tảng.

Từ Java 17, biểu thức dấu phẩy động luôn tuân theo ngữ nghĩa strict. Mục tiêu là làm hành vi phép toán nhất quán hơn giữa các nền tảng. `strictfp` vẫn có thể xuất hiện trong source cũ nhưng không còn cần thiết để ép strict semantics.

Cần phân biệt hai điều:

- Always-strict áp dụng cho cách đánh giá các phép toán dấu phẩy động theo quy tắc Java.
- Nó **không** làm cho `float` hoặc `double` biểu diễn chính xác mọi số thập phân, cũng không biến mọi hàm toán học thành kết quả bit-for-bit giống nhau trên mọi JVM.

Các giá trị `float` và `double` vẫn là số dấu phẩy động nhị phân theo IEEE 754. Sai số làm tròn khi biểu diễn số thập phân vẫn tồn tại.

### 3.2. Kiểm tra số thập phân không biểu diễn chính xác bằng nhị phân

Ví dụ quen thuộc:

```java
double value = 0.1 + 0.2;

System.out.println(value);          // thường hiển thị 0.30000000000000004
System.out.println(value == 0.3);   // false
```

Đây không phải lỗi riêng của Java 17. `0.1` và `0.2` không có biểu diễn hữu hạn chính xác trong hệ nhị phân, nên phép cộng có sai số làm tròn.

Không nên viết test:

```java
assert 0.1 + 0.2 == 0.3;
```

nếu mục tiêu là kiểm tra kết quả số thực theo cách tổng quát. Hãy chọn tiêu chí so sánh phù hợp với độ chính xác nghiệp vụ.

### 3.3. So sánh bằng tolerance

Với phép tính gần đúng, có thể dùng sai số tuyệt đối hoặc kết hợp sai số tương đối:

```java
static boolean nearlyEqual(
        double actual,
        double expected,
        double absoluteTolerance,
        double relativeTolerance) {

    if (Double.doubleToLongBits(actual)
            == Double.doubleToLongBits(expected)) {
        return true;
    }

    if (Double.isNaN(actual) || Double.isNaN(expected)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(actual), Math.abs(expected));

    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );
}
```

Không có một tolerance chung cho mọi bài toán. Ví dụ:

- Đồ họa có thể chấp nhận sai số tương đối nhỏ.
- Tính toán khoa học cần tolerance dựa trên độ ổn định số và sai số thuật toán.
- Hệ thống tiền tệ không nên dùng tolerance để che sai số biểu diễn; hãy dùng kiểu thập phân phù hợp.
- So sánh kết quả thuật toán có yêu cầu tái lập bit chính xác cần kiểm tra bit pattern và điều kiện runtime cụ thể.

Đối với test nâng cấp, ghi rõ tolerance và lý do chọn. Không tăng tolerance chỉ để làm test pass nếu chưa hiểu nguyên nhân khác biệt.

### 3.4. So sánh bit pattern khi hợp đồng yêu cầu chính xác

Có thể quan sát biểu diễn bit của `double`:

```java
long bits = Double.doubleToRawLongBits(value);
System.out.printf("0x%016X%n", bits);
```

Dùng `doubleToRawLongBits` khi cần phân biệt bit pattern, bao gồm payload của NaN. `Double.doubleToLongBits` chuẩn hóa các NaN thành một biểu diễn canonical, nên hai phương thức không hoàn toàn giống nhau trong test bit-level.

So sánh bit phù hợp khi:

- Kiểm tra một thuật toán có kết quả bit-level được quy định.
- Kiểm tra dữ liệu số được serialize theo hợp đồng binary.
- Phát hiện thay đổi rounding trong một pipeline xác định.

Không nên dùng bit equality cho mọi test số thực. Nếu hợp đồng chỉ yêu cầu kết quả nằm trong sai số cho phép, dùng tolerance hoặc ULP phù hợp.

### 3.5. Giá trị biên cần kiểm thử

Bộ test số thực nên bao gồm:

| Trường hợp | Ví dụ | Điều cần xác nhận |
|---|---|---|
| Số hữu hạn thông thường | `1.25`, `-3.5` | Kết quả cơ bản |
| Giá trị rất nhỏ | `Double.MIN_VALUE` | Subnormal và underflow |
| Số chuẩn nhỏ nhất | `Double.MIN_NORMAL` | Ranh giới normal/subnormal |
| Giá trị rất lớn | `Double.MAX_VALUE` | Overflow khi tính toán |
| Dương/vô cực âm | `POSITIVE_INFINITY`, `NEGATIVE_INFINITY` | Quy tắc lan truyền |
| NaN | `Double.NaN` | So sánh và kiểm tra NaN |
| Số 0 có dấu | `0.0`, `-0.0` | Phân biệt sign bit |
| Giá trị gần điểm làm tròn | Các số sát midpoint | Rounding |
| Giá trị sau nhiều phép toán | Tổng tích lũy dài | Sai số tích lũy |

Một số assertion mẫu:

```java
assert Double.isNaN(Double.NaN);
assert Double.isInfinite(1.0 / 0.0);
assert Double.doubleToRawLongBits(0.0)
        != Double.doubleToRawLongBits(-0.0);
assert Double.compare(-0.0, 0.0) < 0;
```

Lưu ý `0.0 == -0.0` trả về true, nhưng hai giá trị có sign bit khác nhau và có thể cho kết quả khác khi thực hiện phép toán như chia. `NaN` không bằng chính nó theo toán tử `==`; dùng `Double.isNaN()` để kiểm tra.

### 3.6. Kiểm tra overflow, underflow và tích lũy sai số

Ví dụ:

```java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = Double.MIN_VALUE / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // có thể thành 0.0
```

Test cần kiểm tra ứng dụng xử lý các kết quả này thế nào. Nếu đầu vào lớn có thể tạo infinity rồi được lưu xuống database hoặc JSON, cần quy định rõ có chấp nhận hay phải từ chối.

Với tổng nhiều giá trị, thứ tự cộng có thể ảnh hưởng kết quả vì phép cộng floating-point không có tính kết hợp tuyệt đối:

```java
double a = (1e16 + -1e16) + 1.0;
double b = 1e16 + (-1e16 + 1.0);

System.out.println(a); // 1.0
System.out.println(b); // có thể là 0.0
```

Nếu code nâng cấp đồng thời thay đổi cách duyệt collection hoặc thứ tự xử lý, kết quả có thể thay đổi dù mỗi phép toán riêng lẻ tuân thủ cùng quy tắc strict. Hãy kiểm thử cả thuật toán và thứ tự dữ liệu.

### 3.7. Phân biệt Math và StrictMath

Always-strict không đồng nghĩa mọi phương thức trong `Math` phải trả về cùng bit pattern trên mọi nền tảng. Đối với một số hàm toán học, Java cho phép implementation có sai số trong giới hạn quy định.

`StrictMath` cung cấp các hàm với yêu cầu reproducibility chặt hơn cho các hàm được đặc tả. Nếu ứng dụng cần kết quả hàm toán học nhất quán giữa các nền tảng theo hợp đồng của API, hãy cân nhắc `StrictMath` và test tương ứng.

Không thay toàn bộ `Math` bằng `StrictMath` một cách máy móc. Hãy xác định nhu cầu tái lập, hiệu năng và độ chính xác của từng thuật toán.

### 3.8. Tiền tệ và số thập phân nên dùng BigDecimal

Nếu domain xử lý giá, thuế, số dư hoặc tỷ lệ tài chính cần quy tắc thập phân rõ ràng, hãy cân nhắc `BigDecimal` thay vì `double`.

Tránh tạo BigDecimal trực tiếp từ double:

```java
BigDecimal wrong = new BigDecimal(0.1);
BigDecimal intended = new BigDecimal("0.1");
BigDecimal alsoUseful = BigDecimal.valueOf(0.1);
```

`new BigDecimal(0.1)` biểu diễn chính xác giá trị double nhị phân đã được làm tròn, nên kết quả có nhiều chữ số hơn mong đợi. Dùng chuỗi thập phân hoặc `BigDecimal.valueOf` khi cần giá trị thập phân theo biểu diễn chuẩn của double.

Phép chia thập phân có thể không có kết quả hữu hạn:

```java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        2,
        RoundingMode.HALF_UP
);
```

Cần xác định rõ scale và `RoundingMode`. Không để rounding mặc định hoặc hành vi ngầm quyết định quy tắc tiền tệ.

### 3.9. equals() và compareTo() của BigDecimal

`BigDecimal.equals()` xét cả giá trị và scale:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
```

Nếu hợp đồng so sánh giá trị số, thường dùng `compareTo() == 0`. Nếu scale có ý nghĩa, ví dụ số chữ số thập phân được lưu theo quy ước, hãy kiểm tra cả scale.

Khi nâng cấp, cần kiểm tra code dùng `BigDecimal` làm key trong `HashMap`/`HashSet`, vì `equals()` và `hashCode()` phân biệt scale.

### 3.10. JEP 306 và modifier strictfp

JEP 306 có hiệu lực từ Java 17 và khôi phục always-strict floating-point semantics. Source cũ có thể còn modifier `strictfp`; compiler Java 17 có thể cảnh báo rằng modifier này không còn cần thiết.

Không cần thêm `strictfp` vào code mới để “sửa” khác biệt. Hãy kiểm tra các kết quả số thực quan trọng trên Java 17, đặc biệt nếu ứng dụng chạy trên nhiều kiến trúc hoặc từng phụ thuộc vào extended precision. Tài liệu tham khảo chính thức nằm ở JEP 306 và JLS 17.


## 4. Kiểm thử múi giờ và timezone database

Múi giờ không chỉ là một độ lệch cố định so với UTC. Một vùng như `Europe/Paris` hoặc `America/New_York` có bộ quy tắc lịch sử và tương lai, bao gồm thay đổi DST do luật pháp. Bộ quy tắc này được phân phối cùng JDK dưới dạng timezone database (tzdb) và có thể được cập nhật giữa các bản JDK.

Khi nâng cấp Java 17, cùng một `LocalDateTime` và `ZoneId` có thể được ánh xạ sang offset hoặc instant khác nếu dữ liệu tzdb mới chứa thay đổi quy tắc. Đây là lý do cần kiểm thử cả thời điểm lịch sử, thời điểm hiện tại và lịch hẹn tương lai.

### 4.1. Phân biệt Instant, LocalDateTime, OffsetDateTime và ZonedDateTime

Các kiểu trong `java.time` biểu diễn các khái niệm khác nhau:

| Kiểu | Ý nghĩa | Dùng khi |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC | Log event, thời điểm tạo bản ghi, timestamp trao đổi |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương, không có zone/offset | Giờ mở cửa hoặc giờ hẹn chưa gắn vùng |
| `OffsetDateTime` | Ngày giờ cùng offset cố định, ví dụ +07:00 | Protocol yêu cầu offset tại thời điểm gửi |
| `ZonedDateTime` | Ngày giờ cùng quy tắc của một `ZoneId` | Lịch theo vùng địa lý, DST và quy tắc địa phương |

Không thay một vùng timezone bằng offset cố định nếu nghiệp vụ cần quy tắc lịch. Ví dụ `Asia/Ho_Chi_Minh` là một vùng có ID và lịch sử quy tắc; `+07:00` chỉ là offset cố định.

Với event đã xảy ra, lưu `Instant` thường phù hợp. Với lịch hẹn tương lai được định nghĩa theo giờ địa phương, thường cần giữ cả local date/time và zone ID, cùng chính sách xử lý gap/overlap.

### 4.2. Vì sao tzdb có thể làm kết quả thay đổi?

Chính phủ có thể thay đổi ngày bắt đầu/kết thúc DST, offset chuẩn hoặc quy tắc của một vùng. Bản cập nhật JDK có thể mang tzdb mới hơn. Vì vậy:

```java
ZoneId zone = ZoneId.of("Region/City");
LocalDateTime local = LocalDateTime.of(2030, 4, 1, 9, 0);

ZonedDateTime resolved = local.atZone(zone);
System.out.println(resolved);
System.out.println(resolved.toInstant());
```

Cùng code và input có thể cho kết quả khác giữa hai bộ tzdb nếu quy tắc của vùng thay đổi. Đây có thể là cập nhật dữ liệu đúng theo luật mới, không nhất thiết là regression của Java.

### 4.3. Ghi nhận phiên bản tzdb đang có

Java cung cấp `ZoneRulesProvider.getVersions(zoneId)` để xem các phiên bản rule có sẵn cho một vùng:

```java
import java.time.ZoneId;
import java.time.zone.ZoneRulesProvider;

String zoneId = "Europe/Paris";

var versions = ZoneRulesProvider.getVersions(zoneId);
System.out.println("tzdb versions = " + versions.keySet());
```

Khi điều tra khác biệt giữa môi trường, ghi nhận phiên bản JDK và danh sách phiên bản rules của các zone quan trọng. Việc này giúp phân biệt code change với tzdb update.

Không nên hard-code một phiên bản tzdb trong logic nghiệp vụ. Mục đích của thông tin phiên bản là chẩn đoán và tái lập test, còn việc cập nhật timezone data cần theo chính sách triển khai của hệ thống.

### 4.4. Kiểm thử DST gap: giờ địa phương không tồn tại

Khi đồng hồ chuyển sang giờ mùa hè, một khoảng giờ địa phương có thể bị bỏ qua. Ví dụ tại một vùng có DST, đồng hồ có thể nhảy từ 01:59 lên 03:00; khi đó 02:30 không tồn tại trong ngày chuyển đổi.

Có thể kiểm tra bằng `ZoneRules.getValidOffsets`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

ZoneId zone = ZoneId.of("Europe/Paris");
ZoneRules rules = zone.getRules();

LocalDateTime local =
        LocalDateTime.of(2024, 3, 31, 2, 30);

var offsets = rules.getValidOffsets(local);

System.out.println(offsets); // danh sách rỗng nếu local time nằm trong gap
```

Trong một gap, danh sách offset hợp lệ rỗng. `ZonedDateTime.of` hoặc `LocalDateTime.atZone` có quy tắc điều chỉnh để đẩy local time về phía sau gap. Ứng dụng cần quyết định liệu đó có phải hành vi nghiệp vụ mong muốn hay nên từ chối input.

Không nên để hành vi mặc định của API vô tình quyết định cách xử lý lịch hẹn. Nếu người dùng nhập giờ không tồn tại, hệ thống có thể:

- Từ chối và yêu cầu chọn giờ khác.
- Điều chỉnh sang thời điểm hợp lệ kế tiếp theo chính sách được công bố.
- Giữ input và yêu cầu xác nhận cách điều chỉnh.

### 4.5. Kiểm thử DST overlap: giờ địa phương xuất hiện hai lần

Khi đồng hồ quay ngược, một khoảng giờ địa phương có thể xuất hiện hai lần với hai offset khác nhau. Trong overlap, `getValidOffsets` thường trả về hai offset hợp lệ:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local =
        LocalDateTime.of(2024, 10, 27, 2, 30);

var offsets = zone.getRules().getValidOffsets(local);

System.out.println(offsets); // hai offset cho hai lần 02:30
```

Hai lần 02:30 này tương ứng với hai instant khác nhau. Nếu chỉ lưu `LocalDateTime`, thông tin chưa đủ để xác định một thời điểm duy nhất.

Có thể chọn offset tường minh:

```java
ZonedDateTime earlier =
        ZonedDateTime.ofLocal(local, zone, null)
                .withEarlierOffsetAtOverlap();

ZonedDateTime later =
        ZonedDateTime.ofLocal(local, zone, null)
                .withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant());
System.out.println(later.toInstant());
```

Test phải xác nhận hệ thống chọn lần xuất hiện nào, hoặc từ chối để người dùng quyết định. Không chỉ kiểm tra chuỗi hiển thị vì hai kết quả có thể cùng hiện “02:30” nhưng khác offset và instant.

### 4.6. Kiểm thử phép cộng thời gian qua DST

`Duration` biểu diễn lượng thời gian trên timeline; `Period` biểu diễn đơn vị lịch. Với `ZonedDateTime`, phép cộng một ngày lịch có thể khác cộng đúng 24 giờ.

Ví dụ:

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris")
);

ZonedDateTime calendarDay = start.plusDays(1);
ZonedDateTime elapsed24Hours = start.plus(Duration.ofHours(24));

System.out.println(calendarDay);
System.out.println(elapsed24Hours);
```

Nếu qua thời điểm chuyển DST, `plusDays(1)` cố giữ giờ địa phương theo lịch, còn `plus(Duration.ofHours(24))` cộng đúng 24 giờ đã trôi qua. Hai kết quả có thể lệch nhau một giờ.

Hãy xác định yêu cầu nghiệp vụ:

- “Ngày mai lúc 12:00 theo giờ địa phương” thường là phép toán lịch.
- “Sau đúng 24 giờ” là phép toán thời lượng.
- “Sau 15 phút” nên tính theo timeline, thường dùng `Duration`.

### 4.7. Không dùng timezone mặc định cho logic nghiệp vụ

`ZoneId.systemDefault()` lấy timezone mặc định của môi trường. Kết quả có thể khác giữa máy developer, CI, container và production.

Nếu nghiệp vụ gắn với một vùng cụ thể, hãy truyền `ZoneId` tường minh:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localBusinessTime =
        instant.atZone(businessZone);
```

Nếu ứng dụng thật sự phải dùng timezone mặc định của máy, hãy kiểm tra cấu hình khi khởi động và log lại giá trị. Không để test vô tình phụ thuộc vào máy chạy.

Có thể chạy test trong CI với timezone cố định:

```bash
java -Duser.timezone=UTC -jar app-tests.jar
```

Sau đó chạy thêm một job với timezone đại diện cho production hoặc các vùng người dùng hỗ trợ. Test UTC không thay thế test DST; nó chỉ tạo một baseline xác định.

### 4.8. Dùng Clock để test logic phụ thuộc thời điểm hiện tại

Tránh gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` trong logic nghiệp vụ khó kiểm thử. Hãy truyền `Clock`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.fixed(
        Instant.parse("2024-06-01T10:15:30Z"),
        ZoneId.of("UTC")
);

LocalDate today = LocalDate.now(clock);
```

Trong production có thể dùng `Clock.system(zone)` hoặc `Clock.systemUTC()`; trong test dùng `Clock.fixed` để tạo thời điểm ổn định. Có thể dùng `Clock.offset` để kiểm tra logic trước/sau một khoảng thời gian mà không phải chờ đồng hồ thật.

### 4.9. Kiểm thử lịch hẹn tương lai và quy tắc thay đổi

Với lịch hẹn tương lai, cần quyết định hệ thống ưu tiên điều gì khi tzdb thay đổi:

- Giữ nguyên instant đã chốt, dù giờ địa phương hiển thị có thể đổi.
- Giữ nguyên giờ địa phương theo vùng, rồi tính lại instant theo rule mới.
- Giữ cả instant đã chốt và zone/local intent để có thể giải thích hoặc yêu cầu xác nhận.

Không có lựa chọn đúng cho mọi sản phẩm. Vé máy bay, cuộc họp định kỳ, lịch phát sóng và lịch mở cửa có thể có yêu cầu khác nhau.

Test nâng cấp cần có fixture cho lịch hẹn tương lai tại vùng có thay đổi rule, sau đó xác nhận chính sách của ứng dụng được áp dụng nhất quán.

## 5. Kiểm thử dữ liệu đầu vào, parsing và validation

Nâng cấp JDK có thể làm lộ các giả định trong cách ứng dụng đọc, chuyển đổi và xác thực dữ liệu. Cần kiểm thử input hợp lệ, input biên và dữ liệu sai định dạng, đặc biệt khi logic phụ thuộc locale, Unicode, charset hoặc timezone mặc định.

### 5.1. Phân biệt parsing và validation

Parsing chuyển dữ liệu từ dạng biểu diễn sang kiểu dữ liệu của chương trình. Validation xác nhận giá trị sau khi parse có thỏa hợp đồng nghiệp vụ hay không.

Ví dụ với số tiền: chuỗi `"1.234,50"` được parse theo locale phù hợp, chuyển thành số thập phân, rồi kiểm tra không âm, không vượt giới hạn và có scale được chấp nhận. Nếu gộp cả ba bước vào một lời gọi parse mặc định, ứng dụng có thể đọc nhầm dấu thập phân hoặc chấp nhận một phần chuỗi không mong muốn.

### 5.2. Locale ảnh hưởng định dạng số và ngày

Không dùng `Locale.getDefault()` làm quy tắc parse cho protocol hoặc file có định dạng cố định. Locale mặc định có thể khác giữa máy developer, CI và production.

| Locale | Ví dụ hiển thị |
|---|---|
| `Locale.US` | `1,234.50` |
| `Locale.GERMANY` | `1.234,50` |
| `Locale.FRANCE` | `1 234,50` |

Khi dữ liệu đầu vào theo định dạng do ứng dụng quy định, hãy chỉ định locale tường minh. Khi dữ liệu là nội dung người dùng nhập theo locale của họ, locale phải là một phần của ngữ cảnh request hoặc user profile.

### 5.3. Parse số theo locale và kiểm tra toàn bộ chuỗi

`NumberFormat.parse` có thể parse phần đầu của chuỗi và để lại phần còn lại. Nếu input phải chứa đúng một số, cần kiểm tra vị trí parse đã tiêu thụ hết chuỗi.

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
DecimalFormat decimalFormat = (DecimalFormat) format;
decimalFormat.setParseBigDecimal(true);

String input = "1.234,50";
ParsePosition position = new ParsePosition(0);
Number parsed = decimalFormat.parse(input, position);

if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}

BigDecimal amount = (BigDecimal) parsed;
```

Test định dạng đúng theo locale, dấu phân cách của locale khác, ký tự thừa ở cuối, khoảng trắng đầu/cuối, dấu âm, số mũ, nhóm chữ số không hợp lệ, chuỗi rỗng và chuỗi chỉ có khoảng trắng. Không dùng parser theo locale hiển thị để đọc protocol máy-to-máy nếu protocol đã quy định cú pháp riêng.

### 5.4. Parse ngày theo formatter tường minh và strict

Với định dạng ngày cố định, hãy chỉ định pattern, locale và resolver style. Dùng ký hiệu year phù hợp cho năm lịch là `uuuu` khi cần strict date parsing:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("2024-02-29", formatter);
```

Test cả ngày nhuận hợp lệ và không hợp lệ: `2024-02-29` hợp lệ; `2023-02-29`, `2024-13-01` và `2024-04-31` không hợp lệ. Chuỗi thiếu chữ số hoặc có ký tự thừa phải bị từ chối theo hợp đồng.

Nếu dùng formatter theo locale, hãy đặt locale rõ ràng và kiểm thử với locale mà sản phẩm hỗ trợ. Đừng để cách parse thay đổi theo `Locale.getDefault()` ngoài ý muốn.

### 5.5. Kiểm tra Unicode whitespace và quy tắc trim

`String.trim()` và `String.strip()` không có cùng quy tắc. `strip()` dựa trên `Character.isWhitespace` và hỗ trợ nhiều dạng whitespace Unicode hơn. Tuy nhiên, không phải mọi ký tự trông như khoảng trắng đều được `Character.isWhitespace` xem là whitespace; ví dụ một số non-breaking space được phân loại khác.

Nếu API cho phép loại bỏ khoảng trắng đầu/cuối, hãy định nghĩa chính xác nhóm code point được chấp nhận. Đừng thay `trim()` bằng `strip()` mà không kiểm thử.

```java
String input = "  hello  ";
String asciiTrimmed = input.trim();
String unicodeStripped = input.strip();
```

Bộ test nên chứa tab, line separator, em space, non-breaking space và các ký tự whitespace mà sản phẩm quyết định hỗ trợ. Với identifier hoặc password, việc tự động strip có thể làm thay đổi dữ liệu; cần có hợp đồng rõ ràng trước khi áp dụng.

### 5.6. Độ dài, code point và ký tự hiển thị

Nếu validation giới hạn độ dài chuỗi, cần xác định đơn vị đo. `String.length()` đếm UTF-16 code unit, không phải số code point hoặc grapheme cluster.

```java
String basic = "A";
String supplementary = "🙂";
String combined = "é";

System.out.println(basic.length());          // 1
System.out.println(supplementary.length());  // 2 UTF-16 code units
System.out.println(combined.length());       // 2 code units
System.out.println(
        supplementary.codePointCount(0, supplementary.length())
); // 1 code point
```

Nếu sản phẩm giới hạn số ký tự người dùng nhìn thấy, cần xử lý grapheme cluster theo Unicode text segmentation. Đừng gọi code point count là “số ký tự hiển thị”.

### 5.7. Kiểm thử surrogate và dữ liệu Unicode sai cấu trúc

Một `String` Java có thể chứa unpaired surrogate dù nó không phải chuỗi Unicode scalar value hợp lệ. Khi encode sang charset, encoder có thể thay thế hoặc báo lỗi tùy cấu hình.

Nếu dữ liệu đến từ parser, file hoặc API có thể chứa chuỗi bất thường, cần quyết định chấp nhận và giữ nguyên UTF-16 code unit, từ chối chuỗi có surrogate không ghép cặp, hay thay thế theo quy tắc đã công bố. Với output cần bảo toàn dữ liệu, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để phát hiện trường hợp không mã hóa được thay vì để thay thế âm thầm.

### 5.8. Validation số và biên kiểu dữ liệu

Khi nâng cấp, kiểm tra các ranh giới của kiểu số và cách chuyển đổi:

- Giá trị nhỏ nhất/lớn nhất của `int` và `long`.
- Giá trị ngoài phạm vi khi parse.
- Chuỗi có dấu cộng/âm, leading zero hoặc exponent.
- Chuyển đổi từ `long` sang `int` có mất dữ liệu.
- Chuyển đổi `BigDecimal` sang integer có làm tròn hoặc bỏ phần thập phân.
- `NaN` và infinity nếu input là số dấu phẩy động.

```java
int value = Integer.parseInt(input);

if (value < 0 || value > 1000) {
    throw new IllegalArgumentException("Value out of range");
}

long source = 3_000_000_000L;
int converted = Math.toIntExact(source); // ArithmeticException
```

`Math.toIntExact` phát hiện overflow thay vì cast im lặng. Test giá trị đúng biên, ngay ngoài biên, chuỗi rỗng, khoảng trắng, ký tự Unicode trông giống chữ số ASCII và chuỗi có phần dư.

### 5.9. Locale ảnh hưởng format output

Không chỉ parse mà format cũng có thể thay đổi theo locale mặc định. Ví dụ `String.format("%,d", value)` có thể dùng locale mặc định của JVM.

Nếu output là giao thức, log máy đọc, CSV chuẩn hoặc dữ liệu snapshot cần ổn định, hãy chỉ định locale:

```java
String stable = String.format(Locale.ROOT, "%,.2f", 1234.5);
```

Với nội dung hiển thị cho người dùng, dùng locale người dùng một cách có chủ đích. Không so sánh output đã format theo locale mặc định trên các máy khác nhau như thể đó là kết quả nghiệp vụ bất biến.

## 6. Bộ kiểm thử hồi quy cho Java 17

Bộ test nên chia thành nhóm độc lập để khi thất bại có thể xác định nguyên nhân nhanh.

| Nhóm | Fixture | Kiểm tra chính |
|---|---|---|
| Charset | UTF-8 tiếng Việt, CJK, emoji | Round-trip và byte output |
| Charset lỗi | Byte sequence UTF-8 không hợp lệ | Decoder báo lỗi hoặc thay thế theo policy |
| Unicode | NFC/NFD, combining mark, supplementary code point | So sánh và giới hạn độ dài |
| Default charset | Windows/Linux/container | Ghi nhận default, xác nhận code không phụ thuộc ngoài ý muốn |
| Floating-point | 0.1 + 0.2, rounding, overflow, underflow | Sai số và always-strict |
| Floating-point đặc biệt | NaN, infinity, signed zero, subnormal | Nhánh xử lý và serialization |
| Decimal | BigDecimal scale, divide, rounding | Kết quả tiền tệ |
| Timezone | UTC, Asia/Ho_Chi_Minh, zone có DST | Instant và local time |
| DST gap/overlap | Giờ không tồn tại hoặc xuất hiện hai lần | Từ chối/điều chỉnh và chọn offset |
| tzdb | Rule lịch sử và tương lai | Phát hiện thay đổi dữ liệu timezone |
| Locale | US, Germany, France | Parse/format số và ngày |
| Input boundary | Min/max, null, rỗng, ký tự thừa | Validation và lỗi có kiểm soát |

### 6.1. Chạy test với nhiều môi trường mặc định

Nếu ứng dụng phụ thuộc vào default locale, timezone hoặc charset ở một số điểm, hãy chạy CI trong ma trận có chủ đích:

- Linux/container với locale UTF-8.
- Windows nếu sản phẩm hỗ trợ.
- Locale US và locale có dấu thập phân khác.
- Timezone UTC và timezone production.
- Java runtime cũ đang hỗ trợ và Java 17.

Mỗi job cần log các thuộc tính môi trường:

```java
System.out.println("charset=" + Charset.defaultCharset());
System.out.println("locale=" + Locale.getDefault());
System.out.println("zone=" + ZoneId.systemDefault());
System.out.println("runtime=" + Runtime.version());
```

Dùng thông tin này để giải thích khác biệt. Không dựa vào một job duy nhất nếu production có nhiều loại node hoặc container image.

### 6.2. Tách test phụ thuộc môi trường khỏi test nghiệp vụ

Một chiến lược tốt là có hai nhóm:

- **Deterministic tests:** truyền charset, locale, zone và clock rõ ràng; cùng fixture phải cho cùng kết quả theo hợp đồng.
- **Environment integration tests:** xác nhận ứng dụng hoạt động đúng trong các cấu hình máy thực tế và ghi nhận default đang được chọn.

Không đặt toàn bộ test vào một suite phụ thuộc môi trường vì khi CI thay locale hoặc timezone, test không liên quan cũng có thể thất bại.

### 6.3. Dùng golden fixture có kiểm soát

Với dữ liệu quan trọng, lưu fixture ở dạng byte hoặc text đã xác định encoding. Ví dụ file UTF-8 có ký tự tiếng Việt/emoji, payload số với locale đã định nghĩa, timestamp UTC và lịch hẹn local có zone ID, giá trị số thực có expected tolerance/bit pattern và bộ input hợp lệ/không hợp lệ cho parser.

Nếu fixture là file văn bản, ghi rõ encoding ngay trong tài liệu test. Tránh tạo fixture bằng editor có encoding tự động mà không xác nhận byte.

### 6.4. Kiểm thử trên cả runtime cũ và Java 17

Trong giai đoạn nâng cấp, chạy cùng bộ fixture trên runtime cũ đang được hỗ trợ, Java 17 với cùng OS/container và dependency khi có thể, và các nền tảng production khác nếu có.

Phân loại mỗi khác biệt:

- **Expected runtime change:** ví dụ strict floating-point semantics từ Java 17.
- **Environment difference:** charset, locale, timezone hoặc tzdb khác.
- **Application regression:** code hoặc dependency mới làm thay đổi hành vi ngoài hợp đồng.
- **Existing defect exposed:** test mới phát hiện giả định sai đã tồn tại từ trước.

Không nên sửa expected output để che khác biệt trước khi xác định nó thuộc nhóm nào.

## 7. Ví dụ: cố định thời gian trong một test

Một hàm tính ngày hết hạn có thể nhận `Clock` và `ZoneId` thay vì tự đọc đồng hồ hoặc timezone hệ thống:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

final class ExpiryPolicy {
    private final Clock clock;
    private final ZoneId businessZone;

    ExpiryPolicy(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    LocalDate expiryDate(int validDays) {
        return LocalDate.now(clock.withZone(businessZone))
                .plusDays(validDays);
    }
}
```

Test có thể cố định instant:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-06-01T23:30:00Z"),
        ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(
        fixed,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate expiry = policy.expiryDate(7);
```

Vì instant là 23:30 UTC, ngày tại Ho Chi Minh City đã sang ngày kế tiếp. Test này xác nhận logic tính ngày dùng timezone nghiệp vụ, không dùng timezone ngẫu nhiên của máy CI.

## 8. Những lỗi thường gặp khi nâng cấp

1. **Giả định Java 17 mặc định UTF-8:** default charset vẫn phụ thuộc môi trường; UTF-8 trở thành default chuẩn hóa từ Java 18.
2. **Chỉ test bằng ASCII:** bổ sung tiếng Việt có dấu, CJK, emoji và chuỗi Unicode tổ hợp.
3. **Âm thầm thay byte không hợp lệ:** với input cần chính xác, cấu hình `REPORT` và test lỗi encoding.
4. **Cho rằng always-strict làm số thập phân chính xác:** JEP 306 không thay đổi bản chất biểu diễn nhị phân của `float`/`double`.
5. **Dùng equality tuyệt đối cho mọi double:** xác định tolerance/ULP và kiểm thử NaN, infinity, signed zero riêng.
6. **Dùng double cho tiền tệ:** dùng `BigDecimal`, quy định scale và rounding tại các bước nghiệp vụ.
7. **Coi offset là timezone:** offset cố định không chứa lịch sử hoặc quy tắc DST; dùng `ZoneId` cho lịch theo vùng.
8. **Coi một ngày luôn bằng 24 giờ:** phân biệt phép tính `Period`/ngày lịch với `Duration`/thời lượng.
9. **Dùng timezone mặc định trong test:** dùng `Clock.fixed` và `ZoneId` tường minh.
10. **Parse số/ngày theo Locale mặc định:** chỉ định locale và formatter theo hợp đồng.
11. **Dùng String.length() làm số ký tự hiển thị:** xác định giới hạn theo code unit, code point hay grapheme cluster.
12. **Chỉ test happy path:** tạo negative test cho input sai định dạng, ngoài biên, null, ký tự thừa và ngày DST bất thường.

## 9. Checklist trước khi chuyển production sang Java 17

- [ ] Xem xét mọi điểm đọc/ghi byte mà không chỉ định charset.
- [ ] Chỉ định UTF-8 hoặc charset đúng theo hợp đồng cho file và protocol.
- [ ] Có fixture Unicode tiếng Việt, CJK, emoji và normalization.
- [ ] Có test decoder với byte sequence sai định dạng.
- [ ] Ghi nhận default charset trong từng môi trường hỗ trợ.
- [ ] Kiểm thử số thực trên Java 17, bao gồm rounding và giá trị biên.
- [ ] Rà soát thuật toán từng phụ thuộc extended precision hoặc modifier `strictfp`.
- [ ] Dùng `BigDecimal` cho số thập phân cần quy tắc tài chính rõ.
- [ ] Quy định tolerance/ULP hoặc bit-level expectation cho từng nhóm phép tính.
- [ ] Kiểm tra `NaN`, infinity, signed zero, overflow và underflow.
- [ ] Dùng `Instant` cho timestamp tuyệt đối và `ZoneId` cho lịch theo vùng.
- [ ] Kiểm thử DST gap/overlap cho các vùng có DST.
- [ ] Ghi nhận tzdb version khi điều tra sự cố.
- [ ] Dùng `Clock` có thể thay thế trong logic phụ thuộc thời điểm hiện tại.
- [ ] Chỉ định locale cho parse/format theo hợp đồng.
- [ ] Kiểm thử input đúng, sai, biên và Unicode whitespace.
- [ ] Chạy cùng fixture trên runtime cũ và Java 17 trước khi chốt kết quả.

## 10. Bài tập tự luyện

### Bài 1. Charset mặc định

Một ứng dụng chạy Java 17 trên Windows đọc file UTF-8 bằng constructor không chỉ định charset. Trên Linux file được đọc đúng, còn trên Windows xuất hiện ký tự lỗi.

**Đáp án:** Hai môi trường có thể có default charset khác nhau. Chỉ định `StandardCharsets.UTF_8` khi đọc file và kiểm thử bằng cùng một fixture byte.

### Bài 2. Java 17 và số thực

Một test so sánh `0.1 + 0.2 == 0.3` thất bại trên cả Java 17 và runtime cũ.

**Đáp án:** Đây là đặc tính biểu diễn nhị phân của số thực, không phải riêng thay đổi JEP 306. Dùng tolerance phù hợp hoặc kiểu thập phân như `BigDecimal` nếu domain yêu cầu.

### Bài 3. Always-strict

Vì sao nên kiểm thử lại thuật toán số thực khi nâng cấp Java 17 dù code không đổi?

**Đáp án:** Java 17 khôi phục always-strict floating-point semantics. Những ứng dụng từng phụ thuộc extended exponent value set trên nền tảng cũ có thể quan sát khác biệt ở kết quả trung gian.

### Bài 4. BigDecimal

`new BigDecimal(0.1)` và `new BigDecimal("0.1")` có giống nhau không?

**Đáp án:** Không. Constructor nhận double giữ chính xác giá trị nhị phân đã làm tròn của double; constructor nhận chuỗi tạo giá trị thập phân 0.1 theo chuỗi đầu vào.

### Bài 5. DST gap

Một người dùng đặt lịch vào 02:30 trong ngày đồng hồ nhảy từ 02:00 lên 03:00.

**Đáp án:** Local time này không tồn tại trong vùng đó. Dùng `ZoneRules.getValidOffsets()` để nhận biết gap và áp dụng policy từ chối, điều chỉnh hoặc yêu cầu xác nhận.

### Bài 6. DST overlap

Một người dùng đặt lịch 02:30 vào ngày đồng hồ quay ngược và giờ này xuất hiện hai lần.

**Đáp án:** Có hai offset/instant hợp lệ. Ứng dụng cần chọn lần sớm, lần muộn hoặc yêu cầu người dùng xác nhận.

### Bài 7. Một ngày và 24 giờ

Một job cần chạy mỗi ngày lúc 09:00 theo giờ địa phương. Nên mô hình hóa lịch bằng `Duration.ofHours(24)` hay phép toán ngày lịch?

**Đáp án:** Lịch theo giờ địa phương cần phép toán lịch với `ZoneId`, vì ngày DST có thể không dài đúng 24 giờ. `Duration` phù hợp với thời lượng đã trôi qua.

### Bài 8. Locale parsing

Chuỗi `1.234,50` được gửi theo định dạng Đức nhưng server dùng Locale.US.

**Đáp án:** Parse theo locale của hợp đồng hoặc ngữ cảnh dữ liệu, không dùng `Locale.getDefault()`. Kiểm tra parser đã tiêu thụ toàn bộ chuỗi.

### Bài 9. Độ dài chuỗi

Một emoji có `String.length()` bằng 2. Điều đó có nghĩa người dùng nhìn thấy hai ký tự không?

**Đáp án:** Không. Nó có thể là một Unicode code point được mã hóa bằng hai UTF-16 code unit. Grapheme cluster còn là một đơn vị khác.

### Bài 10. Thiết kế test nâng cấp

Cần so sánh ứng dụng cũ và Java 17 nhưng kết quả ngày giờ khác nhau trên CI.

**Đáp án:** Ghi nhận JDK, tzdb, timezone và locale; dùng cùng fixture; cố định `Clock` và `ZoneId`; xác định khác biệt đến từ rule data hay code.

## 11. Tài liệu tham khảo chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ JDK 18, hữu ích để phân biệt Java 17 với các bản JDK mới hơn.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): thay đổi floating-point semantics được áp dụng trong Java 17.
- [JDK 17 API — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): charset mặc định và API mã hóa ký tự.
- [JDK 17 API — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý malformed/unmappable input.
- [JDK 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác, scale và rounding.
- [JDK 17 API — java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): kiểu ngày giờ hiện đại.
- [JDK 17 API — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): offset hợp lệ, transition, gap và overlap.
- [JDK 17 API — ZoneRulesProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): cung cấp và xem phiên bản timezone rules.
- [JDK 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): clock có thể thay thế để kiểm thử thời gian.
- [JDK 17 API — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale và các quy tắc định dạng theo ngôn ngữ/vùng.
- [JDK 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.

**Ghi nhớ:** Khi nâng cấp lên Java 17, hãy kiểm tra charset vì UTF-8 chưa phải default bắt buộc trên mọi môi trường; kiểm tra số thực vì JEP 306 đưa mọi phép toán về always-strict; kiểm tra timezone vì tzdb có thể thay đổi giữa các JDK; và kiểm tra parsing/validation với locale, Unicode cùng dữ liệu biên. Dùng charset, locale, zone và clock tường minh cho test xác định, sau đó chạy thêm test tích hợp trên môi trường production đại diện.



