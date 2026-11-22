# Ánh xạ NVM: `force` và việc đẩy dữ liệu tới bộ nhớ lưu giữ (Java 14+)

## 1. Vấn đề cần giải quyết: đã ghi vào vùng nhớ ánh xạ thì dữ liệu đã bền chưa?

Khi dùng `FileChannel.map(...)`, Java đưa một vùng của tệp vào không gian địa chỉ bộ nhớ và trả về `MappedByteBuffer`. Chương trình có thể sửa các byte bằng `put(...)` như đang thao tác trên bộ nhớ. Nhưng **việc thay đổi byte trong buffer và việc bảo đảm thay đổi đã đến thiết bị lưu giữ là hai bước khác nhau**.

Ví dụ:

```java
// Snippet nằm trong method có MappedByteBuffer mapped được ánh xạ READ_WRITE.
mapped.putInt(4, 2026);   // Sửa dữ liệu qua bộ nhớ ánh xạ.
mapped.force(4, 4);       // Yêu cầu đẩy vùng byte tương ứng tới storage.
```

Nếu bỏ thao tác `force`, thay đổi trong mapping `READ_WRITE` có thể được hệ điều hành đẩy xuống tệp **về sau**, nhưng chương trình không có một điểm xác nhận rõ ràng rằng vùng đã sửa được đẩy tới storage. Điều đó đặc biệt quan trọng với:

- Tệp chứa trạng thái phục hồi sau sự cố.
- Bản ghi metadata, checkpoint hoặc chỉ số trên storage.
- Vùng tệp đặt trên thiết bị hỗ trợ **non-volatile memory (NVM)** / persistent memory và **direct access (DAX)**.
- Chương trình có yêu cầu thời điểm **độ bền dữ liệu (durability)** rõ ràng.

**Chủ đề bài:** hiểu `MappedByteBuffer.force()` và `force(int index, int length)`, cơ chế với mapping thông thường và mapping NVM đặc biệt, giới hạn cam kết của Java API, cách dùng đúng và cách kiểm thử mà không đánh đồng “đọc lại được” với “chống mất điện đã được chứng minh”.

### Kiến thức còn hiện hành

`MappedByteBuffer` là API Java NIO được hỗ trợ lâu dài. Overload **`force(int, int)` có từ Java 13**; **Java 14 bổ sung mapping đồng bộ dành cho NVM** theo JEP 352, thông qua `jdk.nio.mapmode.ExtendedMapMode.READ_WRITE_SYNC` và `READ_ONLY_SYNC`. Các API đó vẫn tồn tại trong JDK hiện đại, nhưng **mapping SYNC là mở rộng đặc thù JDK và phụ thuộc thiết bị/hệ điều hành**. Ví dụ chính dùng **Java 17+** trên file thông thường để mọi môi trường có NIO mapping đều có cơ hội thực hành; phần NVM/DAX được tách riêng và kiểm thử khả năng hỗ trợ.

## 2. Hiểu các tầng lưu trữ trước khi gọi `force`

Có thể hình dung đường đi của dữ liệu:

```text
Java app: mapped.put(...)
           |
           v
Địa chỉ bộ nhớ ánh xạ (mapped region)
           |
           +-- READ_WRITE thông thường
           |       |
           |       v
           |   page cache / cơ chế mmap của OS
           |       |
           |     force()
           |       |
           |       v
           |   storage device chứa file
           |
           +-- READ_WRITE_SYNC nếu hệ thống hỗ trợ NVM/DAX
                   |
                   v
               ánh xạ trực tiếp tới non-volatile memory
                   |
                 force()
                   |
                   v
              cache-line writeback theo JDK/OS
                   |
                   v
              miền lưu giữ bền vững tương ứng
```

Sơ đồ là mô hình giải thích, **không phải cam kết rằng mọi OS/JVM đều có đúng một pipeline vật lý**. Thiết bị có thể có cache, controller, chính sách bảo đảm ghi và đường đi riêng. Quan trọng nhất là **hợp đồng `force` được quy định trong Javadoc**, không phải khả năng suy luận từ một thao tác đọc.

### RAM, cache và NVM khác nhau thế nào?

- **RAM thông thường** là bộ nhớ làm việc volatile: nội dung có thể mất khi mất điện.
- **File-backed mapped memory** là cửa sổ địa chỉ vào nội dung tệp; việc `put` sửa các byte không đồng nghĩa mọi byte đã tới thiết bị lưu giữ bền.
- **NVM/persistent memory** là loại lưu trữ có khả năng giữ dữ liệu khi tắt nguồn theo đặc tính phần cứng; để ánh xạ trực tiếp thường cần phần cứng, filesystem và cấu hình **DAX** thích hợp.
- **CPU cache** có thể chứa những thay đổi chưa được đẩy vào miền persistence; vì vậy mapping SYNC sử dụng cơ chế writeback phù hợp khi gọi `force`.

Đừng đồng nhất **NVM** với “file trên SSD”. Một tệp trên SSD thông thường vẫn có thể dùng `READ_WRITE` và gọi `force`, nhưng **không tự biến thành `READ_WRITE_SYNC`/DAX**. Ngược lại, một vùng RAM ảo được ánh xạ từ tệp cũng không tự có tính bền của persistent memory.

## 3. Các chế độ `FileChannel.MapMode` và tác dụng của `force`

`FileChannel.map(MapMode mode, long position, long size)` ánh xạ một vùng tệp. Cần đọc đúng mode:

| Chế độ | Ý nghĩa | `force` có tác dụng gì? |
| --- | --- | --- |
| `FileChannel.MapMode.READ_WRITE` | Mapping đọc/ghi chung; thay đổi có thể lan tới file | **Có**: yêu cầu đưa thay đổi buffer tới storage theo hợp đồng Javadoc |
| `FileChannel.MapMode.READ_ONLY` | Mapping chỉ đọc | **Không có tác dụng hữu ích** vì không thể thay đổi nội dung qua buffer |
| `FileChannel.MapMode.PRIVATE` | Mapping copy-on-write riêng | **Không có tác dụng ghi sửa đổi private trở lại tệp** |
| `ExtendedMapMode.READ_WRITE_SYNC` | Mapping đọc/ghi NVM đồng bộ khi OS/JDK hỗ trợ | Trên implementation hỗ trợ, `force` dùng **cache-line writeback** thay cho flush qua thiết bị file |
| `ExtendedMapMode.READ_ONLY_SYNC` | Mapping NVM chỉ đọc, đồng bộ khi OS/JDK hỗ trợ | Không có thao tác sửa nội dung từ buffer để đẩy về storage |

### Vì sao `PRIVATE` không phù hợp cho durability của tệp?

`PRIVATE` thực hiện **copy-on-write**: chương trình có thể thấy dữ liệu sửa trong vùng riêng nhưng các thay đổi đó **không được đưa về file gốc**. Gọi `force` không biến một mapping private thành bản ghi vĩnh viễn.

Nếu yêu cầu là lưu thay đổi xuống tệp, chọn **`READ_WRITE`**, mở `FileChannel` với quyền đọc/ghi, và gọi `force` đúng phạm vi. Đừng test `PRIVATE` bằng cách đọc lại nội dung *trong chính buffer private* rồi kết luận file đã thay đổi.

### Mapping NVM là tùy chọn của nền tảng

`jdk.nio.mapmode.ExtendedMapMode` thuộc **module `jdk.nio.mapmode`**, không phải một phần của ba hằng `FileChannel.MapMode` chuẩn. Cả `READ_ONLY_SYNC` lẫn `READ_WRITE_SYNC` có `Since: 14` trong API Java 25.

Nếu nền tảng **không hỗ trợ** mode đồng bộ, `FileChannel.map(...)` có thể ném **`UnsupportedOperationException`**. Theo ghi chú implementation Oracle, Linux dùng các flag mmap `MAP_SYNC` và `MAP_SHARED_VALIDATE` khi chọn mode SYNC. Hỗ trợ thực tế còn phụ thuộc filesystem và việc tệp thực sự được backing bởi persistent memory/DAX.

**Không viết `READ_WRITE_SYNC` rồi kỳ vọng tự động được hỗ trợ trên Windows, mọi SSD hoặc mọi Linux filesystem.** Nếu yêu cầu nghiệp vụ bắt buộc có NVM flush, chương trình phải **kiểm tra khả năng hỗ trợ và fail fast khi không đáp ứng** thay vì âm thầm dùng mode khác.

## 4. Hai overload của `MappedByteBuffer.force`

```java
MappedByteBuffer force()
MappedByteBuffer force(int index, int length)
```

Đây là chữ ký phương thức rút gọn. Chúng thuộc `java.nio.MappedByteBuffer` và đều trả lại chính `MappedByteBuffer` để có thể tiếp tục thao tác.

### 4.1. `force()`: toàn vùng mapping

`mapped.force()` có tác dụng tương đương:

```java
mapped.force(0, mapped.capacity());
```

Nó dùng **toàn bộ `capacity()`**, không chỉ khoảng từ `position()` tới `limit()`. Do đó:

```java
// Snippet: giả sử mapped có capacity 16.
mapped.position(12);
mapped.limit(15);
mapped.force();        // Không chỉ flush 3 byte [12, 15).
```

Nếu chỉ muốn tác động tới vùng đã sửa, chọn overload có `index` và `length` phù hợp, đồng thời nhớ rằng OS có thể flush rộng hơn vùng yêu cầu.

### 4.2. `force(index, length)`: chọn vùng theo byte offset trong buffer

```java
mapped.force(4, 4);
```

Nghĩa là yêu cầu đẩy những thay đổi của **vùng byte từ index 4 tới trước index 8** trong buffer. `index` là **offset tương đối với buffer**, không phải số byte tuyệt đối từ đầu file nếu mapping được tạo ở offset khác 0.

Giả sử:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 4096, 1024);
mapped.putInt(20, 123);
mapped.force(20, Integer.BYTES);
```

Đây là snippet nằm trong method có `FileChannel channel` đã mở đọc/ghi, và một file có vùng dữ liệu tương ứng. Nó yêu cầu flush vùng tương ứng **file offset 4096 + 20 = 4116**, không phải file offset 20.

**Chú ý:** Một vùng `force(index,length)` có thể khiến hệ điều hành ghi **cả byte bên ngoài vùng yêu cầu** nếu granularity của page/block/cache bắt buộc. Đây là điều được Javadoc cho phép, không phải lỗi.

### 4.3. Điều kiện biên và exception

Với buffer có capacity dương, Javadoc quy định:

- `index >= 0`;
- `index < capacity()`;
- `length >= 0`;
- `length <= capacity() - index`.

Nếu vi phạm, `force(index,length)` ném **`IndexOutOfBoundsException`**. Ví dụ capacity = 16, `force(14, 3)` không hợp lệ vì vùng vượt qua byte cuối. Dùng `index=0, length=0` với capacity dương thì hợp lệ nhưng không có byte nào cần flush; không nên lợi dụng length 0 làm cơ chế xác nhận durability.

Khi ghi dữ liệu xuống thiết bị gặp lỗi, `MappedByteBuffer.force` có thể ném **`UncheckedIOException`** — khác với `FileChannel.force(boolean)` có checked `IOException`.

### 4.4. `position()` và `limit()` không phải vùng cần flush

`force` không phải phép đọc/ghi tuần tự `get/put`, không phụ thuộc current cursor. Đừng nhầm `flip()`, `clear()` hoặc `rewind()` với việc flush; các phương thức đó chỉ điều chỉnh trạng thái buffer, không bảo đảm ghi dữ liệu xuống thiết bị.

Khi test, có thể lưu `position/limit` trước và sau `force` để xác nhận chúng vẫn đúng, nhưng điểm mấu chốt vẫn là **đưa dữ liệu qua API persistence**, không phải thay đổi cursor.

## 5. Hợp đồng durability của `force`: bảo đảm tới đâu?

Theo Javadoc Java 25:

- Với mapping `READ_WRITE` trên **tệp nằm trên thiết bị lưu trữ cục bộ**, khi `force` trả về bình thường, những thay đổi được thực hiện đối với **phạm vi được force** kể từ khi tạo buffer hoặc lần force tương ứng trước đó **được bảo đảm ghi tới thiết bị lưu trữ đó**.
- Với **tệp không nằm trên thiết bị cục bộ** (ví dụ một số network filesystem), API **không đưa ra bảo đảm tương đương**.
- Với `READ_ONLY` và `PRIVATE`, force **không có tác dụng đẩy dữ liệu sửa đổi của buffer về tệp**.
- Với mapping mode mở rộng như `READ_WRITE_SYNC`, hành vi phụ thuộc implementation; Oracle ghi rõ cache-line writeback dành cho vùng NVM/DAX khi hỗ trợ.
- Với `force(int index,int length)`, hệ thống **có thể ghi thêm byte ngoài vùng yêu cầu**, nhưng chỉ những byte trong vùng chỉ định là phạm vi mà ứng dụng dựa vào để đòi bảo đảm.

### Không được suy ra điều gì từ bảo đảm này?

**`force` không phải transaction hay cơ chế atomic commit.** Nó không tự:

- Bảo đảm nhiều field được cập nhật nguyên tử cùng nhau.
- Tạo thứ tự commit nghiệp vụ cho các thread writer không đồng bộ.
- Thực hiện checksum, versioning, journal hoặc phục hồi sau hỏng dở.
- Bảo đảm một thao tác rename, tạo file hoặc ghi metadata thư mục đã có durability giống dữ liệu mapped.
- Bảo vệ khỏi mất dữ liệu do thiết bị hỏng, lỗi firmware, lỗi filesystem, bộ điều khiển không thực hiện đúng hợp đồng hoặc phá hủy vật lý.
- Bảo đảm byte trên **network filesystem** đã nằm an toàn ở thiết bị cuối.
- Ngăn chương trình khác sửa/truncate file đã map hoặc chặn race giữa các thread.

**Khuyến nghị:** Dùng `force` làm **một phần của chiến lược durability**, rồi thiết kế định dạng dữ liệu có version/checksum, commit marker hoặc journal nếu yêu cầu tự phục hồi sau crash. Không dùng một lần force như bằng chứng transaction gồm nhiều cập nhật đã hoàn tất nguyên tử.

## 6. Chương trình Java 17+ hoàn chỉnh: `force` trên file cục bộ

Ví dụ sau dùng **file bình thường** trên thiết bị filesystem hiện có, không yêu cầu DAX/NVM đặc thù. Nó kiểm tra cơ chế `MappedByteBuffer.force` và cách chọn vùng bằng tham số.

Tạo tệp **`MappedForceDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedForceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-force-demo-", ".bin");

        try {
            boolean sameBuffer;
            boolean boundsChecked = false;
            int savedPosition, savedLimit;

            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                // Tạo file 16 byte trước khi ánh xạ.
                ByteBuffer initial = ByteBuffer.allocate(16);
                while (initial.hasRemaining()) {
                    channel.write(initial);
                }

                MappedByteBuffer mapped = channel.map(
                        FileChannel.MapMode.READ_WRITE, 0, 16);

                // Các absolute put không thay đổi position.
                mapped.put(0, (byte) 'N');
                mapped.put(1, (byte) 'V');
                mapped.put(2, (byte) 'M');
                mapped.put(3, (byte) '!');
                mapped.putInt(4, 2026);
                mapped.put(8, (byte) 'A');

                // Cố ý thay position và limit trước force.
                mapped.position(12);
                mapped.limit(15);
                savedPosition = mapped.position();
                savedLimit = mapped.limit();

                // Force vùng [0, 8) và kiểm tra buffer trả về.
                sameBuffer = mapped.force(0, 8) == mapped;

                if (mapped.position() != savedPosition ||
                        mapped.limit() != savedLimit) {
                    throw new AssertionError(
                            "force changed position/limit");
                }

                // Force toàn bộ mapping, gồm marker ở index 8.
                mapped.force();

                // capacity 16, nhưng [14, 17) là vùng sai.
                try {
                    mapped.force(14, 3);
                } catch (IndexOutOfBoundsException expected) {
                    boundsChecked = true;
                }
            }

            // Đọc lại tệp để kiểm tra dữ liệu được nhìn thấy.
            byte[] data = Files.readAllBytes(file);
            String label = new String(
                    data, 0, 4, StandardCharsets.US_ASCII);
            int number = ByteBuffer.wrap(data).getInt(4);

            if (!"NVM!".equals(label) || number != 2026 ||
                    data[8] != (byte) 'A') {
                throw new AssertionError(
                        "Unexpected data after remapping");
            }

            System.out.println("fileBytes=" + data.length);
            System.out.println("label=" + label);
            System.out.println("version=" + number);
            System.out.println("marker=" + (char) data[8]);
            System.out.println("sameBuffer=" + sameBuffer);
            System.out.println("positionUnchanged=" +
                    (savedPosition == 12 && savedLimit == 15));
            System.out.println("boundsChecked=" + boundsChecked);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Biên dịch và chạy** bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 MappedForceDemo.java
java MappedForceDemo
```

**Standard output của lần chạy đã kiểm thử:**

```text
fileBytes=16
label=NVM!
version=2026
marker=A
sameBuffer=true
positionUnchanged=true
boundsChecked=true
```

### Giải thích từng kết quả

- `fileBytes=16`: chương trình đã chuẩn bị file đủ 16 byte, không dựa vào việc map vào cuối file chưa có dữ liệu.
- `label=NVM!`: bốn byte đầu được viết bằng các `put(index,byte)` tuyệt đối.
- `version=2026`: `putInt(4, 2026)` viết bốn byte tại chỉ số 4..7. `ByteBuffer` mặc định có byte order BIG_ENDIAN, và `ByteBuffer.wrap(...).getInt(4)` đọc cùng định dạng.
- `marker=A`: byte tại index 8 cũng được ghi, rồi `force()` toàn bộ mapping.
- `sameBuffer=true`: `force(0,8)` trả lại chính buffer, không tạo bản sao khác.
- `positionUnchanged=true`: ví dụ kiểm tra `force` không thay đổi cursor/limit đang sử dụng.
- `boundsChecked=true`: vùng `force(14,3)` vượt capacity 16 và ném `IndexOutOfBoundsException` như kỳ vọng.

**Điều ví dụ này CHƯA chứng minh:** Việc đọc lại thành công **không phải phép thử mất điện hoặc crash**. Sau khi ghi, hệ điều hành có thể cung cấp dữ liệu từ cache hoặc mapping đã được flush. Bài thử chứng minh **cách gọi API, điều kiện biên và trạng thái file quan sát được**. Bảo đảm durability cần được hiểu qua **hợp đồng Javadoc** và khả năng của thiết bị/filesystem, không phải bằng giả lập “đọc lại được”.

### Vì sao dùng `try-with-resources`?

`FileChannel` được đóng tự động. `MappedByteBuffer` là một mapped buffer có vòng đời mapping **không phụ thuộc việc đóng channel**; mapping thường còn hợp lệ đến khi buffer được GC, theo hợp đồng `FileChannel.map`. Vì vậy **đóng channel không thay thế một lần `mapped.force()`** và cũng không phải phép unmap xác định ngay lập tức.

Tệp tạm được xóa trong `finally`; trên nền tảng có chính sách khóa mapping (đặc biệt Windows), việc xóa file vẫn đang mapped có thể bị ảnh hưởng bởi vòng đời native mapping/GC. Vì vậy, ứng dụng thật nên quản lý vòng đời và chính sách xóa/truncate rất cẩn thận; không dựa vào `System.gc()` như một cơ chế unmap/durability bảo đảm.

## 7. Mapping NVM thật: `ExtendedMapMode.READ_WRITE_SYNC`

Tính năng NVM nổi bật của Java 14 là **map mode mở rộng**:

```java
import jdk.nio.mapmode.ExtendedMapMode;

// Snippet: giả sử đã có FileChannel channel đọc/ghi,
// file được backing bởi persistent memory và filesystem hỗ trợ DAX.
MappedByteBuffer mapped = channel.map(
        ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);

mapped.putInt(0, 2026);
mapped.force(0, Integer.BYTES);
```

Đoạn này **chỉ minh họa API**, không phải chương trình đầy đủ. Nó **không thể chạy phổ quát** trên mọi máy; nếu OS/JDK/filesystem không hỗ trợ SYNC map mode, lời gọi `map` có thể ném `UnsupportedOperationException`.

**Khi mode được hỗ trợ**, Javadoc `ExtendedMapMode` nói rằng thao tác `force` trên buffer `READ_WRITE_SYNC` được thực hiện qua **cache-line writeback** thay cho flush qua thiết bị file thông thường. Mục tiêu là đưa các cập nhật CPU cache tới miền persistence của NVM một cách phù hợp với loại mapping.

### `READ_ONLY_SYNC` có ý nghĩa gì?

`READ_ONLY_SYNC` là chế độ chỉ đọc cho mapping file backing bởi non-volatile RAM. Vì không cho sửa buffer qua API thông thường, gọi `force` không có cập nhật nào để đẩy về storage. Nếu nhu cầu cập nhật bền vững, phải dùng **`READ_WRITE_SYNC`** trên nền tảng có hỗ trợ, không cố viết lên buffer chỉ đọc.

### NVM và mode mở rộng không phải chuẩn portable của mọi JVM

`ExtendedMapMode` là **JDK-specific**, thuộc module `jdk.nio.mapmode`. Để compile ví dụ có import module này, có thể khai báo module trong build:

```bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 SyncMapCapabilityDemo.java
java --add-modules jdk.nio.mapmode SyncMapCapabilityDemo
```

Lệnh trên đi với tệp ở phần 8. Trên nền tảng không hỗ trợ mode SYNC, `map` có thể ném `UnsupportedOperationException`. Không tự động biến thất bại đó thành “NVM đã được bật”.

## 8. Chương trình kiểm tra khả năng map SYNC, không giả vờ mọi máy đều có NVM

Tệp **`SyncMapCapabilityDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class SyncMapCapabilityDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile(
                "sync-map-probe-", ".bin");

        try (FileChannel ch = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            ch.write(ByteBuffer.wrap(new byte[4096]));

            try {
                ch.map(ExtendedMapMode.READ_WRITE_SYNC, 0, 4096);
                System.out.println("syncMapSupported=true");
            } catch (UnsupportedOperationException expected) {
                System.out.println("syncMapSupported=false");
            } catch (IOException mappingError) {
                System.out.println("syncMapOpenFailed=" +
                        mappingError.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

**Trên môi trường Windows JDK 24 đã kiểm thử**, build với Java 17 target:

```bash
javac --release 17 --add-modules jdk.nio.mapmode -encoding UTF-8 SyncMapCapabilityDemo.java
java --add-modules jdk.nio.mapmode SyncMapCapabilityDemo
```

**Standard output của lần kiểm thử này:**

```text
syncMapSupported=false
```

Điều đó nói rằng **nền tảng/file trong bài thử không hỗ trợ `READ_WRITE_SYNC`**. Đây là kết quả **đúng và quan trọng**, không phải lỗi của Java compiler. Khi thật sự dùng file trên NVM/DAX được hỗ trợ, kết quả có thể là `true`. Trường hợp mapping gặp lỗi I/O thực tế, chương trình in `syncMapOpenFailed=...` với tên lớp exception tương ứng.

**Giới hạn test:** Tệp tạm được tạo trên filesystem mặc định. Một kết quả `false` ở đó **không chứng minh không tồn tại thiết bị NVM nào khác trong máy hoặc hệ thống**; nó chỉ phản ánh yêu cầu map SYNC ở đúng đường dẫn và môi trường vừa thử.

### Fallback nên xử lý thế nào?

Nếu bạn cần **durability file thông thường**, có thể chọn `READ_WRITE` và `force` theo hợp đồng Javadoc cho storage cục bộ. Nếu bài toán yêu cầu **đặc tính DAX/persistent-memory SYNC** vì latency và thiết kế cụ thể, không nên âm thầm fallback rồi ghi log “NVM mode active”.

Ví dụ chính sách rõ ràng:

```java
// Snippet: chỉ dùng nếu dự án đã thiết kế fallback được phép.
try {
    useSyncMapping();
} catch (UnsupportedOperationException unsupported) {
    // Chỉ fallback khi yêu cầu sản phẩm chấp nhận mode thường
    // và đã đánh giá lại performance/durability.
    useOrdinaryReadWriteMapping();
}
```

Snippet này không độc lập: `useSyncMapping` và `useOrdinaryReadWriteMapping` là các phương thức nghiệp vụ giả định. Nếu SYNC mode là **điều kiện bắt buộc**, hãy fail fast với thông báo cấu hình có ích và giữ nguyên cause, thay vì tắt tính năng trong im lặng.

## 9. `MappedByteBuffer.force` khác `FileChannel.force(boolean)`

Đây là lỗi rất dễ mắc khi chuyển từ `FileChannel.write` sang memory mapping.

| API | Phạm vi chủ yếu | Exception | Ghi chú bảo đảm |
| --- | --- | --- | --- |
| `MappedByteBuffer.force()` | Nội dung toàn mapping buffer | `UncheckedIOException` nếu lỗi ghi | Dành cho thay đổi thực hiện **qua mapped buffer** |
| `MappedByteBuffer.force(index,length)` | Vùng được chỉ định trong mapping | `IndexOutOfBoundsException`, `UncheckedIOException` | Byte offset theo buffer, được phép ghi rộng hơn vùng |
| `FileChannel.force(false)` | Nội dung file do channel cập nhật | `IOException` | Chỉ buộc nội dung, có thể không buộc metadata |
| `FileChannel.force(true)` | Nội dung và metadata file theo hợp đồng | `IOException` | OS quyết định chi tiết; không mặc nhiên thay `mapped.force()` |

**Điểm quan trọng từ Javadoc `FileChannel.force`:** Phương thức này **chỉ bảo đảm** đẩy các thay đổi thực hiện bởi những phương thức FileChannel (hoặc FileOutputStream/RandomAccessFile liên quan theo hợp đồng); nó **có thể có hoặc không có tác dụng** đối với những thay đổi của `MappedByteBuffer` lấy từ `map(...)`.

Vì vậy, khi code làm:

```java
// Snippet: ghi bằng mapped buffer
mapped.putInt(0, 2026);
channel.force(true); // Không nên coi đây là thay thế chắc chắn cho mapped.force()
```

thì điều cần dùng để bảo đảm thay đổi vùng mapping là:

```java
mapped.force(0, Integer.BYTES);
```

Ngược lại, khi thay đổi nội dung qua `channel.write(...)` và cần đẩy cả nội dung lẫn metadata, `channel.force(true)` là API phù hợp cho những thay đổi thuộc phạm vi hợp đồng của channel.

**Nếu một giao dịch vừa cập nhật mapping vừa đổi metadata file**, thiết kế cần xét cả hai phạm vi, thứ tự ghi, tính crash consistency và đặc tính filesystem. **Không có một lựa chọn `force` duy nhất bảo đảm toàn bộ nhiều tài nguyên/đường dẫn được commit nguyên tử.**

## 10. `force` khác `load`, `isLoaded`, `flip` và `clear`

Những phương thức gần nhau dễ gây nhầm:

- `mapped.load()`: nỗ lực đưa dữ liệu của vùng mapping **vào RAM**; có thể tạo page faults/I/O. **Không phải thao tác persist**.
- `mapped.isLoaded()`: cho biết nhiều khả năng dữ liệu đã resident trong bộ nhớ vật lý; đây là **gợi ý**, không bảo đảm chắc chắn, và **không cho biết đã flush xuống storage**.
- `mapped.force()`: yêu cầu **đẩy sửa đổi của mapping** ra storage theo hợp đồng.
- `mapped.flip()`: đổi `limit/position` để chuẩn bị chuyển từ ghi tuần tự sang đọc tuần tự; **không flush**.
- `mapped.clear()`: đặt lại cursor/limit để dùng buffer; **không xóa dữ liệu và không bảo đảm flush**.
- `mapped.rewind()`: đưa position về đầu buffer; **không ảnh hưởng durability**.
- `channel.close()`: đóng channel; mapping đã tạo có vòng đời riêng, **không được coi thay `mapped.force()`**.

Một chương trình gọi `load` trước `force` có thể vô tình tạo thêm I/O nhưng vẫn không giải quyết đúng yêu cầu durability. Chọn API theo mục đích: **đọc nhanh hơn** và **ghi bền vững** là hai mục tiêu khác nhau.

## 11. Hiệu năng: force vùng nào, khi nào và chi phí ra sao?

`force` có thể gây thao tác đồng bộ với storage hoặc cache-line writeback, nên chi phí phụ thuộc:

- Dung lượng và số trang dữ liệu cần flush.
- Loại mapping: `READ_WRITE` thường hay `READ_WRITE_SYNC` NVM.
- Filesystem, driver, bộ điều khiển, thiết bị, tải I/O cùng lúc.
- Độ rộng của vùng force và tính phân tán của các sửa đổi.
- Số lần gọi, tần suất, khả năng gộp batch và chiến lược logging.
- Granularity trang/bộ nhớ và những lần flush thực tế ngoài phạm vi chỉ định.

### Ba cách áp dụng

**A. Flush toàn mapping tại một checkpoint**

```java
// Snippet: nhiều sửa đổi đã được ghi vào mapped buffer.
updateManyRecords(mapped);
mapped.force();
```

Phù hợp nếu toàn vùng dữ liệu cần được đẩy ở một mốc checkpoint rõ ràng. `updateManyRecords` là hàm nghiệp vụ giả định, snippet không độc lập.

**B. Flush đúng vùng logic vừa sửa**

```java
mapped.putLong(128, 42L);
mapped.force(128, Long.BYTES);
```

Đây là snippet giả định mapping có `capacity()` đủ lớn và writable. Dùng nếu chỉ một đoạn nhỏ cần durability ngay. Nhưng đừng kết luận OS **chỉ** ghi tám byte vật lý, bởi API được phép ghi thêm byte ngoài phạm vi vì granularity.

**C. Batch các sửa đổi theo mốc durability**

```java
// Pseudocode nghiệp vụ:
for (RecordUpdate update : batch) {
    writeMappedRecord(update);
}
forceAffectedRegions();
markBatchComplete();
```

Đoạn trên là **pseudocode**, không phải chương trình có các class và method được định nghĩa. Nếu yêu cầu crash consistency, `markBatchComplete` cũng phải có thiết kế thứ tự và persistence an toàn, không thể chỉ đánh dấu “đã xong” ở RAM.

### Không force mỗi byte vô điều kiện

Gọi `force(0,1)` sau từng `put(byte)` có thể làm số lần đồng bộ rất lớn, nhất là khi storage có granularity page/block. Chọn mức flush theo **độ bền yêu cầu**, **mức mất dữ liệu chấp nhận được** và **SLO độ trễ**. Đo trên thiết bị thật với kích thước dữ liệu và tải phù hợp, không lấy một benchmark JVM file tạm để kết luận về tốc độ NVM.

## 12. Tính nhất quán khi crash: `force` cần phối hợp với định dạng dữ liệu

Giả sử một record gồm:

```text
version (4 bytes)
length  (4 bytes)
payload (n bytes)
checksum (4 bytes)
commit flag
```

Nếu sửa trực tiếp từng field trong file mapped rồi gọi `force` một lần, hệ thống có thể bị crash trong **quá trình cập nhật**, và bản ghi có thể ở trạng thái **một phần cũ, một phần mới**. API không biến các `putInt` và `put(byte)` thành transaction.

Một số nguyên tắc thiết kế (không phải một thuật toán crash-safe hoàn chỉnh):

1. **Có định dạng on-disk xác định**, bao gồm byte order, size, alignment, version và checksum.
2. **Tránh sửa trực tiếp record đang được coi là đã commit** nếu reader cần luôn đọc trạng thái nhất quán.
3. **Cân nhắc hai slot/copy-on-write hoặc journal**, mỗi bản có sequence number và checksum.
4. **Đẩy nội dung record mới** bằng `force` đúng vùng trước khi công bố trạng thái mới.
5. **Thiết kế commit marker/metadata** và quy tắc thứ tự durability phù hợp phần cứng/filesystem; marker cũng cần cơ chế persist riêng.
6. **Sau crash**, phục hồi bằng cách chọn bản ghi hoàn chỉnh/hợp lệ theo checksum/version, thay vì giả định tất cả write đã atomic.
7. **Test lỗi và restart** tại nhiều điểm; không chỉ test “chạy xong bình thường rồi đọc lại”.

**Cảnh báo:** Chiến lược trên là các nguyên tắc để phân tích thiết kế. Atomicity, tear-free write, ordering và flush của hệ thống lưu trữ có yêu cầu rất riêng; **không thể tuyên bố hai `force` liên tiếp tự động tạo một transaction an toàn** nếu không có giao thức commit và giả định phần cứng rõ ràng.

## 13. Mapping lifecycle, đồng thời và an toàn dữ liệu

### 13.1. Không ghi/truncate file cùng lúc mà không phối hợp

`MappedByteBuffer` phản ánh một vùng file-backed. Nội dung có thể bị thay đổi bởi chương trình khác hoặc thread khác. Nếu file bị **truncate** trong lúc buffer còn được ánh xạ, một phần mapping có thể trở nên không truy cập được và hành vi lỗi khi đọc/ghi phụ thuộc OS/JVM theo Javadoc.

Vì vậy:

- Chỉ một writer hoặc giao thức phối hợp rõ ràng khi nhiều writer.
- Tránh resize/truncate cùng tệp khi mapping vẫn đang sử dụng.
- Phân định vùng byte mà mỗi writer được phép sửa.
- Ghi nhận thiết kế khóa, memory visibility và read-after-write; `force` **không phải lock hoặc memory barrier cho toàn bộ object graph Java**.
- Đừng cho rằng những thay đổi từ process khác ngay lập tức đồng bộ theo lịch trình cố định.

### 13.2. Mapping sống lâu hơn `FileChannel`

`FileChannel.map(...)` trả `MappedByteBuffer`; mapping được duy trì đến khi buffer tương ứng được garbage-collected theo hợp đồng API. **`FileChannel.close()` không làm mapping vừa tạo tự biến mất ngay lập tức.**

Điều này ảnh hưởng việc xóa file, đổi tên, không gian địa chỉ và vòng đời resource trên một số OS. Với hệ thống cần **unmap xác định**, Java hiện đại còn hỗ trợ API mapped memory segment qua `FileChannel.map(..., Arena)` (từ Java 22) trong ngữ cảnh thiết kế khác; không nên dùng hack truy cập `sun.misc.Unsafe` hoặc API nội bộ để ép unmap buffer.

Bài này tập trung `MappedByteBuffer.force`; khi chọn API khác như `MemorySegment.force()`, hãy đọc đúng tài liệu của loại mapping và quản lý `Arena` tương ứng.

### 13.3. Exception và xử lý thất bại

`MappedByteBuffer.force` có thể ném **`UncheckedIOException`** khi I/O flush thất bại. Ví dụ:

```java
// Snippet nằm trong phương thức có logger và mapped.
try {
    mapped.force();
} catch (java.io.UncheckedIOException failure) {
    logger.log(
            java.util.logging.Level.SEVERE,
            "Không thể persist vùng file ánh xạ", failure);
    throw failure;
}
```

Đây không phải mã độc lập; nó minh họa **giữ Throwable/stack trace** khi log. Khi flush thất bại, không ghi lại “checkpoint hoàn thành” hoặc chuyển state sang success. Cần quyết định retry, cô lập file, fail-fast hoặc đưa hệ thống vào trạng thái chỉ đọc theo yêu cầu nghiệp vụ và đặc tính storage.

Nếu dùng `FileChannel.force(boolean)` thì cần xử lý checked `IOException` theo hợp đồng của method đó. Đừng bắt tất cả exception rồi trả về một giá trị mặc định khiến hệ thống tưởng dữ liệu đã bền.

## 14. Các hiểu nhầm phổ biến

| Nhận định / lỗi | Vì sao sai | Cách áp dụng đúng |
| --- | --- | --- |
| “`put(...)` xong là dữ liệu đã persistent” | Mapping có thể chỉ mới dirty trong cache | Gọi `force` khi yêu cầu có mốc durability |
| “Gọi `flip()`/`clear()` là flush” | Chỉ đổi trạng thái buffer | Dùng `MappedByteBuffer.force` |
| “`load()` = đẩy dữ liệu xuống NVM” | `load` nạp **vào RAM**, không persist | Phân biệt `load` và `force` |
| “`force()` chỉ làm từ position tới limit” | Nó tương đương `force(0,capacity())` | Dùng `force(index,length)` để chọn vùng |
| “Index của `force` là file offset tuyệt đối” | Index tương đối buffer mapping | Cộng map offset khi reasoning file location |
| “`force(14,3)` hợp lệ với capacity 16” | Vùng vượt capacity | Kiểm tra `index+length <= capacity` |
| “`force(index,len)` chỉ ghi chính xác len byte vật lý” | OS có thể flush thêm block/page | Không dựa vào lượng I/O byte chính xác |
| “`PRIVATE.force()` lưu sửa đổi vào file gốc” | Private copy-on-write không lan về file | Dùng `READ_WRITE` |
| “`READ_ONLY.force()` bảo đảm persist” | Không có sửa đổi qua buffer read-only | Không dùng force để chứng minh file đã được cập nhật |
| “`FileChannel.force(true)` luôn thay `mapped.force()`” | Javadoc không bảo đảm force các write qua mapped buffer | Flush bằng chính mapped buffer |
| “`READ_WRITE_SYNC` dùng được mọi máy” | JDK/OS/filesystem/NVM có thể không hỗ trợ | Check capability, handle UOE |
| “SSD = NVM DAX” | Storage SSD thông thường khác direct persistent memory | Xác minh hardware và filesystem DAX |
| “force thành công = nhiều record commit nguyên tử” | `force` không phải transaction | Dùng journal/checksum/commit protocol |
| “Đọc lại file sau close chứng minh chịu mất điện” | Cache có thể trả dữ liệu bình thường | Kiểm tra theo hợp đồng, test crash riêng |
| “Mapping biến mất khi channel close” | Mapping có vòng đời riêng | Quản lý lifecycle, tránh truncate/delete khi dùng |
| “Nếu force gặp lỗi, cứ báo đã lưu” | Durability chưa được xác nhận | Log Throwable, fail hoặc retry có kiểm soát |
| “Force file trên network có cam kết như local” | API không đưa bảo đảm tương đương | Xác minh semantics NFS/SMB/provider |
| “Bất kỳ giá trị `MappedByteBuffer` nào cũng map được NVM” | Chế độ thông thường không chứng minh DAX | Dùng `ExtendedMapMode` đúng môi trường khi cần |

## 15. Checklist khi triển khai dữ liệu bền trên mapped file

- [ ] Đã xác định **storage thực tế** là local file thường, network file hay NVM/DAX?
- [ ] Đã chọn **`READ_WRITE`** hoặc `READ_WRITE_SYNC` (chỉ khi được hỗ trợ) theo yêu cầu?
- [ ] File đã được tạo/chuẩn bị kích thước phù hợp trước khi map?
- [ ] Mọi `put` cần durability đều được bao trong **vùng `force` tương ứng**?
- [ ] `index` của `force(index,length)` tính tương đối buffer và không vượt capacity?
- [ ] Hiểu rằng `force()` flush toàn capacity, không chỉ khoảng position..limit?
- [ ] Đã xử lý `UncheckedIOException` và lỗi mở/map của channel?
- [ ] Không coi `FileChannel.force(true)` là thay thế mặc định cho mapped force?
- [ ] Nếu dùng SYNC mapping, có kiểm tra DAX/OS/JDK, không silent fallback?
- [ ] Không giả định network storage có bảo đảm durability như local?
- [ ] Nếu data quan trọng, đã có checksum, version, phục hồi sau crash và kế hoạch kiểm thử?
- [ ] Đã phối hợp concurrent writers, tránh resize/truncate mapped file ngoài ý muốn?
- [ ] Có đo chi phí flush và chọn batching/độ dài vùng phù hợp?
- [ ] Không dùng `load`/`clear`/`flip` để giả làm persist?
- [ ] Có chiến lược vòng đời mapping và cleanup file theo OS?
- [ ] Phân biệt kết quả **đọc lại thành công** với kiểm thử thật về mất điện/durability?

## 16. Câu hỏi tự kiểm tra

**1. Vì sao `mapped.putInt(...)` không đủ nếu ứng dụng cần một checkpoint đã ghi bền?**

Vì nó chỉ sửa vùng mapped memory. `force` cung cấp thao tác yêu cầu đẩy thay đổi theo hợp đồng Java API; không có `force`, lịch trình writeback có thể do OS quyết định.

**2. `force()` flush theo `position..limit` hay theo toàn `capacity`?**

Theo **toàn `capacity`**; API quy định tương đương `force(0, capacity())`.

**3. Mapping tại file offset 4096, gọi `force(20,4)` đang nói tới những byte nào?**

Byte index 20..23 trong buffer, tương ứng file offset 4116..4119 của mapping đó.

**4. Sau `force(0,4)`, có chắc hệ điều hành chỉ ghi đúng bốn byte không?**

Không. Javadoc cho phép writeback ngoài vùng nếu cần do granularity storage/page.

**5. `FileChannel.force(true)` có chắc đẩy những thay đổi ghi qua `MappedByteBuffer.put`?**

Không. Javadoc `FileChannel.force` không đưa bảo đảm tổng quát cho changes made via mapped buffer; dùng `mapped.force` cho mục đích đó.

**6. `READ_WRITE_SYNC` khác `READ_WRITE` ở điểm nào?**

SYNC mode nhắm persistent-memory-backed file và, trên implementation hỗ trợ, dùng cache-line writeback khi `force`; mode thông thường thực hiện flush theo cơ chế file/device. SYNC mode **không portable tới mọi OS/file**.

**7. Tại sao ví dụ đọc lại được `NVM!` không chứng minh chống mất điện?**

Vì một lần đọc bình thường có thể thấy dữ liệu trong cache hoặc sau khi flush; không mô phỏng được mất điện giữa các bước. Cần kết hợp hợp đồng API, bảo đảm thiết bị và test crash/recovery có kiểm soát.

**8. `force` có tự làm một record nhiều field được cập nhật nguyên tử không?**

Không. Cần thiết kế layout, checksum/version, journal/commit marker và xác nhận persistence/ordering trên storage thực tế.

## 17. Nguồn chính thức đang áp dụng

- [Oracle Java 25 API — `MappedByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): hợp đồng `force()` và `force(index,length)`, giới hạn local/non-local, exception và lifecycle.
- [Oracle Java 25 API — `FileChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): `map`, `force(boolean)`, các MapMode, giới hạn bảo đảm khi dùng mapped buffer.
- [Oracle Java 25 API — `ExtendedMapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): `READ_ONLY_SYNC`/`READ_WRITE_SYNC` và cache-line writeback NVM.
- [Oracle Java 25 API — `FileChannel.MapMode`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): `READ_ONLY`, `READ_WRITE`, `PRIVATE`.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): lịch sử bổ sung hỗ trợ non-volatile memory mapping trong Java 14 và mục tiêu persistence.
- [Oracle Java 25 API — `MemorySegment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html): lựa chọn mapped memory hiện đại khác, khi ứng dụng yêu cầu lifecycle được quản lý bởi `Arena`.

**Ghi nhớ:** Với `MappedByteBuffer`, **`force` là điểm yêu cầu đẩy các thay đổi của mapping tới storage**, không phải thao tác đổi cursor, đồng bộ thread hoặc transaction. Dùng **`force(index,length)`** khi chỉ cần một vùng; dùng **`READ_WRITE_SYNC`** cho NVM/DAX **chỉ khi nền tảng hỗ trợ**. Luôn phân biệt **bảo đảm cho file local**, hạn chế network/storage và nhu cầu thiết kế phục hồi sau crash.
