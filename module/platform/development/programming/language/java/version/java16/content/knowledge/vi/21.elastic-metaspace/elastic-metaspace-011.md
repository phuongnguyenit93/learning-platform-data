# Bật Native Memory Tracking và đối chiếu VM.native_memory

Khi ứng dụng Java tăng mức dùng RAM, chỉ nhìn Java heap thường không đủ để tìm nguyên nhân. Process còn dùng native memory cho class metadata, thread stack, code cache, cấu trúc garbage collector và nhiều thành phần nội bộ của JVM. **Native Memory Tracking (NMT)** là tính năng của HotSpot giúp theo dõi các nhóm bộ nhớ nội bộ đó. Lệnh chẩn đoán **jcmd VM.native_memory** đọc số liệu NMT và cho phép so sánh với một baseline đã tạo trước đó.

Trong Java 16, NMT đã có thể dùng cùng các cải tiến Elastic Metaspace để quan sát nhóm bộ nhớ Class. Cách dùng này vẫn áp dụng trong các JDK HotSpot hiện đại. Bài học tập trung vào bật đúng chế độ, tạo baseline sau warm-up, đọc **summary.diff** và **detail.diff**, rồi đối chiếu kết quả với Metaspace, RSS và giới hạn bộ nhớ của hệ điều hành.

## 1. NMT và VM.native_memory là gì?

NMT là tính năng chẩn đoán của **Java HotSpot VM**. Nó ghi nhận mức dùng bộ nhớ nội bộ do HotSpot quản lý và tổng hợp theo subsystem hoặc theo allocation call site.

**VM.native_memory** là diagnostic command mà **jcmd** gửi tới JVM để đọc dữ liệu NMT. Hai tên này không phải hai hệ thống theo dõi độc lập:

| Thành phần | Vai trò |
|---|---|
| Native Memory Tracking | Cơ chế ghi nhận các nhóm native memory nội bộ của HotSpot. |
| **-XX:NativeMemoryTracking** | Tùy chọn JVM chọn mức tracking khi khởi động. |
| jcmd | Công cụ gửi lệnh chẩn đoán tới JVM đang chạy. |
| VM.native_memory | Lệnh trong JVM để in báo cáo, tạo baseline và xem chênh lệch. |

NMT chỉ có trong HotSpot và các bản phân phối JDK dựa trên HotSpot có hỗ trợ tính năng này. Đây không phải API bắt buộc của Java SE; không giả định mọi JVM vendor đều cung cấp cùng cờ hoặc cùng output.

## 2. NMT giúp quan sát những vùng nhớ nào?

NMT nhóm memory theo subsystem. Các nhóm thường gặp gồm:

| Nhóm | Nội dung điển hình |
|---|---|
| Java Heap | Vùng địa chỉ và bộ nhớ đã commit dành cho heap. |
| Class | Class metadata, Metaspace và class space. |
| Thread | Cấu trúc thread, stack và các vùng nhớ liên quan. |
| Code | Code cache và mã máy được sinh ra. |
| GC | Cấu trúc dữ liệu và vùng nhớ phục vụ garbage collector. |
| Compiler | Bộ nhớ nội bộ của compiler. |
| Internal | Bộ nhớ JVM không thuộc các nhóm riêng khác. |
| Symbol | Symbol và dữ liệu liên quan. |
| Native Memory Tracking | Bộ nhớ dùng chính NMT để theo dõi. |
| Module, Logging, Arguments, Arena Chunk | Bộ nhớ phục vụ các subsystem tương ứng. |

Danh sách category có thể thay đổi theo JDK release và cấu hình. Một số bản có thêm **GCCardSet**; đây là nhóm liên quan remembered set của G1. Hãy đọc category thực tế trong output của JVM đang vận hành.

NMT đặc biệt hữu ích khi:

- Heap tương đối ổn định nhưng RSS hoặc memory của container tiếp tục tăng.
- Muốn biết nhóm Class, Thread, Code hay GC đang tăng.
- Cần so sánh native memory trước và sau một workload.
- Điều tra mức dùng Metaspace hoặc Compressed Class Space trong ứng dụng có nhiều class loader.
- Muốn tìm allocation call site của các vùng nhớ nội bộ HotSpot khi bật detail tracking.

## 3. NMT không đo toàn bộ RAM của process

Đây là giới hạn quan trọng nhất khi đọc báo cáo. NMT theo dõi bộ nhớ nội bộ của HotSpot, không phải công cụ đo mọi allocation native trên process.

NMT không theo dõi đầy đủ:

- Native memory do mã bên ngoài JVM cấp phát, chẳng hạn thư viện JNI hoặc thư viện C/C++ của bên thứ ba.
- Allocation do JDK class libraries thực hiện.
- Toàn bộ bộ nhớ liên quan Class Data Sharing (CDS archive).
- Mọi phần RSS, shared mapping, page cache hoặc memory được hệ điều hành tính vào container.

Do đó, tổng **committed** trong NMT không nhất thiết bằng RSS của process hoặc **memory.current** trong cgroup. Nếu RSS tăng mà NMT gần như không đổi, cần kiểm tra native library, JNI, direct/mapped buffer, memory mapping và các số liệu của hệ điều hành.

NMT cũng không phải heap profiler. Dù báo cáo có category Java Heap, nó không cho biết object Java nào đang giữ nhiều heap nhất. Dùng heap dump, JFR hoặc công cụ phân tích heap khi câu hỏi nằm ở object retention.

## 4. Chọn summary hay detail

HotSpot cung cấp ba mode:

| Mode | Cách thu thập | Khi nên dùng |
|---|---|---|
| off | Tắt NMT; đây là mặc định. | Khi không cần tracking. |
| summary | Tổng hợp bộ nhớ theo subsystem/category. | Theo dõi xu hướng và xác định nhóm đang tăng. |
| detail | Bổ sung thông tin allocation theo call site và virtual memory region. | Điều tra sâu sau khi đã xác định nhóm đáng nghi. |

Ví dụ bật summary:

~~~bash
java -XX:NativeMemoryTracking=summary -jar inventory-service.jar
~~~

Bật detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar inventory-service.jar
~~~

**summary** thường là điểm bắt đầu hợp lý vì báo cáo dễ đọc hơn. **detail** tạo thêm dữ liệu về call site và virtual memory map, hữu ích khi cần xác định vị trí cấp phát nhưng cũng làm tăng lượng thông tin cần xử lý.

## 5. Bật NMT lúc khởi động JVM

NMT phải được bật bằng JVM option **trước khi ứng dụng chạy**. Không thể bật hoặc khởi động lại NMT bằng **jcmd** trên một JVM vốn khởi động khi NMT đang tắt.

Nếu process đã chạy mà chưa bật NMT:

1. Lên lịch restart theo quy trình vận hành.
2. Thêm **-XX:NativeMemoryTracking=summary** hoặc **detail** vào cấu hình khởi động.
3. Khởi động lại ứng dụng.
4. Xác nhận JVM mới đã nhận option.
5. Dùng **jcmd** để lấy báo cáo.

Không nhầm việc chạy **jcmd <pid> VM.native_memory** với thao tác bật NMT. Lệnh này chỉ truy vấn dữ liệu mà JVM đã thu thập.

### 5.1. Xác nhận option đang có hiệu lực

Có thể kiểm tra các flag của JVM:

~~~bash
jcmd 12345 VM.flags
~~~

Hoặc xem command line của process:

~~~bash
jcmd 12345 VM.command_line
~~~

Thay **12345** bằng PID thực tế. Dùng **jcmd <pid> help VM.native_memory** để xem cú pháp command được hỗ trợ bởi đúng runtime.

### 5.2. Cấu hình service hoặc container

Đặt option trong đúng cấu hình khởi động của ứng dụng:

- systemd service: thêm vào ExecStart hoặc file cấu hình JVM mà service đọc.
- Container: thêm vào command/entrypoint hoặc biến cấu hình JVM của image.
- Script: thêm vào danh sách JVM options trước -jar, -m hoặc main class.
- Launcher jpackage: cấu hình Java options cho launcher của ứng dụng.

Không đặt option vào môi trường toàn cục nếu chỉ một service cần NMT. Ghi lại mode đang dùng trong cấu hình triển khai để người vận hành biết process có chịu overhead của tracking hay không.

## 6. Hiểu chi phí khi bật NMT

Tài liệu Oracle ghi nhận bật NMT có thể làm hiệu năng JVM giảm khoảng **5–10%**, tùy workload và mức tracking. NMT còn thêm hai machine words vào header của các allocation qua malloc; bộ nhớ do chính NMT sử dụng cũng được NMT theo dõi.

Vì vậy:

- Đo hiệu năng trước và sau khi bật NMT trên workload đại diện.
- Bắt đầu với **summary** nếu mục tiêu chỉ là theo dõi category.
- Dùng **detail** trong giai đoạn điều tra cần call site.
- Không bật **detail** đại trà trên toàn bộ fleet nếu chưa đánh giá overhead và chi phí lưu trữ output.
- Khi điều tra production, chọn canary hoặc một nhóm instance có thể quan sát và so sánh.

Không nên diễn giải 5–10% như một con số cố định cho mọi ứng dụng. Tác động thực tế phụ thuộc JVM, workload, mức allocation và môi trường.

## 7. Dùng jcmd để tìm JVM và đọc báo cáo

**jcmd** nằm trong thư mục bin của JDK. Liệt kê các JVM có thể truy cập:

~~~bash
jcmd -l
~~~

Sau khi xác định PID, đọc báo cáo summary:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

Đọc báo cáo detail:

~~~bash
jcmd 12345 VM.native_memory detail
~~~

Có thể chọn đơn vị:

~~~bash
jcmd 12345 VM.native_memory summary scale=MB
~~~

Hoặc:

~~~bash
jcmd 12345 VM.native_memory detail scale=MB
~~~

**jcmd** phải chạy trên cùng máy với JVM và bằng effective user/group phù hợp với process đã khởi chạy JVM. Trong môi trường container, thường cần chạy lệnh trong đúng container hoặc PID namespace để thấy và attach được process.

Nếu **jcmd** không thấy process hoặc không attach được, kiểm tra PID namespace, user, quyền truy cập, container boundary và JDK tool đang dùng. Đừng kết luận NMT không hoạt động chỉ từ một lỗi attach.

## 8. Tạo baseline và so sánh với summary.diff

Baseline là ảnh chụp số liệu tại một thời điểm. NMT dùng baseline gần nhất để tính chênh lệch cho những lần truy vấn tiếp theo.

Quy trình nên dùng:

1. Khởi động JVM với NMT đã bật.
2. Chờ ứng dụng hoàn tất startup và warm-up.
3. Chạy workload đại diện ở trạng thái ổn định.
4. Tạo baseline.
5. Chạy workload cần điều tra.
6. Lấy **summary.diff**.
7. Lặp lại theo nhiều khoảng thời gian để phân biệt tăng trưởng ngắn hạn với xu hướng kéo dài.

Tạo baseline:

~~~bash
jcmd 12345 VM.native_memory baseline
~~~

Đọc chênh lệch tổng hợp:

~~~bash
jcmd 12345 VM.native_memory summary.diff scale=MB
~~~

**summary.diff** hiển thị thay đổi so với baseline gần nhất. Dấu **+** biểu thị tăng và dấu **-** biểu thị giảm. Hãy so sánh từng category, đặc biệt là **committed**, thay vì chỉ nhìn dòng Total.

### 8.1. Vì sao nên tạo baseline sau warm-up?

Trong startup, JVM còn nạp class, tạo thread, khởi tạo compiler, GC, logging và các subsystem khác. Nếu tạo baseline ngay khi process vừa chạy, phần tăng tự nhiên trong warm-up sẽ xuất hiện trong diff và có thể làm nhiễu kết quả.

Với hệ thống plugin hoặc ứng dụng có tác vụ định kỳ, baseline nên được tạo sau khi:

- Startup hoàn tất.
- Cache và connection pool đã đạt trạng thái vận hành đại diện.
- Các class và framework chính đã được nạp.
- Workload nền đã ổn định.

Ghi lại thời điểm, workload và trạng thái ứng dụng khi tạo baseline để người khác có thể tái hiện phép đo.

## 9. Dùng detail.diff để tìm allocation call site

Nếu **summary.diff** cho thấy một category tăng bất thường nhưng chưa chỉ ra nguyên nhân, có thể dùng detail tracking.

JVM phải được khởi động với:

~~~bash
java -XX:NativeMemoryTracking=detail -jar inventory-service.jar
~~~

Tạo baseline:

~~~bash
jcmd 12345 VM.native_memory baseline
~~~

Sau workload:

~~~bash
jcmd 12345 VM.native_memory detail.diff scale=MB
~~~

Detail báo cáo các allocation site và vùng virtual memory mà NMT theo dõi. Nó giúp định hướng tới code path nội bộ HotSpot đang cấp phát bộ nhớ.

Detail không phải stack trace của mọi object Java và cũng không xác định trực tiếp dòng code ứng dụng đã làm rò rỉ. Nếu call site dẫn tới một subsystem của JVM, cần kết hợp workload, JFR, log GC và công cụ chuyên biệt để tìm nguyên nhân cấp cao hơn.

## 10. Đọc cấu trúc output của VM.native_memory

Một báo cáo NMT thường có dạng rút gọn như sau:

~~~text
Native Memory Tracking:
Total: reserved=...KB, committed=...KB

- Java Heap (reserved=...KB, committed=...KB)
- Class (reserved=...KB, committed=...KB)
    (classes #...)
    (Metadata: reserved=...KB, committed=...KB)
    (Class space: reserved=...KB, committed=...KB)
- Thread (reserved=...KB, committed=...KB)
- Code (reserved=...KB, committed=...KB)
- GC (reserved=...KB, committed=...KB)
- Compiler (reserved=...KB, committed=...KB)
- Internal (reserved=...KB, committed=...KB)
- Native Memory Tracking (reserved=...KB, committed=...KB)
~~~

Đây là sơ đồ minh họa các trường thường thấy, không phải output cố định cho mọi JDK. Category và cấu trúc chi tiết có thể thay đổi.

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| reserved | Không gian địa chỉ ảo JVM đã reserve cho subsystem. |
| committed | Phần bộ nhớ JVM đã commit để subsystem sử dụng. |
| malloc | Phần allocation thông qua malloc được ghi nhận. |
| mmap | Phần vùng nhớ được ánh xạ qua memory mapping. |
| classes # | Số class được nạp tại thời điểm báo cáo, kèm phân loại nếu có. |
| used | Số liệu dùng trong một số phần báo cáo chi tiết, ví dụ metadata hoặc class space. |
| free | Phần dung lượng còn trống trong vùng hoặc chunk được báo cáo. |
| tracking overhead | Bộ nhớ NMT tự sử dụng để thu thập số liệu. |

## 11. Phân biệt reserved và committed

Hai số này thường bị nhầm lẫn:

- **Reserved** là không gian địa chỉ ảo đã được JVM dành trước. Nó không đồng nghĩa toàn bộ vùng đó đang chiếm RAM vật lý.
- **Committed** là phần vùng nhớ đã được JVM commit để sử dụng. Đây là chỉ số quan trọng khi đánh giá mức tăng native memory do JVM quản lý.

Ví dụ, JVM có thể reserve một vùng heap lớn theo **-Xmx**, nhưng chỉ commit một phần theo nhu cầu hiện tại. Vì vậy, reserved cao không tự động là lỗi.

Committed cũng không phải phép đo RSS chính xác từng byte. RSS phản ánh các trang memory đang resident theo cách hệ điều hành tính; NMT mô tả các vùng bộ nhớ JVM quản lý. Hai công cụ nhìn memory ở hai lớp khác nhau.

Khi điều tra:

1. So sánh committed theo category giữa các baseline.
2. Kiểm tra reserved tăng hay chỉ committed tăng.
3. Đối chiếu RSS hoặc memory của cgroup.
4. Nếu RSS tăng nhiều hơn NMT, tìm allocation ngoài phạm vi NMT.

## 12. Đọc category Class trong bối cảnh Elastic Metaspace

Với Elastic Metaspace, category **Class** là phần cần quan sát đầu tiên. Báo cáo có thể hiển thị:

- Số class đã nạp.
- **Metadata**: vùng metadata của class.
- **Class space**: vùng Compressed Class Space nếu cơ chế tương ứng được bật.
- reserved, committed, used, free và các allocation liên quan.

Ví dụ diễn giải:

| Dấu hiệu | Hướng điều tra |
|---|---|
| Số class và Class committed cùng tăng | Ứng dụng có thể đang nạp class mới; kiểm tra workload, plugin, proxy và class loader. |
| Số class ổn định nhưng Class committed tăng | Xem chunk, allocator và các thay đổi nội bộ; đối chiếu thêm VM.metaspace. |
| Class used tăng qua từng chu kỳ deploy | Kiểm tra class loader cũ có còn reachable hoặc class động có được tạo lặp lại không. |
| Class used giảm nhưng committed chưa giảm | Có thể JVM giữ vùng đã commit để tái sử dụng; chưa đủ để kết luận leak. |
| Compressed Class Space tăng nhanh | Kiểm tra số class, compressed class pointers và vùng class space. |

NMT giúp nhìn category Class trong tổng thể native memory. Để đọc allocator và class loader chi tiết hơn, có thể đối chiếu với:

~~~bash
jcmd 12345 VM.metaspace
jcmd 12345 VM.classloader_stats
~~~

**VM.metaspace** tập trung vào trạng thái Metaspace của HotSpot; **VM.classloader_stats** cho biết số liệu theo class loader. Kết hợp ba báo cáo giúp phân biệt class metadata tăng hợp lệ với class loader bị giữ ngoài ý muốn.

## 13. Ví dụ đối chiếu baseline qua hai giai đoạn

Giả sử service chạy một tác vụ tạo và hủy plugin. Sau warm-up, nhóm vận hành tạo baseline. Sau 30 phút, **summary.diff** cho kết quả minh họa:

~~~text
Total: committed=620MB +48MB

- Class: committed=180MB +34MB
- Thread: committed=42MB +2MB
- Code: committed=38MB +3MB
- GC: committed=76MB +4MB
- Internal: committed=18MB +1MB
~~~

Số liệu trên chỉ là ví dụ giả định. Cách đọc:

1. Tổng committed tăng 48 MB.
2. Category Class chiếm phần tăng lớn nhất.
3. Kiểm tra số class và **VM.classloader_stats**.
4. Nếu mỗi chu kỳ plugin tạo thêm class loader mà loader cũ không biến mất, điều tra reference giữ loader.
5. Nếu số loader ổn định và workload thực sự nạp thêm class, mức tăng có thể là hợp lệ.
6. Lặp lại phép đo với cùng workload để xác nhận xu hướng.

Không kết luận leak từ một diff duy nhất. Một đợt tăng có thể đến từ warm-up chưa hoàn tất, tải tăng, plugin mới hoặc cache nội bộ.

## 14. Dùng nhiều baseline để phân tích xu hướng

NMT cho phép tạo baseline mới sau khi đã đọc diff. Có thể dùng chu kỳ đo:

~~~bash
# Sau warm-up và khi ứng dụng ổn định
jcmd 12345 VM.native_memory baseline

# Sau workload thứ nhất
jcmd 12345 VM.native_memory summary.diff scale=MB

# Tạo baseline mới cho giai đoạn tiếp theo
jcmd 12345 VM.native_memory baseline

# Sau workload thứ hai
jcmd 12345 VM.native_memory summary.diff scale=MB
~~~

Mỗi lần gọi **baseline** sẽ tạo mốc so sánh mới. Ghi lại timestamp và workload cho từng mốc; nếu không, người đọc có thể nhầm diff đang so sánh với baseline nào.

Với leak nhỏ, cần quan sát đủ lâu và lặp nhiều chu kỳ. Oracle lưu ý lượng leak nhỏ có thể mất thời gian mới thể hiện rõ trong báo cáo.

## 15. Phân biệt tăng trưởng bình thường với native memory leak

NMT giúp xác định nhóm memory tăng, nhưng không tự kết luận nguyên nhân. Cần tìm xu hướng có thể tái hiện:

**Dấu hiệu đáng điều tra:**

- Committed của một category tăng đều qua các chu kỳ workload tương đương.
- Sau khi tác vụ kết thúc, committed hoặc allocation count không ổn định lại.
- Detail diff liên tục cho thấy cùng call site tạo allocation mới.
- Tăng trưởng tiếp tục sau warm-up và không giải thích được bằng thay đổi tải.

**Dấu hiệu chưa đủ để kết luận leak:**

- Reserved tăng nhưng committed không tăng tương ứng.
- Một category tăng trong startup rồi ổn định.
- Committed tăng trong thời gian tải tăng và giảm/ổn định sau đó.
- NMT tracking overhead tăng sau khi bật NMT.
- Một lần summary.diff có số tăng nhưng chưa lặp lại.

Để kết luận, cần so sánh nhiều baseline, kiểm soát workload và đối chiếu với công cụ khác.

## 16. Giới hạn và cách kết hợp công cụ khác

| Công cụ | Phù hợp để trả lời |
|---|---|
| NMT summary | Subsystem HotSpot nào đang tăng committed memory? |
| NMT detail | Allocation call site hoặc virtual memory region nào đang tăng? |
| jcmd VM.metaspace | Metaspace và class space đang có trạng thái allocator nào? |
| jcmd VM.classloader_stats | Class loader nào đang giữ nhiều class metadata? |
| JFR/JDK Mission Control | Class loading, GC, thread và hoạt động ứng dụng diễn ra theo thời gian ra sao? |
| Heap dump | Object hoặc reference nào đang giữ class loader hay cấu trúc Java? |
| OS tools | RSS, mapping, native allocation và memory của process/container đang thay đổi thế nào? |

Ví dụ, nếu RSS tăng 300 MB nhưng NMT committed chỉ tăng 20 MB:

1. Kiểm tra cgroup hoặc RSS theo hệ điều hành.
2. Xem NMT category nào thay đổi.
3. Kiểm tra thư viện JNI/native và allocation ngoài HotSpot.
4. Kiểm tra direct/mapped buffer bằng số liệu buffer pool phù hợp.
5. Kiểm tra memory mapping, CDS và vùng shared memory.
6. Dùng profiler hoặc công cụ native phù hợp nếu NMT không bao quát allocation đang tăng.

Không cố ép tổng NMT phải bằng RSS. Chúng đo phạm vi khác nhau.

## 17. NMT trong môi trường container

Giới hạn memory của container áp dụng cho tổng memory được cgroup tính, không chỉ Java heap và không chỉ các category NMT theo dõi.

Khi đối chiếu:

- Ghi nhận NMT committed theo category.
- Ghi nhận RSS của process hoặc **memory.current** của cgroup.
- Ghi lại heap, số thread, workload và thời điểm lấy số liệu.
- Kiểm tra native library và allocation bên ngoài HotSpot.
- Không dùng riêng NMT để dự báo chính xác container còn bao nhiêu memory.

Nếu NMT ổn định nhưng cgroup memory tăng, tiếp tục điều tra những vùng NMT không theo dõi. Đây là một kết quả hữu ích vì nó thu hẹp phạm vi tìm kiếm.

## 18. In báo cáo NMT khi JVM thoát

Có thể yêu cầu HotSpot in thống kê NMT cuối cùng khi JVM thoát:

~~~bash
java \
  -XX:NativeMemoryTracking=summary \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+PrintNMTStatistics \
  -jar inventory-service.jar
~~~

**-XX:+PrintNMTStatistics** in số liệu cuối cùng khi NMT đã được bật. Tùy chọn này hữu ích khi cần lưu báo cáo lúc process kết thúc; nó không thay thế baseline/diff trong thời gian ứng dụng đang chạy.

## 19. Dừng NMT và các giới hạn vòng đời

Có thể dừng tracking bằng:

~~~bash
jcmd 12345 VM.native_memory shutdown
~~~

Sau khi shutdown, NMT không tiếp tục thu thập. **jcmd** không thể start hoặc restart NMT trên cùng process. Muốn theo dõi lại, phải khởi động JVM mới với **-XX:NativeMemoryTracking=summary** hoặc **detail**.

Vì vậy, không chạy **shutdown** trong lúc còn cần các baseline tiếp theo. Trong quy trình điều tra, chỉ dừng khi đã thu thập đủ dữ liệu hoặc chuẩn bị kết thúc process.

## 20. Lỗi thường gặp khi bật và đọc NMT

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| VM.native_memory báo NMT chưa bật | JVM khởi động mà không có option tracking | Restart JVM với summary hoặc detail. |
| Thêm option vào môi trường nhưng không thấy hiệu lực | Service/container không đọc biến hoặc file cấu hình vừa sửa | Kiểm tra command line thực tế và restart đúng process. |
| jcmd không tìm thấy JVM | Khác PID namespace, user hoặc máy | Chạy trong đúng host/container và đúng effective user/group. |
| summary.diff không có chênh lệch đáng kể | Workload chưa tạo thêm allocation hoặc baseline đặt sai thời điểm | Xác nhận workload, tạo baseline sau warm-up và đo lại. |
| Class committed tăng sau redeploy | Class loader cũ còn sống hoặc ứng dụng nạp class hợp lệ | Đối chiếu class count, classloader stats và Metaspace. |
| RSS tăng nhưng NMT không tăng | Allocation nằm ngoài phạm vi NMT hoặc do OS mapping | Dùng OS tools và profiler native. |
| Detail report quá nhiều dữ liệu | Bật detail trong thời gian dài hoặc workload có nhiều allocation | Dùng summary trước; bật detail trong giai đoạn cần điều tra. |
| Kết quả NMT khác giữa hai JDK | Category hoặc cách quản lý nội bộ thay đổi theo release | So sánh đúng JDK/vendor/build và không giả định output cố định. |
| NMT shutdown rồi không bật lại được | NMT không thể restart bằng jcmd | Khởi động JVM mới với option tracking. |

## 21. Quy trình điều tra đề xuất

1. Xác định JDK vendor, version, build và PID của JVM.
2. Kiểm tra NMT đã bật ở summary hay detail.
3. Xác nhận workload và memory baseline trước khi đo.
4. Tạo baseline sau warm-up.
5. Chạy workload có thể lặp lại.
6. Đọc summary.diff để tìm category tăng.
7. Nếu cần, dùng detail mode và detail.diff để xem call site.
8. Với category Class, đối chiếu VM.metaspace và VM.classloader_stats.
9. Với RSS tăng ngoài số liệu NMT, dùng công cụ hệ điều hành và profiler native.
10. Lặp lại nhiều chu kỳ để xác nhận xu hướng.
11. Ghi lại mode, overhead, thời gian baseline, workload và kết quả.
12. Chỉ kết luận leak khi xu hướng tăng có thể tái hiện và đã loại trừ warm-up/tải hợp lệ.

## 22. Cách áp dụng trong Java hiện đại

- Dùng NMT trên HotSpot để theo dõi bộ nhớ nội bộ của JVM; không coi đây là phép đo toàn bộ off-heap hoặc RSS.
- Bật **-XX:NativeMemoryTracking=summary** hoặc **detail** khi JVM khởi động; không kỳ vọng có thể bật lại bằng **jcmd**.
- Bắt đầu bằng **summary**, tạo baseline sau warm-up và so sánh bằng **summary.diff**.
- Chuyển sang **detail** và **detail.diff** khi cần xác định allocation call site.
- Đọc **reserved** và **committed** riêng biệt; không xem reserved là RAM đang dùng.
- Quan sát category **Class** khi điều tra Elastic Metaspace, rồi đối chiếu với **VM.metaspace** và **VM.classloader_stats**.
- Tính overhead 5–10% được Oracle ghi nhận vào quyết định bật NMT, nhất là trong production.
- Kết hợp NMT với JFR, heap dump và công cụ hệ điều hành khi memory tăng nằm ngoài phạm vi tracking.
- Ghi rõ JDK vendor/build và category thực tế vì output có thể thay đổi theo release.

NMT giúp chuyển câu hỏi “process Java đang dùng thêm RAM ở đâu?” thành các phép đo có thể so sánh theo subsystem và call site. Khi bật đúng từ đầu, tạo baseline có kiểm soát và đọc chênh lệch qua nhiều chu kỳ, nhóm vận hành có thể xác định liệu native memory tăng đến từ Class, Thread, Code, GC hay nằm ngoài phạm vi HotSpot mà cần công cụ khác.

## Tài liệu tham khảo

- [Oracle JDK 16 — The java Command: NativeMemoryTracking](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [Oracle JDK 16 — Java Virtual Machine Guide: Native Memory Tracking](https://docs.oracle.com/en/java/javase/16/vm/java-virtual-machine-guide.pdf)
- [Oracle JDK 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html)
- [Oracle JDK 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle JDK 26 — Diagnostic Tools: Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 26 — Troubleshooting Guide: Diagnosing Native Memory Leaks](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf)
