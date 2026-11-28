# Cấu hình bộ lọc, ngưỡng và phạm vi thu thập để kiểm soát lượng sự kiện

## 1. Bài toán và mục tiêu

Khi điều tra hiệu năng một ứng dụng Java, bật tất cả sự kiện JFR với mức chi tiết cao có thể tạo ra recording lớn và làm tăng chi phí quan sát. Ngược lại, chỉ ghi một số event chung có thể không đủ để trả lời câu hỏi cụ thể: phương thức nào đang chậm, một method được gọi bao nhiêu lần, hay chỉ những lần gọi kéo dài mới đáng xem?

Java 25 bổ sung **JFR Method Timing & Tracing (JEP 520)**. JFR có thể dùng bytecode instrumentation để đo thời gian và ghi dấu những phương thức được chọn. Ta có thể giới hạn phạm vi bằng bộ lọc theo lớp, phương thức hoặc annotation; sau đó kiểm soát thêm bằng ngưỡng thời gian, stack trace, chu kỳ ghi và thời lượng recording.

Bài **Cấu hình bộ lọc, ngưỡng và phạm vi thu thập để kiểm soát lượng sự kiện**, thuộc chương **Đo và truy vết JFR** của lộ trình **JAVA_VERSION_JAVA25**, hướng dẫn:

1. Phân biệt lấy mẫu stack với đo thời gian/truy vết từng lần gọi bằng JEP 520.
2. Chọn giữa hai event JFR mới: **jdk.MethodTiming** và **jdk.MethodTrace**.
3. Viết filter theo class, class-method, method name hoặc annotation.
4. Dùng enabled, filter, threshold, stackTrace, throttle và period đúng mục đích.
5. Cấu hình trực tiếp qua StartFlightRecording, JFC hoặc Java Recording API.
6. Giới hạn thời gian, phạm vi method và lượng event để giảm overhead.
7. Đọc kết quả, kiểm chứng filter và phân biệt thời gian thực thi với CPU time.

**Phạm vi phiên bản:** JEP 520 đã được đưa vào Java 25. Các ví dụ sử dụng JDK 25 và không cần preview flag. Không cần cài agent bên ngoài hoặc sửa source code ứng dụng chỉ để bật MethodTiming/MethodTrace; JFR thực hiện instrumentation theo cấu hình của recording.

## 2. Vì sao phải giới hạn phạm vi thu thập?

Một dịch vụ thương mại có thể gọi hàng triệu method mỗi phút. Nếu ghi từng lần gọi trên toàn bộ ứng dụng, số event có thể tăng rất nhanh, làm file JFR lớn và khiến việc phân tích trở nên khó khăn. Thu thập quá rộng còn có thể làm thay đổi chính workload đang điều tra.

~~~mermaid
flowchart TD
    A["Câu hỏi cần điều tra"] --> B["Chọn lớp / phương thức"]
    B --> C["Chọn event: MethodTiming hoặc MethodTrace"]
    C --> D["Đặt threshold / stackTrace / throttle"]
    D --> E["Giới hạn thời gian recording"]
    E --> F["Ghi file JFR"]
    F --> G["Phân tích kết quả"]
    G --> H{"Đủ bằng chứng?"}
    H -->|Chưa| B
    H -->|Đủ| I["Kết luận và sửa nguyên nhân"]
~~~

Nên bắt đầu từ một giả thuyết có thể kiểm tra, chẳng hạn:

- Phương thức xử lý đơn hàng có thời gian wall-clock cao bất thường.
- Một repository method được gọi quá nhiều lần.
- Một method có nhiều lần thực thi vượt 20 ms.
- Một constructor hoặc static initializer làm chậm startup.
- Một số method trong package nghiệp vụ có thời gian trung bình cao.

Khi đã xác định được lớp/phương thức nghi vấn, hãy ghi đúng phạm vi đó trong một khoảng ngắn. Nếu chưa biết method nào có vấn đề, dùng **ExecutionSample** hoặc cấu hình **profile.jfc** để tìm hot stack trước; sau đó mới dùng Method Timing/Tracing để đo chi tiết một mục tiêu cụ thể.

## 3. Hai event mới của JEP 520

JEP 520 bổ sung hai event trong nhóm **Java Virtual Machine / Method Tracing**:

| Event | Dữ liệu chính | Phù hợp với câu hỏi |
| --- | --- | --- |
| **jdk.MethodTrace** | Một event cho lần gọi method được chọn, có thời điểm, duration, method, thread và stack trace. | Muốn biết từng lần gọi diễn ra khi nào, kéo dài bao lâu và được gọi từ stack nào. |
| **jdk.MethodTiming** | Thống kê theo method như số invocation, minimum, average và maximum time. | Muốn biết method nào được gọi nhiều và phân bố thời gian tổng hợp của nó. |

Hai event sử dụng bytecode instrumentation. Đây là cơ chế khác với **jdk.ExecutionSample**, vốn lấy mẫu stack tại các thời điểm:

| Tiêu chí | ExecutionSample | MethodTrace | MethodTiming |
| --- | --- | --- | --- |
| Cách thu thập | Lấy mẫu stack định kỳ. | Ghi từng invocation được chọn và đạt điều kiện. | Tổng hợp số liệu invocation của method được chọn. |
| Dữ liệu | Stack xuất hiện trong các mẫu. | Thời điểm, thời lượng, method và stack trace. | Số lần gọi, thời gian tối thiểu, trung bình, tối đa. |
| Filter method cụ thể | Không dùng filter method của JEP 520. | Có. | Có. |
| Ngưỡng duration | Không phải cơ chế chính để lọc method sample. | Có thể đặt threshold để bỏ lần gọi ngắn. | Không phải event dùng threshold theo từng invocation. |
| Dung lượng | Phụ thuộc sampling period và thời gian ghi. | Có thể tăng nhanh nếu method được gọi nhiều. | Thường gọn hơn vì ghi thống kê tổng hợp. |
| Câu hỏi điển hình | Stack nào thường xuất hiện khi ứng dụng chạy? | Lần gọi cụ thể nào chậm và được gọi từ đâu? | Method có bao nhiêu lần gọi và min/avg/max ra sao? |

**Lưu ý về thời gian:** MethodTiming và MethodTrace đo thời gian method thực thi theo đồng hồ thời gian trôi qua, bao gồm cả thời gian chờ bên trong method; đây không phải phép đo CPU time thuần túy. Nếu method chờ database hoặc network, thời lượng có thể lớn dù CPU tiêu thụ thấp.

## 4. Cơ chế lọc method của JEP 520

Hai event **jdk.MethodTrace** và **jdk.MethodTiming** có setting tên **filter**. Filter là danh sách mục tiêu được phân tách bằng dấu chấm phẩy. Java SE 25 hỗ trợ bốn dạng mục tiêu:

| Dạng filter | Ví dụ | Phạm vi |
| --- | --- | --- |
| **class** | **com.example.OrderService** | Các method thuộc lớp được nêu. |
| **class-method** | **com.example.OrderService::place** | Method có tên place trong lớp OrderService. |
| **method** | **::close** | Method có tên close, không giới hạn tên lớp trong filter. |
| **annotation** | **@com.example.Profiled** | Method được đánh dấu bằng annotation đã nêu. |

Có thể kết hợp nhiều mục tiêu bằng dấu **;**:

~~~text
com.example.OrderService::place;com.example.PricingService::calculate
~~~

Filter dùng tên lớp và tên method theo cú pháp Java; không phải regular expression và không có wildcard. Grammar của filter không bao gồm chữ ký tham số method. Nếu lớp có nhiều overload cùng tên, hãy kiểm tra kết quả ghi để xác nhận chính xác các method đã được chọn.

### 4.1. Chọn cả lớp

Nếu cần quan sát mọi method trong một lớp nhỏ, dùng tên fully qualified:

~~~text
com.example.checkout.OrderService
~~~

Cách này tiện khi chưa biết method nào trong lớp là điểm nóng. Không nên dùng một lớp quá lớn hoặc lớp framework có hàng trăm method nếu mục tiêu chỉ là đo một thao tác cụ thể.

### 4.2. Chọn một method trong lớp

~~~text
com.example.checkout.OrderService::place
~~~

Đây thường là lựa chọn phù hợp nhất cho production investigation: phạm vi rõ, dễ giải thích và ít tạo event hơn so với ghi toàn bộ lớp.

### 4.3. Chọn method theo tên

~~~text
::close
~~~

Filter này có thể khớp method close ở nhiều lớp. Chỉ dùng khi thực sự muốn so sánh một tên method trên nhiều class. Nếu ứng dụng có nhiều loại resource, nên ưu tiên class-method để tránh thu thập ngoài phạm vi.

### 4.4. Chọn method theo annotation

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Profiled {
}
~~~

Đánh dấu các method muốn quan sát:

~~~java
public class OrderService {
    @Profiled
    public Order place(OrderRequest request) {
        // Xử lý nghiệp vụ
        return new Order();
    }
}
~~~

Filter:

~~~text
@com.example.Profiled
~~~

Cách này hữu ích khi nhóm muốn đánh dấu một tập method theo quy ước kỹ thuật. Annotation chỉ là cách chọn mục tiêu thu thập; nó không tự biến method thành transaction, không tự ghi JFR event và không thay thế authorization.

### 4.5. Constructor và static initializer

Filter grammar hỗ trợ tên đặc biệt:

~~~text
com.example.OrderService::<init>
com.example.OrderService::<clinit>
~~~

**init** đại diện constructor, còn **clinit** đại diện static initializer. Có thể dùng chúng khi điều tra thời gian tạo object hoặc khởi tạo lớp. Chỉ bật trong một recording ngắn và giới hạn class cụ thể vì constructor hoặc static initializer có thể được gọi trong nhiều tình huống.

## 5. Bốn setting cơ bản và hai setting kiểm soát bổ sung

JFR cung cấp các setting phổ biến cho event. Không phải event nào cũng sử dụng mọi setting theo cùng cách; hãy xem descriptor của event hoặc tài liệu Java SE 25 trước khi áp dụng.

| Setting | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| **enabled** | Bật hoặc tắt event. | Chỉ bật event cần quan sát. |
| **filter** | Chọn class/method/annotation cho MethodTrace và MethodTiming. | Thu hẹp instrumentation vào mục tiêu. |
| **threshold** | Không ghi event duration ngắn hơn ngưỡng. | Bỏ các lần gọi quá nhanh, tập trung vào outlier. |
| **stackTrace** | Ghi stack trace tại vị trí event. | Bật khi cần biết call path; tắt nếu chỉ cần duration và muốn giảm dữ liệu. |
| **period** | Khoảng phát event định kỳ. | Chỉ dùng với event periodic; MethodTiming phát thống kê theo chunk. |
| **throttle** | Giới hạn tốc độ ghi event theo đơn vị thời gian. | Hạn chế event rate khi event hỗ trợ setting này. |

### Threshold không phải timeout

Nếu đặt threshold là **5 ms**, JFR bỏ các event có duration ngắn hơn 5 ms; nó không hủy method khi method chạy quá 5 ms, không interrupt thread và không giới hạn thời gian thực thi.

### Period không phải threshold

**period** quy định khoảng phát event định kỳ. **threshold** lọc theo thời lượng event. Không áp dụng period tùy tiện cho mọi event; ví dụ MethodTiming tổng hợp dữ liệu và phát theo chunk, trong khi MethodTrace ghi event cho invocation được chọn.

### Throttle không thay thế filter

Throttle giới hạn tốc độ event được ghi, còn filter xác định method nào được quan sát. Nếu chọn quá nhiều method rồi chỉ throttle, dữ liệu có thể bị giới hạn theo tốc độ và làm mất một phần invocation cần điều tra. Hãy lọc đúng mục tiêu trước, rồi mới dùng throttle như một lớp kiểm soát bổ sung.

## 6. Đặt threshold và stack trace cho MethodTrace

MethodTrace ghi từng lần gọi phù hợp với filter. Nếu method được gọi hàng nghìn lần mỗi giây, event có thể tăng nhanh. Một ngưỡng duration giúp tập trung vào những lần gọi chậm:

~~~text
jdk.MethodTrace#enabled=true
jdk.MethodTrace#filter=com.example.OrderService::place
jdk.MethodTrace#threshold=10ms
jdk.MethodTrace#stackTrace=true
~~~

Trong ví dụ, chỉ method place của OrderService được chọn; các lần gọi ngắn hơn 10 ms bị bỏ qua; các lần còn lại có stack trace để xác định call path.

| Mục tiêu | Threshold gợi ý để bắt đầu | Stack trace |
| --- | --- | --- |
| Tìm các invocation rất chậm | 20–50 ms | Bật |
| Tìm độ trễ vừa phải ở một method quan trọng | 5–10 ms | Bật |
| Chỉ cần event timing, đã biết caller | Theo yêu cầu, có thể thấp | Tắt nếu không cần stack |
| Kiểm tra method ít được gọi | 0 ms trong recording ngắn | Bật |

Các con số chỉ là điểm bắt đầu để thử nghiệm, không phải ngưỡng chuẩn cho mọi hệ thống. Nếu đặt ngưỡng quá cao, bạn có thể bỏ lỡ nhiều invocation chậm vừa phải nhưng xảy ra thường xuyên. Nếu đặt 0 ms cho method có tần suất rất cao, file JFR có thể tăng nhanh.

**Không áp dụng threshold như một tiêu chí đánh giá SLA cuối cùng.** Một method mất 8 ms có thể quan trọng nếu nằm trên đường request p99, trong khi method khác mất 50 ms nhưng chỉ chạy trong tác vụ nền không quan trọng. Hãy đặt threshold theo mục tiêu quan sát và đối chiếu với latency của request thực tế.

## 7. Chọn filter cho MethodTiming

MethodTiming phù hợp khi cần biết method nào có số invocation cao hoặc thời gian tối thiểu/trung bình/tối đa đáng chú ý. Ví dụ:

~~~text
jdk.MethodTiming#enabled=true
jdk.MethodTiming#filter=com.example.OrderService::place
~~~

MethodTiming tổng hợp thống kê của method được chọn và phát event theo chu kỳ chunk của recording. Dữ liệu gồm:

- **Invocations:** số lần gọi được thống kê.
- **Minimum Time:** thời gian nhỏ nhất được quan sát.
- **Average Time:** thời gian trung bình.
- **Maximum Time:** thời gian lớn nhất.

Các thời gian là giá trị xấp xỉ theo clock/timing implementation của JVM. Ở độ phân giải clock thấp hoặc số lần gọi quá ít, một số trường thời gian có thể không có giá trị đáng tin cậy. Không suy luận quá mức từ một mẫu nhỏ.

**MethodTiming không cung cấp stack trace cho từng invocation.** Nếu average hoặc maximum cao và bạn cần biết call path của lần gọi cụ thể, hãy thực hiện recording thứ hai bằng MethodTrace với filter hẹp và threshold phù hợp.

## 8. Bắt đầu MethodTrace qua command line

Ví dụ ghi các invocation của một method trong 30 giây:

~~~bash
java -XX:StartFlightRecording:filename=method-trace.jfr,duration=30s,settings=profile,jdk.MethodTrace#enabled=true,jdk.MethodTrace#filter=com.example.OrderService::place,jdk.MethodTrace#threshold=5ms,jdk.MethodTrace#stackTrace=true -jar app.jar
~~~

Trong lệnh:

- **filename** đặt tên file recording.
- **duration** giới hạn khoảng ghi.
- **settings=profile** dùng cấu hình profiling có sẵn.
- **jdk.MethodTrace#filter** giới hạn method cần theo dõi.
- **threshold** loại các invocation ngắn hơn 5 ms.
- **stackTrace=true** giữ stack trace của invocation được ghi.

Sau khi recording hoàn tất:

~~~bash
jfr summary method-trace.jfr
jfr view jdk.MethodTrace method-trace.jfr
jfr print --events jdk.MethodTrace --stack-depth 20 method-trace.jfr
~~~

Nếu chạy ứng dụng bằng classpath thay vì JAR:

~~~bash
java -XX:StartFlightRecording:filename=method-trace.jfr,duration=30s,settings=profile,jdk.MethodTrace#filter=com.example.OrderService::place,jdk.MethodTrace#threshold=5ms -cp app.jar com.example.Main
~~~

Thay tên class, JAR, filter và payload theo dự án. Đừng đưa dữ liệu khách hàng hoặc secret vào command line.

## 9. Bắt đầu MethodTiming qua command line

Để ghi thống kê cho method place:

~~~bash
java -XX:StartFlightRecording:filename=method-timing.jfr,duration=60s,settings=profile,jdk.MethodTiming#enabled=true,jdk.MethodTiming#filter=com.example.OrderService::place -jar app.jar
~~~

Xem kết quả tổng hợp:

~~~bash
jfr summary method-timing.jfr
jfr view method-timing method-timing.jfr
jfr print --events jdk.MethodTiming method-timing.jfr
~~~

Kết quả có thể giúp trả lời:

- Method được gọi bao nhiêu lần trong khoảng ghi?
- Thời gian trung bình có cao hơn kỳ vọng không?
- Có một số lần gọi rất chậm làm maximum tăng mạnh không?
- Nên tiếp tục truy vết method này bằng MethodTrace hay điều tra dependency mà method gọi?

**MethodTiming ghi thống kê theo chunk**, vì vậy khoảng thời gian ghi quá ngắn hoặc workload gọi method quá ít có thể tạo số liệu không đủ ý nghĩa. Hãy chạy đủ số request đại diện và đọc thời điểm/period của recording khi diễn giải.

## 10. Kết hợp nhiều method và nhiều event

Có thể đưa nhiều mục tiêu vào một filter bằng dấu chấm phẩy:

~~~bash
java -XX:StartFlightRecording:filename=checkout-trace.jfr,duration=45s,settings=profile,jdk.MethodTrace#enabled=true,jdk.MethodTrace#filter="com.example.OrderService::place;com.example.PricingService::calculate;com.example.InventoryService::reserve",jdk.MethodTrace#threshold=10ms,jdk.MethodTrace#stackTrace=true -jar app.jar
~~~

Filter chọn ba method trên cùng một recording. Cách này hữu ích khi muốn theo dõi một luồng nghiệp vụ qua các tầng service.

Trong shell, dấu chấm phẩy có ý nghĩa đặc biệt; hãy đặt toàn bộ giá trị filter trong dấu nháy để shell truyền nó thành một argument. Cú pháp quoting có thể khác giữa Bash, PowerShell và CI YAML; kiểm tra command thực tế nếu filter bị tách thành nhiều lệnh.

Có thể ghi thêm event khác để đặt method timing vào bối cảnh:

~~~bash
java -XX:StartFlightRecording:filename=checkout-investigation.jfr,duration=60s,settings=profile,jdk.MethodTiming#filter=com.example.OrderService::place,jdk.ExecutionSample#enabled=true,jdk.GarbageCollection#enabled=true,jdk.ThreadPark#enabled=true -jar app.jar
~~~

MethodTiming cho số liệu tổng hợp, ExecutionSample cho hot stack, còn GC và ThreadPark giúp đối chiếu method timing với hoạt động JVM. Đừng bật mọi event cùng lúc; chỉ thêm event trả lời câu hỏi điều tra.

## 11. Tạo custom JFC để tái sử dụng filter

Khi nhóm thường xuyên điều tra cùng một nhóm method, nên lưu cấu hình vào file **.jfc** thay vì lặp lại command line dài.

Tạo cấu hình MethodTrace dựa trên profile:

~~~bash
jfr configure --input profile.jfc --output checkout-trace.jfc jdk.MethodTrace#enabled=true jdk.MethodTrace#filter=com.example.OrderService::place jdk.MethodTrace#threshold=5ms jdk.MethodTrace#stackTrace=true
~~~

Tạo cấu hình MethodTiming:

~~~bash
jfr configure --input profile.jfc --output checkout-timing.jfc jdk.MethodTiming#enabled=true jdk.MethodTiming#filter=com.example.OrderService::place
~~~

Sau đó chạy:

~~~bash
java -XX:StartFlightRecording:filename=checkout-trace.jfr,duration=30s,settings=checkout-trace.jfc -jar app.jar
java -XX:StartFlightRecording:filename=checkout-timing.jfr,duration=60s,settings=checkout-timing.jfc -jar app.jar
~~~

Kiểm tra cấu hình:

~~~bash
jfr configure --input checkout-trace.jfc --output checkout-trace-verified.jfc --verbose
jfr help configure
~~~

Không sửa trực tiếp default.jfc hoặc profile.jfc trong thư mục JDK. Hãy tạo file riêng, đặt tên theo mục tiêu, lưu trong version control và ghi rõ owner, thời gian sử dụng dự kiến, method được chọn và lý do chọn threshold.

### 11.1. Filter nhiều mục tiêu trong JFC

Nếu cần nhiều method, đặt giá trị filter thành chuỗi có dấu chấm phẩy:

~~~bash
jfr configure --input profile.jfc --output order-flow.jfc "jdk.MethodTrace#filter=com.example.OrderService::place;com.example.PricingService::calculate;com.example.InventoryService::reserve" jdk.MethodTrace#threshold=10ms
~~~

Giữ dấu nháy bao quanh toàn bộ argument filter để tránh shell hiểu dấu chấm phẩy là dấu phân tách lệnh.

## 12. Cấu hình bằng Java Recording API

Nếu muốn tạo recording trong một test harness hoặc công cụ nội bộ, có thể cấu hình event bằng API:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public final class MethodTraceRecording {

    public static void main(String[] args) throws Exception {
        Configuration profile = Configuration.getConfiguration("profile");

        try (Recording recording = new Recording(profile)) {
            recording.setName("order-method-trace");
            recording.enable("jdk.MethodTrace")
                    .with("filter", "com.example.OrderService::place")
                    .withThreshold(Duration.ofMillis(5))
                    .with("stackTrace", "true");

            recording.start();
            runRepresentativeWorkload();
            recording.stop();
            recording.dump(Path.of("order-method-trace.jfr"));
        }
    }

    private static void runRepresentativeWorkload() {
        // Gọi workload kiểm thử của ứng dụng.
    }
}
~~~

Để dùng MethodTiming, thay event được enable:

~~~java
recording.enable("jdk.MethodTiming")
        .with("filter", "com.example.OrderService::place");
~~~

MethodTiming tổng hợp số liệu theo chunk, nên không đặt threshold invocation giống MethodTrace. Nếu muốn cấu hình đồng thời cả hai event, enable chúng riêng với filter tương ứng. Trong module system, module chứa code cần khai báo **requires jdk.jfr;**.

## 13. Phân biệt filter lúc ghi và filter lúc đọc

Đây là điểm quan trọng để kiểm soát overhead:

| Thời điểm | Cách lọc | Tác dụng |
| --- | --- | --- |
| **Trước/khi ghi event** | JFC hoặc event setting như MethodTrace filter, threshold, throttle. | Giảm số method được instrument hoặc số event được ghi. |
| **Sau khi ghi** | jfr print --events, --categories, --stack-depth; JMC filter. | Giảm lượng dữ liệu hiển thị/phân tích, không thu hồi overhead đã phát sinh trong recording. |
| **Ở tầng ứng dụng** | Custom event chỉ phát khi điều kiện nghiệp vụ đúng. | Hạn chế event từ code ứng dụng theo điều kiện đã thiết kế. |

Ví dụ:

~~~bash
# Lọc event sau khi đã có file recording
jfr print --events jdk.MethodTrace --stack-depth 15 method-trace.jfr
~~~

Lệnh này chỉ chọn event để in ra. Nếu recording ban đầu đã instrument và ghi quá nhiều method, việc lọc sau đó không làm giảm chi phí đã xảy ra. Muốn giảm overhead, phải cấu hình filter và phạm vi ngay khi recording bắt đầu.

## 14. Cách chọn filter, threshold và thời lượng

Một quy trình thực tế có thể tiến hành theo từng vòng:

1. **Tìm vùng nghi vấn:** dùng profile recording hoặc metric để xác định lớp/service có khả năng gây chậm.
2. **Chọn một vài method:** ưu tiên class-method cụ thể; tránh lọc cả package rộng nếu chưa cần.
3. **Chọn event:** MethodTiming để xem số liệu tổng hợp; MethodTrace để xem từng invocation.
4. **Đặt threshold:** chọn ngưỡng thấp hơn mức latency đang điều tra nhưng đủ cao để loại các lần gọi không đáng quan tâm.
5. **Quyết định stack trace:** bật nếu cần caller; tắt khi đã biết call path và chỉ cần thời lượng.
6. **Giới hạn recording:** đặt duration, chạy một workload đại diện, dừng sau khi có dữ liệu.
7. **Đọc kết quả:** xem invocation count, min/avg/max hoặc từng trace; đối chiếu với request latency và các event JVM khác.
8. **Thu hẹp hoặc mở rộng có kiểm soát:** nếu chưa đủ bằng chứng, thêm method liên quan hoặc điều chỉnh threshold trong recording tiếp theo.

### Ma trận lựa chọn nhanh

| Câu hỏi | Event và cấu hình nên bắt đầu |
| --- | --- |
| Method nào trong service có thời gian trung bình cao? | MethodTiming, filter theo class hoặc method. |
| Method được gọi bao nhiêu lần? | MethodTiming. |
| Lần gọi cụ thể nào vượt 20 ms? | MethodTrace, filter hẹp, threshold 20 ms. |
| Ai gọi method chậm? | MethodTrace với stackTrace=true. |
| Constructor nào làm startup chậm? | MethodTiming hoặc MethodTrace lọc constructor. |
| Một nhóm method theo annotation nào đang chậm? | Filter annotation, sau đó xem MethodTiming/MethodTrace. |
| Ứng dụng chậm nhưng chưa biết method? | ExecutionSample/profile recording trước, rồi chọn method. |
| Method chậm do CPU hay do chờ I/O? | Kết hợp JFR method timing với ExecutionSample, socket/file events và thread states. |

**Không nhầm thời gian method với CPU time:** MethodTiming bao gồm thời gian method bị chặn/chờ. Nếu một method chờ database 200 ms, MethodTiming có thể cho thấy thời lượng lớn nhưng không chứng minh CPU dùng 200 ms. Hãy đối chiếu với ExecutionSample hoặc CPU-time profiling phù hợp nền tảng.

## 15. Overhead và các giới hạn cần biết

JEP 520 dùng bytecode instrumentation để đo/truy vết method được chọn. Vì vậy chi phí phụ thuộc vào:

- Số lượng method trong filter.
- Tần suất gọi của method.
- Số event được ghi bởi MethodTrace.
- Threshold và throttle.
- Việc ghi stack trace.
- Thời lượng recording và kích thước buffer/disk.

### Nguyên tắc giảm overhead

- Bắt đầu bằng MethodTiming nếu chỉ cần số liệu tổng hợp.
- Dùng MethodTrace cho một vài method cụ thể và một khoảng ngắn.
- Chọn threshold theo mục tiêu điều tra; không mặc định 0 ms trên method tần suất rất cao.
- Chỉ bật stackTrace khi cần call path.
- Không instrument toàn bộ thư viện/framework nếu chưa có lý do.
- Dùng duration và maxsize/maxage phù hợp cho recording.
- Đo lại khi không bật method tracing để ước lượng phần overhead của cấu hình.

### Giới hạn khi diễn giải

1. MethodTiming cung cấp thời gian xấp xỉ và thống kê theo chunk, không phải phép đo microbenchmark chính xác.
2. MethodTrace có thể tạo nhiều event nếu method được gọi thường xuyên.
3. Filter theo tên method không phải filter theo chữ ký đầy đủ; overload cần được kiểm tra.
4. MethodTiming không cung cấp stack trace của từng invocation.
5. Thời gian wall-clock không đồng nghĩa CPU time.
6. Instrumentation có thể làm thay đổi timing; không dùng số liệu JFR như benchmark tuyệt đối để so sánh những thay đổi rất nhỏ.

Nếu cần benchmark microsecond/nanosecond với kiểm soát warm-up và fork, dùng **JMH** cho benchmark chuyên biệt; dùng JFR để quan sát hành vi ứng dụng trong workload gần thực tế. Hai công cụ bổ trợ nhau.

## 16. Bảo mật và quyền riêng tư

Recording JFR có thể chứa tên lớp, method, stack trace, thread name và dữ liệu do custom event ghi. Khi dùng MethodTrace, stack trace có thể làm lộ cấu trúc nội bộ hoặc tên thành phần nghiệp vụ.

- Không ghi token, password, session ID, nội dung request nhạy cảm hoặc dữ liệu cá nhân trong custom event.
- Chỉ chia sẻ file recording với người có quyền truy cập phù hợp.
- Giới hạn thời gian lưu file và xóa file điều tra khi hết mục đích.
- Nếu cần chia sẻ, lọc event không cần thiết bằng jfr scrub rồi kiểm tra file đầu ra.
- Không đưa file production lên repository công khai hoặc ticket không được bảo vệ.
- Không dùng filter rộng để thu thập method của thư viện bên thứ ba nếu không có nhu cầu điều tra cụ thể.

Ví dụ loại một event ứng dụng nhạy cảm khỏi bản recording chia sẻ:

~~~bash
jfr scrub --exclude-events com.example.SensitivePayload recording.jfr recording-scrubbed.jfr
~~~

Scrub loại event theo filter; nó không tự động ẩn mọi dữ liệu nhạy cảm trong event khác. Hãy kiểm tra recording đã scrub trước khi chia sẻ.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có jdk.MethodTrace trong file | Filter không khớp, event chưa enabled hoặc recording không chạy trong lúc method được gọi. | Kiểm tra tên fully qualified class/method, enabled và workload. |
| Có MethodTrace nhưng không có invocation ngắn | Threshold cao hơn duration của các lần gọi. | Giảm threshold trong recording kiểm thử. |
| File JFR quá lớn | Filter quá rộng, method tần suất cao, threshold thấp hoặc stack trace bật quá nhiều. | Thu hẹp filter, tăng threshold, giảm thời lượng hoặc tắt stack trace. |
| Không thấy stack trace | stackTrace=false hoặc event/recording không lưu stack. | Bật stackTrace cho MethodTrace và kiểm tra cấu hình JFC. |
| MethodTiming có invocation count thấp | Workload chưa gọi method đủ nhiều hoặc recording quá ngắn. | Chạy workload đại diện lâu hơn. |
| MethodTiming không có min/avg/max đáng tin | Số invocation ít hoặc clock resolution không đủ. | Tăng số lần gọi và xem giá trị thiếu như dữ liệu chưa đủ. |
| MethodTiming cao nhưng CPU thấp | Method đang chờ I/O, lock hoặc dependency. | Đối chiếu socket/file events, ThreadPark, monitor events và CPU samples. |
| Filter nhiều method chỉ ghi một method | Dấu chấm phẩy bị shell tách thành lệnh riêng hoặc chuỗi filter sai. | Quote toàn bộ giá trị filter và kiểm tra JFC đầu ra. |
| Không thấy method theo annotation | Annotation name sai hoặc filter không khớp annotation type. | Dùng fully qualified annotation class và kiểm tra event metadata. |
| Filter dùng wildcard nhưng không hoạt động | Filter grammar không hỗ trợ wildcard/regex. | Dùng tên class, class-method, method hoặc annotation đúng cú pháp. |
| jfr view không nhận diện tên view | Sai cú pháp hoặc JDK/jfr tool không cùng phiên bản. | Dùng jfr help view và jfr view all-views. |
| Recording gây chậm ứng dụng | Instrumentation quá rộng hoặc thời lượng dài. | Giảm scope, chuyển sang MethodTiming, tăng threshold và đo overhead. |

### Checklist kiểm tra trước khi kết luận

1. Xác nhận java và jfr cùng thuộc JDK 25.
2. Xác nhận recording có duration và filename đúng.
3. Kiểm tra filter dùng tên fully qualified chính xác.
4. Kiểm tra event enabled và threshold không loại mọi invocation.
5. Kiểm tra workload thực sự gọi method trong thời gian ghi.
6. Dùng jfr summary và jfr print để xác nhận event tồn tại trước khi mở JMC.
7. Đối chiếu thời lượng method với CPU, I/O, lock và GC.
8. Ghi rõ JDK build, filter, threshold, stackTrace, thời lượng và workload để tái hiện.

## 18. Bài tập thực hành

### Bài A — MethodTiming cho một service

Tạo lớp OrderService với method place được gọi nhiều lần. Bật MethodTiming và lọc theo class-method. Chạy workload có ít nhất vài trăm request, sau đó xem invocation count, minimum, average và maximum.

**Đạt:** giải thích được method nào được chọn và vì sao thống kê chỉ có ý nghĩa khi workload đại diện.

### Bài B — MethodTrace với threshold

Bật MethodTrace cho OrderService.place với threshold 10 ms và stackTrace=true. Tạo workload có một số request cố ý chậm, rồi xem các invocation được ghi.

**Đạt:** chứng minh invocation ngắn hơn threshold không xuất hiện; các invocation chậm có stack trace để xác định caller.

### Bài C — So sánh filter theo class và method

Tạo hai recording: một filter theo tên class OrderService, một filter chỉ theo OrderService.place. So số lượng event và file size.

**Đạt:** giải thích được vì sao filter class có thể rộng hơn class-method.

### Bài D — Filter theo annotation

Đánh dấu một số method bằng annotation Profiled. Cấu hình filter annotation và xác nhận chỉ các method phù hợp được quan sát.

**Đạt:** hiểu annotation là tiêu chí chọn method, không phải công cụ tự ghi event.

### Bài E — Kết hợp nhiều mục tiêu

Lọc OrderService.place, PricingService.calculate và InventoryService.reserve bằng dấu chấm phẩy. Quan sát thứ tự và duration trên cùng một recording.

**Đạt:** quote filter đúng cách trong shell và xác định method nào chiếm nhiều thời gian hơn.

### Bài F — Method chậm do I/O hay CPU?

Tạo một method có thời gian chờ database giả lập và một method có vòng lặp CPU. So MethodTiming với ExecutionSample và event I/O.

**Đạt:** giải thích được vì sao method wall-clock cao không có nghĩa CPU cao.

## 19. Câu hỏi tự kiểm tra

1. JEP 520 bổ sung hai event nào vào JFR trong Java 25?
2. MethodTrace khác MethodTiming ở dạng dữ liệu và độ chi tiết như thế nào?
3. Vì sao MethodTiming không thay thế được stack trace của từng invocation?
4. Filter class-method khác filter method name ở điểm nào?
5. Những dạng mục tiêu nào được filter grammar Java 25 hỗ trợ?
6. Vì sao filter của MethodTrace/MethodTiming nên được áp dụng lúc recording thay vì chỉ dùng jfr print sau đó?
7. Threshold có tác dụng gì và vì sao nó không phải timeout?
8. StackTrace và throttle tác động đến lượng dữ liệu như thế nào?
9. Vì sao MethodTiming có thể báo thời gian lớn trong khi CPU usage thấp?
10. Khi nào nên dùng ExecutionSample trước MethodTrace?
11. Vì sao không nên bật MethodTrace toàn bộ method của một framework trong production dài hạn?
12. Cần kiểm tra những gì khi filter theo annotation không tạo event?

## 20. Tài liệu tham khảo chính thức

- [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): mục tiêu và cơ chế method timing/tracing bằng bytecode instrumentation trong Java 25.
- [Significant Changes in JDK 25 Release — Oracle](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận JFR Method Timing & Tracing là thay đổi trong JDK 25.
- [JFR Package Summary — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): setting enabled, threshold, period, stackTrace, throttle và grammar filter của MethodTrace/MethodTiming.
- [EventSettings — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): cấu hình event bằng Java API.
- [Configure Events and Flight Recorder — Java SE 25](https://docs.oracle.com/en/java/javase/25/jfapi/configuration.html): JFC, event settings và cách giới hạn lượng dữ liệu.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): StartFlightRecording và cú pháp event-setting.
- [The jfr Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): xem, in, lọc và scrub recording.
- [What's New in Java 25 — Inside Java](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): ví dụ command line và output của MethodTrace/MethodTiming.

**Ghi chú tính hiện hành:** JEP 520 là tính năng JFR trong Java 25, không phải preview. Filter theo method, threshold và stack trace là cách giới hạn phạm vi thu thập ngay từ recording. Các số liệu MethodTiming là thống kê thời gian thực thi xấp xỉ, không phải CPU time; MethodTrace có thể tạo nhiều event nên cần filter hẹp và recording có thời hạn.

**Kết quả cần nộp:** một file JFC có filter rõ ràng, recording MethodTiming hoặc MethodTrace, lệnh start và lệnh phân tích, bảng giải thích filter/threshold/stackTrace, số lượng event và dung lượng file, cùng nhận xét overhead và giới hạn của số liệu. Kết quả phải cho thấy bạn kiểm soát được phạm vi instrumentation và lượng dữ liệu JFR theo mục tiêu quan sát trên Java 25.
