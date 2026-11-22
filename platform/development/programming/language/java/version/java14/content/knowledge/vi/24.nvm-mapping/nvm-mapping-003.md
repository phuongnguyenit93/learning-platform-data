# READ_ONLY_SYNC và READ_WRITE_SYNC khi ánh xạ bộ nhớ NVM trong Java

## 1. Mục tiêu: hai chế độ ánh xạ đặc biệt cho bộ nhớ không mất dữ liệu

Java NIO hỗ trợ **memory-mapped files**: thay vì liên tục gọi `read()`/`write()` trên file, chương trình tạo một `MappedByteBuffer`, rồi đọc hoặc thay đổi byte tại các vị trí trong buffer. Dữ liệu được ánh xạ đến một vùng file thông qua hệ điều hành.

Từ **JDK 14**, JEP 352 bổ sung hai chế độ ánh xạ dành riêng cho file được hỗ trợ bởi **non-volatile memory (NVM, persistent memory)**:

- **`ExtendedMapMode.READ_ONLY_SYNC`:** ánh xạ **chỉ đọc** một file được hỗ trợ bởi NVM.
- **`ExtendedMapMode.READ_WRITE_SYNC`:** ánh xạ **đọc/ghi** một file được hỗ trợ bởi NVM; thao tác `force()` trên buffer tạo bằng mode này sử dụng cơ chế **cache-line writeback** thay vì đường đi flush file device thông thường, nếu triển khai và nền tảng hỗ trợ.

Chữ `SYNC` trong tên nói về **chế độ ánh xạ đồng bộ dành cho NVM**, **không** có nghĩa mỗi lệnh `get()` hoặc `put()` sẽ tự động đồng bộ tất cả dữ liệu và cũng **không** biến cập nhật nhiều field thành giao dịch atomic.

Đây là các chế độ **JDK-specific** trong module `jdk.nio.mapmode`, **không phải** hằng số chuẩn thuộc `FileChannel.MapMode`. Các API vẫn hiện diện trong tài liệu **JDK 17, JDK 25 và JDK 26**; bài này chỉ trình bày hành vi còn được hỗ trợ hiện nay, không dựa vào một bản preview hoặc phương thức cũ đã bị loại bỏ.

Một quy tắc quan trọng xuyên suốt bài: **có API trong JDK không đồng nghĩa phần cứng, hệ điều hành và file system đang hỗ trợ ánh xạ NVM**. Phải kiểm tra khả năng thực tế và xử lý lỗi.

## 2. Cú pháp và nơi khai báo chính xác

Hằng số được định nghĩa tại:

~~~java
import jdk.nio.mapmode.ExtendedMapMode;
~~~

Cả hai có kiểu `FileChannel.MapMode`:

~~~java
FileChannel.MapMode readMode = ExtendedMapMode.READ_ONLY_SYNC;
FileChannel.MapMode writeMode = ExtendedMapMode.READ_WRITE_SYNC;
~~~

Đoạn trên là **mã minh họa đặt trong phương thức/class**, không phải một chương trình có `main` độc lập.

Chúng được dùng với method quen thuộc:

~~~java
MappedByteBuffer buffer = channel.map(mode, position, size);
~~~

Với `channel` là `java.nio.channels.FileChannel`, `position` là offset file không âm và `size` là số byte ánh xạ. Đối với overload trả `MappedByteBuffer`, kích thước một vùng ánh xạ **không vượt `Integer.MAX_VALUE`**; nếu cần làm việc với file lớn hơn, chia thành nhiều vùng ánh xạ hoặc dùng API hiện đại phù hợp trên phiên bản JDK đang triển khai.

### So sánh với ba MapMode chuẩn

| Chế độ | Nơi khai báo | Đọc | Ghi qua mapping | Mục đích |
| --- | --- | --- | --- | --- |
| `FileChannel.MapMode.READ_ONLY` | `java.base` | Có | Không | Ánh xạ file chỉ đọc thông thường |
| `FileChannel.MapMode.READ_WRITE` | `java.base` | Có | Có | Ánh xạ file đọc/ghi thông thường |
| `FileChannel.MapMode.PRIVATE` | `java.base` | Có | Có, copy-on-write riêng | Thay đổi không được truyền về file gốc theo hợp đồng |
| `ExtendedMapMode.READ_ONLY_SYNC` | `jdk.nio.mapmode` | Có | Không | Ánh xạ chỉ đọc trên file-backed NVM |
| `ExtendedMapMode.READ_WRITE_SYNC` | `jdk.nio.mapmode` | Có | Có | Ánh xạ đọc/ghi trên file-backed NVM, tối ưu `force` |

**Đừng viết nhầm** `FileChannel.MapMode.READ_WRITE_SYNC` hoặc `FileChannel.MapMode.READ_ONLY_SYNC` — hai tên này **không** tồn tại trong class `FileChannel.MapMode` chuẩn. Phải dùng `jdk.nio.mapmode.ExtendedMapMode`.

Ngoài ra, đây không phải `StandardOpenOption.SYNC` hoặc `DSYNC`. Hai option đó là **chế độ mở channel khi thực hiện cập nhật file**; chúng không thay thế hai hằng số ánh xạ NVM và không tự biến ổ SSD thành NVM có DAX.

## 3. READ_ONLY_SYNC: đọc file NVM, không cho sửa buffer

Ý tưởng trong một môi trường **đã xác minh hỗ trợ ánh xạ NVM**:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(ExtendedMapMode.READ_ONLY_SYNC, 0, fileSize);
    byte value = mapped.get(0);
    System.out.println(value);
}
~~~

Đây là **đoạn minh họa** với `path` và `fileSize` do ứng dụng cung cấp, cần import `FileChannel`, `MappedByteBuffer` và `StandardOpenOption`. Nó **không được bảo đảm chạy** trên file system thông thường hoặc Windows; chỉ dùng khi nền tảng thực sự hỗ trợ sync mapping.

Các điểm chính:

1. Mode dành cho ánh xạ **chỉ đọc** file NVM. Channel phải có quyền **READ**.
2. Kết quả có đặc tính read-only. Gọi `mapped.put(...)` trên read-only buffer sẽ bị từ chối bằng `ReadOnlyBufferException`.
3. Vì không ghi dữ liệu, không có chuyện gọi `mapped.force()` để “lưu” những byte vừa đọc; `force` đối với read-only mapping không có tác dụng ghi một thay đổi từ buffer.
4. `READ_ONLY_SYNC` không phải cơ chế khóa file. Nó **không bảo đảm** các tiến trình khác sẽ không thay file, không bảo đảm snapshot nhất quán và không tự giải quyết race giữa các readers/writers.
5. Nếu backing file không phù hợp hoặc nền tảng không hỗ trợ, `FileChannel.map(...)` có thể thất bại. Không được suy luận “file đọc được bằng `Files.readAllBytes` thì `READ_ONLY_SYNC` chắc chắn dùng được”.

Nếu ứng dụng chỉ cần **đọc một file thông thường** và không có lý do dùng file-backed NVM, `FileChannel.MapMode.READ_ONLY` là lựa chọn phổ thông hơn.

## 4. READ_WRITE_SYNC: ghi NVM và flush theo cơ chế đặc biệt

Ý tưởng trong một môi trường DAX/NVM phù hợp:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    MappedByteBuffer mapped =
            channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);

    mapped.putInt(0, 2026);              // Thay đổi các byte được ánh xạ
    mapped.force(0, Integer.BYTES);      // Yêu cầu writeback vùng được sửa
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. File phải tồn tại và có vùng ánh xạ hợp lệ hoặc được chuẩn bị theo quy tắc `FileChannel.map`. Có thể `map` thất bại nếu thiết bị/file system không hỗ trợ đồng bộ NVM.

Giải thích:

- Channel mở với cả **READ** và **WRITE**, vì `READ_WRITE_SYNC` là mapping đọc/ghi.
- `mapped.putInt(0, 2026)` thay đổi các byte trong mapping. Nếu cần quy ước byte order giữa chương trình khác nhau, hãy đặt `mapped.order(ByteOrder.BIG_ENDIAN)` hoặc `LITTLE_ENDIAN` một cách tường minh trước khi ghi dữ liệu nhiều byte.
- `mapped.force(0, Integer.BYTES)` yêu cầu ghi lại vùng byte đã sửa ra storage. Đối với `READ_WRITE_SYNC`, API `ExtendedMapMode` nêu cơ chế **cache-line writeback** thay cho thông thường flush file device.
- `force(index, length)` có từ Java 13, nhận offset **trong buffer**, không phải offset tuyệt đối trên file. Phạm vi bắt đầu tại `index` và dài `length` byte; Javadoc cho phép implementation đồng bộ thêm các byte ngoài phạm vi nếu cần theo granularity thiết bị.
- Có thể gọi `mapped.force()` để yêu cầu flush toàn bộ vùng được ánh xạ. Cả hai overload trả lại buffer.

**Không nhầm thao tác:** `putInt(...)` **không** đồng nghĩa “transaction đã bền vững”; cần thiết kế thời điểm `force` theo hợp đồng dữ liệu. `READ_WRITE_SYNC` không cung cấp một giao thức transaction, write-ahead log, checksums hoặc recovery protocol.

Nếu chỉ làm việc với file phổ thông không có NVM/DAX, dùng `FileChannel.MapMode.READ_WRITE` và `MappedByteBuffer.force()` theo hợp đồng lưu trữ phù hợp. **Đừng tuyên bố** fallback này giữ nguyên cơ chế cache-line writeback hoặc đặc tính độ trễ của sync mapping.

## 5. Các điều kiện hệ thống: NVM không chỉ là “ổ lưu trữ nhanh”

**Non-volatile RAM/persistent memory** là bộ nhớ có tính không mất dữ liệu khi mất điện, được hệ thống triển khai theo một mô hình lưu trữ thích hợp. Với JEP 352, hai chế độ sync nhắm đến **ánh xạ file trên vùng NVM**; trên Linux, tài liệu Java mô tả khi dùng mode này, hệ thống yêu cầu `mmap` với hai flag:

~~~text
MAP_SHARED_VALIDATE | MAP_SYNC
~~~

Đây là **ghi chú triển khai Linux** trong Javadoc, không phải flag mà Java code tự truyền vào một API `mmap` công khai.

Các điều kiện cần xem xét:

- JVM/JDK thực sự có module `jdk.nio.mapmode` và hỗ trợ các mode đó.
- Hệ điều hành và kernel hỗ trợ cơ chế ánh xạ đồng bộ tương ứng.
- File nằm trong vùng lưu **NVM có khả năng mapping phù hợp**, ví dụ cấu hình filesystem/DAX hỗ trợ `MAP_SYNC` theo hệ điều hành.
- File được mở đúng **READ** hoặc **READ+WRITE** và có đủ quyền; kích thước/offset hợp lệ.
- Hệ thống thực sự có **đường đi persistence** phù hợp; không chỉ đổi tên thư mục hoặc file để trông như NVM.

**SSD/NVMe không tự động bằng NVM dạng file-backed mà `ExtendedMapMode` yêu cầu.** SSD có thể nhanh và giữ dữ liệu khi mất điện theo khả năng thiết bị, nhưng một file thường trên SSD không mặc định có trực tiếp bộ nhớ persistently-addressable với DAX mà mode sync cần.

Cũng không phải mọi Linux + JDK 17 đều dùng được chế độ này: môi trường phải được kernel và filesystem hỗ trợ. Trên nền tảng hoặc filesystem không đáp ứng, việc map sync có thể bị từ chối.

### Các lỗi thật sự khi thiếu hỗ trợ

Javadoc `ExtendedMapMode` nói rằng `FileChannel.map` với mode không được implementation hỗ trợ sẽ ném **`UnsupportedOperationException`**. Trong một số tình huống cụ thể như Linux file không hỗ trợ `MAP_SYNC`, lỗi từ hệ điều hành có thể được Java báo dưới dạng **`IOException`**.

Không nên viết:

~~~java
// Không nên: lặng lẽ giả định SYNC mode luôn hoạt động.
MappedByteBuffer buffer =
        channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size);
~~~

rồi quảng cáo ứng dụng sẽ chạy trên mọi máy có Java 17. Đây chỉ là ví dụ trong môi trường giả định. Hãy xử lý lỗi theo **yêu cầu bền vững dữ liệu của ứng dụng**, không bắt rồi bỏ qua.

## 6. Compile/run với module JDK-specific

Vì hai hằng số nằm trong module `jdk.nio.mapmode`, không nên chỉ import rồi giả định mọi môi trường lập tức resolve module đó. Với file Java trên classpath, có thể chỉ định module khi biên dịch và chạy:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 SyncMappingProbeDemo.java
java --add-modules jdk.nio.mapmode SyncMappingProbeDemo
~~~

**Hai lệnh này đã được kiểm tra trên JDK 24 với target Java 17.** `javac --release 17` chọn API/cú pháp mục tiêu; `--add-modules jdk.nio.mapmode` bổ sung module JDK cụ thể vào module graph. Trên JDK khác hoặc custom runtime đã loại module này, việc build/launch có thể thất bại.

Với dự án modular có `module-info.java`, có thể khai báo:

~~~java
module my.persistence.app {
    requires jdk.nio.mapmode;
}
~~~

Đây là **mã minh họa trong một dự án modular**, không phải file chạy độc lập. Đây là sự phụ thuộc **JDK-specific**, nên không thể tự động đòi một Java runtime chỉ triển khai Java SE hoặc một custom `jlink` image bỏ module cũng chạy như nhau.

### Tránh nhầm tên module với package

- **Module:** `jdk.nio.mapmode`
- **Package:** `jdk.nio.mapmode`
- **Class:** `jdk.nio.mapmode.ExtendedMapMode`
- **Hằng số:** `ExtendedMapMode.READ_ONLY_SYNC` và `ExtendedMapMode.READ_WRITE_SYNC`

Tên giống nhau giữa module và package không phải lỗi; Java module có thể export một package cùng tên.

## 7. Chương trình Java 17+ số 1: so sánh mode thường và thử mode SYNC

Chương trình sau **không yêu cầu NVM để chạy phần ánh xạ thông thường**. Nó cố thử hai sync modes trên một file tạm để chứng minh **kết quả phụ thuộc OS/filesystem/JVM**, không ép phải thành công.

Tạo file **`SyncMappingProbeDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class SyncMappingProbeDemo {
    static String tryMode(Path file, FileChannel.MapMode mode, boolean writable) {
        try (FileChannel channel = writable
                ? FileChannel.open(file, StandardOpenOption.READ, StandardOpenOption.WRITE)
                : FileChannel.open(file, StandardOpenOption.READ)) {
            MappedByteBuffer mapped = channel.map(mode, 0, 32);
            return mapped.isReadOnly() ? "mapped-read-only" : "mapped-read-write";
        } catch (UnsupportedOperationException e) {
            return "not-supported-by-implementation";
        } catch (IOException e) {
            return "mapping-rejected-by-file-or-os";
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("sync-mode-demo-", ".bin");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                channel.truncate(0);
                MappedByteBuffer ordinary = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, 32);
                ordinary.order(ByteOrder.BIG_ENDIAN);
                ordinary.putInt(0, 2026);
                ordinary.force(0, Integer.BYTES);
            }

            try (FileChannel readOnly = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                MappedByteBuffer ordinaryRead = readOnly.map(
                        FileChannel.MapMode.READ_ONLY, 0, 32);

                System.out.println("ordinaryValue=" + ordinaryRead.getInt(0));
                System.out.println("ordinaryIsReadOnly=" + ordinaryRead.isReadOnly());
                try {
                    ordinaryRead.put(0, (byte) 1);
                    throw new AssertionError("Write unexpectedly succeeded");
                } catch (ReadOnlyBufferException expected) {
                    System.out.println("ordinaryReadOnlyWriteRejected=true");
                }
            }

            System.out.println("readOnlySync=" +
                    tryMode(file, ExtendedMapMode.READ_ONLY_SYNC, false));
            System.out.println("readWriteSync=" +
                    tryMode(file, ExtendedMapMode.READ_WRITE_SYNC, true));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 SyncMappingProbeDemo.java
java --add-modules jdk.nio.mapmode SyncMappingProbeDemo
~~~

**Stdout được kiểm chứng trên Windows với OpenJDK 24.0.2:**

~~~text
ordinaryValue=2026
ordinaryIsReadOnly=true
ordinaryReadOnlyWriteRejected=true
readOnlySync=not-supported-by-implementation
readWriteSync=not-supported-by-implementation
~~~

### Diễn giải đúng các dòng output

1. `ordinaryValue=2026`: mapping thường `READ_WRITE` đã ghi một số nguyên, gọi `force(...)` và đọc lại qua `READ_ONLY`; đây là phép kiểm tra chức năng cơ bản trong môi trường thử nghiệm.
2. `ordinaryIsReadOnly=true`: `FileChannel.MapMode.READ_ONLY` trả buffer không cho sửa.
3. `ordinaryReadOnlyWriteRejected=true`: thử ghi vào buffer chỉ đọc bị ném `ReadOnlyBufferException` như mong đợi.
4. Hai dòng `...=not-supported-by-implementation`: Windows/JVM đang chạy **không hỗ trợ** hai sync modes trên file tạm cụ thể. Đây **không phải** lỗi cú pháp import/mapping.
5. Trên Linux có cơ chế và file-backed NVM phù hợp, hai dòng sync **có thể** trở thành `mapped-read-only` và `mapped-read-write`. Trên Linux thiếu DAX, có thể in `mapping-rejected-by-file-or-os`. Kết quả tùy môi trường, không có stdout universal cho hai dòng này.

**Lưu ý quan trọng về test:** file tạm thường **không phải vùng NVM/DAX**. Demo chỉ chứng minh API tồn tại và cách xử lý tình huống không được hỗ trợ, **không xác nhận hiệu năng hay độ bền khi mất điện của thiết bị NVM**. Để kiểm thử NVM thực sự, phải cung cấp file trên backing storage đã được người vận hành xác minh.

## 8. Chương trình Java 17+ số 2: không tự hạ chuẩn persistence khi SYNC không có

Có hai yêu cầu nghiệp vụ khác nhau:

- **Bắt buộc sync NVM:** nếu hệ thống cần đặc tính của ánh xạ NVM cho giao thức persistence, thiếu hỗ trợ phải **từ chối vận hành** hoặc chuyển sang giải pháp đã được thiết kế/kiểm định tương đương.
- **Cho phép mapping thường:** nếu NVM chỉ là tối ưu tùy chọn và ứng dụng **đã có hợp đồng durability thích hợp** cho file thông thường, có thể dùng `FileChannel.MapMode.READ_WRITE` với `force`. Không được gọi đó là “sync NVM” khi đã fallback.

Chương trình tiếp theo minh họa một **policy tường minh**. Nó chỉ fallback khi implementation ném `UnsupportedOperationException`; **không nuốt mọi `IOException`**, vì IOException có thể liên quan hỏng file, lỗi I/O hoặc điều kiện không nên bỏ qua. Đây là chủ ý về an toàn và khả năng điều tra lỗi.

Tạo file **`SyncModePolicyDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.atomic.AtomicBoolean;
import jdk.nio.mapmode.ExtendedMapMode;

public class SyncModePolicyDemo {
    static final int SIZE = 16;

    static MappedByteBuffer mapForWrite(FileChannel channel,
            boolean mustBeSync, AtomicBoolean downgraded) throws IOException {
        try {
            return channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, SIZE);
        } catch (UnsupportedOperationException e) {
            if (mustBeSync) {
                throw new IllegalStateException(
                        "Synchronous NVM mapping is required", e);
            }
            downgraded.set(true);
            return channel.map(FileChannel.MapMode.READ_WRITE, 0, SIZE);
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("sync-policy-", ".bin");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                channel.truncate(0);
                AtomicBoolean downgrade = new AtomicBoolean();
                String requiredStatus;
                try {
                    mapForWrite(channel, true, new AtomicBoolean());
                    requiredStatus = "supported";
                } catch (IllegalStateException expected) {
                    requiredStatus = "rejected-unsupported-implementation";
                }
                System.out.println("requiredStatus=" + requiredStatus);

                MappedByteBuffer buffer =
                        mapForWrite(channel, false, downgrade);
                buffer.putInt(0, 42);
                buffer.force(0, Integer.BYTES);
                System.out.println("fallbackUsed=" + downgrade.get());
            }

            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                MappedByteBuffer mapped = channel.map(
                        FileChannel.MapMode.READ_ONLY, 0, SIZE);
                System.out.println("reopenedValue=" + mapped.getInt(0));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 SyncModePolicyDemo.java
java --add-modules jdk.nio.mapmode SyncModePolicyDemo
~~~

**Stdout đã kiểm chứng trên Windows JDK 24, nơi map SYNC ném `UnsupportedOperationException`:**

~~~text
requiredStatus=rejected-unsupported-implementation
fallbackUsed=true
reopenedValue=42
~~~

Vì sao test hữu ích?

- Với `mustBeSync=true`, **không âm thầm chuyển** sang `READ_WRITE`. Trên máy thử không hỗ trợ, chương trình trả trạng thái từ chối rõ ràng.
- Với `mustBeSync=false`, chương trình **cho phép hạ cấp theo policy**, dùng mapping thường rồi gọi `force`.
- `reopenedValue=42` chứng minh các byte được đọc lại qua file trong môi trường đó. Nó **không phải thí nghiệm rút điện**, không chứng minh atomic commit, và không so sánh cache-line flush với file-device flush.
- Trên phần cứng hỗ trợ SYNC, output có thể là `requiredStatus=supported` và `fallbackUsed=false`. Không phụ thuộc vào một kết quả duy nhất trên mọi máy.
- **Trên Linux không hỗ trợ `MAP_SYNC`, `map` có thể ném `IOException` thay vì `UnsupportedOperationException`.** Trong demo này lỗi `IOException` **được đưa ra ngoài**, không bị lặng lẽ fallback. Ứng dụng thật cần quyết định rõ cách phân loại lỗi có thể phục hồi, log nguyên nhân và cấu hình thay thế, thay vì catch chung mọi I/O error.

Nếu nghiệp vụ **bắt buộc NVM persistence** mà không có nền tảng tương đương, không được dùng mapping thường rồi vẫn tuyên bố dữ liệu đã có cùng đặc tính NVM. Nếu ứng dụng **cho phép** thay công nghệ lưu trữ, phải đặc tả, kiểm thử crash recovery và performance trên cả hai đường.

## 9. Hiểu đúng `force()`: durability không phải giao dịch

Trong cả `MappedByteBuffer` thường và sync NVM, `force()` là API quan trọng, nhưng cần phân biệt **độ bền lưu trữ**, **thứ tự ghi** và **tính nguyên tử**:

| Khía cạnh | `MappedByteBuffer.force()` / `force(index,length)` | Không được suy ra |
| --- | --- | --- |
| Mục tiêu | Yêu cầu các thay đổi của vùng mapping được đẩy tới backing storage | Tất cả lần `put` trước đó đều tự force dù không gọi method |
| `READ_WRITE_SYNC` | Javadoc nói triển khai dùng **cache-line writeback** thay vì file device flush | Mọi thiết bị đều có cùng latency/throughput |
| `READ_ONLY_SYNC` | Mapping chỉ đọc, không có thay đổi cần ghi từ buffer | Force read-only sẽ tạo/sửa nội dung |
| Phạm vi range | `force(index,length)` yêu cầu ghi lại một vùng byte | Luôn chỉ flush đúng byte đó và không đụng granularity khác |
| Đồng bộ | Độ bền của dữ liệu đã được đẩy theo hợp đồng API và storage | Ghi nhiều trường tự động atomic hoặc linearizable với readers khác |
| Lỗi | Có thể gặp lỗi I/O, ví dụ `UncheckedIOException` từ `MappedByteBuffer.force` | Một lệnh force thành công có thể bỏ qua mọi rủi ro phần cứng hoặc lỗi logic |

**Atomicity:** một bản ghi gồm header, length, payload và checksum có thể bị thay đổi một phần trước khi hệ thống crash. Ngay cả khi dùng SYNC mode, bạn vẫn cần **protocol về thứ tự ghi, commit marker, checksum/version, recovery** nếu ứng dụng hứa một record luôn hợp lệ sau restart. `force` không tự cung cấp transaction cho nhiều field.

**Visibility:** việc một thread khác hoặc tiến trình khác nhìn thấy bytes mới là vấn đề riêng của memory visibility, synchronization và hành vi map của hệ điều hành. `SYNC` không thay thế `synchronized`, `volatile`, locks, atomics hoặc một giao thức chia sẻ dữ liệu có thiết kế.

**File metadata:** vùng mapping có thể dựa vào kích thước file, metadata hoặc cấu trúc filesystem. Nếu giao thức persistence đòi file mới được tạo/directory entry tồn tại sau crash, chỉ force một vài byte trong mapping có thể chưa bao phủ mọi điều kiện durability ở tầng metadata và hệ thống lưu trữ. Phải thiết kế theo hệ điều hành và storage cụ thể.

## 10. Lỗi và điều kiện biên khi gọi `FileChannel.map(...)`

| Tình huống | Hành vi hoặc biện pháp |
| --- | --- |
| JVM/implementation không hỗ trợ sync mode | `UnsupportedOperationException` theo Javadoc `ExtendedMapMode` |
| Kernel/filesystem không cho mapping `MAP_SYNC` | Có thể bị từ chối bằng lỗi I/O; cần xem nguyên nhân cụ thể |
| Channel chỉ mở `WRITE` nhưng cần đọc | Cần mở quyền `READ`; thiếu quyền có thể ném `NonReadableChannelException` |
| `READ_WRITE_SYNC` nhưng channel không có `READ + WRITE` | Cần mở cả hai quyền; thiếu quyền ghi có thể ném `NonWritableChannelException` |
| `READ_ONLY_SYNC` rồi gọi `put` khi map thành công | `ReadOnlyBufferException` |
| Offset/size âm hoặc size vượt giới hạn của `MappedByteBuffer` | `IllegalArgumentException` theo tiền điều kiện `FileChannel.map` |
| File bị truncate hoặc đổi trong khi còn mapping | Vùng map có thể trở nên không truy cập được; hành vi chi tiết phụ thuộc OS |
| Cùng vùng mapping được nhiều threads ghi | Cần protocol đồng bộ riêng, tránh data race và dữ liệu nửa chừng |
| Dùng `force` sai index/length | Có thể ném `IndexOutOfBoundsException` |
| Không phân biệt nguồn lỗi I/O | Đừng nuốt exception; log/định nghĩa fallback chỉ khi hợp đồng cho phép |

**Đóng `FileChannel` không tự unmap buffer.** Với overload `map(...)` trả `MappedByteBuffer`, mapping vẫn còn hợp lệ cho đến khi chính buffer được garbage-collected; vòng đời và tài nguyên native cần được quản trị. Trên một số OS, mapping đang sống có thể ảnh hưởng việc truncate, xóa hoặc thay file. Vì vậy không nên sử dụng file tạm/buffer mapping như một tài nguyên mà chỉ cần `channel.close()` là chắc chắn đã được giải phóng khỏi bộ nhớ.

**Tránh suy luận về hiệu suất:** memory-mapped file có overhead thiết lập và không nhất thiết nhanh hơn read/write thường đối với các file nhỏ. Điều này đúng cả khi app dùng NVM và NIO: đo theo workload thực tế trước khi lựa chọn.

## 11. Checklist triển khai thực tế

1. **Đọc hợp đồng:** ứng dụng cần file thông thường, cần NVM cache-line writeback, hay cần crash-consistent transaction?
2. **Xác định runtime:** `jdk.nio.mapmode` phải có trong JDK/custom runtime; nếu build modular, khai báo `requires jdk.nio.mapmode`.
3. **Xác định backing storage:** file nằm trên vùng được quản trị là NVM/DAX thực sự, không chỉ là SSD/NVMe thông thường.
4. **Kiểm tra OS/FS:** trên Linux, xác nhận có `MAP_SYNC` và `MAP_SHARED_VALIDATE` trên đường đi file đó theo đặc tả của kernel/filesystem.
5. **Mở channel đúng quyền:** `READ_ONLY_SYNC` cần đọc; `READ_WRITE_SYNC` cần cả đọc/ghi.
6. **Map đúng kích thước:** index/size không âm, không vượt giới hạn `MappedByteBuffer`, xử lý file chưa đủ dài một cách có chủ đích.
7. **Bắt đúng lỗi hỗ trợ:** `UnsupportedOperationException`; phân biệt `IOException` với lỗi logic, quyền hoặc hỏng storage.
8. **Chọn fallback theo hợp đồng:** nếu yêu cầu SYNC là bắt buộc, fail rõ ràng; nếu tối ưu tùy chọn, ghi log loại mapping thực sự dùng và xác nhận durability thay thế.
9. **Thiết kế dữ liệu bền vững:** dùng version/checksum/commit protocol nếu cần phục hồi giữa chừng; đừng hiểu nhầm `force` là giao dịch.
10. **Quản lý concurrency:** thống nhất ai ghi, ai đọc, khi nào flush, dùng các công cụ Java memory synchronization phù hợp.
11. **Quản lý vòng đời:** nhớ mapped buffer có thể sống sau khi đóng channel; tránh xóa/truncate file đang có mapping khác sử dụng.
12. **Kiểm thử đúng môi trường:** phân biệt smoke test trên file thông thường với kiểm thử persistence trên thiết bị NVM thật, gồm thử restart/crash nếu hệ thống có yêu cầu.
13. **Theo dõi thay đổi triển khai:** hai mode này là **JDK-specific**, không phải Java SE portable; kiểm tra release notes, module availability và support của target JVM.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai hằng số `READ_ONLY_SYNC` và `READ_WRITE_SYNC` nằm ở class nào?  
**Đáp án:** `jdk.nio.mapmode.ExtendedMapMode`, module `jdk.nio.mapmode`. Không phải `FileChannel.MapMode.READ_*_SYNC`.

**Câu 2.** `READ_ONLY_SYNC` có được dùng để thay đổi byte trong mapped buffer không?  
**Đáp án:** Không. Đây là chế độ read-only; ghi vào buffer bị từ chối.

**Câu 3.** Lợi ích được Javadoc nêu trực tiếp của `READ_WRITE_SYNC` ở `force` là gì?  
**Đáp án:** Dùng cache-line writeback cho file-backed NVM thay cho đường file-device flush thường, nếu mapping sync thành công.

**Câu 4.** Có JDK 17 và SSD NVMe thì `READ_WRITE_SYNC` chắc chắn map thành công?  
**Đáp án:** Không. Cần OS/filesystem và NVM/DAX phù hợp; SSD/NVMe thông thường không đồng nghĩa file-backed NVM.

**Câu 5.** Trên Linux, implementation note nhắc hai flag `mmap` nào?  
**Đáp án:** `MAP_SYNC` và `MAP_SHARED_VALIDATE`.

**Câu 6.** Khi nền tảng không hỗ trợ map mode, exception nào được Javadoc ExtendedMapMode nêu?  
**Đáp án:** `UnsupportedOperationException`. Tùy lỗi OS/filesystem, cũng có thể có `IOException`.

**Câu 7.** Có nên luôn fallback từ SYNC sang `READ_WRITE` khi gặp lỗi không?  
**Đáp án:** Không. Chỉ khi chính sách ứng dụng cho phép và hành vi durability khác biệt được chấp nhận/kiểm định; không được âm thầm hạ chuẩn.

**Câu 8.** `mapped.putInt(0, value)` có tự đảm bảo dữ liệu đã durable và atomic không?  
**Đáp án:** Không. Dùng `force` theo yêu cầu, và nếu có nhiều field cần transaction/recovery protocol riêng.

**Câu 9.** `MappedByteBuffer.force(4, 8)` dùng offset từ đầu file hay đầu buffer?  
**Đáp án:** Offset tính theo **buffer**; vùng dài 8 byte tính từ index 4.

**Câu 10.** Đóng FileChannel có làm mapping lập tức biến mất không?  
**Đáp án:** Không. Mapping tồn tại tới khi buffer được garbage-collected theo hợp đồng của overload trả `MappedByteBuffer`.

**Câu 11.** `StandardOpenOption.SYNC` có phải giá trị của `FileChannel.MapMode` không?  
**Đáp án:** Không. Nó là option khi mở file/channel, khác với sync map mode.

**Câu 12.** Chạy demo trên Windows thấy cả hai mode `not-supported-by-implementation` có chứng minh API đã lỗi thời không?  
**Đáp án:** Không. API vẫn hiện diện trong JDK hiện đại; kết quả chỉ cho biết implementation/nền tảng/file hiện tại không hỗ trợ ánh xạ NVM đó.

## Tài liệu chính thức

- **Oracle Java SE 26 — `ExtendedMapMode`:** hai hằng số còn áp dụng; mô tả read-only, read-write và cache-line writeback; unsupported mapping; Linux flags. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- **Oracle Java SE 17 — `ExtendedMapMode`:** API ổn định từ Java 14; cùng semantics cho Java 17+. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html
- **Oracle Java SE 26 — `jdk.nio.mapmode` module:** module dành cho file mapping modes JDK-specific. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.nio.mapmode/module-summary.html
- **Oracle Java SE 17 — `FileChannel.map(...)`:** quyền đọc/ghi, giới hạn size, UnsupportedOperationException, mapping lifetime, các MapMode tiêu chuẩn. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- **Oracle Java SE 17 — `MappedByteBuffer.force()` / `force(index,length)`:** ghi các thay đổi mapping, phạm vi force, lỗi I/O và điều kiện local storage. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html
- **OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers:** lịch sử bổ sung hai map modes trong JDK 14 và mục đích tận dụng persistent memory. https://openjdk.org/jeps/352
- **Oracle Java SE 17 — `StandardOpenOption`:** phân biệt `SYNC` và `DSYNC` cho file operations với mode ánh xạ NVM. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
- **Linux manual — `mmap(2)`:** tài liệu kernel/user-space cho `MAP_SHARED_VALIDATE` và `MAP_SYNC`, giúp hiểu điều kiện DAX trên Linux. https://man7.org/linux/man-pages/man2/mmap.2.html