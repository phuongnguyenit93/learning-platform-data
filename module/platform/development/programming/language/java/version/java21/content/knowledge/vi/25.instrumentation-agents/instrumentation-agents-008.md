# Quản lý quyền nạp agent và cấu hình tường minh theo môi trường

Java agent có thể quan sát hoặc thay đổi bytecode trong một JVM. Vì vậy, cho phép một thành phần nạp agent vào process đang chạy là một quyết định về tính toàn vẹn và quyền kiểm soát process, không chỉ là cách bật profiler. Trong Java 21, HotSpot phát cảnh báo khi Java agent hoặc JVM TI agent được nạp động. Quản trị viên có thể chủ động cho phép bằng `-XX:+EnableDynamicAgentLoading`, hoặc chặn bằng `-XX:-EnableDynamicAgentLoading`.

Với agent cần thiết trong mọi lần chạy, nên nạp từ đầu bằng `-javaagent`, `-agentlib` hoặc `-agentpath`. Với môi trường không cần dynamic attach, hãy đặt chính sách chặn rõ ràng. Chỉ bật dynamic loading ở môi trường chẩn đoán hoặc kiểm thử có kiểm soát, và chỉ cho phép người vận hành cùng agent JAR đáng tin cậy.

## 1. Quyền nạp agent là một quyết định ở cấp JVM

Agent chạy bên trong process JVM và có thể dùng Instrumentation API hoặc JVM Tool Interface (JVMTI) để instrument class, thay đổi hành vi method hoặc hỗ trợ công cụ chẩn đoán. Một agent không đáng tin cậy có thể tác động sâu đến dữ liệu và hành vi của ứng dụng.

Trong Java 21 cần phân biệt hai đường nạp:

| Cơ chế | Ví dụ | Thời điểm | Điều khiển bởi `EnableDynamicAgentLoading`? |
|---|---|---|---|
| Nạp khi khởi động | `-javaagent:agent.jar`, `-agentlib:agent`, `-agentpath:/path/agent` | Khi JVM khởi chạy | Không; đây là startup loading |
| Nạp động | Attach API, `jcmd` hoặc công cụ tương thích yêu cầu nạp agent vào JVM đang chạy | Sau khi JVM đã khởi chạy | Có, trên HotSpot |

`-XX:-EnableDynamicAgentLoading` chỉ chặn việc nạp agent động. Nó không chặn agent đã được khai báo ngay từ đầu bằng `-javaagent`, `-agentlib` hoặc `-agentpath`.

Đây không phải một lời nhắc xác nhận của Java Security Manager hay một hộp thoại hỏi người dùng. Đây là chính sách được đặt khi khởi chạy JVM. Quyền hệ điều hành đối với process đích và tính đáng tin cậy của agent JAR vẫn phải được kiểm soát riêng.

## 2. JEP 451 và hành vi trong Java 21

JEP 451 được đưa vào JDK 21 để chuẩn bị cho việc tăng cường tính toàn vẹn của JVM. Khi agent được nạp động vào một JVM đang chạy, HotSpot in cảnh báo ra standard error. Startup agent không tạo cảnh báo này.

Các điểm cần hiểu chính xác:

- Trong JDK 21 HotSpot, dynamic agent loading vẫn được cho phép mặc định.
- `-XX:+EnableDynamicAgentLoading` thể hiện chủ đích cho phép nạp agent động và suppress cảnh báo tương ứng.
- `-XX:-EnableDynamicAgentLoading` chặn việc nạp agent động và có thể dùng để kiểm thử xem ứng dụng hoặc thư viện có phụ thuộc vào cơ chế đó hay không.
- Cảnh báo của JDK 21 không có nghĩa dynamic attach đã bị loại bỏ.
- JEP 451 mô tả hướng thay đổi mặc định trong một bản JDK tương lai; không được suy luận rằng thay đổi đó đã có hiệu lực chỉ từ nội dung cảnh báo.

Tài liệu Java Instrumentation của JDK 27 vẫn mô tả cảnh báo khi agent được nạp vào JVM đang chạy và ghi nhận tùy chọn HotSpot `-XX:+EnableDynamicAgentLoading`. Mã nguồn HotSpot hiện hành cũng vẫn khai báo giá trị mặc định của flag là `true`. Vì vậy, khi nâng JDK, hãy xác minh hành vi của đúng vendor và phiên bản triển khai thay vì coi kế hoạch tương lai trong JEP là hành vi đã được áp dụng.

## 3. Hai tùy chọn HotSpot cần phân biệt

### EnableDynamicAgentLoading

Đây là tùy chọn có phạm vi hẹp, điều khiển việc công cụ có được nạp agent vào JVM đang chạy hay không:

```bash
# Cho phép dynamic agent loading và biểu thị đây là cấu hình có chủ đích
java -XX:+EnableDynamicAgentLoading -jar app.jar

# Chặn dynamic agent loading
java -XX:-EnableDynamicAgentLoading -jar app.jar
```

Khi flag bị tắt, các công cụ vẫn có thể sử dụng những khả năng attach không yêu cầu nạp agent, nếu JVM và nền tảng cho phép. Tuy nhiên, thao tác nạp Java agent hoặc JVM TI agent động sẽ bị từ chối.

### DisableAttachMechanism

Đây là tùy chọn rộng hơn, tắt cơ chế attach cho phép công cụ kết nối vào JVM:

```bash
java -XX:+DisableAttachMechanism -jar app.jar
```

Khi bật, các công cụ dựa trên Attach Mechanism như `jcmd` không thể attach vào process đó. Điều này ảnh hưởng đến nhiều thao tác chẩn đoán và serviceability, không chỉ việc nạp agent.

| Tùy chọn | Mục đích | Ảnh hưởng đến `-javaagent` lúc khởi động |
|---|---|---|
| `-XX:-EnableDynamicAgentLoading` | Chặn nạp agent sau khi JVM chạy | Không ảnh hưởng |
| `-XX:+DisableAttachMechanism` | Tắt cơ chế attach của công cụ | Không ảnh hưởng |

Nếu chỉ muốn chặn dynamic agent nhưng vẫn cần dùng `jcmd` để xem flag, thread dump hoặc thông tin JVM, hãy bắt đầu bằng `-XX:-EnableDynamicAgentLoading`. Chỉ bật `DisableAttachMechanism` khi môi trường thực sự không cần công cụ attach và đã kiểm thử tác động vận hành.

## 4. Chính sách nên đặt theo từng môi trường

Không nên dùng cùng một chính sách dynamic agent cho tất cả môi trường. Hãy xác định agent nào cần chạy, ai có thể nạp agent và công cụ vận hành nào cần attach.

| Môi trường | Chính sách gợi ý | Ví dụ cấu hình |
|---|---|---|
| Production thông thường | Chặn dynamic loading; agent APM bắt buộc được khai báo lúc khởi động | `-XX:-EnableDynamicAgentLoading -javaagent:/opt/agents/apm.jar` |
| Production có quy trình chẩn đoán được phê duyệt | Chỉ bật trong instance hoặc cửa sổ chẩn đoán đã kiểm soát | `-XX:+EnableDynamicAgentLoading` |
| Staging/performance test | Bật nếu profiler hoặc công cụ kiểm thử thật sự cần attach; ghi nhận công cụ và thời gian sử dụng | `-XX:+EnableDynamicAgentLoading` |
| Development | Ưu tiên startup agent; bật dynamic loading khi IDE/profiler/test tool cần và developer hiểu tác động | Cấu hình theo run configuration của IDE |
| Unit/integration test | Ưu tiên khai báo agent trong JVM test; chỉ bật dynamic loading nếu thư viện test chưa hỗ trợ startup loading | `-javaagent:...` hoặc flag opt-in cho test JVM riêng |
| Runtime image tối giản, không có nhu cầu chẩn đoán attach | Có thể tắt Attach Mechanism sau khi xác nhận không cần `jcmd`/profiler | `-XX:+DisableAttachMechanism` |

Ví dụ production cần APM từ request đầu tiên nhưng không cho phép thư viện tự attach:

```bash
java \
  -XX:-EnableDynamicAgentLoading \
  -javaagent:/opt/agents/apm-agent.jar \
  -jar application.jar
```

Ví dụ một instance staging được cấp quyền cho profiler attach trong thời gian kiểm thử:

```bash
java \
  -XX:+EnableDynamicAgentLoading \
  -jar application.jar
```

Flag `+` không tự nạp agent và cũng không xác thực agent JAR. Nó chỉ cho phép đường nạp động trên HotSpot và suppress cảnh báo tương ứng.

## 5. Cấu hình riêng cho test JVM và công cụ phát triển

Một số thư viện kiểm thử hoặc công cụ bytecode có thể tự attach agent vào JVM test. Vì vậy, việc ứng dụng production không dùng dynamic attach không có nghĩa test suite sẽ không phát sinh cảnh báo.

Thứ tự xử lý nên là:

1. Xác định thư viện hoặc plugin nào yêu cầu agent.
2. Kiểm tra công cụ có hỗ trợ nạp agent khi khởi động bằng `-javaagent` hay không.
3. Nếu có, cấu hình agent trong đúng forked test JVM hoặc run configuration.
4. Nếu chưa thể chuyển sang startup loading, chỉ bật `-XX:+EnableDynamicAgentLoading` cho test JVM cần thiết.
5. Không thêm flag cho toàn bộ máy developer hoặc production chỉ để làm mất một cảnh báo của test.

Ví dụ khởi chạy một JVM kiểm thử với agent ngay từ đầu:

```bash
java \
  -javaagent:/opt/test-tools/instrumentation-agent.jar \
  -jar test-runner.jar
```

Nếu build tool tạo forked JVM, JVM argument phải được đặt ở cấu hình fork/test tương ứng. Đặt flag cho JVM chạy Maven hoặc Gradle daemon không đảm bảo nó được truyền sang JVM fork dùng để thực thi test.

## 6. Quản lý cấu hình theo deployment

Đặt JVM option tại nơi chịu trách nhiệm khởi chạy process để có thể review và audit cùng cấu hình triển khai. Có thể dùng command line, service definition hoặc biến môi trường tùy nền tảng.

Ví dụ dùng `JAVA_TOOL_OPTIONS` trong một môi trường kiểm thử riêng:

```bash
export JAVA_TOOL_OPTIONS="-XX:+EnableDynamicAgentLoading"
java -jar test-runner.jar
```

PowerShell:

```powershell
$env:JAVA_TOOL_OPTIONS = "-XX:+EnableDynamicAgentLoading"
java -jar test-runner.jar
```

`JAVA_TOOL_OPTIONS` được JVM đọc khi khởi tạo, vì vậy nó có thể ảnh hưởng đến nhiều JVM được khởi chạy từ cùng môi trường. Chỉ đặt biến trong phạm vi job, container hoặc service cần thiết; không đặt ở cấp máy dùng chung nếu các ứng dụng có chính sách khác nhau.

Trong container hoặc Kubernetes, đặt option trong command/args của container hoặc biến môi trường của đúng workload. Tránh đưa một flag opt-in dynamic agent vào base image dùng chung cho mọi ứng dụng nếu không phải tất cả ứng dụng đều cần quyền này.

Ví dụ cấu hình cần thể hiện rõ mục tiêu:

```text
production:
  JAVA_TOOL_OPTIONS=-XX:-EnableDynamicAgentLoading

staging-profiler:
  JAVA_TOOL_OPTIONS=-XX:+EnableDynamicAgentLoading

test-job:
  JAVA_TOOL_OPTIONS=-javaagent:/opt/test-tools/agent.jar
```

Đây là sơ đồ cấu hình minh họa; cú pháp khai báo biến trong Helm, Kubernetes manifest, Docker Compose hoặc service manager phụ thuộc nền tảng triển khai.

## 7. Phát hiện thư viện đang dùng dynamic attach

Không phải mọi dynamic agent đều do người vận hành gọi `jcmd` trực tiếp. Một thư viện trong ứng dụng hoặc test framework có thể tự attach để nạp instrumentation agent.

JDK 21 cung cấp system property `jdk.instrument.traceUsage` để truy vết việc sử dụng `java.lang.instrument` API:

```bash
java \
  -Djdk.instrument.traceUsage=true \
  -jar application.jar
```

Property này có thể in thông báo và stack trace tại nơi API instrumentation được sử dụng. Bật tạm thời trong development/staging để xác định thư viện hoặc code path liên quan; output có thể nhiều nên không nên bật vô thời hạn trong production nếu chưa đánh giá chi phí log.

Sau khi xác định thành phần tự attach:

- Kiểm tra tài liệu và phiên bản thư viện.
- Ưu tiên chế độ startup agent nếu thư viện hỗ trợ.
- Tắt tính năng instrumentation động nếu ứng dụng không cần nó.
- Nếu vẫn cần, ghi nhận lý do và bật quyền chỉ cho JVM tương ứng.

Không dùng `-XX:+IgnoreUnrecognizedVMOptions` để che lỗi chính sách hoặc flag không hợp lệ. Một cấu hình bị JVM bỏ qua có thể khiến ứng dụng chạy với quyền khác điều mà đội vận hành dự định.

## 8. Xác minh cấu hình đang có hiệu lực

### Kiểm tra trước khi khởi chạy

`PrintFlagsFinal` giúp xem giá trị flag của JVM đang được gọi:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep EnableDynamicAgentLoading
```

PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String EnableDynamicAgentLoading
```

Kiểm tra bằng đúng executable và đúng JDK vendor dùng trong deployment. Giá trị có thể bị ghi đè bởi command line hoặc biến môi trường.

### Kiểm tra process đang chạy

Nếu Attach Mechanism vẫn được bật, có thể xem command line và VM flags của process:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

`VM.command_line` giúp kiểm tra các đối số khởi chạy; `VM.flags` giúp xem giá trị flag hiện hành. Nếu đã dùng `-XX:+DisableAttachMechanism`, không thể dựa vào `jcmd` để attach vào process đó. Khi cần audit trong trường hợp này, lưu cấu hình khởi chạy ở deployment system hoặc ghi nhận `RuntimeMXBean.getInputArguments()` từ ứng dụng.

### Kiểm thử chính sách chặn

Trên một JVM kiểm thử riêng, chạy với:

```bash
java -XX:-EnableDynamicAgentLoading -jar application.jar
```

Sau đó chạy các test hoặc công cụ có khả năng dynamic attach. Những thành phần thực sự phụ thuộc dynamic loading phải thất bại ở bước nạp agent; điều này giúp tìm dependency ẩn trước khi áp dụng chính sách cho production. Không chạy phép thử này trên process production đang phục vụ traffic.

## 9. Bảo vệ agent JAR và quyền attach ở cấp hệ điều hành

JVM flag không thay thế kiểm soát truy cập hệ điều hành. Người có khả năng attach vào process có thể yêu cầu JVM nạp code chạy trong process đó. Vì vậy:

1. Chạy service bằng user riêng, không dùng chung tài khoản đặc quyền với người dùng hoặc workload không tin cậy.
2. Giới hạn quyền đọc/ghi thư mục agent; chỉ pipeline phát hành được phép thay thế agent JAR.
3. Kiểm tra nguồn phát hành, checksum và chữ ký artifact trong quy trình triển khai.
4. Không lấy đường dẫn agent hoặc tên file agent trực tiếp từ request bên ngoài.
5. Giới hạn quyền truy cập PID/process namespace và container host.
6. Ghi audit agent nào được triển khai, phiên bản nào, ở process nào và ai phê duyệt.
7. Chỉ mở dynamic loading cho instance có nhu cầu và tắt lại khi kết thúc cửa sổ chẩn đoán nếu quy trình vận hành cho phép.

Không giả định một JAR được ký thì JVM tự động xác minh chữ ký trước khi nạp. Việc xác minh nguồn gốc và tính toàn vẹn của agent phải nằm trong quy trình phát hành và vận hành của tổ chức.

## 10. Phân biệt quyền nạp động với quyền dùng công cụ chẩn đoán

`-XX:-EnableDynamicAgentLoading` và `-XX:+DisableAttachMechanism` có tác động khác nhau. Chọn sai flag có thể làm mất khả năng chẩn đoán khi sự cố xảy ra.

| Tình huống | `-XX:-EnableDynamicAgentLoading` | `-XX:+DisableAttachMechanism` |
|---|---|---|
| Nạp `-javaagent` lúc startup | Vẫn được phép | Vẫn được phép |
| Nạp agent qua Attach API | Bị chặn | Không thể attach |
| Dùng `jcmd` attach để xem VM flags | Attach mechanism vẫn có thể hoạt động | Bị chặn |
| Dùng profiler cần dynamic agent | Không hoạt động nếu cần nạp agent động | Không thể attach |
| Môi trường cần chẩn đoán trực tiếp | Có thể giữ lại nhiều khả năng chẩn đoán không cần agent | Có thể làm giảm đáng kể khả năng chẩn đoán |

Nếu chính sách yêu cầu không có công cụ nào được attach, `DisableAttachMechanism` có thể phù hợp. Nếu chỉ muốn ngăn code agent được nạp động nhưng vẫn cần `jcmd`, thường nên dùng `-XX:-EnableDynamicAgentLoading`.

## 11. Checklist trước khi triển khai

1. Liệt kê agent startup và dynamic agent mà ứng dụng, framework, profiler và test tool đang sử dụng.
2. Chuyển agent luôn cần sang startup loading nếu công cụ hỗ trợ.
3. Chọn chính sách theo môi trường: chặn dynamic loading ở production thông thường; chỉ opt-in ở môi trường được phê duyệt.
4. Xác nhận vendor/JDK version và hỗ trợ của `EnableDynamicAgentLoading` trên runtime thực tế.
5. Kiểm tra mọi nguồn cấu hình: command line, `JAVA_TOOL_OPTIONS`, service definition, container args và test JVM.
6. Dùng `-Djdk.instrument.traceUsage=true` trong môi trường kiểm thử để tìm thư viện tự sử dụng Instrumentation API.
7. Chạy test với `-XX:-EnableDynamicAgentLoading` để phát hiện dependency vào dynamic attach.
8. Chỉ dùng `-XX:+DisableAttachMechanism` khi đã đánh giá ảnh hưởng đến `jcmd`, profiler và công cụ vận hành.
9. Xác minh agent JAR, quyền file, user chạy service và quyền truy cập process.
10. Ghi lại chính sách, người phê duyệt, thời hạn và cách thu hồi quyền dynamic loading.

## Tài liệu tham khảo chính thức

- [Oracle JDK 21 Release Notes — Warning Printed When an Agent Is Loaded into a Running VM](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
- [Java SE 21 API — Instrumentation package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 21 API — Attach API VirtualMachine](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Oracle Java SE 27 API — Instrumentation package](https://docs.oracle.com/en/java/javase/27/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [OpenJDK HotSpot — EnableDynamicAgentLoading flag](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/globals.hpp)
