# Heap histogram, heap dump và chi phí thu thập

Khi một ứng dụng Java dùng heap tăng bất thường, tạo nhiều object hơn dự kiến hoặc gặp `OutOfMemoryError`, cần biết bộ nhớ đang được sử dụng bởi những lớp nào và object nào đang giữ các object khác. Java 17 cung cấp các công cụ chẩn đoán như **heap histogram**, **heap dump** và **Java Flight Recorder (JFR)** để trả lời những câu hỏi đó.

Ba loại dữ liệu này phục vụ các mục đích khác nhau:

- **Heap histogram** thống kê số instance và tổng shallow size theo lớp. Nó giúp tìm nhanh nhóm lớp chiếm nhiều heap.
- **Heap dump** ghi lại đồ thị object của heap tại một thời điểm. Công cụ phân tích có thể tìm đường tham chiếu, dominator và retained size.
- **JFR recording** ghi nhận sự kiện theo thời gian như allocation, garbage collection, thread, lock và I/O. Nó giúp tìm thời điểm và hoạt động dẫn tới áp lực bộ nhớ.

Thu thập dữ liệu heap có chi phí. Các lệnh histogram và dump có thể yêu cầu JVM dừng ở safepoint, duyệt lượng lớn object, chạy Full GC hoặc ghi file rất lớn. Trong production, cần chọn đúng mức dữ liệu, thời điểm và nơi lưu trữ.

## 1. Heap histogram là gì?

Heap histogram là bảng thống kê các object đang được quản lý trên Java heap, được nhóm theo lớp. Mỗi dòng thường thể hiện:

| Cột | Ý nghĩa |
| --- | --- |
| `num` | Thứ tự dòng trong kết quả. |
| `#instances` | Số instance của lớp được thống kê. |
| `#bytes` | Tổng shallow size của các instance thuộc lớp đó. |
| `class name` | Tên lớp; có thể kèm module hoặc thông tin loader tùy cách hiển thị. |

Ví dụ minh họa:

```text
 num      #instances       #bytes  class name
------------------------------------------------
   1          85000       6800000  byte[]
   2          42000       3360000  java.lang.String
   3          12000       1920000  com.example.Order
   4           8000       1280000  java.util.HashMap$Node
   5           4000        640000  com.example.Customer
------------------------------------------------
Total:       151000      14000000
```

Các số liệu trên chỉ để minh họa cách đọc bảng, không phải kết quả benchmark hoặc số liệu mặc định của JVM.

### 1.1. Shallow size và retained size

`#bytes` trong histogram là tổng **shallow size** của các instance thuộc lớp. Shallow size là lượng bộ nhớ của chính object đó, không cộng toàn bộ object khác mà nó tham chiếu.

Ví dụ:

```text
Order
  ├── Customer
  ├── Item[]
  │    ├── Item
  │    └── Item
  └── Metadata
```

Histogram có thể cho biết có bao nhiêu `Order`, `Customer`, `Item[]` và `Item`, cùng shallow bytes của từng lớp. Nó không cho biết một `Order` cụ thể giữ bao nhiêu object khác còn sống.

**Retained size** là lượng bộ nhớ có thể được giải phóng nếu một object (hoặc tập object được dominator giữ) không còn reachable từ GC roots. Muốn phân tích retained size và đường tham chiếu, thường cần heap dump và công cụ phân tích heap.

Không cộng `#bytes` của một lớp rồi gọi đó là retained size. Hai khái niệm đo hai điều khác nhau.

### 1.2. Histogram trả lời được và không trả lời được điều gì?

Histogram hữu ích để trả lời:

- Lớp nào có nhiều instance nhất?
- Tổng shallow bytes theo lớp đang tập trung ở đâu?
- Có nhiều `byte[]`, `char[]`, `String`, collection node hoặc DTO hơn dự kiến không?
- Sau một thay đổi hoặc một giai đoạn tải, nhóm lớp nào tăng mạnh?

Histogram không trực tiếp trả lời:

- Object nào đang giữ các instance đó?
- Vì sao một object vẫn reachable?
- Đường tham chiếu nào dẫn từ GC root tới object?
- Retained size của một object cụ thể là bao nhiêu?
- Lớp tăng nhiều là rò rỉ bộ nhớ hay chỉ là cache/batch hợp lệ?

Để trả lời nhóm câu hỏi thứ hai, cần phân tích heap dump và đối chiếu với vòng đời nghiệp vụ.

## 2. Thu thập heap histogram bằng jcmd

Trên JDK 17, `jcmd` là công cụ chẩn đoán JVM phù hợp để gọi các diagnostic command của tiến trình đang chạy.

Liệt kê các JVM mà công cụ nhìn thấy:

```bash
jcmd -l
```

Kết quả hiển thị process ID và thông tin tiến trình Java. Sau khi xác định đúng PID, có thể hỏi cú pháp lệnh:

```bash
jcmd 12345 help GC.class_histogram
```

Thay `12345` bằng PID thực tế.

### 2.1. Histogram của các object còn sống

Lệnh:

```bash
jcmd 12345 GC.class_histogram
```

Theo hành vi mặc định của diagnostic command, histogram chỉ thống kê live objects và JVM yêu cầu một Full GC trước khi kiểm tra heap. Điều này giúp loại bỏ object không còn reachable trước khi thống kê, nhưng có thể tạo một khoảng dừng và chi phí GC đáng kể.

Đây là lý do cần cân nhắc thời điểm chạy lệnh trên hệ thống có latency nhạy cảm hoặc heap lớn.

### 2.2. Histogram bao gồm cả object unreachable

Có thể yêu cầu kiểm tra tất cả object, bao gồm object chưa còn reachable nhưng chưa được thu hồi:

```bash
jcmd 12345 GC.class_histogram -all
```

`-all` thay đổi ý nghĩa thống kê: kết quả có thể bao gồm object mà GC có thể thu hồi. Vì vậy, số lượng và bytes có thể cao hơn histogram live-object. Tùy chọn này tránh yêu cầu Full GC chỉ để loại object unreachable trước khi lấy histogram, nhưng JVM vẫn phải thực hiện công việc kiểm tra heap.

Khi so sánh hai histogram, phải ghi rõ có dùng `-all` hay không. So sánh kết quả live-object với kết quả all-object như thể chúng cùng một phép đo sẽ dẫn tới kết luận sai.

### 2.3. Đọc kết quả

Giả sử histogram có các dòng:

```text
  #instances       #bytes  class name
       90000      7200000  byte[]
       50000      4000000  java.lang.String
       10000      1600000  com.example.Session
```

Có thể nhận xét:

- `byte[]` đang chiếm tổng shallow bytes lớn nhất trong các dòng hiển thị.
- `String` có số instance lớn; cần xem chúng có thuộc cache, request, log buffer hay dữ liệu nghiệp vụ không.
- `Session` có thể đáng chú ý nếu số lượng tăng theo thời gian hoặc không giảm sau khi phiên hết hạn.

Nhưng chưa thể kết luận `Session` bị leak chỉ từ một lần chụp. Cần so sánh nhiều thời điểm trong điều kiện tải tương đương, xem heap sau GC và tìm đường tham chiếu trong dump nếu cần.

## 3. Heap dump là gì?

Heap dump là bản ghi dữ liệu mô tả heap tại một thời điểm, thường ở định dạng **HPROF**. Nó chứa thông tin về các class, instance, mảng và quan hệ tham chiếu đủ để công cụ phân tích tái dựng đồ thị object.

Khác với histogram chỉ thống kê theo lớp, heap dump cho phép công cụ điều tra:

- Object cụ thể nào đang tồn tại.
- Object nào tham chiếu tới object nào.
- Đường đi từ GC roots tới một object.
- Dominator tree và retained size.
- Những instance nào đang giữ collection, cache, listener hoặc session.

Heap dump thường là dữ liệu lớn và nhạy cảm. Nó có thể chứa chuỗi, nội dung request, thông tin người dùng, token hoặc dữ liệu nghiệp vụ còn nằm trong heap. Cần xem file dump như dữ liệu production nhạy cảm.

### 3.1. Histogram và heap dump khác nhau thế nào?

| Tiêu chí | Heap histogram | Heap dump |
| --- | --- | --- |
| Dữ liệu | Số instance và shallow bytes theo lớp | Đồ thị object và quan hệ tham chiếu |
| Kích thước kết quả | Thường nhỏ, dạng bảng văn bản | Có thể rất lớn, thường là file HPROF |
| Tìm lớp chiếm nhiều heap | Có | Có, qua công cụ phân tích |
| Tìm object giữ object khác | Không trực tiếp | Có |
| Phân tích GC roots/dominator | Không | Có |
| Chi phí | Có thể cao; mặc định live histogram yêu cầu Full GC | Thường cao; mặc định dump live objects yêu cầu Full GC và ghi file |
| Rủi ro dữ liệu nhạy cảm | Thấp hơn, nhưng vẫn có thể lộ tên lớp | Cao hơn do chứa nội dung object |

Nên bắt đầu bằng histogram khi cần khoanh vùng nhanh lớp đang chiếm heap. Khi cần tìm lý do object còn sống, đường tham chiếu hoặc retained size, chuyển sang heap dump.

## 4. Tạo heap dump bằng jcmd

Diagnostic command:

```bash
jcmd 12345 GC.heap_dump /var/tmp/app-heap.hprof
```

Lệnh tạo heap dump HPROF tại đường dẫn đã chỉ định.

Nếu không dùng tùy chọn `-all`, JVM chỉ dump live objects và yêu cầu Full GC trước khi tạo dump. Việc này giúp dump tập trung vào object còn reachable, nhưng có thể làm ứng dụng dừng trong thời gian đáng kể.

Trên hệ thống Windows, dùng đường dẫn phù hợp, ví dụ:

```powershell
jcmd 12345 GC.heap_dump C:\temp\app-heap.hprof
```

Đường dẫn cần có thư mục cha tồn tại và tài khoản chạy JVM phải có quyền ghi.

### 4.1. Dump cả object unreachable với -all

Để bao gồm cả object unreachable chưa được thu hồi:

```bash
jcmd 12345 GC.heap_dump -all /var/tmp/app-all-objects.hprof
```

Khi dùng `-all`, JVM không yêu cầu Full GC chỉ để lọc ra live objects trước khi dump. Dump có thể chứa nhiều object hơn và phản ánh cả object mà GC có thể thu hồi. Điều này có thể hữu ích cho một số điều tra về object allocation/chưa được thu hồi, nhưng khi tìm retained heap hoặc memory leak, dump live-object thường dễ diễn giải hơn.

Luôn ghi nhận tùy chọn này khi lưu hoặc chia sẻ kết quả để người phân tích biết dump mô tả tập object nào.

### 4.2. Nén heap dump

JDK 17 hỗ trợ nén output heap dump qua tùy chọn `-gz`:

```bash
jcmd 12345 GC.heap_dump -gz=1 /var/tmp/app-heap.hprof.gz
```

Mức nén từ 1 đến 9. Mức nén cao hơn thường giảm dung lượng file hơn nhưng tiêu tốn thêm CPU và thời gian nén. Chọn mức nén theo giới hạn đĩa, thời gian cho phép và khả năng giải nén/phân tích ở công cụ tiếp theo.

Nén không làm cho thao tác thu thập miễn phí; JVM vẫn phải duyệt heap và tạo dữ liệu dump.

### 4.3. Không ghi đè nhầm file dump

Nếu file đích đã tồn tại, lệnh có thể từ chối ghi đè. Chỉ dùng `-overwrite` khi chắc chắn file cũ không còn cần:

```bash
jcmd 12345 GC.heap_dump -overwrite /var/tmp/app-heap.hprof
```

Trong quy trình incident, tên file có timestamp và mã tiến trình giúp tránh ghi đè nhầm dữ liệu của lần thu thập trước.

### 4.4. Kiểm tra cú pháp và tùy chọn

Không nên nhớ cú pháp từ một script cũ mà không xác nhận phiên bản JDK đang chạy. Có thể hỏi JVM đích:

```bash
jcmd 12345 help GC.heap_dump
jcmd 12345 help GC.class_histogram
```

Các tùy chọn như `-all`, `-gz`, `-overwrite` và `-parallel` cần được dùng đúng theo diagnostic command được JVM đó công bố.

## 5. Phân tích heap dump

File HPROF thường được mở bằng một công cụ phân tích heap, chẳng hạn Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích HPROF khác.

Một quy trình phân tích thường gồm:

1. Mở dump và chờ công cụ lập index.
2. Xem histogram để xác định lớp có nhiều instance hoặc shallow bytes lớn.
3. Xem dominator tree để tìm object giữ nhiều bộ nhớ.
4. Kiểm tra retained size của các dominator đáng chú ý.
5. Mở đường tham chiếu tới GC roots để biết vì sao object vẫn reachable.
6. Đối chiếu với vòng đời nghiệp vụ và code quản lý cache/session/listener.

### 5.1. Dominator tree

Một object A là dominator của object B nếu mọi đường đi từ GC roots tới B đều đi qua A. Nếu loại bỏ A và các tham chiếu giữ B chỉ đi qua A, B có thể trở thành unreachable.

Dominator tree giúp tìm những object đang giữ phần lớn heap. Ví dụ:

```text
GC Root
  └── ApplicationContext
       └── CacheManager
            └── UserCache
                 ├── User 1
                 ├── User 2
                 └── User ...
```

Nếu `UserCache` giữ hàng triệu user không được loại bỏ, retained size của cache có thể rất lớn. Khi đó câu hỏi tiếp theo là chính sách eviction, TTL, invalidation và khả năng cache giữ tham chiếu ngoài ý muốn.

### 5.2. Paths to GC roots

Đường tham chiếu tới GC roots cho biết vì sao object vẫn còn sống. Các root phổ biến có thể liên quan:

- Static field của class.
- Thread stack hoặc local variable đang được giữ.
- JNI/global reference.
- Class loader hoặc cấu trúc runtime giữ object.

Khi một object đáng lẽ đã hết vòng đời vẫn reachable, đường tham chiếu thường cho thấy thành phần đang giữ nó. Cần đọc đường dẫn cùng ngữ cảnh ứng dụng; một tham chiếu còn tồn tại chưa chắc là bug nếu object vẫn thuộc cache hoặc request đang hoạt động hợp lệ.

### 5.3. Shallow size và retained size trong công cụ phân tích

Một object có shallow size nhỏ nhưng retained size lớn nếu nó là dominator của nhiều object khác. Ví dụ một `HashMap` có thể không chiếm nhiều byte trực tiếp, nhưng map giữ tham chiếu đến hàng trăm nghìn value.

Ngược lại, một `byte[]` có thể có shallow size lớn nhưng không giữ object khác. Histogram sẽ cho thấy tổng bytes của các mảng; heap dump giúp xác định ai đang giữ từng mảng và chúng có được giải phóng đúng lúc không.

## 6. Chi phí thu thập heap histogram

Heap histogram thường nhẹ hơn heap dump về lượng dữ liệu phải ghi ra, nhưng không nên xem nó là phép đo miễn phí.

### 6.1. Duyệt heap

Để đếm object và tổng shallow bytes theo lớp, JVM phải duyệt một lượng lớn object trong heap. Chi phí phụ thuộc:

- Heap đang sử dụng bao nhiêu.
- Số lượng object và cấu trúc object.
- Garbage collector và trạng thái tiến trình.
- Khả năng dùng song song cho thao tác inspection.
- Tùy chọn live-object hay all-object.

Heap có nhiều object nhỏ có thể tốn thời gian duyệt dù tổng bytes không quá lớn. Ngược lại, heap chứa ít object lớn có đặc điểm chi phí khác.

### 6.2. Full GC và pause

Histogram mặc định thống kê live objects và yêu cầu Full GC trước khi inspection. Full GC có thể:

- Tạm dừng các application thread.
- Tốn CPU để đánh dấu, quét và thu hồi object.
- Làm tăng latency của request.
- Gây ảnh hưởng tới throughput trong khoảng thời gian thu thập.

Tùy chọn `-all` bỏ yêu cầu Full GC trước phép thống kê live-object vì nó bao gồm cả object unreachable. Tuy vậy, nó không loại bỏ chi phí duyệt heap hoặc mọi safepoint cần thiết.

### 6.3. Kết quả nhỏ không có nghĩa thao tác rẻ

Histogram là bảng văn bản nhỏ, nhưng để tạo ra bảng đó JVM có thể đã phải xử lý hàng triệu object. Kích thước file kết quả không phản ánh chi phí thu thập.

## 7. Chi phí thu thập heap dump

Heap dump thường có chi phí cao hơn histogram vì JVM phải duyệt object graph và ghi thông tin object, class, array và reference ra file.

### 7.1. Thời gian dừng ứng dụng

Heap dump live-object mặc định yêu cầu Full GC trước khi dump. Sau đó JVM cần tạo snapshot nhất quán theo cơ chế heap inspection; quá trình này có thể làm application thread dừng hoặc giảm khả năng xử lý trong một khoảng thời gian.

Thời gian phụ thuộc heap occupancy, số object, tốc độ ghi đĩa, nén và môi trường chạy. Không có một con số pause chung có thể áp dụng cho mọi ứng dụng.

Với dịch vụ latency-sensitive, một heap dump trên heap lớn có thể tạo gián đoạn đáng kể. Hãy cân nhắc thời điểm, tải hiện tại, ngân sách downtime và khả năng chuyển traffic trước khi thu thập.

### 7.2. CPU và I/O

Dump cần CPU để duyệt heap, định dạng dữ liệu và có thể nén output. Nó cũng tạo I/O lớn:

- Ghi nhiều dữ liệu lên filesystem.
- Có thể cạnh tranh băng thông với log, database, file upload hoặc tác vụ khác.
- Nén tăng CPU và có thể kéo dài thời gian dump.
- Công cụ phân tích sau đó cũng cần CPU và RAM đáng kể.

Nếu dump vào cùng volume đang gần đầy hoặc có I/O bận, thao tác có thể làm các dịch vụ khác chậm hoặc thất bại.

### 7.3. Dung lượng file và không gian trống

Kích thước heap dump phụ thuộc số object, loại dữ liệu, layout và tùy chọn dump. Không thể suy ra chính xác file sẽ bằng `-Xmx` hay bằng heap used. Tuy nhiên, cần dự trù dung lượng lớn và kiểm tra volume trước khi bắt đầu.

Trước khi dump, xác nhận:

- Thư mục đích tồn tại và JVM có quyền ghi.
- Volume còn đủ dung lượng cho file dump và log liên quan.
- Có quota/container ephemeral-storage phù hợp.
- Có chính sách dọn dẹp file cũ sau khi phân tích.
- Không ghi vào thư mục công khai hoặc thư mục được đồng bộ ngoài ý muốn.

Nếu filesystem hết dung lượng giữa chừng, dump có thể thất bại và ứng dụng vẫn đã chịu một phần chi phí thu thập.

### 7.4. Nén là một đánh đổi

Nén có thể giảm I/O và dung lượng lưu trữ nhưng tăng CPU và thời gian tạo dump. Nếu CPU đang bão hòa, nén mức cao có thể làm incident nặng hơn. Nếu disk hoặc network transfer là nút thắt, nén có thể hữu ích.

Chọn mức nén theo bottleneck hiện tại, không chỉ theo dung lượng file mong muốn.

## 8. Bảo mật và quyền truy cập đối với heap dump

Heap dump có thể chứa dữ liệu nhạy cảm còn trong bộ nhớ:

- Access token, session ID, cookie hoặc API key.
- Thông tin cá nhân và nội dung request.
- Dữ liệu thanh toán, địa chỉ hoặc thông tin tài khoản.
- SQL statement, message payload hoặc dữ liệu cache.
- Secret tạm thời đang được ứng dụng xử lý.

Vì vậy:

1. Chỉ người có nhiệm vụ điều tra mới được đọc dump.
2. Lưu trong thư mục hạn chế quyền truy cập.
3. Mã hóa khi truyền và lưu trữ theo chính sách tổ chức.
4. Không đính kèm dump vào ticket hoặc chat công khai.
5. Đặt thời hạn lưu và xóa an toàn sau khi hoàn tất phân tích.
6. Nếu cần chia sẻ, ưu tiên histogram đã loại thông tin nhạy cảm hoặc một báo cáo phân tích thay cho file dump nguyên gốc.

Không coi heap dump là file log vô hại. Nó có thể chứa nội dung bộ nhớ của tiến trình tại thời điểm thu thập.

## 9. JFR trong chẩn đoán bộ nhớ

Java Flight Recorder ghi nhận sự kiện runtime theo thời gian, gồm các sự kiện liên quan allocation, garbage collection, thread, lock và hoạt động JVM khác. JFR giúp hiểu **điều gì xảy ra trước và trong lúc heap tăng**, trong khi histogram và heap dump cho biết trạng thái heap tại thời điểm thu thập.

Một số câu hỏi JFR có thể hỗ trợ:

- Thread hoặc code path nào tạo nhiều object?
- Allocation rate tăng vào thời điểm nào?
- GC xảy ra thường xuyên hay kéo dài?
- Có allocation lớn hoặc pressure tăng theo workload không?
- Hoạt động nào trùng với giai đoạn latency tăng?

JFR không phải heap dump. Một recording thông thường không chứa đầy đủ đồ thị object để truy vấn retained size và đường đi tới GC roots như heap dump.

### 9.1. Kết hợp JFR và histogram

Quy trình ví dụ:

1. Dùng JFR để xác định thời điểm allocation tăng hoặc GC pressure xuất hiện.
2. Thu histogram ở thời điểm tải đại diện để tìm lớp đang chiếm shallow bytes.
3. So sánh histogram ở các thời điểm tương đương để xem lớp nào tăng và không giảm sau GC.
4. Nếu cần biết object nào giữ dữ liệu, thu heap dump có kiểm soát.
5. Dùng dominator tree và paths to GC roots để xác định nguồn giữ object.

JFR giúp tìm **nguồn tạo allocation**; histogram giúp khoanh vùng **nhóm lớp đang tồn tại**; heap dump giúp tìm **quan hệ giữ object**.

### 9.2. JFR thường phù hợp hơn cho quan sát liên tục

JFR có thể ghi nhận dữ liệu trong thời gian dài với cấu hình phù hợp và thường có overhead thấp hơn thao tác heap dump toàn bộ. Tuy nhiên overhead thực tế phụ thuộc event, settings, sampling, workload và thời gian ghi.

Không nên bật mọi event ở mức chi tiết cao trong thời gian dài mà không cân nhắc chi phí. Dùng cấu hình mặc định phù hợp hoặc profile recording khi điều tra, và kiểm tra kích thước recording cũng như overhead trong môi trường đại diện.

## 10. Quy trình thu thập trong production

Một quy trình thận trọng có thể chia thành các mức:

### Mức 1 — Quan sát trước

- Kiểm tra heap usage, GC logs/metrics và JFR recording nếu có.
- Xác định PID, JVM version, thời điểm incident và workload.
- Xác định giới hạn CPU, latency, memory và disk hiện tại.
- Không bắt đầu bằng heap dump nếu chưa rõ câu hỏi cần trả lời.

### Mức 2 — Thu histogram

```bash
jcmd 12345 GC.class_histogram
```

Ghi lại thời gian chạy, PID, timestamp, tùy chọn `-all` hay mặc định và trạng thái tải. Nếu cần tránh Full GC trước phép thống kê, cân nhắc `-all` và hiểu rằng kết quả bao gồm object unreachable.

### Mức 3 — Thu heap dump khi cần đường tham chiếu

```bash
jcmd 12345 GC.heap_dump /secure-diagnostics/app-heap-2026-11-15.hprof
```

Chỉ chạy khi đã xác nhận dung lượng, quyền truy cập, mức ảnh hưởng pause và nơi lưu. Với hệ thống có traffic lớn, cân nhắc giảm traffic hoặc chuyển tải nếu kiến trúc cho phép.

### Mức 4 — Phân tích và kết luận

- Mở dump trong công cụ phân tích được tổ chức chấp thuận.
- Xác định dominator và retained size.
- Truy tìm GC roots.
- Đối chiếu với JFR, metrics, logs và vòng đời object trong code.
- Ghi lại bằng chứng cần thiết, không chia sẻ dump thô rộng rãi.

### Mức 5 — Lưu giữ và dọn dẹp

- Lưu kết quả phân tích và histogram cần thiết.
- Giới hạn quyền đọc file HPROF.
- Xóa dump theo thời hạn đã định.
- Ghi lại lệnh, tùy chọn và thời gian thu thập để có thể tái hiện.

## 11. Tự động tạo heap dump khi OutOfMemoryError

JVM hỗ trợ tùy chọn:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/secure-diagnostics -jar app.jar
```

Khi gặp `OutOfMemoryError`, JVM cố gắng tạo heap dump theo cấu hình. Tùy chọn này hữu ích vì sự cố có thể làm ứng dụng không còn hoạt động ổn định để người vận hành chủ động gọi lệnh.

Tuy nhiên, cần lưu ý:

- Dump không ngăn hoặc khắc phục `OutOfMemoryError`.
- Việc tạo dump cần dung lượng đĩa và thời gian.
- Nếu filesystem hết dung lượng hoặc không ghi được, dump có thể không tạo thành công.
- File vẫn chứa dữ liệu nhạy cảm và cần được bảo vệ.
- Dump được tạo khi OOME có thể phản ánh heap ở trạng thái áp lực cao; phân tích có thể cần kết hợp logs và JFR.

Hãy cấu hình `HeapDumpPath` tới volume có dung lượng và quyền truy cập phù hợp. Không nên mặc định thư mục làm việc hiện tại luôn là nơi an toàn hoặc đủ dung lượng.

## 12. Những yếu tố làm chi phí thay đổi

| Yếu tố | Histogram | Heap dump |
| --- | --- | --- |
| Heap occupancy | Tăng lượng dữ liệu cần kiểm tra | Tăng lượng object/reference cần dump |
| Số object | Tăng chi phí duyệt và đếm | Tăng chi phí duyệt và ghi object |
| Full GC | Mặc định live histogram yêu cầu Full GC; `-all` bao gồm unreachable | Mặc định live dump yêu cầu Full GC; `-all` bao gồm unreachable |
| CPU | Duyệt heap, có thể dùng parallel inspection | Duyệt heap, serialize dump, có thể nén |
| Disk I/O | Kết quả văn bản thường nhỏ | File có thể rất lớn |
| Pause/latency | Có thể gây pause đáng kể | Có thể gây pause đáng kể và kéo dài |
| Bảo mật | Thường chỉ có tên lớp và số liệu | Có thể chứa nội dung object nhạy cảm |

Không thể đưa ra một thời gian thu thập cố định chỉ dựa vào `-Xmx`. Cần đo trên workload và heap gần với production, đồng thời dành dung lượng và thời gian dự phòng.

## 13. Các lệnh chẩn đoán hữu ích

| Mục tiêu | Lệnh |
| --- | --- |
| Liệt kê JVM nhìn thấy được | `jcmd -l` |
| Xem trợ giúp histogram | `jcmd <pid> help GC.class_histogram` |
| Thu histogram live objects | `jcmd <pid> GC.class_histogram` |
| Thu histogram gồm unreachable | `jcmd <pid> GC.class_histogram -all` |
| Xem trợ giúp heap dump | `jcmd <pid> help GC.heap_dump` |
| Tạo heap dump live objects | `jcmd <pid> GC.heap_dump /path/app.hprof` |
| Tạo dump gồm unreachable | `jcmd <pid> GC.heap_dump -all /path/app-all.hprof` |
| Tạo dump có nén | `jcmd <pid> GC.heap_dump -gz=1 /path/app.hprof.gz` |

Các ví dụ dùng PID minh họa. Thay `<pid>` bằng process ID thật; dùng đường dẫn hợp lệ trên hệ điều hành đích. Nên gọi `help` trên chính JVM mục tiêu để xác nhận cú pháp và tùy chọn được hỗ trợ.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Histogram cho biết object nào giữ memory. | Histogram chỉ nhóm instance và shallow bytes theo lớp; cần heap dump để tìm reference path và dominator. |
| `#bytes` trong histogram là retained size. | Đây là tổng shallow size theo lớp. |
| Heap dump luôn chỉ chứa object live. | Mặc định dump live objects và yêu cầu Full GC; `-all` có thể gồm cả object unreachable. |
| `-all` làm lệnh inspection không tốn chi phí. | Nó tránh Full GC trước để lọc live objects, nhưng heap vẫn phải được kiểm tra và dump. |
| File dump có kích thước bằng `-Xmx`. | Kích thước phụ thuộc object graph, dữ liệu và tùy chọn; không thể suy ra chính xác từ heap maximum. |
| Histogram nhỏ nên lệnh luôn rẻ. | Kết quả nhỏ nhưng JVM có thể phải duyệt toàn bộ heap và yêu cầu Full GC. |
| JFR thay thế heap dump. | JFR ghi sự kiện theo thời gian; heap dump lưu đồ thị object tại một thời điểm. |
| Số instance lớn đồng nghĩa memory leak. | Có thể là tải hợp lệ, cache hoặc batch; cần so sánh qua thời gian và tìm đường giữ object. |
| Có heap dump khi OOME nghĩa là đã xử lý OOME. | Dump chỉ cung cấp dữ liệu để điều tra; nó không sửa nguyên nhân thiếu bộ nhớ. |
| Có thể gửi HPROF như file log thông thường. | HPROF có thể chứa secret và dữ liệu người dùng; cần kiểm soát quyền truy cập và thời hạn lưu. |

## 15. Bài tập thực hành

### Bài 1 — Đọc histogram

Chạy một ứng dụng nhỏ tạo nhiều `String`, `byte[]` và DTO. Thu `GC.class_histogram`, giải thích sự khác nhau giữa `#instances` và `#bytes`, rồi chỉ ra vì sao kết quả không cho biết retained size.

### Bài 2 — So sánh live và all objects

Tạo nhiều object tạm thời rồi bỏ tham chiếu. Thu histogram mặc định và histogram `-all`. Ghi rõ tùy chọn nào yêu cầu Full GC trước inspection và vì sao kết quả có thể khác nhau.

### Bài 3 — Phân tích heap dump

Tạo một cache giữ nhiều DTO. Dump heap, mở bằng công cụ phân tích HPROF, tìm cache trong dominator tree và kiểm tra paths to GC roots. Giải thích object nào đang giữ dữ liệu.

### Bài 4 — Đo chi phí thu thập

Trên môi trường thử nghiệm, ghi lại thời gian chạy histogram và heap dump với heap nhỏ và heap lớn. Theo dõi pause, CPU, I/O và kích thước file. Không suy rộng kết quả từ máy thử nghiệm sang production khi workload khác nhau.

### Bài 5 — JFR kết hợp histogram

Ghi một JFR recording trong lúc ứng dụng tạo nhiều object. Xác định khoảng thời gian allocation tăng, sau đó thu histogram và so sánh lớp nổi bật. Giải thích vì sao JFR cho biết hoạt động theo thời gian còn histogram là snapshot.

### Bài 6 — Chuẩn bị quy trình production

Viết checklist vận hành trước khi tạo heap dump: PID, tải hiện tại, ngân sách pause, dung lượng volume, quyền ghi, nơi lưu an toàn, người được phép truy cập và thời hạn xóa.

## 16. Tài liệu Java 17 chính thức

- [Java SE 17 jcmd tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cú pháp lệnh chẩn đoán `GC.class_histogram`, `GC.heap_dump` và mô tả impact.
- [Java SE 17 jmap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): tài liệu công cụ bản đồ heap; với diagnostic command trên JVM đang chạy, xem `jcmd`.
- [Java SE 17 Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): cấu hình recording và các mức thu thập sự kiện.
- [Eclipse Memory Analyzer (MAT)](https://eclipse.dev/mat/): công cụ phân tích heap dump HPROF, histogram, dominator tree và GC roots.

Heap histogram là cách nhanh để biết **lớp nào đang chiếm shallow heap**; heap dump giúp tìm **object nào đang giữ bộ nhớ và vì sao nó còn reachable**; JFR cho biết **allocation và hoạt động JVM diễn ra khi nào**. Thu thập histogram hoặc dump đều có thể gây pause và tiêu tốn CPU; heap dump còn cần nhiều I/O, dung lượng lưu trữ và bảo vệ dữ liệu nhạy cảm. Hãy bắt đầu bằng dữ liệu ít tốn kém hơn, chỉ thu dump khi cần phân tích quan hệ tham chiếu và luôn tính trước chi phí vận hành.
