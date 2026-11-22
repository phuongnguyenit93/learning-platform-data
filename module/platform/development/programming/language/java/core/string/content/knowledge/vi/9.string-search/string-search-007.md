# Chuỗi tìm rỗng và các trường hợp ở biên khi tìm kiếm `String` trong Java

Khi tìm một chuỗi con bằng `String.indexOf()`, `lastIndexOf()`, `contains()`, `startsWith()` hay `endsWith()`, rất dễ bỏ qua trường hợp **chuỗi cần tìm là `""` (chuỗi rỗng)**. Tuy nhiên, Java coi đây là **đầu vào hợp lệ**, và kết quả có quy tắc cụ thể. Các chỉ số ở biên như `0`, `length()`, chỉ số âm hoặc lớn hơn độ dài cũng có thể tạo kết quả khác với suy đoán ban đầu.

Bài học này tập trung vào ba câu hỏi:

1. Vì sao tìm kiếm `""` vẫn có kết quả dù nó không chứa ký tự nào?
2. Các API tìm kiếm xử lý **chuỗi rỗng, chuỗi nguồn rỗng và chỉ số `fromIndex` ngoài phạm vi** như thế nào?
3. Làm sao viết mã an toàn khi chuỗi cần tìm đến từ người dùng hoặc khi lặp qua nhiều lần xuất hiện?

Các ví dụ áp dụng cho **Java 17+** và dựa trên hợp đồng của `java.lang.String`.

## 1. Phân biệt chuỗi nguồn, chuỗi cần tìm và vị trí tìm kiếm

Trong biểu thức:

```java
int position = text.indexOf(keyword);
```

- `text` là **chuỗi nguồn** (*haystack*).
- `keyword` là **chuỗi cần tìm** (*needle*).
- `position` là chỉ số bắt đầu của lần xuất hiện đầu tiên hoặc `-1` nếu không tìm thấy.

Chỉ số `String` trong Java bắt đầu từ `0`, dùng **đơn vị mã UTF-16**, và vị trí kết thúc chuỗi (ngay sau đơn vị mã cuối) là `text.length()`.

Ví dụ chuỗi `"Java"` có độ dài `4`:

```text
       J   a   v   a
Index  0   1   2   3
Vị trí có thể chèn chuỗi rỗng:
       0   1   2   3   4
```

Một cách hiểu hữu ích: **chuỗi rỗng phù hợp tại một vị trí ranh giới, không cần chiếm ký tự nào**. Vì thế, không nên tự động diễn giải kết quả của tìm kiếm `""` là “không tìm thấy”.

Hãy phân biệt rõ ba giá trị:

- `""`: một đối tượng `String` hợp lệ có `length() == 0`.
- `" "`: chuỗi chứa một dấu cách, có `length() == 1`. Tìm dấu cách khác hoàn toàn tìm chuỗi rỗng.
- `null`: không tham chiếu tới đối tượng `String`; không phải chuỗi có độ dài 0.

## 2. Kết quả cơ bản khi chuỗi cần tìm là `""`

Xét:

```java
String text = "Java";
System.out.println(text.indexOf(""));
System.out.println(text.lastIndexOf(""));
System.out.println(text.contains(""));
System.out.println(text.startsWith(""));
System.out.println(text.endsWith(""));
```

Các dòng sẽ in:

```text
0
4
true
true
true
```

Giải thích theo từng API:

| Lời gọi với `text = "Java"` | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `text.indexOf("")` | `0` | Vị trí khớp rỗng đầu tiên là ngay trước chữ `J`. |
| `text.lastIndexOf("")` | `4` | Vị trí khớp rỗng cuối cùng là ngay sau chữ `a` cuối. |
| `text.contains("")` | `true` | Chuỗi rỗng được coi là chuỗi con của mọi `String`. |
| `text.startsWith("")` | `true` | Mọi chuỗi đều có tiền tố rỗng. |
| `text.endsWith("")` | `true` | Mọi chuỗi đều có hậu tố rỗng. |

Đây là **hành vi theo hợp đồng API**, không phải lỗi hoặc sự trùng hợp ngẫu nhiên từ một phiên bản JVM. Đặc biệt, `indexOf("")` trả `0` và `lastIndexOf("")` trả `length()`, không trả `-1`.

Ngược lại, khi tìm một **chuỗi không rỗng** mà nguồn không chứa nó, kết quả `indexOf()` hoặc `lastIndexOf()` là `-1`:

```java
"Java".indexOf("Python")      // -1
"Java".lastIndexOf("Python")  // -1
"Java".contains("Python")     // false
```

Các dòng vừa rồi là biểu thức minh họa trong một phương thức, không phải tệp Java độc lập.

## 3. Nếu chính chuỗi nguồn cũng rỗng thì sao?

Cho `String empty = "";`. Câu trả lời vẫn tuân theo cùng quy tắc:

```java
String empty = "";

System.out.println(empty.length());        // 0
System.out.println(empty.indexOf(""));     // 0
System.out.println(empty.lastIndexOf("")); // 0
System.out.println(empty.contains(""));    // true
System.out.println(empty.startsWith(""));  // true
System.out.println(empty.endsWith(""));    // true
System.out.println(empty.indexOf("a"));    // -1
System.out.println(empty.contains("a"));   // false
```

Chuỗi nguồn rỗng có **một vị trí biên duy nhất**, tức vị trí `0`, nên tìm `""` thành công tại đó. Nhưng nó **không chứa bất kỳ chuỗi con không rỗng nào**.

Các trường hợp nên nhớ:

| Chuỗi nguồn | Chuỗi tìm | `indexOf` | `lastIndexOf` | `contains` |
| --- | --- | ---: | ---: | --- |
| `""` | `""` | 0 | 0 | `true` |
| `""` | `"a"` | -1 | -1 | `false` |
| `"abc"` | `""` | 0 | 3 | `true` |
| `"abc"` | `"bc"` | 1 | 1 | `true` |
| `"abc"` | `"x"` | -1 | -1 | `false` |

Không dùng `text.contains("")` làm điều kiện xác nhận `text` **không rỗng**. Cả `"abc".contains("")` lẫn `"".contains("")` đều là `true`. Để kiểm tra nguồn rỗng, dùng `text.isEmpty()` sau khi bảo đảm tham chiếu khác `null`.

## 4. `indexOf("", fromIndex)`: vị trí tìm rỗng theo chiều tiến

Phương thức `indexOf(String str, int fromIndex)` tìm lần xuất hiện đầu tiên của `str` bắt đầu từ chỉ số `fromIndex`. Với `str = ""`, công thức kết quả rất cụ thể:

```text
indexOf("", fromIndex)
    = min(max(fromIndex, 0), text.length())
```

Nói cách khác, Java **giới hạn chỉ số về khoảng từ 0 đến `length()`** khi chuỗi cần tìm rỗng.

Ví dụ `text = "Java"` có `length() == 4`:

| `fromIndex` | `text.indexOf("", fromIndex)` | Giải thích |
| ---: | ---: | --- |
| `-3` | `0` | Chỉ số âm được quy về vị trí đầu. |
| `0` | `0` | Khớp rỗng ngay đầu chuỗi. |
| `2` | `2` | Khớp rỗng tại ranh giới trước đơn vị mã thứ ba. |
| `4` | `4` | Cho phép vị trí ngay sau ký tự cuối. |
| `9` | `4` | Vượt quá độ dài, kết quả được giới hạn tại `length()`. |

**Điểm dễ sai:** nếu chuỗi cần tìm **không rỗng**, truyền `fromIndex` lớn hơn hoặc bằng `length()` thường sẽ không còn đủ vị trí để khớp và trả `-1`. Với chuỗi cần tìm rỗng, ngay cả `fromIndex` rất lớn vẫn trả `length()`:

```java
String text = "Java";
System.out.println(text.indexOf("a", 99)); // -1
System.out.println(text.indexOf("", 99));  // 4
```

Không giả định rằng “`fromIndex` vượt biên thì mọi phép tìm kiếm đều trả `-1`”.

## 5. `lastIndexOf("", fromIndex)`: tìm theo chiều ngược

`lastIndexOf(String str, int fromIndex)` tìm lần xuất hiện cuối cùng có vị trí bắt đầu **không lớn hơn `fromIndex`**. Với `str = ""`, quy tắc khác `indexOf` ở phía chỉ số âm:

```text
Nếu fromIndex < 0:
    lastIndexOf("", fromIndex) = -1
Ngược lại:
    lastIndexOf("", fromIndex) = min(fromIndex, text.length())
```

Cho `text = "Java"`:

| `fromIndex` | `text.lastIndexOf("", fromIndex)` | Giải thích |
| ---: | ---: | --- |
| `-3` | `-1` | Không có vị trí bắt đầu hợp lệ ở bên trái chỉ số âm. |
| `0` | `0` | Khớp rỗng đầu tiên cũng là vị trí cuối cho phép. |
| `2` | `2` | Khớp rỗng gần nhất từ phía trái tại vị trí 2. |
| `4` | `4` | Khớp rỗng tại điểm kết thúc chuỗi. |
| `9` | `4` | Chỉ số lớn hơn độ dài được giới hạn ở cuối chuỗi. |

Điểm đối chiếu quan trọng:

```java
String text = "Java";
System.out.println(text.indexOf("", -1));     // 0
System.out.println(text.lastIndexOf("", -1)); // -1
```

Cả hai API đều hiểu `fromIndex` theo hướng tìm kiếm của mình. Với chỉ số âm, tìm xuôi vẫn bắt đầu từ đầu chuỗi; tìm ngược thì không còn điểm bắt đầu hợp lệ, trả `-1`.

**Không nhầm `lastIndexOf("")` với `lastIndexOf("", 0)`**:

```java
"Java".lastIndexOf("")     // 4
"Java".lastIndexOf("", 0)  // 0
```

Bản không truyền `fromIndex` xét vị trí khớp rỗng cuối cùng của toàn bộ chuỗi, còn bản truyền `0` chỉ xét đến vị trí `0`.

## 6. Tiền tố/hậu tố rỗng và kiểm tra chỉ số `startsWith("", offset)`

`startsWith(String prefix)` và `endsWith(String suffix)` trả `true` khi đối số rỗng, kể cả khi chuỗi nguồn cũng rỗng:

```java
"Java".startsWith("") // true
"Java".endsWith("")   // true
"".startsWith("")     // true
"".endsWith("")       // true
```

Với phương thức có `offset`, điều kiện chính xác hơn. `text.startsWith("", offset)` trả `true` **khi và chỉ khi** `0 <= offset <= text.length()`:

| `text = "Java"`, `length() = 4` | Kết quả |
| --- | --- |
| `text.startsWith("", -1)` | `false` |
| `text.startsWith("", 0)` | `true` |
| `text.startsWith("", 2)` | `true` |
| `text.startsWith("", 4)` | `true` |
| `text.startsWith("", 5)` | `false` |

So sánh hai lời gọi khi `offset` lớn hơn độ dài:

```java
String text = "Java";
System.out.println(text.indexOf("", 5));     // 4
System.out.println(text.startsWith("", 5));   // false
```

`indexOf` chuẩn hóa chỉ số đối với chuỗi cần tìm rỗng; `startsWith` với chỉ số `offset` không hợp lệ trả `false`. Vì vậy, **không suy diễn quy tắc chỉ số từ API này sang API khác**.

## 7. Chương trình Java 17+: bảng kết quả biên có thể chạy lại

Tạo tệp `EmptySearchBoundaryDemo.java`:

```java
public class EmptySearchBoundaryDemo {
    public static void main(String[] args) {
        String text = "Java";
        int[] positions = {-3, 0, 2, 4, 9};

        System.out.println("length = " + text.length());
        System.out.println("indexOfEmpty = " + text.indexOf(""));
        System.out.println("lastIndexOfEmpty = " + text.lastIndexOf(""));
        System.out.println("containsEmpty = " + text.contains(""));
        System.out.println("startsWithEmpty = " + text.startsWith(""));
        System.out.println("endsWithEmpty = " + text.endsWith(""));

        for (int from : positions) {
            System.out.println(
                "from=" + from
                + " indexOf=" + text.indexOf("", from)
                + " lastIndexOf=" + text.lastIndexOf("", from)
                + " startsWith=" + text.startsWith("", from)
            );
        }

        String empty = "";
        System.out.println("empty.indexOfEmpty = " + empty.indexOf(""));
        System.out.println(
            "empty.lastIndexOfEmpty = " + empty.lastIndexOf(""));
        System.out.println("empty.containsEmpty = " + empty.contains(""));
        System.out.println("empty.indexOfA = " + empty.indexOf("a"));
    }
}
```

Biên dịch và chạy:

```bash
javac EmptySearchBoundaryDemo.java
java EmptySearchBoundaryDemo
```

Kết quả:

```text
length = 4
indexOfEmpty = 0
lastIndexOfEmpty = 4
containsEmpty = true
startsWithEmpty = true
endsWithEmpty = true
from=-3 indexOf=0 lastIndexOf=-1 startsWith=false
from=0 indexOf=0 lastIndexOf=0 startsWith=true
from=2 indexOf=2 lastIndexOf=2 startsWith=true
from=4 indexOf=4 lastIndexOf=4 startsWith=true
from=9 indexOf=4 lastIndexOf=4 startsWith=false
empty.indexOfEmpty = 0
empty.lastIndexOfEmpty = 0
empty.containsEmpty = true
empty.indexOfA = -1
```

Ba khác biệt nên tự giải thích lại:

1. `indexOf("", -3) == 0` nhưng `lastIndexOf("", -3) == -1`.
2. `indexOf("", 9) == 4` nhưng `startsWith("", 9) == false`.
3. Tìm `""` trong nguồn `""` vẫn thành công tại `0`; tìm `"a"` trong nguồn rỗng không thành công.

## 8. Chỉ số biên khi chuỗi tìm **không rỗng**

Không nên chỉ ghi nhớ trường hợp chuỗi rỗng rồi áp dụng sai cho mọi chuỗi tìm. Với `text = "ababa"`, độ dài `5`:

```java
String text = "ababa";

System.out.println(text.indexOf("aba"));       // 0
System.out.println(text.indexOf("aba", 1));    // 2
System.out.println(text.indexOf("aba", 3));    // -1

System.out.println(text.lastIndexOf("aba"));   // 2
System.out.println(text.lastIndexOf("aba", 1)); // 0

System.out.println(text.indexOf("ba", -10));    // 1
System.out.println(text.indexOf("ba", 5));      // -1
System.out.println(text.lastIndexOf("ba", 99)); // 3
System.out.println(text.lastIndexOf("ba", -1)); // -1
```

Đây là fragment Java đặt trong một phương thức. Những kết quả này cho thấy:

- `indexOf("aba", 1)` tìm từ chỉ số `1` về cuối, nên bỏ lần khớp ở `0` và gặp lần khớp ở `2`.
- `lastIndexOf("aba", 1)` chỉ chấp nhận điểm bắt đầu không lớn hơn `1`, nên tìm ra lần ở `0`.
- Với chuỗi tìm không rỗng, `indexOf` từ `length()` không còn vị trí khớp.
- Với `lastIndexOf`, chỉ số lớn hơn độ dài có thể vẫn tìm thấy chuỗi ở phía bên trái, vì đây là phép tìm **ngược**.
- Hai lần xuất hiện có thể **chồng lấn**, như `"aba"` ở chỉ số `0` và `2`.

Mô hình tổng quát: `indexOf` tìm lần đầu có vị trí bắt đầu **từ `fromIndex` trở về sau** (chỉ số âm được coi như `0`); `lastIndexOf` tìm lần cuối có vị trí bắt đầu **không vượt quá `fromIndex`**. Kết quả `-1` nghĩa là không có lần xuất hiện thỏa điều kiện.

## 9. Cẩn thận với `null`: không đồng nghĩa `""`

Chuỗi tìm rỗng là **giá trị hợp lệ**; `null` thì **không phải một chuỗi**.

```java
String text = "Java";
String keyword = null;

// text.indexOf(keyword);  // Ném NullPointerException.
// text.contains(keyword); // Ném NullPointerException.
// text.startsWith(keyword); // Ném NullPointerException.
```

Ba dòng gọi API trên được chú thích để ví dụ không ném ngoại lệ khi biên dịch/chạy. Tương tự, nếu chính biến `text` là `null` thì `text.indexOf(...)` cũng ném `NullPointerException` vì không có đối tượng nhận lời gọi.

Nếu keyword đến từ UI, API hoặc cấu hình, hãy **định nghĩa rõ chính sách**. Ví dụ, tùy chức năng, bạn có thể:

- Từ chối `null` và `""` như từ khóa không hợp lệ.
- Coi `""` là điều kiện tìm kiếm không lọc (trả mọi bản ghi), nhưng kiểm tra tường minh thay vì vô tình dựa vào `contains("")`.
- Cho phép `""` để mô hình hóa vị trí rỗng trong một API chuyên xử lý văn bản.

Các lựa chọn này khác nhau về nghiệp vụ; Java không tự biết người dùng muốn cách nào.

## 10. Lỗi nguy hiểm: vòng lặp tìm mọi lần xuất hiện bị kẹt khi keyword rỗng

Khi duyệt các lần xuất hiện của một chuỗi con, lập trình viên thường tăng vị trí tìm tiếp dựa theo `keyword.length()`:

```java
// Mã minh họa cách làm SAI nếu keyword là "":
int from = 0;
int hit;
while ((hit = text.indexOf(keyword, from)) >= 0) {
    System.out.println(hit);
    from = hit + keyword.length();
}
```

Nếu `keyword.equals("")`, thì `keyword.length() == 0`. Ở lần đầu, `hit` có thể là `0`, và `from` vẫn bằng `0`. Lần sau lại tìm được đúng vị trí đó: **vòng lặp không tiến lên**.

Một cách phòng tránh là yêu cầu keyword phải không rỗng trước khi tìm. Nếu chức năng cần liệt kê tất cả **điểm ranh giới rỗng**, cần viết một nhánh riêng có số bước hữu hạn (từ `0` đến `text.length()`); không dùng mã lặp dành cho chuỗi con không rỗng mà không sửa quy tắc tăng chỉ số.

### Ví dụ Java 17+ có kiểm tra đầu vào và hỗ trợ các lần khớp chồng lấn

Tạo tệp `SafeSubstringSearch.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeSubstringSearch {
    static List<Integer> findAll(String text, String keyword) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(keyword, "keyword");

        if (keyword.isEmpty()) {
            throw new IllegalArgumentException("keyword must not be empty");
        }

        List<Integer> positions = new ArrayList<>();
        int from = 0;

        while (from < text.length()) {
            int found = text.indexOf(keyword, from);
            if (found == -1) {
                break;
            }
            positions.add(found);
            from = found + 1; // Cho phép lần khớp tiếp theo chồng lấn.
        }

        return positions;
    }

    public static void main(String[] args) {
        System.out.println(findAll("ababa", "aba"));
        System.out.println(findAll("aaaa", "aa"));
        System.out.println(findAll("", "a"));
        System.out.println(findAll("Java", "x"));

        try {
            findAll("Java", "");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac SafeSubstringSearch.java
java SafeSubstringSearch
```

Kết quả:

```text
[0, 2]
[0, 1, 2]
[]
[]
keyword must not be empty
```

Trong `findAll()`:

- Kiểm tra `null` trước khi gọi phương thức trên `text` hoặc `keyword`.
- Chặn `keyword.isEmpty()` để không có trường hợp `indexOf("")` trả lại vị trí cũ liên tục.
- Tăng `from = found + 1` giúp tìm **cả những lần xuất hiện chồng lấn**. Nếu bài toán chỉ cần lần khớp **không chồng lấn** với keyword không rỗng, có thể tăng `from = found + keyword.length()`.
- Vòng lặp hữu hạn vì `from` tăng và bị ràng buộc bởi độ dài chuỗi. Khi không còn kết quả, `indexOf()` trả `-1` và vòng lặp dừng.

Với chương trình cần hiển thị vị trí khớp rỗng như một tính năng hợp lệ, hãy mô tả rõ: trên chuỗi có `n` UTF-16 code units sẽ có **`n + 1` ranh giới** (từ `0` đến `n`). Đây là quy ước về **vị trí chỉ số UTF-16**, không phải số ranh giới grapheme mà người dùng nhìn thấy.

## 11. Unicode: vị trí tìm kiếm tính theo UTF-16, không theo số emoji hiển thị

Các API `indexOf()` và `lastIndexOf()` của `String` trả về **chỉ số UTF-16 code units**. Ví dụ:

```java
String text = "A\uD83D\uDE00B"; // A😀B, emoji là một surrogate pair.

System.out.println(text.length());        // 4
System.out.println(text.indexOf("B"));    // 3
System.out.println(text.indexOf(""));     // 0
System.out.println(text.lastIndexOf("")); // 4
System.out.println(text.indexOf("", 2));  // 2
```

Về mặt chuỗi ký tự hiển thị, văn bản `A😀B` thường có ba ký tự được cảm nhận. Nhưng về chỉ số UTF-16, nó có bốn code units: `A` ở 0; hai đơn vị mã của emoji ở 1 và 2; `B` ở 3.

Vì chuỗi tìm rỗng không chiếm code unit nào, vị trí `2` vẫn là một **ranh giới UTF-16 hợp lệ cho phép tìm kiếm**, dù ranh giới đó nằm giữa hai nửa của surrogate pair. Đây là lý do không nên diễn giải vị trí tìm `""` trực tiếp thành “vị trí ký tự hiển thị” trong giao diện.

Nếu ứng dụng muốn di chuyển theo Unicode code points, dùng những API như `codePointAt()`, `codePointCount()`, `offsetByCodePoints()` khi phù hợp. Nếu muốn thao tác theo ký tự người dùng cảm nhận (grapheme), cần quy tắc phân đoạn grapheme phù hợp. **`String.length()` và chỉ số `indexOf()` không tự giải quyết vấn đề đó.**

So sánh tìm kiếm `String` theo các API trên cũng **phân biệt chữ hoa/chữ thường** và **không tự chuẩn hóa Unicode**. Ví dụ `"Java".indexOf("java") == -1`; còn hai cách biểu diễn Unicode nhìn giống nhau có thể khác dãy đơn vị mã. Nếu nghiệp vụ yêu cầu chuẩn hóa, cần làm một cách nhất quán trước khi tìm.

## 12. Một số trường hợp ở biên bổ sung

| Tình huống | Kết quả / Điều cần lưu ý |
| --- | --- |
| `text.indexOf("")` | Luôn `0` với mọi đối tượng `String text` khác `null`. |
| `text.lastIndexOf("")` | Luôn bằng `text.length()`. |
| `text.contains("")` | Luôn `true` đối với đối tượng `String` khác `null`. |
| `text.indexOf("", Integer.MAX_VALUE)` | Bằng `text.length()`. |
| `text.indexOf("", Integer.MIN_VALUE)` | Bằng `0`. |
| `text.lastIndexOf("", Integer.MAX_VALUE)` | Bằng `text.length()`. |
| `text.lastIndexOf("", Integer.MIN_VALUE)` | `-1`. |
| `text.startsWith("", text.length())` | `true`. |
| `text.startsWith("", text.length() + 1)` | `false`, nếu phép cộng không tràn số nguyên (với chuỗi Java thực tế thông thường). |
| `text.indexOf("x")` mà không có `x` | `-1`. |
| `text.indexOf("") == -1` | Luôn `false` khi `text` khác `null`. |
| `text.contains(" ")` | Tìm **dấu cách thật**, không đồng nghĩa `contains("")`. |

Cần nhớ rằng `indexOf(int ch)` tìm một **ký tự/code point** theo tham số `int`, không nhận một chuỗi tìm rỗng; các quy tắc tìm `""` ở bài này dành cho overload nhận **`String`** (hoặc `CharSequence` trong trường hợp `contains()`).

## 13. Những ngộ nhận dễ gây lỗi

1. **“Không có ký tự nào thì không thể tìm thấy.”** Sai: chuỗi rỗng là chuỗi con hợp lệ; `indexOf("")` trả `0`.
2. **“`lastIndexOf("")` luôn trả `0`.”** Sai: trên chuỗi `"Java"`, nó trả `4`.
3. **“`contains("")` nghĩa là nguồn phải có ít nhất một ký tự.”** Sai: `"".contains("")` vẫn là `true`.
4. **“Chỉ số lớn hơn độ dài thì `indexOf` luôn trả `-1`.”** Sai khi chuỗi tìm rỗng: `text.indexOf("", 999)` trả `text.length()`.
5. **“`indexOf` và `lastIndexOf` xử lý chỉ số âm giống nhau.”** Sai: `indexOf("", -1)` trả `0`; `lastIndexOf("", -1)` trả `-1`.
6. **“`startsWith("", offset)` luôn đúng ở mọi offset.”** Sai: chỉ đúng khi `offset` thuộc đoạn `0..length()`.
7. **“Chuỗi rỗng giống `null`.”** Sai: `""` là đối tượng hợp lệ còn `null` không phải đối tượng `String`.
8. **“Vòng lặp tìm tất cả khớp có thể tăng `keyword.length()` bất kể giá trị.”** Sai: khi keyword rỗng, độ tăng bằng `0` có thể tạo vòng lặp vô hạn.
9. **“Mọi chỉ số tìm kiếm là số ký tự hiển thị.”** Sai: `String` dùng vị trí UTF-16 code units, kể cả ở giữa surrogate pair.

## 14. Tự kiểm tra

**Câu 1.** Với `String s = "abc";`, ba kết quả sau là gì?

```java
System.out.println(s.indexOf(""));
System.out.println(s.lastIndexOf(""));
System.out.println(s.contains(""));
```

Đáp án:

```text
0
3
true
```

**Câu 2.** Vì sao kết quả hai lời gọi sau không giống nhau?

```java
String s = "abc";
System.out.println(s.indexOf("", -5));
System.out.println(s.lastIndexOf("", -5));
```

Kết quả lần lượt là `0` và `-1` vì tìm xuôi giới hạn đầu vào âm về `0`, còn tìm ngược với `fromIndex < 0` không có điểm bắt đầu hợp lệ.

**Câu 3.** Nếu `String s = "";`, kết quả `s.startsWith("")`, `s.endsWith("")` và `s.indexOf("x")` là gì?

Lần lượt: `true`, `true` và `-1`. Nguồn rỗng vẫn có tiền tố/hậu tố rỗng nhưng không chứa chuỗi `"x"`.

**Câu 4.** Một ô tìm kiếm cho phép người dùng để trống, và chức năng yêu cầu “không nhập gì thì hiển thị tất cả bản ghi”. Có nên chỉ viết `value.contains(keyword)`?

Không nên chỉ dựa vào hành vi ngầm của `contains("")`. Hãy kiểm tra rõ `keyword == null`, `keyword.isEmpty()` (hoặc `isBlank()` nếu nghiệp vụ coi whitespace là bỏ trống), rồi chọn nhánh “không lọc”. Làm vậy sẽ rõ chính sách dữ liệu và tránh trường hợp mã sau này đổi API nhưng không còn giữ cùng hành vi.

**Câu 5.** Một vòng lặp tiến từ `from = found + keyword.length()` bị kẹt khi keyword rỗng vì sao?

Vì `keyword.length() == 0` và `indexOf("", from)` trả lại `from` nếu nó nằm trong phạm vi. Cần chặn keyword rỗng hoặc triển khai một nhánh xử lý ranh giới riêng.

## Tóm tắt kiến thức

- `""` là chuỗi tìm hợp lệ: `indexOf("") == 0`, `lastIndexOf("") == length()`, `contains("") == true`, `startsWith("") == true` và `endsWith("") == true`.
- `indexOf("", fromIndex)` giới hạn `fromIndex` trong đoạn `0..length()`. `lastIndexOf("", fromIndex)` trả `-1` với chỉ số âm, còn chỉ số không âm được giới hạn tối đa tại `length()`.
- `startsWith("", offset)` chỉ trả `true` khi `offset` nằm trong phạm vi `0..length()`.
- Với chuỗi tìm không rỗng, `-1` nghĩa là không có khớp thỏa điều kiện; kết quả tìm kiếm tính theo **UTF-16 code-unit indexes**.
- Phân biệt rõ `""`, whitespace và `null`. Khi viết vòng lặp tìm nhiều lần khớp, **xử lý keyword rỗng tường minh** để tránh không tiến lên.
- Trường hợp ở biên không phải ngoại lệ cần đoán: mỗi phương thức có hợp đồng riêng; đọc và thử đúng API được dùng.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): hợp đồng chính thức của `indexOf(String)`, `indexOf(String, int)`, `lastIndexOf(String)`, `lastIndexOf(String, int)`, `contains(CharSequence)`, `startsWith(String, int)` và `endsWith(String)`.
- [Java SE 21 API — `java.lang.Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): UTF-16, surrogate pairs và Unicode code points.
