# Kiểm thử chuỗi tiếng Việt, ký tự bổ sung và dữ liệu rỗng

## 1. Vì sao chuỗi ASCII chưa đủ để kiểm tra mã hóa?

Một hàm xử lý chuỗi có thể chạy đúng với `"Hello"` nhưng sai với tên `"Đặng"`, chữ có dấu kết hợp hoặc một ký tự nằm ngoài phạm vi một `char`.

Các dữ liệu đó làm lộ những giả định thường bị che khuất:

- Một ký tự luôn chiếm một byte.
- Một `char` luôn biểu diễn trọn vẹn một ký tự Unicode.
- Hai chuỗi trông giống nhau luôn có cùng dữ liệu.
- Chuỗi rỗng, khoảng trắng và null là một trường hợp.
- Encode rồi decode có kết quả giống ban đầu là đủ chứng minh mọi thứ đúng.

Bài này xây một tập kiểm thử nhỏ nhưng có mục đích rõ cho ba nhóm: **tiếng Việt, ký tự bổ sung và dữ liệu rỗng**. Kiến thức áp dụng cho Java hiện đại; các API gắn với Java 6 như `String.isEmpty()`, constructor nhận `Charset` và `Normalizer` vẫn có thể được học bằng một JDK mới.

Ví dụ chạy dùng JDK 17+; một số tiện ích như `StandardCharsets` hoặc `isBlank()` được bổ sung sau Java 6. Không coi toàn bộ mã minh họa là mã chỉ dùng API Java 6.

## 2. Trước khi viết test, xác định đang đo đơn vị nào

| Đại lượng | Ví dụ API | Ý nghĩa |
| --- | --- | --- |
| Số byte UTF-8 | `text.getBytes(UTF_8).length` | Dung lượng biểu diễn theo UTF-8 |
| Số đơn vị mã UTF-16 | `text.length()` | Số vị trí `char` trong String |
| Số code point | `text.codePointCount(0, text.length())` | Số giá trị Unicode mà thao tác nhận diện trong phạm vi |
| Số cụm ký tự hiển thị | Cơ chế phân đoạn theo yêu cầu | Gần với đơn vị người dùng cảm nhận; không tự bằng ba số trên |

Ví dụ với `U+1F600`:

```text
UTF-8: 4 byte
String.length(): 2 đơn vị mã UTF-16
Số code point: 1
```

Với chữ `ế`:

```text
Dạng dựng sẵn: U+1EBF
Dạng phân rã:  U+0065 U+0302 U+0301
```

Hai dạng có thể thể hiện cùng một chữ khi hiển thị, nhưng có số code point và chuỗi đơn vị mã khác nhau.

Vì vậy, tên một test như “độ dài đúng” là chưa đủ. Cần ghi rõ đang kiểm số byte, số `char`, số code point hay giới hạn theo ký tự hiển thị.

Đếm code point cũng không tự kiểm chứng dữ liệu UTF-16 hợp lệ: một String có surrogate không ghép cặp vẫn có thể tồn tại. Nếu cần xác nhận nó mã hóa được nghiêm ngặt sang UTF-8, phải kiểm tra bằng cơ chế phù hợp.

## 3. Lập bảng dữ liệu có khả năng bắt lỗi

Một bảng đầu vào hữu ích:

| Nhóm | Dữ liệu | Lỗi muốn phát hiện |
| --- | --- | --- |
| Đường cơ sở | `"abc"` | Lỗi xử lý thông thường |
| Tiếng Việt | `"Tiếng Việt"` | Mất dấu, chọn charset sai, nhầm byte với char |
| Chữ Đ | `"Đặng"` | Bộ lọc/ánh xạ sai ký tự tiếng Việt |
| Dấu dựng sẵn | `U+1EBF` | Đường xử lý ký tự có dấu |
| Dấu phân rã | `U+0065 U+0302 U+0301` | Giả định “trông giống là equals” hoặc cắt giữa dấu |
| Ký tự bổ sung | `U+1F600` | Cắt surrogate pair hoặc đếm theo char |
| Chuỗi hỗn hợp | `A + U+1F600 + B` | Sai chỉ số tại ranh giới BMP/ký tự bổ sung |
| Rỗng | `""`, `byte[0]` | Sai biên, cố truy cập phần tử đầu |
| Khoảng trắng | space, tab, xuống dòng | Nhầm empty với blank |
| Không có giá trị | `null` | Hợp đồng null không rõ |
| Byte lỗi | UTF-8 không hợp lệ | Thay thế âm thầm hoặc kiểm tra lỗi sai |
| UTF-16 lỗi | Surrogate không ghép cặp | Cắt chuỗi làm hỏng dữ liệu |

Không cần nhân bản hàng trăm mẫu chỉ khác nhau về chữ cái thông thường. Nên có ít nhất một mẫu cho mỗi cơ chế sai có khả năng xảy ra.

Dữ liệu lỗi trong bảng không phải dữ liệu “bắt buộc phải chấp nhận”. Test phải đối chiếu đúng chính sách: thay thế có kiểm soát, báo lỗi hay từ chối ở một ranh giới đã định.

## 4. Kiểm thử tiếng Việt cần ít nhất hai kiểu so sánh

### 4.1. So sánh chính xác để bảo toàn dữ liệu

Nếu một hàm có nhiệm vụ encode/decode hoặc chuyển tiếp nguyên văn, kỳ vọng thường là:

```text
chuỗi nhận được equals chuỗi ban đầu
```

Không tự normalize, trim hoặc bỏ dấu trong test chỉ để nó vượt qua. Những thao tác đó có thể che mất thay đổi dữ liệu không được phép.

Đặc biệt, cần có một mảng byte UTF-8 đã biết làm đối chứng. Nếu chỉ dùng một hàm encode và một hàm decode cùng mắc một giả định sai, kiểm thử đi-về vẫn có thể vượt qua.

Ví dụ `ế` có UTF-8 đã biết:

```text
U+1EBF → E1 BA BF
```

Test cần kiểm cả chiều:

- Byte `E1 BA BF` được giải mã thành `U+1EBF`.
- `U+1EBF` được mã hóa thành đúng ba byte đó.

### 4.2. So sánh tương đương sau chuẩn hóa khi yêu cầu cần

Hai giá trị:

```text
U+1EBF
U+0065 U+0302 U+0301
```

không bằng nhau theo `String.equals` vì khác chuỗi đơn vị mã. Nếu nghiệp vụ yêu cầu coi hai dạng tương đương chuẩn tắc, có thể normalize cả hai về NFC trước khi so sánh.

Ví dụ minh họa:

```java
boolean equivalent = Normalizer.normalize(left, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(right, Normalizer.Form.NFC));
```

Đoạn này giả sử đã có `left`, `right` hợp lệ và import `java.text.Normalizer`.

Điều cần kiểm là **quy tắc nghiệp vụ**, không phải một quy tắc “normalize mọi thứ cho chắc”. Nội dung chữ ký, dữ liệu cần bảo toàn nguyên văn hoặc phép so sánh byte có thể yêu cầu giữ đúng biểu diễn ban đầu.

Chuẩn hóa Unicode cũng không đồng nghĩa bỏ dấu, chuyển hoa/thường hoặc so sánh theo ngôn ngữ. Đó là các yêu cầu riêng.

### 4.3. Không bỏ qua chữ Đ

Chỉ thử vài nguyên âm có dấu có thể bỏ sót logic xử lý sai `Đ`/`đ`. Một tập mẫu tiếng Việt nên chứa nhóm chữ này nếu hệ thống phải hỗ trợ tên hoặc văn bản tiếng Việt đầy đủ.

Trong ví dụ, tên `Đặng` có bốn đơn vị mã UTF-16 nhưng bảy byte UTF-8:

```text
Đ: C4 90
ặ: E1 BA B7
n: 6E
g: 67
```

Đây cũng là một đối chứng độc lập để phát hiện chọn sai bảng mã.

## 5. Kiểm thử ký tự bổ sung và ranh giới cắt

Ký tự bổ sung là ký tự có code point lớn hơn `U+FFFF`. Trong String, nó được biểu diễn bằng một cặp surrogate gồm hai `char`.

Vì vậy, một hàm có dạng:

```java
String first = value.substring(0, 1);
```

có thể lấy một ký tự BMP hoàn chỉnh nhưng chỉ lấy nửa đầu surrogate pair khi chuỗi bắt đầu bằng một ký tự bổ sung. Đoạn này không nhất thiết ném lỗi; nó có thể tạo String chứa dữ liệu UTF-16 không hợp lệ.

Một test tốt không chỉ kiểm `first.length()==1`. Cần kiểm kỳ vọng thực tế:

- Nếu muốn lấy một code point, ranh giới cần được tính theo code point.
- Nếu muốn lấy một ký tự hiển thị, cần quy tắc phân đoạn phù hợp; code point có thể chưa đủ.
- Nếu đầu ra phải mã hóa UTF-8 hợp lệ, thử encoder nghiêm ngặt để phát hiện surrogate không ghép cặp.

Ví dụ với chuỗi hỗn hợp:

```text
A + U+1F600 + B

Vị trí char:
0: A
1: high surrogate
2: low surrogate
3: B
```

Muốn trích code point thứ hai, ranh giới char là 1 và 3, không phải 1 và 2.

Có thể tính bằng `offsetByCodePoints` rồi gọi `substring`. Cách này tránh cắt surrogate pair cho code point đã chọn, nhưng không bảo đảm giữ nguyên mọi cụm hiển thị gồm nhiều code point.

## 6. Phân biệt empty, blank và null

### Chuỗi và byte rỗng

`""` là một String hợp lệ có độ dài 0. `new byte[0]` là một mảng byte hợp lệ không có phần tử.

Với UTF-8:

```text
String rỗng → 0 byte
0 byte → String rỗng
```

Các test nên xác nhận hàm xử lý rỗng không cố lấy `charAt(0)`, byte đầu tiên hoặc ranh giới không tồn tại.

### Khoảng trắng

`" "` không rỗng. Nó chứa một code point space. Một chuỗi gồm space, tab và xuống dòng có thể là blank theo định nghĩa của `String.isBlank()`.

Không thay một yêu cầu “không rỗng” thành “không blank” nếu nghiệp vụ không yêu cầu; hai điều kiện chấp nhận dữ liệu khác nhau.

Khi mở rộng ngoài space ASCII, cần đọc định nghĩa khoảng trắng của API. “Nhìn trống trên màn hình” không đủ để kết luận một code point được `isBlank()` coi là khoảng trắng.

### Null

Null là không có tham chiếu tới một đối tượng String/mảng; nó không phải String có độ dài 0.

Trước khi kiểm thử, chọn hợp đồng:

| Hợp đồng | Kỳ vọng test |
| --- | --- |
| Không cho null | Báo lỗi rõ tại ranh giới |
| Có nhận null và giữ nghĩa “thiếu” | Kết quả giữ được sự khác biệt với rỗng |
| Chủ động chuyển null thành rỗng | Test xác nhận chính sách này là yêu cầu, không phải tác dụng phụ |

Ví dụ trong bài chọn **từ chối mảng null** trong hàm giải mã nghiêm ngặt, đồng thời chấp nhận mảng không có byte. Không dùng một trường hợp để thay cho trường hợp còn lại.

## 7. Bộ kiểm thử Java độc lập, không cần thư viện ngoài

Tệp `UnicodeStringChecks.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.Objects;

public final class UnicodeStringChecks {
    private static int checks;

    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static String decodeStrict(byte[] bytes)
            throws CharacterCodingException {
        Objects.requireNonNull(bytes, "bytes");
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    private static byte[] encodeStrict(String value)
            throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(value));
        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        return result;
    }

    public static void main(String[] args) throws Exception {
        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        check(vietnamese.length() == 10, "Vietnamese UTF-16 units");
        check(vietnamese.getBytes(StandardCharsets.UTF_8).length == 14,
                "Vietnamese UTF-8 bytes");

        String composed = "\u1EBF";
        String decomposed = "e\u0302\u0301";
        check(!composed.equals(decomposed), "exact equality is different");
        check(composed.length() == 1 && decomposed.length() == 3,
                "normalization forms have different lengths");
        check(Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                .equals(composed), "NFC equality");
        byte[] known = {(byte) 0xE1, (byte) 0xBA, (byte) 0xBF};
        check(decodeStrict(known).equals(composed), "known UTF-8 bytes");
        check(Arrays.equals(encodeStrict(composed), known),
                "known UTF-8 encoding");
        String name = "\u0110\u1EB7ng";
        byte[] nameBytes = {
                (byte) 0xC4, (byte) 0x90,
                (byte) 0xE1, (byte) 0xBA, (byte) 0xB7, 0x6E, 0x67
        };
        check(name.length() == 4, "Vietnamese D with stroke");
        check(name.getBytes(StandardCharsets.UTF_8).length == 7,
                "Vietnamese name UTF-8 bytes");
        check(decodeStrict(nameBytes).equals(name),
                "Vietnamese name known UTF-8 bytes");
        System.out.println("PASS vietnamese");

        String emoji = new String(Character.toChars(0x1F600));
        check(emoji.length() == 2, "supplementary UTF-16 units");
        check(emoji.codePointCount(0, emoji.length()) == 1,
                "supplementary code point");
        check(emoji.getBytes(StandardCharsets.UTF_8).length == 4,
                "supplementary UTF-8 bytes");
        check(Character.isSurrogatePair(emoji.charAt(0), emoji.charAt(1)),
                "surrogate pair");
        String mixed = "A" + emoji + "B";
        int start = mixed.offsetByCodePoints(0, 1);
        int end = mixed.offsetByCodePoints(start, 1);
        check(mixed.substring(start, end).equals(emoji),
                "slice one complete code point");

        String broken = emoji.substring(0, 1);
        check(broken.length() == 1
                && Character.isHighSurrogate(broken.charAt(0)),
                "broken slice contains high surrogate");
        boolean rejectedBroken = false;
        try {
            encodeStrict(broken);
        } catch (CharacterCodingException expected) {
            rejectedBroken = true;
        }
        check(rejectedBroken, "strict encoder rejects unpaired surrogate");
        System.out.println("PASS supplementary");

        check("".isEmpty(), "empty string");
        check("".length() == 0, "empty UTF-16 length");
        check("".codePointCount(0, 0) == 0, "empty code point count");
        check(encodeStrict("").length == 0, "empty encoding");
        check(decodeStrict(new byte[0]).isEmpty(), "empty decoding");
        check(!" ".isEmpty(), "space is not empty");
        check(" \t\n".isBlank(), "ASCII whitespace is blank");
        check(!"a".isBlank(), "letter is not blank");
        boolean rejectedNull = false;
        try {
            decodeStrict(null);
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }
        check(rejectedNull, "null differs from empty input");
        System.out.println("PASS empty-and-null");

        String[] samples = {
                "", vietnamese, composed, decomposed, emoji, mixed
        };
        for (String sample : samples) {
            check(decodeStrict(encodeStrict(sample)).equals(sample),
                    "exact UTF-8 round trip");
        }
        System.out.println("PASS round-trip");

        byte[] invalid = {(byte) 0xC3, 0x28};
        boolean rejectedBytes = false;
        try {
            decodeStrict(invalid);
        } catch (CharacterCodingException expected) {
            rejectedBytes = true;
        }
        check(rejectedBytes, "strict decoder rejects malformed UTF-8");
        check(new String(invalid, StandardCharsets.UTF_8)
                .equals("\uFFFD("), "constructor replacement policy");
        System.out.println("PASS malformed");
        System.out.println("checks=" + checks);
    }
}
```

### Vì sao mã dùng Unicode escape?

Các literal như `"Ti\u1EBFng Vi\u1EC7t"` trong tệp Java biểu diễn `Tiếng Việt` mà không phụ thuộc việc editor có giữ đúng các ký tự đó khi lưu mã nguồn.

Các escape là cách viết mã nguồn; chúng không có nghĩa dữ liệu lúc chạy chứa nguyên các ký tự gạch chéo, chữ u và số.

Trong kiểm thử tích hợp, vẫn cần có dữ liệu tiếng Việt thực được lưu trong fixture/tệp/request theo đúng charset để kiểm cả đường truyền và cấu hình đọc thực tế. Escape trong mã nguồn không kiểm thử thay cho việc giải mã một tệp bên ngoài.

### Vì sao không dùng từ khóa assert?

Hàm `check` tự ném `AssertionError` khi sai, nên các kiểm tra luôn chạy, không cần bật `-ea`.

Nếu chuyển sang JUnit, có thể tách thành các test/parameterized test và dùng assertion của JUnit. Bộ ví dụ độc lập ở đây giúp chạy trực tiếp bằng `javac`/`java` mà không cần thiết lập dependency trước.

### Vì sao có encoder và decoder REPORT?

Các API tiện lợi như constructor String nhận Charset có thể thay dữ liệu lỗi. Nếu test chỉ nhìn thấy “có một String được tạo”, có thể bỏ sót lỗi.

Hai hàm strict trong ví dụ làm chính sách từ chối lỗi tường minh và tạo đối tượng encoder/decoder riêng cho mỗi thao tác. Không dùng chung một đối tượng có trạng thái giữa nhiều luồng.

## 8. Biên dịch, chạy và stdout

Từ thư mục chứa tệp, dùng JDK 17+:

```powershell
javac --release 17 -d out UnicodeStringChecks.java
java -cp out UnicodeStringChecks
```

Chỉ chạy lệnh thứ hai nếu biên dịch thành công.

Stdout:

```text
PASS vietnamese
PASS supplementary
PASS empty-and-null
PASS round-trip
PASS malformed
checks=34
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm tra trên JDK 24.0.2.

Nếu một kiểm tra sai, chương trình ném `AssertionError` với nhãn của phép kiểm và không in kết quả PASS cho các nhóm chưa vượt qua. Không bắt lỗi assertion rồi vẫn in một dòng thành công chung.

### 34 phép kiểm chứng minh gì?

| Nhóm | Bằng chứng chính |
| --- | --- |
| Vietnamese | Độ dài, byte UTF-8 đã biết, dạng dựng sẵn/phân rã, NFC và chữ Đ |
| Supplementary | Cặp surrogate, số byte/code point, trích ranh giới đúng và từ chối nửa cặp |
| Empty-and-null | Rỗng hợp lệ, khoảng trắng khác rỗng, null bị từ chối |
| Round-trip | Sáu mẫu giữ nguyên dữ liệu khi mã hóa/giải mã UTF-8 nghiêm ngặt |
| Malformed | Byte lỗi bị từ chối trong chế độ strict; constructor thay thế theo hợp đồng |

Số 34 chỉ mô tả bộ mã đã cung cấp, không phải thước đo rằng mọi hệ thống có 34 test là đầy đủ.

## 9. Hiểu kiểm thử đi-về và giới hạn của nó

Một tính chất hữu ích là:

```text
decodeUTF8(encodeUTF8(text)) equals text
```

Điều kiện của bộ ví dụ là các mẫu đầu vào có biểu diễn UTF-16 hợp lệ và cả hai chiều đều dùng UTF-8 nghiêm ngặt.

Đối với dữ liệu phân rã, kỳ vọng là giữ nguyên chuỗi phân rã nếu nhiệm vụ là chuyển đổi bảo toàn nguyên văn. Việc kết quả nhìn giống dạng dựng sẵn chưa đủ; `equals` giúp kiểm dữ liệu chính xác.

Nhưng kiểm thử đi-về chưa đủ vì:

1. Hai chiều có thể cùng dùng sai bảng mã so với giao thức bên ngoài.
2. Nó chưa đối chiếu một mảng byte chuẩn độc lập.
3. Nó không kiểm đường đọc/ghi thực tế của file, HTTP hoặc cơ sở dữ liệu.
4. Nó không kiểm một bước cắt, trim, normalize hoặc ánh xạ khác nằm ngoài hai hàm.

Đó là lý do ví dụ vừa dùng round-trip, vừa dùng byte đã biết cho `ế` và `Đặng`, vừa có dữ liệu cố ý bị lỗi.

Không tạo expected bằng cách gọi lại chính hàm đang cần kiểm. Nếu một hàm sai được dùng cả để tạo giá trị mong đợi và giá trị thực, test có thể vượt qua mà không cung cấp bằng chứng độc lập.

## 10. Mở rộng sang đường xử lý thực tế

Bộ ví dụ kiểm tra tính chất của xử lý chuỗi/mã hóa. Nếu ứng dụng có một pipeline thật, hãy đặt các ca trên vào đúng ranh giới cần kiểm:

```text
Byte từ bên ngoài
    ↓
Giải mã với charset và chính sách lỗi xác định
    ↓
Kiểm tra/chuẩn hóa theo hợp đồng nghiệp vụ
    ↓
Lưu hoặc xử lý
    ↓
Mã hóa đầu ra theo hợp đồng
```

Ví dụ:

- Với đọc tệp: fixture phải có byte UTF-8 xác định, không chỉ là String đã có sẵn trong test.
- Với HTTP: kiểm cả metadata bảng mã, byte body và logic đọc thực sự.
- Với lưu trữ: kiểm một vòng ghi/đọc qua hệ thống lưu trữ, không thay nó bằng biến String trong bộ nhớ.
- Với giới hạn độ dài: kiểm đúng đơn vị mà giao thức/cột dữ liệu quy định.
- Với cắt chuỗi hiển thị: thêm dấu kết hợp và chuỗi có nhiều code point tạo thành một cụm hiển thị.

Đừng tự normalize tất cả dữ liệu ở mỗi tầng để làm các phép so sánh vượt qua. Cần một chính sách và một nơi áp dụng rõ ràng, đồng thời kiểm sự khác biệt giữa dữ liệu nguyên bản và giá trị được chuẩn hóa nếu cả hai đều cần được giữ.

### Không kết luận mọi emoji đã được kiểm

`U+1F600` là một mẫu tốt để bắt lỗi surrogate pair, nhưng không đại diện mọi chuỗi emoji.

Một cờ, một emoji có biến thể màu da hoặc một chuỗi nối bằng ZWJ có thể gồm nhiều code point. Nếu sản phẩm có quy tắc theo “ký tự người dùng nhìn thấy”, cần test theo ranh giới cụm grapheme phù hợp và phiên bản dữ liệu Unicode đang dùng.

Không thay `length()` bằng `codePointCount()` rồi khẳng định mọi thao tác hiển thị đã đúng. Cách thay đó xử lý được một lớp lỗi, chưa giải quyết toàn bộ phân đoạn văn bản.

## 11. Khi test thất bại, chẩn đoán theo dữ liệu

Không chỉ chụp lại ảnh console, vì font, fallback, ký tự thay thế hoặc dấu kết hợp có thể làm hai dữ liệu khác nhau trông giống nhau.

Nên kiểm:

1. Các byte đầu vào ở dạng hex.
2. Charset được dùng.
3. Code point và độ dài UTF-16.
4. Trạng thái chuẩn hóa nếu có yêu cầu.
5. Bước nào đã làm thay đổi dữ liệu.

Một trình tự hữu ích:

```text
Expected byte khác actual byte?
    ↓
Có thể sai mã hóa, dữ liệu nguồn hoặc bước chuyển đổi.

Byte đúng nhưng String sai?
    ↓
Kiểm charset, phạm vi byte và chính sách lỗi.

String khác equals nhưng trông giống?
    ↓
Kiểm code point, dấu kết hợp và chuẩn hóa.

Cắt chuỗi xong không encode strict được?
    ↓
Kiểm có cắt surrogate pair hay không.
```

Nếu cần log dữ liệu, chọn phần dữ liệu thử nghiệm phù hợp; không cần đưa toàn bộ nội dung người dùng thực vào log chỉ để kiểm bảng mã.

### Lỗi do môi trường cũng cần được cô lập

Một ví dụ in trực tiếp `Tiếng Việt` có thể hiển thị sai vì console, dù String trong JVM đúng. Ngược lại, console có thể hiển thị một chuỗi đã mất dữ liệu bằng ký tự thay thế trông khó nhận ra.

Do đó, dùng assertion về nội dung và các giá trị code point/byte khi cần, rồi kiểm đường hiển thị như một lớp riêng.

## 12. Lỗi thiết kế test thường gặp

| Lỗi | Hậu quả |
| --- | --- |
| Chỉ dùng chữ không dấu ASCII | Không bắt được sai charset hoặc giả định một byte/một ký tự |
| Chỉ dùng một dạng chữ có dấu | Bỏ sót tương đương Unicode và dấu phân rã |
| Chỉ kiểm String.length | Bỏ sót sai đơn vị và surrogate bị cắt |
| Đếm code point rồi coi là số ký tự hiển thị | Vẫn có thể cắt cụm gồm nhiều code point |
| Chuyển null thành rỗng trong helper test | Che hợp đồng null của mã đang kiểm |
| Normalize cả expected và actual cho mọi test | Có thể che thay đổi dữ liệu không được phép |
| Round-trip bằng cùng một giả định charset sai | Cả hai chiều cùng sai nhưng test vẫn vượt qua |
| Bắt mọi Exception rồi coi là “đã báo lỗi đúng” | Lỗi không liên quan cũng bị chấp nhận |
| Kiểm mỗi chuỗi trông đúng trên màn hình | Bỏ qua dữ liệu chính xác và cấu hình console |
| Dùng constructor thay thế lỗi để kiểm “UTF-8 hợp lệ” | Dữ liệu lỗi có thể biến thành String thay vì bị từ chối |

Một test tốt phải có lý do khiến nó thất bại khi một giả định cụ thể bị vi phạm. Dữ liệu phong phú nhưng expected không rõ vẫn chưa tạo thành một bộ kiểm tra đáng tin cậy.

## 13. Bài tập tự kiểm chứng

1. Thay `mixed.substring(start, end)` bằng `mixed.substring(1, 2)`. Nhóm kiểm nào thất bại? Nó đã bắt lỗi ranh giới gì?
2. Bỏ bước NFC khỏi phép so sánh hai dạng của `ế`. Giải thích vì sao equals thất bại dù có thể hiển thị cùng một chữ.
3. Đổi decoder trong một bản thử nghiệm thành bảng mã khác, nhưng giữ nguyên byte UTF-8 đối chứng. Quan sát vì sao byte chuẩn độc lập bắt được lỗi.
4. Thêm một chuỗi chỉ gồm dấu kết hợp. Quy tắc nghiệp vụ của ứng dụng nên chấp nhận hay từ chối? Đừng dùng “không rỗng” làm câu trả lời cho mọi miền dữ liệu.
5. Viết một ca kiểm giới hạn đầu vào bằng byte UTF-8 và một ca giới hạn bằng code point. Dùng cùng một ký tự bổ sung để chứng minh hai giới hạn không tương đương.
6. Nếu hàm của ứng dụng được quy định chuyển null thành rỗng, hãy thay đúng test hợp đồng đó và giải thích thông tin nào bị gộp; không thay mọi helper một cách ngầm định.
7. Thêm fixture tiếng Việt thật trên đĩa và kiểm đường đọc của ứng dụng, giữ nguyên test byte/code point để phân biệt lỗi fixture với lỗi xử lý.

Điểm cần nắm là **kiểm thử Unicode phải chọn đúng dữ liệu và đúng đơn vị kỳ vọng**. Tiếng Việt có dấu, ký tự bổ sung và dữ liệu rỗng không phải các ví dụ trang trí; mỗi nhóm giúp phát hiện một loại giả định sai khác nhau.

## Tài liệu đối chiếu

- [String — Javadoc Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): UTF-16, chỉ số char, code point, equals và các API chuỗi.
- [Normalizer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html): các dạng chuẩn hóa Unicode, API có từ 1.6.
- [CharsetEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetEncoder.html): UTF-16 lỗi và chính sách REPORT.
- [CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): byte lỗi và chính sách giải mã.
- [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/): phân biệt code point với cụm ký tự người dùng cảm nhận.
