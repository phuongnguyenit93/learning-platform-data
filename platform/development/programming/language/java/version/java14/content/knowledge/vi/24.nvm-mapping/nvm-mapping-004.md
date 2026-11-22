# Điều kiện phần cứng, hệ thống tệp và hệ điều hành hỗ trợ ánh xạ NVM trong Java

> **Ngữ cảnh:** Java 14 → *Ánh xạ NVM* → **Điều kiện phần cứng, hệ thống tệp và hệ điều hành hỗ trợ**. **JEP 352 – Non-Volatile Mapped Byte Buffers** đưa các chế độ `ExtendedMapMode.READ_ONLY_SYNC` và `READ_WRITE_SYNC` vào JDK 14. API này **vẫn có trong tài liệu Oracle JDK 25**. Các ví dụ dùng **Java 17+**, không dùng preview, incubator hoặc hướng dẫn chỉ hợp với phần mềm cũ.

## 1. Câu hỏi quan trọng nhất: điều kiện nào phải đồng thời đúng?

Ánh xạ tệp NVM qua `FileChannel.map(ExtendedMapMode.READ_WRITE_SYNC, ...)` **không phải** khả năng mặc định của mọi ổ cứng, hệ thống tệp hay JVM. Một môi trường có thể có Java mới nhất, ổ SSD “non-volatile” và `FileChannel.map()` thông thường vẫn hoạt động, nhưng **SYNC mapping vẫn không được hỗ trợ**.

Để chế độ ánh xạ này hoạt động như thiết kế, cần xét **cả chuỗi điều kiện**:

1. **Thiết bị hoặc tầng bộ nhớ:** tệp nằm trên một vùng lưu trữ có khả năng **truy cập trực tiếp bằng CPU theo địa chỉ bộ nhớ**, phù hợp với mô hình persistent memory / DAX; không chỉ đơn thuần là ổ lưu trữ không mất dữ liệu khi tắt nguồn.
2. **Bộ điều khiển và phần mềm hệ thống:** firmware, driver, kernel và cơ chế xử lý persistence hỗ trợ ánh xạ phù hợp; ở Linux, ánh xạ SYNC của Java dựa vào `mmap` với `MAP_SHARED_VALIDATE` và `MAP_SYNC`.
3. **Hệ thống tệp + tệp thực tế:** hệ thống tệp có đường đi **Filesystem DAX (FS-DAX)** phù hợp và **chính tệp được ánh xạ** đang ở chế độ DAX; chỉ nhìn tên filesystem như `ext4`/`xfs` là chưa đủ.
4. **Triển khai JVM/JDK:** có module `jdk.nio.mapmode`, `ExtendedMapMode` và triển khai native hỗ trợ sync map trên OS/architecture đang dùng.
5. **Quyền và file hợp lệ:** kênh được mở theo chế độ đọc/ghi tương ứng, tệp được tạo hoặc có chiều dài hợp lệ, không bị hạn chế bởi mount, bảo mật, quota, phân vùng hay provider.
6. **Thử nghiệm trên đúng đường dẫn thật:** thực hiện `FileChannel.map(READ_WRITE_SYNC, ...)` với một tệp nằm trong **đúng thư mục DAX dự kiến**, sau đó ghi và `force()`. Kiểm tra lỗi thực tế.

~~~text
JDK có ExtendedMapMode?
        |
        v
OS + kernel hỗ trợ kiểu MAP_SYNC tương ứng?
        |
        v
Thiết bị / namespace thực sự hỗ trợ direct access?
        |
        v
File system và FILE ĐÍCH đang bật DAX phù hợp?
        |
        v
Quyền, file size, FileChannel options đúng?
        |
        v
map(READ_WRITE_SYNC,...) thành công?
        |
        +-- không --> KHÔNG được tự kết luận "NVM đã hoạt động"
        |
        +-- có ----> có khả năng SYNC mapping tại đường dẫn vừa thử
                      |
                      v
                 kiểm thử durability, crash consistency
                 và hiệu năng ở tầng ứng dụng
~~~

**Nguyên tắc:** kết quả **“có API Java”** không tương đương kết quả **“hardware NVM hoạt động”**. Kết quả ánh xạ thành công chỉ xác nhận **tổ hợp môi trường và file đã thử**, không đảm bảo mọi tệp trên máy cũng có DAX.

## 2. Phân biệt NVM, PMEM, NVMe SSD và RAM

Các thuật ngữ thường bị đánh đồng nhưng mang nghĩa khác nhau:

| Thuật ngữ | Ý nghĩa | Có tự đủ để dùng `READ_WRITE_SYNC` không? |
| --- | --- | --- |
| **NVM (non-volatile memory)** | Bộ nhớ giữ dữ liệu sau khi mất nguồn; thuật ngữ khá rộng | **Không**; cần biết cách CPU truy cập và tầng OS cung cấp |
| **Persistent memory (PMEM)** | Bộ nhớ có khả năng giữ dữ liệu và thường được trình bày qua không gian địa chỉ để CPU truy cập trực tiếp | **Chưa đủ**; còn cần DAX, kernel, filesystem và JVM |
| **NVDIMM / vùng PMEM DAX-capable** | Một dạng thiết bị/namespace có thể hỗ trợ memory-mapped direct access | **Có thể phù hợp**, khi được cấu hình đúng |
| **NVMe SSD thông thường** | Thiết bị lưu trữ block, thường dùng flash; dữ liệu không mất nguồn | **Không mặc nhiên** là byte-addressable PMEM/FS-DAX |
| **DRAM / tmpfs** | RAM thông thường và hệ thống tệp dựa trên RAM | Không có ý nghĩa persistent-memory SYNC tương ứng; dữ liệu không có cam kết tồn tại qua mất nguồn |
| **Device DAX (`/dev/dax...`)** | Namespace cung cấp ánh xạ thiết bị kiểu ký tự, **không đi qua filesystem thông thường** | Khác đường đi FS-DAX; đừng xem một `/dev/dax` là thư mục chứa tệp cho ví dụ `Files.createTempFile` |
| **Filesystem DAX (FS-DAX)** | Kernel cho phép file mapping trực tiếp vào bộ nhớ của thiết bị tương thích, bỏ qua page cache cho nội dung file | **Ứng viên thích hợp**, nhưng Java SYNC mode vẫn phải được thử thực tế |

**Vì sao “SSD cũng không mất dữ liệu” chưa đủ?** Nhiều SSD thông thường được truy cập bằng **block I/O**; Java `mmap` thông thường có thể đưa những trang **page cache DRAM** vào không gian địa chỉ, không đồng nghĩa file được map thẳng tới byte-addressable persistent memory. Mode `READ_WRITE_SYNC` có semantics và đường thực thi khác, không tự chuyển mọi SSD thành thiết bị PMEM.

**Vì sao còn phải quan tâm đến mất nguồn?** Ngay trên PMEM, dữ liệu vừa được CPU ghi có thể nằm trong processor caches hoặc các miền đệm khác. `force()` với SYNC mapping liên quan đến việc thực hiện writeback/cache-line flush theo triển khai; điều này **không tự cung cấp atomic transaction hoặc khôi phục cấu trúc dữ liệu sau crash**. Cần thêm thiết kế consistency như write-ahead log, bản ghi có version/checksum và thứ tự ghi hợp lý.

## 3. API Java vẫn áp dụng trên JDK hiện đại

Java cung cấp hai chế độ thông qua module **`jdk.nio.mapmode`**:

| API | Ý nghĩa | Giới hạn chính |
| --- | --- | --- |
| `ExtendedMapMode.READ_ONLY_SYNC` | Ánh xạ chỉ đọc của tệp dựa trên non-volatile RAM | Không dùng để ghi; không phải mọi hệ điều hành/filesystem hỗ trợ |
| `ExtendedMapMode.READ_WRITE_SYNC` | Ánh xạ đọc/ghi của tệp dựa trên non-volatile RAM | Cần môi trường SYNC mapping phù hợp; `force()` dùng cơ chế cache-line writeback theo ghi chú API |
| `FileChannel.MapMode.READ_ONLY` | Map tệp chỉ đọc thông thường | Không có ngữ nghĩa NVM-specific |
| `FileChannel.MapMode.READ_WRITE` | Map đọc/ghi thông thường | Không tự xác nhận DAX hoặc persistence domain |
| `MappedByteBuffer.force()` / `force(index,length)` | Yêu cầu flush nội dung vùng map, với semantics do mode và file provider xác định | Không tạo transaction, lock hay bản sao dự phòng |

Các hằng số `READ_ONLY_SYNC`/`READ_WRITE_SYNC` là **JDK-specific**, không nằm trong ba mode chuẩn `READ_ONLY`/`READ_WRITE`/`PRIVATE` của `FileChannel.MapMode`. Các mode SYNC được khai báo dưới `jdk.nio.mapmode.ExtendedMapMode`, có mặt từ Java 14 và vẫn được tài liệu JDK 25 công nhận.

### 3.1. Khi nào `map` có thể thất bại?

`FileChannel.map(...)` có thể ném:

- `UnsupportedOperationException`: Java/implementation không hỗ trợ map mode yêu cầu.
- `IOException`: I/O hoặc thao tác ánh xạ bị từ chối bởi OS, filesystem, mount, thiết bị hoặc nguyên nhân khác.
- `NonReadableChannelException` / `NonWritableChannelException`: channel không được mở theo quyền phù hợp với mode.
- `IllegalArgumentException`: offset/size sai điều kiện hoặc các tham số khác không hợp lệ.
- Lỗi phát sinh ở bước `Files.createTempFile` hoặc `FileChannel.open`: quyền, hết dung lượng, đường dẫn không hợp lệ, quota v.v.

**Không xử lý mọi lỗi thành “thiết bị chắc chắn không hỗ trợ NVM”.** Ví dụ một thiết bị có DAX nhưng user không có quyền ghi cũng khiến phép thử thất bại. Kết luận chỉ nên là **chưa dùng được với tổ hợp file/JDK/OS/quyền hiện tại**, sau đó đọc nguyên nhân thực.

### 3.2. `--add-modules jdk.nio.mapmode`

Ví dụ chương trình trên **classpath**, không có `module-info.java`, dùng:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode NvmCapabilityProbe.java
java --add-modules jdk.nio.mapmode NvmCapabilityProbe /mnt/pmem/test-area
~~~

Đây là lệnh mẫu cho **JDK 17+**, không phải lệnh có thể chạy khi chưa có thư mục `/mnt/pmem/test-area`. Nếu ứng dụng là **Java module có `module-info.java`**, hãy khai báo `requires jdk.nio.mapmode;` và cấu hình module path/build phù hợp.

Không giả định mọi custom runtime image hoặc Java distribution đều chứa `jdk.nio.mapmode`. Có thể kiểm tra:

~~~bash
java --list-modules | grep '^jdk.nio.mapmode@'
~~~

Lệnh trên dùng Linux/Bash và chỉ xác nhận **module hiện diện trong runtime**; nó **không chứng minh native OS mapping sẽ thành công**.

## 4. Hệ điều hành: ưu tiên kiểm tra Linux và không suy diễn sang nền tảng khác

### 4.1. Vì sao tài liệu Java nhắc riêng Linux?

Javadoc `ExtendedMapMode` của **JDK 25** nêu rõ implementation note:

- Trên **Linux**, khi dùng các SYNC modes, native `mmap` được yêu cầu với **`MAP_SYNC`** và **`MAP_SHARED_VALIDATE`**.
- `READ_WRITE_SYNC` định hướng `force()` dùng **cache-line writeback** thay vì đường flush của block file device thông thường.
- Nếu implementation không hỗ trợ mode đó, `FileChannel.map` ném `UnsupportedOperationException`.

Điều kiện này cho biết **đường triển khai trên Linux**, **không phải lời hứa mọi kernel Linux và mọi filesystem đều hỗ trợ**. Tổ hợp kernel, CPU architecture, thiết bị, DAX filesystem, mount policy và file cụ thể phải phù hợp. Một filesystem có DAX nói chung chưa chắc đáp ứng `MAP_SYNC` trong mọi tình huống.

### 4.2. Windows và macOS

Không thể suy ra `READ_WRITE_SYNC` được hỗ trợ trên Windows/macOS chỉ vì:

- Cùng chương trình chạy được trên Linux;
- Dùng JDK 17/21/25;
- Có `ExtendedMapMode` trong `java --list-modules`;
- Ổ chứa tệp là SSD hoặc có nhãn “persistent”.

Trong lần kiểm chứng của bài trên **Windows với OpenJDK 24**, đoạn Java dùng `ExtendedMapMode.READ_WRITE_SYNC` biên dịch được nhưng `map` trả `UnsupportedOperationException`. Đây là **một quan sát tại môi trường kiểm tra**, không phải tuyên bố tuyệt đối về mọi phiên bản JVM/OS.

Với macOS hoặc một JVM khác, cần **đối chiếu tài liệu của bản phân phối** và **thử map thực tế**; nếu không hỗ trợ, dùng API ánh xạ tệp thông thường khi phù hợp mục đích, hoặc thay thiết kế theo những tính năng được platform hỗ trợ.

### 4.3. Máy ảo, container và remote filesystem

Một môi trường Linux container chạy trên host có PMEM có thể **không được cấp quyền hoặc không nhìn thấy mount DAX đúng**. Tương tự, một VM có thể thấy block device do hypervisor cung cấp nhưng không có cùng semantics persistence như host.

- **Container**: xác minh mount namespace, user permissions, đường dẫn bind mount, LSM/seccomp policy và backing storage thật.
- **VM**: xác minh guest kernel, loại device được expose (ví dụ virtiofs DAX nếu sử dụng) và cam kết persistence của lớp ảo hóa.
- **Network filesystem**: không giả định file nằm trên NFS/SMB/remote store được hỗ trợ `MAP_SYNC`; các bảo đảm `force()` trên file không nằm ở local device khác so với local storage.
- **WSL**: không chỉ dựa vào tên “Linux” trong user space; phải kiểm tra kernel, filesystem mount và thiết bị DAX thật được expose.

**Nguyên tắc triển khai:** kiểm tra **file path thật mà `FileChannel.open` sử dụng**, không chỉ kiểm tra host OS nói chung.

## 5. Hệ thống tệp Linux: FS-DAX và trạng thái của chính file

### 5.1. Những filesystem nào có DAX?

Tài liệu **Linux kernel hiện hành** liệt kê một số filesystem có đường hỗ trợ DAX như **ext2, ext4, XFS, virtiofs, EROFS**. Nhưng đây là danh sách **hỗ trợ DAX ở các dạng khác nhau**, không phải cam kết rằng mọi filesystem đó có thể **tạo file đọc/ghi trên PMEM và map `READ_WRITE_SYNC`** trong mọi kernel.

Đối với **file đọc/ghi được đặt trên persistent memory theo mô hình FS-DAX**, các trường hợp thường được quản trị và kiểm chứng là **XFS** hoặc **ext4** trên một backing device/namespace có khả năng direct access. Những điều kiện khác vẫn cần kiểm tra:

1. Filesystem driver và kernel có hỗ trợ đường DAX phù hợp.
2. Device/namespace bên dưới thực sự có khả năng direct access.
3. **DAX policy** được bật cho file mới hoặc file đang có.
4. **Trạng thái hoạt động** của file là DAX, không chỉ có một flag yêu cầu DAX.
5. `mmap` có `MAP_SYNC` thành công cho chính file đó.
6. User được phép đọc/ghi và kích thước file hợp lệ.

**Đừng nhầm filesystem có tên XFS/ext4 với DAX đã bật.** Một thư mục XFS trên SSD bình thường chưa chứng minh bất kỳ điều kiện PMEM nào.

### 5.2. `FS_XFLAG_DAX` khác `S_DAX`

Với Linux **ext4/XFS**, kernel phân biệt hai trạng thái:

| Trạng thái | Ý nghĩa | Vì sao quan trọng? |
| --- | --- | --- |
| `FS_XFLAG_DAX` | Flag **advisory/persistent** được gắn với inode hoặc thư mục để yêu cầu chính sách DAX, có thể được thừa kế bởi file mới | Có flag này **không bảo đảm** DAX đang hoạt động |
| `S_DAX` | Trạng thái DAX **thực sự hoạt động trong kernel** đối với inode file | Đây là thứ cần xác minh, có thể quan sát bằng `statx` với `STATX_ATTR_DAX` |
| `dax=inode` | Mount policy theo flag inode trên XFS/ext4, là chế độ mặc định trong nhiều cấu hình kernel hiện đại | File mới cần thừa kế hoặc được cấu hình đúng |
| `dax=always` | Mount policy buộc cố gắng bật DAX cho file theo cơ chế filesystem, bỏ qua advisory flag | Chỉ có hiệu lực nếu backing storage và kernel thực sự hỗ trợ |
| `dax=never` | Tắt trạng thái DAX dù có advisory flag | `MAP_SYNC` NVM có thể thất bại |

Tài liệu kernel cảnh báo dạng mount option cũ **`-o dax`** là alias có thể bị loại bỏ; nếu cần mô tả chế độ toàn filesystem trên kernel hiện đại, ưu tiên ngữ nghĩa rõ ràng **`dax=always`**. **Không tự sửa mount option trên server đang chạy** nếu chưa có thẩm quyền vận hành: thay đổi chính sách có thể tác động dữ liệu, availability và khả năng khởi động.

Việc thay `FS_XFLAG_DAX` của file đang mở không nhất thiết làm `S_DAX` đổi ngay; kernel có điều kiện về **đóng file/evict inode** rồi mới đánh giá lại. Vì vậy **chỉ kiểm tra một flag trên thư mục** chưa đủ để kết luận trạng thái file cụ thể.

### 5.3. Kiểm tra DAX trên Linux theo cách đọc, không phá dữ liệu

Một chuỗi preflight mang tính quan sát:

~~~bash
# 1. Xem filesystem chứa đúng đường dẫn mục tiêu.
findmnt -T /mnt/pmem/test-area -o TARGET,SOURCE,FSTYPE,OPTIONS

# 2. Xem thiết bị, namespace và kiểu filesystem.
lsblk -o NAME,TYPE,FSTYPE,MOUNTPOINTS

# 3. Nếu có xfs_io, kiểm tra thuộc tính trên một FILE THỰC,
#    không chỉ kiểm tra thư mục.
xfs_io -c 'lsattr' /mnt/pmem/test-area/probe.bin

# 4. Kiểm tra trạng thái DAX thực (S_DAX) bằng statx.
xfs_io -c 'statx -r' /mnt/pmem/test-area/probe.bin
~~~

Các đường dẫn `/mnt/pmem/test-area` và `probe.bin` là **ví dụ**, phải thay bằng mount và file thực. `probe.bin` cần tồn tại trước khi gọi các bước 3–4. `xfs_io` có thể chưa được cài và lệnh `statx` của nó phụ thuộc phiên bản công cụ. `lsblk`/`findmnt` chủ yếu cho thông tin **backing device và mount**, không chứng minh một file cụ thể ở `S_DAX`.

Theo tài liệu kernel, `STATX_ATTR_DAX` cho biết trạng thái `S_DAX` được phản ánh từ kernel. Ví dụ một output mang tính minh họa có thể hiển thị:

~~~text
stat.attributes = 0x2000
~~~

`0x2000` là bit flag `STATX_ATTR_DAX` trong trường thuộc tính được báo cáo, **không phải một đoạn output được đo trên máy hiện tại**. Các phiên bản `xfs_io` có thể in thêm trường khác; kiểm tra **flag thực** thay vì so sánh nguyên văn cả dòng.

**Đặc biệt:** file được tạo mới có thể thừa kế DAX policy từ thư mục cha nếu dùng `dax=inode`. Vì vậy probe Java bên dưới tạo **file tạm ngay trong thư mục được chỉ định** để phép thử gắn với chính môi trường cần triển khai, thay vì tạo trong thư mục temp mặc định có thể nằm trên ổ khác.

### 5.4. FS-DAX khác Device-DAX

**Filesystem DAX (FS-DAX):** một vùng lưu trữ được gắn vào hệ thống tệp; bạn tạo một regular file, rồi map file đó. Bài này dùng `FileChannel.open(Path)` và `Files.createTempFile` theo mô hình ấy.

**Device DAX (devdax):** namespace được expose như một device đặc biệt (thường dạng `/dev/daxN.M`), không có XFS/ext4 ở trên và không có regular files như `/mnt/pmem/data.bin`. Thiết kế ứng dụng để map trực tiếp device là **bài toán khác**, cần kiểm tra device permissions, phạm vi vùng nhớ và API/driver cụ thể; **không truyền `/dev/dax0.0` vào ví dụ yêu cầu một directory chứa file tạm**.

DAX theo nghĩa kernel có thể dùng cho các tình huống khác ngoài byte-addressable persistent memory, nhưng **khả năng DAX không tự khẳng định dữ liệu tồn tại sau mất nguồn**. Cần xem riêng đặc tính của storage và platform.

## 6. Chương trình Java 17+: thử SYNC mapping an toàn trên đúng thư mục đích

Ví dụ tạo **một tệp mới với tên ngẫu nhiên** trong directory được chỉ định, ghi kích thước 4096 byte, sau đó thử `READ_WRITE_SYNC` và gọi `force(...)`. Không ghi đè dữ liệu hiện có, không tự thay mount/DAX policy. Khi kết thúc, xóa tệp thử nghiệm.

**File: `NvmCapabilityProbe.java`**

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import jdk.nio.mapmode.ExtendedMapMode;

public class NvmCapabilityProbe {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("usage: NvmCapabilityProbe <directory>");
            return;
        }

        Path directory = Path.of(args[0]);
        if (!Files.isDirectory(directory)) {
            throw new IllegalArgumentException("not a directory");
        }

        // Tạo một file MỚI trong đúng filesystem cần thử.
        Path file = Files.createTempFile(
                directory, "nvm-probe-", ".bin");

        try {
            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                final int size = 4096;
                ByteBuffer initial = ByteBuffer.allocate(size);
                while (initial.hasRemaining()) {
                    channel.write(initial);
                }

                try {
                    MappedByteBuffer mapped =
                            channel.map(
                                    ExtendedMapMode.READ_WRITE_SYNC,
                                    0, size);

                    mapped.putInt(0, 42);
                    mapped.force(0, Integer.BYTES);

                    System.out.println("syncMap=SUPPORTED");
                    System.out.println("value=" + mapped.getInt(0));

                } catch (UnsupportedOperationException
                         | IOException
                         | UncheckedIOException ex) {

                    System.out.println("syncMap=UNAVAILABLE");
                    System.out.println(
                            "cause=" + ex.getClass().getSimpleName());
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch trên JDK 17+ có module `jdk.nio.mapmode`:

~~~bash
javac --release 17 --add-modules jdk.nio.mapmode NvmCapabilityProbe.java
~~~

Chạy **trên Linux có thư mục FS-DAX bạn đã kiểm tra**:

~~~bash
java --add-modules jdk.nio.mapmode \
  NvmCapabilityProbe /mnt/pmem/test-area
~~~

Hoặc chạy trên Windows PowerShell để **kiểm tra đường dẫn hiện tại, không kỳ vọng có PMEM**:

~~~powershell
java --add-modules jdk.nio.mapmode NvmCapabilityProbe .
~~~

### 6.1. Kết quả và cách diễn giải

**Trên Windows/JDK 24 được thử trong quá trình biên soạn**, chương trình trên in:

~~~text
syncMap=UNAVAILABLE
cause=UnsupportedOperationException
~~~

**Trên một hệ Linux/thiết bị/file thực sự hỗ trợ mode**, nhánh thành công của chương trình sẽ in:

~~~text
syncMap=SUPPORTED
value=42
~~~

Dòng thành công là **kết quả dự kiến có điều kiện**; không phải output đã đo trên một máy Linux DAX trong lần kiểm chứng này.

Nếu kernel/file không hỗ trợ `MAP_SYNC`, thiết bị thiếu tính năng, mount không bật DAX hoặc có I/O error, chương trình có thể in `syncMap=UNAVAILABLE` với nguyên nhân `IOException` hoặc `UnsupportedOperationException`. Những lỗi khi **tạo tệp, mở channel hay xóa file** được cho phép lan ra ngoài để không nhầm với lỗi riêng của map mode.

### 6.2. Vì sao đoạn code viết như vậy?

1. `Files.createTempFile(directory,...)` tạo một file mới **ngay trên filesystem đang thử**; không đụng vào file dữ liệu thực.
2. Mở `FileChannel` với **READ và WRITE**; `READ_WRITE_SYNC` cần quyền đọc/ghi tương ứng.
3. Ghi đủ 4096 byte vào file trước khi map để vùng `[0,4096)` tồn tại; vòng lặp `while (initial.hasRemaining())` tránh giả định một lời gọi `write` luôn ghi hết.
4. `channel.map(ExtendedMapMode.READ_WRITE_SYNC, 0, size)` là **phép kiểm tra khả năng thực sự** của đường Java → OS → FS → device.
5. `mapped.putInt(0,42)` ghi vào vùng mapped.
6. `mapped.force(0,Integer.BYTES)` yêu cầu đồng bộ vùng vừa sửa theo semantics của SYNC mode; không tự tạo transaction.
7. `try-with-resources` đóng file channel; `finally` xóa tệp thử nghiệm.
8. Nếu không hỗ trợ, chương trình **báo UNAVAILABLE rõ ràng**, không tự đổi sang `MapMode.READ_WRITE` rồi in “SUPPORTED”.

**Không xóa file ngoài ý muốn:** chương trình chỉ xóa file **mới do chính nó tạo ra**. Nếu OS không thể xóa file đang còn mapped (một số platform có quy tắc khác nhau), thao tác cleanup có thể thất bại và chương trình báo lỗi thay vì âm thầm giữ file.

### 6.3. Hai mức kiểm tra, không nên gộp

**Mức 1 — capability probe:** `map` + `force` thành công hay không trên **đúng file**. Chương trình trên kiểm tra cấp độ này.

**Mức 2 — persistence correctness:** dữ liệu có **khôi phục chính xác sau crash/mất nguồn** không, ứng dụng có xử lý các lần ghi bị gián đoạn/torn write không, metadata/directory entries có được persist đúng thứ tự không. Đây là **kiểm thử tích hợp và thiết kế lưu trữ**, không thể khẳng định chỉ từ việc `mapped.getInt(0) == 42` ngay sau khi ghi.

Không tạo hoặc thử sự cố mất nguồn trên môi trường production chỉ để kiểm tra NVM. Sử dụng hệ thống test và quy trình kiểm chứng persistence được kiểm soát.

## 7. Khi không có NVM/DAX: dùng map thông thường đúng mục đích

Nếu nhu cầu chỉ là **đọc/ghi tệp lớn qua memory mapping** chứ không cần đặc tính SYNC của persistent memory, `FileChannel.MapMode.READ_ONLY` hoặc `READ_WRITE` vẫn có giá trị trên các hệ thống tệp thông thường.

Ví dụ **đoạn trong phương thức** khi đã có một `FileChannel channel` phù hợp:

~~~java
MappedByteBuffer regular =
        channel.map(FileChannel.MapMode.READ_WRITE, 0, 4096);

regular.putInt(0, 42);
regular.force();
~~~

Đoạn cần import `java.nio.MappedByteBuffer` và `java.nio.channels.FileChannel`; file cần có vùng hợp lệ và channel có quyền phù hợp.

**Cảnh báo:** `READ_WRITE` map thành công **không cho biết file được đặt trên NVM, không chứng minh DAX, không thay thế `READ_WRITE_SYNC`**. Chỉ sử dụng như fallback **khi yêu cầu ứng dụng cho phép semantics thông thường**; không tự động đổi mode và tuyên bố vẫn đạt thiết kế persistence của NVM.

Đối với ứng dụng có dữ liệu quan trọng, đôi khi **FileChannel.write + force(true)**, cơ sở dữ liệu có transaction hoặc thư viện lưu trữ được thiết kế để phục hồi crash sẽ là phương án thích hợp hơn. Cần chọn theo nhu cầu durability, throughput và tính toàn vẹn dữ liệu thật.

## 8. Lỗi và dấu hiệu dễ chẩn đoán sai

| Dấu hiệu | Điều **có thể** xảy ra | Cần làm gì |
| --- | --- | --- |
| `javac` báo package `jdk.nio.mapmode` không tồn tại | JDK/runtime thiếu module hoặc chưa cấu hình module | Kiểm tra `java --list-modules`, JDK version, `--add-modules` |
| Compile thành công nhưng `map` ném `UnsupportedOperationException` | Mode không được JVM/provider hỗ trợ ở runtime | Xem OS/JDK implementation; kiểm thử đúng platform khác nếu có |
| `map` ném `IOException` hoặc lỗi OS `Operation not supported` | File không hỗ trợ `MAP_SYNC`, thiếu DAX, mount/driver không phù hợp hoặc I/O khác | Kiểm tra filesystem và `S_DAX` của **file cụ thể**, OS logs |
| `FileChannel.open` báo `AccessDeniedException` | Thiếu quyền directory/file hoặc policy bảo mật | Sửa quyền đúng nguyên tắc least privilege |
| `channel.map` báo `NonWritableChannelException` | Mở file chỉ đọc rồi dùng `READ_WRITE_SYNC` | Mở channel READ+WRITE và xác nhận file cho phép ghi |
| XFS/ext4 có mount nhưng SYNC map fail | Chưa bật DAX cho file hoặc backing không hỗ trợ | Đọc `findmnt`, `statx`, kernel/namespace config |
| Có `FS_XFLAG_DAX` nhưng không có `S_DAX` | Advisory flag không tương ứng trạng thái active | Xem mount policy, backing storage, file lifecycle |
| File trên SSD NVMe và `READ_WRITE` map được | Đó là mmap thông thường qua hệ thống tệp | Không suy ra `READ_WRITE_SYNC` sẽ chạy |
| File nằm trong `/tmp` chứ không phải thư mục PMEM | Thử nhầm mount, có thể là `tmpfs` hoặc disk khác | Tạo probe trực tiếp tại filesystem mục tiêu |
| `/dev/dax0.0` được đưa làm directory | Device DAX khác thư mục FS-DAX | Chọn đường đi triển khai đúng loại namespace |
| `force()` chạy không lỗi nhưng dữ liệu bị hỏng sau crash | Không có transaction, thứ tự ghi/metadata chưa đúng | Thiết kế lại crash consistency, dùng checksum/WAL/version |
| VM thấy một loại device ảo | Backing/persistence semantics có thể khác host | Xác minh cam kết lớp virtualization |
| Java `READ_WRITE_SYNC` chạy được trong một folder, fail ở folder khác | Backing mount và active DAX state khác nhau | Thử **đúng đường dẫn** sẽ deploy |
| Ghi mapped buffer rồi cắt/truncate file trong process khác | Mapping có thể trở nên không truy cập được | Không truncate/unlink tùy tiện file đang dùng |

### Một lưu ý về vùng mapped

Javadoc `MappedByteBuffer` cho biết file mapping có thể còn sống đến khi buffer được GC; việc đóng `FileChannel` không có nghĩa vùng mmap lập tức được unmap. Không thay đổi kích thước hoặc nội dung file cùng lúc một cách tùy tiện; file bị truncate có thể khiến truy cập mapped region thất bại, kể cả khi Java code trước đó chạy bình thường.

Các ứng dụng cần quản lý mapping lifecycle chặt có thể xem API **Foreign Function & Memory** đã ổn định từ Java 22, bao gồm `FileChannel.map(MapMode,long,long,Arena)` trên JDK tương ứng. Nhưng **API quản lý vùng nhớ khác không xóa các điều kiện DAX/OS/phần cứng**; bài Java 17+ ở đây tiếp tục dùng `MappedByteBuffer` để bảo đảm khả năng biên dịch được.

## 9. Vì sao `force()` không đồng nghĩa một transaction bền vững?

`READ_WRITE_SYNC` có mục tiêu cho phép hệ thống flush những cache lines liên quan đến persistent memory, khác đường flush file-device truyền thống. Nhưng hãy phân biệt:

- **Durability of modified bytes:** yêu cầu đưa dữ liệu đã thay đổi về storage qua cơ chế phù hợp.
- **Atomicity:** nhiều trường/bytes cập nhật **cùng thành công hoặc cùng thất bại** — không tự được tạo ra bởi `force()`.
- **Consistency:** dữ liệu sau mất nguồn phải còn một cấu trúc hợp lệ — do định dạng file và giao thức cập nhật thiết kế.
- **Concurrency:** nhiều thread/process ghi chung mapped region cần cơ chế đồng bộ phù hợp, lock, ordering và kiểm soát races.
- **Metadata durability:** tạo file, mở rộng file, rename, directory entry và việc đồng bộ metadata còn có những quy tắc riêng của OS/FS.

Ví dụ, bạn có một header gồm `length` và `checksum`. Nếu hai trường được ghi vào memory mapped vùng riêng, crash giữa hai lần ghi có thể tạo header không nhất quán. Chỉ gọi một lần `force()` ở cuối không làm biến hai phép ghi thành atomic commit.

**Biện pháp cấp ứng dụng:** dùng định dạng có version và checksum; áp dụng transactional update protocol hoặc WAL/dual-slot/commit markers, lập thứ tự ghi và flush rõ ràng, rồi kiểm thử phục hồi. Khi xử lý dữ liệu quan trọng, kiểm tra thêm power-fail domain và chính sách firmware/hardware thay vì tin một nhãn “persistent”.

## 10. Checklist vận hành trước khi chọn `READ_WRITE_SYNC`

- [ ] Đã xác minh **mục tiêu thật sự cần NVM SYNC mapping** chứ không chỉ cần mmap bình thường.
- [ ] JVM/JDK hiện hành có `jdk.nio.mapmode` và `ExtendedMapMode`; không dựa vào incubator cũ.
- [ ] Hệ điều hành/kernel/JVM implementation hỗ trợ mode, đặc biệt đường `MAP_SYNC`/`MAP_SHARED_VALIDATE` trên Linux.
- [ ] Thiết bị/namespace đáp ứng direct access và persistence requirements; không coi NVMe SSD thông thường là NVDIMM.
- [ ] File nằm trên **FS-DAX** phù hợp nếu dùng regular-file mapping; không nhầm với device DAX.
- [ ] Đã kiểm tra filesystem, mount và đường dẫn bằng `findmnt`/`lsblk` hoặc công cụ phù hợp.
- [ ] Đã xác nhận **S_DAX/STATX_ATTR_DAX của file**; không chỉ nhìn tên ext4/XFS hoặc flag `FS_XFLAG_DAX`.
- [ ] Tệp tạm được tạo trong đúng thư mục, có quyền đọc/ghi, dung lượng đủ và size hợp lệ.
- [ ] `FileChannel.map(READ_WRITE_SYNC,...)` thực sự thành công; không coi compile PASS là runtime PASS.
- [ ] Có mã xử lý `UnsupportedOperationException`, `IOException` và lỗi quyền/metadata.
- [ ] Không tự fallback thành `READ_WRITE` rồi vẫn công bố durability NVM.
- [ ] Gọi `force()` đúng vùng dữ liệu khi cần persistence; xử lý lỗi flush và hệ thống lưu trữ.
- [ ] Có protocol crash-consistency, checksum/transaction hoặc cơ chế phục hồi phù hợp.
- [ ] Có test sau restart/crash trong môi trường kiểm soát, không làm rủi ro dữ liệu production.
- [ ] Có quyết định rõ cho Windows/macOS/VM/container: khả năng thực tế hay fallback chủ đích.
- [ ] Ghi log JDK version, OS/kernel, filesystem, backing device, `S_DAX` và kết quả probe, **không log secrets**.

## 11. Bài tập tự luyện

1. Nêu ba lý do vì sao một ổ NVMe SSD có dữ liệu không mất nguồn vẫn chưa đủ để Java `READ_WRITE_SYNC` hoạt động.
2. Phân biệt **FS-DAX** với **Device DAX**. Ví dụ `Files.createTempFile(dir,...)` yêu cầu loại nào?
3. Xem `ExtendedMapMode` trên JDK bạn dùng. Hằng `READ_ONLY_SYNC` và `READ_WRITE_SYNC` nằm trong module nào? `FileChannel.MapMode.READ_WRITE` khác gì?
4. Chạy `java --list-modules` và biên dịch `NvmCapabilityProbe.java` với `--release 17 --add-modules jdk.nio.mapmode`. Nếu compile được, bạn đã chứng minh được gì? Chưa chứng minh được gì?
5. Chạy probe trên một thư mục filesystem thông thường và ghi nhận lỗi. Giải thích vì sao không được suy ra “toàn bộ phần cứng không hỗ trợ PMEM” từ một đường dẫn.
6. Trên server Linux được phép quản trị, đọc `findmnt -T`, `lsblk` và trạng thái `S_DAX` bằng `statx`. Vì sao `FS_XFLAG_DAX` chưa đủ để khẳng định file đang ở DAX mode?
7. Phân biệt ba chính sách `dax=inode`, `dax=always` và `dax=never`. Vì sao không nên sửa mount option tùy tiện trên máy đang vận hành?
8. Nêu nguyên nhân khiến VM hoặc container không thể dùng SYNC mapping dù host có PMEM.
9. Trong trường hợp `map` thành công, giải thích vì sao `mapped.getInt(0)==42` ngay sau ghi **không đủ** để chứng minh phục hồi dữ liệu đúng sau mất nguồn.
10. Thiết kế một thử nghiệm có chủ đích dùng file mới, kiểm tra `READ_WRITE_SYNC`, `force()`, unmap/lifecycle và khôi phục sau restart trên môi trường test.
11. Giả sử bạn phải chạy cùng ứng dụng trên Linux và Windows. Nêu cách báo rõ “NVM feature unavailable”, xử lý fallback nếu yêu cầu nghiệp vụ cho phép, và không báo sai trạng thái capability.
12. Một ứng dụng lưu index + payload vào PMEM. Hãy vẽ thứ tự ghi/flush/commit để tránh việc chỉ mục trỏ tới dữ liệu chưa hợp lệ sau crash.

## 12. Tài liệu chính thức hiện hành

- [Oracle JDK 25 — ExtendedMapMode](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.nio.mapmode/jdk/nio/mapmode/ExtendedMapMode.html): định nghĩa hai SYNC modes, khả năng ném `UnsupportedOperationException`, ghi chú `MAP_SYNC`/`MAP_SHARED_VALIDATE` trên Linux và cache-line writeback.
- [Oracle JDK 25 — FileChannel.map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long)): điều kiện open mode, size, exceptions và map modes.
- [Oracle JDK 25 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html): `force`, phạm vi mapped, ảnh hưởng khi tệp bị truncate.
- [Linux kernel — Direct Access for files](https://docs.kernel.org/filesystems/dax.html): danh sách các đường hỗ trợ DAX hiện hành, `FS_XFLAG_DAX`, `S_DAX`, `STATX_ATTR_DAX` và `dax=inode/always/never`.
- [Linux NVDIMM docs — FS Mount Options](https://nvdimm.docs.kernel.org/fs_mount_options.html): cách phân biệt flag yêu cầu và trạng thái DAX của regular file.
- [Linux NVDIMM docs — Persistent Memory](https://nvdimm.docs.kernel.org/): phân biệt filesystem DAX, device DAX và persistent memory namespaces.
- [OpenJDK JEP 352 — Non-Volatile Mapped Byte Buffers](https://openjdk.org/jeps/352): bối cảnh đưa khả năng ánh xạ bộ nhớ không bay hơi vào JDK 14.

**Ghi nhớ:** để Java ánh xạ **NVM theo `READ_WRITE_SYNC`**, **API đúng là điều kiện cần nhưng chưa đủ**. Phải có **thiết bị/backing phù hợp, kernel và OS hỗ trợ, filesystem/file thật sự dùng DAX, quyền và channel đúng**, rồi **thử map + force trên chính đường dẫn triển khai**. Nếu một mắt xích không đáp ứng, báo rõ “không khả dụng” và chỉ dùng fallback khi hợp đồng dữ liệu cho phép.