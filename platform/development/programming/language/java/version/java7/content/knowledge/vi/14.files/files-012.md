# Tránh giả định trạng thái không đổi sau thao tác kiểm tra với `Files` trong Java

## 1. Vấn đề cốt lõi: trạng thái tệp có thể thay đổi bất kỳ lúc nào

Trong Java, lớp `java.nio.file.Files` cho phép kiểm tra sự tồn tại, kiểu, quyền truy cập và thuộc tính của một đường dẫn. Nhưng hệ thống tệp **không phải một cơ sở dữ liệu bất biến**: ứng dụng khác, luồng khác, người dùng hoặc chính chương trình của bạn có thể tạo, xóa, thay thế, sửa nội dung hay đổi symbolic link trong khoảng thời gian giữa hai thao tác.

Ví dụ rất dễ mắc lỗi:

~~~java
if (Files.exists(path)) {
    String text = Files.readString(path, StandardCharsets.UTF_8);
    // Sai nếu giả định đến đây file chắc chắn vẫn tồn tại.
}
~~~

Đây là **đoạn minh họa**, cần biến `Path path` và import `Files`, `StandardCharsets`. Dù `Files.exists(path)` trả `true` tại thời điểm kiểm tra, một tiến trình khác có thể xóa/di chuyển file trước khi `readString` mở nó. `readString` vẫn có thể ném `NoSuchFileException` hoặc một `IOException` khác.

Hiện tượng này được gọi là **TOCTOU** (*time-of-check to time-of-use*, thời điểm kiểm tra khác thời điểm sử dụng). Bài học nằm trong chủ đề **`Files`** và tập trung vào nguyên tắc: **kết quả kiểm tra chỉ mô tả một quan sát tại thời điểm đó, không khóa trạng thái cho hành động tiếp theo**.

**Mục tiêu học tập:**

- Phân biệt thông tin từ `Files.exists`, `notExists`, `isReadable`, `isRegularFile`, `size`, `readAttributes` với khả năng **thực hiện thao tác**.
- Hiểu vì sao `exists` và `notExists` không luôn là hai giá trị bù nhau.
- Thay mẫu “kiểm tra trước rồi tin rằng sẽ không đổi” bằng thao tác trực tiếp và **xử lý chính xác lỗi**.
- Sử dụng `CREATE_NEW`/`Files.createFile` để kiểm tra-và-tạo theo một thao tác nguyên tử ở mức API.
- Hiểu giới hạn của việc kiểm tra symlink, đường dẫn thật, thuộc tính, file handle và quá trình ghi file.
- Viết kiểm thử tái hiện thay đổi trạng thái **có chủ đích** mà không phụ thuộc vào may rủi scheduler.

**Tính hiện hành:** đây là quy tắc quan trọng của Java NIO.2 từ Java 7 và vẫn còn áp dụng trên **Java 17, 21 và các JDK hiện đại**. Ví dụ runnable dùng Java 21, `Files.readString` / `writeString` và `StandardCharsets.UTF_8`; không dùng API legacy.

## 2. Mô hình thời gian: một bước kiểm tra không giữ quyền sở hữu đối tượng

Giả sử hai tác nhân cùng truy cập `/data/report.txt`:

~~~text
Thời điểm       Luồng A                       Luồng B
---------       ----------------------------  ----------------------------
t1              Files.exists(path) == true
t2                                            Files.delete(path)
t3              Files.readString(path)
t4              NoSuchFileException
~~~

Đây là sơ đồ thứ tự sự kiện, không phải chương trình Java chạy được. Luồng A **không sai** khi dùng `exists` để hỏi tình trạng tại `t1`, nhưng sẽ **sai về lập luận** nếu xem kết quả đó là lời hứa về tình trạng tại `t3`.

Vấn đề tương tự có thể xuất hiện giữa:

- `Files.notExists(path)` rồi `Files.createFile(path)`.
- `Files.isReadable(path)` rồi `Files.newBufferedReader(path)`.
- `Files.isRegularFile(path)` rồi `Files.readString(path)`.
- `Files.size(path)` rồi đọc nội dung và giả định kích thước vẫn giữ nguyên.
- `Files.readAttributes(path, BasicFileAttributes.class)` rồi dựa vào thuộc tính cũ để đưa ra quyết định truy cập.
- `path.toRealPath()` rồi mở lại path, khi một symlink có thể bị thay ở giữa.
- `Files.isSameFile(a, b)` rồi tin rằng hai tên sẽ mãi trỏ cùng đối tượng.

**Mấu chốt:** một `Path` object mô tả **tên/đường đi** và có thể giữ giá trị của nó không đổi, nhưng **file/directory/symlink phía sau tên vẫn có thể đổi**. Không phải vì `Path` immutable mà đối tượng trên đĩa trở thành immutable.

## 3. Phân biệt các phương thức kiểm tra của `Files`

| API | Nó trả lời điều gì tại thời điểm gọi? | Điều nó **không** bảo đảm cho lần gọi sau |
| --- | --- | --- |
| `Files.exists(path)` | Có xác định được file đang tồn tại không? | Lần mở sau vẫn thấy cùng file |
| `Files.notExists(path)` | Có xác định được file không tồn tại không? | Tên sẽ còn trống lúc tạo |
| `Files.isReadable(path)` | Có xác định file có thể đọc theo kiểm tra hiện tại không? | `newBufferedReader`/`readString` chắc chắn thành công |
| `Files.isWritable(path)` | Có xác định file có thể ghi theo kiểm tra hiện tại không? | `writeString` chắc chắn thành công và ghi đủ |
| `Files.isRegularFile(path)` | Có xác định đây là regular file không? | Sau đó tên không bị thay thành thư mục/link |
| `Files.isDirectory(path)` | Có xác định là directory không? | Sau đó các thành phần đường dẫn vẫn nguyên |
| `Files.size(path)` | Kích thước file tại một thời điểm | Dữ liệu đọc sau đó có đúng kích thước này |
| `Files.getLastModifiedTime(path)` | Thời điểm sửa cuối quan sát được | Không ai có thể sửa lại sau đó |
| `Files.readAttributes(...)` | Một tập thuộc tính tại thời điểm truy vấn | Thuộc tính giữ nguyên khi sử dụng |
| `path.toRealPath()` | Đường dẫn thật của một file hiện có | Symlink và cây thư mục không thay sau khi kiểm tra |

**Cần phân biệt “best effort check” với “operation contract”.** Khi điều kiện quan trọng là “đọc file thành công”, thì sự kiện quyết định phải là **chính thao tác mở/đọc** và kết quả/ngoại lệ của nó, không phải boolean kiểm tra trước.

### 3.1. `exists` và `notExists` không nhất thiết là phủ định nhau

Một bẫy đặc biệt của NIO.2:

~~~java
boolean a = Files.exists(path);
boolean b = Files.notExists(path);
~~~

Đây là đoạn minh họa. Theo Javadoc, **không được suy ra** `b == !a`. Khi không thể xác định trạng thái (ví dụ lỗi truy cập hoặc I/O), **cả hai có thể trả `false`**. Vì vậy tồn tại ba trạng thái quan sát được:

| `exists(path)` | `notExists(path)` | Cách hiểu |
| --- | --- | --- |
| `true` | `false` | Đã xác định là có tại lúc kiểm tra |
| `false` | `true` | Đã xác định là không có tại lúc kiểm tra |
| `false` | `false` | **Không xác định** được trạng thái; đừng coi như “chắc chắn không có” |
 
Hai lời gọi cũng diễn ra vào **hai thời điểm khác nhau**, nên nếu có người sửa file ở giữa, những giá trị quan sát còn có thể phản ánh hai trạng thái khác nhau. Bảng chỉ là cách hiểu **một trạng thái file system ổn định trong giai đoạn quan sát**, không phải một phép đọc snapshot nguyên tử của hai boolean.

**Không dùng:**

~~~java
if (!Files.exists(path)) {
    // KHÔNG thể kết luận chắc chắn đường dẫn đang không có file.
}
~~~

Lệnh `notExists` phù hợp hơn khi muốn hỏi “đã xác nhận không tồn tại chưa?”, nhưng **kết quả true vẫn có thể hết hạn ngay lập tức**.

### 3.2. Symbolic link làm điều kiện kiểm tra phức tạp hơn

`Files.exists(path)` thường **đi theo symbolic link**. Có thể cấu hình `LinkOption.NOFOLLOW_LINKS` để hỏi **chính link** thay vì target. Một dangling symlink có thể tồn tại như một đối tượng tệp dù target đã biến mất.

~~~java
boolean targetExists = Files.exists(path);
boolean linkItselfExists = Files.exists(path, LinkOption.NOFOLLOW_LINKS);
~~~

Đoạn trên là minh họa, cần import `LinkOption`. Hai giá trị có thể khác trong tình huống symlink; **cả hai cũng chỉ là kết quả kiểm tra tại thời điểm gọi**. `NOFOLLOW_LINKS` không khóa thư mục và không ngăn một tác nhân khác thay thế link sau đó.

## 4. Chương trình Java 21: thay đổi trạng thái có chủ đích giữa check và use

Ví dụ dưới đây **không phụ thuộc vào race thực ngẫu nhiên**: chương trình chủ động tạo/xóa/thay file **sau** bước kiểm tra nhưng **trước** bước sử dụng. Nó tái hiện chính xác một thứ tự sự kiện mà hệ thống nhiều luồng/tiến trình cũng có thể gặp.

Bài test chứng minh bốn tình huống:

1. `Files.exists` trả `true`, nhưng file bị xóa trước khi đọc.
2. `Files.notExists` trả `true`, nhưng một tác nhân khác tạo cùng tên trước bước tạo của mình.
3. `Files.size` trả kích thước ban đầu, nhưng nội dung đã đổi trước khi đọc.
4. `Files.isReadable` trả `true`, nhưng file bị xóa trước bước đọc thực tế.

Nó cũng minh họa phương pháp đúng: **thực hiện thao tác rồi xử lý ngoại lệ**, và sử dụng `CREATE_NEW` để việc “chỉ tạo khi chưa có file” được kiểm tra **ở chính bước tạo**.

Tạo file `src/main/java/demo/CheckThenActExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Optional;

public final class CheckThenActExample {
    private CheckThenActExample() {}

    static Optional<String> readIfPresent(Path path) throws IOException {
        try {
            return Optional.of(Files.readString(path, StandardCharsets.UTF_8));
        } catch (NoSuchFileException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("check-act-");
        Path report = work.resolve("report.txt");
        Path claim = work.resolve("claim.txt");

        try {
            Files.writeString(report, "first", StandardCharsets.UTF_8);
            System.out.println("exists-before=" + Files.exists(report));
            Files.delete(report);
            try {
                Files.readString(report, StandardCharsets.UTF_8);
            } catch (NoSuchFileException ex) {
                System.out.println("read-after-delete=NoSuchFileException");
            }
            System.out.println("safe-missing=" + readIfPresent(report).isEmpty());

            System.out.println("slot-absent-before=" + Files.notExists(claim));
            Files.writeString(claim, "competitor", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            try {
                Files.writeString(claim, "mine", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("claim-after-create=FileAlreadyExistsException");
            }
            System.out.println("claim-content="
                    + Files.readString(claim, StandardCharsets.UTF_8));

            Files.writeString(report, "A", StandardCharsets.UTF_8);
            long checkedSize = Files.size(report);
            Files.writeString(report, "changed", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("size-when-checked=" + checkedSize);
            System.out.println("content-when-used="
                    + Files.readString(report, StandardCharsets.UTF_8));

            System.out.println("readable-when-checked=" + Files.isReadable(report));
            Files.delete(report);
            try {
                Files.readString(report, StandardCharsets.UTF_8);
            } catch (NoSuchFileException ex) {
                System.out.println("read-after-readable=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(report);
            Files.deleteIfExists(claim);
            Files.deleteIfExists(work);
        }
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK 21 hoặc JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/CheckThenActExample.java
java -cp out demo.CheckThenActExample
~~~

**Stdout chính xác** trên file system mặc định đã kiểm thử:

~~~text
exists-before=true
read-after-delete=NoSuchFileException
safe-missing=true
slot-absent-before=true
claim-after-create=FileAlreadyExistsException
claim-content=competitor
size-when-checked=1
content-when-used=changed
readable-when-checked=true
read-after-readable=NoSuchFileException
~~~

### 4.1. Ý nghĩa của từng nhóm kết quả

**`exists-before=true` / `read-after-delete=NoSuchFileException`:** file có tồn tại ở thời điểm `exists`, nhưng `Files.delete` đã làm thay đổi sự thật đó trước `readString`. Kiểm tra tồn tại thành công không bảo đảm lần mở file tiếp theo thành công.

**`safe-missing=true`:** `readIfPresent` không cần `exists` trước. Nó thử đọc trực tiếp, chỉ coi **`NoSuchFileException`** là trường hợp “không có file” và để các `IOException` khác truyền ra. Đây là **lựa chọn hợp đồng của helper**: không biến lỗi quyền truy cập, hỏng đĩa hay lỗi giải mã thành “file không có”.

**`slot-absent-before=true`:** trước khi tạo, tên `claim.txt` được xác định chưa tồn tại. Nhưng một tác nhân (ở đây chính chương trình để test có tính quyết định) tạo file trước bước tiếp theo.

**`claim-after-create=FileAlreadyExistsException` / `claim-content=competitor`:** bước tạo thứ hai dùng `CREATE_NEW` thất bại thay vì ghi đè file đã được tác nhân kia tạo. File vẫn chứa `competitor`, không bị đổi thành `mine`.

**`size-when-checked=1` / `content-when-used=changed`:** dữ liệu ban đầu chỉ một byte ASCII `A`. Sau bước kiểm tra kích thước, chương trình đã ghi `"changed"`, nên người đọc sau đó thấy nội dung mới. Kích thước trả về trước đó không phải một ràng buộc về số byte trong lần đọc tiếp theo.

**`readable-when-checked=true` / `read-after-readable=NoSuchFileException`:** kết quả `isReadable` không bảo đảm file vẫn tồn tại hoặc còn quyền đọc lúc thao tác thật.

Ví dụ chủ động làm thay đổi file giữa các lệnh; nó **không chứng minh rằng JVM tự gây race**. Nó chứng minh giả định về trạng thái bất biến là không hợp lệ khi có bất kỳ tác nhân nào được phép thay đổi file system giữa check và use.

## 5. Mẫu thiết kế tốt: thử hành động thật và bắt ngoại lệ phù hợp

Đối với phần lớn thao tác file, thay vì:

~~~java
// Anti-pattern: kết quả exists có thể hết hạn trước read.
if (Files.exists(path)) {
    return Files.readString(path, StandardCharsets.UTF_8);
}
return "";
~~~

hãy dùng một helper có **hợp đồng xử lý lỗi rõ ràng**:

~~~java
static Optional<String> readIfPresent(Path path) throws IOException {
    try {
        return Optional.of(Files.readString(path, StandardCharsets.UTF_8));
    } catch (NoSuchFileException ex) {
        return Optional.empty();
    }
}
~~~

Đây là **phương thức đầy đủ** khi đặt trong một class với import `Optional`, `Path`, `Files`, `StandardCharsets`, `IOException`, `NoSuchFileException`. Nó là cùng helper đã chạy trong ví dụ chính.

Lợi ích:

- Không có khoảng trống do bước **`exists` riêng** trước khi đọc.
- Thành công dựa trên **readString hoàn tất thật**, không dựa trên boolean dự đoán.
- Chỉ dùng `Optional.empty()` cho **trường hợp file không có**, nếu đó là nghĩa mà API của bạn muốn cung cấp.
- Các lỗi khác vẫn được **ném lên caller**, vì chính sách retry/thông báo/log khác nhau theo nguyên nhân.

**Không hiểu nhầm:** bỏ precheck **không loại bỏ mọi race trong quá trình đọc**. Một tiến trình khác vẫn có thể thay đổi nội dung file khi thao tác đang diễn ra, và hệ thống tệp có thể báo I/O error. Cách viết này loại bỏ sự phụ thuộc sai vào *kết quả kiểm tra cũ*, chứ không tạo snapshot bất biến hoặc transaction.

### 5.1. Không bắt tràn lan rồi coi mọi lỗi là “không có file”

Không nên:

~~~java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (IOException ex) {
    return "";
}
~~~

Đây là đoạn **phản ví dụ**. Nó có thể che cả `AccessDeniedException`, `MalformedInputException`, lỗi thiết bị hoặc nhiều tình huống khác bằng một chuỗi rỗng có vẻ hợp lệ.

Đọc file thành công nhưng rỗng và đọc file thất bại **không phải cùng một kết quả nghiệp vụ**. Nếu muốn hiển thị lỗi thân thiện, nên giữ nguyên nguyên nhân hoặc phân loại các ngoại lệ cụ thể rồi trả kết quả mang trạng thái lỗi rõ ràng, thay vì mất dấu.

### 5.2. Retry phải có giới hạn và biết lỗi nào có thể retry

Khi trạng thái file biến động, **retry** có thể phù hợp cho một số lỗi tạm thời. Nhưng cần:

- Xác định lỗi nào thật sự tạm thời, lỗi nào là lỗi quyền, sai đường dẫn, sai charset hoặc dữ liệu không hợp lệ.
- Giới hạn số lần/ thời gian retry, có backoff khi cần.
- Bảo đảm thao tác được retry **idempotent** hoặc có cơ chế deduplication phù hợp. Retry thao tác ghi có thể tạo dữ liệu trùng hoặc làm hỏng file.
- Không biến lỗi bảo mật/validation thành vòng lặp retry vô hạn.

`Files.exists` lặp lại nhiều lần trước khi thực hiện một thao tác không giải quyết khoảng trống TOCTOU. Ngay cả khi lần kiểm tra cuối trả true, file vẫn có thể đổi ngay sau đó.

## 6. Khi muốn “chỉ tạo nếu chưa tồn tại”: sử dụng thao tác nguyên tử

Sai lầm thường gặp:

~~~java
// Anti-pattern: có thể có tác nhân khác tạo file giữa hai dòng.
if (Files.notExists(path)) {
    Files.writeString(path, content, StandardCharsets.UTF_8);
}
~~~

Vấn đề: `Files.writeString` không truyền option sẽ mặc định **tạo nếu thiếu hoặc truncate file hiện có**. Nếu một tiến trình khác tạo file giữa `notExists` và `writeString`, đoạn trên có thể **ghi đè dữ liệu của họ**.

### 6.1. `StandardOpenOption.CREATE_NEW`

Thực hiện điều kiện “tên chưa có thì tạo” ở chính thao tác ghi:

~~~java
try {
    Files.writeString(path, content, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException ex) {
    // Tên đã tồn tại lúc thao tác tạo: chọn tên khác hoặc báo xung đột.
}
~~~

Đây là đoạn minh họa, cần `Path path`, `String content` và xử lý `IOException` bên ngoài.

Theo hợp đồng của `CREATE_NEW`, việc **kiểm tra sự tồn tại và tạo file nếu chưa có** là một thao tác **atomic đối với các hoạt động có thể ảnh hưởng thư mục đó**. Đây là một bảo đảm quan trọng mà việc tự ghép `notExists` + `writeString` không có.

**Giới hạn:** bảo đảm này liên quan **kiểm tra-và-tạo**. Nó không tự biến việc ghi toàn bộ nội dung thành một transaction không thể quan sát giữa chừng, không bảo đảm dữ liệu được flush/durable qua mất điện và không loại bỏ các lỗi I/O xảy ra sau khi file được tạo.

### 6.2. `Files.createFile`

Nếu chỉ muốn tạo file rỗng mới và xử lý xung đột:

~~~java
try {
    Files.createFile(path);
} catch (FileAlreadyExistsException ex) {
    // File đã tồn tại tại thời điểm tạo.
}
~~~

Theo Javadoc, `Files.createFile` thực hiện kiểm tra tồn tại và tạo file rỗng trong **một thao tác nguyên tử** ở mức API, khác với `if (!exists) create...`.

Sau khi file được tạo, nội dung vẫn có thể bị người khác sửa nếu họ có quyền. Nếu cần kiểm soát cùng một đối tượng file trong nhiều bước, phải quản lý file handle/quyền và hợp đồng thao tác cụ thể, không chỉ dùng tên `Path` làm bảo đảm.

### 6.3. `CREATE` khác `CREATE_NEW`

| Option | Ý nghĩa | Phù hợp với |
| --- | --- | --- |
| `CREATE` | Tạo file nếu chưa có; nếu đã có thì có thể mở file hiện hữu | Chủ đích cho phép ghi vào file đã tồn tại |
| `CREATE_NEW` | Tạo file **chỉ nếu chưa có**, từ chối tên đã tồn tại | Không được phép ghi đè một file do bên khác tạo |
| `TRUNCATE_EXISTING` | Khi được mở để ghi, rút file hiện hữu về kích thước 0 | Ghi đè có chủ đích; nguy hiểm nếu tên bị chiếm chỗ |
| `APPEND` | Thêm byte ở cuối file | Log/ghi bổ sung theo hợp đồng, **không tự bảo đảm transaction logic** |
| `WRITE` | Mở quyền ghi | Khi chủ ý thay nội dung |

Không dùng `CREATE` hay `TRUNCATE_EXISTING` như cách thay thế `CREATE_NEW` trong quy trình “tên phải chưa có”. Ngay cả khi `Files.notExists` vừa trả true, tên có thể bị chiếm chỗ ngay sau đó.

## 7. Khi tạo thư mục: `createDirectories` không giống nhiều lần precheck

Mẫu kém chắc chắn:

~~~java
if (!Files.exists(directory)) {
    Files.createDirectory(directory);
}
~~~

Nếu tác nhân khác tạo thư mục sau `exists` nhưng trước `createDirectory`, lệnh tạo của bạn có thể ném `FileAlreadyExistsException` dù trạng thái cuối cùng đã phù hợp.

Với mục tiêu **đảm bảo có một chuỗi thư mục cha**, có thể dùng:

~~~java
Files.createDirectories(directory);
~~~

`Files.createDirectories` tự tạo các thư mục cha chưa có, cho phép thư mục tồn tại sẵn theo hợp đồng và được thiết kế cho use case chuẩn bị cây thư mục. Tuy nhiên:

- Nó **không phải một transaction nguyên tử cho toàn bộ chuỗi thư mục**.
- Nếu gặp lỗi giữa chừng, **một số thư mục cha đã được tạo có thể vẫn còn**.
- Nếu path bị thay đổi hoặc một thành phần đã là file thường, vẫn có thể thất bại.
- Nếu bài toán là “chính tôi phải là người tạo mới thư mục này”, `createDirectories` không thay thế kiểm soát xung đột/ownership của `createDirectory`.

Dù dùng phương thức phù hợp, vẫn **xử lý ngoại lệ ở thao tác thật**.

## 8. `Files.isReadable`, `isWritable`, `isRegularFile` chỉ là quan sát

Một ứng dụng thường kiểm tra trước khi mở:

~~~java
if (Files.isRegularFile(path) && Files.isReadable(path)) {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Đây là đoạn phản ví dụ nếu chương trình coi các kiểm tra là *bảo đảm*. Giữa các lệnh, file có thể:

- Bị xóa, đổi tên hoặc thay bằng đối tượng khác.
- Bị sửa quyền truy cập.
- Bị thay bằng directory, symlink hoặc file khác.
- Bị thay đổi nội dung trong khi đang đọc.

`isReadable` còn có thể trả false khi **không thể xác định quyền truy cập**, và kể cả true cũng không phải lời cam kết mọi lần mở/đọc đều thành công.

**Khi nào kiểm tra vẫn có ích?** Trong UI muốn hiển thị trạng thái sơ bộ, trong log/diagnostics, khi lọc danh sách tệp hoặc khi lựa chọn thao tác dựa trên thông tin gần đúng. Tuy nhiên, **phải vẫn có xử lý lỗi của thao tác thật**.

### 8.1. `size`, timestamp và thuộc tính không phải snapshot vĩnh viễn

~~~java
long before = Files.size(path);
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Hai kết quả được lấy ở hai thời điểm khác nhau. File có thể tăng/giảm kích thước, giữ nguyên size nhưng đổi byte, hoặc bị thay thế giữa hai lần gọi. Cùng timestamp cũng không phải bằng chứng chắc chắn nội dung không thay đổi: độ phân giải thời gian, cách cập nhật metadata và các thao tác bên ngoài còn ảnh hưởng.

Nếu cần một **snapshot nhất quán** của dữ liệu:

- Xem liệu hệ thống tệp/storage cung cấp snapshot/versioning hoặc lock phù hợp không.
- Nếu có thể, **mở một handle** rồi đọc theo một giao thức có quản lý concurrency, thay vì liên tục tra cứu lại đường dẫn bằng tên.
- Với dữ liệu quan trọng, xem xét checksum, version marker, locking hoặc cơ chế transaction **theo hệ thống lưu trữ cụ thể**.
- Không tuyên bố rằng một file handle tự động ngăn mọi thay đổi đồng thời của nội dung: các tiến trình khác vẫn có thể ghi tùy hệ điều hành và quyền.

`BasicFileAttributes.fileKey()` có thể hỗ trợ phân biệt đối tượng trong một số provider, nhưng có thể là `null`, phụ thuộc filesystem và không thay thế quản lý race/ownership.

## 9. Symlink, `toRealPath` và path traversal: check rồi open vẫn có thể race

Kiểm tra trước khi mở file nhạy cảm thường gặp:

~~~java
Path realRoot = allowedRoot.toRealPath();
Path realTarget = realRoot.resolve(userRelative).toRealPath();

if (!realTarget.startsWith(realRoot)) {
    throw new SecurityException("outside allowed root");
}

// Kiểm tra ở trên KHÔNG khóa link/directory trước lần mở.
String text = Files.readString(realTarget, StandardCharsets.UTF_8);
~~~

Đây là đoạn **minh họa chưa đủ để xây sandbox an toàn**, cần các biến và import phù hợp.

- `toRealPath()` hỏi file system về path thật **tại thời điểm kiểm tra**.
- `Path.startsWith(Path)` so các **thành phần path**, tốt hơn `String.startsWith` nhưng không ngăn thay đổi sau đó.
- Nếu attacker có thể thay symlink hoặc một directory giữa check và open, thao tác sau có thể truy cập một đối tượng **khác**.
- `LinkOption.NOFOLLOW_LINKS` thay đổi cách follow symlink cho các API hỗ trợ; nó **không tự khóa toàn bộ cây thư mục**, cũng không thay cho thiết kế bảo mật.
- Với quyền truy cập nhạy cảm, cân nhắc kiểm soát quyền ở hệ điều hành và API kiểu **directory handle** như `SecureDirectoryStream` trên provider hỗ trợ, thay vì tự tin vào một chuỗi boolean checks.

**Phân biệt hai mức độ:** việc dùng `toRealPath` và `Path.startsWith` có thể là một bước **hợp lý để xác định tình trạng hiện tại**, nhưng yêu cầu “không bao giờ mở ra ngoài thư mục” trong môi trường có đối thủ đòi cơ chế access an toàn trước race, không chỉ một kiểm tra path đã rút gọn.

## 10. Thay file nhiều bước: `ATOMIC_MOVE` có phạm vi bảo đảm cụ thể

Với file cấu hình cần được cập nhật, ghi đè trực tiếp có thể làm người đọc nhìn thấy file rỗng hoặc file mới chỉ ghi một phần. Một mẫu thường cân nhắc là:

1. Tạo một **file tạm riêng** trong cùng vùng file system thích hợp.
2. Ghi toàn bộ nội dung và xử lý lỗi của bước ghi.
3. Khi nội dung đã sẵn sàng, đổi tên/di chuyển file tạm tới đích qua API thích hợp, ví dụ `Files.move` với `StandardCopyOption.ATOMIC_MOVE` **nếu provider hỗ trợ**.
4. Có chiến lược xử lý lỗi, cleanup và độ bền dữ liệu theo hệ thống tệp.

Ví dụ cấu trúc ý tưởng:

~~~java
Files.move(staged, destination, StandardCopyOption.ATOMIC_MOVE);
~~~

Đây là **đoạn minh họa**, không phải một quy trình ghi an toàn hoàn chỉnh. Trên filesystem không hỗ trợ thao tác đó, có thể ném `AtomicMoveNotSupportedException`. Khi dùng `ATOMIC_MOVE`, việc xử lý nếu **đích đã tồn tại** phụ thuộc implementation theo hợp đồng Javadoc; đừng mặc nhiên khẳng định có thể dùng thêm `REPLACE_EXISTING` để tạo semantics giống nhau trên mọi provider.

**Không nhầm:** `ATOMIC_MOVE` nói về **di chuyển/đổi tên là thao tác nguyên tử được hỗ trợ**. Nó không đảm bảo toàn bộ quá trình tạo file tạm, ghi nội dung, flush, fsync và move là một transaction duy nhất hoặc luôn bền trước mất điện. Cần xác định riêng mục tiêu: *không thấy file ghi dở*, *không ghi đè file người khác*, *bảo toàn dữ liệu khi mất điện* hay *bảo mật chống symlink race*.

## 11. Phạm vi bảo đảm: atomic creation không có nghĩa mọi bước sau đều atomic

Khi nhìn thấy `Files.createFile` hoặc `StandardOpenOption.CREATE_NEW`, hãy chỉ khẳng định điều được Javadoc bảo đảm: **kiểm tra tên chưa tồn tại và tạo file nếu chưa có là một bước nguyên tử**.

Không tự suy ra:

- Mọi byte được ghi sau đó xuất hiện đồng thời trước mọi reader.
- Quyền truy cập của file sẽ không thay đổi.
- Không ai có thể xóa hoặc đổi tên file ngay sau khi tạo.
- Không tiến trình khác nào có thể ghi vào nội dung.
- File sẽ sống vĩnh viễn nếu process gặp crash.
- File và nội dung chắc chắn tồn tại sau mất điện.

Điều tương tự áp dụng với `Files.deleteIfExists`: dùng API này có thể tránh một bước “exists rồi delete” không cần thiết, nhưng không nên hiểu nó là bảo đảm delete luôn thành công hoặc file sẽ không được tạo lại ngay sau khi xóa.

**Chọn đúng mức atomicity của nghiệp vụ**, rồi tìm API và bảo đảm từ filesystem/storage thực tế, thay vì ghép nhiều phép kiểm tra độc lập rồi gọi đó là transaction.

## 12. Cách thiết kế API và exception handling rõ ràng

Một workflow tệp thường có nhiều loại kết quả:

| Kết quả thật của thao tác | Cách ứng dụng có thể xử lý |
| --- | --- |
| Đọc thành công | Trả dữ liệu và tiếp tục |
| `NoSuchFileException` | Nếu “không có file” là bình thường, trả `Optional.empty()` hoặc thông báo phù hợp |
| `FileAlreadyExistsException` | Trong chế độ tạo mới duy nhất, báo xung đột hoặc chọn tên mới |
| `AccessDeniedException` | Báo thiếu quyền / từ chối truy cập, không coi như file rỗng |
| `MalformedInputException` | Sai charset hoặc byte không hợp lệ; xử lý theo định dạng và chính sách dữ liệu |
| `AtomicMoveNotSupportedException` | Chọn chiến lược fallback theo yêu cầu thực tế, **không nói fallback non-atomic là tương đương** |
| `IOException` khác | Log/chẩn đoán, retry có giới hạn nếu được phép, hoặc báo thất bại |

Bắt một subtype cụ thể là cách **diễn đạt quyết định nghiệp vụ**, chứ không chỉ làm compiler hết phàn nàn về checked exceptions.

### 12.1. Vì sao `readIfPresent` chỉ bắt `NoSuchFileException`?

Trong bài thử, khi đường dẫn không còn file, helper trả `Optional.empty()`. Nhưng nếu gặp `AccessDeniedException` hay lỗi thiết bị, một “empty value” sẽ nói sai sự thật với caller. Đây là lý do helper chỉ bắt lỗi **mang nghĩa dữ liệu có thể vắng mặt**.

Nếu ứng dụng cần báo **file không tồn tại, lỗi quyền và lỗi I/O** thành ba trạng thái khác nhau, có thể định nghĩa kết quả tường minh (ví dụ sealed interface/record trong Java hiện đại). Không cần ép mọi lỗi thành null hoặc string rỗng.

### 12.2. Có nên dùng `Files.exists` trước khi hiển thị một lựa chọn UI?

Có thể. Nếu mục đích là hiển thị tình trạng “hiện có file” để gợi ý nút mở, phép kiểm tra là hữu ích. Nhưng khi người dùng nhấn nút, **phải vẫn thử mở và xử lý lỗi** vì trạng thái có thể đã đổi trong khoảng thời gian người dùng suy nghĩ.

Nên phân biệt **status hint** (gợi ý) với **precondition guarantee** (điều kiện được bảo đảm). API `Files` không biến một boolean đọc trước đó thành precondition còn hiệu lực.

## 13. Kiểm thử TOCTOU theo cách đáng tin cậy

Một unit/integration test chỉ dùng hai luồng chạy “gần như đồng thời” có thể thất thường do scheduler: đôi khi race xuất hiện, đôi khi không. Muốn kiểm thử logic khi trạng thái thay đổi, nên **điều khiển thứ tự sự kiện**:

1. Tạo file.
2. Kiểm tra `exists`.
3. **Chủ động xóa file**.
4. Thử đọc và xác nhận `NoSuchFileException`.

Hoặc:

1. Kiểm tra `notExists`.
2. Tạo file bằng một bước đóng vai tác nhân khác.
3. Thử tạo lại bằng `CREATE_NEW`.
4. Xác nhận nhận `FileAlreadyExistsException` **và file gốc không bị ghi đè**.

Đó là cách chương trình `CheckThenActExample` thực hiện. Test phản ánh một interleaving có thể xảy ra trong thực tế, nhưng vẫn cho stdout lặp lại được mà không cần đoán thời gian scheduler.

### 13.1. Cần kiểm thử thêm những trường hợp nào?

- File bị xóa hoặc đổi tên sau khi lấy metadata.
- File bị thay bằng directory sau khi `isRegularFile`.
- Symlink bị thay trước khi mở (trong môi trường test có hỗ trợ symlink).
- Không có quyền đọc/ghi, hoặc quyền đổi sau check.
- File nội dung thay đổi nhưng kích thước không đổi.
- Hai tác nhân cùng muốn tạo một tên, hoặc cùng append vào một file.
- Ghi file cấu hình bị lỗi giữa chừng và cleanup file tạm.
- `Files.exists`/`notExists` trả trạng thái **không xác định** khi provider từ chối cho biết.
- File system không hỗ trợ `ATOMIC_MOVE` và workflow fallback phải tuân theo hợp đồng.

Không ép mọi test phụ thuộc quyền tạo symlink hay danh tính file trên tất cả nền tảng. Test cross-platform nên dùng tài nguyên tạm và các biểu thức boolean/ngoại lệ ổn định; test symlink/security nên chạy trên đúng provider và quyền yêu cầu.

## 14. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| `if (Files.exists(p)) read(p)` và tin chắc không lỗi | File có thể mất sau check | Thực hiện read thật, xử lý `IOException` |
| `if (!Files.exists(p)) create(p)` | `!exists` có thể là **không xác định**, tên cũng có thể bị tạo sau check | `CREATE_NEW` hoặc `createFile` |
| `if (Files.notExists(p)) writeString(p, text)` | Mặc định write có thể truncate file vừa được bên khác tạo | `CREATE_NEW` + xử lý `FileAlreadyExistsException` |
| `Files.isReadable(p) == true` nghĩa là đọc chắc chắn thành công | Quyền/file có thể đổi sau đó | Bắt lỗi khi mở/đọc |
| `Files.size(p)` là kích thước cố định cho lần đọc tiếp theo | File có thể bị sửa | Dựa trên dữ liệu thực đọc hoặc snapshot/version |
| `Files.readAttributes` chứng minh metadata bất biến | Kết quả chỉ là một lần quan sát | Không giữ assumption qua nhiều thao tác |
| `toRealPath().startsWith(root)` là sandbox hoàn chỉnh | Symlink/directory có thể đổi giữa check/open | Access qua cơ chế chống TOCTOU khi cần |
| Bắt mọi `IOException` rồi trả empty | Che lỗi quyền/charset/hệ thống | Phân loại exception, không đánh đồng lỗi |
| Gọi nhiều lần `exists` để thu hẹp race | Race vẫn tồn tại ngay sau check cuối | Thiết kế thao tác có semantics nguyên tử hoặc hợp đồng lỗi |
| Tưởng `CREATE_NEW` làm cả file-write transaction | Chỉ check-và-create được bảo đảm atomic | Dùng staging/move/độ bền theo nhu cầu |
| Tưởng `ATOMIC_MOVE` luôn sẵn có và thay đích đồng nhất | Phụ thuộc provider/FS; target-exists semantics không chung | Xử lý unsupported và thiết kế chính sách ghi đè |
| Quên dọn tài nguyên tạm sau test | Rò rỉ file/thư mục | Dùng `try/finally`/try-with-resources |
| Dựa vào `String.startsWith` cho boundary | Prefix ký tự không phải ranh giới thư mục | Dùng `Path.startsWith` + giải quyết vấn đề link/race |

## 15. Bài tập có đáp án

**Bài 1.** `Files.exists(path)` vừa trả true. Có thể bỏ `try/catch` quanh `Files.readString(path, charset)` vì file chắc chắn vẫn ở đó không?

**Đáp án:** Không. File có thể bị xóa, đổi tên, thay quyền, bị sửa hoặc gặp lỗi I/O sau check. `readString` vẫn có thể thất bại; xử lý checked `IOException` là bắt buộc theo API.

**Bài 2.** Tại sao `Files.notExists(path)` không thể dùng như một “khóa tên file”?

**Đáp án:** Nó chỉ quan sát tên tại thời điểm gọi. Một tác nhân khác có thể tạo tên ngay sau đó. Dùng `CREATE_NEW` hoặc `Files.createFile` để check-và-create nguyên tử.

**Bài 3.** Nếu `Files.exists(path) == false`, có thể khẳng định `Files.notExists(path) == true` không?

**Đáp án:** Không. Khi không xác định được trạng thái, cả hai có thể false. Hai lời gọi cũng có thể quan sát file system ở hai thời điểm khác nhau.

**Bài 4.** Một ứng dụng đọc size rồi cấp bộ đệm bằng đúng size ấy; file tăng thêm dữ liệu trước khi đọc. Giả định nào sai?

**Đáp án:** Kích thước là snapshot metadata tại thời điểm kiểm tra, không phải giới hạn bất biến cho mọi lần đọc sau đó. Dùng API đọc có quản lý lượng dữ liệu thực tế hoặc cơ chế snapshot/version phù hợp.

**Bài 5.** `isReadable` trả true rồi `newBufferedReader` thất bại. Có nhất thiết Java `Files` sai không?

**Đáp án:** Không. Trạng thái file, quyền hoặc filesystem có thể thay đổi; boolean kiểm tra không bảo đảm một thao tác sau sẽ thành công.

**Bài 6.** Muốn chỉ tạo mới một báo cáo nếu tên chưa được ai sử dụng, nên dùng `CREATE` hay `CREATE_NEW`?

**Đáp án:** `CREATE_NEW`. Nó cung cấp check-và-create nguyên tử và từ chối tên đã tồn tại. `CREATE` không có cùng ý nghĩa “tên phải còn trống”.

**Bài 7.** `Files.createDirectories(dir)` có tạo nguyên tử cả một chuỗi `a/b/c` không?

**Đáp án:** Không. Nó hỗ trợ tạo các thư mục cha theo nhu cầu, nhưng không cam kết cả chuỗi là một giao dịch nguyên tử. Khi lỗi, có thể còn thư mục cha đã tạo một phần.

**Bài 8.** Vì sao `toRealPath()` và `Path.startsWith(...)` chưa đủ để đảm bảo chống mọi tấn công symlink race?

**Đáp án:** Vì sau khi check path thật, kẻ có quyền thay directory/symlink có thể làm thay đổi mục tiêu trước khi mở. Cần thiết kế access giảm race, không chỉ kiểm tra tên.

**Bài 9.** Có nên bắt mọi `IOException` rồi trả `Optional.empty()` không?

**Đáp án:** Không, trừ khi nghiệp vụ thực sự định nghĩa tất cả lỗi I/O giống nhau (điều này hiếm khi đúng). Đối với helper “đọc nếu tồn tại”, chỉ bắt `NoSuchFileException` giúp giữ thông tin của lỗi quyền và lỗi I/O khác.

**Bài 10.** `CREATE_NEW` có đồng nghĩa file hoàn chỉnh được ghi và fsync nguyên tử, không thể mất dữ liệu nếu máy tắt điện không?

**Đáp án:** Không. Bảo đảm là **kiểm tra-và-tạo** tên file trong một bước nguyên tử. Việc ghi nội dung, độ bền dữ liệu và chống mất điện là các yêu cầu khác.

## 16. Checklist áp dụng trong code review

- [ ] Chỉ xem kết quả kiểm tra `Files` là **thông tin ở thời điểm quan sát**.
- [ ] Không đặt độ đúng của thao tác file vào khoảng trống `exists/notExists/isReadable` rồi hành động.
- [ ] Nếu mục tiêu là mở/đọc/ghi, thực hiện thao tác đó và xử lý exception đúng ngữ nghĩa.
- [ ] Không coi `!Files.exists` tương đương `Files.notExists`.
- [ ] Với “chỉ tạo nếu chưa có”, dùng `CREATE_NEW`/`Files.createFile`; tránh precheck + ghi có truncate.
- [ ] Với cây thư mục cha, dùng `createDirectories` đúng mục đích và hiểu thiếu atomicity toàn chuỗi.
- [ ] Khi cần file identity/ownership, suy nghĩ về file handle, symlink và sự thay đổi của filesystem.
- [ ] Không xem `toRealPath`/`isSameFile`/`readAttributes` là snapshot vĩnh viễn.
- [ ] Với file quan trọng, tách yêu cầu “không ghi đè”, “không lộ nội dung viết dở”, “bền khi mất điện” và “chống symlink race”.
- [ ] Khi retry, chọn lỗi phù hợp, giới hạn retry và quan tâm idempotency.
- [ ] Kiểm thử interleaving có chủ đích, không dựa vào delay/scheduler để hy vọng tạo race.
- [ ] Dùng Java NIO.2 và API hiện đại có bảo đảm được tài liệu mô tả, không dựa vào API legacy.

## 17. Tài liệu chính thức còn áp dụng

- [Java SE 21 — Files.exists](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#exists(java.nio.file.Path,java.nio.file.LinkOption...)): chỉ là kiểm tra tại thời điểm gọi, không bảo đảm lần truy cập sau và có thể không xác định được tồn tại.
- [Java SE 21 — Files.notExists](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#notExists(java.nio.file.Path,java.nio.file.LinkOption...)): không phải phủ định `exists` trong mọi tình huống.
- [Java SE 21 — Files.isReadable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#isReadable(java.nio.file.Path)): kiểm tra best-effort và trạng thái có thể đổi ngay.
- [Java SE 21 — Files.createFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#createFile(java.nio.file.Path,java.nio.file.attribute.FileAttribute...)): check-và-create nguyên tử.
- [Java SE 21 — StandardOpenOption.CREATE_NEW](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html#CREATE_NEW): check-và-create nguyên tử khi mở file để ghi.
- [Java SE 21 — Files.createDirectories](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#createDirectories(java.nio.file.Path,java.nio.file.attribute.FileAttribute...)): tạo chuỗi thư mục cha, không toàn bộ nguyên tử.
- [Java SE 21 — Files.move](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)) và [StandardCopyOption.ATOMIC_MOVE](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html#ATOMIC_MOVE): thao tác chuyển atomic nếu hỗ trợ, các giới hạn đối với target và provider.
- [Java SE 21 — Files.readString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#readString(java.nio.file.Path,java.nio.charset.Charset)): thao tác thực tế và các ngoại lệ.
- [Java SE 21 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): API directory-handle trên provider hỗ trợ để giảm rủi ro race.
- [Java SE 21 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): metadata, size, timestamps và `fileKey`.

**Kết luận:** trong hệ thống tệp có thể thay đổi, “đã kiểm tra” **không đồng nghĩa** “sẽ còn đúng lúc dùng”. Hãy thiết kế dựa trên kết quả của **thao tác thật và exception phù hợp**, tận dụng `CREATE_NEW`/`createFile` khi cần check-và-create nguyên tử, và xử lý symlink/ownership/TOCTOU một cách tường minh khi có yêu cầu an toàn. Đây là kiến thức vẫn cần thiết trên Java hiện đại.
