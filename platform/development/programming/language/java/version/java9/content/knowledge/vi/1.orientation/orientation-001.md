# Những nền tảng Java 9 còn được dùng trong Java hiện đại

## 1. Phạm vi và cách nhìn hiện nay

Java 9 là một mốc quan trọng vì giới thiệu hệ thống module và nhiều API, công cụ vẫn hiện diện trong các JDK hiện đại. Bản thân Java 9 đã hết vòng đời hỗ trợ, vì vậy không nên chọn Java 9 làm runtime mới cho ứng dụng. Điều có giá trị ngày nay là những tính năng Java 9 đã trở thành API ổn định và tiếp tục được duy trì trong các phiên bản JDK đang được hỗ trợ.

Bài này tập trung vào các nền tảng đó: module system, API collections và streams, Process API, I/O, concurrency, công cụ JDK, logging và cách kiểm soát mức tương thích khi build. Các API từng ở trạng thái incubator trong Java 9 chỉ được nhắc đến khi cần phân biệt vòng đời; không dùng chúng làm nền tảng cho mã mới.

## 2. Java Platform Module System (JPMS)

JPMS, thường được gọi là Project Jigsaw, đưa khái niệm module vào nền tảng Java. Một module có tên, khai báo phụ thuộc và xác định package nào được công khai cho module khác. Khai báo nằm trong file module-info.java.

Ví dụ một module ứng dụng:

~~~java
module com.acme.orders {
    requires java.logging;

    exports com.acme.orders.api;

    uses com.acme.orders.spi.PaymentProvider;

    provides com.acme.orders.spi.PaymentProvider
        with com.acme.orders.internal.DefaultPaymentProvider;
}
~~~

Các chỉ thị thường gặp:

- requires khai báo module phụ thuộc. Module cần được tìm thấy trên module path khi biên dịch và chạy.
- exports công khai một package cho module khác truy cập ở mức Java language access.
- opens cho phép reflection truy cập sâu vào package. Chỉ mở package cần thiết, có thể giới hạn cho một module cụ thể.
- uses khai báo module tiêu thụ một service.
- provides ... with ... khai báo implementation của service mà module cung cấp.

### 2.1. Module path và classpath

Classpath vẫn được hỗ trợ và vẫn phù hợp với nhiều ứng dụng. JPMS không bắt buộc mọi dự án phải chuyển sang module ngay lập tức.

Khi chạy ứng dụng modular, dùng module path và chỉ rõ module cùng main class:

~~~bash
java --module-path mods:lib -m com.acme.orders/com.acme.orders.Main
~~~

Trên Windows, dấu phân cách các thư mục trong module path là dấu chấm phẩy. Các build tool như Maven và Gradle có thể quản lý module path cho dự án; nên để build tool xử lý classpath/module path thay vì tự ghép chuỗi trong script.

Một JAR không có module-info.class có thể được đưa vào module path như automatic module. Cách này hữu ích khi chuyển đổi hệ thống cũ, nhưng tên module tự suy ra từ tên JAR có thể không ổn định. Thư viện muốn hỗ trợ JPMS nên khai báo Automatic-Module-Name trong manifest hoặc cung cấp module descriptor phù hợp.

### 2.2. Khi nào nên dùng JPMS

JPMS hữu ích khi ứng dụng cần ranh giới phụ thuộc rõ, muốn đóng gói runtime nhỏ, hoặc muốn kiểm soát package nào được module khác truy cập. Với ứng dụng chạy trên classpath, framework và thư viện chưa hỗ trợ modular tốt, có thể tiếp tục dùng classpath.

Không nên thêm module-info.java chỉ để có vẻ hiện đại. Trước khi modular hóa, hãy kiểm tra toàn bộ thư viện, annotation processor, plugin build và framework reflection. Các framework dùng reflection có thể cần opens cho package cụ thể; không mở toàn bộ module nếu không cần.

## 3. API Java 9 vẫn dùng thường xuyên

### 3.1. Factory method cho collection bất biến

Java 9 bổ sung List.of, Set.of, Map.of và Map.ofEntries để tạo collection ngắn gọn:

~~~java
List<String> roles = List.of("ADMIN", "EDITOR", "VIEWER");

Set<String> regions = Set.of("ap-southeast-1", "eu-west-1");

Map<String, Integer> statusCodes = Map.of(
    "OK", 200,
    "NOT_FOUND", 404
);

Map<String, Integer> extendedCodes = Map.ofEntries(
    Map.entry("OK", 200),
    Map.entry("NOT_FOUND", 404),
    Map.entry("CONFLICT", 409)
);
~~~

Các collection tạo bằng các factory method này không cho phép thêm, xóa hoặc thay thế phần tử. Chúng cũng không chấp nhận null. Set.of và Map.of sẽ báo lỗi nếu có phần tử hoặc key trùng lặp. List.of cho phép giá trị trùng lặp.

Đây là collection không sửa đổi được, nhưng không có nghĩa các object nằm bên trong cũng bất biến. Nếu phần tử là một object có setter, object đó vẫn có thể thay đổi.

Khi cần một danh sách có thể chỉnh sửa, tạo bản sao mutable:

~~~java
List<String> editableRoles = new ArrayList<>(roles);
editableRoles.add("AUDITOR");
~~~

Với Map.of, có các overload tối đa 10 cặp key/value; dùng Map.ofEntries khi cần nhiều cặp hơn.

### 3.2. Optional.stream và Stream API

Java 9 bổ sung các thao tác hữu ích để xử lý dữ liệu dạng stream:

- Optional.stream chuyển Optional có giá trị thành stream một phần tử, còn Optional rỗng thành stream rỗng.
- Stream.ofNullable(value) tạo stream rỗng nếu value là null, hoặc stream một phần tử nếu có giá trị.
- takeWhile lấy phần đầu của stream theo điều kiện.
- dropWhile bỏ phần đầu liên tiếp thỏa điều kiện rồi trả phần còn lại.

Ví dụ làm phẳng danh sách Optional:

~~~java
List<Optional<String>> candidates = List.of(
    Optional.of("An"),
    Optional.empty(),
    Optional.of("Binh")
);

List<String> names = candidates.stream()
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
~~~

Ví dụ lấy các phần tử đứng trước giá trị đầu tiên không còn thỏa điều kiện:

~~~java
List<Integer> values = List.of(2, 4, 6, 7, 8, 10);

List<Integer> prefix = values.stream()
    .takeWhile(value -> value % 2 == 0)
    .collect(Collectors.toList());

System.out.println(prefix);
~~~

Output:

~~~text
[2, 4, 6]
~~~

Với stream có encounter order, takeWhile và dropWhile làm việc trên phần đầu liên tiếp của stream. Với stream không có thứ tự, không nên giả định chúng sẽ chọn một prefix giống như danh sách có thứ tự. Nếu logic phụ thuộc thứ tự, hãy giữ nguồn dữ liệu ordered.

### 3.3. Private method trong interface

Java 9 cho phép interface có private instance method và private static method. Chúng giúp các default method hoặc static method chia sẻ logic nội bộ mà không biến helper thành API công khai.

~~~java
interface NameFormatter {
    default String format(String input) {
        return "[" + normalize(input) + "]";
    }

    private String normalize(String input) {
        return input == null ? "" : input.trim();
    }
}
~~~

Lớp triển khai chỉ gọi format. Nó không thể gọi trực tiếp normalize vì đây là private method của interface. Cách này phù hợp khi có nhiều default method cần dùng chung một đoạn xử lý.

### 3.4. Try-with-resources với biến effectively final

Từ Java 9, một biến resource đã được khai báo trước đó có thể được dùng trực tiếp trong try-with-resources nếu biến đó là final hoặc effectively final:

~~~java
BufferedReader reader = Files.newBufferedReader(path);

try (reader) {
    String firstLine = reader.readLine();
    System.out.println(firstLine);
}
~~~

Biến reader không bị gán lại sau khi khởi tạo. Khi thoát khỏi khối try, Java tự đóng resource, kể cả khi có exception. Nếu cần quản lý nhiều resource, có thể liệt kê chúng trong cùng dấu ngoặc của try-with-resources.

Cải tiến này giúp code ngắn hơn khi resource đã được tạo ở một bước chuẩn bị trước đó.

### 3.5. InputStream.transferTo

InputStream.transferTo(OutputStream) sao chép dữ liệu từ stream nguồn sang stream đích cho đến EOF và trả về số byte đã chuyển:

~~~java
try (InputStream input = Files.newInputStream(sourcePath);
     OutputStream output = Files.newOutputStream(targetPath)) {
    long copiedBytes = input.transferTo(output);
    System.out.println("Copied bytes: " + copiedBytes);
}
~~~

Phương thức này không tự đóng input hoặc output. Vì vậy, ứng dụng vẫn cần quản lý vòng đời stream bằng try-with-resources hoặc cơ chế quản lý resource phù hợp.

Dùng transferTo khi cần chuyển toàn bộ nội dung giữa hai stream. Nếu cần giới hạn số byte, biến đổi nội dung hoặc xử lý theo từng record, hãy dùng vòng lặp đọc/ghi phù hợp với yêu cầu.

## 4. Process API và concurrency

### 4.1. ProcessHandle

ProcessHandle cung cấp API chuẩn để lấy thông tin và quản lý tiến trình của hệ điều hành. Có thể truy cập tiến trình hiện tại, PID, trạng thái sống, tiến trình cha, tiến trình con và các tiến trình descendants.

~~~java
ProcessHandle current = ProcessHandle.current();

System.out.println("alive=" + current.isAlive());
System.out.println("pid=" + current.pid());

current.info().command().ifPresent(
    command -> System.out.println("command=" + command)
);
~~~

PID và command phụ thuộc môi trường nên không có stdout cố định. Các trường trong ProcessHandle.Info được trả về dưới dạng Optional vì hệ điều hành có thể không cung cấp đầy đủ thông tin.

Khi khởi chạy tiến trình con bằng ProcessBuilder, có thể lấy ProcessHandle từ Process.handle(), theo dõi tiến trình và đăng ký callback với onExit(). Cần xử lý trường hợp tiến trình kết thúc trước khi ứng dụng kịp đọc thông tin; trạng thái tiến trình có thể thay đổi giữa hai lần kiểm tra.

### 4.2. CompletableFuture có timeout

Java 9 bổ sung các phương thức hữu ích cho CompletableFuture:

- orTimeout đặt kết quả thành exceptional completion với TimeoutException nếu tương lai chưa hoàn tất trước thời hạn.
- completeOnTimeout hoàn tất tương lai bằng một giá trị dự phòng nếu quá thời hạn.
- delayedExecutor tạo Executor trì hoãn việc thực thi task.

Ví dụ:

~~~java
CompletableFuture<String> response = new CompletableFuture<>();

String value = response
    .completeOnTimeout("fallback", 100, TimeUnit.MILLISECONDS)
    .join();

System.out.println(value);
~~~

Output:

~~~text
fallback
~~~

Timeout trên CompletableFuture không tự động bảo đảm thao tác I/O hoặc công việc bên dưới đã bị hủy. Nếu cần hủy HTTP request, truy vấn database hoặc tiến trình con, phải kết nối timeout với cơ chế cancellation của chính thao tác đó.

### 4.3. Flow API và backpressure

Java 9 đưa Flow vào JDK với các interface Publisher, Subscriber, Subscription và Processor. Đây là bộ hợp đồng cho luồng dữ liệu bất đồng bộ có backpressure.

Subscriber đăng ký với Publisher, nhận Subscription và yêu cầu số phần tử có thể xử lý thông qua request(n). Publisher chỉ nên phát dữ liệu trong giới hạn nhu cầu đã được yêu cầu. Subscriber có thể hủy subscription khi không còn cần dữ liệu.

Flow hữu ích khi xây dựng thành phần reactive tương thích với Reactive Streams. Trong ứng dụng thực tế, nhiều dự án sử dụng thư viện như Reactor hoặc RxJava để có thêm operator và tích hợp hệ sinh thái. Khi tích hợp, hãy kiểm tra đúng phiên bản và adapter; không tạo hai hệ thống điều khiển backpressure độc lập trên cùng một luồng dữ liệu.

## 5. API nền tảng phục vụ chẩn đoán và thư viện

### 5.1. StackWalker

StackWalker cung cấp cách duyệt call stack hiện tại theo hướng lazy. Nó hữu ích khi cần xác định caller, thu thập một số frame hoặc lọc frame của reflection mà không cần tạo toàn bộ stack trace.

~~~java
String caller = StackWalker.getInstance().walk(frames ->
    frames.skip(1)
        .findFirst()
        .map(StackWalker.StackFrame::getMethodName)
        .orElse("unknown")
);
~~~

Chỉ dùng khi thông tin call stack thực sự cần thiết cho chẩn đoán hoặc framework. Không nên dùng việc đọc stack để thay thế thiết kế API, truyền context tường minh hoặc cơ chế tracing.

### 5.2. VarHandle

VarHandle cung cấp cách truy cập có kiểu vào field, phần tử array hoặc biến tĩnh với các memory ordering và atomic operation được chỉ định. Nó là nền tảng cho một số cấu trúc concurrency trong JDK và thư viện hiệu năng cao.

Trong code nghiệp vụ thông thường, AtomicInteger, AtomicReference, volatile, synchronized hoặc Lock thường dễ đọc và dễ kiểm tra hơn. Chỉ dùng VarHandle khi cần kiểm soát memory semantics ở mức thấp và có hiểu biết về Java Memory Model.

### 5.3. System.Logger

System.Logger là logging API tiêu chuẩn trong JDK. Nó cho phép thư viện hoặc ứng dụng phát log mà không phải phụ thuộc trực tiếp vào một logging backend cụ thể:

~~~java
private static final System.Logger LOG =
    System.getLogger(OrderService.class.getName());

void start() {
    LOG.log(System.Logger.Level.INFO, "Order service started");
}
~~~

JDK có logger provider mặc định và có thể tích hợp provider phù hợp. Với ứng dụng cần cấu hình tập trung, structured logging, correlation ID hoặc nhiều appender, vẫn nên chọn logging framework phù hợp với kiến trúc dự án.

## 6. Công cụ JDK 9 vẫn hữu ích

### 6.1. JShell

JShell là môi trường REPL đi kèm JDK, cho phép thử biểu thức, câu lệnh và API nhanh mà không cần tạo một dự án hoàn chỉnh:

~~~bash
jshell
~~~

Ví dụ trong JShell:

~~~java
jshell> List<String> roles = List.of("ADMIN", "EDITOR");
jshell> roles.size()
$2 ==> 2
~~~

JShell hữu ích để kiểm tra nhanh API, thử xử lý dữ liệu hoặc giải thích ví dụ nhỏ. Mã đã ổn định vẫn nên được chuyển vào source file, build và test theo quy trình của dự án.

### 6.2. jdeps và jlink

jdeps phân tích dependency ở mức class hoặc module. Công cụ này giúp phát hiện module JDK mà ứng dụng cần, kiểm tra phụ thuộc và chuẩn bị cho việc tạo runtime image.

~~~bash
jdeps --print-module-deps --module-path lib app.jar
~~~

Cần cung cấp classpath hoặc module path đầy đủ nếu ứng dụng phụ thuộc thư viện bên ngoài. Nếu thiếu dependency, kết quả phân tích có thể không đầy đủ.

jlink tạo runtime image tùy chỉnh từ các module đã chọn:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.orders --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

Ví dụ giả định ứng dụng đã được đóng gói thành named module com.acme.orders và mọi module phụ thuộc đều có trên module path. Trên Windows, dùng dấu chấm phẩy để phân tách các đường dẫn.

jlink giúp giảm kích thước runtime và kiểm soát các module JDK được đóng gói. Nó không tự đóng gói mọi thư viện bên thứ ba, file cấu hình hoặc tài nguyên ứng dụng. Các dependency ngoài JDK vẫn phải được đóng gói và triển khai theo cách phù hợp.

### 6.3. Multi-Release JAR

Multi-Release JAR cho phép một thư viện phân phối nhiều phiên bản implementation trong cùng một JAR. JVM chọn class trong thư mục phiên bản cao nhất không vượt quá phiên bản runtime đang chạy.

Ví dụ cấu trúc:

~~~text
example-library.jar
  META-INF/
    MANIFEST.MF
    versions/
      17/
        com/acme/Codec.class
  com/
    acme/
      Codec.class
~~~

Manifest phải có thuộc tính:

~~~text
Multi-Release: true
~~~

Class ở gốc JAR là implementation nền, tương thích với Java release thấp nhất mà thư viện hỗ trợ. Class trong META-INF/versions/17 có thể dùng API Java 17 để tối ưu cho runtime mới hơn. Runtime cũ hơn sẽ dùng class nền.

Tính năng này phù hợp với tác giả thư viện cần hỗ trợ nhiều runtime trong một artifact. Cần kiểm tra bytecode, API và test trên từng runtime; đừng để implementation phiên bản cao làm thay đổi contract công khai của thư viện.

## 7. Logging JVM và garbage collector

### 7.1. Unified JVM Logging

Java 9 giới thiệu unified logging với tùy chọn -Xlog. Cách này vẫn là giao diện chuẩn để thu thập log từ JVM, bao gồm GC, class loading, module, safepoint và nhiều thành phần khác.

Ví dụ bật log GC và safepoint ra standard output:

~~~bash
java -Xlog:gc*,safepoint=info:stdout:time,uptime,level,tags -jar app.jar
~~~

Có thể chọn tag, level, output và decorator theo nhu cầu vận hành. Trong production, cần kiểm soát dung lượng log, vị trí lưu, rotation và quyền truy cập. Không bật mọi tag ở mức chi tiết cao trong thời gian dài nếu chưa đánh giá tác động và dung lượng.

### 7.2. G1 Garbage Collector

Java 9 đặt G1 làm collector mặc định cho cấu hình server-class. G1 vẫn là lựa chọn phổ biến trong các JDK hiện đại, nhưng collector thực tế còn phụ thuộc vào JDK distribution, kiến trúc, heap và cấu hình JVM.

Có thể xem thông tin khởi tạo GC bằng:

~~~bash
java -Xlog:gc+init=info -version
~~~

Không nên sao chép bộ cờ GC từ một máy chủ khác mà không đo đạc. Hãy quan sát allocation rate, pause time, heap occupancy, throughput và đặc điểm workload trước khi thay đổi collector hoặc tuning. Các lựa chọn GC hiện đại khác có thể phù hợp hơn với yêu cầu latency hoặc throughput cụ thể.

## 8. Kiểm soát mức Java khi build

Một nền tảng quan trọng khác được giới thiệu cùng JDK 9 là tùy chọn javac --release. Nó giới hạn đồng thời cú pháp ngôn ngữ, API nền tảng và định dạng bytecode theo release mục tiêu.

Ví dụ biên dịch bằng JDK mới nhưng giữ tương thích Java 17:

~~~bash
javac --release 17 -d out src/main/java/com/acme/App.java
~~~

Thư mục out phải tồn tại trước khi chạy lệnh. Có thể tạo bằng mkdir out trên shell Unix hoặc New-Item -ItemType Directory out trên PowerShell.

Nếu chỉ đặt source và target, compiler có thể vẫn nhìn thấy API mới của JDK đang chạy. Mã nguồn vì vậy có thể biên dịch thành công nhưng gọi API không tồn tại trên runtime thấp hơn. --release tránh được phần lớn lỗi tương thích API nền tảng này.

### 8.1. Maven

Với Maven Compiler Plugin phiên bản hỗ trợ thuộc tính release, cấu hình mức Java trong pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hãy pin phiên bản Maven Compiler Plugin và Maven Wrapper trong dự án để build ổn định giữa máy cá nhân và CI. Release mục tiêu cần trùng với mức thấp nhất mà sản phẩm cam kết hỗ trợ.

### 8.2. Gradle

Với Gradle Kotlin DSL, có thể khai báo Java toolchain và release:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Ví dụ này dùng JDK 21 để biên dịch nhưng chỉ cho phép cú pháp, API nền tảng và bytecode Java 17. Toolchain điều khiển JDK mà task sử dụng; options.release xác định mức tương thích của mã nguồn đầu ra.

JDK chạy Gradle Daemon vẫn là một vấn đề riêng. Phiên bản Gradle Wrapper phải tương thích với JDK chạy build. Kiểm tra bằng ./gradlew --version và log toolchain khi có khác biệt giữa máy cá nhân và CI.

### 8.3. Build và test trên runtime được hỗ trợ

--release không chứng minh rằng mọi thư viện bên thứ ba, native library hoặc framework đều chạy được trên runtime mục tiêu. CI vẫn cần kiểm tra:

1. Biên dịch bằng JDK/toolchain đã được dự án phê duyệt.
2. Chạy unit test trên runtime thấp nhất mà sản phẩm hỗ trợ.
3. Chạy integration test trên các runtime nằm trong support matrix.
4. Kiểm tra JAR/container image thực tế và JDK bên trong môi trường triển khai.
5. Ghi nhận JDK distribution, patch version, build tool và ngày kiểm tra.

Nên dùng Maven Wrapper hoặc Gradle Wrapper đã được commit, pin plugin và dependency quan trọng, đồng thời cập nhật JDK patch theo chính sách bảo mật của tổ chức.

## 9. Ví dụ chạy tổng hợp

Lưu chương trình sau vào file Java9FoundationsDemo.java. Ví dụ kết hợp các API Java 9 vẫn dùng được trên JDK hiện đại: collection factory, private interface method, Stream.takeWhile, Optional.stream, InputStream.transferTo, CompletableFuture timeout và ProcessHandle.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import java.util.stream.Stream;

interface Labeler {
    default String label(String value) {
        return "[" + normalize(value) + "]";
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}

public class Java9FoundationsDemo implements Labeler {
    public static void main(String[] args) throws Exception {
        List<String> levels = List.of("HIGH", "NORMAL", "LOW");
        Map<String, Integer> statusCodes = Map.of(
            "OK", 200,
            "NOT_FOUND", 404
        );

        List<String> activeLevels = levels.stream()
            .takeWhile(level -> !level.equals("LOW"))
            .collect(Collectors.toList());

        List<String> names = Stream.of(
                Optional.of("An"),
                Optional.<String>empty(),
                Optional.of("Binh")
            )
            .flatMap(Optional::stream)
            .collect(Collectors.toList());

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (InputStream input = new ByteArrayInputStream(
                "Java 9".getBytes(StandardCharsets.UTF_8))) {
            input.transferTo(output);
        }

        String fallback = new CompletableFuture<String>()
            .completeOnTimeout("fallback", 10, TimeUnit.MILLISECONDS)
            .join();

        Java9FoundationsDemo demo = new Java9FoundationsDemo();

        System.out.println("levels=" + levels);
        System.out.println("statusOk=" + statusCodes.get("OK"));
        System.out.println("active=" + activeLevels);
        System.out.println("names=" + names);
        System.out.println("copied=" +
            new String(output.toByteArray(), StandardCharsets.UTF_8));
        System.out.println("label=" + demo.label(" Java "));
        System.out.println("timeout=" + fallback);
        System.out.println("processAlive=" + ProcessHandle.current().isAlive());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 Java9FoundationsDemo.java
java Java9FoundationsDemo
~~~

Stdout:

~~~text
levels=[HIGH, NORMAL, LOW]
statusOk=200
active=[HIGH, NORMAL]
names=[An, Binh]
copied=Java 9
label=[Java]
timeout=fallback
processAlive=true
~~~

Chương trình không phụ thuộc vào network hoặc tiến trình bên ngoài. Timeout được hoàn tất bằng giá trị fallback trước khi join trả về. PID không được in ra vì PID thay đổi theo lần chạy và môi trường.

## 10. Lưu ý khi đọc tài liệu Java 9 cũ

Khi tra cứu tài liệu hoặc ví dụ từ thời Java 9, hãy xác định trạng thái của API trước khi áp dụng:

- Phân biệt API đã được chuẩn hóa với API từng ở trạng thái incubator hoặc preview. Chỉ dùng API ổn định có trong JDK mục tiêu.
- HTTP Client từng xuất hiện dưới dạng incubator trong Java 9. API ổn định hiện nay là java.net.http, được chuẩn hóa từ Java 11; dự án hiện đại nên dùng API chuẩn này.
- Kiểm tra module, class và tùy chọn JVM theo đúng JDK đang triển khai. Không giả định mọi ví dụ Java 9 vẫn có mặt hoặc hoạt động giống nhau trong mọi bản JDK hiện đại.
- Không copy cờ JVM, dependency hoặc plugin từ một bài viết cũ nếu chưa kiểm tra trạng thái hỗ trợ và tác động của chúng.

Mục tiêu là giữ lại các API và công cụ Java 9 vẫn được duy trì, đồng thời dùng phiên bản JDK, build tool và thư viện đang được hỗ trợ.

## 11. Checklist áp dụng

- [ ] Xác định JDK distribution và các runtime mà sản phẩm hỗ trợ.
- [ ] Chọn classpath hoặc JPMS dựa trên yêu cầu thật của ứng dụng.
- [ ] Dùng List.of, Set.of, Map.of khi cần collection không sửa đổi được.
- [ ] Dùng Optional.stream và các thao tác Stream khi chúng làm rõ logic xử lý dữ liệu.
- [ ] Dùng ProcessHandle và CompletableFuture timeout cho quản lý tiến trình/tác vụ bất đồng bộ khi phù hợp.
- [ ] Quản lý stream và resource bằng try-with-resources.
- [ ] Dùng jdeps/jlink khi cần phân tích module hoặc tạo runtime image.
- [ ] Dùng -Xlog để chẩn đoán JVM và GC.
- [ ] Khai báo --release trong Maven hoặc Gradle để cố định mức API/bytecode.
- [ ] Chạy CI trên các runtime trong support matrix và kiểm tra artifact thực tế.
- [ ] Loại bỏ ví dụ dựa trên API incubator, preview hoặc đã bị loại khỏi JDK mục tiêu.

## Tài liệu tham khảo

- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
- [Collection Factory Methods — JEP 269](https://openjdk.org/jeps/269)
- [More Concurrency Updates — JEP 266](https://openjdk.org/jeps/266)
- [Process API Updates — JEP 102](https://openjdk.org/jeps/102)
- [Stack-Walking API — JEP 259](https://openjdk.org/jeps/259)
- [Unified JVM Logging — JEP 158](https://openjdk.org/jeps/158)
- [Multi-Release JAR Files — JEP 238](https://openjdk.org/jeps/238)
- [javac command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [jlink command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html)
- [jdeps command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html)
- [Maven Compiler Plugin: Setting the --release option](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle: Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
