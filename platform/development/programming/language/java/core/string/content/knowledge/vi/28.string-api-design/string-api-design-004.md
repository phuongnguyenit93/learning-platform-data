# Quy định đơn vị chỉ số hoặc giới hạn độ dài trong API xử lý `String` Java

## 1. Vấn đề: “vị trí 3” và “tối đa 20 ký tự” chưa đủ rõ

Một API nhận `String` dễ có tham số như `start`, `end`, `maxLength` hay `maxChars`. Nếu không mô tả **đơn vị**, người gọi có thể hiểu nhầm là số ký tự nhìn thấy trên màn hình, còn mã Java lại thực hiện `String.length()` hoặc `substring()` theo **UTF-16 code unit**.

Ví dụ, xét chuỗi gồm chữ `A`, emoji `😃` và chữ `e` có dấu sắc kết hợp (`e\u0301`):

~~~text
Nhìn thấy:          A | 😃 | é
UTF-16 code unit:   1 +  2 + 2 = 5
Unicode code point: 1 +  1 + 2 = 4
UTF-8 byte:         1 +  4 + 3 = 8
Grapheme cluster:   1 +  1 + 1 = 3 (theo phân đoạn Unicode thông thường)
~~~

Vì vậy, cùng một dữ liệu có thể được gọi là dài **5**, **4**, **8** hoặc **3** tùy tiêu chí. Nếu tài liệu API chỉ ghi “độ dài tối đa 4 ký tự”, người dùng sẽ không biết chuỗi này hợp lệ hay bị từ chối.

**Nguyên tắc thiết kế:** mọi chỉ số, khoảng cắt, vị trí con trỏ và giới hạn độ dài phải được gắn với một **đơn vị đếm được định nghĩa tường minh**.

## 2. Bốn đơn vị thường gặp

| Đơn vị | Ý nghĩa | API Java liên quan | Dùng khi |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Mỗi `char` 16 bit của `String` | `length()`, `charAt()`, `substring()`, `indexOf()` | Tương thích API `String`, vị trí nội bộ Java |
| **Unicode code point** | Mã Unicode biểu thị bằng `int`; ký tự ngoài BMP dùng hai code unit | `codePoints()`, `codePointCount()`, `codePointAt()`, `offsetByCodePoints()` | Quy tắc xử lý theo từng code point |
| **Grapheme cluster** | Một cụm ký tự mà người dùng thường nhận thức như một ký tự | Thư viện phân đoạn Unicode theo grapheme boundary | Cắt/chọn/xóa ký tự trong giao diện người dùng |
| **Byte theo encoding** | Số byte sau khi mã hóa, chẳng hạn UTF-8 | `getBytes(StandardCharsets.UTF_8)`, `CharsetEncoder` | Giao thức, mạng, lưu trữ, giới hạn payload |

**Lưu ý:** một grapheme cluster có thể gồm nhiều code point (chữ + dấu kết hợp; emoji có ZWJ, biến thể hoặc màu da). Ngược lại, số cột hiển thị trên terminal không nhất thiết bằng số grapheme cluster; việc hiển thị còn tùy font, terminal và môi trường.

Nếu một API dùng `int` cho cả chỉ số UTF-16 và số code point, **kiểu `int` không thể hiện đơn vị**. Phải dùng tên biến, tên phương thức, tài liệu hợp đồng hoặc kiểu giá trị riêng để làm rõ.

## 3. Cách Java `String` đánh chỉ số: UTF-16 code unit

Hầu hết API chỉ số của `String` dùng **đơn vị UTF-16 code unit**:

~~~java
String s = "A\uD83D\uDE03B"; // A😃B
System.out.println(s.length());          // 4
System.out.println(s.charAt(0) == 'A');   // true
System.out.println(s.charAt(3) == 'B');   // true
~~~

Hai `char` ở chỉ số 1 và 2 lần lượt là **high surrogate** và **low surrogate** của `😃`. Vì thế `substring(1, 2)` chỉ lấy một nửa cặp surrogate, khiến chuỗi kết quả chứa surrogate đứng lẻ:

~~~java
String broken = s.substring(1, 2);
System.out.println(broken.length());                  // 1
System.out.println(Character.isHighSurrogate(
        broken.charAt(0)));                           // true
~~~

`substring(beginIndex, endIndex)` lấy vùng **nửa mở** `[beginIndex, endIndex)`: bao gồm đầu, không bao gồm cuối, và hai tham số là chỉ số UTF-16, **không phải chỉ số code point hoặc grapheme**.

Một API nên mô tả rõ cả **đơn vị** lẫn **quy tắc biên**:

> `sliceUtf16(String input, int beginUtf16Inclusive, int endUtf16Exclusive)` nhận offset theo UTF-16 code unit và dùng khoảng [begin, end). Người gọi phải chọn ranh giới phù hợp nếu cần bảo toàn một code point hoặc grapheme.

Nếu API dành cho người dùng cuối, việc buộc họ truyền offset UTF-16 có thể không phù hợp; hãy cân nhắc API theo code point hoặc grapheme.

## 4. Khi hợp đồng yêu cầu code point

`String.codePointCount(beginIndex, endIndex)` đếm số code point trong một vùng **UTF-16 index**. `String.codePoints().count()` đếm theo toàn chuỗi. Trong cả hai cách, một cặp surrogate hợp lệ được tính là **một** code point; surrogate lẻ được tính riêng, không tự biến mất.

~~~java
String s = "A\uD83D\uDE03B";
System.out.println(s.length());                     // 4
System.out.println(s.codePointCount(0, s.length())); // 3
System.out.println(s.codePoints().count());         // 3
~~~

Để biến chỉ số code point thành **chỉ số UTF-16** dùng cho `substring`, dùng `offsetByCodePoints`:

~~~java
String s = "A\uD83D\uDE03B";

int beginUtf16 = s.offsetByCodePoints(0, 1);
int endUtf16 = s.offsetByCodePoints(beginUtf16, 1);

String secondCodePoint = s.substring(beginUtf16, endUtf16);
System.out.println(secondCodePoint.equals("\uD83D\uDE03")); // true
~~~

`beginUtf16` là 1, `endUtf16` là 3: đúng cặp surrogate của emoji. Không được mặc định rằng `substring(1, 2)` sẽ lấy “ký tự thứ hai”.

### Xây dựng API cắt theo số code point

Đoạn sau là ví dụ phương thức độc lập, có thể đặt trong một class Java:

~~~java
static String takeCodePoints(String input, int maxCodePoints) {
    java.util.Objects.requireNonNull(input, "input");
    if (maxCodePoints < 0) {
        throw new IllegalArgumentException("maxCodePoints < 0");
    }

    int count = input.codePointCount(0, input.length());
    int numberToKeep = Math.min(maxCodePoints, count);
    int endUtf16 = input.offsetByCodePoints(0, numberToKeep);
    return input.substring(0, endUtf16);
}
~~~

Tên `maxCodePoints` nêu rõ đơn vị. Hàm không cắt đôi một cặp surrogate hợp lệ, nhưng vẫn có thể cắt **giữa các code point thuộc cùng một grapheme cluster** (ví dụ chữ `e` và dấu kết hợp). Khi yêu cầu là “không làm hỏng ký tự hiển thị”, cần phân đoạn grapheme riêng.

**Đừng nhầm:** tham số thứ hai của `offsetByCodePoints(index, codePointOffset)` là số code point cần di chuyển; giá trị nó trả về vẫn là **offset UTF-16**.

## 5. Khi hợp đồng yêu cầu grapheme cluster

Ví dụ `"e\u0301"` gồm **hai code point** (`e` và dấu sắc kết hợp) nhưng thường hiển thị thành **một** chữ có dấu. Một số emoji gia đình cũng gồm nhiều code point nối bằng ZWJ, trong khi người dùng nhìn thấy một biểu tượng.

Vì vậy:

- `String.length()` **không** đếm số ký tự nhìn thấy.
- `codePoints().count()` cũng **không** luôn đếm số ký tự nhìn thấy.
- `substring` hoặc việc lấy đúng `n` code point có thể cắt giữa các thành phần của grapheme.

Với giới hạn độ dài ô nhập, thao tác xóa một ký tự theo phím Backspace hay vị trí con trỏ UI, nên xác định liệu **extended grapheme cluster** có phải đơn vị mong muốn hay không.

Trong Java, có `java.text.BreakIterator.getCharacterInstance()`, nhưng khả năng phân đoạn grapheme theo Unicode phụ thuộc phiên bản và quy tắc được hỗ trợ; không được mặc định nó khớp đầy đủ quy tắc extended grapheme cluster mới nhất trên mọi JDK. Nếu yêu cầu đòi hỏi chính xác theo Unicode UAX #29, hãy dùng thư viện có hỗ trợ grapheme boundary rõ ràng (ví dụ ICU4J), ghi nhận phiên bản Unicode của thư viện và kiểm thử với dữ liệu thực.

Một API có thể đặt tên tường minh như:

~~~java
// Chữ ký thiết kế minh họa; implementation cần bộ phân đoạn grapheme.
int countGraphemeClusters(String text);

// Trả về tối đa N grapheme cluster, không cắt giữa cluster.
String takeGraphemeClusters(String text, int maxClusters);
~~~

Hai chữ ký trên chỉ minh họa **hợp đồng API**, không phải chương trình chạy độc lập.

## 6. Khi giới hạn được đo bằng byte

Các giao thức mạng, trường lưu trữ hoặc định dạng file thường ràng buộc độ dài theo **byte**. Khi đó `String.length()` không trả lời đúng câu hỏi.

Trong UTF-8, `A` dùng 1 byte, `😃` dùng 4 byte, `e` dùng 1 byte và dấu sắc kết hợp U+0301 dùng 2 byte. Chuỗi `A😃e\u0301` vì thế chiếm **8 byte UTF-8** dù `length()` chỉ bằng 5.

~~~java
String value = "A\uD83D\uDE03e\u0301";
int bytes = value.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;

System.out.println(bytes); // 8
~~~

Định nghĩa một giới hạn nên ghi đầy đủ, ví dụ:

- `maxUtf8Bytes = 255`: tối đa 255 byte **sau khi mã hóa UTF-8**.
- `maxCodePoints = 50`: tối đa 50 code point trong `String`.
- `maxUtf16Units = 100`: tối đa 100 UTF-16 code unit; tương đương tiêu chí `String.length() <= 100`.

Nếu API gửi dữ liệu dạng JSON, giới hạn “byte của **payload JSON đã serialize và encode UTF-8**” có thể khác giới hạn “byte UTF-8 của giá trị chuỗi trước serialize”: dấu nháy kép, escape, tên thuộc tính và phần cấu trúc JSON có thể chiếm thêm byte.

**Encoding là một phần của hợp đồng.** “255 byte” mà không nói UTF-8, UTF-16 hay định dạng truyền dẫn là mô tả chưa đủ.

### Đầu vào có surrogate không hợp lệ

`String` Java vẫn có thể chứa surrogate lẻ. `getBytes(StandardCharsets.UTF_8)` có thể dùng ký tự thay thế khi không mã hóa được đầu vào, vì thế đếm byte bằng `getBytes` không đồng nghĩa với **kiểm tra UTF-16 hợp lệ**. Nếu hệ thống cần từ chối dữ liệu lỗi, hãy xác thực surrogate pair trước hoặc dùng `CharsetEncoder` với `CodingErrorAction.REPORT`, xử lý `CharacterCodingException` theo chính sách của ứng dụng.

Không nên cắt trực tiếp mảng byte UTF-8 tại một vị trí bất kỳ rồi giải mã lại: việc cắt có thể rơi giữa một chuỗi byte mã hóa code point. Muốn giới hạn byte mà vẫn bảo toàn ký tự, cần cắt tại **ranh giới code point hoặc grapheme** và kiểm tra số byte sau mã hóa.

## 7. Thiết kế hợp đồng API rõ nghĩa

### 7.1. Đặt tên chứa đơn vị

So sánh:

~~~java
// Mơ hồ: giới hạn nào, chỉ số loại nào?
String truncate(String value, int limit);

// Rõ hơn: tối đa bao nhiêu Unicode code point?
String takeCodePoints(String value, int maxCodePoints);

// Rõ hơn: vị trí theo UTF-16.
String sliceUtf16(String value,
                  int beginUtf16Inclusive,
                  int endUtf16Exclusive);

// Rõ hơn: dữ liệu phải vừa giới hạn byte UTF-8.
boolean fitsUtf8Bytes(String value, int maxUtf8Bytes);
~~~

Các chữ ký này diễn đạt **ý định thiết kế**; code implement phải tuân thủ đơn vị đã ghi, thay vì đặt tên `maxCodePoints` rồi kiểm tra bằng `value.length()`.

Nên mô tả thêm:

1. **Giới hạn có bao gồm biên không?** “tối đa 20” thường nghĩa là `<= 20`.
2. **Chỉ số bắt đầu từ 0 hay 1?** Trong Java `String`, chỉ số là 0-based.
3. **Khoảng `[begin,end)` hay `[begin,end]`?** `substring` dùng khoảng nửa mở.
4. **Cắt hay từ chối?** Ví dụ validation trả lỗi khi quá giới hạn, còn truncate chủ ý cắt. Đừng âm thầm cắt dữ liệu khi hợp đồng chỉ nói “validate”.
5. **Xử lý `null`, giới hạn âm, chỉ số ngoài phạm vi và surrogate lỗi ra sao?** Quy định ngoại lệ hoặc kết quả rõ ràng.
6. **Có chuẩn hóa đầu vào trước khi đo không?** Ví dụ Unicode NFC, trim hoặc case conversion có thể làm thay đổi độ dài; phải xác định thứ tự xử lý.

### 7.2. Dùng kiểu riêng khi có nhiều đơn vị

Nếu cùng một hệ thống thường xử lý cả byte offset và UTF-16 offset, có thể tách kiểu để tránh truyền nhầm:

~~~java
record Utf16Index(int value) {}
record CodePointIndex(int value) {}
record Utf8ByteLimit(int value) {}
~~~

Đây là các khai báo kiểu **minh họa** (Java 17). Bản thân record không tự bảo đảm chỉ số hợp lệ; cần kiểm tra phạm vi khi dùng với chuỗi cụ thể. Nhưng chữ ký nhận `Utf16Index` sẽ khó bị nhầm với `CodePointIndex` hơn là khi tất cả đều nhận `int`.

### 7.3. Ghi quy tắc trong tài liệu API và ví dụ

Ví dụ hợp đồng có thể viết:

> `takeCodePoints(text, n)` trả về tiền tố gồm tối đa `n` Unicode code point của `text`, giữ thứ tự ban đầu, không cắt đôi surrogate pair hợp lệ. `n` phải không âm. Phương thức không hứa hẹn giữ nguyên extended grapheme cluster, không chuẩn hóa Unicode và không kiểm soát số byte UTF-8.

Mô tả này có thể kiểm tra được qua unit test. Câu “lấy tối đa n ký tự” không thể hiện đầy đủ các cam kết như vậy.

## 8. Ví dụ Java 17+ đầy đủ có thể biên dịch và chạy

Lưu tệp `StringUnitContractDemo.java`. Ví dụ dùng biểu diễn Unicode escape trong source để không phụ thuộc bộ gõ emoji khi sao chép mã:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class StringUnitContractDemo {
    static String takeCodePoints(String input, int maxCodePoints) {
        Objects.requireNonNull(input, "input");
        if (maxCodePoints < 0) {
            throw new IllegalArgumentException("maxCodePoints < 0");
        }
        int available = input.codePointCount(0, input.length());
        int endUtf16 = input.offsetByCodePoints(
                0, Math.min(maxCodePoints, available));
        return input.substring(0, endUtf16);
    }

    static boolean fitsUtf8Bytes(String input, int maxUtf8Bytes) {
        Objects.requireNonNull(input, "input");
        if (maxUtf8Bytes < 0) {
            throw new IllegalArgumentException("maxUtf8Bytes < 0");
        }
        return input.getBytes(StandardCharsets.UTF_8).length
                <= maxUtf8Bytes;
    }

    static boolean isWellFormedUtf16(String input) {
        Objects.requireNonNull(input, "input");
        for (int i = 0; i < input.length(); i++) {
            char unit = input.charAt(i);
            if (Character.isHighSurrogate(unit)) {
                if (i + 1 == input.length()
                        || !Character.isLowSurrogate(input.charAt(i + 1))) {
                    return false;
                }
                i++; // Bỏ qua low surrogate của cặp đã kiểm tra.
            } else if (Character.isLowSurrogate(unit)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        // A + emoji 😃 + e + dấu sắc kết hợp U+0301
        String text = "A\uD83D\uDE03e\u0301";

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePoints().count());
        System.out.println("utf8Bytes=" +
                text.getBytes(StandardCharsets.UTF_8).length);

        int beginUtf16 = text.offsetByCodePoints(0, 1);
        int endUtf16 = text.offsetByCodePoints(beginUtf16, 1);
        System.out.println("emojiEquals=" + text.substring(
                beginUtf16, endUtf16).equals("\uD83D\uDE03"));

        System.out.println("prefixEquals=" +
                takeCodePoints(text, 2).equals("A\uD83D\uDE03"));

        String broken = text.substring(0, 2);
        System.out.println("brokenWellFormed=" +
                isWellFormedUtf16(broken));
        System.out.println("originalWellFormed=" +
                isWellFormedUtf16(text));

        System.out.println("within4CodePoints=" +
                (text.codePointCount(0, text.length()) <= 4));
        System.out.println("within7Utf8Bytes=" +
                fitsUtf8Bytes(text, 7));

        System.out.printf("emojiCodePoint=U+%X%n",
                text.codePointAt(1));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StringUnitContractDemo.java
java StringUnitContractDemo
~~~

Kết quả `stdout`:

~~~text
utf16Units=5
codePoints=4
utf8Bytes=8
emojiEquals=true
prefixEquals=true
brokenWellFormed=false
originalWellFormed=true
within4CodePoints=true
within7Utf8Bytes=false
emojiCodePoint=U+1F603
~~~

**Giải thích:**

- `length()` cho `5` vì emoji chiếm hai `char`, còn chữ `e` và dấu sắc kết hợp là hai code unit riêng.
- `codePoints().count()` cho `4`: `A`, emoji, `e`, dấu sắc kết hợp.
- `getBytes(UTF_8).length` cho `8`; do đó giới hạn **7 byte** bị vượt, mặc dù giới hạn **4 code point** vẫn vừa.
- Dùng `offsetByCodePoints` để tính hai mốc UTF-16 giúp lấy đầy đủ emoji.
- `substring(0, 2)` vô tình kết thúc ngay sau **high surrogate**, nên `isWellFormedUtf16` phát hiện dữ liệu bị cắt hỏng.
- Kiểm tra UTF-16 hợp lệ trong ví dụ là bước riêng, không được thay thế bởi kiểm tra `length()` hay số code point.

Hàm `fitsUtf8Bytes` minh họa đo byte với đầu vào hợp lệ; nếu ứng dụng yêu cầu nghiêm ngặt với đầu vào lỗi, hãy gọi `isWellFormedUtf16` hoặc dùng encoder báo lỗi trước khi chấp nhận dữ liệu.

## 9. Thứ tự chuẩn hóa, validation và lưu trữ

Một quy trình xử lý giá trị chuỗi nên xác định thứ tự các bước trước khi đặt giới hạn:

1. **Giải mã đầu vào** theo encoding đã thỏa thuận (ví dụ UTF-8), với chính sách rõ ràng cho dữ liệu lỗi.
2. **Xác thực** ký tự hoặc quy tắc nghiệp vụ; xác định có chấp nhận surrogate lỗi không.
3. **Chuẩn hóa nếu hợp đồng yêu cầu**: ví dụ Unicode NFC hoặc quy tắc xử lý whitespace nhất quán.
4. **Đo theo đơn vị đã công bố**: code point, grapheme hay byte UTF-8 sau mã hóa.
5. **Từ chối hoặc cắt** theo chính sách của API, rồi lưu/truyền theo định dạng mong muốn.

Không nên cho rằng `Normalizer.normalize`, `strip()`, `toLowerCase()` hay serializer là các thao tác “không ảnh hưởng độ dài”. Chúng có thể thay đổi số code point, UTF-16 unit hoặc byte. Nếu kiểm tra độ dài trên giá trị **trước xử lý** nhưng lưu giá trị **sau xử lý**, hợp đồng phải giải thích rõ đơn vị và giai đoạn đo.

Ví dụ, `"é"` dạng U+00E9 và `"e\u0301"` (U+0065 + U+0301) có thể trông giống nhau nhưng trước NFC có **1** và **2** code point tương ứng; số byte UTF-8 cũng khác. Nếu hai dạng phải được chấp nhận như cùng dữ liệu, chuẩn hóa trước validation là một quyết định thiết kế cần nêu tường minh.

## 10. Các trường hợp kiểm thử thiết yếu

| Dữ liệu | UTF-16 unit | Code point | UTF-8 byte | Điểm cần xác minh |
| --- | ---: | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | 3 | ASCII: mọi đơn vị trùng nhau |
| `"é"` (U+00E9) | 1 | 1 | 2 | BMP nhưng UTF-8 cần hai byte |
| `"e\u0301"` | 2 | 2 | 3 | Hai code point thường tạo một grapheme |
| `"😃"` | 2 | 1 | 4 | Supplementary code point dùng surrogate pair |
| `"A😃e\u0301"` | 5 | 4 | 8 | Các giới hạn theo đơn vị khác nhau |
| Chuỗi rỗng `""` | 0 | 0 | 0 | Trường hợp biên |
| Surrogate đứng lẻ | Tùy đầu vào | Được `codePoints()` xuất riêng | Phụ thuộc chính sách encoder | Cần validation cho dữ liệu Unicode lỗi |

Để kiểm thử một API cắt chuỗi, còn cần các trường hợp:

- Giới hạn bằng 0, bằng độ dài, nhỏ hơn và lớn hơn độ dài.
- Giá trị giới hạn âm và chỉ số ngoài phạm vi.
- Điểm cắt ngay **trước**, **giữa** và **sau** surrogate pair.
- Điểm cắt giữa chữ cơ sở và dấu kết hợp.
- Emoji nhiều code point có ZWJ/variation selector; kiểm thử theo phiên bản Unicode đã chọn.
- Dữ liệu với ký tự có độ dài UTF-8 1, 2, 3 và 4 byte.
- Chuỗi có Unicode normalization khác nhau nhưng hình thức hiển thị giống nhau.
- Biên của giới hạn byte tính trên **giá trị thực sự được gửi hoặc lưu**.

## 11. Checklist khi công bố API

- **Đơn vị nào?** `utf16Unit`, `codePoint`, `graphemeCluster`, `utf8Byte` hay số byte payload sau serialize?
- **Chỉ số nào?** 0-based/1-based và khoảng đóng/mở?
- **Đếm ở bước nào?** Trước hay sau normalize, trim, encode, escape hoặc serialize?
- **Quá giới hạn thì sao?** Trả lỗi hay cắt? Có giữ nguyên grapheme không?
- **Dữ liệu lỗi thì sao?** Surrogate lẻ, encoding không hợp lệ, `null`, giới hạn âm?
- **Có tương thích API khác?** `substring()` cần offset UTF-16; bộ phân đoạn grapheme có phiên bản Unicode cụ thể.
- **Đã test trên Unicode thực tế chưa?** Supplementary, combining mark, emoji ghép, các ký tự nhiều byte.

**Kết luận:** trong API Java, từ “ký tự” thường quá mơ hồ để làm đơn vị chỉ số hoặc giới hạn. `String.length()` và `substring()` dùng **UTF-16 code unit**; `codePoints()` dùng **Unicode code point**; độ dài hiển thị cần xem **grapheme cluster**; giới hạn truyền/lưu thường cần **byte theo encoding**. Hãy đặt tên và viết hợp đồng thể hiện chính xác đơn vị, quy tắc biên và thứ tự chuẩn hóa, rồi kiểm thử những chuỗi Unicode mà mỗi đơn vị cho kết quả khác nhau.
