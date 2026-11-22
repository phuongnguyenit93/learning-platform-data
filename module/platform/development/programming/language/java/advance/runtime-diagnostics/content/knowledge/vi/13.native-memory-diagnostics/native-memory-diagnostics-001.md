# 13.1. Phân biệt không gian địa chỉ reserved, bộ nhớ committed và RSS

## Mục tiêu

Sau bài này, bạn sẽ:

- Phân biệt **reserved virtual address space**, **committed memory** và **Resident Set Size (RSS)**.
- Hiểu vì sao một JVM có `-Xmx` vài GiB vẫn có thể có RSS nhỏ và vì sao RSS có thể cao hơn số NMT committed.
- Đọc đúng Native Memory Tracking (NMT), các số liệu heap, Linux `VmSize`/`VmRSS`/`smaps_rollup` và bộ nhớ container.
- Kết hợp các chỉ số để điều tra native memory tăng, áp lực bộ nhớ hoặc OOM mà không nhầm “đã giữ địa chỉ”, “đã commit” với “đang nằm trong RAM”.

Ví dụ Java chạy trên **Java 17+**. Các lệnh `/proc` và cgroup dành cho **Linux**; tên và ý nghĩa các chỉ số OS khác nhau theo nền tảng.

## 1. Ba lớp đo bộ nhớ là ba câu hỏi khác nhau

### 1.1. Reserved: JVM đã giữ chỗ bao nhiêu địa chỉ ảo?

**Reserved** nghĩa là một khoảng trong **virtual address space** của tiến trình đã được dành cho một mục đích. Nó không tự chứng minh có đủ lượng RAM vật lý tương ứng đang sử dụng.

Ví dụ, với `-Xmx4g`, HotSpot thường **reserve** một vùng địa chỉ ảo gần 4 GiB cho Java heap tối đa. Nếu JVM mới chạy và heap chỉ cần vài trăm MiB, phần lớn vùng reserve chưa cần commit hoặc touch. Trên hệ 64-bit, không gian địa chỉ ảo lớn nên một reservation vài GiB có thể bình thường.

Các vùng có thể reserve đáng kể gồm Java heap, compressed class space, code cache, stack của platform thread và các mapping phục vụ GC. Một vùng class space giữ trước 1 GiB **không** có nghĩa metadata lớp đang ăn 1 GiB RAM.

Reserved vẫn có chi phí/giới hạn về **địa chỉ ảo**. Tiến trình 32-bit, giới hạn virtual memory (`ulimit -v` trên Linux), chính sách memory overcommit, bố trí/fragmentation của address space hoặc mapping khác có thể khiến reserve thất bại, ngay cả khi máy còn RAM. Vì vậy “không tốn RAM ngay” không có nghĩa “không bao giờ có rủi ro”.

### 1.2. Committed: phần JVM đã chuẩn bị để sử dụng

Trong **HotSpot Native Memory Tracking (NMT)**, `committed` phản ánh phần memory đã được JVM commit/cấp phát để có thể sử dụng. Với mapping, nó thường là phần đã được đưa vào trạng thái sử dụng từ vùng giữ chỗ; với cấp phát `malloc` mà NMT theo dõi, kích thước allocated thường được tính là cả reserved và committed.

Điều quan trọng:

- **Committed không đồng nghĩa resident**. Hệ điều hành có thể dùng *demand paging*: trang được hỗ trợ bằng RAM khi được truy cập (*first touch*), thay vì cấp đủ RAM ngay ở thời điểm JVM commit.
- Trang đã được sử dụng có thể bị chuyển sang swap hoặc bị reclaim tùy OS/chính sách; committed vẫn không phải một ảnh chụp số byte RAM đang nằm trong tiến trình.
- Với cùng một vùng NMT, thông thường `reserved >= committed`. Nhưng số committed này **không phải tổng RAM tiến trình**.
- Từ “committed” có thể mang nghĩa khác ở hệ điều hành: **HotSpot NMT committed** không phải số giống hệt Windows *Commit Size* hay Linux `Committed_AS`.

Đừng nhầm committed với **Java heap used**. Heap committed là phần JVM đã cấp cho heap; heap used là phần đang dùng cho đối tượng tại một thời điểm và thường thấp hơn. JVM có thể tiếp tục giữ heap committed sau khi garbage collection giải phóng đối tượng.

### 1.3. RSS: trang nào hiện đang ở RAM vật lý?

**Resident Set Size (RSS)** là dung lượng các trang của tiến trình **đang hiện diện trong RAM vật lý** lúc đo.

Trên Linux, `VmRSS` được tạo từ ba nhóm:

```text
VmRSS = RssAnon + RssFile + RssShmem
```

- **RssAnon**: các trang resident dạng anonymous, chẳng hạn heap và stack.
- **RssFile**: các trang resident của file mappings, như mã thư viện động và file được map.
- **RssShmem**: các trang của shared memory đang resident.

RSS **bao gồm cả các trang shared** được map vào tiến trình, nên không có nghĩa toàn bộ đó là RAM riêng độc quyền. Nếu hai JVM cùng sử dụng một trang thư viện, nó có thể được tính vào RSS của cả hai. Khi cần chia sẻ phần dùng chung theo tỷ lệ, dùng **PSS (Proportional Set Size)** trong `smaps_rollup`.

RSS không bao gồm các trang hiện bị swap ra khỏi RAM. Các trường `VmRSS` trong `/proc/<PID>/status` là số liệu nhanh và có thể không hoàn toàn chính xác khi đối chiếu ở mức trang; `/proc/<PID>/smaps_rollup` có breakdown hữu ích hơn khi cần phân tích kỹ.

## 2. Reserve, commit và resident liên hệ với nhau thế nào?

Với **một vùng mapping** theo mô hình đơn giản:

```text
Reserve address range
    |
    +--> JVM có một khoảng địa chỉ ảo dành cho vùng memory
            |
            v
         Commit
            |
            +--> phần memory được JVM/OS cho phép sử dụng
                    |
                    v
                Access / first touch
                    |
                    +--> hệ điều hành đưa các trang cần thiết vào RAM
                          (về sau có thể reclaim/swap)
```

Đây là **mô hình tiến trình**, không phải công thức chuyển đổi trực tiếp giữa các bộ đếm. Hệ điều hành có thể cấp phát sớm, map file, dùng trang chia sẻ, thực hiện copy-on-write hoặc thay đổi trạng thái resident sau khi commit. Cần phân biệt:

- **NMT reserved / committed:** báo cáo theo phạm vi bộ cấp phát mà **HotSpot NMT theo dõi**.
- **Linux VmSize / VSZ / VIRT:** kích thước **toàn bộ không gian địa chỉ ảo** của tiến trình theo OS.
- **Linux VmRSS / RSS:** các trang của **toàn tiến trình** hiện resident, gồm cả file mappings và shared pages.

NMT không bao phủ mọi cấp phát trong process (đặc biệt có thể bỏ sót thư viện native bên thứ ba/JNI và một số thành phần thư viện JDK). Vì thế **NMT reserved không bắt buộc bằng VmSize**, và **NMT committed không bắt buộc lớn hơn hoặc nhỏ hơn RSS**.

### Một snapshot minh họa

| Chỉ số | Số giả định | Có nghĩa là gì? |
|---|---:|---|
| NMT Java Heap reserved | 4.096 MiB | Địa chỉ ảo giữ chỗ cho phần heap tối đa |
| NMT Java Heap committed | 512 MiB | Phần heap đã commit |
| NMT Total reserved | 5.400 MiB | Tổng vùng được NMT theo dõi đã reserve |
| NMT Total committed | 760 MiB | Tổng vùng được NMT theo dõi đã commit |
| Linux VmSize | 7.100 MiB | Tất cả mappings/địa chỉ ảo của tiến trình |
| Linux VmRSS | 630 MiB | Các trang hiện resident theo OS |

Những giá trị trên **hoàn toàn có thể cùng tồn tại**. Không được tính `5.400 - 630` MiB rồi gọi kết quả là “RAM đã giữ mà chưa sử dụng”. Cũng không được xem `760 - 630` MiB là “swap” hoặc bộ nhớ rò rỉ: chúng đo những phạm vi khác nhau.

Một số kịch bản:

- **Reserved tăng, RSS gần như giữ nguyên:** JVM mới giữ thêm address space, chưa nhất thiết sử dụng thêm RAM.
- **Committed tăng, RSS chưa tăng tương ứng:** các trang được commit nhưng chưa được touch, hoặc OS còn thay đổi backing.
- **RSS tăng, NMT committed không tăng:** trang đã commit trước đó vừa được touch; cũng có thể thư viện/native allocator/mmap bên ngoài phạm vi NMT tăng.
- **RSS lớn hơn NMT committed:** file mappings, shared pages hoặc cấp phát của thành phần NMT không theo dõi có thể đóng góp vào RSS.
- **RSS nhỏ hơn NMT committed:** phần committed chưa resident, đã bị swap/reclaim hoặc chịu cơ chế accounting khác.

## 3. Đặt cạnh các chỉ số Java heap

| Metric | Phạm vi | Không nên suy ra |
|---|---|---|
| `-Xmx` / `Runtime.maxMemory()` | Giới hạn heap tối đa JVM có thể sử dụng | Không phải giới hạn RSS toàn process |
| `-Xms` | Kích thước heap ban đầu được yêu cầu | Không đảm bảo RSS khởi tạo bằng đúng giá trị này |
| `Runtime.totalMemory()` / heap `MemoryUsage.committed` | Phần Java heap đã được JVM cấp để sử dụng | Không phải mọi trang trong phần đó đã resident |
| Heap `used` / `totalMemory() - freeMemory()` (xấp xỉ) | Bộ nhớ heap đang được dùng | Không gồm native memory của nhiều subsystem |
| NMT `Total committed` | Các vùng HotSpot NMT theo dõi | Không phải OS RSS hay toàn bộ native allocations |
| Process `RSS` | Trang RAM resident của toàn process | Không phải memory dùng riêng, không bao gồm swap |

Trong tình huống `-Xms256m -Xmx4g`, JVM có thể reserve heap gần 4 GiB nhưng commit ban đầu chỉ cỡ vài trăm MiB, tùy collector và cấu hình. Sau GC, **heap used** giảm nhưng **heap committed** có thể không giảm ngay vì JVM giữ vùng đó để cấp phát lại. Do vậy process RSS có thể tiếp tục cao.

Các thành phần ngoài Java heap bao gồm **metaspace**, code cache, GC structures, JIT compiler, native thread stacks, **DirectByteBuffer**, memory-mapped files, JNI/native libraries và allocator C/C++. Giới hạn `-Xmx` chỉ áp dụng cho heap, không phải tổng bộ nhớ JVM/process/container.

Đối với thread, stack của **platform thread** có thể reserve một vùng ảo lớn hơn số trang thực dùng. Virtual thread không tương ứng một-một với OS stack; không được lấy số virtual thread nhân với kích thước stack platform thread để dự báo RSS.

## 4. Xem reserved và committed bằng HotSpot Native Memory Tracking

**Native Memory Tracking (NMT)** là chức năng chẩn đoán của HotSpot, gom thông tin cấp phát theo nhóm như `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Other`. NMT bao gồm cả Java Heap trong `Total`; đừng hiểu “NMT Total” là “native **ngoài** Java heap”.

NMT **tắt mặc định** và phải bật khi khởi động JVM:

```bash
# Chọn một trong hai chế độ:
java -XX:NativeMemoryTracking=summary -jar app.jar
java -XX:NativeMemoryTracking=detail  -jar app.jar
```

`summary` tổng hợp theo subsystem; `detail` bổ sung thông tin allocation site/vùng memory, có overhead cao hơn. Theo tài liệu Oracle, việc bật NMT có thể làm tăng chi phí thực thi khoảng **5–10%** tùy workload. NMT không thể bật lại bằng `jcmd` giữa vòng đời của một tiến trình vốn khởi động với NMT tắt.

Sau khi có PID (lấy bằng `jcmd -l` hoặc công cụ OS):

```bash
jcmd -l
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline

# Sau khi chạy một workload và có khoảng quan sát:
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Thay `<PID>` bằng PID thật. Có thể dùng `detail`/`detail.diff` khi khởi động với mức `detail`. Nên lấy baseline **sau warm up** nếu mục đích là phát hiện native memory tăng bất thường.

Một báo cáo có dạng khái quát như sau (**số chỉ minh họa**):

```text
Native Memory Tracking:

Total: reserved=5400MB, committed=760MB
- Java Heap (reserved=4096MB, committed=512MB)
- Class     (reserved=1024MB, committed=24MB)
...
```

Cách đọc đúng:

1. `reserved` cao nhưng `committed` thấp ở `Java Heap` hoặc `Class` có thể chỉ là reservation được thiết kế trước.
2. `mmap`, `malloc`, `arena` trong một category là **phân rã** của cấp phát, không mặc nhiên là các khoản cộng thêm vào `Total`. NMT `Total` cũng **đã gồm Java Heap**.
3. `summary.diff` cho biết biến động mà **NMT nhìn thấy**, không bảo đảm bắt được native allocations do thư viện bên thứ ba/JNI, một số thư viện JDK hoặc toàn bộ phần class data sharing.
4. NMT cung cấp evidence về JVM allocations, **không đo trực tiếp RSS của OS**. Muốn kết luận về RAM phải ghép thêm công cụ hệ điều hành.

Khi thấy NMT committed tăng, xác định **category nào tăng**. GC, JIT hoặc class loading có thể tăng trong warm up rồi ổn định. Growth qua nhiều vòng workload giống nhau, sau khi hệ thống đạt trạng thái ổn định, đáng điều tra hơn một lần tăng lúc khởi động.

## 5. Đo VmSize, RSS, PSS và Swap trên Linux

### 5.1. Đối chiếu số liệu process

Đặt PID thực vào biến Bash:

```bash
PID=12345

ps -p "$PID" -o pid,vsz,rss,comm
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem|VmSwap):' "/proc/$PID/status"
```

**Thay 12345 bằng PID JVM thật.** `VSZ`/`RSS` trong `ps` trên Linux thường tính bằng KiB. `VmSize`/`VmRSS` trong `status` cũng có đơn vị hiển thị. `VmRSS` là ước lượng kích thước resident; `VmSwap` phản ánh một phạm vi swap của tiến trình, không phải phần còn lại của `VmSize`.

Đừng lấy `VSZ - RSS` và đặt tên là “RAM trống của JVM”. Đó chỉ là chênh giữa virtual address size và lượng resident theo OS; không nói trực tiếp được mức RAM còn có thể cấp phát.

### 5.2. Khi cần private/shared và PSS

```bash
PID=12345

grep -E '^(Rss|Pss|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Swap):' "/proc/$PID/smaps_rollup"
```

- `Rss`: tổng các trang resident của mappings.
- `Pss`: memory resident được phân bổ theo tỷ lệ chia sẻ, hữu ích khi so nhiều process.
- `Private_Clean`/`Private_Dirty`: trang thuộc riêng tiến trình; `Shared_Clean`/`Shared_Dirty`: trang chia sẻ.
- `Swap`: các trang đã swap theo phạm vi bộ đếm.

`smaps_rollup` là cách đọc breakdown thuận tiện hơn `smaps` khi chỉ cần tổng; nhưng vẫn có chi phí truy vấn và có thể yêu cầu quyền truy cập phù hợp. Các số OS có thể thay đổi liên tục do workload và kernel, nên khi đối chiếu cần lấy mẫu gần cùng thời điểm.

### 5.3. Container memory không bằng Java RSS

Ở **cgroup v2**, `memory.current` đếm bộ nhớ đang được tính cho cgroup, có thể gồm anonymous memory, page cache, kernel structures và memory của **nhiều tiến trình**. Nó không phải RSS của riêng Java.

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
```

Đường dẫn trên phổ biến trong container dùng cgroup v2; thực tế còn phụ thuộc vị trí cgroup và namespace. Nếu container bị OOM kill, cần xem **cgroup usage/limit/events**, heap, NMT, RSS/PSS, page cache và các tiến trình cùng cgroup. JVM có thể hết giới hạn container mặc dù heap `used` còn thấp.

**Windows/macOS:** Các metric như *Virtual Size*, *Working Set* và *Commit Size/Private Bytes* có hợp đồng OS riêng. Windows *Commit Size* không phải HotSpot NMT `committed`; working set có thể có shared pages. Luôn ghi kèm tên hệ điều hành, công cụ và metric cụ thể khi so sánh giữa môi trường.

## 6. Thực nghiệm Java: Java heap và direct native buffer

Ví dụ này in giới hạn/committed/used của **Java heap**, sau đó tạo một `DirectByteBuffer` 64 MiB ngoài heap. Chương trình ghi vào từng khoảng 4 KiB để truy cập các trang của buffer, rồi dừng cho phép đo NMT/RSS từ terminal khác.

Tạo tệp **`NativeMemoryLayersDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;

public class NativeMemoryLayersDemo {
    private static final int MIB = 1024 * 1024;

    public static void main(String[] args) throws IOException {
        Runtime runtime = Runtime.getRuntime();
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Heap max MiB: " + runtime.maxMemory() / MIB);
        System.out.println("Heap committed MiB: " + runtime.totalMemory() / MIB);
        System.out.println("Heap used approx MiB: "
                + (runtime.totalMemory() - runtime.freeMemory()) / MIB);

        ByteBuffer direct = ByteBuffer.allocateDirect(64 * MIB);
        for (int offset = 0; offset < direct.capacity(); offset += 4096) {
            direct.put(offset, (byte) 1);
        }

        System.out.println("Direct buffer touched: 64 MiB");
        System.out.println("Press Enter to exit.");
        System.in.read();
        System.out.println("First direct byte: " + direct.get(0));
    }
}
```

Biên dịch/chạy Java 17+:

```bash
javac NativeMemoryLayersDemo.java
java -Xms64m -Xmx256m -XX:NativeMemoryTracking=summary NativeMemoryLayersDemo
```

Ví dụ đã được biên dịch và thực thi với **OpenJDK 24**. PID, heap committed và heap used có thể khác theo lần chạy/JDK. Một lần kiểm tra nhận `Heap max MiB: 256` và `Heap committed MiB: 66`; các giá trị này **không phải stdout cố định**. Những dòng sau là ổn định:

```text
Direct buffer touched: 64 MiB
Press Enter to exit.
First direct byte: 1
```

Khi chương trình dừng ở dòng “Press Enter”, mở terminal khác và thay PID:

```bash
jcmd <PID> VM.native_memory summary scale=MB

# Chỉ trên Linux:
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem):' /proc/<PID>/status
grep -E '^(Rss|Pss|Private_Dirty|Swap):' /proc/<PID>/smaps_rollup
```

Trong những lệnh minh họa này, `<PID>` là **placeholder phải thay** bằng số PID; khi dùng Bash có thể viết `/proc/$PID/status` sau khi gán biến `PID` như mục 5.

Quan sát:

- `Heap max` gần `-Xmx`, trong khi `Heap committed` có thể nhỏ hơn đáng kể.
- Direct buffer nằm **ngoài Java heap**, vì thế heap `used` không tăng tương ứng 64 MiB.
- Việc touch trang có thể làm resident memory tăng, nhưng **không cam kết RSS tăng đúng 64 MiB**: kết quả chịu page size, allocator, trạng thái trang trước đó, tính toán RSS và hoạt động JVM khác.
- NMT có thể ghi nhận native allocation của một số đường cấp phát; **category cụ thể phụ thuộc JDK**, và không được coi NMT là bộ đếm đầy đủ mọi direct/JNI/native library allocation.
- Biến `direct` vẫn được dùng sau lúc chờ, nên buffer còn reachable trong thời gian quan sát. Nhấn **Enter** để chương trình in `First direct byte: 1` rồi kết thúc.

Ví dụ cố tình touch toàn bộ buffer để minh họa paging. Trong ứng dụng thực, không nên tự ý touch mọi trang chỉ để đẩy RSS lên.

## 7. Phân tích số đo theo triệu chứng

| Quan sát | Hướng kiểm tra | Dữ liệu cần lấy |
|---|---|---|
| `VmSize`/`VSZ` rất lớn, RSS nhỏ | Có thể có heap/class-space/stack reservation lớn hoặc mapping đặc thù collector | NMT reserved/committed theo category, `/proc/<PID>/maps` |
| Reserved tăng mạnh, committed ổn định | JVM mới reserve address space | NMT diff, giới hạn virtual address |
| Committed tăng, RSS không đổi ngay | Chưa first touch hoặc có cơ chế paging khác | NMT diff, RSS/PSS theo thời gian, page faults |
| RSS tăng, NMT committed ít thay đổi | Trang đã commit vừa được touch, mmap/native library ngoài NMT, allocator giữ cache | `smaps_rollup`, OS profiler, native allocation tracing |
| Heap `used` giảm sau GC, RSS vẫn cao | Heap còn committed, native allocator giữ memory, direct/mapped memory khác | Heap committed, NMT category, RSS/PSS sau GC |
| Java heap không lớn nhưng container OOM | Off-heap/native, page cache, kernel memory, tiến trình khác, cgroup limit | `memory.current`/`memory.stat`/`memory.events` và JVM metrics |
| NMT category tăng qua nhiều vòng workload | Native growth hợp lệ hoặc leak | Baseline sau warm up, cùng tải, NMT detail/call sites |
| NMT không tăng nhưng RSS liên tục tăng | Vùng NMT không theo dõi hoặc trang đã committed bắt đầu resident | OS maps/smaps, JNI/native profiler, shared/file mapping |

Để xác định leak, theo dõi **xu hướng sau warm up và qua nhiều vòng workload tương đương**. JIT compile, class loading, pool, cache và GC có thể làm memory tăng bình thường lúc đầu, rồi ổn định. Một snapshot cao chưa đủ kết luận.

## 8. Tám sai lầm phổ biến

1. **“Reserved 8 GiB = đang chiếm 8 GiB RAM.”** Không đúng: reserved chủ yếu nói về address space.
2. **“NMT committed 2 GiB thì RSS phải đúng 2 GiB.”** Không đúng: phạm vi NMT và OS resident khác nhau; trang committed có thể chưa resident, và RSS có thể gồm trang NMT không theo dõi.
3. **“RSS là bộ nhớ riêng của một process.”** Không đúng: RSS có thể đếm trang shared của nhiều process; PSS và private breakdown hữu ích khi phân bổ.
4. **“`-Xmx512m` nghĩa là JVM không thể dùng hơn 512 MiB trong container.”** Không đúng: ngoài heap còn metaspace, stack, GC, JIT, direct memory, JNI...
5. **“GC xong, RSS bắt buộc giảm.”** Không đúng: heap/allocator có thể giữ vùng committed để tái sử dụng; OS cũng quyết định residency.
6. **“NMT không tăng thì chắc chắn không có native leak.”** Không đúng: NMT không theo dõi đầy đủ thư viện native bên thứ ba và mọi cấp phát.
7. **“`VmSize - VmRSS` là dung lượng RAM còn trống.”** Không đúng: phép trừ giữa virtual size và resident size không phải chỉ số RAM còn có thể sử dụng.
8. **“Linux `Committed_AS` chính là NMT committed.”** Không đúng: `Committed_AS` là ước lượng commit charge toàn hệ thống theo cách kernel xét overcommit; NMT là accounting của một JVM.

## 9. Checklist khi chẩn đoán memory

1. **Xác định phạm vi:** Java heap, HotSpot NMT, toàn process OS hay container/cgroup?
2. **Đồng bộ thời điểm và đơn vị:** KiB/MiB/GiB; cùng PID, thời điểm, workload; snapshot hay diff.
3. **Đặt đúng nhãn:** reserved (địa chỉ ảo), committed (mức cấp phát/commit), heap used, RSS/PSS (resident), swap.
4. **Xem từng category NMT**; nhớ `Total` đã gồm `Java Heap` và các dòng con không được cộng trùng.
5. **Khi process RSS/OOM bất thường:** đối chiếu heap, native allocator, mapped files, shared memory, cgroup và native code.
6. **Để nhận diện leak:** baseline sau warm up, lặp workload, xem tăng trưởng còn tồn tại sau GC và sau khi hết tải.

### Tự kiểm tra

- Khi `-Xms256m -Xmx4g`, vì sao NMT Java Heap reserved có thể gần 4 GiB nhưng committed/RSS nhỏ?
- Vì sao RSS có thể **cao hơn** NMT Total committed và cũng có thể **thấp hơn**?
- Khi heap used giảm sau GC nhưng RSS đứng yên, cần xem thêm dữ liệu nào?
- Vì sao cộng RSS của hai JVM chạy chung một thư viện không bằng tổng memory riêng của cả hai?
- Nếu container bị OOM kill dù Java heap used thấp, cần khảo sát những vùng nào ngoài heap?

## Tài liệu chính thức

- [Oracle Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): NMT summary/detail, phạm vi theo dõi, baseline và hạn chế.
- [Oracle Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.native_memory`, `summary.diff`, `scale`.
- [Oracle Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): các category trong NMT và cách điều tra.
- [Linux kernel — `/proc` filesystem](https://www.kernel.org/doc/html/latest/filesystems/proc.html): `VmSize`, `VmRSS`, `RssAnon`, `RssFile`, `RssShmem`, `smaps_rollup` và PSS.
- [Linux kernel — cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.current`, `memory.stat`, `memory.events`.
