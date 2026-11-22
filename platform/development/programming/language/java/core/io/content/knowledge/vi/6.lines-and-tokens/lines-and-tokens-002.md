# LF, CRLF, CR và quy ước xuống dòng trong Java

Trong file văn bản, **xuống dòng** là quy ước dùng một hoặc nhiều ký tự điều khiển để phân tách các dòng. Ba cách phổ biến nhất là **LF** (`\n`), **CRLF** (`\r\n`) và **CR** (`\r`). Cùng một nội dung hiển thị có thể được lưu bằng các dãy ký tự hoặc byte khác nhau; điều này ảnh hưởng đến đọc file, so sánh chuỗi, xử lý token, đếm dòng, truyền dữ liệu giữa hệ điều hành và tuân thủ các định dạng/giao thức yêu cầu một kiểu xuống dòng cụ thể.

Trong Java I/O, cần phân biệt hai thao tác:

- **Đọc văn bản thô:** giữ nguyên ký tự `\r` và `\n` đang hiện diện trong dữ liệu.
- **Đọc theo dòng:** nhận các chuỗi nội dung dòng; API có thể *nhận diện và loại bỏ* dấu kết thúc dòng.

Bài học làm rõ byte và ký tự tương ứng, quy ước lịch sử, hành vi của `BufferedReader`, `String.lines()`, `Files.readAllLines`, cách ghi xuống dòng có chủ đích và những lỗi xử lý thường gặp.

## 1. LF, CR, CRLF là gì?

| Tên | Escape Java | Unicode | Byte trong ASCII / UTF-8 | Dạng thập lục phân | Ý nghĩa quy ước |
|---|---|---|---|---|---|
| **LF** — Line Feed | `\n` | U+000A | Một byte `0A` | `0x0A` | Chuyển tới dòng kế tiếp |
| **CR** — Carriage Return | `\r` | U+000D | Một byte `0D` | `0x0D` | Trả vị trí về đầu dòng trong cơ chế máy đánh chữ |
| **CRLF** — Carriage Return + Line Feed | `\r\n` | U+000D rồi U+000A | Hai byte `0D 0A` | `0x0D 0x0A` | Cặp ký tự dùng làm một dấu kết thúc dòng |

Trong **UTF-8**, LF và CR vẫn là các byte đơn `0A` và `0D`. Trong UTF-16LE, cùng các code unit đó thường xuất hiện dưới dạng `0A 00` và `0D 00` ở mức byte; vì vậy không được quét byte `0A` để tìm dòng trong mọi loại mã hóa mà chưa hiểu charset. Bảng trên chỉ khẳng định giá trị byte đối với ASCII và UTF-8.

**Java xử lý CRLF gồm hai `char`**: `'\r'` và `'\n'`. Ở lớp đọc theo dòng, nhiều API coi hai `char` liền nhau là **một dấu ngắt dòng**, chứ không phải hai dòng ngắt độc lập. Điều này khác với việc chuỗi chứa hai code unit.

### Bối cảnh hệ điều hành

- **Unix/Linux** và macOS hiện đại thông thường dùng **LF** làm dấu kết thúc dòng trong file văn bản.
- **Windows** truyền thống dùng **CRLF** trong nhiều file văn bản và API/tiện ích.
- **Classic Mac OS trước macOS** từng dùng **CR**.
- Nhiều bộ soạn thảo hiện đại đọc/ghi được cả ba loại; định dạng file, giao thức mạng, ứng dụng và cấu hình mới quyết định chính xác kiểu được lưu.

Không nên giả định rằng *mọi* file được tạo trên Windows luôn có CRLF hay mọi file trên Linux chỉ có LF. Ví dụ file được tải từ Git, tạo bởi code Java ghi `"\n"`, hoặc do phần mềm bên ngoài xuất ra có thể giữ nguyên kiểu xuống dòng khác quy ước của hệ điều hành.

## 2. Dấu xuống dòng thuộc văn bản, không phải hình thức hiển thị

Hai chuỗi sau thường được hiển thị giống nhau trong trình xem văn bản:

```java
String lf = "first\nsecond";
String crlf = "first\r\nsecond";
```

Nhưng:

- `lf.length() == 12`, vì chỉ có một `char` `'\n'` ở giữa.
- `crlf.length() == 13`, vì có hai `char` `'\r'` và `'\n'` ở giữa.
- `lf.equals(crlf)` là **`false`**; mảng byte UTF-8, độ dài, checksum/hash và vị trí offset cũng khác.

Một đoạn văn bản có thể gồm các dòng `A`, `B`, `C` mà file dùng LF, CRLF, CR, hoặc **trộn cả ba**. Khi xem nội dung chỉ bằng mắt, không dễ phát hiện sự khác biệt.

Không nhầm lẫn ký tự điều khiển với hai ký tự chữ `\` và `n`. Trong mã nguồn Java, `"\n"` là **một** ký tự LF khi chạy; `"\\n"` là **hai** ký tự hiển thị `\` và `n`. Tương tự `"\r\n"` tạo hai ký tự điều khiển, còn `"\\r\\n"` chỉ là văn bản ký hiệu.

### Khái niệm line terminator, line separator và “dòng”

Đối với I/O, LF, CRLF và CR thường được gọi là **line terminators** — ký tự/cặp ký tự đánh dấu kết thúc một dòng. **Line content** là phần dữ liệu giữa các terminator. API đọc dòng như `BufferedReader.readLine()` trả lại **nội dung dòng** mà không kèm terminator.

Tùy API, `"A\n"` có thể biểu diễn **một dòng `A` có dấu kết thúc**, chứ không nhất thiết là hai dòng với dòng cuối rỗng. Phân biệt:

- **Dòng rỗng thực sự** nằm giữa hai dấu ngắt liên tiếp, hoặc là dòng trước dấu ngắt ở đầu dữ liệu.
- **Kết thúc file ngay sau dấu ngắt** thường **không sinh thêm** một dòng rỗng từ `readLine()` hoặc `String.lines()`.
- **File không có dấu ngắt cuối** vẫn có một dòng cuối nếu còn nội dung.
- **File trống** có thể được các API đếm là 0 dòng; đừng tự giả định 1 dòng.

Các tình huống này ảnh hưởng trực tiếp đến số dòng, logic parser và việc lưu lại đúng định dạng ban đầu.

## 3. Java có những cách đọc dòng nào?

### `BufferedReader.readLine()`

`BufferedReader.readLine()` chấp nhận dấu kết thúc dòng bằng **LF**, **CR** hoặc **CRLF**. Nó trả về `String` **không chứa** ký tự kết thúc dòng và trả `null` khi EOF. Dòng rỗng hợp lệ trả `""`.

Một lưu ý: ký tự CRLF liền nhau được nhìn như **một** terminator. Nếu mã nguồn Java đọc bằng `readLine()`, ứng dụng thường **không còn biết** liệu dòng cũ dùng LF, CRLF hay CR.

### `String.lines()` (Java 11+)

`"text".lines()` trả về `Stream<String>` gồm các dòng, nhận diện `\n`, `\r` hoặc `\r\n`. Các dấu ngắt bị bỏ khỏi kết quả. Stream này được xử lý theo nhu cầu và không bắt buộc chia toàn chuỗi thành một mảng ngay lập tức.

- Chuỗi `""` không có dòng: stream rỗng.
- Chuỗi `"A"` có một dòng `A`.
- Chuỗi `"A\n"` có một dòng `A`, **không tự phát sinh dòng cuối rỗng**.
- Chuỗi `"A\n\n"` có dòng `A` và một dòng rỗng.
- Chuỗi `"\n"` chứa một dòng rỗng.
- CRLF chỉ là **một** terminator dù gồm hai `char`.

`String.lines()` **không đồng nghĩa** với “tách mọi dấu ngắt dòng Unicode”: nó nhận diện đúng ba dạng được API quy định (LF, CR, CRLF), trong khi regex `\R` trong Java hỗ trợ tập line-break rộng hơn (ví dụ Unicode NEL, LS, PS).

### `Files.readAllLines` và `Files.lines`

Hai API thuộc `java.nio.file.Files` cũng nhận diện CRLF, LF và CR theo hợp đồng:

- `Files.readAllLines(path, charset)` đọc các dòng thành `List<String>`, loại dấu kết thúc dòng, **giữ toàn bộ kết quả trong bộ nhớ**.
- `Files.lines(path, charset)` tạo `Stream<String>` đọc file theo nhu cầu. Vì stream gắn với tài nguyên file, **đóng stream** trong `try-with-resources`; terminal operation như `count()` không thay thế việc đóng.
- `Files.readString(path, charset)` đọc **toàn bộ nội dung text**, bao gồm các ký tự CR/LF còn nguyên, nếu giải mã đúng; đừng dùng `readAllLines` để tạo bản sao cần giữ nguyên mọi dấu xuống dòng.

Đọc theo dòng có giá trị khi xử lý dữ liệu văn bản ở mức **dòng**; để giữ nguyên byte, dùng `Files.readAllBytes` hoặc stream byte, nhớ chọn đúng charset khi dựng lại văn bản.

## 4. Ví dụ 1 — ba quy ước trong cùng một chuỗi

Tạo tệp `LineEndingDemo.java` (Java 17+):

```java
import java.io.BufferedReader;
import java.io.StringReader;

public class LineEndingDemo {
    public static void main(String[] args) throws Exception {
        String mixed = "A\r\nB\nC\rD\r\n";

        System.out.println("raw length=" + mixed.length());
        System.out.println("String.lines count=" + mixed.lines().count());

        try (BufferedReader reader = new BufferedReader(new StringReader(mixed))) {
            String line;
            int index = 1;
            while ((line = reader.readLine()) != null) {
                System.out.println("line " + index++ + "=[" + line + "]");
            }
        }

        String normalized = mixed.replace("\r\n", "\n").replace('\r', '\n');
        System.out.println("normalized=" + normalized.replace("\n", "<LF>"));
        System.out.println("normalized length=" + normalized.length());
        System.out.println("keeps trailing LF=" + normalized.endsWith("\n"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 LineEndingDemo.java
java LineEndingDemo
```

Kết quả đã kiểm tra:

```text
raw length=10
String.lines count=4
line 1=[A]
line 2=[B]
line 3=[C]
line 4=[D]
normalized=A<LF>B<LF>C<LF>D<LF>
normalized length=8
keeps trailing LF=true
```

**Cách hiểu:**

1. Biến `mixed` chứa lần lượt CRLF, LF, CR và CRLF. Bốn dấu kết thúc dòng đó tạo ra bốn dòng mang nội dung `A`, `B`, `C`, `D`.
2. `mixed.length()` bằng `10` UTF-16 code unit: bốn chữ cái, hai ký tự LF/CR đơn (ở giữa), cộng bốn ký tự nằm trong hai cặp CRLF.
3. `BufferedReader.readLine()` nhận cả ba dạng terminator và **loại dấu kết thúc**, do đó đầu ra là bốn chuỗi không chứa `\r` hoặc `\n`.
4. Lệnh `mixed.replace("\r\n", "\n").replace('\r', '\n')` chuyển **CRLF trước**, rồi CR đơn thành LF. Kết quả `A\nB\nC\nD\n` dài `8` code unit.
5. Dấu LF cuối vẫn còn trong `normalized`. Nếu ngay sau đó gọi `normalized.lines()` thì stream vẫn chỉ có bốn dòng, không phát sinh dòng rỗng cuối.

**Thứ tự thay thế rất quan trọng:** nếu thay `\r` bằng `\n` **trước**, chuỗi CRLF trở thành `\n\n` — hai dấu xuống dòng, vô tình thêm dòng rỗng.

Việc chuẩn hóa trên chỉ thay ký tự ngắt dòng **trong chính chuỗi văn bản**. Nó không thay đổi dữ liệu gốc nếu bạn chưa ghi chuỗi mới vào file, và không tự chọn charset hay kiểu xuống dòng mà một giao thức ngoài yêu cầu.

## 5. Ví dụ 2 — byte trong file và hành vi của `Files`

Tạo tệp `FileLineEndingDemo.java` (Java 17+):

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.List;

public class FileLineEndingDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("line-ending-demo-", ".txt");
        String text = "first\nsecond\r\nthird\r";
        try {
            Files.writeString(file, text, StandardCharsets.UTF_8);
            byte[] bytes = Files.readAllBytes(file);
            System.out.println("hex=" + HexFormat.of().formatHex(bytes));
            System.out.println("raw same=" + text.equals(
                    Files.readString(file, StandardCharsets.UTF_8)));
            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            System.out.println("lines=" + lines);
            System.out.println("line count=" + lines.size());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileLineEndingDemo.java
java FileLineEndingDemo
```

```text
hex=66697273740a7365636f6e640d0a74686972640d
raw same=true
lines=[first, second, third]
line count=3
```

Đầu ra hex cho thấy:

- Chữ `first` tiếp theo là `0A`, tức LF.
- Chữ `second` tiếp theo là `0D0A`, tức CRLF.
- Chữ `third` tiếp theo là `0D`, tức CR.
- Không có byte hay dòng nội dung nào được Java ngầm đổi khi `Files.writeString` nhận chuỗi có dấu ngắt được ghi rõ.

`Files.readString` giữ nguyên thứ tự dấu kết thúc dòng trong văn bản giải mã; do đó `raw same=true`. Trong khi đó `Files.readAllLines` **bỏ terminator**, chỉ trả ba dòng. Nếu nối danh sách dòng lại bằng dấu phân cách tự chọn, kết quả có thể hiển thị giống nhưng **không khôi phục nguyên vẹn file ban đầu**.

Ví dụ chỉ dùng dữ liệu ASCII nên UTF-8 biểu diễn từng ký tự thành một byte. Với tiếng Việt, các ký tự ngoài ASCII có thể chiếm nhiều byte; LF/CR vẫn là các giá trị U+000A/U+000D ở tầng Unicode, nhưng lúc kiểm tra byte cần xét charset cụ thể.

## 6. Ví dụ 3 — dòng rỗng, terminator cuối và token

Tạo tệp `EndOfLineCasesDemo.java` (Java 17+):

```java
import java.util.Arrays;
import java.util.Scanner;

public class EndOfLineCasesDemo {
    public static void main(String[] args) {
        String[] samples = {"", "A", "A\n", "A\n\n", "\n", "\r\n"};
        for (String sample : samples) {
            String escaped = sample.replace("\r", "\\r").replace("\n", "\\n");
            System.out.println("text=[" + escaped + "], lines="
                    + sample.lines().map(String::length).toList());
        }
        try (Scanner scanner = new Scanner("Ada 42\r\nLinh 7\n")) {
            System.out.println("name=" + scanner.next());
            System.out.println("age=" + scanner.nextInt());
            System.out.println("rest=[" + scanner.nextLine() + "]");
            System.out.println("next line=[" + scanner.nextLine() + "]");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EndOfLineCasesDemo.java
java EndOfLineCasesDemo
```

```text
text=[], lines=[]
text=[A], lines=[1]
text=[A\n], lines=[1]
text=[A\n\n], lines=[1, 0]
text=[\n], lines=[0]
text=[\r\n], lines=[0]
name=Ada
age=42
rest=[]
next line=[Linh 7]
```

Danh sách `lines` cố ý chứa **độ dài các dòng** thay vì in trực tiếp từng phần tử: `List.of("")` khi in cũng hiển thị `[]`, dễ nhầm với danh sách rỗng. Ở kết quả trên, `lines=[0]` là **một dòng rỗng**; `lines=[]` là **không có dòng nào**.

`Scanner` được dùng để minh họa sự khác nhau giữa **token** và **dòng**:

- `next()` lấy token `Ada`; `nextInt()` lấy token số `42`. Scanner mặc định phân tách token bằng khoảng trắng theo quy tắc `Character.isWhitespace`, nên các dấu xuống dòng là ranh giới token.
- Sau `nextInt()`, dấu kết thúc dòng CRLF chưa được `nextLine()` tiêu thụ theo cách nhiều người kỳ vọng. `nextLine()` đầu tiên nhận **phần còn lại của dòng hiện tại**, tức chuỗi rỗng `""`.
- `nextLine()` kế tiếp mới lấy dòng `Linh 7`.

Trong bài toán nhập liệu tương tác, đây là lý do phổ biến khiến `nextLine()` sau `nextInt()` tưởng như “bị bỏ qua”. Cần chủ động tiêu thụ phần còn lại của dòng nếu muốn chuyển từ thao tác token sang thao tác đọc nguyên dòng. Đừng dùng `scanner.useDelimiter("\n")` một cách tùy tiện để xử lý cả CRLF: dấu CR có thể còn sót tùy mẫu delimiter và thao tác đọc.

## 7. Ghi xuống dòng: nên dùng cách nào?

### Khi muốn dùng quy ước của môi trường chạy

- `System.lineSeparator()` trả chuỗi dấu kết thúc dòng phụ thuộc môi trường hệ thống (thông thường `"\n"` trên Linux/macOS và `"\r\n"` trên Windows).
- `BufferedWriter.newLine()` ghi dấu xuống dòng dựa vào quy ước được hệ thống xác định.
- `PrintWriter.println(...)` và `System.out.println(...)` ghi kết thúc dòng theo hành vi formatter/writer và nền tảng.

Ví dụ bên trong một phương thức đã có `BufferedWriter writer`:

```java
writer.write("Dòng thứ nhất");
writer.newLine();
writer.write("Dòng thứ hai");
```

Đây là **mã minh họa**, cần có biến `writer` được khởi tạo và xử lý `IOException` khi cần. Nếu muốn output text dùng kiểu xuống dòng của hệ điều hành, `newLine()` là cách diễn đạt ý định rõ ràng.

### Khi phải tuân theo định dạng hoặc giao thức cụ thể

Ghi **literal terminator** do đặc tả yêu cầu:

```java
String dataLf = "A\nB\n";
String dataCrlf = "A\r\nB\r\n";
String dataCr = "A\rB\r";
```

- Với file chuẩn hóa LF trong dự án, ghi `"\n"` một cách rõ ràng.
- Với giao thức yêu cầu CRLF, phải ghi `"\r\n"`. Ví dụ các dòng header của HTTP/1.1 theo cú pháp giao thức dùng CRLF; không dùng `System.lineSeparator()` thay một cách tùy tiện.
- Khi tạo file cần bảo toàn nguyên trạng, **không tự gọi `newLine()` ở chỗ mỗi terminator vốn khác nhau** nếu chỉ có thông tin về nội dung từng dòng.

`System.lineSeparator()` không phải chức năng phân tích file đầu vào. Nó mô tả quy ước của môi trường chạy, **không suy ra** được file đang đọc dùng dấu kết thúc dòng nào.

### Dòng cuối có bắt buộc newline không?

Không có đáp án duy nhất cho mọi file. Một số công cụ theo truyền thống Unix thích hoặc yêu cầu **newline cuối file**; một số giao thức/định dạng quy định riêng; nhiều ứng dụng vẫn đọc được dòng cuối không có terminator. Ví dụ:

```text
"A\nB"   -> dòng B kết thúc tại EOF, không có terminator cuối
"A\nB\n" -> dòng B có LF cuối
```

Hai chuỗi đều có **hai dòng nội dung** theo `String.lines()` và `BufferedReader.readLine()`, nhưng **khác byte**. Kiểm tra yêu cầu đầu ra trước khi tự thêm hoặc xóa newline cuối.

## 8. Chuẩn hóa newline mà không làm mất nội dung cần giữ

Trong nhiều ứng dụng, chuẩn hóa LF giúp so sánh và xử lý nhất quán. Với một **chuỗi Java** chỉ dùng ba loại CRLF, CR, LF:

```java
String normalized = original.replace("\r\n", "\n").replace('\r', '\n');
```

Đây là **mã minh họa**; `original` phải là chuỗi được tạo ở chương trình của bạn. Cách này:

1. Chuyển cặp CRLF thành một LF.
2. Chuyển các CR đơn còn lại thành LF.
3. Giữ LF đã có; không tự cắt khoảng trắng, không tự xóa dòng rỗng, không tự thêm newline cuối.

Đây là phép biến đổi có mất thông tin về **loại dấu ngắt cũ**, dù giữ cấu trúc các dòng trong trường hợp ba loại terminator trên. Nếu cần **giữ chính xác byte**, hãy để nguyên dữ liệu ban đầu và không áp dụng chuẩn hóa.

### Các bẫy khi chuẩn hóa

**Sai thứ tự:**

```java
// SAI khi muốn CRLF tương đương một LF:
String wrong = original.replace('\r', '\n');
// CRLF -> LF LF, có thể vô tình thêm một dòng rỗng.
```

**Tự cắt khoảng trắng:**

```java
// Khác mục tiêu chuẩn hóa newline:
String changed = original.strip();
```

`strip()` còn loại cả whitespace đầu/cuối theo quy tắc Unicode, bao gồm dấu xuống dòng cuối; có thể phá hủy định dạng tài liệu hoặc dữ liệu trống có ý nghĩa. `trim()` cũng không phải phép chuẩn hóa kiểu xuống dòng.

**Phân chia rồi ghép lại:**

```java
String rebuilt = String.join("\n", original.lines().toList());
```

Phép này thường mất dấu kết thúc dòng cuối và không thể biết chỗ nào vốn là CR, CRLF hay LF. Có ích khi bạn **chủ động dựng lại file theo một định dạng mới**, nhưng không thể tuyên bố giữ nguyên dữ liệu.

**Regex `\R` có phạm vi rộng hơn:**

```java
String normalizedUnicodeBreaks = original.replaceAll("\\R", "\n");
```

Trong Java regex, `\R` nhận nhiều dạng line-break Unicode hơn ba kiểu CRLF/CR/LF. Chỉ dùng nếu yêu cầu rõ ràng là thống nhất cả những dấu ngắt Unicode như NEL, LS, PS; nếu không, nó có thể thay đổi các ký tự mà bạn không định coi là kết thúc dòng. `replaceAll` dùng regex và replacement, còn `replace` là thay chuỗi/ký tự theo nghĩa literal.

## 9. Vì sao `String.split("\n")` có thể sai với dữ liệu thực tế?

Một phản xạ thường gặp là đọc file văn bản rồi:

```java
String[] lines = text.split("\n");
```

Điều đó chỉ phù hợp nếu bạn **biết chắc** nguồn dùng LF và cách xử lý dòng cuối của `String.split` là điều mình muốn. Những khác biệt quan trọng:

| Đầu vào | `split("\n")` | `String.lines()` |
|---|---|---|
| `"A\nB"` | `["A", "B"]` | Hai dòng `A`, `B` |
| `"A\r\nB"` | Phần tử đầu là `"A\r"` | Hai dòng `A`, `B` không kèm CR |
| `"A\rB"` | Một phần tử gồm cả chuỗi | Hai dòng `A`, `B` |
| `"A\n"` | Mặc định bỏ chuỗi trống cuối | Một dòng `A` |
| `"\n"` | Mặc định có thể trả mảng không phần tử | Một dòng rỗng |
| `""` | `split` có thể trả một phần tử rỗng | Không có dòng |

`String.split(regex)` hoạt động theo **regular expression**, không theo khái niệm “dòng Java” nếu mẫu regex không đủ. Đặc biệt, `split(regex)` dùng giới hạn `0` theo mặc định nên **loại các chuỗi trống ở cuối**. Muốn giữ các mục rỗng cuối, truyền giới hạn âm, ví dụ `text.split("\\R", -1)`; nhưng lúc đó có thể tạo **một mục trống sau terminator cuối**, khác ngữ nghĩa của `String.lines()`.

Với nhu cầu duyệt dòng đơn thuần, ưu tiên `String.lines()` (chuỗi trong bộ nhớ), `BufferedReader.readLine()` hoặc `Files.lines(...)`. Với nhu cầu giữ nguyên dấu ngắt, dùng đọc văn bản thô rồi tự phân tích và lưu lại dấu ngắt tương ứng.

## 10. Dữ liệu trộn CRLF, LF và CR: nên xử lý thế nào?

Giả sử nhập file từ nhiều hệ thống có cả ba kiểu. Trước hết xác định **hợp đồng đầu vào**:

- Nếu file chỉ cần lấy **dữ liệu từng dòng**, `BufferedReader.readLine()` hoặc `Files.lines` sẽ phân tách ba kiểu này mà không cần bạn tự thay ký tự.
- Nếu sau đó phải ghi ra định dạng LF nhất quán, có thể chuẩn hóa trên chuỗi hoặc dùng `BufferedWriter` ghi từng dòng và literal `"\n"`. Quyết định có cần dấu kết thúc dòng cuối hay không.
- Nếu phải bảo toàn **chính xác** kiểu newline của từng dòng, không dùng các API đã bỏ terminator để lưu nội dung duy nhất; hãy phân tích văn bản thô và ghi lại cả terminator cho từng dòng.
- Nếu file được mở dưới dạng bytes để xử lý dữ liệu có cấu trúc, trước tiên phải biết **charset**. Không tìm dấu `0A`/`0D` bằng cách quét mù dữ liệu nhị phân hoặc UTF-16 mà không hiểu encoding.
- Nếu dữ liệu theo **giao thức**, dùng dấu kết thúc dòng giao thức yêu cầu, dù khác với `System.lineSeparator()` của máy chạy.

### Một parser cần giữ nguyên loại terminator

Về mặt dữ liệu, đừng chỉ lưu danh sách `List<String> lines` khi ứng dụng cần “round-trip” 100%:

```text
Nội dung gốc:      "A\r\nB\nC\rD"
Các đoạn logic:    ("A", "\r\n"), ("B", "\n"), ("C", "\r"), ("D", "")
```

Ở ví dụ này, mỗi cặp lưu **nội dung dòng** và **terminator gốc** (`""` cho dòng cuối không có dấu kết thúc). Ghép lần lượt nội dung và terminator của từng cặp sẽ tái lập nguyên chuỗi. Nếu cần bảo toàn **byte** gốc thay vì chỉ ký tự, còn phải giữ nguyên charset/BOM và byte stream ban đầu hoặc một cơ chế mã hóa chính xác tương đương.

Không tự loại bỏ BOM (Byte Order Mark), thay charset hoặc trim whitespace trong lúc “chỉ chuẩn hóa line ending”; những biến đổi đó nằm ngoài nhiệm vụ xử lý LF/CRLF/CR.

## 11. Dòng, token và cấu trúc tài liệu

Bài nằm trong nhóm **Dòng và token**, nên cần tách rõ:

- **Dòng (line):** một đoạn văn bản được phân ranh bởi line terminator theo quy tắc API.
- **Token:** một đơn vị do **delimiter** (khoảng trắng, dấu phẩy, dấu chấm phẩy, regex, cú pháp parser...) xác định. Một dòng có thể chứa nhiều token, và token cũng có thể trải qua dòng nếu parser/định dạng cho phép.
- `Scanner` mặc định dùng whitespace delimiter để lấy token qua `next()`, `nextInt()`, ...; `nextLine()` lại lấy phần còn lại của dòng hiện tại và tiêu thụ dấu kết thúc dòng.
- `BufferedReader.readLine()` không phân tách token; nó chỉ lấy một dòng. Bạn có thể parse token trong chuỗi dòng sau đó.

Ví dụ dữ liệu `"Ada 42\r\nLinh 7\n"` có hai dòng nhưng bốn token theo whitespace (Ada, 42, Linh, 7). Khi chuyển từ đọc token sang đọc dòng, cần chủ động xử lý delimiter còn lại như ví dụ 3.

Một lưu ý quan trọng với **CSV**: nếu CSV cho phép ký tự newline bên trong trường đặt trong dấu ngoặc kép, **một bản ghi logic không nhất thiết là một dòng vật lý**. Các parser CSV nên tuân theo cú pháp CSV chứ không dựa đơn thuần vào `readLine()` rồi `split(",")`. Tương tự, newline trong chuỗi literal của một định dạng cấu trúc có thể mang nghĩa riêng.

## 12. Những lỗi thường gặp

1. **Gọi CRLF là “một ký tự Java”.** Nó gồm hai `char` (`\r` rồi `\n`) nhưng nhiều API đọc dòng coi đó là một terminator.
2. **Dùng `split("\n")` cho CRLF.** Kết quả có thể còn `\r` ở cuối token/dòng, khiến `equals` và parse dữ liệu bị sai.
3. **Giả sử `readLine()` giữ newline.** Nó loại terminator; sau khi đọc theo dòng, bạn không thể suy ra chính xác terminator cũ từ nội dung trả về.
4. **Nhầm dòng rỗng với EOF.** Với `BufferedReader.readLine()`, `""` là dòng rỗng; `null` là hết input.
5. **Dùng `System.lineSeparator()` để tách file từ hệ khác.** Đây là quy ước nền tảng nơi chương trình đang chạy, không phải metadata của file đầu vào.
6. **Chuẩn hóa CR trước CRLF.** `\r\n` sẽ trở thành `\n\n`, làm tăng số dòng rỗng.
7. **Thay dấu xuống dòng bằng `strip()`/`trim()`.** Những hàm này còn loại bỏ whitespace đầu/cuối và có thể làm mất trailing newline.
8. **Tự động đổi hết file khi chỉ cần đọc.** Nếu parser đã nhận diện CRLF/LF/CR, đọc dòng không yêu cầu ghi file lại; ghi lại có thể tạo diff, thay đổi hash và phá tính nguyên bản.
9. **Giữ các dòng nhưng bỏ quy tắc EOF.** `"A"` và `"A\n"` có cùng dòng nội dung nhưng khác representation và có thể khác hợp đồng định dạng.
10. **Quét byte `0A` để tách dòng trong mọi charset.** UTF-16 và một số dạng mã hóa khác có cấu trúc byte khác; hãy giải mã đúng trước hoặc phân tích byte theo định dạng.
11. **Ngầm dùng `println` khi giao thức yêu cầu CRLF.** Kết quả sẽ phụ thuộc hệ điều hành thay vì quy tắc giao thức.
12. **Đánh đồng dòng vật lý với bản ghi logic.** CSV, nội dung nhiều dòng trong quoted string và các định dạng có cú pháp riêng cần parser phù hợp.
13. **Đoán newline chỉ theo hệ điều hành.** File có thể qua Git, mạng, editor và tool; hãy kiểm tra dữ liệu thực tế hoặc dùng contract được công bố.
14. **Thử chuẩn hóa mọi ký tự trông như “ngắt dòng”.** `\R` trong regex rộng hơn tập LF/CR/CRLF; chỉ dùng khi muốn xử lý toàn bộ nhóm line-break Unicode.

## 13. Checklist chọn giải pháp

| Nhu cầu | Cách làm phù hợp |
|---|---|
| Đọc từng dòng không quan tâm dấu kết thúc gốc | `BufferedReader.readLine()` hoặc `Files.lines(path, charset)` |
| Xử lý dòng trong một chuỗi đang có | `String.lines()` |
| Giữ nguyên CR, LF, CRLF trong văn bản | `Files.readString(path, charset)`, tránh tách/ghép lại nếu cần exact |
| Giữ nguyên **byte** file | `Files.readAllBytes(path)` hoặc I/O byte, không thực hiện chuyển mã hay viết lại |
| Chuẩn hóa ba kiểu sang LF trên chuỗi | `replace("\r\n","\n").replace('\r','\n')` |
| Ghi xuống dòng theo hệ điều hành | `BufferedWriter.newLine()`, `System.lineSeparator()` |
| Ghi dữ liệu theo chuẩn LF | Ghi literal `"\n"` |
| Ghi theo chuẩn CRLF | Ghi literal `"\r\n"` |
| Đếm các dòng text theo hành vi Java 11+ | `String.lines().count()`; chú ý quy ước dòng cuối |
| Xử lý token theo delimiter | `Scanner` hoặc parser chuyên dụng; tách riêng khái niệm line và token |

## 14. Tự kiểm tra kiến thức

**Câu 1.** `"x\r\ny"` gồm mấy `char` và mấy dòng theo `String.lines()`?  
**Đáp án:** 4 `char` (`x`, CR, LF, `y`) và 2 dòng.

**Câu 2.** `BufferedReader.readLine()` gặp `"\n"` ở đầu file thì trả gì?  
**Đáp án:** lần đọc đầu trả chuỗi rỗng `""`; lần tiếp theo nếu file hết sẽ trả `null`.

**Câu 3.** Vì sao `System.lineSeparator()` không dùng để đoán dấu xuống dòng của file?  
**Đáp án:** giá trị của nó dựa trên môi trường chương trình đang chạy, còn nội dung file có thể được tạo trên bất kỳ hệ thống hay quy ước nào.

**Câu 4.** Chuỗi `"A\r\nB"` đi qua `replace('\r','\n')` thì thế nào?  
**Đáp án:** thành `"A\n\nB"`, vô tình xuất hiện một dòng rỗng. Hãy thay `"\r\n"` trước rồi mới thay CR đơn.

**Câu 5.** `"A\n"` và `"A"` có `String.lines().count()` khác nhau không?  
**Đáp án:** không; cả hai có một dòng, nhưng độ dài và byte representation khác nhau.

**Câu 6.** Nếu dữ liệu cần Round-trip chính xác LF, CRLF, CR, có nên chỉ lưu kết quả `Files.readAllLines`?  
**Đáp án:** không. Cần giữ văn bản thô hoặc giữ nội dung dòng **kèm terminator tương ứng**, và giữ charset/byte gốc nếu phải tái lập bytes chính xác.

**Câu 7.** `Scanner.nextLine()` ngay sau `Scanner.nextInt()` có thể trả chuỗi rỗng dù còn dữ liệu?  
**Đáp án:** có, vì nó có thể tiêu thụ phần còn lại (rỗng) của dòng chứa token số, rồi lần gọi kế tiếp mới đọc dòng sau.

## Kết luận

**LF** là `\n` (U+000A), **CR** là `\r` (U+000D), **CRLF** là cặp `\r\n`. Sự khác biệt tồn tại trong nội dung chuỗi và byte file dù hiển thị có thể giống nhau. Trong Java, `BufferedReader.readLine()`, `String.lines()` và các API `Files` đọc theo dòng thường hiểu cả ba dạng và bỏ dấu kết thúc dòng. Khi cần **bảo toàn nguyên dạng**, đọc và giữ dữ liệu thô; khi cần **chuẩn hóa**, chọn quy ước đích có chủ ý và xử lý CRLF trước CR. Khi **ghi**, chọn dấu ngắt theo định dạng hay giao thức yêu cầu, không mặc định dùng quy ước của môi trường chạy.

### Tài liệu Java SE 17

- [`BufferedReader.readLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [`String.lines()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Files.readAllLines()`, `Files.lines()`, `Files.readString()`, `Files.writeString()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`BufferedWriter.newLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [`System.lineSeparator()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [`Scanner.nextLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html)
- [`Pattern` (`\R` trong regex Java)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
