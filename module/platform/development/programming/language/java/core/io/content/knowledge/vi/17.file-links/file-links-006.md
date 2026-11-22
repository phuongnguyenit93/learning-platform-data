# `Files.isSameFile` khác `Path.equals` trong Java NIO.2

## 1. Hai câu hỏi khác nhau

Khi làm việc với tệp trong Java, **đường dẫn** và **tệp thực tế** không phải cùng một khái niệm:

- `path1.equals(path2)` hỏi: **Hai đối tượng `Path` có biểu diễn đường dẫn bằng nhau theo quy tắc của `FileSystem` không?**
- `Files.isSameFile(path1, path2)` hỏi: **Hai đường dẫn có cùng trỏ tới một tệp/thực thể trên hệ thống tệp không?**

Một tệp có thể được truy cập bằng nhiều đường dẫn khác nhau: đường dẫn chứa `.`/`..`, đường dẫn tương đối và tuyệt đối, symbolic link hoặc hard link. Vì vậy, `Path.equals` có thể là `false` trong khi `Files.isSameFile` là `true`.

Đây là hai phép kiểm tra có **mục đích, chi phí và cách xử lý lỗi khác nhau**. Đừng thay thế chúng cho nhau chỉ vì cả hai trả về `boolean`.

## 2. `Path.equals(Object)`: so sánh biểu diễn đường dẫn

`Path` thuộc `java.nio.file`. Lệnh:

~~~java
boolean equalPaths = path1.equals(path2);
~~~

có các đặc điểm:

1. **Không truy cập hệ thống tệp** để tìm tệp; đường dẫn không cần tồn tại.
2. Việc so sánh phụ thuộc cách triển khai `FileSystem`: có hệ thống phân biệt chữ hoa/chữ thường, có hệ thống không. Không nên tự giả định mọi hệ điều hành có cùng quy tắc.
3. Đối tượng khác kiểu `Path` hoặc `Path` thuộc `FileSystem` khác thì kết quả là `false`.
4. Những thành phần như `.` và `..` **không mặc nhiên được chuẩn hóa** bởi lời gọi `equals`; đường dẫn tuyệt đối và tương đối cũng không tự biến đổi cho giống nhau.
5. Vì tuân theo hợp đồng `equals`/`hashCode`, phép so sánh này phù hợp khi dùng `Path` làm khóa `HashMap`, phần tử `HashSet` hoặc so cấu trúc đường dẫn đã được xử lý theo một quy ước thống nhất.

Ví dụ mang tính biểu diễn:

~~~java
Path a = Path.of("docs", "notes.txt");
Path b = Path.of("docs", ".", "notes.txt");

System.out.println(a.equals(b));             // thường là false
System.out.println(a.equals(b.normalize())); // thường là true
~~~

`normalize()` chỉ loại bỏ thành phần thừa **theo cú pháp**, không cần biết tệp nào đang tồn tại. Khi có symbolic link, loại bỏ `..` có thể làm thay đổi tệp đích thực tế; vì vậy không được coi `normalize()` là phép xác minh hai đường dẫn trỏ tới cùng tệp.

## 3. `Files.isSameFile(Path, Path)`: so sánh danh tính tệp

Chữ ký API:

~~~java
public static boolean isSameFile(Path path, Path path2) throws IOException
~~~

`Files.isSameFile` xác định hai đường dẫn có định vị cùng một tệp hay không. Tùy nhà cung cấp hệ thống tệp, việc này có thể phải truy cập hệ thống tệp và đọc thông tin liên quan đến tệp. Nó có thể nhận ra **cùng tệp dưới hai tên đường dẫn khác nhau**, kể cả khi được hỗ trợ thông qua symbolic link hoặc hard link.

Các quy tắc quan trọng từ hợp đồng API Java 17:

- **Nếu `path.equals(path2)` đã là `true`**, `isSameFile` trả `true` ngay, **không kiểm tra tệp có tồn tại hay không**.
- Nếu hai `Path` thuộc **hai file-system provider khác nhau**, trả `false`.
- Trong các trường hợp còn lại, API kiểm tra hai đường dẫn có định vị cùng tệp hay không; có thể phát sinh `IOException` khi kiểm tra thất bại.
- Khi hệ thống tệp không đổi trong quá trình gọi, quan hệ “cùng tệp” có tính phản xạ, đối xứng và bắc cầu. Nếu hệ thống tệp thay đổi đồng thời, kết quả không có bảo đảm đó.
- Phương thức không có tham số `LinkOption.NOFOLLOW_LINKS` và thường nhận diện đích của symbolic link khi link được phân giải bình thường.

**Điểm dễ nhầm:** `Files.isSameFile(missing, missing)` là `true` dù `missing` không tồn tại, do nhánh tối ưu hai `Path` bằng nhau. Trái lại, hai đường dẫn *khác nhau* mà không thể truy cập để xác định tệp có thể gây `NoSuchFileException` hoặc một `IOException` khác. Không dùng `isSameFile` như cách kiểm tra tồn tại tệp; dùng `Files.exists`, `Files.notExists` hoặc thao tác mở/đọc thích hợp, đồng thời nhớ rằng trạng thái tệp có thể đổi ngay sau khi kiểm tra.

## 4. Bảng đối chiếu

| Tiêu chí | `Path.equals` | `Files.isSameFile` |
|---|---|---|
| So sánh cái gì? | Biểu diễn `Path` theo quy tắc `FileSystem` | Tệp mà hai `Path` cùng định vị |
| Truy cập đĩa / I/O? | Không | Có thể có |
| Đường dẫn cần tồn tại? | Không | Thông thường cần kiểm tra được; ngoại lệ khi hai `Path` đã bằng nhau |
| `.`, `..`, đường dẫn khác cách viết | Không tự chuẩn hóa trước khi so | Có thể cùng tệp nếu hai đường dẫn phân giải về cùng đích |
| Symbolic link, hard link | Không kiểm tra quan hệ liên kết | Có thể nhận diện cùng tệp |
| `IOException`? | Không có checked `IOException` | Có, cần khai báo hoặc xử lý |
| Sử dụng chủ yếu | So sánh cấu trúc/khóa `Path` | Kiểm tra danh tính của tệp |

**Không nên suy luận** “hai tệp có cùng nội dung ⇒ `isSameFile` trả `true`”. Hai tệp độc lập chứa cùng số byte vẫn có danh tính khác nhau.

## 5. Ví dụ Java 17+ chạy được

Chương trình bên dưới dùng thư mục tạm và tạo thư mục con thực sự để `sub/../data.txt` có thể được hệ thống tệp phân giải. Nó không phụ thuộc vào quyền tạo symbolic link hoặc hard link.

**Tệp: `SameFileVsPathEquals.java`**

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SameFileVsPathEquals {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("same-file-demo-");

        try {
            Files.createDirectory(root.resolve("sub"));

            Path first = Files.writeString(
                    root.resolve("data.txt"), "hello", StandardCharsets.UTF_8);
            Path alias = root.resolve("sub").resolve("..").resolve("data.txt");
            Path other = Files.writeString(
                    root.resolve("other.txt"), "hello", StandardCharsets.UTF_8);
            Path missing = root.resolve("missing.txt");

            System.out.println(first.equals(alias));
            System.out.println(Files.isSameFile(first, alias));
            System.out.println(first.equals(alias.normalize()));
            System.out.println(Files.isSameFile(first, other));
            System.out.println(Files.isSameFile(missing, missing));
        } finally {
            Files.deleteIfExists(root.resolve("other.txt"));
            Files.deleteIfExists(root.resolve("data.txt"));
            Files.deleteIfExists(root.resolve("sub"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp nguồn:

~~~bash
javac SameFileVsPathEquals.java
java SameFileVsPathEquals
~~~

**Kết quả:**

~~~text
false
true
true
false
true
~~~

Giải thích theo thứ tự:

1. `first.equals(alias)` → `false`: hai `Path` có chuỗi thành phần khác nhau.
2. `Files.isSameFile(first, alias)` → `true`: vì thư mục `sub` tồn tại nên đi qua `sub/..` quay lại thư mục cha rồi đến chính `data.txt`.
3. `first.equals(alias.normalize())` → `true`: chuẩn hóa cú pháp bỏ cặp `sub/..` trong ví dụ cụ thể này.
4. `Files.isSameFile(first, other)` → `false`: hai tệp độc lập dù đều chứa `hello`.
5. `Files.isSameFile(missing, missing)` → `true`: hai đối số `Path` bằng nhau nên không kiểm tra tồn tại.

Chương trình dùng `finally` để xóa tài nguyên tạm; một lỗi xóa tệp vẫn có thể phát sinh `IOException` trên hệ thống đang khóa tệp. Chương trình không dựa vào đường dẫn thư mục tạm cụ thể nên không in đường dẫn ngẫu nhiên.

## 6. Cùng tệp qua symbolic link và hard link

Hãy hình dung các đường dẫn sau (mang tính minh họa, phụ thuộc hỗ trợ của hệ thống tệp):

~~~text
/work/report.csv          ← tệp gốc
/work/latest.csv          ← symbolic link tới report.csv
/work/report-copy-name    ← hard link tới cùng tệp
~~~

- `Path.of("/work/report.csv").equals(Path.of("/work/latest.csv"))` thường là `false` do biểu diễn đường dẫn khác nhau.
- `Files.isSameFile(original, symbolicLink)` thường là `true` khi symbolic link hợp lệ, phân giải về chính tệp gốc.
- `Files.isSameFile(original, hardLink)` là `true` khi hard link thực sự trỏ tới cùng tệp.
- Sao chép `report.csv` thành một tệp mới có nội dung giống hệt không làm chúng thành “cùng tệp”; `isSameFile` khi kiểm tra thành công sẽ trả `false`.

Tạo link bằng `Files.createSymbolicLink` hoặc `Files.createLink` là thao tác tùy hỗ trợ của nhà cung cấp và quyền hệ điều hành, có thể ném ngoại lệ. Đừng viết unit test *bắt buộc* hệ thống Windows/Linux bất kỳ tạo được symbolic link nếu môi trường CI chưa được chuẩn bị.

## 7. Phân biệt với `normalize()`, `toAbsolutePath()`, `toRealPath()`

- **`path.normalize()`**: chuẩn hóa cú pháp (`.` và phần `..` có thể rút gọn), không xác minh có tệp thật. Không bảo đảm bảo toàn tệp đích khi xuất hiện symbolic link.
- **`path.toAbsolutePath()`**: biến đường dẫn thành dạng tuyệt đối theo ngữ cảnh của file system; **không** xác nhận nó tồn tại hay là đường dẫn duy nhất của tệp.
- **`path.toRealPath()`**: mặc định truy cập hệ thống tệp, tạo đường dẫn thực/chuẩn tắc theo provider, thường phân giải symbolic link và yêu cầu mục tiêu tồn tại; có thể ném `IOException`. `NOFOLLOW_LINKS` thay đổi cách xử lý liên kết.
- **`Files.isSameFile(a, b)`**: trả lời trực tiếp câu hỏi liệu hai đường dẫn có cùng định vị một tệp. Không yêu cầu tự chuyển cả hai thành chuỗi hoặc so `toString()`.

Ví dụ cần kiểm tra danh tính tệp thì `Files.isSameFile` thể hiện ý định rõ hơn việc so sánh `toRealPath().equals(...)`. Trái lại, nếu cần tạo khóa `Path` theo một quy ước chuẩn hóa riêng cho ứng dụng thì `equals` có thể phù hợp hơn. Hai hướng xử lý giải quyết hai bài toán khác nhau.

## 8. Chọn API trong tình huống thực tế

**Dùng `Path.equals` khi:**

- Muốn biết hai giá trị đường dẫn đã lưu có bằng nhau theo quy tắc của `FileSystem`.
- Muốn tra cứu cấu trúc dữ liệu dựa vào `equals`/`hashCode` mà không thực hiện I/O.
- Đang xử lý các đường dẫn chưa tồn tại (ví dụ kế hoạch tạo file mới).

**Dùng `Files.isSameFile` khi:**

- Muốn biết hai đầu vào tệp khác tên có trỏ tới cùng tệp hiện tại không.
- Muốn phát hiện alias qua symbolic link/hard link trong logic xử lý tệp.
- Cần tránh thao tác lặp vào cùng một tệp khi hai đường dẫn có cách viết khác nhau.

Ví dụ xử lý ngoại lệ, nếu yêu cầu chỉ hoạt động với hai tệp đã xác minh tồn tại:

~~~java
try {
    if (Files.isSameFile(source, destination)) {
        throw new IllegalArgumentException(
                "Source và destination cùng trỏ tới một tệp");
    }
    // Tiếp tục logic phù hợp với ứng dụng.
} catch (IOException ex) {
    // Không thể kết luận danh tính tệp: báo lỗi hoặc xử lý theo chính sách ứng dụng.
    throw new IllegalStateException("Không kiểm tra được danh tính tệp", ex);
}
~~~

Đoạn trên là **mã minh họa bên trong một phương thức** đã khai báo hai biến `Path source` và `Path destination`; không phải chương trình Java chạy độc lập.

Lưu ý: ngay cả khi `isSameFile` vừa trả kết quả, tác vụ khác có thể xóa/đổi tên/thay liên kết tệp trước thao tác kế tiếp (**race/TOCTOU**). Không coi kết quả kiểm tra tại một thời điểm là bảo đảm an toàn cho chuỗi thao tác nhạy cảm. Nếu cần tính nguyên tử hoặc chống thay đổi đồng thời, ưu tiên API thao tác tệp/handle và cơ chế kiểm soát truy cập thích hợp cho bài toán.

## 9. Lỗi thường gặp và cách nhớ

1. **Dùng `equals` để nhận diện file vật lý:** bỏ sót symbolic link, hard link và các đường dẫn khác nhau cùng trỏ về một tệp.
2. **Dùng `isSameFile` như `Files.exists`:** hai đường dẫn `Path` bằng nhau cho kết quả `true` ngay cả khi file không tồn tại.
3. **Cho rằng `isSameFile` không ném ngoại lệ:** phải tính đến `IOException`, thiếu quyền và trạng thái tệp thay đổi.
4. **Coi `normalize()` là canonicalization của hệ thống tệp:** nó xử lý cú pháp, có thể sai về danh tính tệp khi có symbolic link.
5. **So chuỗi `path.toString()`:** dễ sai do khác biệt cú pháp, quy tắc hệ thống tệp và phân biệt chữ hoa/thường.
6. **Đồng nhất nội dung với danh tính:** hai bản sao có checksum giống nhau vẫn là hai tệp khác nhau.

Ghi nhớ ngắn gọn:

~~~text
Path.equals(a, b)       → Hai biểu diễn Path có bằng nhau?
Files.isSameFile(a, b)  → Hai Path có đang chỉ tới cùng một tệp?
~~~

### Tài liệu chính thức

- [Java 17: Path.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#equals(java.lang.Object))
- [Java 17: Files.isSameFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path))
- [Java 17: Path.toRealPath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...))
