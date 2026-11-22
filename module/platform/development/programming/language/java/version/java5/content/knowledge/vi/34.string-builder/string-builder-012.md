# Chi phí nối chuỗi trong vòng lặp và cách đo phù hợp

## Xác định đúng bài toán cần tối ưu

Giả sử bạn cần tạo một dòng báo cáo từ nhiều phần dữ liệu. Có hai tình huống khác nhau:

```java
String label = "name=" + name + ", age=" + age;
```

Đây là một biểu thức có số toán hạng cố định. Còn đoạn dưới tích lũy kết quả qua số vòng lặp phụ thuộc dữ liệu:

```java
String result = "";
for (String part : parts) {
    result = result + part;
}
```

Trong tình huống thứ hai, mỗi bước phụ thuộc toàn bộ tiền tố đã dựng. Vấn đề cần phân tích là **lượng dữ liệu phải xử lý lại qua các vòng**, không phải chỉ đếm dấu `+` trong mã nguồn.

Java hiện đại có cơ chế hỗ trợ nối chuỗi qua `StringConcatFactory` và các điểm gọi `invokedynamic`. Vì vậy, không nên giải thích mọi dấu `+` bằng một chuỗi lệnh `new StringBuilder` cố định hoặc khẳng định cứ dùng `+` là chậm. Cơ chế tối ưu một biểu thức cũng không cho phép mặc định rằng việc tích lũy qua mọi vòng lặp đã được biến thành một bộ đệm dùng chung. [Java SE 25: StringConcatFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/StringConcatFactory.html).

Bài này dùng ví dụ Java 17+ và một dự án JMH độc lập để kiểm tra cả thời gian lẫn cấp phát, không đưa ra hệ số tăng tốc áp dụng cho mọi máy.

## Mô hình chi phí của việc dựng lại tiền tố

`String` là bất biến. Khi một phép nối cần tạo kết quả mới, nó không sửa nội dung đối tượng `String` cũ. Xét mô hình đơn giản: các phần đều dài `k` và mỗi vòng tạo một chuỗi đầy đủ mới.

| Vòng | Độ dài kết quả mới |
| --- | --- |
| 1 | `k` |
| 2 | `2k` |
| 3 | `3k` |
| n | `nk` |

Tổng lượng nội dung kết quả được tạo qua các vòng là:

```text
k + 2k + ... + nk = k * n * (n + 1) / 2
```

Trong mô hình này, tổng công việc tăng theo `n²` khi `k` cố định, trong khi kết quả cuối chỉ dài `n * k`. Những tiền tố đầu bị đưa vào nhiều kết quả trung gian rồi trở thành rác khi không còn được tham chiếu.

Đây là **mô hình để dự đoán xu hướng**, không phải cam kết rằng JVM phải thực hiện đúng từng bản sao vật lý hoặc cấp phát đúng một số đối tượng nhất định. JIT có thể tối ưu, độ dài các phần có thể không đều và cách biểu diễn nội bộ có thể khác. Với dữ liệu thực, hãy xét độ dài các tiền tố và kiểm chứng bằng đo đạc.

Nếu mỗi vòng chỉ tạo một nhãn độc lập rồi xử lý ngay, không tích lũy tiền tố, mô hình trên không áp dụng nguyên vẹn:

```java
for (String name : names) {
    String label = "user=" + name;
    consume(label);
}
```

Đoạn này chỉ minh họa ranh giới bài toán; `names` và `consume` do ứng dụng cung cấp. Việc có `+` bên trong vòng lặp chưa đủ để kết luận độ phức tạp bậc hai.

## StringBuilder thay đổi cách tích lũy như thế nào?

Một builder cho cả kết quả cho phép nối thêm vào chuỗi có thể sửa đổi:

```java
StringBuilder result = new StringBuilder();
for (String part : parts) {
    result.append(part);
}
String output = result.toString();
```

Các phần mới được nối vào cùng builder. Khi thiếu dung lượng, builder phải mở rộng vùng chứa, nên không thể nói mọi lệnh `append` đều miễn phí hay luôn có chi phí cố định. Tuy nhiên, cách này tránh yêu cầu dựng lại toàn bộ `String` tiền tố ở mỗi vòng. Lần `toString()` cuối cùng cũng là một phần chi phí nếu sản phẩm đầu ra cần là `String`.

Với chiến lược tăng dung lượng phù hợp, mô hình xây kết quả bằng builder thường gần tuyến tính theo tổng độ dài đầu ra. Không thể tránh công việc xử lý nội dung cuối cùng chỉ bằng đổi API. Hãy phân biệt chi phí tăng dung lượng, chi phí nối dữ liệu và chi phí tạo kết quả cuối.

Một lỗi dễ mắc là chuyển đổi trong vòng lặp:

```java
StringBuilder result = new StringBuilder();
for (String part : parts) {
    result.append(part);
    String snapshot = result.toString();
    consume(snapshot);
}
```

Nếu ứng dụng thực sự cần mọi ảnh chụp tiền tố, tổng kích thước các chuỗi đầu ra vẫn có thể tăng theo mô hình bậc hai. Nếu chỉ cần kết quả cuối, hãy đặt `toString()` sau vòng lặp. Đoạn này là minh họa; `consume` biểu thị nơi ứng dụng dùng từng ảnh chụp.

### Dự trữ dung lượng có ích khi nào?

Nếu đã biết gần đúng độ dài kết quả, constructor `new StringBuilder(expectedLength)` có thể giảm số lần mở rộng vùng chứa. Dung lượng được tính theo đơn vị UTF-16, không theo byte của một tệp UTF-8.

Đừng dùng `setLength(expectedLength)` để dự trữ: nó tạo nội dung có độ dài đó, khiến các lần `append` bắt đầu sau phần đã tạo.

Việc biết chính xác tổng độ dài có thể cần một lượt duyệt trước. Nếu lượt duyệt ấy chỉ phục vụ tối ưu, phải tính nó vào bài toán đầu cuối. Nếu độ dài đã có sẵn từ metadata đáng tin cậy, có thể đo riêng tình huống “đã biết dung lượng”. Không cấp phát quá lớn tùy ý để đổi lấy một kết quả benchmark đẹp.

## Vì sao một lần đo nanoTime chưa đủ?

`System.nanoTime()` phù hợp để lấy chênh lệch thời gian trong cùng JVM, nhưng tự bọc hai đoạn mã rồi chạy mỗi đoạn một lần dễ tạo kết luận sai:

| Yếu tố | Ảnh hưởng đến phép so sánh |
| --- | --- |
| Nạp lớp, liên kết mã nối chuỗi, JIT | Lần đầu có thể đo cả chi phí khởi động |
| Khởi động nóng chưa đủ | Các biến thể có thể ở giai đoạn biên dịch khác nhau |
| Kết quả không được dùng | Trình tối ưu có thể loại công việc không quan sát được |
| Dữ liệu là hằng số | Một phần công việc có thể được tính trước |
| In console trong vùng đo | Đo cả I/O, khóa và định dạng của việc in |
| Thứ tự chạy cố định | Đoạn sau chịu trạng thái máy và JVM khác đoạn trước |
| Cấp phát và GC | Chỉ nhìn thời gian có thể bỏ sót áp lực bộ nhớ |
| Một kích thước dữ liệu | Khó nhận ra xu hướng tăng chi phí |

JMH cung cấp bộ khung đo trên JVM. Khi phương thức benchmark trả kết quả, JMH tiếp nhận kết quả đó để hạn chế việc loại bỏ mã không được dùng. Điều này hỗ trợ phép đo, nhưng không tự chứng minh rằng dữ liệu và phạm vi đo đã đúng với ứng dụng. [JMH: ví dụ về loại bỏ mã không được dùng](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

## Thí nghiệm JMH có thể chạy lại

Thí nghiệm sau trả lời câu hỏi cụ thể:

> Với một mảng chuỗi đã có sẵn, mất bao nhiêu thời gian và cấp phát bao nhiêu bộ nhớ để tạo một chuỗi duy nhất có dấu phẩy ngăn cách?

Ba biến thể phải tạo cùng nội dung:

- `plusInLoop`: tích lũy bằng phép nối `String`.
- `builder`: builder mới với dung lượng mặc định.
- `builderReserved`: builder mới với dung lượng biết trước.

Mỗi lượt gọi tạo builder/kết quả mới; không có bộ đệm tái sử dụng giữa các lượt. Dữ liệu mẫu và tổng độ dài được chuẩn bị ngoài vùng đo. Vì vậy, biến thể dự trữ đại diện tình huống **đã biết tổng độ dài**, không chứng minh việc tính tổng luôn miễn phí.

JMH khuyến nghị dự án benchmark độc lập và cần bộ xử lý annotation để sinh mã đo. [Hướng dẫn chính thức của JMH](https://github.com/openjdk/jmh/blob/master/README.md).

### 1. Tạo cấu trúc dự án độc lập

Dùng JDK 17 trở lên và Maven. Tạo một thư mục riêng, không đặt các tệp sau vào module ứng dụng chỉ để chạy thí nghiệm:

```text
concat-bench/
├── pom.xml
└── src/main/java/bench/ConcatBenchmark.java
```

Lưu `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>learning</groupId>
  <artifactId>concat-bench</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <jmh.version>1.37</jmh.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-core</artifactId>
      <version>${jmh.version}</version>
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
              <version>${jmh.version}</version>
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
            <goals><goal>shade</goal></goals>
            <configuration>
              <finalName>benchmarks</finalName>
              <createDependencyReducedPom>false</createDependencyReducedPom>
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
```

Các phiên bản được ghim để thí nghiệm có cấu hình cụ thể. `annotationProcessorPaths` khai báo rõ bộ sinh mã JMH; `maven.compiler.release` đặt mức Java 17 cho mã được biên dịch. Lần build đầu cần internet để tải plugin và thư viện công khai.

### 2. Viết benchmark

Lưu nội dung này vào `src/main/java/bench/ConcatBenchmark.java`:

```java
package bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ConcatBenchmark {
    @Param({"10", "100", "1000"})
    public int n;

    @Param({"ascii", "unicode"})
    public String alphabet;

    private String[] parts;
    private int totalLength;

    @Setup(Level.Trial)
    public void setup() {
        parts = new String[n];
        totalLength = Math.max(0, n - 1);
        for (int i = 0; i < n; i++) {
            parts[i] = (alphabet.equals("ascii") ? "item" : "m\u1EE5c") + i;
            totalLength = Math.addExact(totalLength, parts[i].length());
        }
        String expected = String.join(",", parts);
        if (!expected.equals(plusInLoop())
                || !expected.equals(builder())
                || !expected.equals(builderReserved())) {
            throw new IllegalStateException("Different output");
        }
    }

    @Benchmark
    public String plusInLoop() {
        String result = "";
        for (int i = 0; i < parts.length; i++) {
            result = result + (i == 0 ? "" : ",") + parts[i];
        }
        return result;
    }

    @Benchmark
    public String builder() {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) {
                result.append(',');
            }
            result.append(parts[i]);
        }
        return result.toString();
    }

    @Benchmark
    public String builderReserved() {
        StringBuilder result = new StringBuilder(totalLength);
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) {
                result.append(',');
            }
            result.append(parts[i]);
        }
        return result.toString();
    }
}
```

`setup` tạo dữ liệu lúc bắt đầu mỗi lượt thử cấu hình và xác nhận ba biến thể cho cùng kết quả. Nếu sai nội dung, thí nghiệm dừng thay vì so tốc độ của ba công việc khác nhau.

Hai nhóm dữ liệu là ASCII và chuỗi có chữ `ụ`. Việc thay nhóm dữ liệu giúp kiểm tra mức nhạy với nội dung; không nên suy rộng kết quả chỉ đo ASCII sang mọi dữ liệu Unicode. Đây vẫn là dữ liệu tổng hợp, chưa thay thế dữ liệu đại diện cho hệ thống thật.

### 3. Build, kiểm tra danh sách và chạy

Từ thư mục chứa `pom.xml`:

```shell
mvn clean package
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar "bench.ConcatBenchmark.*" -t 1 -prof gc -rf json -rff results.json
```

Lệnh cuối chạy đủ tổ hợp tham số và lưu kết quả JSON. JMH sẽ in thông tin JVM, cấu hình và số đo; thời gian cụ thể thay đổi theo môi trường, nên không có một stdout thời gian cố định để chép làm đáp án.

Nếu muốn bắt đầu từ một trường hợp hẹp rồi mới mở rộng:

```shell
java -jar target/benchmarks.jar "bench.ConcatBenchmark.*" -p n=100 -p alphabet=ascii -t 1 -prof gc
```

### 4. Hiểu cấu hình đang đo

- `@State(Scope.Thread)` cho mỗi luồng trạng thái riêng; lệnh trên chọn một luồng để tập trung vào thao tác dựng chuỗi.
- `@Param` thay kích thước và nhóm dữ liệu mà không phải viết các bản sao benchmark.
- `@Warmup` chạy ba vòng khởi động nóng, mỗi vòng một giây, trước phần lấy số liệu.
- `@Measurement` lấy số liệu qua năm vòng, mỗi vòng một giây.
- `@Fork(2)` chạy các JVM thử nghiệm riêng để giảm phụ thuộc vào một lịch sử chạy duy nhất.
- `Mode.AverageTime` và `MICROSECONDS` báo thời gian trung bình cho một lần gọi phương thức benchmark.

**Một operation trong ví dụ là tạo cả chuỗi từ `n` phần**, không phải một lệnh `append` và cũng không phải một ký tự. Khi đọc `us/op` hoặc `B/op`, phải giữ đúng đơn vị công việc này.

Đây là cấu hình khởi đầu có thể chạy lại, không phải bằng chứng rằng ba giây khởi động nóng đủ cho mọi máy. Nếu số đo còn trôi hoặc các lượt lệch lớn, cần xem dữ liệu từng vòng, thời lượng chạy và môi trường trước khi kết luận.

## Đọc kết quả mà không suy diễn quá mức

Với từng cặp `n` và `alphabet` giống nhau, so sánh:

1. **Score và Units:** thời gian trung bình cho cả kết quả. Đừng so một hàng `n=10` với hàng `n=1000` rồi coi đó là tốc độ của cùng một tác vụ.
2. **Error và độ ổn định:** không chọn phương án chỉ vì một số trung bình nhỏ hơn rất ít. Xem biến động giữa các vòng và các fork, rồi đánh giá chênh lệch có ý nghĩa thực tế hay chưa.
3. **`gc.alloc.rate.norm`, đơn vị `B/op`:** lượng cấp phát chuẩn hóa theo một lần gọi benchmark.
4. **Xu hướng khi n tăng:** đối chiếu với giả thuyết về việc dựng lại tiền tố và chi phí mở rộng builder.

Profiler GC của JMH cung cấp cả tốc độ cấp phát lẫn lượng cấp phát chuẩn hóa. Chỉ nhìn `MB/s` có thể gây nhầm: phương án chạy nhanh hơn có thể thực hiện nhiều operation hơn mỗi giây. `B/op` giúp so lượng cấp phát cho cùng một đơn vị công việc. [JMH: ví dụ profiler](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java).

`B/op` không phải lượng bộ nhớ còn sống lâu dài và không tự cho biết mức sử dụng heap cực đại. Thời gian và cấp phát cũng không phải một đại lượng: cần xem cả hai tùy mục tiêu hệ thống.

Đối với `builderReserved`, nếu ứng dụng phải tính tổng trong mỗi lần gọi, hãy thêm một biến thể đo cả lượt tính độ dài lẫn lượt dựng chuỗi. Kết quả đã loại bước đó ra ngoài vùng đo chỉ trả lời tình huống độ dài có sẵn.

Không dùng kết quả này để kết luận mọi biểu thức `"a=" + a + ",b=" + b` đều nên đổi sang builder. Muốn trả lời câu hỏi về biểu thức cố định, cần một thí nghiệm riêng tạo đúng nhãn đó.

## Từ thí nghiệm đến quyết định trong ứng dụng

Trước khi áp dụng kết quả, ghi lại JDK và nhà cung cấp, JVM flags, heap/GC, CPU, hệ điều hành, phiên bản JMH, tham số và phạm vi đo. Chạy trên cùng môi trường khi so sánh các biến thể và tránh tác vụ nền nặng, debugger hoặc in log trong vùng đo.

Nếu việc tạo dữ liệu đầu vào hoặc mã hóa đầu ra là một phần quan trọng của công việc thật, hãy có phép đo đầu cuối bao gồm chúng. Nếu hệ thống xử lý nhiều luồng, bổ sung phép đo theo tải phù hợp; một benchmark một luồng không chứng minh khả năng mở rộng của cả dịch vụ.

Với kết quả nhỏ hoặc đường chạy ít dùng, ưu tiên mã dễ hiểu. Với việc tích lũy nhiều phần để tạo một kết quả, builder là một phương án rõ ràng để tránh dựng lại tiền tố. Sau thay đổi, dùng profiler và phép đo ứng dụng để xác nhận lợi ích xuất hiện ở đúng điểm đang tốn tài nguyên.

### Thực hành

1. Giữ nguyên ba thuật toán, thay danh sách kích thước và quan sát xu hướng `us/op` cùng `B/op`.
2. Thêm biến thể tính tổng độ dài ngay trong phương thức benchmark trước khi tạo builder dự trữ. So sánh với `builderReserved` để thấy tác động của phạm vi đo.
3. Thay dữ liệu tổng hợp bằng các đoạn văn bản đại diện cho ứng dụng nhưng vẫn chuẩn bị giống nhau cho mọi biến thể.
4. Giải thích vì sao bỏ `toString()` khỏi hai phương thức builder sẽ làm phép so sánh không còn tạo cùng sản phẩm đầu ra.
5. Nêu một trường hợp vòng lặp tạo các nhãn độc lập, rồi giải thích tại sao không thể gán ngay mô hình chi phí tiền tố bậc hai cho nó.
