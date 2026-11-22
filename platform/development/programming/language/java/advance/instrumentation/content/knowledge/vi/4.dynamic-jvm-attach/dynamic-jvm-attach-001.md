# Attach API và module `jdk.attach` có vai trò gì trong Java?

## 1. Vấn đề: ứng dụng đã chạy, ta muốn quan sát hoặc bổ sung công cụ

Một JVM production có thể đã chạy hàng giờ. Khi cần chẩn đoán, ta thường muốn lấy thông tin hoặc kích hoạt công cụ đo mà **không dừng ứng dụng rồi khởi động lại chỉ để thêm tùy chọn**. **Attach API** là một giao diện do JDK cung cấp, cho phép một chương trình Java đóng vai trò **công cụ (attacher/client)** kết nối tới một **JVM mục tiêu (target VM) đang chạy**, rồi gửi các yêu cầu được cơ chế attach của JVM đó hỗ trợ.

Các ứng dụng tiêu biểu:

- Tìm những JVM mà công cụ có thể phát hiện và lấy định danh của chúng.
- Đọc một số thông tin quản trị như system properties hoặc agent properties của target VM.
- Khởi động management agent/JMX của JVM mục tiêu khi API và cấu hình cho phép.
- Nạp **Java agent** sau khi JVM đã khởi động để quan sát, profiling, tracing hoặc chèn probe bằng `java.lang.instrument`.
- Nạp agent native thông qua JVM Tool Interface (JVM TI) khi cần khả năng ở mức thấp hơn.

**Điểm cốt lõi:** *attach* là **thiết lập kết nối điều khiển đến JVM đang chạy**; *load agent* là **một thao tác có thể thực hiện thông qua kết nối đó**. Chỉ gọi `VirtualMachine.attach(...)` không tự chèn bytecode, không tự nạp agent và không đồng nghĩa có quyền thay đổi mã trong mọi JVM.

## 2. `jdk.attach` là gì, đặt ở đâu và khác `java.instrument` thế nào?

Kể từ **JDK 9**, Attach API được đóng gói thành module JDK tên **`jdk.attach`**. Module này công khai hai package:

| Package | Vai trò |
| --- | --- |
| `com.sun.tools.attach` | API cho công cụ: `VirtualMachine`, `VirtualMachineDescriptor`, các exception và phương thức attach/đọc thông tin/nạp agent |
| `com.sun.tools.attach.spi` | Service Provider Interface: `AttachProvider` để các nhà cung cấp JVM/hệ thống hiện thực cách tìm và kết nối VM |

Tên package bắt đầu bằng `com.sun`, nhưng đây là **package được module `jdk.attach` export và có Java API documentation công khai**. Tuy vậy, `jdk.attach` là module chuyên dụng của JDK, không phải thư viện Java SE mà mọi runtime rút gọn hay JVM thay thế đều buộc phải có. Trên **JDK 8**, các lớp Attach API từng đi cùng công cụ trong `tools.jar`; từ hệ thống module JDK 9+, không thêm `tools.jar` như cách cũ.

Sự khác biệt giữa hai module thường bị nhầm:

| Thành phần | Chạy ở đâu? | Nhiệm vụ chính |
| --- | --- | --- |
| **`jdk.attach`** | Trong **tool JVM** gọi API | Tìm target VM, tạo kết nối, yêu cầu nạp agent hoặc lấy thông tin |
| **`java.instrument`** | Trong **target JVM**, nơi Java agent chạy | Cấp đối tượng `Instrumentation` cho `premain`/`agentmain` để có thể đăng ký transformer, retransform/redefine nếu được hỗ trợ |
| **Attach provider/transport** | Cơ chế phụ thuộc JVM, hệ điều hành | Thực hiện giao tiếp giữa tool VM và target VM |

Với **tool là named module**, khai báo phụ thuộc trong `module-info.java`:

~~~java
module com.example.attachtool {
    requires jdk.attach;
}
~~~

Đây là **nội dung file module-info.java**, không phải chương trình chạy độc lập. Trong ứng dụng chạy trên **class path** với JDK đầy đủ, ví dụ dưới đây nêu rõ `--add-modules jdk.attach` để yêu cầu runtime resolve module; nó không phải thao tác mở package nội bộ bằng `--add-opens`. Khi dùng `jlink` tạo runtime image tối giản, phải bảo đảm module `jdk.attach` và attach provider cần thiết thực sự có mặt **ở runtime của công cụ**. JVM mục tiêu phải có cơ chế attach tương thích; nó không nhất thiết phải chạy code import `com.sun.tools.attach`.

## 3. Hai tiến trình giao tiếp với nhau như thế nào?

Sơ đồ dưới đây mô tả **trường hợp thường gặp**: công cụ và ứng dụng là hai tiến trình Java riêng.

~~~text
  JVM của công cụ (JDK có jdk.attach)            JVM mục tiêu đang chạy
  +-----------------------------------+          +---------------------------+
  | AttachInspector / AgentLoader     |          | TargetApp                 |
  |  VirtualMachine.list()            |          |  Attach listener/provider |
  |  VirtualMachine.attach(id) -------+--------->|  kiểm tra điều kiện attach|
  |  getSystemProperties() -----------+--------->|  phản hồi dữ liệu          |
  |  loadAgent(agent.jar) ------------+--------->|  nạp JAR, gọi agentmain   |
  |  detach()                         |          |  agent dùng Instrumentation|
  +-----------------------------------+          +---------------------------+
                  tool JVM                                    target JVM
~~~

Thông thường:

1. **Xác định target**: từ `VirtualMachine.list()` (danh sách những JVM được các attach provider phát hiện) hoặc một ID đã biết. Trong nhiều triển khai, ID là PID hệ điều hành, nhưng API **không bảo đảm mọi provider đều dùng PID**.
2. **Attach**: `VirtualMachine.attach(id)` chọn provider tương thích rồi thiết lập kết nối nếu target cho phép.
3. **Gửi yêu cầu**: chẳng hạn `getSystemProperties()` hoặc `loadAgent(...)`. Việc một lệnh thành công còn tùy trạng thái target, khả năng provider và chính sách JVM.
4. **Detach**: gọi `detach()` để đóng kết nối điều khiển, kể cả khi tác vụ trung gian thất bại. **Detach không phải lệnh dừng target VM hoặc tháo agent đã được nạp**.

`VirtualMachine.list()` là kết quả tổng hợp từ các provider có sẵn, **không phải danh sách toàn bộ JVM trên mọi máy/container**. Một JVM có thể tồn tại nhưng không hiện trong list, hoặc có trong list rồi tắt trước lúc attach. Một ID hợp lệ cũng chưa chắc tạo được kết nối do quyền truy cập, phiên bản JVM, cấu hình hoặc lỗi I/O.

## 4. Các lớp và phương thức cần nắm

| API | Công dụng | Điểm cần nhớ |
| --- | --- | --- |
| `VirtualMachine.list()` | Liệt kê các `VirtualMachineDescriptor` có thể phát hiện | Danh sách động, không nhất thiết đầy đủ |
| `VirtualMachine.attach(String id)` | Kết nối tới VM theo ID | Có thể ném `AttachNotSupportedException` hoặc `IOException` |
| `VirtualMachine.attach(VirtualMachineDescriptor)` | Kết nối bằng descriptor | Sử dụng provider gắn với descriptor đó |
| `VirtualMachine.id()`, `provider()` | Xem ID/provider của kết nối | ID không bắt buộc là PID |
| `getSystemProperties()` | Lấy bản sao các system properties dạng chuỗi của target | Có thể chứa thông tin nhạy cảm; chỉ lấy/hiển thị thông tin cần thiết |
| `getAgentProperties()` | Lấy thuộc tính do cơ chế agent quản lý ở target | Không đồng nhất với system properties |
| `loadAgent(jarPath, options)` | Yêu cầu nạp **Java agent JAR** và gọi `agentmain` | Path được diễn giải theo filesystem của **target VM**; agent chạy code trong target |
| `loadAgentLibrary(name, options)` | Nạp native JVMTI agent theo **tên thư viện** | Cơ chế tìm thư viện phụ thuộc nền tảng |
| `loadAgentPath(path, options)` | Nạp native JVMTI agent theo **đường dẫn đầy đủ** | Khác với Java agent JAR |
| `startLocalManagementAgent()` / `startManagementAgent(props)` | Khởi động JMX management agent theo cơ chế API | Có ảnh hưởng vận hành; xem điều kiện bảo mật và cấu hình |
| `detach()` | Kết thúc kết nối từ công cụ | Đặt trong `finally` sau khi attach thành công |

`VirtualMachineDescriptor` cung cấp ID, tên hiển thị và provider. `AttachProvider` là **SPI dành cho implementer của cơ chế attach**; phần lớn người viết công cụ chỉ gọi `VirtualMachine`, không tự hiện thực provider.

Các exception giúp phân biệt nguyên nhân: `AttachNotSupportedException` thường biểu thị không có provider/tài nguyên tương thích; `IOException` có thể là lỗi kết nối/giao tiếp; `AgentLoadException` là vấn đề nạp agent; `AgentInitializationException` là vấn đề khởi tạo agent bên target. `SecurityException` cũng có thể xuất hiện tùy nền tảng/chính sách. Không nên tự động retry vô hạn khi PID sai, JVM đã kết thúc hoặc attach bị khóa bởi chính sách.

## 5. Ví dụ Java 17+: công cụ đọc thông tin JVM đang chạy

Ví dụ thứ nhất **không nạp agent**. Đây là một chương trình Java độc lập, minh họa cả `list`, `attach`, `getSystemProperties` và `detach`. Nó hiển thị tên module khi không truyền tham số; `--list` liệt kê các VM công cụ tìm thấy; truyền ID/PID để thử kết nối và đọc duy nhất thuộc tính phiên bản Java.

**Tệp: AttachInspector.java**

~~~java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import java.util.Properties;

public final class AttachInspector {
    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println(
                    "module=" + VirtualMachine.class.getModule().getName());
            System.out.println(
                    "usage: AttachInspector --list | <vm-id>");
            return;
        }
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected one argument");
        }

        if ("--list".equals(args[0])) {
            for (VirtualMachineDescriptor descriptor : VirtualMachine.list()) {
                System.out.println(
                        "vm=" + descriptor.id() + " "
                        + descriptor.displayName());
            }
            return;
        }

        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            Properties properties = target.getSystemProperties();
            System.out.println("attached=" + target.id());
            System.out.println(
                    "java.version=" + properties.getProperty(
                            "java.version", "unknown"));
        } finally {
            target.detach();
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.attach AttachInspector.java
java --add-modules jdk.attach AttachInspector
~~~

**Stdout chính xác** ở chế độ không tham số, khi có `jdk.attach`:

~~~text
module=jdk.attach
usage: AttachInspector --list | <vm-id>
~~~

Tìm các JVM:

~~~bash
java --add-modules jdk.attach AttachInspector --list
~~~

Kết quả phụ thuộc JVM và môi trường, có thể gồm các dòng dạng `vm=12345 com.example.Main` hoặc **không có dòng nào**; đây **không phải stdout cố định**. Trong môi trường mà ID là PID và đã có quyền truy cập target:

~~~bash
java --add-modules jdk.attach AttachInspector 12345
~~~

Khi kết nối thành công, các dòng có dạng `attached=12345` và `java.version=17.0.x`, trong đó giá trị thực phụ thuộc target. Nếu thất bại, phiên bản ví dụ để exception thoát ra nhằm nhìn rõ loại lỗi; tool thực tế nên bắt exception cụ thể, cung cấp thông báo gọn, log an toàn và quyết định retry theo nguyên nhân.

**Vì sao cần `finally`?** Nếu đọc properties ném `IOException`, khối `finally` vẫn gọi `detach()`. Chỉ gọi detach **sau khi** attach thành công; nếu `attach()` ném exception thì chưa có đối tượng để giải phóng. Không in toàn bộ `Properties` lên log production vì có thể chứa secret hoặc cấu hình nhạy cảm.

## 6. Nạp Java agent bằng Attach API: luồng đầy đủ

Một công cụ quan sát có thể cần đưa agent vào JVM **sau lúc target đã chạy**. Khi đó luồng chính là:

1. **Tạo agent JAR** có manifest `Agent-Class` trỏ tới class chứa `public static void agentmain(String, Instrumentation)`.
2. **Khởi động target JVM** và bảo đảm chính sách cho phép dynamic agent loading.
3. **Công cụ gọi `VirtualMachine.attach(id)`**, sau đó `loadAgent(jarPath, options)`.
4. **Target JVM nạp JAR và chạy `agentmain`**; đối tượng `Instrumentation` được JVM truyền cho agent.
5. **Công cụ gọi `detach()`**; agent có thể tiếp tục hoạt động trong target nếu được viết để làm vậy.

Cần phân biệt manifest `Agent-Class`/`agentmain` cho **nạp động** với `Premain-Class`/`premain` khi dùng **`-javaagent` lúc khởi động**. Đó là hai vòng đời khác nhau. Việc agent nhận `Instrumentation` không tự sửa class; agent phải chủ động đăng ký `ClassFileTransformer` hoặc dùng các API như `retransformClasses` khi JVM/cấu hình hỗ trợ.

### 6.1. Ví dụ agent và hai chương trình

Để minh họa tác động một cách dễ kiểm chứng, agent chỉ ghi một dòng vào **stdout của target VM**; nó không biến đổi bytecode.

**Tệp: SampleAgent.java**

~~~java
import java.lang.instrument.Instrumentation;

public final class SampleAgent {
    public static void agentmain(
            String options, Instrumentation instrumentation) {
        System.out.println("[agent] attached; options=" + options);
    }
}
~~~

**Tệp: TargetApp.java**

~~~java
public final class TargetApp {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("target pid=" + ProcessHandle.current().pid());
        System.out.println("target ready");
        Thread.sleep(120_000);
    }
}
~~~

Target giữ tiến trình chạy hai phút để công cụ có thời gian attach. Trong ứng dụng thực, target là service đã chạy từ trước; ví dụ này chỉ tạo môi trường thử nghiệm.

**Tệp: AgentLoader.java**

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AgentLoader {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: AgentLoader <vm-id> <agent-jar>");
        }

        String jarPath = Path.of(args[1]).toAbsolutePath().toString();
        VirtualMachine target = VirtualMachine.attach(args[0]);
        try {
            target.loadAgent(jarPath, "demo");
        } finally {
            target.detach();
        }
        System.out.println("Agent load finished");
    }
}
~~~

**Tệp: MANIFEST.MF** (kết thúc bằng dòng trống):

~~~text
Manifest-Version: 1.0
Agent-Class: SampleAgent

~~~

Giả sử cả bốn file Java và manifest ở cùng thư mục làm việc. Biên dịch, đóng gói JAR:

~~~bash
javac --release 17 --add-modules jdk.attach \
    AttachInspector.java SampleAgent.java TargetApp.java AgentLoader.java
jar --create --file sample-agent.jar --manifest MANIFEST.MF SampleAgent.class
~~~

Dấu `\` ở cuối dòng là cú pháp tiếp dòng của shell Unix. Trên Windows PowerShell, viết `javac --release 17 --add-modules jdk.attach AttachInspector.java SampleAgent.java TargetApp.java AgentLoader.java` trên **một dòng**; lệnh `jar` vẫn tương tự.

Ở **terminal A**, trên HotSpot dùng tùy chọn cho phép nạp agent động:

~~~bash
java -XX:+EnableDynamicAgentLoading TargetApp
~~~

Ví dụ target in ra:

~~~text
target pid=12345
target ready
~~~

PID sẽ khác trên máy của bạn. Trong **terminal B**, dùng PID thật vừa thấy:

~~~bash
java --add-modules jdk.attach AgentLoader 12345 sample-agent.jar
~~~

Khi thành công, **stdout terminal B** chính xác là:

~~~text
Agent load finished
~~~

**Terminal A** nhận thêm dòng do agent chạy **bên trong target JVM**:

~~~text
[agent] attached; options=demo
~~~

Đây là khác biệt quan trọng: loader báo kết quả tại **tool VM**, còn `agentmain` chạy và ghi output trong **target VM**. Ví dụ không phụ thuộc framework hay thư viện bên ngoài, nhưng kết nối thực tế đòi hỏi JVM/OS hỗ trợ attach và quyền truy cập phù hợp. Các PID/tình trạng quyền/hệ điều hành không cố định. Chạy trên JVM riêng do bạn quản lý trong môi trường thử nghiệm, sau đó kết thúc target hoặc chờ khoảng thời gian ngủ kết thúc.

### 6.2. Những điều kiện của `loadAgent`

- Đường dẫn JAR được **target VM** diễn giải. Nếu tool chạy trên host còn target chạy trong container với filesystem riêng, đường dẫn nhìn thấy ở tool có thể **không tồn tại** trong target.
- JAR cần manifest chứa `Agent-Class` hợp lệ và class cần có `public static agentmain(...)`. Thiếu class, manifest hoặc chữ ký sẽ dẫn đến lỗi nạp/khởi tạo.
- Dynamic attach có thể bị từ chối do chính sách JVM. **Được attach và được đọc properties không có nghĩa được nạp agent**.
- Agent chạy code **trong tiến trình target**, có thể quan sát/biến đổi trạng thái và ảnh hưởng hiệu năng, class loading, bảo mật. Chỉ nạp agent đã đánh giá nguồn gốc và được ứng dụng cho phép.
- `loadAgentLibrary`/`loadAgentPath` là đường **native JVMTI agent**, không phải tên khác của `loadAgent` dành cho Java JAR.

Ví dụ này cố ý không minh họa `ClassFileTransformer` để làm rõ ranh giới trách nhiệm: **Attach API đưa agent vào đúng JVM; `java.instrument` mới cung cấp khả năng can thiệp bytecode khi agent yêu cầu**.

## 7. Quyền truy cập, cấu hình và các thay đổi cần chú ý

Attach liên quan đến quyền truy cập giữa các tiến trình. Trong nhiều triển khai HotSpot thông thường, việc attach được giới hạn bởi chủ sở hữu tiến trình, hệ điều hành, chính sách bảo vệ và môi trường chạy. Khả năng attach còn bị ảnh hưởng bởi container/PID namespace, file permission, cấu hình JVM, provider, tiến trình đã thoát hoặc runtime image rút gọn.

Hai tùy chọn HotSpot **không tương đương**:

| Tùy chọn khi khởi động **target VM** | Ý nghĩa |
| --- | --- |
| `-XX:+DisableAttachMechanism` | Tắt cơ chế attach của HotSpot; các công cụ dựa vào cơ chế ấy có thể không kết nối được |
| `-XX:-EnableDynamicAgentLoading` | Không cho nạp agent động vào JVM đang chạy, dù một số chức năng attach/chẩn đoán khác vẫn có thể khả dụng |
| `-XX:+EnableDynamicAgentLoading` | Cho phép dynamic agent loading theo cơ chế HotSpot, thể hiện chấp thuận và ngăn cảnh báo về việc nạp agent động trên các bản JDK có cảnh báo |

**JEP 451 từ JDK 21** bắt đầu phát cảnh báo khi nạp agent động nếu chưa opt-in trên các JVM HotSpot tương ứng, nhằm chuẩn bị cho thay đổi **từ chối nạp động theo mặc định ở một bản JDK tương lai**. Vì mặc định có thể thay đổi giữa các bản phát hành, hãy kiểm tra tài liệu phiên bản JVM đang triển khai; không mặc định “JDK nào cũng cho nạp agent”. **Cảnh báo/tùy chọn này nhắm vào dynamic agent loading, không đồng nghĩa toàn bộ Attach API bị bỏ.** Agent cung cấp khi khởi động qua `-javaagent` có vòng đời khác với nạp động.

**Self-attach** (tool tự attach tới chính PID của nó) cũng có thể bị chặn theo mặc định trên HotSpot. Các cấu hình như `jdk.attach.allowAttachSelf` phụ thuộc triển khai và chỉ nên cân nhắc trong thử nghiệm có kiểm soát; ví dụ trên cố ý tạo **hai JVM riêng**. Không cố né cơ chế bảo vệ của môi trường production hoặc tự ý bật attach chỉ để tiện debug.

### Một số lỗi điển hình

| Hiện tượng | Cách đọc và hướng xử lý |
| --- | --- |
| `Module jdk.attach not found` | JDK/runtime tool thiếu module hoặc image đã lược bỏ; kiểm tra `java --list-modules` / cách build `jlink` |
| `package com.sun.tools.attach does not exist` | Tool đang dùng Java runtime/compiler không có Attach API hoặc build chưa resolve module |
| `AttachNotSupportedException` | VM ID sai/đã thoát, provider không tương thích, target không hỗ trợ attach hoặc cơ chế bị tắt |
| `IOException`/`AttachOperationFailedException` | Kết nối bị từ chối hoặc tác vụ bên target thất bại; đọc thông báo và kiểm tra OS/JVM/container |
| `AgentLoadException` | Không thể nạp JAR/thư viện; kiểm tra đường dẫn nhìn từ target, manifest, loại agent, chính sách dynamic loading |
| `AgentInitializationException` | Agent không khởi tạo thành công; xem log của target và mã `agentmain` |
| Attach được nhưng `loadAgent` thất bại | Quyền nạp agent động khác với khả năng attach/đọc properties; kiểm tra cờ và chính sách |
| `list()` không có target | Kết quả provider có giới hạn; kiểm tra JVM có hoạt động, cùng người dùng/namespace, phiên bản và khả năng attach |

Có thể kiểm tra module phía tool bằng `java --list-modules` hoặc `java --describe-module jdk.attach`. Không kết luận attach thành công chỉ vì module tồn tại: đó mới là một điều kiện về **API ở tool**, không chứng minh target cho phép kết nối.

## 8. Khi nào sử dụng, khi nào chọn cách khác?

| Nhu cầu | Phương án có ý nghĩa | Lý do |
| --- | --- | --- |
| Ứng dụng đã chạy; cần agent quan sát mới | Attach + `loadAgent` (nếu được cho phép) | Không cần khởi động lại, chấp nhận chi phí/rủi ro nạp động |
| Có thể cấu hình trước khi khởi động | `-javaagent:...` với `premain` | Chủ ứng dụng quyết định agent lúc startup; không phụ thuộc dynamic attach |
| Cần chẩn đoán JVM có sẵn | `jcmd`, JFR, JMX, logs/metrics theo khả năng target | Có thể đủ thông tin mà không cần viết Java attacher riêng |
| Cần đọc vài thông tin runtime của target | `VirtualMachine.attach` + `getSystemProperties` hoặc JMX | Không cần tạo Java agent chỉ để đọc thuộc tính |
| Cần chèn probe/đổi bytecode | Java agent + `Instrumentation` và transformer | Attach chỉ cung cấp đường đưa agent vào, không tự thực hiện biến đổi |

`jcmd` và các công cụ chẩn đoán JDK có thể dùng cơ chế attach, nhưng **không phải mọi lệnh `jcmd` đều nạp agent**. JFR/JMX/metrics có thể là lựa chọn phù hợp hơn nếu yêu cầu chủ yếu là quan sát. Việc chọn công cụ phải dựa vào câu hỏi thực tế, mức quyền truy cập, tác động production và cấu hình JVM.

## 9. Các hiểu nhầm cần tránh

1. **“`jdk.attach` là module để viết `agentmain`.”** Sai: công cụ attach import `com.sun.tools.attach`; mã agent lấy `Instrumentation` từ `java.instrument`.
2. **“Gọi `attach(pid)` là bytecode bị thay đổi.”** Sai: attach chỉ tạo kết nối; biến đổi phụ thuộc agent, API và điều kiện hỗ trợ.
3. **“`VirtualMachine.list()` thấy tất cả process Java.”** Không có bảo đảm; danh sách phụ thuộc provider/môi trường.
4. **“`loadAgent` đọc đường dẫn của tool.”** Target diễn giải đường dẫn; trong container có thể khác hoàn toàn.
5. **“`detach` gỡ agent khỏi JVM.”** Không; nó đóng kết nối từ tool.
6. **“Có module `jdk.attach` thì chắc chắn attach được.”** Không; vẫn cần target hỗ trợ, quyền OS, provider và cấu hình.
7. **“Tắt dynamic agent loading thì mọi lệnh chẩn đoán đều bị cấm.”** Không nhất thiết; đó là chính sách nạp agent động, khác `DisableAttachMechanism`.
8. **“Agent nào cũng an toàn.”** Không; agent chạy trong target JVM và có thể tác động tới toàn bộ tiến trình. Phải kiểm tra nguồn, tính tương thích, phạm vi can thiệp và overhead.

## 10. Kiểm tra hiểu biết

1. Tại sao ta cần **hai JVM** trong ví dụ, và thành phần nào thực sự chạy `agentmain`?
2. Vì sao một tool có thể liệt kê VM nhưng attach thất bại? Liệt kê ít nhất hai nguyên nhân.
3. Nếu file `sample-agent.jar` chỉ nằm trên host nhưng target ở container riêng, `loadAgent` có thành công không?
4. `jdk.attach` và `java.instrument` khác vai trò ra sao?
5. Tại sao nên đặt `detach()` trong `finally`? Sau detach, agent đã được nạp còn tồn tại không?
6. Có thể dùng `-XX:-EnableDynamicAgentLoading` để thử chính sách nạp agent nghiêm ngặt hơn mà vẫn thử các tác vụ attach khác không?
7. Khi mục tiêu chỉ là thu dữ liệu JVM, vì sao `jcmd`/JFR/JMX có thể phù hợp hơn việc tự nạp agent?

**Ghi nhớ:** `jdk.attach` cung cấp **giao diện công cụ để kết nối và yêu cầu thao tác với một JVM đang chạy**. `VirtualMachine` là điểm vào chính; `AttachProvider` cung cấp cơ chế kết nối theo triển khai. Nếu công cụ gọi `loadAgent`, mã `agentmain` mới chạy trong target và có thể dùng `Instrumentation`; vì vậy, khả năng attach, khả năng nạp agent và khả năng biến đổi bytecode là **ba lớp trách nhiệm cần phân biệt**.

### Tài liệu tham khảo chính thức

- [Java 17 — Module jdk.attach](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html)
- [Java 17 — VirtualMachine API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Java 17 — java.lang.instrument và vòng đời agent](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JDK 21 Release Notes — Dynamic agent loading / JEP 451](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
