# Phân biệt bộ nhớ bền vững vật lý với lưu và khôi phục đối tượng Java

## 1. Vấn đề cốt lõi: NVM giữ byte, không tự khôi phục Java object

**Non-volatile memory (NVM)** là bộ nhớ có thể giữ dữ liệu sau khi mất điện theo đặc tính phần cứng và chế độ vận hành. **Java object persistence** lại là khả năng ứng dụng lưu trạng thái có ý nghĩa rồi tái tạo các đối tượng trong một lần chạy JVM khác. Chúng không phải cùng một khả năng.

Giả sử một JVM có Java heap được đặt trên thiết bị NV-DIMM thích hợp:

~~~java
final class Order {
    String id = "order-42";
    int quantity = 3;
}

Order order = new Order();
~~~

Khi JVM dừng hoặc máy mất điện, **không được kết luận** rằng JVM khởi động lần sau sẽ tự tìm được đúng object `order` và tiếp tục chạy từ trạng thái cũ. Thiết bị có thể giữ nội dung của một số byte, nhưng JVM mới có runtime metadata mới, root references mới, hệ thống garbage collection và class loading riêng. **Java SE không cung cấp cơ chế tự gắn lại toàn bộ live object graph của JVM trước** chỉ vì backing heap nằm trên bộ nhớ bền vững vật lý.

Có ba tầng cần phân biệt:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Physical persistence** | Byte trên thiết bị có còn sau mất điện? | NVDIMM, persistent memory đã cấu hình đúng |
| **Durable logical state** | Ứng dụng đã commit một bản ghi/snapshot đủ hoàn chỉnh chưa? | File versioned, database transaction, WAL |
| **Java object recovery** | JVM mới có thể đọc và tạo lại object hợp lệ không? | Decode thành `new Order(...)`, nạp từ DB |

**Bài học:** tính không mất điện của thiết bị là đặc tính vật chứa byte; lưu/khôi phục object là **thiết kế ở tầng ứng dụng hoặc storage engine**.

### Vì sao đây là một chủ đề của Java 10?

**OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices**, ra mắt trong **JDK 10**, hỗ trợ đặt Java object heap trên một thiết bị bộ nhớ thay thế như NVDIMM bằng một filesystem mapping, thông qua cờ:

~~~text
-XX:AllocateHeapAt=<path>
~~~

Tính năng này nói về **vị trí cấp phát Java heap trong JVM đang chạy**, **không phải** snapshot tự động hoặc cơ sở dữ liệu đối tượng. Oracle JDK 25 Java launcher và tài liệu OpenJDK mainline vẫn mô tả `-XX:AllocateHeapAt`; vì vậy không gọi cờ này là đã bị xóa. Tuy nhiên, khả năng sử dụng thật phụ thuộc JDK/HotSpot, OS, filesystem, hardware và quyền cấu hình.

Ví dụ Java 17+ bên dưới mô tả **lưu trạng thái và phục hồi qua hai process riêng**, dùng API Java SE vẫn hỗ trợ, không phụ thuộc sở hữu thiết bị NVDIMM.

## 2. Phân biệt DRAM, persistent memory, storage và Java heap

### 2.1. DRAM và NVM

- **DRAM** là bộ nhớ truy cập ngẫu nhiên phổ biến, nội dung không còn sau khi bị mất nguồn theo đặc tính vận hành thông thường.
- **Persistent/non-volatile memory** có thể giữ byte khi mất nguồn, nhưng đặc tính load/store, độ trễ, băng thông và tính nguyên tử phụ thuộc phần cứng.
- **SSD/HDD** là thiết bị lưu trữ bền vững, thường truy cập qua file/block I/O. Không mặc định chúng có các semantics thao tác nguyên tử và hiệu năng cần thiết để dùng làm Java heap.
- **DAX (Direct Access)** là một cách kernel/filesystem cung cấp truy cập memory-mapped tới thiết bị phù hợp, thường tránh page cache thông thường.
- **Memory-mapped file** là ánh xạ byte từ file vào không gian địa chỉ của process; bản thân mapping không đồng nghĩa mọi write đã được sync hoặc update nhiều field đã atomic.

Không phải mọi **alternative memory device** đều non-volatile, và một thiết bị vật lý non-volatile cũng có thể được dùng như **volatile memory** (chỉ tăng dung lượng hoạt động, không lưu dữ liệu ứng dụng).

### 2.2. Heap là gì trong ngữ cảnh JVM?

Java heap là nơi JVM cấp phát object và array theo hợp đồng Java, nhưng cách bố trí byte trong đó là **chi tiết triển khai HotSpot/collector**, không phải một file format lưu trữ. Java heap có các đặc điểm:

1. Object references được JVM quản lý.
2. Collector có thể di chuyển/compact object, tái sử dụng region và cập nhật references.
3. Roots có thể nằm trên thread stack, static fields, JNI handles và những cấu trúc runtime khác.
4. Class metadata, JIT code và GC bookkeeping có thể nằm **ngoài** object heap.
5. Sau restart, JVM nạp classes, thiết lập heap và GC state từ đầu.

Một phần của các bytes tồn tại vật lý không chứng minh tất cả metadata và root graph có thể phục hồi hợp lệ.

### 2.3. Vùng virtual address không phải object ID

Sơ đồ minh họa:

~~~text
JVM lần 1:
  Order@0xA000 --> String@0xB000
          |
          +------> Customer@0xC000

JVM lần 2:
  heap mapping khác, class loaders khác,
  metadata GC khác, JNI/thread roots khác.

Không tồn tại Java SE API công khai:
  Object recovered = Runtime.reopenOldObjectAt(0xA000);
~~~

Tên phương thức trong dòng cuối chỉ là **minh họa điều không được Java SE cung cấp**. Một memory address, `identityHashCode` hoặc vị trí object trong heap không phải một định danh nghiệp vụ ổn định xuyên tiến trình.

## 3. JEP 316: AllocateHeapAt giúp gì và không giúp gì?

### 3.1. Cú pháp còn được tài liệu hóa

~~~bash
java -Xms1g -Xmx1g -XX:AllocateHeapAt=/mnt/pmem -jar app.jar
~~~

Lệnh chỉ có ý nghĩa khi `/mnt/pmem` là đường dẫn tới filesystem trên một **memory device phù hợp** và môi trường đủ quyền, dung lượng, semantics. **Đừng chạy trên một thư mục ổ đĩa thông thường rồi tuyên bố đã dùng NVDIMM.**

Theo Java launcher documentation:

- `-XX:AllocateHeapAt=<path>` yêu cầu HotSpot memory-map Java object heap ở thiết bị thay thế do đường dẫn chỉ định.
- Thiết bị phải cung cấp semantics giống DRAM cần cho JVM, gồm những atomic operations tương ứng.
- Các cấu trúc khác, ví dụ metaspace, code heap và thread stacks, vẫn có khu vực DRAM riêng theo mô tả tính năng.
- Các cờ như `-Xms`, `-Xmx` và collector options tiếp tục làm việc theo phạm vi của chúng.

### 3.2. Đây là volatile use của non-volatile media

Từ “persistent” trong tên thiết bị không tự biến JVM heap thành **durable object graph**. Dù backing memory là vật lý non-volatile, Java object allocation trên vùng này vẫn chịu quy tắc reachability và GC **trong phiên JVM hiện tại**.

JEP 316 **không** cung cấp:

- Snapshot ổn định để JVM mới mount và khôi phục.
- Persistent object ID hoặc root registry được chuẩn hóa.
- Định nghĩa durable layout của `String`/`HashMap`/`record`.
- Đảm bảo flush tự động mọi field sau từng thao tác Java.
- Transaction atomic trên nhiều objects.
- Replay/recovery của GC, class-loader và native runtime metadata.
- Khả năng khôi phục thread stacks, sockets, locks hoặc instruction pointer.
- Hợp đồng tương thích heap image giữa các JDK versions.

Vì vậy không gọi `AllocateHeapAt` là “cờ bật tự động lưu Java object”. Cũng không lấy file mmap do JVM dùng làm backing heap rồi tự đưa cho một tiến trình khác để diễn giải như serialized file.

### 3.3. Full heap trên thiết bị thay thế có tăng hiệu năng?

Chưa thể khẳng định. Thiết bị alternative memory có thể có latency/bandwidth khác DRAM; collector, NUMA, working set và mức GC pressure ảnh hưởng throughput, startup và pauses. Hãy benchmark trên **hardware, OS, JDK build và workload thật**; không bảo đảm “NVM nhanh hơn” hoặc “đã đặt heap trên NVM thì RAM DRAM không cần nữa”.

### 3.4. GC có còn hoạt động?

**Có.** Object không còn reachable vẫn có thể bị GC reclaim dù heap đang dùng backing NVM. Không được dùng non-volatile memory làm lý do để bỏ qua memory-leak analysis, heap sizing hoặc garbage collection tuning.

Một object được ứng dụng coi là nghiệp vụ quan trọng nhưng **không còn reachable** vẫn không tự được giữ bền vững chỉ vì thiết bị không mất điện. Khái niệm **object liveness** do GC quản lý khác với **durable record lifetime** của database.

## 4. Vì sao raw heap bytes không phải dữ liệu khôi phục ổn định?

### 4.1. Các mối liên hệ phụ thuộc JVM

Object graph trong Java có tham chiếu tới những objects khác. Việc diễn giải tham chiếu có thể phụ thuộc heap base, nén con trỏ, object layout, collector, class loaders và metadata.

Sau khi JVM restart:

- Các objects cũ không có root references theo JVM mới.
- Java classes/fields có thể thay đổi khi ứng dụng nâng phiên bản.
- Heap memory có thể ánh xạ tại địa chỉ ảo khác.
- Garbage collector có thể đã chuyển/reclaim objects ngay trước crash.
- Native resources không thể dùng lại như cũ.
- Có thể một số writes chưa đi đến thiết bị bền vững.

**Không tự diễn giải bytes** như Java `Object` trên JVM mới. Đây là chuyện khác với nạp một file nhị phân có schema do ứng dụng quản lý.

### 4.2. Crash có thể xảy ra giữa những thay đổi logic

Ví dụ chuyển tiền:

~~~text
A.balance -= 100
B.balance += 100
~~~

Nếu crash sau bước đầu, dù thiết bị giữ byte đã ghi, trạng thái có thể không nhất quán vì transaction gồm **hai cập nhật có liên hệ**.

Media non-volatility không tự cung cấp transaction atomicity, isolation hoặc recovery. Cần WAL, copy-on-write, commit marker, transaction engine hoặc cơ chế tương đương.

### 4.3. Bền vững byte và an toàn object khác nhau

Một snapshot hợp lệ cần:

- Format identifier và schema version.
- Trường dữ liệu có ý nghĩa nghiệp vụ (ID, quantity, status, revision).
- Encoding và byte order rõ ràng.
- Kích thước tối đa để tránh dữ liệu quá lớn.
- Checksum để phát hiện truncation/corruption thông thường.
- Validation business invariants khi khôi phục.
- Commit protocol và chính sách xử lý half-written record.
- Migration khi đổi schema/class version.

Các thông tin trên không tự xuất hiện từ `new Order()` hoặc cờ `AllocateHeapAt`.

## 5. Vật liệu bền vững, flush và transaction: những mức độ khác nhau

| Mức | Cam kết trong phạm vi thiết kế | Chưa có chỉ vì mức đó |
| --- | --- | --- |
| Java Memory Model visibility | Thread khác có thể thấy write theo quy tắc happens-before | Write đã bền vững qua mất điện |
| Persistent physical media | Một số bytes có thể còn sau mất nguồn | File/application record có schema hợp lệ |
| File durability | Ghi và sync dữ liệu theo API và storage semantics | Atomic multi-record update |
| Application crash consistency | Recovery chọn được trạng thái hoàn chỉnh đã commit | Backup/replication ngoài thiết bị |
| Object reconstruction | Đã decode và tạo Java object mới | Tiến trình cũ resume nguyên instruction |

### 5.1. Java volatile KHÔNG phải non-volatile hardware

~~~java
class ReadyState {
    volatile boolean ready;
}
~~~

`volatile` trong Java là cơ chế về memory ordering/visibility giữa các thread. Nó **không** bảo đảm field `ready` được tự ghi vào NVM hay phục hồi sau khi JVM restart.

Ba khái niệm tách biệt:

- **Java volatile:** visibility/ordering.
- **Non-volatile memory:** giữ byte theo tính chất vật lý.
- **Persisted state:** ứng dụng/storage đã lưu một bản ghi có ý nghĩa.

### 5.2. FileChannel.force chưa phải transaction

Java 17 có `java.nio.channels.FileChannel.force(boolean)`:

~~~java
// Mã minh họa nằm trong một method throws IOException.
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("data.bin"),
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.WRITE)) {
    channel.force(true);
}
~~~

Code trên chưa ghi bytes nào, chỉ minh họa API. Trong luồng thực cần ghi dữ liệu trước rồi `force(true)`. Với local storage, phương thức yêu cầu đồng bộ những cập nhật thuộc file channel trong phạm vi Javadoc; `true` còn yêu cầu metadata.

**Đừng coi force là atomic multi-file transaction.** API không tự tạo commit marker, rollback hoặc kiểm schema. Remote filesystem, OS, firmware và phương thức mount có thể có failure semantics khác.

### 5.3. Atomic rename và durable rename khác nhau

Một chiến lược snapshot thường là:

~~~text
1. Ghi temp-file mới hoàn chỉnh.
2. Sync nội dung temp-file.
3. Rename/move temp-file sang tên snapshot chính bằng atomic move.
4. Sync directory metadata khi nền tảng cần và có hỗ trợ.
5. Khi restart, chọn snapshot hợp lệ.
~~~

Bước (3) giúp tránh nhìn thấy file bị ghi dở nếu filesystem hỗ trợ atomic move. Nhưng **atomicity của đổi tên** và **durability của directory entry sau power failure** là hai đặc tính khác nhau. Java SE không cung cấp một cách portable đơn giản để bảo đảm mọi directory sync trên mọi OS/filesystem.

Với hệ thống có yêu cầu mất dữ liệu bằng 0, phải kiểm cụ thể storage, filesystem, atomic replace semantics và crash model; hoặc sử dụng database có durability contract rõ.

## 6. Lưu trạng thái ứng dụng: file, DB và event log

Một ứng dụng có thể lưu state theo các cách hiện vẫn phù hợp:

1. **Versioned file:** JSON hoặc binary có schema, checksum và replace/recovery.
2. **Relational database:** transaction, indexes, schema migrations và backup.
3. **Key-value/document database:** lưu record theo business ID và hợp đồng consistency.
4. **Write-ahead log:** ghi hành động trước khi áp dụng state; replay khi restart.
5. **Event sourcing:** lưu các sự kiện, rebuild state hoặc kết hợp snapshot.
6. **Java Object Serialization:** API vẫn còn nhưng có ràng buộc compatibility/security; không khuyến nghị deserialize input không tin cậy.

Không có yêu cầu nào trong số này đòi Java object heap phải nằm trên NVM. Một JVM trên DRAM có thể lưu durable state vào SSD/database. Ngược lại, JVM đặt heap trên NVM vẫn cần một cơ chế ghi logical state nếu muốn recovery.

### 6.1. Khôi phục object nghĩa là tạo object mới

~~~text
JVM 1:                           JVM 2:
Order object                     Đọc file/database
  id=order-42    ---> ghi file       |
  qty=3              state           v
  rev=7                           Decode/validate
                                     |
                                     v
                                  new Order(...)
                                  id=order-42
                                  qty=3
                                  rev=7

Giá trị tương đương, nhưng identity của object không sống qua process.
~~~

`Object.equals` có thể trả true khi so field/value của hai objects. `==` là so reference identity **trong một JVM**, không thể dùng để so identity thực xuyên hai JVM độc lập.

### 6.2. Vì sao business ID quan trọng?

Nếu muốn liên kết các entities sau restore, lưu `orderId`, `customerId` hoặc một khóa ổn định; không lưu địa chỉ bộ nhớ hay `System.identityHashCode`.

Những dữ liệu không nên cố persist nguyên trạng gồm:

- `Thread`, stack frames và live monitors.
- Socket/TCP connection/DB connection đang mở.
- Native pointer/file descriptor không còn hợp lệ.
- ExecutorService, queues phụ thuộc runtime khi phục hồi.
- JIT compiled machine code.
- VM/GC internal metadata.

Sau restart, ứng dụng dựng lại runtime resources từ config và persisted state.

## 7. Java Object Serialization vẫn được hỗ trợ, nhưng có giới hạn

### 7.1. ObjectOutputStream và ObjectInputStream

`java.io.Serializable` và `ObjectOutputStream`/`ObjectInputStream` vẫn có trong Java SE. Chúng encode một object graph thành stream bytes, sau đó deserialize thành objects **mới** trong JVM khác khi classes tương thích.

~~~java
// Mã minh họa, chỉ trong chương trình có xử lý checked exceptions.
record ItemState(String id, int count)
        implements java.io.Serializable {}

try (var out = new java.io.ObjectOutputStream(
        java.nio.file.Files.newOutputStream(path))) {
    out.writeObject(new ItemState("item-1", 3));
}
~~~

`path` là biến Path cần được khai báo trong chương trình thực. **Đây là mã minh họa**, không phải chương trình độc lập; ví dụ runnable đầy đủ bên dưới sử dụng một **schema binary rõ ràng**, tránh ràng buộc của native Java serialization.

### 7.2. Serializable không tự lưu object

Chỉ khai báo `implements Serializable` **không tạo file** và không tự sync field changes. Cần thực sự gọi phương thức lưu với một output stream, đóng/flush theo hợp đồng phù hợp và triển khai recovery.

Những thứ không tự persist như object state thông thường:

- Fields `static` và `transient`.
- Những runtime/native handles.
- Thread state và live locks.
- Một transaction đã gửi nhưng chưa commit.
- Các object không hỗ trợ serialization.
- Các caches tạo lại sau restart.

### 7.3. Object graph được tái tạo, không dùng lại reference cũ

Java serialization có thể bảo toàn quan hệ reference sharing/cycles bên trong stream theo quy tắc specification, nhưng những reference đó được **tái tạo** trong process/JVM mới. Chúng không phải raw addresses được lấy lại từ JEP 316 heap.

### 7.4. Lưu ý bảo mật nghiêm trọng

Deserialization từ nguồn không tin cậy có thể gây rủi ro an ninh, đặc biệt nếu classpath có các class không an toàn khi khởi tạo/deserialization. Không khuyến nghị dùng `ObjectInputStream.readObject` trực tiếp trên request từ mạng hoặc file attacker kiểm soát.

Khi buộc phải dùng, cần `ObjectInputFilter` (JEP 290) để giới hạn classes/depth/array size/bytes, xác thực nguồn và thực hiện threat modeling. Filter không thay thế schema validation và không đảm bảo tự động an toàn cho mọi graph.

**Thực hành mới:** ưu tiên format có schema/version rõ ràng, parser kiểm tra kích thước, các trường nghiệp vụ và xử lý lỗi; sử dụng Java serialization chỉ khi có lý do phù hợp và dữ liệu **được tin cậy**.

## 8. File mapping và NVM: lưu byte không phải lưu Java object

### 8.1. MappedByteBuffer

`MappedByteBuffer` là view vùng file map, được tạo bởi `FileChannel.map`. Ví dụ chỉ minh họa, giả sử file đã đủ 4.096 bytes:

~~~java
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("data.bin"),
        java.nio.file.StandardOpenOption.READ,
        java.nio.file.StandardOpenOption.WRITE)) {
    var mapped = channel.map(
            java.nio.channels.FileChannel.MapMode.READ_WRITE,
            0, 4096);
    mapped.putInt(0, 42);
    mapped.force();
}
~~~

Lệnh `putInt(0,42)` ghi bốn bytes theo byte order của buffer; nó **không** đưa một object `Integer` vào persistent object store.

Khi restart, một mapping mới có thể đọc bốn bytes đó nếu file còn và đã được lưu, nhưng ứng dụng phải biết offset 0 nghĩa là gì. Với nhiều records, cần định dạng ID/length/checksum/version và recovery.

### 8.2. ExtendedMapMode hỗ trợ non-volatile mapping trên nền tảng phù hợp

JDK 14 giới thiệu các map modes ở module `jdk.nio.mapmode`:

~~~java
jdk.nio.mapmode.ExtendedMapMode.READ_ONLY_SYNC
jdk.nio.mapmode.ExtendedMapMode.READ_WRITE_SYNC
~~~

Oracle Java SE 25/26 Javadoc vẫn ghi những modes này. Với `READ_WRITE_SYNC` trên platform hỗ trợ, `force` có thể dùng cache-line writeback cho NVM thay vì phương thức file-device flush thông thường.

**Đừng dùng trên máy không có khả năng DAX/NVM thích hợp rồi kỳ vọng chạy được:** `FileChannel.map` có thể ném `UnsupportedOperationException` với mode không được implementation hỗ trợ.

Ngay cả trên thiết bị có hỗ trợ, các map modes **chỉ cung cấp khả năng truy cập và force mapped bytes**, không tự xây transaction engine cho Java heap.

### 8.3. Foreign Function & Memory API không phải object persistence

Foreign Function & Memory API được chuẩn hóa từ **Java 22** (JEP 454), cung cấp `Arena` và `MemorySegment` để quản lý off-heap/native memory trong vòng đời xác định.

Nó hữu ích cho native data layouts và mapped memory, nhưng vẫn yêu cầu code tự định nghĩa **logical format, commit, validation và recovery** nếu dữ liệu phải sống qua restart. Ví dụ Java 17 của bài không dùng các APIs Java 22 để giữ khả năng chạy trên Java 17.

## 9. Chương trình Java 17+ hoàn chỉnh: lưu và khôi phục state qua hai JVM

Đây là ví dụ **không phụ thuộc NV-DIMM**. Nó thể hiện đúng ranh giới: object trong JVM 1 được **encode thành bản ghi**, JVM 2 **decode và tạo object mới**.

Ứng dụng lưu một record:

~~~text
orderId  = order-42
quantity = 3
revision = 7
~~~

Định dạng file `order-snapshot.bin`:

| Thành phần | Format | Ý nghĩa |
| --- | --- | --- |
| Magic | 4-byte int = `0x4A533031` | Nhận diện `JS01` |
| Format version | 2-byte unsigned int = `1` | Kiểm schema |
| Order ID | `DataOutputStream.writeUTF` | Modified UTF-8 của Java Data streams |
| Quantity | 4-byte int | Số lượng |
| Revision | 8-byte long | Phiên bản trạng thái |
| CRC32 | 4-byte int | Phát hiện corruption thông thường |

**CRC32 không phải MAC/chữ ký chống sửa đổi ác ý.** Nếu file có threat model attacker, cần authentication/encryption/permissions phù hợp.

### 9.1. Toàn bộ mã nguồn

Lưu file **`PersistentMemoryVsObjectStateDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.zip.CRC32;

public final class PersistentMemoryVsObjectStateDemo {
    private static final int MAGIC = 0x4A533031; // JS01
    private static final int VERSION = 1;
    private static final int MAX_BYTES = 4096;
    private static final String FILE_NAME = "order-snapshot.bin";

    private PersistentMemoryVsObjectStateDemo() {
    }

    record OrderState(String id, int quantity, long revision) {
        OrderState {
            if (id == null || id.isBlank() || id.length() > 100
                    || quantity < 0 || revision < 0) {
                throw new IllegalArgumentException(
                        "invalid order state");
            }
        }
    }

    static byte[] encode(OrderState state) throws IOException {
        var bytes = new ByteArrayOutputStream();

        try (var out = new DataOutputStream(bytes)) {
            out.writeInt(MAGIC);
            out.writeShort(VERSION);
            out.writeUTF(state.id());
            out.writeInt(state.quantity());
            out.writeLong(state.revision());
        }

        byte[] data = bytes.toByteArray();
        var crc = new CRC32();
        crc.update(data);

        return ByteBuffer.allocate(
                data.length + Integer.BYTES)
                .put(data)
                .putInt((int) crc.getValue())
                .array();
    }

    static OrderState decode(byte[] data) throws IOException {
        if (data.length < 24 || data.length > MAX_BYTES) {
            throw new IOException("invalid snapshot length");
        }

        int contentLength = data.length - Integer.BYTES;
        int storedChecksum = ByteBuffer.wrap(
                data, contentLength, Integer.BYTES).getInt();

        var crc = new CRC32();
        crc.update(data, 0, contentLength);

        if (storedChecksum != (int) crc.getValue()) {
            throw new IOException("snapshot checksum mismatch");
        }

        try (var in = new DataInputStream(
                new ByteArrayInputStream(
                        data, 0, contentLength))) {
            if (in.readInt() != MAGIC) {
                throw new IOException("invalid snapshot magic");
            }
            if (in.readUnsignedShort() != VERSION) {
                throw new IOException(
                        "unsupported snapshot version");
            }

            String id = in.readUTF();
            int quantity = in.readInt();
            long revision = in.readLong();

            if (in.read() != -1) {
                throw new IOException(
                        "unexpected trailing bytes");
            }

            try {
                return new OrderState(id, quantity, revision);
            } catch (IllegalArgumentException ex) {
                throw new IOException(
                        "invalid persisted business state", ex);
            }
        }
    }

    static void save(OrderState state) throws IOException {
        Path dest = Path.of(FILE_NAME).toAbsolutePath();
        Path dir = dest.getParent();
        Path temporary = Files.createTempFile(
                dir, ".order-snapshot-", ".tmp");

        try {
            byte[] content = encode(state);
            try (var channel = FileChannel.open(
                    temporary,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                var buffer = ByteBuffer.wrap(content);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
                channel.force(true);
            }

            try {
                Files.move(
                        temporary,
                        dest,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                throw new IOException(
                        "atomic move unsupported", ex);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    static OrderState load() throws IOException {
        byte[] bytes = Files.readAllBytes(
                Path.of(FILE_NAME));
        return decode(bytes);
    }

    static String describe(OrderState s) {
        return s.id() + "|" + s.quantity() + "|"
                + s.revision();
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "expected save or load");
        }

        switch (args[0]) {
            case "save" -> {
                var original = new OrderState("order-42", 3, 7);
                save(original);
                System.out.println(
                        "saved=" + describe(original));
            }

            case "load" -> {
                OrderState restored = load();
                OrderState expected =
                        new OrderState("order-42", 3, 7);

                System.out.println(
                        "loaded=" + describe(restored));
                System.out.println(
                        "equalValues="
                        + restored.equals(expected));
                System.out.println(
                        "sameReference="
                        + (restored == expected));
            }

            default -> throw new IllegalArgumentException(
                    "expected save or load");
        }
    }
}
~~~

### 9.2. Biên dịch/chạy hai tiến trình riêng

Thực hiện trong một **thư mục thử nghiệm mới, có quyền ghi**, không chứa file quan trọng. Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 PersistentMemoryVsObjectStateDemo.java
~~~

Chạy **JVM thứ nhất**:

~~~bash
java PersistentMemoryVsObjectStateDemo save
~~~

**Stdout chính xác nếu ghi thành công:**

~~~text
saved=order-42|3|7
~~~

File `order-snapshot.bin` lúc này là **logical state đã encode**. Java object `original` ở tiến trình thứ nhất không còn tồn tại như object sống sau khi tiến trình đó kết thúc.

Chạy **JVM thứ hai** trong cùng thư mục, sau khi lệnh trên đã kết thúc:

~~~bash
java PersistentMemoryVsObjectStateDemo load
~~~

**Stdout chính xác:**

~~~text
loaded=order-42|3|7
equalValues=true
sameReference=false
~~~

Giải thích:

1. JVM mới đọc file, kiểm magic, schema version, CRC32, giới hạn kích thước và dữ liệu.
2. JVM mới gọi constructor của `OrderState` để tạo record `restored`. Đây **không** phải phép phục hồi memory address của object trong JVM trước.
3. `expected` là record **khác** được tạo trong JVM mới để kiểm logic.
4. `equals==true` vì hai record có cùng các thành phần giá trị.
5. `==false` vì `restored` và `expected` là hai references tới hai object khác nhau.
6. Nếu file bị xóa, truncate, sửa checksum hoặc version không khớp, chương trình báo lỗi thay vì giả định có thể khôi phục.
7. `writeUTF` dùng **modified UTF-8** trong Java Data streams, nên không khẳng định format có thể trao đổi nguyên trạng như chuẩn UTF-8 chung của mọi ngôn ngữ.

### 9.3. Demo có bảo đảm không mất dữ liệu khi mất điện không?

**Không bảo đảm toàn diện.** Ví dụ đã dùng nhiều bước tốt:

- Tạo temp file trong cùng thư mục.
- Ghi toàn bộ bytes, checksum.
- Gọi `FileChannel.force(true)`.
- Dùng `Files.move` với `ATOMIC_MOVE`.
- Validate format khi load.

Nhưng vẫn có giới hạn:

- **Atomic rename không nhất thiết là durable rename**. Một filesystem có thể cần đồng bộ directory metadata sau move.
- Không có một cách portable Java SE duy nhất để bảo đảm đồng bộ directory entry trên mọi OS/filesystem.
- `ATOMIC_MOVE` có thể không được hỗ trợ; code cố ý ném `IOException` thay vì âm thầm coi move thường là atomic.
- Khi target đã tồn tại, ngữ nghĩa overwrite của atomic move phụ thuộc provider; production phải kiểm.
- Demo không có concurrent-writer coordination, multi-record transaction, backup hay replication.
- File size được kiểm **sau khi `readAllBytes`**; với file từ nguồn không tin cậy hoặc kích thước lớn, cần giới hạn size trước/đọc streaming để bảo vệ memory.
- CRC32 chỉ phát hiện corruption thông thường, **không** bảo vệ trước attacker có thể thay file.

Do đó, chương trình này minh họa **save/restore qua hai JVM**, không phải một cơ sở dữ liệu giao dịch hay chứng nhận zero-data-loss.

## 10. Trường hợp một ứng dụng thật cần recovery phức tạp

### 10.1. Một snapshot chưa đủ cho nhiều bản ghi

Nếu ứng dụng có hàng triệu orders, balances và relations, một file đơn giản không tự giải quyết:

- Concurrent updates.
- Partial writes và crash sau bước ghi thứ nhất.
- Transaction atomicity trên nhiều records.
- Data deduplication và ID generation.
- Snapshot versioning và schema migration.
- Backup/replication và disaster recovery.
- Indexing và phục hồi nhanh.
- Encryption, authorization và audit.

Khi có yêu cầu giao dịch, hãy cân nhắc **database transaction/WAL** thay vì xây một heap persistence engine từ đầu.

### 10.2. Đừng serialize tất cả object tùy tiện

Phân loại state:

~~~text
Nguồn dữ liệu bền vững:
  Orders, payments, balances, audit records

Dữ liệu có thể tái tạo:
  Index, cache, compiled query plans, projections

Runtime resources:
  Thread, socket, JDBC connection, executor,
  process-local lock, native pointer

Chỉ nhóm state thật sự cần durable mới phải được thiết kế
lưu/khôi phục theo hợp đồng dữ liệu tương ứng.
~~~

Lưu mọi object đang sống thường làm tăng kích thước snapshot, ràng buộc class versions và lưu cả những objects/cache không cần thiết.

### 10.3. Java Serialization là một công cụ, không phải bảo đảm durability

Dù gọi `out.writeObject(state)` thành công, vẫn phải bảo đảm output file/storage đã commit, compatibility và recovery policy. Java serialization chỉ định format của stream, không tự thay thế fsync/WAL/database commit.

### 10.4. Tham chiếu logic thay cho con trỏ

Nếu `Order` có `customer`, format có thể lưu `customerId`, khi khôi phục dùng repository đọc đúng `Customer` rồi nối liên hệ. Đừng persist JVM pointer address hoặc giả định một địa chỉ ảo luôn biểu diễn cùng object.

### 10.5. Checkpoint/restore tiến trình là một chủ đề riêng

Công nghệ checkpoint/restore có thể phục vụ mục tiêu giảm startup hoặc phục hồi một phần trạng thái tiến trình trong môi trường nhất định, nhưng có ràng buộc với JVM, OS, JDK build, sockets, file descriptors và security. **JEP 316 không cung cấp một checkpoint/restore API Java SE phổ quát.**

Không dùng thuật ngữ checkpoint như một cách gọi khác của “heap nằm trên NVM”.

## 11. Container/Kubernetes: volume bền vững khác heap bền vững

Trong container, dù host dùng SSD hoặc persistent memory, file ghi vào **ephemeral container layer** có thể mất khi Pod/container bị thay thế.

Để lưu logical state qua Pod lifecycle, dùng database hoặc storage volume có hợp đồng tồn tại phù hợp (ví dụ Kubernetes PersistentVolume/PersistentVolumeClaim) và xác minh backup/restore.

~~~text
JVM heap backed by NVM device
    KHÁC
file snapshot trên PVC
    KHÁC
database transaction đã commit
    KHÁC
object graph của JVM mới sau restore
~~~

Một PVC bền vững không tự tạo ACID transaction; nó chỉ là lớp storage. Còn `-XX:AllocateHeapAt` không thay đổi chuỗi trách nhiệm lưu/khôi phục dữ liệu ứng dụng.

### Container bị OOMKill có còn objects không?

Không tự động. Kernel có thể kết thúc Java process, JVM mới sẽ khởi tạo heap mới. Chỉ những state đã ghi/commit và có storage tồn tại phù hợp mới có thể được ứng dụng khôi phục theo schema. Nếu backing device giữ byte, JEP 316 vẫn **không** tự cung cấp object recovery.

## 12. Quy trình thiết kế và kiểm thử durability

### Bước 1: Định nghĩa hợp đồng

Ví dụ:

~~~text
Sau khi API trả "confirmed":
  trạng thái order phải tồn tại sau JVM restart.
  status/quantity/total phải nhất quán.
  không được mất hoặc nhân đôi payment transaction.
~~~

Trước khi nói “persist”, định nghĩa **khi nào commit được xem thành công** và failure model (JVM crash, OS crash, power failure, node loss).

### Bước 2: Chọn storage đúng mục đích

- File cấu hình ít thay đổi: versioned atomic replace.
- Business transaction: database có transaction và WAL.
- Audit/event stream: durable log với offsets/commit.
- Cache: có thể tái tạo sau restart.
- Dữ liệu NVM bytes chuyên biệt: NVM-aware storage engine với layout/flush/recovery.

### Bước 3: Xác định format và migration

Gắn magic/version hoặc schema name/version, stable business IDs, required fields, length bounds, checksum và validation. Xây logic migrate khi thêm/xóa fields. Không lưu nguyên raw memory layout Java.

### Bước 4: Thiết kế commit/crash consistency

Định nghĩa thứ tự write, flush, commit marker, atomic publish, rollback/replay và retry idempotency. Kiểm hệ storage local/remote và điều kiện directory durability. Đừng dùng `Files.writeString` đơn lẻ như bằng chứng dữ liệu đã durable trong mọi failure mode.

### Bước 5: Khôi phục có kiểm tra

Khi khởi động JVM mới:

1. Đọc state từ durable storage.
2. Kiểm integrity, version và giới hạn.
3. Migrate schema nếu hợp đồng cho phép.
4. Tạo objects mới với constructor/validation.
5. Rebuild caches/indexes, mở lại connections.
6. Replay/rollback transaction chưa hoàn tất.
7. Công bố ứng dụng ready sau khi phục hồi thành công.

### Bước 6: Thử các failure windows

Thực hành trong môi trường **cách ly**, không phá dữ liệu thật:

- JVM restart bình thường.
- SIGKILL giữa hai writes.
- Hỏng/truncate snapshot file.
- Disk full hoặc permission denied.
- Storage unavailable.
- Schema upgrade không tương thích.
- Pod reschedule sang node khác.
- Transaction retry/duplicate execution.
- Crash ngay sau khi trả response nhưng trước durable commit.
- Restore từ backup khi disk hỏng.

Chỉ một phép thử restart thành công không chứng minh hệ thống sẽ chịu được mọi power loss.

## 13. Bảng quyết định nhanh

| Mục tiêu thật | Công cụ/thiết kế phù hợp | Không nên dựa vào |
| --- | --- | --- |
| Tăng dung lượng live Java heap trên thiết bị khác | `-XX:AllocateHeapAt` khi được JDK/hardware hỗ trợ | Hiểu nhầm thành snapshot |
| Persist một cấu hình/versioned record | Java NIO file I/O + schema + flush/atomic publish | Raw object memory |
| Persist tiền/giao dịch | Database/WAL/transaction | Một lần gọi `System.gc()` |
| Rebuild cache sau restart | Dữ liệu nguồn + cache warm-up | Serialize toàn bộ heap |
| Lưu byte trên NVM map | `MappedByteBuffer`, NVM mapping phù hợp | Coi map = object DB |
| Truy cập native memory an toàn trên Java 22+ | `Arena`/`MemorySegment` | Coi memory lifetime = persistence |
| Phục hồi object values qua JVM khác | Decode/validate thành objects mới | Memory addresses/`==` |
| Bảo vệ dữ liệu sau node failure | Backup/replication + storage durability policy | Chỉ non-volatile device trên một node |

## 14. Các lỗi phổ biến khi học chủ đề này

| Nhận định | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| NVM còn byte nên JVM tiếp tục từ object cũ | Class/GC/threads/heap roots không được phục hồi | Explicit state recovery |
| `AllocateHeapAt` là lệnh lưu snapshot | Nó chỉ chọn nguồn memory cho live heap | Dùng storage riêng |
| Heap ở NVM thì không có GC | GC vẫn quản lý object liveness | Tối ưu/tune GC như bình thường |
| `volatile` field tự sống qua reboot | Java volatile là visibility/order | Dùng file/DB commit |
| `-Xmx` quyết định dung lượng snapshot | Xmx là giới hạn heap | Storage file có logic riêng |
| Lưu object pointer rồi mở lại | Địa chỉ ảo không ổn định và không là ID | Lưu business key |
| Flush field A bảo đảm transaction A+B | Atomicity nhiều writes chưa có | WAL/transaction |
| MappedByteBuffer là persistent Java object store | Chỉ map file bytes | Schema và decode |
| `FileChannel.force` luôn là DB commit | Chỉ đồng bộ trong phạm vi API | Transaction/atomicity riêng |
| Atomic rename luôn bền vững sau mất điện | Directory entry có thể cần sync | Kiểm filesystem |
| Serializable tự lưu mọi object | Phải thực sự dùng output stream | Explicit save |
| Deserialization data từ mạng luôn an toàn | Có thể khai thác classpath | Avoid/filter/validation |
| Sau load, `==` phải true | Objects được tạo mới | So values/IDs |
| CRC32 là chữ ký an ninh | Không có khóa | Dùng MAC/signature phù hợp |
| NVM luôn có cùng latency với DRAM | Hardware tiers khác | Benchmark |
| Java 17 có FFM final API | FFM final từ Java 22 | Dùng Java 17 NIO cho demo |
| Một bản snapshot là database hoàn chỉnh | Thiếu concurrency/transaction/replication | Storage engine hợp lệ |
| PVC tự tạo transaction cho state | PVC là storage layer | Commit protocol |
| Một crash test thành công là đủ | Nhiều failure windows | Test có hệ thống |

## 15. Checklist khi code review

- [ ] Đã nói rõ đây là **physical byte retention** hay **application state recovery**?
- [ ] Không tuyên bố JEP 316 tự khôi phục Java heap sau restart?
- [ ] Kiểm JDK/OS/hardware và điều kiện `AllocateHeapAt` trước khi triển khai?
- [ ] Không nhầm DRAM, NVM, SSD, DAX và file mapping?
- [ ] Không persist memory addresses hoặc JVM internal metadata?
- [ ] Có schema version, magic, giới hạn file/record và validation?
- [ ] Có checksum hoặc integrity thích hợp với threat model?
- [ ] Có storage bền vững xuyên lifecycle Pod/host theo yêu cầu?
- [ ] Có commit/force/atomic publish và hiểu giới hạn durability?
- [ ] Có transaction khi nhiều records liên quan?
- [ ] Có migration và backup?
- [ ] Tránh deserialize không tin cậy?
- [ ] Có kế hoạch mở lại runtime handles sau restore?
- [ ] Đã kiểm nhiều failure windows trong môi trường thử?
- [ ] Đã đo hiệu năng/GC nếu sử dụng alternative memory thật?
- [ ] Có phân biệt RPO/RTO và yêu cầu phục hồi?

### 15.1. Câu hỏi tự kiểm tra

**Câu 1.** JDK 10 JEP 316 cho phép điều gì?

**Đáp án:** Đặt live Java object heap trên thiết bị nhớ thay thế phù hợp bằng `-XX:AllocateHeapAt`.

**Câu 2.** Heap trên NVDIMM có tự khôi phục Java object sau restart không?

**Đáp án:** Không. JEP 316 không cung cấp schema, object IDs, roots hay runtime recovery.

**Câu 3.** Java `volatile` có làm data survive power failure không?

**Đáp án:** Không; `volatile` quản lý thread visibility/ordering.

**Câu 4.** Khi decode snapshot ở process mới, object cũ có được sử dụng trực tiếp không?

**Đáp án:** Không, JVM tạo những objects mới từ persisted logical data.

**Câu 5.** `ObjectOutputStream` còn hỗ trợ không?

**Đáp án:** Có, nhưng phải chủ động ghi stream, có rủi ro bảo mật với input không tin cậy và cần quản lý compatibility.

**Câu 6.** `MappedByteBuffer.force()` có tự tạo multi-object transaction?

**Đáp án:** Không. Nó liên quan đồng bộ mapped bytes; transaction cần thiết kế riêng.

**Câu 7.** CRC32 có chống sửa dữ liệu ác ý không?

**Đáp án:** Không; chỉ phát hiện corruption phổ biến.

**Câu 8.** Có thể phục hồi object bằng `System.identityHashCode` cũ không?

**Đáp án:** Không. Nó không phải persistent object ID xuyên tiến trình.

**Câu 9.** Vì sao cần schema version?

**Đáp án:** Vì ứng dụng/class có thể nâng phiên bản và định dạng lưu trữ cần hỗ trợ kiểm/migrate.

**Câu 10.** File snapshot trên container ephemeral có bảo đảm còn khi Pod bị thay thế không?

**Đáp án:** Không. Cần persistent storage/database và hiểu failure semantics.

**Câu 11.** Vì sao atomic rename chưa chắc durable qua mất điện?

**Đáp án:** Metadata của directory có thể chưa sync theo filesystem/OS.

**Câu 12.** Một chương trình Java 17 muốn persist state mà không có NVDIMM thì làm thế nào?

**Đáp án:** Lưu file/DB có schema và commit rõ ràng, restart đọc/validate rồi tạo objects mới.

## 16. Nguồn chính thức vẫn áp dụng

- [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): mục tiêu của tính năng Java 10 liên quan memory placement.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:AllocateHeapAt` còn được tài liệu hóa; mô tả các phần khác ở DRAM.
- [OpenJDK mainline — java launcher source documentation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): mô tả hiện hành của `AllocateHeapAt`.
- [Oracle Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, file mapping, read/write và giới hạn local/remote.
- [Oracle Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): mapped memory và `force()`.
- [Oracle Java SE 25 — ExtendedMapMode](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_WRITE_SYNC`/`READ_ONLY_SYNC` khi NVM mapping được hỗ trợ.
- [Oracle Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): Java object serialization stream.
- [Oracle Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): reconstruct objects từ stream và cảnh báo input.
- [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): hợp đồng object graph và compatibility.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): lọc dữ liệu deserialize khi bắt buộc dùng.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): các mapped modes cho NVM từ Java 14.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API chuẩn từ Java 22 cho native memory, không tự bảo đảm persistence.
- [Oracle Java SE 17 — Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): atomic file move và những giới hạn triển khai.
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/): storage lifecycle và quyền sử dụng PVC.

**Kết luận:** **Non-volatile memory** có thể giữ byte vật lý; **Java heap trên NVM** vẫn là heap được JVM/GC quản lý trong một tiến trình. JEP 316 **không** tự biến object thành bản ghi bền vững. Muốn sau restart có lại state, phải **encode thành định dạng có schema, ghi và commit theo yêu cầu storage, kiểm integrity, rồi decode/tạo objects mới**. Phân biệt đúng ba tầng vật lý, giao dịch và khôi phục giúp tránh sai lầm nghiêm trọng trong thiết kế Java systems.