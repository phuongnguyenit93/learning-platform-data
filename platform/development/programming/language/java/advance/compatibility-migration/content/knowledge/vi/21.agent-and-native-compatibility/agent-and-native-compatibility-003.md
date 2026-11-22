# Cảnh báo hoặc giới hạn nạp agent động theo phiên bản JDK

Trong quá trình nâng cấp JDK, một ứng dụng có thể vẫn biên dịch, chạy test và khởi động bình thường nhưng bất ngờ in cảnh báo liên quan đến **agent được nạp động**:

```text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with
         -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with
         -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
```

Đây là nhóm cảnh báo gắn với **JEP 451 — Prepare to Disallow the Dynamic Loading of Agents**, được đưa vào JDK 21. Mục tiêu của thay đổi là tăng tính toàn vẹn của JVM: khả năng sửa đổi hoặc quan sát bytecode trong một tiến trình đã chạy phải là một quyết định được kiểm soát, thay vì một tác dụng phụ khó phát hiện của thư viện hoặc test framework.

Cảnh báo không tự động có nghĩa ứng dụng đang bị tấn công hay agent không tương thích. Nó cũng không đồng nghĩa mọi Java agent hoặc mọi công cụ chẩn đoán đã bị cấm. Điều cần làm là phân biệt **agent được khai báo khi JVM khởi động** với **agent được đính kèm sau khi JVM đã chạy**, xác định JDK nào đang thực thi tiến trình đích, hiểu chính sách nạp động của JVM đó, rồi chọn cơ chế deployment phù hợp.

Bài học giải thích Java agent và native JVMTI agent, cơ chế Attach API, các thay đổi theo phiên bản JDK, cờ kiểm soát dynamic loading, ví dụ `premain` và `agentmain`, tình huống Mockito/Byte Buddy/APM, rủi ro bảo mật, cách chẩn đoán và quy trình migration.

> **Lưu ý về phiên bản:** JDK 21 là mốc xác định của JEP 451 khi cảnh báo được giới thiệu. Đối với JDK sau 21, bao gồm bản JDK mới được dùng tại thời điểm triển khai, phải kiểm tra release notes và hành vi của **đúng vendor, update level và runtime image**. Không nên biến câu “một bản tương lai sẽ mặc định cấm” của JEP thành khẳng định rằng một số JDK cụ thể chắc chắn đã đổi mặc định mà chưa kiểm chứng.

## 1. Agent trong Java là gì?

### 1.1. Java instrumentation agent

Java agent là thành phần chạy cùng JVM để quan sát hoặc tác động đến quá trình tải và thực thi class. API trung tâm là:

```java
java.lang.instrument.Instrumentation
```

Một agent có thể đăng ký `ClassFileTransformer`, đo lường các class được nạp, điều chỉnh bytecode ở thời điểm cho phép hoặc retransform/redefine những class đủ điều kiện.

Những ứng dụng hợp lệ thường gặp:

- Application Performance Monitoring (APM), tracing và profiling.
- Code coverage trong test.
- Mocking framework cần instrument class, ví dụ trong một số cấu hình Mockito/Byte Buddy.
- Debugging, serviceability và diagnostic tooling.
- Runtime policy enforcement hoặc observability do tổ chức quản lý.
- Framework integration cần biến đổi bytecode.

Agent có quyền năng lớn trong tiến trình. Nó có thể tác động đến behavior, dữ liệu nhạy cảm và hiệu năng; do đó, quyền nạp agent cần được xem như quyền thay đổi tính toàn vẹn của runtime.

### 1.2. Native JVM TI agent

Java Virtual Machine Tool Interface (JVMTI) cho phép native agent tương tác với JVM bằng các API ở tầng máy ảo. Native agent thường là shared library:

```text
Linux   : libobserver.so
macOS   : libobserver.dylib
Windows : observer.dll
```

Native agent có thể được cấu hình khi khởi động qua các tùy chọn như `-agentlib` hoặc `-agentpath` và, khi runtime hỗ trợ, có thể được nạp động qua cơ chế attach.

Java instrumentation agent và JVMTI native agent khác nhau về API và packaging, nhưng đều có thể thuộc phạm vi kiểm soát **dynamic agent loading**.

### 1.3. Agent khác thư viện Java thông thường

Một JAR được thêm vào classpath không tự động là Java agent. Một agent JAR có manifest khai báo entry point và được JVM nạp theo cơ chế agent.

Ví dụ:

```text
application.jar       -> chứa ứng dụng
logging-api.jar       -> dependency thông thường
observability-agent.jar -> agent JAR có Premain-Class / Agent-Class
```

Cùng một sản phẩm quan sát hệ thống có thể phát hành cả thư viện API và agent độc lập. Cần tìm thành phần nào thực sự được nạp bằng tùy chọn JVM hoặc Attach API.

## 2. Hai cách nạp agent: khi khởi động và khi đang chạy

### 2.1. Startup agent

Java instrumentation agent có thể được khai báo trước khi ứng dụng chạy:

```shell
java -javaagent:/opt/agents/observe-agent.jar \
     -jar application.jar
```

Trong trường hợp này, JVM nhận biết agent ngay từ đầu. Entry point thường là `premain`.

Ưu điểm:

- Có quyết định rõ từ người quản lý startup JVM.
- Không cần yêu cầu quyền attach vào tiến trình sau khi chạy.
- Có thể instrument các class quan trọng ngay từ thời điểm chúng được tải.
- Ít phụ thuộc vào chính sách dynamic attach của JDK mới.
- Thích hợp để khai báo trong service launcher, container, test JVM hoặc CI.

Hạn chế:

- Thường cần khởi động lại JVM để thêm, bỏ hoặc đổi agent.
- Phải quản lý agent version, tham số và JAR trước khi khởi động.
- Agent lỗi ở giai đoạn khởi tạo có thể ngăn ứng dụng startup.
- Không phải agent nào cũng hỗ trợ cùng một cách dùng.

### 2.2. Dynamic agent

Dynamic attach diễn ra sau khi JVM đích đã khởi động:

```text
JVM ứng dụng đã chạy
        |
        v
Công cụ / tiến trình attach
        |
        v
Attach API / serviceability mechanism
        |
        v
JVM đích nạp Java agent hoặc native agent
        |
        v
agentmain(...) hoặc agent entry point tương ứng
```

Java instrumentation agent được nạp bằng đường động thường sử dụng `agentmain`, còn native JVMTI agent có entry point tương ứng với cơ chế JVMTI.

Ưu điểm:

- Có thể bật chẩn đoán hoặc instrumentation mà không nhất thiết restart ứng dụng.
- Hữu ích khi đang điều tra một tiến trình đang chạy.
- Một số công cụ phát triển tự attach để thực hiện mocking/instrumentation.

Hạn chế:

- Phụ thuộc cơ chế attach, quyền OS, khả năng nạp agent của JVM đích và packaging.
- Có thể sinh cảnh báo hoặc bị từ chối theo JDK policy.
- Những class đã nạp có thể cần retransform/redefine, và không phải mọi sửa đổi bytecode đều được hỗ trợ.
- Cơ chế tự attach có thêm hạn chế riêng.
- Một thư viện có thể tự nạp agent mà người vận hành không biết.

### 2.3. So sánh nhanh

| Tiêu chí | Startup agent | Dynamic agent |
|---|---|---|
| Thời điểm nạp | Trước/đầu quá trình JVM khởi chạy | Sau khi tiến trình JVM đã chạy |
| Tùy chọn phổ biến | `-javaagent`, `-agentlib`, `-agentpath` | Attach API và công cụ tương ứng |
| Java agent entry point | `premain` | `agentmain` |
| Cần attach vào JVM đang chạy | Không | Có |
| Cảnh báo JEP 451 khi nạp động | Không phải trường hợp cảnh báo nạp động thông thường | Là trường hợp cần chú ý từ JDK 21 |
| Tác động chính sách tương lai | Cơ chế startup được chủ động cấp quyền | Có thể bị hạn chế mặc định tùy phiên bản |
| Cần restart để bổ sung agent | Thường có | Không nhất thiết, nếu JVM cho phép |
| Khả năng instrument class sớm | Tốt hơn | Có thể đã bỏ lỡ thời điểm class được tải |

Điểm khác nhau quan trọng nhất không phải việc code agent “mạnh” hay “yếu”, mà là **ai và khi nào cho phép agent can thiệp vào JVM**.

## 3. Java agent entry points: premain và agentmain

### 3.1. Agent hỗ trợ nạp khi startup

Một Java agent tối giản:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(
            String agentArgs,
            Instrumentation instrumentation) {

        System.out.println(
            "[agent] premain called; args=" + agentArgs
        );

        System.out.println(
            "[agent] loaded class count="
                + instrumentation.getAllLoadedClasses().length
        );
    }
}
```

Đây là ví dụ chỉ in thông tin đã được JVM cung cấp, không thay đổi class. Để runtime tìm thấy entry point khi dùng `-javaagent`, JAR phải có manifest khai báo đúng `Premain-Class`.

### 3.2. Agent hỗ trợ nạp động

Bổ sung entry point:

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(
            String options,
            Instrumentation instrumentation) {

        report("premain", options, instrumentation);
    }

    public static void agentmain(
            String options,
            Instrumentation instrumentation) {

        report("agentmain", options, instrumentation);
    }

    private static void report(
            String mode,
            String options,
            Instrumentation instrumentation) {

        System.out.println(
            "[agent] " + mode + " options=" + options
        );
        System.out.println(
            "[agent] loaded="
                + instrumentation.getAllLoadedClasses().length
        );
    }
}
```

Khi được tải như startup agent, JVM gọi `premain`; khi được tải động theo Java instrumentation agent protocol, JVM gọi `agentmain`. Một agent có thể hỗ trợ một hoặc cả hai chế độ.

Một số cách instrument thực tế sẽ gọi `addTransformer`, `retransformClasses` hoặc `redefineClasses`. Những thao tác này phụ thuộc capability, class modifiability, JDK version và định dạng bytecode; không nên suy rằng mọi class đều có thể bị thay đổi tuỳ ý.

### 3.3. Manifest của agent JAR

Ví dụ:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.ObserveAgent
Agent-Class: com.example.agent.ObserveAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
```

Các attribute có ý nghĩa:

- `Premain-Class`: class entry point khi nạp qua `-javaagent`.
- `Agent-Class`: class entry point khi nạp động.
- `Can-Redefine-Classes`: capability được yêu cầu để sử dụng một số API redefine class.
- `Can-Retransform-Classes`: capability được yêu cầu cho retransform.
- `Can-Set-Native-Method-Prefix`: capability liên quan native method prefix trong những agent sử dụng tính năng đó.

Khai báo capability không bảo đảm JVM hỗ trợ toàn bộ các biến đổi mà agent muốn làm. Khi chạy, có thể dùng `Instrumentation.isRedefineClassesSupported()` và `isRetransformClassesSupported()` để kiểm tra.

### 3.4. Build agent JAR không phải JAR ứng dụng thường

Agent entry class và những dependency cần thiết phải được đóng gói/hiển thị đúng cách khi JVM nạp agent. Nếu phụ thuộc vào thư viện bytecode, cần giải quyết classloading, package conflicts và module access phù hợp.

Việc tạo JAR có manifest hợp lệ chỉ là điều kiện ban đầu. Hãy kiểm tra hai đường chạy riêng biệt nếu agent cam kết hỗ trợ cả startup và dynamic loading.

## 4. Attach API và JVM đích

### 4.1. API Java cho nạp agent động

JDK có API để công cụ tương tác với một JVM khác:

```java
com.sun.tools.attach.VirtualMachine
```

Một chương trình quản trị có thể attach vào tiến trình JVM đích rồi yêu cầu nạp agent JAR. Ví dụ minh họa dùng PID và đường dẫn do operator chỉ định:

```java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachAgentTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: AttachAgentTool <pid> <agent-jar>"
            );
        }

        String pid = args[0];

        Path agentPath = Path.of(args[1])
            .toAbsolutePath()
            .normalize();

        VirtualMachine vm = VirtualMachine.attach(pid);

        try {
            vm.loadAgent(agentPath.toString(), "mode=observe");
        } finally {
            vm.detach();
        }
    }
}
```

Đây là ví dụ về API trong môi trường đã được cho phép quản trị JVM, không phải lời khuyên nạp agent tùy ý vào tiến trình của người khác. Công cụ chỉ hoạt động nếu JDK và tiến trình đích cung cấp cơ chế attach tương ứng, quyền OS cho phép, và chính sách dynamic loading không từ chối yêu cầu.

### 4.2. Chương trình attach và JVM đích là hai tiến trình

Cần tách:

```text
Process A: AttachAgentTool chạy với JDK A
Process B: Application JVM đích chạy với JDK B
```

JDK của công cụ attach **không nhất thiết** là JDK của ứng dụng đích. Cảnh báo và cờ cho phép nạp agent động chịu tác động chủ yếu bởi **JVM đích**, không phải chỉ bởi JDK đang chạy công cụ attach.

Nếu tool attach báo thành công nhưng agent không hoạt động, cần xem cả log của JVM đích lẫn log của tool. Agent có thể được nạp nhưng lỗi trong `agentmain`, hoặc code instrumentation không tương thích với class-file versions đang tồn tại.

### 4.3. Từ tools.jar đến module jdk.attach

Trên nhiều JDK 8 truyền thống, Attach API được cung cấp trong `tools.jar` của JDK, không phải API nằm trong mọi JRE tối giản.

Từ JDK 9, modular JDK giới thiệu module `jdk.attach`. Một ứng dụng modular dùng Attach API có thể cần descriptor:

```java
module com.example.attachtool {
    requires jdk.attach;
}
```

Với ứng dụng trên classpath hoặc dùng custom runtime image, cần xác nhận module `jdk.attach` có sẵn và được resolve trong cấu hình thực tế.

Không copy `tools.jar` từ JDK 8 vào runtime JDK mới để “khôi phục” Attach API; đây không phải đường migration được thiết kế.

### 4.4. Custom runtime image có thể không gồm attach

Khi tạo runtime bằng `jlink`, các module được đưa vào image là một phần của quyết định packaging. Một image tối giản có thể không chứa những module công cụ cần thiết.

Cần tách:

- Runtime của **tool attach** có `jdk.attach` và các thành phần cần thiết không?
- Runtime của **JVM đích** có hỗ trợ serviceability/attach và instrumentation không?
- Agent JAR cần module `java.instrument` hay các thành phần khác không?
- JDK vendor hoặc custom image có loại bỏ tính năng không?

Không nên giả định một container chỉ chứa application runtime image tối giản cũng có đầy đủ `jcmd`, `jps` hoặc các công cụ JDK như máy developer.

## 5. Những thay đổi theo phiên bản JDK

### 5.1. JDK 8: cơ chế attach đã tồn tại

Trong các bản HotSpot/OpenJDK JDK 8 phổ biến, Java instrumentation và Attach API đã được sử dụng cho nhiều công cụ. Tài liệu/build có thể dùng `tools.jar` và các lệnh hoặc API đặc thù JDK 8.

Điều cần chú ý khi nâng cấp:

- Không được giả định classpath của công cụ còn đường dẫn `lib/tools.jar`.
- Agent cũ có thể dùng nội bộ JVM/JDK không còn ổn định.
- Code transformer có thể không hiểu class-file version mới.
- Startup/attach flags có thể thay đổi qua vendor và JDK release.

### 5.2. JDK 9 trở đi: JPMS và tổ chức JDK mới

Attach API chuyển vào mô hình module của JDK. Java instrumentation và JVMTI vẫn là những cơ chế quan trọng, nhưng module encapsulation khiến một số kỹ thuật phản chiếu của agent/framework cũ gặp trở ngại.

Ví dụ các lỗi có thể xuất hiện:

```text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.ClassNotFoundException
```

Không nên gộp những lỗi này với cảnh báo JEP 451. Chúng có thể liên quan đến module exports/opens, classloading hoặc dependency incompatibility chứ không phải quyền nạp agent động.

### 5.3. JDK 17 và những bản trước JDK 21

Trên các runtime HotSpot/OpenJDK phổ biến trước JDK 21, dynamic agent loading thường được dùng mà chưa có cảnh báo chuẩn của JEP 451. Nhưng khả năng attach vẫn có thể bị hạn chế bởi flags, OS permissions, environment, container hoặc security policy.

Vì vậy, “không có cảnh báo JEP 451” **không** nghĩa nạp agent thành công trên mọi máy. Cũng không nên kết luận Java 17 không có rủi ro instrumentation chỉ vì log không in cảnh báo.

### 5.4. JDK 21: JEP 451 giới thiệu cảnh báo

JEP 451 chuẩn bị cho việc cấm nạp agent động theo mặc định trong tương lai. Ở mốc JDK 21, khi một Java agent hoặc JVMTI agent được nạp động trong những tình huống được JEP đề cập, JVM có thể phát cảnh báo đến standard error.

Thông điệp cốt lõi:

- Đã xảy ra **dynamic loading** của agent.
- Nếu đây là việc quản trị/serviceability có chủ đích, có thể khai báo rõ quyền cho phép bằng `-XX:+EnableDynamicAgentLoading`.
- Nếu không có chủ đích, dùng `-Djdk.instrument.traceUsage` để truy vết việc sử dụng instrumentation trong những trường hợp phù hợp.
- Một bản JDK tương lai có thể thay đổi trạng thái cho phép mặc định.

Ở JDK 21, JEP này tập trung vào việc cảnh báo và chuẩn bị migration, không phải tuyên bố rằng mọi cơ chế nạp động đã bị tắt ngay trên mọi runtime.

### 5.5. Những bản JDK sau JDK 21

Không được lấy ví dụ JDK 21 để suy ra mặc định của mọi JDK sau đó. Khi nâng lên một release mới:

1. Đọc JDK release notes và tài liệu flag của **đúng bản JDK**.
2. Xác định JDK vendor/distribution và update level.
3. Chạy một smoke test nạp agent có kiểm soát, nếu sản phẩm phụ thuộc vào dynamic loading.
4. Kiểm tra cảnh báo, exit code, agent entry point và application logs.
5. Xác nhận ý nghĩa và mức hỗ trợ của `-XX:+EnableDynamicAgentLoading`/`-XX:-EnableDynamicAgentLoading` trên runtime đó.
6. Không dựa vào dự đoán thời điểm đổi default của một JEP làm căn cứ release.

Bảng tư duy:

| Giai đoạn | Điều đáng nhớ | Việc nên làm |
|---|---|---|
| JDK 8 | Attach API và instrumentation đã có; packaging kiểu JDK cũ | Tìm dependency `tools.jar` và API nội bộ |
| JDK 9–20 | JPMS làm thay đổi JDK layout và module access | Kiểm tra `jdk.attach`, `java.instrument`, opens/exports, bytecode tools |
| JDK 21 | JEP 451 đưa ra cảnh báo cho dynamic agent loading | Nhận diện nguồn agent và chuyển sang startup agent khi hợp lý |
| JDK sau 21 | Chính sách có thể tiến hóa theo release/vendor | Xác minh release notes và hành vi thực tế trước khi chốt trạng thái |

Bảng này phân loại các mốc công nghệ, không phải support matrix cam kết của mọi vendor JVM.

## 6. Cảnh báo JEP 451 thực sự nói lên điều gì?

### 6.1. Không phải lỗi compile

Một ứng dụng có thể build thành công, mở cổng HTTP và xử lý request bình thường dù JVM in cảnh báo. Cảnh báo hướng tới một cơ chế instrumentation, không tự động chỉ ra source code ứng dụng sai.

Tuy nhiên, không nên bỏ qua vì một release tương lai có thể làm workflow phụ thuộc nạp động không hoạt động theo mặc định.

### 6.2. Không tự động là lỗ hổng đang bị khai thác

Có nhiều nguồn agent hợp lệ: APM, profiler, công cụ kiểm thử, debugger hoặc troubleshooting. Một warning xuất hiện trong CI khi test framework thực hiện instrumentation thường khác với một agent lạ xuất hiện trên production không có change request.

Điều cần phân loại:

- **Expected and authorized:** agent/version/path có trong deployment/test plan.
- **Expected but implicit:** thư viện hoặc test framework tự attach nhưng chưa được quản trị rõ.
- **Unexpected:** không biết ai nạp agent, từ JAR nào hoặc vì sao cần can thiệp JVM.

Trường hợp thứ hai cần cải thiện cấu hình; trường hợp thứ ba cần điều tra theo quy trình bảo mật/vận hành.

### 6.3. Warning liên quan thời điểm nạp, không phải tên sản phẩm

Cùng một agent JAR có thể được nạp bằng `-javaagent` khi startup hoặc bằng Attach API trong lúc chạy. JEP 451 phân biệt cách nạp, không đơn giản phân biệt “agent của vendor A” với “agent của vendor B”.

Không thể kết luận chỉ từ tên thư viện rằng nó sẽ sinh warning. Phải xem cách thư viện/test tool khởi tạo instrumentation.

### 6.4. Trạng thái “đã in warning” không chứng minh instrument thành công

Dòng cảnh báo cho biết JVM đã đi vào đường nạp động theo cơ chế có cảnh báo. Agent vẫn có thể thất bại khi:

- Không tìm thấy `Agent-Class` hoặc `agentmain` đúng chữ ký.
- Thiếu dependency trong agent JAR.
- Bytecode transformer không hiểu class major.
- Không có capability retransform/redefine cần thiết.
- Module access bị từ chối.
- Agent ném exception khi khởi tạo.
- Một class không cho phép thay đổi theo yêu cầu của agent.

Vì vậy, khi chẩn đoán cần xem **kết quả attach, log agent và hành vi instrumentation**, không chỉ tìm “WARNING”.

## 7. Các cờ JVM quan trọng

### 7.1. `-XX:+EnableDynamicAgentLoading`

Trên các runtime HotSpot/JDK hỗ trợ cờ này, việc khai báo:

```shell
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

thể hiện quyết định có chủ đích cho phép nạp agent động vào JVM đích. Với hành vi JDK 21 được JEP 451 mô tả, khai báo explicit này cũng là cách ngăn cảnh báo cảnh báo riêng về dynamic agent loading.

**Quan trọng:** phải đặt flag cho **JVM đích khi nó khởi động**. Đặt cờ này chỉ vào tiến trình attach client không tự sửa policy của JVM đã chạy.

Flag không làm agent tự nạp. Nó chỉ điều khiển quyền nạp động trong runtime phù hợp. Agent/tool vẫn phải có quyền attach và thỏa mãn các điều kiện khác.

### 7.2. `-XX:-EnableDynamicAgentLoading`

Cờ đối nghịch:

```shell
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

yêu cầu JVM HotSpot hỗ trợ flag từ chối dynamic agent loading. Đây có thể là cấu hình thử nghiệm rất hữu ích để **phát hiện sớm** thư viện hay công cụ nào còn phụ thuộc tự nạp agent.

Nếu agent được đưa vào từ startup bằng `-javaagent`, đó là một đường khác với dynamic loading; không nên coi cờ này là cách tắt tất cả instrumentation trên mọi JVM.

### 7.3. `-XX:+DisableAttachMechanism`

Ví dụ:

```shell
java -XX:+DisableAttachMechanism -jar application.jar
```

Ở những runtime HotSpot hỗ trợ cờ này, đây là một chính sách mạnh hơn, ảnh hưởng cơ chế attach của JVM và có thể làm nhiều công cụ serviceability/diagnostic không kết nối được.

Không nên dùng `DisableAttachMechanism` làm cách “ẩn warning” đơn thuần. Nó có thể làm mất công cụ thiết yếu để thu thread dumps, thông tin JVM hoặc chẩn đoán production. Phải xem tác động lên hệ thống vận hành và phân biệt với việc chỉ từ chối **dynamic agent loading**.

### 7.4. `-Djdk.instrument.traceUsage`

Ví dụ khi điều tra:

```shell
java -Djdk.instrument.traceUsage -jar application.jar
```

System property này được nhắc trong cảnh báo JEP 451 để giúp theo dõi nơi Instrumentation API được sử dụng trên những runtime hỗ trợ diagnostic tương ứng.

Nó hữu ích khi một thư viện thực hiện instrumentation gián tiếp và đội phát triển chưa biết code path nào đang tham gia. Tuy nhiên:

- Không phải mọi attach operation đều nhất thiết được giải thích hoàn toàn qua trace này.
- Trace có thể làm log nhiều và ảnh hưởng hiệu năng.
- Nó **không** tự cấp quyền attach hoặc sửa incompatibility.
- Nên bật có thời hạn trong môi trường được kiểm soát.

### 7.5. `-Djdk.attach.allowAttachSelf=true`

Trên một số runtime HotSpot, việc **JVM tự attach vào chính PID của nó** bị hạn chế trừ khi có cấu hình cho phép:

```shell
java -Djdk.attach.allowAttachSelf=true -jar application.jar
```

Đây là vấn đề **self-attach**, khác với quyền dynamic agent loading và khác với attach từ một process bên ngoài.

Nếu một thư viện vẫn tự attach sau khi bật property này, nó còn phải qua kiểm tra dynamic-agent policy. Không dùng property self-attach như phương án thay thế cho `-XX:+EnableDynamicAgentLoading`.

### 7.6. Bảng phân biệt các cờ

| Tùy chọn | Mục đích chính | Không thay thế cho |
|---|---|---|
| `-javaagent:path` | Nạp Java instrumentation agent khi startup | Không phải yêu cầu dynamic attach |
| `-agentlib:name` / `-agentpath:path` | Nạp native JVMTI agent khi startup | Không thay thế Java instrumentation JAR |
| `-XX:+EnableDynamicAgentLoading` | Cho phép dynamic agent loading theo policy runtime hỗ trợ | Không tự khởi tạo agent, không bỏ qua mọi OS permission |
| `-XX:-EnableDynamicAgentLoading` | Từ chối dynamic agent loading theo policy runtime | Không nhất thiết vô hiệu hóa mọi công cụ attach |
| `-XX:+DisableAttachMechanism` | Vô hiệu/giới hạn attach mechanism trên runtime hỗ trợ | Không phải công cụ chỉ để ẩn warning |
| `-Djdk.instrument.traceUsage` | Truy vết sử dụng instrumentation theo runtime hỗ trợ | Không cấp quyền nạp agent |
| `-Djdk.attach.allowAttachSelf=true` | Cho phép self-attach ở các runtime áp dụng hạn chế này | Không bảo đảm dynamic loading được phép |

Các `-XX` flags là tùy chọn JVM implementation-specific. Nếu runtime dùng một JVM vendor/implementation khác HotSpot hoặc một custom image, cần kiểm tra danh sách flags được hỗ trợ và ý nghĩa thực tế.

## 8. Một kịch bản test để phân biệt warning với blocking

Giả sử có một target JVM chạy ứng dụng:

```shell
java -jar application.jar
```

Và một công cụ quản trị có quyền phù hợp gọi `VirtualMachine.loadAgent(...)` vào PID của target.

### 8.1. Trên JDK 21 với cấu hình mặc định phù hợp JEP 451

Trong trường hợp dynamic loading được cho phép theo mặc định, agent có thể được nạp, đồng thời JVM đích phát cảnh báo. Công cụ và ứng dụng phải được kiểm tra để xác nhận `agentmain` thực sự chạy.

### 8.2. Cho phép nạp động có chủ đích

Target được khởi động với:

```shell
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

Nếu runtime hỗ trợ và quyền attach hợp lệ, việc nạp động có thể tiếp tục. Trên JDK 21, đây cũng là cách khai báo explicit permission nhằm tránh warning tương ứng.

### 8.3. Thử nghiệm đường bị từ chối

Target được khởi động với:

```shell
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

Lệnh attach yêu cầu nạp Java/JVMTI agent có thể thất bại. Hãy ghi nhận exception/message thực tế và xác nhận ứng dụng hoặc test suite có cơ chế fallback phù hợp.

Không coi việc công cụ attach thất bại là bug JDK ngay lập tức: chính sách đã được cấu hình để từ chối thao tác đó.

### 8.4. Tách “agent load” khỏi “attach diagnostics”

Một số lệnh serviceability giao tiếp với JVM bằng cơ chế attach nhưng không tải một Java/JVMTI agent theo nghĩa của JEP 451. Không nên suy từ việc chặn dynamic agent loading rằng **mọi** lệnh `jcmd` đều sẽ thất bại.

Ngược lại, nếu vô hiệu hóa toàn bộ Attach Mechanism, một số công cụ chẩn đoán phụ thuộc attach có thể không kết nối được. Hãy thử riêng các use cases vận hành quan trọng.

## 9. Tình huống test framework: Mockito, Byte Buddy và inline mocking

### 9.1. Vì sao unit test có thể phát warning dù ứng dụng không dùng agent?

Một số framework mocking và bytecode tools có thể dùng Java instrumentation để mock các class hoặc phương thức mà proxy thông thường khó thay thế. Khi không có Instrumentation instance được cung cấp từ startup, chúng có thể dùng self-attachment hoặc một cơ chế động để lấy quyền instrument JVM test.

Vì vậy log test có thể có cảnh báo agent dù source application không chứa `VirtualMachine.attach`.

Ví dụ thường gặp là những cấu hình Mockito/Byte Buddy sử dụng inline instrumentation. Hành vi chính xác phụ thuộc phiên bản library, plugin và cấu hình test; không nên khẳng định mọi phiên bản Mockito đều bắt buộc tự attach.

### 9.2. Nhận diện thành phần thực sự nạp agent

Kiểm tra:

- Stack trace hoặc đường dẫn JAR trong warning.
- Resolved test-runtime dependency graph.
- Phiên bản Mockito, Byte Buddy và thư viện Byte Buddy agent.
- Plugin JUnit/TestNG và build tool.
- Các `jvmArgs` của test JVM.
- Tài liệu migration của đúng phiên bản mocking framework.
- Có một `-javaagent` nào đã được cấu hình tại startup chưa?

Nếu warning xuất hiện **chỉ khi chạy tests**, đừng vội thêm `-XX:+EnableDynamicAgentLoading` vào toàn bộ production JVM. Hãy xử lý tại scope test.

### 9.3. Ưu tiên agent startup nếu framework hỗ trợ

Một cách tiếp cận bền vững là cấp agent cần thiết cho JVM test qua `-javaagent`, thay vì để thư viện tự attach lúc đang chạy.

Ví dụ hình thức lệnh:

```shell
java -javaagent:/opt/test-agents/mock-agent.jar \
     -cp "test-classes:dependencies/*" \
     com.example.RunTests
```

Đây là cấu trúc minh họa; `mock-agent.jar` không phải tên artifact thực tế bắt buộc của Mockito. Với framework đang sử dụng, phải xác nhận **artifact nào được công bố là Java agent**, cách khai báo trong manifest và mức hỗ trợ JDK.

Không đưa một JAR bất kỳ vào `-javaagent` chỉ vì nó là dependency của Mockito/Byte Buddy.

### 9.4. Gradle: truyền agent vào JVM test

Nếu build sử dụng Gradle, các test JVM có thể được cấu hình `jvmArgs` hoặc `jvmArgumentProviders`. Ví dụ đơn giản với agent JAR đã được tạo riêng trong một vị trí được quản trị:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs "-javaagent:/opt/test-agents/test-agent.jar"
}
```

Đây là mẫu cú pháp, không phải cấu hình portable nên sao chép nguyên xi. Trong dự án thực tế, nên resolve agent qua dependency configuration hoặc provider, dùng path tương ứng trên Windows/Linux và tránh hard-code đường dẫn máy developer.

Nếu Gradle chạy nhiều test tasks, phải xác định task nào thật sự cần instrumentation, ví dụ unit tests so với integration tests, để không nạp agent không cần thiết vào tất cả JVM.

### 9.5. Maven Surefire/Failsafe: giữ các JVM arguments khác

Maven Surefire hoặc Failsafe có thể cho phép đặt `argLine` để truyền `-javaagent` cho test JVM. Tuy nhiên, `argLine` có thể đang được JaCoCo hoặc plugin khác chỉnh sửa.

Nếu cấu hình mới ghi đè toàn bộ `argLine`, bạn có thể vô tình làm mất code coverage hoặc các JVM flags đang cần.

Nguyên tắc migration:

1. Xác định ai đang quản lý `argLine` hiện tại.
2. Dùng cơ chế phối hợp giá trị/late interpolation mà phiên bản plugin hỗ trợ.
3. Đảm bảo agent path được resolve trước khi test JVM khởi chạy.
4. Không đặt agent vào JVM Maven chính khi chỉ test JVM cần.
5. Chạy thử coverage và mocking cùng lúc.

`-XX:+EnableDynamicAgentLoading` có thể là cách trì hoãn migration có kiểm soát, nhưng không nên là giải pháp dài hạn nếu test framework đã hỗ trợ khai báo startup agent.

### 9.6. Không vô hiệu hóa warning bằng cách bỏ qua log

Một pipeline có thể filter toàn bộ dòng `WARNING` khiến CI “xanh đẹp”, nhưng đây là cách che giấu một dependency vào dynamic instrumentation có thể không còn hoạt động trong tương lai.

Nên sửa cấu hình test hoặc pin/cập nhật phiên bản framework được hỗ trợ, rồi có một test xác nhận hành vi mocking thật sự còn đúng khi dynamic loading bị từ chối.

## 10. APM, profiling và production observability

### 10.1. Agent APM thường được nạp từ startup

Một ví dụ JVM service:

```shell
java -javaagent:/opt/agents/apm-agent.jar \
     -Dservice.name=orders \
     -jar orders-service.jar
```

Cách này làm startup ownership và phiên bản agent dễ kiểm soát hơn. Một số sản phẩm có khả năng attach vào process đang chạy, nhưng cần xem chính sách JDK và hướng dẫn của vendor.

### 10.2. Dynamic profiling có thể là nhu cầu vận hành hợp lệ

Khi service production gặp vấn đề, một công cụ được ủy quyền có thể cần attach để bật profiler hoặc instrument một phần hệ thống mà không restart. Đây là tình huống mà tổ chức phải quyết định quyền lợi vận hành và rủi ro về tính toàn vẹn.

Không có một lựa chọn duy nhất phù hợp mọi dịch vụ:

- Dịch vụ yêu cầu integrity cao có thể tắt dynamic agent loading mặc định.
- Dịch vụ cần chẩn đoán đặc biệt có thể bật có kiểm soát.
- Có thể ưu tiên JFR, thread dump, heap dump hoặc metrics có sẵn nếu đủ để điều tra.
- Một số môi trường cần một luồng thay đổi/khởi động lại để bật agent.
- Cần audit việc ai đã dùng công cụ và trên PID nào.

### 10.3. JFR và công cụ chẩn đoán không nhất thiết là Java agent

Java Flight Recorder (JFR) là khả năng quan sát JVM có thể được cấu hình qua JVM flags hoặc serviceability tools trên runtime phù hợp. Nó không mặc nhiên đồng nghĩa dùng `VirtualMachine.loadAgent` để nạp một Java instrumentation agent.

Ví dụ khởi động một recording theo khả năng HotSpot hỗ trợ:

```shell
java -XX:StartFlightRecording=filename=service.jfr \
     -jar application.jar
```

Trên runtime phù hợp, `jcmd` có các lệnh liên quan JFR. Tuy nhiên, việc dùng `jcmd` có thể phụ thuộc Attach Mechanism và quyền process; không nên coi JFR là không có điều kiện môi trường.

Khi migration, hãy kiểm tra tool đang dùng có thật sự **dynamic-load agent** hay chỉ yêu cầu JVM thực hiện một diagnostic command.

## 11. Java agent và JVMTI native agent: khác biệt khi chuyển hệ điều hành

### 11.1. Startup native agent

Ví dụ:

```shell
java -agentlib:observe=mode=sample -jar application.jar
```

Hoặc:

```shell
java -agentpath:/opt/agents/libobserve.so \
     -jar application.jar
```

Đây là ví dụ cú pháp, không có bảo đảm thư viện `observe` tồn tại. Native library phải được build cho OS/architecture/ABI tương ứng.

### 11.2. Dynamic native agent

Attach API cũng có những phương thức dành cho native agent, ví dụ `loadAgentLibrary` hoặc `loadAgentPath` tùy trường hợp. Chính sách dynamic agent loading có thể ảnh hưởng đường này; không chỉ Java `-javaagent` mới cần quan tâm.

Khi điều tra, cần hỏi:

- Agent là Java JAR hay native shared library?
- Được nạp khi startup hay sau startup?
- Agent cần JVMTI capabilities nào?
- Library có phù hợp OS, CPU architecture và libc?
- Native symbol entry point có đúng không?
- Dùng đúng vendor JVM và supported JVMTI version chưa?

### 11.3. Bytecode compatibility khác native compatibility

Một Java agent JAR có thể mang bytecode Java 17 và chạy trên JDK 21, nhưng native companion library có thể chỉ hỗ trợ Linux x86_64. Ngược lại, một native agent có thể load được nhưng dùng các JVMTI events/capabilities khác nhau theo phiên bản JVM.

Đừng cố chữa `UnsatisfiedLinkError` bằng `EnableDynamicAgentLoading`. Đây là hai nhóm lỗi khác nhau.

## 12. Module access, instrumentation và giới hạn biến đổi class

### 12.1. Java agent không thể sửa mọi class tùy ý

`Instrumentation` có các API:

```java
boolean isRedefineClassesSupported();
boolean isRetransformClassesSupported();
boolean isModifiableClass(Class<?> type);
```

Khi dùng transformer hoặc redefinition, agent phải tuân theo những giới hạn class-file và runtime. Một số thay đổi cấu trúc class như thêm/bớt method/field hay thay hierarchy bị hạn chế trong cơ chế redefinition thông thường.

Ví dụ kiểm tra:

```java
public static void agentmain(
        String options,
        java.lang.instrument.Instrumentation instrumentation) {

    System.out.println(
        "Retransform supported: "
        + instrumentation.isRetransformClassesSupported()
    );
}
```

Một agent nạp thành công chưa chắc instrument class thành công.

### 12.2. JDK mới có class-file version mới

Nếu ứng dụng chuyển sang JDK 21 hoặc 25, compiler có thể tạo class files với major mới. Agent dùng phiên bản ASM/Byte Buddy/Javassist cũ có thể không hiểu định dạng class mới, gây lỗi bytecode parsing hoặc instrumentation.

Quy trình kiểm tra:

1. Xác định class-file major của ứng dụng và libraries.
2. Xác định version bytecode library mà agent sử dụng.
3. Đối chiếu release notes của agent/bytecode library.
4. Chạy startup và dynamic agent tests nếu cả hai được hỗ trợ.
5. Không chỉ kiểm tra agent load thành công; phải kiểm tra chức năng tracing/mocking.
6. Ghi nhận agent version trong release metadata.

### 12.3. JPMS encapsulation là một trục khác

Từ JDK 9, module system quản lý readability, exports và opens. Một agent hoặc thư viện mà agent dùng có thể gặp:

```text
java.lang.reflect.InaccessibleObjectException
```

Giải pháp thích hợp có thể là cập nhật agent/framework để dùng API được hỗ trợ hoặc thiết lập quyền module có phạm vi rõ. `Instrumentation.redefineModule` cung cấp khả năng điều chỉnh quan hệ module trong những trường hợp phù hợp; startup `--add-opens` cũng có thể là biện pháp có kiểm soát.

Nhưng **`--add-opens` không biến một JVM cấm nạp agent động thành JVM cho phép**. Tách hai câu hỏi:

- Agent có được **nạp** vào JVM không?
- Agent đã nạp có được **truy cập/instrument** những lớp mục tiêu không?

Nếu trả lời sai tầng, một đội sẽ tiếp tục thêm JVM flags mà không sửa được lỗi.

### 12.4. Virtual threads và instrumentation

Khi nâng lên JDK có virtual threads, APM hoặc profiling agent có thể cần cập nhật cách ghi nhận thread context, stack frames và tracing. Dynamic loading policy không phải nguyên nhân duy nhất khiến agent cũ hoạt động khác.

Khi ứng dụng thực sự dùng virtual threads, hãy xác minh support matrix của agent và test propagation/tracing, thay vì chỉ kiểm tra JVM flags.

## 13. Vấn đề bảo mật và tính toàn vẹn

### 13.1. Vì sao JDK quan tâm đến dynamic loading?

Một agent có quyền instrument bytecode và quan sát runtime có thể ảnh hưởng tính toàn vẹn ứng dụng. Nếu thư viện tự attach mà không có quyết định rõ từ người vận hành, một ứng dụng đang chạy có thể bị thay đổi hành vi sau startup.

JEP 451 hướng tới việc giúp người vận hành quản trị ranh giới này. Đó không phải bằng chứng mọi agent đều nguy hiểm, mà là yêu cầu quyền nạp agent phải rõ ràng.

### 13.2. Nạp agent không được xem như thao tác vô hại

Một agent có thể:

- Đọc thông tin heap hoặc class metadata theo API được cấp.
- Ghi instrumentation data có khả năng chứa dữ liệu nhạy cảm.
- Thay đổi behavior của class khi được hỗ trợ.
- Tăng overhead CPU, memory hoặc latency.
- Can thiệp startup/classloading và gây deadlock hoặc crash nếu lỗi.
- Nạp native code với rủi ro về bộ nhớ/ABI.

Vì vậy, cần kiểm soát artifact origin, version, quyền cấu hình JVM và audit trail. Agent cũng là một phần của software supply chain.

### 13.3. Least privilege và khả năng chẩn đoán

Một chính sách vận hành có thể quy định:

- Chỉ cho startup agents được phê duyệt trong môi trường production tiêu chuẩn.
- Không bật dynamic agent loading mặc định nếu không cần.
- Quyền truy cập PID và JVM diagnostic interfaces thuộc nhóm operator được ủy quyền.
- Nếu cần bật dynamic loading, phải có change record và thời hạn.
- Cần duy trì đường lấy thread dump/JFR/metrics phù hợp để không mất khả năng ứng cứu.
- Truyền secrets vào agent qua cơ chế an toàn, không hard-code vào JVM command line nếu có thể.

Không nên đưa `-XX:+DisableAttachMechanism` vào mọi service chỉ để giảm surface mà không đánh giá hậu quả cho incident response.

### 13.4. JVM flag không phải lớp bảo vệ duy nhất

Quyền OS, container namespace, service account, filesystem permissions và runtime configuration cùng quyết định khả năng tương tác với process. Ngay cả khi một JVM cấm dynamic agent loading, nó không trở thành một sandbox hoàn chỉnh trước attacker đã có quyền tương đương process owner hoặc quyền hệ điều hành cao hơn.

Ngược lại, cho phép dynamic loading không đồng nghĩa mọi người dùng trên máy đều attach được: OS-level access vẫn có vai trò.

## 14. Tình huống Docker, Kubernetes và custom runtime image

### 14.1. Container làm thay đổi môi trường attach

Trong container, công cụ bên ngoài có thể không nhìn thấy PID hoặc process namespace như host. `jcmd -l` và cơ chế attach có thể cần quyền OS, filesystem/temporary directory và môi trường tương ứng.

Các vấn đề thường gặp:

- PID trong container khác PID trên host.
- Sidecar không chia sẻ process namespace.
- User/group của tool không khớp user chạy Java.
- Security policy/container profile giới hạn thao tác.
- Runtime image không chứa công cụ JDK hoặc module cần thiết.
- Filesystem tạm thời hoặc quyền ghi không phù hợp với attach implementation.
- JDK đích có policy dynamic loading bị tắt.

Không khắc phục bằng cách cấp đặc quyền container quá rộng chỉ vì một công cụ attach không hoạt động. Hãy xác định yêu cầu quyền cụ thể và cân nhắc startup instrumentation.

### 14.2. Startup agent trong container

Một cơ chế rõ ràng:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application.jar /app/application.jar
COPY agents/observe-agent.jar /opt/agents/observe-agent.jar
ENTRYPOINT ["java", "-javaagent:/opt/agents/observe-agent.jar", "-jar", "/app/application.jar"]
```

Đây là Dockerfile minh họa, chưa nêu chính sách image digest, user không đặc quyền hoặc các yêu cầu supply chain. Agent JAR phải tồn tại trong build context và tương thích runtime.

Nếu application image không chủ đích dùng dynamic attach, startup agent giúp mô tả chính xác trạng thái instrumentation từ lúc container bắt đầu.

### 14.3. Không giả định base image có công cụ JDK

Một image chỉ chứa JRE hoặc `jlink` runtime có thể không có:

```text
jcmd
jps
javac
jdk.attach
```

Từng thành phần cần được kiểm tra riêng. Công cụ chẩn đoán có thể chạy từ một image quản trị khác nếu kiến trúc, permissions và chính sách tổ chức cho phép.

### 14.4. Kubernetes sidecar hoặc ephemeral container

Một profiler được khởi chạy trong sidecar/ephemeral container có thể gặp hai loại hạn chế:

1. **Kubernetes/OS:** PID namespace và quyền truy cập process.
2. **JVM:** Attach Mechanism và dynamic agent loading policy.

Nếu sidecar nhìn thấy PID nhưng JVM không cho phép nạp agent, việc thay đổi namespace không giải quyết vấn đề. Nếu JVM cho phép nạp động nhưng sidecar không có quyền OS, thêm `EnableDynamicAgentLoading` cũng không đủ.

## 15. Chẩn đoán bằng công cụ hệ thống

### 15.1. Xác định JDK của JVM đích

Không suy từ `java -version` trong terminal của người vận hành nếu ứng dụng được chạy bằng một đường dẫn JVM khác. Cần kiểm tra command line thực tế của service, container image và thông tin JDK runtime.

Trên runtime cho phép attach, một lệnh hữu ích:

```shell
jcmd <pid> VM.version
```

Thay `<pid>` bằng PID thực tế; ví dụ syntax chỉ áp dụng khi `jcmd` khả dụng và có quyền tương tác.

### 15.2. Kiểm tra JVM flags

```shell
jcmd <pid> VM.flags
```

Hoặc:

```shell
jcmd <pid> VM.command_line
```

Đây là những cách thu thập thông tin trên runtime hỗ trợ serviceability interface. Nếu JVM đã vô hiệu hóa Attach Mechanism, những lệnh này có thể không hoạt động. Khi đó, dùng startup logs, deployment manifests hoặc thông tin cấu hình đã được lưu.

### 15.3. Phân biệt mục tiêu “có agent” và “nạp động”

Một log chỉ cho biết `premain` được gọi không chứng minh Attach API đang được dùng. Một warning JEP 451 thường gắn với đường nạp động. Khi điều tra, cần tìm:

- `-javaagent` trong startup args.
- `-agentlib`/`-agentpath` trong startup args.
- Log `agentmain` của agent.
- Dòng warning có đường dẫn agent JAR/native library.
- Stack trace từ thư viện self-attach.
- Cơ chế APM/profiler CLI được vận hành.
- Flags `EnableDynamicAgentLoading` và `DisableAttachMechanism`.

Truy vết bằng chứng nguồn, không chỉ đoán theo tên JAR.

### 15.4. Không in secrets trong diagnostics

JVM command line, system properties và agent options đôi khi chứa dữ liệu nhạy cảm. Khi chia sẻ logs cho vendor hoặc đưa vào CI artifacts, phải redact token, password, credentials và đường dẫn nhạy cảm.

## 16. Troubleshooting: cảnh báo và lỗi thường gặp

### 16.1. Chỉ có warning, test vẫn chạy

**Triệu chứng:**

```text
WARNING: A Java agent has been loaded dynamically (...)
BUILD SUCCESSFUL
```

**Nguyên nhân khả dĩ:** một mocking/instrumentation library tự nạp agent trong test JVM trên JDK 21 hoặc runtime có policy tương tự.

**Hướng xử lý:** xác định dependency nào thực hiện attach, kiểm tra tài liệu phiên bản mới, ưu tiên startup agent trong test khi được hỗ trợ. Không mặc định thêm flag cho production.

### 16.2. Dynamic loading bị từ chối

**Triệu chứng:** attach client báo lỗi nạp agent hoặc runtime nói dynamic agent loading không được cho phép.

**Nguyên nhân khả dĩ:** target JVM dùng `-XX:-EnableDynamicAgentLoading` hoặc mặc định của phiên bản/vendor đã thay đổi; cũng có thể thiếu capability/permission ở tầng khác.

**Hướng xử lý:** xác minh runtime target version và flags; quyết định có cấp quyền nạp động không. Nếu đây là hoạt động có chủ đích, cấu hình quyền phù hợp từ startup hoặc chuyển sang startup agent. Không cố bỏ qua security policy.

### 16.3. `AttachNotSupportedException`

**Triệu chứng:** không attach được vào PID.

**Nguyên nhân khả dĩ:** PID sai, process không phải JVM hỗ trợ attach, khác user/permission, container namespace, Attach Mechanism bị tắt hoặc runtime image thiếu thành phần.

**Hướng xử lý:** xác nhận PID, runtime, quyền, container và cơ chế attach. Cần phân biệt attach thất bại **trước khi** đến bước load agent với việc agent bị policy dynamic loading chặn.

### 16.4. `AgentLoadException`

**Triệu chứng:** attach có thể kết nối nhưng `loadAgent` hoặc loader liên quan thất bại.

**Nguyên nhân khả dĩ:** policy không cho nạp động, agent JAR/native library không tồn tại, manifest/entry point sai hoặc lỗi loader.

**Hướng xử lý:** đọc cause và log JVM đích; kiểm tra Agent-Class, path, flags và môi trường, không chỉ bắt exception rồi thử lại không giới hạn.

### 16.5. `AgentInitializationException`

**Triệu chứng:** JVM đã cố khởi tạo agent nhưng entry point hoặc logic agent lỗi.

**Nguyên nhân:** exception trong `agentmain`, dependency thiếu, option sai hoặc lỗi instrumentation.

**Hướng xử lý:** đọc agent log/stack trace và test agent riêng với đúng JDK; không giả định là lỗi permission.

### 16.6. `ClassNotFoundException` hoặc `NoClassDefFoundError` từ agent

**Nguyên nhân:** agent packaging thiếu dependency hoặc classloading/module visibility không đúng.

**Hướng xử lý:** kiểm tra JAR manifest, runtime classpath/module path, embedded dependencies và phiên bản JDK. Đưa `-XX:+EnableDynamicAgentLoading` vào không bổ sung class bị thiếu.

### 16.7. `InaccessibleObjectException` sau khi agent đã nạp

**Nguyên nhân:** strong encapsulation/JPMS từ chối reflection.

**Hướng xử lý:** cập nhật agent/framework hoặc cấp opens có phạm vi chính xác theo tài liệu. Đây là vấn đề **access sau khi nạp**, không phải **quyền nạp động**.

### 16.8. Lỗi đọc class version mới

**Triệu chứng:** transformer báo unsupported class-file major version, không instrument được class hoặc test fail sau khi nâng JDK.

**Nguyên nhân:** ASM/Byte Buddy/Javassist/agent quá cũ so với bytecode target.

**Hướng xử lý:** nâng agent và bytecode tool theo support matrix, chạy regression tests và kiểm tra output trên JDK đích.

### 16.9. Agent được load nhưng không có dữ liệu tracing

**Nguyên nhân khả dĩ:** instrument nhầm classloader, không retransform những class đã nạp, cấu hình filter sai, sampling tắt, network exporter lỗi hoặc agent/runtime incompatibility.

**Hướng xử lý:** kiểm tra capability, target class selection, exporter connection, config và runtime metrics. Không chỉ xem “agentmain called” là đã hoàn thành tính năng.

### 16.10. `jcmd` không chạy sau khi hardening

**Nguyên nhân khả dĩ:** `-XX:+DisableAttachMechanism` hoặc quyền/namespace bị giới hạn.

**Hướng xử lý:** xem xét lại chính sách hardening và cơ chế incident response; không cần thiết phải bật mọi dynamic agent loading để lấy mọi diagnostic data, nhưng cần có đường hỗ trợ công cụ tương ứng.

## 17. Chọn chiến lược migration

### 17.1. Chiến lược A: chuyển sang startup agent

Phù hợp khi agent được dùng thường xuyên cho APM, tracing hoặc mocking/instrumentation trong một test suite.

Các bước:

1. Xác định artifact agent được vendor/framework hỗ trợ.
2. Pin version của agent theo support matrix với JDK đích.
3. Cấu hình `-javaagent` cho JVM cần sử dụng.
4. Bỏ đường self-attach/dynamic attach không còn cần.
5. Chạy test startup, instrumentation, performance và shutdown.
6. Đảm bảo đường dẫn agent tồn tại trong container/CI.
7. Ghi rõ agent version, options và ownership trong release metadata.

Ưu điểm là quyền instrumentation được thể hiện rõ trong startup configuration.

### 17.2. Chiến lược B: giữ dynamic loading có kiểm soát

Phù hợp khi nhu cầu thật sự là attach vào JVM đang chạy trong quá trình điều tra sự cố.

Các bước:

1. Kiểm tra JVM target JDK/version/vendor hỗ trợ đường nạp động.
2. Quyết định có bật explicit `EnableDynamicAgentLoading` không.
3. Giới hạn quyền OS và quyền dùng công cụ.
4. Quản lý agent binaries và phiên bản được phê duyệt.
5. Audit sự kiện/command attach khi hạ tầng hỗ trợ.
6. Kiểm tra trong staging với policy tương ứng production.
7. Có phương án thay thế khi một JDK tương lai thay đổi default hoặc không hỗ trợ như trước.

Đừng bật quyền trên toàn bộ fleet nếu chỉ một nhóm service cần nạp động.

### 17.3. Chiến lược C: thay bằng khả năng quan sát tích hợp

Nếu mục đích của agent chỉ là lấy số liệu hoặc chẩn đoán, có thể xem xét:

- JFR và JDK-supported diagnostic commands.
- Metrics mà ứng dụng đã xuất qua endpoint.
- Structured logging và distributed tracing instrumented từ source.
- Async profiling/monitoring tools được xác nhận hỗ trợ JDK mà không yêu cầu cùng kiểu dynamic agent loading.
- Heap/thread dumps theo cơ chế quản trị được hỗ trợ.

Không phải mọi tính năng agent đều có một bản thay thế tương đương. Cần đánh giá data fidelity, overhead và mức truy cập thực sự cần thiết.

### 17.4. Chiến lược D: giữ thư viện/framework trong trạng thái được hỗ trợ

Nếu một dependency tự attach do phiên bản cũ, trước khi thêm workaround JVM dài hạn hãy kiểm tra:

- Bản thư viện mới có hỗ trợ JEP 451 hoặc JDK target chưa?
- Có hướng cấu hình agent startup chính thức không?
- Phiên bản mới có thay đổi cơ chế mocking/profiling không?
- Build plugin có cung cấp tùy chọn tự cấp `-javaagent` không?
- Có thể tạm vô hiệu hóa tính năng instrumentation không cần thiết không?

Workaround có thể hữu ích khi phát hành khẩn cấp, nhưng phải có owner và kế hoạch xử lý nợ kỹ thuật.

## 18. Quy trình migration thực hành qua các bước

### Giai đoạn 1: Inventory agents và attach paths

Tìm trong repository/configuration:

```text
-javaagent
-agentlib
-agentpath
EnableDynamicAgentLoading
DisableAttachMechanism
jdk.attach.allowAttachSelf
jdk.instrument.traceUsage
VirtualMachine.attach
loadAgent
loadAgentLibrary
loadAgentPath
ByteBuddyAgent
Mockito
java.instrument
jdk.attach
```

Một số truy vấn ban đầu với ripgrep:

```shell
rg -n "javaagent|agentlib|agentpath|EnableDynamicAgentLoading" .
rg -n "VirtualMachine[.]attach|loadAgent|ByteBuddyAgent" .
rg -n "Mockito|mockito|byte-buddy|jacoco|apm" .
```

Lưu ý đường nạp agent có thể nằm trong CI configuration ngoài repo, service unit, Helm chart, container entrypoint hoặc vendor launcher. Kết quả source search không phải inventory đầy đủ.

### Giai đoạn 2: Phân loại từng agent

| Agent | Môi trường | Cách nạp | Owner | Có bắt buộc? | Đề xuất |
|---|---|---|---|---|---|
| Unit-test mocking | CI | Self-attach có thể xảy ra | Dev team | Theo test feature | Ưu tiên startup test agent khi hỗ trợ |
| APM | Production | Startup `-javaagent` | SRE | Có | Giữ startup, nâng version theo JDK |
| Incident profiler | Staging/production | Attach khi cần | SRE/Platform | Theo sự cố | Quyền nạp động có kiểm soát |
| Native monitoring | Production | `-agentlib`/dynamic JVMTI | Platform | Tùy yêu cầu | Kiểm tra native ABI và JVMTI |
| Legacy helper | Build/CI | Không rõ | Build team | Cần xác minh | Truy vết và loại bỏ nếu không còn dùng |

Bảng là ví dụ mẫu. Cần điền actual agent versions, paths và runtime của hệ thống.

### Giai đoạn 3: Thu thập baseline

Ghi:

- JDK vendor, release, update level.
- Framework, test tool và agent versions.
- Startup JVM flags.
- OS/architecture và container image digest.
- Cách nạp agent: startup, external attach, self-attach.
- Cảnh báo/exception hiện có.
- Test kết quả instrumentation thật.
- Tác động hiệu năng và startup time.

Đây là dữ liệu giúp xác định một thay đổi do JDK policy, do agent version hay do deployment configuration.

### Giai đoạn 4: Thử chế độ hạn chế từ sớm

Trên một runtime HotSpot hỗ trợ flag, chạy test với:

```shell
java -XX:-EnableDynamicAgentLoading ...
```

Ý nghĩa là mô phỏng môi trường mà dynamic agent loading không được phép, trong khi các startup agents được khai báo rõ vẫn có thể sử dụng theo policy tương ứng.

Nếu test thất bại:

1. Xác định code/tool đang cố attach.
2. Kiểm tra đó là nhu cầu thật hay behavior ngầm của thư viện.
3. Thử cấu hình startup agent được hỗ trợ.
4. Kiểm tra không mất coverage/mocking/tracing.
5. Cập nhật CI và tài liệu deployment.

Lưu ý đây là **test về quyền nạp động**, không phải Content QA hay test mọi tính năng JVM.

### Giai đoạn 5: Thử trên JDK đích

Chạy ma trận:

```text
JDK cũ + agent cũ                -> baseline
JDK mới + agent cũ               -> phát hiện lỗi
JDK mới + agent mới              -> ứng viên
JDK mới + startup agent          -> phương án chính
JDK mới + dynamic loading off    -> kiểm tra phụ thuộc ngầm
JDK mới + dynamic loading on     -> kiểm tra use case quản trị
```

Không bắt buộc mọi ứng dụng phải thử mọi dòng nếu không sử dụng agent. Nhưng khi có agent/JVMTI trong stack, cần xác định đường nạp thực tế.

### Giai đoạn 6: Release và vận hành

- Thêm config agent vào deployment-as-code.
- Pin agent version và provenance.
- Tách test-only flags khỏi production flags.
- Không hard-code đường dẫn JAR theo máy cá nhân.
- Có policy cho phép/hạn chế dynamic attach theo môi trường.
- Đảm bảo SRE có đường chẩn đoán khi cần.
- Theo dõi log warning/agent initialization errors.
- Có rollback nếu agent làm giảm hiệu năng hoặc gây crash.

## 19. Kiểm tra trên CI và test suite

### 19.1. Ma trận tối thiểu

| Kịch bản | Mục tiêu |
|---|---|
| Test JVM với JDK hiện tại | Baseline các framework instrumentation |
| Test JVM với JDK đích | Phát hiện warning/exception mới |
| JDK đích + startup agent | Xác nhận đường không phụ thuộc dynamic attach |
| JDK đích + dynamic loading disabled | Bắt các trường hợp tự attach bị bỏ sót |
| Production-like startup | Xác nhận agent arguments, image và quyền |
| Agent functionality tests | Không chỉ “test process chạy”, phải kiểm tra chức năng agent |

### 19.2. Test thực sự có sử dụng instrumentation

Nếu mục đích của agent là inline mocking, một test chỉ chạy `assertTrue(true)` không xác minh khả năng mocking.

Nếu mục đích là APM, một smoke test có thể cần kiểm tra trace/span được xuất đúng sau một HTTP request; nếu mục đích là profiler, cần xác nhận dữ liệu lấy được bằng công cụ được cấp quyền.

Không nhất thiết viết toàn bộ test integration cho từng agent; nhưng ít nhất một test phải thực thi **tính năng khiến agent tồn tại**.

### 19.3. Failure phải báo rõ nguyên nhân

Một test harness tốt nên phân biệt:

```text
ATTACH_UNAVAILABLE
DYNAMIC_AGENT_LOADING_DISABLED
AGENT_JAR_NOT_FOUND
AGENT_ENTRYPOINT_INVALID
AGENT_INITIALIZATION_FAILED
BYTECODE_TRANSFORM_FAILED
MODULE_ACCESS_DENIED
INSTRUMENTATION_FEATURE_FAILED
```

Đây là các nhãn chẩn đoán đề xuất, không phải mã lỗi chuẩn của JVM. Phân loại giúp tránh một workaround sai như bật `--add-opens` khi vấn đề thật là dynamic loading bị từ chối.

### 19.4. Không tự động thêm startup flag cho mọi tiến trình

Nếu test framework cần agent, hãy cấu hình **test JVM**. Nếu APM production cần startup agent, hãy cấu hình **service JVM**. Không nên thêm `JAVA_TOOL_OPTIONS` toàn hệ thống một cách tùy tiện, vì nó có thể ảnh hưởng compiler, build tools, command-line utilities hoặc các JVM khác được chạy trong cùng môi trường.

## 20. Chẩn đoán an toàn khi cảnh báo xuất hiện trong production

Một quy trình phản ứng ngắn:

1. Ghi thời điểm, service/PID/container và JDK runtime.
2. Lưu warning cùng đường dẫn agent đã được redact nếu cần.
3. Kiểm tra agent có trong danh sách approved artifacts không.
4. Xác định hoạt động attach do operator, profiler hoặc thư viện nào khởi xướng.
5. Xem startup flags và policy về dynamic loading.
6. Kiểm tra agent đã instrument đúng và có gây hiệu năng bất thường không.
7. Nếu không được phép, áp dụng quy trình incident response và giới hạn quyền phù hợp.
8. Nếu được phép nhưng chưa khai báo rõ, cập nhật deployment/runbook.
9. Lên lộ trình thay self-attach bằng startup agent hoặc cơ chế tương đương nếu được hỗ trợ.
10. Test lại trên JDK release mục tiêu trước khi rollout.

Không kết luận “có attacker” chỉ vì thấy warning. Đồng thời, cũng không bỏ qua một agent lạ vì “mọi thư viện đều có thể tự attach”.

## 21. Những sai lầm migration cần tránh

### 21.1. Nghĩ JDK 21 đã cấm mọi agent

Không đúng về mặt khái niệm. JEP 451 cảnh báo và chuẩn bị giới hạn **dynamic loading**. Startup agents được khai báo rõ là một cơ chế khác.

### 21.2. Nghĩ một warning luôn là lỗi runtime

Không nhất thiết. Agent có thể hoạt động bình thường nhưng dùng cơ chế mà JVM muốn đưa ra cảnh báo để operator nhận biết.

### 21.3. Chỉ bật `EnableDynamicAgentLoading` để log hết warning

Nếu ứng dụng không có nhu cầu nạp động, việc bật quyền chỉ để loại cảnh báo làm tăng phạm vi cho phép mà không giải quyết dependency ngầm. Hãy tìm source và cân nhắc startup agent.

### 21.4. Dùng `DisableAttachMechanism` mà không nghĩ đến SRE

Vô hiệu hóa toàn bộ attach có thể làm nhiều công cụ chẩn đoán mất tác dụng. Đây là quyết định vận hành/security, không chỉ là một dòng build flags.

### 21.5. Nhầm self-attach với external attach

`jdk.attach.allowAttachSelf` liên quan self-attach trong những runtime phù hợp; không thay thế policy dynamic loading và không sửa permission của một external tool.

### 21.6. Chỉ thêm `--add-opens` khi gặp lỗi attach

Module opens giải quyết một loại quyền truy cập sau khi code đã nạp. Nó không thể biến một tác vụ bị chặn ở tầng nạp agent thành hợp lệ.

### 21.7. Nâng JDK mà giữ nguyên mọi agent binary

Bytecode libraries, native JVMTI, instrumentation rules và JVM internals có thể thay đổi. Phải đọc compatibility matrix của agent theo JDK target.

### 21.8. Để test framework tự attach mà không biết

Lúc test chạy trên JDK mới, sự phụ thuộc ngầm có thể trở thành blocker. Nên pin version tool và cấu hình startup agent nếu framework hỗ trợ.

### 21.9. Dùng kết quả từ developer laptop làm kết luận production

Container/JRE image, OS permissions, PID namespaces, JDK vendor và startup flags khác nhau. Test cần sát deployment thực tế.

### 21.10. Dùng warning text để đoán policy của mọi JDK sau đó

JEP là một lộ trình thay đổi. Chốt kết luận theo release notes và hành vi **JDK đích**, không theo suy luận từ “in a future release”.

## 22. Checklist migration

### Agent inventory

- [ ] Đã liệt kê Java agents, JVMTI native agents và tất cả cách nạp.
- [ ] Đã phân biệt startup `premain` với dynamic `agentmain`.
- [ ] Đã xác định agent do application, test framework, APM hay operator cung cấp.
- [ ] Agent versions, artifact origin và owner được ghi nhận.
- [ ] Không còn agent tự attach không rõ chủ sở hữu.

### Phiên bản JDK và permissions

- [ ] Đã xác định đúng JDK/vendor/update level của JVM đích.
- [ ] Đã đọc release notes cho policy dynamic agent loading của JDK đích.
- [ ] Đã kiểm tra các flag `EnableDynamicAgentLoading` trên runtime áp dụng.
- [ ] Đã phân biệt `DisableAttachMechanism` với quyền nạp dynamic agent.
- [ ] Đã kiểm tra yêu cầu self-attach nếu sản phẩm sử dụng.
- [ ] OS/container/PID namespace/permissions được kiểm tra.
- [ ] Custom runtime image có các modules/công cụ cần thiết.

### Tương thích agent

- [ ] Java agent JAR có manifest `Premain-Class`/`Agent-Class` đúng chế độ.
- [ ] Agent support matrix bao gồm JDK và class-file versions mục tiêu.
- [ ] Thư viện bytecode và native companions được nâng tương ứng.
- [ ] JPMS access/opens được kiểm soát ở phạm vi phù hợp.
- [ ] Chức năng instrumentation thật đã được kiểm thử.
- [ ] Performance, memory và startup impact được theo dõi.

### Build, CI và deployment

- [ ] Test JVM và production JVM có agent configuration riêng.
- [ ] Có test khi dynamic loading bị từ chối nếu cần tương thích lâu dài.
- [ ] Có startup agent thay thế khi framework hỗ trợ.
- [ ] Không ghi đè các JVM args của JaCoCo/test runner không chủ đích.
- [ ] Có CI result trên runtime JDK đích.
- [ ] Agent artifacts và flags được pin trong deployment-as-code.
- [ ] Log và runbook có hướng xử lý warning, attach failures và agent errors.
- [ ] Có kế hoạch rollback và phương án chẩn đoán cho SRE.

## 23. Bài tập thực hành

### Bài tập 1: Cảnh báo từ thư viện kiểm thử

Một bộ test Mockito/Byte Buddy chạy ổn trên JDK 17 nhưng phát warning nạp agent động khi chuyển sang JDK 21.

Hãy xác định:

1. Thư viện nào nạp agent và bằng đường nào?
2. Vì sao warning xuất hiện dù test chưa thất bại?
3. Có cách cấp agent ngay khi test JVM startup được library hỗ trợ không?
4. Làm thế nào để thử nghiệm khi `EnableDynamicAgentLoading` bị tắt?
5. Cách nào tránh đưa test-only flags vào production?

### Bài tập 2: APM và production policy

Một service Java 21 có APM agent được nạp bằng `-javaagent`, trong khi đội SRE đôi lúc attach profiler lúc xảy ra sự cố.

Hãy thiết kế:

- Policy cho startup APM agent.
- Policy cho dynamic profiler agent.
- Danh sách quyền OS/JVM flags cần xét.
- Chức năng `jcmd`/JFR cần giữ.
- Audit trail và runbook xử lý warning.
- Fallback nếu JDK mục tiêu không cho dynamic attach theo mặc định.

### Bài tập 3: Phân loại lỗi attach

Trong staging có ba lỗi:

```text
Case A: AttachNotSupportedException
Case B: AgentLoadException after connecting
Case C: InaccessibleObjectException during instrumentation
```

Hãy chỉ ra mỗi lỗi nằm ở tầng nào, thông tin cần thu thập và vì sao không nên sửa cả ba bằng một `--add-opens`.

### Bài tập 4: Container có runtime tối giản

Một ứng dụng Java chạy trong custom `jlink` image. Nhóm vận hành muốn dùng Attach API từ một công cụ riêng.

Hãy kiểm tra:

- Runtime image của công cụ có `jdk.attach` không?
- JVM đích có cơ chế attach và policy dynamic loading phù hợp không?
- Process namespace/permissions có cho phép kết nối không?
- Có công cụ JFR/metrics thay thế không?
- Agent JAR/native library có đúng OS/arch/JDK không?

### Bài tập 5: Lập ma trận nâng cấp JDK

Tạo bảng cho JDK 17, JDK 21 và JDK target hiện tại của tổ chức, với các cột:

```text
JDK vendor/update
Startup agent support
Dynamic agent loading policy
Self-attach policy
Container/OS constraints
Instrumentation feature test
Release notes evidence
Owner/decision
```

Không tự điền trạng thái “supported” cho JDK mới khi chưa có bằng chứng chính thức và test trên runtime thực tế.

## Kết luận

Java agent là cơ chế quan trọng cho observability, profiling, testing và instrumentation, nhưng cách **nạp agent sau khi JVM đã chạy** đặt ra yêu cầu kiểm soát tính toàn vẹn của tiến trình. JEP 451 đưa cảnh báo về dynamic agent loading vào JDK 21 để chuẩn bị cho một chính sách chặt chẽ hơn trong tương lai. Cảnh báo không tự động khiến ứng dụng thất bại, không đồng nghĩa mọi Java agent bị cấm và không thay thế việc xác minh tình trạng thực tế trên từng JDK/vendor.

Để migration bền vững, hãy xác định ai và khi nào nạp agent, phân biệt `-javaagent`/`premain` với Attach API/`agentmain`, kiểm soát `EnableDynamicAgentLoading` theo JVM đích, tránh nhầm self-attach và module-access errors, nâng agent cùng các thư viện bytecode/native, và thử trên artifact/runtime thực tế. Khi agent cần thiết lâu dài, ưu tiên cơ chế startup được công bố và kiểm soát rõ; khi dynamic attach là yêu cầu vận hành, duy trì quyền có chủ đích, audit, giới hạn phù hợp và phương án chẩn đoán thay thế.

