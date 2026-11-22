# Khởi tạo agent khi ứng dụng đã chạy và các lớp có thể đã được nạp

## 1. Vấn đề cần giải quyết

Một dịch vụ Java có thể đã chạy hàng giờ trước khi nhóm phát triển cần bật chẩn đoán, ghi metric hoặc quan sát một phương thức. Tại thời điểm đó, nhiều class đã được JVM nạp, có object đang sống và có thread đang thực thi. Việc **attach agent vào JVM đang chạy** giải quyết hai bài toán khác nhau: **(1) khởi tạo agent trong process hiện hữu**; **(2) xử lý các class đã được nạp trước thời điểm agent đăng ký bộ biến đổi**.

Bài này giải thích `agentmain`, `VirtualMachine.attach/loadAgent`, `Instrumentation`, class đã tải và chưa tải, `ClassFileTransformer`, `retransformClasses`, `redefineClasses`, những giới hạn về state, thread và tính an toàn. Cuối bài có ví dụ **Java 17+** chỉ dùng JDK, cho thấy agent được attach sau khi class đích đã load và chủ động đưa class đó qua callback của transformer.

**Cần nhớ ngay:** attach thành công không khiến mọi class từng được nạp tự động đi qua transformer mới. Và dù bytecode của class đã nạp được xử lý lại, agent cũng **không thể hồi tưởng chính xác các lời gọi đã xảy ra trước khi được cài**, trừ khi hệ thống đã có nguồn telemetry khác ghi chúng.

## 2. Dòng thời gian: trước và sau dynamic attach

~~~text
t0: JVM khởi động, chạy main() của ứng dụng
    |
t1: JVM nạp ServiceA.class; các lời gọi A đã xảy ra
    |
t2: JVM nạp ServiceB.class; các lời gọi B đã xảy ra
    |
t3: Công cụ ngoài attach vào JVM đích
    |
t4: JVM gọi agentmain(agentArgs, instrumentation)
    |
t5: Agent đăng ký ClassFileTransformer
    |   +--> ClassC mới nạp sau t5: transformer có thể được gọi
    |
t6: Agent yêu cầu retransformClasses(ServiceA.class)
    |   +--> Transformer có hỗ trợ retransform xử lý class A đã nạp
    |
t7: Các thread, object và ứng dụng tiếp tục chạy
~~~

Tại **t5**, `addTransformer` thiết lập callback cho các class được JVM định nghĩa hoặc biến đổi *sau thời điểm đăng ký*. `ServiceA` và `ServiceB` đã qua giai đoạn nạp ban đầu nên **không tự phát sinh callback mới chỉ vì agent vừa xuất hiện**.

Tại **t6**, nếu JVM hỗ trợ và `ServiceA` là modifiable class, **`retransformClasses`** chủ động đưa định nghĩa lớp cũ qua quy trình biến đổi. Đây là điểm mấu chốt của bài.

Bảng so sánh:

| Câu hỏi | Startup agent | Agent attach muộn |
|---|---|---|
| JVM nạp agent khi nào? | Lúc launcher khởi động với `-javaagent` | Khi có yêu cầu attach đến JVM đang chạy |
| Entry point | `premain(...)` | `agentmain(...)` |
| Manifest | `Premain-Class` | `Agent-Class` |
| Thời gian chạy so với ứng dụng | `premain` trước `main` | Ứng dụng có thể đang phục vụ request |
| Class đã tải | Thường có thể cài transformer sớm cho app | Phải xét các class đã tải và khả năng xử lý lại |
| Dữ liệu lịch sử | Không tự tạo dữ liệu trước khi probe chạy | Không tái tạo sự kiện từng xảy ra trước attach |

Một JAR có thể hỗ trợ cả hai lối khởi động, nhưng `loadAgent` gọi `agentmain` từ **`Agent-Class`**, còn `-javaagent` gọi `premain` từ **`Premain-Class`**. `Main-Class` chỉ dùng cho executable JAR chạy bằng `java -jar`.

## 3. Attach API hoạt động như thế nào?

Module **`jdk.attach`** cung cấp `com.sun.tools.attach.VirtualMachine` trong các JDK có triển khai Attach API. Cơ chế mẫu:

~~~text
  JVM công cụ attach                      JVM ứng dụng đích
  -----------------                      ----------------
  VirtualMachine.attach(pid) ---------> kết nối đến JVM đang chạy
  vm.loadAgent(agentJar, args) --------> đọc agent JAR và Agent-Class
                                       nạp lớp agent
                                       gọi agentmain(args, Instrumentation)
                                           |
                                           +--> đăng ký transformer
                                           +--> xem các lớp đã tải
                                           +--> có thể retransform
  loadAgent trả về          <----------- agentmain hoàn tất
  vm.detach()                          JVM đích tiếp tục chạy
~~~

**Ba vai trò cần phân biệt:**

1. **Ứng dụng đích:** JVM đang phục vụ công việc, giữ object và thread hiện có.
2. **Công cụ attach:** một process JVM khác gọi `VirtualMachine.attach(pid)`, `loadAgent(path, options)` và `detach()`.
3. **Mã agent:** class có `public static void agentmain(...)`; phương thức này **chạy bên trong JVM đích**, nhận đối tượng `Instrumentation` do JVM đích cung cấp.

`loadAgent` dùng **đường dẫn file được JVM đích giải thích**. Trong container, cùng một chuỗi đường dẫn ở host chưa chắc trỏ tới file bên trong container. `detach()` chỉ đóng kết nối Attach API; nó **không tự tháo transformer, ngừng thread agent, hoàn nguyên bytecode hay xóa metric**.

Việc attach còn phụ thuộc nhà cung cấp JVM, cấu hình bảo mật, quyền OS, PID namespace và các lựa chọn lúc khởi động. Không giả định mọi JVM đều cho phép attach, và không dựa vào self-attach vì nhiều bản HotSpot từ chối mặc định khi process tự attach vào chính mình.

## 4. API để nhận diện và xử lý các lớp đã được nạp

### 4.1. Xem snapshot các class đã nạp

`Instrumentation.getAllLoadedClasses()` trả về mảng những `Class<?>` mà JVM đang giữ tại thời điểm truy vấn. Điều này gồm nhiều class ngoài ứng dụng như framework, class của JDK, array hoặc hidden class. Không nên lấy toàn bộ rồi gọi retransform hàng loạt.

~~~java
Class<?> target = Arrays.stream(inst.getAllLoadedClasses())
        .filter(c -> c.getName().equals("lab.TargetService"))
        .findFirst()
        .orElse(null);
~~~

**Mã này là trích đoạn, không phải chương trình độc lập.** Nó phù hợp với ví dụ đơn giản chỉ có một class loader. Trong Spring Boot, application server, plugin system hoặc OSGi, hai loader có thể tạo **hai class riêng dù cùng tên nhị phân**; phải lọc đúng class loader, module và nguồn class trước khi tác động.

Đây là một **snapshot**, không đóng băng quá trình nạp class. Một class có thể xuất hiện ngay sau khi snapshot được tạo.

### 4.2. Khả năng của JVM và khả năng của một lớp

Trước khi gọi `retransformClasses(target)`, kiểm tra:

~~~java
if (inst.isRetransformClassesSupported()
        && target != null
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

Cũng là **trích đoạn**, dùng trong ngữ cảnh có `inst` và `target`.

- `isRetransformClassesSupported()` là capability của cấu hình JVM hiện tại và agent. Agent cần khai báo **`Can-Retransform-Classes: true`** trong manifest, đồng thời VM phải hỗ trợ.
- `isModifiableClass(target)` cho biết lớp cụ thể có thể sửa đổi theo cơ chế instrumentation hay không. Array và primitive class không modifiable; các loại class khác cũng có thể bị giới hạn.
- `retransformClasses(target)` yêu cầu JVM thực hiện quy trình retransform trên class đó. Nó **không có nghĩa mọi thay đổi bytecode đều được chấp nhận**.

Để callback của một **transformer mới** được gọi trong retransformation, đăng ký nó với:

~~~java
inst.addTransformer(transformer, true);
~~~

Nếu dùng `addTransformer(transformer, false)`, callback của transformer đó **không được gọi mới** khi retransform; JVM có thể tái sử dụng kết quả từng được tính từ transformer không hỗ trợ retransformation trong các giai đoạn trước.

### 4.3. Retransform và redefine không giống nhau

- **Retransform:** `retransformClasses(Class<?>... classes)` chạy lại quy trình transformer trên định nghĩa lớp đang có (theo ngữ nghĩa của JVM). Thường hợp với việc áp dụng instrumenter cho class đã tải.
- **Redefine:** `redefineClasses(ClassDefinition... definitions)` nhận **classfile bytes thay thế** do agent cung cấp, chẳng hạn luồng hot-replace/debugger. Nó cần `Can-Redefine-Classes: true` và VM hỗ trợ.
- Hai capability **độc lập**; bật một thuộc tính không mặc nhiên bật thuộc tính kia.
- Cả hai chịu ràng buộc về thay đổi cấu trúc class, bytecode verification và những class không thể chỉnh sửa.

**Giới hạn quan trọng:** retransform/redefine không được hiểu là tái khởi tạo class hoặc khởi động lại ứng dụng. **Static initializer không chạy lại chỉ vì thao tác này; static field và object hiện tại giữ state**. Các stack frame đang thực thi method cũ có thể tiếp tục bytecode cũ; **lần gọi method mới** dùng định nghĩa sau khi cập nhật thành công.

## 5. Thực hành Java 17+: agent xuất hiện sau khi class đã load

Bài demo tạo hai JVM: JVM đích nạp sẵn `lab.TargetService`, còn JVM attach ra lệnh nạp agent muộn. Transformer trong ví dụ **chỉ in callback và trả `null`**, nghĩa là **không thay bytecode**. Nhờ đó ví dụ xác nhận chính xác cơ chế `agentmain` và retransform mà không cần ASM/Byte Buddy.

### 5.1. Cấu trúc thư mục

~~~text
late-attach-lab/
├── agent.mf
├── src/
│   ├── TargetService.java
│   ├── TargetApp.java
│   ├── LiveAgent.java
│   └── AttachTool.java
├── out/                      # được sinh khi biên dịch
└── agent.jar                 # được sinh bằng lệnh jar
~~~

### 5.2. Class đã nạp trước khi attach

Tệp **`src/TargetService.java`**:

~~~java
package lab;

public final class TargetService {
    public String work() {
        return "OK";
    }
}
~~~

Tệp **`src/TargetApp.java`**:

~~~java
package lab;

public final class TargetApp {
    public static void main(String[] args) throws Exception {
        TargetService service = new TargetService();
        System.out.println("target-ready:" + service.work());
        System.out.flush();
        Thread.sleep(20000);
    }
}
~~~

Đến khi chương trình in **`target-ready:OK`**, `TargetService` đã được nạp và instance của nó đã được sử dụng. `Thread.sleep(20000)` giữ JVM đích sống khoảng 20 giây để mở terminal khác và attach. Trong thực hành thủ công, nếu JVM đã thoát, hãy chạy lại để có PID mới.

### 5.3. Dynamic agent và ClassFileTransformer

Tệp **`src/LiveAgent.java`**:

~~~java
package lab;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Arrays;

public final class LiveAgent {
    public static void agentmain(String agentArgs, Instrumentation inst)
            throws Exception {
        System.out.println("agentmain:" + agentArgs);

        Class<?> target = Arrays.stream(inst.getAllLoadedClasses())
                .filter(c -> c.getName().equals("lab.TargetService"))
                .findFirst()
                .orElse(null);

        System.out.println("already-loaded:" + (target != null));
        System.out.println(
                "retransform-supported:" + inst.isRetransformClassesSupported()
        );

        if (target == null || !inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            return;
        }

        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> classBeingRedefined, ProtectionDomain domain,
                    byte[] bytes) {
                if ("lab/TargetService".equals(className)) {
                    System.out.println(
                        "transform-existing:" + (classBeingRedefined != null)
                    );
                }
                return null; // Không sửa bytecode trong thí nghiệm.
            }
        };

        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(target);
        } finally {
            inst.removeTransformer(transformer);
        }
    }
}
~~~

Giải thích đầy đủ:

1. JVM gọi **`agentmain`** sau khi Attach API yêu cầu nạp agent. Tham số `agentArgs` được truyền nguyên chuỗi từ helper.
2. **`getAllLoadedClasses`** cho phép tìm `TargetService` đã nạp trước; nếu không tìm thấy, demo báo `already-loaded:false` và dừng.
3. Cờ capability và **`isModifiableClass`** bảo đảm không thử retransform khi biết trước không hỗ trợ.
4. **`addTransformer(transformer, true)`** đăng ký transformer có khả năng tham gia retransformation, khác với cờ mặc định `false`.
5. **`retransformClasses(target)`** yêu cầu JVM xét lại class cũ. Trong callback, `classBeingRedefined != null` cho thấy JVM truyền tham chiếu tới class đang retransform, thay vì class mới nạp lần đầu.
6. **`return null`** nghĩa là transformer này không cung cấp bytes thay thế. Đây là bài demo cơ chế callback; **không tạo probe đo lường thực sự**.
7. **`removeTransformer`** gỡ callback sau một lần thử. Nó không làm JVM thoát, không xóa agent và không tự hoàn nguyên bytecode đã đổi ở một ví dụ khác.

Một agent production theo dõi liên tục thường **giữ transformer đã đăng ký** để xử lý các class mới nạp, quản lý vòng đời và tránh gắn trùng nhiều lần. Demo gỡ ngay để xác minh đúng **một thao tác**.

### 5.4. Main manifest của agent JAR

Tệp **`agent.mf`**, kết thúc bằng newline:

~~~text
Manifest-Version: 1.0
Agent-Class: lab.LiveAgent
Can-Retransform-Classes: true

~~~

**`Agent-Class`** là thuộc tính bắt buộc để JVM gọi `agentmain` qua đường dynamic attach; `Premain-Class` được dùng cho `-javaagent` khi startup. **`Can-Retransform-Classes: true`** yêu cầu capability retransform; VM vẫn có quyền báo không hỗ trợ. Không cần `Main-Class` trong agent JAR này.

**Lưu ý manifest:** Thuộc tính nằm trong main section của **`META-INF/MANIFEST.MF`** bên trong JAR. Dùng `jar --manifest agent.mf` để công cụ tạo entry chính xác; tệp manifest nguồn phải có newline cuối, các dòng thuộc tính theo cú pháp `Name: value`.

### 5.5. Công cụ attach ở JVM riêng

Tệp **`src/AttachTool.java`**:

~~~java
package lab;

import com.sun.tools.attach.VirtualMachine;

public final class AttachTool {
    public static void main(String[] args) throws Exception {
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(args[1], "late-load");
        } finally {
            vm.detach();
        }
        System.out.println("attached");
    }
}
~~~

`args[0]` là **PID của JVM đích**; `args[1]` là **đường dẫn JAR mà JVM đích đọc được**. Tùy chọn `"late-load"` đi vào `agentmain` như một chuỗi, không được tự động phân tích thành các tham số tên–giá trị.

`VirtualMachine` thuộc module JDK `jdk.attach`, vì vậy demo dùng tùy chọn `--add-modules jdk.attach` khi biên dịch/chạy helper. Công cụ có thể kết nối tới JVM đích nếu JVM, quyền và nền tảng cho phép; không có đảm bảo trên mọi JRE hay môi trường bị khóa.

### 5.6. Biên dịch bằng JDK

Tại thư mục gốc **`late-attach-lab`**, tạo `out`. Trong Bash:

~~~bash
mkdir -p out
~~~

Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out
~~~

Biên dịch tất cả source với Java 17 target:

~~~bash
javac --release 17 --add-modules jdk.attach -d out src/TargetService.java src/TargetApp.java src/LiveAgent.java src/AttachTool.java
~~~

Tạo agent JAR chỉ chứa class agent:

~~~bash
jar --create --file agent.jar --manifest agent.mf -C out lab/LiveAgent.class
jar --list --file agent.jar
~~~

Danh sách entry quan trọng:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/LiveAgent.class
~~~

Vì các tệp nằm ở `package lab;`, entry class phải là **`lab/LiveAgent.class`**. Lệnh `-C out lab/LiveAgent.class` tránh đưa nhầm tiền tố `out/` vào bên trong JAR. `TargetApp`, `TargetService` và `AttachTool` chỉ cần có trong `out` cho bài demo, không phải trong agent JAR.

### 5.7. Chạy hai terminal và xem output

**Terminal A**: khởi động ứng dụng đích. Với HotSpot hỗ trợ cờ sau, bật dynamic-agent loading một cách tường minh:

~~~bash
java -XX:+EnableDynamicAgentLoading -cp out lab.TargetApp
~~~

JVM đích in:

~~~text
target-ready:OK
~~~

Đây là thời điểm class đích đã nạp. Trong vòng 20 giây, tại **terminal B** chạy:

~~~bash
jps -l
~~~

Tìm dòng có tên `lab.TargetApp`; số ở đầu dòng là **PID đích**. Thay PID minh họa **`12345`** và đường dẫn `/absolute/path/to/agent.jar` bằng giá trị phù hợp với hệ điều hành/JVM đích:

~~~bash
java --add-modules jdk.attach -cp out lab.AttachTool 12345 /absolute/path/to/agent.jar
~~~

Ở terminal B, nếu `loadAgent` thành công, stdout là:

~~~text
attached
~~~

Ở **terminal A** (JVM đích), trên một JVM có hỗ trợ tính năng cần thiết, các dòng thêm là:

~~~text
agentmain:late-load
already-loaded:true
retransform-supported:true
transform-existing:true
~~~

Các dòng này chứng minh:

- `agentmain` chạy sau khi ứng dụng đã bắt đầu.
- `TargetService` nằm trong tập class đã tải.
- JVM hỗ trợ retransformation cho agent đã cấu hình.
- Transformer nhận callback trên class **đã tồn tại**, do lời gọi `retransformClasses`.

**Không có thông điệp nào chứng minh hành vi method đã bị thay đổi**, vì transformer của demo trả `null`. Nếu target đã thoát trước khi attach, hãy chạy lại và lấy PID mới. Nếu triển khai JVM không hỗ trợ flag startup, dùng chính sách của VM đó thay vì mặc định thêm một JVM flag không tương thích.

### 5.8. Thí nghiệm đối chứng

Tạm bỏ dòng **`inst.retransformClasses(target)`** khỏi demo, build lại JAR và attach vào **một JVM đích mới**. Vì `TargetService` đã load trước lúc transformer được đăng ký, mà demo lại remove transformer ngay, sẽ không xuất hiện **`transform-existing:true`**. Điều này thể hiện ranh giới giữa việc **đăng ký xử lý class mới** và việc **chủ động xử lý class cũ**.

Tương tự, nếu đổi `Can-Retransform-Classes: false` trong manifest, trên JVM tuân theo capability này, `isRetransformClassesSupported()` sẽ là **false** và demo bỏ qua retransformation. Chỉ sửa manifest là chưa đủ: phải **đóng gói JAR mới** rồi attach vào JVM test mới.

## 6. Khi đổi bytecode của class đã nạp, điều gì vẫn được giữ nguyên?

Retransformation không phải restart hay redeploy:

- **Object và static state không tự bị xóa.** Field hiện có, trạng thái singleton và instance đang dùng tiếp tục tồn tại.
- **Static initializer không chạy lại** chỉ vì `retransformClasses`.
- **Frame đang chạy:** Nếu một thread đang thực thi bytecode cũ của method bị retransform, frame đó có thể tiếp tục chạy phiên bản cũ. **Lần gọi mới** tới method sử dụng phiên bản đã cập nhật sau khi thay đổi thành công.
- **Sự kiện quá khứ không tự được ghi nhận.** Một counter được chèn hôm nay không thể đếm chính xác các invocation hôm qua.
- **Giới hạn cấu trúc:** Trên các JVM phổ biến như HotSpot, không thể giả định retransform cho phép thay đổi số field/method, superclass hoặc signature tùy ý. Bytecode không hợp lệ sẽ bị verifier hoặc API từ chối.
- **Khả năng sửa từng class:** `isModifiableClass` có thể false dù JVM hỗ trợ retransformation nói chung.

Một agent biến đổi bytecode thực sự cần sinh class bytes hợp lệ và bảo đảm kiểm chứng (stack map frames, method descriptors, class file version, compatibility). Có thể dùng ASM hoặc Byte Buddy trong dự án thực tế. **Ví dụ hiện tại không phụ thuộc chúng**, nên tập trung vào logic attach, chọn class và gọi API đúng thời điểm.

## 7. Đồng thời và khoảng thời gian không được quan sát

Ứng dụng **không bị tự động đóng băng** trong lúc agent attach. Class loading, GC, network I/O và các request có thể vẫn xảy ra. Nếu agent làm:

~~~text
t1: snapshot = getAllLoadedClasses()
t2: application nạp ClassX
t3: agent addTransformer(...)
t4: agent retransformClasses(snapshot đã chọn)
~~~

thì `ClassX` **có thể bị bỏ qua** vì được nạp sau snapshot nhưng trước lúc transformer có hiệu lực. Vì vậy, ngay cả khi kết hợp transformer và một vòng quét các class cũ, **không được tuyên bố đã instrument tuyệt đối 100% class** nếu chưa thiết kế giải pháp xử lý race, định nghĩa ranh giới độ phủ và kiểm chứng kết quả.

Trong production:

1. Chỉ lấy snapshot để tìm **các lớp thực sự cần**; giảm phạm vi theo class loader, module, package và tên class.
2. Kiểm tra class còn modifiable; phân nhóm/giới hạn số lượng để tránh spike chi phí.
3. Đặt transformer có cơ chế loại trừ lớp agent, lớp JVM core và phụ thuộc nội bộ để tránh recursion.
4. Nếu cần theo dõi liên tục, giữ transformer cho future class load và quản lý lifecycle; nếu chỉ kiểm tra một lần, remove trong `finally`.
5. Ghi nhận class nào đã được xử lý và thất bại ra sao; cân nhắc quét lại có giới hạn khi race quan trọng.
6. Tính đến nhiều class loader, JPMS access và các khác biệt triển khai JVM. Hai class cùng tên không nhất thiết cùng định nghĩa.
7. Tránh chèn logging/lock nặng vào hot method hoặc chạy network I/O nặng trong `transform`.

## 8. Quản lý vòng đời agent sau khi attach

`agentmain` khởi chạy khi JVM đang sống, không phải trong một môi trường trống. Một agent có thể tạo thread, metric exporter, timer, MBean hoặc transformer. **`vm.detach()` không gỡ các resource ấy.**

Đối với agent thực tế, nên thiết kế **khởi tạo idempotent** (tránh attach lặp tạo transformer/thread trùng nhau), duy trì trạng thái đã khởi tạo rõ ràng, có giới hạn telemetry và cơ chế shutdown/reconfiguration thích hợp. Nếu agent biến đổi class, **chỉ gỡ transformer không hoàn nguyên các thay đổi bytecode đã áp dụng**; cần cơ chế khôi phục riêng nếu thật sự cần rollback. Không giả định một lệnh attach thứ hai sẽ tự sửa sạch trạng thái lần đầu.

Lưu ý về lỗi: theo đặc tả `java.lang.instrument`, lỗi khởi chạy `agentmain` trong dynamic attach **không bắt buộc JVM đích phải thoát** như lỗi `premain` lúc startup. Tuy nhiên lỗi attach có thể xuất hiện ở helper dưới dạng `AgentLoadException`, `AgentInitializationException` hoặc `IOException`, và tác dụng phụ trong JVM đích vẫn có thể tồn tại. Quan sát **cả log helper lẫn log của target JVM**.

## 9. Quyền truy cập, JVM flags và môi trường thực tế

Attach API phụ thuộc hỗ trợ của JVM và chính sách môi trường:

| Tình huống | Điều cần xác minh |
|---|---|
| Không tìm thấy PID | JVM chưa chạy, đã thoát, không cùng PID namespace hoặc `jps` không thể liệt kê |
| `VirtualMachine.attach` từ chối | User/permission khác, attach provider không tương thích, target cấm attach |
| `loadAgent` không tìm thấy JAR | Đường dẫn phải được **JVM đích** truy cập, đặc biệt trong container |
| JVM thiếu `jdk.attach` | Runtime bị rút gọn hoặc không cung cấp Attach API cần thiết |
| JVM không nhận `Agent-Class` | Manifest sai, class không nằm trong JAR hoặc `agentmain` sai chữ ký |
| `retransform-supported:false` | Thiếu capability trong JAR hoặc VM không hỗ trợ; không gọi ép API |
| `isModifiableClass` false | Một lớp cụ thể không thể biến đổi; bỏ qua và chọn phương pháp khác |
| Bytecode transformer gây lỗi | Bytecode không hợp lệ, schema thay đổi bị cấm, class loading recursion |
| Agent chạy nhưng không có dữ liệu cũ | Probe xuất hiện **sau** những sự kiện cần điều tra |
| Target latency tăng sau attach | Transformer, retransform hoặc probe có overhead cần đo và giới hạn |

### Thay đổi từ JDK 21

**JEP 451 của JDK 21** đưa ra cảnh báo khi agent được **nạp động** vào JVM chạy mà không có opt-in rõ ràng, chuẩn bị cho việc hạn chế mặc định trong các phiên bản tương lai. Trên HotSpot triển khai cờ này, khởi động target với **`-XX:+EnableDynamicAgentLoading`** thể hiện việc cho phép dynamic loading rõ ràng; **`-XX:-EnableDynamicAgentLoading`** cấm tải agent động. Hành vi mặc định có thể khác nhau theo **phiên bản/vender/cấu hình runtime**, vì vậy kiểm tra môi trường thực tế, không coi hướng dẫn này là cam kết rằng mọi JVM đều cho phép attach.

**Hai quyền không thay thế nhau:**

- JVM có cho phép **nạp agent động** vào target hay không: cơ chế attach/flag/policy.
- Agent sau khi nạp có được **retransform class** hay không: capability của VM cùng thuộc tính manifest **`Can-Retransform-Classes: true`**.

Có thể attach thành công nhưng không retransform được; cũng có thể manifest yêu cầu retransform đúng nhưng target chặn việc nạp agent.

Nếu ứng dụng chạy trong container, namespace PID và filesystem có thể khác bên ngoài; đường dẫn absolute trên host **không tự đồng nghĩa** đường dẫn mà target JVM nhìn thấy. Khi nền tảng cấm attach vì chính sách, hãy xem xét startup agent trong lần deploy sau, JFR hoặc cơ chế quan sát được nền tảng hỗ trợ.

## 10. Những hiểu nhầm thường gặp

**Hiểu nhầm 1: “Agentmain chạy rồi, vậy tất cả lớp đều được chèn probe.”**  
Sai. Agent phải chọn class, đăng ký transformer đúng khả năng, xử lý lớp cũ khi cần, và kiểm chứng hiệu lực trên các lời gọi mới.

**Hiểu nhầm 2: “Gọi `getAllLoadedClasses` chính là instrument.”**  
Sai. Đây là thao tác xem danh sách class đã tải; bản thân nó không thay đổi bytecode.

**Hiểu nhầm 3: “Chỉ gọi `addTransformer(transformer, true)` là đủ cho mọi class cũ.”**  
Sai. Thông thường cần một yêu cầu retransform cụ thể cho class đã nạp.

**Hiểu nhầm 4: “`Can-Retransform-Classes: true` chắc chắn retransform được.”**  
Sai. VM có thể không hỗ trợ, và mỗi class có thể không modifiable.

**Hiểu nhầm 5: “`return null` trong transformer đã thay đổi method.”**  
Sai. Đây là tín hiệu **không có bytes thay thế** từ transformer đó. Callback đã chạy và hành vi class đã đổi là hai điều khác nhau.

**Hiểu nhầm 6: “Class đang chạy lập tức chuyển sang bytecode mới ở giữa method.”**  
Sai. Các frame đang hoạt động có thể tiếp tục bytecode cũ; cần kiểm tra các lời gọi mới.

**Hiểu nhầm 7: “Attach xong thì có thể truy vấn lại mọi request quá khứ.”**  
Sai. Mã đo không thể tái dựng những sự kiện mà hệ thống chưa thu thập.

**Hiểu nhầm 8: “`vm.detach()` là hoàn nguyên toàn bộ agent.”**  
Sai. Nó ngắt phiên điều khiển Attach API, không tự hoàn nguyên transformer/class bytes/hook/thread.

**Hiểu nhầm 9: “Cùng tên `Class.getName()` chắc chắn cùng class.”**  
Sai. Class identity trong JVM còn phụ thuộc defining class loader; chọn nhầm loader có thể khiến không quan sát đúng đối tượng.

## 11. Bài tập và câu hỏi tự kiểm tra

**Bài tập A:** Chạy hai terminal như mục 5, chứng minh `TargetService` đã load trước attach bằng dòng `target-ready:OK` và sau attach bằng `already-loaded:true`. Tại sao callback vẫn chạy được? Vì agent đã gọi **`retransformClasses`**.

**Bài tập B:** Bỏ `retransformClasses(target)`, giữ phần còn lại, build JAR và chạy thử trên JVM mới. Vì sao không còn `transform-existing:true`? Vì transformer đăng ký muộn không tự hồi tố class đã nạp.

**Bài tập C:** Chuyển manifest thành `Can-Retransform-Classes: false`, build JAR mới và chạy lại trên JVM mới. Giải thích ý nghĩa `retransform-supported:false` và vì sao agent không gọi `retransformClasses`.

**Bài tập D:** Có hai bản `com.example.Service` do hai class loader khác nhau. Hãy đề xuất cách chọn đúng `Class<?>` dựa trên defining loader/module thay vì chỉ tên.

**Bài tập E:** Trong một request dài, attach và retransform một method đúng lúc method đang chạy. Tại sao nên tạo request mới để xác nhận probe? Vì frame hiện tại có thể tiếp tục bytecode cũ.

**Câu hỏi nhanh:**

- Dynamic attach dùng entry point gì? **`agentmain`**, được khai báo bởi **`Agent-Class`**.
- Dữ liệu nào nói class đã được nạp? **`getAllLoadedClasses()`**.
- Hai kiểm tra quan trọng trước retransform? **`isRetransformClassesSupported()`** và **`isModifiableClass(target)`**.
- Khi nào transformer mới có callback với class cũ? Khi JVM **thực hiện retransformation** cho class phù hợp và transformer đăng ký có hỗ trợ.
- `detach()` có xóa hook đã cài không? **Không**.
- Muốn có số lượt gọi trước attach phải dựa vào đâu? **Telemetry đã tồn tại từ trước**, không dựa vào transformer mới.

## 12. Ghi nhớ và tài liệu chuẩn

**Attach muộn là khởi tạo thêm mã quan sát trong một JVM đang sống.** `agentmain` cho agent quyền truy cập `Instrumentation`, nhưng lớp đã nạp cần được xử lý có chủ đích bằng `retransformClasses` hoặc `redefineClasses` nếu phù hợp và được VM hỗ trợ. Việc thay đổi class không làm chạy lại phần lịch sử hoặc khởi tạo lại toàn bộ state của ứng dụng. Khi điều tra sự cố, hãy đo trên **các sự kiện mới**, xác minh bytecode/probe thực sự hiệu lực và đánh giá chi phí khi có traffic thật.

Tham khảo đặc tả chính thức:

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Agent-Class`, `agentmain`, lifecycle và manifest.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): loaded classes, transformers, retransformation, redefinition và state.
- [Java SE 17 — Attach API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html): `VirtualMachine` và module `jdk.attach`.
- [OpenJDK — JEP 451](https://openjdk.org/jeps/451): thay đổi cảnh báo và quyền tải agent động từ JDK 21.
