# Phân biệt tính bền dữ liệu với tính nguyên tử và đồng bộ giữa các luồng khi ánh xạ NVM trong Java

## 1. Ba tính chất khác nhau, không được dùng thay cho nhau

Với Java NIO, một tệp có thể được ánh xạ vào không gian địa chỉ tiến trình qua `FileChannel.map(...)`, rồi truy cập như một `MappedByteBuffer`. Khi tệp nằm trên vùng nhớ không mất dữ liệu khi mất nguồn điện (*non-volatile memory*, NVM) và nền tảng hỗ trợ các chế độ ánh xạ thích hợp, chương trình có thể yêu cầu các thay đổi được ghi bền vững.

Tuy nhiên, **ghi được dữ liệu xuống thiết bị không đồng nghĩa thao tác ghi là nguyên tử; thao tác nguyên tử cũng không đồng nghĩa các luồng được đồng bộ; và đồng bộ các luồng không đồng nghĩa dữ liệu đã bền vững qua sự cố**.

Ba khái niệm phải tách ra:

| Tính chất | Câu hỏi nó trả lời | Ví dụ cơ chế | Nó **không** bảo đảm |
| --- | --- | --- | --- |
| **Durability – tính bền dữ liệu** | Sau khi thao tác ghi đã được xác nhận, dữ liệu có được ghi vào storage phù hợp thay vì chỉ nằm ở cache dễ mất? | `MappedByteBuffer.force()`/`force(index,length)` trên mapping hỗ trợ; chính sách flush và thiết bị phù hợp | Nhiều trường cập nhật cùng lúc theo nguyên tắc all-or-nothing |
| **Atomicity – tính nguyên tử** | Một phép cập nhật có xuất hiện như **một đơn vị không thể chia** đối với quan sát hoặc phục hồi không? | Atomic primitive trong phạm vi bảo đảm thích hợp; giao thức transaction/WAL/copy-on-write cho nhiều byte/trường | Các byte đã được đẩy tới NVM sau sự cố |
| **Synchronization/visibility – đồng bộ và khả kiến** | Các thread/process phối hợp, thấy thứ tự và trạng thái dữ liệu nào? | `synchronized`, `Lock`, thao tác acquire/release, giao thức `FileLock` liên tiến trình | Dữ liệu đã được flush bền vững hoặc transaction an toàn khi crash |

**Thông điệp cốt lõi:** `force()` là thao tác **persistence**, không phải `synchronized`, không phải một transaction, cũng không phải lệnh biến hai lần `putInt` thành một lần cập nhật nguyên tử.

Bài học đặt trong ngữ cảnh **“Ánh xạ NVM” của Java 14**. JEP 352 (*Non-Volatile Mapped Byte Buffers*) giới thiệu các mode ánh xạ chuyên biệt từ Java 14; API `MappedByteBuffer` và `jdk.nio.mapmode.ExtendedMapMode` vẫn hiện diện ở Java hiện đại. Các chương trình mẫu dùng **Java 17+ ổn định**, không dùng preview/legacy.

## 2. NVM, memory mapping và phạm vi của lời hứa persistence

### 2.1. Mapping là gì?

Với `FileChannel.map(...)`, một vùng của tệp được ánh xạ thành vùng nhớ mà Java có thể đọc/ghi qua `MappedByteBuffer`:

```java
// Đoạn đặt trong phương thức; channel là FileChannel mở READ/WRITE.
MappedByteBuffer map =
        channel.map(FileChannel.MapMode.READ_WRITE, 0, 4096);

map.putInt(0, 42);
map.force(0, Integer.BYTES);
```

Hai API quan trọng:

- `putInt(0, 42)`: sửa **nội dung mapping** tại offset 0. Không có cam kết rằng ngay lúc lệnh trở về, mọi byte đã nằm trên thiết bị bền vững.
- `force(0, Integer.BYTES)`: yêu cầu các thay đổi thuộc vùng mapping đó được ghi xuống thiết bị theo hợp đồng của API và mode ánh xạ.

Đây là đoạn minh họa trên một vùng mapped file. Nó **không chứng minh** `putInt` là atomic, và không cho phép bỏ qua quản lý đồng thời nếu có nhiều thread dùng cùng buffer.

### 2.2. Các mode ánh xạ

| Mode | Ý nghĩa | Lưu ý về persistence |
| --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | Đọc vùng tệp | Không cho ghi; `force` không dùng để ghi |
| `FileChannel.MapMode.READ_WRITE` | Đọc/ghi vùng tệp thông thường | Có thể dùng `MappedByteBuffer.force` để đẩy thay đổi tới storage |
| `FileChannel.MapMode.PRIVATE` | Mapping riêng, copy-on-write | Thay đổi riêng không được lan truyền vào file nguồn như một shared writable mapping |
| `ExtendedMapMode.READ_ONLY_SYNC` | Chế độ read-only chuyên biệt cho non-volatile RAM | Yêu cầu nền tảng/file system hỗ trợ |
| `ExtendedMapMode.READ_WRITE_SYNC` | Chế độ read/write chuyên biệt cho non-volatile RAM | `force` dùng cơ chế cache-line writeback trên implementation hỗ trợ |

Hai hằng `ExtendedMapMode` nằm trong **module JDK `jdk.nio.mapmode`**, không phải trong `FileChannel.MapMode` chuẩn. Chúng vẫn là API hiện hành nhưng mang tính **phụ thuộc JDK và nền tảng**. Trên Linux, triển khai sử dụng các tùy chọn `MAP_SYNC`/`MAP_SHARED_VALIDATE` của `mmap` khi ánh xạ tệp thích hợp.

**Không phải SSD, ổ NVMe hoặc filesystem bình thường nào cũng là DAX/NVM mapping hợp lệ.** Một ổ lưu trữ có độ bền dữ liệu tốt không có nghĩa `READ_WRITE_SYNC` được hỗ trợ. Chỉ sử dụng mode này khi OS, hardware, filesystem và runtime đáp ứng yêu cầu; nếu không, lệnh ánh xạ có thể thất bại, ví dụ `UnsupportedOperationException`.

### 2.3. `force()` bảo đảm chính xác điều gì?

Theo hợp đồng `MappedByteBuffer.force` với mapping read/write thông thường:

- Đối với **tệp trên thiết bị lưu trữ cục bộ**, khi `force()` trả về thành công, thay đổi thuộc phạm vi buffer được yêu cầu đã được ghi tới thiết bị theo bảo đảm API.
- Đối với **tệp không ở thiết bị cục bộ**, API không đưa ra cùng bảo đảm đó.
- `force(index, length)` áp dụng cho một vùng; triển khai **có thể flush thêm byte nằm ngoài vùng**, do granularity của thiết bị.
- Với mapping read-only hoặc private, gọi `force` có thể không có tác dụng; với mode chuyên biệt, hành vi còn phụ thuộc mode/implementation.
- Nếu có lỗi ghi, API có thể ném ngoại lệ như `UncheckedIOException`. Không nuốt lỗi rồi đánh dấu thao tác ghi là thành công.

Đối với `READ_WRITE_SYNC` trên NVM thực sự, tài liệu `ExtendedMapMode` giải thích đường `force` dùng **cache-line writeback** thay vì flush theo kiểu tệp/thành phần block device. Đây là một khác biệt kỹ thuật về persistence, **không** phải lời hứa transaction.

**Giới hạn rất quan trọng:** bảo đảm lưu bền của storage còn phụ thuộc hợp đồng OS, driver, filesystem, phần cứng, tính đúng đắn của cache/flush và cách chống mất điện của thiết bị. API Java không cung cấp một transaction engine hay cơ chế phục hồi dữ liệu đa trường chỉ qua một lời gọi `force`.

## 3. Vì sao bền dữ liệu không đồng nghĩa nguyên tử?

Giả sử một bản ghi được mã hóa thành **hai trường 32-bit**:

```text
offset 0..3: balance
offset 4..7: checksum hoặc một giá trị phụ thuộc balance
```

Chương trình muốn chuyển trạng thái từ `(100, -100)` sang `(200, -200)`:

```java
map.putInt(0, 200);  // Ghi trường 1
map.putInt(4, -200); // Ghi trường 2
map.force(0, 8);     // Yêu cầu ghi bền vùng này
```

**Đây không phải giao dịch nguyên tử**. Hãy xét thời điểm crash:

1. **Trước lần ghi thứ nhất:** file có thể còn trạng thái cũ.
2. **Giữa hai lần ghi:** chương trình đã thay đổi `balance` nhưng chưa sửa giá trị phụ thuộc.
3. **Sau cả hai lần ghi nhưng trước `force` hoàn tất:** một phần, toàn bộ hoặc chưa phần nào của thay đổi có thể đã được đẩy xuống storage; không được suy luận về kết quả crash từ tiến trình bình thường.
4. **Sau `force` trả về thành công trên mapping/tệp cục bộ thuộc điều kiện hợp đồng:** yêu cầu durability đã được thực hiện đối với vùng được flush. Nhưng điều này **không làm hai câu lệnh ghi trở thành all-or-nothing** khi một luồng khác có thể quan sát giữa các lệnh hoặc khi crash xảy ra giữa chuỗi cập nhật.

Mệnh đề `force(0, 8)` **không** thay thế cơ chế commit transaction. Cũng không thể giả định `putInt` đơn lẻ luôn là một thao tác ghi nguyên tử ở mức storage/NVM chỉ vì Java có kiểu `int`.

### “Atomic” ở cấp nào?

Một câu hỏi “ghi có atomic không?” phải chỉ rõ **đối tượng quan sát**:

- **Atomic đối với các Java thread còn sống?** Có thể dùng lock chung bao quanh cả hai trường; chỉ những thread tuân thủ lock đó mới thấy một trạng thái nhất quán.
- **Atomic đối với một primitive/truy cập bộ nhớ?** Phụ thuộc API, kích thước, alignment, access mode và nền tảng. Không suy rộng bảo đảm của `AtomicInteger` hay `VarHandle` sang mọi `MappedByteBuffer.putInt`/`putLong`.
- **Atomic qua sự cố mất điện/crash?** Cần protocol lưu trữ và recovery được thiết kế, kiểm tra; một chuỗi byte writes và `force` không tự tạo được all-or-nothing.

**Tính nguyên tử của “từng phép gán” khác tính nguyên tử của “một bản ghi gồm nhiều trường”.** Ngay cả khi từng write riêng lẻ có tính nguyên tử trong một bối cảnh được định nghĩa, một giao dịch gồm hai write vẫn có thể để lộ trạng thái giữa chừng.

## 4. Đồng bộ giữa các thread là một trục khác

### 4.1. `MappedByteBuffer` không tự động thread-safe

Tài liệu Java NIO nêu rõ các `Buffer` **không an toàn cho nhiều thread sử dụng đồng thời** nếu không được điều phối. Chúng có cả trạng thái vị trí (`position`), giới hạn (`limit`), mark và vùng dữ liệu chia sẻ.

```java
// Cố ý minh họa lỗi: nhiều thread dùng chung buffer mà không phối hợp.
int current = map.getInt(0);
map.putInt(0, current + 1);
```

Hai thread có thể cùng đọc giá trị `5`, rồi đều ghi `6`: một lượt tăng bị mất. Gọi `map.force()` sau đó có thể đẩy **giá trị sai `6`** xuống storage rất bền vững. **Durable bug vẫn là bug.**

Dùng absolute-index `getInt(0)`/`putInt(0, value)` giúp không phải cùng sửa `position`, nhưng **không tự tạo tính nguyên tử cho thao tác đọc–sửa–ghi**. `duplicate()` và `slice()` có state vị trí riêng, nhưng **chia sẻ byte nội dung** của mapping gốc; chúng không ngăn data race trong vùng byte chồng lấn.

### 4.2. `synchronized` và `Lock` giải quyết vấn đề gì?

Một lock chung bảo đảm các thread **cùng tuân thủ giao thức** không thực hiện đồng thời đoạn cập nhật quan trọng:

```java
Object mutex = new Object();

synchronized (mutex) {
    int next = map.getInt(0) + 1;
    map.putInt(0, next);
    map.putInt(4, -next);
}
```

Nếu **mọi reader và writer trong JVM** dùng cùng `mutex` cho cặp trường đó, chúng không thấy trạng thái nửa chừng do hai thao tác trên bị xen kẽ. Đồng thời cơ chế monitor lock thực thi **happens-before** thích hợp của Java Memory Model: hành động trước khi nhả lock có thể được quan sát đúng thứ tự bởi thread sau đó lấy cùng lock.

Nhưng:

- `synchronized` **không flush dữ liệu xuống NVM**.
- Lock này chỉ có hiệu lực với code trong **cùng JVM** sử dụng **cùng đối tượng khóa**.
- Nếu có một thread không lấy lock hoặc tiến trình độc lập dùng cùng file, lock nội bộ không bảo vệ nó.
- Nếu JVM/OS crash giữa hai write, lock biến mất cùng tiến trình; nó không biến chuỗi cập nhật thành transaction bền vững.

`ReentrantLock` cũng có bảo đảm đồng bộ bộ nhớ tương ứng theo API `Lock`, nhưng không thay thế `force`.

### 4.3. `volatile`, `AtomicInteger`, `VarHandle` có thay `force` không?

Không. `volatile`/`VarHandle` với access mode phù hợp giúp quy định **atomicity/visibility/ordering** cho truy cập được hỗ trợ trong mô hình bộ nhớ Java; `AtomicInteger` giúp thực hiện các thao tác nguyên tử trên biến Java tương ứng. Những cơ chế đó không tự thực hiện **storage flush**.

Ví dụ, một `AtomicInteger` trong heap được increment an toàn vẫn có thể mất toàn bộ trạng thái khi JVM/host tắt nếu không có logic lưu bền. Một `VarHandle.setRelease(...)` cũng không phải câu lệnh “persist bytes to NVM”, và không làm tập hợp nhiều lần ghi trở thành giao dịch chống crash.

Nếu ứng dụng dùng `MethodHandles.byteBufferViewVarHandle(...)` để thao tác atomic trên direct/mapped buffer, phải tuân thủ các điều kiện **alignment, loại truy cập và hỗ trợ nền tảng** của API; rồi vẫn cần thiết kế durability, recovery và đồng bộ liên tiến trình riêng. Không dùng API này như mẹo để bỏ qua nguyên tắc transaction.

## 5. Đồng bộ giữa các **tiến trình**: `FileLock` có vai trò riêng

Hai JVM độc lập có thể cùng mở/mapping một tệp. Một `synchronized (mutex)` trong tiến trình A **không chặn** tiến trình B cập nhật tệp.

`FileChannel.lock()`/`tryLock()` trả về `FileLock`, một cơ chế điều phối dựa trên khả năng locking của hệ điều hành:

```java
// Đoạn trong phương thức; channel là FileChannel được mở hợp lệ.
try (java.nio.channels.FileLock lock = channel.lock()) {
    // Thực hiện thao tác theo giao thức ứng dụng.
}
```

Lưu ý quan trọng từ tài liệu Java:

- File locks được giữ **thay cho toàn bộ JVM**, nên **không thích hợp để điều phối các thread trong cùng JVM**. Dùng `synchronized`/`Lock` cho phần đó.
- Trên một số OS/filesystem, file locks chỉ mang tính **advisory**: các tiến trình muốn an toàn phải cùng tuân thủ giao thức khóa; lock không tự ngăn mọi thao tác đọc/ghi của chương trình bỏ qua nó.
- Một số hệ thống có giới hạn khi kết hợp **file lock và memory mapping**, thậm chí có thể không cho phép hai cơ chế đồng thời.
- Lock file **không đảm bảo lưu bền** và không khôi phục giao dịch dở dang khi tiến trình chết.
- Cần phối hợp version/format của dữ liệu và xử lý trường hợp ứng dụng crash sau khi đã nhả lock hay trước khi flush.

Vì vậy, với nhiều JVM, có thể cần **cả lock nội bộ + protocol file lock + persistence protocol**, tùy kiểu truy cập. Không giả định mọi filesystem hoặc hệ điều hành cung cấp cùng bảo đảm cross-process.

## 6. Chương trình Java 17+ độc lập: hai thread, một mapping và một lần mở lại

Ví dụ này cố ý dùng **mapping tệp thông thường `READ_WRITE`**, **không dùng NVM/DAX chuyên biệt**, để chạy được trên máy phát triển phổ biến. Nó minh họa ba hoạt động **riêng biệt**:

1. **Đồng bộ:** hai thread cùng cập nhật cặp `(counter, -counter)` dưới một `mutex` chung.
2. **Durability request:** sau khi cả hai thread kết thúc, chương trình gọi `MappedByteBuffer.force(0, 8)`.
3. **Kiểm tra đọc lại:** chạy một **tiến trình Java mới** mở lại file và xác nhận giá trị đã được lưu qua quá trình kết thúc bình thường.

**Lưu ý:** kết quả đọc lại **không phải kiểm thử mất điện**, không chứng minh cập nhật cặp trường là atomic khi crash, và không chứng minh `READ_WRITE_SYNC` hoạt động trên NVM.

### Tệp `Main.java`

```java
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class Main {
    private static final int SIZE = 8;
    private static final int UPDATES_PER_THREAD = 500;

    static void write(Path path) throws Exception {
        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
            MappedByteBuffer map =
                    channel.map(FileChannel.MapMode.READ_WRITE, 0, SIZE);
            map.order(ByteOrder.BIG_ENDIAN);
            map.putInt(0, 0);
            map.putInt(4, 0);

            Object mutex = new Object();
            Runnable task = () -> {
                for (int i = 0; i < UPDATES_PER_THREAD; i++) {
                    synchronized (mutex) {
                        int next = map.getInt(0) + 1;
                        map.putInt(0, next);
                        map.putInt(4, -next);
                    }
                }
            };
            Thread first = new Thread(task, "writer-one");
            Thread second = new Thread(task, "writer-two");
            first.start();
            second.start();
            first.join();
            second.join();

            synchronized (mutex) {
                int count = map.getInt(0);
                System.out.println("THREADS_DONE="
                        + (!first.isAlive() && !second.isAlive()));
                System.out.println("COUNTER=" + count);
                System.out.println("PAIR_VALID=" + (map.getInt(4) == -count));
                map.force(0, SIZE);
                System.out.println("FORCE_RETURNED=true");
            }
        }
    }

    static void read(Path path) throws Exception {
        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.READ)) {
            MappedByteBuffer map =
                    channel.map(FileChannel.MapMode.READ_ONLY, 0, SIZE);
            map.order(ByteOrder.BIG_ENDIAN);
            int count = map.getInt(0);
            System.out.println("REOPENED_COUNTER=" + count);
            System.out.println("REOPENED_PAIR_VALID="
                    + (map.getInt(4) == -count));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: Main write|read file");
        }
        Path path = Path.of(args[1]);
        switch (args[0]) {
            case "write" -> write(path);
            case "read" -> read(path);
            default -> throw new IllegalArgumentException(args[0]);
        }
    }
}
```

### Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main write state.dat
java Main read state.dat
```

**Stdout chính xác đã kiểm chứng trên JDK hiện đại:**

```text
THREADS_DONE=true
COUNTER=1000
PAIR_VALID=true
FORCE_RETURNED=true
REOPENED_COUNTER=1000
REOPENED_PAIR_VALID=true
```

**Giải thích vì sao output xác định:**

- Hai thread mỗi thread thực hiện `500` lượt tăng, **cùng giữ `mutex` trong thao tác read–modify–write**, nên tổng sau `join()` là `1000`.
- Mỗi lượt cập nhật `counter` và giá trị đối `-counter` trong cùng vùng khóa. Phần kiểm tra sau khi cả hai thread hoàn tất in `PAIR_VALID=true`.
- `map.force(0, SIZE)` gọi thao tác yêu cầu flush vùng mapped file rồi mới in `FORCE_RETURNED=true`. Đó là báo cáo rằng **lời gọi đã trả về không lỗi** trong phép kiểm thử, không phải bảo đảm giao dịch chống crash.
- Lệnh `java Main read state.dat` là **tiến trình mới**. Nó mở file ở chế độ read-only, lấy hai trường và kiểm tra lại. Tính nhất quán sau một lần thoát **bình thường** không chứng minh cấu trúc dữ liệu có thể phục hồi nếu mất điện đúng giữa hai lệnh ghi.
- Ví dụ ghi đúng 8 byte ở offset 0 và 4; `ByteOrder.BIG_ENDIAN` được chỉ định tường minh ở cả hai tiến trình để định dạng dữ liệu nhất quán.

Nếu chạy lại `write`, tệp được khởi tạo về `(0,0)` rồi tăng lại tới `1000`. Không dùng ví dụ này làm persistent counter có transaction hoặc cơ chế chống corruption trong production; đây là bài minh họa **phân tách vai trò của lock và force**.

## 7. Ánh xạ NVM chuyên biệt với `READ_WRITE_SYNC`

Khi có thiết bị/file backing thuộc **non-volatile RAM**, OS và filesystem hỗ trợ mode đồng bộ, JDK cung cấp:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

class SyncNvmExample {
    static void writePersistentNvm(Path daxFile) throws IOException {
        try (FileChannel channel = FileChannel.open(daxFile,
                StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            MappedByteBuffer map = channel.map(
                    ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
            map.putInt(0, 42);
            map.force(0, Integer.BYTES);
        }
    }
}
```

**Lệnh kiểm tra cú pháp trên Java 17+:**

```bash
javac --release 17 --add-modules jdk.nio.mapmode SyncNvmExample.java
```

Cú pháp đã được **biên dịch thành công**. Ví dụ này là **lớp hỗ trợ không có `main`**, không phải chương trình độc lập để chạy một mình. Khi viết ứng dụng classpath cần module `jdk.nio.mapmode`, có thể phải khai báo `--add-modules jdk.nio.mapmode` ở bước chạy; với ứng dụng modular, đưa `requires jdk.nio.mapmode;` vào `module-info.java` theo cấu hình module.

**Điều kiện thực thi thật:** `daxFile` phải là tệp/vùng NVM đủ kích thước và được OS/filesystem/JDK hỗ trợ mapping sync. **Đừng chạy nguyên ví dụ trên file thường rồi coi đó là benchmark NVM.** Một số môi trường sẽ từ chối mode bằng ngoại lệ; không nên thay âm thầm về `READ_WRITE` rồi tuyên bố nhận được bảo đảm của `READ_WRITE_SYNC`.

Cơ chế `READ_WRITE_SYNC` tối ưu đường flush cho NVM bằng cache-line writeback khi implementation hỗ trợ. Nó **không thay đổi** việc `putInt` là câu lệnh ghi dữ liệu và không tạo transaction hai hoặc nhiều trường. Cần phân biệt rõ lựa chọn **storage mapping mode** với lựa chọn **algorithm cập nhật dữ liệu**.

## 8. Một `force` hay hai `force` có tạo transaction không?

Xét một bản ghi có dữ liệu `A` và `B`:

```text
Trạng thái ban đầu: A=100, B=-100
Cập nhật dự kiến:   A=200, B=-200

write(A=200)
write(B=-200)
force()
```

Nếu crash ở giữa, không có cam kết transaction all-or-nothing. Thử:

```text
write(A=200)
force(A)
write(B=-200)
force(B)
```

Điều này thêm **hai bước yêu cầu persistence** và có thể giúp thiết kế giao thức thứ tự ghi nếu môi trường/hardware có bảo đảm phù hợp, nhưng **tự nó vẫn không tạo ra atomicity của cặp trường**. Crash giữa các bước có thể để lại `(200,-100)`. Không nhầm **“ghi bền từng phần”** với **“commit nguyên tử toàn transaction”**.

### Phải có giao thức phục hồi

Các kỹ thuật phổ biến trong hệ thống cần *crash consistency* gồm:

- **Write-ahead log (WAL):** lưu thông tin đủ để redo/undo và có cơ chế xác nhận commit; recovery phân biệt transaction hoàn tất với transaction dở dang.
- **Copy-on-write / hai bản sao (double buffering):** ghi một phiên bản mới trong vùng chưa được công bố, bảo đảm nó bền vững theo thứ tự đúng rồi thay đổi thông tin trỏ tới phiên bản hợp lệ. Cách công bố đó cũng cần thiết kế tránh ghi dở/torn writes.
- **Version + length + checksum/CRC:** giúp phát hiện bản ghi không đồng nhất hoặc bị hỏng khi khôi phục; **checksum chỉ phát hiện lỗi**, không tự sửa và không biến ghi thành nguyên tử.
- **Commit marker và recovery validation:** chỉ công nhận bản ghi có marker/metadata hợp lệ, nhưng phải thiết kế kích thước ghi nguyên tử, thứ tự flush, failure domain và kiểm tra thiết bị cụ thể.

**Không có một recipe cố định đúng cho mọi NVM/file system.** Những bảo đảm như *atomic write size*, *cache-line persistence ordering*, *power-failure atomicity* và *write barriers* phải lấy từ tài liệu của OS, CPU, filesystem, NVM và API/engine đang dùng. Đặt thêm một trường `committed=true` rồi gọi `force` **chưa đủ chứng minh** giao thức có thể phục hồi sau mất điện.

### Tính nguyên tử và tính bền dữ liệu là hai trục độc lập

Một transaction có thể:

1. **Atomic nhưng chưa bền:** các thread không thấy trạng thái giữa chừng, nhưng dữ liệu chưa được flush khi thiết bị gặp sự cố.
2. **Đã được flush nhưng không atomic:** một số trường của transaction được ghi bền, trong khi các trường khác chưa tới lúc ghi.
3. **Có synchronized nhưng không liên tiến trình:** các thread cùng JVM hợp tác tốt, nhưng một tiến trình khác vẫn có thể sửa file nếu không có giao thức chung.
4. **Bền và có giao thức phục hồi:** chỉ khi thiết kế, môi trường và phép kiểm thử chứng minh được cả các tính chất mới nên tuyên bố một update là crash-safe.

## 9. `MappedByteBuffer.force` và `FileChannel.force` không hoàn toàn giống nhau

Java NIO có cả:

```java
map.force();
map.force(0, 8);
channel.force(true);
```

Nhưng chúng hoạt động trên **đối tượng và phạm vi khác**:

| API | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `MappedByteBuffer.force()` | Flush thay đổi thuộc mapping | Dùng để yêu cầu persistence cho byte đã sửa qua mapped buffer |
| `MappedByteBuffer.force(index,length)` | Flush một vùng của mapping | Bắt đầu tại chỉ số của mapping/buffer, không phải “số lần cập nhật”; có thể flush thêm byte |
| `FileChannel.force(false)` | Yêu cầu ghi bền nội dung đã thay đổi qua channel | Không bảo đảm bao trùm mọi thay đổi được thực hiện **qua mapped buffer** |
| `FileChannel.force(true)` | Yêu cầu ghi bền cả nội dung/metadata theo hợp đồng channel | Không thay thế `map.force` cho mapped writes; ảnh hưởng metadata tùy OS |

Tài liệu `FileChannel` chỉ bảo đảm `channel.force(...)` cho các thay đổi được thực hiện qua những phương thức channel/file stream được chỉ định; nó **có thể hoặc không** flush mọi thay đổi do viết qua mapped buffer. Vì vậy khi sửa `map.putInt(...)`, hãy dùng **`map.force(...)`** cho vùng mapping theo hợp đồng của nó.

Cũng đừng nhầm `map.load()` hoặc `map.isLoaded()` với durability. Hai phương thức ấy liên quan việc vùng dữ liệu có thể được nạp/ở trong **RAM vật lý**, không phải xác nhận byte đã bền vững trên storage.

## 10. Visibility giữa các tiến trình không giống bảo đảm của Java Memory Model

Một ví dụ hay gây nhầm:

- Tiến trình A dùng `synchronized`, sửa mapped file rồi gọi `force`.
- Tiến trình B đã có mapping của cùng file và đọc giá trị.

Không nên khẳng định “vì A gọi `force` nên B **bắt buộc** thấy ngay bản ghi nguyên vẹn”. Java Memory Model quản lý happens-before giữa **các Java thread**, không tự tạo hợp đồng đồng bộ giữa **hai JVM độc lập**.

Tài liệu `FileChannel` và `MappedByteBuffer` lưu ý rằng visibility của thay đổi mapping giữa các tiến trình/phần mềm khác có thể **phụ thuộc hệ điều hành và filesystem**, nhất là trên network filesystem. Việc một tiến trình đọc các byte đã được flush cũng không bảo đảm nó thấy một transaction **nhất quán về nhiều trường** nếu nó đọc trong lúc tiến trình khác đang thay đổi.

**Cần định nghĩa giao thức inter-process**, bao gồm:

1. Ai được ghi, ai được đọc, vùng dữ liệu nào dùng chung?
2. Cơ chế khóa/công bố/đồng bộ liên tiến trình có gì được OS hỗ trợ?
3. Khi nào writer thực hiện persistence flush, khi nào reader được quyền tin version mới?
4. Nếu writer crash giữa chừng, reader/recovery kiểm tra validity thế nào?
5. Nếu mất điện hoặc mmap bị mất hiệu lực do file bị truncate, hành vi lỗi được xử lý ra sao?

Điểm cuối quan trọng vì `MappedByteBuffer` có thể trở nên không truy cập được nếu file bị truncate/đổi kích thước bất ngờ. Không dùng `force` để chữa lỗi race với thay đổi kích thước file.

## 11. Cách kiểm thử đúng ba tính chất

Không thể kiểm thử cả ba bằng một lệnh “chạy rồi in PASS”. Cần **ba nhóm phép thử khác nhau**:

| Mục tiêu | Bài kiểm thử | Không được suy luận |
| --- | --- | --- |
| **Thread synchronization** | Nhiều writer/reader cùng JVM, kiểm tra race, counter, invariant; chạy cả tải cao | Test thành công một lần không chứng minh mọi đường chạy không có data race |
| **Persistence thông thường** | Ghi mapping, gọi `force`, đóng process bình thường, mở từ process khác, đọc lại | Chưa kiểm chứng mất điện ở giữa cập nhật |
| **Crash atomicity/recovery** | Injection failure ở nhiều mốc ghi/flush/commit; khởi động lại và chạy recovery; kiểm tra bản ghi hợp lệ theo protocol | `force` trả về không chứng minh transaction đa trường nguyên tử |

### Kiểm thử crash phải có trạng thái có thể xác định

Với hai bản sao dữ liệu và checksum, nên đưa tiến trình thử vào các điểm dừng cụ thể trong thuật toán (trước/sau ghi data, trước/sau flush, trước/sau publish commit). Ở mỗi mốc, mô phỏng failure phù hợp rồi chạy recovery, kiểm tra hệ thống chọn **bản cũ hợp lệ hoặc bản mới hợp lệ** chứ không trả một cặp trường lai.

Nhưng **`kill -9` hay `Process.destroyForcibly()` không tương đương mất điện vật lý**: OS còn hoạt động và có thể flush dirty pages sau khi process bị kill. Muốn kiểm chứng bảo đảm power-failure thực, cần phương pháp thử fault injection và phần cứng/lớp storage thích hợp.

### Dùng concurrency test đúng mục tiêu

- Có nhiều thread cùng đọc/ghi trong thời gian dài, không chỉ hai lần gọi liên tiếp.
- Reader và writer phải sử dụng cùng giao thức lock nếu muốn kiểm tra tính nhất quán **dựa trên lock**.
- Kiểm tra không có lost update, trạng thái `(A,B)` hợp lệ, thời hạn hoàn thành, deadlock và race.
- Với nhiều tiến trình, phải test cơ chế **file lock/coordination riêng**, không chỉ đồng bộ nội JVM.
- Với storage, test đường lỗi `IOException`/`UncheckedIOException`, thiếu dung lượng, không hỗ trợ sync mapping và file bị thay đổi.

Việc benchmark throughput/latency nên đặt sau bước đảm bảo đúng dữ liệu. Nếu bỏ lock để tăng tốc nhưng tạo sai dữ liệu, cải thiện số ops/s không có giá trị.

## 12. Các sai lầm phổ biến

| Nhận định sai | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “`force` tạo một transaction” | Flush không hợp nhất nhiều write thành all-or-nothing | Cần protocol commit/recovery |
| “Một `putLong` chắc chắn atomic trên mọi NVM” | Java NIO không hứa crash-atomic storage write như thế | Kiểm tra API, alignment, hardware/failure domain |
| “`synchronized` đảm bảo dữ liệu bền qua mất điện” | Lock điều phối thread, không flush | Kết hợp persistence riêng |
| “`volatile` tương đương persistent write barrier” | Java visibility khác storage durability | Dùng storage flush/API phù hợp |
| “`FileLock` đủ cho các thread trong một JVM” | File lock là lock cấp JVM/hệ OS, không dành cho intra-JVM | Dùng `synchronized`/`Lock` |
| “`FileLock` buộc mọi process tuân thủ trên mọi OS” | Có hệ thống lock chỉ advisory | Thiết kế protocol hợp tác và test OS |
| “`READ_WRITE_SYNC` sẽ chạy trên mọi ổ SSD/NVMe” | Mode yêu cầu môi trường NVM mapping hỗ trợ | Kiểm tra DAX, filesystem, JVM và ngoại lệ |
| “Mapped file đọc được sau process exit nghĩa là crash-safe” | Đó là normal shutdown, không phải crash | Test recovery/failure injection |
| “`channel.force(true)` chắc chắn flush mọi `map.put`” | Hợp đồng channel không bảo đảm thế | Dùng `map.force` cho mapped writes |
| “`isLoaded() == true` nghĩa là đã persist” | Chỉ nói về residency trong RAM | Không dùng làm durability check |
| “Dùng buffer `duplicate()` thì các thread độc lập byte” | Duplicate chia sẻ content | Lock/cơ chế atomic phù hợp |
| “Chỉ cần lưu checksum là đã có transaction” | Checksum giúp phát hiện trạng thái sai, không tự phục hồi | Redundancy + recovery + commit protocol |
| “Sau `force` mọi process khác thấy ngay một record đầy đủ” | Visibility và atomicity liên tiến trình có giới hạn riêng | Đồng bộ và xác nhận version/invariant |

## 13. Tự kiểm tra

**Câu 1.** Hai thread cùng chạy `counter = map.getInt(0) + 1` rồi `map.putInt(0,counter)` mà không khóa. Sau đó `force`. Có tránh được lost update không?

**Đáp án:** Không. `force` có thể ghi bền **giá trị đã bị lost update**. Cần đồng bộ hoặc cơ chế atomic read–modify–write thích hợp.

**Câu 2.** Ghi hai trường `A` và `B` rồi gọi `force(0, 8)`. Nếu crash giữa lúc viết hai trường, có bảo đảm chỉ thấy bản cũ hoặc bản mới không?

**Đáp án:** Không. Không có transaction all-or-nothing do hai thao tác `putInt` và `force` tự tạo.

**Câu 3.** Khi nào dùng `FileLock` thay vì `synchronized`?

**Đáp án:** `FileLock` hữu ích để **các tiến trình phối hợp** theo chính sách OS/file system. Với các thread cùng JVM, cần lock trong Java. Nếu cả hai loại cạnh tranh tồn tại, có thể cần cả hai.

**Câu 4.** Vì sao chương trình dùng `READ_WRITE_SYNC` có thể chạy thất bại trên filesystem thông thường?

**Đáp án:** Đây là map mode chuyên biệt cho non-volatile RAM, phụ thuộc OS, filesystem, driver và hardware. Không phải môi trường nào cũng cung cấp sync mapping.

**Câu 5.** Tại sao “đọc lại file trong một JVM mới thấy `1000`” chưa chứng minh transaction đã crash-safe?

**Đáp án:** Writer kết thúc bình thường sau khi gọi `force`. Chưa có sự cố tại các mốc giữa hai write và chưa có giao thức recovery được kiểm thử.

**Câu 6.** `MappedByteBuffer.load()` có bảo đảm dữ liệu đã được ghi bền không?

**Đáp án:** Không. Nó liên quan việc nạp vùng mapped data vào bộ nhớ vật lý, không phải yêu cầu persistence xuống thiết bị.

**Ghi nhớ:** Trong ánh xạ NVM, **durability**, **atomicity** và **thread/process synchronization** là ba yêu cầu **khác nhau**. `force` giúp yêu cầu ghi bền vùng mapped data theo điều kiện API; lock/VarHandle giúp điều phối hay khả kiến theo hợp đồng riêng; còn tính nguyên tử và khả năng phục hồi của nhiều trường khi crash cần một **thiết kế transaction/recovery chuyên dụng**. Chỉ kết luận một hệ thống ghi dữ liệu là an toàn sau khi xác minh cả ba khía cạnh trên nền tảng và thiết bị thật.

### Tài liệu chính thức

- [JEP 352 — Non-Volatile Mapped Byte Buffers, Java 14](https://openjdk.org/jeps/352)
- [Java SE 21 — `MappedByteBuffer`, `force` và mapping](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html)
- [Java SE 25 — `ExtendedMapMode.READ_WRITE_SYNC`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html)
- [Java SE 21 — `FileChannel`, `force` và `map`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java SE 21 — `FileLock` và giới hạn liên tiến trình](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html)
- [Java SE 21 — `Buffer`, mục Thread Safety](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/Buffer.html)
- [Java Language Specification, `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html)
