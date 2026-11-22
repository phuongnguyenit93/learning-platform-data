# Xử lý chuỗi có code point ngoài BMP

## 1. Bài toán: không cắt đôi một ký tự bổ sung

Một ứng dụng cần giới hạn độ dài tiêu đề, đếm nội dung và chuyển văn bản sang UTF-8. Với dữ liệu chỉ có ASCII, dùng `length()`, vòng lặp `charAt(i)` hoặc `substring(0, n)` có vẻ cho cùng một khái niệm “ký tự”.

Khi chuỗi có ký tự ngoài BMP hoặc dấu kết hợp, các thao tác đó không còn đo cùng một đơn vị.

Trong bài thực hành này cần:

1. Phân biệt byte, đơn vị mã UTF-16, code point và cụm ký tự hiển thị.
2. Duyệt ký tự bổ sung mà không tách cặp surrogate.
3. Cắt tiền tố theo code point đúng ranh giới.
4. Nhận ra khi cần cắt theo cụm grapheme thay vì code point.
5. Xử lý chuỗi UTF-16 không hợp lệ theo chính sách rõ ràng.
6. Kiểm chứng bằng chương trình Java 17+ và output không phụ thuộc font hiển thị.

Các API hỗ trợ code point có từ lâu nhưng vẫn là cách xử lý đúng trên Java hiện đại. Không cần loại bỏ ký tự ngoài BMP để né giới hạn của một vòng lặp viết theo `char`.

## 2. Bốn đơn vị khác nhau

| Đơn vị | Ý nghĩa |
| --- | --- |
| Byte | Đơn vị dữ liệu của một phép mã hóa cụ thể như UTF-8 |
| Code unit UTF-16 | Một giá trị `char` 16 bit trong cách đánh chỉ số của Java |
| Code point | Giá trị định danh trong không gian mã Unicode, thường viết dạng `U+...` |
| Grapheme cluster | Cụm văn bản gần với một “ký tự” mà người dùng cảm nhận |

`String.length()` trả số code unit UTF-16. Các chỉ số của `charAt()` và `substring()` cũng theo code unit, theo [String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html).

Đây là hợp đồng logic của API; không suy ra mọi JDK đều phải lưu nội bộ mỗi String bằng một `char[]` có cấu trúc giống nhau.

### BMP và vùng bổ sung

BMP (Basic Multilingual Plane) là khoảng `U+0000` đến `U+FFFF`. Các code point từ `U+10000` đến `U+10FFFF` nằm ngoài BMP và được gọi là code point bổ sung.

UTF-16 biểu diễn một giá trị bổ sung bằng hai code unit:

```text
high surrogate: U+D800 .. U+DBFF
low surrogate:  U+DC00 .. U+DFFF
```

Ví dụ `U+1F680` được biểu diễn bằng cặp `D83D DE80`. Không có một giá trị `char` đơn lẻ chứa được toàn bộ code point đó; Java dùng `int` khi thao tác code point.

Khoảng surrogate nằm trong BMP nhưng các giá trị surrogate riêng lẻ không phải Unicode scalar value. Một scalar value là code point hợp lệ ngoài khoảng `U+D800..U+DFFF`.

## 3. Đếm đúng đơn vị trước khi đặt giới hạn

Xét chuỗi gồm:

```text
U+0041   LATIN CAPITAL LETTER A
U+1F680  ROCKET
U+0065   LATIN SMALL LETTER E
U+0301   COMBINING ACUTE ACCENT
```

Chữ `e` cùng dấu kết hợp tạo thành một cụm hiển thị. Kết quả:

| Cách đo | Số lượng |
| --- | --- |
| Code unit UTF-16 | 5 |
| Code point | 4 |
| Cụm grapheme theo phân đoạn của ví dụ | 3 |
| Byte UTF-8 | 8 |

Không có một con số duy nhất luôn đúng cho câu hỏi “chuỗi dài bao nhiêu ký tự”. Phải xác định yêu cầu:

- Giao thức giới hạn byte: đo theo phép mã hóa được quy định.
- Thuật toán làm việc trên mã Unicode: có thể cần code point.
- Giao diện cắt tiêu đề hoặc di chuyển con trỏ: thường cần ranh giới grapheme.
- API Java nhận chỉ số substring: truyền chỉ số UTF-16 đã tính đúng.

Các loại độ dài không đổi sang nhau bằng cách nhân một hằng số. Chẳng hạn code point UTF-8 có độ dài thay đổi, và một cụm grapheme có thể chứa nhiều code point.

## 4. Duyệt code point đúng cách

Một vòng lặp theo `char` sẽ gặp từng nửa surrogate khi có ký tự bổ sung:

```java
// Đoạn minh họa: không dùng mỗi char như một code point hoàn chỉnh.
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
}
```

Có hai cách phổ biến để làm việc theo code point:

```java
// Minh họa: cp có kiểu int.
text.codePoints().forEach(cp -> {
    // Xử lý code point tại đây.
});
```

```java
// Minh họa khi cần giữ chỉ số UTF-16.
for (int offset = 0; offset < text.length(); ) {
    int cp = text.codePointAt(offset);
    // Xử lý cp và offset.
    offset += Character.charCount(cp);
}
```

Vòng thứ hai phải bắt đầu từ một ranh giới đúng. Gọi `codePointAt()` tại vị trí đang trỏ vào low surrogate không tự tìm ngược lại để ghép với high surrogate phía trước.

Khi phân loại chữ cái hoặc chữ số cho toàn bộ Unicode, ưu tiên overload nhận `int` của `Character`. Ép một code point bổ sung về `char` làm mất thông tin; không dùng `(char) cp` để đưa nó vào kết quả.

Để dựng văn bản, có thể dùng `Character.toChars(cp)` hoặc `StringBuilder.appendCodePoint(cp)` với đầu vào đáp ứng chính sách hợp lệ. Phân biệt các overload và cách biểu diễn được mô tả trong [Character API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).

## 5. Cắt theo code point mà không tách surrogate pair

Sai lầm thường gặp:

```java
// Không bảo đảm giữ nguyên code point bổ sung.
String prefix = text.substring(0, 2);
```

Với chuỗi mẫu ở trên, chỉ số 2 nằm giữa high surrogate và low surrogate. `substring()` không báo lỗi chỉ vì ranh giới đó tạo một chuỗi có surrogate lẻ.

Cách làm:

1. Quyết định đầu vào có bắt buộc là UTF-16 đúng cấu trúc hay không.
2. Tính số code point cần giữ.
3. Dùng `offsetByCodePoints()` để tìm chỉ số UTF-16 tương ứng.
4. Gọi `substring()` với chỉ số đó.

```java
// Minh họa khi đầu vào đã được kiểm tra đúng cấu trúc.
int available = text.codePointCount(0, text.length());
int keep = Math.min(maximum, available);
int end = text.offsetByCodePoints(0, keep);
String prefix = text.substring(0, end);
```

Đoạn này giữ nguyên code point, nhưng chưa bảo đảm giữ nguyên grapheme. Giữ ba code point đầu của chuỗi mẫu vẫn bỏ dấu kết hợp ở vị trí thứ tư, dù kết quả không có surrogate lỗi.

## 6. Khi nào phải dùng grapheme?

Một ký tự mà người dùng cảm nhận có thể gồm:

- Một chữ cái và một hoặc nhiều dấu kết hợp.
- Nhiều code point kết hợp thành emoji.
- Chuỗi có ký tự nối hoặc thành phần trình bày khác.

Quy tắc phân đoạn mặc định được mô tả trong [Unicode Text Segmentation, UAX #29](https://www.unicode.org/reports/tr29/). Grapheme cluster là mô hình phân đoạn văn bản, không phải số byte, số ô rộng trên terminal hoặc số glyph mà mọi font nhất thiết vẽ ra.

Trong regex Java hiện đại, `\X` khớp một extended grapheme cluster. Khi viết chuỗi Java phải escape dấu gạch chéo:

```java
Pattern grapheme = Pattern.compile("\\X");
```

Đặc tả biểu thức nằm trong [Pattern API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html).

Quy tắc và dữ liệu Unicode được triển khai theo phiên bản JDK. Không giả định JDK 17 nhận diện mọi chuỗi mới nhất giống một thư viện Unicode mới hơn. Nếu sản phẩm cần tuân thủ một phiên bản cụ thể, phải chọn triển khai phù hợp và có bộ ca kiểm thử tương ứng.

Cũng không nên chỉ đổi thuật toán đảo chuỗi từ `char` sang code point rồi coi đã xử lý đúng mọi văn bản. Đảo thứ tự code point có thể tách hoặc đổi vị trí dấu kết hợp. `StringBuilder.reverse()` có xử lý cặp surrogate theo hợp đồng riêng, nhưng không phải phép đảo grapheme tổng quát; xem [StringBuilder.reverse()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#reverse()).

## 7. Chuỗi Java có thể chứa surrogate lẻ

Một đối tượng `String` không tự bảo đảm toàn bộ nội dung là một chuỗi Unicode scalar value được mã hóa UTF-16 đúng cấu trúc.

Có thể tạo surrogate lẻ bằng cách:

- Cắt giữa một cặp.
- Dựng chuỗi trực tiếp từ mảng `char` chứa dữ liệu lỗi.
- Ghép các mảnh văn bản ở ranh giới không phù hợp.

`codePointCount()` không phải bộ kiểm tra hợp lệ: một surrogate lẻ vẫn được tính như một đơn vị chưa ghép. `codePoints()` cũng không tự từ chối mọi trường hợp đó.

Chính sách của lời giải là **từ chối UTF-16 có surrogate lẻ** trước khi cắt. Một ứng dụng khác có thể thay thế dữ liệu lỗi, nhưng phải công bố rõ; không âm thầm thay đổi dữ liệu rồi coi đó là đầu vào gốc.

Nếu nhận một `int` từ bên ngoài để dựng scalar value, kiểm tra cả phạm vi code point lẫn việc loại trừ khoảng surrogate. Chỉ kiểm tra `Character.isValidCodePoint(cp)` chưa đủ để loại mọi surrogate code point, vì API này kiểm tra phạm vi mã của Java.

## 8. Chương trình Java 17+ chạy đầy đủ

Chương trình dùng dạng `U+...` khi in để output vẫn rõ ngay cả khi terminal không có font biểu diễn ký tự bổ sung.

Hai hàm cắt có hợp đồng:

- Giới hạn âm bị từ chối.
- Giới hạn 0 trả chuỗi rỗng.
- Giới hạn lớn hơn số phần tử trả toàn bộ chuỗi.
- Đầu vào phải có surrogate ghép đúng.
- Một hàm đếm theo code point; hàm kia theo extended grapheme của regex JDK.

Lưu thành `SupplementaryTextDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class SupplementaryTextDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    static void requireWellFormedUtf16(String text) {
        Objects.requireNonNull(text);
        for (int i = 0; i < text.length(); i++) {
            char current = text.charAt(i);
            if (Character.isHighSurrogate(current)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(text.charAt(i + 1))) {
                    throw new IllegalArgumentException("Unpaired surrogate");
                }
                i++;
            } else if (Character.isLowSurrogate(current)) {
                throw new IllegalArgumentException("Unpaired surrogate");
            }
        }
    }

    static String prefixByCodePoints(String text, int maximum) {
        requireWellFormedUtf16(text);
        if (maximum < 0) {
            throw new IllegalArgumentException("Negative maximum");
        }
        int count = text.codePointCount(0, text.length());
        int end = text.offsetByCodePoints(0, Math.min(maximum, count));
        return text.substring(0, end);
    }

    static String prefixByGraphemes(String text, int maximum) {
        requireWellFormedUtf16(text);
        if (maximum < 0) {
            throw new IllegalArgumentException("Negative maximum");
        }
        Matcher matcher = GRAPHEME.matcher(text);
        int end = 0;
        for (int i = 0; i < maximum && matcher.find(); i++) {
            end = matcher.end();
        }
        return text.substring(0, end);
    }

    static String hexCodePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String rocket = new String(Character.toChars(0x1F680));
        String text = "A" + rocket + "e\u0301";
        requireWellFormedUtf16(text);

        System.out.println("units=" + text.length());
        System.out.println("points="
                + text.codePointCount(0, text.length()));
        System.out.println("graphemes="
                + GRAPHEME.matcher(text).results().count());
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8Bytes=" + encoded.length);
        System.out.println("codePoints=" + hexCodePoints(text));
        System.out.println("prefix2="
                + hexCodePoints(prefixByCodePoints(text, 2)));
        System.out.println("prefix3="
                + hexCodePoints(prefixByCodePoints(text, 3)));
        System.out.println("graphemePrefix3="
                + hexCodePoints(prefixByGraphemes(text, 3)));
        System.out.println("roundTrip="
                + text.equals(new String(encoded, StandardCharsets.UTF_8)));

        String broken = text.substring(0, 2);
        try {
            requireWellFormedUtf16(broken);
        } catch (IllegalArgumentException expected) {
            System.out.println("badSlice=REJECTED");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror SupplementaryTextDemo.java
java SupplementaryTextDemo
```

Stdout:

```text
units=5
points=4
graphemes=3
utf8Bytes=8
codePoints=U+0041 U+1F680 U+0065 U+0301
prefix2=U+0041 U+1F680
prefix3=U+0041 U+1F680 U+0065
graphemePrefix3=U+0041 U+1F680 U+0065 U+0301
roundTrip=true
badSlice=REJECTED
```

### Đọc kết quả

`prefix2` giữ hai code point đầu và không cắt đôi `U+1F680`.

`prefix3` là UTF-16 đúng cấu trúc nhưng không còn dấu kết hợp đi sau `e`. Điều này chứng minh “không hỏng surrogate” khác với “không cắt cụm hiển thị”.

`graphemePrefix3` giữ ba cụm nên còn đủ cả chữ và dấu.

`badSlice` là kết quả cắt bằng chỉ số UTF-16 không phù hợp; hàm kiểm tra phát hiện surrogate lẻ. Không in trực tiếp chuỗi lỗi để tránh việc terminal tự thay ký tự và che mất nguyên nhân.

## 9. Biên byte: ghi rõ charset và chính sách dữ liệu lỗi

Với chuỗi đã đúng cấu trúc, mã hóa/giải mã UTF-8 rõ ràng:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Không dùng charset mặc định làm giả định ngầm của một định dạng dữ liệu. Cũng không dùng số byte của UTF-8 làm chỉ số cho `substring()`.

Khi xử lý luồng byte chia thành nhiều phần, một phần có thể kết thúc giữa chuỗi byte của code point. Không giải mã từng mảnh độc lập rồi nối kết quả nếu mảnh không được bảo đảm nằm đúng ranh giới. Dùng decoder có trạng thái và giữ phần byte chưa đủ.

Nếu chính sách yêu cầu từ chối UTF-8 lỗi, có thể dùng decoder báo lỗi:

```java
// Minh họa cho một mảng byte đầy đủ; cần xử lý CharacterCodingException.
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
```

Đoạn này cần các kiểu `ByteBuffer` và `CodingErrorAction` tương ứng từ `java.nio`/`java.nio.charset`. Cách xử lý đầu vào lỗi và trạng thái giải mã được mô tả trong [CharsetDecoder API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

Ví dụ round-trip trong chương trình sử dụng dữ liệu đúng cấu trúc do chương trình tạo. Không lấy kết quả đó làm bằng chứng rằng mọi mảng byte hoặc String lỗi đều sẽ được bảo toàn qua các hàm tiện ích.

## 10. Chuẩn hóa khác với ghép surrogate

Hai chuỗi nhìn giống nhau có thể có dãy code point khác nhau, chẳng hạn một chữ có dấu dựng sẵn so với chữ và dấu kết hợp. `String.equals()` so sánh nội dung biểu diễn, không tự chuẩn hóa Unicode.

Khi miền bài toán cần so sánh theo dạng chuẩn nhất quán, có thể sử dụng `Normalizer` và lựa chọn dạng như NFC theo hợp đồng ứng dụng. Xem [Normalizer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html).

Chuẩn hóa không phải thuốc chữa mọi vấn đề:

- Không thay việc kiểm tra surrogate lỗi.
- Không biến mọi grapheme thành một code point.
- Không tự làm hai chuỗi có ý nghĩa nghiệp vụ khác nhau thành cùng một định danh hợp lệ.
- Có thể thay đổi số code point hoặc chỉ số, nên phải xác định thứ tự chuẩn hóa và tính vị trí.

Không chuẩn hóa tùy ý các dữ liệu cần giữ nguyên byte, chữ ký hoặc định danh theo một hợp đồng khác.

## 11. Bài tập mở rộng và ca kiểm thử

| Dữ liệu/điều kiện | Điều cần kiểm tra |
| --- | --- |
| Chuỗi rỗng | Mọi giới hạn không âm đều không gây lỗi |
| Một code point bổ sung | Length là 2; cắt một code point giữ đủ cặp |
| Chữ cùng dấu kết hợp | Cắt theo code point và grapheme cho kết quả khác nhau ở ranh giới phù hợp |
| Chuỗi emoji nhiều code point | Không đồng nhất số code point với số cụm |
| High surrogate đứng cuối | Bị từ chối theo chính sách lời giải |
| Low surrogate không có high surrogate trước | Bị từ chối |
| Giới hạn 0, âm, vượt độ dài | Đúng hợp đồng đã công bố |
| Byte UTF-8 bị chia giữa code point | Decoder trạng thái giữ được dữ liệu qua các phần |
| Hai dạng chuẩn hóa tương đương | So sánh trước/sau chuẩn hóa đúng mục đích |

Mở rộng bài bằng cách viết hàm lấy đoạn con theo chỉ số code point, rồi kiểm tra điểm bắt đầu/kết thúc. Sau đó thiết kế phiên bản theo grapheme cho giao diện. Đừng dùng chung một tham số tên mơ hồ như `length` cho các đơn vị khác nhau; có thể đặt `maxCodePoints`, `maxGraphemes` hoặc `maxUtf8Bytes`.

## 12. Tự kiểm tra

1. Vì sao một code point ngoài BMP cần hai vị trí trong String? **API String dùng đơn vị UTF-16, và ký tự bổ sung được mã hóa bằng cặp surrogate.**
2. length có đếm code point không? **Không; nó đếm code unit.**
3. Dùng codePoints có đủ cho cắt nội dung giao diện không? **Không phải luôn; có thể cần grapheme cluster.**
4. substring có tự ngăn cắt giữa surrogate pair không? **Không.**
5. codePointCount có kiểm tra chuỗi Unicode hợp lệ không? **Không; phải có chính sách kiểm tra riêng khi cần.**
6. Số byte UTF-8 có dùng làm chỉ số substring được không? **Không; hai đơn vị khác nhau.**
7. Vì sao ví dụ in dạng U+...? **Để kiểm chứng dãy code point mà không phụ thuộc font hoặc cách terminal hiển thị.**
