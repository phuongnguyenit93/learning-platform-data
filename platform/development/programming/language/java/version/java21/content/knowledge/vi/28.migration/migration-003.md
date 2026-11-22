# Nâng từ Java 17 lên Java 21 theo từng thay đổi có thể kiểm chứng

Nâng ứng dụng từ Java 17 lên Java 21 nên được thực hiện như một thay đổi runtime có kiểm soát: chạy ứng dụng hiện tại trên JDK 21 trước khi biên dịch lại, kiểm tra khác biệt về charset và thư viện, xử lý cảnh báo JVM, sau đó mới bật các API hoặc tính năng mới của Java 21. Phần lớn ứng dụng Java 17 có thể chạy trên Java 21 mà không cần viết lại, nhưng build tool, thư viện thao tác bytecode, agent, mã xử lý văn bản và một số đường chạy đồng thời cần được kiểm tra.

Bài này tập trung vào những thay đổi đã được chuẩn hóa hoặc thay đổi hành vi có thể quan sát trong quá trình nâng cấp. Các tính năng chỉ ở trạng thái preview/incubator trong Java 21 không được xem là nền tảng cho migration production.

## 1. Chốt phạm vi và lập baseline trên Java 17

Trước khi thay JDK, ghi lại trạng thái của ứng dụng đang chạy ổn định trên Java 17:

- Phiên bản JDK, hệ điều hành, kiến trúc CPU và giới hạn bộ nhớ/container.
- Lệnh khởi chạy, toàn bộ JVM flags, system properties và biến môi trường.
- Phiên bản Maven/Gradle, compiler plugin, test plugin, IDE và công cụ đóng gói.
- Các framework, thư viện, JDBC driver, HTTP client, thư viện xử lý bytecode và agent.
- Bộ test hiện tại, thời gian build, startup time, throughput, p95/p99 latency, CPU và heap.
- Các đầu vào/đầu ra nhạy cảm với encoding, locale, timezone, reflection, serialization và native code.

Lưu lại kết quả test và metric này để có mốc so sánh. Nếu không có baseline, rất khó phân biệt lỗi do thay JDK với thay đổi dependency, cấu hình hoặc dữ liệu test.

## 2. Chạy ứng dụng trên JDK 21 trước khi biên dịch lại

Oracle khuyến nghị thử chạy ứng dụng trên JDK đích trước, sau đó cập nhật thư viện, biên dịch và phân tích dependency theo từng vòng. Cách này giúp tách lỗi runtime khỏi lỗi source/compiler.

Kiểm tra JDK đang được dùng trong terminal và tiến trình:

~~~shell
java --version
javac --version
jcmd -l
~~~

Đặt JAVA_HOME trỏ tới JDK 21 trong môi trường thử nghiệm, cập nhật PATH, rồi chạy đúng artifact đã phát hành trên Java 17:

~~~shell
java -jar application.jar
~~~

Trong lần chạy này, ghi lại:

- JVM có khởi động được không; có cảnh báo option hoặc agent mới không.
- Test smoke và các luồng nghiệp vụ chính có cho cùng kết quả không.
- Log có lỗi liên quan class loading, reflection, provider mật mã hoặc native library không.
- Date, currency, văn bản, file và dữ liệu giao tiếp có thay đổi không.
- Startup time, memory, CPU, throughput và latency có khác baseline đáng kể không.

Nếu JVM không khởi động, kiểm tra các option trong lệnh chạy trước khi sửa code. Nếu ứng dụng khởi động nhưng test thất bại, khoanh vùng theo nhóm thay đổi ở các phần sau.

## 3. Kiểm tra thay đổi default charset từ JDK 18

Một khác biệt runtime quan trọng trên đường từ Java 17 tới Java 21 đến từ JEP 400: từ JDK 18, UTF-8 là default charset của Java SE trên mọi hệ điều hành. Trên JDK 17 và cũ hơn, default charset có thể phụ thuộc môi trường, ví dụ Windows có thể dùng một code page như windows-1252 hoặc windows-31j.

Điều này có thể làm thay đổi dữ liệu khi ứng dụng dùng API không chỉ định charset:

- FileReader và FileWriter.
- InputStreamReader và OutputStreamWriter khi không truyền charset.
- new String(byte[]) và String.getBytes() không truyền charset.
- Một số constructor của Scanner, Formatter và PrintStream.

Hãy tìm các vị trí chuyển đổi byte/string hoặc đọc/ghi file mà không chỉ rõ encoding. Với file và giao thức có quy định UTF-8, chỉ định charset ngay tại API:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data.txt");

String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);

byte[] payload = content.getBytes(StandardCharsets.UTF_8);
String decoded = new String(payload, StandardCharsets.UTF_8);
~~~

Không tự động chuyển mọi file sang UTF-8. Nếu một định dạng tích hợp yêu cầu encoding khác, hãy chỉ định đúng encoding của định dạng đó. Đặc biệt kiểm tra file CSV, dữ liệu nhập từ hệ thống cũ, tên file, nội dung email và giao thức giữa các dịch vụ.

Có thể ghi nhận charset mặc định thực tế trong cả hai môi trường:

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
~~~

Trên JDK 21, kết quả mặc định là UTF-8. file.encoding=COMPAT có thể dùng trong thử nghiệm trên JDK 18+ để mô phỏng hành vi phụ thuộc môi trường của JDK 17; đây chỉ là công cụ so sánh, không nên trở thành cách né kiểm tra encoding trong cấu hình dài hạn. Tài liệu Oracle mô tả các giá trị UTF-8 và COMPAT cùng cách kiểm tra tại [Default Charset](https://docs.oracle.com/en/java/javase/21/intl/supported-encodings.html).

## 4. Biên dịch bằng toolchain và API của Java 21

JDK 21 tạo class file với major version 65. Các thư viện xử lý bytecode như ASM, Byte Buddy, công cụ coverage, mocking, instrumentation và obfuscation cần phiên bản có thể đọc class file Java 21. Nếu compiler tạo được class nhưng một plugin hoặc agent không đọc được bytecode, lỗi có thể xuất hiện ở test, packaging hoặc lúc ứng dụng khởi động.

Với ứng dụng chuyển hẳn sang Java 21, dùng --release 21 để compiler kiểm tra đồng thời ngôn ngữ, bytecode và API Java SE theo release đích:

~~~shell
javac --release 21 -d out src/com/example/Main.java
~~~

Với Maven, cấu hình release ở compiler plugin:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Với Gradle, chọn JDK toolchain và release cho Java compilation:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Nếu cần tiếp tục phát hành artifact chạy trên Java 17 trong một giai đoạn chuyển tiếp, có thể build bằng JDK mới nhưng phải giữ --release 17 và không sử dụng API Java 21. Artifact biên dịch với release 21 không chạy được trên Java 17.

Hãy nâng các build plugin, test engine, framework và thư viện bytecode lên phiên bản hỗ trợ JDK 21 theo ma trận tương thích của nhà cung cấp. Không chỉ kiểm tra compiler: test runner, coverage agent, mock maker, APM agent và plugin đóng gói cũng có thể chạy bên trong JVM hoặc phân tích class file.

## 5. Quét dependency vào JDK internals và API deprecated

jdeps phát hiện dependency tĩnh vào API nội bộ của JDK. Chạy trên artifact và thư viện của ứng dụng:

~~~shell
jdeps --jdk-internals --multi-release 21 application.jar
~~~

Nếu kết quả có sun.*, com.sun.* hoặc package nội bộ khác, hãy tìm API được hỗ trợ thay thế và cập nhật thư viện sở hữu dependency đó. jdeps là phân tích tĩnh, không phát hiện đầy đủ các truy cập được thực hiện bằng reflection hoặc tên lớp tạo động; vì vậy vẫn cần integration test trên JDK 21.

Dùng jdeprscan để tìm API Java SE đã deprecated trong class file hoặc JAR:

~~~shell
jdeprscan application.jar
~~~

Khi có lỗi hoặc cảnh báo, xác định class và thư viện tạo ra nó trước khi thay thế. Đừng chỉ thêm --add-opens hoặc --add-exports hàng loạt để làm test chạy qua. Các cờ này chỉ nên dùng cho package và module cụ thể khi đã hiểu dependency, có kế hoạch cập nhật và kiểm soát rủi ro.

Tham khảo [jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html), [jdeprscan](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html) và hướng dẫn [Preparing for Migration](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html).

## 6. Kiểm tra agent và cảnh báo dynamic loading trong Java 21

JEP 451 thay đổi hành vi chẩn đoán agent: khi Java agent hoặc JVM TI agent được nạp động vào một JVM đang chạy, HotSpot trên JDK 21 in cảnh báo. Agent được nạp lúc JVM khởi động bằng -javaagent hoặc -agentlib không tạo cảnh báo này.

Tình huống có thể xuất hiện trong:

- Test framework hoặc mock framework dùng instrumentation.
- APM, profiler, debugger và công cụ quan sát.
- Thư viện tự attach vào JVM để cài agent.

Khi thấy cảnh báo, tìm thành phần gọi Attach API hoặc nạp agent động. Nếu agent được yêu cầu cho mọi lần chạy, ưu tiên cấu hình nạp agent lúc khởi động:

~~~shell
java -javaagent:agent.jar -jar application.jar
~~~

Nếu công cụ quản trị thực sự cần nạp agent sau khi JVM chạy, -XX:+EnableDynamicAgentLoading là lựa chọn opt-in trên HotSpot để cho phép hành vi đó và tắt cảnh báo tương ứng. Chỉ bật khi đã xác định công cụ và mục đích. Có thể dùng -Djdk.instrument.traceUsage để truy vết nơi gọi API instrumentation khi cần điều tra.

Không coi cảnh báo này là lỗi ứng dụng ngay lập tức; hãy xác định agent nào tạo ra nó và kiểm tra agent có hỗ trợ JDK 21. Tài liệu: [JEP 451](https://openjdk.org/jeps/451) và [JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html).

## 7. Áp dụng các tính năng Java 21 đã finalized

Java 21 có các tính năng ngôn ngữ đã trở thành chính thức, có thể dùng mà không bật preview:

### Record patterns

Record pattern cho phép kiểm tra kiểu record và lấy component trong cùng một biểu thức:

~~~java
record Point(int x, int y) {}

static int manhattanDistance(Object value) {
    if (value instanceof Point(int x, int y)) {
        return Math.abs(x) + Math.abs(y);
    }
    return 0;
}
~~~

Điều này có thể làm code xử lý DTO hoặc mô hình dữ liệu dạng record gọn hơn. Trước khi thay đổi, giữ nguyên các kiểm tra null, kiểu dữ liệu và nhánh lỗi của logic hiện tại.

### Pattern matching for switch

Switch có thể chọn nhánh theo kiểu và binding biến, đồng thời hỗ trợ biểu thức switch:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case Integer number -> "integer: " + number;
        case String text -> "text: " + text;
        default -> "other";
    };
}
~~~

Với sealed hierarchy, compiler có thể kiểm tra tính exhaustiveness của switch. Khi thêm subtype mới, các switch cần cập nhật sẽ được phát hiện trong quá trình biên dịch. Hãy kiểm tra các nhánh null và default theo hợp đồng nghiệp vụ; không thêm default một cách máy móc nếu muốn compiler cảnh báo khi hierarchy thay đổi.

Hai tính năng trên là finalized trong Java 21 theo [JEP 440](https://openjdk.org/jeps/440) và [JEP 441](https://openjdk.org/jeps/441). Không cần --enable-preview để sử dụng chúng.

## 8. Kiểm tra tác động của Sequenced Collections

Java 21 bổ sung SequencedCollection, SequencedSet và SequencedMap để biểu diễn rõ encounter order và cung cấp API thống nhất cho phần tử đầu, cuối và view đảo thứ tự.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> steps = new ArrayList<>(
        List.of("validate", "process", "publish")
);

String first = steps.getFirst();
String last = steps.getLast();
List<String> reverseView = steps.reversed();

System.out.println(first);
System.out.println(last);
System.out.println(reverseView);
~~~

reversed() trả về reverse-ordered view, không phải bản sao độc lập. Với collection có thể sửa, thao tác qua view có thể ghi xuyên xuống collection gốc. Các thao tác thêm/xóa ở hai đầu là optional; collection bất biến hoặc implementation không hỗ trợ có thể ném UnsupportedOperationException.

Đặc biệt kiểm tra các lớp tự triển khai List, Set, SortedSet, Map hoặc SortedMap. Các interface mới bổ sung default method như getFirst(), getLast(), reversed(), addFirst() và removeLast(). Method cùng tên trong lớp tự viết có thể vô tình trở thành override, gây xung đột chữ ký hoặc thay đổi cách gọi. Hãy biên dịch lại toàn bộ source, kiểm tra API public của thư viện nội bộ và chạy test thứ tự iteration.

Các interface này là thay đổi API Java Collections Framework theo [JEP 431](https://openjdk.org/jeps/431). Tài liệu Oracle có phần [Sequenced Collections](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html).

## 9. Đánh giá virtual threads như một lựa chọn, không phải bước bắt buộc

Virtual threads được finalized trong Java 21. Chúng phù hợp với nhiều tác vụ đồng thời có phần lớn thời gian chờ I/O và giúp giữ mô hình code blocking dễ đọc:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var first = executor.submit(() -> callServiceA());
    var second = executor.submit(() -> callServiceB());

    Result a = first.get();
    Result b = second.get();
}
~~~

Khi thử áp dụng:

- Tạo một virtual thread cho mỗi task; không tạo pool để tái sử dụng virtual thread.
- Dùng Semaphore, connection pool hoặc rate limiter để giới hạn tài nguyên thực sự khan hiếm.
- Rà soát ThreadLocal đang cache object nặng vì mỗi virtual thread có thể tạo một bản riêng.
- Đo throughput, latency, heap và số tác vụ chờ bằng workload đại diện.
- Giữ nguyên executor platform thread giới hạn cho tác vụ CPU-bound nếu số lượng song song cần được kiểm soát theo CPU.

Trên runtime Java 21, blocking trong synchronized hoặc native method có thể pin virtual thread vào carrier và ảnh hưởng khả năng mở rộng. Đo bằng JFR và kiểm tra vùng giữ monitor trước khi thay đổi đồng bộ hóa. Không thay toàn bộ synchronized bằng ReentrantLock nếu chưa xác định invariant được bảo vệ.

Hành vi pinning phụ thuộc phiên bản runtime: JDK 24 đã thay đổi monitor pinning theo JEP 491. Nếu ứng dụng sau này chạy JDK mới hơn, đánh giá theo tài liệu của runtime thực tế thay vì áp dụng nguyên xi kết luận dành riêng cho Java 21. Xem [Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) và [JEP 444](https://openjdk.org/jeps/444).

## 10. Kiểm tra thay đổi về ZGC nếu ứng dụng cần độ trễ thấp

Không cần đổi collector chỉ vì nâng lên Java 21. G1 vẫn là lựa chọn mặc định trên các cấu hình HotSpot thông thường; hãy giữ collector hiện tại làm baseline rồi đo trước khi đổi.

Nếu workload cần pause time thấp và đã benchmark cho thấy ZGC phù hợp, Java 21 có thể bật Generational ZGC bằng:

~~~shell
java -XX:+UseZGC -XX:+ZGenerational -Xmx4g -jar application.jar
~~~

Đây là cách bật riêng cho Java 21. Generational ZGC tận dụng khác biệt về tuổi object để thu gom Young Generation thường xuyên hơn. Hãy theo dõi allocation rate, live set, heap headroom, GC CPU, allocation stall và p95/p99 latency.

Phải phân biệt cấu hình theo runtime:

| Runtime | Cách chọn ZGC |
|---|---|
| Java 21 | -XX:+UseZGC -XX:+ZGenerational |
| JDK 23 | Generational mode là mặc định khi chọn ZGC |
| JDK 24 trở lên | ZGC chỉ còn generational mode; không truyền -XX:+ZGenerational vì option đã bị loại bỏ |

Không sao chép cờ Java 21 sang JDK mới hơn mà không kiểm tra. Tài liệu: [JEP 439](https://openjdk.org/jeps/439), [JEP 474](https://openjdk.org/jeps/474), [JEP 490](https://openjdk.org/jeps/490) và [ZGC Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html).

## 11. Đánh giá các API mới theo nhu cầu ứng dụng

Không cần thay toàn bộ code để dùng API mới. Chỉ áp dụng khi có use case và test phù hợp:

| API/thay đổi | Tác động migration | Cách kiểm chứng |
|---|---|---|
| HttpClient triển khai AutoCloseable | Có thể quản lý vòng đời client bằng try-with-resources hoặc lifecycle owner | Kiểm tra shutdown chờ request đang chạy và response body đã được đóng |
| javax.crypto.KEM | Có API KEM chuẩn trong JCA, thuật toán chuẩn Java 21 là DHKEM | Kiểm tra provider, key/curve và interoperability hai phía |
| Sequenced Collections | Có API first/last/reversed thống nhất | Kiểm tra encounter order và custom collection implementation |
| Virtual threads | Có mô hình thread-per-task cho I/O-bound workload | Benchmark và kiểm tra giới hạn tài nguyên |

Với KEM, không giả định thuật toán có mặt trên mọi provider hoặc mọi bản phân phối JDK. Java 21 định nghĩa tên DHKEM; Oracle JDK 21 cung cấp implementation trong SunJCE cho các key/curve được tài liệu hóa. Ứng dụng tổng quát nên yêu cầu thuật toán qua JCA mà không hard-code provider trừ khi chính sách triển khai yêu cầu. Tham khảo [KEM API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html) và [JEP 452](https://openjdk.org/jeps/452).

## 12. Kiểm tra thư viện, agent và môi trường triển khai

Ngoài code ứng dụng, lập danh sách thành phần chạy trong cùng JVM:

- Framework web, DI, ORM và validation.
- JDBC driver, database pool, HTTP client và messaging client.
- Logging, metrics, tracing, profiler và APM agent.
- Bytecode enhancement, mocking, coverage và test runner.
- JNI/JNA, thư viện native, TLS provider và security provider.
- Container image, base OS, architecture và memory limit.

Xác nhận nhà cung cấp công bố hỗ trợ JDK 21 cho đúng phiên bản. Đặc biệt kiểm tra thư viện tạo hoặc biến đổi bytecode, agent và framework dựa trên reflection. Test trên JDK 21 không thay thế kiểm tra native library theo hệ điều hành/CPU thực tế.

## 13. Chạy bộ kiểm thử theo từng lớp

Sau khi artifact đã chạy được trên JDK 21:

1. Chạy unit test và integration test bằng đúng JDK 21.
2. Chạy test encoding với dữ liệu UTF-8 và các encoding tích hợp được quy định.
3. Chạy test date, time, currency, locale và timezone với locale được production sử dụng.
4. Chạy test serialization, reflection, classpath/module path, service loading và resource lookup.
5. Chạy test database, transaction, connection pool, HTTP/TLS và messaging.
6. Kiểm tra cảnh báo dynamic agent, JVM flags và log khởi động.
7. Chạy smoke test trên container hoặc máy có cùng kiến trúc và giới hạn tài nguyên production.
8. Chạy load test để so sánh startup, throughput, p95/p99 latency, CPU, heap và GC với baseline Java 17.

Nếu kết quả khác, thay đổi từng yếu tố một. Không đổi JDK, framework, database driver và collector cùng lúc vì sẽ khó tìm nguyên nhân.

## 14. Quy trình triển khai có thể quay lại

Một lần rollout an toàn nên có các mốc xác nhận:

| Giai đoạn | Điều kiện đi tiếp |
|---|---|
| Local/CI với JDK 21 | Compile, unit test và static analysis thành công |
| Integration environment | Encoding, database, HTTP, agent và native integration hoạt động đúng |
| Staging với tải đại diện | Latency, throughput, CPU, memory và GC nằm trong ngưỡng |
| Canary | Error rate và p95/p99 không vượt ngưỡng rollback |
| Mở rộng rollout | Không có lỗi mới hoặc xu hướng suy giảm theo thời gian |

Giữ artifact Java 17 và cấu hình triển khai cũ trong thời gian rollout để có thể quay lại. Theo dõi cả log JVM lẫn metric nghiệp vụ; ứng dụng khởi động thành công chưa đủ để kết luận migration đã hoàn tất.

## 15. Checklist cuối cùng

- [ ] Ghi lại baseline Java 17 và danh sách toàn bộ JVM flags/dependency/agent.
- [ ] Chạy artifact hiện tại trên JDK 21 trước khi biên dịch lại.
- [ ] Kiểm tra default charset UTF-8 và chỉ định charset tại ranh giới file/protocol.
- [ ] Cập nhật build tool, compiler plugin, test runner và thư viện hỗ trợ class file version 65.
- [ ] Dùng --release 21 khi mục tiêu phát hành là Java 21.
- [ ] Chạy jdeps --jdk-internals và jdeprscan trên artifact.
- [ ] Xử lý cảnh báo dynamic agent theo JEP 451.
- [ ] Kiểm tra custom collection implementation với default methods mới.
- [ ] Chỉ bật virtual threads sau khi đo workload và giới hạn tài nguyên.
- [ ] Giữ cấu hình GC hiện tại làm baseline; benchmark trước khi chuyển ZGC.
- [ ] Kiểm thử API mới như KEM hoặc HttpClient lifecycle chỉ khi ứng dụng có nhu cầu.
- [ ] Chạy unit, integration, smoke và load test trên môi trường gần production.
- [ ] So sánh metric với baseline và chuẩn bị rollback trong rollout.

Nâng Java 17 lên Java 21 thành công khi artifact chạy đúng trên runtime mới, build và thư viện tương thích, dữ liệu không đổi ngoài dự kiến và metric nằm trong ngưỡng đã thống nhất. Các tính năng Java 21 như record patterns, switch patterns, sequenced collections và virtual threads là cơ hội cải thiện code sau khi nền tảng migration đã ổn định; không cần áp dụng tất cả trong cùng một lần nâng cấp.

## Tài liệu tham khảo

- [Oracle JDK 21 Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/)
- [Preparing for Migration](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html)
- [JDK 21 Significant Changes](https://docs.oracle.com/en/java/javase/21/migrate/significant-changes-jdk-release.html)
- [Java Language Changes for Java 21](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
