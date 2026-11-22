# Đo chi phí khóa trước khi chọn ReadWriteLock

## 1. Nhiều lần đọc không tự bảo đảm nhanh hơn

ReadWriteLock cho phép các reader cùng giữ khóa đọc, còn writer phải độc quyền. Khả năng đồng thời này có thể hữu ích, nhưng bản thân việc quản lý khóa đọc-ghi cũng có chi phí.

Nếu mỗi lần đọc chỉ lấy một trường trong vài thao tác, phần tiết kiệm nhờ reader chạy cùng nhau có thể nhỏ hơn chi phí xin và nhả khóa. Nếu vùng đọc dài hơn, nhiều reader thực sự có thể chồng lấp công việc và tạo lợi ích rõ hơn.

Do đó, câu hỏi cần kiểm tra là:

> Với công việc, phần cứng và mức tranh chấp của ứng dụng này, khóa đọc-ghi có giúp đạt mục tiêu tốt hơn phương án đơn giản hơn không?

Không có quy tắc “đọc chiếm 90% thì luôn dùng ReentrantReadWriteLock”.

Tài liệu [ReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html) cũng chỉ ra sự phụ thuộc vào tần suất đọc/ghi, độ dài thao tác và tranh chấp, cùng nhu cầu đo đạc thực tế.

## 2. Đo chi phí nào?

Một lần truy cập có thể gồm nhiều phần:

```text
Chờ được chạy trên CPU
    -> xin khóa
    -> có thể chờ khóa
    -> thực hiện công việc trong vùng bảo vệ
    -> nhả khóa
    -> xử lý ngoài khóa
```

Ba đại lượng không nên gộp lại:

| Đại lượng | Ý nghĩa |
|---|---|
| Chi phí xin/nhả khi ít tranh chấp | Phần quản lý khóa trong điều kiện đơn giản |
| Thời gian đợi có quyền vào | Hậu quả tranh chấp và cách điều phối |
| Thời gian xử lý toàn thao tác | Điều ứng dụng thường cần đáp ứng |

Một phép đo “nhiều thao tác mỗi giây” có thể cho thấy thông lượng tốt nhưng che việc writer chờ rất lâu. Ngược lại, đo một vòng lock/unlock không có công việc bên trong không thể dự đoán đầy đủ hiệu năng tra cứu dữ liệu thật.

Mục tiêu cần được xác định trước: tăng thông lượng, giảm độ trễ đọc, giữ độ trễ cập nhật hay hạn chế tài nguyên.

## 3. Đặt các phương án cạnh nhau với cùng yêu cầu đúng

Ít nhất cần có một phương án đối chiếu rõ:

- Khóa loại trừ như ReentrantLock hoặc synchronized.
- ReentrantReadWriteLock với read lock cho đọc và write lock cho cập nhật.
- Nếu phù hợp yêu cầu: bản chụp bất biến hoặc cấu trúc đồng thời có API thích hợp.

Không so một phương án bảo vệ đầy đủ dữ liệu với phương án bỏ khóa rồi gọi phần chênh lệch là “chi phí không cần thiết”. Phương án nhanh nhưng có data race không thay thế hợp lệ.

Hai phương án phải làm công việc tương đương:

- Cùng dữ liệu và kích thước.
- Cùng phạm vi nhất quán.
- Cùng thao tác đọc và ghi.
- Cùng điều kiện thực thi, trừ đặc tính đang chủ động khảo sát.

Nếu một phương án trả bản sao còn phương án kia trả tham chiếu nội bộ, cần xét cả sự khác nhau về cam kết dữ liệu trước khi đọc số đo.

## 4. Những yếu tố phải thay đổi trong phép đo

| Yếu tố | Vì sao ảnh hưởng kết quả? |
|---|---|
| Độ dài vùng đọc | Reader cùng vào có hữu ích hơn khi có đủ công việc |
| Độ dài vùng ghi | Writer giữ độc quyền lâu làm reader chờ |
| Số reader và writer | Quyết định mức tranh chấp, không chỉ tỷ lệ phần trăm dự kiến |
| Kích thước dữ liệu | Ảnh hưởng bộ nhớ đệm CPU, thời gian quét hoặc tra cứu |
| Fairness | Đánh đổi thứ tự chờ và thông lượng |
| Số lõi, giới hạn CPU của môi trường | Giới hạn khả năng chạy thực sự đồng thời |
| Tải nền và cơ chế tiết kiệm điện | Có thể làm phép đo dao động |
| Mô hình truy cập | Đợt ghi dồn, reader liên tục, điểm dữ liệu nóng |

Tỷ lệ **số luồng** không phải tỷ lệ **số thao tác đã hoàn tất**. Bảy reader và một writer không bảo đảm chính xác 87,5% thao tác là đọc: một loại thao tác có thể nhanh hơn nhiều loại còn lại.

Cần đọc các số đo thành phần và xem tải ấy có đại diện cho ứng dụng không.

## 5. Vì sao không chỉ tự viết một vòng lặp nanoTime?

Các lỗi phổ biến của phép đo nhỏ tự viết:

- Chưa có giai đoạn làm nóng nên trộn thời gian khởi động và tối ưu JIT.
- Không dùng kết quả, khiến một phần công việc có thể bị tối ưu bỏ.
- Dữ liệu không được chia sẻ giữa các luồng nên không có tranh chấp cần đo.
- Mọi reader và writer chạy lần lượt thay vì đồng thời.
- Print log trong mỗi lần truy cập nên chủ yếu đo I/O.
- Tạo Thread, pool hoặc dữ liệu trong vùng tính thời gian dù đó không phải thao tác cần khảo sát.
- Tự thêm vòng lặp khổng lồ rồi chia thời gian mà không xét tối ưu giữa các vòng.
- Chỉ chạy một lần và coi khác biệt nhỏ là kết luận.

System.nanoTime hữu ích cho đo khoảng thời gian, nhưng không tự tạo một thiết kế benchmark đúng. Đo trực tiếp cũng có chi phí riêng, đặc biệt với thao tác rất ngắn.

Có thể dùng **JMH** cho phép đo nhỏ trên JVM. JMH cung cấp cơ chế tổ chức lượt chạy, warmup, đo và tiến trình fork; người viết vẫn phải xây workload đúng.

Các ví dụ chính thức của OpenJDK giải thích [nhóm luồng bất đối xứng](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_15_Asymmetric.java) và [bẫy vòng lặp trong benchmark](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java).

## 6. Ví dụ JMH: cùng một phép đọc dưới hai loại khóa

Ví dụ so sánh:

- Một ReentrantLock bảo vệ cả đọc lẫn ghi.
- Một ReentrantReadWriteLock cho đọc đồng thời và ghi độc quyền.

Mỗi lần đọc quét toàn bộ mảng và trả tổng. Mỗi lần ghi tăng phần tử đầu tiên. Cả hai phương án có cùng công việc và giá trị khởi tạo.

Tham số size thay đổi lượng công việc đọc. Tham số fair áp dụng cùng lựa chọn công bằng cho hai loại khóa.

### Cấu trúc dự án riêng

Đây là ví dụ độc lập, không thêm vào mã nghiệp vụ đang chạy:

```text
read-write-lock-measurement/
├── pom.xml
└── src/main/java/demo/LockCostBenchmark.java
```

Cần JDK 17+ và Maven. Lần build đầu cần truy cập kho Maven công khai để tải phụ thuộc. Các phiên bản trong pom được ghim để tái lập cấu hình ví dụ, không phải khẳng định đó là mọi phiên bản mới nhất.

Nội dung **pom.xml**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>read-write-lock-measurement</artifactId>
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
    <dependency>
      <groupId>org.openjdk.jmh</groupId>
      <artifactId>jmh-generator-annprocess</artifactId>
      <version>${jmh.version}</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>
  <build>
    <finalName>benchmarks</finalName>
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
        <version>3.5.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
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

Nội dung **src/main/java/demo/LockCostBenchmark.java**:

```java
package demo;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import org.openjdk.jmh.annotations.*;

@State(Scope.Group)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class LockCostBenchmark {
    @Param({"16", "1024"})
    public int size;

    @Param({"false", "true"})
    public boolean fair;

    private long[] values;
    private ReentrantLock mutex;
    private ReentrantReadWriteLock readWrite;

    @Setup(Level.Trial)
    public void initialize() {
        values = new long[size];
        for (int i = 0; i < size; i++) {
            values[i] = i;
        }
        mutex = new ReentrantLock(fair);
        readWrite = new ReentrantReadWriteLock(fair);
    }

    private long scan() {
        long sum = 0;
        for (long value : values) {
            sum += value;
        }
        return sum;
    }

    @Benchmark
    @Group("mutex")
    @GroupThreads(7)
    public long mutexRead() {
        mutex.lock();
        try {
            return scan();
        } finally {
            mutex.unlock();
        }
    }

    @Benchmark
    @Group("mutex")
    @GroupThreads(1)
    public long mutexWrite() {
        mutex.lock();
        try {
            return ++values[0];
        } finally {
            mutex.unlock();
        }
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(7)
    public long sharedRead() {
        readWrite.readLock().lock();
        try {
            return scan();
        } finally {
            readWrite.readLock().unlock();
        }
    }

    @Benchmark
    @Group("readWrite")
    @GroupThreads(1)
    public long exclusiveWrite() {
        readWrite.writeLock().lock();
        try {
            return ++values[0];
        } finally {
            readWrite.writeLock().unlock();
        }
    }
}
```

### Những lựa chọn trong mã có ý nghĩa gì?

- Scope.Group làm trạng thái được chia sẻ trong cùng nhóm reader/writer. Mỗi nhóm có trạng thái riêng, tránh vô tình đo các luồng không tranh chấp.
- Group liên kết phương thức đọc và ghi thành một workload.
- GroupThreads đặt bảy luồng đọc và một luồng ghi cho mỗi nhóm.
- Mảng được tạo trong Setup, không tạo lại ở mỗi lần đo.
- Giá trị đọc/ghi được trả về để JMH tiêu thụ kết quả.
- Vòng lặp scan là công việc ứng dụng đang mô hình hóa, không phải vòng lặp thêm vào chỉ để lặp lock/unlock rồi tự chia thời gian.
- Hai phương án được khảo sát ở các nhóm benchmark tương ứng, không dùng hai khóa khác nhau cùng bảo vệ một mảng được truy cập đồng thời ngoài giao thức.

Đây là mô hình quét mảng, không phải bản sao của mọi kho cấu hình hoặc map. Phải thay bằng công việc đại diện trước khi dùng kết quả chọn kiến trúc thật.

## 7. Build và chạy

Từ thư mục chứa pom:

```shell
mvn clean package
java -jar target/benchmarks.jar "demo.LockCostBenchmark.*" -t 8 -rf json -rff results.json
```

Trong ví dụ, một nhóm có tám luồng. Dùng -t 8 để khảo sát một nhóm chia sẻ trạng thái cho mỗi trường hợp; tăng thành bội số của tám có thể tạo nhiều nhóm độc lập, không tương đương dồn mọi luồng vào cùng một đối tượng khóa.

Các annotation đặt:

- Ba lượt warmup, mỗi lượt một giây.
- Năm lượt đo, mỗi lượt một giây.
- Hai fork, chạy bằng các JVM riêng.

Đây là cấu hình khởi đầu. Thời gian đủ hay chưa phải được đánh giá qua độ ổn định và workload, không chỉ vì đã có annotation.

### Chạy kiểm tra nhanh khác phép đo dùng để kết luận

Để kiểm tra dự án build và chạy được:

```shell
java -jar target/benchmarks.jar "demo.LockCostBenchmark.*" -t 8 -wi 0 -i 1 -r 100ms -f 1 -p size=16 -p fair=false
```

Lệnh này bỏ warmup và đo rất ngắn. Nó chỉ thích hợp kiểm tra đường chạy, **không dùng số của nó để kết luận loại khóa nào nhanh hơn**.

Đầu ra JMH có thông tin JDK, tham số, lượt chạy, điểm đo và đơn vị; kết quả số phụ thuộc máy và điều kiện thực thi nên không có một stdout số cố định áp dụng cho mọi người.

Không đưa một bảng số tưởng tượng làm kết quả kỳ vọng. Hãy giữ file JSON cùng thông tin môi trường thực tế của lần đo.

## 8. Đọc kết quả mà không chọn nhầm

Ví dụ dùng Throughput với đơn vị thao tác/giây. Điểm lớn hơn nghĩa hoàn tất nhiều lần gọi benchmark hơn trong khoảng thời gian tương ứng.

Nhưng không chỉ nhìn điểm tổng của nhóm. Cần xem các kết quả thành phần cho reader và writer:

- Reader nhanh hơn nhưng writer gần như không tiến triển có đáp ứng yêu cầu cập nhật không?
- Fairness làm writer đều hơn nhưng tổng throughput giảm có phù hợp mục tiêu không?
- Mảng nhỏ có kết quả khác mảng lớn không?
- Khác biệt có lặp lại qua fork và các lần chạy không?
- Mức dao động hoặc khoảng sai số có khiến kết luận còn chưa chắc không?

Không lấy điểm tổng rồi gọi nghịch đảo là thời gian chờ của writer. Tổng thông lượng của nhóm hỗn hợp không trực tiếp cho biết phân vị độ trễ của từng thao tác.

### Đây là so sánh thao tác, không tách được một hằng số chi phí khóa

Thời gian khóa và công việc bên trong tương tác với bộ nhớ đệm, tranh chấp và lịch luồng. Không thể đơn giản trừ hai điểm throughput để nói “read lock tốn đúng X nano giây”.

Nếu cần khảo sát thành phần rất nhỏ, phải thiết kế phép đo riêng và kiểm soát các yếu tố tương ứng. Kết quả vẫn chỉ có ý nghĩa trong bối cảnh đã đo.

## 9. Đo độ trễ và tải thực bên cạnh throughput

Ứng dụng thường cần biết một cập nhật chờ lâu nhất ở mức nào hoặc reader có bị trễ khi đợt ghi tới không.

Có thể mở rộng kế hoạch đo:

1. Khảo sát chế độ thời gian của JMH phù hợp, hoặc một bài tải ứng dụng có thu nhận độ trễ.
2. Tách reader và writer trong báo cáo.
3. Đo cả lúc tải vừa phải lẫn gần bão hòa.
4. Có trường hợp ghi dồn theo đợt, không chỉ một writer chạy đều.
5. Theo dõi bộ nhớ, CPU và ảnh hưởng tới toàn bộ luồng xử lý.

Benchmark vòng kín, nơi mỗi luồng làm xong rồi mới gửi thao tác tiếp theo, không tự mô phỏng dòng yêu cầu từ người dùng vẫn tới trong lúc hệ thống chậm. Độ trễ dưới tải đầu vào thực có thể khác.

Nếu thêm đo thời gian vào mọi lần lock rất ngắn, bản thân việc đo có thể làm thay đổi kết quả. Dùng cách thu mẫu và công cụ phù hợp thay vì mặc định đặt hai lần nanoTime quanh mọi lệnh là không có chi phí.

## 10. Phải kiểm tra tính đúng trước và trong khi đo

Một phương án đọc-ghi chỉ hợp lệ khi:

- Reader không làm thay đổi dữ liệu được khóa bảo vệ.
- Writer dùng đúng write lock của cùng đối tượng.
- Không có đường truy cập ngoài giao thức.
- Không trả tham chiếu thay đổi được rồi sửa ngoài khóa.
- Nhả khóa đầy đủ dù có ngoại lệ.

Ví dụ benchmark chỉ thay đổi phần tử dưới khóa phù hợp. Nếu bỏ read lock để điểm tăng lên, đó là một workload khác với khả năng data race, không phải tối ưu tương đương.

JMH đo hiệu năng, không phải bằng chứng đầy đủ rằng chương trình đồng thời luôn đúng. Cần kiểm tra bất biến và các tình huống tương tác của thiết kế riêng.

Không để một “bài kiểm tra nhanh hơn” làm mất điều kiện nhất quán mà người dùng cần.

## 11. Những giới hạn cần ghi trong báo cáo lựa chọn

Một kết luận có ích nên gồm:

| Nội dung | Ví dụ loại thông tin cần ghi |
|---|---|
| Môi trường | Phiên bản JDK/JVM, CPU, số lõi được cấp, giới hạn container |
| Workload | Dữ liệu, vùng đọc/ghi, số luồng, fairness |
| Cấu hình đo | Warmup, measurement, fork và tham số |
| Kết quả | Throughput và độ trễ phù hợp, dao động, writer/reader riêng |
| Tính đúng | Phạm vi bảo vệ và bất biến được giữ |
| Giới hạn | Chưa mô phỏng I/O, tải đầu vào, đợt ghi hoặc phần ứng dụng nào |

Không ghi “ReadWriteLock nhanh hơn” như một tính chất tuyệt đối. Kết luận nên gắn với workload và mục tiêu: chẳng hạn phương án nào đáp ứng độ trễ writer trong khi đạt thông lượng cần thiết trên dữ liệu đã kiểm tra.

Nếu chênh lệch không có ý nghĩa thực tế, một phương án đơn giản hơn và dễ bảo trì có thể phù hợp. Nếu lợi ích rõ, vẫn cần đánh giá độ phức tạp của nâng/hạ chế độ, fairness và việc dọn khóa.

## 12. Tự kiểm tra

1. Vì sao nhiều lời gọi đọc không tự bảo đảm khóa đọc-ghi có lợi?
2. Bảy reader và một writer có nghĩa chính xác 87,5% thao tác đã hoàn tất là đọc không?
3. Scope.Thread cho mọi dữ liệu có đo được tranh chấp trên cùng trạng thái không?
4. Vì sao không nên print trong từng lần truy cập đang đo?
5. Điểm throughput tổng có cho trực tiếp p99 thời gian chờ của writer không?
6. Benchmark chạy nhanh có chứng minh dữ liệu được bảo vệ đúng không?
7. Lệnh chạy 100 ms không warmup có dùng để kết luận hiệu năng không?

**Gợi ý:** (1) Chi phí khóa có thể lấn lợi ích nếu đọc ngắn hoặc tranh chấp không phù hợp. (2) Không. (3) Không theo mô hình dữ liệu riêng từng luồng. (4) Có thể chủ yếu đo I/O và làm thay đổi lịch thực thi. (5) Không. (6) Không. (7) Không, đó chỉ là kiểm tra đường chạy.

Chọn ReadWriteLock sau khi đã xác định **điều kiện đúng, workload đại diện, mục tiêu hiệu năng và số đo có thể tái lập**, thay vì suy luận chỉ từ tỷ lệ đọc.
