# Elastic Metaspace từ Java 16 và bộ nhớ metadata của class

Từ Java 8, HotSpot lưu metadata của class trong bộ nhớ native gọi là **Metaspace**, thay cho PermGen của các JDK cũ. Java 16 tiếp tục cải tiến vùng nhớ này bằng **JEP 387: Elastic Metaspace**. Thay đổi này giúp HotSpot quản lý các khối metadata linh hoạt hơn, giảm lãng phí và trả bộ nhớ đã không còn cần thiết về hệ điều hành kịp thời hơn, đặc biệt ở ứng dụng tạo nhiều class loader nhỏ hoặc thường xuyên nạp rồi dỡ class.

Elastic Metaspace vẫn là cơ chế quản lý nội bộ của HotSpot. Ứng dụng không cần gọi API mới để sử dụng nó. Tuy nhiên, để vận hành ứng dụng Java hiện đại, cần hiểu Metaspace khác Java heap thế nào, class loader ảnh hưởng đến vòng đời metadata ra sao, và cách đọc số liệu để phân biệt tăng trưởng bình thường với rò rỉ class loader.

## 1. Metaspace lưu trữ dữ liệu gì?

Khi JVM nạp một class, nó tạo cấu trúc metadata để mô tả class đó: thông tin kiểu, phương thức, field, runtime constant pool và các dữ liệu nội bộ cần cho việc liên kết, kiểm tra và thực thi class. Trong HotSpot, phần lớn metadata này được cấp phát từ bộ nhớ native, không nằm trong Java heap.

| Khu vực | Nội dung điển hình | Cơ chế thu hồi |
|---|---|---|
| Java heap | Object, array và phần lớn dữ liệu ứng dụng | Garbage collector thu hồi object không còn reachable. |
| Metaspace | Metadata của class và interface đã nạp | Metadata được thu hồi khi class loader định nghĩa chúng có thể được garbage collector thu hồi. |
| Compressed Class Space | Một vùng metadata riêng cho compressed class pointers khi cơ chế này được bật | Được quản lý cùng vòng đời class metadata; có giới hạn không gian riêng. |
| Native memory khác | Thread stack, code cache, direct buffer, JNI/native library và cấu trúc JVM | Theo cơ chế của từng thành phần; không phải tất cả đều thuộc Metaspace. |

Ví dụ, một ứng dụng có thể giữ số lượng object trong heap ổn định nhưng vẫn nạp thêm class liên tục do tạo proxy, class động hoặc class loader mới. Khi đó Metaspace có thể tăng dù heap không tăng tương ứng.

Metaspace không phải nơi lưu toàn bộ dữ liệu static của ứng dụng. Các giá trị object mà ứng dụng giữ vẫn thuộc vùng nhớ object tương ứng; Metaspace lưu metadata mà JVM cần để hiểu và thực thi kiểu đã nạp.

## 2. Từ PermGen đến Metaspace

PermGen là vùng nhớ của các HotSpot JDK cũ. JDK 8 đã loại bỏ Permanent Generation và chuyển class metadata sang native memory. Vì vậy, khi vận hành JDK hiện đại, không tiếp tục áp dụng cấu hình PermGen.

| Thời kỳ | Cách quản lý class metadata |
|---|---|
| JDK 7 trở về trước | HotSpot sử dụng Permanent Generation trong heap. |
| JDK 8–15 | Metaspace dùng native memory; cơ chế quản lý metadata được cấp phát theo class loader. |
| JDK 16 trở đi | JEP 387 thay đổi cách quản lý chunk và thu hồi vùng nhớ, làm Metaspace linh hoạt hơn. |

Các tùy chọn cũ như **-XX:PermSize** và **-XX:MaxPermSize** thuộc thời PermGen và không phải cấu hình Metaspace hiện hành. Không chuyển nguyên các giá trị đó sang JDK mới.

JDK 16 cũng đánh dấu một số tùy chọn nội bộ liên quan Metaspace là deprecated, gồm **InitialBootClassLoaderMetaspaceSize** và **UseLargePagesInMetaspace**. Không đưa các cờ này vào cấu hình mới.

## 3. Elastic Metaspace trong JDK 16 thay đổi điều gì?

Trước JDK 16, Metaspace đã có khả năng thu hồi bộ nhớ khi class loader được dỡ, nhưng cách quản lý chunk và vùng nhớ còn có thể để lại phần committed lớn hơn nhu cầu hiện tại. JEP 387 thay đổi cấu trúc allocator và cách quản lý vùng nhớ để giảm fragmentation, dùng chunk hiệu quả hơn và uncommit vùng không còn cần thiết sớm hơn.

Các ý chính của thay đổi:

- Dùng buddy-style allocator để quản lý chunk với các kích thước phù hợp.
- Chia vùng nhớ thành các granule, là đơn vị cơ bản để commit hoặc uncommit.
- Cho phép những vùng chunk đã trả về allocator được tái sử dụng hoặc uncommit để trả backing memory về hệ điều hành.
- Cải thiện hành vi trong ứng dụng có nhiều class loader nhỏ, plugin, proxy hoặc class được tạo động.
- Giảm lượng memory committed không cần thiết sau khi class được unload.

Một granule là đơn vị quản lý commit/uncommit, không phải một class hay một object. Nếu một phần granule vẫn còn được sử dụng, JVM không thể trả riêng các byte còn lại của granule đó về hệ điều hành.

### 3.1. Vì sao cần allocator linh hoạt?

Một class loader có thể cần metadata cho nhiều class. HotSpot cấp phát metadata từ các chunk gắn với class loader. Khi class loader được thu hồi, chunk của nó có thể được đưa về danh sách tái sử dụng hoặc trả lại cho hệ điều hành.

Trong ứng dụng tạo nhiều class loader ngắn hạn, ví dụ hệ thống plugin hoặc môi trường triển khai ứng dụng web, kích thước và cách phân phối chunk ảnh hưởng đến lượng memory bị giữ lại. Elastic Metaspace cải thiện việc quản lý các chunk này để vùng nhớ không còn cần thiết có cơ hội được uncommit sớm hơn.

### 3.2. Elastic không có nghĩa là mọi memory đều giảm ngay

Elastic Metaspace không đảm bảo RSS của process giảm ngay sau mỗi lần dỡ class. Có một số lý do:

- Class loader vẫn còn reachable nên class của nó chưa được unload.
- Một số chunk hoặc granule còn chứa metadata đang dùng.
- JVM có thể giữ vùng nhớ đã commit để tái sử dụng, tùy chính sách reclaim.
- Reserved virtual address space có thể vẫn còn được giữ dù backing memory đã được uncommit.
- Process còn nhiều vùng native memory khác không liên quan đến Metaspace.

Vì vậy, hãy quan sát **used**, **committed**, **reserved** và số liệu class loader thay vì chỉ nhìn một con số RSS.

## 4. Class loader quyết định vòng đời metadata

Class được định nghĩa bởi một class loader. Theo quy tắc của Java, một class chỉ có thể được unload khi class loader định nghĩa nó có thể được garbage collector thu hồi. JVM không thể unload class của một loader vẫn còn reachable.

Điều này rất quan trọng với hệ thống nạp code động:

- Plugin manager tạo class loader riêng cho từng plugin.
- Máy chủ ứng dụng triển khai và gỡ nhiều ứng dụng web.
- Framework tạo proxy class hoặc bytecode khi chạy.
- Công cụ test tạo class loader cho từng test suite.
- Runtime scripting hoặc engine biên dịch class động.

Nếu ứng dụng gỡ plugin nhưng còn một object giữ class loader, các class của plugin vẫn có thể còn sống và metadata chưa thể được thu hồi.

### 4.1. Những tham chiếu thường giữ class loader ngoài ý muốn

| Nguồn tham chiếu | Cách gây giữ class loader |
|---|---|
| Static registry | Class của ứng dụng chính giữ object hoặc callback thuộc plugin. |
| Thread context class loader | Thread sống lâu giữ context class loader của ứng dụng đã gỡ. |
| ThreadLocal | Thread pool giữ value hoặc class thuộc ứng dụng cũ. |
| Executor hoặc background thread | Thread do plugin tạo chưa dừng khi plugin bị unload. |
| Listener và callback | Event bus, timer hoặc framework vẫn giữ listener của plugin. |
| Cache toàn cục | Cache giữ Class, Method, Constructor hoặc proxy class của loader cũ. |
| JDBC driver, MBean hoặc logging registry | Registry dùng chung giữ implementation do class loader ứng dụng nạp. |
| Native/JNI callback | Thành phần native giữ global reference hoặc callback gắn với class loader. |

Các ví dụ trên là những điểm cần kiểm tra, không phải bằng chứng mặc định rằng framework tương ứng bị lỗi. Cần xác định đường tham chiếu thực tế bằng log, heap dump hoặc công cụ chẩn đoán.

### 4.2. Quy trình gỡ plugin đúng

Khi một plugin không còn được sử dụng, quy trình dừng plugin nên:

1. Ngừng nhận request hoặc event mới từ plugin.
2. Dừng thread, scheduler và executor do plugin sở hữu.
3. Hủy đăng ký listener, MBean, driver và callback đã đăng ký.
4. Xóa reference trong registry và cache dùng chung.
5. Xóa ThreadLocal hoặc khôi phục context class loader trên các thread dùng lại.
6. Đóng tài nguyên của class loader nếu API loader cung cấp thao tác close phù hợp.
7. Bỏ các reference cuối cùng tới class loader, Class và object của plugin.
8. Theo dõi class loader và metadata qua các chu kỳ triển khai tiếp theo.

Đóng URLClassLoader có thể giải phóng tài nguyên như file JAR đang mở, nhưng thao tác close không tự unload class. Class loader vẫn phải không còn reachable thì class metadata mới đủ điều kiện được thu hồi.

## 5. Phân biệt used, capacity, committed và reserved

Các chỉ số Metaspace có ý nghĩa khác nhau. Không so sánh chúng như thể đều là lượng RAM thực tế đang dùng.

| Chỉ số | Ý nghĩa |
|---|---|
| **used** | Metadata đã được cấp phát và đang được sử dụng cho class đã nạp. |
| **capacity** | Dung lượng có thể cấp phát trong các chunk đã được cấp cho class loader, bao gồm phần chưa dùng trong chunk. |
| **committed** | Phần virtual memory đã được commit/backing để JVM sử dụng. |
| **reserved** | Không gian địa chỉ ảo JVM đã reserve cho Metaspace; không đồng nghĩa toàn bộ vùng đó đang chiếm RAM vật lý. |

Ví dụ:

~~~text
Metaspace:
  used      = 180 MB
  capacity  = 220 MB
  committed = 256 MB
  reserved  = 1 GB
~~~

Trong ví dụ, 1 GB reserved không có nghĩa process đang dùng 1 GB RAM cho metadata. Chỉ số committed phản ánh phần vùng nhớ đã được commit, còn used phản ánh phần metadata thực sự được cấp phát.

Sau khi class loader được unload, used có thể giảm. Nếu allocator uncommit các granule không còn cần thiết, committed cũng có thể giảm. Reserved có thể vẫn giữ nguyên vì JVM còn dành không gian địa chỉ ảo để sử dụng về sau.

### 5.1. Compressed Class Space

Trên cấu hình 64-bit có bật compressed class pointers, HotSpot dùng một vùng địa chỉ riêng để biểu diễn class pointer bằng offset 32-bit. Vùng này gọi là **Compressed Class Space**.

Theo tài liệu HotSpot hiện hành:

- **UseCompressedClassPointers** điều khiển cơ chế compressed class pointers.
- **CompressedClassSpaceSize** đặt kích thước vùng địa chỉ dành cho compressed class space.
- Kích thước mặc định thường là 1 GB trong cấu hình được tài liệu mô tả.
- Vùng này được reserve lúc khởi tạo và commit dần khi cần.
- **MaxMetaspaceSize** áp dụng cho tổng phần committed của compressed class space và phần class metadata còn lại.

Compressed Class Space và phần Metaspace còn lại là hai vùng logic khác nhau. Không kết luận toàn bộ class metadata đều nằm trong Compressed Class Space.

## 6. Các tùy chọn Metaspace còn hữu ích

Các tùy chọn dưới đây là HotSpot-specific, không phải cam kết của Java SE cho mọi JVM vendor. Kiểm tra tài liệu của đúng runtime trước khi triển khai.

| Tùy chọn | Tác dụng | Cách sử dụng |
|---|---|---|
| **-XX:MetaspaceSize** | Mức high-water mark ban đầu; khi vùng metadata committed vượt ngưỡng, JVM có thể kích hoạt GC để thử unload class. | Điều chỉnh khi có bằng chứng GC do metadata threshold xảy ra quá sớm. |
| **-XX:MaxMetaspaceSize** | Giới hạn trên cho native memory dùng làm class metadata. | Dùng như giới hạn tài nguyên sau khi đo nhu cầu thực tế. |
| **-XX:CompressedClassSpaceSize** | Kích thước vùng Compressed Class Space khi cơ chế tương ứng được bật. | Chỉ điều chỉnh khi có bằng chứng vùng này cạn hoặc cần thay đổi memory layout. |
| **-XX:MetaspaceReclaimPolicy** | Tùy chọn HotSpot được JDK 16 release note giới thiệu để điều chỉnh cách reclaim. | Xác minh flag và giá trị được hỗ trợ trên đúng JDK/vendor trước khi dùng. |

### 6.1. MetaspaceSize không phải kích thước tối đa

**-XX:MetaspaceSize** thường bị hiểu nhầm là kích thước khởi tạo hoặc giới hạn của Metaspace. Thực tế, đây là high-water mark ban đầu liên quan đến thời điểm JVM kích hoạt GC khi metadata committed vượt ngưỡng. JVM điều chỉnh ngưỡng này dựa trên lượng metadata được thu hồi sau GC và các tỷ lệ free-space liên quan.

Ví dụ:

~~~bash
java -XX:MetaspaceSize=128m -jar inventory-service.jar
~~~

Giá trị 128 MB trong ví dụ không có nghĩa Metaspace bị giới hạn ở 128 MB. Ứng dụng vẫn có thể dùng nhiều hơn nếu không bị giới hạn bởi **MaxMetaspaceSize** hoặc tài nguyên native memory.

Không tăng MetaspaceSize chỉ vì nhìn thấy một lần GC liên quan metadata. Hãy kiểm tra log, thời gian pause, lượng class được unload và mức tăng trưởng của ứng dụng trước.

### 6.2. MaxMetaspaceSize là giới hạn, không phải cách chữa leak

Theo tài liệu HotSpot hiện hành, mặc định Metaspace không có giới hạn kích thước do JVM đặt. Có thể dùng **-XX:MaxMetaspaceSize** để đặt giới hạn native memory cho class metadata.

Ví dụ:

~~~bash
java -XX:MaxMetaspaceSize=512m -jar inventory-service.jar
~~~

Nếu metadata cần vượt giới hạn này, JVM có thể ném **OutOfMemoryError: Metaspace**. Đặt giới hạn quá thấp có thể làm ứng dụng lỗi dù class loader hoạt động đúng.

Tăng giới hạn có thể giúp ứng dụng có thêm headroom, nhưng không xử lý nguyên nhân nếu class loader bị giữ lại qua mỗi lần redeploy. Trong trường hợp leak, giới hạn cao hơn chỉ có thể làm lỗi xuất hiện muộn hơn.

### 6.3. MetaspaceReclaimPolicy

JDK 16 release note mô tả tùy chọn HotSpot:

~~~text
-XX:MetaspaceReclaimPolicy=balanced
~~~

Các giá trị được mô tả trong release note JDK 16:

| Giá trị | Ý nghĩa được mô tả |
|---|---|
| **balanced** | Cân bằng việc reclaim với chi phí bookkeeping; là mặc định được ghi nhận trong JDK 16. |
| **aggressive** | Tăng mức reclaim, đổi lại chi phí quản lý có thể cao hơn. |
| **none** | Tắt cơ chế reclaim tương ứng. |

Đây là cờ nội bộ HotSpot, không phải API Java SE. Không giả định nó có cùng tên, giá trị hoặc mặc định trên mọi vendor/JDK release. Kiểm tra runtime thực tế bằng **java -XX:+PrintFlagsFinal -version** hoặc **jcmd <pid> VM.flags -all** và tài liệu đi kèm JDK trước khi sử dụng. Không chọn aggressive hoặc none chỉ vì muốn RSS giảm nhanh; hãy đo tác động tới CPU, pause time và memory trước.

## 7. Chẩn đoán bằng jcmd

**jcmd** là công cụ chẩn đoán ưu tiên trong JDK hiện đại. Dùng nó trên cùng máy với JVM đích và bằng user/group có quyền phù hợp với process đó.

Liệt kê JVM đang chạy:

~~~bash
jcmd -l
~~~

In thống kê Metaspace cơ bản:

~~~bash
jcmd 12345 VM.metaspace basic
~~~

Thay 12345 bằng PID thực tế.

Xem mức dùng theo class loader:

~~~bash
jcmd 12345 VM.metaspace show-loaders=true scale=MB
~~~

Nếu cần xem class được nạp bởi từng loader:

~~~bash
jcmd 12345 VM.metaspace show-loaders=true show-classes=true scale=MB
~~~

Xem thống kê class loader:

~~~bash
jcmd 12345 VM.classloader_stats
~~~

Xem cây class loader:

~~~bash
jcmd 12345 VM.classloaders
~~~

Các lệnh **VM.metaspace**, **VM.classloader_stats** và **VM.classloaders** có sẵn trong các JDK hiện đại; tùy chọn chi tiết của lệnh có thể thay đổi theo release. Có thể chạy **jcmd 12345 help VM.metaspace** để xem cú pháp đúng của runtime đang chạy.

### 7.1. Đọc số liệu theo class loader

Khi điều tra leak do redeploy hoặc plugin:

1. Chụp thống kê sau khi ứng dụng khởi động và đã warm up.
2. Thực hiện một chu kỳ deploy/undeploy hoặc load/unload plugin.
3. Đợi các luồng và tài nguyên của plugin kết thúc.
4. Chụp lại số lượng class loader, số class và Metaspace used.
5. Lặp lại nhiều chu kỳ với cùng workload.
6. So sánh xem class loader cũ có tiếp tục tồn tại và số class/metadata có tăng sau mỗi chu kỳ không.

Nếu mỗi lần redeploy lại có một loader mới được giữ cùng số lượng class cũ, hãy tìm reference path giữ loader. Nếu số class tăng vì ứng dụng có thêm tính năng hoặc plugin hợp lệ, mức tăng có thể là bình thường.

Không chỉ nhìn tổng số class. Một class loader có thể nạp rất nhiều class; ngược lại, nhiều loader nhỏ cũng có thể làm tăng overhead và fragmentation.

## 8. Theo dõi native memory bằng Native Memory Tracking

Metaspace thuộc native memory. **Native Memory Tracking (NMT)** giúp xem các nhóm cấp phát nội bộ của HotSpot, trong đó có nhóm Class.

NMT phải được bật khi JVM khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar inventory-service.jar
~~~

Hoặc dùng mức detail khi cần phân tích sâu hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar inventory-service.jar
~~~

Sau khi ứng dụng warm up, tạo baseline:

~~~bash
jcmd 12345 VM.native_memory baseline
~~~

Sau một khoảng thời gian hoặc sau nhiều chu kỳ deploy, xem chênh lệch:

~~~bash
jcmd 12345 VM.native_memory summary.diff
~~~

Nếu cần thông tin theo allocation site:

~~~bash
jcmd 12345 VM.native_memory detail.diff
~~~

NMT có overhead về CPU và bộ nhớ; tài liệu Oracle ghi nhận mức giảm hiệu năng có thể khoảng 5–10% tùy workload và mức tracking. NMT chỉ theo dõi cấp phát nội bộ của HotSpot, không bao quát mọi allocation từ thư viện native bên ngoài JVM. Dùng summary trước, chỉ bật detail trong môi trường và giai đoạn cần chẩn đoán.

### 8.1. Hiểu nhóm Class trong NMT

NMT có thể hiển thị nhóm Class với reserved, committed và số class đã nạp. Đây là góc nhìn hữu ích để so sánh Metaspace với các vùng native memory khác như Thread, Code, GC và Internal.

Ví dụ rút gọn:

~~~text
Native Memory Tracking:
Total: reserved=..., committed=...
- Class (reserved=..., committed=...)
    (classes #...)
    (Metadata: reserved=..., committed=..., used=...)
    (Class space: reserved=..., committed=..., used=...)
~~~

Tên trường và cấu trúc output có thể thay đổi theo JDK. Đọc output từ runtime thực tế thay vì viết parser phụ thuộc cứng vào một định dạng.

## 9. Dùng unified logging và JFR để tìm xu hướng class loading

Khi cần xác nhận class được nạp hoặc unload vào thời điểm nào, có thể bật unified logging trong môi trường thử nghiệm:

~~~bash
java -Xlog:class+load=info,class+unload=info \
  -jar inventory-service.jar
~~~

Log class loading có thể rất lớn với ứng dụng dùng nhiều framework hoặc tạo class động. Chỉ bật trong khoảng thời gian cần thiết, cấu hình rotation và bảo vệ log theo chính sách dữ liệu của hệ thống.

Java Flight Recorder (JFR) và JDK Mission Control có thể giúp tương quan hoạt động class loading, GC, thread và thời điểm ứng dụng triển khai plugin. Dùng recording cấu hình phù hợp với mục tiêu điều tra; không bật profile nặng liên tục nếu chưa đánh giá overhead.

JFR, jcmd và NMT bổ sung cho nhau:

| Công cụ | Câu hỏi trả lời |
|---|---|
| **jcmd VM.metaspace** | Metaspace đang dùng bao nhiêu? Loader nào đang giữ metadata? |
| **jcmd VM.classloader_stats** | Có bao nhiêu class loader và mỗi loader quản lý bao nhiêu class? |
| **NMT** | Nhóm Class/native memory tăng bao nhiêu so với baseline? |
| **Unified logging** | Class được nạp hoặc unload vào thời điểm nào? |
| **JFR/JMC** | Việc nạp class, GC và hoạt động ứng dụng liên quan nhau ra sao? |

## 10. Phân biệt các loại OutOfMemoryError

Không phải mọi lỗi bộ nhớ đều do Metaspace. Đọc detail message của exception và đối chiếu số liệu trước khi thay đổi JVM options.

| Thông báo | Khu vực liên quan | Hướng điều tra |
|---|---|---|
| **OutOfMemoryError: Java heap space** | Java heap không cấp phát được object | Kiểm tra heap live set, object retention và cấu hình heap. |
| **OutOfMemoryError: Metaspace** | Class metadata không thể được cấp phát trong Metaspace | Kiểm tra MaxMetaspaceSize, class loading, class unloading và class-loader leak. |
| **OutOfMemoryError: Compressed class space** | Vùng compressed class metadata đã cạn | Kiểm tra UseCompressedClassPointers và CompressedClassSpaceSize trên runtime đích. |
| Lỗi native allocation hoặc thông báo liên quan swap/native heap | Native memory nói chung | Kiểm tra NMT, JNI/native library, direct buffer, thread stack và tài nguyên hệ điều hành. |

### 10.1. Metaspace OOM không đồng nghĩa class-loader leak

Các nguyên nhân có thể gồm:

- Ứng dụng hợp lệ nạp số lượng class lớn hơn giới hạn đã cấu hình.
- Framework hoặc proxy generator tạo nhiều class động.
- Class loader cũ không được thu hồi sau redeploy.
- **MaxMetaspaceSize** đặt thấp hơn nhu cầu thật.
- Native memory của process hoặc hệ điều hành không còn đủ.

Trước khi tăng giới hạn, hãy xác định số class, class loader, mức used/committed và xu hướng sau khi workload ổn định.

### 10.2. Heap ổn định nhưng Metaspace tăng

Tình huống này thường hướng điều tra tới class loading và class loader:

1. So sánh số class đã nạp qua thời gian.
2. So sánh số class loader và loại loader.
3. Kiểm tra các loader gắn với plugin hoặc ứng dụng đã undeploy.
4. Tìm thread, ThreadLocal, registry hoặc cache còn giữ class loader.
5. Kiểm tra class unloading có xảy ra sau chu kỳ GC phù hợp không.
6. Dùng heap dump hoặc công cụ phân tích reference path nếu cần xác định object đang giữ loader.

Heap dump hữu ích để tìm đường tham chiếu Java tới class loader, nhưng nó không thay thế thống kê Metaspace/NMT khi cần hiểu native committed memory.

## 11. Đọc đúng dấu hiệu của class-loader leak

Một lần tăng Metaspace sau khi khởi động không đủ để kết luận có leak. Ứng dụng có thể đang nạp thêm class do warm-up, JIT, framework hoặc workload mới.

Dấu hiệu đáng nghi hơn:

- Sau mỗi lần undeploy, số class loader không giảm hoặc tiếp tục tăng.
- Cùng một ứng dụng/plugin được deploy lại tạo thêm một loader mới trong khi loader cũ vẫn còn.
- Số class hoặc Metaspace used tăng qua các chu kỳ có workload tương đương.
- Các class loader đã ngừng hoạt động vẫn xuất hiện trong thống kê.
- Sau thời gian ổn định và các cơ hội class unloading, mức metadata live vẫn tăng liên tục.

Ngược lại, committed memory không giảm ngay nhưng used đã giảm và số loader cũ biến mất có thể chỉ là allocator giữ chunk để tái sử dụng. Đó không tự động là leak.

## 12. Quy trình điều tra Metaspace tăng bất thường

Thực hiện theo thứ tự để tránh thay đổi nhiều tham số cùng lúc:

1. Ghi lại JDK vendor, version, build, GC và JVM flags thực tế.
2. Kiểm tra có đặt **MaxMetaspaceSize** hoặc **CompressedClassSpaceSize** không.
3. Lấy baseline bằng **jcmd VM.metaspace** và **VM.classloader_stats**.
4. Nếu cần theo dõi native memory, bật NMT từ lần khởi động có kiểm soát.
5. Chạy workload ổn định và lặp lại thao tác tạo/dỡ class loader.
6. So sánh số class loader, số class, used, committed và NMT Class.
7. Nếu loader cũ còn sống, tìm reference path trong heap hoặc registry.
8. Nếu loader đã biến mất nhưng committed chưa giảm, xem xét chunk/granule còn được giữ để tái sử dụng.
9. Chỉ điều chỉnh giới hạn hoặc reclaim policy sau khi xác định nguyên nhân và đo được lợi ích.
10. Chạy lại benchmark và regression để bảo đảm không tăng pause time hoặc chi phí CPU quá mức.

Không dùng **System.gc()** trong vòng lặp ứng dụng như cách sửa leak. Garbage collection có thể tạo cơ hội unload class khi loader đã unreachable, nhưng không thể thu hồi loader còn bị tham chiếu.

## 13. Tuning Metaspace theo dữ liệu

Thứ tự ưu tiên:

1. Xử lý class-loader leak và dọn vòng đời plugin.
2. Xác định lượng class hợp lệ của ứng dụng sau warm-up.
3. Kiểm tra container/process memory budget.
4. Đặt giới hạn Metaspace nếu cần bảo vệ tài nguyên, dựa trên đo đạc.
5. Chỉ điều chỉnh high-water mark hoặc reclaim policy nếu có bằng chứng về GC frequency, pause và memory footprint.

Ví dụ cấu hình giới hạn có chủ đích:

~~~bash
java \
  -Xms1g \
  -Xmx2g \
  -XX:MaxMetaspaceSize=512m \
  -jar inventory-service.jar
~~~

Đây chỉ là ví dụ cú pháp, không phải bộ thông số khuyến nghị chung. Cần tính tổng memory của process, bao gồm heap, Metaspace, compressed class space, code cache, thread stack, direct buffer, GC và thư viện native.

### 13.1. Đừng đặt MaxMetaspaceSize quá thấp

Giới hạn thấp có thể gây Metaspace OOM trong lúc ứng dụng nạp framework hoặc tạo proxy. Nếu cần dùng giới hạn, hãy đo peak trong startup, warm-up, tải cao và chu kỳ redeploy.

### 13.2. Đừng nhầm reserved với RSS

Reserved address space có thể lớn nhưng chưa được commit. Không giảm heap chỉ vì thấy reserved Metaspace lớn. Trước tiên hãy xem committed và memory thực tế của process.

### 13.3. Kiểm tra đúng runtime trước khi dùng cờ -XX

Các tùy chọn **-XX** phụ thuộc HotSpot và có thể thay đổi theo JDK vendor/release. Kiểm tra cờ hiện có:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Với JVM đang chạy:

~~~bash
jcmd 12345 VM.flags -all
~~~

Sau đó đối chiếu tài liệu của đúng bản phân phối JDK. Không sao chép tuning từ một bài viết cũ sang production mà chưa xác minh.

## 14. Tác động trong container và môi trường giới hạn bộ nhớ

Trong container, giới hạn memory của cgroup áp dụng cho process, không chỉ Java heap. Một ứng dụng có thể còn heap trống nhưng vẫn bị hệ điều hành kill vì tổng native committed memory vượt giới hạn container.

Khi đặt memory budget, tính đến:

- Java heap.
- Metaspace và Compressed Class Space committed.
- Code cache.
- Thread stack và cấu trúc thread.
- Direct byte buffer.
- GC data structures.
- JNI/native library và allocator native.
- Bộ nhớ cho agent, profiler hoặc công cụ giám sát.

Theo dõi cả heap và native memory. Nếu heap ổn định nhưng RSS tăng, dùng NMT và công cụ hệ điều hành để phân biệt Metaspace, thread, code, direct buffer và native library.

NMT không bao quát mọi allocation do mã native bên ngoài HotSpot thực hiện. Nếu NMT không giải thích được phần RSS tăng, cần kiểm tra native allocator và công cụ của hệ điều hành.

## 15. Các giả định sai thường gặp

| Giả định | Thực tế |
|---|---|
| Metaspace nằm trong Java heap. | Metaspace dùng native memory. |
| Elastic Metaspace tự unload class. | Class loader phải đủ điều kiện được GC thu hồi trước khi metadata của nó có thể được thu hồi. |
| RSS phải giảm ngay sau khi unload class. | JVM có thể giữ chunk/granule để tái sử dụng; reserved address space cũng có thể vẫn còn. |
| Metaspace committed cao luôn là leak. | Cần so sánh used, số class loader và xu hướng sau workload ổn định. |
| Tăng MaxMetaspaceSize sửa được mọi Metaspace OOM. | Nó chỉ tăng giới hạn; leak hoặc native memory exhaustion vẫn còn. |
| MetaspaceSize là giới hạn tối đa. | Đây là high-water mark ban đầu liên quan đến GC threshold. |
| Compressed Class Space chứa mọi class metadata. | Nó chỉ dành cho phần metadata liên quan compressed class pointers. |
| Gọi System.gc() sẽ dỡ mọi class loader cũ. | GC không thể thu hồi loader vẫn còn reachable. |
| Heap ổn định nghĩa là native memory ổn định. | Metaspace, thread, direct buffer và JNI có vòng đời riêng. |

## 16. Ví dụ thực hành: phát hiện class loader bị giữ sau redeploy

Giả sử một máy chủ có chức năng deploy và undeploy plugin. Sau mỗi lần redeploy, Metaspace used tăng thêm và không trở về mức ổn định.

### Bước 1: lấy baseline

~~~bash
jcmd -l
jcmd 12345 VM.metaspace show-loaders=true scale=MB
jcmd 12345 VM.classloader_stats
~~~

Lưu output, số loader, số class và mức used/committed.

### Bước 2: thực hiện một chu kỳ deploy/undeploy

Deploy plugin, chạy một vài request đại diện, sau đó undeploy theo đúng API của ứng dụng. Đảm bảo plugin đã dừng thread và hủy đăng ký listener.

### Bước 3: lấy số liệu lần hai

~~~bash
jcmd 12345 VM.metaspace show-loaders=true scale=MB
jcmd 12345 VM.classloader_stats
~~~

So sánh với baseline. Nếu loader của plugin vẫn tồn tại, tìm reference path từ thread, ThreadLocal, static registry, cache hoặc callback.

### Bước 4: lặp nhiều chu kỳ

Thực hiện vài chu kỳ với cùng workload. Nếu mỗi chu kỳ giữ thêm một loader, đó là dấu hiệu mạnh của lifecycle leak. Nếu loader cũ đã biến mất và used giảm nhưng committed chưa giảm tương ứng, allocator có thể đang giữ chunk để tái sử dụng.

### Bước 5: xác nhận sau khi sửa

Sau khi sửa việc dọn thread, listener hoặc registry, chạy lại cùng kịch bản. Số loader và metadata live cần ổn định sau các chu kỳ; kiểm tra cả hiệu năng và memory footprint để chắc chắn thay đổi không tạo regression.

## 17. Checklist vận hành

- [ ] Xác nhận JDK vendor, version và build của runtime.
- [ ] Không sử dụng PermGen flags hoặc tùy chọn Metaspace đã deprecated.
- [ ] Hiểu Metaspace là native class metadata, khác Java heap.
- [ ] Theo dõi used, committed và reserved riêng biệt.
- [ ] Theo dõi Compressed Class Space nếu cơ chế compressed class pointers được bật.
- [ ] Kiểm tra số class loader trong ứng dụng có plugin, proxy hoặc redeploy.
- [ ] Đảm bảo thread, ThreadLocal, listener, registry và cache không giữ loader đã gỡ.
- [ ] Dùng jcmd VM.metaspace và VM.classloader_stats để chẩn đoán.
- [ ] Dùng NMT khi cần phân tích native memory và chấp nhận overhead.
- [ ] Đo startup, warm-up, tải cao và chu kỳ redeploy trước khi đặt MaxMetaspaceSize.
- [ ] Kiểm tra cờ -XX trên đúng JDK/vendor trước khi dùng.
- [ ] Không coi việc committed chưa giảm ngay là bằng chứng leak.
- [ ] Tính Metaspace và các vùng native khác vào memory budget của container.

## 18. Cách áp dụng trong Java hiện đại

- Xem Elastic Metaspace là cải tiến quản lý bộ nhớ nội bộ HotSpot từ JDK 16; ứng dụng không cần thay API để hưởng lợi.
- Tập trung vào vòng đời class loader vì metadata chỉ có thể được thu hồi khi loader định nghĩa class đủ điều kiện được GC thu hồi.
- Dùng **jcmd VM.metaspace**, **VM.classloader_stats** và **VM.classloaders** để kiểm tra số class, loader và chunk.
- Dùng NMT baseline/diff để theo dõi nhóm Class trong native memory; kết hợp công cụ hệ điều hành khi nghi ngờ native allocation ngoài JVM.
- Phân biệt **used**, **capacity**, **committed** và **reserved** trước khi kết luận có leak.
- Chỉ điều chỉnh **MetaspaceSize**, **MaxMetaspaceSize**, **CompressedClassSpaceSize** hoặc reclaim policy sau khi xác định đúng nút thắt.
- Không mang cấu hình PermGen hoặc các cờ Metaspace đã deprecated từ tài liệu cũ vào runtime hiện đại.
- Kiểm thử workload tạo/dỡ class loader lặp lại và xác nhận memory live ổn định sau redeploy.

Elastic Metaspace giúp HotSpot sử dụng class metadata hiệu quả hơn và trả lại vùng memory không còn cần thiết kịp thời hơn. Lợi ích rõ nhất xuất hiện khi ứng dụng có vòng đời class loader thay đổi thường xuyên. Muốn vận hành ổn định, cần kết hợp cơ chế reclaim với quản lý class loader đúng cách và theo dõi native memory bằng công cụ của JDK.

## Tài liệu tham khảo

- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387)
- [Oracle — Consolidated JDK 16 Release Notes, JEP 387](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [Oracle JDK 26 — Garbage Collection Tuning Guide: Class Metadata](https://docs.oracle.com/en/java/javase/26/gctuning/other-considerations.html)
- [Oracle JDK 26 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle JDK 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle JDK 26 — Diagnostic Tools and Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Java Language Specification, Java SE 26 — Unloading of Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
