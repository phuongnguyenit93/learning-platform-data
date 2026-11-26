# Đo hiệu năng với JMH, kiểm soát warmup và phân tích GC thay vì suy luận từ cú pháp

## 1. Cú pháp mới là một giả thuyết cần đo

Một phiên bản Java mới có thể cung cấp cách diễn đạt công việc rõ hơn. Điều đó chưa đủ để kết luận chương trình chạy nhanh hơn, cấp phát ít hơn hoặc có độ trễ ổn định hơn.

Ví dụ, Stream Gatherers là một phần của nội dung Java 22 và đã trở thành API chính thức từ Java 24. Khi cân nhắc thay đoạn gom nhóm thủ công bằng `Gatherers.windowFixed`, cần so sánh trên cùng dữ liệu và cùng yêu cầu đầu ra. Tài liệu hiện hành mô tả hành vi của API, không cam kết một thứ hạng hiệu năng chung giữa mọi cách viết. Xem [Gatherers trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html).

Bài này dùng JMH để xây dựng phép đo trên API còn áp dụng ở Java hiện đại. Ví dụ biên dịch và chạy bằng JDK 27, dùng Gatherers chính thức nên không cần bật preview.

Một phát biểu có thể kiểm chứng là:

> Với danh sách không chứa null, một thread xử lý và kết quả được tạo đầy đủ thành các danh sách không cho sửa, cách chia cửa sổ nào có thời gian và lượng cấp phát phù hợp hơn trên JDK, heap và collector đã chọn?

Phát biểu “stream luôn chậm” hoặc “API mới luôn nhanh” không xác định đủ điều kiện để kiểm chứng.

## 2. Xác định phép đo trước khi viết benchmark

| Câu hỏi | Đại lượng cần quan sát | Giới hạn khi diễn giải |
| --- | --- | --- |
| Một lần xử lý mất bao lâu? | `AverageTime`, chẳng hạn `us/op` | Một operation phải có ý nghĩa rõ ràng |
| Xử lý được bao nhiêu công việc? | `Throughput`, chẳng hạn `ops/s` | Phụ thuộc số worker và mức tranh chấp |
| Mỗi công việc cấp phát bao nhiêu? | `gc.alloc.rate.norm`, đơn vị `B/op` khi được hỗ trợ | Không phải lượng heap còn sống sau GC |
| Tốc độ cấp phát lớn thế nào? | `gc.alloc.rate`, đơn vị do profiler báo | Bị ảnh hưởng bởi tốc độ thực thi operation |
| Collector hoạt động ra sao? | Số lần/thời gian GC và GC log | Cần xem collector và các pha cụ thể |
| Người dùng chờ bao lâu trong dịch vụ? | Phân bố độ trễ dưới tải thực tế | Microbenchmark không thay thế phép đo toàn dịch vụ |

Với ví dụ trong bài, **một operation là chia toàn bộ danh sách đầu vào thành các cửa sổ và tạo đầy đủ đầu ra**. Nó không phải xử lý một phần tử hay tạo một cửa sổ riêng lẻ.

Nếu thay kích thước danh sách, mỗi operation thực hiện lượng công việc khác nhau. Phải so hai phương án ở cùng bộ tham số trước khi diễn giải chênh lệch.

## 3. Tạo môi trường JMH có thể tái lập

JMH cần mã harness được sinh từ benchmark. Chỉ thêm `jmh-core` vào class path và gọi trực tiếp phương thức có `@Benchmark` không tạo ra phép đo JMH đúng cách.

Dự án JMH khuyến khích module benchmark riêng và cung cấp Maven archetype để tạo cấu hình chuẩn. Xem [hướng dẫn sử dụng JMH](https://github.com/openjdk/jmh#usage).

Ví dụ dưới đây là một dự án Maven độc lập, với cấu hình sinh harness và đóng gói JAR thực thi. Các phiên bản được cố định để bản dựng có thể được ghi nhận cùng kết quả; không cần hiểu chúng là một yêu cầu dùng phiên bản mới nhất.

Cấu trúc:

```text
jmh-window-study/
  pom.xml
  src/
    main/
      java/
        bench/
          WindowBenchmark.java
```

### 3.1. Cấu hình Maven

Dùng JDK 27 và Maven hỗ trợ các plugin được chọn. Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>learning.java</groupId>
    <artifactId>jmh-window-study</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>27</maven.compiler.release>
        <jmh.version>1.37</jmh.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>${jmh.version}</version>
        </dependency>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-generator-annprocess</artifactId>
            <version>${jmh.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <annotationProcessors>
                        <annotationProcessor>org.openjdk.jmh.generators.BenchmarkProcessor</annotationProcessor>
                    </annotationProcessors>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <finalName>benchmarks</finalName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Annotation processor được khai báo tường minh. Điều này phù hợp với các JDK hiện đại, nơi không nên dựa vào việc compiler tự tìm mọi processor trên class path. Cơ chế này cũng có trong [mẫu Maven của JMH](https://github.com/openjdk/jmh/blob/master/jmh-archetypes/jmh-java-benchmark-archetype/src/main/resources/archetype-resources/pom.xml).

Thông tin phiên bản: [JMH 1.37](https://javadoc.io/doc/org.openjdk.jmh/jmh-core/1.37/index.html), [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/summary.html) và [Maven Shade Plugin](https://maven.apache.org/plugins/maven-shade-plugin/summary.html).

### 3.2. Ghi nhận công cụ thực sự sử dụng

Trước khi build hoặc đo:

```shell
java --version
javac --version
mvn --version
```

Lưu lại đường dẫn và phiên bản JDK dùng cho compiler, launcher và JVM fork. Nếu có toolchain hoặc cấu hình IDE riêng, phiên bản mà shell báo chưa chắc là phiên bản của mọi tiến trình đó.

## 4. Benchmark hoàn chỉnh: gom cửa sổ với cùng hợp đồng đầu ra

Tệp `src/main/java/bench/WindowBenchmark.java`:

```java
package bench;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
@Threads(1)
public class WindowBenchmark {

    @Param({"8", "1024", "65537"})
    public int size;

    @Param({"16", "128"})
    public int windowSize;

    private List<Integer> input;

    @Setup(Level.Trial)
    public void setup() {
        input = IntStream.range(0, size).boxed().toList();

        // Kiểm tra hợp đồng dữ liệu trước giai đoạn đo.
        if (!manualWindows().equals(gathererWindows())) {
            throw new IllegalStateException(
                    "Hai phương án tạo kết quả khác nhau");
        }
    }

    @Benchmark
    public List<List<Integer>> manual() {
        return manualWindows();
    }

    @Benchmark
    public List<List<Integer>> gatherer() {
        return gathererWindows();
    }

    private List<List<Integer>> manualWindows() {
        int windowCount =
                (input.size() + windowSize - 1) / windowSize;

        List<List<Integer>> windows =
                new ArrayList<>(windowCount);

        for (int start = 0;
             start < input.size();
             start += windowSize) {

            int end = Math.min(
                    start + windowSize,
                    input.size());

            windows.add(List.copyOf(input.subList(start, end)));
        }

        return List.copyOf(windows);
    }

    private List<List<Integer>> gathererWindows() {
        return input.stream()
                .gather(Gatherers.windowFixed(windowSize))
                .toList();
    }
}
```

### 4.1. Vì sao hai phương án có thể so sánh?

Trong phạm vi đầu vào của benchmark, cả hai cùng:

- Giữ thứ tự phần tử.
- Tạo cửa sổ không chồng lấp.
- Giữ cửa sổ cuối khi số phần tử không chia hết.
- Tạo danh sách ngoài và danh sách cửa sổ không cho sửa.
- Tạo đầy đủ đầu ra trong mỗi operation.

Đầu vào không có `null`, không bị sửa và được chuẩn bị trước giai đoạn đo. Việc tạo các `Integer` đầu vào nằm trong setup, nên benchmark tập trung vào chi phí chia cửa sổ từ một danh sách đã có.

Các kích thước có chủ đích: 8 phần tử cho trường hợp cửa sổ lớn hơn dữ liệu; 1024 cho đầu vào vừa; 65537 cho trường hợp có cửa sổ cuối thiếu phần tử.

Cách viết thủ công đã biết kích thước để cấp trước dung lượng danh sách ngoài. Đây là đặc điểm của phương án đang so sánh và cần được giữ trong mô tả kết quả.

### 4.2. Phép đo này chưa bao phủ mọi cách dùng

Kết quả mỗi lần gọi được đưa ra khỏi phương thức benchmark rồi không được ứng dụng mẫu giữ lâu dài. Nếu hệ thống thực tế giữ các cửa sổ trong cache hoặc hàng đợi, thời gian sống của đối tượng và hành vi GC có thể khác.

Nếu nghiệp vụ thực tế chỉ cần tổng hợp một con số, đừng bắt cả hai phương án tạo danh sách chỉ để có một benchmark dễ viết. Hãy đo đúng kiểu tiêu thụ đầu ra của nghiệp vụ.

## 5. Warmup, measurement và fork là ba khái niệm riêng

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| `@Setup(Level.Trial)` | Chuẩn bị dữ liệu cho trial trước các iteration |
| `@Warmup` | Thực thi công việc để JVM tích lũy trạng thái trước phần tính điểm |
| `@Measurement` | Các iteration được dùng để tạo kết quả đo |
| `@Fork(3)` | Chạy benchmark trong nhiều JVM mới |
| `@State(Scope.Thread)` | Mỗi worker có state riêng |
| `@Threads(1)` | Một worker thực hiện benchmark trong cấu hình mặc định của ví dụ |

Thời gian một iteration là khoảng thời gian JMH lặp lại thao tác benchmark, không phải thời gian của một lần gọi.

### 5.1. Warmup giúp xử lý điều gì?

Trong những lần chạy đầu, JVM có thể còn nạp lớp, thu thập profile, biên dịch JIT và thay đổi mã đã tối ưu. Cache và trạng thái heap cũng có thể khác so với giai đoạn hoạt động sau đó.

Warmup tách giai đoạn này khỏi các iteration tính điểm. Tuy nhiên, đặt năm iteration không chứng minh rằng mọi benchmark đều đã ổn định. Số iteration và thời lượng trong ví dụ là điểm khởi đầu của thí nghiệm.

Hãy xem chuỗi kết quả theo iteration:

- Nếu thời gian vẫn giảm có xu hướng khi measurement bắt đầu, cần điều tra quá trình khởi động/JIT và thử warmup dài hơn.
- Nếu có những đợt tăng đột ngột, đối chiếu GC, tải máy và hoạt động hệ điều hành.
- Nếu các fork chênh đáng kể, xem lại môi trường, profile và số lần lặp độc lập.

Các tham số warmup và measurement được mô tả trong [annotation Warmup](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/annotations/Warmup.java) và [Measurement](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/annotations/Measurement.java).

Nếu mục tiêu là thời gian khởi động ứng dụng, một benchmark đã warmup đang trả lời câu hỏi khác. Cần thiết kế phép đo khởi động tiến trình hoặc thí nghiệm cold start tương ứng; đo một phương thức ở chế độ single shot cũng không tự bao gồm toàn bộ startup của dịch vụ.

### 5.2. Fork không phải thread

Một fork tạo JVM mới, giúp giảm việc các benchmark ảnh hưởng nhau thông qua profile tối ưu hóa tích lũy trong cùng tiến trình. Tác động của profile dùng chung được minh họa trong [JMH Sample 12: Forking](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).

Fork không đặt lại toàn bộ trạng thái hệ điều hành, nhiệt độ CPU hay tải máy. Vì vậy, nhiều fork vẫn cần một môi trường đo được kiểm soát.

Không dùng `-f 0` làm cấu hình kết luận chỉ để rút ngắn thời gian chạy. Cấu hình không fork có ích khi gỡ lỗi, nhưng làm thay đổi tính độc lập giữa harness và môi trường benchmark.

## 6. Build, kiểm tra harness và chạy phép đo

Từ thư mục dự án mẫu:

```shell
mvn clean verify
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar -h
```

Danh sách benchmark phải có `bench.WindowBenchmark.manual` và `bench.WindowBenchmark.gatherer`. Nếu thiếu thông tin benchmark được sinh, hãy kiểm tra annotation processing và artifact đã đóng gói.

Có thể chạy thử một bộ tham số ngắn để kiểm tra cấu hình:

```shell
java -jar target/benchmarks.jar 'bench.WindowBenchmark.*' -p size=1024 -p windowSize=16 -f 1 -wi 1 -i 1 -w 1s -r 1s
```

Lần thử này chỉ giúp phát hiện lỗi cấu hình và lỗi thực thi. Không dùng nó để chốt phương án tối ưu.

### 6.1. Đo thời gian

Ví dụ một cấu hình thí nghiệm với một worker, ba fork và G1 được chọn tường minh:

```shell
java -jar target/benchmarks.jar 'bench.WindowBenchmark.*' -f 3 -wi 5 -i 8 -w 1s -r 1s -t 1 -jvmArgsAppend "-Xms1g -Xmx1g -XX:+UseG1GC" -rf json -rff jmh-time.json
```

Heap 1 GiB và G1 là điều kiện của ví dụ, không phải cấu hình tối ưu cho mọi ứng dụng. Hãy chọn cấu hình phù hợp với bộ nhớ máy và câu hỏi thí nghiệm, rồi giữ cùng điều kiện cho các phương án.

Lệnh trên chạy nhiều bộ tham số nên có thể mất nhiều phút. Khi khảo sát một trường hợp, chọn rõ `-p size=...` và `-p windowSize=...`.

### 6.2. Đo kèm allocation và GC

Chạy một lần riêng với cùng cấu hình, thêm GC profiler:

```shell
java -jar target/benchmarks.jar 'bench.WindowBenchmark.*' -f 3 -wi 5 -i 8 -w 1s -r 1s -t 1 -jvmArgsAppend "-Xms1g -Xmx1g -XX:+UseG1GC" -prof gc -rf json -rff jmh-gc.json
```

Dữ liệu profiler giúp giải thích nguyên nhân. Khi so thời gian, cần so các lần chạy có cùng mức instrumentation; profiler có thể tác động đến phép đo.

Các tùy chọn CLI có thể ghi đè annotation. Vì vậy, lưu cả mã benchmark lẫn dòng lệnh và phần đầu output JMH. Các cờ như `-jvm`, `-jvmArgsAppend`, `-rf` và `-rff` được định nghĩa trong [tùy chọn dòng lệnh của JMH](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/runner/options/CommandLineOptions.java).

JVM fork mới là nơi thực thi payload. Đặt cờ heap, GC hoặc module cho đúng JVM đó và kiểm tra thông tin JMH in ra, thay vì chỉ nhìn cấu hình của launcher.

## 7. Giữ benchmark khỏi bị tối ưu thành công việc khác

### 7.1. Kết quả phải được sử dụng

Nếu tính toán xong rồi bỏ kết quả, JIT có thể loại bỏ công việc không còn ảnh hưởng quan sát được. Ví dụ trả đầu ra từ phương thức `@Benchmark` để JMH tiêu thụ kết quả.

Đây là cơ chế được giải thích trong [JMH Sample 08: Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

Nếu có nhiều đầu ra cần giữ, có thể dùng `Blackhole` do JMH cung cấp. Không cần tiêu thụ từng phần tử bằng Blackhole nếu hành vi nghiệp vụ đang đo chỉ tạo và trả cả danh sách; thêm công việc đó sẽ thay đổi payload.

### 7.2. Tránh tính toán chỉ dựa trên hằng số

Một biểu thức nhỏ với đầu vào là hằng có thể được tính trước. `@State` và `@Param` giúp đưa dữ liệu của thí nghiệm vào benchmark, nhưng không phải bảo đảm tự động chống mọi tối ưu hóa.

Cần kiểm tra nguồn dữ liệu và công việc thực sự còn tồn tại khi kết quả quá khác kỳ vọng. Xem [JMH Sample 10: Constant Folding](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java).

### 7.3. Không tự thêm vòng lặp chỉ để “đo cho đủ lâu”

JMH đã lặp lại phương thức benchmark. Một vòng lặp nhân tạo bên trong có thể tạo cơ hội tối ưu khác rồi làm kết quả chia trung bình trở nên sai lệch.

Vòng lặp trong `manualWindows` là công việc thật để chia danh sách nên được giữ lại. Điều cần tránh là bọc thêm hàng nghìn lần chia danh sách chỉ để tự chia thời gian sau đó. Xem [JMH Sample 11: Loops](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java).

### 7.4. Không làm biến dạng dữ liệu qua mỗi lần gọi

Nếu benchmark sắp xếp một mảng, lần đầu có thể nhận dữ liệu chưa sắp, còn các lần sau nhận mảng đã sắp. Khi đó workload đã thay đổi.

Ví dụ trong bài không sửa đầu vào. Với thao tác có sửa dữ liệu, cần quyết định rõ chi phí sao chép/khôi phục thuộc phần việc nào. `@Setup(Level.Invocation)` có chi phí và tác động riêng, không phải cách mặc định để che mọi chi phí chuẩn bị. Xem [JMH Sample 38: Per-Invocation Setup](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_38_PerInvokeSetup.java).

Không ghi log, tạo số ngẫu nhiên hoặc truy cập mạng trong payload nếu những việc đó không thuộc câu hỏi đang đo.

## 8. Đọc allocation và GC theo đúng ý nghĩa

Khi GC profiler và JVM hỗ trợ các bộ đếm tương ứng, có thể quan sát:

| Chỉ số | Ý nghĩa | Không nên suy ra |
| --- | --- | --- |
| `gc.alloc.rate.norm` | Lượng byte cấp phát được profiler ghi nhận trên một operation | Kích thước toàn bộ heap hoặc bộ nhớ sống lâu |
| `gc.alloc.rate` | Tốc độ cấp phát trong khoảng profiler theo dõi | Phương án có số này thấp luôn cấp phát ít hơn mỗi công việc |
| `gc.count` | Chênh lệch bộ đếm số lần collection | Số lần dừng ứng dụng có cùng độ dài |
| `gc.time` | Chênh lệch thời gian collection theo bộ đếm GC | Độ trễ p99 của request hoặc tổng mọi pause được đo riêng |

Cách tính và đơn vị của các metric có thể kiểm tra trong [GCProfiler của JMH 1.37](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/profile/GCProfiler.java).

### 8.1. Phân biệt B/op và tốc độ cấp phát

Một phương án chạy được nhiều operation hơn mỗi giây có thể có tốc độ cấp phát lớn hơn, ngay cả khi cấp phát trên mỗi operation bằng phương án kia.

Khi câu hỏi là “mỗi lần chia danh sách tạo bao nhiêu dữ liệu”, ưu tiên xem `B/op`. Khi câu hỏi là “tải này gây áp lực cấp phát lớn thế nào”, xem thêm tốc độ operation và tốc độ cấp phát.

Tài liệu mẫu JMH minh họa sự phụ thuộc của metric không chuẩn hóa vào tốc độ benchmark trong [Sample 35: Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java).

### 8.2. Allocation không đồng nghĩa với bộ nhớ bị giữ lại

Đối tượng cấp phát có thể sống rất ngắn rồi được thu gom. Một phương án khác có thể cấp phát ít nhưng giữ tham chiếu đến cấu trúc lớn trong thời gian dài.

Vì vậy, ít `B/op` hơn chưa đủ để kết luận ít footprint hơn trong dịch vụ có cache, hàng đợi hoặc kết quả được giữ lâu. Cần thêm quan sát về tập đối tượng còn sống và vòng đời tham chiếu.

Một view từ `subList` cũng không có cùng hợp đồng với một bản sao cửa sổ. Không thay bản sao bằng view chỉ ở một phía rồi gọi đó là tối ưu cú pháp tương đương.

### 8.3. Số GC bằng không chưa chứng minh không có chi phí GC

Trong cửa sổ đo ngắn hoặc heap rộng, có thể chưa xảy ra collection. Việc cấp phát vẫn có thể diễn ra và tạo áp lực về sau.

Ngược lại, thời gian GC tăng không đủ để quy toàn bộ chênh lệch thời gian cho collector. Cần đối chiếu lượng cấp phát, tải thực hiện, tập đối tượng sống và GC log.

Không lấy `gc.time` chia số operation rồi coi kết quả là độ trễ pause mà mọi request đã trải qua. Bộ đếm GC, thời gian pha concurrent và thời gian dừng ứng dụng không phải cùng một đại lượng.

### 8.4. Kiểm tra profiler có quan sát được công việc không

Hỗ trợ metric phụ thuộc JVM, phiên bản JMH và cách thu thập dữ liệu. Trường bị thiếu hoặc giá trị không khả dụng không có nghĩa là bằng không.

Đặc biệt, khi benchmark tạo/hủy thread, dùng virtual thread hoặc chuyển công việc sang executor, cần kiểm tra bộ đếm có bao phủ các cấp phát ở nơi thực thi thật hay không. Có thể cần đối chiếu bằng JFR hoặc công cụ quan sát khác.

Ví dụ trong bài giữ payload trên worker JMH để hạn chế thêm biến số này.

## 9. Dùng GC log để kiểm tra giả thuyết nguyên nhân

Khi cần xem diễn biến GC, chạy một thí nghiệm chẩn đoán có phạm vi nhỏ:

```shell
java -jar target/benchmarks.jar 'bench.WindowBenchmark.*' -p size=65537 -p windowSize=16 -f 1 -wi 5 -i 5 -jvmArgsAppend "-Xms1g -Xmx1g -XX:+UseG1GC -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags"
```

`%p` giúp phân biệt tệp log theo tiến trình fork. Cờ được truyền qua JMH tới JVM đo. Cú pháp `-Xlog` thuộc cơ chế Unified Logging hiện hành; xem [tài liệu lệnh java và GC logging](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework).

Những điều cần đối chiếu với thời điểm iteration:

- Có collection hoặc pause trùng với đợt thời gian tăng không?
- Heap sau collection có xu hướng tăng qua các lần không?
- Có pha concurrent hoặc hoạt động ngoài payload cần được xem riêng không?
- Collector có thay đổi hành vi khi tập dữ liệu hoặc heap thay đổi không?

Logging cũng có chi phí. Dùng lần chạy này để điều tra, rồi xác nhận lại kết luận thời gian bằng cấu hình đo thống nhất.

Không chèn `System.gc()` giữa các lần gọi để “làm sạch” một cách mặc định. Điều đó thêm một điều kiện khác vào workload và không bảo đảm tái lập trạng thái giống môi trường thật.

## 10. Đọc Score, Error và chênh lệch thực tế

Với `AverageTime`, score thấp hơn biểu thị thời gian trung bình thấp hơn trong cấu hình đang đo. Đơn vị phải được đọc cùng score.

`Cnt` là số mẫu mà JMH tổng hợp, không phải số lần phương thức nghiệp vụ được gọi. Trong một iteration, phương thức có thể được gọi rất nhiều lần.

Với kết quả trung bình, JMH tính sai số và khoảng tin cậy thống kê; `Error` không phải p99 hay giá trị lớn nhất. Cách tính có trong [lớp Result của JMH](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/results/Result.java).

Bảng dưới đây là **số giả định để luyện cách đọc**, không phải kết quả chạy benchmark của bài:

| Phương án | AverageTime | Allocation chuẩn hóa |
| --- | --- | --- |
| Thủ công | 82 ± 3 us/op | 131072 B/op |
| Gatherer | 78 ± 4 us/op | 196608 B/op |

Cách đọc có trách nhiệm:

- Điểm trung bình của gatherer thấp hơn trong ví dụ giả định.
- Các khoảng sai số có vùng chồng lấp; chỉ nhìn hai score chưa đủ để khẳng định một khác biệt ổn định.
- Allocation mỗi operation lớn hơn là một đặc điểm khác cần đánh giá dưới tải phù hợp.
- Cần xem kết quả từng fork, phân bố dữ liệu và ý nghĩa thực tế của mức chênh lệch.

Sự chồng lấp khoảng tin cậy không phải một phép kiểm định đầy đủ cho mọi trường hợp. Đừng biến nó thành quy tắc máy móc “chồng lấp thì chắc chắn bằng nhau” hoặc “không chồng lấp thì đủ để triển khai”.

Nếu một thay đổi chỉ tiết kiệm lượng thời gian rất nhỏ trong phần việc không đáng kể của request, lợi ích tổng thể có thể không đủ lớn để bù độ phức tạp. Cần xác nhận bằng phép đo của ứng dụng.

## 11. Kiểm soát biến số khi nâng cấp JDK

Đối với một thay đổi từ Java 22 sang JDK hiện đại, có ít nhất hai câu hỏi khác nhau:

| Câu hỏi | Cách tổ chức phép đo |
| --- | --- |
| Runtime mới ảnh hưởng thế nào? | Giữ workload và artifact tương thích chung khi có thể; thay runtime theo thiết kế thí nghiệm |
| Viết lại bằng API mới ảnh hưởng thế nào? | So hai cách triển khai trên cùng JDK đích |
| Cấu hình GC mới ảnh hưởng thế nào? | Giữ mã và tải; thay cấu hình collector/heap có chủ đích |
| Toàn bộ lần nâng cấp mang lại gì? | Đo cấu hình trước và sau, rồi tách thí nghiệm để giải thích các nguồn thay đổi |

Ví dụ Gatherers trong bài dùng API chính thức và class nhắm Java 27. Không thể lấy nguyên JAR đó chạy trên Java 22 rồi coi là một phép so runtime tương đương.

Với artifact preview, việc đổi JDK còn có ràng buộc phiên bản riêng; cần biên dịch lại theo JDK đích và ghi rõ thay đổi API. Khi không thể giữ chung artifact, báo rõ giới hạn: kết quả phản ánh cả thay đổi mã/build và runtime theo điều kiện đã chọn.

Trong một đợt đo, nên cố định hoặc ghi nhận:

- Nhà cung cấp, phiên bản cập nhật JDK và tùy chọn JVM.
- Phiên bản JMH, commit mã nguồn và cấu hình build.
- Collector, heap, số worker, tham số dữ liệu và khả năng phần cứng liên quan.
- CPU, RAM, hệ điều hành, giới hạn CPU/bộ nhớ của container nếu có.
- Tải nền, chế độ năng lượng và điều kiện làm việc của máy.

Nếu mục tiêu là so runtime với cùng collector, chọn collector tường minh. Nếu mục tiêu là so cấu hình mặc định của từng môi trường, giữ mặc định có chủ đích và ghi lại collector thực sự được chọn.

## 12. Những dấu hiệu phép so sánh chưa công bằng

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Một phía trả stream, phía kia trả danh sách | Một phía chưa thực thi đầy đủ pipeline |
| Một phía trả view, phía kia sao chép dữ liệu | Khác hợp đồng sở hữu và vòng đời dữ liệu |
| Một phía đã có dữ liệu boxed, phía kia phải boxing trong payload | Khác ranh giới chuẩn bị dữ liệu |
| Một phía chạy tuần tự, phía kia song song | Khác số tài nguyên và mô hình thực thi |
| Một phía ghi log hoặc thực hiện I/O phụ | Đang đo thêm công việc khác |
| Benchmark trả về quá nhanh so với công việc dự kiến | Có thể đã loại bỏ công việc hoặc gấp hằng |
| Kết quả nhanh dần qua cả measurement | Warmup hoặc trạng thái dữ liệu chưa phù hợp |
| Tăng thread nhưng dùng state không đúng ý định | Có thể tạo tranh chấp hoặc chia sẻ không đại diện |
| Số cấp phát thấp bất thường khi dùng thread khác | Kiểm tra độ bao phủ của profiler |
| Thay mã, JDK và heap cùng lúc | Chưa tách được nguyên nhân chênh lệch |

`Scope.Thread` cung cấp state theo worker; `Scope.Benchmark` chia sẻ state giữa các worker. Chọn scope phải phản ánh cách dữ liệu được chia sẻ trong workload, không chọn chỉ vì nó tạo điểm số đẹp hơn. Xem [annotation State](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/annotations/State.java).

Tăng `-t` không có nghĩa là đã mô phỏng chính xác số request đồng thời của một dịch vụ. Còn phải xét I/O, hàng đợi, giới hạn kết nối, tài nguyên dùng chung và cách phát tải.

## 13. Từ kết quả JMH đến quyết định trong dự án

Một trình tự làm việc hữu ích:

1. Viết câu hỏi và hợp đồng đầu ra trước khi viết benchmark.
2. Kiểm tra hai phương án thực hiện cùng công việc.
3. Chạy thử để xác nhận harness, tham số và kết quả nghiệp vụ.
4. Quan sát warmup, rồi chọn thời lượng measurement và số fork đủ cho câu hỏi.
5. Đo thời gian và allocation trong điều kiện đã ghi nhận.
6. Dùng profiler/GC log để giải thích điểm bất thường.
7. Lặp lại thí nghiệm khi có giả thuyết mới hoặc biến số chưa được kiểm soát.
8. Xác nhận lợi ích trên workload ứng dụng trước khi quyết định triển khai.

Mẫu ghi nhận kết quả:

```text
Câu hỏi:
Commit và hai phương án:
Hợp đồng đầu ra:
JDK / JMH / cấu hình build:
CPU / RAM / hệ điều hành / giới hạn tài nguyên:
Collector / heap / số worker:
Dữ liệu và tham số:
Warmup / measurement / fork:
Dòng lệnh:
Tệp kết quả JSON:
Thời gian và khoảng sai số:
Allocation mỗi operation:
Diễn biến GC:
Giới hạn của phép đo:
Kết quả xác nhận trong ứng dụng:
```

Quyết định cuối cùng nên gắn với mục tiêu cụ thể như giảm thời gian xử lý, giảm áp lực cấp phát hoặc đáp ứng ngân sách tài nguyên. Khả năng đọc hiểu và bảo trì cũng là tiêu chí lựa chọn; các con số JMH cung cấp bằng chứng trong phạm vi thí nghiệm đã mô tả.