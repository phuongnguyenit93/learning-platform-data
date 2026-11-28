# Theo dõi thay đổi thư mục bằng WatchService

Trong Java 27, **WatchService** thuộc API **java.nio.file** cho phép ứng dụng đăng ký theo dõi những thay đổi được hệ thống tệp thông báo đối với các mục trong một thư mục. Các tình huống thường gặp gồm phát hiện tệp mới xuất hiện, nhận biết tệp bị xóa, cập nhật chỉ mục, làm mới bộ nhớ đệm hoặc kích hoạt một bước xử lý khi dữ liệu đầu vào thay đổi.

Các thành phần quan trọng gồm:

- **WatchService:** dịch vụ nhận thông báo thay đổi từ hệ thống tệp.
- **WatchKey:** đối tượng đại diện cho một lần đăng ký theo dõi, đồng thời chứa các sự kiện đang chờ xử lý.
- **WatchEvent:** thông tin về một thay đổi, chẳng hạn tạo, xóa hoặc sửa một mục.
- **Path:** biểu diễn thư mục được đăng ký và đường dẫn của mục thay đổi.

Ví dụ ý tưởng:

~~~text
Thư mục data/
      |
      | đăng ký ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY
      v
  WatchService
      |
      | take() / poll()
      v
    WatchKey
      |
      | pollEvents()
      v
  WatchEvent<?> ------> xử lý thay đổi
      |
      | reset()
      v
    chờ tiếp
~~~

**WatchService là cơ chế nhận thông báo, không phải nhật ký đầy đủ, chính xác tuyệt đối của mọi thao tác tệp.** Sự kiện có thể bị gộp, đến trễ hoặc bị mất khi xảy ra tràn hàng đợi. Một thiết kế đáng tin cậy cần hiểu giới hạn của API và có cơ chế **quét lại trạng thái** khi cần.

Bài viết tập trung vào những khả năng hiện hành của Java 27 và những quy tắc sử dụng an toàn, không dựa vào hành vi lỗi thời hoặc các chi tiết riêng của một phiên bản JVM.

## 1. Khi nào nên dùng WatchService?

WatchService hữu ích khi ứng dụng cần **phản ứng với các thay đổi của hệ thống tệp** mà không phải liên tục quét toàn bộ thư mục theo một chu kỳ rất ngắn.

Ví dụ:

1. Một chương trình nhập dữ liệu nhận thông báo khi có tệp mới được chuyển vào thư mục.
2. Một công cụ phát triển theo dõi thay đổi tệp cấu hình hoặc mã nguồn và kích hoạt bước làm mới.
3. Một dịch vụ cập nhật chỉ mục khi có tệp được thêm hoặc xóa.
4. Một chương trình đồng bộ đánh dấu những đường dẫn cần kiểm tra lại.

Tuy nhiên, WatchService không phải công cụ phù hợp nếu ứng dụng đòi hỏi mọi thay đổi đều phải được ghi nhận **chính xác một lần**, đúng thứ tự toàn cục hoặc không được bỏ sót trong bất kỳ điều kiện tải nào. Những yêu cầu đó thường cần cơ chế có khả năng đối soát trạng thái, nhật ký sự kiện bền vững hoặc giao thức riêng của hệ thống dữ liệu.

### WatchService khác quét thư mục định kỳ

| Tiêu chí | WatchService | Quét thư mục định kỳ |
|---|---|---|
| Cách phát hiện | Nhận thông báo từ cơ chế theo dõi của file system provider | Đọc lại trạng thái các mục trong thư mục |
| Độ trễ | Phụ thuộc provider, hệ điều hành và tải | Phụ thuộc chu kỳ quét |
| Chi phí | Có thể tránh nhiều lần quét không cần thiết | Mỗi lần quét phải duyệt dữ liệu |
| Khả năng bỏ sót | Có thể có sự kiện bị gộp, mất hoặc OVERFLOW | Có thể bỏ qua những trạng thái trung gian giữa hai lần quét |
| Đối soát trạng thái cuối | Cần quét lại khi sự kiện không đầy đủ | Có ngay ảnh chụp trạng thái ở lần quét |
| Theo dõi cây thư mục | Cần đăng ký các thư mục con riêng | Có thể duyệt cây thư mục |

Nhiều hệ thống thực tế kết hợp **WatchService để nhận tín hiệu nhanh** và **quét lại để xác minh trạng thái thực**.

## 2. Các lớp và interface cơ bản

Các kiểu thường dùng nằm trong package **java.nio.file**.

| Thành phần | Vai trò |
|---|---|
| **WatchService** | Nhận các WatchKey có sự kiện cần xử lý; có thể đóng bằng **close()** |
| **WatchKey** | Đại diện cho đăng ký, cung cấp **pollEvents()**, **reset()**, **cancel()**, **isValid()** và **watchable()** |
| **WatchEvent<T>** | Mang **kind()**, **count()**, **context()** |
| **WatchEvent.Kind<T>** | Loại sự kiện |
| **StandardWatchEventKinds** | Định nghĩa **ENTRY_CREATE**, **ENTRY_DELETE**, **ENTRY_MODIFY**, **OVERFLOW** |
| **Path** | Thư mục được theo dõi và tên mục thay đổi |
| **FileSystem** | Cung cấp **newWatchService()** |
| **Files** | Kiểm tra, đọc và quét lại trạng thái hệ thống tệp |

Ba loại sự kiện chuẩn thường được đăng ký:

~~~java
import static java.nio.file.StandardWatchEventKinds.ENTRY_CREATE;
import static java.nio.file.StandardWatchEventKinds.ENTRY_DELETE;
import static java.nio.file.StandardWatchEventKinds.ENTRY_MODIFY;
~~~

Ý nghĩa khái quát:

- **ENTRY_CREATE:** một mục được tạo hoặc xuất hiện trong thư mục được theo dõi.
- **ENTRY_DELETE:** một mục bị xóa hoặc biến mất khỏi thư mục.
- **ENTRY_MODIFY:** một thay đổi được báo cáo đối với mục, tùy cách provider định nghĩa và phát hiện.
- **OVERFLOW:** tín hiệu cho biết có thể đã xảy ra mất hoặc bỏ sự kiện; cần xem lại trạng thái thay vì chỉ dựa vào các sự kiện đã nhận.

Loại sự kiện được hỗ trợ cụ thể, độ trễ và mức độ chi tiết có thể khác nhau theo file system provider.

## 3. Tạo WatchService và đăng ký một thư mục

Một **WatchService** được tạo từ **FileSystem** thích hợp:

~~~java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.WatchService;

try (WatchService watcher =
             FileSystems.getDefault().newWatchService()) {
    // Đăng ký thư mục và đọc sự kiện.
}
~~~

**WatchService** triển khai **Closeable**, nên try-with-resources giúp gọi **close()** khi rời phạm vi.

Nếu **Path** thuộc một file system không phải file system mặc định, nên dùng cùng provider với đường dẫn đó:

~~~java
WatchService watcher = directory.getFileSystem().newWatchService();
~~~

Tài nguyên này cũng phải được đóng sau khi sử dụng. Không nên tự động giả định mọi provider đều hỗ trợ theo dõi thay đổi với cùng các khả năng và hành vi.

### Đăng ký Path

~~~java
import java.nio.file.Path;
import java.nio.file.WatchKey;

import static java.nio.file.StandardWatchEventKinds.*;

Path directory = Path.of("data");

try (WatchService watcher =
             directory.getFileSystem().newWatchService()) {

    WatchKey key = directory.register(
            watcher,
            ENTRY_CREATE,
            ENTRY_DELETE,
            ENTRY_MODIFY
    );

    System.out.println(key.isValid());
}
~~~

Để đăng ký thành công, **directory** phải là một thư mục hợp lệ, provider hỗ trợ theo dõi và ứng dụng có các quyền cần thiết. Việc đăng ký có thể ném **IOException** hoặc những ngoại lệ liên quan tới provider, trạng thái đóng dịch vụ hay đối số không hợp lệ.

**Đăng ký thư mục không có nghĩa theo dõi cả mọi thư mục con.** Thông thường, các sự kiện chuẩn áp dụng cho những mục trực tiếp trong thư mục đã đăng ký. Cách theo dõi đệ quy được giải thích ở phần sau.

### Không đăng ký OVERFLOW như một nhu cầu theo dõi thông thường

Trong phần lớn ví dụ, ứng dụng đăng ký **ENTRY_CREATE**, **ENTRY_DELETE** và **ENTRY_MODIFY**. **OVERFLOW** là điều kiện đặc biệt mà WatchService có thể báo ngay cả khi nó không được đưa vào danh sách sự kiện đăng ký.

Do đó, chương trình xử lý sự kiện phải có nhánh **OVERFLOW**, nhưng không cần đăng ký **OVERFLOW** như một thao tác tạo/xóa/sửa tệp thông thường.

## 4. Ví dụ hoàn chỉnh: theo dõi một thư mục

Chương trình sau có thể biên dịch bằng cú pháp Java hiện hành. Nó theo dõi **một thư mục**, in đường dẫn bị ảnh hưởng cùng loại sự kiện và gọi **reset()** sau khi xử lý mỗi WatchKey.

Lưu thành **DirectoryWatcherDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

import static java.nio.file.StandardWatchEventKinds.ENTRY_CREATE;
import static java.nio.file.StandardWatchEventKinds.ENTRY_DELETE;
import static java.nio.file.StandardWatchEventKinds.ENTRY_MODIFY;
import static java.nio.file.StandardWatchEventKinds.OVERFLOW;

public final class DirectoryWatcherDemo {
    private DirectoryWatcherDemo() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java DirectoryWatcherDemo <directory>");
            return;
        }

        Path directory =
                Path.of(args[0]).toAbsolutePath().normalize();

        if (!Files.isDirectory(directory)) {
            System.err.println("Not a directory: " + directory);
            return;
        }

        try (WatchService watcher =
                     directory.getFileSystem().newWatchService()) {

            directory.register(
                    watcher,
                    ENTRY_CREATE,
                    ENTRY_DELETE,
                    ENTRY_MODIFY
            );

            System.out.println("Watching: " + directory);

            while (true) {
                WatchKey key;

                try {
                    key = watcher.take();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    System.out.println("Watcher interrupted");
                    break;
                } catch (ClosedWatchServiceException exception) {
                    break;
                }

                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == OVERFLOW) {
                        System.err.println(
                                "OVERFLOW: rescan directory required");
                        continue;
                    }

                    Object context = event.context();

                    if (!(context instanceof Path relativeName)) {
                        System.err.println(
                                "Unexpected event context: " + context);
                        continue;
                    }

                    Path changed =
                            directory.resolve(relativeName).normalize();

                    System.out.printf(
                            "%s: %s (count=%d)%n",
                            event.kind().name(),
                            changed,
                            event.count()
                    );
                }

                if (!key.reset()) {
                    System.out.println(
                            "Watch registration is no longer valid");
                    break;
                }
            }
        }
    }
}
~~~

Ví dụ sử dụng trong một terminal:

~~~text
javac DirectoryWatcherDemo.java
java DirectoryWatcherDemo watched
~~~

Trước đó, cần tạo thư mục **watched** bằng cách phù hợp với hệ điều hành hoặc công cụ quản lý tệp. Trong terminal khác, hãy tạo, sửa và xóa một tệp bên trong thư mục này.

Kết quả có thể tương tự:

~~~text
Watching: .../watched
ENTRY_CREATE: .../watched/sample.txt (count=1)
ENTRY_MODIFY: .../watched/sample.txt (count=1)
ENTRY_DELETE: .../watched/sample.txt (count=1)
~~~

**Đây chỉ là ví dụ đầu ra có thể xảy ra**, không phải thứ tự hoặc số lượng sự kiện được bảo đảm. Một thao tác ghi có thể tạo nhiều **ENTRY_MODIFY**, tạo tệp có thể đi kèm sự kiện sửa, và các provider khác nhau có thể báo những chuỗi sự kiện khác nhau.

Chương trình dùng **watcher.take()** để chờ vô thời hạn khi chưa có sự kiện. Trong hệ thống thật, cần có cơ chế dừng có kiểm soát, cơ chế quét lại khi **OVERFLOW** và chính sách xử lý công việc phù hợp.

## 5. Các bước trong vòng lặp nhận sự kiện

Mẫu xử lý cơ bản:

~~~java
while (true) {
    WatchKey key = watcher.take();

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý sự kiện.
    }

    boolean valid = key.reset();
    if (!valid) {
        break;
    }
}
~~~

Ba thao tác quan trọng:

1. **take()** chờ cho tới khi có một WatchKey được báo là sẵn sàng.
2. **pollEvents()** lấy và loại các sự kiện đang chờ của key để ứng dụng xử lý.
3. **reset()** đặt lại key sau khi xử lý để nó tiếp tục có thể được báo khi phát sinh thay đổi mới.

Không nên bỏ qua **reset()**. Nếu key chưa được reset đúng cách, ứng dụng có thể không nhận những lần báo hiệu tiếp theo như mong đợi.

### Cơ chế trạng thái của WatchKey

Có thể hình dung các trạng thái chính:

~~~text
     READY
       |
       | thay đổi được phát hiện
       v
    SIGNALED -----> key vào hàng đợi của WatchService
       |
       | take()/poll() lấy key
       v
  xử lý pollEvents()
       |
       | reset()
       +----------> READY nếu còn hợp lệ
       |
       +----------> INVALID nếu đăng ký không còn hợp lệ
~~~

Trong lúc key còn **SIGNALED**, các sự kiện mới có thể tiếp tục được ghi nhận hoặc được gộp theo quy tắc của provider. Sau khi **reset()**, nếu đã có sự kiện chờ thích hợp, key có thể lại được báo ngay.

**WatchKey không đại diện cho một sự kiện duy nhất.** Một key có thể chứa nhiều **WatchEvent**; vì vậy phải duyệt danh sách do **pollEvents()** trả về.

## 6. Lấy sự kiện bằng take(), poll() và poll(timeout)

**WatchService** cung cấp ba cách nhận WatchKey:

| Phương thức | Hành vi | Dùng khi |
|---|---|---|
| **take()** | Chặn cho tới khi có key hoặc quá trình chờ bị gián đoạn/đóng dịch vụ | Vòng xử lý chuyên nhận sự kiện |
| **poll()** | Trả về key ngay nếu có, hoặc **null** | Cần kiểm tra không chặn |
| **poll(long timeout, TimeUnit unit)** | Chờ tối đa thời gian chỉ định rồi trả về key hoặc **null** | Cần kiểm tra định kỳ trạng thái dừng hoặc công việc khác |

Ví dụ dùng timeout:

~~~java
import java.util.concurrent.TimeUnit;

WatchKey key = watcher.poll(5, TimeUnit.SECONDS);

if (key == null) {
    System.out.println("No events within five seconds");
} else {
    for (WatchEvent<?> event : key.pollEvents()) {
        System.out.println(event.kind().name());
    }

    if (!key.reset()) {
        System.out.println("Registration invalid");
    }
}
~~~

Mẫu này giả định biến **watcher** đã được tạo và thư mục đã đăng ký trước đó. **poll(timeout)** cũng có thể ném **InterruptedException**, nên method chứa mã phải xử lý hoặc khai báo ngoại lệ này.

### Không dùng vòng lặp poll() liên tục không có điều tiết

~~~java
// Không nên dùng vòng lặp bận:
while (true) {
    WatchKey key = watcher.poll();
    // Nếu null và không có cơ chế chờ, vòng lặp có thể dùng CPU cao.
}
~~~

Nếu muốn chờ sự kiện, **take()** hoặc **poll(timeout)** là lựa chọn tự nhiên hơn việc kiểm tra liên tục không có giới hạn.

## 7. WatchEvent.kind(), count() và context()

Mỗi sự kiện có ba thông tin chính:

~~~java
WatchEvent.Kind<?> kind = event.kind();
int count = event.count();
Object context = event.context();
~~~

### kind(): loại sự kiện

Với các loại chuẩn:

~~~java
if (event.kind() == ENTRY_CREATE) {
    // Mục xuất hiện.
} else if (event.kind() == ENTRY_DELETE) {
    // Mục biến mất.
} else if (event.kind() == ENTRY_MODIFY) {
    // Provider báo mục được sửa.
} else if (event.kind() == OVERFLOW) {
    // Có thể đã mất sự kiện: cần đối soát trạng thái.
}
~~~

Các phép so sánh với **StandardWatchEventKinds** mô tả những loại sự kiện chuẩn mà ứng dụng quan tâm.

### count(): số lần sự kiện được gộp

Một **WatchEvent** có thể đại diện cho nhiều lần xuất hiện tương đương đã được gộp, thể hiện qua **count()**.

~~~java
System.out.println(
        event.kind().name() + " x" + event.count());
~~~

Không nên diễn giải **count()** thành số thao tác người dùng chính xác tuyệt đối. Provider có thể gộp hoặc bỏ sự kiện; **count()** chỉ mô tả sự kiện đã được giao theo cơ chế của WatchService.

### context(): tên mục tương đối

Với **ENTRY_CREATE**, **ENTRY_DELETE** và **ENTRY_MODIFY** chuẩn trên thư mục, context thông thường là một **Path tương đối** chỉ tên mục thay đổi trong thư mục đã đăng ký.

Ví dụ:

~~~text
Thư mục đã theo dõi: /project/input
Context của sự kiện: data.csv
Đường dẫn kết hợp:  /project/input/data.csv
~~~

Mã xử lý:

~~~java
Object context = event.context();

if (context instanceof Path relativeName) {
    Path fullPath = directory.resolve(relativeName);
    System.out.println(fullPath);
}
~~~

**Không mặc định context là đường dẫn tuyệt đối.** Khi theo dõi nhiều thư mục, cần kết hợp context với **đúng thư mục tương ứng với WatchKey**, không phải một thư mục cố định bất kỳ.

Với **OVERFLOW**, không nên cố ép **context()** thành Path; ứng dụng cần xử lý riêng loại sự kiện này.

## 8. ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY có nghĩa gì trong thực tế?

### ENTRY_CREATE

Sự kiện tạo có thể xuất hiện khi:

- Tệp mới được tạo trong thư mục đang theo dõi.
- Một thư mục con mới xuất hiện.
- Một mục được chuyển hoặc đổi tên vào thư mục, tùy cách provider báo thao tác.

**ENTRY_CREATE không bảo đảm tệp đã được ghi xong và có thể xử lý ngay.** Một chương trình khác có thể đang tiếp tục ghi dữ liệu, hoặc mục có thể bị xóa trước khi chương trình watcher đọc đến nó.

Ví dụ:

~~~java
if (event.kind() == ENTRY_CREATE) {
    Path path = directory.resolve((Path) event.context());

    if (Files.isRegularFile(path)) {
        System.out.println("File currently exists: " + path);
    }
}
~~~

Trong ví dụ, **Files.isRegularFile(path)** là một phép kiểm tra tại thời điểm gọi, không phải bảo đảm tệp sẽ tiếp tục tồn tại trong suốt quá trình xử lý.

### ENTRY_DELETE

Khi nhận **ENTRY_DELETE**, mục đã có thể không còn tồn tại:

~~~java
if (event.kind() == ENTRY_DELETE) {
    Path deleted = directory.resolve((Path) event.context());

    System.out.println("Removed: " + deleted);
}
~~~

Không thể giả định **Files.readString(deleted)** sẽ đọc được nội dung trước khi xóa. Nếu cần dữ liệu của phiên bản cũ, ứng dụng phải có cơ chế lưu snapshot hoặc lưu nội dung trước đó.

### ENTRY_MODIFY

Một lần ghi hoặc thay đổi metadata có thể tạo ra một hoặc nhiều thông báo sửa, tùy provider.

~~~java
if (event.kind() == ENTRY_MODIFY) {
    Path changed = directory.resolve((Path) event.context());
    System.out.println("Check current state of " + changed);
}
~~~

Tốt hơn nên coi **ENTRY_MODIFY** là tín hiệu **cần kiểm tra lại trạng thái**, thay vì bằng chứng rằng nội dung đã hoàn tất và chỉ thay đổi đúng một lần.

### Rename hoặc move

Không có một sự kiện chuẩn phổ quát riêng mang tên **ENTRY_RENAME** trong bộ **StandardWatchEventKinds**. Một thao tác đổi tên/chuyển mục có thể được thể hiện bằng thông báo xóa và tạo, hoặc các biểu hiện khác theo provider. Không nên giả định luôn nhận được một cặp xóa-tạo để suy ra quan hệ đổi tên chính xác.

## 9. OVERFLOW: mất hoặc bỏ sự kiện

**OVERFLOW** là một trường hợp phải được thiết kế xử lý ngay từ đầu. Khi hệ thống có quá nhiều thay đổi, hàng đợi hoặc cơ chế theo dõi có thể không giữ được mọi thông báo.

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == OVERFLOW) {
        System.err.println("Events may have been lost");
        // Bắt đầu quét lại và đối soát trạng thái.
        continue;
    }

    // Xử lý sự kiện thường.
}
~~~

Nếu chỉ bỏ qua **OVERFLOW**, ứng dụng có thể giữ một chỉ mục hoặc bộ nhớ đệm **không còn phản ánh trạng thái thật** của thư mục.

### Chiến lược khôi phục

Một cách tiếp cận phù hợp:

1. Lưu trạng thái quan tâm trước đó, ví dụ tập đường dẫn đang có, metadata hoặc dấu vết nội dung.
2. Khi nhận **OVERFLOW**, đánh dấu trạng thái hiện tại **cần đối soát**.
3. Duyệt lại thư mục bằng **Files.list()**, **DirectoryStream** hoặc **Files.walkFileTree()** theo nhu cầu.
4. Đối chiếu trạng thái quét được với chỉ mục trước đó, phát hiện những mục hiện có hoặc đã biến mất.
5. Với các tệp còn tồn tại, kiểm tra lại dữ liệu cần thiết; không chỉ so sánh tên nếu ứng dụng quan tâm nội dung.
6. Tiếp tục nhận sự kiện và thực hiện đối soát lại khi cần để xử lý những thay đổi xảy ra trong lúc quét.

Ví dụ hàm lấy tên các mục trực tiếp đang tồn tại:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Set<Path> snapshotEntries(Path directory) throws IOException {
    try (Stream<Path> entries = Files.list(directory)) {
        return entries
                .map(Path::getFileName)
                .collect(Collectors.toSet());
    }
}
~~~

**snapshotEntries()** đọc tập tên các mục tại thời điểm duyệt, rồi đóng Stream do **Files.list()** cung cấp. Đây là ví dụ **đối soát danh sách tên**, không phải bản ghi atomic của mọi thay đổi và cũng không phát hiện chắc chắn những lần sửa nội dung của một tệp vẫn giữ nguyên tên.

Với hệ thống quan trọng, cần thiết kế snapshot theo miền nghiệp vụ (kích thước, thời điểm sửa, nội dung hoặc phiên bản) và chấp nhận rằng snapshot từ một thư mục đang thay đổi **không tự động là một giao dịch nhất quán**.

## 10. Race condition: sự kiện đến nhưng tệp đã thay đổi lần nữa

WatchService cho biết **một sự kiện đã được phát hiện**, không khóa tệp để bảo đảm trạng thái được giữ nguyên cho tới khi ứng dụng xử lý.

Ví dụ trình tự:

~~~text
Ứng dụng A: tạo report.csv
             |
WatchService: báo ENTRY_CREATE
             |
Ứng dụng A: ghi tiếp dữ liệu và đổi tên tệp
             |
Ứng dụng B: nhận WatchKey
             |
Ứng dụng B: kiểm tra report.csv (có thể không còn tồn tại)
~~~

Vì vậy:

- **Files.exists(path)** hoặc **Files.isRegularFile(path)** chỉ xác nhận trạng thái ở thời điểm kiểm tra, không bảo đảm một thao tác kế tiếp sẽ thành công.
- Không coi một lần **ENTRY_CREATE** là cam kết tệp đã sẵn sàng đọc.
- Nếu mở tệp thất bại vì nó bị xóa/chuyển hoặc bị khóa theo nền tảng, xử lý đúng loại lỗi thay vì cho rằng watcher đã hoạt động sai.
- Khi xử lý các tệp đầu vào, ứng dụng nên có giao thức xác nhận tệp đã hoàn tất nếu cần.

### Mô hình ghi tệp tạm rồi công bố tệp đích

Nếu bạn kiểm soát **bên ghi dữ liệu**, một cách giảm nguy cơ đọc tệp chưa hoàn tất là:

1. Ghi toàn bộ dữ liệu vào một tệp tạm riêng trong cùng thư mục hoặc cùng file store phù hợp.
2. Đóng luồng ghi và xác minh dữ liệu.
3. Chuyển tệp tạm sang tên đích khi đã sẵn sàng; dùng cơ chế move/atomic move khi file system hỗ trợ.
4. Bên watcher kiểm tra tên đích theo quy ước và mở để đọc.

Ví dụ ý tưởng:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path temporary = Path.of("data", "report.tmp");
Path published = Path.of("data", "report.csv");

// temporary đã được ghi và đóng ở bước trước.
Files.move(
        temporary,
        published,
        StandardCopyOption.ATOMIC_MOVE
);
~~~

**ATOMIC_MOVE không được mọi file system hoặc mọi tình huống hỗ trợ**; thao tác có thể ném **AtomicMoveNotSupportedException**. Cần thiết kế fallback và quy tắc xử lý tệp đích đã tồn tại phù hợp. Quan trọng hơn, việc move thành công không biến WatchService thành kênh sự kiện không thể mất: bên đọc vẫn cần kiểm tra trạng thái và khôi phục sau **OVERFLOW**.

Nếu không kiểm soát chương trình tạo tệp, có thể dùng cơ chế chờ tệp ổn định, kiểm tra độ dài/metadata theo chu kỳ hoặc nhận một tín hiệu hoàn tất riêng từ nguồn; cần giới hạn thời gian chờ và xử lý lỗi thay vì lặp vô hạn.

## 11. Theo dõi nhiều thư mục

Một WatchService có thể được dùng để đăng ký nhiều thư mục theo khả năng của provider. Mỗi đăng ký trả về một **WatchKey**; khi nhận key, cần biết nó đại diện cho thư mục nào.

Có thể giữ một **Map<WatchKey, Path>**:

~~~java
import java.nio.file.Path;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.HashMap;
import java.util.Map;

Map<WatchKey, Path> directories = new HashMap<>();

WatchKey keyA = dirA.register(
        watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
directories.put(keyA, dirA);

WatchKey keyB = dirB.register(
        watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
directories.put(keyB, dirB);
~~~

Ví dụ giả định **dirA**, **dirB**, **watcher** đã được khai báo và xử lý ngoại lệ phù hợp.

Khi nhận sự kiện:

~~~java
WatchKey key = watcher.take();
Path watchedDirectory = directories.get(key);

if (watchedDirectory != null) {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == OVERFLOW) {
            // Quét lại thư mục phù hợp.
            continue;
        }

        if (event.context() instanceof Path relative) {
            Path changed = watchedDirectory.resolve(relative);
            System.out.println(changed);
        }
    }
}

if (!key.reset()) {
    directories.remove(key);
}
~~~

**key.watchable()** cũng cung cấp đối tượng Watchable đã đăng ký. Với đăng ký bằng Path, đó là một Path tương ứng; dùng map rõ ràng vẫn hữu ích khi cần quản lý metadata hoặc vòng đời nhiều thư mục.

Đừng lấy context của key thuộc **dirB** rồi ghép vào **dirA**. Điều đó sẽ tạo ra đường dẫn sai và có thể khiến ứng dụng xử lý nhầm tệp.

## 12. WatchService không theo dõi đệ quy tự động

Đăng ký thư mục gốc không đồng nghĩa các thư mục con đều được theo dõi. Ví dụ:

~~~text
workspace/
├── a.txt
└── nested/
    └── b.txt
~~~

Khi chỉ đăng ký **workspace/**, ứng dụng thường quan sát những thay đổi đối với **a.txt** và chính mục **nested/** trong thư mục gốc, nhưng **không tự động** nhận mọi thay đổi sâu bên trong **nested/**.

Muốn theo dõi toàn bộ cây thư mục, một cách tổng quát là:

1. Duyệt các thư mục hiện có bằng **Files.walkFileTree()**.
2. Đăng ký **mỗi thư mục** với WatchService.
3. Duy trì map từ WatchKey đến Path.
4. Khi xuất hiện thư mục mới, đăng ký thư mục đó cùng các thư mục con có thể đã được tạo bên trong.
5. Khi key không còn hợp lệ, loại bỏ đăng ký tương ứng khỏi map.
6. Khi có **OVERFLOW**, quét lại và đối soát **toàn bộ phạm vi** bị ảnh hưởng.

Một đoạn hỗ trợ đăng ký cây thư mục:

~~~java
import java.io.IOException;
import java.nio.file.BasicFileAttributes;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.Map;

import static java.nio.file.StandardWatchEventKinds.*;

static void registerTree(
        Path root,
        WatchService watcher,
        Map<WatchKey, Path> directories) throws IOException {

    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult preVisitDirectory(
                Path dir,
                java.nio.file.attribute.BasicFileAttributes attrs)
                throws IOException {

            WatchKey key = dir.register(
                    watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
            directories.put(key, dir);

            return FileVisitResult.CONTINUE;
        }
    });
}
~~~

Ví dụ trên là hàm hỗ trợ, không phải chương trình hoàn chỉnh. **BasicFileAttributes** nằm trong package **java.nio.file.attribute**; khai báo đầy đủ trong tham số cho thấy chính xác kiểu được sử dụng.

**Files.walkFileTree()** theo mặc định không đi theo symbolic link tới thư mục khác. Nếu muốn theo link, phải thiết kế chính sách vòng lặp, quyền truy cập, phạm vi được phép theo dõi và giới hạn tài nguyên phù hợp.

### Xử lý thư mục mới

Khi nhận **ENTRY_CREATE**, cần xác định mục mới có đang là thư mục hay không:

~~~java
import java.nio.file.LinkOption;

if (event.kind() == ENTRY_CREATE
        && event.context() instanceof Path relative) {

    Path created = watchedDirectory.resolve(relative);

    if (Files.isDirectory(created, LinkOption.NOFOLLOW_LINKS)) {
        registerTree(created, watcher, directories);
    }
}
~~~

Phần mã giả định các biến **watchedDirectory**, **watcher**, **directories** và **event** đã tồn tại trong vòng nhận sự kiện.

Có một **khoảng đua (race)**: thư mục mới có thể đã chứa nhiều tệp trước khi ứng dụng đăng ký nó. Những thay đổi xảy ra trước đăng ký có thể không được giao dưới dạng sự kiện. Do đó, sau khi đăng ký nhánh mới, ứng dụng cần quét nội dung nhánh để phát hiện trạng thái đã tồn tại và không phụ thuộc hoàn toàn vào sự kiện phát sinh sau đó.

Ngoài ra, việc kiểm tra **Files.isDirectory()** có thể thất bại vì mục vừa bị xóa hoặc vì lỗi I/O. Không nên coi kết quả false là bằng chứng chắc chắn mục chưa bao giờ là thư mục.

## 13. Ví dụ theo dõi đệ quy có quản lý WatchKey

Ví dụ dưới đây trình bày một vòng xử lý theo dõi nhiều thư mục, tự đăng ký khi thấy một thư mục con mới. Nó minh họa cách quản lý key nhưng **không phải hệ thống đối soát đầy đủ**: thông báo **OVERFLOW** và những thay đổi xảy ra trong lúc đăng ký/quét phải được xử lý thêm trong ứng dụng sản xuất.

Lưu thành **RecursiveWatcherDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashMap;
import java.util.Map;

import static java.nio.file.StandardWatchEventKinds.*;

public final class RecursiveWatcherDemo {
    private final WatchService watcher;
    private final Map<WatchKey, Path> directories = new HashMap<>();

    private RecursiveWatcherDemo(WatchService watcher) {
        this.watcher = watcher;
    }

    private void registerTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attributes)
                    throws IOException {

                WatchKey key = dir.register(
                        watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
                directories.put(key, dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private void run() throws InterruptedException {
        while (!directories.isEmpty()) {
            WatchKey key = watcher.take();
            Path directory = directories.get(key);

            if (directory == null) {
                key.reset();
                continue;
            }

            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == OVERFLOW) {
                    System.err.println(
                            "OVERFLOW in " + directory
                            + ": rescan required");
                    continue;
                }

                if (!(event.context() instanceof Path relative)) {
                    continue;
                }

                Path changed = directory.resolve(relative).normalize();

                System.out.println(
                        event.kind().name() + ": " + changed);

                if (event.kind() == ENTRY_CREATE
                        && Files.isDirectory(
                                changed, LinkOption.NOFOLLOW_LINKS)) {
                    try {
                        registerTree(changed);
                        System.out.println(
                                "Registered new subtree: " + changed);
                        // Production code should also rescan the subtree.
                    } catch (IOException exception) {
                        System.err.println(
                                "Cannot register subtree "
                                + changed + ": " + exception);
                    }
                }
            }

            if (!key.reset()) {
                directories.remove(key);
                System.out.println(
                        "Stopped watching: " + directory);
            }
        }
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        if (args.length != 1) {
            System.err.println(
                    "Usage: java RecursiveWatcherDemo <directory>");
            return;
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();

        if (!Files.isDirectory(root)) {
            System.err.println("Not a directory: " + root);
            return;
        }

        try (WatchService watcher =
                     root.getFileSystem().newWatchService()) {

            RecursiveWatcherDemo app = new RecursiveWatcherDemo(watcher);

            app.registerTree(root);
            System.out.println("Watching tree: " + root);
            app.run();
        }
    }
}
~~~

Lưu ý quan trọng:

- Mỗi thư mục trong cây được đăng ký riêng.
- **Map<WatchKey, Path>** xác định đúng thư mục của từng sự kiện.
- Khi nhận **ENTRY_CREATE** của một thư mục, chương trình cố đăng ký cả nhánh đó.
- Khi **reset()** trả false, key được loại khỏi map.
- Nếu một thư mục bị xóa và key trở nên không hợp lệ, ứng dụng ngừng dùng key đó.
- Nếu cây có nhiều thay đổi đồng thời, có thể mất sự kiện trước khi một nhánh mới được đăng ký.
- **OVERFLOW hiện chỉ được ghi cảnh báo**: ứng dụng sản xuất cần bổ sung logic quét lại và đối soát dữ liệu.
- Chương trình không cung cấp sẵn thao tác dừng qua lệnh nhập; cần cơ chế shutdown khi dùng trong dịch vụ chạy lâu dài.

Đừng coi **theo dõi đệ quy** chỉ là một tùy chọn bật/tắt của WatchService. Đó là logic tổ chức nhiều đăng ký và đối soát trạng thái do ứng dụng thiết kế.

## 14. reset(), cancel() và key không còn hợp lệ

Một WatchKey có thể không còn hợp lệ khi:

- Ứng dụng chủ động gọi **cancel()**.
- Thư mục hoặc đối tượng được theo dõi không còn được provider cho phép theo dõi.
- WatchService bị đóng.
- Một điều kiện khác của file system provider làm đăng ký mất hiệu lực.

Ví dụ:

~~~java
WatchKey key = directory.register(
        watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);

if (key.isValid()) {
    System.out.println("Registration valid");
}

key.cancel();
System.out.println(key.isValid()); // false
~~~

**cancel()** hủy đăng ký; nó không phải thao tác xóa thư mục hay tệp trên đĩa.

**reset()** trả về boolean thể hiện key còn hợp lệ sau khi đặt lại hay không. Khi giá trị là **false**, ứng dụng nên bỏ đăng ký đó khỏi cấu trúc quản lý, không tiếp tục kỳ vọng nhận sự kiện mới từ key.

### Thư mục bị xóa rồi tạo lại

Nếu một thư mục đang được theo dõi bị xóa và sau đó tạo lại với cùng tên, đừng mặc định WatchKey cũ tự động theo dõi đối tượng thư mục mới.

Ứng dụng cần phát hiện trạng thái mất hiệu lực, kiểm tra lại đường dẫn và **đăng ký lại** khi thích hợp. Với trình theo dõi đệ quy, việc đăng ký lại có thể cần kết hợp quét cây thư mục để phát hiện những nhánh mới.

## 15. Đóng WatchService và dừng vòng xử lý

**WatchService** là tài nguyên cần được đóng khi không còn dùng:

~~~java
try (WatchService watcher =
             FileSystems.getDefault().newWatchService()) {
    // Đăng ký và xử lý các sự kiện.
}
~~~

Khi **close()** được gọi, WatchService không còn nhận đăng ký và sự kiện theo cách của dịch vụ đang mở; các key liên quan trở nên không hợp lệ. Một thread đang chờ **take()** có thể được đánh thức bằng **ClosedWatchServiceException**.

Một ứng dụng chạy lâu dài nên có cách dừng có kiểm soát, chẳng hạn:

1. Thành phần quản lý yêu cầu dừng.
2. Đóng WatchService để đánh thức thread đang chờ.
3. Thread xử lý bắt **ClosedWatchServiceException** như một tín hiệu kết thúc nếu việc đóng là chủ đích.
4. Giải phóng các thành phần liên quan và chờ worker xử lý kết thúc nếu hợp đồng ứng dụng yêu cầu.

Không nên dùng **System.exit()** hoặc kết thúc cưỡng bức như chiến lược quản lý tài nguyên thông thường.

### InterruptedException

**take()** và **poll(timeout)** là những thao tác có thể bị gián đoạn:

~~~java
try {
    WatchKey key = watcher.take();
    // Xử lý key.
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    // Kết thúc hoặc chuyển tín hiệu hủy tới caller.
}
~~~

Nếu bắt **InterruptedException** mà không ném tiếp, thường nên khôi phục cờ interrupt bằng **Thread.currentThread().interrupt()** để không làm mất tín hiệu hủy.

### WatchService và xử lý đồng thời

Không nên giả định mỗi sự kiện sẽ được phân cho một thread riêng hoặc mỗi event là một giao dịch độc lập. Thường một thread chuyên lấy key và chuyển công việc có giới hạn sang bộ xử lý khác là cách tổ chức dễ kiểm soát.

Nếu dùng nhiều thread để xử lý nội dung tệp, cần tránh sửa chung **Map**, index hoặc bộ nhớ đệm mà không có cơ chế đồng bộ phù hợp. Việc WatchService báo sự kiện không tự làm các cấu trúc dữ liệu của ứng dụng trở nên thread-safe.

## 16. Không thực hiện I/O nặng ngay trong vòng nhận sự kiện

Một lỗi thiết kế phổ biến: mỗi khi nhận **ENTRY_MODIFY**, chương trình lập tức chạy một tác vụ tốn nhiều thời gian trong chính thread đang gọi **take()**.

Ví dụ:

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    // Xử lý lâu ở đây khiến vòng watcher nhận các key tiếp theo chậm.
    // parseLargeFile();
    // reindexWholeRepository();
}
key.reset();
~~~

Khi vòng theo dõi không quay lại nhận sự kiện đủ nhanh, hàng đợi có thể tích lũy nhiều thay đổi và tăng khả năng xuất hiện **OVERFLOW**.

Một kiến trúc thực tế thường tách hai phần:

~~~text
WatchService / WatchKey
          |
          v
  Phát hiện đường dẫn
          |
          v
 Hàng đợi có giới hạn
          |
          v
 Worker xử lý nội dung
          |
          v
 Cập nhật chỉ mục/trạng thái
~~~

Các lưu ý:

- **Giữ vòng nhận sự kiện nhẹ:** đọc sự kiện, xác định đường dẫn, đánh dấu cần xử lý, reset key.
- **Gộp công việc trùng lặp:** nhiều **ENTRY_MODIFY** cho cùng một đường dẫn không nhất thiết đòi hỏi xử lý lại tức thời nhiều lần.
- **Có giới hạn hàng đợi:** tránh cấp phát vô hạn khi bên tạo tệp nhanh hơn bên xử lý.
- **Có kế hoạch khi quá tải:** đánh dấu cần quét lại hoặc làm mới toàn bộ chỉ mục thay vì âm thầm bỏ dữ liệu.
- **Có điểm dừng:** khi service shutdown, quyết định các công việc đang chờ được hoàn tất hay hủy theo hợp đồng.

Mẫu phát hiện bằng sự kiện và xử lý theo trạng thái hiện tại thường đáng tin hơn việc coi mỗi event là một mệnh lệnh “thực hiện đúng một lần”.

## 17. Debounce và chống xử lý lặp

Một trình soạn thảo có thể ghi một tệp thành nhiều thao tác nhỏ trong một khoảng thời gian ngắn. WatchService có thể báo nhiều thay đổi liên tiếp.

Thay vì xử lý mỗi **ENTRY_MODIFY** ngay lập tức, ứng dụng có thể thực hiện **debounce**:

1. Khi có event của đường dẫn **P**, lưu thời điểm phát hiện gần nhất.
2. Nếu có event mới của **P**, cập nhật thời điểm.
3. Chờ một khoảng yên lặng do ứng dụng cấu hình.
4. Kiểm tra lại trạng thái thực của **P** rồi xử lý.
5. Nếu phát hiện thêm thay đổi trong lúc xử lý, đánh dấu **P** cần xử lý lại.

Đây chỉ là một chiến lược cải thiện hiệu suất và độ ổn định. **Debounce không bảo đảm tệp đã được ghi xong**, đặc biệt khi quá trình ghi có khoảng nghỉ dài hoặc dữ liệu nằm trên hệ thống tệp mạng.

Với hệ thống nhập dữ liệu quan trọng, giao thức công bố “đã ghi xong”, move tệp tạm hoặc một thông điệp xác nhận riêng thường đáng tin hơn việc dựa vào thời gian chờ cố định.

## 18. Bảo vệ đường dẫn và dữ liệu không tin cậy

Một ứng dụng watcher có thể theo dõi thư mục nhận tệp từ bên ngoài. Không nên coi nội dung, tên tệp hoặc đường dẫn xuất hiện trong event là an toàn.

Những điểm cần quan tâm:

- Dùng **Path.resolve()** để kết hợp đường dẫn, tránh tự nối chuỗi bằng ký tự **/** hoặc **\\**.
- Kiểm tra kiểu tệp và quyền truy cập trước khi xử lý; nhưng phải hiểu rằng trạng thái có thể thay đổi ngay sau kiểm tra.
- Không giả định **ENTRY_CREATE** luôn chỉ tệp thường: đó cũng có thể là thư mục, symbolic link hoặc mục khác.
- Nếu ứng dụng chỉ được phép xử lý một cây thư mục nhất định, cần có chính sách kiểm soát phạm vi đường dẫn và symbolic link rõ ràng.
- Một kiểm tra **normalize()** không tự ngăn mọi trường hợp truy cập ngoài phạm vi, nhất là khi symbolic link hoặc việc thay đổi cây thư mục diễn ra đồng thời.
- Không thực thi nội dung tệp chỉ vì có một event mới.
- Không dùng WatchService làm cơ chế bảo mật duy nhất để ngăn thay đổi trái phép; nó không cung cấp nhật ký đầy đủ và đáng tin cậy cho mục tiêu kiểm toán an ninh.

Ví dụ với tệp mới, có thể chọn bỏ qua symbolic link nếu ứng dụng không muốn đi theo liên kết:

~~~java
import java.nio.file.LinkOption;

if (event.kind() == ENTRY_CREATE
        && event.context() instanceof Path relative) {

    Path candidate = directory.resolve(relative);

    if (Files.isRegularFile(
            candidate, LinkOption.NOFOLLOW_LINKS)) {
        System.out.println("Regular file now: " + candidate);
    }
}
~~~

Mẫu trên chỉ là bộ lọc trạng thái tại thời điểm gọi; nó **không tạo bảo đảm chống TOCTOU** (*time-of-check to time-of-use*). Khi xử lý dữ liệu nhạy cảm, cần thiết kế các thao tác mở/tương tác tệp có giới hạn quyền truy cập và đặc tính an toàn theo nền tảng.

## 19. Khác biệt hệ điều hành và file system provider

API Java chuẩn cung cấp chung những khái niệm WatchService, WatchKey và WatchEvent, nhưng cơ chế bên dưới do file system provider và hệ điều hành quyết định.

Một số yếu tố có thể khác biệt:

- Sự kiện nào được hỗ trợ và được phát khi nào.
- Độ trễ phát hiện thay đổi.
- Việc gộp nhiều sự kiện tương tự.
- Cách diễn giải thao tác đổi tên hoặc chuyển tệp.
- Giới hạn số lượng thư mục có thể theo dõi.
- Hành vi trên file system mạng, thiết bị ngoài hoặc file system ảo.
- Việc mất đăng ký khi thư mục bị xóa hoặc không thể truy cập.
- Cách xử lý symbolic link và các thư mục mới xuất hiện.

**Không nên xây dựng correctness dựa trên một chuỗi sự kiện quan sát được ở duy nhất máy phát triển.** Hãy thử nghiệm trên những hệ điều hành và loại file system thực sự dùng trong môi trường triển khai.

### WatchService không bảo đảm phát hiện thay đổi tức thời

Ngay cả với thư mục local, thông báo có thể không được giao ngay sau thao tác ghi. Nếu ứng dụng có yêu cầu thời gian xử lý, cần xác định mức độ trễ chấp nhận được, chính sách timeout và phương án dự phòng thay vì xem WatchService như một cơ chế real-time tuyệt đối.

### Giới hạn tài nguyên

Đăng ký theo dõi nhiều thư mục, đặc biệt cây thư mục lớn, có thể tiêu thụ tài nguyên hệ điều hành hoặc gặp giới hạn provider. Nên có cách giới hạn phạm vi theo dõi, ghi nhận lỗi đăng ký, đóng những watcher không còn cần thiết và thực hiện đối soát định kỳ theo nhu cầu.

## 20. Gỡ lỗi và xử lý tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Không thấy sự kiện nào | Chưa đăng ký, theo dõi sai thư mục, provider không hỗ trợ hoặc key không được reset | Xác minh đường dẫn, kiểm tra đăng ký và chu trình **take() → pollEvents() → reset()** |
| **take()** chờ mãi | Chưa có key được báo, sai phạm vi theo dõi hoặc chương trình chỉ cần timeout | Dùng **poll(timeout)** khi cần kiểm tra định kỳ; xác minh thư mục |
| Tạo một tệp nhưng thấy nhiều event | Provider báo cả tạo lẫn sửa hoặc gộp theo cách riêng | Thiết kế xử lý idempotent, gộp công việc theo đường dẫn |
| Xóa tệp rồi vẫn nhận sự kiện liên quan | Sự kiện được giao trễ, trạng thái đã thay đổi | Kiểm tra trạng thái hiện tại; không tin đường dẫn còn tồn tại |
| Không thấy event ở thư mục con | WatchService không theo dõi đệ quy tự động | Đăng ký từng thư mục con; xử lý thư mục mới |
| Có **OVERFLOW** | Hàng đợi hoặc cơ chế thông báo không giữ đủ sự kiện | Quét lại và đối soát; giảm I/O nặng trong vòng nhận |
| **reset()** trả false | Key không còn hợp lệ | Loại key, cân nhắc đăng ký lại nếu thư mục tồn tại |
| Gặp **ClosedWatchServiceException** | Service đã bị đóng | Kiểm tra vòng đời và tín hiệu shutdown |
| Gặp **InterruptedException** | Thread chờ bị interrupt | Tôn trọng tín hiệu hủy; khôi phục interrupt nếu bắt và không ném tiếp |
| Đăng ký thất bại | Không phải thư mục hợp lệ, lỗi I/O hoặc hạn chế provider | Kiểm tra quyền, đường dẫn, provider và loại ngoại lệ |
| Một file được xử lý khi đang ghi | WatchService báo thay đổi trước khi producer hoàn tất | Dùng giao thức công bố tệp hoàn chỉnh hoặc xác minh trạng thái |
| Chuyển/đổi tên file không ra event như mong đợi | Không có hợp đồng rename chuẩn chung | Theo dõi trạng thái và đối soát, không phụ thuộc cặp sự kiện cố định |
| Chương trình dùng nhiều CPU | Vòng **poll()** không chờ hoặc xử lý sự kiện lặp | Dùng **take()**/**poll(timeout)**, debounce và queue có giới hạn |
| Kết quả khác giữa local và network drive | Provider hoặc cơ chế bên dưới có khác biệt | Kiểm thử môi trường triển khai, có rescan dự phòng |

## 21. Checklist trước khi triển khai WatchService

Trước khi đưa một trình theo dõi thư mục vào ứng dụng Java 27, hãy xác nhận:

- Thư mục có thực sự tồn tại và thuộc file system provider hỗ trợ WatchService không?
- Có đăng ký chính xác **ENTRY_CREATE**, **ENTRY_DELETE** và **ENTRY_MODIFY** theo nhu cầu không?
- Có vòng nhận **take()**, **poll()** hoặc **poll(timeout)** phù hợp với cách dừng chương trình không?
- Mỗi WatchKey có được xử lý các **pollEvents()** rồi **reset()** đúng cách không?
- Khi **reset()** trả false, ứng dụng có loại key và đăng ký lại nếu cần không?
- Có xử lý **OVERFLOW** bằng quét lại và đối soát, thay vì chỉ bỏ qua không?
- Khi tạo đường dẫn đầy đủ, context của event có được kết hợp với đúng thư mục của WatchKey không?
- Có tránh giả định mỗi thao tác tệp luôn tương ứng đúng một event không?
- Có tránh xử lý tệp như thể **ENTRY_CREATE** đồng nghĩa “đã ghi xong” không?
- Khi tệp bị sửa/xóa trước lúc xử lý, có đường đi lỗi hợp lý không?
- Nếu theo dõi đệ quy, đã đăng ký từng thư mục hiện có và các thư mục mới chưa?
- Có rescan để bù những thay đổi xảy ra trong khoảng thời gian chưa đăng ký không?
- Có đóng WatchService và quản lý interrupt khi shutdown không?
- Các tác vụ nặng có được tách khỏi vòng nhận sự kiện để giảm nguy cơ OVERFLOW không?
- Có cơ chế gộp và điều tiết event trùng lặp, hàng đợi giới hạn và chính sách quá tải không?
- Đường dẫn, symbolic link, quyền truy cập và dữ liệu đầu vào có được kiểm tra theo yêu cầu an toàn không?
- Đã kiểm thử trên hệ điều hành và file system của môi trường chạy thật chưa?

## Kết luận

**WatchService** giúp Java 27 phản ứng với những thay đổi được hệ thống tệp báo trong một thư mục, thông qua chuỗi **đăng ký Path → nhận WatchKey → đọc WatchEvent → reset WatchKey**. Các sự kiện chuẩn **ENTRY_CREATE**, **ENTRY_DELETE** và **ENTRY_MODIFY** giúp ứng dụng xác định đường dẫn cần kiểm tra lại; **OVERFLOW** báo rằng thông tin sự kiện có thể không đầy đủ.

Để xây dựng một trình theo dõi đáng tin cậy, cần nhớ bốn giới hạn quan trọng: **sự kiện có thể bị gộp hoặc mất; thao tác tạo tệp không đồng nghĩa tệp đã ghi xong; việc theo dõi không đệ quy tự động; và thông báo không thay thế việc kiểm tra trạng thái thực của file system**.

Trong ứng dụng Java hiện đại, thiết kế phù hợp là giữ vòng nhận sự kiện nhẹ, quản lý chính xác các WatchKey và vòng đời WatchService, xử lý những thay đổi lặp theo cách idempotent và kết hợp **quét lại/đối soát trạng thái** khi cần.
