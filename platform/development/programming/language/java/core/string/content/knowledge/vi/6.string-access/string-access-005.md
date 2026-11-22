# `String.offsetByCodePoints()` — di chuyển theo Unicode code point trong Java

## 1. Mục tiêu: vị trí UTF-16 khác với số lượng code point

Trong Java, `String` là dãy các **đơn vị mã UTF-16** (`char`). Chỉ số dùng bởi `String.charAt()`, `substring()`, `codePointAt()` và `offsetByCodePoints()` đều là **chỉ số UTF-16**. Một Unicode code point trong Basic Multilingual Plane (BMP) thường chiếm một `char`; code point ngoài BMP chiếm **hai `char`** (một cặp *high surrogate* và *low surrogate*).

Vì vậy, di chuyển chỉ số thêm `1` đơn vị UTF-16 (`index++`) không luôn đồng nghĩa với di chuyển thêm một code point. `offsetByCodePoints` giải quyết đúng vấn đề này: **nhận một vị trí UTF-16 ban đầu và số code point muốn đi qua; trả về một vị trí UTF-16 mới**.

Ví dụ với chuỗi `"A🙂B"`:

```text
Nội dung nhìn thấy:       A       🙂        B
Unicode code point:      U+0041  U+1F642   U+0042
Độ dài UTF-16:              1       2        1

Chỉ số UTF-16:            0   1   2   3   4
                          | A |  🙂   | B |
Vị trí hợp lệ giữa
các code point:          ^   ^       ^   ^
                         0   1       3   4

index 2 nằm GIỮA hai char tạo thành emoji.
```

`"A🙂B".length()` bằng **4**, còn `codePointCount(0, length())` bằng **3**. Muốn di chuyển hai code point từ đầu chuỗi phải đến chỉ số UTF-16 **3**, không phải **2**.

## 2. Chữ ký và hợp đồng của `offsetByCodePoints`

API thuộc `java.lang.String` (có từ Java 5, dùng trực tiếp trong Java 17+):

```java
public int offsetByCodePoints(int index, int codePointOffset)
```

| Tham số / kết quả | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `index` | Chỉ số UTF-16 | Vị trí bắt đầu di chuyển; hợp lệ trong khoảng `0..length()`, **bao gồm** `length()` |
| `codePointOffset` | Số code point | Số lượng code point cần đi qua: dương tiến về cuối, âm lùi về đầu, 0 đứng yên |
| Giá trị trả về `int` | Chỉ số UTF-16 | Vị trí mới có thể truyền vào các API dùng offset UTF-16, ví dụ `substring` |
| Ngoại lệ | — | `IndexOutOfBoundsException` nếu vị trí ban đầu sai hoặc số bước yêu cầu vượt phần văn bản còn lại theo hướng di chuyển |

Ví dụ về cách hiểu (giả sử `String text = "A🙂B";`):

```java
text.offsetByCodePoints(0, 0);  // 0: không di chuyển
text.offsetByCodePoints(0, 1);  // 1: đi qua 'A'
text.offsetByCodePoints(0, 2);  // 3: đi qua 'A' và '🙂'
text.offsetByCodePoints(0, 3);  // 4: đi qua cả ba code point
text.offsetByCodePoints(4, -1); // 3: lùi qua 'B'
text.offsetByCodePoints(4, -2); // 1: lùi qua 'B' và '🙂'
text.offsetByCodePoints(4, -3); // 0: về đầu chuỗi
```

Những dòng trên là **snippet biểu thức**, chưa phải chương trình độc lập. Điểm cần ghi nhớ: tham số thứ hai tính bằng **code point**, còn **kết quả vẫn là chỉ số UTF-16**.

`offsetByCodePoints` không thay đổi `String`, không trả code point, không trả số ký tự và không cắt chuỗi. Nó chỉ tính một offset mới từ vị trí hiện tại.

## 3. Cơ chế tiến và lùi qua surrogate pair

Một code point ngoài BMP được mã hóa trong UTF-16 thành hai đơn vị `char` liên tiếp:
- *High surrogate*: giá trị `char` trong khoảng `U+D800..U+DBFF`.
- *Low surrogate*: giá trị `char` trong khoảng `U+DC00..U+DFFF`.

Khi bắt đầu tại **ranh giới code point hợp lệ**:
- Di chuyển **tiến** qua ký tự BMP thông thường tăng chỉ số UTF-16 thêm 1; tiến qua một cặp surrogate hợp lệ tăng thêm 2.
- Di chuyển **lùi** qua ký tự BMP thông thường giảm chỉ số 1; lùi qua một cặp surrogate hợp lệ giảm 2.
- Nếu dãy UTF-16 có **surrogate lẻ, không ghép cặp**, Java tính mỗi surrogate lẻ là một code point khi di chuyển. Phương thức không tự chuẩn hóa hoặc sửa dữ liệu đầu vào.

Do đó bạn không thể thay thế tổng quát bằng `index + codePointOffset`, kể cả khi chuỗi “trông có vẻ” chỉ gồm vài ký tự. Nội dung Unicode quyết định số đơn vị UTF-16 phải đi qua.

### Ví dụ Java 17+ chạy độc lập: tiến, lùi và cắt đúng ranh giới

Lưu thành `OffsetByCodePointsDemo.java`:

```java
public class OffsetByCodePointsDemo {
    public static void main(String[] args) {
        String text = "A🙂B";

        int p0 = 0;
        int p1 = text.offsetByCodePoints(p0, 1);
        int p2 = text.offsetByCodePoints(p1, 1);
        int p3 = text.offsetByCodePoints(p2, 1);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println(
                "Code points: " + text.codePointCount(0, text.length()));
        System.out.println(
                "Boundaries: " + p0 + " -> " + p1 + " -> " + p2 + " -> " + p3);
        System.out.println("Forward 2: " + text.offsetByCodePoints(0, 2));
        System.out.println(
                "Back 2: " + text.offsetByCodePoints(text.length(), -2));
        System.out.println("Emoji: " + text.substring(p1, p2));
        System.out.println(
                "Code point: U+" +
                Integer.toHexString(text.codePointAt(p1)).toUpperCase());
    }
}
```

Biên dịch và chạy bằng JDK 17+ (nguồn mã UTF-8):

```bash
javac -encoding UTF-8 OffsetByCodePointsDemo.java
java OffsetByCodePointsDemo
```

```text
UTF-16 length: 4
Code points: 3
Boundaries: 0 -> 1 -> 3 -> 4
Forward 2: 3
Back 2: 1
Emoji: 🙂
Code point: U+1F642
```

Chỉ số `p1 = 1` ngay trước emoji; vì emoji chiếm hai `char` nên `p2 = 3`. `substring(p1,p2)` lấy đúng hai đơn vị UTF-16 biểu diễn **một** code point emoji. `codePointAt(p1)` đọc code point tại chỉ số UTF-16 1, trả `0x1F642`; `charAt(p1)` chỉ trả high surrogate.

## 4. Di chuyển từng code point trong vòng lặp

### Duyệt tiến

Khi viết thuật toán duyệt từng code point, dùng một biến `int index` đại diện cho **vị trí UTF-16 ở đầu code point tiếp theo**. Bắt đầu tại 0, tiếp tục đến khi `index == text.length()`:

```java
for (int index = 0; index < text.length(); ) {
    int codePoint = text.codePointAt(index);
    // Xử lý codePoint ở đây.
    index = text.offsetByCodePoints(index, 1);
}
```

Không thêm `index++` vào phần cuối vòng lặp: số `char` của code point vừa đọc có thể là 1 hoặc 2. Có thể thay bước di chuyển bằng `index += Character.charCount(codePoint)` khi `codePoint` được đọc đúng từ `codePointAt(index)`, nhưng `offsetByCodePoints` thể hiện trực tiếp ý định di chuyển theo code point và hỗ trợ cả hướng âm.

### Duyệt lùi

Muốn đi ngược từ cuối chuỗi, đặt `index = text.length()` và lùi một code point **trước khi** gọi `codePointAt`:

```java
for (int index = text.length(); index > 0; ) {
    index = text.offsetByCodePoints(index, -1);
    int codePoint = text.codePointAt(index);
    // Xử lý codePoint ở đây.
}
```

Vị trí `length()` hợp lệ đối với `offsetByCodePoints`; nó là ranh giới **sau ký tự cuối**. Nhưng `text.codePointAt(text.length())` không hợp lệ, vì `codePointAt` cần vị trí của một phần tử `char` thực tế, từ 0 đến `length()-1`.

### Ví dụ hai chiều chạy độc lập

Lưu thành `WalkCodePoints.java`:

```java
public class WalkCodePoints {
    public static void main(String[] args) {
        String value = "A🙂B";

        StringBuilder forward = new StringBuilder();
        for (int i = 0; i < value.length(); ) {
            int next = value.offsetByCodePoints(i, 1);
            forward.append('[').append(value, i, next).append(']');
            i = next;
        }

        StringBuilder backward = new StringBuilder();
        for (int i = value.length(); i > 0; ) {
            int previous = value.offsetByCodePoints(i, -1);
            backward.append(value, previous, i);
            i = previous;
        }

        System.out.println(forward);
        System.out.println(backward);
    }
}
```

```bash
javac -encoding UTF-8 WalkCodePoints.java
java WalkCodePoints
```

```text
[A][🙂][B]
B🙂A
```

Bước `append(value, i, next)` lấy một đoạn `CharSequence` theo **chỉ số UTF-16 [i, next)**, nên emoji không bị cắt ở giữa hai surrogate. Vòng lặp lùi thu được các code point theo thứ tự đảo ngược. Tuy nhiên, đảo thứ tự **code point** không phải lúc nào cũng tương đương đảo thứ tự **ký tự hiển thị** (ví dụ ký tự có dấu tổ hợp), vì một grapheme cluster có thể gồm nhiều code point.

## 5. Dùng `offsetByCodePoints` với `substring`

`String.substring(beginIndex, endIndex)` nhận **chỉ số UTF-16**. Nếu yêu cầu nghiệp vụ lại nói “lấy từ code point thứ `a` đến trước code point thứ `b`”, không nên truyền `a` và `b` trực tiếp vào `substring`.

Cách đúng là:
1. Kiểm tra chỉ số tính theo code point và tổng số code point.
2. Đổi offset code point đầu thành chỉ số UTF-16 qua `offsetByCodePoints(0, beginCodePoint)`.
3. Từ ranh giới đầu, tiến `endCodePoint - beginCodePoint` code point để tìm ranh giới cuối.
4. Gọi `substring(beginUtf16, endUtf16)`.

Ví dụ hoàn chỉnh, lưu `SliceByCodePoints.java`:

```java
import java.util.Objects;

public class SliceByCodePoints {
    static String slice(String text, int beginCodePoint, int endCodePoint) {
        Objects.requireNonNull(text, "text");

        int total = text.codePointCount(0, text.length());
        if (beginCodePoint < 0
                || endCodePoint < beginCodePoint
                || endCodePoint > total) {
            throw new IndexOutOfBoundsException("Invalid code point range");
        }

        int beginUtf16 = text.offsetByCodePoints(0, beginCodePoint);
        int endUtf16 = text.offsetByCodePoints(
                beginUtf16, endCodePoint - beginCodePoint);
        return text.substring(beginUtf16, endUtf16);
    }

    public static void main(String[] args) {
        String text = "A🙂B🚀";

        System.out.println(slice(text, 1, 3));
        System.out.println(slice(text, 0, 2));
        System.out.println(slice(text, 3, 4));
        System.out.println(slice(text, 2, 2).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SliceByCodePoints.java
java SliceByCodePoints
```

```text
🙂B
A🙂
🚀
true
```

Hàm này xem `beginCodePoint` là vị trí đầu **tính theo số code point**, `endCodePoint` là ranh giới cuối **loại trừ**. Nó chuyển hai vị trí đó về offset UTF-16 trước khi cắt. Chỉ số trong `substring` là 0-based theo đơn vị `char`; chỉ số đầu/cuối mà hàm `slice` nhận là 0-based theo ranh giới code point. Hai hệ tọa độ không được dùng lẫn nhau.

**Khi dữ liệu có surrogate lẻ:** phép đếm và di chuyển của Java vẫn có quy tắc nhất quán (mỗi surrogate lẻ tính một code point), nhưng hàm trên không phải bộ kiểm định chuỗi Unicode hợp lệ. Ứng dụng đòi hỏi Unicode scalar value hợp lệ nên kiểm tra dữ liệu riêng.

## 6. Ranh giới và ngoại lệ

`offsetByCodePoints(index, codePointOffset)` sẽ ném `IndexOutOfBoundsException` nếu:
- `index < 0` hoặc `index > text.length()`.
- `codePointOffset > 0` nhưng không còn đủ code point ở đoạn sau `index`.
- `codePointOffset < 0` nhưng không có đủ code point ở đoạn trước `index`.

Các tình huống điển hình với `String text = "A🙂B";`:

| Lệnh | Kết quả | Vì sao |
| --- | --- | --- |
| `text.offsetByCodePoints(0, 0)` | `0` | Giữ nguyên vị trí đầu |
| `text.offsetByCodePoints(4, 0)` | `4` | Giữ nguyên vị trí cuối |
| `text.offsetByCodePoints(0, 3)` | `4` | Đi qua đúng 3 code point |
| `text.offsetByCodePoints(4, -3)` | `0` | Lùi đúng 3 code point |
| `text.offsetByCodePoints(4, 1)` | Ngoại lệ | Không còn code point phía sau |
| `text.offsetByCodePoints(0, -1)` | Ngoại lệ | Không có code point phía trước |
| `text.offsetByCodePoints(0, 4)` | Ngoại lệ | Chuỗi chỉ có 3 code point |
| `text.offsetByCodePoints(5, 0)` | Ngoại lệ | Chỉ số UTF-16 ngoài phạm vi |

Nếu cần xử lý việc “không đủ bước” như một kết quả nghiệp vụ bình thường, hãy kiểm tra trước số code point khả dụng bằng `codePointCount(index, length())` khi tiến, hoặc `codePointCount(0, index)` khi lùi, **với điều kiện `index` đã ở một ranh giới code point thích hợp**. Đừng nuốt mọi `IndexOutOfBoundsException`: lỗi có thể cho thấy chương trình đã trộn lẫn chỉ số UTF-16 và chỉ số code point.

### Không tự động sửa vị trí nằm giữa surrogate pair

Đây là một trường hợp tinh tế. `index` về mặt API chỉ cần thỏa `0 <= index <= length()`; phương thức **không yêu cầu kiểm tra** rằng `index` bắt đầu tại ranh giới code point và cũng **không tự dịch** nó về đầu cặp surrogate.

Với `text = "A🙂B"`, `index = 2` nằm ở **low surrogate** của emoji:

```java
String text = "A🙂B";
System.out.println(Character.isLowSurrogate(text.charAt(2))); // true
System.out.println(text.offsetByCodePoints(2, 1));            // 3
System.out.println(text.offsetByCodePoints(2, -1));           // 1
```

Đây là snippet đặt trong `main`. Khi tiến từ vị trí giữa cặp, nửa low surrogate ở phía sau được tính như một đơn vị lẻ trong phạm vi cần đi; khi lùi, nửa high surrogate ở phía trước cũng được tính riêng. Kết quả **không** có nghĩa vị trí 2 là ranh giới hợp lý để xử lý emoji trọn vẹn.

**Quy tắc thực hành:** luôn tạo con trỏ từ đầu hoặc cuối chuỗi rồi di chuyển bằng `offsetByCodePoints`; hoặc chuyển vị trí code point sang UTF-16 một lần trước khi dùng. Không lấy một chỉ số `charAt` bất kỳ rồi mặc định nó nằm ở đầu code point.

## 7. Surrogate lẻ và những điều `offsetByCodePoints` không làm

Một chuỗi Java có thể chứa một high surrogate không đi kèm low surrogate hợp lệ, hoặc một low surrogate đơn độc. Trong phạm vi xét bởi `offsetByCodePoints`, **surrogate lẻ được đếm là một code point** theo hợp đồng Java. Điều này không biến nó thành Unicode scalar value hợp lệ và không có nghĩa Java “sửa” văn bản.

Ví dụ độc lập, lưu `UnpairedSurrogateDemo.java`:

```java
public class UnpairedSurrogateDemo {
    public static void main(String[] args) {
        char[] chars = {'A', '\uD83D', 'B'};
        String text = new String(chars);

        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));
        System.out.println(text.offsetByCodePoints(1, 1));
        System.out.println(
                Integer.toHexString(text.codePointAt(1)));
    }
}
```

```bash
javac -encoding UTF-8 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
```

```text
3
3
2
d83d
```

Mảng có ba đơn vị UTF-16: `'A'`, một high surrogate lẻ `\uD83D`, rồi `'B'`. Phương thức đếm ba code point theo quy tắc Java và di chuyển từ offset 1 sang 2 qua surrogate lẻ. Đây là cách API xử lý dữ liệu chưa ghép cặp, không phải ví dụ một ký tự Unicode hợp lệ có mã U+D83D.

Một giới hạn khác: **code point không đồng nghĩa với grapheme cluster**. Ví dụ `"e\u0301"` là chữ `e` theo sau bằng dấu sắc kết hợp. Nó có **hai code point** nhưng thường hiển thị như một chữ “é”. Di chuyển một code point sẽ đứng giữa chữ cơ sở và dấu kết hợp. Các chuỗi emoji nối bằng ZWJ hay biểu tượng cờ còn có thể gồm nhiều code point cho một ký tự người dùng nhìn thấy. Nếu yêu cầu là di chuyển theo *grapheme cluster* để xử lý caret/chọn văn bản, cần thuật toán phân đoạn ký tự phù hợp với Unicode; `offsetByCodePoints` chỉ đáp ứng mức code point.

## 8. Đặt cạnh các phương thức liên quan

| API | Đầu vào là chỉ số gì? | Đầu ra là gì? | Công dụng |
| --- | --- | --- | --- |
| `length()` | Không có | Số **char** UTF-16 | Độ dài bộ lưu trữ logic theo UTF-16 |
| `charAt(i)` | UTF-16 | Một `char` | Đọc đúng một đơn vị UTF-16 |
| `codePointAt(i)` | UTF-16 | Một `int` code point | Đọc code point tại vị trí đầu (nếu là high surrogate có low theo sau thì ghép đôi) |
| `codePointBefore(i)` | UTF-16 ranh giới sau phần tử | Một `int` code point | Đọc code point ngay trước vị trí đó |
| `codePointCount(begin,end)` | Hai chỉ số UTF-16 | **Số** code point trong đoạn | Đếm, không trả chỉ số |
| `offsetByCodePoints(index,n)` | UTF-16 + **số** code point | Chỉ số UTF-16 | Di chuyển con trỏ |
| `substring(begin,end)` | Hai chỉ số UTF-16 | `String` | Cắt đoạn theo ranh giới cung cấp |
| `codePoints()` | Không có | `IntStream` | Duyệt giá trị code point |
| `chars()` | Không có | `IntStream` của đơn vị `char` | Duyệt từng đơn vị UTF-16 |

Cần phân biệt đặc biệt hai lời gọi:

```java
int howMany = text.codePointCount(0, text.length()); // SỐ lượng
int where = text.offsetByCodePoints(0, 2);           // VỊ TRÍ UTF-16
```

Không đưa `howMany` thẳng vào `substring` như một chỉ số UTF-16. `codePointCount` và `offsetByCodePoints` là hai phép toán khác nhau: **đếm** và **đổi vị trí sau khi di chuyển**.

Nếu chỉ muốn duyệt tuần tự toàn bộ chuỗi theo code point mà không cần vị trí, `text.codePoints()` có thể đơn giản hơn. Nếu cần vị trí để tương tác với `substring`, `regionMatches`, hoặc ghi nhớ con trỏ UTF-16, `offsetByCodePoints` hữu ích.

Java cũng cung cấp `Character.offsetByCodePoints(CharSequence seq, int index, int codePointOffset)`; phiên bản này nhận một `CharSequence`, cho phép thuật toán dùng với các lớp triển khai ngoài `String`. Ngoài ra còn overload cho một vùng `char[]` với `start`, `count` và `index`; ở đó cần tuân thủ ranh giới **của vùng mảng được chỉ định**, không mặc định toàn bộ mảng. Dù API nào, kiểu chỉ số trả về vẫn là offset theo đơn vị UTF-16.

## 9. Thiết kế hàm di chuyển an toàn

Một API lưu vị trí trỏ vào `String` nên xác định rõ hệ tọa độ. Ví dụ:
- Tên `utf16Offset` cho vị trí đưa vào `charAt`/`substring`/`offsetByCodePoints`.
- Tên `codePointOffset` hoặc `codePointIndex` cho số bước hoặc thứ tự code point.
- Khi cần đi từ code point thứ `k` về chỉ số UTF-16, dùng `text.offsetByCodePoints(0, k)` sau khi đã kiểm tra `0 <= k <= text.codePointCount(0,text.length())`.
- Khi cần đi từ vị trí UTF-16 `p` tới vị trí tương ứng code point thứ mấy từ đầu, dùng `text.codePointCount(0,p)` **nếu `p` là ranh giới đúng**; nếu `p` cắt surrogate pair thì đây không còn là phép đổi vị trí nguyên vẹn.
- Nếu phải di chuyển nhiều bước liên tục, giữ và cập nhật vị trí hiện tại; tránh quét lại từ 0 sau mỗi bước.

Về hiệu năng, `offsetByCodePoints` phải xem xét nội dung trong phạm vi đi qua để nhận ra cặp surrogate; không giả định truy cập code point thứ `k` có chi phí hằng số. Duyệt tuần tự với vị trí được cập nhật là lựa chọn rõ ràng; nếu cần truy cập ngẫu nhiên rất nhiều vị trí code point trên cùng văn bản lớn, cân nhắc lưu chỉ số ranh giới đã tính trước hoặc dùng biểu diễn dữ liệu phù hợp và đo đạc thực tế trước khi tối ưu.

Với `StringBuilder` mutable, dữ liệu có thể thay đổi và các vị trí UTF-16 cũ trở nên không còn chính xác sau thao tác chèn/xóa. Không duyệt dựa trên các offset đã tính cũ trong lúc nội dung đang thay đổi mà không có quy tắc cập nhật vị trí thích hợp.

## 10. Các lỗi phổ biến

1. **Dùng `index++` để đi tới “ký tự Unicode kế tiếp”.** Nếu gặp emoji ngoài BMP, chỉ số sẽ đi vào giữa cặp surrogate. Dùng `offsetByCodePoints(index,1)` từ ranh giới hợp lệ.
2. **Nhầm giá trị trả về là số code point.** Kết quả của `offsetByCodePoints` là offset UTF-16; số code point trong đoạn lấy từ `codePointCount`.
3. **Dùng chỉ số code point trực tiếp với `substring`.** Chuyển hai đầu đoạn thành vị trí UTF-16 trước.
4. **Gọi `codePointAt(length())`.** Vị trí cuối hợp lệ làm **điểm xuất phát** để lùi, nhưng không hợp lệ để đọc code point phía sau.
5. **Không xét bước âm.** `codePointOffset` âm là hợp lệ và cần thiết cho duyệt lùi; nó có thể gây ngoại lệ nếu lùi quá đầu.
6. **Giả định chỉ số UTF-16 bất kỳ đều ở đầu code point.** Phương thức không tự sửa khi điểm bắt đầu nằm giữa surrogate pair.
7. **Cho rằng API luôn có dữ liệu Unicode hợp lệ.** Surrogate lẻ có thể tồn tại trong `String` và được Java tính như một code point trong các API liên quan.
8. **Nhầm code point với ký tự hiển thị.** Dấu tổ hợp, cờ, emoji ZWJ có thể chứa nhiều code point; cần phân đoạn grapheme nếu bài toán yêu cầu.
9. **Đo lường chi phí như truy cập phần tử mảng.** Di chuyển theo code point cần quét nội dung giữa các ranh giới; tránh tính lại từ đầu vô ích.

## 11. Câu hỏi tự kiểm tra

Với `String s = "X🙂Y";`, hãy tự trả lời:

1. `s.length()` và `s.codePointCount(0,s.length())` khác nhau thế nào?
2. `s.offsetByCodePoints(0,2)` trả về chỉ số mấy? Vì sao không phải `2`?
3. `s.offsetByCodePoints(s.length(),-2)` trả về chỉ số mấy?
4. Nếu muốn lấy riêng emoji bằng `substring`, phải truyền hai chỉ số UTF-16 nào?
5. Vì sao `s.offsetByCodePoints(2,1)` không phải cách đúng để tiến **từ đầu emoji** sang code point sau?

Đáp án: (1) `4` và `3`; (2) `3`; (3) `1`; (4) `substring(1,3)`; (5) vị trí `2` đã nằm giữa hai surrogate của emoji, không phải ranh giới code point để bắt đầu duyệt.

**Quy tắc cần nhớ:** `offsetByCodePoints` nhận **offset UTF-16 hiện tại** và **số bước code point**, sau đó trả lại **offset UTF-16 mới**. Hãy sinh và duy trì các vị trí ở ranh giới code point khi chuyển qua lại giữa duyệt Unicode và các API Java dùng chỉ số `char`.

## Tài liệu API chính thức (Java SE 17)

- [`String.offsetByCodePoints`, `codePointAt`, `codePointCount`, `substring` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Character.offsetByCodePoints`, `charCount`, surrogate helpers — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [`CharSequence` và `codePoints()` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
