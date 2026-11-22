# EventStream: yêu cầu tệp và thư mục tồn tại, đúng loại và có quyền truy cập (Java 14+)

## 1. Vì sao phải kiểm tra nguồn trước khi mở `EventStream`?

Trong Java Flight Recorder (JFR), `jdk.jfr.consumer.EventStream` cung cấp các phương thức đọc sự kiện từ **tệp recording** hoặc **kho dữ liệu recording (disk repository)**. Khi đưa `Path` vào API, một chuỗi đường dẫn hợp lệ về cú pháp **không có nghĩa** đối tượng trên hệ thống tệp đã tồn tại hoặc tiến trình Java có quyền đọc nó.

Hai nguồn quan trọng:

```java
EventStream.openFile(Path file);
EventStream.openRepository(Path directory);
```

Các dòng trên là **chữ ký API giản lược**, không phải mã độc lập; cần import `jdk.jfr.consumer.EventStream` và `java.nio.file.Path`. Phương thức thứ nhất cần một **tệp JFR recording** có thể mở để đọc. Phương thức thứ hai cần **thư mục disk repository của JFR** có thể truy cập; một thư mục ngẫu nhiên tồn tại chưa chắc là repository hợp lệ.

Ví dụ vấn đề thực tế:

- Đường dẫn `recordings/trace.jfr` chưa được tạo, hoặc tệp đã bị chuyển/xóa.
- Đường dẫn trỏ **tới thư mục**, nhưng ứng dụng gọi `openFile`.
- Đường dẫn trỏ **tới tệp**, nhưng ứng dụng gọi `openRepository`.
- Tiến trình đang chạy dưới tài khoản dịch vụ không có quyền đọc thư mục hoặc tệp.
- Thư mục tồn tại nhưng không phải **kho JFR thực**, hoặc một tệp tên `.jfr` chưa chứa dữ liệu JFR hợp lệ.
- Tệp hoặc quyền truy cập đã thay đổi trong khoảng thời gian giữa lần kiểm tra và khi mở.

**Mục tiêu bài học** là hiểu điều kiện tồn tại, loại đối tượng, quyền đọc, cách phản hồi lỗi `IOException` và sự khác biệt giữa **kiểm tra sơ bộ** với **mở thành công trong thực tế**. Các bài kiểm tra đường dẫn nên giúp chẩn đoán rõ hơn, không tạo ảo giác rằng hệ thống tệp đứng yên.

### Phiên bản hiện hành

`EventStream` có từ **Java 14** (JEP 349: *JFR Event Streaming*), và các overload `openFile(Path)` / `openRepository(Path)` vẫn là API được hỗ trợ trong Java hiện đại. Ví dụ bài này biên dịch bằng **`javac --release 17`**, không dùng tính năng preview hoặc API lỗi thời. JFR thuộc module **`jdk.jfr`**, nên runtime/build cần cung cấp module này.

## 2. Ba cách lấy nguồn sự kiện – đừng nhầm tệp, thư mục và JVM hiện tại

| API | Nguồn cần đọc | Hành vi khởi đầu mặc định |
| --- | --- | --- |
| `EventStream.openFile(Path file)` | **Một tệp** recording JFR đã ghi, thường đuôi `.jfr` | Đọc từ sự kiện đầu tiên của tệp |
| `EventStream.openRepository(Path directory)` | **Một thư mục** repository JFR trên đĩa | Mặc định bắt đầu với sự kiện tiếp theo được JFR flush |
| `EventStream.openRepository()` | Repository của **JVM hiện tại** | Mặc định bắt đầu với sự kiện JFR được flush tiếp theo |

**Khác biệt quan trọng:** `openFile` đọc tệp ghi hoàn chỉnh hoặc nguồn file phù hợp; `openRepository(directory)` đọc các đoạn dữ liệu sự kiện trong repository. Repository **không phải một tệp `.jfr` bất kỳ được lưu trong một folder**.

Nếu cần tự mở luồng có recording ngay từ JVM của ứng dụng, còn có `jdk.jfr.consumer.RecordingStream`. API này quản lý recording của JVM hiện tại, khác với nhiệm vụ “mở một đường dẫn đã được cung cấp”.

### Những giả định không hợp lệ

- **Có phần mở rộng `.jfr`** không chứng minh đó là recording JFR đọc được.
- **`Files.isDirectory(path)` là `true`** không chứng minh đó là JFR disk repository.
- **`Files.exists(path)` là `true`** không chứng minh tiến trình có quyền đọc.
- **`Files.isReadable(path)` là `true`** không bảo đảm lần gọi `openFile`/`openRepository` kế tiếp chắc chắn thành công.
- **`openRepository()` không đối số** không phải đường tắt để đọc repository của một JVM khác qua mạng; theo API nó mở repository của JVM hiện tại.

## 3. Các phép kiểm tra với `java.nio.file.Files`

Khi cần nhận đường dẫn từ cấu hình hoặc CLI, thường kiểm tra **loại**, **sự tồn tại** và **quyền đọc** trước khi mở.

| Kiểm tra | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `Files.exists(path)` | Kiểm tra đường dẫn có tồn tại ở thời điểm kiểm tra không | Kết quả không đóng băng filesystem và có thể không xác định do thiếu quyền |
| `Files.isRegularFile(path)` | Kiểm tra đối tượng là tệp thông thường | Không chứng minh nội dung là JFR hợp lệ |
| `Files.isDirectory(path)` | Kiểm tra đối tượng là thư mục | Không chứng minh thư mục là repository JFR |
| `Files.isReadable(path)` | Kiểm tra JVM hiện tại dường như có quyền đọc | Không bảo đảm thao tác mở sau đó sẽ thành công |
| `Files.isSymbolicLink(path)` | Nhận biết đường dẫn liên kết tượng trưng | Không tự giải quyết rủi ro race hoặc quyền của đích liên kết |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | Xác định tệp thường **không đi theo symlink** tại lần kiểm tra | Vẫn là kiểm tra tại một thời điểm, không phải khóa đối tượng |
| `Files.isDirectory(path, NOFOLLOW_LINKS)` | Tương tự, xác định thư mục thật thay vì symlink | Có thể không phù hợp nếu ứng dụng chủ đích cho phép symlink đáng tin |

**Chọn phép kiểm tra theo loại nguồn:**

```java
// Snippet minh họa trong phương thức có Path file.
if (!java.nio.file.Files.isRegularFile(file)) {
    throw new java.io.IOException("Không phải tệp thông thường");
}
if (!java.nio.file.Files.isReadable(file)) {
    throw new java.io.IOException("Không thể đọc tệp");
}
```

Đối với repository:

```java
// Snippet minh họa trong phương thức có Path directory.
if (!java.nio.file.Files.isDirectory(directory)) {
    throw new java.io.IOException("Không phải thư mục");
}
if (!java.nio.file.Files.isReadable(directory)) {
    throw new java.io.IOException("Không thể đọc thư mục");
}
```

Hai đoạn trên **không tự chạy độc lập**: biến `file` / `directory` phải có kiểu `Path`. Đó là **kiểm tra hỗ trợ thông báo lỗi**, không phải bảo đảm về quyền truy cập, tính hợp lệ của JFR repository hay việc không có sửa đổi xen giữa hai thao tác.

### Vì sao không chỉ viết `Files.exists`?

`Files.exists(file)` đúng không có nghĩa `file` là tệp thường. Một directory cũng “tồn tại” nhưng không phải file phù hợp cho `EventStream.openFile`. Vì vậy, `Files.isRegularFile` có giá trị kiểm tra mạnh hơn: kết hợp được thông tin **đúng loại đối tượng** và **tồn tại** theo nghĩa của phép kiểm tra. Tương tự, `Files.isDirectory` giúp chặn trường hợp lấy một file làm disk repository.

Điều này **không thay đổi** nghĩa vụ bắt `IOException` từ API đọc JFR. Một precheck có thể trả `false` nếu thuộc tính không xác định do I/O hoặc thiếu quyền, thay vì luôn ném exception chính xác; khi cần điều tra nguyên nhân cụ thể có thể dùng API đọc thuộc tính `Files.readAttributes`, kết hợp bắt lỗi, hoặc để thao tác mở thực tế trả về lỗi.

## 4. Ví dụ hoàn chỉnh Java 17+: tạo `.jfr` thật, kiểm tra nguồn và đọc bằng `EventStream`

Ví dụ này sử dụng **JFR thật**, không chỉ tạo một tệp giả tên `.jfr`. Chương trình ghi một sự kiện tùy chỉnh vào recording bằng `jdk.jfr.Recording`, dump ra tệp, kiểm tra đường dẫn, rồi mở bằng `EventStream.openFile`.

Nó cũng kiểm thử ba đầu vào sai thường gặp: file không tồn tại, directory bị đưa vào nơi cần file, và file bị đưa vào nơi cần directory. Không dùng thao tác cố tình thay quyền hệ thống, vì các hành vi phân quyền có thể khác nhau giữa Windows, Linux, container và tài khoản chạy tiến trình.

Tạo tệp **`JfrSourcePreflightDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

public class JfrSourcePreflightDemo {
    @Name("lesson.InputChecked")
    public static final class InputChecked extends Event {
        public String id;
    }

    static Path requireReadableJfrFile(Path file) throws IOException {
        if (file == null) {
            throw new IllegalArgumentException("file is null");
        }
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Not an existing regular file: " + file);
        }
        if (!Files.isReadable(file)) {
            throw new IOException("File is not readable: " + file);
        }
        return file;
    }

    static Path requireReadableRepository(Path directory) throws IOException {
        if (directory == null) {
            throw new IllegalArgumentException("directory is null");
        }
        if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException(
                    "Not an existing directory: " + directory);
        }
        if (!Files.isReadable(directory)) {
            throw new IOException(
                    "Directory is not readable: " + directory);
        }
        return directory;
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("jfr-source-demo-");
        Path recordingFile = directory.resolve("capture.jfr");

        try {
            String name = EventType
                    .getEventType(InputChecked.class).getName();

            // Tạo recording hợp lệ và ghi một custom event.
            try (Recording recording = new Recording()) {
                recording.enable(InputChecked.class).withoutThreshold();
                recording.start();

                InputChecked custom = new InputChecked();
                custom.id = "REQ-42";
                custom.commit();

                recording.stop();
                recording.dump(recordingFile);
            }

            // Kiểm tra đúng loại và quyền đọc trước khi mở.
            Path checkedFile = requireReadableJfrFile(recordingFile);
            Path checkedDir = requireReadableRepository(directory);

            System.out.println("fileValid="
                    + Files.isRegularFile(checkedFile));
            System.out.println("fileReadable="
                    + Files.isReadable(checkedFile));
            System.out.println("directoryValid="
                    + Files.isDirectory(checkedDir));
            System.out.println("directoryReadable="
                    + Files.isReadable(checkedDir));

            AtomicInteger observed = new AtomicInteger();

            try (EventStream stream = EventStream.openFile(checkedFile)) {
                stream.onEvent(name, event -> {
                    if ("REQ-42".equals(event.getString("id"))) {
                        observed.incrementAndGet();
                    }
                });
                stream.start();
            }

            if (observed.get() != 1) {
                throw new AssertionError(
                        "Expected exactly one matching event");
            }
            System.out.println("matchingEvents=" + observed.get());

            // Không có file.
            try {
                requireReadableJfrFile(
                        directory.resolve("missing.jfr"));
                throw new AssertionError(
                        "Missing file should be rejected");
            } catch (IOException expected) {
                System.out.println("missingFileRejected=true");
            }

            // Nhầm thư mục với tệp.
            try {
                requireReadableJfrFile(directory);
                throw new AssertionError(
                        "A directory should not be a file");
            } catch (IOException expected) {
                System.out.println("directoryAsFileRejected=true");
            }

            // Nhầm tệp với thư mục.
            try {
                requireReadableRepository(recordingFile);
                throw new AssertionError(
                        "A file should not be a directory");
            } catch (IOException expected) {
                System.out.println("fileAsDirectoryRejected=true");
            }
        } finally {
            Files.deleteIfExists(recordingFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

**Biên dịch và chạy** với JDK 17+ có hỗ trợ `jdk.jfr`:

```bash
javac --release 17 -encoding UTF-8 JfrSourcePreflightDemo.java
java JfrSourcePreflightDemo
```

**Kết quả chính xác trong môi trường kiểm thử đã chạy:**

```text
fileValid=true
fileReadable=true
directoryValid=true
directoryReadable=true
matchingEvents=1
missingFileRejected=true
directoryAsFileRejected=true
fileAsDirectoryRejected=true
```

### Vì sao bài thử không cần một tệp `.jfr` bên ngoài?

Chương trình tạo **một thư mục tạm** bằng `Files.createTempDirectory` và tự sinh tệp `capture.jfr` thông qua `Recording.dump`. `Recording` bật event `InputChecked`, gọi `commit()` một lần và dừng recording trước khi dump.

Sự kiện có tên `lesson.InputChecked` được lấy từ `EventType.getEventType(...).getName()`, giúp callback:

```java
stream.onEvent(name, event -> {
    if ("REQ-42".equals(event.getString("id"))) {
        observed.incrementAndGet();
    }
});
```

đọc đúng loại và ID. `stream.start()` xử lý stream file đồng bộ đến khi xử lý xong; sau đó kiểm tra `observed.get() == 1`. Chương trình sẽ **ném `AssertionError` nếu nhận được số sự kiện không như dự kiến**, chứ không in “PASS” vô điều kiện.

### Vì sao demo kiểm tra directory nhưng không gọi `openRepository(directory)`?

Thư mục tạm ở đây là **nơi lưu một tệp `.jfr`**, chứ **không được cấu hình thành JFR disk repository**. Phương thức `requireReadableRepository(directory)` chỉ kiểm tra rằng nó tồn tại, đúng loại và có thể đọc, **không chứng minh nó là repository**.

Gọi `EventStream.openRepository(directory)` rồi tuyên bố phải nhận được sự kiện trong `capture.jfr` sẽ nhầm lẫn giữa **một directory thông thường chứa file dump** với **JFR repository**. Nếu cần đọc file dump đó, `openFile(recordingFile)` mới là API tương ứng.

### Vì sao phải dùng `try-with-resources` và `finally`?

`Recording` và `EventStream` có vòng đời tài nguyên. `try-with-resources` bảo đảm chúng được đóng khi ra khỏi khối, kể cả có exception. `finally` dọn tệp và directory tạm theo đúng thứ tự **tệp trước, thư mục sau**.

Mã minh họa giả định tệp tạm không bị chương trình ngoài chiếm giữ. Với môi trường khác, I/O cleanup cũng có thể ném `IOException`; cần có chiến lược giữ log/cause và dọn dẹp phù hợp, đặc biệt nếu đang điều tra lỗi mở tệp gốc.

## 5. Cách dùng `EventStream.openFile(Path)` trong ứng dụng

Với đường dẫn được cung cấp từ tham số ứng dụng:

```java
// Snippet: sourceFile là Path đã được xác thực ở tầng cấu hình.
Path checked = requireReadableJfrFile(sourceFile);

try (EventStream stream = EventStream.openFile(checked)) {
    stream.onEvent(event -> {
        System.out.println(event.getEventType().getName());
    });
    stream.start();
}
```

Đoạn này là **snippet** trong một class có phương thức `requireReadableJfrFile` ở trên; cần import tương ứng và xử lý `IOException`. Nó sẽ in **tên các sự kiện có trong file**, không tạo sự kiện mới.

Đối với `openFile`:

- Đường dẫn là **`Path` trỏ tới tệp**; `Path.of("/var/logs/recording.jfr")` là cách tạo path trên hệ thống tương ứng.
- API có thể ném **`IOException`** nếu tệp không thể được mở hoặc gặp lỗi trong quá trình đọc.
- Tệp có thể tồn tại, có quyền đọc nhưng **dữ liệu không phải recording JFR hợp lệ**. Vì vậy, không chỉ dùng tên đuôi `.jfr` để xác nhận hợp lệ.
- Mặc định stream file bắt đầu từ **event đầu tiên** trong tệp.
- Nên **chỉ mở recording file đến từ nguồn tin cậy**, theo hướng dẫn API, nhất là khi ứng dụng xử lý dữ liệu từ người dùng hoặc một hệ thống khác.
- Nếu file có dung lượng lớn, điều chỉnh callback, bộ nhớ và tiến trình xử lý, tránh lưu toàn bộ `RecordedEvent` vào một danh sách không giới hạn khi chỉ cần thống kê.
- Nếu chỉ cần một số loại event, sử dụng `onEvent("event.name", action)` để lọc callback, thay vì phải tự lọc một tập rất lớn.

### Không tạo một tệp rỗng “để EventStream khỏi báo thiếu file”

Việc gọi:

```java
Files.createFile(path);
```

có thể tạo một **file rỗng**, nhưng **không tạo dữ liệu ghi JFR**. Tương tự, `Files.writeString(path, "hello")` tạo tệp văn bản, không phải recording. Các bước đó không phải cách sửa lỗi `openFile` thiếu tệp.

Nếu cần tạo recording, sử dụng `jdk.jfr.Recording` hoặc cơ chế JFR hợp lệ để **ghi và dump** dữ liệu; nếu cần đọc, phải cung cấp đường dẫn tới recording thực.

## 6. Cách dùng `EventStream.openRepository(Path)`: yêu cầu thư mục thật

`openRepository(Path directory)` dùng để mở **disk repository** có dữ liệu JFR. Ví dụ cấu trúc:

```java
// Snippet: repositoryDir là Path đến repository JFR tin cậy
// đang được JFR sử dụng / có nội dung repository hợp lệ.
Path checkedRepository = requireReadableRepository(repositoryDir);

try (EventStream stream =
             EventStream.openRepository(checkedRepository)) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.start();
}
```

Đây là **đoạn minh họa, không phải chương trình chạy độc lập**; cần một **JFR disk repository thật** đang cung cấp sự kiện, cùng đường dẫn được ứng dụng biết trước. `start()` có thể chờ trong thời gian dài để nhận sự kiện tiếp theo được flush, vì repository stream không đồng nghĩa với việc duyệt hết một file cố định. Với chương trình chạy lâu, cần chiến lược dừng bằng `close()` và quản lý thread phù hợp.

**Điều kiện tối thiểu ở mức filesystem:**

- `repositoryDir` là đường dẫn không `null`, trỏ đến **thư mục thực sự tồn tại**.
- Tiến trình có khả năng đọc/truy cập directory và **các file dữ liệu JFR** cần thiết bên trong.
- Đường dẫn là **repository tin cậy**, không phải thư mục được chọn tùy ý chỉ vì `Files.isDirectory` trả `true`.
- Nếu repository thuộc một tiến trình/JVM khác, cần bảo đảm mô hình vận hành thực sự hỗ trợ truy cập dữ liệu repository đó, quyền phù hợp và tính nhất quán; `EventStream` không tự vượt qua ranh giới quyền của hệ điều hành.
- Nếu repo chưa được JFR tạo hoặc đã bị xóa/di chuyển, kiểm tra và thao tác mở sẽ thất bại hoặc không thể cung cấp sự kiện mong đợi.

**Không tự động gọi `Files.createDirectories(repositoryDir)` để “sửa” mọi lỗi thiếu thư mục**. Một directory mới tạo chỉ là thư mục rỗng, không tự trở thành repository đang được JVM sử dụng. Chỉ tạo và cấu hình thư mục theo đúng vòng đời producer JFR khi ứng dụng thực sự chịu trách nhiệm thiết lập nơi ghi dữ liệu.

### Khi muốn đọc repository JVM hiện tại

```java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.GarbageCollection",
            event -> System.out.println(
                    event.getEventType().getName()));
    stream.start();
}
```

Không cần truyền `Path`, vì API truy cập repository của **JVM hiện tại**. Đường ghi phụ thuộc cấu hình JFR/runtime. Phần này **không loại bỏ** yêu cầu ứng dụng cần JFR hoạt động và có thể truy cập repository.

**Đừng dùng `openRepository()` làm cách “mở mọi tệp trong một thư mục tuỳ ý”**: đó là một trường hợp sử dụng khác.

## 7. Quyền truy cập: `Files.isReadable` không phải giấy bảo đảm

### 7.1. “Có quyền đọc” là quyền của tiến trình Java

Quyền truy cập phụ thuộc vào tài khoản và môi trường chạy **JVM**, không phải đơn thuần tài khoản người đang ngồi trước máy:

- Local developer có thể đọc file nhưng service chạy dưới tài khoản khác lại không.
- Trong container, mount có thể là read-only hoặc bị policy hạn chế.
- Trên Linux/Unix, directory thường cần quyền **traversal/search** để truy cập các mục con; quyền “read” của directory chưa chắc đã bao hàm mọi quyền cần thiết.
- Trên Windows, ACL có thể ảnh hưởng cả quyền đọc folder, file và đường dẫn cha; cách kiểm tra không hoàn toàn giống bit mode POSIX.
- Network file system có thể thay đổi kết nối, permission và trạng thái file giữa hai thao tác.

Vì vậy, **`Files.isReadable(path) == true` chỉ là một dự đoán tại thời điểm đó**. Nó có thể dựa trên ACL hoặc attribute, không phải một hành động mở file giữ quyền cố định.

### 7.2. Tình huống TOCTOU: kiểm tra xong nhưng khi mở thì khác

*Time-of-check to time-of-use* (TOCTOU) là khoảng thời gian giữa lần kiểm tra và lần sử dụng:

```java
if (Files.isReadable(path)) {
    // Trước khi tới dòng dưới, path có thể bị thay thế,
    // bị xóa, đổi permission hoặc thay nội dung.
    try (EventStream stream = EventStream.openFile(path)) {
        stream.onEvent(event -> { /* ... */ });
        stream.start();
    }
}
```

Đây là **snippet minh họa**. Có thể xảy ra:

1. `Files.isReadable(path)` trả `true`.
2. Một process khác di chuyển, xóa hoặc thay thế file.
3. `EventStream.openFile(path)` không thể mở được, hoặc truy cập **một file khác** tại đường dẫn đó.

Vì vậy, **luôn xử lý lỗi của thao tác thật**. Precheck có giá trị cải thiện thông báo (ví dụ “đang trỏ tới directory”), **không phải là khóa hay bảo chứng truy cập**.

### 7.3. `NOFOLLOW_LINKS` và symlink

Trong chương trình chính:

```java
Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)
```

Hai kiểm tra này **không đi theo symbolic link** tại thời điểm đánh giá. Trong ví dụ, chính sách là **từ chối symlink** để hạn chế nhầm lẫn đối tượng với đường dẫn được cấu hình. Nếu ứng dụng được thiết kế để cho phép symlink tin cậy, có thể chọn chính sách khác và xác minh đích/đường dẫn theo yêu cầu.

**Không suy diễn:** `NOFOLLOW_LINKS` trong một lệnh kiểm tra **không có nghĩa** `EventStream.openFile` sẽ mở một file “đã được khóa danh tính”. `openFile` chỉ nhận `Path`, và đường dẫn vẫn có thể đổi giữa các lời gọi. Khi dữ liệu đến từ nguồn không tin cậy hoặc có nguy cơ symlink race, giải pháp bảo vệ phải ở **kiến trúc quyền và luồng xử lý nguồn**, không phải chỉ thêm một flag vào precheck.

### 7.4. Vì sao không kiểm tra `Files.isWritable` để đọc EventStream?

Đối với **đọc tệp recording đã có**, ứng dụng thường cần **đọc**, không phải ghi vào tệp đó. Vì vậy, `Files.isWritable` không phải điều kiện bắt buộc của `EventStream.openFile`. Đòi writable cho mọi input có thể khiến một file JFR hợp lệ, chỉ đọc, bị từ chối vô lý.

Tuy nhiên, quyền truy cập repository của một JVM đang ghi dữ liệu có thể có yêu cầu vận hành riêng của producer và filesystem. Cần phân biệt **quyền của phía đọc stream** với **quyền tạo/ghi/chỉnh repository** của phía phát dữ liệu.

## 8. Xử lý lỗi: bắt `IOException` từ thao tác mở, không tự tạo thông điệp sai

`EventStream.openFile` và `EventStream.openRepository` đều khai báo có thể ném **`IOException`** nếu không thể mở hoặc đọc nguồn. Đừng biến mọi lỗi thành một câu chung “file không tồn tại”.

Ví dụ xử lý có ngữ cảnh:

```java
// Snippet đặt trong method throws IOException, với Path recordingPath.
try (EventStream stream = EventStream.openFile(recordingPath)) {
    stream.onEvent(event ->
            System.out.println(event.getEventType().getName()));
    stream.start();
} catch (IOException e) {
    // Logger cụ thể phụ thuộc ứng dụng; thông điệp bên ngoài
    // phải tránh lộ path nhạy cảm khi không được phép.
    throw new IOException(
            "Không thể mở hoặc đọc tệp JFR đã cấu hình", e);
}
```

Giữ `cause` bằng constructor `(message, e)` để tầng quan sát log có thể truy vết lỗi I/O gốc. Trong ứng dụng có logger, nên dùng overload nhận `Throwable` thay vì chỉ log `getMessage()`, và tránh log lặp lại cùng một lỗi ở nhiều tầng.

**Lưu ý phân loại:** Các exception cụ thể từ filesystem như `NoSuchFileException` và `AccessDeniedException` có thể xuất hiện khi hệ thống phân biệt được nguyên nhân, nhưng **không nên giả định luôn có đúng subclass đó** trên mọi provider, phiên bản và điểm phát sinh lỗi. Hợp đồng công khai của `EventStream` bảo đảm có thể có `IOException`.

| Trạng thái lỗi | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Đường dẫn không tồn tại | Cấu hình path, thư mục cha, mount | Sửa cấu hình hoặc quy trình sinh dữ liệu |
| `Path` là directory khi cần file | `Files.isRegularFile` | Chỉ tới recording JFR thực |
| `Path` là file khi cần repository | `Files.isDirectory` | Chỉ tới JFR disk repository thực |
| Không đủ quyền đọc/traversal | Tài khoản tiến trình, ACL/POSIX, container mount | Cấp quyền tối thiểu phù hợp; không dùng quyền admin mặc định |
| Tệp có đuôi `.jfr` nhưng nội dung sai | Nguồn tạo recording, trạng thái dump/ghi | Tạo/dump recording hợp lệ; không tự sửa byte dữ liệu |
| Repository directory tồn tại nhưng không phải JFR repo | Cách JVM/JFR cấu hình repository | Tìm đúng repository; không biến directory thường thành repo bằng cách tạo rỗng |
| Bị thay thế/xóa sau precheck | Race hoặc retention của hệ thống | Xử lý lỗi khi mở; cân nhắc kiểm soát vòng đời dữ liệu |
| Stream mở nhưng callback không được gọi | Event type, khoảng thời gian nguồn, callback, việc `start()` | Xác minh dữ liệu thực có event tương ứng |

### Trường hợp không thấy event không đồng nghĩa không đọc được

Một stream có thể **mở thành công**, nhưng callback lọc theo tên event không nhận gì. Nguyên nhân có thể đơn giản là trong file không chứa loại event đang tìm, hoặc một repository stream đang đợi sự kiện được flush. Hãy tách hai nhóm lỗi:

1. **Open/read failure:** lỗi filesystem/định dạng/IO – thường là exception.
2. **No matching event:** stream chạy nhưng không có dữ liệu phù hợp trong khoảng thời gian được quan sát.

Không chuyển nhóm thứ hai thành câu “không có quyền truy cập” khi chưa có bằng chứng.

## 9. Đường dẫn tương đối, đường dẫn tuyệt đối và nguồn tin cậy

Nếu người dùng truyền:

```java
Path path = Path.of("recordings", "capture.jfr");
```

đó là **đường dẫn tương đối** được giải thích theo thư mục làm việc của tiến trình Java. Thư mục làm việc khi chạy IDE, test runner, hệ thống CI/CD hoặc Windows service có thể khác nhau.

Có thể phục vụ chẩn đoán bằng:

```java
Path displayPath = path.toAbsolutePath().normalize();
System.out.println(displayPath);
```

Điều này giúp biết path tương đối được giải theo đâu. Nhưng `toAbsolutePath().normalize()` chủ yếu là chuẩn hóa **từ vựng path**; nó **không tự xác nhận file tồn tại hoặc an toàn**.

Với file tin cậy và khi cần phân giải đường dẫn thực, `toRealPath()` có thể đọc trạng thái hệ thống tệp và xử lý symbolic link theo tham số. Tuy nhiên, ngay cả việc kiểm tra đường dẫn thực cũng có **rủi ro thay đổi sau kiểm tra**. Không dùng nó như bảo chứng quyền truy cập vĩnh viễn.

### Chỉ mở dữ liệu JFR từ nguồn tin cậy

Javadoc của cả `openFile(Path)` lẫn `openRepository(Path)` khuyến cáo **chỉ mở recording/repository từ nguồn tin cậy**. Điều này đặc biệt quan trọng nếu ứng dụng cho phép upload file JFR hoặc chọn một thư mục trên disk.

Biện pháp thiết kế nên có:

- Dùng danh sách **đường dẫn/căn thư mục được phép** trong cấu hình, không tùy tiện ghép path người dùng thành đường dẫn bất kỳ.
- Không dùng quyền filesystem cao hơn cần thiết.
- Giới hạn dung lượng, vòng đời và nguồn cấp file trước khi thực hiện phân tích dữ liệu bên ngoài.
- Không cho một đường dẫn từ nguồn không tin cậy truy cập tới repository của process khác nếu không được phân quyền.
- Cân nhắc chạy xử lý file ngoài vùng sản xuất nhạy cảm, với quyền tối thiểu, khi nguồn dữ liệu chưa được kiểm chứng.
- Tránh in path nhạy cảm hoặc nội dung event chứa dữ liệu bảo mật vào log công khai.

**Precheck tồn tại/đọc được không đồng nghĩa source được tin cậy.** Đây là hai lớp yêu cầu khác nhau.

## 10. Tình huống thực hành và cách chọn thao tác

### A. Một tệp `.jfr` đã được dump hoàn tất

Bài toán: một process tạo `capture.jfr`, cần đọc tất cả event liên quan.

Cách làm: cấu hình `Path`, kiểm tra đây là file thường, khả năng đọc, rồi mở bằng **`EventStream.openFile(file)`**. Đăng ký callback và `start()`. Cần kiểm soát quá trình producer tạo/dump file hoàn chỉnh và có quyền đọc.

**Không chọn** `openRepository(file.getParent())` chỉ vì file nằm trong một thư mục.

### B. Muốn theo dõi repository JFR đang tạo thêm event

Bài toán: một JFR disk repository cụ thể có dữ liệu đang được ghi/flush.

Cách làm: lấy **đúng repository directory** từ hệ thống có quyền quản lý, kiểm tra đó là directory và có quyền truy cập các file bên trong, mở bằng **`EventStream.openRepository(directory)`**, rồi quản lý stream trong suốt thời gian cần theo dõi.

**Không tạo** một directory rỗng bất kỳ rồi mặc nhiên coi nó là repository hợp lệ.

### C. Muốn theo dõi chính JVM đang chạy chương trình

Bài toán: ứng dụng cần nhận các event từ JVM của mình.

Cách làm: cân nhắc **`EventStream.openRepository()`** (không nhận Path) hoặc **`RecordingStream`** nếu muốn đồng thời cấu hình recording ngay trong ứng dụng. Lúc này không cần user cung cấp đường dẫn disk repository.

### D. Tệp có thể bị xoay vòng/xóa theo chính sách retention

Bài toán: process khác dọn những file recording cũ định kỳ.

Cách làm: chấp nhận trường hợp `Files.isRegularFile` trả true ở bước trước nhưng `openFile` vẫn báo IOException. Phối hợp producer-consumer, chỉ mở file đã dump xong; không dùng kiểm tra một lần rồi cho rằng file luôn tồn tại.

### E. Container có quyền đọc khác máy phát triển

Bài toán: chạy local thành công nhưng deploy bị lỗi.

Cách làm: kiểm tra **đường dẫn trong container**, mount path, tài khoản chạy process, mode/ACL và quyền truy cập directory cha. Đừng chỉ so sánh `Path.of` trên máy developer với path trong container.

## 11. Checklist kiểm thử khả năng truy cập nguồn EventStream

| Ca kiểm thử | Thiết lập | Kết quả mong muốn |
| --- | --- | --- |
| File JFR hợp lệ | Tạo `Recording`, `commit()` event, `dump()` | `openFile` nhận event qua callback |
| File chưa tồn tại | Đường dẫn tới `missing.jfr` | Validation từ chối; thao tác thật cũng phải được xử lý khi IO thất bại |
| Directory thay cho file | Truyền directory vào `requireReadableJfrFile` | Báo sai loại thay vì giả định tồn tại là đủ |
| File thay cho directory | Truyền file vào `requireReadableRepository` | Báo sai loại |
| Directory có thể đọc nhưng không phải repository | Tạo directory thường | Precheck có thể pass; **không kết luận** đó là repository |
| File rỗng hoặc nội dung văn bản | Tạo file giả đuôi `.jfr` | Không coi suffix/tồn tại là bằng chứng JFR hợp lệ |
| Symlink | Path là symbolic link | Theo chính sách demo, `NOFOLLOW_LINKS` từ chối ở precheck |
| Không đủ permission | Chạy dưới tài khoản không có quyền thật | Phát hiện lỗi đọc/mở; không phụ thuộc chính xác lớp exception trên mọi OS |
| Thay path sau precheck | Di chuyển/xóa/đổi quyền file | Xử lý `IOException` tại thao tác thực, không dựa riêng vào boolean cũ |
| Không có event khớp | File hợp lệ, callback lọc tên không xuất hiện | Không tự kết luận IO/permission bị lỗi |
| Cleanup | Đóng stream rồi xóa file tạm | Không để lại file và tài nguyên khi test kết thúc |

### Lưu ý khi kiểm thử permission

Không nên viết bài test phổ thông bằng cách thử `chmod 000` trên một OS rồi khẳng định mọi Java runtime đều có kết quả tương tự. Tài khoản root, Windows ACL, mount, filesystem provider và container có thể khiến `Files.isReadable` không trả kết quả như suy đoán. Cách chắc chắn hơn là **test integration dưới tài khoản service thật** hoặc môi trường kiểm thử có quyền được điều khiển rõ ràng; kiểm tra kết quả I/O thực tế và thông báo lỗi phù hợp.

## 12. Các lỗi lập trình viên dễ mắc

1. **Chỉ gọi `Files.exists(path)`** rồi chuyển thẳng sang `openFile`, quên rằng path có thể là folder.
2. **Nhầm một directory chứa `.jfr` với JFR repository**, sau đó gọi `openRepository(directory)` và mong file dump được phát lại.
3. **Gọi `Files.createDirectories` mỗi khi báo thiếu repository**, tạo folder rỗng nhưng không có JFR producer nào ghi dữ liệu.
4. **Dùng phần mở rộng `.jfr` như bằng chứng hợp lệ**, trong khi tệp rỗng hoặc file văn bản vẫn có thể đặt tên như vậy.
5. **Cho `isReadable == true` nghĩa là không thể có IOException**, bỏ xử lý lỗi của `EventStream.openFile`.
6. **Đòi `isWritable == true` để mở file chỉ đọc**, khiến input hợp lệ bị từ chối vô ích.
7. **Không quan tâm tài khoản tiến trình**, vì nhầm quyền của người chạy IDE với quyền của service.
8. **Coi `NOFOLLOW_LINKS` tại precheck là bảo vệ tuyệt đối**, trong khi file vẫn có thể bị thay đổi trước lúc mở.
9. **Log mọi `IOException` như “file không tồn tại”**, che các lỗi access/format/mount hoặc race.
10. **Không đóng EventStream**, khiến luồng xử lý và tài nguyên bị kéo dài ngoài vòng đời job.
11. **Trông đợi sự kiện từ repository ngay lập tức**, trong khi API repository mặc định bắt đầu với flush kế tiếp và có thể phải chờ.
12. **Đọc file JFR từ nguồn không tin cậy không có chính sách**, bất chấp khuyến cáo trong Javadoc.

## 13. Câu hỏi tự kiểm tra

**1. Tại sao `Files.exists(path)` chưa đủ để gọi `EventStream.openFile(path)`?**

Vì một directory cũng tồn tại, và tệp có thể thiếu quyền đọc hoặc nội dung không phải JFR. Kiểm tra đúng loại bằng `Files.isRegularFile`, kiểm tra khả năng đọc rồi **vẫn xử lý IOException tại lúc mở**.

**2. `Files.isReadable(path)` trả `true` có bảo đảm `openFile(path)` chắc chắn thành công không?**

Không. Permission/path có thể thay đổi ngay sau lần kiểm tra (TOCTOU). Thậm chí file vẫn đọc được nhưng dữ liệu JFR không hợp lệ. Việc mở và đọc thật mới là bước quyết định.

**3. Thư mục `recordings/` chứa `capture.jfr` có tự trở thành JFR disk repository không?**

Không. Một folder chứa file dump `.jfr` khác với repository do JFR quản lý. Dùng `openFile(capture.jfr)` cho file dump; chỉ dùng `openRepository(directory)` với repository thực.

**4. Trong ví dụ, tại sao `requireReadableRepository(directory)` có thể pass nhưng chưa gọi `EventStream.openRepository(directory)`?**

Vì helper chỉ kiểm tra **loại directory và quyền đọc**, không xác nhận nội dung là JFR repository. Folder do `Files.createTempDirectory` tạo chỉ là folder thường.

**5. Tại sao không dùng `Files.isWritable` để từ chối tệp JFR chỉ-đọc?**

`EventStream.openFile` dùng nguồn để đọc. Quyền ghi không phải yêu cầu đương nhiên của việc đọc file đã có; đòi writable sẽ loại nhầm file hợp lệ.

**6. Tại sao `EventStream.openRepository()` không cần tham số `Path`?**

Nó mở repository của **JVM hiện tại**, không phải một đường dẫn file bất kỳ do user cung cấp.

**7. Nếu ứng dụng cần làm việc với đường dẫn được cấp từ người dùng, chỉ kiểm tra `NOFOLLOW_LINKS` đã đủ an toàn chưa?**

Chưa. Nó chỉ ảnh hưởng việc đi theo link trong lần kiểm tra cụ thể. Cần chính sách nguồn tin cậy, quyền tối thiểu, hạn chế path và xử lý race ở mức kiến trúc/hệ thống.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java 25 API — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile(Path)`, `openRepository(Path)`, `openRepository()`, checked `IOException` và khuyến cáo chỉ dùng nguồn tin cậy.
- [Oracle Java 25 API — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `exists`, `isRegularFile`, `isDirectory`, `isReadable` và giới hạn của các phép kiểm tra quyền.
- [Oracle Java 25 API — `java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` trong phép kiểm tra đường dẫn.
- [Oracle Java 25 API — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình và ghi JFR recording, `dump(Path)`.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): cơ sở của event streaming từ Java 14.

**Ghi nhớ:** Với `EventStream.openFile`, cần **một tệp recording JFR có thể mở**; với `EventStream.openRepository(Path)`, cần **thư mục disk repository JFR thực**. `Files.isRegularFile`, `Files.isDirectory` và `Files.isReadable` hỗ trợ kiểm tra đầu vào và báo lỗi rõ ràng, nhưng **không thay thế `IOException`, không chứng minh nguồn là JFR hợp lệ và không loại bỏ thay đổi quyền/đường dẫn sau kiểm tra**.
