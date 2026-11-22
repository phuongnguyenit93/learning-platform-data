# Scanner với File, Path và Charset (Java 10+)

## 1. Mục tiêu và kết luận

Khi đọc một tệp văn bản bằng `java.util.Scanner`, có hai việc khác nhau: **mở nguồn dữ liệu** (tệp do `File` hoặc `Path` chỉ đến) và **giải mã byte thành ký tự** (dựa trên `Charset`). Từ **Java 10**, `Scanner` có hai constructor nhận trực tiếp một đối tượng `Charset`:

~~~java
Scanner(File source, Charset charset) throws IOException
Scanner(Path source, Charset charset) throws IOException
~~~

Đây là **chữ ký constructor của thư viện chuẩn**, không phải mã cần định nghĩa lại. Cả hai được đánh dấu **`Since: 10`** trong Javadoc Java hiện hành.

Ví dụ ngắn:

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Scanner;

// Những dòng sau đặt trong phương thức throws IOException:
File file = new File("data.txt");
Path path = Paths.get("data.txt");

try (Scanner byFile = new Scanner(file, StandardCharsets.UTF_8)) {
    // Đọc các token/dòng qua byFile.
}

try (Scanner byPath = new Scanner(path, StandardCharsets.UTF_8)) {
    // Đọc cùng tệp theo đường dẫn Path.
}
~~~

Điều kiện của ví dụ: `data.txt` phải tồn tại trong **thư mục làm việc** tương ứng khi chương trình chạy. `StandardCharsets.UTF_8` cho biết **byte trong tệp phải được giải mã theo UTF-8**.

**Ghi nhớ:**

- `File` và `Path` là hai cách biểu diễn vị trí tệp; chúng **không phải nội dung tệp**.
- `Charset` mô tả cách chuyển **byte sang ký tự Unicode**.
- `Scanner` sau khi giải mã còn **phân tích token** thành chuỗi, số hoặc các kiểu dữ liệu khác; charset không quyết định delimiter hay locale.
- Khai báo charset tường minh giúp tránh phụ thuộc vào charset mặc định của môi trường.
- Khi làm việc với nguồn file, dùng **`try-with-resources`** để đóng `Scanner` và tài nguyên bên dưới.

Bài này sử dụng các API vẫn còn áp dụng; ví dụ chương trình hoàn chỉnh được thiết kế cho **Java 10 trở lên** và có thể chạy bằng **JDK 17+**.

## 2. `File`, `Path` và `Charset` khác nhau thế nào?

| Khái niệm | Kiểu Java | Vai trò |
| --- | --- | --- |
| File | `java.io.File` | Đại diện một đường dẫn tệp/thư mục theo API `java.io`; không tự chứa byte dữ liệu |
| Path | `java.nio.file.Path` | Đại diện đường dẫn trong hệ thống tệp theo API NIO.2; làm việc tự nhiên với `Files` |
| Charset | `java.nio.charset.Charset` | Xác định cách giải mã byte đã lưu thành ký tự, ví dụ UTF-8 |
| Scanner | `java.util.Scanner` | Đọc nguồn, tách token/dòng và chuyển token thành dữ liệu như `int`, `double`, `String` |

Luồng xử lý khi dùng các constructor hai đối số:

~~~text
Tệp trên đĩa (byte)
     |
     | File / Path: xác định vị trí và mở nguồn
     v
Dữ liệu byte
     |
     | Charset: giải mã
     v
Ký tự Unicode
     |
     | Scanner: phân tách dòng/token, xử lý locale, chuyển kiểu
     v
String / int / double / ... trong ứng dụng
~~~

**Không nhầm `Charset` với ký tự phân cách.** `UTF_8` không nói rằng tệp có dấu phẩy hay dấu cách. Sau khi mở thành công, `Scanner` mặc định phân tách token theo whitespace; muốn dùng delimiter khác phải gọi `useDelimiter(...)`.

**Không nhầm charset với locale.** `StandardCharsets.UTF_8` hỗ trợ đọc ký tự có dấu; `Locale.US` lại ảnh hưởng cách `Scanner.nextDouble()` nhận dạng dấu thập phân và một số quy ước số. Một file UTF-8 vẫn có thể chứa chuỗi số `"1,5"` hoặc `"1.5"` tùy quy ước ứng dụng.

## 3. Constructor `Scanner(File, Charset)`

`File` đến từ `java.io`. Khi ứng dụng đã có một đối tượng `File`, có thể truyền trực tiếp:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class ReadFromFile {
    public static void main(String[] args) throws IOException {
        File file = new File("notes.txt");

        try (Scanner scanner =
                     new Scanner(file, StandardCharsets.UTF_8)) {
            while (scanner.hasNextLine()) {
                String line = scanner.nextLine();
                System.out.println(line);
            }
        }
    }
}
~~~

**Đây là một chương trình Java độc lập** có tên tệp `ReadFromFile.java`. Cần chuẩn bị `notes.txt` có nội dung UTF-8 trong thư mục chạy. Nếu không có tệp hoặc không thể mở, constructor có thể ném `IOException`.

Khai báo phương thức tương ứng:

~~~java
public Scanner(File source, Charset charset) throws IOException
~~~

Điểm đáng chú ý: overload `Scanner(File, Charset)` của Java 10 khai báo **`IOException`**, không nên giả định rằng chỉ có `FileNotFoundException` là ngoại lệ checked có thể xuất hiện. `FileNotFoundException` là một lớp con của `IOException` và có liên quan tới một số constructor `Scanner(File, ...)` khác, nhưng khi viết mã cho overload `Charset`, **`IOException` là kiểu cần xử lý/khai báo theo Javadoc**.

### Khi nào chọn `File`?

- API có sẵn trả về `File`.
- Mã cần tích hợp với thư viện đang sử dụng `java.io.File`.
- Không cần chuyển kiểu chỉ để gọi constructor: `new Scanner(file, StandardCharsets.UTF_8)` là hợp lệ.

`File` không được xem là một đối tượng chứa nội dung file; `new File("notes.txt")` chỉ tạo đối tượng đường dẫn, còn việc mở và đọc thực sự xảy ra trong các API I/O tương ứng.

## 4. Constructor `Scanner(Path, Charset)`

`Path` thuộc `java.nio.file`. Với mã Java hiện đại thường dùng `Files` để xử lý tệp, đường dẫn `Path` là lựa chọn tự nhiên:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Scanner;

public class ReadFromPath {
    public static void main(String[] args) throws IOException {
        Path path = Paths.get("notes.txt");

        try (Scanner scanner =
                     new Scanner(path, StandardCharsets.UTF_8)) {
            while (scanner.hasNextLine()) {
                System.out.println(scanner.nextLine());
            }
        }
    }
}
~~~

Tương tự, `notes.txt` cần tồn tại và được mã hóa đúng charset. Chữ ký:

~~~java
public Scanner(Path source, Charset charset) throws IOException
~~~

**`Paths.get(...)` dùng được từ trước Java 10.** Trong các phiên bản Java mới, `Path.of(...)` cũng phổ biến, nhưng **`Path.of` xuất hiện từ Java 11**, nên chương trình trên dùng `Paths.get(...)` để giữ tương thích Java 10.

Khi có `Path`, không cần chuyển sang `File` để đọc:

~~~java
Path path = Paths.get("notes.txt");
try (Scanner s = new Scanner(path, StandardCharsets.UTF_8)) {
    // ...
}
~~~

Đối với các `Path` thuộc hệ thống tệp đặc biệt, việc chuyển sang `File` không phải lúc nào cũng khả thi hoặc thích hợp. Đó cũng là một lý do dùng overload nhận `Path` trực tiếp.

### So sánh nhanh `File` và `Path`

| Tiêu chí | `Scanner(File, Charset)` | `Scanner(Path, Charset)` |
| --- | --- | --- |
| Tham số nguồn | `java.io.File` | `java.nio.file.Path` |
| Tham số bộ mã | `java.nio.charset.Charset` | `java.nio.charset.Charset` |
| Bổ sung từ Java | 10 | 10 |
| Checked exception khi mở | `IOException` | `IOException` |
| Đọc dòng/token sau khi mở | Các phương thức `Scanner` như nhau | Các phương thức `Scanner` như nhau |
| Khuyến nghị | Phù hợp khi API sẵn dùng `File` | Tự nhiên với mã dùng `Path` và `Files` |

Không có sự khác nhau về đơn vị token/dòng chỉ vì đã chọn `File` thay vì `Path`. Khi hai constructor trỏ đến **cùng một file** và nhận **cùng charset**, các ký tự được giải mã có cùng ý nghĩa; việc phân tích token do cùng `Scanner` đảm nhiệm.

## 5. Vì sao nên truyền `StandardCharsets.UTF_8` thay vì dựa vào mặc định?

`StandardCharsets` cung cấp sẵn các đối tượng charset chuẩn, chẳng hạn:

~~~java
StandardCharsets.UTF_8
StandardCharsets.US_ASCII
StandardCharsets.ISO_8859_1
StandardCharsets.UTF_16
StandardCharsets.UTF_16BE
StandardCharsets.UTF_16LE
~~~

`StandardCharsets.UTF_8` là lựa chọn thường dùng cho văn bản có tiếng Việt và nhiều ngôn ngữ. Khi mã hóa/giải mã, quan trọng nhất là **charset thực tế của tệp** phải khớp charset được yêu cầu.

**Đừng nhầm “hỗ trợ tiếng Việt” với “mọi file tiếng Việt đều là UTF-8”.** Một file cũ có thể dùng charset khác; cần biết nguồn dữ liệu, chuyển mã rõ ràng hoặc có quy trình nhận diện/phê duyệt charset. Nếu file thực sự là UTF-8 mà lại đọc theo Latin-1, có thể xuất hiện chữ lỗi (*mojibake*).

Các constructor không có charset tường minh, ví dụ:

~~~java
new Scanner(file)
new Scanner(path)
~~~

sử dụng **default charset** của môi trường theo hợp đồng tương ứng. Từ Java 18, JEP 400 chuẩn hóa UTF-8 làm default charset trong đa số cấu hình Java SE, nhưng có các chi tiết cấu hình/môi trường và mã Java 10 cũ mà bạn không nên dựa vào khi cần giao tiếp dữ liệu nhất quán.

**Khuyến nghị hiện nay:** khi file có hợp đồng mã hóa rõ, hãy truyền chính xác `Charset` thay vì dựa vào thiết lập máy chạy. Ví dụ:

~~~java
try (Scanner scanner = new Scanner(
        Paths.get("data.txt"), StandardCharsets.UTF_8)) {
    // ...
}
~~~

### `Charset` so với tên charset dưới dạng `String`

Java có overload cũ nhận tên bộ mã:

~~~java
new Scanner(file, "UTF-8")
new Scanner(path, "UTF-8")
~~~

Chúng **vẫn còn dùng được**, không phải API bị xóa. Tuy nhiên khi đã có một đối tượng `Charset`, truyền trực tiếp thường dễ bảo trì và tránh sai chính tả tên charset:

~~~java
Charset charset = StandardCharsets.UTF_8;
Scanner scanner = new Scanner(path, charset);
~~~

Khi chọn charset theo cấu hình động, có thể dùng `Charset.forName(name)` để chuyển một tên hợp lệ sang đối tượng `Charset`; cần xử lý cấu hình sai, charset không được hỗ trợ và giới hạn nguồn tin của tên nhận từ bên ngoài.

**Không phải mọi giá trị `String` truyền vào `Scanner` đều là tên charset:** constructor `new Scanner("hello")` có **một tham số String** và hiểu String đó là **nội dung cần quét**, không phải tên tệp hay charset.

## 6. Phân biệt rất quan trọng: `new Scanner(String)` không mở tệp!

Sai lầm phổ biến:

~~~java
String filename = "notes.txt";
Scanner scanner = new Scanner(filename);
~~~

Đoạn trên tạo Scanner đọc **chính chuỗi `"notes.txt"`**, **không mở file `notes.txt`**. Vì vậy:

~~~java
Scanner scanner = new Scanner("100 200");
System.out.println(scanner.nextInt()); // 100
~~~

Ở đây nguồn là chuỗi literal đã có trong bộ nhớ. Ngược lại:

~~~java
Path path = Paths.get("notes.txt");
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    // Mở dữ liệu của tệp do path chỉ tới.
}
~~~

Nếu người dùng có một String chứa đường dẫn, trước tiên chuyển nó thành đối tượng đường dẫn:

~~~java
String filename = "notes.txt";
Path path = Paths.get(filename);

try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    // ...
}
~~~

Không nên kiểm tra một dòng `new Scanner(path.toString())` rồi kết luận Scanner đã đọc file. Overload ở đây là `Scanner(String)`, khác hoàn toàn với `Scanner(Path, Charset)`.

## 7. Charset chỉ lo giải mã; `Scanner` còn có delimiter, locale và quy tắc token

Mặc định, Scanner xem các ký tự whitespace là dấu ngăn cách token, vì vậy:

~~~java
// Đoạn minh họa trong phương thức:
Scanner scanner = new Scanner("42 7 1.5");
scanner.useLocale(java.util.Locale.US);

int a = scanner.nextInt();     // 42
int b = scanner.nextInt();     // 7
double c = scanner.nextDouble(); // 1.5
scanner.close();
~~~

**Điều này không phụ thuộc việc Scanner nhận File hay Path.** Sau khi giải mã thành văn bản, cách quét token là như nhau.

### Delimiter

Nếu dữ liệu đơn giản phân tách bằng dấu phẩy:

~~~java
try (Scanner scanner = new Scanner("A,B,C")) {
    scanner.useDelimiter(",");
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
~~~

Kết quả các dòng là `A`, `B` và `C`. Đối với dữ liệu CSV chuẩn có dấu ngoặc kép, ký tự thoát, dấu phẩy bên trong trường, không nên coi `useDelimiter(",")` là một CSV parser đầy đủ. Hãy dùng thư viện CSV phù hợp khi định dạng phức tạp.

### Locale khi đọc số

~~~java
try (Scanner scanner = new Scanner("1.5")) {
    scanner.useLocale(java.util.Locale.US);
    double value = scanner.nextDouble(); // 1.5
}
~~~

`Locale` quyết định cách nhận dạng nhiều định dạng số. Một tài liệu UTF-8 có ký tự `"1.5"` không tự buộc `Scanner` sử dụng dấu chấm làm dấu thập phân nếu locale định dạng hiện hành khác. Dùng `useLocale(...)` khi dữ liệu có định dạng số đã quy định rõ.

### `nextLine` và `nextInt` không tiêu thụ theo cùng cách

~~~java
try (Scanner scanner = new Scanner("42 7\nNext line")) {
    int a = scanner.nextInt();
    int b = scanner.nextInt();

    String restOfLine = scanner.nextLine(); // Chuỗi rỗng.
    String nextLine = scanner.nextLine();   // "Next line"
}
~~~

`nextInt` đọc token số; ký tự xuống dòng ở cuối dòng có thể còn chờ `nextLine`. **`nextLine` đầu tiên** ở ví dụ này tiêu thụ phần cuối của dòng số và trả về chuỗi rỗng. Đây là hành vi phân tích văn bản, **không phải lỗi UTF-8 hay lỗi constructor `Path`**.

Nếu mục tiêu là xử lý theo dòng, ưu tiên một vòng lặp `hasNextLine()/nextLine()`. Nếu mục tiêu là xử lý token số, dùng `hasNextInt()/nextInt()` và kiểm soát delimiter, locale, cũng như ranh giới dòng.

## 8. Chương trình hoàn chỉnh: File, Path, UTF-8 và kết quả có thể kiểm chứng

Chương trình này **tự tạo tệp tạm**, ghi dữ liệu UTF-8, mở nó lần lượt bằng `Scanner(Path, Charset)` và `Scanner(File, Charset)`, thử giải mã bằng charset sai, rồi xóa tệp tạm. Không cần tải hoặc tạo `notes.txt` bằng tay.

Lưu vào tệp **`CharsetScannerDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Scanner;

public class CharsetScannerDemo {

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("scanner-java10-", ".txt");

        try {
            // "Café Việt" và hai dòng số, được lưu dưới UTF-8.
            // Escape Unicode giữ file mã nguồn Java độc lập charset editor.
            String content = "Caf\u00E9 Vi\u1EC7t\n42 7\n1.5\n";

            Files.write(path,
                    content.getBytes(StandardCharsets.UTF_8));

            String expectedLine =
                    content.substring(0, content.indexOf('\n'));

            // 1. Dùng Path + Charset.
            try (Scanner scanner =
                         new Scanner(path, StandardCharsets.UTF_8)) {
                scanner.useLocale(Locale.US);

                String first = scanner.nextLine();
                int a = scanner.nextInt();
                int b = scanner.nextInt();
                boolean emptyRemainder = scanner.nextLine().isEmpty();
                double ratio = scanner.nextDouble();

                System.out.println("pathTextOK="
                        + first.equals(expectedLine));
                System.out.println("utf16Units=" + first.length());
                System.out.println("utf8Bytes="
                        + first.getBytes(StandardCharsets.UTF_8).length);
                System.out.println("pathNumbers=" + a + "," + b);
                System.out.println(
                        "lineRemainderEmpty=" + emptyRemainder);
                System.out.println("pathRatio=" + ratio);
            }

            // 2. Dùng File + Charset với chính tệp đó.
            try (Scanner scanner =
                         new Scanner(path.toFile(), StandardCharsets.UTF_8)) {
                System.out.println("fileTextOK="
                        + scanner.nextLine().equals(expectedLine));
                System.out.println(
                        "fileNextLine=" + scanner.nextLine());
            }

            // 3. Giải mã UTF-8 bằng charset không phù hợp.
            try (Scanner scanner = new Scanner(
                    path, StandardCharsets.ISO_8859_1)) {
                System.out.println("wrongCharsetMatches="
                        + scanner.nextLine().equals(expectedLine));
            }

            // 4. Scanner(String) KHÔNG đọc nội dung file.
            try (Scanner scanner = new Scanner(path.toString())) {
                System.out.println("stringSourceIsPathText="
                        + scanner.nextLine().equals(path.toString()));
            }

            // 5. Charset là null là đối số không hợp lệ.
            try (Scanner ignored = new Scanner(path, (Charset) null)) {
                System.out.println("nullCharset=unexpected");
            } catch (NullPointerException ex) {
                System.out.println("nullCharset=NPE");
            }

        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CharsetScannerDemo.java
java CharsetScannerDemo
~~~

Chương trình sử dụng các API có thể biên dịch với **JDK 10 trở lên**; nên chạy bằng **JDK 17+** khi học Java hiện đại.

**`stdout` được đối chiếu bằng JDK 24:**

~~~text
pathTextOK=true
utf16Units=9
utf8Bytes=12
pathNumbers=42,7
lineRemainderEmpty=true
pathRatio=1.5
fileTextOK=true
fileNextLine=42 7
wrongCharsetMatches=false
stringSourceIsPathText=true
nullCharset=NPE
~~~

### Giải thích từng nhóm kết quả

1. `pathTextOK=true`: tệp được lưu bằng UTF-8 và đọc đúng bằng cùng charset.
2. `utf16Units=9`, `utf8Bytes=12`: dòng `"Café Việt"` có **9 đơn vị UTF-16** nhưng **12 byte UTF-8**. Scanner giải mã byte trước khi phân tích; hai con số đo hai khía cạnh khác nhau.
3. `pathNumbers=42,7`: `nextInt` đọc hai token số từ dòng thứ hai.
4. `lineRemainderEmpty=true`: sau hai `nextInt`, `nextLine` đầu tiên xử lý phần còn lại của dòng số (rỗng).
5. `pathRatio=1.5`: số thập phân được đọc theo `Locale.US`, không phụ thuộc locale của máy chạy.
6. `fileTextOK=true` và `fileNextLine=42 7`: overload nhận `File` đọc chính cùng nội dung UTF-8.
7. `wrongCharsetMatches=false`: đọc byte UTF-8 theo `ISO_8859_1` tạo văn bản khác. Đây là minh họa *mojibake*, không phải bằng chứng Scanner bỏ qua Charset.
8. `stringSourceIsPathText=true`: overload `Scanner(String)` quét chuỗi đường dẫn, **không mở file**.
9. `nullCharset=NPE`: `Charset` truyền vào constructor `Path` không được null.

**Không in tên file tạm** vì đường dẫn là ngẫu nhiên theo môi trường; chương trình chỉ in các điều kiện và số liệu có kết quả ổn định. `Files.deleteIfExists(path)` nằm trong `finally` để thu dọn tệp sau khi các Scanner đã đóng.

## 9. Quản lý tài nguyên và `try-with-resources`

`Scanner` triển khai `Closeable`/`AutoCloseable`. Khi nguồn của Scanner cũng là một nguồn có thể đóng, `Scanner.close()` sẽ đóng nó theo hợp đồng. Với Scanner đọc file, nên:

~~~java
try (Scanner scanner = new Scanner(
        Paths.get("data.txt"), StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        // Xử lý line.
    }
}
~~~

Trong chương trình thực, đặt khối này trong phương thức khai báo hoặc xử lý `IOException`, và tệp `data.txt` phải tồn tại. Khối try-with-resources đóng Scanner ngay cả khi có exception bên trong khối.

**Đừng bỏ quên đóng Scanner** được tạo từ file, vì nó sở hữu tài nguyên bên dưới. Ngược lại, một `Scanner` tạo từ `System.in` cũng có thể đóng luồng đầu vào chuẩn khi đóng Scanner; đó là tình huống quản lý vòng đời khác, không phải lý do để bỏ try-with-resources khi Scanner tự mở file.

Sau khi `Scanner` đã đóng, các lời gọi quét như `nextLine()` hoặc `hasNext()` sẽ ném `IllegalStateException`. Không tái sử dụng một Scanner đã đóng.

### Khi cần mở lại và đọc từ đầu

Một Scanner không phải “cửa sổ” tự động chạy lại từ đầu. Khi duyệt hết file, muốn đọc từ đầu lần nữa, thường tạo một Scanner **mới**:

~~~java
Path path = Paths.get("data.txt");

try (Scanner first = new Scanner(path, StandardCharsets.UTF_8)) {
    while (first.hasNextLine()) {
        first.nextLine();
    }
}

try (Scanner second = new Scanner(path, StandardCharsets.UTF_8)) {
    // Đọc lại từ đầu.
}
~~~

Cần cân nhắc rằng nội dung file có thể đã thay đổi giữa hai lần mở. Nếu yêu cầu một snapshot nội dung cố định, hãy thiết kế luồng xử lý và cách lưu dữ liệu theo hợp đồng đó.

## 10. Ngoại lệ và sai sót khi mở/đọc tệp

### `IOException` khi mở nguồn

Hai overload Java 10 được quan tâm đều khai báo:

~~~java
new Scanner(File source, Charset charset) // throws IOException
new Scanner(Path source, Charset charset) // throws IOException
~~~

Ví dụ tệp không tồn tại, đường dẫn không thể truy cập, quyền đọc bị từ chối hoặc có lỗi I/O mở file. Không cần giả định một subclass ngoại lệ cố định ở mọi nền tảng; ứng dụng có thể bắt `IOException` để xử lý chung và phân loại nguyên nhân cụ thể khi cần.

~~~java
try (Scanner scanner =
             new Scanner(Paths.get("missing.txt"), StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
} catch (IOException ex) {
    System.err.println("Cannot open file: " + ex.getMessage());
}
~~~

Đây là ví dụ **phụ thuộc vào file thực tế**; nếu file tồn tại thì không có lỗi. Đừng dùng ví dụ này để làm kiểm thử có `stdout` cố định.

### Tham số `null`

Không được truyền `null` làm `File`/`Path`/`Charset` cho các constructor trên. Các tham số `null` không hợp lệ có thể gây `NullPointerException` ngay khi xây Scanner.

~~~java
// Ví dụ lỗi cố ý:
// new Scanner((Path) null, StandardCharsets.UTF_8);
// new Scanner(Paths.get("data.txt"), (Charset) null);
~~~

Cần dùng cast trong ví dụ null có thể gây mơ hồ overload, để trình biên dịch biết chính xác constructor được gọi.

### Lỗi I/O phát sinh trong lúc quét

Một chi tiết dễ bỏ sót của `Scanner`: khi `Readable` bên dưới phát sinh `IOException` trong quá trình đọc, Scanner thường xem như đã chạm cuối dữ liệu. **Ngoại lệ I/O gần nhất có thể được truy vấn bằng `scanner.ioException()`**; nếu không có, phương thức trả về `null`.

~~~java
// scanner giả định là Scanner đã tạo và còn mở.
while (scanner.hasNextLine()) {
    process(scanner.nextLine());
}

IOException ioError = scanner.ioException();
if (ioError != null) {
    throw ioError;
}
~~~

Đây là **đoạn minh họa trong một phương thức**, trong đó `process(String)` là hàm ứng dụng cần tự định nghĩa. Điểm chính: **không suy luận chỉ từ `hasNextLine() == false` rằng mọi byte đã được đọc thành công** nếu cần phân biệt EOF bình thường với lỗi I/O.

`ioException()` báo lỗi gần nhất từ nguồn `Readable` trong quá trình Scanner hoạt động; nó không thay cho xử lý `IOException` lúc **mở file**.

### Lỗi phân tích token

Những lỗi này là **khác** lỗi charset và mở file:

- `InputMismatchException`: token có mặt nhưng không hợp định dạng kiểu yêu cầu, ví dụ `nextInt()` gặp `"abc"`.
- `NoSuchElementException`: cố đọc token/dòng mà Scanner không còn cung cấp.
- `IllegalStateException`: thao tác quét sau khi Scanner đã đóng.

Nên dùng `hasNextInt()`/`hasNextDouble()`, xác thực từng dòng, hoặc bắt ngoại lệ có chủ đích theo dữ liệu đầu vào. Nhưng nhớ `hasNextInt()` cũng dùng locale/radix của Scanner, không phải tự động đoán ý định của người viết file.

## 11. Xử lý BOM, sai mã hóa và dữ liệu không hợp lệ

Nếu một file UTF-8 có **BOM** (byte-order mark), ký tự `U+FEFF` có thể xuất hiện ở đầu dữ liệu sau giải mã, tùy API/đường đọc. Nó có thể ảnh hưởng token đầu tiên hoặc thao tác `nextInt` nếu bạn giả định file bắt đầu ngay bằng chữ số. Vì vậy, đừng chỉ nghĩ “đọc đúng UTF-8” là mọi tiền tố đặc biệt đều biến mất.

Khi hợp đồng nguồn dữ liệu có BOM, hãy xác định chính sách bỏ BOM ở tầng đọc văn bản. Ví dụ sau chỉ minh họa loại bỏ BOM nếu **chuỗi đầu vào** thực sự bắt đầu bằng `U+FEFF`:

~~~java
String line = scanner.nextLine();
if (!line.isEmpty() && line.charAt(0) == '\uFEFF') {
    line = line.substring(1);
}
~~~

**Không tự xóa ký tự U+FEFF ở mọi nơi trong văn bản**; đây là ví dụ xử lý một dấu BOM đầu nội dung, không phải biến đổi Unicode tổng quát.

Nếu dùng sai charset, văn bản có thể bị giải mã sai hoặc phát sinh ký tự thay thế. Tùy pipeline giải mã, dữ liệu byte không hợp lệ có thể được xử lý theo cơ chế báo lỗi/thay thế. **Đừng dựa vào `Scanner` như một trình xác thực byte/charset nghiêm ngặt**. Khi bắt buộc phát hiện lỗi mã hóa, dùng `CharsetDecoder` với chính sách `CodingErrorAction.REPORT` trong một pipeline giải mã có kiểm soát.

~~~java
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(
                java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(
                java.nio.charset.CodingErrorAction.REPORT);
~~~

Đây là **đoạn minh họa cấu hình decoder**, chưa phải một chương trình đọc file hoàn chỉnh; cần truyền nó cho pipeline giải mã tương ứng.

Điểm cần nhớ là cả hai overload `Scanner(File, Charset)` và `Scanner(Path, Charset)` giải mã byte theo charset được chỉ định, nhưng vẫn cần xử lý dữ liệu đầu vào không khớp đặc tả thực tế của file.

## 12. Khi nào nên dùng `Scanner` và khi nào chọn API khác?

`Scanner` hợp lý khi cần:

- Đọc một file văn bản thành **các token**.
- Chuyển token trực tiếp thành `int`, `long`, `double`, `boolean` với `Locale`/radix phù hợp.
- Xử lý từng dòng bằng `hasNextLine()/nextLine()` cho dữ liệu vừa phải.
- Mở tệp với `File` hoặc `Path` và **charset tường minh**.

Nếu ứng dụng chỉ cần đọc từng dòng mà không phân tích số/token, `BufferedReader` thường đơn giản hơn:

~~~java
try (var reader = java.nio.file.Files.newBufferedReader(
        java.nio.file.Paths.get("data.txt"),
        StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Đoạn này cần đặt trong phương thức xử lý hoặc khai báo `IOException` và tệp phải tồn tại. Trong ứng dụng lớn, chọn API theo yêu cầu sử dụng, đặc biệt với luồng dữ liệu lớn: Scanner có thể chậm hơn các giải pháp đọc tuyến tính chuyên dụng do phải phân tích token bằng biểu thức chính quy/định dạng.

Nếu file có cấu trúc JSON, XML hoặc CSV đầy đủ, việc dùng Scanner với delimiter đơn giản dễ dẫn tới xử lý sai quy tắc quoting/escaping. Hãy dùng parser phù hợp với định dạng, thay vì cố “sửa” bằng cách đổi Charset.

### Khi nào Charset không liên quan?

~~~java
new Scanner("42 7")
~~~

Đây là `Scanner(String)`, đầu vào đã là **ký tự trong bộ nhớ**, không có bước giải mã byte từ file. Vì thế không thể “sửa lỗi tên file” bằng cách chỉ đổi charset khi thực chất đang dùng nhầm constructor `Scanner(String)`.

## 13. Lỗi phổ biến và cách sửa

| Lỗi/hiểu nhầm | Thực tế | Cách sửa |
| --- | --- | --- |
| `new Scanner("notes.txt")` mở file | Không: quét literal `"notes.txt"` | Dùng `new Scanner(Paths.get("notes.txt"), UTF_8)` hoặc `new Scanner(new File(...), UTF_8)` |
| `File` chứa sẵn nội dung | `File` đại diện đường dẫn | Truyền `File` vào API mở/đọc thực tế |
| Chỉ `Scanner(File)` mới đọc được file | `Scanner(Path, Charset)` cũng hỗ trợ trực tiếp | Ưu tiên kiểu đường dẫn đang có |
| Constructor `(File, Charset)` chỉ ném `FileNotFoundException` | Chữ ký khai báo `IOException` | Xử lý hoặc khai báo `IOException` |
| UTF-8 là delimiter | Charset chỉ giải mã byte | Sử dụng `useDelimiter` khi cần |
| UTF-8 tự quy định dấu thập phân | Số phụ thuộc locale/radix của Scanner | Gọi `useLocale(...)` phù hợp |
| `nextLine` sau `nextInt` “bị lỗi” | Token scan có thể để lại phần cuối dòng | Chủ động tiêu thụ dòng còn lại |
| Dùng `new Scanner(path.toString())` đọc file | Đây là `Scanner(String)` | Truyền `Path` trực tiếp |
| Sai charset nhưng cố sửa bằng `nextLine` | Ký tự đã được giải mã sai | Xác định charset thật của file |
| Không đóng Scanner đọc file | Có thể rò rỉ handle/tài nguyên | Dùng try-with-resources |
| Kết thúc vòng đọc nghĩa là không có lỗi I/O | Scanner có thể coi IOException bên dưới như EOF | Kiểm tra `scanner.ioException()` nếu cần |
| Dùng `Scanner` để phân tích CSV/JSON phức tạp | Delimiter thường không hiểu quoting/nesting | Dùng parser định dạng chuyên biệt |

## 14. Câu hỏi tự kiểm tra

### Câu 1 — Constructor nào đọc file bằng UTF-8?

~~~java
Path p = Paths.get("notes.txt");
Scanner a = new Scanner(p.toString());
Scanner b = new Scanner(p, StandardCharsets.UTF_8);
~~~

**Đáp án:** `b` mở file qua `Path` với UTF-8; `a` chỉ quét chuỗi tên đường dẫn. Để chạy, tệp phải tồn tại, mã cần xử lý `IOException`, và phải đóng `Scanner` bằng try-with-resources hoặc `close()`.

### Câu 2 — `File` hay `Path` khác cách giải mã Unicode không?

**Đáp án:** Không tự khác. Với cùng file và cùng `Charset`, cả hai constructor cho dữ liệu ký tự có cùng ý nghĩa. Việc đọc số/dòng còn phụ thuộc delimiter/locale, không phụ thuộc kiểu đối tượng đường dẫn.

### Câu 3 — UTF-8 và `Locale.US` điều khiển việc gì?

**Đáp án:** `StandardCharsets.UTF_8` giải mã byte thành ký tự; `Locale.US` hỗ trợ cách nhận dạng số như `1.5` khi `nextDouble` được gọi. Hai cơ chế giải quyết hai vấn đề độc lập.

### Câu 4 — Tệp có dòng `42 7` rồi xuống dòng; gọi `nextInt` hai lần rồi `nextLine` được gì?

**Đáp án:** Hai `nextInt` trả `42` và `7`. `nextLine` đầu tiên thường trả chuỗi rỗng vì nó xử lý phần còn lại của dòng hiện tại sau token `7`.

### Câu 5 — File UTF-8 đọc bằng ISO-8859-1 có chắc đọc đúng dấu tiếng Việt không?

**Đáp án:** Không. Với các ký tự không nằm trong ASCII, giải mã UTF-8 bằng Latin-1 thường tạo chuỗi khác. Bài kiểm thử `"Café Việt"` cho `wrongCharsetMatches=false`.

### Câu 6 — Tại sao dùng `try-with-resources`?

**Đáp án:** Scanner đọc file quản lý một nguồn I/O cần được đóng. `try-with-resources` giúp đóng nó kể cả khi có ngoại lệ trong quá trình phân tích dữ liệu.

### Câu 7 — Nếu `hasNextLine()` trả false thì luôn đọc file thành công?

**Đáp án:** Không nhất thiết. Nếu nguồn `Readable` bị lỗi I/O trong lúc quét, Scanner có thể coi đó là kết thúc; `scanner.ioException()` cho phép kiểm tra ngoại lệ I/O gần nhất. Việc mở file ban đầu vẫn có thể ném `IOException` riêng.

## 15. Tổng kết và nguồn chính thức

- **`Scanner(File, Charset)` và `Scanner(Path, Charset)` cùng được bổ sung từ Java 10**, vẫn áp dụng hiện nay.
- Cả hai đọc **byte từ file** và giải mã theo **Charset tường minh**, ví dụ `StandardCharsets.UTF_8`.
- **`File`/`Path` mô tả vị trí file**, không phải nội dung; `Scanner(String)` quét chính nội dung String và **không tự mở file**.
- **Charset không thay cho delimiter hay locale**. Dùng `useDelimiter`/`useLocale` khi dữ liệu yêu cầu.
- **Hai overload với Charset khai báo `throws IOException` khi mở nguồn**; dùng try-with-resources và, nếu cần kiểm tra lỗi lúc đọc, `ioException()`.
- Dữ liệu UTF-8 phải đọc bằng charset phù hợp; sai charset có thể gây *mojibake*. Khi cần kiểm tra nghiêm ngặt byte không hợp lệ, thiết kế pipeline giải mã với `CharsetDecoder`.
- **Ưu tiên `Path` với NIO hiện đại** nếu đã có `Path`; dùng `File` khi API đang dùng `File`; cả hai đều là lựa chọn còn phù hợp.

### Tài liệu tham khảo chính thức

- [Java SE 26 — `Scanner` constructors và `ioException()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html): hai constructor nhận `File/Path, Charset`; `Since: 10`, `IOException` và các phương thức quét.
- [Java SE 26 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): các đối tượng charset chuẩn.
- [Java SE 26 — `CharsetDecoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): chính sách khi giải mã byte sai.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18; lý do vẫn nên ghi rõ charset theo hợp đồng nguồn dữ liệu.
