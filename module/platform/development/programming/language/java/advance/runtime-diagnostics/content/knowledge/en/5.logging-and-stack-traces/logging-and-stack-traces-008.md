# 5.8 Khám phá tag khả dụng và đổi cấu hình ghi bằng VM.log

**Unified JVM Logging** là cơ chế ghi nhật ký của HotSpot. Khi cần chẩn đoán GC, safepoint, class loading hay hoạt động của runtime Java, ta có thể chọn thông điệp bằng **tag**, **level**, quyết định nơi ghi bằng **output**, và thêm thời gian/PID bằng **decorators**. Với **JDK 21 sử dụng HotSpot**, lệnh **jcmd <PID> VM.log** cho phép kiểm tra và thay đổi cấu hình ghi ngay khi JVM còn chạy, thường không phải restart ứng dụng.

Ba công việc dễ nhầm với nhau:

1. **Khám phá tag và cú pháp hỗ trợ:** dùng **java -Xlog:help** của đúng binary JDK/VM đang khảo sát.
2. **Xem cấu hình được bật trên tiến trình đích:** dùng **jcmd PID VM.log list**.
3. **Đổi cấu hình của một output:** dùng **jcmd PID VM.log output=... what=... decorators=...**, kiểm tra lại rồi **khôi phục** sau khi thu đủ bằng chứng.

Bài này thuộc phần **Nhật ký và stack trace** của chuyên đề **runtime-diagnostics**. Các lệnh thay đổi VM.log áp dụng cho **HotSpot/JDK 21**; Java SE không bắt buộc mọi triển khai JVM phải có jcmd, VM.log hoặc cùng danh mục tag. Các PID, tên file và sample log trong bài là **minh họa**, không phải dữ liệu từ một JVM production cụ thể.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **tag**, **tag set**, **selector**, **level**, **output**, **decorator** và **output options** của Unified Logging.
- Sử dụng **-Xlog:help** để biết tag hỗ trợ, hiểu sự khác nhau giữa danh mục tag và các event đang được xuất.
- Đọc **VM.log list** và xác định output nào đang ghi ra **stdout**, **stderr** hoặc một file cụ thể.
- Phân biệt **gc=info**, **gc*=debug**, **gc+heap=debug**, **all=warning** và các mức trace/debug.
- Cấu hình **VM.log output, what, decorators, output_options**, hiểu ý nghĩa file rotation.
- Đổi cấu hình tại runtime mà vẫn giữ những output có sẵn; không làm mất cảnh báo bằng **VM.log disable**.
- Kiểm tra tác động trên **CPU, disk, latency, container logging**, xử lý trường hợp không có log và phục hồi cấu hình gốc.
- Tạo một chương trình Java 21 chạy được để thử VM.log từ terminal khác trong môi trường cô lập.

## 2. Các khái niệm trong Unified JVM Logging

Mỗi log site trong HotSpot có một **tag set** và **level**. JVM so sánh chúng với bộ **selector** của từng output; nếu phù hợp, dòng log được in tại đích với những **decorators** đã chọn.

| Khái niệm | Ví dụ | Công dụng |
| --- | --- | --- |
| **Tag** | **gc**, **heap**, **class**, **load**, **safepoint**, **os**, **thread** | Mô tả một chủ đề runtime. |
| **Tag set** | **gc**; **gc+heap**; **class+load** | Một thông điệp có thể có nhiều tag. |
| **Selector / what** | **gc=info** hoặc **gc*=debug** | Chọn những tag set và level được ghi. |
| **Level** | **error**, **warning**, **info**, **debug**, **trace** | Chỉ độ chi tiết/nghiêm trọng của thông điệp. |
| **Output** | **stdout**, **stderr**, **file=/diagnostics/gc.log** | Nơi log của **JVM đích** được xuất. |
| **Decorator** | **time**, **uptime**, **pid**, **tid**, **level**, **tags** | Metadata giúp đọc/tương quan log. |
| **Output options** | **filecount=5,filesize=10M** | Cấu hình vòng quay file cho output file. |

Dòng log sau là ví dụ minh họa:

~~~text
[2026-10-29T12:01:02.000+0700][1.314s][info][gc] GC(3) Pause Young ... 6.31ms
~~~

Nó có timestamp, uptime, level, tags và nội dung sự kiện. **Đừng coi phần thông điệp, timestamp và số GC cụ thể là stdout cố định**: chúng thay đổi theo JVM, collector, tải và các decorators được bật.

### 2.1. Mức log là ngưỡng chi tiết

Các mức thông dụng trong HotSpot theo thứ tự tăng độ chi tiết là:

~~~text
off < error < warning < info < debug < trace
~~~

**gc*=debug** cho phép những sự kiện phù hợp có level từ **error** đến **debug**, không chỉ riêng dòng có chữ debug; nó không lấy log ở mức trace. **gc*=trace** rộng hơn và có thể tốn CPU/I/O đáng kể.

Mặc định thường ghi các mức **warning** và **error** của nhiều tag set ra stdout, tương ứng ý tưởng **all=warning**. Tuy nhiên không dựa vào mặc định khi debug một process đang chạy: **VM.log list** mới cho biết cấu hình thực tế, vì startup flags hoặc lệnh runtime trước đó có thể đã đổi.

Đây là log **của HotSpot**, không tự động thay đổi **logger ứng dụng**. Lệnh VM.log không điều chỉnh SLF4J, Logback, Log4j, Spring Boot logging hoặc java.util.logging. Khi lỗi thuộc lớp business/app, dùng công cụ log tương ứng.

### 2.2. Sự khác biệt quan trọng giữa tag và tag set

Giả sử có ba log site:

~~~text
[info][gc] ...
[debug][gc,heap] ...
[debug][gc,ergo] ...
~~~

**gc=info** không có wildcard chỉ khớp tag set chính xác **gc**; nó **không tự chọn** gc+heap hoặc gc+ergo. **gc*=info** có wildcard, chọn các tag set có chứa **gc**, kể cả những tổ hợp rộng hơn. **gc+heap=debug** chọn chính xác cặp gc/heap; nếu site mang thêm tag khác, muốn bao phủ chúng phải cân nhắc **gc+heap*=debug**.

| Selector | Phạm vi chọn | Điều cần nhớ |
| --- | --- | --- |
| **gc=info** | Tag set chỉ có gc, đến level info | Phạm vi hẹp. |
| **gc*=info** | Mọi tag set chứa gc, đến info | Bao phủ các tổ hợp gc+... |
| **gc*=debug** | Mọi tag set chứa gc, đến debug | Chi tiết hơn, log có thể lớn. |
| **gc+heap=debug** | Chính xác tag set gc+heap, đến debug | Không tự bao phủ tag set có tag thứ ba. |
| **safepoint=info** | Tag set safepoint đến info | Có thể cần selector khác cho dữ liệu sâu hơn. |
| **class+load=info** | Tag set class+load đến info | Chỉ thấy sự kiện từ thời điểm bật trở đi. |
| **all=warning** | Mọi tag set, đến warning | Thường là baseline, nhưng phải xem list. |
| **all=off** | Tắt lựa chọn log trên output được cấu hình | Không dùng tùy tiện trên stdout cần cảnh báo. |
| **gc*=info,safepoint=info** | Hai selector trong một chuỗi what | Dấu phẩy phân tách các selector. |

Nếu không có dòng log sau khi bật, chưa thể kết luận tag đó không tồn tại: có thể sự kiện chưa xảy ra trong cửa sổ quan sát, selector quá hẹp, level không đủ, hoặc output không được ghi/thu gom đúng.

## 3. Khám phá tag có sẵn bằng -Xlog:help

Trên một bản **HotSpot JDK 21**:

~~~bash
java -Xlog:help
~~~

Lệnh này in hướng dẫn **-Xlog**, gồm level, các tag hỗ trợ, decorators, output options và ví dụ. Nó không yêu cầu attach vào một ứng dụng đang chạy và thường kết thúc sau khi in trợ giúp.

Câu hỏi quan trọng là **java nào đang được dùng?**

~~~bash
java -version
jcmd 12345 VM.version
jcmd 12345 VM.command_line
~~~

**12345 chỉ là PID minh họa.** Lệnh đầu hỏi JDK của shell, hai lệnh sau hỏi **JVM đích** nếu attach thành công. Một host có thể cài nhiều JDK; Docker image có thể chứa JDK khác host; Java 21 của vendor khác có thể dùng VM không phải HotSpot. Vì vậy:

- Dùng **-Xlog:help** trên **binary tương ứng với JVM target** để biết tập tag phù hợp.
- Ghi **full Java version, VM name/vendor, GC đang sử dụng** và môi trường JDK/runtime.
- Đừng sao chép tag từ một blog cho JDK 8, 17 hoặc 24 rồi khẳng định nó chắc chắn khả dụng và có log site trên JDK 21 đích.
- Khi dùng **runtime image tạo bằng jlink** hoặc distroless, có thể không có **jcmd** bên trong image. Đây là vấn đề bộ công cụ, không tự chứng minh JVM thiếu mọi tag.

### 3.1. Phân biệt ba dạng truy vấn

| Lệnh | Trả lời | Không trả lời |
| --- | --- | --- |
| **java -Xlog:help** | Binary Java đang gọi hỗ trợ cú pháp/tag gì? | Tiến trình ứng dụng đích đang bật output nào? |
| **jcmd PID help VM.log** | Diagnostic command VM.log trên process có tùy chọn gì? | Danh sách đầy đủ mọi tag hoặc có bao nhiêu event đã xảy ra? |
| **jcmd PID VM.log list** | Các output/selector/decorators đang hoạt động là gì? | Tất cả tag có thể phát ở version này? |

Đừng gọi **VM.log list** rồi dựa vào những selector có mặt để suy ra đầy đủ danh sách tag. Nếu list chỉ hiện **all=warning**, điều đó không có nghĩa JVM không có **gc** hay **safepoint**.

## 4. Trước khi đổi cấu hình: xác minh đúng JVM và quyền

Một chuỗi đọc ít xâm lấn:

~~~bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 help VM.log
jcmd 12345 VM.log list
~~~

Trên Linux/container, **jcmd -l** có thể không liệt kê được tiến trình vì khác PID namespace hoặc chính sách attach. Hãy dùng PID chính xác theo **môi trường nơi jcmd chạy** và nhận diện JVM bằng process manager, Docker/Kubernetes nếu cần. PID 1 bên trong container không mặc nhiên là JVM nếu có **tini**, shell wrapper hoặc shareProcessNamespace.

**VM.log được tài liệu JDK 21 đánh giá Impact: Low** đối với thao tác diagnostic command. Nhưng bật lượng log trace lớn có thể tốn chi phí đáng kể trong nhiều phút; đó là **tác động riêng của dữ liệu tiếp tục được phát**, không mâu thuẫn với mức impact của lệnh cấu hình.

Nếu **jcmd PID help** không liệt kê **VM.log**, đừng gửi command mù quáng. Xác minh VM implementation, JDK, PID, quyền và khả năng attach. Jcmd là công cụ cho JVM có hỗ trợ diagnostic command; Java SE 21 không cam kết JVM nào cũng có cùng giao diện.

### 4.1. Hiểu đầu ra VM.log list

Đây là ví dụ **được giản lược để giải thích**, không bảo đảm khớp chính xác output của JVM thật:

~~~text
Log output configuration:
 #0: stdout all=warning uptime,level,tags
 #1: stderr all=off uptime,level,tags
 #2: file=/diagnostics/gc.log gc*=debug time,uptime,level,tags filecount=5,filesize=10240K
~~~

- **#0 / #1 / #2** là ID của các output **trong process hiện tại**. Không giả định #2 luôn là gc.log.
- **stdout, stderr** là luồng standard output/error của **JVM target**, không phải terminal đang gõ jcmd.
- **file=/diagnostics/gc.log** là đường dẫn được **JVM đích** mở theo filesystem của nó.
- **all=warning, gc*=debug** là các selector cấu hình cho output.
- **time, uptime, level, tags** là các decorators.
- **filecount/filesize** là tùy chọn file output, khi được áp dụng.

**Lưu lại toàn bộ VM.log list trước thay đổi**, không chỉ nhớ một dòng. Đó là bằng chứng để khôi phục nguyên trạng, đặc biệt nếu hệ thống đã có nhiều output khác nhau.

## 5. Các tham số VM.log được JDK 21 công bố

Tài liệu jcmd mô tả:

~~~text
jcmd PID VM.log [output=...] [output_options=...]
                [what=...] [decorators=...]
                [list] [rotate] [disable]
~~~

Đây là mẫu nhiều dòng để đọc, **không phải lệnh shell nhiều dòng có thể copy nguyên**. Các option có tên đều dùng cú pháp **key** hoặc **key=value**, phải tuân theo help của JVM đích.

| Tên | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **output** | Chọn tên hoặc chỉ số #N của output để cấu hình | stdout, stderr, file=/diagnostics/log.txt, #2 |
| **what** | Chọn tag set/level | gc*=debug, safepoint=info |
| **decorators** | Metadata ở đầu dòng; none để không dùng decorators | uptime,pid,level,tags |
| **output_options** | Tùy chọn file, thường thiết lập khi tạo output mới | filecount=5,filesize=10M |
| **list** | Liệt kê cấu hình output hiện tại | VM.log list |
| **rotate** | Yêu cầu rotate các log file theo chính sách | VM.log rotate |
| **disable** | Tắt toàn bộ Unified Logging, xóa cấu hình | VM.log disable |

**Phân biệt hai thao tác tắt:**

- **what=all=off** áp lên **một output đã chỉ định** cho phép tắt selector của output đó, sau đó xác minh bằng list.
- **VM.log disable** là thao tác **toàn cục**, có thể tắt cả warning/error đang được các output khác thu thập. Nó không phải nút hoàn tác một phiên debug nhỏ.

**output_options** cho output đã tồn tại có thể không thay đổi được trực tiếp như what/decorators. Đặt chính sách rotation khi **tạo output mới**; nếu cần thay rotation của output đang dùng, hãy thiết kế thay đổi riêng và kiểm tra trên JDK thực tế, không coi cấu hình file là cập nhật tùy ý.

## 6. Thực hành thay đổi log cho một output file mới

Giả sử đã xác minh PID của JVM HotSpot JDK 21 là **12345**, container/host có thư mục **/diagnostics** mà JVM thực sự được quyền ghi, và có đủ disk/quota. Bạn đã lưu kết quả **VM.log list** trước khi thay đổi.

Bật thêm log GC ở mức debug:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/gc-investigation.log' \
  what='gc*=debug' \
  decorators='time,uptime,pid,level,tags' \
  output_options='filecount=5,filesize=10M'
~~~

**Giải thích:**

- **output=file=...**: tạo hoặc cấu hình file output trên **JVM target**.
- **what=gc*=debug**: chọn mọi tag set có **gc**, đến mức **debug**.
- **decorators**: gắn timestamp, uptime, PID, level, tag set.
- **output_options**: xoay file theo ngưỡng kích thước xấp xỉ và số lượng file.

Ví dụ trên dùng dấu nháy theo **Bash**. Nếu dùng Windows PowerShell/cmd, cơ chế quote khác; cần chuyển đúng các đối số, đặc biệt **\***, dấu phẩy và dấu #. Đừng chạy command trên production khi chưa xác định tác động, dung lượng và đường thu hồi.

Ngay sau đó:

~~~bash
jcmd 12345 VM.log list
~~~

Tìm **đúng tên output** và xác minh selector/decorators/rotation. Nếu không thấy, xem stderr/exit status, quyền attach, tag hợp lệ, đường dẫn file ở góc nhìn JVM, filesystem read-only hoặc hết không gian. **Không coi command đã gửi là bằng chứng log đã được bật**.

### 6.1. Cẩn thận khi thay đổi stdout

Ví dụ sau chỉnh **output đang tồn tại**:

~~~bash
jcmd 12345 VM.log output=stdout what='gc=info' decorators='uptime,level,tags'
~~~

Nếu stdout trước đó đang có **all=warning** hoặc những selector khác, thay như vậy có thể làm thay đổi tập log cảnh báo quan trọng. Khi cần giữ cảnh báo, bạn có thể gộp selector đã biết, ví dụ **nếu baseline chỉ là all=warning**:

~~~bash
jcmd 12345 VM.log output=stdout what='all=warning,gc=info'
~~~

**Chỉ dùng khi đã đọc baseline thực tế.** Nếu stdout trước phiên điều tra có nhiều selector hơn, ví dụ class+load=info, việc thay bằng hai selector trên chưa phải khôi phục. Phương án ít ảnh hưởng thường là **tạo file output điều tra riêng** và chạm vào stdout ít nhất có thể.

**JVM stdout khác stdout của jcmd.** Trên Docker/Kubernetes, stdout của Java có thể được runtime collector thu vào **docker logs** hoặc **kubectl logs**; terminal gọi jcmd chỉ nhận phản hồi của diagnostic command. Muốn log JVM hiện trong terminal hiện tại, đừng nhầm lệnh VM.log output=stdout với shell redirection.

### 6.2. Thay selector trên output đã có bằng ID

Giả sử lệnh **VM.log list ngay trước đó** xác nhận:

~~~text
#2: file=/diagnostics/gc-investigation.log gc*=debug ...
~~~

Nếu thật sự cần tăng mức log trong thời gian rất ngắn:

~~~bash
jcmd 12345 VM.log output='#2' what='gc*=trace'
jcmd 12345 VM.log list
~~~

**#2 là ví dụ**, phải xác minh ID hiện tại. Tăng lên trace có thể tạo lượng log lớn và overhead; hãy có hạn mức, người phụ trách thời điểm tắt và kế hoạch rollback. Không copy cứng #2 từ một JVM khác hoặc từ process trước khi restart.

## 7. Decorators và cách đọc thời gian

Decorators giúp log dùng được cho điều tra tương quan:

| Decorator | Diễn giải | Khi nào hữu ích |
| --- | --- | --- |
| **time** | Timestamp wall-clock của thông điệp | So với thời điểm incident, application logs và hệ monitoring. |
| **uptime** | Thời gian từ lúc JVM startup | Phân biệt startup/warmup và thời gian sự kiện. |
| **pid** | PID ở góc nhìn JVM | Phân biệt nhiều process/instance ghi chung storage. |
| **tid** | ID thread ở cấp VM/native | Điều tra một nhóm thread; không đồng nhất với Java thread ID. |
| **level** | Mức thông điệp | Phân biệt info/debug/trace khi phân tích. |
| **tags** | Tag set của thông điệp | Biết vì sao selector cho phép log. |
| **none** | Bỏ decorations | Giảm metadata nhưng mất bối cảnh; cân nhắc. |

Cấu hình có thể là:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/safepoint.log' \
  what='safepoint=info' \
  decorators='time,uptime,pid,tid,level,tags' \
  output_options='filecount=3,filesize=10M'
~~~

Nếu latency spike xuất hiện ở 12:05 và có dòng safepoint gần thời điểm đó, **sự trùng thời gian là gợi ý** chứ chưa đủ chứng minh safepoint là nguyên nhân duy nhất. Đối chiếu request traces, GC events, CPU/throttling, load và đồng bộ clock.

**Decorator pid trong container** có thể là PID theo PID namespace của JVM, khác số PID ở node Linux. Khi liên kết event giữa node exporter và Java, dùng thêm **container/Pod identity, host, JVM start timestamp** thay vì chỉ PID.

## 8. File output và rotation

Các file log tăng nhanh nếu bật nhiều tag mức debug/trace. **filesize=10M,filecount=5** giới hạn lượng log giữ theo chính sách rotation của HotSpot; đây là **ngưỡng mục tiêu**, kích thước thực có thể chênh lệch do cách ghi/rotate. Tài liệu **java JDK 21** mô tả rotation mặc định của file output với **tối đa 5 file xoay**, target khoảng **20 MB**, trừ khi cấu hình khác. **filecount=0** tắt rotation, có thể làm file tăng cho tới khi hết filesystem/quota.

Ví dụ:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/class-load.log' \
  what='class+load=info' \
  decorators='time,uptime,level,tags' \
  output_options='filecount=4,filesize=10M'
~~~

Tài liệu **-Xlog** hỗ trợ placeholder **%p** (PID JVM) và **%t** (mốc thời gian startup) trong tên file, hữu ích để tránh trùng tên. Nhưng một PID có thể được tái sử dụng, vì thế khi cần định danh ổn định hãy kết hợp service/instance/incident.

**Tắt rotate bằng filecount=0** chỉ khi có chiến lược kiểm soát dung lượng khác và nhu cầu thu hồi đặc biệt. Không tạo tệp **all=trace** vô hạn trên root filesystem của container.

### 8.1. Đường dẫn file luôn phụ thuộc ngữ cảnh JVM đích

Khi bạn chạy trên host:

~~~bash
jcmd 12345 VM.log output='file=/diagnostics/gc.log' what='gc*=info'
~~~

file **/diagnostics/gc.log** được **JVM đích** mở. Nếu JVM đang chạy trong Docker, đường dẫn này được hiểu trong **mount namespace/file system của container**, không tự động trùng host. Nếu container mount **/srv/diag/host** vào **/diagnostics**, host có thể thấy cùng file dưới tên khác, nhưng phải đọc metadata mount để khẳng định.

Preflight từ môi trường JVM khi có các công cụ:

~~~bash
id
ls -ld /diagnostics
df -h /diagnostics
df -i /diagnostics
~~~

Kiểm tra **UID/GID của chính JVM**, không chỉ của shell debug đang chạy root. Cần xét filesystem read-only, volume quota, disk free, inode, log collector và nơi thu hồi. Khi image distroless không có **sh/df**, dùng công cụ debug/node được phép thay vì suy ra file path từ host.

### 8.2. Docker và Kubernetes có ba ranh giới cần chú ý

1. **Namespace PID:** PID của JVM trong container có thể khác PID của Java process nhìn từ host. Dùng PID theo môi trường mà tiện ích jcmd đang attach.
2. **Mount namespace:** **file=/diagnostics/gc.log** thuộc namespace của JVM. **kubectl exec** vào sidecar không chứng minh sidecar có cùng mount path; mỗi container cần mount được khai báo.
3. **Logging pipeline:** **output=stdout** của JVM được runtime/container log collector nhận nếu được nối đúng. Nó không tự ghi file trên máy người dùng chạy **kubectl** hoặc Docker CLI.

Với **Kubernetes**, volume **emptyDir** có vòng đời theo Pod và chịu các giới hạn ephemeral-storage; **emptyDir medium: Memory** là tmpfs dùng bộ nhớ. Một **PVC** có thể phù hợp khi cần giữ log qua thay thế Pod, nhưng vẫn phải kiểm tra quyền, quota, throughput và bảo mật. File logging trên rootfs container có thể mất khi container được thay thế.

Ví dụ lệnh chỉ để quan sát (đổi tên Pod và namespace cho đúng):

~~~bash
kubectl get pod java-app-0 -o wide
kubectl exec java-app-0 -c app -- id
kubectl exec java-app-0 -c app -- df -h /diagnostics
kubectl logs java-app-0 -c app --since=10m
~~~

**kubectl logs** đọc stream runtime đang thu gom, thường tương ứng stdout/stderr; không có nghĩa tự động đọc mọi file log trong **/diagnostics**. Nếu muốn sao chép file, dùng volume hoặc cơ chế **kubectl cp** khi có tar và quyền phù hợp.

### 8.3. VM.log rotate

~~~bash
jcmd 12345 VM.log rotate
~~~

Lệnh này yêu cầu HotSpot rotate **các log file output** theo cơ chế đang được cấu hình; nó không phải lệnh xóa mọi log cũ hay giải phóng dung lượng không giới hạn. Kiểm tra **VM.log list** và nhu cầu lưu chứng cứ trước khi chạy. Nếu filesystem đầy, nên khắc phục nguồn tiêu thụ, quota và cấu hình logging thay vì rotate lặp liên tục.

## 9. Hoàn tác thay đổi khi hết thời gian thu

**Khôi phục trước hết cần biết trạng thái trước thay đổi.** VM.log không giữ lịch sử tự động để bạn bấm "undo". Khi phiên điều tra kết thúc, làm theo thứ tự:

1. Xác nhận tên/ID output đã thêm bằng **jcmd PID VM.log list**.
2. Nếu đó là output **chỉ dùng cho incident**, đổi selector của riêng output thành **all=off**.
3. Nếu bạn đã sửa stdout/stderr/file output có sẵn, khôi phục **chính xác what và decorators trong snapshot trước phiên**, không chỉ tắt mọi log.
4. Đọc **VM.log list** lần nữa để xác nhận và lưu kết quả sau rollback.
5. Thu hồi file và kiểm tra toàn vẹn, rồi xử lý giữ/xóa theo chính sách.

Giả sử **#2 vừa được xác minh là file debug riêng**:

~~~bash
jcmd 12345 VM.log output='#2' what='all=off'
jcmd 12345 VM.log list
~~~

Lệnh này tắt lựa chọn log cho output #2, không tự xóa file đã ghi. **Không dùng số #2 nếu chưa xác minh nó đúng output mục tiêu tại thời điểm đó.**

Tránh dùng lệnh sau như cách tắt một phiên debug:

~~~bash
jcmd 12345 VM.log disable
~~~

Vì **disable** tắt **toàn bộ Unified Logging** và xóa cấu hình hiện có, có thể chặn các dòng warning/error mà hệ thống cần cho vận hành. Chỉ sử dụng nó khi thực sự có mục tiêu quản lý mọi output và đã có kế hoạch phục hồi.

Nếu snapshot stdout cũ là:

~~~text
#0: stdout all=warning uptime,level,tags
~~~

và người vận hành đã sửa stdout, một cách khôi phục tương ứng là:

~~~bash
jcmd 12345 VM.log output=stdout \
  what='all=warning' decorators='uptime,level,tags'
jcmd 12345 VM.log list
~~~

**Ví dụ này chỉ đúng cho baseline trên.** Nếu config thật còn nhiều selector, thay đổi cũ cần được khôi phục đầy đủ theo snapshot.

## 10. Phân biệt cấu hình startup -Xlog và runtime VM.log

| Cơ chế | Tình huống | Ranh giới |
| --- | --- | --- |
| **java -Xlog:help** | Hỏi binary Java về tags/levels/outputs | Không inspect JVM đã chạy. |
| **-Xlog:...** khi khởi động | Ghi cả class/GC/safepoint event từ đầu phiên | Muốn đổi startup cần thay triển khai/restart. |
| **jcmd PID VM.log list** | Xem output của tiến trình hiện tại | Không kể lại log đã xảy ra. |
| **jcmd PID VM.log output=...** | Bật/tăng giảm log khi ứng dụng đang chạy | Không tạo lại những event trước thời điểm bật. |
| **-Xlog qua config deploy** | Giữ selector qua restart | Cần quản lý file/rotation/quyền khi triển khai. |

Ví dụ cấu hình từ startup:

~~~bash
java '-Xlog:gc*=info:file=/diagnostics/gc-start.log:time,uptime,level,tags:filecount=5,filesize=10M' \
  -jar application.jar
~~~

**application.jar** là ví dụ tên JAR. Khi cần khảo sát **startup**, bật log từ lúc khởi động có thể ghi được event xảy ra trước khi có thể gửi jcmd. Nếu service đang nóng và muốn quan sát tạm, VM.log phù hợp để tăng độ chi tiết có thời hạn.

**Thay đổi runtime không tự tồn tại qua JVM restart.** Nếu file còn trên volume sau deploy, không chứng minh JVM mới đang dùng cùng selector. Phải chạy **VM.log list** trên process mới.

## 11. Bài thực hành Java 21 chạy được

Ứng dụng nhỏ dưới đây in PID rồi duy trì công việc trong khoảng một phút để có thời gian thử VM.log từ terminal khác. Nó tạo allocation nhỏ, nhưng **không bảo đảm tất cả loại log GC sẽ xuất hiện**, vì việc GC thực sự diễn ra phụ thuộc collector, heap, điều kiện runtime và tối ưu compiler.

**Tệp LogProbe.java**

~~~java
public final class LogProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY pid="
                + ProcessHandle.current().pid());

        byte[][] recent = new byte[8][];
        for (int i = 0; i < 300; i++) {
            byte[] payload = new byte[128 * 1024];
            payload[0] = (byte) i;
            recent[i % recent.length] = payload;

            if (i % 100 == 0) {
                System.out.println("PHASE " + i);
            }
            Thread.sleep(200);
        }
        System.out.println("DONE");
    }
}
~~~

Biên dịch/chạy với JDK 21:

~~~bash
javac --release 21 LogProbe.java
java -Xms32m -Xmx32m LogProbe
~~~

**Stdout của chương trình khi hoàn tất bình thường:** dòng đầu là **READY pid=<PID thực>**, tiếp đến lần lượt **PHASE 0**, **PHASE 100**, **PHASE 200**, cuối cùng **DONE**. Con số PID không cố định, thời gian thực thi có dao động do hệ thống; **không in một giá trị PID giả thành expected output**.

Từ terminal khác, giả sử chương trình in PID **24680**, thay số bằng PID thật:

~~~bash
jcmd 24680 VM.version
jcmd 24680 help VM.log
jcmd 24680 VM.log list
~~~

Nếu muốn thử một file output trong máy local đã bảo đảm quyền và dung lượng:

~~~bash
jcmd 24680 VM.log \
  output='file=/tmp/log-probe-gc.log' \
  what='gc*=debug' \
  decorators='uptime,level,tags' \
  output_options='filecount=2,filesize=5M'
jcmd 24680 VM.log list
~~~

**/tmp** chỉ là vị trí thử local. Trong container, /tmp có thể là volume nhỏ, tmpfs hoặc writable layer, cần kiểm tra riêng; không mang đường dẫn này sang production máy móc.

Nếu chương trình kết thúc trước khi thao tác, phải chạy **một JVM mới và lấy PID mới**. Không chạy jcmd bằng PID cũ vì hệ điều hành có thể tái sử dụng PID. Khi đã bật thành công, hãy quan sát file và kiểm tra số event, rồi tắt đúng output theo hướng dẫn phần 9 trước khi kết thúc phiên dài.

## 12. Lựa chọn tag cho một số tình huống chẩn đoán

| Vấn đề | Selector mở đầu khả dĩ | Cách đọc kết quả |
| --- | --- | --- |
| GC bất thường, cần tổng quan | **gc=info** hoặc **gc*=info** | Kết hợp heap occupancy, allocation, pause metrics. |
| Cần chi tiết GC/heap | **gc*=debug** hoặc **gc+heap=debug** | Hiểu ngưỡng level, tag set, collector và overhead. |
| Suspected safepoint latency | **safepoint=info** | Đối chiếu request timestamp, CPU, thread states. |
| Class load sau deploy | **class+load=info** | Chỉ thấy sự kiện từ khi bật trở đi, không có toàn bộ lịch sử. |
| Native thread activity | Selector như **os+thread=info** nếu runtime hỗ trợ | Phân biệt native TID với Java thread ID. |
| JIT compilation | Tìm tag phù hợp trong **-Xlog:help** của target | Đối chiếu JFR/compiler activity, không bịa tên tag. |

**Không có một selector vạn năng.** Chọn log đủ để kiểm tra giả thuyết, tăng mức từ info lên debug/trace khi cần và theo dõi tốc độ ghi. **all=trace** thường quá rộng cho production trừ tình huống được kiểm soát.

Để phân biệt **không có event** với **không lấy được event**, luôn ghi: lúc bắt đầu logging, selector thực tế từ list, thời lượng, workload, collector, file output và tình trạng mất log.

## 13. Tác động của chính việc quan sát

Tăng logging có thể làm tăng:

- Chi phí CPU để xử lý thông điệp, định dạng metadata và ghi file.
- Disk I/O, độ trễ khi storage/remote volume nghẽn, áp lực với log collector.
- Dung lượng filesystem/ephemeral-storage, nguy cơ file bị rotation ghi đè trước khi được thu hồi.
- CPU/lock contention, jitter trong p95/p99 latency khi khối lượng log lớn.
- Khả năng lộ thông tin cấu hình VM, đường dẫn, tên lớp/module hoặc dữ liệu nhạy cảm tùy sự kiện.

**Không xem VM.log là phép quan sát vô hình**. Ghi thời điểm bật/tắt, lấy baseline, đối chiếu các metric cùng một cửa sổ và xem sự khác biệt của workload. Một lần p99 tăng sau khi bật trace có thể là hệ quả của cả sự cố lẫn logging overhead.

**-Xlog:async** là chế độ Unified Logging bất đồng bộ được JDK hiện đại hỗ trợ, giảm chờ I/O trực tiếp nhưng dùng buffer/CPU và có thể mất thông điệp khi buffer đầy/crash. Không cho rằng mọi chế độ có thể chuyển đổi động qua VM.log; kiểm tra tài liệu JDK/flags đang chạy trước khi thay cơ chế ghi.

Khi file rotation làm mất các dòng cũ trước lúc thu thập, dữ liệu không còn đại diện toàn bộ incident. Điều chỉnh filecount/filesize theo dự kiến tốc độ ghi, thời lượng quan sát và dung lượng thực tế; sau đó kiểm tra file còn lại.

## 14. Xử lý sự cố khi VM.log không cho kết quả mong muốn

| Triệu chứng | Giả thuyết | Hướng kiểm tra |
| --- | --- | --- |
| **jcmd không có trong image** | Runtime image tối giản/jlink hoặc PATH sai | Xác nhận JDK tools ở container/node, dùng cách debug được hỗ trợ. |
| **Could not attach / process not found** | PID sai namespace, quyền khác, JVM/attach bị hạn chế | Xác nhận PID target, user, JVM vendor, container PID namespace. |
| **Unknown diagnostic command: VM.log** | VM không hỗ trợ command hoặc khác HotSpot | Chạy **jcmd PID help** và **VM.version**. |
| **VM.log list không có debug output** | Chưa bật hoặc lệnh thay đổi thất bại | Đọc exit status, stdout/stderr và list sau thao tác. |
| **Output file không được tạo** | Đường dẫn JVM sai, thiếu quyền, read-only, hết disk/quota | Kiểm tra mount, UID/GID, df -h/-i ở đúng filesystem. |
| **File có nhưng không có log** | Selector quá hẹp, level chưa đủ, event chưa xảy ra | So **gc** với **gc***, thời điểm bật, workload và collector. |
| **Có nhiều log hơn dự kiến** | Wildcard/trace quá rộng, nhiều output | Hẹp selector, giảm level, giới hạn filecount/filesize. |
| **stdout chỉ hiện trong docker logs** | stdout thuộc JVM trong container, được collector thu | Xem Docker/Kubernetes logging pipeline. |
| **Output #2 không phải file muốn đổi** | ID thay đổi/ghi nhớ nhầm | Luôn đọc **VM.log list** ngay trước thao tác. |
| **Sau restart mất mức debug** | Cấu hình runtime không lưu qua restart | Đưa -Xlog vào startup nếu cần lâu dài. |
| **Không đổi được rotation trên output cũ** | output_options áp dụng không linh hoạt cho output đã tạo | Cấu hình output mới với rotation mong muốn. |
| **Thấy latency xấu khi bật trace** | Observer effect và/hoặc sự cố thật | Hạ mức log, đo A/A, đối chiếu timing, CPU/disk. |

Nếu lệnh được mô tả **Impact: Low**, đó chỉ là mức tác động của diagnostic command trên JDK docs; **không** chứng minh log debug/trace không ảnh hưởng tải suốt nhiều phút. Đánh giá hai loại tác động riêng biệt.

## 15. Kịch bản thực tế: tăng GC log trong 5 phút

Giả định p99 của dịch vụ tăng đột ngột và team cần thêm thông tin GC. Có thể thiết kế một phiên thu thập như sau:

**Bước 1 — Xác định đối tượng:** Pod/container/host, JVM PID, version/vendor, loại collector. Không dùng PID phỏng đoán; xác minh bằng **VM.version**.

**Bước 2 — Chụp cấu hình hiện có:** chạy **VM.log list**, lưu output selectors/decorators và những file quan trọng. Khám phá tag bằng **-Xlog:help của đúng binary**.

**Bước 3 — Chọn file và giới hạn:** ví dụ **/diagnostics/incident-gc.log** là mount đã được JVM quyền ghi; kiểm tra disk/quota/inode. Chọn **gc*=debug**, 5 phút, rotation và nơi lấy file. Nếu chỉ cần summary, bắt đầu hẹp hơn.

**Bước 4 — Bật tạm:**

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/incident-gc.log' \
  what='gc*=debug' \
  decorators='time,uptime,pid,level,tags' \
  output_options='filecount=5,filesize=10M'
jcmd 12345 VM.log list
~~~

**Bước 5 — Theo dõi:** xem log sinh ra, CPU/disk/I/O và request latency. Ghi timestamp của lúc bắt đầu/thay đổi; không gán mọi spike cho GC chỉ vì trùng giờ.

**Bước 6 — Khôi phục:** xác định đúng output điều tra mới bằng **list**, đặt **all=off** cho output đó nếu không cần nữa hoặc khôi phục chính xác baseline nếu đã chạm một output cũ. Đọc **list** sau rollback.

**Bước 7 — Lưu chứng cứ:** xác minh file trên filesystem JVM, sao chép, kiểm tra kích thước/checksum khi file ngừng ghi; lưu quyền hạn/retention phù hợp. Không gửi log nhạy cảm công khai.

Đây là một quy trình có kiểm chứng. Không có câu lệnh VM.log nào tự tạo ra bằng chứng về quan hệ nhân quả; phải kết hợp timeline và metrics.

## 16. Tự kiểm tra với đáp án

**1. VM.log list chỉ cho thấy all=warning. Điều đó có nghĩa JVM không hỗ trợ gc?**

Không. Nó là cấu hình **đang bật**, không phải danh sách tag. Dùng **-Xlog:help** trên đúng binary để xem các tag mà VM hỗ trợ.

**2. Vì sao gc=info không hiện [gc,heap]?**

Vì không có wildcard, nó chỉ khớp tag set **gc**. Muốn tất cả tag set chứa gc, dùng **gc*=info** (với lưu ý log nhiều hơn).

**3. Dùng VM.log disable có phải cách tắt file debug an toàn?**

Không. **disable** tắt toàn bộ Unified Logging, không chỉ một output. Tắt selector trên đúng output hoặc khôi phục cấu hình đã lưu.

**4. Vì sao VM.log output=file=/diagnostics/gc.log được gọi trên host nhưng file không có ở host?**

Vì đường dẫn do **JVM đích** mở, có thể nằm trong mount namespace container. Xem volume mapping, quyền JVM và vị trí file từ container.

**5. VM.log list báo đã bật gc*=debug nhưng file vẫn không có dòng GC. Có thể kết luận không có GC?**

Không. Log có thể chưa có sự kiện phù hợp, đã bật quá muộn, output không truy cập được hoặc event/tag/level chưa đúng. Cần kiểm tra thời gian, selector, collector và dữ liệu khác.

**6. Tại sao output=stdout không nhất thiết hiện trong terminal gọi jcmd?**

Vì stdout là luồng của **JVM**, không phải stdout của **tiện ích jcmd**. Container runtime có thể chuyển stdout JVM tới docker logs/kubectl logs.

**7. Đổi tag bằng VM.log có giữ lại sau khi process restart không?**

Thông thường không. Đó là cấu hình runtime; nếu muốn giữ, đưa lựa chọn **-Xlog** vào startup và xác minh trên JVM mới.

**8. Có thể dùng một ID output #2 từ bản deploy trước không?**

Không. ID output thuộc cấu hình hiện tại của từng JVM. Cần **VM.log list** mới để biết tên output và ID.

**9. Tại sao không tăng gc*=trace ngay lập tức trên production?**

Trace có thể tạo lượng log rất lớn, ảnh hưởng CPU/I/O, disk và latency. Chọn mức đủ cho giả thuyết, giới hạn thời gian và có rollback.

**10. -Xlog:help đã liệt kê tag, vậy có bảo đảm sẽ xuất ít nhất một dòng tương ứng trong một phút không?**

Không. Nó cho biết tag được binary nhận biết. Log site và event thực tế còn phụ thuộc workload, VM, cấu hình, level và thời điểm quan sát.

## 17. Các lỗi tư duy nên tránh

1. Nhầm **VM.log list** là danh sách toàn bộ tag được hỗ trợ.
2. Lấy kết quả **-Xlog:help** từ Java trên PATH mà không so JDK vendor/version với target.
3. Tưởng **gc=debug** bao phủ mọi tag set **gc+...**.
4. Tưởng bật logging debug chỉ ghi những event level debug; các level nghiêm trọng hơn cũng được chọn.
5. Thay stdout và đánh mất các selector warning/error ban đầu.
6. Dùng **VM.log disable** để rollback riêng một output.
7. Hardcode ID output từ một process trước hoặc sau restart.
8. Quên file rotation, disk/quota, inode và tốc độ log khi nâng level.
9. Tưởng file được tạo tại cwd của **jcmd** thay vì cwd/filesystem của **JVM target**.
10. Nhầm stdout của JVM với stdout của terminal gọi jcmd.
11. Cho rằng **VM.log** thay đổi Logback/Log4j của ứng dụng.
12. Coi **không thấy log** là bằng chứng **sự kiện không tồn tại**.
13. Bật debug sau sự cố rồi trông chờ thấy event xảy ra trước đó.
14. Coi runtime config luôn sống qua restart.
15. Gán mọi latency spike mới cho GC mà không xét overhead của logging.
16. Sao chép file vẫn đang ghi rồi so checksum như file đã hoàn tất.

## 18. Checklist kết thúc phiên thu thập

- [ ] Xác định đúng **JVM PID, VM version/vendor, container/host**.
- [ ] Khám phá tags từ **java -Xlog:help** trên binary phù hợp.
- [ ] Lưu **VM.log list** trước thay đổi.
- [ ] Chọn selector đúng **tag set + wildcard + level**.
- [ ] Chọn output, decorators, rotation và thời gian thu có giới hạn.
- [ ] Kiểm tra đường dẫn, quyền **JVM**, filesystem, quota, inode và cơ chế thu hồi file.
- [ ] Xác nhận thay đổi bằng **VM.log list** và log thực tế.
- [ ] Ghi nhận thời điểm bật/tắt, CPU/I/O/latency, tránh observer bias.
- [ ] Tắt **đúng output** hoặc hoàn nguyên các selector cũ, không dùng disable toàn cục.
- [ ] Đọc **VM.log list** sau rollback và lưu file/bằng chứng an toàn.

## Nguồn kỹ thuật để đối chiếu

- [JDK 21 — jcmd: VM.log (output, what, list, rotate, disable)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — java: Unified JVM Logging và -Xlog:help](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158)
- [OpenJDK JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271)
- [Inside Java — JVM Logging và runtime VM.log](https://inside.java/2022/11/07/sip071/)
- [AWS Corretto — Asynchronous Logging và cấu hình VM.log động](https://aws.amazon.com/blogs/developer/asynchronous-logging-corretto-17/)
- [Java SE 21 — ProcessHandle.current().pid()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)

**Tiêu chí thành công:** bạn nêu được **tag đang có, selector đang bật, output sẽ nhận file ở đâu, mức độ chi tiết, thời điểm quan sát, chi phí logging**, và **cách khôi phục chính xác**. Nếu thiếu những yếu tố này, tăng log bằng VM.log có thể tạo thêm nhiều dòng nhưng vẫn không tạo được bằng chứng đáng tin cậy để chẩn đoán JVM.
