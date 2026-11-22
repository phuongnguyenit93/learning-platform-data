# Quyền đọc ghi, thời gian sống, flush dữ liệu và giới hạn do hệ điều hành khi làm việc với bộ đệm và tệp

## 1. Bài toán: ánh xạ tệp vào bộ nhớ không biến tệp thành một mảng Java bình thường

Java có nhiều cách thao tác bytes của tệp: `Files.readAllBytes`, `InputStream`/`OutputStream`, `FileChannel.read`/`write`, `ByteBuffer` và **memory-mapped file**. Trong Java Foreign Function & Memory API (FFM), một ánh xạ tệp có thể được biểu diễn bằng `MemorySegment`. Điểm khác biệt lớn: khi ánh xạ tệp, **JVM và hệ điều hành phối hợp quản lý vùng địa chỉ, trang nhớ, quyền truy cập và việc đẩy thay đổi trở lại thiết bị lưu trữ**.

Vì vậy, có ít nhất bốn câu hỏi phải trả lời trước khi dùng một vùng nhớ ánh xạ:

1. **Quyền đọc/ghi:** tệp được mở `READ`/`WRITE` như thế nào và vùng ánh xạ được tạo bằng `READ_ONLY`, `READ_WRITE` hay `PRIVATE`? Có thể đọc? Có thể ghi? Thay đổi có vào file gốc không?
2. **Thời gian sống:** mapping được gắn với `Arena` hay `MappedByteBuffer`? Đóng `FileChannel` có làm mất mapping? Khi nào phải unmap để có thể giải phóng tài nguyên?
3. **Flush/durability:** một phép `set`/`put` vào mapped memory đã đảm bảo bytes an toàn trên ổ đĩa chưa? Khi nào cần `MemorySegment.force()`, `MappedByteBuffer.force()` hoặc `FileChannel.force(...)`?
4. **Giới hạn hệ điều hành:** page cache, không gian địa chỉ, tệp thay đổi kích thước, filesystem/network, quyền OS, ổ đĩa đầy, khóa tệp và nhiều tiến trình cùng ghi có thể ảnh hưởng điều gì?

Các câu hỏi ấy **độc lập**: vùng nhớ có thể còn sống và ghi được nhưng thay đổi chưa durable; vùng nhớ có thể còn sống theo `Arena` nhưng tệp đã bị một tiến trình khác rút ngắn; `force()` có thể trả về mà không tạo một transaction dữ liệu nguyên tử.

**Phiên bản trong bài:** FFM `FileChannel.map(MapMode, long, long, Arena)` trả về `MemorySegment` được bổ sung từ **JDK 22**. Các đoạn Java dùng `java.lang.foreign.` cần **JDK 22+** (FFM final theo JEP 454). Phần `MappedByteBuffer` truyền thống và `FileChannel.force` có thể dùng trên **Java 17+**. Không copy ví dụ `MemorySegment` vào Java 17 mà không thay API.

## 2. Mô hình dữ liệu: file bytes, mapped view và page cache

Ví dụ file dài 16 byte được map thành một `MemorySegment`:

```text
Ứng dụng Java                     Hệ điều hành / file system
┌────────────────────────┐
│ FileChannel            │
│  .map(READ_WRITE,      │
│       0, 16, arena)    │
│         │              │
│         ▼              │
│  MemorySegment         │         Virtual memory mapping
│  [byte 0 ... byte 15] ├────────► [trang nhớ/page cache]
│       │                │                    │
│       ├── get/set      │                    │ dirty pages
│       └── force() ─────┼────────────────────┤ flush request
└────────────────────────┘                    ▼
                                         File contents
                                       trên thiết bị lưu trữ
```

`FileChannel.map` không giống `Files.readAllBytes` ở chỗ nó không bắt buộc tạo một bản sao `byte[]` chứa toàn bộ file trong Java heap. Hệ điều hành thiết lập một **virtual memory mapping** liên kết vùng địa chỉ của tiến trình với nội dung file; hệ điều hành có thể nạp trang nhớ khi truy cập và dọn trang theo chính sách cache.

Cần phân biệt:

- **Mapped view:** địa chỉ và giới hạn mà Java dùng để đọc/ghi.
- **Resident pages:** các trang hiện ở bộ nhớ vật lý, có thể thay đổi theo thời gian.
- **Dirty pages:** trang bị sửa và đang chờ đồng bộ về storage theo cơ chế OS.
- **Persistent storage:** bản dữ liệu trên filesystem/thiết bị; có thể có cache/metadata/khả năng lỗi riêng.
- **File descriptor/channel:** handle Java/OS dùng để mở, map và điều phối I/O. Đóng nó không đồng nghĩa mọi mapped view đã bị hủy.

**Không được suy** rằng “đọc từ memory map không bao giờ xảy ra I/O”. Một page fault có thể kích hoạt đọc trang từ storage. Cũng không suy “ghi một byte trong mapped view thì disk đã ghi xong”: hệ điều hành thường trì hoãn writeback.

## 3. Hai lớp quyền: open options và map mode

### 3.1. Mở FileChannel với quyền phù hợp

`FileChannel.open(path, options...)` quyết định Java channel được phép đọc/ghi. Ví dụ:

```java
FileChannel readOnlyChannel = FileChannel.open(
        path, StandardOpenOption.READ);

FileChannel readWriteChannel = FileChannel.open(
        path, StandardOpenOption.READ,
        StandardOpenOption.WRITE);
```

Đây là **fragment**, cần các imports `FileChannel`, `Path` và `StandardOpenOption` cùng biến `path`. Quyền mở còn phải phù hợp **quyền filesystem/ACL** thực tế: khai báo `WRITE` không giúp vượt qua quyền OS.

Đối với `FileChannel.map` chuẩn:

| Map mode | Channel tối thiểu theo API | Vùng ánh xạ có ghi được? | Ghi có được đưa vào file gốc? |
| --- | --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | Mở **READ** | **Không** | Không có ghi |
| `FileChannel.MapMode.READ_WRITE` | Mở **READ + WRITE** | **Có** | Các sửa đổi được truyền về tệp; có thể cần `force()` để bảo đảm writeback |
| `FileChannel.MapMode.PRIVATE` | Mở **READ + WRITE** | **Có** (copy-on-write) | **Không** truyền thay đổi riêng sang file gốc |

**Điểm dễ nhầm:** `PRIVATE` vẫn đòi hỏi channel mở cả READ và WRITE theo Java FileChannel contract, mặc dù các ghi vào private mapping **không** phải ghi trực tiếp sang file gốc.

Nếu bạn mở channel chỉ với `READ` rồi gọi `map(READ_WRITE, ...)` hoặc `map(PRIVATE, ...)`, kỳ vọng `NonWritableChannelException`. Mở channel không cho đọc mà map `READ_ONLY` có thể gây `NonReadableChannelException`.

Đây là **lỗi quyền ở lớp Java channel**, khác với `AccessDeniedException` hoặc `IOException` khi OS không cho mở tệp ở lớp filesystem.

### 3.2. Quyền của segment sau khi map

Trong JDK 22+:

```java
MemorySegment readOnly = channel.map(
        FileChannel.MapMode.READ_ONLY, 0L, bytes, arena);

System.out.println(readOnly.isReadOnly()); // true
```

Đây là **fragment**, `channel` phải mở READ, `bytes` là độ dài hợp lệ và `arena` còn sống. Ghi vào segment này qua `set` sẽ bị chặn; theo `MemorySegment` API, read-only write gây `IllegalArgumentException`.

Nếu đang dùng NIO `MappedByteBuffer`:

```java
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_ONLY, 0L, bytesAsInt);

buffer.put(0, (byte) 1); // ReadOnlyBufferException
```

Đây là **fragment**, `bytesAsInt` phải nằm trong giới hạn `int` cho buffer và channel có quyền READ. Cùng ý nghĩa quyền truy cập, nhưng **loại exception của buffer và segment không nhất thiết giống nhau**.

### 3.3. View read-only không đổi quyền của các view khác

`MemorySegment.asReadOnly()` tạo một **read-only view** của segment; nó **không** sửa file permissions trên OS và **không** biến các aliases khác của cùng backing bytes thành read-only.

```java
MemorySegment writable = /* mapped READ_WRITE */;
MemorySegment roView = writable.asReadOnly();

System.out.println(roView.isReadOnly()); // true
System.out.println(writable.isReadOnly()); // false
```

Đây là fragment thể hiện semantics, không phải mã có thể biên dịch nguyên xi do phần tạo `writable` chưa được cung cấp. Nếu một thread/process khác vẫn có writable mapping tới file, việc Java giữ `roView` **không ngăn** bên kia sửa dữ liệu.

## 4. READ_ONLY, READ_WRITE và PRIVATE: chọn đúng mục đích

### 4.1. READ_ONLY: đọc và kiểm tra nội dung file

Phù hợp khi ứng dụng chỉ parse file, tra cứu chỉ mục, đọc metadata/bảng dữ liệu không cần sửa. Thường dùng:

```java
try (FileChannel ch = FileChannel.open(path,
        StandardOpenOption.READ);
     Arena arena = Arena.ofConfined()) {

    long length = ch.size();
    MemorySegment mapped = ch.map(
            FileChannel.MapMode.READ_ONLY,
            0L, length, arena);

    // ... Chỉ get/copy dữ liệu, không gọi set ...
}
```

Đây là **fragment nằm trong method có throws IOException**; `path` có sẵn. Nếu file rỗng, mapping size 0 không hữu ích để đọc; ứng dụng cần xử lý trường hợp `length == 0` một cách rõ ràng.

Read-only mapping không đồng nghĩa file **bất biến**: bên khác có thể sửa bytes, truncate hoặc thay file theo cách mà thời điểm quan sát thay đổi tùy OS. Nếu xử lý file untrusted hoặc thay đổi đồng thời, phải thiết kế thêm cơ chế snapshot/version/lock phù hợp.

### 4.2. READ_WRITE: sửa file thông qua vùng nhớ

Phù hợp cho index, tệp trạng thái, cơ sở dữ liệu tùy thiết kế hoặc xử lý binary data cần cập nhật tại chỗ.

```java
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L, fileLength, arena);

mapped.set(ValueLayout.JAVA_BYTE, 0L, (byte) 42);
mapped.force();
```

Đây là fragment; `channel` mở READ+WRITE, file đủ dài, `arena` hợp lệ. `force()` **đẩy những thay đổi của mapped segment tới thiết bị lưu trữ theo hợp đồng API trên local storage**. Nó không biến nhiều field writes thành một transaction nguyên tử hoặc phối hợp các tiến trình độc lập.

Nếu ứng dụng cần crash consistency cho nhiều fields, hãy dùng journal/WAL, checksum, copy-on-write file format hoặc transaction protocol riêng thay vì chỉ dựa vào `force()`.

### 4.3. PRIVATE: copy-on-write, không ghi vào file gốc

`MapMode.PRIVATE` tạo ánh xạ **copy-on-write**. Khi ứng dụng sửa mapped region, OS có thể tạo bản sao trang của các byte bị sửa cho view này. Những thay đổi đó:

- Có thể đọc lại trong private view của chính chương trình.
- **Không** được propagated sang file gốc.
- Không phải cơ chế commit; `force()` trên private mapping có thể **không có tác dụng** theo Javadoc.
- Không thay thế một bản snapshot bất biến/transactional của toàn bộ file khi file gốc bị bên khác thay đổi đồng thời; các chi tiết đồng bộ/visibility do OS quyết định.

```java
MemorySegment privateView = channel.map(
        FileChannel.MapMode.PRIVATE, 0L, size, arena);

privateView.set(ValueLayout.JAVA_BYTE, 4L, (byte) 99);

// Sửa ở privateView != ghi dữ liệu 99 vào file gốc.
```

Đây là fragment. Trên Windows/Linux/macos, cách OS cấp phát/sao chép trang khác nhau; code đúng phải dựa trên contract **không propagate private writes** thay vì đoán số lượng pages đã copy.

### 4.4. Khi nào không nên dùng memory mapping?

Đối với file rất nhỏ chỉ đọc một lần, `Files.readAllBytes` đơn giản hơn. Đối với luồng dữ liệu liên tục, network streams hoặc append-only logging có nhu cầu điều khiển rõ ràng, `FileChannel.read/write` hoặc buffered I/O có thể dễ quản lý hơn.

Memory mapping thường phù hợp **random access**, đọc lặp nhiều lần hoặc chia sẻ byte storage giữa hệ điều hành và ứng dụng, nhưng không miễn phí: phải quản lý mapping lifetime, file changes và các ràng buộc OS.

## 5. Ví dụ đầy đủ JDK 22+: quyền, arena lifetime, force và PRIVATE

Ví dụ tạo **một tệp tạm đúng 16 byte**, map nó ba lần trong cùng một `Arena`:

1. `READ_WRITE` để ghi bytes.
2. `READ_ONLY` để kiểm tra giá trị và chứng minh không thể ghi.
3. `PRIVATE` để thay một byte theo copy-on-write và xác nhận **file gốc không đổi**.

Để output không phụ thuộc endian của CPU, `int` được lưu bằng `ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN)`.

**Tệp `MappedRightsDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

public final class MappedRightsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-rights-", ".bin");

        try {
            // Quy định chính xác độ dài file trước khi map.
            Files.write(file, new byte[16]);

            var intBE = ValueLayout.JAVA_INT_UNALIGNED
                    .withOrder(ByteOrder.BIG_ENDIAN);

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 Arena arena = Arena.ofConfined()) {

                MemorySegment readWrite = channel.map(
                        FileChannel.MapMode.READ_WRITE,
                        0L, 16L, arena);

                System.out.println(
                        "mapped: " + readWrite.isMapped());
                System.out.println(
                        "rw readOnly: " + readWrite.isReadOnly());

                readWrite.set(intBE, 0L, 0x11223344);
                readWrite.set(ValueLayout.JAVA_BYTE, 4L, (byte) 7);

                // Buộc những sửa đổi trên READ_WRITE mapping
                // xuống local storage theo hợp đồng force().
                readWrite.force();

                MemorySegment readOnly = channel.map(
                        FileChannel.MapMode.READ_ONLY,
                        0L, 16L, arena);

                System.out.println(
                        "readOnly: " + readOnly.isReadOnly());
                System.out.printf(Locale.ROOT,
                        "readOnly int: %08X%n",
                        readOnly.get(intBE, 0L));

                try {
                    readOnly.set(
                            ValueLayout.JAVA_BYTE, 5L, (byte) 9);
                } catch (IllegalArgumentException ex) {
                    System.out.println(
                            "read-only write: rejected");
                }

                MemorySegment privateView = channel.map(
                        FileChannel.MapMode.PRIVATE,
                        0L, 16L, arena);

                privateView.set(
                        ValueLayout.JAVA_BYTE, 4L, (byte) 99);

                System.out.println(
                        "private byte4: " +
                        Byte.toUnsignedInt(privateView.get(
                                ValueLayout.JAVA_BYTE, 4L)));

                System.out.println(
                        "rw byte4: " +
                        Byte.toUnsignedInt(readWrite.get(
                                ValueLayout.JAVA_BYTE, 4L)));
            }
            // Arena đóng -> mapping được unmap;
            // Channel cũng đóng -> OS file handle được giải phóng.

            byte[] persisted = Files.readAllBytes(file);
            System.out.println(
                    "file byte4: " +
                    Byte.toUnsignedInt(persisted[4]));
        } finally {
            // Xóa file sau khi mọi mapping của demo đã đóng.
            Files.deleteIfExists(file);
        }
    }
}
```

**Biên dịch/chạy với JDK 22+:**

```bash
javac MappedRightsDemo.java
java MappedRightsDemo
```

Không cần `--enable-preview` đối với FFM API chính thức từ JDK 22. Ví dụ không gọi restricted FFM methods như `Linker.downcallHandle` hay `MemorySegment.reinterpret`, nên không cần cấp `--enable-native-access` chỉ để sử dụng `FileChannel.map(..., Arena)`.

**Stdout dự kiến khi hệ thống tệp hỗ trợ mapping và lệnh chạy thành công:**

```text
mapped: true
rw readOnly: false
readOnly: true
readOnly int: 11223344
read-only write: rejected
private byte4: 99
rw byte4: 7
file byte4: 7
```

### 5.1. Giải thích kết quả

- `Files.write(file, new byte[16])` làm file dài chính xác 16 byte; code **không dựa** vào hành vi map vùng vượt cuối file.
- `READ_WRITE` tạo segment mapped có thể ghi; `isMapped() == true` và `isReadOnly() == false`.
- `set(intBE, 0, 0x11223344)` ghi bốn byte đầu theo **big-endian**. Gọi `force()` để yêu cầu ghi các sửa đổi tới thiết bị lưu trữ.
- `READ_ONLY` map cùng vùng và đọc được `11223344`, nhưng `set` vào view này bị từ chối. Lỗi được bắt bằng `IllegalArgumentException` theo contract `MemorySegment`.
- `PRIVATE` lưu giá trị `99` tại byte 4 trong **copy-on-write view**, còn READ_WRITE mapping gốc vẫn thấy `7`.
- Sau khi đóng arena/channel, `Files.readAllBytes` đọc từ file thấy byte 4 là `7`, không phải `99`: thay đổi riêng không được propagate.
- Mọi đối tượng mapped segment trong ví dụ chỉ dùng **trong** try-with-resources; không lưu một `MemorySegment` vào static field để đọc sau khi arena đóng.
- `finally` dọn file temp sau khi mapping đã được đóng. Trên hệ thống không hỗ trợ map kiểu này, hoặc thiếu OS permissions/tài nguyên, chương trình sẽ ném exception thay vì in đủ các dòng thành công.

### 5.2. Vì sao dùng layout UNALIGNED trong ví dụ?

Mapped region có cơ chế căn trang do OS xử lý, nhưng **file format không nhất thiết tự bảo đảm mọi field ở offset căn hàng 4/8**. `JAVA_INT_UNALIGNED` cho phép minh họa một field 4 byte theo packed-file contract, còn `withOrder(BIG_ENDIAN)` định nghĩa cách sắp xếp byte.

**Endian, alignment, quyền truy cập và lifetime là các vấn đề khác nhau**. Thay `READ_ONLY` bằng `READ_WRITE` không sửa byte order; thay `JAVA_INT` bằng `JAVA_INT_UNALIGNED` không thay quyền ghi.

## 6. Vòng đời: Arena, FileChannel và MappedByteBuffer khác nhau

### 6.1. Với FFM MemorySegment: arena kiểm soát unmap

Trong JDK 22:

```java
try (FileChannel ch = FileChannel.open(
        path, StandardOpenOption.READ);
     Arena arena = Arena.ofConfined()) {

    MemorySegment mapped = ch.map(
            FileChannel.MapMode.READ_ONLY,
            0L, ch.size(), arena);

    // mapped còn hợp lệ trong scope arena.
}
// Arena đóng -> vùng mapping bị unmap.
```

Đây là fragment có biến `path` và import tương ứng. `FileChannel.map(MapMode, offset, size, Arena)` gắn **lifetime mapping** với `arena`, chứ không với biến Java `FileChannel`.

Do đó:

- **Đóng FileChannel sau khi map** không tự vô hiệu hóa mapped segment đã tạo. Mapped region có lifecycle riêng.
- **Đóng Arena closeable** (ví dụ `ofConfined` hoặc `ofShared`) khiến các mappings thuộc scope đó được unmap.
- **Truy cập segment sau arena.close()` vi phạm lifetime** và sẽ bị phát hiện theo `MemorySegment` scope checks; thường là `IllegalStateException`.
- Nếu dùng confined arena, chỉ thread sở hữu truy cập segment; thread khác có thể gặp `WrongThreadException`.
- Khi ứng dụng cần nhiều thread, `Arena.ofShared()` cho phép truy cập cross-thread theo luật scope nhưng vẫn cần đồng bộ **dữ liệu chia sẻ** và shutdown order đúng.

**Không đồng nhất unmap với force.** Đóng arena để ngừng dùng mapping; gọi `force()` để có yêu cầu durability. Nếu cần độ bền rõ ràng, **force trước khi đóng** và xử lý lỗi I/O. Đừng coi việc đóng scope tự động là transactional commit.

### 6.2. Với MappedByteBuffer: không có close() trực tiếp cho mapping

Phương thức truyền thống:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        0L, (int) fileSize);
```

trả `MappedByteBuffer`. Theo JDK documentation, mapping và buffer thường còn valid **cho tới khi buffer được GC thu hồi**. Không có `mapped.close()` chuẩn để chủ động unmap giống arena mapping của FFM.

Vì thế:

- Đóng `FileChannel` không tự unmap `MappedByteBuffer`.
- Giữ buffer/slices/duplicates sống có thể tiếp tục giữ mapping.
- Xóa/đổi tên tệp khi còn mapping có thể bị chặn trên một số OS (đặc biệt là các file-handle/mapping semantics của Windows).
- Không dùng `System.gc()` như lời hứa deterministic unmap.
- Nếu cần giải phóng mapping chủ động và chính xác ở Java hiện đại, cân nhắc `MemorySegment` với một closeable `Arena`.

**Lưu ý:** `ByteBuffer.clear()` không giải phóng bộ nhớ. Nó chỉ reset các con trỏ `position/limit/mark` của buffer. `MappedByteBuffer.force()` cũng không giải phóng mapping.

### 6.3. asByteBuffer của mapped MemorySegment vẫn theo arena scope

`mapped.asByteBuffer()` tạo `ByteBuffer` view để sử dụng các API NIO vốn nhận `ByteBuffer`, nhưng **vòng đời view bị ràng buộc với segment gốc**.

```java
// Fragment trong scope arena còn sống:
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, size, arena);

ByteBuffer view = mapped.asByteBuffer();
view.put(0, (byte) 42);
mapped.force();
```

Không được giữ `view` rồi dùng sau khi arena đóng. Với confined segment, thread khác cũng không tự nhiên được phép truy cập view. `ByteBuffer` có capacity kiểu `int` nên **không** thể tạo một view bao trùm segment `byteSize() > Integer.MAX_VALUE`; khi đó dùng `MemorySegment` và slices/long byte offsets thay vì ép toàn bộ thành một `ByteBuffer`.

### 6.4. Quy trình đóng đúng trong ứng dụng bất đồng bộ

Giả sử một executor đang đọc mapped segment. Đừng đóng arena ngay sau khi submit task:

```text
map region
  │
  ├── start/submit readers
  ├── stop accepting new work
  ├── wait for in-flight readers/writers
  ├── force() nếu có durable writes
  ├── close arena (unmap)
  └── close file resources / release locks
```

Với `Arena.ofShared`, cần giao thức shutdown bảo đảm không thread nào còn gọi `get/set/load/force` khi arena bị close. Với `Arena.ofConfined`, worker khác không được dùng segment trực tiếp; có thể chuyển copy/snapshot dữ liệu hoặc thiết kế lại ownership.

Một mapped segment còn được Java code tham chiếu **không được phép dùng** sau khi arena đóng: reachability của Java object không gia hạn scope.

## 7. Flush, force và durability: phân biệt ba cấp

### 7.1. Ghi bytes vào mapped memory chưa có nghĩa disk đã bền vững

`segment.set(...)` thay đổi bytes của mapped view. Trên `READ_WRITE`, OS có thể đánh dấu pages là dirty và tự ghi xuống file về sau. Điều này khác với việc gọi `force()`:

```java
mapped.set(ValueLayout.JAVA_BYTE, 7L, (byte) 1);

// Flush theo hợp đồng mapped segment:
mapped.force();
```

**`MemorySegment.force()` chỉ áp dụng cho mapped segment**; gọi trên segment bình thường từ `Arena.allocate` có thể gây `UnsupportedOperationException`.

Theo Javadoc JDK 22:
- Nếu file descriptor chỉ tới **local storage**, khi `force()` trả thành công, các thay đổi đối với vùng mapped được bảo đảm đã được ghi tới thiết bị theo phạm vi API.
- Với **non-local storage** (ví dụ network filesystem), Javadoc **không đưa ra cùng bảo đảm**.
- Với `READ_ONLY` hoặc `PRIVATE`, `force()` có thể **không có tác dụng**. PRIVATE changes không trở thành file changes chỉ bằng cách flush.
- I/O error trong `MemorySegment.force()` được báo bằng `UncheckedIOException`. Không nuốt lỗi rồi tuyên bố dữ liệu đã lưu.

**Giới hạn:** dù flush thành công trên local storage, `force()` không cung cấp transaction isolation, atomicity cho nhiều fields hay hệ thống journal/recovery logic. Nó không thay thế database transaction hoặc write-ahead log.

### 7.2. FileChannel.force(boolean) dành cho cập nhật qua channel

`FileChannel.force(metaData)` đảm bảo các cập nhật file thông qua channel được ghi ra thiết bị theo hợp đồng Java (trên local device). Tham số:

- `force(false)`: yêu cầu đồng bộ **file content**.
- `force(true)`: yêu cầu đồng bộ cả **content và file metadata** thuộc phạm vi API.

Ví dụ:

```java
// Fragment: channel mở WRITE và vừa write bytes.
channel.force(false);
```

Khi sửa qua **mapped segment**, dùng **`mapped.force()`** cho các sửa đổi của mapping; đừng mặc định `channel.force(false)` sẽ flush mọi trang bẩn của một mapping đã được tạo qua channel và có lifecycle riêng. Khi ứng dụng còn thay đổi metadata/file structure, cần thêm chính sách `channel.force(true)` nếu phù hợp.

**Không nhầm `FileChannel.force(true)` với thao tác bảo đảm atomic rename và durability của parent directory entry.** Những bảo đảm về directory fsync, atomic move, filesystem journal và power-fail nằm ngoài một lời hứa giao dịch phổ quát của FFM.

### 7.3. OutputStream.flush() / BufferedOutputStream.flush() không phải fsync

Với `BufferedOutputStream`, `flush()` chủ yếu đẩy bytes đang giữ trong **Java buffer** xuống downstream stream. Nó không bắt buộc đồng nghĩa dữ liệu đã đến thiết bị bền vững. Tương tự, C `fflush(FILE*)` chủ yếu flush C stdio buffer về OS; không đồng nhất với OS `fsync`/`FlushFileBuffers`.

Bảng:

| Lệnh | Ý nghĩa chính |
| --- | --- |
| `BufferedOutputStream.flush()` | Đẩy Java user-space buffered bytes ra downstream stream |
| `FileChannel.force(false)` | Đẩy cập nhật file content của channel xuống storage theo hợp đồng |
| `FileChannel.force(true)` | Yêu cầu đồng bộ content và metadata |
| `MappedByteBuffer.force()` | Flush dirty mapped buffer pages |
| `MemorySegment.force()` | Flush dirty mapped segment pages |
| `MemorySegment.load()` | Cố gắng nạp pages vào RAM; **không** ghi disk |
| `MemorySegment.unload()` | Cố gắng gỡ pages khỏi RAM; **không** phải “unmap” hoặc “flush” |
| `Arena.close()` | Kết thúc scope và unmap resources của arena; không phải transaction commit |

### 7.4. Một thao tác flush không bảo đảm mọi ứng dụng nhìn thấy cùng snapshot

Khi tiến trình A ghi nhiều fields vào mapping, tiến trình B có thể quan sát một phần thay đổi giữa chừng nếu không có giao thức đồng bộ. `force()` hướng tới **durability**, không tạo **atomic visibility** hoặc mutual exclusion giữa readers/writers.

Nếu file cần cấu trúc nhất quán sau crash:

1. Xác định format có header/version/checksum.
2. Viết payload mới tới vùng tạm.
3. `force` payload.
4. Commit bằng một chỉ dấu/record theo giao thức có recovery.
5. `force` trạng thái commit.
6. Khi restart, đọc và kiểm tra checksum/version, hoàn tất hoặc rollback phần dang dở.

Thứ tự chính xác tùy ứng dụng; ví dụ này là **khung tư duy**, không phải một giao thức database đã chứng minh an toàn trên mọi filesystem.

## 8. FileChannel.force với Java 17+: ví dụ độc lập không dùng mapping

Để nhìn rõ sự khác biệt giữa buffer thông thường và mapped memory, ví dụ thứ hai ghi bốn ký tự ASCII qua `ByteBuffer` và `FileChannel.write`, gọi `FileChannel.force(true)` rồi đọc lại. Nó chạy với **JDK 17+**, không cần `java.lang.foreign`.

**Tệp `ChannelForceDemo.java`:**

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ChannelForceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("channel-force-", ".txt");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.READ)) {

                ByteBuffer buffer = ByteBuffer.wrap(
                        "DATA".getBytes(StandardCharsets.US_ASCII));

                // FileChannel.write có thể ghi ít hơn số bytes còn lại.
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                // Đồng bộ data + metadata của file theo contract.
                channel.force(true);
            }

            System.out.println("file: " +
                    Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Biên dịch/chạy:**

```bash
javac ChannelForceDemo.java
java ChannelForceDemo
```

**Stdout dự kiến:**

```text
file: DATA
```

Chương trình không tạo `MemorySegment` hoặc `MappedByteBuffer`; `FileChannel.force(true)` áp dụng cho file updates qua channel. Cách dùng vòng `while (buffer.hasRemaining())` là quan trọng vì `FileChannel.write(ByteBuffer)` có thể không ghi hết bytes trong một lần gọi.

Không dùng `Files.readString` sau write làm “bằng chứng đĩa đã ghi bền vững”: nó chỉ chứng minh bytes được đọc lại qua hệ thống file hiện tại. `force(true)` mang hợp đồng writeback riêng.

## 9. MappedByteBuffer truyền thống trên Java 17+

Trước và song song với FFM, Java NIO có:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L, fileLength);
```

Đây là fragment. `MappedByteBuffer` là direct `ByteBuffer` có `position/limit/capacity` kiểu `int`, phù hợp nhiều NIO APIs hiện có. Nó có:

- `mapped.get(index)` / `mapped.put(index, byte)`: đọc/ghi byte.
- `mapped.order(ByteOrder...)`: xác định cách diễn giải values nhiều byte.
- `mapped.force()` và `mapped.force(index, length)`: yêu cầu writeback.
- `mapped.load()` / `mapped.isLoaded()`: OS residency hints.
- Không có public `close()` cho mapping, nên unmap không được kiểm soát tường minh như arena.

**Một đoạn đối chiếu:**

```java
// Fragment: channel mở READ+WRITE; file chứa ít nhất 16 byte.
MappedByteBuffer buffer = channel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 16L);

buffer.order(ByteOrder.BIG_ENDIAN);
buffer.putInt(0, 0x01020304);
buffer.force();

int same = buffer.getInt(0); // 0x01020304
```

Không nên xem `buffer.clear()` là đóng mapping. `clear()` chỉ thiết lập `position = 0`, `limit = capacity` và xóa mark (không xóa bytes).

### 9.1. Giới hạn kích thước: int cho ByteBuffer, long cho MemorySegment

NIO buffer capacity dùng `int`; `FileChannel.map(MapMode, position, size)` trả `MappedByteBuffer` có `size <= Integer.MAX_VALUE`. Mapping file 4 GiB vào **một** `MappedByteBuffer` là không hợp lệ theo API.

Trong khi đó, `FileChannel.map(MapMode, long offset, long size, Arena)` trả `MemorySegment` với kích thước `long`. Về nguyên tắc API có thể mô tả vùng trên 2 GiB, nhưng **OS và không gian địa chỉ ảo** vẫn quyết định liệu ánh xạ lớn có thành công.

Không vì thế mà gọi:

```java
// SAI nếu mapped.byteSize() > Integer.MAX_VALUE:
ByteBuffer whole = mapped.asByteBuffer();
```

Vì `ByteBuffer` có giới hạn `int`, `asByteBuffer()` trên segment quá lớn sẽ ném `UnsupportedOperationException` theo API. Thay vào đó dùng `MemorySegment.get`/`set` với `long` offsets hoặc tạo **các slices nhỏ**, có bounds hợp lệ, rồi tạo `ByteBuffer` cho từng slice.

### 9.2. Địa chỉ file và địa chỉ segment là hai offset

`channel.map(mode, fileOffset, size, arena)` có:

- `fileOffset`: offset **byte trong file**, không phải index của phần tử Java.
- `size`: số bytes được map.
- `mapped.get(layout, segmentOffset)`: offset byte **tính từ đầu mapped segment**, không phải offset tuyệt đối trong file.

Ví dụ:

```text
Map fileOffset = 4096, size = 1024
mapped.get(JAVA_BYTE, 0)    -> byte 4096 trong file
mapped.get(JAVA_BYTE, 15)   -> byte 4111 trong file
mapped.asSlice(16, 8)       -> file bytes 4112..4119
```

Muốn đọc một field tại fileOffset 4120, byte offset của mapped segment là `4120 - 4096 = 24`. Trộn các hệ tọa độ là lỗi phổ biến khi map file theo window.

## 10. File size, truncate và rủi ro lớn nhất do OS

### 10.1. Đừng map vùng vượt file size rồi dựa vào kết quả

Theo JDK 22 Javadoc, hành vi mapping một vùng **không nằm hoàn toàn trong file hiện tại** là **không được bảo đảm**. Trên một số nền tảng, mapping vượt EOF có thể dẫn tới nới file hoặc lỗi; code portable **không nên phụ thuộc** vào điều đó.

Trước khi map:

- Đọc `channel.size()` và so sánh region.
- Kiểm tra `offset >= 0`, `size >= 0` và không overflow `offset + size`.
- Đối với read-only, chỉ map bytes thực có.
- Đối với file mới sẽ ghi, **tạo/đặt kích thước file tường minh trước**; ví dụ `Files.write(path, new byte[n])` cho file nhỏ hoặc cơ chế ghi/allocate đúng cho file lớn. `FileChannel.truncate(newSize)` **không tự mở rộng file** nếu `newSize` lớn hơn kích thước hiện tại.

**Một case nguy hiểm:** code đặt channel position ở cuối rồi tưởng nó đã kéo file dài:

```java
channel.position(4096L); // Chỉ đổi vị trí, KHÔNG tăng size.
```

Muốn tăng file, cần **thao tác ghi** hoặc API được bảo đảm tạo file dài như yêu cầu. Nếu dùng sparse files, kiểm tra chính sách OS và storage allocation thực tế. Đừng tạo vùng 4 GiB bằng một `new byte[4 GiB]` trong Java.

### 10.2. File bị truncate sau khi mapping: có thể gây lỗi không xác định

Một mapping có thể đang hợp lệ và được đọc thành công, nhưng tiến trình khác gọi `truncate` làm file nhỏ lại. JDK docs cảnh báo rằng **toàn bộ hoặc một phần mapped region có thể trở nên inaccessible bất kỳ lúc nào**.

Hệ quả:

- `mapped.byteSize()` vẫn có thể báo bounds ban đầu.
- Việc đọc byte trong bounds Java chưa chắc an toàn nếu backing pages đã mất do file thay đổi.
- Javadoc chỉ hứa một **unspecified exception** có thể được ném khi truy cập hoặc muộn hơn; **không** giả định luôn `IndexOutOfBoundsException`.
- Trên hệ điều hành thực tế, lỗi mmap có thể nghiêm trọng. Đừng thiết kế bằng cách cố bắt một Java exception cụ thể để hồi phục sau concurrent truncate.

**Khuyến nghị:** mapping file phải có hợp đồng quản lý **version và thay đổi kích thước**. Nếu một tiến trình ghi file mới, cân nhắc tạo file mới, flush, rồi thay thế theo protocol ổn định thay vì truncate trực tiếp file đang có readers mapped.

### 10.3. Cùng file, nhiều tiến trình: visibility không hoàn toàn do Java kiểm soát

Javadoc FileChannel cảnh báo rằng các views file trong cùng Java program có cơ chế nhất quán nhất định, nhưng giữa các chương trình độc lập có thể chịu ảnh hưởng **filesystem cache và network protocol**. Việc thay đổi file đồng thời có thể được quan sát ở thời điểm khác nhau; không giả định có snapshot isolation.

Với file mapping được nhiều processes chia sẻ:

- Xác định ai ghi và ai đọc.
- Dùng version counters/checksums hoặc record states nếu dữ liệu phải nhất quán.
- Dùng `FileLock` khi cần phối hợp tiến trình, nhưng kiểm tra tính hỗ trợ và tính **advisory/mandatory** theo OS.
- Không kỳ vọng `force()` làm readers dừng hoặc tạo lock.
- Không dùng `MapMode.PRIVATE` làm một broadcast channel giữa processes; private writes không được propagate sang file.

## 11. Giới hạn OS: pages, virtual address space, handles và disk capacity

### 11.1. Mapping không đồng nghĩa ngay lập tức chiếm toàn bộ RAM

OS có thể map một file lớn vào **virtual address space** và nạp từng page theo nhu cầu. Việc map file dài 10 GiB **không đồng nghĩa** Java đã cấp phát 10 GiB heap hay 10 GiB RAM ngay lúc `map` trả.

Tuy vậy, không có nghĩa “map vô hạn”:

- Mapping cần một dải **virtual address space** đủ lớn và hệ điều hành phải có các page tables/resources.
- 32-bit process thường hạn chế address space hơn 64-bit; virtual fragmentation cũng có thể khiến map thất bại.
- Nhiều mappings mở đồng thời tiêu thụ tài nguyên kernel, file descriptors hoặc handle counts.
- Disk quota, filesystem capacity và trạng thái I/O có thể khiến flush/truy cập thất bại sau khi map ban đầu thành công.
- Mapping trên network filesystem có consistency/durability khác local storage.
- OS có thể giới hạn mapped address regions, page size alignment, file offsets hoặc hỗ trợ mode.
- Trên Windows, file đang mapped có thể ảnh hưởng đến rename/delete/truncate; release/unmap kịp thời là yêu cầu thực tế.

**Kết luận:** giới hạn `long` của API không phải lời hứa hệ điều hành cấp được mọi size.

### 11.2. Page size và offset alignment do implementation xử lý

Virtual memory mapping của OS thường hoạt động theo trang (ví dụ 4 KiB trên nhiều môi trường). Java `FileChannel.map` nhận `offset` tính bằng byte và implementation phải xử lý các yêu cầu OS alignment nội bộ khi có thể.

**Không** tự thêm một offset pad theo page size vào mọi phép `get` khi dùng Java mapped segment; offset Java được tính từ đầu region yêu cầu. Tuy nhiên, khi tự quản lý raw POSIX `mmap` qua C/FFM downcall, phải tuân thủ riêng yêu cầu `mmap` về page-aligned offsets. Không lấy kết luận từ API C thấp tầng áp vào ý nghĩa `FileChannel.map` cao tầng.

### 11.3. load, isLoaded, unload chỉ là gợi ý về residency

FFM mapped segment cung cấp:

```java
mapped.load();
boolean likelyResident = mapped.isLoaded();
mapped.unload();
```

Đây là fragment, `mapped` là mapped segment còn sống và accessible trên thread hiện tại.

- `load()` cố gắng đưa pages vào physical memory (prefetch); **best effort**.
- `isLoaded()` trả kết quả mang tính **hint**. `true` chỉ có nghĩa dữ liệu rất có khả năng đang resident ở thời điểm kiểm tra, không phải khóa pages trong RAM.
- `unload()` cố gắng làm pages không còn resident; **không phải unmap**, không đóng arena và không phải thủ tục flush durable writes.
- Sau `unload()`, đọc lại có thể gây page faults và OS tự tải pages trở lại.
- Không dùng `isLoaded() == true` làm bảo đảm I/O latency bằng 0 cho mọi lần đọc về sau.

Cần tối ưu page faults hãy đo trên workload/OS thật, không gọi `load()` mọi lần theo thói quen mà không benchmark.

### 11.4. Khác biệt file-system, SSD/HDD, remote và memory-backed file

Mức độ durable cụ thể phụ thuộc lớp storage. Local file JDK `force()` có hợp đồng rõ trong API; remote filesystem không có cùng bảo đảm. Với RAM disk, network share, encrypted filesystem, cloud-synced directory hoặc container overlay, hành vi thực tế có thể khác và cần kiểm thử/quy trình vận hành phù hợp.

Một lần `force()` trả thành công cũng không có nghĩa ứng dụng đã xây dựng giao thức chống **logic corruption** khi nhiều writers ghi cùng file, hay chống mọi loại hardware/controller failure. Durability, consistency và atomicity là các thuộc tính tách biệt.

## 12. Quyền OS, FileLock và đồng bộ đa luồng

### 12.1. Java quyền ghi không vượt được quyền filesystem

File có ACL chỉ đọc hoặc nằm trên filesystem được mount read-only có thể khiến `FileChannel.open(... WRITE)` thất bại, thường biểu hiện `AccessDeniedException`/`IOException` tùy provider và OS.

Ngược lại, file có quyền OS ghi được nhưng mapping `READ_ONLY` vẫn không cho Java ghi qua view. **Hai lớp kiểm tra không loại trừ nhau**.

Khi debug:

1. Xác minh path, owner và ACL.
2. Kiểm tra mount state và filesystem provider.
3. Kiểm tra `FileChannel.open` options.
4. Kiểm tra `MapMode`.
5. Kiểm tra `mapped.isReadOnly()`.
6. Kiểm tra arena alive, thread accessibility, offset/bounds.
7. Kiểm tra OS error khi `map`/`force`.

Không phản ứng với `AccessDeniedException` bằng cách tự đổi map sang `PRIVATE` rồi tưởng có quyền sửa file gốc; `PRIVATE` không commit.

### 12.2. FileLock giúp phối hợp nhưng không phải mutex RAM

`FileChannel.lock` và `tryLock` tạo file locks theo cơ chế OS. File locks có những hạn chế:

- Có thể là advisory hoặc mandatory tùy platform.
- Shared locks có thể không được hỗ trợ đầy đủ; OS có thể nâng thành exclusive.
- Locks áp dụng ở cấp VM/file theo contract Java, **không dùng để điều phối nhiều threads trong cùng JVM**.
- Lock trên một vùng file không tự làm `get/set` trên mapped pages trở thành atomic transaction.
- Nếu một external process bỏ qua advisory locks, nó vẫn có thể sửa/truncate file.

Dùng Java `synchronized`/`Lock` hoặc concurrent protocol cho threads cùng JVM; dùng file lock/protocol liên tiến trình theo OS khi cần.

### 12.3. Arena.ofShared cho phép nhiều thread nhưng không tự thread-safe hóa dữ liệu

`Arena.ofShared()` cho phép segment được truy cập từ nhiều thread, còn `Arena.ofConfined()` giới hạn thread sở hữu. **Được phép truy cập** không đồng nghĩa **không có data race**.

Hai threads cùng gọi `set(JAVA_INT, offset, ...)` trên một mapped segment mà không có protocol phù hợp có thể nhìn kết quả lẫn nhau theo ràng buộc memory ordering; đừng suy từ tên API rằng mọi multi-byte update có atomicity hoặc cross-process synchronization.

Nếu cần atomic operations, dùng access modes/VarHandle phù hợp theo layout và giới hạn ABI, hoặc khóa/giao thức riêng. Phải kiểm tra alignment và tính hỗ trợ của mapped memory, đặc biệt khi tương tác native processes.

## 13. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NonWritableChannelException` khi map `READ_WRITE` | Channel chỉ mở `READ` | Mở `READ + WRITE` và bảo đảm quyền OS |
| `NonWritableChannelException` khi map `PRIVATE` | Quên rằng PRIVATE cũng cần READ+WRITE channel | Mở đúng modes; hiểu PRIVATE không commit |
| `NonReadableChannelException` | Map yêu cầu READ nhưng channel không có | Mở channel READ |
| `AccessDeniedException` / `IOException` lúc open | ACL, mount read-only, file share lock, OS provider | Kiểm tra quyền và trạng thái filesystem |
| `IllegalArgumentException` khi `MemorySegment.set` | Segment read-only hoặc layout alignment không tương thích | Kiểm tra `isReadOnly()`, mode, alignment |
| `ReadOnlyBufferException` khi `MappedByteBuffer.put` | Map READ_ONLY | Chuyển workflow sang READ_WRITE khi thật sự được phép |
| `IllegalStateException` sau close arena | Mapped segment hết scope | Không dùng sau close; quản lý owner rõ |
| `WrongThreadException` | Confined segment dùng từ thread khác | Chỉ dùng thread owner hoặc shared arena có đồng bộ |
| `UnsupportedOperationException` ở `force/load` | Segment không phải mapped, OS/provider không hỗ trợ | Kiểm tra `isMapped()` và supported features |
| `UncheckedIOException` ở `mapped.force()` | Ghi storage thất bại | Ghi log, đánh dấu chưa durable, không nuốt exception |
| `mapped.asByteBuffer()` thất bại | Segment lớn hơn `Integer.MAX_VALUE` hoặc không tương thích | Truy cập bằng MemorySegment/long offsets hoặc chia slices |
| Mapping thành công rồi đọc lỗi sau truncate | Backing file bị thay đổi/rút ngắn | Ngăn concurrent truncate; dùng versioning/snapshot |
| Flush rồi file gốc không đổi | Đang dùng `PRIVATE` | Dùng `READ_WRITE` nếu cần write-through |
| Đóng FileChannel mà file vẫn bị giữ | Mapping còn sống | Đóng Arena (FFM) hoặc chờ GC (MappedByteBuffer) |
| File map size lớn lỗi | Hạn chế virtual memory, descriptors, disk, OS | Windowed mapping, giảm số mappings, xử lý IOException/OOME phù hợp |
| `isLoaded()==true` nhưng đọc vẫn chậm | Residency là hint, OS có thể paging | Đo page faults/I/O; không coi đây là cam kết |
| Dữ liệu sai mà không ném exception | Sai byte order, offset/stride, concurrent writes | So sánh golden bytes, schema và thread/process protocol |

### 13.1. Không nhầm FileChannel.close với giải phóng MemorySegment

Nếu muốn “đảm bảo đã unmap”, phần quan trọng của FFM là **đóng arena** và bảo đảm không references/tasks nào còn sử dụng. Channel close xử lý file descriptor, không phải mapping scope. Với `MappedByteBuffer`, không có API close chuẩn nên file locks/renames có thể kéo dài hơn bạn dự kiến.

### 13.2. Không bắt một loại exception duy nhất cho mọi lỗi I/O

Lỗi có thể đến từ:
- `IOException` khi `FileChannel.open/map`/file writes.
- `UncheckedIOException` khi `MemorySegment.force` hoặc `MappedByteBuffer.force`.
- `IllegalArgumentException` khi map region parameters invalid hoặc write read-only segment.
- `IllegalStateException` / `WrongThreadException` do scope/thread.
- `UnsupportedOperationException` nếu provider không hỗ trợ mapping hoặc muốn chuyển segment lớn thành ByteBuffer.
- **Unspecified exception** khi mapped region bị backing file truncate/inaccessible.

Ứng dụng production nên phân loại lỗi theo **stage** và hậu quả của nó, không tự “retry tất cả mọi exception” nếu mapped state đang không an toàn.

## 14. Kiến trúc lưu tệp an toàn: không dùng force như commit tất cả

### 14.1. Khi dữ liệu có cấu trúc

Giả sử một file gồm:

```text
[header version][recordCount][records...][checksum]
```

Nếu ghi `recordCount` trước rồi ghi records và crash ở giữa, sau restart reader có thể tin file chứa N records trong khi dữ liệu chưa đủ. Việc `force()` ở cuối không cứu được crash **xảy ra giữa các write**.

Một hướng thiết kế tốt:

- Dùng file mới/tạm đủ size.
- Ghi toàn bộ content mới.
- Validate counts, bounds, checksum.
- Flush mapped content `force()`.
- Đánh dấu file complete bằng schema có version/generation nếu cần.
- Dùng replace/rename theo khả năng **atomic move** được filesystem hỗ trợ.
- Xử lý thêm durability của metadata/directory theo yêu cầu OS (không mặc định mọi hệ đều giống nhau).
- Sau restart, parse/verify schema và có quy tắc recovery.

Đối với database/transactional store, thường ưu tiên engine đã giải quyết WAL, crash recovery, locking và durable commits. Memory mapping là một **I/O primitive**, không phải transaction manager.

### 14.2. Nhiều mapped views và thay đổi đồng thời

Nếu cùng file có nhiều writable views, việc một view ghi không cần `force()` để các views khác **có thể** nhìn thấy trong quá trình chạy, nhưng visibility/ordering giữa các process không thể suy thành “atomic commit”. `force()` hướng đến storage persistence, không phải message passing.

Khi cần nhiều readers + một writer:
- Có thể dùng immutable segments và publish generation/version.
- Tránh thay đổi file size khi readers còn mapped.
- Dùng checksum/seqlock-like protocol nếu đọc nhất quán mà không lock là yêu cầu thiết kế được kiểm chứng.
- Quy định ownership và shutdown; không để worker đang dùng mapped segment khi arena close.

### 14.3. Byte order là một phần file format

Mapped bytes không tự mang thông tin endian. Với file có field 32-bit big-endian:

```java
var i32BE = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);

int fileValue = mapped.get(i32BE, byteOffset);
```

Đây là fragment. Không đọc bằng `JAVA_INT` mặc định (native order) nếu file specification cố định big-endian; và đừng nhầm `byteOffset` với `getAtIndex` element index. Quyền đọc/ghi và flush đúng **không sửa được một schema diễn giải sai**.

## 15. Checklist triển khai production

- [ ] File mapping thật sự phù hợp workload; đã đo so với buffered I/O và `FileChannel.read/write`.
- [ ] Dùng đúng phiên bản API: `java.lang.foreign` và `FileChannel.map(...,Arena)` cần JDK 22+; NIO mapped buffer hỗ trợ JDK cũ hơn.
- [ ] Channel open options đúng: `READ_ONLY` cần READ, `READ_WRITE`/**`PRIVATE` cần READ+WRITE; OS permissions hợp lệ.
- [ ] Biết sự khác biệt giữa mapping ghi chung (`READ_WRITE`) và copy-on-write (`PRIVATE`).
- [ ] Kiểm tra `fileOffset`/`size`/`channel.size()`, overflow và bounds trước khi map.
- [ ] Không phụ thuộc map beyond EOF; file mới được tạo đủ kích thước theo cách portable.
- [ ] Quản lý `Arena` với owner rõ, đóng sau khi tasks hoàn tất; không dùng mapped segment sau close.
- [ ] Với shared segment, dùng synchronization cho data races; không trông cậy `FileLock` như Java thread lock.
- [ ] Gọi `mapped.force()` cho durable writes theo contract (local storage); xử lý `UncheckedIOException`.
- [ ] Nếu ghi qua channel, cân nhắc `channel.force(false/true)` theo nhu cầu content/metadata.
- [ ] Không hiểu `load/isLoaded/unload` là commit, prefetch guarantee hay unmap.
- [ ] Có chính sách bảo vệ khỏi concurrent truncate/replace đối với mapped files.
- [ ] Kiểm tra file locks, rename/delete, disk quota, virtual address space, memory pressure theo OS.
- [ ] Không cố lấy `asByteBuffer` từ segment quá 2 GiB; chia window/slices.
- [ ] Không giả định network filesystem có cùng force guarantee như local storage.
- [ ] Có test crash/restart, checksum/version/recovery cho data structures quan trọng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `FileChannel.open(path, READ)` rồi `map(READ_WRITE, 0, size, arena)` có hợp lệ không?  
**Đáp án:** Không; READ_WRITE mapping yêu cầu channel mở cả READ và WRITE. Nếu không, thường có `NonWritableChannelException`.

**Câu 2.** PRIVATE mapping cho phép `set` và gọi `force()`. Vậy file gốc được cập nhật chứ?  
**Đáp án:** Không. PRIVATE là copy-on-write; các thay đổi riêng không propagate sang file gốc. `force()` trên private mapping có thể không có tác dụng.

**Câu 3.** `readOnlySegment.set(...)` bị từ chối bằng loại lỗi gì trong MemorySegment API?  
**Đáp án:** `IllegalArgumentException` khi cố ghi read-only segment. Với `MappedByteBuffer.put`, lỗi là `ReadOnlyBufferException`.

**Câu 4.** Sau khi tạo `MemorySegment` bằng `FileChannel.map(..., arena)`, đóng channel rồi vẫn giữ arena mở có phải segment hết hạn ngay không?  
**Đáp án:** Không. Lifetime mapping được quản lý bởi arena. Đóng channel không tự động unmap segment đã tạo.

**Câu 5.** `Arena.close()` có đồng nghĩa `mapped.force()` và commit giao dịch nhiều field không?  
**Đáp án:** Không. Close unmap/invalidate scope; force hướng tới durable writeback; cả hai không tự tạo multi-field transaction/atomic commit.

**Câu 6.** `mapped.isLoaded() == true` bảo đảm mọi lần đọc sau đó không gặp page fault?  
**Đáp án:** Không. Đó là hint về residency ở thời điểm kiểm tra; OS có thể paging ngay sau đó.

**Câu 7.** Tại sao `FileChannel.map(mode, offset, size)` cổ điển khó xử lý một file trên 2 GiB bằng một buffer?  
**Đáp án:** `MappedByteBuffer` có capacity kiểu `int` và map size bị giới hạn bởi `Integer.MAX_VALUE`. `FileChannel.map(..., Arena)` trả `MemorySegment` dùng long size nhưng vẫn chịu giới hạn OS.

**Câu 8.** `MemorySegment` map 4 GiB rồi gọi `mapped.asByteBuffer()` để tận dụng NIO API có hợp lệ không?  
**Đáp án:** Không cho một ByteBuffer toàn vùng, vì capacity của `ByteBuffer` là int. Dùng long offsets hoặc các slices nhỏ.

**Câu 9.** Một process khác truncate file sau khi map. Segment bounds vẫn đúng; có an toàn đọc không?  
**Đáp án:** Không thể bảo đảm. Backing pages có thể inaccessible; Javadoc nêu unspecified exception khi truy cập hoặc sau đó. Phải ngăn/điều phối concurrent truncate.

**Câu 10.** `MappedByteBuffer.force`, `FileChannel.force` và `BufferedOutputStream.flush` có giống nhau không?  
**Đáp án:** Không. Các API flush ở các tầng khác nhau: mapped pages, file-channel updates và Java buffered bytes. Chúng có contracts khác nhau về durability.

**Câu 11.** `MemorySegment.load()` có bảo đảm dữ liệu được ghi bền vững xuống file không?  
**Đáp án:** Không. `load()` cố đưa pages từ file vào RAM; không flush dirty pages xuống storage.

**Câu 12.** File nằm trên network filesystem. `mapped.force()` trả bình thường có bảo đảm giống local disk không?  
**Đáp án:** Không. Javadoc chỉ bảo đảm cụ thể cho local storage; với non-local không đưa ra cùng bảo đảm.

**Câu 13.** `FileChannel.truncate(4096)` có luôn tăng file từ 128 byte lên 4096 byte không?  
**Đáp án:** Không. `truncate(size)` không thay đổi file nếu `size` lớn hơn hoặc bằng kích thước hiện có. Muốn mở rộng phải dùng phương thức ghi/thiết lập độ dài thích hợp.

**Câu 14.** Hai threads cùng ghi các fields vào `Arena.ofShared` mapped segment, có thread-safe nhờ arena shared không?  
**Đáp án:** Không tự động. Shared arena chỉ thay đổi điều kiện thread access; vẫn cần memory ordering/locks hoặc protocol nhất quán.

**Câu 15.** Gọi `force()` sau khi viết index, payload và checksum có đủ biến ba write thành commit nguyên tử khi mất điện giữa chừng không?  
**Đáp án:** Không. Cần schema với recovery/WAL hoặc giao thức commit được thiết kế và kiểm thử trên storage mục tiêu.

## 17. Tổng kết

- **Quyền:** `READ_ONLY` đọc, `READ_WRITE` ghi chung và có thể flush, `PRIVATE` copy-on-write không sửa file gốc; open options và OS permissions đều có hiệu lực.
- **Lifetime:** FFM mapped `MemorySegment` thuộc scope của `Arena`; đóng arena unmap; đóng `FileChannel` riêng không đủ. `MappedByteBuffer` kiểu cũ không có close mapping tường minh và tồn tại đến GC.
- **Flush:** `MemorySegment.force()`/`MappedByteBuffer.force()` dùng cho mapped writes; `FileChannel.force` cho channel writes; `OutputStream.flush` cho Java buffering. Mỗi API có giới hạn bảo đảm riêng.
- **OS:** page faults, page cache, filesize changes, truncate, file locks, virtual address space, quota và network filesystem có thể ảnh hưởng correctness/liveness/durability.
- **Giới hạn kích thước:** `MappedByteBuffer` dùng `int` capacity; `MemorySegment` dùng `long` size nhưng không thể vượt khả năng thực tế của OS. `asByteBuffer()` không nhận toàn bộ segment quá `Integer.MAX_VALUE`.
- **Thiết kế:** kiểm tra bounds/ownership, đồng bộ hóa writers, tránh concurrent truncate, phân biệt durability và atomicity, có checksum/version/recovery nếu file chứa dữ liệu quan trọng.

### Tài liệu chính thức

- [Oracle Java SE 22 — FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): map modes, open permissions, `map(..., Arena)`, mapped memory lifetime, truncate, `force(boolean)` và OS consistency.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `isMapped`, `isReadOnly`, `force`, `load`, `unload`, scope/thread rules và `asByteBuffer`.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared arenas, lifecycle và explicit close.
- [Oracle Java SE 22 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/MappedByteBuffer.html): force/load/isLoaded, lifetime gắn với GC và ảnh hưởng của truncation.
- [Oracle Java SE 22 — FileChannel.MapMode](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): READ_ONLY, READ_WRITE và PRIVATE copy-on-write.
- [Oracle Java SE 22 — ByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html): capacity kiểu int, position/limit, read-only exceptions và byte order.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API chính thức từ JDK 22 và cơ chế quản lý scope cho native/mapped memory.
