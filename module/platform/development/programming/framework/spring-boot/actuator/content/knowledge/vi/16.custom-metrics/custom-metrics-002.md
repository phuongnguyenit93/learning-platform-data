# Đăng ký Counter để đếm sự kiện theo chiều tăng

## 1. Counter trả lời câu hỏi nào?

Giả sử ứng dụng gửi thông báo qua email và SMS. Ta muốn biết đã quan sát được bao nhiêu lần nhà cung cấp xác nhận chấp nhận yêu cầu gửi, rồi theo dõi số xác nhận mỗi giây.

Đại lượng cần đo là **số sự kiện đã xảy ra**, phù hợp với `Counter` của Micrometer. Mỗi lần sự kiện được xác nhận, ta cộng thêm vào bộ đếm:

```text
Ban đầu:                  0
Một xác nhận mới:         1
Ba xác nhận mới nữa:      4
Hai xác nhận mới nữa:     6
```

Bộ đếm tích lũy theo chiều tăng: giá trị có thể đứng yên khi không có sự kiện mới, nhưng ứng dụng không chủ động trừ đi để “hoàn tác” một sự kiện.

Trong bài này, “nhà cung cấp chấp nhận” chỉ là mức xác nhận từ nhà cung cấp, không đồng nghĩa người nhận cuối cùng đã đọc hoặc đã nhận thông báo. Điểm ghi phải khớp chính xác với ý nghĩa đã công bố.

`Counter` không phải biến trạng thái bất kỳ. “Tổng số thông báo từng được chấp nhận” là một đại lượng; “số thông báo hiện đang chờ gửi” là đại lượng khác. Giá trị đang chờ có thể tăng và giảm, nên cần một phép đo trạng thái như `Gauge`.

Đường đi của phép đo là:

```text
Sự kiện xảy ra
    → code gọi increment
    → Counter cập nhật trong MeterRegistry
    → Actuator/exporter cung cấp số đo
    → hệ thống giám sát tính tốc độ hoặc mức tăng
```

Gọi `increment()` không có nghĩa mỗi sự kiện lập tức tạo một HTTP request tới hệ thống giám sát. Cách xuất và thời điểm thu thập do registry/backend quyết định.

## 2. Phân biệt đăng ký, tăng và đọc

Ba thao tác có vai trò riêng:

| Thao tác | Ví dụ API | Ý nghĩa |
| --- | --- | --- |
| Đăng ký | `registry.counter(...)` hoặc `builder.register(registry)` | Lấy Counter gắn với registry và định danh cụ thể |
| Tăng | `counter.increment()`, `counter.increment(amount)` | Ghi nhận thêm lượng sự kiện vừa xảy ra |
| Đọc | `counter.count()` | Quan sát giá trị hiện được Counter cung cấp |

**Đăng ký không phải ghi nhận một sự kiện.** Với `SimpleMeterRegistry` ở chế độ mặc định trong ví dụ, Counter vừa đăng ký có count bằng 0.

Có thể đăng ký một lần trong constructor của thành phần đo, giữ tham chiếu trong field rồi sử dụng cho nhiều sự kiện. Việc này làm rõ vòng đời phép đo và tránh tra cứu lại cùng Counter ở đường chạy thường xuyên.

Không có API `decrement()`, `set(...)` hoặc `reset()` trên giao diện `Counter`. Nếu cần trạng thái lên/xuống, chọn loại meter khác; nếu muốn xem số sự kiện trong ngày, truy vấn theo khoảng thời gian thay vì reset Counter mỗi nửa đêm.

Giao diện và cách đăng ký được mô tả trong [Counter của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Counter.java).

## 3. Hai cách đăng ký Counter

### 3.1. Đăng ký nhanh qua MeterRegistry

Đoạn sau dùng khi đã có một biến `registry` kiểu `MeterRegistry`:

```java
Counter accepted = registry.counter(
        "notification.provider.accepted",
        "channel", "email",
        "provider", "primary");
```

Tên metric là `notification.provider.accepted`. Các chuỗi theo sau là từng cặp khóa–giá trị của tag:

```text
channel  → email
provider → primary
```

Danh sách tag phải đủ cặp. Không truyền một danh sách có số phần tử lẻ hoặc một tag value null. Dữ liệu từ bên ngoài cần được chuẩn hóa trước khi dùng làm tag.

Cách gọi này vừa tìm vừa đăng ký: nếu Counter tương ứng đã tồn tại trong registry, nó trả lại Counter đó; nếu chưa có, registry tạo và giữ meter phù hợp.

### 3.2. Đăng ký bằng Counter.builder

Builder cho phép đặt thêm mô tả và đơn vị khi cần:

```java
Counter accepted = Counter.builder("notification.provider.accepted")
        .description("Provider acceptance confirmations observed")
        .tag("channel", "email")
        .tag("provider", "primary")
        .register(registry);
```

Chỉ gọi `Counter.builder(...)` chưa đủ. Builder là đối tượng cấu hình; phải gọi `register(registry)` để có Counter sử dụng được.

`description` diễn giải nội dung phép đo. Phương thức `baseUnit(...)` có thể bổ sung đơn vị cho đại lượng được đếm, nhưng không tự biến đổi số đầu vào. Ví dụ, với bộ đếm dung lượng, khai báo byte không tự chuyển một giá trị đang tính bằng kilobyte thành byte.

Trong bài, mỗi đơn vị đếm là một lần quan sát xác nhận nên ta không thêm một đơn vị riêng vào tên xuất. Nếu cấu hình base unit, cần kiểm tra lại tên series mà backend sinh.

Hãy quyết định metadata lúc đăng ký đầu tiên. Đăng ký lại cùng định danh với mô tả hoặc đơn vị khác không phải cơ chế đáng tin cậy để cập nhật hợp đồng của meter.

### 3.3. Định danh gồm tên và tập tag

Trong cùng registry, hai yêu cầu đăng ký có cùng tên và cùng tập tag tìm đến cùng Counter. Thứ tự các cặp tag không tạo Counter mới.

Ngược lại, thay `channel=email` thành `channel=sms` sẽ tạo một nhóm dữ liệu riêng:

```text
notification.provider.accepted{channel=email, provider=primary}
notification.provider.accepted{channel=sms,   provider=primary}
```

Tag là chiều phân nhóm, không phải thuộc tính thay đổi tại chỗ của một Counter đang giữ. Muốn ghi cho SMS, sử dụng Counter của SMS; không đổi tag trên Counter email rồi mong số cũ tự chuyển nhóm.

Một registry khác có vòng đời dữ liệu riêng. Hai Counter cùng tên và tag trong hai `SimpleMeterRegistry` độc lập không tự chia sẻ số đếm. Trong Spring Boot có composite registry, việc phối hợp các registry con do composite thực hiện; điều đó không có nghĩa mọi registry tự tạo trong ứng dụng đều tự liên thông.

## 4. Tăng đúng lượng, tại đúng thời điểm

### 4.1. Một sự kiện hoặc một lô sự kiện

```java
accepted.increment();
accepted.increment(3);
```

Lệnh đầu tăng một. Lệnh sau tăng ba, phù hợp khi ta vừa xác nhận ba sự kiện cùng loại.

Không dùng `increment(currentTotal)` để “đặt” tổng hiện tại. Nếu tổng nguồn lần lượt là 10 rồi 12 mà gọi tăng 10 rồi tăng 12, Counter trở thành 22. Trường hợp nguồn đã có một tổng tích lũy cần một cách tích hợp khác, chẳng hạn đọc bằng `FunctionCounter` khi đáp ứng hợp đồng của nó, hoặc tính phần tăng một cách có kiểm soát. Không biến Counter thành phép gán.

`increment(double amount)` nhận số thực. Điều đó cho phép đếm một lượng dương nói chung, nhưng nếu đại lượng là số sự kiện rời rạc thì nên truyền số nguyên có ý nghĩa. Không làm tròn một dữ liệu không rõ nghĩa chỉ để nó trông giống bộ đếm.

### 4.2. Không dựa vào giá trị âm hoặc giá trị không hợp lệ

Hợp đồng sử dụng Counter là tăng bằng lượng dương. Không dùng số âm để giảm count và không dựa vào việc mọi registry đều ném ngoại lệ hoặc đều bỏ qua cùng một kiểu đầu vào sai.

Với dữ liệu do bên ngoài cung cấp, cần chặn số âm, `NaN` và vô cực trước điểm ghi phù hợp. Trường hợp không có sự kiện mới thì không cần gọi tăng.

Ví dụ một adapter nhận số lượng nguyên có thể quy định:

```text
amount < 0 → dữ liệu đầu vào không hợp lệ
amount = 0 → không phát sinh thao tác tăng
amount > 0 → tăng đúng amount
```

Nếu chỉ có ba trong năm thông báo của một lô được nhà cung cấp chấp nhận, tăng ba; không tăng năm chỉ vì đã gửi năm yêu cầu.

Xem [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

### 4.3. Điểm ghi quyết định ý nghĩa của số đếm

Nếu đặt tăng trước lời gọi nhà cung cấp, metric thực tế đếm lần thử gửi. Nếu đặt sau khi đã kiểm tra phản hồi chấp nhận, metric đếm xác nhận chấp nhận.

```text
Bắt đầu gửi
  → gọi nhà cung cấp
  → nhận phản hồi
  → kiểm tra có được chấp nhận không
  → chỉ khi được chấp nhận: tăng Counter accepted
```

Một lời gọi HTTP không ném ngoại lệ chưa đủ chứng minh nội dung phản hồi là chấp nhận. Quy tắc xác nhận phải dựa vào giao thức và hợp đồng tích hợp.

Với xử lý bất đồng bộ, tăng ở nhánh đã nhận kết quả thực sự. Việc trả về một `CompletableFuture` hay đưa yêu cầu vào queue chưa phải xác nhận của nhà cung cấp.

Nếu retry tạo thêm một phản hồi chấp nhận, Counter đếm phản hồi có thể tăng thêm. Muốn đếm thông báo duy nhất được chấp nhận thì phải xử lý trùng ở cấp nghiệp vụ và đặt phép tăng sau ranh giới xác nhận duy nhất đó. Counter không tự nhận biết message ID đã được đếm.

## 5. Ví dụ chạy được: đăng ký lại, phân nhóm và tăng đồng thời

Chương trình sau dùng Java 17 và Micrometer 1.13.0. Không cần khởi động Spring Boot hoặc kết nối dịch vụ gửi thông báo; các lần tăng là dữ liệu thí nghiệm.

### 5.1. Chuẩn bị dependency trong thư mục thí nghiệm riêng

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

Task chỉ lấy các dependency cần chạy, bao gồm dependency bắc cầu. Phiên bản được ghim để ví dụ tái lập được; trong ứng dụng Spring Boot hãy sử dụng phiên bản Micrometer mà BOM của ứng dụng quản lý.

Với Gradle 8.x và JDK 17 đã có, chạy:

```bash
gradle -q copyRuntimeDependencies
```

Nếu thư mục đã có Gradle Wrapper, dùng wrapper tương ứng thay `gradle`. Lần lấy dependency đầu tiên cần kết nối tới Maven Central.

### 5.2. Chương trình CounterRegistrationDemo.java

Đặt tệp Java này ở cùng thư mục với `build.gradle`; ta sẽ biên dịch bằng `javac`, không dùng source layout Gradle trong thí nghiệm này.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CounterRegistrationDemo {
    private static void printCount(String label, Counter counter) {
        System.out.println(label + "=" + Math.round(counter.count()));
    }

    public static void main(String[] args) throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter email = Counter.builder("notification.provider.accepted")
                    .description("Provider acceptance confirmations observed")
                    .tags("channel", "email", "provider", "primary")
                    .register(registry);

            printCount("initial.email", email);
            email.increment();
            email.increment(3);
            printCount("afterSingleAndBatch.email", email);

            Counter alias = registry.counter(
                    "notification.provider.accepted",
                    "provider", "primary", "channel", "email");
            System.out.println("sameCounter=" + (email == alias));
            alias.increment(2);
            printCount("afterAlias.email", email);

            Counter sms = registry.counter(
                    "notification.provider.accepted",
                    "channel", "sms", "provider", "primary");
            sms.increment(2);
            printCount("sms", sms);

            ExecutorService workers = Executors.newFixedThreadPool(4);
            try {
                List<Future<?>> futures = new ArrayList<>();
                for (int worker = 0; worker < 4; worker++) {
                    futures.add(workers.submit(() -> {
                        for (int event = 0; event < 250; event++) {
                            email.increment();
                        }
                    }));
                }
                for (Future<?> future : futures) {
                    future.get();
                }
            } finally {
                workers.shutdownNow();
            }

            printCount("parallel.email", email);
            System.out.println("meter.ids=" + registry.getMeters().size());

            SimpleMeterRegistry secondRegistry = new SimpleMeterRegistry();
            try {
                Counter otherEmail = secondRegistry.counter(
                        "notification.provider.accepted",
                        "channel", "email", "provider", "primary");
                printCount("secondRegistry.email", otherEmail);
                printCount("firstRegistry.email", email);
            } finally {
                secondRegistry.close();
            }
        } finally {
            registry.close();
        }
    }
}
```

### 5.3. Biên dịch và chạy

Windows PowerShell hoặc Command Prompt:

```powershell
javac --release 17 -cp "build/runtime-libs/*" CounterRegistrationDemo.java
java -cp ".;build/runtime-libs/*" CounterRegistrationDemo
```

Linux/macOS dùng dấu hai chấm để tách các mục classpath:

```bash
javac --release 17 -cp "build/runtime-libs/*" CounterRegistrationDemo.java
java -cp ".:build/runtime-libs/*" CounterRegistrationDemo
```

Stdout khi chạy thành công:

```text
initial.email=0
afterSingleAndBatch.email=4
sameCounter=true
afterAlias.email=6
sms=2
parallel.email=1006
meter.ids=2
secondRegistry.email=0
firstRegistry.email=1006
```

### 5.4. Giải thích kết quả

1. Counter email mới đăng ký có giá trị 0 trong registry thí nghiệm.
2. Tăng một rồi tăng ba cho kết quả 4.
3. `alias` có cùng tên và cùng tag với `email`, dù thứ tự tag đảo lại. `sameCounter=true` và tăng qua alias làm Counter email thành 6.
4. Counter SMS có tag khác nên giá trị 2 của nó không cộng vào Counter email.
5. Bốn tác vụ cùng tăng, mỗi tác vụ 250 lần: thêm `4 × 250 = 1.000`. Kết quả email cuối cùng là `6 + 1.000 = 1.006`.
6. Đăng ký alias không tạo thêm meter; registry đầu có hai ID tương ứng email và SMS.
7. Registry thứ hai có Counter email mới bằng 0, trong khi registry đầu vẫn giữ 1.006.

`Future.get()` bảo đảm từng tác vụ đã hoàn thành trước khi in kết quả. Không thay bằng một lần `Thread.sleep(...)` rồi đoán công việc đã xong.

Phương thức `Math.round(...)` chỉ giúp stdout gọn vì các giá trị trong thí nghiệm đều là số nguyên nhỏ. API `count()` thực tế trả về `double`; không coi việc làm tròn là một phần của cơ chế Counter.

## 6. Dùng Counter trong thành phần Spring Boot

Ứng dụng cần Spring Boot Actuator để có hạ tầng metrics. Với dependency management của Boot đã được cấu hình, phần dependency thường có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Starter này không tự tạo một HTTP server. Phần kiểm tra qua HTTP bên dưới giả định ứng dụng đã có web starter phù hợp. Nếu muốn xuất Prometheus, còn cần `io.micrometer:micrometer-registry-prometheus` trên runtime classpath.

Tạo `NotificationCounters.java` trong package được Spring quét. Đây là lớp thành phần dùng trong ứng dụng Boot, không phải chương trình `main` độc lập:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.EnumMap;
import java.util.Objects;
import org.springframework.stereotype.Component;

@Component
public final class NotificationCounters {
    public enum Channel {
        EMAIL, SMS
    }

    private final EnumMap<Channel, Counter> acceptedByChannel =
            new EnumMap<>(Channel.class);

    public NotificationCounters(MeterRegistry registry) {
        acceptedByChannel.put(Channel.EMAIL,
                createCounter(registry, "email"));
        acceptedByChannel.put(Channel.SMS,
                createCounter(registry, "sms"));
    }

    private static Counter createCounter(
            MeterRegistry registry, String channel) {
        return Counter.builder("notification.provider.accepted")
                .description("Provider acceptance confirmations observed")
                .tags("channel", channel, "provider", "primary")
                .register(registry);
    }

    public void accepted(Channel channel) {
        acceptedByChannel.get(Objects.requireNonNull(channel)).increment();
    }

    public void acceptedBatch(Channel channel, int amount) {
        Counter counter =
                acceptedByChannel.get(Objects.requireNonNull(channel));
        if (amount < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
        if (amount > 0) {
            counter.increment(amount);
        }
    }
}
```

Điểm tích hợp sẽ gọi `accepted(Channel.EMAIL)` sau một xác nhận email, hoặc `acceptedBatch(Channel.EMAIL, n)` cho n xác nhận của một lô. Không gọi cả hai cách cho cùng tập sự kiện.

Lớp đăng ký trước đúng hai nhóm tag và giữ các Counter trong field. Điều này giúp xuất hiện cả nhóm chưa có sự kiện với count ban đầu bằng 0 khi thành phần đã được khởi tạo và meter không bị filter từ chối.

`EnumMap` chỉ được ghi trong constructor rồi đọc sau đó; các phép tăng đi vào Counter đã có. Ví dụ không yêu cầu tạo và sửa map theo từng request.

### 6.1. Dùng registry do Spring quản lý

Inject `MeterRegistry` giúp meter đi qua registry, exporter, common tags và filter của ứng dụng. Không tự tạo một `SimpleMeterRegistry` trong service rồi mong endpoint Actuator tự tổng hợp số đo từ đối tượng riêng ấy.

Các hàm static của `Metrics` thao tác với global registry. Trong ứng dụng Boot, ưu tiên registry được inject để vòng đời và cấu hình rõ ràng.

Nếu cần khởi tạo common tags hoặc tùy chỉnh registry, sử dụng cơ chế cấu hình của Boot trước thời điểm đăng ký meter. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 6.2. Giới hạn tag ngay tại điểm ghi

`channel` trong lớp chỉ có email và SMS; `provider` trong ví dụ là một mã cấu hình ổn định. Không thay chúng bằng nội dung tùy ý của request.

Không tạo tag theo email người nhận, số điện thoại, mã thông báo hoặc trace ID. Mỗi giá trị mới có thể tạo thêm Counter và chuỗi dữ liệu. Những định danh chi tiết thuộc log/tracing hoặc kho dữ liệu nghiệp vụ.

Cùng một họ Counter nên giữ bộ khóa tag nhất quán. Không đăng ký một nhóm chỉ có `channel` rồi nhóm khác cùng tên lại thêm `recipient`. Ngoài chi phí dữ liệu, một số backend còn đặt ràng buộc đối với tập nhãn của cùng một tên metric.

Đăng ký lại cùng tên và tag không làm tăng số meter; đăng ký cùng tên với hàng triệu tag khác nhau thì có.

### 6.3. Không cần @Counted để dùng Counter thủ công

Lời gọi `increment` trực tiếp đã ghi nhận sự kiện. `@Counted` là một cách instrumentation khác, thường cần thành phần hỗ trợ annotation/aspect phù hợp; chỉ gắn annotation vào một phương thức tùy ý chưa bảo đảm phép đếm hoạt động.

Một annotation đếm lượt gọi phương thức cũng chưa chắc khớp “nhà cung cấp đã chấp nhận”. Nếu phương thức bao retry hoặc trả về trước khi biết kết quả bất đồng bộ, phải kiểm tra rõ phạm vi đếm. Khi đã tăng thủ công, tránh bổ sung một phép đếm khác cho cùng định nghĩa mà không có chủ đích.

## 7. Tăng đồng thời an toàn không có nghĩa toàn bộ nghiệp vụ là nguyên tử

Các Counter chuẩn của Micrometer được dùng để nhận phép tăng từ nhiều luồng; thí nghiệm ở trên kiểm chứng kết quả cuối sau khi các tác vụ đã hoàn thành.

Không tự bảo vệ số đếm bằng cách:

```text
đọc count hiện tại → cộng một trong biến cục bộ → tìm cách đặt lại count
```

Hãy gọi trực tiếp `increment()`. Counter chịu trách nhiệm cập nhật số đo; ứng dụng không cần tự tạo vòng đọc–sửa–ghi bên ngoài.

Tuy nhiên, cần phân biệt:

| Tính chất | Counter có tự giải quyết không? |
| --- | --- |
| Nhiều luồng cùng ghi vào Counter chuẩn | Có cơ chế cập nhật phù hợp trong triển khai |
| Chống đếm trùng cùng một thông báo | Không |
| Giao dịch DB và phép tăng cùng commit/rollback | Không |
| Tăng hai Counter thành một giao dịch nguyên tử | Không |
| Đọc nhiều meter thành một ảnh chụp nhất quán | Không |
| Giữ dữ liệu sau khi tiến trình chết | Không tự bảo đảm |

Một luồng có thể tăng `accepted` rồi một luồng khác thu thập dữ liệu trước khi metric liên quan được cập nhật. Vì vậy không dùng hai số đo vừa đọc để thực hiện quyết định nghiệp vụ đòi hỏi tính nguyên tử.

Đọc `count()` trong lúc nhiều luồng vẫn đang tăng là một quan sát ở thời điểm đó, không phải cam kết rằng mọi sự kiện đang diễn ra đã được phản ánh. Để kiểm thử tổng cuối, đợi công việc hoàn thành như ví dụ.

## 8. Xác minh Counter qua Actuator

### 8.1. Mở endpoint chẩn đoán trong môi trường cục bộ

Với ứng dụng web đã có Actuator, cấu hình thí nghiệm:

```yaml
management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Quyền truy cập vẫn chịu ảnh hưởng của Spring Security và cấu hình mạng đang dùng. Hợp nhất với phần `management` sẵn có, không tạo hai khóa gốc trùng nhau.

Sau khi thành phần `NotificationCounters` được khởi tạo, gọi:

```bash
curl "http://127.0.0.1:8081/actuator/metrics"
curl "http://127.0.0.1:8081/actuator/metrics/notification.provider.accepted"
curl "http://127.0.0.1:8081/actuator/metrics/notification.provider.accepted?tag=channel:email&tag=provider:primary"
```

Trên PowerShell, có thể dùng `curl.exe` để tránh nhầm với alias.

Endpoint dùng tên `notification.provider.accepted` trong Micrometer. Với registry tích lũy, phần `measurements` của Counter có thống kê `COUNT`. Giá trị cụ thể phụ thuộc sự kiện đã phát sinh; không có một JSON số lượng cố định đúng cho mọi ứng dụng.

Nếu bỏ bộ lọc channel, endpoint metrics có thể cộng số đếm của các Counter cùng tên phù hợp. Trong thí nghiệm độc lập, email 1.006 và SMS 2 tạo tổng 1.008; con số tổng không có nghĩa email riêng đã đạt 1.008.

### 8.2. Xuất sang Prometheus

Thêm registry Prometheus vào dependency của ứng dụng Boot và bổ sung endpoint:

```groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Đây là phần cập nhật cấu hình endpoint ở ví dụ trước, không phải một khóa `management` thứ hai trong cùng tệp.

Với tên và cấu hình không có base unit riêng trong bài, series Counter thường có dạng:

```text
notification_provider_accepted_total{channel="email",provider="primary"} 1006.0
```

Giá trị 1006.0 minh họa số đếm email trong bộ dữ liệu thí nghiệm; ứng dụng Boot đang chạy có giá trị theo sự kiện thực tế của nó và có thể có thêm nhãn. Xem endpoint `/actuator/prometheus` để xác nhận tên, giá trị và toàn bộ nhãn.

Không đưa tên có hậu tố Prometheus vào đường dẫn `/actuator/metrics/...`. Cũng không tự thêm `_total` vào tên trong mã chỉ để đoán tên xuất.

## 9. Đọc tốc độ tăng và hiểu reset

### 9.1. Tổng thô bị ảnh hưởng bởi thời gian ứng dụng đã chạy

Một instance đã chạy bảy ngày có count 500.000; instance mới chạy năm phút có count 2.000. Không thể từ hai tổng thô kết luận instance thứ nhất đang xử lý nhanh hơn ở hiện tại.

Với hệ thống như Prometheus, thường phân tích tốc độ hoặc mức tăng trong một cửa sổ:

```promql
sum by (channel) (
  rate(notification_provider_accepted_total{provider="primary"}[5m])
)
```

Truy vấn biểu diễn tốc độ trung bình số xác nhận mỗi giây trong cửa sổ năm phút, cộng các series phù hợp theo channel.

Nếu backend chứa nhiều ứng dụng cùng tên metric, bổ sung nhãn xác định đúng dịch vụ/môi trường trước khi cộng; không vô tình gộp dữ liệu không cùng phạm vi.

Muốn xem số xác nhận tăng thêm trong khoảng 15 phút:

```promql
sum by (channel) (
  increase(notification_provider_accepted_total{provider="primary"}[15m])
)
```

`increase` có thể trả số không nguyên vì cách ngoại suy theo cửa sổ lấy mẫu. Nó là kết quả truy vấn từ dữ liệu giám sát, không phải sổ cái chính xác từng sự kiện. Xem [Prometheus — Query functions](https://prometheus.io/docs/prometheus/2.55/querying/functions/).

### 9.2. Reset của tiến trình không phải decrement trong code

Khi instance khởi động lại, Counter tích lũy của tiến trình mới thường bắt đầu lại. Biểu đồ thô có thể rơi từ một số lớn về số nhỏ.

Ứng dụng không cần giảm hoặc reset Counter để xử lý việc này. Backend dùng hàm dành cho counter, chẳng hạn `rate` hoặc `increase`, để xử lý reset theo từng series.

Tính tốc độ theo từng series trước rồi mới cộng như các truy vấn trên. Cộng các tổng của nhiều instance trước khi xét mức tăng có thể làm mất dấu reset của từng instance.

Reset cũng không khôi phục những sự kiện xảy ra trước lần thu thập đầu tiên hoặc dữ liệu chưa kịp xuất khi tiến trình chết. Metrics không thay thế lưu trữ bền vững cần cho đối soát nghiệp vụ.

### 9.3. Không áp giả định tích lũy của một registry cho mọi backend

`SimpleMeterRegistry` mặc định trong thí nghiệm và Prometheus thường thể hiện count tích lũy. Một số registry xuất theo từng khoảng thời gian cố định, thường gọi là `step`, nên cách quan sát count có thể phản ánh kỳ đã kết thúc thay vì toàn bộ vòng đời tiến trình.

Đây là cách tổng hợp của registry, không phải yêu cầu để code nghiệp vụ tự reset Counter sau mỗi kỳ. Khi chuyển backend, đọc tài liệu registry và cách tổng hợp thay vì dùng `count()` như một tổng bền vững chung cho mọi hệ thống.

Tham khảo [Micrometer — Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

### 9.4. Không có dữ liệu khác với không có sự kiện

Counter đã đăng ký nhưng chưa tăng có thể có giá trị 0. Meter chưa được tạo, bị filter từ chối hoặc không được thu thập lại có thể không xuất hiện trong backend.

`rate` cần đủ mẫu. Một tiến trình vừa lên chưa có đủ dữ liệu không tự chứng minh tốc độ bằng 0. Khi xây cảnh báo, cần xác định cả tình huống metric vắng mặt và tình huống số đếm không tăng.

## 10. Chẩn đoán khi Counter không xuất hiện hoặc không tăng

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Không tìm thấy tên metric | Builder đã gọi register chưa? Thành phần đăng ký đã được khởi tạo chưa? |
| Code tăng nhưng Actuator không thấy | Có đang ghi vào registry riêng thay vì registry của Spring không? |
| Có email nhưng không có SMS | SMS đã được đăng ký chưa? Đường chạy có dùng đúng tag không? |
| Có Counter nhưng count vẫn 0 | Điểm gọi có thực sự đi qua nhánh sự kiện không? Meter có bị trả về dạng NOOP không? |
| Count lớn hơn dự kiến | Có retry, callback lặp hoặc hai điểm cùng tăng cho một sự kiện không? |
| Count thấp hơn dự kiến | Có đường đi chưa được đo, lô thất bại một phần, bộ lọc từ chối hoặc mất dữ liệu khi restart không? |
| Tổng hợp khác số của một tag | Endpoint/truy vấn có đang cộng nhiều channel, provider hoặc instance không? |
| Sau đăng ký lại count không về 0 | Cùng tên và tag đang trả lại Counter đã tồn tại |
| Backend có quá nhiều series | Có tag chứa định danh người nhận, request hoặc thông tin động không? |
| count thay đổi theo kỳ | Registry có dùng cơ chế step không? |
| Có timer rồi mà thêm counter nữa | Hai meter có đếm cùng sự kiện không, hay thực sự là hai ranh giới khác nhau? |

`MeterFilter` có thể từ chối một meter và trả về đối tượng không ghi nhận số đo (NOOP). Lúc đó gọi `increment` không nhất thiết ném ngoại lệ nhưng số liệu mong đợi vẫn không xuất hiện. Kiểm tra cấu hình lọc và điều kiện cho phép tag, thay vì ghi lặp nhiều lần để thử.

Xem [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

Một số lỗi cần tránh ngay trong thiết kế:

- Không xóa rồi đăng ký lại meter theo từng request để lấy số đếm mới.
- Không tạo tên chứa mã người nhận hoặc ngày hiện tại để giả lập nhóm/reset.
- Không dùng Counter đang tăng để đại diện số lượng hiện có trong queue.
- Không giảm Counter accepted khi sau đó có thông báo lỗi giao tới người nhận; nếu cần, ghi một sự kiện lỗi với định nghĩa riêng.
- Không coi registry trong bộ nhớ là nơi đếm duy nhất, chống trùng hoặc giữ lịch sử nghiệp vụ.
- Không thêm counter chỉ để đếm chính các sự kiện đã có count của `Timer` hoặc `DistributionSummary`, trừ khi có một phạm vi đo khác rõ ràng.

## 11. Thực hành

1. Trong chương trình độc lập, đổi lượng tăng theo lô từ 3 thành 5. Tính trước các giá trị email sau alias và sau bốn luồng, rồi chạy đối chiếu.
2. Đổi tag alias từ `channel=email` thành `channel=sms`. Dự đoán `sameCounter`, số meter ID và số đếm mỗi nhóm.
3. Thêm một tag `provider=backup` vào một Counter mới. Giải thích vì sao đó là một định danh khác và truy vấn tổng hợp theo channel sẽ cộng những nhóm nào.
4. Chạy tám tác vụ, mỗi tác vụ tăng 125 lần, vẫn chờ đủ `Future`. Giải thích vì sao lượng tăng cuối giống thí nghiệm bốn tác vụ.
5. Với lô có 20 yêu cầu nhưng chỉ 17 xác nhận được chấp nhận, xác định Counter accepted tăng bao nhiêu. Nếu muốn theo dõi 20 lần thử và ba lần bị từ chối, đề xuất phép đo riêng.
6. Vẽ vị trí tăng Counter trong luồng gửi bất đồng bộ có retry. Nêu rõ phép đo đếm lần thử, phản hồi chấp nhận hay thông báo duy nhất.
7. Giải thích vì sao Counter 0, series vắng mặt và chưa đủ mẫu để tính `rate` là ba tình huống cần phân biệt.

Sau khi thực hành, cần tự chứng minh được rằng **định danh đúng → Counter đúng → điểm ghi đúng → lượng tăng đúng → truy vấn đúng phạm vi**. Đó là nền tảng để một bộ đếm đơn giản trở thành số đo có thể tin cậy trong vận hành.
