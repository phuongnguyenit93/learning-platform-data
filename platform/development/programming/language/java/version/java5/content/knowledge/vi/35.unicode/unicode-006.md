# Character.toChars và Character.toCodePoint

## Hai chiều chuyển đổi giữa mã điểm và UTF-16

Khi nhận một giá trị Unicode như `U+1D11E`, bạn đang có **mã điểm (code point)**, không phải một `char` Java. Ngược lại, khi đọc một mảng `char[]`, mỗi phần tử là **đơn vị mã UTF-16 (code unit)**. Một mã điểm có thể cần một hoặc hai phần tử.

Hai phương thức trong bài giải quyết hai chiều liên quan:

```text
mã điểm int  ── Character.toChars ──>  một hoặc hai char UTF-16
cặp surrogate hợp lệ ── Character.toCodePoint ──> mã điểm int
```

Điểm quan trọng: `toCodePoint` chỉ ghép **một cặp surrogate**, không phải hàm ghép hai ký tự bất kỳ. Một giá trị BMP thông thường không cần hàm này để trở thành `int`.

Bài dùng hợp đồng Java hiện hành và chương trình Java 17+; không phụ thuộc font có hiển thị được ký hiệu hay không.

## Cần hiểu gì trước khi chuyển đổi?

Không gian mã điểm Unicode có phạm vi `U+0000..U+10FFFF`. BMP là phần `U+0000..U+FFFF`. Các mã điểm ngoài BMP cần hai đơn vị UTF-16:

- Nửa đầu là high surrogate, nằm trong `D800..DBFF`.
- Nửa sau là low surrogate, nằm trong `DC00..DFFF`.
- Đúng thứ tự high rồi low mới tạo thành cặp surrogate.

Vùng surrogate được dành cho cơ chế UTF-16. Khi nói về **giá trị vô hướng Unicode (Unicode scalar value)**, phải loại vùng mã điểm `D800..DFFF` ra khỏi phạm vi Unicode. [Unicode: các định nghĩa về mã điểm, surrogate và UTF-16](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/).

Trong bài, `U+1EC7` là một giá trị BMP, còn ký hiệu khóa Sol `U+1D11E` nằm ngoài BMP. Hai giá trị này cho phép quan sát cả nhánh một `char` lẫn nhánh hai `char`.

## Character.toChars: từ int sang biểu diễn UTF-16

Có hai overload:

```java
public static char[] toChars(int codePoint)
public static int toChars(int codePoint, char[] dst, int dstIndex)
```

Overload thứ nhất trả về một mảng mới chứa biểu diễn UTF-16. Overload thứ hai ghi vào mảng đích có sẵn và trả về **số phần tử đã ghi**, là 1 hoặc 2; nó không trả về mã điểm hay chỉ số tiếp theo. Với giá trị ngoài phạm vi mã điểm Unicode, phương thức ném `IllegalArgumentException`. [Java SE 25: toChars](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#toChars(int)).

Ví dụ dạng ngắn:

```java
char[] bmp = Character.toChars(0x1EC7);    // 1 phần tử: 1EC7
char[] pair = Character.toChars(0x1D11E);  // 2 phần tử: D834 DD1E
String symbol = new String(pair);
```

`new String(pair)` dựng chuỗi từ nội dung mảng. Gọi `pair.toString()` không chuyển nội dung mảng thành chuỗi ký tự mong muốn.

Đừng thay `toChars` bằng phép ép `(char) cp` khi `cp` có thể nằm ngoài BMP. Phép ép về `char` giữ 16 bit thấp, không tạo cặp UTF-16. Với `0x1D11E`, nó chỉ còn `0xD11E` và đã làm mất dữ liệu.

## Character.toCodePoint: ghép một cặp đã kiểm tra

Chữ ký:

```java
public static int toCodePoint(char high, char low)
```

Phương thức này **không kiểm tra tính hợp lệ của hai đối số**. Khi dữ liệu chưa được bảo đảm từ trước, hãy kiểm tra `Character.isSurrogatePair(high, low)` rồi mới ghép. Đừng chờ `toCodePoint('A', 'B')` báo lỗi để xác định hai ký tự có phải cặp hay không. [Java SE 25: toCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#toCodePoint(char,char)).

Đoạn minh họa trong một phương thức:

```java
char high = '\uD834';
char low = '\uDD1E';
if (!Character.isSurrogatePair(high, low)) {
    throw new IllegalArgumentException("Invalid surrogate pair");
}
int cp = Character.toCodePoint(high, low);
// cp == 0x1D11E
```

Nếu dữ liệu chỉ có một `char` BMP thông thường, có thể mở rộng trực tiếp sang `int`:

```java
char letter = '\u1EC7';
int cp = letter;
// cp == 0x1EC7
```

Không tự ghép `letter` với ký tự kế tiếp bằng `toCodePoint`; chúng có thể là hai mã điểm độc lập. Cũng không dùng phép cộng `high + low` để ghép cặp: cộng giá trị hai đơn vị mã không phải giải mã UTF-16.

## Chương trình minh chứng đầy đủ

Lưu thành `CharacterConversionDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;

public class CharacterConversionDemo {
    private static String hex(int value) {
        return String.format(Locale.ROOT, "%04X", value);
    }

    private static String units(char[] chars) {
        StringBuilder out = new StringBuilder();
        for (char ch : chars) {
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(hex(ch));
        }
        return out.toString();
    }

    private static int readStrict(char[] source, int index) {
        Objects.checkIndex(index, source.length);
        char first = source[index];
        if (Character.isHighSurrogate(first)) {
            if (index + 1 >= source.length
                    || !Character.isSurrogatePair(first, source[index + 1])) {
                throw new IllegalArgumentException("Unpaired high surrogate");
            }
            return Character.toCodePoint(first, source[index + 1]);
        }
        if (Character.isLowSurrogate(first)) {
            throw new IllegalArgumentException("Unpaired low surrogate");
        }
        return first;
    }

    public static void main(String[] args) {
        int bmp = 0x1EC7;
        int clef = 0x1D11E;
        char[] one = Character.toChars(bmp);
        char[] pair = Character.toChars(clef);
        System.out.println("BMP units: " + units(one));
        System.out.println("supplementary units: " + units(pair));
        System.out.println("pair valid: " + Character.isSurrogatePair(pair[0], pair[1]));
        System.out.println("decoded: " + hex(Character.toCodePoint(pair[0], pair[1])));
        System.out.println("wrong cast: " + hex((char) clef));

        char[] buffer = new char[5];
        Arrays.fill(buffer, '_');
        int written = Character.toChars(clef, buffer, 1);
        System.out.println("written: " + written);
        System.out.println("buffer units: " + units(buffer));
        String symbol = new String(pair);
        System.out.println("slice equals: " + symbol.equals(new String(buffer, 1, written)));
        System.out.println("String length: " + symbol.length());
        System.out.println("String code points: " + symbol.codePointCount(0, symbol.length()));

        char[] text = ("A" + symbol + "B").toCharArray();
        StringBuilder decoded = new StringBuilder();
        for (int i = 0; i < text.length;) {
            int cp = readStrict(text, i);
            if (decoded.length() > 0) {
                decoded.append(' ');
            }
            decoded.append(hex(cp));
            i += Character.charCount(cp);
        }
        System.out.println("strict scan: " + decoded);

        for (int cp : new int[] {0, 0xFFFF, 0x10000, 0x10FFFF}) {
            char[] encoded = Character.toChars(cp);
            int restored = encoded.length == 1 ? encoded[0]
                    : Character.toCodePoint(encoded[0], encoded[1]);
            System.out.println("boundary " + hex(cp) + ": length=" + encoded.length
                    + ", roundTrip=" + (restored == cp));
        }

        for (int invalid : new int[] {-1, 0x110000}) {
            try {
                Character.toChars(invalid);
            } catch (IllegalArgumentException ex) {
                System.out.println("invalid rejected: " + invalid);
            }
        }

        char[] small = {'_'};
        try {
            Character.toChars(clef, small, 0);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("too small: " + units(small));
        }
        try {
            Character.toChars(clef, null, 0);
        } catch (NullPointerException ex) {
            System.out.println("null destination rejected");
        }

        System.out.println("AB pair valid: " + Character.isSurrogatePair('A', 'B'));
        char[] lone = Character.toChars(0xD800);
        System.out.println("surrogate accepted by toChars: " + units(lone));
        try {
            readStrict(lone, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict scan rejects lone high");
        }
        try {
            readStrict(new char[] {'\uDC00'}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict scan rejects lone low");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 CharacterConversionDemo.java
java CharacterConversionDemo
```

Stdout:

```text
BMP units: 1EC7
supplementary units: D834 DD1E
pair valid: true
decoded: 1D11E
wrong cast: D11E
written: 2
buffer units: 005F D834 DD1E 005F 005F
slice equals: true
String length: 2
String code points: 1
strict scan: 0041 1D11E 0042
boundary 0000: length=1, roundTrip=true
boundary FFFF: length=1, roundTrip=true
boundary 10000: length=2, roundTrip=true
boundary 10FFFF: length=2, roundTrip=true
invalid rejected: -1
invalid rejected: 1114112
too small: 005F
null destination rejected
AB pair valid: false
surrogate accepted by toChars: D800
strict scan rejects lone high
strict scan rejects lone low
```

Hàm `hex` in dạng hệ mười sáu, giúp phân biệt giá trị dữ liệu với cách terminal vẽ ký hiệu. Không có yêu cầu cài font âm nhạc để xác minh `D834 DD1E`.

## Đọc kết quả theo từng mục tiêu

### 1. Một mã điểm có thể tạo hai char

`toChars(0x1EC7)` cho một phần tử, còn `toChars(0x1D11E)` cho cặp `D834 DD1E`. Ghép lại bằng `toCodePoint` cho đúng giá trị `1D11E` ban đầu.

Chuỗi `symbol` chỉ chứa một mã điểm ngoài BMP nhưng `length()` bằng 2. Kết quả `codePointCount` bằng 1 cho thấy số đơn vị UTF-16 và số mã điểm là hai phép đếm khác nhau.

Hai `char` đó không biểu thị hai ký hiệu khóa Sol; chúng cùng tạo biểu diễn cho một mã điểm.

### 2. Overload ghi vào đích không tự quản lý vị trí của bạn

Mảng `buffer` ban đầu có năm dấu gạch dưới. Lệnh `Character.toChars(clef, buffer, 1)` ghi vào vị trí 1 và 2, đồng thời trả về 2. Ba dấu gạch dưới ngoài phần ghi vẫn còn.

Khi tích lũy nhiều mã điểm vào một bộ đệm đã đủ chỗ, cách cập nhật vị trí là:

```java
int position = 0;
position += Character.toChars(0x1EC7, buffer, position);
position += Character.toChars(0x1D11E, buffer, position);
// Ba phần tử đầu là kết quả đã ghi.
String text = new String(buffer, 0, position);
```

Đây là đoạn minh họa tiếp nối với `buffer` đủ dung lượng. `position` tăng theo số `char` thực sự ghi, không tăng cố định một đơn vị cho mỗi mã điểm.

Nếu mảng lớn hơn phần nội dung đang dùng, đừng mặc định `new String(buffer)` chỉ lấy các vị trí đã ghi. Constructor đó lấy cả mảng; dùng overload có `offset` và `count` để chọn đúng vùng nội dung.

Đối với mảng đích, API quy định `NullPointerException` khi mảng là `null`, và `IndexOutOfBoundsException` khi chỉ số không hợp lệ hoặc không đủ chỗ. Riêng trường hợp chỉ còn một vị trí nhưng cần cặp surrogate, high surrogate không được ghi vào vị trí cuối đó. Trong chương trình, mảng một dấu gạch dưới vẫn in thành `005F` sau lỗi. [Java SE 21: toChars với mảng đích](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html#toChars(int,char%5B%5D,int)).

### 3. Đọc tuần tự cần phân nhánh theo đơn vị đầu

`readStrict` trong chương trình áp dụng chính sách từ chối UTF-16 có surrogate đứng riêng:

1. Kiểm tra chỉ số trước khi đọc.
2. Nếu gặp high surrogate, phải có đơn vị sau và phải tạo được cặp hợp lệ; sau đó dùng `toCodePoint`.
3. Nếu gặp low surrogate mà chưa được ghép bởi nhánh trước, từ chối.
4. Nếu không thuộc vùng surrogate, trả giá trị của `char` BMP.

Vòng lặp đọc `A`, khóa Sol và `B`. Sau mỗi mã điểm, `Character.charCount(cp)` cho bước nhảy UTF-16 tương ứng. Vì `readStrict` đã kiểm tra dữ liệu, bước nhảy ở đây chỉ là 1 hoặc 2 và không dùng thay cho bước kiểm tra.

`readStrict` là hàm mẫu xử lý một mảng hoàn chỉnh trong bộ nhớ. Với dữ liệu truyền từng khối, một high surrogate ở cuối khối có thể cần chờ low surrogate từ khối tiếp theo; muốn áp dụng cho nguồn đó, phải thiết kế trạng thái giữa các khối thay vì từ chối ngay như ví dụ mảng hoàn chỉnh.

Nếu chỉ cần đọc theo cách thông thường, các API như `Character.codePointAt` đã hỗ trợ ghép cặp hợp lệ. Tuy nhiên, đừng mặc định mọi API đọc mã điểm đều từ chối surrogate đứng riêng; chính sách “strict” của ví dụ được viết ra rõ ràng.

## Phạm vi mã điểm không đồng nghĩa dữ liệu văn bản đã hợp lệ

Trong chương trình, `Character.toChars(0xD800)` thành công và trả về một surrogate đơn. Điều đó cho thấy kiểm tra phạm vi `0..0x10FFFF` không tự loại vùng surrogate. Java cho phép biểu diễn những giá trị `char` như vậy; yêu cầu dữ liệu văn bản hợp lệ phải được xác định thêm.

Nếu đầu vào là các mã điểm độc lập và mục tiêu là tạo văn bản từ giá trị vô hướng, có thể kiểm tra trước:

```java
boolean scalar = Character.isValidCodePoint(cp)
        && (cp < Character.MIN_SURROGATE || cp > Character.MAX_SURROGATE);
```

Đoạn này giả sử `cp` là một `int` đầu vào trong phương thức đang viết. Điều kiện đầu kiểm tra phạm vi số, điều kiện sau loại surrogate. Nó không khẳng định ký tự được font hỗ trợ hoặc là ký tự được ứng dụng chấp nhận.

Các kiểm tra biên trong chương trình xác nhận:

| Đầu vào | Số char | Ý nghĩa kiểm tra |
| --- | --- | --- |
| `0x0000` | 1 | Cận dưới phạm vi |
| `0xFFFF` | 1 | Cận trên BMP |
| `0x10000` | 2 | Bắt đầu phần ngoài BMP |
| `0x10FFFF` | 2 | Cận trên phạm vi Unicode |
| `-1`, `0x110000` | Không chuyển đổi | Ngoài phạm vi |

Bảng này kiểm tra biểu diễn số, không dùng việc in trực tiếp ký hiệu để đánh giá giá trị biên. Một mã điểm nằm trong phạm vi cũng không đồng nghĩa đó là ký tự văn bản thông thường đã được gán tên.

## Cơ chế số học phía sau cặp surrogate

Có thể hiểu cách biểu diễn của `U+1D11E` bằng công thức UTF-16:

```text
x = codePoint - 0x10000
high = 0xD800 + (x >>> 10)
low  = 0xDC00 + (x & 0x3FF)

codePoint = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
```

Với `codePoint = 0x1D11E`, `x = 0xD11E`, tạo ra `high = 0xD834` và `low = 0xDD1E`. Công thức giải thích vì sao cần đúng hai miền surrogate và đúng thứ tự.

Trong mã ứng dụng, ưu tiên `toChars` và `toCodePoint` sau kiểm tra phù hợp. Công thức chỉ nhằm giúp hiểu cơ chế, không cần viết lại các phép toán này ở mọi nơi.

## Giới hạn và lỗi thường gặp

- **Nhầm char[] với byte[]:** kết quả `toChars` là đơn vị UTF-16 trong API Java, không phải các byte UTF-8 để gửi qua mạng.
- **Cố ép mọi mã điểm vào một char:** làm mất phần cao khi mã điểm ngoài BMP.
- **Cho rằng toCodePoint luôn kiểm tra đầu vào:** hai đối số phải được bảo đảm là cặp hợp lệ trước khi ghép.
- **Gọi toCodePoint cho mọi hai char liên tiếp:** làm sai cả văn bản BMP thông thường như `AB`.
- **Tăng vị trí đích cố định 1:** có thể ghi đè nửa cặp hoặc chọn sai vùng nội dung khi kết quả cần 2 `char`.
- **Coi một mã điểm là một ký tự hiển thị hoàn chỉnh:** dấu kết hợp và một số chuỗi biểu tượng gồm nhiều mã điểm; các hàm trong bài không phân đoạn cụm ký tự hiển thị.

## Thực hành

1. Thay `clef` bằng `0x1F680`, chạy lại và kiểm tra cặp UTF-16 cùng kết quả khôi phục.
2. Đổi `dstIndex` của lệnh ghi cặp vào mảng năm phần tử thành 4. Giải thích vì sao chỉ số nằm trong mảng mà vẫn không đủ chỗ.
3. Đảo hai phần tử của `pair` và kiểm tra `isSurrogatePair`; không dùng giá trị ghép từ một cặp sai làm đáp án Unicode.
4. Bổ sung ca đọc `high surrogate + chữ A` và xác nhận `readStrict` từ chối.
5. Viết phép chuyển đổi khứ hồi cho một mảng giá trị vô hướng: `int` sang `char[]`, đọc lại bằng `readStrict` rồi so với dữ liệu đầu vào.

Khi chọn API, hãy xác định chiều chuyển đổi và định dạng đầu vào: `toChars` tạo một hoặc hai đơn vị UTF-16; `toCodePoint` khôi phục mã điểm từ một cặp surrogate đã hợp lệ.
