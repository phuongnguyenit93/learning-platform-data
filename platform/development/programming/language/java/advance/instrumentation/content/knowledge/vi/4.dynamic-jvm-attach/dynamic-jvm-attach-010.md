# Cảnh báo nạp agent động, `EnableDynamicAgentLoading` và chính sách theo phiên bản JDK

> **Ngữ cảnh:** Java Advance → Instrumentation → Attach vào JVM. Nội dung tập trung vào agent nạp **sau khi JVM đã khởi động** trên HotSpot/OpenJDK, cách đọc cảnh báo JEP 451, cách kiểm chứng các cờ JVM và chiến lược chuẩn bị cho những bản JDK tiếp theo. Thông tin phiên bản được đối chiếu đến **31/10/2026**; các nhà cung cấp JVM có thể có chính sách hoặc triển khai attach riêng.

## 1. Cần phân biệt ba thời điểm và ba thao tác

Agent là mã chạy trong JVM, có thể sử dụng API `java.lang.instrument` hoặc JVM Tool Interface (JVM TI) để quan sát hay biến đổi việc thực thi. **Không phải mọi kết nối tới JVM đang chạy đều là nạp agent.**

| Cách kích hoạt | Entry point điển hình | Xảy ra khi nào? | Có thuộc phạm vi cảnh báo JEP 451? |
|---|---|---|---|
| Startup Java agent: `java -javaagent:agent.jar ...` | `premain(String, Instrumentation)`; manifest `Premain-Class` | Khi khởi chạy JVM, trước `main` của ứng dụng | **Không**: cảnh báo nạp động không áp dụng cho agent được khai báo lúc startup |
| Dynamic Java agent: `VirtualMachine.loadAgent(...)`, thường qua Attach API | `agentmain(String, Instrumentation)`; manifest `Agent-Class` | Sau khi JVM mục tiêu đã chạy | **Có** khi JVM triển khai chính sách cảnh báo và nạp động chưa được opt-in |
| Attach để chẩn đoán: đọc thuộc tính/heap/thread hoặc gọi lệnh hỗ trợ | Không nhất thiết có `agentmain` hay agent JAR | JVM đã chạy | **Không tự động**: attach, diagnostic command và *agent loading* là các thao tác khác nhau |

Ví dụ, một công cụ có thể dùng Attach API để đọc thông tin hệ thống mà không gọi `loadAgent`. Cờ `-XX:-EnableDynamicAgentLoading` chặn **khả năng nạp agent động**, không có nghĩa toàn bộ tính năng attach hoặc mọi lệnh `jcmd` đều bị tắt. Ngược lại, `-XX:+DisableAttachMechanism` (HotSpot) nhắm đến việc vô hiệu hóa **cơ chế attach** và có phạm vi rộng hơn.

JEP 451 được thúc đẩy bởi nguyên tắc **integrity by default**: code có quyền sửa đổi hành vi của một JVM đang chạy cần nhận được sự chấp thuận rõ ràng từ người vận hành. Công cụ profiler, debugger và kiểm thử có trường hợp sử dụng hợp lệ; tuy nhiên thư viện tự attach agent vào tiến trình của ứng dụng có thể thực thi code đặc quyền mà người vận hành không ý thức được.

## 2. Lịch sử phiên bản: điều đã thay đổi và điều mới được dự kiến

**JEP 451 — Prepare to Disallow the Dynamic Loading of Agents** được đưa vào **JDK 21 (2023)**. Tên JEP nói về việc *chuẩn bị* chuyển chính sách: JDK 21 không đồng nghĩa với việc mọi attach bị khóa. Nạp động vẫn được cho phép trong cấu hình mặc định HotSpot, nhưng JVM cảnh báo khi một agent được nạp vào tiến trình đang chạy nếu chủ tiến trình chưa opt-in rõ ràng.

| Phiên bản / giai đoạn | HotSpot và cảnh báo JEP 451 | `EnableDynamicAgentLoading` | Điều không nên suy diễn |
|---|---|---|---|
| JDK 8 | Có các cơ chế agent/attach phụ thuộc triển khai; **chưa có cảnh báo JEP 451** | Không lấy cú pháp/cấu hình HotSpot JDK mới làm cam kết cho Java 8 | Đừng nghĩ không cảnh báo nghĩa là agent không chạy |
| JDK 9–20, gồm JDK 17 | Dynamic agent loading **được bật mặc định**, chưa có cảnh báo JEP 451 | Cờ `-XX:[+|-]EnableDynamicAgentLoading` được hỗ trợ trong HotSpot từ JDK 9 | Đừng cho rằng runtime “an toàn hơn” chỉ vì im lặng |
| JDK 21 | Dynamic loading **vẫn bật mặc định**, nhưng phát cảnh báo khi nạp agent động nếu chưa opt-in | `+`: cho phép và bỏ cảnh báo; `-`: từ chối nạp động | **Cảnh báo không phải lỗi và cũng không chứng minh đã sửa bytecode** |
| JDK 22–27 (đối chiếu đến 31/10/2026) | Chính sách cảnh báo/opt-in của JEP 451 vẫn là điểm cần kiểm tra khi nâng phiên bản; không xác định rằng tất cả agent đã bị chặn mặc định | Dùng cờ `+`/`-` trên **JVM đích** và kiểm tra trạng thái thực tế của vendor/build | Không tự gán một phiên bản cụ thể là mốc đã “đổi mặc định” chỉ dựa vào thông báo cảnh báo |
| Bản JDK tương lai nếu chuyển chính sách | Dự kiến **không cho nạp agent động theo mặc định**, trừ khi người vận hành cho phép | `-XX:+EnableDynamicAgentLoading` là opt-in đã được chuẩn bị trước | Thông điệp “future release” **không công bố một số phiên bản cam kết** |

Đây là bảng dành cho **HotSpot/OpenJDK** và những phiên bản đã nêu. Một runtime khác (ví dụ OpenJ9), một bản dựng tùy chỉnh, hoặc bản cập nhật của vendor có thể có chi tiết cảnh báo và mặc định khác. Khi cần chắc chắn, hãy kiểm tra **JVM thực sự chạy ứng dụng**, thay vì chỉ nhìn JDK dùng để build.

Tính đến mốc cập nhật của bài, JDK 27 đã được phát hành tháng 9/2026; không được đọc lời cảnh báo từ JDK 21 rồi khẳng định “JDK 27 chắc chắn chặn agent động mặc định” khi chưa kiểm tra release notes và flag của chính bản dựng đó. Tương tự, không cam kết rằng “đến JDK 28 mới thay đổi” nếu chưa có thông báo chính thức. Hãy xem đây là **khả năng phải chuẩn bị và kiểm thử**, không phải một ngày triển khai đã cố định.

## 3. Đọc cảnh báo cho đúng

Trên HotSpot JDK 21 trở lên, khi tiến trình đang chạy được yêu cầu nạp Java agent động mà chưa có opt-in, stderr thường có nhóm dòng bắt đầu bằng nội dung như:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
...
WARNING: Dynamic loading of agents will be disallowed by default in a future release
~~~

Các dòng giữa có thể hướng dẫn dùng `-XX:+EnableDynamicAgentLoading` để xác nhận quyền nạp động hoặc `-Djdk.instrument.traceUsage` để hỗ trợ chẩn đoán. Đường dẫn JAR, số lần in và định dạng có thể thay đổi theo JDK, vendor và việc agent đã được nạp trước đó. **Đừng so khớp toàn bộ cảnh báo như một chuỗi bất biến trong bài test.**

Ý nghĩa:

1. **Sự kiện:** JVM đã thấy yêu cầu nạp một agent vào tiến trình đang chạy. Với cảnh báo điển hình, tải agent đang được cho phép; đây **không tự nó** là lỗi.
2. **Rủi ro tương lai:** việc phụ thuộc vào nạp động mặc định có thể không còn hoạt động ở một bản JVM sau này.
3. **Quyền quyết định:** người chạy JVM phải chủ động cho phép nếu thật sự cần khả năng này. Chỉ thay đổi log level của ứng dụng sẽ không giải quyết nguyên nhân, vì cảnh báo đến từ JVM và thường ghi ở **stderr**.

Ví dụ: một bộ test dùng công cụ mock hoặc bytecode instrumentation có thể vẫn **PASS**, đồng thời JVM in cảnh báo. Không được giải quyết bằng cách xóa log mà không nhận diện ai đã yêu cầu nạp agent. Trên môi trường có nhiều JVM (IDE, Gradle daemon, Gradle Test worker, Maven Surefire fork, app server), cần tìm **đúng PID và đúng JVM đích**.

## 4. Ba cờ quan trọng và phạm vi áp dụng

### `-XX:+EnableDynamicAgentLoading` — cho phép chủ động

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Với HotSpot có JEP 451, đây là tín hiệu **opt-in** từ khi khởi chạy: cho phép nạp agent động và không phát nhóm cảnh báo JEP 451 khi agent được nạp. Cờ phải có trên **command line của JVM mục tiêu lúc nó khởi động**, không phải chỉ thêm cho công cụ Attach ở tiến trình khác. Không thể trông chờ đổi `-XX` flag của một JVM đang chạy bằng cách thêm nó vào lệnh `java` chạy client.

Cờ không cấp quyền hệ điều hành, không mở khóa mọi cơ chế attach bị giới hạn và không sửa một JAR agent lỗi. Nó cũng **không** làm agent tự xuất hiện: vẫn phải có yêu cầu nạp agent thực tế.

### `-XX:-EnableDynamicAgentLoading` — kiểm tra chính sách chặn

~~~bash
java -XX:-EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Cách này mô phỏng điều kiện **không cho phép tải agent động** của chính sách tương lai. Với một lời gọi `VirtualMachine.loadAgent(...)`, thường bạn sẽ nhận lỗi nạp agent ở công cụ yêu cầu thay vì gọi được `agentmain` trong JVM đích. Tên exception và thông điệp chi tiết là triển khai cụ thể; chẳng hạn client có thể nhận `AgentLoadException`. **Không khẳng định JVM đích sẽ chết**: tiến trình ứng dụng thường tiếp tục hoạt động.

Điểm cần phân biệt: dù `-XX:-EnableDynamicAgentLoading` đang bật, Java agent được chỉ định khi **startup** bằng `-javaagent` vẫn không bị chính cờ này cấm. Đây là cách hữu ích để kiểm chứng một thư viện có thể chuyển sang khởi động cùng ứng dụng hay không.

### `-Djdk.instrument.traceUsage=true` — truy vết cách dùng Instrumentation

~~~bash
java -Djdk.instrument.traceUsage=true -cp out/app demo.app.TargetApp
~~~

Thuộc tính hệ thống này yêu cầu in trace/stack trace của các thao tác sử dụng `java.lang.instrument` để hỗ trợ lần theo tác nhân đang instrument code. Đây **không phải** cờ cho phép nạp agent và cũng không phải cơ chế chắc chắn liệt kê mọi sự kiện Attach. Trong ví dụ thực hành bên dưới, agent chỉ in một dòng mà không gọi phương thức của đối tượng `Instrumentation`, vì thế **không có gì bảo đảm sẽ phát thêm stack trace**. Khi một thư viện thực sự gọi các API Instrumentation, thông tin này hữu ích hơn.

### Những cờ dễ bị nhầm

| Cờ / thuộc tính | Ý nghĩa chính | Có thay thế opt-in nạp agent động? |
|---|---|---|
| `-javaagent:...` | Tải Java agent **lúc khởi động** (`premain`) | Không cần opt-in nạp động; đây là đường startup khác |
| `-XX:+EnableDynamicAgentLoading` | Cho phép chủ tiến trình chấp thuận nạp agent động | **Có**, đối với tính năng này trên HotSpot |
| `-XX:-EnableDynamicAgentLoading` | Từ chối nạp agent động sau startup | Không; nó cố ý chặn |
| `-XX:+DisableAttachMechanism` | Vô hiệu hóa cơ chế attach HotSpot, có thể ảnh hưởng nhiều công cụ chẩn đoán | Không; còn có thể chặn yêu cầu attach từ đầu |
| `-Djdk.attach.allowAttachSelf=true` | Trên các JDK có hỗ trợ, thay đổi hạn chế **self-attach** trong cùng tiến trình | **Không**: self-attach và quyền nạp agent động là hai kiểm soát khác nhau |
| `-Djdk.instrument.traceUsage=true` | Truy vết cách dùng Instrumentation | **Không**, chỉ là công cụ tìm nguyên nhân |

Không có sự tương đương giữa “attach thành công” và “loadAgent thành công”. Trong chế độ từ chối nạp động, một số thao tác attach dùng để chẩn đoán vẫn có thể tiếp tục hoạt động.

## 5. Thực hành Java 17+: quan sát cả `premain` và `agentmain`

Thí nghiệm tạo một agent **không biến đổi bytecode**, một ứng dụng làm JVM đích và một chương trình Attach riêng. Dùng **hai cửa sổ terminal** cho hai tiến trình để biết cảnh báo nằm ở đâu. Mẫu biên dịch với JDK 17+; **để thực sự quan sát cảnh báo JEP 451, phải chạy JVM đích bằng JDK 21 trở lên**.

### Cấu trúc thư mục

~~~text
dynamic-agent-policy/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   └── PolicyAgent.java
│       ├── app/
│       │   └── TargetApp.java
│       └── attach/
│           └── LoadAgent.java
└── out/
    ├── agent/
    ├── app/
    ├── attach/
    └── policy-agent.jar
~~~

Tạo các file trong thư mục gốc `dynamic-agent-policy/`; `out/` được sinh khi build. Không yêu cầu Spring, Maven, Gradle hay thư viện bên ngoài.

### File `src/demo/agent/PolicyAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class PolicyAgent {
    private PolicyAgent() {}

    public static void premain(String args, Instrumentation inst) {
        System.out.println("[AGENT] premain args=" + args);
    }

    public static void agentmain(String args, Instrumentation inst) {
        System.out.println("[AGENT] agentmain args=" + args);
    }
}
~~~

Một agent JAR **có thể hỗ trợ cả hai kiểu khởi chạy**, nhưng entry point sử dụng tùy thuộc cách kích hoạt. `-javaagent` gọi `premain`; Attach API `loadAgent` gọi `agentmain`. Trong mẫu này, cả hai phương thức chỉ in thông điệp để quan sát, không gọi `addTransformer` hoặc thay đổi class.

### File `src/demo/app/TargetApp.java`

~~~java
package demo.app;

public final class TargetApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[TARGET] pid=" + ProcessHandle.current().pid());
        System.out.println("[TARGET] ready; press Enter to exit");
        System.in.read();
        System.out.println("[TARGET] bye");
    }
}
~~~

Ứng dụng in PID của tiến trình hiện tại và chờ nhập Enter để bạn có thể attach từ một terminal khác. Phải chạy trong **terminal tương tác** giữ stdin mở; nếu stdin đang đóng/EOF (ví dụ một số CI runner), nó có thể thoát ngay sau khi in. PID sẽ khác giữa các lần chạy.

### File `src/demo/attach/LoadAgent.java`

~~~java
package demo.attach;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class LoadAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: LoadAgent <pid> <agent-jar>");
            System.exit(2);
        }

        String pid = args[0];
        String jar = Path.of(args[1]).toAbsolutePath().normalize().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(jar, "probe");
            System.out.println("[ATTACH] loadAgent completed");
        } finally {
            vm.detach();
        }
    }
}
~~~

Mã dùng module **`jdk.attach`**, được JDK cung cấp từ Java 9; đây là JDK-specific API, không có nghĩa mọi JVM/runtime image đều hỗ trợ. `VirtualMachine.attach(pid)` kết nối đến JVM đích; `vm.loadAgent(jar, "probe")` yêu cầu JVM đích nạp JAR và gọi `agentmain`. `detach()` giải phóng kết nối trong mọi trường hợp. Mẫu **không** attach chính tiến trình client nên không cần bật quyền self-attach.

### File `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PolicyAgent
Agent-Class: demo.agent.PolicyAgent

~~~

Manifest của **agent JAR** có cả `Premain-Class` và `Agent-Class`. Đó là hai thuộc tính khác nhau. Nếu chỉ có `Premain-Class`, bạn không thể dùng cùng JAR cho `VirtualMachine.loadAgent` theo đúng hợp đồng Java Instrumentation. Hãy đảm bảo manifest có newline cuối file; công cụ `jar` sẽ đưa nó vào `META-INF/MANIFEST.MF`.

### Biên dịch và đóng gói

macOS/Linux (Bash):

~~~bash
mkdir -p out/agent out/app out/attach

javac --release 17 -d out/agent src/demo/agent/PolicyAgent.java
javac --release 17 -d out/app src/demo/app/TargetApp.java
javac --add-modules jdk.attach -d out/attach src/demo/attach/LoadAgent.java

jar --create --file out/policy-agent.jar --manifest manifest.mf -C out/agent .
jar --list --file out/policy-agent.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app, out/attach | Out-Null

javac --release 17 -d out/agent src/demo/agent/PolicyAgent.java
javac --release 17 -d out/app src/demo/app/TargetApp.java
javac --add-modules jdk.attach -d out/attach src/demo/attach/LoadAgent.java

jar --create --file out/policy-agent.jar --manifest manifest.mf -C out/agent .
jar --list --file out/policy-agent.jar
~~~

Dùng `--release 17` cho agent và ứng dụng để có class file chạy trên JDK 17 trở lên; compiler cho client dùng JDK đang cài và module `jdk.attach`. Khi dùng nhiều JDK trên máy, nên chọn **cùng vendor/JDK chính và kiến trúc tương thích** cho cả client lẫn JVM đích để tránh lỗi Attach API không liên quan đến JEP 451.

Lệnh liệt kê JAR phải bao gồm `META-INF/MANIFEST.MF` và `demo/agent/PolicyAgent.class`. Nếu sai package hoặc tên agent class, lỗi xảy ra **trước** khi nhận được các mốc mong muốn.

## 6. Bốn kịch bản thực nghiệm

### Trường hợp A — nạp động trên HotSpot JDK 21+ với mặc định cảnh báo

**Terminal A:** đứng tại thư mục gốc dự án, chạy JVM mục tiêu:

~~~bash
java -cp out/app demo.app.TargetApp
~~~

Các dòng đầu dự kiến ở terminal A:

~~~text
[TARGET] pid=12345
[TARGET] ready; press Enter to exit
~~~

`12345` chỉ là **PID ví dụ**, hãy dùng **PID thực tế** in ra trong lần chạy của bạn. Giữ terminal A đang chờ Enter.

**Terminal B:** cùng thư mục dự án, thay `12345` bằng PID đó:

~~~bash
java --add-modules jdk.attach -cp out/attach demo.attach.LoadAgent 12345 out/policy-agent.jar
~~~

Với quyền attach hợp lệ và dynamic loading đang được cho phép, client dự kiến in:

~~~text
[ATTACH] loadAgent completed
~~~

Trong **terminal A của JVM đích**, bạn sẽ thấy dòng:

~~~text
[AGENT] agentmain args=probe
~~~

Và trên **stderr của JVM đích** có thể có nhóm cảnh báo JEP 451 (dùng chữ `WARNING`). Thứ tự *gộp* giữa stdout/stderr không được bảo đảm tuyệt đối vì chúng là hai luồng đầu ra. Điều cần đối chiếu là: `agentmain` chạy **sau khi app đã vào `main`**, và cảnh báo không đồng nghĩa lệnh đã thất bại.

### Trường hợp B — opt-in ngay từ đầu: `-XX:+EnableDynamicAgentLoading`

Dừng JVM đích ở terminal A bằng Enter, rồi chạy lại:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Terminal B gọi lại `LoadAgent` với **PID mới**. Kết quả mong đợi: vẫn có `[AGENT] agentmain args=probe` tại JVM đích và `[ATTACH] loadAgent completed` phía client, nhưng **không có nhóm cảnh báo JEP 451** do thiếu opt-in. Log khác của ứng dụng vẫn có thể xuất hiện.

**Lý do:** cờ `+` không chặn attach; nó xác nhận chủ tiến trình cho phép load agent động. Đặt cờ vào **terminal B** mà không đặt ở **terminal A** không giải quyết cảnh báo của JVM mục tiêu.

### Trường hợp C — chặn nạp động: `-XX:-EnableDynamicAgentLoading`

Dừng JVM đích, chạy lại terminal A:

~~~bash
java -XX:-EnableDynamicAgentLoading -cp out/app demo.app.TargetApp
~~~

Terminal B chạy lệnh Attach với PID mới. Kết quả kỳ vọng:

- Phần kết nối attach có thể vẫn thành công.
- Yêu cầu `loadAgent` **bị từ chối**; client có exception (thường thuộc nhóm `AgentLoadException`) và **không** in `[ATTACH] loadAgent completed`.
- JVM đích không thực thi `PolicyAgent.agentmain` nên không có dòng `[AGENT] agentmain args=probe` từ lần yêu cầu bị chặn.
- Chương trình `TargetApp` vẫn có thể chờ Enter và thoát bình thường; không nên kết luận “JVM crash”.

Thông điệp lỗi chi tiết có thể khác theo phiên bản, vendor và cách attach. Không hard-code nguyên văn error text vào test; kiểm tra **có/không callback, lệnh thành công hay lỗi và flag của JVM đích**.

### Trường hợp D — startup agent vẫn chạy dù cấm nạp động

Đây là phép thử so sánh rất quan trọng. Chạy ở terminal A:

~~~bash
java -XX:-EnableDynamicAgentLoading -javaagent:out/policy-agent.jar=boot -cp out/app demo.app.TargetApp
~~~

Các dòng đầu dự kiến theo thứ tự:

~~~text
[AGENT] premain args=boot
[TARGET] pid=12345
[TARGET] ready; press Enter to exit
~~~

Một lần nữa, PID chỉ là **ví dụ**. Không xuất hiện cảnh báo nạp **động** JEP 451 vì agent đã được yêu cầu trong command line startup. Cờ `-XX:-EnableDynamicAgentLoading` kiểm soát nạp **sau khi JVM chạy**, nên tự nó không cấm `-javaagent`. Nếu tiếp tục gửi yêu cầu `loadAgent` từ terminal B vào JVM này, yêu cầu **nạp thêm** có thể bị từ chối như trường hợp C.

### Tóm tắt kết quả mong đợi

| Cách chạy **JVM đích** | `premain` | `agentmain` khi client yêu cầu | Cảnh báo JEP 451 từ lần nạp động | Kết quả tải động |
|---|---:|---:|---|---|
| Không agent, không flag (HotSpot JDK 21+) | Không | Có | Có, thông thường | Cho phép theo mặc định hiện hành |
| `-XX:+EnableDynamicAgentLoading` | Không | Có | Không vì đã opt-in | Cho phép |
| `-XX:-EnableDynamicAgentLoading` | Không | Không | Không có cảnh báo “đã nạp thành công” cho agent bị chặn | Bị từ chối |
| `-XX:-EnableDynamicAgentLoading -javaagent:...` | Có | Không nếu tiếp tục thử load động | Không cho agent startup | Startup thành công, nạp động vẫn bị chặn |

Giữ cố định **agent JAR**, JVM đích, quyền attach và client qua bốn lượt, chỉ đổi cờ. Mỗi lượt dùng **PID mới**, vì mỗi lần gọi `java` sinh một JVM mới.

## 7. Chẩn đoán khi gặp cảnh báo trong dự án thật

### Bước 1: xác nhận phiên bản và JVM thực sự phát cảnh báo

~~~bash
java -version
java -XX:+PrintFlagsFinal -version 2>&1 | grep EnableDynamicAgentLoading
~~~

Trên PowerShell thay bộ lọc bằng:

~~~powershell
java -version
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String EnableDynamicAgentLoading
~~~

`PrintFlagsFinal` cho biết trạng thái cờ của **JVM đang chạy câu lệnh đó**, không tự động phản ánh một JVM ứng dụng khác đã khởi động từ IDE/service. Muốn biết runtime thực tế, kiểm tra command line và version của **PID đích**, cấu hình process manager/IDE/container, và các cờ được truyền cho đúng Java process.

Trong hệ sinh thái build, hãy phân biệt JVM điều khiển **Gradle daemon** với JVM chạy **Gradle Test worker**, hoặc JVM **Maven launcher** với **Surefire fork**. Agent có thể nằm trong JVM test dù daemon không hiển thị cảnh báo.

### Bước 2: tìm ai đang nạp agent

Các nguồn thường gặp là công cụ kiểm thử cần instrument class, mocking inline, profiling, monitoring, bytecode weaving, hoặc thư viện gọi self-attach khi ứng dụng chạy. Kiểm tra dependency/configuration của tool, startup script và log được in ở JVM đích; dùng `-Djdk.instrument.traceUsage=true` **trên JVM đích** để truy vết những lời gọi API Instrumentation khi có hoạt động liên quan.

Không phải mọi thông điệp chứa từ `agent` đều thuộc JEP 451. Nếu lỗi chính là `AttachNotSupportedException`, không tìm thấy PID hoặc permission denied thì phải xử lý **kết nối attach** trước. Nếu đã attach nhưng `Agent-Class` bị thiếu, phải sửa **manifest**. Nếu lỗi nói dynamic loading bị từ chối, hãy kiểm tra `-XX:-EnableDynamicAgentLoading` và chính sách runtime.

### Bước 3: ưu tiên agent lúc khởi động khi có thể

Nếu thư viện/tool hỗ trợ đặt agent khi JVM khởi chạy, chuyển sang `-javaagent:<đường-dẫn-JAR>` với `Premain-Class` thích hợp. Điều này minh bạch quyền can thiệp của agent, dễ audit và không bị ảnh hưởng bởi thay đổi mặc định của **dynamic** loading. **Không phải mọi JAR vốn được load qua `agentmain` đều sẵn có `premain`**: phải xem manifest và tài liệu của chính công cụ.

Ví dụ cấu hình cho JVM chạy **task test của Gradle** (Groovy DSL):

~~~groovy
tasks.withType(Test).configureEach {
    // Chẩn đoán: thử policy từ chối nạp động.
    jvmArgs '-XX:-EnableDynamicAgentLoading'
}
~~~

Nếu test thất bại do dependency thực sự cần attach, có thể tạm thời opt-in trên đúng JVM test:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '-XX:+EnableDynamicAgentLoading'
}
~~~

Đây là **hai cấu hình thay thế nhau**, không khai báo cùng lúc. Cấu hình `-XX:+...` giúp test tiếp tục chạy theo cơ chế nạp động nhưng chưa giải quyết phụ thuộc vào attach. Để bỏ phụ thuộc đó, xem hướng dẫn chính thức của library về cung cấp `-javaagent` cho JVM test; các phiên bản library khác nhau có thể đòi hỏi JAR và tham số khác nhau.

Ví dụ với Maven Surefire: cấu hình `<argLine>` cho **forked test JVM** nếu cần kiểm thử bằng `-XX:-EnableDynamicAgentLoading`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-XX:-EnableDynamicAgentLoading</argLine>
  </configuration>
</plugin>
~~~

Khi dự án đã có `argLine` do JaCoCo hoặc cấu hình kiểm thử khác tạo ra, **phải hợp nhất** các tham số theo hướng dẫn của plugin, không ghi đè mù quáng. Mẫu trên chỉ minh họa ý nghĩa của flag, không phải cấu hình hoàn chỉnh cho mọi dự án.

### Bước 4: xác nhận nhu cầu sử dụng trong triển khai

Nếu cần dynamic attach cho profiler/debugger trong production, hãy ghi nhận việc bật `-XX:+EnableDynamicAgentLoading` như quyết định của người vận hành JVM, kiểm soát quyền tài khoản và nguồn gốc agent JAR. Nếu không cần, chạy thử với `-XX:-EnableDynamicAgentLoading` ở staging/CI để phát hiện self-attach ẩn trước khi cập nhật JDK. Không coi một cảnh báo im lặng là bằng chứng mọi agent đều an toàn.

## 8. Những nhầm lẫn phổ biến

**“JDK 21 trở lên đã cấm attach.”** Sai. JEP 451 bổ sung cảnh báo khi nạp agent động; attach và loadAgent là hai khả năng riêng. Cần kiểm tra build/JVM cụ thể.

**“Cảnh báo làm test fail.”** Không tự nó; có thể là cảnh báo trên stderr trong khi test vẫn PASS. Test thất bại thường do exception khác, chính sách đã đặt `-XX:-EnableDynamicAgentLoading`, hoặc công cụ phân loại cảnh báo là lỗi.

**“Chỉ cần thêm `-XX:+EnableDynamicAgentLoading` vào lệnh chạy client attach.”** Sai. Cờ phải được đặt cho **tiến trình JVM nhận agent** khi tiến trình đó khởi động.

**“`-Djdk.instrument.traceUsage` là cách tắt cảnh báo.”** Sai. Đây là cách hỗ trợ truy vết API instrumentation; opt-in HotSpot dùng `-XX:+EnableDynamicAgentLoading`.

**“`-javaagent` và `VirtualMachine.loadAgent` cùng gọi `premain`.”** Sai. Startup đi qua `premain`, dynamic đi qua `agentmain`. Nếu muốn một JAR hỗ trợ cả hai, phải có đủ entry point và manifest attributes tương ứng.

**“Bật `-XX:+EnableDynamicAgentLoading` thì đã bật khả năng tự attach cho mọi process.”** Sai. OS permissions, attach provider, security policy, loại runtime image và giới hạn self-attach vẫn có thể cản trở. Opt-in nạp động không phải là cách bypass các quyền đó.

**“Nhìn dòng WARNING có chữ future release là biết đúng JDK nào sẽ cấm.”** Sai. Đó là thông báo chuẩn bị. Hãy đọc thông báo phát hành của runtime đang dùng, xác nhận mặc định bằng cách thử cờ `-XX:-EnableDynamicAgentLoading` và kiểm tra lại khi cập nhật phiên bản.

## 9. Câu hỏi tự kiểm tra

1. **JDK 21, không truyền cờ, một agent được nạp qua Attach API: có thể có cảnh báo mà agent vẫn chạy không?** Có. Trong HotSpot mặc định của JEP 451, nạp động còn được phép, cảnh báo chỉ nhắc thay đổi tương lai.
2. **Muốn mô phỏng việc default sẽ chặn nạp động, dùng cờ nào?** `-XX:-EnableDynamicAgentLoading` trên JVM đích.
3. **Muốn xác nhận chủ tiến trình cho phép nạp động và tránh cảnh báo JEP 451 hiện tại, dùng gì?** `-XX:+EnableDynamicAgentLoading` trên JVM đích, từ lúc khởi chạy.
4. **Cờ từ chối dynamic loading có cấm `-javaagent` khi khởi động không?** Không, đó là con đường startup được quy định riêng.
5. **Client attach được nhưng `loadAgent` bị lỗi có chứng tỏ attach bị tắt hoàn toàn không?** Không. Kết nối có thể vẫn hoạt động nhưng yêu cầu nạp agent bị từ chối.
6. **Nhìn stdout của một agent chỉ in mốc có thể khẳng định nó đã sửa bytecode không?** Không. Việc nạp agent và việc gọi các API instrument class là hai sự kiện khác nhau.
7. **Có thể dùng version Java compiler để biết JVM nào in warning không?** Không; phải xem runtime của tiến trình phát cảnh báo.

## 10. Checklist trước khi nâng JDK

- [ ] Ghi nhận JVM vendor, bản JDK thực chạy, PID và flags tại môi trường có cảnh báo.
- [ ] Xác định có dùng `-javaagent` ngay startup hay tải thông qua `VirtualMachine.loadAgent`/công cụ tương đương khi JVM đang chạy.
- [ ] Thử trên cùng môi trường với `-XX:-EnableDynamicAgentLoading` để phát hiện chỗ thật sự phụ thuộc dynamic loading.
- [ ] Chuyển sang startup agent khi công cụ hỗ trợ; xác minh manifest và thông số của library.
- [ ] Nếu bắt buộc phải dynamic load, đặt `-XX:+EnableDynamicAgentLoading` **trên JVM đích** và bảo đảm quyền/nguồn agent được kiểm soát.
- [ ] Kiểm tra log **stderr** và hành vi thực tế; không coi việc biến mất cảnh báo là phép kiểm tra đầy đủ.
- [ ] Đọc release notes của đúng JDK trước khi kết luận chính sách đã thay đổi.

## Tài liệu chuẩn để đối chiếu

- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): mục tiêu, lý do, cảnh báo từ JDK 21, cách opt-in và hướng chuyển chính sách.
- [Oracle JDK 21 Release Notes — Warning Printed When an Agent Is Loaded](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): mô tả hành vi HotSpot, `EnableDynamicAgentLoading` và `jdk.instrument.traceUsage`.
- [Java SE 26 — `java.lang.instrument` Package Specification](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): phân biệt `premain`/`agentmain`, `Premain-Class`/`Agent-Class` và việc cảnh báo trên stderr.
- [Java SE 21 — `jdk.attach` Module](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/module-summary.html): module cung cấp `com.sun.tools.attach`.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): điểm kiểm chứng chính sách và thông tin bản JDK 27 tại thời điểm cập nhật bài.
