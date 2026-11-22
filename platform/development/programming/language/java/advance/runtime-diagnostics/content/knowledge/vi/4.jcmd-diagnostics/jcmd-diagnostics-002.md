# 4.2 Điều kiện cùng máy, quyền người dùng và khả năng attach

> **Java Advance – runtime-diagnostics** · **4. Công cụ jcmd**

## 1. Vì sao chạy được jcmd vẫn chưa chắc kết nối được JVM?

*jcmd* là công cụ chẩn đoán đi kèm JDK, gửi **diagnostic commands** tới một JVM Java đang chạy. Lệnh có thể hỏi phiên bản VM, cấu hình khởi động, thread dump, thông tin bộ nhớ hoặc điều khiển Java Flight Recorder. Nhưng *có lệnh jcmd trong PATH*, *nhìn thấy PID* và *attach thành công* là **ba điều kiện khác nhau**.

Theo tài liệu JDK, jcmd cần hoạt động trên **cùng máy** với JVM đích và, với hệ thống có user/group ID như Linux, phải có **effective user ID và effective group ID tương ứng** với JVM được khởi chạy. Đồng thời, tiến trình phải thực sự tồn tại, nhìn thấy được qua namespace phù hợp, cung cấp cơ chế attach tương thích và có khả năng phản hồi. Container, cấu hình bảo mật, khác phiên bản JDK, quyền truy cập process/temporary directory hoặc JVM bị treo đều có thể khiến một phép chẩn đoán thất bại.

Bài này tập trung vào **điều kiện thực thi và cách kiểm tra attach**, không đào sâu phân tích nội dung thread dump, heap dump hay JFR.

Sau bài học, bạn có thể:

1. Giải thích “cùng máy” theo góc nhìn process, quyền hệ điều hành và container, thay vì nhầm với việc kết nối HTTP/JMX từ xa.
2. Xác định đúng PID và phân biệt kết quả *jcmd -l* với khả năng attach.
3. So sánh effective UID/GID của người gọi và JVM đích trên Linux; nhận biết giới hạn quyền trên Windows.
4. Kiểm tra tool JDK, JVM hỗ trợ attach, cờ *DisableAttachMechanism*, cấu hình temp/process namespace và tính sẵn sàng của tiến trình.
5. Chẩn đoán thông báo lỗi thường gặp mà không tự mở quyền hoặc thay đổi môi trường production thiếu kiểm soát.

## 2. Mô hình tư duy: bốn cổng cần đi qua

~~~text
Terminal có jcmd
       |
       v
[1] Đúng host / PID namespace, tìm đúng process?
       |
       v
[2] User + group + cơ chế bảo mật cho phép truy cập?
       |
       v
[3] JVM hỗ trợ và cho phép Attach Mechanism?
       |
       v
[4] JVM đang phản hồi và kênh attach có thể trao đổi?
       |
       v
jcmd <PID> VM.version thành công
       |
       v
Mới chọn diagnostic command phù hợp mục tiêu
~~~

Sơ đồ là **mô hình kiểm tra**, không phải đặc tả từng bước của giao thức attach trên mọi hệ điều hành. Một JVM có thể thỏa cổng trước nhưng trượt ở cổng sau: ví dụ PID hiển thị trong *ps* nhưng UID không khớp; hoặc user đúng nhưng JVM khởi động với attach bị vô hiệu.

| Câu hỏi | Dấu hiệu cần xác nhận | Nếu sai thường dẫn đến |
| --- | --- | --- |
| Đúng máy và đúng tiến trình? | Host/container, PID và command line đúng ứng dụng | Không thấy PID, chọn nhầm PID, process not found |
| Đúng danh tính/được phép? | Effective UID/GID, quyền hệ điều hành, chính sách bảo mật | Permission denied, Operation not permitted |
| Có công cụ và cơ chế tương thích? | JDK tool, JVM thực tế, phiên bản tương thích, attach enabled | Command not found, attach unsupported/disabled |
| JVM đáp ứng? | Process đang sống và phản hồi; đường trao đổi attach truy cập được | Timeout, unable to open socket/file, target does not respond |

**Nguyên tắc phân biệt:** *process visibility* chưa phải *permission*, và *permission* chưa phải *attach success*. Không suy ra “JVM không chạy” chỉ vì một lệnh liệt kê không tìm thấy nó.

## 3. “Cùng máy” nghĩa là gì?

*jcmd* chủ yếu là **công cụ chẩn đoán cục bộ**. Khi chạy:

~~~bash
jcmd <PID> VM.version
~~~

công cụ tìm tiến trình JVM đích và dùng kênh attach cục bộ của hệ điều hành/JVM. Đây **không** phải API HTTP/JMX mà chỉ cần hostname, cổng và mật khẩu. Không có cú pháp chuẩn “jcmd server.example.com:1234 VM.version” để attach từ laptop tới JVM trên máy khác.

Nếu JVM chạy trên máy chủ từ xa, cách diễn đạt đúng là: **đăng nhập vào đúng máy được cho phép (ví dụ SSH), rồi chạy jcmd tại máy đó**. Với container/Kubernetes, cần thực thi công cụ trong môi trường mà PID, quyền và kênh attach tương thích với JVM đích, thường là container ứng dụng hoặc môi trường chẩn đoán được cấu hình đúng.

| Trường hợp | Có đáp ứng “cùng máy” không? | Còn phải kiểm tra gì? |
| --- | --- | --- |
| Java và jcmd chạy cùng host, cùng user | Thường có | PID, group, JDK/JVM, attach enabled, JVM phản hồi |
| Laptop chạy jcmd nhưng Java ở máy remote | Không | Chạy công cụ từ remote host/đúng môi trường |
| SSH tới host chạy Java rồi gọi jcmd tại đó | Có ở mức host | User/group, namespace, binary, bảo mật |
| Java trong Docker, jcmd chạy ở host | Cùng host vật lý nhưng có thể **khác namespace/mount** | PID nhìn từ từng phía, kênh attach, UID/GID, quyền |
| Java trong container, jcmd chạy **ngay trong container ấy** | Thường là đường đơn giản nhất | Ảnh container có JDK/jcmd không; user có khớp không |
| jcmd trong một pod/container khác | Không mặc định attach được | PID namespace, temp/mount namespace, user, quyền; cần thiết kế debug thích hợp |

Đừng kết luận “cùng node Kubernetes” tức là jcmd chắc chắn attach được. Các pod thường có process namespaces riêng, và ngay cả các container trong một pod cũng không mặc định có đầy đủ quyền/đường dẫn để attach xuyên container.

## 4. PID là danh tính của **một process trong namespace cụ thể**

### 4.1 Liệt kê JVM bằng jcmd

Lệnh cơ bản:

~~~bash
jcmd -l
~~~

Trong môi trường bình thường, kết quả có thể có các dòng dạng:

~~~text
12345 com.example.Main
12501 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

Số PID và tên thực tế **thay đổi theo lần chạy**. *jcmd* có thể tự xuất hiện trong kết quả vì nó cũng chạy trên JVM. Hãy đối chiếu tên main class/JAR, command line, thời điểm khởi động và dịch vụ bạn muốn đo trước khi chọn PID.

Theo hướng dẫn chính thức của JDK 21, **jcmd -l không liệt kê các JVM đang chạy trong Docker process tách biệt** theo cách liệt kê thông thường; dùng các công cụ như *ps* để xác định PID khi cần. Vì thế:

- Không thấy JVM trong *jcmd -l* **không chứng minh JVM đã chết**.
- Thấy PID trong *jcmd -l* **không đảm bảo** lệnh attach có quyền và thành công.
- PID ngoài host và PID bên trong container **có thể khác nhau**. Ví dụ JVM là PID 1 trong container nhưng có PID khác khi nhìn từ host.
- PID có thể tái sử dụng sau khi process kết thúc; đừng lấy PID cũ rồi thực hiện một lệnh tác động mạnh.

### 4.2 Xác nhận PID bằng hệ điều hành

Trên Linux, tại môi trường có thể nhìn thấy Java:

~~~bash
ps -ef
~~~

Nếu đã có PID nghi vấn, kiểm tra cụ thể:

~~~bash
ps -o pid,ppid,euid,egid,args -p <PID>
~~~

Ghi nhận PID, PPID, EUID, EGID và chuỗi lệnh. *args* có thể chứa bí mật nếu ứng dụng truyền token, mật khẩu hoặc URL nhạy cảm trên command line; tránh sao chép nguyên văn ra nơi không được kiểm soát.

Trong container, nếu ứng dụng chạy là PID 1, đó có thể là **PID 1 bên trong container**, không phải PID 1 của host. Nên chạy phép kiểm và *jcmd* trong **cùng không gian PID** hoặc hiểu rõ ánh xạ PID giữa các namespace.

## 5. Quyền người dùng: effective UID/GID, không chỉ tên hiển thị

Trong mô hình Linux/Unix, user của shell là người **thực sự gọi jcmd**; user của JVM là danh tính tiến trình Java đang chạy. Tài liệu jcmd JDK 21 yêu cầu **same effective user and group identifiers**. Điều này cụ thể hơn nhận định “cùng nhóm Linux là đủ” hoặc “sudo/root chắc chắn luôn attach được”.

### Kiểm tra shell đang dùng

~~~bash
whoami
id
id -u
id -g
~~~

Ví dụ giả định:

~~~text
appuser
uid=10001(appuser) gid=10001(appgroup) groups=10001(appgroup)
10001
10001
~~~

Phần trên là **minh họa**, không phải output cố định trên mọi máy. *id -u* và *id -g* khi chạy bình thường mô tả effective identity tương ứng; với các trường hợp real/effective ID khác nhau, kiểm tra kỹ dữ liệu của tiến trình.

### Kiểm tra JVM đích

~~~bash
ps -o pid,euid,egid,args -p <PID>
~~~

Nếu JVM có effective UID=10001, effective GID=10001, nhưng shell chạy jcmd là UID=1000, GID=1000, đó là **mismatch đáng kiểm tra trước**. Chạy lệnh dưới user vận hành thích hợp theo quy trình được phép, ví dụ trên hệ thống đã cho phép chuyển sang *appuser*:

~~~bash
sudo -u appuser -- jcmd <PID> VM.version
~~~

Lệnh này chỉ là ví dụ có điều kiện; hãy xác minh **cả group effective** sau chuyển user, quyền chính sách của hệ thống và đường dẫn JDK. Không được coi *sudo -u* là mẹo chắc chắn giải quyết mọi lỗi hoặc yêu cầu tự nâng quyền trong môi trường hạn chế.

**Linux groups bổ sung** có thể cấp quyền tài nguyên khác, nhưng không thay thế điều kiện effective identity mà jcmd mô tả. Các cơ chế SELinux/AppArmor, seccomp, procfs restrictions, container capabilities và chính sách dịch vụ có thể giới hạn thao tác ngay cả khi user trông giống nhau. Quyền root, nếu có, cũng không tự giải quyết PID/mount namespace, attach disabled hoặc JVM không phản hồi.

### Trên Windows

Windows không dùng UID/GID POSIX theo cùng cách. Hãy kiểm tra tài khoản chạy dịch vụ Java, tài khoản gọi jcmd, quyền truy cập process và mức quyền/elevation. Chạy terminal cùng tài khoản/ngữ cảnh bảo mật thích hợp thường là hướng kiểm tra đầu tiên. Không suy diễn từ quy tắc Linux rằng chỉ cần *whoami* giống nhau là đủ trên mọi Windows service/session.

### Vì sao điều này quan trọng?

Diagnostic commands có thể bộc lộ command-line arguments, thông tin cấu hình, stack, dữ liệu memory, hoặc tạo dump chứa dữ liệu nhạy cảm. Kiểm soát quyền attach là một phần của biên bảo mật; không nên “chữa lỗi” bằng cách vô hiệu hóa chính sách an toàn một cách đại trà.

## 6. Có jcmd trong image hay không: JDK, JRE và PATH

Để chạy jcmd cần có **binary jcmd** trong môi trường thực thi công cụ, thường thuộc JDK. Nhiều runtime image tối giản, JRE-only hoặc distroless **không kèm** công cụ này. Một JVM vẫn có thể chạy ứng dụng bình thường mà container không có lệnh *jcmd*.

Kiểm tra:

~~~bash
java -version
jcmd -h
~~~

Trong Linux/macOS shell có *command*:

~~~bash
command -v java
command -v jcmd
~~~

Nếu jcmd không nằm trong PATH nhưng được JDK cài đặt, có thể sử dụng đường dẫn đầy đủ tới *bin/jcmd* của JDK phù hợp. Tuy nhiên đừng coi việc chép một binary từ JDK không tương thích vào image là biện pháp chuẩn.

**Tính tương thích phiên bản:** tài liệu lệnh *java* lưu ý các công cụ JDK (gồm jcmd, jmap, jstack, jinfo) **không được hỗ trợ** khi dùng công cụ từ một phiên bản JDK để chẩn đoán JVM của phiên bản khác. Vì vậy lựa chọn an toàn là dùng **jcmd của JDK tương ứng với JVM đích**; kiểm tra *java -version* của cả công cụ và Java đang chạy, không chỉ Java mặc định trong PATH.

Nếu target là một VM hoặc implementation không hỗ trợ các diagnostic commands của HotSpot, một kết quả attach không thành công không có nghĩa ứng dụng bị lỗi. Cần xác minh tên VM, version, implementation và tài liệu của nhà cung cấp.

## 7. Attach Mechanism phải được bật và JVM phải phản hồi

HotSpot có tùy chọn:

~~~text
-XX:+DisableAttachMechanism
~~~

Khi JVM được khởi động với cờ này, cơ chế để các công cụ attach vào JVM bị vô hiệu. Đối với trường hợp đó, chạy đúng user/host/PID vẫn **không làm jcmd attach thành công**. Cờ được xác định khi khởi động; nếu chính sách vận hành cho phép thay đổi, cần lên kế hoạch điều chỉnh cấu hình và khởi động lại có kiểm soát. Không tự đổi cờ trên production chỉ vì muốn lấy một snapshot.

Phân biệt các khái niệm dễ nhầm:

- **DisableAttachMechanism:** hạn chế trực tiếp cơ chế attach của công cụ.
- **EnableDynamicAgentLoading:** liên quan khả năng nạp agent Java/JVMTI động; không đồng nghĩa “bật mọi lệnh jcmd”.
- **JEP 451 (JDK 21):** cảnh báo khi nạp agent động; **không phải** thông báo rằng mọi lệnh đọc như *VM.version* bị tắt.
- **-Djdk.attach.allowAttachSelf:** cấu hình liên quan self-attach trong một số trường hợp API; không phải cách chung để sửa *jcmd* chạy như một process bên ngoài.

Một JVM có attach enabled nhưng đang bị nghẽn nghiêm trọng, pause dài hoặc không đáp ứng kịp request có thể khiến lệnh thất bại vì timeout. Lỗi thời gian chờ **không đủ bằng chứng** kết luận cờ DisableAttachMechanism được bật.

Cơ chế attach trên Linux có thể liên quan các tệp/socket tạm và đường dẫn nhìn qua namespace/mount khác nhau. Nếu công cụ không nhìn thấy kênh trao đổi do cấu hình container/temp filesystem hay sự cố môi trường, kết nối có thể thất bại dù process tồn tại. Không tùy tiện xóa socket, xóa thư mục temp hay mở quyền toàn bộ */tmp* trên production: các thao tác đó có thể ảnh hưởng JVM và ứng dụng khác.

## 8. Quy trình kiểm tra ít xâm lấn: từ PID đến VM.version

Đi theo đúng thứ tự để tránh chạy thử những lệnh có overhead lớn khi chưa rõ target.

### Bước 1 – Xác định môi trường

Ghi nhận:

- Host hoặc node/container/pod thực sự chạy ứng dụng.
- OS, JDK/JVM version và đường dẫn *jcmd* dự kiến.
- Tài khoản effective của JVM, tài khoản của terminal, nhóm tương ứng.
- Mốc thời gian và instance/version đang chịu triệu chứng.

### Bước 2 – Xác định đúng PID

~~~bash
jcmd -l
ps -ef
~~~

Trong môi trường không có *ps* hoặc *jcmd*, cần một phương án quan sát process hợp lệ, không tự kết luận Java chết. So khớp command line với ứng dụng đích; nếu process mới vừa restart, lấy PID mới.

### Bước 3 – Xác minh user/group khi dùng Linux

~~~bash
id
ps -o pid,euid,egid,args -p <PID>
~~~

Nếu có mismatch, xin/áp dụng quyền vận hành thích hợp để chạy từ cùng effective identity. Không tự nâng đặc quyền trái chính sách.

### Bước 4 – Kiểm tra lệnh attach đơn giản nhất

~~~bash
jcmd <PID> VM.version
~~~

*VM.version* là phép kiểm đọc trạng thái, thường nhẹ hơn thread dump hoặc heap dump. Kết quả thành công có phần đầu chứa PID đích và thông tin VM/version; nội dung chính xác thay đổi theo JDK và vendor.

Tiếp tục liệt kê diagnostic commands mà **chính JVM đích** hỗ trợ:

~~~bash
jcmd <PID> help
~~~

Có thể hỏi riêng cú pháp của một diagnostic command:

~~~bash
jcmd <PID> help Thread.print
~~~

Khi đã chắc chắn attach được và có mục đích chẩn đoán rõ:

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
~~~

*VM.flags* cho biết cấu hình VM thực tế; *VM.command_line* có thể để lộ tham số nhạy cảm nên chỉ lưu/xuất theo phạm vi bảo mật cho phép. Sau đó mới cân nhắc *Thread.print*, *JFR.start*, *GC.heap_dump* tùy vấn đề và mức tác động; “attach được” không có nghĩa mọi lệnh đều miễn phí hoặc chỉ đọc.

### Bước 5 – Ghi kết quả và giới hạn

Một báo cáo tốt cần có thời điểm, PID, JVM version, user/group context, container/namespace, lệnh chẩn đoán, outcome/error nguyên văn **đã lọc dữ liệu nhạy cảm**, và vì sao kết luận được hoặc chưa được về khả năng attach. Không gán lỗi quyền nếu thực tế là JVM đang pause hoặc dùng JDK không tương thích.

## 9. Lab Java 17+: chạy JVM và attach đúng cùng máy

Lab dưới đây tạo một ứng dụng **đang sống đủ lâu** để thử *jcmd*. Chạy trên máy phát triển do bạn kiểm soát, với JDK 17+ có cả *javac*, *java*, *jcmd*. Không cần thư viện ngoài.

Tạo file **JcmdAttachDemo.java**:

~~~java
public final class JcmdAttachDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("Attach demo ready");
        Thread.sleep(90_000L);
    }
}
~~~

Biên dịch:

~~~bash
javac JcmdAttachDemo.java
~~~

Trong **terminal A**, chạy:

~~~bash
java JcmdAttachDemo
~~~

Stdout chính xác của chương trình ngay lúc bắt đầu:

~~~text
Attach demo ready
~~~

JVM tiếp tục ngủ khoảng 90 giây rồi kết thúc bình thường, không in thêm gì. Nếu tiến trình bị dừng sớm bằng Ctrl+C, phần kết thúc phụ thuộc hệ điều hành, nhưng dòng đầu vẫn là đầu ra ứng dụng.

Trong **terminal B** (cùng host, cùng tài khoản effective và JDK phù hợp) khi JVM còn sống:

~~~bash
jcmd -l
~~~

Tìm dòng chứa *JcmdAttachDemo* và PID của nó. Ví dụ minh họa **PID không cố định**:

~~~text
12345 JcmdAttachDemo
~~~

Sau đó, thay *<PID>* bằng đúng PID vừa thấy:

~~~bash
jcmd <PID> VM.version
jcmd <PID> help
~~~

Nếu lệnh đầu thành công, bạn đã xác minh có thể giao tiếp với một JVM thực sự đang chạy trong ngữ cảnh đó. Nội dung *VM.version* không cố định vì phụ thuộc JDK/vendor/build; đừng kỳ vọng chuỗi xuất ra giống hệt giữa máy khác nhau.

**Thử nghiệm phân biệt list và attach (chỉ trên lab):** dừng chương trình, khởi động lại với attach bị vô hiệu:

~~~bash
java -XX:+DisableAttachMechanism JcmdAttachDemo
~~~

Chạy lại *jcmd -l* và *jcmd <PID> VM.version* trong thời gian program còn sống. Khả năng liệt kê process có thể khác nhau, nhưng việc attach vào JVM đã tắt cơ chế attach **phải thất bại**. Đây là minh chứng rằng “tìm thấy PID” và “attach thành công” không tương đương. Không dùng thử nghiệm tắt attach trên ứng dụng thật ngoài phạm vi cho phép.

### Vì sao mã có thể chạy trên Java 17?

Đây là Java thuần với *public static void main*, *System.out.println* và *Thread.sleep(long)*, không dùng API preview hay dependency. Tên file trùng tên public class. Mã chỉ giữ JVM sống để đo khả năng attach; nó **không thực hiện bản thân jcmd** hoặc thay đổi quyền tiến trình.

## 10. Docker: nhìn PID và user từ đúng phía

Trong image có JDK tool, ví dụ một container được đặt tên *my-java-app*, đường điều tra thường là thực thi lệnh **bên trong container ứng dụng**:

~~~bash
docker exec my-java-app sh -c 'id'
docker exec my-java-app sh -c 'ps -ef'
docker exec my-java-app jcmd -l
~~~

Nếu image không có *sh*, *ps* hoặc *jcmd*, các lệnh sẽ báo thiếu công cụ; điều này không nói rằng JVM không chạy. Ảnh production tối giản có thể chỉ chứa runtime và binary ứng dụng. Khi đó dùng đường chẩn đoán đã được đội vận hành phê duyệt (image debug phù hợp, môi trường có cùng PID/permission/temp requirements, hoặc telemetry sẵn có).

Một số Java app chạy trực tiếp với PID **1** trong container, nhưng không phải luôn luôn: entrypoint có thể gồm shell/tini hoặc nhiều process. Cần xác nhận *ps* nếu có, thay vì mặc định PID 1.

Nếu biết PID bên trong container (ví dụ PID 1 sau khi xác minh) và user khớp:

~~~bash
docker exec my-java-app jcmd 1 VM.version
~~~

**Điều kiện quan trọng:** user thực thi *docker exec* có thể theo cấu hình image/container và không giống user thực sự khởi chạy Java; kiểm tra *id* và process EUID/EGID. Docker cung cấp tùy chọn *--user* nếu bạn có quyền vận hành cần thiết, nhưng thay user phải phù hợp effective identity và không phá chính sách container.

**Tránh hai kết luận sai:**

1. Host thấy process Java có PID 24189 còn container thấy PID 1 không phải hai JVM khác nhau; đó có thể là **cùng một process được gán số khác giữa PID namespaces**.
2. Việc có thể dùng *docker ps* hoặc *docker exec* không chứng minh tool chẩn đoán cùng user, đúng JDK hoặc có đường attach hoạt động.

Khi buộc phải chẩn đoán từ host hoặc debug container, cần hiểu PID mapping, quyền hệ điều hành, *procfs*, mount namespace và nơi JVM tạo kênh attach. Không hướng dẫn chung bằng cách gắn */tmp* của các container với nhau hoặc mở quyền file/socket; cần xem xét riêng theo cấu hình bảo mật.

## 11. Kubernetes: kiểm tra đúng pod, container và namespace

Trong Kubernetes, vị trí chạy *kubectl* là workstation của bạn, nhưng lệnh sau thực thi chương trình **bên trong container** đã chọn:

~~~bash
kubectl exec -n <namespace> <pod> -c <container> -- jcmd -l
~~~

Để yêu cầu *VM.version* sau khi xác minh PID:

~~~bash
kubectl exec -n <namespace> <pod> -c <container> -- jcmd <PID> VM.version
~~~

Các tham số *<namespace>*, *<pod>*, *<container>* và *<PID>* chỉ là chỗ thay thế bằng giá trị thực. Trước khi chạy, kiểm tra đúng cluster/context, namespace, pod và container; pod có thể gồm nhiều container hoặc vừa restart. PID từ một lần chạy cũ có thể không còn.

Nếu *kubectl exec* báo không tìm thấy jcmd, đó là **vấn đề công cụ trong image**, không chứng minh target bị treo hoặc mất attach. Nếu không thấy PID, kiểm tra namespace/process visibility; nếu thất bại vì permission, xem effective user và chính sách container.

**Debug sidecar/ephemeral container không phải bảo đảm tự động:** một container mới có thể có *jcmd* nhưng không chia sẻ PID namespace hoặc temp/mount namespace với Java, hoặc chạy user khác. Cần phương án debug do đội platform quản lý, với truy cập đã cho phép và đúng ngữ cảnh, thay vì tự thêm capability cao hay bật privileged trên production.

Thực thi *jcmd* trong container không cần mở một HTTP endpoint hoặc management port mới. Đây là thao tác local vào process, nhưng vẫn được kiểm soát bởi Kubernetes RBAC, quyền exec và chính sách hệ điều hành.

## 12. Chẩn đoán lỗi phổ biến bằng dấu hiệu, không đoán mò

Thông báo cụ thể phụ thuộc JDK, OS, distro và cách triển khai. Bảng dưới đây là **hướng khoanh vùng**, không khẳng định mọi lỗi có một nguyên nhân duy nhất.

| Hiện tượng hoặc thông báo | Giả thuyết hợp lý | Phép kiểm tiếp theo |
| --- | --- | --- |
| *jcmd: command not found* | Không có JDK bin/jcmd hoặc PATH sai | Kiểm tra binary, image, JDK version |
| *jcmd -l* không thấy Java | Khác container/PID namespace; quyền khám phá process; JVM không xuất hiện trong cơ chế liệt kê; process đã thoát | *ps* trong đúng môi trường, PID/timestamp/container |
| *No such process*, *process not found* | PID sai, process đã restart/thoát hoặc namespace khác | Lấy lại PID mới, so command line và thời điểm |
| *Permission denied* / *Operation not permitted* | EUID/EGID mismatch hoặc cơ chế bảo mật chặn thao tác | *id*, *ps -o euid,egid*, chính sách OS/container |
| *AttachNotSupportedException* | JVM không hỗ trợ provider, attach disabled, sai implementation/version hoặc môi trường không tương thích | Xác minh JVM/JDK, startup flags, provider, PID |
| *Unable to open socket file* / *target does not respond* | Kênh attach/temp không truy cập được, khác namespace, target quá bận/không đáp ứng hoặc attach bị hạn chế | Đối chiếu process state, mount/temp, thời điểm, logs; không xóa socket tùy tiện |
| *Unknown diagnostic command* | Lệnh không tồn tại trong JVM/version đó hoặc tên/cú pháp sai | *jcmd <PID> help*, *help <command>* |
| Lệnh đọc nhẹ chạy được, heap dump/JFR thất bại | Quyền ghi file/đường dẫn, chi phí/tài nguyên, cấu hình riêng của command | Đọc help command, disk capacity, path nhìn từ JVM, permission |
| Lệnh chạy trên host nhưng không chạy trong container | Binary/user/PID/mount namespace khác, image tối giản | So cùng VM, effective identity, namespace và công cụ |

### Cách diễn giải có thứ tự

**Trường hợp A – jcmd -l không thấy target:**

1. Kiểm tra process Java còn sống hay không trong đúng host/container.
2. Xác nhận PID namespace và phạm vi liệt kê; với Docker, *jcmd -l* có giới hạn được tài liệu nêu.
3. Kiểm tra user context, tool version; không tự tăng quyền chỉ để “thấy thêm”.
4. Chỉ khi có PID đúng và quyền đúng mới thử *jcmd <PID> VM.version*.

**Trường hợp B – thấy PID nhưng attach báo permission denied:**

1. So effective UID/GID của shell và Java.
2. Kiểm tra OS policy, container security context, quyền process và temp path nếu cần.
3. Dùng danh tính được phép thay vì mở quyền toàn hệ.
4. Lặp lại lệnh đọc nhẹ, lưu error nguyên văn và timestamp nếu vẫn lỗi.

**Trường hợp C – UID/GID khớp nhưng attach timeout:**

1. Xác minh đúng PID/JVM/version.
2. Kiểm tra JVM có attach enabled hay không từ cấu hình khởi động/deployment.
3. Kiểm tra trạng thái process, CPU/GC/pause và dấu hiệu không phản hồi trong đúng khoảng.
4. Kiểm tra khác namespace hoặc temp/mount isolation.
5. Nếu JVM thực sự treo, cân nhắc phương án lấy thông tin qua telemetry, logs hoặc cơ chế OS khác do đội vận hành cho phép. Không coi mỗi lần timeout là bằng chứng JVM deadlock.

## 13. Lệnh có quyền nhưng mức tác động không giống nhau

Sau khi attach thành công, một số lệnh chủ yếu đọc thông tin, số khác gây overhead hoặc thay đổi trạng thái runtime:

| Nhóm | Ví dụ | Lưu ý |
| --- | --- | --- |
| Xác minh attach | *VM.version*, *help* | Thường là điểm bắt đầu nhẹ và dễ quan sát |
| Thông tin cấu hình | *VM.flags*, *VM.command_line* | Có thể lộ tham số nhạy cảm |
| Quan sát thread | *Thread.print -l* | Chi phí phụ thuộc số lượng thread; dữ liệu có thể lớn |
| Quan sát theo thời gian | *JFR.start*, *JFR.dump*, *JFR.stop* | Quản lý duration, dung lượng, vị trí lưu, overhead |
| Heap/memory dump | *GC.heap_dump* | Có thể ảnh hưởng đáng kể, tốn dung lượng và chứa dữ liệu nhạy cảm |
| Thay đổi cấu hình hoặc agent | *VM.set_flag*, *JVMTI.agent_load* và lệnh quản trị khác | Có thể thay đổi trạng thái hoặc mở khả năng mạnh; cần đánh giá/ủy quyền riêng |

Đừng thử một lệnh nặng trên JVM production chỉ để kiểm tra “attach có hoạt động không”. *VM.version* là phép xác nhận thích hợp hơn trong mục tiêu của bài này. Đặc biệt, các lệnh ghi file có thể tạo file theo **đường dẫn mà JVM đích nhìn thấy**, không nhất thiết đường dẫn của terminal/debug container gọi lệnh.

Nếu có lệnh dùng dữ liệu nhạy cảm (heap, args, stack), hạn chế quyền xem, nơi lưu, thời hạn lưu và cách chia sẻ. Không chuyển nội dung thực tế của process ra nơi công khai chỉ để lấy hỗ trợ debug.

## 14. Phân biệt lỗi attach với lỗi command

Một cuộc chẩn đoán phải kết luận đúng tầng thất bại:

~~~text
jcmd không chạy được?
  -> kiểm tra binary/PATH/JDK của terminal.

jcmd chạy nhưng không thấy JVM trong danh sách?
  -> kiểm tra PID, container/namespace, quyền khám phá process.

jcmd <PID> VM.version thất bại?
  -> kiểm tra PID còn sống, EUID/EGID, attach enabled,
     JDK/JVM tương thích, OS policy, kênh attach, JVM phản hồi.

VM.version thành công nhưng lệnh khác thất bại?
  -> attach cơ bản đã hoạt động; kiểm tra command help, cú pháp,
     quyền và tài nguyên riêng của lệnh, path đầu ra.

Lệnh chạy được nhưng dữ liệu không đúng mục tiêu?
  -> kiểm tra đã chọn đúng process, version, container, thời điểm.
~~~

**Quan trọng:** Nếu *VM.version* thành công, có bằng chứng rằng kết nối diagnostic với process đích hoạt động tại thời điểm đó; không có nghĩa mọi diagnostic command sẽ thành công trong mọi thời điểm. Nếu *VM.version* thất bại, không thể từ một lỗi duy nhất suy ra chính xác root cause; còn phải dựa vào loại lỗi và đối chứng.

## 15. Ba tình huống thực tế cần suy luận

### Tình huống 1 – Java chạy bằng appuser, terminal đăng nhập deployer

- JVM effective UID/GID là 10001:10001.
- Terminal gọi *jcmd* có 1000:1000.
- *ps* có thể thấy JVM, nhưng *jcmd <PID> VM.version* báo lỗi permission.

**Giả thuyết:** khác effective identity. **Kiểm chứng:** so *id*, *ps -o euid,egid*, quyền hệ điều hành; chọn user được phép khớp và chạy lại lệnh đọc. Không đổi ownership toàn bộ app hoặc cho chmod rộng.

### Tình huống 2 – JVM chạy PID 1 trong Docker

- *docker exec* cho thấy Java PID 1.
- Trên host, *ps* hiển thị một PID khác; *jcmd -l* ở host không liệt kê Java theo cách thông thường.
- Trong container không có jcmd vì dùng runtime image tối giản.

**Giả thuyết:** không phải thiếu JVM mà là khác PID namespace và thiếu công cụ. **Cách xử lý:** xác nhận PID thực và chọn đường debug được phép có JDK tương thích, cùng user/namespace/temp. Không tải/copy tùy tiện tool không tương thích vào container đang phục vụ traffic.

### Tình huống 3 – Đúng PID, đúng user nhưng chỉ một JVM attach thất bại

- Hai process HotSpot chạy cùng host và user.
- JVM A nhận *VM.version*; JVM B không nhận dù PID còn sống.
- Startup configuration của B có *-XX:+DisableAttachMechanism*.

**Giả thuyết có bằng chứng mạnh:** B tắt cơ chế attach ở startup. **Hành động:** ghi nhận giới hạn chẩn đoán, chuyển sang telemetry/log sẵn có; nếu cần mở attach, thay đổi cấu hình và rollout theo quy trình phê duyệt. Không trông chờ việc chuyển user hoặc tăng quyền giải quyết cờ VM này.

## 16. Checklist dành cho người trực sự cố

Trước khi sử dụng jcmd trên Java runtime:

1. Tôi đang ở đúng máy hoặc thực thi lệnh **trong đúng host/container** chứa JVM đích chưa?
2. PID có đúng process, cùng namespace và còn sống không? Có xác minh command line/instance/version?
3. *jcmd -l* có giới hạn trong môi trường container này không? Tôi có dùng *ps* hoặc cơ chế process discovery phù hợp chưa?
4. Java và jcmd có cùng họ implementation và phiên bản JDK phù hợp không?
5. Effective UID/GID (hoặc security context Windows) của người gọi có khớp điều kiện attach không?
6. JVM có bật Attach Mechanism không? Có *-XX:+DisableAttachMechanism* trong cấu hình khởi động không?
7. Chính sách process, procfs, filesystem/temp và container security có cho phép kênh attach không?
8. JVM có đang quá bận, pause dài hoặc không phản hồi vào thời điểm thao tác không?
9. Tôi đã thử **jcmd <PID> VM.version** và **help** trước các lệnh chi phí cao chưa?
10. Tôi đã ghi được timestamp, PID, lệnh, kết quả/error, phiên bản và điều chưa chắc chắn chưa?

Báo cáo kiểm tra nên dùng dạng ngắn sau:

~~~text
Target host/container:
JVM PID (namespace):
JVM Java version / implementation:
jcmd path / version:
Caller effective UID/GID (nếu Linux):
Target effective UID/GID (nếu Linux):
Attach enabled / startup flags evidence:
Command: jcmd <PID> VM.version
Timestamp/timezone:
Result: success / exact error
Hypothesis and next safe check:
~~~

Kết luận chỉ nên nằm trong giới hạn bằng chứng. “Permission denied do UID mismatch” đòi hỏi có chứng cứ identity; “Attach disabled” đòi hỏi có chứng cứ cấu hình JVM; “không thấy trong jcmd -l” **không đủ** để xác nhận JVM đã tắt.

## 17. Câu hỏi tự kiểm tra

**1. Tại sao jcmd -l chạy được nhưng không thấy Java trong Docker?**  
Vì khả năng liệt kê của jcmd có giới hạn với JVM trong Docker process tách biệt, đồng thời namespace/quyền có thể làm khác phạm vi quan sát. Cần xác minh process bằng công cụ hệ điều hành trong đúng môi trường; không đồng nhất “không được liệt kê” với “không tồn tại”.

**2. Cùng host và thấy PID có đủ để attach không?**  
Không. Còn điều kiện effective user/group, JVM hỗ trợ và cho phép attach, JDK/JVM tương thích, chính sách OS/container, kênh attach và mức phản hồi thực tế.

**3. *sudo* có luôn giải quyết Permission denied không?**  
Không. Phải bảo đảm danh tính và các quyền phù hợp; namespace, security policy hoặc attach disabled vẫn có thể chặn. Chỉ chuyển user/nâng quyền khi có ủy quyền vận hành.

**4. Nếu JVM có -XX:+DisableAttachMechanism, chạy jcmd dưới đúng UID có thành công không?**  
Không theo cơ chế attach đã bị vô hiệu. Cần điều chỉnh startup theo quy trình nếu muốn cho phép attach, hoặc dùng kênh quan sát khác.

**5. JEP 451 làm jcmd VM.version trên JDK 21 không dùng được?**  
Không. JEP 451 nói về nạp agent động và cảnh báo khi agent được nạp; không đồng nghĩa các diagnostic commands đọc trạng thái bị vô hiệu.

**6. VM.version thành công nhưng GC.heap_dump không ghi được file nói lên điều gì?**  
Attach cơ bản đã hoạt động. Cần kiểm tra điều kiện của **command cụ thể**, ví dụ đường dẫn/dung lượng/permissions theo góc nhìn JVM và ảnh hưởng tài nguyên, trước khi quy lỗi attach.

**7. Một command timeout có chứng minh JVM deadlock không?**  
Không. Timeout có thể do pause dài, áp lực tài nguyên, kênh attach/temp/namespace, cơ chế bị chặn hoặc JVM không đáp ứng trong khoảng giới hạn. Cần evidence bổ sung.

## 18. Tài liệu chính thức để tra cứu

- Oracle JDK 21, **The jcmd Command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21, **Diagnostic Tools**: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21, **The java Command**, mục *Advanced Serviceability Options*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- OpenJDK **JEP 451: Prepare to Disallow the Dynamic Loading of Agents**: https://openjdk.org/jeps/451

Đọc tài liệu đúng phiên bản JDK thực tế vì command list, cờ và cơ chế của từng VM có thể khác nhau.

## Ghi nhớ

**jcmd là đường chẩn đoán local từ công cụ đến một JVM cụ thể.** Muốn attach thành công, cần **đúng host/namespace và PID**, **đúng effective identity/quyền**, **JDK/JVM tương thích**, **Attach Mechanism cho phép**, và **JVM/kênh trao đổi đang phản hồi**. *jcmd -l* chỉ hỗ trợ khám phá process; bằng chứng kiểm tra trực tiếp đơn giản là *jcmd <PID> VM.version*. Luôn tách lỗi **tìm process**, **quyền**, **attach**, và **diagnostic command** để tránh sửa sai tầng hoặc tăng rủi ro vận hành.