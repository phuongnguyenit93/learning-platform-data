# `Files.mismatch` và so sánh nội dung hai tệp trong Java I/O

## 1. Khi nào hai tệp được xem là giống nhau?

Khi kiểm tra sao lưu, đồng bộ dữ liệu, phát hiện file bị thay đổi hoặc xác minh kết quả xuất dữ liệu, câu hỏi quan trọng thường là: **hai tệp có chứa đúng cùng một dãy byte theo cùng thứ tự không?**

Hai tệp có thể:

- Có **tên khác nhau** nhưng byte giống hệt nhau.
- Có **kích thước bằng nhau** nhưng một hoặc nhiều byte khác nhau.
- Có **thời gian sửa đổi** khác nhau nhưng nội dung byte không đổi.
- Chứa văn bản nhìn giống nhau nhưng khác byte vì charset, BOM, dạng chuẩn hóa Unicode hoặc cách xuống dòng.
- Chứa cùng giá trị logic nhưng cách biểu diễn nhị phân khác nhau, ví dụ metadata nằm ngay trong cấu trúc file.

Từ Java 12, lớp `java.nio.file.Files` cung cấp phương thức **`Files.mismatch(Path path, Path path2)`** để tìm **vị trí byte đầu tiên khác nhau** giữa hai tệp. Đây là API thích hợp khi mục tiêu là so sánh nội dung byte chứ không phải tên, kích thước hay ngày sửa.

**Tư duy nền tảng:** `Files.mismatch` kiểm tra *binary equality*, không tự kiểm tra hai tệp có “cùng ý nghĩa” về mặt văn bản, JSON, ảnh hoặc tài liệu.

## 2. Chữ ký phương thức và ý nghĩa giá trị trả về

Phương thức trong `java.nio.file.Files`:

```java
public static long mismatch(Path path, Path path2) throws IOException
```

Trong đó:

- `path` và `path2` là hai `Path` trỏ tới các tệp cần so sánh.
- Giá trị trả về kiểu **`long`** là **offset tính từ 0 của byte đầu tiên khác nhau**.
- Trả **`-1L`** khi không tìm thấy byte khác nhau và hai tệp có độ dài bằng nhau.
- Nếu một tệp là tiền tố byte chính xác của tệp kia nhưng **ngắn hơn**, kết quả là **kích thước byte của tệp ngắn hơn**, vì ở offset đó một bên đã hết byte.
- Lỗi truy cập/đọc tệp có thể phát sinh **`IOException`**; phương thức không trả một mã số đặc biệt để biểu diễn lỗi I/O.

Ví dụ với dãy byte:

```text
Tệp A: 10 20 30 40
Tệp B: 10 20 30 40     -> -1  (bằng nhau)
Tệp C: 10 20 99 40     ->  2  (khác byte thứ ba)
Tệp D: 10 20           ->  2  (D kết thúc trước A)
Tệp E: 99 20 30 40     ->  0  (khác ngay byte đầu)
Tệp F: [rỗng]          ->  0  (F là tiền tố rỗng của A)
```

Offset **bắt đầu từ 0**, không phải 1: byte thứ nhất có offset `0`, byte thứ ba có offset `2`. Kết quả `0` **không có nghĩa là hai tệp giống nhau**; chỉ duy nhất `-1L` biểu diễn không có mismatch.

Bảng đối chiếu:

| Kết quả | Cách hiểu |
| ---: | --- |
| `-1L` | Hai tệp có cùng độ dài và cùng byte ở mọi vị trí |
| `0L` | Khác ở byte đầu tiên, hoặc một tệp rỗng còn tệp kia không |
| `k >= 0` | Byte đầu tiên không tương ứng ở offset `k` |
| Ngoại lệ `IOException` | Không hoàn thành được việc so sánh vì lỗi I/O |

Phương thức không sửa nội dung tệp theo hợp đồng sử dụng thông thường; nhiệm vụ của nó là đọc và đối chiếu.

## 3. Ví dụ Java 17+ hoàn chỉnh: so sánh tệp giống, khác và tệp tiền tố

Ví dụ này dùng thư mục tạm và các byte đã biết trước để đầu ra có thể kiểm chứng. Tạo file **`FilesMismatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilesMismatchDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("files-mismatch-");
        Path base = folder.resolve("base.bin");
        Path same = folder.resolve("same.bin");
        Path different = folder.resolve("different.bin");
        Path shorter = folder.resolve("shorter.bin");
        Path first = folder.resolve("first.bin");
        Path empty = folder.resolve("empty.bin");

        try {
            Files.write(base, new byte[]{10, 20, 30, 40});
            Files.write(same, new byte[]{10, 20, 30, 40});
            Files.write(different, new byte[]{10, 20, 99, 40});
            Files.write(shorter, new byte[]{10, 20});
            Files.write(first, new byte[]{99, 20, 30, 40});
            Files.write(empty, new byte[0]);

            System.out.println("same=" + Files.mismatch(base, same));
            System.out.println("different="
                    + Files.mismatch(base, different));
            System.out.println("shorter="
                    + Files.mismatch(base, shorter));
            System.out.println("first=" + Files.mismatch(base, first));
            System.out.println("empty=" + Files.mismatch(base, empty));
            System.out.println("self=" + Files.mismatch(base, base));
        } finally {
            Files.deleteIfExists(base);
            Files.deleteIfExists(same);
            Files.deleteIfExists(different);
            Files.deleteIfExists(shorter);
            Files.deleteIfExists(first);
            Files.deleteIfExists(empty);
            Files.deleteIfExists(folder);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FilesMismatchDemo.java
java FilesMismatchDemo
```

Kết quả khi các thao tác tệp tạm đều thành công:

```text
same=-1
different=2
shorter=2
first=0
empty=0
self=-1
```

Giải thích:

1. `same` và `base` có byte bằng nhau dù là **hai đường dẫn** và hai tệp được tạo riêng biệt.
2. `different` có cùng kích thước nhưng byte tại index `2` là `99` thay cho `30`.
3. `shorter` khớp hai byte đầu rồi kết thúc, nên mismatch nằm ở index `2`.
4. `first` khác ngay index `0`.
5. `empty` không có byte để khớp với `base`, do đó index `0` là vị trí bắt đầu khác nhau.
6. So sánh tệp với chính nó cho kết quả `-1`.

Chương trình cố gắng xóa các tệp tạm trong `finally`; nếu hệ thống không cho tạo/đọc/xóa tệp, thao tác có thể báo `IOException`. Đối với sản phẩm thực tế, cần xử lý lỗi cleanup cẩn thận để không che nguyên nhân chính, và tuyệt đối không tự động xóa tệp người dùng.

## 4. Thuật toán về mặt logic: so byte cho tới khi phát hiện khác biệt

Có thể hình dung `Files.mismatch(a, b)` theo thuật toán:

```text
offset = 0
Lặp:
    lấy byte tiếp theo từ A và B
    nếu cả hai EOF: trả -1
    nếu chỉ một bên EOF: trả offset
    nếu hai byte khác nhau: trả offset
    offset = offset + 1
```

Đây là **mô hình ngữ nghĩa**, không phải mã nguồn triển khai chính thức của JDK. Java có thể tối ưu cách đọc, bộ đệm và phương pháp đối chiếu, nhưng kết quả API phải phản ánh vị trí mismatch đầu tiên.

Nếu hai tệp khác nhau ngay byte đầu, không cần xét ý nghĩa các byte sau để xác định kết quả. Nếu hai tệp giống nhau hoàn toàn, hệ thống phải có đủ thông tin để xác nhận nội dung toàn bộ phạm vi cần so sánh. Không dựa vào một giả định cố định rằng API sẽ dùng bao nhiêu RAM, chia block bao nhiêu byte hoặc gọi hệ điều hành bao nhiêu lần: đó là chi tiết triển khai.

Vì offset là `long`, API có thể biểu diễn vị trí lớn hơn giới hạn `int`, phù hợp khi làm việc với các tệp rất lớn.

## 5. So sánh nội dung với `Files.size`, tên và thời gian sửa đổi

Các API trả lời **các câu hỏi khác nhau**:

| API/thuộc tính | Cho biết điều gì? | Có chứng minh nội dung giống hệt không? |
| --- | --- | --- |
| `Files.mismatch(a, b) == -1L` | Byte trong hai tệp bằng nhau tại thời điểm được so sánh | **Có**, với giả định nguồn ổn định trong lúc kiểm tra |
| `Files.size(a) == Files.size(b)` | Hai kích thước theo byte bằng nhau | **Không** |
| `Files.getLastModifiedTime(path)` | Timestamp do hệ thống tệp cung cấp | **Không** |
| `a.equals(b)` | Hai đối tượng `Path` bằng nhau về cách biểu diễn theo provider | **Không** nếu là hai tệp khác đường dẫn; nó không so byte |
| `Files.isSameFile(a, b)` | Hai đường dẫn được xác định trỏ tới **cùng một tệp** | Không so sánh nội dung của hai tệp khác nhau |
| So sánh tên file hoặc extension | Metadata hoặc quy ước đặt tên | **Không** |

Ví dụ:

```text
A.bin = 01 02 03 04   -> size = 4
B.bin = 01 02 99 04   -> size = 4

Files.size(A) == Files.size(B)       -> true
Files.mismatch(A, B)                 -> 2
```

**Tối ưu đơn giản:** Nếu chỉ cần biết **có bằng nhau hay không**, có thể kiểm tra kích thước trước. Nếu hai kích thước khác nhau thì hai tệp chắc chắn không giống hệt byte, không cần gọi `mismatch`. Nếu kích thước bằng nhau vẫn phải so nội dung. Tuy nhiên, nếu mục tiêu là **tìm vị trí khác nhau đầu tiên**, không được chỉ lấy kích thước làm offset: hai tệp có thể vừa khác kích thước **vừa** có byte khác sớm hơn.

Ví dụ A có byte `01 02 03`, B có `01 99 03 04`. Mismatch là `1`, **không phải** `3` (kích thước tệp ngắn).

## 6. `mismatch` đếm byte, không đếm ký tự, dòng hoặc code point

Java `String` và các API đọc văn bản vận hành theo ký tự Unicode, nhưng `Files.mismatch` so **byte của tệp gốc**. Không có tham số `Charset` và không có bước chuẩn hóa văn bản ngầm.

Với UTF-8, ký tự có dấu có thể chiếm nhiều byte. Ví dụ:

```text
"café" mã hóa UTF-8:
63 61 66 C3 A9
          ^^
index: 0  1  2  3  4

"cafe\u0301" mã hóa UTF-8:
63 61 66 65 CC 81
          ^^
index: 0  1  2  3  4  5
```

Hai chuỗi có thể **trông giống nhau** vì một chuỗi dùng ký tự `é` dựng sẵn (`U+00E9`) và chuỗi còn lại dùng `e` cộng dấu sắc kết hợp (`U+0065` và `U+0301`). Tuy nhiên, byte đầu tiên khác nhau ở **offset 3**.

Tương tự, hai tệp có nội dung nhìn như cùng các dòng nhưng một bên dùng `LF` (byte `0A`) còn bên kia dùng `CRLF` (byte `0D 0A`) sẽ khác nhau ngay dấu xuống dòng đầu tiên.

**Các khác biệt thường bị bỏ sót khi nhìn bằng trình soạn thảo:** BOM UTF-8 ở đầu file, dấu cách cuối dòng, tab so với khoảng trắng, Unicode NFC/NFD, dấu xuống dòng, charset, kết thúc file có hoặc không có newline.

Nếu ứng dụng muốn hỏi “văn bản sau khi chuẩn hóa có giống nhau không?”, cần một bài toán **so sánh ngữ nghĩa văn bản** khác, không phải nhiệm vụ của `Files.mismatch`.

## 7. Ví dụ chạy được: văn bản nhìn giống nhưng byte khác

Tạo **`TextBytesMismatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;

public class TextBytesMismatchDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("text-mismatch-");
        Path composed = dir.resolve("composed.txt");
        Path decomposed = dir.resolve("decomposed.txt");
        Path lf = dir.resolve("lf.txt");
        Path crlf = dir.resolve("crlf.txt");

        try {
            Files.writeString(composed, "caf\u00E9", StandardCharsets.UTF_8);
            Files.writeString(decomposed, "cafe\u0301",
                    StandardCharsets.UTF_8);
            Files.writeString(lf, "A\nB", StandardCharsets.UTF_8);
            Files.writeString(crlf, "A\r\nB", StandardCharsets.UTF_8);

            System.out.println("unicode-offset="
                    + Files.mismatch(composed, decomposed));
            System.out.println("newlines-offset="
                    + Files.mismatch(lf, crlf));

            String left = Normalizer.normalize(
                    Files.readString(composed, StandardCharsets.UTF_8),
                    Normalizer.Form.NFC);
            String right = Normalizer.normalize(
                    Files.readString(decomposed, StandardCharsets.UTF_8),
                    Normalizer.Form.NFC);
            System.out.println("normalized-text-equal="
                    + left.equals(right));
        } finally {
            Files.deleteIfExists(composed);
            Files.deleteIfExists(decomposed);
            Files.deleteIfExists(lf);
            Files.deleteIfExists(crlf);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy trên Java 17:

```bash
javac -encoding UTF-8 TextBytesMismatchDemo.java
java TextBytesMismatchDemo
```

Đầu ra:

```text
unicode-offset=3
newlines-offset=1
normalized-text-equal=true
```

Đây không phải mâu thuẫn. `Files.mismatch` trả lời **“byte có giống hệt nhau không?”**, còn phép chuẩn hóa `Normalizer.Form.NFC` rồi `String.equals` trả lời **“chuỗi đã chuẩn hóa có cùng đơn vị mã UTF-16 không?”**.

Khi so sánh văn bản, phải xác định trước hợp đồng: có bỏ qua chữ hoa/chữ thường, dấu cách, dòng trống, thứ tự dòng hoặc các chi tiết định dạng khác hay không? Mỗi lần bỏ qua một khác biệt, bạn thay đổi **định nghĩa về sự bằng nhau**. Không chuẩn hóa tùy tiện nếu mục tiêu là sao lưu hoặc xác minh file nguyên bản.

## 8. Cách viết hàm tiện ích trả lời “hai tệp có giống nhau không?”

Nếu chỉ cần boolean và muốn ném lỗi lên lớp gọi để xử lý, dùng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileContentEquality {
    private FileContentEquality() {
    }

    public static boolean sameBytes(Path first, Path second)
            throws IOException {
        return Files.mismatch(first, second) == -1L;
    }
}
```

Tạo tệp **`FileContentEquality.java`**, biên dịch:

```bash
javac FileContentEquality.java
```

Đây là class tiện ích **biên dịch được nhưng không có `main`**, vì vậy không chạy trực tiếp bằng `java FileContentEquality`. Nó dùng được khi tích hợp vào chương trình khác:

```java
if (FileContentEquality.sameBytes(source, copy)) {
    System.out.println("Nội dung byte giống nhau");
} else {
    System.out.println("Nội dung byte khác nhau");
}
```

Đây là đoạn minh họa: `source` và `copy` phải được khai báo với kiểu `Path`; phương thức gọi xử lý `IOException`.

**Không bắt `IOException` rồi trả `false` vô điều kiện** nếu ý nghĩa `false` là “đã kiểm tra và chắc chắn khác nhau”. Có ít nhất ba trạng thái cần phân biệt:

- Đã kiểm tra, byte **bằng nhau**.
- Đã kiểm tra, byte **khác nhau**.
- **Không thể kiểm tra** vì lỗi I/O.

Có thể dùng `boolean` + `throws IOException` như trên, hoặc một kiểu kết quả giàu thông tin hơn nếu ứng dụng cần phân biệt lỗi, thời gian kiểm tra và vị trí mismatch.

## 9. Ví dụ công cụ dòng lệnh kiểm tra hai tệp

Tệp **`CompareFilesCli.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CompareFilesCli {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java CompareFilesCli <first> <second>");
            return;
        }

        Path first = Path.of(args[0]);
        Path second = Path.of(args[1]);

        try {
            long offset = Files.mismatch(first, second);

            if (offset == -1L) {
                System.out.println("Hai tệp giống hệt nhau theo byte.");
            } else {
                System.out.println("Byte khác đầu tiên tại offset " + offset);
                System.out.println("Kích thước A = " + Files.size(first));
                System.out.println("Kích thước B = " + Files.size(second));
            }
        } catch (IOException ex) {
            System.err.println("Không thể so sánh: " + ex.getMessage());
        }
    }
}
```

Biên dịch và gọi với **hai đường dẫn thực tế**:

```bash
javac -encoding UTF-8 CompareFilesCli.java
java CompareFilesCli first.bin second.bin
```

Không có đầu ra cố định: kết quả phụ thuộc hai tệp được truyền vào và trạng thái filesystem. Nếu một tệp không tồn tại hoặc không đọc được, `Files.mismatch` có thể ném `IOException` (ví dụ `NoSuchFileException`), và chương trình báo không thể so sánh thay vì khẳng định hai tệp khác nhau.

Với công cụ CLI dùng trong automation, cần quyết định **mã thoát (exit code)** cho ba trường hợp bằng nhau, khác nhau và lỗi; ví dụ trên mới in thông báo để minh họa API, không định nghĩa mã thoát đặc biệt.

## 10. Khi nào chọn `Files.mismatch`, `Arrays.equals`, so sánh chuỗi hoặc hash?

### So sánh trực tiếp hai file theo byte

`Files.mismatch(a, b)` là lựa chọn rõ ràng khi muốn vị trí byte đầu tiên khác nhau. Nó không đòi hỏi ứng dụng tự đọc cả hai tệp vào hai mảng byte.

### `Files.readAllBytes` + `Arrays.equals`

```java
boolean equal = Arrays.equals(
        Files.readAllBytes(first),
        Files.readAllBytes(second));
```

Đây là **đoạn minh họa**, với `Path first` và `second` đã khai báo, cần import `java.util.Arrays`, `java.nio.file.Files` và xử lý `IOException`. Nó dễ hiểu và hữu ích cho tệp **nhỏ**, nhưng tạo mảng byte chứa toàn bộ nội dung cả hai tệp trong RAM; với tệp lớn có nguy cơ tiêu tốn bộ nhớ rất cao. `Arrays.equals` chỉ cho kết quả bằng/khác, **không trả offset đầu tiên**.

Nếu hai mảng byte đã tồn tại trong RAM từ bước trước, `Arrays.equals` có thể là cách trực tiếp hơn là phải tạo tệp tạm để dùng `mismatch`.

### `Files.readString` + `String.equals`

```java
boolean sameText = Files.readString(first, StandardCharsets.UTF_8)
        .equals(Files.readString(second, StandardCharsets.UTF_8));
```

Đây là **đoạn minh họa**, cần các import và xử lý `IOException`. Cách này so văn bản sau khi **giải mã UTF-8**, không tự chuẩn hóa Unicode, newline hoặc bỏ khoảng trắng. Nó cũng cần bộ nhớ để giữ cả hai chuỗi.

Vì được giải mã sang ký tự, bài toán này khác so sánh byte: có thể có những mã byte khác nhau nhưng cùng biểu diễn văn bản sau các bước xử lý nhất định. Nếu tệp có byte không hợp lệ với charset, việc đọc văn bản có thể không thành công.

### Hash/checksum

Với việc xác minh nhiều file, hệ thống phân tán hay kiểm tra dữ liệu lớn lặp lại, có thể sử dụng hash như **SHA-256** để tạo dấu vân tay nội dung. Tuy nhiên:

- Cùng hash tạo ra từ thuật toán xác định trên cùng byte; hash khác nhau chứng tỏ byte khác nhau.
- Hai hash bằng nhau mang ý nghĩa **xác suất va chạm cực nhỏ** với thuật toán mạnh, nhưng không phải một chứng minh toán học tuyệt đối rằng mọi byte giống nhau.
- Hash không trực tiếp cho biết **offset mismatch**.
- Hash đã lưu từ trước chỉ đáng tin khi nguồn hash và quy trình tính toán được tin cậy; nếu cần chứng minh nguồn gốc/chống giả mạo, còn phải xét chữ ký số hoặc mã xác thực thông điệp thích hợp.

Khi chỉ cần đối chiếu chính xác **hai tệp hiện có tại chỗ**, `Files.mismatch` thường tránh được việc tự thiết kế vòng lặp hash hoặc tải hết nội dung vào RAM.

## 11. Hiệu năng: khác ở đầu và giống hệt là hai tình huống khác nhau

Việc phát hiện một mismatch ở đầu tệp có thể kết thúc sớm hơn so với phải xác minh hàng gigabyte nội dung giống nhau. Tuy vậy, tốc độ phụ thuộc nhiều vào:

- Kích thước và vị trí byte khác đầu tiên.
- Loại lưu trữ: SSD, HDD, network filesystem, cloud mount...
- Bộ đệm hệ điều hành/JVM và việc dữ liệu đã được cache hay chưa.
- Chi phí mở file, phân quyền, thao tác metadata.
- Các thay đổi đồng thời lên file trong lúc đọc.

**Không suy đoán** thời gian chạy từ số ký tự trong tên file hoặc kích thước metadata. Nếu hiệu năng quan trọng, benchmark với kích thước và môi trường thật.

Một cách tối ưu hợp lý khi chỉ hỏi boolean:

```java
static boolean equalWithSizeHint(Path a, Path b)
        throws IOException {
    if (Files.size(a) != Files.size(b)) {
        return false;
    }
    return Files.mismatch(a, b) == -1L;
}
```

Đây là **phương thức minh họa**, cần import `Path`, `Files` và `IOException`, đặt trong class. Việc kiểm tra size chỉ là **bộ lọc sớm**, không thay thế kiểm tra nội dung khi size bằng nhau. Với tệp bị sửa đồng thời giữa hai lời gọi, kết quả size và mismatch có thể phản ánh hai thời điểm khác nhau; vì vậy đây không phải cơ chế chứng nhận snapshot bất biến.

Nếu cần báo **offset đầu tiên**, cứ gọi `Files.mismatch` và dùng trực tiếp kết quả thay vì chỉ lấy size.

## 12. Ngoại lệ và tài nguyên: phân biệt “khác nhau” với “không đọc được”

`Files.mismatch` khai báo `throws IOException`; lỗi có thể xảy ra vì:

- Một đường dẫn không tồn tại hoặc bị đổi tên trong lúc thao tác.
- Không đủ quyền đọc một nguồn.
- Thiết bị hoặc filesystem mạng lỗi.
- Dữ liệu nguồn bị thay đổi trong quá trình so sánh, khiến kết quả không còn đại diện cho một snapshot nhất quán.
- Nguồn không có hành vi như một tệp thông thường theo quy định của provider.

**Không dùng `-1L` hay `0L` làm giá trị “lỗi” trong phần catch.** Hai giá trị này đã mang ý nghĩa thành công hợp lệ của thuật toán so sánh.

Mẫu xử lý:

```java
try {
    long mismatch = Files.mismatch(left, right);
    if (mismatch == -1L) {
        // Thành công: cùng byte
    } else {
        // Thành công: khác byte tại mismatch
    }
} catch (IOException ex) {
    // Không thể hoàn tất phép so sánh; giữ nguyên lỗi để xử lý
}
```

Đây là **đoạn minh họa**, `left`/`right` phải là `Path`, cần import `Files` và `IOException`.

`Files.mismatch` tự tổ chức việc đọc theo API; bạn **không cần** và cũng **không nên** mở một `InputStream` cho từng tệp chỉ để truyền vào `mismatch`, vì phương thức nhận `Path`. Nếu cần đọc byte xung quanh offset khác đầu tiên, đó là tác vụ riêng có thể dùng `SeekableByteChannel` hoặc `FileChannel`, cần nhớ đóng tài nguyên do bạn tự mở bằng `try-with-resources`.

## 13. Các giới hạn quan trọng của phép so sánh

### Thay đổi đồng thời và tính nhất quán

Hai tệp có thể bị tiến trình khác sửa trong lúc `mismatch` đang chạy. Phương thức này **không phải transaction** và không bảo đảm hai tệp được so từ hai snapshot bất biến tại cùng một thời điểm.

Nếu cần xác minh backup hoặc artifact đáng tin cậy:

1. Đảm bảo mỗi tệp đã được ghi hoàn chỉnh và writer đã đóng.
2. Dùng snapshot hoặc cơ chế khóa/phối hợp ghi khi hệ thống hỗ trợ và yêu cầu tính nhất quán.
3. So sánh trên nguồn ổn định; nếu đầu vào còn đang ghi, dời bước verify sang sau điểm commit.
4. Với dữ liệu cần chứng minh lâu dài, lưu checksum/hash và metadata theo quy trình phù hợp.

### Symbolic link và danh tính của tệp

`Path` biểu diễn đường dẫn; hai đường dẫn có thể cùng trỏ đến một tệp thông qua hard link, symbolic link hoặc quy tắc hệ thống tệp. Nếu cần hỏi **“có phải cùng thực thể file không?”**, xem `Files.isSameFile`. Nếu cần hỏi **“byte có giống nhau không?”**, xem `Files.mismatch`.

Đừng nhầm bằng nhau về nội dung với bằng nhau về danh tính. Hai bản sao ở hai thư mục khác nhau có thể byte hoàn toàn giống nhau nhưng vẫn là hai tệp độc lập.

### Không kiểm tra tính hợp lệ của định dạng

Hai file ZIP, PDF, JSON hoặc ảnh có thể có cùng byte nhưng cùng bị hỏng. `Files.mismatch` không xác nhận tệp mở được bằng ứng dụng tương ứng. Ngược lại, hai ảnh hiển thị giống nhau nhưng encode khác vẫn bị đánh giá là khác byte.

**So sánh byte**, **so sánh cấu trúc** và **so sánh ý nghĩa** là ba yêu cầu khác nhau; cần chọn công cụ theo mức bảo đảm mong muốn.

## 14. Tình huống thực tế: xác minh bản sao sau khi ghi

Giả sử ứng dụng vừa sao chép một tệp và muốn xác nhận nội dung tại thời điểm kiểm tra:

```java
Path source = Path.of("source.dat");
Path backup = Path.of("backup.dat");

Files.copy(source, backup,
        StandardCopyOption.REPLACE_EXISTING);

long mismatch = Files.mismatch(source, backup);
if (mismatch != -1L) {
    throw new IOException("Bản sao khác từ offset " + mismatch);
}
```

Đây là **đoạn minh họa**, cần import `Path`, `Files`, `StandardCopyOption` và `IOException`, và chỉ nên chạy với đường dẫn/việc ghi đè đã được người dùng cho phép. `Files.copy` có thể thay thế tệp đích và bản thân thao tác sao chép không được mặc định là atomic; nếu có lỗi giữa quá trình, file đích có thể chưa hoàn chỉnh. Sau khi copy thành công, `mismatch` kiểm tra lại byte của hai tệp.

**Quan trọng:** Kết quả `-1` không tự bảo đảm bản backup đã được **fsync** xuống ổ lưu trữ, sẽ tồn tại sau mất điện hay không thể bị thay đổi ngay sau lần kiểm tra. Độ bền dữ liệu và chống sửa đổi cần biện pháp bổ sung ở tầng filesystem và quy trình vận hành.

Với quy trình backup nghiêm ngặt, có thể tạo tệp tạm, ghi xong, xác thực nội dung rồi mới công bố tên backup chính thức.

## 15. Lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `mismatch == 0` nghĩa là bằng nhau | Offset 0 là byte khác đầu tiên | Chỉ `mismatch == -1L` nghĩa là bằng nhau |
| Coi offset là dòng hoặc ký tự | API trả offset **byte** | Chỉ tính dòng/ký tự sau khi giải mã và ánh xạ đúng |
| Hai file cùng size nên chắc giống nhau | Cùng size vẫn có thể khác byte | Dùng `Files.mismatch` hoặc so nội dung |
| Lấy size ngắn làm mismatch trong mọi trường hợp khác size | Hai file có thể khác byte trước lúc file ngắn kết thúc | Dùng kết quả thực tế từ `mismatch` |
| So `Path.equals` để xác minh bản sao | So cách biểu diễn đường dẫn, không so byte | Dùng `Files.mismatch` |
| Dùng `Files.isSameFile` thay phép so nội dung | Kiểm tra danh tính tệp | So byte nếu cần chứng minh nội dung |
| Bắt `IOException` rồi trả `false` | Không đọc được bị báo thành chắc chắn khác nhau | Để lỗi lan truyền hoặc trả trạng thái lỗi rõ ràng |
| Đọc hết file khổng lồ bằng `readAllBytes` | Tốn RAM không cần thiết | `Files.mismatch` khi so tệp với tệp |
| Mong `mismatch` bỏ qua BOM/newline/khoảng trắng | Không có chuẩn hóa văn bản | Chọn giải pháp so sánh văn bản riêng |
| Dùng hash làm offset mismatch | Hash chỉ là dấu vân tay nội dung | `Files.mismatch` để lấy offset |
| So file còn đang bị ghi rồi coi kết quả vĩnh viễn đúng | Nguồn thay đổi giữa và sau phép đọc | Kiểm tra trên snapshot hoặc nguồn ổn định |
| Coi `mismatch == -1` là file đã được lưu an toàn vĩnh viễn | Byte equality không đồng nghĩa durability | Quản lý flush, fsync/force, lưu trữ và commit |

## 16. Checklist và bài tự luyện

**Trước khi so sánh:**

- [ ] Chọn rõ: cần cùng **byte**, cùng **văn bản chuẩn hóa**, cùng **nội dung logic** hay cùng **thực thể tệp**?
- [ ] Xác minh hai đường dẫn đúng đối tượng và có quyền đọc.
- [ ] Đảm bảo nguồn đã ghi hoàn tất và ổn định nếu cần kết luận đáng tin.
- [ ] Nếu chỉ cần boolean, nhớ giá trị duy nhất biểu diễn bằng nhau là `-1L`.
- [ ] Nếu muốn biết vị trí đầu tiên khác nhau, dùng offset `long` trả về, bắt đầu từ 0.
- [ ] Xử lý `IOException` riêng, không biến lỗi thành kết quả khác byte.
- [ ] Với tệp lớn, tránh đọc tất cả vào RAM nếu không cần.
- [ ] Với văn bản, ghi rõ charset và quy tắc chuẩn hóa nếu bài toán không phải so byte thuần.

**Bài 1 — offset:** Tệp A chứa `00 11 22 33 44`, tệp B chứa `00 11 FF 33 44`. Dự đoán kết quả `Files.mismatch` rồi tự tạo hai tệp bằng `Files.write` để kiểm chứng. Đáp án: offset **`2`**.

**Bài 2 — tiền tố:** Tệp A chứa `41 42` (hai byte ASCII “AB”), tệp B chứa `41 42 43` (“ABC”). Tại sao mismatch là `2` chứ không phải `-1`? Vì tại offset 2, tệp A đã kết thúc nhưng B vẫn còn một byte.

**Bài 3 — cùng độ dài:** Tệp A chứa `01 02 03`, tệp B chứa `01 FF 03`. Cả hai đều dài 3 byte; hãy chứng minh kích thước không đủ để nhận định bình đẳng nội dung. `mismatch` phải trả **`1`**.

**Bài 4 — Unicode:** Tạo hai tệp UTF-8 chứa cùng từ nhìn như “café” theo dạng NFC và NFD. So sánh bằng `Files.mismatch` rồi đọc bằng `Files.readString`, chuẩn hóa với `Normalizer.Form.NFC` và dùng `equals`. Giải thích vì sao hai phép so sánh có thể đưa ra câu trả lời khác nhau.

**Ghi nhớ:** **`Files.mismatch(a, b)`** (Java 12+) trả **`-1L` khi hai tệp giống hệt theo byte**, hoặc **offset `long` bắt đầu từ 0** của byte khác đầu tiên; nếu một tệp là tiền tố của tệp kia thì offset là kích thước tệp ngắn. Phương thức không so metadata hay nội dung ngữ nghĩa, không tự bảo đảm snapshot/độ bền và có thể ném `IOException`.