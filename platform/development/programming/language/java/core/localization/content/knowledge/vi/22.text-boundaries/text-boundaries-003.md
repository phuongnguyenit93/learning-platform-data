# BreakIterator: following, preceding, isBoundary và chỉ số UTF-16 trong Java

Khi người dùng đặt con trỏ vào giữa một chuỗi, muốn chọn từ gần nhất, di chuyển một “ký tự nhìn thấy” hoặc cắt một đoạn văn bản, **chỉ số của Java `String` không nhất thiết là ranh giới mà người dùng mong muốn**. Java có `java.text.BreakIterator` để tìm các ranh giới văn bản (*text boundaries*) theo các quy tắc phù hợp từng loại: ký tự, từ, dòng và câu. Ba phương thức rất dễ nhầm là **`following(int)`**, **`preceding(int)`** và **`isBoundary(int)`**.

Bài này giải thích chi tiết:

- Ranh giới thực chất là **vị trí giữa các đơn vị mã UTF-16**, không phải số thứ tự từ.
- `following(offset)` tìm biên **lớn hơn hẳn** `offset`; `preceding(offset)` tìm biên **nhỏ hơn hẳn** `offset`; `isBoundary(offset)` kiểm tra **chính offset**.
- `BreakIterator.DONE`, trường hợp đầu/cuối chuỗi, offset không hợp lệ và trạng thái hiện hành của iterator.
- Vì sao emoji, ký tự ngoài BMP và dấu kết hợp khiến `String.length()`, `codePointCount` và “ký tự người dùng nhìn thấy” khác nhau.
- Cách dùng kết quả biên với `substring` và xử lý vùng chọn/di chuyển con trỏ.
- Vì sao không thể lấy chỉ số theo code point, byte UTF-8 hoặc số từ rồi truyền thẳng cho `following`.

Ví dụ dành cho **Java 17+**, dùng `Locale.ROOT` hoặc locale tường minh và các đoạn đầu ra xác định được; với quy tắc phân tách từ/câu phụ thuộc dữ liệu locale của JDK, bài tập trung vào **bất biến API** thay vì khẳng định mọi bản JDK phải chia từ giống hệt nhau.

## 1. BreakIterator là gì?

`BreakIterator` là một abstract class trong package `java.text`. Ta lấy triển khai từ factory:

| Factory | Mục đích |
| --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Các ranh giới đơn vị văn bản được dùng cho dịch chuyển ký tự; không chỉ đơn giản là một UTF-16 `char` |
| `BreakIterator.getWordInstance(locale)` | Ranh giới của các đoạn có thể gồm từ, khoảng trắng và dấu câu |
| `BreakIterator.getLineInstance(locale)` | Các điểm có thể ngắt dòng theo quy tắc ngôn ngữ |
| `BreakIterator.getSentenceInstance(locale)` | Ranh giới câu |

Một instance chỉ làm việc với **văn bản đã được gán**:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator boundaries =
        BreakIterator.getWordInstance(Locale.ROOT);
boundaries.setText("Hello, Việt Nam!");
```

Đây là **fragment**, cần nằm trong phương thức Java. Sau `setText`, iterator biết chuỗi cần quét. Các lời gọi `first()`, `last()`, `next()`, `previous()`, `following(...)`, `preceding(...)` có thể cập nhật **vị trí hiện hành**.

`BreakIterator` không tự cắt hoặc xóa chuỗi; nó trả về **offset**. Việc lấy nội dung tương ứng thường dùng `String.substring(start, end)` với hai chỉ số đã kiểm tra.

### Một biên là một vị trí, không phải một ký tự

Chuỗi `"cat"` có ba đơn vị mã UTF-16, nhưng có **bốn vị trí biên** có thể có:

```text
String:            c   a   t
UTF-16 index:      0   1   2
Boundary slots:   0 | 1 | 2 | 3
                 ^   ^   ^   ^
```

Với `getCharacterInstance`, một chuỗi ASCII đơn giản như `"cat"` có các biên `0, 1, 2, 3`. Biên `3` là **cuối chuỗi** (`String.length()`), không phải chỉ số một ký tự tồn tại tại vị trí 3.

Các ranh giới từ hoặc câu thường **thưa hơn** ranh giới ký tự: khoảng từ `start` đến `end` có thể chứa nhiều UTF-16 code units. Bản chất “boundary” phụ thuộc loại iterator được chọn.

## 2. Tại sao offset là UTF-16, không phải code point?

Java `String` lưu chuỗi theo **các đơn vị mã UTF-16**. Một ký tự Unicode ở BMP thường chiếm một đơn vị mã `char`; nhiều code point ngoài BMP cần **hai** `char` tạo thành surrogate pair.

Ví dụ `"A😀B"`:

```text
Nội dung nhìn thấy:       A       😀       B
Code point:             U+0041  U+1F600   U+0042
Số code point:             1       1        1
Số đơn vị mã UTF-16:       1       2        1
UTF-16 offsets:         0   1   2   3   4
                        | A | hi  lo | B |
Boundary ký tự:         0   1       3   4
                                ^^^^^
                          hai đơn vị mã cho 😀
```

`String.length()` của chuỗi là **4**, còn `codePointCount(0, length())` là **3**. Chỉ số UTF-16 `2` nằm **giữa high surrogate và low surrogate**: nó không phải vị trí hợp lệ để tách đôi emoji như một ký tự hoàn chỉnh.

Các API sau trả hoặc nhận **UTF-16 index**:

- `String.length()`, `String.charAt(index)`, `String.substring(begin, end)`.
- `String.offsetByCodePoints(index, count)`: **trả về** chỉ số UTF-16 sau khi dịch theo code points.
- `BreakIterator.first()/next()/following()/preceding()/current()`, với văn bản được cấp bằng `setText(String)`.
- `StringCharacterIterator` với range phù hợp, nhưng có thể có **beginIndex khác 0**, cần lưu ý khi chuyển offset.

**Không truyền số thứ tự code point như offset UTF-16.** Muốn đổi vị trí “sau 2 code point kể từ đầu” thành UTF-16 offset, dùng `text.offsetByCodePoints(0, 2)`. Tuy nhiên, **biên code point vẫn chưa chắc là biên ký tự nhìn thấy**, vì một grapheme có thể chứa nhiều code points như chữ với dấu kết hợp.

## 3. following(offset): biên đầu tiên *sau* một offset

`following(int offset)` trả về **biên đầu tiên có vị trí lớn hơn hẳn offset**:

```text
following(offset) = min { b ∈ B | b > offset }
```

Ở đây `B` là tập biên của iterator với văn bản đang xét. Nếu không còn biên nào sau offset, phương thức trả về `BreakIterator.DONE`.

**Tính chất cần nhớ:**

- Nếu `offset` **đang là một boundary**, `following(offset)` **không** trả lại chính offset: nó tìm biên kế tiếp.
- Nếu `offset` **nằm giữa hai boundary**, kết quả là biên ở phía sau.
- Nếu `offset == lastBoundary`, kết quả là `DONE`.
- `offset` nằm ngoài vùng văn bản cho phép khiến `following` ném `IllegalArgumentException`.
- Khi thành công, iterator chuyển current position tới biên được trả về; khi offset đã ở last boundary và kết quả `DONE`, trạng thái current không bị đổi theo hợp đồng API.

Ví dụ có biên `0, 2, 5`:

| Gọi | Kết quả | Vì sao |
| --- | --- | --- |
| `following(0)` | `2` | Biên đầu tiên lớn hơn 0 |
| `following(1)` | `2` | 1 nằm giữa 0 và 2 |
| `following(2)` | `5` | Không trả về chính 2 |
| `following(4)` | `5` | 4 nằm trong đoạn 2–5 |
| `following(5)` | `DONE` | Đã ở biên cuối |

Bảng là **minh họa theo tập biên giả định**; không phải lời khẳng định một câu tiếng Việt nào đó nhất định có các boundary `0, 2, 5` ở mọi JDK.

## 4. preceding(offset): biên cuối cùng *trước* một offset

`preceding(int offset)` trả về **biên cuối cùng nhỏ hơn hẳn offset**:

```text
preceding(offset) = max { b ∈ B | b < offset }
```

Đây là đối xứng về ý nghĩa với `following`:

- Nếu `offset` đang là biên, `preceding(offset)` vẫn đi **lùi sang biên trước**, không trả lại chính offset.
- Nếu offset ở bên trong đoạn, trả về biên bên trái.
- Nếu `offset == firstBoundary`, trả `DONE`.
- Ngoài phạm vi văn bản, ném `IllegalArgumentException`.
- Khi thành công, current position được chuyển đến biên trả về; trường hợp ở first boundary, kết quả `DONE` không khiến current di chuyển ngoài phạm vi.

Với cùng tập biên `0, 2, 5`:

| Gọi | Kết quả |
| --- | --- |
| `preceding(0)` | `DONE` |
| `preceding(1)` | `0` |
| `preceding(2)` | `0` |
| `preceding(4)` | `2` |
| `preceding(5)` | `2` |

**Bẫy off-by-one:** người dùng click đúng ở biên giữa hai từ. Nếu muốn “từ chứa vị trí này”, ta phải xác định chính sách chọn **đoạn bên trái hay bên phải**, không đơn giản gọi cả `following(offset)` và `preceding(offset)` mà mặc định đó là hai đầu của một từ duy nhất.

## 5. isBoundary(offset): kiểm tra *chính vị trí đó*

`isBoundary(int offset)` trả về `true` khi **chính offset** thuộc tập biên của iterator, ngược lại trả `false`. Nó không hỏi “offset có nằm trong một từ hay không”.

Ví dụ với `B = {0, 2, 5}`:

```text
isBoundary(0) = true
isBoundary(1) = false
isBoundary(2) = true
isBoundary(3) = false
isBoundary(5) = true
```

Các điểm cần lưu ý:

1. **Đầu và cuối văn bản** thường là boundary hợp lệ; đối với `setText(String)`, dải offset là `0..text.length()` (bao gồm hai đầu).
2. `isBoundary(-1)` hay `isBoundary(text.length()+1)` ném `IllegalArgumentException`, không chỉ trả `false`.
3. Không dùng `isBoundary` để kiểm tra xem UTF-16 `char` là một ký tự Unicode độc lập. Nó kiểm tra **boundary của loại BreakIterator đang dùng** (character/word/line/sentence).
4. Nếu cần giữ state của iterator, đừng giả định mọi phương thức hỏi biên là phép toán **không có tác dụng lên con trỏ**. Có thể gọi `first()` hoặc định vị lại bằng `following/preceding` trước khi thực hiện vòng lặp tiếp theo. Tài liệu API có các hành vi current position riêng cho thao tác định vị.

### So ba phương thức tại một boundary

Với `B = {0, 2, 5}`, khi offset là `2`:

```text
isBoundary(2) == true
preceding(2) == 0
following(2) == 5
```

Điểm `2` thuộc tập biên, nhưng cả `following` và `preceding` **đều bỏ qua chính nó** do quan hệ lớn hơn/nhỏ hơn nghiêm ngặt. Đây là sự khác biệt quan trọng nhất trong đề bài.

## 6. Ví dụ Java 17+ chạy độc lập: các biên ASCII chắc chắn

Tạo file **`BoundaryMethodsDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryMethodsDemo {
    private static String label(int pos) {
        return pos == BreakIterator.DONE
                ? "DONE" : Integer.toString(pos);
    }

    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("cat");

        System.out.println("Length: 3");
        System.out.println("following(1): " + label(it.following(1)));
        System.out.println("preceding(2): " + label(it.preceding(2)));
        System.out.println("isBoundary(2): " + it.isBoundary(2));
        System.out.println("following(3): " + label(it.following(3)));
        System.out.println("preceding(0): " + label(it.preceding(0)));

        System.out.print("All boundaries:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BoundaryMethodsDemo.java
java BoundaryMethodsDemo
```

Stdout:

```text
Length: 3
following(1): 2
preceding(2): 1
isBoundary(2): true
following(3): DONE
preceding(0): DONE
All boundaries: 0 1 2 3
```

Ví dụ dùng chuỗi ASCII đơn giản và `getCharacterInstance` để tránh sự khác nhau về việc tách từ của một văn bản có ngữ cảnh phức tạp. Vòng lặp `first()/next()` liệt kê **cả biên ở đầu và biên cuối**, chứ không đếm số ký tự bằng cách đếm trực tiếp số dòng output.

**Chú ý:** Vòng lặp bắt đầu bằng `first()`, không dựa vào current position còn lại sau các lệnh `following/preceding/isBoundary` trước đó.

## 7. Emoji là hai UTF-16 code units nhưng một code point

Tạo file **`SurrogateBoundaryDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SurrogateBoundaryDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B"; // A😀B

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Boundary at 2: "
                + it.isBoundary(2));
        System.out.println("Boundary at 3: "
                + it.isBoundary(3));
        System.out.println("following(1): " + it.following(1));
        System.out.println("preceding(3): " + it.preceding(3));
        System.out.println("Emoji length: "
                + text.substring(1, 3).length());

        System.out.print("Breaks:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

```bash
javac -encoding UTF-8 SurrogateBoundaryDemo.java
java SurrogateBoundaryDemo
```

Stdout trong JDK 17:

```text
UTF-16 length: 4
Code points: 3
Boundary at 2: false
Boundary at 3: true
following(1): 3
preceding(3): 1
Emoji length: 2
Breaks: 0 1 3 4
```

**Giải thích:** `\uD83D\uDE00` là một cặp surrogate trong chuỗi Java và cùng mã hóa code point `U+1F600`. Offset `1` nằm trước emoji, offset `3` ở sau nó; `2` nằm **giữa** hai code units nên không được xem là biên của ký tự này.

Nếu code vô tình gọi `text.substring(1, 2)`, kết quả chỉ chứa **high surrogate**; nó không phải một Unicode scalar value hoàn chỉnh và có thể hiển thị thành ký tự thay thế khi encode sang UTF-8. Đừng dùng `substring(index, index+1)` cho mọi ký tự người dùng nhập.

**Đặc biệt:** một *grapheme cluster* có thể chứa nhiều code points như `a` cộng dấu sắc hoặc chuỗi emoji có bộ nối ZWJ. Không thể suy luận rằng `BreakIterator.getCharacterInstance` của mọi JDK/version/provider sẽ xử lý mọi emoji sequence hiện đại theo cùng một quy tắc segmentation. Muốn bảo đảm UX cho các grapheme mới, hãy kiểm tra dữ liệu Unicode và phiên bản JDK mục tiêu, hoặc dùng thư viện hỗ trợ tiêu chuẩn segmentation phù hợp với ứng dụng.

## 8. Code point boundary khác grapheme boundary

Xét chữ `"e\u0301"` gồm `e` và **combining acute accent**:

```text
UTF-16 index:       0   1   2
Text units:          e  ◌́
Code points:         U+0065 U+0301
Một chữ nhìn thấy:   é  (thường)
```

`text.offsetByCodePoints(0, 1)` trả về `1`, vì nó đi qua **một code point**. Nhưng đây nằm giữa base letter và combining mark, không phải biên tốt để di chuyển caret như một ký tự. `BreakIterator.getCharacterInstance` theo quy tắc character break có thể đặt biên ngoài cụm này ở `0` và `2` (với ví dụ đơn giản trên), giúp thao tác chọn chữ không tách dấu khỏi chữ cái.

### Demo Java 17 — `CombiningMarkBoundaryDemo.java`

```java
import java.text.BreakIterator;
import java.util.Locale;

public class CombiningMarkBoundaryDemo {
    public static void main(String[] args) {
        String text = "e\u0301";
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        int afterOneCodePoint = text.offsetByCodePoints(0, 1);
        System.out.println("Length: " + text.length());
        System.out.println("Code point count: "
                + text.codePointCount(0, text.length()));
        System.out.println("After 1 code point: "
                + afterOneCodePoint);
        System.out.println("Break at code point index: "
                + it.isBoundary(afterOneCodePoint));

        System.out.print("Breaks:");
        for (int p = it.first(); p != BreakIterator.DONE;
                p = it.next()) {
            System.out.print(" " + p);
        }
        System.out.println();
    }
}
```

```bash
javac -encoding UTF-8 CombiningMarkBoundaryDemo.java
java CombiningMarkBoundaryDemo
```

Stdout cho cụm chữ+dấu cơ bản trên JDK 17:

```text
Length: 2
Code point count: 2
After 1 code point: 1
Break at code point index: false
Breaks: 0 2
```

**Bài học:** “di chuyển một Unicode code point” và “di chuyển một ký tự người dùng nhìn thấy” có thể là hai thao tác khác nhau. `offsetByCodePoints` chỉ giúp không cắt surrogate pair; nó không áp dụng quy tắc grapheme. `BreakIterator` giúp xác định các biên theo loại ngữ nghĩa mong muốn.

## 9. Đầu/cuối, DONE và offset ngoài phạm vi

Với văn bản đặt bằng `setText(String)` dài `n` đơn vị mã UTF-16, chỉ các offset trong **`0..n`** (bao gồm hai đầu) mới nằm trong dải được phép.

| Trường hợp | Kết quả/hành vi |
| --- | --- |
| `first()` | Biên đầu tiên, thông thường `0` |
| `last()` | Biên cuối cùng, thông thường `n` |
| `following(n)` | `BreakIterator.DONE` |
| `preceding(0)` | `BreakIterator.DONE` |
| `isBoundary(0)` | `true` |
| `isBoundary(n)` | `true` |
| `following(-1)` | `IllegalArgumentException` |
| `preceding(n + 1)` | `IllegalArgumentException` |
| `isBoundary(-1)` | `IllegalArgumentException` |

`BreakIterator.DONE` là sentinel integer bằng **`-1`**, không phải một vị trí hợp lệ trong chuỗi. Không truyền `DONE` vào `substring` hoặc `charAt`; phải kiểm tra trước.

**File `BoundaryEdgesDemo.java`:**

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryEdgesDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("ab");

        System.out.println("First: " + it.first());
        System.out.println("Last: " + it.last());
        System.out.println("After last: "
                + (it.following(2) == BreakIterator.DONE));
        System.out.println("Before first: "
                + (it.preceding(0) == BreakIterator.DONE));
        System.out.println("End boundary: " + it.isBoundary(2));

        try {
            it.following(-1);
            System.out.println("Unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("Out-of-range rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 BoundaryEdgesDemo.java
java BoundaryEdgesDemo
```

Stdout:

```text
First: 0
Last: 2
After last: true
Before first: true
End boundary: true
Out-of-range rejected
```

**Văn bản rỗng:** `setText("")` có thể có biên duy nhất tại `0`; `first()` và `last()` đều bằng `0`, `following(0)`/`preceding(0)` trả `DONE`. Khi thiết kế logic cắt đoạn, phải xử lý không có đoạn nội dung thay vì giả định luôn có ít nhất một segment.

## 10. current, next, previous: đừng làm mất vị trí đang duyệt

`BreakIterator` là một iterator có **trạng thái**. Phương thức `current()` cho biết vị trí biên hiện tại; `next()` đi đến biên tiếp, `previous()` đi về biên trước. Khi gọi `following(offset)` hoặc `preceding(offset)` thành công, current được đặt ở biên trả về.

Ví dụ với `"cat"`, đi từ trái qua phải:

```text
first() -> 0; current() -> 0
next()  -> 1; current() -> 1
next()  -> 2; current() -> 2
next()  -> 3; current() -> 3
next()  -> DONE; current() vẫn là biên cuối
```

Phân biệt `following(offset)` và `next()`:

- `following(offset)` định vị **tương đối với offset truyền vào**, không phụ thuộc việc current trước đó là gì.
- `next()` định vị **tương đối với current position hiện có**.
- `preceding(offset)` định vị **tương đối với offset**, còn `previous()` lùi từ current.
- `isBoundary(offset)` là phép kiểm tra ranh giới; code không nên dựa vào current trước/sau phép kiểm tra nếu không muốn lệ thuộc chi tiết iterator/provider.

Vì vậy, nếu bạn vừa gọi `following(1)` rồi gọi `next()`, `next()` sẽ đi tiếp từ **biên mà following đã tìm**, chứ không quay về biên đầu chuỗi. Để lặp lại toàn bộ từ đầu, hãy dùng `first()`.

### Demo trạng thái — `IteratorStateDemo.java`

```java
import java.text.BreakIterator;
import java.util.Locale;

public class IteratorStateDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText("abc");

        System.out.println("After first: " + it.first());
        System.out.println("After following(0): "
                + it.following(0));
        System.out.println("Current: " + it.current());
        System.out.println("Next: " + it.next());
        System.out.println("Previous: " + it.previous());
        System.out.println("Current again: " + it.current());
    }
}
```

```bash
javac -encoding UTF-8 IteratorStateDemo.java
java IteratorStateDemo
```

Stdout:

```text
After first: 0
After following(0): 1
Current: 1
Next: 2
Previous: 1
Current again: 1
```

Đây là các phương thức định vị **có side effect** lên iterator; tránh chia sẻ cùng một instance đang duyệt giữa các luồng hoặc các thao tác UI không liên quan. `BreakIterator` là mutable; tạo instance cho mỗi tác vụ hoặc quản lý việc tái sử dụng/đồng bộ có chủ đích.

## 11. Cắt nội dung bằng ranh giới đúng

Một cách an toàn để duyệt từng đoạn là `start = first()`, sau đó `end = next()`. Trả về `substring(start, end)`, rồi chuyển `start = end`.

**File `SafeSegmentsDemo.java`:**

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SafeSegmentsDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";
        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        int start = it.first();
        for (int end = it.next();
                end != BreakIterator.DONE;
                start = end, end = it.next()) {
            System.out.println("[" + start + "," + end + "): "
                    + text.substring(start, end));
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeSegmentsDemo.java
java SafeSegmentsDemo
```

Stdout với console UTF-8:

```text
[0,1): A
[1,3): 😀
[3,4): B
```

**Quan trọng:** `substring(begin, end)` dùng khoảng **nửa mở** `[begin,end)`, chính xác cùng kiểu biểu diễn segment bằng hai ranh giới. `end` không phải chỉ số của ký tự cuối, mà là vị trí **ngay sau** segment. Không cộng thêm 1 chỉ vì tư duy “end inclusive”.

Với `getWordInstance`, vòng lặp sẽ trả các **đoạn giữa các boundary** chứ không bảo đảm chỉ các từ chữ cái: có thể có khoảng trắng, dấu câu, số hoặc các đoạn mà sản phẩm không muốn coi là “từ”. Nếu đếm từ, cần phân loại segment theo chính sách (ví dụ kiểm tra có code point là chữ/số). Không dùng số segment == số từ theo ngữ nghĩa.

## 12. Dùng following và preceding để chọn đoạn chứa caret

Giả sử caret ở offset bất kỳ. Ta có thể tìm boundary bên trái và phải, nhưng phải xét **đúng trường hợp caret trùng boundary**.

**Thuật toán chọn đoạn ở bên phải caret** (nếu caret trùng boundary thì chọn đoạn phía phải; nếu caret ở giữa đoạn thì chọn đoạn đang chứa caret):

```text
Input: String text, BreakIterator it, int caret
1. Validate 0 <= caret <= text.length()
2. if caret == text.length(): không có đoạn bên phải
3. right = it.following(caret)
4. if it.isBoundary(caret): left = caret
   else: left = it.preceding(caret)
5. Nếu left / right hợp lệ: substring(left, right)
```

Đoạn trên là **pseudocode**; việc kiểm tra `isBoundary` có thể định vị current theo implementation, nên mọi bước định vị sử dụng **offset rõ ràng**, không sử dụng `next()` trên trạng thái ngầm.

Nếu muốn **đoạn bên trái** khi caret nằm ngay trên boundary, công thức khác:

```text
Nếu caret > 0 và isBoundary(caret):
  left = preceding(caret)
  right = caret
Nếu caret nằm giữa hai biên:
  left = preceding(caret)
  right = following(caret)
```

Chính sách lựa chọn bên trái/bên phải phải được thiết kế từ nhu cầu UI, không do `BreakIterator` tự quyết định. Trên biên giữa hai từ, **một caret không nằm bên trong duy nhất một từ** nếu không nói rõ bên nào được ưu tiên.

### Ví dụ chọn grapheme bên phải caret

Lưu **`SelectAtCaretDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SelectAtCaretDemo {
    private static String selectRight(String text, int caret) {
        if (caret < 0 || caret > text.length()) {
            throw new IndexOutOfBoundsException();
        }
        if (caret == text.length()) {
            return "";
        }

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);

        boolean atBoundary = it.isBoundary(caret);
        int left = atBoundary ? caret : it.preceding(caret);
        int right = it.following(caret);

        if (left == BreakIterator.DONE
                || right == BreakIterator.DONE) {
            return "";
        }
        return text.substring(left, right);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("At 1: "
                + selectRight(text, 1).length());
        System.out.println("At 2: "
                + selectRight(text, 2).length());
        System.out.println("At 3: "
                + selectRight(text, 3));
        System.out.println("At 4 is empty: "
                + selectRight(text, 4).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SelectAtCaretDemo.java
java SelectAtCaretDemo
```

Stdout:

```text
At 1: 2
At 2: 2
At 3: B
At 4 is empty: true
```

Caret `1` nằm ngay trước emoji; `2` nằm giữa surrogate pair (một offset UTF-16 có thể xuất hiện trong dữ liệu/lệnh API dù UI thông thường tránh tạo caret như vậy). Với chính sách “lấy segment chứa offset, ưu tiên segment phía phải nếu đúng boundary”, cả `1` và `2` dẫn đến đoạn emoji dài 2 code units. Vị trí `4` là cuối chuỗi nên không còn đoạn phía phải.

**Trong UI thật**, caret cũng có thể là một vị trí trong model riêng của framework, không mặc nhiên là UTF-16 index của `String` Java. Hãy xác định hệ tọa độ và chuyển đổi đúng trước khi gọi `BreakIterator`.

## 13. getWordInstance, getLineInstance, getSentenceInstance: semantics khác nhau

Một offset như `5` có thể là:

- Biên **character** (giữa hai ký tự).
- Không phải biên **word** nếu ở giữa một từ.
- Không phải điểm ngắt **line** nếu việc ngắt tại đó không hợp lệ.
- Không phải biên **sentence** nếu ở giữa một câu.

Không có một tập boundary chung cho mọi chế độ. Ví dụ gọi `getWordInstance(Locale.forLanguageTag("vi-VN"))` rồi `isBoundary(offset)` kiểm tra **word boundary theo bộ quy tắc của runtime**, không phải “vị trí hợp lệ để cắt surrogate pair”. Trái lại, `getCharacterInstance` nhằm chia các đơn vị ký tự phù hợp, nhưng không có nghĩa là bộ tách từ/ngữ nghĩa của tiếng Việt.

### Đếm đoạn văn bản không đồng nghĩa đếm “từ” theo ngôn ngữ

Ví dụ văn bản `"Hello, world!"` có dấu phẩy, dấu cách, chấm than. Word break iterator cung cấp các vị trí tách giữa những vùng văn bản, gồm cả các vùng không phải từ. Do đó, vòng lặp:

```java
for (int b = it.first(); b != BreakIterator.DONE; b = it.next()) {
    // b là vị trí biên; chưa phải một token "word".
}
```

là **fragment** minh họa, chưa phải chương trình độc lập. Để xác định token thật, dùng `text.substring(prev, next)` rồi phân loại. Quy tắc chữ viết không có khoảng trắng (một số ngôn ngữ Đông Á) và xử lý dấu câu phụ thuộc provider, Unicode/CLDR data hoặc thuật toán của JDK, vì thế không hard-code một danh sách “mọi word offsets” cho các runtime khác nhau.

### Khi nào chọn loại nào?

| Nhu cầu | Iterator | Lưu ý |
| --- | --- | --- |
| Chọn một ký tự/cụm chữ | `getCharacterInstance` | Không cắt đôi surrogate pair/combining sequence trong những trường hợp được hỗ trợ |
| Di chuyển qua vùng từ | `getWordInstance` | Có cả ranh giới dấu câu/khoảng trắng |
| Ngắt dòng cho layout văn bản | `getLineInstance` | Chỉ cho biết cơ hội ngắt; không đo độ rộng pixel |
| Tách câu theo quy tắc chung | `getSentenceInstance` | Không hiểu hoàn toàn ngữ nghĩa, dấu viết tắt hay domain chuyên biệt |

`BreakIterator` hỗ trợ text boundary, **không thay thế** parser ngôn ngữ, model từ vựng, hệ layout rich-text hoặc quy tắc kiểm tra hợp lệ dữ liệu nghiệp vụ.

## 14. StringCharacterIterator và dải offset không bắt đầu từ 0

`BreakIterator.setText(String)` là trường hợp tiện lợi: begin = `0`, end = `text.length()`. Nhưng overload `setText(CharacterIterator)` có thể nhận `StringCharacterIterator` đại diện cho một **đoạn của chuỗi** với `beginIndex` và `endIndex` riêng.

```java
String source = "abcdef";
StringCharacterIterator part =
        new StringCharacterIterator(source, 2, 5, 2);

BreakIterator it =
        BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(part);
```

Đây là **fragment** cần `import java.text.BreakIterator;`, `java.text.StringCharacterIterator;` và `java.util.Locale;`. Theo `StringCharacterIterator` ở đây, vùng được chỉ định có **beginIndex = 2** và **endIndex = 5** (đoạn `"cde"`). Trong tình huống này:

- `it.first()` ứng với boundary đầu của **vùng**, không buộc là 0.
- `it.last()` ứng với boundary cuối của **vùng**, không buộc là `source.length()`.
- Offset hợp lệ của `following/preceding/isBoundary` phải thuộc **dải index của CharacterIterator**, không dùng ngầm `0..partLength`.

Không lấy offset `2` của vùng rồi coi đó là chỉ số tương đối `0` trong `source.substring(...)`. Nếu code API trả offset trên hệ chỉ số của `CharacterIterator`, phải xác định chúng tham chiếu tới chuỗi gốc hoặc phạm vi con nào trước khi cắt.

### Khác biệt giữa “offset của text hiện hành” và “offset của toàn file”

Trong ứng dụng text editor, bộ đệm có thể chỉ đưa một đoạn văn/ô đang sửa cho BreakIterator. Một offset biên trả về khi ấy **không mặc nhiên là tọa độ toàn tài liệu**. Nếu bạn tách chuỗi `whole.substring(start,end)` rồi `setText` trên chuỗi mới, offset sẽ lại bắt đầu từ 0; muốn ánh xạ ngược ra tài liệu, cần cộng `start`. Ngược lại, khi dùng CharacterIterator với startIndex khác 0, offset có thể đã mang tọa độ gốc. **Đừng cộng offset hai lần**.

## 15. Boundary index không phải UTF-8 byte offset

Một chuỗi Unicode có thể được lưu trong file dưới dạng UTF-8. Nhưng BreakIterator làm việc với **các vị trí ký tự của Java text**, không phải byte trong file. Với `"A😀B"`:

```text
Java UTF-16:
  A    = 1 code unit
  😀   = 2 code units
  B    = 1 code unit
  length = 4

UTF-8 bytes:
  A    = 1 byte
  😀   = 4 bytes
  B    = 1 byte
  total = 6 bytes
```

Biên UTF-16 ở vị trí `3` sau emoji **không** tương đương byte offset 3 trong UTF-8: vị trí byte sau emoji là `5`. Không dùng `fileBytes[boundary]` hay cắt mảng byte tại `boundary` khi offset xuất phát từ BreakIterator.

Nếu cần tạo vị trí byte cho giao thức hoặc tệp, phải chuyển đổi một cách rõ ràng, chẳng hạn encode prefix `text.substring(0, boundary)` theo `StandardCharsets.UTF_8` rồi lấy độ dài byte (chỉ khi cần và có kiểm soát chi phí). Với nhiều vị trí, nên xây bảng ánh xạ byte↔UTF-16 bằng decoder/encoder phù hợp thay vì encode prefix liên tục.

**UTF-16 offset khác số code point và khác grapheme index** — không chỉ khác byte offset. Khi tích hợp Java với JavaScript, Python, database và giao diện người dùng, cần ghi rõ hệ chỉ số của mỗi API.

## 16. Những lỗi lập trình phổ biến

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Nghĩ `following(x)` có thể trả `x` | Phương thức dùng quan hệ **>**, không phải **>=** | Muốn kiểm tra x là biên, dùng `isBoundary(x)` |
| Nghĩ `preceding(x)` có thể trả `x` | Phương thức dùng quan hệ **<** | Chọn chính sách đoạn trái/phải tại boundary |
| So `following(last) == last` | Kết quả phải là `DONE` | Kiểm tra sentinel |
| Gọi `substring(DONE, end)` | `DONE = -1`, không là chỉ số hợp lệ | Rẽ nhánh khi `DONE` |
| Dùng `isBoundary(-1)` để hỏi “không hợp lệ?” | Ném exception | Kiểm tra dải offset trước |
| Lấy số code point làm UTF-16 offset | Sai sau ký tự ngoài BMP | Dùng `offsetByCodePoints` khi cần |
| Cắt `substring(i, i + 1)` cho mọi glyph | Có thể tách surrogate pair/combining mark | Dùng biên character BreakIterator |
| Hiểu `String.length()` là số chữ nhìn thấy | Là UTF-16 code units | Phân biệt code points/grapheme |
| Dùng `next()` sau `following` và nghĩ vẫn bắt đầu tại 0 | Iterator đã định vị lại | Gọi `first()` nếu muốn duyệt từ đầu |
| Lấy `isBoundary` làm phép check không side effect | Có thể ảnh hưởng vị trí dùng cho lần duyệt tiếp | Đặt lại current theo nhu cầu |
| Dùng word segments và đếm tất cả là từ | Có dấu câu và khoảng trắng | Phân loại segment |
| Hard-code word boundary cho mọi locale | Thuật toán/data khác nhau | Test trên locale/JDK mục tiêu |
| Truyền offset từ `CharacterIterator` không biết beginIndex | Có thể lệch vùng | Kiểm tra begin/end và mapping |
| Dùng offset UTF-16 làm byte offset UTF-8 | Sai vị trí trong file/API | Convert hệ tọa độ |
| Tái sử dụng instance BreakIterator mutable giữa request | State rò, nguy cơ race | Tạo riêng/clone theo chiến lược phù hợp |
| Tin character BreakIterator hiểu mọi emoji ZWJ mới nhất | Unicode segmentation phụ thuộc phiên bản | Kiểm thử/tận dụng thư viện phù hợp |
| So chuỗi tiếng Việt bằng byte rồi kết luận cùng/khác glyph | Unicode có precomposed/decomposed | Normalization theo policy khi cần |

## 17. Kiểm thử hành vi ở ranh giới

Một bộ test nên có cả các trường hợp **đúng biên** và **bên trong segment**:

1. **ASCII:** `"cat"`, biên `0,1,2,3`; `following(1)=2`, `preceding(2)=1`, `isBoundary(2)=true`.
2. **Đầu/cuối:** `following(length)=DONE`, `preceding(0)=DONE`, `isBoundary(0/length)=true`.
3. **Ngoài dải:** `-1` và `length+1` gây `IllegalArgumentException`.
4. **Surrogate pair:** `"A😀B"`, `length=4`, `codePointCount=3`, `isBoundary(2)=false`, `following(1)=3`.
5. **Combining mark:** `"e\u0301"` có hai code points nhưng là một cụm chữ cơ bản; biên character tránh tách dấu.
6. **Caret đúng biên:** chọn đoạn trái hay phải có chính sách riêng, đặc biệt ở `0` và `length`.
7. **Caret giữa segment:** `preceding`/`following` trả các biên bao quanh, không cắt đôi segment.
8. **State:** kiểm tra `current()` sau `following/preceding`; vòng duyệt mới bắt đầu từ `first()`.
9. **Vùng phụ:** `CharacterIterator` có `beginIndex` khác 0 và mapping chính xác tới chuỗi gốc.
10. **Locale:** `getWordInstance(Locale)` và `getSentenceInstance(Locale)` với đoạn văn các ngôn ngữ khác nhau; chỉ snapshot chính xác khi runtime/provider được khóa.
11. **Text rỗng:** không có segment; không gọi `substring` với `DONE`.
12. **Data changes:** nếu thay văn bản, gọi `setText` trên instance thích hợp; không tái dùng biên cũ làm index cho chuỗi đã chỉnh sửa.

### Bài tập A — Dự đoán ba phương thức

Cho tập boundary giả định `B = {0, 3, 7, 10}`. Tính `following(3)`, `preceding(3)`, `isBoundary(3)`, `following(10)`, `preceding(0)` và `isBoundary(6)`. Giải thích vì sao “đang đúng boundary” không có nghĩa `following`/`preceding` giữ nguyên vị trí.

### Bài tập B — UTF-16 với emoji

Lấy `"X😀Y"`. Dùng `String.length`, `codePointCount`, `offsetByCodePoints` để lập bảng index. Dùng `BreakIterator.getCharacterInstance` in các biên, rồi cắt đúng emoji bằng `substring`. Thử cắt `substring(1, 2)` và mô tả vì sao tạo surrogate đơn lẻ không hợp lệ.

### Bài tập C — Chữ có dấu

Lấy `"e\u0301"` và `"\u00E9"`. So sánh số code point và số đơn vị UTF-16. Tìm character boundaries; nếu sản phẩm cần so sánh nội dung, áp dụng `Normalizer.Form.NFC` riêng với segmentation. Vì sao normalization và BreakIterator phục vụ hai mục đích khác nhau?

### Bài tập D — Chọn từ theo caret

Với chuỗi `"Hello world!"` và `BreakIterator.getWordInstance(Locale.US)`, xây hàm trả segment chứa caret, có chính sách rõ với caret ở boundary. Không tự xem khoảng trắng/dấu câu là từ; chỉ nhận những segment chứa chữ cái. Thử offset `0`, giữa `Hello`, sau dấu cách và `length`.

### Bài tập E — Văn bản phân vùng

Dùng `StringCharacterIterator(source, begin, end, begin)` cho chuỗi có prefix và suffix. Gọi `first/last`, thử `following(begin)`, `preceding(end)`, và ánh xạ kết quả về chuỗi gốc. So sánh với việc gọi `setText(source.substring(begin, end))` để nhận các offset bắt đầu từ 0.

## 18. Tài liệu chính thức

- [Java SE 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html): `following`, `preceding`, `isBoundary`, `DONE`, `first`/`last`, `next`/`previous`.
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `length`, `substring`, `codePointCount`, `offsetByCodePoints` và UTF-16 indexing.
- [Java SE 21 — CharacterIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/CharacterIterator.html): begin/end/current index của văn bản cần duyệt.
- [Java SE 21 — StringCharacterIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/StringCharacterIterator.html): xử lý một dải có beginIndex/endIndex.
- [Unicode Standard Annex #29](https://www.unicode.org/reports/tr29/): Unicode text segmentation, grapheme/word/sentence boundaries.
- [Unicode FAQ — UTF & BOM](https://www.unicode.org/faq/utf_bom.html): phân biệt UTF-16 code units, code points và encoding.

## 19. Ghi nhớ

**`following(offset)` tìm biên kế tiếp có chỉ số **lớn hơn** offset; `preceding(offset)` tìm biên trước đó có chỉ số **nhỏ hơn** offset; `isBoundary(offset)` kiểm tra **ngay chính offset**.** Đúng tại một boundary không làm `following/preceding` trả lại boundary ấy. Ở đầu/cuối dải, các lệnh tìm biên ngoài phạm vi trả `BreakIterator.DONE`, còn offset không hợp lệ ném `IllegalArgumentException`.

Với `setText(String)`, các index của BreakIterator là **UTF-16 code-unit offsets** tương thích `substring`: một emoji ngoài BMP có thể chiếm hai đơn vị mã và một chữ kèm dấu có thể gồm nhiều code points. Hãy dùng đúng loại BreakIterator, xử lý `DONE`, ranh giới đầu/cuối, trạng thái current và các quy tắc locale; **đừng nhầm UTF-16 offsets với byte UTF-8, code point index hoặc “số ký tự nhìn thấy”**.