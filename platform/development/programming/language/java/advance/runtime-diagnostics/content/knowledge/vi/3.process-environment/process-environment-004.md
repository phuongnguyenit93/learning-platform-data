# 3.4. VM.command_line, VM.flags, VM.system_properties và VM.info

Khi một ứng dụng Java chạy khác giữa máy phát triển và production, câu hỏi quan trọng thường không phải “cấu hình trong repository là gì?” mà là **JVM đang chạy thực sự được khởi động và cấu hình như thế nào**. Lệnh chạy trong shell, tham số JVM, Java system properties và trạng thái môi trường có thể khác nhau do script khởi động, container, orchestration, biến môi trường, cấu hình runtime hoặc thao tác sau khi process đã bắt đầu.

Với các JVM HotSpot/OpenJDK hỗ trợ diagnostic commands, tiện ích **`jcmd`** cho phép đọc thông tin trực tiếp từ một **tiến trình JVM còn sống**. Bốn lệnh sau phục vụ bốn câu hỏi riêng:

- **`VM.command_line`:** JVM được khởi động bằng các đối số nào?
- **`VM.flags`:** các cờ VM hiện có giá trị hiệu lực gì?
- **`VM.system_properties`:** Java system properties mà process đang thấy là gì?
- **`VM.info`:** trạng thái và bối cảnh môi trường JVM đang chạy ra sao?

Bài học thuộc nhóm **3. Tiến trình và môi trường**, tập trung vào mục đích, cách dùng, cách đọc, so sánh và giới hạn của bốn diagnostic commands này trong Java 17+. Không nên coi chúng là bằng chứng duy nhất về hành vi ứng dụng, và cũng không được nhầm thông tin chụp được ở thời điểm kiểm tra với cấu hình được version-control lúc build.

## 1. Điều kiện để đọc trực tiếp JVM đang chạy

`jcmd` nằm trong bộ công cụ **JDK** phù hợp. Phần lớn lệnh gửi yêu cầu chẩn đoán tới JVM qua cơ chế attach nên cần:

1. Tiến trình JVM **đang tồn tại**. Ghi đúng PID, container/pod/host, thời điểm và JDK version.
2. Chạy `jcmd` trên cùng máy hoặc trong môi trường có thể truy cập process tương ứng, với **effective user/group** phù hợp. Trên container có PID namespace khác, PID trong host và PID bên trong container có thể không trùng.
3. JVM đích hỗ trợ các lệnh được gọi và cho phép attach. Nếu chạy với `-XX:+DisableAttachMechanism` hoặc môi trường bị chặn quyền/truy cập, lệnh có thể thất bại.
4. Có chương trình `jcmd` trong môi trường thực thi công cụ. Một runtime image tối giản chỉ chứa JRE/application binary có thể không có `jcmd`; có thể cần JDK và cách truy cập tiến trình phù hợp.
5. Không giả định mọi vendor/version JVM đều có cùng nội dung hoặc định dạng output. **Hỏi trực tiếp JVM đích bằng `help`** để biết command thực sự được hỗ trợ.

Các lệnh cơ bản (ví dụ PID là **12345**, cần thay bằng PID thật):

~~~bash
jcmd -l
jcmd 12345 help
jcmd 12345 help VM.command_line
jcmd 12345 help VM.flags
jcmd 12345 help VM.system_properties
jcmd 12345 help VM.info
~~~

`jcmd -l` liệt kê JVM nhìn thấy từ môi trường hiện tại. Nó **có thể bỏ sót JVM nằm trong Docker/PID namespace riêng**; khi đó tra PID bằng công cụ process/container ở đúng namespace. Không dùng `jcmd 0 ...` hoặc target theo main class trong môi trường nhiều JVM chỉ để tiện thao tác: có nguy cơ gửi tới **nhiều tiến trình**. Gọi đúng PID cụ thể.

**Phạm vi thao tác:** bốn lệnh đang học dùng để *xem* thông tin, không phải `VM.set_flag` để thay đổi flag. Tuy nhiên output có thể dài và chứa bí mật; nên giới hạn người có quyền đọc, lưu ở nơi bảo vệ và xử lý trước khi chia sẻ.

## 2. Bảng phân biệt nhanh

| Lệnh | Trả lời câu hỏi | Dữ liệu cốt lõi | Điểm cần tránh |
| --- | --- | --- | --- |
| `VM.command_line` | “Đã khởi chạy bằng gì?” | JVM arguments và Java command/main class/JAR, tùy bản JVM | Không xem như trạng thái **cấu hình ứng dụng hiện tại** sau mọi thay đổi runtime |
| `VM.flags` | “VM flags đang có giá trị gì?” | Các flag của JVM với giá trị hiệu lực hiện tại; có thể xem toàn bộ bằng `-all` | Không nhầm flag với system property, args của `main` hoặc env var |
| `VM.system_properties` | “Java system properties hiện tại là gì?” | Danh sách `key=value` tương ứng properties JVM nhìn thấy | Không đồng nhất với **OS environment variables** hoặc mọi cấu hình Spring/application |
| `VM.info` | “Môi trường và trạng thái JVM như thế nào?” | Báo cáo tổng hợp về JVM/runtime và môi trường, phụ thuộc phiên bản | Không coi là snapshot đầy đủ của mọi vấn đề memory/CPU/thread; không kỳ vọng cấu trúc cố định |

**Hình dung ba lớp cấu hình:**

~~~text
Lệnh/launcher khởi động JVM
       |
       +-- JVM options: -Xmx, -Xms, -XX:... ----> VM.flags (giá trị hiệu lực)
       |
       +-- Java properties: -Dkey=value -------> VM.system_properties (snapshot hiện tại)
       |
       +-- Main class/JAR và app args ----------> VM.command_line (dấu vết startup)
       |
       +-- OS/container/JDK/runtime -----------> VM.info (báo cáo môi trường và trạng thái)
~~~

Đây là sơ đồ ý niệm, **không phải ánh xạ một-một** giữa các chuỗi ký tự. Ví dụ `-Xmx256m` khi đọc `VM.flags` thường được thể hiện qua flag `MaxHeapSize` theo đơn vị byte; một flag có thể được VM tự tính theo ergonomic defaults; một system property có thể bị chương trình thay đổi bằng `System.setProperty(...)` sau startup.

## 3. VM.command_line — đối số khi JVM được khởi động

Cú pháp:

~~~bash
jcmd 12345 VM.command_line
~~~

Command này in thông tin câu lệnh mà JVM lưu lại khi khởi động. Trên một bản HotSpot, có thể gặp các mục như:

~~~text
VM Arguments:
jvm_args: -Xms128m -Xmx256m -Ddemo.mode=startup
java_command: VmIntrospectDemo alpha beta
java_class_path (initial): .
Launcher Type: SUN_STANDARD
~~~

**Đây là output minh họa**, không phải stdout đảm bảo của mọi JDK/launcher. Vị trí, trường và nội dung thay đổi theo cách khởi chạy, vendor, Java version và classpath/JAR/module path.

Thông thường:
- **`jvm_args`:** đối số gửi vào JVM ở lúc startup, chẳng hạn `-Xmx`, `-XX:+UseG1GC`, `-Ddemo.mode=startup`.
- **`java_command`:** ứng dụng được khởi chạy và các application arguments theo cách launcher biểu diễn; ví dụ `-jar app.jar` hoặc tên main class kèm `args`.
- **Classpath/launcher:** có thể cho biết đường dẫn classpath ban đầu hoặc loại launcher, nhưng không nói rằng đường dẫn còn có hiệu lực y nguyên ở mọi classloader sau đó.

Dùng khi:
- Deploy báo JVM chạy với `-Xmx` khác cấu hình mong đợi.
- Cần xác minh process thực tế chạy class/JAR nào, có arguments nào sau main.
- Hai pod cùng image nhưng script/entrypoint hoặc JVM arguments khác nhau.
- Cần kiểm tra có vô tình truyền `-D...`, `-XX...`, agent hay option chỉ dành cho môi trường khác.

**Giới hạn quan trọng:** output phản ánh thông tin startup mà VM giữ; nó không phải bản sao đầy đủ, không bị biến đổi của câu lệnh shell gốc, quote/expansion, biến môi trường, configuration files hoặc toàn bộ nội dung application framework đang sử dụng. Nếu application thay đổi một property sau khi start, command line vẫn cho thấy đầu vào khởi động, còn `VM.system_properties` có thể cho giá trị mới. Một số launcher/runtime có thể bổ sung hoặc biến đổi options (ví dụ thông qua biến môi trường Java liên quan đến startup); khi cần truy gốc, đối chiếu với entrypoint, manifest deploy và cấu hình môi trường.

Đặc biệt chú ý **bí mật trong command line**: một ứng dụng truyền token/password bằng `-Dsecret=...` hoặc application argument có thể khiến nội dung xuất hiện trong output và cả công cụ quan sát process khác. Tránh đưa bí mật vào command line; khi phải thu chứng cứ, redact trước khi lưu/chia sẻ.

## 4. VM.flags — flag JVM và giá trị hiệu lực

Cú pháp:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
~~~

- **`VM.flags`:** hiển thị các flag VM theo cách định dạng của JVM, thường tập trung vào những flag đáng chú ý/không mặc định, không nhất thiết là danh mục đầy đủ.
- **`VM.flags -all`:** yêu cầu hiển thị các flags được VM hỗ trợ cùng giá trị hiện tại; output rất dài, thích hợp khi cần điều tra flag cụ thể hoặc nguồn thiết lập.

Các tên liên quan thường gặp trong điều tra:

| Flag | Liên quan đến |
| --- | --- |
| `InitialHeapSize` | Kích thước heap khởi tạo, thường liên hệ `-Xms` |
| `MaxHeapSize` | Giới hạn Java heap tối đa, thường liên hệ `-Xmx` |
| `UseG1GC` / flag GC khác | Garbage collector được lựa chọn |
| `ActiveProcessorCount` | Giá trị cấu hình thủ công cho số processor mà VM sử dụng để ra một số quyết định |
| `MaxRAMPercentage` | Tỷ lệ RAM được cân nhắc khi tính heap tối đa nếu không đặt trực tiếp giới hạn phù hợp |
| `UseContainerSupport` | Cơ chế VM xét thông tin container trong các bản HotSpot hỗ trợ |

Flag có thể là **boolean, số, chuỗi hoặc size**; output thường biểu diễn size theo **bytes** hoặc định dạng nội bộ. Ví dụ `-Xmx256m` thường tương ứng `MaxHeapSize` khoảng **268435456 bytes** (256 × 1024 × 1024), nhưng đừng mặc định mọi ràng buộc/alignment/JVM đều giống nhau. Cần đọc **giá trị thực** tại tiến trình đích.

Trong output `-all` của HotSpot, có thể xuất hiện ký hiệu giá trị và metadata về loại/nguồn, chẳng hạn `{product}`, `{default}`, `{command line}`, `{ergonomic}`; **diễn giải đúng theo phiên bản JVM đích**. Điều này giúp phân biệt:
- **Giá trị mặc định:** JVM chọn nếu không có điều chỉnh áp dụng.
- **Giá trị khai báo ở startup:** người vận hành, launcher hoặc cấu hình truyền vào.
- **Giá trị được tính theo ergonomic logic:** JVM lựa chọn dựa trên môi trường và chính sách.
- **Giá trị có thể được chỉnh khi chạy:** chỉ với flag đủ điều kiện thay đổi và công cụ có quyền; không coi mọi flag đều mutable.

Đây là lớp **JVM options**. Nó **không** phải tập hợp `-D` system properties và **không** phải đối số truyền vào `main(String[] args)`. Hai nơi có chuỗi tên tương tự nhau vẫn có thể có ý nghĩa độc lập.

### Vì sao “đã truyền -Xmx” vẫn phải xem VM.flags?

Vì JVM có thể áp dụng tính toán, alignment, chính sách liên quan RAM/container, lựa chọn collector và các defaults theo version. So sánh startup với **giá trị hiệu lực** cho phép xác nhận giả thuyết “đã đặt -Xmx nhưng heap thực tế khác”. Nếu không thấy option trong `VM.flags` dạng rút gọn, không vội kết luận “chưa có”: sử dụng `VM.flags -all`, `VM.command_line` và `help`.

Không dùng `VM.flags` để kết luận giới hạn bộ nhớ **của cả process**: heap chỉ là một phần; metaspace, code cache, native buffers, stacks và GC/JIT còn tiêu thụ bộ nhớ riêng. Dù biết `MaxHeapSize`, vẫn cần process RSS/cgroup và công cụ memory khác nếu điều tra OOMKilled.

## 5. VM.system_properties — Java system properties hiện tại

Cú pháp:

~~~bash
jcmd 12345 VM.system_properties
~~~

Nội dung là các cặp **`key=value`** mà Java system properties cung cấp trong JVM tại thời điểm đọc; những property tiêu biểu gồm:

~~~text
java.version=17...
java.home=...
java.class.path=...
user.dir=...
file.encoding=...
demo.mode=runtime
~~~

Đây là **ví dụ rút gọn**, dấu `...` biểu thị giá trị phụ thuộc môi trường chứ không phải dữ liệu thực. Chương trình cũng có thể thêm/chỉnh property, ví dụ:

~~~java
System.setProperty("demo.mode", "runtime");
String mode = System.getProperty("demo.mode");
~~~

Đoạn trên chỉ là **minh họa API**, muốn chạy độc lập hãy dùng chương trình đầy đủ ở mục 7. Nếu JVM ban đầu được chạy với `-Ddemo.mode=startup` nhưng chương trình sau đó gọi `System.setProperty("demo.mode", "runtime")`, lúc chụp `VM.system_properties` có thể thấy `demo.mode=runtime`. Điều này là một chứng cứ **cấu hình hiện tại khác đầu vào startup**, không phải sự “mâu thuẫn” giữa hai lệnh.

Phân biệt ba nguồn thường bị trộn lẫn:

| Thứ được đọc | Ví dụ thiết lập | Cách kiểm tra | Giới hạn |
| --- | --- | --- | --- |
| **Java system property** | `-Ddemo.mode=startup` hoặc `System.setProperty` | `VM.system_properties` / `System.getProperty` | Có thể bị đổi trong runtime |
| **Environment variable** | `APP_MODE=prod` trong shell/pod | `System.getenv("APP_MODE")` hoặc công cụ OS/container | Không tự động trở thành Java system property |
| **Application/framework config** | YAML, JSON, config server, secret manager, command-line application args | Cơ chế diagnostics/config của framework ứng dụng | Có thể hợp nhất nhiều nguồn theo precedence; chưa chắc là property của JVM |

Ví dụ `SPRING_PROFILES_ACTIVE` là biến môi trường có thể được framework đọc và chuyển thành cấu hình ứng dụng, nhưng không được mặc định nó xuất hiện nguyên dạng trong `VM.system_properties`. Việc `java.version`/`user.dir` hiện trong hệ thống properties cũng không biến chúng thành environment variables.

**Lưu ý về snapshot:** properties có thể bị code khác thay đổi cùng lúc; chỉ coi output là ảnh chụp tại thời điểm lệnh thực thi. Khi thấy khác nhau giữa hai lần đọc, lưu timestamp và xác định code/config nào thực sự thay đổi chúng. Không lấy nó để suy ra trực tiếp **tất cả** biến môi trường, secrets và runtime configuration.

**Bảo vệ dữ liệu:** system properties có thể chứa endpoint nội bộ, user information, truststore/key store paths, proxy details, token hoặc thông tin nhạy cảm do app tự nhét vào `-D`. Không công khai dump thô; giới hạn người đọc và redact có kiểm soát khi tạo báo cáo.

## 6. VM.info — bối cảnh tổng hợp của JVM và môi trường

Cú pháp:

~~~bash
jcmd 12345 VM.info
~~~

`VM.info` in báo cáo thông tin về **JVM environment and status** theo bản cài đặt. Trên nhiều bản HotSpot, output có thể dài và gồm các nhóm về JVM/runtime, compiler/GC, cấu hình, OS, CPU, bộ nhớ hoặc các phần liên quan đến trạng thái VM. **Không dựa vào thứ tự hoặc danh mục section cố định**: một JDK khác, vendor khác hoặc bản nâng cấp có thể thay đổi những phần có mặt. Đọc `jcmd 12345 help VM.info` để biết command được hỗ trợ và tùy chọn cho đúng target.

Khi nào có ích:
- Điều tra khác biệt giữa các máy/container dù cùng ứng dụng.
- Bổ sung bối cảnh runtime cho bug report khi cần tái hiện: JDK build/vendor, OS, CPU, memory, trạng thái JVM tại thời điểm chụp.
- Kết hợp với `VM.command_line` và `VM.flags` để xác minh environment effect, nhất là giới hạn container hoặc quyết định ergonomics.
- Thu thêm bối cảnh khi thấy CPU/GC/memory bất thường mà log ứng dụng chỉ ghi triệu chứng.

**Không diễn giải quá mức:** `VM.info` không phải heap dump, thread timeline, CPU profiler, JFR recording hay bằng chứng đầy đủ cho từng phân bổ native memory. Tùy vấn đề, có thể cần `GC.heap_info`, `Thread.print`, GC logs/JFR, NMT hoặc metrics OS/container; chúng **nằm ngoài bốn lệnh chính** của bài này.

**Tính vận hành:** bốn command được JDK mô tả là diagnostics có tác động thấp, nhưng `VM.flags -all` và `VM.info` vẫn có thể tạo lượng text đáng kể, tốn thời gian đọc/lưu và chứa thông tin nhạy cảm. Tránh chạy lặp vô hạn hoặc thu thập tràn lan trong sự cố. Chọn thời điểm, PID, phạm vi và nơi lưu an toàn.

## 7. Thực hành Java 17+: nhìn thấy khác biệt startup và runtime

Chương trình dưới đây **chạy độc lập**, sử dụng Java 17+. Nó nhận một system property từ startup, sau đó **cố ý thay giá trị trong runtime**, in số lượng application arguments và giữ process sống đủ lâu để bạn gọi `jcmd` từ terminal khác.

Lưu nguyên mã vào **VmIntrospectDemo.java**:

~~~java
public final class VmIntrospectDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "initial.demo.mode=" + System.getProperty("demo.mode", "unset")
        );

        System.setProperty("demo.mode", "runtime");

        System.out.println(
                "current.demo.mode=" + System.getProperty("demo.mode")
        );
        System.out.println("appArgCount=" + args.length);
        System.out.println("ready");

        Thread.sleep(120_000L);
    }
}
~~~

Biên dịch rồi chạy ở **Terminal 1**:

~~~bash
javac VmIntrospectDemo.java
java -Xms128m -Xmx256m -Ddemo.mode=startup VmIntrospectDemo alpha beta
~~~

**Stdout chính xác của ứng dụng trước khi ngủ:**

~~~text
initial.demo.mode=startup
current.demo.mode=runtime
appArgCount=2
ready
~~~

Sau đó main thread ngủ tối đa khoảng 120 giây (thực tế có thể bị đánh thức muộn). Nếu thử trong terminal tương tác, có thể kết thúc bằng Ctrl+C sau khi kiểm tra. Chú ý đây là chương trình thí nghiệm, **không phải server có giao diện HTTP**.

Trong **Terminal 2**, chạy khi tiến trình còn sống:

~~~bash
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
jcmd 12345 VM.info
~~~

**Thay `12345` bằng PID của process `VmIntrospectDemo` thật.** Nếu container không liệt kê được qua `jcmd -l`, cần lấy PID từ đúng môi trường process.

Đối chiếu có mục tiêu:

| Câu hỏi | Dấu hiệu mong đợi |
| --- | --- |
| Có truyền `-Ddemo.mode=startup` không? | `VM.command_line` thường có đối số JVM khởi động tương ứng |
| Giá trị property hiện tại là gì? | `VM.system_properties` có `demo.mode=runtime` do code đã sửa |
| `alpha beta` thuộc JVM flags hay app arguments? | Chúng là **hai đối số ứng dụng**, xuất hiện theo cách launcher thể hiện trong `java_command`, không phải VM flags |
| Có đặt `-Xms128m` và `-Xmx256m` không? | Startup chứa options; `VM.flags` có thể cho `InitialHeapSize` và `MaxHeapSize` hiệu lực |
| Thông tin VM/OS từ đâu? | `VM.info` cung cấp bối cảnh runtime và môi trường, phụ thuộc JVM |

**Không đưa ra stdout giả cho `jcmd`:** mỗi môi trường có PID, Java build, OS, classpath, danh mục flags và lượng memory khác nhau. Output ví dụ ở trên chỉ minh họa cấu trúc, các dòng chắc chắn được chương trình in là bốn dòng ứng dụng đã nêu.

### Bài tập tự kiểm tra

1. Bỏ `-Ddemo.mode=startup` rồi chạy lại: `initial.demo.mode=unset`, sau đó property bị thay thành `runtime`. Lần này `VM.command_line` không có `-Ddemo.mode=startup`, nhưng `VM.system_properties` vẫn có `demo.mode=runtime`.
2. Đổi `-Xmx256m` thành `-Xmx384m`: xem thay đổi ở `VM.command_line` và `MaxHeapSize` qua `VM.flags`. Không suy rằng RSS/cgroup memory bằng heap max.
3. Bỏ hai đối số `alpha beta`: `appArgCount=0`; điều này không có nghĩa JVM hết flags hoặc system properties.
4. Quan sát `VM.info` ở hai môi trường khác nhau; ghi rõ **những trường có mặt thực sự** trước khi so sánh, không tự giả định cùng schema output.

## 8. Quy trình đối chiếu cấu hình khi chẩn đoán sự cố

Một bản thu có giá trị hơn nếu trả lời “process nào, lúc nào, đang thấy gì và khác dự kiến ở đâu?”:

**Bước 1 — Chỉ rõ tiến trình đích.** Ghi service, pod/container, host, timestamp có timezone, PID tại namespace đang dùng, Java version/vendor, deployment revision. PID có thể được OS tái sử dụng sau restart, nên cần liên hệ tới thời điểm start.

**Bước 2 — Lưu dấu vết startup.** Thu `VM.command_line` để kiểm tra JVM options, agent, class/JAR và application arguments. So với deployment manifest/entrypoint đã triển khai thực tế, không chỉ file cấu hình nguồn.

**Bước 3 — Lưu giá trị flags.** Thu `VM.flags`; dùng `VM.flags -all` khi cần xác định cờ vắng mặt trong bản ngắn. Với nghi vấn heap/GC, đối chiếu `InitialHeapSize`, `MaxHeapSize`, GC choice và dấu chỉ ra nguồn giá trị nếu có.

**Bước 4 — Kiểm tra system properties.** Thu `VM.system_properties` và chỉ so sánh các key có liên quan sau khi lọc bí mật. Nếu runtime property khác `-D`, điều tra code đã gọi `System.setProperty`, initialization libraries hoặc cấu hình framework.

**Bước 5 — Gắn môi trường thực thi.** Thu `VM.info` và số liệu OS/container nếu cần. Ví dụ hai pod có cùng `-Xmx` nhưng memory limit/CPU quota khác vẫn có thể hành xử khác nhau. `VM.info` hỗ trợ diễn giải, không thay thế dữ liệu cgroup hoặc metric sát thời điểm sự cố.

**Bước 6 — Lập bảng expected/actual.** Tránh ghi “JVM sai cấu hình” chung chung. Ví dụ:

| Khoản cần xác minh | Dự kiến từ deployment | Thực tế từ process | Kết luận có thể kiểm chứng |
| --- | --- | --- | --- |
| Heap tối đa | `-Xmx512m` | `VM.command_line` thấy `-Xmx256m`; `VM.flags` báo heap max tương ứng | Bản khởi động thực tế khác cấu hình mong đợi; truy entrypoint/override |
| Property ứng dụng | `-Dapp.mode=prod` | Startup là `prod` nhưng live property là `test` | Có khả năng thay đổi sau startup; tìm nguồn mutation |
| Java runtime | JDK 17 build đã duyệt | VM.info cho thấy vendor/build khác | Kiểm tra image digest/JDK đóng gói trước khi quy bug cho application |

Những giá trị trên **chỉ minh họa cách ghi**, không phải số liệu lấy từ một JVM cụ thể. Cần lưu output cùng mốc thời gian và không đưa chuỗi bí mật vào báo cáo.

### Trường hợp khó: VM.flags không giống command line

Không phải mọi khác biệt đều là lỗi:
- `-Xmx` được ánh xạ thành tên flag nội bộ và có thể có điều chỉnh theo alignment.
- Một số flags được chọn **ergonomically** thay vì xuất hiện trong startup command.
- `-XX:MaxRAMPercentage` cùng CPU/memory limit ảnh hưởng đến quyết định tự tính heap khi không có override liên quan.
- Một số flag hỗ trợ thay đổi ở runtime, nên giá trị hiện tại có thể khác đầu vào lúc start; cần xác nhận cách chỉnh thay vì suy từ output duy nhất.
- Khác vendor/JDK version có thể thay đổi flags được hỗ trợ và cơ chế default.

Muốn chứng minh “cấu hình deploy bị override”, kết hợp startup arguments, giá trị hiệu lực, nguồn đặt flag (nếu JVM hiển thị) và cấu hình container/launcher; không suy chỉ từ một dòng.

## 9. Khi jcmd thất bại hoặc output thiếu

| Hiện tượng | Khả năng cần xem | Hành động tiếp theo |
| --- | --- | --- |
| `jcmd -l` không thấy process | PID namespace/container khác; JVM không được discover | Tìm PID qua process tool đúng namespace; không quét all-process |
| `Could not attach` / permission denied | User/group khác, attach disabled, thư mục tạm hoặc môi trường hạn chế | Kiểm tra quyền và cơ chế attach; chạy công cụ ở môi trường phù hợp |
| PID có lúc tồn tại, lúc không | Process restart/crash/exit, PID được tái sử dụng | Kiểm tra timestamp, start time, logs và container events |
| `Unknown diagnostic command` | Vendor/JDK không hỗ trợ hoặc tên lệnh khác | Dùng `jcmd <pid> help` đúng JVM, không đoán option |
| `VM.flags` thiếu flag muốn xem | Bản mặc định chỉ liệt kê nhóm hạn chế | Thử `VM.flags -all` nếu target hỗ trợ, đối chiếu `help` |
| `VM.system_properties` không có env variable | OS env không phải Java property | Dùng công cụ env/container thích hợp và logic đọc config |
| Output quá nhiều hoặc có bí mật | Command/info/property chứa dữ liệu vận hành nhạy cảm | Giới hạn phạm vi, lưu nội bộ, redact trước khi chia sẻ |
| Số liệu hai lần khác nhau | Process đã restart, runtime đã đổi, hoặc đo sai thời điểm | Xác nhận PID + start time, version, timestamp và truy thay đổi |

**Không sửa cấu hình chỉ vì thấy một dòng không mong đợi.** Trước tiên xác minh mục đích và nguồn của giá trị, phiên bản JVM, cách khởi chạy, container limit và baseline. Bốn lệnh đang học là công cụ kiểm chứng trạng thái; muốn phân tích CPU hotspot, memory leak hay deadlock cần chứng cứ chuyên biệt.

## 10. Lỗi thường gặp và cách tránh

- **Gọi `VM.command_line` là “cấu hình hiện tại của ứng dụng”.** Nó phản ánh startup command theo cách VM giữ lại; framework và runtime có thể đổi config sau đó.
- **Lẫn `-D` với `-XX`.** `-Dkey=value` tạo Java system property, còn `-XX:...` đặt VM flag; chúng khác hệ thống.
- **Lẫn args sau main class với JVM flags.** `java -Xmx256m App one two` có `one two` là đối số `main`, không phải JVM option.
- **Thấy `VM.flags` ngắn rồi kết luận thiếu cờ.** Hỏi `VM.flags -all` và xem nguồn giá trị nếu cần.
- **Nhầm số heap với bộ nhớ process/container.** `MaxHeapSize` không bao gồm toàn bộ memory footprint.
- **Nhầm Java properties với environment.** `System.getProperty` và `System.getenv` có nguồn và cách quản lý khác nhau.
- **Đọc mọi output như một schema cố định.** Section, flag và tên field của `VM.info` hoặc `VM.flags -all` thay đổi theo JDK/vendor.
- **Đọc PID sai namespace.** Khi JVM chạy trong container, PID trên host và trong container khác nhau; phải gắn evidence với process cụ thể.
- **Gọi command vào process đã restart.** PID có thể thay đổi hoặc tái sử dụng; cần timestamp và start time.
- **Coi snapshot là nguyên nhân gốc.** Nó cho biết trạng thái, còn quan hệ nhân quả phải được chứng minh bằng timeline, metrics, logs và deployment events.
- **Đưa secrets vào command line/properties rồi chia sẻ dump nguyên văn.** Phải xử lý dữ liệu nhạy cảm và hạn chế quyền truy cập.
- **Dùng lệnh khác để “xác minh nhanh” nhưng thay đổi trạng thái.** `VM.set_flag` hoặc các command chủ động tác động VM là việc khác với bốn lệnh quan sát ở đây.

## 11. Checklist tóm tắt khi bàn giao sự cố

Một báo cáo về process Java nên có:

1. **Identity:** service, PID, host/container, thời điểm quan sát và phiên bản JDK.
2. **Startup:** các JVM/application arguments có liên quan từ `VM.command_line`.
3. **Effective VM settings:** các flags quan trọng và giá trị thực từ `VM.flags` hoặc `VM.flags -all`.
4. **Current Java properties:** key liên quan trong `VM.system_properties`, có xác minh khác biệt với startup và đã lọc bí mật.
5. **Environment/status:** các trường thực có từ `VM.info`, kết hợp OS/container metrics nếu giả thuyết cần.
6. **Expected vs actual:** nguồn cấu hình dự kiến và bằng chứng thực tế, thời điểm thay đổi có thể có.
7. **Điều chưa biết:** không phỏng đoán bản chất override hoặc nguyên nhân sự cố chỉ từ một snapshot.

**Ghi nhớ:** `VM.command_line` nhìn vào **đầu vào khởi động**; `VM.flags` cho biết **giá trị flag JVM có hiệu lực**; `VM.system_properties` là **ảnh chụp Java properties hiện tại**; `VM.info` cung cấp **bối cảnh tổng hợp về môi trường và tình trạng JVM**. Đọc bốn lớp trên **cùng một PID, cùng khoảng thời gian, cùng JDK** để tránh ghép nhầm chứng cứ.

**Tài liệu đối chiếu:** Oracle JDK 17, *The jcmd Command*, https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html. Dùng `jcmd <pid> help <command>` để xác nhận cú pháp và flags thực tế trên JVM đang điều tra.