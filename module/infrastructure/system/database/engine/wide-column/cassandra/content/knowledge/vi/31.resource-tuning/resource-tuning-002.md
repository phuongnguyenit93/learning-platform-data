# Heap, off-heap và bộ nhớ cần cho hệ điều hành

> **Chương:** Tối ưu tài nguyên  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu phân tán, lưu dữ liệu theo mô hình wide-column. Hiệu năng của một nút phụ thuộc đồng thời vào thiết kế phân vùng, truy vấn CQL, replication, compaction, repair, xử lý lỗi và khối lượng yêu cầu từ ứng dụng Java.

## 1. Mục tiêu và vấn đề cần giải quyết

Một nút Cassandra thường dùng **một tiến trình JVM** nhưng không chỉ tiêu thụ bộ nhớ Java heap. Nó còn cần bộ nhớ native/off-heap, vùng ánh xạ tệp và **RAM dành cho hệ điều hành quản lý I/O, đặc biệt là Linux page cache**. Vì vậy, nhìn vào biểu đồ heap rồi kết luận nút còn nhiều RAM là một sai lầm nguy hiểm.

Sau bài học, bạn cần giải thích được:

1. **Heap**, **off-heap/native memory** và **bộ nhớ do hệ điều hành quản lý** khác nhau thế nào.
2. Vì sao đặt **-Xmx** quá lớn có thể khiến đọc SSTable chậm hoặc nút bị OOM kill dù không xuất hiện lỗi Java heap.
3. Những loại dữ liệu Cassandra có thể giữ trên heap, off-heap hoặc trong page cache; đường đi đọc/ghi tác động đến chúng ra sao.
4. Cách lập ngân sách RAM cho nút, container hoặc máy ảo có giới hạn tài nguyên.
5. Cách đo, xác định nguyên nhân và thay đổi cấu hình có kiểm chứng khi gặp GC pause, cạn direct memory, thiếu page cache hoặc Linux OOM kill.

Nguyên tắc xuyên suốt là: **RAM vật lý phải phục vụ đồng thời JVM và hệ điều hành**. Tăng heap chỉ giúp khi heap thực sự là nút thắt; nếu lấy RAM từ page cache hoặc vùng native, tổng thể có thể tệ hơn.

## 2. Bản đồ bộ nhớ của một nút Cassandra

### 2.1. Các lớp bộ nhớ

| Lớp | Lưu những gì? | Ai quản lý / thu hồi? | Dấu hiệu cần theo dõi |
|---|---|---|---|
| **Java heap** | Đối tượng Java, một phần trạng thái request, bộ đệm và cấu trúc trong JVM; một số thành phần Cassandra tùy phiên bản/cấu hình | JVM, garbage collector (GC) | Heap used/committed/max, allocation rate, GC pause, live set sau GC |
| **Off-heap / native** | Direct ByteBuffer, bộ nhớ cấp phát native, một số cấu trúc memtable hoặc metadata SSTable tùy phiên bản/cấu hình, buffer mạng | JVM/native allocator và chính các thành phần sở hữu; không tự động được Java heap GC thu hồi như object thường | Direct/native usage, giới hạn bộ nhớ, RSS, native OOM |
| **Non-heap của JVM** | Metaspace, code cache, thread stacks, một số vùng runtime/JIT | JVM và hệ điều hành; mỗi vùng có giới hạn/cách thu hồi khác nhau | Metaspace, thread count, native memory tracking |
| **File-backed memory và page cache** | Trang dữ liệu của SSTable/index/commitlog được hệ điều hành cache; các trang được ánh xạ bằng **mmap** nếu cấu hình sử dụng | Kernel; các trang sạch có thể được thu hồi dưới áp lực bộ nhớ | MemAvailable, cache activity, major page faults, disk read latency |
| **Kernel, dịch vụ phụ trợ** | Kernel slab, network/socket buffer, journaling/filesystem và agent giám sát, log forwarder, container runtime | Kernel và các tiến trình tương ứng | RAM khả dụng, kernel memory, mức dùng của service khác |

**Heap không phải toàn bộ RAM của JVM.** Tương tự, **off-heap không đồng nghĩa với RAM còn dư cho Cassandra**: nó đã chiếm phần bộ nhớ nằm ngoài heap và có thể cạnh tranh với page cache.

Một cách hình dung:

~~~mermaid
flowchart TB
    R["RAM vật lý / giới hạn bộ nhớ container"] --> J["Tiến trình Cassandra (JVM)"]
    R --> O["Hệ điều hành và các tiến trình khác"]
    R --> P["Linux page cache và file-backed pages"]
    J --> H["Java heap (giới hạn bởi -Xmx)"]
    J --> N["Native/off-heap allocations"]
    J --> M["Metaspace, code cache, thread stacks"]
    J -. "Có thể ánh xạ tệp" .-> P
    O --> K["Kernel, socket, agent..."]
~~~

Sơ đồ mô tả **trách nhiệm sử dụng bộ nhớ**, không phải các vùng vật lý luôn tách biệt tuyệt đối. Trang file-backed được ánh xạ vào tiến trình có thể xuất hiện trong **RSS** của tiến trình **và** trong thống kê cache của hệ điều hành. Vì thế, **không cộng thẳng RSS + Cached** để ước lượng RAM đã sử dụng; làm vậy có thể đếm trùng.

### 2.2. Những phép đo dễ bị nhầm

- **Heap used:** dung lượng đối tượng đang sử dụng trong heap, không phải toàn bộ resident memory của tiến trình.
- **Heap committed:** lượng vùng heap JVM đã cam kết; có thể khác heap used và heap max.
- **-Xmx:** ngưỡng tối đa cho Java heap, **không** phải giới hạn tổng bộ nhớ tiến trình hoặc container.
- **RSS (Resident Set Size):** trang đang resident được tính cho tiến trình, bao gồm nhiều vùng native và file-backed; không phải thước đo trực tiếp của heap leak.
- **VSZ/VIRT:** không gian địa chỉ ảo; vùng đã ánh xạ/đặt chỗ có thể lớn hơn rất nhiều RAM resident.
- **MemAvailable:** ước lượng bộ nhớ có thể cấp cho ứng dụng mới mà không phải swap quá mức; hữu ích hơn chỉ nhìn cột **free**.
- **memory.current** của cgroup v2: mức dùng bộ nhớ được tính vào cgroup, thường bao gồm cả anonymous memory và file cache; so sánh với **memory.max**.

Linux có thể dùng RAM nhàn rỗi làm cache và thu hồi các trang sạch khi cần. **Cached cao không mặc nhiên là lỗi**. Ngược lại, vùng cache bị thu hồi liên tục sẽ khiến truy vấn phải đọc lại từ ổ đĩa, ảnh hưởng đến latency dù tiến trình Java vẫn chạy ổn định.

## 3. Bộ nhớ được sử dụng ở đâu trên đường đọc và ghi?

### 3.1. Ghi dữ liệu

Một thao tác ghi điển hình:

~~~mermaid
flowchart LR
    A["CQL write từ ứng dụng Java"] --> C["Coordinator"]
    C --> R["Replica"]
    R --> L["Append commitlog (đĩa / I/O kernel)"]
    R --> T["Cập nhật memtable (heap/off-heap tùy cấu hình)"]
    T --> F["Flush"]
    F --> S["SSTable trên đĩa"]
    S --> PC["Đọc sau này có thể hưởng lợi từ page cache"]
~~~

**Memtable** là cấu trúc ghi trong bộ nhớ; bộ nhớ dành cho memtable bị giới hạn bằng các cơ chế cấu hình của Cassandra, nhưng việc dùng heap hay off-heap phụ thuộc vào **phiên bản và kiểu memtable**. **Commitlog** là nhật ký trên hệ thống tệp, không nên tính toàn bộ dung lượng commitlog trên đĩa như một khối heap. Ghi file và flush vẫn gây áp lực lên I/O kernel, buffer và page cache.

Khi memtable đạt ngưỡng hoặc cần flush, Cassandra tạo SSTable. Nếu quá trình flush không theo kịp tốc độ ghi, số memtable cần xử lý, áp lực heap/native, I/O và độ trễ ghi có thể tăng. **Tăng heap không sửa được một ổ đĩa đang bị quá tải.**

### 3.2. Đọc dữ liệu

Khi đọc theo partition key, coordinator chọn replica dựa trên replication, topology và consistency level. Trên replica, Cassandra có thể tra memtable và những SSTable liên quan, dùng cấu trúc chỉ mục, Bloom filter, cache nội bộ và bộ nhớ do hệ điều hành cache.

~~~mermaid
flowchart TD
    Q["SELECT theo partition key"] --> R["Replica xử lý đọc"]
    R --> M["Kiểm tra dữ liệu trong memtable"]
    R --> I["Tra metadata, index, Bloom filter..."]
    I --> P{"Trang dữ liệu SSTable đã có trong page cache?"}
    P -->|Có| C["Đọc từ RAM / file-backed page"]
    P -->|Chưa| D["Đọc từ thiết bị lưu trữ"]
    D --> C
    M --> A["Kết hợp dữ liệu và áp dụng ngữ nghĩa truy vấn"]
    C --> A
    A --> Z["Trả kết quả cho coordinator"]
~~~

Đây là sơ đồ khái niệm: đường đọc thực tế còn phụ thuộc phiên bản, SSTable format, loại cache và bố cục dữ liệu. Một số cấu trúc **Bloom filter, index summary, cache** có thể dùng off-heap hoặc cách bố trí khác theo phiên bản/cấu hình. Điểm quan trọng là **cả bộ nhớ Cassandra quản lý và page cache đều có thể ảnh hưởng đến đọc**.

Nếu heap chiếm gần hết RAM, kernel có ít chỗ giữ trang SSTable nóng; số lần đọc thiết bị tăng. Nếu off-heap và memtable tăng không kiểm soát, chúng cũng có thể đẩy page cache ra khỏi bộ nhớ.

### 3.3. Ảnh hưởng của thiết kế truy vấn

Bộ nhớ không được tối ưu chỉ bằng thông số JVM:

- **Partition quá lớn:** đẩy cao khối lượng dữ liệu và thời gian đọc/compaction; yêu cầu đọc có thể giữ trạng thái xử lý lâu hơn.
- **Truy vấn không định vị được partition key:** chạm nhiều replica/phân vùng, làm tăng I/O và tài nguyên xử lý.
- **Client đọc toàn bộ kết quả vào List:** làm tăng heap **của ứng dụng Java**; đồng thời nhiều truy vấn đồng thời có thể tăng tải bộ nhớ phía Cassandra.
- **Page size và concurrency quá lớn:** tăng số hàng/buffer xử lý cùng lúc. Paging phân đoạn dữ liệu truyền về; **không** biến một truy vấn tốn kém thành truy vấn rẻ.
- **Compaction và repair:** tạo tải nền lên CPU, I/O và vùng nhớ đệm; lúc sizing phải tính cả thời điểm hoạt động bảo trì, không chỉ workload ổn định.

Vì Cassandra là hệ phân tán, một truy vấn thiếu tối ưu còn có thể nhân tải lên nhiều replica. Kiểm tra **mô hình wide-column, partition key, thiết kế bảng theo truy vấn và consistency level** trước khi kết luận tăng RAM là giải pháp.

## 4. Heap: chọn kích thước theo live set và hành vi GC

### 4.1. Heap lớn hơn có luôn tốt hơn?

Không. Heap lớn có thể trì hoãn một số đợt thu gom nhưng đồng thời:

1. Lấy bớt RAM mà kernel có thể dùng để cache các trang dữ liệu.
2. Tăng phạm vi bộ nhớ mà GC phải quản lý; hậu quả về pause hoặc CPU phụ thuộc vào collector, live set và tốc độ cấp phát.
3. Che giấu việc ứng dụng đang tạo quá nhiều object hoặc giữ request quá lâu.
4. Khiến tiến trình tiến gần giới hạn RAM của host/container nếu không dự trù native memory.

Heap quá nhỏ thì lại có thể khiến GC dày, promotion/evacuation khó khăn, độ trễ tăng hoặc xuất hiện **java.lang.OutOfMemoryError: Java heap space**.

**Không có một giá trị -Xmx tối ưu cho mọi cluster.** Sizing cần xét phiên bản Cassandra/JDK, collector, số core, loại ổ đĩa, RAM khả dụng, dữ liệu nóng, kích thước partition và kiểu đọc/ghi. Khuyến nghị lịch sử cho một phiên bản JVM không nên được sao chép nguyên sang phiên bản mới.

### 4.2. Cần nhìn cả những gì nằm sau biểu đồ heap

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Heap used **sau** GC | Live set còn lại có tăng liên tục hay ổn định? |
| Heap allocation rate | Object được tạo nhanh đến mức nào? Có request/batch bất thường không? |
| GC pause p95/p99/max | Có pause ảnh hưởng đến latency của replica hoặc coordinator không? |
| GC CPU / tần suất | GC đang tiêu tốn bao nhiêu tài nguyên để duy trì heap? |
| Heap max và committed | Giới hạn và lượng committed hiện tại có đúng theo tiến trình chạy không? |
| Thread count / stack | Có quá nhiều luồng, stack native hoặc executor bị nghẽn không? |

Ví dụ: **heap used khoảng 45%** không đủ chứng minh nút an toàn. Tiến trình có thể dùng nhiều direct buffers, hàng nghìn thread, hoặc page cache liên tục bị thu hồi. Ngược lại, **heap used cao ngay trước GC** chưa đủ chứng minh memory leak; phải xem **live set sau GC** và xu hướng dài hạn.

## 5. Off-heap và native memory: giảm áp lực GC nhưng vẫn dùng RAM

### 5.1. Tại sao Cassandra sử dụng vùng ngoài heap?

Các cấu trúc cấp phát off-heap có thể giảm số object Java mà GC phải quét và hỗ trợ thao tác I/O hiệu quả. Ví dụ thường gặp gồm **direct buffers**, thành phần mạng, dữ liệu memtable hoặc cấu trúc phục vụ đọc SSTable, tùy phiên bản/cấu hình.

Đánh đổi:

- **Ưu điểm:** giảm một phần áp lực heap và GC; có thể hữu ích khi workload tạo nhiều buffer.
- **Chi phí:** vẫn tiêu thụ RAM thật; khó nhận diện nếu chỉ nhìn JVM heap, có thể gây lỗi native allocation, fragment memory hoặc OOM kill ở mức hệ điều hành.
- **Vòng đời:** không nên giả định vùng native được thu hồi tức thì ngay khi tham chiếu Java hết sử dụng. Cách giải phóng phụ thuộc thư viện/allocator và vòng đời cấu trúc dữ liệu.

Một số vùng **metaspace, code cache, thread stacks** cũng nằm ngoài Java heap nhưng không nên gộp cơ học thành “direct memory”. Chúng có giới hạn và tín hiệu sự cố khác nhau.

### 5.2. Đừng dùng một giới hạn để suy ra mọi giới hạn

**-XX:MaxDirectMemorySize** là một giới hạn liên quan đến direct-buffer allocation của JVM, không phải trần tuyệt đối cho **mọi** dạng native/off-heap, memory mapping hay toàn bộ RSS. **-Xmx8g** không đồng nghĩa tiến trình chỉ dùng 8 GiB RAM.

Các cơ chế Cassandra quản lý memtable/cache và JVM quản lý direct memory có thể tác động lẫn nhau. Trước khi chỉnh bất kỳ tham số nào, phải xem **phiên bản đang chạy, tài liệu cấu hình đúng phiên bản và giá trị hiệu lực thực tế**.

Một thay đổi chuyển bộ nhớ từ heap sang off-heap có thể cải thiện GC nhưng vẫn làm **RSS tăng**. Nếu hệ điều hành không còn đủ chỗ cho page cache, độ trễ đọc có thể xấu đi. Do đó phải đo **GC và I/O cùng lúc**.

## 6. Bộ nhớ phải chừa cho hệ điều hành và page cache

Cassandra thường truy cập các file SSTable lớn; kernel cache các trang đã đọc giúp hạn chế truy cập thiết bị lưu trữ. Khi một truy vấn đụng dữ liệu chưa có trong bộ nhớ, tốc độ đọc SSD/NVMe và tình trạng compaction quyết định phần lớn latency của đường đọc đó.

Để vận hành ổn định cần có RAM cho:

- **Page cache / file-backed pages:** giữ dữ liệu và chỉ mục nóng; lượng cần thiết phụ thuộc working set.
- **Kernel và mạng:** TCP/socket buffers, filesystem và kernel data structures.
- **Các tiến trình khác:** exporter, sidecar, log/monitoring agent, container runtime.
- **Đỉnh tải tạm thời:** compaction, repair, streaming, tăng số kết nối và request đồng thời.

**Swap** có thể làm tăng độ trễ không dự đoán được khi một phần bộ nhớ tiến trình bị đưa ra đĩa. Nhiều hệ Cassandra sản xuất hạn chế hoặc tắt swap theo hướng dẫn triển khai, nhưng lựa chọn cụ thể phải phù hợp chiến lược vận hành, cgroup và khả năng chịu lỗi; không thay thế việc sizing RAM đúng. Khi RAM thực sự thiếu, không có swap hoặc cấu hình bảo vệ khác, kernel/cgroup có thể giết tiến trình để giải phóng bộ nhớ.

### 6.1. RSS, page cache và cgroup không cộng đơn giản được

Giả sử trình giám sát hiển thị:

- Cassandra **RSS = 20 GiB**;
- Linux **Cached = 30 GiB**;
- host có **64 GiB RAM**.

Không thể khẳng định Cassandra dùng **20 + 30 = 50 GiB** chỉ từ hai số đó. Một phần file-backed pages có thể đã được tính cả vào RSS và cache. Hãy dùng thêm **MemAvailable**, **cgroup memory.current**, **memory.stat**, **smaps_rollup** và dữ liệu native/heap để phân tách xu hướng.

Trong container, **giới hạn cgroup** thường quan trọng hơn tổng RAM của máy chủ. Một node có thể chạy trên host 128 GiB nhưng bị giới hạn 16 GiB; đặt heap 12 GiB có thể vẫn làm container OOM vì còn native memory, kernel accounting và cache.

## 7. Lập ngân sách RAM: ví dụ có số cụ thể

Giả sử một nút Cassandra **được phép sử dụng 64 GiB RAM**, lưu trữ SSTable trên SSD và chạy cùng vài tiến trình giám sát. Mục tiêu ban đầu có thể là:

| Hạng mục | Ngân sách minh họa |
|---|---:|
| JVM heap tối đa (-Xmx) | 8 GiB |
| Native/off-heap và phần non-heap của JVM (ước lượng để lập kế hoạch) | 10 GiB |
| Kernel, agent và bộ nhớ dự phòng vận hành | 6 GiB |
| **Phần còn lại có thể hỗ trợ page cache và dư địa biến động** | **40 GiB** |
| **Tổng ngân sách** | **64 GiB** |

Phép tính là **64 − 8 − 10 − 6 = 40 GiB**. Đây chỉ là **kịch bản minh họa cách phân bổ**, **không phải khuyến nghị mặc định “8 GiB heap” cho mọi nút 64 GiB**.

Lưu ý khi sử dụng bảng:

1. Các giá trị **native** và **kernel** là ước lượng dựa trên workload; chúng có thể dao động mạnh, nhất là lúc repair/streaming/compaction. Cần đo để hiệu chỉnh.
2. **40 GiB không phải vùng page cache được đặt cứng**. Kernel phân bổ và thu hồi cache động, chia sẻ RAM với phần mềm khác.
3. Nếu quá trình đo cho thấy off-heap thực tế thường lên **18 GiB**, phải giảm phần dự kiến cho cache/dư địa hoặc thay đổi thiết kế tài nguyên.
4. Với container **memory.max = 24 GiB**, **không** lấy tổng RAM của host để tính. Phải lập lại bảng từ 24 GiB hoặc giới hạn thực tế thấp hơn.
5. Ngân sách cần đủ cho **đỉnh tải**, không chỉ số trung bình; duy trì khoảng dự phòng để tránh các đợt tăng đột ngột gây OOM.

Một công thức lập kế hoạch, không phải công thức đo:

~~~text
RAM được phép dùng
  ≈ heap tối đa có thể dùng
  + native/off-heap và non-heap dự kiến
  + kernel/agent/overhead
  + dư địa cho page cache và các đỉnh tải
~~~

Không sử dụng công thức trên để cộng lại các thống kê Linux có vùng chồng lấp như **RSS** và **Cached**. Đây là **ngân sách theo loại trách nhiệm**, không phải phương pháp cộng chỉ số runtime.

### 7.1. Khi nào nên cân nhắc tăng heap?

Chỉ sau khi có bằng chứng rằng:

- Live set heap áp sát giới hạn hoặc JVM liên tục thiếu dung lượng dành cho allocation.
- GC gây pause/CPU đáng kể và vấn đề không chủ yếu xuất phát từ truy vấn, partition nóng hoặc backlog compaction.
- Node còn đủ RAM để duy trì native memory và page cache sau khi tăng heap.
- Có thể thử nghiệm trên node/canary với workload đại diện, theo dõi latency, GC, I/O, memory headroom và rollback.

Nếu tăng heap giúp GC nhưng **disk read latency tăng**, cần đánh giá tác động page cache trước khi giữ cấu hình mới.

## 8. Công cụ quan sát và kiểm tra

Các lệnh sau dùng trong môi trường Linux và Cassandra/JDK tương thích. **Không chạy tất cả lệnh trên production chỉ vì thấy RAM cao**; chọn lệnh theo câu hỏi vận hành và quyền truy cập. Tên metric hay trường in ra có thể khác giữa các phiên bản Cassandra, JDK và Linux.

### 8.1. Quan sát Cassandra

~~~bash
# Tổng quan node: heap, off-heap (nếu phiên bản hiển thị), load, uptime...
nodetool info

# Thống kê bảng: memtable, SSTable, Bloom filter, off-heap, latency...
nodetool tablestats app.events_by_tenant_day

# Công việc compaction đang chạy / chờ
nodetool compactionstats

# Thread pool và pending tasks
nodetool tpstats

# Thống kê GC nếu phiên bản cung cấp
nodetool gcstats
~~~

Tên **app.events_by_tenant_day** chỉ là bảng minh họa; thay bằng keyspace/bảng thực tế. Nếu phiên bản không hỗ trợ tham số hoặc trường metric cụ thể, dùng cú pháp đúng từ phiên bản đang vận hành.

Để tìm nguyên nhân đọc chậm, đối chiếu số liệu **từ ít nhất hai phía**: ứng dụng/driver (p95/p99, timeout, concurrency) và node Cassandra (heap/GC, compaction, disk I/O, memtable, cache). **Tăng latency trong lúc compaction chạy** không tự chứng minh thiếu heap.

### 8.2. JVM và tiến trình

~~~bash
# Thay <pid> bằng PID thực của tiến trình Cassandra.
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info

# Chỉ có dữ liệu hữu ích khi JVM đã bật Native Memory Tracking.
jcmd <pid> VM.native_memory summary

# Quan sát nhanh vùng resident/virtual, phù hợp quyền truy cập.
ps -o pid,rss,vsz,%mem,cmd -p <pid>
grep -E 'VmRSS|VmHWM|VmSize|Threads' /proc/<pid>/status
~~~

**Native Memory Tracking (NMT)** thường phải được bật từ lúc khởi động JVM (ví dụ chọn **-XX:NativeMemoryTracking=summary**, tùy JDK). NMT có overhead và **không đo được mọi cấp phát native của thư viện ngoài JVM**; vì thế không nên dùng NMT làm kiểm toán đầy đủ tất cả off-heap. Công cụ **jcmd** cũng có thể yêu cầu cùng người dùng hệ điều hành và phiên bản JDK tương thích.

Khi cần phân tích sâu RSS, **/proc/<pid>/smaps_rollup** cung cấp thống kê resident/PSS cùng phân loại nhất định trên Linux hỗ trợ. Dùng cho điều tra có chủ đích; không cần thu thập quá dày.

### 8.3. Hệ điều hành / container

~~~bash
free -h
grep -E 'MemTotal|MemAvailable|Cached|SReclaimable|SwapTotal|SwapFree' /proc/meminfo

# Cgroup v2; đường dẫn thay đổi theo môi trường triển khai.
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events

# Kernel log / sự kiện OOM tùy quyền và nền tảng.
dmesg
~~~

Ở cgroup v1, Kubernetes hoặc môi trường có cgroup lồng nhau, đường dẫn và cách thống kê có thể khác. **memory.max = max** trong cgroup v2 nghĩa là cgroup đó không đặt giới hạn hữu hạn tại cấp đang xem; còn phải xét các cấp cha. **memory.events** giúp phát hiện các sự kiện chạm giới hạn, OOM và OOM kill tại cgroup tương ứng.

Nếu ứng dụng Java báo **connection reset** hoặc mất kết nối đột ngột, cần kiểm tra cả sự kiện OOM kill của node/container; JVM bị kill không nhất thiết kịp ghi stack trace **OutOfMemoryError**.

## 9. Chẩn đoán theo triệu chứng

| Triệu chứng | Điều cần phân biệt | Hướng xử lý dựa trên bằng chứng |
|---|---|---|
| **GC liên tục, pause dài, heap sau GC cao** | Live set lớn, tạo object quá nhanh, request quá nhiều, heap thiếu hoặc leak | Đo allocation/live set; kiểm tra request và partition; chỉ cân nhắc chỉnh heap/GC khi còn RAM |
| **java.lang.OutOfMemoryError: Java heap space** | Heap thực sự cạn, dữ liệu/object giữ lâu | Phân tích heap và workload; tránh tăng heap trước khi hiểu nguyên nhân |
| **OutOfMemoryError: Direct buffer memory** | Giới hạn/cấp phát direct buffer; không đồng nghĩa heap cạn | Kiểm tra direct/native usage, JDK flags, thư viện networking, concurrency |
| **Process/container bị OOM kill, heap nhìn vẫn thấp** | RSS/native, cache, giới hạn cgroup hoặc tiến trình khác | Đọc memory.events, log kernel, memory.current/max, RSS và NMT; điều chỉnh ngân sách tổng |
| **GC tốt nhưng truy vấn đọc chậm, disk I/O tăng** | Page cache thiếu, dữ liệu nóng vượt RAM, nhiều SSTable, compaction/tombstone | Đo MemAvailable, page faults, disk latency, SSTable/compaction; xem lại access pattern |
| **RSS tăng cùng lúc với off-heap** | Native allocation hoặc file-backed pages resident tăng | Phân tích NMT, smaps_rollup và memory.stat theo thời gian; không gọi ngay là leak |
| **Ghi chậm khi flush/compaction dồn** | Disk throughput, memtable flush, compaction backlog, commitlog I/O | Kiểm tra compactionstats, tpstats, disk utilization và phân vùng nóng |
| **Repair/streaming làm node hụt RAM** | Hoạt động nền đồng thời dùng I/O, buffer, network và cache | Điều phối concurrency/cửa sổ bảo trì, theo dõi đỉnh tải và dư địa RAM |
| **Driver Java giữ nhiều kết quả, app OOM** | Heap **của ứng dụng** khác heap **của Cassandra** | Sử dụng paging, giới hạn số request đồng thời, xử lý theo luồng thay vì gom hết |

### Ba bẫy chẩn đoán

**Bẫy 1 — Thấy Cached lớn và kết luận rò rỉ RAM.** Cache có thể là hành vi bình thường của kernel. Kiểm tra **MemAvailable**, paging/reclaim, độ trễ I/O và dấu hiệu cạn bộ nhớ thực tế.

**Bẫy 2 — Thấy heap thấp và kết luận JVM không thể gây OOM.** Native memory, thread stacks, mmap/file cache được tính vào cgroup và các tiến trình khác vẫn có thể làm node vượt giới hạn.

**Bẫy 3 — Thấy đọc chậm và tăng heap.** Đọc SSTable cần page cache và ổ đĩa; heap tăng có thể làm phần bộ nhớ này bị thu hẹp. Kiểm tra truy vấn, kích thước partition, SSTable/tombstone, compaction và OS trước.

## 10. Cấu hình, thay đổi và kiểm chứng an toàn

### 10.1. Tìm cấu hình đang **có hiệu lực**

Cassandra và JDK có thể khác nhau về vị trí tập tin cấu hình, cơ chế tính heap mặc định, collector và các tên tùy chọn. Trước khi thay đổi, hãy ghi lại:

- Phiên bản **Cassandra** và **JDK** đang chạy.
- Giá trị hiệu lực **-Xms**, **-Xmx**, GC collector và direct/native-related flags (kiểm tra bằng **jcmd VM.flags** khi phù hợp).
- Giới hạn RAM của host/VM và **cgroup**, số tiến trình chia sẻ máy.
- Cấu hình memtable, cache và các giới hạn liên quan **đúng với phiên bản Cassandra**.
- Giá trị baseline: độ trễ p50/p95/p99, timeout, GC pause, RSS, MemAvailable, disk I/O, compaction và trạng thái repair.

Ví dụ các JVM flags sau chỉ mô tả **ý nghĩa** của cấu hình, không phải cấu hình khuyến nghị cố định:

~~~text
-Xms8g    # dung lượng heap ban đầu
-Xmx8g    # dung lượng heap tối đa
~~~

Trong một số bản phân phối/phiên bản Cassandra, heap được đặt qua **cassandra-env.sh**, biến môi trường hoặc tệp tùy chọn JVM; cơ chế thực tế cần kiểm chứng trên node. Đừng thêm tùy chọn trùng nhau ở nhiều nơi rồi giả định lệnh cuối chắc chắn có hiệu lực.

Các tham số như **memtable_heap_space**, **memtable_offheap_space** hoặc **memtable_allocation_type** (nếu được phiên bản đang chạy hỗ trợ) có ý nghĩa riêng; giới hạn vùng memtable không phải giới hạn tổng RAM và mức off-heap thực tế còn phụ thuộc cách cấu hình. Xem cấu hình có hiệu lực trước khi điều chỉnh.

### 10.2. Quy trình điều chỉnh theo số liệu

1. **Khoanh vùng triệu chứng:** heap OOM, direct/native OOM, cgroup OOM, GC pause hay thiếu page cache? Xác nhận bằng nhiều nguồn số liệu.
2. **Chụp baseline:** cùng loại workload và khung giờ, lưu latency, throughput, GC, RSS, MemAvailable, disk I/O, timeout và compaction.
3. **Lập ngân sách RAM:** dựa trên giới hạn thực tế và đỉnh tải; chừa không gian cho kernel, native allocations và page cache.
4. **Thay một nhóm tham số có liên quan:** ví dụ sizing heap **hoặc** giới hạn concurrency/memtable, tránh sửa nhiều yếu tố khiến không truy nguyên được kết quả.
5. **Kiểm chứng canary hoặc rollout từng phần:** quan sát cả đọc/ghi, retry, GC, I/O, số replica sẵn sàng, mức nhất quán và tải lúc compaction/repair.
6. **So với baseline và giữ phương án rollback:** thay đổi được chấp nhận khi cải thiện mục tiêu mà không làm xấu những chỉ số tài nguyên khác hoặc giảm độ ổn định cluster.

Không nên restart đồng thời mọi replica chỉ để áp dụng một thay đổi memory. Phân tán thao tác bảo trì theo quy trình cluster và mức nhất quán đang sử dụng, theo dõi replica availability ở từng bước.

## 11. Liên hệ Java driver, replication và vận hành Cassandra

Một truy vấn Java thực thi **SELECT** có thể được phân trang:

~~~java
// Giả sử session, prepared, tenantId và eventDay đã được khởi tạo.
var statement = prepared.bind(tenantId, eventDay)
        .setPageSize(100);
var result = session.execute(statement);

for (var row : result) {
    // Xử lý từng hàng; tránh đưa toàn bộ kết quả vào List lớn.
    processRow(row);
}
~~~

**Page size = 100** là kích thước trang yêu cầu driver/server sử dụng, không phải lời bảo đảm mỗi truy vấn chỉ đọc tổng cộng 100 hàng hoặc bộ nhớ tối đa cố định. Việc duyệt hết kết quả có thể tiếp tục nạp nhiều trang; nếu gọi đồng thời quá nhiều truy vấn, node Cassandra và ứng dụng Java đều chịu áp lực. Trong ứng dụng thật, **processRow** là hàm do ứng dụng định nghĩa và việc dùng **var** yêu cầu phiên bản Java hỗ trợ.

Những yếu tố bổ sung phải tính chung khi tối ưu RAM:

- **Replication:** mỗi replica tiêu thụ tài nguyên phục vụ dữ liệu nó lưu; replication factor tăng có thể làm tăng dung lượng lưu trữ và công việc bảo trì trên toàn cluster. Consistency level quyết định số phản hồi cần thiết và có thể ảnh hưởng latency/tải, nhưng không thay thế sizing RAM.
- **Compaction:** đọc/ghi nhiều SSTable, dùng CPU, I/O và bộ đệm; cần dự trù lúc khối lượng compaction đạt đỉnh.
- **Repair / streaming:** truyền dữ liệu giữa các nút, tạo áp lực I/O/network và bộ nhớ phụ trợ. Kế hoạch bảo trì phải tránh dồn nhiều tác vụ nặng không cần thiết.
- **Thiết kế bảng theo truy vấn:** partition key/bucket hợp lý giảm hotspot, read amplification và khối lượng dữ liệu mỗi yêu cầu.
- **Xử lý lỗi:** retry không giới hạn khi node thiếu tài nguyên có thể khuếch đại vấn đề. Điều tiết concurrency, giới hạn timeout và giữ idempotency phù hợp từng loại ghi.

Tóm lại, **tối ưu bộ nhớ chỉ có ý nghĩa khi đặt cạnh mô hình dữ liệu, tốc độ truy vấn và công việc nền của toàn bộ cluster**.

## 12. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập A — Tìm nguy cơ ở container 24 GiB

Một Cassandra container có **memory.max = 24 GiB**, **-Xmx = 18 GiB**. Theo số liệu đo, native/non-heap và tiến trình phụ có thể lên **5 GiB** trước khi tính đến page cache/overhead còn lại.

- Phần ngân sách lý thuyết còn lại là bao nhiêu?
- Khi compaction/repair đẩy native usage cao hơn dự kiến, lỗi nào có thể xuất hiện?
- Vì sao **Java heap used chỉ 50%** vẫn không đủ để kết luận an toàn?

**Gợi ý:** 24 − 18 − 5 = **1 GiB** trước page cache và overhead chưa tính; khoảng trống cực nhỏ, có thể gây áp lực cache hoặc OOM kill. **-Xmx** là trần heap, không phải toàn bộ mức dùng của tiến trình. Cần dựa trên resident/current usage và đỉnh tải thực tế.

### Bài tập B — Đọc chậm sau khi tăng heap

Một node có heap từ **8 GiB** tăng lên **16 GiB**. Sau thay đổi, GC pause giảm nhưng disk read latency và p99 SELECT tăng.

Giải thích giả thuyết hợp lý và đề xuất cách kiểm chứng.

**Gợi ý:** RAM có thể bị chuyển từ page cache sang heap, làm tăng đọc đĩa. So sánh **MemAvailable**, page faults, cache reclaim, I/O latency và số SSTable trước/sau trên cùng workload; đồng thời loại trừ compaction, thay đổi dữ liệu nóng và lỗi thiết bị. Có thể cần rollback hoặc sizing lại thay vì chỉ nhìn GC.

### Bài tập C — Phân biệt lỗi

Cho ba tín hiệu:

1. **java.lang.OutOfMemoryError: Java heap space**;
2. **java.lang.OutOfMemoryError: Direct buffer memory**;
3. Kernel/cgroup báo **oom_kill**, Cassandra biến mất không có Java stack trace.

Hãy ghép từng tín hiệu với phép đo ưu tiên.

**Gợi ý:** (1) heap/live set và GC; (2) direct/native allocations, giới hạn liên quan và concurrency; (3) memory.current/max/events, kernel logs, RSS và memory accounting. Không gộp mọi trường hợp thành “tăng -Xmx”.

### Câu hỏi kiểm tra

1. **Vì sao RSS có thể bao gồm những trang cũng được tính trong Linux page cache?**  
   Vì tiến trình có thể ánh xạ và giữ resident các trang file-backed mà kernel đang cache; các chỉ số này có thể chồng lấp.
2. **Tại sao không tối ưu Cassandra bằng cách cấp gần hết RAM cho heap?**  
   Native/off-heap, hệ điều hành, page cache và đỉnh tải nền vẫn cần RAM.
3. **Có thể kết luận native memory leak từ một lần thấy RSS cao không?**  
   Chưa; cần phân rã memory và quan sát xu hướng theo thời gian, phân biệt file-backed pages, allocator, workload và GC.
4. **Page size trong Java driver có giải quyết tận gốc truy vấn qua quá nhiều phân vùng không?**  
   Không; phải thiết kế lại access pattern và partition key.
5. **Compaction hoặc repair liên quan gì đến lập ngân sách RAM?**  
   Chúng làm thay đổi tải I/O, network, buffer và đôi khi đỉnh mức dùng bộ nhớ, nên cần tính trong kiểm chứng/capacity planning.

## 13. Kết luận

Đối với Apache Cassandra, **Java heap**, **native/off-heap** và **bộ nhớ hệ điều hành/page cache** cùng chia sẻ một ngân sách RAM hữu hạn. Heap đủ dùng giúp giảm áp lực cấp phát và GC; off-heap phù hợp có thể giảm số object do GC xử lý; còn page cache giúp giảm số lần đọc SSTable từ thiết bị. Không có vùng nào có thể được tối ưu riêng mà bỏ qua hai vùng còn lại.

Muốn tìm cấu hình hợp lý, hãy xác định giới hạn RAM thực, đo live set/GC, RSS/native memory, MemAvailable/cache và disk I/O trên cùng workload, rồi điều chỉnh từng bước. **Partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair và hành vi ứng dụng Java** đều ảnh hưởng nhu cầu bộ nhớ; xử lý đúng nguyên nhân tại từng tầng mới giúp Cassandra có độ trễ ổn định và tránh các sự cố OOM.
