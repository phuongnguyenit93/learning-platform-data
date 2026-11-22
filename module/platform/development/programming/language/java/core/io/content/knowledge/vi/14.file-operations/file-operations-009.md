# Không kiểm tra trước rồi mặc định thao tác sau sẽ thành công trong Java I/O

## 1. Vấn đề: kiểm tra đúng ở thời điểm này không bảo đảm đúng ở thời điểm sau

Khi thao tác với file, một cách viết dễ gặp là kiểm tra điều kiện trước rồi **mặc định rằng điều kiện đó vẫn còn đúng** khi thực hiện hành động:

~~~java
// KHÔNG AN TOÀN nếu coi kết quả exists() là sự bảo đảm.
if (Files.exists(path)) {
    String content = Files.readString(path);
    process(content);
}
~~~

Tại thời điểm `Files.exists(path)` chạy, file có thể đang tồn tại. Nhưng giữa lúc kiểm tra và `Files.readString(path)`, một tiến trình khác, thread khác, dịch vụ đồng bộ, người dùng hoặc chính mã của chương trình có thể **xóa, đổi tên, thay thế hoặc thay đổi quyền truy cập**. Kết quả là thao tác đọc vẫn có thể thất bại.

~~~text
Thời điểm       Ứng dụng A                     Tác nhân B
----------      ---------------------------    -----------------------
T1              Files.exists(path) == true
T2                                             Files.delete(path)
T3              Files.readString(path)
                -> IOException
~~~

Đây là dạng lỗi **TOCTOU — Time Of Check To Time Of Use** (chênh lệch giữa thời điểm kiểm tra và thời điểm sử dụng). TOCTOU không chỉ xuất hiện ở file: socket, database record, lock, giao dịch và các tài nguyên dùng chung cũng có tình huống tương tự.

**Nguyên tắc học tập:** Thao tác I/O **phải được kiểm tra ngay tại lúc thực hiện** thông qua kết quả trả về và ngoại lệ; một phép kiểm tra trước chỉ cung cấp thông tin tức thời, **không phải lời bảo đảm về tương lai**.

Không phải cứ gọi `Files.exists()` là sai. Sai là **dựa hoàn toàn vào kết quả đó để bỏ qua xử lý lỗi của thao tác tiếp theo**, hoặc dùng check-then-act để giả lập một thao tác vốn cần tính nguyên tử.

## 2. Những phép kiểm tra thường bị hiểu nhầm

| Phép kiểm tra | Thông tin nó cung cấp | Điều nó KHÔNG bảo đảm |
| --- | --- | --- |
| `Files.exists(path)` | Path có vẻ tồn tại tại thời điểm kiểm tra | Lần open/read/delete/rename sau sẽ thành công |
| `Files.notExists(path)` | Có cơ sở xác định path không tồn tại | Sau đó không ai tạo path |
| `Files.isReadable(path)` | Đánh giá khả năng đọc tại thời điểm kiểm tra | Lần đọc sau không gặp lỗi quyền, khóa, race hoặc I/O |
| `Files.isWritable(path)` | Đánh giá khả năng ghi tại thời điểm kiểm tra | Lần ghi sau sẽ thành công và đủ dung lượng |
| `Files.isRegularFile(path)` | Nhận biết kiểu mục tiêu tại thời điểm kiểm tra | Mục tiêu không bị thay bằng directory hoặc symlink |
| `Files.isDirectory(path)` | Nhận biết directory ở thời điểm kiểm tra | Lần mở thư mục/duyệt con sau sẽ thành công |
| `Files.size(path)` | Kích thước file quan sát tại thời điểm gọi | Kích thước không đổi trong khi đọc |
| `Files.getLastModifiedTime(path)` | Metadata thời gian sửa đổi hiện tại | Nội dung không thay đổi; metadata không phải khóa |

**Trường hợp đặc biệt của `exists()` và `notExists()`:** Java cho phép **cả hai cùng trả false** nếu không thể xác định trạng thái do quyền truy cập hoặc lỗi I/O. Không suy ra `!Files.exists(path)` tương đương `Files.notExists(path)` trong mọi tình huống.

Các phép kiểm tra trên có thể hữu ích để **hiển thị giao diện** hoặc **cung cấp chẩn đoán sơ bộ**, nhưng không thể thay thế `try/catch` quanh thao tác thực sự.

## 3. Ví dụ Java 17+: file biến mất sau phép kiểm tra

Tạo file **CheckThenActDemo.java** và lưu mã nguồn bằng UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class CheckThenActDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("toctou-demo-");
        Path target = directory.resolve("notes.txt");

        try {
            Files.writeString(
                    target, "hello", StandardCharsets.UTF_8);

            boolean wasThere = Files.exists(target);
            System.out.println("checkedExists=" + wasThere);

            // Mô phỏng một tác nhân khác thay đổi file
            // giữa bước kiểm tra và bước sử dụng.
            Files.delete(target);

            try {
                String text = Files.readString(
                        target, StandardCharsets.UTF_8);
                System.out.println("text=" + text);
            } catch (NoSuchFileException expected) {
                System.out.println("readAfterChange=missing");
            }
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CheckThenActDemo.java
java CheckThenActDemo
~~~

Stdout:

~~~text
checkedExists=true
readAfterChange=missing
~~~

Ở đây việc xóa file **được thực hiện có chủ ý** giữa hai lệnh để tái hiện race theo cách dễ quan sát; ví dụ **không cần tạo thread**. Trong ứng dụng thực tế, hành động chen ngang có thể đến từ thread hoặc process khác và xảy ra bất kỳ lúc nào.

Chương trình chứng minh một điều: **`exists() == true` và `readString()` thất bại có thể cùng đúng**, vì chúng đánh giá hai thời điểm khác nhau. Việc xử lý `NoSuchFileException` nằm ở thao tác đọc mới là xử lý lỗi đúng.

Đoạn `finally` dùng `deleteIfExists()` để dọn file do chương trình tạo; nếu file đã bị xóa thì hàm có thể trả false mà không coi đó là lỗi. Việc dọn dẹp directory được thực hiện sau khi dọn file.

## 4. Cách đọc đúng: thực hiện thao tác rồi xử lý kết quả

Khi mục tiêu là **đọc file nếu có**, nhiều trường hợp không cần hỏi file có tồn tại trước hay không. Hãy trực tiếp gọi hàm đọc:

~~~java
// Mảnh code: path là Path, các import tương ứng đã có.
try {
    String text = Files.readString(path, StandardCharsets.UTF_8);
    use(text);
} catch (NoSuchFileException missing) {
    // Đối tượng không còn tồn tại lúc mở/đọc.
    reportMissing(path);
} catch (java.nio.file.AccessDeniedException denied) {
    // Không được phép truy cập.
    reportDenied(path);
} catch (IOException failure) {
    // Các lỗi I/O còn lại: filesystem, thiết bị, đọc lỗi...
    reportIoFailure(failure);
}
~~~

`use`, `reportMissing`, `reportDenied` và `reportIoFailure` ở trên là các hàm **do ứng dụng cung cấp**; đây là **mảnh code minh họa**, không phải chương trình chạy độc lập.

Ưu điểm:

1. Không tạo một giả định sai rằng kiểm tra ban đầu đảm bảo thao tác.
2. Bắt được các lỗi phát sinh **ngay tại bước làm việc**.
3. Phân biệt file không còn, quyền bị từ chối và các lỗi I/O khác khi provider cung cấp exception cụ thể.
4. Giảm một lần truy vấn filesystem có thể không cần thiết.

**Không đảm bảo mọi hệ điều hành và provider sẽ luôn ném cùng một lớp ngoại lệ cụ thể.** `NoSuchFileException` và `AccessDeniedException` là các trường hợp phổ biến, nhưng ứng dụng vẫn nên có nhánh `IOException` tổng quát.

**Đối với file tùy chọn**, “file không tồn tại” có thể là tình huống nghiệp vụ bình thường (ví dụ chưa có cấu hình riêng). Đối với file bắt buộc, cùng tình huống ấy là lỗi cần báo cho người dùng. Cách xử lý tùy hợp đồng ứng dụng, không tùy việc có hay không có phép `exists()`.

## 5. Check-then-create: nguy cơ khi tạo file mới

Một mẫu dễ gây race:

~~~java
// SAI nếu cần bảo đảm không ghi đè file đã có.
if (Files.notExists(target)) {
    Files.writeString(target, "new content");
}
~~~

Sau khi `notExists()` trả true, tác nhân khác có thể tạo target ngay lập tức. Nếu `Files.writeString` dùng các tùy chọn mặc định, thao tác đó có thể **tạo file nếu thiếu hoặc truncate file đã tồn tại**. Như vậy chương trình có thể ghi đè dữ liệu của người khác trái với mục tiêu “chỉ tạo khi chưa có”.

Mục tiêu đúng ở đây là một **thao tác tạo có điều kiện** do filesystem thực hiện như một đơn vị, không phải hai thao tác kiểm tra + ghi tách rời.

Dùng **`StandardOpenOption.CREATE_NEW`** khi tạo file và ghi nội dung:

~~~java
Files.writeString(
        target,
        "new content",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

Theo hợp đồng Files, với `CREATE_NEW`, **kiểm tra tồn tại và tạo file mới được thực hiện nguyên tử đối với các thao tác filesystem khác**. Nếu đã có file (kể cả symbolic link tại vị trí đích), thao tác thất bại; trên default provider thông thường đó là `FileAlreadyExistsException`.

Lưu ý: **nguyên tử ở bước tạo file** không có nghĩa việc ghi toàn bộ nội dung ngay sau đó cũng là một transaction nguyên tử. Nếu ghi lỗi giữa chừng, file mới tạo có thể chỉ chứa nội dung một phần. Đừng nhầm “không tạo trùng” với “nội dung được commit trọn vẹn”.

### Ví dụ Java 17+: CREATE_NEW ngăn lần tạo thứ hai

Tạo file **CreateNewDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CreateNewDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("create-new-demo-");
        Path target = directory.resolve("result.txt");

        try {
            Files.writeString(
                    target,
                    "first",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            System.out.println("firstCreate=ok");

            try {
                Files.writeString(
                        target,
                        "second",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
                System.out.println("secondCreate=ok");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("secondCreate=already-exists");
            }

            System.out.println("content=" + Files.readString(
                    target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CreateNewDemo.java
java CreateNewDemo
~~~

Stdout:

~~~text
firstCreate=ok
secondCreate=already-exists
content=first
~~~

Ở lần đầu, file chưa tồn tại nên tạo thành công. Ở lần hai, `CREATE_NEW` phát hiện đích đã có và từ chối thao tác. Nội dung **vẫn là first**, không bị lần gọi thứ hai ghi đè. Thay vì hỏi trước `notExists`, mã chọn hành vi “chỉ được tạo mới” ở **chính lệnh ghi**, nơi nó có hiệu lực.

Cũng có thể dùng `Files.createFile(target)` để tạo file rỗng mới. Theo hợp đồng, thao tác kiểm tra-và-tạo của `createFile` là nguyên tử đối với các thao tác filesystem khác. Tuy vậy, sau `createFile` rồi mở luồng khác để ghi vẫn là **hai bước riêng**: nếu quan tâm cả độ an toàn của nội dung, hãy cân nhắc mở ngay bằng `CREATE_NEW` và giữ handle thích hợp.

## 6. Check-then-delete và deleteIfExists

Mẫu sau cũng không có bảo đảm:

~~~java
// Không cần thiết và vẫn có race.
if (Files.exists(path)) {
    Files.delete(path);
}
~~~

Tác nhân khác có thể xóa path giữa `exists` và `delete`. Lúc đó `Files.delete(path)` có thể ném `NoSuchFileException`.

Nếu yêu cầu nghiệp vụ là “xóa nếu có; nếu không có thì bỏ qua”, dùng trực tiếp:

~~~java
boolean deleted = Files.deleteIfExists(path);
System.out.println("deleted=" + deleted);
~~~

- `true`: thao tác đã xóa một đối tượng.
- `false`: thao tác không xóa vì đối tượng không tồn tại.
- Ngoài ra, thao tác vẫn có thể ném `IOException` do quyền truy cập, thư mục không rỗng, lỗi I/O hoặc những điều kiện khác.

**`deleteIfExists` không bảo đảm xóa thành công**, và cũng không làm các bước nghiệp vụ trước/sau thành một transaction. Nó chỉ gộp logic “nếu tồn tại thì xóa” vào một API thuận tiện và hạn chế một khoảng check-then-act không cần thiết.

Nếu ứng dụng **bắt buộc phải xóa một file cụ thể đã kiểm tra trước đó**, việc gọi `deleteIfExists(path)` chưa giải quyết yêu cầu định danh đó. Đường dẫn có thể đã bị thay bằng đối tượng khác. Bài toán chống race với đối tượng cụ thể cần cơ chế handle/file identity và quyền kiểm soát filesystem phù hợp.

## 7. Check-then-write, copy và move

Không nên viết:

~~~java
// SAI nếu mục đích là chắc chắn không ghi đè file khác.
if (!Files.exists(destination)) {
    Files.copy(source, destination);
}
~~~

Giữa lúc kiểm tra và copy, đích có thể xuất hiện. Hãy quyết định **chính sách tại thao tác**:

- **Không ghi đè đích có sẵn:** gọi `Files.copy(source, destination)` không kèm `REPLACE_EXISTING` rồi xử lý trường hợp file đích đã tồn tại.
- **Chấp nhận thay thế đích:** cân nhắc `StandardCopyOption.REPLACE_EXISTING`, hiểu rằng kết quả còn phụ thuộc filesystem, quyền và các lỗi có thể xảy ra.
- **Di chuyển file:** dùng `Files.move` với tùy chọn phù hợp; nếu cần đổi tên theo cơ chế nguyên tử, cân nhắc `StandardCopyOption.ATOMIC_MOVE` nhưng phải chuẩn bị xử lý `AtomicMoveNotSupportedException`.

Các ví dụ:

~~~java
// Không cho phép copy đè: ứng dụng xử lý IOException nếu đích có.
Files.copy(source, destination);
~~~

~~~java
// Chấp nhận thay thế theo hợp đồng của Files.copy.
Files.copy(
        source, destination,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
~~~

~~~java
// Yêu cầu move nguyên tử; có provider/filesystem không hỗ trợ.
Files.move(
        source, destination,
        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
~~~

Những đoạn trên là **mảnh code** trong phương thức đã có Path và xử lý IOException. Lưu ý quan trọng:

1. Các thao tác `copy` và `move` có thể thất bại bởi quyền truy cập, file nguồn mất, đích xuất hiện, cross-filesystem hoặc các lỗi khác.
2. **`Files.copy` không bảo đảm nguyên tử**; nếu xảy ra lỗi I/O, một phần file đích có thể đã được tạo hoặc ghi.
3. `ATOMIC_MOVE` là yêu cầu hỗ trợ từ filesystem/provider; nó có thể bị từ chối bằng `AtomicMoveNotSupportedException`. Không tự coi “move” hay “replace existing” là giao dịch nguyên tử.
4. Với `ATOMIC_MOVE`, ngữ nghĩa khi **target đã tồn tại** có những chi tiết phụ thuộc implementation theo đặc tả; phải xác định hợp đồng ứng dụng và hành vi provider. Không kết hợp tùy chọn rồi suy rằng mọi platform đều thay thế giống nhau.

**Quy tắc tổng quát:** tránh kiểm tra rồi làm như thể hai bước là một giao dịch; thay vào đó chọn một thao tác có điều kiện/tùy chọn thích hợp và **luôn xử lý kết quả của chính thao tác đó**.

## 8. Check-then-mkdir và createDirectories

Một ví dụ phổ biến:

~~~java
if (!Files.exists(directory)) {
    Files.createDirectory(directory);
}
~~~

Tác nhân khác có thể tạo directory ngay sau check, gây `FileAlreadyExistsException`. Nếu yêu cầu là “bảo đảm toàn bộ chuỗi thư mục cha tồn tại khi thao tác có thể”, thường dùng:

~~~java
Files.createDirectories(directory);
~~~

`createDirectories` có thể tạo các thành phần thư mục chưa có và **không thất bại chỉ vì thư mục mục tiêu đã tồn tại dưới dạng directory**. Nhưng nó vẫn có thể ném IOException nếu một thành phần là file thường, không có quyền, có lỗi hệ thống, hoặc nếu môi trường thay đổi trong khi tạo.

**Không suy ra createDirectories là một transaction nguyên tử.** Nếu việc tạo một loạt thành phần thất bại, một số thư mục cha trước đó có thể đã được tạo thành công. Ứng dụng cần xem xét cleanup của những tài nguyên/side effect do chính mình sở hữu nếu cần rollback.

## 9. Quyền truy cập và kiểm tra metadata không thay thế thao tác mở

Mẫu:

~~~java
if (Files.isReadable(path)) {
    return Files.readString(path);
}
return "";
~~~

có hai vấn đề:

1. `isReadable` chỉ mô tả trạng thái **tại thời điểm kiểm tra**; quyền có thể bị thay đổi hoặc đối tượng bị đổi sau đó.
2. Nếu `isReadable` trả false, có thể do không kiểm tra được hoặc điều kiện đặc thù provider; trả chuỗi rỗng sẽ **che mất lý do thất bại** và khiến ứng dụng tưởng file có nội dung rỗng.

Tốt hơn:

~~~java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (IOException failure) {
    // Quyết định nghiệp vụ: báo lỗi, fallback hoặc thử lại có giới hạn.
    throw failure;
}
~~~

Tương tự, `Files.isWritable` không chứng minh còn đủ dung lượng lưu trữ, không bị quota, file không bị khóa và ghi thành công. `Files.size` không bảo đảm file vẫn giữ kích thước đó trong lúc đọc. Để đọc một snapshot nhất quán, cần thiết kế giao dịch/snapshot/locking thích hợp với filesystem và tác nhân ghi.

**File locking cũng không phải giải pháp phổ quát:** mức độ bắt buộc, phạm vi, tương tác với phần mềm khác và tính portable phụ thuộc filesystem cùng hệ điều hành. Không thay thế logic xử lý exception bằng niềm tin rằng kiểm tra quyền hoặc lock một lần sẽ giải quyết mọi race.

## 10. Symbolic link làm check-then-use nguy hiểm hơn

Giả sử ứng dụng muốn đọc file dưới một thư mục cho phép. Nó kiểm tra:

~~~text
/base/uploads/report.txt
~~~

Nếu attacker hoặc tiến trình khác có quyền sửa cây thư mục, chúng có thể thay file hay một thành phần cha bằng **symbolic link** trỏ sang nơi khác giữa bước xác minh và mở. Một phép kiểm tra bằng đường dẫn **không cố định danh tính của đối tượng sẽ được mở sau đó**.

Các khái niệm liên quan:

- **`Path.normalize()`** chỉ rút gọn các thành phần `.` và `..` theo cú pháp, không truy vấn filesystem.
- **`Path.toRealPath()`** có thể phân giải một đường dẫn tồn tại tại thời điểm gọi, nhưng vẫn không “khóa” kết quả khỏi thay đổi về sau.
- **`LinkOption.NOFOLLOW_LINKS`** ảnh hưởng một số thao tác theo cách đặc tả, nhưng một lần kiểm tra không tự bảo đảm tất cả thành phần của đường dẫn không bị thay giữa check/use.
- **`SecureDirectoryStream`** cung cấp một số thao tác tương đối so với một directory stream mở, có thể giảm rủi ro race trong những trường hợp provider hỗ trợ; không phải mọi filesystem đều cung cấp API này.

Với đường dẫn không đáng tin cậy, chỉ kiểm tra `resolved.normalize().startsWith(base)` là **chưa đủ** nếu có symbolic link và race. Thiết kế an toàn hơn cần quản lý danh tính thư mục, khả năng theo symlink, quyền sửa thư mục và cách mở file, chứ không chỉ so sánh String hay Path trước đó.

Nếu ứng dụng không hoạt động trong mô hình có đối tượng đối kháng, việc phân biệt vẫn hữu ích: kể cả không ai cố tình tấn công, các tiến trình đồng bộ file hoặc người dùng thao tác đồng thời cũng có thể gây race.

## 11. Quy tắc mở rồi dùng: handle vẫn có thể lỗi

Có một khác biệt quan trọng:

- Khi **mở** một file qua `Files.newInputStream` hoặc `Files.newByteChannel`, ta có một đối tượng stream/channel gắn với việc mở được chấp nhận tại thời điểm đó.
- Nhưng **không có gì bảo đảm mọi lần read/write/flush/close về sau đều thành công**. Thiết bị có thể gặp lỗi, mạng hoặc bộ nhớ ngoài có thể biến mất, filesystem hết dung lượng, stream bị đóng hoặc tài nguyên khác thay đổi.
- Bởi vậy cần **try-with-resources** để đóng và xử lý exception ở cả lúc mở, đọc/ghi, và đóng.

Ví dụ đọc theo luồng:

~~~java
// Mảnh code: input là Path, output là OutputStream hợp lệ.
try (var stream = Files.newInputStream(input)) {
    stream.transferTo(output);
}
~~~

`transferTo` có thể ném IOException trong khi đang copy. TWR vẫn cố đóng stream. Không cho rằng “mở stream thành công” đồng nghĩa đọc trọn vẹn và đóng sẽ luôn thành công.

**Không dùng `Files.exists` như cách đảm bảo tính nguyên tử của toàn bộ quy trình.** Một tiến trình muốn ghi output hoàn chỉnh có thể dùng mô hình tạo file tạm, ghi/flush/đóng, rồi publish bằng move theo semantics hỗ trợ; nhưng phải xử lý lỗi và dọn file tạm. Giữa các bước vẫn cần thiết kế rõ ràng, không thể giả định mọi phần được rollback tự động.

## 12. Không kiểm tra trước nghĩa là không được xác minh dữ liệu?

Không. Bài học này **không khuyên bỏ kiểm tra dữ liệu đầu vào**. Hãy phân biệt:

**Kiểm tra hợp đồng đầu vào** (nên làm):

- Người dùng đã cung cấp tên file hay chưa?
- Extension/định dạng có được cho phép theo nghiệp vụ không?
- Dung lượng tối đa của payload sẽ chấp nhận là bao nhiêu?
- Đường dẫn có vượt chính sách bảo mật không?
- Dữ liệu đã đọc có đúng schema, checksum, magic bytes hoặc version không?

**Kiểm tra trạng thái động rồi giả định không thay đổi** (không nên):

- `exists` hôm nay, đọc chắc chắn được ở dòng kế tiếp.
- `notExists` trước khi ghi, nên tuyệt đối không đè file khác.
- `isWritable` trước khi export, nên chắc chắn file sẽ được ghi đủ.
- `size` trước khi cấp phát, nên file không bao giờ thay đổi khi đọc.
- `isRegularFile` trước khi open, nên không thể bị thay bằng đối tượng khác.

Ứng dụng có thể **vừa xác minh đầu vào vừa bắt lỗi thao tác thực tế**. Với security boundary, nên dùng thao tác dựa trên handle hoặc cơ chế được thiết kế tránh race, thay vì dựa duy nhất vào một phép kiểm tra trạng thái filesystem.

## 13. Cần retry khi file biến mất hoặc xuất hiện không?

Không phải mọi IOException đều nên thử lại:

| Tình huống | Hướng xử lý |
| --- | --- |
| File tùy chọn chưa tồn tại | Có thể fallback sang cấu hình mặc định, nếu nghiệp vụ cho phép |
| File bắt buộc không tồn tại | Báo rõ lỗi hoặc yêu cầu cung cấp đường dẫn đúng |
| Tạo file với CREATE_NEW gặp FileAlreadyExistsException | Chọn tên khác hoặc báo xung đột, không tự ghi đè |
| Lỗi quyền AccessDeniedException | Thường báo lỗi quyền/cấu hình, không retry vô hạn |
| Lỗi I/O tạm thời theo giao thức có quy định | Có thể retry có giới hạn, delay/backoff và kiểm tra trạng thái |
| Việc ghi đã có thể hoàn thành một phần | Phải biết thao tác có idempotent hay không trước khi retry |
| Move/copy thất bại giữa chừng | Kiểm tra trạng thái output thực tế, xử lý bản dở dang theo contract |

Một retry không kiểm soát có thể ghi đè dữ liệu, tạo nhiều file, lặp vô tận hoặc tạo thêm race. Nếu cần retry, chọn **thao tác idempotent** hoặc dùng tên/ID riêng và protocol an toàn. Đặc biệt với ghi dữ liệu, hãy xem xét khả năng **đã ghi một phần** trước khi thực hiện lại.

## 14. Các mẫu đúng và sai đặt cạnh nhau

| Mục tiêu | Mẫu dễ sai | Cách diễn đạt ý định tốt hơn |
| --- | --- | --- |
| Đọc file có thể vắng mặt | `if (exists) read` rồi bỏ xử lý lỗi | `readString` trực tiếp, bắt NoSuchFileException/IOException |
| Chỉ tạo nếu chưa có | `if (notExists) write` | `CREATE_NEW` hoặc `createFile` |
| Xóa nếu có | `if (exists) delete` | `deleteIfExists` và xử lý IOException |
| Tạo cây thư mục | `if (!exists) createDirectory` | `createDirectories` và xử lý IOException |
| Copy không ghi đè | `if (!exists(dest)) copy` | `Files.copy` không REPLACE_EXISTING, xử lý conflict |
| Move yêu cầu tính nguyên tử | Kiểm tra đích trước rồi move thường | Cân nhắc `ATOMIC_MOVE` và xử lý unsupported/race |
| Kiểm tra đọc được | `isReadable` rồi tin lần read chắc thành công | Mở/đọc trực tiếp, xử lý lỗi thực |
| Đọc file lớn | `size` rồi tin kích thước cố định | Đọc theo luồng, giới hạn dữ liệu, xử lý EOF/lỗi |
| Cho phép file chỉ nằm dưới base | Chỉ `normalize().startsWith(base)` | Kiểm soát symlink, quyền và thao tác mở thực tế |

**Các hàm Files API giải quyết những yêu cầu khác nhau.** Hãy chọn API theo **bất biến nghiệp vụ**: không ghi đè, thay thế có kiểm soát, chỉ đọc, xóa nếu có, tạo thư mục... thay vì kiểm tra lẻ rồi hy vọng.

## 15. Quy trình thực hành khi viết thao tác file

1. **Xác định hành vi mong muốn:** file bắt buộc hay tùy chọn? Có được tạo? Có được ghi đè? Nếu xung đột thì báo lỗi hay đổi tên?
2. **Chọn phép toán phản ánh hành vi tại bước thực hiện:** ví dụ `CREATE_NEW` cho tạo độc quyền, `deleteIfExists` cho xóa tùy chọn, `createDirectories` cho tạo cây.
3. **Đừng dùng kết quả của một phép kiểm tra trạng thái làm cam kết tương lai.** Nếu cần hiển thị “file tồn tại”, vẫn có thể gọi `exists`, nhưng thao tác dùng file phải tự xử lý lỗi.
4. **Quản lý vòng đời tài nguyên** bằng try-with-resources và xử lý lỗi trong đọc/ghi/flush/close.
5. **Định nghĩa tính nhất quán:** chấp nhận file đang thay đổi, cần snapshot, cần atomic publish hay cần lock/handle an toàn?
6. **Xử lý cả output dở dang** sau một thao tác thất bại; phân biệt cleanup resource với rollback dữ liệu.
7. **Kiểm tra thông báo lỗi và phép thử race:** file mất sau check; file xuất hiện trước create; permission thay đổi; file bị thay bằng symlink; I/O lỗi khi đang copy.

Đây là tư duy **“try the operation, handle its actual result”**. Nó không loại bỏ nhu cầu validate đầu vào mà loại bỏ giả định rằng một trạng thái vừa quan sát sẽ luôn đúng cho hành động kế tiếp.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Files.exists(path)` trả true. Lần đọc tiếp theo có chắc chắn thành công không?  
**Đáp án:** Không. File có thể bị xóa, đổi tên, thay thế, đổi quyền hoặc gặp lỗi I/O trước/trong lúc đọc.

**Câu 2.** Vì sao `if (Files.notExists(path)) Files.writeString(path, data)` có thể ghi đè file vừa được tác nhân khác tạo?  
**Đáp án:** Check và write là hai bước riêng. Tác nhân khác có thể tạo file sau check; `writeString` mặc định có thể truncate file đã tồn tại.

**Câu 3.** Khi chỉ được tạo file mới nếu chưa tồn tại, nên chọn gì?  
**Đáp án:** `StandardOpenOption.CREATE_NEW` hoặc `Files.createFile`, rồi xử lý trường hợp đích đã tồn tại. Không thay bằng check-then-create.

**Câu 4.** Nếu `Files.exists` và `Files.notExists` cùng false thì kết luận file tồn tại hay không?  
**Đáp án:** Không thể khẳng định từ hai giá trị đó; có thể hệ thống không xác định được trạng thái file.

**Câu 5.** `Files.deleteIfExists` bảo đảm xóa mọi file thành công không?  
**Đáp án:** Không. Nó bỏ qua trường hợp đối tượng vắng mặt, nhưng vẫn có thể thất bại bởi quyền, thư mục không rỗng và lỗi I/O.

**Câu 6.** `Files.isReadable(path)` true có đủ để bỏ catch IOException quanh `Files.readString` không?  
**Đáp án:** Không. Trạng thái có thể thay đổi và lỗi vẫn xảy ra khi đọc.

**Câu 7.** `Files.copy` có mặc định là một transaction nguyên tử không?  
**Đáp án:** Không. Lỗi trong quá trình copy có thể để lại đích dở dang; cần thiết kế cleanup hoặc publish đúng yêu cầu.

**Câu 8.** `normalize().startsWith(base)` có đủ để ngăn truy cập ngoài base khi có symbolic link không?  
**Đáp án:** Chưa. Normalize là lexical, còn symlink và race cần kiểm soát theo filesystem/handle.

**Câu 9.** Nếu `CREATE_NEW` tạo file thành công rồi thao tác ghi thất bại nửa chừng, file có tự biến mất không?  
**Đáp án:** Không có bảo đảm đó. CREATE_NEW đảm bảo điều kiện tạo, không tạo transaction cho toàn bộ nội dung ghi; ứng dụng cần xử lý file dở dang.

**Câu 10.** Nếu có phép kiểm tra UI “tệp đang tồn tại” thì có nên bỏ không?  
**Đáp án:** Không nhất thiết. Thông tin tức thời hữu ích cho giao diện; chỉ không được coi nó thay thế kiểm tra kết quả và ngoại lệ tại thao tác I/O.

## 17. Tài liệu Java SE 17

- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `isReadable`, `createFile`, `createDirectories`, `deleteIfExists`, `copy`, `move`.
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING` và `ATOMIC_MOVE`.
- [FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html) và [NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): lỗi tồn tại/không tồn tại tại thời điểm thao tác.
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác thư mục có cơ chế hỗ trợ chống một số race dựa trên đường dẫn, khi provider hỗ trợ.

**Ghi nhớ:** Đối với file và tài nguyên dùng chung, **trạng thái quan sát ở thời điểm kiểm tra không bảo đảm thao tác sử dụng sau đó thành công**. Thay vì check-then-act và giả định mọi thứ giữ nguyên, hãy dùng **API thể hiện điều kiện tại chính thao tác** (chẳng hạn `CREATE_NEW`), xử lý đầy đủ ngoại lệ, đóng tài nguyên đúng lúc và chỉ dùng kiểm tra trước như thông tin bổ sung.
