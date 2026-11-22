# Kiểm thử ứng dụng khi không cho phép dynamic agent loading

Java agent và JVMTI agent có thể thay đổi bytecode hoặc quan sát hoạt động bên trong JVM. Agent có thể được nạp ngay khi JVM khởi động, hoặc được nạp vào một JVM đang chạy thông qua cơ chế attach. Cách thứ hai được gọi là *dynamic agent loading* và có thể làm thay đổi hành vi của ứng dụng sau khi tiến trình đã bắt đầu.

JEP 451 được đưa vào Java 21 để chuẩn bị cho việc hạn chế dynamic agent loading theo hướng integrity by default. Trên HotSpot JDK 21, dynamic loading vẫn được cho phép mặc định nhưng JVM phát cảnh báo khi agent được nạp động. Có thể chạy ứng dụng với `-XX:-EnableDynamicAgentLoading` để kiểm thử trường hợp không cho phép nạp agent sau startup. Đây là cách quan trọng để phát hiện test framework, mocking library hoặc công cụ quan sát đang âm thầm phụ thuộc vào self-attach.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt agent được nạp lúc JVM khởi động với agent được nạp động.
- Giải thích thay đổi của Java 21 theo JEP 451.
- Dùng `-XX:-EnableDynamicAgentLoading` để kiểm thử ứng dụng và test suite.
- Nhận diện thư viện hoặc công cụ đang dùng Attach API để nạp agent.
- Phân biệt cấm dynamic agent loading với việc tắt toàn bộ Attach Mechanism.
- Cấu hình test JVM để phát hiện phụ thuộc vào dynamic attach.
- Chuyển agent cần thiết sang startup loading bằng `-javaagent`, `-agentlib` hoặc `-agentpath` khi công cụ hỗ trợ.
- Xác minh ứng dụng vẫn hoạt động đúng khi dynamic agent loading bị từ chối.

## 1. Agent có thể được nạp theo hai thời điểm

Java instrumentation agent thường triển khai `premain` hoặc `agentmain` thông qua `java.lang.instrument`. Native JVMTI agent có các entry point tương ứng theo hợp đồng JVMTI.

### 1.1. Nạp agent khi JVM khởi động

Agent được chỉ định trên command line trước khi ứng dụng bắt đầu:

```bash
java -javaagent:observability-agent.jar -jar application.jar
```

JVM nạp agent trước khi gọi `main()` và gọi phương thức `premain` của Java agent. Native agent có thể được nạp lúc startup bằng `-agentlib` hoặc `-agentpath`.

Startup loading có ưu điểm là chủ sở hữu ứng dụng khai báo agent rõ ràng trong lệnh chạy hoặc cấu hình deployment. Agent đã được chọn trước khi ứng dụng bắt đầu xử lý công việc.

### 1.2. Nạp agent vào JVM đang chạy

Một tiến trình bên ngoài, hoặc chính ứng dụng trong trường hợp runtime cho phép self-attach, có thể dùng Attach API để kết nối tới JVM đang chạy và yêu cầu nạp agent:

```java
import com.sun.tools.attach.VirtualMachine;

static void loadAgent(String pid) throws Exception {
    VirtualMachine vm = VirtualMachine.attach(pid);
    try {
        vm.loadAgent("runtime-agent.jar");
    } finally {
        vm.detach();
    }
}
```

Với Java instrumentation agent, thao tác dynamic loading gọi `agentmain` thay vì `premain`. Attach API cũng có các phương thức nạp native agent library/path. Self-attach có thể chịu thêm giới hạn riêng của runtime và không nên được giả định luôn bật. Một số thư viện tự attach vào JVM hiện tại để cài agent phục vụ mocking, profiling hoặc instrumentation mà người chạy ứng dụng không nhận ra từ command line.

### 1.3. So sánh

| Đặc điểm | Startup loading | Dynamic loading |
|---|---|---|
| Thời điểm | Trước khi ứng dụng chạy | Sau khi JVM đã khởi động |
| Java agent entry point | `premain` | `agentmain` |
| Cách yêu cầu | `-javaagent` | Attach API, ví dụ `VirtualMachine.loadAgent()` |
| Native JVMTI agent | `-agentlib` hoặc `-agentpath` | Attach API nạp library/path |
| Bị chặn bởi `-XX:-EnableDynamicAgentLoading` | Không | Có |
| Mục đích thường gặp | Agent được deployment khai báo trước | Công cụ attach hoặc thư viện tự cài instrumentation khi runtime |

Tắt dynamic loading không đồng nghĩa với tắt toàn bộ instrumentation. Agent được nạp khi startup vẫn được phép theo cơ chế này.

## 2. Thay đổi của Java 21 theo JEP 451

JEP 451 có tên *Prepare to Disallow the Dynamic Loading of Agents*. Mục tiêu là giúp ứng dụng tiến dần tới trạng thái mặc định bảo vệ tính toàn vẹn: mã agent không thể tự ý được đưa vào một JVM đang chạy nếu chủ sở hữu ứng dụng không cho phép.

Trên HotSpot JDK 21:

- Dynamic agent loading vẫn được bật mặc định để duy trì tương thích.
- JVM phát cảnh báo khi Java agent hoặc JVMTI agent được nạp động.
- `-XX:+EnableDynamicAgentLoading` thể hiện chủ sở hữu ứng dụng chủ động cho phép dynamic loading và tắt cảnh báo tương ứng.
- `-XX:-EnableDynamicAgentLoading` từ chối nạp agent động và có thể dùng để kiểm thử hành vi của ứng dụng nếu dynamic loading không còn được cho phép.
- Startup agent qua `-javaagent`, `-agentlib` hoặc `-agentpath` không bị thay đổi bởi JEP 451.

Ví dụ cảnh báo thường có nội dung tương tự:

```text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default in a future release
```

Nội dung chính xác có thể khác theo vendor hoặc bản cập nhật JDK. Không nên xử lý cảnh báo bằng cách thêm `-XX:+EnableDynamicAgentLoading` một cách máy móc; trước hết cần xác định agent nào đang được nạp và vì sao.

### 2.1. Chạy JVM với dynamic agent loading bị tắt

Để kiểm thử ứng dụng:

```bash
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

Nếu một thành phần cố nạp agent sau startup, thao tác đó sẽ thất bại. Lỗi có thể xuất hiện dưới dạng exception từ Attach API hoặc thông báo lỗi do thư viện gọi attach phát sinh. Hãy kiểm tra nguyên nhân gốc thay vì chỉ tìm một chuỗi exception cố định.

Trên JDK 21, cờ này là cách chủ động mô phỏng chính sách chặt hơn được JEP 451 hướng tới. Khi chuyển sang JDK khác hoặc vendor khác, hãy kiểm tra release notes và tài liệu của runtime đích để xác nhận mặc định và cách cấu hình tương ứng.

## 3. Vì sao nên kiểm thử khi dynamic loading bị cấm?

Ứng dụng có thể chạy bình thường trong môi trường phát triển nhưng phụ thuộc dynamic agent loading thông qua một dependency gián tiếp. Khi runtime từ chối attach, lỗi có thể chỉ xuất hiện ở một số test hoặc chức năng ít được chạy.

Các nguồn phụ thuộc thường gặp:

- Mocking framework cần instrument class, method hoặc constructor trong runtime.
- Bytecode manipulation library tự cài agent khi khởi tạo.
- Profiler hoặc diagnostic tool attach vào tiến trình để nạp agent.
- APM hoặc tracing integration có chế độ attach sau startup.
- Framework persistence hoặc runtime enhancement cài agent để biến đổi class.
- Test plugin tự attach vào JVM fork để thu thập coverage hoặc instrumentation.

Không phải mọi công cụ trong các nhóm trên đều cần dynamic loading. Nhiều công cụ hỗ trợ startup agent hoặc không cần agent. Cần kiểm tra đúng phiên bản, cấu hình và chế độ chạy của dependency đang dùng.

Kiểm thử với cờ tắt dynamic loading giúp trả lời các câu hỏi:

1. Ứng dụng có khởi động và phục vụ chức năng chính khi không có agent attach động không?
2. Test suite có phụ thuộc vào self-attach của một thư viện không?
3. Agent nào thực sự cần thiết và có thể nạp từ startup không?
4. Có thể thay thế một chức năng instrumentation không bắt buộc bằng API hoặc cấu hình không cần agent không?
5. Công cụ vận hành có đang dùng dynamic agent loading như một phần bắt buộc của quy trình không?

## 4. Phân biệt các cờ JVM liên quan

Không nhầm lẫn giữa việc tắt dynamic agent loading và việc tắt Attach Mechanism:

| Cờ | Tác dụng | Ảnh hưởng chính |
|---|---|---|
| `-XX:-EnableDynamicAgentLoading` | Từ chối nạp agent vào JVM đang chạy | Ngăn dynamic Java/JVMTI agent loading |
| `-XX:+EnableDynamicAgentLoading` | Chủ động cho phép dynamic agent loading | Cho phép attach agent và tránh cảnh báo JEP 451 trên JDK 21 |
| `-XX:+DisableAttachMechanism` | Tắt Attach Mechanism của HotSpot | Có thể làm các công cụ cần attach, bao gồm một số lệnh chẩn đoán, không kết nối được |
| `-Djdk.instrument.traceUsage` | In trace khi các API `java.lang.instrument` được sử dụng | Hỗ trợ tìm thành phần đang dùng instrumentation API |

`-XX:-EnableDynamicAgentLoading` không có nghĩa là vô hiệu hóa mọi khả năng chẩn đoán JVM. Attach Mechanism và dynamic agent loading là hai lớp khác nhau. Nếu mục tiêu chỉ là kiểm tra ứng dụng không nạp agent động, hãy dùng cờ `EnableDynamicAgentLoading` thay vì tắt toàn bộ attach.

`-Djdk.instrument.traceUsage` là công cụ chẩn đoán, không phải cờ chặn agent. Nó giúp truy vết nơi sử dụng instrumentation API; không thay thế việc chạy test với dynamic loading bị tắt.

## 5. Quy trình kiểm thử ứng dụng trên Java 21

Nên kiểm tra theo nhiều lớp để xác định rõ agent đến từ ứng dụng, test framework hay công cụ vận hành.

### 5.1. Kiểm thử startup và smoke test

Khởi chạy ứng dụng với dynamic agent loading bị từ chối:

```bash
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

Sau khi ứng dụng khởi động, chạy smoke test bao phủ các chức năng chính:

- Khởi động dependency và kết nối tới dịch vụ ngoài.
- Xử lý một request đại diện.
- Chạy một tác vụ nền.
- Ghi log, metric và trace theo cấu hình.
- Đóng ứng dụng theo quy trình shutdown bình thường.

Nếu ứng dụng lỗi ngay khi startup, kiểm tra stack trace để tìm dependency khởi tạo agent động. Nếu chỉ một chức năng lỗi, kiểm tra đường code được kích hoạt ở chức năng đó.

### 5.2. Kiểm thử toàn bộ test suite trong JVM fork

Cờ JVM phải được truyền khi process test được khởi chạy. Không thể thay đổi chính sách này bằng `System.setProperty()` sau khi JVM đã chạy.

Với Maven Surefire, thêm cờ vào JVM fork:

```xml
<plugin>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>-XX:-EnableDynamicAgentLoading</argLine>
    </configuration>
</plugin>
```

Nếu build đã dùng `argLine` cho JaCoCo hoặc startup agent khác, hãy hợp nhất các tham số thay vì ghi đè cấu hình hiện có. Ví dụ, giữ placeholder do build quản lý và thêm cờ kiểm thử:

```xml
<argLine>${argLine} -XX:-EnableDynamicAgentLoading</argLine>
```

Hãy xác nhận placeholder thực tế của build được khởi tạo đúng; cấu hình ví dụ cần điều chỉnh theo phiên bản plugin và cách JaCoCo được tích hợp.

Với Gradle Groovy DSL:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs("-XX:-EnableDynamicAgentLoading")
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("-XX:-EnableDynamicAgentLoading")
}
```

Chạy đúng task test của dự án và kiểm tra log để xác nhận test worker thực sự nhận cờ. Một số plugin chạy test trong process riêng hoặc tạo thêm JVM con; cần áp dụng cờ cho từng process liên quan.

### 5.3. Kiểm thử agent startup vẫn hoạt động

Nếu ứng dụng cần một agent đã được phê duyệt từ lúc khởi động, có thể kết hợp startup agent với việc cấm dynamic loading:

```bash
java \
  -XX:-EnableDynamicAgentLoading \
  -javaagent:approved-agent.jar \
  -jar application.jar
```

Startup agent vẫn được nạp trước `main()`. Bài test này xác nhận ứng dụng không cần dynamic attach ngoài danh sách agent được khai báo trước.

Nếu mục tiêu là kiểm tra ứng dụng không cần bất kỳ Java agent nào, hãy chạy thêm một lượt không có `-javaagent`, `-agentlib` hoặc `-agentpath`. Hai mục tiêu kiểm thử này khác nhau.

## 6. Tìm thành phần đang dynamic attach

### 6.1. Đọc cảnh báo JEP 451

Trên Java 21, chạy ứng dụng trong cấu hình mặc định và thu thập standard error. Cảnh báo dynamic loading thường nêu tên hoặc vị trí agent JAR được nạp. Đây là manh mối đầu tiên để xác định dependency.

Không bỏ qua cảnh báo chỉ vì ứng dụng vẫn chạy. Ghi lại:

- Tên agent hoặc đường dẫn JAR/library.
- Thời điểm cảnh báo xuất hiện.
- Test hoặc chức năng đang chạy.
- Dependency trực tiếp/gián tiếp liên quan.
- Agent được nạp bởi ứng dụng, test framework hay công cụ bên ngoài.

### 6.2. Dùng `-Djdk.instrument.traceUsage`

Để truy vết nơi sử dụng API instrumentation, chạy JVM với:

```bash
java -Djdk.instrument.traceUsage -jar application.jar
```

Hoặc bật property này trong test JVM:

```text
-Djdk.instrument.traceUsage=true
```

JVM in thông tin trace/stack khi các API của `java.lang.instrument.Instrumentation` được sử dụng. Dùng stack trace để lần ngược về thư viện gọi API và xác định mục đích của nó.

Property này là công cụ điều tra. Nó không đảm bảo phát hiện mọi hoạt động attach ở mọi tầng, đặc biệt khi thành phần gọi Attach API nhưng không đi qua đường sử dụng instrumentation mà trace đang theo dõi. Hãy kết hợp với cảnh báo, dependency tree và cấu hình công cụ.

### 6.3. Kiểm tra dependency tree

Khi stack trace chỉ ra thư viện trung gian, xem dependency tree của cấu hình chạy hoặc test để xác định phiên bản được nạp:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration testRuntimeClasspath
```

Tìm các dependency liên quan đến bytecode instrumentation, attach API, agent loader hoặc mocking. Xác minh phiên bản và chế độ hoạt động trong tài liệu chính thức của thư viện.

Không loại bỏ dependency chỉ dựa vào tên artifact. Một thư viện có thể cung cấp nhiều chức năng và chỉ một chế độ cụ thể mới yêu cầu dynamic loading.

## 7. Xử lý dependency cần instrumentation

Khi xác định được thành phần cần agent, có một số hướng xử lý.

### 7.1. Chuyển sang startup agent

Nếu công cụ hỗ trợ startup loading, cấu hình agent rõ ràng trong JVM test hoặc application process:

```bash
java \
  -javaagent:approved-agent.jar \
  -XX:-EnableDynamicAgentLoading \
  -jar application.jar
```

Agent được nạp qua `premain` và không cần Attach API sau startup. Cách này phù hợp với công cụ profiling, coverage, APM hoặc bytecode instrumentation có hỗ trợ startup agent.

Với test framework cần một agent phụ trợ, cấu hình nó trong test JVM thay vì để thư viện tự attach. Hãy dùng đúng phiên bản agent mà framework yêu cầu và kiểm tra thứ tự/cấu hình agent theo tài liệu của nhà cung cấp.

### 7.2. Dùng chức năng không cần agent nếu có

Một số thư viện có nhiều chế độ: chế độ instrument runtime, chế độ proxy/interface, chế độ code generation hoặc chế độ không cần biến đổi class. Nếu yêu cầu nghiệp vụ không cần khả năng đặc biệt của agent, chọn chế độ ít quyền hơn.

Ví dụ, khi test có thể mock qua interface hoặc dependency injection, không nhất thiết phải bật chế độ cần instrument static/final/constructor nếu dự án không cần các khả năng đó. Quyết định phải dựa trên API và giới hạn của framework cụ thể.

### 7.3. Nâng cấp hoặc cấu hình lại thư viện

Kiểm tra release notes để tìm phiên bản có hỗ trợ startup agent hoặc không còn yêu cầu self-attach trong môi trường tương ứng. Không giả định mọi bản nâng cấp đều bỏ dynamic loading; xác minh bằng cách chạy test với cờ từ chối.

Nếu thư viện không có chế độ được hỗ trợ khi dynamic loading bị cấm, cần đánh giá lại lựa chọn công cụ hoặc chấp nhận một chính sách cho phép agent động trong môi trường có kiểm soát. Không che giấu vấn đề bằng cách bỏ cờ khỏi CI mà không ghi nhận lý do.

## 8. Những công cụ thường cần kiểm tra

Các nhóm công cụ dưới đây có thể liên quan tới agent; chế độ cụ thể phụ thuộc phiên bản và cấu hình:

| Nhóm | Câu hỏi cần xác minh |
|---|---|
| Mocking/bytecode library | Có self-attach để instrument class không? Có hỗ trợ startup `-javaagent` không? |
| Coverage tool | Agent có được nạp từ JVM startup hay plugin cố attach sau khi test bắt đầu? |
| APM/tracing agent | Agent được khai báo trong startup command hay được cài bằng attach? |
| Profiler | Công cụ dùng JFR/JMX/diagnostic command hay phải nạp native/Java agent động? |
| Runtime enhancement | Class được enhance lúc build, lúc startup hay bằng agent động? |
| IDE/debugger | Chức năng nào cần agent và chức năng nào chỉ cần Attach API/diagnostic command? |

Không kết luận một công cụ chắc chắn tương thích hoặc không tương thích chỉ từ tên sản phẩm. Kiểm tra tài liệu phiên bản đang dùng và chạy thử trong JVM có cờ `-XX:-EnableDynamicAgentLoading`.

## 9. Dynamic agent loading và Attach Mechanism là hai chính sách khác nhau

Một JVM có thể cho phép các công cụ attach để truy vấn thông tin hoặc gửi diagnostic command, nhưng từ chối nạp agent động. Ngược lại, tắt toàn bộ Attach Mechanism có thể làm mất khả năng của các công cụ vận hành cần kết nối vào JVM.

Vì vậy:

- Dùng `-XX:-EnableDynamicAgentLoading` khi muốn kiểm thử ứng dụng không phụ thuộc dynamic Java/JVMTI agent.
- Chỉ cân nhắc `-XX:+DisableAttachMechanism` khi chính sách vận hành yêu cầu tắt Attach Mechanism hoàn toàn và đã đánh giá ảnh hưởng đến JFR, `jcmd`, debugger, profiler cùng các công cụ quản trị.
- Không thêm cả hai cờ chỉ để “tăng bảo mật” mà chưa xác định yêu cầu và ảnh hưởng thực tế.

`jcmd` có nhiều diagnostic command không phải là dynamic agent loading. Tuy nhiên, một số command hoặc công cụ riêng có thể yêu cầu nạp agent; hãy kiểm tra hành vi cụ thể thay vì suy luận từ việc chúng dùng attach.

## 10. Ma trận kiểm thử đề xuất

| Cấu hình JVM | Mục tiêu | Kết quả mong đợi |
|---|---|---|
| Mặc định Java 21 | Phát hiện cảnh báo dynamic loading | Nếu có agent động, JVM cảnh báo theo JEP 451 |
| `-Djdk.instrument.traceUsage` | Tìm nơi sử dụng instrumentation API | Có trace hỗ trợ xác định caller khi API được dùng |
| `-XX:-EnableDynamicAgentLoading` | Kiểm tra không phụ thuộc dynamic loading | Ứng dụng/test không cần dynamic agent vẫn chạy; nỗ lực nạp động bị từ chối |
| `-XX:-EnableDynamicAgentLoading -javaagent:approved.jar` | Kiểm tra startup agent được khai báo trước | `premain` vẫn chạy; dynamic loading vẫn bị từ chối |
| Không có startup agent và dynamic loading bị tắt | Kiểm tra chức năng không phụ thuộc agent | Chức năng chính vẫn hoạt động theo yêu cầu |

Chạy các cấu hình trong cùng môi trường và cùng test data để so sánh. Ghi lại test nào thất bại, stack trace, agent path và dependency version.

## 11. Checklist đưa kiểm thử vào CI

- Xác định JDK vendor và phiên bản JDK 21 được dùng trong CI.
- Thêm `-XX:-EnableDynamicAgentLoading` vào mọi test JVM fork cần kiểm tra.
- Xác nhận test plugin không tạo JVM con thiếu cờ.
- Chạy smoke test ứng dụng với dynamic loading bị tắt.
- Thu thập cảnh báo JEP 451 ở cấu hình mặc định để nhận diện agent đang được nạp động.
- Dùng `-Djdk.instrument.traceUsage` khi cần tìm caller của instrumentation API.
- Kiểm tra dependency tree của runtime và test classpath.
- Phân loại agent: startup agent được phê duyệt, dynamic agent cần thay đổi hoặc công cụ không còn cần thiết.
- Cấu hình startup agent rõ ràng nếu công cụ hỗ trợ.
- Giữ test riêng cho trường hợp không có agent nếu đó là yêu cầu sản phẩm.
- Kiểm tra kết quả trên JDK đích khi nâng cấp runtime; không giả định mặc định giữa các phiên bản giống nhau.
- Không che cảnh báo hoặc xóa cờ kiểm thử chỉ để làm pipeline xanh mà không xử lý nguyên nhân.

## 12. Nguyên tắc thiết kế

- Ưu tiên khai báo agent cần thiết ngay từ JVM startup.
- Dùng `-XX:-EnableDynamicAgentLoading` để kiểm thử ứng dụng và test suite không phụ thuộc agent attach động.
- Xem cảnh báo JEP 451 là tín hiệu cần điều tra, không chỉ là thông báo có thể bỏ qua.
- Dùng `-Djdk.instrument.traceUsage` để hỗ trợ tìm nơi sử dụng instrumentation API.
- Phân biệt `-XX:-EnableDynamicAgentLoading` với `-XX:+DisableAttachMechanism`; hai cờ có phạm vi tác động khác nhau.
- Kiểm tra từng phiên bản mocking, profiling, APM và enhancement tool thay vì suy luận từ tên thư viện.
- Giữ nguyên các startup agent đã được phê duyệt khi kiểm thử chính sách cấm dynamic loading.
- Chỉ cho phép dynamic loading trở lại khi có nhu cầu cụ thể, được chủ sở hữu ứng dụng chấp thuận và có cấu hình triển khai rõ ràng.
- Kiểm thử trên JDK/vendor thực tế và xem release notes khi chuyển phiên bản.

Kiểm thử với dynamic agent loading bị tắt giúp phát hiện các phụ thuộc instrumentation ẩn trước khi chúng trở thành lỗi vận hành hoặc vấn đề tương thích khi nâng JDK. Trên Java 21, `-XX:-EnableDynamicAgentLoading` cung cấp cách trực tiếp để kiểm tra chính sách này, trong khi startup agent vẫn có thể được khai báo minh bạch bằng command line.

## Tài liệu tham khảo

- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): mục tiêu, cảnh báo và chính sách dynamic agent loading.
- [Oracle — JDK 21 Release Notes, Prepare to Disallow the Dynamic Loading of Agents](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): mặc định của Java 21, `EnableDynamicAgentLoading` và `jdk.instrument.traceUsage`.
- [Java SE 21 API — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API instrumentation của Java agent.
- [Java SE 21 API — `VirtualMachine`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): Attach API và các thao tác nạp agent vào JVM đang chạy.
- [Java SE 21 API — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): hợp đồng startup và dynamic Java agent.
- [Java SE 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): các tùy chọn khởi chạy JVM, bao gồm startup agent và HotSpot options được hỗ trợ.
