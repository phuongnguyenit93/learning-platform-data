# Đánh giá module tăng tốc theo dòng phiên bản và môi trường Java

Jackson Databind phải thực hiện nhiều bước khi chuyển đổi object: introspect kiểu, tìm property, tạo serializer/deserializer, đọc hoặc ghi token và truy cập getter, setter, field hay constructor. Với ứng dụng xử lý nhiều JSON, chi phí truy cập property có thể trở thành một phần đáng kể của CPU. Jackson có các module bổ sung như Afterburner và Blackbird để tối ưu một số đường truy cập này.

Tuy nhiên, không có module tăng tốc nào luôn nhanh hơn trong mọi ứng dụng. Kết quả phụ thuộc phiên bản Jackson, phiên bản Java, JIT, kiến trúc CPU, kiểu model, cấu trúc payload, tỷ lệ serialize/deserialze và cấu hình mapper. Một module có thể cải thiện throughput trên JDK này nhưng không tạo khác biệt trên JDK khác; một tối ưu có thể không phù hợp với native image, JPMS hoặc model dùng nhiều reflection/custom serializer.

Vì vậy, đánh giá module tăng tốc cần kết hợp ba việc: hiểu cơ chế và giới hạn tương thích của module, benchmark trên đúng dòng Jackson/JDK sẽ triển khai, và xác nhận kết quả chuyển đổi vẫn đúng với JSON contract của ứng dụng. Không chọn module chỉ dựa trên một con số benchmark tổng quát hoặc một bài viết cũ.

## 1. Jackson tiêu tốn thời gian ở những bước nào?

Một lần deserialize thường đi qua các bước:

```text
JSON bytes / InputStream
        |
        v
Jackson Core parser
        |
        v
Databind tìm deserializer cho target type
        |
        v
Đọc token và chuyển kiểu dữ liệu
        |
        v
Truy cập constructor / setter / field
        |
        v
Java object
```

Serialize đi theo chiều ngược lại:

```text
Java object
     |
     v
Databind tìm serializer
     |
     v
Đọc getter / field / property accessor
     |
     v
Jackson Core generator
     |
     v
JSON bytes / OutputStream
```

Trong ứng dụng thực tế, thời gian có thể đến từ nhiều nơi:

- Parse và generate token ở Jackson Core.
- Introspection, xây dựng và cache serializer/deserializer.
- Gọi getter, setter, field accessor và constructor.
- Chuyển đổi date/time, enum, number, polymorphic type hoặc custom value.
- Cấp phát object, collection, buffer và chuỗi.
- I/O, compression, network, logging và xử lý nghiệp vụ xung quanh.

Afterburner và Blackbird tập trung chủ yếu vào tối ưu một số thao tác truy cập property/creator trong Databind. Chúng không loại bỏ chi phí đọc toàn bộ bytes, network, compression, allocation của object graph hoặc business logic. Nếu ứng dụng mất phần lớn thời gian ở I/O hay database, module tăng tốc property access có thể tạo ra khác biệt rất nhỏ ở end-to-end latency.

## 2. Các module tăng tốc thường gặp

Hai module thường được nhắc đến trong Jackson 2.x là:

| Module | Cơ chế khái quát | Mục tiêu |
|---|---|---|
| `jackson-module-afterburner` | Tạo bytecode/accessor tối ưu cho một số thao tác property | Giảm chi phí gọi getter/setter/field và một số đường binding |
| `jackson-module-blackbird` | Dùng MethodHandle và cơ chế liên kết của JVM để tối ưu một số accessor | Tối ưu property access trên các JVM hiện đại, đặc biệt từ Java 9 trở lên |

Đây là các mô tả cơ chế ở mức khái quát. Chi tiết implementation, phạm vi tối ưu, hỗ trợ kiểu model và trạng thái bảo trì phải được xác nhận trong tài liệu của đúng module version đang dùng.

### 2.1. Afterburner

Afterburner là module Jackson lâu đời, được thiết kế để tăng tốc Databind bằng cách tạo bytecode truy cập trực tiếp hơn vào property thay vì đi qua một số đường reflection thông thường.

Đăng ký trong Jackson 2.x:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.module.afterburner.AfterburnerModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new AfterburnerModule());
```

Afterburner có thể hữu ích với model bean có nhiều getter/setter và đường binding tương thích với module. Tuy nhiên, bytecode generation và quyền truy cập member chịu ảnh hưởng bởi class loader, visibility và hệ thống module của JVM. Với class nằm trong named module hoặc package không mở cho truy cập phản chiếu/bytecode cần thiết, module có thể không tối ưu được một số property hoặc phát sinh cảnh báo/lỗi truy cập tùy cấu hình.

Không nên mặc định rằng thêm `--add-opens` rộng cho toàn bộ ứng dụng là cách xử lý đúng. Trước hết hãy kiểm tra lỗi cụ thể, member nào cần truy cập và tài liệu của module. Mở package chỉ nên là quyết định có phạm vi hẹp, được đánh giá theo chính sách bảo mật và runtime.

### 2.2. Blackbird

Blackbird là module tối ưu Databind được giới thiệu trong dòng Jackson 2.x hiện đại (từ 2.12). Module sử dụng MethodHandle và cơ chế liên kết của JVM để tăng tốc một số đường truy cập property. Nó được thiết kế cho Java 9 trở lên và thường là ứng viên cần benchmark trên các runtime Java hiện đại.

Đăng ký:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.module.blackbird.BlackbirdModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new BlackbirdModule());
```

Blackbird không phải một nút “tăng tốc mọi thứ”. Lợi ích phụ thuộc model, JDK, JIT và phần công việc thực sự nằm ở property access. Một số đường binding đặc biệt hoặc custom serializer/deserializer có thể không được tối ưu theo cách giống bean property thông thường.

### 2.3. Không coi Afterburner và Blackbird là hai module bắt buộc phải đăng ký cùng nhau

Hai module giải quyết vùng tối ưu gần nhau. Không nên đăng ký cả hai trên cùng mapper rồi kết luận module nào nhanh hơn hoặc mong chúng cộng dồn hiệu năng. Module có thể cùng tác động đến accessor construction và serializer/deserializer caching; thứ tự đăng ký và implementation version có thể ảnh hưởng hành vi.

Để so sánh công bằng, tạo ba mapper độc lập:

1. Baseline: không có module tăng tốc.
2. Afterburner: chỉ đăng ký Afterburner.
3. Blackbird: chỉ đăng ký Blackbird (trên JDK được module hỗ trợ).

Chỉ thử kết hợp module nếu tài liệu của version đang dùng xác nhận trường hợp đó được hỗ trợ và ứng dụng có nhu cầu cụ thể. Khi benchmark, không dùng kết quả của mapper đăng ký cả hai làm đại diện cho từng module riêng lẻ.

## 3. Đọc đúng dòng phiên bản Jackson trước khi chọn module

Jackson gồm nhiều artifact có liên quan: `jackson-core`, `jackson-databind`, `jackson-annotations` và các module mở rộng. Module tăng tốc cần tương thích với dòng release của các thành phần Databind mà ứng dụng đang chạy.

Với Jackson 2.x, nên quản lý version bằng Jackson BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.module</groupId>
        <artifactId>jackson-module-blackbird</artifactId>
    </dependency>
</dependencies>
```

Nếu thử Afterburner, thay artifact tương ứng hoặc tạo profile riêng. Không ghim một module vào version khác release train với Databind chỉ vì Maven vẫn giải quyết được dependency.

### 3.1. Kiểm tra dependency thực tế, không chỉ nhìn file build

Version trong `pom.xml` hoặc `build.gradle` có thể bị dependency bắc cầu, dependency constraints hoặc platform BOM ghi đè. Trước khi benchmark, xác nhận runtime classpath:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-module-blackbird --configuration runtimeClasspath
```

Ghi lại version của:

- `jackson-core`.
- `jackson-databind`.
- `jackson-annotations`.
- Module tăng tốc đang thử.
- Các module khác như Java Time, Kotlin, XML, CBOR hoặc YAML nếu chúng tham gia workload.

Nếu các artifact Jackson lệch version, kết quả benchmark có thể phản ánh vấn đề dependency hoặc hành vi không được hỗ trợ thay vì hiệu năng module. Cũng cần kiểm tra không có hai version cùng xuất hiện trên classpath.

### 3.2. Dòng Jackson 2.x và 3.x là hai ranh giới tương thích riêng

Không giả định một module build cho Jackson 2.x sẽ dùng nguyên dependency, package hoặc API trên Jackson 3.x. Major version có thể thay đổi baseline Java, namespace package, artifact coordinates, module availability và API builder.

Khi chuyển sang Jackson 3.x:

- Dùng BOM và hướng dẫn migration của đúng major version.
- Xác nhận module tăng tốc có artifact tương ứng và được duy trì cho dòng đó.
- Kiểm tra package import và API đăng ký module theo tài liệu version.
- Chạy lại toàn bộ benchmark trên JDK baseline của ứng dụng.
- Chạy correctness tests với model thật, đặc biệt custom serializer/deserializer và polymorphic binding.

Không copy nguyên ví dụ `com.fasterxml.jackson...` của Jackson 2.x sang major version mới mà không kiểm tra tài liệu. Tên module giống nhau không bảo đảm binary compatibility.

## 4. Ma trận đánh giá theo môi trường Java

Khả năng dùng và hiệu quả của module phụ thuộc JDK. Một ma trận khởi đầu có thể như sau:

| Môi trường | Ứng viên cần xem xét | Điểm cần kiểm tra |
|---|---|---|
| Java 8 với Jackson 2.x | Baseline và Afterburner nếu module/version hỗ trợ | Blackbird yêu cầu Java 9+; kiểm tra bytecode/access behavior và kết quả thực tế |
| Java 11 với Jackson 2.x | Baseline, Afterburner, Blackbird | MethodHandle behavior, JPMS access, warmup và throughput |
| Java 17/21 với Jackson 2.x | Baseline, Blackbird và Afterburner như một đối chứng | Strong encapsulation, class loader, cảnh báo truy cập và hiệu năng JIT |
| Java 17+ với Jackson 3.x | Baseline và module được hỗ trợ trong release train 3.x | API/package/artifact thay đổi và baseline runtime mới |
| GraalVM Native Image | Baseline native và module chỉ khi có hỗ trợ rõ ràng | Runtime code generation, reflection metadata, build-time analysis và binary size |
| Container/Serverless | Các cấu hình thực sự triển khai | CPU quota, cold start, memory limit và concurrency |

Đây là ma trận lựa chọn để thử nghiệm, không phải tuyên bố mọi tổ hợp đều được module hỗ trợ. Trước khi thêm dependency, kiểm tra README/Javadoc/release notes của artifact đúng version và chạy thử trên JDK đích.

### 4.1. Java 8

Blackbird được thiết kế cho Java 9 trở lên nên không phải lựa chọn cho runtime Java 8. Với ứng dụng còn ở Java 8, có thể benchmark Afterburner nếu phiên bản Jackson và module đang dùng hỗ trợ tổ hợp đó.

Đừng nâng module riêng lẻ vượt khỏi mức tương thích với Jackson/JDK của ứng dụng. Nếu ứng dụng vẫn cần Java 8 vì một dependency hoặc nền tảng cũ, baseline có thể là lựa chọn ổn định hơn một module tối ưu ít mang lại lợi ích.

### 4.2. Java 11, 17 và các runtime mới hơn

Trên Java 9+, module system (JPMS) và thay đổi về encapsulation có thể ảnh hưởng đến cách thư viện truy cập member. Blackbird dùng MethodHandle và cơ chế JVM hiện đại; Afterburner dùng bytecode generation. Không thể kết luận chỉ từ tên JDK rằng module nào luôn nhanh hơn.

Benchmark phải chạy trên đúng vendor, version và flags của JVM production. Ví dụ Java 17 HotSpot với G1 có thể cho kết quả khác Java 21 với ZGC hoặc một build JVM khác. Cũng cần quan sát warning/error về reflective access và package access, không bỏ qua chỉ vì benchmark vẫn chạy.

### 4.3. GraalVM Native Image và môi trường AOT

Module dựa trên runtime bytecode generation hoặc reflection động có thể không phù hợp với native image nếu không được hỗ trợ hoặc không có metadata cần thiết. Native image có mô hình build-time reachability khác JVM JIT thông thường.

Nếu ứng dụng build native:

- Kiểm tra tài liệu module về Native Image support.
- Build và chạy native executable thật; benchmark JVM mode không thay thế được.
- Kiểm tra reflection/configuration metadata và dynamic class generation.
- Đo startup time, binary size, memory footprint và throughput riêng.
- So sánh baseline không module với module trong chính native executable.

Không thêm module tăng tốc chỉ vì nó cải thiện benchmark trên HotSpot. Nếu native build không hỗ trợ hoặc cần cấu hình phức tạp không đáng giá, baseline có thể phù hợp hơn.

## 5. Vì sao cùng module cho kết quả khác nhau giữa JDK?

JVM có thể tối ưu method call, inline getter/setter, compile hot code và quản lý allocation khác nhau theo version, vendor, flags và workload. Một đường truy cập đã được JIT tối ưu tốt có thể khiến lợi ích của module nhỏ hơn dự kiến.

Các yếu tố quan trọng:

- **JIT warmup:** code chưa được compile tối ưu ở những vòng đầu.
- **Method inlining:** getter đơn giản có thể được JVM inline.
- **MethodHandle optimization:** hiệu quả phụ thuộc cách JVM liên kết và tối ưu handle.
- **Class loading:** module sinh class hoặc tạo accessor có thể làm tăng chi phí startup.
- **JPMS:** quyền truy cập package/member có thể khác giữa classpath và module path.
- **GC và allocation:** module giảm một số chi phí call không đồng nghĩa giảm số object được tạo.
- **CPU architecture:** x86-64 và ARM64 có thể có profile và hiệu năng khác.
- **Container limits:** CPU quota và throttling có thể làm kết quả dao động.

Vì vậy, hãy benchmark cùng JDK vendor/version và cùng runtime flags với production. Không lấy kết quả từ máy laptop làm kết luận cuối cùng cho container chạy trên ARM hoặc CPU quota thấp.

## 6. Xác định workload trước khi benchmark

Trước khi chọn module, cần hiểu ứng dụng thực sự làm gì với Jackson. Không benchmark một POJO nhỏ rồi suy ra toàn bộ hệ thống sẽ nhanh hơn.

Thu thập các đặc điểm:

- Tỷ lệ deserialize/serialize, ví dụ 80% read và 20% write.
- Payload trung bình và p95/p99 theo bytes.
- Số lượng property và kiểu dữ liệu.
- Tỷ lệ collection, nested object và polymorphic type.
- Số model mutable bean, record, immutable constructor và Kotlin data class.
- Tỷ lệ custom serializer/deserializer.
- Số lần dùng annotation, mix-in, views và naming strategy.
- Mapper có được chia sẻ hay tạo mới thường xuyên.
- Throughput và latency hiện tại.
- Phần CPU thực tế dành cho Jackson theo profiler.

Nếu ứng dụng bị giới hạn bởi network, database hoặc compression, tối ưu getter/setter có thể không thay đổi đáng kể request latency. Hãy dùng profiling để xác nhận Jackson là hotspot trước khi thêm module.

## 7. Thiết kế benchmark công bằng

Một benchmark có ý nghĩa cần giữ nguyên mọi yếu tố ngoài module đang so sánh:

1. Cùng JDK vendor/version và JVM flags.
2. Cùng Jackson release train và cùng model.
3. Cùng payload bytes, cùng object input và cùng feature configuration.
4. Cùng tỷ lệ serialize/deserialze và cùng số lượng property.
5. Mapper được tạo một lần trong setup, không tạo mapper cho mỗi operation.
6. Có warmup để JIT và Jackson serializer/deserializer cache ổn định.
7. Dùng nhiều fork để giảm ảnh hưởng trạng thái JVM.
8. Đo allocation/GC bên cạnh throughput hoặc latency.
9. Chạy trên môi trường gần production.
10. Lặp lại với payload và model đại diện cho ứng dụng.

Không benchmark như sau:

```java
@Benchmark
public byte[] serialize() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.writeValueAsBytes(event);
}
```

Đoạn này chủ yếu đo chi phí tạo mapper và khởi tạo cache, không phản ánh mapper được tái sử dụng trong server. Nếu startup/cold start là mục tiêu, hãy đo riêng một benchmark cold-start có tên rõ ràng.

## 8. Dùng JMH thay vì đo thời gian bằng `System.nanoTime()` đơn giản

JMH là harness benchmark cho JVM, có hỗ trợ warmup, measurement iteration, fork và cơ chế giảm một số sai lệch do compiler/JIT. Thêm dependency benchmark riêng, không đưa JMH vào runtime application artifact.

Ví dụ Maven dependency:

```xml
<dependency>
    <groupId>org.openjdk.jmh</groupId>
    <artifactId>jmh-core</artifactId>
    <version>${jmh.version}</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.openjdk.jmh</groupId>
    <artifactId>jmh-generator-annprocess</artifactId>
    <version>${jmh.version}</version>
    <scope>test</scope>
</dependency>
```

Trong dự án thật, cấu hình annotation processor và plugin chạy JMH theo hướng dẫn của JMH. Không cần đặt JMH vào code production chỉ để đo hiệu năng.

### 8.1. Một benchmark đọc JSON

Ví dụ dưới đây chạy cùng một workload với mapper baseline, Afterburner hoặc Blackbird. Chỉ chọn `blackbird` trên JDK/module version được hỗ trợ.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.module.afterburner.AfterburnerModule;
import com.fasterxml.jackson.module.blackbird.BlackbirdModule;
import org.openjdk.jmh.annotations.*;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class JacksonReadBenchmark {

    @Param({"baseline", "afterburner", "blackbird"})
    public String mode;

    private byte[] json;
    private ObjectReader reader;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        ObjectMapper mapper = switch (mode) {
            case "afterburner" -> new ObjectMapper()
                    .registerModule(new AfterburnerModule());
            case "blackbird" -> new ObjectMapper()
                    .registerModule(new BlackbirdModule());
            default -> new ObjectMapper();
        };

        json = ("""
                {
                  "id": 1001,
                  "name": "An Nguyen",
                  "active": true,
                  "score": 98.5
                }
                """).getBytes(java.nio.charset.StandardCharsets.UTF_8);

        reader = mapper.readerFor(BenchmarkUser.class);

        // Đọc trước một lần để phát hiện lỗi cấu hình và khởi tạo cache.
        reader.readValue(json);
    }

    @Benchmark
    public BenchmarkUser deserialize() throws Exception {
        return reader.readValue(json);
    }
}
```

Model:

```java
public record BenchmarkUser(
        long id,
        String name,
        boolean active,
        double score) {
}
```

Đây là mẫu cấu trúc benchmark; khi chạy thực tế, kiểm tra module có hỗ trợ model record và JDK đang dùng. Nếu muốn đo bean mutable, thêm một model có getter/setter. Không dùng một record duy nhất để kết luận cho mọi kiểu model.

### 8.2. Benchmark serialize riêng

Serialize cần một benchmark riêng với object đã tạo sẵn:

```java
@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class JacksonWriteBenchmark {

    @Param({"baseline", "afterburner", "blackbird"})
    public String mode;

    private BenchmarkUser user;
    private ObjectWriter writer;

    @Setup(Level.Trial)
    public void setup() {
        ObjectMapper mapper = switch (mode) {
            case "afterburner" -> new ObjectMapper()
                    .registerModule(new AfterburnerModule());
            case "blackbird" -> new ObjectMapper()
                    .registerModule(new BlackbirdModule());
            default -> new ObjectMapper();
        };

        user = new BenchmarkUser(1001L, "An Nguyen", true, 98.5);
        writer = mapper.writerFor(BenchmarkUser.class);
    }

    @Benchmark
    public byte[] serialize() throws Exception {
        return writer.writeValueAsBytes(user);
    }
}
```

Benchmark đọc và ghi riêng giúp xác định module có lợi ở chiều nào. Một ứng dụng read-heavy có thể có kết quả khác ứng dụng write-heavy.

### 8.3. Vì sao dùng `ObjectReader` và `ObjectWriter`?

Reader/writer được tạo trong setup để không tính chi phí tạo cấu hình ở mỗi operation. Chúng cũng thể hiện cách ứng dụng có thể tái sử dụng binding configuration.

Nếu production gọi `mapper.readValue()` trực tiếp, có thể benchmark đường đó ở một benchmark khác. Quan trọng là mỗi biến thể phải dùng cùng một API và cùng cách tái sử dụng.

## 9. Đo throughput, latency và allocation

Không chỉ xem một chỉ số:

| Chỉ số | Ý nghĩa | Cách đọc |
|---|---|---|
| Throughput (ops/s) | Số lần chuyển đổi mỗi giây | Cao hơn thường tốt hơn nếu workload giống nhau |
| Average time | Thời gian trung bình mỗi operation | Thấp hơn thường tốt hơn, nhưng dễ che tail latency |
| Sample time | Phân phối thời gian đo được | Quan sát p50/p90/p99 trong benchmark phù hợp |
| Allocation bytes/op | Số byte cấp phát cho mỗi operation | Thấp hơn có thể giảm GC pressure |
| GC count/time | Tần suất và thời gian GC | Xem ảnh hưởng đến tail latency và CPU |
| Startup/cold time | Chi phí tạo mapper và khởi tạo serializer | Quan trọng với serverless/CLI hoặc process ngắn hạn |

Chạy JMH có profiler GC:

```bash
java -jar target/benchmarks.jar JacksonReadBenchmark -prof gc
```

Đo throughput và average time ở các mode khác nhau:

```java
@BenchmarkMode({Mode.Throughput, Mode.AverageTime})
```

Nên chạy các mode riêng khi cần báo cáo rõ ràng. Đối với latency tail của hệ thống thực, JMH microbenchmark không thay thế load test end-to-end với server, network và concurrency thực tế.

## 10. Tách cold start khỏi steady state

Jackson có thể cache serializer/deserializer sau khi sử dụng. JIT cũng cần thời gian để tối ưu hot code. Do đó, kết quả sau warmup khác với lần gọi đầu.

Đo riêng hai mục tiêu:

**Cold start:**

- Tạo factory và mapper.
- Đăng ký module.
- Đọc/ghi lần đầu để xây dựng serializer/deserializer.
- Đo thời gian khởi tạo và bộ nhớ ban đầu.

**Steady state:**

- Mapper đã được cấu hình và cache đã warm.
- Chạy nhiều operation trên payload đại diện.
- Đo throughput, latency và allocation.

Module tăng tốc có thể thêm chi phí khởi tạo nhưng cải thiện steady state. Với service chạy liên tục, trade-off có thể chấp nhận được; với command-line tool chạy một lần hoặc serverless có cold start quan trọng, lợi ích cần được cân nhắc khác.

Không trộn thời gian khởi tạo mapper vào benchmark steady-state nếu production không tạo mapper mỗi request. Cũng không bỏ qua cold-start nếu process của ứng dụng thường xuyên bị tạo mới.

## 11. Benchmark nhiều loại model và payload

Một benchmark POJO nhỏ chỉ đại diện cho một lát workload. Nên xây dựng bộ dữ liệu có tính đại diện:

| Workload | Điều cần quan sát |
|---|---|
| Bean nhỏ, nhiều getter/setter | Property access có thể là phần đáng kể |
| Bean lớn với nhiều property | Số lần accessor và serializer lookup |
| Nested object | Chi phí đệ quy và nhiều type khác nhau |
| Collection lớn | Parser, allocation và collection growth |
| Immutable constructor/record | Creator path có được module tối ưu không |
| Enum/date/number | Chi phí custom scalar deserializer/formatter |
| Polymorphic type | Type resolution và subtype deserializer |
| Custom serializer/deserializer | Phần việc do code riêng đảm nhiệm |
| Payload nhỏ, tần suất cao | Overhead cố định và throughput |
| Payload lớn | Parser, memory bandwidth và allocation |

Giữ payload bytes giống nhau giữa các mapper. Nếu một module tạo JSON khác về whitespace hoặc property order nhưng vẫn hợp lệ, không dùng output bytes đó làm input benchmark của mapper khác trừ khi đây là chủ đích.

## 12. Kiểm tra correctness trước khi tin benchmark

Một module chỉ có ý nghĩa khi cải thiện hiệu năng mà không làm sai dữ liệu. Trước khi chạy benchmark, chạy cùng một bộ test trên baseline và từng mapper có module.

Các trường hợp cần kiểm tra:

- Field public, protected, package-private và private theo visibility policy.
- Getter/setter thông thường và accessor có annotation.
- Constructor creator, immutable class và record.
- `@JsonProperty`, `@JsonIgnore`, `@JsonAlias`, `@JsonFormat`.
- Mix-in và naming strategy.
- Custom serializer/deserializer và contextual deserializer.
- Polymorphic typing với subtype allowlist.
- Object identity, forward reference và graph lồng nhau nếu ứng dụng dùng.
- Java Time, enum và numeric precision.
- Null, missing property, unknown property và coercion.

Đặc biệt kiểm tra các model nằm trong named module hoặc package có visibility hạn chế. Một module tăng tốc có thể bỏ qua accessor hoặc không hoạt động với một số member tùy runtime; cần xác nhận object sau deserialize và JSON output thực tế.

Không chỉ so sánh `toString()` hoặc `equals()` nếu equality không bao phủ mọi field. Dùng assertions theo JSON tree và property quan trọng; với object identity thì dùng `assertSame()` khi cần.

## 13. Kiểm tra module trên JPMS và class loader

Ứng dụng Java hiện đại có thể chạy trên classpath hoặc module path. Quy tắc truy cập member và package khác nhau giữa unnamed module và named module.

Khi thử Afterburner/Blackbird trong JPMS:

- Kiểm tra package chứa model có được export/open phù hợp với nhu cầu thực tế không.
- Đọc warning hoặc exception về reflective access và MethodHandle access.
- Kiểm tra cả model public lẫn model package-private.
- Không thêm `--add-opens` cho toàn bộ module hệ thống nếu không cần.
- Kiểm tra ứng dụng chạy với class loader production, không chỉ test runner.
- Kiểm tra redeploy/hot reload nếu container hoặc plugin framework dùng class loader riêng.

Module tối ưu có thể cần tạo accessor/class liên kết với class loader. Ứng dụng plugin, application server hoặc môi trường hot reload có thể có lifecycle khác một executable đơn giản. Đo memory/class count và kiểm tra classloader leak nếu process liên tục load/unload module.

## 14. Kiểm tra tương thích với Java records và immutable model

Các model hiện đại thường dùng record hoặc immutable class thay cho bean mutable. Đường deserialize của chúng dựa vào constructor/creator và metadata parameter thay vì setter.

Không giả định module tối ưu accessor getter cũng tối ưu constructor creator theo cùng mức. Benchmark riêng:

- Serialize record.
- Deserialize record.
- Serialize bean getter/setter.
- Deserialize bean mutable.
- Deserialize constructor-based immutable class.

Nếu module không tạo khác biệt cho record, điều đó không có nghĩa nó không có lợi cho bean; ngược lại, kết quả tốt trên bean không chứng minh immutable model cũng nhanh hơn.

## 15. Ảnh hưởng của các module Jackson khác

Ứng dụng thường đăng ký nhiều module cùng lúc:

- `jackson-datatype-jsr310` cho Java Time.
- `jackson-module-parameter-names` cho parameter names.
- `jackson-module-kotlin` cho Kotlin.
- `jackson-dataformat-*` cho XML, CBOR, Smile, YAML, BSON, Avro.
- Custom modules của ứng dụng.

Benchmark phải giữ các module nghiệp vụ này giống nhau giữa baseline và biến thể tăng tốc. Nếu baseline thiếu Java Time module còn Blackbird mapper có module đó, kết quả không còn là phép so sánh công bằng.

Thứ tự đăng ký module và cách Jackson introspect annotation có thể ảnh hưởng một số extension point. Hãy dùng cùng thứ tự đăng ký cho cả biến thể, chỉ thêm đúng module đang đánh giá. Không thay naming strategy, feature hoặc serializer giữa các mapper.

## 16. Không phải mọi ứng dụng đều hưởng lợi

Module tăng tốc có thể không cải thiện đáng kể khi:

- Payload chủ yếu là scalar hoặc custom serializer.
- Thời gian network/database lớn hơn nhiều thời gian Databind.
- Mapper chỉ chạy một vài lần nên startup cost chiếm ưu thế.
- Model dùng constructor/record hoặc visibility path mà module không tối ưu.
- JIT của JVM đã inline các accessor đơn giản hiệu quả.
- Workload bị giới hạn bởi allocation/GC hoặc parsing chứ không phải method access.
- Module tạo thêm chi phí class generation, linkage hoặc memory.

Một benchmark chỉ ra throughput tăng nhưng allocation và tail latency xấu hơn có thể không phù hợp production. Đánh giá phải dựa trên mục tiêu vận hành chứ không chỉ một cột ops/s.

## 17. Đọc kết quả benchmark mà không kết luận quá mức

Ví dụ bảng báo cáo (không phải số liệu đo thật):

| Biến thể | JDK | Jackson line | Deserialize ops/s | Serialize ops/s | Allocation/op | Ghi chú |
|---|---|---|---:|---:|---:|---|
| Baseline | 17 | 2.x | — | — | — | Mapper không có module tăng tốc |
| Afterburner | 17 | 2.x | — | — | — | Chỉ đăng ký Afterburner |
| Blackbird | 17 | 2.x | — | — | — | Chỉ đăng ký Blackbird |

Điền số liệu từ JMH của chính ứng dụng. Không dùng dấu phần trăm cải thiện từ một bài viết khác làm kỳ vọng bắt buộc.

Khi đọc kết quả:

- So sánh cùng workload và cùng môi trường.
- Xem độ lệch giữa fork/iteration; kết quả dao động lớn cần điều tra.
- Kiểm tra confidence interval hoặc error do JMH báo.
- Xem allocation và GC, không chỉ throughput.
- Chạy đủ lâu để tránh kết luận từ warmup hoặc CPU boost ngắn hạn.
- Chạy nhiều fork và lặp lại trên máy/runner ổn định.
- Phân biệt microbenchmark với end-to-end load test.

Nếu mức cải thiện nhỏ hơn nhiễu đo hoặc không tạo khác biệt ở p95/p99 production, chi phí vận hành module có thể không đáng.

## 18. Tái hiện môi trường benchmark

Mỗi báo cáo nên ghi lại:

| Thành phần | Thông tin cần lưu |
|---|---|
| JDK | Vendor, full version, build number |
| JVM flags | Heap, GC, module opens, compiler flags |
| Jackson | Core, Databind, annotations, module versions |
| Module tăng tốc | Artifact và version chính xác |
| OS/CPU | Hệ điều hành, architecture, CPU model/core count |
| Container | CPU quota, memory limit, throttling |
| Workload | Payload size, model, read/write ratio, concurrency |
| JMH | Version, warmup, measurement, fork, mode, profiler |
| Result | Throughput, latency, allocation, GC, error |

Có thể lưu output JMH dạng JSON:

```bash
java -jar target/benchmarks.jar -rf json -rff results-jdk17-blackbird.json
```

Tên file nên thể hiện JDK, Jackson line và module để có thể so sánh qua lần nâng cấp. Không ghi đè kết quả cũ; giữ lại commit hash hoặc build identifier của source benchmark.

## 19. Đánh giá trong container và production-like environment

Máy developer thường có CPU không bị giới hạn giống container production. Trong Kubernetes/container:

- CPU quota có thể gây throttling.
- Memory limit ảnh hưởng GC và heap sizing.
- CPU architecture có thể khác máy local.
- Concurrency và request mix ảnh hưởng cache/JIT.
- Logging, compression và network có thể làm thay đổi bottleneck.

Chạy benchmark trên runner/container có cấu hình gần production. Ghi nhận CPU throttling và heap. Nếu module chỉ cải thiện trên máy không giới hạn nhưng không cải thiện trong container, không nên dùng số liệu local để quyết định triển khai.

Sau microbenchmark, chạy load test với endpoint hoặc message consumer thực tế. So sánh p50/p95/p99, CPU per request, allocation rate, GC pause và error rate. Đảm bảo load test dùng cùng payload distribution và concurrency.

## 20. Đánh giá module theo chi phí vận hành

Module tăng tốc là dependency bổ sung. Ngoài tốc độ, cần cân nhắc:

- Tương thích Jackson/JDK và lịch nâng cấp.
- Cảnh báo hoặc giới hạn truy cập member.
- Hành vi với class loader và JPMS.
- Hỗ trợ native image/AOT nếu ứng dụng dùng.
- Thời gian startup và số class được tạo.
- Memory footprint và class metadata.
- Khả năng debug stack trace và profiler.
- Tình trạng duy trì, issue và release cadence của module.
- Chi phí test trên nhiều runtime.

Nếu lợi ích chỉ vài phần trăm trong microbenchmark nhưng không cải thiện service-level objective, có thể không đáng thêm dependency và ma trận tương thích. Nếu workload Databind rất lớn và cải thiện được xác nhận trong production-like test, module có thể đáng dùng.

## 21. Cách tạo mapper baseline và mapper tăng tốc nhất quán

Một factory method giúp bảo đảm các mapper có cùng cấu hình ngoài module:

```java
public final class MapperVariants {

    public static ObjectMapper baseline() {
        return commonMapper();
    }

    public static ObjectMapper afterburner() {
        ObjectMapper mapper = commonMapper();
        mapper.registerModule(new AfterburnerModule());
        return mapper;
    }

    public static ObjectMapper blackbird() {
        ObjectMapper mapper = commonMapper();
        mapper.registerModule(new BlackbirdModule());
        return mapper;
    }

    private static ObjectMapper commonMapper() {
        ObjectMapper mapper = new ObjectMapper();
        // Đăng ký cùng JavaTimeModule, custom module và feature ở đây.
        return mapper;
    }
}
```

Đối với runtime không hỗ trợ Blackbird, không tạo class benchmark tham chiếu trực tiếp đến module nếu dependency không thể nạp trên JDK đó. Có thể tách benchmark source set/profile hoặc chỉ chạy biến thể phù hợp với JDK. Không bắt lỗi `NoClassDefFoundError` rồi tiếp tục báo cáo rằng Blackbird đã được benchmark.

Mapper phải được tạo một lần, cấu hình xong rồi tái sử dụng. Không thay module sau khi serializer/deserializer cache đã được sử dụng.

## 22. Kiểm tra hiệu năng trong ứng dụng thật

Microbenchmark giúp so sánh một thao tác nhỏ. Để đánh giá lợi ích production, cần xác định phần trăm tổng thời gian request nằm trong Jackson.

Ví dụ, nếu profiler cho thấy JSON binding chỉ chiếm 8% CPU của request, ngay cả một module làm phần binding nhanh gấp đôi cũng chỉ giảm tối đa một phần nhỏ tổng CPU theo định luật Amdahl. Nếu binding chiếm 60%, module có tiềm năng tác động lớn hơn.

Đo:

- CPU time trong parser/databind/accessor.
- Request latency p50/p95/p99.
- Throughput tại cùng CPU quota.
- Allocation rate và GC pause.
- Error rate và correctness.
- Startup/cold start nếu liên quan.

Không bật module chỉ dựa trên benchmark tổng hợp của một model. Hãy xác nhận endpoint hoặc consumer đang có bottleneck phù hợp.

## 23. Quy trình nâng cấp Jackson và đánh giá lại module

Mỗi lần nâng Jackson major/minor hoặc JDK, nên thực hiện:

1. Ghi lại baseline hiệu năng trên version đang chạy.
2. Nâng các artifact Jackson theo BOM/release train nhất quán.
3. Kiểm tra release notes, migration notes và module compatibility.
4. Build và chạy correctness tests trước khi benchmark.
5. Benchmark baseline mới không có module tăng tốc.
6. Benchmark từng module phù hợp trên JDK đích.
7. So sánh cold start, steady state, throughput, latency, allocation và GC.
8. Chạy load test production-like.
9. Kiểm tra warning, JPMS, class loader và native-image behavior nếu liên quan.
10. Chỉ giữ module khi lợi ích đo được đủ lớn và không làm tăng rủi ro vận hành quá mức.

Điểm quan trọng là baseline cũng phải được benchmark lại sau khi nâng Jackson/JDK. Bản Jackson mới hoặc JIT mới có thể đã cải thiện đường binding cơ bản; module từng có lợi ở version cũ có thể không còn tạo khác biệt.

## 24. Triển khai an toàn và khả năng quay lui

Khi quyết định thêm module vào service:

- Thêm dependency theo BOM và pin release train.
- Tạo mapper đã cấu hình ở startup.
- Chạy regression suite trên toàn bộ model quan trọng.
- Chạy canary hoặc rollout theo nhóm instance nếu hệ thống cho phép.
- Theo dõi CPU, latency, GC, startup và lỗi mapping.
- Giữ cách quay về baseline bằng cấu hình/build rõ ràng.

Không đổi module động trên mapper đang dùng chung theo từng request. Nếu cần thử nghiệm production, có thể triển khai hai nhóm instance với hai build/config khác nhau rồi so sánh metric trên cùng traffic profile.

Khi rollback, phải bảo đảm mapper baseline có cùng JSON contract và dependency set tương thích. Module tăng tốc không nên là nơi duy nhất chứa custom behavior hoặc policy nghiệp vụ.

## 25. Những lỗi thường gặp khi đánh giá module tăng tốc

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Chọn module theo bài benchmark cũ | Khác JDK, Jackson version và model | Đo trên runtime và payload thực tế |
| So sánh module trên các Jackson version khác nhau | Không cô lập được yếu tố module | Dùng cùng release train cho mọi biến thể |
| Đăng ký Afterburner và Blackbird cùng lúc | Không biết module nào tạo tác động | Benchmark từng module độc lập |
| Tạo mapper trong mỗi benchmark operation | Đo startup/cache creation thay vì steady state | Tạo mapper trong `@Setup` |
| Không có JMH warmup/fork | JIT và noise làm kết quả thiếu ổn định | Dùng warmup, measurement và nhiều fork |
| Chỉ đo một POJO nhỏ | Không đại diện workload | Dùng nhiều model/payload thật |
| Chỉ đo throughput | Bỏ qua allocation, GC và tail latency | Đo nhiều chỉ số và load test |
| Bỏ qua correctness | Có thể nhanh hơn nhưng mapping sai | Chạy cùng regression suite trên từng mapper |
| Giả định Blackbird dùng được trên Java 8 | Lỗi runtime/build hoặc không tương thích | Chọn module theo JDK baseline |
| Giả định Afterburner luôn hoạt động trên JPMS | Access warning hoặc lỗi ở package kín | Test class/module access trên runtime đích |
| Dùng kết quả HotSpot cho Native Image | Kết luận sai về runtime AOT | Benchmark native executable riêng |
| Không kiểm tra dependency tree | Module/core/databind lệch version | Dùng BOM và xác nhận runtime classpath |
| Giữ module dù không cải thiện production | Thêm dependency và ma trận bảo trì không cần thiết | Đặt ngưỡng lợi ích và quyết định có bằng chứng |

## 26. Mẫu báo cáo đánh giá

Một báo cáo ngắn nên ghi đủ thông tin để nhóm khác tái hiện:

```text
Workload:
  - Model/payload:
  - Read/write ratio:
  - Payload size distribution:

Runtime:
  - JDK vendor/version:
  - OS/architecture:
  - JVM flags/GC:
  - Container CPU/memory limit:

Jackson:
  - Core:
  - Databind:
  - Annotations:
  - Other modules:

Variants:
  - Baseline:
  - Afterburner:
  - Blackbird:

JMH:
  - Version:
  - Warmup/measurement/forks:
  - Benchmark mode/profiler:

Results:
  - Throughput:
  - Latency:
  - Allocation/op:
  - GC:
  - Startup/cold start:

Correctness:
  - Regression tests:
  - Model types covered:
  - JPMS/native checks:

Decision:
  - Chosen variant:
  - Measured benefit:
  - Compatibility constraints:
  - Rollback path:
```

Không điền số liệu dự đoán. Báo cáo chỉ nên đưa con số đã đo và ghi rõ môi trường, workload cùng mức dao động.

## 27. Checklist trước khi chọn module

- [ ] Jackson Core, Databind, Annotations và module dùng cùng release train.
- [ ] Version module được hỗ trợ bởi dòng Jackson đang triển khai.
- [ ] JDK vendor/version production nằm trong phạm vi module hỗ trợ.
- [ ] Blackbird chỉ được thử trên Java 9+.
- [ ] Afterburner được kiểm tra về bytecode/access behavior trên runtime đích.
- [ ] JPMS/class loader/native image đã được kiểm tra nếu ứng dụng sử dụng.
- [ ] Baseline, Afterburner và Blackbird dùng cùng mapper configuration ngoài module.
- [ ] Mỗi biến thể chạy bằng mapper riêng, không đăng ký chồng module.
- [ ] JMH có warmup, measurement và nhiều fork.
- [ ] Benchmark tách serialize, deserialize và cold start.
- [ ] Payload và model đại diện cho production.
- [ ] Đo throughput, latency, allocation và GC.
- [ ] Regression tests xác nhận JSON contract và object values.
- [ ] Load test xác nhận lợi ích end-to-end.
- [ ] Có quyết định giữ/bỏ module dựa trên ngưỡng lợi ích rõ ràng.

## 28. Ghi nhớ

Afterburner và Blackbird là các lựa chọn tối ưu một số đường truy cập property trong Jackson Databind. Afterburner dùng bytecode generation; Blackbird dùng MethodHandle và được thiết kế cho Java 9 trở lên. Khả năng tương thích và hiệu quả thay đổi theo Jackson release train, JDK, JPMS, class loader, model và môi trường chạy. Không có module nào mặc định nhanh nhất cho mọi ứng dụng.

Hãy đồng bộ Jackson artifacts bằng BOM, kiểm tra đúng module version, tạo mapper baseline và từng mapper tăng tốc độc lập, rồi benchmark bằng JMH trên JDK và payload đại diện. Đo cả serialize/deserialze, cold start, throughput, latency, allocation và GC; chạy correctness suite trước khi tin số liệu. Với Native Image, container hoặc runtime có module system, kiểm tra trực tiếp trên môi trường triển khai. Chỉ giữ module khi lợi ích được đo lường trong workload thật đủ lớn để bù chi phí dependency, tương thích và vận hành.
