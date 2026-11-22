# Quan hệ giữa `-Xms`, `-Xmx` và bộ thu gom khi đặt Java heap trên thiết bị bộ nhớ thay thế (Java 10+)

## 1. Bài toán: di chuyển Java object heap sang bộ nhớ khác có làm mất giới hạn heap?

Trong ứng dụng Java thông thường, JVM cấp phát **Java object heap** trên vùng bộ nhớ mà hệ điều hành cung cấp, thường liên hệ với DRAM. Một số máy chủ chuyên dụng có **thiết bị bộ nhớ thay thế** (ví dụ thiết bị bộ nhớ không mất dữ liệu dạng NV-DIMM được hệ điều hành phơi bày dưới dạng hệ thống tệp hỗ trợ ánh xạ trực tiếp). Với HotSpot, tùy chọn sau cho phép thử đặt **object heap** lên thiết bị như vậy:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms1g -Xmx4g \
     -XX:+UseG1GC \
     -jar app.jar
```

Lệnh này chỉ là **mẫu cấu hình để hiểu cơ chế**. Đường dẫn `/mnt/pmem/heap`, JAR, phần cứng, hệ thống tệp và quyền truy cập đều phải được thay bằng môi trường **thật sự hỗ trợ**. Không chạy lệnh trên một thư mục thường rồi tự kết luận đã sử dụng PMEM/NV-DIMM.

**Câu hỏi chính:** khi thay vị trí cấp phát object heap bằng `-XX:AllocateHeapAt`, các giới hạn `-Xms`, `-Xmx` và việc chọn garbage collector có tiếp tục có ý nghĩa hay không?

**Trả lời:** Có. Tài liệu Oracle Java SE 25 và 27 hiện hành vẫn mô tả `-XX:AllocateHeapAt` và khẳng định các tùy chọn heap như `-Xmx`, `-Xms` cùng các tùy chọn liên quan **garbage collection** tiếp tục hoạt động như trước. Cờ đặt vị trí nhớ **không thay thế** cờ kích thước heap và **không tắt GC**.

Ba nhóm trách nhiệm độc lập về khái niệm:

1. **`-XX:AllocateHeapAt`:** chỉ định **nơi** HotSpot cố bố trí Java object heap qua memory mapping.
2. **`-Xms` và `-Xmx`:** quy định **mức heap ban đầu/tối thiểu** và **giới hạn heap tối đa**.
3. **Bộ thu gom rác (GC):** quyết định **cách nhận biết, thu hồi và tổ chức các Java object** trong heap, với các đặc điểm throughput, latency và footprint khác nhau.

**Không nhầm vị trí với dung lượng:** đặt heap trên thiết bị khác không làm giới hạn `-Xmx4g` tự tăng lên bằng dung lượng thiết bị, và có thiết bị 1 TiB không nghĩa JVM có thể dùng hết 1 TiB nếu cấu hình `-Xmx4g`.

## 2. Nguồn gốc Java 10 và phạm vi kiến thức còn hiệu lực

Tính năng **Heap Allocation on Alternative Memory Devices** được giới thiệu với **OpenJDK JEP 316** ở Java 10. Mục tiêu là tận dụng một loại thiết bị bộ nhớ có thể được ánh xạ vào không gian địa chỉ tiến trình như DRAM mà **không cần thay đổi mã Java ứng dụng**.

**Đây là khả năng của HotSpot VM**, không phải cú pháp ngôn ngữ Java 10 hay API `ByteBuffer` được ứng dụng gọi trực tiếp. Trên JDK hiện hành, Oracle vẫn tài liệu hóa `-XX:AllocateHeapAt` trong phần *Advanced Runtime Options*; vì vậy bài này chỉ trình bày những cách hiểu và tùy chọn vẫn còn áp dụng, không hướng dẫn sử dụng các bộ thu gom đã bị loại bỏ hay flag GC legacy.

Tuy nhiên, cần phân biệt:

- **Cờ vẫn được tài liệu hóa** không có nghĩa mọi JDK, OS, kiến trúc CPU và filesystem đều hỗ trợ mọi trường hợp triển khai.
- **Thiết bị lưu trữ thông thường** như SSD, ổ cứng hay NFS không mặc nhiên là thiết bị bộ nhớ thay thế thỏa yêu cầu mapping.
- Một tính năng có từ Java 10 không bắt buộc phải chạy trên **JDK 10 đã ngừng vòng cập nhật thông thường**. Nên dùng phiên bản JDK/HotSpot còn được hỗ trợ và xác nhận thực tế trên nền tảng chạy.

Bài tập trung vào **quan hệ với kích thước heap và GC**, không đào sâu cấu hình phần cứng NVDIMM đặc thù của từng nhà sản xuất.

## 3. Object heap không phải toàn bộ bộ nhớ JVM

Một tiến trình Java sử dụng nhiều vùng bộ nhớ:

```text
Tiến trình HotSpot
 |
 +-- Java object heap                   <-- có thể chọn vị trí qua AllocateHeapAt
 |    +-- Java objects / arrays
 |    +-- Các vùng hoặc thế hệ do GC quản lý
 |
 +-- Metaspace / class metadata         <-- không tự chuyển theo object heap
 +-- Code cache / JIT-compiled code     <-- không tự chuyển theo object heap
 +-- Thread stacks                     <-- không tự chuyển theo object heap
 +-- GC/native bookkeeping             <-- có thể còn ở bộ nhớ khác
 +-- Direct buffers / JNI / libc       <-- không tự chuyển theo object heap
 +-- OS page tables và tài nguyên khác
```

Theo tài liệu Oracle, khi dùng `-XX:AllocateHeapAt`, **các cấu trúc bộ nhớ khác** như code heap, metaspace và thread stacks **vẫn ở DRAM**, thay vì tự dời đi cùng Java object heap.

Điều này dẫn đến ba lưu ý:

- Dù heap được đặt trên một thiết bị dung lượng lớn, **DRAM vẫn cần thiết** cho các thành phần khác.
- `-Xmx` **không** phải giới hạn tổng memory/RSS của tiến trình.
- Cải thiện được dung lượng heap **không tự động** giải quyết thiếu native memory, số lượng thread quá nhiều hoặc OOMKill trong container.

**Không tự suy rằng bộ nhớ không mất dữ liệu sẽ lưu bền object Java:** Java heap vẫn là vùng quản lý runtime với GC và vòng đời của tiến trình. `AllocateHeapAt` không biến object graph thành database hay kho dữ liệu có thể khôi phục sau restart.

## 4. `-XX:AllocateHeapAt` thực sự làm gì?

Cú pháp HotSpot hiện hành:

```text
-XX:AllocateHeapAt=path
```

Tùy chọn này chỉ định một **đường dẫn trên filesystem được hệ điều hành cung cấp cho thiết bị bộ nhớ**. JVM dùng **memory mapping** để bố trí vùng object heap trên thiết bị đó.

Oracle mô tả rằng các thiết bị thích hợp cần có **ngữ nghĩa tương tự DRAM**, gồm **các thao tác nguyên tử (atomic operations)**, để Java object heap có thể được đặt lên đó mà không yêu cầu sửa mã ứng dụng.

Một số filesystem hỗ trợ **direct access (DAX)** để memory-mapped memory được ánh xạ trực tiếp đến bộ nhớ thiết bị thay vì đi qua page cache thông thường. Đây là một thuộc tính của **nền tảng + thiết bị + filesystem + mount configuration**, không phải điều kiện tự động có chỉ vì đường dẫn tồn tại.

**Phân biệt chính xác:**

| Công nghệ/đối tượng | Có đủ để suy rằng object heap chạy trên alternative memory? |
| --- | --- |
| NV-DIMM / thiết bị có memory semantics thích hợp, OS expose mapping tương ứng | **Có thể**, sau khi cấu hình và kiểm chứng |
| Filesystem DAX được mount và cho phép mapping phù hợp | **Có thể**, phụ thuộc JDK/OS/device |
| Thư mục trong `/tmp` | **Không**; tên đường dẫn không chứng minh loại bộ nhớ |
| SSD/HDD thông thường | **Không**; block storage không tự thành RAM có atomic semantics |
| `java.nio.MappedByteBuffer` trong code ứng dụng | **Không**; đây là API map file riêng, không tự dời object heap |
| `-Xmx` lớn hơn | **Không**; tăng giới hạn dung lượng không đổi vị trí heap |
| DRAM host còn đủ | **Không**; đây là dung lượng, không phải yêu cầu placement |

**Đường dẫn trong ví dụ chỉ là ký hiệu**. Trước khi thử thật, đội vận hành cần xác nhận chuẩn filesystem/PMEM theo nhà cung cấp, kiểm tra quyền truy cập và hỗ trợ của JDK, không sử dụng một filesystem lưu dữ liệu quan trọng để chạy thí nghiệm ghi/mapping tùy tiện.

## 5. `-Xms`: giới hạn tối thiểu và kích thước khởi đầu của Java heap

Tùy chọn:

```bash
java -Xms1g -jar app.jar
```

`-Xms` đặt kích thước **initial/minimum Java heap** theo hợp đồng của launcher HotSpot. Nhiều ví dụ giải thích đơn giản rằng “heap bắt đầu 1 GiB”; đây là cách nói hữu ích nhưng cần phân biệt với việc **mọi trang vật lý đã được chạm và cấp phát thực sự**.

Ví dụ khi chạy với heap trên thiết bị bộ nhớ thay thế:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms1g -Xmx4g \
     -jar app.jar
```

**Ý nghĩa:**

- Object heap của JVM được yêu cầu đặt tại đường dẫn alternative-memory phù hợp.
- `-Xms1g` đặt mức heap ban đầu/tối thiểu.
- `-Xmx4g` đặt giới hạn heap tối đa.
- Khi tải biến động, GC/HotSpot có thể **điều chỉnh phần heap được commit hoặc sử dụng** trong khoảng chính sách cho phép, tùy collector và các cờ khác.

`-Xms` **không** có nghĩa ứng dụng đã tạo object Java chiếm 1 GiB. `MemoryUsage.getUsed()` có thể chỉ là vài MiB ngay sau khởi động.

Một điểm quan trọng về thiết bị: `-Xms` càng lớn thì nhu cầu commit/touch và thời gian khởi tạo có thể lớn hơn; **chi phí thực tế phụ thuộc cách HotSpot, OS và thiết bị map/commit**. Không có bảo đảm startup sẽ nhanh hơn chỉ vì tăng Xms.

## 6. `-Xmx`: trần heap, không phải dung lượng thực được dùng

Tùy chọn:

```bash
java -Xmx4g -jar app.jar
```

`-Xmx` (tương đương `-XX:MaxHeapSize`) đặt **maximum heap**. Nó giới hạn vùng Java object heap, bất kể vùng đó nằm trên DRAM hay một thiết bị bộ nhớ thay thế được hỗ trợ.

Với:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms1g -Xmx4g \
     -jar app.jar
```

những điều **không** xảy ra chỉ vì có `AllocateHeapAt`:

- `-Xmx` không tự tăng lên bằng toàn bộ dung lượng NV-DIMM.
- Giới hạn cgroup/container memory (nếu có) không tự biến mất.
- JVM không tự bỏ qua mọi điều kiện `OutOfMemoryError`.
- Một GC không được phép cấp phát object Java vượt trần heap vì storage còn chỗ.
- Metaspace, code cache và thread stacks không tự bị tính **bên trong** 4 GiB object heap.

**Cảnh báo về số đo:** `-Xmx4g` là mức được cấu hình; khi quan sát qua `Runtime.maxMemory()` hoặc `MemoryMXBean`, số byte hiệu lực có thể chênh lệch một chút do collector, căn chỉnh, các vùng heap và cách API báo giá trị. Cấu hình trần không phải lời hứa một phép đo bằng đúng 4 GiB trong mọi bản HotSpot.

Nếu thiết bị không đủ chỗ hoặc mapping/commit thất bại, JVM có thể không khởi động hoặc gặp lỗi cấp phát sau đó. Đặt `-Xmx` cao **không tạo ra capacity** cho thiết bị.

## 7. Quan hệ `-Xms` và `-Xmx` không thay đổi khi đổi nơi đặt heap

Một bảng ra quyết định đơn giản:

| Cấu hình | Hợp đồng kích thước heap | Ý nghĩa khi dùng `AllocateHeapAt` |
| --- | --- | --- |
| Không ghi `-Xms`/`-Xmx` | VM chọn giá trị dựa trên ergonomics, môi trường và GC | Vẫn phải tính heap và kiểm tra capacity của thiết bị |
| `-Xms1g -Xmx4g` | Initial/minimum ~1 GiB, maximum ~4 GiB | Đặt vùng Java heap trong phạm vi đó ở vị trí được chỉ định |
| `-Xms4g -Xmx4g` | Heap được cấu hình cùng mức initial và maximum | Giảm mức linh hoạt tự động co/giãn; không ép dữ liệu Java sử dụng đủ 4 GiB |
| `-Xms5g -Xmx4g` | Mức initial lớn hơn maximum | **Cấu hình sai**, JVM không thể đáp ứng |
| `-Xms1g` và không `-Xmx` | Minimum/initial tường minh, trần do VM chọn | Không suy rằng maximum = initial |
| Chỉ `-Xmx4g` | Maximum tường minh; initial do VM chọn | Không suy rằng initial bằng 4 GiB |

Trong thực tế, heap cần có:

```text
initial/minimum <= maximum
```

Nếu đòi initial lớn hơn maximum, HotSpot thường **không khởi động**; không phải nó tự lấy dung lượng từ ổ PMEM rồi cho phép một heap vượt giới hạn.

### Vì sao đôi khi đặt `-Xms` bằng `-Xmx`?

Điều này có thể có ích trong một số workload muốn giữ heap ổn định, giảm biến động do growth/shrink. Tuy nhiên, nó có thể:

- Tăng nhu cầu bộ nhớ/commit khi startup.
- Kéo dài startup nếu chạm trước nhiều trang heap.
- Gây lãng phí khả năng linh hoạt cho một ứng dụng hiếm khi cần heap lớn.
- Làm việc mapping/khởi tạo trên thiết bị thay thế nhạy hơn với dung lượng và hiệu năng thiết bị.

**Không có quy tắc “bắt buộc `Xms=Xmx` khi dùng `AllocateHeapAt`”.** Tài liệu Oracle nói các tùy chọn heap tiếp tục hoạt động như trước; chọn bằng nhau hay không phải dựa vào workload, GC và điều kiện device.

## 8. GC vẫn quản lý object heap như trước

GC là thành phần quyết định **khi nào thu gom**, **đối tượng nào còn sống** và **cách reclaim/reorganize heap**. Tùy chọn `AllocateHeapAt` đổi chỗ bố trí **vùng object heap**, chứ không làm ứng dụng phải tự `free()` các object Java.

Ví dụ:

```java
byte[] payload = new byte[1024 * 1024];
payload[0] = 42;
```

Đây là mã minh họa trong một phương thức. Khi `payload` và các reference khác đến mảng không còn được dùng, bộ thu gom sẽ xử lý theo chính sách GC; không phải application có một API `free(payload)` vì heap ở NV-DIMM.

Tài liệu Oracle Java SE 25/27 nêu rằng **các cờ liên quan GC vẫn hoạt động như trước** trong mô hình alternative heap. Điều đó có nghĩa lựa chọn collector và các mục tiêu GC vẫn có ý nghĩa, ví dụ:

```bash
java -Xms1g -Xmx4g \
     -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -jar app.jar
```

Khi thêm `-XX:AllocateHeapAt=/mnt/pmem/heap` vào cùng một JVM hỗ trợ, ý nghĩa của **giới hạn heap** và **mục tiêu GC** không biến thành cơ chế lưu trữ bền vững hay quản lý storage file.

**Nhưng không suy ra tất cả collector/VM/OS đều hỗ trợ mọi cấu hình alternative heap**. Nền tảng có thể có ràng buộc về page mapping, cấu trúc địa chỉ và các chế độ GC đặc thù; cần kiểm tra tương thích trên **đúng JDK build/GC + hardware**. Câu “GC flags continue to work” không có nghĩa latency hoặc throughput y hệt DRAM.

## 9. Chọn collector theo mục tiêu ứng dụng, không theo tên thiết bị

Một số GC hiện hành trong HotSpot:

| Bộ thu gom | Tùy chọn điển hình | Hướng tối ưu chính | Lưu ý trong bài toán alternative heap |
| --- | --- | --- | --- |
| **G1** | `-XX:+UseG1GC` | Cân bằng throughput và pause goal | Cần đo pause, region sizing, concurrent work khi truy cập device |
| **Parallel GC** | `-XX:+UseParallelGC` | Throughput với stop-the-world parallel phases | Tốc độ quét/copy có thể nhạy với băng thông và độ trễ thiết bị |
| **Serial GC** | `-XX:+UseSerialGC` | Đơn giản, footprint nhỏ ở workload phù hợp | Không mặc định phù hợp heap rất lớn |
| **ZGC** | `-XX:+UseZGC` trên bản hỗ trợ | Độ trễ thấp, concurrent GC | Cần kiểm tra hỗ trợ và yêu cầu mapping của GC/bản JDK; **không mặc định** ghép với mọi memory device |
| **Shenandoah** | `-XX:+UseShenandoahGC` trên bản hỗ trợ | Giảm pause bằng concurrent work | Không có ở mọi bản phân phối; phải xác nhận support |

**Cảnh báo:** đây là bảng **định hướng lựa chọn collector trong HotSpot hiện đại**, **không phải bảng đã chứng minh từng collector có thể dùng `AllocateHeapAt` trên mọi phần cứng**. Nếu một VM không nhận cờ của một collector hoặc một combination thất bại, cần dùng collector/VM/hardware combo được nhà cung cấp hỗ trợ.

GC đã bị loại bỏ khỏi các JDK mới **không được đưa vào cấu hình khuyến nghị**. Cũng tránh chọn GC chỉ vì bài hướng dẫn Java 10 cũ từng dùng một bộ thu gom khác.

### “Bộ thu gom hoạt động như trước” nghĩa đến đâu?

- Đối tượng Java vẫn do GC quản lý.
- Cờ kích thước heap và cờ GC vẫn có vai trò thông thường.
- Mã ứng dụng không phải thay đổi để free object.
- GC vẫn cần thực hiện marking, evacuation, compaction… phù hợp thuật toán.

**Không bảo đảm:**

- Pause time không đổi.
- GC throughput không đổi.
- Mọi đường cấp phát đều chỉ chạm bộ nhớ thay thế.
- DRAM usage bằng 0.
- Mọi collector có cùng support matrix và cùng minimum heap.
- Không có lỗi capacity, mapping hoặc alignment do thiết bị.

Đó là giới hạn quan trọng khi áp dụng trong production.

## 10. Memory bandwidth, latency và tác động đến GC

Đặt heap trên loại bộ nhớ khác DRAM có thể mở rộng capacity, nhưng **độ trễ truy cập và băng thông thiết bị** có thể khác DRAM. GC cũng đọc/ghi object và metadata liên quan, vì vậy sự khác biệt phần cứng có thể ảnh hưởng:

- Allocation throughput.
- Tốc độ copy/evacuate các object sống.
- Thời gian mark/scan vùng object heap.
- Concurrent GC CPU/bandwidth pressure.
- Pause latency và tail latency của request.
- Khả năng giữ các thread ứng dụng chạy khi GC concurrent đang hoạt động.
- Nhu cầu native DRAM cho metaspace, JIT và dữ liệu VM khác.

**Không hứa “heap trên PMEM luôn nhanh hơn”**; ý tưởng ban đầu chủ yếu mở ra một lựa chọn về **capacity/cost/topology** cho những thiết bị có memory semantics thích hợp. Performance phải được kiểm chứng trên thiết bị và workload thực.

Ví dụ một phép benchmark có thể đặt:

```text
Cấu hình A: HotSpot + G1 + DRAM heap
Cấu hình B: cùng HotSpot + G1 + AllocateHeapAt tới device hỗ trợ

Giữ cùng:
  - phiên bản Java và cờ GC
  - -Xms, -Xmx
  - CPU, NUMA policy, giới hạn container
  - workload, lượng dữ liệu sống, allocation rate
  - điều kiện warmup, số lần lặp, chỉ số đo

So:
  - throughput và p95/p99 latency
  - GC pause/event count
  - allocation rate và promoted bytes
  - memory pressure/capacity của device
  - DRAM và native memory footprint
```

Nếu đổi cả GC lẫn nơi đặt heap trong cùng một thử nghiệm, rất khó biết nguyên nhân của chênh lệch performance.

## 11. Các vùng DRAM ngoài heap vẫn cần tính toán

Giả sử có thiết bị thay thế dung lượng 256 GiB và bạn đặt:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms32g -Xmx128g \
     -jar app.jar
```

Không được suy rằng một JVM như vậy sẽ chỉ cần rất ít DRAM không đáng kể. Dù object heap có thể được bố trí trên device, **metaspace, code heap, thread stacks** vẫn nằm ở DRAM theo tài liệu, bên cạnh những tài nguyên VM và native khác.

Các nguy cơ có thể gồm:

- Hàng nghìn thread làm tăng tổng nhu cầu stack.
- Nhiều classloader/dynamic proxy phát sinh class metadata.
- Framework hoặc thư viện native dùng direct buffers/Unsafe/JNI ngoài heap.
- Heap dump hoặc profiling tạo thêm pressure trên filesystem/memory.
- OS page tables và file mappings tiêu tốn tài nguyên.
- JVM cần native memory để tổ chức collector và vùng runtime.

**Giới hạn `-Xmx` không phải rào chắn tổng RSS.** Nếu container/pod áp memory limit, tổng memory được tính vào cgroup còn phụ thuộc cơ chế memory accounting của kernel và device mapping. Không mặc định “heap ở PMEM thì sẽ không bị cgroup memory limit tính đến”.

Mục tiêu capacity planning là xác định **cả memory device lẫn DRAM/native budget**, không chỉ mua/đặt một thiết bị lớn rồi tăng `-Xmx`.

## 12. Sự khác nhau giữa reserved, committed, used và maximum heap

Một nguồn nhầm lẫn khi debug `-Xms/-Xmx` là gom mọi số memory thành một.

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Reserved virtual address space** | Không gian địa chỉ được dành để có thể mở rộng mapping/heap |
| **Committed heap** | Phần heap mà VM đã làm sẵn có cho việc cấp phát theo hợp đồng memory accounting |
| **Used heap** | Phần heap thực chứa dữ liệu object theo số đo JVM |
| **Maximum heap** | Trần heap do JVM/GC quyết định từ cờ và giới hạn khác |
| **Physical/device memory used** | Trạng thái thật trên OS/thiết bị, có thể khác số byte committed hoặc mapped |

Trong Java:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage heap =
        ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

long initialBytes = heap.getInit();
long usedBytes = heap.getUsed();
long committedBytes = heap.getCommitted();
long maximumBytes = heap.getMax();
```

Đây là các câu lệnh minh họa **bên trong một phương thức**, không phải một file Java độc lập.

**Lưu ý:** `getInit()` và `getMax()` có thể dùng `-1` nếu một trường không được định nghĩa theo hợp đồng `MemoryUsage`. Trên HotSpot thông thường chúng được báo có giá trị, nhưng code đo lường tổng quát phải xử lý tình huống “undefined” thay vì mặc định mọi JVM đều trả số dương.

**Điều các API này không nói:** số `getMax()` hoặc `getCommitted()` **không tự tiết lộ object heap đang nằm trên NV-DIMM/DAX hay DRAM**. Chúng mô tả kích thước/quản lý memory, không phải bằng chứng placement trên phần cứng.

## 13. Vì sao `-Xmx128m` đôi khi không hiện đúng 128 MiB trong Java API?

Trên **Azul Zulu OpenJDK 24.0.2, HotSpot Windows x64**, đã thử ba collector **trên bộ nhớ thông thường** với cùng cờ:

```bash
java -Xms32m -Xmx128m -XX:+UseG1GC -XshowSettings:vm -version

java -Xms32m -Xmx128m -XX:+UseParallelGC -XshowSettings:vm -version

java -Xms32m -Xmx128m -XX:+UseSerialGC -XshowSettings:vm -version
```

`-XshowSettings:vm` trong cả ba trường hợp **đều báo**:

```text
Min. Heap Size: 32.00M
Max. Heap Size: 128.00M
```

Tuy nhiên, một lần kiểm tra bằng `MemoryMXBean.getHeapMemoryUsage()` với cùng bộ cờ cho:

| Collector | `getInit()` theo MiB | `getMax()` theo MiB (chia nguyên) |
| --- | ---: | ---: |
| G1 | 32 | 128 |
| Parallel | 32 | 114 |
| Serial | 32 | 123 |

Điều này không phải chứng minh `-Xmx` đã bị bỏ qua. Những collector có cách tổ chức young/old generation, survivor spaces, vùng được báo qua `MemoryUsage` và rounding khác nhau. Giá trị **effective maximum được Java API báo** có thể không giống hệt số byte từ cờ command-line ở mọi collector.

**Bài học:** khi chẩn đoán:

- Đọc **cờ JVM đã cấu hình** (`-Xms/-Xmx`).
- Đọc **mức heap mà VM đã chọn** (`-XshowSettings:vm`, `-XX:+PrintFlagsFinal`).
- Đọc **heap thực tế mà API báo** (`MemoryMXBean`, `Runtime.maxMemory()`).
- Xác định **collector hiện đang dùng**, vì một số con số phản ánh cách chia vùng heap của collector.

Không lấy một chênh lệch vài MiB giữa API và `-Xmx` làm bằng chứng rằng `AllocateHeapAt` không hoạt động. Những số trên được đo **không sử dụng alternative-memory device**, nên **chỉ kiểm chứng ngữ nghĩa và khả năng quan sát của cờ kích thước/GC**, không phải chứng minh placement.

## 14. Chương trình Java 17+ hoàn chỉnh: kiểm tra heap và collector

Bài này cung cấp một chương trình Java chỉ dùng API quản trị chuẩn để **đo heap và GC đã được JVM chọn**. Nó **không đòi hỏi có NV-DIMM** để biên dịch/chạy, vì vị trí bố trí heap là cấu hình của HotSpot lúc khởi động.

Tạo tệp `AlternativeHeapLimitsProbe.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.List;

public class AlternativeHeapLimitsProbe {

    static long mib(long bytes) {
        return bytes / (1024L * 1024L);
    }

    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        List<String> collectors =
                ManagementFactory.getGarbageCollectorMXBeans()
                        .stream()
                        .map(GarbageCollectorMXBean::getName)
                        .sorted()
                        .toList();

        System.out.println(
                "initialHeapMiB=" + mib(heap.getInit()));
        System.out.println(
                "maximumHeapMiB=" + mib(heap.getMax()));

        System.out.println(
                "usedWithinCommitted="
                        + (heap.getUsed() <= heap.getCommitted()));

        System.out.println(
                "committedWithinMax="
                        + (heap.getCommitted() <= heap.getMax()));

        System.out.println(
                "hasCollector=" + !collectors.isEmpty());
        System.out.println(
                "collectors=" + collectors);

        if (heap.getInit() <= 0
                || heap.getMax() < heap.getInit()
                || heap.getUsed() < 0
                || heap.getUsed() > heap.getCommitted()
                || heap.getCommitted() > heap.getMax()
                || collectors.isEmpty()) {
            throw new AssertionError(
                    "Heap/GC state is inconsistent");
        }

        System.out.println("tests=PASS");
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 AlternativeHeapLimitsProbe.java
```

Chạy trên **bộ nhớ thường** trước:

```bash
java -Xms32m -Xmx128m \
     -XX:+UseG1GC \
     AlternativeHeapLimitsProbe
```

Output đã kiểm chứng trên **Azul Zulu OpenJDK 24.0.2 / HotSpot Windows x64**:

```text
initialHeapMiB=32
maximumHeapMiB=128
usedWithinCommitted=true
committedWithinMax=true
hasCollector=true
collectors=[G1 Concurrent GC, G1 Old Generation, G1 Young Generation]
tests=PASS
```

**Cách đọc:**

1. `initialHeapMiB=32`: đúng mức initial heap được cấu hình ở trường hợp cụ thể.
2. `maximumHeapMiB=128`: G1 báo max heap hiệu lực 128 MiB trong lần chạy này.
3. `usedWithinCommitted=true`: lượng heap được dùng không vượt phần committed.
4. `committedWithinMax=true`: phần heap committed không vượt maximum hiệu lực mà collector báo.
5. `hasCollector=true`: JVM có bộ thu gom được báo qua management API.
6. `collectors=[...]`: xác nhận những thành phần GC mà HotSpot này công bố; tên có thể khác ở các JDK khác.
7. `tests=PASS` chỉ xuất hiện khi các điều kiện về heap state đều đúng.

Với Parallel/Serial GC, chương trình có thể in tên collector và max heap khác; **đừng hardcode G1 output làm expected của mọi VM**. Đây là chương trình dùng API **Java 17** và không có thư viện ngoài.

**Quan trọng:** `AlternativeHeapLimitsProbe` **không có cách nào từ các API này để xác nhận heap nằm trên alternative memory**. Cần quan sát bên ngoài từ HotSpot/OS và xác minh filesystem/device.

## 15. Thử `-XX:AllocateHeapAt` trên nền tảng thật như thế nào?

Sau khi đội vận hành xác nhận có **thiết bị + filesystem hỗ trợ mapping**, có quyền phù hợp và bản HotSpot hỗ trợ flag, lệnh thử là:

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms1g -Xmx4g \
     -XX:+UseG1GC \
     -Xlog:gc*=info \
     AlternativeHeapLimitsProbe
```

Đây chỉ là **lệnh triển khai minh họa, không phải kết quả test thực nghiệm của bài**. Việc thành công còn phụ thuộc:

- Đường dẫn là vùng filesystem/device phù hợp, không chỉ một thư mục tùy ý.
- Hệ điều hành có khả năng memory-map và thiết bị hỗ trợ atomic/memory semantics.
- Đủ dung lượng, mapping space và quyền truy cập theo cấu hình.
- Cờ được bản HotSpot/OS hỗ trợ.
- Collector đã chọn và cách tổ chức heap tương thích với cơ chế mapping.
- Một số flag khác (NUMA, large pages, JIT, module, GC) không mâu thuẫn.

**Không mặc định JVM sẽ fallback sang DRAM nếu mapping thất bại.** Với một tùy chọn placement được yêu cầu tường minh, cần **kiểm tra exit code và log**; JVM có thể từ chối khởi động hoặc gặp lỗi cấp phát. Nếu ứng dụng cần cơ chế fallback theo nghiệp vụ, hãy xây dựng chiến lược launch/deploy có kiểm soát, không tự giả định behavior.

### Có nên dùng `-Xms4g -Xmx4g` ngay khi thử?

Chưa chắc. Nếu device/FS chưa được kiểm chứng capacity/commit, đặt initial lớn có thể làm một phép thử trở nên tốn tài nguyên hoặc không khởi động. Bắt đầu với mức sizing phù hợp quy định test, rồi tăng có kiểm soát. Không để một ví dụ copy-paste thay thế kế hoạch capacity của production.

## 16. Cách xem GC thực sự được chọn và log GC

Lệnh chẩn đoán cơ bản:

```bash
java -Xms32m -Xmx128m \
     -XX:+UseG1GC \
     -Xlog:gc*=info \
     AlternativeHeapLimitsProbe
```

Các dòng log GC có thể ghi những thông tin như:

```text
[info][gc] Using G1
[info][gc,init] Heap Initial Capacity: ...
[info][gc,init] Heap Max Capacity: ...
```

Đây là **ví dụ hình thái log**, không phải output cố định của mọi JDK; nội dung còn tùy collector và version. Khi JVM có khả năng in mức cụ thể, hãy phân tích theo tag/mức log, đừng so cứng từng câu tiếng Anh.

Các tùy chọn HotSpot còn hữu ích:

```bash
java -Xms32m -Xmx128m \
     -XX:+PrintFlagsFinal \
     -version
```

Tìm các cờ:

```text
InitialHeapSize
MinHeapSize
MaxHeapSize
AllocateHeapAt
UseG1GC
UseParallelGC
UseSerialGC
```

Bài đã kiểm chứng trên JDK 24: `AllocateHeapAt` vẫn xuất hiện trong `-XX:+PrintFlagsFinal`. Điều đó **xác nhận cờ có mặt trong build HotSpot được kiểm tra**, **không chứng minh** một thiết bị NV-DIMM/DAX có sẵn.

Để chẩn đoán cụ thể vị trí mapping, phối hợp:

- Thông báo lỗi/log startup của HotSpot khi dùng flag.
- Mount/device information từ hệ điều hành.
- Process memory mappings theo công cụ OS thích hợp.
- Số liệu device/NUMA khi có.
- Các marker thống kê/observability do platform team thiết lập.

**Đừng dựa duy nhất vào `Runtime.maxMemory()` hoặc tên GC trong log** để kết luận nơi đặt heap.

## 17. `-XX:+AlwaysPreTouch` có tương tác gì?

`-XX:+AlwaysPreTouch` là tùy chọn HotSpot hiện hành yêu cầu JVM **chạm trước các trang heap** theo chính sách khởi tạo bộ nhớ để các trang trở nên sẵn sàng cho ứng dụng.

```bash
java -Xms1g -Xmx4g \
     -XX:+AlwaysPreTouch \
     -jar app.jar
```

Khi cân nhắc dùng chung với alternative memory:

- Chi phí startup có thể tăng do pre-touch nhiều trang heap.
- Việc pre-touch có thể bộc lộ vấn đề capacity/latency của device sớm hơn.
- Tác động khác nhau theo số trang, GC, page size, OS và device.
- Không có nghĩa Java heap đã chứa 1 GiB dữ liệu object ứng dụng.
- Không thay thế đo memory mappings hoặc kiểm tra GC behavior.

**Không bật pre-touch mặc định chỉ để “làm cho AllocateHeapAt chạy nhanh hơn”.** Đây là một trade-off cần benchmark theo thời gian khởi động, footprint và request latency thực tế.

## 18. Heap nhỏ, heap lớn và GC khác nhau: đo trước khi quyết định

Chọn `-Xms/-Xmx` cần xét application live set, tỷ lệ cấp phát object và chiến lược GC.

### Live set và allocation rate

- **Live set**: tập dữ liệu object còn sống sau GC, không thể reclaim ngay.
- **Allocation rate**: số object/byte mới được tạo trong một đơn vị thời gian.
- **GC headroom**: phần dung lượng còn lại cần thiết để collector hoạt động hiệu quả, evacuation, allocation burst và các thuật toán riêng.

Nếu `-Xmx` gần đúng bằng live set và không có headroom, GC có thể tốn rất nhiều công sức, thậm chí OOME, dù alternative-memory device còn hàng trăm GiB. **Nâng dung lượng thiết bị không thay đổi `-Xmx`**, nên vấn đề vẫn xảy ra.

Ngược lại, đặt `-Xmx` cực lớn so với live set chỉ vì có thiết bị lớn có thể làm tăng footprint/mapping và thay đổi các quyết định GC. Không có một tỷ lệ tối ưu cho tất cả ứng dụng.

### Ví dụ hai chính sách lựa chọn collector

**Mục tiêu throughput** (chỉ là lựa chọn cần benchmark):

```bash
java -Xms2g -Xmx8g \
     -XX:+UseParallelGC \
     -jar app.jar
```

**Mục tiêu pause/latency cân bằng** (chỉ là lựa chọn cần benchmark):

```bash
java -Xms2g -Xmx8g \
     -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -jar app.jar
```

Khi gắn `-XX:AllocateHeapAt=...` vào mỗi cấu hình, cần xác minh collector và device combo có thực sự được hỗ trợ trước khi suy diễn về kết quả. Không coi `MaxGCPauseMillis=200` là **cam kết tuyệt đối** pause dưới 200 ms; đó là mục tiêu hướng dẫn cho collector có hỗ trợ.

## 19. Những lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “`AllocateHeapAt` tự tăng `-Xmx` tới kích thước thiết bị.” | Nó chọn nơi đặt heap, không đặt maximum | Cấu hình `-Xmx` riêng, đo capacity |
| “Heap nằm trên PMEM thì không cần `-Xms`.” | Initial/minimum heap vẫn do JVM/cờ sizing quyết định | Chọn Xms theo startup/workload |
| “Heap nằm trên PMEM thì GC tự động tắt.” | GC vẫn quản lý Java objects | Xác nhận GC và log theo JDK |
| “Có NV-DIMM thì `-Xmx` không cần trần.” | Thiết bị có capacity và GC có headroom requirements | Capacity planning và giới hạn rõ |
| “`-Xmx` chính là RSS process.” | RSS gồm nhiều vùng ngoài heap | Quan sát heap + native + OS memory |
| “`-Xms4g` có nghĩa ứng dụng đang dùng 4 GiB objects.” | Initial/committed khác used | Dùng MemoryMXBean, GC logs |
| “Các GC khác nhau sẽ báo đúng cùng byte max heap.” | Layout/survivor/rounding khác | Phân biệt flag và API value |
| “Mọi GC đều dùng mọi filesystem alternative-memory.” | Support phụ thuộc JDK/OS/collector/device | Test combination thật |
| “`MaxGCPauseMillis=200` là SLA tuyệt đối.” | Đây là GC target, không phải hard bound | Đo p95/p99 pauses |
| “Chọn directory thường là đã có DAX/NV-DIMM.” | Đường dẫn không chứng minh memory semantics | Kiểm chứng device/mount |
| “Mapped file nghĩa Java objects được lưu bền.” | GC/VM heap không phải persistent object database | Dùng lưu trữ bền vững đúng nghĩa |
| “Chỉ cần in `Runtime.maxMemory` là biết heap ở PMEM.” | API chỉ nói mức heap, không phải placement | Phối hợp OS mappings/VM logs |
| “Các vùng native/metaspace cũng chuyển hết sang PMEM.” | Oracle nói các vùng đó còn ở DRAM | Dự trù DRAM/native memory |
| “Tăng Xmx là cách giải quyết mọi OOME.” | Có thể là leak, native OOM hoặc device mapping failure | Phân loại lỗi và profile |
| “`-Xms` lớn luôn làm startup nhanh hơn.” | Pre-touch/commit và device có thể làm startup tốn hơn | Benchmark theo workload |
| “Bài Java 10 phải chạy JDK 10 mới dùng được.” | Flag vẫn được tài liệu hóa ở JDK mới | Chọn JDK còn được bảo trì |
| “GC flags tiếp tục hoạt động nghĩa performance y như DRAM.” | Memory latency/bandwidth có thể khác | So benchmark A/B cùng collector |

## 20. Tình huống triển khai có kiểm soát

Giả sử một dịch vụ analytics có live set lớn, muốn khảo sát thiết bị nhớ mới để tăng capacity. Quy trình không nên bắt đầu bằng lệnh launch với `-Xmx` tùy ý. Thay vào đó:

1. **Xác định mục tiêu:** thiếu DRAM capacity, GC pause, throughput hay chi phí phần cứng?
2. **Chọn runtime còn được hỗ trợ**, xác nhận HotSpot có `AllocateHeapAt`.
3. **Xác minh OS/FS/device** cung cấp memory mapping và atomic semantics thích hợp.
4. **Chọn một collector** được dùng ổn định trong baseline và có khả năng tương thích với phương thức placement.
5. **Đặt `-Xms/-Xmx` phù hợp** live set, allocation burst và GC headroom, không theo dung lượng device một cách máy móc.
6. **Đo native DRAM budget**: metaspace, code heap, stacks, buffer và các chi phí VM khác.
7. **Chạy baseline DRAM**, ghi GC logging/JFR và metrics latency/throughput.
8. **Chạy alternative heap cùng flags** chỉ đổi placement; xác minh thực sự map đúng thiết bị.
9. **Kiểm tra lỗi khởi động và tài nguyên**, capacity, permissions, mapping failure và deployment portability.
10. **Đo lại khi nâng JDK/GC** vì behavior và support có thể thay đổi theo build.

Chỉ khi các phép đo chứng minh được lợi ích trên workload thật, mới cân nhắc vận hành dài hạn. **Không lấy công nghệ phần cứng đặc thù làm mặc định chung cho mọi Java service.**

## 21. Bài tập tự kiểm tra

### Câu 1: giải thích ba flag

```bash
java -XX:AllocateHeapAt=/mnt/pmem/heap \
     -Xms2g -Xmx8g \
     -XX:+UseG1GC -jar app.jar
```

**Hỏi:** flag nào chọn device, flag nào giới hạn heap, flag nào chọn collector?

**Đáp án:** `AllocateHeapAt` chọn vị trí của **Java object heap**. `-Xms2g` đặt initial/minimum heap, `-Xmx8g` đặt maximum heap. `-XX:+UseG1GC` yêu cầu collector G1 trên bản hỗ trợ. Ba nhóm nhiệm vụ riêng, không triệt tiêu nhau.

### Câu 2: storage lớn, heap trần nhỏ

**Hỏi:** thiết bị phù hợp có dung lượng 512 GiB nhưng `-Xmx4g`. JVM có được tự dùng 512 GiB cho Java object heap không?

**Đáp án:** Không. `-Xmx4g` vẫn là giới hạn heap; device capacity không thay thế cấu hình đó. Hơn nữa capacity còn phải xét quyền, filesystem, mapping và vùng DRAM ngoài heap.

### Câu 3: bộ thu gom có tắt không?

**Hỏi:** khi object heap nằm trên device khác DRAM, các object Java không còn được GC thu gom?

**Đáp án:** Sai. Java objects vẫn được thu gom theo cơ chế GC đã chọn; cờ GC vẫn có vai trò thông thường. Chỉ có **vị trí memory mapping** của vùng heap được thay đổi. Không tự mặc định mọi GC được hỗ trợ trên mọi device.

### Câu 4: Xms và used

**Hỏi:** `-Xms1g`, sau startup `MemoryUsage.getUsed()` báo 12 MiB. Đây có là lỗi không?

**Đáp án:** Không. Initial/minimum heap và **used object bytes** khác nhau. Runtime có thể dành/commit không gian heap mà app chưa tạo dữ liệu sống tương ứng.

### Câu 5: max heap API thấp hơn flag

**Hỏi:** `-Xmx128m` nhưng `MemoryMXBean.getHeapMemoryUsage().getMax()` là 114 MiB ở một collector. Có khẳng định flag bị JVM bỏ qua?

**Đáp án:** Không. Cần phân biệt giá trị command-line với effective heap value theo collector, cấu trúc heap và rounding. Trong thí nghiệm JDK24, Parallel GC báo 114 MiB dù launcher vẫn hiển thị max heap được cấu hình 128 MiB.

### Câu 6: heap ở device khác nhưng thiếu DRAM

**Hỏi:** tại sao ứng dụng còn cần RAM host khi object heap đã chuyển sang NV-DIMM?

**Đáp án:** Metaspace, code heap, thread stacks và nhiều vùng native khác **không tự chuyển theo** object heap. Cần có DRAM budget và giám sát phần ngoài heap.

### Câu 7: chứng minh placement

**Hỏi:** chương trình `AlternativeHeapLimitsProbe` in `maxHeapMiB=128` và `tests=PASS` có chứng minh heap nằm trên DAX filesystem không?

**Đáp án:** Không. Nó xác nhận heap accounting/collector. Phải kiểm tra runtime flags cùng OS mappings, mount/device và log startup để xác nhận placement.

### Câu 8: khi nào `Xms=Xmx` không phải lựa chọn tốt?

**Hỏi:** ứng dụng có live set thấp, workload dao động lớn, startup rất nhạy và thiết bị nhớ chậm khi pre-touch. Có nên mặc định `-Xms8g -Xmx8g`?

**Đáp án:** Không có đủ căn cứ. Cấu hình đó có thể làm tăng chi phí startup/capacity. Thử `Xms` phù hợp mức tải đầu và để collector quyết định commitment trong ngưỡng `Xmx`, đo throughput/latency/memory theo workload.

## 22. Checklist nhanh trước khi dùng heap trên alternative memory

1. Xác nhận **JDK hiện hành** và HotSpot có cờ `-XX:AllocateHeapAt`.
2. Xác định đúng **memory device + filesystem** cho phép ánh xạ với semantics cần thiết.
3. Xác nhận **vị trí heap** bằng OS mapping/log; không chỉ nhìn `-Xmx`.
4. Giữ **`-Xms` và `-Xmx`** trong ngân sách capacity có chủ đích.
5. Không để `-Xms > -Xmx`.
6. Không coi initial heap là used heap hoặc physical footprint.
7. Nhớ rằng **metaspace/code heap/stacks vẫn cần DRAM**.
8. Xem **collector được chọn**, logging và support matrix trên đúng JDK/OS.
9. Không giả định G1, Parallel, ZGC, Shenandoah có cùng mapping/latency support.
10. Đo **GC pause, throughput, allocation rate, live set** và native memory.
11. Không coi `-Xmx` bằng giới hạn tổng RSS/cgroup.
12. Kiểm tra filesystem capacity, permissions và hệ quả startup nếu mapping không khả dụng.
13. Tránh lạm dụng `AlwaysPreTouch` nếu chưa đo chi phí startup.
14. Đánh giá baseline trên DRAM và phiên bản alternative-memory với **cùng GC/heap flags**.
15. Không dùng `AllocateHeapAt` để kỳ vọng persistence của Java objects.
16. Test lại khi thay **JDK build, collector hoặc firmware/OS/device**.
17. Dùng config deploy nhất quán và có kế hoạch rollback nếu device không được hỗ trợ.
18. Ưu tiên lợi ích đo được, không lấy tên công nghệ làm tiêu chí duy nhất.

## Kết luận

Khi dùng `-XX:AllocateHeapAt` trên một nền tảng và **thiết bị bộ nhớ thay thế được hỗ trợ**, HotSpot có thể **chuyển vị trí bố trí Java object heap**, còn **ý nghĩa của `-Xms`, `-Xmx` và các tùy chọn GC vẫn giữ nguyên**:

- `-Xms` kiểm soát **initial/minimum heap**.
- `-Xmx` kiểm soát **maximum heap**.
- GC tiếp tục thu gom Java objects theo collector và các tham số được chọn.
- Metaspace, code heap, thread stacks và vùng native khác vẫn cần DRAM; placement không tạo persistence hay gỡ bỏ mọi memory limit.

Đừng nhầm **dung lượng thiết bị**, **giới hạn heap**, **heap đang dùng** và **vị trí mapping**. Đây là bốn thông tin khác nhau, cần được quan sát bằng đúng công cụ. Tài liệu Java SE 25/27 hiện hành vẫn ghi nhận tính năng này, nên có thể học và kiểm chứng trên JDK đang được bảo trì; riêng các kết luận về performance hoặc hỗ trợ cụ thể phải dựa trên **thử nghiệm thiết bị/collector thật**, không chỉ output của một chương trình Java.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 — `java` launcher, `-XX:AllocateHeapAt`, `-Xms`, `-Xmx` và GC options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): quan hệ giữa placement, heap bounds, GC, và các vùng DRAM ngoài heap.
- [Oracle Java SE 27 — `java` launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): hợp đồng và danh sách flag HotSpot đang được tài liệu hóa.
- [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): nguồn gốc thiết kế từ Java 10, mục tiêu object heap mapping không sửa application code.
- [Java SE 25 — `MemoryUsage`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): init/used/committed/max và giá trị undefined.
- [Java SE 25 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): Java heap management metrics.
- [Java SE 25 — `GarbageCollectorMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): quan sát collectors và GC metrics.
- [Oracle Java SE 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): lựa chọn và tinh chỉnh GC theo workload.
- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): quan sát native memory ngoài Java heap.
