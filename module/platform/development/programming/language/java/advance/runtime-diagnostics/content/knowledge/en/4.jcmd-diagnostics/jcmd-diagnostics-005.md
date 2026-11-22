# 4.5 Chọn đường dẫn đầu ra theo ngữ cảnh của JVM đích và kiểm tra dung lượng còn lại

Khi chẩn đoán Java bằng **jcmd**, một lệnh có thể được gõ trên Linux host, bên trong container, hoặc qua công cụ điều khiển Pod; nhưng **tệp heap dump hay JFR được tạo bởi JVM đích**. Vì vậy, đường dẫn đầu ra phải được hiểu theo **filesystem/mount namespace và thư mục làm việc của JVM đích**, không phải mặc nhiên theo thư mục nơi người vận hành gõ lệnh. Nếu chọn sai, lệnh có thể báo **No such file or directory**, **Permission denied**, **Read-only file system** hoặc **No space left on device**; tệ hơn, dump có thể được tạo thành công nhưng nằm ở vị trí khó truy xuất, bị xóa khi container khởi động lại hoặc làm đầy volume chứa dữ liệu ứng dụng.

Trong nhóm **Công cụ jcmd**, bài này tập trung vào **cách quyết định vị trí lưu file**, **kiểm tra đủ không gian trước khi thu thập** và **xác minh file sau khi ghi**. Các ví dụ jcmd dựa trên **JDK 21/HotSpot**; cú pháp lệnh và khả năng attach phải được xác nhận lại trên JVM thật. Không dùng các lệnh tạo heap dump lên production chỉ để thử bài học.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **đường dẫn được JVM đích xử lý** với **đường dẫn chuyển hướng stdout do shell gọi jcmd xử lý**.
- Dự đoán sự khác nhau giữa đường dẫn tuyệt đối, tương đối, thư mục làm việc của JVM và đường dẫn chỉ tồn tại trên host hoặc trong container.
- Chọn volume hoặc thư mục ghi có **quyền**, **dung lượng**, **inode**, **quota**, **khả năng lưu giữ** và **cơ chế lấy file ra** phù hợp.
- Thực hiện preflight với **pwd, id, ls/stat, df -h, df -i** trong đúng môi trường và hiểu giới hạn của từng phép kiểm tra.
- Ước lượng dung lượng cần thiết cho **JFR** và **heap dump**, phân biệt dung lượng file đầu ra với bộ đệm/repository tạm và các công việc ghi đồng thời.
- Hiểu vì sao **Docker overlay**, **bind mount**, **Docker volume**, **Kubernetes emptyDir/PVC** và **tmpfs** dẫn tới các lựa chọn khác nhau.
- Kiểm tra kết quả sau khi jcmd thành công, sao chép tệp có kiểm soát và không nhầm file thiếu/truncated với dữ liệu chẩn đoán hợp lệ.

## 2. Câu hỏi nền tảng: ai thực sự mở file đầu ra?

**jcmd** là tiện ích yêu cầu **JVM đang chạy** thực thi một diagnostic command. Trong trường hợp JVM ghi file, quá trình ghi thường diễn ra **trong process của JVM** với quyền truy cập và filesystem mà JVM nhìn thấy. Người gọi jcmd có thể nằm ở vị trí khác.

Xem ba thao tác sau trên JDK 21 HotSpot; **12345** là PID minh họa, không được dùng nguyên số này trên máy thực:

~~~bash
jcmd 12345 VM.version
jcmd 12345 Thread.print -l > ./thread-dump.txt
jcmd 12345 GC.heap_dump /diagnostics/heap/incident-001.hprof
~~~

Ba thao tác có **ba ý nghĩa đầu ra**:

| Thao tác | Dữ liệu đầu ra nằm ở đâu? | Ai quyết định đường dẫn? |
| --- | --- | --- |
| **VM.version** | Nội dung text trong stdout của tiện ích jcmd | Không tạo file dữ liệu dump trong ví dụ. |
| **Thread.print -l > ./thread-dump.txt** | **./thread-dump.txt** theo thư mục làm việc của **shell chạy jcmd** | Toán tử **>** do shell xử lý; nếu dùng shell ở host thì file ở host, nếu shell ở container thì file ở container. |
| **GC.heap_dump /diagnostics/heap/incident-001.hprof** | File HPROF ở đường dẫn mà **JVM đích** truy cập được | Tên file là **đối số của diagnostic command**, được thực thi bởi JVM. |

Tương tự, với lệnh:

~~~bash
jcmd 12345 JFR.dump name=incident filename=/diagnostics/jfr/incident-001.jfr
~~~

**/diagnostics/jfr/incident-001.jfr** phải có ý nghĩa với **JVM đích**. File không tự xuất hiện tại cùng đường dẫn trên laptop/host chỉ vì bạn chạy jcmd từ đó.

**Phân biệt thêm:** **jcmd -f commands.txt** đọc **tệp đầu vào chứa lệnh** từ phía công cụ jcmd. Còn tùy chọn **filename=...** của **JFR.dump** hoặc tham số file của **GC.heap_dump** yêu cầu JVM tạo **tệp đầu ra**. Không coi mọi đường dẫn xuất hiện trên cùng dòng lệnh là cùng một phía filesystem.

### 2.1. Hai chiều vận hành với một JVM trong container

Giả sử có container **orders-java**, nơi JVM nhìn thấy:

~~~text
/app                      ứng dụng và thư mục làm việc
/diagnostics              điểm mount cho file chẩn đoán
/diagnostics/jfr          thư mục ghi JFR
/diagnostics/heap         thư mục ghi heap dump
~~~

Trên Linux host, thư mục **/srv/diag/orders/** được bind mount vào **/diagnostics**. Khi đó:

- JVM nhận **/diagnostics/heap/a.hprof**, mở file qua đường dẫn container và ghi vào mount.
- Người dùng trên host có thể thấy cùng dữ liệu ở **/srv/diag/orders/heap/a.hprof**, nếu đây thật sự là bind mount đã cấu hình.
- Gửi **/srv/diag/orders/heap/a.hprof** cho jcmd làm đường dẫn dump **không đúng**, nếu JVM không có đường dẫn host đó trong mount namespace của nó.
- Một container khác có thể mount **cùng volume** tại tên đường dẫn khác; cần xác minh cách mount của **đúng container JVM**.

Đường dẫn trên host và trong container là **hai tên của vùng lưu trữ theo cấu hình mount**, không phải hai chuỗi có thể tự chuyển đổi từ tên container.

## 3. Đường dẫn tuyệt đối, tương đối và working directory

### 3.1. Đường dẫn tuyệt đối là mặc định an toàn hơn

Với file do JVM tạo, ưu tiên **đường dẫn tuyệt đối trong filesystem của JVM**:

~~~bash
jcmd 12345 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
jcmd 12345 JFR.dump name=incident filename=/diagnostics/jfr/orders-incident-001.jfr
~~~

Điều kiện bắt buộc là **/diagnostics/heap** và **/diagnostics/jfr** thực sự tồn tại, phù hợp quyền của JVM và đủ không gian. Những lệnh trên là **ví dụ cách đặt tên**, không xác nhận đường dẫn hay dung lượng của một môi trường thực nào.

Sử dụng tên file có khả năng phân biệt **service/instance/thời điểm/incident** thay vì lặp lại **heap.hprof**. Mặc định, **GC.heap_dump** trên JDK 21 có tùy chọn **-overwrite** với giá trị **false**; đừng dựa vào việc ghi đè file cũ và đừng bật ghi đè khi chưa có lý do rõ ràng.

### 3.2. Đường dẫn tương đối có thể khiến file nằm ngoài dự kiến

Ví dụ:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
jcmd 12345 JFR.dump name=incident filename=incident.jfr
~~~

Không nên suy luận hai file nằm trong thư mục hiện tại của terminal jcmd. Chúng được tạo từ góc nhìn của **JVM đích**. Với các đường dẫn tương đối của những lệnh này, hãy xem **working directory của JVM** hoặc nơi JVM khởi chạy theo cơ chế cụ thể; **đừng lấy cwd của tiện ích jcmd để kết luận**.

Ví dụ, bạn có thể đứng ở **/home/operator/** trên host, nhưng Java process được khởi chạy từ **/app** trong container. File không nhất thiết nằm ở **/home/operator/**.

Trong Linux, nếu có quyền xem procfs của **đúng JVM** từ góc nhìn tương ứng:

~~~bash
readlink /proc/12345/cwd
~~~

Lệnh trả **thư mục làm việc hiện tại của process** mà procfs đó nhìn thấy. Nếu JVM trong container có PID **1** nhưng host PID **48210**, **/proc/1/cwd** trong container và **/proc/48210/cwd** trên host có thể đại diện cùng process theo hai namespace. Đường dẫn hiển thị và khả năng truy cập còn phụ thuộc mount namespace và quyền đọc liên kết. Đây là **bước xác minh**, không phải phép biến đổi PID tự động.

**System.getProperty("user.dir")** trong Java thường phản ánh thư mục làm việc Java nhận tại thời điểm khởi chạy, nhưng giá trị property có thể bị thay đổi và không phải phép kiểm tra hệ điều hành cho mọi biến đổi cwd. Khi cần biết file được mở ở đâu, hãy ưu tiên **đường dẫn tuyệt đối được cấu hình rõ ràng** và xác minh từ góc nhìn JVM.

### 3.3. Không dựa vào một đường dẫn ngầm định /tmp

Một số chế độ JFR dùng **repository tạm**, thường mặc định trong vùng temporary directory của hệ điều hành. Còn file xuất của **JFR.dump**/**JFR.start** có thể được cấu hình ở đường dẫn khác. Vì vậy, có thể xảy ra tình trạng **volume chứa file cuối còn trống** nhưng **/tmp hoặc repository của JFR hết chỗ**. Cần xem cả hai vị trí nếu dùng JFR với **disk=true**.

**/tmp** không phải lúc nào cũng cùng loại storage: có thể nằm trong container writable layer, trên volume khác hoặc trên **tmpfs**. Chỉ dùng **df/findmnt/mount** và cấu hình container thực tế mới biết. Việc chọn **/tmp** vì “ai cũng có” không thay thế kiểm tra dung lượng, quota, quyền ghi hay vòng đời dữ liệu.

## 4. Chọn vị trí theo vòng đời dữ liệu và kiến trúc triển khai

| Vị trí | Ưu điểm | Hạn chế cần kiểm tra |
| --- | --- | --- |
| **Thư mục ứng dụng trong writable layer container** | Đường dẫn có thể dễ gọi | Có thể bị xóa khi container bị thay thế, dùng chung nguồn lực với image/log layer và chịu hạn mức ephemeral storage. Có thể bị chặn khi root filesystem chỉ đọc. |
| **Docker bind mount** | Có ánh xạ cụ thể sang đường dẫn của Linux host; dễ thu hồi file khi thiết lập đúng | Quyền chủ sở hữu, SELinux/ACL khi có, đường dẫn host và sự khác biệt host/container phải được xác nhận. Host ở đây là máy chạy Docker daemon, không mặc định là máy dùng Docker CLI. |
| **Docker named volume** | Docker quản lý vòng đời lưu trữ, có thể chia sẻ với container khác theo cấu hình | Không suy ra đường dẫn host từ tên volume; dùng metadata Docker để xác định. Khả năng còn trống phụ thuộc filesystem/driver/quota thực tế. |
| **Kubernetes emptyDir trên disk** | Thư mục tạm cho Pod; có thể mount vào container Java và sidecar | Thường mất khi Pod bị gỡ khỏi node; chịu giới hạn ephemeral-storage/sizeLimit và áp lực disk của node. |
| **Kubernetes emptyDir với medium: Memory** | Truy cập I/O nhanh trong tmpfs | Chiếm **bộ nhớ**, chịu memory limit; heap dump lớn có thể gây memory pressure/OOM thay vì chỉ “đầy đĩa”. |
| **Kubernetes PVC** | Có thể phù hợp nhu cầu lưu giữ file qua vòng đời Pod, tùy StorageClass và policy | Kiểm tra quota thực, quyền mount, hiệu năng, filesystem, quyền truy cập đồng thời và dữ liệu nhạy cảm. PVC không tự bảo đảm luôn còn dung lượng. |
| **NFS/remote volume/object pipeline** | Có thể thuận tiện cho thu hồi và quản lý bằng policy | I/O và trạng thái network làm tăng thời gian dump; đường dẫn phải là mount/file API thật với JVM. Object store URI không đương nhiên dùng được như đường dẫn HPROF/JFR. |

Nên có **thư mục chẩn đoán riêng**, cách ly với dữ liệu vận hành quan trọng, và quy trình kiểm soát giữ/xóa file. Chọn mục tiêu theo **mục đích chẩn đoán**: JFR ngắn thường cần ít chỗ hơn heap dump lớn, nhưng không có quy tắc kích thước cố định. File dump có thể chứa dữ liệu nhạy cảm, vì vậy việc chọn nơi lưu là một phần của vận hành và bảo mật.

### 4.1. Ví dụ bind mount Docker

Ví dụ minh họa thiết kế cấu hình:

~~~bash
docker run --name orders-java \
  --mount type=bind,source=/srv/diag/orders,target=/diagnostics \
  my-orders-image
~~~

Trong JVM container, dùng **/diagnostics/...**; trên Linux host của Docker daemon, kiểm tra **/srv/diag/orders/...**. Đây là lệnh khởi chạy một container minh họa; không chạy lại nếu dịch vụ đang hoạt động.

Nếu muốn kiểm tra mount của container đang chạy, đây là thao tác đọc metadata:

~~~bash
docker inspect --format '{{json .Mounts}}' orders-java
~~~

Các trường từ metadata giúp xác định **Source** và **Destination**. Không tự suy ra từ tên image hoặc tên container.

**Docker Desktop:** Linux containers hoạt động trong Linux VM; vị trí host/bind mount có tầng ánh xạ với máy desktop. Cần dùng metadata/đường dẫn mà Docker hỗ trợ, thay vì suy ra Linux **/proc** hoặc thư mục của VM trùng với Windows/macOS.

### 4.2. Ví dụ cấu trúc Kubernetes

Đoạn YAML chỉ minh họa **cách mount**, không phải manifest hoàn chỉnh:

~~~yaml
spec:
  containers:
    - name: app
      image: example/orders:1.0
      volumeMounts:
        - name: diagnostic-files
          mountPath: /diagnostics
  volumes:
    - name: diagnostic-files
      emptyDir:
        sizeLimit: 4Gi
~~~

Dù ví dụ khai báo **sizeLimit: 4Gi**, không nên đọc **df -h** rồi kết luận có thể sử dụng đủ 4 GiB: **sizeLimit**, giới hạn **ephemeral-storage** của container/Pod và node pressure có thể hạn chế mức thực tế theo cơ chế đo/eviction của Kubernetes. Kubelet và cấu hình filesystem quyết định cách giám sát. Khi cần lưu dữ liệu qua việc gỡ Pod, một **PVC đã được cấp và mount đúng** thường phù hợp hơn emptyDir.

## 5. Chọn loại đầu ra trước khi dự trù dung lượng

### 5.1. JFR: file kết quả và repository không nhất thiết cùng nơi

**JFR.start** có thể bắt đầu recording và, khi recording dừng, ghi file theo **filename** đã cấu hình. Trong tài liệu **jcmd JDK 21**, **duration=60s** quy định thời lượng ghi; **filename** chỉ định file xuất khi recording kết thúc. Mặc định **disk=true** có thể dùng repository trên disk trong khi recording. **JFR.dump** tạo một file dump từ recording đang chạy và **recording tiếp tục chạy** sau thao tác dump.

Ví dụ minh họa, chỉ chạy khi đã preflight:

~~~bash
jcmd 12345 JFR.start name=orders-triage settings=default duration=60s filename=/diagnostics/jfr/orders-triage-001.jfr
jcmd 12345 JFR.check
~~~

File **orders-triage-001.jfr** có thể chỉ xuất hiện khi recording dừng, không bắt buộc xuất hiện ngay sau khi JFR.start trả thành công. Hãy kiểm tra **JFR.check**, kết quả chẩn đoán và thời gian dự kiến trước khi kết luận file bị thiếu.

Một lựa chọn khác, nếu recording **orders-triage** đang chạy:

~~~bash
jcmd 12345 JFR.dump name=orders-triage filename=/diagnostics/jfr/orders-triage-snapshot-001.jfr
~~~

**JFR.dump** không tự dừng recording đang chạy. Nếu không chỉ định **name**, cú pháp JDK 21 cho phép dump dữ liệu từ nhiều recording hoạt động; dùng tên rõ ràng để tránh nhầm nội dung. Với **JFR.dump**, đối số filename có thể là thư mục để JVM tự tạo tên file; khi cần dự đoán chính xác vị trí và kiểm tra kết quả, hãy chỉ định **tên file đầy đủ**.

Các tùy chọn **%p** và **%t** được JDK 21 hỗ trợ trong **filename** của JFR để chèn PID/thời điểm của JVM; điều này hữu ích tránh trùng tên. Không suy rộng rằng mọi diagnostic command đều hỗ trợ giống nhau.

**Ngân sách lưu trữ JFR** nên tính cả: repository trung gian (nếu sử dụng), file xuất cuối, các lần dump lặp, log chẩn đoán liên quan và phần dự phòng. **JFR.start maxsize** có thể giới hạn lượng dữ liệu recording giữ trên disk theo cơ chế của JFR, nhưng không bảo đảm toàn bộ filesystem sẽ không đầy bởi các tệp khác hoặc một loạt file dump độc lập.

### 5.2. Heap dump: kích thước lớn, rủi ro thời gian dừng

**GC.heap_dump** tạo HPROF heap dump và được JDK 21 ghi nhận **Impact: High**, phụ thuộc heap size và nội dung. Theo tài liệu, lệnh thường yêu cầu full GC trước khi dump, trừ khi dùng **-all** để dump cả object không còn reachable. Bởi vậy, một heap dump có thể tạo pause đáng kể và tác động cả CPU, I/O, disk.

Ví dụ tên file tuyệt đối:

~~~bash
jcmd 12345 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
~~~

JDK 21 còn hỗ trợ tùy chọn nén:

~~~bash
jcmd 12345 GC.heap_dump -gz=1 /diagnostics/heap/orders-incident-001.hprof.gz
~~~

**Không chạy cả hai lệnh trên cùng sự cố chỉ để “đảm bảo có file”**: đó là hai thao tác dump riêng và có thể tạo tải lớn. **-gz=1** yêu cầu mức nén GZIP tương ứng, có thể giảm kích thước trên disk nhưng thêm xử lý CPU; tỷ lệ nén **không cố định** và không bảo đảm file nhỏ hơn một ngưỡng nào. File nén cần công cụ hỗ trợ định dạng khi phân tích.

**-Xmx** cho biết giới hạn heap tối đa của JVM khi cấu hình có hiệu lực, nhưng **không phải kích thước chính xác của file HPROF**. Live set, object graph, cấu trúc HPROF, khả năng nén và số liệu dump thực tế làm kích thước biến thiên. Một heap dump có thể rất lớn; với production hãy dùng **dự báo bảo thủ dựa trên heap, số liệu đã quan sát và dự phòng**, thay vì “file chắc chắn chỉ bằng 10% -Xmx”.

**Cảnh báo:** heap dump có thể chứa token, phiên làm việc, thông tin cá nhân và chuỗi cấu hình còn nằm trong heap. Tránh mount public, tránh sao chép vào thư mục chia sẻ không kiểm soát và dùng chính sách thu hồi/xóa thích hợp sau khi phân tích.

### 5.3. Crash/OOM dump và JFR dump là hai cơ chế khác nhau

Khi JVM được khởi chạy với:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/diagnostics/heap
~~~

một heap dump khi **OutOfMemoryError** sẽ dùng đường dẫn đã cấu hình theo tài liệu lệnh **java** và filesystem mà JVM nhìn thấy. Đây là cấu hình **startup**, khác với việc chủ động gửi **jcmd PID GC.heap_dump**. Nếu đường dẫn không được ghi hoặc hết dung lượng đúng lúc OOM, tệp có thể không xuất hiện; không nên coi flag là sự bảo đảm thu thập tuyệt đối.

Tương tự, file JFR được xuất khi **recording kết thúc**, khi chạy **JFR.dump**, hoặc khi cấu hình **dumponexit**, tùy hình thức. Không giả định chỉ cần thấy tùy chọn JFR là file đã nằm tại một vị trí cố định.

## 6. Kiểm tra đúng thư mục sẽ ghi: tồn tại, quyền và filesystem

Giả sử đích mong muốn là **/diagnostics/heap** trong container. Trước khi yêu cầu JVM tạo file, cần kiểm tra **trên chính filesystem mà JVM nhìn thấy**:

~~~bash
id
pwd
ls -ld /diagnostics /diagnostics/heap
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

Lệnh minh họa cho Linux shell có các công cụ tương ứng. Nếu image tối giản không có **sh, df, stat, ps**, đó là hạn chế của image; dùng công cụ debug/runtime thích hợp thay vì mặc định kết luận mount không tồn tại.

**Ý nghĩa từng kiểm tra:**

1. **id**: xem UID/GID của **shell hiện tại**. Quan trọng vì shell qua **docker exec/kubectl exec** có thể được chạy với user khác JVM. **Quyền của người gọi không mặc nhiên là quyền của JVM**.
2. **pwd**: xem cwd của **shell**, chỉ để định hướng; không tự chứng minh cwd của JVM nếu shell là process khác.
3. **ls -ld**: xác nhận thư mục thực sự tồn tại và quan sát owner/group/mode; nếu có ACL, SELinux hoặc mount policy, mode bits chưa đủ kết luận.
4. **df -h thư_mục**: xem filesystem chứa thư mục và lượng block còn trống theo góc nhìn lệnh chạy.
5. **df -i thư_mục**: xem inode còn trống nếu filesystem hỗ trợ. Hết inode có thể không tạo được file dù block còn.
6. Nếu có **findmnt -T /diagnostics/heap** hoặc **stat -f**: xem loại mount/filesystem và hỗ trợ phân biệt overlay, volume, tmpfs.

**Cần đưa vào df một đường dẫn đang tồn tại**. Nếu file đích chưa có, **df -h /diagnostics/heap/incident.hprof** có thể lỗi vì path chưa tồn tại; hãy kiểm tra **thư mục cha**:

~~~bash
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

Nếu **/diagnostics/heap** chưa tồn tại, dùng thư mục cha hiện có để xác định mount, rồi **xác nhận cách tạo thư mục đúng quyền/quy trình** trước khi dump. Tự tạo thư mục dưới một mount điểm sai vị trí có thể khiến dữ liệu rơi vào container writable layer thay vì volume dự kiến.

### 6.1. Kiểm tra quyền bằng đúng danh tính JVM

Giả sử shell trong container chạy root nhưng JVM chạy UID **10001**, lệnh:

~~~bash
test -w /diagnostics/heap
~~~

trả thành công cho root **không chứng minh UID 10001 có thể ghi**. Cần kiểm tra bằng đúng effective user/group của JVM hoặc các quyền ACL/mount được cấu hình. File được tạo bởi JVM phải thuộc vùng mà **JVM có quyền mở/ghi**, không chỉ tiện ích jcmd.

Với Docker, **docker exec --user 10001 ...** có thể giúp kiểm tra một user tương ứng nhưng còn phụ thuộc effective GID, supplementary groups và bảo mật mount. Tránh giả định chỉ từ một UID trùng tên. Trên Kubernetes, xem cấu hình **securityContext**, UID/GID/fsGroup và thực tế permission của volume; việc root nhìn thấy file không bảo đảm JVM user ghi được.

Kiểm tra **read-only root filesystem** (ví dụ Kubernetes **readOnlyRootFilesystem**), mount **:ro**, bind mount chỉ đọc hoặc policy của volume. Khi thư mục đích read-only, **df** có thể vẫn hiển thị nhiều block trống, nhưng ghi sẽ thất bại.

### 6.2. Kiểm tra path vật lý, symlink và inode

Nếu **/diagnostics/heap** là symlink đến vị trí khác, phép kiểm tra trên một parent gần đó có thể đo **nhầm filesystem**. Xác nhận bằng các công cụ có sẵn:

~~~bash
ls -ld /diagnostics/heap
readlink -f /diagnostics/heap
df -h /diagnostics/heap
df -i /diagnostics/heap
~~~

Tùy image, **readlink -f** có thể không có hoặc xử lý symlink khác nhau. Với bảo mật chặt hơn, tránh symlink trỏ ra ngoài volume chẩn đoán và sử dụng một thư mục cụ thể đã được provision.

**Inode** thường không phải giới hạn chính của **một heap dump lớn**, nhưng có thể là vấn đề khi tạo hàng nghìn JFR chunk/file nhỏ hoặc filesystem gần hết inode. Dùng **df -i** để phát hiện loại giới hạn này, song vẫn phải kiểm tra quota và mức tiêu thụ đồng thời.

## 7. “df còn nhiều chỗ” vẫn chưa đủ

Dung lượng báo bởi **df -h** là **snapshot filesystem**, không phải lời hứa cấp phát thành công. Có ít nhất sáu rào cản cần xét:

- **Quota theo user/group/project/volume** có thể nhỏ hơn free space của filesystem. Lệnh df không tự hiển thị mọi giới hạn quota áp dụng.
- **Kubernetes ephemeral-storage limit / emptyDir sizeLimit** và áp lực node có thể khiến Pod bị **evicted**, dù df bên trong container trông còn chỗ.
- **tmpfs** chiếm bộ nhớ; một heap dump vào **emptyDir medium: Memory** có thể gây áp lực RAM hoặc memory OOM.
- **Writable layer** của container có thể dùng chung tài nguyên với image, logs và các container khác; file lớn làm ảnh hưởng node/service.
- **Tệp khác đang ghi đồng thời** có thể chiếm hết dung lượng giữa preflight và lần ghi cuối; không nên coi số đo lúc đầu là bất biến.
- **I/O errors, permission, disk full inode, filesystem read-only, network volume mất kết nối** đều có thể làm tệp tạo ra không đầy đủ.

**Quota** và **filesystem capacity** là hai khái niệm khác nhau. Ví dụ **df** báo 20 GiB trống nhưng Pod chỉ còn 1 GiB ngân sách ephemeral-storage, một dump 4 GiB vẫn có thể khiến workload bị evicted. Vì vậy, muốn dự báo chính xác hơn phải kiểm tra **cả filesystem và giới hạn do container orchestrator/volume định nghĩa**.

### 7.1. Tính ngân sách với phần dự phòng

Đặt:

- **F**: không gian hữu dụng được đo trên đúng filesystem, ở thời điểm preflight.
- **D**: kích thước file dump ước tính; nếu chưa biết thì dùng giả định bảo thủ và ghi rõ.
- **R**: dung lượng dự phòng cho log, ứng dụng, hoạt động nền, thay đổi dữ liệu trong lúc dump.
- **T**: dung lượng tạm bổ sung **trên cùng filesystem** (ví dụ repository JFR, các lần ghi đồng thời) nếu có.
- **Q**: lượng không gian còn có thể sử dụng theo quota/ephemeral/PVC thực sự, nếu bị giới hạn.

Điều kiện kiểm tra ban đầu:

\[
F \ge D+R+T,\qquad Q \ge D+R+T
\]

Nếu **Q** không đo được, không thể kết luận đã bảo đảm đủ chỗ chỉ nhờ **df**. Nếu T nằm trên **filesystem khác**, kiểm tra riêng filesystem đó; không cộng file của một volume vào free space của volume khác.

Ví dụ minh họa với đơn vị **MiB**:

| Thông số | Giá trị giả định |
| --- | ---: |
| Free/usable tại nơi ghi file | 3.072 MiB |
| Dự kiến file heap dump | 2.200 MiB |
| Dự phòng cho hệ thống/log | 768 MiB |
| Tệp tạm cùng filesystem | 0 MiB |
| Tổng cần (ước tính + dự phòng) | 2.968 MiB |
| Headroom ước tính | 104 MiB |

Theo **chỉ báo filesystem**, phép tính vừa đủ, nhưng headroom chỉ **104 MiB** là mỏng; nếu dump lớn hơn dự kiến hoặc quota thấp hơn 2.968 MiB, thao tác sẽ có nguy cơ thất bại. **Không có ngưỡng dự phòng phổ quát** phù hợp mọi workload: cần dựa vào mức ghi nền, giới hạn đang áp dụng và khả năng chịu rủi ro của service.

Không dùng dung lượng **heap used sau GC** làm dự báo chắc chắn cho kích thước HPROF. Không lấy **file size từ lần trước** làm giới hạn tối đa của lần sau. Compression cũng không tạo bảo đảm dung lượng.

### 7.2. Vì sao “df -h /” dễ gây hiểu sai?

Trên Linux container, **/** có thể nằm trên writable overlay, còn **/diagnostics** là PVC hoặc bind mount khác. Khi đó:

~~~bash
df -h /
df -h /diagnostics
~~~

có thể cho **hai filesystem và hai giá trị available khác nhau**. Nếu file thực sự được JVM ghi vào **/diagnostics**, thông số cần kiểm tra là filesystem **chứa /diagnostics**, không phải root filesystem. Tương tự nếu **/tmp** chứa JFR repository nhưng file cuối nằm ở **/diagnostics**, cần kiểm tra **cả hai**.

### 7.3. Khi đã xóa file mà df không tăng

Trên Linux, một file đã bị unlink nhưng **process vẫn giữ file descriptor mở** có thể tiếp tục chiếm block cho đến khi descriptor đóng. Trong tình huống này, lệnh liệt kê directory hoặc **du** có thể không phản ánh toàn bộ block đã dùng, còn **df** vẫn thấy tiêu thụ. Khi điều tra cần kiểm tra các file đã bị xóa nhưng còn mở bằng công cụ phù hợp/quyền phù hợp; **không xóa hoặc kill process tùy tiện** để lấy chỗ.

## 8. Ví dụ Java 21: kiểm tra không gian từ filesystem mà JVM nhìn thấy

**java.nio.file.FileStore** cung cấp **getUsableSpace()**, là lượng byte khả dụng theo góc nhìn JVM đối với một filestore. API nói rõ giá trị **chỉ là gợi ý gần thời điểm đọc, không bảo đảm việc ghi sẽ thành công**. Đây là phép **preflight**, không thay quota/orchestrator hay việc kiểm tra dữ liệu sau ghi.

**Tệp DiagnosticSpacePreflight.java:**

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DiagnosticSpacePreflight {
    private static final long MIB = 1024L * 1024L;

    private static long mibToBytes(String value) {
        return Math.multiplyExact(Long.parseLong(value), MIB);
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 3) {
            System.out.println(
                    "Usage: java DiagnosticSpacePreflight <dir> <estimateMiB> <reserveMiB>");
            return;
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        long estimate = mibToBytes(args[1]);
        long reserve = mibToBytes(args[2]);
        if (estimate < 0 || reserve < 0) {
            throw new IllegalArgumentException(
                    "Estimate and reserve must be nonnegative");
        }

        if (!Files.isDirectory(dir)) {
            System.out.println("Directory exists: false");
            return;
        }

        FileStore store = Files.getFileStore(dir);
        long usable = store.getUsableSpace();
        long required = Math.addExact(estimate, reserve);

        System.out.println("Directory: " + dir);
        System.out.println("Directory exists: true");
        System.out.println("Directory writable (hint): "
                + Files.isWritable(dir));
        System.out.println("File store read-only: "
                + store.isReadOnly());
        System.out.println("Usable MiB (snapshot): " + usable / MIB);
        System.out.println("Required MiB: " + required / MIB);
        System.out.println("Filesystem budget check: "
                + (usable >= required));
    }
}
~~~

Biên dịch bằng JDK 21:

~~~bash
javac --release 21 DiagnosticSpacePreflight.java
java DiagnosticSpacePreflight /diagnostics/heap 2200 768
~~~

**Kết quả có phần cố định và phần phụ thuộc môi trường.** Nếu thư mục không có, chương trình in chính xác:

~~~text
Directory exists: false
~~~

Nếu thư mục có, chương trình in bảy dòng với **Directory**, **Directory exists: true**, **Directory writable (hint)**, **File store read-only**, **Usable MiB (snapshot)**, **Required MiB: 2968**, **Filesystem budget check** theo đúng thứ tự. Giá trị path, writable, read-only, usable và kết luận boolean tùy môi trường; **không có stdout số free space cố định**.

**Đọc đúng giới hạn:**
- Kiểm tra **Files.isWritable** có thể giúp phát hiện lỗi rõ ràng, nhưng vẫn chỉ là kiểm tra tại thời điểm đó; quyền hoặc mount có thể đổi trước khi ghi.
- FileStore có thể không biết **ephemeral-storage limit** hoặc quota khác ở mức orchestrator.
- Chạy chương trình trong JVM/process khác có thể thấy filesystem hoặc UID khác; để có bằng chứng mạnh, chạy trong **đúng container/namespace và user tương ứng với ứng dụng**, hoặc tích hợp một bước kiểm tra có kiểm soát trong ứng dụng thực.
- Chương trình **không tạo file**, không chứng minh hệ thống cho phép tạo mọi file dự kiến, và không thử ghi heap dump.
- Với khối lượng lớn, phải bổ sung quota, latency I/O, inode, log growth và dự phòng.

### 8.1. Ví dụ Java 21 có stdout cố định để hiểu phép tính

**Tệp DumpBudgetExample.java:**

~~~java
public final class DumpBudgetExample {
    public static void main(String[] args) {
        long usableMiB = 3072;
        long estimatedDumpMiB = 2200;
        long reserveMiB = 768;

        long requiredMiB = estimatedDumpMiB + reserveMiB;
        long headroomMiB = usableMiB - requiredMiB;

        System.out.println("Required: " + requiredMiB + " MiB");
        System.out.println("Headroom: " + headroomMiB + " MiB");
        System.out.println("Pass filesystem budget: "
                + (headroomMiB >= 0));
    }
}
~~~

~~~bash
javac --release 21 DumpBudgetExample.java
java DumpBudgetExample
~~~

**stdout chính xác:**

~~~text
Required: 2968 MiB
Headroom: 104 MiB
Pass filesystem budget: true
~~~

Kết luận **true** ở đây chỉ có nghĩa **đúng theo dữ kiện giả định**, chưa tính quota, dữ liệu sinh thêm hoặc thay đổi free space. Đừng cho ví dụ này tự quyết định việc tạo dump thực trên một hệ thống đang chạy.

## 9. Quy trình preflight có kiểm soát cho một JVM trong Docker

Giả sử JVM của service **orders-java** chạy trong Docker Linux, được mount **/diagnostics** và có thể dùng **jcmd**. Ví dụ sau mô tả quy trình, không phải lệnh đã được thực thi trên một hệ thống thật.

### Bước 1 — Xác nhận đúng container/JVM và danh tính

~~~bash
docker inspect --format '{{.State.Running}}' orders-java
docker inspect --format '{{json .Mounts}}' orders-java
docker exec orders-java id
docker exec orders-java ps -eo pid,ppid,comm
~~~

Các lệnh có thể không khả dụng nếu image tối giản. **Không mặc định Java là PID 1**; init wrapper, shell và PID namespace chia sẻ có thể làm PID JVM khác. Trong các lệnh sau giả sử đã xác minh **PID của JVM trong container là 1**. Với JVM PID khác, thay bằng số thực trong cùng namespace.

Khi có công cụ phù hợp:

~~~bash
docker exec orders-java jcmd 1 VM.version
docker exec orders-java jcmd 1 help GC.heap_dump
docker exec orders-java jcmd 1 help JFR.dump
~~~

**jcmd** cần khả năng attach và quyền thích hợp, thường cùng effective user/group theo tài liệu JDK. Lệnh thất bại có thể do image thiếu JDK tools, attach bị hạn chế hoặc dùng sai process; việc chọn đúng PID mới chỉ là điều kiện cần.

### Bước 2 — Kiểm tra thư mục trong container

~~~bash
docker exec orders-java sh -c 'id; ls -ld /diagnostics /diagnostics/heap /diagnostics/jfr'
docker exec orders-java sh -c 'df -h /diagnostics/heap; df -i /diagnostics/heap'
docker exec orders-java sh -c 'df -h /diagnostics/jfr; df -i /diagnostics/jfr'
docker exec orders-java sh -c 'df -h /tmp'
~~~

Các lệnh trên dùng **sh, ls, df** trong container và phù hợp khi image có sẵn chúng. Nếu image không có, có thể dùng tooling khác đã được vận hành phê duyệt để kiểm tra mount/quota từ node hoặc debug container. **Không tự giả định giá trị /tmp hoặc /diagnostics giống ở host**.

Đánh giá **quyền theo UID/GID của JVM**, tính dung lượng dự kiến cùng log/JFR repository và giới hạn có thể gây eviction. **df -i** kiểm tra inode, **df -h** kiểm tra block. Cả hai không đủ thay các giới hạn khác.

### Bước 3 — Chọn một đường dẫn duy nhất và ghi khi có cơ sở

Ví dụ JFR theo thời hạn:

~~~bash
docker exec orders-java jcmd 1 JFR.start name=incident-001 settings=default duration=60s filename=/diagnostics/jfr/orders-incident-001.jfr
~~~

Với heap dump, đây là lệnh riêng **có tác động cao**:

~~~bash
docker exec orders-java jcmd 1 GC.heap_dump /diagnostics/heap/orders-incident-001.hprof
~~~

**Chỉ thực thi heap dump khi đã có phê duyệt vận hành/chấp nhận tác động phù hợp**, có ngân sách dung lượng và có lý do điều tra heap; không chạy như cách “thử đường dẫn”. Nếu chỉ cần xác nhận VM, **VM.version** là phép quan sát ít xâm lấn hơn.

### Bước 4 — Xác minh file cuối từ phía JVM rồi lấy ra

Khi lệnh dump đã hoàn tất, kiểm tra từ đúng container:

~~~bash
docker exec orders-java ls -lh /diagnostics/heap/orders-incident-001.hprof
docker exec orders-java df -h /diagnostics/heap
~~~

Với JFR có **duration=60s**, đợi thời điểm recording kết thúc theo trạng thái và lịch thu, rồi kiểm tra file JFR. **File có tên đúng chưa đủ để kết luận hợp lệ**: xem lệnh có báo lỗi không, dung lượng có hợp lý không, có thể mở bằng công cụ phân tích tương thích không.

Nếu dùng Docker CLI có quyền lấy file và đã xác minh nơi lưu:

~~~bash
docker cp orders-java:/diagnostics/jfr/orders-incident-001.jfr ./orders-incident-001.jfr
~~~

**docker cp** chuyển dữ liệu từ đường dẫn trong container sang đường dẫn local của phía gọi Docker CLI theo cơ chế Docker; file đích cần đủ dung lượng và quyền ở nơi nhận. Với named volume/bind mount, có thể dùng cơ chế thu hồi file riêng; vẫn phải kiểm tra mapping, quyền và toàn vẹn dữ liệu.

Đừng xóa bản gốc cho đến khi việc sao chép/kiểm tra dữ liệu thành công và đáp ứng chính sách lưu giữ. Nếu file là heap dump, bảo vệ quyền đọc và tránh đưa lên kênh công khai.

## 10. Quy trình tương ứng trong Kubernetes

Trong Kubernetes, **/diagnostics** có thể là **emptyDir**, **PVC** hoặc volume do nền tảng quản lý. Giả sử Pod **orders-0**, container **app** trong namespace mặc định của kubeconfig hiện tại; thêm **-n <namespace>** khi cần để tránh chọn nhầm đối tượng.

### Bước 1 — Xác nhận Pod, container, volume và giới hạn

Đọc cấu hình Pod bằng công cụ phù hợp:

~~~bash
kubectl get pod orders-0 -o wide
kubectl describe pod orders-0
kubectl exec orders-0 -c app -- id
kubectl exec orders-0 -c app -- df -h /diagnostics
kubectl exec orders-0 -c app -- df -i /diagnostics
~~~

**kubectl describe** giúp nhận diện volume mount, trạng thái và event liên quan tới Pod; kiểm tra thêm cấu hình **resources.limits.ephemeral-storage**, emptyDir **sizeLimit** và quota ở node/volume nếu dùng chúng. **kubectl exec** chạy process mới bên trong container, không mặc định cùng UID với Java khi có cấu hình riêng.

Đặc biệt, **emptyDir medium: Memory** dùng **tmpfs** và bị tính vào **bộ nhớ container**. Một heap dump kích thước lớn trên tmpfs có thể làm cạn memory budget; file được tạo trong **memory-backed volume** không trở thành file an toàn chỉ vì df còn block.

### Bước 2 — Chọn vùng có vòng đời phù hợp

- Nếu cần recording ngắn và sẽ **thu hồi ngay**, một disk-backed emptyDir có ngân sách rõ có thể phù hợp.
- Nếu cần giữ dữ liệu qua việc thay Pod, chọn **PVC hoặc hạ tầng thu thập hỗ trợ** đã được cấu hình.
- Nếu cần heap dump lớn, phải xét cả **disk free**, **ephemeral-storage/PVC capacity**, **quota**, **I/O throughput** và **giới hạn tác động JVM**.
- Nếu Pod có nhiều container, phải kiểm tra **volumeMount của đúng container Java**, dù sidecar có thể đọc cùng volume ở một đường dẫn khác.

### Bước 3 — Xác minh file tại container đích

~~~bash
kubectl exec orders-0 -c app -- ls -lh /diagnostics/jfr/orders-incident-001.jfr
kubectl exec orders-0 -c app -- df -h /diagnostics
~~~

Để sao chép file, **kubectl cp** có thể được dùng khi container có **tar** và môi trường đáp ứng điều kiện:

~~~bash
kubectl cp -c app orders-0:/diagnostics/jfr/orders-incident-001.jfr ./orders-incident-001.jfr
~~~

Nếu image không có tar hoặc **kubectl cp** lỗi, dùng cơ chế xuất dữ liệu khác mà nền tảng hỗ trợ; không coi lỗi copy là bằng chứng file JVM chưa tồn tại. Đặc biệt với heap dump lớn, kiểm tra giới hạn truyền tải, phiên sao chép, dung lượng nhận và tính toàn vẹn.

## 11. Các bẫy phổ biến về đường dẫn, quota và quyền

| Dấu hiệu | Khả năng đáng kiểm tra | Hành động kiểm chứng phù hợp |
| --- | --- | --- |
| **No such file or directory** | Thư mục cha không tồn tại ở **filesystem của JVM**, dùng nhầm path host, mount sai, symlink hỏng | Kiểm tra mount, **ls -ld** thư mục cha **trong container/JVM**; so Docker/K8s volumeMount. |
| **Permission denied** | JVM UID/GID không có quyền, ACL/SELinux, mount policy | Kiểm tra effective user của JVM, owner/group/mode, ACL/securityContext; đừng thử chỉ bằng shell root. |
| **Read-only file system** | Rootfs hoặc volume mount read-only | Xem readOnlyRootFilesystem, mount options; chọn vị trí ghi được đã provision. |
| **No space left on device** | Hết block, inode, filesystem tạm, quota hoặc storage limit | **df -h**, **df -i** trên **đúng mount**; kiểm tra quota/ephemeral/PVC và JFR repository. |
| **df còn nhiều chỗ nhưng ghi lỗi** | Quota chặt hơn, quyền, inode, storage pressure, concurrent writers | Đừng dừng ở df; kiểm tra nhiều tầng giới hạn và thời điểm lỗi. |
| **jcmd thành công nhưng không thấy file ở host** | File ở mount namespace JVM, relative path, chưa tới lúc JFR dừng, không có bind/volume mapping | Xem đường dẫn từ **container**, JFR.check, Docker/K8s mount và thời gian recording. |
| **JFR.start đã trả thành công nhưng chưa có .jfr** | File được ghi khi recording dừng/theo cấu hình, file name tự sinh | Kiểm tra **JFR.check**, **duration**, **filename**, event/error; không mặc định thất bại ngay. |
| **File dump rất nhỏ hoặc không mở được** | Dump chưa hoàn tất, disk full, lỗi I/O, copy bị ngắt, định dạng/nén không phù hợp | Đọc trạng thái lệnh, kích thước, verify bằng công cụ phân tích, checksum sau copy. |
| **Heap dump làm Pod bị evict** | File vượt ephemeral/emptyDir budget hoặc disk pressure; tmpfs gây memory pressure | Kiểm tra Pod events/limits, dùng vị trí có hạn mức phù hợp và thu hồi kịp thời. |
| **Cùng tên file từ nhiều JVM** | Ghi đè/xung đột, thiếu namespace/instance identifier | Dùng tên duy nhất theo service, instance, thời điểm; xác minh file chưa có. |
| **Không tạo được file sau khi rename/mount** | Path đến filesystem khác, mount/symlink thay đổi, quyền JVM không còn đúng | Kiểm tra mount và **df** lại tại thời điểm thao tác; không dựa vào preflight cũ. |

### 11.1. Phân biệt lỗi ghi và lỗi attach

Nếu nhận **Could not attach to target VM**, cần kiểm tra PID, effective user/group, cùng máy, namespace, attach mechanism và JDK tools. Đây thường **khác** lỗi filesystem của **GC.heap_dump**/**JFR.dump** sau khi JVM đã nhận command.

Nếu attach thành công nhưng báo **Permission denied** khi mở file, hãy nghĩ tới **filesystem/UID của JVM**, chứ không chỉ tài khoản shell chạy jcmd.

Nếu jcmd trả về thông báo thành công nhưng thao tác lấy file ra thất bại, vấn đề có thể ở **bước export/copy**, không nhất thiết ở giai đoạn JVM ghi. Phân biệt các giai đoạn giúp không lặp lại một heap dump tốn kém chỉ vì bước sao chép bị lỗi.

## 12. Xác minh file sau ghi và ngân sách ở nơi nhận

Một chuỗi kiểm chứng có thể gồm:

1. **Xác định command đã chạy xong thành công** và thu lại stdout/stderr, thời điểm bắt đầu/kết thúc, PID JVM, tên recording nếu là JFR.
2. **Xem tệp trong chính filesystem JVM**: đường dẫn đầy đủ, file có tồn tại, kích thước, owner/group, modified time. Kiểm tra nếu hệ thống yêu cầu việc ghi file kết thúc mới được thu hồi.
3. **Kiểm tra filesystem sau ghi**: dung lượng remaining thực tế, error của volume, Pod/node event liên quan đến storage pressure. Việc tạo dump lớn có thể tác động đến những process khác.
4. **Sao chép về nơi nhận** bằng cơ chế phù hợp; nơi nhận cũng cần đủ dung lượng. Trên network copy, chú ý timeout và tránh tên file trùng.
5. **Xác minh toàn vẹn**: so kích thước trước/sau hoặc checksum, sau đó mở được bằng công cụ đọc JFR/HPROF tương thích. Với file đang tăng trưởng, chưa nên chốt checksum.
6. **Quản trị vòng đời**: gắn incident ID, JVM version, thời điểm, quyền truy cập; di chuyển sang storage được kiểm soát hoặc xóa theo quy trình sau khi hết nhu cầu.

Ví dụ (đường dẫn minh họa, lệnh chỉ đọc):

~~~bash
ls -lh /diagnostics/jfr/orders-incident-001.jfr
wc -c /diagnostics/jfr/orders-incident-001.jfr
sha256sum /diagnostics/jfr/orders-incident-001.jfr
df -h /diagnostics/jfr
~~~

Các lệnh chạy **ở nơi có file thật**. **sha256sum** có thể không có trong image; checksum hai phía chỉ so sánh được khi đã xác nhận file không còn ghi và cùng bytes. Với JFR:

~~~bash
jfr summary /diagnostics/jfr/orders-incident-001.jfr
~~~

**jfr summary** cần JDK tool và đọc file ở **nơi gọi lệnh**. Nếu đã sao chép file về máy phân tích, dùng đường dẫn ở **máy phân tích**, không dùng path container. Không nhất thiết phải cài công cụ phân tích vào production image.

### 12.1. Tránh giữ lại file nhạy cảm không kiểm soát

Heap dump và recording có thể lộ dữ liệu nghiệp vụ hoặc tên đường dẫn/hạ tầng. Dùng permissions hẹp, vùng lưu trữ được kiểm soát và quy trình xóa theo chính sách. Nếu chia sẻ file cho người phân tích, kiểm tra phạm vi truy cập, thời hạn, mã hóa khi truyền/lưu và dấu vết sự cố. Không gửi heap dump lên kênh công khai chỉ để kiểm tra nó có tạo được không.

## 13. Quy trình quyết định ngắn gọn trước khi bấm Enter

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Tôi định lấy **stdout text**, **JFR** hay **heap dump**? | Tên diagnostic command và loại file rõ ràng. |
| File được mở bởi **shell jcmd** hay **JVM đích**? | Dấu **>** ở shell so với **filename=/...** hoặc tham số filename trong command. |
| Tôi biết chính xác **JVM/PID** chưa? | PID theo namespace công cụ, VM.version, container/Pod identity và đúng target. |
| Đường dẫn có phải tuyệt đối trong **filesystem JVM** không? | Cấu hình path cụ thể, mount điểm từ đúng container/Pod, parent directory tồn tại. |
| **JVM UID/GID** có quyền ghi không? | Owner/mode/ACL/mount chính xác; kiểm tra theo danh tính JVM. |
| **df -h** đang đo đúng filesystem không? | df của **directory đích**, không chỉ df /. |
| Có đủ **inode và quota/ephemeral limit** không? | df -i, volume/Pod/namespace/node budget, read-only và tmpfs đã xét. |
| Đã ước lượng **dump + reserve + tệp tạm** chưa? | Ngân sách F/D/R/T/Q và giới hạn của từng filesystem. |
| File sau đó sẽ được **thu hồi bằng cách nào**? | Bind mount/PVC/copy/export có đủ chỗ ở phía nhận. |
| Có làm gián đoạn hệ thống không? | Impact của command, đặc biệt GC.heap_dump, được đánh giá. |
| Sau khi ghi, ai xác minh **file hợp lệ**? | Đường dẫn, kích thước, checksum/reader, thời điểm hoàn tất. |

## 14. Bài tập tình huống có lời giải

**Tình huống A — Nhầm đường dẫn host với container.** Host có **/srv/diag/orders** và Docker bind mount nó vào **/diagnostics**. Người vận hành chạy **jcmd 12345 GC.heap_dump /srv/diag/orders/heap.hprof** từ host. Vì sao có thể lỗi?

**Giải:** Đối số **GC.heap_dump** được JVM mở; JVM trong container có thể **chỉ biết /diagnostics**, không có **/srv/diag/orders**. Nếu đã xác minh mount và quyền, đường dẫn đúng cho JVM là **/diagnostics/heap.hprof**. Sau đó trên host có thể thấy file ở **/srv/diag/orders/heap.hprof**. Không dùng tên đường dẫn host làm argument cho JVM khi nó không tồn tại trong mount namespace.

**Tình huống B — df root còn 50 GiB, nhưng dump bị đầy.** JVM ghi file vào **/diagnostics**, trong khi **df -h /** báo 50 GiB free. Dữ liệu thêm cần xem?

**Giải:** Kiểm tra **df -h /diagnostics**, **df -i /diagnostics**, quota của volume, writable layer, Kubernetes **ephemeral-storage/sizeLimit** nếu liên quan, tệp ghi đồng thời và repository JFR nếu dùng. **/** và **/diagnostics** có thể là hai filesystems khác nhau.

**Tình huống C — Bật JFR.start rồi không thấy file ngay.** Người vận hành dùng **duration=60s filename=/diagnostics/a.jfr** và kiểm tra sau 2 giây.

**Giải:** JFR.start cấu hình recording; với duration, file thường xuất khi recording kết thúc. Xem **JFR.check** và kiểm tra sau thời gian dự kiến. Nếu cần snapshot từ recording đang chạy, dùng **JFR.dump** với tên recording và filename riêng, nhưng nhớ recording vẫn tiếp tục.

**Tình huống D — Java chạy UID 10001, shell debug là root.** Root **test -w /diagnostics/heap** trả true; JVM vẫn lỗi **Permission denied**.

**Giải:** Quyền của root shell không chứng minh JVM có thể ghi. Phải kiểm tra quyền directory/mount theo **effective UID/GID và nhóm của JVM**, ACL/SELinux/securityContext; chọn volume hoặc quyền đúng theo quy trình vận hành.

**Tình huống E — emptyDir memory còn "chỗ" nhưng JVM bị OOM.** Heap dump được ghi vào **emptyDir medium: Memory**.

**Giải:** emptyDir memory là **tmpfs**, dùng RAM và bị tính vào memory budget; df block free không chứng minh đủ RAM. Nên chọn disk-backed volume đủ dung lượng và policy khi cần file lớn.

**Tình huống F — jcmd Thread.print tạo file ở host nhưng JFR.dump không có file ở host.** Cùng người dùng chạy lệnh từ host Linux.

**Giải:** **Thread.print > file** có dấu chuyển hướng do shell xử lý **phía host**. **JFR.dump filename=file** yêu cầu JVM ghi **phía target**, nên file có thể nằm trong container/volume theo working directory hoặc absolute target path.

**Tình huống G — Tệp đã sao chép nhưng không mở được.** Lệnh JVM tạo file và quá trình copy bắt đầu trước khi recording thực sự kết thúc.

**Giải:** Xác minh trạng thái kết thúc và kích thước ổn định, sao chép lại từ file hoàn chỉnh, đối chiếu checksum/size và dùng công cụ đọc đúng định dạng. Không vội khởi động heap dump mới khi chỉ có lỗi copy.

## 15. Những sai lầm cần tránh

1. **“Chạy jcmd ở thư mục nào thì heap dump nằm ở đó.”** Sai với file do JVM đích tạo.
2. **“Đường dẫn tuyệt đối trên host cũng là tuyệt đối trong container.”** Sai nếu không được mount tương ứng.
3. **“JFR.start trả thành công nghĩa là file .jfr đã xuất ngay.”** Còn phụ thuộc thời gian và cơ chế dừng/ghi.
4. **“df -h / báo 100 GiB nên /diagnostics cũng đủ 100 GiB.”** Có thể khác filesystem.
5. **“Root trong debug container ghi được thì JVM user ghi được.”** UID/GID và quyền mount khác nhau.
6. **“Chỉ cần kiểm tra df trước lệnh.”** Còn quota, inode, read-only, tmpfs, storage pressure, tăng trưởng đồng thời.
7. **“Heap dump chắc chắn có kích thước nhỏ hơn -Xmx.”** Không có bảo đảm chung như vậy với mọi nội dung/định dạng; dự toán phải kiểm chứng.
8. **“Bật -gz=1 là sẽ đủ chỗ.”** Tỷ lệ nén thay đổi và xử lý nén vẫn có chi phí.
9. **“Có file là đã có dump hợp lệ.”** Có thể incomplete/truncated hoặc đã copy trước khi ghi xong.
10. **“Kubernetes emptyDir là nơi lưu qua mọi lần Pod restart/replacement.”** EmptyDir gắn vòng đời Pod, không phải storage bền vững.
11. **“/tmp luôn là disk.”** Có thể là tmpfs hoặc writable layer nhỏ; cần kiểm tra.
12. **“Không đọc thấy file bằng kubectl cp nghĩa là JVM không ghi file.”** Có thể container thiếu tar, sai container, sai mount hoặc lỗi copy.
13. **“File nhạy cảm để trong volume chẩn đoán thì ai cũng có thể đọc.”** Phải giới hạn quyền truy cập và quản lý vòng đời.
14. **“Dump thất bại nên cứ chạy lại.”** Nếu nguyên nhân là hết chỗ/thiếu quyền, lặp heap dump chỉ tăng rủi ro và tải.

## Nguồn tham khảo kỹ thuật

- [JDK 21 — jcmd: JFR.start, JFR.dump, GC.heap_dump, impact và filename](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — java launcher: HeapDumpOnOutOfMemoryError và HeapDumpPath](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 — FileStore.getUsableSpace(): số liệu khả dụng chỉ mang tính gợi ý](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileStore.html#getUsableSpace())
- [GNU Coreutils — df: filesystem chứa đường dẫn và inode](https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html)
- [Docker — Bind mounts và mối quan hệ host/container path](https://docs.docker.com/engine/storage/bind-mounts/)
- [Docker — docker cp](https://docs.docker.com/reference/cli/docker/container/cp/)
- [Kubernetes — Local ephemeral storage, emptyDir và giới hạn/eviction](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/)
- [Kubernetes — Share volume với emptyDir](https://kubernetes.io/docs/concepts/storage/volumes/#emptydir)
- [Kubernetes — kubectl cp và điều kiện tar](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_cp/)

**Điều kiện để bắt đầu thu thập:** đã xác định **đúng JVM**, **đúng loại command**, **đường dẫn mà JVM thực sự có thể ghi**, **quyền của JVM**, **filesystem + quota + inode + dung lượng dự phòng**, cùng **cách xác minh và thu hồi file**. Sau lệnh, file phải được kiểm tra từ phía JVM rồi mới được coi là bằng chứng chẩn đoán có thể sử dụng.
