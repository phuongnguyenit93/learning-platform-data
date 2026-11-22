# `IOException` và thay đổi trạng thái hệ thống tệp khi truy vấn `FileStore` trong Java

## Mục tiêu bài học

`java.nio.file.FileStore` đại diện cho vùng lưu trữ mà Java có thể quan sát: phân vùng, volume, thiết bị, storage pool, file system hoặc một loại kho lưu trữ do **file-system provider** định nghĩa. Ta thường lấy `FileStore` bằng `Files.getFileStore(Path)`, rồi hỏi tổng dung lượng, dung lượng còn có thể dùng, dung lượng chưa cấp phát hoặc kích thước block.

Những phép truy vấn này **không làm hệ thống tệp đứng yên**. Trong khi ứng dụng đang chạy, tệp có thể bị di chuyển, volume bị tháo gắn kết, ổ đĩa rời bị ngắt, mount mạng mất kết nối, quota thay đổi hoặc tiến trình khác tiêu thụ dung lượng. Vì vậy `FileStore` vừa liên quan đến **checked `IOException`**, vừa liên quan đến việc **số liệu đúng khi vừa đọc có thể không còn đúng ngay sau đó**.

Bài này giúp bạn:

- Nhận diện chính xác API nào của `FileStore` ném `IOException`, API nào có thể ném `UnsupportedOperationException`.
- Hiểu tác động của thay đổi trạng thái hệ thống tệp lên `Files.getFileStore(path)` và những lần dùng `FileStore` sau đó.
- Phân biệt `getUsableSpace()`, `getUnallocatedSpace()`, `getTotalSpace()` và `isReadOnly()`.
- Tránh lỗi **time-of-check to time-of-use (TOCTOU)**: kiểm tra đủ dung lượng không bảo đảm lần ghi kế tiếp thành công.
- Thiết kế xử lý lỗi, cảnh báo, tái truy vấn và ghi dữ liệu theo hướng an toàn.
- Chạy chương trình Java 17+ mô phỏng số liệu thay đổi và `IOException` với kết quả kiểm tra được, không cần tháo ổ đĩa thật.

**Phạm vi Java:** `FileStore` và `Files.getFileStore` có từ Java 7, tiếp tục được hỗ trợ. Riêng `FileStore.getBlockSize()` được bổ sung từ **Java 10** và cũng vẫn có mặt trong JDK hiện hành. Không dùng API legacy.

## 1. Từ `Path` tới `FileStore`

Để lấy thông tin vùng lưu trữ nơi một đường dẫn **đang tồn tại**, dùng:

~~~java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of(".").toAbsolutePath().normalize();
FileStore store = Files.getFileStore(path);
~~~

`Path.of(".")` ở đây trỏ tới thư mục làm việc hiện tại. Khi gọi `Files.getFileStore(path)`, Java hỏi provider của `Path` để xác định vùng lưu trữ chứa đường dẫn đó.

`FileStore` **không đồng nghĩa một tệp**, cũng không luôn đồng nghĩa một ổ đĩa vật lý riêng biệt: một vùng lưu trữ có thể tương ứng với mount, volume, thiết bị, vùng lưu trữ ảo hoặc một provider đặc thù. `store.name()` và `store.type()` do provider định nghĩa; không viết logic nghiệp vụ phụ thuộc vào một giá trị tên/type cố định trên mọi hệ điều hành.

**Điểm cần nhớ:** `Files.getFileStore(Path)` khai báo `throws IOException`. Truy vấn có thể không thành công nếu đường dẫn, provider hoặc hệ thống tệp không thể truy cập tại thời điểm gọi.

### Ví dụ đọc có bắt lỗi

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of(".").toAbsolutePath().normalize();

try {
    FileStore store = Files.getFileStore(path);
    long total = store.getTotalSpace();
    long usable = store.getUsableSpace();

    System.out.println("store: " + store.name());
    System.out.println("total bytes: " + total);
    System.out.println("usable bytes: " + usable);
} catch (IOException ex) {
    System.err.println("Không thể đọc thông tin vùng lưu trữ: " + ex.getMessage());
}
~~~

Đây là **đoạn minh họa trong một phương thức**, không phải chương trình độc lập. Giá trị in ra tùy máy, quyền truy cập, provider và trạng thái tại thời điểm chạy; không có stdout số cụ thể nào đúng trên mọi hệ thống.

## 2. Những phương thức nào liên quan đến lỗi?

| API | Kết quả | Lỗi cần tính tới |
| --- | --- | --- |
| `Files.getFileStore(path)` | `FileStore` chứa một path | `IOException` khi không thể xác định/truy cập; loại lỗi cụ thể phụ thuộc provider |
| `store.getTotalSpace()` | Tổng số byte của file store | `IOException` |
| `store.getUsableSpace()` | Số byte **có thể dùng bởi JVM hiện tại**, theo ước lượng | `IOException` |
| `store.getUnallocatedSpace()` | Số byte **chưa cấp phát** | `IOException` |
| `store.getBlockSize()` | Kích thước block, tính bằng byte | `IOException`; **`UnsupportedOperationException` nếu không được hỗ trợ** |
| `store.getAttribute(name)` | Thuộc tính do provider định nghĩa | `IOException`; `UnsupportedOperationException` nếu attribute/view không hỗ trợ |
| `store.isReadOnly()` | Cờ read-only dạng `boolean` | Không khai báo checked `IOException` trong chữ ký |
| `store.name()`, `store.type()` | Chuỗi tên và loại vùng lưu trữ | Không khai báo checked `IOException` trong chữ ký |

Với `getBlockSize()`, cần chú ý hợp đồng của Java 10+: implementation mặc định trong lớp `FileStore` ném `UnsupportedOperationException`. Một provider **có thể** ghi đè và hỗ trợ phương thức này, nhưng không phải provider nào cũng làm vậy. Đừng coi việc truy vấn được `getTotalSpace` là bằng chứng `getBlockSize` chắc chắn hoạt động.

~~~java
try {
    long blockSize = store.getBlockSize();
    System.out.println("block size = " + blockSize);
} catch (UnsupportedOperationException ex) {
    // Provider không hỗ trợ thuộc tính block size.
} catch (IOException ex) {
    // Có hỗ trợ về mặt API nhưng truy vấn gặp lỗi I/O.
}
~~~

Đây là hai tình huống khác nhau: **không hỗ trợ tính năng** và **tính năng truy vấn thất bại**. Không tự quy cả hai thành `0` vì `0` dễ bị hiểu nhầm là giá trị đo hợp lệ.

## 3. Vì sao `IOException` xuất hiện?

`IOException` là **checked exception**. Nó có thể xuất hiện cả khi **lấy** `FileStore` từ `Path` lẫn khi **đọc thông tin** từ `FileStore`.

Một số tình huống thực tế:

| Thay đổi / vấn đề | Ảnh hưởng có thể xảy ra |
| --- | --- |
| Tệp hoặc thư mục bị xóa trước khi truy vấn | `Files.getFileStore(path)` có thể thất bại; loại exception cụ thể tùy provider |
| Đường dẫn chuyển sang một mount/volume khác | Kết quả truy vấn cũ có thể không còn gắn với nơi tệp mới nằm |
| Ổ đĩa rời bị tháo, network share mất kết nối | Truy vấn metadata hoặc dung lượng có thể thất bại hoặc không còn ý nghĩa |
| Volume được unmount/remount hoặc provider thay đổi trạng thái | FileStore cũ có thể trở nên không còn truy cập được; phải xử lý bằng kiểm tra I/O thực |
| Quyền truy cập, chính sách hệ điều hành hoặc quota thay đổi | Kết quả usable có thể đổi; ghi thực tế có thể bị từ chối |
| File system bị đóng (với provider cho phép đóng) | Thao tác liên quan có thể ném `ClosedFileSystemException` không checked |
| Lỗi lưu trữ hoặc provider | Có thể ném `IOException` mà ứng dụng không dự đoán chính xác subtype |

Tài liệu `Files.getFileStore` nêu rõ một điểm thường bỏ qua: **sau khi lấy được một `FileStore`, việc các thao tác trên đối tượng đó còn phụ thuộc vào sự tồn tại của tệp hay không là chuyện đặc thù implementation**. Đặc biệt, khi tệp **bị xóa hoặc bị di chuyển sang file store khác**, hành vi tiếp theo của `FileStore` cũ **không được API bảo đảm**.

Do đó:

- Không giả định rằng tham chiếu `FileStore` tồn tại lâu sẽ luôn mô tả đúng nơi chứa một `Path` đã bị di chuyển.
- Không giả định rằng `store.getUsableSpace()` sẽ luôn trả số chỉ vì đối tượng `store` từng được lấy thành công.
- Không suy luận một subtype cố định như `NoSuchFileException` là kết quả bắt buộc trên mọi provider.
- Nếu đường dẫn đích có thể thay đổi nơi lưu trữ, **xác định lại file store từ Path đích hiện tại** khi quyết định cần thông tin mới — và vẫn phải xử lý lỗi ở lúc sử dụng.

### `FileStore` không phải một kết nối luôn sống

Đối tượng `FileStore` không phải `AutoCloseable`, không có bước `close()` riêng để “làm mới”. Việc giữ tham chiếu không khóa filesystem và không ngăn thao tác mount/unmount. Muốn biết dung lượng hiện tại, gọi lại các phương thức truy vấn; nếu cần xác định **vùng lưu trữ của một path mới/đã di chuyển**, gọi `Files.getFileStore(path)` lại và tính đến race condition.

## 4. Dung lượng là số liệu động, không phải một lời cam kết

Ba đại lượng quan trọng:

~~~java
long total = store.getTotalSpace();
long unallocated = store.getUnallocatedSpace();
long usable = store.getUsableSpace();
~~~

**`getTotalSpace()`**: tổng dung lượng vùng lưu trữ (byte). Trong thực tế, tổng dung lượng có thể thay đổi khi storage pool, volume, thin provisioning hoặc cấu hình phân vùng thay đổi; không nên coi đây là hằng số vĩnh viễn.

**`getUnallocatedSpace()`**: dung lượng chưa cấp phát tại thời điểm truy vấn. Nó không đồng nghĩa rằng tiến trình hiện tại có quyền sử dụng toàn bộ số byte ấy.

**`getUsableSpace()`**: dung lượng được ước tính là **có thể sử dụng bởi JVM hiện tại**. Đây thường là đại lượng phù hợp hơn để ước lượng khả năng ghi dữ liệu từ ứng dụng, bởi nó có thể phản ánh hạn chế quyền truy cập hoặc điều kiện hệ thống tệp.

Ví dụ khái niệm:

~~~text
Total space       : 10 GiB
Unallocated space :  3 GiB
Usable space      :  2 GiB
~~~

Các số trên chỉ minh họa, không phải kết quả của máy cụ thể. Sự khác nhau có thể đến từ phần dung lượng dành riêng, quota hoặc ràng buộc của provider. **Không bảo đảm rằng usable luôn bằng unallocated.**

### Dùng `long` cho đơn vị byte

Những phương thức dung lượng trên trả `long`, vì số byte có thể vượt quá giới hạn `int`. Khi cần đổi đơn vị để hiển thị:

~~~java
long usableBytes = store.getUsableSpace();
double gib = usableBytes / (1024.0 * 1024 * 1024);
System.out.printf(java.util.Locale.ROOT, "usable GiB: %.2f%n", gib);
~~~

Nếu dùng phép chia số nguyên, hãy chấp nhận nó bỏ phần thập phân; khi định dạng số để máy đọc, cố định `Locale` nếu yêu cầu định dạng dấu thập phân nhất quán.

### Các lần đọc liên tiếp không tạo một snapshot nguyên tử

~~~java
long total = store.getTotalSpace();
long usable = store.getUsableSpace();
long unallocated = store.getUnallocatedSpace();
~~~

Ba biến là kết quả của **ba lời gọi riêng biệt**. Giữa các lời gọi, tiến trình khác có thể ghi/xóa dữ liệu hoặc trạng thái file store có thể đổi. Đừng coi ba số đó là một snapshot nguyên tử của toàn bộ hệ thống tệp tại một thời điểm duy nhất.

Khi tính `used = total - unallocated` để hiển thị dashboard, hiểu đây là **ước lượng từ các phép đo ở những thời điểm có thể hơi khác nhau**. Với dữ liệu thay đổi hoặc provider đặc thù, những phép tính tổng hợp có thể không khớp hoàn toàn như kỳ vọng. Không biến sai lệch tức thời thành khẳng định hệ thống tệp bị hỏng.

## 5. Giá trị `getUsableSpace()` chỉ là gợi ý

Javadoc của `FileStore.getUsableSpace()` nói rõ: số byte trả về là **hint**, không phải bảo đảm rằng bạn có thể dùng hết hoặc một phần số byte đó. Thông tin thường chính xác nhất **ngay sau lúc truy vấn** và có thể trở nên không còn đúng do thao tác I/O từ chính JVM này hoặc từ hệ thống bên ngoài.

Ví dụ lỗi tư duy:

~~~java
long available = store.getUsableSpace();
if (available >= uploadSize) {
    // Sai nếu kết luận Files.write(...) chắc chắn thành công.
}
~~~

Giữa lúc kiểm tra và ghi:

- Tiến trình khác có thể dùng mất dung lượng.
- Quota của người dùng/container có thể thay đổi hoặc đã gần giới hạn.
- Đích có thể đã chuyển sang vùng lưu trữ khác.
- File system có thể chuyển sang read-only, mất kết nối hoặc gặp lỗi ghi.
- Metadata, journal, block allocation, replication hoặc cấu hình provider có thể làm lượng cần ghi khác ước lượng `uploadSize`.

**Hệ quả:** kiểm tra trước khi ghi chỉ là **preflight về khả năng**, không phải một phép “giữ chỗ dung lượng” và không thay thế việc bắt `IOException` trong thao tác ghi thật.

### TOCTOU: kiểm tra trước, dùng sau

Đây là một dạng lỗi **time-of-check to time-of-use**:

~~~text
T0: Files.getFileStore(targetDir)
T1: store.getUsableSpace() -> 500 MiB
T2: một tiến trình khác ghi 480 MiB, hoặc mount/permission thay đổi
T3: ứng dụng thử ghi tệp 100 MiB
T4: thao tác ghi có thể thất bại dù preflight từng báo “đủ chỗ”
~~~

Các con số là mô phỏng. Không cần cố gắng “đo lại nhiều lần cho đến khi chắc chắn” vì một phép đo mới cũng chỉ phản ánh một thời điểm. Điều quan trọng là xử lý lỗi ngay **tại thao tác sử dụng tài nguyên**.

## 6. `isReadOnly()` cũng không cam kết ghi thành công

`store.isReadOnly()` cho biết file store có được báo là chỉ đọc hay không:

~~~java
boolean readOnly = store.isReadOnly();
~~~

Nếu báo `true`, các thao tác tạo/sửa tệp trên vùng lưu trữ đó không được hỗ trợ theo hợp đồng. Nếu báo `false`, **không thể** kết luận rằng:

- Tiến trình hiện tại có quyền ghi vào mọi thư mục.
- Mọi tệp trong vùng đều cho phép thay đổi.
- Quota còn đủ.
- Không có lỗi thiết bị hoặc mạng.
- Trạng thái sẽ giữ nguyên đến lúc ghi thật.

Vì vậy việc kiểm tra:

~~~java
if (!store.isReadOnly() && store.getUsableSpace() > neededBytes) {
    // Chỉ có thể xem là điều kiện sơ bộ, không phải bảo đảm.
}
~~~

vẫn đòi hỏi `try/catch IOException` quanh thao tác ghi. `isReadOnly()` **không khai báo checked `IOException`**, nhưng một số vấn đề trạng thái/provider vẫn có thể biểu hiện ở các thao tác I/O sau đó.

## 7. `getBlockSize()` của Java 10: lỗi khác với I/O thông thường

`FileStore.getBlockSize()` được bổ sung ở **Java 10**. Kết quả là kích thước block của vùng lưu trữ, tính bằng byte, nếu provider cung cấp thông tin.

~~~java
try {
    long bytesPerBlock = store.getBlockSize();
    System.out.println("block size = " + bytesPerBlock);
} catch (UnsupportedOperationException ex) {
    System.out.println("Provider không cung cấp kích thước block");
} catch (IOException ex) {
    System.out.println("Truy vấn block size bị lỗi I/O");
}
~~~

**Sự khác biệt cần nhớ:**

- `UnsupportedOperationException`: tính năng này không được provider hỗ trợ.
- `IOException`: lỗi thực tế khi truy vấn I/O.
- `getBlockSize()` không phải số byte của một tệp, cũng không phải dung lượng còn trống.
- Kích thước block không tự chứng minh rằng hệ thống đủ chỗ cho tệp cần ghi, vì phân bổ thực tế, metadata và quota có thể khác nhau.

Nếu đây chỉ là số liệu hiển thị phụ, một ứng dụng có thể báo **“không hỗ trợ”** và tiếp tục các chức năng chính. Nếu đo lường này là điều kiện bắt buộc của một phép tính, hãy báo lỗi rõ ràng, không ngầm dùng một block size mặc định rồi coi là đã đo được.

## 8. Chương trình Java 17+ mô phỏng thay đổi và `IOException`

Các chỉ số từ ổ đĩa thật không có stdout cố định; chúng phụ thuộc hệ thống. Vì vậy, để kiểm chứng chính xác thứ tự lỗi và giá trị, ta tạo một **FileStore giả lập trong bộ nhớ phục vụ bài học**, không đụng tới ổ đĩa hay tháo mount thật.

- Lần 1 hỏi `getUsableSpace()`: 1200 byte.
- Lần 2: 900 byte (giá trị thay đổi).
- Lần 3: ném `IOException`, mô phỏng provider không thể trả lời.
- `getBlockSize()` không được override: dùng hợp đồng mặc định của lớp `FileStore`, ném `UnsupportedOperationException`.

Lưu vào tệp **FileStoreDriftDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;

public class FileStoreDriftDemo {
    static final class ChangingStore extends FileStore {
        private int reads;

        @Override
        public String name() {
            return "sample";
        }

        @Override
        public String type() {
            return "demo";
        }

        @Override
        public boolean isReadOnly() {
            return false;
        }

        @Override
        public long getTotalSpace() throws IOException {
            return 4096;
        }

        @Override
        public long getUnallocatedSpace() throws IOException {
            return 2048;
        }

        @Override
        public long getUsableSpace() throws IOException {
            ++reads;
            if (reads == 1) {
                return 1200;
            }
            if (reads == 2) {
                return 900;
            }
            throw new IOException("store unavailable");
        }

        @Override
        public boolean supportsFileAttributeView(
                Class<? extends FileAttributeView> type) {
            return false;
        }

        @Override
        public boolean supportsFileAttributeView(String name) {
            return false;
        }

        @Override
        public <V extends FileStoreAttributeView> V getFileStoreAttributeView(
                Class<V> type) {
            return null;
        }

        @Override
        public Object getAttribute(String attribute) throws IOException {
            throw new UnsupportedOperationException("not supported");
        }

        // Không override getBlockSize():
        // FileStore.getBlockSize() mặc định ném UnsupportedOperationException.
    }

    public static void main(String[] args) throws IOException {
        FileStore store = new ChangingStore();

        System.out.println(
                "store: " + store.name() + " (" + store.type() + ")"
        );
        System.out.println("total: " + store.getTotalSpace());
        System.out.println("unallocated: " + store.getUnallocatedSpace());
        System.out.println("first usable: " + store.getUsableSpace());
        System.out.println("second usable: " + store.getUsableSpace());

        try {
            store.getUsableSpace();
        } catch (IOException ex) {
            System.out.println("third usable: IOException");
        }

        try {
            store.getBlockSize();
        } catch (UnsupportedOperationException ex) {
            System.out.println("block size: UnsupportedOperationException");
        }

        System.out.println("read only: " + store.isReadOnly());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FileStoreDriftDemo.java
java FileStoreDriftDemo
~~~

**Stdout chính xác:**

~~~text
store: sample (demo)
total: 4096
unallocated: 2048
first usable: 1200
second usable: 900
third usable: IOException
block size: UnsupportedOperationException
read only: false
~~~

**Phân tích:**

1. `FileStore` là một lớp trừu tượng, nên bài thử tạo `ChangingStore` để kiểm soát kết quả, không gọi hệ thống tệp thật.
2. `getTotalSpace()` và `getUnallocatedSpace()` trả những con số cố định cho ví dụ.
3. Hai lần đọc usable không bằng nhau; điều này minh họa rằng một kết quả cũ không thể là giá trị hiện thời cho lần truy vấn sau.
4. Lần đọc thứ ba mô phỏng `IOException`. Không có giá trị `long` hợp lệ nào trả về từ lời gọi lỗi.
5. `getBlockSize()` phát sinh `UnsupportedOperationException` vì implementation giả lập kế thừa phương thức mặc định từ `FileStore`. Đây **không phải** tình huống đầy đĩa hoặc hết quota.
6. `isReadOnly() == false` không thể chứng minh hoạt động ghi thực tế thành công; bài thử còn cố ý cho thấy các truy vấn khác vẫn có thể lỗi.

Đây là **mô phỏng deterministic** để học API và xử lý lỗi; trên hệ thống thật, số byte, loại ngoại lệ cụ thể và thời điểm lỗi phụ thuộc provider. Không cần và không nên phá kết nối ổ đĩa thật để kiểm thử.

## 9. Đọc `FileStore` thật: kết quả phụ thuộc máy, không có stdout cố định

Đoạn sau cho biết cách thu thập số liệu thực trên thư mục đang tồn tại. Đây là một **chương trình độc lập khác**, không phải phần bổ sung trực tiếp vào chương trình mô phỏng ở mục 8.

Lưu thành tệp **FileStoreInspection.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileStoreInspection {
    public static void main(String[] args) {
        Path path = Path.of(".").toAbsolutePath().normalize();

        try {
            FileStore store = Files.getFileStore(path);

            System.out.println("store: " + store.name());
            System.out.println("type: " + store.type());
            System.out.println("readOnly: " + store.isReadOnly());
            System.out.println("total bytes: " + store.getTotalSpace());
            System.out.println("usable bytes: " + store.getUsableSpace());
            System.out.println("unallocated bytes: "
                    + store.getUnallocatedSpace());

            try {
                System.out.println("block bytes: " + store.getBlockSize());
            } catch (UnsupportedOperationException ex) {
                System.out.println("block bytes: unsupported");
            }
        } catch (IOException ex) {
            System.err.println(
                    "FileStore query failed: " + ex.getClass().getSimpleName()
            );
        }
    }
}
~~~

Chạy:

~~~bash
javac FileStoreInspection.java
java FileStoreInspection
~~~

**Không công bố một stdout số cố định** cho chương trình này. Tên store, loại filesystem, tổng dung lượng, usable/unallocated bytes và hỗ trợ block size phụ thuộc vào máy, container, mount và provider. Nếu có lỗi truy vấn, chương trình in tên loại `IOException` quan sát được. Với yêu cầu production, cần ghi log đầy đủ hơn (đường dẫn, thao tác, exception/cause và thời điểm), nhưng tránh tiết lộ đường dẫn nhạy cảm cho người dùng không được phép xem.

## 10. Không coi một lần đọc `FileStore` là kiểm tra ghi thành công

Một flow upload thường cần ước lượng dung lượng trước khi nhận dữ liệu lớn:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

static boolean likelyEnoughSpace(
        Path existingTargetDirectory, long bytesNeeded, long reserveBytes)
        throws IOException {

    if (bytesNeeded < 0 || reserveBytes < 0) {
        throw new IllegalArgumentException("negative size");
    }

    FileStore store = Files.getFileStore(existingTargetDirectory);
    long usable = store.getUsableSpace();

    // Tránh cộng bytesNeeded + reserveBytes gây tràn long.
    return usable >= bytesNeeded
            && usable - bytesNeeded >= reserveBytes;
}
~~~

Đây là **phương thức minh họa nằm trong một class**, không phải chương trình riêng. Kết quả `true` chỉ có nghĩa rằng **theo ước lượng tại thời điểm truy vấn**, ứng dụng có vẻ đủ dung lượng để thực hiện tác vụ, sau khi trừ một biên dự phòng. Nó **không phải giấy phép ghi chắc chắn thành công**.

Khi ghi thật:

~~~java
// Minh họa trong phương thức; target và bytes đã được chuẩn bị.
try {
    Files.write(target, bytes);
} catch (IOException ex) {
    // Báo lỗi ghi, xử lý tệp dở dang/cleanup theo hợp đồng nghiệp vụ.
    throw ex;
}
~~~

Bất kể kiểm tra preflight ra sao, `Files.write` vẫn có thể ném `IOException`. Với luồng ghi lớn, ứng dụng có thể đã ghi được **một phần** trước khi lỗi xuất hiện. Cần thiết kế quá trình xử lý tệp tạm, cleanup, kiểm tra checksum/độ dài và công bố kết quả theo nhu cầu, không chỉ kiểm tra dung lượng rồi giả định không thể lỗi.

### Lưu ý khi đích chưa tồn tại

`Files.getFileStore(path)` hỏi vùng lưu trữ **nơi tệp/đường dẫn tồn tại**. Nếu đường dẫn tệp cần tạo **chưa có**, hãy truy vấn một **thư mục cha đã tồn tại** và thật sự là nơi dự kiến ghi. Đừng luôn gọi `Files.getFileStore(newFilePath)` rồi dựa vào kết quả cho path chưa tồn tại; provider có thể ném `IOException`.

Nếu đường dẫn qua symlink, bị đổi thư mục, hoặc mount thay đổi, kết quả trên thư mục cha tại T0 vẫn không bảo đảm đường dẫn đích khi sử dụng T1 là cùng một file store. Việc giải quyết hoàn toàn các race condition về path cần thiết kế truy cập tệp/định danh đường dẫn an toàn theo nền tảng, không chỉ gọi lại `getFileStore`.

## 11. Khi nào nên truy vấn lại, khi nào không nên retry?

Một chiến lược tốt phân biệt **đọc metadata để hiển thị** và **thao tác ghi dữ liệu có hậu quả**.

### Hiển thị trạng thái dung lượng

- Thu thập theo chu kỳ phù hợp, **gắn thời điểm đo**.
- Khi `getUsableSpace()` ném `IOException`, hiển thị “không lấy được số liệu” / “unknown” kèm lỗi chẩn đoán trong log, **không đổi thành `0 bytes`**.
- Không tiếp tục hiển thị kết quả cũ như thể vừa đo được; nếu giữ số cũ, đánh dấu rõ **stale** và thời điểm cuối cùng thành công.
- Với file store biến mất hoặc không truy cập được, cân nhắc tái khám phá từ path, không chỉ gọi mãi trên cùng đối tượng cũ.
- Tránh polling quá dày gây thêm tải hoặc spam log khi storage/network đang có sự cố.

### Truy vấn lỗi `IOException`: có nên retry?

Có thể retry **hữu hạn, có delay/backoff** khi lỗi có khả năng tạm thời (ví dụ network filesystem chập chờn), nhưng cần:

1. Đảm bảo thao tác đọc metadata an toàn để thử lại.
2. Kiểm tra nguồn/path vẫn là đối tượng mục tiêu.
3. Giới hạn số lần và thời gian chờ; hỗ trợ cancel khi phù hợp.
4. Không che lỗi liên tục bằng vòng lặp vô hạn.
5. Phân biệt lỗi không hỗ trợ tính năng (`UnsupportedOperationException`) với lỗi I/O tạm thời: retry không thể tự biến một API không được provider hỗ trợ thành được hỗ trợ.

Khi retry **thao tác ghi**, yêu cầu khó hơn: nếu lần ghi trước đã tạo nội dung một phần, cần chiến lược đảm bảo idempotency hoặc cleanup trước khi thử lại; không tự động lặp ghi mà không hiểu trạng thái đích.

## 12. Liệt kê tất cả FileStore: không phải một danh sách bất biến

Ngoài việc truy vấn `FileStore` theo `Path`, có thể duyệt:

~~~java
import java.nio.file.FileStore;
import java.nio.file.FileSystems;

for (FileStore store : FileSystems.getDefault().getFileStores()) {
    try {
        System.out.println(store.name() + ": "
                + store.getUsableSpace() + " bytes");
    } catch (IOException ex) {
        System.err.println("Cannot query store: " + store.name());
    }
}
~~~

Đây là đoạn minh họa trong một phương thức. Theo hợp đồng của `FileSystem.getFileStores()`:

- Thứ tự file store **không được bảo đảm**.
- Danh sách có thể thay đổi trong vòng đời JVM do mount, unmount, thiết bị rời hoặc provider.
- Khi một store không thể truy cập vì lỗi I/O, **iterator có thể bỏ qua store đó** thay vì nhất thiết ném `IOException` trong vòng lặp.
- Ngay cả store đã được liệt kê, một lần gọi `getUsableSpace()` sau đó vẫn có thể ném `IOException`.

Vì vậy, “không thấy store trong kết quả liệt kê” **không chứng minh chắc chắn** thiết bị không tồn tại. Cũng không coi tập được liệt kê một lần là inventory đầy đủ và cố định cho mọi thời điểm.

Nếu cần biết vùng lưu trữ của **một đường dẫn cụ thể**, `Files.getFileStore(path)` thường sát mục đích hơn việc dựa vào tên store tìm thấy trong danh sách.

## 13. Theo dõi, ghi log và xử lý lỗi có thể hành động

Một thông báo lỗi tốt nên phân biệt:

| Trạng thái | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| `OK` | Đọc được số liệu tại thời điểm đo | Dùng số liệu để hiển thị / đánh giá sơ bộ |
| `IO_ERROR` | Không truy vấn được một thuộc tính | Log thao tác và cause; không dùng giá trị giả |
| `UNSUPPORTED` | Provider không hỗ trợ thuộc tính phụ, ví dụ block size | Ẩn chỉ số phụ hoặc báo “not available” |
| `STALE` | Chỉ còn giá trị đã đo trước đây | Hiển thị timestamp, thử làm mới có kiểm soát |
| `READ_ONLY` | File store báo chỉ đọc | Không lên kế hoạch ghi; vẫn cần xử lý các lỗi khác |
| `WRITE_FAILED` | Thao tác ghi thực tế thất bại | Xử lý cleanup/trạng thái giao dịch, thông báo lỗi |

Một kiến trúc đo lường thường tách **kết quả đo** khỏi **lỗi truy vấn**, chẳng hạn dữ liệu có các trường `measuredAt`, `totalBytes`, `usableBytes`, `unallocatedBytes`, `status`, `errorType`. Nếu một phép đo thất bại, không tạo một bản ghi có `usableBytes=0` mà không ghi rõ đó là giá trị chưa đo được.

Khi thu thập trong môi trường container, NAS hoặc network share, điều kiện/quota thực tế của tiến trình có thể khác với hình dung về “free disk toàn máy”. Hãy dựa vào đại lượng mô tả **khả năng sử dụng bởi JVM** và vẫn đánh giá thao tác ghi thật.

### FileStore có luôn cần query lại mọi lần đọc giao diện?

Không nhất thiết. Dashboard có thể lưu cache trong một khoảng ngắn kèm thời điểm; nhưng việc cache là quyết định về **độ tươi dữ liệu**, không biến giá trị thành bất biến. Với quyết định nhạy cảm như chuẩn bị một upload lớn, nên lấy đo gần thời điểm sử dụng nhất có thể mà không nhầm nó với một bảo đảm ghi.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
| --- | --- | --- |
| “Đã lấy được FileStore thì lần sau query chắc chắn không lỗi.” | Lưu trữ, đường dẫn và provider có thể thay đổi. | Bắt `IOException` khi truy vấn lại. |
| “`getUsableSpace` là số byte được đặt trước cho ứng dụng.” | Chỉ là ước lượng/hint hiện tại. | Vẫn bắt lỗi trong thao tác ghi thật. |
| “`total`, `usable`, `unallocated` là snapshot nguyên tử.” | Ba lời gọi xảy ra ở thời điểm khác nhau. | Hiển thị là số liệu đo, không khẳng định bất biến đồng thời. |
| “`getUnallocatedSpace` chính là số byte tôi được phép ghi.” | Không nhất thiết, vì quota/quyền/giới hạn. | Dùng `getUsableSpace` để tham khảo khả năng ghi của JVM. |
| “`isReadOnly() == false` nghĩa là mọi lần ghi sẽ thành công.” | Quyền thư mục, quota và lỗi I/O vẫn có thể cản trở. | Thử ghi và xử lý `IOException`. |
| “`getBlockSize` Java 10 luôn được hỗ trợ.” | Mặc định có thể ném `UnsupportedOperationException`. | Có fallback / báo không hỗ trợ. |
| “Một path đã di chuyển vẫn gắn với FileStore cũ chính xác.” | Javadoc không bảo đảm hành vi sau khi xóa hoặc chuyển sang store khác. | Lấy lại FileStore theo path hiện tại khi cần. |
| “File store không có trong danh sách nghĩa là không tồn tại.” | Iterator có thể bỏ qua store không truy cập được. | Dùng nguồn xác thực phù hợp, có trạng thái unknown. |
| “Khi query lỗi, giá trị free bằng 0.” | Lỗi truy vấn là **không biết**, không phải có 0 byte. | Tách metric khỏi status/error. |
| “Retry đến khi hết IOException là an toàn.” | Không đúng với mọi lỗi; có thể treo luồng và che sự cố. | Retry hữu hạn, backoff, cảnh báo. |
| “Preflight free-space đủ thì có thể bỏ try/catch quanh ghi.” | TOCTOU khiến thao tác ghi vẫn thất bại. | Bắt lỗi tại điểm thực hiện và xử lý tệp dở dang. |
| “Tên/type FileStore dùng để nhận diện volume trên mọi OS.” | `name()`, `type()` mang tính provider-specific. | Dùng path/provider và metadata phù hợp thay vì hard-code. |

## 15. Tự kiểm tra

### Bài 1 — ba lần đo

Giả sử cùng một `FileStore` lần lượt trả `getUsableSpace()` như sau: `1000L`, `700L`, rồi ném `IOException`.

- A. Có được cache `1000` và khẳng định đó là dung lượng hiện tại ở lần thứ ba không?
- B. Nên ghi nhận gì khi truy vấn thứ ba thất bại?
- C. Nếu cần tạo tệp 500 byte và lần đo thứ hai trả 700 byte, có thể đảm bảo ghi thành công không?

**Đáp án:** A = không, số liệu có thể thay đổi; B = trạng thái không thể truy vấn, có thể giữ số đo cũ **kèm nhãn stale/timestamp**; C = không, vì có TOCTOU, quota và lỗi I/O khác.

### Bài 2 — loại ngoại lệ

~~~java
try {
    long block = store.getBlockSize();
} catch (UnsupportedOperationException ex) {
    // ?
} catch (IOException ex) {
    // ?
}
~~~

**Đáp án:** nhánh đầu xử lý **provider không hỗ trợ thuộc tính block size**; nhánh thứ hai xử lý **lỗi I/O** khi truy vấn. Hai trạng thái không nên được đồng nhất.

### Bài 3 — tệp đã chuyển sang volume khác

Một ứng dụng lấy `FileStore a = Files.getFileStore(path)`, sau đó tiến trình khác chuyển tệp được chỉ bởi `path` sang vùng lưu trữ khác. Có thể tin rằng mọi thao tác trên `a` vẫn mô tả đúng vị trí mới của tệp không?

**Đáp án:** không. Hành vi sau khi đường dẫn bị xóa hoặc chuyển sang một file store khác là **implementation-specific/không được bảo đảm** theo Javadoc. Nếu cần thông tin ở vị trí mới, phải xác định lại từ path hiện tại và xử lý lỗi/race condition.

### Bài 4 — liệt kê store

`FileSystems.getDefault().getFileStores()` trả hai store. Trước đó dashboard hiển thị ba store. Có đủ bằng chứng kết luận store thứ ba đã bị xóa hoàn toàn không?

**Đáp án:** không. File store có thể thay đổi trong vòng đời JVM; iterator có thể bỏ qua store không truy cập được do lỗi I/O. Cần đối chiếu bằng nguồn dữ liệu và trạng thái truy vấn phù hợp.

### Bài 5 — cần ước lượng trước upload

Khi `getUsableSpace()` báo đủ chỗ để ghi, mã ứng dụng nên làm gì tiếp theo?

**Đáp án:** có thể tiếp tục thao tác **nếu các điều kiện nghiệp vụ khác đã hợp lệ**, nhưng vẫn phải bắt lỗi trong lúc thực sự ghi dữ liệu và xử lý cleanup/partial output. Số liệu FileStore chỉ hỗ trợ quyết định sơ bộ, không cấp phát/quyền ghi hoặc giữ chỗ dung lượng.

## 16. Ghi nhớ và tài liệu chính thức

- `Files.getFileStore(Path)` và các phương thức dung lượng của `FileStore` có thể ném **checked `IOException`**.
- `FileStore.getBlockSize()` có từ **Java 10**; ngoài `IOException` còn phải tính tới `UnsupportedOperationException` khi không được hỗ trợ.
- `getUsableSpace()` và `getUnallocatedSpace()` là **số liệu động/hint**, có thể nhanh chóng cũ đi do hoạt động I/O khác; không thể bảo đảm thao tác ghi thành công.
- `getTotalSpace()` là tổng byte của file store tại thời điểm truy vấn; không nên xem hệ thống tệp là bất biến.
- Khi path bị xóa hoặc chuyển sang store khác, hành vi của đối tượng `FileStore` cũ **không được cam kết**.
- `FileSystem.getFileStores()` không có thứ tự cố định, có thể thay đổi theo mount và có thể bỏ qua store không truy cập được.
- Kiểm tra dung lượng trước khi ghi **không thay thế** xử lý lỗi I/O tại lần ghi thật.
- Khi truy vấn thất bại, phân biệt **UNKNOWN/IO_ERROR** với “0 byte còn trống”; khi dữ liệu cũ được dùng, ghi nhãn stale và thời điểm đo.
- Thiết kế retry hữu hạn, có giới hạn và kiểm tra tác động của việc thử lại, nhất là với thao tác ghi có thể tạo tệp dở dang.

Các tài liệu chuẩn hiện hành:

- [Java SE 17 — `FileStore`, `getTotalSpace`, `getUsableSpace`, `getUnallocatedSpace`, `getBlockSize`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [Java SE 25 — `FileStore`, hợp đồng `IOException` và dung lượng động](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html)
- [Java SE 17 — `Files.getFileStore(Path)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path))
- [Java SE 17 — `FileSystem.getFileStores()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getFileStores())
- [Java SE 17 — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html)

**Kết luận:** `FileStore` giúp **quan sát** trạng thái lưu trữ, không khóa trạng thái đó và không bảo đảm kết quả ghi trong tương lai. Muốn code an toàn, hãy xử lý `IOException`, phân biệt API không được hỗ trợ, chấp nhận số liệu có thể cũ và luôn bắt lỗi tại **thao tác tệp thực tế**.
