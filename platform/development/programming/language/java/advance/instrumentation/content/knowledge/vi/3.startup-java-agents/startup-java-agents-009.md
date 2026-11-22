# Phân biệt `Main-Class`, `Premain-Class`, `Agent-Class` và `Launcher-Agent-Class`

Bốn thuộc tính này đều có thể xuất hiện trong `META-INF/MANIFEST.MF` của JAR, nhưng chúng **không cùng chỉ định một kiểu entrypoint**. `Main-Class` chọn điểm bắt đầu của **ứng dụng**; ba thuộc tính còn lại chọn điểm bắt đầu của **Java instrumentation agent** theo ba cơ chế khác nhau. Điểm dễ nhầm nhất: `Launcher-Agent-Class` chứa từ *Launcher* nhưng gọi **`agentmain`**, không gọi `premain`, và chạy **trước** `main` của ứng dụng.

Bài học tập trung vào agent tại thời điểm khởi động JVM/executable JAR; cơ chế attach khi JVM đã chạy được trình bày để làm rõ sự khác nhau giữa `Agent-Class` và `Launcher-Agent-Class`.

## 1. Bản đồ bốn thuộc tính

| Thuộc tính trong main manifest | Kích hoạt bởi | Phương thức được gọi | Thời điểm | Vai trò |
|---|---|---|---|---|
| `Main-Class` | `java -jar app.jar` | `public static void main(String[] args)` | Entry point ứng dụng | Chỉ định lớp ứng dụng cần chạy |
| `Premain-Class` | `java -javaagent:agent.jar[=options] ...` | `public static void premain(String, Instrumentation)` hoặc `premain(String)` | Trước `main` ứng dụng | Cài agent từ đầu phiên JVM |
| `Agent-Class` | Công cụ attach/load agent vào **JVM đang chạy** | `public static void agentmain(String, Instrumentation)` hoặc `agentmain(String)` | Sau khi JVM đã khởi động, thường sau khi ứng dụng đã vào `main` | Khởi tạo agent động |
| `Launcher-Agent-Class` | Khởi chạy **executable JAR** chứa agent cùng ứng dụng, thường `java -jar app.jar` | `public static void agentmain(String, Instrumentation)` hoặc `agentmain(String)` | Trước `main` ứng dụng | Agent tích hợp ngay trong application JAR |

Các giá trị như `demo.DemoApp` và `demo.DemoAgent` là **tên nhị phân của lớp Java** theo package (dấu chấm, không có `.class`, không phải đường dẫn file). Thuộc tính phải nằm trong **main section** của manifest. JVM không chạy mọi entrypoint chỉ vì thấy cả bốn tên trong cùng một JAR: JVM chọn theo **cách chương trình/agent được khởi chạy**.

Có thể ghi nhớ bằng câu hỏi:

- **Chạy ứng dụng nào?** → `Main-Class`.
- **Tải agent qua đối số JVM ngay lúc startup?** → `Premain-Class`.
- **Nạp agent vào process đã chạy?** → `Agent-Class`.
- **Tự chạy agent đóng gói cùng executable JAR?** → `Launcher-Agent-Class`.

### Luồng tổng quát

~~~text
java -jar app.jar
    đọc Main-Class + Launcher-Agent-Class (nếu có)
    -> gọi launcher agent: agentmain("", Instrumentation)
    -> gọi ứng dụng: main(String[])

java -javaagent:agent.jar=cfg -cp ... demo.DemoApp
    đọc Premain-Class trong agent.jar
    -> gọi startup agent: premain("cfg", Instrumentation)
    -> gọi ứng dụng: main(String[])

JVM ứng dụng đang hoạt động
    công cụ attach gọi loadAgent("agent.jar", "cfg")
    -> đọc Agent-Class trong agent.jar
    -> gọi dynamic agent: agentmain("cfg", Instrumentation)
    -> ứng dụng tiếp tục chạy
~~~

Sơ đồ minh họa **ba đường kích hoạt độc lập**. Dòng `java -javaagent:...` ở trên cố ý chạy ứng dụng bằng `-cp`, để không đồng thời kích hoạt `Launcher-Agent-Class` từ executable JAR. Nếu người dùng chủ ý kết hợp `-javaagent` với `-jar`, cả hai cơ chế startup có thể cùng khởi động agent; phải xét từng cơ chế, không suy rằng một thuộc tính “ưu tiên” và vô hiệu hóa thuộc tính còn lại.

## 2. `Main-Class`: entrypoint của ứng dụng

Manifest ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp

~~~

Khi chạy `java -jar app.jar`, Java launcher tìm `Main-Class`, tải lớp được chỉ định và gọi entrypoint `main`. Ở ví dụ Java 17 trong bài, chữ ký là:

~~~java
public static void main(String[] args) throws Exception
~~~

`args` nhận các đối số **sau tên JAR** trong lệnh `java -jar app.jar one two`. `Main-Class` **không cấp `Instrumentation`**, không định nghĩa `premain`/`agentmain`, không tự biến ứng dụng thành agent. Nếu application JAR thiếu `Main-Class` phù hợp, `java -jar` không biết lớp nào làm điểm bắt đầu và sẽ báo lỗi khởi chạy.

Khác biệt quan trọng:

~~~bash
java -jar app.jar
java -cp app.jar demo.DemoApp
~~~

Lệnh thứ nhất lấy entrypoint từ `Main-Class`. Lệnh thứ hai dùng **tên lớp ghi tường minh** và không dựa vào `Main-Class` trong manifest. Thuộc tính `Launcher-Agent-Class` cũng là cơ chế dành cho executable JAR; chỉ đặt JAR vào `-cp` không khiến launcher agent của JAR đó tự chạy.

`Main-Class` áp dụng cho application JAR, không phải `main()` bắt buộc của agent. Một agent JAR chỉ dùng với `-javaagent` hoàn toàn có thể **không có `Main-Class`**.

## 3. `Premain-Class`: Java agent từ command line

Manifest agent:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.DemoAgent

~~~

Lệnh kích hoạt:

~~~bash
java -javaagent:agent.jar=trace -cp app.jar demo.DemoApp
~~~

JVM đọc `Premain-Class` của **`agent.jar`** và gọi phương thức `premain` **trước** khi gọi `main` ứng dụng. Các chữ ký được chấp nhận:

~~~java
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst)

// Chữ ký dự phòng, nếu lớp không khai báo dạng hai tham số:
public static void premain(String agentArgs)
~~~

Đây là các **chữ ký minh họa phương thức**, không phải hai method cần bắt buộc khai báo cùng lúc. JVM ưu tiên dạng `(String, Instrumentation)`, sau đó mới tìm dạng chỉ có `(String)` nếu dạng ưu tiên không tồn tại. Trong thực tế, dạng hai tham số thường hữu ích vì `Instrumentation` cho phép đăng ký `ClassFileTransformer`, kiểm tra lớp đã tải và thực hiện các thao tác instrument được JVM hỗ trợ.

- `agentArgs` là **một chuỗi duy nhất** chứa phần sau dấu `=` của `-javaagent:...=...`. Nếu muốn định dạng `key=value,flag`, agent tự parse.
- `String[] args` của ứng dụng khác với `agentArgs`; option của agent không tự chuyển thành đối số ứng dụng.
- Có thể dùng nhiều `-javaagent`; JVM gọi các `premain` **theo thứ tự xuất hiện trên command line**.
- Khi agent không có `Premain-Class`, không có `premain` phù hợp, hoặc `premain` ném lỗi không được xử lý, JVM **dừng khởi động trước `main`**.
- Dù một agent class có cả `premain` và `agentmain`, cơ chế `-javaagent` chỉ chọn **`premain`**, không gọi `agentmain` thay thế.

`premain` không phải điểm vào trước *mọi* hoạt động của JVM: JVM đã có quá trình khởi tạo riêng trước đó. Nó được gọi trước `main` ứng dụng và có thể khiến nhiều lớp được tải trong khi agent khởi tạo. Nếu muốn theo dõi những lớp được tải sau đó, agent thường đăng ký transformer ngay trong `premain`.

## 4. `Agent-Class`: agent nạp sau khi JVM đã chạy

Manifest agent:

~~~text
Manifest-Version: 1.0
Agent-Class: demo.DemoAgent

~~~

Ở đường đi này, một công cụ attach vào JVM đang chạy rồi yêu cầu nạp JAR làm agent, ví dụ qua API `com.sun.tools.attach.VirtualMachine.loadAgent`. JVM đọc `Agent-Class` và gọi:

~~~java
public static void agentmain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst)

// Chữ ký dự phòng nếu không có dạng hai tham số:
public static void agentmain(String agentArgs)
~~~

Tên phương thức **phải là `agentmain`**. Tồn tại `premain` trong lớp đó không làm nó trở thành entrypoint của dynamic attach. `agentArgs` nhận chuỗi options do công cụ attach truyền vào; không có quy ước bắt buộc phải giống đối số `-javaagent`.

Ở runtime, lớp ứng dụng có thể **đã được tải và thực thi** khi `agentmain` chạy. Đăng ký transformer tại thời điểm này không có nghĩa mọi lớp đã tải tự động được biến đổi hồi tố. Tùy khả năng mà JVM cấp và manifest khai báo, agent có thể dùng `Instrumentation.retransformClasses`/`redefineClasses` cho những lớp thích hợp. Điều này tách biệt với việc gọi entrypoint.

Khác với lỗi startup agent, lỗi nạp agent động thường **không buộc JVM ứng dụng dừng** theo đặc tả `java.lang.instrument` (công cụ attach có thể nhận lỗi, JVM có thể ghi log). Cơ chế attach phụ thuộc JVM, chính sách và môi trường: quyền của process, mô-đun `jdk.attach`, khả năng hỗ trợ attach và cấu hình bảo mật có thể hạn chế thao tác. **Chỉ có `Agent-Class` trong manifest không tự động attach vào JVM nào cả**.

Với HotSpot JDK 21, việc nạp agent động có thể phát cảnh báo theo JEP 451; tùy chính sách, khởi chạy JVM đích với `-XX:+EnableDynamicAgentLoading` thể hiện lựa chọn cho phép nạp agent động và tránh cảnh báo. Đây là thiết lập liên quan **dynamic attach**, không phải điều kiện thông thường để dùng `-javaagent` lúc startup.

## 5. `Launcher-Agent-Class`: agent đi kèm executable JAR

Manifest ứng dụng kết hợp agent:

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp
Launcher-Agent-Class: demo.DemoAgent

~~~

Lệnh điển hình:

~~~bash
java -jar app.jar
~~~

Nếu Java launcher/runtime hỗ trợ cơ chế executable JAR này, nó tìm lớp agent được khai báo qua `Launcher-Agent-Class` **trong chính application JAR**, gọi **`agentmain` trước `main`** rồi mới cho ứng dụng chạy. Đây vẫn là **startup agent theo thời điểm thực thi**, mặc dù tên callback là `agentmain`.

Những điều cần phân biệt chính xác:

1. `Launcher-Agent-Class` gọi **`agentmain`**, không gọi `premain`; chữ ký hợp lệ giống `Agent-Class`.
2. `agentArgs` truyền vào `agentmain` qua đường **launcher agent luôn là chuỗi rỗng `""`**, kể cả khi `java -jar app.jar first second` có đối số ứng dụng. Hai đối số `first`, `second` đi vào `main(String[])`, **không đi vào agent**.
3. Lớp agent phải **được đóng gói cùng executable JAR**; khác với `-javaagent` trỏ rõ tới một agent JAR độc lập.
4. Nếu `Launcher-Agent-Class` được khai báo nhưng agent không tải được, không có `agentmain` hợp lệ hoặc callback ném exception/error không được bắt, **JVM dừng trước `main`**.
5. `Launcher-Agent-Class` tự nó **không đồng nghĩa** `Agent-Class`: cùng tên callback nhưng một bên được kích hoạt bởi launcher executable JAR, một bên được kích hoạt bởi công cụ attach sau startup. Hai thuộc tính có thể khai báo hai class khác nhau.

Giá trị `Launcher-Agent-Class` thường hữu ích cho ứng dụng tự đóng gói cơ chế đo đạc/chẩn đoán và muốn khởi tạo agent trước code ứng dụng mà không yêu cầu người dùng tự thêm `-javaagent`. Vì agent được tải rất sớm và có quyền instrument, nhà phát triển cần kiểm soát nguồn JAR và ảnh hưởng khởi tạo.

## 6. Thực hành Java 17+: một JAR, bốn thuộc tính, ba kiểu kích hoạt

Ví dụ **biên dịch và chạy được với JDK 17+** dùng ba lớp trong package `demo`. Hai lớp đầu được đưa vào một executable JAR; lớp thứ ba là tiện ích attach chạy riêng.

Cấu trúc thư mục:

~~~text
agent-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── DemoApp.java
│       ├── DemoAgent.java
│       └── AttachAgent.java
└── out/                      thư mục chứa file .class sau biên dịch
~~~

### 6.1. Ứng dụng: `src/demo/DemoApp.java`

~~~java
package demo;

import java.util.Arrays;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[main] args=" + Arrays.toString(args));
        if (args.length > 0 && args[0].equals("wait")) {
            System.out.println("[main] pid=" + ProcessHandle.current().pid());
            System.out.println("[main] Press Enter to exit");
            System.in.read();
        }
    }
}
~~~

`DemoApp` chỉ có `main`. Khi truyền `wait`, nó in PID và đọc một ký tự từ console để giữ process còn sống cho bài thực hành dynamic attach. Không truyền `wait` thì kết thúc ngay.

### 6.2. Agent: `src/demo/DemoAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[premain] options=" + render(agentArgs));
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[agentmain] options=" + render(agentArgs));
    }

    private static String render(String value) {
        return value == null ? "<null>" : (value.isEmpty() ? "<empty>" : value);
    }
}
~~~

Ở đây agent chỉ in tên callback và options để quan sát đường chạy, không thực hiện biến đổi bytecode. Nhờ đó ta phân biệt được **cơ chế chọn entrypoint** mà không cần thêm thư viện ASM/Byte Buddy. Trong agent thật, tham số `inst` chính là đối tượng `Instrumentation` dùng để đăng ký transformer hoặc xem khả năng của JVM.

### 6.3. Tiện ích attach: `src/demo/AttachAgent.java`

~~~java
package demo;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachAgent {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: AttachAgent <pid> <jar>");
        }

        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            target.loadAgent(
                    Path.of(args[1]).toAbsolutePath().toString(),
                    "from-attach");
        } finally {
            target.detach();
        }
    }
}
~~~

Class `AttachAgent` nằm trong **công cụ điều khiển riêng**, không bắt buộc đóng trong application/agent JAR. Nó dùng module `jdk.attach` của JDK (thường không có trong runtime image tối giản). Mẫu này cần JVM đích cho phép attach từ process đang dùng, thường cùng người dùng hệ điều hành. `finally` bảo đảm ngắt kết nối sau khi gửi yêu cầu.

### 6.4. Manifest: `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Main-Class: demo.DemoApp
Premain-Class: demo.DemoAgent
Agent-Class: demo.DemoAgent
Launcher-Agent-Class: demo.DemoAgent

~~~

Đây là **một manifest hợp lệ** để cùng một JAR phục vụ nhiều đường chạy. Đảm bảo có **dòng trống kết thúc phần main manifest**. File manifest dùng cặp `Tên-Thuộc-Tính: giá trị`, không viết `demo/DemoAgent.class`. `jar` sẽ gộp manifest này khi đóng gói.

### 6.5. Biên dịch và đóng gói

Từ thư mục `agent-lab` (đã tạo `src/demo` và `out`), chạy:

~~~bash
javac --release 17 -d out src/demo/DemoApp.java src/demo/DemoAgent.java src/demo/AttachAgent.java
jar --create --file demo.jar --manifest MANIFEST.MF -C out demo/DemoApp.class -C out demo/DemoAgent.class
~~~

`javac --release 17` tạo bytecode phù hợp Java 17. `DemoApp.class` và `DemoAgent.class` được chứa trong `demo.jar`, còn `AttachAgent.class` vẫn ở thư mục `out` để chạy công cụ attach. Không cần Maven/Gradle cho thí nghiệm này.

### 6.6. Chạy A — executable JAR: `Main-Class` + `Launcher-Agent-Class`

~~~bash
java -jar demo.jar alpha
~~~

Stdout:

~~~text
[agentmain] options=<empty>
[main] args=[alpha]
~~~

JVM gọi **`DemoAgent.agentmain`**, dù trong manifest cũng có `Premain-Class` và `Agent-Class`. Lý do: đường này được kích hoạt bởi **`Launcher-Agent-Class`** của executable JAR. Dòng `options=<empty>` chứng minh launcher agent **không nhận** đối số `alpha` của ứng dụng.

### 6.7. Chạy B — startup agent qua `-javaagent`: `Premain-Class`

~~~bash
java -javaagent:demo.jar=boot -cp demo.jar demo.DemoApp alpha
~~~

Stdout:

~~~text
[premain] options=boot
[main] args=[alpha]
~~~

Ở đây JVM đọc **`Premain-Class`** từ JAR dùng với `-javaagent` và gọi `DemoAgent.premain("boot", inst)`. `Main-Class` không được dùng để tìm app vì đã ghi `demo.DemoApp` trực tiếp trên command line. `Launcher-Agent-Class` cũng không được kích hoạt: ứng dụng chạy qua **classpath**, không qua `java -jar`.

Vị trí của `-javaagent` là trong **các tùy chọn JVM, trước tên main class hoặc trước `-jar`**. Nếu đặt nhầm sau tên lớp hoặc sau tên executable JAR, nó thường trở thành **đối số ứng dụng**, không còn là tùy chọn JVM.

### 6.8. Chạy C — classpath bình thường: không tự kích hoạt agent

~~~bash
java -cp demo.jar demo.DemoApp alpha
~~~

Stdout:

~~~text
[main] args=[alpha]
~~~

Kết quả chỉ có `main`. Dù manifest mang đủ bốn thuộc tính, không có `-javaagent`, `-jar` hoặc lời gọi dynamic attach thì JVM không tự kích hoạt agent.

### 6.9. Chạy D — attach vào JVM đang chạy: `Agent-Class`

Mở **terminal thứ nhất** từ thư mục `agent-lab`:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp demo.jar demo.DemoApp wait
~~~

Ứng dụng in `[main] args=[wait]`, sau đó in dòng `[main] pid=` cùng PID thật và chờ Enter. Trong thí nghiệm, `-XX:+EnableDynamicAgentLoading` áp dụng cho **JVM đích HotSpot**, cho phép dynamic attach rõ ràng. Con số PID khác nhau giữa các lần chạy.

Mở **terminal thứ hai** trong cùng thư mục. Giả sử terminal đầu vừa in `pid=12345`, chạy:

~~~bash
java --add-modules jdk.attach -cp out demo.AttachAgent 12345 demo.jar
~~~

`AttachAgent` chuyển `demo.jar` thành đường dẫn tuyệt đối và gọi `VirtualMachine.loadAgent(..., "from-attach")`. Terminal đầu sẽ in thêm:

~~~text
[agentmain] options=from-attach
~~~

Đây là **`Agent-Class`**: callback `agentmain` chạy trong **JVM đích đang hoạt động**. `-XX:+EnableDynamicAgentLoading` là tùy chọn của JVM đích, không phải `-javaagent`. Sau thí nghiệm, nhấn Enter trong terminal đầu để kết thúc ứng dụng.

Nếu công cụ attach thất bại, kiểm tra PID còn sống, quyền truy cập cùng user, JDK có `jdk.attach`, cấu hình attach của hệ điều hành/container và chính sách JVM. Trên JDK 21, thiếu lựa chọn opt-in có thể dẫn đến cảnh báo về nạp agent động; trên các phiên bản hoặc bản phân phối khác, chính sách nạp động có thể chặt hơn. Không lấy output của lỗi môi trường làm dấu hiệu rằng `Agent-Class` gọi `premain`.

## 7. Nếu cùng JAR khai báo nhiều thuộc tính thì điều gì quyết định?

**Trigger quyết định entrypoint**, không phải thứ tự dòng trong manifest.

| Cách khởi chạy | Thuộc tính được sử dụng trong ví dụ | Callback |
|---|---|---|
| `java -jar demo.jar` | `Launcher-Agent-Class` và `Main-Class` | `agentmain("")`, sau đó `main(args)` |
| `java -javaagent:demo.jar=boot -cp demo.jar demo.DemoApp` | `Premain-Class` | `premain("boot")`, sau đó `main(args)` |
| `java -cp demo.jar demo.DemoApp` | Không cần thuộc tính nào trong bốn thuộc tính | Chỉ `main(args)` |
| `VirtualMachine.loadAgent("demo.jar", "from-attach")` | `Agent-Class` | `agentmain("from-attach")` trong JVM đích |

Khi `-javaagent` trỏ vào JAR có cả `Premain-Class` và `Agent-Class`, JVM chọn **`Premain-Class`**; dòng `Agent-Class` không khiến `agentmain` chạy trên đường startup đó. Khi attach vào JAR tương tự, JVM chọn **`Agent-Class`**. Hai thuộc tính có thể cùng trỏ tới **một lớp** với cả hai phương thức như `DemoAgent`, hoặc hai lớp khác nhau.

Có thể chạy `java -javaagent:demo.jar=boot -jar demo.jar alpha` để vừa dùng **startup agent** vừa dùng **launcher agent** từ cùng JAR. Trong tình huống này, đừng xem việc một lớp có cùng tên ở hai thuộc tính là cơ chế chống đăng ký lặp: từng đường khởi động có ý nghĩa riêng. Nếu agent có side effect (ghi log, tạo thread, đăng ký transformer), nó cần thiết kế khởi tạo phù hợp khi người dùng chủ động kích hoạt nhiều cơ chế. Các `premain` của **nhiều `-javaagent`** được gọi theo thứ tự các tùy chọn; không suy diễn thứ tự giữa mọi loại hook từ vị trí các dòng trong manifest.

**Không tồn tại quy tắc** “JVM gọi hết `main`, `premain`, `agentmain` có mặt trong lớp”. Manifest chứa tên class; launcher/VM tìm method dựa trên **đường kích hoạt**.

## 8. Đóng gói, quyền hạn và các thuộc tính đi kèm

Manifest có thể có thêm những thuộc tính tùy chọn dành cho khả năng của agent:

~~~text
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

Chỉ khai báo những khả năng thực sự cần dùng. Khai báo `true` biểu thị **yêu cầu khả năng** nhưng không bảo đảm mọi class có thể redefine/retransform; agent phải kiểm tra phương thức hỗ trợ tương ứng của `Instrumentation` và giới hạn của JVM. Các giá trị khác `true` được hiểu là `false`; mặc định là `false`. Những thuộc tính này **không thay thế** cho `Premain-Class`, `Agent-Class` hoặc `Launcher-Agent-Class`.

Khi đóng gói production:

- Xác định rõ ứng dụng có cần **agent JAR riêng** (`-javaagent`) hay muốn **tích hợp agent vào executable JAR** (`Launcher-Agent-Class`). Không cần cố nhồi cả bốn thuộc tính nếu chỉ sử dụng một cách chạy.
- Đảm bảo `META-INF/MANIFEST.MF` là **main manifest thật** của JAR khởi chạy. Tên lớp trong manifest phải khớp package/class đã build, và lớp phải tải được qua hệ thống class loader liên quan.
- Với **fat JAR**, **shaded JAR** hoặc launcher riêng (ví dụ ứng dụng framework có cơ chế bootstrap), kiểm tra manifest thực tế và cách launcher tải lớp: nested JAR và custom class loader có thể ảnh hưởng khả năng tìm entrypoint. Đừng mặc định mọi executable archive hoạt động như JAR đơn giản của `jar` tool.
- Cân nhắc **module `java.instrument`**, quyền truy cập lớp và việc agent có thể làm nảy sinh class loading sớm, logging hoặc vòng phụ thuộc khi startup. Tác dụng phụ trong callback có thể xuất hiện trước code ứng dụng đầu tiên.
- Chỉ chạy agent từ nguồn tin cậy: agent có thể can thiệp bytecode và trạng thái quan sát của cả process. Không coi việc cùng nằm trong một JAR là một ranh giới bảo mật.
- Với **dynamic attach**, chuẩn bị cho chính sách nạp động thay đổi giữa các phiên bản JDK. JEP 451 đã đưa cảnh báo từ JDK 21; JDK có thể yêu cầu opt-in rõ ràng. Với ứng dụng cần agent từ đầu, `-javaagent` thường có vòng đời dễ kiểm soát hơn.

## 9. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách đối chiếu |
|---|---|---|
| `java -jar` báo thiếu main manifest attribute | Không có `Main-Class` phù hợp trong executable JAR | Kiểm tra **manifest của JAR được truyền sau `-jar`** |
| `-javaagent` báo không tìm được `Premain-Class` | Agent JAR chỉ có `Agent-Class` hoặc manifest sai | Đặt `Premain-Class` đúng class có `premain` |
| `premain` không in gì nhưng ứng dụng vẫn chạy | Chạy `java -cp`/`java -jar` mà không dùng `-javaagent` | Kiểm tra đúng **trigger**, không chỉ nội dung JAR |
| Có `Launcher-Agent-Class` nhưng nhận `premain` ngoài mong muốn | Nhầm `-javaagent` và executable-JAR launcher; class có hai callback | Quan sát lệnh chạy thực tế và log tên callback |
| `Launcher-Agent-Class` đã khai báo nhưng startup thất bại | Thiếu `agentmain`, tên class sai hoặc lỗi khởi tạo | Kiểm tra phương thức public static `agentmain` và class packaging |
| Attach thất bại dù có `Agent-Class` | JVM/process không cho attach, thiếu `jdk.attach`, sai PID/quyền, hoặc class agent không tải được | Phân biệt **lỗi kết nối attach** với **lỗi callback** |
| `agentmain` thấy chuỗi rỗng dù app có CLI args | Đang dùng đường `Launcher-Agent-Class` | Đây là hành vi đúng: launcher agent nhận `""`; đối số app vào `main` |
| Transformer không tác động lớp đã load | Agent được attach sau khi lớp đã được định nghĩa | Phân biệt transform khi load với retransform/redefine, kiểm tra khả năng JVM |
| Agent bị kích hoạt hai lần | Kết hợp `-javaagent` và launcher-agent hoặc attach bổ sung | Thiết kế initialization idempotent theo nhu cầu; ghi rõ cơ chế triển khai |

Khi điều tra, nên đọc theo thứ tự: **lệnh `java` thực tế** → **đúng JAR nào** → **manifest trong JAR đó** → **chữ ký callback** → **log/exception khi JVM gọi callback**. Đừng đổi tên `premain` thành `agentmain` chỉ vì thấy tên `Launcher-Agent-Class`; bản chất phụ thuộc trường manifest được launcher sử dụng.

## 10. Tự kiểm tra

1. `agent.jar` chỉ có `Premain-Class`, không có `Main-Class`. Có thể chạy bằng `-javaagent` không? **Có**, nếu lớp có `premain` hợp lệ; một agent JAR không cần là executable application JAR.
2. `app.jar` có `Main-Class` và `Launcher-Agent-Class`. `java -jar app.jar hello` sẽ đưa `hello` vào đâu? **Vào `main(String[])`**; callback `agentmain` qua launcher nhận chuỗi `""`.
3. `agent.jar` có cả `Premain-Class` và `Agent-Class`. `java -javaagent:agent.jar=cfg ...` gọi method nào? **`premain`**; không tự gọi `agentmain`.
4. Một công cụ sử dụng `VirtualMachine.loadAgent(...)` vào JVM đang chạy sẽ tìm thuộc tính nào? **`Agent-Class`**, rồi gọi `agentmain`.
5. Chỉ thêm `Agent-Class` vào manifest của `app.jar` có làm agent chạy khi `java -jar app.jar` không? **Không**; cần launcher-agent cho đường executable JAR hoặc thao tác attach thật.
6. Vì sao `Launcher-Agent-Class` không đồng nghĩa với dynamic attach? Vì nó **khởi động trước application `main` trong đường executable JAR**, còn `Agent-Class` là mục tiêu của yêu cầu **load agent vào JVM đang chạy**, dù cả hai gọi `agentmain`.
7. Nếu startup agent ném ngoại lệ chưa bắt, `main` ứng dụng có chạy tiếp theo đặc tả không? **Không** đối với `Premain-Class` và `Launcher-Agent-Class`; lỗi dynamic attach không có cùng quy tắc abort JVM đích.

### Tài liệu tham khảo

- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): lifecycle, callback và các thuộc tính manifest của agent.
- [Oracle Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Main-Class`, `Launcher-Agent-Class` và định dạng manifest.
- [Oracle Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): các cách chạy `-jar`, `-cp` và tùy chọn JVM.
- [Oracle Java SE 21 — `Instrumentation` interface](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): khả năng instrument trong callback.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): chính sách và cảnh báo dynamic attach.

**Ghi nhớ:** `Main-Class` là **ứng dụng**; `Premain-Class` là **agent qua `-javaagent`**; `Agent-Class` là **agent qua attach vào JVM đang chạy**; `Launcher-Agent-Class` là **agent được đóng gói cùng executable JAR và gọi `agentmain` trước `main`**.