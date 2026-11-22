# Tùy chọn -XX:AllocateHeapAt và đường dẫn thiết bị — Java 10+

## 1. Vấn đề: vì sao muốn đặt Java object heap trên một loại bộ nhớ khác?

Một ứng dụng Java dùng **Java heap** để chứa phần lớn các object được cấp phát bằng `new`. Ở cấu hình thông thường, bộ nhớ vật lý hậu thuẫn heap được hệ điều hành cấp từ RAM và các chính sách virtual memory của máy. Trong một số hệ thống chuyên biệt, quản trị viên có **thiết bị bộ nhớ thay thế** được ánh xạ vào không gian địa chỉ, ví dụ vùng **persistent memory (PMEM/NVDIMM)** hỗ trợ cơ chế truy cập thích hợp. Nhóm thiết bị này có thể cung cấp dung lượng lớn hoặc đặc tính chi phí/độ trễ khác DRAM.

Từ **Java 10**, **JEP 316 — Heap Allocation on Alternative Memory Devices** cho phép HotSpot JVM đặt **Java object heap** trên một vùng nhớ thay thế được hệ điều hành trình bày qua **file system**, bằng một tùy chọn khởi động:

```text
-XX:AllocateHeapAt=<path>
```

Đây là **cờ JVM**, không phải một lời gọi API Java. Một chương trình Java sử dụng collection, record, object, array hoặc thư viện thông thường **không phải sửa mã** chỉ vì heap được đặt trên một thiết bị đáp ứng đúng ngữ nghĩa bộ nhớ mà JVM yêu cầu.

**Thông điệp quan trọng:** `-XX:AllocateHeapAt=/mnt/pmem` không có nghĩa “JVM dùng toàn bộ thiết bị /dev/pmem0”, cũng không có nghĩa “Java objects được lưu bền vững, có thể phục hồi sau restart”. Nó yêu cầu HotSpot **tạo một vùng ánh xạ file-backed cho object heap** tại **đường dẫn file system** được chỉ định. Muốn thực sự dùng bộ nhớ thay thế, thư mục đó phải nằm trên một filesystem/mount được cấu hình đúng với thiết bị và khả năng direct mapping tương ứng.

Cờ `-XX:AllocateHeapAt` **vẫn có mặt trong tài liệu lệnh `java` của Oracle JDK 25 và 27**, vì vậy đây không phải kiến thức đã bị loại bỏ. Tuy nhiên, việc dùng được trên từng OS, filesystem, CPU architecture, collector và JDK distribution **phải được xác minh**, không tự suy từ một trang tài liệu chung.

### Mục tiêu của bài

Sau bài này, bạn sẽ biết:

1. Đọc đúng cú pháp `-XX:AllocateHeapAt=<path>` và hiểu `path` là gì.
2. Phân biệt **đường dẫn tới thư mục mount** với **raw device path** và đường dẫn heap dump.
3. Hiểu vai trò `mmap`, file backing và **filesystem DAX**.
4. Biết yêu cầu quan trọng về **ngữ nghĩa truy cập như DRAM**, kể cả các thao tác atomic.
5. Xác định phần nào của JVM có thể ở thiết bị thay thế và phần nào vẫn cần DRAM.
6. Kết hợp cờ với `-Xms`, `-Xmx` và GC theo tài liệu bản JDK đang chạy.
7. Nhận ra lỗi đường dẫn không tồn tại, không thể ghi, hết dung lượng hoặc filesystem không phù hợp.
8. Kiểm chứng cấu hình bằng Java code, Linux `/proc/<pid>/maps` và thông tin mount thực tế.
9. Phân biệt việc **đã mmap heap** với việc **đã thật sự dùng bộ nhớ DAX/PMEM**.
10. Hiểu vì sao persistent memory **không tự biến Java heap thành persistent object database**.
11. Đánh giá capacity, độ trễ, GC, bảo mật và triển khai trên container.
12. Lựa chọn khi nào nên dùng và khi nào nên giữ heap mặc định trên hệ thống hiện đại.

## 2. JEP 316 thay đổi gì?

**JEP 316** được đưa vào **JDK 10** với mục tiêu cho phép HotSpot JVM **cấp phát Java object heap trên thiết bị bộ nhớ thay thế do người vận hành chỉ định**. Một trường hợp được thiết kế hướng tới là thiết bị **NV-DIMM**, khi OS cung cấp cơ chế để CPU truy cập các byte của thiết bị bằng load/store thông thường.

Ý tưởng không phải viết lại Java garbage collector để thao tác với disk block I/O theo từng object, mà là để **hệ điều hành ánh xạ file thành virtual memory**. JVM có thể tiếp tục thao tác với object references và heap address space theo hợp đồng bộ nhớ Java.

### Không phải mọi “thiết bị lưu trữ” đều đủ điều kiện

Cần phân biệt:

| Loại tài nguyên | Có ý nghĩa gì? | Có thể tự coi là Java heap alternative-memory chuẩn không? |
| --- | --- | --- |
| **DRAM thông thường** | RAM do kernel quản lý | Cấu hình mặc định; không cần AllocateHeapAt |
| **PMEM/NVDIMM có hỗ trợ direct access** | Vùng bộ nhớ được CPU truy cập qua memory mapping thích hợp | **Ứng viên**, khi OS/filesystem/JVM hỗ trợ và có ngữ nghĩa như DRAM |
| **DAX-capable filesystem được mount trên PMEM** | Cho phép tạo file và ánh xạ nội dung file vào vùng nhớ trực tiếp | Thường là cách cung cấp `path` cho cờ |
| **SSD/HDD có filesystem bình thường** | Lưu file qua page cache, I/O và paging | Không tương đương direct-access PMEM, dù JVM có thể mmap file |
| **Raw block device `/dev/pmem0`** | Đường dẫn thiết bị cấp block, chưa phải một mountpoint directory | **Không** tự coi là tham số thư mục của cờ |
| **Device-DAX character device `/dev/daxN.M`** | Device mapping không thông qua filesystem | Là loại khác filesystem DAX; không dùng thay mount directory một cách máy móc |
| **Java heap dump file** | Snapshot để điều tra object | Không phải vùng heap runtime mà AllocateHeapAt quản lý |
| **MappedByteBuffer của ứng dụng** | Vùng map riêng được lập trình viên tạo | Không phải việc chuyển toàn bộ JVM object heap |

Điều kiện quan trọng: thiết bị thay thế phải có **ngữ nghĩa bộ nhớ tương đương DRAM, bao gồm atomic memory operations**, để VM giữ đúng ngữ nghĩa của Java. Việc một thiết bị “đọc ghi được như file” **không đủ** để kết luận phù hợp.

## 3. Cú pháp -XX:AllocateHeapAt

Cú pháp theo tài liệu Oracle:

```text
-XX:AllocateHeapAt=<path>
```

Ví dụ trên Linux, **giả sử quản trị viên đã chuẩn bị một filesystem được mount** tại `/mnt/pmem`:

```bash
java -XX:AllocateHeapAt=/mnt/pmem -Xms1g -Xmx4g -jar app.jar
```

Giải thích:

- `-XX:AllocateHeapAt=/mnt/pmem`: yêu cầu dùng filesystem path này để làm nơi đặt backing mapping của Java object heap.
- `-Xms1g`: quy mô heap ban đầu theo quy tắc JVM.
- `-Xmx4g`: giới hạn heap tối đa mà JVM được phép dùng theo quy tắc bình thường.
- `-jar app.jar`: khởi chạy ứng dụng.
- Các `-XX:...` và `-X...` nằm **trước** `-jar` để launcher nhận chúng là tùy chọn JVM.

**Điều kiện tiên quyết:** `/mnt/pmem` phải **tồn tại, có thể ghi, đủ dung lượng phù hợp và thực sự trỏ tới filesystem backing mong muốn**. Đoạn lệnh chỉ là **ví dụ cấu hình**, không phải minh chứng máy đang dùng PMEM thật.

### Path nên trỏ tới đâu?

Trong quy trình của JEP 316, một ví dụ điển hình là **thư mục mount** của filesystem đặt trên vùng PMEM:

```text
/dev/pmem0   --(được cấu hình, tạo filesystem, mount bởi admin)-->
/mnt/pmem    --(filesystem path của JVM)-->
-XX:AllocateHeapAt=/mnt/pmem
```

Không được suy từ sơ đồ rằng bạn có thể chạy trực tiếp:

```bash
# KHÔNG nên coi raw device là mount directory:
java -XX:AllocateHeapAt=/dev/pmem0 -jar app.jar
```

Cách cấp phát theo cờ này **dựa trên thao tác file/memory mapping từ đường dẫn filesystem**; raw device và filesystem DAX là hai cách trình bày tài nguyên khác nhau. Các bước quản trị thiết bị/mount do người quản lý hạ tầng thực hiện theo **tài liệu kernel và nhà cung cấp**; bài không khuyến nghị chạy `mkfs` hay thay partition trên thiết bị thật chỉ để học một VM option.

### Path là tùy chọn khởi động, không thể thay tuỳ ý khi JVM đã chạy

HotSpot cần quyết định nơi backing Java heap **trong giai đoạn khởi tạo JVM**. Bạn không thể dùng:

```java
System.setProperty("AllocateHeapAt", "/mnt/pmem");
```

rồi mong toàn bộ heap đang chạy được chuyển thiết bị. Đây không phải một Java system property, và việc thay `java.io.tmpdir` cũng **không** tương đương.

Nếu cần chuyển đường dẫn heap, thông thường phải **thay tham số startup và restart JVM**, đồng thời kiểm tra rằng JDK/collector/chế độ triển khai hỗ trợ cấu hình mới.

## 4. Memory mapping, DAX và đường đi của dữ liệu

### 4.1. Memory mapping là gì?

Khi JVM có file backing trên một filesystem phù hợp, nó yêu cầu OS **map file vào virtual address space**. Các lệnh đọc/ghi Java heap cuối cùng được thực hiện trên vùng địa chỉ bộ nhớ này.

```text
Java source: new Customer(...)
        |
        v
HotSpot allocates Java object in heap virtual address range
        |
        v
Operating system maps heap backing file
        |
        +--> filesystem/mount specified by AllocateHeapAt
                    |
                    +--> underlying memory device
                         (PMEM/NVDIMM if actually configured)
```

Điểm cần tránh: Java object **không được serialize thành một file mỗi khi tạo**; JVM vẫn sử dụng cấu trúc object/headers/references bình thường của HotSpot.

### 4.2. DAX có ý nghĩa gì?

**DAX (Direct Access)** là các cơ chế để những file trên filesystem phù hợp có thể **được memory-map trực tiếp vào thiết bị bộ nhớ**, tránh đường đi qua page cache theo cách thông thường. Trên Linux, một số filesystem như ext4/XFS có những chế độ DAX phụ thuộc kernel, loại namespace PMEM và cấu hình filesystem.

**Không suy rằng một thư mục tên `/mnt/pmem` chắc chắn đang DAX.** Tên thư mục có thể là bất cứ thứ gì; muốn biết thật, kiểm tra nguồn mount, chế độ filesystem và trạng thái DAX của file trên OS/JDK tương ứng.

### 4.3. Nếu trỏ vào filesystem thông thường?

Trên một JVM Linux, một thư mục hợp lệ trên filesystem bình thường **có thể được dùng làm nơi tạo memory-mapped backing file**, nhưng cơ chế đó **không chứng minh** dữ liệu nằm trên alternative physical memory.

Nếu filesystem không cung cấp direct mapping tới PMEM, OS có thể dùng page cache và I/O/paging theo quy tắc thông thường. Việc đặt `-XX:AllocateHeapAt` trong trường hợp này **không tự giúp tăng dung lượng RAM vật lý hay bảo đảm tăng hiệu năng**.

Vì vậy cần hai phép kiểm tra độc lập:

1. **JVM đã dùng path và tạo memory mapping cho heap chưa?**
2. **Path thực sự thuộc DAX-capable PMEM device và direct mapping đã có hiệu lực chưa?**

Chỉ câu thứ nhất không đủ để trả lời câu thứ hai.

## 5. Những cấu trúc JVM nào được đặt ở thiết bị thay thế?

Theo tài liệu Oracle JDK hiện hành, cờ này hướng tới **Java object heap**. Các cấu trúc bộ nhớ JVM khác **vẫn tiếp tục dùng DRAM** như cấu hình thông thường.

| Loại dữ liệu/bộ nhớ | Vai trò | Tác động trực tiếp của AllocateHeapAt |
| --- | --- | --- |
| **Java object heap** | Chứa object/array được JVM quản lý bởi GC | **Có**, đây là phạm vi mục tiêu |
| **JIT code cache/code heap** | Mã máy được biên dịch bởi JIT compiler | **Không**, tiếp tục dùng bộ nhớ riêng thường ở DRAM |
| **Metaspace** | Metadata class/runtime | **Không** trực tiếp chuyển theo object heap |
| **Java thread stacks** | Frames, local variables, return addresses | **Không** trực tiếp chuyển sang thiết bị heap |
| **Native/JNI memory** | Bộ nhớ do native libraries cấp phát | **Không** được cờ này tự chuyển |
| **DirectByteBuffer/off-heap memory** | Vùng native/direct do thư viện/API quản lý | **Không** được cờ này tự chuyển |
| **GC/native bookkeeping** | Dữ liệu phụ trợ của VM, runtime structures | **Không** bảo đảm mọi byte ở cùng thiết bị với Java heap |
| **MappedByteBuffer do app tạo** | Mapping do Java NIO thực hiện | Phụ thuộc path/Options của riêng app, không phải cờ này |

**Kết luận thực tế:** JVM vẫn cần đủ **DRAM và native-memory headroom**, ngay cả khi object heap được đặt trên một thiết bị khác. Không thể lấy số `-Xmx4g` để khẳng định tiến trình chỉ dùng 4 GiB tổng memory, và cũng không thể coi việc đặt heap trên PMEM là giải pháp cho mọi `OutOfMemoryError`.

### Đừng nhầm với -XX:MaxDirectMemorySize

`-XX:MaxDirectMemorySize` liên quan đến các direct-buffer allocations theo quy tắc riêng. Nó **không** cấu hình vị trí Java object heap và không phải công tắc chọn PMEM.

### Đừng nhầm với HeapDumpPath

`-XX:HeapDumpPath` (khi sử dụng cùng công cụ heap dump phù hợp) điều khiển đường dẫn **file dump để chẩn đoán**. `-XX:AllocateHeapAt` điều khiển **heap backing khi JVM đang chạy**. Hai đường dẫn khác nhau, không thay thế được nhau.

## 6. -Xms, -Xmx và GC vẫn giữ ý nghĩa như trước

JEP 316 không yêu cầu chương trình Java thay đổi kiểu object hay buộc garbage collector dùng một format heap khác.

Trong tài liệu Oracle:

- `-Xms`: điều khiển **initial/minimum heap size** theo các quy tắc JVM.
- `-Xmx`: giới hạn **maximum Java heap size**.
- Các tùy chọn GC tiếp tục giữ ngữ nghĩa chung theo collector và JDK được sử dụng.
- Việc đặt heap trên thiết bị khác **không bảo đảm** garbage collection nhanh hơn hoặc tương thích với mọi collector/tuning flag trên mọi build.

Ví dụ:

```bash
java -XX:AllocateHeapAt=/mnt/pmem \
     -Xms512m -Xmx2g \
     -XX:+UseG1GC \
     -Xlog:gc=info \
     -jar app.jar
```

Lệnh giả định JVM có thể sử dụng `/mnt/pmem` và hỗ trợ tổ hợp option đó. Nếu tập flags/collector không hợp lệ với build hiện tại, phải xử lý theo thông báo khởi động, **không ép bỏ qua lỗi để giả vờ đã dùng PMEM**.

### Không dùng cờ này như một phương thuốc cho mọi GC pause

- PMEM có latency/bandwidth khác DRAM; scan/copy/evacuation heap có thể gặp tradeoff.
- GC vẫn cần quét dữ liệu sống, reclaim bộ nhớ, dọn các object unreachable.
- Một Java heap rất lớn có thể làm **live-set** và một số công việc GC tốn thời gian hơn.
- Heap trên bộ nhớ khác không sửa lỗi giữ object references, cache tăng không giới hạn hoặc allocation pressure.
- Không tăng `-Xmx` chỉ vì có thể cấp heap trên PMEM mà bỏ qua CPU/GC cost.

Sự phù hợp của một GC collector với placement này phải được kiểm tra trên **JDK thực tế** và workload tương tự production.

## 7. Đường dẫn thiết bị: chuẩn bị và kiểm tra an toàn trên Linux

Để dùng thực tế, quản trị viên hạ tầng phải chuẩn bị:

1. Thiết bị bộ nhớ/namespace được OS nhận diện và có **memory semantics phù hợp**.
2. Filesystem hỗ trợ cơ chế DAX tương ứng và được mount đúng cách.
3. Một **directory** dùng riêng cho JVM heap backing, ví dụ `/mnt/pmem/java-heaps`.
4. Đường dẫn có quyền đọc/ghi phù hợp với **user chạy JVM**.
5. Dung lượng/khả năng cấp phát vật lý đáp ứng heap size và các overhead liên quan.
6. Chính sách bảo mật với dữ liệu nhạy cảm có thể đi qua thiết bị.
7. Giám sát capacity, filesystem errors, device health và dự phòng khởi động nếu device không khả dụng.

Có thể kiểm tra **mà không thay dữ liệu**:

```bash
# Thư mục phải tồn tại:
test -d /mnt/pmem/java-heaps

# Process user chạy JVM cần có quyền ghi:
test -w /mnt/pmem/java-heaps

# Hỏi OS filesystem/mount thực tế:
findmnt -T /mnt/pmem/java-heaps

# Kiểm tra dung lượng và filesystem:
df -h /mnt/pmem/java-heaps
```

**Những kiểm tra này là điều kiện cần nhưng chưa đủ.** `test -w` và `df` không kiểm tra toàn bộ mmap semantics, DAX status hoặc các điều kiện atomic memory access. Với hệ thống PMEM, hãy đối chiếu thêm tài liệu Linux kernel/vendor, namespace mode và cấu hình filesystem DAX hiện hành.

### Filesystem DAX khác Device DAX

Theo Linux NVDIMM documentation:

- **fsdax** cho phép một filesystem như ext4/XFS dùng PMEM và cung cấp direct access cho file mapping khi thiết lập phù hợp.
- **devdax** trình bày một character device để phần mềm có thể trực tiếp mmap device theo hợp đồng riêng, **không phải filesystem thông thường**.

Với tùy chọn dựa trên **filesystem path** như `AllocateHeapAt`, điểm mount directory là biểu diễn phù hợp với mô hình mô tả. Không tự thay `/mnt/pmem/java-heaps` bằng `/dev/dax0.0` khi chưa có tài liệu JVM triển khai cho đường đó.

### Cách trình bày mount thay đổi qua kernel

Trên hệ thống Linux mới, DAX có thể được cấu hình theo inode/mount policy; Red Hat Enterprise Linux hiện đại có những chế độ DAX khác nhau. Vì vậy không chỉ dựa vào sự hiện diện của một chữ `dax` trong một lệnh mount cũ để tuyên bố đã direct mapped. Cần kiểm tra **filesystem/OS documentation đúng phiên bản** và trạng thái DAX áp dụng cho file thực.

## 8. JVM làm gì với backing file? Có để lại file sau khi thoát không?

Cờ `AllocateHeapAt` không có nghĩa bạn cần tự tạo một file heap cố định và nhập dữ liệu vào đó. Trong implementation HotSpot/Linux, JVM có thể **tạo một file hoặc anonymous file trong directory được chỉ định**, sau đó memory-map file ấy để dùng làm backing của Java heap.

Ví dụ mapping có thể trông như:

```text
/mnt/pmem/java-heaps/#<inode> (deleted)
```

hoặc một định dạng tên tạm khác, tùy JDK/kernel/filesystem. Từ `(deleted)` trong `/proc/<pid>/maps` có thể cho biết path entry đã được unlink trong khi mapping vẫn tồn tại. Điều đó **không** có nghĩa heap đã biến mất khi JVM còn dùng mapping.

Trong một phép thử OpenJDK 21/Linux với **thư mục filesystem bình thường** (không phải thiết bị PMEM), sau khi JVM kết thúc, thư mục thử nghiệm rỗng; trong lúc JVM chạy, `/proc/<pid>/maps` cho thấy file mapping gắn với thư mục đó. Đây là một ví dụ của cách backing file có thể được quản lý, **không phải hợp đồng về tên file tạm hoặc dữ liệu sẽ luôn bị xóa an toàn trong mọi tình huống**.

### Không mở file đó làm dữ liệu nghiệp vụ

Không dùng file backing của HotSpot như một định dạng persistent database, không ghi tay vào nó và không mong JVM mới có thể phục hồi object graph của JVM cũ từ file này. Heap có references, object headers, JIT/GC/runtime metadata và trạng thái tiến trình; không có hợp đồng Java SE cho phép deserialize heap bằng cách map lại file sau restart.

## 9. Persistent memory không tự cho persistent Java objects

Đây là một trong các khác biệt quan trọng nhất.

- **Bộ nhớ vật lý non-volatile:** có thể giữ các bit qua mất điện theo đặc tính thiết bị.
- **Java object heap:** được JVM quản lý **trong vòng đời tiến trình**, với references/GC và cấu trúc nội bộ.
- **Persistent Java application state:** cần thiết kế giao dịch, serialization, database hoặc hệ thống lưu trữ có hợp đồng khôi phục riêng.

Do đó:

```text
-XX:AllocateHeapAt=/mnt/pmem
      !=
Tự động khôi phục các Java objects sau khi JVM tắt/mất điện
```

Ngay cả khi các bit trên PMEM tồn tại, JVM **không bảo đảm** object references, atomicity của toàn transaction, tính nhất quán sau crash, class definitions hay runtime metadata có thể được tái dựng an toàn chỉ từ backing file.

### Những rủi ro bảo mật đi kèm

- Dữ liệu nhạy cảm trong object heap có thể tồn tại trên medium có khả năng giữ dữ liệu.
- Việc unlink một backing file không đồng nghĩa luôn **xóa vật lý an toàn** các byte trong thiết bị non-volatile.
- Cần giới hạn quyền truy cập mount, bảo vệ file system, kiểm soát access của user/container khác.
- Nếu workload chứa secret, credential, personal data, cần một chính sách bảo vệ/khử dữ liệu phù hợp thiết bị và threat model.
- Không chia sẻ directory không an toàn giữa các tenant rồi mặc định dữ liệu không thể bị truy cập qua hệ thống tệp.

Đây là trách nhiệm vận hành của thiết bị và hệ thống, không phải một bảo đảm phát sinh từ JVM flag.

## 10. Ví dụ Java 17+ hoàn chỉnh: không thay đổi code khi đổi heap backing

Ta tạo một chương trình Java nhỏ **không biết** nơi object heap thực sự nằm. Cùng chương trình có thể chạy:

- Với heap mặc định.
- Với flag `-XX:AllocateHeapAt` trỏ tới một directory có thể mmap.
- Với directory được mount trên PMEM thực, nếu hệ điều hành và JDK hỗ trợ.

Điều này minh họa điểm chính của JEP 316: **mã cấp phát object của ứng dụng không cần thay đổi**.

Tạo file **`HeapPlacementDemo.java`**:

```java
public final class HeapPlacementDemo {
    private static volatile byte[][] keepAlive;

    public static void main(String[] args) throws InterruptedException {
        byte[][] blocks = new byte[4][];
        int checksum = 0;
        for (int i = 0; i < blocks.length; i++) {
            blocks[i] = new byte[256 * 1024];
            blocks[i][0] = (byte) (i + 1);
            blocks[i][blocks[i].length - 1] = (byte) (i + 2);
            checksum += blocks[i][0] + blocks[i][blocks[i].length - 1];
        }
        keepAlive = blocks;

        System.out.println("blocks=" + keepAlive.length);
        System.out.println("allocatedBytes=" +
                (keepAlive.length * 256 * 1024));
        System.out.println("checksum=" + checksum);
        System.out.println("maxHeapAtLeast32MiB=" +
                (Runtime.getRuntime().maxMemory() >=
                        32L * 1024 * 1024));

        long waitMillis = Long.getLong("demo.waitMillis", 0L);
        if (waitMillis > 0) {
            Thread.sleep(waitMillis);
        }

        System.out.println("finished=true");
    }
}
```

### Biên dịch

```bash
javac --release 17 HeapPlacementDemo.java
```

Chương trình chỉ dùng Java SE API đã ổn định, có thể biên dịch bằng JDK hỗ trợ target Java 17.

### Chạy bình thường

```bash
java -Xms32m -Xmx64m HeapPlacementDemo
```

**Stdout chính xác đã được kiểm chứng bằng cách chạy trên OpenJDK 21/Linux:**

```text
blocks=4
allocatedBytes=1048576
checksum=24
maxHeapAtLeast32MiB=true
finished=true
```

Giải thích:

- Có 4 mảng, mỗi mảng có 256 KiB, tổng được code yêu cầu cấp phát là **1.048.576 byte**.
- `checksum=24` vì mỗi mảng ghi hai byte `i+1` và `i+2`, với `i=0..3`.
- `maxHeapAtLeast32MiB=true` là phép kiểm tra tương đối theo `-Xmx64m`, không khẳng định `maxMemory()` **luôn bằng chính xác 64 MiB** trên mọi GC/JDK.
- `volatile keepAlive` giữ tham chiếu tới các mảng qua phần chạy demo.
- Khi không có property chờ, chương trình kết thúc ngay.

### Chạy với heap backing filesystem

**Trước khi chạy**, hãy chọn một directory đang có và cho phép ghi. Ví dụ trên máy thử Linux, dùng một directory tạm **không phải PMEM** chỉ để kiểm chứng parser/VM mapping.

```bash
mkdir -p /tmp/heap-placement-test

java -XX:AllocateHeapAt=/tmp/heap-placement-test \
     -Xms32m -Xmx64m \
     HeapPlacementDemo
```

**Kết quả đã kiểm chứng trên OpenJDK 21/Linux** với một directory filesystem hợp lệ:

```text
blocks=4
allocatedBytes=1048576
checksum=24
maxHeapAtLeast32MiB=true
finished=true
```

**Đây không phải bài benchmark PMEM.** Vì directory trong phép thử chỉ thuộc filesystem thông thường, chương trình thành công **chứng minh VM nhận flag và dùng một file-backed mapping hợp lệ**, không chứng minh có thiết bị NV-DIMM, filesystem DAX hoặc hiệu quả latency tốt hơn.

Khi muốn thử trên thiết bị thực, **thay** `/tmp/heap-placement-test` bằng directory mount do quản trị viên xác nhận:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/java-heaps \
     -Xms32m -Xmx64m \
     HeapPlacementDemo
```

Lệnh cuối cùng là **minh họa có điều kiện**, không phải lệnh đã được chạy trên thiết bị PMEM trong phép thử.

## 11. Kiểm tra mapping thực tế bằng /proc/<pid>/maps trên Linux

Java SE không có một API chuẩn trả về “loại thiết bị vật lý mà object heap đang dùng”. In `Runtime.getRuntime().maxMemory()` **không chứng minh** heap đã nằm trên PMEM.

Trên Linux, có thể quan sát **memory mappings** của tiến trình từ `/proc/<pid>/maps`. Chương trình ví dụ hỗ trợ một property để chờ trong một khoảng ngắn:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/java-heaps \
     -Xms32m -Xmx64m \
     -Ddemo.waitMillis=10000 \
     HeapPlacementDemo &
pid=$!

sleep 1
grep -F '/mnt/pmem/java-heaps' /proc/$pid/maps

wait "$pid"
```

**Điều kiện:** directory `/mnt/pmem/java-heaps` đã sẵn sàng và JVM được cấp quyền; lệnh này là ví dụ cho **Linux shell**, không phải PowerShell/Windows.

Nếu JVM thật sự mmap heap qua path đó, maps có thể hiện một hoặc nhiều vùng với directory đích, chẳng hạn:

```text
... rw-s ... /mnt/pmem/java-heaps/#<inode> (deleted)
```

Trong phép thử Linux với directory tạm, đã quan sát các vùng `rw-s` có tên directory đó; khi process kết thúc, bản đồ memory cũng biến mất. **Tên inode và số địa chỉ không cố định**, đừng viết parser dựa trên các số này.

### Vì sao cần kiểm tra thêm mount?

`/proc/<pid>/maps` xác nhận **đường dẫn file mapping**, không tự xác nhận backend là NV-DIMM/PMEM. Cần kết hợp:

```bash
findmnt -T /mnt/pmem/java-heaps
df -h /mnt/pmem/java-heaps
```

và công cụ quản trị PMEM/FS DAX theo OS version. Nếu chỉ dùng `/tmp` bình thường, kết quả có mapping **không** làm `/tmp` trở thành persistent memory.

### Nếu ứng dụng chạy trong container

Quan sát mapping **trong cùng namespace phù hợp**. Host và container có thể nhìn đường dẫn khác nhau do mount namespaces. Directory `/mnt/pmem` bên trong container không nhất thiết tồn tại hoặc tương ứng đúng thiết bị trên host. Nếu chỉ test ngoài container, kết luận chưa áp dụng cho deployment thực.

## 12. Điều gì xảy ra khi đường dẫn không hợp lệ?

Một directory không tồn tại hoặc không cho tạo backing file có thể làm JVM **thất bại trong giai đoạn khởi tạo**. Không giả định JVM sẽ tự động quay về heap DRAM mà không báo lỗi.

Ví dụ trong phép thử OpenJDK 21/Linux, chạy với một path không tồn tại đã cho:

```text
Error occurred during initialization of VM
Could not create file for Heap at location /not-a-real-mount-for-heap-demo-987654
```

Process **thoát với mã lỗi 1** trước khi chạy `main()`. Ngoài ra JVM có in một warning chứa template file path, nhưng tên ngẫu nhiên của file không cần đưa vào expected output.

Lỗi thực tế tùy OS/HotSpot build. Các nhóm nguyên nhân cần phân biệt:

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo backing file | Directory không tồn tại | `test -d` và absolute path |
| Permission denied | User chạy JVM không có quyền | Owner/group/ACL, SELinux/AppArmor policy |
| No space left / mapping failed | Filesystem thiếu capacity hoặc quota | `df`, device free space, cgroup/mount conditions |
| Device không có | PMEM mount chưa sẵn sàng | `findmnt`, mount namespace, service dependencies |
| Flag không được JVM nhận diện | OS/VM/vendor khác, build không hỗ trợ | `java --version` và tài liệu HotSpot/vendor |
| GC/flag combination không hợp lệ | Cấu hình JVM không tương thích | Read startup diagnostics, thử baseline |
| Process start được nhưng memory vẫn từ DRAM | Path thuộc filesystem thường/page cache | Xác minh FS DAX và underlying device |
| Heap pressure hoặc OOM sau một thời gian | Live set vượt `-Xmx`/capacity | GC logs, heap sizing, object retention |

**Không dùng** cờ kiểu “ignore unrecognized options” để che việc `AllocateHeapAt` không được hỗ trợ: nếu JVM âm thầm bỏ qua option, bạn có thể triển khai sai thiết kế memory placement mà không nhận ra.

## 13. Heap ở thiết bị thay thế có thay đổi cấu hình GC không?

**Về mặt contract thông thường**, các flags `-Xms`, `-Xmx` và GC vẫn mang ý nghĩa vốn có. Nhưng **hiệu năng** có thể khác vì memory device có latency, bandwidth, NUMA affinity hoặc đặc tính page fault khác DRAM.

Những yếu tố nên đo:

- **Throughput**: request/s, ops/s hoặc batch processing time.
- **p95/p99/p99.9 latency**: tail latency trong các đợt thu gom hoặc memory pressure.
- **GC pause duration/frequency**: G1 hoặc collector đang dùng có hành vi gì khi thao tác với heap mapped?
- **Live-set size**: bao nhiêu dữ liệu vẫn reachable sau GC.
- **Allocation rate**: số byte cấp phát mỗi giây.
- **Memory bandwidth** và số cache misses/page faults ở mức OS.
- **NUMA topology**: vị trí CPU/memory device và remote-access cost.
- **Capacity/health** của thiết bị và filesystem.
- **DRAM RSS/native memory** còn sử dụng cho metaspace, stacks, code cache, native allocations.

### Memory bandwidth và GC

GC có thể quét/di chuyển nhiều byte trong heap. Một thiết bị có dung lượng lớn hơn DRAM **không đồng nghĩa GC nhanh hơn**. Nếu thiết bị có bandwidth thấp hoặc latency cao, một số workload có thể **chậm hơn** dù tăng capacity.

Cũng không nên khẳng định mọi collector đều hỗ trợ option giống nhau qua mọi release; kiểm tra JDK/collector/flags kết hợp trong môi trường gần production.

### Không đánh đồng với swap

Chuyển heap qua memory-mapped backing của một filesystem hỗ trợ PMEM **không đồng nghĩa** OS swapping object Java ra đĩa để tiết kiệm RAM. Trong trường hợp không có DAX, mmap có thể đi qua page cache/paging và chịu đặc tính khác. Vì vậy phải nhận diện **backend thật**, không chỉ dựa vào tên cờ hoặc tên directory.

## 14. Capacity planning và các giới hạn bộ nhớ liên quan

Ví dụ muốn chạy heap tối đa **4 GiB** trên PMEM, không nên chỉ xét “thiết bị còn đúng 4 GiB”. Cần dự phòng cho:

- Cấu trúc filesystem/backing/mapping và cách JVM reserve/commit.
- Metadata/quản lý bộ nhớ của hệ điều hành.
- Concurrent allocation pressure, mục tiêu `-Xms/-Xmx`, heap growth.
- Các tiến trình khác chia sẻ thiết bị/mount.
- Native memory/stack/metaspace/code cache vẫn tiêu thụ DRAM.
- Cgroup/container memory accounting khi chạy trong orchestrator.
- Khả năng recover và xử lý khi device đầy/bị unmount.

**Cờ không cho phép bỏ qua memory limits của container.** File-backed mappings có thể vẫn chịu những quy tắc tính bộ nhớ/quota của OS/cgroups. Đừng coi PMEM là nguồn RAM “vô hạn” bên ngoài mọi giới hạn.

### Thực hành sizing

1. Đo **live set** và memory footprint trên heap bình thường.
2. Xác định mục tiêu `-Xms/-Xmx` từ workload, không phải từ kích thước thiết bị đơn thuần.
3. Kiểm tra **free capacity của filesystem thực** khi ứng dụng chạy.
4. Kiểm tra headroom DRAM dành cho metaspace, JIT code, stacks và native memory.
5. Chạy load test ở mức heap pressure thực tế, không chỉ `java -version`.
6. Kiểm chứng ứng dụng có xử lý thích hợp khi device/mapping lỗi hay không.

## 15. Trường hợp trên Docker/Kubernetes

Đường dẫn `-XX:AllocateHeapAt=/mnt/pmem` có ý nghĩa **trong mount namespace của process chạy Java**. Với container, chỉ đặt flag **không** đưa thiết bị PMEM vào container. Hạ tầng phải mount/volume-map filesystem backing theo chính sách bảo mật và storage của cluster.

Một minh họa **fragment** của cấu hình ứng dụng (không phải Kubernetes manifest đầy đủ):

```yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:AllocateHeapAt=/mnt/pmem/java-heaps -Xms512m -Xmx2g"
volumeMounts:
  - name: alternative-heap
    mountPath: /mnt/pmem
volumes:
  - name: alternative-heap
    persistentVolumeClaim:
      claimName: heap-device-volume
```

**Chỉ là sơ đồ ý tưởng:** PVC `heap-device-volume` giả định đã được storage admin provision đúng. **Một PVC bất kỳ không bảo đảm** fsdax/PMEM hoặc mmap direct access. Trước khi dùng, phải kiểm chứng storage class, CSI driver, kernel, permission, performance và quyền truy cập của pod.

Trong thiết kế multi-tenant:

- Tránh chia sẻ cùng một writable directory giữa các JVM không tin cậy.
- Mỗi JVM nên có location/ownership phù hợp, tránh tương tác với backing file của nhau.
- Nếu device bị unmount khi app đang hoạt động, cần hiểu failure modes của OS/JVM.
- Không assume pod restart sẽ phục hồi heap object graph cũ.
- Theo dõi capacity và áp dụng chính sách xử lý lỗi rõ ràng.

### Container CPU và memory là những vấn đề riêng

`-XX:ActiveProcessorCount` xử lý số CPU VM dùng cho sizing; `-XX:AllocateHeapAt` xử lý vị trí backing Java object heap; `-Xmx` xử lý heap limit; còn Docker/Kubernetes áp resource constraints theo OS. Không trộn các cờ này như thể chúng thay thế nhau.

## 16. Bảo mật dữ liệu trên thiết bị có khả năng lưu bền

Một thiết bị non-volatile có thể giữ dữ liệu vật lý sau khi JVM thoát hoặc máy mất điện. Dù Java heap là **volatile về hợp đồng ứng dụng**, cần coi những byte từng nằm trên heap **có khả năng là dữ liệu nhạy cảm**.

Một số biện pháp vận hành phù hợp:

- Phân quyền directory/mount theo nguyên tắc ít quyền nhất.
- Không cung cấp heap backing path qua shared mount công khai.
- Theo dõi ownership/SELinux/AppArmor, container security context.
- Đánh giá mã hóa bộ nhớ/lưu trữ nếu device và OS hỗ trợ.
- Có chính sách secure erase/sanitization phù hợp loại thiết bị khi decommission hoặc tái phân bổ tenant.
- Không xem file bị unlink là bằng chứng tất cả physical bits đã được xóa.
- Không cho rằng JVM bảo đảm consistency của data-at-rest sau crash.
- Kiểm soát access tới core dump/heap dump vì chúng cũng có thể chứa object data nhạy cảm.

**Đừng tự tạo script xóa raw device để “dọn heap”.** Việc làm sạch thiết bị phải do quy trình quản trị hạ tầng thực hiện, bởi thao tác trên raw device có thể phá dữ liệu của các ứng dụng khác.

## 17. Khi nào nên dùng và không nên dùng?

### Có thể phù hợp khi

- Hạ tầng có thiết bị bộ nhớ thay thế được **chứng minh hỗ trợ DRAM-like semantics và mmap/DAX**.
- Workload cần **heap capacity lớn** và benchmark xác nhận tradeoff throughput/latency chấp nhận được.
- Tổ chức có đội vận hành PMEM, filesystem và bảo mật thiết bị.
- JDK/HotSpot build và collector mục tiêu được kiểm chứng hỗ trợ cấu hình.
- Có yêu cầu rõ về chi phí hoặc phân tầng tài nguyên mà không muốn viết lại Java application code.
- Có quy trình đảm bảo mount/volume sẵn sàng trước JVM startup.

### Không phù hợp khi

- Chỉ có SSD/HDD thông thường và muốn “mở rộng RAM miễn phí” bằng cách mmap qua file system.
- Muốn lưu và tự động phục hồi Java objects sau restart.
- Muốn thay thế database/cache có persistent-state contract.
- Ứng dụng nhạy cảm với memory latency nhưng chưa đo được chi phí của device.
- Chưa thể xác minh DAX, permission, filesystem và device health.
- Đang chạy JVM vendor/OS không hỗ trợ hoặc không rõ hỗ trợ.
- Chỉ cần xử lý `OutOfMemoryError` do memory leak.
- Đang dùng filesystem tạm không ổn định trong container production.
- Không có chính sách bảo vệ dữ liệu trên non-volatile device.

Nhiều dịch vụ Java hiện nay sẽ **không cần** `AllocateHeapAt`. Lựa chọn mặc định nên là JDK được hỗ trợ, cấu hình heap/GC phù hợp và giữ kiến trúc đơn giản; chỉ chọn alternative heap placement khi hạ tầng và benchmark cho thấy có lợi ích thực.

## 18. Quy trình kiểm thử theo từng mức rủi ro

### Mức 1: Kiểm tra cú pháp/VM option

```bash
java --version
java -XX:+PrintFlagsFinal -version
```

Tìm `AllocateHeapAt` trong output `PrintFlagsFinal` nếu HotSpot build hỗ trợ; trên JVM khác có thể không có. Việc flag tồn tại trong danh sách **không chứng minh** device cụ thể đủ điều kiện.

### Mức 2: Thử với directory filesystem bình thường, dung lượng nhỏ

Tạo một directory tạm do bạn sở hữu, chạy demo heap nhỏ như mục 10, sau đó xác nhận:

- JVM nhận option.
- App vẫn chạy đúng.
- `/proc/<pid>/maps` ghi nhận path backing nếu Linux hỗ trợ.

Kết quả này chỉ xác minh **mmap behavior**, không được kết luận PMEM.

### Mức 3: Kiểm tra mount DAX thực

Có đội vận hành xác nhận thiết bị, namespace, filesystem và đường dẫn mount. Dùng `findmnt`/công cụ FS và thông tin DAX phù hợp phiên bản Linux, sau đó chạy demo heap nhỏ.

### Mức 4: Stress/so sánh có kiểm soát

Với workload đại diện:

- Giữ nguyên ứng dụng/JDK/GC, chỉ đổi heap backing.
- Đo allocations, throughput, tail latency, GC pauses, CPU/memory, page faults.
- Chạy nhiều lần và ghi phân bố, tránh quyết định từ một lần benchmark.
- Kiểm tra device capacity, lỗi I/O, restart và rollback.
- Lên kế hoạch dự phòng khi mount hỏng hoặc device không sẵn sàng.

### Mức 5: Production rollout

- Gắn option vào deployment config có quản lý phiên bản.
- Đảm bảo mount readiness/permissions trước JVM startup.
- Thiết lập health metrics và cảnh báo dung lượng.
- Quản lý dữ liệu nhạy cảm, access policy và lịch bảo trì hardware.
- Có cách rollback về cấu hình đã được benchmark, không tạo ảo giác một flag có thể chuyển heap trong lúc app đang chạy.

## 19. Những lỗi phổ biến

**Lỗi 1 — “`AllocateHeapAt` nhận raw block device `/dev/pmem0` như đường dẫn hoàn chỉnh.”**

Không đúng theo cách dùng filesystem path/mount directory của JEP 316; cần cấu hình filesystem và mount phù hợp trước khi chỉ định path.

**Lỗi 2 — “Thư mục có tên pmem nghĩa là đã dùng PMEM.”**

Không đúng. Tên path không nói gì về backend; kiểm tra mount/OS/DAX.

**Lỗi 3 — “JVM nhận flag nghĩa là heap đã được đặt trên NVDIMM thật.”**

Không đúng. Một directory filesystem thường có thể tạo mapping. Cần xác nhận physical device.

**Lỗi 4 — “Mapping file nghĩa là Java object được serialize thành file.”**

Không đúng. HotSpot vẫn quản lý native heap layout và object references bình thường.

**Lỗi 5 — “PMEM non-volatile nên restart JVM sẽ phục hồi toàn bộ object graph.”**

Không. JEP 316 không cung cấp persistent Java object store hoặc transaction/recovery contract.

**Lỗi 6 — “Cờ này chuyển metaspace, JIT code cache và stack sang PMEM.”**

Không. Tài liệu Oracle nói các cấu trúc memory khác tiếp tục dùng DRAM.

**Lỗi 7 — “`-Xmx` không còn có tác dụng khi dùng AllocateHeapAt.”**

Sai. Các flags heap/GC giữ ý nghĩa chung như trước.

**Lỗi 8 — “Đặt heap trên PMEM sẽ luôn tăng hiệu năng.”**

Không có bảo đảm; latency/bandwidth/NUMA và GC có thể tạo tradeoff khác.

**Lỗi 9 — “Heap device lớn sẽ sửa mọi OutOfMemoryError.”**

Không. Một số lỗi do giữ object sống, native memory, metaspace, thread creation hoặc resource constraints khác.

**Lỗi 10 — “Nếu path lỗi thì JVM chắc chắn fallback âm thầm về DRAM.”**

Không được giả định. Trong OpenJDK 21/Linux thử nghiệm, path không tồn tại khiến JVM dừng khởi tạo với mã lỗi 1.

**Lỗi 11 — “`HeapDumpPath` và `AllocateHeapAt` là cùng một loại đường dẫn.”**

Không. Heap dump là file chẩn đoán; AllocateHeapAt là backing mapping của heap đang chạy.

**Lỗi 12 — “MappedByteBuffer hoặc direct buffer tự chuyển theo AllocateHeapAt.”**

Không. Các loại memory này có chính sách cấp phát riêng.

**Lỗi 13 — “Dùng `/tmp` là đã kiểm thử thiết bị bộ nhớ thay thế.”**

Không. `/tmp` chỉ có giá trị để kiểm chứng cú pháp/VM mapping nếu không có PMEM.

**Lỗi 14 — “Thấy `/proc/<pid>/maps` chứa path đủ để chứng minh DAX.”**

Không. Maps chứng minh mapping; còn DAX phải kiểm tra filesystem/OS/device riêng.

**Lỗi 15 — “File đã `(deleted)` nghĩa là không thể còn dữ liệu nhạy cảm trên PMEM.”**

Không. Unlink path không thay thế secure erase hoặc data protection của medium.

**Lỗi 16 — “Một Java heap dùng ở hai JVM khác nhau có thể chia sẻ cùng object graph qua mount.”**

Không. Mỗi JVM quản lý heap và metadata của riêng nó; đây không phải distributed shared-memory Java object system.

**Lỗi 17 — “Mọi collector trên mọi JDK vendor chắc chắn nhận tổ hợp cờ này.”**

Không. Phải đọc tài liệu, chạy thử và xác minh startup/log trên đúng build.

**Lỗi 18 — “Trong Kubernetes chỉ cần đặt JAVA_TOOL_OPTIONS; không cần provision device.”**

Không. Container còn cần volume/mount/permissions/storage driver thực tế; PVC bất kỳ không đồng nghĩa PMEM.

**Lỗi 19 — “Cứ mount lại trong lúc app đang chạy là đổi heap device được.”**

Không nên. Java heap đã được map trong startup; thay device/mount sau đó có thể gây lỗi runtime, không phải cơ chế migration hợp lệ.

**Lỗi 20 — “Đường dẫn càng dài/cụ thể càng chứng minh feature đã hoạt động.”**

Không. Cần mapping evidence, mount/device verification và kiểm thử workload.

## 20. Checklist dành cho code review và vận hành

- [ ] Đã chọn đúng JDK/HotSpot distribution còn được cập nhật và kiểm tra option được hỗ trợ.
- [ ] Biết `-XX:AllocateHeapAt` dùng một **filesystem path**, thường là directory mount.
- [ ] Không nhầm directory mount với raw block/device-DAX path.
- [ ] Đã xác nhận đường dẫn tồn tại và user chạy JVM có quyền phù hợp.
- [ ] Filesystem thật được mount trên thiết bị mong muốn, không chỉ có tên `pmem`.
- [ ] Đã kiểm tra yêu cầu DAX/atomic memory semantics theo OS/device hiện hành.
- [ ] Heap size `-Xms/-Xmx` được chọn theo live set/workload.
- [ ] Phần metaspace, stack, code cache và native memory vẫn có đủ DRAM.
- [ ] Không coi cờ là cách bypass cgroup memory limits.
- [ ] Có kiểm tra filesystem capacity và lỗi thiết bị.
- [ ] Có test startup khi path không hợp lệ, không dựa vào fallback giả định.
- [ ] Có kiểm tra mapping ở `/proc/<pid>/maps` khi chạy Linux.
- [ ] Không lấy mapping path làm bằng chứng duy nhất về PMEM/DAX.
- [ ] Không dùng file backing để lưu/khôi phục Java object state sau restart.
- [ ] Có chính sách quyền truy cập và bảo vệ dữ liệu nhạy cảm trên thiết bị.
- [ ] Đã thử workload có GC pressure thực; không chỉ chạy `java -version`.
- [ ] Đã so sánh throughput, p99/p99.9, GC pauses, page faults, CPU/NUMA.
- [ ] Không coi việc tăng capacity là bảo đảm giảm latency.
- [ ] Nếu dùng container, mount namespace/volume/permissions đã được xác minh.
- [ ] Nếu dùng Kubernetes, PVC/CSI thực sự hỗ trợ storage semantics cần thiết.
- [ ] Không ghi đè các cờ/đường dẫn ngoài phạm vi cấu hình có chủ đích.
- [ ] Có phương án rollback khi device gặp sự cố.
- [ ] Không mang nguyên các hướng dẫn cấu hình PMEM của một phần cứng/OS cũ vào môi trường mới.

## 21. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** JEP nào bổ sung Heap Allocation on Alternative Memory Devices?

**Đáp án:** **JEP 316**, được triển khai trong Java 10.

**Câu 2.** Cú pháp option chính xác là gì?

**Đáp án:** `-XX:AllocateHeapAt=<path>`, với path là vị trí filesystem phù hợp để HotSpot tạo backing mapping cho Java object heap.

**Câu 3.** Có nên truyền trực tiếp `/dev/pmem0` như thể đó là một directory mount không?

**Đáp án:** Không. Raw device và directory của filesystem được mount là hai đối tượng khác nhau; cấu hình theo yêu cầu JVM/OS.

**Câu 4.** Vì sao một filesystem cần DAX nếu mục tiêu là direct mapping tới PMEM?

**Đáp án:** DAX cho phép file mapping vào thiết bị bộ nhớ theo cơ chế direct access thích hợp, không tự đi qua page cache như filesystem thông thường.

**Câu 5.** Nếu JVM chạy được với `AllocateHeapAt=/tmp/test`, có chứng minh RAM thật đã được thay bằng PMEM không?

**Đáp án:** Không. Điều đó chỉ kiểm chứng HotSpot có thể dùng file-backed heap mapping tại path. Phải xác nhận backend của filesystem.

**Câu 6.** Những cấu trúc JVM nào vẫn cần DRAM?

**Đáp án:** Metaspace, code heap/JIT code cache, stacks và nhiều cấu trúc native/VM khác không được cờ này chuyển cùng Java object heap.

**Câu 7.** `-Xmx` có còn giới hạn Java heap không?

**Đáp án:** Có. Các flags heap size tiếp tục có ý nghĩa thông thường.

**Câu 8.** Persistent memory có tự khôi phục object graph sau JVM restart không?

**Đáp án:** Không. Java heap vẫn mang ngữ nghĩa trạng thái trong đời tiến trình; muốn persistence phải dùng cơ chế lưu trữ có hợp đồng.

**Câu 9.** Làm sao chứng minh JVM đã memory-map một backing file qua mount path trên Linux?

**Đáp án:** Quan sát `/proc/<pid>/maps` của tiến trình thực và đối chiếu path; tiếp tục dùng công cụ mount/device để xác nhận backend.

**Câu 10.** `Runtime.maxMemory()` có cho biết thiết bị vật lý của heap không?

**Đáp án:** Không. Nó nói về quy mô heap, không trả về vị trí physical memory.

**Câu 11.** Nếu path không tồn tại, JVM có chắc chắn fallback về DRAM không?

**Đáp án:** Không được giả định. Trong phép thử OpenJDK 21/Linux, JVM báo không tạo được file cho heap và thoát với code 1.

**Câu 12.** DAX và Device DAX có giống nhau hoàn toàn không?

**Đáp án:** Không. Filesystem DAX cho phép direct mapping thông qua file trên filesystem; Device DAX là một dạng device mapping khác, không phải directory filesystem thông thường.

**Câu 13.** Có thể dùng cờ này để tự động chuyển DirectByteBuffer và JNI allocations sang PMEM không?

**Đáp án:** Không. Cờ nhắm Java object heap; off-heap/native memory có cơ chế cấp phát riêng.

**Câu 14.** Tại sao không thể coi backing file như một database?

**Đáp án:** Nó chứa runtime heap representation và references của HotSpot, không có transaction, crash-consistency và recovery contract cho object graph.

**Câu 15.** Tại sao cần quản lý bảo mật dữ liệu nếu thiết bị là non-volatile?

**Đáp án:** Những byte từng chứa object data có thể còn tồn tại trên medium; cần quyền, mã hóa/sanitization phù hợp, không dựa vào unlink file.

**Câu 16.** Có thể dùng một PVC Kubernetes bất kỳ để bảo đảm PMEM/DAX không?

**Đáp án:** Không. Phải xác nhận CSI/storage class/volume thực và cấu hình OS/filesystem thích hợp.

**Câu 17.** Có nên dùng cờ này nếu chỉ có SSD thông thường và app đang chậm?

**Đáp án:** Không tự động. Storage file mapping không tương đương memory semantics/latency của PMEM; có thể làm workload chậm hơn.

**Câu 18.** Những chỉ số nào nên so sánh khi chuyển heap?

**Đáp án:** Throughput, p99/p99.9 latency, GC pauses, allocation rate/live set, memory bandwidth/page faults, native DRAM footprint và capacity/device health.

**Câu 19.** Nếu Java source code không thay đổi, có cần kiểm thử regression khi đổi backing heap không?

**Đáp án:** Có. VM vẫn phải chạy đúng, nhưng device latency, GC, resource constraints và failure modes khác có thể ảnh hưởng hành vi vận hành và SLA.

**Câu 20.** Khi nào cấu hình thay thế heap được coi là sẵn sàng production?

**Đáp án:** Khi OS/JDK/vendor support đã được xác minh, path/mount/DAX đúng, memory semantics và bảo mật đạt yêu cầu, workload benchmark chấp nhận được và có monitoring/rollback.

## 22. Nguồn tài liệu chính thức còn áp dụng

1. [OpenJDK — JEP 316: Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): thiết kế và mục tiêu được đưa vào Java 10.
2. [Oracle Java SE 25 — The java Command, -XX:AllocateHeapAt](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): định nghĩa hiện hành về path, memory mapping, NV-DIMM, những vùng JVM còn ở DRAM và `-Xms/-Xmx`.
3. [OpenJDK — java launcher manual (current source)](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): sự hiện diện của tùy chọn trong hướng dẫn OpenJDK mới.
4. [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): tham chiếu phiên bản hiện đại; cần kiểm tra lại nếu dùng bản sau này.
5. [Linux NVDIMM documentation](https://nvdimm.docs.kernel.org/): namespace modes, fsdax/devdax và khả năng DAX.
6. [Linux Kernel — LIBNVDIMM](https://www.kernel.org/doc/html/latest/driver-api/nvdimm/nvdimm.html): mô hình PMEM/DAX của Linux.
7. [Red Hat Enterprise Linux 10 — NVDIMM persistent memory storage](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/managing_storage_devices/using-nvdimm-persistent-memory-storage): cách dùng filesystem DAX hiện hành; chi tiết thay đổi theo OS.
8. [Java SE 25 — Runtime.maxMemory()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#maxMemory()): heap sizing API, không xác định vật lý memory device.
9. [Oracle Java SE 25 — Memory Management and Garbage Collection](https://docs.oracle.com/en/java/javase/25/gctuning/): các tradeoff heap/GC cần đo trên workload thực.
10. [Java SE 25 — File Systems](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html): OS/JDK abstraction của file system, không thay thế xác minh direct access backend.

**Kết luận:** `-XX:AllocateHeapAt=<path>` đưa vào từ Java 10 và **vẫn được tài liệu hóa trong HotSpot JDK hiện đại**. Nó chỉ định một **đường dẫn filesystem** để JVM memory-map **Java object heap** trên loại memory backing do hệ điều hành cung cấp. Cần dùng đúng directory mount, device semantics, capacity, permissions và DAX khi mục tiêu là PMEM thật; heap size và GC flags vẫn có ngữ nghĩa thông thường, còn metaspace/stacks/code cache vẫn cần DRAM. Đây **không phải cơ chế persistent Java objects, không phải heap dump và không phải cách biến disk thành RAM miễn phí**. Để áp dụng an toàn, hãy xác minh mapping cùng backend vật lý, benchmark workload và quản lý security/failure modes của thiết bị.
