# Đo hiệu năng bằng benchmark cho Java Pattern Matching (Java 21+)

## 1. Đặt câu hỏi đúng trước khi đo

Khi thay mã Java sử dụng `instanceof` và ép kiểu bằng type pattern hoặc record pattern, nhiều lập trình viên muốn biết: **“Pattern matching có nhanh hơn cách truyền thống không?”**. Câu trả lời đáng tin không thể suy ra chỉ từ cú pháp ngắn hơn, số dòng ít hơn hay một lần bấm chạy.

Có ít nhất ba kiểu mã cần phân biệt:

~~~java
// Cách A: kiểm tra kiểu + ép kiểu
if (value instanceof Order) {
    Order order = (Order) value;
    return 31L * order.units() + order.sku().length();
}

// Cách B: type pattern
if (value instanceof Order order) {
    return 31L * order.units() + order.sku().length();
}

// Cách C: record pattern (Java 21+)
if (value instanceof Order(var units, var sku)) {
    return 31L * units + sku.length();
}
~~~

Các đoạn trên **chỉ minh họa phần nhánh**, chưa phải một phương thức Java độc lập. Phần chạy được hoàn chỉnh ở mục 4 và mục 6.

Ba cách viết có thể dẫn tới công việc rất giống nhau sau khi `javac` và JIT tối ưu. Không có bảo đảm ngôn ngữ rằng type pattern hoặc record pattern **luôn nhanh hơn** cách dùng cast. Cần đo trên đúng JDK, workload, CPU và cấu hình của ứng dụng.

Trong chủ đề này, benchmark là một **thí nghiệm lặp lại được** nhằm trả lời câu hỏi cụ thể về thời gian, throughput hoặc tài nguyên. Với pattern matching, một thí nghiệm hợp lý là:

> Với cùng đối tượng đầu vào và cùng phép tính, chi phí phân nhánh bằng cast, type pattern và record pattern có khác biệt có thể đo và tái lập hay không?

**Microbenchmark** tập trung vào một đoạn mã rất nhỏ; **benchmark đầu-cuối** đo cả luồng nghiệp vụ như parse request, I/O, validation, database và serialization. Kết quả của microbenchmark **không tự trở thành** độ trễ của một API hay tốc độ toàn bộ ứng dụng.

## 2. Vì sao cách đo `System.nanoTime()` ngây thơ dễ sai?

Một cách phổ biến là chạy đoạn mã trong một vòng lặp rồi chia tổng thời gian cho số lần gọi:

~~~java
// Phản ví dụ minh họa; score và value chưa được khai báo ở đây.
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    score(value);
}
long nanos = System.nanoTime() - start;
System.out.println(nanos / 1_000_000.0);
~~~

Điều này chưa phải một microbenchmark đáng tin vì:

1. **Dead-code elimination:** nếu kết quả `score(value)` bị bỏ qua, trình biên dịch JIT có thể loại công việc không tạo tác động quan sát được.
2. **Constant folding:** nếu `value` là một giá trị hằng quen thuộc, kết quả có thể được tính trước.
3. **Loop optimization:** unroll, vectorization, hoisting hoặc các phép tối ưu xuyên lượt lặp có thể khiến phép đo không còn đại diện cho một invocation riêng.
4. **JIT warm-up:** lần chạy đầu có thể đo cả bytecode interpreter, biên dịch C1/C2 và quá trình thu thập profiling data.
5. **GC và nhiễu hệ thống:** thu gom rác, scheduler, thread khác, thermal throttling và CPU frequency ảnh hưởng kết quả.
6. **Branch prediction:** một triệu lần xét cùng một subtype khác hẳn tập dữ liệu hỗn hợp nhiều subtype.
7. **Overhead đồng hồ:** lời gọi đồng hồ, độ phân giải và nhiễu có thể cùng cỡ với phép toán muốn đo.

`System.nanoTime()` vẫn hữu ích cho quan sát một tác vụ đủ lớn hoặc tracing cục bộ; vấn đề là **không nên coi một con số nanos/op đơn lẻ là bằng chứng ưu thế của cú pháp**.

Với JVM microbenchmark, nên dùng **JMH (Java Microbenchmark Harness)** của OpenJDK. JMH hỗ trợ warm-up, measurement iteration, fork JVM, xử lý đầu ra và các cơ chế giúp hạn chế lỗi đo phổ biến. JMH cũng không thể biến một workload thiết kế sai thành kết luận đúng: người viết vẫn chịu trách nhiệm về tính tương đương của các phương án và tính đại diện của input.

## 3. Thiết kế thí nghiệm công bằng

Ví dụ dùng hai record:

~~~java
record Order(int units, String sku) {}
record Payment(String currency, long cents) {}
~~~

Ba phương án phải cùng tính điểm:

- Nếu `x` là `Order`: trả `31L * units + sku.length()`.
- Nếu `x` là `Payment`: trả `cents % 97 + currency.length()`.
- Nếu `x` là `null` hoặc kiểu khác: trả `0`.

Như vậy, ta kiểm tra **phương pháp truy cập và phân loại kiểu**, không vô tình so một phiên bản xử lý ít công việc hơn phiên bản khác.

| Yếu tố cần kiểm soát | Nguyên tắc |
| --- | --- |
| Logic | Các phiên bản có cùng phép tính, cùng kết quả và cùng chính sách null |
| Dữ liệu | Cùng seed, cùng phân phối kiểu và kích thước dữ liệu |
| JVM | Cùng bản JDK, JVM flags, GC và chế độ biên dịch |
| CPU/máy | Cùng phần cứng; giảm tác vụ nền, tránh throttling |
| Khởi tạo | Chuẩn bị input ngoài đoạn code đo nếu không định đo allocation |
| JIT | Warm-up đủ; đo nhiều iteration và fork |
| Kết quả | Được harness sử dụng, tránh tối ưu bỏ thao tác |
| Điều kiện | Mô tả tỉ lệ subtype, null và kiểu không khớp |
| Diễn giải | Phân biệt chi phí thao tác benchmark với độ trễ hệ thống |

**Tiền đề của workload:** `sku` và `currency` trong hai record luôn khác null. Nếu dữ liệu thực tế cho phép component null, phải thêm cách xử lý **giống nhau** cho cả ba phương án trước khi đo. Record pattern không mặc định bảo đảm mọi component tham chiếu đều khác null.

## 4. Kiểm thử tương đương trước khi đo hiệu năng

Tạo tệp **`PatternBenchmarkCheck.java`**. Đây là chương trình **chỉ dùng JDK**, không cần JMH, nhằm đối chiếu cả ba cách xử lý.

~~~java
public class PatternBenchmarkCheck {
    record Order(int units, String sku) {}
    record Payment(String currency, long cents) {}

    static long classic(Object x) {
        if (x instanceof Order) {
            Order o = (Order) x;
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment) {
            Payment p = (Payment) x;
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long typePattern(Object x) {
        if (x instanceof Order o) {
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment p) {
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long recordPattern(Object x) {
        if (x instanceof Order(var units, var sku)) {
            return 31L * units + sku.length();
        }
        if (x instanceof Payment(var currency, var cents)) {
            return cents % 97 + currency.length();
        }
        return 0;
    }

    static int passed = 0;

    static void verify(String name, Object input, long expected) {
        long a = classic(input);
        long b = typePattern(input);
        long c = recordPattern(input);

        if (a != expected || b != expected || c != expected) {
            throw new AssertionError(
                    name + ": " + a + " / " + b + " / " + c);
        }
        ++passed;
        System.out.println("PASS " + name + " -> " + expected);
    }

    public static void main(String[] args) {
        verify("order-one", new Order(1, "A"), 32);
        verify("order-zero", new Order(0, "XYZ"), 3);
        verify("order-seven", new Order(7, "AB"), 219);
        verify("order-negative", new Order(-1, "P"), -30);
        verify("payment-usd", new Payment("USD", 1234), 73);
        verify("payment-vnd-zero", new Payment("VND", 0), 3);
        verify("payment-eur-mod", new Payment("EUR", 97), 3);
        verify("payment-jpy-negative", new Payment("JPY", -1), 2);
        verify("null", null, 0);
        verify("other-string", "other", 0);
        verify("other-integer", 42, 0);
        verify("other-boolean", Boolean.TRUE, 0);

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac --release 21 PatternBenchmarkCheck.java
java PatternBenchmarkCheck
~~~

**Kết quả xác định:**

~~~text
PASS order-one -> 32
PASS order-zero -> 3
PASS order-seven -> 219
PASS order-negative -> -30
PASS payment-usd -> 73
PASS payment-vnd-zero -> 3
PASS payment-eur-mod -> 3
PASS payment-jpy-negative -> 2
PASS null -> 0
PASS other-string -> 0
PASS other-integer -> 0
PASS other-boolean -> 0
ALL PASSED: 12
~~~

`classic` dùng phép cast tường minh sau `instanceof`; `typePattern` kết hợp kiểm tra kiểu và khai báo biến; `recordPattern` phân rã record (Java 21+). Với tất cả đầu vào trong danh sách, ba cách trả về cùng kết quả.

**Đây là kiểm thử tính đúng đắn, không phải phép đo hiệu năng.** Nó cho thấy có thể so sánh công bằng trên các giá trị đã kiểm tra. Trước khi benchmark dữ liệu sản xuất, nên thêm test cho các quy tắc nghiệp vụ thực tế như chuỗi null, trường không hợp lệ và các loại đầu vào khác.

## 5. Chuẩn bị JMH với Maven

Trang dự án chính thức: [OpenJDK JMH](https://github.com/openjdk/jmh). JMH khuyến nghị dự án benchmark Maven riêng để build và chạy ổn định; cần cơ chế annotation processing để sinh mã harness, **chỉ thêm `jmh-core` là chưa đủ**.

Ví dụ cấu trúc:

~~~text
pattern-jmh/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── bench/
                └── PatternJmh.java
~~~

### Tệp `pom.xml` đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.example</groupId>
    <artifactId>pattern-jmh</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
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
                    <release>21</release>
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
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation=
                                    "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
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

Giải thích:

- `jmh-core` cung cấp annotation, runtime và công cụ thực hiện benchmark.
- `jmh-generator-annprocess` chạy khi compile, sinh các lớp phục vụ JMH.
- `maven-compiler-plugin` dùng `--release 21` để chấp nhận record pattern.
- `maven-shade-plugin` đóng gói mã và dependency thành JAR có `Main-Class` là JMH.

Ví dụ cố định **JMH 1.37** để cấu hình có thể tái lập. Khi nâng phiên bản, cập nhật `jmh-core` và `jmh-generator-annprocess` đồng bộ. Không suy ra rằng một phiên bản được ghi trong bài là phiên bản mới nhất ở mọi thời điểm.

**Điều kiện thực thi:** có JDK 21+ và Maven, cùng quyền tải dependency hoặc cache Maven tương ứng. Nếu JMH không nhận diện benchmark, kiểm tra annotation processing và danh sách benchmark sinh ra thay vì tin rằng lệnh đã đo thành công.

## 6. Tệp `PatternJmh.java` hoàn chỉnh

Lưu trong **`src/main/java/bench/PatternJmh.java`**:

~~~java
package bench;

import java.util.SplittableRandom;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class PatternJmh {
    record Order(int units, String sku) {}
    record Payment(String currency, long cents) {}

    @State(Scope.Thread)
    public static class Input {
        private static final int SIZE = 4096;

        @Param({"0", "50", "90"})
        public int orderPercent;

        private Object[] values;
        private int cursor;

        @Setup(Level.Trial)
        public void setup() {
            values = new Object[SIZE];
            cursor = 0;
            SplittableRandom random = new SplittableRandom(2026L);
            int paymentLimit =
                    orderPercent + (100 - orderPercent) / 2;

            for (int i = 0; i < values.length; i++) {
                int draw = random.nextInt(100);
                if (draw < orderPercent) {
                    values[i] = new Order(
                            1 + random.nextInt(20), "AB");
                } else if (draw < paymentLimit) {
                    values[i] = new Payment(
                            "USD", 100 + random.nextInt(1000));
                } else {
                    values[i] = (i & 1) == 0 ? null : "ignored";
                }
            }
        }

        Object next() {
            int current = cursor;
            cursor = (current + 1) & (SIZE - 1);
            return values[current];
        }
    }

    static long classicScore(Object x) {
        if (x instanceof Order) {
            Order o = (Order) x;
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment) {
            Payment p = (Payment) x;
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long typePatternScore(Object x) {
        if (x instanceof Order o) {
            return 31L * o.units() + o.sku().length();
        }
        if (x instanceof Payment p) {
            return p.cents() % 97 + p.currency().length();
        }
        return 0;
    }

    static long recordPatternScore(Object x) {
        if (x instanceof Order(var units, var sku)) {
            return 31L * units + sku.length();
        }
        if (x instanceof Payment(var currency, var cents)) {
            return cents % 97 + currency.length();
        }
        return 0;
    }

    @Benchmark
    public long classic(Input input) {
        return classicScore(input.next());
    }

    @Benchmark
    public long typePattern(Input input) {
        return typePatternScore(input.next());
    }

    @Benchmark
    public long recordPattern(Input input) {
        return recordPatternScore(input.next());
    }
}
~~~

Mỗi `@Benchmark` trả một giá trị `long`, giúp harness quan sát kết quả thay vì để phép tính bị tối ưu bỏ. Dữ liệu tạo trong `@Setup(Level.Trial)`, không tạo record mới ở đường đo.

### Vì sao dùng `Input.next()`?

`Input` giữ một mảng gồm 4096 giá trị thuộc nhiều loại. `next()` lấy **một** phần tử rồi chuyển con trỏ sang vị trí tiếp theo. `SIZE == 4096` là lũy thừa của hai, nên `(cursor + 1) & (SIZE - 1)` hoạt động như phép quay vòng chỉ số.

Việc trả mỗi lần một phần tử cho harness tránh anti-pattern tự chạy hàng triệu lần trong thân một `@Benchmark`. JMH có thể đo nhiều invocation mà không yêu cầu người viết tự chia thời gian tổng cho số vòng.

**Phạm vi phép đo:** số `ns/op` bao gồm **đọc mảng, cập nhật con trỏ và thao tác phân loại/tính điểm**. Đây là chi phí của thao tác benchmark đã định nghĩa, **không phải** riêng một opcode `instanceof`. Chi phí truy cập dữ liệu là phần chung của ba phương án; khi nó lớn so với khác biệt nhỏ của pattern, kết quả sẽ khó phân biệt.

### Tại sao cần nhiều tỉ lệ đầu vào?

`@Param({"0", "50", "90"})` tạo ba cấu hình với tỉ lệ mục tiêu `Order` xấp xỉ 0%, 50% và 90%. Phần còn lại gồm `Payment`, `null` và chuỗi không khớp.

- Tỉ lệ subtype thay đổi làm số lần thử nhánh và branch prediction thay đổi.
- Seed `2026L` cố định giúp các phép thử trong cùng cấu hình tạo lại một chuỗi dữ liệu có thể tái hiện.
- Tỉ lệ thực tế **xấp xỉ** tham số vì sinh ngẫu nhiên theo xác suất; không phải cam kết chính xác bao nhiêu phần tử của từng loại.
- Các `String` trong `Order`/`Payment` đều không null nên ba cách tính điểm có cùng hợp đồng.

`@State(Scope.Thread)` tạo state riêng theo thread, tránh thread khác cùng tăng `cursor`. Khi ứng dụng thật có concurrency, nên đo riêng tình huống nhiều thread hoặc contention; ví dụ này đo một đường phân loại mà không cố mô phỏng mọi tranh chấp trong ứng dụng.

### Ý nghĩa cấu hình JMH

- `@BenchmarkMode(Mode.AverageTime)`: đo thời gian trung bình mỗi operation.
- `@OutputTimeUnit(TimeUnit.NANOSECONDS)`: báo `ns/op`.
- `@Warmup(iterations = 3, time = 1)`: warm-up ba iteration, mỗi iteration khoảng một giây.
- `@Measurement(iterations = 5, time = 1)`: thu thập từ năm measurement iteration.
- `@Fork(2)`: chạy hai JVM fork độc lập để giảm phụ thuộc một quá trình JVM duy nhất.
- `@Param`: xuất kết quả riêng theo từng cấu hình workload.

Đây là cấu hình học tập có tính lặp lại, **không phải bảo đảm tuyệt đối rằng số liệu đã ổn định**. Với khác biệt rất nhỏ, có thể cần tăng số fork/iteration hoặc xem lại tác vụ nền, nhiệt độ CPU và độ đại diện của input.

## 7. Build, chạy và lưu kết quả

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar 'bench.PatternJmh.*'
~~~

Lệnh đầu tạo JAR benchmark có dependency. Lệnh `-l` liệt kê benchmark đã được nhận diện; hãy kiểm tra có đủ `classic`, `typePattern` và `recordPattern`. Lệnh cuối chạy tất cả ba phương án theo các `@Param` đã định nghĩa.

Chạy riêng một phép thử:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.recordPattern'
~~~

Lưu kết quả JSON:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.*' -rf json -rff result.json
~~~

`result.json` là tệp do JMH sinh ra khi chạy lệnh, không có sẵn trong tài liệu này. Dùng `java -jar target/benchmarks.jar -h` để xem đầy đủ tham số trong phiên bản JMH đang chạy.

**Không có stdout benchmark “chuẩn” theo số nanosecond**: kết quả phụ thuộc JVM, CPU, OS, bộ nhớ, tải máy, branch prediction và nhiều yếu tố khác. Vì chưa chạy workload JMH thực trên môi trường mục tiêu, bài không gán số `Score` giả và không tuyên bố một phiên bản thắng.

Đọc thêm: [JMH chính thức](https://github.com/openjdk/jmh) và [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples).

## 8. Đọc kết quả JMH đúng cách

Trong `Mode.AverageTime`, một bảng JMH thường có những cột:

| Cột | Ý nghĩa |
| --- | --- |
| `Benchmark` | Phương thức benchmark được đo |
| `(orderPercent)` | Tham số tỉ lệ đầu vào đang chạy |
| `Mode` | `avgt`: average time |
| `Cnt` | Số điểm đo thống kê sau các measurement |
| `Score` | Ước lượng trung tâm của thời gian |
| `Error` | Sai số thống kê JMH báo cáo, **không** bao phủ mọi sai lệch do thiết kế thí nghiệm |
| `Units` | `ns/op`, nanosecond trên một lần gọi theo workload đã định nghĩa |

Với `ns/op`, **càng thấp càng nhanh** trong cùng điều kiện. Phải so **cùng `orderPercent`**. Không so `classic(orderPercent=0)` với `recordPattern(orderPercent=90)` vì đó là hai workload khác nhau.

**Ví dụ hoàn toàn giả định** về cách diễn giải:

- Phương án A: `12.0 ± 0.5 ns/op`.
- Phương án B: `11.8 ± 0.6 ns/op`.

Không nên kết luận B chắc chắn nhanh hơn chỉ từ `11.8 < 12.0`. Chênh lệch 0.2 ns nhỏ so với biên dao động báo cáo; cần kiểm tra độ ổn định và chạy thêm phép đo. Các số này **không phải kết quả được đo từ mã của bài**.

Kết quả khác biệt dù rõ về thống kê vẫn cần xét **ý nghĩa thực tế**: nếu pattern dispatch chiếm một phần rất nhỏ của request và không tác động đến latency/throughput sản phẩm, việc refactor chỉ để tiết kiệm một lượng nanosecond có thể không đáng đánh đổi tính dễ đọc.

## 9. Các bẫy JVM khi benchmark pattern matching

### 9.1. JIT warm-up và compilation tier

Những lần chạy đầu có thể dùng bytecode interpreter, biên dịch ở tier khác nhau hoặc đang tích lũy profiling data. Phép đo ngắn dễ phản ánh pha khởi động thay vì đường thực thi nóng.

**Cách xử lý:** warm-up, kiểm tra xu hướng từng iteration và chạy nhiều JVM fork. Nếu sản phẩm quan tâm cold-start, thiết kế một benchmark **cold-start riêng**, không lấy dữ liệu warm-up làm số đo startup.

### 9.2. Dead-code elimination

~~~java
// Anti-pattern minh họa: không phải benchmark độc lập.
@Benchmark
public void broken() {
    score(fixedValue); // Không dùng kết quả.
}
~~~

JIT có thể bỏ công việc không có tác dụng quan sát. Trong mã JMH chính, các method trả kết quả `long` cho harness. Với nhiều kết quả, có thể dùng `Blackhole` của JMH. **Không thêm `System.out.println` trong đường đo** vì I/O sẽ lấn át phần lớn chi phí pattern.

### 9.3. Constant folding và devirtualization

Một benchmark luôn xử lý `new Order(1, "A")` có thể được tối ưu như trường hợp chỉ có một kiểu hằng. Mảng nhiều loại của ví dụ giúp tránh một workload phi thực tế, nhưng không chứng minh mọi tối ưu JIT đã giống hệ thống sản xuất.

**Cách xử lý:** chọn dữ liệu đại diện, thay tỉ lệ theo kịch bản được kiểm soát, và đối chiếu trên phiên bản JVM mục tiêu.

### 9.4. Loop hoisting và unrolling

Tự lặp hàng triệu lần rồi chia kết quả có thể làm mỗi lượt rẻ bất thường vì JIT dời phép tính ra ngoài vòng hoặc hợp nhất thao tác. OpenJDK JMH Samples có ví dụ giải thích vì sao **không nên tự thêm vòng lặp chỉ để làm đẹp số ns/op**.

**Cách xử lý:** để harness gọi một lần xử lý mỗi invocation; nếu nghiệp vụ bắt buộc đo cả batch, hãy định nghĩa rõ batch là một operation và diễn giải đúng đơn vị kết quả.

### 9.5. Branch prediction và data layout

Nếu 90% input là `Order`, CPU có thể đoán nhánh `Order` tốt hơn. Nếu tỷ lệ hỗn hợp, null xuất hiện thường xuyên hoặc đối tượng nằm rải rác trong bộ nhớ, số đo có thể khác.

**Cách xử lý:** ghi lại phân phối kiểu và kích thước tập dữ liệu. Không so hai triển khai trên hai phân phối khác nhau rồi kết luận do cú pháp.

### 9.6. Allocation và escape analysis

Record pattern dùng để **khớp và phân rã đối tượng record đã tồn tại**; cú pháp phân rã không mặc định cấp phát một bản sao record. Ngược lại, nếu tự `new Order(...)` trong phương thức đo, kết quả sẽ trộn chi phí cấp phát với dispatch.

**Cách xử lý:** tạo dữ liệu trong `@Setup` nếu muốn đo phân loại. Dùng thí nghiệm riêng nếu mục tiêu là chi phí khởi tạo đối tượng.

### 9.7. Kết quả quá nhỏ để ra quyết định

Khi chi phí chỉ vài nanosecond, nhiễu đồng hồ, CPU frequency và overhead chung của benchmark có thể chiếm phần đáng kể. Số đo phải được tái lập; cần xét **độ lớn hiệu ứng** chứ không chỉ số trung tâm.

**Cách xử lý:** đo lặp, xem sai số, thay đổi workload và kiểm tra có tác động đến ứng dụng thực hay không.

## 10. Thử nghiệm mở rộng: pattern switch và null

Java 21 cũng cho phép so sánh `if + instanceof` với `switch` dùng record pattern:

~~~java
// Phương thức minh họa trong phạm vi có record Order và Payment.
static long switchPattern(Object x) {
    return switch (x) {
        case Order(var units, var sku) ->
                31L * units + sku.length();
        case Payment(var currency, var cents) ->
                cents % 97 + currency.length();
        case null -> 0;
        default -> 0;
    };
}
~~~

Phương thức này có cùng hợp đồng trả về với ba cách viết ở trên. `case null` là quan trọng vì trong pattern switch Java 21, `default` không tự bắt selector null.

Muốn benchmark phiên bản này, hãy:

1. Thêm `switchPatternScore(Object x)` vào lớp JMH với logic như trên.
2. Thêm một `@Benchmark` trả `switchPatternScore(input.next())`.
3. Mở rộng kiểm thử tương đương trước khi đo.
4. So sánh cùng phân phối `orderPercent` và cùng thông số JMH.

Không nên mặc định `switch` chắc chắn dùng jump table hoặc luôn nhanh hơn nhiều `if`. Pattern switch có thể được biên dịch theo cách khác tùy trường hợp, JDK và JIT. Muốn giải thích chênh lệch, cần đo và nếu cần phân tích thêm bytecode/generated machine code bằng công cụ chuyên dụng.

## 11. Không dừng ở microbenchmark: allocation, GC và ứng dụng thật

Một thay đổi cú pháp có thể tạo chênh lệch nhỏ trong phép đo đơn lẻ, nhưng đường đi thực tế có thể dành nhiều thời gian cho I/O, serialization, truy vấn và networking hơn.

Một số bước mở rộng phù hợp:

- Chạy JMH với GC profiler khi muốn quan sát cấp phát/GC của workload.
- Dùng profiler CPU để xác định thời gian thực tế trong pattern dispatch so với các công việc khác.
- Đo latency p50/p95/p99 hoặc throughput của pipeline thật bằng một kịch bản tải có kiểm soát.
- Thử cả tải có concurrency nếu ứng dụng chạy nhiều thread.
- Theo dõi hiệu quả sau thay đổi trên môi trường gần với hệ thống thực.

Ví dụ:

~~~bash
java -jar target/benchmarks.jar 'bench.PatternJmh.*' -prof gc
~~~

Profiler có thể làm thay đổi phép đo, nên ghi rõ khi nào chạy profiler và đối chiếu cẩn thận với lần chạy không có profiler. Nếu workload ở đây gần như không cấp phát trong `@Benchmark` thì **không được suy rộng** rằng mọi code dùng record pattern đều không cấp phát: các record đã được tạo ở `@Setup`.

## 12. Quy trình benchmark có thể tái lập

Một quy trình thực tế:

1. **Ghi giả thuyết rõ ràng:** “Trong tải 50% Order, record pattern giảm chi phí trung bình ít nhất 5% so với cast”.
2. **Kiểm tra đúng đắn:** chạy `PatternBenchmarkCheck` và bổ sung test cho các ca biên của ứng dụng thật.
3. **Chọn workload đại diện:** tỉ lệ subtype, null, loại khác, cấu trúc dữ liệu và kích thước mảng.
4. **Dùng JMH có warm-up/fork:** tránh một lần chạy ngoài IDE bằng stopwatch thủ công.
5. **Giữ môi trường ổn định:** JVM, CPU, OS, bộ nhớ, GC, JVM flags, các tác vụ nền.
6. **Ghi lại thông tin thí nghiệm:** phiên bản JDK/JMH, source revision, tham số và kết quả JSON.
7. **Đọc cả score và error:** không chỉ nhìn thứ hạng dựa trên một số.
8. **Kiểm tra độ nhạy:** thử nhiều tỉ lệ kiểu và bộ dữ liệu phù hợp kịch bản sản xuất.
9. **Đối chiếu hiệu năng đầu-cuối:** cải thiện microbenchmark có thật sự ảnh hưởng tới người dùng?
10. **Quyết định theo cả readability:** nếu hiệu năng tương đương hoặc khác biệt không đáng kể, ưu tiên đoạn code rõ, dễ review và khó tạo lỗi hơn.

Khi công việc thật dành phần lớn thời gian chờ I/O, thay cú pháp pattern có thể không phải ưu tiên tối ưu. Benchmark giúp quyết định **nơi cần đầu tư**, không phải chứng minh trước một cách viết nhanh hơn.

## 13. Lỗi phổ biến và cách tránh

**Lỗi 1 — benchmark trên một object hằng.** JIT có thể tối ưu mạnh tình huống chỉ có một subtype. Dùng dữ liệu có tỉ lệ loại giống tải thực.

**Lỗi 2 — đo các thuật toán không tương đương.** Một phiên bản bỏ qua null hoặc một phép tính sẽ nhanh vì **làm ít việc hơn**, không phải vì pattern tốt hơn.

**Lỗi 3 — cấp phát dữ liệu trong `@Benchmark`.** Chi phí `new` và GC có thể lấn át dispatch. Dùng `@Setup` khi không đo allocation.

**Lỗi 4 — bỏ kết quả hoặc in log trong đường đo.** Bỏ kết quả có thể gây dead-code elimination; in log biến thí nghiệm thành phép đo I/O. Trả kết quả cho JMH hoặc dùng `Blackhole`.

**Lỗi 5 — tự loop nhiều triệu lần.** Phép chia thời gian vòng lặp không bảo đảm phản ánh từng thao tác; JIT có thể unroll, hoist, gộp công việc. Để JMH điều khiển invocation.

**Lỗi 6 — chỉ chạy một lần, không warm-up hoặc fork.** Noise và quá trình JIT làm số đo khó tin cậy.

**Lỗi 7 — xem `Error` là bảo đảm không có sai lệch.** Sai số thống kê không tự loại các lỗi thiết kế workload, máy quá tải hoặc phép tính bị tối ưu mất.

**Lỗi 8 — gọi `ns/op` là “thời gian request”.** Kết quả chỉ áp dụng cho operation được định nghĩa trong benchmark, không bao gồm cả API.

**Lỗi 9 — so các cấu hình input khác nhau.** Phải so cùng `orderPercent`, JVM và điều kiện môi trường.

**Lỗi 10 — tối ưu làm code khó đọc dù khác biệt không đáng kể.** Khi thời gian tương tự, readability và mức độ an toàn thường quan trọng hơn chênh lệch nhỏ chưa được tái lập.

**Lỗi 11 — xem record pattern là phép cấp phát record.** Pattern phân rã record hiện có. Allocation cần được đo và phân tích riêng.

**Lỗi 12 — quên hợp đồng null khi thêm `switch`.** Trong Java 21 pattern switch, thiếu `case null` có thể dẫn tới `NullPointerException` trong khi `instanceof` trả false. Hai phiên bản phải có cùng hành vi trước khi benchmark.

## 14. Checklist trước khi công bố kết quả

| Câu hỏi | Cần đạt |
| --- | --- |
| Các cách viết tạo cùng kết quả? | Có test so sánh, gồm null và kiểu khác |
| Input có đại diện cho ứng dụng? | Có ghi tỉ lệ subtype, dữ liệu và seed |
| Dữ liệu được tạo ngoài đường đo? | Có, trừ khi chính allocation là mục tiêu |
| Kết quả được JMH tiêu thụ? | Có |
| Đã có warm-up và nhiều fork? | Có |
| JVM/JDK, CPU, OS, flags được ghi nhận? | Có |
| So sánh cùng tham số workload? | Có |
| Score và error được xem cùng nhau? | Có |
| Có đánh giá tác động đầu-cuối? | Khi dùng kết quả để tối ưu ứng dụng |
| Không suy rộng từ microbenchmark? | Kết luận giới hạn trong điều kiện đo |

### Bài tập tự luyện

1. Thêm `switchPatternScore` vào chương trình kiểm thử, bảo đảm bốn phiên bản có cùng kết quả trên 12 ca, rồi thêm JMH benchmark tương ứng.
2. Thay `@Param({"0","50","90"})` thành một dải tỉ lệ khác và giải thích sự khác nhau theo branch prediction.
3. Tạo một workload chỉ gồm `Order`, so với workload hỗn hợp, rồi phân tích vì sao hai kết quả không nên dùng thay cho nhau.
4. Thêm profiler GC; phân biệt record được tạo ở `@Setup` với allocation trong `@Benchmark`.
5. Lấy một đường xử lý nghiệp vụ thật, so sánh phần trăm CPU dành cho phân loại pattern với phần thời gian ở parsing, I/O và truy vấn.

**Ghi nhớ:** Để đo hiệu năng pattern matching, trước hết chứng minh **các cách viết làm cùng một việc**, sau đó dùng JMH với warm-up, fork, workload đại diện và kết quả được tiêu thụ. Không kết luận cú pháp pattern luôn nhanh hơn cast hoặc pattern switch luôn nhanh hơn `if` chỉ từ trực giác hay một con số stopwatch. **Đo, kiểm tra độ ổn định, nêu giới hạn và ưu tiên tính dễ đọc khi hiệu năng không khác biệt đáng kể.**