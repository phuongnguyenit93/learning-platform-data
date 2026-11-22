# 3.6 Phân biệt PID của container với PID trên máy chủ

Khi điều tra một tiến trình Java trong container, cùng một JVM có thể được ghi là **PID 1** trong container nhưng **PID 48210** ở máy chủ Linux. Đây không phải hai tiến trình: đó có thể là **hai số nhận diện của cùng một tiến trình** dưới hai **PID namespace**. Nếu nhập PID ở sai phạm vi, các lệnh **ps**, **jcmd**, **kill**, thao tác **/proc** và quy trình gắn log/trace có thể nhắm nhầm tiến trình hoặc báo không tìm thấy JVM.

Bài này giải thích cơ chế PID namespace trên **Linux**, cách đối chiếu PID của container với PID ở máy chủ, những trường hợp không thể giả định Java là PID 1, và cách chọn đúng PID khi chẩn đoán JVM Java 21 với Docker/Kubernetes. Lệnh và ví dụ đầu ra dùng số minh họa; PID thật phải được kiểm chứng tại thời điểm thao tác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một tiến trình có thể có **nhiều PID hợp lệ** khi nhìn từ những PID namespace khác nhau.
- Phân biệt **PID của JVM**, **PID 1 của container**, **PID mà Docker daemon trả về**, **PID ở Linux host**, và **container ID**.
- Đọc trường **NStgid** cùng **NSpid** trong **/proc/<pid>/status** và hiểu hướng hiển thị từ namespace ngoài vào namespace trong.
- Đối chiếu một tiến trình Java trong container với tiến trình tương ứng trên Linux host mà không suy diễn bằng cách cộng/trừ một khoảng PID.
- Biết chọn PID cho **jcmd, ps, JFR, thread dump** theo môi trường công cụ đang chạy.
- Nhận ra ngoại lệ **--pid=host**, container cùng namespace, Kubernetes **shareProcessNamespace**, **hostPID**, image tối giản và Docker Desktop.
- Giảm rủi ro nhắm sai tiến trình sau khi container khởi động lại hoặc PID bị tái sử dụng.

## 2. PID là số có phạm vi: PID namespace xác định “nhìn từ đâu”

Trong Linux, **process ID (PID)** do kernel quản lý và có nghĩa trong một **PID namespace**. Khi container dùng namespace PID riêng, tiến trình bên trong thường chỉ thấy các tiến trình thuộc namespace đó và những namespace con có thể nhìn thấy; nó không mặc nhiên nhìn thấy toàn bộ tiến trình của Linux host. Ngược lại, namespace tổ tiên có thể nhìn thấy tiến trình của namespace con, nhưng mỗi nơi gọi tiến trình đó bằng một PID phù hợp với chính namespace của mình.

Ví dụ trong cách triển khai Docker Linux thông thường:

~~~text
Một tiến trình Java X trong Linux kernel
    |
    +-- PID namespace ở Linux host : PID 48210
    |
    +-- PID namespace của container: PID 1

Hai số 48210 và 1 có thể cùng chỉ tiến trình X.
~~~

**Điểm quyết định:** PID là giá trị gắn với **góc nhìn (namespace)**, không phải mã nhận diện toàn cục, vĩnh viễn cho một tiến trình. Các tiến trình khác nhau, ở những PID namespace khác nhau, đều có thể là **PID 1** mà không xung đột.

Một số quy tắc quan trọng:

1. Một tiến trình thuộc PID namespace khi nó được tạo. Namespace có thể lồng nhau thành một hệ phân cấp.
2. Tiến trình trong namespace con có PID tương ứng ở namespace đó và mỗi namespace tổ tiên có thể nhìn thấy nó. Các PID này **không có quy luật chuyển đổi số học đơn giản**.
3. **getpid()**, tương ứng với **ProcessHandle.current().pid()** trong Java, trả số tiến trình theo góc nhìn runtime nơi JVM chạy. Không dùng kết quả đó như PID toàn cục để ra lệnh từ mọi nơi.
4. PID namespace con thông thường không thể xem/điều khiển tiến trình chỉ tồn tại ở namespace tổ tiên bằng PID host. Phạm vi hiển thị cũng phụ thuộc **/proc** được mount từ namespace nào.
5. PID namespace và **cgroup** giải quyết hai bài toán khác nhau: namespace quyết định **PID và khả năng nhìn thấy tiến trình**; cgroup liên quan đến nhóm tiến trình và giới hạn/theo dõi tài nguyên. Có cùng cgroup hoặc container ID không biến hai PID thành cùng một giá trị.

**“Host” phải được định nghĩa rõ:** trong Docker Engine chạy trực tiếp trên Linux, host thường là chính kernel Linux nơi Docker daemon chạy. Trong **Docker Desktop trên Windows/macOS**, Linux containers chạy trong một **Linux VM**: PID mà Docker Engine nhìn thấy thuộc môi trường VM, **không phải PID của tiến trình Windows/macOS**. Trong Kubernetes, “host PID” thường là PID theo namespace của **node Linux** chạy Pod, không phải máy trạm đang chạy kubectl.

## 3. Không đồng nhất PID 1, Java PID và host PID

Một container có thể chạy một hoặc nhiều tiến trình. **PID 1** là tiến trình init trong PID namespace riêng khi container thực sự có namespace đó; PID 1 không có nghĩa “đây chắc chắn là Java”.

### 3.1. Ba cấu trúc khởi động thường gặp

**Trường hợp A: Java được thực thi trực tiếp**

~~~text
Linux host                          Trong container
PID 48210  java -jar app.jar   <=>   PID 1  java -jar app.jar
~~~

Nếu entrypoint khởi động **java** trực tiếp hoặc shell dùng **exec java ...**, Java có thể chính là PID 1. Khi đó giá trị **State.Pid** của Docker container có thể trỏ đến đúng tiến trình Java ở góc nhìn host Linux.

**Trường hợp B: shell/wrapper không dùng exec**

~~~text
Linux host                          Trong container
PID 48210  /bin/sh start.sh    <=>   PID 1  /bin/sh start.sh
PID 48253  java -jar app.jar   <=>   PID 7  java -jar app.jar
~~~

Docker thường biết PID của **tiến trình ban đầu container**, ví dụ **48210**. Nhưng JVM cần chẩn đoán là tiến trình **48253** (PID 7 bên trong). Dùng kết quả Docker inspect của tiến trình khởi đầu làm PID cho **jcmd** có thể nhắm vào shell, không phải JVM.

**Trường hợp C: có init nhỏ hoặc process supervisor**

~~~text
Linux host                          Trong container
PID 48210  tini                 <=>   PID 1  tini
PID 48253  java -jar app.jar    <=>   PID 7  java -jar app.jar
~~~

Sử dụng **docker run --init**, supervisor hoặc một init wrapper có thể giúp chuyển tiếp signal và thu hồi zombie child. Khi đó Java thường là **tiến trình con**, nên **PID 1** vẫn không phải PID cần chỉ định cho JVM diagnostics.

**Hệ quả thực tế:** trước khi dùng **jcmd 1**, phải xác nhận tiến trình có PID 1 trong namespace hiện tại **thực sự là JVM**. Không suy ra chỉ từ tên container, image Java hoặc service name.

### 3.2. PID, PPID, TID, container ID và Pod UID khác nhau

| Thuật ngữ | Là gì | Dùng để làm gì |
| --- | --- | --- |
| **PID** | ID của một process trong một PID namespace cụ thể | Chỉ định process cho ps, jcmd, signal, /proc theo góc nhìn caller. |
| **PPID** | PID của tiến trình cha nhìn từ namespace liên quan | Hiểu cây tiến trình; cha ở namespace ngoài có thể không hiển thị như bạn mong đợi. |
| **TID / LWP ID** | ID của thread ở mức kernel | Điều tra từng native thread; không trộn với PID process hoặc Java thread ID. |
| **Container ID** | ID do container runtime quản lý | Chọn container cho docker exec/inspect; **không phải PID**. |
| **Pod UID / container runtime ID** | Danh tính orchestration/runtime | Xác định chính xác workload/instance, hữu ích khi nhiều container trùng tên logic. |
| **PID namespace inode** | Danh tính của một đối tượng PID namespace trong cùng kernel | So sánh hai tiến trình có cùng PID namespace hay không. |

Đối với Java, **Thread.currentThread().threadId()** là **Java thread ID**, không phải Linux PID của JVM và cũng không đương nhiên là native TID; càng không dùng làm đối số **jcmd**. Trên Linux, trường **Tgid** là **thread-group ID**, tức process ID của thread group; trường **Pid** trong tệp status của một task là **thread ID**. Với thread-group leader hai giá trị thường trùng nhau.

## 4. Dữ liệu kernel để đối chiếu: /proc/<pid>/status

Tại Linux host, nếu có quyền đọc tệp **/proc/<host-pid>/status**, bạn có thể xem những dòng sau:

~~~text
Name:   java
Tgid:   48210
Pid:    48210
PPid:   47990
NStgid: 48210   1
NSpid:  48210   1
~~~

*Đây là dữ liệu minh họa cho trường hợp JVM chính là PID 1 trong container, được đọc từ procfs mount ở namespace host.*

**Cách đọc NStgid:**

- **NStgid** là danh sách **thread-group ID / process PID** qua các PID namespace mà process có mặt.
- **Giá trị bên trái** là PID theo namespace của tiến trình **đã mount procfs** đang đọc (thường là namespace host khi dùng **/proc** chuẩn ở Linux host).
- Các giá trị về bên phải là PID trong các namespace con ngày càng sâu.
- Ở ví dụ trên, **48210** là PID theo host procfs, **1** là PID theo namespace của container.
- Nếu namespace lồng sâu, bạn có thể thấy ba hoặc nhiều số, chẳng hạn **NStgid: 48253 301 7**. Không giả định chỉ có đúng hai cột.

**NSpid** có thứ tự tương tự nhưng mô tả **thread ID** trong từng PID namespace. Khi đọc tệp **/proc/<pid>/status** của **thread-group leader**, NSpid thường trùng NStgid. Khi đọc **/proc/<pid>/task/<tid>/status** của thread khác, NSpid chỉ **TID** và có thể khác NStgid. Khi mục tiêu là **PID của JVM như một process**, nên ưu tiên **NStgid**; đừng dùng TID của một Java worker thread làm process PID.

**Lưu ý chính xác về /proc:** kernel hiển thị các trường namespace trên hệ Linux có hỗ trợ (chúng xuất hiện từ Linux 4.1). Các giá trị bên trái phụ thuộc **procfs được mount từ namespace nào**. Trong container có procfs mount ở namespace chính nó, cùng tiến trình có thể hiển thị chỉ:

~~~text
Name:   java
NStgid: 1
NSpid:  1
~~~

Điều đó **không có nghĩa** PID host cũng là 1; procfs của container chỉ đang hiển thị từ góc nhìn hẹp hơn. **Không dựa vào /proc/self/status bên trong container để mặc định lấy được PID host**. Nếu các trường không tồn tại hoặc bị hạn chế quyền, dùng cơ chế container runtime/node tương ứng thay vì đoán PID.

### 4.1. Kiểm tra namespace inode

Linux còn cung cấp liên kết biểu diễn namespace, ví dụ:

~~~bash
readlink /proc/48210/ns/pid
~~~

Kết quả *minh họa*:

~~~text
pid:[4026532465]
~~~

Nếu hai process đang ở **cùng Linux kernel** và các đường dẫn **/proc/<pid>/ns/pid** có cùng namespace inode, chúng ở cùng PID namespace. Nhưng inode không thay thế **PID mapping**: hai process cùng namespace vẫn có PID khác nhau. So sánh inode giữa các **máy/VM khác nhau** không có ý nghĩa. Đừng suy ra PID bên trong từ số inode.

**PID namespace inode** còn hữu ích để thấy rằng **PID 1 của host** và **PID 1 của container** có thể thuộc hai namespace khác nhau, dù số cùng bằng 1. Cần biết namespace và ngữ cảnh mới xác định đúng tiến trình.

## 5. Thực hành Docker Engine trên Linux: đối chiếu một container đang chạy

Phần này giả định bạn có **Docker CLI truy cập daemon đang quản lý container trên Linux host** và có quyền cần thiết. Giả sử container tên **my-java-app**; thay bằng ID/tên thật. Các lệnh này chỉ kiểm tra thông tin, không dừng process.

### Bước 1 — Nhìn tiến trình trong container

Khi image có **sh**, **ps** và **cat**:

~~~bash
docker exec my-java-app sh -c 'ps -eo pid,ppid,comm'
docker exec my-java-app sh -c 'cat /proc/1/status | grep -E "^(Name|Tgid|Pid|PPid|NStgid|NSpid):"'
~~~

Đọc **PID của Java** và **PID của tiến trình 1**, xem chúng có giống nhau không. **docker exec** tạo thêm tiến trình tạm thời khi chạy lệnh nên process list có thể chứa cả shell/ps mới. Nếu container là **distroless**, không có shell/ps, đừng kết luận PID không tồn tại; chuyển sang thông tin từ Docker daemon/runtime hoặc công cụ debug được tổ chức cho phép.

**Nếu Java là PID 7:** dùng **7** khi thao tác trong chính PID namespace/container đó, bất kể Docker inspect báo PID của tiến trình 1 là bao nhiêu. Kiểm tra tên process và đường lệnh thay vì chỉ dựa vào số.

### Bước 2 — Lấy PID của tiến trình khởi đầu container từ Docker daemon

Chạy ở nơi có Docker CLI và daemon phù hợp:

~~~bash
docker inspect --format '{{.State.Pid}}' my-java-app
docker inspect --format '{{.HostConfig.PidMode}}' my-java-app
~~~

Giả sử kết quả lệnh đầu là **48210**. Trong triển khai **Docker Engine trực tiếp trên Linux**, **State.Pid** thường là PID của **tiến trình khởi đầu container** ở góc nhìn Linux host/daemon. Nó **không phải** ID container và **không nhất thiết** là PID của Java khi Java được shell, tini hay supervisor sinh ra. Giá trị **0** hoặc không có PID khả dụng có thể xuất hiện khi container không còn chạy; cần kiểm tra trạng thái container.

Giá trị **HostConfig.PidMode** giúp nhận biết container có dùng cấu hình chia sẻ PID đặc biệt hay không, chẳng hạn **host** hoặc **container:<id>**. Trường này không tự thay thế việc nhận diện JVM process đang sống.

### Bước 3 — Đọc bản đồ PID ở đúng Linux host

Trên **cùng Linux host/kernel với Docker daemon**:

~~~bash
HOST_PID=$(docker inspect --format '{{.State.Pid}}' my-java-app)
printf 'Docker init host PID: %s\n' "$HOST_PID"
grep -E '^(Name|Tgid|Pid|PPid|NStgid|NSpid):' /proc/"$HOST_PID"/status
readlink /proc/"$HOST_PID"/ns/pid
~~~

**Điều kiện:** đang chạy ở Linux shell đúng host, có procfs và đủ quyền. Đừng sao chép lệnh **/proc/$HOST_PID** sang Windows PowerShell/macOS rồi hy vọng đọc cùng kernel: khi dùng Docker Desktop, daemon/Linux containers nằm trong VM. Khi Docker CLI kết nối daemon từ xa, PID đó cũng thuộc **máy chạy daemon**, không thuộc máy đang gõ lệnh.

**Ví dụ giả định** nếu tiến trình khởi đầu là Java:

~~~text
Docker init host PID: 48210
Name:   java
Tgid:   48210
Pid:    48210
NStgid: 48210   1
NSpid:  48210   1
pid:[4026532465]
~~~

Dòng **NStgid: 48210 1** là bằng chứng mạnh về cặp PID nếu procfs được mount ở namespace host. Các số là minh họa, không phải đầu ra cố định.

### Bước 4 — Nếu Java không phải PID 1, phải tìm chính JVM trên host

Giả sử:

~~~text
Docker init: host PID 48210 / container PID 1 / program tini
Java:        host PID 48253 / container PID 7 / program java
~~~

Khi đó **docker inspect State.Pid = 48210** chỉ xác định **tini**. Bạn phải xác định **host PID 48253 của JVM**, ví dụ qua danh sách tiến trình mà Docker/runtime hoặc Linux host cho phép quan sát, rồi xác nhận:

~~~bash
grep -E '^(Name|Tgid|Pid|PPid|NStgid|NSpid):' /proc/48253/status
readlink /proc/48253/ns/pid
~~~

Kết quả minh họa:

~~~text
Name:   java
Tgid:   48253
Pid:    48253
PPid:   48210
NStgid: 48253   7
NSpid:  48253   7
pid:[4026532465]
~~~

Như vậy **48253** là PID host của JVM, **7** là PID container. Không tính **48253 - 48210 = 43** rồi dùng số 43 làm “offset” cho những process khác: mỗi namespace phân phối PID độc lập và có thể tái sử dụng số.

Khi nhiều JVM cùng container hoặc process được restart, kiểm tra thêm command line, thời gian bắt đầu, container ID và namespace. **Một cặp PID hôm qua có thể đã bị thu hồi và tái sử dụng hôm nay.**

### Bước 5 — Chọn lệnh theo nơi công cụ chạy

| Vị trí thao tác | PID dùng để xác định JVM | Thao tác điển hình |
| --- | --- | --- |
| **Trong container / PID namespace JVM** | **PID container** của Java, ví dụ **7** | **jcmd 7 VM.version**, **ps -p 7**, **/proc/7/status** nếu công cụ và quyền cho phép. |
| **Tại Linux host chứa Docker daemon** | **PID host** của chính JVM, ví dụ **48253** | **ps -p 48253**, **/proc/48253/status**, thử **jcmd 48253 ...** khi attach hỗ trợ. |
| **Docker CLI từ laptop kết nối daemon Linux từ xa** | PID theo daemon/remote host, **không phải PID laptop** | **docker inspect/exec** hướng tới daemon; thao tác /proc cần thực hiện trên đúng Linux host. |
| **Docker Desktop Windows/macOS (Linux containers)** | PID trong container hoặc Linux VM theo góc nhìn daemon | Dùng **docker exec**/khả năng chẩn đoán được hỗ trợ; **tasklist/Activity Monitor** không hiển thị trực tiếp cùng PID Linux. |
| **Kubernetes container tách PID namespace** | PID trong namespace container khi exec vào container | **kubectl exec** vào đúng container, xác định JVM PID trước khi chạy jcmd; host PID thuộc node Linux. |

Không chuyển đổi PID bằng cách thêm/bớt một con số, cũng không chọn **PID 1** chỉ vì đây là container Java.

## 6. Ví dụ Java 21 chạy được: xem PID mà chính JVM nhìn thấy

Java cung cấp **ProcessHandle.current().pid()**. Nó rất hữu ích để log **PID theo môi trường chạy JVM** nhưng không có API Java SE nào biến con số này thành “PID Linux host” trên mọi platform.

Chương trình sau đọc thêm thông tin **/proc/self/status** trên Linux. Nó vẫn biên dịch trên Java 21 ở platform khác; khi không có **/proc**, phần đó được bỏ qua với thông báo rõ ràng.

**Tệp PidNamespaceView.java**

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class PidNamespaceView {
    private static String field(List<String> lines, String name) {
        String prefix = name + ":";
        return lines.stream()
                .filter(line -> line.startsWith(prefix))
                .findFirst()
                .map(line -> line.substring(prefix.length()).trim())
                .orElse("(not available)");
    }

    public static void main(String[] args) throws IOException {
        ProcessHandle self = ProcessHandle.current();

        System.out.println("Java PID: " + self.pid());
        System.out.println("Java parent PID: "
                + self.parent()
                        .map(parent -> Long.toString(parent.pid()))
                        .orElse("(not visible)"));

        Path status = Path.of("/proc/self/status");
        if (!Files.isReadable(status)) {
            System.out.println("/proc/self/status: unavailable");
            return;
        }

        List<String> lines = Files.readAllLines(status);
        for (String name : List.of(
                "Name", "Tgid", "Pid", "PPid", "NStgid", "NSpid")) {
            System.out.println(name + ": " + field(lines, name));
        }
    }
}
~~~

Biên dịch và chạy với JDK 21:

~~~bash
javac --release 21 PidNamespaceView.java
java PidNamespaceView
~~~

**Diễn giải stdout:** những dòng **Java PID**, **Java parent PID**, **Name**, **Tgid**, **Pid**, **PPid**, **NStgid**, **NSpid** được in theo thứ tự đã viết khi **/proc** đọc được, còn các số cụ thể **khác nhau ở mỗi lần chạy**. Không nên ghi một bộ PID “chuẩn” duy nhất. Nếu **/proc** không đọc được, chương trình sẽ in hai dòng PID Java và dòng **/proc/self/status: unavailable**.

Ví dụ hình dung **khi Java thực sự là tiến trình 1** trong container Linux có procfs mount tại namespace container:

~~~text
Java PID: 1
Java parent PID: (not visible)
Name: java
Tgid: 1
Pid: 1
PPid: 0
NStgid: 1
NSpid: 1
~~~

Các dòng trên **chỉ là một khả năng minh họa**, không được bảo đảm cho mọi container. Tên **Name**, cách nhìn cha, procfs mount và JVM launcher có thể khác. Nếu Java là **PID 7**, chương trình thường thấy **Java PID: 7** ở namespace của mình; khi đọc **host procfs** bên ngoài, người vận hành có thể thấy NStgid dạng **48253 7**.

**Giới hạn quan trọng:** chương trình Java đang đọc **procfs đang được mount tại đường dẫn đó**. Nếu /proc không được mount đúng theo namespace hiện tại, trường NStgid có thể mang góc nhìn khác với **ProcessHandle.current().pid()**. Đừng diễn giải sai lệch đó là lỗi ProcessHandle; hãy xem cấu hình procfs/namespace.

### 6.1. Ví dụ Java 21 có stdout cố định: đọc NStgid mẫu

Đoạn này chỉ minh họa cách phân tích **một dòng mẫu đã biết**, không truy vấn tiến trình thật.

**Tệp PidMappingExample.java**

~~~java
public final class PidMappingExample {
    public static void main(String[] args) {
        String status = """
                Name:\tjava
                NStgid:\t48253\t7
                NSpid:\t48253\t7
                """;

        String line = status.lines()
                .filter(s -> s.startsWith("NStgid:"))
                .findFirst()
                .orElseThrow();

        String[] ids = line.substring("NStgid:".length())
                .trim()
                .split("\\s+");

        System.out.println("PID at procfs mount: " + ids[0]);
        System.out.println("PID at innermost namespace: "
                + ids[ids.length - 1]);
    }
}
~~~

~~~bash
javac --release 21 PidMappingExample.java
java PidMappingExample
~~~

**stdout chính xác:**

~~~text
PID at procfs mount: 48253
PID at innermost namespace: 7
~~~

Nếu trường mẫu có ba số **48253 301 7**, mảng **ids** sẽ có ba phần tử; đầu tiên vẫn là theo procfs mount, cuối cùng là namespace sâu nhất. Trong hệ thống thật, cần xác minh tên trường, trạng thái tiến trình và góc nhìn của procfs trước khi coi chúng là host/container PID.

## 7. Khi dùng công cụ chẩn đoán Java: PID sai phạm vi dẫn tới sai JVM

Với JDK 21, **jcmd** dùng PID tiến trình Java làm đối số. Tài liệu lệnh nêu rằng **jcmd -l** không nhất thiết liệt kê JVM chạy trong Docker process riêng; phải dùng công cụ quản lý tiến trình phù hợp để biết PID. Công cụ attach cần cùng máy chạy JVM và điều kiện quyền, runtime/VM, filesystem và namespace đáp ứng yêu cầu; **biết đúng PID chưa bảo đảm attach thành công**.

### 7.1. Chạy jcmd bên trong container

Khi container có JDK tools và Java đã được xác nhận là PID 7:

~~~bash
docker exec my-java-app jcmd 7 VM.version
docker exec my-java-app jcmd 7 help
~~~

Hoặc, nếu đã vào một shell **trong đúng PID namespace**, chạy:

~~~bash
jcmd 7 VM.version
jcmd 7 Thread.print
~~~

**Thread.print** chỉ nên dùng khi cần lấy snapshot thread với hiểu biết về overhead. **VM.version** là bước xác minh ít xâm lấn. Nếu Java là PID 1 thì thay **7** bằng **1**, nhưng chỉ **sau khi xác minh** bằng process list hoặc Java PID log.

Lệnh có thể không chạy vì image JRE/jlink/distroless thiếu **jcmd**, thiếu quyền theo effective UID/GID, bị hạn chế attach, container sai, hoặc đường dẫn/file socket bị ngăn. **Không sửa lỗi bằng cách tự động tăng quyền container** khi chưa biết nguyên nhân.

### 7.2. Chạy jcmd từ Linux host

Nếu đã xác nhận chính JVM có **host PID 48253** và công cụ phía host cùng môi trường/kernel có thể attach đúng cách:

~~~bash
jcmd 48253 VM.version
~~~

Lệnh **có thể thất bại** dù PID đúng. Khi JVM nằm trong container, cơ chế attach của HotSpot liên quan đến quyền, PID namespace, đường dẫn tạm và mount namespace; cấu hình bảo mật hoặc bộ công cụ khác nhau có thể cản trở. Việc **jcmd -l không hiển thị** một JVM Docker cũng **không chứng minh** JVM vắng mặt. Ưu tiên chạy công cụ trong môi trường phù hợp của JVM hoặc quy trình debug đã được kiểm chứng.

**Chọn PID cho /proc theo góc nhìn procfs**: đọc **/proc/48253/status** trên host để điều tra JVM đó, nhưng đọc **/proc/7/status** bên trong namespace container thông thường. **Không đưa 48253 vào đường dẫn /proc của container** chỉ vì thấy con số đó trên máy chủ.

### 7.3. Kết nối sang các tín hiệu chẩn đoán khác

- **Java application logs:** ghi **ProcessHandle.current().pid()** kèm container ID/Pod UID, instance ID, thời điểm khởi động, VM version để người vận hành xác định nguồn log. PID một mình không đủ làm khóa định danh toàn cục.
- **GC/JFR logs:** tệp được ghi ở filesystem theo môi trường tiến trình JVM; nếu chẩn đoán trên host/container khác, cần biết mount namespace và nơi file thực sự được tạo.
- **Thread dump:** ID từng native thread trong dump không phải PID của process; Java virtual-thread ID cũng không phải PID Linux. Phải phân biệt thread với process để không dùng nhầm PID cho signal/attach.
- **Metrics:** một label **pid=7** từ trong container không tự ghép được với **pid=48253** từ node exporter trên host. Cần khóa tương quan gồm container/runtime identity và namespace/cặp mapping đã được xác nhận.
- **JMX và API quản lý nội bộ:** có thể lấy số liệu qua endpoint mà không cần translate PID thủ công, nhưng quyền truy cập, mạng, chi phí và bảo mật của endpoint vẫn phải được kiểm soát.

## 8. Những ngoại lệ khiến giả định “container có PID riêng, Java là PID 1” sai

### 8.1. Docker --pid=host

Tùy chọn Docker:

~~~bash
docker run --pid=host ...
~~~

yêu cầu container **dùng chung PID namespace với Linux host**, thay vì namespace PID riêng mặc định. Khi đó tiến trình bên trong container nhìn PID theo host namespace; **PID 1** thường là init của host và **không phải** tiến trình chính của container. Tuy nhiên container vẫn có các cơ chế cô lập khác (mount, user, network, cgroup...) tùy cấu hình; chia sẻ PID không đồng nghĩa không có mọi dạng cô lập.

Không nên bật **--pid=host** chỉ để chữa lỗi quan sát PID: chia sẻ namespace làm thay đổi phạm vi tiến trình nhìn thấy và bề mặt bảo mật. Một số cấu hình user namespace cũng có hạn chế về khả năng dùng tùy chọn này.

### 8.2. Docker --pid=container:<name-or-id>

Hai container có thể chia sẻ cùng một PID namespace:

~~~bash
docker run --pid=container:my-java-app ...
~~~

Tiến trình đầu của container thứ hai **không nhất thiết là PID 1**, vì namespace đã có tiến trình init. Công cụ trong container thứ hai có thể nhìn thấy process của container mục tiêu nếu procfs, quyền và cấu hình cho phép. Dùng container ID/namespace để xác định đúng process; không mặc định container nào cũng có PID 1 riêng.

### 8.3. Kubernetes shareProcessNamespace và hostPID

Thông thường, các container trong một Pod **không nhất thiết** nhìn thấy process của nhau. Khi Pod được cấu hình:

~~~yaml
spec:
  shareProcessNamespace: true
~~~

các container trong Pod chia sẻ một PID namespace. Tiến trình chính của ứng dụng có thể có **PID khác 1**, và **PID 1** có thể là tiến trình của Pod sandbox. Sidecar/debug container có thể thấy các process khác cùng Pod theo quyền thích hợp. Việc này ảnh hưởng đến cách thu thập stack, gửi signal và cấu hình entrypoint.

Với **hostPID: true**, Pod dùng PID namespace của node; tiến trình trong container nhìn các PID theo namespace host tương ứng. Kubernetes không cho đặt **hostPID** và **shareProcessNamespace** đồng thời trong cùng Pod theo API. Những tùy chọn này cần có quyết định triển khai và bảo mật riêng.

Ví dụ đọc PID của Java từ container cụ thể:

~~~bash
kubectl exec pod-name -c app-container -- ps -eo pid,ppid,comm
~~~

Nếu image không có **ps**, dùng debug container/công cụ trên node theo chính sách vận hành. **kubectl** chạy trên laptop không khiến **/proc** của laptop trở thành /proc của node; muốn host PID thật phải kiểm tra từ **node/runtime** đang chạy Pod.

### 8.4. Docker Desktop, VM và daemon từ xa

Trên Docker Desktop cho Linux containers:

~~~text
Windows/macOS desktop
     |
     +-- Linux VM (Docker Engine, Linux host PIDs)
             |
             +-- container PID namespace (container PIDs)
~~~

Trong sơ đồ này, **Docker inspect State.Pid** phản ánh tiến trình theo góc nhìn Docker Engine/Linux VM; nó không phải số có thể dùng với **taskkill** của Windows hoặc **kill** trên macOS để tác động trực tiếp đến JVM Linux. Khi Docker CLI dùng context trỏ tới daemon từ xa, “host” lại là **máy daemon**, không phải terminal người dùng.

**Cùng cách viết "host PID" có thể chỉ ba môi trường khác nhau**: physical Linux node, Docker VM hoặc host daemon từ xa. Báo cáo chẩn đoán phải ghi rõ môi trường gốc.

### 8.5. Procfs, namespace lồng nhau, rootless và quyền

Một container tùy biến có thể không mount procfs như bạn mong đợi; vì vậy **ps**, **/proc/self** hoặc **NStgid** có thể đưa ra góc nhìn bất ngờ. Namespace lồng nhau, container chạy bên trong container, rootless runtime và các chính sách bảo mật có thể thay đổi công cụ và khả năng đọc.

PID namespace **không tự cấp quyền** đọc mọi /proc hoặc attach mọi JVM. User namespace/UID mapping, quyền truy cập /proc, chính sách của hệ thống và công cụ JVM vẫn quyết định hành động có được phép hay không. **Không yêu cầu --privileged, --pid=host hay vô hiệu hóa bảo vệ như một bước mặc định** của phép đo.

## 9. Tại sao PID 1 đặc biệt quan trọng với vận hành Java

Tiến trình PID 1 trong PID namespace có vai trò init: quản lý vòng đời và thu hồi các tiến trình con mồ côi. Linux có những quy tắc đặc biệt cho signal nhắm PID 1; ứng dụng Java chạy làm PID 1 có thể không nhận/xử lý signal theo cách bạn tưởng nếu không thiết lập handler và đường truyền signal đúng.

Ví dụ về thiết kế entrypoint:

~~~dockerfile
# Mô tả minh họa, không phải Dockerfile hoàn chỉnh
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ở dạng exec-form này (và PID namespace riêng), Java **có thể** là PID 1. Nếu dùng shell-form hoặc một script không **exec** Java, shell có thể là PID 1 và Java là child. Khi Docker dùng **--init** hoặc supervisor, init có thể ở PID 1 để nhận signal, chuyển tiếp và thu hồi zombie.

Việc container dừng/restart nên được thực hiện theo cơ chế Docker/Kubernetes với timeout và graceful shutdown thích hợp. Tránh dùng **kill -9** hoặc **kill 1** trên một PID suy đoán: **PID 1** ở namespace này có thể không phải JVM mong muốn, và PID có thể đã được tái sử dụng.

## 10. Công thức xử lý sự cố: chọn đúng PID trước khi debug

**Tình huống:** cảnh báo cho biết JVM trong container **orders-api** có CPU cao. Người vận hành chạy **jcmd 1 Thread.print** trong container nhưng nhận lỗi **not a Java process**. Trên host, **ps** lại cho thấy một Java process PID 56432.

**Cách phân tích:**

1. **Xác định đúng instance:** lấy container ID/Pod UID, node/daemon, trạng thái container và thời điểm bắt đầu. Tránh nhầm với replica khác cùng tên logic.
2. **Xác nhận PID tại nơi công cụ sẽ chạy:** bên trong container có thể thấy **tini PID 1** và **java PID 7**. Trên host cùng kernel, Java có thể là **PID 56432**.
3. **Đối chiếu cùng một process:** kiểm tra host **/proc/56432/status**; trường **NStgid** minh họa có thể là **56432 7**. Kiểm tra namespace inode và command line nếu cần. Đừng dùng **State.Pid** của Docker để thay thế PID Java khi có init/wrapper.
4. **Chạy diagnostic đúng phạm vi:** trong container dùng **jcmd 7 VM.version** trước; tại host, nếu attach được hỗ trợ và quyền phù hợp, dùng **jcmd 56432 VM.version**. Chỉ sau khi xác minh mới yêu cầu thread dump/JFR.
5. **Giữ chứng cứ gắn danh tính:** ghi container ID, node, thời điểm, cặp host/container PID, JVM version và kết quả lệnh. Nếu container restart, **tra lại mapping** thay vì tái sử dụng cặp PID cũ.

**Kết luận có cơ sở:** lỗi ban đầu xuất phát từ việc **chọn PID 1 là init**, không phải Java; phần quan sát cần nhắm đúng PID. Tuy nhiên nếu đã chọn đúng PID mà attach vẫn lỗi, phải tiếp tục kiểm tra quyền, file system, runtime và công cụ. Không kết luận tất cả lỗi attach đều do mapping.

### 10.1. Checklist trước khi dùng jcmd/ps/kill trên container Java

| Câu hỏi | Xác minh |
| --- | --- |
| Tôi đang thao tác ở đâu? | Container, node Linux, Docker VM hay laptop kết nối daemon từ xa? |
| PID namespace được chia sẻ hay riêng? | Docker PidMode, Kubernetes hostPID/shareProcessNamespace, namespace inode. |
| Tiến trình Java có phải PID 1 không? | Process list, command line, ProcessHandle log, procfs. |
| Cặp PID được xác minh trên cùng process chưa? | NStgid từ đúng procfs, command/start time/container identity. |
| Tại nơi chạy tool phải dùng PID nào? | PID theo namespace/procfs của tool (hoặc runtime API tương ứng). |
| Tool có ở đó và có đủ quyền không? | JDK/JRE image, effective UID/GID, attach policy, procfs/socket, security controls. |
| PID còn đúng tại thời điểm tác động không? | Kiểm tra process vẫn sống và container chưa restart, tránh PID reuse. |
| Có thể dùng lệnh đọc trước không? | VM.version, ps, /proc/status; chỉ dùng thao tác gây tác động khi cần thiết. |

## 11. Những lỗi tư duy thường gặp

1. **“Java trong container luôn là PID 1.”** Sai khi có shell, tini, supervisor hoặc share PID namespace.
2. **“docker inspect State.Pid là PID của JVM.”** Nó là PID của tiến trình khởi đầu container theo daemon; JVM có thể là con.
3. **“PID của container khác PID host một offset cố định.”** PID namespace gán PID độc lập; không có công thức cộng/trừ tổng quát.
4. **“NSpid là PID process ở mọi chỗ.”** NSpid mô tả thread ID; dùng NStgid để xem process/thread-group ID, và xét bạn đang đọc task nào.
5. **“NStgid bên trong container luôn chứa PID ngoài host.”** Tùy procfs mount; container mount riêng thường chỉ hiển thị số thuộc góc nhìn nó.
6. **“Không thấy JVM trong jcmd -l nên JVM đã dừng.”** Docker, phạm vi process, quyền, image và attach có thể khiến công cụ không liệt kê được.
7. **“docker inspect chạy từ Windows nghĩa là PID Windows.”** Docker Desktop Linux containers chạy trong Linux VM; PID thuộc môi trường Linux daemon.
8. **“Có root trong container thì attach được mọi JVM.”** Namespace khác user mapping, procfs/mount restrictions, quyền effective UID/GID và công cụ JVM.
9. **“Kubernetes Pod có một PID 1 nhất định là Java.”** Với shareProcessNamespace, init của Pod và JVM có thể là hai tiến trình khác.
10. **“PID được ghi tuần trước còn đúng sau deploy.”** PID bị tái sử dụng; luôn kèm thời điểm, container identity và process start.
11. **“Cùng PID số 7 nghĩa là cùng tiến trình.”** Hai namespace hoặc hai host khác nhau đều có thể chứa PID 7.
12. **“Dùng host PID với jcmd trong container cho chắc.”** PID phải theo góc nhìn công cụ và cơ chế attach thực tế; host PID có thể không tồn tại trong /proc của container.

## 12. Tự kiểm tra

**Câu 1.** Docker inspect báo **State.Pid = 41000**, trong container **ps** có **tini PID 1** và **java PID 8**. Có thể chạy **jcmd 41000** trên host để lấy thread dump Java chưa?

**Trả lời:** chưa có căn cứ. **41000** có thể là host PID của **tini**, không phải Java. Cần tìm host PID của JVM, đối chiếu **NStgid** và kiểm tra khả năng attach. Trong container, sau khi xác nhận, mục tiêu phù hợp là PID **8**.

**Câu 2.** Trên host Linux, **/proc/53000/status** có **NStgid: 53000 13**. Nếu host procfs mount ở namespace host và tiến trình nằm trong một namespace con, PID nào dùng khi đọc /proc bên trong container?

**Trả lời:** thường **13**, nếu /proc của container mount trong namespace chứa tiến trình tương ứng. Trên host dùng **53000**. Không đổi chiều nếu chưa xác minh góc nhìn procfs.

**Câu 3.** JVM in **ProcessHandle.current().pid() = 1**, nhưng **docker inspect** báo **31200**. Có mâu thuẫn không?

**Trả lời:** không. Đây có thể là cùng JVM khi nó là PID 1 trong container và PID 31200 ở host Linux. Kiểm chứng bằng mapping, không chỉ nhìn số.

**Câu 4.** Docker Desktop trên macOS báo **State.Pid = 880**. Có thể chạy **kill 880** ở macOS terminal để dừng chính JVM Linux đó không?

**Trả lời:** không được suy ra như vậy; PID 880 thuộc Linux VM theo Docker daemon, không phải PID macOS của cùng process. Dùng cơ chế Docker, exec hoặc debug trong môi trường Linux phù hợp.

**Câu 5.** Một Pod có **shareProcessNamespace: true**. Có thể mặc định **jcmd 1 VM.version** nhắm Java application không?

**Trả lời:** không. PID 1 có thể là tiến trình sandbox/init của Pod, trong khi Java nằm ở PID khác. Xem process list và định danh container.

**Câu 6.** Hai lệnh **readlink /proc/A/ns/pid** và **readlink /proc/B/ns/pid** trả cùng inode. Có chứng minh A và B là cùng process không?

**Trả lời:** không. Chúng có thể là hai process **khác nhau trong cùng PID namespace**. Cần so PID, namespace, command, start time và container identity.

## Nguồn tham khảo để đối chiếu

- [Linux pid_namespaces(7): quan hệ namespace tổ tiên/con, PID 1 và /proc](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
- [Linux proc_pid_status(5): Tgid, Pid, NStgid và NSpid](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
- [Linux namespaces(7): namespace inode và liên kết trong /proc](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Docker run: các chế độ PID namespace và --pid](https://docs.docker.com/reference/cli/docker/container/run/)
- [Docker inspect: định dạng và truy vấn metadata container](https://docs.docker.com/reference/cli/docker/inspect/)
- [Docker Desktop: ranh giới Linux VM và máy desktop](https://docs.docker.com/faqs/platform/)
- [Kubernetes: chia sẻ PID namespace trong Pod](https://kubernetes.io/docs/tasks/configure-pod-container/share-process-namespace/)
- [Java SE 21: ProcessHandle API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)
- [JDK 21: jcmd, PID lookup và điều kiện attach](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)

**Nguyên tắc sử dụng được ngay:** khi thấy một PID liên quan đến Java container, hãy luôn xác định **tiến trình nào, ở PID namespace nào, trên kernel/host nào, vào thời điểm nào và từ vị trí nào chạy công cụ**. Chỉ khi đã xác nhận đủ các yếu tố đó mới dùng số PID để chẩn đoán hoặc điều khiển JVM.
