# Giá trị -1 và lỗi dùng kết quả tìm kiếm làm chỉ số trong Java String

Khi tìm một ký tự hoặc một đoạn văn bản bằng `String.indexOf(...)` hay `String.lastIndexOf(...)`, kết quả là **vị trí bắt đầu khớp theo chỉ số UTF-16**, hoặc **`-1` nếu không tìm thấy**. Giá trị `-1` là một *giá trị báo hiệu* (*sentinel*), không phải vị trí của ký tự trong chuỗi.

Lỗi thường gặp là đưa ngay kết quả tìm kiếm vào `substring(...)`, `charAt(...)` hoặc phép tính chỉ số mà chưa kiểm tra. Có trường hợp Java ném ngoại lệ rõ ràng; có trường hợp phép tính biến `-1` thành `0` và trả về nội dung **sai nhưng hoàn toàn không báo lỗi**. Để xử lý đúng, hãy hiểu hợp đồng của hàm tìm kiếm trước, kiểm tra trạng thái “không tìm thấy”, rồi mới tính ranh giới cần trích xuất.

## 1. `indexOf` và `lastIndexOf` trả giá trị gì?

Những overload quen thuộc của `String` gồm:

```java
text.indexOf('a');             // tìm ký tự/code point
text.indexOf("abc");           // tìm chuỗi con
text.indexOf("abc", fromIndex); // tìm từ vị trí chỉ định
text.lastIndexOf('a');         // vị trí khớp cuối cùng
text.lastIndexOf("abc");       // vị trí bắt đầu khớp cuối cùng
```

Đây là **đoạn minh họa các lời gọi**, giả sử biến `text` có kiểu `String` và không null. `indexOf` tìm từ trái sang phải; `lastIndexOf` tìm lần xuất hiện cuối cùng (hoặc ngược về phía đầu đối với overload có `fromIndex`). Cả hai trả về **`int`**, với hai nhóm kết quả:

- **Tìm thấy:** trả một offset UTF-16 **không âm**. Giá trị `0` là kết quả hợp lệ, nghĩa là khớp ngay từ đầu chuỗi. Nếu tìm đoạn dài hơn 0, vị trí khớp không thể vượt quá `text.length() - needle.length()`.
- **Không tìm thấy:** trả **`-1`**, không có vị trí tương ứng trong chuỗi.

Ví dụ với `"bananas"` có độ dài `7`:

| Lời gọi | Kết quả | Giải thích |
|---|---:|---|
| `"bananas".indexOf('a')` | `1` | Chữ `a` đầu tiên ở vị trí 1 |
| `"bananas".lastIndexOf('a')` | `5` | Chữ `a` cuối cùng ở vị trí 5 |
| `"bananas".indexOf("na")` | `2` | Khớp `"na"` đầu tiên bắt đầu ở 2 |
| `"bananas".lastIndexOf("na")` | `4` | Khớp cuối cùng bắt đầu ở 4 |
| `"bananas".indexOf("xy")` | `-1` | Không chứa `"xy"` |
| `"bananas".indexOf("ba")` | `0` | Khớp ở đầu chuỗi; **không phải** thất bại |
| `"bananas".indexOf("")` | `0` | Chuỗi tìm kiếm rỗng khớp tại ranh giới đầu |
| `"bananas".lastIndexOf("")` | `7` | Chuỗi tìm kiếm rỗng khớp tại ranh giới cuối |

**Phân biệt `0` và `-1`:** Điều kiện `if (index > 0)` sẽ bỏ sót khớp ở đầu; điều kiện `if (index == 0)` không có nghĩa là không tìm thấy. Để kiểm tra có khớp, dùng `index >= 0` hoặc `index != -1`; để kiểm tra thất bại, dùng `index == -1` hoặc `index < 0` khi giá trị xuất phát từ các API tìm kiếm này.

### Ví dụ chạy được: đọc đúng vị trí và sentinel

Lưu thành **`SearchResultDemo.java`**:

```java
public class SearchResultDemo {
    public static void main(String[] args) {
        String text = "bananas";

        System.out.println("first a: " + text.indexOf('a'));
        System.out.println("last a: " + text.lastIndexOf('a'));
        System.out.println("first na: " + text.indexOf("na"));
        System.out.println("last na: " + text.lastIndexOf("na"));
        System.out.println("missing xy: " + text.indexOf("xy"));
        System.out.println("at beginning: " + text.indexOf("ba"));
        System.out.println("empty indexOf: " + text.indexOf(""));
        System.out.println("empty lastIndexOf: " + text.lastIndexOf(""));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac SearchResultDemo.java
java SearchResultDemo
```

**Stdout:**

```text
first a: 1
last a: 5
first na: 2
last na: 4
missing xy: -1
at beginning: 0
empty indexOf: 0
empty lastIndexOf: 7
```

Chuỗi rỗng là **trường hợp đặc biệt quan trọng**. Tìm `""` không có nghĩa là tìm thất bại: `indexOf("")` cho `0`, `lastIndexOf("")` cho `length()`. Vì vậy, khi thiết kế chức năng “tìm lần xuất hiện của một từ khóa”, hãy quyết định rõ liệu từ khóa rỗng có được chấp nhận hay phải bị từ chối ngay từ đầu.

## 2. Vì sao `-1` nguy hiểm khi dùng như một chỉ số?

Nhiều API truy cập chuỗi chỉ nhận chỉ số không âm:

| API | Miền chỉ số hợp lệ | Nếu đưa trực tiếp `-1` |
|---|---|---|
| `charAt(index)` | `0 <= index < length()` | Ném `IndexOutOfBoundsException` |
| `substring(begin)` | `0 <= begin <= length()` | Ném `IndexOutOfBoundsException` |
| `substring(begin, end)` | `0 <= begin <= end <= length()` | Ném `IndexOutOfBoundsException` nếu begin/end là `-1` |
| `subSequence(begin, end)` | Tương tự `substring(begin, end)` | Phạm vi sai; ném ngoại lệ |
| `codePointAt(index)` | `0 <= index < length()` | Ném `IndexOutOfBoundsException` |
| `substring(position + 1)` | Tùy kết quả phép cộng | **Có thể hợp lệ nhưng sai ý nghĩa** nếu `position == -1` |

Điểm cuối cùng đặc biệt dễ bỏ qua:

```java
String input = "name=value";
int colon = input.indexOf(':'); // -1

// Sai: từ 0 tới -1, gây ngoại lệ.
String beforeColon = input.substring(0, colon);

// Cũng sai về ý nghĩa: -1 + 1 = 0.
// Không có ngoại lệ; kết quả lại là toàn chuỗi "name=value".
String afterColon = input.substring(colon + 1);
```

Đây là **mã minh họa hai lỗi**, không phải chương trình để chạy nguyên khối. Một lỗi biểu hiện ngay bằng ngoại lệ; lỗi còn lại nguy hiểm vì giá trị trông hợp lệ và dễ lọt qua kiểm thử hời hợt.

**Nguyên tắc:** kiểm tra **kết quả tìm kiếm gốc trước khi cộng/trừ**. Đừng dùng `index + 1`, `index - 1`, `substring(index)` hoặc `charAt(index)` trước khi bảo đảm `index >= 0` và ranh giới phát sinh vẫn hợp lệ.

## 3. Ví dụ đối chiếu: ngoại lệ và lỗi trả sai âm thầm

**`SearchIndexPitfallDemo.java`**

```java
public class SearchIndexPitfallDemo {
    public static void main(String[] args) {
        String input = "name=value";
        int colon = input.indexOf(':');

        System.out.println("colon: " + colon);

        try {
            System.out.println(input.substring(0, colon));
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("substring(0, -1): invalid");
        }

        try {
            System.out.println(input.charAt(colon));
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("charAt(-1): invalid");
        }

        String misleading = input.substring(colon + 1);
        System.out.println("substring(-1 + 1): " + misleading);
    }
}
```

```bash
javac SearchIndexPitfallDemo.java
java SearchIndexPitfallDemo
```

**Stdout:**

```text
colon: -1
substring(0, -1): invalid
charAt(-1): invalid
substring(-1 + 1): name=value
```

Ví dụ chủ động bắt ngoại lệ để minh họa lỗi. Trong mã nghiệp vụ, không nên dùng bắt ngoại lệ làm bước kiểm tra thông thường cho trường hợp dấu phân cách có thể không tồn tại: `indexOf()` đã trả `-1` để báo rõ tình huống đó.

Một bẫy liên quan: nếu viết `text.substring(found, found + keyword.length())` khi `found == -1`, biểu thức có thể gây ngoại lệ; nếu `keyword.length() == 1` thì `found + keyword.length() == 0` và vẫn sai vì ranh giới bắt đầu `-1`. Không có phép cộng nào khiến `found == -1` trở thành bằng chứng đã tìm thấy.

## 4. Quy trình chuẩn: kiểm tra trước, tính chỉ số sau

Để lấy phần trước/sau một dấu phân cách, tách ba bước:

1. **Tìm** dấu phân cách bằng `indexOf()` hoặc `lastIndexOf()`.
2. **Kiểm tra** kết quả có phải `-1` không.
3. **Chỉ khi tìm thấy**, sử dụng vị trí để gọi `substring()`.

Ví dụ phân tích chuỗi `key=value`:

**`SafeDelimiterDemo.java`**

```java
public class SafeDelimiterDemo {
    private static void parse(String line) {
        int separator = line.indexOf('=');

        if (separator < 0) {
            System.out.println("Missing separator: " + line);
            return;
        }

        String key = line.substring(0, separator);
        String value = line.substring(separator + 1);

        System.out.println("key=<" + key + ">, value=<" + value + ">");
    }

    public static void main(String[] args) {
        parse("name=Java");
        parse("=value");
        parse("key=");
        parse("missing");
        parse("a=b=c");
    }
}
```

```bash
javac SafeDelimiterDemo.java
java SafeDelimiterDemo
```

**Stdout:**

```text
key=<name>, value=<Java>
key=<>, value=<value>
key=<key>, value=<>
Missing separator: missing
key=<a>, value=<b=c>
```

Cần hiểu các trường hợp biên:

- Dấu phân cách ở **đầu** có `separator == 0`. Đây là **đã tìm thấy**, nên chuỗi trước dấu là `""`.
- Dấu phân cách ở **cuối** có `separator == length() - 1`, vì thế `substring(separator + 1)` tương đương `substring(length())`, là phép trích xuất **hợp lệ** trả về `""`.
- Không có dấu phân cách thì `separator == -1`. Ví dụ xử lý bằng thông báo riêng; không tiếp tục tính ranh giới.
- Nếu có nhiều dấu `=`, `indexOf('=')` lấy dấu **đầu tiên**, phần bên phải có thể vẫn chứa dấu `=`. Nếu yêu cầu lấy dấu cuối cùng, chuyển sang `lastIndexOf('=')` và giữ nguyên bước kiểm tra `-1`.
- Bài toán có thể yêu cầu **key không rỗng**, **value không rỗng**, hoặc chỉ chấp nhận đúng một dấu `=`. Đó là các kiểm tra **nghiệp vụ bổ sung**; sự tồn tại của dấu phân cách không tự bảo đảm các điều kiện ấy.

### Trường hợp không tìm thấy cần một hợp đồng rõ ràng

Thay vì luôn in thông báo, một hàm thư viện có thể:

- Trả về `Optional<String>` hoặc một kiểu kết quả nêu rõ “có/không có”.
- Ném `IllegalArgumentException` nếu dấu phân cách bắt buộc phải có và thiếu là dữ liệu sai.
- Trả `null` nếu API quy định như vậy, nhưng người gọi phải biết và kiểm tra `null`.

Không nên trả `""` vô điều kiện để thay cho “không có dấu”: dấu ở cuối chuỗi cũng cho **giá trị rỗng hợp lệ**. Nếu hai trạng thái có ý nghĩa khác nhau, cần biểu diễn chúng khác nhau.

## 5. Từ vị trí khớp đến phạm vi chuỗi con

Với `needle` là từ khóa **không rỗng** và `position = text.indexOf(needle)`:

```text
Nếu position == -1:
    Không có vùng khớp; không được tự tạo chỉ số con.

Nếu position >= 0:
    begin = position
    end   = position + needle.length()
    [begin, end) nằm trong text.
```

`indexOf(String)` trả vị trí bắt đầu của toàn bộ chuỗi con khớp, vì vậy khi tìm thấy, Java bảo đảm đủ code unit để có đoạn `needle`. Độ dài ở đây là `needle.length()` theo UTF-16, cùng đơn vị với chỉ số mà `indexOf` trả về.

Ví dụ:

**`MatchRangeDemo.java`**

```java
public class MatchRangeDemo {
    private static void showMatch(String text, String needle) {
        if (needle.isEmpty()) {
            System.out.println("Empty keyword is not supported");
            return;
        }

        int position = text.indexOf(needle);
        if (position < 0) {
            System.out.println("Not found: " + needle);
            return;
        }

        int end = position + needle.length();
        String found = text.substring(position, end);
        System.out.println("match [" + position + "," + end + "): " + found);
    }

    public static void main(String[] args) {
        showMatch("Java String", "String");
        showMatch("Java String", "Java");
        showMatch("Java String", "Kotlin");
        showMatch("Java String", "");
    }
}
```

```bash
javac MatchRangeDemo.java
java MatchRangeDemo
```

**Stdout:**

```text
match [5,11): String
match [0,4): Java
Not found: Kotlin
Empty keyword is not supported
```

Trường hợp `needle.isEmpty()` được **chủ động từ chối theo hợp đồng ví dụ**, vì nhu cầu là khớp một từ khóa có nội dung. Đây không phải hạn chế của `indexOf("")`; Java cho phép tìm chuỗi rỗng.

Khi biến `position` đã được kiểm tra, việc trích xuất cả vùng khớp hữu ích cho tô sáng, thay thế có kiểm soát, ghi nhận offset hoặc phân tích cú pháp. Nhưng nếu muốn so nội dung, `text.contains(needle)` hoặc `text.indexOf(needle) >= 0` có thể đủ, không cần `substring`.

## 6. Lấy phần mở rộng tên tệp bằng `lastIndexOf`

Một ứng dụng hay tìm dấu chấm cuối cùng rồi lấy phần sau:

```java
int dot = filename.lastIndexOf('.');
String extension = filename.substring(dot + 1);
```

Nếu không có dấu chấm, `dot == -1`, làm `dot + 1 == 0` và biến `extension` nhận **toàn bộ tên tệp** thay vì một phần mở rộng. Không có ngoại lệ, nhưng nghĩa dữ liệu sai.

Ngay cả khi có dấu, cần phân biệt:

- `"report.txt"`: dấu ở giữa, phần mở rộng `"txt"`.
- `"report"`: không có dấu, không có phần mở rộng.
- `".env"`: dấu ở đầu; nhiều hệ thống xem đây là tên file ẩn **không có phần mở rộng**.
- `"report."`: dấu ở cuối; phần sau rỗng, chính sách ứng dụng có thể coi là không có phần mở rộng.
- `"archive.tar.gz"`: dùng dấu cuối nên phần mở rộng là `"gz"`, không phải `"tar.gz"`.

Ví dụ dưới đây quy định **chỉ trả phần mở rộng nếu dấu chấm nằm giữa tên tệp**.

**`FileExtensionDemo.java`**

```java
import java.util.Optional;

public class FileExtensionDemo {
    private static Optional<String> extensionOf(String name) {
        int dot = name.lastIndexOf('.');
        if (dot <= 0 || dot == name.length() - 1) {
            return Optional.empty();
        }
        return Optional.of(name.substring(dot + 1));
    }

    private static void show(String name) {
        System.out.println(name + " -> "
                + extensionOf(name).orElse("(none)"));
    }

    public static void main(String[] args) {
        show("report.txt");
        show("report");
        show(".env");
        show("report.");
        show("archive.tar.gz");
    }
}
```

```bash
javac FileExtensionDemo.java
java FileExtensionDemo
```

**Stdout:**

```text
report.txt -> txt
report -> (none)
.env -> (none)
report. -> (none)
archive.tar.gz -> gz
```

Đây chỉ là quy tắc phân tích **chuỗi tên tệp đơn giản**, không phải trình phân tích đường dẫn đầy đủ hoặc quy tắc thống nhất của mọi hệ điều hành. Với đường dẫn có thư mục, dấu chấm trong tên thư mục hay nhiều loại file đặc biệt, cần xử lý tên tệp riêng và thống nhất chính sách ứng dụng.

## 7. Các bẫy với `fromIndex`, vị trí đầu và từ khóa rỗng

Overload có `fromIndex` dùng để điều khiển nơi bắt đầu tìm, nhưng không biến `-1` thành một chỉ số hợp lệ để trích chuỗi.

Ví dụ trên `"bananas"`:

| Biểu thức | Kết quả | Ý nghĩa |
|---|---:|---|
| `indexOf("na", 0)` | `2` | Khớp đầu tiên từ vị trí 0 |
| `indexOf("na", 3)` | `4` | Bỏ qua khớp bắt đầu ở 2 |
| `indexOf("na", 5)` | `-1` | Không còn khớp bắt đầu tại/từ 5 |
| `indexOf("na", -10)` | `2` | Với `indexOf`, `fromIndex` âm được xử lý như 0 |
| `indexOf("na", 99)` | `-1` | Vị trí bắt đầu tìm đã ở sau mọi khớp |
| `lastIndexOf("na", 3)` | `2` | Khớp cuối cùng có vị trí bắt đầu không vượt 3 |
| `lastIndexOf("na", -1)` | `-1` | Không có vị trí bắt đầu không âm <= -1 |
| `lastIndexOf("na", 99)` | `4` | Vẫn lấy khớp cuối cùng hiện có |

**Chú ý sự khác nhau:** `indexOf(..., -10)` có thể tìm ra kết quả vì cách nó xử lý offset bắt đầu âm, còn `lastIndexOf(..., -1)` trả `-1`. Đây là hợp đồng của **phương thức tìm kiếm**, không phải giấy phép truyền chỉ số âm vào `substring()` hay `charAt()`.

Ngoài ra:

- `text.indexOf("")` bằng `0` và `text.lastIndexOf("")` bằng `text.length()` đối với dạng **không truyền fromIndex**.
- Với `indexOf("", fromIndex)`, Java giới hạn ranh giới kết quả vào đoạn `[0, length()]`; tìm chuỗi rỗng thường vẫn có kết quả kể cả khi offset bắt đầu nằm ngoài độ dài.
- Với `lastIndexOf("", fromIndex)`, ranh giới lớn hơn độ dài được đưa về `length()`; nếu `fromIndex < 0` thì trả `-1`.
- Nếu thuật toán lặp đang tìm tất cả các khớp, một `needle` rỗng cần xử lý đặc biệt. Nếu không, việc tăng chỉ số qua `length()` nhưng tiếp tục gọi `indexOf("", fromIndex)` có thể dẫn đến **vòng lặp vô hạn** khi kết quả cứ là `length()`.

Nếu người gọi chỉ cần **biết có hay không có**, dùng `text.contains(needle)` là cách trực tiếp, rõ ý định, nhưng cần biết `contains("")` là `true`. Khi cần offset để trích xuất, `indexOf`/`lastIndexOf` vẫn cần thiết.

## 8. Tìm tất cả vị trí: kiểm tra `-1` và tiến chỉ số đúng

Để tìm nhiều lần xuất hiện, thường dùng vòng lặp gọi lại `indexOf(needle, fromIndex)`. Luôn:

1. Quy định từ khóa không rỗng hoặc có nhánh xử lý riêng cho chuỗi rỗng.
2. Kiểm tra `position < 0` **trước khi** sử dụng hoặc cộng vào vị trí khớp.
3. Tăng vị trí tìm tiếp để thuật toán có tiến triển.
4. Chọn có cho phép các khớp **chồng lấn** hay không.

Ví dụ với `"aaaa"` và `"aa"`: vị trí khớp chồng lấn là `0, 1, 2`. Nếu tăng `fromIndex` theo `needle.length() == 2` sau mỗi khớp, thuật toán chỉ lấy `0, 2` (không chồng lấn).

**`FindAllMatchesDemo.java`**

```java
public class FindAllMatchesDemo {
    private static void findAllOverlapping(String text, String needle) {
        if (needle.isEmpty()) {
            throw new IllegalArgumentException("needle must not be empty");
        }

        int from = 0;
        while (true) {
            int index = text.indexOf(needle, from);
            if (index == -1) {
                return;
            }

            System.out.println("match at: " + index);
            from = index + 1;
        }
    }

    public static void main(String[] args) {
        findAllOverlapping("aaaa", "aa");
    }
}
```

```bash
javac FindAllMatchesDemo.java
java FindAllMatchesDemo
```

**Stdout:**

```text
match at: 0
match at: 1
match at: 2
```

Ở đây tăng `from = index + 1` để cho phép chồng lấn. Vì `needle` không rỗng, mỗi vị trí khớp nằm trước cuối chuỗi; `from` tăng và vòng lặp dừng khi không còn khớp. Nếu ứng dụng yêu cầu khớp không chồng lấn, đặt `from = index + needle.length()` sau mỗi kết quả và giữ nguyên kiểm tra `-1`.

## 9. Chỉ số tìm kiếm là offset UTF-16, không phải số “ký tự nhìn thấy”

Các overload tìm kiếm của `String` trả **offset UTF-16**, thống nhất với `substring`. Điều này quan trọng với emoji, ký tự ngoài BMP, dấu kết hợp và một số tổ hợp ký tự.

Ví dụ `"A😊B😊"` có `length() == 6`: `A` chiếm một code unit, mỗi emoji 😊 chiếm hai code unit và `B` chiếm một. Hai emoji lần lượt bắt đầu tại offset `1` và `4`, dù người đọc thấy chúng ở vị trí ký tự thứ hai và thứ tư nếu đếm theo phần tử hiển thị.

**`UnicodeSearchIndexDemo.java`**

```java
public class UnicodeSearchIndexDemo {
    public static void main(String[] args) {
        String smile = "\uD83D\uDE0A";
        String text = "A" + smile + "B" + smile;

        int first = text.indexOf(smile);
        int last = text.lastIndexOf(smile);
        int missing = text.indexOf("X");

        System.out.println("units: " + text.length());
        System.out.println("points: "
                + text.codePointCount(0, text.length()));
        System.out.println("first smile: " + first);
        System.out.println("last smile: " + last);
        System.out.println("missing X: " + missing);
        System.out.println("complete smile: "
                + text.substring(first, first + smile.length()).equals(smile));

        String broken = text.substring(first, first + 1);
        System.out.println("broken high surrogate: "
                + Character.isHighSurrogate(broken.charAt(0)));
    }
}
```

```bash
javac UnicodeSearchIndexDemo.java
java UnicodeSearchIndexDemo
```

**Stdout:**

```text
units: 6
points: 4
first smile: 1
last smile: 4
missing X: -1
complete smile: true
broken high surrogate: true
```

**Giải thích:** `indexOf(smile)` trả offset bắt đầu của toàn bộ cặp surrogate; `smile.length() == 2` nên phạm vi `[first, first + 2)` lấy đầy đủ emoji. Nếu chỉ cắt `[first, first + 1)`, kết quả là một high surrogate đứng lẻ dù ranh giới vẫn đúng về mặt số học.

Nếu chỉ số dùng để đánh dấu vị trí trong giao diện hay đếm code point, hãy chuyển đổi đơn vị một cách tường minh. Dù trích đúng các code point, một tổ hợp chữ và dấu hoặc emoji ghép có thể gồm nhiều code point; khi yêu cầu giữ nguyên “ký tự người dùng cảm nhận”, cần phân đoạn theo grapheme cluster.

## 10. Phân biệt kết quả tìm kiếm, chỉ số không hợp lệ và đầu vào null

Ba loại tình huống này cần xử lý khác nhau:

- **Không tìm thấy:** `indexOf`/`lastIndexOf` trả `-1`. Đây là **kết quả bình thường** của một phép tìm kiếm, không phải ngoại lệ.
- **Dùng chỉ số không hợp lệ để truy cập/trích xuất:** `charAt(-1)`, `substring(0, -1)` hoặc `substring(length() + 1)` ném một loại `IndexOutOfBoundsException`.
- **Không có đối tượng `String` để gọi phương thức:** nếu biến `text == null` mà gọi `text.indexOf("a")`, chương trình ném `NullPointerException`. Không thể coi null là “không tìm thấy” trừ khi API bao ngoài chủ động thiết kế như vậy.

Nếu chỉ cần kiểm tra chuỗi có chứa đoạn văn bản, `contains()` là một lựa chọn diễn đạt rõ ràng:

```java
String text = "Java String";
boolean found = text.contains("String"); // true
boolean absent = text.contains("Kotlin"); // false
```

Đây là ví dụ minh họa, không phải một lớp độc lập. `contains()` trả boolean, không có sentinel `-1`; tuy nhiên nó cũng không cho vị trí để cắt chuỗi. Nếu `text` là null, `text.contains(...)` vẫn ném `NullPointerException`.

Ngoài ra, **đừng kiểm tra kết quả bằng `if (index)`** như trong vài ngôn ngữ khác: Java không tự chuyển `int` thành `boolean` nên câu đó không biên dịch. Viết rõ `if (index >= 0)` hoặc `if (index == -1)`.

## 11. Sai lầm điển hình và cách phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| `substring(0, text.indexOf(':'))` | Nếu không có `:`, `end == -1` và ném ngoại lệ | Lưu kết quả vào biến, kiểm tra `>= 0` trước |
| `substring(text.indexOf(':') + 1)` | Nếu không thấy `:`, trả toàn chuỗi từ offset 0 | Kiểm tra sentinel **trước khi cộng 1** |
| `if (index > 0)` để kiểm tra tìm thấy | Bỏ sót khớp ở vị trí `0` | Dùng `index >= 0` |
| `charAt(indexOf(...))` | Có thể nhận chỉ số `-1` và ném ngoại lệ | Chỉ truy cập sau khi chắc chắn có khớp |
| Lấy phần mở rộng bằng `substring(lastIndexOf('.') + 1)` | Không có dấu chấm thì trả toàn bộ tên | Kiểm tra `dot` và ràng buộc vị trí hợp lệ |
| Lặp `indexOf("", fromIndex)` không có nhánh riêng | Có thể không tiến triển và lặp mãi ở cuối | Xử lý từ khóa rỗng tường minh |
| Coi `indexOf(...) == 0` là thất bại | Bỏ qua từ khóa ở đầu | `0` là vị trí hợp lệ |
| Nghĩ mọi kết quả `-1` đều là ngoại lệ | Nhầm hợp đồng tìm kiếm với hợp đồng trích xuất | Tìm kiếm trả sentinel; dùng sai chỉ số mới gây lỗi |
| Dùng index tìm kiếm như số thứ tự code point | Sai vị trí khi chuỗi chứa ký tự ngoài BMP | Ghi rõ offset UTF-16 và chuyển đổi khi cần |
| Xem chuỗi rỗng sau dấu phân cách là “không tìm thấy” | Gộp hai trạng thái nghiệp vụ khác nhau | Phân biệt sentinel `-1` và `substring(length()) == ""` |

## 12. Tự kiểm tra

Với `text = "a:b:c"`, dự đoán kết quả sau:

```java
String text = "a:b:c";

int first = text.indexOf(':');
int last = text.lastIndexOf(':');
int absent = text.indexOf('/');

System.out.println(first);
System.out.println(last);
System.out.println(absent);
System.out.println(text.substring(first + 1));
System.out.println(text.substring(last + 1));
System.out.println(text.substring(absent + 1));
```

**Stdout:**

```text
1
3
-1
b:c
c
a:b:c
```

Ba dòng cuối minh họa điều quan trọng: cả `first + 1` và `last + 1` đều hợp lệ **vì có dấu `:`**, trong khi `absent + 1 == 0` tạo ra chuỗi toàn phần mà không ném ngoại lệ. Nếu kết quả có thể không tìm thấy, không được viết dòng cuối theo mẫu đó trong mã thật.

**Bài luyện tập ngắn:** viết một hàm lấy phần trước dấu `@` của địa chỉ nhập vào. Thử các trường hợp `"a@b"`, `"@b"`, `"a@"`, `"abc"` và `""`. Xác định riêng trường hợp thiếu dấu, trường hợp phần trước rỗng và trường hợp phần sau rỗng; đừng để phép cộng hoặc `substring` tự quyết định chính sách nghiệp vụ.

**Quy tắc cần ghi nhớ:** khi một API trả vị trí tìm kiếm, hãy đọc `-1` là **“không có vị trí”**, `0` là **“có khớp tại đầu”**, còn mọi giá trị dương hợp lệ là **offset UTF-16 của khớp**. Kiểm tra sentinel **trước**, sau đó mới tính `begin`, `end` hoặc gọi `substring`. Việc này ngăn được cả ngoại lệ hiển nhiên lẫn lỗi âm thầm khi `-1 + 1` trở thành `0`.
