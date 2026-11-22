# first, next, previous và BreakIterator.DONE trong Java

## 1. Vì sao phải đi qua ranh giới văn bản?

Trong ứng dụng đa ngôn ngữ, không thể luôn cắt văn bản theo khoảng trắng hoặc lấy từng `char` để tìm từ, câu, chỗ xuống dòng hay ký tự người dùng cảm nhận. Có ngôn ngữ không đặt khoảng trắng giữa các từ; có dấu câu, chữ viết ghép, emoji nhiều code point và quy ước phân đoạn thay đổi theo locale.

Java cung cấp `java.text.BreakIterator` để **duyệt các ranh giới** văn bản. Đối tượng này giống một **con trỏ trạng thái** di chuyển qua các vị trí hợp lệ của một kiểu phân đoạn. Những phương thức quan trọng nhất trong bài:

- `first()`: đặt con trỏ tại ranh giới đầu tiên.
- `next()`: đi đến ranh giới sau vị trí hiện tại.
- `previous()`: đi đến ranh giới trước vị trí hiện tại.
- `BreakIterator.DONE`: giá trị đánh dấu **đã hết ranh giới theo chiều đang duyệt**.

Điểm dễ nhầm: `next()` **không trả về một từ**, `previous()` **không trả về một ký tự**, và `DONE` **không phải một chỉ số cắt chuỗi**. Các phương thức trả về **offset nguyên**; bạn phải dùng cặp ranh giới liên tiếp để lấy đoạn văn bản.

Ví dụ chuỗi `"One two!"`, với `BreakIterator.getWordInstance(Locale.US)`, các ranh giới trong dữ liệu Java đã kiểm chứng là:

```text
Văn bản:  O n e   t w o !
Offset:   0 1 2 3 4 5 6 7 8

Ranh giới word: 0 → 3 → 4 → 7 → 8 → DONE(-1)

Các đoạn: [0,3) "One"
           [3,4) " "
           [4,7) "two"
           [7,8) "!"
```

Cả dấu cách và dấu chấm than đều có thể tạo thành **segment riêng** của word iterator. Vì vậy tên `getWordInstance` không có nghĩa `next()` chỉ trả về các từ chứa chữ cái.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Giải thích ý nghĩa chính xác của `first()`, `next()`, `previous()`, `last()`, `current()` và `DONE`.
2. Viết vòng lặp duyệt xuôi và ngược an toàn, không bỏ hoặc nhân đôi đoạn.
3. Phân biệt **ranh giới (boundary)** với **đoạn nằm giữa hai ranh giới (segment)**.
4. Dùng kết quả để `substring` đúng cách và biết đó là **UTF-16 offsets**, không phải ordinal index của code point.
5. Hiểu khác biệt giữa `getCharacterInstance`, `getWordInstance`, `getSentenceInstance`, `getLineInstance`.
6. Xử lý chuỗi rỗng, iterator hết dữ liệu, dấu cách/dấu câu, locale và trạng thái mutable.
7. Biết khi nào phải kiểm tra riêng Unicode grapheme, tokenization, hay dùng thư viện phân tích ngôn ngữ sâu hơn.

## 2. Khởi tạo `BreakIterator` đúng loại và locale

`BreakIterator` là lớp trừu tượng; ứng dụng thông thường lấy instance thông qua các factory:

| Factory | Ranh giới phục vụ mục đích gì? | Không được đồng nhất với |
| --- | --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Ranh giới ký tự ở mức text segmentation | Mỗi `char` Java hay chắc chắn mỗi glyph |
| `BreakIterator.getWordInstance(locale)` | Ranh giới phân đoạn từ và các đoạn xen giữa | Một tokenizer chỉ xuất từ có nghĩa |
| `BreakIterator.getSentenceInstance(locale)` | Ranh giới câu theo quy tắc phân đoạn | Phân tích ngữ pháp câu hoàn hảo |
| `BreakIterator.getLineInstance(locale)` | Cơ hội ngắt dòng phù hợp với quy tắc | Số dòng hiển thị sau khi layout hoặc chỉ ký tự newline |

Các overload không nhận `Locale` dùng locale mặc định có liên quan đến định dạng văn bản trong JVM. Với ứng dụng đa người dùng, nên truyền locale tường minh:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
BreakIterator words = BreakIterator.getWordInstance(locale);
words.setText("Chào bạn!");
```

Đây là **đoạn code nằm trong phương thức**, cần `import java.text.BreakIterator;` và `import java.util.Locale;`.

Một số lớp con thực tế do JDK/provider chọn có thể khác nhau. Không ép kiểu về lớp triển khai cụ thể khi code chỉ cần hợp đồng `BreakIterator`. Dữ liệu phân đoạn cũng có thể thay đổi theo phiên bản JDK, Unicode và locale provider; nếu cần segmentation đặc biệt cho sản phẩm, kiểm thử trên runtime mục tiêu.

### Bước bắt buộc: `setText`

Trước khi duyệt một chuỗi cụ thể, gọi `setText(String)` để đặt nội dung:

```java
BreakIterator iterator = BreakIterator.getWordInstance(Locale.US);
iterator.setText("One two!");
```

`setText` thiết lập nội dung và đặt trạng thái iterator ở vị trí khởi đầu. Tuy vậy nên gọi `first()` rõ ràng ở đầu thuật toán vì điều đó khiến điều kiện khởi tạo của vòng lặp dễ đọc và không phụ thuộc vào con trỏ còn lại từ thao tác trước.

Với overload `setText(CharacterIterator)`, phạm vi chỉ số có thể được giới hạn bởi `getBeginIndex()` / `getEndIndex()` của iterator gốc, nên đừng tổng quát hóa **mọi** `first()` đều trả 0. Với `setText(String)`, ranh giới đầu thường là index 0 và ranh giới cuối là `text.length()`.

## 3. Mô hình trạng thái: con trỏ nằm trên *ranh giới*, không nằm trên ký tự

Mô hình đơn giản:

```text
Boundaries:      b0         b1    b2        b3   b4
                  |          |     |         |    |
Text:            "O n e"    " "   "t w o"    "!"
Index:            0          3     4         7    8

first()  → b0
next()   → b1 → b2 → b3 → b4 → DONE
previous() ← ranh giới trước current()
last()   → b4
```

Trong `"One two!"`, `b0=0`, `b1=3`, `b2=4`, `b3=7`, `b4=8`.

Để lấy đoạn, phải có **hai offset**:

```java
int start = iterator.first();
int end = iterator.next();

if (end != BreakIterator.DONE) {
    String segment = text.substring(start, end);
}
```

Đây là đoạn minh họa với `iterator` đã nhận text và `text` đã được khai báo. `substring(start,end)` nhận khoảng **[start, end)** — có `start` nhưng không gồm `end`. Không nên lấy `substring(0, next())` trong mỗi vòng lặp, vì như vậy sẽ lấy các tiền tố dài dần thay vì từng segment độc lập.

### `first()`

- Dịch con trỏ đến ranh giới đầu.
- Trả vị trí ranh giới đầu.
- Khi dùng `setText(String)`, đó là 0.
- Gọi lại `first()` sẽ **reset** tiến trình duyệt; không thể tiếp tục từ vị trí đang có.

### `next()`

- Tìm ranh giới ngay **sau** vị trí hiện tại, đặt con trỏ tại đó rồi trả offset.
- Nếu đã ở ranh giới cuối, trả `BreakIterator.DONE`.
- Lần trả `DONE` **không có nghĩa `current()` biến thành `-1`**. Trong JDK, con trỏ vẫn ở ranh giới cuối khi `next()` không đi xa hơn.

### `previous()`

- Tìm ranh giới ngay **trước** vị trí hiện tại.
- Nếu đã ở ranh giới đầu, trả `BreakIterator.DONE`.
- Dùng `last()` rồi `previous()` để duyệt ngược một cách tự nhiên.
- Gọi `previous()` sau khi đã duyệt `next()` đến `DONE` có thể đưa về ranh giới áp chót (vì current vẫn ở cuối).

### `BreakIterator.DONE`

`DONE` là sentinel nguyên với giá trị **`-1`** trong Java SE. Nó biểu thị **không có ranh giới kế tiếp hoặc trước đó**, chứ không phải ranh giới thật.

```java
if (end == BreakIterator.DONE) {
    // Đã hết các segment theo chiều duyệt.
}
```

Tuyệt đối không truyền `-1` cho `String.substring(...)` hay dùng làm index vào mảng: sẽ gặp `StringIndexOutOfBoundsException` / lỗi biên tương ứng. So sánh bằng hằng `BreakIterator.DONE` thay vì viết rải rác literal `-1` để biểu đạt ý nghĩa rõ.

## 4. Vòng lặp chuẩn với `first` và `next`

Mẫu an toàn và phổ biến:

```java
for (int start = iterator.first(), end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Xử lý segment [start,end)
}
```

Giải thích từng bước:

1. `start = first()` đặt offset đầu.
2. `end = next()` đặt offset kết thúc của segment thứ nhất.
3. Điều kiện `end != DONE` xác nhận offset dùng để cắt là hợp lệ.
4. Xử lý `text.substring(start,end)`.
5. `start = end` biến ranh giới cuối cũ thành đầu đoạn tiếp theo; `end = next()` tiến thêm một ranh giới.
6. Khi `next()` trả `DONE`, dừng **mà không gọi `substring(start, -1)`**.

### Ví dụ Java 17+ chạy độc lập: duyệt word segments

Tạo file `ForwardBreakIteratorDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class ForwardBreakIteratorDemo {
    public static void main(String[] args) {
        String text = "One two!";
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText(text);

        int start = iterator.first();
        int end;

        while ((end = iterator.next()) != BreakIterator.DONE) {
            System.out.println("[" + start + "," + end + ") = "
                    + "'" + text.substring(start, end) + "'");
            start = end;
        }

        System.out.println("DONE=" + BreakIterator.DONE);
        System.out.println("current=" + iterator.current());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ForwardBreakIteratorDemo.java
java ForwardBreakIteratorDemo
```

Stdout với dữ liệu phân đoạn `Locale.US` đã kiểm chứng:

```text
[0,3) = 'One'
[3,4) = ' '
[4,7) = 'two'
[7,8) = '!'
DONE=-1
current=8
```

Đoạn `" "` và `"!"` vẫn được trả về vì iterator đang xác định **ranh giới**, không lọc bỏ segment không phải từ. Nếu công việc là đếm từ, phải bổ sung một chính sách lọc segment có ký tự từ (hoặc sử dụng thư viện tokenization đúng ngôn ngữ). Đếm số lần gọi `next()` **không** tương đương số từ.

## 5. Vòng lặp chuẩn với `last` và `previous`

Nếu muốn duyệt **các segment theo thứ tự ngược**, không lấy `first()` rồi gọi `previous()`: tại đầu không có ranh giới nào đứng trước, nên lần gọi đầu tiên sẽ trả `DONE`.

Hãy bắt đầu tại **ranh giới cuối**:

```java
int end = iterator.last();
int start;

while ((start = iterator.previous()) != BreakIterator.DONE) {
    String segment = text.substring(start, end);
    // Xử lý đoạn hiện tại từ phải sang trái
    end = start;
}
```

Hai offset vẫn theo quy tắc `start < end` trong chuỗi nguồn, dù thứ tự **duyệt segment** là từ cuối về đầu. `substring(start,end)` không được đảo tham số thành `substring(end,start)`.

### Ví dụ Java 17+: duyệt ngược

File `BackwardBreakIteratorDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BackwardBreakIteratorDemo {
    public static void main(String[] args) {
        String text = "One two!";
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText(text);

        int end = iterator.last();
        int start;

        while ((start = iterator.previous()) != BreakIterator.DONE) {
            System.out.println("[" + start + "," + end + ") = "
                    + "'" + text.substring(start, end) + "'");
            end = start;
        }

        System.out.println("DONE=" + BreakIterator.DONE);
        System.out.println("current=" + iterator.current());
    }
}
```

```bash
javac BackwardBreakIteratorDemo.java
java BackwardBreakIteratorDemo
```

```text
[7,8) = '!'
[4,7) = 'two'
[3,4) = ' '
[0,3) = 'One'
DONE=-1
current=0
```

**Duyệt ngược các đoạn** khác với **đảo từng ký tự trong mỗi đoạn**. Ví dụ này in segment `"two"` nguyên vẹn, không đổi thành `"owt"`. Nếu mục tiêu là đảo chuỗi Unicode theo grapheme, còn cần cân nhắc code points/emoji; `BreakIterator` giúp xác định ranh giới nhưng không tự thực hiện reverse.

## 6. `current()` và điều gì xảy ra tại `DONE`?

`current()` trả vị trí ranh giới **hiện tại** mà iterator đang giữ; khác với giá trị `DONE` là dấu kết thúc một lần di chuyển.

Ví dụ trên `"One two!"`:

| Thao tác | Giá trị trả về | `current()` sau thao tác |
| --- | ---: | ---: |
| `first()` | 0 | 0 |
| `next()` | 3 | 3 |
| `next()` | 4 | 4 |
| `next()` | 7 | 7 |
| `next()` | 8 | 8 |
| `next()` | `DONE=-1` | 8 |
| `previous()` (sau `DONE`) | 7 | 7 |
| `last()` | 8 | 8 |
| `next()` (ở cuối) | `DONE=-1` | 8 |
| `first()` | 0 | 0 |
| `previous()` (ở đầu) | `DONE=-1` | 0 |

Điểm dễ sai là xử lý `DONE` như một vị trí mà con trỏ thật sự bị đặt đến. **Đừng lưu `int index = next()` rồi cho rằng `current() == index` trong mọi trường hợp**, vì khi `next()` trả `DONE`, `current()` vẫn giữ ranh giới cuối.

Tương tự, một vòng lặp có thể gọi `next()` thêm nhiều lần sau `DONE` và vẫn nhận `DONE`. Đây không phải điều kiện để tăng bộ đếm hay tiến thêm ký tự; nên dừng vòng lặp ngay khi thấy sentinel.

### Ví dụ trạng thái cụ thể

Tạo file `BreakIteratorStateDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BreakIteratorStateDemo {
    public static void main(String[] args) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText("One two!");

        System.out.println("first=" + iterator.first());
        System.out.println("next1=" + iterator.next());
        System.out.println("next2=" + iterator.next());
        System.out.println("next3=" + iterator.next());
        System.out.println("next4=" + iterator.next());
        System.out.println("next5=" + iterator.next());
        System.out.println("current=" + iterator.current());
        System.out.println("previous=" + iterator.previous());
        System.out.println("current=" + iterator.current());

        System.out.println("first again=" + iterator.first());
        System.out.println("previous at first=" + iterator.previous());
        System.out.println("current=" + iterator.current());
    }
}
```

```bash
javac BreakIteratorStateDemo.java
java BreakIteratorStateDemo
```

```text
first=0
next1=3
next2=4
next3=7
next4=8
next5=-1
current=8
previous=7
current=7
first again=0
previous at first=-1
current=0
```

## 7. Chuỗi rỗng: chỉ có một vị trí ranh giới

Với `String text = ""`:

- `first()` là 0.
- `last()` cũng là 0.
- `next()` ngay sau `first()` trả `DONE`.
- `previous()` tại vị trí đầu cũng trả `DONE`.
- Không có **segment có độ dài dương** để đưa vào danh sách.

Vì vậy vòng lặp chuẩn `while ((end = next()) != DONE)` tự nhiên chạy 0 lần; không cần tạo riêng một chuỗi rỗng giả làm "từ thứ nhất".

Ví dụ Java 17+:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class EmptyTextDemo {
    public static void main(String[] args) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.US);
        iterator.setText("");

        System.out.println("first=" + iterator.first());
        System.out.println("next=" + iterator.next());
        System.out.println("previous=" + iterator.previous());
        System.out.println("last=" + iterator.last());
    }
}
```

```bash
javac EmptyTextDemo.java
java EmptyTextDemo
```

```text
first=0
next=-1
previous=-1
last=0
```

Kết quả này giúp phân biệt **chuỗi rỗng** và **không có iterator**. `DONE` không báo một lỗi đọc dữ liệu; nó là kết quả kết thúc duyệt bình thường.

## 8. Các phương thức hỗ trợ di chuyển con trỏ

Ngoài ba phương thức chính còn có:

| Phương thức | Ý nghĩa |
| --- | --- |
| `last()` | Đặt con trỏ vào ranh giới cuối của text |
| `current()` | Đọc offset hiện tại, không dịch chuyển |
| `next(int n)` | Đi `n` ranh giới: dương đi tới, âm đi lùi, 0 giữ nguyên |
| `following(int offset)` | Tìm ranh giới **đầu tiên sau** offset được cung cấp |
| `preceding(int offset)` | Tìm ranh giới **cuối cùng trước** offset |
| `isBoundary(int offset)` | Kiểm tra offset có nằm đúng ranh giới không; **có thể thay đổi current** |
| `getText()` | Trả `CharacterIterator` phản ánh nội dung đã đặt |

`following(offset)` khác `next()`: `following` nhảy từ offset được **chỉ định** chứ không đơn thuần dựa vào ranh giới current. `preceding(offset)` tương tự khi tìm ranh giới trước offset.

Các offset do API này nhận và trả là **chỉ số UTF-16 của văn bản** (với `String`). Nếu offset nằm giữa một cặp surrogate, việc chọn ranh giới phụ thuộc thuật toán phân đoạn, không được coi offset đó tương ứng với một code point hoàn chỉnh.

### Ví dụ Java 17+: `next(int)`, `following`, `preceding` và `isBoundary`

File `BreakIteratorNavigationDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BreakIteratorNavigationDemo {
    public static void main(String[] args) {
        BreakIterator it = BreakIterator.getWordInstance(Locale.US);
        it.setText("One two!");

        System.out.println("first=" + it.first());
        System.out.println("next(2)=" + it.next(2));
        System.out.println("next(-1)=" + it.next(-1));
        System.out.println("following(3)=" + it.following(3));
        System.out.println("preceding(4)=" + it.preceding(4));
        System.out.println("isBoundary(5)=" + it.isBoundary(5));
        System.out.println("current=" + it.current());
        System.out.println("isBoundary(7)=" + it.isBoundary(7));
    }
}
```

```bash
javac BreakIteratorNavigationDemo.java
java BreakIteratorNavigationDemo
```

```text
first=0
next(2)=4
next(-1)=3
following(3)=4
preceding(4)=3
isBoundary(5)=false
current=7
isBoundary(7)=true
```

Vì `5` ở giữa từ `two`, `isBoundary(5)` trả `false` nhưng con trỏ được đặt đến ranh giới **sau** nó, tại `7`. Nếu sau đó gọi `next()` mà không xét tác dụng phụ này, bạn có thể **bỏ qua một segment**. Đừng xem `isBoundary` là phép truy vấn luôn không thay đổi trạng thái của iterator.

**Chú ý:** nếu dùng offset ngoài phạm vi hợp lệ của `CharacterIterator`, các phương thức có thể ném `IllegalArgumentException`. `DONE` chỉ là kết quả "không có ranh giới" trong điều kiện tìm kiếm, không thay cho kiểm tra input offset và trạng thái.

## 9. Character, word, sentence, line: cùng API nhưng ranh giới khác nhau

Khi đổi factory, hành vi `first`/`next`/`previous`/`DONE` **không đổi về nguyên lý**, nhưng **những offset được coi là ranh giới** sẽ khác.

Với text `"One two!"`, theo dữ liệu phân đoạn Java US đã kiểm chứng:

| Iterator | Các segment minh họa |
| --- | --- |
| `getCharacterInstance` | `"O"`, `"n"`, `"e"`, `" "`, `"t"`, `"w"`, `"o"`, `"!"` |
| `getWordInstance` | `"One"`, `" "`, `"two"`, `"!"` |
| `getSentenceInstance` | `"One two!"` |
| `getLineInstance` | `"One "`, `"two!"` |

Sự khác nhau của `getLineInstance` dễ nhầm: nó mô tả **vị trí được phép ngắt dòng**, chứ không yêu cầu văn bản chứa ký tự xuống dòng `\n` hoặc bảo đảm có đúng hai dòng khi hiển thị. Layout engine còn cần thông tin chiều rộng, font và chính sách ngắt dòng.

### Ví dụ Java 17+: đối chiếu cả bốn kiểu

Tạo file `BreakTypesDemo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class BreakTypesDemo {
    static List<String> segments(String s, BreakIterator it) {
        it.setText(s);
        List<String> list = new ArrayList<>();
        int start = it.first();
        for (int end = it.next(); end != BreakIterator.DONE;
                start = end, end = it.next()) {
            list.add(s.substring(start, end));
        }
        return list;
    }

    public static void main(String[] args) {
        String text = "One two!";
        System.out.println("character="
                + segments(text,
                    BreakIterator.getCharacterInstance(Locale.US)));
        System.out.println("word="
                + segments(text,
                    BreakIterator.getWordInstance(Locale.US)));
        System.out.println("sentence="
                + segments(text,
                    BreakIterator.getSentenceInstance(Locale.US)));
        System.out.println("line="
                + segments(text,
                    BreakIterator.getLineInstance(Locale.US)));
    }
}
```

```bash
javac BreakTypesDemo.java
java BreakTypesDemo
```

```text
character=[O, n, e,  , t, w, o, !]
word=[One,  , two, !]
sentence=[One two!]
line=[One , two!]
```

Dòng `character`/`word` được in bởi `List.toString()` nên phần tử chỉ chứa một dấu cách xuất hiện như **hai khoảng trắng liên tiếp giữa các dấu phẩy**; đó là định dạng của danh sách và **không có phần tử nào bị mất**. Nếu cần so sánh tự động, in `start`/`end` như `ForwardBreakIteratorDemo` sẽ rõ ràng hơn và ít phụ thuộc vào cách hiển thị khoảng trắng.

Một số ngôn ngữ có phân đoạn từ khác tiếng Anh; không lấy output US trên ASCII làm quy tắc áp dụng toàn cầu.

## 10. Các offset trả về vẫn là UTF-16 index

Điều này đặc biệt quan trọng trong localization. Java `String.length()` trả về số **UTF-16 code units**, không phải số Unicode code points hay grapheme clusters.

Ví dụ:

```text
A🌍B
```

Có ba Unicode code points, nhưng `String.length() == 4` vì `🌍` U+1F30D gồm hai UTF-16 code units. Với `BreakIterator.getCharacterInstance(Locale.US)` trên một JDK phân đoạn cặp surrogate hợp lệ như một ký tự, các boundary trong ví dụ là:

```text
0 → 1 → 3 → 4
```

Không phải `0 → 1 → 2 → 3`. Nếu `next()` trả offset `3`, nó có thể chỉ ra vị trí sau toàn bộ emoji, tương ứng `substring(1,3)`.

### Ví dụ Java 17+ không phụ thuộc font emoji của console

File `BreakIteratorUtf16Demo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class BreakIteratorUtf16Demo {
    public static void main(String[] args) {
        String globe = new String(Character.toChars(0x1F30D));
        String text = "A" + globe + "B";

        BreakIterator it =
                BreakIterator.getCharacterInstance(Locale.US);
        it.setText(text);

        List<Integer> offsets = new ArrayList<>();
        for (int at = it.first(); at != BreakIterator.DONE;
                at = it.next()) {
            offsets.add(at);
        }

        System.out.println("utf16 length=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("boundaries=" + offsets);
    }
}
```

```bash
javac BreakIteratorUtf16Demo.java
java BreakIteratorUtf16Demo
```

```text
utf16 length=4
codePoints=3
boundaries=[0, 1, 3, 4]
```

Vì `String` lấy chỉ số UTF-16, kết quả `BreakIterator` được dùng trực tiếp với `substring(start,end)`. Không chuyển nhầm offset này thành "thứ tự code point" rồi đưa vào `substring` lần nữa.

### Cảnh báo với emoji phức tạp và JDK 17

Không phải mọi *grapheme cluster* chỉ có một code point. Ví dụ emoji kết hợp ZWJ, skin tone modifier hoặc cặp regional indicator có thể gồm nhiều code points. **JDK 17 `BreakIterator.getCharacterInstance` không được bảo đảm xử lý đầy đủ mọi extended grapheme cluster hiện đại**; triển khai mặc định được nâng cấp theo UAX #29 từ JDK 20 (JDK-8291660). Khi cần giới hạn ký tự hiển thị chính xác trên Java 17, có thể dùng regex `Pattern.compile("\\X")` (hỗ trợ extended grapheme cluster) hoặc thư viện Unicode phù hợp, và luôn kiểm thử với phiên bản Unicode của sản phẩm.

**Không sử dụng `BreakIterator.getCharacterInstance` như chứng minh rằng mỗi segment là một glyph có chiều rộng cố định**. Grapheme boundaries và bố trí font/pixel là các bài toán khác nhau.

## 11. Word boundaries không có nghĩa chỉ chứa từ

Ví dụ `"One two!"` cho word iterator tạo cả:

```text
"One"    — chữ cái
" "      — khoảng trắng
"two"    — chữ cái
"!"      — dấu câu
```

Nếu chỉ muốn đếm từ, một hướng có thể là **lọc segment** bằng quy tắc nghiệp vụ:

```java
static boolean hasLetterOrDigit(String segment) {
    return segment.codePoints()
            .anyMatch(Character::isLetterOrDigit);
}
```

Đây là **phương thức minh họa**, không phải định nghĩa từ theo mọi ngôn ngữ. Từ ngôn ngữ học và sản phẩm có thể chứa dấu nối, số, hashtag, apostrophe, script phức tạp, emoji hoặc không có khoảng trắng. Với tiếng Trung, Nhật, Thái hoặc các hệ chữ khác, segmentation có thể phụ thuộc locale data và dictionary; thuật toán đếm từ cho analytics/search thường cần tokenizer chuyên dụng.

Một vài trường hợp cần phân biệt:

- **Phân đoạn để chọn từ bằng con trỏ:** word boundary engine thích hợp.
- **Tách token để đánh chỉ mục tìm kiếm:** analyzer/tokenizer có thêm normalization/casefold và các rule domain.
- **Đếm từ theo quy chuẩn biên tập:** cần định nghĩa thế nào là "một từ".
- **Chia câu:** dùng sentence iterator, không đếm số dấu chấm.

Không gán sai nhiệm vụ cho `BreakIterator` chỉ vì nó có phương thức `getWordInstance`.

## 12. Duyệt ngược và vấn đề trạng thái mutable

`BreakIterator` là một **stateful iterator**. `first()`, `last()`, `next()`, `previous()` và cả một số phương thức kiểm tra ranh giới đều có thể thay đổi `current()`. Hệ quả:

- Không dùng cùng một instance để **đồng thời** duyệt xuôi và ngược nếu các thao tác xen kẽ không được quản lý.
- Không dùng chung một iterator mutable giữa các request/threads mà không có cơ chế tách state.
- Không gọi `setText(...)` giữa một vòng lặp đang xử lý mà vẫn dùng `start/end` của text cũ.
- Nếu cần duyệt lại từ đầu, gọi `first()` và tính toán lại.
- Nếu cần kiểm tra vị trí bất kỳ bằng `following/preceding` trong lúc đang duyệt, cân nhắc tạo iterator khác hoặc lưu offset và đặt lại đúng trạng thái.
- `BreakIterator` hỗ trợ `clone()`; nhưng clone cũng cần dùng trên text/trạng thái đã được kiểm soát và không nên lạm dụng như một phương pháp giữ shared mutable iterator đa luồng.

### Đừng quên bảo toàn text của ranh giới

Đoạn lấy từ `text.substring(start,end)` chỉ đúng nếu `start/end` được tạo từ **đúng text đang được iterator phân đoạn**. Nếu một bước normalization, chuyển chữ thường, xóa dấu hay đổi encoding làm thay đổi độ dài, offset thuộc text đã biến đổi **không nhất thiết** dùng được trên raw text.

Ví dụ `"e\u0301"` là hai code units, trong khi dạng NFC `"\u00E9"` chỉ có một. Nếu phân đoạn text đã normalize rồi dùng offset để cắt/đánh dấu raw text, có thể sai vị trí. Đây là vấn đề thường gặp khi highlight kết quả tìm kiếm. Cần giữ mapping offsets hoặc phân đoạn và thao tác trên cùng một biểu diễn.

## 13. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `next()` trả một từ | Nó trả **chỉ số ranh giới** | Dùng `substring(start,end)` |
| Dùng `substring(0, end)` ở mọi lượt | Lấy tiền tố dài dần, không phải segment | Cập nhật `start=end` |
| Truyền `DONE=-1` vào `substring` | Lỗi index âm | Kiểm tra `end != DONE` trước khi cắt |
| Duyệt ngược từ `first()` | `previous()` lập tức trả DONE | Bắt đầu từ `last()` |
| Đảo tham số `substring(end,start)` khi duyệt ngược | `beginIndex > endIndex` | Luôn dùng `substring(start,end)` với start nhỏ hơn end |
| Nghĩ `current() == DONE` sau `next() == DONE` | Current vẫn ở ranh giới cuối | Kiểm tra return value của `next` |
| Nghĩ word iterator bỏ space và dấu câu | Nó cũng trả ranh giới các đoạn này | Lọc theo chính sách token |
| Gọi `isBoundary(offset)` như một phép truy vấn hoàn toàn thuần | Có thể đổi vị trí current | Cẩn thận trước `next/previous` |
| Dùng `String.length()` như số ký tự hiển thị | UTF-16 code units khác grapheme | Chọn đơn vị đúng |
| Dùng boundary từ string đã normalize để cắt raw string | Offset có thể thay đổi | Dùng đúng string/mapping |
| Cho rằng line iterator trả các dòng do `\n` tạo | Nó biểu diễn line-break opportunities | Phân biệt layout dòng và ký tự xuống dòng |
| Đếm `next()` để đếm từ | Không phân biệt punctuation/whitespace | Tokenization chuyên biệt |
| Dùng một iterator giữa nhiều threads | Mutable state có thể bị xáo trộn | Instance theo thao tác |
| Giả định mọi JDK/provider phân đoạn emoji ZWJ như nhau | Unicode implementation thay đổi | Kiểm thử JDK17/20+ và policy |
| Dùng `Locale.getDefault()` cho mọi user | Không phản ánh user locale | Truyền locale tường minh |

## 14. Checklist thiết kế thuật toán ranh giới

Trước khi triển khai, trả lời:

1. **Đang tìm ranh giới của cái gì?** Character, word, sentence hay line?
2. **Locale nguồn là gì?** Ngôn ngữ hiển thị có thể khác JVM default.
3. **Text là bản gốc hay đã normalize?** Offset trả về gắn với bản nào?
4. **Đơn vị index là gì?** `BreakIterator` dùng UTF-16 offsets cho `String`.
5. **Có dùng `first()`/`last()` đúng chiều?** Đừng gọi `previous()` ở đầu hoặc `next()` ở cuối rồi coi `DONE` là offset.
6. **Mọi vòng lặp có kiểm tra `DONE` trước khi cắt không?**
7. **Có lọc segment theo nghiệp vụ không?** Space/punctuation không tự biến mất.
8. **Text rỗng và text chỉ có dấu cách thì sao?** Không được tạo từ giả.
9. **Có dấu kết hợp, surrogate, ZWJ, emoji không?** Segmentation và glyph width khác nhau.
10. **Có dùng chung iterator mutable giữa threads không?** Tạo mới hoặc tách ownership.
11. **Có test unicode và nhiều locale theo phiên bản JDK không?** Đừng chỉ kiểm thử ASCII.
12. **Có cần bảo toàn offset để highlight UI không?** Phải tương thích với raw text/rendered text.
13. **Có bị lẫn line breaking với tokenization hoặc sentence segmentation không?**
14. **Có cần tính toán lại boundary sau khi text thay đổi không?** Có, vì các offset cũ có thể vô hiệu.

## 15. Câu hỏi tự kiểm tra

1. **`first()` trả về điều gì?** Ranh giới đầu và đặt current về đó.
2. **`next()` trả về chuỗi từ hay vị trí?** Trả **UTF-16 boundary offset**, không trả chuỗi.
3. **`BreakIterator.DONE` có giá trị bao nhiêu?** `-1` trong Java SE, là sentinel không phải offset.
4. **Với `"One two!"` word iterator, chuỗi ranh giới nào nhận được?** `0,3,4,7,8` rồi `DONE`.
5. **Vì sao có segment `" "` và `"!"`?** Vì phân đoạn word gồm cả khoảng trắng/dấu câu; không tự lọc từ.
6. **Viết điều kiện dừng vòng lặp xuôi như thế nào?** `while ((end = iterator.next()) != BreakIterator.DONE)`.
7. **Muốn duyệt các đoạn ngược, khởi tạo ra sao?** `end = iterator.last()`, rồi gọi `previous()` để lấy `start`.
8. **Tại sao `previous()` ngay sau `first()` trả `DONE`?** Không có ranh giới nào đứng trước đầu text.
9. **`current()` sẽ là gì sau khi `next()` ở cuối trả DONE?** Vẫn giữ ranh giới cuối, không phải -1.
10. **`last()` với text rỗng trả gì?** 0 nếu text được đặt bằng `setText("")`.
11. **`following(3)` có chọn offset 3 nếu 3 là boundary không?** Không; nó tìm boundary *sau* 3.
12. **`isBoundary(5)` có thể ảnh hưởng đến `next()` tiếp theo không?** Có, vì nó có thể đặt current ở boundary phía sau offset.
13. **`BreakIterator` dùng code point offsets hay UTF-16?** UTF-16 offsets với `String`.
14. **Trong `"A🌍B"`, ranh giới character đi qua offset nào?** `0,1,3,4` trên JDK đã kiểm chứng.
15. **Có thể dựa vào `getWordInstance` để đếm từ tiếng Việt/Thái/Trung chính xác tuyệt đối không?** Không; cần định nghĩa từ và kiểm thử segmentation theo ngôn ngữ.
16. **`getLineInstance` phân tích gì?** Cơ hội ngắt dòng, không phải số dòng UI hay chỉ dấu newline.
17. **Vì sao không lấy offset của text đã normalize để cắt text gốc?** Vì normalization có thể thay đổi độ dài, khiến offset không tương ứng.
18. **Trong server đa người dùng, iterator nên được quản lý thế nào?** Instance riêng cho thao tác/request hoặc ownership rõ; tránh share mutable state.

## Tài liệu tham khảo

- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): `first`, `last`, `next`, `previous`, `current`, `DONE` và các factory phân đoạn.
- [Java SE 17 — CharacterIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CharacterIterator.html): phạm vi `beginIndex/endIndex` và các chỉ số văn bản.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `substring` và chỉ số UTF-16.
- [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/): định nghĩa ranh giới grapheme, word và sentence.
- [Unicode Standard Annex #14 — Line Breaking](https://www.unicode.org/reports/tr14/): các quy tắc line break opportunities.
- [OpenJDK JDK-8291660 — Support grapheme clusters in BreakIterator](https://bugs.openjdk.org/browse/JDK-8291660): thay đổi triển khai JDK 20 dành cho extended grapheme clusters.
