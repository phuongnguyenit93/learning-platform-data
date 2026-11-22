# Ảnh hưởng của cache hệ điều hành khi benchmark Java I/O

Khi đo hiệu năng đọc/ghi tệp lớn bằng Java, kết quả có thể chênh lệch nhiều lần dù **không thay đổi một dòng code**. Nguyên nhân thường không nằm riêng ở `FileInputStream`, `BufferedInputStream`, `FileChannel` hay `MappedByteBuffer`, mà còn ở **page cache của hệ điều hành**, readahead, cơ chế write-back, cache của thiết bị lưu trữ, hoạt động của các tiến trình khác và trạng thái bộ nhớ tại thời điểm đo.

Ví dụ, đọc một tệp 2 GiB từ SSD ở lần đầu có thể phụ thuộc lượng dữ liệu phải thực sự tải từ thiết bị. Nếu dữ liệu đã nằm trong RAM của hệ điều hành, lượt đọc sau chủ yếu truyền dữ liệu từ page cache về ứng dụng. So sánh hai lượt này rồi tuyên bố “API A nhanh hơn API B” là sai nếu chúng không được đo trong **điều kiện cache tương đương**.

Bài học này tập trung vào cách cache hệ điều hành làm sai lệch benchmark, phân biệt **cold-cache** và **warm-cache**, các đặc điểm của đo đọc/ghi, cách thiết kế thử nghiệm Java I/O và cách diễn giải kết quả mà không nhầm tốc độ truy cập RAM với thông lượng thiết bị.

## 1. Page cache nằm ở đâu trong đường đi I/O?

Trên hệ điều hành thông thường, hoạt động đọc một tệp nằm trên hệ thống tệp có thể đi qua các tầng:

```text
Java application
   |
   | FileInputStream / FileChannel.read / Files.read...
   v
Kernel filesystem interface
   |
   v
OS page cache (RAM dùng cache các trang dữ liệu tệp)
   |                         \
   | cache hit                 \ cache miss
   |                            v
   |                      File system + block I/O
   |                            |
   |                            v
   |                      Storage device (SSD/HDD)
   |                            |
   +<---------------------------+
   |
   v
ByteBuffer / byte[] / ứng dụng
```

Đây là mô hình **khái niệm**, không phải đường đi cố định của mọi hệ thống tệp, OS hoặc provider. Hệ điều hành có thể cache metadata, thực hiện readahead, copy hoặc map trang, gom nhiều yêu cầu I/O; thiết bị SSD/HDD cũng có cache riêng.

**Page cache** là RAM mà hệ điều hành tận dụng để lưu những trang dữ liệu của file. Khi một thao tác đọc cần những trang đã có trong cache (*cache hit*), kernel có thể phục vụ mà không phải đọc lại toàn bộ dữ liệu từ thiết bị lưu trữ. Khi chưa có trang phù hợp (*cache miss*), hệ thống phải lấy dữ liệu từ các tầng dưới, thường chậm hơn và biến động hơn.

Hai khái niệm cần phân biệt:

- **Cache của ứng dụng Java:** `byte[]`, `ByteBuffer`, `BufferedInputStream`, cache tự xây dựng hoặc cache của thư viện. Dữ liệu sống theo quy tắc của JVM/ứng dụng.
- **Cache của hệ điều hành:** thường do kernel quản lý và chia sẻ giữa các tiến trình. Đóng `FileChannel` hoặc tạo lại đối tượng Java không có nghĩa kernel đã bỏ các trang tệp tương ứng khỏi cache.

Đọc xong một file rồi đóng stream, mở một stream mới tới cùng file vẫn có thể **đọc từ cache kernel**. Vì thế việc “tạo `FileChannel` mới cho mỗi lượt benchmark” không phải cách bảo đảm mọi lượt bắt đầu trong trạng thái cold.

## 2. Cold cache và warm cache là hai bài toán khác nhau

| Tình huống | Ý nghĩa thực tế | Đo được điều gì? |
| --- | --- | --- |
| **Cold-ish read** | Phần lớn dữ liệu chưa nằm trong page cache cần thiết | Đọc có thể chịu chi phí thiết bị, metadata và readahead |
| **Warm read** | Phần lớn dữ liệu đã có trong page cache | Chi phí kernel/cache, sao chép dữ liệu, xử lý Java, băng thông bộ nhớ |
| **Mixed read** | Một số trang cache hit, một số phải tải lại | Hỗn hợp có thể khác nhau giữa từng lượt |
| **Working set lớn hơn RAM cache khả dụng** | Có thể phát sinh eviction/cache thrashing | Bị chi phối bởi luồng I/O, lượng RAM và tác vụ cạnh tranh |
| **Nhiều tiến trình đọc cùng tệp** | Một tiến trình làm cache nóng cho tiến trình khác | Phụ thuộc hoạt động hệ thống chung, không chỉ một JVM |

Từ “cold” cần định nghĩa **theo phạm vi dữ liệu và trạng thái hệ thống**. Một file chưa từng được mở bởi chính chương trình chưa chắc cold: antivirus, trình index, tiến trình khác hoặc lệnh tạo file trước đó có thể đã đưa các trang của nó vào cache.

Ngược lại, “warm” không có nghĩa mọi byte luôn nằm trong RAM. Kernel có thể thu hồi trang bất cứ lúc nào để cấp RAM cho công việc khác. Nếu file lớn hoặc máy đang chịu memory pressure, lần đọc thứ hai vẫn có thể gặp nhiều cache miss.

**Không được lấy một phép đo cold và một phép đo warm làm hai mẫu tương đương để so sánh thư viện hoặc API.** Nếu sản phẩm đọc cùng file nhiều lần, warm-cache performance có thể là chỉ tiêu đúng. Nếu sản phẩm quét tệp mới sau khi khởi động hoặc đọc các tập dữ liệu vượt RAM, cần kiểm tra cold/mixed-cache và thông lượng lưu trữ thực tế.

## 3. Vì sao lần đọc đầu tiên chưa chắc là cold?

Một quy trình nghe có vẻ hợp lý:

```java
Files.write(file, testData);
long first = timeRead(file);
long second = timeRead(file);
```

nhưng lại không tạo ra kết quả **cold versus warm** đúng nghĩa. Khi `Files.write()` vừa ghi `testData`, nhiều hệ điều hành giữ các trang đã ghi trong page cache. Ngay cả khi `first` là lần đầu ứng dụng **đọc**, dữ liệu có thể **đã warm do thao tác ghi**.

Các lý do khác khiến lần đọc đầu không cold:

1. File đã được tạo, copy hoặc kiểm tra checksum ngay trước benchmark.
2. Một tiến trình khác vừa đọc file, đưa dữ liệu vào cache chung.
3. OS có cơ chế readahead: trong một lần đọc tuần tự, các trang **ở đoạn sau** có thể được tải sớm trước khi code gọi `read()` tới vị trí đó.
4. Filesystem cache metadata/inode/dentry hoặc cache của storage device làm ảnh hưởng thời gian ngay cả khi data page chưa warm.
5. Benchmark framework đã chạy một số vòng warmup, vô tình “làm nóng” dữ liệu cần dùng cho bài đo cold.
6. Một container hoặc JVM mới dùng chung kernel với các workload trước đó; khởi động container mới **không đồng nghĩa xóa cache kernel**.

Do đó, kết quả đo ban đầu chỉ nên được gọi là **first measured pass**, trừ khi có bằng chứng rằng working set bắt đầu ở điều kiện cache đã được kiểm soát.

## 4. BufferedInputStream không phải page cache

`BufferedInputStream` giữ một bộ đệm ở phía Java, giúp giảm số lần gọi xuống `InputStream` bên dưới khi ứng dụng đọc từng byte hoặc các đoạn nhỏ. `FileChannel.read(ByteBuffer)` có thể đọc một khối lớn trong một lời gọi. Nhưng **cả hai vẫn thường được phục vụ qua page cache của kernel** khi đọc file trên filesystem mặc định.

Ví dụ:

```java
try (InputStream input = new BufferedInputStream(
        Files.newInputStream(file), 64 * 1024)) {
    int value;
    while ((value = input.read()) != -1) {
        consume(value); // Hàm nghiệp vụ minh họa.
    }
}
```

Đoạn này **không phải chương trình độc lập**: cần khai báo `file` và hàm `consume`, import `java.io.*`, `java.nio.file.*` cùng xử lý `IOException`. Nó minh họa buffer tầng ứng dụng, không chứng minh rằng kernel sẽ không cache file.

Thêm một tầng buffer **không luôn làm chương trình nhanh hơn**. Nếu ứng dụng vốn đã đọc mảng `byte[65536]` theo khối, bọc thêm `BufferedInputStream` có thể không mang lợi ích tương xứng. Nếu ứng dụng gọi `read()` từng byte, buffer có thể giảm overhead. Để kết luận cần đo với **kích thước buffer, trạng thái page cache, workload và thuật toán xử lý tương đương**.

### Direct ByteBuffer không tự bypass cache hệ điều hành

`ByteBuffer.allocateDirect()` tạo một buffer trực tiếp ở vùng bộ nhớ ngoài heap; nó có thể giảm chi phí copy giữa một số đường đi I/O native và JVM. Tuy nhiên **direct buffer không đồng nghĩa với `O_DIRECT` của Linux**, không bảo đảm bỏ qua OS page cache và cũng không bảo đảm “zero-copy” trong mọi tình huống.

So sánh heap `ByteBuffer` và direct `ByteBuffer` cần tách rõ chi phí cấp phát, reuse, số lần copy, mức cache hit và chi phí đọc trên thiết bị. Nếu không kiểm soát page cache, kết luận “direct nhanh hơn ổ đĩa” dễ là phép đo về cache/bộ nhớ thay vì thiết bị.

## 5. Sequential read, random read và read-ahead

Hệ điều hành thường tối ưu việc đọc tuần tự bằng **readahead**: khi phát hiện mẫu truy cập phù hợp, kernel có thể đọc trước những block chưa được yêu cầu. Vì thế hai benchmark đọc cùng dung lượng nhưng thứ tự khác nhau có thể cho kết quả rất khác:

- **Sequential scan:** Đi từ đầu tới cuối file, kích thước khối tương đối lớn, locality cao. Readahead có thể giúp che giấu độ trễ thiết bị.
- **Random access:** Nhảy giữa các offset phân bố rộng, locality thấp. Có thể làm giảm hiệu quả readahead và tạo nhiều I/O nhỏ.
- **Repeated hot small region:** Liên tục đọc vài MiB đầu của một file vài GiB. Dữ liệu có thể hoàn toàn nằm trong RAM ngay cả khi tổng file lớn hơn RAM.
- **Many-file metadata walk:** Đọc thuộc tính và mở hàng nghìn tệp nhỏ. Cache metadata, đường dẫn và số syscall có thể quan trọng hơn throughput dữ liệu.
- **Mixed read/write:** Workload thật có ghi, đọc lại, cạnh tranh RAM và background writeback; không thể suy ra trực tiếp từ một sequential read-only benchmark.

Nếu muốn kiểm tra hành vi I/O cho file lớn, hãy định nghĩa **working set** là các byte thực sự được chạm tới trong cửa sổ đo; không chỉ nói file trên đĩa dài bao nhiêu. Một file 100 GiB mà bài đo chỉ chạm 4 MiB có working set truy cập khác hoàn toàn với quét đủ 100 GiB.

Khi đọc ngẫu nhiên, cũng cần cố định seed/nguyên tắc sinh offset để hai chiến lược đọc gặp cùng khối dữ liệu. Nếu mỗi lần chạy dùng offset tùy ý khác nhau, các mức cache hit không thể so trực tiếp.

## 6. Write-back cache: ghi “xong” không đồng nghĩa dữ liệu đã bền vững

Khi `FileChannel.write()` hoặc `Files.write()` trả về thành công, nhiều hệ thống tệp đã chấp nhận dữ liệu vào các buffer/cache của hệ điều hành. Điều đó **không chứng minh các byte đã tới bộ nhớ lưu trữ bền vững**. Kernel có thể **write-back** các trang đã thay đổi (*dirty pages*) xuống thiết bị ở thời điểm sau.

Vì vậy một benchmark ghi đơn giản có thể đo chủ yếu tốc độ copy byte vào page cache, rồi kết thúc trước khi kernel hoàn tất ghi thiết bị. Nếu báo kết quả đó là “SSD write throughput” sẽ dễ phóng đại.

| Kiểu đo | Điều đang đo | Điều chưa chắc đo |
| --- | --- | --- |
| `write()` đến khi hết buffer | Thời gian ứng dụng được OS chấp nhận byte | Dữ liệu đã ổn định trên thiết bị |
| `Files.write(...)` rồi đóng stream | Hoàn thành đường ghi ở mức API và close | Độ bền qua mất điện theo mọi filesystem |
| `FileChannel.force(false)` | Yêu cầu đồng bộ nội dung (và metadata cần để lấy lại nội dung) theo hợp đồng API | Không trực tiếp báo cache đã bị xóa |
| `FileChannel.force(true)` | Yêu cầu đồng bộ nội dung và metadata liên quan | Không tự làm file cold cho lần đọc sau |
| `StandardOpenOption.SYNC/DSYNC` | Thay chính sách đồng bộ lúc mở file để ghi | Không miễn phí về latency hoặc tương đương trong mọi filesystem |

`FileChannel.force(true)` là yêu cầu **đẩy cập nhật về thiết bị theo phạm vi cam kết của API**, không phải API xóa page cache. Trên các loại storage/provider khác nhau, bảo đảm thực tế và chi phí có thể khác nhau. Việc force không hứa đồng bộ mọi thay đổi thư mục, rename hoặc thiết bị trong mọi tình huống mất điện.

Để benchmark **durable writes**, hãy mô tả rõ có tính thời gian của `force()`/close, có dùng `SYNC/DSYNC`, file đã tồn tại hay mới tạo, số byte và cách xử lý lỗi hay không. Để benchmark **write acceptance** của API, có thể không force nhưng phải gọi đúng tên chỉ số đó.

## 7. MappedByteBuffer và file memory mapping cũng chịu ảnh hưởng cache

`FileChannel.map()` có thể ánh xạ vùng tệp vào không gian địa chỉ của tiến trình; đọc từ `MappedByteBuffer` có thể dẫn tới **page fault** khi trang tương ứng chưa sẵn có. Những truy cập sau có thể sử dụng các trang đã được ánh xạ/cached.

Những cách đo sai thường thấy:

1. Map file ở ngoài timer, sau đó đo đọc trang trong timer cho chiến lược memory-mapped; nhưng với `FileChannel.read()` lại đo cả thời gian mở file và cấp phát buffer.
2. Một bài benchmark gọi `mapped.load()` trước khi đo, bài kia không warmup dữ liệu tương đương.
3. Đo một lượt mapping cold, lượt mapping khác warm mà không báo state.
4. Xem `MappedByteBuffer.isLoaded()` là công cụ xác nhận chính xác rằng **mọi trang luôn nằm trong RAM**. API chỉ mang tính chỉ báo; hệ điều hành có thể thay đổi trạng thái sau kiểm tra.
5. Gọi `mapped.force()` và cho rằng map đã bị loại khỏi cache. `force()` của mapped buffer là thao tác hướng về **đồng bộ thay đổi**, không phải eviction.

Mapping có các đặc điểm riêng: page faults, độ hạt trang, truy cập ngẫu nhiên và chi phí quản lý vùng ánh xạ. Benchmark cần đo cả thời điểm mapping nếu workload thực tế trả giá đó và so sánh trong tình trạng cache ngang nhau.

**Mapping không phải zero-cost I/O.** Với file khổng lồ, còn cần cân nhắc kích thước vùng map, giới hạn địa chỉ, bộ nhớ khả dụng, vòng đời mapping và việc file bị thay đổi/thu ngắn trong lúc đang truy cập.

## 8. Ví dụ Java 17+ hoàn chỉnh: đo nhiều lượt đọc nhưng không gọi lượt đầu là cold

Ví dụ sau:

- Tạo tệp tạm **8 MiB** chứa dữ liệu byte xác định (không đụng tới tệp người dùng).
- Ghi bằng `FileChannel`, gọi `force(true)` để minh họa khác biệt giữa sync nội dung và cache eviction.
- Đọc tuần tự cùng tệp **bốn lần**, mỗi lần mở `FileChannel` mới và đọc qua một `ByteBuffer` 64 KiB.
- Đo thời gian bằng `System.nanoTime()`, tính throughput theo MiB/s và in lên **stderr** vì số đo phụ thuộc máy.
- Kiểm tra tổng byte và checksum của các lượt đọc rồi in kết quả **cố định trên stdout**.

**Đây là demo quan sát warm-up/cache, không phải phép thử cold-cache có kiểm soát và không phải bằng chứng API I/O nào nhanh hơn.**

Tạo file **`OsCacheBenchmarkDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class OsCacheBenchmarkDemo {
    private static final int BLOCK = 64 * 1024;
    private static final int BLOCKS = 128; // 8 MiB.
    private static final int PASSES = 4;

    private OsCacheBenchmarkDemo() {}

    private record Result(long bytes, long checksum, long elapsedNs) {}

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("os-cache-benchmark-", ".bin");
        try {
            generate(path);

            Result[] results = new Result[PASSES];
            for (int i = 0; i < PASSES; i++) {
                results[i] = readAndMeasure(path);
                double seconds = results[i].elapsedNs() / 1_000_000_000.0;
                double mibPerSecond =
                        (results[i].bytes() / (1024.0 * 1024.0))
                        / Math.max(seconds, 1e-9);
                System.err.printf(
                        "pass=%d elapsed=%.3f ms throughput=%.1f MiB/s%n",
                        i + 1, results[i].elapsedNs() / 1_000_000.0,
                        mibPerSecond);
            }

            boolean sameBytes = true;
            boolean sameChecksum = true;
            for (Result result : results) {
                sameBytes &= result.bytes() == BLOCKS * (long) BLOCK;
                sameChecksum &=
                        result.checksum() == results[0].checksum();
            }

            System.out.println("file bytes=" + Files.size(path));
            System.out.println("all passes have full size=" + sameBytes);
            System.out.println("all passes have same checksum="
                    + sameChecksum);
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static void generate(Path path) throws IOException {
        byte[] bytes = new byte[BLOCK];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) (i & 0xff);
        }

        try (FileChannel out = FileChannel.open(path,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer source = ByteBuffer.wrap(bytes);
            for (int block = 0; block < BLOCKS; block++) {
                source.rewind();
                while (source.hasRemaining()) {
                    if (out.write(source) <= 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
            out.force(true); // Sync request, KHÔNG evict page cache.
        }
    }

    private static Result readAndMeasure(Path path) throws IOException {
        ByteBuffer data = ByteBuffer.allocate(BLOCK);
        try (FileChannel in = FileChannel.open(
                path, StandardOpenOption.READ)) {
            long bytes = 0;
            long checksum = 0;
            long started = System.nanoTime();

            while (true) {
                data.clear();
                int n = in.read(data);
                if (n < 0) {
                    break;
                }
                if (n == 0) {
                    throw new IOException("No read progress");
                }

                bytes += n;
                data.flip();
                while (data.hasRemaining()) {
                    checksum += data.get() & 0xff;
                }
            }

            return new Result(
                    bytes, checksum, System.nanoTime() - started);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac OsCacheBenchmarkDemo.java
java OsCacheBenchmarkDemo
```

**Stdout** khi tạo và đọc tệp thành công:

```text
file bytes=8388608
all passes have full size=true
all passes have same checksum=true
```

**Stderr** sẽ có bốn dòng `pass=1` đến `pass=4`, mỗi dòng chứa milliseconds và throughput tính từ số đo thực tế; **không có giá trị thời gian hoặc MiB/s cố định**. Khi chạy từ terminal, stderr có thể hiển thị xen kẽ stdout.

### Demo chứng minh điều gì và không chứng minh điều gì?

1. `Files.createTempFile()` cấp tệp mới; `generate()` ghi đúng 128 block × 65.536 byte = 8.388.608 byte. Dữ liệu mỗi block có pattern từ 0 đến 255.
2. `out.force(true)` yêu cầu đồng bộ trước khi đo đọc; tuy nhiên dữ liệu vừa ghi **có thể vẫn ở page cache**. Lượt `pass=1` **không được gọi là cold**.
3. Mỗi `readAndMeasure()` mở channel mới nhưng không yêu cầu OS loại các trang vừa đọc khỏi cache. Vì vậy nhiều lượt có thể được phục vụ từ RAM.
4. Vòng `read()` đọc khối tối đa 64 KiB; checksum khiến nội dung thực sự được tiêu thụ, tránh một phép đo chỉ mở file rồi đóng.
5. Thời gian bao gồm `FileChannel.read()`, các thao tác `ByteBuffer` và phép cộng checksum, nhưng **không bao gồm** khởi tạo buffer, mở/đóng channel hay thời gian tạo tệp. Như vậy nó **không đo riêng throughput thiết bị**.
6. Các dòng stdout xác minh mọi pass đọc đủ file và cùng checksum. Dữ liệu đọc giống nhau không cho biết mỗi pass hit page cache bao nhiêu phần trăm.

Nếu muốn so sánh các API khác, phải áp dụng cùng cách tạo dữ liệu, trạng thái cache, lượng byte, mức xác minh, phần timer được bao gồm và số lần lặp. Đo thời gian dài hơn, báo median/p95/phân phối và quan sát disk I/O sẽ hữu ích hơn một lượt đo 8 MiB.

## 9. Thiết kế benchmark công bằng với trạng thái cache

### Bước 1: Xác định câu hỏi muốn trả lời

Hai mục tiêu thường khác nhau:

**A. Người dùng thực tế đọc đi đọc lại một tập file đang nằm trong cache:** Hãy đo warm-cache workload vì nó phản ánh thực tế. Không cần cố gắng loại page cache nếu dịch vụ sản xuất luôn tận dụng cache.

**B. Hệ thống phải xử lý nhiều file mới/lớn, vượt bộ nhớ và gây disk I/O:** Hãy xây dựng dữ liệu và chu kỳ truy cập sao cho đo được cold/mixed cache tương ứng, giám sát các chỉ số storage bên ngoài JVM và báo rõ các giới hạn tái lập.

Không nên đặt tiêu đề “đo hiệu năng ổ đĩa” khi bài đo chỉ lặp đọc cùng một buffer nhỏ từ RAM.

### Bước 2: Kiểm soát working set

Ghi lại:

- Tổng kích thước tập dữ liệu cần chạm tới (không chỉ tên/kích thước một file).
- RAM vật lý, RAM sẵn có, memory pressure và cache capacity trong thời gian đo.
- Kiểu tệp và filesystem: local SSD/HDD, network share, tmpfs, filesystem ảo; nếu đo trên **tmpfs/RAM disk** thì dữ liệu vốn ở RAM, không thể suy diễn về SSD/HDD.
- Sequential hay random, kích thước block, số luồng, mức song song, khoảng cách giữa các pass.
- Có file nào vừa được tạo/copy/ghi/kiểm checksum làm warm cache trước khi đo không.
- Có workload khác sử dụng RAM hoặc disk cùng lúc không.

Một tập dữ liệu **lớn hơn RAM** làm khả năng hit page cache giảm trong nhiều tình huống, nhưng không bảo đảm hoàn toàn cold. OS vẫn có thể cache các vùng được chạm lặp lại, cache metadata hoặc tối ưu hóa đường đi truy cập. Không mô tả quy tắc “file > RAM ⇒ chắc chắn không có cache” như một định luật.

### Bước 3: Warm-up đúng mục đích

Đối với benchmark warm-cache:

1. Chạy đủ lượt ban đầu để JIT/JVM, class loading và dữ liệu I/O có cơ hội ổn định.
2. Tách số đo warm-up khỏi các số đo chính.
3. Chạy nhiều lượt chính, tính phân phối, kiểm tra checksum/số byte.
4. Nếu so sánh A/B, thay đổi thứ tự thử nghiệm (ví dụ ABBA hoặc randomized) nhằm hạn chế việc luôn cho B hưởng cache của A.

Đối với **cold-cache**: warm-up Java code có thể cần thiết, nhưng không được dùng warm-up đọc chính tập file cần giữ cold cho lần đo. Có thể warm JIT bằng một tập dữ liệu khác tương đương mà không chạm vào tập đo chính. Ngay cả vậy, cache dùng chung và hoạt động bên ngoài JVM vẫn phải được quan sát.

### Bước 4: Phân biệt phép đo Java và thiết bị lưu trữ

Bên cạnh `System.nanoTime()`, hãy thu thập số liệu cấp OS phù hợp:

| Nhóm chỉ số | Vì sao hữu ích |
| --- | --- |
| Tổng byte ứng dụng đọc/ghi | Xác minh khối lượng công việc tương đương |
| Disk I/O bytes thực tế, số request, queue và latency | Phân biệt throughput thiết bị với phục vụ từ page cache |
| Page faults / major faults (khi liên quan) | Gợi ý hành vi memory mapping và truy cập trang |
| CPU user/system, context switches | Thấy benchmark bị giới hạn bởi Java parsing/copy/syscalls |
| Page cache/reclaim/memory pressure | Giải thích vì sao các pass có mức cache hit khác nhau |
| Dirty pages và writeback activity | Phân biệt ghi vào RAM với ghi ra thiết bị |
| Per-process và toàn hệ thống I/O | Tránh quy nhầm disk I/O của tiến trình khác cho benchmark |

Các số liệu này không phải lúc nào cũng trực tiếp ánh xạ từng page cache hit của Java sang một con số đơn giản. Trên Linux có thể sử dụng công cụ giám sát hệ thống như `iostat`, `pidstat`, `vmstat`, `perf` (nếu sẵn có và có quyền); trên Windows/macOS sử dụng công cụ đo tương ứng. Hãy ghi rõ công cụ, phiên bản OS và cách thu thập.

## 10. Có thể “xóa page cache” để đo cold bằng Java không?

**Java chuẩn không cung cấp một API portable để xóa page cache của hệ điều hành cho một file hoặc toàn máy.** `FileChannel.close()`, `FileChannel.force()`, `Files.delete()`, `MappedByteBuffer.force()` hay `ByteBuffer.allocateDirect()` không tương đương thao tác xóa cache kernel.

Một số hệ điều hành có công cụ/hint native để điều chỉnh page cache, nhưng chúng:

- Khác nhau giữa Linux, Windows, macOS và các filesystem.
- Có thể yêu cầu quyền quản trị hoặc hỗ trợ ở cấp kernel/filesystem.
- Có thể tác động tới toàn hệ thống, ảnh hưởng tiến trình khác, làm thay đổi điều kiện đo và gây gián đoạn không mong muốn.
- Không đảm bảo trạng thái cold tuyệt đối vì còn cache của thiết bị, metadata, readahead hoặc workload khác.

**Không dùng thao tác thô bạo xóa page cache toàn máy trên môi trường dùng chung hoặc production chỉ để tạo con số benchmark.** Nếu cần thử nghiệm cold có tính kiểm soát, sử dụng máy thử nghiệm riêng, dữ liệu/thiết bị được quản lý, quy trình thiết lập và giám sát được ghi chép; thao tác native phải do người có trách nhiệm hệ thống phê duyệt.

Một phương án giảm cache reuse là thử nghiệm với một tập file đủ lớn, được đọc theo mẫu đã thiết kế, đổi thứ tự dữ liệu và quan sát disk I/O thực. Dù vậy hãy gọi đây là **cache-mitigated/mixed-cache test** nếu chưa xác nhận điều kiện cold.

## 11. Những sai lệch benchmark Java thường đi cùng page cache

Page cache không phải tác nhân duy nhất. Khi số liệu thay đổi mạnh, kiểm tra thêm:

| Sai lệch | Ví dụ | Cách giảm |
| --- | --- | --- |
| **JIT warmup** | Lần đầu có class loading/JIT compilation | Chạy warm-up code tách khỏi tập dữ liệu cold nếu cần |
| **GC/heap pressure** | Dùng `Files.readAllBytes()` làm tệp rất lớn thành array | Chọn khối đọc phù hợp, ghi nhận GC/heap và giữ bài test công bằng |
| **Buffer allocation** | A cấp phát `allocateDirect()` trong timer, B reuse heap buffer ngoài timer | Định nghĩa có/không tính cấp phát giống nhau |
| **Checksum/parsing** | Mỗi byte được xử lý bằng CPU, che mất khác biệt I/O | Đo cả tổng workload và đường đọc tối giản trong những phép thử riêng |
| **JVM/OS background load** | Antivirus, indexing, cron backup, build/test khác | Cách ly thời gian thử, ghi nhận nhiễu |
| **Thermal/power behavior** | CPU/SSD throttling, hiệu năng laptop theo chế độ pin | Ghi nhận power state, nhiệt độ và điều kiện ổn định |
| **File allocation/compression** | Sparse file, compression filesystem, deduplication, zero-filled pattern | Dùng dữ liệu phản ánh thực tế; ghi đặc điểm filesystem |
| **Disk cache/device cache** | Lần đầu đi qua cache của bộ điều khiển SSD | Không xem page cache là tầng cache duy nhất |
| **Small sample** | Đọc 100 KiB và suy tốc độ GiB/s | Tăng khối lượng đo, báo variance và sai số |
| **Measurement scope** | A tính `open()`, B không tính | Đặt timer cùng ranh giới |
| **Contention** | Nhiều benchmark thread cùng đọc file | Kiểm soát concurrency và băng thông chung |
| **Trộn state A/B** | Chạy A trước để warm file rồi B sau | Đảo thứ tự hoặc đưa cả hai vào các state tương đương |

Với microbenchmark thao tác I/O hoặc buffer, có thể dùng **JMH** để quản lý warm-up/measurement/fork và tránh nhiều lỗi liên quan JIT. Tuy nhiên **JMH không tự reset page cache hay biến benchmark storage thành cold-cache test**; cần cấu hình môi trường/working set ngoài harness.

### Đừng dùng tốc độ vượt ổ đĩa làm bằng chứng “benchmark lỗi”

Nếu workload hoàn toàn warm, thông lượng quan sát được có thể vượt nhiều lần tốc độ đọc danh nghĩa của SSD vì phần lớn byte đang đến từ RAM. Điều đó **có thể đúng đối với warm-cache benchmark**. Lỗi là diễn giải kết quả thành băng thông vật lý của SSD hoặc dùng nó làm dự đoán cho ứng dụng thường xuyên đọc cold data.

### Throughput và latency không thay thế nhau

Thông lượng có thể tính theo `MiB/s = bytes / (1024×1024) / seconds`. Nhưng còn cần latency per operation và percentile khi workload gồm nhiều request nhỏ. Một hệ thống có throughput cao khi đọc file tuần tự vẫn có thể có p99 rất tệ do major page fault, queue dài hoặc writeback gây contention.

## 12. Ví dụ thiết kế phép thử A/B có chú giải

Giả sử muốn so sánh `Files.newInputStream()` + byte array với `FileChannel.read(ByteBuffer)`:

**Không công bằng:**

```text
A: đọc file X ngay sau khi máy khởi động
B: đọc lại file X sau A
Kết luận: B luôn nhanh hơn A.
```

A gặp nhiều miss hơn B và có thể gánh thêm khởi tạo JIT. Dữ liệu không chứng minh API B tốt hơn.

**Thiết kế hợp lý hơn:**

1. Mô tả câu hỏi: tốc độ đọc tuần tự **warm-cache** hay cold/mixed-cache? Chỉ công bố kết quả cho một điều kiện được kiểm soát.
2. Chọn cùng tệp, cùng byte range, cùng block size hợp lý và cùng checksum/processing.
3. Làm nóng code Java và dữ liệu theo mục tiêu; nếu là cold/mixed, thiết kế bộ dataset riêng và quy trình kiểm soát bên ngoài JVM.
4. Chạy nhiều lượt với thứ tự hoán đổi, ví dụ A→B→B→A, không để một API luôn chạy trước.
5. Ghi bytes, duration, throughput, CPU, disk I/O, GC và điều kiện test; báo median và phân phối thay vì chỉ tốc độ tốt nhất.
6. Kiểm tra cache state có biến động giữa các lượt, cân nhắc bỏ những lượt bị nhiễu và công bố tiêu chí loại bỏ mẫu trước khi chạy.
7. Khi triển khai thực tế dùng nhiều client, cần benchmark thêm sự cạnh tranh, file sizes và concurrency giống sản phẩm.

Đừng thay đổi cả API, kích thước buffer, cách đọc random/sequential, số luồng và thời điểm flush trong một thử nghiệm rồi quy toàn bộ thay đổi vào API.

## 13. Những lỗi phổ biến và cách sửa

| Ngộ nhận / lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gọi lần đọc đầu tiên là cold vì đó là lần đọc đầu của Java | File có thể đã warm do thao tác tạo/copy | Mô tả first measured pass, kiểm soát dữ liệu và đo disk I/O |
| Đóng `FileChannel` rồi tưởng xóa cache | Lượt đọc sau vẫn được kernel phục vụ từ RAM | Phân biệt vòng đời channel và page cache |
| Gọi `force(true)` rồi tin lần đọc tiếp theo là cold | Force không có ngữ nghĩa eviction | Chỉ dùng force khi muốn đo sync/durability |
| Dùng `allocateDirect()` để bỏ page cache | Direct buffer không tương đương O_DIRECT | Đo copy/alloc riêng, nêu cache path |
| Chạy A trước, B sau trên cùng file | B thường hưởng warm-cache từ A | Đảo thứ tự hoặc tách cache state |
| Chỉ tính thời gian `write()` rồi công bố disk write throughput bền vững | Đo chủ yếu write-back buffering | Công bố write acceptance hoặc tính `force()` khi phù hợp |
| Tạo file test ngay trước “cold read” | Dữ liệu có thể được giữ trong page cache | Có cách thiết lập cold riêng và xác nhận bằng chỉ số |
| Đọc vài MiB rồi suy cho file nhiều GiB | Working set nhỏ có thể nằm trong RAM | Đo theo working set của sản phẩm |
| Dùng `MappedByteBuffer.load()` chỉ cho một chiến lược | Ưu đãi warm-up không công bằng | Giữ phạm vi warm-up tương đương |
| Dùng JMH và giả định cache được reset ở mỗi fork | Fork JVM không reset kernel cache | Kiểm soát cache ngoài JMH |
| Không đọc hết/không xác minh nội dung | Hai phương án không xử lý cùng khối lượng | Đếm bytes, dùng checksum hoặc blackhole hợp lý |
| Dùng file nén/sparse/toàn zero không giống sản phẩm | Tốc độ file system/storage bị bóp méo | Sinh workload dữ liệu tương tự thực tế |
| Chỉ công bố một số MiB/s đẹp nhất | Không biết variance, cold/warm hay nhiễu | Báo phân phối và cấu hình môi trường |
| Thử xóa page cache toàn host đang hoạt động | Ảnh hưởng workload khác và làm biến dạng phép đo | Dùng môi trường thử riêng, quy trình có phê duyệt |

## 14. Checklist báo cáo benchmark có thể tái lập

Một bản báo cáo đọc/ghi file đáng tin cậy nên trả lời:

1. **Mục tiêu:** Đọc tuần tự, ngẫu nhiên, metadata hay durable write? Đang kiểm tra API hay thiết bị?
2. **Bộ dữ liệu:** Tổng byte thật sự đọc/ghi, số file, kích thước mỗi file, mức entropy/compression, file vừa tạo hay đã tồn tại.
3. **Cache condition:** Warm, cold được xác nhận hay mixed/unknown? Trạng thái được chuẩn bị và xác minh bằng cách nào?
4. **Môi trường:** OS/kernel, JVM/vendor/version, CPU, RAM, filesystem, storage device, container/VM hay máy vật lý.
5. **Cấu hình Java:** API, heap/direct buffer, kích thước khối, số luồng, GC/heap size, cách mở/đóng file.
6. **Timer:** Bao gồm open, allocation, read/write, parsing/checksum, force, close và cleanup hay không?
7. **Phương pháp:** Số warm-up pass, số measured pass, cách thay đổi thứ tự A/B, seed random access.
8. **Chỉ số:** Bytes, MiB/s, latency, median/p95, GC/CPU, disk I/O, bộ nhớ và mức biến động.
9. **Độ chính xác:** Kiểm tra checksum/đếm byte, xử lý EOF, partial read/write, lỗi IOException.
10. **Giới hạn:** Các giả định chưa kiểm soát, cache thiết bị hoặc tác vụ nền có thể làm kết quả biến động.
11. **An toàn thử nghiệm:** Không xóa cache toàn máy sản xuất; không chạy benchmark phá dữ liệu thật.
12. **Diễn giải:** Kết luận giới hạn theo workload và cache state đã đo, không khái quát thành tốc độ tuyệt đối của “Java I/O”.

**Ghi nhớ:** Page cache của hệ điều hành có thể biến phép thử đọc tệp thành phép đo truy cập RAM, còn write-back có thể làm phép thử ghi kết thúc trước khi dữ liệu nằm bền vững trên thiết bị. **Đóng file, gọi `force()`, khởi động JVM/container mới hoặc dùng direct `ByteBuffer` không tự xóa page cache**. Benchmark đúng cần định nghĩa mục tiêu cold/warm, kiểm soát working set, đo nhiều lượt công bằng, xác minh khối lượng byte và đối chiếu với số liệu I/O cấp hệ điều hành trước khi kết luận về hiệu năng file hoặc thiết bị.