# StringBuilder: appendCodePoint và dữ liệu Unicode ngoài BMP

## Từ một ký tự đến biểu diễn UTF-16

Khi xử lý dữ liệu có emoji hoặc chữ thuộc các hệ chữ nằm ngoài BMP, không thể luôn coi “một ký tự bằng một `char`”. **Mã điểm Unicode (code point)** là giá trị số nhận diện một vị trí trong không gian Unicode; **đơn vị mã (code unit)** là đơn vị biểu diễn của một cách mã hóa. Trong API chuỗi Java, một `char` là một đơn vị mã UTF-16.

BMP, viết đầy đủ là Basic Multilingual Plane, gồm các mã điểm từ `U+0000` đến `U+FFFF`. Các mã điểm bổ sung ngoài BMP nằm từ `U+10000` đến `U+10FFFF`; UTF-16 biểu diễn chúng bằng **hai `char` tạo thành cặp surrogate**. Một `int` có thể giữ nguyên giá trị mã điểm ngoài BMP. [Java SE 25: biểu diễn Unicode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).

Bài này dùng API vẫn áp dụng trong Java hiện đại và ví dụ chạy được trên Java 17+. Mục tiêu là biết khi nào cần `appendCodePoint`, hiểu dữ liệu thực sự được nối vào builder và tránh làm mất thông tin khi chuyển từ `int` sang `char`.

## appendCodePoint làm gì?

Chữ ký phương thức:

```java
public StringBuilder appendCodePoint(int codePoint)
```

Phương thức nối biểu diễn UTF-16 của mã điểm vào cuối builder và trả lại chính builder, nên có thể gọi nối tiếp. Hiệu quả tương đương nối mảng `char` do `Character.toChars(codePoint)` tạo ra. Độ dài tăng 1 hoặc 2 tùy mã điểm. [Java SE 25: appendCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#appendCodePoint(int)).

Ví dụ ý tưởng:

```java
StringBuilder message = new StringBuilder();
message.append('[').appendCodePoint(0x1F600).append(']');
```

Mã điểm `U+1F600` biểu diễn emoji mặt cười. `message.length()` bằng 4: một `char` cho dấu mở, hai `char` cho emoji và một `char` cho dấu đóng. Độ dài này là số đơn vị UTF-16, không phải số byte trong tệp hay số ô hiển thị trên màn hình.

### append(int) không có cùng ý nghĩa

Với `int cp = 0x1F600;`, ba cách gọi sau thực hiện ba công việc khác nhau:

| Cách gọi | Điều được nối |
| --- | --- |
| `append(cp)` | Dãy chữ số thập phân `"128512"` |
| `append((char) cp)` | Một đơn vị UTF-16 `0xF600` do ép kiểu làm mất phần cao |
| `appendCodePoint(cp)` | Cặp UTF-16 `D83D DE00` biểu diễn đúng `U+1F600` |

Đừng ép kiểu để “chọn overload ký tự” khi dữ liệu đầu vào là mã điểm ngoài BMP. Trong tình huống này, ép kiểu không phải chuyển mã: nó làm mất thông tin. Nếu `cp` chỉ là một số cần ghi vào báo cáo, `append(cp)` lại là lựa chọn đúng.

## Chương trình chạy đầy đủ

Lưu thành `AppendCodePointDemo.java`. Chương trình in các đơn vị UTF-16 dưới dạng số hệ mười sáu thay vì phụ thuộc font của terminal để hiển thị emoji.

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class AppendCodePointDemo {
    private static String hexUnits(String value) {
        return value.chars()
                .mapToObj(unit -> String.format(Locale.ROOT, "%04X", unit))
                .collect(Collectors.joining(" "));
    }

    private static boolean isScalarValue(int cp) {
        return Character.isValidCodePoint(cp)
                && (cp < Character.MIN_SURROGATE || cp > Character.MAX_SURROGATE);
    }

    private static String buildText(int[] codePoints) {
        StringBuilder out = new StringBuilder();
        for (int cp : codePoints) {
            if (!isScalarValue(cp)) {
                throw new IllegalArgumentException("Not a Unicode scalar value");
            }
            out.appendCodePoint(cp);
        }
        return out.toString();
    }

    public static void main(String[] args) {
        int smile = 0x1F600;
        String text = buildText(new int[] {'A', smile, 'B'});
        System.out.println("units: " + hexUnits(text));
        System.out.println("UTF-16 length: " + text.length());
        System.out.println("code points: " + text.codePointCount(0, text.length()));
        System.out.println("chars count: " + text.chars().count());
        System.out.println("codePoints count: " + text.codePoints().count());

        String wrongNumber = new StringBuilder().append(smile).toString();
        String wrongCast = new StringBuilder().append((char) smile).toString();
        System.out.println("append(int): " + wrongNumber);
        System.out.println("cast units: " + hexUnits(wrongCast));

        String converted = new StringBuilder()
                .append(Character.toChars(smile)).toString();
        System.out.println("toChars same: " + converted.equals(
                new StringBuilder().appendCodePoint(smile).toString()));

        StringBuilder copied = new StringBuilder();
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            copied.appendCodePoint(cp);
            i += Character.charCount(cp);
        }
        System.out.println("round trip: " + text.contentEquals(copied));

        int boundary = text.offsetByCodePoints(0, 2);
        System.out.println("first two units: " + hexUnits(text.substring(0, boundary)));

        for (int invalid : new int[] {-1, 0x110000}) {
            try {
                new StringBuilder().appendCodePoint(invalid);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected: " + invalid);
            }
        }

        String surrogate = new StringBuilder().appendCodePoint(0xD800).toString();
        System.out.println("D800 valid code point: " + Character.isValidCodePoint(0xD800));
        System.out.println("D800 scalar value: " + isScalarValue(0xD800));
        System.out.println("surrogate unit: " + hexUnits(surrogate));

        String combining = buildText(new int[] {'a', 0x0301});
        System.out.println("combining code points: " + combining.codePointCount(
                0, combining.length()));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 AppendCodePointDemo.java
java AppendCodePointDemo
```

Stdout:

```text
units: 0041 D83D DE00 0042
UTF-16 length: 4
code points: 3
chars count: 4
codePoints count: 3
append(int): 128512
cast units: F600
toChars same: true
round trip: true
first two units: 0041 D83D DE00
rejected: -1
rejected: 1114112
D800 valid code point: true
D800 scalar value: false
surrogate unit: D800
combining code points: 2
```

### Đọc kết quả để thấy cơ chế

`buildText` nhận mảng mã điểm `A`, `U+1F600`, `B` và nối lần lượt. Hàm `hexUnits` dùng `chars()` để quan sát **đơn vị UTF-16**, nên thấy bốn giá trị `0041 D83D DE00 0042`. Hai giá trị giữa là một cặp, không phải hai emoji.

`append(int)` nhận cùng số `128512` nhưng tạo sáu chữ số. Sau phép ép `(char)`, kết quả chỉ còn `F600`; thông tin cần để tạo cặp surrogate đã mất. Không thể khôi phục ý nghĩa ban đầu từ `char` đó một cách tổng quát.

Dòng `toChars same: true` kiểm tra hai cách tạo biểu diễn của cùng một mã điểm. Với trường hợp thông thường, dùng `appendCodePoint` thể hiện ý định rõ hơn việc tự tách cặp surrogate. Không cần tự viết phép toán bit để tạo hai nửa UTF-16.

## Duyệt dữ liệu theo mã điểm rồi dựng lại chuỗi

Trong chương trình, vòng lặp sao chép dùng:

```java
for (int i = 0; i < text.length();) {
    int cp = text.codePointAt(i);
    copied.appendCodePoint(cp);
    i += Character.charCount(cp);
}
```

`i` vẫn là **chỉ số UTF-16**. Mỗi lần đọc một mã điểm, bước nhảy là số đơn vị UTF-16 của mã điểm đó. Khi gặp emoji trong ví dụ, vòng lặp tăng `i` thêm 2; với `A` hoặc `B`, nó tăng thêm 1.

Nếu vẫn dùng `i++` sau `codePointAt(i)`, lần tiếp theo có thể trỏ vào nửa sau cặp surrogate. Khi đó chương trình không còn duyệt đúng từng mã điểm và có thể xử lý lặp một phần biểu diễn.

Một cách khác khi không cần giữ chỉ số là duyệt `text.codePoints()`. Phân biệt hai API:

- `chars()` cung cấp từng `char` dưới dạng `int`; cặp surrogate vẫn gồm hai phần tử.
- `codePoints()` kết hợp cặp surrogate hợp lệ thành một giá trị mã điểm ngoài BMP; surrogate đứng riêng vẫn được trả ra, nên đây không phải bộ kiểm tra tính hợp lệ của toàn bộ Unicode.

Đây là hợp đồng hiện hành của API chuỗi. [Java SE 25: chars](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#chars()), [Java SE 25: codePoints](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePoints()).

**Lưu ý về phạm vi kết luận:** sao chép nguyên vẹn mọi `char` theo đúng thứ tự vẫn có thể bảo toàn chuỗi gốc. Vấn đề phát sinh khi coi từng `char` là một ký tự độc lập để phân loại, bỏ, đổi hoặc cắt dữ liệu. Khi logic thực sự làm việc với mã điểm, hãy đọc và nối theo mã điểm.

## Kiểm tra đầu vào: mã điểm và giá trị vô hướng

Hai giá trị `-1` và `0x110000` trong chương trình nằm ngoài phạm vi mã điểm Unicode và bị `appendCodePoint` từ chối bằng `IllegalArgumentException`. Đừng biến một số đầu vào tùy ý thành `char` để né lỗi: ép kiểu có thể che giấu dữ liệu sai.

Cần phân biệt thêm **giá trị vô hướng Unicode (Unicode scalar value)** với phạm vi mà API Java gọi là mã điểm hợp lệ. Giá trị vô hướng loại trừ vùng surrogate `U+D800..U+DFFF`. [Unicode: định nghĩa về mã điểm và giá trị vô hướng](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/).

`Character.isValidCodePoint(cp)` kiểm tra phạm vi số `0..0x10FFFF`. Nó không tự loại các giá trị surrogate, và không khẳng định mã điểm đã được gán cho một ký tự có thể hiển thị. [Java SE 25: isValidCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isValidCodePoint(int)).

Chương trình tự kiểm chứng trường hợp `0xD800`:

- `Character.isValidCodePoint(0xD800)` trả về `true`.
- `appendCodePoint(0xD800)` tạo một `char` surrogate đứng riêng trong builder rỗng.
- `isScalarValue(0xD800)` trả về `false`.

Vì `buildText` có mục tiêu tạo chuỗi từ các giá trị vô hướng độc lập, hàm kiểm tra cả phạm vi mã điểm lẫn việc loại vùng surrogate **trước khi nối**. Đây là chính sách đầu vào của hàm ví dụ, chặt hơn việc chỉ gọi API nối. Không diễn giải nó thành quy định rằng mọi API Java đều tự từ chối surrogate đứng riêng.

Nếu đầu vào là các **đơn vị UTF-16** đã tách sẵn thay vì mã điểm, cần ghép và kiểm tra cặp đúng cách trước khi coi chúng là giá trị vô hướng. Hãy xác định rõ định dạng nguồn; một số `int` có thể là mã điểm, giá trị `char` hoặc byte, và ba ý nghĩa đó không hoán đổi được.

## Nối đúng chưa đủ: thao tác tiếp theo cũng phải giữ ranh giới

`appendCodePoint` tạo đúng cặp cho mã điểm ngoài BMP, nhưng các thao tác dựa trên chỉ số UTF-16 vẫn có thể chia đôi cặp sau đó.

Với `text` trong chương trình:

- `text.substring(0, 2)` chỉ giữ `A` và nửa đầu cặp surrogate.
- `text.offsetByCodePoints(0, 2)` cho chỉ số UTF-16 ngay sau mã điểm thứ hai.
- Dùng chỉ số đó làm điểm kết thúc cho `substring` giữ trọn `A` và emoji, như stdout `0041 D83D DE00`.

Chỉ tìm độ lệch theo số mã điểm khi đã xác nhận chuỗi có đủ số lượng cần giữ; không truyền bừa một số vượt nội dung.

Ngoài ra, một mã điểm không luôn tương ứng một ký tự mà người đọc nhìn thấy. Ví dụ cuối ghép `a` và dấu sắc kết hợp `U+0301`: có hai mã điểm nhưng có thể được hiển thị thành một cụm. Các chuỗi emoji cũng có thể chứa nhiều mã điểm. Nếu yêu cầu là giới hạn tên hiển thị hoặc di chuyển con trỏ theo ký tự người dùng cảm nhận, cần quy tắc ranh giới cụm ký tự; `appendCodePoint` không giải quyết phần đó.

## Chọn cách dùng trong thực tế

Dùng `appendCodePoint` khi nguồn dữ liệu là từng mã điểm: đọc kết quả `codePointAt`, duyệt `codePoints()` hoặc dựng văn bản từ một bảng mã điểm đã kiểm tra.

Nếu đã có một `String` chứa đầy đủ dữ liệu cần nối, `append(string)` là đủ; không cần tách thành mã điểm chỉ để nối lại. Nếu nguồn là byte UTF-8, trước hết phải giải mã byte đúng cách; không truyền từng byte vào `appendCodePoint` rồi kỳ vọng nhận được văn bản gốc.

### Bài tập tự kiểm tra

1. Đổi `smile` thành `0x41`. Dự đoán: `appendCodePoint` tạo `A`, còn `append(int)` tạo `"65"`.
2. Dựng chuỗi từ hai giá trị `0x1F600` liên tiếp. Dự đoán: độ dài UTF-16 là 4, số mã điểm là 2.
3. Đưa `0xD800` vào mảng truyền cho `buildText`. Hàm phải từ chối trước khi nối giá trị đó.
4. Giải thích vì sao `chars().count()` và `codePoints().count()` khác nhau trong ví dụ, nhưng không nhất thiết khác nhau với văn bản chỉ gồm `ABC`.
5. Với chuỗi `a` cộng dấu sắc kết hợp, giải thích vì sao “giữ một mã điểm đầu” chưa chắc giữ trọn hình thức chữ có dấu mà người dùng đang nhìn.

Điểm cần giữ rõ xuyên suốt là **nguồn đang cung cấp mã điểm hay đơn vị UTF-16**. `appendCodePoint` nối theo mã điểm; `length()` và nhiều chỉ số trong API chuỗi vẫn đo theo UTF-16.
