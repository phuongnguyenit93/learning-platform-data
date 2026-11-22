# Scanner trong Java: nguồn dữ liệu, delimiter và token

## 1. Scanner giải quyết vấn đề gì?

Khi nhận một đoạn văn bản như `"Lan 21 8.5"`, ứng dụng thường không chỉ muốn đọc từng ký tự: nó muốn lấy **tên**, **tuổi** và **điểm**. `java.util.Scanner` giúp chia đầu vào thành các **token** (đơn vị văn bản) theo quy tắc phân cách, rồi đọc token dưới dạng `String` hoặc chuyển thành các kiểu dữ liệu như `int`, `double` và `boolean`.

Ví dụ dữ liệu:

~~~text
Lan 21 8.5
~~~

Nếu dùng dấu trắng làm ký tự phân cách, luồng token nhận được là:

~~~text
Nguồn:    L a n [space] 2 1 [space] 8 . 5
                   │               │
                   ▼               ▼
Token 1: "Lan"  Token 2: "21"  Token 3: "8.5"
~~~

`Scanner` không chỉ nhận chuỗi trong bộ nhớ; nó còn có thể đọc nội dung từ tệp, `InputStream`, `Readable` và những nguồn được API hỗ trợ. Khi dùng Scanner trên I/O thực, việc tìm token **có thể chặn** trong lúc chờ đủ dữ liệu hoặc dấu phân cách.

Bài này tập trung vào ba câu hỏi có quan hệ trực tiếp:

1. **Nguồn dữ liệu** của `Scanner` là gì, được giải mã thành ký tự ra sao và ai phải đóng tài nguyên?
2. **Delimiter** (biểu thức phân cách) xác định ranh giới giữa những phần nào và được hiểu theo quy tắc regex nào?
3. **Token** được nhận diện, kiểm tra và tiêu thụ ra sao? Khi nào nên đọc token, khi nào nên đọc nguyên dòng?

Điểm cần ghi nhớ trước tiên: **Scanner là bộ phân tích văn bản theo token**. Nó không phải công cụ mặc định cho mọi định dạng tệp hay mọi giao thức dữ liệu.

## 2. Mô hình Scanner: nguồn → giải mã → phân cách → token → giá trị

~~~text
Nguồn
  ├─ String trong bộ nhớ
  ├─ Reader đã tạo sẵn
  ├─ InputStream (byte) + charset
  └─ tệp Path/File + charset
            │
            ▼
  Văn bản đã được đọc/giải mã
            │
            ▼
  Quy tắc delimiter (Pattern / regex)
            │
            ▼
  Chuỗi các token:  "Lan" | "21" | "8.5"
            │
            ├─ next()       → String
            ├─ nextInt()    → int, nếu hợp lệ
            ├─ nextDouble() → double, nếu hợp lệ theo Locale
            └─ next(...)    → String khớp mẫu được yêu cầu
~~~

Không nên trộn lẫn các tầng này:

- **Nguồn** cho biết dữ liệu nằm ở đâu và cách nó được cung cấp.
- **Charset** cho biết byte của nguồn được chuyển thành ký tự bằng quy tắc nào, khi nguồn là byte.
- **Delimiter** cho biết vị trí tách token trong chuỗi ký tự đã đọc.
- **Kiểu dữ liệu đích** cho biết token được diễn giải thành số, boolean hay văn bản.

Thay đổi delimiter **không đổi charset**; thay đổi `Locale` của Scanner để đọc số **không đổi charset**. Chẳng hạn UTF-8 quyết định cách đọc chữ “Đà Nẵng” từ byte; `Locale.GERMANY` quyết định `nextDouble()` hiểu dấu phẩy thập phân trong `"3,5"` thế nào.

## 3. Nguồn dữ liệu của Scanner

### 3.1. Chuỗi String: học và kiểm thử không cần I/O

`new Scanner(String source)` tạo Scanner đọc từ nội dung chuỗi có sẵn. Đây là lựa chọn tốt để thử delimiter và quy tắc token vì dữ liệu xác định và không phụ thuộc tệp.

**Ví dụ chạy độc lập**, lưu thành `ScannerStringDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerStringDemo {
    public static void main(String[] args) {
        String source = "  Java\t17\nI/O  ";

        try (Scanner scanner = new Scanner(source)) {
            while (scanner.hasNext()) {
                System.out.println("[" + scanner.next() + "]");
            }
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ScannerStringDemo.java
java ScannerStringDemo
~~~

Kết quả:

~~~text
[Java]
[17]
[I/O]
~~~

Scanner mặc định dùng **khoảng trắng** làm delimiter, bao gồm dấu cách, tab và xuống dòng được nhận diện theo quy tắc khoảng trắng của Java. Nó bỏ qua các delimiter trước token nên không tạo token cho từng khoảng trắng liên tiếp trong ví dụ trên.

### 3.2. Từ InputStream: byte phải được giải mã

Một `InputStream` cung cấp byte, trong khi Scanner xử lý ký tự. Nên chỉ định charset rõ ràng:

~~~java
Scanner scanner = new Scanner(inputStream, StandardCharsets.UTF_8);
~~~

Đây là **đoạn mã minh họa**, với `inputStream` đã được mở; các import cần thiết là `java.util.Scanner` và `java.nio.charset.StandardCharsets`. API nhận `Charset` có trên Java 17. Lớp nguồn có thể là `FileInputStream` hoặc một nguồn byte khác. Cần xác định bên nào có quyền đóng `inputStream` trước khi đóng Scanner.

Nếu không chọn charset rõ ràng, việc giải mã có thể phụ thuộc cấu hình môi trường/API phiên bản Java. Với dữ liệu truyền giữa nhiều máy, hãy sử dụng charset được định dạng dữ liệu quy định, thường là UTF-8.

### 3.3. Từ Reader: nhận ký tự đã giải mã

`new Scanner(Reader)` phù hợp nếu phần khác đã tạo một `Reader` hoặc cần gắn Scanner vào chuỗi wrapper I/O:

~~~java
Scanner scanner = new Scanner(reader);
~~~

Đây là đoạn minh họa với `reader` đã có. Nếu `reader` được tạo bằng `Files.newBufferedReader(path, UTF_8)`, việc chuyển byte sang ký tự đã nằm ở Reader. Scanner sẽ dùng delimiter trên **ký tự đã nhận**, chứ không dùng regex trên byte UTF-8.

### 3.4. Từ Path/File: chọn charset và xử lý vòng đời

Có thể tạo Scanner từ `Path` cùng `Charset`:

~~~java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    while (scanner.hasNext()) {
        String token = scanner.next();
        // Xử lý token.
    }
}
~~~

Đây là đoạn minh họa: `path` có kiểu `java.nio.file.Path`; phương thức bao ngoài phải khai báo hoặc xử lý ngoại lệ I/O phù hợp. Lớp `Scanner` mở tài nguyên tệp và `try-with-resources` đóng nó khi kết thúc.

Một cách khác cũng hợp lệ là:

~~~java
try (Scanner scanner = new Scanner(
        Files.newBufferedReader(path, StandardCharsets.UTF_8))) {
    // Đọc dữ liệu.
}
~~~

Các đoạn trên cần import `java.util.Scanner`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`. Khi Scanner đóng, nếu nguồn triển khai `Closeable` thì Scanner sẽ đóng nguồn đó; vì vậy không được vô tình đóng một Reader hay InputStream mà bên khác còn sở hữu.

### 3.5. Từ System.in: luồng dùng chung của tiến trình

Đọc nhập liệu ở console có thể dùng:

~~~java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
~~~

Nếu chương trình dòng lệnh dùng `System.in` trong suốt vòng đời, có thể giữ Scanner tương ứng trong suốt phiên làm việc. **Đóng Scanner sẽ đóng `System.in`** vì nguồn là một `InputStream` có thể đóng; một thư viện hoặc một hàm ngắn không nên tự đóng tài nguyên chia sẻ này nếu phần khác còn cần nhập liệu.

Quy tắc sở hữu tổng quát: phần tạo nguồn và trao quyền sở hữu cho Scanner có thể để Scanner đóng; nếu chỉ mượn nguồn từ bên gọi, hãy công bố rõ quy ước đóng hoặc dùng API khác để tránh đóng ngoài ý muốn.

## 4. Delimiter là gì?

Delimiter là **mẫu biểu thức chính quy (regular expression, regex)** dùng để chỉ ra những đoạn văn bản ngăn cách token. Ban đầu Scanner dùng một mẫu nhận diện khoảng trắng.

Giả sử đầu vào:

~~~text
An, Bình; Chi
~~~

Với delimiter mặc định, khoảng trắng mới được coi là ranh giới, vì vậy có thể xuất hiện token `"An,"`, `"Bình;"` và `"Chi"`. Dấu phẩy, chấm phẩy vẫn nằm trong token.

Nếu muốn cả dấu phẩy và chấm phẩy phân cách tên, cần đổi delimiter, ví dụ `\\s*[,;]\\s*`:

- `[,;]`: khớp **một** dấu phẩy hoặc dấu chấm phẩy.
- `\\s*`: khớp **không hoặc nhiều** ký tự trắng ở hai bên dấu phân cách.
- Mẫu này tách các tên bằng một dấu phẩy hoặc dấu chấm phẩy, có thể kèm khoảng trắng.

Trong **chuỗi Java**, ký tự backslash của regex phải được escape. Chuỗi Java dùng cho regex `\s*` ở đây cần viết `"\\s*"` (hai dấu backslash trong mã Java trước `s`). Cẩn thận: từ Java 15, escape `\s` trong Java string literal mang nghĩa một dấu cách, vì vậy viết `"\s*"` không tương đương với regex whitespace `"\\s*"`.

### 4.1. Thay delimiter bằng useDelimiter

Lưu thành `ScannerDelimiterDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerDelimiterDemo {
    public static void main(String[] args) {
        String source = "An, Bình; Chi";

        try (Scanner scanner = new Scanner(source)) {
            scanner.useDelimiter("\\s*[,;]\\s*");

            while (scanner.hasNext()) {
                System.out.println("<" + scanner.next() + ">");
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerDelimiterDemo.java
java ScannerDelimiterDemo
~~~

Kết quả:

~~~text
<An>
<Bình>
<Chi>
~~~

`useDelimiter(String pattern)` biên dịch chuỗi thành mẫu regex. Có thể dùng `useDelimiter(Pattern)` khi đã có một `java.util.regex.Pattern` biên dịch sẵn. `scanner.delimiter()` trả về mẫu delimiter đang được sử dụng.

Một delimiter không nhất thiết là **một ký tự đơn**: nó có thể là dấu phân cách dài (ví dụ `"::"`), nhiều dấu liên tiếp, hoặc một cấu trúc khớp regex. Tuy nhiên càng phức tạp thì càng phải tính đến các ký tự đặc biệt của regex và trường hợp khớp chuỗi rỗng.

### 4.2. Regex có ký tự đặc biệt

Một số dấu trong regex có ý nghĩa riêng:

| Muốn phân cách theo | Regex cần dùng | Chuỗi Java truyền cho useDelimiter |
| --- | --- | --- |
| Dấu phẩy | `,` | `","` |
| Dấu chấm phẩy | `;` | `";"` |
| Dấu chấm thật | `\\.` | `"\\."` |
| Dấu gạch đứng thật | `\\|` | `"\\|"` |
| Một hoặc nhiều dấu trắng | `\\s+` | `"\\s+"` |
| Dấu phẩy hoặc chấm phẩy, có dấu trắng quanh | `\\s*[,;]\\s*` | `"\\s*[,;]\\s*"` |

Dấu `.` chưa escape có nghĩa “một ký tự bất kỳ” trong đa số chế độ regex; dấu `|` chưa escape biểu thị phép lựa chọn. Vì vậy `useDelimiter(".")` hoặc `useDelimiter("|")` thường không mang nghĩa “ngắt ở dấu chấm/dấu gạch đứng như văn bản”.

Nếu delimiter là một chuỗi ký tự **literal** đến từ cấu hình, có thể dùng `Pattern.quote(delimiter)` để tránh vô tình coi nó như regex:

~~~java
String separator = "|";
scanner.useDelimiter(java.util.regex.Pattern.quote(separator));
~~~

Đây là đoạn mã minh họa khi `scanner` đã tồn tại. `Pattern.quote` giúp biểu diễn đúng **chuỗi delimiter cố định**; với một quy tắc regex được thiết kế chủ đích, truyền chính mẫu regex.

### 4.3. Delimiter rỗng hoặc có thể khớp độ dài 0

Regex như `""`, `"\\s*"` hoặc lookaround có thể khớp tại vị trí rỗng. Những mẫu như thế có thể tạo token khác dự kiến, thậm chí từng ký tự trở thành một token, và làm quá trình phân tích khó dự đoán.

Nếu muốn phân cách bằng **ít nhất một** khoảng trắng, dùng `"\\s+"` thay vì `"\\s*"`. Chỉ dùng regex có thể khớp rỗng khi đã hiểu quy tắc Scanner và có kiểm thử cho chuỗi đầu/cuối, delimiter lặp, Unicode và dữ liệu rỗng.

## 5. Token là gì và Scanner tiêu thụ token như thế nào?

Với một delimiter nhất định, token về cơ bản là **đoạn văn bản giữa các phần khớp delimiter** được Scanner phát hiện. `next()` lấy token kế tiếp và **dịch vị trí đọc**. `hasNext()` kiểm tra xem có token tiếp theo hay không nhưng **không tiêu thụ** token.

Ví dụ:

~~~java
try (Scanner scanner = new Scanner("red blue")) {
    System.out.println(scanner.hasNext());
    System.out.println(scanner.hasNext());
    System.out.println(scanner.next());
    System.out.println(scanner.next());
    System.out.println(scanner.hasNext());
}
~~~

Đây là ví dụ nhỏ chạy được bên trong một phương thức khai báo `throws Exception` hoặc phù hợp ngữ cảnh Java hỗ trợ `try-with-resources`. Khi cần chạy độc lập, đặt vào một lớp có `main` và `import java.util.Scanner`.

Kết quả:

~~~text
true
true
red
blue
false
~~~

Hai lần `hasNext()` đầu tiên đều thấy cùng token `red`; chỉ `next()` mới lấy token và tiến vị trí.

Không được gọi `next()` tùy tiện khi nguồn đã hết: nó ném `NoSuchElementException`. `hasNext()` có thể chặn khi Scanner đang chờ thêm đầu vào từ nguồn sống. Một vòng lặp phổ biến:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
    // Xử lý token.
}
~~~

Đây là đoạn mã minh họa với `scanner` đã có. Mỗi vòng lặp tiêu thụ đúng một token. Nếu bỏ `scanner.next()` mà chỉ lặp `hasNext()`, chương trình có thể không tiến triển.

### 5.1. hasNext(Pattern) và next(Pattern)

`hasNext(pattern)` kiểm tra token kế tiếp có khớp mẫu được chỉ định không và không tiêu thụ. `next(pattern)` lấy token kế tiếp nếu khớp; nếu không khớp, ném `InputMismatchException`.

Mẫu trong `next(Pattern)` / `hasNext(Pattern)` được áp dụng cho **toàn bộ token** theo hợp đồng matching của Scanner, không đơn giản là tìm một chuỗi con tùy ý.

Ví dụ:

~~~java
scanner.hasNext("[A-Za-z]+"); // Token kế tiếp gồm các chữ cái ASCII?
scanner.hasNext("\\d+");      // Token kế tiếp gồm một hay nhiều chữ số?
~~~

Đây là đoạn minh họa. Với token `"id42"`, cả hai biểu thức trên đều không khớp toàn bộ token. Nếu cần tìm một đoạn văn bản nằm **bên trong** dòng, xem các phương thức tìm kiếm như `findInLine` hoặc dùng `Matcher` trên một `String` đã đọc; không ép `next(regex)` làm việc của công cụ tìm chuỗi con.

### 5.2. Token không phải dòng

Delimiter mặc định nhận diện xuống dòng như khoảng trắng nên hai dòng:

~~~text
Hoa 18
Nam 20
~~~

có thể thành bốn token `Hoa`, `18`, `Nam`, `20`. Scanner không tự giữ thông tin rằng hai token đầu thuộc dòng thứ nhất nếu ứng dụng chỉ dùng `next()`.

Khi ranh giới **dòng** mang ý nghĩa nghiệp vụ, cân nhắc `hasNextLine()` / `nextLine()` và sau đó phân tích từng dòng riêng, hoặc dùng `BufferedReader`. Đừng giả định cứ hai token là một dòng nếu nguồn có thể có cột trống, dấu nháy hoặc cấu trúc phức tạp.

## 6. Quan hệ giữa next() và nextLine(): lỗi rất thường gặp

`next()` đọc token theo delimiter đang thiết lập. `nextInt()`, `nextDouble()` cũng đọc một token và phân tích giá trị. `nextLine()` thì khác: nó lấy phần còn lại của **dòng hiện tại**, không bao gồm dấu kết thúc dòng, và đưa vị trí Scanner sang dòng kế tiếp.

Sau `nextInt()`, dấu xuống dòng cuối dòng có thể vẫn chưa được `nextLine()` tiêu thụ. Nếu gọi `nextLine()` ngay, bạn thường nhận được **chuỗi rỗng** khi phía sau số không còn ký tự nào trước dấu xuống dòng.

Ví dụ chạy độc lập: `ScannerLinePitfallDemo.java`

~~~java
import java.util.Scanner;

public class ScannerLinePitfallDemo {
    public static void main(String[] args) {
        String input = "42\nNguyen Van A\n";

        try (Scanner scanner = new Scanner(input)) {
            int age = scanner.nextInt();
            String restOfNumberLine = scanner.nextLine();
            String name = scanner.nextLine();

            System.out.println("Age: " + age);
            System.out.println("Remaining chars: " + restOfNumberLine.length());
            System.out.println("Name: " + name);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerLinePitfallDemo.java
java ScannerLinePitfallDemo
~~~

Kết quả:

~~~text
Age: 42
Remaining chars: 0
Name: Nguyen Van A
~~~

Với đầu vào mà sau số có ký tự khác trên **cùng dòng**, `nextLine()` sẽ lấy các ký tự còn lại chứ không nhất thiết trả chuỗi rỗng. Không nên gọi `nextLine()` “để xóa bộ đệm” một cách máy móc: lời gọi đó **tiêu thụ phần còn lại của dòng** và có thể bỏ dữ liệu hữu ích.

Hai chiến lược rõ ràng:

- **Bài toán token:** dùng đồng nhất `hasNext`/`next`/`nextInt` khi định dạng thực sự chia thành token.
- **Bài toán biểu mẫu theo dòng:** dùng `nextLine()` lấy từng dòng, rồi chuyển kiểu bằng `Integer.parseInt(line.strip())` hoặc tạo Scanner riêng cho mỗi dòng. Cách này làm ranh giới dòng rõ ràng.

Một trường hợp dễ nhầm khác: `scanner.useDelimiter(",")` đổi token separator thành dấu phẩy, nhưng `nextLine()` vẫn tìm ranh giới dòng theo hợp đồng của nó; nó **không biến thành “đọc đến dấu phẩy”**.

## 7. Đọc số: delimiter và Locale là hai quy tắc khác nhau

`nextInt()`, `nextLong()`, `nextDouble()` và các phương thức tương tự làm hai bước:

1. Xác định **token** bằng delimiter.
2. Diễn giải **nội dung token** theo ngữ pháp kiểu dữ liệu, radix/`Locale` thích hợp.

Dấu thập phân và dấu phân nhóm chữ số có thể phụ thuộc `Locale`. Vì thế, token `"3,5"` có thể đại diện cho `3.5` theo quy tắc một locale và không hợp lệ hoặc mang nghĩa khác ở locale khác. Đặt `Locale` rõ ràng với định dạng số cố định.

Ví dụ chạy độc lập, `ScannerLocaleDemo.java`:

~~~java
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleDemo {
    public static void main(String[] args) {
        try (Scanner scanner =
                     new Scanner("17 3,5 yes").useLocale(Locale.GERMANY)) {
            int count = scanner.nextInt();
            double value = scanner.nextDouble();
            String flag = scanner.next();

            System.out.println("Count: " + count);
            System.out.println("Value: " + value);
            System.out.println("Flag: " + flag);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerLocaleDemo.java
java ScannerLocaleDemo
~~~

Kết quả:

~~~text
Count: 17
Value: 3.5
Flag: yes
~~~

`Scanner` đọc `3,5` theo `Locale.GERMANY` thành giá trị double `3.5`. Khi in bằng `System.out.println(double)`, Java dùng biểu diễn chuỗi số thông thường với dấu chấm; việc in số bằng `println` không tự kế thừa locale của Scanner.

### 7.1. Ví dụ có dấu phẩy phân cách và dấu phẩy thập phân

Giả sử định dạng có token phân cách bằng dấu phẩy, đồng thời một giá trị số cũng chứa dấu phẩy thập phân theo locale. Không thể dùng `useDelimiter(",")` rồi kỳ vọng Scanner tự biết dấu phẩy nào là dấu tách cột và dấu phẩy nào thuộc số.

**Delimiter giải quyết ranh giới token; Locale giải quyết ý nghĩa của token đã có**. Nếu hai quy tắc dùng cùng ký hiệu, cần một định dạng có quy tắc trích dẫn/escape rõ ràng (chẳng hạn định dạng CSV chuẩn) hoặc chọn ký hiệu phân cách khác. Scanner với một regex delimiter đơn giản không phải một bộ phân tích CSV đầy đủ.

### 7.2. hasNextInt() không tiêu thụ token lỗi

Khi `hasNextInt()` trả về `false`, token kế tiếp vẫn đang chờ. Nếu chỉ lặp kiểm tra mà không xử lý/tiêu thụ nó, chương trình không tiến triển.

Ví dụ `ScannerValidationDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerValidationDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("12 wrong 34")) {
            while (scanner.hasNext()) {
                if (scanner.hasNextInt()) {
                    System.out.println("Number: " + scanner.nextInt());
                } else {
                    System.out.println("Skipped: " + scanner.next());
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerValidationDemo.java
java ScannerValidationDemo
~~~

Kết quả:

~~~text
Number: 12
Skipped: wrong
Number: 34
~~~

Hàm `hasNextInt()` kiểm tra cú pháp và giới hạn của `int` theo ngữ pháp Scanner. Nếu token không phù hợp, `nextInt()` ném `InputMismatchException`; token gây lỗi **không tự được loại bỏ**. Trong ứng dụng thực, tùy yêu cầu bạn có thể dừng để báo lỗi có ngữ cảnh hoặc tiêu thụ token lỗi để phục hồi.

## 8. Dấu phân cách có thể làm thay đổi hoàn toàn token

Xét chuỗi:

~~~text
A|B C|D
~~~

Các thiết lập dẫn đến phân tích khác nhau:

| Delimiter | Token được phát hiện |
| --- | --- |
| Mặc định (khoảng trắng) | `A|B`, `C|D` |
| `"\\|"` | `A`, `B C`, `D` |
| `"[\\s|]+"` | `A`, `B`, `C`, `D` |

Vì dấu `|` là ký tự đặc biệt của regex, muốn phân cách theo dấu gạch đứng cần escape như `"\\|"` hoặc dùng lớp ký tự `"[|]"`. Ở mẫu `"[\\s|]+"`, dấu `|` bên trong lớp ký tự có nghĩa literal.

**Không được tự động bỏ khoảng trắng** khi khoảng trắng là một phần có ý nghĩa của token. Ví dụ `"Hà Nội|Việt Nam"` với delimiter dấu gạch đứng nên có hai token `"Hà Nội"` và `"Việt Nam"`; thêm `\\s+` vào delimiter có thể biến chúng thành bốn token ngoài ý muốn.

### 8.1. Token rỗng, delimiter liên tiếp và dấu nháy

Một mẫu regex tách đơn giản không đủ để biểu diễn mọi định dạng có trường rỗng hoặc trích dẫn. Với dữ liệu:

~~~text
a,,c
~~~

có thể cần hiểu có ba trường, trong đó trường thứ hai rỗng. Nhưng yêu cầu giữ chính xác trường rỗng **không nên phó mặc** cho logic token hóa thông thường nếu chưa kiểm tra hành vi delimiter và các ranh giới đầu/cuối. Với chuỗi trong bộ nhớ và dấu phân cách đơn giản, `String.split(",", -1)` là một phương án giữ cả trường rỗng cuối khi thật sự cần phân tích trường.

Với dữ liệu CSV như:

~~~text
"Nguyễn, An",21,"Hà Nội"
~~~

dấu phẩy nằm trong cặp dấu nháy của tên **không phải dấu phân cách cột**. `scanner.useDelimiter(",")` sẽ cắt sai. CSV còn có quy tắc escape dấu nháy, xuống dòng trong ô và nhiều trường hợp khác. Khi yêu cầu đúng theo CSV, hãy dùng parser chuyên dụng tuân thủ định dạng thay vì một regex đơn lẻ.

## 9. Phân tích token theo mẫu dữ liệu

`next(String pattern)` và `next(Pattern pattern)` chỉ lấy token kế tiếp nếu khớp mẫu; chúng có thể hữu ích khi dữ liệu có cấu trúc token rõ ràng.

Ví dụ `ScannerPatternDemo.java`:

~~~java
import java.util.Scanner;

public class ScannerPatternDemo {
    public static void main(String[] args) {
        try (Scanner scanner = new Scanner("abc 123 x9")) {
            while (scanner.hasNext()) {
                if (scanner.hasNext("[A-Za-z]+")) {
                    System.out.println("WORD: " + scanner.next());
                } else if (scanner.hasNext("\\d+")) {
                    System.out.println("NUMBER: " + scanner.next());
                } else {
                    System.out.println("OTHER: " + scanner.next());
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerPatternDemo.java
java ScannerPatternDemo
~~~

Kết quả:

~~~text
WORD: abc
NUMBER: 123
OTHER: x9
~~~

Mẫu `"[A-Za-z]+"` chỉ nhận chữ ASCII; nếu dữ liệu có chữ tiếng Việt, cần mẫu Unicode thích hợp, chẳng hạn dùng nhóm ký tự `\\p{L}+` cho các ký tự Unicode thuộc nhóm Letter. Nếu cần nhận cả dấu kết hợp, định nghĩa “từ” phải xét thêm ký tự đánh dấu và yêu cầu nghiệp vụ.

Đừng dùng `hasNext("[A-Za-z]+")` để xác định mọi tên người hợp lệ; tên thật có khoảng trắng, dấu, dấu nối và nhiều dạng chữ viết. Mẫu chỉ là minh họa phân loại token.

## 10. Quy tắc đọc theo từng dòng rồi token hóa từng dòng

Dữ liệu có cấu trúc **mỗi dòng là một bản ghi** thường an toàn hơn khi ứng dụng giữ nguyên ranh giới dòng:

~~~text
Lan;21;Ha Noi
Minh;22;Da Nang
~~~

Có thể dùng Scanner ngoài để đọc dòng, Scanner trong để phân tích token của từng dòng:

~~~java
try (Scanner lines = new Scanner(text)) {
    while (lines.hasNextLine()) {
        String line = lines.nextLine();
        try (Scanner fields = new Scanner(line).useDelimiter(";")) {
            // Đọc các trường từ một dòng.
        }
    }
}
~~~

Đây là **đoạn minh họa**, biến `text` có kiểu `String`. Nó phù hợp với định dạng đơn giản không có dấu phân cách nằm trong trường và không có trường rỗng đặc biệt. Nó cũng cho phép chỉ rõ số dòng khi báo lỗi. Nếu dữ liệu cho phép trường rỗng, dấu phân cách được escape, trường đặt trong dấu nháy hoặc chứa xuống dòng, cần parser theo đúng định dạng đó.

### 10.1. Đừng trộn không kiểm soát nextLine với hasNext

Hai kiểu lặp khác nhau có hợp đồng khác nhau:

~~~java
while (scanner.hasNext()) {
    String token = scanner.next();
}
~~~

Lặp này kết thúc khi không còn **token** theo delimiter.

~~~java
while (scanner.hasNextLine()) {
    String line = scanner.nextLine();
}
~~~

Lặp này kết thúc khi không còn **dòng** để đọc. Với dòng rỗng hoặc nhiều dấu phân cách liên tiếp, số dòng không bằng số token. Nếu bài toán cần bảo toàn dòng trắng, chỉ lặp theo token sẽ bỏ qua thông tin đó.

## 11. Lỗi và ngoại lệ cần xử lý

Các phương thức của Scanner có những tình huống lỗi đáng chú ý:

| Tình huống | Hành vi điển hình | Cách xử lý |
| --- | --- | --- |
| `next()` khi không có token | `NoSuchElementException` | Kiểm tra `hasNext()` hoặc quản lý EOF |
| `nextInt()` gặp token không phải số nguyên hợp lệ hoặc vượt khoảng `int` | `InputMismatchException` | Kiểm tra `hasNextInt()` hoặc bắt lỗi và xử lý token |
| Gọi phương thức trên Scanner đã đóng | `IllegalStateException` | Dừng dùng sau `close()`; quản lý quyền sở hữu |
| Regex delimiter không hợp lệ | `PatternSyntaxException` | Kiểm thử regex hoặc dùng `Pattern.quote` cho literal |
| Mở tệp thất bại | Ngoại lệ I/O khi tạo nguồn/Scanner | Kiểm tra đường dẫn, quyền, charset và xử lý lỗi |
| Reader bên dưới ném `IOException` trong lúc Scanner đang đọc | Scanner coi như kết thúc nguồn ở tầng token hóa; lưu lỗi | Kiểm tra `scanner.ioException()` khi cần phân biệt lỗi I/O với EOF |

Một điểm quan trọng: Scanner được thiết kế thuận tiện cho phân tích văn bản, nên có thể **không ném trực tiếp `IOException` phát sinh trong lúc đọc từ `Readable`**. API `scanner.ioException()` cho biết ngoại lệ I/O cuối cùng mà nguồn ném, nếu có. Nếu chương trình phải phân biệt “hết dữ liệu bình thường” với “đọc lỗi giữa chừng”, hãy kiểm tra trường hợp đó và chuyển lỗi lên tầng thích hợp.

Ví dụ minh họa cuối quá trình quét:

~~~java
IOException problem = scanner.ioException();
if (problem != null) {
    throw problem;
}
~~~

Đây là **đoạn minh họa**, yêu cầu `scanner` đã có, `import java.io.IOException` và phương thức bao ngoài khai báo hoặc bắt `IOException`. Với nguồn `String`, sẽ không có lỗi đọc bên ngoài để quan sát; với tệp hoặc kết nối, đây là kiểm tra có giá trị.

Không nên bắt `InputMismatchException` rồi bỏ qua để gọi lại `nextInt()` trên cùng một token: token lỗi thường vẫn nằm ở vị trí hiện tại. Muốn thử lại cần tiêu thụ hoặc thay thế token không hợp lệ, hoặc sửa nguồn theo quy tắc chương trình.

## 12. Vòng đời tài nguyên và trách nhiệm đóng

`Scanner` triển khai `Closeable`, có thể dùng trong `try-with-resources`:

~~~java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    // Quét token.
}
~~~

Khi kết thúc, Scanner tự được đóng, kể cả có ngoại lệ trong thân `try`. Nếu nguồn của Scanner triển khai `Closeable`, `Scanner.close()` sẽ đóng nguồn đó. Vì vậy, cách này là phù hợp khi Scanner **sở hữu** nguồn tệp đã mở.

Các tình huống quyền sở hữu:

- Tạo Scanner đọc từ `String`: không có handle tệp cần giải phóng, nhưng đóng Scanner vẫn có thể biểu đạt vòng đời sử dụng.
- Tạo Scanner từ `Path` hoặc mở `Reader` riêng cho một tác vụ: thông thường phần tạo phải bảo đảm tài nguyên được đóng.
- Nhận `Reader` hoặc `InputStream` của người gọi: cần thỏa thuận ai đóng, vì đóng Scanner có thể đóng nguồn đang được sử dụng chung.
- Scanner trên `System.in`: không nên đóng sớm ở một hàm nhỏ nếu các chức năng sau còn cần console input.

`Scanner` **không an toàn để nhiều thread dùng chung mà không đồng bộ bên ngoài**. Nó có trạng thái vị trí quét, delimiter, locale và buffer. Nếu nhiều phần cần phân tích dữ liệu khác nhau, nên tạo Scanner riêng cho mỗi nguồn độc lập hoặc xây dựng cơ chế điều phối có kiểm soát.

## 13. Hiệu năng: khi nào Scanner phù hợp?

Scanner tiện cho dữ liệu nhỏ hoặc vừa, công cụ dòng lệnh, bài thực hành, định dạng token đơn giản và chương trình cần chuyển kiểu trực tiếp. Nhưng nó cũng xử lý regex và nhiều quy tắc diễn giải dữ liệu, nên với lượng lớn số hoặc log, chi phí có thể cao hơn cách đọc tuyến tính chuyên biệt.

Một số lựa chọn:

| Bài toán | Gợi ý |
| --- | --- |
| Nhập dữ liệu từ console theo từ/số | Scanner với quy tắc token và locale rõ ràng |
| Tách một đoạn `String` nhỏ theo ký tự phân cách đơn giản | Scanner hoặc `String.split` tùy cần trường rỗng |
| Đọc tệp theo từng dòng, cần giữ cả dòng | `BufferedReader.readLine()` / `Files.newBufferedReader` |
| Đọc tệp văn bản rất lớn và xử lý bản ghi tuần tự | BufferedReader và parser phù hợp định dạng |
| Đọc tệp nhị phân | `InputStream` / NIO byte; không dùng Scanner |
| CSV có dấu nháy, dấu phẩy trong ô, dòng nhiều hàng | Parser CSV tuân thủ chuẩn của định dạng |
| JSON/XML | Parser JSON/XML; Scanner delimiter đơn giản không đủ |
| Token phức tạp cần Unicode/ngữ pháp riêng | Xây dựng bộ phân tích theo yêu cầu hoặc dùng thư viện chuyên dụng |

Một token cực dài mà không có delimiter phù hợp có thể khiến Scanner phải tích lũy nhiều ký tự để tìm ranh giới. Với dữ liệu đầu vào không tin cậy, cần định nghĩa giới hạn kích thước, số token, timeout/cách hủy việc đọc và quy tắc kiểm tra, tùy loại nguồn.

Không chọn delimiter regex quá phức tạp khi có cách mô tả định dạng đơn giản hơn. Một regex dễ gây backtracking nặng có thể làm việc tìm token chậm bất thường trên đầu vào dài.

## 14. Ví dụ tổng hợp: phân tích dòng dữ liệu dấu chấm phẩy với kiểm tra token

Ví dụ sau đọc một chuỗi dữ liệu gồm ba token: tên, tuổi và thành phố, phân cách bằng dấu chấm phẩy và khoảng trắng tùy chọn. Dữ liệu cố định cho phép xác minh kết quả rõ ràng.

Lưu vào **ScannerRecordDemo.java**:

~~~java
import java.util.Scanner;

public class ScannerRecordDemo {
    public static void main(String[] args) {
        String record = "Nguyễn An; 23; Hà Nội";

        try (Scanner scanner = new Scanner(record)) {
            scanner.useDelimiter("\\s*;\\s*");

            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing name");
            }
            String name = scanner.next();

            if (!scanner.hasNextInt()) {
                throw new IllegalArgumentException("Invalid age");
            }
            int age = scanner.nextInt();

            if (!scanner.hasNext()) {
                throw new IllegalArgumentException("Missing city");
            }
            String city = scanner.next();

            if (scanner.hasNext()) {
                throw new IllegalArgumentException("Unexpected extra token");
            }

            System.out.println("Name: " + name);
            System.out.println("Age: " + age);
            System.out.println("City: " + city);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScannerRecordDemo.java
java ScannerRecordDemo
~~~

Kết quả:

~~~text
Name: Nguyễn An
Age: 23
City: Hà Nội
~~~

Giải thích:

1. Delimiter chỉ là dấu chấm phẩy kèm dấu trắng quanh nó. Vì **dấu cách giữa các từ trong tên/thành phố không phải delimiter**, `"Nguyễn An"` và `"Hà Nội"` là mỗi cụm một token.
2. `hasNext()` bảo vệ các lệnh `next()` khỏi nguồn thiếu token; `hasNextInt()` xác nhận token tuổi theo ngữ pháp số nguyên.
3. `nextInt()` tiêu thụ cùng một token mà `hasNextInt()` vừa kiểm tra, vì giữa hai lời gọi không có thao tác đọc khác.
4. Kiểm tra `hasNext()` sau cùng phát hiện dữ liệu dư. Với định dạng thực tế, cần bổ sung kiểm tra độ dài, khoảng tuổi, khoảng trắng đầu/cuối, trường rỗng và các trường hợp lỗi phù hợp.
5. Scanner nhận `String` nên không cần tệp; trong hệ thống thật, cùng cách phân tích token có thể áp dụng cho Reader nhưng phải quản lý charset, I/O và quyền sở hữu.

Ví dụ này **không phải parser CSV có dấu trích dẫn**, và `hasNextInt()` phụ thuộc cấu hình locale. Khi định dạng có quy tắc cố định, hãy đặt `Locale` và chính sách xác thực tương ứng.

## 15. Những lỗi phổ biến trong ứng dụng

| Cách làm | Điều có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Dùng delimiter mặc định để đọc `"A,B,C"` | Cả chuỗi có thể là một token | `useDelimiter(",")` nếu định dạng thật sự phân cách bằng dấu phẩy |
| Dùng `useDelimiter(".")` để tách theo dấu chấm | `.` là regex đặc biệt, có thể khớp gần mọi ký tự | `useDelimiter("\\.")` hoặc `Pattern.quote(".")` |
| Gọi `nextLine()` ngay sau `nextInt()` và nghĩ luôn nhận tên | Có thể đọc phần còn lại rỗng của dòng số | Tách chiến lược token/dòng; đọc đúng dòng cần lấy |
| Trộn `next()` và `nextLine()` khi không hiểu vị trí Scanner | Dữ liệu bị bỏ qua hoặc đọc nhầm | Tài liệu hóa định dạng và kiểm thử bằng nhiều dấu xuống dòng |
| Dùng `hasNextInt()` trong vòng lặp nhưng không tiêu thụ token lỗi | Vòng lặp đứng yên | `next()` để bỏ token lỗi hoặc ném lỗi |
| Tưởng `hasNext()` luôn không chặn | Trên nguồn sống, Scanner có thể chờ dữ liệu | Thiết kế timeout/hủy đọc theo nguồn I/O |
| Dùng `useDelimiter(",")` cho CSV có dấu nháy | Cắt sai trường chứa dấu phẩy | Dùng parser CSV chuyên dụng |
| Dùng Scanner đọc nhị phân | Byte bị giải mã như ký tự văn bản | Dùng byte stream/NIO |
| Không chỉ định charset của nguồn byte | Chữ có dấu có thể hỏng | Chọn charset theo hợp đồng dữ liệu |
| Không chỉ định Locale cho số | `nextDouble()` có thể diễn giải sai | `useLocale(Locale.US)` hoặc locale quy định |
| Đóng Scanner trên `System.in` quá sớm | Phần khác không nhập liệu tiếp được | Quản lý vòng đời ở cấp ứng dụng |
| Bỏ qua `scanner.ioException()` khi nguồn đọc lỗi | Có thể nhầm lỗi I/O với EOF | Kiểm tra và báo lỗi đúng nơi |
| Chia token từ dữ liệu không tin cậy mà không giới hạn | Token/regex có thể tiêu tốn bộ nhớ và thời gian | Xác thực kích thước, token count, timeout |

## 16. Tự kiểm tra hiểu biết

**Câu 1.** Với nguồn `"A, B C"` và delimiter mặc định, có bao nhiêu token?

**Đáp án:** ba token theo khoảng trắng: `"A,"`, `"B"`, `"C"`. Dấu phẩy không tự động là delimiter.

**Câu 2.** Với nguồn `"A, B C"` và `useDelimiter("\\s*,\\s*")`, hai token là gì?

**Đáp án:** `"A"` và `"B C"`. Khoảng trắng bên trong `"B C"` được giữ vì chỉ có dấu phẩy kèm khoảng trắng mới phân cách.

**Câu 3.** `hasNext()` gọi hai lần liên tiếp có lấy mất hai token không?

**Đáp án:** không. Nó chỉ kiểm tra, không tiêu thụ token; `next()` mới dịch vị trí.

**Câu 4.** Khi `nextInt()` gặp token `"abc"`, sau khi bắt `InputMismatchException` có thể gọi ngay `nextInt()` lần nữa để đọc số kế không?

**Đáp án:** thông thường không. Token lỗi vẫn ở đó. Cần quyết định dừng báo lỗi hoặc tiêu thụ token lỗi qua `next()` trước khi tiếp tục.

**Câu 5.** `Locale.GERMANY` làm Scanner thay đổi dấu ngắt token từ khoảng trắng sang dấu phẩy phải không?

**Đáp án:** không. Locale ảnh hưởng việc diễn giải số theo quy tắc locale; delimiter được điều khiển riêng bằng `useDelimiter`.

**Câu 6.** Khi `Scanner scanner = new Scanner(System.in)` bị đóng, việc gì xảy ra?

**Đáp án:** `Scanner.close()` đóng nguồn triển khai `Closeable`, ở đây là `System.in`. Cần tránh đóng sớm nếu nhiều thành phần còn muốn dùng console input.

**Câu 7.** Vì sao không nên tự dùng dấu phẩy làm delimiter để đọc một tệp CSV tùy ý?

**Đáp án:** dấu phẩy có thể nằm trong trường trích dẫn, trường có thể rỗng hoặc chứa xuống dòng; cần parser hiểu quy tắc CSV.

### Bài tập thực hành

1. Sửa `ScannerDelimiterDemo` để nhận chuỗi `"Đà Nẵng|Hồ Chí Minh|Hà Nội"` và dùng delimiter dấu `|` literal. Kiểm tra ba địa danh có dấu cách vẫn nguyên vẹn.
2. Sửa `ScannerValidationDemo` để báo tổng các số nguyên hợp lệ và số token bị bỏ qua; kiểm tra nguồn `"2 bad 7 10"`.
3. Dùng `ScannerLinePitfallDemo` với chuỗi `"42 abc\nNguyen Van A\n"`. Quan sát phần còn lại của dòng đầu để hiểu rằng `nextLine()` không phải lời gọi chỉ “xóa ký tự xuống dòng”.
4. Tạo một tệp UTF-8 có dữ liệu `"Lan; 21; Hà Nội"`, dùng Scanner đọc qua `Path`/`Reader` và đối chiếu kết quả với nguồn String. Bổ sung xử lý thiếu tệp và xác định rõ bên đóng tài nguyên.

## 17. Ghi nhớ

- **Scanner biến đầu vào ký tự thành token** theo một delimiter regex rồi có thể diễn giải token thành kiểu dữ liệu cần đọc.
- **Nguồn là String, Reader, InputStream hoặc tệp**, và khi nguồn là byte cần chọn charset đúng. Quyền đóng Scanner có thể kéo theo đóng nguồn bên dưới.
- **Delimiter mặc định là khoảng trắng**; `useDelimiter` thay đổi quy tắc tách token, không thay đổi charset hay Locale.
- **`hasNext` kiểm tra; `next` tiêu thụ.** `hasNextInt`/`nextInt` xử lý token số, còn `nextLine` xử lý ranh giới dòng theo hợp đồng khác.
- **Regex không phải chuỗi literal**: escape `.`, `|` và những ký tự đặc biệt, hoặc dùng `Pattern.quote` cho dấu phân cách cố định.
- **Scanner phù hợp dữ liệu token tương đối đơn giản**. Với CSV có trích dẫn, JSON, XML, tệp nhị phân hoặc định dạng nghiêm ngặt, hãy dùng parser hoặc API tương ứng.

### Tài liệu tham khảo

- [Scanner — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html)
- [Pattern — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [InputStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
