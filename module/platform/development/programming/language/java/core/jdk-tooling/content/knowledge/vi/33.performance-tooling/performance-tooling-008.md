# Benchmarking Java bằng JMH

## 1. Benchmarking là gì?

**Benchmarking** là quá trình đo hiệu năng của một chương trình hoặc một phần chương trình trong những điều kiện được kiểm soát. Mục tiêu là hiểu một thay đổi ảnh hưởng thế nào tới thời gian xử lý, throughput, độ trễ, mức cấp phát bộ nhớ và khả năng mở rộng.

Một benchmark tốt phải trả lời được ba câu hỏi:

1. Đang đo chính xác thao tác nào?
2. Điều kiện đo có đại diện cho cách ứng dụng chạy thật không?
3. Kết quả có đủ ổn định và có thể lặp lại để so sánh không?

Trong Java, phép đo có thể bị ảnh hưởng mạnh bởi JVM và JIT compiler. Một đoạn code chạy nhanh ở lần đầu có thể chậm hơn sau khi class loading, JIT compilation hoặc garbage collection xảy ra. Vì vậy, benchmark Java cần tính đến warmup, fork, dữ liệu đầu vào, thread và trạng thái runtime.

## 2. Phân biệt microbenchmark và macrobenchmark

| Loại benchmark | Phạm vi | Ví dụ | Công cụ phù hợp |
|---|---|---|---|
| Microbenchmark | Một method hoặc thao tác nhỏ | Ghép chuỗi, parse số, lookup collection | JMH |
| Component benchmark | Một thành phần có nhiều method và dependency | Serializer, cache client, repository | JMH hoặc harness riêng có kiểm soát |
| Macrobenchmark | Một luồng nghiệp vụ hoàn chỉnh | Xử lý một HTTP request hoặc batch job | Load testing và production-like test |
| System/load test | Toàn hệ thống dưới tải đồng thời | Throughput, latency p95/p99, saturation | Gatling, k6, JMeter và metrics hệ thống |

JMH được thiết kế cho microbenchmark trên JVM. Nó không tự động chứng minh một endpoint HTTP hoặc toàn bộ hệ thống sẽ nhanh hơn trong production.

Nếu cần đánh giá một luồng nghiệp vụ, hãy đo bằng workload gần thực tế, có network, database, cache, concurrency và dữ liệu đại diện. Có thể dùng JMH để tìm chi phí của một thao tác nhỏ nằm bên trong luồng đó.

## 3. Vì sao không nên tự đo bằng vòng lặp nanoTime?

Một cách đo thường gặp:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    calculate();
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Đoạn code này dễ tạo ra kết quả sai lệch:

- JIT chưa warmup hoặc đang biên dịch method trong lúc đo.
- Dead-code elimination có thể loại bỏ kết quả không được sử dụng.
- Constant folding có thể tính trước biểu thức chỉ phụ thuộc hằng số.
- Inlining, escape analysis và scalar replacement có thể thay đổi code được thực thi.
- Vòng lặp lớn có thể bị unroll hoặc tối ưu theo cách không giống thao tác thật.
- Timer, loop overhead, GC và scheduling có thể chiếm tỷ trọng lớn đối với thao tác rất ngắn.
- Một lần chạy không thể hiện độ biến thiên giữa các process JVM.

System.nanoTime() là đồng hồ phù hợp để đo khoảng thời gian đơn điệu trong Java, nhưng việc tự viết vòng lặp không thay thế được một benchmark harness có warmup, measurement, fork và cách tiêu thụ kết quả được kiểm soát.

## 4. JMH giải quyết những vấn đề nào?

**Java Microbenchmark Harness (JMH)** là bộ công cụ OpenJDK dành cho việc xây dựng và chạy microbenchmark Java.

JMH cung cấp:

- Annotation processor tạo benchmark harness cho các method được đánh dấu.
- Warmup và measurement iterations riêng biệt.
- Fork process JVM để giảm ảnh hưởng của trạng thái JIT từ benchmark khác.
- Quản lý thread và state theo phạm vi được khai báo.
- Các benchmark mode như average time, throughput và sample time.
- Blackhole để ngăn kết quả bị tối ưu loại bỏ.
- Profiler tích hợp để xem allocation, GC và một số thông tin runtime.
- Kết quả thống kê qua nhiều iteration thay vì một phép đo duy nhất.

JMH giúp chuẩn hóa cách đo, nhưng không thể tự sửa một benchmark có workload không đại diện, dữ liệu không phù hợp hoặc cách so sánh thiếu kiểm soát.

## 5. Tạo project Maven với JMH

Ví dụ dưới đây dùng JMH 1.37, Java release 17, Maven Compiler Plugin 3.13.0 và Maven Shade Plugin 3.6.0.

Cấu trúc thư mục:

~~~text
jmh-demo/
  pom.xml
  src/
    main/
      java/
        benchmarks/
          StringJoinBenchmark.java
~~~

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>jmh-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-core</artifactId>
      <version>1.37</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <annotationProcessorPaths>
            <path>
              <groupId>org.openjdk.jmh</groupId>
              <artifactId>jmh-generator-annprocess</artifactId>
              <version>1.37</version>
            </path>
          </annotationProcessorPaths>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals>
              <goal>shade</goal>
            </goals>
            <configuration>
              <finalName>benchmarks</finalName>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>org.openjdk.jmh.Main</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

jmh-core cung cấp API benchmark và runner. jmh-generator-annprocess được khai báo làm annotation processor để tạo mã harness khi biên dịch. Shade plugin đóng gói dependency và đặt entry point là org.openjdk.jmh.Main.

Từ thư mục chứa pom.xml, build:

~~~bash
mvn package
~~~

Nếu build thành công, file chạy được tạo tại:

~~~text
target/benchmarks.jar
~~~

Máy mới có thể cần tải dependency từ Maven repository ở lần build đầu tiên.

## 6. Viết benchmark đầu tiên

Tạo file **StringJoinBenchmark.java**:

~~~java
package benchmarks;

import java.util.concurrent.TimeUnit;
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
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 2, time = 200, timeUnit = TimeUnit.MILLISECONDS)
@Measurement(iterations = 3, time = 200, timeUnit = TimeUnit.MILLISECONDS)
@Fork(1)
public class StringJoinBenchmark {
    @Param({"8", "64"})
    public int elements;

    private String[] parts;

    @Setup(Level.Trial)
    public void setup() {
        parts = new String[elements];
        for (int i = 0; i < elements; i++) {
            parts[i] = "item-" + i;
        }
    }

    @Benchmark
    public String plusInLoop() {
        String result = "";
        for (String part : parts) {
            result += part;
        }
        return result;
    }

    @Benchmark
    public String stringBuilder() {
        StringBuilder result = new StringBuilder();
        for (String part : parts) {
            result.append(part);
        }
        return result.toString();
    }
}
~~~

Benchmark có hai cách ghép cùng một mảng chuỗi:

- plusInLoop dùng toán tử cộng chuỗi trong vòng lặp.
- stringBuilder dùng StringBuilder.append().

Mảng đầu vào được tạo trong setup(), không phải trong method đang đo. @Param chạy benchmark với hai kích thước đầu vào. Mỗi benchmark method trả về kết quả để JMH tiêu thụ, tránh kết quả bị loại bỏ như dead code.

Ví dụ này minh họa cách xây dựng benchmark, không khẳng định StringBuilder luôn nhanh hơn trong mọi workload. Kết quả phụ thuộc kích thước chuỗi, JDK, dữ liệu, collector và môi trường chạy.

## 7. Ý nghĩa các annotation quan trọng

| Annotation | Vai trò |
|---|---|
| @Benchmark | Đánh dấu method cần đo. |
| @State | Khai báo đối tượng state và phạm vi chia sẻ. |
| @Param | Cung cấp nhiều giá trị đầu vào cho một benchmark. |
| @Setup | Chuẩn bị state trước trial, iteration hoặc invocation. |
| @TearDown | Giải phóng hoặc reset state ở lifecycle tương ứng. |
| @BenchmarkMode | Chọn cách biểu diễn hiệu năng. |
| @OutputTimeUnit | Chọn đơn vị hiển thị thời gian. |
| @Warmup | Cấu hình warmup iterations. |
| @Measurement | Cấu hình measurement iterations. |
| @Fork | Số process JVM độc lập dùng để chạy benchmark. |
| @Threads | Số thread chạy benchmark. |
| @OperationsPerInvocation | Khai báo số thao tác logic trong một lần gọi benchmark method. |

Benchmark method thường là public, có thể nhận tham số state được JMH hỗ trợ và trả về một giá trị hoặc void. Không tự gọi benchmark method từ main để lấy kết quả; hãy để JMH runner điều khiển lifecycle.

## 8. Warmup, measurement và fork

Ba khái niệm này rất quan trọng với JVM.

### Warmup

Warmup chạy benchmark trước khi ghi kết quả measurement. Nó cho JVM thời gian thực hiện class loading, profiling và JIT compilation.

Ví dụ:

~~~java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Năm warmup iterations, mỗi iteration một giây, là ví dụ cấu hình. Workload phức tạp có thể cần warmup dài hơn. Không giả định số iteration cố định sẽ luôn làm mọi benchmark ổn định.

### Measurement

Measurement là giai đoạn JMH thu thập số liệu.

~~~java
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Nhiều iteration giúp quan sát độ biến thiên giữa các lần đo. Measurement quá ngắn có thể bị nhiễu bởi scheduling, GC hoặc hoạt động nền.

### Fork

Fork chạy benchmark trong process JVM mới. Điều này giúp tách profile JIT, heap và trạng thái runtime giữa các lần thử.

~~~java
@Fork(3)
~~~

Ba fork tạo ba process JVM độc lập. Khi so sánh hai cách triển khai, dùng cùng số fork, warmup, measurement và JVM arguments.

Warmup không thay thế fork; fork cũng không thay thế measurement. Cả ba cùng giúp kết quả đáng tin cậy hơn.

## 9. Các benchmark mode

JMH hỗ trợ nhiều mode:

| Mode | Ý nghĩa | Đơn vị thường gặp |
|---|---|---|
| Throughput | Số thao tác hoàn thành trong một đơn vị thời gian. | ops/s |
| AverageTime | Thời gian trung bình cho một thao tác. | ns/op, us/op, ms/op |
| SampleTime | Lấy mẫu thời gian thao tác để xem phân phối. | ns/op và percentile |
| SingleShotTime | Đo từng lần thực thi đơn lẻ trong iteration. | ns/op, us/op |
| All | Chạy tất cả mode mà JMH hỗ trợ. | Tùy mode |

Chọn mode theo câu hỏi:

- Muốn biết một method xử lý được bao nhiêu request/operation mỗi giây: Throughput.
- Muốn biết trung bình một operation mất bao lâu: AverageTime.
- Muốn xem phân phối và percentile của thời gian: SampleTime.
- Muốn đo hành vi one-shot hoặc cold path: SingleShotTime, đồng thời thiết kế fork/warmup phù hợp.

Ví dụ cấu hình AverageTime:

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
~~~

Có thể dùng mode khác bằng annotation hoặc command line:

~~~java
@BenchmarkMode(Mode.Throughput)
~~~

~~~bash
java -jar target/benchmarks.jar -bm thrpt
~~~

Không so sánh trực tiếp score của hai mode khác nhau như thể chúng cùng đơn vị.

## 10. State scope và concurrency

@State xác định một đối tượng state được chia sẻ như thế nào giữa các thread.

| Scope | Cách chia sẻ | Trường hợp dùng |
|---|---|---|
| Scope.Thread | Mỗi benchmark thread có state riêng. | Đo thao tác độc lập, tránh contention do chia sẻ state. |
| Scope.Benchmark | Các thread trong benchmark dùng chung một state. | Đo cấu trúc dữ liệu hoặc tài nguyên chia sẻ. |
| Scope.Group | State được chia sẻ trong nhóm thread. | Mô phỏng nhóm reader/writer hoặc workload có vai trò khác nhau. |

Ví dụ:

~~~java
@State(Scope.Thread)
public class ThreadLocalState {
    int counter;
}
~~~

Với Scope.Benchmark, nhiều thread có thể truy cập cùng object. Nếu benchmark cập nhật dữ liệu dùng chung, phải xử lý thread safety như trong ứng dụng thật. Synchronized, lock contention và false sharing có thể trở thành một phần chi phí được đo.

Có thể đặt số thread trên command line:

~~~bash
java -jar target/benchmarks.jar -t 4
~~~

Đừng mặc định tăng thread sẽ làm throughput tăng. Khi contention, memory bandwidth hoặc CPU saturation xuất hiện, throughput có thể chững lại và latency tăng.

## 11. Setup và teardown theo lifecycle

JMH có ba mức lifecycle thường dùng:

| Level | Khi chạy | Dùng cho |
|---|---|---|
| Trial | Một lần cho một trial của state. | Tạo dữ liệu hoặc resource dùng chung trong toàn benchmark trial. |
| Iteration | Trước/sau mỗi warmup hoặc measurement iteration. | Reset dữ liệu giữa các iteration. |
| Invocation | Trước/sau từng lần gọi benchmark method. | Chuẩn bị state rất cụ thể cho mỗi invocation. |

Ví dụ:

~~~java
@Setup(Level.Trial)
public void setupTrial() {
    // Tạo dữ liệu dùng trong trial.
}

@Setup(Level.Iteration)
public void setupIteration() {
    // Reset trạng thái giữa các iteration.
}
~~~

Thời gian chạy setup/teardown không được tính trực tiếp như phần thực thi benchmark method, nhưng việc chuẩn bị state vẫn có thể ảnh hưởng cache, GC và hành vi runtime.

Tránh @Setup(Level.Invocation) cho thao tác cực ngắn nếu không thật sự cần. Chi phí lifecycle, allocation và việc làm nóng dữ liệu ở mỗi invocation có thể khiến workload khác xa ứng dụng thật.

## 12. Dead-code elimination và Blackhole

JIT có thể loại bỏ phép tính nếu kết quả không được sử dụng. Ví dụ:

~~~java
@Benchmark
public void brokenBenchmark() {
    calculateValue();
}
~~~

Nếu calculateValue() không có side effect và kết quả không được dùng, compiler có thể loại bỏ một phần hoặc toàn bộ công việc.

Cách đơn giản là trả về kết quả:

~~~java
@Benchmark
public int returnResult() {
    return calculateValue();
}
~~~

JMH tự tiêu thụ giá trị trả về của benchmark method.

Nếu cần tiêu thụ nhiều kết quả hoặc method phải trả về void, dùng Blackhole:

~~~java
import org.openjdk.jmh.infra.Blackhole;

@Benchmark
public void consumeResult(Blackhole blackhole) {
    int value = calculateValue();
    blackhole.consume(value);
}
~~~

Không cần tự tạo một biến volatile dùng chung chỉ để giữ kết quả. Việc ghi volatile có chi phí riêng và có thể làm thay đổi chính thao tác đang đo.

Blackhole giúp chống dead-code elimination nhưng không đảm bảo benchmark phản ánh workload thực tế. Hãy xem code sinh ra hoặc dùng profiler nếu nghi ngờ benchmark bị tối ưu ngoài dự kiến.

## 13. Constant folding, inlining và dữ liệu đầu vào

Một biểu thức chỉ phụ thuộc hằng số có thể được tính trước:

~~~java
@Benchmark
public int constantExpression() {
    return 42 * 42;
}
~~~

Benchmark này có thể đo việc trả về một hằng số đã tính sẵn thay vì phép nhân như người viết mong muốn.

Dùng dữ liệu đầu vào có ý nghĩa runtime:

~~~java
@State(Scope.Thread)
public class CalculationBenchmark {
    @Param({"17", "29", "41"})
    public int input;

    @Benchmark
    public int square() {
        return input * input;
    }
}
~~~

JMH chạy nhiều trial với các giá trị @Param. Tuy nhiên, @Param không phải biện pháp chống mọi tối ưu hóa; cần bảo đảm dữ liệu và thao tác vẫn đại diện cho trường hợp thực tế.

Inlining và escape analysis là tối ưu hợp lệ của JVM. Không cố vô hiệu hóa mọi tối ưu hóa chỉ để tạo một con số đẹp. Nếu ứng dụng thật cũng được JIT tối ưu như vậy, benchmark nên phản ánh điều đó.

## 14. Vòng lặp và OperationsPerInvocation

Không nên tự bọc một thao tác nhỏ trong vòng lặp lớn chỉ để kéo dài thời gian đo:

~~~java
@Benchmark
public int looped() {
    int result = 0;
    for (int i = 0; i < 1000; i++) {
        result += calculate(i);
    }
    return result;
}
~~~

Vòng lặp có thể bị unroll, vectorize hoặc tối ưu khác với từng invocation riêng. JMH vốn đã gọi benchmark method đủ nhiều lần để thu thập mẫu.

Nếu nghiệp vụ thật là xử lý một batch cố định, vòng lặp trong benchmark là hợp lý. Có thể dùng:

~~~java
@OperationsPerInvocation(1000)
~~~

để khai báo một lần benchmark method tương ứng 1000 operation logic và chuẩn hóa score theo số operation đó.

Chỉ dùng annotation này khi số operation thực sự cố định và mỗi invocation luôn thực hiện đúng số lượng đã khai báo. Với batch có kích thước thay đổi, cần diễn giải score và đơn vị rõ ràng.

## 15. Allocation và garbage collection

Benchmark allocation cần đo cả chi phí cấp phát lẫn tác động GC nếu đó là hành vi của workload.

Có thể dùng GC profiler tích hợp:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

Một số metric thường gặp:

- gc.alloc.rate: tốc độ cấp phát bộ nhớ.
- gc.alloc.rate.norm: số byte cấp phát chuẩn hóa trên mỗi operation.
- gc.count: số lần garbage collection trong thời gian đo.
- gc.time: tổng thời gian GC được profiler ghi nhận.

Nếu một implementation nhanh hơn nhưng cấp phát nhiều object hơn, lợi thế có thể biến mất khi chạy lâu hoặc dưới tải cao.

Không mặc định tắt GC để benchmark allocation. Chỉ thay đổi GC configuration khi mục tiêu nghiên cứu chính là so sánh collector hoặc xác định tác động của một flag cụ thể.

## 16. Profiling benchmark

Khi thấy một benchmark chậm, cần biết thời gian đang tiêu tốn ở đâu.

Một số profiler có thể dùng với JMH:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

Trên Linux, tùy hệ thống và quyền, có thể thử profiler dựa trên perf:

~~~bash
java -jar target/benchmarks.jar -prof perf
~~~

Profiler phụ thuộc hệ điều hành, kernel, quyền truy cập và công cụ được cài. Không giả định mọi profiler đều hoạt động trên Windows hoặc trong container.

Có thể dùng Java Flight Recorder hoặc async-profiler để xem CPU sample, allocation, lock và call stack. Khi profiling, hãy phân biệt số liệu của lần chạy có profiler với kết quả benchmark không profiler vì profiler có thể tạo overhead.

## 17. Chạy benchmark và đọc danh sách

Sau khi build:

~~~bash
java -jar target/benchmarks.jar -l
~~~

Với project mẫu, JMH liệt kê:

~~~text
Benchmarks:
benchmarks.StringJoinBenchmark.plusInLoop
benchmarks.StringJoinBenchmark.stringBuilder
~~~

Chạy hai benchmark với cấu hình đo dài hơn:

~~~bash
java -jar target/benchmarks.jar 'benchmarks.StringJoinBenchmark.*' -wi 5 -i 8 -f 3 -w 1s -r 1s -t 1
~~~

Ý nghĩa các tham số:

| Tham số | Ý nghĩa |
|---|---|
| -wi 5 | Năm warmup iterations. |
| -i 8 | Tám measurement iterations. |
| -f 3 | Ba fork process JVM độc lập. |
| -w 1s | Mỗi warmup iteration kéo dài một giây. |
| -r 1s | Mỗi measurement iteration kéo dài một giây. |
| -t 1 | Một benchmark thread. |

Chạy một cấu hình ngắn để xác minh project hoặc debug harness:

~~~bash
java -jar target/benchmarks.jar 'benchmarks.StringJoinBenchmark.*' -p elements=8 -wi 1 -i 2 -f 1 -w 100ms -r 100ms
~~~

Cấu hình ngắn phù hợp smoke test. Không dùng score từ một warmup iteration, hai measurement iterations và một fork làm kết luận tối ưu hiệu năng.

## 18. Lưu kết quả và so sánh

Có thể xuất kết quả thành JSON:

~~~bash
java -jar target/benchmarks.jar -rf json -rff results.json
~~~

Một kết quả JMH thường có các trường:

| Trường | Ý nghĩa |
|---|---|
| Benchmark | Tên method được đo. |
| Mode | Benchmark mode. |
| Cnt | Số iteration được dùng để tính kết quả. |
| Score | Giá trị hiệu năng được đo. |
| Error | Biên sai số thống kê được báo cáo. |
| Units | Đơn vị của score. |

Khi so sánh hai implementation:

1. Chạy trên cùng máy và cùng cấu hình JVM.
2. Dùng cùng JDK, GC, JVM flags và số thread.
3. Giữ nguyên warmup, measurement, fork và input data.
4. So sánh cùng benchmark mode và cùng đơn vị.
5. Kiểm tra error và độ biến thiên giữa các fork.
6. Chạy lại nếu kết quả thay đổi mạnh giữa các lần đo.
7. Ghi lại commit, JDK, CPU, OS và command line.

Chênh lệch nhỏ hơn mức nhiễu không chứng minh implementation này tốt hơn. Ưu tiên xem tỷ lệ cải thiện, khoảng biến thiên, allocation và tác động tới workload thật.

## 19. Kiểm soát môi trường benchmark

Hiệu năng phụ thuộc cả code lẫn môi trường thực thi.

Trước khi đo, ghi nhận:

- CPU model, số core và cấu hình hyper-threading.
- RAM và loại ổ đĩa nếu benchmark có I/O.
- OS, kernel và phiên bản JDK.
- JVM vendor, GC, heap size và các JVM flags.
- CPU frequency scaling, turbo boost và thermal throttling.
- Số process khác đang sử dụng CPU.
- Container CPU quota, memory limit và cgroup nếu có.
- Nguồn điện và power plan trên máy laptop.

Tránh chạy benchmark cùng lúc với build lớn, antivirus scan, backup hoặc workload khác gây tranh chấp CPU/I/O. Nếu đo trong container, ghi lại CPU quota và memory limit để người khác có thể tái lập điều kiện.

Không so sánh số tuyệt đối giữa hai máy khác cấu hình nếu chưa chuẩn hóa môi trường. Khi nâng JDK hoặc đổi CPU, hãy tạo baseline mới.

## 20. Các sai lầm benchmarking thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đo một lần bằng nanoTime | Bị ảnh hưởng bởi JIT, GC và scheduling. | Dùng JMH với warmup, measurement và fork. |
| Không warmup | Đo lẫn interpreter và JIT compilation. | Cấu hình warmup đủ cho workload. |
| Không fork | Benchmark trước làm nóng hoặc thay đổi profile benchmark sau. | Dùng nhiều fork JVM độc lập. |
| Không tiêu thụ kết quả | JIT loại bỏ phép tính không có side effect. | Trả về kết quả hoặc dùng Blackhole. |
| Chỉ dùng hằng số | Constant folding có thể tính trước kết quả. | Dùng state và input runtime đại diện. |
| Tạo dữ liệu trong benchmark method | Đo cả setup thay vì thao tác mục tiêu. | Dùng @Setup khi setup không thuộc workload. |
| Dùng quá nhiều thread | Tạo contention không có trong ứng dụng thật. | Chọn thread count theo workload mục tiêu. |
| Vòng lặp lớn trong method | Loop unrolling và tối ưu vòng lặp làm sai đơn vị đo. | Đo từng operation hoặc khai báo OperationsPerInvocation cho batch thật. |
| Tắt GC tùy tiện | Che giấu chi phí allocation và collection. | Đo GC bằng profiler khi phù hợp. |
| Chọn profiler rồi so với kết quả không profiler | Overhead profiler làm thay đổi score. | So sánh các lần chạy có cùng profiler hoặc đo riêng. |
| Dùng dữ liệu quá nhỏ | Cache luôn nóng, không đại diện workload. | Chọn dataset phản ánh kích thước và phân phối thực tế. |
| Chỉ nhìn score trung bình | Bỏ qua độ biến thiên và latency distribution. | Xem error, percentile và kết quả nhiều fork. |
| So sánh hai lần chạy khác môi trường | Không thể quy chênh lệch cho code. | Cố định hoặc ghi nhận môi trường và JVM flags. |

## 21. Quy trình benchmarking có thể lặp lại

Một quy trình thực tế:

1. Xác định giả thuyết cần kiểm tra, ví dụ thay đổi cấu trúc dữ liệu sẽ giảm thời gian lookup.
2. Chọn đúng phạm vi: microbenchmark, component benchmark hay load test.
3. Xây dựng baseline và implementation cần so sánh.
4. Chọn dữ liệu đầu vào có phân phối và kích thước đại diện.
5. Đưa setup ra khỏi vùng đo nếu setup không thuộc workload.
6. Chọn state scope và thread count đúng với cách chia sẻ dữ liệu.
7. Chọn benchmark mode theo metric cần đo.
8. Cấu hình warmup, measurement và fork đủ dài.
9. Chạy benchmark không profiler để lấy baseline.
10. Chạy profiler riêng khi cần giải thích nguyên nhân.
11. Lưu JSON, command line, JVM flags và thông tin máy.
12. Lặp lại phép đo và kiểm tra độ biến thiên.
13. Đánh giá cả throughput, latency, allocation và GC.
14. Xác nhận cải thiện trong benchmark rộng hơn hoặc workload gần production.
15. Chỉ kết luận khi kết quả ổn định và giải thích được nguyên nhân.

## 22. Ví dụ kết quả kiểm chứng project

Project mẫu ở trên đã được build bằng Maven với Java release 17 và JMH 1.37. JMH runner chạy trên JDK 24.0.2, liệt kê được hai benchmark:

~~~text
Benchmarks:
benchmarks.StringJoinBenchmark.plusInLoop
benchmarks.StringJoinBenchmark.stringBuilder
~~~

Một smoke run ngắn đã thực thi thành công cả hai method và kết thúc với exit code 0. Vì smoke run chỉ dùng một fork, một warmup iteration và hai measurement iterations ngắn, các score của lần chạy đó chỉ xác nhận harness hoạt động; không dùng chúng để kết luận phương thức nào nhanh hơn.

JMH 1.37 trên JDK 24.0.2 có thể in cảnh báo deprecation liên quan đến sun.misc.Unsafe trong nội bộ JMH. Trong lần kiểm chứng, cảnh báo không làm build hoặc benchmark thất bại. Khi nâng JDK/JMH, hãy kiểm tra release notes và xác nhận lại harness.

## 23. Checklist trước khi tin vào benchmark

- [ ] Đã xác định đúng thao tác và đơn vị cần đo.
- [ ] Đã chọn microbenchmark hay macrobenchmark phù hợp.
- [ ] Đã dùng JMH cho microbenchmark JVM.
- [ ] Đã kiểm tra kết quả không bị dead-code elimination.
- [ ] Đã tránh constant folding từ dữ liệu hằng số.
- [ ] Đã đặt setup ngoài vùng đo khi phù hợp.
- [ ] Đã chọn Scope.Thread, Scope.Benchmark hoặc Scope.Group đúng mục tiêu.
- [ ] Đã chọn benchmark mode phù hợp với metric.
- [ ] Đã có warmup, measurement và fork riêng biệt.
- [ ] Đã kiểm tra allocation và GC nếu workload tạo object.
- [ ] Đã chạy profiler riêng khi cần tìm nguyên nhân.
- [ ] Đã giữ ổn định thread count, JVM flags và môi trường.
- [ ] Đã xem error, độ biến thiên và kết quả nhiều fork.
- [ ] Đã lưu JSON, command line, JDK và thông tin phần cứng.
- [ ] Đã xác nhận cải thiện trên workload gần với ứng dụng thực tế.

## 24. Tài liệu tham khảo

- OpenJDK JMH project: https://github.com/openjdk/jmh
- JMH samples: https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples
- JMH Maven artifact: https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core
- Java SE 17 System.nanoTime(): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()

JMH giúp xây dựng microbenchmark có warmup, measurement, fork và cách tiêu thụ kết quả nhất quán. Kết quả chỉ có ý nghĩa khi benchmark đo đúng workload, dùng dữ liệu đại diện, kiểm soát môi trường và được lặp lại đủ nhiều để phân biệt cải thiện thật với nhiễu đo.