# Khác biệt giữa String.lines() và String.split() với tham số limit trong Java



## 1. Mục tiêu bài học

Java cung cấp hai cách phổ biến để xử lý một chuỗi có nhiều dòng:

- `String.lines()` (Java 11+) trả về `Stream<String>`, duyệt các dòng phân cách bằng **LF (`\n`), CR (`\r`) hoặc CRLF (`\r\n`)**. Đây là thao tác theo dòng; không có tham số `limit` kiểu `split`.
- `String.split(regex)` và `String.split(regex, limit)` trả về **mảng `String[]`**, tách theo một **biểu thức chính quy**. Tham số `limit` điều khiển **số lần áp dụng regex** và **việc giữ hay bỏ các phần rỗng ở cuối**.

Sự khác biệt quan trọng nhất là **dữ liệu rỗng**, **cách giới hạn phần tử**, **bộ ký tự xuống dòng được nhận diện**, và **cách tiêu thụ kết quả**. Không nên coi `lines()` là cách viết khác hoàn toàn tương đương với `split("\\R")`.

Ví dụ nhanh:

```java
String text = "A\n\nB\n";

System.out.println(text.lines().toList());            // [A, , B]
System.out.println(Arrays.toString(text.split("\\R")));    // [A, , B]
System.out.println(Arrays.toString(text.split("\\R", -1))); // [A, , B, ]
```

Dù hai dòng đầu trông giống nhau ở ví dụ này, chúng **khác về kiểu trả về và chế độ làm việc**. Dòng cuối có thêm một phần tử `""` biểu thị ô trống sau ký tự xuống dòng cuối cùng. Khi in trực tiếp `List` hay mảng, phần tử rỗng rất khó quan sát; bài này sẽ dùng cách hiển thị riêng `<...>`.

**Phạm vi bài này:** `String.lines()` xem LF, CR và CRLF là kết thúc dòng và không phát sinh dòng rỗng chỉ từ newline cuối. Phần giải thích chi tiết các terminator nằm ở bài **lines và các kiểu kết thúc dòng CR, LF, CRLF**, còn bảng ranh giới chuỗi rỗng/newline cuối nằm ở bài **Chuỗi rỗng và ký tự xuống dòng ở cuối**. Bài hiện tại tập trung vào chế độ `limit`, kiểu trả về và số phần tử.

**Khác biệt ký tự phân tách:** regex `\\R` nhận Unicode linebreak rộng hơn LF/CR/CRLF, ví dụ U+2028; `split("\\n")` chỉ tách LF nên có thể để lại CR ở chuỗi trước một CRLF. Chọn regex theo định dạng đầu vào.

## 2. String.split(regex, limit): ba chế độ limit

Cú pháp:

```java
String[] parts = text.split(regex);         // Tương đương text.split(regex, 0)
String[] all = text.split(regex, -1);       // Giữ phần rỗng cuối
String[] atMostTwo = text.split(regex, 2); // Tối đa hai phần tử
```

`regex` là **regular expression** (không phải chuỗi phân cách literal). Để tách theo mọi kiểu ngắt dòng Unicode mà Java regex hỗ trợ, dùng `"\\R"` trong **mã nguồn Java**. Hai dấu `\\` trong Java source tạo một dấu `\` ở chuỗi runtime; `\R` là cú pháp regex biểu thị một chuỗi xuống dòng Unicode. Viết `"\R"` trực tiếp trong source sẽ không biên dịch vì `\R` không phải Java string escape.

| Giá trị `limit` | Cách tách | Phần rỗng ở cuối |
| --- | --- | --- |
| `limit > 0` | Pattern được áp dụng **tối đa `limit - 1` lần**; phần tử cuối chứa toàn bộ phần input còn lại | Được giữ nếu có trong các phần kết quả |
| `limit = 0` | Pattern được áp dụng nhiều lần nhất có thể | **Bỏ tất cả** phần tử `""` ở cuối |
| `limit < 0`, ví dụ `-1` | Pattern được áp dụng nhiều lần nhất có thể | **Giữ tất cả** phần tử `""` ở cuối |

`text.split(regex)` tương đương `text.split(regex, 0)`. Dấu `0` ở đây **không** có nghĩa là trả về không phần tử; nó là chế độ tách tối đa nhưng loại các chuỗi rỗng cuối.

Ví dụ cụ thể với `"A\n\nB\n"`:

- `split("\\R", 0)` → `["A", "", "B"]`. Có dòng trống ở giữa, nhưng bỏ trường trống cuối.
- `split("\\R", -1)` → `["A", "", "B", ""]`. Giữ cả trường rỗng sau dấu xuống dòng cuối.
- `split("\\R", 2)` → `["A", "\nB\n"]`. Chỉ tách tại dấu xuống dòng **đầu tiên**; phần thứ hai còn nguyên một dấu xuống dòng trước `B` và dấu xuống dòng cuối.
- `split("\\R", 1)` → mảng một phần tử duy nhất chứa toàn bộ `"A\n\nB\n"`. Không có lần tách nào được áp dụng vì `limit - 1 = 0`.

Điều này cho thấy `limit` dương của `split` **không tương đương** với số dòng cần lấy từ `lines().limit(n)`.

## 3. Ví dụ chạy được với Java 17+

Tạo file **`LinesVsSplitDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class LinesVsSplitDemo {
    // Bao mỗi phần tử trong <> và hiện ký tự xuống dòng dưới dạng \n, \r
    // để phân biệt phần tử rỗng với mảng/danh sách không có phần tử.
    static String show(List<String> parts) {
        return parts.stream()
                .map(s -> "<" + s
                        .replace("\r", "\\r")
                        .replace("\n", "\\n") + ">")
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static String show(String[] parts) {
        return show(Arrays.asList(parts));
    }

    public static void main(String[] args) {
        String input = "A\n\nB\n";

        System.out.println("lines       = " + show(input.lines().toList()));
        System.out.println("split(0)    = " + show(input.split("\\R")));
        System.out.println("split(-1)   = " + show(input.split("\\R", -1)));
        System.out.println("split(2)    = " + show(input.split("\\R", 2)));
        System.out.println("limit(2)    = " + show(input.lines().limit(2).toList()));

        System.out.println("mix         = "
                + show("A\r\nB\rC\nD".lines().toList()));

        System.out.println("empty lines = " + "".lines().count());
        System.out.println("empty split = " + "".split("\\R").length);

        String unicode = "A\u2028B"; // Unicode LINE SEPARATOR (U+2028)
        System.out.println("unicode lines = " + unicode.lines().count());
        System.out.println("unicode split = " + unicode.split("\\R").length);
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 LinesVsSplitDemo.java
java LinesVsSplitDemo
```

**Stdout** (đã đối chiếu hành vi các biểu thức qua JShell/JDK):

```text
lines       = [<A>, <>, <B>]
split(0)    = [<A>, <>, <B>]
split(-1)   = [<A>, <>, <B>, <>]
split(2)    = [<A>, <\nB\n>]
limit(2)    = [<A>, <>]
mix         = [<A>, <B>, <C>, <D>]
empty lines = 0
empty split = 1
unicode lines = 1
unicode split = 2
```

Các kết quả quan trọng:

1. `lines()` giữ **dòng rỗng nội bộ** của `"A\n\nB\n"`, nhưng không tạo thêm dòng rỗng sau ký tự `\n` cuối.
2. `split("\\R", -1)` giữ **cột trống cuối**, thích hợp khi phải phân biệt một bản ghi kết thúc bằng delimiter với bản ghi không có delimiter cuối.
3. `split("\\R", 2)` giữ lại phần `"\nB\n"` trong token cuối; `lines().limit(2)` chỉ lấy **hai dòng đầu tiên** là `"A"` và `""`.
4. Input rỗng là trường hợp khác biệt rõ: `lines()` cho `0` dòng, còn `split("\\R")` cho mảng có **một** phần tử `""`. Vì vậy in `Arrays.toString` trực tiếp có thể khiến cả hai trông như `[]` dù số phần tử khác nhau.
5. Ký tự U+2028 được `\\R` nhận diện là line break, còn `lines()` **không** nhận diện nó như một trong ba line terminator LF/CR/CRLF.

## 4. Những khác biệt dễ nhầm khi dùng limit

### 5.1. lines().limit(n) đếm dòng, split(regex, n) đếm phần tối đa

Cho input `"red\ngreen\nblue"`:

```java
String colors = "red\ngreen\nblue";

List<String> topTwo = colors.lines().limit(2).toList();
// ["red", "green"]

String[] twoParts = colors.split("\\R", 2);
// ["red", "green\nblue"]
```

`lines().limit(2)` bỏ qua dòng `blue` vì terminal operation không yêu cầu đến đó. Ngược lại, `split("\\R", 2)` không bỏ dữ liệu phía sau dấu phân tách đầu tiên; toàn bộ phần dư `green\nblue` nằm trong phần tử cuối.

**Khi nào dùng cách nào?**

- Chỉ cần hai dòng đầu để hiển thị, preview hoặc kiểm tra header: `lines().limit(2)`.
- Muốn tách **phần đầu** và **phần thân còn lại**, ví dụ dòng đầu là header và phần còn lại là nội dung: `split("\\R", 2)`. Cần xử lý input rỗng và trường hợp không có delimiter phù hợp theo nghiệp vụ.

### 5.2. Không nhầm split(..., 0) với Stream.limit(0)

`split("\\R", 0)` yêu cầu tách với chế độ loại trường rỗng ở cuối; kết quả vẫn có thể chứa nhiều phần tử. `lines().limit(0)` là Stream không có phần tử nào. Hai số `0` ở hai API có ý nghĩa hoàn toàn khác:

```java
String data = "a\nb";
System.out.println(data.split("\\R", 0).length); // 2
System.out.println(data.lines().limit(0).count()); // 0
```

### 5.3. filter và limit thay đổi thứ tự logic

```java
String input = "\nfirst\n\nsecond\nthird";

List<String> a = input.lines()
        .filter(s -> !s.isBlank())
        .limit(2)
        .toList();
// ["first", "second"]

List<String> b = input.lines()
        .limit(2)
        .filter(s -> !s.isBlank())
        .toList();
// ["first"]
```

Trong `a`, chương trình tìm hai dòng **không trống** đầu tiên; trong `b`, chỉ xét hai dòng gốc đầu tiên rồi lọc. Quy tắc tương tự áp dụng cho pipeline Stream nói chung.

## 5. Dòng rỗng: bảng các trường hợp biên

Bảng dùng ký hiệu `<A>` cho chuỗi `"A"` và `<>` cho chuỗi rỗng. Dấu ngoặc vuông `[...]` biểu diễn danh sách các phần tử; `[]` nghĩa là không có phần tử nào. Tất cả chuỗi input sau đây đều sử dụng ký tự `\n` thật.

| Input trong Java | `lines()` | `split("\\R", 0)` | `split("\\R", -1)` |
| --- | --- | --- | --- |
| `""` | `[]` | `[<>]` | `[<>]` |
| `"A"` | `[<A>]` | `[<A>]` | `[<A>]` |
| `"A\n"` | `[<A>]` | `[<A>]` | `[<A>, <>]` |
| `"A\n\n"` | `[<A>, <>]` | `[<A>]` | `[<A>, <>, <>]` |
| `"\nA"` | `[<>, <A>]` | `[<>, <A>]` | `[<>, <A>]` |
| `"\n"` | `[<>]` | `[]` | `[<>, <>]` |
| `"A\nB"` | `[<A>, <B>]` | `[<A>, <B>]` | `[<A>, <B>]` |

Không thể thay thế `lines()` bằng `split("\\R", 0)` và mong giữ nguyên 100% cấu trúc dòng trong mọi trường hợp. Hai API đặc biệt khác nhau với chuỗi rỗng và khi input kết thúc bằng nhiều delimiter. Nếu ứng dụng cần lưu chính xác một danh sách trường/record, phải định nghĩa rõ liệu dấu xuống dòng cuối có đại diện cho một trường rỗng mới hay chỉ là **dấu kết thúc dòng**.

Đối với `split`, mặc định các phần rỗng ở **giữa** vẫn được giữ; việc loại bỏ chỉ áp dụng với các phần rỗng ở **cuối** khi limit bằng 0.

## 6. Lựa chọn API theo yêu cầu thực tế

| Nhu cầu | Cách nên cân nhắc | Lý do |
| --- | --- | --- |
| Đọc các dòng trong một chuỗi, lọc và lấy vài dòng đầu | `text.lines().filter(...).limit(n)` | Stream lười, `limit` cho phép dừng duyệt khi đã đủ |
| Lấy toàn bộ các dòng LF/CR/CRLF thành `List` | `text.lines().toList()` | Dễ nối tiếp `map`/`filter`, xử lý theo dòng |
| Cần `String[]` của các phần phân cách bằng Unicode newline, bỏ rỗng cuối | `text.split("\\R")` | Regex phân tách, `limit=0` mặc định |
| Cần giữ trường rỗng ở cuối của dữ liệu delimiter | `text.split("\\R", -1)` | Bảo toàn vị trí phần tử trống sau delimiter cuối |
| Cần chia một lần để lấy header và phần còn lại | `text.split("\\R", 2)` | Phần tử cuối giữ nguyên dữ liệu chưa tách |
| Cần giữ mọi ký tự, không muốn hiểu regex | Chọn API literal phù hợp hoặc xử lý chỉ số trực tiếp | `split` nhận regex; phải escape delimiter đặc biệt |

**Lưu ý về hiệu năng:** `String.lines()` thường phù hợp hơn khi cần pipeline Stream và có thể dừng sớm. `split` trả mảng nên tạo các phần kết quả trước khi caller xử lý. Với input nhỏ hoặc khi cần đầy đủ mọi phần, hãy chọn theo semantics và kiểm chứng bằng benchmark nếu hiệu năng thật sự quan trọng. Tránh khẳng định Stream luôn nhanh hơn.

**Lưu ý về phạm vi:** Cả hai API đang thao tác trên một `String` **đã có trong bộ nhớ**; `String.lines()` không tự đọc dữ liệu từ file hay mạng. Khi xử lý file rất lớn, `Files.lines(path)` (trả Stream đọc từ file) là API khác, với yêu cầu quản lý tài nguyên riêng.

## 7. Bài tập tự kiểm tra

**Bài 1: Dự đoán số phần tử.** Với `String input = "\n\n";`, xét:

```java
System.out.println(input.lines().count());
System.out.println(input.split("\\R", 0).length);
System.out.println(input.split("\\R", -1).length);
```

Đáp án tương ứng là **2, 0, 3**. Hai dấu xuống dòng kết thúc hai dòng rỗng; `split` với limit 0 bỏ tất cả chuỗi rỗng cuối, còn limit âm giữ ba phần rỗng trước, giữa và sau hai delimiter.

**Bài 2: Chỉ cần hai dòng hợp lệ đầu tiên.** Với `"\nalpha\n\nbeta\ngamma"`, viết:

```java
List<String> result = "\nalpha\n\nbeta\ngamma"
        .lines()
        .filter(s -> !s.isBlank())
        .limit(2)
        .toList();
System.out.println(result); // [alpha, beta]
```

Nếu chuyển `limit(2)` lên trước `filter`, kết quả chỉ còn `[alpha]`, vì chỉ xét hai dòng nguồn đầu.

**Bài 3: Giữ nguyên phần nội dung sau dòng tiêu đề.** Với `"HEADER\nbody line 1\nbody line 2"`, dùng:

```java
String[] parts = "HEADER\nbody line 1\nbody line 2"
        .split("\\R", 2);
System.out.println(parts[0]); // HEADER
System.out.println(parts[1]); // in hai dòng body, còn dấu \n giữa chúng
```

`split("\\R", 2)` phù hợp vì phần tử thứ hai giữ nguyên `"body line 1\nbody line 2"`. Nếu dùng `lines().limit(2)` sẽ mất dòng body thứ hai.

**Bài 4: Input rỗng.** Giải thích vì sao `"".lines().count()` bằng 0 nhưng `"".split("\\R").length` bằng 1: `lines` định nghĩa **dòng**, còn `split` khi không có delimiter khớp sẽ trả lại **toàn bộ input** làm một token, kể cả khi token đó là `""`.

## 8. Ghi nhớ nhanh

`String.lines()` là công cụ xử lý **dòng LF/CR/CRLF bằng Stream lười**, thích hợp cho pipeline và lấy một số dòng đầu. `String.split(regex, limit)` là công cụ **tách theo regex thành mảng**; `limit=0` bỏ trường rỗng cuối, `limit<0` giữ trường rỗng cuối, `limit>0` giới hạn số lần tách và giữ phần dư ở token cuối. `Stream.limit(n)` giới hạn **số dòng được phát ra**; nó không mang ý nghĩa `split(..., n)`. Hãy lựa chọn theo **dữ liệu rỗng cần giữ**, **loại newline thực tế**, **kiểu trả về** và **cách dùng phần dữ liệu còn lại**.

**Tài liệu chính thức:** [Java SE 17 — String.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#lines()), [Java SE 17 — String.split(String, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#split(java.lang.String,int)), [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
