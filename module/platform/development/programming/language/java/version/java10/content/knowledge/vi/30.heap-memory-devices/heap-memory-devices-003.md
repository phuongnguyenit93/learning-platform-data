# Ánh xạ bộ nhớ từ hệ thống tệp được môi trường hỗ trợ — Java heap trên thiết bị bộ nhớ thay thế

## 1. Bài học giải quyết vấn đề gì?

Thông thường, **Java heap** được HotSpot quản lý trên những vùng bộ nhớ ảo mà hệ điều hành hỗ trợ bằng RAM và các cơ chế quản lý trang. Tuy nhiên, một số hệ thống có **thiết bị bộ nhớ khác DRAM**, ví dụ memory modules được OS công bố qua filesystem và cho phép truy cập bằng thao tác load/store của CPU. Trong những môi trường như vậy, HotSpot có thể yêu cầu **heap được backing bởi file mapping** trên filesystem tương ứng.

Từ **Java 10**, **JEP 316 — Heap Allocation on Alternative Memory Devices** bổ sung khả năng này. Tùy chọn HotSpot là:

~~~text
-XX:AllocateHeapAt=<đường-dẫn-filesystem>
~~~

Khi được nền tảng/JVM hỗ trợ, HotSpot có thể sử dụng **memory mapping** để cấp phát **Java object heap** dựa trên thiết bị bộ nhớ được hệ thống tệp phơi bày. Oracle **Java SE 25** vẫn mô tả `-XX:AllocateHeapAt=path` trong phần *Advanced Runtime Options for Java*, vì vậy đây không chỉ là một tham số mang tính lịch sử của Java 10.

Điểm cốt lõi của đề mục **“Ánh xạ bộ nhớ từ hệ thống tệp được môi trường hỗ trợ”** là:

> JVM không thể biến bất kỳ đường dẫn file thành một thiết bị RAM đặc biệt. **Hệ điều hành, phần cứng và filesystem phải cung cấp loại memory mapping phù hợp**; HotSpot chỉ sử dụng cơ chế đó để backing heap.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `AllocateHeapAt` là tùy chọn của **HotSpot**, không phải câu lệnh của ngôn ngữ Java.
- Phân biệt **memory mapping của heap do JVM thực hiện** với `FileChannel.map` do ứng dụng sử dụng.
- Hiểu vai trò của filesystem, device, virtual memory, page tables và page faults.
- Phân biệt **file-backed mmap thông thường** với **DAX (Direct Access)** tới thiết bị memory-like.
- Hiểu tại sao NV-DIMM/persistent-memory media có thể được sử dụng làm **volatile Java heap**, chứ không mặc nhiên trở thành cơ sở dữ liệu bền vững.
- Biết `-Xms`, `-Xmx` và GC tiếp tục có ngữ nghĩa quen thuộc; các vùng **metaspace**, **code heap**, **thread stacks** không tự chuyển theo.
- Thực hành Java 17+ để so sánh output của heap mặc định và heap có `-XX:AllocateHeapAt`.
- Xem các vùng mapping từ `/proc/<pid>/maps` trên Linux và hiểu những giới hạn của bằng chứng.
- Biết kiểm tra filesystem có thực sự hỗ trợ DAX, quyền ghi, dung lượng, hardware semantics, security và performance.
- Tránh nhầm tính năng này với **CDS/AppCDS**, NIO mapped files, heap dumps, off-heap buffers hoặc Java object persistence.
- Chẩn đoán một số lỗi thường gặp khi cấu hình trong Linux/container và tránh áp dụng legacy instructions.

**Ngữ cảnh cha:** **Heap trên thiết bị bộ nhớ**. **Nội dung chính:** **Ánh xạ bộ nhớ từ hệ thống tệp được môi trường hỗ trợ**. Bài ưu tiên hành vi và tài liệu còn được sử dụng trên HotSpot/JDK hiện đại.

## 2. Java heap là gì và bình thường nằm ở đâu?

**Java heap** là vùng bộ nhớ runtime quản lý cho các đối tượng Java được cấp phát trong ứng dụng. Chương trình dùng `new`, mảng, collections, record instances... và JVM cùng garbage collector chịu trách nhiệm quản lý tính reachability và thu hồi vùng heap không còn cần thiết.

Một chương trình:

~~~java
byte[] bytes = new byte[1024 * 1024];
~~~

yêu cầu cấp phát một đối tượng mảng `byte[]` trên Java heap (theo ngữ nghĩa quan sát được). Code không biết và không cần biết những trang vật lý tương ứng đang được OS hỗ trợ bằng DRAM, một vùng file-backed memory đủ điều kiện hay một cơ chế mapping triển khai cụ thể.

Trong môi trường thông thường:

~~~text
Java application
      |
      | new byte[...]
      v
  HotSpot GC heap
      |
      | memory reservation / commitment
      v
  Virtual address space of process
      |
      v
  OS memory manager
      |
      v
  Physical memory and OS paging mechanisms
~~~

Khi `AllocateHeapAt` được bật trong cấu hình hỗ trợ, **đường backing** của vùng heap có thể chuyển sang một **memory-mapped file** nằm trên filesystem được chỉ định. **Không thay đổi syntax cấp phát Java objects** và không bắt từng class biết địa chỉ của thiết bị bộ nhớ.

### 2.1. Java heap không bằng toàn bộ bộ nhớ của JVM

Một JVM còn có nhiều vùng khác:

| Vùng | Vai trò | `AllocateHeapAt` có tự chuyển sang thiết bị thay thế không? |
| --- | --- | --- |
| **Java object heap** | Đối tượng và mảng mà GC quản lý. | **Có thể**, là mục tiêu của `AllocateHeapAt`. |
| **Metaspace** | Phần lớn class metadata của HotSpot. | **Không tự động** chuyển theo heap. |
| **JIT code cache/code heap** | Mã máy do JIT compiler sinh. | **Không tự động** chuyển theo heap. |
| **Thread stacks** | Stack của threads và trạng thái gọi hàm. | **Không tự động** chuyển theo heap. |
| **Direct buffers / native allocations** | Các vùng ngoài Java heap do thư viện/JVM cấp phát. | **Không tự động** chuyển theo heap. |
| **CDS/AppCDS archives** | Class metadata đã chuẩn bị để chia sẻ. | **Cơ chế khác** với object heap backing. |

Oracle Java SE 25 giải thích các vùng khác như code heap, metaspace và thread stacks vẫn ở DRAM theo mô hình của tính năng này. Không nên quảng bá `AllocateHeapAt` như một cách “chuyển toàn bộ JVM sang NV-DIMM”.

### 2.2. Tại sao heap cần memory semantics?

GC và ứng dụng thường đọc, ghi và cập nhật đối tượng theo những yêu cầu nhất quán của Java Memory Model. Một thiết bị thay thế dùng cho heap phải cung cấp **ngữ nghĩa tương thích với bộ nhớ thông thường**, bao gồm **atomic operations** và những đặc tính mà CPU/JVM cần để đọc/ghi an toàn.

Không phải mọi loại lưu trữ đều đáp ứng điều kiện. Một SSD chỉ có giao diện block I/O thông thường **không trở thành DRAM-like memory** vì được mount vào một thư mục; việc mapping file trên SSD có thể đi qua page cache, paging và storage I/O.

## 3. Bộ ba quan trọng: device — filesystem — memory mapping

Một triển khai hợp lệ cần nhìn qua nhiều lớp:

~~~text
APPLICATION JAVA
      |
      v
HOTSPOT JVM
  -XX:AllocateHeapAt=/mnt/pmem-heap
      |
      | request mapping for Java object heap
      v
OPERATING SYSTEM (virtual memory manager)
      |
      | file mapping / page tables / permissions
      v
FILESYSTEM backing /mnt/pmem-heap
      |
      | (nếu hỗ trợ DAX, page cache có thể được bypass)
      v
MEMORY-LIKE DEVICE
  ví dụ thiết bị NVDIMM/DAX phù hợp
~~~

**Đường dẫn filesystem chỉ là cách định vị nơi tạo file backing.** Nó không bảo đảm:

- Có thiết bị NV-DIMM thật bên dưới.
- Filesystem đã kích hoạt DAX.
- Mỗi mapping đều bypass page cache.
- Các trang đang resident 100% trong RAM/PMem.
- Hiệu năng chắc chắn tốt hơn DRAM.
- Dữ liệu object sẽ còn truy xuất được sau khi JVM tắt.

Những kết luận đó cần **kiểm chứng riêng** theo OS, media, mount options, JDK implementation và workload.

### 3.1. Memory mapping là gì?

**Memory mapping (mmap)** cho phép một file hoặc vùng dữ liệu được hệ điều hành gắn với một đoạn **virtual address space** của process. Sau khi mapping, CPU truy cập địa chỉ ảo; OS và thiết bị bộ nhớ quyết định cách trang được backing.

Với file mapping thông thường:

~~~text
Process virtual address
          |
          v
Mapped file pages
          |
          v
OS page cache (khi dùng page-cache-backed mapping)
          |
          v
Filesystem / storage device
~~~

Với filesystem hỗ trợ **DAX** trên thiết bị memory-like:

~~~text
Process virtual address
          |
          v
DAX file mapping
          |
          v
Directly addressable device memory
  (bỏ qua bản sao page cache thông thường)
~~~

**DAX** không đồng nghĩa với mọi file-backed mmap. Tài liệu Linux Kernel giải thích DAX được thiết kế để tránh việc sao chép dữ liệu từ thiết bị bộ nhớ phù hợp sang page cache rồi mới cho userspace truy cập.

### 3.2. Những điều khác nhau dù đều dùng `mmap`

| Cấu hình | JVM có thể map file? | Có thể khẳng định truy cập trực tiếp bộ nhớ NV-DIMM không? |
| --- | --- | --- |
| File trên ổ SSD thông thường | Có thể theo OS/JVM. | **Không**. |
| File trong `tmpfs` dùng RAM | Có thể. | **Không**, không có bằng chứng NV-DIMM. |
| File trên network filesystem | Có thể có mmap theo OS, nhưng còn ràng buộc lớn. | **Không**; không nên coi là backing phù hợp cho heap cần memory semantics. |
| Filesystem được cấu hình DAX nhưng device không hỗ trợ DAX | Có thể thất bại hoặc không kích hoạt DAX thật. | **Không**. |
| Filesystem + device có DAX thực sự và đáp ứng yêu cầu JVM | Có thể là kịch bản đúng mục tiêu JEP 316. | **Có thể xác minh**, nhưng phải kiểm tra filesystem/device thực tế. |

**Không dùng “lệnh chạy không lỗi” làm chứng nhận chất lượng phần cứng.**

## 4. DAX là gì và vì sao liên quan tới đề mục?

**Direct Access (DAX)** là cơ chế trong Linux cho phép một số filesystem truy cập các storage devices mang tính chất **memory-like** theo cách trực tiếp hơn, bỏ qua page cache thông thường với những file được bật DAX phù hợp.

Trong Linux Kernel documentation hiện hành:

- DAX chỉ có tác dụng nếu **underlying device** và **filesystem** hỗ trợ.
- Không phải mọi file trong một filesystem hỗ trợ DAX đều đang bật DAX.
- Các filesystem như **ext4** và **XFS** có các chính sách DAX và cờ per-inode cần kiểm tra.
- **`S_DAX` / `STATX_ATTR_DAX`** giúp biểu thị **trạng thái DAX thực tế của inode**, khác với chỉ đặt một cấu hình gợi ý.
- Trên ext4/XFS hiện đại, những mount options như `dax=inode`, `dax=always` hoặc `dax=never` có ý nghĩa; không nên dùng cách hướng dẫn mount cũ đã đổi semantics.

Một điều cần chú ý: Linux Kernel docs ghi **`-o dax` là alias legacy cho `dax=always` và có thể bị bỏ trong tương lai**. Vì Special Note yêu cầu chỉ dùng kiến thức còn áp dụng hiện nay, đừng khuyến nghị `mount -o dax` như câu lệnh mặc định chuẩn cho mọi ext4/XFS mới.

### 4.1. DAX không phải “mọi file trên thư mục /mnt/pmem”

Giả sử một hệ thống có thiết bị PMem gắn vào `/mnt/pmem`. Cần biết:

1. Loại device thật đang backing filesystem.
2. Filesystem có hỗ trợ DAX trên kernel đó không.
3. DAX policy trên mount và trên inode của file backing.
4. File đang dùng mapping có `S_DAX` hoạt động hay không.
5. Hardware access semantics và khả năng truy cập nguyên tử phù hợp.
6. HotSpot build/collector có chấp nhận và thực sự sử dụng mapping không.

Tên thư mục `/mnt/pmem` **không có giá trị chứng minh**. Ai cũng có thể đặt một folder mang tên như vậy trên ổ đĩa bình thường.

### 4.2. DAX bỏ qua page cache không phải “không có cache”

Với DAX, OS không dùng **page cache như một lớp sao chép dữ liệu file truyền thống**. Nhưng CPU vẫn có **hardware caches** và các quy tắc coherence/flush tương ứng.

Không được diễn giải “bypass page cache” thành “CPU không có cache” hoặc “mọi write lập tức được commit durable”. Đây là các khái niệm khác nhau.

## 5. `-XX:AllocateHeapAt=path` làm gì?

Oracle Java SE 25 vẫn nêu rõ:

- Tùy chọn nhận một **filesystem path**.
- HotSpot sử dụng **memory mapping** để đặt Java object heap trên thiết bị bộ nhớ được chỉ định, ví dụ NV-DIMM phù hợp.
- Thiết bị phải có **semantics giống DRAM**, kể cả những thao tác nguyên tử được JVM yêu cầu.
- Những bộ nhớ khác của HotSpot như **code heap, metaspace, thread stacks** vẫn là vùng riêng, không tự di chuyển.
- Các tùy chọn heap `-Xmx`/`-Xms` và những tùy chọn GC tiếp tục có ngữ nghĩa quen thuộc.

Ví dụ **chỉ dành cho môi trường đã được quản trị viên xác thực** có một filesystem/backing device phù hợp:

~~~bash
java -Xms4g -Xmx4g -XX:AllocateHeapAt=/mnt/pmem-heap -jar application.jar
~~~

Lệnh trên chỉ là **mẫu cấu hình**, không phải một phép thử đã thực hiện trên thiết bị NVDIMM. Đường dẫn `/mnt/pmem-heap` phải tồn tại, được phép tạo backing file, còn dung lượng và mapping support phù hợp. Kích thước heap 4 GiB chỉ là minh họa; **không** lấy làm khuyến nghị cho mọi workload.

### 5.1. Path thường đại diện nơi HotSpot tạo backing file

Trong cách triển khai HotSpot được quan sát, `AllocateHeapAt` nhận một **đường dẫn đến nơi có thể tạo file backing**, thông thường là thư mục trên filesystem mục tiêu. JVM tạo file backing và memory-map các vùng cần thiết.

**Không** nên đưa vào `-XX:AllocateHeapAt` một đường dẫn tới file dữ liệu kinh doanh hoặc file dump đã có với suy nghĩ JVM sẽ nạp các Java objects từ file đó. Tính năng này **không phải loader của object graph**.

Khi thiết lập đường dẫn:

- Chỉ định **directory dành riêng**, dễ quản lý ownership, quota và cleanup.
- Xác minh JVM có quyền tạo và mapping file tại đó.
- Dùng filesystem/device đúng cấu hình mong muốn.
- Không dùng đường dẫn nhạy cảm, ổ đĩa đầy hoặc filesystem thiếu khả năng mapping.
- Không chia sẻ đường dẫn writable với process không đáng tin.

### 5.2. File backing có thể không hiện rõ bằng `ls`

Một số HotSpot/Linux implementations tạo backing file tạm rồi **unlink** tên file trong khi mapping còn tồn tại. Khi đó:

- `ls /mnt/pmem-heap` có thể **không thấy một file tên `jvmheap`**.
- `/proc/<pid>/maps` vẫn có thể cho thấy một file-backed mapping với hậu tố **`(deleted)`**.
- File/inode backing có thể được giải phóng sau khi JVM đóng mapping.
- Không được suy ra “không có mapping” chỉ vì directory listing trống.

**Hậu tố `(deleted)` không đồng nghĩa nội dung Java heap đã được lưu bền vững để khôi phục.** Nó thường chỉ cho biết tên file đã được unlink khỏi directory namespace trong khi process còn giữ mapping.

## 6. Java objects vẫn là **volatile heap**, không phải persistent object database

Tên **persistent memory device** dễ gây hiểu lầm.

Ngay cả khi thiết bị phần cứng có khả năng giữ byte khi mất điện, **Java heap của HotSpot** vẫn có vòng đời do **mỗi JVM process** quản lý:

- Địa chỉ object, metadata, GC bookkeeping và references chỉ có ý nghĩa trong một runtime cụ thể.
- GC có thể di chuyển và thu hồi objects.
- Class loaders và JVM object representation không phải định dạng serialization bền vững.
- JVM mới không thể tự đọc bytes từ file heap cũ rồi phục hồi trạng thái như database transaction log.
- Cleanup/unlink file, crash recovery và data hygiene phải được xử lý theo hợp đồng môi trường.

**Do đó không được tuyên bố:**

> “Dùng `AllocateHeapAt` rồi restart JVM thì các Java objects cũ tự xuất hiện lại.”

Tính năng này được thiết kế cho cách **sử dụng vùng thiết bị bộ nhớ khác như volatile Java heap**, không tự cung cấp durability, transactions, serialization hay crash consistency.

### 6.1. Persistence của medium ≠ persistence của Java object graph

| Thành phần | Có thể tồn tại sau mất điện? | Có thể Java tự khôi phục object graph nhờ `AllocateHeapAt`? |
| --- | --- | --- |
| Byte trên thiết bị PMem được cấu hình đúng | Phụ thuộc medium, flush, filesystem và durability guarantees. | **Không tự động**. |
| Java heap reference trong một process | Không được bảo đảm có nghĩa sau restart. | **Không**. |
| Serialized dữ liệu đã ghi theo protocol bền vững | Có thể nếu ứng dụng triển khai và lưu đúng. | Cần logic khôi phục riêng. |
| Heap dump `.hprof` | File chẩn đoán có thể được lưu lại. | **Không** phải startup heap snapshot tự động. |
| CDS archive `.jsa` | Là artifact tối ưu class metadata. | **Không** chứa mutable application heap để phục hồi. |

Nếu nghiệp vụ cần durable state, hãy dùng hệ thống lưu trữ/transaction/serialization được thiết kế cho mục đích đó. Không dùng `AllocateHeapAt` như bản thay thế cho database hoặc snapshot.

## 7. Chương trình Java 17+ hoàn chỉnh

Để hiểu tính **trong suốt đối với Java code**, chạy cùng một chương trình với heap thông thường và với một file-backed heap trên filesystem có memory mapping. Kết quả nghiệp vụ phải giống nhau.

Tạo file **`AlternativeHeapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AlternativeHeapDemo {
    public static void main(String[] args) {
        List<byte[]> blocks = new ArrayList<>();

        for (int i = 0; i < 4; i++) {
            byte[] bytes = new byte[1024 * 1024];
            bytes[0] = (byte) (i + 1);
            bytes[bytes.length - 1] = (byte) (i + 1);
            blocks.add(bytes);
        }

        long checksum = 0;
        for (byte[] bytes : blocks) {
            checksum += Byte.toUnsignedInt(bytes[0]);
            checksum += Byte.toUnsignedInt(bytes[bytes.length - 1]);
        }

        System.out.println("blocks=" + blocks.size());
        System.out.println("bytes=" + 4 * 1024 * 1024);
        System.out.println("checksum=" + checksum);
        System.out.println("heapMaxPositive=" +
                (Runtime.getRuntime().maxMemory() > 0));
    }
}
~~~

**Giải thích code:**

1. Chương trình cấp phát bốn mảng, mỗi mảng **1 MiB**.
2. Chỉ ghi hai phần tử ở đầu/cuối mảng để có kết quả kiểm tra ổn định.
3. Giữ các mảng trong `List<byte[]>` cho đến khi tính checksum.
4. `Byte.toUnsignedInt` chuyển byte sang giá trị không dấu để phép tính dễ đọc.
5. Tổng `1+1+2+2+3+3+4+4` bằng **20**.
6. `Runtime.maxMemory()` là Java heap maximum JVM báo, không phải bằng chứng physical medium hay DAX.
7. Không đọc hardware address bằng Java API; làm vậy sẽ không portable và không cần thiết với code nghiệp vụ.

### 7.1. Biên dịch

~~~bash
javac -encoding UTF-8 AlternativeHeapDemo.java
~~~

Chương trình chỉ dùng Java SE, biên dịch trên Java 17+ và không cần thư viện ngoài.

### 7.2. Chạy với heap thông thường

~~~bash
java -Xms64m -Xmx64m AlternativeHeapDemo
~~~

**Stdout đã được kiểm chứng trên OpenJDK 21.0.12.1 Linux:**

~~~text
blocks=4
bytes=4194304
checksum=20
heapMaxPositive=true
~~~

`4 * 1024 * 1024 = 4.194.304` bytes là tổng dữ liệu mảng do chính chương trình yêu cầu; **heap thực tế còn overhead** của objects, metadata và runtime nên không lấy số này làm heap-used metric.

### 7.3. Chạy với một filesystem path để minh họa memory mapping

Trên **Linux sandbox/test** có quyền tạo thư mục tạm:

~~~bash
HEAP_DIR=$(mktemp -d)
javac -encoding UTF-8 AlternativeHeapDemo.java
java -Xms64m -Xmx64m -XX:AllocateHeapAt="$HEAP_DIR" AlternativeHeapDemo
rmdir "$HEAP_DIR"
~~~

**Lưu ý:** Lệnh trên chỉ dành cho môi trường kiểm thử có thể tạo heap mapping trong thư mục tạm. Không dùng `/tmp` như đường dẫn mặc định cho production memory device và không xóa thư mục nếu còn JVM đang chạy hoặc file quan trọng. Trong triển khai thật, dùng một **dedicated directory của filesystem được kiểm chứng**.

**Trên OpenJDK 21.0.12.1 Linux đã kiểm chứng**, chạy với tùy chọn `AllocateHeapAt` trỏ đến một thư mục tạm trên filesystem thông thường cho cùng stdout:

~~~text
blocks=4
bytes=4194304
checksum=20
heapMaxPositive=true
~~~

Điều này chứng minh **chương trình vẫn hoạt động với heap backing qua file mapping trong môi trường test**. Nó **không chứng minh** thư mục đó được backing bởi NV-DIMM hoặc DAX. Trong phần 8, chúng ta kiểm tra thêm OS mapping.

### 7.4. Vì sao chỉ dùng heap 64 MiB?

Heap 64 MiB đủ cho bốn mảng và runtime trong thử nghiệm, giúp chạy nhanh mà không đòi một memory device dung lượng lớn. Tuy nhiên:

- `-Xms64m` và `-Xmx64m` là **cấu hình lab**, không phải khuyến nghị production.
- Dung lượng file backing có thể liên quan **reserved/committed** heap và logic cấp phát, không đơn giản bằng tổng kích thước mảng `4 MiB`.
- JVM có thể reserve address space nhiều hơn committed physical pages.
- Những collector khác nhau có thể có ràng buộc riêng; đừng hứa `AllocateHeapAt` hỗ trợ mọi collector/OS combination.
- Code không biết memory placement, vì vậy stdout giống nhau là **đúng dự kiến**, không đủ làm bằng chứng location.

## 8. Kiểm tra mapping ở mức hệ điều hành trên Linux

### 8.1. Đọc `/proc/<pid>/maps`

Linux ghi các virtual memory areas của process trong:

~~~text
/proc/<pid>/maps
~~~

Với JVM dùng file-backed heap, bạn có thể thấy một vùng mapping với:

- Dải địa chỉ ảo.
- Quyền đọc/ghi.
- Private/shared mapping flag.
- File offset và device/inode.
- Đường dẫn backing file hoặc một tên đã bị unlink.

Trên thí nghiệm OpenJDK 21.0.12.1 Linux, quan sát thực tế có các dòng dạng:

~~~text
... rw-s ... /tmp/java10-heapmap-.../#... (deleted)
~~~

Đây là **ví dụ trích rút các trường quan trọng**, không phải bản ghi nguyên văn với địa chỉ ảo cố định. `rw-s` là dấu hiệu vùng file mapping có quyền đọc/ghi và shared mapping theo encoding của `/proc/maps`.

**Điều quan sát chứng minh:** JVM có vùng **file-backed writable mapping** tại path đã cấp trong lần chạy thử.

**Điều quan sát không chứng minh:** filesystem đó dùng DAX; thiết bị là NV-DIMM; mapping truy cập trực tiếp bytes không qua page cache; objects có tính bền vững; hoặc hiệu năng sẽ cải thiện.

### 8.2. Xem mapping khi JVM còn chạy

Với một ứng dụng service chạy dài, có thể dùng:

~~~bash
PID=<pid-cua-JVM>
grep -E 'jvmheap|pmem|heap' "/proc/$PID/maps"
~~~

**Không dùng chuỗi filename `jvmheap` như một đảm bảo bất biến.** Tên file backing cụ thể có thể khác theo JDK/OS, và HotSpot có thể unlink file nên tên hiển thị trở thành `(deleted)`.

Trong ứng dụng thật, nên lọc theo **directory path đã truyền vào `AllocateHeapAt`** và đối chiếu PID với chính tiến trình mong muốn. Nếu có nhiều JVM, mỗi process có `/proc/<pid>/maps` riêng.

### 8.3. Vì sao nhìn thấy `(deleted)` không phải bug?

Các chương trình Unix có thể unlink tên file **sau khi mở file descriptor/mapping**. Mapping còn hoạt động trong lifetime của process dù directory entry đã bị xóa. Khi JVM kết thúc, kernel có thể giải phóng resource tương ứng.

Hậu tố này thường xuất hiện trong test, nhưng không nên buộc mọi bản JDK phải hiển thị cùng một tên hoặc hậu tố.

### 8.4. Không đọc page table như heap object format

`/proc/maps` cho biết **vùng address space**, không có cách nào dùng đó để giải mã Java object references hoặc phân tích object graph. Nếu cần phân tích objects và GC, dùng **JFR, heap dump, GC logs, jcmd** theo đúng mục đích.

Không viết Java code dựa vào một địa chỉ ảo cụ thể đọc từ `/proc/maps`. ASLR, GC, compression và JVM internals có thể thay đổi các địa chỉ đó.

## 9. Làm sao xác minh **filesystem thực sự hỗ trợ DAX**?

Để triển khai trên thiết bị memory-like, thao tác cấu hình thuộc trách nhiệm quản trị hệ thống, không phải một đoạn code Java có thể tự quyết định.

### 9.1. Bắt đầu từ thiết bị và mount

Trên Linux, các lệnh điều tra **chỉ đọc** có thể bao gồm:

~~~bash
findmnt -T /mnt/pmem-heap -o TARGET,SOURCE,FSTYPE,OPTIONS
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -h /mnt/pmem-heap
ls -ld /mnt/pmem-heap
~~~

Thông tin cần lấy:

- Directory có thực sự tồn tại?
- Nó nằm trên thiết bị/mount nào?
- Filesystem loại gì? Phiên bản kernel/driver nào?
- Có đủ dung lượng và quyền tạo backing file không?
- Thiết bị có thật sự hỗ trợ DAX/byte-addressable memory semantics?
- Filesystem policy có bật DAX cho **backing file** cụ thể không?

`findmnt`/`lsblk` là nguồn **thông tin hệ thống**, không phải bằng chứng duy nhất DAX đã kích hoạt trên inode. Cần kiểm tra DAX flags/policy của **file thực sự dùng** khi có thể.

### 9.2. DAX policy hiện hành trên ext4/XFS

Linux Kernel documentation mô tả:

- `S_DAX`: trạng thái DAX hiệu dụng trên inode.
- `STATX_ATTR_DAX`: thuộc tính có thể truy vấn qua `statx`.
- `FS_XFLAG_DAX`: cờ lưu gợi ý DAX qua metadata filesystem.
- `dax=inode`, `dax=always`, `dax=never`: các chính sách mount trong những filesystem áp dụng.

**Cảnh báo cập nhật:** Trên ext4/XFS hiện đại, `-o dax` là alias legacy và có thể bị loại bỏ; ưu tiên tham khảo `dax=always` hoặc chính sách per-inode phù hợp theo **đúng kernel/filesystem**, thay vì bê lệnh mount cũ từ một bài Java 10.

Ngoài ra, đặt cờ hint trên **directory** không chứng minh ngay tất cả inode đã có `S_DAX`; chính sách có thể được áp khi tạo file hoặc khi inode được tái khởi tạo theo quy tắc kernel.

### 9.3. Quy tắc an toàn khi xác minh

Không tự:

- Format một ổ hoặc NV-DIMM bằng `mkfs` trong bài lab.
- Thay mount options của production filesystem khi chưa có backup và maintenance window.
- Chuyển device mode, tạo namespace PMem hoặc thay firmware trong môi trường người học.
- Xóa hoặc truncate backing file của một JVM đang chạy.
- Cấp quyền writable cho mọi process chỉ để JVM chạy được.

Các thao tác này có thể làm mất dữ liệu của ứng dụng khác. Bài học chỉ đưa ra **lệnh kiểm tra trạng thái**, còn việc thiết lập phần cứng/filesystem phải theo runbook và quản trị viên hệ thống.

## 10. Cần bao nhiêu dung lượng filesystem và nên cấp phát thế nào?

`-Xmx` là **max Java heap**, còn `-Xms` là **initial heap size**. JVM vẫn cần vùng address space, backing file capacity và tài nguyên OS phù hợp để hoạt động.

Ví dụ:

~~~bash
java -Xms8g -Xmx8g -XX:AllocateHeapAt=/mnt/pmem-heap -jar application.jar
~~~

Về mặt thiết kế, cần dự trù dung lượng và mapping phù hợp với heap được cấu hình, bên cạnh overhead của JVM và hệ điều hành. **Không lấy tổng kích thước các object đang sống** làm kích thước backing file tối đa cần thiết.

Nếu filesystem:

- Đã gần đầy hoặc bị quota.
- Không hỗ trợ tạo file/mmap kiểu JVM yêu cầu.
- Không cho phép process ghi.
- Cấp phát backing file thất bại.
- Không còn memory resources hoặc device gặp I/O errors.

thì JVM có thể **không khởi động được** hoặc **bị lỗi** theo behavior của bản runtime. Không viết ứng dụng phụ thuộc vào việc JVM **luôn tự fallback** sang DRAM khi `AllocateHeapAt` thất bại; cần xem log và exit code thực tế.

### 10.1. Tại sao không chọn `/tmp` làm PMem production?

`/tmp` có thể là:

- Một filesystem trên ổ đĩa bình thường.
- Một `tmpfs` dùng RAM.
- Một mount bị giới hạn bởi container/quota.
- Một directory được dọn theo chính sách hệ thống.

Nó có thể **cho phép mmap**, nhưng không đảm bảo file mapping tới thiết bị DAX/NV-DIMM. Vì vậy thử nghiệm trên `/tmp` chỉ có giá trị xác minh cú pháp và behavior mapping **trên host thử**, không phải chứng nhận tính năng **alternative memory device** trong production.

### 10.2. Dành đường dẫn riêng cho từng JVM?

Nếu nhiều JVM cần tạo backing file trong cùng một filesystem, có thể dùng directory chung được quản lý an toàn nhưng nên có **quota/ownership/capacity và isolation** phù hợp.

Không tự cho rằng hai JVM chạy cùng `AllocateHeapAt` sẽ **chia sẻ cùng Java heap**. Mỗi JVM có object heap và garbage collector riêng; cùng backing device/filesystem **không** biến hai process thành một shared object graph.

Nếu muốn giao tiếp liên process, dùng IPC, database hoặc một shared-memory protocol chuyên dụng; `AllocateHeapAt` không cung cấp API đó.

## 11. Có cần sửa Java code khi chuyển heap sang memory device?

Về **ngữ nghĩa Java**, không:

~~~java
var list = new java.util.ArrayList<String>();
list.add("hello");
System.out.println(list.get(0));
~~~

Khi môi trường cho phép, `AllocateHeapAt` thay đổi **cách HotSpot backing Java heap**, không thay đổi cách gọi `new`, `List.add`, `String` hoặc GC semantics mà ứng dụng được phép dựa vào.

Điều cần làm ở tầng ứng dụng:

- Vẫn tuân thủ Java Memory Model và thread-safety.
- Vẫn xử lý lỗi application-level bình thường.
- Không lấy địa chỉ physical của Java object làm API.
- Không giả định objects tồn tại bền vững sau restart.
- Không chia sẻ một object giữa hai JVM bằng cách truyền giá trị địa chỉ.
- Vẫn kiểm thử hiệu năng dưới workload thật, vì memory device có thể khác DRAM về latency/bandwidth.

### 11.1. Garbage collector vẫn làm việc

Oracle docs nói các GC-related flags và heap flags tiếp tục hoạt động theo ngữ nghĩa trước đó. Điều đó không có nghĩa mọi collector/OS/filesystem/JDK build đều có **đúng cùng hỗ trợ kỹ thuật** đối với alternative heap backing.

Hãy xác minh:

1. `java -version` và HotSpot build.
2. Collector thực tế qua `-Xlog:gc+init=info`.
3. `-Xms`/`-Xmx`, page size, reserved/committed memory.
4. Archive/large-page/NUMA flags có xung đột hay hạn chế không.
5. Startup đã thành công và chương trình chạy đúng.
6. OS mapping/medium thật có phù hợp với yêu cầu thiết bị không.

Không thay đổi hàng loạt GC flags chỉ vì chuyển backing device. Bắt đầu từ cấu hình đã được benchmark và so sánh trước/sau.

## 12. Không nhầm với `FileChannel.map` hoặc Foreign Function & Memory API

Java cũng có API cho **ứng dụng tự ánh xạ file**, ví dụ:

~~~java
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("data.bin"),
        java.nio.file.StandardOpenOption.READ,
        java.nio.file.StandardOpenOption.WRITE)) {
    java.nio.MappedByteBuffer buffer =
            channel.map(
                    java.nio.channels.FileChannel.MapMode.READ_WRITE,
                    0,
                    1024);
    buffer.putInt(0, 42);
}
~~~

**Đây chỉ là đoạn minh họa NIO mapping**, yêu cầu file và môi trường phù hợp; không phải chương trình demo độc lập đã kiểm chứng của phần 7.

Sự khác biệt:

| Cơ chế | Ai yêu cầu mapping? | Dữ liệu nào được map? | Có tự thành Java object heap? |
| --- | --- | --- | --- |
| **`-XX:AllocateHeapAt=path`** | **HotSpot JVM** lúc khởi động. | Backing cho Java object heap. | **Có**, đó là mục tiêu của flag. |
| **`FileChannel.map`** | **Java application**. | File được ứng dụng chọn. | **Không**; buffer/view riêng. |
| **`MemorySegment` file mapping (FFM API)** | Java application. | File được mapped thành off-heap memory segment theo API được hỗ trợ. | **Không**; là bộ nhớ segment. |
| **CDS/AppCDS** | HotSpot JVM. | Class metadata được archive và dùng lại. | **Không**; khác mutable object heap. |
| **Heap dump `.hprof`** | JVM diagnostics. | Snapshot phục vụ phân tích objects. | **Không**; không phải cách backing heap live. |

**Không** chỉ thấy từ `mmap` rồi cho rằng các cơ chế này đồng nhất.

### 12.1. `FileChannel.map` không tự chuyển toàn bộ heap

Chương trình dùng `MappedByteBuffer` để đọc/ghi file sẽ có **một vùng file-backed buffer**. Những đối tượng Java khác vẫn ở Java heap theo cấu hình VM. Không phải cứ có một mapped file thì `ArrayList` hoặc tất cả `byte[]` đã được cấp phát ở thiết bị đó.

### 12.2. FFM không biến file mapping thành shared Java heap

Foreign Function & Memory API là API hiện đại cho những vùng memory segments/foreign memory. Nó có use cases khác, không thay thế `AllocateHeapAt` như một JVM heap-placement option.

Nếu cần tự thiết kế persistent data structures, bạn phải xác định layout, ownership, concurrency, crash consistency và lifecycle. Đừng lấy một map file thành “đã có Java heap bền vững”.

## 13. Dữ liệu có thể bị lộ qua backing device không?

Có thể có **rủi ro bảo mật/vận hành** cần đánh giá:

- Java heap có thể chứa dữ liệu nghiệp vụ hoặc secrets trong memory của process.
- File backing trên filesystem/device phải có quyền truy cập chặt chẽ.
- Một filesystem có tính persistent không có nghĩa JVM tự có chính sách secure erase sau crash.
- Mapping hoặc backing allocation có thể tồn tại cho tới khi process/kernel dọn resource; behavior cụ thể phụ thuộc JDK/OS/filesystem.
- Dumps, swap, crash artifacts và forensic images có thể là nguồn lộ dữ liệu.
- Đặt directory writable cho untrusted users có thể dẫn tới rủi ro ảnh hưởng file backing hoặc đặt một filesystem không đúng thiết bị.

**Thực hành:**

1. Dùng mount và directory được quản trị viên kiểm soát.
2. Giới hạn quyền đọc/ghi của OS user chạy JVM.
3. Có chính sách encryption/data-at-rest phù hợp nếu medium lưu giữ dữ liệu.
4. Không tái sử dụng các bytes còn sót để khôi phục object graph.
5. Đặt quy trình xử lý crash, cleanup và revoke access rõ ràng.
6. Đọc tài liệu filesystem/device cho khả năng dữ liệu còn lưu trên media.

Không hứa “vì file bị unlink nên mọi bytes đã được xóa an toàn”. Unlink tên file **không bảo đảm secure erasure của persistent media**.

## 14. Hiệu năng: thiết bị thay thế không chắc nhanh hơn DRAM

Một thiết bị memory-like có thể có **dung lượng lớn hơn hoặc chi phí khác** DRAM, nhưng latency/bandwidth và các hành vi NUMA/cache có thể khác đáng kể.

Các yếu tố ảnh hưởng:

- Độ trễ khi truy cập các trang được backing bởi thiết bị.
- Throughput/bandwidth của memory bus.
- CPU caching, NUMA locality và synchronization.
- Số objects sống, allocation rate, kích thước heap.
- GC cycles, collector và object-movement patterns.
- Page faults, first-touch behavior, filesystem/dax semantics.
- Container limits và hoạt động I/O của hệ thống.
- Mức overhead của native/DRAM components ngoài Java heap.

**Không** kết luận “mmap là zero-copy nên heap chắc chắn nhanh hơn”. Một mục tiêu thực tế có thể là **giảm áp lực dung lượng DRAM** hoặc có thêm capacity cho live set lớn, với trade-off latency/bandwidth.

### 14.1. Benchmark có ý nghĩa cần so những gì?

| Tiêu chí | Baseline heap mặc định | Heap backing từ memory device |
| --- | --- | --- |
| JVM/JDK build | Cố định | Giống baseline. |
| `-Xms`, `-Xmx` | Cố định | Giống baseline. |
| GC/VM flags | Cố định | Chỉ khác `AllocateHeapAt` khi có thể. |
| Application JAR/input | Cố định | Giống baseline. |
| Startup latency | Đo nhiều lượt. | Đo cùng điều kiện. |
| Throughput | Đo dưới tải ổn định. | Đo cùng tải. |
| GC pause p95/p99 | Thu GC logs/JFR. | So collector + workload. |
| Heap used/live set | Theo dõi theo thời gian. | Cùng cách đo. |
| Memory/device placement | Xác minh OS mapping. | Xác minh DAX/device nếu mục tiêu đó. |
| Failure behavior | Ghi timeout/OOME. | Ghi startup/mapping errors. |

Nếu môi trường benchmark không có device DAX phù hợp, hãy **nói rõ** thử nghiệm chỉ so **file-backed mapping thông thường**, không so DRAM với NV-DIMM.

### 14.2. Heap backing không giảm mọi vùng DRAM

Vì metaspace, code cache, stacks và các native allocations vẫn có thể dùng DRAM, tổng DRAM consumption **không giảm đúng bằng giá trị `-Xmx`**. Cần đo OS memory footprint theo đúng accounting của platform.

Ví dụ: nếu heap tối đa 4 GiB đặt lên device khác, không thể kết luận process không dùng DRAM. Thêm nữa, một số layer page cache, overhead kernel hoặc storage behavior còn phụ thuộc filesystem thực tế.

## 15. Cách chẩn đoán khi `AllocateHeapAt` không hoạt động

Những nhóm lỗi có thể xảy ra:

| Hiện tượng | Nguyên nhân cần xem | Hành động hợp lý |
| --- | --- | --- |
| `Unrecognized VM option` | JVM vendor/platform/version không hỗ trợ flag. | Kiểm tra `java -version` và Java launcher docs của runtime. |
| JVM báo không tạo/mở được backing file | Directory sai, thiếu quyền, filesystem read-only. | Kiểm tra path, owner, ACL, mount options. |
| JVM báo không reserve/map được heap | Device/filesystem/memory mapping constraints, heap size. | Kiểm tra `-Xms/-Xmx`, capacity, OS logs/JVM logs. |
| JVM chạy nhưng không có DAX | Mapped file trên filesystem thường hoặc DAX không bật ở inode. | Kiểm tra device và `S_DAX`; đừng dựa vào output Java. |
| File backing không thấy trong `ls` | HotSpot đã unlink temporary file. | Xem `/proc/<pid>/maps` khi JVM còn sống. |
| Crash/OOME xảy ra | Không nhất thiết do alternative memory; có thể pressure, device error hoặc lỗi app. | Thu GC logs, hs_err, OS diagnostics. |
| Hiệu năng kém hơn | Thiết bị latency cao hơn, NUMA, page faults, GC workload. | Benchmark và phân tích native/heap/device metrics. |
| Sau restart Java objects biến mất | Đây không phải persistent heap restoration. | Dùng persistence mechanism được thiết kế riêng. |

### 15.1. Trình tự triage

1. **Xác nhận JDK build và OS** bằng `java -version`.
2. **Xác minh flag được hỗ trợ** theo Java launcher docs và JVM options thực tế.
3. **Kiểm tra directory** được chỉ định có tồn tại và JVM user có quyền write/create/mmap.
4. **Kiểm tra dung lượng** của filesystem và mọi quota/container limits liên quan.
5. **Kiểm tra physical device và DAX policy** nếu mục tiêu là thiết bị non-DRAM.
6. **Dùng heap nhỏ trong lab an toàn** để tách lỗi môi trường khỏi áp lực workload thật.
7. **Chạy cùng code không có flag** để có baseline.
8. **Xem `/proc/<pid>/maps`** trên Linux khi JVM đang chạy; lọc đường dẫn thực.
9. **Thu JVM/OS logs** để biết fail ở open, reserve, commit, mapping hay runtime.
10. **Chỉ triển khai production** sau khi khẳng định performance, security, compatibility và rollback.

### 15.2. Những gì `PrintFlagsFinal` có thể giúp

Một số HotSpot có thể hiển thị flag trong:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Nếu muốn lọc:

~~~bash
java -XX:+PrintFlagsFinal -version | grep AllocateHeapAt
~~~

Việc flag xuất hiện/được nhận không chứng minh **filesystem mapping thành công** trong một JVM ứng dụng. Flag discovery là bước tiền đề, không thay OS mapping inspection.

### 15.3. GC logs và Native Memory Tracking dùng cho vấn đề khác

Với GC:

~~~bash
java -Xlog:gc* -Xms64m -Xmx64m AlternativeHeapDemo
~~~

Log sẽ giúp đọc heap capacity, occupancy và collector events. Nhưng thông thường nó **không cho biết chi tiết lớp physical memory device** của mọi heap page.

**Native Memory Tracking** hoặc `jcmd VM.native_memory` giúp phân tích một số JVM native categories, nhưng không biến một JVM-level allocation report thành chứng nhận DAX. Xem thêm **OS mapping** và filesystem/device diagnostics.

## 16. Chạy trong Docker/container có điểm gì cần lưu ý?

Một container có thể thấy đường dẫn mount từ host, nhưng:

- File backing phải được phép tạo/mmap từ namespace của container.
- Memory/device path phải được mount vào đúng nơi.
- Cgroup memory limits vẫn có thể ảnh hưởng JVM và process; không tự loại trừ OOM kill chỉ vì heap backed bởi file.
- Filesystem trên host phải thật sự là loại cần dùng; container bind mount **không tự chuyển storage thành DAX**.
- Container security policies (SELinux/AppArmor/seccomp/mount permissions) có thể cản trở access.
- Filesystem tạm của container có thể bị xóa/recreate, ảnh hưởng capacity và lifecycle.
- Không đưa thông tin mật trong heap vào một shared writable mount không tin cậy.

**Không** coi việc container chạy được lệnh trên `/tmp` là bằng chứng thiết bị persistent memory đã được bật.

### 16.1. Cần kiểm chứng trên runtime image thật

1. Pin đúng JDK vendor/build.
2. Mount thiết bị/filesystem đã được quản trị xác minh.
3. Dùng một directory riêng cho JVM user.
4. Xem `java -version` và VM flags bên trong container.
5. Chạy với heap size/resource limits phù hợp.
6. Xác minh mapping/metrics tại host và container namespace.
7. Đọc GC logs, application outputs và đo throughput/latency.
8. Ghi lại cách rollback về heap mặc định nếu thiết bị không sẵn sàng.

**Không** sử dụng một kết quả từ máy phát triển khác nền tảng để chứng minh thiết bị production hỗ trợ memory mapping.

## 17. Những nhầm lẫn thường gặp

| Ngộ nhận | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Chỉ cần đặt `-XX:AllocateHeapAt=/tmp` là có NV-DIMM.” | `/tmp` thường không chứng minh loại physical device. | Phải xác minh device/filesystem và DAX. |
| “File-backed mmap nào cũng là DAX.” | Mmap thông thường có thể dùng page cache. | DAX là cơ chế riêng cần underlying support. |
| “Có chữ `pmem` trong path nghĩa thiết bị PMem thật.” | Path có thể đặt tên tùy ý. | Kiểm tra mount/source/device. |
| “Filesystem báo hỗ trợ DAX nên mọi file đều đang ở DAX mode.” | Policy có thể per-inode và cần `S_DAX`. | Xem DAX thực tế trên file backing. |
| “`-o dax` luôn là cú pháp mount tương lai.” | Kernel docs ghi alias legacy có thể bị bỏ. | Dùng policy DAX hiện hành phù hợp OS. |
| “JVM memory mapping nghĩa toàn bộ file đã ở RAM.” | Mapping địa chỉ ảo khác resident pages. | Xem page faults/OS memory accounting. |
| “AllocateHeapAt biến Java heap thành một database bền vững.” | JVM objects/GC/runtime state không có format restore. | Dùng persistence protocol riêng. |
| “Sau restart object cũ vẫn tồn tại vì PMem là non-volatile.” | Medium durability không phải object graph persistence. | Serialize/transaction/restore có chủ đích. |
| “Một JVM dùng path đó làm heap chung với JVM khác.” | Mỗi process có heap/GC riêng. | Cần IPC/shared-memory protocol khác. |
| “Một file dump HPROF là backing file của live heap.” | Heap dump là snapshot diagnostic. | Phân biệt dump với memory mapping. |
| “`FileChannel.map` chuyển tất cả `new` sang file.” | MappedByteBuffer là vùng riêng của ứng dụng. | JVM heap placement là một flag khác. |
| “CDS archive là object heap live.” | CDS tối ưu class metadata. | Không nhầm AppCDS và JEP 316. |
| “Metaspace và thread stacks cũng tự nằm trên thiết bị thay thế.” | Oracle docs nói những vùng khác vẫn ở DRAM. | Chỉ nói tới Java object heap. |
| “`-Xmx` vô hiệu khi dùng `AllocateHeapAt`.” | Heap sizing flags vẫn có ngữ nghĩa. | Tiếp tục cấu hình/đo heap đúng cách. |
| “Mọi collector đều hoạt động giống nhau trên mọi device.” | Phụ thuộc HotSpot build, OS và GC. | Kiểm tra hỗ trợ thực tế và benchmark. |
| “Java chạy không lỗi chứng minh có DAX.” | Mmap thường cũng có thể thành công. | Dùng filesystem/kernel diagnostics. |
| “File `(deleted)` trong maps nghĩa object data đã được xóa sạch.” | Unlink không phải secure erase. | Quản lý data-at-rest và cleanup. |
| “Vì heap trên thiết bị khác nên JVM không còn dùng DRAM.” | Native areas vẫn có thể dùng DRAM. | Đo total footprint đúng nghĩa. |
| “Memory device chắc chắn nhanh hơn DRAM.” | Latency/bandwidth khác, có thể chậm hơn. | Đo workload đại diện. |
| “Dùng SSD/remote filesystem làm backing luôn an toàn như DRAM.” | Không cùng memory/atomicity/device semantics. | Chỉ dùng môi trường hỗ trợ và đã được kiểm chứng. |

## 18. Bài tập thực hành và đáp án

### Bài 1 — `AllocateHeapAt` thay đổi gì?

**Hỏi:** Nó thay câu lệnh `new` trong code Java không?

**Đáp án:** Không. HotSpot thay đổi cách backing **object heap** ở tầng runtime. Code Java dùng `new` như bình thường.

### Bài 2 — Mapped file khác DAX ra sao?

**Hỏi:** Một JVM tạo được writable file mapping dưới `/tmp`. Có chứng minh nó dùng NV-DIMM không?

**Đáp án:** Không. File-backed mmap thông thường có thể dùng DRAM/page cache. DAX cần device và filesystem thực sự hỗ trợ, được kiểm chứng riêng.

### Bài 3 — Heap có bền vững không?

**Hỏi:** JVM chạy trên non-volatile media, sau khi restart có tự lấy lại các Java objects không?

**Đáp án:** Không. `AllocateHeapAt` không cung cấp object-graph serialization, transaction recovery hoặc stable reference semantics qua các JVM lifetimes.

### Bài 4 — Metaspace ở đâu?

**Hỏi:** Có thể kết luận mọi class metadata nằm trong NV-DIMM vì `AllocateHeapAt` đang bật?

**Đáp án:** Không. Oracle docs phân biệt Java object heap với metaspace/code heap/thread stacks, vốn không tự chuyển theo cờ này.

### Bài 5 — `-Xmx` có còn áp dụng?

**Hỏi:** Nếu dùng `-XX:AllocateHeapAt=/mnt/pmem-heap` thì `-Xmx4g` còn có ý nghĩa không?

**Đáp án:** Có. Heap-related flags vẫn có ngữ nghĩa khi JVM dùng alternative heap backing phù hợp.

### Bài 6 — Memory mapping có nghĩa load toàn bộ file vào RAM?

**Đáp án:** Không. Memory mapping tạo virtual address range. Resident physical pages và đường backing phụ thuộc OS/filesystem/memory device.

### Bài 7 — Khi nào cần `S_DAX`?

**Hỏi:** Một filesystem hỗ trợ DAX nhưng chưa biết file backing có bật DAX hay chưa. Nên kiểm tra gì?

**Đáp án:** Xem trạng thái DAX hiệu dụng trên inode, ví dụ `S_DAX`/`STATX_ATTR_DAX` theo tài liệu kernel, và hardware/underlying-device support.

### Bài 8 — File không thấy trong directory?

**Hỏi:** `/proc/<pid>/maps` có dòng file-backed `(deleted)` nhưng `ls` không thấy file. Có nghĩa JVM không map thành công?

**Đáp án:** Không. JVM có thể mở rồi unlink backing file, trong khi OS vẫn giữ mapping tới khi process kết thúc.

### Bài 9 — Hai process dùng chung `AllocateHeapAt` path?

**Đáp án:** Không tự có shared Java heap. Mỗi JVM có GC/object graph riêng; cùng filesystem path chỉ là nơi cấp backing resource.

### Bài 10 — `FileChannel.map` so với `AllocateHeapAt`?

**Đáp án:** `FileChannel.map` tạo một mapped buffer được ứng dụng quản lý cho file cụ thể, không chuyển toàn bộ các objects trong Java heap. `AllocateHeapAt` là cờ VM đặt heap backing.

### Bài 11 — DAX có bỏ CPU cache không?

**Đáp án:** Không. DAX nhằm tránh bản sao page cache thông thường; CPU hardware caches và coherence vẫn có vai trò.

### Bài 12 — Thiết bị nhanh hay chậm hơn?

**Hỏi:** Có thể kết luận heap trên PMem luôn nhanh hơn DRAM chỉ từ việc bỏ page cache?

**Đáp án:** Không. Latency/bandwidth/NUMA/GC và workload quyết định. Benchmark đúng môi trường mới có kết luận.

### Bài 13 — Đo heap used bằng gì?

**Hỏi:** Có thể lấy `/proc/<pid>/maps` rồi tính tổng object bytes còn sống không?

**Đáp án:** Không. Maps mô tả virtual mappings. GC logs/JFR/heap dump phù hợp hơn để phân tích objects; OS metrics để phân tích placement/residency.

### Bài 14 — Directory filesystem đầy?

**Hỏi:** Trình khởi chạy dùng `AllocateHeapAt` nhưng filesystem không còn dung lượng. Nên tự fallback silently sang DRAM?

**Đáp án:** Không nên giả định fallback. Kiểm tra exit code/JVM logs, dung lượng, quota, quyền và mapping support; xử lý theo deployment policy, không coi startup thành công được bảo đảm.

### Bài 15 — Cú pháp DAX cũ

**Hỏi:** Vì sao không nên lấy `-o dax` từ tài liệu cũ làm hướng dẫn mount chuẩn cho mọi ext4/XFS mới?

**Đáp án:** Linux Kernel docs hiện hành đánh dấu đó là alias legacy của `dax=always` có thể bị bỏ. Dùng policy phù hợp kernel/filesystem, kiểm tra trạng thái DAX thực của inode.

### Bài 16 — Kết quả Java giống nhau?

**Hỏi:** Demo in cùng checksum 20 với heap thường và heap mapped. Có mâu thuẫn không?

**Đáp án:** Không. `AllocateHeapAt` là tối ưu/chọn placement ở tầng VM, không được thay đổi ngữ nghĩa của phép tính Java. Muốn xác minh placement phải kiểm tra OS mappings, và muốn xác minh DAX phải kiểm tra filesystem/device.

## 19. Checklist trước khi triển khai

- [ ] Tôi đã xác minh **JDK vendor, build, OS, architecture, collector** và hỗ trợ `AllocateHeapAt`.
- [ ] Tôi hiểu đây là tùy chọn HotSpot có từ Java 10, vẫn được Oracle Java SE 25 mô tả.
- [ ] Tôi biết path là nơi HotSpot có thể tạo backing file, không phải một serialized object snapshot.
- [ ] Tôi không coi một directory có tên `pmem` là bằng chứng thiết bị PMem thật.
- [ ] Tôi đã xác minh **memory-like semantics**, gồm atomic operations mà JVM cần.
- [ ] Tôi đã kiểm tra underlying device, filesystem, mount options và DAX inode state.
- [ ] Tôi không đánh đồng ordinary file mapping với DAX.
- [ ] Tôi không dùng mount option `-o dax` legacy như lời khuyên mặc định.
- [ ] Tôi đã phân quyền directory và có đủ dung lượng/quota phù hợp heap.
- [ ] Tôi có chính sách bảo mật cho dữ liệu heap/secrets còn lưu trên media.
- [ ] Tôi hiểu unlink file không đồng nghĩa secure erase.
- [ ] Tôi không hy vọng Java objects tự sống qua JVM restart.
- [ ] Tôi không nhầm Java object heap với metaspace, JIT code cache, threads hoặc native buffers.
- [ ] Tôi vẫn áp dụng `-Xms`, `-Xmx` và GC settings theo bản JVM phù hợp.
- [ ] Tôi đã chạy ứng dụng với **heap mặc định** và **mapped heap** để so chức năng.
- [ ] Tôi đã kiểm tra `/proc/<pid>/maps` hoặc công cụ OS tương đương khi cần xác minh placement.
- [ ] Tôi không lấy `ls` một mình làm bằng chứng không có backing file.
- [ ] Tôi không suy ra memory placement từ stdout/`Runtime.maxMemory()`.
- [ ] Tôi không sử dụng `FileChannel.map`, FFM hay CDS để thay cho tính năng đặt Java heap.
- [ ] Tôi đã benchmark startup, throughput, GC pauses, memory footprint và NUMA/latency.
- [ ] Tôi đã ghi lại lỗi khởi động, quota, mapping support và kế hoạch rollback.
- [ ] Tôi không làm thay đổi dữ liệu/format của physical device khi chỉ đang học tính năng Java.

## 20. Tài liệu tham khảo còn hiệu lực

1. [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): mốc Java 10, thiết bị bộ nhớ thay thế và lý do sử dụng file-backed heap.
2. [Oracle Java SE 25 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp flag hiện hành, memory mapping của object heap, thiết bị có DRAM-like semantics, các vùng bộ nhớ JVM khác và sự tương thích `-Xms/-Xmx`/GC.
3. [OpenJDK mainline — java launcher manual](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): định nghĩa `AllocateHeapAt` tiếp tục có mặt trong manpage nguồn của OpenJDK.
4. [Linux Kernel — Direct Access for files](https://docs.kernel.org/filesystems/dax.html): DAX và page cache, device support, ext4/XFS DAX policy, `S_DAX`/`STATX_ATTR_DAX`, lưu ý `-o dax` legacy.
5. [Linux Kernel — proc_pid_maps](https://www.man7.org/linux/man-pages/man5/proc_pid_maps.5.html): đọc virtual address mappings, quyền, pathnames và `(deleted)`.
6. [Oracle Java SE 25 — FileChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html): `map` tạo mapped buffer riêng, khác VM-managed Java heap.
7. [Oracle Java SE 25 — Runtime.maxMemory()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#maxMemory()): max Java heap không phải physical device/cgroup measurement.
8. [Oracle Java SE 25 — Native Memory Tracking and Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các công cụ chẩn đoán JVM/GC, không thay xác minh DAX của kernel.
9. [NVDIMM Linux documentation](https://nvdimm.docs.kernel.org/): filesystem và thiết bị bộ nhớ bền vững, hỗ trợ DAX trong môi trường Linux.
10. [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): các memory segments của Java hiện đại, cần phân biệt với placement của GC-managed heap.

**Kết luận:** **`-XX:AllocateHeapAt=path`** cho phép HotSpot (từ Java 10/JEP 316 và vẫn được mô tả trong Java SE 25) dùng **memory mapping qua filesystem** làm backing cho **Java object heap** trong môi trường hỗ trợ. Điều kiện quan trọng là **filesystem, OS và device có memory access semantics phù hợp**, chứ không phải tên directory có chữ `pmem`. Một vùng `rw-s` trong `/proc/<pid>/maps` có thể chứng minh file-backed mapping, nhưng **không tự chứng minh DAX, NV-DIMM hoặc persistence**. `-Xms/-Xmx` và GC vẫn có ý nghĩa, các vùng metaspace/code cache/thread stacks không tự chuyển theo. Java objects **không tự tồn tại qua restart** và không trở thành database. Trước khi dùng thật, cần xác minh DAX/device, quyền, dung lượng, security và benchmark trên phần cứng/runtime mục tiêu.