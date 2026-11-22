# Tránh ghi nhận trùng khi thao tác đã được tự động đo lường

## 1. Vấn đề bắt đầu từ một thao tác nhưng có nhiều nơi ghi số đo

Giả sử một yêu cầu thanh toán được xử lý đúng một lần. Spring Boot đã có phép đo HTTP tự động, nhưng ứng dụng còn thêm một lớp đo bằng annotation và một đoạn `Timer.record(...)` bao quanh cùng công việc. Bảng giám sát có thể hiển thị hai hoặc ba phép đo cho cùng một hoạt động.

Có hai hậu quả cần phân biệt:

- Nhiều nơi ghi vào **cùng meter** làm số lần ghi nhận và tổng thời lượng bị tăng.
- Nhiều meter khác tên cùng mô tả một hoạt động tạo dữ liệu dư thừa; nếu dashboard cộng chúng như các sự kiện độc lập, số liệu tổng hợp cũng sai.

Mục tiêu không phải loại bỏ mọi phép đo lồng nhau. Mục tiêu là xác định **mỗi phép đo trả lời câu hỏi gì, đo từ đâu đến đâu và thành phần nào chịu trách nhiệm ghi**.

Ví dụ, thời lượng toàn yêu cầu HTTP và thời lượng bước kiểm tra giá trong yêu cầu là hai câu hỏi khác nhau. Chúng có thể cùng tồn tại. Ngược lại, hai lớp đều tuyên bố đếm “số yêu cầu HTTP đã hoàn tất” cho cùng một lần xử lý thì cần xem lại trách nhiệm đo.

## 2. Hiểu luồng tạo số đo trước khi thêm metric tùy chỉnh

Một cách hình dung luồng xử lý là:

```text
thao tác thực tế
    → điểm bắt đầu/kết thúc phép đo
    → Timer hoặc Observation
    → MeterRegistry
    → endpoint / hệ thống xuất số đo
    → dashboard và cảnh báo
```

`Observation` biểu diễn vòng đời một hoạt động. Các `ObservationHandler` phản ứng với vòng đời đó để tạo số đo, trace hoặc những hành vi quan sát khác. Nếu registry đã có handler tạo metric, một observation kết thúc đã có thể làm `Timer` được ghi nhận. Thêm một `Timer.record(...)` quanh cùng hoạt động không còn là thao tác “bổ sung cho đủ” nữa. Xem [cơ chế Observation Handler của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Trên ứng dụng Spring Boot, cần kiểm tra những điểm đo sẵn có trước:

| Phạm vi | Nguồn đo có thể đã tồn tại | Điều cần xác minh |
| --- | --- | --- |
| Yêu cầu Spring MVC/Spring WebFlux | Phép đo request của framework, thường có tên `http.server.requests` | Actuator, cấu hình observation và luồng xử lý thực tế |
| Gọi HTTP ra ngoài | Phép đo của client được cấu hình từ builder do Spring Boot cung cấp | Client có thực sự dùng builder đã được cấu hình không |
| Phương thức repository | Tích hợp tương ứng của Spring Data | Loại repository và cấu hình đang sử dụng |
| Phương thức có `@Observed` hoặc `@Timed` | Aspect hoặc tích hợp xử lý annotation | Cơ chế đó có hoạt động và lời gọi có đi qua nó không |
| Đoạn nghiệp vụ tự viết | Observation hoặc Timer do ứng dụng chủ động tạo | Đoạn đó có thật sự chưa được đo với cùng ý nghĩa không |

Không suy ra rằng mọi phương thức của một `@Service` đều đã được tự động đo. Cũng không suy ra rằng chỉ cần có annotation trên mã là chắc chắn có metric. Điều phải kiểm tra là cơ chế thực thi và số đo xuất hiện trong runtime.

Với HTTP client, Spring Boot hướng dẫn dùng `RestTemplateBuilder`, `RestClient.Builder` hoặc `WebClient.Builder` được tự động cấu hình để nhận hỗ trợ đo lường. Tự tạo client theo cách khác có thể không đi qua tích hợp đó. [Tài liệu Metrics của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html) mô tả các tích hợp này.

## 3. Ba phân biệt giúp tránh chẩn đoán sai

### 3.1. Đăng ký lại meter khác với ghi nhận lại sự kiện

Danh tính meter được xác định bởi tên và tập nhãn trong một registry. Với cùng loại meter và cùng danh tính, việc gọi lại builder/register thường trả về meter đã có; nó không tự tăng số lần xử lý. Thứ tự khai báo các nhãn không tạo ra một danh tính mới.

```java
Timer first = registry.timer("checkout.duration", "channel", "web");
Timer second = registry.timer("checkout.duration", "channel", "web");
```

Đây là đoạn minh họa với `registry` đã tồn tại. Hai lệnh trên chỉ lấy/đăng ký timer. Chưa có `record(...)` hoặc sample được dừng vào timer thì chưa có lần đo thời lượng nào.

Ngược lại, hai lời gọi `record(...)` là hai lần ghi nhận, dù cả hai cùng trỏ tới một đối tượng timer. Registry không biết hai bản ghi đó thực ra đại diện cho cùng một công việc và không tự khử trùng theo mã yêu cầu. [Tài liệu Meters của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) giải thích danh tính meter theo tên và nhãn.

### 3.2. Timer đã có số lần ghi nhận, không chỉ có thời lượng

`Timer` ghi cả số lần đo và tổng thời gian. Không cần thêm một `Counter` chỉ để đếm lại đúng những lần gọi đã được timer ghi nhận, nếu câu hỏi và ranh giới đếm hoàn toàn giống nhau.

Tuy nhiên, “số đơn được chấp nhận”, “số dòng dữ liệu nhập thành công” hoặc “số lần thử thanh toán” có thể là những sự kiện nghiệp vụ khác. Counter cho các sự kiện đó vẫn có ý nghĩa khi định nghĩa rõ và không bị cộng lẫn với số request. Đây cũng là điểm được nhấn mạnh trong [tài liệu Counters của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 3.3. Hai phép đo lồng nhau có thể đều đúng

Giả sử một request mất 10 ms, trong đó bước kiểm tra dữ liệu mất 2 ms:

```text
toàn request:        [---------- 10 ms ----------]
kiểm tra dữ liệu:          [-- 2 ms --]
```

Một bản ghi cho request và một bản ghi cho bước kiểm tra là hợp lý. Tổng thời gian request vẫn là 10 ms. Cộng 10 + 2 rồi gọi 12 ms là “tổng thời gian xử lý request” sẽ đếm phần lồng nhau hai lần.

Cũng cần phân biệt một thao tác nghiệp vụ với các lần thử lại. Một lần thanh toán có thể gọi cổng thanh toán ba lần do retry: số thao tác nghiệp vụ bằng 1, số lần gọi ra ngoài bằng 3. Khác nhau về số lượng ở đây có thể hoàn toàn đúng.

## 4. Thí nghiệm Java: một lần xử lý nhưng count tăng hai

Ví dụ sau dùng Java 21 và Micrometer 1.13.0. Nó chạy độc lập ở cấp Micrometer để cô lập cơ chế; không khởi động Spring Boot hay máy chủ HTTP.

`DefaultMeterObservationHandler` đóng vai trò tự động chuyển observation thành timer. Cùng lúc đó, nhánh sai còn ghi thủ công vào chính timer ấy. `MockClock` giúp kết quả thời gian xác định mà không cần ngủ thật.

### 4.1. Khai báo dependency

Tạo `pom.xml` trong một thư mục thực hành độc lập:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duplicate-recording-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Các phiên bản được ghi rõ để tái lập thí nghiệm độc lập. Trong ứng dụng Spring Boot thực tế, dùng cơ chế quản lý dependency của Spring Boot để giữ các thư viện Micrometer tương thích.

### 4.2. Chương trình hoàn chỉnh

Lưu tại `src/main/java/demo/DuplicateRecordingDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DuplicateRecordingDemo {
    public static void main(String[] args) {
        sameOperation("DUPLICATED", true);
        sameOperation("ONE_OWNER", false);
        differentScopes();
    }

    private static void sameOperation(String label, boolean duplicate) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry meters =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));

            Timer timer = Timer.builder("demo.checkout")
                    .tags("channel", "web", "error", "none")
                    .register(meters);
            Timer same = Timer.builder("demo.checkout")
                    .tags("error", "none", "channel", "web")
                    .register(meters);
            System.out.printf("%s sameMeter=%s before=%d%n",
                    label, timer == same, timer.count());

            AtomicInteger workCalls = new AtomicInteger();
            Observation.createNotStarted("demo.checkout", observations)
                    .lowCardinalityKeyValue("channel", "web")
                    .observe(() -> {
                        if (duplicate) {
                            timer.record(() -> doWork(clock, workCalls));
                        } else {
                            doWork(clock, workCalls);
                        }
                    });

            long expectedCount = duplicate ? 2 : 1;
            if (workCalls.get() != 1 || timer.count() != expectedCount) {
                throw new AssertionError("Unexpected recording count");
            }
            System.out.printf(Locale.ROOT,
                    "%s work=%d count=%d totalMs=%.0f%n",
                    label, workCalls.get(), timer.count(),
                    timer.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            meters.close();
        }
    }

    private static void doWork(MockClock clock, AtomicInteger workCalls) {
        workCalls.incrementAndGet();
        clock.add(Duration.ofMillis(10));
    }

    private static void differentScopes() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry meters =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));
            Timer validation = Timer.builder("checkout.validation")
                    .tag("phase", "basic")
                    .register(meters);

            Observation.createNotStarted("demo.request", observations)
                    .observe(() -> {
                        clock.add(Duration.ofMillis(3));
                        validation.record(() -> clock.add(Duration.ofMillis(2)));
                        clock.add(Duration.ofMillis(5));
                    });

            Timer request = meters.get("demo.request").timer();
            System.out.printf(Locale.ROOT,
                    "DIFFERENT_SCOPES requestCount=%d requestMs=%.0f validationCount=%d validationMs=%.0f%n",
                    request.count(), request.totalTime(TimeUnit.MILLISECONDS),
                    validation.count(), validation.totalTime(TimeUnit.MILLISECONDS));
        } finally {
            meters.close();
        }
    }
}
```

Trong hai kịch bản đầu, timer thủ công có nhãn `channel=web` và `error=none` để khớp timer mà handler tạo cho observation thành công trong phiên bản đang thử. Đây là cách cố ý tạo cùng danh tính cho thí nghiệm. Khi tích hợp thật, không sao chép nhãn nội bộ của framework để tự ghi vào meter HTTP của nó.

`AtomicInteger` đếm số lần phần xử lý thật được thực thi; nhờ đó ta phân biệt “công việc chạy hai lần” với “công việc chạy một lần nhưng bị ghi số đo hai lần”.

### 4.3. Biên dịch và chạy

Từ thư mục chứa `pom.xml`, dùng JDK 21 và Maven. Lần tải dependency đầu cần truy cập kho Maven.

Trên PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/DuplicateRecordingDemo.java
java -cp "target/classes;target/dependency/*" demo.DuplicateRecordingDemo
```

Trên Linux/macOS, dùng hai lệnh đầu tương tự và thay lệnh chạy bằng:

```bash
java -cp "target/classes:target/dependency/*" demo.DuplicateRecordingDemo
```

Stdout chính xác:

```text
DUPLICATED sameMeter=true before=0
DUPLICATED work=1 count=2 totalMs=20
ONE_OWNER sameMeter=true before=0
ONE_OWNER work=1 count=1 totalMs=10
DIFFERENT_SCOPES requestCount=1 requestMs=10 validationCount=1 validationMs=2
```

### 4.4. Vì sao có kết quả này?

Ở `DUPLICATED`:

1. Hai lần đăng ký cùng danh tính trả về cùng timer; trước khi chạy, count vẫn bằng 0.
2. Công việc thật chạy một lần và làm đồng hồ tăng 10 ms.
3. `timer.record(...)` ghi một lần 10 ms.
4. Khi observation kết thúc, handler ghi thêm một lần 10 ms.
5. Kết quả là count bằng 2 và tổng thời gian bằng 20 ms.

Ở `ONE_OWNER`, ta bỏ lời gọi `timer.record(...)` bên trong. Observation cùng handler chịu trách nhiệm ghi duy nhất một lần, nên count bằng 1 và tổng thời gian bằng 10 ms.

Ở `DIFFERENT_SCOPES`, observation ngoài đo toàn khối 3 + 2 + 5 = 10 ms; timer trong chỉ đo bước 2 ms. Mỗi bộ đo có một bản ghi và trả lời một câu hỏi khác nhau.

Một điểm dễ bỏ sót: trong kịch bản sai, trung bình 20/2 vẫn bằng 10 ms. Vì vậy, nhìn mỗi thời lượng trung bình có thể không phát hiện lỗi ghi trùng. Số lần gọi, tổng thời lượng, phân bố nhãn và số lần thực thi thật đều cần được đối chiếu.

## 5. Chọn thành phần chịu trách nhiệm đo trong Spring Boot

### 5.1. Giữ phép đo tự động khi nó đã trả lời đúng câu hỏi

Nếu cần số request, trạng thái HTTP và thời lượng xử lý request, hãy kiểm tra meter tự động trước khi thêm một timer khác bao quanh controller.

Đối với trường hợp này, thường nên:

- Giữ phép đo HTTP của framework.
- Bỏ timer/annotation tự viết chỉ để đếm lại cùng loại request.
- Dùng nhãn và truy vấn phù hợp để lọc endpoint cần xem.
- Nếu cần mở rộng thông tin, xem cơ chế observation convention thay vì tạo thêm một phép đo cùng ý nghĩa.

Một annotation tạo một meter khác tên không tự sửa được trùng lặp về ý nghĩa. Ví dụ, `http.server.requests` và `checkout.http.duration` vẫn có thể cùng mô tả lượt checkout nếu cả hai đều được dashboard dùng như số request checkout. Phải định nghĩa lại cách sử dụng hoặc bỏ phần dư, không chỉ đổi tên.

### 5.2. Tạo phép đo nghiệp vụ khi câu hỏi thực sự khác

Giả sử cần đo riêng việc tính giá, có thể tạo một observation ở ranh giới nghiệp vụ:

```java
return Observation.createNotStarted("checkout.price", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(this::calculatePrice);
```

Đây là đoạn minh họa bên trong một thành phần đã có `ObservationRegistry` và phương thức `calculatePrice`. Ranh giới cần được định nghĩa là “một lần tính giá”, không phải “một request HTTP”.

Nếu observation đó đã được handler chuyển thành metric, không thêm một `Timer.record(...)` quanh chính `calculatePrice` với cùng mục tiêu đo. Có thể chọn Timer thủ công thay cho observation nếu chỉ cần số đo thời gian, nhưng nên chọn một cơ chế chịu trách nhiệm cho ranh giới này.

Phép đo nghiệp vụ có thể được gọi từ HTTP, lịch chạy hoặc message consumer. Khi đó, số lần tính giá không nhất thiết bằng số request HTTP và không nên bị ép phải bằng nhau.

### 5.3. Annotation cũng là một điểm đo cần kiểm kê

`@Timed`, `@Observed` và mã `Timer`/`Observation` thủ công đều có thể tham gia vào luồng đo. Khi cơ chế xử lý annotation đang hoạt động, đặt annotation rồi tiếp tục đo thủ công quanh cùng thân phương thức có thể tạo thêm bản ghi hoặc thêm một observation dư.

Không mặc định mọi bản Spring Boot, mọi cấu hình AOP và mọi kiểu lời gọi đều xử lý annotation giống nhau. Ví dụ, `@Timed` cho phương thức thông thường cần cơ chế xử lý tương ứng; với Spring AOP, lời gọi phải đi qua proxy. [Tài liệu Timers và TimedAspect](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) mô tả cách annotation được thực thi.

Khi đã chọn annotation làm nơi đo, thân phương thức nên tập trung vào nghiệp vụ. Khi đã chọn mã đo thủ công để kiểm soát ranh giới phức tạp, loại bỏ annotation có cùng trách nhiệm.

## 6. Những cách “sửa” dễ làm mất hoặc méo dữ liệu

### 6.1. Không thêm handler tạo metric thứ hai chỉ vì chưa thấy metric

Trong Spring Boot, các thành phần observation có thể đã được tự động đăng ký. Trước khi gọi thủ công:

```java
observations.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));
```

hãy kiểm tra registry hiện tại đã có handler tạo metric chưa. Đoạn này cần thiết trong chương trình Micrometer độc lập ở phần 4, nhưng không phải hướng dẫn để chép nguyên vào mọi ứng dụng Spring Boot.

Một observation có handler cho metric và handler cho tracing là cách dùng hợp lệ: hai handler phục vụ hai đầu ra khác nhau. Điều đáng kiểm tra là nhiều handler cùng tạo lại cùng loại metric cho một observation.

### 6.2. Không dùng MeterFilter để đoán bản ghi nào là bản sao

`MeterFilter` có thể từ chối meter hoặc thay đổi danh tính meter. Nếu hai nơi cùng ghi vào một meter, filter theo tên không biết lời ghi nào là “bản gốc” và lời ghi nào là “bản sao”. Từ chối meter đó có thể làm mất cả hai.

Tương tự, đổi tên hai meter khác nhau thành cùng tên hoặc bỏ các nhãn dùng để phân biệt chúng có thể gộp các nguồn ghi vào cùng danh tính. Vì thế, chỉnh filter không thay thế việc sửa nơi ghi. Xem [vai trò và thứ tự áp dụng MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

### 6.3. Phân biệt ngăn observation với ngăn meter

Khi có kế hoạch thay thế hẳn một tích hợp, Spring Boot cho phép ngăn observation theo tiền tố tên. Ví dụ cấu hình sau có phạm vi rộng:

```properties
management.observations.enable.http.server.requests=false
```

Nó ngăn các observation có tiền tố tương ứng; đây không phải cách chỉ bỏ một annotation trùng trên một controller. Việc ngăn observation còn có thể ảnh hưởng các đầu ra phụ thuộc vào observation đó, như tracing. Chỉ dùng khi đã xác định rõ phạm vi thay thế và kiểm chứng những dữ liệu vẫn cần giữ.

Ngược lại, cấu hình `management.metrics.enable...` tác động ở tầng meter; nó không đồng nghĩa ngừng mọi observation/trace liên quan. Một Timer thủ công cũng không tự đi qua `ObservationPredicate` chỉ vì tên của nó giống tên observation.

Thông thường, nếu phần đo thêm là dư thừa, sửa đúng phần thêm đó sẽ rõ ràng hơn việc tắt phép đo HTTP trên toàn ứng dụng. [Tài liệu Observability của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.preventing-observations) giải thích cơ chế ngăn observation.

### 6.4. Không dùng một hệ số chia để che số liệu tăng gấp đôi

Lấy count chia 2 trên dashboard chỉ che một biểu hiện. Nhánh lỗi, retry hoặc một tuyến gọi không đi qua cả hai lớp đo có thể không còn tạo đúng hai bản ghi. Sau một thay đổi nhỏ, hệ số đó làm dữ liệu sai theo cách khác.

Cần sửa điểm tạo dữ liệu rồi kiểm tra lại số tăng thêm cho một nhóm đầu vào đã biết.

## 7. Kiểm chứng trên ứng dụng bằng số tăng thêm của COUNT

Hãy kiểm thử trên một instance có thể kiểm soát và chọn một luồng gọi cụ thể. Ví dụ, ứng dụng Spring MVC đã có `GET /checkout` và endpoint `metrics` được expose trong môi trường thử nghiệm.

Đọc metric tự động bằng tên gốc trong Java, đồng thời lọc đủ nhãn cần thiết:

```bash
curl --get "http://127.0.0.1:8080/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/checkout" --data-urlencode "tag=method:GET" --data-urlencode "tag=status:200"
```

Trên PowerShell có thể gọi `curl.exe` để tránh bí danh. Nếu ứng dụng dùng cổng hoặc đường dẫn management khác, thay URL theo cấu hình thực tế. Tên và giá trị nhãn phải lấy từ meter đang có, không giả định mọi tích hợp đều dùng cùng một tập nhãn.

Thực hiện theo thứ tự:

1. Nếu meter chưa tồn tại, gửi một request khởi tạo rồi đọc giá trị ban đầu. Chưa có meter không phải bằng chứng rằng count hiện tại bằng một giá trị đã đo được.
2. Ghi lại `COUNT` sau khi request khởi tạo đã hoàn tất.
3. Gửi chính xác N request phù hợp nhãn đang lọc, không bật retry tự động và chờ tất cả hoàn thành.
4. Đọc lại cùng metric với cùng bộ lọc.
5. Với hợp đồng “mỗi request hoàn tất được ghi một lần”, hiệu `COUNT_sau - COUNT_trước` phải bằng N.

Không so sánh trực tiếp giá trị tích lũy với N nếu tiến trình đã phục vụ những request trước đó. Không dùng tổng thời lượng thật làm hằng số kiểm thử, vì nó phụ thuộc môi trường.

Endpoint `metrics` cộng các phép đo của những meter khớp tên và các nhãn được chọn. Thiếu bộ lọc có thể làm kết quả bao gồm nhiều URI hoặc nhiều nhóm trạng thái. Chính request đọc Actuator cũng là lưu lượng HTTP, nên việc chỉ chọn `uri:/checkout` giúp tránh trộn nó vào nhóm đang kiểm tra.

Nếu count tăng 2N, kiểm tra các nơi ghi trong tiến trình. Nếu count tăng đúng N trong registry nhưng dashboard vẫn tăng gấp đôi, chuyển sang kiểm tra truy vấn, các nhãn và đường thu thập dữ liệu.

## 8. Kiểm tra cả nhánh lỗi, retry và ranh giới bất đồng bộ

Một luồng thành công cho kết quả đúng chưa đủ để kết luận đã hết ghi trùng.

- **Nhánh lỗi:** cùng một lần lỗi có thể được ghi ở cả `catch` lẫn `finally`. Chọn một điểm kết thúc phép đo; việc gắn nhãn lỗi phải nhất quán với định nghĩa phép đo.
- **Retry:** phân biệt một thao tác logic với mỗi lần gọi thử. Chọn vị trí đo ngoài vòng retry nếu cần thời gian toàn thao tác; chọn từng lần thử nếu cần chẩn đoán lời gọi ra ngoài. Nếu giữ cả hai, dùng tên và câu hỏi rõ ràng.
- **Bất đồng bộ:** phương thức trả về chưa chắc công việc đã hoàn thành. Một lớp đo thời gian gửi việc và lớp khác đo thời gian thực thi có ranh giới khác nhau; đừng gọi cả hai là thời gian hoàn tất cùng một công việc.
- **Luồng gọi qua proxy:** một nhánh đi qua aspect, nhánh khác tự gọi trong cùng đối tượng có thể tạo số bản ghi khác nhau. Không dựa vào sự bỏ qua aspect để “khử trùng”.
- **Đường gọi lồng nhau:** request ngoài và client call bên trong thường là hai sự kiện khác nhau. Nếu client gọi ngược về chính ứng dụng, số HTTP request thực tế có thể nhiều hơn số lần người dùng bấm nút.

Điểm kiểm tra là số lần thực thi thật của từng đơn vị công việc, không chỉ số lần đi vào phương thức ngoài cùng.

## 9. Tách lỗi trong ứng dụng khỏi lỗi ở đường thu thập

| Quan sát | Hướng kiểm tra |
| --- | --- |
| Một lần thực thi thật, cùng timer tăng count hai lần | Timer thủ công, sample, aspect hoặc observation handler cùng ghi |
| Hai metric khác tên cùng được cộng thành “số request” | Định nghĩa metric và truy vấn dashboard |
| Metric tăng đúng trong tiến trình, tổng trên dashboard gấp đôi | Scrape trùng, đường export song song hoặc phép tổng hợp không phù hợp |
| Nhiều time series của cùng tên nhưng khác URI/status/instance | Các chiều dữ liệu; chưa đủ để kết luận ghi trùng |
| Một timer có count, total và các bucket | Nhiều thống kê của cùng bộ đo; không phải mỗi dòng là một lần xử lý |
| Một nghiệp vụ có một timer ngoài và nhiều lần thử bên trong | Kiểm tra hợp đồng retry và phạm vi đo trước khi xóa |

Một `CompositeMeterRegistry` phân phối số đo tới nhiều registry đích có thể là cấu hình chủ động, chẳng hạn gửi đến hai hệ thống giám sát khác nhau. Điều đó không tự chứng minh nguồn Java ghi trùng. Chỉ có vấn đề tổng hợp khi cùng dữ liệu quay về một nơi và bị tính nhiều lần ngoài ý muốn.

Các tổ hợp nhãn khác nhau là những chuỗi dữ liệu khác nhau. Giữ nhãn có số giá trị hữu hạn và có ý nghĩa phân nhóm; không thêm request ID hoặc timestamp để biến từng lần ghi thành một meter mới. Cách đó tăng số chuỗi dữ liệu và không giải quyết nguyên nhân đo trùng.

## 10. Cách chốt một thiết kế đo không trùng

Trước khi thêm hoặc giữ một metric, viết được một câu rõ ràng theo mẫu:

```text
Metric này đo [đơn vị công việc],
từ [điểm bắt đầu] đến [điểm kết thúc],
được ghi bởi [thành phần],
và được dùng để trả lời [câu hỏi].
```

Ví dụ:

- `http.server.requests`: một request HTTP do tích hợp web ghi, dùng để theo dõi lưu lượng và thời lượng request.
- `checkout.price`: một lần tính giá do observation ở tầng nghiệp vụ ghi, dùng để phân tích phần tính giá.
- `payment.attempt`: một lần gọi thử đến cổng thanh toán, dùng để xem hiệu quả retry.

Ba tên này có thể cùng tồn tại vì ba đơn vị công việc khác nhau. Mỗi ranh giới vẫn cần một thành phần chịu trách nhiệm ghi duy nhất.

Tự kiểm tra với ba tình huống:

1. Đăng ký cùng timer hai lần nhưng không gọi `record`: count có tăng không?
2. Một công việc 10 ms được timer thủ công và observation handler cùng ghi vào cùng meter: count và tổng thời gian là bao nhiêu?
3. Request 10 ms chứa bước kiểm tra 2 ms: có được cộng hai timer thành 12 ms thời gian request không?

Đối chiếu: không tăng; count bằng 2 và tổng thời gian bằng 20 ms trong thí nghiệm; không cộng vì thời gian bước kiểm tra đã nằm trong thời gian request.

Thiết kế đúng được chứng minh bằng số lần thực thi và ranh giới đo đã xác định, rồi kiểm tra lại trên dữ liệu runtime. Tên metric đẹp hoặc biểu đồ có vẻ hợp lý không thay thế được việc đối chiếu đó.
