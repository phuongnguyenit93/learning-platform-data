# Đăng ký và đọc lại một Counter hoặc Timer đầu tiên

Để bắt đầu đo lường một ứng dụng Java bằng Micrometer, hãy tạo một `MeterRegistry`, đăng ký meter với tên và các tag có ý nghĩa, ghi nhận một vài sự kiện rồi đọc lại số liệu. `Counter` dùng để đếm sự kiện tích lũy; `Timer` dùng để đo thời gian thực hiện thao tác và đồng thời ghi nhận số lần thao tác được đo.

Bài này đi qua hai cách chạy: dùng `SimpleMeterRegistry` để thử Micrometer độc lập, và inject `MeterRegistry` do Spring Boot tự cấu hình trong ứng dụng. Sau khi hoàn thành, bạn có thể xác nhận meter đã được đăng ký, hiểu cách tìm lại meter bằng tên và tag, và biết vì sao số liệu trong registry thử nghiệm chưa tự động xuất hiện trên hệ thống giám sát.

## 1. Chọn cách tích hợp và thêm dependency

Micrometer Core cung cấp API chung như `MeterRegistry`, `Counter` và `Timer`. Để dùng API đó, dự án cần có dependency `micrometer-core`. Nếu ứng dụng dùng Spring Boot, starter Actuator tích hợp Micrometer và cấu hình registry phù hợp với các dependency exporter có mặt trong ứng dụng.

Với Spring Boot và Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Với Spring Boot và Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Các ví dụ trên giả định dự án đã dùng Spring Boot parent, plugin hoặc BOM để quản lý phiên bản dependency. Hãy để Spring Boot quản lý phiên bản Micrometer tương thích với phiên bản Boot đang dùng; tránh tự ghép các phiên bản Micrometer khác dòng nếu không có chủ đích.

Nếu dự án Java không dùng Spring Boot, chỉ cần Micrometer Core. Ví dụ khai báo Gradle khi dự án quản lý phiên bản bằng version catalog hoặc dependency constraints:

```kotlin
dependencies {
    implementation("io.micrometer:micrometer-core:<micrometer-version>")
}
```

Thay `<micrometer-version>` bằng phiên bản đã chọn và quản lý tập trung trong dự án. Với Maven, dependency tương ứng là `io.micrometer:micrometer-core`, cùng phiên bản được khai báo trong thẻ `version` hoặc được quản lý bởi BOM. Sau khi đồng bộ dependency, IDE cần nhận diện được các package `io.micrometer.core.instrument`.

## 2. Tạo registry đơn giản để thử nghiệm

`MeterRegistry` là điểm đăng ký và truy cập các meter. Với ứng dụng thật, registry thường được Spring Boot tự cấu hình hoặc được kết nối với một backend. Khi muốn thử API trong một chương trình nhỏ hay bài kiểm thử, `SimpleMeterRegistry` là lựa chọn thuận tiện vì lưu số liệu trong bộ nhớ của tiến trình.

Ví dụ dưới đây đăng ký một counter cho đơn hàng được tạo và một timer cho thao tác thanh toán:

```java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class FirstMeterExample {
    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        Counter ordersCreated = registry.counter(
                "demo.orders.created",
                "channel", "web");

        ordersCreated.increment();
        ordersCreated.increment(2.0);

        Timer checkoutDuration = registry.timer(
                "demo.checkout.duration",
                "result", "success");

        checkoutDuration.record(() -> {
            // Thay phần xử lý minh họa bằng thao tác nghiệp vụ cần đo.
            for (int i = 0; i < 100_000; i++) {
                Math.sqrt(i);
            }
        });

        Counter counterReadBack = registry.find("demo.orders.created")
                .tag("channel", "web")
                .counter();

        Timer timerReadBack = registry.find("demo.checkout.duration")
                .tag("result", "success")
                .timer();

        if (counterReadBack == null || timerReadBack == null) {
            throw new IllegalStateException("Không tìm thấy meter đã đăng ký");
        }

        System.out.println("Orders created = " + counterReadBack.count());
        System.out.println("Checkout count = " + timerReadBack.count());
        System.out.println("Checkout total ms = "
                + timerReadBack.totalTime(TimeUnit.MILLISECONDS));

        registry.close();
    }
}
```

Đây là chương trình minh họa API; vòng lặp chỉ tạo một thao tác có thời lượng để timer ghi nhận. Trong ứng dụng thực tế, hãy truyền vào `record(...)` lời gọi nghiệp vụ cần đo, chẳng hạn xử lý thanh toán hoặc gọi một dịch vụ khác. Không dùng thời lượng của vòng lặp minh họa để đánh giá hiệu năng hệ thống.

Kết quả counter trong ví dụ là `3.0`, vì meter được tăng một lần rồi tăng thêm hai. `Checkout count` là `1`, vì timer đã ghi nhận một lần thực hiện. `Checkout total ms` phụ thuộc thời gian chạy trên máy, nên không có một con số cố định cần mong đợi.

## 3. Đăng ký và đọc lại Counter

`Counter` biểu diễn số lần một sự kiện xảy ra. Mỗi lần sự kiện hoàn tất, gọi `increment()`; nếu một thao tác đại diện cho nhiều sự kiện, có thể gọi `increment(amount)` với lượng tăng không âm.

```java
Counter completed = registry.counter(
        "orders.completed",
        "channel", "mobile");

completed.increment();
completed.increment(3.0);

double total = completed.count();
```

`registry.counter(name, tags...)` vừa tìm meter có định danh tương ứng vừa đăng ký meter nếu chưa có. Định danh meter được tạo từ tên và tập tag. Gọi lại với cùng tên và cùng cặp tag sẽ truy cập cùng một meter trong registry; thay giá trị tag sẽ tạo một chuỗi meter khác.

Có thể đọc lại meter bằng API tìm kiếm của registry:

```java
Counter readBack = registry.find("orders.completed")
        .tag("channel", "mobile")
        .counter();

if (readBack != null) {
    System.out.println(readBack.count());
}
```

`find(...)` hữu ích khi cần tra cứu meter đã tồn tại. Nếu không có meter phù hợp với tên và tag đã cung cấp, `counter()` trả về `null`; vì vậy cần kiểm tra kết quả trước khi sử dụng. Khi đã có tham chiếu `Counter` lúc đăng ký, đọc trực tiếp qua `count()` thường đơn giản hơn.

Counter là số đo tích lũy, chỉ tăng trong vòng đời của meter. Không dùng counter để biểu diễn số phần tử hiện đang nằm trong hàng đợi hoặc số kết nối đang mở, vì các đại lượng đó có thể tăng và giảm. Hãy dùng `Gauge` cho trạng thái hiện tại. Tốc độ request mỗi giây cũng không phải giá trị mà ứng dụng nên tự ghi vào counter; backend có thể tính tốc độ tăng từ counter theo cửa sổ thời gian.

## 4. Đăng ký và đọc lại Timer

`Timer` đo thời gian của một thao tác. Khi ghi nhận một lần thực hiện, timer tích lũy số lần (`count`) và tổng thời gian (`totalTime`). Tùy registry và cấu hình phân phối, timer còn có thể xuất histogram hoặc percentile.

Đăng ký timer theo tên và tag:

```java
Timer checkoutTimer = registry.timer(
        "checkout.duration",
        "result", "success");
```

Gọi `record(Runnable)` để đo thời gian chạy của một đoạn mã:

```java
checkoutTimer.record(() -> paymentService.charge(order));
```

Timer đo toàn bộ thời gian từ lúc bắt đầu đến khi đoạn mã kết thúc. Việc ghi nhận vẫn được thực hiện khi đoạn mã ném exception; nếu cần phân biệt kết quả, hãy dùng tag có tập giá trị hữu hạn và chọn giá trị phù hợp sau khi biết kết quả thao tác. Với logic cần chọn tag sau khi thao tác kết thúc, `Timer.Sample` cho phép bắt đầu đo trước rồi dừng vào timer tương ứng:

```java
Timer.Sample sample = Timer.start(registry);
String result = "success";

try {
    paymentService.charge(order);
} catch (RuntimeException exception) {
    result = "failure";
    throw exception;
} finally {
    sample.stop(registry.timer("checkout.duration", "result", result));
}
```

Đọc lại timer bằng tên và tag giống lúc đăng ký:

```java
Timer readBack = registry.find("checkout.duration")
        .tag("result", "success")
        .timer();

if (readBack != null) {
    long executions = readBack.count();
    double totalMilliseconds = readBack.totalTime(TimeUnit.MILLISECONDS);
    System.out.println("Executions = " + executions);
    System.out.println("Total ms = " + totalMilliseconds);
}
```

`count()` là số lần thao tác đã được ghi nhận; `totalTime(unit)` là tổng thời gian của tất cả lần ghi nhận, được chuyển sang đơn vị yêu cầu. Đây là tổng thời gian tích lũy, không phải thời gian của lần gọi gần nhất. Nếu cần thời gian trung bình trong chính tiến trình, có thể chia tổng thời gian cho số lần khi `count()` lớn hơn không. Khi tổng hợp nhiều instance, hãy để backend cộng tổng thời gian và số lần trước khi chia để có trung bình có trọng số.

Tên `Timer` có từ `duration` hoặc `seconds` không tự quyết định đơn vị lưu trữ. Micrometer xử lý đơn vị thời gian qua API và registry; khi đọc, luôn chỉ định đơn vị rõ ràng như `TimeUnit.MILLISECONDS` hoặc `TimeUnit.SECONDS`.

## 5. Dùng MeterRegistry do Spring Boot cung cấp

Khi ứng dụng có `spring-boot-starter-actuator` và một cấu hình registry phù hợp, Spring Boot tự cấu hình `MeterRegistry` để các bean có thể sử dụng. Hãy inject registry qua constructor. Cách này bảo đảm meter được đăng ký vào cùng registry mà Actuator và exporter sử dụng.

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final MeterRegistry registry;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void orderCompleted(String channel) {
        registry.counter("orders.completed", "channel", channel)
                .increment();
    }

    public void measureCheckout(Runnable checkout) {
        registry.timer("checkout.duration")
                .record(checkout);
    }
}
```

Service nghiệp vụ có thể gọi `orderCompleted(...)` sau khi đơn hàng hoàn tất và bọc thao tác cần đo bằng `measureCheckout(...)`. Giá trị `channel` cần thuộc một tập hữu hạn đã được xác định, ví dụ `web`, `mobile` hoặc `partner`. Không đưa `orderId`, email, mã người dùng, token hoặc URL đầy đủ vào tag.

Không tự tạo `new SimpleMeterRegistry()` trong bean của ứng dụng Spring Boot để ghi metric vận hành. Registry đó chỉ giữ số liệu riêng trong bộ nhớ của nó; Actuator và exporter không tự nhìn thấy các meter đã ghi vào một registry độc lập. `SimpleMeterRegistry` phù hợp cho ví dụ nhỏ và kiểm thử cô lập.

## 6. Đọc meter qua Spring Boot Actuator

Để kiểm tra meter từ HTTP endpoint, hãy bật exposure cho endpoint `metrics`. Trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi ứng dụng khởi động và có ít nhất một lần ghi nhận, có thể gọi:

```text
GET /actuator/metrics/orders.completed
GET /actuator/metrics/orders.completed?tag=channel:web
GET /actuator/metrics/checkout.duration
```

Endpoint metrics trả về các measurement mà registry cung cấp. Với counter, hãy tìm measurement `COUNT`; với timer, thường có `COUNT` và `TOTAL_TIME`, tùy registry. Truy vấn có tham số tag giúp lọc đúng chuỗi meter đã đăng ký. Tên metric trong endpoint là tên meter Micrometer; tên xuất ra backend có thể được chuẩn hóa theo quy tắc đặt tên của registry.

Nếu endpoint trả về 404, kiểm tra ứng dụng đã thêm Actuator, endpoint `metrics` đã được expose, ứng dụng có đang dùng management port hoặc base path riêng không, và meter đã được ghi nhận chưa. Nếu ứng dụng có Spring Security, cần bảo đảm quyền truy cập endpoint theo chính sách bảo mật của môi trường. Chỉ expose endpoint giám sát ra mạng có kiểm soát; không mở công khai chỉ để thử nghiệm.

Actuator endpoint hữu ích để xác nhận meter tại ứng dụng. Để gửi dữ liệu đến hệ giám sát, dự án còn cần registry/exporter tương ứng với backend, chẳng hạn registry Prometheus hoặc OTLP. Chỉ thêm `micrometer-core` hay dùng `SimpleMeterRegistry` không tự tạo endpoint scrape hoặc đẩy dữ liệu ra ngoài.

## 7. Kiểm tra nhanh bằng bài thử nhỏ

Với `SimpleMeterRegistry`, có thể xác minh số đo ngay trong unit test mà không cần chạy Spring Boot hay backend bên ngoài:

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.counter("test.jobs.completed", "queue", "email")
        .increment(2.0);

Timer timer = registry.timer("test.job.duration", "queue", "email");
timer.record(() -> runJob());

Counter counter = registry.find("test.jobs.completed")
        .tag("queue", "email")
        .counter();
Timer recordedTimer = registry.find("test.job.duration")
        .tag("queue", "email")
        .timer();

assert counter != null && counter.count() == 2.0;
assert recordedTimer != null && recordedTimer.count() == 1;

registry.close();
```

Đoạn kiểm tra trên minh họa các điều cần xác nhận: counter tăng đúng lượng, timer ghi nhận đúng số lần, và registry tìm lại được meter bằng đúng tên cùng tag. Trong test thực tế, thay `runJob()` bằng lời gọi có sẵn trong fixture hoặc một thao tác giả lập phù hợp; dùng assertion của framework kiểm thử dự án thay cho Java `assert` nếu cần kết quả luôn được kiểm tra khi chạy test.

Khi kiểm tra tích hợp Spring Boot, thực hiện thêm một lần gọi nghiệp vụ rồi đọc `/actuator/metrics/...` hoặc endpoint của exporter. Việc test qua `SimpleMeterRegistry` chỉ xác minh instrumentation trong tiến trình; nó không xác minh cấu hình mạng, scrape, xác thực, chuyển đổi tên metric hay truy vấn ở backend.

## 8. Lỗi thường gặp khi đăng ký và đọc meter

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `registry.find(...).counter()` trả về `null` | Sai tên meter, thiếu tag hoặc giá trị tag khác với lúc đăng ký | Đối chiếu chính xác tên và từng cặp tag; xác nhận đã gọi API đăng ký trước đó |
| Counter luôn bằng 0 | Luồng nghiệp vụ chưa chạy hoặc nhánh tăng counter chưa được thực thi | Đặt phép tăng tại điểm sự kiện thực sự hoàn tất và kiểm tra nhánh điều kiện |
| Timer có `count` bằng 0 | Chưa gọi `record(...)` hoặc đoạn mã chưa chạy | Kiểm tra luồng gọi và bảo đảm thao tác được bọc trong timer |
| Actuator không hiển thị meter | Dùng registry độc lập, thiếu Actuator hoặc endpoint chưa expose | Inject registry do Spring Boot cấu hình và kiểm tra cấu hình endpoint |
| Có quá nhiều chuỗi thời gian | Tag nhận giá trị gần như không giới hạn | Thay ID hoặc dữ liệu tự do bằng nhóm giá trị hữu hạn |
| Không thấy dữ liệu ở backend | Chưa có registry/exporter hoặc backend chưa scrape/nhận dữ liệu | Kiểm tra dependency exporter, endpoint scrape, cấu hình đích và log kết nối |

Một meter được định danh bởi tên và tag. Nếu cùng một tên nhưng thêm tag `result=success`, đó là một chuỗi riêng so với `result=failure`. Vì vậy, khi đọc lại, phải dùng đúng các tag mà code đã dùng khi đăng ký. Hãy chuẩn hóa tên meter và tag giữa các thành phần để dashboard và truy vấn có thể dự đoán được cấu trúc dữ liệu.

## Checklist hoàn thành

- [ ] Dự án đã khai báo `micrometer-core` hoặc `spring-boot-starter-actuator` phù hợp với cách tích hợp.
- [ ] Có một `MeterRegistry` được tạo rõ ràng cho ví dụ độc lập hoặc được Spring Boot inject cho ứng dụng.
- [ ] Counter được tăng tại điểm sự kiện hoàn tất và trả về giá trị mong đợi khi đọc `count()`.
- [ ] Timer bọc đúng thao tác cần đo và trả về số lần cùng tổng thời gian khi đọc lại.
- [ ] Tên meter và tag nhất quán; tag chỉ dùng giá trị hữu hạn.
- [ ] Đã phân biệt registry trong bộ nhớ dùng thử nghiệm với registry/exporter gửi dữ liệu đến backend.

Khi đã đăng ký và đọc lại thành công một `Counter` hoặc `Timer`, bạn đã hoàn thành vòng đo lường cơ bản: chọn đại lượng, ghi nhận tại điểm thích hợp và xác minh dữ liệu trong registry. Các bước tiếp theo là cấu hình exporter, kiểm tra định dạng metric được xuất và xây dựng truy vấn giám sát từ các số đo đó.
