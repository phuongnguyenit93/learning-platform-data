# `Files.exists()`, `Files.notExists()` và trạng thái không xác định

## Mục tiêu bài học

Trong Java NIO.2, hai phương thức `Files.exists(Path, LinkOption...)` và `Files.notExists(Path, LinkOption...)` giúp kiểm tra **khả năng xác minh trạng thái tồn tại của một đường dẫn**. Chúng có vẻ đối xứng, nhưng **không phải hai hàm phủ định logic của nhau trong mọi hoàn cảnh**. Nếu không thể xác định trạng thái — chẳng hạn do lỗi truy cập metadata hoặc filesystem không phản hồi theo cách có thể kết luận — **cả hai có thể cùng trả về `false`**.

Sau bài này, bạn có thể:

- Phân biệt `Files.exists(path)`, `Files.notExists(path)` và toán tử `!Files.exists(path)`.
- Diễn giải đúng **ba tình trạng**: *xác nhận tồn tại*, *xác nhận không tồn tại*, và *không xác định được*.
- Hiểu `LinkOption.NOFOLLOW_LINKS`, symbolic link hợp lệ hoặc bị hỏng, và sự khác nhau giữa **link** và **đích của link**.
- Không nhầm “có đường dẫn” với “là file thông thường”, “có quyền đọc”, “nội dung ổn định” hay “mở thành công”.
- Tránh lỗi **TOCTOU (time-of-check-to-time-of-use)** khi kiểm tra trạng thái rồi mới mở, tạo, xóa hoặc sửa file.
- Biết khi nào dùng phép thao tác trực tiếp và ngoại lệ (`Files.readAttributes`, `Files.newInputStream`, `Files.createFile`…) thay cho việc chỉ tin kết quả boolean.
- Viết và chạy mã Java 17+, xử lý trạng thái không xác định mà không tự suy diễn thành file không tồn tại.

## 1. Nền tảng: `Path` không đồng nghĩa một file đã tồn tại

```java
Path path = Path.of("data", "report.txt");
```

Đây là **đoạn minh họa** với `import java.nio.file.Path;`. Việc tạo `Path` chỉ tạo **một đối tượng biểu diễn đường dẫn**, không tự tạo file, không kiểm tra quyền và không đảm bảo file có thật. Hệ điều hành và filesystem quyết định đường dẫn đó có thể được phân giải tới một entry tại thời điểm thực hiện thao tác I/O hay không.

Các yếu tố cần phân biệt:

- **Path**: cách biểu diễn một vị trí/đường dẫn trong một filesystem.
- **Entry**: đối tượng tại tên đó (file thông thường, thư mục, symbolic link, hoặc loại khác tùy filesystem).
- **Metadata**: thuộc tính file/entry như loại, kích thước, timestamps, quyền.
- **Filesystem provider**: lớp hiện thực đọc/ghi theo filesystem (default provider, ZipFS, provider bên thứ ba…).
- **Thao tác I/O**: mở file, tạo file, đọc thuộc tính, xóa, đổi tên — có thể phát sinh ngoại lệ và có thể bị ảnh hưởng bởi thay đổi đồng thời.

`Files.exists` và `Files.notExists` kiểm tra thông tin tồn tại **ở thời điểm gần lời gọi**, không đặt khóa lên entry và không biến đường dẫn thành reference bất biến.

## 2. API của `exists` và `notExists`

Hai chữ ký trong `java.nio.file.Files`:

```java
public static boolean exists(
    Path path, LinkOption... options);

public static boolean notExists(
    Path path, LinkOption... options);
```

Đây là **chữ ký API minh họa**, không phải mã cần định nghĩa lại trong ứng dụng. `LinkOption` nằm trong `java.nio.file`. Nếu bỏ các option, **mặc định các phương thức theo symbolic link** khi kiểm tra.

Ví dụ sử dụng:

```java
Path p = Path.of("data.txt");

boolean confirmedPresent = Files.exists(p);
boolean confirmedAbsent = Files.notExists(p);

boolean linkEntryPresent =
    Files.exists(p, LinkOption.NOFOLLOW_LINKS);
```

Đây là **đoạn minh họa**; cần `Files`, `Path`, `LinkOption`, và `p` phải có ý nghĩa với filesystem hiện hành.

Các diễn giải chính:

| Biểu thức | Chỉ nên kết luận |
|---|---|
| `Files.exists(path) == true` | Đã xác minh đối tượng theo chính sách link được chọn **có tồn tại** tại lần kiểm tra |
| `Files.notExists(path) == true` | Đã xác minh đối tượng theo chính sách link được chọn **không tồn tại** tại lần kiểm tra |
| `Files.exists(path) == false` | **Chưa xác minh được rằng nó tồn tại**; có thể không tồn tại **hoặc** chưa biết |
| `Files.notExists(path) == false` | **Chưa xác minh được rằng nó không tồn tại**; có thể tồn tại **hoặc** chưa biết |
| Cả hai cùng `false` | **Trạng thái không xác định** từ hai phép kiểm tra |
| `!Files.exists(path)` | Phủ định kết quả boolean của một phép kiểm tra; **không tương đương** `Files.notExists(path)` trong trường hợp chưa biết |

Từ đây rút ra một điều: **một kết quả boolean `false` không luôn mang thông tin âm tính chắc chắn về filesystem**.

## 3. Bảng chân trị ba trạng thái: điểm cốt lõi

Nếu hai kiểm tra quan sát **cùng một trạng thái không đổi** và cùng chính sách theo link, ta có:

| Trạng thái có thể xác minh | `Files.exists(p)` | `Files.notExists(p)` | Phải hiểu là |
|---|:---:|:---:|---|
| Đã xác minh tồn tại | `true` | `false` | **PRESENT** |
| Đã xác minh không tồn tại | `false` | `true` | **ABSENT** |
| Không thể xác minh trạng thái | `false` | `false` | **UNKNOWN** |
| `true` và `true` | Không phải kết quả nhất quán của một trạng thái bất biến | | Nếu quan sát ở hai thời điểm khác nhau, có thể do thay đổi đồng thời hoặc yếu tố provider |

**Không nên viết:**

```java
if (!Files.exists(path)) {
    System.out.println("File chắc chắn không tồn tại");
}
```

Đây là **phản ví dụ**: nhánh này cũng chạy khi `exists` không xác minh được trạng thái. Nếu cần thông báo chắc chắn không tồn tại, kiểm tra `Files.notExists(path)`.

Một cách làm rõ cả ba trạng thái:

```java
if (Files.exists(path)) {
    System.out.println("Đã xác minh tồn tại");
} else if (Files.notExists(path)) {
    System.out.println("Đã xác minh không tồn tại");
} else {
    System.out.println("Không xác minh được trạng thái");
}
```

Đây là **đoạn minh họa**, `path` là `Path` và đã import `Files`. **Lưu ý:** Hai lời gọi xảy ra ở **hai thời điểm**; file có thể được tạo/xóa/đổi tên ở giữa. Vì vậy, đây là cách mô tả hợp lý để **phân loại quan sát gần đúng**, không phải giao dịch nguyên tử về trạng thái file.

### Vì sao có UNKNOWN?

Một số tình huống khiến provider không thể xác minh chắc chắn:

1. Quyền truy cập directory hoặc metadata không đủ để truy vấn đường dẫn.
2. Storage từ xa hoặc filesystem provider không phản hồi, không thể xác minh trạng thái.
3. Lỗi hệ thống tệp, môi trường container, mount, hoặc tầng I/O khiến tra cứu metadata không có kết quả kết luận được.
4. Một symbolic link hoặc đường dẫn có quá trình phân giải lỗi.
5. Một số tình huống đặc thù của filesystem/provider làm thông tin tồn tại không sẵn có.

**Không khẳng định tuyệt đối “permission denied luôn làm cả hai trả false”**: trên một filesystem cụ thể, metadata có thể vẫn đủ để kết luận tồn tại; trên provider khác có thể trả giá trị khác hoặc ném `SecurityException` theo chính sách bảo mật. Điều quan trọng là không biến trường hợp không chắc thành `ABSENT`.

Theo hợp đồng Java, khi không thể xác định kết quả vì lỗi truy cập file, `exists` và `notExists` có thể trả `false`; chúng không cung cấp mọi chi tiết lỗi I/O qua kiểu trả về boolean. Một số kiểm tra bảo mật có thể dẫn đến `SecurityException` không kiểm tra (*unchecked*).

## 4. Tại sao `notExists()` không phải `!exists()`?

Trong logic Boolean hai giá trị thông thường:

```text
exists = true  → not exists = false
exists = false → not exists = true
```

Nhưng các API này không chỉ biểu diễn trạng thái vật lý. Chúng biểu diễn **khả năng xác minh** một mệnh đề từ filesystem:

```text
                        Phép tra cứu trạng thái
                                 │
               ┌─────────────────┼──────────────────┐
               ▼                 ▼                  ▼
        Xác nhận có         Xác nhận không        Không xác minh
               │                 │                  │
        exists = true      exists = false     exists = false
        notExists = false  notExists = true   notExists = false
```

Do đó:

```text
!Files.exists(p)        = "không nhận được kết quả xác nhận có"
Files.notExists(p)      = "nhận được kết quả xác nhận không"
```

Hai câu khác nhau khi kết quả bị **unknown**.

Trong code nghiệp vụ, hãy đặt tên biến theo thông tin thật:

```java
boolean isConfirmedMissing = Files.notExists(path);
boolean isConfirmedPresent = Files.exists(path);
```

Tránh đặt tên `missing` cho `!Files.exists(path)` nếu người đọc có thể hiểu nó là sự vắng mặt chắc chắn.

Nếu hệ thống cần **một trạng thái duy nhất**, một kiểu enum ba giá trị sẽ diễn đạt hợp đồng tốt hơn hai cờ boolean, dù cần nhớ đây vẫn chỉ là snapshot không nguyên tử từ nhiều phép kiểm tra.

## 5. Ví dụ Java 17: trạng thái tệp tồn tại và tệp đã xóa

Lưu **`ExistenceBasicsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExistenceBasicsDemo {
    private static void show(String label, Path path) {
        System.out.println(label
            + " exists=" + Files.exists(path)
            + " notExists=" + Files.notExists(path));
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("exists-demo-", ".txt");

        try {
            Files.writeString(file, "hello", StandardCharsets.UTF_8);
            show("created", file);
        } finally {
            Files.deleteIfExists(file);
        }

        show("removed", file);
    }
}
```

Chạy:

```bash
javac ExistenceBasicsDemo.java
java ExistenceBasicsDemo
```

Kết quả trong filesystem bình thường, nếu tạo/xóa và tra cứu metadata đều thành công:

```text
created exists=true notExists=false
removed exists=false notExists=true
```

Giải thích:

1. `Files.createTempFile` tạo một file mới trên filesystem và trả `Path`.
2. `Files.writeString` ghi nội dung vào file; việc ghi nội dung không ảnh hưởng đến bản chất kiểm tra tồn tại.
3. Trong vùng `try`, file đang tồn tại và có thể xác minh nên `exists == true`.
4. `Files.deleteIfExists` xóa file trong khối `finally`; nếu việc xóa thành công, lần kiểm tra tiếp theo xác nhận vắng mặt.
5. Chương trình **không chứng minh** filesystem luôn trả được kết quả chắc chắn khi mất quyền, I/O lỗi hoặc trạng thái thay đổi đồng thời.

Ví dụ không in tên file tạm vì phần ngẫu nhiên của tên khác nhau ở mỗi lần chạy. Không cần thay tên thật của người dùng bằng dữ liệu cố định để có output deterministic; chỉ in trạng thái đã kiểm tra.

## 6. `LinkOption.NOFOLLOW_LINKS`: kiểm tra link hay đích?

Symbolic link (liên kết tượng trưng) là một entry đại diện đường dẫn tham chiếu đến entry khác. Mặc định, `Files.exists(link)` và `Files.notExists(link)` **theo symbolic link**. Khi truyền `LinkOption.NOFOLLOW_LINKS`, Java kiểm tra **bản thân link** thay vì đi đến target.

Ví dụ ý tưởng:

```text
directory/
├── target.txt                 (file thật)
└── shortcut.txt -> target.txt (symbolic link)
```

Nếu `target.txt` còn tồn tại, cả kiểm tra theo link lẫn không theo link có thể xác nhận có entry:

```java
Files.exists(link);                        // thường true
Files.exists(link, LinkOption.NOFOLLOW_LINKS); // true khi link hiện hữu
```

Đây là **đoạn minh họa**, `link` là `Path` đã trỏ tới symbolic link. Nhưng khi target bị xóa:

```text
directory/
├── target.txt                  (đã xóa)
└── shortcut.txt -> target.txt  (link vẫn còn)
```

Hai câu hỏi khác nhau:

- **Theo link (mặc định):** Target có tồn tại không? Nếu đã xác minh target vắng mặt, `Files.exists(link)` là `false` và `Files.notExists(link)` là `true`.
- **Không theo link:** Entry symbolic link có tồn tại không? Nếu có và xác minh được, `Files.exists(link, NOFOLLOW_LINKS)` là `true` và `Files.notExists(link, NOFOLLOW_LINKS)` là `false`.

### Ma trận tượng trưng

| Trường hợp | Mặc định follow links | `NOFOLLOW_LINKS` |
|---|---|---|
| File thông thường tồn tại | Xác nhận tồn tại | Xác nhận tồn tại |
| Symlink tồn tại, target tồn tại | Thường xác nhận tồn tại | Xác nhận **link** tồn tại |
| Symlink tồn tại, target đã mất (*dangling link*) | Thường xác nhận target không tồn tại nếu có thể xác minh | Xác nhận **link** tồn tại |
| Đường dẫn thật sự không có entry | Xác nhận không tồn tại nếu có thể xác minh | Xác nhận không tồn tại nếu có thể xác minh |
| Không đủ thông tin truy cập metadata | Có thể UNKNOWN | Có thể UNKNOWN |

**Điểm mấu chốt:** `NOFOLLOW_LINKS` thay đổi **đối tượng đang được hỏi**, chứ không bảo đảm truy vấn chắc chắn thành công hoặc khắc phục mọi lỗi quyền.

### Khi nào dùng `NOFOLLOW_LINKS`?

- Công cụ quản trị muốn biết chính **symbolic link entry** có tồn tại hay không.
- Bộ dọn dẹp cần phân biệt “link hỏng nhưng vẫn có entry” với “tên hoàn toàn trống”.
- Logic không muốn metadata lookup tự động đi qua symlink.
- Một số workflow cần kiểm tra link rồi quyết định có xóa/đổi tên entry đó hay không.

Tuy nhiên, **kiểm tra `NOFOLLOW_LINKS` rồi mở file bình thường không tự ngăn rủi ro symlink**. Một process khác có thể thay entry sau kiểm tra. Với yêu cầu bảo mật, cần API mở/đọc phù hợp, quyền OS và xử lý TOCTOU.

## 7. Ví dụ Java 17: kiểm tra symbolic link bị hỏng (môi trường hỗ trợ)

Tạo symbolic link là thao tác có thể bị giới hạn trên Windows, trong container hoặc với filesystem provider nhất định. Vì vậy, ví dụ dưới đây **chỉ in kết quả xác định khi tạo link thành công và filesystem có ngữ nghĩa thông thường**; nếu thiếu quyền hỗ trợ, chương trình không giả định mọi môi trường đều giống nhau.

Lưu **`SymlinkExistenceDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymlinkExistenceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("link-demo-");
        Path link = dir.resolve("shortcut.txt");

        try {
            try {
                Files.createSymbolicLink(
                    link, Path.of("missing-target.txt"));
            } catch (UnsupportedOperationException
                     | SecurityException
                     | IOException ex) {
                System.out.println("Symlink unavailable");
                return;
            }

            System.out.println(
                "follow exists=" + Files.exists(link));
            System.out.println(
                "follow notExists=" + Files.notExists(link));
            System.out.println(
                "nofollow exists=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println(
                "nofollow notExists=" +
                    Files.notExists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac SymlinkExistenceDemo.java
java SymlinkExistenceDemo
```

Khi tạo symbolic link được hỗ trợ, link tồn tại và target không có, kết quả thông thường là:

```text
follow exists=false
follow notExists=true
nofollow exists=true
nofollow notExists=false
```

Nếu môi trường không cho phép tạo symlink, chương trình in `Symlink unavailable` rồi thoát sau khi chạy `finally`. Khi filesystem không xác định được target, cặp kiểm tra follow có thể đều `false`; do đó **output trên là kỳ vọng có điều kiện**, không phải cam kết xuyên mọi provider.

Mã dùng target tương đối `missing-target.txt` để tạo dangling symlink; nó không cần tạo file đích thật. Khi xóa `link`, `Files.deleteIfExists(link)` xóa **entry link** chứ không yêu cầu target phải tồn tại. Nếu quyền xóa bị hạn chế hoặc directory bị can thiệp đồng thời, cleanup có thể ném `IOException` — ví dụ không cố che giấu lỗi này.

## 8. Không xác định trạng thái: cách biểu diễn rõ trong chương trình

Do hai phương thức trả boolean, một ứng dụng có thể muốn gói trạng thái thành enum. Ví dụ:

```java
enum Existence {
    PRESENT, ABSENT, UNKNOWN
}
```

Mã enum trên là **đoạn định nghĩa minh họa** cho một lớp hoặc file Java; enum chỉ mô tả trạng thái quan sát, không làm filesystem trở nên nguyên tử.

### Ví dụ Java 17: phân loại ba trạng thái

Lưu **`ExistenceStateDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class ExistenceStateDemo {
    enum State {
        PRESENT, ABSENT, UNKNOWN
    }

    static State probe(Path path, LinkOption... options) {
        if (Files.exists(path, options)) {
            return State.PRESENT;
        }
        if (Files.notExists(path, options)) {
            return State.ABSENT;
        }
        return State.UNKNOWN;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("state-demo-", ".dat");
        try {
            System.out.println("present: " + probe(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println("absent: " + probe(file));
    }
}
```

Chạy:

```bash
javac ExistenceStateDemo.java
java ExistenceStateDemo
```

Stdout trong điều kiện filesystem tạo/xóa và truy vấn bình thường:

```text
present: PRESENT
absent: ABSENT
```

**Không cố mô phỏng UNKNOWN bằng cách thay đổi quyền với một thư mục tạm** rồi khẳng định kết quả cụ thể. Trên Windows, Unix, container hoặc khi chương trình chạy với quyền đặc biệt, thao tác permission có thể tạo trạng thái khác nhau; thậm chí vẫn xác minh được sự tồn tại dù không được phép đọc nội dung. Để kiểm thử nhánh UNKNOWN một cách deterministic, nên **tách logic phân loại ra khỏi API filesystem** và cung cấp kết quả probe qua một abstraction có thể giả lập.

Ví dụ hướng kiểm thử:

```text
probe.exists = true,  probe.notExists = false  → PRESENT
probe.exists = false, probe.notExists = true   → ABSENT
probe.exists = false, probe.notExists = false  → UNKNOWN
```

Đó là fixture trạng thái logic, **không phải** kết luận hệ điều hành đã tạo ra ba trạng thái đó trong một lần chạy.

### Hạn chế: hai lần tra cứu không phải snapshot atomic

Trong `probe`, `exists` và `notExists` là hai lượt truy vấn. Nếu entry bị tạo/xóa giữa các lượt, kết quả enum chỉ phản ánh logic trên hai lần quan sát, **không phải trạng thái chắc chắn tại một thời điểm duy nhất**. Hàm hữu ích cho báo cáo UI/diagnostics, nhưng không phải giao thức đồng bộ an toàn để quyết định có tạo/xóa file trong điều kiện tranh chấp.

## 9. `Files.exists` không đồng nghĩa file có thể đọc hoặc ghi

Đường dẫn có thể tồn tại nhưng:

- Đó là **directory**, symbolic link, FIFO, device node hoặc loại entry khác.
- File bị từ chối quyền đọc/ghi.
- File hiện có, nhưng ngay sau đó bị process khác xóa, thay nội dung hoặc đổi tên.
- Filesystem/provider gặp lỗi I/O khi mở.
- File là symlink trỏ tới đường dẫn bị thay đổi hoặc nằm ngoài root an toàn.
- Một kho lưu trữ từ xa có thể mất kết nối sau khi trả metadata.

Vì vậy:

```java
if (Files.exists(path)) {
    try (var input = Files.newInputStream(path)) {
        // ...
    }
}
```

Đây là **đoạn minh họa**, với `path` là `Path` và xử lý `IOException`. Kiểm tra tồn tại ban đầu không bảo đảm `newInputStream` thành công. Trong mã thực tế, nếu mục tiêu là đọc file, thường **thử mở file trực tiếp** và xử lý ngoại lệ sẽ đáng tin hơn so với kiểm tra trước bằng `exists`.

| Câu hỏi | API/chiến lược tương ứng |
|---|---|
| Có xác nhận entry đang tồn tại không? | `Files.exists(path, options)` |
| Có xác nhận entry không tồn tại không? | `Files.notExists(path, options)` |
| Có thể đọc từ đường dẫn này ngay bây giờ không? | Thử `Files.newInputStream`, đọc và xử lý lỗi |
| Có thể ghi file mới mà không ghi đè file cũ? | `Files.createFile` hoặc mở với `CREATE_NEW` |
| Entry có phải file thông thường? | `Files.isRegularFile` hoặc `BasicFileAttributes.isRegularFile()` |
| Có thể đọc metadata hoặc biết lý do thất bại? | `Files.readAttributes` với `try/catch` |
| File có dữ liệu chính xác/có đúng định dạng không? | Mở, đọc, parse và validate nội dung |
| File có bền vững sau mất điện không? | Đòi hỏi thiết kế sync/commit riêng, không suy từ `exists` |

Các hàm như `Files.isRegularFile`, `Files.isDirectory`, `Files.isReadable`, `Files.isWritable` cũng có thể trả `false` khi không xác minh được điều kiện. Không tự động diễn giải `false` của mọi predicate thành bằng chứng chắc chắn về nguyên nhân.

## 10. Khi cần chẩn đoán lý do: `Files.readAttributes` và ngoại lệ

`exists`/`notExists` giúp biểu đạt câu hỏi đơn giản bằng boolean nhưng **cố ý không truyền mọi lỗi I/O theo kiểu checked exception**. Nếu cần phân biệt đường dẫn không tồn tại với lỗi truy cập, nên cân nhắc API thực hiện thao tác cần thiết và cho phép bắt ngoại lệ.

Ví dụ:

```java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class,
    LinkOption.NOFOLLOW_LINKS
);
```

Đây là **đoạn minh họa**, cần import `java.nio.file.Files`, `java.nio.file.LinkOption`, `java.nio.file.attribute.BasicFileAttributes`, và xử lý `IOException`. Khi thành công, bạn nhận được thông tin `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `size()`, v.v. Khi thất bại, API có thể ném `NoSuchFileException`, `AccessDeniedException` hoặc các kiểu `IOException` khác tùy provider.

### Ví dụ Java 17: đọc metadata với cách báo lỗi có ngữ cảnh

Lưu **`ReadAttributesStatusDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class ReadAttributesStatusDemo {
    static String describe(Path path) {
        try {
            BasicFileAttributes attrs = Files.readAttributes(
                path,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS
            );
            if (attrs.isRegularFile()) {
                return "regular file";
            }
            if (attrs.isDirectory()) {
                return "directory";
            }
            if (attrs.isSymbolicLink()) {
                return "symbolic link";
            }
            return "other entry";
        } catch (NoSuchFileException ex) {
            return "missing";
        } catch (AccessDeniedException ex) {
            return "access denied";
        } catch (IOException ex) {
            return "I/O unknown";
        } catch (SecurityException ex) {
            return "security denied";
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("attr-demo-", ".txt");
        try {
            System.out.println("created: " + describe(file));
        } finally {
            Files.deleteIfExists(file);
        }
        System.out.println("removed: " + describe(file));
    }
}
```

Biên dịch/chạy:

```bash
javac ReadAttributesStatusDemo.java
java ReadAttributesStatusDemo
```

Stdout trên filesystem hỗ trợ basic attributes và hoạt động bình thường:

```text
created: regular file
removed: missing
```

Điểm cần chú ý:

- `NoSuchFileException` cung cấp ngữ cảnh khác `AccessDeniedException`; `Files.exists` không tự trả cho caller một object exception tương ứng.
- `NOFOLLOW_LINKS` khiến `readAttributes` mô tả **entry link** nếu target là symbolic link.
- Một lỗi provider có thể là `FileSystemException` hoặc subtype `IOException` khác, không phải lúc nào cũng thuộc hai nhánh đầu.
- Với trường hợp sử dụng thật, đừng “thử kiểm tra tồn tại rồi đọc attributes” nếu một lần `readAttributes` đã đáp ứng mục tiêu; thêm lần truy vấn có thể tạo race không cần thiết.
- Ngay cả metadata vừa đọc vẫn có thể bị lỗi thời trước thao tác tiếp theo.

## 11. TOCTOU: kiểm tra rồi thao tác không phải nguyên tử

Một lỗi thiết kế phổ biến:

```java
if (Files.notExists(path)) {
    Files.writeString(path, "new content");
}
```

Đây là **phản ví dụ**. Kể cả khi `notExists` trả `true`, một process khác có thể tạo file tại `path` **sau lần kiểm tra và trước khi ghi**. `Files.writeString` mặc định có thể tạo hoặc truncate file theo cách mở tương ứng, gây ghi đè ngoài ý muốn. **Không** dùng kiểm tra tồn tại trước làm thay thế cho thao tác tạo file nguyên tử.

Lược đồ:

```text
Tiến trình A                        Tiến trình B
------------                       -------------
Files.notExists(p) → true
                                   Tạo p
Files.writeString(p, ...)
→ có thể tác động vào p             (race!)
```

Kỹ thuật đúng khi yêu cầu “tạo file nếu chưa có và không ghi đè”:

```java
try {
    Files.createFile(path);
    // Tạo thành công.
} catch (FileAlreadyExistsException ex) {
    // Tên đã có, xử lý chính sách không ghi đè.
}
```

Đây là **đoạn minh họa**, với `path` là `Path`; cần import `Files`, `FileAlreadyExistsException`, và xử lý các `IOException` khác. Theo hợp đồng `Files.createFile`, **kiểm tra sự tồn tại và tạo file là một thao tác nguyên tử** đối với các hoạt động filesystem khác ảnh hưởng tới directory, tùy khả năng hỗ trợ của provider. Nếu không tạo được vì quyền/trục trặc khác, API ném ngoại lệ khác — không được chuyển mọi lỗi thành “file đã tồn tại”.

Một lựa chọn khác khi muốn **tạo rồi ghi**, đồng thời từ chối ghi đè file có sẵn:

```java
try (var out = Files.newOutputStream(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(payload);
}
```

Đây là **đoạn minh họa**, `payload` là `byte[]`, cần import `Files`, `StandardOpenOption` và xử lý `IOException`. `CREATE_NEW` dành cho mục tiêu “file chưa tồn tại mới tạo”; nếu đã có entry, thao tác mở/tạo thất bại thay vì âm thầm truncate file cũ. Quy tắc riêng của provider và xử lý symlink vẫn phải tuân theo hợp đồng của phương thức thực tế.

### Xóa file có cần `exists` trước không?

Không cần:

```java
Files.deleteIfExists(path);
```

Đây là **đoạn minh họa**, `path` là `Path` và xử lý `IOException`. `deleteIfExists` thực hiện mục tiêu “xóa nếu có” trong **một API**, thay vì tự làm:

```java
if (Files.exists(path)) {
    Files.delete(path);
}
```

Đây là **phản ví dụ không cần thiết** vì có race và thừa lần kiểm tra. Lưu ý `deleteIfExists` có thể vẫn ném `IOException` nếu việc xóa gặp lỗi; `false` thường biểu thị không có gì được xóa, không phải chứng nhận vĩnh viễn rằng tên luôn vắng mặt. API cũng không tự giải quyết mọi rủi ro symlink/permission trong môi trường không tin cậy.

## 12. `exists`, `notExists` và `Files.isRegularFile`

Một đường dẫn có thể tồn tại nhưng không phải **file thông thường**:

```text
project/
├── config.json   (file)
├── cache/        (directory)
└── latest -> config.json (symlink)
```

Khi cần phân biệt loại:

```java
if (Files.isRegularFile(path)) {
    System.out.println("regular file");
} else if (Files.isDirectory(path)) {
    System.out.println("directory");
} else if (Files.isSymbolicLink(path)) {
    System.out.println("symbolic link");
} else {
    System.out.println("other or cannot determine");
}
```

Đây là **đoạn minh họa**, `path` là `Path`, đã import `Files`.

Lưu ý:

- `isRegularFile` và `isDirectory` mặc định **theo symbolic link**, nên nếu link trỏ đến file thường thì `isRegularFile(link)` có thể là `true`.
- `isSymbolicLink` kiểm tra entry link theo nghĩa của API, không phải “nó trỏ đến file gì”.
- Nếu các predicate đều `false`, không được mặc định path chắc chắn là loại entry “other”; đó cũng có thể là trường hợp **không xác minh được**.
- Muốn một bộ thuộc tính liên quan được đọc một lần, dùng `Files.readAttributes(..., BasicFileAttributes.class, options)` khi phù hợp.
- Không giả định `exists == true` kéo theo `isReadable == true`, hoặc `isRegularFile == true` là cam kết file vẫn tồn tại đến lần mở sau.

## 13. Trường hợp đường dẫn tương đối và quyền truy cập

`Path.of("report.txt")` là một đường dẫn tương đối; nó được diễn giải theo filesystem và **working directory** của tiến trình khi giải quyết một thao tác. Nếu chạy trong IDE, terminal, service hoặc container với working directory khác nhau, cùng chuỗi đường dẫn có thể trỏ đến mục khác.

```java
Path relative = Path.of("report.txt");
System.out.println(relative.toAbsolutePath());
```

Đây là **đoạn minh họa**, kết quả tuyệt đối phụ thuộc môi trường.

Một kết quả `Files.notExists(relative)` chỉ có ý nghĩa với **vị trí mà runtime hiện diễn giải**, không phải bằng chứng mọi file tên `report.txt` đều không tồn tại trên máy.

Đối với ứng dụng nghiêm túc:

1. Xác định root working directory hoặc cấu hình path rõ ràng.
2. Dùng `Path.resolve` để ghép đúng parent/child.
3. Kiểm soát `normalize()`/canonicalization và symlink theo threat model.
4. Không dùng `Files.exists` để quyết định quyền truy cập thực tế mà không xử lý lỗi khi mở.
5. Nếu filename đến từ người dùng, chống path traversal bằng cơ chế truy cập filesystem phù hợp, không chỉ kiểm tra có tồn tại.

### `SecurityException` và lỗi I/O khác nhau

Theo môi trường và provider, lời gọi `Files.exists`/`notExists` có thể chịu kiểm tra quyền bảo mật và **ném `SecurityException`** thay vì chỉ trả `false`. Không nên xem việc không xuất hiện checked `IOException` trên chữ ký là bảo đảm “không có lỗi”.

Nếu nghiệp vụ yêu cầu log nguyên nhân chính xác, gọi một API có exception thích hợp (ví dụ `readAttributes` hoặc thao tác mở) và phân loại lỗi theo semantics của filesystem thay vì lặp lại `Files.exists` cho đến khi có true.

## 14. Lỗi phổ biến và cách sửa

| Cách làm sai | Vấn đề | Cách làm đúng hơn |
|---|---|---|
| `!Files.exists(p)` nghĩa là file không tồn tại chắc chắn | UNKNOWN cũng tạo `false` từ `exists` | `Files.notExists(p)` khi cần chứng nhận vắng mặt |
| `Files.exists(p) || Files.notExists(p)` luôn true | Cả hai có thể false | Xử lý nhánh UNKNOWN |
| Gặp UNKNOWN thì tạo file như chắc chắn trống | Có thể đã tồn tại nhưng thiếu quyền xác minh | Dùng `CREATE_NEW` hoặc thao tác nguyên tử đúng yêu cầu |
| Kiểm tra `notExists` rồi ghi bằng open mặc định | Có race và nguy cơ truncate file vừa được tạo | Tạo bằng `Files.createFile` hoặc `CREATE_NEW` |
| Kiểm tra `exists` rồi mới xóa | Thêm TOCTOU và thao tác thừa | Dùng `deleteIfExists` theo chính sách |
| Chỉ kiểm tra tồn tại rồi đọc mà không catch lỗi | File có thể thay đổi/không có quyền đọc | Thử mở/đọc trực tiếp và xử lý `IOException` |
| `exists == true` ⇒ file thông thường | Directory/link cũng tồn tại | Dùng `isRegularFile` hoặc attributes |
| `exists == false` ⇒ `notExists == true` | Không đúng khi chưa xác minh được | Giữ ba trạng thái riêng |
| Dùng `NOFOLLOW_LINKS` nhưng nghĩ đang kiểm tra target | Nó kiểm tra chính entry link | Chọn link policy rõ ràng |
| Chỉ dùng follow links cho dangling symlink và kết luận entry mất | Target mất nhưng link vẫn tồn tại | Dùng `NOFOLLOW_LINKS` khi hỏi về entry |
| Nhầm mọi lỗi truy vấn với `NoSuchFileException` | Lỗi quyền/I/O và provider khác nhau | Bắt subtype `IOException` phù hợp |
| Test UNKNOWN bằng chmod rồi yêu cầu output cố định | Hành vi quyền khác nhau theo OS/user | Fake abstraction hoặc integration test có điều kiện |
| Quên trạng thái thay đổi giữa hai lời gọi | Snapshot không nguyên tử | Tránh kiểm tra trước khi thao tác khi có thể |
| Đưa đường dẫn tương đối vào service mà không kiểm tra root | Working directory thay đổi | Quy định root/path được cấu hình |
| Dùng kết quả exists như kiểm tra bảo mật | Không giải quyết traversal/symlink/TOCTOU | Dùng cơ chế OS và API mở phù hợp |
| Tin `Files.exists` kiểm tra checksum/nội dung | Chỉ liên quan xác minh sự tồn tại | Mở, đọc và validate nội dung thật |

## 15. Quy trình quyết định theo bài toán

### A. Chỉ cần thông báo trạng thái trong UI

Có thể dùng:

```java
if (Files.exists(p)) {
    status = "Present";
} else if (Files.notExists(p)) {
    status = "Absent";
} else {
    status = "Unknown";
}
```

Đây là **đoạn minh họa**, `p` là `Path`, `status` là biến kiểu `String`. UI cần giữ khả năng hiển thị **Unknown**. Không gắn nhãn đỏ “missing” cho mọi `false`.

### B. Cần tạo file mới nếu chưa có, tuyệt đối không ghi đè

Ưu tiên thao tác `Files.createFile(p)` hoặc mở với `StandardOpenOption.CREATE_NEW`. Bắt `FileAlreadyExistsException` tách biệt các lỗi khác. **Không** đặt `notExists` làm điều kiện duy nhất.

### C. Cần đọc file nếu có, còn thiếu thì bỏ qua

Thử mở và đọc trực tiếp:

```java
try (var in = Files.newInputStream(p)) {
    // Đọc dữ liệu.
} catch (NoSuchFileException ex) {
    // Theo chính sách ứng dụng, bỏ qua nếu file không tồn tại.
} catch (IOException ex) {
    // Lỗi quyền, filesystem, I/O khác: báo hoặc xử lý phù hợp.
}
```

Đây là **đoạn minh họa**, cần import `Files`, `NoSuchFileException`, `IOException`. Tùy provider, không phải mọi trường hợp mất file đều dùng chính xác subtype này; hãy tham chiếu hợp đồng I/O đang dùng. Không nuốt toàn bộ `IOException` để biến thành “file missing”.

### D. Cần phân tích symlink hoặc kiểm tra entry để dọn

Dùng `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` và/hoặc `Files.readAttributes(..., NOFOLLOW_LINKS)` nếu cần metadata. Nhưng khi thao tác entry thật, vẫn xử lý race/permission và lỗi của `delete`/`move`.

### E. Cần kiểm kê nhiều file trên storage từ xa

Một lần `exists` cho mỗi file có thể tốn round-trip và gây inconsistent snapshot. Cân nhắc API liệt kê/batch chuyên dụng của provider, thiết kế retry/backoff và biểu diễn trạng thái **unknown** rõ ràng khi không truy cập được. Không xem “không phản hồi” là “không tồn tại”.

## 16. Bài tập tự kiểm tra

**Câu 1.** Nếu `Files.exists(p) == false`, file có chắc chắn không tồn tại không?

**Đáp án:** Không. Kết quả có thể là ABSENT hoặc UNKNOWN. Phải hiểu `Files.notExists(p)` là kiểm tra xác nhận không tồn tại.

**Câu 2.** Khi nào cả `Files.exists(p)` và `Files.notExists(p)` cùng trả `false`?

**Đáp án:** Khi provider không xác minh được trạng thái; ví dụ một số lỗi quyền, metadata hoặc filesystem. Đây là UNKNOWN, không phải mâu thuẫn logic của API.

**Câu 3.** `Files.notExists(p)` có luôn bằng `!Files.exists(p)` không?

**Đáp án:** Không. Trong trạng thái UNKNOWN, `notExists` là `false` còn `!exists` là `true`.

**Câu 4.** Vì sao không nên viết `if (Files.notExists(p)) Files.writeString(p, data)` để bảo đảm không ghi đè?

**Đáp án:** Có TOCTOU: file có thể được tạo giữa hai lệnh. Dùng `CREATE_NEW` hoặc `Files.createFile` để yêu cầu tạo mới không ghi đè.

**Câu 5.** Có symbolic link vẫn còn trên đĩa nhưng target bị xóa. Mặc định `exists(link)` hỏi điều gì?

**Đáp án:** Mặc định theo link, nên hỏi target được phân giải; có thể là false khi target mất. Nếu muốn hỏi chính entry symbolic link, dùng `NOFOLLOW_LINKS`.

**Câu 6.** `Files.exists(path) == true` có bảo đảm mở được file để đọc?

**Đáp án:** Không. Path có thể là directory, thiếu quyền đọc, hoặc bị thay đổi sau kiểm tra. Mở/đọc và xử lý lỗi trực tiếp.

**Câu 7.** Nếu ứng dụng cần phân biệt không tồn tại với access denied, nên chọn gì?

**Đáp án:** API truy vấn metadata hoặc thao tác thực với `IOException`/subtype (ví dụ `Files.readAttributes`), thay vì chỉ dựa trên boolean `exists`.

**Câu 8.** `Files.deleteIfExists(p)` giải quyết điều gì?

**Đáp án:** Gộp mục tiêu xóa nếu có vào một thao tác, tránh vòng check-then-delete không cần thiết. Nó vẫn có thể ném lỗi; không tạo bảo đảm vĩnh viễn về trạng thái.

**Câu 9.** Tại sao các kết quả `exists` và `notExists` đọc liên tiếp không phải ảnh chụp nguyên tử?

**Đáp án:** Filesystem có thể thay đổi giữa hai lời gọi; các kết quả được quan sát tại những thời điểm khác nhau.

**Câu 10.** `NOFOLLOW_LINKS` có tự bảo đảm chống path traversal và symlink race không?

**Đáp án:** Không. Nó chỉ thay cách kiểm tra đối tượng; an toàn cần thiết kế root, quyền và API thao tác trực tiếp phù hợp.

## Tổng kết

- `Files.exists(p)` **xác nhận sự tồn tại** nếu có thể.
- `Files.notExists(p)` **xác nhận sự không tồn tại** nếu có thể.
- Nếu **cả hai false**, trạng thái là **UNKNOWN**, không được ép thành ABSENT.
- Hai phép kiểm tra **không nguyên tử**, không thay thế thao tác mở/tạo/xóa thực tế và không tự bảo đảm quyền, nội dung hoặc độ bền dữ liệu.
- Với symlink, phân biệt **theo link** và **`NOFOLLOW_LINKS`**; một dangling symlink có thể tồn tại dù target không tồn tại.
- Nếu cần lỗi có ngữ cảnh, chọn API trả `IOException` và xử lý đúng subtype; nếu cần tạo file không ghi đè, dùng `CREATE_NEW` hoặc `Files.createFile`.
- Khi viết ứng dụng Java 17, hãy biểu diễn **PRESENT / ABSENT / UNKNOWN** minh bạch và luôn kiểm soát TOCTOU, ownership, filesystem provider cùng chính sách bảo mật.
