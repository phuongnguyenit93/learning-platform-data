# Đánh giá thời gian khởi động, bộ nhớ và trải nghiệm gọi một lệnh

Một ứng dụng Spring Shell có thể được dùng như REPL chạy lâu dài hoặc như CLI thực thi một lệnh rồi kết thúc. Hai cách dùng này có đặc điểm hiệu năng khác nhau. Với REPL, chi phí khởi động được chia cho nhiều lệnh. Với CLI một lần gọi, người dùng phải chờ JVM, Spring ApplicationContext, command runner và nghiệp vụ hoàn tất trong mỗi tiến trình.

Khi đánh giá một bản phân phối, cần đo ba nhóm riêng biệt:

- **Thời gian:** từ lúc tiến trình được gọi đến lúc có kết quả và thoát; thời gian Spring sẵn sàng; độ trễ của command đầu tiên.
- **Bộ nhớ:** heap Java, bộ nhớ JVM ngoài heap và bộ nhớ tiến trình do hệ điều hành quan sát.
- **Trải nghiệm gọi lệnh:** cú pháp ngắn, output ổn định, mã thoát, hành vi khi chạy trong script và thời gian chờ mà người dùng thực sự cảm nhận.

Bài học dùng Spring Shell 3.1.6 và Spring Boot 3.1.x làm mốc API. Các ví dụ JVM và GraalVM Native Image cần được chạy trên cùng máy, cùng dữ liệu và cùng cấu hình nếu muốn so sánh có ý nghĩa.

## 1. Xác định kiểu sử dụng trước khi benchmark

Spring Shell hỗ trợ hai kiểu tương tác chính:

- **Interactive:** người dùng mở REPL, nhập nhiều command trong một tiến trình.
- **Non-interactive:** một command được truyền từ command line, chạy xong rồi tiến trình kết thúc.

Spring Shell còn có ScriptShellRunner để chạy nội dung script. Các runner này được điều khiển bởi ShellApplicationRunner, dựa trên application arguments. Có thể bật hoặc tắt runner qua các thuộc tính spring.shell.interactive.enabled, spring.shell.noninteractive.enabled và spring.shell.script.enabled.

Với REPL, người dùng trả chi phí khởi động một lần rồi chạy nhiều command:

~~~text
$ project-cli
shell:> project list
shell:> project show --id 101
shell:> project close --id 101
shell:> exit
~~~

Với CLI một lệnh, mỗi lần gọi có thể tạo một JVM và Spring context mới:

~~~text
$ java -jar project-cli.jar project list
$ java -jar project-cli.jar project show --id 101
~~~

Vì vậy, benchmark project list trong một JVM đang chạy không trả lời câu hỏi giống với benchmark java -jar ... project list. Cần ghi rõ đang đo startup của tiến trình mới hay độ trễ command bên trong một REPL đã khởi động.

## 2. Xác định các mốc thời gian cần đo

Không nên gom mọi thời gian thành một con số “startup”. Một lần gọi CLI có thể được chia thành các mốc:

~~~mermaid
flowchart LR
    A["OS tạo tiến trình"] --> B["JVM khởi tạo"]
    B --> C["Spring ApplicationContext"]
    C --> D["ShellApplicationRunner"]
    D --> E["Parse và gọi command"]
    E --> F["Ghi output"]
    F --> G["Đóng context"]
    G --> H["Tiến trình thoát"]
~~~

| Mốc | Ý nghĩa | Cách đo phù hợp |
|---|---|---|
| Process launch | Từ lúc OS bắt đầu chạy executable | Đồng hồ bên ngoài tiến trình |
| Spring started | Context đã refresh và phát ApplicationStartedEvent | Spring Boot startup metric |
| Spring ready | Application runners đã hoàn tất và app phát ApplicationReadyEvent | Spring Boot startup metric |
| First output | Người dùng nhìn thấy kết quả đầu tiên | Đo từ process ngoài hoặc ghi timestamp |
| Command complete | Nghiệp vụ và output command đã hoàn tất | Đo quanh command hoặc process |
| Process exit | Tiến trình kết thúc hoàn toàn | Đồng hồ bên ngoài tiến trình |

Với một lệnh chạy độc lập, thời gian quan trọng nhất với người dùng thường là **end-to-end**: từ lúc gọi command đến lúc tiến trình kết thúc. Con số này bao gồm khởi tạo JVM, Spring, xử lý command, ghi output và đóng tiến trình.

Với REPL, cần đo riêng thời gian mở shell và thời gian thực thi các command tiếp theo. Không cộng startup vào mọi command trong một phiên đã hoạt động.

## 3. Đo thời gian end-to-end bằng công cụ bên ngoài

Đồng hồ ngoài tiến trình đo đúng trải nghiệm mà script, CI hoặc người dùng nhận được. Có thể dùng Hyperfine để chạy một command nhiều lần, thống kê kết quả và so sánh nhiều executable.

Ví dụ so sánh executable JAR với native binary trên Linux:

~~~bash
hyperfine --warmup 3 --runs 30 --export-json benchmark.json \
  'java -jar build/libs/project-cli.jar project list' \
  './build/native/nativeCompile/project-cli project list'
~~~

Hyperfine chạy mỗi command trong một tiến trình riêng. Nó hỗ trợ warmup, nhiều lần chạy, phân tích thống kê, phát hiện outlier và xuất JSON/CSV/Markdown. Có thể dùng cùng công cụ trên Windows; thay đường dẫn native binary bằng file .exe được build cho Windows.

Một lệnh benchmark đơn giản cho riêng JAR:

~~~bash
hyperfine --warmup 3 --runs 30 \
  'java -jar build/libs/project-cli.jar project list'
~~~

### 3.1. Hiểu đúng warmup

--warmup 3 chạy command ba lần trước khi bắt đầu các lần đo chính. Điều này thường làm nóng cache của hệ điều hành, chẳng hạn cache file JAR và thư viện đã đọc từ đĩa.

Tuy nhiên, nếu mỗi lần benchmark khởi chạy một tiến trình mới, warmup **không giữ trạng thái JIT của tiến trình trước** cho lần đo kế tiếp. Mỗi JVM mới vẫn phải khởi tạo và thực hiện quá trình tối ưu hóa riêng.

Nên báo cáo ít nhất hai tình huống:

- **Lần chạy đầu / cold start:** lần gọi đầu sau khi build, khởi động máy hoặc trong môi trường cache lạnh được kiểm soát.
- **Warm file cache:** các lần gọi sau khi hệ điều hành đã đọc artifact và thư viện.

Không nên xóa cache toàn hệ thống trên máy dùng chung chỉ để tạo số cold start. Nếu cần cold-cache benchmark, dùng máy hoặc môi trường cô lập và ghi rõ thao tác chuẩn bị.

### 3.2. Lặp đủ số lần và đọc thống kê

Một lần chạy không đủ để kết luận. Thời gian có thể thay đổi do:

- CPU đang bận bởi tiến trình khác.
- Cache đĩa và antivirus.
- Garbage collection.
- JIT compilation.
- Kết nối database hoặc mạng.
- Tải dữ liệu và trạng thái cache ứng dụng.

Chạy nhiều lần, giữ lại dữ liệu thô và báo cáo median, độ phân tán, min/max; chỉ báo cáo p95 khi số mẫu đủ lớn để percentile có ý nghĩa. Nếu dùng Hyperfine, có thể lưu JSON để tính toán lại thay vì chỉ chép một dòng kết quả tóm tắt.

Không chạy song song nhiều benchmark trên cùng máy nếu mục tiêu là so sánh latency. CPU, disk và memory contention sẽ làm sai lệch kết quả.

## 4. Đo bằng đồng hồ của hệ điều hành

Có thể dùng công cụ sẵn có để kiểm tra nhanh mà không cài Hyperfine.

Trên Linux với GNU Time:

~~~bash
/usr/bin/time -v java -jar build/libs/project-cli.jar project list
~~~

Output của GNU Time có Elapsed (wall clock) time và Maximum resident set size. Giá trị RSS cực đại là bộ nhớ cư trú lớn nhất mà tiến trình chiếm trong RAM theo cách đo của hệ điều hành.

Trên macOS, time -l có thể hiển thị maximum resident set size; tên trường và đơn vị khác GNU Time.

Trên Windows PowerShell, đo wall-clock:

~~~powershell
Measure-Command {
    & java -jar .\build\libs\project-cli.jar project list | Out-Null
}
~~~

Để đo memory peak trên Windows, dùng Windows Performance Monitor, Windows Performance Recorder hoặc công cụ theo dõi tiến trình. Lấy một ảnh chụp Get-Process sau khi command đã kết thúc không phản ánh peak của tiến trình ngắn hạn. Nếu tự viết vòng lặp polling WorkingSet64, chu kỳ polling có thể bỏ lỡ spike ngắn; cần ghi rõ đây là peak được lấy mẫu.

## 5. Phân biệt startup của Spring với thời gian của toàn tiến trình

Spring Boot 3.1.x cung cấp các metric startup:

- application.started.time: thời gian từ khi ứng dụng bắt đầu đến ApplicationStartedEvent.
- application.ready.time: thời gian đến khi ứng dụng phát ApplicationReadyEvent, sau khi các application/command-line runner đã chạy xong.

Các metric này giúp xác định phần thời gian thuộc Spring lifecycle. Trong ứng dụng Spring Shell, command runner tham gia vào quá trình thực thi non-interactive. Tuy vậy, các metric nội bộ không thay thế phép đo process end-to-end: chúng không bao gồm mọi chi phí từ lúc OS tạo process đến khi OS thu hồi process.

Nếu command kết thúc nhanh và ApplicationContext đóng ngay sau runner, một metrics endpoint HTTP có thể không còn tồn tại để đọc sau khi command hoàn tất. Muốn thu thập metric trong trường hợp đó, cần xuất metric trước khi process kết thúc, dùng registry push hoặc ghi kết quả chẩn đoán ra file/log trong profile benchmark.

Spring Boot Actuator cũng cung cấp các metric JVM như jvm.memory.used, jvm.memory.committed, jvm.memory.max, buffer pool, GC và thread. Những metric này mô tả trạng thái JVM, không phải toàn bộ RSS của process.

## 6. Dùng ApplicationStartup để tìm bước khởi tạo chậm

Khi biết tổng thời gian startup nhưng chưa rõ Spring đang mất thời gian ở đâu, có thể bật BufferingApplicationStartup:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class ProjectCliApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProjectCliApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }
}
~~~

ApplicationStartup ghi lại các StartupStep trong quá trình Spring tạo context, đăng ký và khởi tạo bean. Với Actuator, có thể cấu hình startup endpoint để xem timeline dưới dạng JSON trong môi trường chẩn đoán.

Dùng dữ liệu này để tìm những bước như:

- Component scan và xử lý bean definition.
- Tạo bean và inject dependency.
- Auto-configuration.
- Khởi tạo repository hoặc client.
- Đọc cấu hình hoặc kết nối hệ thống ngoài.

Đây là công cụ phân tích Spring context. Nó không đo đầy đủ JVM bootstrap, chi phí nạp file JAR từ OS hay toàn bộ thời gian command chạy sau khi context đã sẵn sàng.

## 7. Dùng Java Flight Recorder để phân tích JVM

Java Flight Recorder (JFR) thu thập sự kiện JVM như allocation, garbage collection, class loading, thread và CPU. Có thể bật recording khi chạy JAR:

~~~bash
java \
  -XX:StartFlightRecording:filename=project-cli.jfr,dumponexit=true,settings=profile \
  -jar build/libs/project-cli.jar project list
~~~

Sau khi tiến trình kết thúc, xem tóm tắt recording:

~~~bash
jfr summary project-cli.jfr
~~~

Có thể dùng jfr print hoặc Java Mission Control để phân tích sự kiện chi tiết.

Spring Boot cũng có FlightRecorderApplicationStartup, tích hợp các startup step của Spring vào JFR. Cách này giúp đối chiếu thời điểm khởi tạo bean với allocation, GC và class loading của JVM.

JFR và startup tracing có thể thêm overhead. Dùng chúng để tìm nguyên nhân trong một lần chạy chẩn đoán riêng; sau đó tắt instrumentation khi lấy benchmark cuối cùng.

## 8. Hiểu đúng các loại bộ nhớ

Một JVM process dùng nhiều vùng bộ nhớ khác nhau:

| Loại bộ nhớ | Nội dung |
|---|---|
| Java heap | Object được quản lý bởi garbage collector |
| Metaspace | Metadata của class |
| Code cache | Mã máy do JIT biên dịch |
| Thread stack | Stack của từng thread |
| Direct buffer | Buffer ngoài heap |
| Native/runtime memory | Thư viện native, JVM runtime và vùng cấp phát ngoài heap |
| Memory-mapped files | Các vùng file được ánh xạ vào address space |

jvm.memory.used chỉ mô tả vùng memory do JVM quản lý theo meter tương ứng. Nó không bằng tổng memory của process.

RSS hoặc working set của process phản ánh các trang bộ nhớ đang cư trú trong RAM. Con số này bao gồm heap cùng nhiều vùng ngoài heap và thư viện được map. Vì vậy:

- Heap nhỏ không chứng minh process dùng ít RAM.
- Heap committed không đồng nghĩa toàn bộ vùng đó đang nằm trong RAM.
- RSS cao không nhất thiết có nghĩa Java object đang giữ nhiều dữ liệu.
- Native Image vẫn có heap được quản lý và có thể sử dụng native memory.

Khi so sánh hai bản phân phối, hãy ghi rõ đang báo cáo heap used, heap committed, maximum heap hay peak RSS. Không so một giá trị heap của JVM với RSS của native executable rồi kết luận một bên dùng ít bộ nhớ hơn.

## 9. Đo heap và memory metrics bằng Actuator

Khi ứng dụng có Spring Boot Actuator và Micrometer, các metric JVM được đăng ký tự động. Những tên thường dùng:

| Metric | Ý nghĩa |
|---|---|
| jvm.memory.used | Bộ nhớ đang được dùng trong vùng JVM |
| jvm.memory.committed | Bộ nhớ JVM đã cam kết với hệ điều hành |
| jvm.memory.max | Giới hạn tối đa của vùng memory tương ứng |
| jvm.gc.pause | Thời gian pause do garbage collection |
| jvm.threads.live | Số thread đang sống |

Có thể xem các metric qua Actuator metrics endpoint trong một process còn hoạt động, ví dụ:

~~~text
GET /actuator/metrics/jvm.memory.used
GET /actuator/metrics/jvm.memory.committed
~~~

Nếu muốn phân tích một vùng cụ thể, dùng tag area hoặc id mà meter cung cấp. Ví dụ heap và non-heap là các vùng khác nhau; đừng cộng hoặc so sánh khi chưa xác định tag.

Với CLI một lệnh, process có thể thoát trước khi có thể gọi endpoint. Trong trường hợp đó, dùng một trong các cách:

- Gửi metric đến registry bên ngoài trước khi context đóng.
- Ghi snapshot vào log/file trong profile benchmark.
- Chạy command trong một process giữ context để chẩn đoán nội bộ, nhưng không dùng số đo đó thay cho end-to-end one-shot.
- Dùng JFR và OS process monitor để quan sát memory peak.

Không bật Actuator hoặc thêm exporter vào artifact production chỉ để đo một lần nếu chúng làm thay đổi footprint mà người dùng cuối phải nhận.

## 10. Đo peak RSS của tiến trình

Đối với một CLI ngắn hạn, peak RSS từ công cụ hệ điều hành là chỉ số hữu ích để hiểu lượng RAM mà process thực sự chiếm.

Trên Linux:

~~~bash
/usr/bin/time -v java -jar build/libs/project-cli.jar project list
~~~

Tìm dòng Maximum resident set size (kbytes). Chạy cùng command và cùng dữ liệu cho mọi artifact.

Trên macOS:

~~~bash
/usr/bin/time -l java -jar build/libs/project-cli.jar project list
~~~

Trên Windows, dùng Performance Monitor hoặc Windows Performance Recorder để ghi working set và private bytes của process trong suốt lần chạy. Có thể quan sát bằng Process Explorer khi chạy thủ công, nhưng với command quá ngắn, cần công cụ ghi theo thời gian để không bỏ lỡ peak.

Nên đo nhiều lần và ghi median/peak quan sát được. Nếu benchmark tool chỉ cung cấp wall-clock, không suy ra memory từ thời gian chạy. Hai chỉ số cần được thu thập riêng.

## 11. So sánh JVM và GraalVM Native Image

Spring Shell 3.1.6 hỗ trợ native compilation dựa trên AOT của Spring Framework và Spring Boot. Khi build native, application context được chuẩn bị ở build time và GraalVM phân tích reachability để tạo executable.

Với Gradle, tài liệu Spring Shell 3.1.6 hướng dẫn dùng plugin GraalVM Native Build Tools và chạy:

~~~bash
./gradlew nativeCompile
~~~

Native executable được tạo trong thư mục build/native/nativeCompile. Với Maven và Spring Boot parent, có thể dùng profile native theo cấu hình của dự án:

~~~bash
./mvnw package -Pnative
~~~

Native Image có thể giảm thời gian startup và footprint cho một số CLI, nhưng không đảm bảo kết quả tốt hơn với mọi workload. Cần cân nhắc:

- Thời gian và lượng RAM cần cho native build.
- Kích thước executable.
- Thư viện dùng reflection, dynamic proxy, JNI hoặc tài nguyên được nạp động.
- Reachability metadata cần thiết cho thư viện bên thứ ba.
- Khác biệt về throughput, GC và hành vi runtime.
- Chi phí bảo trì pipeline build theo từng OS/architecture.

GraalVM thực hiện phân tích tĩnh khi build. Các phần được truy cập động mà không thể suy ra ở build time có thể cần reachability metadata. Spring Shell có cung cấp một số hint, nhưng thư viện bên thứ ba vẫn có thể cần cấu hình bổ sung.

### 11.1. Theo dõi native memory của Native Image

Native Memory Tracking (NMT) của Native Image bị tắt mặc định và phải được bật khi build executable bằng tùy chọn `--enable-monitoring=nmt`. Khi executable đã được build có hỗ trợ NMT, có thể yêu cầu in báo cáo khi process kết thúc:

~~~bash
./project-cli -XX:+PrintNMTStatistics
~~~

NMT giúp quan sát một số vùng native/off-heap do runtime quản lý. Nó không thay thế peak RSS của hệ điều hành và không nhất thiết ghi nhận mọi vùng được thư viện cấp phát trực tiếp qua các cơ chế riêng.

Không gộp thời gian native compilation vào thời gian khởi động runtime. Hai số liệu này phục vụ hai quyết định khác nhau: chi phí phát hành artifact và trải nghiệm chạy artifact.

## 12. Benchmark JAR và native executable công bằng

Dùng cùng một command, cùng input, cùng cấu hình và cùng nguồn dữ liệu. Ví dụ:

~~~bash
hyperfine --warmup 3 --runs 30 \
  'java -jar build/libs/project-cli.jar project list' \
  './build/native/nativeCompile/project-cli project list'
~~~

Trước khi so sánh, kiểm tra:

1. Cả hai artifact chạy cùng version code và dữ liệu.
2. Cùng OS và CPU architecture.
3. JVM dùng đúng JDK version và JVM flags dự kiến phát hành.
4. Native executable được build bằng GraalVM version đã ghi lại.
5. Cùng biến môi trường, profile, cấu hình log và database.
6. Output có cùng nội dung và command thực hiện cùng nghiệp vụ.
7. Không có tiến trình benchmark khác gây contention.

Ghi riêng:

- Kích thước JAR và native executable.
- Thời gian build.
- Thời gian process end-to-end.
- Peak RSS.
- Heap metrics nếu có.
- Mã thoát và độ chính xác output.

Native executable gắn với OS và architecture mục tiêu. Không so binary Linux với JAR chạy trên Windows rồi quy toàn bộ chênh lệch cho JVM hay GraalVM.

## 13. Đo trải nghiệm của command đầu tiên trong REPL

Với REPL, đo hai phần:

- Thời gian từ khi chạy executable đến khi prompt đầu tiên sẵn sàng.
- Thời gian từ lúc nhấn Enter đến khi output của command đầu tiên xuất hiện.

Command đầu tiên có thể chịu chi phí lazy initialization, tải cấu hình, mở kết nối hoặc nạp cache. Các command sau có thể nhanh hơn vì những tài nguyên này đã sẵn sàng.

Một kịch bản benchmark REPL nên ghi timestamp ở ba điểm:

1. Khi shell hiển thị prompt đầu tiên.
2. Khi command được gửi.
3. Khi command hoàn tất và output đã được ghi.

Không dùng thời gian command thứ hai trong REPL để đại diện command đầu tiên. Cũng không dùng thời gian command trong REPL để thay cho one-shot process latency.

Nếu người dùng thường chỉ chạy một lệnh, tối ưu one-shot startup và output quan trọng hơn việc giảm vài mili giây ở command thứ năm của một phiên REPL dài.

## 14. Tối ưu trải nghiệm gọi một command

Spring Shell 3.1.6 có thuộc tính spring.shell.noninteractive.primary-command dành cho ứng dụng chỉ có một mục đích chính. Khi cấu hình, các runner khác bị tắt và NonInteractiveShellRunner dùng command đã chọn làm primary command.

Ví dụ:

~~~yaml
spring:
  shell:
    noninteractive:
      primary-command: project list
~~~

Nếu không cấu hình primary command, người dùng gọi:

~~~bash
java -jar project-cli.jar project list --format json
~~~

Khi đã cấu hình primary command, cú pháp có thể ngắn hơn:

~~~bash
java -jar project-cli.jar --format json
~~~

Điều này giúp ứng dụng đóng gói như một công cụ chuyên dụng. Cần kiểm tra lại help và option vì tên command không còn xuất hiện trong lệnh gọi.

Nếu ứng dụng cần REPL, không đặt primary command chỉ để rút ngắn cú pháp. Chọn runner theo mục đích sử dụng thực tế.

## 15. Đóng ApplicationContext sau lệnh

Spring Shell thực thi command thông qua Spring Boot application runner. Theo mặc định, ApplicationContext thường đóng sau khi các runner hoàn tất, trừ khi còn thành phần giữ process sống, ví dụ scheduler hoặc thread không kết thúc.

Có thể cấu hình:

~~~yaml
spring:
  shell:
    context:
      close: true
~~~

Thuộc tính này đăng ký xử lý để yêu cầu đóng context sau khi shell hoàn thành execution logic. Nó không được bật mặc định trong Spring Shell 3.1.6.

Nếu CLI một lệnh không thoát, kiểm tra:

- @EnableScheduling hoặc scheduler không cần thiết.
- Executor hoặc thread pool còn hoạt động.
- Connection pool hoặc client tạo thread nền.
- Hook hoặc listener giữ tài nguyên.
- Tài nguyên đã tạo nhưng chưa đóng.

Đừng thêm System.exit(0) để che một thread không được quản lý. Hãy đóng đúng tài nguyên và xác minh exit code của process.

## 16. Tối ưu JVM theo số đo

Nếu JAR vẫn là lựa chọn phù hợp, hãy đo trước khi thay đổi JVM flags. Những điểm có thể xem xét:

- Loại bỏ dependency và auto-configuration không cần thiết.
- Tránh tạo bean hoặc kết nối ngoài trước khi command cần đến.
- Giảm logging không cần thiết trong đường chạy one-shot.
- Dùng lazy initialization nếu chấp nhận chuyển một phần chi phí từ startup sang command đầu tiên.
- Điều chỉnh heap chỉ khi có số đo và giới hạn memory mục tiêu.
- Kiểm tra GC pause và allocation bằng JFR trước khi thay collector hoặc flags.

Lazy initialization có thể làm startup nhanh hơn nhưng khiến lần gọi bean đầu tiên chậm hơn. Với CLI một lệnh, nếu bean đó chắc chắn được dùng ngay, tổng thời gian end-to-end có thể không giảm. Hãy đo cả first-command latency.

Không giảm -Xmx chỉ vì muốn RSS thấp. Heap quá nhỏ có thể làm GC thường xuyên và tăng tổng thời gian. Không thêm nhiều JVM flags cùng lúc vì sẽ khó xác định thay đổi nào tạo ra kết quả.

## 17. Đánh giá output và mã thoát

Một command nhanh nhưng output khó dùng vẫn là trải nghiệm CLI kém. Với command được gọi từ script hoặc CI, cần đánh giá:

- Có thể gọi bằng một dòng lệnh dễ nhớ không?
- Có yêu cầu prompt hoặc stdin khi chạy non-interactive không?
- Output thành công có ổn định để script parse không?
- Diagnostic có làm nhiễu stdout không?
- Lỗi có trả mã thoát khác 0 không?
- Có timeout hoặc retry ngoài ý muốn không?
- Command có kết thúc process đúng lúc không?

Quy ước thường hữu ích:

- stdout: kết quả chính, có thể là text hoặc JSON.
- stderr: diagnostic, cảnh báo và thông báo lỗi.
- Exit code 0: command thành công.
- Exit code khác 0: command thất bại hoặc input không hợp lệ.

Ví dụ script:

~~~bash
project-cli --format json > result.json
status=$?

if [ "$status" -ne 0 ]; then
  echo "project-cli failed with code $status" >&2
  exit "$status"
fi
~~~

Nếu cần pipeline ổn định, không in banner hoặc log startup vào cùng stream với JSON. Có thể tắt banner bằng cấu hình Spring Boot:

~~~yaml
spring:
  main:
    banner-mode: "off"
~~~

Đo cả thời gian và kích thước output. Một lệnh tạo hàng nghìn dòng có thể tốn thời gian ghi terminal hoặc pipe nhiều hơn phần xử lý nghiệp vụ.

## 18. Thiết kế ma trận benchmark

Một benchmark có ích nên bao gồm các kịch bản phản ánh cách ứng dụng được dùng:

| Kịch bản | JVM JAR | Native Image | Mục tiêu |
|---|---|---|---|
| --help | Đo | Đo | Độ trễ khởi động tối thiểu |
| Command nhẹ, không truy cập mạng | Đo | Đo | Chi phí startup và parser |
| Command đọc dữ liệu nhỏ | Đo | Đo | Startup cộng nghiệp vụ |
| Command tạo dữ liệu | Đo | Đo | Tác động persistence |
| REPL prompt đầu tiên | Đo | Đo | Trải nghiệm mở shell |
| Command thứ hai trong REPL | Đo | Đo | Chi phí sau startup |

Không cần chạy mọi kịch bản nếu sản phẩm chỉ có một kiểu sử dụng. Chọn command đại diện cho công việc người dùng thường thực hiện.

## 19. Ghi lại kết quả có thể tái lập

Tạo bảng lưu kết quả cho mỗi lần phát hành:

| Trường | Giá trị cần ghi |
|---|---|
| Commit / version | Mã nguồn của artifact |
| Spring Shell / Spring Boot | Phiên bản dependency |
| JDK / GraalVM | Runtime và compiler |
| OS / architecture | Hệ điều hành, CPU architecture |
| Artifact | JAR hoặc native executable |
| Artifact size | Kích thước file |
| Command | Lệnh và option được benchmark |
| Cache condition | Cold hay warm |
| Runs | Số lần đo |
| Median / p95 | Thời gian process |
| Peak RSS | Bộ nhớ process cực đại |
| JVM heap | Used / committed / max nếu thu thập |
| Exit code | Kết quả thực thi |
| Output check | Output có đúng và ổn định không |

Không đưa số liệu benchmark từ một máy vào tài liệu như một cam kết chung. Dùng chúng làm baseline cho cùng môi trường build và chạy. Nếu đổi JDK, GraalVM, CPU, OS hoặc dependency, hãy tạo baseline mới.

## 20. Quy trình benchmark từ đầu đến cuối

Có thể dùng quy trình sau cho mỗi bản phát hành:

1. Build JAR release và native executable nếu dự án hỗ trợ.
2. Ghi lại commit, dependency versions, OS, CPU và RAM.
3. Chọn một command đại diện, cùng input và dữ liệu cho mọi artifact.
4. Xác minh output và exit code trước khi đo hiệu năng.
5. Chạy một lần riêng để xác nhận môi trường và cache.
6. Đo cold-start và warm-file-cache theo hai nhóm riêng.
7. Dùng Hyperfine chạy lặp và xuất JSON.
8. Đo peak RSS bằng công cụ hệ điều hành.
9. Dùng Actuator, ApplicationStartup hoặc JFR trong lần chạy chẩn đoán riêng để tìm nút thắt.
10. Tắt instrumentation chẩn đoán và chạy lại benchmark cuối.
11. So sánh median, độ phân tán, peak RSS, artifact size và trải nghiệm gọi lệnh.
12. Lưu kết quả để so sánh với bản phát hành kế tiếp.

Khi số đo bất thường, không vội thay flags. Trước hết kiểm tra cache, background processes, dữ liệu, network, log và các dependency có được khởi tạo giống nhau không.

## 21. Những lỗi đánh giá thường gặp

| Cách đánh giá sai | Vì sao sai | Cách khắc phục |
|---|---|---|
| Chỉ đo dòng Started ... in ... | Không bao gồm đầy đủ chi phí OS process và thời gian thoát | Đo end-to-end bên ngoài |
| Dùng command thứ hai trong REPL để đại diện one-shot | Bỏ qua startup JVM và Spring | Đo tiến trình mới cho mỗi lần gọi |
| So heap của JAR với RSS native | Hai số đo khác phạm vi | So cùng loại metric |
| Chỉ chạy một lần | Bị ảnh hưởng bởi cache và tải máy | Lặp nhiều lần, báo cáo thống kê |
| Dùng warmup rồi gọi đó là cold start | Warmup làm nóng cache | Báo cáo cold và warm riêng |
| Dùng Thread.sleep để đo command | Thời gian chờ cố định không phản ánh hoàn tất | Ghi timestamp hoặc chờ điều kiện hoàn tất |
| Giảm -Xmx ngay để giảm RAM | Có thể làm GC tăng và command chậm | Xem heap, GC và RSS trước |
| So sánh native build time với JAR startup | Build time và runtime là hai giai đoạn khác nhau | Ghi riêng chi phí build và chạy |
| Bật JFR trong tất cả lần benchmark | Instrumentation có thể thêm overhead | Dùng JFR cho lần chẩn đoán riêng |
| Không kiểm tra exit code | Lệnh có thể in output nhưng vẫn thất bại | Kiểm tra output và exit status |
| Để log startup chen vào JSON | Script không parse được output | Tách stdout/stderr và tắt banner khi cần |
| Bỏ qua OS/architecture | Native binary phụ thuộc nền tảng | So trên cùng nền tảng |

## 22. Bài thực hành: benchmark một command của Project CLI

Giả sử ứng dụng có command project list, trả danh sách dự án và hỗ trợ JSON output.

Thực hiện:

1. Build executable JAR release.
2. Build native executable nếu môi trường có GraalVM.
3. Chạy cùng command với cùng dataset ở cả hai artifact.
4. Xác minh output JSON hợp lệ và exit code bằng 0.
5. Dùng Hyperfine với warmup và ít nhất 30 lần đo.
6. Xuất dữ liệu JSON để lưu lại kết quả.
7. Đo peak RSS riêng bằng công cụ hệ điều hành.
8. Bật BufferingApplicationStartup hoặc JFR để xem bước khởi tạo chậm.
9. Tắt instrumentation và đo lại.
10. Thử cấu hình spring.shell.noninteractive.primary-command nếu CLI chỉ phục vụ một command.
11. Kiểm tra stdout chỉ chứa JSON và diagnostic đi ra stderr.
12. So sánh thời gian, memory, artifact size và độ thuận tiện của cú pháp.

Kết quả cần ghi vào bảng:

| Chỉ số | JAR | Native | Ghi chú |
|---|---:|---:|---|
| Artifact size |  |  |  |
| Cold process time |  |  |  |
| Warm process time |  |  |  |
| Median |  |  |  |
| p95 (nếu đủ mẫu) |  |  |  |
| Peak RSS |  |  |  |
| Exit code |  |  |  |
| Output hợp lệ |  |  |  |

Không điền số liệu dự đoán. Chỉ ghi kết quả từ đúng môi trường đã benchmark.

## 23. Checklist trước khi phát hành

- [ ] Đã xác định người dùng chạy REPL, non-interactive hay script.
- [ ] Đã đo process end-to-end cho command một lần gọi.
- [ ] Đã đo startup và command đầu tiên riêng cho REPL.
- [ ] Đã phân biệt application.started.time và application.ready.time.
- [ ] Đã đo heap và peak RSS như hai loại metric riêng.
- [ ] Đã ghi lại JDK, GraalVM, OS và architecture.
- [ ] Đã benchmark với nhiều lần chạy và điều kiện cache rõ ràng.
- [ ] Đã kiểm tra output và exit code.
- [ ] Đã kiểm tra stdout/stderr cho script.
- [ ] Đã thử cú pháp primary command nếu sản phẩm chỉ có một command.
- [ ] Đã xác minh process thoát sau khi hoàn tất.
- [ ] Đã tắt instrumentation chẩn đoán trong lần benchmark cuối.
- [ ] Đã lưu kết quả để so sánh các bản phát hành sau.

## 24. Kết luận

Đánh giá một ứng dụng Spring Shell cần nhìn vào cách người dùng thực sự chạy nó. Với REPL, cần biết thời gian mở shell và độ trễ command đầu tiên. Với CLI một lệnh, cần đo toàn bộ vòng đời process từ lúc OS khởi chạy đến khi process thoát.

Dùng Hyperfine hoặc đồng hồ hệ điều hành để đo end-to-end; dùng application.started.time, application.ready.time, ApplicationStartup và JFR để tìm nguyên nhân bên trong Spring/JVM; dùng peak RSS để đánh giá bộ nhớ tiến trình và Actuator để xem heap metrics. Khi so sánh JAR với Native Image, giữ cùng command, dữ liệu, OS và cấu hình, đồng thời tách chi phí build khỏi runtime.

Một bản phân phối tốt cần khởi động phù hợp với workload, dùng bộ nhớ trong giới hạn, có cú pháp dễ gọi, output ổn định và mã thoát đáng tin cậy cho script. Chỉ kết luận sau khi đo lặp lại trên môi trường đại diện cho người dùng.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Building and Native Support](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Single Command and Context Close](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Boot 3.1 Reference: Application Startup Tracking](https://docs.spring.io/spring-boot/docs/3.1.x/reference/html/features.html)
- [Spring Boot 3.1 Reference: Actuator Metrics](https://docs.spring.io/spring-boot/docs/3.1.x/reference/html/actuator.html)
- [Spring Boot 3.1 Actuator API: Metrics and Startup](https://docs.spring.io/spring-boot/docs/3.1.x/actuator-api/htmlsingle/)
- [Oracle JDK 21: The java Command and Flight Recording Options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [GraalVM Native Image: Overview and Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/)
- [GraalVM Native Image: Memory Management](https://www.graalvm.org/reference-manual/native-image/MemoryManagement/)
- [GraalVM Native Image: Native Memory Tracking](https://www.graalvm.org/latest/reference-manual/native-image/debugging-and-diagnostics/NMT/)
- [Hyperfine: Command-line Benchmarking Tool](https://github.com/sharkdp/hyperfine)

