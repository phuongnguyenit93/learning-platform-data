# So sánh nội dung hai tệp bằng Files.mismatch trong Java 17

**Chủ đề:** Java 17 → Tệp và mã hóa ký tự  
**Trọng tâm:** Dùng `Files.mismatch(Path, Path)` để xác định hai tệp có cùng nội dung byte hay không; hiểu giá trị trả về, vị trí byte khác nhau, trường hợp một tệp là tiền tố của tệp kia, và phân biệt so sánh byte với so sánh văn bản sau khi giải mã.

Java 17 có phương thức `Files.mismatch` trong package `java.nio.file`. Phương thức này so sánh nội dung của hai tệp và trả về vị trí byte đầu tiên khác nhau. Nếu nội dung giống nhau, nó trả về `-1L`. API được bổ sung từ Java 12, nên đã là API tiêu chuẩn và dùng được bình thường trong Java 17.

Điểm quan trọng là **`Files.mismatch` so sánh byte của tệp**, không giải mã ký tự, không chuẩn hóa xuống dòng và không bỏ qua khoảng trắng. Nếu hai tệp chứa cùng văn bản nhưng được lưu bằng charset hoặc line ending khác nhau, phương thức vẫn có thể báo khác biệt. Khi mục tiêu là so sánh văn bản theo ngữ nghĩa, cần giải mã bằng charset đã xác định và áp dụng quy tắc chuẩn hóa phù hợp trước khi so sánh.

## 1. Files.mismatch làm gì?

Cú pháp:

~~~java
long position = Files.mismatch(Path path, Path path2);
~~~

Phương thức nhận hai đối tượng `Path` và tìm vị trí đầu tiên mà nội dung của hai tệp khác nhau.

| Kết quả | Ý nghĩa |
| --- | --- |
| `-1L` | Hai tệp có cùng nội dung byte; nếu chúng là cùng một tệp, kết quả cũng là `-1L`. |
| `0L` | Byte đầu tiên đã khác nhau. |
| `n > 0` | Byte tại offset `n` là vị trí khác nhau đầu tiên; các byte trước đó giống nhau. |
| `sizeOfSmallerFile` | Một tệp là tiền tố hoàn chỉnh của tệp kia: mọi byte trong tệp ngắn hơn đều giống, nhưng tệp còn lại có thêm dữ liệu. |

Vị trí được tính từ **0**, theo đơn vị **byte**, không phải ký tự, dòng hoặc chỉ số UTF-16. Kiểu trả về là `long` để hỗ trợ tệp lớn hơn giới hạn của `int`.

Ví dụ:

~~~java
Path first = Path.of("first.bin");
Path second = Path.of("second.bin");

long mismatch = Files.mismatch(first, second);

if (mismatch == -1L) {
    System.out.println("Hai tệp giống hệt nội dung byte.");
} else {
    System.out.println("Byte khác nhau đầu tiên ở offset " + mismatch);
}
~~~

Phương thức ném `IOException` nếu xảy ra lỗi I/O, ví dụ không mở được tệp hoặc có lỗi khi đọc. Vì vậy, thường gọi nó trong phương thức khai báo `throws IOException` hoặc xử lý ngoại lệ phù hợp.

## 2. Ví dụ cơ bản: hai tệp giống nhau và khác nhau

Giả sử có hai tệp:

**`first.txt`**

~~~text
Java 17
Files API
~~~

**`second.txt`**

~~~text
Java 17
Files API
~~~

So sánh:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareFiles {
    public static void main(String[] args) throws IOException {
        Path first = Path.of("first.txt");
        Path second = Path.of("second.txt");

        long mismatch = Files.mismatch(first, second);

        if (mismatch == -1L) {
            System.out.println("Files are identical.");
        } else {
            System.out.println("First mismatch at byte " + mismatch);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 CompareFiles.java
java CompareFiles
~~~

Nếu hai tệp có cùng byte, kết quả:

~~~text
Files are identical.
~~~

Nếu sửa một ký tự trong `second.txt`, kết quả sẽ là offset của byte khác nhau đầu tiên. Nếu ký tự khác nằm trong UTF-8 và chiếm nhiều byte, offset vẫn là vị trí byte đầu tiên khác, không phải vị trí ký tự mà người đọc nhìn thấy.

## 3. Vị trí mismatch là offset byte bắt đầu từ 0

Ví dụ hai nội dung ASCII:

~~~text
Tệp A: c a t
Offset: 0 1 2

Tệp B: c u t
Offset: 0 1 2
        | ^
        Byte đầu tiên khác nhau ở offset 1.
~~~

Có thể tái tạo trường hợp này bằng Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path a = Files.createTempFile("compare-a-", ".txt");
Path b = Files.createTempFile("compare-b-", ".txt");

try {
    Files.writeString(a, "cat", StandardCharsets.UTF_8);
    Files.writeString(b, "cut", StandardCharsets.UTF_8);

    System.out.println(Files.mismatch(a, b)); // 1
} finally {
    Files.deleteIfExists(a);
    Files.deleteIfExists(b);
}
~~~

Vì các ký tự trong ví dụ thuộc ASCII, mỗi ký tự UTF-8 chiếm một byte. Byte tại offset 0 (chữ c) giống nhau; byte tại offset 1 (chữ a và u) khác nhau.

**Không suy luận offset byte thành số ký tự.** Với tiếng Việt hoặc ký tự Unicode khác, một code point UTF-8 có thể chiếm nhiều byte; offset mismatch có thể nằm giữa dãy byte mã hóa của một ký tự.

## 4. Khi một tệp là tiền tố của tệp kia

Không phải lúc nào hai tệp cũng có một byte khác nhau ở vị trí mà cả hai đều có dữ liệu. Trường hợp một tệp kết thúc sớm hơn cũng được xem là mismatch.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path shortFile = Files.createTempFile("short-", ".txt");
Path longFile = Files.createTempFile("long-", ".txt");

try {
    Files.writeString(shortFile, "Java", StandardCharsets.UTF_8);
    Files.writeString(longFile, "Java 17", StandardCharsets.UTF_8);

    System.out.println(Files.mismatch(shortFile, longFile)); // 4
} finally {
    Files.deleteIfExists(shortFile);
    Files.deleteIfExists(longFile);
}
~~~

Nội dung byte của `shortFile` là tiền tố của `longFile`. Bốn byte đầu giống nhau; tại offset 4, tệp ngắn hơn đã hết trong khi tệp dài hơn còn dấu cách và phần dữ liệu tiếp theo. Vì vậy, kết quả là độ dài tính theo byte của tệp ngắn hơn: `4L`.

Nếu hai tệp đều rỗng, kết quả là `-1L`. Nếu một tệp rỗng và tệp kia có dữ liệu, kết quả là `0L`.

| Tệp A | Tệp B | Kết quả |
| --- | --- | ---: |
| byte rỗng | byte rỗng | `-1L` |
| `"A"` | `"A"` | `-1L` |
| `"A"` | `"AB"` | `1L` |
| `"AB"` | `"A"` | `1L` |
| `"cat"` | `"cut"` | `1L` |
| `"cat"` | `"dog"` | `0L` |

## 5. Files.mismatch so sánh byte, không so sánh ký tự

Vì chủ đề nằm trong chương **Tệp và mã hóa ký tự**, cần phân biệt rõ:

- **So sánh byte:** kiểm tra chính xác dãy byte được lưu trong hai tệp.
- **So sánh văn bản:** giải mã byte thành ký tự bằng charset, sau đó so sánh theo quy tắc văn bản mà ứng dụng định nghĩa.

`Files.mismatch` thực hiện việc thứ nhất. Nó không biết tệp được tạo bằng UTF-8, UTF-16, ISO-8859-1 hay một charset khác.

### 5.1. Cùng văn bản, khác charset

Ký tự `é` có thể được mã hóa thành các byte khác nhau:

- UTF-8: hai byte `C3 A9`.
- ISO-8859-1: một byte `E9`.

Hai tệp có thể giải mã ra cùng ký tự `é` nếu mỗi tệp được đọc bằng charset tương ứng, nhưng `Files.mismatch` vẫn phát hiện byte khác nhau.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path utf8 = Files.createTempFile("utf8-", ".txt");
Path latin1 = Files.createTempFile("latin1-", ".txt");

try {
    Files.writeString(utf8, "café", StandardCharsets.UTF_8);
    Files.writeString(latin1, "café", StandardCharsets.ISO_8859_1);

    System.out.println(Files.mismatch(utf8, latin1) >= 0); // true

    String text1 = Files.readString(utf8, StandardCharsets.UTF_8);
    String text2 = Files.readString(latin1, StandardCharsets.ISO_8859_1);

    System.out.println(text1.equals(text2)); // true
} finally {
    Files.deleteIfExists(utf8);
    Files.deleteIfExists(latin1);
}
~~~

`Files.mismatch` cho biết hai tệp khác byte. Sau khi giải mã mỗi tệp bằng đúng charset, hai chuỗi Java lại bằng nhau. Đây không phải mâu thuẫn: hai phép so sánh đang trả lời hai câu hỏi khác nhau.

### 5.2. Cùng nội dung nhìn thấy, khác line ending

Hai tệp có thể hiển thị cùng hai dòng:

~~~text
File LF:
Line 1\n
Line 2\n

File CRLF:
Line 1\r\n
Line 2\r\n
~~~

Trong byte, line ending LF là `0A`; CRLF là hai byte `0D 0A`. Do đó, `Files.mismatch` báo khác nhau ngay tại byte đầu tiên thuộc line ending khác nhau.

Nếu mục tiêu là so sánh chính xác nội dung tệp, đây là kết quả đúng. Nếu mục tiêu là so sánh văn bản và coi LF với CRLF tương đương, phải chuẩn hóa line ending sau khi giải mã.

### 5.3. BOM và Unicode normalization

Hai tệp có thể chứa cùng văn bản hiển thị nhưng byte vẫn khác vì:

- Một tệp có BOM (byte order mark), tệp còn lại không có.
- Một tệp mã hóa ký tự bằng UTF-8, tệp kia dùng UTF-16.
- Một ký tự có thể được biểu diễn bằng dạng Unicode dựng sẵn hoặc chuỗi ký tự kết hợp dấu (*composed/decomposed*).
- Line ending hoặc khoảng trắng đầu/cuối khác nhau.

`Files.mismatch` không tự loại BOM, chuẩn hóa Unicode NFC/NFD hoặc bỏ khoảng trắng. Mọi quy tắc tương đương văn bản phải do ứng dụng xác định.

## 6. So sánh văn bản sau khi giải mã

Nếu cần xác định hai tệp có cùng văn bản theo một charset cụ thể, hãy đọc chúng thành `String` bằng charset rõ ràng:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareTextFiles {
    public static void main(String[] args) throws IOException {
        Path first = Path.of("first.txt");
        Path second = Path.of("second.txt");

        String text1 = Files.readString(first, StandardCharsets.UTF_8);
        String text2 = Files.readString(second, StandardCharsets.UTF_8);

        System.out.println(text1.equals(text2));
    }
}
~~~

`Files.readString(path, charset)` giải mã nội dung theo charset chỉ định. Nếu byte không hợp lệ đối với charset đó, việc giải mã có thể ném lỗi; không nên dùng charset mặc định của máy để tạo kết quả so sánh khó tái lập.

### 6.1. Bỏ khác biệt line ending theo chính sách

Nếu ứng dụng coi CRLF và LF tương đương, có thể chuẩn hóa trước khi so sánh:

~~~java
static String normalizeLineEndings(String text) {
    return text.replace("\r\n", "\n")
               .replace('\r', '\n');
}
~~~

Sử dụng:

~~~java
String text1 = Files.readString(first, StandardCharsets.UTF_8);
String text2 = Files.readString(second, StandardCharsets.UTF_8);

boolean sameText = normalizeLineEndings(text1)
    .equals(normalizeLineEndings(text2));
~~~

Chỉ chuẩn hóa line ending khi hợp đồng của ứng dụng cho phép. Nếu CRLF và LF có ý nghĩa riêng (ví dụ dữ liệu kiểm thử byte-exact, chữ ký số hoặc định dạng giao thức), không nên xóa khác biệt đó.

### 6.2. Chuẩn hóa Unicode khi cần so sánh tương đương chuẩn tắc

Trong Unicode, một ký tự có dấu có thể được biểu diễn theo nhiều chuỗi code point tương đương về mặt chuẩn tắc. Khi nghiệp vụ muốn coi những dạng chuẩn tắc đó như nhau, dùng `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

static String normalizeUnicode(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFC);
}
~~~

Sau khi giải mã đúng charset, có thể chuẩn hóa NFC rồi so sánh. Không nên tự động áp dụng chuẩn hóa Unicode cho mọi loại dữ liệu; quyết định phụ thuộc định nghĩa “giống nhau” của ứng dụng.

## 7. Dùng Files.mismatch cho tệp nhị phân

Với tệp nhị phân như ảnh, archive, PDF hoặc dữ liệu nhị phân do ứng dụng tạo, so sánh byte thường chính là điều cần làm. Không giải mã những dữ liệu này thành `String`.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareBinaryFiles {
    static boolean sameContent(Path first, Path second)
            throws IOException {
        return Files.mismatch(first, second) == -1L;
    }

    public static void main(String[] args) throws IOException {
        Path original = Path.of("image-original.png");
        Path downloaded = Path.of("image-downloaded.png");

        if (sameContent(original, downloaded)) {
            System.out.println("Binary content matches.");
        } else {
            System.out.println("Binary content differs.");
        }
    }
}
~~~

Ưu điểm của `Files.mismatch` là ứng dụng không cần tự đọc toàn bộ hai tệp vào hai mảng byte chỉ để so sánh. API có thể so sánh theo cách không cần nạp toàn bộ nội dung vào bộ nhớ. Chi tiết triển khai và hiệu năng phụ thuộc filesystem/provider; không nên suy ra một mức tốc độ cố định cho mọi môi trường.

## 8. Files.mismatch so với Arrays.equals và hash

Một cách đơn giản khác là đọc toàn bộ nội dung:

~~~java
byte[] firstBytes = Files.readAllBytes(first);
byte[] secondBytes = Files.readAllBytes(second);

boolean same = java.util.Arrays.equals(firstBytes, secondBytes);
~~~

`Arrays.equals` so sánh chính xác từng byte trong hai mảng, nhưng `readAllBytes` nạp toàn bộ nội dung mỗi tệp vào heap. Với tệp lớn, điều này có thể tốn nhiều bộ nhớ hoặc gây `OutOfMemoryError`.

| Cách | So sánh chính xác byte? | Bộ nhớ ứng dụng | Ghi chú |
| --- | --- | --- | --- |
| `Files.mismatch(path1, path2)` | Có | Không cần giữ toàn bộ hai tệp trong mảng byte của ứng dụng | API chuyên dụng để tìm offset mismatch. |
| `Files.readAllBytes` + `Arrays.equals` | Có | Tỷ lệ với tổng kích thước dữ liệu được đọc | Hữu ích với tệp nhỏ hoặc khi cần xử lý byte sau khi đọc. |
| So sánh hash/checksum | Không thể kết luận tuyệt đối chỉ từ hash | Thường nhỏ hơn so với giữ toàn bộ nội dung | Hash giống nhau là bằng chứng thực tế mạnh tùy thuật toán, nhưng về nguyên tắc vẫn có khả năng va chạm. |

Nếu mục tiêu cuối cùng là xác nhận hai tệp byte-identical, `Files.mismatch` cho câu trả lời trực tiếp và không có vấn đề va chạm hash.

### 8.1. Khi nào dùng checksum?

Checksum hoặc cryptographic hash hữu ích khi cần:

- Lưu fingerprint của tệp để kiểm tra về sau.
- Trao đổi digest qua mạng thay vì trao đổi toàn bộ tệp.
- Xác minh dữ liệu nhận được với digest được công bố.

Tuy nhiên, hai hash bằng nhau không phải chứng minh toán học tuyệt đối rằng hai tệp giống byte. Nếu cần so sánh chính xác hai đường dẫn đang có, `Files.mismatch` là lựa chọn trực tiếp. Nếu cần bảo đảm nguồn gốc hoặc tính toàn vẹn trước đối thủ, phải dùng hash/MAC/chữ ký theo mô hình bảo mật phù hợp; `Files.mismatch` chỉ so sánh nội dung, không xác thực nguồn.

## 9. Xử lý lỗi I/O

`Files.mismatch` khai báo `throws IOException`. Một số lỗi thường gặp:

| Lỗi | Tình huống |
| --- | --- |
| `NoSuchFileException` | Một đường dẫn không tồn tại. |
| `AccessDeniedException` | Tiến trình không có quyền đọc tệp. |
| `FileSystemException` | Lỗi cụ thể từ filesystem hoặc provider. |
| `IOException` | Lỗi đọc/mở khác. |
| `NullPointerException` | Một trong hai đối số `Path` là null. |

Ví dụ xử lý:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareWithErrorHandling {
    public static void main(String[] args) {
        Path first = Path.of("first.dat");
        Path second = Path.of("second.dat");

        try {
            long mismatch = Files.mismatch(first, second);

            if (mismatch == -1L) {
                System.out.println("Identical");
            } else {
                System.out.println("Mismatch at byte " + mismatch);
            }
        } catch (IOException e) {
            System.err.println("Cannot compare files: " + e.getMessage());
        }
    }
}
~~~

Trong ứng dụng thực tế, không nên chỉ in thông báo rồi tiếp tục như thể hai tệp giống nhau. Hãy trả kết quả trạng thái rõ ràng hoặc truyền ngoại lệ lên tầng gọi để xử lý theo nghiệp vụ.

### 9.1. Đường dẫn và loại tệp

`Files.mismatch` nhận `Path`, nên có thể dùng với filesystem provider tương ứng. Trong ứng dụng thông thường, nên truyền đường dẫn tới **tệp thường** (*regular file*). Theo hợp đồng API, hành vi khi một hoặc cả hai đường dẫn không trỏ tới tệp thường là implementation-specific; không nên dựa vào kết quả cụ thể cho directory, device hoặc loại filesystem đặc biệt.

Kiểm tra trước có thể giúp báo lỗi dễ hiểu:

~~~java
if (!Files.isRegularFile(first) || !Files.isRegularFile(second)) {
    throw new IllegalArgumentException("Both paths must be regular files");
}
long mismatch = Files.mismatch(first, second);
~~~

`Files.isRegularFile` mặc định theo symbolic link. Việc kiểm tra trước không loại bỏ mọi race condition: tệp có thể bị thay đổi hoặc thay thế sau khi kiểm tra. Nếu môi trường có nhiều tiến trình đồng thời chỉnh sửa tệp, cần quản lý quyền sở hữu, khóa hoặc quy trình snapshot ở tầng ứng dụng.

### 9.2. Không có snapshot giao dịch tự động

`Files.mismatch` đọc nội dung từ hai đường dẫn trong lúc thực thi. Phương thức không hứa tạo một snapshot giao dịch bất biến nếu một tiến trình khác đang sửa các tệp cùng thời điểm. Nếu cần kết quả so sánh có ý nghĩa ổn định:

1. Bảo đảm không có writer sửa hai tệp trong thời gian so sánh.
2. So sánh các bản sao/snapshot đã được tạo và chốt.
3. Dùng cơ chế khóa hoặc quản lý phiên bản tệp nếu nhiều tiến trình cùng thao tác.

Không nên coi `Files.mismatch` là một thao tác đồng bộ hóa filesystem.

## 10. Ví dụ hoàn chỉnh: so sánh hai đường dẫn từ command line

Tạo tệp **`FileMismatchCli.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileMismatchCli {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java FileMismatchCli <file1> <file2>");
            return;
        }

        Path first = Path.of(args[0]);
        Path second = Path.of(args[1]);

        long position = Files.mismatch(first, second);

        if (position == -1L) {
            System.out.println("IDENTICAL");
        } else {
            System.out.println("DIFFERENT");
            System.out.println("First mismatch byte offset: " + position);
        }
    }
}
~~~

Biên dịch:

~~~shell
javac --release 17 FileMismatchCli.java
~~~

Chạy:

~~~shell
java FileMismatchCli first.bin second.bin
~~~

Chương trình trả một trong hai trạng thái dễ dùng trong script:

- `IDENTICAL`: nội dung byte giống nhau.
- `DIFFERENT` và offset: có byte khác nhau hoặc một tệp là tiền tố của tệp còn lại.

Nếu đường dẫn không tồn tại hoặc không thể đọc, chương trình ném `IOException` và kết thúc với lỗi. Trong CLI dành cho người dùng cuối, có thể bắt ngoại lệ để in thông báo dễ hiểu và chọn exit code khác 0.

## 11. So sánh nội dung không đồng nghĩa so sánh metadata

`Files.mismatch` chỉ tập trung vào nội dung byte. Nó không so sánh:

- Tên tệp.
- Đường dẫn.
- Thời gian sửa đổi.
- Quyền truy cập hoặc owner.
- Kích thước block vật lý trên đĩa.
- Thuộc tính filesystem khác.

Hai tệp có tên và metadata khác nhau nhưng cùng byte vẫn có thể cho kết quả `-1L`. Ngược lại, hai tệp có cùng kích thước và timestamp nhưng khác một byte sẽ cho offset mismatch.

Nếu cần so sánh metadata, hãy dùng API tương ứng như `Files.size`, `Files.getLastModifiedTime` hoặc `Files.readAttributes`; không dùng `Files.mismatch` như một phép kiểm tra toàn bộ trạng thái filesystem.

## 12. Chọn so sánh byte hay so sánh văn bản?

| Mục tiêu | Cách làm phù hợp |
| --- | --- |
| Xác nhận hai bản sao binary giống từng byte | `Files.mismatch(path1, path2) == -1L` |
| Kiểm tra file tải xuống có đúng bản gốc không | `Files.mismatch`, hoặc kiểm tra digest đã xác thực theo yêu cầu hệ thống |
| So sánh hai file UTF-8, yêu cầu byte giống hệt | `Files.mismatch` |
| So sánh nội dung văn bản sau khi giải mã UTF-8 | `Files.readString(path, UTF_8)` rồi `String.equals` |
| Coi CRLF và LF là tương đương | Giải mã rồi chuẩn hóa line ending theo quy tắc đã thống nhất |
| Coi các dạng Unicode NFC/NFD là tương đương | Giải mã rồi chuẩn hóa bằng `Normalizer` |
| So sánh nội dung rất lớn theo ngữ nghĩa văn bản | Dùng `Reader`/`BufferedReader` hoặc parser streaming với charset rõ ràng |
| So sánh cả tên, quyền và timestamp | Đọc metadata riêng; `Files.mismatch` không làm việc đó |

Trước khi viết code, hãy trả lời câu hỏi: **“Giống nhau” nghĩa là giống từng byte, hay giống nội dung sau khi giải mã và chuẩn hóa?** Chọn sai loại so sánh có thể tạo ra kết quả đúng về kỹ thuật nhưng sai với ý nghĩa nghiệp vụ.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách tránh |
| --- | --- | --- |
| Coi giá trị trả về là số ký tự | API trả về byte offset. | Gọi nó là byte position/offset, không phải character index. |
| So sánh file UTF-8 và UTF-16 rồi mong cùng văn bản cho kết quả `-1L` | Hai encoding tạo ra byte khác nhau. | Giải mã mỗi tệp bằng charset đúng nếu mục tiêu là so sánh văn bản. |
| Cho rằng LF và CRLF giống nhau | Byte line ending khác nhau. | Chuẩn hóa line ending chỉ khi nghiệp vụ cho phép. |
| Nghĩ `-1L` nghĩa là hai path có cùng tên | Nó biểu thị cùng nội dung byte (hoặc cùng file), không phải cùng tên. | Dùng `Files.isSameFile` nếu cần kiểm tra identity của file. |
| Nghĩ cùng kích thước nghĩa là cùng nội dung | Một byte có thể khác dù kích thước giống nhau. | Dùng `Files.mismatch` hoặc digest phù hợp. |
| Đọc toàn bộ tệp lớn bằng `readAllBytes` chỉ để so sánh | Tốn bộ nhớ theo kích thước tệp. | Dùng `Files.mismatch` cho so sánh byte. |
| Bỏ qua `IOException` rồi coi hai tệp bằng nhau | Không đọc được không có nghĩa là giống nhau. | Biểu diễn lỗi riêng với kết quả equal/different. |
| Dùng cho directory hoặc loại file đặc biệt | Hành vi không phải lúc nào cũng được đặc tả như tệp thường. | Chỉ dùng với regular files hoặc định nghĩa xử lý riêng. |
| Tin kết quả khi file đang bị writer khác sửa | Không có snapshot giao dịch. | Khóa, snapshot hoặc bảo đảm nguồn không đổi trong lúc so sánh. |

## 14. Câu hỏi thường gặp

**`Files.mismatch` có từ Java mấy?**  
API được bổ sung từ Java 12, nên có sẵn trong Java 17.

**`Files.mismatch` trả về `-1` hay `-1L`?**  
Kiểu trả về là `long`; giá trị sentinel là `-1L`. So sánh với `-1L` thể hiện rõ kiểu.

**Offset mismatch tính từ 0 hay 1?**  
Từ 0. Byte đầu tiên có offset 0.

**Nếu một tệp ngắn hơn nhưng toàn bộ byte của nó giống phần đầu tệp kia thì sao?**  
Kết quả là kích thước theo byte của tệp ngắn hơn, tức vị trí mà tệp đó kết thúc.

**`Files.mismatch` có đọc file vào RAM toàn bộ không?**  
Ứng dụng không phải nạp toàn bộ hai tệp vào mảng byte. API được thiết kế để so sánh mà không cần giữ toàn bộ nội dung trong bộ nhớ; chi tiết triển khai tùy provider.

**Hai tệp hiển thị cùng nội dung nhưng kết quả khác nhau là vì sao?**  
Có thể khác charset, BOM, line ending, Unicode normalization hoặc khoảng trắng. `Files.mismatch` so sánh byte chính xác.

**`Files.mismatch` có so sánh tên và thời gian sửa đổi không?**  
Không. Nó so sánh nội dung tệp; metadata phải được kiểm tra bằng API khác.

**Có nên dùng hash thay cho `Files.mismatch`?**  
Hash phù hợp để lưu hoặc truyền fingerprint. Nếu cần xác nhận chính xác hai tệp đang có giống byte, `Files.mismatch` trả lời trực tiếp và không có vấn đề va chạm hash.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 API — Files.mismatch(Path, Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)): mô tả giá trị trả về, byte offset, trường hợp hai tệp là cùng một file và ngoại lệ I/O.
- [Java SE 17 API — Files.readString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readString(java.nio.file.Path,java.nio.charset.Charset)): đọc và giải mã văn bản theo charset được chỉ định.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8 và ISO-8859-1.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa chuỗi Unicode theo NFC, NFD, NFKC hoặc NFKD.
- [Java SE 17 API — Files.readAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAttributes(java.nio.file.Path,java.lang.Class,java.nio.file.LinkOption...)): đọc metadata khi ứng dụng cần so sánh thuộc tính ngoài nội dung.

**Nguyên tắc áp dụng:** Dùng `Files.mismatch` khi cần biết hai tệp có giống từng byte hay không và cần offset khác biệt đầu tiên. Khi bài toán nói về “cùng văn bản”, hãy giải mã bằng charset rõ ràng rồi quyết định có chuẩn hóa line ending, Unicode hoặc khoảng trắng hay không. Byte equality và text equality là hai hợp đồng khác nhau.
